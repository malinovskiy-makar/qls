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
        # ⚠️ Экраны переехали в поток (ревью 17.08, п. 4.5): корзина одна на
        # все шаги и на оба вида работы — это и проверяется.
        homework = self.client.get('/teacher/work/')
        exam = self.client.get('/teacher/work/?kind=exam')
        build = self.client.get('/teacher/work/compose/')
        for response in (homework, exam, build):
            self.assertEqual(response.status_code, 200)
            self.assertIn(CART_KEY, response.content.decode())

    def test_old_split_keys_are_never_read_or_written(self):
        """⚠️ Две корзины — это две работы, а собирают одну.

        ПЕРЕСЧИТАН 16.08: старые имена снова появились в разметке, но уже
        в другом качестве — их СТИРАЮТ (`_cart_keys.html`). Проверка «слова
        нет на странице» после этого краснела бы на правильном экране,
        поэтому проверяем смысл: читать и писать в них нельзя.
        """
        for url in ('/teacher/assignment/create/',
                    '/teacher/groups/%d/exams/new/' % self.group.pk,
                    '/teacher/assignment/build/',
                    '/teacher/assignment/generate/'):
            body = self.client.get(url).content.decode()
            for dead in ('hw_cart', 'exam_cart'):
                self.assertNotIn("getItem('%s')" % dead, body, url)
                self.assertNotIn("setItem('%s'" % dead, body, url)

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
        response = self.client.get('/teacher/work/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_three_tabs(self):
        """⚠️ Вкладок стало пять, а названия — общие для платформы."""
        html = self.page()
        self.assertIn('Искать самому', html)
        self.assertIn('Отложенные (', html)
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
        self.assertIn('data-full', piece)
        self.assertIn('data-add', piece)
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
        html = self.client.get('/teacher/work/?group=%d&kind=exam'
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
        # ⚠️ У ЗАНЯТИЙ ДОЛЖНЫ БЫТЬ УЧЕНИКИ (ревью 17.08, п. 5.7): пустое
        # занятие выбрать нельзя, и отмечать его адресом тоже нельзя —
        # работа ушла бы в пустоту.
        cls.first.students.add(User.objects.create_user('t11g-a', password='x',
                                                        role='student'))
        cls.second.students.add(User.objects.create_user('t11g-b', password='x',
                                                         role='student'))

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def checked(self, url):
        html = self.client.get(url).content.decode()
        # ⚠️ Ищем `checked` ГДЕ УГОДНО ВНУТРИ ТЕГА, а не следующим словом:
        # проверка ломалась от любого нового атрибута между ними, хотя
        # проверяет она совсем другое. Так и вышло, когда полю добавили
        # число учеников для сводки выдачи.
        return re.findall(r'name="groups" value="(\d+)"[^>]*?\bchecked', html,
                          re.S)

    def test_creation_screens_precheck_the_group(self):
        for url in ('/teacher/work/give/?group=%d' % self.second.pk,
                    '/teacher/work/give/?group=%d&kind=exam' % self.second.pk):
            self.assertEqual(self.checked(url), [str(self.second.pk)], url)

    def test_without_a_group_nothing_is_prechecked(self):
        self.assertEqual(self.checked('/teacher/work/give/'), [])

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
