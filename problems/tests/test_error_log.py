# -*- coding: utf-8 -*-
"""Журнал отказов API + лог консоли (Фаза 1-2, 04.09.2026, разбор
run2-corpus-20260904).

`append_raw_log` пишется только из `on_row` — то есть только после
успеха. Отказ, отбитый сервером, бросает исключение и до записи не
доходит: полтора часа отказов `400 code 1210` не оставили ни одной
строки нигде (`RUN2_POSTMORTEM.md`, раздел 5). Здесь проверяется
обратное — каждая неудачная попытка (даже закрывшаяся повтором)
оставляет след, запись в журнал сама не роняет прогон, и равенство
«манифест = обработано + пропущено + невосстановленные» держится даже
когда часть задач падает навсегда.

Провайдер подделан через `sys.modules['openai']` — тот же приём, что и
в `test_ai_providers.py` (`_OpenAIMixin`): `except openai.APIStatusError`
внутри `GLMProvider.complete()` ловит по идентичности класса, поэтому
поддельный модуль подставляется целиком, а не мокается отдельный вызов.
"""
import json
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from problems.ai import providers
from problems.enrich import prompts_v2
from problems.management.commands import glm_enrich_run as run_cmd
from problems.management.commands import pilot_enrich_v2 as pilot
from problems.models import Problem
from problems.tests.test_glm_enrich_run import (VALID_CALL2_JSON, _FakeReply,
                                                _valid_call1_json)


class FakeAPIConnectionError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


class FakeAPIStatusError(Exception):
    """Как `FakeAPIStatusError` в `test_ai_providers.py`, плюс `body` —
    туда Z.AI кладёт код `1210` (`{'error': {'code': '1210', ...}}`)."""

    def __init__(self, message='', status_code=500, body=None):
        super(FakeAPIStatusError, self).__init__(message)
        self.status_code = status_code
        self.body = body


class _FakeUsage(object):
    def __init__(self):
        self.prompt_tokens = 100
        self.completion_tokens = 50
        self.prompt_tokens_details = types.SimpleNamespace(cached_tokens=0)
        self.completion_tokens_details = types.SimpleNamespace(reasoning_tokens=0)


def _fake_chat_response(text):
    message = types.SimpleNamespace(content=text)
    choice = types.SimpleNamespace(message=message)
    return types.SimpleNamespace(choices=[choice], usage=_FakeUsage())


def _fake_openai_module(create_fn):
    """Подставной модуль `openai` под контракт `chat.completions.create`
    (GLMProvider), не Responses API (OpenAIProvider у `test_ai_providers.py`)."""
    module = types.ModuleType('openai')
    module.APIConnectionError = FakeAPIConnectionError
    module.RateLimitError = FakeRateLimitError
    module.APIStatusError = FakeAPIStatusError

    completions = types.SimpleNamespace(create=create_fn)
    chat = types.SimpleNamespace(completions=completions)
    client = types.SimpleNamespace(chat=chat)
    module.OpenAI = lambda **kwargs: client
    return module


SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}}}


class GlmCompleteFnErrorLogTests(TestCase):
    """`make_glm_complete_fn` — журналирует каждую неудачную попытку до
    решения о повторе (тесты 1 и 2 из плана фазы 3)."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.error_log = self.tmp_dir / 'errors.jsonl'

    def _run(self, create_fn, problem_id=1, call='call1'):
        complete_fn = run_cmd.make_glm_complete_fn(
            error_log_path=str(self.error_log), run_id='r-test',
            prompt_version='pv-test')
        module = _fake_openai_module(create_fn)
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'GLM_API_KEY': 'test-glm-key'}), \
                mock.patch('time.sleep'):
            with pilot.call_error_context(
                    problem_id=problem_id, call=call, prompt_chars=123,
                    has_image=False, solution_sent=True):
                return complete_fn('glm-5.3-flash', ['core'], 'user',
                                   SCHEMA, 'high')

    def _lines(self):
        if not self.error_log.exists():
            return []
        return [json.loads(l) for l in
               self.error_log.read_text(encoding='utf-8').splitlines() if l]

    def test_один_обрыв_сети_потом_успех(self):
        """Заглушка падает один раз, потом отвечает нормально: в журнале
        ровно одна строка с attempt=1, will_retry=true; задача в
        результате есть; прогон не падает."""
        calls = {'n': 0}

        def create_fn(**kwargs):
            calls['n'] += 1
            if calls['n'] == 1:
                raise FakeAPIConnectionError('обрыв сети')
            return _fake_chat_response('{"ok": true}')

        reply = self._run(create_fn, problem_id=42, call='call1')

        self.assertEqual(reply.text, '{"ok": true}')
        lines = self._lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['attempt'], 1)
        self.assertIs(lines[0]['will_retry'], True)
        self.assertEqual(lines[0]['problem_id'], 42)
        self.assertEqual(lines[0]['call'], 'call1')
        self.assertEqual(lines[0]['error_class'], 'FakeAPIConnectionError')

    def test_код_1210_на_всех_попытках(self):
        """Заглушка падает `BadRequestError` с `code=1210` на ВСЕХ
        попытках: строк в журнале отказов столько же, сколько попыток;
        задача — в списке невосстановленных (исключение уходит наверх);
        прогон (сам вызов) не падает необработанно — исключение штатное
        `providers.ProviderError`."""
        def create_fn(**kwargs):
            raise FakeAPIStatusError(
                'Invalid API parameter', status_code=400,
                body={'error': {'code': '1210', 'message': 'Invalid API parameter'}})

        with self.assertRaises(providers.ProviderError):
            self._run(create_fn, problem_id=7, call='call2')

        lines = self._lines()
        self.assertEqual(len(lines), pilot.NETWORK_RETRIES)
        self.assertTrue(all(l['api_code'] == '1210' for l in lines))
        self.assertTrue(all(l['http_status'] == 400 for l in lines))
        self.assertTrue(all(l['error_class'] == 'FakeAPIStatusError' for l in lines))
        self.assertTrue(all(l['will_retry'] for l in lines[:-1]))
        self.assertIs(lines[-1]['will_retry'], False)
        self.assertTrue(all(l['call'] == 'call2' for l in lines))

    def test_журнал_не_содержит_ключ_api(self):
        """Ключ поставщика нигде в строке журнала — ни в message, ни в
        остальных полях (требование 6 плана фазы 3)."""
        secret = 'sk-super-secret-glm-key-do-not-leak'

        def create_fn(**kwargs):
            raise FakeAPIStatusError('unauthorized', status_code=401)

        module = _fake_openai_module(create_fn)
        complete_fn = run_cmd.make_glm_complete_fn(
            error_log_path=str(self.error_log), run_id='r-secret',
            prompt_version='pv-test')
        with mock.patch.dict(sys.modules, {'openai': module}), \
                mock.patch.dict('os.environ', {'GLM_API_KEY': secret}), \
                mock.patch('time.sleep'):
            with pilot.call_error_context(problem_id=1, call='call1',
                                          prompt_chars=10, has_image=False,
                                          solution_sent=False):
                with self.assertRaises(providers.ProviderError):
                    complete_fn('glm-5.3-flash', ['core'], 'user', SCHEMA, 'high')

        raw = self.error_log.read_text(encoding='utf-8')
        self.assertNotIn(secret, raw)


class Call2FailureContextTests(TestCase):
    """Отказ ИМЕННО в call2 при успешном call1 — контекст журнала не
    путает вызовы (тест 3 из плана фазы 3)."""

    def test_отказ_в_call2_не_путает_call1(self):
        problem = Problem.objects.create(
            statement='Утка стоит X рублей, спрос линейный, найдите равновесие.')
        tmp = Path(tempfile.mkdtemp())
        error_log = tmp / 'errors.jsonl'
        schema1 = prompts_v2.call1_schema(with_concepts=True)
        schema2 = prompts_v2.CALL2_SCHEMA

        def complete_fn(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            if is_call1:
                return _FakeReply(_valid_call1_json(user_text))
            error = providers.ProviderError('сервис перегружен', kind='other')
            pilot.append_error_log(str(error_log), 'r-call2', 'pv-test',
                                   1, error, False)
            raise error

        variant = {'call1_model': 'glm-5.3-flash', 'call1_effort': 'high',
                  'call2_model': 'glm-5.3-flash', 'call2_effort': 'high',
                  'concepts': True}

        with self.assertRaises(providers.ProviderError):
            pilot._process_one_problem(
                problem, variant, complete_fn, {}, with_tikz=True,
                core1_blocks=['core1'], core2_blocks=['core2'],
                schema1=schema1, schema2=schema2)

        lines = [json.loads(l) for l in
                error_log.read_text(encoding='utf-8').splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['call'], 'call2')
        self.assertEqual(lines[0]['problem_id'], problem.id)
        self.assertNotIn('call1', [l['call'] for l in lines])


class AppendErrorLogSwallowsWriteFailureTests(TestCase):
    """Запись в журнал отказов сама не должна ронять прогон (тест 4 из
    плана фазы 3)."""

    def test_ошибка_записи_журнала_проглатывается_с_одной_строкой(self):
        error = providers.ProviderError('обрыв', kind='other')

        printed = []
        with mock.patch.object(pilot, 'open',
                               side_effect=OSError('диск недоступен'), create=True), \
                mock.patch('builtins.print', side_effect=lambda *a, **k: printed.append(a)):
            # Не должно бросить исключение — вот и весь тест.
            pilot.append_error_log('/несуществующий/путь/errors.jsonl',
                                   'r-fail', 'pv', 1, error, True)

        self.assertEqual(len(printed), 1)


class ManifestInvariantTests(TestCase):
    """Равенство «манифест = обработано + пропущено + невосстановленные»
    на синтетическом манифесте из 10 задач, где 2 падают навсегда (тест 5
    из плана фазы 3). Проверяется через файлы прогона, а не парсингом
    консоли — устойчивее к правкам текста сообщений."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.problems = [
            Problem.objects.create(statement='Задача номер %d про рынок.' % i)
            for i in range(10)
        ]
        self.raw_path = self.tmp_dir / 'run_raw.jsonl'
        self.parsed_path = self.tmp_dir / 'run_parsed.jsonl'
        self.metrics_path = self.tmp_dir / 'run_metrics.json'
        self.manifest_path = self.tmp_dir / 'run300_sample_ids.json'
        self.battle_manifest_path = self.tmp_dir / 'run_full_sample_ids.json'

    def _patch_paths(self):
        return mock.patch.multiple(
            run_cmd,
            RAW_LOG_PATH=self.raw_path,
            PARSED_LOG_PATH=self.parsed_path,
            METRICS_PATH=self.metrics_path,
            SAMPLE_MANIFEST_PATH=self.manifest_path,
            BATTLE_MANIFEST_PATH=self.battle_manifest_path,
        )

    def test_равенство_держится_с_двумя_вечно_падающими_задачами(self):
        doomed_ids = {self.problems[0].id, self.problems[1].id}

        def fake_complete(model, blocks, user_text, schema, effort, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            # По тексту задачи узнаём, какая это — id ещё не виден на
            # этом уровне, но текст содержит номер по порядку создания.
            for pid in doomed_ids:
                marker = 'номер %d про' % (pid - self.problems[0].id)
                if marker in user_text:
                    raise providers.ProviderError('перегружено', kind='other')
            return _FakeReply(_valid_call1_json(user_text) if is_call1
                              else VALID_CALL2_JSON)

        with self._patch_paths(), \
                mock.patch.object(run_cmd, 'make_glm_complete_fn',
                                  return_value=fake_complete):
            call_command('glm_enrich_run', limit=len(self.problems),
                        max_cost=100.0, workers=1, run_id='r-invariant')

        metrics = json.loads(self.metrics_path.read_text(encoding='utf-8'))
        total_processed = metrics['total_processed']

        unrecovered_path = self.tmp_dir / 'r-invariant_unrecovered_ids.txt'
        self.assertTrue(unrecovered_path.exists())
        unrecovered_ids = [
            int(l) for l in unrecovered_path.read_text(encoding='utf-8').splitlines()
            if l and not l.startswith('#')]

        self.assertEqual(set(unrecovered_ids), doomed_ids)
        self.assertEqual(len(self.problems),
                         total_processed + len(unrecovered_ids))
