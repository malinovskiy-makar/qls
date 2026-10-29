# -*- coding: utf-8 -*-
"""Редакция 2 (29.10.2026): принявшие редакцию 1 один раз видят экран согласия.

Согласие на рассылку от номера редакции не зависит: правка Политики не должна
молча отписывать людей (`legal.consent.wants_mail`).
"""
from django.test import TestCase, override_settings

from legal import consent
from problems.models_legal import ConsentRecord
from problems.tests.factories import make_user

PD = ConsentRecord.Kind.PD
MAIL = ConsentRecord.Kind.MAIL


def old_record(user, kind, source=ConsentRecord.Source.REGISTER):
    """Запись, принятая на редакции 1 (до выкатки ред. 2)."""
    return ConsentRecord.objects.create(user=user, kind=kind, version='1', source=source)


@override_settings(LEGAL_ENFORCEMENT_ENABLED=True, MAIL_ENABLED=True)
class EditionTwoTests(TestCase):
    def setUp(self):
        self.user = make_user('edition_two')
        self.client.force_login(self.user)

    def test_the_site_runs_edition_two(self):
        self.assertEqual(consent.current_version(), '2')

    def test_edition_one_acceptor_is_sent_to_the_consent_screen_once(self):
        old = old_record(self.user, PD)
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/legal/accept/'))

        accept = self.client.post('/legal/accept/', {'agree': '1', 'next': '/profile/'})
        self.assertEqual(accept['Location'], '/profile/')
        old.refresh_from_db()
        self.assertIsNotNone(old.superseded_at)
        active = ConsentRecord.objects.get(user=self.user, kind=PD,
                                           revoked_at__isnull=True, superseded_at__isnull=True)
        self.assertEqual(active.version, '2')
        self.assertEqual(ConsentRecord.objects.filter(user=self.user, kind=PD).count(), 2)
        # Второй раз экран уже не показывается.
        self.assertEqual(self.client.get('/profile/').status_code, 200)

    def test_mail_consent_of_edition_one_survives_edition_two(self):
        old_record(self.user, PD)
        mail = old_record(self.user, MAIL)
        self.assertTrue(consent.wants_mail(self.user))
        self.client.post('/legal/accept/', {'agree': '1', 'next': '/profile/'})
        mail.refresh_from_db()
        self.assertIsNone(mail.superseded_at)
        self.assertIsNone(mail.revoked_at)
        self.assertEqual(mail.version, '1')
        self.assertTrue(consent.wants_mail(self.user))
        self.assertFalse(consent.has_current(self.user, MAIL))

    def test_mail_consent_is_not_a_reason_to_show_the_screen(self):
        """У кого только согласие на рассылку ред. 1 – экран спрашивает про данные, а не про рассылку."""
        old_record(self.user, MAIL)
        self.assertEqual(self.client.get('/profile/').status_code, 302)
        self.assertTrue(consent.wants_mail(self.user))
