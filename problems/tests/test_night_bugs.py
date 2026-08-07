"""
Одиннадцать багов приёмки (фаза 7 ночной сессии).

Каждый тест — про КОНКРЕТНЫЙ видимый дефект, найденный владельцем руками,
а не про «код работает». Номера совпадают с номерами в задании.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import (
    Assignment, AssignmentItem, CustomProblem, StudentGroup, Submission,
)
from problems.stats import needs_attention
from problems.timefmt import human_deadline
from problems.tests.factories import make_problem, make_user


class Bug71ProgressPageTests(TestCase):
    """7.1 — ошибка 500 на «Прогресс ученика»."""

    def setUp(self):
        self.tutor = make_user('b71_tutor', role='teacher')
        self.student = make_user('b71_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.client.force_login(self.tutor)

    def test_page_opens_when_submission_has_no_catalog_problem(self):
        """Работа по СВОЕЙ задаче репетитора: поля `problem` у неё нет.

        Именно на такой записи страница падала: код читал
        `submission.problem.problem_type`, а `problem` стал необязательным,
        когда появились свои задачи.
        """
        custom = CustomProblem.objects.create(
            owner=self.tutor, statement='Своя задача',
            kind=CustomProblem.Kind.OPEN, correct_answer='42')
        item = AssignmentItem.objects.create(assignment=self.work, order=0,
                                             custom_problem=custom)
        Submission.objects.create(student=self.student, assignment=self.work,
                                  problem=None, problem_item=item,
                                  status='reviewed')
        response = self.client.get(
            reverse('teacher:student_progress', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)

    def test_custom_test_counts_as_a_test(self):
        """Тип берётся у ПОЗИЦИИ: она знает про оба вида задач."""
        from teacher.views import _submission_is_test

        custom = CustomProblem.objects.create(
            owner=self.tutor, statement='Свой тест',
            kind=CustomProblem.Kind.SINGLE)
        item = AssignmentItem.objects.create(assignment=self.work, order=1,
                                             custom_problem=custom)
        sub = Submission.objects.create(student=self.student,
                                        assignment=self.work,
                                        problem_item=item, status='reviewed')
        self.assertTrue(_submission_is_test(sub))


class Bug74SortTests(TestCase):
    """7.4 — задания сортируются по дедлайну, ближайшие первыми."""

    def setUp(self):
        self.tutor = make_user('b74_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.client.force_login(self.tutor)
        now = timezone.now()
        self.far = Assignment.objects.create(
            name='Далёкая', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=10))
        self.near = Assignment.objects.create(
            name='Ближняя', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=1))
        self.past = Assignment.objects.create(
            name='Прошедшая', author=self.tutor, group=self.group,
            deadline=now - timedelta(days=5))
        self.none = Assignment.objects.create(
            name='Без срока', author=self.tutor, group=self.group)

    def _names(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        return [row['assignment'].name
                for row in response.context['assignment_rows']]

    def test_sorted_by_deadline(self):
        self.assertEqual(self._names(),
                         ['Прошедшая', 'Ближняя', 'Далёкая', 'Без срока'])

    def test_undated_goes_last(self):
        """У задания без срока нет места на шкале — оно не должно быть первым."""
        self.assertEqual(self._names()[-1], 'Без срока')


class Bug75CheckedBadgeTests(TestCase):
    """7.5 — «проверено» только когда было что проверять."""

    def setUp(self):
        self.tutor = make_user('b75_tutor', role='teacher')
        self.student = make_user('b75_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'))
        self.client.force_login(self.tutor)

    def _row(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        return response.context['assignment_rows'][0]

    def test_nobody_submitted_is_not_checked(self):
        row = self._row()
        self.assertTrue(row['nobody_submitted'])
        self.assertFalse(row['all_checked'])

    def test_badge_says_nobody_submitted(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        body = response.content.decode()
        self.assertIn('никто не сдал', body)
        self.assertNotIn('>проверено<', body)

    def test_checked_only_after_a_real_submission(self):
        Submission.objects.create(student=self.student, assignment=self.work,
                                  problem_item=self.item, status='reviewed')
        row = self._row()
        self.assertFalse(row['nobody_submitted'])
        self.assertTrue(row['all_checked'])


class Bug78TitlesTests(TestCase):
    """7.8 — в сводке решений нормальное название, а не «Задача #»."""

    def test_statement_start_instead_of_the_id(self):
        tutor = make_user('b78_tutor', role='teacher')
        student = make_user('b78_student', role='student')
        group = StudentGroup.objects.create(name='Гр', teacher=tutor)
        work = Assignment.objects.create(name='ДЗ', author=tutor, group=group)
        work.students.add(student)
        problem = make_problem(
            'Фирма выпускает 100 единиц, постоянные издержки 2000 рублей.')
        item = AssignmentItem.objects.create(assignment=work, order=0,
                                             catalog_problem=problem)
        Submission.objects.create(student=student, assignment=work,
                                  problem=problem, problem_item=item,
                                  status='submitted')
        self.client.force_login(tutor)
        body = self.client.get(
            reverse('teacher:group_submissions',
                    args=[group.pk, work.pk])).content.decode()
        self.assertIn('Фирма выпускает', body)
        self.assertNotIn('Задача #%d' % problem.pk, body)


class Bug79WordCutTests(TestCase):
    """7.9 — обрезка условия по СЛОВАМ: число нельзя рвать пополам."""

    def test_numbers_are_not_split(self):
        from teacher.picker import word_cut

        text = ('Фирма выпускает продукцию, её постоянные издержки равны '
                '2000 рублей, а переменные — 3000 рублей в месяц всего')
        cut = word_cut(text, 100)
        self.assertTrue(cut.endswith('…'))
        # Обрезка ровно по границе слова: обрубка числа быть не должно.
        self.assertNotIn('300…', cut)
        self.assertNotIn('200…', cut)

    def test_short_text_is_untouched(self):
        from teacher.picker import word_cut

        self.assertEqual(word_cut('Коротко', 100), 'Коротко')


class Bug710HumanDeadlineTests(TestCase):
    """7.10 — срок по-человечески, точная дата в подсказке."""

    def setUp(self):
        self.now = timezone.now().replace(hour=12, minute=0, second=0,
                                          microsecond=0)

    def test_tomorrow(self):
        self.assertTrue(
            human_deadline(self.now + timedelta(days=1), self.now)
            .startswith('завтра до '))

    def test_in_three_days(self):
        self.assertEqual(
            human_deadline(self.now + timedelta(days=3), self.now),
            'через 3 дня')

    def test_two_days_ago(self):
        self.assertEqual(
            human_deadline(self.now - timedelta(days=2), self.now),
            'прошёл 2 дня назад')

    def test_today(self):
        self.assertTrue(
            human_deadline(self.now + timedelta(hours=3), self.now)
            .startswith('сегодня до '))

    def test_no_deadline_is_an_empty_string(self):
        """Пусто — решает вызывающий, писать ли «без срока»."""
        self.assertEqual(human_deadline(None), '')

    def test_calendar_days_not_twenty_four_hours(self):
        """Сегодня 23:00 и завтра 01:00 — это «сегодня» и «завтра».

        ⚠️ Моменты строим в МЕСТНОМ поясе, а не в UTC. Проект живёт в
        UTC+3: «23:00 UTC» — это уже 02:00 следующего дня по Москве, и
        тест, собранный в UTC, проверял бы не то, что видит человек.
        """
        from problems.timefmt import local

        here = local(self.now)
        late = here.replace(hour=23, minute=0)
        soon = (here + timedelta(days=1)).replace(hour=1, minute=0)
        self.assertTrue(human_deadline(late, self.now).startswith('сегодня'))
        self.assertTrue(human_deadline(soon, self.now).startswith('завтра'))


class Bug711StaleReviewTests(TestCase):
    """7.11 — четвёртое условие плашки: работа ждёт ВАШЕЙ проверки."""

    def setUp(self):
        self.tutor = make_user('b711_tutor', role='teacher')
        self.student = make_user('b711_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        self.work.students.add(self.student)
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'))

    def _submit(self, days_ago):
        return Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='submitted',
            submitted_at=timezone.now() - timedelta(days=days_ago))

    def _reasons(self):
        rows = needs_attention(self.group)
        for row in rows:
            if row['student'].pk == self.student.pk:
                return row['reasons']
        return []

    def test_fresh_submission_is_not_flagged(self):
        self._submit(1)
        self.assertFalse([r for r in self._reasons() if 'вашей проверки' in r])

    def test_stale_submission_is_flagged(self):
        self._submit(4)
        stale = [r for r in self._reasons() if 'вашей проверки' in r]
        self.assertEqual(len(stale), 1)
        self.assertIn('4 дня', stale[0])

    def test_wording_is_about_the_tutor(self):
        """Формулировка про репетитора, а не «ученик виноват»."""
        self._submit(5)
        stale = [r for r in self._reasons() if 'вашей проверки' in r][0]
        self.assertIn('вашей проверки', stale)
        self.assertNotIn('не сдал', stale)

    def test_reviewed_work_does_not_count(self):
        sub = self._submit(9)
        sub.status = 'reviewed'
        sub.save()
        self.assertFalse([r for r in self._reasons() if 'вашей проверки' in r])
