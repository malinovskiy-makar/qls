"""
Единая точка обращения к модели: `run(profile, ...)`.

Здесь и только здесь живут кэш, лимиты, учёт расхода и разбор ответа.
Продуктовый код (подбор домашки и всё, что появится следом) знает про
модель ровно одно слово — `run`.
"""
import hashlib
import json
import logging
import time
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import providers
from .prompts import PROFILES, system_blocks

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = 'anthropic'
DEFAULT_MODEL = 'claude-haiku-4-5'
# Цена за миллион токенов: (вход, выход). Держим таблицей, а не числами в
# расчёте: тариф меняется, и меняться он должен в одном месте.
# Тарифы на 30.08.2026, Sonnet 5 — до 31.08.2026 включительно (с 01.09.2026
# дорожает до $3/$15).
DEFAULT_PRICES = {
    'claude-haiku-4-5': (1.0, 5.0),
    'claude-sonnet-5': (2.0, 10.0),
}
# Записанный в кэш токен стоит на четверть дороже обычного, прочитанный из
# кэша — десятую часть. Отсюда и вся выгода.
CACHE_WRITE_MULTIPLIER = Decimal('1.25')
CACHE_READ_MULTIPLIER = Decimal('0.1')

DEFAULT_DAILY_LIMIT = 30
DEFAULT_CACHE_SECONDS = 900
DEFAULT_MAX_TOKENS = 2000


class AiUnavailable(Exception):
    """Модель недоступна или выключена. Текст уже человеческий.

    `kind` — вид отказа для экрана: `no_key` (доступ не настроен или ключ не
    принят), `limit` (кончилась суточная квота), `other` (всё прочее).
    Экран по нему выбирает совет; сам текст исключения идёт в журнал.
    """

    def __init__(self, message, kind='other'):
        super(AiUnavailable, self).__init__(message)
        self.kind = kind


class AiResult(object):
    """Что вернул слой: разобранные данные плюс честный счёт расхода."""

    def __init__(self, data, usage, cached=False):
        self.data = data
        self.usage = usage
        self.cached = cached


def _setting(name, default):
    return getattr(settings, name, default)


def available_profiles():
    return sorted(PROFILES)


def _provider():
    return providers.get_provider(_setting('AI_PROVIDER', DEFAULT_PROVIDER))


def is_available():
    """Можно ли обращаться к модели вообще."""
    try:
        return _provider().is_available()
    except KeyError:
        return False


def unavailable_reason():
    """Почему нельзя — человеческими словами, без слова «эксепшн»."""
    try:
        return _provider().unavailable_reason()
    except KeyError as error:
        return ('Работа с моделью настроена неверно: %s. Соберите домашку '
                'вручную.' % error.args[0])


def used_today(user):
    """Сколько обращений израсходовано сегодня.

    ⚠️ СЧИТАЮТСЯ ТОЛЬКО УДАЧНЫЕ (`ok=True`) — сессия 7, фаза 7.3. Раньше
    считались все строки расхода подряд, и репетитор видел «использовано 5
    из 30», не получив ни одного разбора: неверный ключ, лимит поставщика
    или таймаут съедали суточную квоту так же, как настоящая работа.
    Обращение, за которое ничего не пришло, — не расход.

    Неудачные строки из журнала НЕ убираем: они нужны, чтобы понять, что
    именно сломалось. Меняется только то, что считает лимит.
    """
    from problems.models import AiUsageLog

    start = timezone.localtime(timezone.now()).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return AiUsageLog.objects.filter(user=user, created_at__gte=start,
                                     ok=True).count()


def daily_limit():
    return _setting('AI_GENERATOR_DAILY_LIMIT', DEFAULT_DAILY_LIMIT)


def _cache_key(profile, model, user_text):
    """Ключ НАШЕГО кэша ответов — не путать с кэшем префикса у поставщика.

    Наш кэш экономит обращение целиком (одинаковый запрос в течение
    четверти часа), кэш поставщика — часть его стоимости.
    """
    payload = json.dumps([profile, model, user_text], ensure_ascii=False)
    return 'ai:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def run(profile, user_text, schema, user, max_tokens=None,
        cache_seconds=None, check_limit=True, model=None):
    """Выполнить задачу `profile` и вернуть разобранную структуру.

    `user_text` — ВСЁ переменное: описание, параметры, подсказки из банка.
    В системную часть ничего переменного не попадает никогда (см.
    `prompts.py`), иначе кэш префикса перестаёт срабатывать.

    `model` — необязательное переопределение модели для ЭТОГО обращения
    (например, сравнение вариантов из management-команды). По умолчанию —
    настройка `AI_MODEL` / `DEFAULT_MODEL`, как и раньше.
    """
    provider = _provider()
    if not provider.is_available():
        raise AiUnavailable(provider.unavailable_reason(), kind='no_key')

    user_text = (user_text or '').strip()
    if not user_text:
        raise AiUnavailable('Пустой запрос — разбирать нечего.')

    model = model or _setting('AI_MODEL', DEFAULT_MODEL)
    key = _cache_key(profile, model, user_text)
    hit = cache.get(key)
    if hit is not None:
        return AiResult(hit['data'], hit['usage'], cached=True)

    if check_limit and user is not None:
        limit = daily_limit()
        if used_today(user) >= limit:
            raise AiUnavailable(
                'На сегодня лимит обращений исчерпан (%d в сутки).' % limit,
                kind='limit')

    blocks = system_blocks(profile)
    started = time.monotonic()
    try:
        reply = provider.complete(
            blocks, user_text, schema, model,
            max_tokens or _setting('AI_MAX_TOKENS', DEFAULT_MAX_TOKENS))
    except providers.ProviderError as error:
        _log(user, profile, provider.name, model, None,
             time.monotonic() - started, ok=False, note=str(error)[:290])
        raise AiUnavailable(str(error), kind=getattr(error, 'kind', 'other'))

    seconds = time.monotonic() - started
    usage = _log(user, profile, provider.name, model, reply, seconds)

    try:
        data = json.loads(reply.text)
    except ValueError:
        # Мусор вместо структуры — это не «поломка сервера», а «модель
        # ответила не тем». Репетитору нужен понятный выход, а не трассировка.
        logger.warning('Модель вернула не JSON (профиль %s)', profile)
        raise AiUnavailable(
            'Разбор запроса вернул неожиданный ответ. Попробуйте описать '
            'домашку иначе или соберите её вручную.')
    if not isinstance(data, dict):
        raise AiUnavailable(
            'Разбор запроса вернул неожиданный ответ. Попробуйте описать '
            'домашку иначе или соберите её вручную.')

    result = AiResult(data, usage, cached=False)
    cache.set(key, {'data': data, 'usage': usage},
              cache_seconds if cache_seconds is not None
              else _setting('AI_CACHE_SECONDS', DEFAULT_CACHE_SECONDS))
    return result


def _cost(model, reply):
    """Деньги за обращение с учётом кэша префикса."""
    prices = _setting('AI_PRICES', DEFAULT_PRICES)
    price_in, price_out = prices.get(model, DEFAULT_PRICES[DEFAULT_MODEL])
    price_in = Decimal(str(price_in))
    price_out = Decimal(str(price_out))
    total = (Decimal(reply.input_tokens) * price_in
             + Decimal(reply.output_tokens) * price_out
             + Decimal(reply.cache_write_tokens) * price_in
             * CACHE_WRITE_MULTIPLIER
             + Decimal(reply.cache_read_tokens) * price_in
             * CACHE_READ_MULTIPLIER)
    return (total / Decimal(10 ** 6)).quantize(Decimal('0.000001'))


def _log(user, profile, provider_name, model, reply, seconds, ok=True,
         note=''):
    """Строка расхода. ⚠️ Запись НЕБЛОКИРУЮЩАЯ — как учебные события.

    Упавший учёт не имеет права уронить работу репетитора: он пришёл
    собирать домашку, а не вести нашу бухгалтерию.
    """
    from problems.models import AiUsageLog

    if reply is None:
        reply = providers.Reply('')
    cost = _cost(model, reply)
    usage = {
        'input_tokens': reply.input_tokens,
        'output_tokens': reply.output_tokens,
        'cache_write_tokens': reply.cache_write_tokens,
        'cache_read_tokens': reply.cache_read_tokens,
        'cost_usd': float(cost),
        'model': model,
        'provider': provider_name,
        'seconds': round(seconds, 2),
        'profile': profile,
        'ok': ok,
    }
    if user is None:
        return usage
    try:
        AiUsageLog.objects.create(
            user=user, kind=profile, model_name=model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cache_write_tokens=reply.cache_write_tokens,
            cache_read_tokens=reply.cache_read_tokens,
            provider=provider_name, seconds=round(seconds, 2),
            cost_usd=cost, ok=ok, note=note)
    except Exception:
        logger.exception('Не удалось записать расход на ИИ — основной '
                         'сценарий не тронут')
    return usage
