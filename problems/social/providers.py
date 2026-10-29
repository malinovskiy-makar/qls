# -*- coding: utf-8 -*-
"""Два сервиса входа: адрес авторизации, обмен кода и данные человека.

Каждый сервис отдаёт наружу один и тот же словарь:
`{uid, first_name, last_name, email, email_verified, birth_date, avatar_url}`.

⚠️ ТОКЕН ЖИВЁТ ТОЛЬКО ВНУТРИ `fetch_profile`. Он нужен ровно на один запрос
данных и дальше не уходит никуда: ни в словарь, ни в сессию, ни в базу, ни в
журнал (сторож — `problems/tests/test_social_login.py`, `zz_token_marker`).

⚠️ ДАТА РОЖДЕНИЯ ОТБРАСЫВАЕТСЯ ЗДЕСЬ ЖЕ, пока `SOCIAL_STORE_BIRTHDATE` выключен:
до ред. 3 документов её нельзя держать даже в сессии (решение 29.10.2026).

⚠️ Наружу ходим через `urllib.request`, как бот стены (`vp/telegram.py`):
`requests` в боевых зависимостях нет. Адреса сервисов зашиты константами и все
`https://` — схему из данных запроса `urlopen` не получает никогда.

Адреса и поля сверены 29.10.2026: Яндекс — с официальной документацией
(yandex.ru/dev/id/doc); VK ID — по описанию OAuth 2.1 в промпте и открытым
библиотекам (официальная страница id.vk.com не открылась загрузчику). Живой
вход проверяется после выдачи ключей (карточка Notion).
"""
import base64
import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date

from django.conf import settings

logger = logging.getLogger(__name__)

#: Ожидание ответа сервиса (промпт: 10 с).
HTTP_TIMEOUT = 10


class SocialError(Exception):
    """Сервис не ответил или ответил не то. Текст — для журнала, не для человека."""


def code_challenge(verifier):
    """PKCE S256: base64url(sha256(verifier)) без «=» на конце."""
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def _request(url, *, data=None, headers=None):
    """JSON от сервиса. Любой сбой сети или разбора — `SocialError`."""
    body = urllib.parse.urlencode(data).encode('utf-8') if data is not None else None
    request = urllib.request.Request(url, data=body, headers=dict(headers or {}))
    if body is not None:
        request.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # nosec B310 — адрес из констант модуля, только https
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        # Тело ответа об ошибке в журнал не пишем: в нём бывает эхо кода.
        raise SocialError('HTTP %s от %s' % (error.code, urllib.parse.urlsplit(url).netloc)) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise SocialError('%s: %s' % (urllib.parse.urlsplit(url).netloc,
                                      type(error).__name__)) from None
    if not isinstance(payload, dict):
        raise SocialError('ответ не объект')
    return payload


def _birth_date(raw, fmt):
    """Дата рождения или None. Неполная дата («0000-12-23» у Яндекса) — None."""
    if not raw or not settings.SOCIAL_STORE_BIRTHDATE:
        return None
    try:
        if fmt == 'dmy':
            day, month, year = (int(part) for part in str(raw).split('.'))
        else:
            year, month, day = (int(part) for part in str(raw).split('-'))
        return date(year, month, day).isoformat()
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class Provider:
    name: str                 # код в SocialAccount.provider и в адресе
    title: str                # «VK ID» / «Яндекс ID»
    authorize_url: str
    scope: str
    #: Почту сервиса считаем подтверждённой, если он отдал её как основную.
    #: Оба сервиса подтверждают адрес у себя; флаг — на случай, если это изменится.
    trust_email: bool
    client_id_setting: str
    client_secret_setting: str
    #: Право на дату рождения: просим его, только пока дату разрешено хранить.
    birthday_scope: str = ''

    @property
    def client_id(self):
        return getattr(settings, self.client_id_setting, '') or ''

    @property
    def client_secret(self):
        return getattr(settings, self.client_secret_setting, '') or ''

    @property
    def enabled(self):
        return bool(settings.SOCIAL_LOGIN_ENABLED and self.client_id)

    def request_scope(self):
        scopes = self.scope.split()
        if self.birthday_scope and settings.SOCIAL_STORE_BIRTHDATE:
            scopes.append(self.birthday_scope)
        return ' '.join(scopes)

    def authorize_redirect(self, redirect_uri, state, verifier):
        query = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'state': state,
            'code_challenge': code_challenge(verifier),
            'code_challenge_method': 'S256',
            'scope': self.request_scope(),
        }
        return self.authorize_url + '?' + urllib.parse.urlencode(query)

    def fetch_profile(self, params, verifier, redirect_uri, state):
        """Код из адреса возврата → единый словарь данных человека."""
        raise NotImplementedError


class VKProvider(Provider):
    TOKEN_URL = 'https://id.vk.com/oauth2/auth'
    USER_INFO_URL = 'https://id.vk.com/oauth2/user_info'

    def fetch_profile(self, params, verifier, redirect_uri, state):
        token = _request(self.TOKEN_URL, data={
            'grant_type': 'authorization_code',
            'code': params.get('code', ''),
            'code_verifier': verifier,
            'client_id': self.client_id,
            # VK ID возвращает device_id в адресе возврата и ждёт его при обмене.
            'device_id': params.get('device_id', ''),
            'redirect_uri': redirect_uri,
            'state': state,
        }).get('access_token')
        if not token:
            raise SocialError('VK ID: нет access_token')
        info = _request(self.USER_INFO_URL, data={
            'client_id': self.client_id, 'access_token': token}).get('user')
        if not isinstance(info, dict) or not info.get('user_id'):
            raise SocialError('VK ID: нет user_id')
        email = (info.get('email') or '').strip()
        return {
            'uid': str(info['user_id']),
            'first_name': (info.get('first_name') or '').strip(),
            'last_name': (info.get('last_name') or '').strip(),
            'email': email,
            'email_verified': bool(email) and self.trust_email,
            'birth_date': _birth_date(info.get('birthday'), 'dmy'),
            'avatar_url': (info.get('avatar') or '').strip(),
        }


class YandexProvider(Provider):
    TOKEN_URL = 'https://oauth.yandex.ru/token'
    USER_INFO_URL = 'https://login.yandex.ru/info?format=json'
    AVATAR_URL = 'https://avatars.yandex.net/get-yapic/%s/islands-200'

    def fetch_profile(self, params, verifier, redirect_uri, state):
        data = {
            'grant_type': 'authorization_code',
            'code': params.get('code', ''),
            'code_verifier': verifier,
            'client_id': self.client_id,
        }
        if self.client_secret:
            data['client_secret'] = self.client_secret
        token = _request(self.TOKEN_URL, data=data).get('access_token')
        if not token:
            raise SocialError('Яндекс ID: нет access_token')
        info = _request(self.USER_INFO_URL, headers={'Authorization': 'OAuth ' + token})
        if not info.get('id'):
            raise SocialError('Яндекс ID: нет id')
        email = (info.get('default_email') or '').strip()
        avatar_id = info.get('default_avatar_id')
        avatar = (self.AVATAR_URL % urllib.parse.quote(str(avatar_id), safe='')
                  if avatar_id and not info.get('is_avatar_empty') else '')
        return {
            'uid': str(info['id']),
            'first_name': (info.get('first_name') or '').strip(),
            'last_name': (info.get('last_name') or '').strip(),
            'email': email,
            'email_verified': bool(email) and self.trust_email,
            'birth_date': _birth_date(info.get('birthday'), 'ymd'),
            'avatar_url': avatar,
        }


# Телефон не запрашиваем ни у кого (решение 08.10.2026).
PROVIDERS = {
    'vk': VKProvider(
        name='vk', title='VK ID', authorize_url='https://id.vk.com/authorize',
        scope='vkid.personal_info email', trust_email=True,
        client_id_setting='VK_ID_CLIENT_ID', client_secret_setting='VK_ID_CLIENT_SECRET'),
    'yandex': YandexProvider(
        name='yandex', title='Яндекс ID', authorize_url='https://oauth.yandex.ru/authorize',
        scope='login:info login:email login:avatar', trust_email=True,
        client_id_setting='YANDEX_CLIENT_ID', client_secret_setting='YANDEX_CLIENT_SECRET',
        birthday_scope='login:birthday'),
}


def get(name):
    """Включённый сервис по коду или None."""
    provider = PROVIDERS.get(name)
    return provider if provider is not None and provider.enabled else None


def enabled():
    """Включённые сервисы в порядке кнопок: VK ID, Яндекс ID."""
    return [provider for provider in PROVIDERS.values() if provider.enabled]


# ── Аватар ─────────────────────────────────────────────────────────────────
#: Откуда разрешено скачивать аватар. Ссылка не отсюда — не скачиваем вовсе.
AVATAR_HOSTS = ('userapi.com', 'vk.com', 'vk.me', 'vkuserphoto.ru',
                'avatars.yandex.net', 'avatars.mds.yandex.net')
AVATAR_TIMEOUT = 5
AVATAR_MAX_BYTES = 3 * 1024 * 1024


def avatar_url_allowed(url):
    parts = urllib.parse.urlsplit(url or '')
    host = (parts.hostname or '').lower()
    return parts.scheme == 'https' and any(
        host == allowed or host.endswith('.' + allowed) for allowed in AVATAR_HOSTS)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Переадресация увела бы скачивание с разрешённого хоста на любой другой."""

    def redirect_request(self, *args, **kwargs):
        return None


def download_avatar(url):
    """Байты картинки или None. Любая ошибка — None, молча."""
    if not avatar_url_allowed(url):
        return None
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(url, timeout=AVATAR_TIMEOUT) as response:  # nosec B310 — https и хост из белого списка проверены выше
            body = response.read(AVATAR_MAX_BYTES + 1)
    except Exception:  # noqa: BLE001 — аватар по желанию, сбой не должен мешать входу
        return None
    if not body or len(body) > AVATAR_MAX_BYTES:
        return None
    return body
