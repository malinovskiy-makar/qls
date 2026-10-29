# -*- coding: utf-8 -*-
"""Почта, фаза 4: согласие на рассылку (`legal/consent.py::wants_mail`, docs/MAIL.md)."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from legal import consent, documents
from problems.models_legal import ConsentRecord

User = get_user_model()
MAIL = ConsentRecord.Kind.MAIL


@override_settings(MAIL_ENABLED=True)
class MailConsentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('masha', email='masha@mail.ru',
                                             password='Parol-Rassylki-11',
                                             email_verified_at=timezone.now())
        self.client.force_login(self.user)

    # 8
    def test_raising_docs_version_does_not_unsubscribe(self):
        consent.grant(self.user, MAIL, ConsentRecord.Source.REGISTER)
        self.assertTrue(consent.wants_mail(self.user))
        with override_settings(LEGAL={**settings.LEGAL, 'docs_version': '3'}):
            self.assertFalse(consent.has_current(self.user, MAIL))
            self.assertTrue(consent.wants_mail(self.user))

    def test_grant_and_revoke_from_profile(self):
        response = self.client.post('/legal/mail/grant/')
        self.assertRedirects(response, '/profile/?tab=data', fetch_redirect_response=False)
        record = ConsentRecord.objects.get(user=self.user, kind=MAIL)
        self.assertEqual(record.source, ConsentRecord.Source.PROFILE)
        self.client.post('/legal/mail/revoke/')
        record.refresh_from_db()
        self.assertIsNotNone(record.revoked_at)       # отзыв — отметка, строка осталась
        self.assertFalse(consent.wants_mail(self.user))

    # 9
    def test_grant_without_verified_email_goes_to_email_page(self):
        self.user.email_verified_at = None
        self.user.save()
        response = self.client.post('/legal/mail/grant/')
        self.assertRedirects(response, '/account/email/?next=%2Fprofile%2F%3Ftab%3Ddata',
                             fetch_redirect_response=False)
        self.assertFalse(ConsentRecord.objects.filter(user=self.user, kind=MAIL).exists())

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get('/legal/mail/grant/').status_code, 405)

    def test_document_is_listed_and_served(self):
        self.assertIn('consent-mail', [d.slug for d in documents.all_documents()])
        self.assertContains(self.client.get('/legal/'), '/legal/consent-mail/')
        page = self.client.get('/legal/consent-mail/')
        self.assertContains(page, 'Согласие на получение рассылки')
        self.assertContains(page, 'Юнисендер')

    @override_settings(MAIL_ENABLED=False)
    def test_document_hidden_without_mail(self):
        self.assertNotIn('consent-mail', [d.slug for d in documents.all_documents()])
        self.assertEqual(self.client.get('/legal/consent-mail/').status_code, 404)
