# -*- coding: utf-8 -*-
u"""Маршруты ASGI игры: WebSocket дуэли и проверка живости процесса."""
from django.urls import path, re_path

from game import consumers

websocket_urlpatterns = [
    # Код набора — Crockford base32 без I, L, O, U (game/models.py).
    re_path(r'^ws/duel/(?P<code>[0-9A-Za-z]{4,16})/$',
            consumers.DuelConsumer.as_asgi()),
]


def http_application(django_app):
    u"""HTTP-часть ASGI: `/ws/health/` мимо Django, остальное в Django.

    ⚠️ ПРОВЕРКА ЖИВОСТИ НЕ ХОДИТ В DJANGO И В БАЗУ НАРОЧНО. Она отвечает на
    вопрос «жив ли ASGI-процесс», а не «жив ли сайт»: за второе отвечает
    обычная страница. Балансировщик, дёргающий ручку раз в секунду, не
    должен создавать нагрузку на базу.
    """
    from channels.routing import URLRouter

    return URLRouter([
        path('ws/health/', consumers.health),
        re_path(r'', django_app),
    ])
