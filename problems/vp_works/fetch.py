"""Скачивание PDF по index с докачкой. Без Django — клиент и сон подменяемы.

Докачка: файл, который уже лежит на месте (есть, не пустой, начинается с
%PDF), заново НЕ качается — у него только досчитываются сведения. Файл
пишется во временный `.part` и подменяется целиком, так что прерванный
запуск не оставляет полуфайла под настоящим именем.
"""
import os
import time

from . import hse, pdfwork

#: Серия неудач подряд, после которой — пауза (сервер ночью шаткий).
FAIL_STREAK = 20
STREAK_PAUSE = 600
MAX_STREAK_PAUSES = 3


def download_all(records, data_dir, client, *, limit=0, log=print,
                 sleep=time.sleep, save=None, save_every=10, stop_after_fails=0):
    """Пройти index и скачать недостающее. Возвращает счётчики.

    `save(records)` зовётся каждые `save_every` файлов и в конце — чтобы
    прерванный ночью прогон не потерял сведения о скачанном.
    `hse.Blocked` не ловится: вызывающий сохраняет и останавливается.
    `stop_after_fails=N` — после N неудач подряд выйти (сайт лёг), не
    тратя часы на повторы; ждёт и перезапускает внешний цикл.
    """
    stats = {'downloaded': 0, 'skipped_existing': 0, 'failed': 0, 'pauses': 0}
    streak = 0
    attempted = 0
    try:
        for rec in records:
            rel = pdfwork.pdf_relpath(rec)
            path = os.path.join(data_dir, rel)
            if pdfwork.looks_like_pdf(path):
                stats['skipped_existing'] += 1
                if rec.get('status') != 'ok' or rec.get('pdf_path') != rel:
                    _fill(rec, path, rel)
                continue
            if limit and attempted >= limit:
                continue
            attempted += 1
            os.makedirs(os.path.dirname(path), exist_ok=True)
            try:
                body = client.work_pdf(rec['work_id'])
                tmp = path + '.part'
                with open(tmp, 'wb') as fh:
                    fh.write(body)
                os.replace(tmp, path)
                _fill(rec, path, rel)
            except hse.SiteError as error:
                rec.update({'pdf_path': None, 'status': 'failed',
                            'reason': str(error)[:300]})
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
                        log('СТОП: %d неудач подряд после %d пауз.'
                            % (streak, MAX_STREAK_PAUSES))
                        stats['stopped'] = 'fail_streak'
                        break
                    stats['pauses'] += 1
                    log('%d неудач подряд — пауза %d с (%d/%d)'
                        % (streak, STREAK_PAUSE, stats['pauses'], MAX_STREAK_PAUSES))
                    sleep(STREAK_PAUSE)
                    streak = 0
            if save and attempted % save_every == 0:
                save(records)
                log('  скачано %d, ошибок %d, уже было %d'
                    % (stats['downloaded'], stats['failed'], stats['skipped_existing']))
    finally:
        if save:
            save(records)
    return stats


def _fill(rec, path, rel):
    """Сведения о файле в строку index; битый файл — failed, не ok."""
    try:
        info = pdfwork.pdf_info(path)
    except ValueError as error:
        rec.update({'pdf_path': rel, 'status': 'failed', 'reason': str(error)[:300]})
        return
    rec.update({'pdf_path': rel, 'status': 'ok', 'reason': ''})
    rec.update(info)


def check_download(records, data_dir):
    """Инварианты Фазы 3."""
    ok = [r for r in records if r.get('status') == 'ok']
    failed = [r for r in records if r.get('status') == 'failed']
    pending = len(records) - len(ok) - len(failed)
    bad_ok = [r['work_id'] for r in ok
              if not pdfwork.looks_like_pdf(os.path.join(data_dir, r['pdf_path']))]
    return {'ok': len(ok), 'failed': len(failed), 'pending': pending,
            'ok_not_pdf': bad_ok,
            'bytes': sum(r.get('bytes', 0) for r in ok)}
