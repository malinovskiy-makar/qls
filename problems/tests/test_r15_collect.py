# -*- coding: utf-8 -*-
"""Фаза 12 объединённого ревью 15.08: конструктор подборки.

Блок назывался «Работа глазами ученика», а показывал название, тему и
балл — то есть ровно то, чего ученик не видит. Ни условия, ни пунктов, ни
ответов; перетаскивания не было ни одного элемента; предпросмотра печати
не существовало вовсе — увидеть собранное можно было единственным
способом: создать работу.

⚠️ ПОРЯДОК КОРЗИНЫ. Найдено сценарием: кнопка «выше» срабатывала, корзина
переписывалась, а список возвращался на место. Корзина — объект, а
JavaScript отдаёт ЧИСЛОВЫЕ ключи объекта по возрастанию НЕЗАВИСИМО от
порядка добавления; ключ каталожной задачи — её номер, значит порядок
задач молча совпадал с порядком номеров в банке. Порядок теперь хранится
отдельным списком.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from problems.models import CustomProblem, Problem, ProblemPart, StudentGroup
from teacher.picker import cart_items, cart_rows

User = get_user_model()


class CartRowsCarryTheWholeProblemTests(TestCase):
    """Позиция отдаёт задачу целиком, а не название с баллом."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t12', password='x',
                                             role='teacher')
        cls.problem = Problem.objects.create(
            title='Спрос', statement='Спрос задан $Q_d = 100 - 2P$.',
            answer='P = 20', solution='Решаем через равенство.',
            problem_type='задача', difficulty=4,
            status=Problem.Status.PUBLISHED)
        ProblemPart.objects.create(problem=cls.problem, label='а',
                                   statement='Найдите равновесие.',
                                   answer='50')
        ProblemPart.objects.create(problem=cls.problem, label='б',
                                   statement='Постройте график.',
                                   answer='—')
        cls.own = CustomProblem.objects.create(
            owner=cls.tutor, title='Своя', statement='Условие своей',
            kind=CustomProblem.Kind.OPEN, difficulty=2)

    def rows(self):
        return cart_rows([str(self.problem.pk), 'c%d' % self.own.pk],
                         self.tutor)

    def test_statement_is_there(self):
        self.assertIn('100 - 2P', self.rows()[0]['statement'])

    def test_all_parts_with_answers(self):
        parts = self.rows()[0]['parts']
        self.assertEqual([p['label'] for p in parts], ['а', 'б'])
        self.assertEqual(parts[0]['answer'], '50')

    def test_solution_presence_is_reported(self):
        rows = self.rows()
        self.assertTrue(rows[0]['has_solution'])
        self.assertFalse(rows[1]['has_solution'])

    def test_kind_and_difficulty(self):
        row = self.rows()[0]
        self.assertEqual(row['kind_label'], 'Задача')
        self.assertEqual(row['difficulty'], 4)

    def test_answer_of_the_whole_problem(self):
        self.assertEqual(self.rows()[0]['answer'], 'P = 20')

    def test_points_are_the_ones_the_tutor_set(self):
        rows = cart_rows([str(self.problem.pk)], self.tutor,
                         points={str(self.problem.pk): 7})
        self.assertEqual(rows[0]['points'], 7.0)


class CartOrderTests(TestCase):
    """Порядок позиций — тот, что задал репетитор."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t12o', password='x',
                                             role='teacher')
        cls.first = Problem.objects.create(title='Первая', statement='a',
                                           status=Problem.Status.PUBLISHED)
        cls.second = Problem.objects.create(title='Вторая', statement='b',
                                            status=Problem.Status.PUBLISHED)

    def test_manual_order_is_respected_key_by_key(self):
        keys = [str(self.second.pk), str(self.first.pk)]
        rows = cart_rows(keys, self.tutor, manual_order=True)
        self.assertEqual([r['key'] for r in rows], keys)

    def test_without_manual_order_tests_go_first(self):
        test = Problem.objects.create(title='Тест', statement='t',
                                      problem_type='тест: один ответ',
                                      status=Problem.Status.PUBLISHED)
        rows = cart_rows([str(self.first.pk), str(test.pk)], self.tutor)
        self.assertEqual(rows[0]['key'], str(test.pk))

    def test_order_is_kept_in_a_list_not_in_object_keys(self):
        """⚠️ Числовые ключи объекта JavaScript всегда идут по возрастанию.

        Значит порядок каталожных задач нельзя было задать вообще ничем.
        Экран хранит порядок отдельным списком — проверяем, что он есть.
        """
        with open('teacher/templates/teacher/assignment_build.html',
                  encoding='utf-8') as fh:
            page = fh.read()
        # ПЕРЕСЧИТАН 16.08: имя ключа теперь приходит из общего
        # `_cart_keys.html` (одна точка на все экраны), а не собирается
        # здесь строкой. Смысл проверки прежний — список порядка есть.
        self.assertIn('var ORDER_KEY = window.QLS_CART.order', page)
        self.assertIn('function readOrder', page)


class CartPrintPreviewTests(TestCase):
    """Печатный лист собирается ДО создания работы, той же сборкой."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t12p', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Г12', teacher=cls.tutor)
        cls.problem = Problem.objects.create(
            title='Задача печати', statement='Условие для листка',
            status=Problem.Status.PUBLISHED)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def post(self, **extra):
        data = {'keys': str(self.problem.pk), 'work_name': 'Проба'}
        data.update(extra)
        return self.client.post('/teacher/assignment/cart/print/', data)

    def test_sheet_renders(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Условие для листка', html)
        self.assertIn('Проба', html)

    def test_preview_says_the_work_is_not_created_yet(self):
        self.assertIn('работа ещё не создана', self.post().content.decode())

    def test_nothing_is_written_to_the_database(self):
        from problems.models import Assignment, AssignmentItem

        before = (Assignment.objects.count(), AssignmentItem.objects.count())
        self.post()
        self.assertEqual((Assignment.objects.count(),
                          AssignmentItem.objects.count()), before)

    def test_points_from_the_screen_reach_the_sheet(self):
        html = self.post(points='%d:7' % self.problem.pk).content.decode()
        self.assertIn('7', html)

    def test_only_post(self):
        self.assertEqual(
            self.client.get('/teacher/assignment/cart/print/').status_code,
            405)

    def test_same_builder_as_the_created_work(self):
        """⚠️ Предпросмотр, собранный своим кодом, показывал бы не то, что
        напечатается потом."""
        from problems import assignment_export

        items, _ = cart_items([str(self.problem.pk)], self.tutor)
        rows, _skipped = assignment_export.print_rows(
            _shell(), items=items)
        self.assertEqual(len(rows), 1)
        self.assertIn('Условие для листка', rows[0]['statement'])


def _shell():
    from types import SimpleNamespace

    return SimpleNamespace(pk=None, name='Проба', is_exam=False,
                           manual_order=False, group=None, group_id=None,
                           deadline_at=None)


class BuildScreenMarkupTests(TestCase):
    """Кнопки и подписи экрана."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t12m', password='x',
                                             role='teacher')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def page(self):
        response = self.client.get('/teacher/assignment/build/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_block_name_matches_what_it_shows(self):
        html = self.page()
        self.assertIn('<h2>Состав работы</h2>', html)

    def test_student_view_is_a_separate_button(self):
        html = self.page()
        self.assertIn('Посмотреть, как увидит ученик', html)
        self.assertIn('id="bd-eyes-box"', html)

    def test_print_preview_button(self):
        html = self.page()
        self.assertIn('Предпросмотр печатного листа', html)
        self.assertIn('/teacher/assignment/cart/print/', html)

    def test_order_has_buttons_not_only_dragging(self):
        """⚠️ Перетаскивание недоступно с клавиатуры — кнопки обязательны."""
        html = self.page()
        self.assertIn('class="bd-up"', html)
        self.assertIn('class="bd-down"', html)
        self.assertIn('draggable="true"', html)

    def test_hidden_name_field_does_not_clash(self):
        """⚠️ Второй элемент с именем `name` делал `[name=name]`
        двусмысленным — сценарий находил первым скрытый."""
        html = self.page()
        self.assertIn('name="work_name"', html)
        self.assertEqual(html.count('name="name"'), 1)
