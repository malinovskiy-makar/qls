"""
catalog/semantic.py — модуль семантического поиска задач.

Стадия 1: локальный прототип без HyDE.
- Использует уже посчитанные эмбеддинги Problem.embedding.
- Модель и индекс грузятся лениво при первом запросе и живут в памяти.
- Никаких внешних API, никаких новых моделей, никаких миграций.
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Имя модели — совпадает с build_embeddings.py (важно для совместимости).
_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

# Размер вектора для данной модели.
_EMBEDDING_DIM = 384

# Ленивые синглтоны — инициализируются при первом вызове get_model()/get_index().
_model = None
_index = None   # словарь: {'matrix': ndarray (N, dim), 'ids': list[int], 'is_test_flags': list[bool]}


def get_model():
    """Ленивая загрузка sentence-transformers модели.

    Первый вызов занимает ~6–7 секунд (загрузка с диска).
    Последующие — мгновенны (объект жив в памяти процесса).
    """
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info('Загружаем модель %s...', _MODEL_NAME)
            _model = SentenceTransformer(_MODEL_NAME)
            logger.info('Модель загружена.')
        except ImportError:
            logger.error(
                'sentence_transformers не установлен. '
                'Установите: pip install sentence-transformers'
            )
            raise
    return _model


def _deserialize(blob) -> np.ndarray:
    """Десериализует BinaryField → numpy float32.

    BinaryField Django возвращает memoryview, а не bytes.
    bytes() обёртка обязательна — np.frombuffer(memoryview) падает.
    """
    return np.frombuffer(bytes(blob), dtype=np.float32)


def _build_index():
    """Строит индекс: матрица нормализованных эмбеддингов + список id.

    Включает только published-задачи без флага качества и с эмбеддингом.
    Нормализует строки сразу, чтобы косинус = скалярное произведение (быстрее).
    """
    from problems.models import Problem

    logger.info('Строим индекс эмбеддингов...')

    # Два источника признака «это тест»:
    # 1) problem_type начинается с «тест:» — проставлено при импорте;
    # 2) тема «Тест» — часть задач импортирована с пустым problem_type,
    #    но правильно размечена темой. Нормализация через problem_type отложена.
    topic_test_ids = set(
        Problem.objects
        .filter(topics__name='Тест')
        .values_list('id', flat=True)
    )

    qs = (
        Problem.objects
        .filter(
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
            embedding__isnull=False,
        )
        .only('id', 'embedding', 'problem_type')
        .values_list('id', 'embedding', 'problem_type')
    )

    ids = []
    vecs = []
    is_test_flags = []  # True если задача — тест (по problem_type ИЛИ теме «Тест»).

    for pid, raw_emb, ptype in qs.iterator(chunk_size=1000):
        raw = bytes(raw_emb)
        # Пропускаем задачи с повреждёнными эмбеддингами (неверный размер).
        if len(raw) != _EMBEDDING_DIM * 4:
            continue
        vec = np.frombuffer(raw, dtype=np.float32)
        ids.append(pid)
        vecs.append(vec)
        is_test = (ptype or '').lower().startswith('тест:') or (pid in topic_test_ids)
        is_test_flags.append(is_test)

    if not vecs:
        logger.warning('Индекс пуст — нет задач с эмбеддингами.')
        return {
            'matrix': np.empty((0, _EMBEDDING_DIM), dtype=np.float32),
            'ids': [],
            'is_test_flags': [],
        }

    matrix = np.stack(vecs)  # (N, dim)

    # Нормируем строки заранее: cos(a,b) = (a/|a|)·(b/|b|)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    matrix = matrix / norms

    logger.info('Индекс готов: %d задач.', len(ids))
    return {'matrix': matrix, 'ids': ids, 'is_test_flags': is_test_flags}


def get_index():
    """Возвращает закешированный индекс, строя его при первом вызове."""
    global _index
    if _index is None:
        _index = _build_index()
    return _index


def invalidate_index():
    """Принудительно сбрасывает кэш индекса (например, после переимпорта)."""
    global _index
    _index = None


def embed_query(text: str) -> np.ndarray:
    """Кодирует текстовый запрос в нормализованный вектор."""
    model = get_model()
    vec = model.encode([text], show_progress_bar=False)[0].astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0:
        norm = 1e-9
    return vec / norm


def search(query_text: str,
           topic_id: Optional[int] = None,
           difficulty: Optional[int] = None,
           has_solution: bool = False,
           content_kind: str = 'problems',
           limit: int = 20) -> list[dict]:
    """Семантический поиск по текстовому описанию.

    Параметры:
        query_text   — описание задачи произвольным текстом.
        topic_id     — id Topic для жёсткого фильтра (None = без фильтра).
        difficulty   — уровень сложности 1–5 (None = любой).
        has_solution — показывать только задачи с непустым решением.
        content_kind — 'problems' (по умолчанию, исключить тесты),
                       'tests' (только тесты), 'all' (без фильтра по типу).
        limit        — максимальное число результатов.

    Возвращает список словарей:
        [{'problem': Problem, 'score': float (0–1)}, ...]
    """
    from problems.models import Problem

    if not query_text or not query_text.strip():
        return []

    # Получаем вектор запроса и индекс.
    query_vec = embed_query(query_text.strip())
    idx = get_index()

    matrix = idx['matrix']
    ids = idx['ids']

    if matrix.shape[0] == 0:
        return []

    # Косинус = скалярное произведение (матрица уже нормализована, запрос тоже).
    scores = matrix @ query_vec  # (N,)

    # Берём топ с запасом для последующей фильтрации.
    top_k = min(limit * 10, len(ids))
    top_indices = np.argpartition(scores, -top_k)[-top_k:]
    top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

    # Фильтр по типу контента ('problems' — без тестов, 'tests' — только тесты, 'all' — всё).
    # is_test_flags учитывает оба источника: problem_type и тему «Тест».
    is_test_flags = idx['is_test_flags']
    if content_kind != 'all':
        is_test = (content_kind == 'tests')
        top_indices = [
            i for i in top_indices.tolist()
            if is_test_flags[i] == is_test
        ]

    top_ids_ordered = [ids[i] for i in top_indices]
    top_scores = {ids[i]: float(scores[i]) for i in top_indices}

    # Загружаем задачи одним запросом с нужными данными.
    qs = (
        Problem.objects
        .filter(pk__in=top_ids_ordered)
        .prefetch_related('topics', 'parts')
        .only('id', 'title', 'statement', 'difficulty', 'solution', 'status',
              'needs_quality_review')
    )

    # Жёсткие фильтры.
    if topic_id:
        qs = qs.filter(topics__id=topic_id)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    if has_solution:
        qs = qs.exclude(solution='').filter(solution__isnull=False)

    # Собираем результаты в исходном порядке (по убыванию score).
    problems_by_id = {p.pk: p for p in qs}

    results = []
    for pid in top_ids_ordered:
        if pid not in problems_by_id:
            continue
        results.append({
            'problem': problems_by_id[pid],
            'score': top_scores[pid],
        })
        if len(results) >= limit:
            break

    return results
