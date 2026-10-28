# -*- coding: utf-8 -*-
"""Почта, фаза 3: регистрация в два шага и вход почтой (docs/MAIL.md)."""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.db.models import F
from django.test import TestCase, override_settings
from django.utils import timezone

from problems.models_legal import ConsentRecord
from problems.models_mail import EmailCode
from problems.views_auth import PENDING_KEY

User = get_user_model()
PASSWORD = 'Ochen-Dlinnyi-Parol-77'


def code_of(message):
    return re.search(r'(\d{6})', message.subject).group(1)


def wrong(code):
    return '%06d' % ((int(code) + 1) % 10 ** 6)


@override_settings(MAIL_ENABLED=True)
class RegisterWithEmailTests(TestCase):
    def setUp(self):
        cache.clear()

    def step1(self, **overrides):
        data = {'username': 'masha', 'email': 'Masha@Mail.RU', 'password1': PASSWORD,
                'password2': PASSWORD, 'role': 'student', 'consent': 'on'}
        data.update(overrides)
        return self.client.post('/register/', {k: v for k, v in data.items() if v is not None})

    def confirm(self, code):
        return self.client.post('/register/confirm/', {'code': code})

    # 1
    def test_step1_creates_no_user_and_keeps_no_password(self):
        before = User.objects.count()
        response = self.step1()
        self.assertRedirects(response, '/register/confirm/', fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), before)
        self.assertEqual(len(django_mail.outbox), 1)
        self.assertEqual(django_mail.outbox[0].to, ['masha@mail.ru'])
        session = self.client.session
        pending = session[PENDING_KEY]
        self.assertNotIn(PASSWORD, repr(dict(session.items())))
        self.assertNotEqual(pending['password_hash'], PASSWORD)
        page = self.client.get('/register/confirm/')
        self.assertContains(page, 'masha@mail.ru')
        self.assertContains(page, 'autocomplete="one-time-code"')
        self.assertContains(page, 'inputmode="numeric"')

    # 2
    def test_mail_consent_box_is_never_prechecked(self):
        html = self.client.get('/register/').content.decode()
        box = re.search(r'<input type="checkbox" name="mail_consent"[^>]*>', html)
        self.assertIsNotNone(box)
        self.assertNotIn('checked', box.group(0))
        self.assertIn('/legal/consent-mail/', html)
        self.assertIn('name="email"', html)

    # 3
    def test_wrong_code_creates_nobody(self):
        self.step1()
        before = User.objects.count()
        response = self.confirm(wrong(code_of(django_mail.outbox[0])))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Неверный код. Осталось попыток: 4.')
        self.assertEqual(User.objects.count(), before)

    # 4
    def test_right_code_creates_verified_account_with_mail_consent(self):
        self.step1(mail_consent='on', next='/vp/')
        response = self.confirm(code_of(django_mail.outbox[0]))
        self.assertRedirects(response, '/vp/', fetch_redirect_response=False)
        user = User.objects.get(username='masha')
        self.assertEqual(user.email, 'masha@mail.ru')
        self.assertIsNotNone(user.email_verified_at)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(user.profile.role, 'student')
        pd = ConsentRecord.objects.filter(user=user, kind=ConsentRecord.Kind.PD)
        self.assertEqual(pd.count(), 1)
        self.assertEqual(pd.get().source, ConsentRecord.Source.REGISTER)
        self.assertEqual(ConsentRecord.objects.filter(
            user=user, kind=ConsentRecord.Kind.MAIL, source=ConsentRecord.Source.REGISTER).count(), 1)
        self.assertEqual(self.client.session.get('_auth_user_id'), str(user.pk))
        self.assertNotIn(PENDING_KEY, self.client.session)

    def test_right_code_without_mail_consent_and_default_target(self):
        self.step1(role='tutor')
        response = self.confirm(code_of(django_mail.outbox[0]))
        self.assertRedirects(response, '/profile/?welcome=1', fetch_redirect_response=False)
        user = User.objects.get(username='masha')
        self.assertEqual(user.profile.role, 'tutor')
        self.assertEqual(ConsentRecord.objects.filter(user=user, kind=ConsentRecord.Kind.MAIL).count(), 0)
        self.assertEqual(ConsentRecord.objects.filter(user=user, kind=ConsentRecord.Kind.PD).count(), 1)

    def test_foreign_next_is_dropped(self):
        self.step1(next='https://evil.example/')
        response = self.confirm(code_of(django_mail.outbox[0]))
        self.assertRedirects(response, '/profile/?welcome=1', fetch_redirect_response=False)

    # 5
    def test_address_of_a_verified_account_is_refused(self):
        User.objects.create_user('owner', email='masha@mail.ru', password=PASSWORD,
                                 email_verified_at=timezone.now())
        response = self.step1(email='MASHA@mail.ru')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Эта почта уже привязана к аккаунту.')
        self.assertContains(response, 'href="/password/forgot/"')
        self.assertEqual(len(django_mail.outbox), 0)

    # 6
    def test_unverified_old_address_does_not_block(self):
        User.objects.create_user('old', email='masha@mail.ru', password=PASSWORD)
        self.step1()
        response = self.confirm(code_of(django_mail.outbox[0]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(username='masha').email_verified_at)

    # 7
    def test_username_taken_between_steps(self):
        self.step1()
        User.objects.create_user('Masha', password=PASSWORD)
        response = self.confirm(code_of(django_mail.outbox[0]))
        self.assertRedirects(response, '/register/', fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(email='masha@mail.ru').exists())
        self.assertEqual(User.objects.filter(username__iexact='masha').count(), 1)
        page = self.client.get('/register/')
        self.assertContains(page, 'Этот логин успели занять. Начните регистрацию заново.')

    # 8
    def test_pending_older_than_30_minutes_is_dropped(self):
        self.step1()
        session = self.client.session
        pending = session[PENDING_KEY]
        pending['started_at'] -= 31 * 60
        session[PENDING_KEY] = pending
        session.save()
        response = self.client.get('/register/confirm/')
        self.assertRedirects(response, '/register/', fetch_redirect_response=False)
        self.assertNotIn(PENDING_KEY, self.client.session)
        self.assertContains(self.client.get('/register/'),
                            'Время подтверждения вышло, заполните форму ещё раз.')

    def test_confirm_without_pending_goes_to_form(self):
        self.assertRedirects(self.client.get('/register/confirm/'), '/register/',
                             fetch_redirect_response=False)

    # 9
    def test_resend_waits_a_minute_and_kills_old_code(self):
        self.step1()
        old = code_of(django_mail.outbox[0])
        page = self.client.get('/register/confirm/')
        self.assertContains(page, 'data-resend-wait="60"')
        self.assertContains(page, 'disabled')
        response = self.client.post('/register/confirm/', {'action': 'resend'}, follow=True)
        self.assertContains(response, 'Новый можно запросить через')
        self.assertEqual(len(django_mail.outbox), 1)
        delta = timedelta(seconds=61)
        EmailCode.objects.update(created_at=F('created_at') - delta,
                                 expires_at=F('expires_at') - delta)
        response = self.client.post('/register/confirm/', {'action': 'resend'}, follow=True)
        self.assertContains(response, 'Мы отправили новый код.')
        self.assertEqual(len(django_mail.outbox), 2)
        new = code_of(django_mail.outbox[1])
        if new != old:
            self.assertContains(self.confirm(old), 'Неверный код.')
        self.assertEqual(self.confirm(new).status_code, 302)

    def test_change_email_returns_to_filled_form(self):
        self.step1(mail_consent='on', role='tutor', next='/vp/')
        html = self.client.get('/register/?edit=1').content.decode()
        self.assertIn('value="masha"', html)
        self.assertIn('value="masha@mail.ru"', html)
        self.assertIn('name="next" value="/vp/"', html)
        self.assertRegex(html, r'name="mail_consent"\s+checked')
        self.assertRegex(html, r'value="tutor"\s+checked')
        self.assertNotIn(PASSWORD, html)

    def test_wait_with_same_address_goes_to_confirm(self):
        self.step1()
        response = self.step1()
        self.assertRedirects(response, '/register/confirm/', fetch_redirect_response=False)
        self.assertEqual(len(django_mail.outbox), 1)

    # 11
    def test_at_sign_in_new_username_is_refused(self):
        response = self.step1(username='masha@mail.ru')
        self.assertContains(response, 'В логине не может быть @: для почты есть отдельное поле.')
        self.assertEqual(len(django_mail.outbox), 0)

    def test_at_sign_in_profile_username(self):
        user = User.objects.create_user('plain', password=PASSWORD)
        legacy = User.objects.create_user('legacy@mail.ru', password=PASSWORD)
        self.client.force_login(user)
        response = self.client.post('/profile/', {'action': 'data', 'username': 'new@name.ru'})
        self.assertContains(response, 'В логине не может быть @')
        self.assertEqual(User.objects.get(pk=user.pk).username, 'plain')
        # Старый логин с «@» остаётся рабочим: правило только для нового значения.
        self.client.force_login(legacy)
        response = self.client.post('/profile/', {'action': 'data', 'username': 'legacy@mail.ru'})
        self.assertRedirects(response, '/profile/?saved=1', fetch_redirect_response=False)


@override_settings(MAIL_ENABLED=True)
class LoginWithEmailTests(TestCase):
    # 10
    def setUp(self):
        cache.clear()

    def login(self, username, password=PASSWORD):
        return self.client.post('/login/', {'username': username, 'password': password})

    def test_verified_email_in_any_case_logs_in(self):
        user = User.objects.create_user('masha', email='masha@mail.ru', password=PASSWORD,
                                        email_verified_at=timezone.now())
        response = self.login('  MASHA@Mail.ru'.strip())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('_auth_user_id'), str(user.pk))

    def test_unverified_email_gets_the_same_refusal_as_wrong_password(self):
        User.objects.create_user('old', email='old@mail.ru', password=PASSWORD)
        by_email = self.login('old@mail.ru')
        by_bad_password = self.login('old', 'не-тот-пароль-123')
        for response in (by_email, by_bad_password):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Неверный логин или пароль. Попробуйте ещё раз.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_legacy_username_with_at_logs_in_by_username(self):
        user = User.objects.create_user('legacy@mail.ru', password=PASSWORD)
        self.login('legacy@mail.ru')
        self.assertEqual(self.client.session.get('_auth_user_id'), str(user.pk))

    def test_verified_email_wins_over_someone_elses_username(self):
        User.objects.create_user('twin@mail.ru', password='Chuzhoi-Parol-Login-1')
        owner = User.objects.create_user('owner', email='twin@mail.ru', password=PASSWORD,
                                         email_verified_at=timezone.now())
        self.login('twin@mail.ru', 'Chuzhoi-Parol-Login-1')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.login('twin@mail.ru')
        self.assertEqual(self.client.session.get('_auth_user_id'), str(owner.pk))

    def test_login_screen_mentions_email_and_reset(self):
        page = self.client.get('/login/')
        self.assertContains(page, 'Логин или почта')
        self.assertContains(page, 'href="/password/forgot/"')
        self.assertContains(page, 'Нет почты в аккаунте?')


@override_settings(MAIL_ENABLED=False)
class MailDisabledRegistrationTests(TestCase):
    # 12
    def test_old_one_step_registration(self):
        html = self.client.get('/register/').content.decode()
        self.assertNotIn('name="email"', html)
        self.assertNotIn('mail_consent', html)
        response = self.client.post('/register/', {
            'username': 'petya', 'password1': PASSWORD, 'password2': PASSWORD,
            'role': 'student', 'consent': 'on'})
        self.assertRedirects(response, '/profile/?welcome=1', fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username='petya', email='').exists())
        self.assertEqual(len(django_mail.outbox), 0)

    def test_confirm_page_does_not_exist(self):
        self.assertEqual(self.client.get('/register/confirm/').status_code, 404)

    def test_login_screen_is_the_old_one(self):
        page = self.client.get('/login/')
        self.assertNotContains(page, 'Логин или почта')
        self.assertNotContains(page, '/password/forgot/')
