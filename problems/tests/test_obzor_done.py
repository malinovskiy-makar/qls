"""
Обзор кабинета 13.08.2026, фаза 8 — экран итогов проверки.

Пункты владельца 54, 55:
  • экран назывался «Работа проверена» и подписывался «пройдена целиком»,
    а внутри стояли задачи со статусом «НА ПРОВЕРКЕ»;
  • крупный балл не учитывал непроверенные задачи и молчал об этом,
    хотя на соседнем экране — глазами ученика — предупреждение было.
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


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class DoneScreenTests(TestCase):
    def setUp(self):
        from problems.models import (Assignment, AssignmentItem,
                                     Submission, TeacherFeedback)

        self.now = timezone.now()
        self.tutor = make_user('od_tutor', role='teacher')
        self.student = make_user('od_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])
        self.work = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=self.group,
            deadline=self.now + timedelta(days=1))
        self.work.students.set([self.student])

        self.items = [AssignmentItem.objects.create(
            assignment=self.work, order=index,
            catalog_problem=make_problem('Условие %d' % index),
            points=Decimal('5')) for index in range(3)]
        self.subs = [Submission.objects.create(
            student=self.student, assignment=self.work, problem_item=item,
            status='submitted', submitted_at=self.now,
            submitted_answer='5') for item in self.items]
        # Первая проверена, две остальные ждут.
        TeacherFeedback.objects.create(submission=self.subs[0],
                                       score=Decimal('3'),
                                       reviewed_by=self.tutor)
        self.subs[0].status = 'reviewed'
        self.subs[0].save()
        self.client.force_login(self.tutor)

    def _html(self):
        return self.client.get(
            reverse('teacher:work_done',
                    args=[self.group.pk, self.work.pk,
                          self.student.pk])).content.decode()

    def _text(self):
        """Страница без разметки и лишних пробелов.

        ⚠️ Фразы в шаблоне разбиты переносами строк, и поиск точной строки
        по сырому HTML краснел бы на форматировании, а не на смысле.
        """
        import re as _re
        return _re.sub(r'\s+', ' ', _re.sub('<[^>]+>', ' ', self._html()))

    def _header(self):
        return self._html().split('<div class="page-header">')[1][:900]

    def _check_all(self):
        from problems.models import TeacherFeedback

        for sub in self.subs[1:]:
            TeacherFeedback.objects.create(submission=sub, score=Decimal('5'),
                                           reviewed_by=self.tutor)
            sub.status = 'reviewed'
            sub.save()

    # ---- 8.1 заголовок ------------------------------------------------
    def test_partial_state_is_named_so(self):
        html = self._html()
        self.assertIn('проверена частично', html)
        self.assertNotIn('пройдена целиком', html)

    def test_partial_state_says_how_many_are_left(self):
        self.assertIn('Осталось проверить', self._html())
        self.assertIn('2 задачи', self._html())

    def test_the_number_is_a_link_to_the_first_unchecked(self):
        html = self._html()
        expected = reverse('teacher:group_review_submission',
                           args=[self.group.pk, self.subs[1].pk])
        self.assertIn('<a href="%s">2 задачи</a>' % expected, html)

    def test_page_title_matches_the_state(self):
        self.assertIn('<title>Проверено частично', self._html())

    def test_flag_says_partially_checked(self):
        html = self._html()
        self.assertIn('k-flag--pending', self._header())

    def test_fully_checked_work_keeps_the_old_wording(self):
        self._check_all()
        html = self._html()
        self.assertIn('пройдена целиком', html)
        self.assertNotIn('проверена частично', html)
        self.assertIn('<title>Работа проверена', html)

    def test_fully_checked_flag_is_green(self):
        self._check_all()
        self.assertIn('k-flag--correct', self._header())

    def test_crumb_follows_the_state(self):
        # ⚠️ Крошка стала `<nav>` (ревью 15.08, фаза 2) — ищем по новому тегу.
        crumb = re.search(r'<nav class="crumbs"[^>]*>(.*?)</nav>',
                          self._html(), re.S).group(1)
        self.assertIn('итог', crumb)
        self._check_all()
        crumb = re.search(r'<nav class="crumbs"[^>]*>(.*?)</nav>',
                          self._html(), re.S).group(1)
        self.assertIn('готово', crumb)

    # ---- 8.2 плашка ---------------------------------------------------
    def test_the_plate_is_shown(self):
        html = self._html()
        self.assertIn('предварительный результат', html)
        self.assertIn('k-prelim', html)

    def test_plate_counts_the_same_tasks(self):
        self.assertIn('2 задачи ещё не проверены', self._text())

    def test_no_plate_when_everything_is_checked(self):
        self._check_all()
        self.assertNotIn('предварительный результат', self._html())

    def test_the_plate_is_one_partial_for_both_screens(self):
        """Вторую такую же не писали — иначе разъедутся формулировкой."""
        done = read('teacher', 'templates', 'teacher', 'groups',
                    'work_done.html')
        eyes = read('student', 'templates', 'student', 'work_review.html')
        self.assertIn("_prelim.html", done)
        self.assertIn("_prelim.html", eyes)
        self.assertNotIn('предварительный результат', done)
        self.assertNotIn('предварительный результат', eyes)

    def test_the_student_screen_still_shows_it(self):
        html = self.client.get(
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.work.pk,
                          self.student.pk])).content.decode()
        self.assertIn('предварительный результат', html)
        self.assertIn('2 задачи ещё не проверены',
                      re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', html)))

    def test_plate_wording_is_impersonal(self):
        """«Проверяет преподаватель» на экране преподавателя — про кого?

        ⚠️ Смотрим ВЫВОД, а не файл: в комментарии шаблона это слово стоит
        законно — там объясняется, почему его убрали из текста.
        """
        from django.template.loader import render_to_string

        shown = render_to_string('_prelim.html', {'pending': 2})
        self.assertNotIn('преподаватель', shown)
        self.assertIn('ещё не', re.sub(r'\s+', ' ', shown))

    def test_plate_style_lives_in_the_kit(self):
        kit = read('templates', '_kit.html')
        self.assertIn('.k-prelim {', kit)
        eyes = read('student', 'templates', 'student', 'work_review.html')
        self.assertNotIn('.wr-warn', eyes)

    def test_one_task_left_is_declined(self):
        from problems.models import TeacherFeedback

        TeacherFeedback.objects.create(submission=self.subs[1],
                                       score=Decimal('5'),
                                       reviewed_by=self.tutor)
        self.subs[1].status = 'reviewed'
        self.subs[1].save()
        self.assertIn('1 задача ещё не проверена', self._text())
