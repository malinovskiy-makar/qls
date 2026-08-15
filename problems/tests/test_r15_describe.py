# -*- coding: utf-8 -*-
"""Фаза 13 объединённого ревью 15.08: экраны «Описать словами».

⚠️ ЛОКАЛЬНО КЛЮЧ МОДЕЛИ НЕ ЗАДАН, поэтому в браузере экран честно пишет
«функция выключена», а шаги «Что нашлось» и «Конструктор» недоступны.
Владелец видел это и просил разобраться: дело в отсутствующем ключе, а не
в поломке. Поэтому проверка идёт ПОДСТАВНЫМ поставщиком (`AI_PROVIDER =
'fake'`) — тем самым, что заведён в проекте ровно для этого.

Что закрываем:
  • задача на шаге «Что нашлось» раскрывается ЦЕЛИКОМ: условие без
    обрезки, все пункты, ответы, наличие эталонного решения;
  • запрос, по которому найдена группа, виден БЕЗ раскрытия карточки;
  • из группы выбираются конкретные задачи, а не всё подряд.
"""
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from problems import hw_generator
from problems.models import ProblemPart, Topic
from problems.tests.factories import make_problem, make_user


def reply(rows):
    return json.dumps({'rows': rows, 'note': ''}, ensure_ascii=False)


class FoundStepTests(TestCase):
    """Шаг «Что нашлось» — с подставной моделью, как и требовалось."""

    def setUp(self):
        from django.core.cache import cache

        from catalog import semantic

        cache.clear()
        semantic.invalidate_index()
        self.tutor = make_user('r15_desc', role='teacher')
        self.client.force_login(self.tutor)
        topic = Topic.objects.create(name='Эластичность', slug='elast-r15')
        # Условие длиннее прежней обрезки в 900 символов: раньше оно
        # показывалось кусочком, и это выглядело как целое условие.
        self.long = 'Эластичность спроса по цене. ' + ('Дано число 7. ' * 90)
        self.problem = make_problem(self.long, title='Эластичность спроса',
                                    difficulty=3)
        self.problem.topics.add(topic)
        self.problem.answer = 'E = -1,5'
        self.problem.solution = 'Считаем по формуле дуговой эластичности.'
        self.problem.save()
        ProblemPart.objects.create(problem=self.problem, label='а',
                                   statement='Найдите коэффициент.',
                                   answer='-1,5')
        ProblemPart.objects.create(problem=self.problem, label='б',
                                   statement='Сделайте вывод о выручке.',
                                   answer='выручка вырастет')

    def gate(self):
        answer = reply([{'label': 'эластичность', 'query': 'эластичность спроса',
                         'topic': '', 'difficulty': 3, 'count': 1}])
        with override_settings(AI_PROVIDER='fake', AI_FAKE_REPLY=answer):
            response = self.client.post(
                reverse('teacher:assignment_generate'),
                {'step_action': 'parse', 'text': 'домашка про эластичность',
                 'count': 1, 'min_difficulty': 1, 'max_difficulty': 5})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_screen_renders_without_a_real_key(self):
        """Шаблон обязан рисоваться под подставным поставщиком."""
        self.assertIn('Вот что нашлось', self.gate())

    def test_statement_is_shown_whole(self):
        """⚠️ Обрезка по 900 символам выглядела как целое условие."""
        body = self.gate()
        self.assertIn(self.long[:60], body)
        self.assertIn(self.long[-40:].strip(), body)

    def test_all_parts_with_answers(self):
        body = self.gate()
        self.assertIn('Найдите коэффициент', body)
        self.assertIn('Сделайте вывод о выручке', body)
        self.assertIn('выручка вырастет', body)

    def test_solution_presence_is_reported(self):
        self.assertIn('эталонное решение есть', self.gate())

    def test_query_is_visible_without_expanding(self):
        """Видно, какая строка запроса дала эту группу задач."""
        body = self.gate()
        self.assertIn('искали: «эластичность спроса»', body)

    def test_specific_problems_can_be_chosen(self):
        """Из группы берут конкретные задачи, а не всё подряд."""
        body = self.gate()
        self.assertIn('class="cand-pick"', body)
        self.assertIn('cand-pick" value="%d"' % self.problem.pk, body)

    def test_card_carries_the_whole_problem(self):
        card = hw_generator.problem_card(self.problem)
        self.assertEqual(card['body'].strip()[-14:],
                         hw_generator.clean(self.long).strip()[-14:])
        self.assertEqual([p['label'] for p in card['parts']], ['а', 'б'])
        self.assertEqual(card['answer'], 'E = -1,5')
        self.assertTrue(card['has_solution'])


class MoreCandidatesTests(TestCase):
    """Догруженная карточка не беднее серверной."""

    def setUp(self):
        from django.core.cache import cache

        from catalog import semantic

        cache.clear()
        semantic.invalidate_index()
        self.tutor = make_user('r15_more', role='teacher')
        self.client.force_login(self.tutor)
        for index in range(8):
            problem = make_problem('Задача про эластичность %d.' % index,
                                   title='Эластичность %d' % index,
                                   difficulty=3)
            problem.answer = 'ответ %d' % index
            problem.save()
            ProblemPart.objects.create(problem=problem, label='а',
                                       statement='Пункт %d' % index,
                                       answer='%d' % index)

    def test_json_has_the_same_fields(self):
        response = self.client.post(reverse('teacher:api_more_candidates'),
                                    {'query': 'эластичность', 'count': 2,
                                     'difficulty': 3, 'offset': 0})
        self.assertEqual(response.status_code, 200)
        cards = response.json()['cards']
        self.assertTrue(cards)
        for field in ('body', 'parts', 'answer', 'has_solution', 'is_test'):
            self.assertIn(field, cards[0], field)

    def test_script_fills_those_fields(self):
        """⚠️ Иначе задачи из «Показать ещё 5» раскрывались бы беднее."""
        with open('teacher/templates/teacher/generate.html',
                  encoding='utf-8') as fh:
            page = fh.read()
        piece = page.split('function makeRow')[1][:2000]
        for name in ('cand-st', 'cand-parts', 'cand-answer', 'cand-kind',
                     'cand-sol'):
            self.assertIn(name, piece, name)
