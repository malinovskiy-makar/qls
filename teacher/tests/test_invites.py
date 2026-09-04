# -*- coding: utf-8 -*-
"""Код приглашения: выдача, смена, состав занятия и границы доступа.

⚠️ ГРАНИЦЫ ПРОВЕРЯЮТСЯ ОТРИЦАТЕЛЬНЫМИ ТЕСТАМИ. «Свой репетитор прошёл» без
парного «чужой не прошёл» границей не считается: именно чужой репетитор —
тот, от кого закрывается занятие.
"""
import re

from django.core.cache import cache
from django.test import TestCase

from problems.models import INVITE_ALPHABET, StudentGroup, User

PASSWORD = 'invite-probe-2026'
CODE_RE = re.compile(r'^[%s]{4}-[%s]{4}$' % (INVITE_ALPHABET, INVITE_ALPHABET))


def tutor(name):
    return User.objects.create_user(username=name, password=PASSWORD,
                                    role='teacher')


def student(name):
    return User.objects.create_user(username=name, password=PASSWORD,
                                    role='student')


class InviteCodeTests(TestCase):
    """Код выдаётся сам, по маске и без повторов."""

    def setUp(self):
        self.teacher = tutor('inv_tu')

    def test_code_is_issued_on_create(self):
        group = StudentGroup.objects.create(name='Группа', teacher=self.teacher)
        self.assertTrue(group.invite_code)
        self.assertRegex(group.invite_code, CODE_RE)

    def test_two_hundred_groups_get_two_hundred_codes(self):
        """Уникальность — не декларация, а проверка на объёме."""
        codes = set()
        for index in range(200):
            group = StudentGroup.objects.create(name='Г%d' % index,
                                                teacher=self.teacher)
            self.assertRegex(group.invite_code, CODE_RE, group.invite_code)
            codes.add(group.invite_code)
        self.assertEqual(len(codes), 200)

    def test_alphabet_has_no_confusable_pairs(self):
        """Ни 0/O, ни 1/I: код диктуют голосом и переписывают с доски."""
        self.assertEqual(len(INVITE_ALPHABET), 32)
        for char in '01IO':
            self.assertNotIn(char, INVITE_ALPHABET)

    def test_code_does_not_change_on_every_save(self):
        group = StudentGroup.objects.create(name='Г', teacher=self.teacher)
        first = group.invite_code
        group.name = 'Другое имя'
        group.save()
        group.refresh_from_db()
        self.assertEqual(group.invite_code, first)

    def test_regenerate_gives_a_new_one(self):
        group = StudentGroup.objects.create(name='Г', teacher=self.teacher)
        first = group.invite_code
        second = group.regenerate_invite_code()
        self.assertNotEqual(first, second)
        self.assertRegex(second, CODE_RE)

    def test_normalize_accepts_what_a_human_types(self):
        """Строчными, без дефиса, с пробелами — это тот же код."""
        code = 'ABCD-2345'
        for typed in ('ABCD-2345', 'abcd-2345', 'ABCD2345', ' abcd 2345 ',
                      'a b c d 2 3 4 5'):
            self.assertEqual(StudentGroup.normalize_invite_code(typed), code,
                             typed)

    def test_normalize_refuses_garbage(self):
        for typed in ('', None, 'ABC', 'ABCD-234', 'ABCD-23456', 'ОШИБКА!!'):
            self.assertEqual(StudentGroup.normalize_invite_code(typed), '',
                             repr(typed))


class TeacherScreenTests(TestCase):
    """Что видит и что может репетитор."""

    def setUp(self):
        cache.clear()
        self.teacher = tutor('inv_own')
        self.stranger = tutor('inv_alien')
        self.group = StudentGroup.objects.create(name='Моя группа',
                                                 teacher=self.teacher)
        self.pupil = student('inv_pupil')
        self.group.students.add(self.pupil)

    def test_code_is_on_the_list_screen(self):
        self.client.force_login(self.teacher)
        html = self.client.get('/teacher/groups/').content.decode('utf-8')
        self.assertIn(self.group.invite_code, html)

    def test_code_and_roster_are_on_the_group_screen(self):
        self.client.force_login(self.teacher)
        html = self.client.get(
            '/teacher/groups/%d/' % self.group.pk).content.decode('utf-8')
        self.assertIn(self.group.invite_code, html)
        self.assertIn('inv_pupil', html)
        self.assertIn('Приглашение', html)
        self.assertIn('Состав', html)

    def test_regenerate_invalidates_the_old_code(self):
        self.client.force_login(self.teacher)
        old = self.group.invite_code
        response = self.client.post(
            '/teacher/groups/%d/invite/regenerate/' % self.group.pk)
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.invite_code, old)
        # Старый код больше не находит занятие.
        self.assertFalse(StudentGroup.objects.filter(invite_code=old).exists())

    def test_remove_student_keeps_their_work(self):
        """Отчисление убирает из состава, но не из истории работ."""
        from problems.models import Assignment
        work = Assignment.objects.create(name='Домашка', author=self.teacher,
                                         group=self.group)
        work.students.add(self.pupil)

        self.client.force_login(self.teacher)
        self.client.post('/teacher/groups/%d/students/%d/remove/'
                         % (self.group.pk, self.pupil.pk))

        self.assertFalse(self.group.students.filter(pk=self.pupil.pk).exists())
        self.assertTrue(work.students.filter(pk=self.pupil.pk).exists(),
                        'выданная работа исчезла вместе с отчислением')

    def test_edit_changes_name(self):
        self.client.force_login(self.teacher)
        self.client.post('/teacher/groups/%d/edit/' % self.group.pk,
                         {'name': 'Новое имя', 'description': 'и описание'})
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Новое имя')

    def test_empty_name_is_refused(self):
        self.client.force_login(self.teacher)
        self.client.post('/teacher/groups/%d/edit/' % self.group.pk,
                         {'name': '   '})
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Моя группа')

    def test_individual_lists_only_my_own_students(self):
        """⚠️ В СПИСКЕ УЧЕНИКОВ — ТОЛЬКО СВОИ, НЕ ВСЯ БАЗА.

        Утечкой был не сам выбор ученика, а СОСТАВ списка: там стояли все
        ученики базы поимённо, включая чужих. Поле осталось (без него нельзя
        завести занятие с тем, кто уже учится у этого репетитора), а список
        сузился до своих.

        ⚠️ Первая версия этого теста требовала, чтобы поля не было ВОВСЕ, —
        и тем самым закрепляла случайно снесённую возможность владельца.
        Её ловили три теста в `problems/tests/test_individual.py`, которые
        старше и описывают настоящее поведение. Прав оказался старый тест.
        """
        alien_tutor = tutor('inv_alien_tu')
        alien = student('inv_alien_st')
        alien_group = StudentGroup.objects.create(name='Чужая',
                                                  teacher=alien_tutor)
        alien_group.students.add(alien)

        self.client.force_login(self.teacher)
        html = self.client.get(
            '/teacher/groups/create/?kind=individual').content.decode('utf-8')

        self.assertIn('name="student"', html)          # поле на месте
        self.assertIn('inv_pupil', html)               # свой ученик виден
        self.assertNotIn('inv_alien_st', html)         # чужой — нет

    def test_individual_without_a_student_is_not_created(self):
        """Индивидуальное занятие без человека — это группа из нуля людей."""
        self.client.force_login(self.teacher)
        self.client.post('/teacher/groups/create/',
                         {'kind': 'individual', 'name': 'Пётр'})
        self.assertFalse(StudentGroup.objects.filter(name='Пётр').exists())


class TeacherBoundaryTests(TestCase):
    """⚠️ ОТРИЦАТЕЛЬНЫЕ: чужое занятие для репетитора не существует."""

    def setUp(self):
        cache.clear()
        self.owner = tutor('bnd_own')
        self.stranger = tutor('bnd_alien')
        self.group = StudentGroup.objects.create(name='Чужая', teacher=self.owner)
        self.pupil = student('bnd_pupil')
        self.group.students.add(self.pupil)

    def test_stranger_does_not_see_the_code(self):
        self.client.force_login(self.stranger)
        response = self.client.get('/teacher/groups/%d/' % self.group.pk)
        self.assertEqual(response.status_code, 404)

    def test_stranger_cannot_regenerate(self):
        self.client.force_login(self.stranger)
        old = self.group.invite_code
        response = self.client.post(
            '/teacher/groups/%d/invite/regenerate/' % self.group.pk)
        self.assertEqual(response.status_code, 404)
        self.group.refresh_from_db()
        self.assertEqual(self.group.invite_code, old)

    def test_stranger_cannot_remove_a_student(self):
        self.client.force_login(self.stranger)
        response = self.client.post('/teacher/groups/%d/students/%d/remove/'
                                    % (self.group.pk, self.pupil.pk))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.group.students.filter(pk=self.pupil.pk).exists())

    def test_stranger_cannot_edit(self):
        self.client.force_login(self.stranger)
        response = self.client.post('/teacher/groups/%d/edit/' % self.group.pk,
                                    {'name': 'Взломано'})
        self.assertEqual(response.status_code, 404)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Чужая')

    def test_student_cannot_use_teacher_screens(self):
        self.client.force_login(self.pupil)
        for url in ('/teacher/groups/%d/' % self.group.pk,
                    '/teacher/groups/%d/edit/' % self.group.pk):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_guest_is_sent_to_login(self):
        response = self.client.get('/teacher/groups/%d/' % self.group.pk)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_regenerate_is_post_only(self):
        """GET не меняет состояние — иначе код сменился бы по ссылке."""
        self.client.force_login(self.owner)
        old = self.group.invite_code
        response = self.client.get(
            '/teacher/groups/%d/invite/regenerate/' % self.group.pk)
        self.assertEqual(response.status_code, 405)
        self.group.refresh_from_db()
        self.assertEqual(self.group.invite_code, old)


class QueryCountTests(TestCase):
    """Число запросов не растёт линейно с числом занятий.

    ⚠️ МЕРИМ РОСТ, А НЕ АБСОЛЮТНОЕ ЧИСЛО. Точное число запросов на экране
    кабинета зависит от того, что на нём ещё показано, и прибивать его
    гвоздём значит ловить чужие правки. Опасен именно РОСТ на занятие:
    он и означает запрос в цикле.
    """

    def _queries(self, url):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
        return len(captured)

    def test_teacher_group_list(self):
        teacher = tutor('q_tu')
        self.client.force_login(teacher)
        for index in range(3):
            StudentGroup.objects.create(name='Г%d' % index, teacher=teacher)
        few = self._queries('/teacher/groups/')
        for index in range(3, 13):
            StudentGroup.objects.create(name='Г%d' % index, teacher=teacher)
        many = self._queries('/teacher/groups/')
        self.assertLessEqual(
            many - few, 10,
            'десять новых занятий добавили %d запросов — это запрос в цикле'
            % (many - few))

    def test_student_dashboard(self):
        """У ученика карточки занятий: автор и число работ — не по запросу."""
        pupil = student('q_st')
        self.client.force_login(pupil)
        teacher = tutor('q_tu2')
        for index in range(2):
            group = StudentGroup.objects.create(name='Г%d' % index,
                                                teacher=teacher)
            group.students.add(pupil)
        few = self._queries('/student/')
        for index in range(2, 7):
            group = StudentGroup.objects.create(name='Г%d' % index,
                                                teacher=teacher)
            group.students.add(pupil)
        many = self._queries('/student/')
        self.assertLessEqual(
            many - few, 3,
            'пять новых занятий добавили %d запросов — карточки ходят в базу '
            'по одной' % (many - few))
