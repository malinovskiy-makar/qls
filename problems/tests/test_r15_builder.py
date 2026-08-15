# -*- coding: utf-8 -*-
"""Фаза 11 объединённого ревью 15.08: конструктор работы.

11.1 Корзина ОДНА на собираемую работу. Их было две (`hw_cart` и
     `exam_cart`), а переключатель «Домашка / Контрольная» — это переход по
     ссылке: уходя на соседний экран, репетитор терял всё отобранное.
11.2 Третья вкладка «Мои задачи». «Сохранённые» — закладки КАТАЛОГА, свои
     задачи туда не попадали, и владелец решил, что задача не сохранилась.
11.3 Вход на страницу своих задач с экрана «Ученики» (раньше — только
     вводом адреса в строке браузера).
11.5 Занятие из адреса отмечено в «Кому выдать» одинаково на всех экранах.

Полноэкранный режим полей (11.4) проверяется в живом браузере —
`scripts/r15_builder_probe.js`: работает он на классах и предпросмотре,
которых питон-тест не исполняет.
"""
import re

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, TestCase

from problems.models import CustomProblem, Problem, StudentGroup
from teacher.picker import CART_KEY, own_problem_rows

User = get_user_model()


class OneCartTests(TestCase):
    """11.1 — ключ корзины один и приходит из одной точки."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t11', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Г11', teacher=cls.tutor)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def test_key_is_the_same_for_homework_and_exam(self):
        homework = self.client.get('/teacher/assignment/create/')
        exam = self.client.get('/teacher/groups/%d/exams/new/' % self.group.pk)
        build = self.client.get('/teacher/assignment/build/')
        for response in (homework, exam, build):
            self.assertEqual(response.status_code, 200)
            self.assertIn(CART_KEY, response.content.decode())

    def test_old_split_keys_are_gone(self):
        """⚠️ Две корзины — это две работы, а собирают одну."""
        for url in ('/teacher/assignment/create/',
                    '/teacher/groups/%d/exams/new/' % self.group.pk,
                    '/teacher/assignment/build/',
                    '/teacher/assignment/generate/'):
            body = self.client.get(url).content.decode()
            self.assertNotIn("'hw_cart'", body, url)
            self.assertNotIn("'exam_cart'", body, url)

    def test_key_lives_in_python(self):
        self.assertEqual(CART_KEY, 'work_cart')


class OwnProblemsTabTests(TestCase):
    """11.2 — третья вкладка и ключи её карточек."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t11o', password='x',
                                             role='teacher')
        cls.other = User.objects.create_user('t11x', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Г11о', teacher=cls.tutor)
        cls.mine = CustomProblem.objects.create(
            owner=cls.tutor, title='Моя задача', statement='Условие своей',
            kind=CustomProblem.Kind.OPEN, difficulty=3)
        cls.alien = CustomProblem.objects.create(
            owner=cls.other, title='Чужая', statement='Не показывать')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def page(self):
        response = self.client.get('/teacher/assignment/create/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_three_tabs(self):
        html = self.page()
        self.assertIn('>Каталог<', html)
        self.assertIn('Сохранённые (', html)
        self.assertIn('Мои задачи (', html)

    def test_own_tab_counts_only_mine(self):
        self.assertIn('Мои задачи (1)', self.page())

    def test_alien_problem_never_shows(self):
        self.assertNotIn('Не показывать', self.page())

    def test_card_key_is_prefixed(self):
        """⚠️ Своя задача №3 и каталожная №3 голым номером не различаются."""
        rows = own_problem_rows(self.tutor)
        self.assertEqual(rows[0]['key'], 'c%d' % self.mine.pk)
        self.assertIn('data-pid="c%d"' % self.mine.pk, self.page())

    def test_card_looks_like_a_catalog_card(self):
        html = self.page()
        piece = html.split('id="pane-own"')[1].split('id="pane-saved"')[0]
        self.assertIn('btn-preview', piece)
        self.assertIn('btn-add', piece)
        self.assertIn('k-type k-type--task', piece)

    def test_saved_tab_is_not_mixed_with_own(self):
        html = self.page()
        saved = html.split('id="pane-saved"')[1]
        self.assertNotIn('Моя задача', saved)

    def test_preview_endpoint_serves_own_problems(self):
        response = self.client.get('/teacher/api/problem/c%d/' % self.mine.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Моя задача')

    def test_preview_endpoint_hides_alien_problems(self):
        response = self.client.get('/teacher/api/problem/c%d/' % self.alien.pk)
        self.assertEqual(response.status_code, 404)

    def test_preview_endpoint_still_serves_the_catalog(self):
        problem = Problem.objects.create(title='Каталожная', statement='у',
                                         status=Problem.Status.PUBLISHED)
        response = self.client.get('/teacher/api/problem/%d/' % problem.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Каталожная')

    def test_garbage_key_is_not_found(self):
        self.assertEqual(
            self.client.get('/teacher/api/problem/abc/').status_code, 404)

    def test_exam_builder_has_the_tab_too(self):
        html = self.client.get('/teacher/groups/%d/exams/new/'
                               % self.group.pk).content.decode()
        self.assertIn('Мои задачи (1)', html)


class OwnProblemsEntryTests(TestCase):
    """11.3 — на страницу своих задач можно попасть из интерфейса."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t11e', password='x',
                                             role='teacher')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def test_link_on_the_students_screen(self):
        html = self.client.get('/teacher/groups/').content.decode()
        self.assertIn('href="/teacher/problems/"', html)
        self.assertIn('Мои задачи', html)

    def test_top_menu_is_not_touched(self):
        """⚠️ У верхнего меню известная поломка на узком экране — не трогаем."""
        nav = render_to_string('_nav.html', {'user': self.tutor})
        self.assertNotIn('/teacher/problems/', nav)


class GroupFromUrlTests(TestCase):
    """11.5 — занятие из адреса отмечено, и память его не перебивает."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t11g', password='x',
                                             role='teacher')
        cls.first = StudentGroup.objects.create(name='Первое',
                                                teacher=cls.tutor)
        cls.second = StudentGroup.objects.create(name='Второе',
                                                 teacher=cls.tutor)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def checked(self, url):
        html = self.client.get(url).content.decode()
        return re.findall(r'name="groups" value="(\d+)"\s*\n?\s*checked', html)

    def test_creation_screens_precheck_the_group(self):
        for url in ('/teacher/assignment/create/?group=%d' % self.second.pk,
                    '/teacher/assignment/build/?group=%d' % self.second.pk):
            self.assertEqual(self.checked(url), [str(self.second.pk)], url)

    def test_without_a_group_nothing_is_prechecked(self):
        self.assertEqual(self.checked('/teacher/assignment/create/'), [])

    def test_memory_yields_to_the_address(self):
        """⚠️ Память ДОБАВЛЯЛА к отмеченному занятию прошлое, и работа тихо
        уходила ещё и в чужую группу."""
        script = render_to_string('teacher/_build_keep.html')
        self.assertIn('var fromUrl', script)
        self.assertIn('fromUrl ? [] :', script)


class ZoomFieldMarkupTests(TestCase):
    """11.4 — обёртки полноэкранного режима стоят у всех трёх полей."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t11z', password='x',
                                             role='teacher')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def page(self):
        response = self.client.get('/teacher/problems/new/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_statement_solution_and_part_are_zoomable(self):
        html = self.page()
        for name in ('Текст задачи', 'Эталонное решение', 'Вопрос пункта'):
            self.assertIn('data-zoom="%s"' % name, html)

    def test_new_parts_get_a_wrapper_too(self):
        """Пункт, добавленный скриптом, тоже разворачивается."""
        html = self.page()
        piece = html.split('function addPart')[1][:900]
        self.assertIn('zoom-box', piece)

    def test_zoom_is_above_the_sticky_menu(self):
        """⚠️ Шапка сайта — z-index 200; кнопка «Свернуть» уезжала под неё."""
        html = self.page()
        found = re.search(r'\.zoom-box\.is-zoomed \{[^}]*z-index: (\d+)', html)
        self.assertIsNotNone(found)
        self.assertGreater(int(found.group(1)), 200)

    def test_field_is_not_moved_out_of_its_place(self):
        """⚠️ Панель формул вставляется СОСЕДОМ за полем: перенос поля в
        отдельное окно оставил бы кнопку «∑ Формула» позади."""
        html = self.page()
        self.assertIn('classList.add(\'is-zoomed\')', html)
        self.assertNotIn('fsHost.appendChild(area)', html)
