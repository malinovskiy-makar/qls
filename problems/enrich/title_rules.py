# -*- coding: utf-8 -*-
"""Правило перезаписи `Problem.title` → `title_candidate` (Фаза 4.1, Б5).

⚠️ ТОЛЬКО СЧИТАЕТ. Ничего в этом модуле не пишет в базу — `classify_current_title`
классифицирует УЖЕ существующий `Problem.title` на A/B/C/D, чтобы посчитать,
сколько задач попадёт под перезапись новым `title_candidate` от модели, когда
это будет решено применять. Сама перезапись — отдельная, более поздняя сессия.

Категории:
    A — пусто или заглушка ("—", "Разное", "Разное 3"...) → пишем.
    B — сломан: сырая LaTeX-разметка, кракозябры (мусор кодировки), похоже
        на имя файла, длиннее 80 символов → пишем.
    C — нормализованный заголовок — префикс нормализованного условия, или
        совпадает с первыми 60 символами условия на ≥ 85 % → пишем (заголовок
        просто эхо первого предложения, содержательной ценности не несёт).
    D — всё остальное → НЕ трогаем.

Пересекается по смыслу с `classify_title` в
`problems/management/commands/apply_batch1_titles.py` (тот же класс проблем:
junk/echo_stub/raw_latex/tail_stub), но НЕ переиспользует его код: тот модуль
— однократная команда применения заголовков Батча 1 поверх `Problem.title`
напрямую, эта — независимый счётчик для НОВОГО поля `title_candidate`. Правки
одного не должны тихо менять поведение другого.
"""
import difflib
import re

from problems.models import Problem

CATEGORY_EMPTY_OR_STUB = 'A'
CATEGORY_BROKEN = 'B'
CATEGORY_ECHO = 'C'
CATEGORY_KEEP = 'D'

# Категория → `Problem.TitleSource` (Фаза 2Б.3, 2026-09-01): единственное
# место, где категория A/B/C/D превращается в значение поля `title_source` —
# соответствие 1:1 с формулировками choices на самой модели.
CATEGORY_TITLE_SOURCE = {
    CATEGORY_EMPTY_OR_STUB: Problem.TitleSource.MODEL_EMPTY,
    CATEGORY_BROKEN: Problem.TitleSource.MODEL_BROKEN,
    CATEGORY_ECHO: Problem.TitleSource.MODEL_FIRSTLINE,
    CATEGORY_KEEP: Problem.TitleSource.KEPT,
}

MAX_CLEAN_LENGTH = 80
ECHO_PREFIX_LENGTH = 60
ECHO_SIMILARITY_THRESHOLD = 0.85

_PLACEHOLDER_RE = re.compile(r'^(—|-|–|−|разное\s*\d*)$', re.IGNORECASE)
_LATEX_RE = re.compile(r'\\\(|\\\)|\\frac\b|\\sqrt\b|\^|_\{|\$|\{|\}')
# Кракозябры — типичный мусор от неверной кодировки (двойное UTF-8→CP1251
# и подобное): символ replacement character, длинные пробеги латиницы с
# management-символами, или доля непечатных/управляющих символов.
_MOJIBAKE_CHARS_RE = re.compile(r'[�\x00-\x08\x0b\x0c\x0e-\x1f]')
_FILENAME_RE = re.compile(
    r'\.(docx?|pdf|jpe?g|png|gif|bmp|tiff?|xlsx?|pptx?|txt|zip|rar)$',
    re.IGNORECASE)


def _norm(text):
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _looks_broken(title):
    if _LATEX_RE.search(title):
        return True
    if _MOJIBAKE_CHARS_RE.search(title):
        return True
    if _FILENAME_RE.search(title):
        return True
    if len(title) > MAX_CLEAN_LENGTH:
        return True
    return False


def _echo_ratio(title_norm, statement_prefix):
    if not title_norm or not statement_prefix:
        return 0.0
    matcher = difflib.SequenceMatcher(None, title_norm, statement_prefix)
    return matcher.ratio()


def classify_current_title(title, statement):
    """Категория A/B/C/D для текущего `Problem.title` этой задачи."""
    raw = (title or '').strip()
    norm = _norm(raw)

    if not norm or _PLACEHOLDER_RE.match(norm):
        return CATEGORY_EMPTY_OR_STUB

    if _looks_broken(raw):
        return CATEGORY_BROKEN

    statement_norm = _norm(statement)
    statement_prefix60 = statement_norm[:ECHO_PREFIX_LENGTH]
    if statement_norm.startswith(norm):
        return CATEGORY_ECHO
    if _echo_ratio(norm, statement_prefix60) >= ECHO_SIMILARITY_THRESHOLD:
        return CATEGORY_ECHO

    return CATEGORY_KEEP


def classify_and_pick_source(title, statement):
    """`(категория, Problem.TitleSource)` для текущего заголовка задачи."""
    category = classify_current_title(title, statement)
    return category, CATEGORY_TITLE_SOURCE[category]
