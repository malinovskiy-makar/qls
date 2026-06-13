"""
fix_part_markers.py — нормализация маркеров подпунктов (B6).

Источник: только Archive 3 (source_id=14) — полностью русский.

Проблема: некоторые задачи в statement содержат смешанные маркеры:
  латинское «a)» рядом с кириллическими «б)», «в)» и т.д.

Правило: латинские маркеры a/b/c/d/e (строчные и заглавные) вне мат-спанов,
  если они стоят как маркеры варианта (после пробела/переноса строки),
  → заменяются на кириллические а/б/в/г/д.

ЖЕЛЕЗНЫЕ ПРАВИЛА:
  - content_hash не трогаем
  - только statement (не answer/solution — нет маркеров там)
  - только source_id=14 (Archive 3)
  - --dry-run + идемпотентность
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem

REPORT_DIR = 'reports/quality_audit'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids_F.txt')

# Маппинг латиница → кириллица (оба регистра → строчный кириллический маркер)
LAT_TO_CYR = {
    'a': 'а', 'A': 'а',
    'b': 'б', 'B': 'б',
    'c': 'в', 'C': 'в',
    'd': 'г', 'D': 'г',
    'e': 'д', 'E': 'д',
}

# Два паттерна маркеров:
# 1. Начало строки: захватываем ВЕСЬ префикс + буква + )
#    группа 1 = prefix (newline+spaces), группа 2 = буква
LINE_START_RE = re.compile(
    r'(\n[ \t]*(?:•[ \t]*)?)([a-eA-E])\)',
    re.MULTILINE,
)
# 2. (a) формат: «(» сразу перед буквой, не предшествует слово
PAREN_MARKER_RE = re.compile(r'(?<!\w)\(([a-eA-E])\)')

# Простой поиск латинского маркера (для быстрой проверки)
_LAT_ANY_RE = re.compile(r'(?<!\w)[a-eA-E]\)')
# Кириллический маркер — для проверки что смешение есть
CYR_MARKER_RE = re.compile(r'(?<!\w)[аАбБвВгГдД]\)')

# Мат-спаны
MATH_SPAN_RE = re.compile(
    r'\\\[.+?\\\]'
    r'|\\\(.+?\\\)'
    r'|\$\$.+?\$\$'
    r'|\$[^$]+?\$',
    re.DOTALL,
)
_PH = '\x00M\x00'
_PH_RE = re.compile(re.escape(_PH))


def _mask(text):
    spans = []
    def _r(m):
        spans.append(m.group(0))
        return _PH
    t = text.replace('\\$', '\x00D\x00')
    t = MATH_SPAN_RE.sub(_r, t)
    return t, spans


def _unmask(text, spans):
    it = iter(spans)
    r = _PH_RE.sub(lambda _: next(it), text)
    return r.replace('\x00D\x00', '\\$')


def fix_markers(text):
    """
    Заменяет латинские маркеры вариантов на кириллические.
    Только если в тексте есть хотя бы один кириллический маркер (смешение).
    """
    if not text:
        return text
    if not _LAT_ANY_RE.search(text):
        return text
    if not CYR_MARKER_RE.search(text):
        return text  # нет кириллических — это англоязычный текст, не трогаем

    masked, spans = _mask(text)

    def _replace_line(m):
        prefix = m.group(1)  # newline + spaces
        letter = m.group(2)
        return prefix + LAT_TO_CYR.get(letter, letter) + ')'

    def _replace_paren(m):
        letter = m.group(1)
        return '(' + LAT_TO_CYR.get(letter, letter) + ')'

    fixed = LINE_START_RE.sub(_replace_line, masked)
    fixed = PAREN_MARKER_RE.sub(_replace_paren, fixed)

    if fixed == masked:
        return text
    return _unmask(fixed, spans)


def _append_ids(ids):
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE):
        with open(CHANGED_IDS_FILE) as f:
            existing = {int(l.strip()) for l in f if l.strip().isdigit()}
    with open(CHANGED_IDS_FILE, 'w') as f:
        for i in sorted(existing | set(ids)):
            f.write(f'{i}\n')


class Command(BaseCommand):
    help = 'Нормализация латинских маркеров подпунктов (B6) для source #14'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False,
                            help='Боевой прогон')
        parser.add_argument('--examples', type=int, default=20)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        dry_run = options['dry_run']
        do_all  = options['all']
        n_ex    = options['examples']

        if not dry_run and not do_all:
            self.stderr.write('Укажи --all для боевого прогона или --dry-run.')
            return

        qs = (
            Problem.objects
            .filter(
                status='published',
                needs_quality_review=False,
                source_references__source_id=14,
            )
            .distinct()
            .only('id', 'statement')
        )

        total = 0
        changed_ids = []
        examples = []

        for problem in qs.iterator(chunk_size=500):
            total += 1
            old_stmt = problem.statement or ''
            new_stmt = fix_markers(old_stmt)

            if new_stmt == old_stmt:
                continue

            changed_ids.append(problem.id)
            if len(examples) < n_ex:
                # Find first changed line for display
                old_lines = old_stmt.splitlines()
                new_lines = new_stmt.splitlines()
                diff_lines = []
                for ol, nl in zip(old_lines, new_lines):
                    if ol != nl:
                        diff_lines.append((ol[:80], nl[:80]))
                        if len(diff_lines) >= 2:
                            break
                examples.append((problem.id, diff_lines))

            if dry_run:
                continue

            problem.statement = new_stmt
            problem.save(update_fields=['statement'])

            if total % 2000 == 0:
                self.stdout.write(f'  ...{total} задач обработано')

        if dry_run:
            self.stdout.write(f'=== DRY-RUN: изменится {len(changed_ids)} задач из {total} ===')
            self.stdout.write('')
            for pid, diff_lines in examples[:n_ex]:
                self.stdout.write(f'  #{pid}:')
                for ol, nl in diff_lines:
                    self.stdout.write(f'    ДО:    {ol}')
                    self.stdout.write(f'    ПОСЛЕ: {nl}')
            return

        _append_ids(changed_ids)
        self.stdout.write(self.style.SUCCESS(
            f'Готово: изменено {len(changed_ids)} задач из {total} обработанных'
        ))
