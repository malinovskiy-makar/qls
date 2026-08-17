# -*- coding: utf-8 -*-
"""
Числа, которые врут (ревью 17.08, фаза 2).

Три дефекта одного рода — на экране стоит число, которое не значит того,
что написано рядом с ним:

  2.1 «Сдано работ 25 (7 ждёт)» у вкладки «Обзор» против «3 работы ждут
      проверки» у вкладки «Задания» ОДНОЙ группы с одиннадцатью заданиями:
      таблица считала строки `Submission`, а они заводятся на КАЖДУЮ ЗАДАЧУ;
  2.2 «2,5 из 18» в сводке решений и «2,5 из 13» в разборе той же работы:
      второй экран делил на максимум только проверенных задач;
  2.3 «Лучший день — 275» у ученика, решившего за месяц 55 задач;
  2.4 «3 баллов» на странице задания.
"""
import datetime
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.assignment_rows import point_word, points_text
from problems.gamification import best_day_of, update_records
from problems.models import (
    Assignment, AssignmentItem, LearningEvent, PersonalRecord, Problem,
    StudentGroup, Submission, TeacherFeedback, User,
)
from problems.work_review import work_summary


class WaitingUnitBase(TestCase):
    """2.1 — «работа» значит одно и то же во всех трёх местах."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('tn-tutor', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Группа',
                                                teacher=cls.tutor)
        cls.students = []
        for index in range(2):
            student = User.objects.create_user('tn-s%d' % index, password='x',
                                               role='student')
            cls.group.students.add(student)
            cls.students.append(student)

        cls.problems = [
            Problem.objects.create(title='Задача %d' % n, statement='Условие',
                                   status=Problem.Status.PUBLISHED,
                                   problem_type='задача', difficulty=3)
            for n in range(4)]

        # Две работы по четыре задачи в каждой: если считать строки
        # `Submission`, числа раздуются вчетверо.
        cls.works = []
        for n in range(2):
            work = Assignment.objects.create(name='Работа %d' % n,
                                             author=cls.tutor, group=cls.group)
            for order, problem in enumerate(cls.problems):
                AssignmentItem.objects.create(assignment=work, order=order,
                                              catalog_problem=problem,
                                              points=Decimal('2'))
            work.students.set(cls.group.students.all())
            cls.works.append(work)

        # Первый ученик сдал обе работы, второй — одну.
        for work, students in ((cls.works[0], cls.students),
                               (cls.works[1], cls.students[:1])):
            for student in students:
                for item in work.items.all():
                    Submission.objects.create(
                        assignment=work, student=student,
                        problem=item.catalog_problem, problem_item=item,
                        status='submitted')


class WaitingIsCountedOnceTests(WaitingUnitBase):

    def test_column_counts_works_not_problem_rows(self):
        """Три сданных работы — это 3, а не 12 строк `Submission`."""
        rows = stats.group_table(self.group, period='all')
        by_name = {row['student'].username: row for row in rows}
        self.assertEqual(by_name['tn-s0']['submitted'], 2)
        self.assertEqual(by_name['tn-s1']['submitted'], 1)
        self.assertEqual(Submission.objects.count(), 12)

    def test_column_and_tab_agree(self):
        """Сумма по колонке «ждёт» = число у вкладки. По построению."""
        rows = stats.group_table(self.group, period='all')
        by_column = sum(row['pending'] for row in rows)
        self.assertEqual(by_column, stats.works_waiting(self.works))
        self.assertEqual(by_column, 3)

    def test_group_screen_shows_one_number(self):
        """Экран занятия: кружок вкладки и колонка не расходятся."""
        client = Client()
        client.force_login(self.tutor)
        page = client.get(reverse('teacher:group_detail',
                                  args=[self.group.pk]) + '?tab=overview')
        self.assertEqual(page.status_code, 200)
        rows = page.context['rows']
        self.assertEqual(sum(row['pending'] for row in rows),
                         page.context['waiting_total'])

    def test_other_groups_do_not_leak_in(self):
        """Колонка считает ПО ЭТОЙ группе, а не по всему сайту."""
        other_tutor = User.objects.create_user('tn-other', password='x',
                                               role='teacher')
        other = StudentGroup.objects.create(name='Чужая', teacher=other_tutor)
        other.students.add(self.students[0])
        work = Assignment.objects.create(name='Чужая работа',
                                         author=other_tutor, group=other)
        item = AssignmentItem.objects.create(assignment=work, order=0,
                                             catalog_problem=self.problems[0],
                                             points=Decimal('1'))
        Submission.objects.create(assignment=work, student=self.students[0],
                                  problem=self.problems[0], problem_item=item,
                                  status='submitted')

        rows = stats.group_table(self.group, period='all')
        by_name = {row['student'].username: row for row in rows}
        self.assertEqual(by_name['tn-s0']['submitted'], 2,
                         'работа чужой группы попала в счёт')

    def test_counts_share_one_definition(self):
        """`works_waiting` — сумма того же счёта, а не второй запрос."""
        counts = stats.student_work_counts(self.works, stats.WAITING_STATUSES)
        self.assertEqual(sum(counts.values()),
                         stats.works_waiting(self.works))


class DenominatorIsTheWholeWorkTests(TestCase):
    """2.2 — знаменатель итогового балла один: полный максимум работы."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('dn-tutor', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('dn-student', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Группа',
                                                teacher=cls.tutor)
        cls.group.students.add(cls.student)
        cls.work = Assignment.objects.create(name='Работа', author=cls.tutor,
                                             group=cls.group)
        cls.items = []
        for order in range(3):
            problem = Problem.objects.create(
                title='Задача %d' % order, statement='Условие',
                status=Problem.Status.PUBLISHED, problem_type='задача')
            item = AssignmentItem.objects.create(
                assignment=cls.work, order=order, catalog_problem=problem,
                points=Decimal('6'))
            cls.items.append(item)
        cls.work.students.add(cls.student)

        # Все три сданы, проверена одна: 2,5 из 18, ещё 12 на проверке.
        for item in cls.items:
            sub = Submission.objects.create(
                assignment=cls.work, student=cls.student,
                problem=item.catalog_problem, problem_item=item,
                status='submitted')
            if item is cls.items[0]:
                TeacherFeedback.objects.create(submission=sub,
                                               score=Decimal('2.5'),
                                               reviewed_by=cls.tutor)

    def test_denominator_is_the_full_maximum(self):
        summary = work_summary(self.work, self.student, viewer=self.tutor)
        self.assertEqual(summary['max_score'], '18')
        self.assertEqual(summary['scored'], '2,5')

    def test_unchecked_points_are_named_separately(self):
        summary = work_summary(self.work, self.student, viewer=self.tutor)
        self.assertEqual(summary['pending_points'], '12')
        self.assertFalse(summary['is_final'])

    def test_screen_shows_full_denominator_and_the_rest(self):
        client = Client()
        client.force_login(self.tutor)
        page = client.get(reverse('teacher:student_work_review',
                                  args=[self.group.pk, self.work.pk,
                                        self.student.pk]))
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn('>18<', body, 'знаменатель не полный максимум')
        self.assertIn('на проверке', body)

    def test_checked_work_says_nothing_extra(self):
        """Всё проверено — скобок нет, только «2,5 из 18»."""
        for item in self.items[1:]:
            sub = Submission.objects.get(problem_item=item)
            TeacherFeedback.objects.create(submission=sub, score=Decimal('6'),
                                           reviewed_by=self.tutor)
        summary = work_summary(self.work, self.student, viewer=self.tutor)
        self.assertTrue(summary['is_final'])
        self.assertEqual(summary['max_score'], '18')
        self.assertEqual(summary['pending_points'], '0')


class BestDayTests(TestCase):
    """2.3 — «Лучший день» считается по журналу и включает игру."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user('bd-student', password='x',
                                               role='student')
        cls.problem = Problem.objects.create(
            title='Задача', statement='Условие',
            status=Problem.Status.PUBLISHED, problem_type='задача')

    def event(self, day, kind='solved', source='homework'):
        moment = timezone.make_aware(
            datetime.datetime(2026, 8, day, 12, 0))
        event = LearningEvent.objects.create(
            user=self.student, event_type=kind, source=source,
            catalog_problem=self.problem)
        LearningEvent.objects.filter(pk=event.pk).update(created_at=moment)

    def test_best_day_counts_solved_by_day(self):
        for _ in range(3):
            self.event(4)
        self.event(5)
        day, solved = best_day_of(self.student)
        self.assertEqual(solved, 3)
        self.assertEqual(str(day), '2026-08-04')

    def test_game_counts_too(self):
        """⚠️ Игра ВХОДИТ — так теперь написано в подсказке на экране."""
        self.event(4)
        self.event(5, source='game')
        self.event(5, source='game')
        _, solved = best_day_of(self.student)
        self.assertEqual(solved, 2)

    def test_wrong_answers_do_not_count(self):
        self.event(4)
        self.event(4, kind='failed')
        _, solved = best_day_of(self.student)
        self.assertEqual(solved, 1)

    def test_no_events_means_no_record(self):
        self.assertIsNone(best_day_of(self.student))

    def test_record_can_go_down(self):
        """⚠️ Раньше рекорд только РОС, и завышенное число жило вечно."""
        PersonalRecord.objects.create(
            user=self.student, kind=PersonalRecord.Kind.MOST_PRODUCTIVE_DAY,
            value=275, payload={'date': '2026-08-04'})
        self.event(6)
        update_records(self.student)
        record = PersonalRecord.objects.get(
            user=self.student, kind=PersonalRecord.Kind.MOST_PRODUCTIVE_DAY)
        self.assertEqual(record.value, 1)
        self.assertEqual(record.payload['date'], '2026-08-06')

    def test_hint_no_longer_denies_the_game(self):
        client = Client()
        client.force_login(self.student)
        body = client.get(reverse('student_stats')).content.decode()
        self.assertNotIn('Игра сюда не входит', body)


class PointWordTests(TestCase):
    """2.4 — склонение идёт через общее место, а не заплаткой в шаблоне."""

    def test_forms(self):
        self.assertEqual(point_word(1), 'балл')
        self.assertEqual(point_word(3), 'балла')
        self.assertEqual(point_word(5), 'баллов')
        self.assertEqual(point_word(11), 'баллов')
        self.assertEqual(point_word(21), 'балл')
        self.assertEqual(point_word(0), 'баллов')

    def test_fraction_is_always_genitive(self):
        self.assertEqual(point_word(Decimal('1.5')), 'балла')
        self.assertEqual(point_word(Decimal('2.5')), 'балла')

    def test_points_text_uses_the_same_rule(self):
        self.assertEqual(points_text(3), '3 балла')
        self.assertEqual(points_text(Decimal('1.5')), '1,5 балла')
        for number in (0, 1, 2, 5, 11, 21, 100):
            self.assertTrue(points_text(number).endswith(point_word(number)))

    def test_assignment_page_declines_the_word(self):
        tutor = User.objects.create_user('pw-tutor', password='x',
                                         role='teacher')
        group = StudentGroup.objects.create(name='Группа', teacher=tutor)
        work = Assignment.objects.create(name='Работа', author=tutor,
                                         group=group)
        problem = Problem.objects.create(title='Задача', statement='Условие',
                                         status=Problem.Status.PUBLISHED,
                                         problem_type='задача')
        AssignmentItem.objects.create(assignment=work, order=0,
                                      catalog_problem=problem,
                                      points=Decimal('3'))
        client = Client()
        client.force_login(tutor)
        body = client.get(reverse('teacher:group_assignment',
                                  args=[group.pk, work.pk])).content.decode()
        self.assertIn('>балла<', body)
        self.assertNotIn('>баллов<', body)
