"""Превью условия для карточек каталога и «похожих»: формулы упрощаются,
а не вырезаются, заголовок-обрезок не показывается.

⚠️ ПОЧЕМУ НЕ ВЫРЕЗАТЬ ФОРМУЛЫ. Прежний `_strip_latex` удалял `$…$`
целиком, и превью оставалось с сиротами: «в точке , » и «спроса .» —
карточка Notion 3d0b11c92bc1811e9d6de18e28c6c46e (аудит 04.09.2026).
Формула в превью нужна как ТЕКСТ: `$P=20$` → «P=20», `\\frac{a}{b}` →
«a/b». Длинная формула (больше 40 знаков после упрощения) превью не
помогает — на её месте многоточие.

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
# Формула длиннее этого после упрощения заменяется многоточием.
FORMULA_MAX = 40
# Заголовок длиннее этого без точки на конце — обрезок, а не название.
TITLE_MAX = 70

# `$$…$$` и `\[…\]` раньше `$…$` — тот же порядок, что у KaTeX на странице:
# иначе `$$x$$` читался бы как два пустых `$…$`.
_RX_FORMULA = re.compile(
    r'\$\$(.+?)\$\$|\\\[(.+?)\\\]|\$([^$\n]+?)\$|\\\((.+?)\\\)', re.DOTALL)
_RX_FRAC = re.compile(r'\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}')
_RX_SQRT = re.compile(r'\\sqrt\s*\{([^{}]*)\}')
_RX_SCRIPT = re.compile(r'([_^])\{([^{}]*)\}')
_RX_CMD_ARG = re.compile(r'\\[a-zA-Z]+\*?\s*\{([^{}]*)\}')
_RX_CMD = re.compile(r'\\[a-zA-Z]+\*?')
_RX_SPACE = re.compile(r'[\s\u00a0]+')
_RX_ORPHAN_BEFORE = re.compile(r'\s+([,.;:!?)»])')
_RX_ORPHAN_AFTER = re.compile(r'([(«])\s+')
_RX_EMPTY_PAREN = re.compile(r'\(\s*\)')
_RX_DOUBLE_PUNCT = re.compile(r'([,;:])(\s*[,;:])+')

# Литеральный доллар (`\$` — цена, не формула) прячется на время разбора.
_DOLLAR = '\x00'

# Команды без аргумента → знак. Порядок не важен: заменяются по словам.
_SYMBOLS = {
    'cdot': '·', 'times': '×', 'le': '≤', 'leq': '≤', 'leqslant': '≤',
    'ge': '≥', 'geq': '≥', 'geqslant': '≥', 'ne': '≠', 'neq': '≠',
    'to': '→', 'rightarrow': '→', 'Rightarrow': '⇒', 'infty': '∞',
    'pm': '±', 'approx': '≈', 'sum': 'Σ', 'prod': 'Π', 'int': '∫',
    'partial': '∂', 'ldots': '…', 'dots': '…', 'cdots': '…',
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
    'varepsilon': 'ε', 'lambda': 'λ', 'mu': 'μ', 'pi': 'π', 'sigma': 'σ',
    'tau': 'τ', 'theta': 'θ', 'omega': 'ω', 'rho': 'ρ', 'eta': 'η',
    'phi': 'φ', 'varphi': 'φ', 'Delta': 'Δ', 'Sigma': 'Σ', 'Pi': 'Π',
    'Omega': 'Ω', 'quad': ' ', 'qquad': ' ', 'left': '', 'right': '',
    'displaystyle': '', 'limits': '', 'nolimits': '',
}
_RX_SYMBOL = re.compile(r'\\(' + '|'.join(sorted(_SYMBOLS, key=len, reverse=True))
                        + r')(?![a-zA-Z])')


def _simplify_formula(body):
    """Тело формулы → читаемый текст: `\\frac{a}{b}` → a/b, `\\cdot` → ·."""
    text = body
    for _ in range(4):                       # вложенные дроби — снаружи внутрь
        text, n = _RX_FRAC.subn(r'\1/\2', text)
        if not n:
            break
    text = _RX_SQRT.sub(r'√\1', text)
    text = _RX_SYMBOL.sub(lambda m: _SYMBOLS[m.group(1)], text)
    text = text.replace(r'\%', '%').replace(r'\,', ' ').replace(r'\;', ' ')
    text = text.replace(r'\!', '').replace('\\ ', ' ').replace('\\\\', ' ')
    text = _RX_SCRIPT.sub(r'\1\2', text)     # _{ab} → _ab
    text = _RX_CMD_ARG.sub(r'\1', text)      # \text{руб} → руб
    text = _RX_CMD.sub('', text)             # остальное без аргумента — прочь
    text = text.replace('{', '').replace('}', '')
    text = _RX_SPACE.sub(' ', text).strip()
    if len(text) > FORMULA_MAX:
        return '…'
    return text


def preview_text(statement):
    """Условие одной строкой для превью: формулы текстом, без сирот."""
    text = (statement or '').replace(r'\$', _DOLLAR)
    text = _RX_FORMULA.sub(
        lambda m: _simplify_formula(next(g for g in m.groups() if g is not None)),
        text)
    # Команды вне формул (`\textbf{…}`) — оставить содержимое.
    text = _RX_CMD_ARG.sub(r'\1', text)
    text = _RX_CMD.sub('', text)
    text = text.replace(_DOLLAR, '$')
    text = _RX_SPACE.sub(' ', text)
    text = _RX_ORPHAN_BEFORE.sub(r'\1', text)
    text = _RX_ORPHAN_AFTER.sub(r'\1', text)
    text = _RX_EMPTY_PAREN.sub('', text)
    text = _RX_DOUBLE_PUNCT.sub(r'\1', text)
    text = _RX_SPACE.sub(' ', text)
    return text.strip()


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
