"""
Поставщики модели. Смена — НАСТРОЙКОЙ, а не правкой кода продукта.

Наружу каждый поставщик отдаёт одно и то же: `complete(...) → Reply`.
Никакой продуктовый код здесь не появляется — иначе переезд на российскую
модель снова стал бы переписыванием, от которого этот слой и защищает.

Как переключить (`config/settings*.py`):

    AI_PROVIDER = 'anthropic'      # по умолчанию
    AI_MODEL = 'claude-haiku-4-5'
    AI_PRICES = {'claude-haiku-4-5': (1.0, 5.0)}   # $ за млн: вход, выход

Подставной поставщик для тестов:

    AI_PROVIDER = 'fake'
    AI_FAKE_REPLY = '{"rows": [...]}'   # или функция (profile, text) → str
"""
import json
import os


class Reply(object):
    """Ответ поставщика: текст плюс счётчики токенов."""

    def __init__(self, text, input_tokens=0, output_tokens=0,
                 cache_write_tokens=0, cache_read_tokens=0):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_write_tokens = cache_write_tokens
        self.cache_read_tokens = cache_read_tokens


class ProviderError(Exception):
    """Поставщик не смог ответить. Текст уже человеческий.

    ⚠️ У ОТКАЗА ЕСТЬ ВИД (`kind`) — сессия 7, фаза 7.4. Экран показывает
    репетитору не текст поставщика, а свой, зависящий от вида: «не настроен
    доступ» и «сервис не ответил» — это разные советы. Код ошибки
    (401/429/500) остаётся в журнале сервера и на экран не выходит: он
    ничего не говорит тому, кто собирает домашку.
    """

    def __init__(self, message, kind='other'):
        super(ProviderError, self).__init__(message)
        self.kind = kind


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

    def complete(self, system_blocks, user_text, schema, model, max_tokens):
        raise NotImplementedError


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
        except anthropic.APIConnectionError:
            raise ProviderError(
                'Не удалось связаться с сервисом разбора запроса. Проверьте '
                'сеть или соберите домашку вручную.')
        except anthropic.RateLimitError:
            raise ProviderError(
                'Сервис разбора сейчас перегружен. Попробуйте через минуту '
                'или соберите домашку вручную.')
        except anthropic.APIStatusError as error:
            # 401/403 — ключ не принят: это «не настроен доступ», а не
            # «сервис молчит», и совет репетитору другой.
            kind = 'no_key' if error.status_code in (401, 403) else 'other'
            raise ProviderError(
                'Сервис разбора вернул ошибку (%s).' % error.status_code,
                kind=kind)
        except Exception:
            # Библиотека может кинуть что угодно своё. Белого экрана у
            # репетитора быть не должно ни при какой ошибке.
            raise ProviderError(
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

    def complete(self, system_blocks, user_text, schema, model, max_tokens):
        from django.conf import settings

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
    FakeProvider.name: FakeProvider,
}


def get_provider(name):
    """Поставщик по имени из настроек. Неизвестное имя — сразу и громко."""
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise KeyError('Неизвестный поставщик модели: %r. Доступны: %s'
                       % (name, ', '.join(sorted(PROVIDERS))))
