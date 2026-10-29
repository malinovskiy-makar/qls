"""`manage.py tg_poll` как боевая служба (docs/VP.md, «Бот: вебхук и длинный опрос», S2b).

Telegram подменён: `vp.telegram.call` – сценарием, а `urllib.request.urlopen` бросает
AssertionError – настоящая сеть в тестах падает. Паузы подменены записью в список.

⚠️ Служба живёт неделями, поэтому проверяется то, что бывает только в долгой жизни:
обрыв связи (пауза растёт и не превращается в шквал запросов), 409, повтор одного и того
же обновления между опросом и вебхуком, сбой одного обновления, SIGTERM, и что в логе нет
ни токена, ни текста людей.
"""
import json
import os
import signal
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from vp import bot, telegram

TOKEN = '123456:SECRET-bot-token-xyz'
SECRET = 'hook-secret_0123'
BODY = 'ПРИВАТНЫЙ-ТЕКСТ-ЧЕЛОВЕКА'

POLL_SETTINGS = override_settings(
    VP_WALL_ENABLED=True, VP_WALL_TG_ENABLED=True,
    TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_BOT_USERNAME='poll_bot',
    TELEGRAM_WEBHOOK_SECRET=SECRET, TELEGRAM_CHANNEL='@weconomics_ru',
    TELEGRAM_API_BASE='https://api.telegram.org')

NET = telegram.TelegramError('network', 'URLError')


def message(update_id, text=BODY):
    return {'update_id': update_id, 'message': {
        'text': text, 'chat': {'id': 5, 'type': 'private'}, 'from': {'id': 5}}}


class Scripted:
    """Подмена `vp.telegram.call`: на `getUpdates` отвечает по очереди заготовками.

    Заготовка – список обновлений или исключение. Когда очередь кончилась – вызывается
    `after` (по умолчанию пустой ответ). Остальные методы отвечают по умолчанию.
    """

    def __init__(self, updates=(), me=None, webhook_url='', start_errors=()):
        self.queue = list(updates)
        self.calls = []
        self.me = me or {'username': 'poll_bot'}
        self.webhook_url = webhook_url
        self.start_errors = list(start_errors)
        self.after = lambda: []

    def __call__(self, method, *, http_timeout=8, **params):
        self.calls.append((method, http_timeout, params))
        if method == 'getMe':
            if self.start_errors:
                raise self.start_errors.pop(0)
            return self.me
        if method == 'getWebhookInfo':
            return {'url': self.webhook_url}
        if method == 'getUpdates':
            item = self.queue.pop(0) if self.queue else self.after()
            if isinstance(item, BaseException):
                raise item
            return item
        return {}

    def of(self, method):
        return [(t, p) for m, t, p in self.calls if m == method]


class PollCase(TestCase):
    """Общая обвязка: сеть запрещена, кэш чист, паузы и `bot.handle` записываются."""

    def setUp(self):
        cache.clear()
        patch = mock.patch('urllib.request.urlopen',
                           side_effect=AssertionError('настоящая сеть в тестах'))
        patch.start()
        self.addCleanup(patch.stop)
        self.pauses = []
        patch = mock.patch('vp.management.commands.tg_poll.sleep', self.pauses.append)
        patch.start()
        self.addCleanup(patch.stop)
        self.handled = []
        patch = mock.patch('vp.bot.handle', self.handled.append)
        patch.start()
        self.addCleanup(patch.stop)
        self.alive = os.path.join(tempfile.mkdtemp(), 'alive')

    def poll(self, script, *args, loops=None):
        """Один запуск `tg_poll` со сценарием; `loops` – сколько ответов `getUpdates` взять."""
        extra = ['--max-loops', str(loops if loops is not None else len(script.queue) or 1),
                 '--alive-file', self.alive]
        with mock.patch('vp.telegram.call', script):
            call_command('tg_poll', *extra, *args)

    def hook(self, update):
        return Client().post(reverse('vp:tg_hook'), json.dumps(update),
                             content_type='application/json',
                             HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=SECRET)


@POLL_SETTINGS
class PollLoopTests(PollCase):
    def test_two_updates_are_handled_and_offset_moves(self):
        script = Scripted([[message(10), message(11)], []])
        self.poll(script)
        self.assertEqual([u['update_id'] for u in self.handled], [10, 11])
        offsets = [p.get('offset') for _, p in script.of('getUpdates')]
        self.assertEqual(offsets, [None, 12])

    def test_request_shape_long_poll(self):
        script = Scripted([[]])
        self.poll(script)
        (http_timeout, params), = script.of('getUpdates')
        self.assertEqual(params['timeout'], 50)
        self.assertEqual(http_timeout, 60)
        self.assertEqual(params['allowed_updates'], ['message', 'callback_query'])

    def test_alive_file_is_touched_after_telegram_answers(self):
        Path(self.alive).write_text('')
        os.utime(self.alive, (1, 1))
        self.poll(Scripted([[]]))
        self.assertGreater(os.path.getmtime(self.alive), time.time() - 60)

    def test_startup_logs_bot_name_without_secrets(self):
        with self.assertLogs('vp.bot', level='INFO') as logs:
            self.poll(Scripted([[]], me={'username': 'weconomics_dev_bot'}))
        self.assertIn('Опрос запущен, бот @weconomics_dev_bot', '\n'.join(logs.output))


@POLL_SETTINGS
class PollNetworkTests(PollCase):
    def test_pause_doubles_and_resets_after_success(self):
        script = Scripted([NET, NET, NET, [], NET, []])
        self.poll(script, loops=2)
        self.assertEqual(self.pauses, [5, 10, 20, 5])

    def test_pause_is_capped_at_a_minute(self):
        script = Scripted([NET] * 8 + [[]])
        self.poll(script, loops=1)
        self.assertEqual(self.pauses, [5, 10, 20, 40, 60, 60, 60, 60])

    def test_5xx_is_a_network_error_not_a_crash(self):
        down = telegram.TelegramError('network', 'HTTP 502', 502)
        self.poll(Scripted([down, []]), loops=1)
        self.assertEqual(self.pauses, [5])

    def test_no_network_at_startup_waits_instead_of_dying(self):
        script = Scripted([[]], start_errors=[NET, NET])
        self.poll(script)
        self.assertEqual(self.pauses, [5, 10])
        self.assertEqual(len(script.of('getUpdates')), 1)

    def test_one_log_line_per_error_with_class_and_pause(self):
        with self.assertLogs('vp.bot', level='INFO') as logs:
            self.poll(Scripted([NET, NET, []]), loops=1)
        lines = [line for line in logs.output if 'пауза' in line]
        self.assertEqual(len(lines), 2)
        self.assertIn('network, пауза 5 с', lines[0])
        self.assertIn('network, пауза 10 с', lines[1])


@POLL_SETTINGS
class PollFatalTests(PollCase):
    def test_409_stops_with_a_clear_message(self):
        conflict = telegram.TelegramError(
            'api', 'Conflict: terminated by other getUpdates request', 409)
        script = Scripted([conflict, [message(1)]])
        with self.assertRaises(CommandError) as raised:
            self.poll(script)
        self.assertIn('409', str(raised.exception))
        self.assertEqual(len(script.of('getUpdates')), 1)
        self.assertEqual(self.pauses, [])
        self.assertEqual(self.handled, [])

    def test_exit_code_of_409_is_not_zero(self):
        # CommandError – единственный способ Django выйти из команды с кодом не 0
        # (`run_from_argv` превращает его в `sys.exit(returncode)`).
        conflict = telegram.TelegramError('api', 'Conflict', 409)
        with self.assertRaises(CommandError) as raised:
            self.poll(Scripted([conflict]))
        self.assertNotEqual(raised.exception.returncode, 0)

    def test_revoked_token_stops_too(self):
        revoked = telegram.TelegramError('api', 'Unauthorized', 401)
        with self.assertRaises(CommandError):
            self.poll(Scripted([revoked]))
        self.assertEqual(self.pauses, [])

    def test_wrong_config_stops(self):
        script = Scripted([[]], start_errors=[telegram.TelegramError('config', 'нет токена')])
        with self.assertRaises(CommandError):
            self.poll(script)

    def test_webhook_blocks_polling_without_force(self):
        script = Scripted([[]], webhook_url='https://example.test/hook')
        with self.assertRaises(CommandError):
            self.poll(script)
        self.assertEqual(script.of('deleteWebhook'), [])
        self.assertEqual(script.of('getUpdates'), [])

    def test_force_removes_the_webhook(self):
        script = Scripted([[]], webhook_url='https://example.test/hook')
        self.poll(script, '--force')
        self.assertEqual(len(script.of('deleteWebhook')), 1)


@POLL_SETTINGS
class PollOnceTests(PollCase):
    def test_same_update_via_poll_and_hook_is_handled_once(self):
        self.poll(Scripted([[message(50)]]))
        self.assertEqual(self.hook(message(50)).status_code, 200)
        self.assertEqual([u['update_id'] for u in self.handled], [50])

    def test_same_update_via_hook_then_poll_is_handled_once(self):
        self.hook(message(51))
        self.poll(Scripted([[message(51), message(52)]]))
        self.assertEqual([u['update_id'] for u in self.handled], [51, 52])

    def test_repeat_inside_one_batch_and_across_restarts(self):
        self.poll(Scripted([[message(60), message(60)]]))
        self.poll(Scripted([[message(60)]]))  # перезапуск службы: Telegram отдал заново
        self.assertEqual([u['update_id'] for u in self.handled], [60])

    def test_handle_once_answers_true_then_false(self):
        self.assertTrue(bot.handle_once(message(70)))
        self.assertFalse(bot.handle_once(message(70)))

    def test_hook_answers_200_when_handling_fails(self):
        with mock.patch('vp.bot.handle', side_effect=ValueError('boom')):
            with self.assertLogs('vp.bot', level='WARNING') as logs:
                response = self.hook(message(75))
        self.assertEqual(response.status_code, 200)
        self.assertIn('обновление 75 (message) – ValueError', '\n'.join(logs.output))

    def test_one_failure_does_not_stop_the_next_update(self):
        def flaky(update):
            self.handled.append(update)
            if update['update_id'] == 80:
                raise ValueError('boom ' + BODY)
        with mock.patch('vp.bot.handle', flaky):
            with self.assertLogs('vp.bot', level='WARNING') as logs:
                self.poll(Scripted([[message(80), message(81)]]))
        self.assertEqual([u['update_id'] for u in self.handled], [80, 81])
        text = '\n'.join(logs.output)
        self.assertIn('обновление 80 (message) – ValueError', text)


@POLL_SETTINGS
class PollLogTests(PollCase):
    def test_log_has_neither_token_nor_people_text(self):
        def flaky(update):
            raise RuntimeError(TOKEN + BODY)
        conflict_text = telegram.TelegramError('network', 'URLError')
        with mock.patch('vp.bot.handle', flaky):
            with self.assertLogs('vp.bot', level='DEBUG') as logs:
                self.poll(Scripted([conflict_text, [message(90, text=BODY)], []]), loops=2)
        everything = '\n'.join(logs.output)
        self.assertNotIn(TOKEN, everything)
        self.assertNotIn('SECRET-bot-token', everything)
        self.assertNotIn(BODY, everything)
        self.assertIn('90', everything)


@POLL_SETTINGS
class PollSignalTests(PollCase):
    def test_sigterm_while_waiting_for_telegram_exits_cleanly(self):
        script = Scripted([[message(100)]])

        def term_then_hang():
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(5)  # до сюда обработчик не даст дойти
            raise AssertionError('SIGTERM не прервал ожидание')
        script.after = term_then_hang
        before = signal.getsignal(signal.SIGTERM)
        self.poll(script, loops=5)  # без исключения – код возврата 0
        self.assertEqual([u['update_id'] for u in self.handled], [100])
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_sigterm_during_handling_finishes_the_update_first(self):
        def term_inside(update):
            self.handled.append(update)
            os.kill(os.getpid(), signal.SIGTERM)
        script = Scripted([[message(110), message(111)]])
        with mock.patch('vp.bot.handle', term_inside):
            self.poll(script, loops=5)
        # Обработка 110 дошла до конца; 111 не тронуто – Telegram отдаст его снова.
        self.assertEqual([u['update_id'] for u in self.handled], [110])
        self.assertEqual(len(script.of('getUpdates')), 1)


class DedupeIsOneSpotTests(SimpleTestCase):
    def test_hook_view_has_no_dedupe_of_its_own(self):
        source = Path(__file__).resolve().parents[1].joinpath('views_wall.py').read_text('utf-8')
        self.assertNotIn('vp:tg:update', source)
        self.assertIn('bot.handle_once(', source)


@POLL_SETTINGS
class RealCallShapeTests(SimpleTestCase):
    """Настоящий `telegram.call` (сеть подменена на уровне `urlopen`): прежний `tg_poll`
    падал с TypeError на первом запросе – `timeout` HTTP совпадал с `timeout` Telegram."""

    def test_get_updates_carries_both_timeouts(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true, "result": []}'
        with mock.patch('urllib.request.urlopen', return_value=response) as opened:
            result = telegram.call('getUpdates', http_timeout=60, timeout=50, offset=7)
        self.assertEqual(result, [])
        request = opened.call_args.args[0]
        self.assertEqual(opened.call_args.kwargs['timeout'], 60)
        self.assertEqual(json.loads(request.data), {'timeout': 50, 'offset': 7})

    def test_error_code_is_kept_without_the_token(self):
        body = ('{"ok": false, "error_code": 409, "description": "Conflict: %s"}' % TOKEN).encode()
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = body
        with mock.patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(telegram.TelegramError) as raised:
                telegram.call('getUpdates')
        self.assertEqual(raised.exception.code, 409)
        self.assertNotIn(TOKEN, str(raised.exception))


class TgbotServiceTests(SimpleTestCase):
    """Служба `tgbot` в боевом compose: не стартует сама, без миграций, без портов."""

    ROOT = Path(__file__).resolve().parents[2]

    def service(self):
        import yaml
        compose = yaml.safe_load((self.ROOT / 'deploy/docker-compose.yml').read_text('utf-8'))
        return compose['services']['tgbot']

    def test_service_is_opt_in_and_closed_to_the_outside(self):
        svc = self.service()
        self.assertEqual(svc['profiles'], ['tgbot'])
        self.assertNotIn('ports', svc)
        self.assertEqual(svc['container_name'], 'weco-tgbot')
        self.assertEqual(svc['restart'], 'unless-stopped')
        self.assertEqual(svc['env_file'], ['/srv/weconomics/.env'])
        self.assertEqual(svc['depends_on']['web']['condition'], 'service_healthy')
        self.assertEqual(svc['depends_on']['redis']['condition'], 'service_healthy')

    def test_entrypoint_never_migrates(self):
        svc = self.service()
        self.assertEqual(svc['entrypoint'], ['/app/deploy/entrypoint-tgbot.sh'])
        script = (self.ROOT / 'deploy/entrypoint-tgbot.sh').read_text('utf-8')
        code = [line for line in script.splitlines() if not line.lstrip().startswith('#')]
        joined = '\n'.join(code)
        self.assertNotIn('migrate', joined)
        self.assertNotIn('collectstatic', joined)
        self.assertIn('manage.py tg_poll', joined)

    def test_healthcheck_reads_the_alive_file_that_tg_poll_writes(self):
        from vp.management.commands import tg_poll
        test = ' '.join(self.service()['healthcheck']['test'])
        self.assertIn(tg_poll.ALIVE_FILE, test)


class RelayFilesTests(SimpleTestCase):
    """Пример настройки посредника (deploy/tg_relay): закрыт чужим, без журнала, длинный опрос влезает."""

    RELAY = Path(__file__).resolve().parents[2] / 'deploy' / 'tg_relay'

    def conf(self):
        text = (self.RELAY / 'nginx.conf').read_text('utf-8')
        return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))

    def test_only_our_server_is_let_in(self):
        conf = self.conf()
        self.assertIn('allow __OUR_SERVER_IP__;\n    deny all;', conf)

    def test_no_access_log_anywhere(self):
        conf = self.conf()
        self.assertEqual(conf.count('access_log off;'), 2)
        self.assertNotIn('access_log on', conf)
        for line in conf.splitlines():
            if 'access_log' in line:
                self.assertIn('off', line)
        # Журнал ошибок содержит адрес запроса (токен) – только критичное.
        for line in conf.splitlines():
            if 'error_log' in line:
                self.assertTrue(line.strip().endswith('crit;'), line)

    def test_forwards_to_telegram_and_holds_a_long_poll(self):
        conf = self.conf()
        for needle in ('proxy_pass https://api.telegram.org;', 'proxy_ssl_server_name on;',
                       'proxy_set_header Host api.telegram.org;', 'proxy_read_timeout 90s;',
                       'proxy_send_timeout 90s;'):
            self.assertIn(needle, conf)

    def test_port_80_is_only_for_certbot(self):
        conf = self.conf()
        self.assertIn('location /.well-known/acme-challenge/', conf)
        self.assertIn('return 444;', conf)

    def test_names_are_placeholders_in_one_place_each(self):
        conf = self.conf()
        self.assertNotIn('weconomics', conf.replace('weconomics_', ''))
        self.assertIn('__RELAY_HOST__', conf)
        left = conf.replace('__RELAY_HOST__', '').replace('__OUR_SERVER_IP__', '')
        self.assertNotIn('__', left)

    def test_readme_walks_through_the_agreed_steps(self):
        readme = (self.RELAY / 'README.md').read_text('utf-8')
        # С 29.10.2026 схема – обратный SSH-туннель (nginx.conf оставлен как справка).
        for needle in ('https://api.telegram.org/', 'НЕ ИСПОЛЬЗУЕТСЯ', 'permitlisten="172.17.0.1:18443"',
                       'Match User tgtunnel', 'AllowTcpForwarding remote', 'GatewayPorts clientspecified',
                       'ufw allow from 172.16.0.0/12 to 172.17.0.1 port 18443', 'tg-tunnel',
                       '--resolve api.telegram.org:18443:172.17.0.1', 'host-gateway',
                       'TELEGRAM_API_BASE=https://api.telegram.org:18443', 'LEGAL_TG_RELAY', 'токен'):
            self.assertIn(needle, readme)
        self.assertNotIn('access_log on', readme)
