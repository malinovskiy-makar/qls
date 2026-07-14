# -*- coding: utf-8 -*-
"""Полный скан детекторов дефектов отображения по всему видимому пулу задач.

Команда ТОЛЬКО ЧИТАЕТ базу. Прогоняет весь пул (status=published,
needs_quality_review=False, ~18 600 задач) через детекторы из
problems/diagnostics.py и считает:

  1. точные счётчики по каждому флагу — всего и в разрезе источников;
  2. статистику переносов строк по источникам (медианная длина строки, доля
     «плохих» окончаний строк, доля задач с \\n) — чтобы отличить источники
     со структурными переносами (абзацы/списки, pre-line безопасен) от
     источников с жёсткой PDF-нарезкой строк (pre-line там развалит текст).

Результаты:
  reports/diagnostic_sample/full_scan_counts.md        — счётчики по флагам
  reports/diagnostic_sample/ids_<флаг>.txt              — id по каждому флагу
  reports/diagnostic_sample/source_linebreak_stats.md   — таблица для человека
  reports/diagnostic_sample/source_linebreak_stats.csv  — то же машиночитаемо
                                                            (нужен diagnostic_sample --by-flag)

Скан идёт через iterator(chunk_size=...) с prefetch_related('parts', ...) —
весь пул в память не грузится.
"""
import csv
import os
import statistics
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.utils import timezone

from problems.diagnostics import FLAG_DEFS, build_scan_text, collect_line_stats, scan_flags
from problems.models import Problem

REPORT_DIR = 'reports/diagnostic_sample'
COUNTS_MD = os.path.join(REPORT_DIR, 'full_scan_counts.md')
LINEBREAK_MD = os.path.join(REPORT_DIR, 'source_linebreak_stats.md')
LINEBREAK_CSV = os.path.join(REPORT_DIR, 'source_linebreak_stats.csv')

CHUNK_SIZE = 2000

# Пороги классификации источников по риску «жёсткой PDF-нарезки» строк.
# Подобраны по фактическому распределению метрик на этой базе (первый прогон
# без порогов показал чёткий разрыв в данных, см. обоснование в
# reports/diagnostic_sample/full_scan_summary.md, раздел «Классификация
# источников»): 16 из 20 источников с достаточной статистикой имеют медиану
# строки 17–105 символов и долю «плохих» окончаний 42–82% — явная жёсткая
# нарезка. Единственный явный контрпример — ILE (медиана 550, доля «плохих»
# окончаний 16.9%) отделён от остальных разрывом почти в 2.5 раза по доле
# «плохих» окончаний (16.9% против ближайших 42.2%) — естественная граница
# для STRUCTURAL_BAD_RATIO.
HARD_WRAP_MEDIAN_LEN = 100
HARD_WRAP_BAD_RATIO = 0.35
STRUCTURAL_BAD_RATIO = 0.20
MIN_PROBLEMS_FOR_STATS = 10


def classify_source(median_len, bad_ratio, pool_count):
    if pool_count < MIN_PROBLEMS_FOR_STATS:
        return 'insufficient'
    if median_len is None:
        return 'insufficient'
    if median_len < HARD_WRAP_MEDIAN_LEN and bad_ratio > HARD_WRAP_BAD_RATIO:
        return 'hard_wrap'
    if bad_ratio <= STRUCTURAL_BAD_RATIO:
        return 'structural'
    return 'mixed'


class Command(BaseCommand):
    help = ('Полный скан детекторов дефектов отображения по всему видимому пулу '
            '(только чтение — ничего не пишет и не меняет в базе).')

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        pool_qs = Problem.objects.filter(
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
        )
        total_pool = pool_qs.count()
        if not total_pool:
            self.stderr.write(self.style.ERROR('Пул пуст.'))
            return

        overall_counts = Counter()
        ids_by_flag = defaultdict(list)

        # source_id -> накопительная статистика (имя, счётчики флагов, строки)
        source_stats = {}
        no_source_count = 0

        qs = (
            pool_qs
            .prefetch_related('parts', 'source_references__source')
            .order_by('id')
            .iterator(chunk_size=CHUNK_SIZE)
        )

        processed = 0
        for problem in qs:
            parts = list(problem.parts.all())
            scan_text = build_scan_text(problem, parts)
            flags = scan_flags(scan_text)

            for key, is_set in flags.items():
                if is_set:
                    overall_counts[key] += 1
                    ids_by_flag[key].append(problem.id)

            refs = list(problem.source_references.all())
            sources_seen = {}
            for r in refs:
                sources_seen[r.source_id] = r.source.name
            if not sources_seen:
                no_source_count += 1

            for source_id, name in sources_seen.items():
                st = source_stats.get(source_id)
                if st is None:
                    st = {
                        'name': name,
                        'pool_count': 0,
                        'flag_counts': Counter(),
                        'line_lengths': [],
                        'non_list_lines': 0,
                        'bad_ending_lines': 0,
                        'newline_docs': 0,
                    }
                    source_stats[source_id] = st
                st['pool_count'] += 1
                for key, is_set in flags.items():
                    if is_set:
                        st['flag_counts'][key] += 1
                if flags['newline']:
                    st['newline_docs'] += 1
                collect_line_stats(problem.statement or '', st)

            processed += 1
            if processed % 4000 == 0:
                self.stdout.write('  ...обработано {0} / {1}'.format(processed, total_pool))

        self._write_ids_files(ids_by_flag)
        self._write_counts_md(total_pool, overall_counts, source_stats, no_source_count)
        classification = self._write_linebreak_reports(source_stats)

        self.stdout.write(self.style.SUCCESS('Обработано задач: {0}'.format(processed)))
        self.stdout.write('Сводка по флагам (всего в пуле {0}):'.format(total_pool))
        for key, label in FLAG_DEFS:
            cnt = overall_counts.get(key, 0)
            self.stdout.write('  {0}: {1} ({2:.1f}%)'.format(label, cnt, 100.0 * cnt / total_pool))
        self.stdout.write('Классификация источников по переносам:')
        group_counts = Counter(classification.values())
        for group in ('hard_wrap', 'mixed', 'structural', 'insufficient'):
            self.stdout.write('  {0}: {1} источников'.format(group, group_counts.get(group, 0)))
        self.stdout.write('Файлы:')
        self.stdout.write('  {0}'.format(COUNTS_MD))
        self.stdout.write('  {0}'.format(LINEBREAK_MD))
        self.stdout.write('  {0}'.format(LINEBREAK_CSV))
        for key, _ in FLAG_DEFS:
            self.stdout.write('  {0}'.format(os.path.join(REPORT_DIR, 'ids_{0}.txt'.format(key))))

    # ── Запись файлов ──

    def _write_ids_files(self, ids_by_flag):
        for key, _ in FLAG_DEFS:
            path = os.path.join(REPORT_DIR, 'ids_{0}.txt'.format(key))
            with open(path, 'w', encoding='utf-8') as f:
                for pid in ids_by_flag.get(key, []):
                    f.write('{0}\n'.format(pid))

    def _write_counts_md(self, total_pool, overall_counts, source_stats, no_source_count):
        lines = []
        lines.append('# Полный скан дефектов отображения — счётчики\n')
        lines.append('Сгенерировано: {0}. Пул: status=published, needs_quality_review=False. '
                      'Всего задач в пуле: **{1}**.\n'.format(
                          timezone.now().strftime('%Y-%m-%d %H:%M'), total_pool,
                      ))

        lines.append('## Всего по базе\n')
        lines.append('| Флаг | Задач | % от пула |')
        lines.append('|---|---:|---:|')
        for key, label in FLAG_DEFS:
            cnt = overall_counts.get(key, 0)
            lines.append('| {0} | {1} | {2:.1f}% |'.format(label, cnt, 100.0 * cnt / total_pool))
        lines.append('')

        lines.append('## В разрезе источников\n')
        flag_keys = [key for key, _ in FLAG_DEFS]
        header = ['Источник', 'В пуле'] + [label for _, label in FLAG_DEFS]
        lines.append('| ' + ' | '.join(header) + ' |')
        lines.append('|' + '---|' * len(header))
        for source_id, st in sorted(source_stats.items(), key=lambda kv: -kv[1]['pool_count']):
            row = [st['name'], str(st['pool_count'])]
            for key in flag_keys:
                cnt = st['flag_counts'].get(key, 0)
                pct = 100.0 * cnt / st['pool_count'] if st['pool_count'] else 0.0
                row.append('{0} ({1:.0f}%)'.format(cnt, pct))
            lines.append('| ' + ' | '.join(row) + ' |')
        if no_source_count:
            lines.append('\n(без привязки к источнику: {0} задач, в общую таблицу не включены)\n'.format(
                no_source_count,
            ))

        with open(COUNTS_MD, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

    def _write_linebreak_reports(self, source_stats):
        classification = {}
        rows = []
        for source_id, st in source_stats.items():
            line_lengths = st['line_lengths']
            median_len = statistics.median(line_lengths) if line_lengths else None
            non_list = st['non_list_lines']
            bad_ratio = (st['bad_ending_lines'] / non_list) if non_list else 0.0
            newline_ratio = st['newline_docs'] / st['pool_count'] if st['pool_count'] else 0.0
            group = classify_source(median_len, bad_ratio, st['pool_count'])
            classification[source_id] = group
            rows.append({
                'source_id': source_id,
                'name': st['name'],
                'pool_count': st['pool_count'],
                'median_line_len': '{0:.0f}'.format(median_len) if median_len is not None else '',
                'bad_ending_pct': '{0:.1f}'.format(100.0 * bad_ratio),
                'newline_doc_pct': '{0:.1f}'.format(100.0 * newline_ratio),
                'group': group,
            })

        rows.sort(key=lambda r: -r['pool_count'])

        with open(LINEBREAK_CSV, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'source_id', 'name', 'pool_count', 'median_line_len',
                'bad_ending_pct', 'newline_doc_pct', 'group',
            ])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        group_titles = {
            'hard_wrap': 'жёсткая нарезка',
            'mixed': 'смешанно/непонятно',
            'structural': 'структурные',
            'insufficient': 'недостаточно данных',
        }
        md_lines = []
        md_lines.append('# Классификация источников по типу переносов строк\n')
        md_lines.append(
            'Пороги: median_line_len < {0} и bad_ending_pct > {1:.0f}% → «жёсткая нарезка»; '
            'bad_ending_pct <= {2:.0f}% → «структурные»; иначе «смешанно». '
            'Меньше {3} задач в пуле у источника — «недостаточно данных».\n'.format(
                HARD_WRAP_MEDIAN_LEN, 100 * HARD_WRAP_BAD_RATIO,
                100 * STRUCTURAL_BAD_RATIO, MIN_PROBLEMS_FOR_STATS,
            )
        )
        md_lines.append(
            '| Источник | В пуле | Медиана длины строки | Доля «плохих» окончаний | Доля задач с \\n | Группа |'
        )
        md_lines.append('|---|---:|---:|---:|---:|---|')
        for row in rows:
            md_lines.append('| {0} | {1} | {2} | {3}% | {4}% | {5} |'.format(
                row['name'], row['pool_count'], row['median_line_len'] or '—',
                row['bad_ending_pct'], row['newline_doc_pct'], group_titles[row['group']],
            ))

        with open(LINEBREAK_MD, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines) + '\n')

        return classification
