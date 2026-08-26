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


#: Команды-«воздух»: чисто оформительские, переносить некуда (задача CSS,
#: не текста) — CORPUS-FORMAT.md §3, строка «\\medskip, \\bigskip, ...».
_JUNK_COMMANDS = (
    r'\\medskip', r'\\bigskip', r'\\quad', r'\\qquad',
    r'\\noindent', r'\\centering',
)
_JUNK_COMMANDS_RE = re.compile('|'.join(_JUNK_COMMANDS))


def strip_junk_commands(text):
    """Убрать \\medskip/\\bigskip/\\quad/\\qquad/\\noindent/\\centering
    целиком, без замены."""
    return _JUNK_COMMANDS_RE.sub('', text)


#: \textcolor{цвет}{содержимое} — двухаргументная форма, содержимое остаётся.
_TEXTCOLOR_RE = re.compile(r'\\textcolor\{[^}]*\}\{([^}]*)\}')
#: \color{цвет} — переключатель без своих аргументов-содержимого, убирается целиком.
_COLOR_SWITCH_RE = re.compile(r'\\color\{[^}]*\}')


def strip_color(text):
    """Убрать \\color/\\textcolor, оставить содержимое без цвета."""
    text = _TEXTCOLOR_RE.sub(r'\1', text)
    text = _COLOR_SWITCH_RE.sub('', text)
    return text


#: Комментарий — '%' в начале строки (после необязательных пробелов),
#: НЕ экранированный '\%'. Ловушка задокументирована в атласе: снимать
#: комментарии нужно ДО остального разбора, но '\%' — легитимный процент.
_TEX_COMMENT_RE = re.compile(r'(^|\n)[ \t]*%[^\n]*', re.MULTILINE)


def strip_tex_comments(text):
    """Убрать TeX-комментарии (только в начале строк, не в середине текста)."""
    return _TEX_COMMENT_RE.sub(r'\1', text)


#: \textbf{X} -> **X**; \textit{X}/\emph{X} -> *X*. Нежадный [^}]* — без
#: вложенных фигурных скобок внутри аргумента (в банке их не встречалось,
#: см. атлас: собственных макросов в телах практически нет).
_TEXTBF_RE = re.compile(r'\\textbf\{([^}]*)\}')
_TEXTIT_EMPH_RE = re.compile(r'\\(?:textit|emph)\{([^}]*)\}')


def convert_emphasis(text):
    """LaTeX \\textbf/\\textit/\\emph -> markdown **/*. Уже-markdown
    **жирный**/*курсив* проходит без изменений (regex их не матчит).
    Вызывать ТОЛЬКО на math-protected тексте — иначе `$Q^*$` пострадает
    от парсера markdown позже, но сам этот шаг звёздочки не трогает вовсе,
    только \\textbf/\\textit/\\emph."""
    text = _TEXTBF_RE.sub(r'**\1**', text)
    text = _TEXTIT_EMPH_RE.sub(r'*\1*', text)
    return text


#: Только явные LaTeX-окружения — доверенный сигнал по sweep-диагностике
#: (corpus_format_sweep_20260824.md: "italic/список — шумные признаки").
#: Голая '-'/'N.'/'N)' в начале строки НЕ распознаётся как список нигде
#: в этом модуле — намеренно, это и есть защита от ловушек метода.
_ITEMIZE_RE = re.compile(r'\\begin\{itemize\}(.*?)\\end\{itemize\}', re.DOTALL)
_ENUMERATE_RE = re.compile(r'\\begin\{enumerate\}(.*?)\\end\{enumerate\}', re.DOTALL)
#: \item[X] — ручная метка (Школково: (а), А), 1) ...) — сохраняется как
#: текст пункта, не переинтерпретируется; \item без метки просто режет на пункты.
_ITEM_RE = re.compile(r'\\item(?:\[([^\]]*)\])?\s*')


def _split_items(body):
    items = []
    # \item[label]?content — re.split с группой возвращает
    # [pre, label_or_None, content, label_or_None, content, ...]
    parts = _ITEM_RE.split(body)
    pre = parts[0]
    if pre.strip():
        # Текст до первого \item внутри itemize/enumerate не встречался
        # в проверенных источниках — не теряем его молча.
        items.append(pre.strip())
    for i in range(1, len(parts), 2):
        label = parts[i]
        content = parts[i + 1].strip() if i + 1 < len(parts) else ''
        if label:
            items.append(f'{label} {content}'.strip())
        else:
            items.append(content)
    return [item for item in items if item]


def convert_lists(text):
    """\\begin{itemize}/\\begin{enumerate} -> markdown-списки с реальными
    переносами строк. Не трогает ничего вне этих двух явных окружений."""
    def repl_itemize(match):
        items = _split_items(match.group(1))
        return '\n'.join(f'- {item}' for item in items)

    def repl_enumerate(match):
        items = _split_items(match.group(1))
        return '\n'.join(f'{i}. {item}' for i, item in enumerate(items, start=1))

    text = _ITEMIZE_RE.sub(repl_itemize, text)
    text = _ENUMERATE_RE.sub(repl_enumerate, text)
    return text


_TABULAR_RE = re.compile(r'\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}', re.DOTALL)
_MULTICOL_ROW_RE = re.compile(r'\\multicolumn|\\multirow')
_HLINE_RE = re.compile(r'\\hline')


def _tabular_to_markdown(body):
    """Тело tabular (между {cols} и \\end) -> markdown-таблица.

    Строки режутся по '\\\\', ячейки — по '&'. \\hline игнорируется
    (роль отступа/рамки, в markdown-таблице у неё нет аналога)."""
    body = _HLINE_RE.sub('', body)
    rows = [row.strip() for row in body.split('\\\\') if row.strip()]
    grid = [[cell.strip() for cell in row.split('&')] for row in rows]
    if not grid:
        return None
    width = len(grid[0])
    lines = ['| ' + ' | '.join(grid[0]) + ' |']
    lines.append('| ' + ' | '.join(['---'] * width) + ' |')
    for row in grid[1:]:
        lines.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(lines)


def convert_tables(text):
    """Простые \\begin{tabular} (без multicolumn/multirow) -> markdown-таблицы.
    Сложные — не трогаем, сигнализируем True вторым элементом кортежа, ради
    ручной очереди (CORPUS-FORMAT.md §3: "слияние ячеек markdown-таблицей
    не выражается")."""
    complex_found = False
    out = []
    pos = 0
    for match in _TABULAR_RE.finditer(text):
        start, end = match.span()
        body = match.group(1)
        out.append(text[pos:start])
        if _MULTICOL_ROW_RE.search(body):
            complex_found = True
            out.append(match.group(0))
        else:
            markdown_table = _tabular_to_markdown(body)
            if markdown_table is not None:
                out.append(markdown_table)
            else:
                # Таблица не конвертирована (пусто, вырождена или др.) —
                # оставляем как есть, но флагируем для ручной очереди.
                complex_found = True
                out.append(match.group(0))
        pos = end
    out.append(text[pos:])
    return ''.join(out), complex_found


_FOOTNOTE_RE = re.compile(r'\s*\\footnote\{([^}]*)\}')


def extract_footnotes(text):
    """Вырезать \\footnote{...} из текста, собрать содержимое по порядку.
    Пробел ПЕРЕД сноской в исходнике съедается вместе с ней, чтобы не
    оставить двойной пробел на месте вырезанной сноски."""
    notes = []

    def repl(match):
        notes.append(match.group(1))
        return ''

    result = _FOOTNOTE_RE.sub(repl, text)
    return result, notes


def append_footnote_notes(text, notes):
    """Дописать сноски в конец отдельным абзацем «Примечание: …» —
    CORPUS-FORMAT.md §3: "ссылку-маркер в тексте не пытаться имитировать"."""
    if not notes:
        return text
    if len(notes) == 1:
        lines = [f'Примечание: {notes[0]}']
    else:
        lines = [f'Примечание {i}: {note}' for i, note in enumerate(notes, start=1)]
    return text + '\n\n' + '\n'.join(lines)


def normalize_dashes(text):
    """--- -> —, -- -> –, ' - ' (тире между словами) -> ' — '.

    Одиночный '-' без пробелов с обеих сторон НЕ трогается — он почти
    всегда часть слова (составное существительное) или знак минуса перед
    числом, а не тире (CORPUS-FORMAT.md §3 обсуждает только сам факт
    нормализации, различение "тире vs дефис" — эвристика этой сессии,
    задокументированная явно, а не молчаливое допущение)."""
    text = text.replace('---', '—')
    text = text.replace('--', '–')
    text = re.sub(r'(?<=\S) - (?=\S)', ' — ', text)
    return text


#: Прямые кавычки режутся ПАРАМИ по очереди: первая пара -> «», вторая
#: -> «», и так далее — нечётная кавычка (без пары) не трогается вовсе.
_STRAIGHT_QUOTE_RE = re.compile(r'"([^"]*)"')
_ANGLE_QUOTE_RE = re.compile(r'<<([^>]*)>>')


def normalize_quotes(text):
    """<<...>>, "..." -> «...» — подтверждённый домашний стандарт
    (test_fix_latex_junk.py:66: <<Ромашка>> -> «Ромашка» — починка, не порча)."""
    text = _ANGLE_QUOTE_RE.sub(r'«\1»', text)
    text = _STRAIGHT_QUOTE_RE.sub(r'«\1»', text)
    return text
