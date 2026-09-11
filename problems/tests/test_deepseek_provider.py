# -*- coding: utf-8 -*-
"""DeepSeekProvider — контракт и счётчики токенов.

⚠️ НИ ОДНОГО СЕТЕВОГО ВЫЗОВА, клиент подставной — как в соседних
`test_ai_providers.py` и `test_openrouter_provider.py`.

Отдельный класс, а не `GLMProvider` с другим адресом: GLM обязательно
шлёт `thinking` и `reasoning_effort`, DeepSeek такие поля не принимает.
Один класс на двоих означал бы ветвление по адресу внутри — то самое
«поставщик знает, кто он», от которого слой и защищает.

Что здесь стережётся:
  - кэш входа читается из `prompt_cache_hit_tokens`, а НЕ из
    `prompt_tokens_details.cached_tokens`, как у OpenAI и Z.ai: у DeepSeek
    своя схема поля, и молчаливый ноль в кэше сделал бы смету неверной;
  - `prompt_tokens` у DeepSeek — ПОЛНЫЙ вход, попадание кэша сидит внутри
    него, поэтому свежий вход считается вычитанием;
  - схема уходит текстом в системном сообщении: `json_schema` DeepSeek не
    поддерживает, только `json_object`.
"""
import sys
import types
from unittest import mock

from django.test import TestCase

from problems.ai.providers import DeepSeekProvider, ProviderError


class _FakeUsage(object):
    def __init__(self, prompt_tokens=1000, completion_tokens=300,
                 cache_hit=200, reasoning_tokens=0):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_cache_hit_tokens = cache_hit
        self.completion_tokens_details = types.SimpleNamespace(
            reasoning_tokens=reasoning_tokens)


class _FakeResponse(object):
    def __init__(self, text='{"a": "ok"}', usage=None):
        self.choices = [types.SimpleNamespace(
            message=types.SimpleNamespace(content=text))]
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
    module.last_client_kwargs = {}

    def factory(**kwargs):
        module.last_client_kwargs = kwargs
        return types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=completions))

    module.OpenAI = factory
    module.APIConnectionError = FakeAPIConnectionError
    module.RateLimitError = FakeRateLimitError
    module.APIStatusError = FakeAPIStatusError
    return module


class _Mixin(object):
    def run_complete(self, completions, model='deepseek-v4-pro'):
        module = _fake_openai_module(completions)
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'k-test'}):
            reply = DeepSeekProvider().complete(
                system_blocks=['ты судья'], user_text='вот пул',
                schema={'type': 'object'}, model=model, max_tokens=512,
                timeout=30)
        return reply, completions.kwargs, module


class AvailabilityTests(TestCase):
    def test_без_ключа_недоступен(self):
        with mock.patch.dict('os.environ', {'DEEPSEEK_API_KEY': ''}):
            self.assertFalse(DeepSeekProvider().is_available())
            self.assertIn('DEEPSEEK_API_KEY',
                          DeepSeekProvider().unavailable_reason())

    def test_имя_переменной_с_ключом(self):
        self.assertEqual(DeepSeekProvider.key_env, 'DEEPSEEK_API_KEY')

    def test_базовый_адрес_ведёт_на_deepseek(self):
        self.assertEqual(DeepSeekProvider.BASE_URL, 'https://api.deepseek.com')


class RequestShapeTests(_Mixin, TestCase):
    def test_модель_приходит_параметром_вызова(self):
        _, kwargs, _ = self.run_complete(_FakeCompletions(),
                                         model='deepseek-flash')
        self.assertEqual(kwargs['model'], 'deepseek-flash')

    def test_ответ_просят_json_объектом(self):
        _, kwargs, _ = self.run_complete(_FakeCompletions())
        self.assertEqual(kwargs['response_format'], {'type': 'json_object'})

    def test_схема_уходит_текстом_в_системном_сообщении(self):
        _, kwargs, _ = self.run_complete(_FakeCompletions())
        system = kwargs['messages'][0]
        self.assertEqual(system['role'], 'system')
        self.assertIn('JSON-СХЕМЕ', system['content'])

    def test_поля_thinking_от_glm_здесь_нет(self):
        # `thinking` — форма Z.AI. Слать её DeepSeek незачем: у него свой
        # ключ, и это одна из причин, по которой класс отдельный.
        _, kwargs, _ = self.run_complete(_FakeCompletions())
        self.assertNotIn('thinking', kwargs.get('extra_body') or {})

    def test_уровень_рассуждения_берётся_из_настройки(self):
        # ⚠️ Замерено на живой пачке из 25 карточек 10.09.2026: с
        # рассуждением выход 5 902 токена, без него 359. Это разница
        # между $10,45 и $4,25 на полном прогоне судьи — то есть между
        # «не помещается в потолок» и «помещается».
        _, kwargs, _ = self.run_complete(_FakeCompletions())
        self.assertEqual(kwargs['extra_body']['reasoning_effort'], 'none')

    def test_настройка_уровня_рассуждения_уважается(self):
        from django.test import override_settings
        with override_settings(AI_REASONING_EFFORT='high'):
            _, kwargs, _ = self.run_complete(_FakeCompletions())
        self.assertEqual(kwargs['extra_body']['reasoning_effort'], 'high')


class UsageTests(_Mixin, TestCase):
    def test_кэш_читается_из_своего_поля(self):
        reply, _, _ = self.run_complete(_FakeCompletions(_FakeResponse(
            usage=_FakeUsage(prompt_tokens=1000, cache_hit=200))))
        self.assertEqual(reply.cache_read_tokens, 200)
        self.assertEqual(reply.input_tokens, 800)

    def test_без_поля_кэша_не_роняет(self):
        usage = _FakeUsage()
        del usage.prompt_cache_hit_tokens
        reply, _, _ = self.run_complete(_FakeCompletions(
            _FakeResponse(usage=usage)))
        self.assertEqual(reply.cache_read_tokens, 0)
        self.assertEqual(reply.input_tokens, 1000)

    def test_выход_и_рассуждение_читаются(self):
        reply, _, _ = self.run_complete(_FakeCompletions(_FakeResponse(
            usage=_FakeUsage(completion_tokens=300, reasoning_tokens=120))))
        self.assertEqual(reply.output_tokens, 300)
        self.assertEqual(reply.reasoning_tokens, 120)

    def test_стоимость_провайдер_не_называет(self):
        # DeepSeek цену в ответе не присылает — считаем по прайсу.
        reply, _, _ = self.run_complete(_FakeCompletions())
        self.assertIsNone(reply.cost_usd)


class FailureTests(_Mixin, TestCase):
    def run_error(self, error):
        module = _fake_openai_module(_FakeCompletions(error=error))
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'k-test'}):
            with self.assertRaises(ProviderError) as caught:
                DeepSeekProvider().complete(
                    system_blocks=['s'], user_text='u', schema={},
                    model='deepseek-v4-pro', max_tokens=10)
        return caught.exception

    def test_ключ_не_принят_даёт_no_key(self):
        self.assertEqual(self.run_error(
            FakeAPIStatusError(status_code=401)).kind, 'no_key')

    def test_лимит_частоты_даёт_limit(self):
        self.assertEqual(self.run_error(FakeRateLimitError()).kind, 'limit')

    def test_сырое_исключение_доживает_до_журнала(self):
        error = self.run_error(FakeAPIStatusError(status_code=429))
        self.assertEqual(error.original.status_code, 429)
