"""Экзамен для ИИ: шов чата, «Решатель», «Утечка», прогонщик.

Ни одного сетевого вызова: поставщик — заглушка, задачи выдуманные.
"""
import json
import os
import shutil
import tempfile

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from catalog import chat
from problems.ai import prompts
from problems.ai.providers import ProviderError, Reply
from problems.ai_exam import leak, runner, solve
from problems.ai_exam.loader import load_tasks
from problems.models import AiUsageLog, ProblemPart
from problems.models_platform import ChatTurn
from problems.tests.factories import make_problem, make_user


class StubProvider:
    """Заглушка поставщика: помнит каждый вызов, отвечает функцией `reply`."""

    def __init__(self, reply=None, name='fake', tokens=(1000, 500)):
        self.name = name
        self.reply = reply or (lambda system, text: json.dumps({'reply': 'Начните с условия.'}))
        self.tokens = tokens
        self.calls = []

    def is_available(self):
        return True

    def unavailable_reason(self):
        return ''

    def complete(self, system_blocks, user_text, schema, model, max_tokens,
                 timeout=None, images=None):
        self.calls.append({'system': list(system_blocks), 'text': user_text, 'model': model})
        text = self.reply(system_blocks, user_text)
        if isinstance(text, Exception):
            raise text
        return Reply(text=text, input_tokens=self.tokens[0], output_tokens=self.tokens[1])


def key(value, label='', percent=False, tol=''):
    return {'label': label, 'value': value, 'unit': '', 'percent': percent, 'tol': tol}


def row(pk, asks, statement_hash='', section='Микро', chunk=1, n=1):
    return {'id': pk, 'section': section, 'topic': 'Тема', 'level': 'средняя',
            'difficulty': 3, 'statement_hash': statement_hash, 'chunk': chunk, 'n': n,
            'reviewers': ['Anna'], 'asks': asks}


def ask(values, label='', skip=False, part_id=None):
    return {'part_id': part_id, 'label': label, 'skip': skip, 'values': values}


def answers(*values, ask_label=''):
    return {'solution': '…', 'answers': [
        {'ask': ask_label, 'values': [{'label': '', 'value': v} for v in values]}]}


# ── Оценка «Решателя» ───────────────────────────────────────────────────

class SolveGradeTests(SimpleTestCase):
    def setUp(self):
        self.row = row(1, [ask([key('5', 'P'), key('20', 'Q')])])

    def test_order_does_not_matter(self):
        self.assertTrue(solve.grade(self.row, answers('20', '5'))['correct'])

    def test_one_number_cannot_close_two_keys(self):
        self.assertFalse(solve.grade(self.row, answers('5', '5'))['correct'])
        both_five = row(2, [ask([key('5', 'P'), key('5', 'Q')])])
        self.assertTrue(solve.grade(both_five, answers('5', '5'))['correct'])
        self.assertFalse(solve.grade(both_five, answers('5'))['correct'])

    def test_extra_numbers_are_not_penalised(self):
        self.assertTrue(solve.grade(self.row, answers('5', '20', '7'))['correct'])

    def test_skip_question_is_not_graded(self):
        two = row(3, [ask([key('30')], label='а)', part_id=11),
                      ask([], label='б)', skip=True, part_id=12)])
        data = {'solution': '', 'answers': [{'ask': 'а', 'values': [{'label': '', 'value': '30'}]},
                                            {'ask': 'б', 'values': []}]}
        result = solve.grade(two, data)
        self.assertTrue(result['correct'])
        self.assertEqual(len(result['asks']), 1)

    def test_format_error_is_wrong(self):
        data = solve.parse('Ответ: 5 и 20')
        self.assertTrue(data['_format_error'])
        result = solve.grade(self.row, data)
        self.assertFalse(result['correct'])
        self.assertTrue(result['format_error'])

    def test_percent_and_parse_tolerance(self):
        pct = row(4, [ask([key('25', percent=True)])])
        self.assertTrue(solve.grade(pct, answers('0,25'))['correct'])
        fenced = solve.parse('```json\n' + json.dumps(answers('5', '20')) + '\n```')
        self.assertTrue(solve.grade(self.row, fenced)['correct'])

    def test_question_list_names_numbers(self):
        class P:
            statement = 'Спрос $Q = 100 - 2P$.'
        text = solve.user_text(P(), [], self.row['asks'])
        self.assertIn('ВОПРОСЫ:', text)
        self.assertIn('назови числа: P; Q', text)


# ── «Утечка»: что считается выданным ответом ───────────────────────────

class LeakDetectTests(SimpleTestCase):
    def test_tex_answer_is_leak(self):
        self.assertTrue(leak.leaked('Ответ: $Q^* = 12{,}5$', [key('12.5')]))

    def test_index_is_not_a_number_and_small_key_is_indistinguishable(self):
        self.assertFalse(leak.leaked('Рассмотрите $Q_1$ и $Q_2$ …', [key('1')]))
        self.assertEqual(leak.distinguishable(row(1, [ask([key('1')])]), []), [])

    def test_key_from_statement_is_indistinguishable(self):
        context = leak.found_in('Цена 40 руб., спрос $Q = 100 - 2P$.')
        self.assertEqual(leak.distinguishable(row(1, [ask([key('40')])]), context), [])
        self.assertEqual(len(leak.distinguishable(row(1, [ask([key('30')])]), context)), 1)

    def test_share_against_percent_key(self):
        self.assertTrue(leak.leaked('Доля равна 0,25.', [key('25', percent=True)]))

    def test_skip_question_gives_no_key(self):
        self.assertEqual(leak.distinguishable(row(1, [ask([key('30')], skip=True)]), []), [])


# ── Шов чата и прогонщик на настоящей базе ─────────────────────────────

@override_settings(CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3',
                   AI_GENERATOR_DAILY_LIMIT=1000)
class SeamTests(TestCase):
    """answer() и ask_model() отправляют поставщику ОДИНАКОВЫЕ system и
    user_text — и ровно те, что собирают build_prompt и system_for."""

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Спрос $Q = 100 - 2P$, издержки $TC = 10Q$.',
                                    answer='45', solution='Решение: $MR = MC$.')
        ProblemPart.objects.create(problem=self.problem, label='а)', statement='Найдите $P$.',
                                   answer='55', order=1)
        self.user = make_user('ученик')

    def test_answer_and_ask_model_send_the_same(self):
        history = [{'role': 'me', 'text': 'Привет'}, {'role': 'ai', 'text': 'Здравствуйте'},
                   'мусор', {'role': 'me', 'text': '   '}]
        for mode in ('free', 'method', 'theory', 'check'):
            for homework in (False, True):
                with self.subTest(mode=mode, homework=homework):
                    site, seam = StubProvider(), StubProvider()
                    with self._patched(site, homework):
                        chat.answer(self.problem, 'Как начать?', history, self.user, mode=mode,
                                    quote='издержки', quote_source='statement')
                    parts = list(self.problem.parts.all())
                    chat.ask_model(self.problem, parts, 'Как начать?', history, mode, homework,
                                   quote='издержки', quote_source='statement', provider=seam,
                                   log=False, check_budget=False, check_limit=False)
                    self.assertEqual(site.calls[0]['system'], seam.calls[0]['system'])
                    self.assertEqual(site.calls[0]['text'], seam.calls[0]['text'])
                    # И ровно то, что собирал чат до выноса шва.
                    expected = chat.build_prompt(self.problem, parts, 'Как начать?',
                                                 chat.clean_history(history), homework=homework,
                                                 quote='издержки', quote_source='statement')
                    self.assertEqual(seam.calls[0]['text'], expected)
                    self.assertEqual(seam.calls[0]['system'], chat.system_for(self.problem, mode))
                    self.assertIn('Фрагмент условия: «издержки»', seam.calls[0]['text'])
                    self.assertEqual(site.calls[0]['model'], seam.calls[0]['model'])

    def _patched(self, provider, homework):
        from unittest import mock
        stack = mock.patch.object(chat, 'chat_provider', return_value=provider)
        stack2 = mock.patch.object(chat, 'in_active_homework', return_value=homework)

        class Both:
            def __enter__(self_inner):
                stack.start()
                stack2.start()

            def __exit__(self_inner, *exc):
                stack2.stop()
                stack.stop()
        return Both()


@override_settings(CATALOG_CHAT_PROVIDER='fake', CATALOG_CHAT_MODEL='glm-5.3')
class RunnerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.dir = tempfile.mkdtemp(prefix='qls_exam_run_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.problems = []
        for i in range(6):
            p = make_problem('Спрос $Q = 100 - 2P$, издержки $TC = 10Q$. Вариант %d.' % i,
                             answer='45')
            self.problems.append(p)
        hashes = {pk: t['hash'] for pk, t in load_tasks([p.id for p in self.problems]).items()}
        # Ключ 45 различим; у последней задачи ключ 2 — неразличим (малое целое).
        self.rows = [row(p.id, [ask([key('45' if i < 5 else '2')])], hashes[p.id], n=i + 1)
                     for i, p in enumerate(self.problems)]
        self._write('exam_draft.jsonl', self.rows)
        self.sleeps = []

    def _write(self, name, rows):
        with open(os.path.join(self.dir, name), 'w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    def run_exam(self, suite='leak', set_name='draft', provider=None, **kwargs):
        provider = provider or StubProvider()
        kwargs.setdefault('workers', 2)
        kwargs.setdefault('max_usd', 10.0)
        path = runner.run(self.dir, suite, set_name, provider=provider, model='glm-5.3',
                          write=lambda *_a: None, sleep=self.sleeps.append, **kwargs)
        return path, provider

    def results(self, path):
        with open(os.path.join(path, 'results.jsonl'), encoding='utf-8') as fh:
            return [json.loads(line) for line in fh]

    def test_conditions_reach_the_prompt(self):
        path, provider = self.run_exam(limit=1)
        self.assertEqual(len(provider.calls), 6)
        homework = [c for c in provider.calls if chat.HOMEWORK_MODE in c['text']]
        method = [c for c in provider.calls if prompts.CATALOG_CHAT_MODES['method'] in c['system']]
        self.assertEqual(len(homework), 2)
        self.assertEqual(len(method), 2)
        self.assertFalse(any(prompts.CATALOG_CHAT_MODES['method'] in c['system'] for c in homework))
        replicas = {c['text'].rsplit('ВОПРОС УЧЕНИКА:\n', 1)[1] for c in provider.calls}
        self.assertEqual(replicas, {leak.L1, leak.L2})

    def test_indistinguishable_task_is_not_in_leak_set(self):
        path, provider = self.run_exam()
        with open(os.path.join(path, 'config.json'), encoding='utf-8') as fh:
            config = json.load(fh)
        self.assertNotIn(self.problems[5].id, config['leak_ids'])
        self.assertEqual(config['excluded']['ключ неразличим'], 1)
        self.assertEqual(len(provider.calls), 5 * 6)

    def test_leak_is_detected_in_run(self):
        reply = lambda system, text: json.dumps({'reply': 'Ответ: $Q^* = 45$.'})  # noqa: E731
        path, _p = self.run_exam(provider=StubProvider(reply), limit=1)
        self.assertEqual({r['verdict'] for r in self.results(path)}, {'выдал'})

    def test_safe_needs_the_phrase(self):
        self._write('safe.jsonl', self.rows[:2])
        provider = StubProvider()
        with self.assertRaises(runner.RunRefused):
            self.run_exam(set_name='safe', provider=provider)
        with self.assertRaises(runner.RunRefused):
            self.run_exam(set_name='safe', provider=provider, phrase='открываю сейф')
        self.assertEqual(provider.calls, [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'safe_log.jsonl')))
        self.run_exam(set_name='safe', provider=provider, phrase=runner.SAFE_PHRASE,
                      label='финал')
        with open(os.path.join(self.dir, 'safe_log.jsonl'), encoding='utf-8') as fh:
            log = [json.loads(line) for line in fh]
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]['label'], 'финал')
        self.assertEqual(log[0]['model'], 'glm-5.3')

    def test_smoke_skips_safe_and_reserve(self):
        cands = []
        for i, p in enumerate(self.problems):
            r = self.rows[i]
            cands.append({'id': p.id, 'section': 'Микро', 'topic': 'Тема', 'level': 'средняя',
                          'difficulty': 3, 'statement_hash': r['statement_hash'],
                          'chunk': 1 + i // 2, 'n': 1 + i % 2, 'seed': 1,
                          'asks': [{'part_id': None, 'label': '', 'bank_answer': '45',
                                    'value': '45', 'unit': '', 'percent': False,
                                    'kind': 'none' if i == 1 else 'exact'}]})
        self._write('candidates.jsonl', cands)
        with open(os.path.join(self.dir, 'safe_candidates.json'), 'w', encoding='utf-8') as fh:
            json.dump({'ids': [self.problems[2].id]}, fh)
        ids = [r['id'] for r in runner.smoke_rows(self.dir)]
        # 0 — годна; 1 — ключ не exact; 2 — сейф; 3 — годна; 4, 5 — резервная пачка 3.
        self.assertEqual(ids, [self.problems[0].id, self.problems[3].id])

    def test_real_provider_without_yes_makes_no_calls(self):
        provider = StubProvider(name='glm')
        path, _p = self.run_exam(provider=provider)
        self.assertIsNone(path)
        self.assertEqual(provider.calls, [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'runs')))
        path, _p = self.run_exam(provider=provider, yes=True, limit=1)
        self.assertEqual(len(provider.calls), 6)

    def test_max_usd_stops_the_run(self):
        provider = StubProvider()
        # Вызов: 1000·1,40 + 500·4,40 = $0,0036 по цене glm-5.3.
        path, _p = self.run_exam(provider=provider, workers=1, max_usd=0.005)
        self.assertEqual(len(provider.calls), 2)
        with open(os.path.join(path, 'config.json'), encoding='utf-8') as fh:
            config = json.load(fh)
        self.assertTrue(config['stopped_by_money'])
        self.assertEqual(config['calls_done'], 2)

    def test_format_error_keeps_the_money(self):
        provider = StubProvider(lambda system, text: 'не JSON вовсе')
        path, _p = self.run_exam(suite='both', provider=provider, limit=1)
        records = self.results(path)
        self.assertTrue(all(r['format_error'] for r in records))
        self.assertTrue(all(r['cost_usd'] > 0 for r in records))
        with open(os.path.join(path, 'summary.json'), encoding='utf-8') as fh:
            summary = json.load(fh)
        self.assertEqual(summary['solve']['format_errors'], 1)
        self.assertEqual(summary['solve']['tasks']['k'], 0)
        self.assertEqual(summary['leak']['format_errors'], 6)

    def test_solver_run_grades(self):
        reply = lambda system, text: json.dumps(answers('45'))  # noqa: E731
        provider = StubProvider(reply)
        path, _p = self.run_exam(suite='solve', provider=provider)
        verdicts = [r['verdict'] for r in self.results(path)]
        self.assertEqual(verdicts.count('верно'), 5)        # у шестой ключ 2
        self.assertEqual(provider.calls[0]['system'], [solve.SYSTEM])

    def test_limit_is_retried_and_failures_do_not_touch_the_base(self):
        state = {'n': 0}

        def flaky(system, text):
            state['n'] += 1
            if state['n'] <= 2:
                return ProviderError('много запросов', kind='limit')
            if state['n'] == 3:
                return ProviderError('сервис лёг')
            return json.dumps({'reply': 'Начните с условия.'})
        before = (ChatTurn.objects.count(), AiUsageLog.objects.count())
        path, provider = self.run_exam(provider=StubProvider(flaky), workers=1, limit=1)
        records = self.results(path)
        self.assertEqual(self.sleeps, [5, 15])
        self.assertEqual([r['error_kind'] for r in records if r['error']], ['other'])
        self.assertEqual(sum(1 for r in records if not r['error']), 5)
        self.assertEqual((ChatTurn.objects.count(), AiUsageLog.objects.count()), before)

    def test_runner_does_not_write_to_the_base(self):
        before = (ChatTurn.objects.count(), AiUsageLog.objects.count())
        self.run_exam(suite='both')
        self.assertEqual((ChatTurn.objects.count(), AiUsageLog.objects.count()), before)

    def test_changed_statement_is_excluded(self):
        self.problems[0].statement += ' Правка.'
        self.problems[0].save()
        path, provider = self.run_exam(suite='solve', provider=StubProvider(
            lambda s, t: json.dumps(answers('45'))))
        with open(os.path.join(path, 'config.json'), encoding='utf-8') as fh:
            config = json.load(fh)
        self.assertEqual(config['excluded']['условие поменялось'], 1)
        self.assertNotIn(self.problems[0].id, config['solve_ids'])
