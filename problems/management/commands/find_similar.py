"""
Команда find_similar — поиск похожих задач по косинусному сходству эмбеддингов.

Запуск:
    ./venv/bin/python manage.py find_similar --problem-id 42
    ./venv/bin/python manage.py find_similar --problem-id 42 --limit 5
"""

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from problems.models import Problem, SourceReference

LOAD_BATCH = 1000   # сколько эмбеддингов грузим в память за раз


def cosine_similarity_batch(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Косинусное сходство query_vec (dim,) с каждой строкой matrix (N, dim)."""
    # Нормируем строки матрицы
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    normed = matrix / norms
    # Нормируем запрос
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0:
        q_norm = 1e-9
    normed_q = query_vec / q_norm
    return normed @ normed_q


class Command(BaseCommand):
    help = 'Ищет похожие задачи по косинусному сходству эмбеддингов (Этап 5а)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--problem-id', type=int, required=True,
            help='ID задачи, для которой ищем похожие.'
        )
        parser.add_argument(
            '--limit', type=int, default=10,
            help='Сколько похожих задач вернуть (по умолчанию 10).'
        )

    def handle(self, *args, **options):
        problem_id = options['problem_id']
        limit = options['limit']

        # Загружаем запросную задачу
        try:
            query_problem = Problem.objects.get(pk=problem_id)
        except Problem.DoesNotExist:
            raise CommandError(f'Задача с id={problem_id} не найдена.')

        if not query_problem.embedding:
            raise CommandError(
                f'У задачи #{problem_id} нет эмбеддинга. '
                f'Сначала запустите: ./venv/bin/python manage.py build_embeddings'
            )

        query_vec = np.frombuffer(bytes(query_problem.embedding), dtype=np.float32)
        dim = query_vec.shape[0]

        self.stdout.write(f'Задача #{problem_id}: {str(query_problem)[:80]}')
        self.stdout.write(f'Ищем топ-{limit} похожих...\n')

        # Загружаем эмбеддинги всех остальных задач батчами
        # Накапливаем (id, similarity) пары
        results = []

        qs = (Problem.objects
              .exclude(pk=problem_id)
              .filter(embedding__isnull=False)
              .only('id', 'embedding')
              .values_list('id', 'embedding'))

        batch_ids = []
        batch_vecs = []

        for pid, raw_emb in qs.iterator(chunk_size=LOAD_BATCH):
            raw = bytes(raw_emb)
            if len(raw) != dim * 4:
                continue
            vec = np.frombuffer(raw, dtype=np.float32)
            batch_ids.append(pid)
            batch_vecs.append(vec)

            if len(batch_ids) >= LOAD_BATCH:
                matrix = np.stack(batch_vecs)
                sims = cosine_similarity_batch(query_vec, matrix)
                for pid_, sim in zip(batch_ids, sims):
                    results.append((pid_, float(sim)))
                batch_ids = []
                batch_vecs = []

        # Остаток
        if batch_ids:
            matrix = np.stack(batch_vecs)
            sims = cosine_similarity_batch(query_vec, matrix)
            for pid_, sim in zip(batch_ids, sims):
                results.append((pid_, float(sim)))

        if not results:
            self.stdout.write('Нет задач с эмбеддингами для сравнения.')
            return

        # Топ-N по убыванию сходства
        results.sort(key=lambda x: x[1], reverse=True)
        top = results[:limit]

        # Загружаем детали задач
        top_ids = [r[0] for r in top]
        sim_by_id = {r[0]: r[1] for r in top}

        problems = {
            p.pk: p for p in Problem.objects.filter(pk__in=top_ids)
                                             .prefetch_related('topics')
                                             .select_related('owner')
        }

        # Источники — берём первый SourceReference для каждой задачи
        sources = {}
        for sr in SourceReference.objects.filter(
            problem_id__in=top_ids
        ).select_related('source').order_by('problem_id'):
            if sr.problem_id not in sources:
                sources[sr.problem_id] = sr.source.name

        self.stdout.write(f'{"#":<6} {"Сходство":<10} {"ID":<8} {"Сложность":<10} '
                         f'{"Тема":<25} {"Источник":<30} Заголовок')
        self.stdout.write('-' * 120)

        for rank, (pid, sim) in enumerate(top, 1):
            p = problems.get(pid)
            if not p:
                continue
            topics_str = ', '.join(t.name for t in p.topics.all()[:2]) or '—'
            source_str = sources.get(pid, '—')
            diff = str(p.difficulty) if p.difficulty else '—'
            title = str(p)[:50]
            self.stdout.write(
                f'{rank:<6} {sim:<10.4f} {pid:<8} {diff:<10} '
                f'{topics_str[:24]:<25} {source_str[:29]:<30} {title}'
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Найдено {len(results)} задач с эмбеддингами, показаны топ-{limit}.'))
