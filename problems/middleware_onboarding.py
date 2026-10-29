# -*- coding: utf-8 -*-
"""Шлюз онбординга (решения владельца 29.10.2026): без пройденной анкеты сайтом
пользоваться нельзя, куда бы человек ни пошёл. Старые аккаунты проходят её при
следующем входе.

Порядок экранов: сначала согласие на документы (`legal.middleware`), потом почта
для аккаунтов из VK ID / Яндекс ID (её спрашивает сам `/welcome/`), потом анкета.
Поэтому слой стоит СРАЗУ ПОСЛЕ слоя согласия: тот перехватывает раньше.

Срабатывает, только если всё сразу:
* `ONBOARDING_ENABLED`;
* человек вошёл и он не сотрудник;
* `profile.onboarded_at` пуст;
* запрос `GET`/`HEAD` и ждёт страницу (скрипты и POST пропускаются — иначе
  сломались бы формы и API);
* адрес не из белого списка.

⚠️ ЗАПРОСА К БАЗЕ НА КАЖДОЙ СТРАНИЦЕ НЕТ: признак «пройдено» кладётся в сессию,
как у экрана согласия. База спрашивается, пока признака нет.
"""
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect

from legal.middleware import is_script_request
from problems.models_platform import UserProfile

WELCOME_URL = '/welcome/'
SESSION_KEY = 'onboarded'

#: Что шлюз не трогает никогда: сама анкета и вход через сервисы, выход,
#: документы и экран согласия, страница «Почта», пароль, файлы, админка и
#: служебные адреса (как у слоя согласия).
EXEMPT_PREFIXES = (
    WELCOME_URL,
    '/auth/',
    '/logout/',
    '/legal/',
    '/account/email/',
    '/password/',
    '/static/',
    '/media/',
    '/admin/',
    '/healthz/',
    '/health/',
    '/api/track/',
    '/csp-report/',
    '/robots.txt',
    '/sitemap.xml',
)


def is_exempt(path):
    static_url = getattr(settings, 'STATIC_URL', '') or '/static/'
    return path.startswith(EXEMPT_PREFIXES) or path.startswith(static_url)


class OnboardingGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._must_onboard(request):
            return redirect('%s?next=%s' % (
                WELCOME_URL, quote(request.get_full_path(), safe='/')))
        return self.get_response(request)

    @staticmethod
    def _must_onboard(request):
        if not getattr(settings, 'ONBOARDING_ENABLED', False):
            return False
        if request.method not in ('GET', 'HEAD') or is_exempt(request.path_info):
            return False
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated or user.is_staff:
            return False
        if is_script_request(request) or request.session.get(SESSION_KEY):
            return False
        onboarded = (UserProfile.objects.filter(user=user)
                     .values_list('onboarded_at', flat=True).first())
        if onboarded is not None:
            request.session[SESSION_KEY] = True
            return False
        return True
