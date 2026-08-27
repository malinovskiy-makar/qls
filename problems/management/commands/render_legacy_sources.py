# -*- coding: utf-8 -*-
"""«Боевой рендер» легаси-источников (Фаза 3 брифа corpus-converter-render):
поставить `content_format='markdown'` кандидатам, которых пропускает
`render_preflight_v2()`, из четырёх одобренных владельцем источников
(Archive 3, МатЭк, ЛШ Олмат 2025, Решалки Олмат) — Notion «Решения»,
карточка «Фаза 5 конвертера корпуса: одобрение по источникам после
визуального ревью».

Эта команда НЕ трогает `statement`/`answer`/`solution`/`ProblemPart` —
только флаг `content_format`. Текст уже приведён к своему финальному виду
предыдущими сессиями (МатЭк фикс-пак, автопочинка `\\begin{cases}`);
здесь конвейер запускается ВТОРОЙ раз только чтобы СПРОСИТЬ у шлюза
`render_preflight_v2()`, не чтобы получить новый текст.

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
    build_blocks, convert_problem_v2, render_preflight_v2,
)
from problems.corpus_converter.reshalki_dollar_exclusions import (
    FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT,
)
from problems.models import Problem

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


class Command(BaseCommand):
    help = (
        'Боевой рендер легаси-источников: content_format=markdown кандидатам, '
        'прошедшим render_preflight_v2(). Без --apply — сухой прогон.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать в базу (по умолчанию сухой прогон)')

    def handle(self, *args, **options):
        do_apply = options['apply']

        problems_before_total = Problem.objects.count()

        per_source = {}
        all_pass_ids = set()
        all_fail_ids = set()

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
                    existing_parts = [(part.label, part.statement) for part in p.parts.all()]
                    result = convert_problem_v2(
                        statement=p.statement, answer=p.answer, solution=p.solution,
                        existing_parts=existing_parts,
                    )
                    blocks = build_blocks(p.statement, existing_parts, p.answer,
                                          p.solution, result)
                    verdict = render_preflight_v2(blocks, checker,
                                                  raw_statement=p.statement)
                    if verdict.ok:
                        pass_ids.append(p.id)
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
        to_change_ids = sorted(all_pass_ids - already_markdown_ids)

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

        os.makedirs(OUT_DIR, exist_ok=True)

        if not do_apply:
            self.stdout.write(self.style.WARNING(
                f'Сухой прогон завершён. Изменений в базе НЕТ. '
                f'Для записи повторить с --apply после визуальной проверки '
                f'boevoi_render_review.html.'
            ))
            return

        # --- Запись ---
        backup_path = os.path.join(OUT_DIR, 'render_legacy_sources_backup.json')
        backup = list(
            Problem.objects.filter(id__in=to_change_ids)
            .values('id', 'content_format')
        )
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump({
                'note': 'Снимок content_format ДО боевого рендера — для отката.',
                'count': len(backup),
                'problems': backup,
            }, f, ensure_ascii=False, indent=1)

        with transaction.atomic():
            updated = Problem.objects.filter(id__in=to_change_ids).update(
                content_format=Problem.ContentFormat.MARKDOWN,
            )

        problems_after_total = Problem.objects.count()
        if problems_before_total != problems_after_total:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было '
                f'{problems_before_total}, стало {problems_after_total}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'ЗАПИСАНО. content_format=markdown поставлен {updated} задачам. '
            f'Бэкап: {backup_path}. Инвариант count() сошёлся ({problems_before_total}).'
        ))
