"""
Команда build_embeddings — строит векторные эмбеддинги для задач.

Использует модель из problems.embedding_config.EMBEDDING_MODEL_NAME (сейчас BAAI/bge-m3).
Результат сохраняется в Problem.embedding как bytes (numpy float32).

Запуск:
    ./venv/bin/python manage.py build_embeddings
    ./venv/bin/python manage.py build_embeddings --limit 5000
    ./venv/bin/python manage.py build_embeddings --reset  # пересчитать все
"""

import time

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand

from problems.models import Problem
from problems.embedding_config import EMBEDDING_MODEL_NAME

# Псевдоним для обратной совместимости: night_embeddings.py импортирует MODEL_NAME отсюда.
MODEL_NAME = EMBEDDING_MODEL_NAME
BATCH_SIZE = 100


def problem_to_text(problem: Problem) -> str:
    """Строит текст для эмбеддинга: заголовок + условие + подпункты + темы + навыки.

    Порядок блоков:
      1. title (если есть)
      2. statement[:500]
      3. подпункты ProblemPart.statement (до 500 символов суммарно)
      4. «Темы: …» — канонические темы, исключая техническую тему «Тест»
      5. «Навыки: …» — навыки задачи

    Блоки 4 и 5 добавляются только если у задачи есть соответствующие объекты.
    Для задач без тем/навыков текст не изменится по структуре.

    ⚠️ Требует prefetch_related('parts', 'topics', 'skills') при батч-запросе.
    """
    parts = []
    if problem.title:
        parts.append(problem.title + '.')
    parts.append(problem.statement[:500])

    # Подпункты
    subparts = list(problem.parts.all())  # Meta.ordering = ['order', 'label']
    if subparts:
        subtext = ' '.join(sp.statement for sp in subparts if sp.statement)
        if subtext:
            parts.append(subtext[:500])

    # Темы (исключаем «Тест» — техническая метка импорта, не смысловая)
    topic_names = [t.name for t in problem.topics.all() if t.name != 'Тест']
    if topic_names:
        parts.append('Темы: ' + ', '.join(topic_names) + '.')

    # Навыки
    skill_names = [s.name for s in problem.skills.all()]
    if skill_names:
        parts.append('Навыки: ' + ', '.join(skill_names) + '.')

    return ' '.join(parts)


class Command(BaseCommand):
    help = 'Строит векторные эмбеддинги для задач (Этап 5а)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Ограничить количество задач (по умолчанию — все без эмбеддинга).'
        )
        parser.add_argument(
            '--reset', action='store_true',
            help='Пересчитать эмбеддинги даже для задач, у которых они уже есть.'
        )

    def handle(self, *args, **options):
        if not getattr(settings, 'LOAD_EMBEDDINGS_MODEL', True):
            self.stderr.write('LOAD_EMBEDDINGS_MODEL=False — команда отключена на продакшене.')
            return

        from sentence_transformers import SentenceTransformer

        limit = options['limit']
        reset = options['reset']

        self.stdout.write('Загружаем модель...')
        t0 = time.time()
        model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        self.stdout.write(f'Модель загружена за {time.time() - t0:.1f}с')

        qs = Problem.objects.all()
        if not reset:
            qs = qs.filter(embedding__isnull=True)
        qs = qs.only('id', 'title', 'statement')

        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f'Задач для обработки: {total}')

        if total == 0:
            self.stdout.write('Нет задач без эмбеддинга. Готово.')
            return

        built = 0
        t_start = time.time()

        # Обрабатываем батчами
        ids = list(qs.values_list('id', flat=True))

        for batch_start in range(0, len(ids), BATCH_SIZE):
            batch_ids = ids[batch_start:batch_start + BATCH_SIZE]
            problems = list(
                Problem.objects
                .filter(id__in=batch_ids)
                .only('id', 'title', 'statement')
                .prefetch_related('parts', 'topics', 'skills')
            )

            texts = [problem_to_text(p) for p in problems]
            # encode() возвращает numpy array shape (N, dim)
            embeddings = model.encode(texts, show_progress_bar=False, batch_size=BATCH_SIZE)

            updates = []
            for p, emb in zip(problems, embeddings):
                p.embedding = emb.astype(np.float32).tobytes()
                updates.append(p)

            Problem.objects.bulk_update(updates, ['embedding'])
            built += len(updates)

            if built % 500 == 0 or built == total:
                elapsed = time.time() - t_start
                speed = built / elapsed if elapsed > 0 else 0
                self.stdout.write(
                    f'  {built}/{total} ({speed:.0f} задач/с, '
                    f'{elapsed:.0f}с прошло)'
                )

        elapsed = time.time() - t_start
        self.stdout.write(
            self.style.SUCCESS(
                f'Готово: построено {built} эмбеддингов за {elapsed:.1f}с '
                f'({built / elapsed:.0f} задач/с)'
            )
        )
