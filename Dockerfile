# Боевой образ приложения.
#
# ⚠️ ГЛАВНОЕ ПРАВИЛО ЭТОГО ФАЙЛА: ставится requirements/base.txt И ТОЛЬКО ОН.
# В local.txt лежат sentence-transformers и torch — вместе они тянут около
# двух гигабайт (ADR 0002). Модель на прод не едет: она грузится в память
# КАЖДОГО воркера, и на 8 ГБ сервера четыре воркера её просто не переживут.
# Проверка отсутствия torch в собранном образе — в docs/SERVER.md, и её надо
# повторять при каждом изменении этого файла.
#
# Две ступени: в первой собираются колёса, во второй остаётся только
# результат. Так компилятор и заголовки не едут в боевой образ.

# ─── Ступень 1: сборка зависимостей ──────────────────────────────────────
FROM python:3.13-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libpq-dev и gcc нужны ТОЛЬКО здесь: psycopg[binary] приезжает колесом,
# но если колеса под платформу не окажется, сборка не должна падать молча.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements/base.txt ./base.txt
RUN pip wheel --wheel-dir /wheels -r base.txt


# ─── Ступень 2: боевой образ ─────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# PYTHONUNBUFFERED — иначе логи gunicorn копятся в буфере и в `docker logs`
# ничего не видно ровно тогда, когда это нужнее всего.
# PYTHONDONTWRITEBYTECODE — .pyc в контейнере не нужны, только мусор в слое.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings_production

# libpq5 — рантайм-часть драйвера PostgreSQL. Без -dev и без компилятора.
# curl нужен healthcheck-у контейнера.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# ⚠️ ПРИЛОЖЕНИЕ РАБОТАЕТ НЕ ОТ root. Пробой в веб-приложении не должен
# сразу давать полные права внутри контейнера.
RUN groupadd --system --gid 1001 weco \
    && useradd --system --uid 1001 --gid weco --create-home weco

COPY --from=build /wheels /wheels
COPY requirements/base.txt /tmp/base.txt
RUN pip install --no-index --find-links=/wheels -r /tmp/base.txt \
    && rm -rf /wheels /tmp/base.txt

WORKDIR /app
COPY --chown=weco:weco . /app

# ⚠️ САМ КАТАЛОГ /app ПРИНАДЛЕЖИТ root, И ЭТО ЛОВУШКА.
# `WORKDIR` создаёт его от root, а `COPY --chown` меняет владельца только
# у СОДЕРЖИМОГО. Пользователь weco не может создать внутри новый подкаталог,
# и `collectstatic` падает с `PermissionError: '/app/staticfiles'` — уже
# после успешных миграций, то есть контейнер умирает на последнем шаге.
# Поймано локальным запуском 2026-08-21 до всякого сервера.
# Каталоги заводим заранее: под них монтируются тома, и точки монтирования
# тоже должны принадлежать weco.
RUN mkdir -p /app/staticfiles /app/media && chown -R weco:weco /app

# ⚠️ collectstatic ЗДЕСЬ НЕ ЗАПУСКАЕТСЯ, И ЭТО НЕ ЗАБЫТО.
# Статика лежит в именованном томе, который монтируется при ЗАПУСКЕ.
# Монтирование перекрывает содержимое каталога в образе — собранная на
# этапе сборки статика была бы просто не видна, и сайт поехал бы без стилей.
# Поэтому collectstatic живёт в entrypoint. Подробности — docs/SERVER.md.

COPY --chown=weco:weco deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER weco

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
