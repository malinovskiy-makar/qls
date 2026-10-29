# -*- coding: utf-8 -*-
"""Вход через сервисы, раунд 4 (29.10.2026): медленный ответ VK ID.

Живая проверка владельца: две попытки из трёх отвалились ровно через 10 с
(прежний `HTTP_TIMEOUT`), одна прошла за 0,35 с. Здесь:

- точная причина в журнале (`timeout`, `http_400 invalid_grant`, `network_dns`…)
  без кода, токена и `device_id`;
- ожидание — `SOCIAL_HTTP_TIMEOUT` (20 с);
- повтор один и только если запрос не ушёл (сбой соединения), после любого
  HTTP-ответа и после таймаута ожидания ответа — без повтора;
- своя страница «долго не отвечает»;
- второй возврат с тем же `state`, пока первый ждёт сервис, второго обмена не
  делает.

Сеть подменяется на уровне `urllib.request.urlopen` — так проверяется и
разбор сбоев в `providers._send`, а не только подмена `_request`.
"""
import io
import json
import socket
import time
import urllib.error
from unittest import mock

from django.test import override_settings

from problems.models import SocialAccount, User
from problems.social import providers
from problems.tests.test_social_login import TOKEN, SocialBase, vk_user

AUTH_CODE = 'zz_auth_code_marker'
DEVICE = 'zz_device_marker'


class _Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode('utf-8')

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def connect_timeout():
    return urllib.error.URLError(TimeoutError('timed out'))


def http_error(url, status, payload):
    return urllib.error.HTTPError(url, status, 'Bad Request', {},
                                  io.BytesIO(json.dumps(payload).encode('utf-8')))


class FakeVK:
    """Подмена `urlopen`: по очереди отдаёт сбои из `token_failures`, потом
    отвечает как VK ID. Запоминает каждую попытку обмена и её `timeout`."""

    def __init__(self, token_failures=()):
        self.token_failures = list(token_failures)
        self.token_attempts = 0
        self.timeouts = []

    def __call__(self, request, timeout=None):
        self.timeouts.append(timeout)
        url = request.full_url
        if url == providers.VKProvider.TOKEN_URL:
            self.token_attempts += 1
            if self.token_failures:
                failure = self.token_failures.pop(0)
                raise failure(url) if callable(failure) else failure
            return _Response({'access_token': TOKEN})
        if url == providers.VKProvider.USER_INFO_URL:
            return _Response({'user': vk_user()})
        raise AssertionError('неожиданный адрес ' + url)


class SlowServiceTests(SocialBase):
    def returned(self, fake, **extra):
        _location, query = self.start('vk', '/vp/x/')
        params = {'code': AUTH_CODE, 'device_id': DEVICE, 'state': query['state'][0]}
        params.update(extra)
        with mock.patch.object(providers.urllib.request, 'urlopen', fake), \
                self.assertLogs('problems.social', 'INFO') as logs:
            # Удачный вход журнал не пишет, а assertLogs требует хоть одну строку.
            providers.logger.info('начало проверки')
            response = self.client.get('/auth/vk/callback/', params)
        log = '\n'.join(logs.output)
        for secret in (AUTH_CODE, DEVICE, TOKEN, query['state'][0]):
            self.assertNotIn(secret, log)
        return response, log

    def test_timeout_then_success_is_one_retry_and_a_login(self):
        fake = FakeVK([connect_timeout()])
        response, log = self.returned(fake)
        self.assertEqual(fake.token_attempts, 2)
        self.assertRedirects(response, '/auth/finish/', fetch_redirect_response=False)
        self.assertIn('повтор после timeout', log)

    def test_timeout_twice_is_the_slow_page(self):
        fake = FakeVK([connect_timeout(), connect_timeout()])
        response, log = self.returned(fake)
        self.assertEqual(fake.token_attempts, 2)
        self.assertContains(response, 'VK ID долго не отвечает. Попробуйте ещё раз',
                            status_code=400)
        self.assertContains(response, 'Попробовать снова', status_code=400)
        self.assertContains(response, 'Войти по почте', status_code=400)
        self.assertIn('Вход через vk не удался: шаг exchange, причина timeout', log)
        self.assertEqual(User.objects.count(), 0)

    def test_http_400_is_not_repeated_and_the_reason_is_logged(self):
        echo = 'zz_description_echo'
        fake = FakeVK([lambda url: http_error(url, 400, {
            'error': 'invalid_grant', 'error_description': echo})])
        response, log = self.returned(fake)
        self.assertEqual(fake.token_attempts, 1)
        self.assertContains(response, 'VK ID не ответил', status_code=400)
        self.assertIn('шаг exchange, причина http_400 invalid_grant', log)
        self.assertNotIn(echo, log)

    def test_waiting_for_the_answer_timed_out_is_not_repeated(self):
        # Запрос ушёл, ответа нет: код мог быть уже погашен — повтор запрещён.
        fake = FakeVK([TimeoutError('timed out')])
        response, log = self.returned(fake)
        self.assertEqual(fake.token_attempts, 1)
        self.assertContains(response, 'VK ID долго не отвечает', status_code=400)
        self.assertIn('причина timeout_response', log)

    def test_dns_failure_is_repeated_and_named(self):
        dns = urllib.error.URLError(socket.gaierror(11001, 'getaddrinfo failed'))
        fake = FakeVK([dns, urllib.error.URLError(socket.gaierror(11001, 'x'))])
        response, log = self.returned(fake)
        self.assertEqual(fake.token_attempts, 2)
        self.assertContains(response, 'VK ID не ответил', status_code=400)
        self.assertIn('причина network_dns', log)

    def test_garbage_answer_is_bad_response(self):
        class Garbage(_Response):
            def read(self):
                return b'<html>'
        fake = FakeVK()
        fake_call = fake.__call__

        def urlopen(request, timeout=None):
            if request.full_url == providers.VKProvider.TOKEN_URL:
                return Garbage({})
            return fake_call(request, timeout)
        _response, log = self.returned(urlopen)
        self.assertIn('причина bad_response', log)

    def test_default_wait_is_20_seconds(self):
        fake = FakeVK()
        self.returned(fake)
        self.assertEqual(fake.timeouts, [20, 20])

    @override_settings(SOCIAL_HTTP_TIMEOUT=7)
    def test_wait_comes_from_the_setting(self):
        fake = FakeVK()
        self.returned(fake)
        self.assertEqual(fake.timeouts, [7, 7])

    def test_vk_return_address_with_ext_id_and_type_works(self):
        # Адрес возврата VK ID у владельца: …&ext_id=…&type=code_v2. По документации
        # (id.vk.ru, обмен кода) при обмене они не нужны — и не мешают.
        fake = FakeVK()
        response, _log = self.returned(fake, ext_id='zz_ext', type='code_v2')
        self.assertRedirects(response, '/auth/finish/', fetch_redirect_response=False)


class BudgetTests(SocialBase):
    def test_no_attempt_when_the_budget_is_spent(self):
        fake = FakeVK()
        with mock.patch.object(providers.urllib.request, 'urlopen', fake):
            with self.assertRaises(providers.SocialError) as caught:
                providers._request(providers.VKProvider.TOKEN_URL, data={},
                                   deadline=time.monotonic() + 0.5)
        self.assertEqual(caught.exception.reason, 'timeout')
        self.assertEqual(fake.token_attempts, 0)

    def test_attempt_is_cut_to_what_is_left(self):
        fake = FakeVK()
        with mock.patch.object(providers.urllib.request, 'urlopen', fake):
            providers._request(providers.VKProvider.TOKEN_URL, data={},
                               deadline=time.monotonic() + 5)
        self.assertLessEqual(fake.timeouts[0], 5)

    def test_budget_is_under_gunicorn_and_nginx_60_seconds(self):
        self.assertLess(providers.TOTAL_BUDGET, 60)


class SameReturnTwiceTests(SocialBase):
    """Второй запрос того же адреса возврата не делает второго обмена."""

    def test_second_request_while_the_first_waits_gets_busy_page(self):
        _location, query = self.start('vk', '/vp/x/')
        url = '/auth/vk/callback/'
        params = {'code': AUTH_CODE, 'device_id': DEVICE, 'state': query['state'][0]}
        fake = FakeVK()
        inner = {}

        def slow_urlopen(request, timeout=None):
            # Пока первый ждёт VK, браузер шлёт тот же адрес ещё раз. Сессия
            # первого ещё не сохранена — `state` в ней цел.
            if request.full_url == providers.VKProvider.TOKEN_URL and not inner:
                inner['response'] = self.client.get(url, params)
            return fake(request, timeout)

        with mock.patch.object(providers.urllib.request, 'urlopen', slow_urlopen), \
                self.assertLogs('problems.social.views', 'WARNING') as logs:
            first = self.client.get(url, params)
        self.assertEqual(fake.token_attempts, 1)
        self.assertEqual(inner['response'].status_code, 409)
        self.assertContains(inner['response'], 'Вход через VK ID уже выполняется',
                            status_code=409)
        self.assertContains(inner['response'], 'Попробовать снова', status_code=409)
        self.assertRedirects(first, '/auth/finish/', fetch_redirect_response=False)
        self.assertIn('повторный возврат с тем же state', '\n'.join(logs.output))

    def test_same_return_after_login_goes_on_without_exchange(self):
        owner = User.objects.create_user('known', password='x')
        SocialAccount.objects.create(user=owner, provider='vk', uid='1001')
        _location, query = self.start('vk', '/vp/x/')
        params = {'code': AUTH_CODE, 'device_id': DEVICE, 'state': query['state'][0]}
        fake = FakeVK()
        with mock.patch.object(providers.urllib.request, 'urlopen', fake):
            first = self.client.get('/auth/vk/callback/', params)
            again = self.client.get('/auth/vk/callback/', params)
        self.assertRedirects(first, '/vp/x/', fetch_redirect_response=False)
        # Поток уже забран из сессии, а `next` вместе с ним — дом по роли.
        self.assertRedirects(again, '/student/', fetch_redirect_response=False)
        self.assertEqual(fake.token_attempts, 1)

    def test_same_return_while_on_almost_done_goes_back_there(self):
        _location, query = self.start('vk')
        params = {'code': AUTH_CODE, 'device_id': DEVICE, 'state': query['state'][0]}
        fake = FakeVK()
        with mock.patch.object(providers.urllib.request, 'urlopen', fake):
            self.client.get('/auth/vk/callback/', params)
            again = self.client.get('/auth/vk/callback/', params)
        self.assertRedirects(again, '/auth/finish/', fetch_redirect_response=False)
        self.assertEqual(fake.token_attempts, 1)
