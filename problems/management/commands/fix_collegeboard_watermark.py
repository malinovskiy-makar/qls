"""
fix_collegeboard_watermark — вырезает служебный watermark CollegeBoard из полей задач.

Паттерны (режутся всё от первого совпадения до конца поля):
  1. "\n\nAdditional answer page" (начало blank-раздела)
  2. "\nTHIS PAGE MAY BE USED FOR TAKING NOTES"
  3. "any part of this page is illegal"
  4. "unauthorized reproduction or use"

Применяется к ProblemPart.statement и Problem.statement.
Только задачи из источника AP Economics (id 7, 8, 18, 20, 21, 22) — где встречается.

Использование:
    ./venv/bin/python manage.py fix_collegeboard_watermark --dry-run
    ./venv/bin/python manage.py fix_collegeboard_watermark
"""

import re
from django.core.management.base import BaseCommand
from django.db import transaction
from problems.models import Problem, ProblemPart

CHANGED_IDS_FILE = 'reports/quality_audit/changed_ids_G.txt'

# Паттерны по приоритету (режем по первому совпадению)
CUT_PATTERNS = [
    re.compile(r'\n\nAdditional answer page', re.IGNORECASE),
    re.compile(r'\nTHIS PAGE MAY BE USED FOR TAKING NOTES', re.IGNORECASE),
    re.compile(r'unauthorized reproduction or use', re.IGNORECASE),
    re.compile(r'any part of this page is illegal', re.IGNORECASE),
]


def find_cut_pos(text):
    """Находит позицию для обрезки — минимальная позиция среди всех паттернов."""
    if not text:
        return None
    candidates = []
    for pat in CUT_PATTERNS:
        m = pat.search(text)
        if m:
            candidates.append(m.start())
    return min(candidates) if candidates else None


def clean_text(text):
    """Возвращает текст с вырезанным watermark или None если не нужно менять."""
    if not text:
        return None
    pos = find_cut_pos(text)
    if pos is None:
        return None
    cleaned = text[:pos].rstrip()
    if cleaned == text.rstrip():
        return None  # ничего не изменилось
    return cleaned


class Command(BaseCommand):
    help = 'Вырезает watermark CollegeBoard из statement задач и подпунктов'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--all', action='store_true', dest='all_sources')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Источники AP Economics
        AP_SOURCE_IDS = [7, 8, 18, 20, 21, 22]

        changed_problem_ids = set()
        parts_changed = 0
        problems_changed = 0

        # --- ProblemPart ---
        part_qs = ProblemPart.objects.filter(
            problem__source_references__source_id__in=AP_SOURCE_IDS,
            statement__icontains='illegal'
        ).distinct()

        self.stdout.write(f'Проверяем ProblemPart: {part_qs.count()} кандидатов...')
        examples_shown = 0
        for pp in part_qs.iterator():
            cleaned = clean_text(pp.statement)
            if cleaned is None:
                continue
            if dry_run and examples_shown < 5:
                self.stdout.write(f'  PP {pp.id} (prob {pp.problem_id}):')
                self.stdout.write(f'    БЫЛО: {repr(pp.statement[:200])}')
                self.stdout.write(f'    СТАНЕТ: {repr(cleaned[:150])}')
                examples_shown += 1
            if not dry_run:
                pp.statement = cleaned
                pp.save(update_fields=['statement'])
            changed_problem_ids.add(pp.problem_id)
            parts_changed += 1

        # --- Problem.statement ---
        prob_qs = Problem.objects.filter(
            source_references__source_id__in=AP_SOURCE_IDS,
            statement__icontains='illegal'
        ).distinct()

        self.stdout.write(f'Проверяем Problem.statement: {prob_qs.count()} кандидатов...')
        examples_shown = 0
        for p in prob_qs.iterator():
            cleaned = clean_text(p.statement)
            if cleaned is None:
                continue
            if dry_run and examples_shown < 3:
                self.stdout.write(f'  Problem {p.id}:')
                self.stdout.write(f'    БЫЛО: {repr(p.statement[:200])}')
                self.stdout.write(f'    СТАНЕТ: {repr(cleaned[:150])}')
                examples_shown += 1
            if not dry_run:
                p.statement = cleaned
                p.save(update_fields=['statement'])
            changed_problem_ids.add(p.id)
            problems_changed += 1

        self.stdout.write(f'\nProblemPart изменено: {parts_changed}')
        self.stdout.write(f'Problem.statement изменено: {problems_changed}')
        self.stdout.write(f'Уникальных задач: {len(changed_problem_ids)}')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: изменения не сохранены'))
            return

        # Запись изменённых id
        with open(CHANGED_IDS_FILE, 'a') as f:
            for pid in sorted(changed_problem_ids):
                f.write(f'{pid}\n')

        self.stdout.write(self.style.SUCCESS('Готово'))
