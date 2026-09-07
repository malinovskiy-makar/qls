# -*- coding: utf-8 -*-
"""Раскладка журнала обогащения v2 по боевым полям.

Чистые функции без обращения к базе там, где это возможно: команда
`merge_enrichment_v2` их зовёт, а тесты проверяют по отдельности. Канон
особенностей и правило витрины — `problems/enrich/features.py`.
"""
import io
import json
import os
import re

from problems.enrich import features as feat
from problems.enrich.text import (has_graph_in_statement, has_table_in_statement,
                                  is_english_text, problem_full_text)

TERMS_PATH = os.path.join('data', 'econ_terms.json')

# «3 балла», «10 баллов», «2 б.» не ловим намеренно: сокращение «б.» стоит и
# в «б) …», то есть в букве подпункта.
SCORE_RE = re.compile(r'\d+\s*балл', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

def ensure_features():
    """Справочник особенностей = канон из `features.py`. Идемпотентно.

    Наполняется кодом, а не миграцией данных: список закрыт решением
    владельца и живёт в одном месте — держать его копию в миграции значило бы
    завести второй источник правды, который никто не обновит.
    """
    from problems.models import Feature

    by_key = {}
    for order, (key, label, counted_by) in enumerate(feat.CATALOG_FEATURES):
        obj, _created = Feature.objects.update_or_create(
            key=key,
            defaults={'label': label, 'counted_by': counted_by, 'order': order})
        by_key[key] = obj
    return by_key


def load_terms(path=TERMS_PATH):
    """Словарь понятий: каноническая форма → раздел."""
    with io.open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    return {t['canonical']: t.get('section', '') for t in data['terms']}


def concept_lookup(terms):
    """Индекс «как модель могла написать» → каноническая форма.

    Модель отвечает словами из словаря, но регистр и пробелы гуляют. Ключ —
    нижний регистр со схлопнутыми пробелами; синонимы сюда НЕ добавляются:
    прогон отдаёт канонические формы, а сведение синонимов — работа
    шорт-листа (`problems/enrich/shortlist.py`), не наша.
    """
    return {_norm_concept(name): name for name in terms}


def _norm_concept(value):
    return re.sub(r'\s+', ' ', (value or '')).strip().lower()


def match_concepts(raw_values, lookup):
    """Список от модели → (канонические формы, что не нашлось в словаре)."""
    found, missing = [], []
    seen = set()
    for value in raw_values or ():
        canon = lookup.get(_norm_concept(value))
        if canon is None:
            missing.append(value)
        elif canon not in seen:
            seen.add(canon)
            found.append(canon)
    return found, missing


# ---------------------------------------------------------------------------
# Особенности, которые считает код
# ---------------------------------------------------------------------------

def code_features(statement, part_texts, has_figure, parts_count,
                  has_rubric, has_olympiad_ref):
    """Ключи кодовых особенностей одной задачи.

    Считается по данным банка и НЕ зависит от того, обогащалась задача или
    нет — поэтому пересчитывается по всем активным задачам, а не по составу
    прогона.

    ⚠️ «С реальной олимпиады» выведена из `OlympiadRef`, а НЕ из источника
    задачи. Источник врёт: у SolveHub, ILE и Школково стоит их собственный
    `Source`, а внутри лежат задачи ВсОШ, МОШ и Высшей пробы — по источнику
    мы пометили бы агрегатор и пропустили настоящие олимпиады
    (`claude/HANDOFF_OLYMPIADS_20260901.md`, §2.4).
    """
    text = problem_full_text(statement, part_texts)
    keys = set()
    if is_english_text(text):
        keys.add('на_английском')
    if has_graph_in_statement(text, has_figure):
        keys.add('график_в_условии')
    if has_table_in_statement(text):
        keys.add('табличка_в_условии')
    if parts_count > 1:
        keys.add('многопунктовая')
    if has_rubric or SCORE_RE.search(text or ''):
        keys.add('есть_разбалловка')
    if has_olympiad_ref:
        keys.add('с_реальной_олимпиады')
    return keys


def merge_feature_sources(model_keys, code_keys):
    """`{ключ: кто поставил}` — модель, код или оба.

    Пересечение (сегодня это только «графическое_решение») помечается
    `both`: иначе пересчёт кодовой половины стирал бы ответ модели.
    """
    model_keys = {k for k in (model_keys or ()) if k in feat.MODEL_KEYS}
    code_keys = {k for k in (code_keys or ()) if k in feat.CODE_KEYS or k in feat.MODEL_KEYS}
    out = {}
    for key in model_keys | code_keys:
        if key in model_keys and key in code_keys:
            out[key] = feat.BY_BOTH
        elif key in model_keys:
            out[key] = feat.BY_MODEL
        else:
            out[key] = feat.BY_CODE
    return out


# ---------------------------------------------------------------------------
# Состояние текста
# ---------------------------------------------------------------------------

# Чем больше число, тем хуже. Правило владельца 07.09.2026: чистка сильнее
# прогона, ПОВЫШЕНИЙ НЕТ — `needs_fix`, поставленный `content_cleanup`, не
# поднимается до `ok` из-за того, что модель сочла текст чистым.
_STATUS_RANK = {'ok': 0, 'needs_fix': 1, 'junk': 2}


def content_status_for(current, text_quality, problem_type):
    """Новое значение `content_status` — не ниже текущего.

    `не_задача` в любом из двух полей → `junk`; `серьёзные_дефекты` →
    `needs_fix`; всё остальное текущего значения не меняет.
    """
    if text_quality == 'не_задача' or problem_type == 'не_задача':
        candidate = 'junk'
    elif text_quality == 'серьёзные_дефекты':
        candidate = 'needs_fix'
    else:
        candidate = 'ok'
    current = current or 'ok'
    return candidate if _STATUS_RANK[candidate] > _STATUS_RANK[current] else current


# ---------------------------------------------------------------------------
# Поля строки журнала
# ---------------------------------------------------------------------------

# Поле журнала → поле Problem. Только те, что кладутся «как есть»; темы,
# теги, заголовок, подсказки, тип и сложность разложены отдельно и правила
# у них свои (см. `merge_enrichment_v2`).
TEXT_FIELDS = {
    'given': 'given',
    'find': 'find',
    'plot': 'plot',
    'difficulty_note': 'difficulty_note',
    'text_quality_note': 'text_quality_note',
}

CHOICE_FIELDS = {
    'task_nature': ('task_nature', ('расчётная', 'теоретическая',
                                    'качественная', 'не_задача')),
    'text_quality': ('text_quality', ('чистая', 'мелкие_дефекты',
                                      'серьёзные_дефекты', 'не_задача')),
    'topic_confidence': ('topic_confidence', ('высокая', 'средняя', 'низкая')),
}


def row_scalar_fields(row):
    """Строка журнала → (что писать, что отбраковано по справочнику).

    Пустое кандидатное значение в результат не попадает вовсе: затирать
    непустое боевое пустым нельзя (правило переливки).
    """
    values, invalid = {}, {}
    for src, dst in TEXT_FIELDS.items():
        raw = (row.get(src) or '').strip()
        if raw:
            values[dst] = raw
    for src, (dst, allowed) in CHOICE_FIELDS.items():
        raw = (row.get(src) or '').strip()
        if not raw:
            continue
        if raw not in allowed:
            invalid[dst] = raw
            continue
        values[dst] = raw
    queries = [q for q in (row.get('search_queries') or []) if isinstance(q, str) and q.strip()]
    if queries:
        values['search_queries'] = queries
    return values, invalid
