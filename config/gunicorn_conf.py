# -*- coding: utf-8 -*-
"""Настройки gunicorn контейнера web — подключаются в deploy/entrypoint.sh (`-c`).

Флаги командной строки в entrypoint (воркеры, таймауты, --max-requests) остаются
там, где были: здесь только хуки, которые флагом не задать.
"""


def post_worker_init(worker):
    """Прогреть воркер до первого запроса (catalog/warmup.py).

    ⚠️ ВОРКЕР ЗАНЯТ ПРОГРЕВОМ ЦЕЛИКОМ, а арбитр gunicorn ждёт от него сигнала
    «жив» не дольше `--timeout` (60 с). Поэтому между шагами зовётся
    `worker.notify()`. Один шаг дольше 60 с воркер не переживёт — тогда прогрев
    выключается переменной SMART_SEARCH_WARMUP=0, и поиск строит корпус сам.
    ⚠️ При старте контейнера греются ВСЕ воркеры сразу: первые секунды после
    выкатки сайт отвечает медленно (healthcheck ждёт 120 с, это покрывает).
    """
    from catalog.warmup import warm_worker

    warm_worker(log=worker.log.info, notify=worker.notify)
