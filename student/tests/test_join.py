# -*- coding: utf-8 -*-
"""Вступление в занятие по коду приглашения.

⚠️ ГЛАВНОЕ, ЧТО ЗДЕСЬ СТОРОЖИТСЯ, — НЕ УДОБСТВО, А МОЛЧАНИЕ. Ошибка на
неверный код не должна отличаться от ошибки на чужой существующий: иначе
перебором собирается список живых занятий.
"""
from django.core.cache import cache
from django.test import TestCase

from problems.models import StudentGroup, User

PASSWORD = 'join-probe-2026'


def message_texts(response):
    return [str(m) for m in response.context['messages']]


class JoinTests(TestCase):

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='join_tu', password=PASSWORD, role='teacher')
        self.group = StudentGroup.objects.create(name='Экономика 10',
                                                 teacher=self.teacher)
        self.pupil = User.objects.create_user(
            username='join_st', password=PASSWORD, role='student')
        self.client.force_login(self.pupil)

    def _join(self, code):
        return self.client.post('/student/join/', {'code': code}, follow=True)

    def test_join_with_the_exact_code(self):
        self._join(self.group.invite_code)
        self.assertTrue(self.group.students.filter(pk=self.pupil.pk).exists())

    def test_join_without_dash_and_in_lowercase(self):
        """Человек диктует код голосом — вводит как получится."""
        typed = self.group.invite_code.replace('-', '').lower()
        self._join(typed)
        self.assertTrue(self.group.students.filter(pk=self.pupil.pk).exists())

    def test_join_with_spaces(self):
        typed = ' %s ' % self.group.invite_code.replace('-', ' ')
        self._join(typed)
        self.assertTrue(self.group.students.filter(pk=self.pupil.pk).exists())

    def test_wrong_code_says_nothing_about_existing_ones(self):
        response = self._join('ZZZZ-9999')
        self.assertFalse(self.group.students.filter(pk=self.pupil.pk).exists())
        texts = ' '.join(message_texts(response))
        self.assertIn('Такого кода нет', texts)
        # Ни числа занятий, ни намёка на близость кода.
        self.assertNotIn('Экономика', texts)

    def test_joining_twice_is_not_an_error(self):
        self._join(self.group.invite_code)
        response = self._join(self.group.invite_code)
        self.assertIn('уже в этом занятии', ' '.join(message_texts(response)))
        self.assertEqual(self.group.students.filter(pk=self.pupil.pk).count(), 1)

    def test_several_groups_at_once_is_normal(self):
        second = StudentGroup.objects.create(name='Второе', teacher=self.teacher)
        self._join(self.group.invite_code)
        self._join(second.invite_code)
        self.assertEqual(self.pupil.enrolled_groups.count(), 2)

    def test_regenerated_code_stops_working(self):
        old = self.group.invite_code
        self.group.regenerate_invite_code()
        self._join(old)
        self.assertFalse(self.group.students.filter(pk=self.pupil.pk).exists())
        self._join(self.group.invite_code)
        self.assertTrue(self.group.students.filter(pk=self.pupil.pk).exists())

    def test_eleventh_miss_is_throttled(self):
        """Десять промахов — опечатки. Одиннадцатый — уже не опечатка."""
        for index in range(10):
            self._join('ZZZZ-999%d' % (index % 10))
        response = self._join(self.group.invite_code)
        self.assertIn('Слишком много попыток', ' '.join(message_texts(response)))
        # ⚠️ И ВЕРНЫЙ КОД ТОЖЕ НЕ СРАБОТАЛ: иначе задержка не мешала бы
        # перебору, а только замедляла показ ошибки.
        self.assertFalse(self.group.students.filter(pk=self.pupil.pk).exists())

    def test_get_is_not_allowed(self):
        """Вступление меняет состояние — только POST."""
        self.assertEqual(self.client.get('/student/join/').status_code, 405)

    def test_guest_is_sent_to_login(self):
        self.client.logout()
        response = self.client.post('/student/join/',
                                    {'code': self.group.invite_code})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_tutor_cannot_join_as_a_student(self):
        """⚠️ ОТРИЦАТЕЛЬНЫЙ: у репетитора свой контур, ученики в нём другие."""
        self.client.force_login(self.teacher)
        response = self.client.post('/student/join/',
                                    {'code': self.group.invite_code})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.group.students.count(), 0)


class DashboardTests(TestCase):
    """Экран «Занятия»: карточки групп и форма кода."""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='dash_tu', password=PASSWORD, role='teacher',
            first_name='Иван', last_name='Петров')
        self.pupil = User.objects.create_user(
            username='dash_st', password=PASSWORD, role='student')
        self.client.force_login(self.pupil)

    def test_empty_state_says_what_to_do(self):
        html = self.client.get('/student/').content.decode('utf-8')
        self.assertIn('Пока вы ни в одной группе', html)
        self.assertIn('name="code"', html)

    def test_card_shows_group_and_tutor(self):
        group = StudentGroup.objects.create(name='Экономика 11',
                                            teacher=self.teacher)
        group.students.add(self.pupil)
        html = self.client.get('/student/').content.decode('utf-8')
        self.assertIn('Экономика 11', html)
        self.assertIn('Иван Петров', html)

    def test_invite_code_is_not_shown_to_the_student(self):
        """⚠️ КОД ВИДЕН ТОЛЬКО РЕПЕТИТОРУ.

        Ученику он не нужен: вступать он уже вступил, а показывать код
        значило бы раздавать его дальше без ведома репетитора.
        """
        group = StudentGroup.objects.create(name='Экономика 11',
                                            teacher=self.teacher)
        group.students.add(self.pupil)
        html = self.client.get('/student/').content.decode('utf-8')
        self.assertNotIn(group.invite_code, html)

    def test_screen_is_called_lessons(self):
        html = self.client.get('/student/').content.decode('utf-8')
        self.assertIn('<h1 class="page-title">Занятия</h1>', html)
        self.assertIn('Мои работы', html)
