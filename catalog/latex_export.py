"""
Генерация LaTeX/PDF для подборок задач (Этап Б2).
"""

import re
import subprocess
import tempfile
from pathlib import Path

# ── Экранирование LaTeX-спецсимволов ───────────────────────────────────────

# Regex, который разбивает текст на (обычные части, формулы, обычные части, …)
# Порядок альтернатив важен: $$ до $ чтобы не откусить полформулы.
# (?<!\\) — экранированный валютный \$ (сессия C) не является границей формулы.
_FORMULA_RE = re.compile(
    r'((?<!\\)\$\$.*?(?<!\\)\$\$'                 # $$...$$
    r'|(?<!\\)\$[^$\n]+?(?<!\\)\$'                # $...$
    r'|\\\[.*?\\\]'                               # \[...\]
    r'|\\\(.*?\\\)'                               # \(...\)
    r'|\\begin\{[^}]+\}.*?\\end\{[^}]+\})',       # \begin{...}...\end{...}
    re.DOTALL,
)

_LATEX_MAP = {
    '\\': r'\textbackslash{}',
    '{':  r'\{',
    '}':  r'\}',
    '$':  r'\$',
    '%':  r'\%',
    '&':  r'\&',
    '#':  r'\#',
    '_':  r'\_',
    '^':  r'\^{}',
    '~':  r'\textasciitilde{}',
}
_SPECIAL_RE = re.compile(r'[\\{}$%&#_^~]')


def _escape_plain(text: str) -> str:
    """Один проход по всем спецсимволам — не порождает цепочек двойного экранирования.
    Уже экранированный валютный \\$ (сессия C) — валидный LaTeX, оставляем как есть."""
    text = text.replace('\\$', '\x00')
    text = _SPECIAL_RE.sub(lambda m: _LATEX_MAP[m.group()], text)
    return text.replace('\x00', r'\$')


def escape_latex(text: str) -> str:
    """Экранирует спецсимволы в обычных частях текста, формулы не трогает."""
    if not text:
        return ''
    parts = _FORMULA_RE.split(text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 0:   # нечётные индексы — совпавшие формулы
            result.append(_escape_plain(part))
        else:
            result.append(part)  # формулу оставляем нетронутой
    return ''.join(result)


# ── Генерация .tex ──────────────────────────────────────────────────────────

_TPL_LABEL = {
    'homework': 'Домашнее задание',
    'test':     'Контрольная работа',
    'sheet':    'Листок задач',
}


def generate_latex(collection, show_answers: bool = False,
                   show_solutions: bool = False) -> str:
    """Генерирует полный .tex файл для подборки."""
    # Задачи в порядке из problem_order; качественный шлюз — мимо экспорта
    from problems.models import Problem

    order_map = {pid: i for i, pid in enumerate(collection.problem_order)}
    problems  = sorted(
        collection.problems.filter(
            needs_quality_review=False,
            hidden_pending_review=False,
            content_status=Problem.ContentStatus.OK)
        .prefetch_related('parts'),
        key=lambda p: order_map.get(p.pk, 9999),
    )

    title    = escape_latex(collection.name)
    tpl_name = escape_latex(_TPL_LABEL.get(collection.template_type, ''))

    out = []
    out += [
        '% !TeX program = xelatex',
        r'\documentclass[12pt,a4paper]{article}',
        r'\usepackage{fontspec}',
        r'\setmainfont{DejaVu Serif}',
        r'\usepackage[russian]{babel}',
        r'\usepackage{amsmath,amssymb,amsthm}',
        r'\usepackage{geometry}',
        r'\geometry{top=2cm,bottom=2cm,left=2.5cm,right=2cm}',
        r'\usepackage{enumitem}',
        r'\usepackage{parskip}',
        r'\setlength{\parskip}{6pt}',
        r'\pagestyle{plain}',
        '',
        r'\begin{document}',
        '',
        r'\begin{center}',
        r'{\Large\bfseries ' + title + r'}\\[4pt]',
        r'{\normalsize ' + tpl_name + r'}',
        r'\end{center}',
        r'\medskip\hrule\medskip',
        '',
    ]

    for n, p in enumerate(problems, 1):
        stmt  = escape_latex(p.statement or '')
        parts = list(p.parts.all())

        out.append(r'\textbf{Задача ' + str(n) + r'.}\quad ' + stmt)
        out.append('')

        if parts:
            out.append(r'\begin{enumerate}[leftmargin=*]')
            for part in parts:
                # метка с ровно одной «)» (в базе есть и «а», и «а)» — не дублируем)
                raw_lbl   = (part.label or '').rstrip(').．。 ')
                lbl       = escape_latex(raw_lbl)
                part_stmt = escape_latex(part.statement or '')
                if lbl:
                    out.append(r'\item[' + lbl + r')] ' + part_stmt)
                else:
                    out.append(r'\item ' + part_stmt)
            out.append(r'\end{enumerate}')
            out.append('')

        if show_answers and p.answer:
            out.append(r'\smallskip')
            out.append(r'\textit{Ответ:} ' + escape_latex(p.answer))
            out.append('')

        if show_solutions and p.solution and not p.solution_needs_review:
            out.append(r'\smallskip')
            out.append(r'\textit{Решение:} ' + escape_latex(p.solution))
            out.append('')

        out.append(r'\bigskip')
        out.append('')

    out.append(r'\end{document}')
    return '\n'.join(out)


# ── Компиляция в PDF ────────────────────────────────────────────────────────

def _xelatex_bin() -> str:
    """Возвращает путь к xelatex: сначала из XELATEX_PATH, иначе 'xelatex' из PATH."""
    from django.conf import settings
    return getattr(settings, 'XELATEX_PATH', 'xelatex')


def xelatex_available() -> bool:
    """True если xelatex найден (по XELATEX_PATH или в PATH)."""
    import os
    import shutil
    from django.conf import settings
    path = getattr(settings, 'XELATEX_PATH', None)
    if path:
        return os.path.isfile(path) and os.access(path, os.X_OK)
    return shutil.which('xelatex') is not None


def compile_pdf(tex_content: str):
    """
    Компилирует .tex в PDF через xelatex.
    Возвращает (pdf_bytes, None) при успехе или (None, log_str) при ошибке.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / 'collection.tex'
        pdf_path = Path(tmpdir) / 'collection.pdf'

        tex_path.write_text(tex_content, encoding='utf-8')

        try:
            result = subprocess.run(
                [
                    _xelatex_bin(),
                    '-interaction=nonstopmode',
                    '-output-directory', tmpdir,
                    str(tex_path),
                ],
                capture_output=True,
                timeout=30,
            )
        except FileNotFoundError:
            return None, 'xelatex не найден на сервере'
        except subprocess.TimeoutExpired:
            return None, 'xelatex превысил лимит времени (30 с)'

        if pdf_path.exists():
            return pdf_path.read_bytes(), None

        # PDF не создан — возвращаем лог
        log = result.stdout.decode('utf-8', errors='replace')
        return None, log or 'Неизвестная ошибка компиляции'
