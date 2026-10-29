"""Бот стены ходит в Telegram через обратный SSH-туннель (docs/VP.md, deploy/tg_relay/README.md).

На боевом хосте адрес 172.17.0.1:18443 – сквозной TLS до api.telegram.org. Контейнер видит его так:
`extra_hosts: api.telegram.org:host-gateway` + `TELEGRAM_API_BASE=https://api.telegram.org:18443`.
Имя остаётся настоящим, поэтому сертификат и SNI совпадают, а порт в базе обязан дожить до адреса запроса.

Сеть подменена: `urllib.request.urlopen` перехватывает запрос и отдаёт заготовленный ответ.
"""
import json
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from django.test import SimpleTestCase, override_settings

from vp import telegram

TOKEN = '123456:SECRET-bot-token-xyz'
BASE = 'https://api.telegram.org:18443'

TUNNEL = override_settings(TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_API_BASE=BASE)


def _response(result):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {'ok': True, 'result': result}).encode('utf-8')
    return response


class PortInBaseTests(SimpleTestCase):
    def sent(self, method, **params):
        """Запрос, который `telegram.call` отдал бы в сеть."""
        with mock.patch('urllib.request.urlopen', return_value=_response({'id': 1})) as urlopen:
            telegram.call(method, **params)
        return urlopen.call_args.args[0]

    @TUNNEL
    def test_get_me_url_keeps_name_and_port(self):
        request = self.sent('getMe')
        self.assertEqual(request.full_url, f'{BASE}/bot{TOKEN}/getMe')
        parts = urlsplit(request.full_url)
        self.assertEqual((parts.hostname, parts.port), ('api.telegram.org', 18443))

    @TUNNEL
    def test_get_updates_url_and_body(self):
        request = self.sent('getUpdates', offset=7, timeout=50)
        self.assertEqual(request.full_url, f'{BASE}/bot{TOKEN}/getUpdates')
        self.assertEqual(json.loads(request.data), {'offset': 7, 'timeout': 50})

    @override_settings(TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_API_BASE=BASE + '/')
    def test_trailing_slash_does_not_double_up(self):
        self.assertEqual(self.sent('getMe').full_url, f'{BASE}/bot{TOKEN}/getMe')

    @TUNNEL
    def test_http_scheme_is_still_refused_with_a_port(self):
        with override_settings(TELEGRAM_API_BASE='http://api.telegram.org:18443'):
            with mock.patch('urllib.request.urlopen', side_effect=AssertionError('сеть')):
                with self.assertRaises(telegram.TelegramError) as raised:
                    telegram.call('getMe')
        self.assertEqual(raised.exception.kind, 'config')

    @TUNNEL
    def test_port_base_is_not_a_config_error(self):
        with mock.patch('urllib.request.urlopen', return_value=_response({'id': 1})):
            self.assertEqual(telegram.call('getMe'), {'id': 1})


class ComposeResolvesTelegramToHostTests(SimpleTestCase):
    """Каждая служба, что ходит в Telegram, видит api.telegram.org как шлюз хоста."""

    ROOT = Path(__file__).resolve().parents[2]
    CALLERS = ('web', 'tgbot')

    def services(self):
        import yaml
        compose = yaml.safe_load((self.ROOT / 'deploy/docker-compose.yml').read_text('utf-8'))
        return compose['services']

    def test_callers_map_the_name_to_host_gateway(self):
        services = self.services()
        for name in self.CALLERS:
            self.assertIn('api.telegram.org:host-gateway', services[name].get('extra_hosts', []),
                          f'у службы {name} нет api.telegram.org → host-gateway')

    def test_the_name_is_never_pinned_to_a_literal_ip(self):
        # Адрес шлюза даёт docker сам (172.17.0.1 на боевом); зашитый IP сломался бы при смене сети.
        for name, service in self.services().items():
            for entry in service.get('extra_hosts', []):
                if entry.startswith('api.telegram.org:'):
                    self.assertEqual(entry, 'api.telegram.org:host-gateway', name)
