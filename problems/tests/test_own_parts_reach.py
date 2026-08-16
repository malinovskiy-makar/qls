"""
Пункты СВОЕЙ задачи репетитора обязаны доходить до КАЖДОГО выхода.

⚠️ ПОЧЕМУ ЭТОТ ФАЙЛ ПОЯВИЛСЯ. Пункты своей задачи лежат в своей таблице
(`CustomProblemPart`) — `ProblemPart` ссылается на каталог, куда задача
репетитора не попадает никогда. Когда таблицу заводили, про неё узнала
только сторона ВВОДА (`answer_parts`): четыре экрана независимо писали
`item.catalog_problem.parts.all()` и у своей задачи получали пустоту. Ученик
получал задачу БЕЗ ВОПРОСОВ — на экране, в печатном листке и в `.tex`
одновременно, и ни один тест этого не видел.

Отсюда правило и этот файл: пункты спрашивает ОДНА функция
(`assignment_rows.display_parts`), а тест обходит ВСЕ выходы разом. Проверка
одного экрана здесь бесполезна — дефект был именно в том, что экранов много,
а общей сборки не было.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems.assignment_export import build_tex, print_rows
from problems.assignment_rows import answer_gist, build_rows, display_parts
from problems.models import (
    Assignment, AssignmentItem, Problem, ProblemPart, StudentGroup, User,
)
from problems.models_platform import CustomProblem, CustomProblemPart


def make_user(username, role='teacher'):
    user = User.objects.create_user(username=username, password='x12345678',
                                    email='%s@t.local' % username)
    user.role = role
    user.save()
    return user


class OwnPartsBase(TestCase):
    """Работа из ОДНОЙ своей задачи с двумя пунктами — как у владельца."""

    # Слова ищем такие, каких заведомо нет в разметке страницы: подпись
    # пункта «а)» встречается на экране и без наших пунктов.
    A_TEXT = 'Найдите общие издержки'
    B_TEXT = 'Найдите средние издержки'

    def setUp(self):
        self.tutor = make_user('op_tutor')
        self.student = make_user('op_student', 'student')
        self.group = StudentGroup.objects.create(name='Занятие пунктов',
                                                 teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(
            name='Работа со своей задачей', author=self.tutor,
            group=self.group)
        self.work.students.add(self.student)

        self.problem = CustomProblem.objects.create(
            owner=self.tutor, title='Издержки фирмы',
            statement='Фирма выпускает 200 единиц товара.',
            kind=CustomProblem.Kind.OPEN)
        self.part_a = CustomProblemPart.objects.create(
            problem=self.problem, label='а', statement=self.A_TEXT + ' (TC).',
            answer='12000', points=Decimal('1'), order=0)
        self.part_b = CustomProblemPart.objects.create(
            problem=self.problem, label='б', statement=self.B_TEXT + ' (ATC).',
            answer='60', points=Decimal('2'), order=1)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0, custom_problem=self.problem,
            points=Decimal('9'))

    def as_tutor(self):
        self.client.force_login(self.tutor)

    def as_student(self):
        self.client.force_login(self.student)

    def both_parts(self, text, where):
        self.assertIn(self.A_TEXT, text, '%s: пункт «а» не дошёл' % where)
        self.assertIn(self.B_TEXT, text, '%s: пункт «б» не дошёл' % where)


class NineOutputsTests(OwnPartsBase):
    """Девять выходов, перечисленных владельцем. Каждый — отдельная проверка."""

    def test_1_assignment_screen(self):
        """Экран задания у репетитора."""
        self.as_tutor()
        page = self.client.get(reverse('teacher:group_assignment',
                                       args=[self.group.pk, self.work.pk]))
        self.assertEqual(page.status_code, 200)
        self.both_parts(page.content.decode(), 'экран задания')

    def test_2_submissions_summary(self):
        """Сводка решений открывается и знает про задачу с пунктами."""
        self.as_tutor()
        page = self.client.get(reverse('teacher:group_submissions',
                                       args=[self.group.pk, self.work.pk]))
        self.assertEqual(page.status_code, 200)

    def test_3_work_review_by_student_eyes(self):
        """Разбор работы глазами ученика (экран репетитора)."""
        self.as_tutor()
        page = self.client.get(
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.work.pk, self.student.pk]))
        self.assertEqual(page.status_code, 200)
        self.both_parts(page.content.decode(), 'разбор глазами ученика')

    def test_4_work_done(self):
        """Итоги проверки."""
        self.as_tutor()
        page = self.client.get(reverse('teacher:work_done',
                                       args=[self.group.pk, self.work.pk,
                                             self.student.pk]))
        self.assertEqual(page.status_code, 200)

    def test_5_student_page(self):
        """Страница работы у ученика — там, где он и отвечает."""
        self.as_student()
        page = self.client.get(reverse('student:assignment_detail',
                                       args=[self.work.pk]))
        self.assertEqual(page.status_code, 200)
        self.both_parts(page.content.decode(), 'страница ученика')

    def test_6_print_for_student(self):
        """Печать ученикам."""
        self.as_tutor()
        page = self.client.get(
            reverse('teacher:assignment_print',
                    args=[self.group.pk, self.work.pk]) + '?for=student')
        self.assertEqual(page.status_code, 200)
        self.both_parts(page.content.decode(), 'печать ученикам')

    def test_7_print_for_teacher(self):
        """Печать с ответами: и вопросы, и эталоны пунктов."""
        self.as_tutor()
        page = self.client.get(
            reverse('teacher:assignment_print',
                    args=[self.group.pk, self.work.pk]) + '?for=teacher')
        self.assertEqual(page.status_code, 200)
        text = page.content.decode()
        self.both_parts(text, 'печать с ответами')
        self.assertIn('12000', text)
        self.assertIn('60', text)

    def test_8_tex_for_student(self):
        """`.tex` ученикам."""
        tex, skipped = build_tex(self.work, for_teacher=False)
        self.assertEqual(skipped, [])
        self.both_parts(tex, '.tex ученикам')

    def test_9_tex_for_teacher(self):
        """`.tex` с ответами — вопросы и эталоны рядом."""
        tex, _ = build_tex(self.work, for_teacher=True)
        self.both_parts(tex, '.tex с ответами')
        self.assertIn('12000', tex)

    def test_10_builder_preview(self):
        """Предпросмотр из конструктора — он работал и обязан работать дальше.

        Отвечает JSON, поэтому сверяем разобранные поля, а не текст ответа:
        кириллица в нём экранирована, и поиск по подстроке нашёл бы пустоту
        при совершенно правильном ответе.
        """
        self.as_tutor()
        page = self.client.get(reverse('teacher:api_problem_detail',
                                       args=['c%d' % self.problem.pk]))
        self.assertEqual(page.status_code, 200)
        self.both_parts(' '.join(p['text'] for p in page.json()['parts']),
                        'предпросмотр конструктора')


class DisplayPartsRuleTests(OwnPartsBase):
    """Правила самой функции — чтобы её не «починили» обратно."""

    def test_custom_parts_are_found(self):
        parts = display_parts(self.item)
        self.assertEqual([p.pk for p in parts],
                         [self.part_a.pk, self.part_b.pk])

    def test_catalog_parts_still_found(self):
        """Каталожная задача ведёт себя как раньше — правило одно на обе."""
        problem = Problem.objects.create(title='Каталожная',
                                         statement='Условие', status='published')
        ProblemPart.objects.create(problem=problem, label='а',
                                   statement='Первый вопрос', order=0)
        item = AssignmentItem.objects.create(assignment=self.work, order=1,
                                             catalog_problem=problem)
        self.assertEqual([p.label for p in display_parts(item)], ['а'])

    def test_empty_statement_part_is_not_a_question(self):
        """Пункт без условия — мусор импорта, а не вопрос."""
        CustomProblemPart.objects.create(problem=self.problem, label='в',
                                         statement='   ', order=2)
        self.assertEqual(len(display_parts(self.item)), 2)

    def test_test_options_are_not_drawn_as_parts(self):
        """У теста подпункты — это варианты ответа, второй раз их не рисуем."""
        test = CustomProblem.objects.create(
            owner=self.tutor, title='Свой тест', statement='Верно ли?',
            kind=CustomProblem.Kind.SINGLE)
        test.options.create(text='Да', is_correct=True, order=0)
        test.options.create(text='Нет', is_correct=False, order=1)
        item = AssignmentItem.objects.create(assignment=self.work, order=2,
                                             custom_problem=test)
        self.assertEqual(display_parts(item), [])

    def test_rows_carry_parts(self):
        """Общая сборка строк отдаёт пункты — с неё живут три экрана."""
        rows = build_rows(self.work, self.student, user=self.student)
        self.assertEqual(len(rows[0]['parts']), 2)

    def test_print_rows_carry_parts(self):
        rows, _ = print_rows(self.work)
        self.assertEqual([p['label'] for p in rows[0]['parts']], ['а', 'б'])
        self.assertEqual(rows[0]['parts'][0]['answer'], '12000')


class AnswerGistTests(OwnPartsBase):
    """Плашка «проверяется само» обязана говорить правду про эталон."""

    def test_gist_lists_part_answers(self):
        self.assertEqual(answer_gist(self.item), 'а) 12000 · б) 60')

    def test_gist_empty_when_no_reference_answer(self):
        """Ни одного эталона — плашка не имеет права обещать автопроверку."""
        self.problem.parts.update(answer='')
        self.item.refresh_from_db()
        self.assertEqual(answer_gist(self.item), '')

    def test_screen_says_manual_when_gist_empty(self):
        self.problem.parts.update(answer='')
        self.as_tutor()
        page = self.client.get(reverse('teacher:group_assignment',
                                       args=[self.group.pk, self.work.pk]))
        text = page.content.decode()
        self.assertIn('эталон не задан', text)
        self.assertNotIn('задан разметкой', text)
