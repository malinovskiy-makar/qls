# -*- coding: utf-8 -*-
"""Фаза 1 сессии 3А: три находки карты маршрутов, закрытые отрицательными тестами.

Отрицательный тест — это тест, который КРАСНЕЕТ, если дыру вернуть. Обычный
тест доказывает, что всё работает у правильного пользователя; здесь ровно
наоборот — что всё ломается у неправильного.

⚠️ НИ ОДИН ТЕСТ ЗДЕСЬ НЕ ОПИРАЕТСЯ НА КОНКРЕТНЫЕ id. Счётчики автоинкремента
в PostgreSQL не откатываются вместе с транзакцией, соседний тест по алфавиту
двигает их, и проверка вида «объект получил номер 5» была бы зелёной по
неправильной причине. Чужие номера берутся из созданных объектов, а
заведомо отсутствующий — как `max(id) + 1000`.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import CalendarEvent, StudentGroup
from problems.models_platform import UserProfile

User = get_user_model()

PASSWORD = 'proverka12345'


def _login(username):
    client = Client()
    assert client.login(username=username, password=PASSWORD), (
        'не удалось войти как %s' % username)
    return client


# ===========================================================================
# 1.1. Две системы ролей приведены к одной проверке
# ===========================================================================

class RoleSystemsAgreeTests(TestCase):
    """Репетитор проходит одинаково, каким бы способом он ни заведён.

    ⚠️ ЧТО ИМЕННО БЫЛО СЛОМАНО. В проекте две системы ролей: старое поле
    `User.role` и новая `UserProfile.role`. Синхронизация между ними
    ОДНОСТОРОННЯЯ — профиль подтягивает старое поле (`sync_user_role`), но не
    наоборот. Декоратор `teacher_required` смотрел только старое поле, а
    `tutor_required` — обе системы. Итог: один и тот же человек проходил на
    95 маршрутов кабинета и получал 403 на шести.
    """

    @classmethod
    def setUpTestData(cls):
        # (1) Заведён по-старому: роль в User, профиль остался ученическим.
        cls.old_only = User.objects.create_user('tutor_old',
                                                password=PASSWORD)
        cls.old_only.role = 'teacher'
        cls.old_only.save()

        # (2) Заведён по-новому: роль в профиле, а старое поле РАССИНХРОНЕНО.
        # Это не выдумка ради теста: `sync_user_role` пишет в одну сторону,
        # и правка `User.role` через админку профиль не подтянет.
        cls.profile_only = User.objects.create_user('tutor_profile',
                                                    password=PASSWORD)
        profile = cls.profile_only.profile
        profile.role = UserProfile.Role.TUTOR
        profile.save()
        User.objects.filter(pk=cls.profile_only.pk).update(role='student')
        cls.profile_only.refresh_from_db()

        # (3) Обе системы согласованы — штатный случай.
        cls.both = User.objects.create_user('tutor_both', password=PASSWORD)
        both_profile = cls.both.profile
        both_profile.role = UserProfile.Role.TUTOR
        both_profile.save()
        cls.both.refresh_from_db()

        # (4) Не репетитор ни по одной системе — контроль на отказ.
        cls.student = User.objects.create_user('pupil', password=PASSWORD)

    def test_fixture_really_is_desynced(self):
        """Проверка самой заготовки: рассинхрон действительно есть.

        Без неё главный тест мог бы стать зелёным по неправильной причине —
        если бы синхронизация однажды стала двусторонней, «профиль без
        старого поля» перестал бы существовать, и проверять было бы нечего.
        """
        self.assertEqual(self.profile_only.role, 'student')
        self.assertEqual(self.profile_only.profile.role,
                         UserProfile.Role.TUTOR)

    # Маршруты, висевшие на СТАРОЙ проверке. Именно они отвечали 403
    # репетитору из профиля.
    #
    # ⚠️ У КАЖДОГО РЕПЕТИТОРА СВОЙ УЧЕНИК, И ЭТО НЕ МЕЛОЧЬ. Первая версия
    # теста давала всем троим одного ученика из группы `both` — и он честно
    # краснел, но не на роли, а на ВЛАДЕНИИ: `student_progress` проверяет,
    # что ученик занимается у этого репетитора. Тест, смешивающий две
    # границы, не доказывает ни одной.
    def _urls_for(self, tutor):
        group = StudentGroup.objects.create(
            name='Занятие %s' % tutor.username, teacher=tutor)
        pupil = User.objects.create_user('pupil_of_%s' % tutor.username,
                                         password=PASSWORD)
        pupil.role = 'student'
        pupil.save()
        group.students.add(pupil)
        return [
            reverse('teacher:student_progress', args=[pupil.pk]),
            reverse('teacher:api_problem_detail', args=['1']),
            # ⚠️ ТОЛЬКО GET. POST на этот адрес СОЗДАЁТ РАБОТУ, и второй
            # точки создания в проекте нет. GET отдаёт редирект и ничего
            # не меняет — этого достаточно, чтобы увидеть работу декоратора.
            reverse('teacher:assignment_create'),
        ]

    def test_all_three_tutors_pass_the_old_check_routes(self):
        """Все три способа завести репетитора дают ОДИН И ТОТ ЖЕ доступ."""
        for user in (self.old_only, self.profile_only, self.both):
            client = _login(user.username)
            for url in self._urls_for(user):
                with self.subTest(user=user.username, url=url):
                    response = client.get(url)
                    self.assertNotEqual(
                        response.status_code, 403,
                        'репетитор %s получил 403 на %s' % (user.username, url))

    def test_non_tutor_is_still_refused(self):
        """Контроль: объединение проверок не открыло дверь ученику."""
        urls = self._urls_for(self.both)
        client = _login(self.student.username)
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)

    def test_guest_is_redirected_to_login(self):
        """Гость уходит на вход, а не получает страницу."""
        for url in self._urls_for(self.both):
            with self.subTest(url=url):
                response = Client().get(url)
                self.assertIn(response.status_code, (302, 403))
                if response.status_code == 302:
                    self.assertIn('/login/', response['Location'])

    def test_one_implementation_left(self):
        """`teacher_required` и `tutor_required` — это один объект.

        Смысл проверки не в стиле: пока реализаций две, любая правка права
        обязана быть внесена дважды, и однажды её внесут один раз.
        """
        from teacher.access import tutor_required
        from teacher.views import teacher_required

        self.assertIs(teacher_required, tutor_required)


# ===========================================================================
# 1.2. assignment_print закрыт декоратором
# ===========================================================================

class AssignmentPrintAccessTests(TestCase):
    """Печатный лист чужой работы не открывается, а гость не роняет сервер."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('print_owner',
                                             password=PASSWORD, role='teacher')
        cls.stranger = User.objects.create_user('print_stranger',
                                                password=PASSWORD,
                                                role='teacher')
        cls.student = User.objects.create_user('print_pupil',
                                               password=PASSWORD)

        cls.group = StudentGroup.objects.create(name='Своё занятие',
                                                teacher=cls.owner)
        cls.group.students.add(cls.student)

        from problems.models import Assignment
        cls.assignment = Assignment.objects.create(
            name='Работа на печать', author=cls.owner, group=cls.group)
        cls.url = reverse('teacher:assignment_print',
                          args=[cls.group.pk, cls.assignment.pk])

    def test_guest_does_not_get_a_server_error(self):
        """Главное в этой проверке — что ответ НЕ пятисотый.

        Раньше гость получал 500: `own_group_or_404` фильтровал
        `teacher=AnonymousUser`, и запрос падал несравнимым типом ещё до
        базы. Пятисотая на месте проверки прав — это и шум в мониторинге,
        и трассировка наружу при включённом отладочном режиме.
        """
        response = Client().get(self.url)
        self.assertNotEqual(response.status_code, 500)
        self.assertIn(response.status_code, (302, 403))
        if response.status_code == 302:
            self.assertIn('/login/', response['Location'])

    def test_stranger_tutor_gets_404(self):
        """Чужой репетитор не видит даже факта существования работы."""
        client = _login(self.stranger.username)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, 'Работа на печать',
                               status_code=404)

    def test_student_is_refused(self):
        """Ученик в кабинет репетитора не ходит вовсе."""
        client = _login(self.student.username)
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_owner_still_gets_the_sheet(self):
        """Контроль: владельцу лист по-прежнему открывается."""
        client = _login(self.owner.username)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Работа на печать')


# ===========================================================================
# 1.3. event_delete не сносит чужие звенья серии
# ===========================================================================

class CalendarSeriesDeleteTests(TestCase):
    """Удаление серии повторов не выходит за пределы своих событий."""

    @classmethod
    def setUpTestData(cls):
        cls.mine = User.objects.create_user('cal_mine', password=PASSWORD,
                                            role='teacher')
        cls.other = User.objects.create_user('cal_other', password=PASSWORD,
                                             role='teacher')

    def setUp(self):
        now = timezone.now()
        # Серия: родитель мой, одно звено моё, одно звено ЧУЖОЕ.
        # Чужое звено внутри серии — не выдумка: `parent_event` обычный
        # внешний ключ, и админка позволяет его переставить.
        self.parent = CalendarEvent.objects.create(
            title='Родитель серии', author=self.mine, start_datetime=now,
            is_recurring=True)
        self.mine_child = CalendarEvent.objects.create(
            title='Моё звено', author=self.mine, start_datetime=now,
            parent_event=self.parent)
        self.alien_child = CalendarEvent.objects.create(
            title='ЧУЖОЕ звено', author=self.other, start_datetime=now,
            parent_event=self.parent)

    def _delete_all(self, client, event):
        return client.post(
            reverse('calendar_stub:event_delete', args=[event.pk]),
            data='{"delete_all": true}',
            content_type='application/json')

    def test_alien_link_survives_series_delete(self):
        """Своё удаляется, ЧУЖОЕ остаётся. Это и есть закрытая дыра."""
        client = _login(self.mine.username)
        response = self._delete_all(client, self.parent)
        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            CalendarEvent.objects.filter(pk=self.parent.pk).exists(),
            'своё родительское звено обязано было удалиться')
        self.assertFalse(
            CalendarEvent.objects.filter(pk=self.mine_child.pk).exists(),
            'своё дочернее звено обязано было удалиться')
        self.assertTrue(
            CalendarEvent.objects.filter(pk=self.alien_child.pk).exists(),
            'ЧУЖОЕ звено удалено — дыра вернулась')

    def test_alien_link_is_only_orphaned_not_broken(self):
        """Осиротевшее чужое звено остаётся целым, а не ломается.

        `parent_event` объявлен с `on_delete=SET_NULL`, поэтому звено просто
        перестаёт быть частью серии. Проверяем именно это, а не «оно есть».
        """
        client = _login(self.mine.username)
        self._delete_all(client, self.parent)

        alien = CalendarEvent.objects.get(pk=self.alien_child.pk)
        self.assertIsNone(alien.parent_event_id)
        self.assertEqual(alien.title, 'ЧУЖОЕ звено')
        self.assertEqual(alien.author_id, self.other.pk)

    def test_stranger_cannot_delete_someone_elses_series(self):
        """Автор чужого звена не сносит серию через своё звено.

        Он вправе удалить СВОЁ звено — и ровно его, а родитель и соседнее
        звено чужие и обязаны уцелеть.
        """
        client = _login(self.other.username)
        response = self._delete_all(client, self.alien_child)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            CalendarEvent.objects.filter(pk=self.parent.pk).exists(),
            'чужой родитель серии удалён — дыра вернулась')
        self.assertTrue(
            CalendarEvent.objects.filter(pk=self.mine_child.pk).exists(),
            'чужое звено серии удалено — дыра вернулась')

    def test_outsider_cannot_delete_at_all(self):
        """Посторонний не удаляет ничего и получает отказ."""
        outsider = User.objects.create_user('cal_outsider', password=PASSWORD)
        client = _login(outsider.username)
        response = self._delete_all(client, self.parent)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            CalendarEvent.objects.filter(
                pk__in=[self.parent.pk, self.mine_child.pk,
                        self.alien_child.pk]).count(), 3)

    def test_single_delete_still_works(self):
        """Контроль: обычное удаление одного события не сломано."""
        client = _login(self.mine.username)
        response = client.post(
            reverse('calendar_stub:event_delete', args=[self.mine_child.pk]),
            data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CalendarEvent.objects.filter(pk=self.mine_child.pk).exists())
        self.assertTrue(
            CalendarEvent.objects.filter(pk=self.parent.pk).exists())
