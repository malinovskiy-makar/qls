# -*- coding: utf-8 -*-
"""Почта, фаза 2: модуль кодов (`problems/email_codes.py`, docs/MAIL.md).

Время двигаем сдвигом полей строк назад (`.update(created_at=…)`), как в
`legal/tests/test_purge_expired.py`, — без новых зависимостей.
"""
import re
import smtplib
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.core.management import call_command
from django.db.models import F
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from problems import email_codes, erasure
from problems.email_codes import Purpose
from problems.models_mail import EmailCode

EMAIL = 'masha@mail.ru'


def code_of(message):
    """Код из темы письма; тот же обязан стоять в тексте."""
    return re.search(r'(\d{6})', message.subject).group(1)


def age(seconds, **filters):
    """Состарить коды на `seconds` секунд."""
    delta = timedelta(seconds=seconds)
    EmailCode.objects.filter(**filters).update(
        created_at=F('created_at') - delta, expires_at=F('expires_at') - delta)


@override_settings(MAIL_ENABLED=True)
class EmailCodeTests(TestCase):
    def setUp(self):
        cache.clear()

    def send(self, email=EMAIL, purpose=Purpose.REGISTER, **kwargs):
        return email_codes.send_code(email, purpose, **kwargs)

    # 1
    def test_send_one_letter_and_store_only_a_digest(self):
        result = self.send()
        self.assertEqual(result, email_codes.SendResult(True))
        self.assertEqual(len(django_mail.outbox), 1)
        message = django_mail.outbox[0]
        code = code_of(message)
        self.assertRegex(code, r'^\d{6}$')
        self.assertIn(code, message.body)
        self.assertEqual(re.findall(r'\b\d{6}\b', message.body), [code])
        self.assertEqual(message.subject, 'Код подтверждения Weconomics: %s' % code)
        self.assertEqual(EmailCode.objects.count(), 1)
        row = EmailCode.objects.get()
        for field in row._meta.concrete_fields:
            self.assertNotIn(code, str(getattr(row, field.attname)), field.name)
        self.assertEqual(len(row.code_hash), 64)
        self.assertEqual(row.expires_at - row.created_at, timedelta(minutes=10))

    def test_reset_letter_has_its_own_subject(self):
        self.send(purpose=Purpose.RESET)
        message = django_mail.outbox[0]
        self.assertEqual(message.subject,
                         'Код для смены пароля Weconomics: %s' % code_of(message))
        self.assertIn('Код для смены пароля на Weconomics:', message.body)

    # 2
    def test_resend_too_early_waits(self):
        self.send()
        age(10)
        result = self.send()
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, 'wait')
        self.assertTrue(1 <= result.wait_seconds <= 60, result.wait_seconds)
        self.assertEqual(result.wait_seconds, 50)
        self.assertEqual(len(django_mail.outbox), 1)
        self.assertEqual(email_codes.resend_wait(EMAIL, Purpose.REGISTER), 50)

    # 3
    def test_resend_after_a_minute_kills_the_old_code(self):
        self.send()
        old = code_of(django_mail.outbox[0])
        age(61)
        self.assertTrue(self.send().ok)
        new = code_of(django_mail.outbox[1])
        if new == old:      # один шанс на миллион: перевыпускаем
            age(61)
            self.send()
            new = code_of(django_mail.outbox[2])
        self.assertFalse(email_codes.check_code(EMAIL, Purpose.REGISTER, old).ok)
        self.assertTrue(email_codes.check_code(EMAIL, Purpose.REGISTER, new).ok)

    # 4
    def test_sixth_letter_in_an_hour_is_refused(self):
        for _ in range(5):
            self.assertTrue(self.send().ok)
            age(61)
        result = self.send()
        self.assertEqual(result.reason, 'limit')
        self.assertGreater(result.wait_seconds, 0)
        self.assertEqual(len(django_mail.outbox), 5)

    # 5
    def test_five_wrong_tries_lock_the_code(self):
        self.send()
        code = code_of(django_mail.outbox[0])
        wrong = '%06d' % ((int(code) + 1) % 10 ** 6)
        for left in (4, 3, 2, 1):
            result = email_codes.check_code(EMAIL, Purpose.REGISTER, wrong)
            self.assertEqual((result.reason, result.attempts_left), ('wrong', left))
        self.assertEqual(email_codes.check_code(EMAIL, Purpose.REGISTER, wrong).reason, 'locked')
        self.assertEqual(email_codes.check_code(EMAIL, Purpose.REGISTER, code).reason, 'locked')

    # 6
    def test_code_expires_after_ten_minutes(self):
        self.send()
        code = code_of(django_mail.outbox[0])
        age(11 * 60)
        self.assertEqual(email_codes.check_code(EMAIL, Purpose.REGISTER, code).reason, 'expired')

    # 7
    def test_spaces_are_ignored_and_code_is_single_use(self):
        self.send()
        code = code_of(django_mail.outbox[0])
        spaced = '%s %s' % (code[:3], code[3:])
        self.assertTrue(email_codes.check_code(EMAIL, Purpose.REGISTER, spaced).ok)
        self.assertEqual(email_codes.check_code(EMAIL, Purpose.REGISTER, code).reason, 'missing')

    # 8
    @override_settings(MAIL_ENABLED=False)
    def test_disabled_mail_sends_nothing(self):
        self.assertEqual(self.send(), email_codes.SendResult(False, 'disabled'))
        self.assertEqual(len(django_mail.outbox), 0)
        self.assertEqual(EmailCode.objects.count(), 0)

    # 9
    def test_send_failure_leaves_no_row_and_no_code_in_logs(self):
        error = smtplib.SMTPServerDisconnected('gone')
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=error), \
                self.assertLogs('problems.mail', level='WARNING') as logs:
            result = self.send()
        self.assertEqual(result, email_codes.SendResult(False, 'send_failed'))
        self.assertEqual(EmailCode.objects.count(), 0)
        self.assertFalse(re.search(r'\d{6}', '\n'.join(logs.output)))
        # Неотправленный код не съел минуту ожидания.
        self.assertTrue(self.send().ok)

    # 10
    def test_email_is_normalized(self):
        self.send(email=' Masha@Mail.RU ')
        self.assertEqual(EmailCode.objects.get().email, 'masha@mail.ru')
        self.assertEqual(django_mail.outbox[0].to, ['masha@mail.ru'])
        code = code_of(django_mail.outbox[0])
        self.assertTrue(email_codes.check_code('MASHA@mail.ru', Purpose.REGISTER, code).ok)

    # 11
    def test_code_is_bound_to_its_purpose(self):
        self.send(purpose=Purpose.REGISTER)
        code = code_of(django_mail.outbox[0])
        self.assertEqual(email_codes.check_code(EMAIL, Purpose.RESET, code).reason, 'missing')
        self.send(purpose=Purpose.RESET)
        self.assertEqual(email_codes.check_code(EMAIL, Purpose.RESET, code).reason, 'wrong')
        self.assertTrue(email_codes.check_code(EMAIL, Purpose.REGISTER, code).ok)

    # 12
    def test_many_letters_from_one_network_address_are_stopped(self):
        request = RequestFactory().post('/register/', REMOTE_ADDR='10.1.2.3')
        threshold = 5 * email_codes.ratelimit.IP_MULTIPLIER
        for n in range(threshold):
            self.assertTrue(self.send(email='kid%d@school.ru' % n, request=request).ok)
        result = self.send(email='one-more@school.ru', request=request)
        self.assertEqual(result.reason, 'ip_locked')
        self.assertGreater(result.wait_seconds, 0)
        self.assertEqual(len(django_mail.outbox), threshold)
        other = RequestFactory().post('/register/', REMOTE_ADDR='10.9.9.9')
        self.assertTrue(self.send(email='one-more@school.ru', request=other).ok)

    # 13
    def test_purge_expired_removes_codes_older_than_a_day(self):
        now = timezone.now()
        old = EmailCode.objects.create(email='a@b.ru', purpose=Purpose.REGISTER,
                                       code_hash='x' * 64, created_at=now - timedelta(hours=25),
                                       expires_at=now - timedelta(hours=25) + timedelta(minutes=10))
        fresh = EmailCode.objects.create(email='a@b.ru', purpose=Purpose.REGISTER,
                                         code_hash='y' * 64, created_at=now - timedelta(hours=1),
                                         expires_at=now - timedelta(minutes=50))
        dry = StringIO()
        call_command('purge_expired', stdout=dry)
        self.assertRegex(dry.getvalue(), r'problems\.EmailCode \(старше суток\)\s+1')
        self.assertEqual(EmailCode.objects.count(), 2)
        call_command('purge_expired', '--apply', stdout=StringIO())
        self.assertFalse(EmailCode.objects.filter(pk=old.pk).exists())
        self.assertTrue(EmailCode.objects.filter(pk=fresh.pk).exists())

    def test_erase_user_removes_codes_by_link_and_by_address(self):
        user = get_user_model().objects.create_user('masha', email='Masha@Mail.ru',
                                                    password='x' * 12)
        now = timezone.now()
        common = dict(code_hash='z' * 64, created_at=now, expires_at=now + timedelta(minutes=10))
        EmailCode.objects.create(email='masha@mail.ru', purpose=Purpose.CONFIRM, user=user, **common)
        EmailCode.objects.create(email='masha@mail.ru', purpose=Purpose.REGISTER, **common)
        stranger = EmailCode.objects.create(email='other@mail.ru', purpose=Purpose.REGISTER, **common)
        erasure.erase_user(user)
        self.assertEqual(list(EmailCode.objects.values_list('pk', flat=True)), [stranger.pk])


@override_settings(MAIL_ENABLED=True)
class VerifiedEmailTests(TestCase):
    def test_only_verified_address_counts(self):
        User = get_user_model()
        old = User.objects.create_user('old', email='same@mail.ru', password='x' * 12)
        self.assertFalse(email_codes.has_verified_email(old))
        self.assertIsNone(email_codes.verified_user_for('same@mail.ru'))
        fresh = User.objects.create_user('fresh', email='same@mail.ru', password='x' * 12,
                                         email_verified_at=timezone.now())
        self.assertTrue(email_codes.has_verified_email(fresh))
        self.assertEqual(email_codes.verified_user_for(' SAME@Mail.ru'), fresh)

    def test_two_verified_accounts_cannot_share_an_address(self):
        from django.db import IntegrityError, transaction
        User = get_user_model()
        User.objects.create_user('a', email='twin@mail.ru', password='x' * 12,
                                 email_verified_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('b', email='TWIN@mail.ru', password='x' * 12,
                                     email_verified_at=timezone.now())
