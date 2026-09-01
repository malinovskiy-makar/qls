# -*- coding: utf-8 -*-
"""«Текст задачи» — одно определение, общее для Б1 (частоты) и Б2 (пилот).

Условие + подпункты, без обрезки. Здесь же живёт эвристика «английский
текст» — единственного признака стратификации выборки Б2, для которого в
базе нет своего поля (docs/TAXONOMY.md §7: «на английском» вычисляется
кодом по доле кириллицы).
"""
import re

from problems.templatetags.ru import pick

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


# «График в условии» / «Табличка в условии» — особенности 11 и 12 из
# docs/TAXONOMY.md §7. Модель картинку не видит и таблицу распознаёт хуже
# регулярки — обе считаются кодом, а не спрашиваются у модели.
_GRAPH_MARKER_RE = re.compile(r'\[\[FIGURE:|\\begin\{tikzpicture\}')
_TABLE_MARKER_RE = re.compile(
    r'\\begin\{tabular\}|\\begin\{array\}|\\begin\{table\}|<table', re.IGNORECASE)


def has_graph_in_statement(text, has_problem_figure=False):
    """«График в условии» (docs/TAXONOMY.md §7, особенность 11).

    `has_problem_figure` — есть ли у задачи строка `ProblemFigure`; сюда
    передаётся вызывающим кодом, т.к. эта функция работает с голым текстом
    и к БД не обращается. Считается истиной ещё и по маркеру `[[FIGURE:`
    или сырому `tikzpicture`-блоку в тексте (задача до сборки ассета).
    """
    if has_problem_figure:
        return True
    return bool(_GRAPH_MARKER_RE.search(text or ''))


def has_table_in_statement(text):
    """«Табличка в условии» (docs/TAXONOMY.md §7, особенность 12).

    LaTeX-окружения `tabular`/`array`/`table`, HTML `<table`, либо
    markdown-таблица (строка с двумя и более символами `|`).
    """
    text = text or ''
    if _TABLE_MARKER_RE.search(text):
        return True
    return any(line.count('|') >= 2 for line in text.splitlines())


_FIGURE_MARKER_ONLY_RE = re.compile(r'\[\[FIGURE:')


def with_figure_note(text, figure_count):
    """Служебная строка `[[FIGURE: к задаче приложено N изображений]]` в
    КОНЦЕ payload — только если у задачи есть строки `ProblemFigure`
    (`figure_count > 0`), а в самом тексте нет ни одного маркера
    `[[FIGURE:` (Фаза 2, 2026-09-01: 732 задачи, 28% визуального
    множества, без этой строки модель видит «на рисунке…» без единого
    сигнала, что рисунок вообще есть).

    Правит только то, что уходит в API — `statement`/`ProblemPart.statement`
    в базе не трогает ни на байт.
    """
    if figure_count <= 0 or _FIGURE_MARKER_ONLY_RE.search(text or ''):
        return text
    note = '[[FIGURE: к задаче приложено %d %s]]' % (
        figure_count,
        pick(figure_count, 'изображение', 'изображения', 'изображений'))
    return '%s\n%s' % (text or '', note)


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
