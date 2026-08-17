"""
Фаза 8 сессии 9 — экран «Ученики» и карточки занятий.

Владелец: список остаётся всегда, даже при одном занятии; карточки должны
нести смысл, а строка «Активность» бесполезна.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user


class CardsTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from problems.models import Assignment, AssignmentItem, Submission

        self.tutor = make_user('ss_tutor', role='teacher')
        self.students = [make_user('ss_s%d' % i, role='student',
                                   first_name='Имя%d' % i,
                                   last_name='Фам%d' % i)
                         for i in range(3)]
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set(self.students)

        now = timezone.now()
        self.work = Assignment.objects.create(
            name='ДЗ', author=self.tutor, group=self.group,
            deadline=now + timedelta(days=2))
        self.work.students.set(self.students)
        item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('10'))
        Submission.objects.create(student=self.students[0],
                                  assignment=self.work, problem_item=item,
                                  status='submitted', submitted_at=now)

        self.solo_student = make_user('ss_solo', role='student',
                                      first_name='Мария', last_name='Ким')
        self.solo_student.profile.grade = 11
        self.solo_student.profile.save()
        # ⚠️ «Не заходил» считается по УЧЕБНЫМ СОБЫТИЯМ (`_last_activity`),
        # а не по `last_login`: заход на сайт без единой решённой задачи —
        # не занятие. Нам нужен случай без предупреждений, поэтому событие.
        from problems.models import LearningEvent
        LearningEvent.objects.create(user=self.solo_student, source='catalog',
                                     event_type='solved')
        self.lesson = StudentGroup.objects.create(
            name='Мария Ким', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.solo_student])

        self.client.force_login(self.tutor)

    def _cards(self):
        resp = self.client.get(reverse('teacher:groups'))
        self.assertEqual(resp.status_code, 200)
        return {c['group'].pk: c for c in resp.context['cards']}, resp

    def test_both_kinds_are_in_one_list(self):
        cards, _ = self._cards()
        self.assertIn(self.group.pk, cards)
        self.assertIn(self.lesson.pk, cards)

    def test_list_stays_with_a_single_lesson(self):
        """Решение владельца: список не прячется при одном занятии."""
        self.group.delete()
        cards, resp = self._cards()
        self.assertEqual(len(cards), 1)
        self.assertIn('gc-card', resp.content.decode())

    def test_numerals_are_declined(self):
        _, resp = self._cards()
        html = resp.content.decode()
        self.assertIn('3 ученика', html)
        self.assertIn('1 задание', html)
        # Прежняя поломка: `pluralize` с тремя формами давал пустоту.
        self.assertNotIn('3 ученик<', html)
        self.assertNotIn('11 задани<', html)

    def test_individual_card_shows_grade_not_student_count(self):
        _, resp = self._cards()
        html = resp.content.decode()
        self.assertIn('11 класс', html)

    def test_kind_chip_on_every_card(self):
        _, resp = self._cards()
        html = resp.content.decode()
        self.assertIn('группа</span>', html)
        self.assertIn('индивидуально</span>', html)

    def test_activity_line_is_gone(self):
        """Дата последней сдачи не отвечает на вопрос «что делать»."""
        _, resp = self._cards()
        self.assertNotIn('Активность:', resp.content.decode())

    def test_warnings_replace_it(self):
        from datetime import timedelta

        from problems.models import Assignment

        # Работа с прошедшим сроком, которую никто не сдал.
        Assignment.objects.create(
            name='Просроченная', author=self.tutor, group=self.group,
            deadline=timezone.now() - timedelta(days=3)
        ).students.set(self.students)
        cards, _ = self._cards()
        self.assertTrue(cards[self.group.pk]['warnings'])

    def test_no_more_than_three_warnings(self):
        from datetime import timedelta

        from problems.models import Assignment

        Assignment.objects.create(
            name='Просроченная', author=self.tutor, group=self.group,
            deadline=timezone.now() - timedelta(days=3)
        ).students.set(self.students)
        cards, _ = self._cards()
        card = cards[self.group.pk]
        self.assertLessEqual(len(card['warnings']), 3)

    def test_calm_line_when_nothing_is_wrong(self):
        """⚠️ ПЕРЕСЧИТАНО 17.08 (п. 2.2): об одном говорят ОДИН раз.

        В теле спокойной карточки стояло «Всё вовремя, ничего не ждёт
        проверки», а строкой ниже — «Работ на проверке нет». Оставлена
        нижняя: она в одном ряду со сроком и держит сетку карточки.
        """
        cards, resp = self._cards()
        page = resp.content.decode()
        self.assertEqual(cards[self.lesson.pk]['warnings'], [])
        self.assertIn('Работ на проверке нет', page)
        self.assertNotIn('Всё вовремя', page)

    def test_waiting_counter_matches_the_group_screen(self):
        """Число то же, что внутри занятия, — счёт один (фаза 4)."""
        from problems import stats
        from problems.models import Assignment

        cards, _ = self._cards()
        expected = stats.works_waiting(
            list(Assignment.objects.filter(group=self.group)))
        self.assertEqual(cards[self.group.pk]['pending'], expected)

    def test_deadline_is_on_the_card(self):
        cards, _ = self._cards()
        self.assertIsNotNone(cards[self.group.pk]['next_deadline'])

    def test_individual_card_has_no_student_count(self):
        """«1 ученик» у занятия один на один — строка ни о чём."""
        cards, resp = self._cards()
        html = resp.content.decode()
        self.assertNotIn('1 ученик ·', html)

    def test_both_create_buttons(self):
        _, resp = self._cards()
        html = resp.content.decode()
        self.assertIn('+ Группа', html)
        self.assertIn('+ Ученик', html)
        self.assertIn('?kind=individual', html)


class WarningsWordingTests(TestCase):
    """У индивидуального имя не повторяется: оно и есть заголовок карточки."""

    def setUp(self):
        from datetime import timedelta

        from problems.models import Assignment

        self.tutor = make_user('sw_tutor', role='teacher')
        self.student = make_user('sw_student', role='student',
                                 first_name='Тимур', last_name='Ахметов')
        self.lesson = StudentGroup.objects.create(
            name='Тимур Ахметов', teacher=self.tutor,
            kind=StudentGroup.Kind.INDIVIDUAL)
        self.lesson.students.set([self.student])
        Assignment.objects.create(
            name='Просроченная', author=self.tutor, group=self.lesson,
            deadline=timezone.now() - timedelta(days=3)
        ).students.set([self.student])
        self.client.force_login(self.tutor)

    def test_no_name_prefix_for_individual(self):
        resp = self.client.get(reverse('teacher:groups'))
        card = next(c for c in resp.context['cards']
                    if c['group'].pk == self.lesson.pk)
        self.assertTrue(card['warnings'])
        # ⚠️ Строка предупреждения стала СЛОВАРЁМ (ревью 17.08, п. 5.1): к
        # тексту добавилась ступень срочности, от которой зависит цвет
        # чёрточки слева. Проверяем по-прежнему текст.
        for warning in card['warnings']:
            self.assertNotIn('Тимур Ахметов —', warning['text'])

    def test_group_keeps_the_name(self):
        from datetime import timedelta

        from problems.models import Assignment

        group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        group.students.add(self.student)
        Assignment.objects.create(
            name='Просроченная 2', author=self.tutor, group=group,
            deadline=timezone.now() - timedelta(days=3)
        ).students.set([self.student])
        resp = self.client.get(reverse('teacher:groups'))
        card = next(c for c in resp.context['cards']
                    if c['group'].pk == group.pk)
        self.assertTrue(any('Тимур Ахметов —' in w['text']
                            for w in card['warnings']))
