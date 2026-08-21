"""
catalog/semantic.py — модуль семантического поиска задач.

Стадия 1: локальный прототип без HyDE.
- Использует уже посчитанные эмбеддинги Problem.embedding.
- Модель и индекс грузятся лениво при первом запросе и живут в памяти.
- Никаких внешних API, никаких новых моделей, никаких миграций.
"""

import logging
import uuid
from typing import Optional

import numpy as np

from django.core.cache import cache

from problems.embedding_config import EMBEDDING_MODEL_NAME, EMBEDDING_DIM

logger = logging.getLogger(__name__)

# Имя модели и размерность берём из единого источника истины (problems/embedding_config.py).
_MODEL_NAME = EMBEDDING_MODEL_NAME
_EMBEDDING_DIM = EMBEDDING_DIM

# Ленивые синглтоны — инициализируются при первом вызове get_model()/get_index().
_model = None
_index = None   # словарь: {'matrix': ndarray (N, dim), 'ids': list[int], 'is_test_flags': list[bool]}

# ─── Версия индекса: общая на все процессы ───────────────────────────────
#
# ⚠️ ЗАЧЕМ ЭТО НУЖНО. `_index` живёт в памяти ОДНОГО процесса. Пока сайт
# работал в один процесс, `invalidate_index()` было достаточно: сбросил
# переменную — и всё. На боевом сервере воркеров девять, и запрос попадает
# в случайный. Сброс дошёл бы до того воркера, который обработал запрос,
# а остальные восемь продолжили бы отвечать по устаревшему индексу — и
# заметить это снаружи почти нельзя: поиск работает, просто выдаёт старое.
#
# Лечение: маркер версии в общем кэше (Redis). Перед выдачей индекса
# процесс сверяет свой маркер с общим и перестраивает индекс, если они
# разошлись. Цена — один `cache.get` на поисковый запрос.
_VERSION_KEY = 'semantic:index_version'
_index_version = None    # маркер, с которым построен _index в ЭТОМ процессе

# Ответ «кэш не работает» (DummyCache, кэш недоступен). В этом случае
# ведём себя ровно как раньше: один процесс, сверять не с кем.
_NO_CACHE = object()


class SemanticSearchDisabled(RuntimeError):
    """Смысловой поиск выключен настройкой. Это НЕ поломка.

    Отдельный класс, а не общий `RuntimeError`: вызывающая сторона обязана
    уметь отличить «выключено намеренно» от «сломалось» — в первом случае
    надо тихо перейти на поиск по словам и сказать об этом человеку,
    во втором — записать в журнал как ошибку.
    """


def is_enabled():
    """Включён ли смысловой поиск. Единственная точка правды на весь проект."""
    from django.conf import settings

    return getattr(settings, 'SEMANTIC_SEARCH_ENABLED', True)


def get_model():
    """Ленивая загрузка sentence-transformers модели.

    Первый вызов занимает ~6–7 секунд (загрузка с диска).
    Последующие — мгновенны (объект жив в памяти процесса).

    MPS исключён намеренно: BGE-M3 на Apple Silicon 8 ГБ вызывал зависание.
    CPU достаточно для кодирования одиночных поисковых запросов.
    """
    global _model
    # ⚠️ ПРОВЕРКА СТОИТ ДО import, И ЭТО ВЕСЬ ЕЁ СМЫСЛ. После импорта она
    # была бы бесполезна: 2,12 ГБ модели уже лежали бы в памяти процесса,
    # а на четырёх воркерах это 8,5 ГБ при 8 ГБ сервера. Стережёт тест,
    # который смотрит, не появился ли sentence_transformers в sys.modules.
    if not is_enabled():
        raise SemanticSearchDisabled(
            'Смысловой поиск выключен настройкой SEMANTIC_SEARCH_ENABLED. '
            'Модель не загружается: она весит 2,12 ГБ на каждый воркер.'
        )
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            try:
                import torch
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
            except ImportError:
                device = 'cpu'
            logger.info('Загружаем модель %s (device=%s)...', _MODEL_NAME, device)
            _model = SentenceTransformer(_MODEL_NAME, device=device)
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
            hidden_pending_review=False,
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


def _shared_version():
    """Общий маркер версии индекса. Отсутствие ключа = «перестроить».

    ⚠️ ГЛАВНАЯ ЛОВУШКА ЭТОГО МЕСТА. `cache.clear()` у Redis-бэкенда — это
    FLUSHDB: он уносит и сам ключ версии. Если после этого каждый процесс
    просто запишет одно и то же значение (скажем, «1»), то воркер, у
    которого локально уже лежала «1», решит, что ничего не изменилось,
    и останется со СТАРЫМ индексом — то есть ровно с той бедой, ради
    которой всё это заведено.
    Поэтому пропавший ключ восстанавливается СЛУЧАЙНЫМ маркером: он не
    совпадает ни с чьей локальной версией, и перестраиваются все.
    `cache.add`, а не `cache.set`, — чтобы при одновременном обращении
    нескольких воркеров выиграл первый, а не последний, и все сошлись
    на одном значении за один круг.

    Возвращает `_NO_CACHE`, если кэша нет вовсе: тогда сверять не с кем
    и поведение остаётся прежним, «один процесс».
    """
    version = cache.get(_VERSION_KEY)
    if version is not None:
        return version
    # timeout=None — «хранить вечно». На сервере у Redis политика
    # allkeys-lru, поэтому ключ всё же может быть вытеснен; это безопасно:
    # пропажа ключа означает лишний пересчёт индекса, но никогда — выдачу
    # устаревшего.
    cache.add(_VERSION_KEY, uuid.uuid4().hex, None)
    version = cache.get(_VERSION_KEY)
    if version is None:
        return _NO_CACHE
    return version


def get_index():
    """Возвращает закешированный индекс, строя его при первом вызове.

    Индекс считается устаревшим, если общий маркер версии разошёлся с тем,
    с которым индекс построен в этом процессе. Так сброс, сделанный в одном
    воркере, доходит до всех остальных.
    """
    global _index, _index_version
    version = _shared_version()
    if version is _NO_CACHE:
        # Кэша нет — сверять не с чем, работаем как один процесс.
        if _index is None:
            _index = _build_index()
        return _index
    if _index is None or _index_version != version:
        _index = _build_index()
        _index_version = version
    return _index


def invalidate_index():
    """Принудительно сбрасывает кэш индекса (например, после переимпорта).

    Сбрасывает и локальную копию, и общий маркер версии: без второго сброс
    остался бы внутри того процесса, который его выполнил.
    """
    global _index, _index_version
    _index = None
    _index_version = None
    cache.set(_VERSION_KEY, uuid.uuid4().hex, None)


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
