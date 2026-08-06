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
    r'\usepackage[utf8]{inputenc}',
    r'\usepackage[T2A]{fontenc}',
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

    items = list(assignment.items
                 .select_related('catalog_problem', 'custom_problem', 'graph')
                 .prefetch_related('catalog_problem__parts',
                                   'custom_problem__options')
                 .order_by('order', 'id'))

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
    for item in items:
        statement = item.statement or ''
        if looks_broken(statement):
            skipped.append({'item': item, 'why': 'битая разметка в условии'})
            continue
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
    text = ('%s' % value).rstrip('0').rstrip('.')
    return text or '0'


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
