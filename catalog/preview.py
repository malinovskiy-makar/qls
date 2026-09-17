"""Превью условия для карточек каталога и «похожих»: сырой TeX для KaTeX,
заголовок-обрезок не показывается.

⚠️ ФОРМУЛЫ В ПРЕВЬЮ — TeX, ИХ РИСУЕТ KaTeX (решение владельца 17.09.2026).
До этого превью переводило формулы в текст («\\frac{a}{b}» → «a/b»), и
нарисованными оказывались только те карточки, где случайно уцелела пара `$`.
Теперь `tex_preview` оставляет формулы как есть, режет по словам и никогда
не внутри формулы, вырезает токены картинок `[[FIGURE:…]]`. KaTeX на
карточках зовётся при загрузке, после подмены выдачи фильтром и в модалке
(`renderMathIn` в `catalog/base.html`). Ещё раньше формулы вырезались
целиком, и превью оставалось с сиротами «в точке , » — карточка Notion
3d0b11c92bc1811e9d6de18e28c6c46e.

⚠️ ЗАГОЛОВОК-ОБРЕЗОК. У части источников в поле `title` лежат первые
полсотни знаков самого условия («Известно, что монополист получает
максимальную выр»). Показывать такое заголовком — повторять условие
дважды и обрывать его на полуслове. `looks_like_statement_cut` отличает
обрезок от названия («Вмешательство — 5»), и карточка с страницей задачи
показывают заголовок только для названия.
"""
from __future__ import annotations

import re

# Сколько знаков превью в карточке каталога (обрезка — по слову).
PREVIEW_CHARS = 180
# Заголовок длиннее этого без точки на конце — обрезок, а не название.
TITLE_MAX = 70

# Формулы — в порядке KaTeX на странице: `$$` и `\[` раньше `$`, иначе
# `$$x$$` читался бы как два пустых `$…$`.
_RX_MATH = re.compile(r'\$\$(.+?)\$\$|\\\[(.+?)\\\]|\$(.+?)\$|\\\((.+?)\\\)', re.DOTALL)
# Токены картинок и таблиц: страница задачи ставит на их место картинку.
_RX_TOKEN = re.compile(r'\[\[[A-Z_]+:[^\]]*\]\]')
_RX_CMD_ARG = re.compile(r'\\[a-zA-Z]+\*?\s*\{([^{}]*)\}')
_RX_CMD = re.compile(r'\\[a-zA-Z]+\*?')
_RX_SPACE = re.compile(r'[\s\u00a0]+')
# Экранированные знаки ВНЕ формулы: в карточке — сам знак.
_TEXT_ESCAPES = ((r'\%', '%'), (r'\_', '_'), (r'\&', '&'), (r'\#', '#'))

# Литеральный доллар (`\$` — цена, не формула) прячется на время разбора и
# возвращается как `\$`: его разбирает общий конвейер долларов страницы.
_DOLLAR = '\x00'


def _text_piece(piece):
    """Кусок вне формулы: экранированные знаки раскрыть, команды снять,
    оставив содержимое («\\textbf{Итог}» → «Итог»): вне формулы KaTeX их
    не рисует."""
    for escaped, char in _TEXT_ESCAPES:
        piece = piece.replace(escaped, char)
    piece = _RX_CMD_ARG.sub(r'\1', piece)
    return _RX_CMD.sub('', piece)


def _join(pieces):
    return _RX_SPACE.sub(' ', ''.join(pieces)).strip()


def tex_preview(statement, limit=PREVIEW_CHARS):
    """Условие одной строкой не длиннее `limit`: текст и формулы как TeX.

    Выносные формулы становятся строчными: блок посреди карточки рвёт
    строку. Разрез попадает в формулу — режем перед ней; если формула
    первая и сама длиннее `limit`, она остаётся целиком: пустое превью хуже
    длинного.
    """
    text = _RX_TOKEN.sub(' ', statement or '').replace(r'\$', _DOLLAR)
    text = _RX_SPACE.sub(' ', text).strip()
    pieces, pos = [], 0
    for match in _RX_MATH.finditer(text):
        if match.start() > pos:
            pieces.append((False, _text_piece(text[pos:match.start()])))
        body = next(g for g in match.groups() if g is not None).strip()
        pieces.append((True, '$%s$' % body))
        pos = match.end()
    if pos < len(text):
        pieces.append((False, _text_piece(text[pos:])))

    out, used = [], 0
    for is_math, piece in pieces:
        piece = piece.replace(_DOLLAR, r'\$')
        if used + len(piece) <= limit:
            out.append(piece)
            used += len(piece)
            continue
        if is_math:
            if not out:
                out.append(piece)
            return _join(out).rstrip(' ,;:.-–—') + '…'
        lead = piece[:len(piece) - len(piece.lstrip())]
        out.append(lead + cut_words(piece.lstrip(), max(limit - used - len(lead), 0)))
        return _join(out)
    return _join(out)


def cut_words(text, limit):
    """Обрезка по границе слова с многоточием.

    То же правило, что у `teacher.picker.word_cut`: рвать число посередине
    нельзя нигде — «300…» вместо «3000» это ДРУГОЕ число. Своя копия,
    потому что каталог не импортирует конструктор домашки (слой ниже).
    """
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(' ')
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(' ,;:.-–—') + '…'


_RX_TITLE_JUNK = re.compile(r'[$\\{}]')
_RX_TRAIL_DOTS = re.compile(r'(…|\.{3})\s*$')


def _norm(text):
    text = (text or '').casefold().replace('ё', 'е')
    text = _RX_TITLE_JUNK.sub('', text)
    return _RX_SPACE.sub(' ', text).strip()


def looks_like_statement_cut(title, statement):
    """Заголовок — обрезок условия, а не название задачи.

    Истина, если нормализованный заголовок — префикс нормализованного
    условия, ИЛИ он кончается на «-», «—», «…», ИЛИ длиннее 70 знаков без
    точки на конце. Пустой заголовок обрезком не считается: показывать
    там всё равно нечего, это решает вызывающий код.
    """
    raw = (title or '').strip()
    if not raw:
        return False
    if raw[-1] in '-–—…':
        return True
    if len(raw) > TITLE_MAX and not raw.endswith('.'):
        return True
    head = _RX_TRAIL_DOTS.sub('', _norm(raw)).strip()
    body = _norm(statement)
    return bool(head) and bool(body) and body.startswith(head)
