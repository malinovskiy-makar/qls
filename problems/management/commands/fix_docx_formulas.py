"""
Очищает LaTeX-артефакты в задачах из Source #15 («Листки задач»).

Задачи импортировались через pandoc (DOCX→LaTeX), из-за чего часть
команд pandoc оставил в тексте как есть.

Запуск (проверка без сохранения):
    ./venv/bin/python manage.py fix_docx_formulas --dry-run

Боевой прогон:
    ./venv/bin/python manage.py fix_docx_formulas
"""

import re
from django.core.management.base import BaseCommand
from django.db import transaction
from problems.models import Problem, Source, ProblemPart


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _extract_balanced(text: str, pos: int):
    """
    Возвращает (content, end_pos) для балансного содержимого {…} начиная с pos.
    pos должен указывать на '{'.
    """
    if pos >= len(text) or text[pos] != '{':
        return None, pos
    depth = 0
    i = pos
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            i += 2  # пропускаем экранированный символ
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[pos + 1:i], i + 1
        i += 1
    return text[pos + 1:], len(text)


def _strip_command(text: str, cmd: str, transform):
    """
    Заменяет все \\CMD{…} на transform(content).
    Поддерживает вложенные фигурные скобки.
    """
    result = []
    i = 0
    needle = f'\\{cmd}{{'
    while i < len(text):
        idx = text.find(needle, i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
        content, end_pos = _extract_balanced(text, idx + len(needle) - 1)
        if content is not None:
            result.append(transform(content))
            i = end_pos
        else:
            result.append(text[idx])
            i = idx + 1
    return ''.join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Основная функция очистки
# ─────────────────────────────────────────────────────────────────────────────

def fix_text(text: str) -> str:
    if not text:
        return text

    # ── Шаг 1: замена команд с балансными скобками ────────────────────────
    # \footnote{content} → (content)
    text = _strip_command(text, 'footnote', lambda c: f' ({c.strip()})')
    # \hl{content} → content (подсветка правильного ответа — убираем обёртку)
    text = _strip_command(text, 'hl', lambda c: c)
    # \emph{content} → content
    text = _strip_command(text, 'emph', lambda c: c)
    # \textsc{content} → content
    text = _strip_command(text, 'textsc', lambda c: c)
    # \pandocbounded{content} → content
    text = _strip_command(text, 'pandocbounded', lambda c: c)

    # ── Шаг 2: regex-замены (от сложного к простому) ──────────────────────
    # \hyperref[label]{text} → text (вложенные hyperref внутри тоже разберёт re)
    text = re.sub(r'\\hyperref\[[^\]]*\]\{([^}]*)\}', r'\1', text)
    # Повторный проход: в некоторых случаях hyperref вложены
    text = re.sub(r'\\hyperref\[[^\]]*\]\{([^}]*)\}', r'\1', text)

    # \label{...} → удалить
    text = re.sub(r'\\label\{[^}]*\}', '', text)

    # \phantomsection → удалить (артефакт pandoc 3.x)
    text = re.sub(r'\\phantomsection\b', '', text)

    # \subsubsection{text} → text (заголовок раздела в тексте задачи)
    text = re.sub(r'\\subsubsection\{([^}]*)\}', r'\1', text)
    # \section{} → удалить
    text = re.sub(r'\\section\{[^}]*\}', '', text)

    # \textless{} и \textgreater{}
    text = re.sub(r'\\textless\{\}', '<', text)
    text = re.sub(r'\\textgreater\{\}', '>', text)
    # без скобок (не перед буквой, чтобы не зацепить другие команды)
    text = re.sub(r'\\textless(?=[^a-zA-Z])', '<', text)
    text = re.sub(r'\\textgreater(?=[^a-zA-Z])', '>', text)

    # \textbackslash{} → \  (потом \{ → {, \} → } уже не нужны в большинстве случаев)
    text = re.sub(r'\\textbackslash\{\}', '\\\\', text)
    # \textbackslash <space> → \
    text = re.sub(r'\\textbackslash\s', '\\\\', text)
    # \textbackslash на конце строки или перед не-буквой
    text = re.sub(r'\\textbackslash\b', '\\\\', text)

    # \textsubscript{X} → _{X}
    text = re.sub(r'\\textsubscript\{([^}]+)\}', r'_{\1}', text)
    # \textsuperscript{X} → ^{X}
    text = re.sub(r'\\textsuperscript\{([^}]+)\}', r'^{\1}', text)

    # \hat{} → ^ (в выражениях вида Q\hat{}s → Q^s)
    text = re.sub(r'\\hat\{\}', '^', text)

    # \RL{content} → content (арабский RTL-маркер)
    text = re.sub(r'\\RL\{([^}]*)\}', r'\1', text)

    # \hfill\break → перевод строки
    text = re.sub(r'\\hfill\\break', '\n', text)
    # \hfill → удалить
    text = re.sub(r'\\hfill', '', text)
    # \break → удалить
    text = re.sub(r'\\break\b', '', text)
    # \strut → удалить
    text = re.sub(r'\\strut\b', '', text)

    # Элементы таблиц-longtable
    text = re.sub(r'\\endhead\b', '', text)
    text = re.sub(r'\\toprule\b', '', text)
    text = re.sub(r'\\bottomrule\b', '', text)
    text = re.sub(r'\\midrule\b', '', text)
    text = re.sub(r'\\tabularnewline\b', '', text)
    text = re.sub(r'\\multicolumn\{[^}]+\}\{[^}]+\}\{([^}]*)\}', r'\1', text)

    # pandoc-экранирование квадратных скобок: {[...} → [...  и  {]} → ]
    text = re.sub(r'\{(\[[^}]*)\}', r'\1', text)   # {[content} → [content
    text = re.sub(r'\{]\}', ']', text)              # {]} → ]

    # Пустые группы {} (остатки \phantomsection{} и пр.) — после всех замен
    # команд вида \textless{}; не трогаем ^{} и _{} внутри формул
    text = re.sub(r'(?<![\\^_])\{\}', '', text)

    # \\ в конце строки (разделитель строк таблицы) → удалить
    text = re.sub(r'\s*\\\\\s*$', '', text, flags=re.MULTILINE)

    # ── Шаг 3: построчная очистка ─────────────────────────────────────────
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()

        # Строки вида ")}" — артефакт pandoc для тестовых вопросов
        if re.match(r'^\s*\)\}\s*$', line):
            continue
        # "% do not increment counter"
        if '% do not increment' in line:
            continue
        # \end{longtable} и \begin{longtable}
        if stripped == r'\end{longtable}':
            continue
        if stripped.startswith(r'\begin{longtable}'):
            continue
        # Одиночная } — закрывающий блок окружения longtable
        if stripped == '}' and not re.search(r'\S', line.replace('}', '')):
            continue
        # { на одной строке (открывающий блок)
        if stripped == '{':
            continue

        cleaned.append(line)

    text = '\n'.join(cleaned)

    # ── Шаг 4: финальная уборка ────────────────────────────────────────────
    # Схлопываем три и более пустых строки → две
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


# ─────────────────────────────────────────────────────────────────────────────
# Management command
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Очищает LaTeX-артефакты pandoc в задачах из Source #15 (Листки задач)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать примеры ДО/ПОСЛЕ без сохранения',
        )
        parser.add_argument(
            '--source-id',
            type=int,
            default=15,
            help='ID источника (по умолчанию 15 = Листки задач)',
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

        all_changes = []   # (problem_id, field_name, before, after)
        changed_problems = 0
        changed_parts = 0

        for problem in problems:
            prob_dirty = False

            for field in ('statement', 'answer', 'solution'):
                original = getattr(problem, field) or ''
                if not original:
                    continue
                new_text = fix_text(original)
                if new_text != original:
                    all_changes.append((problem.id, field, original, new_text))
                    if not dry_run:
                        setattr(problem, field, new_text)
                    prob_dirty = True

            if prob_dirty:
                if not dry_run:
                    problem.save(update_fields=['statement', 'answer', 'solution'])
                changed_problems += 1

            for part in problem.parts.all():
                part_dirty = False
                for field in ('statement', 'answer'):
                    original = getattr(part, field) or ''
                    if not original:
                        continue
                    new_text = fix_text(original)
                    if new_text != original:
                        all_changes.append(
                            (problem.id, f'part.{part.label}.{field}', original, new_text)
                        )
                        if not dry_run:
                            setattr(part, field, new_text)
                        part_dirty = True

                if part_dirty:
                    if not dry_run:
                        part.save(update_fields=['statement', 'answer'])
                    changed_parts += 1

        # ── Вывод примеров ──────────────────────────────────────────────────
        self.stdout.write(f'\n{"─" * 60}')
        self.stdout.write(f'Примеры преобразований (первые {max_examples}):')
        self.stdout.write(f'{"─" * 60}')

        shown = 0
        for pid, field, original, new_text in all_changes:
            if shown >= max_examples:
                break
            # Ищем первую строку, которая изменилась
            orig_lines = original.split('\n')
            new_lines = new_text.split('\n')
            for ol, nl in zip(orig_lines, new_lines):
                if ol != nl:
                    self.stdout.write(f'\nЗадача #{pid} [{field}]')
                    self.stdout.write(f'  ДО:    {ol[:120]}')
                    self.stdout.write(f'  ПОСЛЕ: {nl[:120]}')
                    break
            else:
                # Изменилось число строк — показываем первые строки
                self.stdout.write(f'\nЗадача #{pid} [{field}] (изменилось число строк)')
                self.stdout.write(f'  ДО ({len(orig_lines)} строк):    {orig_lines[0][:100]}')
                self.stdout.write(f'  ПОСЛЕ ({len(new_lines)} строк): {new_lines[0][:100]}')
            shown += 1

        self.stdout.write(f'\n{"─" * 60}')
        self.stdout.write(f'Всего изменённых полей: {len(all_changes)}')
        self.stdout.write(f'Задач затронуто: {changed_problems}, подпунктов: {changed_parts}')

        if dry_run:
            self.stdout.write('\n[DRY-RUN] Изменения НЕ сохранены.')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nГотово. Сохранено задач: {changed_problems}, подпунктов: {changed_parts}.'
                )
            )
