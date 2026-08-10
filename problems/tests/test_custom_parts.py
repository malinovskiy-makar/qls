"""
Пункты (а, б, в) в СВОЕЙ задаче репетитора (п. 15.1).

⚠️ ЭТО ЕДИНСТВЕННАЯ ФАЗА РЕВЬЮ, КОТОРАЯ ТРОГАЕТ АВТОПРОВЕРКУ, поэтому
проверяем её насквозь: приём ответов, балл по каждому пункту, веса и
задачу БЕЗ пунктов (она обязана вести себя ровно как раньше).

Правило, которое здесь держится: ноль пунктов — это задача без пунктов,
частный случай «одного пункта», а не вторая ветка логики.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems import part_grading
from problems.assignment_rows import (
    answer_input_name, answer_parts, part_key, part_max_score,
)
from problems.models import (
    Assignment, AssignmentItem, PartAnswer, StudentGroup, Submission, User,
)
from problems.models_platform import CustomProblem, CustomProblemPart


def make_user(username, role='teacher'):
    user = User.objects.create_user(username=username, password='x12345678',
                                    email='%s@t.local' % username)
    user.role = role
    user.save()
    return user


class CustomPartsBase(TestCase):

    def setUp(self):
        self.tutor = make_user('cp_tutor')
        self.student = make_user('cp_student', 'student')
        self.group = StudentGroup.objects.create(name='Группа пунктов',
                                                 teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='Работа с пунктами',
                                              author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)

    def custom(self, parts=(), points='10'):
        problem = CustomProblem.objects.create(
            owner=self.tutor, title='Своя задача',
            statement='Спрос $Q_d = 100 - 2P$', kind=CustomProblem.Kind.OPEN,
            correct_answer='20')
        for order, (label, answer, weight) in enumerate(parts):
            CustomProblemPart.objects.create(
                problem=problem, label=label, statement='Вопрос %s' % label,
                answer=answer, points=weight, order=order)
        item = AssignmentItem.objects.create(
            assignment=self.work, order=0, custom_problem=problem,
            points=Decimal(points))
        return problem, item

    def submit(self, item, values):
        submission = Submission.objects.create(
            student=self.student, assignment=self.work, problem_item=item,
            status='draft')
        part_grading.apply_to_submission(submission, item, values)
        submission.save()
        return submission


class PartsPipelineTests(CustomPartsBase):

    def test_no_parts_behaves_exactly_as_before(self):
        """Ноль пунктов — задача без пунктов: один ответ на всю задачу."""
        _, item = self.custom()
        parts = answer_parts(item)
        self.assertEqual(parts, [None])
        submission = self.submit(item, {None: '20'})
        feedback = submission.feedback
        self.assertEqual(float(feedback.score), 10.0)

    def test_two_parts_of_equal_weight(self):
        _, item = self.custom(parts=[('а', '20', None), ('б', '60', None)])
        parts = answer_parts(item)
        self.assertEqual([p.label for p in parts], ['а', 'б'])
        submission = self.submit(item, {part_key(parts[0]): '20',
                                        part_key(parts[1]): '60'})
        self.assertEqual(float(submission.feedback.score), 10.0)

    def test_partially_correct_gets_partial_score(self):
        """«а» и «б» — разные вопросы: верное «а» остаётся верным."""
        _, item = self.custom(parts=[('а', '20', None), ('б', '60', None)])
        parts = answer_parts(item)
        submission = self.submit(item, {part_key(parts[0]): '20',
                                        part_key(parts[1]): '999'})
        self.assertEqual(float(submission.feedback.score), 5.0)
        answers = {a.custom_part.label: a for a
                   in PartAnswer.objects.filter(submission=submission)
                   .select_related('custom_part')}
        self.assertTrue(answers['а'].is_correct)
        self.assertFalse(answers['б'].is_correct)

    def test_weights_split_the_item_points(self):
        """⚠️ Балл позиции — правда, вес пункта — только вес: 1 и 3 из пяти
        баллов дают 1,25 и 3,75."""
        _, item = self.custom(parts=[('а', '20', Decimal('1')),
                                     ('б', '60', Decimal('3'))],
                              points='5')
        parts = answer_parts(item)
        self.assertEqual(part_max_score(item, parts[0], 2), Decimal('1.25'))
        self.assertEqual(part_max_score(item, parts[1], 2), Decimal('3.75'))

    def test_answers_are_stored_in_their_own_rows(self):
        """⚠️ Пункт своей задачи хранится своей ссылкой: номера в двух
        таблицах свои, и пункт №3 каталога — не пункт №3 своей задачи."""
        _, item = self.custom(parts=[('а', '20', None), ('б', '60', None)])
        parts = answer_parts(item)
        submission = self.submit(item, {part_key(parts[0]): '20',
                                        part_key(parts[1]): '60'})
        rows = list(PartAnswer.objects.filter(submission=submission))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.part_id is None for row in rows))
        self.assertEqual({row.custom_part_id for row in rows},
                         {parts[0].pk, parts[1].pk})

    def test_field_names_do_not_collide_with_catalog_parts(self):
        _, item = self.custom(parts=[('а', '20', None)])
        part = answer_parts(item)[0]
        self.assertIn('part_c%d' % part.pk, answer_input_name(item, part))

    def test_own_tolerance_per_part(self):
        """Допуск СВОЙ у каждого пункта."""
        problem, item = self.custom(parts=[('а', '20', None)])
        part = problem.parts.first()
        part.answer_tolerance = Decimal('0.5')
        part.save()
        submission = self.submit(item, {part_key(answer_parts(item)[0]): '20.4'})
        self.assertEqual(float(submission.feedback.score), 10.0)

    def test_blank_part_gets_the_auto_zero(self):
        """Правило автонуля работает ПО КАЖДОМУ пункту."""
        _, item = self.custom(parts=[('а', '20', None), ('б', '60', None)])
        parts = answer_parts(item)
        submission = self.submit(item, {part_key(parts[0]): '20',
                                        part_key(parts[1]): ''})
        answers = {a.custom_part.label: a for a
                   in PartAnswer.objects.filter(submission=submission)
                   .select_related('custom_part')}
        self.assertTrue(answers['б'].auto_zero)
        self.assertEqual(float(answers['б'].score), 0.0)

    def test_test_kind_never_gets_parts(self):
        """У теста подпункты играют роль вариантов — своих полей нет."""
        problem = CustomProblem.objects.create(
            owner=self.tutor, statement='Верно?', kind=CustomProblem.Kind.TF)
        CustomProblemPart.objects.create(problem=problem, label='а',
                                         statement='лишний', answer='1')
        item = AssignmentItem.objects.create(assignment=self.work, order=1,
                                             custom_problem=problem)
        self.assertEqual(answer_parts(item), [None])

    def test_applies_is_untouched(self):
        """⚠️ Стоп-гейт владельца: `part_grading.applies` не переделан."""
        _, item = self.custom(parts=[('а', '20', None)])
        self.assertTrue(part_grading.applies(item))


class PartsEditorTests(TestCase):
    """Форма своей задачи: пункты заводятся, сохраняются и возвращаются."""

    def setUp(self):
        self.tutor = make_user('cpe_tutor')
        self.client.force_login(self.tutor)

    def post(self, **extra):
        data = {
            'kind': 'open', 'statement': 'Условие задачи',
            'correct_answer': '', 'answer_tolerance': '0',
            'part_label': ['', ''],
            'part_statement': ['Найдите цену', 'Найдите количество'],
            'part_answer': ['20', '60'],
            'part_tolerance': ['0', '0'],
            'part_points': ['1', '3'],
        }
        data.update(extra)
        return self.client.post(reverse('teacher:problem_new'), data)

    def test_parts_are_saved_with_default_letters(self):
        self.post()
        problem = CustomProblem.objects.get(owner=self.tutor)
        labels = list(problem.parts.values_list('label', flat=True))
        self.assertEqual(labels, ['а', 'б'])
        self.assertEqual(list(problem.parts.values_list('answer', flat=True)),
                         ['20', '60'])

    def test_empty_statement_makes_no_part(self):
        """Пустая строка — не пункт: репетитор нажал «+ Пункт» и передумал."""
        self.post(part_statement=['Найдите цену', '   '],
                  part_answer=['20', '60'])
        problem = CustomProblem.objects.get(owner=self.tutor)
        self.assertEqual(problem.parts.count(), 1)

    def test_test_kind_drops_parts(self):
        """У теста пунктов быть не должно — даже если поля приехали."""
        self.post(kind='single', option_text=['Раз', 'Два'],
                  option_correct_0='on')
        problem = CustomProblem.objects.get(owner=self.tutor)
        self.assertEqual(problem.parts.count(), 0)

    def test_parts_come_back_to_the_form(self):
        self.post()
        problem = CustomProblem.objects.get(owner=self.tutor)
        body = self.client.get(reverse('teacher:problem_edit',
                                       args=[problem.pk])).content.decode()
        self.assertIn('Найдите цену', body)
        self.assertIn('name="part_answer"', body)
