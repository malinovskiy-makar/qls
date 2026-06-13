"""
Оборачивает «голую» математику в $...$ в задачах МатЭк (Source #13)
и ЛШ Олмат 2025 (Source #3).

Оба источника — LaTeX (Overleaf), поэтому формулы в основном УЖЕ в $...$
или \\(...\\). Команда чинит остатки: уравнения и LaTeX-команды, попавшие
в текст вне математического режима:
    MC=2Q, Q=30          →  $MC=2Q$, $Q=30$
    R \\geq G             →  $R \\geq G$
    Q^*_K=\\frac{160-Q_A}{2}=80-0,5Q_A   →   $...$ (строка целиком)

Никакой конвертации символов НЕ делается — текст уже корректный LaTeX,
его нужно только обернуть.

Что пропускается (безопасность):
  - поля с нечётным числом «$» (разорванная математика — трогать опасно);
  - строки внутри \\begin{...}...\\end{...} и \\[...\\] блоков;
  - строки, уже содержащие $ или \\( или \\[;
  - таблицы (&, \\hline), маркировка списков (label=), ссылки (http);
  - строки с длинными русскими словами оборачиваются только частично
    (inline-спаны вокруг знаков =).

Запуск:
    ./venv/bin/python manage.py fix_matek_formulas --dry-run
    ./venv/bin/python manage.py fix_matek_formulas
    ./venv/bin/python manage.py fix_matek_formulas --source-id 13   # только МатЭк
"""

import os
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart, Source

SOURCE_IDS = [13, 3]   # МатЭк, ЛШ Олмат 2025

CHANGED_IDS_FILE = 'reports/formula_cleanup/changed_ids.txt'


def append_changed_ids(ids):
    """Дописывает id изменённых задач в общий файл сессии чистки (без дублей)."""
    if not ids:
        return
    os.makedirs(os.path.dirname(CHANGED_IDS_FILE), exist_ok=True)
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE):
        with open(CHANGED_IDS_FILE, encoding='utf-8') as f:
            existing = {ln.strip() for ln in f if ln.strip()}
    new = sorted({str(i) for i in ids} - existing, key=int)
    if new:
        with open(CHANGED_IDS_FILE, 'a', encoding='utf-8') as f:
            f.write('\n'.join(new) + '\n')


# ─────────────────────────────────────────────────────────────────────────────
# Распознавание математики
# ─────────────────────────────────────────────────────────────────────────────

# Математические LaTeX-команды (якоря). Текстовые (\textbf, \mbox, \item,
# \alph, \hline...) сюда сознательно НЕ входят.
_MATH_CMD = (
    r'\\(?:frac|sqrt|cdot|times|div|geqslant|leqslant|geq|leq|ge|le|neq|ne'
    r'|approx|infty|partial|sum|prod|int|min|max|pi|alpha|beta|gamma|delta'
    r'|varepsilon|epsilon|lambda|mu|sigma|omega|theta|rho|tau|Delta|Pi|Sigma'
    r'|Longrightarrow|longrightarrow|Rightarrow|rightarrow|to|in|subset'
    r'|left|right|overline|bar|hat|text)\b'
)
_MATH_CMD_RE = re.compile(_MATH_CMD)

# Якорь «это математика»: знак = или математическая LaTeX-команда
_ANCHOR_RE = re.compile(r'=|' + _MATH_CMD)

# Русское слово из 3+ букв
_LONG_CYR_RE = re.compile(r'[а-яёА-ЯЁ]{3,}')

# Маркер подпункта/буллета в начале строки
_ITEM_MARKER_RE = re.compile(r'^(\([a-zа-яёA-ZА-ЯЁ\d]\)\s+|[•‣]\s+|[a-zа-яё]\)\s+)')

# Строки, которые лучше не трогать вовсе (включая TikZ/pgf-графику и опции)
_SKIP_LINE_RE = re.compile(
    r'[&$]|\\\(|\\\)|\\\[|\\\]|\\hline|label=|http|\\item|\\begin|\\end'
    r'|\\draw|\\node|\\fill|\\path|\\addplot|\\tikz|\\coordinate|\\axis'
    r'|/\.style|samples=|node\[|child\s*\{|inner sep|fill=|draw=|font='
    r'|below=|above=|left=|right=|\\small|\\footnotesize'
    r'|leftmargin|itemindent|topsep|parsep'
    r'|ifthenelse|domain=|color='
)

_CYR_SET = frozenset(
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'
)

# Символы внутри inline-спана (плюс правила для пробела, запятой, точки, скобок)
_SPAN_CHARS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    '0123456789'
    '+-*/^_=<>{}\\;%'
)


def _good_content(content: str) -> bool:
    """Спан стоит оборачивать: есть буквы/цифры, есть якорь,
    не обрывается на операторе или backslash («x=», «r=6\\»)."""
    if not content or not _has_math_content(content):
        return False
    if not _ANCHOR_RE.search(content):
        return False
    if content.rstrip()[-1] in '=<>+-*/\\·':
        return False
    # Несбалансированные фигурные скобки (обрезанный \boxed{...} и т.п.) —
    # оборачивание сломало бы KaTeX
    if content.count('{') != content.count('}'):
        return False
    return True


def _next_is_cyrillic(line: str, pos: int, direction: int) -> bool:
    i = pos
    while 0 <= i < len(line) and line[i] == ' ':
        i += direction
    return 0 <= i < len(line) and line[i] in _CYR_SET


def _find_inline_spans(line: str):
    """(start, end) спаны вокруг якорей в строке прозы. Логика как в fix_ksigma."""
    anchors = [m.start() for m in _ANCHOR_RE.finditer(line)]
    raw = []
    for pos in anchors:
        start = pos
        depth = 0
        while start > 0:
            c = line[start - 1]
            if c == ')':
                depth += 1
            elif c == '(':
                if depth == 0:
                    break
                depth -= 1
            elif c == ',':
                if not (start - 2 >= 0 and line[start - 2].isdigit()
                        and start < len(line) and line[start].isdigit()):
                    break
            elif c == '.':
                if not (start - 2 >= 0 and line[start - 2].isdigit()
                        and start < len(line) and line[start].isdigit()):
                    break
            elif c == ' ':
                if _next_is_cyrillic(line, start - 2, -1):
                    break
            elif c not in _SPAN_CHARS:
                break
            start -= 1
        end = pos + 1
        depth = 0
        while end < len(line):
            c = line[end]
            if c == '(':
                if _next_is_cyrillic(line, end + 1, +1):
                    break
                depth += 1
            elif c == ')':
                if depth == 0:
                    break
                depth -= 1
            elif c == ',':
                if depth == 0 and not (
                    end + 1 < len(line) and line[end + 1].isdigit()
                    and end - 1 >= 0 and line[end - 1].isdigit()
                ):
                    break
            elif c == '.':
                if not (end + 1 < len(line) and line[end + 1].isdigit()):
                    break
            elif c == ' ':
                if _next_is_cyrillic(line, end + 1, +1):
                    break
            elif c not in _SPAN_CHARS:
                break
            end += 1
        # обрезано посреди токена — пропускаем
        if (start > 0 and line[start] != ' '
                and (line[start - 1].isalnum() or line[start - 1] == ',')):
            continue
        if (end < len(line) and line[end].isalnum()
                and end > 0 and line[end - 1] != ' '):
            continue
        raw.append((start, end))

    raw.sort()
    merged = []
    for s, e in raw:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def _has_math_content(s: str) -> bool:
    return any(c.isalnum() for c in s)


def _process_line(line: str) -> str:
    if not line.strip():
        return line
    if _SKIP_LINE_RE.search(line):
        return line
    if not _ANCHOR_RE.search(line):
        return line

    stripped = line.strip()
    # Закомментированный LaTeX (% в начале строки) не трогаем
    if stripped.startswith('%'):
        return line

    # Чисто-математическая строка → оборачиваем целиком
    if not _LONG_CYR_RE.search(stripped):
        m = _ITEM_MARKER_RE.match(stripped)
        marker = m.group(0) if m else ''
        body = stripped[len(marker):]
        content = body.rstrip(' .,;:?!')
        trailing = body[len(content):].rstrip()
        if _good_content(content):
            return f'{marker}${content}${trailing}'
        return line

    # Проза → inline-спаны
    spans = _find_inline_spans(line)
    if not spans:
        return line
    parts = []
    prev = 0
    for start, end in spans:
        raw = line[start:end]
        core = raw.strip()
        lead_ws = raw[: len(raw) - len(raw.lstrip())]
        trail_ws = raw[len(lead_ws) + len(core):]
        body = core.lstrip('=<>+/* ')
        lead = lead_ws + core[: len(core) - len(body)]
        content = body.rstrip(' .,;:?!')
        trailing = body[len(content):] + trail_ws
        if _good_content(content):
            parts.append(line[prev:start])
            parts.append(f'{lead}${content}${trailing}')
            prev = end
    parts.append(line[prev:])
    return ''.join(parts)


def fix_text(text: str):
    """Возвращает (новый_текст, [(до, после), ...])."""
    if not text:
        return text, []
    # Нечётное число $ — разорванная математика, не трогаем поле
    if text.count('$') % 2 == 1:
        return text, []

    lines = text.split('\n')
    new_lines = []
    examples = []
    env_depth = 0        # \begin{...} ... \end{...}
    disp_depth = 0       # \[ ... \]
    dollar_open = False  # внутри многострочного $...$ / $$...$$

    for ln in lines:
        opens = ln.count(r'\begin{')
        closes = ln.count(r'\end{')
        d_opens = ln.count(r'\[')
        d_closes = ln.count(r'\]')

        inside_math = env_depth > 0 or disp_depth > 0 or dollar_open

        env_depth += opens - closes
        disp_depth += d_opens - d_closes
        if env_depth < 0:
            env_depth = 0
        if disp_depth < 0:
            disp_depth = 0
        if ln.count('$') % 2 == 1:
            dollar_open = not dollar_open

        if inside_math or opens or closes or d_opens or d_closes:
            new_lines.append(ln)
            continue

        new = _process_line(ln)
        new_lines.append(new)
        if new != ln:
            examples.append((ln, new))

    return '\n'.join(new_lines), examples


# ─────────────────────────────────────────────────────────────────────────────
# Management command
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Оборачивает голую математику в $...$ (МатЭк #13 и ЛШ Олмат #3)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать примеры ДО/ПОСЛЕ без сохранения')
        parser.add_argument('--examples', type=int, default=15,
                            help='Сколько примеров показать')
        parser.add_argument('--source-id', type=int, default=0,
                            help='Только один источник (0 = оба: 13 и 3)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_examples = options['examples']
        sid = options['source_id']
        source_ids = [sid] if sid else SOURCE_IDS

        grand_problems = 0
        grand_parts = 0
        changed_ids = set()

        for source_id in source_ids:
            try:
                source = Source.objects.get(pk=source_id)
            except Source.DoesNotExist:
                self.stderr.write(f'Source #{source_id} не найден.')
                continue

            self.stdout.write(f'\n══ Источник #{source_id}: {source.name}')
            if dry_run:
                self.stdout.write(self.style.WARNING('── DRY-RUN ──'))

            problems = (
                Problem.objects
                .filter(source_references__source=source)
                .distinct()
                .prefetch_related('parts')
                .order_by('id')
            )

            changed_problems = 0
            changed_parts = 0
            all_examples = []

            with transaction.atomic():
                for problem in problems:
                    fields = {}
                    for field in ('statement', 'answer', 'solution'):
                        original = getattr(problem, field) or ''
                        if not original:
                            continue
                        new_text, exs = fix_text(original)
                        if new_text != original:
                            fields[field] = new_text
                            for b, a in exs:
                                all_examples.append((problem.id, field, b, a))
                    if fields:
                        changed_problems += 1
                        changed_ids.add(problem.id)
                        if not dry_run:
                            Problem.objects.filter(pk=problem.pk).update(**fields)

                    for part in problem.parts.all():
                        pfields = {}
                        for field in ('statement', 'answer'):
                            original = getattr(part, field) or ''
                            if not original:
                                continue
                            new_text, exs = fix_text(original)
                            if new_text != original:
                                pfields[field] = new_text
                                for b, a in exs:
                                    all_examples.append(
                                        (problem.id, f'part({part.label}).{field}', b, a)
                                    )
                        if pfields:
                            changed_parts += 1
                            changed_ids.add(problem.id)
                            if not dry_run:
                                ProblemPart.objects.filter(pk=part.pk).update(**pfields)

            self.stdout.write(f'Примеры (первые {max_examples}):')
            for pid, field, before, after in all_examples[:max_examples]:
                self.stdout.write(f'\n#{pid} [{field}]')
                self.stdout.write(f'  ДО:    {before.strip()[:160]}')
                self.stdout.write(f'  ПОСЛЕ: {after.strip()[:160]}')

            self.stdout.write(f'\nИзменённых строк: {len(all_examples)}; '
                              f'задач: {changed_problems}, подпунктов: {changed_parts}')
            grand_problems += changed_problems
            grand_parts += changed_parts

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY-RUN: ничего не сохранено.'))
        else:
            append_changed_ids(changed_ids)
            self.stdout.write(self.style.SUCCESS(
                f'\nГотово. Всего сохранено задач: {grand_problems}, '
                f'подпунктов: {grand_parts}.'
            ))
