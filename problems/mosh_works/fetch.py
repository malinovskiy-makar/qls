"""Скачивание zip по index, распаковка, докачка. Без Django — клиент и сон подменяемы.

Вежливость к чужим серверам — в общем клиенте ВП (`vp_works.hse.Client`):
не чаще 1 запроса в секунду НА ВСЁ (один экземпляр клиента на оба хоста —
reg.cpm.moscow и reg.olimpiada.ru), понятный User-Agent, повторы 5/15/45 с,
403/429/капча → `Blocked` (команда останавливается, а не обходит).

Адреса zip — ТОЛЬКО из index (то есть из ссылок таблицы). Здесь их не
строят и не подбирают.
"""
import os
import re
import time
import urllib.request
import zipfile
from zlib import error as zlib_error

from problems.vp_works import hse

from . import listing, scans

#: Хосты, на которые клиент вообще ходит. Всё остальное — отказ до запроса.
ALLOWED_HOSTS = ('reg.cpm.moscow', 'reg.olimpiada.ru')

#: Допустимое имя файла в zip: плоское, латиница/цифры/точка/дефис/подчёркивание.
MEMBER_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(pdf|jpg|jpeg|png)$', re.I)
MAX_MEMBER_BYTES = 200 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024

FAIL_STREAK = 20
STREAK_PAUSE = 600
MAX_STREAK_PAUSES = 3


class Client(hse.Client):
    """Тот же вежливый клиент, но GET чужого адреса (с проверкой хоста)."""

    def get(self, url, expect='html'):
        host = re.match(r'^https://([^/]+)/', url or '')
        if not host or host.group(1) not in ALLOWED_HOSTS:
            raise ValueError('Хост не из списка разрешённых: %r' % (url or '')[:80])

        def make_request():
            return urllib.request.Request(url, headers={'User-Agent': hse.USER_AGENT})
        return self.fetch(make_request, host.group(1) + ' ' + url.rsplit('/', 1)[-1],
                          expect, fatal=(404, 410))


# ------------------------------------------------------------------ пути

def zip_relpath(rec):
    return 'zip/%d/%s.zip' % (rec['year'], rec['work_id'])


def scan_relpath(rec):
    return 'scans/%d/%s' % (rec['year'], rec['work_id'])


# ------------------------------------------------------------------ zip

def zip_ok(path):
    """Есть, не пустой, настоящий zip, все члены читаются (testzip)."""
    try:
        if os.path.getsize(path) <= 0:
            return False
        with zipfile.ZipFile(path) as zf:
            return bool(zf.namelist()) and zf.testzip() is None
    except (OSError, zipfile.BadZipFile, zlib_error):
        return False


EXTENSIONS = ('pdf', 'jpg', 'jpeg', 'png')


def member_plan(name):
    """Что делать с членом zip: ('keep'|'rename'|'skip', причина).

    Путь с каталогами, `..`, диском или точкой в начале — пропуск (zip-slip).
    Расширение не из списка — пропуск. Имя «странное» (пробелы, кириллица —
    встретилось у настоящей работы 2021), но безопасное — распаковывается под
    нейтральным именем `fNNN.<расширение>`: имя файла могло бы нести то, чего
    в нашей папке быть не должно.
    """
    if not name or name.endswith('/'):
        return 'skip', 'каталог'
    if '/' in name or '\\' in name or '..' in name or ':' in name or name.startswith('.'):
        return 'skip', 'путь выходит за папку или не плоский'
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in EXTENSIONS:
        return 'skip', 'расширение не из списка'
    if MEMBER_RE.match(name):
        return 'keep', ''
    return 'rename', 'странное имя'


def extract_safe(zip_path, dest_dir, log=None):
    """Распаковать безопасные члены. Возвращает {'files': n, 'renamed': n, 'skipped': [причины]}.

    Файлы НЕ исполняются. Имена в журнал не пишем — только причину.
    """
    os.makedirs(dest_dir, exist_ok=True)
    base = os.path.realpath(dest_dir)
    written, renamed, skipped, total = 0, 0, [], 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            action, reason = member_plan(info.filename)
            if action == 'skip' and info.is_dir():
                continue
            if action != 'skip' and (info.file_size > MAX_MEMBER_BYTES
                                     or total + info.file_size > MAX_TOTAL_BYTES):
                action, reason = 'skip', 'слишком большой'
            if action == 'skip':
                skipped.append(reason)
                if log:
                    log('  пропущен член zip: %s' % reason)
                continue
            if action == 'rename':
                renamed += 1
                name = 'f%03d.%s' % (renamed, info.filename.rsplit('.', 1)[-1].lower())
                if log:
                    log('  член zip переименован: %s' % reason)
            else:
                name = info.filename
            target = os.path.realpath(os.path.join(dest_dir, name))
            if not target.startswith(base + os.sep):
                skipped.append('путь выходит за папку')
                continue
            total += info.file_size
            with zf.open(info) as src, open(target, 'wb') as dst:
                dst.write(src.read())
            written += 1
    return {'files': written, 'renamed': renamed, 'skipped': skipped}


def sha256_of(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------------ прогон

def _fill(rec, data_dir, analyze=True, log=None):
    """Сведения о скачанном zip и распакованных сканах → строка index.

    Битый zip — failed, не ok. Анализ первой страницы не роняет прогон:
    его сбой записывается в `analysis_error`.
    """
    zrel, srel = zip_relpath(rec), scan_relpath(rec)
    zpath, sdir = os.path.join(data_dir, zrel), os.path.join(data_dir, srel)
    if not zip_ok(zpath):
        rec.update({'zip_path': zrel, 'status': 'failed', 'reason': 'zip не открывается или битый'})
        return
    try:
        # Распаковка дошла до конца, если файлов на диске ровно столько, сколько
        # в zip безопасных членов; иначе (прерванный запуск) — заново.
        with zipfile.ZipFile(zpath) as zf:
            expected = sum(1 for i in zf.infolist()
                           if not i.is_dir() and member_plan(i.filename)[0] != 'skip')
        if len(sum(scans.list_scan_files(sdir), [])) != expected:
            result = extract_safe(zpath, sdir, log=log)
            rec['skipped_members'] = len(result['skipped'])
        files = len(sum(scans.list_scan_files(sdir), []))
        if files == 0:
            rec.update({'zip_path': zrel, 'status': 'failed', 'reason': 'в zip нет сканов'})
            return
        rec.update({'zip_path': zrel, 'zip_bytes': os.path.getsize(zpath),
                    'sha256': sha256_of(zpath), 'files': files,
                    'pages': scans.count_pages(sdir), 'status': 'ok', 'reason': ''})
    except (OSError, zipfile.BadZipFile) as error:
        rec.update({'zip_path': zrel, 'status': 'failed', 'reason': str(error)[:300]})
        return
    if analyze and 'stickers_pct' not in rec:
        try:
            info = scans.analyze(sdir)
            rec.update(info)
            rec.pop('analysis_error', None)
        except Exception as error:  # noqa: BLE001 — анализ не должен ронять скачивание
            rec['analysis_error'] = '%s: %s' % (type(error).__name__, str(error)[:200])


def download_all(records, data_dir, client, *, limit=0, log=print, sleep=time.sleep,
                 save=None, save_every=10, stop_after_fails=0):
    """Пройти index и скачать недостающее. Возвращает счётчики.

    Докачка: zip на месте и целый (`zip_ok`) — заново НЕ качается, у него
    только досчитываются сведения. Прерванный запуск продолжается с места
    остановки. `hse.Blocked` не ловится: вызывающий сохраняет и останавливается.
    """
    stats = {'downloaded': 0, 'skipped_existing': 0, 'failed': 0, 'pauses': 0}
    streak = attempted = 0
    try:
        for rec in records:
            zpath = os.path.join(data_dir, zip_relpath(rec))
            if not rec.get('zip_url'):
                rec.update({'zip_path': None, 'status': 'failed', 'reason': 'нет ссылки на zip в таблице'})
                stats['failed'] += 1
                continue
            if zip_ok(zpath):
                stats['skipped_existing'] += 1
                if rec.get('status') != 'ok' or 'stickers_pct' not in rec:
                    _fill(rec, data_dir, log=log)
                continue
            if limit and attempted >= limit:
                continue
            attempted += 1
            os.makedirs(os.path.dirname(zpath), exist_ok=True)
            try:
                body = client.get(rec['zip_url'], expect='zip')
                tmp = zpath + '.part'
                with open(tmp, 'wb') as fh:
                    fh.write(body)
                os.replace(tmp, zpath)
                _fill(rec, data_dir, log=log)
            except hse.SiteError as error:
                rec.update({'zip_path': None, 'status': 'failed', 'reason': str(error)[:300]})
            if rec.get('status') == 'ok':
                stats['downloaded'] += 1
                streak = 0
            else:
                stats['failed'] += 1
                streak += 1
                log('  не скачалось %s: %s' % (rec['work_id'], rec.get('reason')))
                if stop_after_fails and streak >= stop_after_fails:
                    log('СТОП: %d неудач подряд — сайт не отвечает, выхожу.' % streak)
                    stats['stopped'] = 'site_down'
                    break
                if streak >= FAIL_STREAK:
                    if stats['pauses'] >= MAX_STREAK_PAUSES:
                        log('СТОП: %d неудач подряд после %d пауз.' % (streak, MAX_STREAK_PAUSES))
                        stats['stopped'] = 'fail_streak'
                        break
                    stats['pauses'] += 1
                    log('%d неудач подряд — пауза %d с (%d/%d)'
                        % (streak, STREAK_PAUSE, stats['pauses'], MAX_STREAK_PAUSES))
                    sleep(STREAK_PAUSE)
                    streak = 0
            if save and attempted and attempted % save_every == 0:
                save(records)
                log('  скачано %d, ошибок %d, уже было %d'
                    % (stats['downloaded'], stats['failed'], stats['skipped_existing']))
    finally:
        if save:
            save(records)
    return stats


def check_download(records, data_dir):
    """Инварианты Фазы 3: ok + failed = строк; у ok zip валиден."""
    ok = [r for r in records if r.get('status') == 'ok']
    failed = [r for r in records if r.get('status') == 'failed']
    pending = len(records) - len(ok) - len(failed)
    bad_ok = [r['work_id'] for r in ok if not zip_ok(os.path.join(data_dir, r['zip_path']))]
    return {'ok': len(ok), 'failed': len(failed), 'pending': pending, 'ok_bad_zip': bad_ok,
            'bytes': sum(r.get('zip_bytes', 0) for r in ok)}
