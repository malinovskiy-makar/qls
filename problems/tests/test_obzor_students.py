"""
Обзор кабинета 13.08.2026, фаза 2 — экран «Ученики».

Пункты владельца 9–12:
  • порядок карточек был произвольным — спокойные выше тех, где ждут;
  • две строки подряд про одного Петра читались как два ученика;
  • «и ещё 3» — тупик, нажать нельзя;
  • у карточек без срока пропадала строка, и ряд разъезжался по высоте.
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user


def cards_html(html):
    """Карточки занятий в порядке, в котором они стоят на экране."""
    return re.findall(r'<div class="k-card gc-card.*?(?=<div class="k-card gc-card|\Z)',
                      html, re.S)


def titles(html):
    return re.findall(r'<div class="gc-title">(.*?)</div>', html, re.S)


class ScreenTests(TestCase):
    def setUp(self):
        from problems.models import (Assignment, AssignmentItem,
                                     LearningEvent, Submission)

        self.now = timezone.now()
        self.tutor = make_user('os_tutor', role='teacher')

        # Спокойная группа: ученик активен, работ без срока нет.
        self.calm = StudentGroup.objects.create(name='Апрель — спокойные',
                                                teacher=self.tutor)
        calm_student = make_user('os_calm', role='student',
                                 first_name='Анна', last_name='Тихая')
        self.calm.students.set([calm_student])
        LearningEvent.objects.create(user=calm_student, source='catalog',
                                     event_type='solved')

        # Тревожная группа: Пётр не сдал работу И его сдача ждёт проверки.
        self.hot = StudentGroup.objects.create(name='Ясень — тревожные',
                                               teacher=self.tutor)
        self.peter = make_user('os_peter', role='student',
                               first_name='Пётр', last_name='Иванов')
        self.other = make_user('os_other', role='student',
                               first_name='Илья', last_name='Сидоров')
        self.hot.students.set([self.peter, self.other])
        for student in (self.peter, self.other):
            LearningEvent.objects.create(user=student, source='catalog',
                                         event_type='solved')

        # Просроченная работа, которую не сдал никто из двоих.
        self.missed = Assignment.objects.create(
            name='Домашка рынок труда', author=self.tutor, group=self.hot,
            deadline=self.now - timedelta(days=6))
        self.missed.students.set([self.peter, self.other])

        # Отдельная работа Петра, сданная и не проверенная пятый день.
        self.stale = Assignment.objects.create(
            name='Старая', author=self.tutor, group=self.hot,
            deadline=self.now - timedelta(days=9))
        self.stale.students.set([self.peter])
        item = AssignmentItem.objects.create(
            assignment=self.stale, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('5'))
        Submission.objects.create(student=self.peter, assignment=self.stale,
                                  problem_item=item, status='submitted',
                                  submitted_at=self.now - timedelta(days=5))

        self.client.force_login(self.tutor)

    def _html(self):
        return self.client.get(reverse('teacher:groups')).content.decode()

    # ---- 2.1 порядок --------------------------------------------------
    def test_troubled_lesson_stands_above_the_calm_one(self):
        """«Ясень» ниже «Апреля» по алфавиту, но выше по вниманию."""
        self.assertEqual(titles(self._html()),
                         ['Ясень — тревожные', 'Апрель — спокойные'])

    def test_inside_a_half_the_order_is_by_name(self):
        from problems.models import LearningEvent

        second_calm = StudentGroup.objects.create(name='Берёза',
                                                  teacher=self.tutor)
        quiet = make_user('os_calm2', role='student')
        second_calm.students.set([quiet])
        LearningEvent.objects.create(user=quiet, source='catalog',
                                     event_type='solved')
        shown = titles(self._html())
        self.assertEqual(shown[0], 'Ясень — тревожные')
        self.assertEqual(shown[1:], ['Апрель — спокойные', 'Берёза'])

    def test_waiting_review_alone_lifts_the_card(self):
        """Предупреждений нет, но сдача ждёт — карточка всё равно наверху."""
        from problems.models import Assignment, AssignmentItem, Submission

        fresh = StudentGroup.objects.create(name='Яблоня', teacher=self.tutor)
        student = make_user('os_fresh', role='student')
        fresh.students.set([student])
        from problems.models import LearningEvent
        LearningEvent.objects.create(user=student, source='catalog',
                                     event_type='solved')
        work = Assignment.objects.create(name='Свежая', author=self.tutor,
                                         group=fresh,
                                         deadline=self.now + timedelta(days=3))
        work.students.set([student])
        item = AssignmentItem.objects.create(
            assignment=work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('3'))
        # Сдана только что: до порога «ждёт три дня» ей далеко.
        Submission.objects.create(student=student, assignment=work,
                                  problem_item=item, status='submitted',
                                  submitted_at=self.now)
        shown = titles(self._html())
        self.assertIn('Яблоня', shown[:2])
        self.assertEqual(shown[-1], 'Апрель — спокойные')

    # ---- 2.2 схлопывание ----------------------------------------------
    def test_one_line_per_student(self):
        card = [c for c in cards_html(self._html())
                if 'Ясень' in c][0]
        lines = re.findall(r'<div>(.*?)</div>',
                           re.search(r'<div class="gc-warn">(.*?)</div>\s*</div>',
                                     card, re.S).group(0), re.S)
        peter_lines = [line for line in lines if 'Пётр' in line]
        self.assertEqual(len(peter_lines), 1, lines)

    def test_both_reasons_are_in_that_one_line(self):
        card = [c for c in cards_html(self._html()) if 'Ясень' in c][0]
        line = [l for l in re.findall(r'<div>(.*?)</div>', card, re.S)
                if 'Пётр' in l][0]
        self.assertIn('Домашка рынок труда', line)
        self.assertIn('ждёт вашей проверки', line)
        self.assertEqual(line.count('Пётр'), 1)

    def test_hidden_counter_counts_students_not_reasons(self):
        """У троих по две причины — скрытых не «пять», а «один ученик»."""
        from problems.models import LearningEvent

        for index in range(2):
            extra = make_user('os_extra%d' % index, role='student',
                              first_name='Доп%d' % index, last_name='Ученик')
            self.hot.students.add(extra)
            LearningEvent.objects.create(user=extra, source='catalog',
                                         event_type='solved')
        card = [c for c in cards_html(self._html()) if 'Ясень' in c][0]
        more = re.search(r'<a class="gc-more".*?>(.*?)</a>', card, re.S).group(1)
        self.assertEqual(re.sub(r'\s+', ' ', more).strip(), 'и ещё 1 ученик →')

    # ---- 2.3 «и ещё N» ссылка -----------------------------------------
    def test_more_line_is_a_link_to_the_overview(self):
        from problems.models import LearningEvent

        for index in range(3):
            extra = make_user('os_more%d' % index, role='student',
                              first_name='Ещё%d' % index, last_name='Ученик')
            self.hot.students.add(extra)
            LearningEvent.objects.create(user=extra, source='catalog',
                                         event_type='solved')
        card = [c for c in cards_html(self._html()) if 'Ясень' in c][0]
        self.assertIn('<a class="gc-more" href="%s"'
                      % reverse('teacher:group_detail', args=[self.hot.pk]),
                      card)

    # ---- 2.4 одинаковая высота ----------------------------------------
    def test_card_without_a_deadline_still_has_the_line(self):
        card = [c for c in cards_html(self._html())
                if 'Апрель' in c][0]
        self.assertIn('сроков нет', card)

    def test_card_with_a_deadline_shows_it(self):
        from problems.models import Assignment

        work = Assignment.objects.create(
            name='Будущая', author=self.tutor, group=self.calm,
            deadline=self.now + timedelta(days=4))
        work.students.set(list(self.calm.students.all()))
        card = [c for c in cards_html(self._html()) if 'Апрель' in c][0]
        self.assertIn('срок:', card)
        self.assertNotIn('сроков нет', card)

    def test_every_card_has_exactly_one_deadline_line(self):
        """Одна строка на карточку — из-за этого ряд и разъезжался."""
        for card in cards_html(self._html()):
            self.assertEqual(card.count('class="gc-when'), 1, card[:200])
