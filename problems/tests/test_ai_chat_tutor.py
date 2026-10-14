"""Сессия «Чат-репетитор, правки 1» (14.10.2026, ADR 0148): слой ИИ.

* ни один поставщик не повторяет запрос сам (`max_retries=0`), таймаут и
  обрыв связи — свои виды отказа;
* `core.run(log=False)` не пишет журнал и на отказе поставщика;
* сбой разбора — строка `ok=False`, но с ценой; личный лимит не тратится;
* ответ без схемы — текстом; обрыв по длине и пустой ответ — свои виды;
* `CORE` не изменился, `TUTOR_CORE` — только у чата;
* уровень рассуждения чата не задевает умный поиск и обогащение;
* тексты ошибок узнаёт отчёт беты.

Сети нет: настоящий клиент `openai` получает подставной транспорт httpx.
"""
import hashlib
import json
import sys
import types
from unittest import mock

import httpx2 as httpx   # транспорт `openai` 3.x
import openai
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from problems.ai import core, prompts, providers
from problems.ai_beta import metrics
from problems.models import AiUsageLog
from problems.tests.factories import make_user

#: sha256 общего ядра `CORE` на 14.10.2026. Чат ушёл на своё ядро, а `CORE`
#: живёт у всех остальных работ (план домашки, темы, проверка, OCR…) — его
#: правка меняла бы их поведение и сбрасывала кэш. Меняете `CORE` нарочно —
#: обновите число и запишите, зачем.
CORE_SHA256 = '3235c2d7d226d0fb213b1812d5d2162f63710c342128b68812792e8bef910cc3'

SCHEMA = {'type': 'object', 'properties': {'reply': {'type': 'string'}}}


# ── Нет скрытых повторов ────────────────────────────────────────────────

class _Counter:
    """Подставной HTTP: считает запросы, отвечает 500 или таймаутом."""

    def __init__(self, mode):
        self.mode = mode
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        if self.mode == 'timeout':
            raise httpx.ReadTimeout('нет ответа', request=request)
        return httpx.Response(500, json={'error': {'message': 'сервер упал'}})


class NoHiddenRetriesTests(SimpleTestCase):
    """Один вопрос — один запрос к поставщику, и на таймауте, и на 500.

    Настоящая библиотека `openai` (по умолчанию повторяет ещё дважды) с
    подставным транспортом: тест краснеет, если у клиента пропадёт
    `max_retries=0`."""

    PROVIDERS = (
        (providers.OpenAIProvider, 'OPENAI_API_KEY'),
        (providers.GLMProvider, 'GLM_API_KEY'),
        (providers.DeepSeekProvider, 'DEEPSEEK_API_KEY'),
        (providers.OpenRouterProvider, 'OPENROUTER_API_KEY'),
    )

    def _call(self, cls, env, counter):
        real = openai.OpenAI

        def client(**kwargs):
            return real(http_client=httpx.Client(transport=httpx.MockTransport(counter)),
                        **kwargs)
        with mock.patch.object(openai, 'OpenAI', client), \
                mock.patch.dict('os.environ', {env: 'test-key'}), \
                self.assertRaises(providers.ProviderError) as caught:
            cls().complete(['ядро'], 'вопрос', SCHEMA, 'm', 100, timeout=5)
        return caught.exception

    def test_library_would_retry_by_default(self):
        # Сторож самого теста: если библиотека перестанет повторять по
        # умолчанию, проверка ниже ничего не докажет.
        self.assertGreater(openai.DEFAULT_MAX_RETRIES, 0)

    def test_timeout_is_one_call_and_kind_timeout(self):
        for cls, env in self.PROVIDERS:
            with self.subTest(provider=cls.name):
                counter = _Counter('timeout')
                error = self._call(cls, env, counter)
                self.assertEqual(counter.calls, 1, 'скрытый повтор на таймауте')
                self.assertEqual(error.kind, 'timeout')
                self.assertIn('занял больше 5 секунд', str(error))
                self.assertNotIn('домашк', str(error))

    def test_server_error_is_one_call(self):
        for cls, env in self.PROVIDERS:
            with self.subTest(provider=cls.name):
                counter = _Counter('500')
                error = self._call(cls, env, counter)
                self.assertEqual(counter.calls, 1, 'скрытый повтор на 500')
                self.assertEqual(error.kind, 'other')

    def test_anthropic_client_is_built_without_retries(self):
        # Пакета anthropic в окружении нет — проверяем, с чем создаётся клиент.
        made = {}

        class Timeout(Exception):
            pass

        def create(**_kwargs):
            raise Timeout()

        def client(**kwargs):
            made.update(kwargs)
            return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        module = types.ModuleType('anthropic')
        module.Anthropic = client
        module.APITimeoutError = Timeout
        module.APIConnectionError = Timeout
        module.RateLimitError = module.APIStatusError = type('E', (Exception,), {})
        with mock.patch.dict(sys.modules, {'anthropic': module}), \
                mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'k'}), \
                self.assertRaises(providers.ProviderError):
            providers.AnthropicProvider().complete(['ядро'], 'вопрос', SCHEMA, 'm', 100)
        self.assertEqual(made.get('max_retries'), 0)


# ── Подставной поставщик со своим ответом ───────────────────────────────

class Scripted:
    """Поставщик-заглушка: отвечает `Reply` или бросает исключение; помнит вызовы."""

    name = 'fake'

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def is_available(self):
        return True

    def unavailable_reason(self):
        return ''

    def complete(self, system_blocks, user_text, schema, model, max_tokens, timeout=None,
                 images=None, **kwargs):
        self.calls.append(dict(kwargs, system=list(system_blocks), schema=schema,
                               timeout=timeout))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def reply(text, finish_reason=None):
    return providers.Reply(text, input_tokens=1000, output_tokens=500,
                           finish_reason=finish_reason)


@override_settings(AI_PRICES={'m': (1.0, 0.1, 5.0)}, AI_GENERATOR_DAILY_LIMIT=30)
class CoreRunTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('ученик_ядро')

    def run_core(self, provider, schema=SCHEMA, **kwargs):
        kwargs.setdefault('cache_seconds', 0)
        return core.run('catalog_chat', 'вопрос', schema, self.user, provider=provider,
                        model='m', system=['ядро'], **kwargs)

    def test_provider_failure_with_log_false_writes_nothing(self):
        failing = Scripted(providers.ProviderError('сервис лёг', kind='timeout'))
        with self.assertRaises(core.AiUnavailable) as caught:
            self.run_core(failing, log=False, check_budget=False)
        self.assertEqual(AiUsageLog.objects.count(), 0)
        self.assertEqual(caught.exception.kind, 'timeout')
        self.assertFalse(caught.exception.usage['ok'])     # сведения — вызывающему

    def test_provider_failure_with_log_true_is_still_logged(self):
        with self.assertRaises(core.AiUnavailable):
            self.run_core(Scripted(providers.ProviderError('сервис лёг')))
        self.assertEqual(list(AiUsageLog.objects.values_list('ok', flat=True)), [False])

    def test_format_failure_keeps_money_and_spares_the_personal_limit(self):
        with self.assertRaises(core.AiUnavailable) as caught:
            self.run_core(Scripted(reply('это не JSON')))
        error = caught.exception
        self.assertEqual(error.kind, 'format')
        self.assertIn('неожиданный ответ', str(error))
        self.assertNotIn('домашк', str(error))
        self.assertGreater(error.usage['cost_usd'], 0)
        row = AiUsageLog.objects.get()
        self.assertFalse(row.ok)
        self.assertGreater(row.cost_usd, 0)
        self.assertEqual(core.used_today(self.user), 0)    # личный лимит не тронут
        self.assertGreater(core.spent_today('catalog_chat'), 0)   # деньги видны потолку

    def test_text_without_schema_comes_back_as_a_string(self):
        provider = Scripted(reply('  Начните с $MR = MC$.  '))
        result = self.run_core(provider, schema=None)
        self.assertEqual(result.data, 'Начните с $MR = MC$.')
        self.assertIsNone(provider.calls[0]['schema'])
        self.assertTrue(AiUsageLog.objects.get().ok)

    def test_cut_by_length_is_its_own_kind(self):
        for schema in (None, SCHEMA):
            with self.subTest(schema=bool(schema)):
                with self.assertRaises(core.AiUnavailable) as caught:
                    self.run_core(Scripted(reply('{"reply": "оборв', 'length')), schema=schema)
                self.assertEqual(caught.exception.kind, 'length')
                self.assertGreater(caught.exception.usage['cost_usd'], 0)

    def test_empty_text_is_its_own_kind(self):
        with self.assertRaises(core.AiUnavailable) as caught:
            self.run_core(Scripted(reply('   ')), schema=None)
        self.assertEqual(caught.exception.kind, 'empty')

    def test_reasoning_reaches_the_provider_only_when_given(self):
        provider = Scripted(reply('ok'))
        self.run_core(provider, schema=None)
        self.run_core(provider, schema=None, reasoning='high')
        self.assertNotIn('reasoning', provider.calls[0])
        self.assertEqual(provider.calls[1]['reasoning'], 'high')


# ── GLM без схемы и с уровнем на вызов ─────────────────────────────────

class GLMRequestTests(SimpleTestCase):
    def _sent(self, schema, reasoning=None, finish='stop'):
        sent = {}

        class Completions:
            def create(self, **kwargs):
                sent.update(kwargs)
                return types.SimpleNamespace(
                    usage=None, choices=[types.SimpleNamespace(
                        message=types.SimpleNamespace(content='ответ'),
                        finish_reason=finish)])
        fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()))
        with mock.patch.object(openai, 'OpenAI', lambda **kw: fake), \
                mock.patch.dict('os.environ', {'GLM_API_KEY': 'k'}):
            got = providers.GLMProvider().complete(['ядро'], 'вопрос', schema, 'glm-5.3', 100,
                                                   reasoning=reasoning)
        return sent, got

    def test_without_schema_no_json_is_asked(self):
        sent, got = self._sent(None)
        self.assertNotIn('response_format', sent)
        self.assertNotIn('JSON', sent['messages'][0]['content'])
        self.assertEqual(got.text, 'ответ')

    def test_with_schema_json_is_asked_as_before(self):
        sent, _got = self._sent(SCHEMA)
        self.assertEqual(sent['response_format'], {'type': 'json_object'})
        self.assertIn('ОТВЕЧАЙ РОВНО ОДНИМ JSON', sent['messages'][0]['content'])

    @override_settings(AI_REASONING_EFFORT='none', CATALOG_CHAT_REASONING='max')
    def test_reasoning_per_call_and_global_default(self):
        sent, _got = self._sent(None)
        self.assertEqual(sent['extra_body']['reasoning_effort'], 'low')   # глобальное none → low
        sent, _got = self._sent(None, reasoning='high')
        self.assertEqual(sent['extra_body']['reasoning_effort'], 'high')

    def test_finish_reason_is_read(self):
        _sent, got = self._sent(None, finish='length')
        self.assertEqual(got.finish_reason, 'length')


# ── Ядра ────────────────────────────────────────────────────────────────

class CoresTests(SimpleTestCase):
    def test_core_is_unchanged(self):
        self.assertEqual(hashlib.sha256(prompts.CORE.encode('utf-8')).hexdigest(), CORE_SHA256)

    def test_tutor_core_only_for_the_chat(self):
        for profile in prompts.PROFILES:
            with self.subTest(profile=profile):
                first = prompts.system_blocks(profile)[0]
                self.assertEqual(first, prompts.TUTOR_CORE if profile == 'catalog_chat'
                                 else prompts.CORE)
        self.assertNotIn('Ты не источник знаний', prompts.TUTOR_CORE)
        # Ссылки на правила общего ядра у чата больше не к чему.
        self.assertNotIn('ядра', prompts.PROFILES['catalog_chat'])
        self.assertNotIn('Верни только `reply`', prompts.PROFILES['catalog_chat'])


# ── Уровень рассуждения чата не задевает поиск и обогащение ────────────

@override_settings(CATALOG_CHAT_REASONING='max', CATALOG_CHAT_MAX_TOKENS=9999,
                   CATALOG_CHAT_TIMEOUT_SECONDS=44)
class ChatSettingsStayInTheChatTests(TestCase):
    def test_rerank_gets_neither_reasoning_nor_chat_limits(self):
        from catalog import rerank

        provider = Scripted(reply(json.dumps({'scores': {'1': 9, '2': 3}})))
        provider.name = 'glm'
        rows = {1: {'id': 1, 'title': 'а'}, 2: {'id': 2, 'title': 'б'}}
        with mock.patch.object(rerank, '_get_provider', return_value=provider), \
                mock.patch.object(rerank, 'card', side_effect=lambda row, *a: row['title']):
            rerank._score_pool('монополия', [1, 2], rows, timeout=7)
        (call,) = provider.calls
        self.assertNotIn('reasoning', call)
        self.assertEqual(call['timeout'], 7)

    def test_enrichment_pilot_reads_only_the_global_level(self):
        from problems.management.commands import pilot_enrich_v2 as pilot

        seen = {}

        def complete(self, *args, **kwargs):
            from django.conf import settings
            seen['effort'] = settings.AI_REASONING_EFFORT
            seen['reasoning'] = kwargs.get('reasoning')
            return reply('{}')
        with mock.patch.object(providers.OpenAIProvider, 'complete', complete):
            pilot.make_openai_complete_fn()('m', ['ядро'], 'текст', SCHEMA, 'low')
        self.assertEqual(seen, {'effort': 'low', 'reasoning': None})

    def test_enrichment_retries_new_kinds(self):
        from problems.management.commands import pilot_enrich_v2 as pilot

        for kind in ('timeout', 'network'):
            self.assertIn(kind, pilot.RETRYABLE_PROVIDER_ERROR_KINDS)


# ── Тексты ошибок узнаёт отчёт беты ─────────────────────────────────────

class ErrorTextsAreRecognisedTests(SimpleTestCase):
    def test_each_text_maps_to_its_kind(self):
        cases = (
            ('timeout', providers.BaseProvider._timeout_text(45), 'timeout'),
            ('network', providers.BaseProvider.NETWORK_TEXT, 'network'),
            ('format', core.FORMAT_TEXT, 'format'),
            ('empty', core.EMPTY_TEXT, 'empty'),
            ('length', core.LENGTH_TEXT, 'length'),
        )
        for kind, text, expected in cases:
            with self.subTest(kind=kind):
                # Так `chat.answer_turn` пишет `ChatTurn.error`.
                self.assertEqual(metrics.error_kind('%s: %s' % (kind, text)), expected)
                self.assertNotIn('домашк', text)

    def test_old_texts_still_map_as_before(self):
        old = (('other: Разбор запроса вернул неожиданный ответ. Попробуйте описать домашку '
                'иначе или соберите её вручную.', 'format'),
               ('other: Помощник не ответил. Попробуйте спросить иначе.', 'empty'),
               ('other: Не удалось связаться с сервисом разбора запроса. Проверьте сеть или '
                'соберите домашку вручную.', 'network'),
               ('other: Ответ занял больше 25 секунд и прерван. Попробуйте отправить ещё раз.',
                'timeout'))
        for text, expected in old:
            self.assertEqual(metrics.error_kind(text), expected)


class BrokenFormulaOnPlainTextTests(SimpleTestCase):
    """Метрика «испорченная формула» ловила след JSON-экранирования; на
    ответе текстом нормальные формулы не должны в неё попадать."""

    def test_plain_tex_is_not_broken(self):
        text = (r'Выручка $TR = P \times Q$, доля $\frac{1}{2}$, $\text{MR} = \theta$, '
                r'$\tau$, $\left(a\right)$, $\rho$, $\beta$, $\rangle$.' '\n\tОтступ табом.')
        self.assertFalse(metrics.is_broken_formula(text))

    def test_json_damage_is_still_caught(self):
        # Модель писала в JSON `\times` одним слешем — разбор делал из него табуляцию.
        damaged = json.loads(r'{"reply": "$P \times Q$, $\frac{1}{2}$"}')['reply']
        self.assertTrue(metrics.is_broken_formula(damaged))
