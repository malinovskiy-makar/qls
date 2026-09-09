# -*- coding: utf-8 -*-
"""OpenRouterProvider — контракт, счётчики токенов и стоимость из usage.

⚠️ НИ ОДНОГО СЕТЕВОГО ВЫЗОВА. Клиент подставной, как и в
`test_ai_providers.py`: настоящий `openai` может быть не установлен, и
провайдер обязан ответить `is_available() = False`, а не упасть.

Что здесь стережётся:
  - модель — ПАРАМЕТР ВЫЗОВА, а не константа класса: у посредника один
    ключ на семь моделей, и весь смысл слоя в том, чтобы гонять их одним
    кодом;
  - в запрос уходит `usage: {include: true}` — без него OpenRouter НЕ
    вернёт стоимость, и жёсткий счётчик бюджета сессии считать будет
    нечем;
  - `Reply.cost_usd` = None, когда посредник стоимость не прислал.
    Ноль здесь означал бы «бесплатно» и молча занижал бы счётчик — а
    отличать «не знаем» от «бесплатно» обязательно, бюджет жёсткий;
  - все четыре счётчика токенов доезжают, включая `reasoning_tokens`:
    у OpenRouter он лежит в `completion_tokens_details`, как у Z.AI, а
    не в `output_tokens_details`, как у OpenAI Responses API.
"""
import sys
import types
from unittest import mock

from django.test import TestCase

from problems.ai.providers import OpenRouterProvider, ProviderError


class _FakeUsage(object):
    def __init__(self, prompt_tokens=1000, completion_tokens=300,
                 cached_tokens=200, reasoning_tokens=120, cost=None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = types.SimpleNamespace(
            cached_tokens=cached_tokens)
        self.completion_tokens_details = types.SimpleNamespace(
            reasoning_tokens=reasoning_tokens)
        if cost is not None:
            self.cost = cost


class _FakeMessage(object):
    def __init__(self, content):
        self.content = content


class _FakeChoice(object):
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse(object):
    def __init__(self, text='{"a": "ok"}', usage=None):
        self.choices = [_FakeChoice(text)]
        self.usage = usage if usage is not None else _FakeUsage()


class _FakeCompletions(object):
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response if self.response is not None else _FakeResponse()


class _FakeClient(object):
    def __init__(self, completions):
        self.chat = types.SimpleNamespace(completions=completions)


class FakeAPIConnectionError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


class FakeAPIStatusError(Exception):
    def __init__(self, message='', status_code=500):
        super(FakeAPIStatusError, self).__init__(message)
        self.status_code = status_code


def _fake_openai_module(completions):
    module = types.ModuleType('openai')
    module.OpenAI = lambda **kwargs: _FakeClient(completions)
    module.last_client_kwargs = {}

    def factory(**kwargs):
        module.last_client_kwargs = kwargs
        return _FakeClient(completions)

    module.OpenAI = factory
    module.APIConnectionError = FakeAPIConnectionError
    module.RateLimitError = FakeRateLimitError
    module.APIStatusError = FakeAPIStatusError
    return module


class _Mixin(object):
    def run_complete(self, completions, model='z-ai/glm-5.3-flash'):
        module = _fake_openai_module(completions)
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'OPENROUTER_API_KEY': 'k-test'}):
            reply = OpenRouterProvider().complete(
                system_blocks=['ты судья'], user_text='вот пул',
                schema={'type': 'object'}, model=model, max_tokens=512,
                timeout=30)
        return reply, completions.kwargs, module


class AvailabilityTests(TestCase):
    def test_без_ключа_недоступен(self):
        with mock.patch.dict('os.environ', {'OPENROUTER_API_KEY': ''}):
            self.assertFalse(OpenRouterProvider().is_available())
            self.assertIn('OPENROUTER_API_KEY',
                          OpenRouterProvider().unavailable_reason())

    def test_базовый_адрес_ведёт_на_openrouter(self):
        self.assertEqual(OpenRouterProvider.BASE_URL,
                         'https://openrouter.ai/api/v1')

    def test_имя_переменной_с_ключом_одно_на_все_модели(self):
        self.assertEqual(OpenRouterProvider.key_env, 'OPENROUTER_API_KEY')


class RequestShapeTests(_Mixin, TestCase):
    def test_модель_приходит_параметром_вызова(self):
        _, kwargs, _ = self.run_complete(_FakeCompletions(),
                                         model='deepseek/deepseek-v4-pro')
        self.assertEqual(kwargs['model'], 'deepseek/deepseek-v4-pro')

    def test_стоимость_запрашивается_явно(self):
        # Без usage.include OpenRouter стоимость не присылает вовсе.
        _, kwargs, _ = self.run_complete(_FakeCompletions())
        self.assertEqual(kwargs['extra_body']['usage'], {'include': True})

    def test_ключ_и_адрес_уходят_в_клиента(self):
        _, _, module = self.run_complete(_FakeCompletions())
        self.assertEqual(module.last_client_kwargs['api_key'], 'k-test')
        self.assertEqual(module.last_client_kwargs['base_url'],
                         'https://openrouter.ai/api/v1')

    def test_таймаут_доезжает_до_запроса(self):
        _, kwargs, _ = self.run_complete(_FakeCompletions())
        self.assertEqual(kwargs['timeout'], 30)


class UsageTests(_Mixin, TestCase):
    def test_стоимость_читается_из_usage(self):
        reply, _, _ = self.run_complete(
            _FakeCompletions(_FakeResponse(usage=_FakeUsage(cost=0.01234))))
        self.assertAlmostEqual(reply.cost_usd, 0.01234)

    def test_без_стоимости_поле_none_а_не_ноль(self):
        reply, _, _ = self.run_complete(
            _FakeCompletions(_FakeResponse(usage=_FakeUsage())))
        self.assertIsNone(reply.cost_usd)

    def test_четыре_счётчика_токенов_читаются(self):
        reply, _, _ = self.run_complete(_FakeCompletions(_FakeResponse(
            usage=_FakeUsage(prompt_tokens=1000, completion_tokens=300,
                             cached_tokens=200, reasoning_tokens=120))))
        self.assertEqual(reply.input_tokens, 800)   # полный вход минус кэш
        self.assertEqual(reply.cache_read_tokens, 200)
        self.assertEqual(reply.output_tokens, 300)
        self.assertEqual(reply.reasoning_tokens, 120)

    def test_текст_ответа_достаётся_из_первого_варианта(self):
        reply, _, _ = self.run_complete(
            _FakeCompletions(_FakeResponse(text='{"12": 2}')))
        self.assertEqual(reply.text, '{"12": 2}')


class FailureTests(_Mixin, TestCase):
    def run_error(self, error):
        module = _fake_openai_module(_FakeCompletions(error=error))
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'OPENROUTER_API_KEY': 'k-test'}):
            with self.assertRaises(ProviderError) as caught:
                OpenRouterProvider().complete(
                    system_blocks=['s'], user_text='u', schema={},
                    model='z-ai/glm-5.3-flash', max_tokens=10)
        return caught.exception

    def test_ключ_не_принят_даёт_no_key(self):
        self.assertEqual(self.run_error(
            FakeAPIStatusError(status_code=401)).kind, 'no_key')

    def test_лимит_частоты_даёт_limit(self):
        self.assertEqual(self.run_error(FakeRateLimitError()).kind, 'limit')

    def test_сеть_не_ответила_даёт_other(self):
        self.assertEqual(self.run_error(
            FakeAPIConnectionError()).kind, 'other')

    def test_сырое_исключение_сохраняется_для_журнала_отказов(self):
        # Урок run2: журнал только успехов сделал полтора часа отказов
        # неразбираемыми. Код и тело ответа обязаны дожить до журнала.
        error = self.run_error(FakeAPIStatusError(status_code=429))
        self.assertIsInstance(error.original, FakeAPIStatusError)
        self.assertEqual(error.original.status_code, 429)
