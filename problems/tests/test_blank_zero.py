"""
Ноль вместо прочерка + четыре состояния проверки в демо-данных (фаза 2).

⚠️ ЗАЧЕМ. Правило «пусто и в ответе, и в решении, и файла нет → ноль ставит
машина» работало только для позиций, которые ученик хотя бы открыл. Приём
работы пропускал полностью пустую позицию ЦЕЛИКОМ, до всякой проверки, и она
оставалась «не начатой»: на экране прочерк вместо балла, в очередь проверки
не попадает, в сумму работы не входит. Худшее из двух — балла нет, и увидеть
позицию тоже нельзя.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems import part_grading
from problems.assignment_rows import item_max_score, part_max_score
from problems.models import (
    Assignment, AssignmentItem, ProblemPart, StudentGroup, Submission,
    TeacherFeedback,
)
from problems.tests.factories import make_problem, make_user
from problems.work_review import work_summary


class BlankPositionsGetZeroTests(TestCase):
    """Отправил работу — незаполненные задачи получают честный ноль."""

    def setUp(self):
        self.tutor = make_user('t-blank', role='teacher')
        self.student = make_user('s-blank', role='student')
        group = StudentGroup.objects.create(name='Группа', teacher=self.tutor)
        group.students.add(self.student)
        self.assignment = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=group)
        self.assignment.students.add(self.student)
        self.items = []
        for order in range(3):
            problem = make_problem('Задача %d.' % order, difficulty=2)
            self.items.append(AssignmentItem.objects.create(
                assignment=self.assignment, order=order,
                catalog_problem=problem, points=Decimal('2')))
        self.client.force_login(self.student)

    def _submit(self, data):
        return self.client.post(
            reverse('student:submit_assignment', args=[self.assignment.pk]),
            data)

    def _feedback(self, item):
        submission = Submission.objects.filter(
            student=self.student, problem_item=item).first()
        if submission is None:
            return None, None
        return submission, TeacherFeedback.objects.filter(
            submission=submission).first()

    def test_untouched_positions_get_zero_after_submit(self):
        from problems.assignment_rows import answer_input_name

        self._submit({answer_input_name(self.items[0], None): '42'})
        for item in self.items[1:]:
            submission, feedback = self._feedback(item)
            self.assertEqual(submission.status, 'reviewed', 'осталась не начата')
            self.assertIsNotNone(feedback, 'балла нет вовсе — это прочерк')
            self.assertEqual(feedback.score, Decimal('0'))

    def test_zero_for_blank_is_marked_as_automatic(self):
        """Ноль за пустоту помечен машинным и не идёт в очередь проверки."""
        from problems.assignment_rows import answer_input_name

        self._submit({answer_input_name(self.items[0], None): '42'})
        submission, feedback = self._feedback(self.items[1])
        self.assertIsNone(feedback.reviewed_by_id, 'выглядит как ручная оценка')
        self.assertTrue(part_grading.is_auto_zero(submission))
        # В очереди осталась только первая задача — по ней ученик ответил, а
        # эталон каталога не утверждён, значит её читает человек. Пустые
        # позиции в очередь не попали.
        self.assertEqual(
            list(Submission.objects.filter(assignment=self.assignment,
                                           status='submitted')
                 .values_list('problem_item_id', flat=True)),
            [self.items[0].pk])

    def test_blank_is_not_called_wrong_on_the_review_screen(self):
        """Ноль за пустоту — состояние «без ответа», а не «неверно».

        Ошибиться человек не успел, и говорить ему «неверно» — неправда.
        """
        from problems.assignment_rows import answer_input_name

        self._submit({answer_input_name(self.items[0], None): '42'})
        summary = work_summary(self.assignment, self.student)
        states = {row['item'].pk: row['state'] for row in summary['rows']}
        self.assertEqual(states[self.items[1].pk], 'blank')
        self.assertEqual(states[self.items[2].pk], 'blank')

    def test_totally_empty_submit_gives_no_zeros(self):
        """Пустая работа целиком не отправлена — раздавать нули не за что.

        Иначе случайное нажатие «Отправить» на нетронутой домашке закрыло бы
        её нулями до того, как ученик к ней приступил.
        """
        self._submit({})
        for item in self.items:
            submission, feedback = self._feedback(item)
            self.assertIsNone(feedback)
            self.assertNotEqual(submission.status, 'reviewed')

    def test_scores_sum_includes_blank_positions(self):
        """Итог работы считается по ВСЕМ задачам, а не только заполненным."""
        from problems.assignment_rows import answer_input_name

        self._submit({answer_input_name(self.items[0], None): '42'})
        summary = work_summary(self.assignment, self.student)
        self.assertEqual(Decimal(str(summary['max_score'])), Decimal('6'))
        # Первая задача каталога без утверждения ждёт человека, две пустые
        # уже закрыты нулём — «проверено» покрывает именно их.
        self.assertEqual(Decimal(str(summary['graded_max'])), Decimal('4'))


class BlankIsZeroEvenWithApprovedReferenceTests(TestCase):
    """Утверждение эталона не превращает «не отвечал» в «ошибся».

    ⚠️ Проверка автонуля стояла на «машина судить не смогла». Стоило
    репетитору утвердить эталон — и ученик, не написавший ни строчки,
    получал «неверно, правильный ответ: 5000».
    """

    def setUp(self):
        self.tutor = make_user('t-appr-blank', role='teacher')
        self.student = make_user('s-appr-blank', role='student')
        problem = make_problem('Фирма выпускает 100 единиц.', difficulty=2)
        self.part = ProblemPart.objects.create(
            problem=problem, label='а', order=0,
            statement='Найдите TC.', answer='5000')
        self.assignment = Assignment.objects.create(name='Работа',
                                                    author=self.tutor)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0, catalog_problem=problem,
            points=Decimal('2'), answer_override={str(self.part.pk): '5000'})
        self.submission = Submission.objects.create(
            student=self.student, assignment=self.assignment,
            problem=problem, problem_item=self.item, status='submitted')

    def test_blank_answer_reads_as_no_answer(self):
        part_grading.apply_to_submission(self.submission, self.item,
                                         {self.part.pk: ''})
        self.submission.save()
        feedback = TeacherFeedback.objects.get(submission=self.submission)
        self.assertEqual(feedback.score, Decimal('0'))
        self.assertEqual(feedback.comment, part_grading.BLANK_COMMENT)
        self.assertTrue(part_grading.is_auto_zero(self.submission))

    def test_wrong_answer_still_reads_as_wrong(self):
        part_grading.apply_to_submission(self.submission, self.item,
                                         {self.part.pk: '999'})
        self.submission.save()
        feedback = TeacherFeedback.objects.get(submission=self.submission)
        self.assertEqual(feedback.score, Decimal('0'))
        self.assertIn('неверно', feedback.comment.lower())
        self.assertFalse(part_grading.is_auto_zero(self.submission))


class PositionPointsWinTests(TestCase):
    """Балл позиции — правда, `ProblemPart.points` — только вес внутри неё.

    ⚠️ Демо-задача «Издержки фирмы» стоила на карточке 3 балла, а в сумме
    работы — 2: у обоих её пунктов в каталоге стоит по единице, и они молча
    перебивали то, что поставил репетитор.
    """

    def setUp(self):
        self.tutor = make_user('t-points', role='teacher')
        self.problem = make_problem('Задача с пунктами.', difficulty=2)
        self.a = ProblemPart.objects.create(problem=self.problem, label='а',
                                            order=0, statement='Найдите TC.',
                                            answer='1', points=Decimal('1'))
        self.b = ProblemPart.objects.create(problem=self.problem, label='б',
                                            order=1, statement='Найдите ATC.',
                                            answer='2', points=Decimal('1'))
        self.assignment = Assignment.objects.create(name='Работа',
                                                    author=self.tutor)
        self.item = AssignmentItem.objects.create(
            assignment=self.assignment, order=0, catalog_problem=self.problem,
            points=Decimal('3'))

    def test_parts_split_the_position_points(self):
        self.assertEqual(item_max_score(self.item), Decimal('3'))
        self.assertEqual(part_max_score(self.item, self.a, 2), Decimal('1.50'))
        self.assertEqual(part_max_score(self.item, self.b, 2), Decimal('1.50'))

    def test_catalog_weights_are_respected(self):
        """Веса 1 и 3 при позиции в 4 балла дают 1 и 3."""
        self.b.points = Decimal('3')
        self.b.save(update_fields=['points'])
        self.item.points = Decimal('4')
        self.item.save(update_fields=['points'])
        self.assertEqual(part_max_score(self.item, self.a, 2), Decimal('1.00'))
        self.assertEqual(part_max_score(self.item, self.b, 2), Decimal('3.00'))

    def test_half_marked_weights_split_evenly(self):
        """Вес есть не у всех пунктов — делим поровну, а не достраиваем."""
        self.b.points = None
        self.b.save(update_fields=['points'])
        self.assertEqual(part_max_score(self.item, self.a, 2), Decimal('1.50'))

    def test_parts_add_up_to_the_position_exactly(self):
        """Три пункта задачи на 10 баллов дают ровно 10, а не 9,99.

        ⚠️ Остаток округления виден на экране разбора работы: там стояло
        «— / 9,99 б.» у задачи, которая на карточке стоит 10.
        """
        third = ProblemPart.objects.create(problem=self.problem, label='в',
                                           order=2, statement='Найдите AVC.',
                                           answer='3')
        self.a.points = None
        self.a.save(update_fields=['points'])
        self.b.points = None
        self.b.save(update_fields=['points'])
        self.item.points = Decimal('10')
        self.item.save(update_fields=['points'])
        total = sum(part_max_score(self.item, part, 3)
                    for part in (self.a, self.b, third))
        self.assertEqual(total, Decimal('10'))


class DemoHasAllFourStatesTests(TestCase):
    """Демо обязано показывать всё, что умеет продукт.

    ⚠️ Без этого правило автонуля и янтарный вид карточки нельзя было
    увидеть глазами вовсе: счётчик «Ждёт проверки» показывал ноль, а
    неутверждённую позицию владелец получил, только сняв утверждение руками.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command('seed_platform_demo', verbosity=0)
        cls.homework = Assignment.objects.filter(
            name__startswith='Домашка №3').first()
        cls.student = cls.homework.students.order_by('pk').first()

    def _rows(self):
        return {row['item'].pk: row
                for row in work_summary(self.homework, self.student)['rows']}

    def test_state_1_blank_position_closed_automatically(self):
        rows = self._rows()
        blanks = [r for r in rows.values() if r['state'] == 'blank']
        self.assertTrue(blanks, 'нет позиции с автоматическим нулём')
        for row in blanks:
            self.assertEqual(Decimal(str(row['score'])), Decimal('0'))
            self.assertIsNone(row['feedback'].reviewed_by_id)

    def test_state_2_solution_without_answer_waits_for_human(self):
        waiting = [row for row in self._rows().values()
                   if row['state'] == 'pending'
                   and not (row['sub'].submitted_answer or '').strip()
                   and (row['sub'].solution_text or '').strip()]
        self.assertTrue(waiting, 'нет позиции «ответа нет, решение написано»')

    def test_state_3_unapproved_catalog_item_exists(self):
        unapproved = [item for item in self.homework.items.all()
                      if not item.is_test and not item.is_custom
                      and not item.answers_approved]
        self.assertTrue(unapproved,
                        'нет неутверждённой каталожной позиции — янтарное '
                        'состояние карточки не на чем посмотреть')

    def test_state_4_wrong_answer_scored_zero_by_machine(self):
        wrong = [row for row in self._rows().values()
                 if row['state'] == 'wrong'
                 and (row['sub'].submitted_answer or '').strip()]
        self.assertTrue(wrong, 'нет позиции с неверным ответом')
        for row in wrong:
            self.assertEqual(Decimal(str(row['score'])), Decimal('0'))
            self.assertIsNone(row['feedback'].reviewed_by_id)

    def test_waiting_counter_is_not_zero(self):
        pending = Submission.objects.filter(assignment=self.homework,
                                            status='submitted').count()
        self.assertGreater(pending, 0,
                           '«Ждёт проверки» показывает ноль — проверять нечего')

    def test_no_full_score_for_the_wrong_answer_30(self):
        """Ответ `30` на эластичность не имеет полного балла."""
        submission = Submission.objects.filter(
            assignment=self.homework, student=self.student,
            submitted_answer='30').first()
        self.assertIsNotNone(submission, 'демо-ответ `30` пропал')
        feedback = TeacherFeedback.objects.filter(
            submission=submission).first()
        if feedback is not None:
            self.assertLess(feedback.score,
                            item_max_score(submission.problem_item))
