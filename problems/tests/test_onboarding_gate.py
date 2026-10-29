# -*- coding: utf-8 -*-
"""Шлюз онбординга (фаза 5): таблица «кто → куда».

Флаг `ONBOARDING_ENABLED` в тестах выключен по умолчанию (старые тесты шлюза не
замечают); здесь он включён явно.
"""
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from legal import consent
from problems.models_legal import ConsentRecord
from problems.tests.factories import make_user


@override_settings(ONBOARDING_ENABLED=True)
class GateTableTests(TestCase):
    def setUp(self):
        self.user = make_user('newbie')
        self.client.force_login(self.user)

    def test_not_onboarded_get_page_goes_to_welcome(self):
        response = self.client.get('/catalog/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/welcome/?next=/catalog/')

    def test_query_string_is_kept_in_next(self):
        response = self.client.get('/catalog/?q=спрос')
        self.assertTrue(response['Location'].startswith('/welcome/?next=/catalog/%3Fq%3D'))

    def test_post_is_not_intercepted(self):
        # Обычная форма страницы, не API: её перехват сломал бы сохранение.
        response = self.client.post('/profile/', {'action': 'data'})
        self.assertFalse(response.get('Location', '').startswith('/welcome/'))

    def test_script_request_is_not_intercepted(self):
        response = self.client.get('/catalog/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(response.get('Location', '').startswith('/welcome/'))

    def test_documents_open(self):
        self.assertEqual(self.client.get('/legal/privacy/').status_code, 200)

    def test_welcome_itself_is_not_intercepted(self):
        response = self.client.get('/welcome/role/')
        self.assertEqual(response.status_code, 200)

    def test_staff_is_not_intercepted(self):
        self.client.force_login(make_user('staffer', is_staff=True))
        self.assertFalse(self.client.get('/catalog/').get('Location', '').startswith('/welcome/'))

    def test_onboarded_is_not_intercepted(self):
        self.user.profile.onboarded_at = timezone.now()
        self.user.profile.save()
        self.assertEqual(self.client.get('/catalog/').status_code, 200)

    def test_guest_is_not_intercepted(self):
        self.client.logout()
        self.assertEqual(self.client.get('/catalog/').status_code, 200)

    @override_settings(ONBOARDING_ENABLED=False)
    def test_flag_off_is_not_intercepted(self):
        self.assertEqual(self.client.get('/catalog/').status_code, 200)

    @override_settings(LEGAL_ENFORCEMENT_ENABLED=True)
    def test_documents_screen_comes_first(self):
        response = self.client.get('/catalog/')
        self.assertTrue(response['Location'].startswith('/legal/accept/'), response['Location'])
        consent.grant(self.user, ConsentRecord.Kind.PD, ConsentRecord.Source.GATE)
        response = self.client.get('/catalog/')
        self.assertEqual(response['Location'], '/welcome/?next=/catalog/')

    def test_gate_sits_right_after_the_consent_layer(self):
        layers = list(settings.MIDDLEWARE)
        self.assertEqual(layers.index('problems.middleware_onboarding.OnboardingGateMiddleware'),
                         layers.index('legal.middleware.ConsentGateMiddleware') + 1)

    def test_after_onboarding_the_flag_lives_in_the_session(self):
        self.user.profile.onboarded_at = timezone.now()
        self.user.profile.save()
        self.client.get('/catalog/')
        self.assertTrue(self.client.session.get('onboarded'))
