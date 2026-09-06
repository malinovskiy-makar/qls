# -*- coding: utf-8 -*-
"""`dev_scrub` — вычистить людей с площадки dev, не тронув банк задач.

⚠️ ГЛАВНОЕ, ЧТО СТОРОЖИТ ЭТОТ НАБОР, — ПРЕДОХРАНИТЕЛЬ. База площадки
`dev.weconomics.ai` — это копия БОЕВОЙ базы, и команда, которая удаляет всех
пользователей, отличается от катастрофы ровно одной проверкой: `SITE_ENV`
обязан быть `dev`. Запуск той же команды в боевом контейнере (где `SITE_ENV`
равно `prod`) обязан ОТКАЗАТЬСЯ работать до единого удаления.

⚠️ ВТОРОЕ — ЧТО БАНК ЗАДАЧ ПЕРЕЖИВАЕТ УДАЛЕНИЕ ЛЮДЕЙ. У `Problem.owner`
стоит `SET_NULL`, но полагаться на «я посмотрел модель» нельзя: одно
изменение `on_delete` на `CASCADE` в чужой ветке — и `dev_scrub` унесёт
корпус. Поэтому число задач до и после сверяется и тестом, и самой командой.
"""
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from io import StringIO

from problems.models import (
    Assignment, CatalogAttempt, Problem, StudentGroup, User,
)
from problems.models_platform import LearningEvent, UserProfile


def _данные():
    """Три человека, задача, попытка, событие, группа, домашка."""
    учитель = User.objects.create_user(
        username='real-teacher', password='x', role=User.Role.TEACHER)
    ученик = User.objects.create_user(
        username='real-student', password='x', role=User.Role.STUDENT)
    ещё = User.objects.create_user(
        username='real-student-2', password='x', role=User.Role.STUDENT)
    задача = Problem.objects.create(
        title='Задача банка', statement='Условие', owner=учитель)
    CatalogAttempt.objects.create(user=ученик, problem=задача)
    LearningEvent.objects.create(
        user=ученик, source=LearningEvent.Source.CATALOG,
        event_type=LearningEvent.EventType.SOLVED)
    группа = StudentGroup.objects.create(name='Группа', teacher=учитель)
    группа.students.add(ученик, ещё)
    Assignment.objects.create(name='Домашка', author=учитель)
    return задача


class DevScrubGuardTests(TestCase):
    """Предохранитель: без `SITE_ENV=dev` команда не делает ничего."""

    @override_settings(SITE_ENV='prod')
    def test_на_бою_команда_отказывается(self):
        _данные()
        было = User.objects.count()
        with self.assertRaises(CommandError) as ловушка:
            call_command('dev_scrub', '--yes', stdout=StringIO())
        self.assertIn('SITE_ENV', str(ловушка.exception))
        self.assertEqual(User.objects.count(), было,
                         'команда удаляла людей на боевых настройках')

    @override_settings(SITE_ENV='dev', DEV_ACCOUNTS_PASSWORD='dev-probe-2026')
    def test_без_yes_только_план(self):
        _данные()
        было = User.objects.count()
        поток = StringIO()
        call_command('dev_scrub', stdout=поток)
        self.assertEqual(User.objects.count(), было,
                         'без --yes команда всё-таки удаляла')
        вывод = поток.getvalue()
        self.assertIn('--yes', вывод, 'план не объясняет, как запустить по-настоящему')

    @override_settings(SITE_ENV='dev', DEV_ACCOUNTS_PASSWORD='')
    def test_пустой_пароль_отказ(self):
        _данные()
        было = User.objects.count()
        with self.assertRaises(CommandError) as ловушка:
            call_command('dev_scrub', '--yes', stdout=StringIO())
        self.assertIn('DEV_ACCOUNTS_PASSWORD', str(ловушка.exception))
        self.assertEqual(User.objects.count(), было)


@override_settings(SITE_ENV='dev', DEV_ACCOUNTS_PASSWORD='dev-probe-2026')
class DevScrubWorkTests(TestCase):
    """Боевой прогон на площадке: людей нет, банк на месте."""

    def setUp(self):
        self.задача = _данные()
        self.задач_было = Problem.objects.count()
        call_command('dev_scrub', '--yes', stdout=StringIO())

    def test_остаются_ровно_два_аккаунта(self):
        логины = sorted(User.objects.values_list('username', flat=True))
        self.assertEqual(логины, ['dev-student', 'dev-teacher'])

    def test_у_аккаунтов_нужные_роли(self):
        учитель = User.objects.get(username='dev-teacher')
        ученик = User.objects.get(username='dev-student')
        self.assertEqual(учитель.role, User.Role.TEACHER)
        self.assertEqual(ученик.role, User.Role.STUDENT)
        # Профиль — вторая система ролей проекта, и без него кабинет пуст.
        self.assertEqual(учитель.profile.role, UserProfile.Role.TUTOR)
        self.assertEqual(ученик.profile.role, UserProfile.Role.STUDENT)

    def test_пароль_из_переменной_работает(self):
        self.assertTrue(self.client.login(username='dev-teacher',
                                          password='dev-probe-2026'))

    def test_банк_задач_на_месте(self):
        self.assertEqual(Problem.objects.count(), self.задач_было)
        self.assertTrue(Problem.objects.filter(pk=self.задача.pk).exists())

    def test_личное_вычищено(self):
        self.assertEqual(CatalogAttempt.objects.count(), 0)
        self.assertEqual(LearningEvent.objects.count(), 0)
        self.assertEqual(StudentGroup.objects.count(), 0)
        # Домашка переживает удаление автора (`author` = SET_NULL), поэтому
        # её сносит явный список команды, а не каскад. Проверка сторожит
        # именно это: забыв модель в списке, мы оставили бы на площадке
        # чужие домашние задания без единого признака владельца.
        self.assertEqual(Assignment.objects.count(), 0)

    def test_повторный_прогон_не_ломается(self):
        """Идемпотентность: второй запуск не падает и не плодит аккаунты."""
        call_command('dev_scrub', '--yes', stdout=StringIO())
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Problem.objects.count(), self.задач_было)
