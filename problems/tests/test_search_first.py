"""
Поиск первый, модель вторая — проверка самого разворота.

Что здесь закрывается. На живом запросе «домашка на КПВ и КТВ из 5 задач»
модель написала «КТВ — альтернативное название КПВ», выдала всем строкам
одну тему, тема сработала жёстким фильтром, и вместо пяти задач нашлось
три. Ни одного из этих четырёх звеньев больше нет:

  * поиск идёт ДО модели и находит КТВ по СЛОВУ, ничего про неё не зная;
  * найденное показывается модели словарём;
  * тема — бонус к рангу, а не фильтр;
  * квота заполняется всегда, а неточное честно помечается.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog import hybrid
from problems import hw_generator
from problems.models import Problem, Topic
from problems.tests.factories import make_problem, make_user


def bank():
    """Маленький банк, где КПВ и КТВ — РАЗНЫЕ вещи, как в жизни."""
    ppf = Topic.objects.create(name='Альтернативные издержки и КПВ',
                               slug='ppf-sf')
    trade = Topic.objects.create(name='Международная торговля', slug='trade-sf')
    made = []
    for index in range(4):
        problem = make_problem(
            'Постройте КПВ страны по данным о производстве %d.' % index,
            title='Вывод КПВ %d' % index, difficulty=3)
        problem.topics.add(ppf)
        made.append(problem)
    for index in range(4):
        problem = make_problem(
            'Две страны торгуют. Постройте КТВ и найдите мировую цену %d.'
            % index, title='КТВ двух стран при торговле %d' % index,
            difficulty=3)
        problem.topics.add(trade)
        made.append(problem)
    return ppf, trade, made


class LexicalFindsRareTermsTests(TestCase):
    """Словарный поиск — ради редких сокращений."""

    def setUp(self):
        self.ppf, self.trade, _ = bank()

    def test_ktv_is_found_by_the_word(self):
        ids, hits, terms = hybrid.lexical_search('построение КТВ', limit=10)
        self.assertTrue(ids)
        titles = set(Problem.objects.filter(pk__in=ids)
                     .values_list('title', flat=True))
        self.assertTrue(any('КТВ' in title for title in titles))
        self.assertFalse(any(title.startswith('Вывод КПВ')
                             for title in titles),
                         'по слову КТВ выданы задачи про КПВ')

    def test_acronyms_go_first_among_terms(self):
        self.assertEqual(hybrid.terms('вторая и третья на сложение КПВ')[0],
                         'КПВ')

    def test_stopwords_are_dropped(self):
        self.assertNotIn('задача', hybrid.terms('задача про эластичность'))

    def test_term_search_looks_into_the_solution(self):
        """Термин часто стоит в решении, а решение в отпечаток не входит."""
        problem = make_problem('Обычное условие без термина.',
                               title='Без термина', difficulty=3)
        problem.solution = 'Здесь применяется лемма Хотеллинга.'
        problem.save()
        ids, _, _ = hybrid.lexical_search('лемма Хотеллинга', limit=10)
        self.assertIn(problem.pk, ids)

    def test_fusion_marks_how_it_was_found(self):
        results = hybrid.search('КТВ', limit=5)
        self.assertTrue(results)
        for hit in results:
            self.assertIn(hit['how'], ('both', 'dense', 'lexical'))
            self.assertIn(hybrid.confidence(hit), ('exact', 'close', 'far'))


class TopicIsNotAFilterTests(TestCase):
    """Тема подсказывает порядок и НИЧЕГО не отсекает."""

    def setUp(self):
        self.ppf, self.trade, _ = bank()

    def test_wrong_topic_does_not_empty_the_result(self):
        """Ровно живой случай: модель ошиблась темой — задачи всё равно есть."""
        row = {'query': 'построение КТВ', 'label': 'КТВ',
               'topic': 'Альтернативные издержки и КПВ',  # ← неверная тема
               'difficulty': 3, 'count': 2}
        found, short = hw_generator.find_problems([row])
        self.assertEqual(len(found), 2)
        self.assertFalse(short)
        titles = [item['problem'].title for item in found]
        self.assertTrue(any('КТВ' in title for title in titles),
                        'неверная тема выбросила правильные задачи: %s'
                        % titles)

    def test_right_topic_still_helps_the_order(self):
        rows_ppf = [{'query': 'кривая возможностей', 'label': 'кпв',
                     'topic': 'Альтернативные издержки и КПВ',
                     'difficulty': 3, 'count': 3}]
        found, _ = hw_generator.find_problems(rows_ppf)
        topics = [t.name for item in found
                  for t in item['problem'].topics.all()]
        self.assertIn('Альтернативные издержки и КПВ', topics)


class SearchBeforeModelTests(TestCase):
    """Порядок: сначала поиск, потом модель — и она видит найденное."""

    def setUp(self):
        cache.clear()
        self.ppf, self.trade, _ = bank()
        self.tutor = make_user('sf_tutor', role='teacher')

    def _reply(self, rows):
        return json.dumps({'rows': rows, 'note': ''}, ensure_ascii=False)

    def test_model_sees_real_problems_from_the_bank(self):
        seen = {}

        def reply(system_blocks, user_text):
            seen['prompt'] = user_text
            seen['system'] = system_blocks
            return self._reply([{'label': 'КТВ', 'query': 'построение КТВ',
                                 'topic': '', 'difficulty': 3, 'count': 5}])

        with override_settings(AI_PROVIDER='fake', AI_FAKE_REPLY=reply):
            hw_generator.parse_request(
                'Домашка на КПВ и КТВ из 5 задач.',
                {'count': 5, 'min_difficulty': 1, 'max_difficulty': 5},
                self.tutor)

        self.assertIn('КТВ двух стран при торговле', seen['prompt'],
                      'модель не увидела найденных задач')
        self.assertIn('словарь банка', seen['prompt'])

    def test_hints_are_built_from_the_catalog_not_written_by_hand(self):
        hints = hw_generator.search_hints('построение КТВ')
        self.assertTrue(hints)
        self.assertTrue(any('КТВ' in hint['title'] for hint in hints))

    def test_quota_is_kept_even_if_the_model_miscounts(self):
        """«Пять задач» — обещание пользователю, а не пожелание модели."""
        rows = [{'label': 'a', 'query': 'КПВ', 'topic': '', 'difficulty': 3,
                 'count': 2},
                {'label': 'b', 'query': 'КТВ', 'topic': '', 'difficulty': 3,
                 'count': 2}]
        with override_settings(AI_PROVIDER='fake',
                               AI_FAKE_REPLY=self._reply(rows)):
            plan = hw_generator.parse_request(
                'пять задач', {'count': 5, 'min_difficulty': 1,
                               'max_difficulty': 5}, self.tutor)
        self.assertEqual(sum(row['count'] for row in plan['rows']), 5)

    def test_garbage_reply_still_produces_a_working_plan(self):
        """Модель ответила пустотой — работаем по фразе репетитора."""
        with override_settings(AI_PROVIDER='fake',
                               AI_FAKE_REPLY=self._reply([])):
            plan = hw_generator.parse_request(
                'домашка про КТВ', {'count': 3, 'min_difficulty': 1,
                                    'max_difficulty': 5}, self.tutor)
        self.assertEqual(len(plan['rows']), 1)
        self.assertEqual(plan['rows'][0]['count'], 3)
        self.assertIn('КТВ', plan['rows'][0]['query'])


class StopGateTests(TestCase):
    """Экран подтверждения: задачи, а не темы; переискать — без модели."""

    def setUp(self):
        cache.clear()
        bank()
        self.tutor = make_user('sg_tutor', role='teacher')
        self.client.force_login(self.tutor)

    def test_gate_shows_found_problems(self):
        reply = json.dumps({'rows': [
            {'label': 'построение КТВ', 'query': 'построение КТВ',
             'topic': '', 'difficulty': 3, 'count': 2}], 'note': ''},
            ensure_ascii=False)
        with override_settings(AI_PROVIDER='fake', AI_FAKE_REPLY=reply):
            body = self.client.post(
                reverse('teacher:assignment_generate'),
                {'action': 'parse', 'text': 'домашка про КТВ', 'count': 2,
                 'min_difficulty': 1, 'max_difficulty': 5}).content.decode()
        self.assertIn('Ваша строка: «построение КТВ»', body)
        self.assertIn('КТВ двух стран при торговле', body)

    def test_research_one_row_does_not_call_the_model(self):
        calls = []

        def reply(system_blocks, user_text):
            calls.append(user_text)
            return json.dumps({'rows': [], 'note': ''})

        with override_settings(AI_PROVIDER='fake', AI_FAKE_REPLY=reply):
            body = self.client.post(
                reverse('teacher:assignment_generate'),
                {'action': 'research', 'text': 'домашка', 'count': 2,
                 'min_difficulty': 1, 'max_difficulty': 5,
                 'row_keep': ['0'], 'row_query': ['построение КТВ'],
                 'row_label': ['моя строка'], 'row_topic': [''],
                 'row_difficulty': ['3'],
                 'row_count': ['2']}).content.decode()
        self.assertEqual(calls, [], 'переискивание сходило к модели')
        self.assertIn('обращения к модели не потребовалось', body)
        self.assertIn('КТВ двух стран при торговле', body)

    def test_result_screen_marks_confidence(self):
        with override_settings(AI_PROVIDER='fake'):
            body = self.client.post(
                reverse('teacher:assignment_generate'),
                {'action': 'search', 'text': 'x', 'count': 2,
                 'min_difficulty': 1, 'max_difficulty': 5,
                 'row_keep': ['0'], 'row_query': ['построение КТВ'],
                 'row_label': ['КТВ'], 'row_topic': [''],
                 'row_difficulty': ['3'],
                 'row_count': ['2']}).content.decode()
        self.assertIn('Найдено задач: 2', body)
        self.assertTrue(any(label in body
                            for label in hybrid.CONFIDENCE_LABELS.values()),
                        'на экране нет ни одной пометки уверенности')


class TitleTests(TestCase):
    """Названия задач в списках — Фаза B.6."""

    def test_no_mid_word_cut_in_the_card(self):
        problem = make_problem(
            'Фирма производит товары $x$и $y$, используя труд нанятых '
            'работников. Всего в штате компании двадцать человек.',
            difficulty=3)
        card = hw_generator.problem_card(problem, 'close')
        self.assertNotIn('шта-', card['title'])
        self.assertIn('$x$ и', card['preview'])
