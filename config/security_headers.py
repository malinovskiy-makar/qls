# -*- coding: utf-8 -*-
"""Заголовки безопасности, которых у Django нет своей настройкой.

Что Django умеет сам и настроено в `settings_production.py`:
`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, флаги кук.
Здесь — два заголовка, для которых настройки нет:

* **`Permissions-Policy`** — какие возможности браузера странице разрешены.
  Проекту не нужна ни одна: ни камера, ни микрофон, ни геолокация, ни
  оплата. Отключаем всё явно.

* **`Content-Security-Policy-Report-Only`** — политика в режиме отчёта.

⚠️ **ПОЧЕМУ ИМЕННО РЕЖИМ ОТЧЁТА, А НЕ БОЕВОЙ.** Внешних источников у
политики больше нет — с 04.09.2026 все библиотеки браузера лежат в
`static/vendor/`, и `script-src`/`style-src`/`font-src` свелись к `'self'`.
Но разметка по-прежнему полна встроенных `<style>` и `<script>` — их в
проекте сотни, и держатся они на `'unsafe-inline'`. Боевая политика без
`'unsafe-inline'` отрезала бы их в первый же день, и «безопасность»
выглядела бы как сломанный сайт. Режим отчёта ничего не блокирует: браузер
выполняет страницу как обычно, но о каждом нарушении сообщает на
`/csp-report/`. Перевод в боевой режим — отдельная работа: вычистить
встроенные скрипты, а не расширить список источников.

Список источников намеренно **не** сделан «пошире, чтобы не шумело»:
политика в режиме отчёта тем и ценна, что шумит. Тихая политика в отчёте
не расскажет ничего, а в бою — не защитит.

⚠️ **ЕДИНСТВЕННЫЙ ЧУЖОЙ АДРЕС — ЯНДЕКС МЕТРИКА (ADR 0133), И ТОЛЬКО ПРИ
ЗАДАННОМ НОМЕРЕ СЧЁТЧИКА.** Без `YANDEX_METRIKA_ID` (локально, площадка
dev, тесты) политика прежняя, без единого чужого адреса.
"""
from django.conf import settings

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

# Внешних БИБЛИОТЕК у проекта НЕТ НИ ОДНОЙ. KaTeX, MathLive, D3, Math.js,
# Chart.js, FullCalendar и html2canvas лежат в `static/vendor/` и едут с
# нашего же адреса — решение владельца 04.09.2026 ради доступности сайта из
# России. Чужой адрес один — счётчик Метрики, и он ниже отдельным словарём:
# от него страница не зависит (тег грузится асинхронно).

CSP_DIRECTIVES = [
    "default-src 'self'",
    # 'unsafe-inline' — временно и честно: встроенных скриптов в проекте
    # сотни, и вычистить их — отдельная работа, а не побочный эффект.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    # Шрифты KaTeX и MathLive лежат рядом со своими библиотеками в
    # static/vendor/; data: нужен встроенным иконкам.
    "font-src 'self' data:",
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

# ─── Яндекс Метрика (ADR 0133) ──────────────────────────────────────────────
# Адреса сверены со справкой «Установка счетчика на сайт с CSP»
# (yandex.ru/support/metrica/ru/code/install-counter-csp, 26.09.2026):
# script-src — сам тег и его модули; img-src — картинка из noscript;
# connect-src — отправка данных; child-src и frame-src с `blob:` — «для
# правильной работы Вебвизора, карт кликов, ссылок и скроллинга».
#
# ⚠️ ИЗ ОБЩЕГО СПИСКА СПРАВКИ ВЗЯТ ТОЛЬКО mc.yandex.ru (+ yastatic.net у
# скриптов). Весь список — 41 адрес на каждую из пяти директив — это около
# 3 КБ заголовка на КАЖДОМ ответе. Вместе с кукой первого касания ответ
# перевалил бы за буфер заголовков nginx по умолчанию (4 КБ, `proxy_buffer_size`
# в конфиге не задан) — и посадочная страница отдала бы 502. Политика в
# режиме отчёта ничего не блокирует: не хватит адреса — придёт отчёт на
# /csp-report/, тогда и дописать его точечно.
#
# ⚠️ `frame-ancestors` НЕ ТРОНУТ. Справка просит пустить во фрейм кабинеты
# Метрики (для Вебвизора и карт), но фрейм запрещает `X-Frame-Options: DENY`
# (ADR 0013), а он, в отличие от этой политики, действует. Ослаблять его —
# решение владельца, а не побочный эффект счётчика.
METRIKA_SOURCES = {
    'script-src': 'https://mc.yandex.ru https://yastatic.net',
    'img-src': 'https://mc.yandex.ru',
    'connect-src': 'https://mc.yandex.ru',
    'frame-src': 'blob: https://mc.yandex.ru',
    'child-src': 'blob: https://mc.yandex.ru',
}


def _with_metrika(directives):
    """Политика с адресами Метрики: дописать их к своим директивам."""
    result, present = [], set()
    for directive in directives:
        name, _, sources = directive.partition(' ')
        present.add(name)
        extra = METRIKA_SOURCES.get(name)
        if extra is None:
            result.append(directive)
        elif sources == "'none'":
            # «никому» с адресами не сочетается — заменяем, а не дописываем.
            result.append('%s %s' % (name, extra))
        else:
            result.append('%s %s' % (directive, extra))
    # Директив, которых в своей политике нет (child-src), — перед report-uri.
    missing = ['%s %s' % (name, extra) for name, extra in METRIKA_SOURCES.items()
               if name not in present]
    return result[:-1] + missing + result[-1:]


CSP_REPORT_ONLY_METRIKA = '; '.join(_with_metrika(CSP_DIRECTIVES))


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
            response.setdefault(
                'Content-Security-Policy-Report-Only',
                CSP_REPORT_ONLY_METRIKA if settings.YANDEX_METRIKA_ID
                else CSP_REPORT_ONLY)
        return response
