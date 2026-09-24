# -*- coding: utf-8 -*-
"""Решения и ответы — только вошедшим (24.09.2026, решение владельца, ADR 0129).

Раньше полное решение, ответы к пунктам и «Почему так» теста лежали в
разметке страницы задачи у каждого, включая гостя: весь банк решений снимался
чтением HTML. Условие остаётся открытым (иначе нет поиска Google и Яндекса).
"""
import json

from django.test import TestCase
from django.urls import reverse

from problems.models import ProblemPart
from problems.tests.factories import make_problem, make_user

SOLUTION = 'Секретное решение: приравниваем MR к MC и находим выпуск.'
PART_ANSWER = 'Ответ пункта сорок два'
TEST_EXPL = 'Пояснение теста: Центральный банк устанавливает ставку.'


class GuestSeesNoSolutionsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.problem = make_problem('Монополист выбирает выпуск.', solution=SOLUTION, answer='Q = 10')
        ProblemPart.objects.create(problem=cls.problem, label='а', order=0,
                                   statement='Найдите цену.', answer=PART_ANSWER)
        cls.test = make_problem('Кто устанавливает ключевую ставку?',
                                problem_type='тест: один ответ', answer='b', solution=TEST_EXPL)
        for i, label in enumerate('abcd'):
            ProblemPart.objects.create(problem=cls.test, label=label, order=i,
                                       statement='Вариант %s' % label)
        cls.url = reverse('catalog:problem_detail', args=[cls.problem.pk])
        cls.api = reverse('catalog:api_solution', args=[cls.problem.pk])

    def _pages(self, problem):
        url = reverse('catalog:problem_detail', args=[problem.pk])
        full = self.client.get(url).content.decode()
        pane = json.dumps(self.client.get(url, {'pane': '1'}).json(), ensure_ascii=False)
        return full, pane

    def test_guest_html_and_pane_have_no_solution_or_answers(self):
        for html in self._pages(self.problem):
            self.assertNotIn('Секретное решение', html)
            self.assertNotIn(PART_ANSWER, html)
            self.assertNotIn('help-sol-tpl', html)
            self.assertIn('help-invite-tpl', html)
            self.assertIn('Решение и ответы открываются после короткой бесплатной регистрации', html)
            self.assertIn('/register/?next=%2Fcatalog%2Fproblem%2F', html)

    def test_guest_test_page_has_no_explanation(self):
        for html in self._pages(self.test):
            self.assertNotIn('Пояснение теста', html)
            self.assertIn('help-invite-tpl', html)

    def test_guest_gets_403_from_the_solution_request(self):
        self.assertEqual(self.client.post(self.api, '{}', content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post(self.api, json.dumps({'part': 0}),
                                          content_type='application/json').status_code, 403)

    def test_signed_in_gets_solution_and_part_by_request(self):
        self.client.force_login(make_user('sol_reader'))
        page = self.client.get(self.url).content.decode()
        self.assertNotIn('Секретное решение', page)
        self.assertNotIn('help-invite-tpl', page)
        data = self.client.post(self.api, '{}', content_type='application/json').json()
        self.assertIn('Секретное решение', data['html'])
        data = self.client.post(self.api, json.dumps({'part': 0}), content_type='application/json').json()
        self.assertIn(PART_ANSWER, data['html'])
        self.assertEqual(self.client.post(self.api, json.dumps({'part': 5}),
                                          content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get(self.api).status_code, 405)

    def test_signed_in_test_page_keeps_explanation(self):
        self.client.force_login(make_user('test_reader'))
        html = self.client.get(reverse('catalog:problem_detail', args=[self.test.pk])).content.decode()
        self.assertIn('Пояснение теста', html)
