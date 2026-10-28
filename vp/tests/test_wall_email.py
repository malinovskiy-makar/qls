"""Стена 2 тура, почтовый путь в окне: `POST /vp/wall/email/<слаг>/` (docs/VP.md).

Почта в памяти (`django.core.mail.outbox`), коды — настоящие `problems.email_codes`.
"""
import re

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from legal import consent
from problems.models_legal import ConsentRecord
from problems.models_mail import EmailCode
from vp import wall
from vp.models import VPWall
from vp.tests.helpers import load_demo

User = get_user_model()
MAIL = ConsentRecord.Kind.MAIL

WALL_MAIL = override_settings(
    VP_WALL_ENABLED=True, MAIL_ENABLED=True, VP_WALL_TG_ENABLED=True,
    TELEGRAM_BOT_TOKEN='000:test-token', TELEGRAM_BOT_USERNAME='test_wall_bot',
    TELEGRAM_WEBHOOK_SECRET='test-secret')


def code_of(message):
    return re.search(r'(\d{6})', message.subject).group(1)


@WALL_MAIL
class WallEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('wall_mail', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('vp:wall_email', args=[self.variant.slug])
        self.intro = reverse('vp:intro', args=[self.variant.slug])

    def post(self, action, **data):
        return self.client.post(self.url, {'action': action, **data})

    def send(self, email='masha@example.ru', box=False):
        data = {'email': email}
        if box:
            data['mail_consent'] = 'on'
        return self.post('send', **data)

    def page(self, state):
        return self.client.get(self.intro, {'wall': state}).content.decode()

    def verify(self, email='masha@example.ru'):
        self.user.email = email
        self.user.email_verified_at = timezone.now()
        self.user.save()

    def test_send_mails_a_code_and_remembers_the_address(self):
        response = self.send()
        self.assertEqual(response['Location'], self.intro + '?wall=code')
        self.assertEqual(len(django_mail.outbox), 1)
        self.assertEqual(self.client.session['vp_wall_email']['email'], 'masha@example.ru')

    def test_right_code_gives_email_contact(self):
        self.send()
        response = self.post('confirm', code=code_of(django_mail.outbox[0]))
        self.assertEqual(response['Location'], self.intro + '?wall=1')
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertEqual(self.user.email, 'masha@example.ru')
        self.assertEqual(VPWall.objects.get(user=self.user).contact_via, 'email')

    def test_consent_only_with_the_box(self):
        self.send()
        self.post('confirm', code=code_of(django_mail.outbox[0]))
        self.assertEqual(ConsentRecord.objects.filter(user=self.user, kind=MAIL).count(), 0)

        other = User.objects.create_user('wall_mail2', password='p12345')
        client = Client()
        client.force_login(other)
        client.post(self.url, {'action': 'send', 'email': 'b@example.ru', 'mail_consent': 'on'})
        client.post(self.url, {'action': 'confirm', 'code': code_of(django_mail.outbox[-1])})
        records = ConsentRecord.objects.filter(user=other, kind=MAIL)
        self.assertEqual(records.count(), 1)
        self.assertEqual(records.get().source, ConsentRecord.Source.VP_WALL)

    def test_wrong_code_shows_attempts_left_and_gives_nothing(self):
        self.send()
        right = code_of(django_mail.outbox[0])
        wrong = '000000' if right != '000000' else '111111'
        response = self.post('confirm', code=wrong)
        self.assertEqual(response['Location'], self.intro + '?wall=code')
        self.assertIn('Осталось попыток: 4', self.page('code'))
        self.assertEqual(wall.step(self.user), 'contact')

    def test_race_other_account_confirms_the_same_email(self):
        self.send(email='race@example.ru')
        other = User.objects.create_user('wall_rival', password='p12345')
        stamp = timezone.now()
        other.email, other.email_verified_at = 'race@example.ru', stamp
        other.save()
        self.post('confirm', code=code_of(django_mail.outbox[0]))
        self.assertIn('Эта почта уже привязана к другому аккаунту.', self.page('email'))
        self.assertEqual(wall.step(self.user), 'contact')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)
        other.refresh_from_db()
        self.assertEqual((other.email, other.email_verified_at), ('race@example.ru', stamp))

    def test_use_with_verified_email_needs_no_code(self):
        self.verify()
        before = EmailCode.objects.count()
        response = self.post('use')
        self.assertEqual(response['Location'], self.intro + '?wall=1')
        self.assertEqual(VPWall.objects.get(user=self.user).contact_via, 'email')
        self.assertEqual(EmailCode.objects.count(), before)

    def test_use_without_verified_email_is_refused(self):
        self.assertEqual(self.post('use').status_code, 400)
        self.assertEqual(wall.step(self.user), 'contact')

    def test_send_with_verified_email_is_refused(self):
        self.verify('old@example.ru')
        self.assertEqual(self.send(email='new@example.ru').status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'old@example.ru')
        self.assertEqual(len(django_mail.outbox), 0)

    def test_unchecked_box_never_revokes(self):
        self.verify()
        consent.grant(self.user, MAIL, ConsentRecord.Source.EMAIL_PAGE)
        self.post('use')
        self.assertTrue(consent.wants_mail(self.user))

    def test_guest_goes_to_login(self):
        response = Client().post(self.url, {'action': 'send', 'email': 'g@example.ru'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/login/'))
        self.assertEqual(len(django_mail.outbox), 0)

    def test_screens_hide_email_from_webvisor(self):
        self.verify()
        known = self.page('email')
        self.assertIn('Продолжить с этой почтой', known)
        self.assertIn('<span class="ym-hide-content">masha@example.ru</span>', known)

        self.user.email_verified_at = None
        self.user.save()
        form = self.page('email')
        self.assertRegex(form, r'class="vp-wall-input ym-disable-keys" type="email"')
        self.assertNotIn('checked', form.split('name="mail_consent"')[1][:40])
        self.send()
        code = self.page('code')
        self.assertIn('<b class="ym-hide-content">masha@example.ru</b>', code)
        self.assertRegex(code, r'class="vp-wall-input vp-wall-code ym-disable-keys"')


@override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=False, VP_WALL_TG_ENABLED=True,
                   TELEGRAM_BOT_TOKEN='000:test-token', TELEGRAM_BOT_USERNAME='test_wall_bot',
                   TELEGRAM_WEBHOOK_SECRET='test-secret')
class WallEmailOffTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def test_mail_off_means_404_and_no_link(self):
        user = User.objects.create_user('wall_off', password='p12345')
        client = Client()
        client.force_login(user)
        url = reverse('vp:wall_email', args=[self.variant.slug])
        self.assertEqual(client.post(url, {'action': 'send', 'email': 'a@b.ru'}).status_code, 404)
        html = client.get(reverse('vp:intro', args=[self.variant.slug]), {'wall': '1'}).content.decode()
        self.assertIn('id="vp-wall"', html)
        self.assertNotIn('Подтвердить почтой', html)
