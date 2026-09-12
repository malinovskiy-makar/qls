"""
Единая точка обращения к модели: `run(profile, ...)`.

Здесь и только здесь живут кэш, лимиты, учёт расхода и разбор ответа.
Продуктовый код (подбор домашки и всё, что появится следом) знает про
модель ровно одно слово — `run`.

⚠️ ДВА ВИДА ПОТРЕБИТЕЛЕЙ, ОДНА ДВЕРЬ (13.09.2026). Изначально `run`
обслуживал только ПРОФИЛИ ГЕНЕРАЦИИ (`prompts.PROFILES`): общий
поставщик из `AI_PROVIDER`, общая модель из `AI_MODEL`, суточный лимит
ОБРАЩЕНИЙ на пользователя. Переранжирование поиска в эту форму не
влезало и потому ходило к поставщику мимо — со своим учётом и без
лимитов вовсе. Теперь у `run` есть переопределения (`provider_name`,
`model`, `system`, `parse`) и ВТОРОЙ вид лимита — суточный ДЕНЕЖНЫЙ
потолок на функцию (`AI_DAILY_COST_CAPS`). Обходить дверь больше незачем:
любая функция сайта, сколько бы она ни стоила, видна в одном журнале
`AiUsageLog` и упирается в один из двух лимитов.
"""
import hashlib
import json
import logging
import time
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone

from . import providers
from .prompts import PROFILES, system_blocks

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = 'anthropic'
DEFAULT_MODEL = 'claude-haiku-4-5'
# Цена за миллион токенов: (вход, выход). Держим таблицей, а не числами в
# расчёте: тариф меняется, и меняться он должен в одном месте.
DEFAULT_PRICES = {'claude-haiku-4-5': (1.0, 5.0)}
# Записанный в кэш токен стоит на четверть дороже обычного, прочитанный из
# кэша — десятую часть. Отсюда и вся выгода.
CACHE_WRITE_MULTIPLIER = Decimal('1.25')
CACHE_READ_MULTIPLIER = Decimal('0.1')

DEFAULT_DAILY_LIMIT = 30
#: Суточный денежный потолок по видам работ (`AiUsageLog.kind`), $ в сутки.
#: Пусто — потолка нет, работает только счётчик обращений на пользователя.
DEFAULT_DAILY_COST_CAPS = {}
# Потолок одного вызова, секунд. Вечный спиннер хуже любой ошибки (ADR 0079).
DEFAULT_TIMEOUT_SECONDS = 25
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


def daily_cost_cap(kind):
    """Суточный денежный потолок этой работы в долларах или None.

    Второй вид лимита рядом с `daily_limit()`, и он про ДРУГОЕ. Счётчик
    обращений защищает от того, что один репетитор выберет бюджет всего
    сайта; он привязан к пользователю и на гостя не работает вовсе.
    Денежный потолок защищает сайт целиком — им закрываются функции,
    которыми пользуются БЕЗ ВХОДА (поиск в каталоге), где считать «на
    пользователя» нечего.
    """
    caps = _setting('AI_DAILY_COST_CAPS', DEFAULT_DAILY_COST_CAPS)
    value = caps.get(kind)
    return None if value is None else Decimal(str(value))


def spent_today(kind):
    """Сколько денег эта работа истратила с начала суток, $.

    ⚠️ СЧИТАЮТСЯ ВСЕ СТРОКИ, И УДАЧНЫЕ, И НЕТ — в отличие от
    `used_today()`. Там лимит про справедливость («репетитор не получил
    разбор — не отнимаем попытку»), здесь про деньги: неудачный вызов,
    за который поставщик успел выставить токены, потрачен так же честно,
    как удачный.
    """
    from problems.models import AiUsageLog

    start = timezone.localtime(timezone.now()).replace(
        hour=0, minute=0, second=0, microsecond=0)
    total = (AiUsageLog.objects.filter(kind=kind, created_at__gte=start)
             .aggregate(models.Sum('cost_usd'))['cost_usd__sum'])
    return Decimal(total or 0)


def budget_exceeded(kind):
    """Выбран ли суточный денежный потолок этой работы.

    Отдельная функция, потому что спрашивать об этом иногда надо ДО
    вызова `run`: тот, кто шлёт несколько пачек параллельно, обязан
    спросить один раз в потоке запроса, а не по разу в каждом рабочем
    потоке — иначе на каждый поисковый запрос уходит по лишнему запросу
    в базу из потока, которому соединение никто не закроет.
    """
    cap = daily_cost_cap(kind)
    return cap is not None and spent_today(kind) >= cap


def remaining_today(user):
    """Сколько обращений осталось сегодня — для строки «осталось сегодня N»."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return 0
    return max(0, daily_limit() - used_today(user))


def timeout_seconds():
    return _setting('AI_TIMEOUT_SECONDS', DEFAULT_TIMEOUT_SECONDS)


def _cache_key(profile, model, user_text):
    """Ключ НАШЕГО кэша ответов — не путать с кэшем префикса у поставщика.

    Наш кэш экономит обращение целиком (одинаковый запрос в течение
    четверти часа), кэш поставщика — часть его стоимости.
    """
    payload = json.dumps([profile, model, user_text], ensure_ascii=False)
    return 'ai:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def run(profile, user_text, schema, user, max_tokens=None,
        cache_seconds=None, check_limit=True, timeout=None, images=None,
        provider=None, model=None, system=None, parse=None, log=True,
        check_budget=True):
    """Выполнить задачу `profile` и вернуть разобранную структуру.

    `user_text` — ВСЁ переменное: описание, параметры, подсказки из банка.
    В системную часть ничего переменного не попадает никогда (см.
    `prompts.py`), иначе кэш префикса перестаёт срабатывать.

    `timeout` — потолок одного вызова в секундах (по умолчанию
    `AI_TIMEOUT_SECONDS`): превышение — `AiUnavailable('other')` с
    человеческим текстом, а не вечное ожидание.

    `images` — список `{media_type, data}` (base64) для распознавания
    текста с фото: файл уходит поставщику блоком рядом с текстом. Кэш
    ответов ключ по картинке не считает — вызывающий кладёт хеш файла в
    `user_text` (`catalog/attachments.py`).

    ⚠️ ПЕРЕОПРЕДЕЛЕНИЯ — ДЛЯ ФУНКЦИЙ, КОТОРЫЕ НЕ ЯВЛЯЮТСЯ ПРОФИЛЯМИ
    ГЕНЕРАЦИИ (см. докстринг модуля). Не задано ни одно — работает старое
    поведение слово в слово.

    * `provider` — ГОТОВЫЙ поставщик вместо того, что назван в
      `AI_PROVIDER`. Принимается объект, а не имя, и это намеренно: у
      вызывающего остаётся один шов, на котором поставщика подменяют
      тесты, — иначе шов раздвоился бы, и подмена в тестах перестала бы
      совпадать с тем, что происходит на самом деле.
    * `model` — модель вместо `AI_MODEL`, по той же причине.
    * `system` — готовые системные блоки вместо `prompts.PROFILES`.
      Тогда `profile` служит только ИМЕНЕМ РАБОТЫ в журнале расхода и в
      денежном потолке, а в `PROFILES` его может не быть вовсе.
    * `parse` — разбор текста ответа вместо строгого `json.loads`.
      Терпимый разбор (обрезка, массив вместо объекта, обрамление
      ```) живёт у вызывающего, потому что чинить он умеет только
      СВОЙ формат ответа.
    * `check_budget=False` — не спрашивать суточный денежный потолок
      здесь: вызывающий спросил `budget_exceeded()` сам, один раз на
      действие человека. Ставится вместе с `log=False` и по той же
      причине — чтобы в рабочих потоках не было обращений к базе.
    * `log=False` — не писать строку расхода СЕЙЧАС; посчитанный расход
      всё равно вернётся в `AiResult.usage`. Нужен тому, кто шлёт
      НЕСКОЛЬКО вызовов на одно действие человека, да ещё и в потоках:
      писать строку из рабочего потока значит открыть там своё
      соединение с базой (в Django они потоко-локальные), а закрывать
      его некому — штатный `close_old_connections` висит на сигналах
      запроса и живёт в главном потоке. Такой вызывающий складывает
      расход сам и пишет ОДНУ строку через `record_usage()` — по строке
      на действие человека, а не на пачку.
    """
    provider = provider if provider is not None else _provider()
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

    # ⚠️ ДЕНЕЖНЫЙ ПОТОЛОК ПРОВЕРЯЕТСЯ ОТДЕЛЬНО ОТ `check_limit`.
    # `check_limit=False` ставят там, где нет пользователя, которому можно
    # списать обращение, — то есть ровно там, где счётчик обращений не
    # защищает ничего и работает один потолок. `check_budget=False` — для
    # того, кто уже спросил `budget_exceeded()` сам, один раз на действие
    # человека (см. её докстринг).
    if check_budget and budget_exceeded(profile):
        raise AiUnavailable(
            'На сегодня исчерпан суточный бюджет этой функции ($%s).'
            % daily_cost_cap(profile), kind='limit')

    blocks = system if system is not None else system_blocks(profile)
    started = time.monotonic()
    try:
        reply = provider.complete(
            blocks, user_text, schema, model,
            max_tokens or _setting('AI_MAX_TOKENS', DEFAULT_MAX_TOKENS),
            timeout=timeout or timeout_seconds(), images=images or None)
    except providers.ProviderError as error:
        _log(user, profile, provider.name, model, None,
             time.monotonic() - started, ok=False, note=str(error)[:290])
        raise AiUnavailable(str(error), kind=getattr(error, 'kind', 'other'))

    seconds = time.monotonic() - started
    usage = (_log(user, profile, provider.name, model, reply, seconds) if log
             else _usage_of(profile, provider.name, model, reply, seconds))

    try:
        data = parse(reply.text) if parse else json.loads(reply.text)
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
    """Деньги за обращение с учётом кэша префикса.

    ⚠️ ЭТО ОЦЕНКА, А НЕ СЧЁТ. Считается по нашей таблице цен и нашему
    пониманию того, что поставщик тарифицирует. Сверить с реальным
    списанием обязательно на пилоте: расхождение здесь означает, что
    смета всего прогона обогащения посчитана неверно.

    Цена в таблице — кортеж из ТРЁХ чисел (вход, кэш, выход) за миллион
    токенов. Кортеж из ДВУХ (вход, выход) продолжает работать: цена кэша
    выводится из цены входа старым множителем. Для `claude-haiku-4-5`
    обе записи дают одно и то же число — (1.0, 5.0) и (1.0, 0.1, 5.0)
    совпадают, потому что 1.0 × 0.1 = 0.1.

    Токены рассуждения отдельно НЕ прибавляются: они уже сидят внутри
    `output_tokens` (см. Reply в providers.py) и посчитались бы дважды.
    """
    prices = _setting('AI_PRICES', DEFAULT_PRICES)
    row = prices.get(model, DEFAULT_PRICES[DEFAULT_MODEL])
    if len(row) == 3:
        price_in, price_cache, price_out = row
        price_cache = Decimal(str(price_cache))
    else:
        price_in, price_out = row
        price_cache = Decimal(str(price_in)) * CACHE_READ_MULTIPLIER
    price_in = Decimal(str(price_in))
    price_out = Decimal(str(price_out))
    total = (Decimal(reply.input_tokens) * price_in
             + Decimal(reply.output_tokens) * price_out
             + Decimal(reply.cache_write_tokens) * price_in
             * CACHE_WRITE_MULTIPLIER
             + Decimal(reply.cache_read_tokens) * price_cache)
    return (total / Decimal(10 ** 6)).quantize(Decimal('0.000001'))


def _usage_of(profile, provider_name, model, reply, seconds, ok=True):
    """Расход одного вызова словарём — БЕЗ записи в журнал."""
    cost = _cost(model, reply)
    return {
        'input_tokens': reply.input_tokens,
        'output_tokens': reply.output_tokens,
        'cache_write_tokens': reply.cache_write_tokens,
        'cache_read_tokens': reply.cache_read_tokens,
        'reasoning_tokens': getattr(reply, 'reasoning_tokens', 0),
        'cost_usd': float(cost),
        'model': model,
        'provider': provider_name,
        'seconds': round(seconds, 2),
        'profile': profile,
        'ok': ok,
    }


def record_usage(profile, provider_name, model, usages, seconds, user=None):
    """Сложить расход нескольких вызовов в ОДНУ строку журнала.

    Для тех, кто на одно действие человека делает несколько обращений
    (пачками, возможно в потоках) и звал `run(..., log=False)`. Пишется в
    том потоке, откуда позвали, — то есть в потоке запроса, где
    соединением с базой занимается сам Django.
    """
    reply = providers.Reply('')
    for usage in usages:
        reply.input_tokens += usage.get('input_tokens', 0)
        reply.output_tokens += usage.get('output_tokens', 0)
        reply.cache_write_tokens += usage.get('cache_write_tokens', 0)
        reply.cache_read_tokens += usage.get('cache_read_tokens', 0)
        reply.reasoning_tokens = (getattr(reply, 'reasoning_tokens', 0)
                                  + usage.get('reasoning_tokens', 0))
    return _log(user, profile, provider_name, model, reply, seconds)


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
        'reasoning_tokens': getattr(reply, 'reasoning_tokens', 0),
        'cost_usd': float(cost),
        'model': model,
        'provider': provider_name,
        'seconds': round(seconds, 2),
        'profile': profile,
        'ok': ok,
    }
    # ⚠️ Гость тоже попадает в журнал (`user=None`). Раньше строка без
    # пользователя не писалась вовсе — и трат функции, которой пользуются
    # без входа, в журнале не было, а значит и денежный потолок по ним не
    # считался. Поле стало необязательным миграцией problems 0064.
    try:
        AiUsageLog.objects.create(
            user=user, kind=profile, model_name=model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cache_write_tokens=reply.cache_write_tokens,
            cache_read_tokens=reply.cache_read_tokens,
            reasoning_tokens=getattr(reply, 'reasoning_tokens', 0),
            provider=provider_name, seconds=round(seconds, 2),
            cost_usd=cost, ok=ok, note=note)
    except Exception:
        logger.exception('Не удалось записать расход на ИИ — основной '
                         'сценарий не тронут')
    return usage
