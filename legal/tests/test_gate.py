# -*- coding: utf-8 -*-
"""Фаза 4: блокирующий экран согласия для уже зарегистрированных."""
import asyncio

from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from legal import consent
from problems.models_legal import ConsentRecord
from legal.ws import CLOSE_CONSENT_REQUIRED, ConsentSocketMiddleware
from problems.tests.factories import make_user

PD = ConsentRecord.Kind.PD


@override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
class GateTests(TestCase):
    def setUp(self):
        self.user = make_user('gate_user')

    def _login(self):
        self.client.force_login(self.user)

    def test_page_request_without_record_redirects_with_return_address(self):
        self._login()
        response = self.client.get('/catalog/?q=%D0%BA%D0%BF%D0%B2')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'],
                         '/legal/accept/?next=%2Fcatalog%2F%3Fq%3D%25D0%25BA%25D0%25BF%25D0%25B2')

    def test_script_request_gets_403_with_a_code_and_no_redirect(self):
        self._login()
        for kwargs in ({'path': '/catalog/api/problem/1/'},
                       {'path': '/profile/', 'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'},
                       {'path': '/profile/', 'HTTP_ACCEPT': 'application/json'},
                       {'path': '/profile/', 'HTTP_SEC_FETCH_DEST': 'empty'},
                       {'path': '/catalog/problem/1/?pane=1'}):
            path = kwargs.pop('path')
            response = self.client.get(path, **kwargs)
            self.assertEqual(response.status_code, 403, (path, kwargs))
            self.assertEqual(response.json()['error'], 'consent_required', (path, kwargs))
            self.assertNotIn('Location', response)

    def test_json_post_is_refused_too(self):
        self._login()
        response = self.client.post('/api/feedback/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'consent_required')

    def test_accepting_lets_the_person_through_and_returns_to_the_original_address(self):
        self._login()
        first = self.client.get('/profile/stats/')
        self.assertEqual(first.status_code, 302)
        accept = self.client.post(first['Location'].split('?')[0], {
            'agree': '1', 'next': '/profile/stats/'})
        self.assertEqual(accept.status_code, 302)
        self.assertEqual(accept['Location'], '/profile/stats/')
        record = ConsentRecord.objects.get(user=self.user)
        self.assertEqual((record.kind, record.source, record.version), ('pd', 'gate', '1'))
        self.assertEqual(self.client.get('/profile/stats/').status_code, 200)

    def test_accept_without_the_checkbox_does_not_record_anything(self):
        self._login()
        response = self.client.post('/legal/accept/', {'next': '/profile/'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ConsentRecord.objects.count(), 0)
        self.assertContains(response, 'Отметьте галочку')

    def test_foreign_return_address_is_ignored(self):
        self._login()
        response = self.client.post('/legal/accept/', {'agree': '1', 'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], '/')

    def test_old_edition_shows_the_screen_again(self):
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self._login()
        self.assertEqual(self.client.get('/profile/').status_code, 200)
        with override_settings(LEGAL={**settings.LEGAL, 'docs_version': '2'}):
            response = self.client.get('/profile/')
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response['Location'].startswith('/legal/accept/'))

    def test_revoked_record_blocks(self):
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        consent.revoke(self.user, PD)
        self._login()
        self.assertEqual(self.client.get('/profile/').status_code, 302)

    def test_guest_never_sees_the_screen(self):
        for url in ('/', '/catalog/', '/login/', '/register/', '/game/', '/calc2/'):
            response = self.client.get(url)
            self.assertNotIn('/legal/accept/', response.get('Location', ''), url)
        self.assertEqual(self.client.get('/catalog/').status_code, 200)

    def test_exempt_addresses_open_without_consent(self):
        self._login()
        for url in ('/legal/', '/legal/privacy/', '/legal/consent/', '/legal/consent-ai/',
                    '/legal/cookies/', '/legal/terms/', '/legal/recommendations/',
                    '/healthz/', '/health/', '/legal/accept/', '/robots.txt'):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get('/static/does-not-exist.css').status_code, 404)
        track = self.client.post('/api/track/', '{}', content_type='application/json')
        self.assertNotIn(b'consent_required', track.content)

    def test_logout_works_without_consent(self):
        self._login()
        response = self.client.post('/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    def test_password_change_endpoint_is_not_blocked(self):
        self._login()
        response = self.client.get('/password/change/')
        self.assertFalse(response.get('Location', '').startswith('/legal/accept/'))

    def test_admin_is_not_blocked_but_staff_goes_through_the_screen_elsewhere(self):
        staff = make_user('gate_staff', role='teacher', is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/legal/accept/'))

    def test_screen_text(self):
        self._login()
        html = self.client.get('/legal/accept/').content.decode('utf-8')
        for needle in ('Правила обработки данных Weconomics',
                       'Чтобы продолжить, ознакомьтесь с документами и примите их.',
                       'Политика обработки персональных данных',
                       'Согласие на обработку персональных данных',
                       'Пользовательское соглашение', 'Принимаю', 'Выйти',
                       'Мне есть 18 лет, либо я пользуюсь сайтом с согласия родителя, который '
                       'ознакомился с документами. Я принимаю ',
                       'Не согласны? Напишите нам, и мы удалим учётную запись:',
                       'weconomics_ru'):
            self.assertIn(needle, html)
        for banned in ('обновили', 'изменили', 'новая редакция', 'Новая редакция'):
            self.assertNotIn(banned, html)
        # Человек на экране уже зарегистрирован: слова «регистрируюсь» здесь нет.
        self.assertNotIn('регистрируюсь', html)

    def test_screen_for_guest_goes_to_login(self):
        response = self.client.get('/legal/accept/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/login/'))

    def test_already_accepted_person_is_bounced_from_the_screen(self):
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self._login()
        response = self.client.get('/legal/accept/?next=/profile/')
        self.assertEqual(response['Location'], '/profile/')

    def test_gate_adds_no_query_per_page_after_the_first(self):
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self._login()
        self.client.get('/legal/')  # прогрев сессии и кэшей
        self.client.get('/profile/')
        with CaptureQueriesContext(connection) as warm:
            self.client.get('/legal/')
        with CaptureQueriesContext(connection) as page:
            self.client.get('/profile/stats/data/')
        consent_queries = [q for q in page.captured_queries if 'problems_consentrecord' in q['sql']]
        self.assertEqual(consent_queries, [], 'признак должен лежать в сессии')
        self.assertEqual([q for q in warm.captured_queries if 'problems_consentrecord' in q['sql']], [])

    def test_session_flag_is_dropped_when_the_edition_changes(self):
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self._login()
        self.assertEqual(self.client.get('/profile/').status_code, 200)
        self.assertEqual(self.client.session[consent.SESSION_KEY], '1')
        with override_settings(LEGAL={**settings.LEGAL, 'docs_version': '3'}):
            self.assertEqual(self.client.get('/profile/').status_code, 302)


@override_settings(LEGAL_ENFORCEMENT_ENABLED=False)
class GateSwitchedOffTests(TestCase):
    def test_gate_is_off_in_test_runs_by_default(self):
        """Тысячи прежних тестов ходят вошедшим без записи согласия."""
        user = make_user('gate_off')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/profile/').status_code, 200)


class SocketGateTests(TransactionTestCase):
    """Сокеты дуэли: вошедший без записи не подключается."""

    @staticmethod
    async def _inner(scope, receive, send):
        await receive()
        await send({'type': 'websocket.accept'})

    def _connect(self, user):
        app = ConsentSocketMiddleware(self._inner)

        async def go():
            communicator = WebsocketCommunicator(app, '/ws/duel/x/')
            communicator.scope['user'] = user
            result = await communicator.connect()
            if result[0]:
                await communicator.disconnect()
            return result
        return asyncio.run(go())

    @override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
    def test_user_without_record_is_refused(self):
        user = make_user('ws_nope')
        connected, code = self._connect(user)
        self.assertFalse(connected)
        self.assertEqual(code, CLOSE_CONSENT_REQUIRED)

    @override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
    def test_user_with_record_connects(self):
        user = make_user('ws_ok')
        consent.grant(user, PD, ConsentRecord.Source.REGISTER)
        self.assertTrue(self._connect(user)[0])

    @override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
    def test_guest_is_passed_to_the_consumer_own_rules(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertTrue(self._connect(AnonymousUser())[0])

    @override_settings(LEGAL_ENFORCEMENT_ENABLED=False)
    def test_switched_off(self):
        self.assertTrue(self._connect(make_user('ws_off'))[0])

    def test_the_real_application_has_the_gate_inside_the_auth_stack(self):
        """Обёртка подключена в боевой маршрутизации, а не лежит рядом."""
        import re
        from pathlib import Path
        source = (Path(settings.BASE_DIR) / 'config' / 'asgi.py').read_text(encoding='utf-8')
        self.assertRegex(source, re.compile(
            r'AuthMiddlewareStack\(\s*ConsentSocketMiddleware\(\s*URLRouter\('))
