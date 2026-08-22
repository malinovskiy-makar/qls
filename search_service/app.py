# -*- coding: utf-8 -*-
"""Сервис кодирования текста в векторы — ОТДЕЛЬНЫЙ процесс (С4).

Зачем он существует: модель BGE-M3 весит 2,12 ГБ, а gunicorn на боевом
сервере поднимает девять воркеров. Модель внутри Django означала бы девять
копий, то есть ~19 ГБ, — это «мина №1» из CLAUDE.md, из-за которой
смысловой поиск и держали выключенным флагом. Здесь модель живёт в ОДНОМ
процессе, а Django-воркеры только ходят по HTTP и модель не импортируют
вовсе.

⚠️ НАРУЖУ ЭТОТ СЕРВИС НЕ ВЫСТАВЛЯЕТСЯ. В docker-compose у него нет секции
`ports` — он доступен только по внутренней сети Docker, по имени `search`.
Публиковать порт нельзя: эндпоинт без авторизации, и любой желающий
получил бы бесплатный доступ к нашей GPU/CPU-молотилке.

⚠️ ОТВЕТ — СЫРОЙ ВЫХОД МОДЕЛИ, БЕЗ НОРМАЛИЗАЦИИ. В базе `Problem.embedding`
лежит тоже сырой вектор, а нормализация делается на стороне Django
(`catalog/semantic.py`: `_build_index` для корпуса, `embed_query` для
запроса). Если начать нормализовать здесь, вектор запроса и вектор корпуса
пройдут разное число нормализаций — косинус поедет молча, ни одна проверка
не покраснеет.

⚠️ ВЕКТОРЫ ЕДУТ BASE64, А НЕ СПИСКОМ ЧИСЕЛ JSON. Требование «побитово тот
же вектор» проще выполнить, чем доказать: JSON-число — это десятичная
запись, и хотя round-trip float32 -> float64 -> repr -> float64 -> float32
математически точен, он зависит от реализации сериализатора на обоих
концах. Base64 от сырых байтов float32 не зависит ни от чего и проверяется
глазами. Заодно ответ втрое компактнее.
"""
import base64
import logging
import os
import threading

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel, Field

logger = logging.getLogger('search_service')

# ⚠️ Имя модели и размерность НЕ дублируются строкой: они приходят из
# переменных окружения, которые compose проставляет из тех же значений,
# что и у Django. Единый источник правды — problems/embedding_config.py.
MODEL_NAME = os.environ.get('EMBEDDING_MODEL_NAME', 'BAAI/bge-m3')
EMBEDDING_DIM = int(os.environ.get('EMBEDDING_DIM', '1024'))
MODEL_BUILD = os.environ.get('EMBEDDING_MODEL_BUILD', 'bge-m3/st-fp32')

app = FastAPI(title='weconomics search service', docs_url=None, redoc_url=None)

# Ленивый синглтон: модель грузится при ПЕРВОМ кодировании, а не при старте.
# Так контейнер поднимается за секунды и отвечает на /healthz сразу — это
# важно и для healthcheck, и для проверки сетевой изоляции: она не должна
# ждать двух гигабайт.
_model = None
_model_lock = threading.Lock()


def get_model():
    """Модель. Первый вызов — долгий (загрузка с диска), дальше мгновенно.

    Блокировка нужна, потому что uvicorn обслуживает запросы конкурентно:
    без неё два одновременных первых запроса начали бы грузить по своей
    копии модели, и пиковая память удвоилась бы ровно на том сервере, ради
    экономии памяти на котором сервис и заведён.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info('Загружаем модель %s...', MODEL_NAME)
                _model = SentenceTransformer(MODEL_NAME, device='cpu')
                logger.info('Модель загружена.')
    return _model


class EncodeRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=64)


class EncodeResponse(BaseModel):
    # base64 от float32-буфера каждого вектора, порядок совпадает с texts
    vectors: list[str]
    dim: int
    model_build: str


@app.get('/healthz')
def healthz():
    """Живость процесса. Модель НЕ трогает намеренно.

    Если бы healthcheck дёргал модель, контейнер считался бы нездоровым
    первые минуты после старта (пока грузятся 2,12 ГБ) и docker compose
    перезапускал бы его по кругу, никогда не давая догрузиться.
    """
    return {'ok': True, 'model_loaded': _model is not None,
            'model_build': MODEL_BUILD}


@app.post('/encode', response_model=EncodeResponse)
def encode(request: EncodeRequest):
    """Кодирует тексты. Возвращает СЫРЫЕ векторы модели в base64."""
    model = get_model()
    vectors = model.encode(request.texts, show_progress_bar=False)
    encoded = []
    for vector in vectors:
        raw = np.asarray(vector, dtype=np.float32).tobytes()
        encoded.append(base64.b64encode(raw).decode('ascii'))
    return EncodeResponse(vectors=encoded, dim=EMBEDDING_DIM,
                          model_build=MODEL_BUILD)
