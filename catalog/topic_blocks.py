"""Пять блоков тем для каталога — ТОНКИЙ СЛОЙ над `problems/sections.py`.

Решение владельца 05.09.2026 (Notion, «Цвет и группировка тем — из одного
модуля problems/sections.py»): границы блоков, оба набора названий (23 живые
темы базы и 29 темы таксономии v2) и цвет живут в ОДНОМ месте на весь сайт —
`problems/sections.py`. Здесь только то, что нужно каталогу сверх этого:
нестрогое сравнение названий, граница «тема каталога / мусор импорта» и
порядок тем внутри блока. Своей таблицы у этого файла НЕТ — появится
тема в `sections.py`, и она сама встанет в свой блок.

Цветов у тем пять — по блоку (`--map-g-micro/macro/fin/math/other` в
`_tokens.html`). Семь цветов разделов карты (ADR 0053) отвергнуты решением
05.09: три группировки в проекте были источником «рандомных чисел».

⚠️ СОПОСТАВЛЕНИЕ ИДЁТ ПО НАЗВАНИЮ ТЕМЫ, А НЕ ПО ID. В базе сегодня 23
живые темы (`apply_topic_mapping.CANONICAL`), в таксономии v2 — 29
(`catalog/data/topic_map.json`), и прогон обогащения заменит первые
вторыми. Регистр, «ё/е», вид тире и лишние пробелы не важны.

⚠️ НЕИЗВЕСТНОЕ НАЗВАНИЕ НЕ РОНЯЕТ ЭКРАН: тема уходит в «Прочее» с одним
предупреждением в лог. Молча выбросить её нельзя — пропала бы из
фильтра вместе со своими задачами.
"""
from __future__ import annotations

import logging
import re

from problems.sections import (
    CANONICAL_SECTION, SECTIONS, V2_SECTION_BY_NUMBER, V2_TOPIC_NAMES,
)

logger = logging.getLogger(__name__)


def _names_of(key):
    """Названия тем блока: сначала живые 23 (в порядке `CANONICAL_SECTION` —
    он же порядок `apply_topic_mapping.CANONICAL`), затем названия
    таксономии v2 по номерам, которых среди живых нет."""
    live = [name for name, section in CANONICAL_SECTION.items() if section == key]
    v2 = [V2_TOPIC_NAMES[n] for n in sorted(V2_TOPIC_NAMES)
          if V2_SECTION_BY_NUMBER[n] == key and V2_TOPIC_NAMES[n] not in live]
    return tuple(live + v2)


# Пять блоков в порядке владельца: `(ключ, подпись, названия тем)`. Подписи
# короткие — те же, что на карте, в тренажёре и на радаре (`SECTIONS`).
BLOCKS = tuple((key, label, _names_of(key)) for key, label in SECTIONS)

# Цвет точки блока в окне фильтров — цвет самого блока: цветов пять.
BLOCK_SECTION = {key: key for key, _label in SECTIONS}

# Куда попадает название, которого нет в таблице.
FALLBACK_BLOCK = 'other'
FALLBACK_SECTION = 'other'

_RX_SPACE = re.compile(r'\s+')
_RX_DASH = re.compile(r'[‐‑‒–—―-]')


def normalize(name):
    """Ключ сравнения названий: регистр, «ё/е», тире и пробелы не важны."""
    text = (name or '').casefold().replace('ё', 'е')
    text = _RX_DASH.sub('-', text)
    return _RX_SPACE.sub(' ', text).strip()


_BLOCK_BY_NAME = {normalize(name): key
                  for key, _label, names in BLOCKS for name in names}
_BLOCK_LABEL = {key: label for key, label, _names in BLOCKS}
_warned = set()


def _warn_once(name):
    key = normalize(name)
    if key in _warned:
        return
    _warned.add(key)
    logger.warning('тема «%s» не описана в problems/sections.py — '
                   'ушла в «Прочее»', name)


def is_known(name):
    """Название описано в `problems/sections.py` — то есть это тема каталога.

    В базе 849 записей `Topic`, из них темы каталога — 23 живые сегодня и 29
    таксономии v2 завтра; остальное — мусор импорта (авторы, адреса).
    Фильтр и карточки показывают только известные названия, и это ОДНО
    место, где проходит граница, а не список в каждом читателе.
    """
    return normalize(name) in _BLOCK_BY_NAME


def block_of(name):
    """Ключ блока фильтра для названия темы; неизвестное → «Прочее»."""
    key = _BLOCK_BY_NAME.get(normalize(name))
    if key is None:
        _warn_once(name)
        return FALLBACK_BLOCK
    return key


def section_of(name):
    """Ключ цвета темы (`--map-g-*`). Цветов пять, по блоку — тот же ключ."""
    key = _BLOCK_BY_NAME.get(normalize(name))
    if key is None:
        _warn_once(name)
        return FALLBACK_SECTION
    return key


def block_label(key):
    """Подпись блока по ключу."""
    return _BLOCK_LABEL[key]


def order_in_block(name):
    """Место темы внутри своего блока — порядок `problems/sections.py`.

    Нужно, чтобы темы в блоке шли в порядке владельца, а не в том, в каком
    их вернула база. Неизвестное название встаёт в конец.
    """
    key = normalize(name)
    for _block, _label, names in BLOCKS:
        for i, known in enumerate(names):
            if normalize(known) == key:
                return i
    return len(_BLOCK_BY_NAME)
