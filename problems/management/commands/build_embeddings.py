"""
Команда build_embeddings — строит векторные эмбеддинги для задач.

Использует модель из problems.embedding_config.EMBEDDING_MODEL_NAME (сейчас BAAI/bge-m3).
Результат сохраняется в Problem.embedding как bytes (numpy float32).

Запуск:
    ./venv/bin/python manage.py build_embeddings
    ./venv/bin/python manage.py build_embeddings --limit 5000
    ./venv/bin/python manage.py build_embeddings --reset            # пересчитать все
    ./venv/bin/python manage.py build_embeddings --stale            # пересчитать устаревшие (С5)
    ./venv/bin/python manage.py build_embeddings --device cpu       # форсировать CPU
    ./venv/bin/python manage.py build_embeddings --batch-size 8     # маленький батч (8 ГБ RAM)
"""

import hashlib
import time

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models.expressions import RawSQL
from django.utils import timezone

from problems.models import Problem
from problems.embedding_config import (
    ACTIVE_SPEC, EMBEDDING_MODEL_NAME, EMBEDDING_DIM, CANONICAL_TAG_NAMES,
    EMBEDDING_FORMULA_VERSION, EMBEDDING_MODEL_BUILD,
)
from problems.embedding_formula import PREFETCH, build_text

# Псевдоним для обратной совместимости: night_embeddings.py импортирует MODEL_NAME отсюда.
MODEL_NAME = EMBEDDING_MODEL_NAME
BATCH_SIZE = 100  # размер батча выборки из БД (не кодирования)

# Ожидаемый размер вектора в байтах для текущей модели (float32 × EMBEDDING_DIM)
EMBEDDING_BYTES = EMBEDDING_DIM * 4  # 4096 для BGE-M3 (1024 × 4)


def _select_device(preferred: str) -> str:
    """Выбирает устройство для вычислений: mps → cuda → cpu.

    ⚠️ ЯВНОЕ «cpu» ОТВЕЧАЕТ ДО ИМПОРТА torch, И ЭТО НЕ МИКРООПТИМИЗАЦИЯ.
    Раньше `import torch` стоял первым, и пока torch не был установлен,
    это сходило с рук: импорт падал в ImportError, и функция возвращала
    'cpu'. Как только torch появился (22.08, сессия С4), тот же импорт
    начал по-настоящему тянуть тяжёлый C-модуль — в том числе внутри
    тестового воркера, где он падает с «module functions cannot set
    METH_CLASS or METH_STATIC» и роняет тест, не имеющий к устройству
    никакого отношения. Спросили 'cpu' — отвечаем 'cpu', ничего не
    импортируя.
    """
    if preferred == 'cpu':
        return 'cpu'
    try:
        import torch
    except ImportError:
        return 'cpu'
    if preferred == 'mps':
        return 'mps' if torch.backends.mps.is_available() else 'cpu'
    # auto
    if torch.backends.mps.is_available():
        return 'mps'
    if torch.cuda.is_available():
        return 'cuda'
    return 'cpu'


def problem_to_text(problem: Problem) -> str:
    """Текст отпечатка по АКТИВНОЙ спецификации формулы.

    Реализация с 07.09.2026 одна — `problems.embedding_formula.build_text`;
    здесь остаётся тонкая обёртка, потому что имя `problem_to_text`
    вызывается из полутора десятков мест. Что именно собирается, решает
    `ACTIVE_SPEC` (сегодня — `v1`, и переключается она одной строкой в
    `embedding_config` после того, как замер назовёт победителя).

    Сегодняшняя `v1`: title + statement[:500] + подпункты (500 суммарно) +
    «Темы» + «Навыки» + ai_blurb[:400] + «Теги» по старому списку
    `CANONICAL_TAG_NAMES`. Решение и ответ в отпечаток не входят.

    ⚠️ Совпадение `build_text(p, SPECS['v1'])` с прежней реализацией —
    СИМВОЛ В СИМВОЛ, и это держит тест
    `problems/tests/test_embedding_formula.py::V1ByteForByteTests`. Без него
    сравнение v1 против v2 было бы сравнением v2 с новой опечаткой.

    ⚠️ Требует `prefetch_related(*PREFETCH)` при батч-запросе.
    """
    return build_text(problem, ACTIVE_SPEC)


def embedding_source_hash(text: str) -> str:
    """MD5 текста, который реально уходит в модель — ключ устаревания С5."""
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def is_stale(problem: Problem, text: str) -> bool:
    """Устарел ли вектор `problem`: версия формулы, сборка модели или сам
    текст (через хеш) разошлись с тем, что записано при последнем расчёте.

    Легаси-записи (посчитаны до С5, все три поля версии пустые/NULL) тоже
    считаются устаревшими — сравнение с текущими константами никогда не
    совпадёт с NULL/''. Это осознанно: для них провенанс неизвестен.
    """
    return (
        problem.embedding_version != EMBEDDING_FORMULA_VERSION
        or problem.embedding_model_build != EMBEDDING_MODEL_BUILD
        or problem.embedding_source_hash != embedding_source_hash(text)
    )


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
        parser.add_argument(
            '--stale', action='store_true',
            help='Пересчитать только устаревшие: изменился текст (по хешу) '
                 'или сменилась версия формулы/сборка модели (С5, вместо '
                 'файла embeddings_done_ids.txt). Проходит по всей базе — '
                 'на 31 000+ задач это отдельный по времени шаг ДО кодирования.'
        )
        parser.add_argument(
            '--device', choices=['auto', 'mps', 'cpu', 'cuda'], default='auto',
            help='Устройство вычислений: auto (MPS→CUDA→CPU), mps, cuda, cpu.'
        )
        parser.add_argument(
            '--batch-size', type=int, default=100,
            help='Батч кодирования модели (default 100; снижай до 8 на 8 ГБ RAM).'
        )

    def handle(self, *args, **options):
        if not getattr(settings, 'LOAD_EMBEDDINGS_MODEL', True):
            self.stderr.write('LOAD_EMBEDDINGS_MODEL=False — команда отключена на продакшене.')
            return

        from sentence_transformers import SentenceTransformer

        limit = options['limit']
        reset = options['reset']
        stale = options['stale']
        encode_batch = options['batch_size']

        if reset:
            ids = list(Problem.objects.values_list('id', flat=True))
        elif stale:
            # Нельзя чистым SQL: хеш зависит от problem_to_text (заголовок,
            # подпункты, темы, навыки, теги — не только statement), значит
            # проверяется в Python, полным проходом по базе.
            self.stdout.write('Ищем устаревшие эмбеддинги (полный проход по базе)...')
            ids = [
                p.id for p in (
                    Problem.objects
                    # ⚠️ `defer('embedding')`, а НЕ `only(...)` со списком
                    # полей: список пришлось бы держать в согласии с составом
                    # активной спецификации формулы, и при переключении на v2
                    # забытое поле обернулось бы тихим N+1 на 41 тысяче задач.
                    # Отложить надо ровно один тяжёлый блоб — 4 КБ на задачу.
                    .defer('embedding')
                    .prefetch_related(*PREFETCH)
                    .iterator(chunk_size=BATCH_SIZE)
                )
                if is_stale(p, problem_to_text(p))
            ]
        else:
            # Берём задачи без актуального вектора: NULL или старая размерность (не EMBEDDING_BYTES).
            # COALESCE(length(embedding), 0) → 0 для NULL, фактический размер для остальных.
            # Это позволяет досчитывать после смены модели, не трогая уже обновлённые векторы.
            qs = Problem.objects.annotate(
                emb_size=RawSQL("COALESCE(length(embedding), 0)", [])
            ).filter(emb_size__lt=EMBEDDING_BYTES)
            # Собираем id заранее — избегаем count() на sliced queryset
            ids = list(qs.values_list('id', flat=True))

        if limit:
            ids = ids[:limit]

        total = len(ids)
        self.stdout.write(f'Задач для обработки: {total}')

        if total == 0:
            self.stdout.write('Нет задач без эмбеддинга. Готово.')
            return

        device = _select_device(options['device'])
        self.stdout.write(f'Устройство: {device}  батч кодирования: {encode_batch}')

        self.stdout.write('Загружаем модель...')
        t0 = time.time()
        model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
        self.stdout.write(f'Модель загружена за {time.time() - t0:.1f}с')

        built = 0
        t_start = time.time()

        for batch_start in range(0, len(ids), BATCH_SIZE):
            batch_ids = ids[batch_start:batch_start + BATCH_SIZE]
            problems = list(
                Problem.objects
                .filter(id__in=batch_ids)
                .only('id', 'title', 'statement', 'ai_blurb')
                .prefetch_related(*PREFETCH)
            )

            texts = [problem_to_text(p) for p in problems]

            # encode() с откатом на CPU при ошибке MPS
            try:
                embeddings = model.encode(texts, show_progress_bar=False, batch_size=encode_batch)
            except RuntimeError as exc:
                if device == 'mps':
                    self.stderr.write(
                        f'MPS ошибка при encode: {exc}\n'
                        f'Откат на CPU — перезагружаем модель.'
                    )
                    device = 'cpu'
                    model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
                    embeddings = model.encode(texts, show_progress_bar=False, batch_size=encode_batch)
                else:
                    raise

            now = timezone.now()
            updates = []
            for p, emb, text in zip(problems, embeddings, texts):
                p.embedding = emb.astype(np.float32).tobytes()
                # С5: штампуем версию формулы, сборку модели и хеш РЕАЛЬНО
                # закодированного текста — этим build_embeddings --stale
                # потом узнаёт, что устарело, без внешнего файла.
                p.embedding_version = EMBEDDING_FORMULA_VERSION
                p.embedding_model_build = EMBEDDING_MODEL_BUILD
                p.embedding_source_hash = embedding_source_hash(text)
                p.embedding_built_at = now
                updates.append(p)

            Problem.objects.bulk_update(updates, [
                'embedding', 'embedding_version', 'embedding_model_build',
                'embedding_source_hash', 'embedding_built_at',
            ])
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
                f'({built / elapsed:.0f} задач/с) на устройстве {device}'
            )
        )
