# -*- coding: utf-8 -*-
"""Диагностическая выборка задач для ручного визуального ревью.

Команда ТОЛЬКО ЧИТАЕТ базу — никаких save/update/delete. Детекторы и
HTML-рендер вынесены в общий модуль problems/diagnostics.py.

Режим по умолчанию (без флагов) — воспроизводимая (seed=2026) выборка задач
из видимого в каталоге пула:
  reports/diagnostic_sample/sample_ids.txt    — список id (по одному в строке)
  reports/diagnostic_sample/sample_review.html — самодостаточный HTML-отчёт

Режим --by-flag — визуальный обзор по категориям дефектов и по источникам
с рискованными переносами. Требует, чтобы ПЕРЕД этим отработала команда
full_defect_scan (читает её файлы reports/diagnostic_sample/ids_<флаг>.txt
и reports/diagnostic_sample/source_linebreak_stats.csv):
  reports/diagnostic_sample/by_flag_review.html — 10 случайных задач на
  каждый флаг + по 5 задач на каждый источник группы «жёсткая нарезка» и
  «смешанно» (классификация из full_defect_scan).
"""
import csv
import os
import random

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.html import escape
from django.utils import timezone

from problems.diagnostics import (
    FLAG_DEFS, SEED, build_scan_text, render_card, render_group_header,
    render_page, scan_flags,
)
from problems.models import Problem, SourceReference

REPORT_DIR = 'reports/diagnostic_sample'
IDS_FILE = os.path.join(REPORT_DIR, 'sample_ids.txt')
HTML_FILE = os.path.join(REPORT_DIR, 'sample_review.html')
BY_FLAG_HTML_FILE = os.path.join(REPORT_DIR, 'by_flag_review.html')
LINEBREAK_CSV = os.path.join(REPORT_DIR, 'source_linebreak_stats.csv')

RANDOM_SAMPLE_SIZE = 40
MIN_SOURCE_POOL = 50
BY_FLAG_PER_FLAG = 10
BY_FLAG_PER_SOURCE = 5

GROUP_LABELS = {
    'hard_wrap': 'жёсткая нарезка',
    'mixed': 'смешанно',
    'structural': 'структурные',
}


# ── Режим по умолчанию: плоская случайная выборка ───────────────────────

def build_sample_ids(stdout):
    pool_qs = Problem.objects.filter(
        status=Problem.Status.PUBLISHED,
        needs_quality_review=False,
    )
    pool_ids = sorted(pool_qs.values_list('id', flat=True))
    if not pool_ids:
        return [], {}

    rng = random.Random(SEED)
    random_ids = sorted(rng.sample(pool_ids, min(RANDOM_SAMPLE_SIZE, len(pool_ids))))
    picked = set(random_ids)

    # Источники с >= MIN_SOURCE_POOL задачами в пуле — по одной случайной задаче.
    source_problem_map = {}
    refs = (
        SourceReference.objects
        .filter(problem_id__in=pool_ids)
        .order_by('source_id', 'problem_id')
        .values_list('source_id', 'problem_id')
    )
    for source_id, problem_id in refs:
        source_problem_map.setdefault(source_id, set()).add(problem_id)

    source_extra = {}  # problem_id -> source_id (для отчёта, откуда взят "довесок")
    for source_id in sorted(source_problem_map.keys()):
        problem_ids = source_problem_map[source_id]
        if len(problem_ids) < MIN_SOURCE_POOL:
            continue
        candidates = sorted(pid for pid in problem_ids if pid not in picked)
        if not candidates:
            continue
        chosen = rng.choice(candidates)
        picked.add(chosen)
        source_extra[chosen] = source_id

    sample_ids = sorted(picked)
    return sample_ids, source_extra


def _problem_source_label(problem, source_extra=None):
    refs = list(problem.source_references.all())
    if refs:
        label = ', '.join(sorted({r.source.name for r in refs}))
    else:
        label = '—'
    if source_extra is not None and problem.id in source_extra:
        label += ' [довесок источника]'
    return label


def _cards_for_ids(ids):
    """Строит HTML-карточки для списка id, сохраняя порядок ids."""
    problems = (
        Problem.objects
        .filter(id__in=ids)
        .prefetch_related('parts', 'source_references__source')
    )
    by_id = {p.id: p for p in problems}
    cards = []
    for pid in ids:
        problem = by_id.get(pid)
        if problem is None:
            continue
        parts = list(problem.parts.all())
        flags = scan_flags(build_scan_text(problem, parts))
        source_label = _problem_source_label(problem)
        cards.append(render_card(problem, parts, flags, source_label))
    return cards


class Command(BaseCommand):
    help = ('Диагностическая выборка задач для ручного визуального ревью '
            '(только чтение — ничего не пишет и не меняет в базе).')

    def add_arguments(self, parser):
        parser.add_argument(
            '--by-flag', action='store_true',
            help='Обзор по 10 задач на каждый флаг + по 5 на источник с рискованными '
                 'переносами (требует предварительного запуска full_defect_scan).',
        )

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        if options['by_flag']:
            self._handle_by_flag()
        else:
            self._handle_default()

    # ── Режим по умолчанию ──

    def _handle_default(self):
        from collections import Counter

        sample_ids, source_extra = build_sample_ids(self.stdout)
        if not sample_ids:
            self.stderr.write(self.style.ERROR(
                'Пул пуст: нет задач status=published, needs_quality_review=False.'
            ))
            return

        with open(IDS_FILE, 'w', encoding='utf-8') as f:
            for pid in sample_ids:
                f.write('{0}\n'.format(pid))

        problems = (
            Problem.objects
            .filter(id__in=sample_ids)
            .prefetch_related('parts', 'source_references__source')
        )
        problems_by_id = {p.id: p for p in problems}

        flags_counter = Counter()
        cards_html_parts = []
        source_name_counter = Counter()

        for pid in sample_ids:
            problem = problems_by_id.get(pid)
            if problem is None:
                continue  # задача исчезла между сборкой id и запросом — пропускаем
            parts = list(problem.parts.all())
            scan_text = build_scan_text(problem, parts)
            flags = scan_flags(scan_text)
            for key, is_set in flags.items():
                if is_set:
                    flags_counter[key] += 1

            refs = list(problem.source_references.all())
            if refs:
                for r in refs:
                    source_name_counter[r.source.name] += 1
            else:
                source_name_counter['(без источника)'] += 1

            source_label = _problem_source_label(problem, source_extra)
            cards_html_parts.append(render_card(problem, parts, flags, source_label))

        summary_rows = ''.join(
            '<tr><td>{0}</td><td>{1} / {2}</td></tr>'.format(
                escape(label), flags_counter.get(key, 0), len(sample_ids),
            )
            for key, label in FLAG_DEFS
        )

        page_html = render_page(
            page_title='Диагностика отображения задач — выборка {0}'.format(len(sample_ids)),
            meta_line='Сгенерировано: {0}. seed={1}. Список id: reports/diagnostic_sample/sample_ids.txt'.format(
                timezone.now().strftime('%Y-%m-%d %H:%M'), SEED,
            ),
            summary_rows_html=summary_rows,
            cards_html=''.join(cards_html_parts),
        )

        with open(HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(page_html)

        self.stdout.write(self.style.SUCCESS(
            'Выборка: {0} задач (случайных: {1}, довесков по источникам: {2}).'.format(
                len(sample_ids), RANDOM_SAMPLE_SIZE, len(source_extra),
            )
        ))
        self.stdout.write('Распределение по источникам в выборке:')
        for name, cnt in source_name_counter.most_common():
            self.stdout.write('  {0}: {1}'.format(name, cnt))
        self.stdout.write('Сводка машинного пре-скана:')
        for key, label in FLAG_DEFS:
            self.stdout.write('  {0}: {1} / {2}'.format(label, flags_counter.get(key, 0), len(sample_ids)))
        self.stdout.write('Файлы:')
        self.stdout.write('  {0}'.format(IDS_FILE))
        self.stdout.write('  {0}'.format(HTML_FILE))

    # ── Режим --by-flag ──

    def _handle_by_flag(self):
        cards_html_parts = []
        summary_rows = []
        total_cards = 0

        # 1. По каждому флагу — 10 случайных id из ids_<флаг>.txt (full_defect_scan).
        for key, label in FLAG_DEFS:
            ids_path = os.path.join(REPORT_DIR, 'ids_{0}.txt'.format(key))
            if not os.path.exists(ids_path):
                self.stderr.write(self.style.ERROR(
                    'Нет файла {0} — сначала запусти full_defect_scan.'.format(ids_path)
                ))
                return
            with open(ids_path, encoding='utf-8') as f:
                flag_ids = [int(line.strip()) for line in f if line.strip()]

            rng = random.Random(SEED)
            sample = sorted(rng.sample(flag_ids, min(BY_FLAG_PER_FLAG, len(flag_ids))))
            summary_rows.append((label, len(sample), len(flag_ids)))

            cards_html_parts.append(render_group_header(
                'Флаг: {0}'.format(label),
                '{0} случайных задач из {1}, отмеченных этим флагом по всему пулу.'.format(
                    len(sample), len(flag_ids),
                ),
            ))
            cards_html_parts.extend(_cards_for_ids(sample))
            total_cards += len(sample)

        # 2. По источникам групп «жёсткая нарезка» и «смешанно» (из full_defect_scan).
        if not os.path.exists(LINEBREAK_CSV):
            self.stderr.write(self.style.ERROR(
                'Нет файла {0} — сначала запусти full_defect_scan.'.format(LINEBREAK_CSV)
            ))
            return

        with open(LINEBREAK_CSV, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            source_rows = list(reader)

        risky_sources = [r for r in source_rows if r['group'] in ('hard_wrap', 'mixed')]
        risky_sources.sort(key=lambda r: (r['group'], -int(r['pool_count'])))

        for row in risky_sources:
            source_id = int(row['source_id'])
            pool_ids = list(
                Problem.objects
                .filter(
                    status=Problem.Status.PUBLISHED, needs_quality_review=False,
                    source_references__source_id=source_id,
                )
                .values_list('id', flat=True)
                .distinct()
                .order_by('id')
            )
            if not pool_ids:
                continue
            rng = random.Random(SEED)
            sample = sorted(rng.sample(pool_ids, min(BY_FLAG_PER_SOURCE, len(pool_ids))))

            group_label = GROUP_LABELS.get(row['group'], row['group'])
            desc = (
                '{0} случайных задач из {1} в пуле. Группа: {2}. '
                'Медианная длина строки: {3}. Доля «плохих» окончаний строк: {4}%. '
                'Доля задач с \\n: {5}%.'
            ).format(
                len(sample), len(pool_ids), group_label,
                row['median_line_len'], row['bad_ending_pct'], row['newline_doc_pct'],
            )
            cards_html_parts.append(render_group_header(
                'Источник: {0} ({1})'.format(row['name'], group_label), desc,
            ))
            cards_html_parts.extend(_cards_for_ids(sample))
            total_cards += len(sample)
            summary_rows.append(('Источник: {0} ({1})'.format(row['name'], group_label), len(sample), len(pool_ids)))

        summary_html = ''.join(
            '<tr><td>{0}</td><td>{1} / {2}</td></tr>'.format(escape(label), shown, total)
            for label, shown, total in summary_rows
        )

        page_html = render_page(
            page_title='Диагностика по флагам и источникам — {0} карточек'.format(total_cards),
            meta_line=(
                'Сгенерировано: {0}. seed={1}. По {2} случайных задач на флаг + по {3} на '
                'источник из групп «жёсткая нарезка»/«смешанно» (source_linebreak_stats.csv).'
            ).format(timezone.now().strftime('%Y-%m-%d %H:%M'), SEED, BY_FLAG_PER_FLAG, BY_FLAG_PER_SOURCE),
            summary_rows_html=summary_html,
            cards_html=''.join(cards_html_parts),
        )

        with open(BY_FLAG_HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(page_html)

        self.stdout.write(self.style.SUCCESS(
            'Обзор по флагам/источникам: {0} карточек.'.format(total_cards)
        ))
        for label, shown, total in summary_rows:
            self.stdout.write('  {0}: показано {1} из {2}'.format(label, shown, total))
        self.stdout.write('Файл: {0}'.format(BY_FLAG_HTML_FILE))
