# -*- coding: utf-8 -*-
"""Диагностика входа через Яндекс ID и VK ID (раунд 3, 29.10.2026).

    manage.py social_check                              # для боевого адреса
    manage.py social_check --base http://127.0.0.1:8010 # Яндекс на своём компьютере
    manage.py social_check --base http://localhost      # VK ID на своём компьютере

По каждому сервису печатает: включён ли флаг, задан ли ключ и похож ли он на
настоящий, какой адрес возврата сайт отправит для `--base`, что ответил адрес
авторизации с параметрами как у настоящей кнопки (код, конечный хост, признаки
ошибки), и итог одной строкой.

⚠️ НИ ОДИН КЛЮЧ В ВЫВОД НЕ ПОПАДАЕТ: только «задан, длина N». Тело ответа сервиса
целиком тоже не печатаем — только найденные признаки ошибки.

Что видно без входа в сервис (проверено 29.10.2026 запросами к обоим):
- **VK ID** проверяет приложение И адрес возврата сразу: с верными в странице
  есть название приложения, с чужим адресом — `"redirect_uri is missing or
  invalid"`, с выдуманным номером — `app is deleted`, с буквами — `client_id is
  missing`.
- **Яндекс** без входа уводит на паспорт и ничего не говорит о приложении. Поэтому
  есть второй запрос: обмен заведомо неверного кода. Известному приложению Яндекс
  отвечает `invalid_grant` («код устарел»), неизвестному — `invalid_client`.
  Адрес возврата Яндекс сверяет только после входа — его команда печатает, чтобы
  сверить с кабинетом глазами.
"""
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from problems.social import providers

TIMEOUT = 15
MAX_BODY = 1024 * 1024
DEFAULT_BASE = 'https://weconomics.ai'
#: Название приложения в кабинетах сервисов (docs/SOCIAL_KEYS.md).
APP_NAME = 'Weconomics'

#: Признаки ошибки в странице сервиса → что это значит простыми словами.
MARKERS = (
    ('invalid_client', 'сервис не знает приложение с этим ключом'),
    ('Неизвестное приложение', 'сервис не знает приложение с этим ключом'),
    ('client_id is missing', 'ключ не того вида (у VK ID — только цифры)'),
    ('app is deleted', 'приложения с таким номером нет или оно удалено'),
    ('redirect_uri is missing or invalid', 'адрес возврата не прописан в кабинете сервиса'),
)
#: Встроенная ошибка страницы VK ID: `"error":{"message":"…","code":"…"`.
EMBEDDED_ERROR = re.compile(r'"error":\{"message":"([^"]{1,200})","code":"([a-z_]{1,40})"')


def fetch(url, data=None, attempts=2):
    """(код, конечный адрес, тело) — сеть подменяется в тестах целиком.

    Один повтор при сбое связи: id.vk.ru с машины владельца изредка рвёт TLS на
    ровном месте (29.10.2026 — один запрос из пяти).
    """
    for attempt in range(attempts):
        try:
            return _fetch_once(url, data)
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == attempts - 1:
                raise
    raise AssertionError('недостижимо')


def _fetch_once(url, data):
    body = urllib.parse.urlencode(data).encode('utf-8') if data is not None else None
    request = urllib.request.Request(url, data=body, headers={'User-Agent': 'Mozilla/5.0 social_check'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # nosec B310 — адреса сервисов из констант, https
            return response.status, response.geturl(), response.read(MAX_BODY).decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        return error.code, error.geturl(), error.read(MAX_BODY).decode('utf-8', 'replace')


def _key_line(provider):
    value = provider.client_id.strip()
    if not value:
        return 'не задан', False
    if not provider.configured:
        return 'задан (длина %d), НЕ похож на настоящий' % len(value), False
    return 'задан (длина %d), похож на настоящий' % len(value), True


class Command(BaseCommand):
    help = 'Диагностика входа через Яндекс ID и VK ID: ключи, адрес возврата, ответ сервиса.'

    def add_arguments(self, parser):
        parser.add_argument('--base', default='',
                            help='адрес сайта, от которого строится адрес возврата '
                                 '(по умолчанию SOCIAL_REDIRECT_BASE или https://weconomics.ai)')

    def handle(self, base='', **options):
        base = (base or settings.SOCIAL_REDIRECT_BASE or DEFAULT_BASE).strip().rstrip('/')
        self.stdout.write('Адрес сайта: %s' % base)
        self.stdout.write('SOCIAL_LOGIN_ENABLED: %s' % ('включён' if settings.SOCIAL_LOGIN_ENABLED
                                                       else 'ВЫКЛЮЧЕН (кнопок на сайте не будет)'))
        verdicts = []
        for provider in providers.PROVIDERS.values():
            self.stdout.write('')
            verdicts.append(self._check(provider, base))
        self.stdout.write('')
        for line in verdicts:
            self.stdout.write(line)

    def _check(self, provider, base):
        title = provider.title.replace(' ID', '')
        out = self.stdout.write
        out('── %s' % provider.title)
        key_text, key_ok = _key_line(provider)
        out('ключ %s: %s' % (provider.client_id_setting, key_text))
        out('ключ %s: %s' % (provider.client_secret_setting,
                             'задан' if provider.client_secret else 'не задан'))
        redirect_uri = base + reverse('social_callback', args=[provider.name])
        out('адрес возврата: %s' % redirect_uri)
        if not key_ok:
            return '%s: ключ %s' % (title, 'не задан' if not provider.client_id.strip()
                                    else 'не похож на настоящий')

        problems = []
        if not settings.SOCIAL_LOGIN_ENABLED:
            problems.append('выключен флаг SOCIAL_LOGIN_ENABLED')
        if provider.name == 'vk':
            parts = urllib.parse.urlsplit(base)
            if parts.scheme == 'http' and parts.netloc != 'localhost':
                problems.append('VK ID на своём компьютере принимает только http://localhost '
                                '(порт 80)')
        if urllib.parse.urlsplit(base).scheme != 'https' and not base.startswith(
                ('http://localhost', 'http://127.0.0.1')):
            problems.append('на боевом сервере адрес обязан начинаться с https://')

        url = provider.authorize_redirect(redirect_uri, secrets.token_urlsafe(32),
                                          secrets.token_urlsafe(64))
        try:
            status, final, body = fetch(url)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            out('адрес авторизации: нет связи (%s)' % type(error).__name__)
            return '%s: не удалось связаться с сервисом (%s) — сеть или VPN' % (
                title, type(error).__name__)
        host = urllib.parse.urlsplit(final).netloc
        out('адрес авторизации: код %s, конечный хост %s' % (status, host))
        found = [meaning for marker, meaning in MARKERS if marker in body]
        embedded = EMBEDDED_ERROR.search(body)
        if embedded:
            out('ошибка в странице сервиса: %s (%s)' % (embedded.group(1), embedded.group(2)))
            if not found:
                found.append('сервис отказал: %s' % embedded.group(1))
        for meaning in dict.fromkeys(found):
            out('признак ошибки: %s' % meaning)
        problems.extend(dict.fromkeys(found))
        if status >= 400 and not found:
            problems.append('сервис ответил кодом %s' % status)

        if provider.name == 'vk' and not found and status < 400:
            if APP_NAME.lower() in body.lower():
                out('приложение узнано: в странице есть «%s»' % APP_NAME)
            else:
                out('название «%s» в странице не найдено' % APP_NAME)
        if provider.name == 'yandex':
            problems.extend(self._yandex_client(provider))

        if problems:
            return '%s: %s' % (title, '; '.join(problems))
        if provider.name == 'yandex':
            return ('%s: готов (адрес возврата Яндекс сверяет после входа — он должен '
                    'стоять в кабинете буква в букву)' % title)
        return '%s: готов' % title

    def _yandex_client(self, provider):
        """Обмен заведомо неверного кода: `invalid_grant` = приложение есть."""
        try:
            status, _final, body = fetch(providers.YandexProvider.TOKEN_URL, data={
                'grant_type': 'authorization_code', 'code': '0000000',
                'client_id': provider.client_id, 'code_verifier': 'x' * 43})
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self.stdout.write('проверка приложения: нет связи (%s)' % type(error).__name__)
            return ['не удалось проверить приложение (%s)' % type(error).__name__]
        try:
            error = json.loads(body).get('error', '')
        except (ValueError, AttributeError):
            error = ''
        self.stdout.write('проверка приложения (обмен неверного кода): код %s, %s'
                          % (status, error or 'без кода ошибки'))
        if error == 'invalid_client':
            return ['Яндекс не знает приложение с этим ClientID']
        if error == 'invalid_grant':
            return []
        return ['неожиданный ответ проверки приложения (%s)' % (error or status)]
