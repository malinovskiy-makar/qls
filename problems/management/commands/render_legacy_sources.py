# -*- coding: utf-8 -*-
"""«Боевой рендер» легаси-источников (Фаза 3 брифа corpus-converter-render):
поставить `content_format='markdown'` кандидатам, которых пропускает
`render_preflight_v2()`, из четырёх одобренных владельцем источников
(Archive 3, МатЭк, ЛШ Олмат 2025, Решалки Олмат) — Notion «Решения»,
карточка «Фаза 5 конвертера корпуса: одобрение по источникам после
визуального ревью».

Команда СОХРАНЯЕТ канонизированный текст (`statement`/`answer`/
`solution`/`ProblemPart.statement`) вместе с флагом `content_format`.

⚠️ Сессия 2026-08-29: до неё команда писала ТОЛЬКО флаг, а её docstring
утверждал, что текст «уже приведён к финальному виду предыдущими
сессиями». Утверждение оказалось неверным: `convert_problem_v2()` меняет
текст у 5 842 из 16 804 кандидатов (34,8 %). Шлюз при этом рендерит
канонизированный текст, а шаблон `catalog/problem_detail.html` —
СОХРАНЁННЫЙ (`problem.statement|render_markdown`). То есть проверяли
одно, а показали бы другое.

Замер боевым путём (500 случайных кандидатов, сид 20260829, тот же
KaTeX): из 465 задач, прошедших шлюз, **70 (15,1 %) сайт показал бы
сломанными** — сырые `\\begin{`/`\\end{` в видимом тексте, русский текст
в math mode, настоящие `KaTeX parse error`. В пересчёте на PASS-множество
это около 2 400 задач.

Лечится не смягчением шлюза, а тем, что в базу ложится ровно тот текст,
который шлюз проверил, — так уже устроены три новых источника
([ADR 0033](../../../docs/adr/0033-new-sources-store-converted-text.md)):
у них конвертер отработал на импорте, и расхождения нет по построению.

Вторая страховка — **идемпотентность по построению**. Сохранять можно
только текст, который является неподвижной точкой конвертера:
`convert(convert(x)) == convert(x)`. У 53 из 16 804 кандидатов (0,32 %)
это не так, и второй проход портит текст (живой минимальный случай —
вложенный `enumerate`: `1. \\begin{enumerate}...` превращается в `1. `,
содержимое теряется). Такие задачи получают код `NOT-IDEMPOTENT`,
остаются на `plain` и уходят в очередь ручного разбора.

⚠️ Сессия 2026-08-27: шлюз заменён со старого `may_render_as_markdown()`
на `render_preflight_v2()`. Старый отвечал на вопрос «разобрал ли
конвертер структуру» и пропускал как чистые 913 карточек, которые
настоящий KaTeX показывает сломанными (независимый аудит владельца).

Абсолютный инвариант (Notion «Решения», карточка «При боевом рендере
одобренных источников не трогаем задачи, подтверждённые человеком»):
НИ ОДНА задача с `human_review='approved'` не должна оказаться среди
кандидатов на запись. Проверяется явно, пересечением множеств — падает
`CommandError`, не продолжает молча.

Вторая, независимая страховка — 3 задачи Решалок Олмат с подтверждённым
разрывом `$$` между `statement`/`solution` (архитектурный дефект
импортёра, не ловится шлюзом в принципе — см.
`problems/corpus_converter/reshalki_dollar_exclusions.py`). Исключаются
принудительно, отдельным списком id, независимо от результата шлюза.

По умолчанию — сухой прогон (ничего не пишется). Запись — только с
`--apply`."""
import json
import os

# Синхронный playwright поднимает event loop, после чего Django запрещает
# ORM. Здесь доступ к базе только на чтение и в один поток — ровно случай,
# для которого этот флаг и предназначен (см. katex_preflight docstring).
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.corpus_converter.katex_preflight import KatexPreflight
from problems.corpus_converter.preflight_gate import (
    GateVerdict, build_blocks, convert_problem_v2, render_preflight_v2,
)
from problems.corpus_converter.reshalki_dollar_exclusions import (
    FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT,
)
from problems.models import Problem, ProblemFigure, ProblemPart

#: те же четыре легаси-источника и id, что у corpus_scaleup_legacy.py /
#: corpus_manual_review_queue.py — единый список, не выдумывается заново.
SOURCES = {
    'archive3': (14, 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'),
    'matek': (13, 'МатЭк — Overleaf архивы (2021–2025)'),
    'lsh2025': (3, 'ЛШ Олмат 2025 (Overleaf)'),
    'reshalki': (16, 'Решалки Олмат (olmat41)'),
}
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')


def _candidate_qs(slug, source_id):
    """Кандидаты источника: НЕ подтверждено человеком; для Решалок — ещё
    и не дубль (`status='duplicate'`, ~85,4% источника по решению Фазы 5)."""
    qs = (
        Problem.objects.filter(source_references__source_id=source_id)
        .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
        .distinct()
        .exclude(human_review=Problem.HumanReview.APPROVED)
    )
    if slug == 'reshalki':
        qs = qs.exclude(status='duplicate')
    return qs


def convert_for(problem):
    """`(подпункты, пары-для-шлюза, результат конвертера)` для одной задачи.

    Подпункты возвращаются объектами, а не метками: писать их потом надо
    по `pk` — метки в корпусе не уникальны."""
    parts = list(problem.parts.all())
    existing_parts = [(part.label, part.statement) for part in parts]
    result = convert_problem_v2(
        statement=problem.statement, answer=problem.answer,
        solution=problem.solution, existing_parts=existing_parts,
    )
    return parts, existing_parts, result


def is_stable(result):
    """Неподвижная ли точка конвертера — можно ли сохранять результат.

    Сохранённый текст следующий прогон снова прогонит через конвертер.
    Если второй проход даёт другой текст, задача будет «доедаться» с
    каждым запуском, а проверка идемпотентности никогда не даст ноль."""
    again = convert_problem_v2(
        statement=result['statement_md'], answer=result['answer_md'],
        solution=result['solution_md'],
        existing_parts=[(part['label'], part['statement_md'])
                        for part in result['parts']],
    )
    for field in ('statement_md', 'answer_md', 'solution_md'):
        if (again[field] or '') != (result[field] or ''):
            return False
    if len(again['parts']) != len(result['parts']):
        return False
    return all((a['statement_md'] or '') == (b['statement_md'] or '')
               for a, b in zip(result['parts'], again['parts']))


class Command(BaseCommand):
    help = (
        'Боевой рендер легаси-источников: канонизированный текст и '
        'content_format=markdown кандидатам, прошедшим render_preflight_v2(). '
        'Без --apply — сухой прогон.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать в базу (по умолчанию сухой прогон)')
        parser.add_argument('--report-dir',
                            help='куда класть отчёты и журнал отката '
                                 '(по умолчанию reports/corpus_converter_scaleup)')

    def handle(self, *args, **options):
        do_apply = options['apply']
        out_dir = options.get('report_dir') or OUT_DIR

        problems_before_total = Problem.objects.count()
        parts_before_total = ProblemPart.objects.count()

        per_source = {}
        all_pass_ids = set()
        all_fail_ids = set()
        #: id -> (statement_md, answer_md, solution_md, [(part_pk, текст)])
        #: только для задач, у которых текст или флаг РЕАЛЬНО отличаются.
        to_write = {}

        # Браузер поднимается ОДИН раз на весь корпус: шлюз рендерит
        # каждое поле настоящим KaTeX, и подъём на задачу стоил бы часы.
        with KatexPreflight() as checker:
            for slug, (source_id, name) in SOURCES.items():
                base_qs = (
                    Problem.objects.filter(source_references__source_id=source_id)
                    .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
                    .distinct()
                )
                total = base_qs.count()
                approved = base_qs.filter(human_review=Problem.HumanReview.APPROVED).count()
                dup_excluded = (
                    base_qs.exclude(human_review=Problem.HumanReview.APPROVED)
                    .filter(status='duplicate').count()
                    if slug == 'reshalki' else 0
                )

                candidates_qs = _candidate_qs(slug, source_id)
                forced_excluded = 0
                if slug == 'reshalki':
                    candidates_qs = candidates_qs.exclude(id__in=FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT)
                    forced_excluded = len(FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT)
                candidate_count = candidates_qs.count()

                pass_ids, fail_ids = [], []
                fail_codes = {}
                for p in candidates_qs.prefetch_related('parts').iterator(chunk_size=500):
                    parts, existing_parts, result = convert_for(p)
                    blocks = build_blocks(p.statement, existing_parts, p.answer,
                                          p.solution, result)
                    available = set(
                        ProblemFigure.objects.filter(problem=p)
                        .values_list('tikz_hash', flat=True))
                    verdict = render_preflight_v2(
                        blocks, checker, raw_statement=p.statement,
                        available_figures=available)

                    # Шлюз пропустил, но конвертер на своём же результате
                    # даёт другой текст — сохранять такое нельзя.
                    if verdict.ok and not is_stable(result):
                        verdict = GateVerdict(
                            False, ['NOT-IDEMPOTENT'],
                            ['второй проход конвертера меняет текст — '
                             'сохранённый результат «доедался» бы при '
                             'каждом следующем прогоне'])

                    if verdict.ok:
                        pass_ids.append(p.id)
                        part_writes = [(part.pk, conv['statement_md'])
                                       for part, conv in zip(parts, result['parts'])]
                        changed = (
                            p.content_format != Problem.ContentFormat.MARKDOWN
                            or (p.statement or '') != (result['statement_md'] or '')
                            or (p.answer or '') != (result['answer_md'] or '')
                            or (p.solution or '') != (result['solution_md'] or '')
                            or any((part.statement or '') != (text or '')
                                   for part, (_pk, text) in zip(parts, part_writes))
                        )
                        if changed:
                            to_write[p.id] = (
                                result['statement_md'], result['answer_md'],
                                result['solution_md'], part_writes,
                            )
                    else:
                        fail_ids.append(p.id)
                        for code in verdict.codes:
                            fail_codes[code] = fail_codes.get(code, 0) + 1

                reconciled = approved + dup_excluded + forced_excluded + candidate_count == total
                if not reconciled:
                    raise CommandError(
                        f'ИНВАРИАНТ НАРУШЕН ({name}): approved({approved}) + '
                        f'dup_excluded({dup_excluded}) + forced_excluded({forced_excluded}) + '
                        f'candidates({candidate_count}) != total({total})'
                    )

                per_source[slug] = {
                    'name': name, 'total': total, 'approved': approved,
                    'dup_excluded': dup_excluded, 'forced_excluded': forced_excluded,
                    'candidates': candidate_count,
                    'pass_ids': pass_ids, 'fail_ids': fail_ids,
                    'fail_codes': fail_codes,
                }
                all_pass_ids.update(pass_ids)
                all_fail_ids.update(fail_ids)

                self.stdout.write(
                    f'{name}: total={total} approved={approved} dup_excluded={dup_excluded} '
                    f'forced_excluded={forced_excluded} candidates={candidate_count} '
                    f'PASS={len(pass_ids)} FAIL={len(fail_ids)}'
                )

        # --- Инвариант 1: НИ ОДНА approved-задача не в PASS (все 4 источника) ---
        all_source_ids = [sid for sid, _ in SOURCES.values()]
        approved_ids = set(
            Problem.objects.filter(
                source_references__source_id__in=all_source_ids,
                human_review=Problem.HumanReview.APPROVED,
            ).values_list('id', flat=True)
        )
        overlap_approved = approved_ids & all_pass_ids
        if overlap_approved:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: {len(overlap_approved)} approved-задач попали в '
                f'PASS-кандидаты: {sorted(overlap_approved)[:30]}'
            )

        # --- Инвариант 2: принудительно исключённые Решалки не в PASS ---
        overlap_forced = FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT & all_pass_ids
        if overlap_forced:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: forced-excluded Решалки (разрыв $$) попали в '
                f'PASS-кандидаты: {sorted(overlap_forced)}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Инварианты сошлись: 0 approved-задач в PASS ({len(approved_ids)} approved всего '
            f'по 4 источникам), 0 forced-excluded Решалки в PASS.'
        ))

        # --- Уже markdown среди PASS (идемпотентность: сколько РЕАЛЬНО изменится) ---
        already_markdown_ids = set(
            Problem.objects.filter(
                id__in=all_pass_ids, content_format=Problem.ContentFormat.MARKDOWN,
            ).values_list('id', flat=True)
        )
        # «Изменится» теперь считается по ТЕКСТУ И флагу вместе: задача
        # может уже стоять на markdown, но хранить неканонизированный
        # текст — до этой сессии именно так и было.
        to_change_ids = sorted(to_write)

        self.stdout.write(
            f'\nPASS всего (все 4 источника): {len(all_pass_ids)}. '
            f'Уже content_format=markdown: {len(already_markdown_ids)}. '
            f'Будет изменено: {len(to_change_ids)}.'
        )

        # Отдельно и заметно: задачи, которые УЖЕ показываются как markdown,
        # но новый шлюз считает их сломанными. Команда их не трогает — она
        # только СТАВИТ markdown прошедшим шлюз и никогда не снимает его.
        # Снятие — отдельное решение владельца, поэтому здесь только сигнал,
        # а не тихая правка.
        already_md_failing = sorted(
            Problem.objects.filter(
                id__in=list(all_fail_ids),
                content_format=Problem.ContentFormat.MARKDOWN,
            ).values_list('id', flat=True)
        )
        if already_md_failing:
            self.stdout.write(self.style.WARNING(
                f'ВНИМАНИЕ: {len(already_md_failing)} задач УЖЕ стоят на '
                f'content_format=markdown, но НЕ проходят новый шлюз — они '
                f'показываются сломанными прямо сейчас. Команда их не трогает '
                f'(она только ставит markdown, не снимает). Решение о снятии — '
                f'за владельцем. id: {already_md_failing}'
            ))

        os.makedirs(out_dir, exist_ok=True)

        if not do_apply:
            self.stdout.write(self.style.WARNING(
                f'Сухой прогон завершён. Изменений в базе НЕТ. '
                f'Для записи повторить с --apply после визуальной проверки '
                f'boevoi_render_review.html.'
            ))
            return

        # --- Журнал отката: и флаг, и ТЕКСТ, и подпункты -------------------
        backup_path = os.path.join(out_dir, 'render_legacy_sources_backup.json')
        backup = [{
            'problem_id': p.id,
            'content_format': p.content_format,
            'statement': p.statement,
            'answer': p.answer,
            'solution': p.solution,
            'parts': [{'id': part.id, 'label': part.label,
                       'statement': part.statement} for part in p.parts.all()],
        } for p in (Problem.objects.filter(id__in=to_change_ids)
                    .prefetch_related('parts').order_by('id'))]
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({
                'note': 'Снимок текста и content_format ДО боевого рендера — '
                        'для отката.',
                'count': len(backup),
                'problems': backup,
            }, f, ensure_ascii=False, indent=1)

        # --- Запись ---
        updated = 0
        parts_updated = 0
        with transaction.atomic():
            for pid in to_change_ids:
                statement_md, answer_md, solution_md, part_writes = to_write[pid]
                updated += Problem.objects.filter(id=pid).update(
                    statement=statement_md,
                    answer=answer_md,
                    solution=solution_md,
                    content_format=Problem.ContentFormat.MARKDOWN,
                )
                for part_pk, text in part_writes:
                    parts_updated += ProblemPart.objects.filter(
                        pk=part_pk).update(statement=text)

        problems_after_total = Problem.objects.count()
        if problems_before_total != problems_after_total:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было '
                f'{problems_before_total}, стало {problems_after_total}'
            )
        parts_after_total = ProblemPart.objects.count()
        if parts_before_total != parts_after_total:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: ProblemPart.objects.count() было '
                f'{parts_before_total}, стало {parts_after_total}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'ЗАПИСАНО. Задач: {updated} (канонизированный текст + '
            f'content_format=markdown). Подпунктов: {parts_updated}. '
            f'Бэкап: {backup_path}. Инварианты сошлись: '
            f'Problem={problems_before_total}, ProblemPart={parts_before_total}.'
        ))
