"""
Команда process_duplicates — автоматически обрабатывает пары DuplicateCandidate
со статусом pending, разделяя их на две группы по уровню похожести.

Группа А (similarity >= 0.97):
  - Сохраняет данные problem_b в JSON-бэкап (папка duplicates_backup/ в корне проекта).
  - Помечает problem_b.status = 'duplicate'.
  - Помечает пару как confirmed.

Группа Б (similarity 0.95–0.96):
  - Помечает problem_b.status = 'hidden'.
  - Устанавливает problem_b.duplicate_of = problem_a.
  - Помечает пару как confirmed.

Обрабатывается батчами по BATCH_SIZE. Поддерживает --dry-run.

Запуск:
    ./venv/bin/python manage.py process_duplicates
    ./venv/bin/python manage.py process_duplicates --dry-run
    ./venv/bin/python manage.py process_duplicates --batch-size 500
"""

import json
import os
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import DuplicateCandidate, Problem, ProblemPart, SourceReference

BATCH_SIZE = 200
THRESHOLD_A = 0.97   # >= этого порога — группа А (duplicate)
THRESHOLD_B = 0.95   # >= этого порога и < THRESHOLD_A — группа Б (hidden)


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _serialize_problem(problem):
    """Сериализует задачу и связанные данные в dict для JSON-бэкапа."""
    parts = list(
        ProblemPart.objects.filter(problem=problem).values(
            'label', 'statement', 'answer', 'solution', 'points', 'order'
        )
    )
    sources = list(
        SourceReference.objects.filter(problem=problem)
        .select_related('source')
        .values('source__name', 'source__kind', 'url', 'note', 'stage', 'grade', 'problem_number', 'page')
    )
    return {
        'id': problem.pk,
        'title': problem.title,
        'statement': problem.statement,
        'answer': problem.answer,
        'solution': problem.solution,
        'problem_type': problem.problem_type,
        'difficulty': problem.difficulty,
        'difficulty_native': problem.difficulty_native,
        'status': problem.status,
        'content_hash': problem.content_hash,
        'topics': list(problem.topics.values_list('name', flat=True)),
        'tags': list(problem.tags.values_list('name', flat=True)),
        'skills': list(problem.skills.values_list('name', flat=True)),
        'mistakes': list(problem.mistakes.values_list('name', flat=True)),
        'parts': parts,
        'sources': sources,
        'created_at': problem.created_at.isoformat(),
        'updated_at': problem.updated_at.isoformat(),
    }


class Command(BaseCommand):
    help = 'Обрабатывает пары DuplicateCandidate: помечает дубли и скрывает похожие'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать количество по группам без изменений в базе',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=BATCH_SIZE,
            help=f'Размер батча (по умолчанию {BATCH_SIZE})',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']

        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY-RUN: изменения не сохраняются ==='))

        pending = DuplicateCandidate.objects.filter(status='pending')
        total = pending.count()
        self.stdout.write(f'Пар со статусом pending: {total}')

        group_a = pending.filter(similarity__gte=THRESHOLD_A)
        group_b = pending.filter(similarity__gte=THRESHOLD_B, similarity__lt=THRESHOLD_A)
        count_a = group_a.count()
        count_b = group_b.count()

        self.stdout.write(
            f'  Группа А (similarity >= {THRESHOLD_A}): {count_a} пар → статус duplicate'
        )
        self.stdout.write(
            f'  Группа Б (similarity {THRESHOLD_B}–{THRESHOLD_A - 0.01:.2f}): '
            f'{count_b} пар → статус hidden + duplicate_of'
        )

        if dry_run:
            self.stdout.write(self.style.SUCCESS('Dry-run завершён. Изменений нет.'))
            return

        # --- Группа А ---
        backup_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ))),
            'duplicates_backup',
        )
        os.makedirs(backup_dir, exist_ok=True)
        backup_filename = f'duplicates_group_a_{date.today().isoformat()}.json'
        backup_path = os.path.join(backup_dir, backup_filename)

        done_a = 0
        backup_records = []

        while True:
            # Всегда берём первые batch_size — обработанные пары уже не попадают
            # в group_a (их статус меняется с pending на confirmed).
            batch = list(
                group_a.select_related('problem_a', 'problem_b')[:batch_size]
            )
            if not batch:
                break

            with transaction.atomic():
                for pair in batch:
                    pb = pair.problem_b
                    backup_records.append({
                        'pair_id': pair.pk,
                        'similarity': pair.similarity,
                        'problem_a_id': pair.problem_a_id,
                        'problem_b': _serialize_problem(pb),
                    })
                    pb.status = Problem.Status.DUPLICATE
                    pb.save(update_fields=['status', 'updated_at'])
                    pair.status = 'confirmed'
                    pair.save(update_fields=['status', 'reviewed_at'])

            done_a += len(batch)
            self.stdout.write(f'  Группа А: обработано {done_a}/{count_a}...')

        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(backup_records, f, ensure_ascii=False, indent=2, cls=_DecimalEncoder)

        # --- Группа Б ---
        done_b = 0
        while True:
            batch = list(
                group_b.select_related('problem_a', 'problem_b')[:batch_size]
            )
            if not batch:
                break

            with transaction.atomic():
                for pair in batch:
                    pb = pair.problem_b
                    pb.status = Problem.Status.HIDDEN
                    pb.duplicate_of = pair.problem_a
                    pb.save(update_fields=['status', 'duplicate_of', 'updated_at'])
                    pair.status = 'confirmed'
                    pair.save(update_fields=['status', 'reviewed_at'])

            done_b += len(batch)
            self.stdout.write(f'  Группа Б: обработано {done_b}/{count_b}...')

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Группа А: {done_a} задач помечено как duplicate\n'
            f'  Группа Б: {done_b} задач помечено как hidden + duplicate_of\n'
            f'  Бэкап группы А: {backup_path}'
        ))
