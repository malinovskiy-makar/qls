# -*- coding: utf-8 -*-
"""Словарь терминов олимпиадной экономики — чтение и поиск (С6).

Данные лежат в `data/econ_terms.json`, собираются из markdown-первоисточника
командой `manage.py build_econ_terms`. Здесь только чтение: ни один вызов
отсюда файл не меняет.

Зачем словарь нужен (решение от 19.08 в Notion): он закрывает четыре задачи
сразу — закрытый список понятий для разметки корпуса (1 772 термина вместо
~210 тегов), нормализация синонимов и аббревиатур в лексическом поиске
(этого IDF не умеет в принципе — он видит разные строки), контрольный набор
для проверки лемматизации и материал обучающих пар.

⚠️ ГЛАВНОЕ ПРАВИЛО, И ОНО КОНТРИНТУИТИВНО: обозначение, за которым стоит
больше одного канонического термина, НЕ нормализуется автоматически вовсе.
`P` — это цена, уровень цен и опцион пут; `S` — предложение и базисный актив;
`C` — потребление, купон и опцион колл; `π` — прибыль и инфляция. Кажется,
что чем больше сопоставлений, тем лучше поиск. На самом деле однозначное
сопоставление без контекста УХУДШАЕТ качество. Предупреждение исходит от
самого словаря, а не придумано нами. Поэтому `lookup_notation` возвращает
флаг `auto_normalize`, и звать его без проверки этого флага — ошибка.
"""
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

DATA_FILE = 'econ_terms.json'


def data_path():
    return Path(settings.BASE_DIR) / 'data' / DATA_FILE


@lru_cache(maxsize=1)
def load():
    """Весь словарь целиком. Кэшируется на процесс — файл 1,3 МБ."""
    with open(data_path(), encoding='utf-8') as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def terms():
    """Список записей: канонический термин, синонимы, English, обозначения,
    словоформы, источники, раздел."""
    return load()['terms']


@lru_cache(maxsize=1)
def notation_index():
    """Обозначение -> {'terms': [...], 'auto_normalize': bool}."""
    return load()['notation_index']


@lru_cache(maxsize=1)
def _by_canonical():
    return {t['canonical']: t for t in terms()}


def get(canonical):
    """Запись по каноническому термину, иначе None."""
    return _by_canonical().get(canonical)


def lookup_notation(symbol):
    """Что стоит за обозначением.

    Возвращает `None`, если символа в словаре нет вовсе.

    ⚠️ Проверяйте `auto_normalize` перед тем, как что-то заменять: у
    неоднозначных символов (`P`, `S`, `AC`, `AP`, `AR`, `C`, `π` и ещё
    полусотни) он `False`, и подставлять любой из терминов без окрестного
    контекста нельзя — см. предупреждение в шапке модуля.
    """
    return notation_index().get((symbol or '').strip())


def normalizable_notation(symbol):
    """Единственный канонический термин символа, если он однозначен.

    Для неоднозначного символа и для незнакомого — `None`. Это удобная
    обёртка ровно для того случая, когда вызывающему нужен ответ «можно
    ли молча заменить», а не полная карточка.
    """
    slot = lookup_notation(symbol)
    if not slot or not slot['auto_normalize']:
        return None
    return slot['terms'][0]


@lru_cache(maxsize=1)
def counts():
    """Числа словаря: сколько чего разобрано и сколько он заявляет о себе."""
    return load()['meta']['actual_counts']


def word_form_pairs():
    """Пары «каноническая форма -> словоформа» для всех падежей.

    Это готовый контрольный набор для проверки лемматизации: словарь даёт
    формы в четырёх падежах, и правильный морфологический разбор обязан
    свести форму и канонический термин к одним и тем же леммам.
    """
    for term in terms():
        canonical = term['canonical']
        for case, form in sorted(term['word_forms'].items()):
            if form:
                yield canonical, case, form
