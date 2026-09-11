# -*- coding: utf-8 -*-
"""Числовой отпечаток условия — эвристика для разведки дедупа.

Зачем. Главный риск дедупа по косинусу — склеить две ЗАДАЧИ ОДНОГО СЮЖЕТА
С РАЗНЫМИ ЧИСЛАМИ. Сюжет («фирма на монопольном рынке, найдите выпуск»)
кодируется почти одинаково, а параметры спроса разные — и это две разные
задачи, а не дубль. Множество чисел в условии — самый дешёвый признак,
который такую пару разводит.

Эвристика намеренно грубая: она НЕ решает, дубль это или нет. Она только
раскладывает пары на «числа совпали / совпали частично / разошлись», чтобы
человек смотрел глазами прицельно.
"""
import re

# Число: необязательный знак, дробная часть через запятую или точку.
#
# ⚠️ Две ветки, и порядок важен. Первая — группы тысяч через пробел
# («1 000 000»), и она требует РОВНО ТРИ цифры после каждого пробела.
# Без этого требования «цена 10 20» склеивалась бы в одно число 1020 —
# ровно это поймал тест `test_половина`. Вторая ветка — обычное число.
# Остаётся неснимаемая двусмысленность: «100 200» — это либо сто тысяч
# двести, либо два числа подряд; берём первое, как в банке чаще.
_NUMBER_RE = re.compile(
    r'-?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?'
    r'|-?\d+(?:[.,]\d+)?'
)

# Служебные куски LaTeX, где цифры не параметры задачи, а разметка:
# \frac12 не даёт чисел 1 и 2 как данных, \hline{3} — тем более.
_LATEX_NOISE_RE = re.compile(
    r'\\(?:begin|end|cline|multicolumn|multirow|includegraphics|ref|label|'
    r'vspace|hspace|scalebox|resizebox|arraystretch|textwidth|linewidth)'
    r'\s*(?:\{[^{}]*\}|\[[^\]]*\])*'
)


def extract_numbers(text: str) -> set:
    """Множество чисел из текста условия в нормальном виде.

    Нормализация: пробелы-разделители тысяч убираются, запятая становится
    точкой, хвостовые нули дробной части отбрасываются — чтобы «12,50»
    и «12.5» считались одним числом, а «1 000» и «1000» не расходились.
    """
    if not text:
        return set()
    cleaned = _LATEX_NOISE_RE.sub(' ', text)
    out = set()
    for raw in _NUMBER_RE.findall(cleaned):
        token = re.sub(r'[\s  ]', '', raw).replace(',', '.')
        token = token.rstrip('.')
        if not token or token in ('-',):
            continue
        try:
            value = float(token)
        except ValueError:
            continue
        # Целое печатаем без дробной части: 12.0 и 12 — одно число.
        out.add(str(int(value)) if value == int(value) else str(value))
    return out


def compare_numbers(text_a: str, text_b: str) -> str:
    """Вердикт по паре: как соотносятся множества чисел двух условий."""
    a = extract_numbers(text_a)
    b = extract_numbers(text_b)
    if not a and not b:
        return 'оба без чисел'
    if not a or not b:
        return 'числа только у одной'
    if a == b:
        return 'совпадают'
    if a & b:
        return 'частично'
    return 'не совпадают'


def jaccard(text_a: str, text_b: str) -> float:
    """Доля общих чисел — для сортировки подозрительных пар."""
    a = extract_numbers(text_a)
    b = extract_numbers(text_b)
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0
