# -*- coding: utf-8 -*-
"""TeX-aware лексер — Шаг 1 архитектуры из аудита 2026-08-27.

Зачем. Прежний конвейер чинил уже готовый HTML регулярками, и это
структурно не могло работать: markdown СНАЧАЛА ставит `<br>`/`<p>`, а
KaTeX ПОТОМ ищет разделители отдельно в каждом текстовом узле. Если
`\\begin{cases}` и `\\end{cases}` разъехались по разные стороны `<br>`,
формулу уже не собрать — на экране остаётся сырой TeX. Аудит нашёл 63
таких карточки, и ни одну из них текстовый предфильтр не видел.

Лексер разбирает исходник на токены ДО markdown, поэтому знает, где
кончается формула, и не даёт разметке залезть внутрь неё.

Классы токенов (терминология аудита): `text`, `inline_math`,
`display_math`, `environment`, `comment`, `currency`.

Отдельная работа лексера — **валюта**. `$` рядом с суммой не должен
открывать формулу (класс `DOLLAR` аудита, живые примеры #26828 `3000$
за тонну`, #35228 `$200 … $150 … $300`). Прежде такие доллары
спаривались между собой и весь абзац прозы уезжал в math mode.

⚠️ Как отличается валюта от формулы. НЕ по «есть ли рядом цифра» —
`$2x$` тоже начинается с цифры и является честной формулой. Решает
СОДЕРЖИМОЕ предполагаемой формулы: если между двумя `$` лежит
естественная речь (два и более русских слова, не считая служебных
связок вроде «если»/«при»/«иначе»), это не формула, а проза, и
открывающий `$` — валюта. Связки исключены намеренно: они законно
встречаются ВНУТРИ формул (#30081: `\\begin{cases}L^2, & если …`), и
без этого исключения правило ломало бы честные кусочные функции.
"""
from __future__ import annotations

import re

#: Русские служебные слова, законно встречающиеся ВНУТРИ формулы.
#: Их наличие не делает фрагмент прозой (Фаза 1 обернёт их в `\text{}`).
MATH_CONNECTIVES = frozenset({
    'если', 'иначе', 'при', 'где', 'или', 'тогда', 'для', 'всех',
    'любых', 'есть', 'нет', 'то', 'и', 'а', 'в', 'на',
})

#: Слово естественного языка — три и более кириллических буквы подряд.
#: Два символа и меньше («в», «на», «за») слишком часто попадаются
#: внутри индексов и подписей, чтобы служить признаком прозы.
_CYRILLIC_WORD_RE = re.compile(r'[а-яёА-ЯЁ]{3,}')
#: Содержимое `\text{…}` — законная речь внутри формулы, из подсчёта
#: прозы исключается.
_TEXT_CMD_RE = re.compile(r'\\text\s*\{[^{}]*\}')

#: Порядок пар обязателен и совпадает с боевым `mathSpanEnd`
#: (`templates/_katex_dollars.html`): `$$` раньше `$`, иначе `$$x$$`
#: прочиталось бы как две пустые inline-формулы.
_PAIRS = (
    ('$$', '$$', True),
    ('\\[', '\\]', True),
    ('\\(', '\\)', False),
    ('$', '$', False),
)

_BEGIN_RE = re.compile(r'\\begin\{([A-Za-z]+\*?)\}')
_END_RE = re.compile(r'\\end\{([A-Za-z]+\*?)\}')


class TokenKind:
    """Строковые константы, а не Enum: токены попадают в отчёты и JSON."""

    TEXT = 'text'
    INLINE_MATH = 'inline_math'
    DISPLAY_MATH = 'display_math'
    ENVIRONMENT = 'environment'
    COMMENT = 'comment'
    CURRENCY = 'currency'


class Token:
    """`raw` — исходный кусок дословно, `body` — содержимое без обёртки.

    Инвариант, проверяемый тестом: склейка `raw` всех токенов равна
    исходному тексту байт в байт. Без него лексер мог бы молча терять
    текст, а именно потерю содержимого аудит и называет P0."""

    __slots__ = ('kind', 'raw', 'body', 'name')

    def __init__(self, kind, raw, body=None, name=None):
        self.kind = kind
        self.raw = raw
        self.body = raw if body is None else body
        self.name = name

    def __repr__(self):
        return f'Token({self.kind}, {self.raw[:40]!r})'

    def __eq__(self, other):
        return (isinstance(other, Token) and self.kind == other.kind
                and self.raw == other.raw and self.name == other.name)


def _find_close(text, start, close):
    """Индекс закрывающего разделителя. `\\$` пропускается — экранированный
    доллар не закрывает формулу (боевой `findClose`)."""
    i, n = start, len(text)
    while i < n:
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
            i += 2
            continue
        if text.startswith(close, i):
            return i
        i += 1
    return -1


def looks_like_prose(body):
    """Похоже ли содержимое на естественную речь, а не на формулу?

    Речь в `\\text{…}` не считается — она внутри формулы законна."""
    stripped = _TEXT_CMD_RE.sub(' ', body)
    words = [w.lower() for w in _CYRILLIC_WORD_RE.findall(stripped)]
    meaningful = [w for w in words if w not in MATH_CONNECTIVES]
    return len(meaningful) >= 2


def _is_comment_start(text, i):
    """`%` открывает комментарий, кроме `\\%` и процента после числа.

    `20%` в этом корпусе означает проценты, а не начало комментария
    (в чистом LaTeX было бы наоборот) — так же считает и прежняя
    `strip_tex_comments` в `core.py`, здесь правило только уточнено."""
    if text[i] != '%':
        return False
    if i > 0 and text[i - 1] == '\\':
        return False
    if i > 0 and text[i - 1].isdigit():
        return False
    return True


def _match_environment(text, i):
    """`\\begin{X}…\\end{X}` с учётом вложенности одноимённых окружений.

    Возвращает `(end_index, name)` или `None`, если пары нет — тогда
    `\\begin` остаётся обычным текстом, а несбалансированность отдельно
    сообщит `environment_balance`."""
    m = _BEGIN_RE.match(text, i)
    if not m:
        return None
    name = m.group(1)
    depth = 1
    pos = m.end()
    open_re = re.compile(r'\\begin\{' + re.escape(name) + r'\}')
    close_re = re.compile(r'\\end\{' + re.escape(name) + r'\}')
    while pos < len(text):
        nxt_open = open_re.search(text, pos)
        nxt_close = close_re.search(text, pos)
        if nxt_close is None:
            return None
        if nxt_open is not None and nxt_open.start() < nxt_close.start():
            depth += 1
            pos = nxt_open.end()
            continue
        depth -= 1
        pos = nxt_close.end()
        if depth == 0:
            return pos, name
    return None


def tokenize(text):
    """Исходный текст → список токенов.

    Порядок проверок на каждой позиции не случаен:
    1. `\\$` — валюта, раньше всего (иначе откроет формулу собой);
    2. `\\%` — литеральный процент;
    3. `%` — комментарий до конца строки;
    4. разделитель формулы (`$$`, `\\[`, `\\(`, `$`) — для одиночного
       `$` дополнительно решается «формула или валюта» по содержимому;
    5. `\\begin{X}` — окружение вне математики (внутрь математики
       управление не дойдёт: она уже съедена шагом 4);
    6. иначе — обычный текст.
    """
    tokens = []
    buf = []
    i, n = 0, len(text)

    def flush():
        if buf:
            tokens.append(Token(TokenKind.TEXT, ''.join(buf)))
            buf.clear()

    while i < n:
        # 1. экранированный доллар — всегда валюта
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
            flush()
            tokens.append(Token(TokenKind.CURRENCY, text[i:i + 2], body='$'))
            i += 2
            continue

        # 2. экранированный процент — обычный текст
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '%':
            buf.append(text[i:i + 2])
            i += 2
            continue

        # 3. комментарий до конца строки
        if _is_comment_start(text, i):
            flush()
            nl = text.find('\n', i)
            end = n if nl == -1 else nl
            tokens.append(Token(TokenKind.COMMENT, text[i:end], body=text[i + 1:end]))
            i = end
            continue

        # 4. разделители формул
        span = _math_span(text, i)
        if span is not None:
            end, body, display, open_ = span
            if open_ == '$' and looks_like_prose(body):
                # Проза между долларами — значит открывающий `$` был
                # валютой, а не разделителем (#26828, #35228).
                flush()
                tokens.append(Token(TokenKind.CURRENCY, '$', body='$'))
                i += 1
                continue
            flush()
            kind = TokenKind.DISPLAY_MATH if display else TokenKind.INLINE_MATH
            tokens.append(Token(kind, text[i:end], body=body))
            i = end
            continue

        # 4б. одиночный `$` без пары формулой быть не может в принципе.
        # Помечаем валютой, а не текстом: в выводе он будет экранирован и
        # не спарится с `$` из соседнего текстового узла (боевой
        # auto-render ищет пары ПОУЗЛОВО, и хвостовой `$150.` из #35228
        # иначе поймал бы доллар из следующего абзаца).
        if text[i] == '$':
            flush()
            tokens.append(Token(TokenKind.CURRENCY, '$', body='$'))
            i += 1
            continue

        # 5. окружение вне математики
        env = _match_environment(text, i)
        if env is not None:
            env_end, name = env
            flush()
            inner = text[i:env_end]
            body = inner[len(f'\\begin{{{name}}}'):-len(f'\\end{{{name}}}')]
            tokens.append(Token(TokenKind.ENVIRONMENT, inner, body=body, name=name))
            i = env_end
            continue

        # 6. обычный текст
        buf.append(text[i])
        i += 1

    flush()
    return tokens


def _math_span(text, i):
    """`(end, body, display, open)` если с позиции `i` начинается формула."""
    for open_, close, display in _PAIRS:
        if not text.startswith(open_, i):
            continue
        end = _find_close(text, i + len(open_), close)
        if end == -1:
            continue
        return end + len(close), text[i + len(open_):end], display, open_
    return None


def math_span(text, i):
    """Публичная обёртка над `_math_span` — нужна `math_canon`, чтобы
    снимать вложенные разделители тем же кодом, каким лексер их находит
    (иначе две реализации границы формулы неизбежно разъехались бы)."""
    return _math_span(text, i)


def environment_balance(text):
    """`(balanced, unclosed, unopened)` — Шаг 5 аудита, класс `ENV-BAL`.

    Считает по ВСЕМУ тексту, включая математику: незакрытое окружение
    внутри `$$…$$` ломает формулу ровно так же, как снаружи."""
    stack = []
    unopened = []
    pattern = re.compile(r'\\(begin|end)\{([A-Za-z]+\*?)\}')
    for m in pattern.finditer(text):
        which, name = m.group(1), m.group(2)
        if which == 'begin':
            stack.append(name)
            continue
        if stack and stack[-1] == name:
            stack.pop()
        elif name in stack:
            # закрылось через голову — всё, что осталось выше, не закрыто
            while stack and stack[-1] != name:
                unopened.append(stack.pop())
            stack.pop()
        else:
            unopened.append(name)
    return (not stack and not unopened), stack, unopened


def strip_tex_comments_lexed(text):
    """Убрать TeX-комментарии лексером, не тронув `20%`, `\\%` и `%` внутри
    математики (Шаг 3 аудита)."""
    return ''.join(t.raw for t in tokenize(text) if t.kind != TokenKind.COMMENT)
