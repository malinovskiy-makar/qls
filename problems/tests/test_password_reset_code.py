# -*- coding: utf-8 -*-
"""Почта, фаза 4: сброс пароля кодом (docs/MAIL.md)."""
import re

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from problems.models_mail import EmailCode

User = get_user_model()
OLD = 'Staryi-Parol-Uchenika-1'
NEW = 'Novyi-Parol-Uchenika-22'
SENT = 'Если эта почта привязана к аккаунту, мы отправили на неё код.'


def code_of(message):
    return re.search(r'(\d{6})', message.subject).group(1)


def wrong(code):
    return '%06d' % ((int(code) + 1) % 10 ** 6)


@override_settings(MAIL_ENABLED=True)
class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('masha', email='masha@mail.ru', password=OLD,
                                             email_verified_at=timezone.now())

    def ask(self, email):
        return self.client.post('/password/forgot/', {'email': email})

    def submit(self, code, password=NEW, again=None):
        return self.client.post('/password/forgot/code/', {
            'code': code, 'new_password1': password, 'new_password2': again or password})

    # 1
    def test_same_answer_for_known_and_unknown_address(self):
        unknown = self.ask('nobody@mail.ru')
        self.assertRedirects(unknown, '/password/forgot/code/', fetch_redirect_response=False)
        page_unknown = self.client.get('/password/forgot/code/').content.decode()
        self.assertEqual(len(django_mail.outbox), 0)

        other = Client()
        known = other.post('/password/forgot/', {'email': 'MASHA@mail.ru'})
        self.assertRedirects(known, '/password/forgot/code/', fetch_redirect_response=False)
        page_known = other.get('/password/forgot/code/').content.decode()
        self.assertEqual(len(django_mail.outbox), 1)
        self.assertEqual(django_mail.outbox[0].subject,
                         'Код для смены пароля Weconomics: %s' % code_of(django_mail.outbox[0]))
        for page in (page_unknown, page_known):
            self.assertIn(SENT, page)
        # Таймер повтора одинаков: считается от запроса, а не по письмам.
        wait = re.compile(r'data-resend-wait="(\d+)"')
        self.assertEqual(wait.search(page_unknown).group(1), wait.search(page_known).group(1))

    def test_unverified_address_gets_no_letter(self):
        User.objects.create_user('old', email='old@mail.ru', password=OLD)
        self.assertRedirects(self.ask('old@mail.ru'), '/password/forgot/code/',
                             fetch_redirect_response=False)
        self.assertEqual(len(django_mail.outbox), 0)

    def test_unknown_address_wrong_code_reads_the_same(self):
        self.ask('nobody@mail.ru')
        response = self.submit('123456')
        self.assertContains(response, 'Неверный или устаревший код.')

    # 2
    def test_right_code_changes_password_and_ends_old_sessions(self):
        before = Client()
        before.force_login(self.user)
        self.assertEqual(before.get('/profile/').status_code, 200)
        self.ask('masha@mail.ru')
        response = self.submit(code_of(django_mail.outbox[0]))
        self.assertRedirects(response, '/login/', fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertTrue(EmailCode.objects.get().used_at)
        self.assertEqual(before.get('/profile/').status_code, 302)
        self.assertContains(self.client.get('/login/'), 'Пароль изменён. Войдите с новым паролем.')
        self.assertTrue(self.client.login(username='masha@mail.ru', password=NEW))

    # 3
    def test_five_wrong_codes_lock(self):
        self.ask('masha@mail.ru')
        code = code_of(django_mail.outbox[0])
        for _ in range(4):
            self.assertContains(self.submit(wrong(code)), 'Неверный или устаревший код.')
        self.assertContains(self.submit(wrong(code)), 'Слишком много попыток. Запросите новый код.')
        self.submit(code)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_bad_password_does_not_burn_the_code(self):
        self.ask('masha@mail.ru')
        code = code_of(django_mail.outbox[0])
        response = self.submit(code, password='123')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(EmailCode.objects.get().used_at)
        self.assertEqual(EmailCode.objects.get().attempts, 0)
        self.submit(code)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))

    def test_code_page_without_request_goes_back(self):
        self.assertRedirects(self.client.get('/password/forgot/code/'), '/password/forgot/',
                             fetch_redirect_response=False)

    @override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
    def test_consent_gate_leaves_guests_alone(self):
        self.assertEqual(self.client.get('/password/forgot/').status_code, 200)
        self.ask('masha@mail.ru')
        self.assertEqual(self.client.get('/password/forgot/code/').status_code, 200)


@override_settings(MAIL_ENABLED=False)
class MailDisabledPagesTests(TestCase):
    # 10
    def test_new_pages_do_not_exist(self):
        user = User.objects.create_user('masha', password=OLD)
        self.client.force_login(user)
        for url in ('/password/forgot/', '/password/forgot/code/', '/account/email/',
                    '/legal/consent-mail/', '/register/confirm/'):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        for url in ('/legal/mail/grant/', '/legal/mail/revoke/'):
            self.assertEqual(self.client.post(url).status_code, 404, url)
        self.assertNotContains(self.client.get('/legal/'), 'consent-mail')
