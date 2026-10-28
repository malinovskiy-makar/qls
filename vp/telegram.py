"""Единственное место, откуда сайт ходит в Telegram (стена 2 тура, docs/VP.md).

⚠️ ТОКЕН БОТА НЕ ПОПАДАЕТ НИ В ЛОГ, НИ В ТЕКСТ ИСКЛЮЧЕНИЯ. Адрес запроса содержит
его целиком, поэтому адрес не логируется никогда, исключения urllib не
пробрасываются наружу (их текст и цепочка могут нести адрес), а описание ошибки
от Telegram на всякий случай чистится от токена.

⚠️ НОВЫХ ПАКЕТОВ НЕТ: `urllib.request`, как в `catalog/search_client.py`.
`TELEGRAM_API_BASE` — только `https://`: иначе `urlopen` открыл бы и `file://`.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

#: Статусы `getChatMember`, которые считаются подпиской.
MEMBER_STATUSES = ('creator', 'administrator', 'member')


class TelegramError(Exception):
    """Отказ Telegram. `kind`: 'network' | 'api' | 'config'. Токена в тексте нет."""

    def __init__(self, kind, description=''):
        self.kind = kind
        self.description = description
        super().__init__(f'{kind}: {description}' if description else kind)


def enabled():
    """Путь Telegram на стене включён: токен, имя бота и секрет вебхука заданы."""
    return bool(getattr(settings, 'VP_WALL_TG_ENABLED', True)
                and getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
                and getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
                and getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', ''))


def _scrub(text):
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    text = str(text or '')
    return text.replace(token, '***') if token else text


def call(method, *, timeout=8, **params):
    """POST JSON на `{TELEGRAM_API_BASE}/bot{token}/{method}`; результат `result`.

    Сеть или `ok=false` → `TelegramError`. Ни адрес, ни токен наружу не выходят.
    """
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    base = (getattr(settings, 'TELEGRAM_API_BASE', '') or '').rstrip('/')
    if not token:
        raise TelegramError('config', 'TELEGRAM_BOT_TOKEN не задан')
    if urllib.parse.urlsplit(base).scheme != 'https':
        raise TelegramError('config', 'TELEGRAM_API_BASE не https://')
    request = urllib.request.Request(
        f'{base}/bot{token}/{method}', data=json.dumps(params).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    data = None
    failure = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 — схема проверена выше: только https
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        # Telegram отвечает 4xx с телом {"ok": false, "description": …}.
        try:
            data = json.loads(error.read().decode('utf-8'))
        except (ValueError, OSError):
            failure = TelegramError('network', f'HTTP {error.code}')
    except (urllib.error.URLError, OSError, ValueError) as error:
        failure = TelegramError('network', type(error).__name__)
    # ⚠️ Вне блока except: цепочка исключений (`__context__`) несла бы адрес с токеном.
    if failure is not None:
        raise failure
    if not isinstance(data, dict) or not data.get('ok'):
        description = data.get('description', '') if isinstance(data, dict) else ''
        raise TelegramError('api', _scrub(description)[:200])
    return data.get('result')


def subscription(tg_user_id):
    """Подписан ли человек на `TELEGRAM_CHANNEL`: True / False / None (не вышло узнать).

    None — например, бот не администратор канала («member list is inaccessible»):
    тогда он не видит подписчиков. Причина — в `TelegramError` для `last_error`.
    """
    member = call('getChatMember', chat_id=settings.TELEGRAM_CHANNEL, user_id=int(tg_user_id))
    status = (member or {}).get('status')
    if status in MEMBER_STATUSES:
        return True
    if status == 'restricted':
        return bool(member.get('is_member'))
    return False


def check_subscription(tg_user_id):
    """`subscription` без исключений: (True | False | None, код ошибки или '')."""
    try:
        return subscription(tg_user_id), ''
    except TelegramError as error:
        logger.warning('Telegram: проверка подписки не удалась (%s)', error.kind)
        return None, error.kind
