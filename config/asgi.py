"""
ASGI-точка входа.

⚠️ ЭТОТ ПРОЦЕСС ОБСЛУЖИВАЕТ ТОЛЬКО `/ws/`. HTTP остаётся за gunicorn: менять
боевой веб-сервер ради одной долгоживущей ручки незачем, а второй процесс с
тем же образом дешевле и откатывается отдельно (docs/SERVER.md, ADR 0062).
Обычные HTTP-запросы сюда всё же попадать могут — на этот случай `http`
маршрутизируется в тот же Django, чтобы процесс не выглядел сломанным.

⚠️ `django.setup()` ЧЕРЕЗ `get_asgi_application()` ЗОВЁТСЯ ПЕРВЫМ, до импорта
`game.routing`. Импортируй мы маршруты раньше — приложение потянуло бы модели
до готовности реестра приложений, и падало бы это только на боевом запуске,
не в тестах.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack           # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import (                # noqa: E402
    AllowedHostsOriginValidator)

from game import routing as game_routing                 # noqa: E402

application = ProtocolTypeRouter({
    'http': game_routing.http_application(django_asgi_app),
    # ⚠️ ПРОВЕРКА ORIGIN ОБЯЗАТЕЛЬНА. Без неё WebSocket открывается с любого
    # чужого сайта с куками игрока — это CSRF, только на сокете, и обычная
    # защита Django его не покрывает. `AllowedHostsOriginValidator` берёт
    # список из ALLOWED_HOSTS, то есть настраивать второй список не нужно.
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(game_routing.websocket_urlpatterns))),
})
