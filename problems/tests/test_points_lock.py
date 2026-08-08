"""
Баллы запираются после первой сдачи (фаза 4 сессии фиксов).

⚠️ ЗАЧЕМ. Максимальный балл за позицию можно было менять когда угодно, в том
числе в домашке, которую уже сдали. Оценки при этом уже выставлены по старой
шкале: ученик, получивший «2 из 2», после правки максимума на 5 обнаружил бы
у себя «2 из 5», ничего не сделав. Итог работы и проценты в статистике
становятся бессмысленными.

Правило владельца: менять можно ДО ПЕРВОЙ СДАЧИ. Запирается работа целиком —
итог это сумма, и подвинутый максимум одной задачи меняет знаменатель у всех.
"""
import json
import re
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.models import (
    Assignment, AssignmentItem, StudentGroup, Submission,
)
from problems.tests.factories import make_problem, make_user


class PointsLockTests(TestCase):

    def setUp(self):
        self.tutor = make_user('t-lock', role='teacher')
        self.student = make_user('s-lock', role='student')
        self.group = StudentGroup.objects.create(name='Группа',
                                                 teacher=self.tutor)
        self.group.students.add(self.student)
        self.problem = make_problem('Задача.', answer='42', difficulty=2)
        self.assignment = Assignment.objects.create(
            name='Работа', author=self.tutor, group=self.group)
        self.assignment.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0,
            catalog_problem=self.problem, points=Decimal('2'))
        self.client.force_login(self.tutor)

    def _submit(self, status='submitted'):
        return Submission.objects.create(
            student=self.student, assignment=self.assignment,
            problem=self.problem, problem_item=self.item, status=status)

    def _post_points(self, value):
        return self.client.post(
            reverse('teacher:api_item_points'),
            json.dumps({'item_id': self.item.pk, 'points': value}),
            content_type='application/json')

    def _page(self):
        return self.client.get(reverse(
            'teacher:group_assignment',
            args=[self.group.pk, self.assignment.pk])).content.decode()

    def _markup(self):
        """Разметка БЕЗ стилей и скриптов.

        Имена классов встречаются и в таблице стилей: искать `pts-lock` по
        всему исходнику значит всегда находить правило и не проверить, есть
        ли на странице сам элемент.
        """
        html = re.sub(r'<script.*?</script>', '', self._page(), flags=re.S)
        return re.sub(r'<style.*?</style>', '', html, flags=re.S)

    # -- само правило -----------------------------------------------------

    def test_not_locked_before_anyone_submits(self):
        self.assertFalse(self.assignment.points_locked)

    def test_locked_after_the_first_submission(self):
        self._submit()
        self.assertTrue(
            Assignment.objects.get(pk=self.assignment.pk).points_locked)

    def test_locked_after_a_reviewed_submission_too(self):
        self._submit(status='reviewed')
        self.assertTrue(
            Assignment.objects.get(pk=self.assignment.pk).points_locked)

    def test_an_opened_but_unsubmitted_work_does_not_lock(self):
        """Ученик открыл домашку и ничего не отправил — менять ещё можно."""
        self._submit(status='not_started')
        self.assertFalse(
            Assignment.objects.get(pk=self.assignment.pk).points_locked)

    def test_lock_covers_the_whole_work_not_one_position(self):
        """Сдали одну задачу — заперты баллы ВСЕХ: итог это сумма."""
        other = AssignmentItem.objects.create(
            assignment=self.assignment, order=1,
            catalog_problem=make_problem('Вторая.', difficulty=2),
            points=Decimal('3'))
        self._submit()
        response = self.client.post(
            reverse('teacher:api_item_points'),
            json.dumps({'item_id': other.pk, 'points': '9'}),
            content_type='application/json')
        self.assertEqual(response.status_code, 409)
        other.refresh_from_db()
        self.assertEqual(other.points, Decimal('3'))

    # -- сервер ------------------------------------------------------------

    def test_points_change_before_submission_goes_through(self):
        response = self._post_points('7')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.points, Decimal('7'))

    def test_server_rejects_the_change_after_submission(self):
        """⚠️ Защита обязана стоять НА СЕРВЕРЕ: спрятать поле мало, запрос
        можно отправить в обход браузера."""
        self._submit()
        response = self._post_points('9')
        self.assertEqual(response.status_code, 409)
        self.assertIn('заперт', response.json()['error'].lower())
        self.item.refresh_from_db()
        self.assertEqual(self.item.points, Decimal('2'))

    # -- экран -------------------------------------------------------------

    def test_field_is_editable_before_submission(self):
        html = self._markup()
        self.assertIn('pts-input', html)
        self.assertNotIn('pts-lock', html)

    def test_number_stays_big_and_visible_after_lock(self):
        """Поле нередактируемо, но ЦИФРА ВИДНА крупно — не прячем."""
        self._submit()
        html = self._markup()
        self.assertNotIn('pts-input', html)
        self.assertIn('k-score__value', html)
        self.assertIn('>2</span>', html)

    def test_locked_screen_explains_why(self):
        """Без объяснения преподаватель решит, что сломалось."""
        self._submit()
        html = self._page()
        self.assertIn('заперт', html.lower())
        self.assertIn('работу уже сдавали', html.lower())
