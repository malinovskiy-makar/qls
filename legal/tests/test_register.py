# -*- coding: utf-8 -*-
"""Фаза 3: регистрация пишет согласие в той же транзакции, что и пользователя."""
from unittest import mock

from django.test import TestCase

from problems.models_legal import ConsentRecord
from problems.models import User

DATA = {'username': 'novichok', 'password1': 'Gh7-kLm2-Qw9x', 'password2': 'Gh7-kLm2-Qw9x',
        'role': 'student'}


class RegisterConsentTests(TestCase):
    def test_registration_creates_exactly_one_pd_record(self):
        response = self.client.post('/register/', {**DATA, 'consent': 'on'})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='novichok')
        records = ConsentRecord.objects.filter(user=user)
        self.assertEqual(records.count(), 1)
        record = records.get()
        self.assertEqual((record.kind, record.source, record.version), ('pd', 'register', '1'))
        self.assertIsNone(record.revoked_at)

    def test_without_the_checkbox_nothing_is_created(self):
        response = self.client.post('/register/', DATA)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='novichok').exists())
        self.assertEqual(ConsentRecord.objects.count(), 0)
        html = response.content.decode('utf-8')
        self.assertIn('Без согласия зарегистрироваться нельзя.', html)
        self.assertNotIn('зарегистрировать нельзя', html)

    def test_user_and_record_are_one_transaction(self):
        """Сбой записи согласия не оставляет аккаунт без доказательства."""
        with mock.patch('problems.views_auth.consent.grant', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.client.post('/register/', {**DATA, 'consent': 'on'})
        self.assertFalse(User.objects.filter(username='novichok').exists())
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_the_checkbox_text_and_three_links(self):
        html = self.client.get('/register/').content.decode('utf-8')
        text = ('Мне есть 18 лет, либо я регистрируюсь с согласия родителя, который '
                'ознакомился с документами. Я принимаю ')
        self.assertIn(text, html)
        for label, url in (('Пользовательское соглашение', '/legal/terms/'),
                           ('Согласие', '/legal/consent/'),
                           ('Политикой', '/legal/privacy/')):
            self.assertIn('<a href="%s" target="_blank" rel="noopener">%s</a>' % (url, label), html)
        self.assertIn('на обработку персональных данных в соответствии с ', html)

    def test_registered_person_is_not_stopped_by_the_gate(self):
        with self.settings(LEGAL_ENFORCEMENT_ENABLED=True):
            self.client.post('/register/', {**DATA, 'consent': 'on'})
            response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 200)
