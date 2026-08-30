# -*- coding: utf-8 -*-
"""Границы одной задачи внутри сырого `.tex` и картинки внутри неё.

Зачем не «окно ±N символов». Замер по сопоставленным фрагментам: при
окне ±300 символов картинка находится у 1 788 задач, при ±5 000 — у
4 804. Рост идёт не оттого, что картинок больше, а оттого, что в окно
заезжают СОСЕДНИЕ задачи листочка. Приписать задаче чужой график хуже,
чем не приписать никакого: ученик решает не ту задачу и не может этого
заметить.

Поэтому границы берутся структурные. У этих архивов есть общий разделитель:
`\\problem` встречается 37 462 раза в 3 761 файле из 4 110 — это макрос
домашнего стиля `olmath_style`. Остальные разделители добавлены как
запасные для файлов, где `\\problem` не используется.
"""
import os
import re

BS = chr(92)

#: Начала новой задачи. Порядок значения не имеет — берётся ближайшая
#: позиция. `\item` СОЗНАТЕЛЬНО не входит: там, где есть `\problem`, он
#: обозначает подпункт, и граница по нему резала бы задачу пополам.
SEPARATORS = re.compile(
    BS + BS + r'(?:problem|Problem|task|Task|section\*?|subsection\*?|'
    r'newpage|clearpage|begin\{problem\}|end\{document\})(?![A-Za-z@])')

#: Тот же набор плюс `\item`. Применяется ТОЛЬКО к файлам, где `\problem`
#: не встречается вовсе: у таких авторов задача и есть `\item`.
#:
#: Правило появилось не из общих соображений. В `05/main.tex` (сборник по
#: темам, разделители — только `\section*`) блок получался в 18 607
#: символов и охватывал целый раздел: задаче #37247 приписались три чужих
#: графика `Cycle_1..3.png`. Чинится не порогом на длину, а тем, что
#: разделитель выбирается по стилю конкретного файла.
SEPARATORS_WITH_ITEM = re.compile(
    BS + BS + r'(?:problem|Problem|task|Task|section\*?|subsection\*?|'
    r'newpage|clearpage|begin\{problem\}|end\{document\}|item)(?![A-Za-z@])')

_HAS_PROBLEM = re.compile(BS + BS + r'problem(?![A-Za-z@])')


def separators_for(text):
    """Разделитель, подходящий стилю ЭТОГО файла."""
    return (SEPARATORS if _HAS_PROBLEM.search(text)
            else SEPARATORS_WITH_ITEM)

#: Начало решения внутри задачи: по нему картинка относится к решению,
#: а не к условию.
SOLUTION_RE = re.compile(BS + BS + r'solution(?![A-Za-z@])')

#: Если разделителей в файле нет вовсе, блок вырождается во весь файл.
#: Тогда лучше узкое окно, чем «вся задача — это документ».
FALLBACK_PAD = 800
#: Блок длиннее этого — признак того, что разделители не сработали.
#: Живые блоки этих архивов держатся в 460–2 200 символах; 8 000 — потолок
#: с запасом, за которым начинается не длинная задача, а целый раздел.
MAX_UNIT = 8000

INCLUDEGRAPHICS_RE = re.compile(
    BS + BS + r'includegraphics\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}')
TIKZ_RE = re.compile(BS + BS + r'begin\{tikzpicture\}')
GRAPHICSPATH_RE = re.compile(BS + BS + r'graphicspath\s*\{(.+?)\}\s*$',
                             re.M | re.S)
_BRACED = re.compile(r'\{([^{}]*)\}')

#: Расширения, которые LaTeX подставляет сам, когда в ссылке его нет.
#: Порядок — как у pdflatex.
TRY_EXT = ('.pdf', '.png', '.jpg', '.jpeg', '.jbig2', '.jb2', '.gif',
           '.bmp', '.webp', '.eps')


def unit_bounds(text, start, end):
    """Границы задачи, внутри которой лежит фрагмент `[start, end)`."""
    left = 0
    right = len(text)
    for m in separators_for(text).finditer(text):
        if m.start() <= start:
            left = m.start()
        else:
            right = m.start()
            break
    if right - left > MAX_UNIT:
        return max(0, start - FALLBACK_PAD), min(len(text), end + FALLBACK_PAD)
    return left, right


def graphics_dirs(text):
    """Папки из `\\graphicspath{{a/}{b/}}` — как их видит LaTeX."""
    m = GRAPHICSPATH_RE.search(text)
    if not m:
        return []
    return [d.strip() for d in _BRACED.findall(m.group(1)) if d.strip()]


def resolve_image(reference, tex_dir, project_root, extra_dirs=()):
    """Полный путь к файлу картинки или None.

    LaTeX ищет ссылку относительно файла, корня проекта и папок
    `\\graphicspath`, а расширение подставляет сам. Повторяем ровно это:
    иначе `\\includegraphics{img/plot}` (108 таких ссылок без расширения)
    остался бы «файлом, которого нет», хотя файл лежит рядом."""
    reference = (reference or '').strip().strip('"')
    if not reference:
        return None
    reference = reference.replace('\\', '/').lstrip('./')
    bases = [tex_dir, project_root]
    for d in extra_dirs:
        d = d.replace('\\', '/').rstrip('/')
        bases.append(os.path.join(tex_dir, d.replace('/', os.sep)))
        bases.append(os.path.join(project_root, d.replace('/', os.sep)))
    rel = reference.replace('/', os.sep)
    names = [rel]
    if not os.path.splitext(rel)[1]:
        names = [rel + ext for ext in TRY_EXT]
    guard = os.path.realpath(project_root)
    for base in bases:
        for name in names:
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            # Ссылка приходит из чужого `.tex`, а результат уезжает в базу
            # байтами. `..` в середине пути (`a/../../secret.png`) обошёл
            # бы очистку начала строки, поэтому проверяется итоговый путь,
            # а не текст ссылки: файл обязан лежать внутри проекта.
            if os.path.commonpath([guard, os.path.realpath(path)]) != guard:
                continue
            return path
    return None


def figures_in_unit(text, left, right):
    """`[(смещение, ссылка)]` для `\\includegraphics` внутри блока."""
    return [(m.start(), m.group(1))
            for m in INCLUDEGRAPHICS_RE.finditer(text, left, right)]


def tikz_in_unit(text, left, right):
    """Смещения блоков `tikzpicture` внутри блока задачи."""
    return [m.start() for m in TIKZ_RE.finditer(text, left, right)]


def field_for(text, left, right, offset):
    """`'statement'` или `'solution'` — куда относится объект на `offset`.

    Картинка после `\\solution` принадлежит разбору, а не условию.
    Положить её в условие значило бы показать ученику ответ."""
    m = SOLUTION_RE.search(text, left, right)
    if m and offset > m.start():
        return 'solution'
    return 'statement'
