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


def tree_text():
    """Дерево тем/тегов, отформатированное для системного ядра промпта.

    Компактно: имя темы, одна строка описания, теги через запятую. Полный
    список — потому что тема и тег выбираются СТРОГО из закрытого списка,
    урезать его нельзя; описание темы сокращает риск ошибки на границе
    («Монополия» vs «Вмешательство государства» при налоге у монополиста).
    """
    lines = []
    for theme in themes():
        lines.append('%d. %s — %s' % (
            theme['id'], theme['name'], theme['description']))
        lines.append('   Теги: ' + '; '.join(theme['tags']))
    return '\n'.join(lines)
