# -*- coding: utf-8 -*-
"""Массовая выгрузка банка через кабинет репетитора закрыта (24.09.2026).

Корзина (`/teacher/api/cart/rows/`), окно «Целиком» (`/teacher/work/api/full/`)
и предпросмотр (`/teacher/api/problem/`) отдают задачу вместе с ответами и
решением. До 24.09 фильтра видимости у них не было, а ключей в корзине —
сколько угодно: любой зарегистрировавшийся «репетитор» одним запросом получал
весь банк, включая скрытое и бракованное.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from problems.models import Assignment, AssignmentItem, Problem
from problems.tests.factories import make_problem

User = get_user_model()


class TeacherBankLeakTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('leak_tutor', password='p12345', role='teacher')
        cls.visible = make_problem('Видимая задача про спрос.', solution='Решение видимой задачи длиннее тридцати.')
        cls.hidden = make_problem('Скрытая задача про налог.', solution='Решение скрытой задачи длиннее тридцати.')
        Problem.objects.filter(pk=cls.hidden.pk).update(status=Problem.Status.HIDDEN)
        cls.defect = make_problem('Бракованная задача.', solution='Решение бракованной задачи длиннее тридцати.')
        Problem.objects.filter(pk=cls.defect.pk).update(needs_quality_review=True)
        cls.in_own_work = make_problem('Скрыта после выдачи.', solution='Решение выданной задачи длиннее тридцати.')
        work = Assignment.objects.create(author=cls.tutor, name='Своя работа')
        AssignmentItem.objects.create(assignment=work, order=0, catalog_problem=cls.in_own_work)
        Problem.objects.filter(pk=cls.in_own_work.pk).update(status=Problem.Status.HIDDEN)

    def setUp(self):
        self.client.force_login(self.tutor)

    def _cart(self, keys):
        return self.client.post('/teacher/api/cart/rows/', {'keys': ','.join(str(k) for k in keys)})

    def test_cart_rows_return_only_visible_or_own(self):
        response = self._cart([self.visible.pk, self.hidden.pk, self.defect.pk, self.in_own_work.pk])
        self.assertEqual(response.status_code, 200)
        keys = [row['key'] for row in response.json()['rows']]
        self.assertEqual(keys, [str(self.visible.pk), str(self.in_own_work.pk)])

    def test_cart_rows_refuse_more_than_a_basket(self):
        response = self._cart(range(1, 102))
        self.assertEqual(response.status_code, 400)

    def test_work_full_hides_hidden(self):
        self.assertEqual(self.client.get('/teacher/work/api/full/%d/' % self.hidden.pk).status_code, 404)
        self.assertEqual(self.client.get('/teacher/work/api/full/%d/' % self.visible.pk).status_code, 200)
        self.assertEqual(self.client.get('/teacher/work/api/full/%d/' % self.in_own_work.pk).status_code, 200)

    def test_problem_preview_hides_hidden_and_broken_text(self):
        self.assertEqual(self.client.get('/teacher/api/problem/%d/' % self.hidden.pk).status_code, 404)
        self.assertEqual(self.client.get('/teacher/api/problem/%d/' % self.defect.pk).status_code, 404)
        Problem.objects.filter(pk=self.visible.pk).update(content_status=Problem.ContentStatus.NEEDS_FIX)
        self.assertEqual(self.client.get('/teacher/api/problem/%d/' % self.visible.pk).status_code, 404)
