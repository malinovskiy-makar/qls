"""Бот стены без вебхука: длинный опрос `getUpdates` (на маке Telegram вебхук не пришлёт).

    manage.py tg_poll [--timeout 25] [--force]

Каждое обновление уходит в тот же `vp.bot.handle`, что и у вебхука.

⚠️ `--force` СНИМАЕТ ВЕБХУК. Только для бота разработки: у боевого бота это снимет
вебхук на сервере, и стена на сайте перестанет получать «Старт» (docs/VP.md).
"""
import logging

from django.core.management.base import BaseCommand, CommandError

from vp import bot, telegram

logger = logging.getLogger('vp.bot')


class Command(BaseCommand):
    help = 'Бот стены ВП длинным опросом (разработка). Ctrl+C — выход.'

    def add_arguments(self, parser):
        parser.add_argument('--timeout', type=int, default=25)
        parser.add_argument('--force', action='store_true',
                            help='снять вебхук (ТОЛЬКО бот разработки)')

    def _call(self, method, **params):
        try:
            return telegram.call(method, **params)
        except telegram.TelegramError as error:
            raise CommandError(f'Telegram: {method} — {error}') from None

    def handle(self, *args, **options):
        info = self._call('getWebhookInfo')
        if info.get('url'):
            if not options['force']:
                raise CommandError(
                    'У бота установлен вебхук — опрос невозможен. Для БОТА РАЗРАБОТКИ: '
                    '--force снимет вебхук. Боевому боту --force не давать.')
            self._call('deleteWebhook')
            self.stdout.write('Вебхук снят (--force).')
        timeout = options['timeout']
        offset = None
        self.stdout.write('Слушаю Telegram. Ctrl+C — выход.')
        try:
            while True:
                params = {'timeout': timeout, 'allowed_updates': ['message', 'callback_query']}
                if offset is not None:
                    params['offset'] = offset
                try:
                    updates = telegram.call('getUpdates', timeout=timeout + 5, **params)
                except telegram.TelegramError as error:
                    self.stderr.write('Telegram: %s' % error.kind)
                    continue
                for update in updates or []:
                    offset = update['update_id'] + 1
                    try:
                        bot.handle(update)
                    except Exception as error:  # noqa: BLE001 — один сбой не роняет опрос
                        logger.warning('Бот: обновление %s (%s) — %s', update.get('update_id'),
                                       bot.update_kind(update), type(error).__name__)
        except KeyboardInterrupt:
            self.stdout.write('Остановлено.')
