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

# Синхронный playwright поднимает event loop, после чего Django запрещает
# ORM. Доступ к базе здесь на чтение и в один поток — ровно случай, для
# которого флаг и предназначен (см. katex_preflight docstring).
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

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
        parser.add_argument('--report-dir',
                            help='куда класть отчёт и бэкап; тесты обязаны давать '
                                 'временную папку — иначе затирают боевой')

    def handle(self, *args, **options):
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
        report_path = os.path.join(out_dir, 'gate_new_sources.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'per_source': per_source,
                'fail_codes': fail_codes,
                'applied': do_apply,
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
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({
                'note': 'Снимок content_format ДО шлюза новых источников — для отката.',
                'count': len(backup), 'problems': backup,
            }, f, ensure_ascii=False, indent=1)

        with transaction.atomic():
            updated = Problem.objects.filter(id__in=to_change).update(
                content_format=Problem.ContentFormat.MARKDOWN)

        problems_after = Problem.objects.count()
        if problems_before != problems_after:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было '
                f'{problems_before}, стало {problems_after}')

        lines.append(f'ЗАПИСАНО: content_format=markdown поставлен {updated} задачам.')
        lines.append(f'  бэкап для отката: {backup_path}')
        lines.append(f'  Problem.objects.count() не изменился: {problems_before}')
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))
