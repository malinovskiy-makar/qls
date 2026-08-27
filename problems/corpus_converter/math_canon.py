# -*- coding: utf-8 -*-
"""Канонизация математики — Шаг 2 архитектуры из аудита 2026-08-27.

ОТДЕЛЬНАЯ стадия, применяемая ПОСЛЕ `convert_text_field`, а не правка
внутри него. Причина принципиальная: у `convert_text_field` есть свой
контракт и живые регрессии (#41612, #26337, #47127, #41824), и менять
его семантику молча — ровно та ошибка, из-за которой прежний шлюз
считал себя готовым. Здесь только добавляется новый этап поверх.

Что делает (по разделам аудита):
* `R-ENV` — math-окружение (`equation*`, `cases`, `align*`, …), оставшееся
  ВНЕ разделителей, заворачивается в один `$$…$$`. Без этого markdown
  разрывает его `<br>`-ами, и KaTeX уже не может собрать формулу.
* `K-ERR`/`DOLLAR` — вложенные `$…$`, `\\[…\\]`, `\\(…\\)` внутри формулы
  снимаются: KaTeX падает с «Can't use function '$' in math mode»
  (живой #30172).
* `K-TEXT` — русская речь внутри формулы оборачивается в `\\text{…}`,
  иначе пробелы в math mode игнорируются и слова слипаются в курсивную
  кашу (живой #30081, 397 формул в 183 карточках по замеру аудита).
* Юникодные операторы `≤ ≥ ∈ → √ ≠` и типографский минус приводятся к
  TeX-командам.

Чего НЕ делает намеренно: не трогает текстовые окружения (`quote`,
`tabular`, `figure` — их маршрут в семантический HTML, Фаза 4), не
чинит неизвестные макросы (Фаза 5 — их нельзя угадывать) и не трогает
типографику вне формул (это работа `normalize_dashes` в `core.py`).
"""
from __future__ import annotations

import re

from problems.corpus_converter.tex_lexer import (
    TokenKind, math_span, tokenize,
)

#: Окружения, которые обязаны жить внутри math-разделителей. Найденные
#: снаружи — заворачиваются в `$$…$$` целиком (обёртка `\begin{…}`
#: остаётся: без неё KaTeX не построит ни скобку `cases`, ни выравнивание).
#:
#: ⚠️ Состав списка ЗАМЕРЕН настоящим KaTeX 0.16.9, а не взят из
#: рекомендации. Аудит советовал «equation/equation* снаружи убрать», но
#: прямая проверка `renderToString` показала, что KaTeX эти окружения
#: поддерживает — снимать обёртку не нужно и было бы потерей смысла.
#: Действительно неподдерживаемые вынесены в `_UNSUPPORTED_ENV_MAP` ниже.
MATH_ENVIRONMENTS = frozenset({
    'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
    'aligned', 'gathered', 'array', 'cases', 'split', 'matrix', 'pmatrix',
    'bmatrix', 'vmatrix', 'smallmatrix', 'alignat', 'alignat*',
    # неподдерживаемые — заворачиваются вместе с заменой имени (ниже)
    'multline', 'multline*', 'eqnarray', 'eqnarray*', 'subequations',
})

#: Замер KaTeX 0.16.9: «No such environment». Заменяются на ближайший
#: поддерживаемый аналог, а не выбрасываются:
#: * `multline` — одна формула, разложенная по строкам → `gathered`;
#: * `eqnarray` — устаревшее rcl-выравнивание, сам LaTeX рекомендует
#:   вместо него `align`/`aligned` → `aligned`;
#: * `subequations` — чистая обёртка нумерации без визуальной структуры,
#:   снимается целиком (содержимое остаётся).
#: Замена не «на глазок»: результат всё равно проверяется настоящим
#: рендером в шлюзе, и неверное отображение станет FAIL, а не тихим PASS.
_UNSUPPORTED_ENV_MAP = {
    'multline': 'gathered', 'multline*': 'gathered',
    'eqnarray': 'aligned', 'eqnarray*': 'aligned',
}
_UNWRAP_ENVIRONMENTS = frozenset({'subequations'})

#: Юникод → TeX. Пробел после команды обязателен: `\lex` слиплось бы в
#: неизвестную команду вместо `\le x`.
_UNICODE_OPERATORS = {
    '≤': r'\le ', '⩽': r'\le ', '≥': r'\ge ', '⩾': r'\ge ',
    '≠': r'\ne ', '∈': r'\in ', '∉': r'\notin ', '⊂': r'\subset ',
    '→': r'\to ', '←': r'\leftarrow ', '⇒': r'\Rightarrow ',
    '⇔': r'\Leftrightarrow ', '×': r'\times ', '·': r'\cdot ',
    '∞': r'\infty ', '±': r'\pm ', '≈': r'\approx ', '∑': r'\sum ',
    '∏': r'\prod ', '∆': r'\Delta ', '≡': r'\equiv ',
}
#: Типографские минус/тире внутри формулы — обычный ASCII-минус.
_UNICODE_MINUS = {'\u2212': '-', '\u2013': '-', '\u2014': '-'}

_SQRT_BRACED_RE = re.compile(r'√\s*\{([^{}]*)\}')
#: `√x`, `√2`, `√\alpha` — операнд до первого разделителя.
_SQRT_TOKEN_RE = re.compile(r'√\s*(\\[A-Za-z]+|[A-Za-z0-9]+)')

#: Уже обёрнутая речь — её трогать нельзя (иначе `\text{\text{если }}`).
_TEXT_CMD_RE = re.compile(r'\\text\s*\{[^{}]*\}')
#: Русская речь: слово или несколько слов через пробел/запятую, плюс
#: необязательный хвостовой пробел — он уходит ВНУТРЬ `\text{…}`,
#: потому что в math mode пробел снаружи игнорируется.
_CYRILLIC_RUN_RE = re.compile(r'[а-яёА-ЯЁ]+(?:[ \t,]+[а-яёА-ЯЁ]+)*[ \t]?')


def strip_nested_delimiters(body):
    """Снять вложенные разделители формул внутри уже-формулы, оставив
    содержимое (рекурсивно). `$x=0$` внутри `\\[…\\]` — живой #30172."""
    out = []
    i, n = 0, len(body)
    while i < n:
        span = math_span(body, i)
        if span is not None:
            end, inner, _display, _open = span
            out.append(strip_nested_delimiters(inner))
            i = end
            continue
        out.append(body[i])
        i += 1
    return ''.join(out)


def normalize_unicode_operators(body):
    """Юникодные операторы и типографский минус → TeX-команды."""
    body = _SQRT_BRACED_RE.sub(lambda m: r'\sqrt{' + m.group(1) + '}', body)
    body = _SQRT_TOKEN_RE.sub(lambda m: r'\sqrt{' + m.group(1) + '}', body)
    for src, dst in _UNICODE_OPERATORS.items():
        body = body.replace(src, dst)
    for src, dst in _UNICODE_MINUS.items():
        body = body.replace(src, dst)
    return body


def _wrap_runs(chunk):
    def repl(match):
        run = match.group(0)
        trailing = ' ' if run[-1] in ' \t' else ''
        core = run.rstrip(' \t')
        return r'\text{' + core + trailing + '}'
    return _CYRILLIC_RUN_RE.sub(repl, chunk)


def wrap_natural_language(body):
    """Русская речь внутри формулы → `\\text{…}`, уже обёрнутую не трогаем."""
    out = []
    pos = 0
    for match in _TEXT_CMD_RE.finditer(body):
        out.append(_wrap_runs(body[pos:match.start()]))
        out.append(match.group(0))
        pos = match.end()
    out.append(_wrap_runs(body[pos:]))
    return ''.join(out)


def rename_environment(body):
    """Заменить неподдерживаемые KaTeX окружения на аналоги (замер выше)."""
    for src, dst in _UNSUPPORTED_ENV_MAP.items():
        body = body.replace(f'\\begin{{{src}}}', f'\\begin{{{dst}}}')
        body = body.replace(f'\\end{{{src}}}', f'\\end{{{dst}}}')
    for name in _UNWRAP_ENVIRONMENTS:
        body = body.replace(f'\\begin{{{name}}}', '').replace(f'\\end{{{name}}}', '')
    return body


def canonicalize_math_body(body):
    """Полная канонизация содержимого одной формулы."""
    body = rename_environment(body)
    body = strip_nested_delimiters(body)
    body = normalize_unicode_operators(body)
    body = wrap_natural_language(body)
    return body


def canonicalize(text):
    """Текст (обычно — выход `convert_text_field`) → канонизированный текст.

    Идемпотентна: повторный прогон ничего не меняет. Это не косметика —
    стадия применяется и в шлюзе, и в подготовке отчёта, и расхождение
    между первым и вторым прогоном означало бы, что шлюз проверяет не
    тот текст, который увидит ученик.
    """
    out = []
    for token in tokenize(text):
        if token.kind in (TokenKind.INLINE_MATH, TokenKind.DISPLAY_MATH):
            body = canonicalize_math_body(token.body)
            if token.kind == TokenKind.DISPLAY_MATH:
                out.append('$$' + body + '$$')
            else:
                out.append('$' + body + '$')
            continue
        if token.kind == TokenKind.CURRENCY:
            # Знать, что это валюта, недостаточно: голый `$` в выводе
            # браузерный auto-render всё равно спарит с соседним и утащит
            # абзац в math mode (живые #26828, #35228 — замерено настоящим
            # KaTeX: после одной лишь канонизации K-TEXT оставался).
            # Экранируем: боевой `maskEscapedDollars` понимает `\$` и
            # показывает его обычным долларом.
            out.append(r'\$')
            continue
        if token.kind == TokenKind.ENVIRONMENT and token.name in MATH_ENVIRONMENTS:
            # Голое math-окружение: обёртка $$ снаружи, само окружение
            # остаётся внутри — KaTeX строит по нему скобку/выравнивание.
            out.append('$$' + canonicalize_math_body(rename_environment(token.raw)) + '$$')
            continue
        out.append(token.raw)
    return ''.join(out)
