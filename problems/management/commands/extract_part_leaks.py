"""
extract_part_leaks.py — сессия H, этап 3e.

Экстрактор утечек решений/ответов из statement ПОДПУНКТОВ (existing
extract_leaked_solutions работает только по Problem.statement).
Улика: #4638 — «Решение:» с полным решением внутри ProblemPart.statement.

Маркеры (с Заглавной, в начале строки): «Решение[:.]?», «Ответ(ы)[:.]».
Предохранители (как в основном экстракторе):
  - маркер не раньше 20-го символа (голова не может опустеть);
  - целевые непустые поля не перезаписываются:
      tail >= 120 симв. → Problem.solution (если пусто; с префиксом «(метка) »),
                          иначе ProblemPart.answer (если пусто),
                          иначе если tail совпадает с уже сохранённым — только
                          вырезание, иначе ручной разбор;
      tail < 120 симв.  → ProblemPart.answer (если пусто/совпадает),
                          иначе ручной разбор.
Идемпотентен: после вырезания маркера повторный прогон кандидата не находит.

Запуск:
    ./venv/bin/python manage.py extract_part_leaks --dry-run --examples 10
    ./venv/bin/python manage.py extract_part_leaks --all
"""

import os
import re

from django.core.management.base import BaseCommand

from problems.models import ProblemPart

REPORT_DIR = 'reports/sessionH'
CHANGED_IDS_FILE = os.path.join(REPORT_DIR, 'changed_ids_H.txt')
MANUAL_FILE = os.path.join(REPORT_DIR, '03e_manual_review_part_ids.txt')

MARKER_RE = re.compile(r'(?:^|\n)[ \t]*(Решение[:.]?|Ответ(?:ы)?[:.])[ \t]*\n?')

MIN_HEAD = 20          # маркер не раньше этой позиции
LONG_TAIL = 120        # длинный хвост → решение


def _append_ids(ids):
    existing = set()
    if os.path.exists(CHANGED_IDS_FILE):
        with open(CHANGED_IDS_FILE) as f:
            existing = {int(l.strip()) for l in f if l.strip().isdigit()}
    with open(CHANGED_IDS_FILE, 'w') as f:
        for i in sorted(existing | set(ids)):
            f.write(f'{i}\n')


class Command(BaseCommand):
    help = 'Перенос «Решение:/Ответ:» из statement подпунктов в solution/answer'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--all', action='store_true', default=False)
        parser.add_argument('--source-id', type=int, default=None)
        parser.add_argument('--examples', type=int, default=10)

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)
        dry_run = options['dry_run'] or not options['all']

        parts = (ProblemPart.objects.exclude(statement='')
                 .select_related('problem').order_by('problem_id', 'id'))
        if options['source_id']:
            parts = parts.filter(
                problem__source_references__source_id=options['source_id'])

        stats = {'to_solution': 0, 'to_part_answer': 0, 'cut_duplicate': 0,
                 'manual': 0}
        changed_ids = set()
        manual = []
        examples_left = options['examples']
        # problem.solution может быть заполнен предыдущим подпунктом в этом же
        # прогоне — отслеживаем локально
        filled_solutions = {}

        for part in parts.iterator(chunk_size=1000):
            st = part.statement or ''
            m = MARKER_RE.search(st)
            if not m or m.start() < MIN_HEAD:
                continue
            head = st[:m.start()].rstrip()
            tail = st[m.end():].strip()
            if not head or not tail:
                continue
            p = part.problem
            kind = 'решение' if m.group(1).startswith('Реш') else 'ответ'

            cur_solution = filled_solutions.get(p.id, p.solution or '')
            action = None
            if len(tail) >= LONG_TAIL:
                if not cur_solution.strip():
                    action = 'to_solution'
                elif not (part.answer or '').strip():
                    action = 'to_part_answer'
                elif tail in cur_solution or tail == (part.answer or '').strip():
                    action = 'cut_duplicate'
            else:
                pa = (part.answer or '').strip()
                if not pa:
                    action = 'to_part_answer'
                elif pa == tail:
                    action = 'cut_duplicate'

            if action is None:
                stats['manual'] += 1
                manual.append(f'{p.id}\tpart {part.label}\t{kind}\ttail {len(tail)}')
                continue

            stats[action] += 1
            if examples_left > 0:
                examples_left -= 1
                self.stdout.write(
                    f'--- prob #{p.id} part({part.label}) [{kind}] → {action}\n'
                    f'  голова: {head[-90:]!r}\n'
                    f'  хвост ({len(tail)}): {tail[:90]!r}')

            if dry_run:
                changed_ids.add(p.id)
                if action == 'to_solution':
                    filled_solutions[p.id] = tail
                continue

            part.statement = head
            if action == 'to_solution':
                p.solution = f'({part.label}) {tail}'
                p.save(update_fields=['solution'])
                filled_solutions[p.id] = p.solution
            elif action == 'to_part_answer':
                part.answer = tail
            part.save(update_fields=['statement', 'answer'])
            changed_ids.add(p.id)

        if manual:
            with open(MANUAL_FILE, 'w') as f:
                f.write('\n'.join(manual) + '\n')

        mode = 'DRY-RUN' if dry_run else 'БОЕВОЙ'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: задач затронуто {len(changed_ids)}, действия: {stats}'
            + (f'; ручной разбор → {MANUAL_FILE}' if manual else '')))
        if not dry_run and changed_ids:
            _append_ids(changed_ids)
