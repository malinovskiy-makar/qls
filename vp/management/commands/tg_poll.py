"""Бот стены без вебхука: длинный опрос `getUpdates` (боевая служба `tgbot`, docs/VP.md).

    manage.py tg_poll [--timeout 50] [--force] [--alive-file /tmp/tg_poll_alive]

Каждое обновление уходит в `vp.bot.handle_once` – тот же отсев повторов и тот же
разбор, что у вебхука. Служба рассчитана на недели работы без присмотра:

- обрыв связи или 5xx: пауза 5 с, удваивается до 60 с, после удачного ответа сбрасывается;
- 409 (установлен вебхук или опрос идёт ещё где-то) и 401 (токен отозван): понятная
  строка в лог и выход с кодом 1 – ждать тут нечего;
- повтор `update_id` (после перезапуска Telegram отдаёт неподтверждённое заново) отсекает
  `handle_once`; сбой одного обновления в лог и дальше;
- после каждого ответа Telegram обновляется время файла `--alive-file`: по нему
  `healthcheck` в `docker compose` понимает, что служба жива;
- SIGTERM (остановка контейнера) и Ctrl+C: чистый выход с кодом 0.

⚠️ В ЛОГ НЕ ПОПАДАЕТ НИ ТОКЕН, НИ ТЕЛО ОБНОВЛЕНИЯ: только имя бота, класс ошибки, пауза,
`update_id` и тип обновления.

⚠️ ЭКЗЕМПЛЯР ОДИН. Второй опрос получит от Telegram 409 и остановится; вдвоём они
отнимали бы друг у друга обновления.

⚠️ `--force` СНИМАЕТ ВЕБХУК. Только для бота разработки: у боевого бота это снимет
вебхук на сервере, и стена на сайте перестанет получать «Старт» (docs/VP.md).
"""
import argparse
import logging
import os
import signal
import threading
import time

from django.core.management.base import BaseCommand, CommandError

from vp import bot, telegram

logger = logging.getLogger('vp.bot')

#: Пауза после сбоя сети: 5, 10, 20, 40, потом 60 с.
PAUSE_START = 5
PAUSE_MAX = 60
#: Куда писать признак жизни (сверяет `healthcheck` службы `tgbot`).
ALIVE_FILE = '/tmp/tg_poll_alive'  # nosec B108 — файл-метка внутри контейнера, не данные

#: Подменяется в тестах: настоящие паузы там не нужны.
sleep = time.sleep


class _Stop(BaseException):
    """Прервать ожидание сети по SIGTERM. BaseException – чтобы не поймал `except Exception`."""


class Command(BaseCommand):
    help = 'Бот стены ВП длинным опросом (боевая служба tgbot). SIGTERM / Ctrl+C – выход.'

    def add_arguments(self, parser):
        parser.add_argument('--timeout', type=int, default=50,
                            help='длинный опрос Telegram, секунд (HTTP-таймаут – на 10 больше)')
        parser.add_argument('--force', action='store_true',
                            help='снять вебхук (ТОЛЬКО бот разработки)')
        parser.add_argument('--alive-file', default=ALIVE_FILE,
                            help='файл, у которого после каждого ответа Telegram обновляется время')
        # Только для тестов: сколько ответов getUpdates обработать и выйти.
        parser.add_argument('--max-loops', type=int, default=0, help=argparse.SUPPRESS)

    # ------------------------------------------------------------------ служебное

    def _alive(self):
        try:
            with open(self.alive_file, 'a'):
                os.utime(self.alive_file, None)
        except OSError:
            pass  # метка жизни – не повод ронять бота

    def _on_term(self, signum, frame):
        self.stopping = True
        if self.waiting:
            raise _Stop

    def _request(self, method, **params):
        """Вызов Telegram, который переживает обрывы связи (пауза с удвоением).

        Не возвращается без ответа, если не пришёл SIGTERM (тогда `_Stop`). Отказ, у которого
        повтор ничего не изменит (409, 401, неверная настройка), – `CommandError`.
        """
        http_timeout = params.pop('http_timeout', 8)
        while True:
            if self.stopping:
                raise _Stop
            self.waiting = True
            try:
                result = telegram.call(method, http_timeout=http_timeout, **params)
            except telegram.TelegramError as error:
                self._fatal_or_pause(error)
                continue
            finally:
                self.waiting = False
            self.pause = PAUSE_START
            self._alive()
            return result

    def _fatal_or_pause(self, error):
        if error.kind == 'config':
            raise CommandError('Telegram: неверная настройка (%s). Опрос остановлен.'
                               % error.description) from None
        if error.kind == 'api' and error.code == 409:
            raise CommandError(
                'Telegram: 409 Conflict – у бота установлен вебхук или опрос уже идёт в '
                'другом месте. Опрос остановлен. Вебхук снимает «tg_setup --delete-webhook»; '
                'опрос должен быть ровно один.') from None
        if error.kind == 'api' and error.code == 401:
            raise CommandError('Telegram: 401 – токен бота не принят (отозван или с '
                               'ошибкой). Опрос остановлен.') from None
        pause = self.pause
        self.pause = min(self.pause * 2, PAUSE_MAX)
        logger.warning('Telegram: %s%s, пауза %d с', error.kind,
                       ' %s' % error.code if error.code else '', pause)
        self.waiting = True
        try:
            sleep(pause)
        finally:
            self.waiting = False

    # ------------------------------------------------------------------ запуск

    def handle(self, *args, **options):
        self.alive_file = options['alive_file']
        self.pause = PAUSE_START
        self.stopping = False
        self.waiting = False
        timeout = options['timeout']
        max_loops = options['max_loops']
        previous = None
        if threading.current_thread() is threading.main_thread():
            previous = signal.signal(signal.SIGTERM, self._on_term)
        try:
            self._run(timeout, options['force'], max_loops)
        except (_Stop, KeyboardInterrupt):
            pass
        finally:
            if previous is not None:
                signal.signal(signal.SIGTERM, previous)
        logger.info('Опрос остановлен.')

    def _run(self, timeout, force, max_loops):
        me = self._request('getMe') or {}
        logger.info('Опрос запущен, бот @%s', me.get('username', '?'))
        info = self._request('getWebhookInfo') or {}
        if info.get('url'):
            if not force:
                raise CommandError(
                    'У бота установлен вебхук – опрос невозможен. Боевой: «tg_setup '
                    '--delete-webhook». Для БОТА РАЗРАБОТКИ: --force снимет вебхук сам.')
            self._request('deleteWebhook')
            logger.info('Вебхук снят (--force).')
        offset = None
        loops = 0
        while not self.stopping:
            params = {'timeout': timeout, 'allowed_updates': ['message', 'callback_query'],
                      'http_timeout': timeout + 10}
            if offset is not None:
                params['offset'] = offset
            updates = self._request('getUpdates', **params)
            for update in updates or []:
                offset = update['update_id'] + 1
                try:
                    bot.handle_once(update)
                except Exception as error:  # noqa: BLE001 — опрос не должен умереть от одного обновления
                    logger.warning('Бот: обновление %s (%s) – %s', update.get('update_id'),
                                   bot.update_kind(update), type(error).__name__)
                if self.stopping:
                    break
            loops += 1
            if max_loops and loops >= max_loops:
                break
