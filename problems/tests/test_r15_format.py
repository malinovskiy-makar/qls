"""
Объединённое ревью 15.08, фаза 1 — курсор, лишние надписи, запись балла.

Пункты владельца 1, 4, П.21 и находка про два формата дробного балла.
"""
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import StudentGroup
from problems.scorefmt import ball, ball_dot, pair
from problems.tests.factories import make_problem, make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Где живёт разметка кабинета и ученической части. Проверки «нигде не
# осталось» обходят эти папки целиком, а не список знакомых файлов: новый
# экран, заведённый мимо списка, иначе проехал бы незамеченным.
MARKUP_DIRS = ('templates', 'teacher', 'student', 'problems/templates',
               'catalog/templates')


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


def walk_markup(suffixes=('.html', '.css', '.js')):
    """Все файлы разметки и стилей кабинета — путь и содержимое."""
    for folder in MARKUP_DIRS:
        for base, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            if 'node_modules' in base:
                continue
            for name in files:
                if name.endswith(suffixes):
                    path = os.path.join(base, name)
                    with open(path, encoding='utf-8') as handle:
                        yield os.path.relpath(path, ROOT), handle.read()


# ---------------------------------------------------------------------------
# 1.1 — курсор
# ---------------------------------------------------------------------------
class CursorTests(TestCase):
    """Стрелка со знаком вопроса убрана со всей платформы."""

    def test_no_cursor_help_anywhere(self):
        found = [path for path, text in walk_markup()
                 if re.search(r'cursor:\s*help', text)]
        self.assertEqual(found, [], 'cursor: help остался: %s' % found)

    def test_hint_mark_still_exists(self):
        """Убран КУРСОР, а не подсказка: знак вопроса на месте."""
        kit = read('templates', '_kit.html')
        self.assertIn('.k-hintmark {', kit)
        self.assertIn('templates/_hint.html', kit)


# ---------------------------------------------------------------------------
# 1.4 — одна запись балла
# ---------------------------------------------------------------------------
class BallFormatTests(TestCase):
    """Правила записи: запятая, без незначащих нулей."""

    def test_fraction_uses_comma(self):
        self.assertEqual(ball(Decimal('4.25')), '4,25')

    def test_trailing_zero_is_dropped(self):
        self.assertEqual(ball(Decimal('0.50')), '0,5')
        self.assertEqual(ball(0.5), '0,5')

    def test_whole_number_has_no_tail(self):
        self.assertEqual(ball(Decimal('2.00')), '2')
        self.assertEqual(ball(2), '2')

    def test_big_whole_number_survives(self):
        """⚠️ Прежний помощник экспорта делал из «10» единицу."""
        self.assertEqual(ball(Decimal('10')), '10')
        self.assertEqual(ball(100), '100')

    def test_empty_stays_empty(self):
        self.assertEqual(ball(None), '')
        self.assertEqual(ball(''), '')
        self.assertEqual(ball('ой'), '')

    def test_comma_on_input_is_understood(self):
        self.assertEqual(ball('1,5'), '1,5')

    def test_machine_form_keeps_the_dot(self):
        self.assertEqual(ball_dot(Decimal('1.50')), '1.5')
        self.assertEqual(ball_dot(Decimal('3')), '3')

    def test_pair_writes_both_halves_the_same_way(self):
        self.assertEqual(pair(Decimal('4.25'), Decimal('18.00')),
                         '4,25 из 18')

    def test_no_minus_zero(self):
        self.assertEqual(ball(Decimal('-0.001')), '0')


class OneFormatOnScreenTests(TestCase):
    """Соседние экраны пишут ОДНО И ТО ЖЕ число одинаково."""

    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, Submission,
                                     TeacherFeedback)

        self.now = timezone.now()
        self.tutor = make_user('rf_tutor', role='teacher')
        self.student = make_user('rf_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])
        self.work = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=self.group,
            deadline=self.now + timedelta(days=1))
        self.work.students.set([self.student])
        # Балл 0,5 из 1 — ровно тот случай, где старая запись давала «0,50».
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('1'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='reviewed',
            submitted_at=self.now, submitted_answer='5')
        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('0.5'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.tutor)

    def _get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()

    def test_summary_writes_the_score_with_a_comma(self):
        """Сводка решений печатала «0.5» с ТОЧКОЙ — строку не локализуют."""
        html = self._get(reverse('teacher:group_submissions',
                                 args=[self.group.pk, self.work.pk]))
        self.assertIn('0,5', html)
        self.assertNotIn('>0.5<', html)

    def test_review_writes_the_same_score(self):
        html = self._get(reverse('teacher:student_work_review',
                                 args=[self.group.pk, self.work.pk,
                                       self.student.pk]))
        self.assertIn('0,5', html)
        self.assertNotIn('0,50', html)

    def test_both_screens_agree(self):
        """Одно число, два экрана — одна запись."""
        from teacher.views_groups import student_cards
        from problems.work_review import work_summary

        card = student_cards(self.work, self.group)[0]
        summary = work_summary(self.work, self.student)
        self.assertEqual(card['scored'], summary['scored'])
        self.assertEqual(card['scored'], '0,5')

    def test_work_done_screen_agrees_too(self):
        html = self._get(reverse('teacher:work_done',
                                 args=[self.group.pk, self.work.pk,
                                       self.student.pk]))
        self.assertIn('0,5', html)
        self.assertNotIn('0,50', html)

    def test_points_field_is_not_a_number_input(self):
        """⚠️ `type="number"` стёр бы «2,5» — как уже было с полем оценки.

        Работа берётся ЧИСТАЯ: у сданной баллы заперты и поля нет вовсе.
        """
        from problems.models import Assignment, AssignmentItem

        fresh = Assignment.objects.create(
            name='Черновик', author=self.tutor, group=self.group,
            deadline=self.now + timedelta(days=3))
        fresh.students.set([self.student])
        AssignmentItem.objects.create(
            assignment=fresh, order=0,
            catalog_problem=make_problem('Ещё условие'),
            points=Decimal('2.5'))
        html = self._get(reverse('teacher:group_assignment',
                                 args=[self.group.pk, fresh.pk]))
        field = html.split('class="pts-input"')[0].rsplit('<input', 1)[1]
        self.assertNotIn('type="number"', field)
        self.assertIn('inputmode="decimal"', field)
        self.assertIn('value="2,5"', html)

    def test_export_prints_the_score_the_same_way(self):
        """⚠️ Старый помощник печатал «10 б.» как «1 б.»."""
        from problems.models import AssignmentItem
        from problems.assignment_export import build_tex

        AssignmentItem.objects.filter(pk=self.item.pk).update(
            points=Decimal('10'))
        text = build_tex(self.work, for_teacher=False)[0]
        self.assertIn('10 б.', text)

        AssignmentItem.objects.filter(pk=self.item.pk).update(
            points=Decimal('2.5'))
        text = build_tex(self.work, for_teacher=False)[0]
        self.assertIn('2,5 б.', text)


class NoStaleFloatformatTests(TestCase):
    """Балл больше не форматируется поштучно в шаблонах."""

    # Поля, которые печатают именно БАЛЛ. Проценты, деньги и счётчики
    # задач через `floatformat` печатать по-прежнему можно.
    SCORE_FIELDS = ('score|floatformat', 'points|floatformat',
                    'max_score|floatformat', 'max_points|floatformat',
                    'scored|floatformat')

    def test_no_floatformat_on_score_fields(self):
        bad = []
        for path, text in walk_markup(suffixes=('.html',)):
            for needle in self.SCORE_FIELDS:
                if needle in text:
                    bad.append('%s: %s' % (path, needle))
        self.assertEqual(bad, [], 'балл всё ещё через floatformat: %s' % bad)


# ---------------------------------------------------------------------------
# 1.2 и 1.3 — надписи
# ---------------------------------------------------------------------------
class CaptionTests(TestCase):
    def setUp(self):
        self.tutor = make_user('rc_tutor', role='teacher')
        self.student = make_user('rc_student', role='student',
                                 first_name='Мария', last_name='Ким')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])
        self.client.force_login(self.tutor)

    def test_group_average_caption_is_gone(self):
        html = self.client.get(
            reverse('teacher:group_detail',
                    args=[self.group.pk])).content.decode()
        self.assertNotIn('Проценты — средние по группе', html)
        self.assertIn('чтобы отсортировать', html)

    def test_old_wording_never_reaches_the_screen(self):
        """«Посмотреть все» не попадает НА ЭКРАН.

        ⚠️ Смотрим РЕНДЕР, а не файл: `{% comment %}` до страницы не
        доезжает, и проверка по исходнику краснела бы на объяснении,
        почему надпись изменили. А вот комментарий в `<style>` и в
        `<script>` на страницу уходит — его как раз и надо ловить.
        """
        html = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments').content.decode()
        self.assertNotIn('Посмотреть все', html)
