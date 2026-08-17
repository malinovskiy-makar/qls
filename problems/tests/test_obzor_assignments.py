"""
Обзор кабинета 13.08.2026, фаза 4 — вкладка «Задания».

Пункты владельца 25–27:
  • четыре карточки из пяти в «Проверены» — «никто не сдал», и все зелёные;
  • «Посмотреть все» без числа;
  • чип типа стоял ПОСЛЕ названия и у длинных названий уезжал к краю.
"""
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cards(html):
    return re.findall(r'<div class="k-card ass-card[^"]*"', html)


class AssignmentsTabTests(TestCase):
    def setUp(self):
        from problems.models import (Assignment, AssignmentItem,
                                     Submission, TeacherFeedback)

        self.now = timezone.now()
        self.tutor = make_user('at_tutor', role='teacher')
        self.student = make_user('at_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])

        # Работа со сроком в прошлом, которую НИКТО не открыл.
        self.empty = Assignment.objects.create(
            name='Никем не тронутая', author=self.tutor, group=self.group,
            deadline=self.now - timedelta(days=5))
        self.empty.students.set([self.student])
        AssignmentItem.objects.create(
            assignment=self.empty, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('5'))

        # Работа со сроком в прошлом, сданная и проверенная.
        self.checked = Assignment.objects.create(
            name='Проверенная целиком', author=self.tutor, group=self.group,
            deadline=self.now - timedelta(days=6))
        self.checked.students.set([self.student])
        item = AssignmentItem.objects.create(
            assignment=self.checked, order=0,
            catalog_problem=make_problem('Условие 2'), points=Decimal('4'))
        sub = Submission.objects.create(
            student=self.student, assignment=self.checked, problem_item=item,
            status='reviewed', submitted_at=self.now - timedelta(days=4))
        TeacherFeedback.objects.create(submission=sub, score=Decimal('4'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.tutor)

    def _html(self):
        return self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments').content.decode()

    def _card(self, name):
        html = self._html()
        start = html.index(name)
        head = html.rfind('<div class="k-card ass-card', 0, start)
        return html[head:start + 400]

    # ---- 4.1 полоса --------------------------------------------------
    def test_nobody_submitted_gets_the_grey_stripe(self):
        self.assertIn('k-mark--empty', self._card('Никем не тронутая'))

    def test_nobody_submitted_is_not_green(self):
        self.assertNotIn('k-mark--correct', self._card('Никем не тронутая'))

    def test_checked_work_keeps_the_green_stripe(self):
        self.assertIn('k-mark--correct', self._card('Проверенная целиком'))

    def test_they_are_in_different_groups_now(self):
        """⚠️ ПЕРЕСЧИТАН (ревью 17.08, п. 5.1). Здесь проверялось, что обе
        работы лежат в «Проверены» и различаются только полосой. Владелец
        назвал это дефектом: работу, которой никто не сдал, проверить
        нельзя — слово «проверены» обещало результат. Для неё заведён блок
        «Завершены», полоса у обеих по-прежнему честная.
        """
        html = self._html()
        done = html.split('Проверены')[1].split('Завершены')[0]
        closed = html.split('Завершены')[1]
        self.assertIn('Проверенная целиком', done)
        self.assertNotIn('Никем не тронутая', done)
        self.assertIn('Никем не тронутая', closed)

    # ---- 4.2 «Посмотреть ещё N» --------------------------------------
    def _fill_checked(self, extra):
        """Доводит группу «Проверены» до нужного размера.

        ⚠️ РАБОТЫ ОБЯЗАНЫ БЫТЬ СДАННЫМИ И ПРОВЕРЕННЫМИ (ревью 17.08, п. 5.1).
        Раньше помощник заводил их пустыми, и они всё равно попадали в
        «Проверены» — ровно тот дефект, ради которого завели блок
        «Завершены». Теперь пустая работа туда не попадает, и помощник
        обязан делать то, что написано в его названии.
        """
        from decimal import Decimal

        from problems.models import (
            Assignment, AssignmentItem, Problem, Submission, TeacherFeedback,
        )

        problem = Problem.objects.create(
            title='Задача для истории', statement='Условие',
            status=Problem.Status.PUBLISHED, problem_type='задача')
        for index in range(extra):
            work = Assignment.objects.create(
                name='Старая %d' % index, author=self.tutor, group=self.group,
                deadline=self.now - timedelta(days=10 + index))
            work.students.set([self.student])
            item = AssignmentItem.objects.create(
                assignment=work, order=0, catalog_problem=problem,
                points=Decimal('1'))
            sub = Submission.objects.create(
                assignment=work, student=self.student, problem=problem,
                problem_item=item, status='reviewed')
            TeacherFeedback.objects.create(submission=sub, score=Decimal('1'),
                                           reviewed_by=self.tutor)

    def test_show_all_button_counts_what_is_hidden(self):
        """⚠️ ОЖИДАНИЕ ПЕРЕСЧИТАНО (ревью 15.08, п. 1.3).

        Было «Посмотреть все 6» — число ВСЕХ работ, стоящее под подписью
        «последние 5 из 6». Ни одно из двух чисел не отвечало на вопрос
        «сколько я ещё не вижу». Теперь кнопка называет СКРЫТЫЕ, подпись
        над списком не тронута.
        """
        self._fill_checked(5)
        html = self._html()
        self.assertIn('Посмотреть ещё 1 работу', html)
        self.assertNotIn('Посмотреть все', html)
        self.assertIn('последние 5 из 6', html)

    def test_hidden_count_is_declined(self):
        """Три скрытых — «3 работы», а не «3 работу»."""
        self._fill_checked(7)
        self.assertIn('Посмотреть ещё 3 работы', self._html())

    def test_no_button_when_nothing_is_hidden(self):
        # ⚠️ Ищем САМУ КНОПКУ по её атрибуту: и класс, и надпись встречаются
        # ещё в комментариях стилей и скрипта — они тоже уходят на страницу,
        # и проверка по ним краснела бы всегда.
        self.assertNotIn('data-more=', self._html())

    # ---- 4.3 чип типа ------------------------------------------------
    def test_chip_stands_before_the_name(self):
        card = self._card('Проверенная целиком')
        self.assertLess(card.index('ass-kind'), card.index('ass-link'))

    def test_chip_has_a_fixed_width(self):
        page = open(os.path.join(ROOT, 'teacher', 'templates', 'teacher',
                                 'groups', 'detail.html'),
                    encoding='utf-8').read()
        block = page.split('.ass-kind {')[1].split('}')[0]
        self.assertIn('min-width: 88px', block)
        self.assertIn('text-align: center', block)
        self.assertNotIn('margin-left', block)

    def test_exam_and_homework_use_the_same_chip(self):
        from problems.models import Assignment

        exam = Assignment.objects.create(
            name='Контрольная работа', author=self.tutor, group=self.group,
            kind=Assignment.Kind.EXAM,
            deadline=self.now - timedelta(days=3))
        exam.students.set([self.student])
        card = self._card('Контрольная работа')
        self.assertIn('>контрольная</span>', card)
        self.assertLess(card.index('ass-kind'), card.index('ass-link'))

    def test_deadline_hint_is_ours_not_the_browser_one(self):
        page = open(os.path.join(ROOT, 'teacher', 'templates', 'teacher',
                                 'groups', 'detail.html'),
                    encoding='utf-8').read()
        self.assertNotIn('title="', page)
        self.assertIn('data-hint="{{ row.deadline_exact }}"', page)
