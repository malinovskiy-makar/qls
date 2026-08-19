"""
Команда cache_similar — кеширует топ-5 похожих задач для каждой опубликованной задачи.

Кандидаты в «похожие» — только published задачи БЕЗ флага качественного шлюза
(needs_quality_review=False): чтобы после фильтрации на чтении блок «Похожие»
не редел. Сами цели (кому считаем кэш) — все published с эмбеддингом, включая
зафлагованные: если флаг потом снимут, кэш уже будет готов.

Запуск:
    ./venv/bin/python manage.py cache_similar
    ./venv/bin/python manage.py cache_similar --limit 5000
    ./venv/bin/python manage.py cache_similar --reset
    ./venv/bin/python manage.py cache_similar --rebuild   # быстрая полная пересборка
"""

import time

import numpy as np
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from problems.models import Problem

TOP_N = 5
POOL_N = 30        # запас кандидатов до фильтров (дубли, совпадающие заголовки)
LOAD_BATCH = 1000  # батч для загрузки матрицы эмбеддингов


def load_exclusion_maps():
    """Карты для гигиены выдачи (сессия E): дубль↔оригинал и заголовки."""
    dup_map = dict(Problem.objects.filter(duplicate_of__isnull=False)
                   .values_list('id', 'duplicate_of_id'))
    titles = dict(Problem.objects.exclude(title='')
                  .values_list('id', 'title'))
    return dup_map, titles


def pick_top(pid, sims_row, all_ids, id_to_idx, dup_map, titles):
    """Топ-5 кандидатов с фильтрами: не сам, не пара дубль↔оригинал,
    не посимвольно совпадающий заголовок."""
    self_idx = id_to_idx.get(pid)
    if self_idx is not None:
        sims_row[self_idx] = -1.0
    pool = min(POOL_N, len(sims_row))
    cand_idx = np.argpartition(sims_row, -pool)[-pool:]
    cand_idx = cand_idx[np.argsort(sims_row[cand_idx])[::-1]]
    my_title = titles.get(pid)
    my_dup = dup_map.get(pid)
    out = []
    for i in cand_idx:
        cid = all_ids[i]
        if cid == pid:
            continue
        if my_dup == cid or dup_map.get(cid) == pid:
            continue
        if my_title and titles.get(cid) == my_title:
            continue
        out.append(cid)
        if len(out) == TOP_N:
            break
    return out


def cosine_similarity_batch(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Косинусное сходство query_vec (dim,) с каждой строкой matrix (N, dim)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    normed = matrix / norms
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0:
        q_norm = 1e-9
    return normed @ (query_vec / q_norm)


class Command(BaseCommand):
    help = 'Кеширует топ-5 похожих задач для каждой опубликованной задачи (Этап Б3)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Обработать первые N задач без кеша (по умолчанию — все).',
        )
        parser.add_argument(
            '--reset', action='store_true',
            help='Пересчитать все задачи, даже если кеш уже есть.',
        )
        parser.add_argument(
            '--rebuild', action='store_true',
            help='Полная быстрая пересборка кэша: очистить таблицу связей '
                 'и записать заново bulk_create-ом.',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        reset = options['reset']
        t0 = time.time()

        # Загружаем кандидатов: published БЕЗ флага качественного шлюза
        self.stdout.write('Загружаем эмбеддинги опубликованных задач (без флага шлюза)...')
        all_qs = (
            Problem.objects
            .filter(status=Problem.Status.PUBLISHED, embedding__isnull=False,
                    needs_quality_review=False)
            .only('id', 'embedding')
            .values_list('id', 'embedding')
        )

        all_ids = []
        all_vecs = []
        dim = None

        for pid, raw_emb in all_qs.iterator(chunk_size=LOAD_BATCH):
            raw = bytes(raw_emb)
            if dim is None:
                dim = len(raw) // 4
            if len(raw) != dim * 4:
                continue
            all_ids.append(pid)
            all_vecs.append(np.frombuffer(raw, dtype=np.float32).copy())

        if not all_ids:
            self.stdout.write(self.style.WARNING('Нет задач с эмбеддингами.'))
            return

        matrix = np.stack(all_vecs)  # (N, dim)
        # Нормируем матрицу один раз
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-9, norms)
        normed_matrix = matrix / norms

        id_to_idx = {pid: i for i, pid in enumerate(all_ids)}

        self.stdout.write(f'Матрица: {len(all_ids)} задач × {dim} dim')

        if options['rebuild']:
            self._full_rebuild(all_ids, id_to_idx, normed_matrix, t0)
            return

        # Определяем, какие задачи нужно обработать
        if reset:
            targets_qs = (
                Problem.objects
                .filter(status=Problem.Status.PUBLISHED, embedding__isnull=False)
                .only('id')
            )
        else:
            # Только задачи без кеша (annotate не поможет для M2M — проверяем через exclude)
            targets_qs = (
                Problem.objects
                .filter(status=Problem.Status.PUBLISHED, embedding__isnull=False)
                .filter(similar_problems__isnull=True)
                .only('id')
                .distinct()
            )

        target_ids = list(targets_qs.values_list('id', flat=True))
        if limit:
            target_ids = target_ids[:limit]

        total = len(target_ids)
        self.stdout.write(f'Задач для обработки: {total}')
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Кеш уже актуален.'))
            return

        dup_map, titles = load_exclusion_maps()
        processed = 0
        for pid in target_ids:
            if pid not in id_to_idx:
                continue  # задача есть в targets, но нет эмбеддинга в матрице

            idx = id_to_idx[pid]
            q = normed_matrix[idx]  # уже нормирован

            # Косинусное сходство со всеми
            sims = normed_matrix @ q  # (N,)
            top_pids = pick_top(pid, sims, all_ids, id_to_idx, dup_map, titles)

            # Сохраняем в M2M
            try:
                p = Problem.objects.get(pk=pid)
                if reset:
                    p.similar_problems.clear()
                p.similar_problems.set(top_pids)
            except Problem.DoesNotExist:
                continue

            processed += 1
            if processed % 500 == 0:
                elapsed = time.time() - t0
                self.stdout.write(
                    f'  Обработано {processed}/{total} '
                    f'({elapsed:.0f}с, {processed / elapsed:.0f} задач/с)'
                )

        elapsed = time.time() - t0
        self.stdout.write(self.style.SUCCESS(
            f'Готово: {processed} задач за {elapsed:.1f}с '
            f'({processed / elapsed:.0f} задач/с)'
        ))

    def _full_rebuild(self, all_ids, id_to_idx, normed_matrix, t0):
        """Полная пересборка: топ-5 для каждой published задачи с эмбеддингом,
        очистка таблицы связей и массовая запись (bulk_create)."""
        through = Problem.similar_problems.through

        # Цели — все published с эмбеддингом (включая зафлагованные шлюзом:
        # их кэш не виден, но пригодится, если флаг снимут)
        targets = list(
            Problem.objects
            .filter(status=Problem.Status.PUBLISHED, embedding__isnull=False)
            .values_list('id', 'embedding')
        )
        self.stdout.write(f'Целей: {len(targets)}; кандидатов: {len(all_ids)}')

        dim = normed_matrix.shape[1]
        dup_map, titles = load_exclusion_maps()
        rows = []
        processed = 0
        chunk_size = 1000
        for start in range(0, len(targets), chunk_size):
            chunk = targets[start:start + chunk_size]
            vecs, pids = [], []
            for pid, raw in chunk:
                v = np.frombuffer(bytes(raw), dtype=np.float32)
                if v.shape[0] != dim:
                    continue
                n = np.linalg.norm(v)
                vecs.append(v / (n if n else 1e-9))
                pids.append(pid)
            if not pids:
                continue
            sims = np.stack(vecs) @ normed_matrix.T  # (m, N)
            for row_i, pid in enumerate(pids):
                top_pids = pick_top(pid, sims[row_i], all_ids, id_to_idx,
                                    dup_map, titles)
                rows.extend(
                    through(from_problem_id=pid, to_problem_id=cid)
                    for cid in top_pids
                )
                processed += 1
            if processed % 5000 < chunk_size:
                self.stdout.write(
                    f'  посчитано {processed}/{len(targets)} ({time.time() - t0:.0f}с)')

        self.stdout.write(f'Записываем {len(rows)} связей...')
        with transaction.atomic():
            with connection.cursor() as cur:
                # Имя таблицы берётся из метаданных модели Django
                # (through._meta.db_table), а не из ввода: это константа,
                # заданная в models.py. Параметром имя таблицы передать
                # нельзя — драйвер подставляет только значения.
                cur.execute(f'DELETE FROM {through._meta.db_table}')  # nosec B608
            through.objects.bulk_create(rows, batch_size=10000)

        self.stdout.write(self.style.SUCCESS(
            f'Готово: кэш пересобран для {processed} задач за {time.time() - t0:.1f}с'))
