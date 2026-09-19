"""Корзина репетитора «Стола» (README §7, снимки 21–25; S5 18.09.2026).

Галочки, «в N домашках», полоса корзины и «+ В корзину» — только репетитору;
ученик и гость не получают ни разметки, ни сценария, ни эндпоинта подборки
(404). Подборка из корзины — те же задачи в том же порядке, за шлюзом. Старая
одиночная «+ В домашку» кладёт задачу позицией (баг Notion …81ce): после
добавления она видна на экране домашки ученика.
"""
import datetime
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import Collection, StudentGroup
from problems.models_platform import AssignmentItem
from problems.tests.factories import make_assignment, make_problem, make_topic, make_user


class TeacherMarksTests(TestCase):

    def setUp(self):
        cache.clear()
        self.topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        self.a = make_problem('Монополист выбирает выпуск.', topic=self.topic, title='Монополист А')
        self.b = make_problem('Монополист и налог.', topic=self.topic, title='Монополист Б')
        self.teacher = make_user('stol_teacher', role='teacher')
        group = StudentGroup.objects.create(name='9Б', teacher=self.teacher)
        make_assignment(self.teacher, problems=[self.a, self.b], name='ДЗ 6. Монополия', group=group)
        make_assignment(self.teacher, problems=[self.a], name='ДЗ 7. Ценовая')
        # Чужая работа и просроченная — не считаются и в меню не попадают.
        make_assignment(make_user('stol_other', role='teacher'), problems=[self.a, self.b], name='Чужая')
        make_assignment(self.teacher, problems=[self.b], name='Прошлая',
                        deadline=timezone.now() - datetime.timedelta(days=3))

    def _entry(self):
        return self.client.get(reverse('catalog:problem_list')).content.decode()

    def test_teacher_rows_have_a_check_and_count_only_his_works(self):
        self.client.force_login(self.teacher)
        html = self._entry()
        row_a = html[html.index('data-id="%d"' % self.a.pk):]
        row_a = row_a[:row_a.index('</a>')]
        self.assertIn('class="rail-check" role="checkbox" aria-checked="false"', row_a)
        self.assertIn('data-basket-title="Монополист А"', row_a)
        self.assertNotIn('rail-status', row_a)
        self.assertIn('>в 2 домашках<', row_a)
        row_b = html[html.index('data-id="%d"' % self.b.pk):]
        row_b = row_b[:row_b.index('</a>')]
        # «Прошлая» — тоже работа репетитора: пометка считает все его работы.
        self.assertIn('>в 2 домашках<', row_b)

    def test_basket_bar_lists_active_works_with_size_and_whom(self):
        self.client.force_login(self.teacher)
        html = self._entry()
        self.assertIn('catalog/js/stol_basket.js', html)
        self.assertIn('<div class="basket" id="basket" role="region" aria-label="Корзина задач" hidden>', html)
        self.assertIn('data-hw-name="ДЗ 6. Монополия"', html)
        self.assertIn('>2&nbsp;задачи · 9Б</small>', html)
        self.assertIn('data-hw-name="ДЗ 7. Ценовая"', html)
        self.assertNotIn('Чужая', html)
        self.assertNotIn('data-hw-name="Прошлая"', html)
        self.assertNotIn('Новая домашка из корзины', html)
        self.assertNotIn('toggleHwDropdown', html)

    def test_student_and_guest_get_no_basket_at_all(self):
        for who in (None, make_user('stol_student')):
            self.client.logout()
            if who:
                self.client.force_login(who)
            html = self._entry()
            for absent in ('rail-check', 'id="basket"', 'stol_basket.js', 'basket-cfg', 'rail-hw'):
                self.assertNotIn(absent, html, (who, absent))

    def test_problem_has_basket_button_and_no_how_for_teacher(self):
        url = reverse('catalog:problem_detail', args=[self.a.pk])
        self.client.force_login(self.teacher)
        html = self.client.get(url).content.decode()
        self.assertIn('id="basket-toggle" data-basket="%d"' % self.a.pk, html)
        self.assertNotIn('id="how"', html)
        self.assertNotIn('+ В домашку', html)
        self.client.force_login(make_user('stol_student2'))
        html = self.client.get(url).content.decode()
        self.assertNotIn('basket-toggle', html)
        self.assertIn('id="how"', html)

    def test_rail_similar_rows_carry_the_check_too(self):
        self.a.similar_problems.add(self.b)
        self.client.force_login(self.teacher)
        rows = self.client.get(reverse('catalog:api_rail_similar', args=[self.a.pk])).json()['rows_html']
        self.assertIn('data-basket="%d"' % self.b.pk, rows)


class FromBasketTests(TestCase):

    def setUp(self):
        cache.clear()
        self.p1 = make_problem('Первая задача корзины.')
        self.p2 = make_problem('Вторая задача корзины.')
        self.hidden = make_problem('Скрытая задача.', flagged=True)
        self.url = reverse('catalog:collection_from_basket')

    def _post(self, ids):
        return self.client.post(self.url, json.dumps({'problem_ids': ids}), content_type='application/json')

    def test_guest_and_student_get_404(self):
        self.assertEqual(self._post([self.p1.pk]).status_code, 404)
        self.client.force_login(make_user('fb_student'))
        self.assertEqual(self._post([self.p1.pk]).status_code, 404)
        self.assertFalse(Collection.objects.exists())

    def test_collection_keeps_basket_order_and_names_the_refused(self):
        teacher = make_user('fb_teacher', role='teacher')
        self.client.force_login(teacher)
        data = self._post([self.p2.pk, self.hidden.pk, self.p1.pk]).json()
        col = Collection.objects.get()
        self.assertEqual(col.problem_order, [self.p2.pk, self.p1.pk])
        self.assertEqual(set(col.problems.values_list('pk', flat=True)), {self.p1.pk, self.p2.pk})
        self.assertEqual(col.author, teacher)
        self.assertEqual(data['refused'], [self.hidden.pk])
        self.assertEqual(data['url'], reverse('catalog:collection_detail', args=[col.token]))
        self.assertEqual(self.client.get(data['url']).status_code, 200)

    def test_only_hidden_is_a_bad_request(self):
        self.client.force_login(make_user('fb_teacher2', role='teacher'))
        self.assertEqual(self._post([self.hidden.pk]).status_code, 400)
        self.assertEqual(self._post([]).status_code, 400)


class SingleAddIsAPositionTests(TestCase):
    """Баг Notion 3dfb11c9…81ce: одиночная «+ В домашку» писала только M2M."""

    def setUp(self):
        self.teacher = make_user('single_teacher', role='teacher')
        self.student = make_user('single_student')
        self.problem = make_problem('Задача, которую добавляют по одной.', title='Задача по одной')
        self.assignment = make_assignment(self.teacher, students=[self.student], name='ДЗ по одной')
        self.url = reverse('teacher:api_assignment_add_problem', args=[self.assignment.pk])

    def _post(self, pid):
        return self.client.post(self.url, json.dumps({'problem_id': pid}), content_type='application/json')

    def test_added_problem_is_on_the_students_homework_screen(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self._post(self.problem.pk).json()['added'], 1)
        self.assertTrue(AssignmentItem.objects.filter(assignment=self.assignment,
                                                      catalog_problem=self.problem).exists())
        self.assertEqual(self._post(self.problem.pk).json()['already'], 1)
        self.assertEqual(self.assignment.items.count(), 1)
        self.client.force_login(self.student)
        html = self.client.get(reverse('student:assignment_detail', args=[self.assignment.pk])).content.decode()
        self.assertIn('Задача, которую добавляют по одной.', html)

    def test_hidden_problem_and_foreign_work_are_not_found(self):
        self.client.force_login(self.teacher)
        hidden = make_problem('Скрытая.', flagged=True)
        self.assertEqual(self._post(hidden.pk).status_code, 404)
        other = make_assignment(make_user('single_other', role='teacher'))
        resp = self.client.post(reverse('teacher:api_assignment_add_problem', args=[other.pk]),
                                json.dumps({'problem_id': self.problem.pk}), content_type='application/json')
        self.assertEqual(resp.status_code, 404)
