"""Этап 5: проверка каталожной попытки моделью (подставной поставщик)."""
import json

from django.core.cache import cache
from django.test import TestCase, override_settings

from catalog import attempts
from problems.ai import core, providers
from problems.models import CatalogAttempt, ProblemPart
from problems.tests.factories import make_problem, make_topic, make_user


def _reply(**overrides):
    data = {
        'score': 5, 'verdict': 'partial',
        'steps': [
            {'n': 1, 'title': 'Предложение с налогом', 'verdict': 'ok', 'comment': 'Верно.'},
            {'n': 2, 'title': 'Равновесный объём', 'verdict': 'ok', 'comment': ''},
            {'n': 3, 'title': 'Условие первого порядка', 'verdict': 'ok', 'comment': ''},
            {'n': 4, 'title': 'Выбор Арслана', 'verdict': 'bad',
             'comment': 'Игра последовательная, а решена как одновременная.'},
            {'n': 5, 'title': 'Итоговые сборы', 'verdict': 'bad', 'comment': 'Следствие шага 4.'},
        ],
        'first_error_step': 4, 'confidence': 'high', 'needs_human': False,
        'summary': 'Первая ошибка в шаге 4: игра последовательная.',
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


@override_settings(AI_PROVIDER='fake')
class CheckAttemptTests(TestCase):
    def setUp(self):
        # ⚠️ `core.run` кэширует ответ по тексту запроса на 15 минут: тесты
        # класса делят одну задачу, и без сброса второй тест получал бы ответ
        # первого, минуя подставного поставщика.
        cache.clear()
        self.user = make_user('ivan', first_name='Иван', last_name='Петров',
                              email='ivan@example.org')
        self.topic = make_topic('Монополия и ценовая дискриминация')
        self.problem = make_problem(
            'На школьной ярмарке спрос $Q_d = 120 - P$, предложение $Q_s = 2P$.',
            title='Вмешательство — 5', topic=self.topic,
            solution='Оба налога ложатся на продавцов; функция реакции Егора и выбор Арслана.',
            answer='1800')
        ProblemPart.objects.create(problem=self.problem, label='а', statement='Ставки?', order=1)

    def _attempt(self, problem=None, text='t1 = t2 = 40, сборы 2133'):
        return CatalogAttempt.objects.create(user=self.user, problem=problem or self.problem,
                                             text=text)

    def test_valid_reply_fills_the_attempt(self):
        with override_settings(AI_FAKE_REPLY=_reply()):
            attempt = attempts.check_attempt(self._attempt(), self.user)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'checked')
        self.assertEqual((attempt.verdict, attempt.score, attempt.max_score), ('partial', 5, 10))
        self.assertEqual(attempt.first_error_step, 4)
        self.assertEqual(len(attempt.steps), 5)
        self.assertEqual(attempt.steps[3]['verdict'], 'bad')
        self.assertEqual(attempt.confidence, 'high')
        self.assertIn('шаге 4', attempt.summary)

    def test_reply_off_schema_marks_error_not_crash(self):
        with override_settings(AI_FAKE_REPLY=json.dumps({'foo': 1})):
            attempt = attempts.check_attempt(self._attempt(), self.user)
        self.assertEqual(attempt.status, 'error')
        self.assertEqual(attempt.summary, attempts.OFF_SCHEMA)
        self.assertIsNone(attempt.score)
        with override_settings(AI_FAKE_REPLY=_reply(score=11)):
            self.assertEqual(attempts.check_attempt(self._attempt(), self.user).status, 'error')
        with override_settings(AI_FAKE_REPLY=_reply(steps=[{'n': 1, 'title': 'x', 'verdict': 'maybe', 'comment': ''}])):
            self.assertEqual(attempts.check_attempt(self._attempt(), self.user).status, 'error')

    def test_not_json_is_ai_unavailable(self):
        with override_settings(AI_FAKE_REPLY='это не json'):
            with self.assertRaises(core.AiUnavailable):
                attempts.check_attempt(self._attempt(), self.user)

    def test_needs_human_drops_the_score(self):
        with override_settings(AI_FAKE_REPLY=_reply(needs_human=True, score=7, verdict='partial')):
            attempt = attempts.check_attempt(self._attempt(), self.user)
        self.assertEqual((attempt.status, attempt.verdict, attempt.score),
                         ('needs_human', 'needs_human', None))

    def test_first_error_step_must_exist_among_steps(self):
        with override_settings(AI_FAKE_REPLY=_reply(first_error_step=9)):
            attempt = attempts.check_attempt(self._attempt(), self.user)
        self.assertEqual(attempt.status, 'checked')
        self.assertIsNone(attempt.first_error_step)

    def test_without_reference_confidence_is_capped(self):
        bare = make_problem('Задача без эталона.', topic=self.topic)
        with override_settings(AI_FAKE_REPLY=_reply(confidence='high')):
            attempt = attempts.check_attempt(self._attempt(problem=bare), self.user)
        self.assertEqual(attempt.confidence, 'medium')
        prompt = attempts.build_prompt(bare, [], 'x')
        self.assertIn(attempts.NO_REFERENCE, prompt)

    def test_prompt_carries_the_problem_but_no_profile_fields(self):
        seen = {}

        def capture(system_blocks, user_text):
            seen['text'] = user_text
            seen['system'] = ' '.join(system_blocks)
            return _reply()

        with override_settings(AI_FAKE_REPLY=capture):
            attempts.check_attempt(self._attempt(), self.user)
        text = seen['text']
        for present in ('На школьной ярмарке', 'а) Ставки?', 'ОТВЕТ: 1800',
                        'функция реакции Егора', 'РЕШЕНИЕ УЧЕНИКА:', 't1 = t2 = 40'):
            self.assertIn(present, text)
        for absent in ('Иван', 'Петров', 'ivan@example.org', 'ivan'):
            self.assertNotIn(absent, text)
            self.assertNotIn(absent, seen['system'])
        self.assertIn('ПОШАГОВО', seen['system'])

    def test_timeout_reaches_the_provider_and_remaining_counts(self):
        calls = {}
        original = providers.FakeProvider.complete

        def spy(self_, system_blocks, user_text, schema, model, max_tokens, timeout=None,
                images=None):
            calls['timeout'] = timeout
            return original(self_, system_blocks, user_text, schema, model, max_tokens, timeout=timeout)

        providers.FakeProvider.complete = spy
        self.addCleanup(setattr, providers.FakeProvider, 'complete', original)
        self.assertEqual(core.remaining_today(self.user), core.daily_limit())
        with override_settings(AI_FAKE_REPLY=_reply(), AI_TIMEOUT_SECONDS=7):
            attempts.check_attempt(self._attempt(), self.user)
        self.assertEqual(calls['timeout'], 7)
        self.assertEqual(core.remaining_today(self.user), core.daily_limit() - 1)
        with override_settings(AI_FAKE_REPLY=_reply(), AI_TIMEOUT_SECONDS=7):
            attempts.check_attempt(self._attempt(text='другой текст'), self.user, timeout=3)
        self.assertEqual(calls['timeout'], 3)
