# -*- coding: utf-8 -*-
"""Текстовые (не-math) окружения и команды — Шаг 3 архитектуры аудита.

Аудит нашёл 295 вхождений `\\begin{…}` вне математики: `quote`, `table`,
`tabular`, `figure`, `tcolorbox`, `caption`, `section`, `title`,
`multicolumn`, `diagbox`, `toprule/midrule/bottomrule`. KaTeX их не
видит вовсе, и на экране остаётся сырой LaTeX (живые #30058, #30921).

⚠️ Честная граница возможного. Аудит рекомендует «семантический HTML»:
`quote → <blockquote>`, `figure/caption → <figure>/<figcaption>`. Сегодня
это **недостижимо**, и не по лени: allow-list `nh3` в
`problems/rendering.py` пропускает только `p, strong, em, ul, ol, li, br,
code, pre, table, thead, tbody, tr, th, td`. `blockquote`, `figure`,
`figcaption` в него не входят и были бы срезаны. Расширение allow-list —
изменение границы безопасности показа, решение владельца (см.
[ADR 0031](../../docs/adr/0031-tikz-svg-blocked-by-sanitizer.md), там же
про картинки).

Поэтому здесь делается достижимое и полезное: обёртка СНИМАЕТСЯ, текст
остаётся видимым абзацем. Дефект «на экране сырой `\\begin{quote}`»
исчезает, семантика цитаты теряется — это честная деградация, а не
починка. Таблицы отдельного кода не требуют: `convert_tables` в
`core.py` уже переводит простой `tabular` в markdown-таблицу, а
markdown-таблицы allow-list пропускает.
"""
from __future__ import annotations

import re

from problems.corpus_converter.tex_lexer import TokenKind, tokenize

#: Окружения-обёртки: снимаются, содержимое остаётся. Ни одно из них не
#: несёт смысла, который выжил бы в текущем allow-list.
UNWRAP_ENVIRONMENTS = frozenset({
    'quote', 'quotation', 'center', 'flushleft', 'flushright', 'abstract',
    'minipage', 'tcolorbox', 'figure', 'figure*', 'table', 'table*',
    'small', 'large', 'footnotesize', 'scriptsize', 'spacing', 'adjustbox',
    'wrapfigure', 'samepage', 'sloppypar', 'multicols',
})

#: Команды с одним аргументом, у которых виден и нужен сам аргумент.
#:
#: ⚠️ `textbf`/`textit`/`emph` здесь ХОТЯ их и переводит стадия 1
#: (`convert_emphasis` → `**жирный**`). Стадия 1 требует `\textbf{` без
#: пробела, а в корпусе встречается `\textbf {Кривая Бевериджа}` — с
#: пробелом. Такая форма проваливалась мимо обеих стадий и доезжала до
#: экрана сырой командой (найдено выборочной проверкой FAIL-карточек
#: после прогона корпуса, живой #32536). Здесь они работают страховкой:
#: если стадия 1 уже сработала, этих команд в тексте просто нет.
_KEEP_ARG_COMMANDS = (
    'caption', 'section', 'subsection', 'subsubsection', 'paragraph',
    'title', 'textsc', 'centerline', 'sout', 'underline', 'uline',
    'mbox', 'texttt', 'textsf', 'textrm', 'textnormal',
    'textbf', 'textit', 'emph', 'fbox', 'framebox', 'MakeUppercase',
)
_KEEP_ARG_RE = re.compile(
    r'\\(?:' + '|'.join(_KEEP_ARG_COMMANDS) + r')\*?\s*\{([^{}]*)\}'
)

#: `\href{url}{текст}` → текст. Ссылку не строим: тега `a` в allow-list
#: нет, а `trust:true` у KaTeX аудит прямо запрещает.
_HREF_RE = re.compile(r'\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}')
_URL_RE = re.compile(r'\\url\s*\{([^{}]*)\}')

#: `\hyperlink{id}{текст}` — как `\href`, виден только второй аргумент.
_HYPERLINK_RE = re.compile(r'\\hyperlink\s*\{[^{}]*\}\s*\{([^{}]*)\}')
#: `\addcontentsline{toc}{section}{Название}` — служебная, три аргумента.
_ADDCONTENTS_RE = re.compile(
    r'\\addcontentsline\s*\{[^{}]*\}\s*\{[^{}]*\}\s*\{[^{}]*\}')

#: Команды-разметки, которые видны сырыми и смысла на экране не несут.
#: Размеры/начертания (`\large`, `\bf`, …) — переключатели без аргумента,
#: их роль берёт на себя CSS; `\cline{1-2}`, `\alph{…}` — служебные с
#: одним аргументом, он тоже снимается.
_DROP_COMMANDS_RE = re.compile(
    r'\\(?:label|ref|eqref|cite|index|nonumber|newpage|clearpage|'
    r'toprule|midrule|bottomrule|hline|cline|maketitle|tableofcontents|'
    r'raggedright|raggedleft|normalsize|itshape|bfseries|scshape|'
    r'large|Large|LARGE|huge|Huge|scriptsize|tiny|bf|it|rm|sf|tt|em|'
    r'center|centering|hrule|hrulefill|dotfill|alph|arabic|roman|'
    r'Alph|Roman|columnbreak|newline|linebreak|pagebreak|noalign|'
    r'rowcolor|arraybackslash|setlength|renewcommand|newcommand)\b'
    r'(?:\s*\{[^{}]*\})?'
)


def _clean_commands(chunk):
    chunk = _ADDCONTENTS_RE.sub('', chunk)
    chunk = _HREF_RE.sub(r'\1', chunk)
    chunk = _HYPERLINK_RE.sub(r'\1', chunk)
    chunk = _URL_RE.sub(r'\1', chunk)
    # дважды: `\textbf{\large Заголовок}` разбирается послойно, снаружи внутрь
    chunk = _KEEP_ARG_RE.sub(r'\1', chunk)
    chunk = _DROP_COMMANDS_RE.sub('', chunk)
    chunk = _KEEP_ARG_RE.sub(r'\1', chunk)
    return chunk


def convert_text_environments(text):
    """Снять текстовые обёртки и служебные команды ВНЕ математики.

    Математика не трогается вовсе: токены формул отдаются как есть —
    внутри них `\\text{…}`, `\\label` и прочее имеют другой смысл."""
    out = []
    for token in tokenize(text):
        if token.kind in (TokenKind.INLINE_MATH, TokenKind.DISPLAY_MATH,
                          TokenKind.CURRENCY, TokenKind.COMMENT):
            out.append(token.raw)
            continue
        if token.kind == TokenKind.ENVIRONMENT and token.name in UNWRAP_ENVIRONMENTS:
            # рекурсивно: внутри цитаты может лежать ещё одна обёртка
            out.append(convert_text_environments(token.body))
            continue
        if token.kind == TokenKind.ENVIRONMENT:
            out.append(token.raw)
            continue
        out.append(_clean_commands(token.raw))
    return ''.join(out)
