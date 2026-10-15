# -*- coding: utf-8 -*-
"""Блокирующий экран согласия (решение владельца 08.10.2026).

Вошедший пользователь без действующей записи `pd` ТЕКУЩЕЙ редакции документов
не может пользоваться сайтом, пока не примет их на `/legal/accept/`:

* обычная страница → перенаправление на экран согласия с возвратом на
  исходный адрес;
* запрос скрипта (JSON, fetch) → 403 с кодом `consent_required`, без
  перенаправления: скрипт не умеет показать экран, а перенаправление он
  принял бы за ответ;
* гостей экран не касается вовсе.

⚠️ ДОБАВЛЯЕТ ЛИ ПРОВЕРКА ЗАПРОС К БАЗЕ НА КАЖДОЙ СТРАНИЦЕ: нет. Признак
«принято» лежит в сессии вместе с номером редакции (`consent.SESSION_KEY`);
база спрашивается один раз, пока признака нет. Смена редакции документов
сбрасывает признак сама: номер в сессии перестаёт совпадать.

⚠️ Сотрудник на обычных страницах проходит экран как все. Не блокируется
только `/admin/`.
"""
from urllib.parse import quote

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

from problems.models_legal import ConsentRecord

from . import consent

ACCEPT_URL = '/legal/accept/'

#: Что экран не трогает никогда. Документы обязаны открываться всегда (иначе
#: не на что смотреть перед согласием), выйти можно без согласия, остальное
#: служебное: проверки живости, отчёты браузера, счётчик посещений, смена пароля.
EXEMPT_PREFIXES = (
    '/legal/',
    '/logout/',
    '/admin/',
    '/healthz/',
    '/health/',
    '/api/track/',
    '/password/change/',
    '/csp-report/',
    '/robots.txt',
    '/sitemap.xml',
)

CONSENT_REQUIRED_TEXT = 'Чтобы продолжить, примите правила обработки данных.'


def is_exempt(path):
    static_url = getattr(settings, 'STATIC_URL', '') or '/static/'
    return path.startswith(EXEMPT_PREFIXES) or path.startswith(static_url)


def is_script_request(request):
    """Запрос сделан скриптом страницы, а не переходом человека.

    Признаков несколько, потому что ни один не надёжен один: современные
    браузеры шлют `Sec-Fetch-Dest: empty` на fetch, старые скрипты проекта
    ставят `X-Requested-With`, а адреса API узнаются по `/api/`.
    """
    headers = request.headers
    if headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    if headers.get('Sec-Fetch-Dest') == 'empty':
        return True
    if 'application/json' in (request.content_type or ''):
        return True
    accept = headers.get('Accept', '')
    if 'application/json' in accept and 'text/html' not in accept:
        return True
    if '/api/' in request.path_info:
        return True
    # «Стол» подменяет панели запросом `?pane=1`.
    return bool(request.GET.get('pane'))


class ConsentGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not consent.enforcement_enabled() or is_exempt(request.path_info):
            return self.get_response(request)
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return self.get_response(request)
        version = consent.current_version()
        if request.session.get(consent.SESSION_KEY) == version:
            return self.get_response(request)
        if consent.has_current(user, ConsentRecord.Kind.PD):
            consent.remember_in_session(request)
            return self.get_response(request)
        if is_script_request(request):
            return JsonResponse(
                {'error': 'consent_required', 'message': CONSENT_REQUIRED_TEXT,
                 'accept_url': ACCEPT_URL}, status=403)
        target = ACCEPT_URL
        if request.method in ('GET', 'HEAD'):
            target = '%s?next=%s' % (ACCEPT_URL, quote(request.get_full_path(), safe=''))
        return redirect(target)
