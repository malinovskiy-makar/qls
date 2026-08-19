"""
Обзор кабинета 13.08.2026, фаза 6 — занятие один на один.

Пункты владельца 36–39:
  • «сдали 1 из 1» — групповая формулировка;
  • «80% средняя оценка»: средняя по одному ученику это просто оценка;
  • «доступные группе» у занятия, где группы нет;
  • пустой блок «Требуют внимания» не должен занимать место.
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user


def meta(html):
    return [re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', m)).strip()
            for m in re.findall(r'<div class="ass-meta">(.*?)</div>', html, re.S)]


def figures(html):
    return [re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', m)).strip()
            for m in re.findall(r'<div class="ass-figures">(.*?)</div>\s*</div>',
                                html, re.S)]


class SoloWordingTests(TestCase):
    def setUp(self):
        from problems.models import (Assignment, AssignmentItem,
                                     LearningEvent, Submission,
                                     TeacherFeedback)

        self.now = timezone.now()
        self.tutor = make_user('sw_tutor', role='teacher')
        self.student = make_user('sw_student', role='student',
                                 first_name='Мария', last_name='Ким')
        LearningEvent.objects.create(user=self.student, source='catalog',
                                     event_type='solved')
        self.lesson = StudentGroup.objects.create(
            name='Мария Ким', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.student])

        self.work = Assignment.objects.create(
            name='Занятие 1', author=self.tutor, group=self.lesson,
            deadline=self.now - timedelta(days=3))
        self.work.students.set([self.student])
        item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('10'))
        self.submitted_at = self.now - timedelta(days=4)
        sub = Submission.objects.create(
            student=self.student, assignment=self.work, problem_item=item,
            status='reviewed', submitted_at=self.submitted_at)
        TeacherFeedback.objects.create(submission=sub, score=Decimal('8'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.tutor)

    def _tab(self, name):
        return self.client.get(
            reverse('teacher:group_detail', args=[self.lesson.pk])
            + '?tab=' + name).content.decode()

    # ---- 6.1 ----------------------------------------------------------
    def test_submitted_date_instead_of_a_ratio(self):
        # ⚠️ Дату сверяем в ПОЯСЕ ПРОЕКТА, а не в UTC. Шаблон печатает момент
        # через `date`, который переводит его в местное время сам, а
        # `strftime` у aware-даты печатает UTC. Между 21:00 и полуночью по
        # местному это РАЗНЫЕ календарные дни, и тест падал только вечером.
        local = timezone.localtime(self.submitted_at)
        line = meta(self._tab('assignments'))[0]
        self.assertIn('сдана %s' % local.strftime('%d.%m'), line)
        self.assertNotIn('из 1', line)

    def test_not_submitted_says_so(self):
        from problems.models import Assignment, Submission

        Submission.objects.filter(assignment=self.work).delete()
        line = meta(self._tab('assignments'))[0]
        self.assertIn('не сдана', line)
        self.assertNotIn('сдали', line)

    def test_group_keeps_the_ratio(self):
        """У группы «сдали N из M» — это доля, и она осмысленна."""
        from problems.models import Assignment

        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        group.students.set([self.student, make_user('sw_2', role='student')])
        work = Assignment.objects.create(
            name='Групповая', author=self.tutor, group=group,
            deadline=self.now + timedelta(days=1))
        work.students.set(list(group.students.all()))
        html = self.client.get(
            reverse('teacher:group_detail', args=[group.pk])
            + '?tab=assignments').content.decode()
        self.assertIn('сдали 0 из 2', meta(html)[0])

    # ---- 6.2 ----------------------------------------------------------
    def test_no_word_average_for_one_student(self):
        line = figures(self._tab('assignments'))[0]
        self.assertIn('оценка', line)
        self.assertNotIn('средняя', line)

    def test_nobody_submitted_is_impersonal_and_singular(self):
        from problems.models import Submission

        Submission.objects.filter(assignment=self.work).delete()
        line = figures(self._tab('assignments'))[0]
        self.assertIn('работа не сдана', line)
        self.assertNotIn('никто не сдал', line)

    def test_group_keeps_the_word_average(self):
        from problems.models import (Assignment, AssignmentItem,
                                     Submission, TeacherFeedback)

        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        other = make_user('sw_3', role='student')
        group.students.set([self.student, other])
        work = Assignment.objects.create(
            name='Групповая', author=self.tutor, group=group,
            deadline=self.now - timedelta(days=2))
        work.students.set([self.student, other])
        item = AssignmentItem.objects.create(
            assignment=work, order=0,
            catalog_problem=make_problem('У'), points=Decimal('10'))
        sub = Submission.objects.create(
            student=self.student, assignment=work, problem_item=item,
            status='reviewed', submitted_at=self.now)
        TeacherFeedback.objects.create(submission=sub, score=Decimal('7'),
                                       reviewed_by=self.tutor)
        html = self.client.get(
            reverse('teacher:group_detail', args=[group.pk])
            + '?tab=assignments').content.decode()
        self.assertIn('средняя оценка', figures(html)[0])

    # ---- 6.3 ----------------------------------------------------------
    def test_materials_talk_about_the_student(self):
        html = self._tab('materials')
        self.assertIn('доступные', html)
        tail = html.split('Сюда лягут')[1][:120]
        self.assertIn('ученику', tail)
        self.assertNotIn('группе', tail)

    def test_group_materials_still_talk_about_the_group(self):
        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        group.students.set([self.student, make_user('sw_4', role='student')])
        html = self.client.get(
            reverse('teacher:group_detail', args=[group.pk])
            + '?tab=materials').content.decode()
        self.assertIn('группе', html.split('Сюда лягут')[1][:120])

    def test_empty_assignments_state_is_about_the_student(self):
        from problems.models import Assignment

        Assignment.objects.filter(group=self.lesson).delete()
        html = self._tab('assignments')
        self.assertIn('У этого ученика пока нет заданий', html)

    # ---- 6.4 ----------------------------------------------------------
    def test_empty_attention_block_is_not_rendered_at_all(self):
        """Ученик активен и всё сдал — блока нет вовсе, места не занимает."""
        html = self._tab('overview')
        self.assertNotIn('Требуют внимания', html)

    def test_attention_block_appears_when_there_is_a_reason(self):
        from problems.models import LearningEvent, Submission

        Submission.objects.filter(assignment=self.work).delete()
        LearningEvent.objects.filter(user=self.student).delete()
        html = self._tab('overview')
        self.assertIn('Требуют внимания', html)

    def test_solo_attention_row_has_no_name(self):
        """Имя уже стоит в шапке — повторять его в каждой строке незачем."""
        from problems.models import LearningEvent, Submission

        Submission.objects.filter(assignment=self.work).delete()
        LearningEvent.objects.filter(user=self.student).delete()
        html = self._tab('overview')
        row = re.search(r'<div class="attention-row">(.*?)</div>',
                        html, re.S).group(1)
        self.assertNotIn('Мария Ким', row)
