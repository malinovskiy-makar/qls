"""
Исправляет формулы в задачах Бахарева (Source #4).

PDF-ридер сохранил математические символы как Unicode-курсив (U+1D400–U+1D7FF).
Команда:
1. Заменяет Unicode-математические буквы на ASCII: 𝑄→Q, 𝑃→P и т.д.
2. Заменяет спецсимволы на LaTeX: ⩽→\leqslant, √→\sqrt{}, − →-, и т.д.
3. Оборачивает математические выражения в $...$

Запуск (проверка без сохранения):
    ./venv/bin/python manage.py fix_bakharev_formulas --dry-run

Боевой прогон:
    ./venv/bin/python manage.py fix_bakharev_formulas
"""

import re
import unicodedata
from django.core.management.base import BaseCommand
from django.db import transaction
from problems.models import Problem, Source, ProblemPart


# ─────────────────────────────────────────────────────────────────────────────
# Таблица замен: Unicode math italic → ASCII/LaTeX
# ─────────────────────────────────────────────────────────────────────────────

def _build_math_italic_map():
    """
    Формат имён: 'MATHEMATICAL ITALIC CAPITAL T', 'MATHEMATICAL ITALIC SMALL X',
    'MATHEMATICAL ITALIC SMALL ALPHA' — последнее слово и есть буква/название.
    """
    m = {}
    for cp in range(0x1D400, 0x1D800):
        try:
            c = chr(cp)
            name = unicodedata.name(c)
        except (ValueError, KeyError):
            continue
        if 'MATHEMATICAL ITALIC' not in name:
            continue
        last = name.split()[-1]          # 'T', 'X', 'ALPHA', 'BETA', ...
        if 'CAPITAL' in name:
            if len(last) == 1 and last.isalpha():
                m[c] = last              # 'T' → 'T'
        elif 'SMALL' in name:
            if last == 'ALPHA':
                m[c] = r'\alpha'
            elif last == 'BETA':
                m[c] = r'\beta'
            elif len(last) == 1 and last.isalpha():
                m[c] = last.lower()      # 'X' → 'x'
    return m


MATH_ITALIC = _build_math_italic_map()
MATH_ITALIC_SET = frozenset(MATH_ITALIC)

# Символы, которые могут входить в спан при расширении ВПРАВО
# Включает () для захвата f(x), min(c1,c2) и т.д.
_RIGHT_EXTEND = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    '0123456789 '
    '=+*/^()[]<>,._-'
    '−'               # U+2212 MINUS SIGN
    '⩽⩾≈·√∆∅¯≤≥≠'
    'αβΠ'
) | MATH_ITALIC_SET

# При расширении ВЛЕВО НЕ захватываем открывающие скобки
# (чтобы не получилось $(t$ из «(𝑡не целое число)»)
_LEFT_EXTEND = _RIGHT_EXTEND - frozenset('([{')


# ─────────────────────────────────────────────────────────────────────────────
# Конвертация содержимого спана
# ─────────────────────────────────────────────────────────────────────────────

def _convert_span(text: str) -> str:
    """
    Принимает текст математического спана (может содержать Unicode math italic),
    возвращает LaTeX-совместимую строку.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]

        if c in MATH_ITALIC:
            ascii_char = MATH_ITALIC[c]
            out.append(ascii_char)
            i += 1
            # Цифры сразу после переменной → степень: Q2 → Q^2
            if i < n and text[i].isdigit():
                digits = []
                while i < n and text[i].isdigit():
                    digits.append(text[i])
                    i += 1
                s = ''.join(digits)
                out.append(f'^{{{s}}}' if len(s) > 1 else f'^{s}')
            # Звёздочка оптимума: Q* → Q^*
            elif i < n and text[i] == '*':
                out.append('^*')
                i += 1

        elif c == '¯':
            # ¯X → \bar{X}
            j = i + 1
            if j < n:
                nc = text[j]
                ac = MATH_ITALIC.get(nc, nc)
                out.append(f'\\bar{{{ac}}}')
                i = j + 1
            else:
                i += 1

        elif c == '√':
            # √X → \sqrt{X} для одного символа
            j = i + 1
            while j < n and text[j] == ' ':
                j += 1
            if j < n:
                nc = text[j]
                if nc in MATH_ITALIC_SET or nc.isalpha() or nc.isdigit():
                    ac = MATH_ITALIC.get(nc, nc)
                    out.append(f'\\sqrt{{{ac}}}')
                    i = j + 1
                    continue
            out.append('\\sqrt{}')
            i += 1

        elif c == '⩽':
            out.append('\\leqslant ')
            i += 1
        elif c == '⩾':
            out.append('\\geqslant ')
            i += 1
        elif c == '−':          # U+2212 MINUS SIGN
            out.append('-')
            i += 1
        elif c == '·':
            out.append('\\cdot ')
            i += 1
        elif c == '∆':
            out.append('\\Delta ')
            i += 1
        elif c == '∅':
            out.append('\\emptyset')
            i += 1
        elif c == '≈':
            out.append('\\approx ')
            i += 1
        elif c == 'Π':
            out.append('\\Pi')
            i += 1
        else:
            out.append(c)
            i += 1

    result = ''.join(out)
    # Убираем двойные пробелы (возникают когда \cdot+ пробел + оригинальный пробел)
    import re as _re
    result = _re.sub(r'  +', ' ', result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Поиск математических спанов в одной строке
# ─────────────────────────────────────────────────────────────────────────────

def _process_line(line: str):
    """
    Находит математические спаны в строке, оборачивает в $...$.
    Возвращает (новая_строка, список_примеров).
    Пример элемента списка: (исходный_текст_спана, конвертированный_текст).
    """
    if not any(c in MATH_ITALIC_SET for c in line):
        return line, []

    # Не трогаем строки, уже содержащие $
    if '$' in line or '\\(' in line:
        return line, []

    # Позиции якорей (Unicode math italic)
    anchors = [i for i, c in enumerate(line) if c in MATH_ITALIC_SET]

    # Для каждого якоря расширяем спан влево и вправо
    raw_spans = []
    for pos in anchors:
        start = pos
        while start > 0 and line[start - 1] in _LEFT_EXTEND:
            start -= 1
        end = pos + 1
        while end < len(line) and line[end] in _RIGHT_EXTEND:
            end += 1
        raw_spans.append((start, end))

    # Объединяем пересекающиеся спаны
    raw_spans.sort()
    merged = []
    for s, e in raw_spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append([s, e])

    # Строим результат
    parts = []
    prev = 0
    examples = []

    for start, end in merged:
        parts.append(line[prev:start])
        raw = line[start:end]

        # Отрезаем ведущие пробелы (они идут до $)
        stripped = raw.lstrip(' ')
        leading = raw[: len(raw) - len(stripped)]

        # Отрезаем хвостовые знаки препинания (они идут после $)
        content = stripped
        trailing = ''
        while content and content[-1] in ' .,;:':
            trailing = content[-1] + trailing
            content = content[:-1]

        if content and any(c in MATH_ITALIC_SET for c in content):
            converted = _convert_span(content)
            examples.append((content, converted))
            parts.append(f'{leading}${converted}${trailing}')
        else:
            parts.append(raw)

        prev = end

    parts.append(line[prev:])
    return ''.join(parts), examples


def fix_text(text: str):
    """
    Обрабатывает весь текст поля (может быть многострочным).
    Возвращает (новый_текст, список_примеров).
    """
    if not text:
        return text, []

    lines = text.split('\n')
    new_lines = []
    all_examples = []

    for line in lines:
        new_line, exs = _process_line(line)
        new_lines.append(new_line)
        all_examples.extend(exs)

    return '\n'.join(new_lines), all_examples


# ─────────────────────────────────────────────────────────────────────────────
# Management command
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Исправляет Unicode-математику в задачах Бахарева (Source #4)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать примеры ДО/ПОСЛЕ без сохранения',
        )
        parser.add_argument(
            '--source-id',
            type=int,
            default=4,
            help='ID источника (по умолчанию 4 = Бахарев)',
        )
        parser.add_argument(
            '--examples',
            type=int,
            default=10,
            help='Количество примеров для --dry-run',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        source_id = options['source_id']
        max_examples = options['examples']

        try:
            source = Source.objects.get(pk=source_id)
        except Source.DoesNotExist:
            self.stderr.write(f'Source #{source_id} не найден')
            return

        self.stdout.write(f'Источник: {source} (#{source_id})')

        problems = (
            Problem.objects
            .filter(source_references__source=source)
            .distinct()
            .prefetch_related('parts')
            .order_by('id')
        )
        total = problems.count()
        self.stdout.write(f'Задач: {total}\n')

        all_examples = []    # (problem_id, field_name, before, after)
        changed_problems = 0
        changed_parts = 0

        for problem in problems:
            prob_changed = False

            # Обрабатываем поля задачи
            for field in ('statement', 'answer', 'solution'):
                original = getattr(problem, field) or ''
                if not original:
                    continue
                new_text, _ = fix_text(original)
                if new_text != original:
                    all_examples.append((problem.id, field, original, new_text))
                    if not dry_run:
                        setattr(problem, field, new_text)
                    prob_changed = True

            if prob_changed and not dry_run:
                problem.save(update_fields=['statement', 'answer', 'solution'])
                changed_problems += 1
            elif prob_changed:
                changed_problems += 1

            # Обрабатываем подпункты
            for part in problem.parts.all():
                part_changed = False
                for field in ('statement', 'answer'):
                    original = getattr(part, field) or ''
                    if not original:
                        continue
                    new_text, _ = fix_text(original)
                    if new_text != original:
                        all_examples.append((problem.id, f'part.{part.label}.{field}', original, new_text))
                        if not dry_run:
                            setattr(part, field, new_text)
                        part_changed = True

                if part_changed and not dry_run:
                    part.save(update_fields=['statement', 'answer'])
                    changed_parts += 1
                elif part_changed:
                    changed_parts += 1

        # ── Вывод примеров ──────────────────────────────────────────────────
        self.stdout.write(f'\n{"─"*60}')
        self.stdout.write(f'Примеры преобразований (первые {max_examples}):')
        self.stdout.write(f'{"─"*60}')

        shown = 0
        for pid, field, original, new_text in all_examples:
            if shown >= max_examples:
                break
            # Показываем первую изменившуюся строку для компактности
            orig_lines = original.split('\n')
            new_lines = new_text.split('\n')
            for ol, nl in zip(orig_lines, new_lines):
                if ol != nl:
                    self.stdout.write(f'\nЗадача #{pid} [{field}]')
                    self.stdout.write(f'  ДО:    {ol}')
                    self.stdout.write(f'  ПОСЛЕ: {nl}')
                    break
            shown += 1

        self.stdout.write(f'\n{"─"*60}')
        self.stdout.write(
            f'Всего изменений в примерах: {len(all_examples)}'
        )
        self.stdout.write(
            f'Задач затронуто: {changed_problems}, подпунктов: {changed_parts}'
        )

        if dry_run:
            self.stdout.write('\n[DRY-RUN] Изменения НЕ сохранены.')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nГотово. Сохранено задач: {changed_problems}, подпунктов: {changed_parts}.'
                )
            )
