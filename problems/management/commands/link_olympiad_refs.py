"""
Команда link_olympiad_refs — привязывает задачи банка к реальным олимпиадам
через точное совпадение SourceReference.url с external_export
(SolveHub/ILE, обход официальных публичных индексов, 01.09.2026).

Основание: у SolveHub (6119 SourceReference) и ILE (3978 SourceReference)
url заполнен на 100% — совпадение строки ссылки достаточно, каскад
SHA-1/fuzzy/эмбеддингов не нужен. Экспорт даёт для каждого найденного там
вхождения (data/all_problem_occurrences.jsonl) ту же самую ссылку.

Каждое совпадение — одна строка OlympiadRef (get_or_create по
(problem, event_id) в --apply). Ничего в Problem/SourceReference не меняется.

Запуск:
    manage.py link_olympiad_refs --export-path <путь к all_problem_occurrences.jsonl>
    manage.py link_olympiad_refs --export-path <путь> --apply
"""

import json
import os
import random

from django.core.management.base import BaseCommand, CommandError

from problems.models import OlympiadRef, Problem, SourceReference

# Профили, которые владелец просил показать отдельно ДО записи в базу —
# это профиль «предпринимательство», а не «экономика».
FLAGGED_SLUGS = {'mosh-entrepreneurship', 'vseros-entrepreneurship', 'apo', 'posh'}

# Ожидаемые числа из data/coverage.json (аудит внешнего экспорта, 01.09.2026).
EXPECTED_SOLVEHUB_MATCHES = 1437
EXPECTED_ILE_MATCHES = 1011
EXPECTED_TOTAL_UNIQUE = 2448
DRIFT_WARN_PCT = 10

EXPLICIT_FIELDS = {
    'academic_year', 'year', 'stage', 'grade', 'variant', 'number',
    'event_id', 'record_id', 'source_site', 'source_url', 'olympiad_slug',
}

NEAR_MISS_REPORT_PATH = 'reports/olympiad_link/near_miss_urls.jsonl'


def load_olympiad_names(export_path):
    """slug -> name_ru из соседнего official_source_registry.jsonl.
    Файла может не быть — тогда olympiad_name остаётся пустым, не фатально."""
    registry_path = os.path.join(
        os.path.dirname(export_path), 'official_source_registry.jsonl')
    names = {}
    if not os.path.exists(registry_path):
        return names
    with open(registry_path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            names[row['slug']] = row.get('name_ru', '')
    return names


def load_url_index():
    """url -> [problem_id, ...] по ВСЕМ SourceReference с непустым url."""
    index = {}
    qs = (SourceReference.objects
          .exclude(url='')
          .values_list('url', 'problem_id'))
    for url, pid in qs.iterator(chunk_size=5000):
        index.setdefault(url, []).append(pid)
    return index


class Command(BaseCommand):
    help = ('Привязывает задачи банка к олимпиадам точным совпадением '
            'SourceReference.url с внешним экспортом SolveHub/ILE.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--export-path', required=True,
            help='Путь к data/all_problem_occurrences.jsonl из внешнего экспорта.')
        parser.add_argument(
            '--apply', action='store_true',
            help='Боевой прогон — без флага только считает и печатает отчёт.')
        parser.add_argument(
            '--sample-size', type=int, default=10,
            help='Сколько случайных совпадений показать в отчёте (по умолчанию 10).')
        parser.add_argument(
            '--seed', type=int, default=42,
            help='Seed для случайной выборки в отчёте (воспроизводимость).')

    def handle(self, *args, **options):
        export_path = options['export_path']
        apply_mode = options['apply']

        if not os.path.exists(export_path):
            raise CommandError(f'Файл не найден: {export_path}')

        olympiad_names = load_olympiad_names(export_path)
        url_index = load_url_index()

        rows = []
        with open(export_path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))

        total = len(rows)
        by_site_total = {}
        by_site_matched = {}
        by_site_unmatched = {}
        by_slug = {}  # slug -> {'matched': int, 'unmatched': int, 'problem_ids': set}
        matched_rows = []       # (row, problem_id) — для сэмпла и записи
        unmatched_rows = []
        near_misses = []
        matched_problem_ids = set()
        flagged_matches = []    # matched строки по FLAGGED_SLUGS

        rstrip_index = None  # строим лениво, только если понадобится

        for row in rows:
            site = row.get('source_site', '?')
            slug = row.get('olympiad_slug', '?')
            url = row.get('source_url', '')

            by_site_total[site] = by_site_total.get(site, 0) + 1
            slug_stat = by_slug.setdefault(
                slug, {'matched': 0, 'unmatched': 0, 'problem_ids': set()})

            pids = url_index.get(url)
            if pids:
                by_site_matched[site] = by_site_matched.get(site, 0) + 1
                slug_stat['matched'] += 1
                for pid in pids:
                    matched_rows.append((row, pid))
                    matched_problem_ids.add(pid)
                    slug_stat['problem_ids'].add(pid)
                    if slug in FLAGGED_SLUGS:
                        flagged_matches.append((row, pid))
            else:
                by_site_unmatched[site] = by_site_unmatched.get(site, 0) + 1
                slug_stat['unmatched'] += 1
                unmatched_rows.append(row)

                if rstrip_index is None:
                    rstrip_index = {}
                    for u in url_index:
                        rstrip_index.setdefault(u.rstrip('/'), []).append(u)
                stripped = url.rstrip('/')
                if stripped in rstrip_index and stripped != url:
                    near_misses.append({
                        'event_id': row.get('event_id'),
                        'record_id': row.get('record_id'),
                        'export_url': url,
                        'matched_db_url_candidates': rstrip_index[stripped],
                    })

        # ── Отчёт: общие числа ────────────────────────────────────────────
        self.stdout.write(f'Строк в экспорте: {total}')
        for site in sorted(by_site_total):
            self.stdout.write(
                f'  {site}: {by_site_total[site]} '
                f'(совпало: {by_site_matched.get(site, 0)}, '
                f'не совпало: {by_site_unmatched.get(site, 0)})')

        self.stdout.write('')
        self.stdout.write(f'Всего точных совпадений по url: {len(matched_rows)}')
        self.stdout.write(f'Уникальных Problem.id с хотя бы одной привязкой: '
                          f'{len(matched_problem_ids)}')
        self.stdout.write(f'Не найдено совпадений: {len(unmatched_rows)}')
        self.stdout.write(f'Near-miss (совпадает после rstrip("/"), '
                          f'НЕ подставляется автоматически): {len(near_misses)}')

        if near_misses:
            os.makedirs(os.path.dirname(NEAR_MISS_REPORT_PATH), exist_ok=True)
            with open(NEAR_MISS_REPORT_PATH, 'w', encoding='utf-8') as fh:
                for item in near_misses:
                    fh.write(json.dumps(item, ensure_ascii=False) + '\n')
            self.stdout.write(f'  → записаны в {NEAR_MISS_REPORT_PATH}')

        # ── Сравнение с ожидаемыми числами из coverage.json ─────────────────
        self.stdout.write('')
        self._report_drift('SolveHub', by_site_matched.get('solvehub', 0),
                           EXPECTED_SOLVEHUB_MATCHES)
        self._report_drift('ILE', by_site_matched.get('ile', 0),
                           EXPECTED_ILE_MATCHES)
        self._report_drift('Всего уникальных Problem.id',
                           len(matched_problem_ids), EXPECTED_TOTAL_UNIQUE)

        # ── Разбивка по olympiad_slug ────────────────────────────────────
        self.stdout.write('')
        self.stdout.write('Разбивка по olympiad_slug (совпало / не совпало / уникальных задач):')
        for slug in sorted(by_slug, key=lambda s: -by_slug[s]['matched']):
            stat = by_slug[slug]
            flag = '  ⚠️ ПРЕДПРИНИМАТЕЛЬСТВО, НЕ ЭКОНОМИКА' if slug in FLAGGED_SLUGS else ''
            self.stdout.write(
                f'  {slug:28s} {stat["matched"]:5d} / {stat["unmatched"]:5d} / '
                f'{len(stat["problem_ids"]):5d}{flag}')

        # ── Флаг-профили: показать НАЙДЕННЫЕ совпадения отдельно ────────────
        if flagged_matches:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'⚠️ Найдены совпадения по флаг-профилям '
                f'{sorted(FLAGGED_SLUGS)}: {len(flagged_matches)} строк. '
                f'Это профиль «предпринимательство», не «экономика» — '
                f'решение нужны ли они в банке, за владельцем. '
                f'НИЧЕГО не записано в базу по этим строкам до явного решения.'))
            for row, pid in flagged_matches[:20]:
                problem = Problem.objects.filter(id=pid).only('statement').first()
                snippet = (problem.statement[:120] if problem and problem.statement
                          else '(нет статьи)')
                self.stdout.write(
                    f'    Problem #{pid} | {row.get("olympiad_slug")} '
                    f'{row.get("year")} {row.get("stage")} | {snippet}')

        # ── Случайная выборка совпадений для визуальной приёмки ─────────────
        # (флаг-профили исключены из выборки — они уже показаны отдельно выше)
        sample_pool = [(r, p) for r, p in matched_rows
                       if r.get('olympiad_slug') not in FLAGGED_SLUGS]
        if sample_pool:
            self.stdout.write('')
            self.stdout.write(f'Случайная выборка совпадений '
                              f'(seed={options["seed"]}):')
            rng = random.Random(options['seed'])
            sample = rng.sample(sample_pool, min(options['sample_size'],
                                                 len(sample_pool)))
            problem_ids = [pid for _, pid in sample]
            problems_by_id = {p.id: p for p in
                              Problem.objects.filter(id__in=problem_ids).only(
                                  'id', 'statement')}
            for row, pid in sample:
                problem = problems_by_id.get(pid)
                snippet = (problem.statement[:150] if problem and problem.statement
                          else '(нет статьи)')
                self.stdout.write(
                    f'  Problem #{pid} | {row.get("olympiad_slug")} '
                    f'{row.get("year")} / {row.get("stage")} / '
                    f'№{row.get("number")} | {snippet}')

        if not apply_mode:
            self.stdout.write('')
            self.stdout.write('DRY-RUN: в базу ничего не записано.')
            return

        # ── Запись ───────────────────────────────────────────────────────
        created, existing = 0, 0
        for row, pid in matched_rows:
            raw_meta = {k: v for k, v in row.items() if k not in EXPLICIT_FIELDS}
            _, was_created = OlympiadRef.objects.get_or_create(
                problem_id=pid,
                event_id=row.get('event_id', ''),
                defaults={
                    'source_site': row.get('source_site', ''),
                    'olympiad_slug': row.get('olympiad_slug', ''),
                    'olympiad_name': olympiad_names.get(row.get('olympiad_slug'), ''),
                    'academic_year': row.get('academic_year') or '',
                    'year': row.get('year'),
                    'stage': row.get('stage') or '',
                    'grade': row.get('grade') or '',
                    'variant': row.get('variant') or '',
                    'number': row.get('number') or '',
                    'record_id': row.get('record_id', ''),
                    'match_method': 'url_exact',
                    'match_score': 1.0,
                    'official_url': row.get('source_url', ''),
                    'raw_meta': raw_meta,
                },
            )
            if was_created:
                created += 1
            else:
                existing += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Готово: создано {created}, уже было {existing}, '
            f'всего OlympiadRef в базе: {OlympiadRef.objects.count()}'))

    def _report_drift(self, label, actual, expected):
        if expected:
            drift_pct = abs(actual - expected) / expected * 100
        else:
            drift_pct = 0.0
        marker = ''
        if drift_pct > DRIFT_WARN_PCT:
            marker = (f'  ⚠️ РАСХОЖДЕНИЕ > {DRIFT_WARN_PCT}% — возможна проблема '
                      f'с форматом url, проверить вручную')
        self.stdout.write(
            f'{label}: факт {actual}, ожидалось (coverage.json) {expected}, '
            f'расхождение {drift_pct:.1f}%{marker}')
