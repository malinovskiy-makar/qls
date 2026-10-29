# -*- coding: utf-8 -*-
"""Справочник школ ← реестр Рособрнадзора: скачать, сравнить, обновить (раунд 3, 29.10.2026).

Общий движок двух команд: `load_schools --format raoo <файл>` (файл уже на диске) и
`sync_schools` (сама скачивает свежий архив; на бою — раз в неделю таймером
`deploy/systemd/weconomics-schools.timer`).

Правила обновления:
* ключ — идентификатор организации в реестре (`registry_id`); если его в таблице нет,
  а ИНН + КПП совпали ровно с одной школой, которой в новом файле нет, — это та же
  школа под новым идентификатором (обновляем, а не плодим);
* новые добавляются, изменённые правятся, исчезнувшие из файла ВЫКЛЮЧАЮТСЯ
  (`is_active=False`), а не удаляются;
* всё — одной транзакцией: при любом сбое таблица остаётся как была;
* предохранитель: файл, в котором школ меньше половины от уже действующих в таблице,
  считается битым и не применяется (иначе обрыв выгрузки выключил бы полстраны).

Строки, залитые из CSV (`registry_id` пуст), синхронизация не трогает.
"""
import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from django.db import transaction

from problems import school_registry

logger = logging.getLogger(__name__)

#: Поля, которые синхронизация сверяет и правит.
SYNC_FIELDS = ('name', 'short_name', 'number', 'city', 'region', 'inn', 'kpp', 'is_branch',
               'is_active')
BATCH = 1000
#: Меньше этой доли от действующих школ из реестра — файл битый, не применяем.
MIN_SHARE = 0.5
#: Ожидание ответа сервера и попытки скачивания.
TIMEOUT = 60
ATTEMPTS = 3
#: Меньше — не архив реестра (страница ошибки, обрыв).
MIN_BYTES = 1024 * 1024


class SyncError(Exception):
    """Сбой синхронизации; данные не тронуты. Текст — простыми словами."""


def apply_rows(rows, *, apply):
    """rows: {registry_id: поля School} → счётчики {total, added, changed, deactivated}.

    `apply=False` — только посчитать. Пишет одной транзакцией.
    """
    from problems.models import School

    existing = {s.registry_id: s for s in School.objects.exclude(registry_id='')}
    active_before = sum(1 for s in existing.values() if s.is_active)
    if active_before and len(rows) < MIN_SHARE * active_before:
        raise SyncError('в файле %d школ, а в таблице %d действующих — файл похож на битый, '
                        'ничего не меняю' % (len(rows), active_before))

    # ИНН + КПП → школа, которой в новом файле нет (кандидат «та же под новым id»).
    gone = {key: s for key, s in existing.items() if key not in rows}
    by_inn_kpp = {}
    for school in gone.values():
        if school.inn and school.kpp:
            by_inn_kpp.setdefault((school.inn, school.kpp), []).append(school)

    to_create, to_update = [], []
    for key, fields in rows.items():
        school = existing.get(key)
        if school is None and fields['inn'] and fields['kpp']:
            same = by_inn_kpp.get((fields['inn'], fields['kpp'])) or []
            if len(same) == 1:
                school = same[0]
                gone.pop(school.registry_id, None)
                by_inn_kpp.pop((fields['inn'], fields['kpp']), None)
                school.registry_id = key
                _set(school, fields)
                to_update.append(school)
                continue
        if school is None:
            new = School(registry_id=key, is_active=True,
                         **{f: v for f, v in fields.items() if f in SYNC_FIELDS})
            new.fill_norms()
            to_create.append(new)
        elif _set(school, fields):
            to_update.append(school)

    to_deactivate = [s for s in gone.values() if s.is_active]
    counts = {'total': len(rows), 'added': len(to_create), 'changed': len(to_update),
              'deactivated': len(to_deactivate)}
    if not apply:
        return counts
    with transaction.atomic():
        School.objects.bulk_create(to_create, batch_size=BATCH)
        if to_update:
            School.objects.bulk_update(
                to_update, list(SYNC_FIELDS) + ['registry_id', 'city_norm', 'name_norm'],
                batch_size=BATCH)
        ids = [s.pk for s in to_deactivate]
        for start in range(0, len(ids), BATCH):
            School.objects.filter(pk__in=ids[start:start + BATCH]).update(is_active=False)
    return counts


def _set(school, fields):
    """Перенести поля реестра в школу; True — если что-то поменялось."""
    changed = False
    for name in SYNC_FIELDS:
        value = True if name == 'is_active' else fields.get(name, getattr(school, name))
        if getattr(school, name) != value:
            setattr(school, name, value)
            changed = True
    if changed:
        school.fill_norms()
    return changed


# ── Скачивание ─────────────────────────────────────────────────────────────

def _request(url, method='GET'):
    """Ответ сервера (файловый объект с заголовками). Подменяется в тестах."""
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise SyncError('адрес реестра обязан быть https://')
    request = urllib.request.Request(url, method=method,
                                     headers={'User-Agent': 'weconomics-sync-schools'})
    return urllib.request.urlopen(request, timeout=TIMEOUT)  # nosec B310 — только https, проверено выше


def remote_info(url):
    """(имя файла, размер) свежего архива по заголовкам, без скачивания."""
    try:
        with _request(url, method='HEAD') as response:
            disposition = response.headers.get('Content-Disposition', '') or ''
            length = response.headers.get('Content-Length')
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SyncError('реестр не отвечает (%s)' % type(error).__name__) from None
    found = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition)
    name = os.path.basename(found.group(1)) if found else ''
    return name, (int(length) if length and length.isdigit() else None)


def download(url, folder, expected_size=None):
    """Скачать архив во `folder` с повторами; путь к файлу. Проверка размера и вида."""
    path = os.path.join(folder, 'raoo.zip')
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with _request(url) as response, open(path, 'wb') as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            size = os.path.getsize(path)
            if expected_size and size != expected_size:
                raise SyncError('скачано %d байт из %d — обрыв' % (size, expected_size))
            if size < MIN_BYTES:
                raise SyncError('файл слишком мал (%d байт) — это не архив реестра' % size)
            if not (zipfile.is_zipfile(path) or _looks_like_xml(path)):
                raise SyncError('скачан не ZIP и не XML')
            return path
        except (urllib.error.URLError, TimeoutError, OSError, SyncError) as error:
            last = error
            logger.warning('Реестр школ: попытка %d из %d не удалась (%s)', attempt, ATTEMPTS,
                           error if isinstance(error, SyncError) else type(error).__name__)
            if attempt < ATTEMPTS:
                time.sleep(5 * attempt)
    if isinstance(last, SyncError):
        raise last
    raise SyncError('реестр не скачался за %d попыток (%s)' % (ATTEMPTS, type(last).__name__))


def _looks_like_xml(path):
    with open(path, 'rb') as handle:
        return handle.read(64).lstrip().startswith(b'<?xml')


def temp_folder():
    return tempfile.mkdtemp(prefix='weco-schools-')


def read_rows(path):
    """Школы из файла реестра или `SyncError` простыми словами."""
    try:
        return school_registry.read_file(path)
    except (ValueError, zipfile.BadZipFile, OSError) as error:
        raise SyncError('файл реестра не читается: %s' % error) from None
    except Exception as error:  # noqa: BLE001 — битый XML (ParseError) и прочее: данные не трогаем
        raise SyncError('файл реестра не разобрался (%s)' % type(error).__name__) from None
