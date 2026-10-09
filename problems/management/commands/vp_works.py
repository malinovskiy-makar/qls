"""Работы победителей и призёров «Высшей пробы»: списки, PDF, баллы по задачам.

    manage.py vp_works index    --dir D [--subjects economics,fingram,business]
    manage.py vp_works download --dir D [--limit N]
    manage.py vp_works scores   --dir D [--limit N] [--max-usd 3.00] [--yes]
    manage.py vp_works report   --dir D

Все файлы — ВНЕ репозитория, в `--dir`. В базу команда не пишет ни строки.
ФИО участников не хранятся нигде: участник — номер работы. Подробности —
docs/VP_WORKS.md.
"""
import json
import os
from collections import Counter
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from problems.vp_works import fetch, hse, listing, pdfwork, scores

DEFAULT_DIR = r'C:\Users\shipu\weconomics-data\vp_works'


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def only_ids(arg):
    """`--only 1,2,3` или `--only @файл` → множество work_id (пусто — все)."""
    arg = (arg or '').strip()
    if arg.startswith('@'):
        with open(arg[1:], encoding='utf-8') as fh:
            arg = fh.read().replace('\n', ',')
    return {w.strip() for w in arg.split(',') if w.strip()}


def load_records(data_dir):
    """index.jsonl + результаты баллов из scores.jsonl (по work_id).

    Баллы живут ОТДЕЛЬНЫМ файлом: download (часы) и scores могут идти
    одновременно, а index пишет только download — иначе два процесса
    затирали бы поля друг друга.
    """
    records = read_jsonl(os.path.join(data_dir, 'index.jsonl'))
    extra = {r['work_id']: r for r in read_jsonl(os.path.join(data_dir, 'scores.jsonl'))}
    for rec in records:
        rec.update({k: v for k, v in extra.get(rec['work_id'], {}).items()
                    if k.startswith('scores_')})
    return records


def save_scores(data_dir, records):
    rows = [dict({'work_id': r['work_id']},
                 **{k: v for k, v in r.items() if k.startswith('scores_')})
            for r in records if r.get('scores_status')]
    write_jsonl(os.path.join(data_dir, 'scores.jsonl'), rows)


def write_jsonl(path, rows):
    """Атомарно: сначала во временный файл, потом подмена."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


class Command(BaseCommand):
    help = 'Работы победителей и призёров ВП: index / download / scores / report.'

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        for name in ('index', 'download', 'scores', 'report'):
            p = sub.add_parser(name)
            p.add_argument('--dir', default=DEFAULT_DIR,
                           help='папка данных вне репозитория')
            if name == 'index':
                p.add_argument('--subjects', default='economics,fingram,business')
                p.add_argument('--seasons', default='',
                               help='только эти сезоны, через запятую: 2019/2020,…')
            if name in ('download', 'scores'):
                p.add_argument('--limit', type=int, default=0)
                p.add_argument('--only', default='',
                               help='work_id через запятую или @файл (по строке на номер)')
            if name == 'scores':
                p.add_argument('--max-usd', type=float, default=3.0)
                p.add_argument('--yes', action='store_true',
                               help='без него — только план, ни одного вызова модели')

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
        try:
            subjects = listing.parse_subjects(opts['subjects'])
        except ValueError as error:
            raise CommandError(str(error))
        only_seasons = {s.strip() for s in (opts.get('seasons') or '').split(',') if s.strip()}
        client = client or hse.Client(log=self.say)
        path = os.path.join(data_dir, 'index.jsonl')
        old = {r['work_id']: r for r in read_jsonl(path)}
        listed_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        records, volume = [], Counter()
        for season_row in client.seasons():
            season = listing.season_label(season_row.get('OlympLearnYear-D', ''))
            if only_seasons and season not in only_seasons:
                continue
            season_id = season_row['ID']
            round_ids = client.round_ids(season_id)
            if not round_ids:
                self.say('%s: туров нет' % season)
                continue
            present = set(client.subjects(round_ids))
            for slug, name in subjects:
                if name not in present:
                    self.say('%s · %s: предмета в этом сезоне нет' % (season, slug))
                    continue
                for grade_row in client.grades(round_ids, name):
                    label = grade_row.get('Master-N', '')
                    grade = listing.grade_number(label)
                    for degree in (1, 2, 3):
                        rows = client.winners(season_id, label, name, degree)
                        for rank, row in enumerate(rows, 1):
                            rec = listing.winner_record(
                                row, rank=rank, subject=slug, season=season,
                                grade=grade, degree=degree,
                                source_url=hse.work_source_url(row.get('ID', '0') or '0'),
                                listed_at=listed_at)
                            # Поля скачивания и баллов, если уже были, сохраняем.
                            prev = old.get(rec['work_id'], {})
                            rec.update({k: v for k, v in prev.items()
                                        if k not in listing.INDEX_FIELDS})
                            records.append(rec)
                        volume[(season, slug, grade, degree)] += len(rows)
                        self.say('%s · %s · %d кл · %d ст.: %d'
                                 % (season, slug, grade, degree, len(rows)))

        write_jsonl(path, records)
        vol_rows = [{'season': s, 'subject': sj, 'grade': g, 'degree': d, 'works': n}
                    for (s, sj, g, d), n in sorted(volume.items())]
        write_jsonl(os.path.join(data_dir, 'volume.jsonl'), vol_rows)
        check = listing.check_index(records, expected_total=sum(volume.values()))
        self.say()
        self.say('index.jsonl: %d строк, сумма таблицы объёма %d'
                 % (check['rows'], sum(volume.values())))
        self.say('повторов work_id: %d; без балла: %d; балл после < до: %d'
                 % (check['duplicates'], check['no_score'], len(check['after_lower'])))
        for line in check['problems']:
            self.say('  нарушение: ' + line)
        if check['after_lower']:
            self.say('  после < до: ' + ', '.join(check['after_lower'][:20]))
        self.say('запросов к сайту: %d' % client.requests)
        return None

    # ---------------------------------------------------------- download
    def do_download(self, data_dir, opts, client=None, sleep=None):
        path = os.path.join(data_dir, 'index.jsonl')
        records = read_jsonl(path)
        if not records:
            raise CommandError('index.jsonl пуст — сначала vp_works index.')
        client = client or hse.Client(log=self.say)
        kwargs = {'sleep': sleep} if sleep else {}
        wanted = only_ids(opts.get('only'))
        batch = [r for r in records if r['work_id'] in wanted] if wanted else records
        try:
            # Сохраняем ВЕСЬ index, даже когда качаем часть (`--only`).
            stats = fetch.download_all(
                batch, data_dir, client, limit=opts.get('limit') or 0,
                log=self.say, save=lambda _rows: write_jsonl(path, records), **kwargs)
        except hse.Blocked:
            self.say('Сайт отказал — index сохранён, докачка продолжит с места.')
            raise
        check = fetch.check_download(records, data_dir)
        self.say()
        self.say('скачано сейчас %d, уже было %d, ошибок %d, пауз %d'
                 % (stats['downloaded'], stats['skipped_existing'], stats['failed'],
                    stats['pauses']))
        self.say('ok %d + failed %d + не трогали %d = %d строк index'
                 % (check['ok'], check['failed'], check['pending'], len(records)))
        self.say('ok, но не PDF: %d; объём ok: %.2f ГБ'
                 % (len(check['ok_not_pdf']), check['bytes'] / 1e9))
        return None

    # ------------------------------------------------------------ scores
    def do_scores(self, data_dir, opts, provider=None):
        import random
        from concurrent.futures import ThreadPoolExecutor

        records = load_records(data_dir)
        spent_before = sum(r.get('scores_cost') or 0 for r in records)
        todo = [r for r in records if r.get('status') == 'ok'
                and r.get('scores_status') not in ('ok', 'review')]
        wanted = only_ids(opts.get('only'))
        if wanted:
            todo = [r for r in todo if r['work_id'] in wanted]
        if opts.get('limit'):
            # Проба — случайная, но воспроизводимая, из разных сезонов.
            todo = random.Random(20261009).sample(todo, min(opts['limit'], len(todo)))

        text_layer = [r for r in todo if r.get('has_text_layer')]
        no_layout = [r for r in todo if not r.get('has_text_layer')
                     and scores.layout_for(r['season']) is None]
        to_model = [r for r in todo if not r.get('has_text_layer')
                    and scores.layout_for(r['season']) is not None]

        self.say('работ к разбору: %d; с текстовым слоем: %d; без раскладки бланка: %d; '
                 'в модель: %d' % (len(todo), len(text_layer), len(no_layout), len(to_model)))
        self.say('смета: ~$%.2f; уже потрачено прежними прогонами $%.4f; потолок на все '
                 'прогоны $%.2f' % (scores.estimate_usd(len(to_model)), spent_before,
                                     opts['max_usd']))

        for rec in text_layer + no_layout:
            # Путь (а) у ВП не встретился ни разу (сканы без текста) — такие
            # работы честно уходят в очередь, а не угадываются.
            rec.update({'scores_status': 'review',
                        'scores_reason': 'text_layer' if rec.get('has_text_layer')
                        else 'no_layout'})

        crops_dir = os.path.join(data_dir, 'crops')
        for rec in to_model:
            rec['scores_crop'] = self._save_crop(data_dir, crops_dir, rec)

        if not opts.get('yes'):
            self.say('ПЛАН. Без --yes модель не вызывается. Вырезы сохранены в %s'
                     % crops_dir)
            return None
        if text_layer or no_layout:
            save_scores(data_dir, records)

        from django.conf import settings
        from django.db import connection, transaction

        from problems.ai import core, providers

        provider = provider or providers.get_provider(
            getattr(settings, 'VP_WORKS_PROVIDER', 'glm'))
        if not provider.is_available():
            raise CommandError('Модель недоступна: %s' % provider.unavailable_reason())

        def call(rec):
            with open(os.path.join(data_dir, rec['scores_crop']), 'rb') as fh:
                png = fh.read()
            user_text = ('Работа %s, сезон %s. Перепиши баллы из таблички.'
                         % (rec['work_id'], rec['season']))
            try:
                # ⚠️ atomic: при отказе поставщика core.run пишет строку
                # AiUsageLog даже с log=False (известный баг, карточка в
                # Notion). Исключение откатывает её — сессия в базу не пишет.
                with transaction.atomic():
                    result = core.run(
                        'vp_works_scores', user_text, scores.SCHEMA, None,
                        provider=provider, model=scores.MODEL, system=scores.SYSTEM,
                        images=[('image/png', png)], log=False, check_limit=False,
                        check_budget=False, cache_seconds=0, timeout=120,
                        parse=scores.tolerant_parse, max_tokens=4000)
                return rec, result.data, result.usage.get('cost_usd', 0.0), None
            except core.AiUnavailable as error:
                return rec, None, 0.0, str(error)[:200]
            finally:
                connection.close()

        spent, done, errors_in_row = 0.0, 0, 0
        stopped = ''
        workers = int(os.environ.get('VP_WORKS_WORKERS', '6'))
        queue = list(to_model)
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
                rec, data, cost, error = finished.result()
                spent += cost
                done += 1
                if error:
                    errors_in_row += 1
                    rec.update({'scores_status': 'review', 'scores_reason': 'ai_error',
                                'scores_error': error})
                    if errors_in_row >= 10 and not stopped:
                        stopped = '10 сбоев модели подряд'
                else:
                    errors_in_row = 0
                    status, details = scores.verdict(data, rec.get('score_before'))
                    rec.update({'scores_status': status,
                                'scores_reason': details.get('reason', ''),
                                'scores_tasks': details.get('tasks'),
                                'scores_sum': details.get('sum'),
                                'scores_model_total': details.get('model_total'),
                                'scores_raw': None if status == 'ok' else data,
                                'scores_cost': round(cost, 6)})
                if done % 20 == 0:
                    save_scores(data_dir, records)
                    self.say('  разобрано %d из %d, $%.4f' % (done, len(to_model), spent))
                if stopped and queue:
                    queue.clear()
        save_scores(data_dir, records)
        self._write_review(data_dir, records)
        batch = [r for r in to_model if r.get('scores_status')]
        ok = sum(1 for r in batch if r['scores_status'] == 'ok')
        self.say()
        if stopped:
            self.say('ОСТАНОВЛЕНО: %s' % stopped)
        self.say('вызовов %d, ok %d (%.0f %%), review %d, потрачено $%.4f'
                 % (done, ok, 100.0 * ok / max(len(batch), 1), len(batch) - ok, spent))
        with open(os.path.join(data_dir, 'scores_runs.jsonl'), 'a', encoding='utf-8') as fh:
            fh.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'calls': done,
                                 'ok': ok, 'spent_usd': round(spent, 6),
                                 'stopped': stopped}, ensure_ascii=False) + '\n')
        return None

    def _save_crop(self, data_dir, crops_dir, rec):
        rel = os.path.join('crops', rec['season'].replace('/', '_'),
                           '%s_%s.png' % (rec['subject'], rec['work_id']))
        out = os.path.join(data_dir, rel)
        if not os.path.exists(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            image = pdfwork.render_page(os.path.join(data_dir, rec['pdf_path']), 0, dpi=150)
            crop = scores.crop_scores(image, scores.layout_for(rec['season']))
            with open(out, 'wb') as fh:
                fh.write(scores.png_bytes(crop))
        return rel

    def _write_review(self, data_dir, records):
        import csv

        with open(os.path.join(data_dir, 'review.csv'), 'w', encoding='utf-8-sig',
                  newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['work_id', 'season', 'subject', 'grade', 'reason', 'crop',
                        'read_tasks', 'read_sum', 'model_total', 'expected_score_before'])
            for r in records:
                if r.get('scores_status') == 'review':
                    w.writerow([r['work_id'], r['season'], r['subject'], r['grade'],
                                r.get('scores_reason'), r.get('scores_crop', ''),
                                json.dumps(r.get('scores_tasks'), ensure_ascii=False),
                                r.get('scores_sum'), r.get('scores_model_total'),
                                r.get('score_before')])

    # ------------------------------------------------------------ report
    def do_report(self, data_dir, opts):
        records = load_records(data_dir)
        by = Counter()
        for r in records:
            by[(r['subject'], r['season'], 'listed')] += 1
            by[(r['subject'], r['season'], r.get('status') or 'pending')] += 1
            by[(r['subject'], r['season'], 'scores_' + (r.get('scores_status') or 'none'))] += 1
        out = os.path.join(data_dir, 'summary.json')
        rows = [{'subject': s, 'season': y, 'what': w, 'n': n}
                for (s, y, w), n in sorted(by.items())]
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        total = Counter(r.get('status') or 'pending' for r in records)
        sc = Counter(r.get('scores_status') or 'none' for r in records)
        gb = sum(r.get('bytes', 0) for r in records if r.get('status') == 'ok') / 1e9
        self.say('в списках %d; скачано %d; не скачалось %d; не трогали %d; %.2f ГБ'
                 % (len(records), total['ok'], total['failed'], total['pending'], gb))
        self.say('баллы по задачам: ok %d, review %d, не читались %d'
                 % (sc['ok'], sc['review'], sc['none']))
        self.say('сводка по предметам и сезонам: %s' % out)
        return None


def _wait_first(futures):
    from concurrent.futures import FIRST_COMPLETED, wait

    done, _ = wait(futures, return_when=FIRST_COMPLETED)
    return done
