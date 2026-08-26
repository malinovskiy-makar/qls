# -*- coding: utf-8 -*-
"""Общий конвертер текста задачи к целевому формату (CORPUS-FORMAT.md §3).

Пилот: UPDATE (ILE, задача уже в базе) и INSERT (Школково, парсинг с диска).
Чистые функции — вход текст, выход текст/структура, никакого I/O и ORM.
"""
from __future__ import annotations

import re

from problems.rendering import _protect_math_and_currency, _restore_math_and_currency

#: Голые окружения — те же, что CORPUS-FORMAT.md §3 и атлас источников:
#: equation/align/gather (со звёздочкой или без). cases НЕ входит — оно
#: почти всегда уже внутри более крупной формулы (см. CORPUS-FORMAT.md
#: Приложение, п.1) и никогда не оборачивается само по себе.
_BARE_ENV_NAMES = ('equation', 'align', 'gather')
_BARE_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(_BARE_ENV_NAMES) + r'\*?)\}.*?\\end\{\1\}',
    re.DOTALL,
)

#: Границы формулы — буквальная копия набора из rendering.py, нужна здесь
#: только чтобы проверить «уже обёрнуто?» перед оборачиванием.
_MATH_OPEN_CLOSE = (('$$', '$$'), ('\\[', '\\]'), ('\\(', '\\)'), ('$', '$'))


def _is_already_wrapped(text, start, end):
    """Проверить, стоит ли по обе стороны от text[start:end] один и тот же
    разделитель формулы (например ``$$`` перед и после)."""
    for open_, close in _MATH_OPEN_CLOSE:
        before = text[max(0, start - len(open_)):start]
        after = text[end:end + len(close)]
        if before == open_ and after == close:
            return True
    return False


def wrap_bare_environments(text):
    """Обернуть голые ``\\begin{equation|align|gather}...\\end{...}`` в ``$$``.

    Не трогает уже обёрнутые (проверка по границам) и не трогает ``cases``
    вовсе (его нет в списке имён окружений)."""
    out = []
    pos = 0
    for match in _BARE_ENV_RE.finditer(text):
        start, end = match.span()
        out.append(text[pos:start])
        if _is_already_wrapped(text, start, end):
            out.append(match.group(0))
        else:
            out.append('$$\n' + match.group(0) + '\n$$')
        pos = end
    out.append(text[pos:])
    return ''.join(out)


def protect_math(text):
    """Вырезать математику/валюту плейсхолдерами. Обёртка над rendering.py —
    единая точка правды для границ формулы во всём проекте (сайт и
    конвертер должны видеть одну и ту же границу)."""
    return _protect_math_and_currency(text)


def restore_math(text, protected):
    """Вернуть математику на место НЕТРОНУТОЙ (без HTML-экранирования —
    конвертер производит markdown-текст, не HTML, экранирование делает
    rendering.py на следующем шаге, при показе)."""
    def repl(match):
        return protected[int(match.group(1))]
    from problems.rendering import _PLACEHOLDER_RE
    return _PLACEHOLDER_RE.sub(repl, text)
