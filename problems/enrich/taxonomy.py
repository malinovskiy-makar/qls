# -*- coding: utf-8 -*-
"""Чтение таксономии v1.1 (`data/taxonomy.json`) для промпта Б2.

Единственный источник правды — сам файл (собран отдельно, версия 1.1,
29 тем / 344 тега). Здесь только чтение и форматирование в текст промпта:
CLAUDE.md прямо запрещает трогать `data/taxonomy.json` и
`docs/TAXONOMY.md` из этой сессии.
"""
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

DATA_FILE = 'taxonomy.json'


def data_path():
    return Path(settings.BASE_DIR) / 'data' / DATA_FILE


@lru_cache(maxsize=1)
def load():
    with open(data_path(), encoding='utf-8') as fh:
        return json.load(fh)


def themes():
    return load()['themes']


@lru_cache(maxsize=1)
def theme_names():
    return tuple(t['name'] for t in themes())


@lru_cache(maxsize=1)
def all_tags():
    """Плоский список всех 344 тегов, в порядке дерева."""
    return tuple(tag for theme in themes() for tag in theme['tags'])


@lru_cache(maxsize=1)
def tag_to_theme():
    """Тег -> имя темы, которой он принадлежит (тег живёт ровно в одной теме)."""
    mapping = {}
    for theme in themes():
        for tag in theme['tags']:
            mapping[tag] = theme['name']
    return mapping


# ---------------------------------------------------------------------------
# Короткие идентификаторы для enum схемы (Б4-2, 31.08.2026, диета префикса).
#
# ⚠️ ПОЧЕМУ. Замер показал: строгая JSON-схема (`strict: true`) с `enum` на
# 344 полных названия стоит НЕПРОПОРЦИОНАЛЬНО дороже своего сырого JSON-
# текста — 41 246 токенов реальной цены против 4 765 по локальному подсчёту
# (~8,7×). Похоже, движок ограниченной генерации разворачивает `enum` во
# внутреннюю грамматику, и её размер зависит от длины самих строк-значений.
# Короткие идентификаторы вместо полных названий должны эту грамматику
# резко сократить — гипотеза проверяется прогоном Б4-2 (Фаза 2).
#
# `data/taxonomy.json` НЕ меняется — идентификаторы выводятся из порядка
# файла (id темы; номер тега внутри темы, с единицы), не хранятся отдельно.
# Соответствие «идентификатор → название» модель берёт из дерева в тексте
# ядра (tree_text ниже), в схему полные названия больше не идут.
# ---------------------------------------------------------------------------

def theme_id(name):
    return str(_theme_name_to_id()[name])


@lru_cache(maxsize=1)
def _theme_name_to_id():
    return {t['name']: t['id'] for t in themes()}


@lru_cache(maxsize=1)
def theme_ids():
    """Идентификаторы тем в порядке файла — то же, что в `enum` схемы."""
    return tuple(str(t['id']) for t in themes())


@lru_cache(maxsize=1)
def _tag_name_to_id():
    mapping = {}
    for theme in themes():
        for index, tag in enumerate(theme['tags'], start=1):
            mapping[tag] = '%d.%d' % (theme['id'], index)
    return mapping


def tag_id(name):
    return _tag_name_to_id()[name]


@lru_cache(maxsize=1)
def tag_ids():
    """Идентификаторы тегов (`<id темы>.<номер тега>`) в порядке файла."""
    return tuple(_tag_name_to_id()[tag] for tag in all_tags())


@lru_cache(maxsize=1)
def _id_to_theme_name():
    return {str(t['id']): t['name'] for t in themes()}


def theme_name_from_id(identifier):
    """Обратное преобразование — идентификатор темы обратно в название."""
    return _id_to_theme_name()[str(identifier)]


@lru_cache(maxsize=1)
def _id_to_tag_name():
    return {identifier: name for name, identifier in _tag_name_to_id().items()}


def tag_name_from_id(identifier):
    """Обратное преобразование — идентификатор тега обратно в название."""
    return _id_to_tag_name()[identifier]


def tree_text():
    """Дерево тем/тегов, отформатированное для системного ядра промпта.

    Компактно: имя темы, одна строка описания, теги через запятую. Полный
    список — потому что тема и тег выбираются СТРОГО из закрытого списка,
    урезать его нельзя; описание темы сокращает риск ошибки на границе
    («Монополия» vs «Вмешательство государства» при налоге у монополиста).

    ⚠️ Каждый тег подписан своим идентификатором (`<id темы>.<номер>`) —
    после диеты Б4-2 схема просит вернуть именно идентификатор, а не
    название, и это дерево — единственное место, где модель видит
    соответствие идентификатора и смысла тега.
    """
    lines = []
    for theme in themes():
        lines.append('%d. %s — %s' % (
            theme['id'], theme['name'], theme['description']))
        tagged = ['%d.%d %s' % (theme['id'], index, tag)
                 for index, tag in enumerate(theme['tags'], start=1)]
        lines.append('   Теги: ' + '; '.join(tagged))
    return '\n'.join(lines)
