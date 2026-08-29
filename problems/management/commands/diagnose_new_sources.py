# -*- coding: utf-8 -*-
"""Разбор отказов шлюза `render_new_sources` — по источнику и по коду.

Зачем отдельная команда. `render_new_sources` пишет в отчёт только
СПИСКИ id (`pass_ids` / `fail_ids`) и сводку кодов по всему корпусу.
Чтобы чинить, этого мало: нужно знать, какой код у КАЖДОЙ задачи и что
именно шлюз увидел («уцелевшие TeX-команды: \\ge, \\le»). Без этого
правка идёт вслепую, а это ровно то, чем испортили 233 поля
([ADR 0005](../../../docs/adr/0005-ai-writes-new-fields-only.md)).

Команда только ЧИТАЕТ. В базу не пишет ни одного поля.

⚠️ Пишет в СВОЙ файл (`fails_diagnosis.json`), а не в
`gate_new_sources.json`: боевой отчёт шлюза затирается любым его
прогоном, в том числе усечённым `--limit` (дефект уже стрелял —
см. `reports/import_new_sources/report.md`, находка 3).
"""
import json
import os
from collections import Counter, defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.katex_preflight import KatexPreflight
from problems.management.commands.render_new_sources import SOURCES, verdict_for
from problems.models import Problem, Source

OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'import_new_sources')


class Command(BaseCommand):
    help = ('Разбор отказов шлюза новых источников: код × источник, '
            'детали и живые примеры. Только чтение.')

    def add_arguments(self, parser):
        parser.add_argument('--source', choices=list(SOURCES),
                            help='только один источник')
        parser.add_argument('--limit', type=int,
                            help='только первые N задач (усечение называется в выводе)')
        parser.add_argument('--examples', type=int, default=3,
                            help='сколько живых примеров показывать на код (по умолчанию 3)')
        parser.add_argument('--out-dir',
                            help='куда класть отчёт; тесты обязаны давать временную папку')

    def handle(self, *args, **options):
        """См. `render_new_sources.handle` — та же обёртка вокруг
        `DJANGO_ALLOW_ASYNC_UNSAFE`: ставим на время прогона и
        возвращаем окружение ровно как было, иначе переменная утекает
        в процесс и роняет `test_check_deploy_is_clean`."""
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
        limit = options['limit']
        slugs = [options['source']] if options['source'] else list(SOURCES)

        names = {}
        for slug in slugs:
            source = Source.objects.filter(name=SOURCES[slug]).first()
            if source is None:
                raise CommandError(
                    f'Источник «{SOURCES[slug]}» не найден в базе — импорт не '
                    f'выполнялся. Сначала import_{slug}, потом разбор.')
            names[slug] = source

        rows = []
        checked = 0
        with KatexPreflight() as checker:
            for slug, source in names.items():
                qs = (Problem.objects.filter(source_references__source=source)
                      .distinct().order_by('id'))
                for problem in qs.prefetch_related('parts').iterator(chunk_size=500):
                    if limit is not None and checked >= limit:
                        break
                    checked += 1
                    verdict = verdict_for(problem, checker)
                    if verdict.ok:
                        continue
                    rows.append({
                        'id': problem.id,
                        'source': slug,
                        'content_format': problem.content_format,
                        'codes': list(verdict.codes),
                        'details': list(verdict.details),
                    })
                self.stdout.write(f'{source.name}: проверено, отказов пока {len(rows)}')

        by_source_code = defaultdict(Counter)
        code_totals = Counter()
        for row in rows:
            for code in row['codes']:
                by_source_code[row['source']][code] += 1
                code_totals[code] += 1

        lines = ['', f'Проверено задач: {checked}', f'Отказов (FAIL): {len(rows)}', '']
        header = ['код'] + slugs + ['всего']
        lines.append(' | '.join(f'{h:>12}' for h in header))
        for code, total in code_totals.most_common():
            cells = [f'{code:>12}']
            cells += [f'{by_source_code[s][code]:>12}' for s in slugs]
            cells.append(f'{total:>12}')
            lines.append(' | '.join(cells))

        # Задачи с ЕДИНСТВЕННЫМ кодом — их чинит одна правка; задачи с
        # букетом кодов дороже и разбираются отдельно.
        single = Counter(row['codes'][0] for row in rows if len(row['codes']) == 1)
        lines.append('')
        lines.append(f'Задач с единственным кодом: {sum(single.values())} из {len(rows)}')
        for code, n in single.most_common():
            lines.append(f'    {code:>12}: {n}')

        n_examples = options['examples']
        lines.append('')
        lines.append('=== живые примеры (id + что увидел шлюз) ===')
        for code, total in code_totals.most_common():
            lines.append(f'--- {code} ({total}) ---')
            shown = 0
            for row in rows:
                if code not in row['codes'] or shown >= n_examples:
                    continue
                shown += 1
                detail = next((d for d in row['details'] if code[:3] in d or True), '')
                lines.append(f'  #{row["id"]} [{row["source"]}] коды={row["codes"]}')
                for d in row['details'][:3]:
                    lines.append(f'      {d[:220]}')

        if limit is not None:
            lines.append('')
            lines.append(f'⚠️ ОХВАТ УСЕЧЁН: --limit {limit} — проверена только часть корпуса')

        out_dir = options.get('out_dir') or OUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, 'fails_diagnosis.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'checked': checked,
                'fails': len(rows),
                'truncated_to': limit,
                'code_totals': dict(code_totals),
                'by_source': {s: dict(c) for s, c in by_source_code.items()},
                'rows': rows,
            }, f, ensure_ascii=False, indent=1)
        lines.append('')
        lines.append(f'  разбор по задачам: {path}')
        self.stdout.write('\n'.join(lines))
