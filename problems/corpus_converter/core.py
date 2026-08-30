# -*- coding: utf-8 -*-
"""Общий конвертер текста задачи к целевому формату (CORPUS-FORMAT.md §3).

Пилот: UPDATE (ILE, задача уже в базе) и INSERT (Школково, парсинг с диска).
Чистые функции — вход текст, выход текст/структура, никакого I/O и ORM.
"""
from __future__ import annotations

import re

from problems.rendering import _protect_math_and_currency

#: Голые окружения — те же, что CORPUS-FORMAT.md §3 и атлас источников:
#: equation/align/gather (со звёздочкой или без). cases НЕ входит — оно
#: почти всегда уже внутри более крупной формулы (см. CORPUS-FORMAT.md
#: Приложение, п.1) и никогда не оборачивается само по себе.
_BARE_ENV_NAMES = ('equation', 'align', 'gather')
_BARE_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(f'{name}\\*?' for name in _BARE_ENV_NAMES) + r')\}.*?\\end\{\1\}',
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


#: Мусорные символы источников, найденные атласом у SolveHub: control-char
#: U+0002 и BOM U+FEFF внутри слов (следы мягкого переноса из PDF), U+2028
#: (line separator) вместо обычного \n, nbsp (U+00A0) вместо пробела,
#: псевдо-HTML `<\li>` (опечатка экспорта, 11 задач). Снимаем ПЕРВЫМ шагом
#: конвейера — иначе мусор может помешать распознаванию TeX-комментариев/
#: разметки на следующих шагах.
_CONTROL_CHARS_RE = re.compile('[\u0002\ufeff]')


def strip_control_and_bom_chars(text):
    """Убрать control-char/BOM-мусор, нормализовать U+2028/nbsp, убрать
    псевдо-HTML `<\\li>` (CORPUS_FORMAT_ATLAS: сюрпризы SolveHub)."""
    text = _CONTROL_CHARS_RE.sub('', text)
    text = text.replace('\u2028', '\n')
    text = text.replace('\u00a0', ' ')
    text = text.replace('<\\li>', '')
    return text


#: Archive 3 (атлас, "Ловушка №1"): 61 из 164 задач с `tabular` держат ВСЮ
#: таблицу внутри `$`/`$$` — таблица не формула, KaTeX её не осилит. Снимаем
#: обёртку ДО protect_math, чтобы дальше таблица шла обычным путём
#: convert_tables, а не пряталась как непрозрачный математический плейсхолдер.
_MATH_WRAPPED_TABLE_RE = re.compile(
    r'\$\$?\s*(\\begin\{tabular\}.*?\\end\{tabular\})\s*\$\$?',
    re.DOTALL,
)
#: \text{X} внутри такой таблицы имел смысл ТОЛЬКО пока таблица была внутри
#: математики — после снятия $$ это осиротевшая команда, а не текст.
#: Найдено на живой задаче #41535 при проверке этой функции на реальных
#: данных: ячейки вида \text{День недели} иначе остались бы сырым LaTeX.
_ORPHANED_TEXT_CMD_RE = re.compile(r'\\text\{([^}]*)\}')


def unwrap_math_wrapped_tables(text):
    """Снять $/$$ обёртку вокруг целой \\begin{tabular}...\\end{tabular},
    заодно снять осиротевшие \\text{} внутри неё (см. _ORPHANED_TEXT_CMD_RE)."""
    def repl(match):
        return _ORPHANED_TEXT_CMD_RE.sub(r'\1', match.group(1))
    return _MATH_WRAPPED_TABLE_RE.sub(repl, text)


#: МатЭк (атлас, "Главный сюрприз"): 46 задач держат ТЕЛО таблицы без
#: обёртки \\begin{tabular}{...} — она потерялась при импорте, остались
#: только \\hline и строки с '&', разделённые пустыми строками (проверено
#: по живым задачам #30025/#30026: "\\hline\n& L & R & C\n \\hline\nA & ...").
#: Реконструируем обёртку, чтобы дальше сработал обычный convert_tables.
#: Срабатывает ТОЛЬКО когда в тексте вообще нет \\begin{tabular} — так
#: исключается риск задеть уже нормально обёрнутую таблицу в том же тексте.
_ORPHAN_TABLE_BLOCK_RE = re.compile(
    r'(?P<block>(?:[ \t]*\\hline[ \t]*\n)'
    r'(?:[^\n]*&[^\n]*\n[ \t]*\\hline[ \t]*\n)+'
    r'[^\n]*&[^\n]*)'
)


def reconstruct_orphaned_tabular(text):
    """Обернуть осиротевшее тело таблицы МатЭк в синтетический
    \\begin{tabular}{...}...\\end{tabular}."""
    if '\\begin{tabular}' in text:
        return text

    def repl(match):
        rows = [row.strip() for row in re.split(r'\\hline', match.group('block')) if row.strip()]
        if not rows:
            return match.group('block')
        width = max(row.count('&') + 1 for row in rows)
        cols = 'l' * width
        body = ' \\\\ '.join(rows)
        return f'\\begin{{tabular}}{{{cols}}}{body}\\end{{tabular}}'

    return _ORPHAN_TABLE_BLOCK_RE.sub(repl, text)


#: Archive 3 (ревью 2026-08-26, задача #33817): другой сорт осиротевшей
#: таблицы, чем у МатЭк выше — строки держатся ГОЛЫМИ `&`, без единого
#: `\hline` вообще, разделены пустыми строками. Замерено по всей базе
#: Archive 3 (13699 задач, только чтение): 19 задач после исключения
#: ложных срабатываний внутри `\begin{cases}` (кусочная функция — тоже
#: использует `&`, но это не таблица).
_BARE_AMPERSAND_ROW_RE = re.compile(
    r'(?:[^\n]*&[^\n]*\n[ \t]*\n){1,}[^\n]*&[^\n]*'
)


def _is_inside_cases_block(text, start, end):
    """span [start, end) целиком внутри \\begin{cases}...\\end{cases}?
    Кусочная функция тоже пишется через '&', но это не табличные данные —
    оборачивать её в tabular значило бы исказить смысл, не просто формат."""
    for match in re.finditer(r'\\begin\{cases\}.*?\\end\{cases\}', text, re.DOTALL):
        if match.start() <= start and end <= match.end():
            return True
    return False


def reconstruct_bare_ampersand_table(text):
    """Обернуть блок голых `&`-строк (без `\\hline`, без `\\begin{tabular}`)
    в синтетический tabular. Не трогает блоки внутри `\\begin{cases}` —
    видит их, чтобы дальнейшая проверка (has_unreconstructed_table_markup)
    не молчала о них, но не оборачивает как таблицу."""
    if '\\begin{tabular}' in text:
        return text

    def repl(match):
        if _is_inside_cases_block(text, match.start(), match.end()):
            return match.group(0)
        rows = [row.strip() for row in match.group(0).split('\n') if row.strip() and '&' in row]
        if len(rows) < 2:
            return match.group(0)
        width = max(row.count('&') + 1 for row in rows)
        cols = 'l' * width
        body = ' \\\\ '.join(rows)
        return f'\\begin{{tabular}}{{{cols}}}{body}\\end{{tabular}}'

    return _BARE_AMPERSAND_ROW_RE.sub(repl, text)


def has_unreconstructed_bare_ampersand_rows(text):
    """После обеих попыток реконструкции (\\hline-стиль МатЭк и голый
    стиль Archive 3 выше) голые `&`-строки могут остаться БЕЗ
    `\\begin{tabular}` — блок внутри `\\begin{cases}` (не таблица, трогать
    нельзя) или строк меньше двух (реконструировать не из чего). Раньше
    такой текст молча терял структуру: ни warning, ни complex_table.
    Вызывается ПОСЛЕ reconstruct_orphaned_tabular/reconstruct_bare_
    ampersand_table в конвейере, поэтому оставшееся совпадение — уже
    не то, что эти функции способны обработать сами."""
    if '\\begin{tabular}' in text:
        return False
    return bool(_BARE_AMPERSAND_ROW_RE.search(text))


#: Ревью 2026-08-26 (владелец лично просмотрел review_samples.html):
#: `\begin{cases}...\end{cases}` — тот же баг импорта, что и у таблиц выше
#: (построчный `\\` потерян, строки разошлись по пустым строкам), но это
#: НЕ table-специфичный дефект: сигнал — пустая строка между сегментами,
#: не `&` (живой пример #28255, МатЭк: `100-0.25x,0\leq x\leq 80` — строки
#: без единого `&`, разделены запятой и пустой строкой). Прежняя страховка
#: (`_BARE_AMPERSAND_ROW_RE`) требует `&` в каждой строке и потому не ловила
#: этот вариант вовсе — сломанный cases проходил без единого warning.
#: Замерено заново по всем 4 легаси-источникам (честный пересчёт, старая
#: цифра 164 сильно занижена — см. report.md).
_CASES_BLOCK_RE = re.compile(r'\\begin\{cases\}(.*?)\\end\{cases\}', re.DOTALL)


def reconstruct_cases_row_separators(text):
    """Восстановить `\\\\` между строками `\\begin{cases}`, если они
    разошлись по пустым строкам — единственный надёжный сигнал границы
    строки здесь пустая строка, `&` не обязателен (в отличие от таблиц,
    cases не превращается в другую структуру — обёртка `\\begin{cases}`
    уже на месте, чинится только разделитель внутри неё).

    Срабатывает, только если сегментов минимум два (однозначно) — при
    одном сегменте (нет пустой строки вовсе) гадать не из чего, оставляем
    как есть, дальше это поймает has_broken_cases_rows.

    Второй сигнал (сессия 2026-08-27): одиночный `\\n` без пустой строки,
    подтверждённый количеством `&` в теле. Строки `cases` в LaTeX идут
    через `&`, поэтому если сегментов после разбиения по `\\n` РОВНО
    столько же, сколько `&`, это не догадка — `&` независимо подтверждает
    число строк (ровно тот же принцип, каким has_broken_cases_rows уже
    считает строки для своей проверки). Несовпадение (например перенос
    длинной формулы, а не граница строки) оставляет блок как есть —
    дальше его поймает has_broken_cases_rows. Проверено на живых данных
    (Archive 3 #41824, #41550, #41293×3, #41236, #39939) — единственные
    7 блоков по всем 4 источникам, где признак сходится."""
    def repl(match):
        body = match.group(1)
        if '\\\\' in body:
            return match.group(0)
        segments = [seg.strip() for seg in re.split(r'\n[ \t]*\n', body) if seg.strip()]
        if len(segments) >= 2:
            segments = [' '.join(seg.split()) for seg in segments]
            return '\\begin{cases}' + ' \\\\ '.join(segments) + '\\end{cases}'
        ampersands = body.count('&')
        if ampersands:
            line_segments = [seg.strip() for seg in body.split('\n') if seg.strip()]
            if len(line_segments) >= 2 and len(line_segments) == ampersands:
                line_segments = [' '.join(seg.split()) for seg in line_segments]
                return '\\begin{cases}' + ' \\\\ '.join(line_segments) + '\\end{cases}'
        return match.group(0)

    return _CASES_BLOCK_RE.sub(repl, text)


#: Построчный разделитель LaTeX — `\\`. Считаем и `\\[8pt]` тоже: там
#: разделитель на месте, добавлен только межстрочный интервал.
_ROW_SEP_RE = re.compile(r'\\\\')


def has_broken_cases_rows(text):
    """Проверка по ПРАВИЛУ, а не по списку известных паттернов поломки:
    внутри `\\begin{cases}...\\end{cases}` разделителей `\\\\` должно быть
    ровно на единицу меньше, чем строк условий. Меньше — значит строки
    слиплись, ЧЕМ бы они ни были разделены на самом деле (пустая строка,
    одиночный `\\n`, запятая, осиротевший `[8pt]`, что угодно ещё, чего мы
    пока не видели). Вызывается ПОСЛЕ reconstruct_cases_row_separators,
    поэтому всё, что дошло сюда сломанным, реконструкция уже не осилила.

    Сколько строк на самом деле:
    * есть `&` — считаем по нему. В `cases` ровно две колонки, значит
      больше одного `&` на строку быть не может: `&`-штук == строк.
      Маркер надёжный, поэтому правило применяется всегда.
    * нет `&` — считаем непустые строки, но ТОЛЬКО когда разделителей нет
      вовсе. Иначе перенос длинной формулы читается как лишняя строка —
      живой ложный пример #41599 (Archive 3): три строки, третья
      перенесена на две физические, разделителей честные два.

    Заменила прежнюю has_unreconstructed_cases_rows, которая флагировала
    любой блок вообще без `\\\\`. Разница на живых данных (замер по всем
    4 легаси-источникам, 1822 блока): новых поломок правило не нашло —
    все 95 совпали со старыми, — но сняло одно ложное срабатывание
    (#28419 МатЭк, честная одностроч­ная `\\begin{cases} p \\end{cases}`)
    и закрыло класс, который старая проверка увидеть не могла в принципе:
    разделители ЕСТЬ, но их не хватает."""
    for match in _CASES_BLOCK_RE.finditer(text):
        body = match.group(1)
        separators = len(_ROW_SEP_RE.findall(body))
        if '&' in body:
            rows = body.count('&')
        elif separators:
            continue
        else:
            rows = len([line for line in body.split('\n') if line.strip()])
        if separators < rows - 1:
            return True
    return False


#: Archive 3 (атлас, "Ловушка №2"): в 147 из 164 задач с `tabular` нет ни
#: одного `\\\\` — построчные разделители срезаны при импорте, строки
#: разошлись по пустым строкам (проверено по живым задачам #43945/#43880).
#: Реконструкция — часть _tabular_to_markdown (не отдельный шаг конвейера):
#: срабатывает только когда после снятия \\hline в теле НЕТ ни одного `\\\\`.
_MULTICOLS_RE = re.compile(r'\\begin\{multicols\}\{[^}]*\}|\\end\{multicols\}')


def strip_multicols_wrapper(text):
    """Убрать обёртку \\begin{multicols}{N}/\\end{multicols} (Archive 3,
    атлас: 243 задачи — вёрстка вариантов ответа в колонки, не таблица;
    содержимое остаётся текстом и идёт по обычному конвейеру списков)."""
    return _MULTICOLS_RE.sub('', text)


#: \begin{center}/\end{center} — центрирование, визуальная обёртка без
#: текстового смысла (ЛЭШ Гамма: живой пример — картинка внутри center).
_CENTER_RE = re.compile(r'\\begin\{center\}|\\end\{center\}')


def strip_center_wrapper(text):
    """Убрать обёртку \\begin{center}/\\end{center}, содержимое остаётся."""
    return _CENTER_RE.sub('', text)


#: \hypertarget{id}{текст} (Archive 3, атлас: 85 вхождений) — обёртка-якорь
#: для навигации по PDF, сам текст внутри второго аргумента виден и нужен.
_HYPERTARGET_RE = re.compile(r'\\hypertarget\{[^}]*\}\{([^}]*)\}')


def strip_hypertarget(text):
    """\\hypertarget{id}{текст} -> текст (якорь убран, содержимое остаётся)."""
    return _HYPERTARGET_RE.sub(r'\1', text)


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
    r'\\noindent', r'\\centering', r'\\par\b',
)
_JUNK_COMMANDS_RE = re.compile('|'.join(_JUNK_COMMANDS))
#: \\vspace{...}/\\hspace{...} — команды отступа с обязательным аргументом
#: (ЛЭШ Гамма: живой пример \\vspace{0.5em} между подпунктами условия).
#: В отличие от _JUNK_COMMANDS_RE эти требуют своего regex — у них есть
#: аргумент в {}, который тоже убирается целиком (это длина отступа, а не
#: видимый текст).
_JUNK_COMMANDS_WITH_ARG_RE = re.compile(r'\\(?:vspace|hspace)\{[^}]*\}')


def strip_junk_commands(text):
    """Убрать \\medskip/\\bigskip/\\quad/\\qquad/\\noindent/\\centering/
    \\vspace{}/\\hspace{} целиком, без замены."""
    text = _JUNK_COMMANDS_WITH_ARG_RE.sub('', text)
    text = _JUNK_COMMANDS_RE.sub('', text)
    return text


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


def split_item_body(body):
    """Тело списка (между тегами itemize/enumerate ИЛИ вообще без обёртки —
    вызывающая сторона решает) -> список пунктов по \\item. Публичная,
    переиспользуется в lesh.py: у ЛЭШ Гамма встречаются \\item внутри
    аргумента макроса \\z без itemize вовсе (см. вызов ниже и
    interpret_z_args в lesh.py)."""
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
        items = split_item_body(match.group(1))
        return '\n'.join(f'- {item}' for item in items)

    def repl_enumerate(match):
        items = split_item_body(match.group(1))
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
    (роль отступа/рамки, в markdown-таблице у неё нет аналога).

    Archive 3 (атлас, "Ловушка №2", 147 из 164 задач): построчные '\\\\'
    иногда срезаны импортом целиком, строки таблицы расходятся пустыми
    строками вместо них. Если после снятия \\hline в теле нет ни одного
    '\\\\' вовсе — реконструируем разделители по пустым строкам."""
    body = _HLINE_RE.sub('', body)
    if '\\\\' not in body:
        chunks = [' '.join(chunk.split()) for chunk in re.split(r'\n\s*\n', body)]
        chunks = [chunk for chunk in chunks if chunk]
        if len(chunks) >= 2:
            body = ' \\\\ '.join(chunks)
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


#: Строка-разделитель markdown-таблицы ("| --- | --- |") — синтаксис,
#: обязательный для markdown-it (`_tabular_to_markdown` его и порождает).
#: Найдено ревью 2026-08-26 при подготовке HTML-страницы для визуального
#: просмотра: normalize_dashes уже трогала эту строку, "---" превращался
#: в "—", markdown-it переставал узнавать таблицу вовсе (весь текст
#: рендерился одним <p> с сырыми "|" вместо <table>) — конвертер
#: производил разметку, которую собственный проверенный движок
#: `problems/rendering.py` показывал бы студенту сломанной.
_TABLE_DELIMITER_ROW_RE = re.compile(r'^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$')


#: Неразрывный пробел LaTeX. Одиночная тильда — всегда пробел; `~~`
#: (чужая разметка зачёркивания) не трогается вовсе.
_NBSP_RE = re.compile(r'(?<!~)~(?!~)')


def normalize_nbsp(text):
    """`~` -> обычный пробел.

    Пробел ОБЫЧНЫЙ, а не U+00A0: `strip_control_and_bom_chars` на шаге 0
    конвейера сознательно чистит nbsp как мусор источников, и класть его
    обратно на шаге 8 значило бы спорить с этим решением.

    ⚠️ Тот же класс, что `[htpb]` и `\\\\`: имени команды нет, поэтому
    ни `R-CMD` шлюза (ищет обратный слеш + слово), ни KaTeX (математики
    тут нет) этого не видят, и тильда доезжает до экрана буквально.
    Свипом по трём новым источникам: 187 задач из уже прошедших шлюз,
    407 случаев (живой #56899 — тильда одна в строке вместо отбивки).

    Идёт по ЗАЩИЩЁННОМУ тексту, как и `normalize_dashes`: внутри формулы
    `~` — это `\\sim`/`\\tilde`, и трогать его нельзя."""
    return _NBSP_RE.sub(' ', text)


def normalize_dashes(text):
    """--- -> —, -- -> –, ' - ' (тире между словами) -> ' — '.

    Одиночный '-' без пробелов с обеих сторон НЕ трогается — он почти
    всегда часть слова (составное существительное) или знак минуса перед
    числом, а не тире (CORPUS-FORMAT.md §3 обсуждает только сам факт
    нормализации, различение "тире vs дефис" — эвристика этой сессии,
    задокументированная явно, а не молчаливое допущение).

    Строки-разделители markdown-таблиц не трогаются вовсе — построчно,
    не одной заменой по всему тексту (см. _TABLE_DELIMITER_ROW_RE)."""
    out_lines = []
    for line in text.split('\n'):
        if _TABLE_DELIMITER_ROW_RE.match(line.strip()):
            out_lines.append(line)
            continue
        line = line.replace('---', '—')
        line = line.replace('--', '–')
        line = re.sub(r'(?<=\S) - (?=\S)', ' — ', line)
        out_lines.append(line)
    return '\n'.join(out_lines)


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


_MARKDOWN_IMAGE_RE = re.compile(r'!\[[^\]]*\]\(([^)]*)\)')
_INCLUDEGRAPHICS_RE = re.compile(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}')
_BARE_URL_RE = re.compile(r'https?://\S+?(?=[)\s]|$)')


def find_images(text):
    """Найти markdown-картинки, \\includegraphics и голые URL картинок.
    НЕ резолвит и НЕ трогает текст — только фиксирует ссылку и вид
    (CORPUS-FORMAT.md §3: "не резолвить..., не терять и не удалять
    молча")."""
    images = []
    covered_spans = []

    for match in _MARKDOWN_IMAGE_RE.finditer(text):
        images.append({'original_ref': match.group(1), 'kind': 'markdown'})
        covered_spans.append(match.span())

    for match in _INCLUDEGRAPHICS_RE.finditer(text):
        images.append({'original_ref': match.group(1), 'kind': 'includegraphics'})
        covered_spans.append(match.span())

    for match in _BARE_URL_RE.finditer(text):
        start, end = match.span()
        if any(cs <= start and end <= ce for cs, ce in covered_spans):
            continue
        images.append({'original_ref': match.group(0), 'kind': 'url'})

    return images


def convert_text_field(text):
    """Один текстовый кусок (statement/answer/solution/criteria/часть
    подпункта) через весь конвейер, в порядке, обязательном по §2б/§3:

    0. control-char/BOM/nbsp-мусор — до всего остального (может помешать
       распознаванию любой разметки на следующих шагах);
    1. TeX-комментарии — до всего остального (иначе '%' может съесть
       часть уже преобразованной разметки на следующих шагах);
    2. \\color/\\textcolor, \\hypertarget — до bold/italic (снимают
       обёртку, которая иначе помешала бы regex увидеть \\textbf изнутри);
    2а. снять $/$$ вокруг целой tabular (Archive 3) и восстановить
        осиротевшую обёртку tabular (МатЭк) — ДО защиты математики: первое
        превращает лже-формулу в обычную таблицу, второе даёт таблице
        границы, которые дальше найдёт convert_tables;
    3. обернуть голые equation/align/gather — ДО защиты математики, чтобы
       новая обёртка $$ была защищена вместе со всем остальным;
    4. защитить математику плейсхолдерами — всё, что дальше, физически
       не видит формулу (значит не может её сломать);
    5. вынести сноски (текст сноски может содержать плейсхолдеры формул —
       восстановятся на шаге 10 при добавлении сносок в конец);
    6. убрать junk-команды (включая multicols-обёртку), картинки —
       зафиксировать, не трогая текст;
    7. bold/italic, списки, таблицы;
    8. тире/кавычки — НА ЗАЩИЩЁННОМ тексте, ДО восстановления математики
       (плейсхолдер — это чистые цифры между служебными символами PUA,
       дефисов и кавычек в нём нет, значит замена его не заденет; а вот
       обратный порядок задевает — round-trip тест поймал живой пример:
       буквальный ' - ' внутри формулы вроде '$\\pi=P\\cdot Q-C(Q)$'
       после restore снова видим как текст и превращается в '—');
    9. вернуть математику на место;
    10. дописать сноски в конец.
    """
    if not text:
        return {'text_md': '', 'images': [], 'complex_table': False, 'warnings': []}

    warnings = []
    text = strip_control_and_bom_chars(text)
    text = strip_tex_comments(text)
    text = strip_color(text)
    text = strip_hypertarget(text)
    text = unwrap_math_wrapped_tables(text)
    text = reconstruct_orphaned_tabular(text)
    # cases — ДО bare_ampersand_table: уже починенный cases-блок (внутри
    # него теперь есть \\) не должен больше выглядеть как кандидат в
    # таблицу для следующего шага.
    text = reconstruct_cases_row_separators(text)
    text = reconstruct_bare_ampersand_table(text)
    bare_amp_unresolved = has_unreconstructed_bare_ampersand_rows(text)
    if bare_amp_unresolved:
        warnings.append(
            'голые "&"-строки без \\begin{tabular} не удалось разобрать как таблицу '
            '(похоже на кусочную функцию без обёртки \\begin{cases}, либо меньше двух строк) '
            '— в очередь на ручной разбор'
        )
    cases_unresolved = has_broken_cases_rows(text)
    if cases_unresolved:
        warnings.append(
            'сломанный \\begin{cases}: разделителей \\\\ меньше, чем строк условий '
            '(строки слиплись), восстановить однозначно не удалось '
            '— в очередь на ручной разбор'
        )
    text = wrap_bare_environments(text)
    protected_text, protected = protect_math(text)
    protected_text, notes = extract_footnotes(protected_text)
    protected_text = strip_junk_commands(protected_text)
    protected_text = strip_multicols_wrapper(protected_text)
    protected_text = strip_center_wrapper(protected_text)
    images = find_images(protected_text)
    protected_text = convert_emphasis(protected_text)
    protected_text = convert_lists(protected_text)
    protected_text, complex_table = convert_tables(protected_text)
    if complex_table:
        warnings.append('сложная таблица (multicolumn/multirow) — в очередь на ручной разбор')
    complex_table = complex_table or bare_amp_unresolved or cases_unresolved
    # Тире/кавычки — на ЕЩЁ защищённом тексте (плейсхолдеры математики
    # состоят только из цифр между служебными символами PUA, дефисов и
    # кавычек в них нет), а не после restore_math: иначе буквальный ' - '
    # или '"' внутри самой формулы (например '$\\pi = P \\cdot Q - C(Q)$')
    # снова становится видимым текстом и ловится этими же regex —
    # round-trip тест через problems.rendering.render_markdown поймал
    # именно эту порчу при обратном порядке.
    protected_text = normalize_nbsp(protected_text)
    protected_text = normalize_dashes(protected_text)
    protected_text = normalize_quotes(protected_text)
    restored = restore_math(protected_text, protected)
    # Сноска обязана пройти ТУ ЖЕ типографику, что и остальной текст.
    # `extract_footnotes` вырезает её ДО нормализации, а
    # `append_footnote_notes` дописывает ПОСЛЕ — сноска проскакивала мимо
    # целиком, и на экран доезжало «Примечание: Косатка~--- крупное»
    # (живой #54489, плюс ещё 5 задач с `--` и задачи с кавычками ``…'').
    # Нормализация идёт по ЕЩЁ защищённому тексту сноски, тем же порядком
    # и по той же причине, что и выше: формула внутри сноски не должна
    # попасть под правила для прозы.
    restored = append_footnote_notes(restored, [
        restore_math(normalize_quotes(normalize_dashes(normalize_nbsp(note))),
                     protected)
        for note in notes
    ])

    return {
        'text_md': restored,
        'images': images,
        'complex_table': complex_table,
        'warnings': warnings,
    }


#: а)/б)/в)... в начале строки — ЕДИНСТВЕННЫЙ доверенный маркер подпункта
#: в этом модуле (кириллический буквенный список с закрывающей скобкой).
#: Латинские a)/A) и другие конвенции атласа — вне пилота (только ILE и
#: Школково; у обоих в проверенных сэмплах кириллическая метка).
_SUBPOINT_RE = re.compile(r'(?m)^\s*([а-я])\)\s+')


def _detect_subpoints(text):
    """Разбить текст на (интро, [(метка, текст_пункта), ...]) по а)/б)/в).
    Без совпадений — (весь_текст, [])."""
    matches = list(_SUBPOINT_RE.finditer(text))
    if not matches:
        return text, []
    intro = text[:matches[0].start()].strip()
    parts = []
    for i, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((label, text[start:end].strip()))
    return intro, parts


def convert_problem(statement, answer='', solution='', existing_parts=None):
    """Вся задача (одно текстовое поле условия + опционально ответ/решение)
    через конвейер. Возвращает структуру Фазы 0 из брифа сессии.

    existing_parts=[(label, statement), ...] — режим UPDATE (ILE): части
    уже есть в базе как ProblemPart, из текста заново их не вычленяем,
    только прогоняем через convert_text_field как есть.

    existing_parts=None — режим INSERT (Школково): пытаемся найти
    а)/б)/в) внутри statement сами."""
    images = []
    warnings = []
    complex_table = False

    def _merge(field_result):
        nonlocal complex_table
        images.extend(field_result['images'])
        warnings.extend(field_result['warnings'])
        if field_result['complex_table']:
            complex_table = True
        return field_result['text_md']

    if existing_parts is not None:
        intro_text = statement
        raw_parts = existing_parts
    else:
        intro_text, raw_parts = _detect_subpoints(statement)

    statement_md = _merge(convert_text_field(intro_text))

    parts = []
    for label, part_statement in raw_parts:
        part_result = convert_text_field(part_statement)
        parts.append({
            'label': label,
            'statement_md': _merge(part_result),
            'answer': '',
        })

    answer_result = convert_text_field(answer)
    answer_md = _merge(answer_result)
    solution_result = convert_text_field(solution)
    solution_md = _merge(solution_result)

    return {
        'statement_md': statement_md,
        'parts': parts,
        'rubric': None,
        'answer_md': answer_md,
        'solution_md': solution_md,
        'images': images,
        'complex_table': complex_table,
        'warnings': warnings,
    }


def may_render_as_markdown(result):
    """Можно ли задаче с таким результатом конвертации ставить
    `content_format='markdown'`.

    ЕДИНСТВЕННАЯ точка этого решения. Боевая команда рендера обязана
    спрашивать здесь, а не сравнивать флаги у себя: `complex_table=True`
    означает «структуру разобрать не удалось, задача в очереди на ручной
    разбор» (multicolumn/multirow, сломанный `\\begin{cases}`, голые
    `&`-строки без обёртки). Показать такую задачу через markdown-рендерер
    значит показать её сломанной — она обязана остаться на PLAIN, пока
    человек её не починит. Очередь — reports/corpus_converter_scaleup/
    manual_review_queue.md, команда `corpus_manual_review_queue`.

    Отдельная функция, а не `if not result['complex_table']` в команде
    рендера, ровно затем, чтобы фильтр нельзя было забыть проверить
    руками: он часть логики и покрыт тестом."""
    return not result['complex_table']
