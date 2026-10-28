# -*- coding: utf-8 -*-
"""Заголовок олимпиадной задачи из импорта эталона (решение 15.10.2026).

Правило владельца: настоящее официальное название из источника остаётся;
заглушка («ВП по финграмотности 2018/2019, 11 кл., задание 3», «Задача 2»,
«СПРАВКА», пусто) после обогащения заменяется названием от ИИ
(`title_candidate`). Олимпиада, год, этап, класс и номер в заголовок не
пишутся — они показываются строкой на странице задачи из `OlympiadRef`.

Отдельный флаг — «похоже на начало текста»: заголовок почти совпадает с
первой фразой условия. Ответ владельца на гейте 1 И3 (28.10): такой
официальный заголовок остаётся, если он короче 80 знаков; длиннее —
заменяется, как заглушка.

Чистые функции, без базы. Применяет правило команда
`import_reference_titles` (только к задачам из журналов импорта).
"""
from __future__ import annotations

import difflib
import re

from problems.olympiad_audit.registry import SHORT_NAMES

#: Потолок `Problem.title_candidate` (max_length поля) и проверки кандидата.
CANDIDATE_MAX = 60
#: Официальный заголовок-«начало текста» короче этого остаётся (гейт 1 И3).
TEXT_START_KEEP_BELOW = 80
TEXT_START_SIMILARITY = 0.85

_NUMBERED = re.compile(
    r'^\s*(?:задача|задание|вопрос|кейс|тест|упражнение)\s*№?\s*[\dA-Za-zА-Яа-я]{0,3}[\d.\-]*\s*[.:)]?\s*$',
    re.IGNORECASE)
_HAS_DIGIT_NUMBER = re.compile(r'^\s*(?:задача|задание|вопрос|кейс|тест)\s*№?\s*\d', re.IGNORECASE)
#: Служебное слово капсом: «СПРАВКА», «ПРИЛОЖЕНИЕ 1», «КЕЙС».
_CAPS_SERVICE = re.compile(r'^[А-ЯЁA-Z\s\d.:№-]{3,30}$')
_OLYMPIAD_WORDS = re.compile(r'олимпиад|высшая проба|\bВП\b|\bМОШ\b|\bВсОШ\b|задани[ея]\s*№?\s*\d',
                             re.IGNORECASE)
_WORD = re.compile(r'[0-9A-Za-zА-Яа-яЁё]+')


def _key(text):
    return ' '.join(_WORD.findall((text or '').lower().replace('ё', 'е')))


def stub_prefixes():
    """Начала заглушки `default_title`: короткие имена олимпиад реестра."""
    return tuple(f'{name} ' for name in SHORT_NAMES.values())


def is_stub(title):
    """Заглушка, а не название: пусто, «ВП по …», «Задача N», служебное слово капсом."""
    t = (title or '').strip()
    if not t:
        return True
    if t.startswith(stub_prefixes()) or t.startswith('ВП по') or t.startswith('МОШ по'):
        return True
    if _NUMBERED.match(t) or _HAS_DIGIT_NUMBER.match(t):
        return True
    letters = [c for c in t if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and _CAPS_SERVICE.match(t) \
            and len(t.split()) <= 3:
        return True
    return False


def looks_like_text_start(title, statement):
    """Заголовок почти совпадает с первой фразой условия (эхо начала текста)."""
    t, s = _key(title), _key(statement)
    if len(t) < 8 or not s:
        return False
    if s.startswith(t):
        return True
    prefix = s[:len(t)]
    return difflib.SequenceMatcher(None, t, prefix).ratio() >= TEXT_START_SIMILARITY


def candidate_problems(candidate):
    """Почему кандидат негоден ([] — годен): пусто, длинно, номер, олимпиада."""
    c = (candidate or '').strip()
    why = []
    if not c:
        return ['пусто']
    if len(c) > CANDIDATE_MAX:
        why.append(f'длиннее {CANDIDATE_MAX}')
    if _HAS_DIGIT_NUMBER.match(c) or re.search(r'№\s*\d', c):
        why.append('номер задания')
    if _OLYMPIAD_WORDS.search(c):
        why.append('название олимпиады')
    if is_stub(c):
        why.append('сам заглушка')
    return why


def decide(title, candidate, statement):
    """{'new': заголовок, 'rule': какое правило, 'flag': '' | 'начало текста',
    'changed': bool}. Ничего не пишет."""
    title = (title or '').strip()
    bad = candidate_problems(candidate)
    if is_stub(title):
        if not bad:
            return {'new': candidate.strip(), 'rule': 'заглушка → title_candidate', 'flag': '',
                    'changed': candidate.strip() != title}
        return {'new': title, 'rule': f'заглушка, кандидат негоден ({", ".join(bad)}) — '
                                      'ждёт обогащения', 'flag': '', 'changed': False}
    if looks_like_text_start(title, statement):
        if len(title) < TEXT_START_KEEP_BELOW:
            return {'new': title, 'rule': 'начало текста, короче 80 — оставлен',
                    'flag': 'начало текста', 'changed': False}
        if not bad:
            return {'new': candidate.strip(), 'rule': 'начало текста, 80+ → title_candidate',
                    'flag': 'начало текста', 'changed': candidate.strip() != title}
        return {'new': title, 'rule': 'начало текста, 80+, кандидат негоден — ждёт обогащения',
                'flag': 'начало текста', 'changed': False}
    return {'new': title, 'rule': 'официальное название — оставлен', 'flag': '', 'changed': False}
