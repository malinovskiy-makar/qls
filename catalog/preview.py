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


# ── Решение, повторяющее условие (аудит P0 «Стола», 18.09.2026) ───────────
# 4 задачи из 7 055 с решением держат в «решении» копию условия, ещё 21 —
# начинают решение с пересказа всего условия. Данные не трогаем: правило
# действует при показе.

#: Доля слов решения, встречающихся в условии, при которой это копия.
COPY_WORD_SHARE = 0.9
#: Копия — примерно той же длины, что условие. Короткий ответ («Дед прав»)
#: весь состоит из слов условия, но копией не является.
COPY_LEN_RANGE = (0.7, 1.3)
#: Сколько последних знаков условия искать в начале решения.
RETELL_TAIL = 60


def solution_is_statement_copy(statement, solution):
    """Решение — это условие ещё раз (такая задача показывается без решения)."""
    st, so = _norm(statement), _norm(solution)
    if not st or not so:
        return False
    low, high = COPY_LEN_RANGE
    if not low * len(st) <= len(so) <= high * len(st):
        return False
    words = set(so.split())
    return len(words & set(st.split())) / len(words) >= COPY_WORD_SHARE


def strip_statement_retell(statement, solution):
    """Решение без пересказа условия в начале.

    Срез только если решение начинается со ВСЕГО условия: его хвост
    (последние RETELL_TAIL знаков) стоит в решении не дальше длины условия
    с запасом. Частичная цитата («На рынке… — отсюда…») не режется: там
    цитата часть рассуждения.
    """
    text = (solution or '').strip()
    tail = (statement or '').strip()[-RETELL_TAIL:]
    if len(tail) < RETELL_TAIL or not text:
        return text
    end = text.find(tail, 0, int(len(statement.strip()) * 1.2) + RETELL_TAIL)
    if end < 0:
        return text
    rest = text[end + len(tail):].strip()
    return rest or text


# ── «Почему так» у теста: баллы составителя не нужны ученику (P6, 18.09.2026) ─
# 25 видимых тестов держат в решении хвосты «(6 баллов)», «**(3 балла)**» —
# разбалловку жюри. При показе они срезаются; данные не трогаем.
# Число бывает и формулой: «( $4$ балла)» (63243, 62901).
_RX_SCORE_TAIL = re.compile(r'\s*\*{0,2}\(\s*\$?\s*\d+(?:[.,]\d+)?\s*\$?\s*балл(?:а|ов)?\s*\)\*{0,2}')


def strip_score_tails(text):
    return _RX_SCORE_TAIL.sub('', text or '').strip()


# ── «Почему так» у теста: повтор верного варианта не нужен (S3, 18.09.2026) ──
# 342 из 1 975 тестов с решением начинают его с верного ответа: «(b) Центральный
# банк Российской Федерации.  Пояснение: Ключевую ставку…». Ученик только что
# видел верную плитку, и «Почему так» должно начинаться с объяснения (README §5,
# снимок 19). Срез — только при показе и только если метка в начале верная.
_RX_ANSWER_HEAD = re.compile(r'^\s*\(?\s*([A-Za-zА-Яа-яЁё0-9])\s*\)\s*')
_RX_EXPLAIN = re.compile(r'^(.*?)\s*Пояснение\s*:\s*', re.S)


def _norm(text):
    return re.sub(r'[\s.;:,$]+', ' ', (text or '').casefold()).strip()


def strip_correct_repeat(text, game):
    """Срезать в начале «(метка) текст верного варианта [Пояснение:]»."""
    from problems.answer_check import normalize_label

    text = (text or '').strip()
    head = _RX_ANSWER_HEAD.match(text)
    if not head or not game or normalize_label(head.group(1)) not in game['correct']:
        return text
    rest = text[head.end():]
    explain = _RX_EXPLAIN.match(rest)
    if explain and len(explain.group(1)) <= 400:
        return rest[explain.end():].strip() or text
    option = next((o['text'] for o in game['options']
                   if o['label'] == normalize_label(head.group(1))), '')
    first = rest.split('\n', 1)[0]
    if option and _norm(first).startswith(_norm(option)):
        return rest[len(first):].strip() or text
    return text
