"""
Группировка работы: сначала тесты, потом открытые задачи (фаза 4).

Правило и его единственное исключение:
  • по умолчанию тесты уходят в начало, открытые задачи в конец;
  • если репетитор расставил порядок сам (`Assignment.manual_order`),
    перестановки НЕТ — его замысел главнее нашего формального признака.

Подписи «Тестовая часть» и «Задачи» ставятся только когда в работе есть обе
части: делить работу из одних тестов не на что.
"""
from django.test import TestCase

from problems.assignment_rows import (
    build_rows, item_section, ordered_items, section_marks,
)
from problems.assignment_export import print_rows
from problems.models import Assignment, ProblemPart
from problems.tests.factories import make_item, make_problem, make_user


def a_test(title='Тест'):
    problem = make_problem('Верно ли утверждение?', title=title,
                           answer='а', problem_type='тест: один ответ')
    for order, label in enumerate(('а', 'б')):
        ProblemPart.objects.create(problem=problem, label=label,
                                   statement='вариант', order=order)
    return problem


def a_task(title='Задача'):
    return make_problem('Найдите равновесие.', title=title)


class OrderingTests(TestCase):

    def setUp(self):
        self.tutor = make_user('so_tutor', role='teacher')
        self.student = make_user('so_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ',
                                                  author=self.tutor)
        self.homework.students.add(self.student)

    def _mixed(self):
        """Задача, тест, задача, тест — намеренно вперемешку."""
        make_item(self.homework, catalog_problem=a_task('З1'), order=0)
        make_item(self.homework, catalog_problem=a_test('Т1'), order=1)
        make_item(self.homework, catalog_problem=a_task('З2'), order=2)
        make_item(self.homework, catalog_problem=a_test('Т2'), order=3)

    def test_tests_go_first(self):
        self._mixed()
        titles = [i.problem_title for i in ordered_items(self.homework)]
        self.assertEqual(titles, ['Т1', 'Т2', 'З1', 'З2'])

    def test_order_inside_part_is_kept(self):
        """Перестановка групповая: внутри части порядок репетитора цел."""
        make_item(self.homework, catalog_problem=a_test('Т-второй'), order=5)
        make_item(self.homework, catalog_problem=a_test('Т-первый'), order=1)
        titles = [i.problem_title for i in ordered_items(self.homework)]
        self.assertEqual(titles, ['Т-первый', 'Т-второй'])

    def test_manual_order_wins(self):
        """Порядок задан человеком — не трогаем ничего."""
        self._mixed()
        self.homework.manual_order = True
        self.homework.save(update_fields=['manual_order'])
        titles = [i.problem_title for i in ordered_items(self.homework)]
        self.assertEqual(titles, ['З1', 'Т1', 'З2', 'Т2'])

    def test_section_of_item(self):
        self.assertEqual(
            item_section(make_item(self.homework,
                                   catalog_problem=a_test())), 'test')
        self.assertEqual(
            item_section(make_item(self.homework,
                                   catalog_problem=a_task())), 'task')


class SectionMarkTests(TestCase):

    def setUp(self):
        self.tutor = make_user('sm_tutor', role='teacher')
        self.student = make_user('sm_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ2',
                                                  author=self.tutor)
        self.homework.students.add(self.student)

    def test_two_marks_on_first_of_each_part(self):
        make_item(self.homework, catalog_problem=a_test('Т1'), order=0)
        make_item(self.homework, catalog_problem=a_test('Т2'), order=1)
        make_item(self.homework, catalog_problem=a_task('З1'), order=2)
        items = ordered_items(self.homework)
        marks = section_marks(items)
        self.assertEqual(sorted(marks), [0, 2])
        # ⚠️ Заголовок части НЕСЁТ СОСТАВ (ревью 15.08, фаза 7): без него
        # разделение читалось как случайная черта посреди списка.
        self.assertEqual(marks[0]['title'], 'Тестовая часть')
        self.assertEqual(marks[0]['count'], 2)
        self.assertEqual(marks[2]['title'], 'Задачи')
        self.assertEqual(marks[2]['count'], 1)
        self.assertIn('2 вопроса', marks[0]['detail'])
        self.assertIn('1 задача', marks[2]['detail'])

    def test_only_tests_no_marks(self):
        make_item(self.homework, catalog_problem=a_test('Т1'), order=0)
        make_item(self.homework, catalog_problem=a_test('Т2'), order=1)
        self.assertEqual(section_marks(ordered_items(self.homework)), {})

    def test_only_tasks_no_marks(self):
        make_item(self.homework, catalog_problem=a_task('З1'), order=0)
        self.assertEqual(section_marks(ordered_items(self.homework)), {})

    def test_rows_carry_the_mark(self):
        make_item(self.homework, catalog_problem=a_task('З1'), order=0)
        make_item(self.homework, catalog_problem=a_test('Т1'), order=1)
        rows = build_rows(self.homework, self.student)
        self.assertEqual([r['title'] for r in rows], ['Т1', 'З1'])
        self.assertEqual([r['section_head']['title'] if r['section_head']
                          else '' for r in rows],
                         ['Тестовая часть', 'Задачи'])

    def test_print_sheet_matches_the_screen(self):
        """Порядок и подписи в листке — те же, что на экране."""
        make_item(self.homework, catalog_problem=a_task('З1'), order=0)
        make_item(self.homework, catalog_problem=a_test('Т1'), order=1)
        make_item(self.homework, catalog_problem=a_task('З2'), order=2)
        screen = build_rows(self.homework, self.student)
        sheet, _ = print_rows(self.homework)
        self.assertEqual([r['title'] for r in screen],
                         [r['title'] for r in sheet])
        self.assertEqual([r['section_head'] for r in screen],
                         [r['section_head'] for r in sheet])

    def test_manual_order_kills_the_marks_too(self):
        """Ручной порядок — значит и делить на части мы не вправе."""
        make_item(self.homework, catalog_problem=a_task('З1'), order=0)
        make_item(self.homework, catalog_problem=a_test('Т1'), order=1)
        make_item(self.homework, catalog_problem=a_task('З2'), order=2)
        self.homework.manual_order = True
        self.homework.save(update_fields=['manual_order'])
        rows = build_rows(self.homework, self.student)
        self.assertEqual([r['title'] for r in rows], ['З1', 'Т1', 'З2'])
        # Части чередуются: подпись «Тестовая часть» встала бы посреди
        # списка перед одним тестом и обещала бы часть, которой нет.
        self.assertEqual([r['section_head'] for r in rows],
                         [None, None, None])

    def test_manual_order_that_happens_to_be_grouped_keeps_marks(self):
        """Ручной порядок, но фактически сгруппировано — подписи правдивы."""
        make_item(self.homework, catalog_problem=a_test('Т1'), order=0)
        make_item(self.homework, catalog_problem=a_task('З1'), order=1)
        make_item(self.homework, catalog_problem=a_task('З2'), order=2)
        self.homework.manual_order = True
        self.homework.save(update_fields=['manual_order'])
        rows = build_rows(self.homework, self.student)
        self.assertEqual([r['title'] for r in rows], ['Т1', 'З1', 'З2'])
        self.assertEqual([(r['section_head'] or {}).get('title', '')
                          for r in rows],
                         ['Тестовая часть', 'Задачи', ''])
