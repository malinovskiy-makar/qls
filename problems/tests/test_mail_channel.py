# -*- coding: utf-8 -*-
"""Почта, фаза 1: канал отправки (`problems/mail.py`), шаблоны, `mail.E001`,
`send_test_email`. Письма уходят в `mail.outbox` (тестовый бэкенд Django)."""
import re
import smtplib
from io import StringIO
from unittest import mock

from django.core import mail as django_mail
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from problems import checks, mail

CODE = '048213'
SUBJECT = 'Код подтверждения Weconomics: %s' % CODE
ALLOWED_LINKS = {'https://weconomics.ai/', 'https://t.me/weconomics_ru'}


def send(**overrides):
    kwargs = dict(to='masha@gmail.com', subject=SUBJECT, template='code',
                  context={'intro': 'Код для регистрации на Weconomics:', 'code': CODE})
    kwargs.update(overrides)
    return mail.send_templated(**kwargs)


@override_settings(DEFAULT_FROM_EMAIL='Weconomics <noreply@weconomics.ai>',
                   MAIL_REPLY_TO='weconomics.privacy@vk.com')
class SendTemplatedTests(SimpleTestCase):
    def test_sender_reply_to_and_auto_submitted(self):
        self.assertTrue(send())
        self.assertEqual(len(django_mail.outbox), 1)
        message = django_mail.outbox[0]
        self.assertEqual(message.from_email, 'Weconomics <noreply@weconomics.ai>')
        self.assertEqual(message.reply_to, ['weconomics.privacy@vk.com'])
        self.assertEqual(message.to, ['masha@gmail.com'])
        self.assertEqual(message.extra_headers.get('Auto-Submitted'), 'auto-generated')
        self.assertIn(CODE, message.body)
        self.assertIn('Код действует 10 минут.', message.body)

    @override_settings(MAIL_REPLY_TO='')
    def test_no_reply_to_when_empty(self):
        self.assertTrue(send())
        self.assertEqual(django_mail.outbox[0].reply_to, [])

    def test_html_has_no_images_and_only_two_links(self):
        send()
        html, mimetype = django_mail.outbox[0].alternatives[0]
        self.assertEqual(mimetype, 'text/html')
        self.assertIn(CODE, html)
        self.assertNotIn('<img', html.lower())
        self.assertNotIn('<style', html.lower())
        links = set(re.findall(r'href="([^"]+)"', html))
        self.assertTrue(links)
        self.assertLessEqual(links, ALLOWED_LINKS)
        text_links = set(re.findall(r'https?://\S+', django_mail.outbox[0].body))
        self.assertLessEqual(text_links, ALLOWED_LINKS)

    def test_failure_returns_false_and_log_has_no_subject_or_code(self):
        error = smtplib.SMTPServerDisconnected('connection lost while sending %s' % SUBJECT)
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=error), \
                self.assertLogs('problems.mail', level='WARNING') as logs:
            self.assertFalse(send())
        text = '\n'.join(logs.output)
        self.assertNotIn(CODE, text)
        self.assertNotIn('Код подтверждения', text)
        self.assertNotIn('masha@gmail.com', text)
        self.assertIn('m***@gmail.com', text)
        self.assertIn('SMTPServerDisconnected', text)

    def test_network_error_returns_false(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=ConnectionRefusedError()), \
                self.assertLogs('problems.mail', level='WARNING'):
            self.assertFalse(send())

    def test_temporary_4xx_is_retried_exactly_once(self):
        busy = smtplib.SMTPSenderRefused(454, b'Throttling', 'noreply@weconomics.ai')
        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=[busy, 1]) as send_mock, \
                mock.patch('problems.mail.time.sleep') as sleep:
            self.assertTrue(send())
        self.assertEqual(send_mock.call_count, 2)
        sleep.assert_called_once_with(mail.RETRY_DELAY)

    def test_second_4xx_gives_up_after_one_retry(self):
        busy = smtplib.SMTPDataError(451, b'Try later')
        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=[busy, busy, busy]) as send_mock, \
                mock.patch('problems.mail.time.sleep'), \
                self.assertLogs('problems.mail', level='WARNING') as logs:
            self.assertFalse(send())
        self.assertEqual(send_mock.call_count, 2)
        self.assertIn('451', '\n'.join(logs.output))

    def test_permanent_5xx_is_not_retried(self):
        refused = smtplib.SMTPRecipientsRefused({'masha@gmail.com': (550, b'No such user')})
        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=refused) as send_mock, \
                mock.patch('problems.mail.time.sleep') as sleep, \
                self.assertLogs('problems.mail', level='WARNING') as logs:
            self.assertFalse(send())
        self.assertEqual(send_mock.call_count, 1)
        sleep.assert_not_called()
        self.assertIn('550', '\n'.join(logs.output))

    def test_mask_email(self):
        self.assertEqual(mail.mask_email('masha@gmail.com'), 'm***@gmail.com')
        self.assertEqual(mail.mask_email('broken'), '***')


class MailCheckTests(SimpleTestCase):
    FULL = dict(EMAIL_HOST='postbox.cloud.yandex.net', EMAIL_HOST_USER='id',
                EMAIL_HOST_PASSWORD='secret')

    def ids(self):
        return [e.id for e in checks.mail_channel_configured(None)]

    @override_settings(DEBUG=False, MAIL_ENABLED=True, EMAIL_HOST='',
                       EMAIL_HOST_USER='id', EMAIL_HOST_PASSWORD='secret')
    def test_enabled_without_host_is_an_error(self):
        self.assertEqual(self.ids(), ['mail.E001'])
        error = checks.mail_channel_configured(None)[0]
        self.assertIn('EMAIL_HOST', error.msg)

    @override_settings(DEBUG=False, MAIL_ENABLED=True, **FULL)
    def test_enabled_with_channel_is_fine(self):
        self.assertEqual(self.ids(), [])

    @override_settings(DEBUG=False, MAIL_ENABLED=False, EMAIL_HOST='')
    def test_disabled_mail_needs_no_channel(self):
        self.assertEqual(self.ids(), [])

    @override_settings(DEBUG=True, MAIL_ENABLED=True, EMAIL_HOST='')
    def test_debug_prints_to_console_without_error(self):
        self.assertEqual(self.ids(), [])


@override_settings(MAIL_ENABLED=False, MAIL_REPLY_TO='weconomics.privacy@vk.com')
class SendTestEmailCommandTests(SimpleTestCase):
    def test_sends_exactly_one_letter_even_with_mail_disabled(self):
        out = StringIO()
        call_command('send_test_email', 'andrey@yandex.ru', stdout=out)
        self.assertEqual(len(django_mail.outbox), 1)
        message = django_mail.outbox[0]
        self.assertEqual(message.subject, 'Проверка почты Weconomics')
        self.assertIn('канал отправки работает', message.body)
        self.assertIn('weconomics.privacy@vk.com', out.getvalue())

    def test_failure_exits_with_error(self):
        from django.core.management.base import CommandError
        with mock.patch('problems.mail.send_templated', return_value=False), \
                self.assertRaises(CommandError):
            call_command('send_test_email', 'andrey@yandex.ru', stdout=StringIO())
