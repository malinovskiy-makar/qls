# -*- coding: utf-8 -*-
"""Лексический отбор шорт-листа словаря терминов (Б1, прогон v2).

Поле `econ_concepts` в прогоне обогащения выбирается моделью из ЗАКРЫТОГО
шорт-листа ~40 терминов, поданного вместе с текстом задачи. Отбирать эти
40 «по теме задачи» нельзя: темы нет у 54,7 % задач и у 100 % новых
источников, а тему как раз и считает вызов, для которого шорт-лист
готовится, — замкнутый круг. Поэтому отбор ЛЕКСИЧЕСКИЙ и делается кодом
до вызова модели.

Как это устроено.

1. `compute_document_frequencies()` один раз проходит по всему корпусу и
   считает документную частоту каждого из 1 772 терминов словаря
   (`problems/econ_terms.py`). Термин «встречен» в тексте, если найдена
   его каноническая форма, любой русский синоним, любая словоформа из
   четырёх падежей, английский эквивалент, ИЛИ многобуквенное однозначное
   обозначение — см. `matched_terms()`.
2. `save_df_cache()` / `load_df_cache()` кладут и читают результат в
   `data/econ_terms_df.json`, чтобы не считать это на каждом прогоне.
3. `shortlist_for(text, k=40)` находит все термины, встречающиеся в
   КОНКРЕТНОМ тексте, сортирует по возрастанию документной частоты
   (редкие вперёд — они различают задачи) и отдаёт первые `k`.

⚠️ ОБОЗНАЧЕНИЯ — ОТДЕЛЬНЫЙ И ОГРАНИЧЕННЫЙ КАНАЛ. Однобуквенные (`P`, `S`,
`D`, `I`, `R`, `C`, `π`...) в отбор не участвуют вообще, даже если словарь
считает их однозначными (`p`, `I`, `W`, `Π` формально `auto_normalize:
true`, но без контекста абзаца это всё равно гадание — предупреждение уже
объяснено в `problems/econ_terms.py`). Обозначения, у которых в обратном
индексе словаря больше одного канонического термина (`auto_normalize:
false`), тоже не участвуют — это тот же принцип, что и в самом словаре,
просто применённый на уровень раньше. Оба правила проверяются ГЛОБАЛЬНО
по обратному индексу словаря, а не по списку обозначений самого термина:
обозначение может стать неоднозначным из-за СОВСЕМ ДРУГОГО термина.

⚠️ ОТБОР ДЕТЕРМИНИРОВАН. Один и тот же текст всегда даёт один и тот же
шорт-лист: сортировка — по (частота, каноническое имя), без случайности.

⚠️ СОВПАДЕНИЕ ФРАЗ — ПО ГРАНИЦАМ СЛОВ, А НЕ ПОДСТРОКОЙ. Наивный `in`
находил бы «рост» внутри «прирост». Текст токенизируется на слова
(с учётом внутреннего дефиса/тире — «Куна-Таккера» остаётся одним
токеном), из токенов строятся n-граммы длиной до максимальной фразы
словаря (7 слов) и проверяются по словарю фраз. Обозначения (`SOC`,
`PPF`...) — короткие и малоупотребимые в обычном тексте, поэтому для них
осознанно оставлена более простая подстрочная проверка, регистрозависимая
(экономическое обозначение регистр не меняет: `MC` — не то же самое, что
«мс» где-то в слове).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from problems import econ_terms

DF_FILE = 'econ_terms_df.json'

# Меньше — добираем ядром до этого числа (см. shortlist_for). Больше — не
# отдаём вовсе, даже если нашлось больше: k управляет верхней границей.
MIN_SHORTLIST = 15
DEFAULT_K = 40

OLYMPIC_CORE_PRIORITY = 'олимпиадное ядро'

_TOKEN_RE = re.compile(
    r'[a-zA-Zа-яА-ЯёЁ0-9]+(?:[-–][a-zA-Zа-яА-ЯёЁ0-9]+)*')


def _tokenize(text):
    return _TOKEN_RE.findall((text or '').lower())


@lru_cache(maxsize=1)
def _phrase_index():
    """Словарь фраз: 'фраза в нижнем регистре' -> {канонические термины}.

    Плюс максимальная длина фразы в словах — n-граммы длиннее её строить
    незачем.
    """
    index = {}
    max_words = 1
    for term in econ_terms.terms():
        canonical = term['canonical']
        phrases = {canonical}
        phrases.update(term.get('synonyms') or [])
        phrases.update((term.get('word_forms') or {}).values())
        phrases.update(term.get('english') or [])
        for phrase in phrases:
            phrase = (phrase or '').strip().lower()
            if not phrase:
                continue
            index.setdefault(phrase, set()).add(canonical)
            words = len(phrase.split())
            if words > max_words:
                max_words = words
    return index, max_words


@lru_cache(maxsize=1)
def _notation_index():
    """Обозначение (регистрозависимо) -> единственный канонический термин.

    Строится из ГЛОБАЛЬНОГО обратного индекса словаря
    (`econ_terms.notation_index()`), а не из списков обозначений отдельных
    терминов — см. предупреждение в докстринге модуля.
    """
    index = {}
    for symbol, slot in econ_terms.notation_index().items():
        symbol = (symbol or '').strip()
        if len(symbol) <= 1:
            continue
        if not slot.get('auto_normalize'):
            continue
        index[symbol] = slot['terms'][0]
    return index


def matched_terms(text):
    """Множество канонических терминов, найденных в тексте."""
    text = text or ''
    found = set()

    phrase_index, max_words = _phrase_index()
    tokens = _tokenize(text)
    n = len(tokens)
    for start in range(n):
        limit = min(max_words, n - start)
        for length in range(1, limit + 1):
            phrase = ' '.join(tokens[start:start + length])
            terms = phrase_index.get(phrase)
            if terms:
                found.update(terms)

    for symbol, canonical in _notation_index().items():
        if symbol in text:
            found.add(canonical)

    return found


def compute_document_frequencies(texts):
    """Документная частота термина = число ДОКУМЕНТОВ, где он встречен.

    `texts` — произвольный итератор строк (одна строка = условие +
    подпункты одной задачи). Повтор термина внутри одного документа
    считается один раз.

    Возвращает `(df, found_counts)`: `df` — словарь каноническое имя ->
    число документов; `found_counts` — список «сколько терминов нашлось»
    по каждому документу, по порядку — материал для инвариантов Б1
    (`corpus_invariants`).
    """
    df = {}
    found_counts = []
    for text in texts:
        found = matched_terms(text)
        found_counts.append(len(found))
        for canonical in found:
            df[canonical] = df.get(canonical, 0) + 1
    return df, found_counts


def corpus_invariants(found_counts):
    """Медиана и доли для отчёта по всему корпусу (печатает Б1-команда)."""
    if not found_counts:
        return {'median': 0, 'share_below_15': 0.0, 'share_above_40': 0.0}
    counts = sorted(found_counts)
    n = len(counts)
    mid = n // 2
    if n % 2:
        median = counts[mid]
    else:
        median = (counts[mid - 1] + counts[mid]) / 2
    below = sum(1 for c in counts if c < MIN_SHORTLIST) / n
    above = sum(1 for c in counts if c > DEFAULT_K) / n
    return {'median': median, 'share_below_15': below, 'share_above_40': above}


def df_cache_path():
    return Path(settings.BASE_DIR) / 'data' / DF_FILE


def save_df_cache(df, path=None):
    path = path or df_cache_path()
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(df, fh, ensure_ascii=False, indent=1, sort_keys=True)


def load_df_cache(path=None):
    path = path or df_cache_path()
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def shortlist_for(text, k=DEFAULT_K, df=None):
    """Шорт-лист из максимум `k` терминов для конкретного текста задачи.

    Редкие термины (низкая документная частота — они различают задачи)
    идут первыми. Если нашлось меньше `MIN_SHORTLIST` (15) — добор
    самыми частыми терминами олимпиадного ядра, которых в шорт-листе ещё
    нет, до 15 (не до `k` — цель добора «дать модели из чего выбирать»,
    а не растянуть список).
    """
    if df is None:
        df = load_df_cache()

    found = matched_terms(text)
    ranked = sorted(found, key=lambda name: (df.get(name, 0), name))
    shortlist = ranked[:k]

    if len(shortlist) < MIN_SHORTLIST:
        chosen = set(shortlist)
        core_terms = [t['canonical'] for t in econ_terms.terms()
                      if t.get('priority') == OLYMPIC_CORE_PRIORITY]
        core_ranked = sorted(core_terms,
                             key=lambda name: (-df.get(name, 0), name))
        for name in core_ranked:
            if len(shortlist) >= MIN_SHORTLIST:
                break
            if name in chosen:
                continue
            shortlist.append(name)
            chosen.add(name)

    return shortlist
