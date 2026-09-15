# -*- coding: utf-8 -*-
"""Прогрев воркера gunicorn: корпус умного поиска и смысловой индекс — ДО первого поиска.

⚠️ ЗАЧЕМ. Корпус bm25 (`catalog.rerank.get_corpus`) и матрица векторов
(`catalog.semantic.get_index`) живут в памяти ПРОЦЕССА и строятся лениво — при
первом поиске в каждом воркере. gunicorn перезапускает воркер каждые ~1 000
запросов (`--max-requests`), и после переноса корпуса (5 090 → 14 070 задач)
холодный воркер платил сборкой прямо на запросе человека: «20+ с вместо 7».
Замер 15.09.2026 на 14 082 видимых задачах: корпус 22–26 с, индекс 3 с.

Зовётся в ФОНОВОМ ПОТОКЕ из `config/gunicorn_conf.py::post_worker_init`:
воркер сразу принимает запросы, а поиск, пришедший до конца сборки, ждёт её
под замком `get_corpus()`. Выключатель — `SMART_SEARCH_WARMUP` (по умолчанию
включён; в тестах gunicorn не поднимается).
"""
import logging
import time

logger = logging.getLogger(__name__)


def warm_worker(log=None):
    """Построить корпус и индекс. Возвращает замеры или None, если прогрев выключен.

    `log` — куда писать строку итога (у gunicorn — `worker.log.info`).

    ⚠️ НИКОГДА НЕ БРОСАЕТ ИСКЛЮЧЕНИЕ. Прогрев — ускорение, а не условие старта:
    упал — поиск построит всё сам при первом запросе, как до 15.09.2026.
    ⚠️ В КОНЦЕ ЗАКРЫВАЕТ СВОЁ СОЕДИНЕНИЕ С БАЗОЙ. Соединение Django живёт в
    потоке, а поток прогрева после сборки больше не нужен: закрыть его
    соединение, кроме него самого, некому, и PostgreSQL держал бы его до
    перезапуска воркера.
    """
    from django.conf import settings
    from django.db import connection

    if not getattr(settings, 'SMART_SEARCH_WARMUP', False):
        return None
    log = log or logger.info
    result = {'corpus': None, 'corpus_seconds': None,
              'index': None, 'index_seconds': None}
    try:
        from catalog import rerank, semantic

        started = time.perf_counter()
        _bm25_index, rows = rerank.get_corpus()
        result['corpus'] = len(rows)
        result['corpus_seconds'] = round(time.perf_counter() - started, 2)
        if semantic.is_enabled():
            started = time.perf_counter()
            index = semantic.get_index()
            result['index'] = len(index['ids'])
            result['index_seconds'] = round(time.perf_counter() - started, 2)
    except Exception:                                       # noqa: BLE001
        logger.warning('прогрев воркера не удался: поиск построит корпус сам '
                       'при первом запросе', exc_info=True)
        return result
    finally:
        connection.close()
    log(summary(result))
    return result


def summary(result):
    """Одна строка для журнала gunicorn."""
    corpus = 'корпус %s задач за %s с' % (result['corpus'], result['corpus_seconds'])
    if result['index'] is None:
        index = 'индекс не строился (смысловой поиск выключен)'
    else:
        index = 'индекс %s векторов за %s с' % (result['index'], result['index_seconds'])
    return 'прогрев: %s, %s' % (corpus, index)
