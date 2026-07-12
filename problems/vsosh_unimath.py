# -*- coding: utf-8 -*-
"""
Конвертер юникод-математики из PDF в обычный LaTeX (импорт ВсОШ, регион).

PDF-файлы ВсОШ набраны в Word: формулы приходят символами блока
Mathematical Alphanumeric Symbols (U+1D400–U+1D7FF): «𝑌 = 2𝑀/𝑃»,
греческие 𝜋/𝛼, надстрочные ² и дробные ½. Здесь — таблично-детерминированная
замена таких символов на ASCII/LaTeX; никакой эвристики по смыслу формул.
"""
import re
import unicodedata

# --- Математические алфавиты (U+1D400–U+1D7FF) --------------------------
# Каждый стиль (bold, italic, bold-italic, script, …) — это 52 буквы A–Z a–z
# подряд; цифровые стили — 10 цифр подряд. Вместо гигантской таблицы —
# список стартовых кодпоинтов.
_LATIN_STARTS = [
    0x1D400,  # bold
    0x1D434,  # italic (основной стиль формул Word)
    0x1D468,  # bold italic
    0x1D49C,  # script
    0x1D4D0,  # bold script
    0x1D504,  # fraktur
    0x1D538,  # double-struck
    0x1D56C,  # bold fraktur
    0x1D5A0,  # sans-serif
    0x1D5D4,  # sans-serif bold
    0x1D608,  # sans-serif italic
    0x1D63C,  # sans-serif bold italic
    0x1D670,  # monospace
]
_DIGIT_STARTS = [0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC, 0x1D7F6]

# Греческий: стили по 58 символов от Alpha; берём italic/bold/bold-italic.
_GREEK_STARTS = [0x1D6A8, 0x1D6E2, 0x1D71C, 0x1D756, 0x1D790]
_GREEK_UPPER = ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta',
                'Theta', 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi',
                'Omicron', 'Pi', 'Rho', 'Theta', 'Sigma', 'Tau', 'Upsilon',
                'Phi', 'Chi', 'Psi', 'Omega', 'nabla']
_GREEK_LOWER = ['alpha', 'beta', 'gamma', 'delta', 'varepsilon', 'zeta',
                'eta', 'theta', 'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi',
                'omicron', 'pi', 'rho', 'varsigma', 'sigma', 'tau', 'upsilon',
                'varphi', 'chi', 'psi', 'omega', 'partial', 'epsilon',
                'vartheta', 'varkappa', 'phi', 'varrho', 'varpi']
# Имена без обратной косой — Omicron/omicron в LaTeX нет, заменяем буквой O/o.
_GREEK_PLAIN = {'Omicron': 'O', 'omicron': 'o'}

_MATH_MAP = {}
for start in _LATIN_STARTS:
    for i in range(26):
        _MATH_MAP[chr(start + i)] = chr(ord('A') + i)
        _MATH_MAP[chr(start + 26 + i)] = chr(ord('a') + i)
for start in _DIGIT_STARTS:
    for i in range(10):
        _MATH_MAP[chr(start + i)] = chr(ord('0') + i)
for start in _GREEK_STARTS:
    for i, name in enumerate(_GREEK_UPPER):
        ch = chr(start + i)
        _MATH_MAP[ch] = _GREEK_PLAIN.get(name, '\\' + name + ' ')
    # Строчные идут сразу после 26 заглавных (25 букв Alpha–Omega + nabla).
    for i, name in enumerate(_GREEK_LOWER):
        ch = chr(start + 26 + i)
        if start + 26 + i > 0x1D7FF:
            continue
        _MATH_MAP[ch] = _GREEK_PLAIN.get(name, '\\' + name + ' ')

# Юникодные «дырки» в италик-стиле: h (планк) и др. лежат отдельно.
_MATH_MAP.update({
    'ℎ': 'h',        # planck = italic h
    'ℓ': '\\ell ',
    'ℂ': 'C', 'ℕ': 'N', 'ℚ': 'Q', 'ℝ': 'R', 'ℤ': 'Z',
})

# --- Одиночные математические символы ------------------------------------
_SYMBOL_MAP = {
    '−': '-', '–': '-', '—': '-',      # разные тире в формулах → минус
    '⋅': ' \\cdot ', '·': ' \\cdot ', '×': ' \\times ', '∙': ' \\cdot ',
    '≤': ' \\le ', '≥': ' \\ge ', '≠': ' \\ne ', '≈': ' \\approx ',
    '⩽': ' \\le ', '⩾': ' \\ge ',      # наклонные ⩽/⩾ — именно их ставит LaTeX ВсОШ
    '∗': '*', '⋆': '\\star ',
    '∞': '\\infty ', '√': '\\sqrt ',
    '∈': ' \\in ', '∉': ' \\notin ', '∆': '\\Delta ', '∂': '\\partial ',
    '∑': '\\sum ', '∏': '\\prod ', '∫': '\\int ',
    '→': ' \\to ', '⇒': ' \\Rightarrow ', '↑': '\\uparrow ', '↓': '\\downarrow ',
    'π': '\\pi ', 'α': '\\alpha ', 'β': '\\beta ', 'γ': '\\gamma ',
    'δ': '\\delta ', 'ε': '\\varepsilon ', 'λ': '\\lambda ', 'μ': '\\mu ',
    'σ': '\\sigma ', 'τ': '\\tau ', 'φ': '\\varphi ', 'ω': '\\omega ',
    'Δ': '\\Delta ', 'Σ': '\\Sigma ', 'Π': '\\Pi ', 'Ω': '\\Omega ',
    '±': ' \\pm ',
}

# Надстрочные/подстрочные цифры и знаки.
_SUPERSCRIPTS = {'⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5',
                 '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁺': '+', '⁻': '-'}
_SUBSCRIPTS = {'₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', '₅': '5',
               '₆': '6', '₇': '7', '₈': '8', '₉': '9'}

# Готовые дробные символы → LaTeX-дробь.
_VULGAR_FRACTIONS = {
    '½': '\\frac{1}{2}', '⅓': '\\frac{1}{3}', '⅔': '\\frac{2}{3}',
    '¼': '\\frac{1}{4}', '¾': '\\frac{3}{4}', '⅕': '\\frac{1}{5}',
    '⅖': '\\frac{2}{5}', '⅗': '\\frac{3}{5}', '⅘': '\\frac{4}{5}',
    '⅙': '\\frac{1}{6}', '⅚': '\\frac{5}{6}', '⅛': '\\frac{1}{8}',
    '⅜': '\\frac{3}{8}', '⅝': '\\frac{5}{8}', '⅞': '\\frac{7}{8}',
}

_MATH_CHAR_RE = re.compile(
    '[' + ''.join(re.escape(c) for c in _MATH_MAP) + ']')


def has_math_alphanumerics(text):
    """Есть ли в тексте символы математических алфавитов юникода."""
    return bool(_MATH_CHAR_RE.search(text))


def replace_unicode_math(text):
    """Замена всех юникод-математических символов на ASCII/LaTeX-эквиваленты.

    ВАЖНО: функция работает посимвольно и не расставляет $…$ — обёртку
    формул делает вызывающий код, которому виден контекст."""
    out = []
    for ch in text:
        if ch in _MATH_MAP:
            out.append(_MATH_MAP[ch])
        elif ch in _VULGAR_FRACTIONS:
            out.append(_VULGAR_FRACTIONS[ch])
        elif ch in _SUPERSCRIPTS:
            out.append('^{' + _SUPERSCRIPTS[ch] + '}')
        elif ch in _SUBSCRIPTS:
            out.append('_{' + _SUBSCRIPTS[ch] + '}')
        elif ch in _SYMBOL_MAP:
            out.append(_SYMBOL_MAP[ch])
        else:
            out.append(ch)
    # Схлопнуть последовательности ^{2}^{3} не пытаемся — в исходниках ВсОШ
    # степени одноцифровые; двойная степень встретится — увидим в превью.
    return ''.join(out)


def strip_soft_junk(text):
    """Мягкие переносы, неразрывные пробелы, нулевой ширины символы."""
    text = text.replace('­', '')            # soft hyphen
    text = text.replace('​', '').replace('﻿', '')
    text = text.replace(' ', ' ').replace(' ', ' ')
    return text
