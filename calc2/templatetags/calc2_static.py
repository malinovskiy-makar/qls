"""Ссылки на статику calc2 с общей меткой версии.

ЗАЧЕМ. Адреса вида ``/static/calc2/calc2.css`` не несут никакой приметы
содержимого, и браузер сам решает, когда переспросить файл. 21.08 это дало
ложное отрицание при приёмке: у владельца в кэше лежал calc2.css на 104 094
байта, на сервере — 105 460, скрипты при этом были свежие. Починенный дефект
выглядел непочиненным, потому что CSS и JS разъехались между собой.

ЧТО ДЕЛАЕМ. Тег ``{% calc2_static 'calc2/файл' %}`` — это обычный ``{% static %}``
плюс ``?v=<метка>``. Метка ОДНА на всю страницу и считается по содержимому
ВСЕХ файлов папки ``calc2/static/calc2/``: правка любого файла меняет её у
всех 23 ссылок разом, поэтому CSS и скрипты обновляются вместе, а не порознь.

ПОЧЕМУ ПО СОДЕРЖИМОМУ, А НЕ ПО ВРЕМЕНИ ФАЙЛА. Время правки у клона репозитория
на сервере — это время ``git clone``, а не время правки: каждая пересборка
контейнера меняла бы метку без единого изменения в коде и заставляла бы всех
качать 1,7 МБ заново. Хеш содержимого меняется ровно тогда, когда меняется код.

ЦЕНА. Полный хеш считается один раз и запоминается. На каждый вызов делается
только ``stat`` по файлам папки (23 штуки); если размер и время не изменились —
берётся запомненное значение. Так метка обновляется и на dev-сервере, который
перезапускается на правку ``.py``, но не на правку ``.js``.

БОЕВОЙ СЕРВЕР. Там статику раздаёт WhiteNoise с
``CompressedManifestStaticFilesStorage``: имя файла уже содержит хеш
содержимого. ``?v=`` поверх этого не мешает — тег зовёт штатный ``static()``
и добавляет метку к тому адресу, который вернуло хранилище, каким бы оно ни
было. То есть механизм работает одинаково и на dev-сервере, и под WhiteNoise.
"""
import hashlib
from pathlib import Path

from django import template
from django.apps import apps
from django.templatetags.static import static

register = template.Library()

# Папка со статикой calc2 в ИСХОДНИКАХ. Считаем метку именно по ней, а не по
# STATIC_ROOT: на dev-сервере STATIC_ROOT может не существовать вовсе.
STATIC_DIR = Path(apps.get_app_config('calc2').path) / 'static' / 'calc2'

# Запомненная метка: {'key': отпечаток stat, 'version': хеш содержимого}.
_cache = {'key': None, 'version': None}


def _files():
    """Файлы статики calc2 в устойчивом порядке (скрытые не в счёт)."""
    if not STATIC_DIR.is_dir():
        return []
    return sorted(
        (p for p in STATIC_DIR.iterdir() if p.is_file() and not p.name.startswith('.')),
        key=lambda p: p.name,
    )


def _stat_key(files):
    """Дешёвый отпечаток: имя + размер + время правки по каждому файлу."""
    return '|'.join(
        '{}:{}:{}'.format(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files
    )


def calc2_static_version():
    """Общая метка версии статики calc2 (10 знаков хеша содержимого)."""
    files = _files()
    if not files:
        # Папки нет — значит, и версии нет. Ронять страницу из-за метки кэша
        # неправильно: без метки она хуже, но живая.
        return 'dev'
    key = _stat_key(files)
    if _cache['key'] == key and _cache['version']:
        return _cache['version']
    digest = hashlib.sha1()
    for p in files:
        # Имя тоже в хеш: переименование файла — это тоже изменение страницы.
        digest.update(p.name.encode('utf-8'))
        digest.update(p.read_bytes())
    version = digest.hexdigest()[:10]
    _cache['key'] = key
    _cache['version'] = version
    return version


@register.simple_tag
def calc2_static(path):
    """``{% calc2_static 'calc2/00-config.js' %}`` → адрес с ``?v=<метка>``."""
    url = static(path)
    sep = '&' if '?' in url else '?'
    return '{}{}v={}'.format(url, sep, calc2_static_version())
