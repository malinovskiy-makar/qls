# -*- coding: utf-8 -*-
"""Проверка живости приложения для healthcheck контейнера.

⚠️ НАРУЖУ ЭТОТ АДРЕС НЕ ВЫСТАВЛЯЕТСЯ. nginx проксирует наружу только то,
что нужно людям; `/healthz/` доступен изнутри сети Docker, где к нему ходит
healthcheck контейнера. Наружу он не нужен никому, а посторонним сообщает
лишнее — состояние внутренних служб.

⚠️ ПОЧЕМУ ПРОВЕРЯЮТСЯ БАЗА И REDIS, А НЕ ПРОСТО «ОТВЕТИЛ 200».
Проверка, которая отвечает 200 всегда, — это не проверка. Приложение может
подняться и отвечать на статику, потеряв базу: тогда контейнер считается
здоровым, а каждая страница отдаёт пятисотку. Оба хранилища обязательны:
без базы сайта нет вовсе, без Redis нет сессий и кэша.
"""
import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger('problems')


@require_safe
@never_cache
def healthz(request):
    """200, если живы база и Redis; 503, если нет.

    ⚠️ Текст ошибки наружу НЕ отдаётся: в сообщениях драйверов бывают адреса
    и имена пользователей. Наружу — только имя службы и слово «сломано»,
    подробности уходят в журнал контейнера.
    """
    беды = []

    try:
        with connection.cursor() as курсор:
            курсор.execute('SELECT 1')
    except Exception:
        логика = 'postgres'
        беды.append(логика)
        logger.exception('healthz: база недоступна')

    try:
        from django.core.cache import caches

        # ⚠️ Именно запись, а не только чтение. `get` несуществующего ключа
        # у части бэкендов возвращает None, не обращаясь к серверу вовсе, —
        # такая проверка зеленела бы при мёртвом Redis.
        caches['default'].set('healthz:проба', '1', 10)
        if caches['default'].get('healthz:проба') != '1':
            raise RuntimeError('кэш не вернул только что записанное значение')
    except Exception:
        беды.append('redis')
        logger.exception('healthz: кэш недоступен')

    if беды:
        return JsonResponse({'ok': False, 'broken': беды}, status=503)
    return JsonResponse({'ok': True})


def _redis_alive(alias):
    """Живой ли Redis-алиас `alias` — запись и чтение, не просто PING.

    ⚠️ Не берём голый PING через внутренний клиент бэкенда (`cache._cache`
    у `django.core.cache.backends.redis.RedisCache` — приватный атрибут,
    не документированный API). Пишем и читаем пробный ключ тем же способом,
    что и `healthz` выше: PING может ответить, а падать будет именно запись
    (не туда ACL, не тот пароль, диск полон) — соединение живое, а Redis для
    приложения нет.
    """
    from django.core.cache import caches

    try:
        caches[alias].set('health:проба', '1', 10)
        return caches[alias].get('health:проба') == '1'
    except Exception:
        logger.exception('health: Redis (%s) недоступен', alias)
        return False


@require_safe
@never_cache
def health(request):
    """Публичная проверка живости: PostgreSQL и обе базы Redis.

    В отличие от `healthz` выше (только для контейнерного healthcheck,
    наружу через nginx не выставлен) этот адрес открыт всем без авторизации —
    для внешнего мониторинга. Поэтому ответ по компонентам, но так же скуп на
    подробности: только имена служб и булевы флаги. Ни версии кода, ни номера
    миграции, ни текста ошибки — в них попадаются адреса и имена учёток
    (см. `healthz` выше), а версия и миграции — готовая карта уязвимостей для
    того, кто эту страницу отсканирует.
    """
    db_ok = True
    try:
        with connection.cursor() as курсор:
            курсор.execute('SELECT 1')
    except Exception:
        db_ok = False
        logger.exception('health: PostgreSQL недоступен')

    redis_default_ok = _redis_alive('default')
    redis_sessions_ok = _redis_alive('sessions')

    healthy = db_ok and redis_default_ok and redis_sessions_ok
    return JsonResponse({
        'status': 'ok' if healthy else 'error',
        'db': db_ok,
        'redis_default': redis_default_ok,
        'redis_sessions': redis_sessions_ok,
    }, status=200 if healthy else 503)
