# Образ сервиса кодирования запросов (С4).
#
# ⚠️ ЭТО ЕДИНСТВЕННОЕ МЕСТО, КУДА ML-СТЕК ЕХАТЬ МОЖНО. В образ Django
# (корневой Dockerfile) torch и sentence-transformers не попадают никогда
# — там девять воркеров, и модель множилась бы на девять (ADR 0002,
# «мина №1»). Здесь процесс один, и модель одна.
#
# Образ получается тяжёлым (torch CPU — около гигабайта). Это осознанная
# цена: тяжесть заперта в одном контейнере, который не масштабируется.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # ⚠️ Кэш моделей вынесен в том (см. docker-compose). Без этого модель
    # на 2,12 ГБ качалась бы заново при каждой пересборке образа, а слой с
    # ней раздувал бы образ до неприличия.
    HF_HOME=/models

# curl — для healthcheck контейнера, больше ничего системного не нужно:
# torch и sentence-transformers приезжают колёсами.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Зависимости отдельным слоем: правка app.py не должна тянуть за собой
# переустановку гигабайта torch.
COPY search_service/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY search_service/app.py ./app.py

# Непривилегированный пользователь: сервису незачем быть root.
RUN groupadd --system --gid 1002 weco \
    && useradd --system --uid 1002 --gid weco --no-create-home weco \
    && mkdir -p /models && chown -R weco:weco /models /app
USER weco

EXPOSE 8001

# ⚠️ ОДИН ВОРКЕР, И ЭТО ВЕСЬ СМЫСЛ СЕРВИСА. Каждый воркер uvicorn — свой
# процесс со своей копией модели. Два воркера = 4,24 ГБ, то есть ровно та
# беда, от которой мы уходили. Нагрузка тут упирается в CPU кодирования,
# а не в число обработчиков.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
