# -*- coding: utf-8 -*-
"""Вход подтверждённой почтой (решение владельца 26.10.2026).

Стоит ПЕРВЫМ в `AUTHENTICATION_BACKENDS`, вторым — штатный `ModelBackend`
(вход по логину).

⚠️ ПОЧЕМУ ДВА БЭКЕНДА, А НЕ ОДИН НАСЛЕДНИК. В каждой открытой сессии Django
записан путь бэкенда, которым человек вошёл, — у всех живых сессий на бою это
`django.contrib.auth.backends.ModelBackend`. Сессия, чей бэкенд пропал из
настроек, становится гостевой: замена бэкенда одним наследником разлогинила
бы всех в момент выкатки.

⚠️ ПОЧТОЙ ВХОДЯТ ТОЛЬКО ПОДТВЕРЖДЁННОЙ. Адреса, введённые в профиле до
26.10.2026, никто не проверял: чужая почта в чужом профиле не должна
становиться ключом к аккаунту.

⚠️ ПОДТВЕРЖДЁННАЯ ПОЧТА ГЛАВНЕЕ ЛОГИНА С «@». У нескольких старых аккаунтов
логин похож на почту. Если введённое совпало с подтверждённой почтой, проверяется
пароль ЕЁ владельца, и при неверном пароле бэкенд бросает `PermissionDenied`:
Django на этом обрывает цепочку, и путь по логину не пробуется. Иначе один и
тот же ввод открывал бы два разных аккаунта.

⚠️ ВРЕМЯ ОТВЕТА НЕ ВЫДАЁТ СУЩЕСТВОВАНИЕ АККАУНТА: на любом пути считается
ровно один хеш пароля — `check_password` владельца почты либо `ModelBackend`
(при несуществующем имени он считает хеш вхолостую, `test_auth_hardening`).

Работает при любом `MAIL_ENABLED`: при выключенной почте подтверждённых
адресов просто нет, и вход идёт по логину, как раньше.
"""
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from .email_codes import verified_user_for


class EmailOrUsernameBackend(ModelBackend):
    """Только путь «подтверждённая почта»; логин — дело `ModelBackend`."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None or '@' not in username:
            return None
        user = verified_user_for(username)
        if user is None:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        raise PermissionDenied
