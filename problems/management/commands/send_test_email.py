# -*- coding: utf-8 -*-
"""Проверочное письмо через настоящий канал отправки (docs/MAIL.md).

    python manage.py send_test_email адрес@пример.ru

Работает НЕЗАВИСИМО от MAIL_ENABLED: ею проверяют канал на сервере ДО того,
как включить почту для людей. Печатает, через что и от кого ушло письмо и
куда ведёт «Ответить». Не ушло — код выхода 1 и причина (класс и код ошибки
сервера) из журнала `problems.mail`.
"""
import logging
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

from problems import mail


class Command(BaseCommand):
    help = 'Отправить проверочное письмо через настоящий канал почты.'

    def add_arguments(self, parser):
        parser.add_argument('address', help='Куда отправить проверочное письмо.')

    def handle(self, *args, **options):
        address = options['address'].strip()
        try:
            validate_email(address)
        except ValidationError:
            raise CommandError('Это не похоже на адрес почты: %r' % address)

        self.stdout.write('Канал (EMAIL_BACKEND): %s' % settings.EMAIL_BACKEND)
        if settings.EMAIL_HOST:
            self.stdout.write('Сервер: %s:%s' % (settings.EMAIL_HOST, settings.EMAIL_PORT))
        self.stdout.write('Отправитель: %s' % settings.DEFAULT_FROM_EMAIL)
        self.stdout.write('«Ответить»: %s' % (settings.MAIL_REPLY_TO or '(не задано)'))
        self.stdout.write('MAIL_ENABLED: %s (на эту команду не влияет)'
                          % ('1' if settings.MAIL_ENABLED else '0'))

        # Причина отказа пишется в журнал `problems.mail`; на время команды
        # выводим его сюда же, иначе на сервере её пришлось бы искать.
        handler = logging.StreamHandler(sys.stderr)
        log = logging.getLogger('problems.mail')
        log.addHandler(handler)
        try:
            ok = mail.send_templated(
                to=address, subject='Проверка почты Weconomics', template='test',
                context={'site_env': settings.SITE_ENV,
                         'sent_at': timezone.localtime().strftime('%d.%m.%Y %H:%M:%S')})
        finally:
            log.removeHandler(handler)

        if not ok:
            raise CommandError('Письмо НЕ отправлено. Причина — строкой выше.')
        self.stdout.write(self.style.SUCCESS(
            'Письмо принято сервером отправки. Проверьте ящик (и папку «Спам») и '
            'заголовки DKIM, SPF, DMARC.'))
