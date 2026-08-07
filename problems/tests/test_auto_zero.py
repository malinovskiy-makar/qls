"""
Автоматический ноль за пустой ответ (фаза 3 ночной сессии).

Правило целиком:
  • пусты И ответ, И решение → ноль ставится машиной, в очередь ручной
    проверки задача НЕ попадает;
  • ответ пуст, но решение написано → на ручную проверку, как раньше:
    ученик рассуждал, значит есть что читать;
  • оба заполнены → обычная проверка.

Стережём именно то, ради чего правило вводилось: репетитор не должен
тратить время на пустоту, но и не должен пропустить работу, где ответа нет,
а решение есть.
"""
from decimal import Decimal

from django.test import TestCase

from problems import part_grading
from problems.models import (
    Assignment, AssignmentItem, PartAnswer, ProblemPart, Submission,
)
from problems.tests.factories import make_problem, make_user


def open_problem_without_reference():
    """Открытая задача каталога БЕЗ утверждённого эталона.

    Именно такая и уходила раньше на ручную проверку всегда — в том числе
    когда ученик не написал ни строчки.
    """
    return make_problem('Найдите равновесную цену.', answer='')


class AutoZeroRuleTests(TestCase):

    def setUp(self):
        self.tutor = make_user('az_tutor', role='teacher')
        self.student = make_user('az_student', role='student')
        self.homework = Assignment.objects.create(name='ДЗ', author=self.tutor)
        self.homework.students.add(self.student)

    def _item(self, problem=None):
        return AssignmentItem.objects.create(
            assignment=self.homework, order=0,
            catalog_problem=problem or open_problem_without_reference())

    def _submit(self, item, answer='', solution=''):
        submission = Submission.objects.create(
            student=self.student, assignment=self.homework,
            problem=item.catalog_problem, problem_item=item,
            submitted_answer=answer, solution_text=solution,
            status='submitted')
        part_grading.apply_to_submission(submission, item, {None: answer})
        submission.save()
        return submission

    # -- случай 1: пусто всё ----------------------------------------------

    def test_both_empty_scored_zero_automatically(self):
        item = self._item()
        submission = self._submit(item, answer='', solution='')
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'reviewed',
                         'пустая работа не должна висеть в очереди проверки')
        self.assertEqual(Decimal(str(submission.feedback.score)), Decimal('0'))
        self.assertTrue(PartAnswer.objects.get(submission=submission).auto_zero)

    def test_auto_zero_says_there_was_no_answer(self):
        """Комментарий честный: «ответа не было», а не «неверно»."""
        item = self._item()
        submission = self._submit(item)
        self.assertIn('автоматически', submission.feedback.comment)
        self.assertIn('ответа не было', submission.feedback.comment)

    # -- случай 2: ответа нет, решение есть -------------------------------

    def test_solution_without_answer_goes_to_human(self):
        """Тот самый случай Петра: ответ пуст, но рассуждение написано."""
        item = self._item()
        submission = self._submit(
            item, answer='', solution='Приравнял спрос и предложение.')
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'submitted',
                         'решение написано — это работа, её читает человек')
        self.assertFalse(hasattr(submission, 'feedback'))
        self.assertFalse(PartAnswer.objects.get(submission=submission).auto_zero)

    # -- случай 3: заполнено ----------------------------------------------

    def test_answer_present_goes_the_usual_way(self):
        item = self._item()
        submission = self._submit(item, answer='30', solution='')
        submission.refresh_from_db()
        # Эталона нет — проверять нечем, задача честно ждёт человека.
        self.assertEqual(submission.status, 'submitted')
        self.assertFalse(PartAnswer.objects.get(submission=submission).auto_zero)

    # -- подпункты: правило по каждому отдельно ---------------------------

    def test_rule_applies_per_part(self):
        problem = make_problem('Задача с пунктами.')
        part_a = ProblemPart.objects.create(problem=problem, label='а',
                                            order=0, statement='Найдите TC.')
        part_b = ProblemPart.objects.create(problem=problem, label='б',
                                            order=1, statement='Найдите ATC.')
        item = self._item(problem)
        # Утверждаем эталон ТОЛЬКО для «а»: «б» проверять нечем.
        item.answer_override = {str(part_a.pk): '5000'}
        item.save(update_fields=['answer_override'])

        submission = Submission.objects.create(
            student=self.student, assignment=self.homework,
            problem=problem, problem_item=item, status='submitted')
        part_grading.apply_to_submission(
            submission, item, {part_a.pk: '5000', part_b.pk: ''})
        submission.save()

        answers = {a.part_id: a for a in
                   PartAnswer.objects.filter(submission=submission)}
        # «а» проверено машиной по эталону — это не автоноль.
        self.assertTrue(answers[part_a.pk].is_correct)
        self.assertFalse(answers[part_a.pk].auto_zero)
        # «б» пусто и решения нет — ноль автоматом.
        self.assertTrue(answers[part_b.pk].auto_zero)
        self.assertEqual(Decimal(str(answers[part_b.pk].score)), Decimal('0'))
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'reviewed')

    def test_written_solution_protects_every_part(self):
        """Решение одно на задачу — значит ни один пункт не обнуляется."""
        problem = make_problem('Задача с пунктами.')
        ProblemPart.objects.create(problem=problem, label='а', order=0,
                                   statement='Найдите TC.')
        ProblemPart.objects.create(problem=problem, label='б', order=1,
                                   statement='Найдите ATC.')
        item = self._item(problem)
        submission = Submission.objects.create(
            student=self.student, assignment=self.homework,
            problem=problem, problem_item=item, status='submitted',
            solution_text='Расписал через средние издержки.')
        parts = list(ProblemPart.objects.filter(problem=problem))
        part_grading.apply_to_submission(
            submission, item, {p.pk: '' for p in parts})
        submission.save()
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'submitted')
        self.assertFalse(
            PartAnswer.objects.filter(submission=submission,
                                      auto_zero=True).exists())

    # -- очередь проверки ---------------------------------------------------

    def test_pending_counter_drops(self):
        """Счётчик «ждёт проверки» пустышки больше не считает."""
        blank_item = self._item()
        self._submit(blank_item, answer='', solution='')
        real_item = AssignmentItem.objects.create(
            assignment=self.homework, order=1,
            catalog_problem=open_problem_without_reference())
        self._submit(real_item, answer='', solution='Что-то написал.')

        pending = Submission.objects.filter(assignment=self.homework,
                                            status='submitted').count()
        self.assertEqual(pending, 1,
                         'в очереди должна остаться только работа с решением')


class WroteAnythingTests(TestCase):
    """Что считается «ученик что-то написал»."""

    def setUp(self):
        self.tutor = make_user('az_tutor2', role='teacher')
        self.student = make_user('az_student2', role='student')
        self.homework = Assignment.objects.create(name='ДЗ2', author=self.tutor)

    def _submission(self, **kwargs):
        return Submission(student=self.student, assignment=self.homework,
                          **kwargs)

    def test_empty_is_empty(self):
        self.assertFalse(part_grading.wrote_anything(self._submission()))

    def test_whitespace_only_is_still_empty(self):
        self.assertFalse(part_grading.wrote_anything(
            self._submission(solution_text='   \n  \t ')))

    def test_text_counts(self):
        self.assertTrue(part_grading.wrote_anything(
            self._submission(solution_text='Приравнял спрос и предложение.')))

    def test_attached_file_counts(self):
        """Скан тетради — это работа, автоматический ноль за неё нельзя."""
        submission = self._submission()
        submission.solution_file = 'submissions/2026/08/skan.jpg'
        self.assertTrue(part_grading.wrote_anything(submission))
