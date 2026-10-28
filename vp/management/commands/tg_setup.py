"""Настройка бота стены 2 тура (docs/VP.md, «Выкатка стены — по шагам»).

    manage.py tg_setup --ping                 # достаёт ли сервер до Telegram, за сколько мс
    manage.py tg_setup --check                # бот, канал, бот — администратор канала
    manage.py tg_setup --set-webhook <url>    # вебхук с секретом
    manage.py tg_setup --delete-webhook
    manage.py tg_setup --info                 # getWebhookInfo без секретов

⚠️ НИ ТОКЕН, НИ СЕКРЕТ НЕ ПЕЧАТАЮТСЯ. При ошибке код возврата не 0.
"""
import re
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from vp import telegram

SECRET_RE = re.compile(r'^[A-Za-z0-9_-]{1,256}$')


class Command(BaseCommand):
    help = 'Бот стены ВП: проверка связи, канала и вебхука (без печати секретов).'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--ping', action='store_true')
        group.add_argument('--check', action='store_true')
        group.add_argument('--set-webhook', metavar='URL')
        group.add_argument('--delete-webhook', action='store_true')
        group.add_argument('--info', action='store_true')

    def _call(self, method, **params):
        try:
            return telegram.call(method, **params)
        except telegram.TelegramError as error:
            raise CommandError(f'Telegram: {method} — {error}') from None

    def handle(self, *args, **options):
        out = self.stdout.write
        if options['ping']:
            started = time.monotonic()
            self._call('getMe', timeout=10)
            out('Telegram отвечает за %d мс' % ((time.monotonic() - started) * 1000))
        elif options['check']:
            me = self._call('getMe')
            out('Бот: @%s' % me.get('username', '?'))
            chat = self._call('getChat', chat_id=settings.TELEGRAM_CHANNEL)
            out('Канал: %s (%s)' % (settings.TELEGRAM_CHANNEL, chat.get('type', '?')))
            member = self._call('getChatMember', chat_id=settings.TELEGRAM_CHANNEL,
                                user_id=me['id'])
            status = member.get('status')
            if status != 'administrator':
                raise CommandError(
                    'Бот в канале со статусом «%s», нужен administrator: иначе он не видит '
                    'подписчиков.' % status)
            out('Бот — администратор канала: да')
        elif options['set_webhook']:
            secret = settings.TELEGRAM_WEBHOOK_SECRET
            if not secret or not SECRET_RE.match(secret):
                raise CommandError('TELEGRAM_WEBHOOK_SECRET пуст или не из A-Za-z0-9_- '
                                   '(1–256 символов). Вебхук не установлен.')
            url = options['set_webhook']
            if not url.startswith('https://'):
                raise CommandError('Адрес вебхука — только https://')
            self._call('setWebhook', url=url, secret_token=secret,
                       allowed_updates=['message', 'callback_query'],
                       drop_pending_updates=True)
            out('Вебхук установлен: %s' % url)
        elif options['delete_webhook']:
            self._call('deleteWebhook')
            out('Вебхук снят')
        elif options['info']:
            info = self._call('getWebhookInfo')
            out('Адрес: %s' % (info.get('url') or '(нет)'))
            out('Ждут обработки: %s' % info.get('pending_update_count', 0))
            if info.get('last_error_message'):
                out('Последняя ошибка: %s' % info['last_error_message'])
