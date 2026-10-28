"""Экзамен v1 из эталона: ключи, отбор, загрузчик, судья, сейф, потолок денег.

Только выдуманные строки эталона: настоящий экзамен в репозиторий не попадает
(ADR 0134, 0149). Без базы и без сети — `SimpleTestCase`, поставщик `fake`.
"""
import json
import os
import tempfile

from django.test import SimpleTestCase, override_settings

from problems.ai import core, providers
from problems.ai_exam import judge, reference, v1run


def ref_row(**kw):
    row = {'event_id': 'mosh-2099-final-9-v1', 'number': '1', 'task_variant': '',
           'academic_year': '2025/26', 'stage': 'final', 'grade': '9',
           'statement_md': 'Фирма продаёт товар по цене 10 д.е., издержки TC = Q^2. '
                           'Найдите оптимальный выпуск фирмы.',
           'parts': [], 'tables': 0, 'figures': [], 'solution_md': '', 'answer': '',
           'criteria_md': '', 'max_score': 10, 'needs_eyes': False, 'numbers_ok': True}
    row.update(kw)
    return row


class KeyExtractionTests(SimpleTestCase):
    def test_answer_line_in_solution_gives_key(self):
        row = ref_row(solution_md='MC = 2Q = 10.\n\n**Ответ:** Q = 5 шт.')
        asks, source = reference.key_for(row)
        self.assertEqual(source, 'solution')
        self.assertEqual(asks[0]['values'][0]['value'], '5')
        self.assertEqual(asks[0]['values'][0]['label'], 'Q')

    def test_empty_answer_line_takes_next_line(self):
        self.assertEqual(reference.answer_lines('**Ответ:**\n\n42 руб.'), ['42 руб.'])

    def test_formula_inequality_or_text_is_not_a_key(self):
        for text in ('Q = 50 - 0,5P', 'P > 25', '32 или 40', 'выпуск вырастет',
                     'от 10 до 20'):
            self.assertIsNone(reference.segment_value(text), text)

    def test_percent_and_unit_tail(self):
        self.assertEqual(reference.segment_value('снизится на 12%'), None)
        value = reference.segment_value('12 %')
        self.assertEqual((value['value'], value['percent']), ('12', True))
        self.assertEqual(reference.segment_value('70 тыс. руб.')['value'], '70')

    def test_parts_get_their_own_numbers(self):
        row = ref_row(parts=[{'label': 'а', 'text': 'x'}, {'label': 'б', 'text': 'y'}],
                      answer='а) 12; б) 30')
        asks, _ = reference.key_for(row)
        self.assertEqual([(a['label'], a['values'][0]['value']) for a in asks],
                         [('а', '12'), ('б', '30')])

    def test_one_number_for_many_subquestions_is_rejected(self):
        row = ref_row(statement_md='Условие задачи про фирму и рынок.\n\n- А) Найдите выпуск.\n'
                                   '- Б) Найдите прибыль.', answer='25')
        self.assertEqual(reference.key_for(row), (None, ''))

    def test_bold_letter_subquestions_are_seen(self):
        row = ref_row(statement_md='Условие задачи про фирму и рынок.\n\n- **А) (5 баллов)** '
                                   'Найдите выпуск.\n- **Б) (5 баллов)** Найдите прибыль.',
                      answer='25')
        self.assertEqual(reference.key_for(row), (None, ''))


class ExclusionTests(SimpleTestCase):
    def test_reasons_in_order(self):
        self.assertEqual(reference.exclusion(ref_row(number='тест-3')), 'тест')
        self.assertEqual(reference.exclusion(ref_row(needs_eyes=True, figures=[{}])), 'needs_eyes')
        self.assertEqual(reference.exclusion(ref_row(numbers_ok=False)), 'numbers_ok=false')
        self.assertEqual(reference.exclusion(ref_row(figures=[{'path': 'x.png'}])),
                         'рисунок в условии')
        self.assertEqual(reference.exclusion(ref_row(statement_md='  ')), 'пустое условие')
        self.assertEqual(reference.exclusion(ref_row(statement_md='Инструкция для участников')),
                         'служебный блок')
        self.assertEqual(reference.exclusion(ref_row()), '')

    def test_numbers_ok_none_is_not_excluded(self):
        self.assertEqual(reference.exclusion(ref_row(numbers_ok=None)), '')

    def test_choice_by_option_number_and_by_option_value(self):
        options = '\n\n- $1/9$\n- $1/10$\n- $3/28$\n- $1/11$'
        statement = 'Какая часть добычи достанется капитану при таком дележе добычи?' + options
        self.assertTrue(reference.is_choice(ref_row(statement_md=statement, answer='1/10')))
        self.assertTrue(reference.is_choice(ref_row(statement_md=statement, answer='[2]')))
        rows = ('\n\n| | |\n|---|---|\n| 1 | Прав. |\n| 2 | Не прав, другое. |\n'
                '| 3 | Нельзя сказать. |')
        self.assertTrue(reference.is_choice(ref_row(
            statement_md='Что можно сказать о мнении критика о выгоде проекта?' + rows,
            answer='3')))

    def test_choose_all_numbers_among_options(self):
        statement = ('При каком объёме выпуска фирма будет добывать по первой технологии '
                     'не менее 3 единиц?\n\n- 4\n- 10\n- 18\n- 20')
        self.assertTrue(reference.is_choice(ref_row(statement_md=statement, answer='4; 10; 20')))

    def test_plain_numeric_task_is_not_choice(self):
        self.assertFalse(reference.is_choice(ref_row(answer='5')))


class BuildTests(SimpleTestCase):
    def rows(self):
        out = []
        for n in range(40):
            year = '2025/26' if n % 2 else '2015/16'
            out.append(ref_row(event_id='mosh-20%02d-final-9-v1' % n, number=str(n),
                               academic_year=year, answer=str(n + 3)))
            out.append(ref_row(event_id='vp-20%02d-final-11-v1' % n, number=str(n),
                               academic_year=year,
                               solution_md='Решение. ' + 'Подробный разбор. ' * 30,
                               criteria_md='2 балла за ответ' if n % 3 else ''))
        return out

    def test_deterministic_and_no_overlap(self):
        first = reference.build(self.rows(), n_a=10, n_b=10, safe_a=2, safe_b=2)
        second = reference.build(self.rows(), n_a=10, n_b=10, safe_a=2, safe_b=2)
        self.assertEqual(reference.dumps(first[0]), reference.dumps(second[0]))
        self.assertEqual(reference.dumps(first[1]), reference.dumps(second[1]))
        work, safe = first[0], first[1]
        self.assertEqual((len(work), len(safe)), (16, 4))
        self.assertFalse({r['key'] for r in work} & {r['key'] for r in safe})
        self.assertGreaterEqual(sum(r['fresh'] for r in work + safe) / 20, 0.4)

    def test_key_is_event_number_variant(self):
        self.assertEqual(reference.row_key(ref_row(task_variant='2')),
                         'mosh-2099-final-9-v1:1:2')


class LoaderTests(SimpleTestCase):
    def test_task_like_bank_problem(self):
        row = reference.exam_row(ref_row(
            statement_md='Условие. 1) Найдите цену. 2) Найдите выпуск.',
            parts=[{'label': '1', 'text': 'Найдите цену.'}, {'label': '2', 'text': 'Новое.'}],
            solution_md='Решение длинное.', criteria_md='3 балла'), 'B')
        task = reference.Task(row)
        parts = task.parts.all()
        self.assertEqual([p.label for p in parts], ['1', '2'])
        # Текст пункта, уже стоящий в условии, второй раз не повторяется.
        self.assertEqual(parts[0].statement, '')
        self.assertEqual(parts[1].statement, 'Новое.')
        self.assertIn('КРИТЕРИИ', task.solution)
        self.assertEqual(task.rubrics.all(), [])
        text = v1run.user_text_b(task)
        self.assertEqual(text.count('Найдите цену.'), 1)
        self.assertIn('ПУНКТЫ: 1, 2', text)


JUDGE_REPLY = json.dumps({
    'parts': [{'label': 'а', 'points_awarded': 6, 'points_max': 10, 'verdict': 'partial',
               'reasons': 'нет проверки второго порядка', 'quote': 'Q = 5'},
              {'label': 'б', 'points_awarded': 12, 'points_max': 10, 'verdict': 'correct',
               'reasons': 'верно', 'quote': ''}],
    'total': 99, 'max': 20, 'confidence': 'high', 'reference_suspect': False,
    'reference_reason': ''}, ensure_ascii=False)


class JudgeTests(SimpleTestCase):
    row = reference.exam_row(ref_row(solution_md='Официальное решение.', max_score=20), 'B')

    @override_settings(AI_FAKE_REPLY=JUDGE_REPLY)
    def test_fake_judge_parsed_and_scored_from_parts(self):
        result = judge.judge(self.row, 'Решение модели: Q = 5', providers.FakeProvider(), 'fake')
        scored = judge.score(result.data, self.row)
        # Сумма пунктов (6 + 12 = 18), а не «total» судьи; максимум — из эталона.
        self.assertEqual((scored['total'], scored['max']), (18.0, 20.0))
        self.assertTrue(scored['solved'])

    @override_settings(AI_FAKE_REPLY='не json')
    def test_garbage_is_format_error_not_crash(self):
        result = judge.judge(self.row, 'x', providers.FakeProvider(), 'fake')
        self.assertTrue(result.data['_format_error'])

    def test_constant_part_is_one_block_with_task_and_reference(self):
        block = judge.system_block(self.row)
        self.assertIn('Официальное решение.', block)
        self.assertIn('МАКСИМУМ ЗА ЗАДАЧУ: 20', block)
        self.assertNotIn('Решение модели', block)

    def test_default_max_without_score(self):
        self.assertEqual(judge.task_max({'max_score': None}), judge.DEFAULT_MAX)


class SafeAndMoneyTests(SimpleTestCase):
    def test_safe_needs_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'safe_v1.jsonl'), 'w', encoding='utf-8') as handle:
                handle.write('{"key": "x"}\n')
            with self.assertRaises(v1run.RunRefused):
                v1run.load_rows(tmp, 'safe', phrase='открываю сейф')
            self.assertFalse(os.path.exists(os.path.join(tmp, 'safe_log.jsonl')))
            rows = v1run.load_rows(tmp, 'safe', phrase=v1run.SAFE_PHRASE, label='t')
            self.assertEqual(rows, [{'key': 'x'}])
            self.assertTrue(os.path.exists(os.path.join(tmp, 'safe_log.jsonl')))

    def test_money_cap_stops_new_calls(self):
        calls = []

        def work(item):
            calls.append(item)
            return {'key': item, 'cost_usd': 0.4}
        spent, stopped, done = v1run.run_pool(list(range(10)), work, workers=1, max_usd=1.0,
                                              spent=0.0, on_record=lambda r: None)
        self.assertTrue(stopped)
        self.assertEqual(len(calls), 3)
        self.assertLess(spent, 1.0 + 0.4 + 1e-9)

    def test_spent_before_counts_against_cap(self):
        spent, stopped, done = v1run.run_pool([1, 2], lambda i: {'cost_usd': 0.1}, workers=1,
                                              max_usd=1.0, spent=1.0, on_record=lambda r: None)
        self.assertEqual((done, stopped), (0, True))


class ResumeTests(SimpleTestCase):
    @override_settings(AI_FAKE_REPLY='{"solution": "Ответ: 5", "answers": '
                                     '[{"ask": "", "values": [{"label": "", "value": "5"}]}]}')
    def test_rerun_requests_only_missing(self):
        rows = [reference.exam_row(ref_row(number=str(n)), 'A',
                                   [{'label': '', 'skip': False, 'values': [
                                       {'label': '', 'value': '5', 'unit': '', 'percent': False,
                                        'tol': ''}]}], 'answer') for n in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            v1run.solve_run(tmp, 'r', rows[:2], providers.FakeProvider(), 'fake', write=lambda t: 0)
            v1run.solve_run(tmp, 'r', rows, providers.FakeProvider(), 'fake', write=lambda t: 0)
            records = v1run.read_jsonl(os.path.join(tmp, 'runs', 'r', 'solve.jsonl'))
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r['verdict'] == 'верно' for r in records))

    def test_summary_invariant_answers_plus_failures_equal_sent(self):
        rows = [{'key': k, 'block': 'A', 'fresh': True} for k in 'abc']
        solved = {'a': {'key': 'a', 'verdict': 'верно', 'seconds': 1},
                  'b': {'key': 'b', 'verdict': 'сбой формата', 'format_error': True, 'seconds': 1},
                  'c': {'key': 'c', 'verdict': 'ошибка', 'error': 'x', 'seconds': 1}}
        item = v1run.summarize(rows, solved, {})['A']
        self.assertEqual(item['answered'] + item['format_errors'] + item['errors'], item['sent'])
        self.assertEqual(item['solved'], 1)


class ProviderHeaderTests(SimpleTestCase):
    def test_workspace_header_from_environment(self):
        provider = providers.AnthropicProvider()
        with self.settings():
            os.environ['ANTHROPIC_WORKSPACE_ID'] = 'wrkspc_test'
            try:
                client = provider.client()
            finally:
                del os.environ['ANTHROPIC_WORKSPACE_ID']
        self.assertEqual(client._custom_headers.get('anthropic-workspace-id'), 'wrkspc_test')

    def test_core_is_untouched_by_judge(self):
        self.assertNotIn(judge.PROFILE, core.available_profiles())


class _Obj(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeBatches(object):
    """Подставной Message Batches: отвечает JUDGE_REPLY на каждую заявку."""

    def __init__(self):
        self.created = []

    def create(self, requests):
        self.created = requests
        return _Obj(id='msgbatch_test', processing_status='in_progress')

    def retrieve(self, batch_id):
        return _Obj(id=batch_id, processing_status='ended')

    def results(self, batch_id):
        usage = _Obj(input_tokens=100, output_tokens=50, cache_creation_input_tokens=0,
                     cache_read_input_tokens=0)
        message = _Obj(content=[_Obj(type='text', text=JUDGE_REPLY)], usage=usage)
        for req in self.created:
            yield _Obj(custom_id=req['custom_id'], result=_Obj(type='succeeded', message=message))


class JudgeBatchTests(SimpleTestCase):
    def test_batch_lands_in_run_folders_and_skips_done(self):
        rows = [reference.exam_row(ref_row(number=str(n), solution_md='Эталон.', max_score=20), 'B')
                for n in range(3)]
        client = _Obj(messages=_Obj(batches=FakeBatches()))
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'runs', 'm1'))
            with open(os.path.join(tmp, 'runs', 'm1', 'solve.jsonl'), 'w', encoding='utf-8') as fh:
                for r in rows:
                    fh.write(json.dumps({'key': r['key'], 'block': 'B', 'verdict': 'ответ',
                                         'solution': 'Q = 5'}, ensure_ascii=False) + '\n')
            v1run.judge_batch(tmp, ['m1'], rows, None, 'claude-sonnet-5-5', client=client,
                              write=lambda t: 0, sleep=lambda s: 0)
            sent = client.messages.batches.created
            self.assertEqual(len(sent), 3)
            self.assertTrue(all(r['custom_id'].startswith('r') for r in sent))
            self.assertEqual(sent[0]['params']['temperature'], 0)
            self.assertIn('cache_control', sent[0]['params']['system'][0])
            out = v1run.read_jsonl(os.path.join(tmp, 'runs', 'm1', 'judge_claude-sonnet-5-5.jsonl'))
            self.assertEqual(len(out), 3)
            self.assertTrue(all(r['solved'] and r['batch'] for r in out))
            # Повторный пакет — оценённое не отправляется.
            again, _ = v1run.batch_requests(tmp, ['m1'], rows, 'claude-sonnet-5-5')
            self.assertEqual(again, [])

    def test_estimate_over_cap_refuses(self):
        rows = [reference.exam_row(ref_row(number='1', solution_md='Эталон.'), 'B')]
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'runs', 'm1'))
            with open(os.path.join(tmp, 'runs', 'm1', 'solve.jsonl'), 'w', encoding='utf-8') as fh:
                fh.write(json.dumps({'key': rows[0]['key'], 'block': 'B', 'verdict': 'ответ',
                                     'solution': 'x'}) + '\n')
            with self.assertRaises(v1run.RunRefused):
                v1run.judge_batch(tmp, ['m1'], rows, None, 'claude-opus-5-5', max_usd=0.0001,
                                  client=object(), write=lambda t: 0)
