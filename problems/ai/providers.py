"""
Поставщики модели. Смена — НАСТРОЙКОЙ, а не правкой кода продукта.

Наружу каждый поставщик отдаёт одно и то же: `complete(...) → Reply`.
Никакой продуктовый код здесь не появляется — иначе переезд на российскую
модель снова стал бы переписыванием, от которого этот слой и защищает.

Как переключить (`config/settings*.py`):

    AI_PROVIDER = 'anthropic'      # по умолчанию; ещё 'openai', 'fake'
    AI_MODEL = 'claude-haiku-4-5'
    AI_PRICES = {'claude-haiku-4-5': (1.0, 0.1, 5.0)}  # $ за млн: вход, кэш, выход
    AI_REASONING_EFFORT = 'none'   # none/low/medium/high/xhigh/max (OpenAI)

Подставной поставщик для тестов:

    AI_PROVIDER = 'fake'
    AI_FAKE_REPLY = '{"rows": [...]}'   # или функция (profile, text) → str
"""
import json
import logging
import os


class Reply(object):
    """Ответ поставщика: текст плюс счётчики токенов.

    ⚠️ `reasoning_tokens` — ЧАСТЬ `output_tokens`, а не добавка к ним.
    У моделей с рассуждением токены рассуждения тарифицируются как
    выходные и уже входят в `output_tokens`; отдельное поле нужно, чтобы
    понять, куда ушёл бюджет, а не чтобы посчитать деньги дважды.
    Поэтому `_cost` его НЕ прибавляет — см. problems/ai/core.py.
    """

    def __init__(self, text, input_tokens=0, output_tokens=0,
                 cache_write_tokens=0, cache_read_tokens=0,
                 reasoning_tokens=0):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_write_tokens = cache_write_tokens
        self.cache_read_tokens = cache_read_tokens
        self.reasoning_tokens = reasoning_tokens


logger = logging.getLogger(__name__)


def log_cause(error):
    """Записать в журнал НАСТОЯЩУЮ причину отказа поставщика.

    ⚠️ ЗАЧЕМ (ревью 16.08, п. 7.5). Наружу поставщик отдаёт человеческий
    текст — репетитору код ошибки не говорит ничего. Но в журнал сервера
    попадал ТОТ ЖЕ текст, и причину приходилось искать руками: локально
    подбор падал из-за `urllib3` v2, несовместимой с LibreSSL системного
    Python 3.9, а в логе стояло «Сервис разбора запроса недоступен».
    Класс исключения и его сообщение теперь пишутся всегда.
    """
    logger.warning('Поставщик модели отказал: %s: %s',
                   type(error).__name__, error, exc_info=True)


class ProviderError(Exception):
    """Поставщик не смог ответить. Текст уже человеческий.

    ⚠️ У ОТКАЗА ЕСТЬ ВИД (`kind`) — сессия 7, фаза 7.4. Экран показывает
    репетитору не текст поставщика, а свой, зависящий от вида: «не настроен
    доступ» и «сервис не ответил» — это разные советы. Код ошибки
    (401/429/500) остаётся в журнале сервера и на экран не выходит: он
    ничего не говорит тому, кто собирает домашку.

    ⚠️ `original` — СЫРОЕ исключение поставщика (`openai.APIStatusError` и
    т.п.), НЕ печатается на экран репетитору (см. выше), но нужно журналу
    отказов боевого прогона (`pilot_enrich_v2.append_error_log`): именно в
    нём живут `status_code`/`body`/код провайдера. Разбор `run2-corpus-
    20260904` (04.09.2026) полтора часа отказов `400 code 1210` не смог
    разобрать ИМЕННО потому, что `ProviderError` терял их бесследно —
    `_fail()` заворачивал их в человеческий текст и выбрасывал оригинал.
    `None` — когда `ProviderError` создан напрямую, не через `_fail()`
    (например `FakeProvider`)."""

    def __init__(self, message, kind='other', original=None):
        super(ProviderError, self).__init__(message)
        self.kind = kind
        self.original = original


class BaseProvider(object):
    name = ''
    # Имя переменной окружения с ключом. Ключ НИКОГДА не берётся из
    # настроек и не попадает в репозиторий.
    key_env = ''

    def api_key(self):
        return os.environ.get(self.key_env, '').strip() if self.key_env else ''

    def is_available(self):
        raise NotImplementedError

    def unavailable_reason(self):
        raise NotImplementedError

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 images=None):
        raise NotImplementedError


    def _fail(self, error, text, kind='other'):
        """Записать причину в журнал и вернуть человеческий отказ.

        ⚠️ ОДНА ТОЧКА НА ВСЕ ВЕТКИ. Раньше каждая ветка `except` собирала
        свой `ProviderError`, а настоящее исключение выбрасывалось молча:
        в журнале оставался тот же текст, что видел репетитор. Локально
        это стоило часа поисков — падала `urllib3` v2 на LibreSSL, а лог
        сообщал «Сервис разбора запроса недоступен».

        `original=error` — та же причина, что уходит и в `log_cause`, но
        сохранённая НА объекте, а не только в логгере: журналу отказов
        боевого прогона (Фаза 1, 04.09.2026) нужен `status_code`/`body`
        оригинального исключения, а не человеческий текст `text`.
        """
        log_cause(error)
        return ProviderError(text, kind=kind, original=error)

class AnthropicProvider(BaseProvider):
    name = 'anthropic'
    key_env = 'ANTHROPIC_API_KEY'

    def is_available(self):
        if not self.api_key():
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def unavailable_reason(self):
        if not self.api_key():
            return ('Работа с моделью выключена: не задан ключ '
                    'ANTHROPIC_API_KEY. Всё остальное работает как обычно — '
                    'соберите домашку вручную, поиск и фильтры на месте.')
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return ('Работа с моделью выключена: на этом сервере не '
                    'установлена библиотека anthropic. Соберите домашку '
                    'вручную.')
        return ''

    def complete(self, system_blocks, user_text, schema, model, max_tokens):
        """⚠️ КЭШИРУЕТСЯ ТОЛЬКО ПЕРВЫЙ БЛОК — неизменное ядро.

        Пометка стоит на нём, потому что скидка даётся на ПРЕФИКС запроса:
        всё до отметки включительно. Поставить её на профиль значило бы
        кэшировать и ядро, и профиль — а профиль правится куда чаще, и
        каждая его правка обнуляла бы кэш целиком.
        """
        import anthropic

        system = []
        for number, text in enumerate(system_blocks):
            block = {'type': 'text', 'text': text}
            if number == 0:
                block['cache_control'] = {'type': 'ephemeral'}
            system.append(block)

        client = anthropic.Anthropic(api_key=self.api_key())
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{'role': 'user', 'content': user_text}],
                output_config={'format': {'type': 'json_schema',
                                          'schema': schema}},
            )
        except anthropic.APIConnectionError as error:
            raise self._fail(
                error,
                'Не удалось связаться с сервисом разбора запроса. Проверьте '
                'сеть или соберите домашку вручную.')
        except anthropic.RateLimitError as error:
            raise self._fail(
                error,
                'Сервис разбора сейчас перегружен. Попробуйте через минуту '
                'или соберите домашку вручную.')
        except anthropic.APIStatusError as error:
            # 401/403 — ключ не принят: это «не настроен доступ», а не
            # «сервис молчит», и совет репетитору другой.
            kind = 'no_key' if error.status_code in (401, 403) else 'other'
            raise self._fail(
                error,
                'Сервис разбора вернул ошибку (%s).' % error.status_code,
                kind=kind)
        except Exception as error:
            # Библиотека может кинуть что угодно своё. Белого экрана у
            # репетитора быть не должно ни при какой ошибке.
            raise self._fail(
                error,
                'Сервис разбора запроса недоступен. Соберите домашку '
                'вручную.')

        usage = response.usage
        return Reply(
            text=''.join(block.text for block in response.content
                         if block.type == 'text'),
            input_tokens=getattr(usage, 'input_tokens', 0) or 0,
            output_tokens=getattr(usage, 'output_tokens', 0) or 0,
            cache_write_tokens=getattr(
                usage, 'cache_creation_input_tokens', 0) or 0,
            cache_read_tokens=getattr(usage, 'cache_read_input_tokens', 0) or 0,
        )


class OpenAIProvider(BaseProvider):
    """GPT через OpenAI Responses API. Тот же контракт, что у Anthropic.

    ⚠️ ВХОДНЫЕ И КЭШИРОВАННЫЕ ТОКЕНЫ РАЗВОДЯТСЯ ЗДЕСЬ. У OpenAI
    `usage.input_tokens` — ПОЛНЫЙ вход, и прочитанное из кэша сидит
    ВНУТРИ него (`input_tokens_details.cached_tokens` — подмножество).
    У Anthropic наоборот: `input_tokens` и `cache_read_input_tokens`
    не пересекаются, и `_cost` считает их сложением. Отдай мы сюда
    сырые числа OpenAI — кэшированная часть посчиталась бы дважды.
    Поэтому наружу отдаём НЕПЕРЕСЕКАЮЩИЕСЯ значения: свежий вход и
    отдельно кэш. Сумма (вход + кэш) сходится с полным входом OpenAI.
    """

    name = 'openai'
    key_env = 'OPENAI_API_KEY'

    # Минимальная длина префикса, с которой у GPT-5.6 вообще включается
    # кэш. Ядро короче — скидки не будет ни при каких условиях, и это
    # надо увидеть в журнале, а не гадать по нулям в отчёте.
    CACHE_MIN_TOKENS = 1024
    # Грубая оценка «символов на токен» для предупреждения выше. Точный
    # счёт требует токенизатора модели; для проверки «явно короче тысячи»
    # хватает и оценки, а ошибиться она может только в сторону запаса.
    CHARS_PER_TOKEN = 4

    def is_available(self):
        if not self.api_key():
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def unavailable_reason(self):
        if not self.api_key():
            return ('Работа с моделью выключена: не задан ключ '
                    'OPENAI_API_KEY. Всё остальное работает как обычно — '
                    'соберите домашку вручную, поиск и фильтры на месте.')
        try:
            import openai  # noqa: F401
        except ImportError:
            return ('Работа с моделью выключена: на этом сервере не '
                    'установлена библиотека openai. Соберите домашку '
                    'вручную.')
        return ''

    def _warn_if_cache_too_short(self, system_blocks):
        """Кэш у GPT-5.6 берётся от префикса длиной от 1024 токенов.

        Ядро короче — кэш не включится вовсе, и нули в отчёте будут
        означать «слишком короткое ядро», а не «кэш не сработал».
        Различить эти два случая постфактум нельзя, поэтому предупреждаем
        сразу.
        """
        core = system_blocks[0] if system_blocks else ''
        approx = len(core) // self.CHARS_PER_TOKEN
        if approx < self.CACHE_MIN_TOKENS:
            logger.warning(
                'Ядро промпта короче %d токенов (оценка: %d) — кэш префикса '
                'у GPT-5.6 не включится, скидки не будет.',
                self.CACHE_MIN_TOKENS, approx)

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 images=None):
        """⚠️ СХЕМА СТРОГАЯ (`strict: true`) — иначе ответ не принимается.

        Всё, что модель написала мимо схемы, отбрасывается на стороне
        поставщика: разбирать «почти JSON» на прогоне в 41 307 задач
        некому. Кэш префикса у OpenAI автоматический, помечать блок,
        как у Anthropic, не нужно — достаточно неизменного начала.

        `images` — необязательный список пар `(MIME-тип, байты)`: картинки
        САМОЙ ЗАДАЧИ из `ProblemFigure.image_data`. Уходят они через этот
        же слой и по тому же правилу «наружу только содержимое задачи»
        (problems/ai/CLAUDE.md): картинка условия — часть условия, поля
        профиля пользователя сюда не попадают и попасть не могут.
        Без картинок вход остаётся ПРОСТОЙ СТРОКОЙ — ровно тем же, что
        уходило до этой правки, чтобы кэш префикса не сломался.
        """
        import openai

        from django.conf import settings

        self._warn_if_cache_too_short(system_blocks)

        effort = getattr(settings, 'AI_REASONING_EFFORT', 'none')

        client = openai.OpenAI(api_key=self.api_key())
        try:
            response = client.responses.create(
                model=model,
                max_output_tokens=max_tokens,
                instructions='\n\n'.join(system_blocks),
                input=self._input_payload(user_text, images),
                reasoning={'effort': effort},
                text={'format': {'type': 'json_schema',
                                 'name': 'reply',
                                 'strict': True,
                                 'schema': schema}},
            )
        except openai.APIConnectionError as error:
            raise self._fail(
                error,
                'Не удалось связаться с сервисом разбора запроса. Проверьте '
                'сеть или соберите домашку вручную.')
        except openai.RateLimitError as error:
            raise self._fail(
                error,
                'Сервис разбора сейчас перегружен. Попробуйте через минуту '
                'или соберите домашку вручную.',
                kind='limit')
        except openai.APIStatusError as error:
            # 401/403 — ключ не принят: это «не настроен доступ», а не
            # «сервис молчит», и совет репетитору другой.
            kind = 'no_key' if error.status_code in (401, 403) else 'other'
            raise self._fail(
                error,
                'Сервис разбора вернул ошибку (%s).' % error.status_code,
                kind=kind)
        except Exception as error:
            raise self._fail(
                error,
                'Сервис разбора запроса недоступен. Соберите домашку '
                'вручную.')

        return self._reply_from(response)

    #: Форматы, которые Responses API принимает как `input_image`.
    #: `image/bmp` в список не входит — в банке такая картинка одна.
    IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')

    def _input_payload(self, user_text, images):
        """Вход для Responses API: строка без картинок, список блоков — с
        ними.

        Картинка уходит как `data:`-URL внутри запроса, а не ссылкой:
        байты лежат в базе (`ProblemFigure.image_data`), файла на диске
        нет, и внешний адрес источника мог давно протухнуть.
        """
        if not images:
            return user_text
        import base64

        content = [{'type': 'input_text', 'text': user_text}]
        for content_type, data in images:
            if content_type not in self.IMAGE_TYPES or not data:
                continue
            content.append({
                'type': 'input_image',
                'image_url': 'data:%s;base64,%s' % (
                    content_type, base64.b64encode(bytes(data)).decode('ascii')),
            })
        if len(content) == 1:  # ни одна картинка не подошла
            return user_text
        return [{'role': 'user', 'content': content}]

    def _reply_from(self, response):
        """Разбор ответа: текст плюс четыре счётчика токенов."""
        usage = getattr(response, 'usage', None)
        total_input = _num(usage, 'input_tokens')
        output = _num(usage, 'output_tokens')

        in_details = getattr(usage, 'input_tokens_details', None)
        cache_read = _num(in_details, 'cached_tokens')
        cache_write = _num(in_details, 'cache_write_tokens')

        out_details = getattr(usage, 'output_tokens_details', None)
        reasoning = _num(out_details, 'reasoning_tokens')

        return Reply(
            text=_output_text(response),
            # Кэш вычитается из входа — см. докстринг класса.
            input_tokens=max(total_input - cache_read, 0),
            output_tokens=output,
            cache_write_tokens=cache_write,
            cache_read_tokens=cache_read,
            reasoning_tokens=reasoning,
        )


def _num(holder, name):
    """Число из поля SDK: и объект, и словарь, и отсутствие поля."""
    if holder is None:
        return 0
    if isinstance(holder, dict):
        value = holder.get(name)
    else:
        value = getattr(holder, name, None)
    return int(value or 0)


def _output_text(response):
    """Текст ответа: `output_text` у SDK, иначе сборка из блоков."""
    text = getattr(response, 'output_text', None)
    if text:
        return text
    parts = []
    for item in getattr(response, 'output', None) or []:
        for block in getattr(item, 'content', None) or []:
            piece = getattr(block, 'text', None)
            if piece:
                parts.append(piece)
    return ''.join(parts)


class GLMProvider(BaseProvider):
    """GLM (Z.AI) через OpenAI-совместимый `chat.completions` эндпоинт.

    ⚠️ НЕ ТОТ ЖЕ КОНТРАКТ, ЧТО У OpenAIProvider — три отличия документации
    Z.AI (проверено обращением к их `docs.z.ai`, сентябрь 2026):
    1. Эндпоинт `client.chat.completions.create`, а не Responses API —
       у Z.AI своей Responses-совместимой версии нет.
    2. `response_format` принимает только `text`/`json_object` —
       `json_schema` и `strict` НЕ поддерживаются вовсе. Схема поэтому
       уходит ТЕКСТОМ внутри системного сообщения (см. `_schema_instruction`),
       а не отдельным параметром API, и соответствие ей проверяется на
       нашей стороне уже ПОСЛЕ ответа — гарантии поставщика здесь нет,
       это и есть предмет замера «доля ответов, прошедших схему».
    3. Рассуждение переключается `thinking.type` (`enabled`/`disabled`) +
       `reasoning_effort`, а не одним полем `reasoning.effort`, как у
       OpenAI.
    """

    name = 'glm'
    key_env = 'GLM_API_KEY'
    BASE_URL = 'https://api.z.ai/api/paas/v4/'

    def is_available(self):
        if not self.api_key():
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def unavailable_reason(self):
        if not self.api_key():
            return ('Работа с моделью выключена: не задан ключ '
                    'GLM_API_KEY. Всё остальное работает как обычно — '
                    'соберите домашку вручную, поиск и фильтры на месте.')
        try:
            import openai  # noqa: F401
        except ImportError:
            return ('Работа с моделью выключена: на этом сервере не '
                    'установлена библиотека openai. Соберите домашку '
                    'вручную.')
        return ''

    def _schema_instruction(self, schema):
        return ('\n\nОТВЕЧАЙ РОВНО ОДНИМ JSON-ОБЪЕКТОМ, СТРОГО '
                'СООТВЕТСТВУЮЩИМ ЭТОЙ JSON-СХЕМЕ (никакого текста ни до, '
                'ни после, никакого markdown-обрамления ```):\n%s'
                % json.dumps(schema, ensure_ascii=False))

    #: Форматы, которые Z.AI chat.completions принимает как `image_url`
    #: (тот же список, что у OpenAIProvider — см. её докстринг).
    IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')

    def _user_content(self, user_text, images):
        """Вход для `chat.completions`: строка без картинок, массив
        content-блоков — с ними. Формат `image_url` с `data:`-URL — тот
        же, что у OpenAI vision, Z.AI заявляет OpenAI-совместимость.
        Диагностический вызов Фазы 0 проверяет, читает ли модель это
        вообще (по `usage` — есть ли токены изображения)."""
        if not images:
            return user_text
        import base64

        content = [{'type': 'text', 'text': user_text}]
        for content_type, data in images:
            if content_type not in self.IMAGE_TYPES or not data:
                continue
            content.append({
                'type': 'image_url',
                'image_url': {'url': 'data:%s;base64,%s' % (
                    content_type, base64.b64encode(bytes(data)).decode('ascii'))},
            })
        if len(content) == 1:  # ни одна картинка не подошла
            return user_text
        return content

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 images=None):
        import openai

        from django.conf import settings

        effort = getattr(settings, 'AI_REASONING_EFFORT', 'none')
        instructions = '\n\n'.join(system_blocks) + self._schema_instruction(schema)

        # ⚠️ GLM-5.3-Flash ВСЕГДА рассуждает — `thinking.type: disabled`
        # отклоняется API кодом 1210 («This model always engages in
        # thinking and cannot be disabled; please use low, high, or max»).
        # `low` — ближайший доступный заменитель «выключено», а не выбор
        # по вкусу; сравнение с моделями, где reasoning=none реален,
        # честно только с пометкой об этом отличии.
        extra_body = {'thinking': {'type': 'enabled'}}
        extra_body['reasoning_effort'] = effort if effort in (
            'low', 'high', 'max') else 'low'

        client = openai.OpenAI(api_key=self.api_key(), base_url=self.BASE_URL)
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {'role': 'system', 'content': instructions},
                    {'role': 'user', 'content': self._user_content(user_text, images)},
                ],
                response_format={'type': 'json_object'},
                extra_body=extra_body,
            )
        except openai.APIConnectionError as error:
            raise self._fail(
                error,
                'Не удалось связаться с сервисом разбора запроса. Проверьте '
                'сеть или соберите домашку вручную.')
        except openai.RateLimitError as error:
            raise self._fail(
                error,
                'Сервис разбора сейчас перегружен. Попробуйте через минуту '
                'или соберите домашку вручную.',
                kind='limit')
        except openai.APIStatusError as error:
            kind = 'no_key' if error.status_code in (401, 403) else 'other'
            raise self._fail(
                error,
                'Сервис разбора вернул ошибку (%s).' % error.status_code,
                kind=kind)
        except Exception as error:
            raise self._fail(
                error,
                'Сервис разбора запроса недоступен. Соберите домашку '
                'вручную.')

        return self._reply_from(response)

    def _reply_from(self, response):
        """Разбор ответа: `prompt_tokens_details.cached_tokens` — то же
        разведение «свежий вход / кэш», что у OpenAI (см. докстринг
        `OpenAIProvider`) — Z.AI считает `prompt_tokens` ПОЛНЫМ входом,
        кэш сидит внутри него.

        ⚠️ `reasoning_tokens` — БАГ ДО Фазы 6 (2026-09-04): это поле
        никогда не читалось вовсе, и `Reply.reasoning_tokens` тихо был 0 на
        КАЖДОМ вызове GLM, независимо от реального уровня рассуждения —
        смок-тест Фазы 6 (задачи 1/13/57130/57144/57149, `effort='high'`)
        первым это заметил. Схема поля у Z.AI СВОЯ: `completion_tokens_
        details.reasoning_tokens`, а не `output_tokens_details`, как у
        OpenAI Responses API (см. `OpenAIProvider._reply_from`) — проверено
        живым вызовом `chat.completions.create`."""
        usage = getattr(response, 'usage', None)
        total_input = _num(usage, 'prompt_tokens')
        output = _num(usage, 'completion_tokens')

        details = getattr(usage, 'prompt_tokens_details', None)
        cache_read = _num(details, 'cached_tokens')

        out_details = getattr(usage, 'completion_tokens_details', None)
        reasoning = _num(out_details, 'reasoning_tokens')

        text = ''
        choices = getattr(response, 'choices', None) or []
        if choices:
            message = getattr(choices[0], 'message', None)
            text = getattr(message, 'content', None) or ''

        return Reply(
            text=text,
            input_tokens=max(total_input - cache_read, 0),
            output_tokens=output,
            cache_read_tokens=cache_read,
            reasoning_tokens=reasoning,
        )


class FakeProvider(BaseProvider):
    """Подставной поставщик — доказательство сменяемости, а не заглушка.

    Существует ровно затем, чтобы «поставщик меняется настройкой» было
    проверяемым утверждением, а не обещанием: тесты гоняют весь слой
    целиком (ядро, профиль, разбор ответа, учёт расхода) без сети.
    """
    name = 'fake'

    def is_available(self):
        return True

    def unavailable_reason(self):
        return ''

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 images=None):
        from django.conf import settings

        self.last_images = list(images or [])
        reply = getattr(settings, 'AI_FAKE_REPLY', None)
        if callable(reply):
            reply = reply(system_blocks, user_text)
        if reply is None:
            reply = json.dumps({'rows': [], 'note': ''}, ensure_ascii=False)
        if isinstance(reply, Exception):
            raise ProviderError(str(reply))
        text = reply if isinstance(reply, str) else json.dumps(
            reply, ensure_ascii=False)
        return Reply(text=text,
                     input_tokens=len(' '.join(system_blocks)) // 4,
                     output_tokens=len(text) // 4)


PROVIDERS = {
    AnthropicProvider.name: AnthropicProvider,
    OpenAIProvider.name: OpenAIProvider,
    GLMProvider.name: GLMProvider,
    FakeProvider.name: FakeProvider,
}


def get_provider(name):
    """Поставщик по имени из настроек. Неизвестное имя — сразу и громко."""
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise KeyError('Неизвестный поставщик модели: %r. Доступны: %s'
                       % (name, ', '.join(sorted(PROVIDERS))))
