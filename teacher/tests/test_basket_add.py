"""Корзина каталога «Стол» → домашка пачкой (часть B ночи 18.09.2026)."""
import json

from django.test import TestCase
from django.urls import reverse

from problems.models_platform import AssignmentItem
from problems.tests.factories import make_assignment, make_problem, make_user


class BasketAddTests(TestCase):

    def setUp(self):
        self.teacher = make_user('basket_teacher', role='teacher')
        self.first = make_problem('Первая задача.')
        self.second = make_problem('Вторая задача.')
        self.hidden = make_problem('Скрытая задача.', flagged=True)
        self.work = make_assignment(self.teacher, problems=[self.first])
        self.client.force_login(self.teacher)

    def _post(self, ids, work=None):
        url = reverse('teacher:api_assignment_add_problems', args=[(work or self.work).pk])
        return self.client.post(url, json.dumps({'problem_ids': ids}),
                                content_type='application/json')

    def test_new_problems_become_positions_after_the_existing(self):
        data = self._post([self.first.pk, self.second.pk]).json()
        self.assertEqual((data['added'], data['already']), (1, 1))
        items = list(AssignmentItem.objects.filter(assignment=self.work).order_by('order')
                     .values_list('catalog_problem_id', flat=True))
        self.assertEqual(items, [self.first.pk, self.second.pk])
        self.assertIn(self.second, self.work.problems.all())

    def test_flagged_problem_is_refused_and_named(self):
        data = self._post([self.hidden.pk, self.second.pk]).json()
        self.assertEqual(data['refused'], [self.hidden.pk])
        self.assertFalse(AssignmentItem.objects.filter(catalog_problem=self.hidden).exists())

    def test_someone_elses_work_is_not_found(self):
        other = make_assignment(make_user('basket_other', role='teacher'))
        self.assertEqual(self._post([self.second.pk], work=other).status_code, 404)

    def test_student_is_refused(self):
        self.client.force_login(make_user('basket_student'))
        self.assertIn(self._post([self.second.pk]).status_code, (302, 403))
        self.assertFalse(AssignmentItem.objects.filter(catalog_problem=self.second).exists())

    def test_empty_basket_is_a_bad_request(self):
        self.assertEqual(self._post([]).status_code, 400)
