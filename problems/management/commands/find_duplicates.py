"""
Команда find_duplicates — ищет пары задач-дубликатов по косинусному сходству
эмбеддингов. Пары с similarity >= 0.95 сохраняются в DuplicateCandidate.

Логика:
  - Грузит эмбеддинги батчами по 1000 (не держит всё в памяти).
  - Для каждого батча считает сходство со всеми остальными задачами.
  - Пара (A, B) всегда сохраняется с a.id < b.id — без дублей.
  - get_or_create — не создаёт запись, если пара уже есть в базе.

Запуск:
    ./venv/bin/python manage.py find_duplicates
    ./venv/bin/python manage.py find_duplicates --threshold 0.90
    ./venv/bin/python manage.py find_duplicates --reset
"""

import time

import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import DuplicateCandidate, Problem

LOAD_BATCH = 1000   # сколько задач грузим за раз


def load_all_embeddings():
    """Загружает все эмбеддинги из базы. Возвращает (ids, matrix)."""
    ids = []
    vecs = []

    qs = (Problem.objects
          .filter(embedding__isnull=False)
          .only('id', 'embedding')
          .values_list('id', 'embedding'))

    for pid, raw_emb in qs.iterator(chunk_size=LOAD_BATCH):
        raw = bytes(raw_emb)
        if not raw:
            continue
        vec = np.frombuffer(raw, dtype=np.float32)
        ids.append(pid)
        vecs.append(vec)

    if not ids:
        return [], None

    matrix = np.stack(vecs)   # shape (N, dim)
    return ids, matrix


def cosine_sim_batch(query_rows: np.ndarray, all_rows: np.ndarray) -> np.ndarray:
    """Косинусное сходство query_rows (M, dim) × all_rows (N, dim) → (M, N)."""
    # Нормируем строки
    q_norms = np.linalg.norm(query_rows, axis=1, keepdims=True)
    q_norms = np.where(q_norms == 0, 1e-9, q_norms)
    q_normed = query_rows / q_norms

    a_norms = np.linalg.norm(all_rows, axis=1, keepdims=True)
    a_norms = np.where(a_norms == 0, 1e-9, a_norms)
    a_normed = all_rows / a_norms

    return q_normed @ a_normed.T   # (M, N)


class Command(BaseCommand):
    help = 'Ищет дубликаты задач через косинусное сходство эмбеддингов (Этап 5б)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--threshold', type=float, default=0.95,
            help='Порог сходства для признания задач дубликатами (по умолчанию 0.95).'
        )
        parser.add_argument(
            '--reset', action='store_true',
            help='Удалить все существующие DuplicateCandidate перед запуском.'
        )

    def handle(self, *args, **options):
        threshold = options['threshold']
        reset = options['reset']

        if reset:
            deleted, _ = DuplicateCandidate.objects.all().delete()
            self.stdout.write(f'Удалено существующих пар: {deleted}')

        self.stdout.write(f'Загружаем эмбеддинги (порог сходства: {threshold})...')
        t0 = time.time()
        all_ids, matrix = load_all_embeddings()

        if not all_ids:
            self.stdout.write('Нет задач с эмбеддингами. Сначала запустите build_embeddings.')
            return

        n = len(all_ids)
        self.stdout.write(f'Задач с эмбеддингами: {n} (загружено за {time.time() - t0:.1f}с)')

        # Строим словарь id → индекс для быстрого поиска
        id_to_idx = {pid: i for i, pid in enumerate(all_ids)}

        new_pairs = 0
        existing_pairs = 0
        t_start = time.time()

        # Обрабатываем задачи батчами
        for batch_start in range(0, n, LOAD_BATCH):
            batch_end = min(batch_start + LOAD_BATCH, n)
            batch_ids = all_ids[batch_start:batch_end]
            batch_matrix = matrix[batch_start:batch_end]  # (M, dim)

            # Косинусное сходство батча со ВСЕМИ задачами: (M, N)
            sim_matrix = cosine_sim_batch(batch_matrix, matrix)

            # Собираем пары выше порога
            pairs_to_create = []
            for local_i, pid_a in enumerate(batch_ids):
                global_i = batch_start + local_i
                sims = sim_matrix[local_i]  # (N,)

                # Ищем индексы выше порога — только те, где глобальный индекс > global_i
                # (чтобы не дублировать пары: A<B и чтобы не брать саму задачу)
                candidates = np.where(sims >= threshold)[0]
                for j in candidates:
                    if j <= global_i:
                        # Пропускаем саму задачу и уже учтённые пары
                        continue
                    pid_b = all_ids[j]
                    sim_val = float(sims[j])

                    # Инвариант: a.id < b.id
                    if pid_a < pid_b:
                        a_id, b_id = pid_a, pid_b
                    else:
                        a_id, b_id = pid_b, pid_a

                    pairs_to_create.append((a_id, b_id, sim_val))

            # Сохраняем пары в базу через get_or_create
            if pairs_to_create:
                with transaction.atomic():
                    for a_id, b_id, sim_val in pairs_to_create:
                        _, created = DuplicateCandidate.objects.get_or_create(
                            problem_a_id=a_id,
                            problem_b_id=b_id,
                            defaults={'similarity': sim_val},
                        )
                        if created:
                            new_pairs += 1
                        else:
                            existing_pairs += 1

            processed = batch_end
            if processed % LOAD_BATCH == 0 or processed == n:
                elapsed = time.time() - t_start
                self.stdout.write(
                    f'  {processed}/{n} задач проверено, '
                    f'новых пар: {new_pairs}, '
                    f'уже было: {existing_pairs} '
                    f'({elapsed:.0f}с)'
                )

        total_in_db = DuplicateCandidate.objects.count()
        elapsed = time.time() - t_start
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Готово за {elapsed:.1f}с:\n'
            f'  Новых пар найдено: {new_pairs}\n'
            f'  Уже было в базе:   {existing_pairs}\n'
            f'  Всего в базе:      {total_in_db}'
        ))
