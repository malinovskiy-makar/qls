# -*- coding: utf-8 -*-
"""Лексическая нога поиска: pymorphy3 + BM25 (bm25s).

Исполняет решение от 19.08.2026 «Лексическая нога — в Python (bm25s +
pymorphy3), не в PostgreSQL»: у нас есть золотой набор, поэтому вес
слияния подбирается по данным, а не на глаз, а полнотекстовый поиск
PostgreSQL такой подгонки не даёт.

⚠️ К КАТАЛОГУ НЕ ПОДКЛЮЧЁН. Модуль гоняет офлайн-замер
(`reports/llm_search_eval/`). Подключение — отдельное решение владельца
по цифрам замера.

⚠️ `catalog/hybrid.py` не трогается и не заменяется: на нём висит
аварийная деградация каталога, когда смысловой поиск лежит. Ломать
работающую деградацию ради замера нельзя, поэтому нога живёт рядом, а
не вместо.

⚠️ `bm25s` и `pymorphy3` НЕ входят в `requirements/base.txt` — импорт
поэтому ленивый, внутри функций. Файл, который импортируется на боевом
сервере просто потому, что лежит в приложении `catalog`, обязан
оставаться безвредным.
"""
import json
import os
import re

#: Токен: слово из букв или число. Пунктуация и одиночные символы вне.
_TOKEN = re.compile(r'[а-яa-z0-9]+', re.IGNORECASE)

#: Кэш разборов: pymorphy3 на 14 тысячах задач иначе становится самой
#: дорогой частью сборки — слова в корпусе повторяются постоянно.
_LEMMA_CACHE = {}
_MORPH = None


def _morph():
    global _MORPH
    if _MORPH is None:
        import pymorphy3
        _MORPH = pymorphy3.MorphAnalyzer()
    return _MORPH


def lemmatize(text):
    """Текст → список лемм: нижний регистр, «ё»→«е», без односимвольных.

    Односимвольные выброшены не как «стоп-слова по списку», а по длине:
    в русском это предлоги и союзы («в», «и», «к»), и они дают BM25
    ровно шум. Числа остаются: «М1», «2020», «CO2» — часть смысла задачи.
    """
    if not text:
        return []
    lemmas = []
    for token in _TOKEN.findall(text.lower().replace('ё', 'е')):
        if len(token) < 2:
            continue
        cached = _LEMMA_CACHE.get(token)
        if cached is None:
            if token.isdigit():
                cached = token
            else:
                cached = _morph().parse(token)[0].normal_form.replace('ё', 'е')
            _LEMMA_CACHE[token] = cached
        lemmas.append(cached)
    return lemmas


#: Порядок частей отпечатка. Заголовок первым — он короткий и точный;
#: тема, теги и понятия в конце — по ним работает разбор запроса моделью.
_PARTS = ('title', 'statement', 'find', 'given')


def index_text(row):
    """Словарь полей задачи → один текст для индекса.

    Принимает словарь, а не объект `Problem`, намеренно: сборка текста
    проверяема без базы, а слой, читающий базу, остаётся тонким.
    """
    pieces = [row.get(name) or '' for name in _PARTS]
    pieces.extend(row.get('parts') or [])
    for name in ('topics', 'tags', 'concepts'):
        pieces.extend(row.get(name) or [])
    return '\n'.join(piece for piece in pieces if piece)


class Index(object):
    """Индекс BM25 плюс список id: bm25s знает только номера строк."""

    def __init__(self, retriever, ids):
        self.retriever = retriever
        self.ids = list(ids)


def build_index(ids, texts):
    """Собрать индекс по параллельным спискам id и текстов."""
    import bm25s

    corpus = [lemmatize(text) for text in texts]
    retriever = bm25s.BM25()
    retriever.index(corpus, show_progress=False)
    return Index(retriever, ids)


def search(index, query, top_k=30):
    """Запрос → [(id, вес)], по убыванию веса, без нулевых весов.

    Нулевой вес означает «ни одного общего слова»; такой кандидат в пуле
    неотличим от случайного, и место в топ-30 он занимать не должен.
    """
    tokens = lemmatize(query)
    if not tokens or not index.ids:
        return []
    k = min(top_k, len(index.ids))
    rows, scores = index.retriever.retrieve([tokens], k=k, show_progress=False)
    hits = [(index.ids[int(row)], float(score))
            for row, score in zip(rows[0], scores[0]) if score > 0]
    return hits


def save_index(index, path):
    """Сохранить индекс на диск: сборка на корпусе стоит секунд, а
    прогон гоняет один и тот же индекс по всем запросам замера."""
    os.makedirs(path, exist_ok=True)
    index.retriever.save(path)
    # Список id — обычный JSON, не pickle: читать сюда чужой файл мы не
    # собираемся, но и повода давать исполнять код из файла индекса нет.
    with open(os.path.join(path, 'ids.json'), 'w', encoding='utf-8') as handle:
        json.dump(index.ids, handle)


def load_index(path):
    import bm25s

    retriever = bm25s.BM25.load(path)
    with open(os.path.join(path, 'ids.json'), encoding='utf-8') as handle:
        ids = json.load(handle)
    return Index(retriever, ids)
