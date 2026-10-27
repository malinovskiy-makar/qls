# -*- coding: utf-8 -*-
"""Почта, фаза 4: страница «Почта» и профиль с почтой (docs/MAIL.md)."""
import re

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from legal import consent
from problems.models_legal import ConsentRecord

User = get_user_model()
PASSWORD = 'Parol-Dlya-Testa-Pochty-1'
MAIL = ConsentRecord.Kind.MAIL


def code_of(message):
    return re.search(r'(\d{6})', message.subject).group(1)


@override_settings(MAIL_ENABLED=True)
class AccountEmailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('masha', password=PASSWORD)
        self.client.force_login(self.user)

    def save(self, email, consent_box=False, query=''):
        data = {'action': 'save', 'email': email}
        if consent_box:
            data['mail_consent'] = 'on'
        return self.client.post('/account/email/' + query, data)

    def enter_code(self, code):
        return self.client.post('/account/email/', {'action': 'code', 'code': code})

    def mail_records(self, **filters):
        return ConsentRecord.objects.filter(user=self.user, kind=MAIL, **filters)

    def test_guest_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get('/account/email/?next=/vp/&src=vp')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/login/?next='))

    def test_state_line(self):
        self.assertContains(self.client.get('/account/email/'), 'Почта не указана')
        self.user.email = 'old@mail.ru'
        self.user.save()
        self.assertContains(self.client.get('/account/email/'), 'Почта не подтверждена:')

    # 4
    def test_add_email_with_code(self):
        response = self.save('Masha@Mail.ru', consent_box=True)
        self.assertRedirects(response, '/account/email/', fetch_redirect_response=False)
        self.assertEqual(len(django_mail.outbox), 1)
        self.assertIn('Код для подтверждения почты на Weconomics:', django_mail.outbox[0].body)
        page = self.client.get('/account/email/')
        self.assertContains(page, 'autocomplete="one-time-code"')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')       # до кода почта не меняется
        response = self.enter_code(code_of(django_mail.outbox[0]))
        self.assertRedirects(response, '/profile/?tab=data', fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'masha@mail.ru')
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertEqual(self.mail_records(source=ConsentRecord.Source.EMAIL_PAGE).count(), 1)

    def test_wrong_code_keeps_email(self):
        self.save('masha@mail.ru')
        response = self.enter_code('000000' if code_of(django_mail.outbox[0]) != '000000' else '111111')
        self.assertContains(response, 'Неверный код. Осталось попыток: 4.')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_email_of_another_verified_account_is_refused(self):
        User.objects.create_user('owner', email='taken@mail.ru', password=PASSWORD,
                                 email_verified_at=timezone.now())
        response = self.save('TAKEN@mail.ru')
        self.assertContains(response, 'Эта почта уже привязана к другому аккаунту.')
        self.assertEqual(len(django_mail.outbox), 0)

    def test_same_verified_email_only_toggles_consent(self):
        self.user.email = 'masha@mail.ru'
        self.user.email_verified_at = timezone.now()
        self.user.save()
        response = self.save('masha@mail.ru', consent_box=True)
        self.assertRedirects(response, '/profile/?tab=data', fetch_redirect_response=False)
        self.assertEqual(self.mail_records(revoked_at__isnull=True).count(), 1)
        self.save('masha@mail.ru', consent_box=False)
        self.assertEqual(self.mail_records().count(), 1)
        self.assertEqual(self.mail_records(revoked_at__isnull=False).count(), 1)
        self.assertEqual(len(django_mail.outbox), 0)

    # 5
    def test_next_is_followed_only_when_own(self):
        self.save('masha@mail.ru', query='?next=/vp/')
        self.assertRedirects(self.enter_code(code_of(django_mail.outbox[0])), '/vp/',
                             fetch_redirect_response=False)

    def test_foreign_next_goes_to_profile(self):
        self.save('masha@mail.ru', query='?next=https://evil.example/')
        self.assertRedirects(self.enter_code(code_of(django_mail.outbox[0])),
                             '/profile/?tab=data', fetch_redirect_response=False)

    # 6
    def test_vp_wall_source(self):
        self.save('masha@mail.ru', consent_box=True, query='?next=/vp/&src=vp')
        self.enter_code(code_of(django_mail.outbox[0]))
        self.assertEqual(self.mail_records().get().source, ConsentRecord.Source.VP_WALL)

    def test_change_email_on_code_step(self):
        self.save('first@mail.ru', query='?next=/vp/&src=vp')
        page = self.client.get('/account/email/')
        change = re.search(r'href="([^"]*change=1[^"]*)"', page.content.decode()).group(1)
        form = self.client.get(change.replace('&amp;', '&')).content.decode()
        self.assertIn('value="first@mail.ru"', form)
        self.assertIn('name="next" value="/vp/"', form)
        self.assertIn('name="src" value="vp"', form)
        self.assertNotIn('one-time-code', form)

    def test_unchecking_on_new_address_revokes(self):
        consent.grant(self.user, MAIL, ConsentRecord.Source.PROFILE)
        self.save('masha@mail.ru', consent_box=False)
        self.enter_code(code_of(django_mail.outbox[0]))
        self.assertFalse(consent.wants_mail(self.user))

    # 7
    def test_profile_has_no_email_input_and_banner_until_verified(self):
        html = self.client.get('/profile/?tab=data').content.decode()
        self.assertNotIn('name="email"', html)
        self.assertIn('Добавьте почту, по ней можно будет восстановить пароль.', html)
        self.assertIn('Чтобы получать письма, ', html)
        self.save('masha@mail.ru')
        self.enter_code(code_of(django_mail.outbox[0]))
        html = self.client.get('/profile/?tab=data').content.decode()
        self.assertNotIn('Добавьте почту', html)
        self.assertIn('подтверждена', html)
        self.assertIn('role="switch" aria-checked="false"', html)
        self.assertIn('/legal/mail/grant/', html)

    def test_profile_save_does_not_touch_email(self):
        self.user.email = 'masha@mail.ru'
        self.user.email_verified_at = timezone.now()
        self.user.save()
        self.client.post('/profile/', {'action': 'data', 'username': 'masha',
                                       'email': 'evil@mail.ru'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'masha@mail.ru')
