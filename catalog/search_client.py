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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
from django.conf import settings
from django.core.cache import caches

from problems.embedding_config import EMBEDDING_DIM, EMBEDDING_MODEL_BUILD

logger = logging.getLogger(__name__)

CACHE_ALIAS = 'search'
CACHE_TTL = 60 * 60 * 24 * 7      # неделя: вектор запроса не портится
_CACHE_PREFIX = 'qvec'

# Схемы, с которыми имеет смысл обращаться к своему HTTP-сервису.
_ALLOWED_SCHEMES = ('http', 'https')


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


def _breaker_seconds():
    """Сколько секунд не ходить к сервису после отказа (выключатель)."""
    return getattr(settings, 'SEARCH_SERVICE_BREAKER_SECONDS', 30.0)


# ─── Короткоживущий выключатель ───────────────────────────────────────────
#
# ⚠️ ЗАЧЕМ. У `urlopen` таймаут один на всё, и когда сервиса нет, КАЖДЫЙ
# поисковый запрос платит его целиком: человек, набравший запрос в
# каталоге, ждёт ровно столько, сколько ждал бы работающий поиск, и
# только потом получает выдачу по словам. А «нет сервиса» — это не авария
# на минуту: контейнер `search` на боевом сервере сегодня не поднят
# ВООБЩЕ, то есть недоступность там — нормальное состояние. Первый отказ
# закрывает дверь на `SEARCH_SERVICE_BREAKER_SECONDS`, и всё это время
# поиск уходит по словам МГНОВЕННО, без единого сетевого вызова.
#
# ⚠️ ОТДЕЛЬНОГО ТАЙМАУТА НА ДОЗВОН ЗДЕСЬ НЕТ, И ЭТО ПРОВЕРЕНО, А НЕ
# ЗАБЫТО. Замер 13.09.2026: `socket.create_connection` на заведомо
# нероутируемые адреса (10.255.255.1, 192.0.2.1, 198.51.100.7) на машине
# владельца возвращает УСПЕХ за миллисекунду — сетевой стек отвечает за
# несуществующего соседа. То есть проба дозвона в таком окружении не
# отличает живой сервис от мёртвого и стоила бы лишнего сокета на каждый
# запрос, ничего не давая. Выключатель работает при любом виде отказа —
# и при отказе в соединении, и при зависшем чтении.
#
# Состояние процессное, а не в общем кэше, и это намеренно: выключатель
# должен работать и когда Redis сам недоступен, иначе он спасает ровно в
# том случае, в котором чаще всего и не сработает. Цена — девять воркеров
# пробуют по разу вместо одного; это девять полусекунд на полминуты.
_breaker_lock = threading.Lock()
_breaker_until = 0.0
_breaker_reason = ''


def _breaker_check():
    """Закрыта ли дверь. Возвращает причину отказа или None."""
    with _breaker_lock:
        if _breaker_until > time.monotonic():
            return _breaker_reason
    return None


def _breaker_trip(reason):
    global _breaker_until, _breaker_reason
    seconds = _breaker_seconds()
    if seconds <= 0:
        return
    with _breaker_lock:
        _breaker_until = time.monotonic() + seconds
        _breaker_reason = reason


def reset_breaker():
    """Открыть дверь немедленно — для тестов и для ручной проверки."""
    global _breaker_until, _breaker_reason
    with _breaker_lock:
        _breaker_until = 0.0
        _breaker_reason = ''


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


def _checked_url(url):
    """Проверяет схему URL ДО того, как он уйдёт в `urlopen`.

    ⚠️ ЭТО НЕ КОСМЕТИКА ДЛЯ BANDIT (B310, CWE-22), А НАСТОЯЩАЯ ЗАЩИТА.
    `urlopen` умеет открывать не только http(s), но и `file://` — bandit не
    может статически доказать, что адрес всегда таков, и правильно
    сомневается. `SEARCH_SERVICE_URL` берётся из настроек (адрес соседнего
    контейнера, не пользовательский ввод), но если однажды его соберут
    неправильно — опечатка, битый `.env`, случайно оставшийся `file:///` —
    приложение обязано понятно упасть, а не молча прочитать локальный файл
    и отдать его содержимое как «вектор». Проверка стоит здесь, единственном
    месте файла, откуда вызывается `urlopen`, а не в комментарии рядом.
    """
    scheme = urllib.parse.urlsplit(url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise SearchServiceUnavailable(
            'SEARCH_SERVICE_URL указывает на недопустимую схему %r '
            '(разрешены только http и https) — проверьте настройки, '
            'адрес: %s' % (scheme, url))
    return url


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
    """Один POST /encode. Любая сетевая беда -> SearchServiceUnavailable.

    Сначала спрашивается выключатель (память процесса) — пока он закрыт,
    до сети дело не доходит вовсе.
    """
    closed = _breaker_check()
    if closed:
        raise SearchServiceUnavailable(closed)
    body = json.dumps({'texts': list(texts)}).encode('utf-8')
    url = _checked_url(service_url().rstrip('/') + '/encode')
    request = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:  # nosec B310 — схема проверена _checked_url выше
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise SearchServiceUnavailable(
            'сервис ответил %s' % exc.code) from exc
    except urllib.error.URLError as exc:
        _breaker_trip('нет связи с сервисом: %s' % exc.reason)
        raise SearchServiceUnavailable(
            'нет связи с сервисом: %s' % exc.reason) from exc
    except TimeoutError as exc:
        _breaker_trip('таймаут запроса')
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
    """Отвечает ли сервис. Модель не трогает (см. /healthz в сервисе).

    Выключатель здесь НЕ спрашивается и НЕ взводится: это проверка «ожил
    ли сосед», и отвечать на неё из памяти процесса означало бы никогда
    не заметить, что он ожил.
    """
    try:
        url = _checked_url(service_url().rstrip('/') + '/healthz')
        with urllib.request.urlopen(url, timeout=_timeout()) as response:  # nosec B310 — схема проверена _checked_url выше
            return json.loads(response.read().decode('utf-8')).get('ok') is True
    except Exception:
        return False
