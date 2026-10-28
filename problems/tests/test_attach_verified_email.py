# -*- coding: utf-8 -*-
"""Привязка подтверждённой почты — одно место для страницы «Почта» и стены ВП.

`problems.email_codes.attach_verified_email` (docs/MAIL.md, «Интерфейс для
других приложений»).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from problems import email_codes
from problems.email_codes import EmailTaken, attach_verified_email

User = get_user_model()


class AttachVerifiedEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('masha', password='Parol-1-Dlya-Testa')
        self.other = User.objects.create_user('petya', password='Parol-1-Dlya-Testa')

    def test_free_email_fills_fields(self):
        attach_verified_email(self.user, '  Masha@Example.RU ')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'masha@example.ru')
        self.assertIsNotNone(self.user.email_verified_at)

    def test_email_verified_by_other_raises_and_changes_nothing(self):
        stamp = timezone.now()
        self.other.email = 'shared@example.ru'
        self.other.email_verified_at = stamp
        self.other.save()
        with self.assertRaises(EmailTaken):
            attach_verified_email(self.user, 'Shared@example.ru')
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.email, '')
        self.assertIsNone(self.user.email_verified_at)
        self.assertEqual(self.other.email, 'shared@example.ru')
        self.assertEqual(self.other.email_verified_at, stamp)

    def test_same_email_of_own_account_is_fine(self):
        self.user.email = 'masha@example.ru'
        self.user.email_verified_at = timezone.now()
        self.user.save()
        attach_verified_email(self.user, 'MASHA@example.ru')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'masha@example.ru')
        self.assertIsNotNone(self.user.email_verified_at)

    def test_race_other_account_confirms_after_free_check(self):
        # Представление проверило «почта свободна» ...
        self.assertIsNone(email_codes.verified_user_for('race@example.ru'))
        # ... тут другой аккаунт успел ввести свой код на ту же почту ...
        self.other.email = 'race@example.ru'
        self.other.email_verified_at = timezone.now()
        self.other.save()
        # ... и привязка обязана сказать «занята», а не уронить IntegrityError.
        with self.assertRaises(EmailTaken):
            attach_verified_email(self.user, 'race@example.ru')
        self.assertEqual(self.user.email, '')  # объект в памяти не испорчен
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)
        self.other.refresh_from_db()
        self.assertEqual(self.other.email, 'race@example.ru')
