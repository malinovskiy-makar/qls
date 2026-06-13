"""
Исправляет OCR-артефакты в задачах КСИ Кыльчик (Source #10).

OCR через macOS Vision читал LaTeX-формулы как обычный текст:
  - √L  → VL    (корень как буква V)
  - x²  → x?    (степень как знак вопроса)
  - q^2 → Q'    (апостроф как суперскрипт)
  - q^{3/2} → q3/2  (дробная степень без ^)
  - q^2 в конце → Q2 (цифра слипается с переменной)

Что делает команда:
  1. VL, VK, Vx, Vу ... → \\sqrt{L}, \\sqrt{K}, ...
  2. q?, Q?, x?, х? ... → q^2, Q^2, x^2, ...
  3. Q' → Q^2
  4. q3/2, L2/3, K3/2 ... → q^{3/2}, L^{2/3}, ...
  5. 0.5Q2 → 0.5Q^2 (цифра-коэффициент + переменная + цифра)
  6. Оборачивает выражения с LaTeX-командами в $...$

Запуск:
    ./venv/bin/python manage.py fix_kylchik_formulas --dry-run
    ./venv/bin/python manage.py fix_kylchik_formulas
"""

import re
from django.core.management.base import BaseCommand
from django.db import transaction
from problems.models import Problem, Source, SourceReference, ProblemPart


# ─────────────────────────────────────────────────────────────────────────────
# OCR-правила
# ─────────────────────────────────────────────────────────────────────────────

def _apply_sqrt_fix(text: str) -> str:
    """
    V + math-буква → \\sqrt{буква}
    Не трогаем V, если перед ней стоит другая буква (AVC, MVC, Volume...).
    """
    # V9 → \\sqrt{q}  (9 — OCR-артефакт q)
    text = re.sub(
        r'(?<![A-Za-zА-ЯЁа-яё])V9(?![A-Za-zА-ЯЁа-яё\d])',
        r'\\sqrt{q}', text,
    )
    # VL + цифра/буква → \\sqrt{L_{...}}  (VL1, VL2, VLy, VLx)
    text = re.sub(
        r'(?<![A-Za-zА-ЯЁа-яё])VL([0-9xy])(?![A-Za-zА-ЯЁа-яё])',
        lambda m: r'\sqrt{L_{' + m.group(1) + '}}',
        text,
    )
    # V + одиночная math-буква
    _SQRT_LETTERS = r'LKQqxXуУхХcCYy'
    text = re.sub(
        r'(?<![A-Za-zА-ЯЁа-яё])V([' + _SQRT_LETTERS + r'])(?![A-Za-zА-ЯЁа-яё])',
        lambda m: r'\sqrt{' + m.group(1) + '}',
        text,
    )
    return text


def _apply_question_mark_fix(text: str) -> str:
    """
    Одиночная math-переменная + ? → переменная^2
    «Одиночная» — перед ней нет другой буквы (иначе это конец слова: сговора?)
    """
    _MATH_VARS = r'qQxXуУхХyYgG'
    text = re.sub(
        r'(?<![A-Za-zА-ЯЁа-яё])([' + _MATH_VARS + r'])\?',
        r'\1^2', text,
    )
    return text


def _apply_prime_fix(text: str) -> str:
    """
    Q' → Q^2  (апостроф/штрих как OCR суперскрипта 2)
    Применяем только к Q, т.к. у других букв ' может быть производной.
    """
    text = re.sub(
        r"(?<![A-Za-zА-ЯЁа-яё])(Q)'(?![A-Za-zА-ЯЁа-яё])",
        r'\1^2', text,
    )
    return text


def _apply_fractional_exponent_fix(text: str) -> str:
    """
    letter + N/M → letter^{N/M}  для дробных показателей степени.
      q3/2 → q^{3/2},  L2/3 → L^{2/3},  K3/2 → K^{3/2}
    Исключение: N=2 и M=2 или M=4 → это скорее деление:
      q2/2 → q^2/2,   Q2/4 → Q^2/4
    """
    # Частный случай "деление": N=2, M ∈ {2, 4}  →  letter^2/M
    text = re.sub(
        r'(?<![A-Za-zА-ЯЁа-яё])([A-Za-zА-ЯЁа-яё])2/([24])(?![A-Za-zА-ЯЁа-яё\d])',
        r'\1^2/\2', text,
    )
    # Остальные дробные степени: q3/2, L2/3, q5/4 и т.д.
    text = re.sub(
        r'(?<![A-Za-zА-ЯЁа-яё])([A-Za-zА-ЯЁа-яё])([2-9])/([2-9])(?![A-Za-zА-ЯЁа-яё\d])',
        r'\1^{\2/\3}', text,
    )
    return text


def _apply_digit_exponent_fix(text: str) -> str:
    """
    Цифра-коэффициент + letter + 2 → letter^2
    Только цифра 2 (возведение в квадрат), другие цифры — нижние индексы.
    Примеры: 0.5Q2 → 0.5Q^2,  1.5L2 → 1.5L^2,  4q2 → 4q^2
    Не трогаем: 6x4 (x_4 — нижний индекс), Q2 = 100 (Q_2 — нижний индекс).
    """
    text = re.sub(
        r'(?<=[0-9.])([A-Za-zА-ЯЁа-яё])2(?=[^A-Za-zА-ЯЁа-яё0-9/])',
        r'\1^2', text,
    )
    return text


def apply_ocr_fixes(text: str) -> str:
    """Применяет все OCR-правила в правильном порядке."""
    if not text:
        return text
    text = _apply_sqrt_fix(text)
    text = _apply_question_mark_fix(text)
    text = _apply_prime_fix(text)
    text = _apply_fractional_exponent_fix(text)
    text = _apply_digit_exponent_fix(text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Оборачивание в $...$
# ─────────────────────────────────────────────────────────────────────────────

# Символы, на которые можно «расширять» математический спан влево
# Точка включена: нужна для десятичных коэффициентов 0.5, 3.14 и т.д.
_LEFT_EXT = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    '0123456789'
    r'\^_{}[]()'
    '+-*/=<>. '
    '½¼¾⅓⅔⅕⅖⅗⅘⅙⅛'    # Unicode-дроби (OCR-артефакты нижних индексов)
)
# Символы, на которые можно «расширять» спан вправо
# Точку НЕ включаем: останавливаемся на конце предложения.
# Десятичные числа (0.5q) корректно читаются, т.к. они ЛЕВЕЕ якоря.
_RIGHT_EXT = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    '0123456789'
    r'\^_{}[]()'
    '+-*/=<> '
    '½¼¾⅓⅔⅕⅖⅗⅘⅙⅛'
)

# Признаки «явной математики»: \\sqrt{ или ^{digit}
_LATEX_ANCHORS = re.compile(r'\\sqrt\{|\^[{0-9]')

# Кириллические символы для проверки «длинного русского слова»
_CYRILLIC = frozenset('АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя')


def _extend_left(line: str, pos: int) -> int:
    """
    Расширяет математический спан ВЛЕВО от позиции pos.

    Правила:
    - Запятая вне скобок → стоп (разделяет уравнения).
    - Запятая внутри скобок → продолжаем (аргументы функции: Q(L,K)).
    - Пробел перед «длинным русским словом» (4+ кириллических букв) → стоп.
    - Незакрытая открывающая скобка → стоп.
    """
    start = pos
    paren_depth = 0
    while start > 0:
        c = line[start - 1]
        if c == ')':
            paren_depth += 1
            start -= 1
        elif c == '(':
            if paren_depth > 0:
                paren_depth -= 1
                start -= 1
            else:
                break  # незакрытая '(' — стоп
        elif c == ',':
            if paren_depth > 0:
                start -= 1  # внутри скобок — продолжаем
            else:
                break  # запятая вне скобок — стоп
        elif c == ' ':
            # Проверяем: слово ПЕРЕД этим пробелом — длинное русское?
            j = start - 2
            cyr_count = 0
            while j >= 0 and line[j] in _CYRILLIC:
                cyr_count += 1
                j -= 1
            if cyr_count > 3:
                break  # длинное русское слово → стоп
            start -= 1
        elif c in _LEFT_EXT:
            start -= 1
        else:
            break
    return start


def _wrap_line(line: str) -> tuple[str, list]:
    """
    Находит LaTeX-спаны в одной строке и оборачивает в $...$.
    Возвращает (новая_строка, [(исходный_спан, новый_спан), ...]).
    """
    if not _LATEX_ANCHORS.search(line):
        return line, []
    if '$' in line or r'\(' in line:
        return line, []

    anchors = [m.start() for m in _LATEX_ANCHORS.finditer(line)]
    if not anchors:
        return line, []

    raw_spans = []
    for pos in anchors:
        start = _extend_left(line, pos)

        # Расширяем вправо; точка — только если за ней цифра (десятичная);
        # «)» без пары → стоп (не вылезаем за пределы скобочного выражения)
        end = pos + 1
        paren_depth_r = 0
        while end < len(line):
            c = line[end]
            if c == '(':
                paren_depth_r += 1
                end += 1
            elif c == ')':
                if paren_depth_r > 0:
                    paren_depth_r -= 1
                    end += 1
                else:
                    break  # непарная ')' — стоп (вышли за границу выражения)
            elif c == '.':
                if end + 1 < len(line) and line[end + 1].isdigit():
                    end += 1  # десятичная точка
                else:
                    break  # конец предложения
            elif c in _RIGHT_EXT:
                end += 1
            else:
                break
        raw_spans.append((start, end))

    # Объединяем перекрывающиеся спаны
    raw_spans.sort()
    merged: list[list[int]] = []
    for s, e in raw_spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    parts = []
    examples = []
    prev = 0
    for start, end in merged:
        parts.append(line[prev:start])
        raw = line[start:end]

        # Обрезаем ведущий маркер подпункта «(a) » или «(а) »
        m_pfx = re.match(r'^(\([a-zа-яёA-ZА-ЯЁ]\)\s+)', raw)
        prefix = m_pfx.group(1) if m_pfx else ''
        raw_math = raw[len(prefix):]

        # Обрезаем пробелы и пунктуацию вокруг математики
        stripped = raw_math.lstrip(' ')
        leading = raw_math[:len(raw_math) - len(stripped)]
        content = stripped.rstrip(' ,;:')
        trailing = stripped[len(content):]

        if content and _LATEX_ANCHORS.search(content):
            examples.append((raw.strip(), f'${content}$'))
            parts.append(f'{prefix}{leading}${content}${trailing}')
        else:
            parts.append(raw)
        prev = end

    parts.append(line[prev:])
    return ''.join(parts), examples


def wrap_in_dollars(text: str) -> tuple[str, list]:
    """
    Проходит по всем строкам текста и оборачивает LaTeX-спаны в $...$.
    Возвращает (новый_текст, список_примеров).
    """
    if not text:
        return text, []
    lines = text.split('\n')
    new_lines, all_ex = [], []
    for line in lines:
        new_line, exs = _wrap_line(line)
        new_lines.append(new_line)
        all_ex.extend(exs)
    return '\n'.join(new_lines), all_ex


# ─────────────────────────────────────────────────────────────────────────────
# Полная обработка одного текстового поля
# ─────────────────────────────────────────────────────────────────────────────

def fix_text(text: str) -> tuple[str, list]:
    """
    Применяет OCR-фиксы + оборачивает в $...$.
    Возвращает (новый_текст, список_пар_(до, после)) где пары — изменившиеся строки.
    """
    if not text:
        return text, []

    orig_lines = text.split('\n')
    fixed = apply_ocr_fixes(text)
    fixed, _ = wrap_in_dollars(fixed)

    new_lines = fixed.split('\n')
    examples = []
    for orig, new in zip(orig_lines, new_lines):
        if orig != new:
            examples.append((orig, new))
    # Если длина изменилась (маловероятно, но на всякий случай):
    for i in range(min(len(orig_lines), len(new_lines)), max(len(orig_lines), len(new_lines))):
        if i < len(orig_lines):
            examples.append((orig_lines[i], ''))
        else:
            examples.append(('', new_lines[i]))

    return fixed, examples


# ─────────────────────────────────────────────────────────────────────────────
# Management command
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_ID = 10   # КСИ — Задачи Кыльчик


class Command(BaseCommand):
    help = 'Исправляет OCR-артефакты в задачах КСИ Кыльчик (Source #10)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только показать изменения, не сохранять.',
        )
        parser.add_argument(
            '--examples', type=int, default=10,
            help='Сколько примеров ДО/ПОСЛЕ показать (по умолчанию 10).',
        )
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Ограничить кол-во обрабатываемых задач (0 = все).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_examples = options['examples']
        limit = options['limit']

        try:
            source = Source.objects.get(pk=SOURCE_ID)
        except Source.DoesNotExist:
            self.stderr.write(f'Source #{SOURCE_ID} не найден.')
            return

        self.stdout.write(f'Источник: {source.name}')
        if dry_run:
            self.stdout.write(self.style.WARNING('── РЕЖИМ DRY-RUN: изменения не сохраняются ──'))

        problems = (
            Problem.objects
            .filter(source_references__source=source)
            .distinct()
            .order_by('id')
        )
        if limit:
            problems = problems[:limit]

        total = problems.count()
        self.stdout.write(f'Задач для обработки: {total}\n')

        changed_count = 0
        example_count = 0
        all_examples = []

        for problem in problems:
            fields_changed = False

            new_stmt, ex_stmt = fix_text(problem.statement or '')
            new_sol, ex_sol = fix_text(problem.solution or '')

            stmt_changed = new_stmt != (problem.statement or '')
            sol_changed = new_sol != (problem.solution or '')

            if stmt_changed or sol_changed:
                fields_changed = True

            # ProblemPart-ы
            part_changes: list[tuple] = []
            for part in problem.parts.all():
                new_pstmt, ex_ps = fix_text(part.statement or '')
                new_pans, ex_pa = fix_text(part.answer or '')
                if new_pstmt != (part.statement or '') or new_pans != (part.answer or ''):
                    part_changes.append((part, new_pstmt, new_pans))
                    fields_changed = True
                all_examples.extend(ex_ps + ex_pa)

            all_examples.extend(ex_stmt + ex_sol)

            if fields_changed:
                changed_count += 1

        # Печатаем примеры
        self.stdout.write(f'Задач с изменениями: {changed_count}\n')
        self.stdout.write('─' * 60)
        self.stdout.write(f'Примеры изменённых строк (ДО → ПОСЛЕ), первые {max_examples}:')

        shown = 0
        for before, after in all_examples:
            if shown >= max_examples:
                break
            self.stdout.write(f'\n  ДО:   {before}')
            self.stdout.write(f'  ПОСЛЕ:{after}')
            shown += 1

        total_changes = len(all_examples)
        remaining = total_changes - shown
        if remaining > 0:
            self.stdout.write(f'\n  ... ещё {remaining} изменённых строк (всего {total_changes}).')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDry-run завершён. Запустите без --dry-run для применения.')
            )
            return

        # Боевой прогон
        with transaction.atomic():
            updated = 0
            for problem in (
                Problem.objects
                .filter(source_references__source=source)
                .distinct()
                .order_by('id')
            ):
                if limit and updated >= limit:
                    break

                new_stmt, _ = fix_text(problem.statement or '')
                new_sol, _ = fix_text(problem.solution or '')

                fields = {}
                if new_stmt != (problem.statement or ''):
                    fields['statement'] = new_stmt
                if new_sol != (problem.solution or ''):
                    fields['solution'] = new_sol

                for part in problem.parts.all():
                    new_ps, _ = fix_text(part.statement or '')
                    new_pa, _ = fix_text(part.answer or '')
                    pf = {}
                    if new_ps != (part.statement or ''):
                        pf['statement'] = new_ps
                    if new_pa != (part.answer or ''):
                        pf['answer'] = new_pa
                    if pf:
                        ProblemPart.objects.filter(pk=part.pk).update(**pf)

                if fields:
                    Problem.objects.filter(pk=problem.pk).update(**fields)
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f'\nОбновлено задач: {updated}'))
