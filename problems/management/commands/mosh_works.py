"""Работы победителей и призёров МОШ по экономике: списки, zip, баллы по задачам.

    manage.py mosh_works index    --dir D [--years 2021,2022,…]
    manage.py mosh_works download --dir D [--limit N] [--only id,…|@файл]
    manage.py mosh_works scores   --dir D [--limit N] [--max-usd 1.50] [--yes] [--retry-review]
    manage.py mosh_works report   --dir D

Все файлы — ВНЕ репозитория, в `--dir`. В базу команда не пишет ни строки.
ФИО участников не хранятся нигде: участник — номер работы. Адреса zip берутся
только из ссылок таблицы призёров, подбор адресов запрещён. Подробности —
docs/MOSH_WORKS.md.
"""
import json
import os
from collections import Counter
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from problems.mosh_works import fetch, listing, scans, scores
from problems.vp_works import hse

DEFAULT_DIR = r'C:\Users\shipu\weconomics-data\mosh_works'

#: Число строк таблиц и ссылок на zip, как их видели при разведке 09.10.2026.
RECON_ROWS = {2021: 237, 2022: 253, 2023: 236, 2024: 257, 2025: 167}
RECON_ZIPS = {2021: 237, 2022: 253, 2023: 236, 2024: 257, 2025: 165}


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path, rows):
    """Атомарно: сначала во временный файл, потом подмена."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


def only_ids(arg):
    """`--only 1,2,3` или `--only @файл` → множество work_id (пусто — все)."""
    arg = (arg or '').strip()
    if arg.startswith('@'):
        with open(arg[1:], encoding='utf-8') as fh:
            arg = fh.read().replace('\n', ',')
    return {w.strip() for w in arg.split(',') if w.strip()}


class Command(BaseCommand):
    help = 'Работы призёров МОШ: index / download / scores / report.'

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        for name in ('index', 'download', 'scores', 'report'):
            p = sub.add_parser(name)
            p.add_argument('--dir', default=DEFAULT_DIR, help='папка данных вне репозитория')
            if name == 'index':
                p.add_argument('--years', default='', help='только эти годы: 2024,2025')
            if name in ('download', 'scores'):
                p.add_argument('--limit', type=int, default=0,
                               help='download — сколько скачать; scores — случайная проба из N работ')
                p.add_argument('--only', default='',
                               help='work_id через запятую или @файл (по строке на номер)')
            if name == 'download':
                p.add_argument('--stop-after-fails', type=int, default=0,
                               help='выйти после N неудач подряд (сайт лёг); 0 — правило пауз')
            if name == 'scores':
                p.add_argument('--max-usd', type=float, default=1.5)
                p.add_argument('--yes', action='store_true',
                               help='без него — только план, ни одного вызова модели')
                p.add_argument('--retry-review', action='store_true',
                               help='второй проход по review: тот же вырез, затем повёрнутый')
                p.add_argument('--years', default='',
                               help='только эти годы; по умолчанию все, кроме 2021 (пятна)')
                p.add_argument('--preview', type=int, default=5,
                               help='в плане: сколько случайных вырезов сохранить для осмотра')

    def say(self, message=''):
        self.stdout.write(message)
        self.stdout.flush()

    def handle(self, *args, **opts):
        data_dir = os.path.abspath(opts['dir'])
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        if data_dir.lower().startswith(repo.lower() + os.sep) or data_dir.lower() == repo.lower():
            raise CommandError('--dir внутри репозитория: данные храним только вне его.')
        os.makedirs(data_dir, exist_ok=True)
        try:
            return getattr(self, 'do_' + opts['action'])(data_dir, opts)
        except hse.Blocked as error:
            raise CommandError('СТОП: %s Сохранено то, что успели.' % error)

    # ------------------------------------------------------------- index
    def do_index(self, data_dir, opts, client=None):
        years = [int(y) for y in (opts.get('years') or '').split(',') if y.strip()] \
            or list(listing.YEARS)
        client = client or fetch.Client(log=self.say)
        path = os.path.join(data_dir, 'index.jsonl')
        old = {(r['year'], r['work_id']): r for r in read_jsonl(path)}
        listed_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        records = []
        for year in years:
            body = client.get(listing.PAGE_URL % year, expect='html')
            try:
                rows = listing.parse_table(body.decode('utf-8', errors='replace'), year, listed_at)
            except ValueError as error:
                raise CommandError('%d: таблицу не разобрать — %s' % (year, error))
            for rec in rows:
                # Поля скачивания и баллов, если уже были, сохраняем.
                prev = old.get((year, rec['work_id']), {})
                rec.update({k: v for k, v in prev.items() if k not in listing.INDEX_FIELDS})
                records.append(rec)
            self.say('%d: строк %d, ссылок на zip %d'
                     % (year, len(rows), sum(1 for r in rows if r['zip_url'])))
        # Годы, которых не касались, остаются как были.
        kept = [r for key, r in old.items() if key[0] not in years]
        write_jsonl(path, kept + records)

        expected = {y: RECON_ROWS[y] for y in years if y in RECON_ROWS}
        check = listing.check_index(records, expected_rows=expected)
        self.say()
        self.say('index.jsonl: %d строк; по годам %s' % (check['rows'], dict(sorted(check['by_year'].items()))))
        self.say('повторов work_id: %d; без суммы: %d; без результата: %d'
                 % (check['duplicates'], len(check['no_total']), len(check['no_result'])))
        self.say('строк без ссылки на zip: %d%s' % (
            len(check['no_zip']), (' (%s)' % ', '.join(check['no_zip'])) if check['no_zip'] else ''))
        for year in years:
            zips = sum(1 for r in records if r['year'] == year and r['zip_url'])
            if year in RECON_ZIPS and zips != RECON_ZIPS[year]:
                check['problems'].append('%d: ссылок на zip %d, при разведке было %d'
                                         % (year, zips, RECON_ZIPS[year]))
        for line in check['problems']:
            self.say('  нарушение: ' + line)
        self.say('запросов к сайту: %d' % client.requests)
        return None

    # ---------------------------------------------------------- download
    def do_download(self, data_dir, opts, client=None, sleep=None):
        path = os.path.join(data_dir, 'index.jsonl')
        records = read_jsonl(path)
        if not records:
            raise CommandError('index.jsonl пуст — сначала mosh_works index.')
        client = client or fetch.Client(log=self.say)
        kwargs = {'sleep': sleep} if sleep else {}
        wanted = only_ids(opts.get('only'))
        batch = [r for r in records if r['work_id'] in wanted] if wanted else records
        try:
            # Сохраняем ВЕСЬ index, даже когда качаем часть (`--only`).
            stats = fetch.download_all(
                batch, data_dir, client, limit=opts.get('limit') or 0, log=self.say,
                save=lambda _rows: write_jsonl(path, records),
                stop_after_fails=opts.get('stop_after_fails') or 0, **kwargs)
        except hse.Blocked:
            self.say('Сайт отказал — index сохранён, докачка продолжит с места.')
            raise
        check = fetch.check_download(records, data_dir)
        self.say()
        if stats.get('stopped'):
            self.say('ОСТАНОВЛЕНО: %s' % stats['stopped'])
        self.say('скачано сейчас %d, уже было %d, ошибок %d, пауз %d'
                 % (stats['downloaded'], stats['skipped_existing'], stats['failed'], stats['pauses']))
        self.say('ok %d + failed %d + не трогали %d = %d строк index'
                 % (check['ok'], check['failed'], check['pending'], len(records)))
        self.say('ok, но zip битый: %d; объём ok: %.2f ГБ; запросов %d'
                 % (len(check['ok_bad_zip']), check['bytes'] / 1e9, client.requests))
        by_year = Counter((r['year'], r.get('status') or 'pending') for r in records)
        for year in sorted({r['year'] for r in records}):
            self.say('  %d: ok %d, failed %d, не трогали %d' % (
                year, by_year[(year, 'ok')], by_year[(year, 'failed')], by_year[(year, 'pending')]))
        return None

    # ------------------------------------------------------------ scores
    def _read_scores(self, data_dir):
        return {r['work_id']: r for r in read_jsonl(os.path.join(data_dir, 'scores.jsonl'))}

    def _save_scores(self, data_dir, rows):
        write_jsonl(os.path.join(data_dir, 'scores.jsonl'), [rows[k] for k in sorted(rows)])

    def _make_crop(self, data_dir, rec, rotate=False):
        """Вырез таблицы баллов → PNG в crops/ (ровно то, что уходит в модель)."""
        rel = 'crops/%d/%s.png' % (rec['year'], rec['work_id'])
        if rotate:
            rel = rel[:-4] + '_rot180.png'
        out = os.path.join(data_dir, rel)
        if not os.path.exists(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            image = scans.first_page_image(
                os.path.join(data_dir, fetch.scan_relpath(rec)), rec['first_page'], dpi=150)
            crop = scans.crop_band(image)
            if crop.width > 1600:
                crop = crop.resize((1600, round(crop.height * 1600 / crop.width)))
            if rotate:
                crop = crop.rotate(180)
            with open(out, 'wb') as fh:
                fh.write(scores.png_bytes(crop))
        return rel

    def do_scores(self, data_dir, opts, provider=None):
        import random
        from concurrent.futures import ThreadPoolExecutor

        index = read_jsonl(os.path.join(data_dir, 'index.jsonl'))
        rows = self._read_scores(data_dir)
        spent_before = sum(r.get('cost') or 0 for r in rows.values())
        years = {int(y) for y in (opts.get('years') or '').split(',') if y.strip()} \
            or {y for y in listing.YEARS if y != 2021}
        wanted = only_ids(opts.get('only'))
        retry = bool(opts.get('retry_review'))

        eligible = [r for r in index if r.get('status') == 'ok' and r['year'] in years
                    and r.get('first_page') and (not wanted or r['work_id'] in wanted)]
        if retry:
            todo = [r for r in eligible
                    if rows.get(r['work_id'], {}).get('scores_status') == 'review'
                    and rows[r['work_id']].get('reason') in scores.RETRYABLE
                    and not rows[r['work_id']].get('retried')]
            hidden = []
        else:
            todo = [r for r in eligible if r['work_id'] not in rows]
            # Закрашено маркером — баллов не видно: не review и не деньги.
            hidden = [r for r in todo
                      if (r.get('band_stickers_pct') or 0) >= scans.HIDDEN_BAND_PCT]
            todo = [r for r in todo if r not in hidden]
        if opts.get('limit'):
            todo = random.Random(20261009).sample(todo, min(opts['limit'], len(todo)))

        self.say('работ в index: %d; подходят (ok, годы %s): %d; закрашено маркером: %d; '
                 'в модель: %d' % (len(index), sorted(years), len(eligible), len(hidden), len(todo)))
        self.say('смета: ~$%.2f; уже потрачено прежними прогонами $%.4f; потолок на все '
                 'прогоны $%.2f' % (scores.estimate_usd(len(todo)), spent_before, opts['max_usd']))
        for rec in hidden:
            rows[rec['work_id']] = {
                'work_id': rec['work_id'], 'year': rec['year'],
                'scores_status': 'hidden_by_stickers', 'reason': 'stickers',
                'band_stickers_pct': rec.get('band_stickers_pct'),
                'total_listed': rec['total_listed'], 'source': None, 'runs': 0, 'cost': 0.0}

        if not opts.get('yes'):
            sample = random.Random(7).sample(todo, min(opts.get('preview') or 0, len(todo)))
            for rec in sample:
                self.say('  вырез для осмотра: %s'
                         % os.path.join(data_dir, self._make_crop(data_dir, rec)))
            self.say('ПЛАН. Без --yes модель не вызывается ни разу.')
            return None

        from django.conf import settings
        from django.db import connection, transaction

        from problems.ai import core, providers

        provider = provider or providers.get_provider(
            getattr(settings, 'MOSH_WORKS_PROVIDER', 'glm'))
        if not provider.is_available():
            raise CommandError('Модель недоступна: %s' % provider.unavailable_reason())

        def call(rec):
            rotate = bool(rec.get('_rot'))
            rel = self._make_crop(data_dir, rec, rotate=rotate)
            with open(os.path.join(data_dir, rel), 'rb') as fh:
                png = fh.read()
            hint = (' ' + scores.RETRY_HINT) if retry else ''
            user_text = 'Работа %s. Перепиши баллы из таблицы.%s%s' % (
                rec['work_id'], hint, ' (вырез повёрнут на 180°)' if rotate else '')
            try:
                # ⚠️ atomic: при отказе поставщика core.run пишет строку AiUsageLog
                # даже с log=False (известный баг, карточка в Notion). Исключение
                # откатывает её — сессия в базу не пишет.
                with transaction.atomic():
                    result = core.run(
                        'mosh_works_scores', user_text, scores.SCHEMA, None,
                        provider=provider, model=scores.MODEL, system=scores.SYSTEM,
                        images=[('image/png', png)], log=False, check_limit=False,
                        check_budget=False, cache_seconds=0, timeout=120,
                        parse=scores.tolerant_parse, max_tokens=4000)
                return rec, rel, result.data, result.usage.get('cost_usd', 0.0), None
            except core.AiUnavailable as error:
                return rec, rel, None, 0.0, str(error)[:200]
            finally:
                connection.close()

        def record(rec, rel, data, cost, status, details, extra=None):
            prev = rows.get(rec['work_id'], {})
            row = {'work_id': rec['work_id'], 'year': rec['year'], 'scores_status': status,
                   'reason': details.get('reason', ''), 'tasks': details.get('tasks'),
                   'tasks_sum': details.get('tasks_sum'), 'total_read': details.get('total_read'),
                   'total_listed': rec['total_listed'], 'appeal_delta': details.get('appeal_delta'),
                   'verified_by': details.get('verified_by'),
                   'merged_1_5': details.get('merged_1_5'), 'missing': details.get('missing'),
                   'source': 'model', 'runs': (prev.get('runs') or 0) + 1, 'crop': rel,
                   'cost': round((prev.get('cost') or 0) + cost, 6),
                   'raw': None if status == 'ok' else data}
            row.update(extra or {})
            rows[rec['work_id']] = row

        spent, done, errors_in_row, stopped = 0.0, 0, 0, ''
        workers = int(os.environ.get('MOSH_WORKS_WORKERS', '6'))
        queue = list(todo)
        total_calls = len(queue)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            running = set()
            while queue or running:
                while queue and len(running) < workers and not stopped:
                    if spent_before + spent >= opts['max_usd']:
                        stopped = 'потолок $%.2f достигнут' % opts['max_usd']
                        break
                    running.add(pool.submit(call, queue.pop(0)))
                if not running:
                    break
                finished = next(iter(_wait_first(running)))
                running.discard(finished)
                rec, rel, data, cost, error = finished.result()
                spent += cost
                done += 1
                if error:
                    errors_in_row += 1
                    record(rec, rel, None, cost, 'review', {'reason': 'ai_error'},
                           {'error': error})
                    if errors_in_row >= 10 and not stopped:
                        stopped = '10 сбоев модели подряд'
                else:
                    errors_in_row = 0
                    status, details = scores.verdict(data, rec['total_listed'])
                    if retry and status != 'ok' and not rec.get('_rot'):
                        # Тот же вырез не помог — один раз повёрнутый на 180°.
                        record(rec, rel, data, cost, 'review', details, {'retried': False})
                        rec['_rot'] = True
                        queue.append(rec)
                    else:
                        record(rec, rel, data, cost, status, details,
                               {'retried': True} if retry else None)
                        rec.pop('_rot', None)
                if done % 20 == 0:
                    self._save_scores(data_dir, rows)
                    self.say('  вызовов %d, $%.4f' % (done, spent))
                if stopped and queue:
                    queue.clear()
        self._save_scores(data_dir, rows)
        self._write_review(data_dir, rows)
        got = Counter(r['scores_status'] for r in rows.values())
        self.say()
        if stopped:
            self.say('ОСТАНОВЛЕНО: %s' % stopped)
        self.say('вызовов %d из %d плановых, потрачено $%.4f' % (done, total_calls, spent))
        self.say('итого в scores.jsonl: %s' % dict(got))
        with open(os.path.join(data_dir, 'scores_runs.jsonl'), 'a', encoding='utf-8') as fh:
            fh.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'calls': done,
                                 'spent_usd': round(spent, 6), 'stopped': stopped,
                                 'statuses': dict(got)}, ensure_ascii=False) + '\n')
        return None

    def _write_review(self, data_dir, rows):
        import csv

        with open(os.path.join(data_dir, 'review.csv'), 'w', encoding='utf-8-sig',
                  newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['work_id', 'year', 'reason', 'crop', 'read_tasks', 'tasks_sum',
                        'total_read', 'total_listed', 'appeal_delta'])
            for r in sorted(rows.values(), key=lambda x: x['work_id']):
                if r.get('scores_status') == 'review':
                    w.writerow([r['work_id'], r['year'], r.get('reason'), r.get('crop', ''),
                                json.dumps(r.get('tasks'), ensure_ascii=False),
                                r.get('tasks_sum'), r.get('total_read'), r.get('total_listed'),
                                r.get('appeal_delta')])

    # ------------------------------------------------------------ report
    def do_report(self, data_dir, opts):
        records = read_jsonl(os.path.join(data_dir, 'index.jsonl'))
        total = Counter(r.get('status') or 'pending' for r in records)
        gb = sum(r.get('zip_bytes', 0) for r in records if r.get('status') == 'ok') / 1e9
        self.say('в списках %d; скачано %d; не скачалось %d; не трогали %d; %.2f ГБ'
                 % (len(records), total['ok'], total['failed'], total['pending'], gb))
        sc = self._read_scores(data_dir)
        by = Counter((r['year'], sc.get(r['work_id'], {}).get('scores_status', 'не читались'))
                     for r in records)
        for year in sorted({r['year'] for r in records}):
            self.say('  %d: %s' % (year, {k[1]: n for k, n in sorted(by.items()) if k[0] == year}))
        return None


def _wait_first(futures):
    from concurrent.futures import FIRST_COMPLETED, wait

    done, _ = wait(futures, return_when=FIRST_COMPLETED)
    return done
