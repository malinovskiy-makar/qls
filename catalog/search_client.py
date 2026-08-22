# -*- coding: utf-8 -*-
"""Клиент сервиса кодирования запросов (С4).

Django-воркеры НЕ грузят модель: они ходят по HTTP в отдельный процесс
`search` (см. `search_service/app.py`). Это снимает «мину №1» — 2,12 ГБ
модели в каждом из девяти воркеров.

⚠️ ЗАВИСИМОСТЕЙ НЕ ДОБАВЛЯЕТ НАМЕРЕННО. Запрос уходит через `urllib` из
стандартной библиотеки, а не через `requests`/`httpx`. Ради одного POST в
соседний контейнер не стоит тащить пакет в боевой образ: у проекта
`pip-audit` в CI и правило «ML на прод не едет» (ADR 0002), и чем меньше
там лишнего, тем меньше поводов для внепланового обновления.

⚠️ КЛЮЧ КЭША СОДЕРЖИТ СБОРКУ МОДЕЛИ. Без неё после смены модели мы
раздавали бы старые векторы запросов против нового корпуса — и косинус
поехал бы молча, без единой красной проверки.
"""
import base64
import hashlib
import json
import logging
import urllib.error
import urllib.request

import numpy as np
from django.conf import settings
from django.core.cache import caches

from problems.embedding_config import EMBEDDING_DIM, EMBEDDING_MODEL_BUILD

logger = logging.getLogger(__name__)

CACHE_ALIAS = 'search'
CACHE_TTL = 60 * 60 * 24 * 7      # неделя: вектор запроса не портится
_CACHE_PREFIX = 'qvec'


class SearchServiceUnavailable(RuntimeError):
    """Сервис поиска не ответил. Это НЕ повод для пятисотки.

    Отдельный класс, а не общий `RuntimeError`, по той же причине, что и
    `SemanticSearchDisabled` рядом: вызывающая сторона обязана отличать
    «сервис прилёг» от «в коде ошибка». Первое лечится переходом на поиск
    по словам и одной строкой в журнале, второе — обязано быть видно.
    """


def service_url():
    return getattr(settings, 'SEARCH_SERVICE_URL', 'http://search:8001')


def _timeout():
    return getattr(settings, 'SEARCH_SERVICE_TIMEOUT', 5.0)


def _cache():
    """Кэш векторов запроса. Отдельный алиас — отдельная база Redis (7).

    ⚠️ ПОЧЕМУ НЕ `default`. `cache.clear()` у Redis — это FLUSHDB, он
    вычищает базу целиком. Векторы запросов считаются моделью и стоят
    дорого; лежи они рядом с обычным кэшем, любой штатный сброс уносил бы
    их вместе с мелочью. По той же причине в проекте разведены кэш и
    сессии (ADR 0011).
    """
    try:
        return caches[CACHE_ALIAS]
    except Exception:
        return caches['default']


def _cache_key(text):
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]
    return '%s:%s:%s' % (_CACHE_PREFIX, EMBEDDING_MODEL_BUILD, digest)


def _decode_vector(payload):
    raw = base64.b64decode(payload)
    vector = np.frombuffer(raw, dtype=np.float32)
    if vector.shape[0] != EMBEDDING_DIM:
        raise SearchServiceUnavailable(
            'сервис вернул вектор длины %d вместо %d'
            % (vector.shape[0], EMBEDDING_DIM))
    return vector


def _post_encode(texts):
    """Один POST /encode. Любая сетевая беда -> SearchServiceUnavailable."""
    body = json.dumps({'texts': list(texts)}).encode('utf-8')
    request = urllib.request.Request(
        service_url().rstrip('/') + '/encode',
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise SearchServiceUnavailable(
            'сервис ответил %s' % exc.code) from exc
    except urllib.error.URLError as exc:
        raise SearchServiceUnavailable(
            'нет связи с сервисом: %s' % exc.reason) from exc
    except TimeoutError as exc:
        raise SearchServiceUnavailable('таймаут запроса') from exc
    except (ValueError, OSError) as exc:
        raise SearchServiceUnavailable(
            'непонятный ответ сервиса: %s' % exc) from exc

    vectors = payload.get('vectors')
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise SearchServiceUnavailable('сервис вернул не столько векторов')
    return [_decode_vector(v) for v in vectors]


def encode_one(text):
    """Вектор одного текста. СЫРОЙ выход модели, без нормализации.

    Нормализация живёт в `catalog/semantic.py` и делается одинаково для
    запроса и для корпуса — здесь её быть не должно, иначе вектор запроса
    пройдёт нормализацию дважды, а корпусный один раз.

    Повторный тот же текст берётся из Redis и до сервиса (а значит и до
    модели) не доходит вовсе.
    """
    key = _cache_key(text)
    cache = _cache()
    cached = cache.get(key)
    if cached is not None:
        return np.frombuffer(cached, dtype=np.float32)

    vector = _post_encode([text])[0]
    try:
        cache.set(key, vector.tobytes(), CACHE_TTL)
    except Exception:
        # Кэш прилёг — это не повод ронять поиск, вектор у нас уже есть.
        logger.warning('search: не удалось сохранить вектор запроса в кэш')
    return vector


def healthy():
    """Отвечает ли сервис. Модель не трогает (см. /healthz в сервисе)."""
    try:
        with urllib.request.urlopen(
                service_url().rstrip('/') + '/healthz',
                timeout=_timeout()) as response:
            return json.loads(response.read().decode('utf-8')).get('ok') is True
    except Exception:
        return False
