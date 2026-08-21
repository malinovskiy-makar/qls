# -*- coding: utf-8 -*-
"""`lockdown_dev_accounts` обязан гасить сессию в ОБОИХ хранилищах.

⚠️ ЗАЧЕМ ЭТОТ ФАЙЛ. Командой пользуются ПЕРЕД ПОКАЗОМ ПРОЕКТА кому-либо:
она гасит учётки с публично известными паролями (`admin12345` и подобные).
С 2026-08-21 движок сессий — `cached_db`, и у каждой сессии две копии:
строка в `django_session` и ключ в кэше. Раньше команда сносила только
строку, а `cached_db` читает сессию из кэша, вообще не заглядывая в базу, —
то есть погашенный аккаунт оставался вошедшим ещё до двух недель.

Команда, которая гасит не до конца, ХУЖЕ отсутствующей: на неё полагаются.
"""
from importlib import import_module

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import TestCase

from problems.management.commands.lockdown_dev_accounts import kill_sessions
from problems.models import User


def _хранилище():
    return import_module(settings.SESSION_ENGINE).SessionStore


class KillSessionsClearsBothCopiesTests(TestCase):

    def setUp(self):
        self.жертва = User.objects.create_user(
            username='демо-жертва', password='admin12345')
        self.посторонний = User.objects.create_user(
            username='посторонний', password='свой-нормальный-пароль-9')

    def _завести_сессию(self, user):
        """Кладёт сессию так же, как это делает вход в систему."""
        store = _хранилище()()
        store['_auth_user_id'] = str(user.pk)
        store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        store.create()
        return store.session_key

    def test_сессия_исчезает_и_из_базы_и_из_кэша(self):
        ключ = self._завести_сессию(self.жертва)
        self.assertTrue(Session.objects.filter(pk=ключ).exists())
        # Прогреваем кэш: именно так и получается вторая копия — cached_db
        # кладёт сессию в кэш при первом чтении.
        self.assertEqual(_хранилище()(session_key=ключ).get('_auth_user_id'),
                         str(self.жертва.pk))

        снято = kill_sessions([self.жертва.pk])
        self.assertEqual(снято, 1)

        self.assertFalse(Session.objects.filter(pk=ключ).exists(),
                         'строка сессии осталась в базе')
        # ⚠️ ГЛАВНАЯ ПРОВЕРКА. Читаем сессию заново: если копия осталась
        # в кэше, cached_db отдаст её, не заглядывая в базу, и погашенный
        # аккаунт по старой куке войдёт как ни в чём не бывало.
        заново = _хранилище()(session_key=ключ)
        self.assertIsNone(
            заново.get('_auth_user_id'),
            'Сессия жива в кэше после гашения: команда сносит только строку '
            'в базе, а у cached_db есть вторая копия. Аккаунт с публично '
            'известным паролем остался бы вошедшим.')

    def test_чужая_сессия_не_страдает(self):
        чужой_ключ = self._завести_сессию(self.посторонний)
        мой_ключ = self._завести_сессию(self.жертва)

        kill_sessions([self.жертва.pk])

        self.assertFalse(Session.objects.filter(pk=мой_ключ).exists())
        self.assertTrue(Session.objects.filter(pk=чужой_ключ).exists(),
                        'снесли сессию постороннего пользователя')
        self.assertEqual(
            _хранилище()(session_key=чужой_ключ).get('_auth_user_id'),
            str(self.посторонний.pk))

    def test_команда_целиком_гасит_вход_по_старой_куке(self):
        """Сквозная проверка: после --apply старая кука доступа не даёт."""
        ключ = self._завести_сессию(self.жертва)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = ключ

        call_command('lockdown_dev_accounts', '--apply', verbosity=0)

        ответ = self.client.get('/student/')
        self.assertNotEqual(
            ответ.status_code, 200,
            'По старой куке всё ещё пускает: гашение не сработало.')
