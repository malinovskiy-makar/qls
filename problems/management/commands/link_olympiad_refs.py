"""
Команда link_olympiad_refs — привязывает задачи банка к реальным олимпиадам
через совпадение SourceReference.url с external_export
(SolveHub/ILE, обход официальных публичных индексов, 01.09.2026).

Два метода, в порядке приоритета:
  1. url_exact — точное совпадение строки, match_score=1.0.
  2. url_www_normalized — совпадение после нормализации (схема → https,
     срезан 'www.', путь без хвостового '/'), match_score=0.97. Найден
     после того как ILE дал 0 точных совпадений: у ILE в базе 99,7% url
     с 'www.', во внешнем экспорте — 0% с 'www.' (все 1169 строк).
     Нормализация — ТОЛЬКО для сравнения; в official_url всегда пишется
     настоящий SourceReference.url как есть, нормализованная форма нигде
     не сохраняется как истина.

Каждое совпадение — одна строка OlympiadRef (get_or_create по
(problem, event_id) в --apply). Ничего в Problem/SourceReference не меняется.

Запуск:
    manage.py link_olympiad_refs --export-path <путь к all_problem_occurrences.jsonl>
    manage.py link_olympiad_refs --export-path <путь> --apply
"""

import json
import os
import random
from urllib.parse import urlsplit, urlunsplit

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

UNMATCHED_REPORT_PATH = 'reports/olympiad_link/unmatched_urls.jsonl'


def normalize_url_for_matching(url):
    """Схема → https, срезан 'www.' с домена, путь без хвостового '/'.

    Только для СРАВНЕНИЯ — настоящий url (exact или из базы) в результат
    не подставляется, чтобы нормализованная форма нигде не осела как истина.
    """
    s = urlsplit(url)
    netloc = s.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    path = s.path.rstrip('/')
    return urlunsplit(('https', netloc, path, s.query, s.fragment))


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


def load_url_indexes():
    """Строит два индекса по ВСЕМ SourceReference с непустым url:
      - exact_index:  url -> [problem_id, ...]
      - norm_index:   normalize_url_for_matching(url) -> [(problem_id, url), ...]
    norm_index хранит НАСТОЯЩИЙ url из базы (не нормализованный) —
    он и пойдёт в official_url при совпадении вторым методом.
    """
    exact_index = {}
    norm_index = {}
    qs = (SourceReference.objects
          .exclude(url='')
          .values_list('url', 'problem_id'))
    for url, pid in qs.iterator(chunk_size=5000):
        exact_index.setdefault(url, []).append(pid)
        norm_key = normalize_url_for_matching(url)
        norm_index.setdefault(norm_key, []).append((pid, url))
    return exact_index, norm_index


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
        url_index, norm_index = load_url_indexes()

        rows = []
        with open(export_path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))

        total = len(rows)
        by_site_total = {}
        # by_site_matched[site][method] = count
        by_site_matched = {}
        by_site_unmatched = {}
        # by_slug[slug] = {'matched': {method: int}, 'unmatched': int, 'problem_ids': set}
        by_slug = {}
        matched_rows = []       # (row, problem_id, method, official_url)
        unmatched_rows = []
        matched_problem_ids = set()
        matched_problem_ids_by_method = {'url_exact': set(), 'url_www_normalized': set()}
        flagged_matches = []    # matched строки по FLAGGED_SLUGS

        for row in rows:
            site = row.get('source_site', '?')
            slug = row.get('olympiad_slug', '?')
            url = row.get('source_url', '')

            by_site_total[site] = by_site_total.get(site, 0) + 1
            slug_stat = by_slug.setdefault(
                slug, {'matched': {}, 'unmatched': 0, 'problem_ids': set()})

            pairs = None       # [(problem_id, official_url), ...]
            method = None

            exact_pids = url_index.get(url)
            if exact_pids:
                method = 'url_exact'
                pairs = [(pid, url) for pid in exact_pids]
            else:
                norm_pairs = norm_index.get(normalize_url_for_matching(url))
                if norm_pairs:
                    method = 'url_www_normalized'
                    pairs = norm_pairs

            if pairs:
                site_stat = by_site_matched.setdefault(site, {})
                site_stat[method] = site_stat.get(method, 0) + 1
                slug_stat['matched'][method] = slug_stat['matched'].get(method, 0) + 1
                for pid, official_url in pairs:
                    matched_rows.append((row, pid, method, official_url))
                    matched_problem_ids.add(pid)
                    matched_problem_ids_by_method[method].add(pid)
                    slug_stat['problem_ids'].add(pid)
                    if slug in FLAGGED_SLUGS:
                        flagged_matches.append((row, pid, method))
            else:
                by_site_unmatched[site] = by_site_unmatched.get(site, 0) + 1
                slug_stat['unmatched'] += 1
                unmatched_rows.append(row)

        # ── Отчёт: общие числа ────────────────────────────────────────────
        self.stdout.write(f'Строк в экспорте: {total}')
        for site in sorted(by_site_total):
            site_stat = by_site_matched.get(site, {})
            matched_total = sum(site_stat.values())
            self.stdout.write(
                f'  {site}: {by_site_total[site]} '
                f'(совпало: {matched_total} '
                f'[url_exact: {site_stat.get("url_exact", 0)}, '
                f'url_www_normalized: {site_stat.get("url_www_normalized", 0)}], '
                f'не совпало: {by_site_unmatched.get(site, 0)})')

        self.stdout.write('')
        self.stdout.write(f'Всего совпадений: {len(matched_rows)} '
                          f'(url_exact: {sum(1 for *_, m, _ in matched_rows if m == "url_exact")}, '
                          f'url_www_normalized: '
                          f'{sum(1 for *_, m, _ in matched_rows if m == "url_www_normalized")})')
        self.stdout.write(f'Уникальных Problem.id с хотя бы одной привязкой: '
                          f'{len(matched_problem_ids)} '
                          f'(из них только через url_www_normalized: '
                          f'{len(matched_problem_ids_by_method["url_www_normalized"] - matched_problem_ids_by_method["url_exact"])})')
        self.stdout.write(f'Не найдено совпадений ни одним методом: {len(unmatched_rows)}')

        if unmatched_rows:
            os.makedirs(os.path.dirname(UNMATCHED_REPORT_PATH), exist_ok=True)
            with open(UNMATCHED_REPORT_PATH, 'w', encoding='utf-8') as fh:
                for row in unmatched_rows:
                    fh.write(json.dumps({
                        'event_id': row.get('event_id'),
                        'record_id': row.get('record_id'),
                        'source_site': row.get('source_site'),
                        'export_url': row.get('source_url'),
                    }, ensure_ascii=False) + '\n')
            self.stdout.write(f'  → записаны в {UNMATCHED_REPORT_PATH}')

        # ── Сравнение с ожидаемыми числами из coverage.json ─────────────────
        # Сравниваем УНИКАЛЬНЫЕ Problem.id (а не строки/совпадения) — coverage.json
        # считает уникальные задачи источника, а не вхождения.
        self.stdout.write('')
        self._report_drift('SolveHub (уникальных Problem.id)',
                           len({pid for r, pid, *_ in matched_rows
                                if r.get('source_site') == 'solvehub'}),
                           EXPECTED_SOLVEHUB_MATCHES)
        self._report_drift('ILE (уникальных Problem.id)',
                           len({pid for r, pid, *_ in matched_rows
                                if r.get('source_site') == 'ile'}),
                           EXPECTED_ILE_MATCHES)
        self._report_drift('Всего уникальных Problem.id',
                           len(matched_problem_ids), EXPECTED_TOTAL_UNIQUE)

        # ── Разбивка по olympiad_slug ────────────────────────────────────
        self.stdout.write('')
        self.stdout.write('Разбивка по olympiad_slug '
                          '(url_exact / url_www_normalized / не совпало / уникальных задач):')
        for slug in sorted(by_slug,
                          key=lambda s: -sum(by_slug[s]['matched'].values())):
            stat = by_slug[slug]
            flag = '  ⚠️ ПРЕДПРИНИМАТЕЛЬСТВО, НЕ ЭКОНОМИКА' if slug in FLAGGED_SLUGS else ''
            self.stdout.write(
                f'  {slug:28s} {stat["matched"].get("url_exact", 0):5d} / '
                f'{stat["matched"].get("url_www_normalized", 0):5d} / '
                f'{stat["unmatched"]:5d} / '
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
            for row, pid, method in flagged_matches[:20]:
                problem = Problem.objects.filter(id=pid).only('statement').first()
                snippet = (problem.statement[:120] if problem and problem.statement
                          else '(нет статьи)')
                self.stdout.write(
                    f'    Problem #{pid} | {row.get("olympiad_slug")} '
                    f'{row.get("year")} {row.get("stage")} | [{method}] | {snippet}')

        # ── Случайная выборка совпадений для визуальной приёмки ─────────────
        # (флаг-профили исключены из выборки — они уже показаны отдельно выше)
        rng = random.Random(options['seed'])
        self._print_sample(
            'Случайная выборка совпадений (оба метода)', rng,
            [(r, p, m) for r, p, m, _ in matched_rows
             if r.get('olympiad_slug') not in FLAGGED_SLUGS],
            options['sample_size'])
        self._print_sample(
            'Случайная выборка совпадений ТОЛЬКО через url_www_normalized',
            rng,
            [(r, p, m) for r, p, m, _ in matched_rows
             if m == 'url_www_normalized'
             and r.get('olympiad_slug') not in FLAGGED_SLUGS],
            options['sample_size'])

        if not apply_mode:
            self.stdout.write('')
            self.stdout.write('DRY-RUN: в базу ничего не записано.')
            return

        # ── Запись ───────────────────────────────────────────────────────
        # Флаг-профили (предпринимательство) НИКОГДА не пишутся, даже если
        # найдены — это соответствует тому, что напечатано в отчёте выше.
        match_scores = {'url_exact': 1.0, 'url_www_normalized': 0.97}
        created_by_method = {'url_exact': 0, 'url_www_normalized': 0}
        existing = 0
        for row, pid, method, official_url in matched_rows:
            if row.get('olympiad_slug') in FLAGGED_SLUGS:
                continue
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
                    'match_method': method,
                    'match_score': match_scores[method],
                    'official_url': official_url,
                    'raw_meta': raw_meta,
                },
            )
            if was_created:
                created_by_method[method] += 1
            else:
                existing += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Готово: создано {sum(created_by_method.values())} '
            f'(url_exact: {created_by_method["url_exact"]}, '
            f'url_www_normalized: {created_by_method["url_www_normalized"]}), '
            f'уже было {existing}, '
            f'всего OlympiadRef в базе: {OlympiadRef.objects.count()}'))

    def _print_sample(self, title, rng, pool, sample_size):
        if not pool:
            return
        self.stdout.write('')
        self.stdout.write(f'{title} (seed воспроизводим для этой команды):')
        sample = rng.sample(pool, min(sample_size, len(pool)))
        problem_ids = [pid for _, pid, _ in sample]
        problems_by_id = {p.id: p for p in
                          Problem.objects.filter(id__in=problem_ids).only(
                              'id', 'statement')}
        for row, pid, method in sample:
            problem = problems_by_id.get(pid)
            snippet = (problem.statement[:150] if problem and problem.statement
                      else '(нет статьи)')
            self.stdout.write(
                f'  Problem #{pid} | {row.get("olympiad_slug")} '
                f'{row.get("year")} / {row.get("stage")} / '
                f'№{row.get("number")} | [{method}] | {snippet}')

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
