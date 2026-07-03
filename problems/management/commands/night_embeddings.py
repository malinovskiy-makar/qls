"""
Команда night_embeddings — пересчёт эмбеддингов (ночная сессия 2026-06-12).

Цели пересчёта:
  1) задачи вообще без эмбеддинга;
  2) задачи из файлов изменённых id (тексты правились в сессиях чистки
     ПОСЛЕ первоначального расчёта эмбеддингов — эмбеддинг устарел).

Устойчивость к обрыву: после каждого батча id дописываются в done-файл;
при повторном запуске уже обработанные id пропускаются.

Запуск:
    ./venv/bin/python manage.py night_embeddings \
        --ids-file reports/formula_cleanup/changed_ids.txt \
        --ids-file reports/quality_audit/changed_ids_B.txt \
        --ids-file reports/quality_audit/changed_ids_C.txt \
        --ids-file reports/quality_audit/changed_ids_D.txt
"""

import os
import time

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand

from problems.models import Problem
from problems.management.commands.build_embeddings import MODEL_NAME, problem_to_text

BATCH_SIZE = 100
LOG_EVERY = 500

DEFAULT_DONE = 'reports/night_session/embeddings_done_ids.txt'
DEFAULT_LOG = 'reports/night_session/embeddings_progress.log'


class Command(BaseCommand):
    help = 'Пересчёт эмбеддингов: без эмбеддинга + изменённые тексты (resume-safe)'

    def add_arguments(self, parser):
        parser.add_argument('--ids-file', action='append', default=[],
                            help='Файл со списком id изменённых задач (можно несколько раз).')
        parser.add_argument('--done-file', default=DEFAULT_DONE,
                            help='Файл с уже обработанными id (для продолжения после обрыва).')
        parser.add_argument('--log-file', default=DEFAULT_LOG,
                            help='Файл прогресс-лога.')
        parser.add_argument('--limit', type=int, default=None)

    def log(self, log_file, msg):
        line = f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}'
        self.stdout.write(line)
        with open(log_file, 'a') as fh:
            fh.write(line + '\n')

    def handle(self, *args, **options):
        if not getattr(settings, 'LOAD_EMBEDDINGS_MODEL', True):
            self.stderr.write('LOAD_EMBEDDINGS_MODEL=False — команда отключена на продакшене.')
            return

        from sentence_transformers import SentenceTransformer

        done_file = options['done_file']
        log_file = options['log_file']
        os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)

        # 1. Целевой набор
        missing = set(Problem.objects.filter(embedding__isnull=True)
                      .values_list('id', flat=True))
        changed = set()
        for path in options['ids_file']:
            if not os.path.exists(path):
                self.stdout.write(self.style.WARNING(f'Нет файла: {path}'))
                continue
            with open(path) as fh:
                changed |= {int(s) for s in (line.strip() for line in fh) if s.isdigit()}
        # только существующие в базе
        changed = set(Problem.objects.filter(id__in=changed).values_list('id', flat=True))

        targets = missing | changed

        # 2. Resume: пропускаем уже сделанное в этой сессии
        done = set()
        if os.path.exists(done_file):
            with open(done_file) as fh:
                done = {int(s) for s in (line.strip() for line in fh) if s.isdigit()}
        # для задач «без эмбеддинга» дополнительная страховка: если эмбеддинг
        # уже появился и задача не из изменённых — пересчитывать не нужно
        remaining = sorted(targets - done)

        if options['limit']:
            remaining = remaining[:options['limit']]

        self.log(log_file,
                 f'Цели: без эмбеддинга {len(missing)}, изменённых {len(changed)}, '
                 f'объединение {len(targets)}, уже сделано {len(done)}, '
                 f'осталось {len(remaining)}')

        if not remaining:
            self.log(log_file, 'Всё уже пересчитано. Готово.')
            return

        self.log(log_file, 'Загружаем модель...')
        t0 = time.time()
        model = SentenceTransformer(MODEL_NAME)
        self.log(log_file, f'Модель загружена за {time.time() - t0:.1f}с')

        built = 0
        t_start = time.time()
        for batch_start in range(0, len(remaining), BATCH_SIZE):
            batch_ids = remaining[batch_start:batch_start + BATCH_SIZE]
            problems = list(
                Problem.objects.filter(id__in=batch_ids)
                .only('id', 'title', 'statement', 'ai_blurb')
                .prefetch_related('parts', 'topics', 'skills', 'tags')
            )
            texts = [problem_to_text(p) for p in problems]
            embeddings = model.encode(texts, show_progress_bar=False,
                                      batch_size=BATCH_SIZE)
            for p, emb in zip(problems, embeddings):
                p.embedding = emb.astype(np.float32).tobytes()
            Problem.objects.bulk_update(problems, ['embedding'])

            with open(done_file, 'a') as fh:
                fh.write('\n'.join(str(p.id) for p in problems) + '\n')

            built += len(problems)
            if built % LOG_EVERY < BATCH_SIZE:
                elapsed = time.time() - t_start
                speed = built / elapsed if elapsed > 0 else 0
                self.log(log_file,
                         f'  {built}/{len(remaining)} ({speed:.0f} задач/с)')

        elapsed = time.time() - t_start
        self.log(log_file, self.style.SUCCESS(
            f'Готово: пересчитано {built} эмбеддингов за {elapsed:.1f}с'))
