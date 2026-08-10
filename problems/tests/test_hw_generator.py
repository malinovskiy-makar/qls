"""
Подбор домашки по описанию: одно обращение, дедупликация, отказы.

⚠️ К настоящему API тесты НЕ ходят. Проверяется архитектура: сколько
обращений на домашку, выбирает ли модель темы из меню, не повторяются ли
задачи, что происходит без ключа. Ходить в сеть из тестов — значит платить
за каждый прогон и краснеть, когда сеть недоступна.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from problems import hw_generator
from problems.models import AiUsageLog, Problem, Topic
from problems.tests.factories import make_problem, make_user


class FakeUsage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class FakeBlock:
    type = 'text'

    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, payload, i=900, o=180):
        self.content = [FakeBlock(json.dumps(payload, ensure_ascii=False))]
        self.usage = FakeUsage(i, o)


def fake_client(payload, counter):
    """Подставной клиент: считает, сколько раз к модели обратились."""
    class Messages:
        def create(self, **kwargs):
            counter.append(kwargs)
            return FakeResponse(payload)

    class Client:
        def __init__(self, **kwargs):
            self.messages = Messages()

    return Client


PLAN = {
    'rows': [
        {'topic': 'Монополия и ценовая дискриминация', 'difficulty': 3,
         'count': 2, 'query': 'монополия и предельный доход'},
        {'topic': 'Эластичность', 'difficulty': 3, 'count': 2,
         'query': 'эластичность спроса по цене'},
        {'topic': 'Монополия и ценовая дискриминация', 'difficulty': 5,
         'count': 1, 'query': 'ценовая дискриминация сложная'},
    ],
    'note': 'Пять задач, последняя сложнее.',
}


@override_settings(AI_GENERATOR_MODEL='claude-haiku-4-5')
class ParseRequestTests(TestCase):

    def setUp(self):
        cache.clear()
        self.tutor = make_user('gen_tutor', role='teacher')

    def _run(self, payload=PLAN, text='домашка на монополию и эластичность, '
                                      'пять задач, одна посложнее в конце'):
        calls = []
        module = mock.MagicMock()
        module.Anthropic = fake_client(payload, calls)
        module.APIConnectionError = type('C', (Exception,), {})
        module.RateLimitError = type('R', (Exception,), {})
        module.APIStatusError = type('S', (Exception,), {})
        with mock.patch.dict('sys.modules', {'anthropic': module}), \
                mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
            plan = hw_generator.parse_request(
                text, {'count': 5, 'min_difficulty': 1, 'max_difficulty': 5},
                self.tutor)
        return plan, calls

    def test_one_api_call_per_homework(self):
        """ГЛАВНОЕ АРХИТЕКТУРНОЕ ТРЕБОВАНИЕ: обращение ровно одно."""
        plan, calls = self._run()
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(plan['rows']), 3)
        self.assertEqual(sum(row['count'] for row in plan['rows']), 5)

    def test_model_gets_the_menu_of_topics(self):
        """Темы модель выбирает ИЗ СПИСКА, а не выдумывает."""
        _, calls = self._run()
        prompt = calls[0]['messages'][0]['content']
        for topic in ('Монополия и ценовая дискриминация', 'Эластичность'):
            self.assertIn(topic, prompt)
        self.assertIn('json_schema',
                      json.dumps(calls[0]['output_config']))

    def test_invented_topic_empties_the_field_but_keeps_the_row(self):
        """⚠️ ИЗМЕНЕНИЕ КОНТРАКТА (Фаза B.4). Раньше строка с выдуманной
        темой ВЫБРАСЫВАЛАСЬ целиком — и вместе с ней исчезала часть просьбы
        репетитора. Теперь тема — подсказка ранжированию, а не фильтр:
        несопоставленная тема просто становится пустой, а строка остаётся
        и ищется по СЛОВАМ репетитора."""
        payload = {'rows': [
            {'topic': 'Микроэкономика рынков', 'difficulty': 3, 'count': 2,
             'query': 'что-то', 'label': 'что-то'},
            {'topic': 'Эластичность', 'difficulty': 2, 'count': 1,
             'query': 'эластичность', 'label': 'эластичность'},
        ], 'note': ''}
        plan, _ = self._run(payload=payload)
        self.assertEqual(len(plan['rows']), 2, 'строка потеряна вместе с темой')
        self.assertEqual(plan['rows'][0]['topic'], '')
        self.assertEqual(plan['rows'][0]['query'], 'что-то')
        self.assertEqual(plan['rows'][1]['topic'], 'Эластичность')

    def test_difficulty_is_clamped_to_the_tutors_range(self):
        payload = {'rows': [{'topic': 'Эластичность', 'difficulty': 5,
                             'count': 1, 'query': 'x'}], 'note': ''}
        calls = []
        module = mock.MagicMock()
        module.Anthropic = fake_client(payload, calls)
        module.APIConnectionError = type('C', (Exception,), {})
        module.RateLimitError = type('R', (Exception,), {})
        module.APIStatusError = type('S', (Exception,), {})
        with mock.patch.dict('sys.modules', {'anthropic': module}), \
                mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
            plan = hw_generator.parse_request(
                'что угодно',
                {'count': 1, 'min_difficulty': 1, 'max_difficulty': 3},
                self.tutor)
        self.assertEqual(plan['rows'][0]['difficulty'], 3)

    def test_tokens_and_cost_are_logged(self):
        plan, _ = self._run()
        log = AiUsageLog.objects.get()
        self.assertEqual(log.input_tokens, 900)
        self.assertEqual(log.output_tokens, 180)
        # Haiku 4.5: $1 за млн входных, $5 за млн выходных.
        self.assertAlmostEqual(float(log.cost_usd),
                               900 / 1e6 * 1 + 180 / 1e6 * 5, places=8)
        self.assertGreater(plan['usage']['cost_usd'], 0)

    def test_same_request_twice_uses_cache(self):
        """Одинаковый запрос подряд не гоняется повторно."""
        self._run()
        _, calls = self._run()
        self.assertEqual(len(calls), 0)
        self.assertEqual(AiUsageLog.objects.count(), 1)

    @override_settings(AI_GENERATOR_DAILY_LIMIT=1)
    def test_daily_limit(self):
        self._run()
        with self.assertRaises(hw_generator.GeneratorUnavailable) as caught:
            self._run(text='совсем другой запрос про эластичность')
        self.assertIn('лимит', str(caught.exception))

    def test_no_key_means_switched_off_not_crash(self):
        with mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': ''}):
            self.assertFalse(hw_generator.is_available())
            self.assertIn('ANTHROPIC_API_KEY',
                          hw_generator.unavailable_reason())
            with self.assertRaises(hw_generator.GeneratorUnavailable):
                hw_generator.parse_request('текст', {}, self.tutor)

    def test_garbage_from_the_model_is_a_message_not_a_500(self):
        calls = []
        module = mock.MagicMock()

        class Messages:
            def create(self, **kwargs):
                calls.append(kwargs)
                response = FakeResponse({})
                response.content = [FakeBlock('это не json')]
                return response

        module.Anthropic = type('C', (), {
            '__init__': lambda self, **kw: setattr(self, 'messages',
                                                   Messages())})
        module.APIConnectionError = type('C', (Exception,), {})
        module.RateLimitError = type('R', (Exception,), {})
        module.APIStatusError = type('S', (Exception,), {})
        with mock.patch.dict('sys.modules', {'anthropic': module}), \
                mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
            with self.assertRaises(hw_generator.GeneratorUnavailable):
                hw_generator.parse_request('текст', {'count': 3}, self.tutor)


class FindProblemsTests(TestCase):
    """Подбор — бесплатный: только свой банк, никакого API."""

    def setUp(self):
        self.topic = Topic.objects.create(name='Эластичность',
                                          slug='elasticity-gen')
        self.problems = []
        for index in range(12):
            problem = make_problem('Задача про эластичность %d' % index,
                                   difficulty=3)
            problem.topics.add(self.topic)
            self.problems.append(problem)

    def _rows(self, count):
        return [{'topic': 'Эластичность', 'difficulty': 3, 'count': count,
                 'query': 'эластичность спроса', 'label': 'эластичность'}]

    def test_no_duplicates_across_rows(self):
        """Две строки по одной теме не вернут одну задачу дважды."""
        rows = [
            {'topic': 'Эластичность', 'difficulty': 3, 'count': 3,
             'query': 'эластичность спроса', 'label': 'спрос'},
            {'topic': 'Эластичность', 'difficulty': 3, 'count': 3,
             'query': 'эластичность предложения', 'label': 'предложение'},
        ]
        found, empty = hw_generator.find_problems(rows)
        ids = [item['problem'].pk for item in found]
        self.assertEqual(len(ids), len(set(ids)), 'задача попала дважды')

    def test_excluded_problems_are_not_returned_again(self):
        """«Подобрать другие» не возвращает уже показанное."""
        first, _ = hw_generator.find_problems(self._rows(3))
        shown = [item['problem'].pk for item in first]
        second, _ = hw_generator.find_problems(self._rows(3), exclude=shown)
        self.assertFalse(set(shown) & {i['problem'].pk for i in second})

    def test_quota_is_filled_even_when_the_row_finds_nothing(self):
        """⚠️ ИЗМЕНЕНИЕ КОНТРАКТА (Фаза B.4): «не хватило задач» больше не
        результат. Просили четыре — получите четыре, а честность
        обеспечивается ПОМЕТКОЙ, а не пустым местом."""
        rows = [{'topic': 'Поведенческая экономика', 'difficulty': 3,
                 'count': 4, 'query': 'нечто чего в банке нет',
                 'label': 'нечто'}]
        found, short = hw_generator.find_problems(rows)
        self.assertEqual(len(found), 4)
        self.assertFalse(short)

    def test_padded_problems_are_honestly_marked(self):
        """Молча подсунуть чужую задачу нельзя."""
        rows = [{'topic': '', 'difficulty': 3, 'count': 4,
                 'query': 'нечто чего в банке нет', 'label': 'нечто'}]
        found, _ = hw_generator.find_problems(rows)
        self.assertTrue(any(item['confidence'] == 'far' for item in found),
                        'добор не помечен как «ближайшее что нашлось»')
        for item in found:
            self.assertIn(item['confidence'], ('exact', 'close', 'far'))

    def test_nothing_at_all_is_still_not_a_crash(self):
        """Пустой банк — не пятисотка, а честно пустой список."""
        Problem.objects.all().delete()
        found, short = hw_generator.find_problems(
            [{'topic': '', 'difficulty': 3, 'count': 3, 'query': 'что угодно',
              'label': 'что угодно'}])
        self.assertEqual(found, [])
        self.assertEqual(short[0]['missing'], 3)

    def test_source_cap_yields_to_the_quota(self):
        """Потолок «не больше трёх из источника» — ПРЕДПОЧТЕНИЕ, не запрет.

        ⚠️ ИЗМЕНЕНИЕ КОНТРАКТА (Фаза B.4). Раньше потолок обрезал подборку
        до трёх задач и репетитор получал три вместо восьми. Пять задач из
        двух сборников лучше трёх и извинения; когда выбора нет — берём из
        одного, потому что пустое место хуже однообразия.
        """
        from problems.models import Source, SourceReference

        source = Source.objects.create(name='Один сборник')
        for problem in self.problems:
            SourceReference.objects.create(problem=problem, source=source)
        found, short = hw_generator.find_problems(self._rows(8))
        self.assertEqual(len(found), 8)
        self.assertFalse(short)


class GenerateScreenTests(TestCase):

    def setUp(self):
        cache.clear()
        self.tutor = make_user('gs_tutor', role='teacher')
        self.client.force_login(self.tutor)

    def test_screen_opens_and_says_when_switched_off(self):
        with mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': ''}):
            body = self.client.get(
                reverse('teacher:assignment_generate')).content.decode()
        self.assertIn('Подобрать домашку по описанию', body)
        self.assertIn('ANTHROPIC_API_KEY', body)
        self.assertIn('вручную', body)

    def test_stop_gate_shows_the_plan_before_searching(self):
        calls = []
        module = mock.MagicMock()
        module.Anthropic = fake_client(PLAN, calls)
        module.APIConnectionError = type('C', (Exception,), {})
        module.RateLimitError = type('R', (Exception,), {})
        module.APIStatusError = type('S', (Exception,), {})
        with mock.patch.dict('sys.modules', {'anthropic': module}), \
                mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
            response = self.client.post(
                reverse('teacher:assignment_generate'),
                {'step_action': 'parse', 'text': 'монополия и эластичность',
                 'count': 5, 'min_difficulty': 1, 'max_difficulty': 5})
        body = response.content.decode()
        self.assertIn('Вот что нашлось по вашему запросу', body)
        # ⚠️ Стоп-гейт показывает ЗАДАЧИ, а не темы: проверить нашу
        # таксономию репетитор не может, а названия задач — за пять секунд.
        # С сессии 8 каждая строка — раскрывающаяся карточка запроса.
        self.assertIn('class="q-head"', body)
        self.assertIn('cand-pick', body)
        self.assertNotIn('Найдено задач', body)
        self.assertEqual(len(calls), 1)

    def test_search_step_makes_no_api_call(self):
        """Шаг подбора ходит только в свой банк — обращений к модели нет."""
        topic = Topic.objects.create(name='Эластичность', slug='el-gs')
        for index in range(4):
            problem = make_problem('Про эластичность %d' % index, difficulty=3)
            problem.topics.add(topic)

        calls = []
        module = mock.MagicMock()
        module.Anthropic = fake_client(PLAN, calls)
        with mock.patch.dict('sys.modules', {'anthropic': module}), \
                mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
            response = self.client.post(
                reverse('teacher:assignment_generate'),
                {'step_action': 'search', 'text': 'x', 'count': 2,
                 'min_difficulty': 1, 'max_difficulty': 5,
                 'row_keep': ['0'], 'row_topic': ['Эластичность'],
                 'row_label': ['эластичность'],
                 'row_difficulty': ['3'], 'row_count': ['2'],
                 'row_query': ['эластичность']})
        self.assertEqual(len(calls), 0)
        self.assertIn('Найдено задач', response.content.decode())

    def test_students_cannot_open(self):
        student = make_user('gs_student', role='student')
        self.client.force_login(student)
        response = self.client.get(reverse('teacher:assignment_generate'))
        self.assertIn(response.status_code, (403, 302))
