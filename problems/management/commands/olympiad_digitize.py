# -*- coding: utf-8 -*-
"""Оцифровка официальных PDF олимпиады — подготовка без модели.

Олимпиада задаётся ЯВНО: `--olympiad vp|mosh` (реестр
`problems/olympiad_audit/registry.py`: папка аудита). Без флага — отказ.

    inventory --olympiad X
        обходит ВСЕ файлы raw\\ аудита и пишет digitized\\inventory.jsonl
        (по строке на файл: вид, комплекты, слой, идёт ли в оцифровку и
        почему нет) и digitized\\events_files.jsonl (комплект → файлы
        условий, решений, критериев; новые комплекты — с new=true);
    render --olympiad X [--limit N]
        PDF из инвентаря (digitize=true, не дубль) → PNG 200 dpi и текст
        слоя по страницам в digitized\\pages\\<sha16>\\; готовое не
        перерисовывается; манифест — digitized\\pages_manifest.jsonl.

    transcribe --olympiad X --max-usd X [--limit N] [--pages-file F] [--workers 20] [--yes]
        страницы → зрячая модель GLM-5.3-Flash → digitized\\pages\\<sha16>\\p<N>.json
        (problems/olympiad_audit/transcribe.py). Без --yes — только ПЛАН
        и смета, ни одного вызова; --max-usd обязателен; готовые страницы
        не вызываются повторно (докачка); расход — transcribe_cost.jsonl;
    assemble --olympiad X [--events ID …] [--no-crop]
        страницы → задания эталона v2: reference_problems_v2.jsonl,
        events_v2.jsonl, figures\\, compare_v1_v2.csv
        (problems/olympiad_audit/assemble.py).

Корень данных: `--data-root`, иначе переменная `OLYMPIAD_DATA_ROOT`,
иначе `<родитель BASE_DIR>\\weconomics-data\\olympiads`.

⚠️ В БАЗУ НИЧЕГО НЕ ПИШЕТСЯ. Пишется только папка digitized\\ аудита;
reference_events.jsonl не правится. Модель зовёт только `transcribe --yes`.

⚠️ ПРОТОКОЛЫ И СПИСКИ ПОБЕДИТЕЛЕЙ В ОЦИФРОВКУ НЕ ИДУТ (персональные данные,
CLAUDE.md P0): инвентарь помечает их `exclude_reason`, и печать выводит
их отдельным списком. Как ищутся — в шапке `problems/olympiad_audit/digitize.py`.
"""
from __future__ import annotations

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.olympiad_audit import assemble, digitize, registry, transcribe

#: Подкоманда → метод. `transcribe` и `assemble` допишутся сюда же.
_SUBCOMMANDS = {
    'inventory': '_inventory',
    'render': '_render',
    'transcribe': '_transcribe',
    'assemble': '_assemble',
}

PROGRESS_EVERY_PAGES = 100


class Command(BaseCommand):
    help = ('Оцифровка олимпиадных PDF: inventory (опись raw\\), '
            'render (страницы в PNG). В базу не пишет.')

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='subcommand', metavar='ПОДКОМАНДА')

        def common(p):
            p.add_argument('--olympiad', choices=sorted(registry.REGISTRY),
                           help='Слаг олимпиады из реестра аудита (обязателен).')
            p.add_argument('--data-root', metavar='DIR',
                           help='Корень данных олимпиад (по умолчанию '
                                'OLYMPIAD_DATA_ROOT или ..\\weconomics-data\\olympiads).')
            return p

        common(sub.add_parser('inventory', help='Опись всех файлов raw\\.'))
        render = common(sub.add_parser('render', help='PDF → PNG 200 dpi + текст слоя.'))
        render.add_argument('--limit', type=int, default=None,
                            help='Нарисовать не больше N файлов (для пробы).')
        tr = common(sub.add_parser('transcribe', help='Страницы → зрячая модель (деньги!).'))
        tr.add_argument('--max-usd', type=float, default=None,
                        help='Потолок расхода прогона, $ (обязателен).')
        tr.add_argument('--limit', type=int, default=None,
                        help='Не больше N страниц (из ещё не готовых).')
        tr.add_argument('--pages-file', metavar='F',
                        help='Только страницы из файла: по строке «pages/<sha16>/p<N>».')
        tr.add_argument('--workers', type=int, default=20,
                        help='Одновременных вызовов (не больше 20; лимит Z.AI — 50).')
        tr.add_argument('--yes', action='store_true',
                        help='Действительно вызывать модель (без флага — только план).')
        asm = common(sub.add_parser('assemble', help='Страницы → задания эталона v2.'))
        asm.add_argument('--events', nargs='*', metavar='EVENT_ID',
                         help='Только эти комплекты (по умолчанию все).')
        asm.add_argument('--no-crop', action='store_true',
                         help='Не вырезать рисунки (быстрая сборка).')

    # ── Вход ────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        name = options.get('subcommand')
        if name not in _SUBCOMMANDS:
            raise CommandError(
                f'Нужна подкоманда: {", ".join(_SUBCOMMANDS)}. Ничего не сделано.')
        if not options.get('olympiad'):
            raise CommandError(
                '--olympiad <слаг> обязателен (vp, mosh, …): папка аудита '
                'берётся из реестра. Ничего не сделано.')
        self.olympiad = registry.get(options['olympiad'])
        root = (Path(options['data_root']) if options.get('data_root')
                else digitize.default_data_root(settings.BASE_DIR))
        self.audit_dir = root / self.olympiad.audit_dir
        if not (self.audit_dir / 'raw').is_dir():
            raise CommandError(f'Нет папки raw\\ аудита: {self.audit_dir}')
        self.digitized = self.audit_dir / 'digitized'
        return getattr(self, _SUBCOMMANDS[name])(options)

    def _say(self, text=''):
        self.stdout.write(text)
        self.stdout.flush()  # прогресс виден и при выводе в файл

    # ── inventory ───────────────────────────────────────────────────────

    def _inventory(self, options):
        started = time.monotonic()
        rows = digitize.build_inventory(self.olympiad.slug, self.audit_dir)
        digitize.write_jsonl(self.digitized / 'inventory.jsonl', rows)
        events = digitize.build_events_files(self.olympiad.slug, self.audit_dir, rows)
        digitize.write_jsonl(self.digitized / 'events_files.jsonl', events)
        summary = digitize.summarize(rows)

        self._say(f'Инвентарь {self.olympiad.slug}: {summary["files"]} файлов '
                  f'→ {self.digitized / "inventory.jsonl"}')
        self._say('\nПо виду (kind):')
        for kind in digitize.KINDS:
            self._say(f'  {kind:<10} {summary["by_kind"].get(kind, 0)}')
        self._say('\nВид × оцифровка:')
        for key, n in summary['kind_x_digitize'].items():
            self._say(f'  {key:<16} {n}')
        self._say('\nОцифровка / причина исключения:')
        for reason, n in sorted(summary['by_reason'].items(), key=lambda x: -x[1]):
            self._say(f'  {n:>5}  {reason}')
        total_kind = sum(summary['by_kind'].values())
        total_reason = sum(summary['by_reason'].values())
        ok = total_kind == total_reason == summary['files']
        self._say(f'\nКонтроль: Σ по виду {total_kind}, Σ по причинам '
                  f'{total_reason}, файлов {summary["files"]} — '
                  f'{"сходится" if ok else "НЕ СХОДИТСЯ"}')
        if not ok:
            raise CommandError('Сумма по категориям не равна числу файлов.')

        self._say(f'\nPDF к оцифровке: {summary["pdf_to_digitize"]} '
                  f'(из них сканов без слоя: {summary["pdf_scans"]}); '
                  f'страниц {summary["pages_to_digitize"]}: со слоем '
                  f'{summary["pages_with_layer"]}, без слоя {summary["pages_scan"]}')
        self._say('Страниц к оцифровке по году и этапу (по первому комплекту файла):')
        for key, n in summary['pages_by_year_stage'].items():
            self._say(f'  {key:<18} {n}')

        personal = summary['personal_data']
        self._say(f'\nПротоколы/списки (персональные данные, в модель НЕ идут): '
                  f'{len(personal) or "не найдено"}')
        for row in rows:
            if row['exclude_reason'] == digitize.REASON_PERSONAL:
                self._say(f'  {row["file"]}  [{row.get("personal_data_hit", "")}]')

        conflicts = [r for r in rows if r.get('duplicate_conflict')]
        if conflicts:
            self._say(f'\nДубли с другой раскладкой по эталону (верна по '
                      f'содержимому — первого файла): {len(conflicts)}')
            for row in conflicts:
                self._say(f'  {row["file"]}: {row["duplicate_conflict"]}')

        new = [e for e in events if e['new']]
        self._say(f'\nКомплектов с файлами: {len(events)} → '
                  f'{self.digitized / "events_files.jsonl"}; новых (нет в '
                  f'reference_events.jsonl): {len(new)}')
        for event in new:
            files = [f['file'].rsplit('/', 1)[-1]
                     for key in ('task_files', 'solution_files', 'criteria_files')
                     for f in event[key]]
            self._say(f'  {event["event_id"]}: {", ".join(files)}')
        self._say(f'\nГотово за {time.monotonic() - started:.0f} с.')

    # ── render ──────────────────────────────────────────────────────────

    def _render(self, options):
        path = self.digitized / 'inventory.jsonl'
        if not path.is_file():
            raise CommandError(f'Нет инвентаря: {path}. Сначала inventory.')
        rows = digitize.read_jsonl(path)
        targets = digitize.render_targets(rows)
        limit = options.get('limit')
        started = time.monotonic()
        manifest, drawn, reused, done_files, next_mark = [], 0, 0, 0, PROGRESS_EVERY_PAGES
        total_pages = sum(r['pages'] for r in targets)
        seen_pages = 0
        for row in targets:
            out_dir = self.digitized / row['page_dir']
            complete = all((out_dir / f'p{n}.{ext}').is_file()
                           for n in range(1, row['pages'] + 1)
                           for ext in ('png', 'txt'))
            if limit is not None and done_files >= limit and not complete:
                continue
            pages, n_drawn = digitize.render_pdf(
                digitize.source_path(self.audit_dir, row), out_dir)
            if n_drawn:
                done_files += 1
            drawn += n_drawn
            reused += len(pages) - n_drawn
            for page in pages:
                manifest.append({'file': row['file'], 'page_dir': row['page_dir'],
                                 **page, 'png': f'{row["page_dir"]}/{page["png"]}'})
            seen_pages += len(pages)
            while seen_pages >= next_mark:
                self._say(f'  … {seen_pages}/{total_pages} страниц '
                          f'({time.monotonic() - started:.0f} с)')
                next_mark += PROGRESS_EVERY_PAGES
        digitize.write_jsonl(self.digitized / 'pages_manifest.jsonl', manifest)
        scaled = sum(1 for m in manifest if m.get('scaled_to_max_side'))
        size = sum(f.stat().st_size for f in (self.digitized / 'pages').rglob('*')
                   if f.is_file()) if (self.digitized / 'pages').is_dir() else 0
        self._say(f'Отрисовано страниц: {drawn}; уже было: {reused}; '
                  f'в манифесте: {len(manifest)} из {total_pages}; '
                  f'уменьшено до {digitize.MAX_SIDE_PX} px: {scaled}; '
                  f'pages\\ на диске: {size / 2**30:.2f} ГБ; '
                  f'{time.monotonic() - started:.0f} с.')

    # ── transcribe ──────────────────────────────────────────────────────

    def _transcribe(self, options):
        if options.get('max_usd') is None:
            raise CommandError('--max-usd обязателен: потолок расхода прогона в '
                               'долларах. Ничего не сделано.')
        path = self.digitized / 'inventory.jsonl'
        if not path.is_file():
            raise CommandError(f'Нет инвентаря: {path}. Сначала inventory и render.')
        jobs = transcribe.build_jobs(digitize.read_jsonl(path), str(self.digitized),
                                     self.olympiad.olympiad_name)
        if options.get('pages_file'):
            with open(options['pages_file'], encoding='utf-8') as handle:
                wanted = {line.strip() for line in handle if line.strip()}
            jobs = [job for job in jobs if job.key in wanted]
        all_todo = transcribe.todo(jobs, str(self.digitized))
        todo = all_todo
        if options.get('limit') is not None:
            todo = todo[:options['limit']]
        cost_log = transcribe.CostLog(str(self.digitized / 'transcribe_cost.jsonl'))
        measured = cost_log.average('page')
        per_page = measured if measured is not None else transcribe.DEFAULT_PAGE_USD
        scans = sum(not job.has_layer for job in todo)
        # Смета: вызов на страницу + повтор у ~20 % страниц со слоем + судья у
        # ~половины сканов (страницы с формулами/таблицами/рисунками).
        calls = len(todo) + 0.2 * (len(todo) - scans) + 0.5 * scans
        spent_before, calls_before = cost_log.total()
        self._say(f'ПЛАН transcribe {self.olympiad.slug}: страниц всего {len(jobs)}, '
                  f'готово {len(jobs) - len(all_todo)}, к вызову {len(todo)} '
                  f'(со слоем {len(todo) - scans}, сканов {scans}; на глаза по '
                  f'выборке {sum(j.eyes_sample for j in todo)}).')
        self._say(f'  Вызовов ≈ {calls:.0f}; цена страницы '
                  f'{"по журналу" if measured is not None else "до замера"} '
                  f'${per_page:.4f} → ≈ ${calls * per_page:.2f}; потолок '
                  f'${options["max_usd"]:.2f}; модель {transcribe.MODEL}, '
                  f'потоков {min(options["workers"], 20)}.')
        self._say(f'  Уже потрачено по журналу: ${spent_before:.4f} за {calls_before} вызовов.')
        if not options.get('yes'):
            self._say('ПЛАН — ни одного вызова модели. Запуск: тот же вызов с --yes.')
            return
        if not todo:
            self._say('Расшифровывать нечего — все страницы готовы.')
            return
        provider = transcribe.make_provider()
        if not provider.is_available():
            raise CommandError(provider.unavailable_reason() or 'Поставщик недоступен.')
        runner = transcribe.Transcriber(
            root=str(self.digitized), provider=provider,
            budget=transcribe.Budget(options['max_usd'], per_page * 1.3),
            cost_log=cost_log, workers=options['workers'], stdout=self.stdout)
        stats = runner.run(todo)
        spent_after, calls_after = cost_log.total()
        self._say(f'ГОТОВО: {dict(stats)}; потрачено в прогоне '
                  f'${runner.budget.spent:.4f} ({runner.budget.calls} вызовов); '
                  f'всего по журналу ${spent_after:.4f} за {calls_after} вызовов.')
        if runner.stopped:
            self._say(f'ОСТАНОВЛЕНО: {runner.stopped}')

    # ── assemble ────────────────────────────────────────────────────────

    def _assemble(self, options):
        events_path = self.audit_dir / 'reference_events.jsonl'
        reference_events = digitize.read_jsonl(events_path) if events_path.is_file() else []
        v1_rows = []
        for candidate in ('session2', 'session1'):
            v1 = self.audit_dir / candidate / 'reference_problems_full.jsonl'
            if v1.is_file():
                v1_rows = digitize.read_jsonl(v1)
                break
        summary = assemble.assemble(
            str(self.digitized), reference_events, v1_rows, model=transcribe.MODEL,
            only_events=set(options['events']) if options.get('events') else None,
            crop=not options.get('no_crop'))
        self._say(f'Сборка {self.olympiad.slug} → '
                  f'{self.digitized / "reference_problems_v2.jsonl"}')
        for key, value in sorted(summary.items()):
            self._say(f'  {key}: {value}')
