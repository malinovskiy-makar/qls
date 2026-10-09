# -*- coding: utf-8 -*-
"""Экран согласия для сокетов (дуэль Wecon Rush).

Обычные страницы закрывает `legal.middleware.ConsentGateMiddleware`, но
WebSocket идёт мимо Django-middleware: у него свой стек Channels. Без этой
обёртки вошедший, не принявший документы, мог играть дуэль в обход экрана.

Отказ — закрытие до принятия соединения: браузер получит 403, как у любого
другого запрещённого сокета проекта.
"""
from channels.db import database_sync_to_async

from problems.models_legal import ConsentRecord

from . import consent

#: Код закрытия «согласие не принято». Свой, чтобы клиент отличал его от
#: прочих отказов; в диапазоне 4000–4999, отведённом приложениям.
CLOSE_CONSENT_REQUIRED = 4403


@database_sync_to_async
def _accepted(user):
    return consent.has_current(user, ConsentRecord.Kind.PD)


class ConsentSocketMiddleware:
    """ASGI-обёртка: вошедший без записи `pd` текущей редакции не подключается.

    Ставится ВНУТРИ `AuthMiddlewareStack` (нужен `scope['user']`). Гостей не
    касается: у сокета дуэли свой отказ для них.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'websocket' and consent.enforcement_enabled():
            user = scope.get('user')
            if user is not None and user.is_authenticated and not await _accepted(user):
                # Протокол ASGI: на `websocket.connect` отвечаем закрытием.
                await receive()
                await send({'type': 'websocket.close', 'code': CLOSE_CONSENT_REQUIRED})
                return
        return await self.inner(scope, receive, send)
