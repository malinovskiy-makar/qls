# -*- coding: utf-8 -*-
"""Шлюз рендера для трёх новых источников (Фаза 4 брифа import-new-sources).

Ставит `content_format='markdown'` тем задачам Школково / SolveHub /
ЛЭШ Гамма, которые пропускает `render_preflight_v2()` — настоящий KaTeX,
а не текстовые эвристики.

**Чем отличается от `render_legacy_sources` и почему это важно.** У легаси
в базе лежит ИСХОДНЫЙ текст, конвертер запускается на лету, и шлюз судит
конвертированный текст — а сайт показывает сохранённый. У новых источников
такого расхождения нет: конвертер отработал НА ИМПОРТЕ, в базе уже лежит
его результат. Поэтому шлюзу отдаётся ровно то, что лежит в базе, и
`render_markdown(problem.statement)` внутри шлюза — дословно тот же вызов,
что делает шаблон `catalog/problem_detail.html`. Что проверили, то и
покажем.

Инварианты, каждый падает `CommandError`:

1. Ни одна задача с `human_review='approved'` не попадает в кандидаты.
2. Задачи чужих источников не берутся вовсе.
3. `Problem.objects.count()` не меняется.
4. Тексты (`statement`/`answer`/`solution`) не трогаются — команда пишет
   ровно одно поле, `content_format`.
5. Источника нет в базе — падаем, а не отчитываемся «кандидатов 0».

Команда только СТАВИТ markdown и никогда не снимает: задачи, которые уже
стоят на markdown, но шлюз их не пропускает, называются отдельной строкой
и остаются как есть — снятие это решение владельца.

По умолчанию — сухой прогон. Запись — только с `--apply`.
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.corpus_converter.katex_preflight import KatexPreflight
from problems.corpus_converter.preflight_gate import render_preflight_v2
from problems.models import Problem, ProblemFigure, Source

SOURCES = {
    'shkolkovo': 'Школково — банк задач по экономике',
    'solvehub': 'SolveHub — банк задач по экономике',
    'lesh': 'ЛЭШ 2026 — Гамма',
}
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'import_new_sources')


def build_blocks_from_stored(problem, parts):
    """Пары «текст → тот же текст» в порядке показа.

    Исходник и «канонизированный» здесь совпадают намеренно: в базе уже
    лежит выход конвертера, второй прогон дал бы другой текст, и шлюз
    судил бы не то, что увидит ученик. Порядок повторяет
    `catalog/templates/catalog/problem_detail.html`."""
    blocks = [('Условие', problem.statement, problem.statement)]
    for part in parts:
        blocks.append((f'Часть {part.label}', part.statement, part.statement))
    if problem.answer:
        blocks.append(('Ответ', problem.answer, problem.answer))
    if problem.solution:
        blocks.append(('Решение', problem.solution, problem.solution))
    return blocks


def verdict_for(problem, checker):
    """Вердикт шлюза по одной задаче. Отдельная функция — это шов: тесты
    подменяют её, чтобы не поднимать браузер ради проверки отбора."""
    parts = list(problem.parts.all())
    blocks = build_blocks_from_stored(problem, parts)
    available = set(
        ProblemFigure.objects.filter(problem=problem)
        .values_list('tikz_hash', flat=True))
    return render_preflight_v2(
        blocks, checker, raw_statement=problem.statement,
        available_figures=available)


class Command(BaseCommand):
    help = ('Поставить content_format=markdown задачам трёх новых источников, '
            'прошедшим render_preflight_v2. Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать (по умолчанию сухой прогон)')
        parser.add_argument('--source', choices=list(SOURCES),
                            help='только один источник')
        parser.add_argument('--limit', type=int,
                            help='только первые N задач (усечение называется в выводе)')
        parser.add_argument('--flag-fails', action='store_true',
                            help='отказавшим шлюзу поставить needs_quality_review '
                                 '(только вместе с --apply)')
        parser.add_argument('--report-dir',
                            help='куда класть отчёт и бэкап; тесты обязаны давать '
                                 'временную папку — иначе затирают боевой')

    def handle(self, *args, **options):
        """Обёртка: выставить DJANGO_ALLOW_ASYNC_UNSAFE на время прогона и
        ВЕРНУТЬ окружение как было.

        Синхронный playwright поднимает event loop, после чего Django
        запрещает ORM; доступ к базе здесь на чтение и в один поток —
        ровно случай, для которого флаг и предназначен (см. docstring
        `katex_preflight`).

        ⚠️ Ни на импорте модуля, ни «навсегда» эту переменную ставить
        нельзя, и это не стиль. Django импортирует модули команд при
        автопоиске, а тесты команду ещё и запускают — переменная
        оставалась в процессе, и
        `test_production_settings.test_check_deploy_is_clean` падал с
        `async.E001` («не выставляйте DJANGO_ALLOW_ASYNC_UNSAFE в
        развёртывании»). Поймано полным прогоном, не рассуждением.
        """
        previous = os.environ.get('DJANGO_ALLOW_ASYNC_UNSAFE')
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = '1'
        try:
            return self._run(*args, **options)
        finally:
            if previous is None:
                os.environ.pop('DJANGO_ALLOW_ASYNC_UNSAFE', None)
            else:
                os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = previous

    def _run(self, *args, **options):
        do_apply = options['apply']
        limit = options['limit']
        slugs = [options['source']] if options['source'] else list(SOURCES)

        names = {}
        for slug in slugs:
            name = SOURCES[slug]
            source = Source.objects.filter(name=name).first()
            if source is None:
                raise CommandError(
                    f'Источник «{name}» не найден в базе — импорт не выполнялся. '
                    f'Сначала import_{slug}, потом шлюз.')
            names[slug] = source

        problems_before = Problem.objects.count()
        per_source = {}
        pass_ids, fail_ids = [], []
        fail_codes = {}
        approved_total = 0

        with KatexPreflight() as checker:
            for slug, source in names.items():
                base_qs = (
                    Problem.objects.filter(source_references__source=source)
                    .distinct())
                total = base_qs.count()
                approved = base_qs.filter(
                    human_review=Problem.HumanReview.APPROVED).count()
                approved_total += approved
                candidates_qs = base_qs.exclude(
                    human_review=Problem.HumanReview.APPROVED)
                source_pass, source_fail = [], []

                for problem in candidates_qs.prefetch_related('parts').iterator(
                        chunk_size=500):
                    if limit is not None and len(pass_ids) + len(fail_ids) >= limit:
                        break
                    verdict = verdict_for(problem, checker)
                    if verdict.ok:
                        source_pass.append(problem.id)
                        pass_ids.append(problem.id)
                    else:
                        source_fail.append(problem.id)
                        fail_ids.append(problem.id)
                        for code in verdict.codes:
                            fail_codes[code] = fail_codes.get(code, 0) + 1

                per_source[slug] = {
                    'name': source.name, 'total': total, 'approved': approved,
                    'pass': len(source_pass), 'fail': len(source_fail),
                    'pass_ids': source_pass, 'fail_ids': source_fail,
                }
                self.stdout.write(
                    f'{source.name}: всего={total} approved исключено: {approved} '
                    f'PASS={len(source_pass)} FAIL={len(source_fail)}')

        # --- Инвариант: ни одной approved-задачи среди PASS ---
        approved_ids = set(
            Problem.objects.filter(
                source_references__source__in=list(names.values()),
                human_review=Problem.HumanReview.APPROVED,
            ).values_list('id', flat=True))
        overlap = approved_ids & set(pass_ids)
        if overlap:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: {len(overlap)} approved-задач попали в PASS: '
                f'{sorted(overlap)[:30]}')

        already_markdown = set(
            Problem.objects.filter(
                id__in=pass_ids,
                content_format=Problem.ContentFormat.MARKDOWN,
            ).values_list('id', flat=True)) if pass_ids else set()
        to_change = sorted(set(pass_ids) - already_markdown)

        already_md_failing = sorted(
            Problem.objects.filter(
                id__in=fail_ids,
                content_format=Problem.ContentFormat.MARKDOWN,
            ).values_list('id', flat=True)) if fail_ids else []

        total_checked = len(pass_ids) + len(fail_ids)
        share = len(pass_ids) / total_checked * 100 if total_checked else 0.0
        lines = [
            '',
            f'Проверено задач: {total_checked}',
            f'  PASS: {len(pass_ids)} ({share:.1f}%)',
            f'  FAIL: {len(fail_ids)}',
            f'  approved исключено: {approved_total}',
            f'  коды отказов: {dict(sorted(fail_codes.items(), key=lambda x: -x[1]))}',
            f'  уже markdown среди PASS: {len(already_markdown)}',
            f'  будет изменено: {len(to_change)}',
        ]
        if already_md_failing:
            lines.append(
                f'  ⚠️ {len(already_md_failing)} задач уже стоят на markdown, но НЕ '
                f'проходят шлюз — команда их НЕ трогает (она только ставит '
                f'markdown, не снимает). Решение о снятии — за владельцем: '
                f'{already_md_failing[:30]}')
        if limit is not None:
            lines.append(f'  ⚠️ ОХВАТ УСЕЧЁН: --limit {limit} — проверена только '
                         f'часть корпуса')

        out_dir = options.get('report_dir') or OUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        # ⚠️ Усечённый прогон в общий отчёт не пишет. `--limit 5` по
        # одному источнику затирал разбор по всему корпусу файлом на пять
        # задач, и выглядело это как настоящий отчёт (та же беда, что с
        # предупреждениями импорта — находка 3 в report.md).
        truncated = limit is not None or options['source']
        name = 'gate_new_sources_partial.json' if truncated else 'gate_new_sources.json'
        report_path = os.path.join(out_dir, name)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'per_source': per_source,
                'fail_codes': fail_codes,
                'applied': do_apply,
                'truncated': truncated,
            }, f, ensure_ascii=False, indent=1)
        lines.append(f'  разбор по источникам: {report_path}')

        if not do_apply:
            lines.append('СУХОЙ ПРОГОН — в базе ничего не изменено.')
            self.stdout.write(self.style.WARNING('\n'.join(lines)))
            return

        backup_path = os.path.join(out_dir, 'gate_new_sources_backup.json')
        backup = list(
            Problem.objects.filter(id__in=to_change)
            .values('id', 'content_format')) if to_change else []
        # ⚠️ ДОПИСЫВАЕМ, а не перезаписываем. Файл — путь отката для ВСЕХ
        # задач, которым шлюз когда-либо поставил markdown. Первая версия
        # затирала его каждым --apply: второй прогон (29.08, 102 задачи)
        # оставил от снимка на 9 066 задач файл на 102, и путь отката для
        # остальных исчез бы, не лежи он в git.
        previous = {}
        if os.path.exists(backup_path):
            with open(backup_path, encoding='utf-8') as f:
                previous = {row['id']: row
                            for row in json.load(f).get('problems', [])}
        for row in backup:
            previous.setdefault(row['id'], row)
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({
                'note': 'Снимок content_format ДО шлюза новых источников — '
                        'для отката. Накапливается по всем прогонам --apply.',
                'count': len(previous),
                'problems': [previous[key] for key in sorted(previous)],
            }, f, ensure_ascii=False, indent=1)

        # Отказ шлюза — это «показывать нельзя», и сказать об этом надо
        # флагом, а не только строкой в отчёте. `hidden_pending_review`
        # для этого не годится: он значит «человек ещё не смотрел», а не
        # «плохо» — три механизма скрытия в CLAUDE.md намеренно разные.
        # Флаг ставится и тем задачам, что уже стоят на markdown и шлюз
        # больше не проходят: снимать markdown команда не вправе (решение
        # владельца), но промолчать о дефекте — тем более.
        flagged = 0
        flag_backup_path = None
        if options['flag_fails'] and fail_ids:
            newly = sorted(Problem.objects.filter(
                id__in=fail_ids, needs_quality_review=False,
            ).values_list('id', flat=True))
            flag_backup_path = os.path.join(out_dir, 'gate_fail_flags.json')
            with open(flag_backup_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'note': 'Задачи, которым ЭТОТ прогон поставил '
                            'needs_quality_review=True. Откат: снять флаг '
                            'ровно этим id — у остальных он мог стоять раньше.',
                    'count': len(newly), 'problems': newly,
                }, f, ensure_ascii=False, indent=1)

        with transaction.atomic():
            updated = Problem.objects.filter(id__in=to_change).update(
                content_format=Problem.ContentFormat.MARKDOWN)
            if options['flag_fails'] and fail_ids:
                flagged = Problem.objects.filter(
                    id__in=fail_ids, needs_quality_review=False,
                ).update(needs_quality_review=True)

        problems_after = Problem.objects.count()
        if problems_before != problems_after:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было '
                f'{problems_before}, стало {problems_after}')

        lines.append(f'ЗАПИСАНО: content_format=markdown поставлен {updated} задачам.')
        lines.append(f'  бэкап для отката: {backup_path}')
        lines.append(f'  Problem.objects.count() не изменился: {problems_before}')
        if options['flag_fails']:
            lines.append(f'  needs_quality_review поставлен {flagged} задачам '
                         f'(из {len(fail_ids)} отказавших; остальным он уже стоял)')
            if flag_backup_path:
                lines.append(f'  бэкап флагов: {flag_backup_path}')
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))
