# -*- coding: utf-8 -*-
"""Заголовки безопасности, которых у Django нет своей настройкой.

Что Django умеет сам и настроено в `settings_production.py`:
`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, флаги кук.
Здесь — два заголовка, для которых настройки нет:

* **`Permissions-Policy`** — какие возможности браузера странице разрешены.
  Проекту не нужна ни одна: ни камера, ни микрофон, ни геолокация, ни
  оплата. Отключаем всё явно.

* **`Content-Security-Policy-Report-Only`** — политика в режиме отчёта.

⚠️ **ПОЧЕМУ ИМЕННО РЕЖИМ ОТЧЁТА, А НЕ БОЕВОЙ.** Сегодня KaTeX грузится с
внешнего CDN (`cdn.jsdelivr.net`), а разметка полна встроенных `<style>` и
`<script>` — их в проекте сотни. Боевая политика отрезала бы часть из этого
в первый же день, и «безопасность» выглядела бы как сломанный сайт.
Режим отчёта ничего не блокирует: браузер выполняет страницу как обычно,
но о каждом нарушении сообщает на `/csp-report/`, и мы собираем настоящий
список того, что придётся починить. Перевод в боевой режим — отдельная
работа ПОСЛЕ самостоятельного размещения статики.

Список источников намеренно **не** сделан «пошире, чтобы не шумело»:
политика в режиме отчёта тем и ценна, что шумит. Тихая политика в отчёте
не расскажет ничего, а в бою — не защитит.
"""

# Ни одной возможности браузера проекту не нужно. Пустой список источников
# `()` означает «запрещено всем, включая саму страницу».
PERMISSIONS_POLICY = ', '.join([
    'accelerometer=()',
    'ambient-light-sensor=()',
    'autoplay=()',
    'camera=()',
    'display-capture=()',
    'encrypted-media=()',
    'fullscreen=(self)',      # печать работы и графики разворачивают окно
    'geolocation=()',
    'gyroscope=()',
    'magnetometer=()',
    'microphone=()',
    'midi=()',
    'payment=()',
    'publickey-credentials-get=()',
    'screen-wake-lock=()',
    'usb=()',
    'xr-spatial-tracking=()',
])

# Куда браузер шлёт отчёт о нарушении. Адрес заведён в config/urls.py.
CSP_REPORT_PATH = '/csp-report/'

# Внешние источники, которыми проект пользуется СЕГОДНЯ. Каждый — это
# зависимость от чужой инфраструктуры и обращение на зарубежный домен;
# они перечислены здесь поимённо, чтобы список было видно одним взглядом.
_CDN = 'https://cdn.jsdelivr.net'

CSP_DIRECTIVES = [
    "default-src 'self'",
    # 'unsafe-inline' — временно и честно: встроенных скриптов в проекте
    # сотни, и вычистить их — отдельная работа, а не побочный эффект.
    "script-src 'self' 'unsafe-inline' " + _CDN,
    "style-src 'self' 'unsafe-inline' " + _CDN,
    # Шрифты KaTeX едут с того же CDN; data: нужен встроенным иконкам.
    "font-src 'self' data: " + _CDN,
    "img-src 'self' data: blob:",
    # Никаких обращений к чужим API из браузера.
    "connect-src 'self'",
    # Ни один сторонний документ не встраивается и не встраивает нас.
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    # Формы отправляются только на наш же адрес: так подменённая разметка
    # не сможет увести введённый пароль на чужой сервер.
    "form-action 'self'",
    'report-uri ' + CSP_REPORT_PATH,
]

CSP_REPORT_ONLY = '; '.join(CSP_DIRECTIVES)


class SecurityHeadersMiddleware:
    """Проставляет `Permissions-Policy` и CSP в режиме отчёта.

    Заголовки ставятся на каждый ответ, включая страницы ошибок: страница
    500 — ровно то место, где чужой скрипт был бы всего опаснее.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # На сам отчёт политику не вешаем: браузер, получив нарушение на
        # странице отчёта, прислал бы отчёт о ней — и так по кругу.
        if request.path != CSP_REPORT_PATH:
            response.setdefault('Permissions-Policy', PERMISSIONS_POLICY)
            response.setdefault('Content-Security-Policy-Report-Only',
                                CSP_REPORT_ONLY)
        return response
