"""
Экспорт домашки и контрольной в `.tex` и PDF — листок, который можно
распечатать и раздать.

Два варианта одного задания:
  * УЧЕНИКУ — условия и место для решения, без ответов;
  * ПРЕПОДАВАТЕЛЮ — те же условия плюс ответы и эталонные решения.

⚠️ КОМПИЛИРУЕМ pdflatex, А НЕ xelatex. Это записанное решение проекта.
Отсюда и преамбула: кириллица идёт через `inputenc/fontenc T2A`, а не через
`fontspec` (пакет `fontspec` работает только в xelatex/lualatex — существующий
экспорт подборок `catalog/latex_export.py` собран под него и НЕ ТРОНУТ).

⚠️ НА ПРОДЕ PDF НЕТ. На бесплатном Render нет TeX Live — там доступен только
`.tex` плюс Overleaf. Это ограничение хостинга, а не кода: локально сборка
работает, на проде функция честно деградирует до `.tex` с объяснением, а не
падает ошибкой.

⚠️ БИТАЯ ЗАДАЧА НЕ РОНЯЕТ ВЕСЬ ЛИСТОК. Непарные `$` или скобки в условии —
обычное дело для банка из 31 тысячи импортированных задач; такая задача
пропускается с пометкой, остальные собираются.
"""
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# Плашка графика в условии: полноценная отрисовка появится, когда будет
# определён формат сцены calc2. Пока печатаем рамку с именем — листок
# собирается, и видно, что здесь должен быть чертёж.
GRAPH_PLATE = re.compile(r'\[\[График:\s*([^\]]+)\]\]')


def escape_latex(text):
    """Экранирование вне формул — берём готовое из экспорта подборок."""
    from catalog.latex_export import escape_latex as base

    return base(text or '')


def looks_broken(text):
    """Похоже ли на битый LaTeX, который уронит сборку целиком.

    Не претендуем на разбор TeX: ловим ровно то, из-за чего pdflatex
    гарантированно падает, — непарные `$` и непарные фигурные скобки.
    """
    if not text:
        return False
    masked = text.replace('\\$', '').replace('\\{', '').replace('\\}', '')
    if masked.count('$$') % 2:
        return True
    if (masked.replace('$$', '').count('$')) % 2:
        return True
    if masked.count('{') != masked.count('}'):
        return True
    return False


def _plate(text):
    """Плашку графика превращаем в видимую рамку, а не теряем молча."""
    return GRAPH_PLATE.sub(
        lambda m: r'\fbox{\parbox{0.9\linewidth}{\centering\vspace{6pt}'
                  r'График: ' + escape_latex(m.group(1)) +
                  r'\vspace{6pt}}}', text)


PREAMBLE = [
    '% !TeX program = pdflatex',
    r'\documentclass[12pt,a4paper]{article}',
    # ⚠️ ФАЙЛ ОБЯЗАН СОБИРАТЬСЯ ЛЮБЫМ КОМПИЛЯТОРОМ. Проверка руками показала
    # худший исход: человек собрал наш .tex XeTeX-ом и получил PDF, где нет
    # ни одного русского слова — только формулы и латиница. Настройки
    # pdflatex (`inputenc`/`fontenc T2A`) XeTeX молча ИГНОРИРУЕТ, кириллица
    # исчезает без единой ошибки. Функция, результат которой зависит от
    # того, угадал ли пользователь движок, сломана — а слов «pdflatex» и
    # «XeTeX» репетитор знать не должен вовсе.
    r'\usepackage{iftex}',
    r'\ifPDFTeX',
    r'  \usepackage[utf8]{inputenc}',
    r'  \usepackage[T2A]{fontenc}',
    r'\else',
    # XeTeX/LuaTeX: кириллицу даёт шрифт, а не кодировка. Latin Modern
    # Roman — юникодная версия штатного шрифта LaTeX, она есть в любой
    # установке TeX Live и на Overleaf, и кириллица в ней полная.
    r'  \usepackage{fontspec}',
    r'  \defaultfontfeatures{Ligatures=TeX}',
    r'  \setmainfont{Latin Modern Roman}',
    r'  \setsansfont{Latin Modern Sans}',
    r'  \setmonofont{Latin Modern Mono}',
    r'\fi',
    r'\usepackage[russian]{babel}',
    r'\usepackage{amsmath,amssymb}',
    r'\usepackage{geometry}',
    r'\geometry{top=2cm,bottom=2cm,left=2.5cm,right=2cm}',
    r'\usepackage{enumitem}',
    r'\usepackage{parskip}',
    r'\setlength{\parskip}{6pt}',
    r'\pagestyle{plain}',
]


def build_tex(assignment, for_teacher=False, solution_space=True):
    """Готовый `.tex` для задания. Возвращает (текст, список пропущенных)."""
    from problems.timefmt import DATE, fmt

    from problems.assignment_rows import ordered_items, section_marks

    # Порядок и деление на части — ТА ЖЕ функция, что у экрана и у страницы
    # печати. Три разных порядка одной работы — это три разных работы.
    items = ordered_items(assignment, list(
        assignment.items
        .select_related('catalog_problem', 'custom_problem', 'graph')
        .prefetch_related('catalog_problem__parts',
                          'custom_problem__options')
        .order_by('order', 'id')))
    marks = section_marks(items)

    kind = 'Контрольная работа' if assignment.is_exam else 'Домашнее задание'
    group = assignment.group.name if assignment.group_id else ''
    deadline = fmt(assignment.deadline_at, DATE)

    out = list(PREAMBLE)
    out += [
        '', r'\begin{document}', '',
        r'\begin{center}',
        r'{\Large\bfseries ' + escape_latex(assignment.name) + r'}\\[4pt]',
        r'{\normalsize ' + escape_latex(kind)
        + (r' \enspace ·\enspace ' + escape_latex(group) if group else '')
        + (r' \enspace ·\enspace до ' + escape_latex(deadline)
           if deadline else '') + r'}',
        r'\end{center}',
    ]
    if for_teacher:
        out.append(r'{\small\itshape Вариант преподавателя: с ответами '
                   r'и решениями.}')
    else:
        out.append(r'\vspace{4pt}{\small Фамилия, имя: '
                   r'\underline{\hspace{7cm}}}')
    out += [r'\medskip\hrule\medskip', '']

    skipped = []
    number = 0
    for index, item in enumerate(items):
        statement = item.statement or ''
        if looks_broken(statement):
            skipped.append({'item': item, 'why': 'битая разметка в условии'})
            continue
        # Заголовок части плюс пунктирная линия. Подпись обязательна: в
        # печати одна линия без слов теряется и читается как случайная
        # черта. Состав («3 вопроса · 6 баллов») приходит готовой строкой
        # из `section_caption` — той же, что на экране.
        head = marks.get(index)
        if head:
            out.append(r'\smallskip{\small\bfseries '
                       + escape_latex(head['caption']) + r'}\nobreak')
            out.append(r'\nobreak\vspace{-4pt}'
                       r'\hrule height 0pt \dotfill \vspace{2pt}')
            out.append('')
        number += 1
        points = ''
        if item.points is not None:
            points = (r'\hfill\textit{%s б.}'
                      % escape_latex(_clean_number(item.points)))
        out.append(r'\textbf{Задача ' + str(number) + r'.}\quad '
                   + _plate(escape_latex(statement)) + points)
        out.append('')

        for line in _parts_lines(item, for_teacher):
            out.append(line)

        if for_teacher:
            out += _teacher_lines(item)
        elif solution_space:
            out.append(r'\vspace{3.2cm}')

        out.append(r'\bigskip')
        out.append('')

    if skipped:
        out += ['', r'\medskip\hrule\medskip',
                r'{\small\itshape Пропущено задач при сборке: %d '
                r'(испорченная разметка условия). Их видно в интерфейсе '
                r'задания.}' % len(skipped)]

    out.append(r'\end{document}')
    return '\n'.join(out), skipped


def _clean_number(value):
    """Балл в листке пишется ТАК ЖЕ, как на экране (`problems/scorefmt.py`).

    ⚠️ Прежняя запись срезала нули с КОНЦА СТРОКИ без оглядки на точку:
    `Decimal('10')` превращалось в «1», а `Decimal('100')` — тоже в «1». В
    базе балл лежит с двумя знаками (`decimal_places=2`), и вживую это не
    стреляло, но сумма и балл, посчитанные в памяти, приходят без хвоста.
    """
    from . import scorefmt

    return scorefmt.ball(value, default='0')


def _parts_lines(item, for_teacher):
    """Пункты «а)», «б)» — отдельными строками, как просили."""
    if item.is_custom or item.catalog_problem_id is None:
        return []
    parts = [p for p in item.catalog_problem.parts.all()
             if (p.statement or '').strip()]
    if not parts:
        return []
    lines = [r'\begin{enumerate}[leftmargin=*]']
    for part in parts:
        label = escape_latex((part.label or '').rstrip(').．。 '))
        text = escape_latex(part.statement or '')
        if looks_broken(part.statement or ''):
            text = r'\textit{(пункт пропущен: испорченная разметка)}'
        head = (r'\item[' + label + r')] ') if label else r'\item '
        if for_teacher and (part.answer or '').strip():
            text += (r' \quad \textit{Ответ:} '
                     + escape_latex(part.answer.strip()))
        lines.append(head + text)
    lines.append(r'\end{enumerate}')
    lines.append('')
    return lines


def _teacher_lines(item):
    lines = []
    answer = (item.correct_answer or '').strip()
    if answer and not looks_broken(answer):
        lines.append(r'\smallskip\textit{Ответ:} ' + escape_latex(answer))
        lines.append('')
    solution = (item.solution_text or '').strip()
    if solution and not looks_broken(solution):
        lines.append(r'\smallskip\textit{Решение:} '
                     + _plate(escape_latex(solution)))
        lines.append('')
    return lines


# ---------------------------------------------------------------------------
# Сборка PDF — только там, где есть TeX Live
# ---------------------------------------------------------------------------

def pdflatex_bin():
    return getattr(settings, 'PDFLATEX_PATH', 'pdflatex')


def pdflatex_available():
    import os
    import shutil

    path = getattr(settings, 'PDFLATEX_PATH', None)
    if path:
        return os.path.isfile(path) and os.access(path, os.X_OK)
    return shutil.which('pdflatex') is not None


def compile_pdf(tex):
    """(pdf_bytes, None) при успехе или (None, «человеческое объяснение»)."""
    if not pdflatex_available():
        return None, ('На этом сервере не установлен TeX Live, поэтому PDF '
                      'собрать нельзя. Скачайте .tex — его открывает Overleaf '
                      'и любой локальный LaTeX.')
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / 'work.tex'
        pdf_path = Path(tmpdir) / 'work.pdf'
        tex_path.write_text(tex, encoding='utf-8')
        try:
            # Два прохода: первый считает ссылки, второй их расставляет.
            for _ in range(2):
                subprocess.run(
                    [pdflatex_bin(), '-interaction=nonstopmode',
                     '-halt-on-error', '-output-directory', tmpdir,
                     str(tex_path)],
                    capture_output=True, timeout=60)
        except FileNotFoundError:
            return None, 'pdflatex не найден на сервере.'
        except subprocess.TimeoutExpired:
            return None, 'pdflatex не уложился в минуту.'
        if not pdf_path.exists():
            log = (Path(tmpdir) / 'work.log')
            tail = ''
            if log.exists():
                tail = log.read_text(encoding='utf-8', errors='replace')[-1500:]
            logger.warning('pdflatex не собрал PDF:\n%s', tail)
            return None, ('LaTeX не смог собрать листок. Скачайте .tex и '
                          'посмотрите, какая задача мешает.')
        return pdf_path.read_bytes(), None


# ---------------------------------------------------------------------------
# Версия для печати — те же данные, что в `.tex`, но рисует их браузер
# ---------------------------------------------------------------------------

def print_rows(assignment, for_teacher=False, items=None):
    """Строки задания для страницы печати. Возвращает (строки, пропущенные).

    ⚠️ `items` ПОЗВОЛЯЕТ СОБРАТЬ ЛИСТОК ДО СОЗДАНИЯ РАБОТЫ (ревью 15.08,
    фаза 12): конструктор подборки показывает печатный лист по корзине, а
    работы ещё нет. Позиции приходят готовыми (`picker.cart_items`), всё
    остальное считается ровно так же — второй сборки печати не заводим,
    иначе предпросмотр начал бы расходиться с тем, что печатается потом.

    ⚠️ ОДНА СБОРКА С `.tex`. Порядок задач, номера, баллы, пункты и то,
    какая задача пропущена из-за битой разметки, обязаны совпадать: лист,
    напечатанный из браузера, и лист, собранный из `.tex`, — это ОДИН И ТОТ
    ЖЕ листок, и расхождение между ними обнаружится на занятии.

    Текст проходит через санитайзер (`text_clean.clean`): числа и знаки он
    не трогает, а склеенные с формулами слова на бумаге видно особенно
    хорошо.
    """
    from problems.text_clean import clean

    from problems.assignment_rows import (
        item_section, ordered_items, section_marks,
    )

    # Порядок и подписи частей — ТА ЖЕ функция, что у экрана. Иначе на
    # странице задача №4, а в листке под этим номером другая.
    if items is None:
        items = list(assignment.items
                     .select_related('catalog_problem', 'custom_problem',
                                     'graph')
                     .prefetch_related('catalog_problem__parts',
                                       'custom_problem__options')
                     .order_by('order', 'id'))
    items = ordered_items(assignment, items)
    marks = section_marks(items)

    rows = []
    skipped = []
    number = 0
    # ⚠️ ИНДЕКС СТРОКИ НАЗЫВАЕТСЯ `index`, А НЕ `position`. Внутри цикла
    # есть ВЛОЖЕННЫЙ перебор вариантов ответа, который раньше тоже звался
    # `position` и затирал внешний: после него подпись части бралась по
    # номеру последнего варианта, и «Тестовая часть» пропадала, а «Задачи»
    # печаталось над тестами. Поймано сквозным сценарием.
    for index, item in enumerate(items):
        statement = item.statement or ''
        if looks_broken(statement):
            skipped.append(index + 1)
            continue
        number += 1
        graph_name = ''
        text = clean(statement)
        plate = GRAPH_PLATE.search(text)
        if plate:
            graph_name = plate.group(1).strip()
            text = GRAPH_PLATE.sub('', text).strip()
        elif item.graph_id:
            graph_name = item.graph.name

        # ⚠️ ВАРИАНТЫ ТЕСТА — ЭТО ВАРИАНТЫ, А НЕ ПУНКТЫ ЗАДАЧИ. Спрашиваем
        # ту же функцию, которая рисует форму ученику: у каталожного теста
        # подпункты играют роль вариантов ответа, и печатать их списком
        # «а) … Ответ: верно» значит выдать ключ прямо в условии.
        from problems.assignment_rows import (
            ANSWER_TEXT, correct_option_values, item_answer_form,
        )
        from problems.answer_check import normalize_label

        options = []
        parts = []
        kind, raw_options = item_answer_form(item)
        if kind != ANSWER_TEXT and raw_options:
            correct = correct_option_values(item)
            for position, option in enumerate(raw_options):
                value = (str(option['value']) if item.is_custom
                         else normalize_label(option['value']))
                options.append({
                    # Буква варианта — своя (а, б, в…): HTML-списки русских
                    # букв не умеют, а ученик отвечает именно буквой.
                    'label': (option.get('part_label')
                              or _letter(position)).rstrip(').'),
                    'text': clean(option['label']),
                    'is_correct': value in correct})
        elif item.catalog_problem_id:
            for part in item.catalog_problem.parts.all():
                if not (part.statement or '').strip():
                    continue
                if looks_broken(part.statement or ''):
                    continue
                # ⚠️ БУКВА ПУНКТА БЕРЁТСЯ ИЗ ЗАДАЧИ, а не выдумывается
                # нумерацией списка. На экране пункты идут «а)» и «б)», и
                # в листке обязаны идти так же: расхождение всплывёт на
                # занятии, когда ученик назовёт «пункт б», а в листке под
                # этим местом стоит «2». Метки нет — подставляем букву по
                # порядку, но НИКОГДА не цифру.
                label = (part.label or '').rstrip(').')
                if not label:
                    label = _letter(len(parts))
                parts.append({'label': label,
                              'statement': clean(part.statement),
                              'answer': clean(part.answer or '')})

        rows.append({
            'number': number,
            'section': item_section(item),
            # Подпись части у первой позиции части; пусто, если часть одна.
            # Нумерация подписей идёт по ИСХОДНОМУ индексу позиции, а не по
            # номеру в листке: задача с битой разметкой пропускается, и
            # номера разъезжаются с индексами.
            'section_head': marks.get(index),
            'title': item.problem_title if item.problem_title != item.statement
                     else '',
            'statement': text,
            'points': item.points,
            'parts': parts,
            'options': options,
            'graph': graph_name,
            'answer': clean(item.correct_answer or ''),
            'solution': clean(item.solution_text or ''),
            # Место для решения — ПО ВЕСУ ЗАДАЧИ, а не по длине условия.
            # Полосок, а не пустоты: на пустом поле ученик пишет мельче и
            # криво. У теста линеек нет вовсе — вариант ответа уже написан,
            # обводить его негде.
            'space_lines': range(solution_lines(item)),
        })
    return rows, skipped


MIN_SPACE_LINES = 3
MAX_SPACE_LINES = 12


def solution_lines(item):
    """Сколько пунктирных линеек дать под решение.

    ⚠️ ПО МАКСИМАЛЬНОМУ БАЛЛУ, а не по длине условия. Длина условия — не
    мера работы: «Найдите равновесие, если D: 100−Q, S: Q» короче любого
    сюжета, а решать её дольше. Балл же репетитор ставит именно за объём
    рассуждения, которого он ждёт.

    У ТЕСТА ЛИНЕЕК НЕТ. Варианты ответа уже напечатаны, ученик обводит
    букву — три пустые полоски под ней просто съедали бумагу (раньше они
    стояли у всех позиций подряд).

    Шкала: балл 2 → 3 линейки (низ шкалы), балл 10 → 11, дальше упор в 12.
    Задача на 10 баллов получает заметно больше места, чем на 2.
    """
    from .assignment_rows import item_section, SECTION_TEST

    if item_section(item) == SECTION_TEST:
        return 0
    points = item.points
    if points is None:
        return MIN_SPACE_LINES
    lines = int(float(points)) + 1
    return max(MIN_SPACE_LINES, min(MAX_SPACE_LINES, lines))


RU_LETTERS = 'абвгдежзиклмнопрстуфхц'


def _letter(position):
    return (RU_LETTERS[position] if position < len(RU_LETTERS)
            else str(position + 1))


def total_points(rows):
    """Сумма максимальных баллов задания.

    Позиция без проставленного балла считается за единицу — ровно так же,
    как её считает `assignment_rows.item_max_score`. Без этого «всего
    баллов» на листке расходилось бы с суммой оценок в журнале.
    """
    from decimal import Decimal

    from .models_platform import LEGACY_POINTS

    total = Decimal('0')
    for row in rows:
        points = row.get('points')
        total += Decimal(str(points)) if points is not None else LEGACY_POINTS
    return total or None


# ---------------------------------------------------------------------------
# Кнопка «Скачать PDF» — ПОДГОТОВЛЕНА, НО ВЫКЛЮЧЕНА
# ---------------------------------------------------------------------------

def pdf_button_enabled():
    """Включена ли кнопка «Скачать PDF».

    ⚠️ ПО УМОЛЧАНИЮ ВЫКЛЮЧЕНА, и это не осторожность, а арифметика: на
    бесплатном Render всему приложению отведено 512 МБ, а headless Chromium
    на ОДИН документ берёт 200–400 МБ. Два учителя, нажавшие кнопку
    одновременно, кладут сайт. Пока флаг снят, кнопки нет вовсе, а листок
    берётся через «Версия для печати» — она ничего не стоит и работает у
    всех.

    Что нужно от хостинга, чтобы включить: ≥1 ГБ памяти на процесс,
    установленный Chromium (`npx playwright install chromium`), доступ в
    сеть за CDN KaTeX либо вендоренная копия. Включается настройкой
    `ASSIGNMENT_PDF_ENABLED = True`.
    """
    return bool(getattr(settings, 'ASSIGNMENT_PDF_ENABLED', False))


def browser_pdf(html):
    """(pdf_bytes, None) или (None, «человеческое объяснение»).

    Печатает НАСТОЯЩИМ браузером ту же страницу, которую видит репетитор:
    второй вёрстки для PDF не заводим.
    """
    import os

    if not pdf_button_enabled():
        return None, ('Скачивание PDF на этом сервере выключено. Откройте '
                      '«Версия для печати» и сохраните в PDF из браузера — '
                      'получится тот же листок.')

    script = Path(settings.BASE_DIR) / 'scripts' / 'print_to_pdf.js'
    if not script.exists():
        return None, 'Не найден сборщик PDF. Воспользуйтесь версией для печати.'

    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / 'sheet.html'
        target = Path(folder) / 'sheet.pdf'
        source.write_text(html, encoding='utf-8')
        try:
            result = subprocess.run(
                ['node', str(script), str(source), str(target)],
                cwd=str(settings.BASE_DIR), capture_output=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.warning('PDF не собрался: %s', error)
            return None, ('Не удалось собрать PDF. Откройте «Версия для '
                          'печати» и сохраните в PDF из браузера.')
        if result.returncode != 0 or not target.exists():
            logger.warning('PDF не собрался: %s',
                           result.stderr.decode('utf-8', 'replace')[:400])
            return None, ('Не удалось собрать PDF. Откройте «Версия для '
                          'печати» и сохраните в PDF из браузера.')
        return target.read_bytes(), None
