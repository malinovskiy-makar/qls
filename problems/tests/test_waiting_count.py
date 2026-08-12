"""
Фаза 4 сессии 9 — единый счёт работ, ждущих проверки.

Три места считали три разные вещи, и на одном экране стояли три числа про
одно и то же: карточка группы — «6 ждёт проверки» (задачи), вкладка
«Задания» — «3 ждут проверки» (задания), кнопки внутри — «Проверить 1»,
«Проверить 1», «Проверить 4» (снова задачи).

Единица счёта теперь одна — ПАРА (УЧЕНИК, РАБОТА). Главный тест здесь —
СХОДИМОСТЬ: сумма по карточкам работ равна числу над списком и числу на
карточке группы.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from problems import stats
from problems.tests.factories import make_problem, make_user


class WaitingCountTests(TestCase):
    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission)

        self.tutor = make_user('wc_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.students = [make_user('wc_s%d' % i, role='student')
                         for i in range(3)]
        for student in self.students:
            self.group.students.add(student)

        # Две работы. В первой два ученика сдали по ДВЕ задачи каждый,
        # во второй один ученик сдал ТРИ. Итого работ, ждущих проверки: 3.
        # Задач при этом семь — на них и расходились прежние счётчики.
        self.works = []
        for index, (count, who) in enumerate(((2, self.students[:2]),
                                              (3, self.students[2:3]))):
            work = Assignment.objects.create(name='Р%d' % index,
                                             author=self.tutor,
                                             group=self.group)
            for student in self.students:
                work.students.add(student)
            items = [AssignmentItem.objects.create(
                assignment=work, order=n,
                catalog_problem=make_problem('Условие %d-%d' % (index, n)),
                points=Decimal('10')) for n in range(count)]
            for student in who:
                for item in items:
                    Submission.objects.create(student=student,
                                              assignment=work,
                                              problem_item=item,
                                              status='submitted')
            self.works.append(work)

    def test_unit_is_student_plus_work(self):
        """Две задачи одного ученика в одной работе — это ОДНА работа."""
        self.assertEqual(stats.works_waiting([self.works[0]]), 2)
        self.assertEqual(stats.works_waiting([self.works[1]]), 1)

    def test_group_total(self):
        self.assertEqual(stats.works_waiting(self.works), 3)

    def test_sum_over_works_equals_group_total(self):
        """⚠️ СХОДИМОСТЬ. Ради неё вся фаза и делалась."""
        by_work = sum(stats.works_waiting([work]) for work in self.works)
        self.assertEqual(by_work, stats.works_waiting(self.works))

    def test_reviewed_work_is_not_waiting(self):
        from problems.models import Submission

        Submission.objects.filter(assignment=self.works[1]).update(
            status='reviewed')
        self.assertEqual(stats.works_waiting(self.works), 2)

    def test_empty_list_is_zero(self):
        self.assertEqual(stats.works_waiting([]), 0)


class WaitingOnScreensTests(TestCase):
    """Одно и то же число во всех четырёх местах интерфейса."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission)

        self.tutor = make_user('ws_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.students = [make_user('ws_s%d' % i, role='student')
                         for i in range(2)]
        for student in self.students:
            self.group.students.add(student)
        self.work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                              group=self.group)
        for student in self.students:
            self.work.students.add(student)
        items = [AssignmentItem.objects.create(
            assignment=self.work, order=n,
            catalog_problem=make_problem('Условие %d' % n),
            points=Decimal('10')) for n in range(3)]
        for student in self.students:
            for item in items:
                Submission.objects.create(student=student,
                                          assignment=self.work,
                                          problem_item=item,
                                          status='submitted')
        self.client.force_login(self.tutor)

    def test_tab_counter_and_buttons_agree(self):
        url = reverse('teacher:group_detail', args=[self.group.pk])
        resp = self.client.get(url + '?tab=assignments')
        self.assertEqual(resp.status_code, 200)
        total = resp.context['waiting_total']
        self.assertEqual(total, 2)
        by_card = sum(row['pending'] for row in resp.context['assignment_rows'])
        self.assertEqual(by_card, total)

    def test_group_card_agrees(self):
        resp = self.client.get(reverse('teacher:groups'))
        card = next(c for c in resp.context['cards']
                    if c['group'].pk == self.group.pk)
        self.assertEqual(card['pending'], 2)

    def test_badge_is_drawn_when_there_is_work(self):
        # ⚠️ Ищем именно РАЗМЕТКУ: правило `.k-count` лежит в наборе деталей,
        # который вклеен в <style> страницы, и по подстроке «k-count»
        # находился бы всегда.
        url = reverse('teacher:group_detail', args=[self.group.pk])
        html = self.client.get(url + '?tab=assignments').content.decode()
        self.assertIn('<span class="k-count">2</span>', html)

    def test_badge_disappears_at_zero(self):
        """Пустой кружок — не «ноль дел», а мусор на экране."""
        from problems.models import Submission

        Submission.objects.filter(assignment=self.work).update(
            status='reviewed')
        url = reverse('teacher:group_detail', args=[self.group.pk])
        html = self.client.get(url + '?tab=assignments').content.decode()
        self.assertNotIn('<span class="k-count">', html)

    def test_numeral_is_declined(self):
        """«Проверить 2 работы», а не «Проверить 2»."""
        url = reverse('teacher:group_detail', args=[self.group.pk])
        html = self.client.get(url + '?tab=assignments').content.decode()
        self.assertIn('Проверить 2 работы', html)

    def test_one_work_is_singular(self):
        from problems.models import Submission

        Submission.objects.filter(assignment=self.work,
                                  student=self.students[1]).update(
            status='reviewed')
        url = reverse('teacher:group_detail', args=[self.group.pk])
        html = self.client.get(url + '?tab=assignments').content.decode()
        self.assertIn('Проверить 1 работу', html)
        self.assertIn('работа ждёт проверки', html)
