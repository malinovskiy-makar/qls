# -*- coding: utf-8 -*-
"""Вход через сервисы, раунд 3 (29.10.2026): всё, что мешало живому входу.

- понятные ошибки на возврате (`error=` сервиса, сбой обмена, нет данных) —
  наша страница с одной фразой и «Попробовать снова» / «Войти по почте», а в
  журнал — только сервис, шаг и код ошибки;
- адрес возврата за nginx — `https://`, и при `SOCIAL_REDIRECT_BASE` — от него;
- VK ID на своём компьютере — только `http://localhost` (порт 80);
- `manage.py social_check` — сеть подменена целиком.
"""
import io
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.core.management import call_command
from django.test import TestCase, override_settings

from problems.management.commands import social_check
from problems.models import SocialAccount, User
from problems.social import providers
from problems.tests.test_production_settings import _production_module
from problems.tests.test_social_login import (
    SOCIAL_ON, TOKEN, VK_KEY, YA_KEY, FakeNetwork, SocialBase)


def redirect_uri_of(response):
    return parse_qs(urlsplit(response['Location']).query)['redirect_uri'][0]


class ReturnErrorTests(SocialBase):
    """Каждый отказ сервиса — наша страница, а не 500 и не чужая ошибка."""

    def returned(self, provider='yandex', **params):
        _location, query = self.start(provider, '/vp/x/')
        params.setdefault('state', query['state'][0])
        with self.assertLogs('problems.social.views', 'WARNING') as logs:
            response = self.client.get('/auth/%s/callback/' % provider, params)
        return response, '\n'.join(logs.output)

    def assert_page(self, response, text, provider='yandex'):
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, text, status_code=400)
        self.assertContains(response, 'Попробовать снова', status_code=400)
        self.assertContains(response, 'href="/auth/%s/start/?next=%%2Fvp%%2Fx%%2F"' % provider,
                            status_code=400)
        self.assertContains(response, 'Войти по почте', status_code=400)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_access_denied(self):
        response, log = self.returned(error='access_denied',
                                      error_description='User denied access')
        self.assert_page(response, 'Вход через Яндекс ID отменён')
        self.assertIn('шаг authorize, код access_denied', log)

    def test_invalid_request(self):
        response, log = self.returned('vk', error='invalid_request')
        self.assert_page(response, 'VK ID не принял запрос сайта', provider='vk')
        self.assertIn('код invalid_request', log)

    def test_access_denied_without_state_is_still_our_page(self):
        response, _log = self.returned(error='access_denied', state='')
        self.assert_page(response, 'Вход через Яндекс ID отменён')

    def test_unknown_error_code_is_not_copied_into_the_log(self):
        response, log = self.returned(error='<script>evil</script>')
        self.assert_page(response, 'Яндекс ID отказал во входе')
        self.assertIn('код other', log)
        self.assertNotIn('evil', log)

    def test_exchange_failure(self):
        _location, query = self.start('yandex', '/vp/x/')
        with mock.patch.object(providers, '_request', FakeNetwork(fail=True)), \
                self.assertLogs('problems.social.views', 'WARNING') as logs:
            response = self.client.get('/auth/yandex/callback/', {
                'code': 'secret-auth-code', 'state': query['state'][0]})
        self.assert_page(response, 'Яндекс ID не ответил')
        log = '\n'.join(logs.output)
        self.assertIn('шаг exchange', log)
        for secret in ('secret-auth-code', query['state'][0], TOKEN):
            self.assertNotIn(secret, log)

    def test_service_gave_no_account_data(self):
        def no_token(url, *, data=None, headers=None):
            return {'error': 'nope'}
        _location, query = self.start('vk', '/vp/x/')
        with mock.patch.object(providers, '_request', no_token), \
                self.assertLogs('problems.social.views', 'WARNING') as logs:
            response = self.client.get('/auth/vk/callback/', {
                'code': 'c', 'device_id': 'd', 'state': query['state'][0]})
        self.assert_page(response, 'VK ID не передал данные аккаунта', provider='vk')
        self.assertIn('шаг data', '\n'.join(logs.output))

    @override_settings(MAIL_ENABLED=False)
    def test_without_mail_the_fallback_is_login_by_username(self):
        response, _log = self.returned(error='access_denied')
        self.assertContains(response, 'Войти по логину', status_code=400)


@override_settings(**SOCIAL_ON)
class RedirectUriTests(TestCase):
    """Адрес возврата обязан совпасть с кабинетом сервиса буква в букву."""

    def test_behind_nginx_with_production_settings_it_is_https(self):
        with _production_module() as production:
            proxy_header = production.SECURE_PROXY_SSL_HEADER
        with self.settings(SECURE_PROXY_SSL_HEADER=proxy_header,
                           ALLOWED_HOSTS=['weconomics.ai']):
            response = self.client.get('/auth/yandex/start/', HTTP_HOST='weconomics.ai',
                                       HTTP_X_FORWARDED_PROTO='https')
        self.assertTrue(redirect_uri_of(response).startswith('https://weconomics.ai/auth/'),
                        redirect_uri_of(response))

    @override_settings(SOCIAL_REDIRECT_BASE='https://weconomics.ai',
                       ALLOWED_HOSTS=['weconomics.ai', 'weconomics.site'],
                       SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_base_is_used_and_the_other_name_is_sent_there_first(self):
        # С weconomics.site — сначала на то же начало входа на weconomics.ai:
        # иначе `state` остался бы в сессии другого имени.
        response = self.client.get('/auth/vk/start/?next=/vp/x/', HTTP_HOST='weconomics.site',
                                   HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response['Location'], 'https://weconomics.ai/auth/vk/start/?next=/vp/x/')
        self.assertNotIn('social_flow', self.client.session)
        response = self.client.get('/auth/vk/start/?next=/vp/x/', HTTP_HOST='weconomics.ai',
                                   HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(urlsplit(response['Location']).netloc, 'id.vk.ru')
        self.assertEqual(redirect_uri_of(response), 'https://weconomics.ai/auth/vk/callback/')

    @override_settings(SOCIAL_REDIRECT_BASE='https://weconomics.ai',
                       ALLOWED_HOSTS=['weconomics.ai'],
                       SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_exchange_sends_the_same_redirect_uri(self):
        response = self.client.get('/auth/vk/start/', HTTP_HOST='weconomics.ai',
                                   HTTP_X_FORWARDED_PROTO='https')
        state = parse_qs(urlsplit(response['Location']).query)['state'][0]
        network = FakeNetwork()
        with mock.patch.object(providers, '_request', network):
            self.client.get('/auth/vk/callback/', {'code': 'c', 'device_id': 'd',
                                                   'state': state},
                            HTTP_HOST='weconomics.ai', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(network.calls[0][1]['redirect_uri'],
                         'https://weconomics.ai/auth/vk/callback/')


@override_settings(**SOCIAL_ON)
class VkLocalhostTests(TestCase):
    """VK ID пускает обратно только на http://localhost — иначе чужая ошибка VK."""

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['127.0.0.1', 'localhost'])
    def test_vk_on_127_is_our_hint_page(self):
        for host in ('127.0.0.1:8010', 'localhost:8010', '127.0.0.1'):
            response = self.client.get('/auth/vk/start/', HTTP_HOST=host)
            self.assertContains(response, 'Для проверки VK ID откройте http://localhost/login/',
                                status_code=400)
            self.assertContains(response, 'href="http://localhost/login/"', status_code=400)
            self.assertNotIn('social_flow', self.client.session)

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['127.0.0.1', 'localhost'])
    def test_vk_on_localhost_and_yandex_anywhere_go_to_the_service(self):
        response = self.client.get('/auth/vk/start/', HTTP_HOST='localhost')
        self.assertEqual(urlsplit(response['Location']).netloc, 'id.vk.ru')
        self.assertEqual(redirect_uri_of(response), 'http://localhost/auth/vk/callback/')
        response = self.client.get('/auth/yandex/start/', HTTP_HOST='127.0.0.1:8010')
        self.assertEqual(urlsplit(response['Location']).netloc, 'oauth.yandex.ru')

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['127.0.0.1'])
    def test_hint_only_in_debug(self):
        response = self.client.get('/auth/vk/start/', HTTP_HOST='127.0.0.1')
        self.assertEqual(urlsplit(response['Location']).netloc, 'id.vk.ru')


def fake_net(authorize, token=(400, '', '{"error": "invalid_grant"}'), fail=()):
    """Подмена `social_check.fetch`: страница авторизации по сервису и ответ обмена."""
    calls = []

    def fetch(url, data=None, attempts=2):
        calls.append((url, data))
        host = urlsplit(url).netloc
        if host in fail:
            raise OSError('нет связи')
        if data is not None:
            return token
        return authorize[host]
    return fetch, calls


YA_OK = (200, 'https://passport.yandex.ru/auth?retpath=x', '<html>Войти</html>')
VK_OK = (200, 'https://id.vk.ru/authorize?x', '<html>"app_name":"Weconomics"</html>')


@override_settings(**SOCIAL_ON)
class SocialCheckCommandTests(TestCase):
    def run_check(self, authorize, base='http://localhost', **kwargs):
        fetch, calls = fake_net(authorize, **kwargs)
        out = io.StringIO()
        with mock.patch.object(social_check, 'fetch', fetch):
            call_command('social_check', '--base', base, stdout=out)
        return out.getvalue(), calls

    def test_both_ready_and_no_key_is_printed(self):
        out, calls = self.run_check({'oauth.yandex.ru': YA_OK, 'id.vk.ru': VK_OK})
        self.assertIn('Яндекс: готов', out)
        self.assertIn('VK: готов', out)
        self.assertIn('адрес возврата: http://localhost/auth/vk/callback/', out)
        self.assertIn('конечный хост passport.yandex.ru', out)
        self.assertIn('задан (длина 32), похож на настоящий', out)
        for key in (VK_KEY, YA_KEY, 'ya-secret'):
            self.assertNotIn(key, out)
        # Параметры как у настоящей кнопки.
        query = parse_qs(urlsplit(calls[0][0]).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['redirect_uri'], ['http://localhost/auth/yandex/callback/'])

    def test_unknown_yandex_app(self):
        out, _calls = self.run_check({'oauth.yandex.ru': YA_OK, 'id.vk.ru': VK_OK},
                                     token=(400, '', '{"error": "invalid_client"}'))
        self.assertIn('Яндекс: Яндекс не знает приложение с этим ClientID', out)

    def test_vk_wrong_redirect_uri_and_deleted_app(self):
        page = (200, 'https://id.vk.ru/authorize', '"error":{"message":"redirect_uri is missing'
                ' or invalid","code":"invalid_request","additional_data":[]}')
        out, _calls = self.run_check({'oauth.yandex.ru': YA_OK, 'id.vk.ru': page})
        self.assertIn('VK: адрес возврата не прописан в кабинете сервиса', out)
        out, _calls = self.run_check({'oauth.yandex.ru': YA_OK,
                                      'id.vk.ru': (200, 'https://id.vk.ru/x', 'app is deleted')})
        self.assertIn('приложения с таким номером нет или оно удалено', out)

    def test_vk_on_127_is_explained(self):
        out, _calls = self.run_check({'oauth.yandex.ru': YA_OK, 'id.vk.ru': VK_OK},
                                     base='http://127.0.0.1:8010')
        self.assertIn('VK: VK ID на своём компьютере принимает только http://localhost', out)

    def test_network_failure_is_one_plain_line(self):
        out, _calls = self.run_check({'oauth.yandex.ru': YA_OK}, fail=('id.vk.ru',))
        self.assertIn('VK: не удалось связаться с сервисом (OSError)', out)

    @override_settings(SOCIAL_REDIRECT_BASE='https://weconomics.ai')
    def test_default_base_is_the_setting(self):
        fetch, _calls = fake_net({'oauth.yandex.ru': YA_OK, 'id.vk.ru': VK_OK})
        out = io.StringIO()
        with mock.patch.object(social_check, 'fetch', fetch):
            call_command('social_check', stdout=out)
        self.assertIn('адрес возврата: https://weconomics.ai/auth/yandex/callback/', out.getvalue())

    @override_settings(VK_ID_CLIENT_ID='demo')
    def test_placeholder_key_is_reported_without_network(self):
        out, calls = self.run_check({'oauth.yandex.ru': YA_OK})
        self.assertIn('VK: ключ не похож на настоящий', out)
        self.assertFalse(any('id.vk.ru' in url for url, _data in calls))
