# -*- coding: utf-8 -*-
"""«Текст задачи» — одно определение, общее для Б1 (частоты) и Б2 (пилот).

Условие + подпункты, без обрезки. Здесь же живёт эвристика «английский
текст» — единственного признака стратификации выборки Б2, для которого в
базе нет своего поля (docs/TAXONOMY.md §7: «на английском» вычисляется
кодом по доле кириллицы).
"""
import re

_CYRILLIC_RE = re.compile(r'[а-яёА-ЯЁ]')
_LATIN_RE = re.compile(r'[a-zA-Z]')

# Порог для эвристики английского текста — см. is_english_text().
MIN_LATIN_LETTERS = 30


def problem_full_text(statement, parts):
    """`parts` — итерируемое объектов с атрибутами `label` и `statement`
    (подходят и `ProblemPart`, и любой объект/namedtuple с теми же полями).
    """
    pieces = [statement or '']
    for part in parts:
        label = getattr(part, 'label', '') or ''
        part_statement = (getattr(part, 'statement', '') or '').strip()
        if not part_statement:
            continue
        pieces.append('(%s) %s' % (label, part_statement) if label
                      else part_statement)
    return '\n'.join(pieces)


def is_english_text(text):
    """Эвристика, а не поле в базе — такого поля у `Problem` нет вовсе.

    Английский, если латиницы заметно (>= MIN_LATIN_LETTERS) и кириллицы
    почти нет (не больше десятой доли латиницы). Не претендует на
    лингвистическую точность — годится ровно для стратификации выборки
    пилота, не для продуктовой разметки.
    """
    text = text or ''
    latin = len(_LATIN_RE.findall(text))
    cyrillic = len(_CYRILLIC_RE.findall(text))
    if latin < MIN_LATIN_LETTERS:
        return False
    return cyrillic <= latin * 0.1
