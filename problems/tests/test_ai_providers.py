# -*- coding: utf-8 -*-
"""OpenAIProvider — контракт, счётчики токенов и цена.

⚠️ НИ ОДНОГО СЕТЕВОГО ВЫЗОВА. Клиент подставной: настоящий `openai` в
окружении может быть даже не установлен, и это штатная ситуация —
провайдер обязан отдать is_available() = False, а не упасть.

Что здесь стережётся:
  - схема уходит в запрос СТРОГОЙ (strict), иначе «почти JSON» придётся
    разбирать руками на прогоне в 41 307 задач;
  - reasoning_effort берётся из настройки, а не зашит: рассуждение
    тарифицируется как выход, и на полном прогоне это +$74;
  - все ЧЕТЫРЕ счётчика токенов доезжают до AiUsageLog. Ноль в поле
    кэша неотличим от «кэш не сработал», а по нему принимается решение
    о Batch API;
  - цена считается по трёхэлементному кортежу, но двухэлементный
    продолжает работать.
"""
import base64
import sys
import types
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings

from problems.ai import core, providers
from problems.ai.providers import OpenAIProvider, ProviderError, Reply
from problems.models import AiUsageLog
from problems.tests.factories import make_user


SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}},
          'required': ['a'], 'additionalProperties': False}


class _FakeUsage(object):
    """Структура usage в том виде, в каком её отдаёт Responses API."""

    def __init__(self, input_tokens=1000, output_tokens=300,
                 cached_tokens=800, cache_write_tokens=0,
                 reasoning_tokens=120):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.input_tokens_details = types.SimpleNamespace(
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens)
        self.output_tokens_details = types.SimpleNamespace(
            reasoning_tokens=reasoning_tokens)


class _FakeResponse(object):
    def __init__(self, text='{"a": "ok"}', usage=None):
        self.output_text = text
        self.usage = usage if usage is not None else _FakeUsage()


class _FakeResponses(object):
    """Запоминает аргументы вызова — по ним и проверяется запрос."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self._response = response or _FakeResponse()
        self._error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeOpenAIClient(object):
    def __init__(self, responses):
        self.responses = responses


# ⚠️ Классы исключений объявлены ЗДЕСЬ, а не внутри фабрики модуля.
# `except openai.RateLimitError` ловит по идентичности класса: собери
# фабрика свои классы на каждый вызов — тот, которым бросили, и тот,
# которым ловят, оказались бы разными, и ветка отказа не сработала бы.
class FakeAPIConnectionError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


class FakeAPIStatusError(Exception):
    def __init__(self, message='', status_code=500):
        super(FakeAPIStatusError, self).__init__(message)
        self.status_code = status_code


def _fake_openai_module(responses):
    """Подставной модуль `openai` в sys.modules — пакета в окружении нет."""
    module = types.ModuleType('openai')
    module.APIConnectionError = FakeAPIConnectionError
    module.RateLimitError = FakeRateLimitError
    module.APIStatusError = FakeAPIStatusError
    module.OpenAI = lambda **kwargs: _FakeOpenAIClient(responses)
    return module


class _OpenAIMixin(object):
    """Подставляет модуль openai и ключ окружения на время теста."""

    def run_complete(self, responses, system_blocks=None, model='gpt-5.6-terra',
                     max_tokens=500):
        module = _fake_openai_module(responses)
        blocks = system_blocks if system_blocks is not None else ['я' * 8000]
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            return OpenAIProvider().complete(
                blocks, 'текст запроса', SCHEMA, model, max_tokens)


class RequestShapeTests(_OpenAIMixin, TestCase):
    """Что именно уходит в запрос."""

    def test_схема_уходит_строгой(self):
        responses = _FakeResponses()
        self.run_complete(responses)

        sent = responses.calls[0]['text']['format']
        self.assertIs(sent['strict'], True)
        self.assertEqual(sent['type'], 'json_schema')
        self.assertEqual(sent['schema'], SCHEMA)

    @override_settings(AI_REASONING_EFFORT='high')
    def test_уровень_рассуждения_берётся_из_настройки(self):
        responses = _FakeResponses()
        self.run_complete(responses)

        self.assertEqual(responses.calls[0]['reasoning'], {'effort': 'high'})

    @override_settings(AI_REASONING_EFFORT='none')
    def test_по_умолчанию_рассуждение_выключено(self):
        responses = _FakeResponses()
        self.run_complete(responses)

        self.assertEqual(responses.calls[0]['reasoning'], {'effort': 'none'})

    def test_короткое_ядро_даёт_предупреждение_в_журнал(self):
        # Кэш префикса у GPT-5.6 включается от 1024 токенов. Ядро короче —
        # скидки не будет вовсе, и нули в отчёте будут означать не «кэш не
        # сработал», а «кэшировать было нечего».
        responses = _FakeResponses()
        with self.assertLogs('problems.ai.providers', level='WARNING') as log:
            self.run_complete(responses, system_blocks=['короткое ядро'])
        self.assertIn('кэш', '\n'.join(log.output).lower())

    def test_длинное_ядро_молчит(self):
        responses = _FakeResponses()
        with mock.patch.object(providers.logger, 'warning') as warn:
            self.run_complete(responses, system_blocks=['я' * 8000])
        warn.assert_not_called()


class TokenCountTests(_OpenAIMixin, TestCase):
    """Четыре счётчика, а не два."""

    def test_все_четыре_счётчика_читаются_из_ответа(self):
        responses = _FakeResponses(_FakeResponse(usage=_FakeUsage(
            input_tokens=1000, output_tokens=300,
            cached_tokens=800, cache_write_tokens=64, reasoning_tokens=120)))
        reply = self.run_complete(responses)

        # ⚠️ Вход у OpenAI ПОЛНЫЙ, кэш сидит внутри него. Наружу отдаём
        # непересекающиеся значения, иначе _cost посчитает кэш дважды.
        self.assertEqual(reply.input_tokens, 200)
        self.assertEqual(reply.cache_read_tokens, 800)
        self.assertEqual(reply.output_tokens, 300)
        self.assertEqual(reply.cache_write_tokens, 64)
        self.assertEqual(reply.reasoning_tokens, 120)

    def test_сумма_входа_и_кэша_сходится_с_полным_входом(self):
        responses = _FakeResponses(_FakeResponse(usage=_FakeUsage(
            input_tokens=1000, cached_tokens=800)))
        reply = self.run_complete(responses)

        self.assertEqual(reply.input_tokens + reply.cache_read_tokens, 1000)

    def test_отсутствие_полей_кэша_не_роняет(self):
        # Старая версия SDK может не отдавать детали — нули, но не падение.
        usage = types.SimpleNamespace(input_tokens=50, output_tokens=10)
        reply = self.run_complete(_FakeResponses(_FakeResponse(usage=usage)))

        self.assertEqual(reply.input_tokens, 50)
        self.assertEqual(reply.cache_read_tokens, 0)
        self.assertEqual(reply.reasoning_tokens, 0)


class UsageLogTests(TestCase):
    """Счётчики доезжают до AiUsageLog, а не теряются по дороге."""

    def test_четыре_счётчика_попадают_в_журнал_расхода(self):
        user = make_user('teacher_ai', role='teacher')
        reply = Reply(text='{}', input_tokens=200, output_tokens=300,
                      cache_write_tokens=64, cache_read_tokens=800,
                      reasoning_tokens=120)

        core._log(user, 'enrich', 'openai', 'gpt-5.6-terra', reply, 1.0)

        row = AiUsageLog.objects.get(user=user)
        self.assertEqual(row.input_tokens, 200)
        self.assertEqual(row.output_tokens, 300)
        self.assertEqual(row.cache_read_tokens, 800)
        self.assertEqual(row.reasoning_tokens, 120)


class CostTests(TestCase):
    """Цена — три числа, но два тоже продолжают работать."""

    @override_settings(AI_PRICES={'gpt-5.6-terra': (2.00, 0.20, 12.00)})
    def test_кэш_считается_по_своей_цене_а_не_по_цене_входа(self):
        reply = Reply(text='{}', input_tokens=0, output_tokens=0,
                      cache_read_tokens=1_000_000)

        # Миллион кэш-токенов по $0.20 — ровно $0.20. По цене входа
        # вышло бы $2.00, вдесятеро дороже.
        self.assertEqual(core._cost('gpt-5.6-terra', reply),
                         Decimal('0.200000'))

    @override_settings(AI_PRICES={'gpt-5.6-terra': (2.00, 0.20, 12.00)})
    def test_вход_и_выход_считаются_по_своим_ценам(self):
        reply = Reply(text='{}', input_tokens=1_000_000,
                      output_tokens=1_000_000)

        self.assertEqual(core._cost('gpt-5.6-terra', reply),
                         Decimal('14.000000'))

    @override_settings(AI_PRICES={'old-model': (1.0, 5.0)})
    def test_двухэлементная_цена_продолжает_работать(self):
        # Обратная совместимость: старая запись (вход, выход) не должна
        # ронять расчёт — цена кэша выводится из цены входа.
        reply = Reply(text='{}', input_tokens=1_000_000,
                      output_tokens=1_000_000)

        self.assertEqual(core._cost('old-model', reply), Decimal('6.000000'))

    def test_две_и_три_цены_дают_одно_число_для_haiku(self):
        # (1.0, 5.0) и (1.0, 0.1, 5.0) обязаны совпасть: 1.0 × 0.1 = 0.1.
        reply = Reply(text='{}', input_tokens=1000, output_tokens=500,
                      cache_read_tokens=4000)

        with override_settings(AI_PRICES={'m': (1.0, 5.0)}):
            old = core._cost('m', reply)
        with override_settings(AI_PRICES={'m': (1.0, 0.1, 5.0)}):
            new = core._cost('m', reply)

        self.assertEqual(old, new)

    @override_settings(AI_PRICES={'gpt-5.6-terra': (2.00, 0.20, 12.00)})
    def test_рассуждение_не_тарифицируется_вторым_разом(self):
        # Токены рассуждения уже сидят внутри output_tokens. Прибавить их
        # отдельно значило бы заплатить за них дважды.
        without = Reply(text='{}', output_tokens=1_000_000,
                        reasoning_tokens=0)
        with_reasoning = Reply(text='{}', output_tokens=1_000_000,
                               reasoning_tokens=500_000)

        self.assertEqual(core._cost('gpt-5.6-terra', without),
                         core._cost('gpt-5.6-terra', with_reasoning))


class FailureTests(_OpenAIMixin, TestCase):
    """Отказы приводятся к ProviderError с человеческим текстом."""

    def _complete_with_error(self, error):
        responses = _FakeResponses(error=error)
        module = _fake_openai_module(responses)
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with self.assertRaises(ProviderError) as caught:
                OpenAIProvider().complete(
                    ['я' * 8000], 'текст', SCHEMA, 'gpt-5.6-terra', 500)
        return caught.exception

    def test_ключ_не_принят_даёт_no_key(self):
        error = FakeAPIStatusError('unauthorized', status_code=401)

        self.assertEqual(self._complete_with_error(error).kind, 'no_key')

    def test_лимит_частоты_даёт_limit(self):
        error = FakeRateLimitError('429')

        self.assertEqual(self._complete_with_error(error).kind, 'limit')

    def test_сервис_не_ответил_даёт_other(self):
        error = FakeAPIStatusError('server error', status_code=500)

        self.assertEqual(self._complete_with_error(error).kind, 'other')

    def test_прочая_ошибка_даёт_other(self):
        exception = self._complete_with_error(ValueError('что угодно'))

        self.assertEqual(exception.kind, 'other')

    def test_наружу_уходит_человеческий_текст_без_кода(self):
        exception = self._complete_with_error(ValueError('SSLError blah'))

        self.assertNotIn('SSLError', str(exception))
        self.assertIn('вручную', str(exception))


class AvailabilityTests(TestCase):
    """Пакета нет или ключа нет — выключаемся, а не падаем."""

    def test_без_пакета_не_падаем_а_отдаём_false(self):
        # Настоящий openai в окружении может быть не установлен —
        # ImportError не имеет права всплыть наружу.
        with mock.patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with mock.patch.dict(sys.modules, {'openai': None}):
                with mock.patch(
                        'builtins.__import__',
                        side_effect=ImportError('No module named openai')):
                    provider = OpenAIProvider()
                    self.assertFalse(provider.is_available())
                    self.assertIn('openai', provider.unavailable_reason())

    def test_без_ключа_недоступен_с_объяснением(self):
        with mock.patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            provider = OpenAIProvider()
            self.assertFalse(provider.is_available())
            self.assertIn('OPENAI_API_KEY', provider.unavailable_reason())


class RegistrationTests(TestCase):
    """Переключение — только настройкой, ни строчки продуктового кода."""

    def test_провайдер_зарегистрирован_под_именем_openai(self):
        self.assertIs(providers.PROVIDERS['openai'], OpenAIProvider)

    @override_settings(AI_PROVIDER='openai')
    def test_настройка_выбирает_провайдер(self):
        self.assertIsInstance(core._provider(), OpenAIProvider)


class OpenAIImageInputTests(TestCase):
    """Картинка задачи уходит в модель через тот же слой `problems/ai/`.

    Проверяется ровно то, что можно проверить без сети: как собирается
    поле `input` запроса. Сам запрос — дело `complete()`, у него свои
    тесты выше.
    """

    def setUp(self):
        self.provider = providers.OpenAIProvider()
        self.png = b'\x89PNG\r\n\x1a\n' + b'0' * 32

    def test_без_картинок_вход_остаётся_простой_строкой(self):
        """Не косметика: строка — ровно то, что уходило до правки. Смена
        формы входа на списке без картинок сломала бы кэш префикса на
        всех 41 307 задачах ради двух тысяч с картинкой."""
        payload = self.provider._input_payload('текст задачи', None)
        self.assertEqual(payload, 'текст задачи')
        self.assertEqual(self.provider._input_payload('текст', []), 'текст')

    def test_картинка_уходит_data_url_рядом_с_текстом(self):
        payload = self.provider._input_payload(
            'текст задачи', [('image/png', self.png)])

        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 1)
        content = payload[0]['content']
        self.assertEqual(payload[0]['role'], 'user')
        self.assertEqual(content[0], {'type': 'input_text',
                                      'text': 'текст задачи'})
        self.assertEqual(content[1]['type'], 'input_image')
        self.assertTrue(content[1]['image_url'].startswith(
            'data:image/png;base64,'))
        self.assertIn(base64.b64encode(self.png).decode('ascii'),
                      content[1]['image_url'])

    def test_несколько_картинок_идут_все(self):
        payload = self.provider._input_payload(
            'текст', [('image/png', self.png), ('image/jpeg', b'\xff\xd8ab')])
        kinds = [block['type'] for block in payload[0]['content']]
        self.assertEqual(kinds, ['input_text', 'input_image', 'input_image'])

    def test_неподдерживаемый_формат_отбрасывается(self):
        """`image/bmp` Responses API не принимает. Молча отправить его —
        значит получить отказ на боевом прогоне вместо ответа."""
        payload = self.provider._input_payload(
            'текст', [('image/bmp', b'BM..'), ('image/png', self.png)])
        kinds = [block['type'] for block in payload[0]['content']]
        self.assertEqual(kinds, ['input_text', 'input_image'])

    def test_если_все_картинки_отброшены_вход_снова_строка(self):
        payload = self.provider._input_payload('текст', [('image/bmp', b'BM')])
        self.assertEqual(payload, 'текст')

    def test_пустые_байты_не_отправляются(self):
        payload = self.provider._input_payload('текст', [('image/png', b'')])
        self.assertEqual(payload, 'текст')

    def test_подставной_поставщик_видит_картинки(self):
        """Контракт `complete(..., images=...)` общий для слоя, а не
        особенность одного поставщика."""
        fake = providers.FakeProvider()
        with override_settings(AI_FAKE_REPLY='{"ok": 1}'):
            fake.complete(['ядро'], 'текст', {}, 'm', 100,
                          images=[('image/png', self.png)])
        self.assertEqual(fake.last_images, [('image/png', self.png)])


class GLMImageInputTests(TestCase):
    """Фаза 0.1/0.4 подготовки боевого прогона (02.09.2026): реальным
    вызовом подтверждено, что GLM-5.3-Flash читает картинку (в `usage`
    появляются токены изображения, а описание совпадает с содержимым).
    Здесь — то же самое, что у `OpenAIImageInputTests`, но для формата
    `chat.completions` (`image_url`, а не `input_image`)."""

    def setUp(self):
        self.provider = providers.GLMProvider()
        self.png = b'\x89PNG\r\n\x1a\n' + b'0' * 32

    def test_без_картинок_вход_остаётся_простой_строкой(self):
        """Кэш префикса у GLM тоже зависит от неизменной формы входа —
        задачи без картинки не должны получить список из одного элемента
        вместо строки."""
        self.assertEqual(self.provider._user_content('текст задачи', None),
                         'текст задачи')
        self.assertEqual(self.provider._user_content('текст', []), 'текст')

    def test_картинка_уходит_data_url_рядом_с_текстом(self):
        content = self.provider._user_content(
            'текст задачи', [('image/png', self.png)])

        self.assertIsInstance(content, list)
        self.assertEqual(content[0], {'type': 'text', 'text': 'текст задачи'})
        self.assertEqual(content[1]['type'], 'image_url')
        url = content[1]['image_url']['url']
        self.assertTrue(url.startswith('data:image/png;base64,'))
        self.assertIn(base64.b64encode(self.png).decode('ascii'), url)

    def test_несколько_картинок_идут_все(self):
        content = self.provider._user_content(
            'текст', [('image/png', self.png), ('image/jpeg', b'\xff\xd8ab')])
        kinds = [block['type'] for block in content]
        self.assertEqual(kinds, ['text', 'image_url', 'image_url'])

    def test_неподдерживаемый_формат_отбрасывается(self):
        content = self.provider._user_content(
            'текст', [('image/bmp', b'BM..'), ('image/png', self.png)])
        kinds = [block['type'] for block in content]
        self.assertEqual(kinds, ['text', 'image_url'])

    def test_если_все_картинки_отброшены_вход_снова_строка(self):
        self.assertEqual(
            self.provider._user_content('текст', [('image/bmp', b'BM')]),
            'текст')

    def test_пустые_байты_не_отправляются(self):
        self.assertEqual(
            self.provider._user_content('текст', [('image/png', b'')]),
            'текст')
