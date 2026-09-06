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
#:
#: `boxed` и `footnote` добавлены по разбору отказов трёх новых
#: источников (`diagnose_new_sources`): `Ответ: \boxed{(b)}` вне
#: математики (живой #53730) и `\footnote{… \textit{…}}` (живой #54399).
#: Рамку и сноску в текущем allow-list не нарисовать — остаётся текст,
#: и это честная деградация, а не починка (см. docstring модуля).
_KEEP_ARG_COMMANDS = (
    'caption', 'section', 'subsection', 'subsubsection', 'paragraph',
    'title', 'textsc', 'centerline', 'sout', 'underline', 'uline',
    'mbox', 'texttt', 'textsf', 'textrm', 'textnormal',
    'textbf', 'textit', 'emph', 'fbox', 'framebox', 'MakeUppercase',
    'boxed', 'footnote', 'footnotetext',
)
#: Длинные раньше коротких: иначе `section` откусил бы начало у
#: `\subsection` — не здесь (шаблон якорится на `\`), но правило дешёвое
#: и защищает от будущих пар вроде `text`/`textbf`.
_KEEP_ARG_START_RE = re.compile(
    r'\\(?:' + '|'.join(sorted(_KEEP_ARG_COMMANDS, key=len, reverse=True))
    + r')\*?[ \t]*\{'
)

#: Команды-символы: на экране это обычный знак, а не разметка.
#: `\ldots` — самая частая (65 задач трёх источников), `\checkmark` — 5,
#: валюты — 2. ВНУТРИ математики не трогаются: там их рисует KaTeX.
SYMBOL_COMMANDS = {
    r'\ldots': '…', r'\dots': '…', r'\textellipsis': '…',
    r'\checkmark': '✓', r'\times': '×',
    r'\pounds': '£', r'\euro': '€', r'\textdegree': '°',
    r'\textnumero': '№', r'\textperthousand': '‰',
}
#: Хвостовая пустая группа — часть записи команды (`\ldots{}`, живой
#: #54413), а не отдельный текст: без неё на экране осталось бы `{}`.
_SYMBOL_RE = re.compile(
    '(' + '|'.join(re.escape(k) for k in
                   sorted(SYMBOL_COMMANDS, key=len, reverse=True))
    + r')(?![A-Za-z])(\{\})?'
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
#: ⚠️ `small` и `footnotesize` в первой версии были пропущены, хотя
#: соседние `large`/`scriptsize`/`tiny` стояли — чистая дыра в списке,
#: найденная разбором отказов новых источников. `hfill` и отбивки
#: (`smallskip`/`medskip`/`bigskip`) — оттуда же: `\hfill (3 балла)`
#: у 14 задач (живой #54179).
_DROP_COMMANDS_RE = re.compile(
    r'\\(?:label|ref|eqref|cite|index|nonumber|newpage|clearpage|'
    r'toprule|midrule|bottomrule|hline|cline|maketitle|tableofcontents|'
    r'raggedright|raggedleft|normalsize|itshape|bfseries|scshape|'
    r'large|Large|LARGE|huge|Huge|scriptsize|tiny|bf|it|rm|sf|tt|em|'
    r'center|centering|hrule|hrulefill|dotfill|alph|arabic|roman|'
    r'Alph|Roman|columnbreak|newline|linebreak|pagebreak|noalign|'
    r'rowcolor|arraybackslash|setlength|renewcommand|newcommand|'
    r'smallskip|medskip|bigskip|addlinespace|noindent|'
    r'hfill|vfill|hfil|vfil|footnotesize|small|qedhere|qed)\b'
    r'(?:\s*\{[^{}]*\})?'
)

#: Плейсхолдер для математики и нетронутых окружений на время чистки
#: команд. Внутри — только цифры: ни скобок, ни обратного слеша, поэтому
#: счётчик скобок в `_unwrap_keep_arg` о него не спотыкается.
_MASK_TEMPLATE = '\x00{}\x00'
_MASK_RE = re.compile('\x00(\\d+)\x00')

#: Необязательный аргумент окружения-обёртки: `\begin{figure}[htpb]`
#: оставлял на экране строку `[htpb]` у 319 задач трёх источников.
#: Шлюз этого НЕ ловит — в `[htpb]` нет обратного слеша.
_LEADING_OPTIONAL_RE = re.compile(r'\A[ \t]*\[[^\]\n]{0,40}\]')
#: Окружения с ОБЯЗАТЕЛЬНЫМ аргументом: у них после `\begin{...}` идёт
#: ещё и `{...}` (ширина колонки, число колонок), тоже невидимая разметка.
_ENV_WITH_ARG = frozenset({
    'minipage', 'adjustbox', 'multicols', 'wrapfigure', 'spacing',
})
_LEADING_GROUP_RE = re.compile(r'\A[ \t]*\{[^{}\n]{0,60}\}')


def _find_matching_brace(text, open_index):
    """Индекс парной `}` для `{` в позиции `open_index`, или -1.

    Экранированная скобка (`\\{`) не считается — иначе `\\{1, 2\\}`
    внутри аргумента съел бы закрывающую скобку команды."""
    depth = 0
    i = open_index
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _unwrap_keep_arg(text):
    r"""`\cmd{...}` → содержимое, со счётом ВЛОЖЕННЫХ скобок.

    Прежний `[^{}]*` не брал ни вложенную группу
    (`\footnote{… \textit{…}}`, живой #54399), ни аргумент с формулой
    внутри (`\subsubsection*{… $t \to \infty$ …}`, живой #53909): во
    втором случае лексер резал команду на три токена, и шаблон не видел
    её целиком. Поэтому чистка идёт по тексту с ЗАМАСКИРОВАННОЙ
    математикой, а границы аргумента ищутся счётчиком скобок."""
    out = []
    pos = 0
    while True:
        match = _KEEP_ARG_START_RE.search(text, pos)
        if match is None:
            out.append(text[pos:])
            return ''.join(out)
        close = _find_matching_brace(text, match.end() - 1)
        if close == -1:
            # Скобка не закрыта — материал сломан. Оставляем как есть,
            # шлюз честно забракует такую задачу.
            out.append(text[pos:match.end()])
            pos = match.end()
            continue
        out.append(text[pos:match.start()])
        out.append(_unwrap_keep_arg(text[match.end():close]))
        pos = close + 1


def _clean_commands(chunk):
    chunk = _ADDCONTENTS_RE.sub('', chunk)
    chunk = _HREF_RE.sub(r'\1', chunk)
    chunk = _HYPERLINK_RE.sub(r'\1', chunk)
    chunk = _URL_RE.sub(r'\1', chunk)
    # дважды: `\textbf{\large Заголовок}` разбирается послойно, снаружи внутрь
    chunk = _unwrap_keep_arg(chunk)
    chunk = _DROP_COMMANDS_RE.sub('', chunk)
    chunk = _unwrap_keep_arg(chunk)
    chunk = _SYMBOL_RE.sub(lambda m: SYMBOL_COMMANDS[m.group(1)], chunk)
    return chunk


def _strip_environment_arguments(name, body):
    r"""Снять невидимую разметку в начале тела окружения-обёртки.

    `\begin{figure}[htpb]` кладёт `[htpb]` прямо в `body`, и после
    снятия обёртки эта строка оставалась на экране (319 задач)."""
    body = _LEADING_OPTIONAL_RE.sub('', body)
    if name in _ENV_WITH_ARG:
        body = _LEADING_GROUP_RE.sub('', body)
        body = _LEADING_OPTIONAL_RE.sub('', body)
    return body


def _unwrap_environments(text):
    """Снять окружения-обёртки, рекурсивно. Ничего больше не трогает."""
    out = []
    for token in tokenize(text):
        if token.kind == TokenKind.ENVIRONMENT and token.name in UNWRAP_ENVIRONMENTS:
            # рекурсивно: внутри цитаты может лежать ещё одна обёртка
            out.append(_unwrap_environments(
                _strip_environment_arguments(token.name, token.body)))
            continue
        out.append(token.raw)
    return ''.join(out)


def convert_text_environments(text):
    r"""Снять текстовые обёртки и служебные команды ВНЕ математики.

    Математика не трогается вовсе: на время чистки команд формулы,
    комментарии, валюта и НЕснимаемые окружения заменяются
    плейсхолдерами — внутри них `\text{…}`, `\label` и прочее имеют
    другой смысл.

    ⚠️ Маскировка, а не «чистить каждый текстовый токен отдельно»
    (как было раньше): аргумент команды может СОДЕРЖАТЬ формулу, и
    тогда лексер режет команду на три токена. `\subsubsection*{2.
    Предельный переход при $t \to \infty$}` (живой #53909) поэтому и
    доезжал до экрана сырым."""
    text = _unwrap_environments(text)
    saved = []
    parts = []
    for token in tokenize(text):
        if token.kind in (TokenKind.INLINE_MATH, TokenKind.DISPLAY_MATH,
                          TokenKind.CURRENCY, TokenKind.COMMENT,
                          TokenKind.ENVIRONMENT):
            parts.append(_MASK_TEMPLATE.format(len(saved)))
            saved.append(token.raw)
            continue
        parts.append(token.raw)
    cleaned = _clean_commands(''.join(parts))
    return _MASK_RE.sub(lambda m: saved[int(m.group(1))], cleaned)
