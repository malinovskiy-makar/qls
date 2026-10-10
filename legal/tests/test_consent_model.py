# -*- coding: utf-8 -*-
"""Фаза 2: запись согласия - кто, что, какую редакцию, когда; отзыв не стирает строку."""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from legal import consent
from problems.models_legal import ConsentRecord
from problems.tests.factories import make_user

PD = ConsentRecord.Kind.PD
AI = ConsentRecord.Kind.AI


class ConsentRecordTests(TestCase):
    def setUp(self):
        self.user = make_user('consent_model')

    def test_grant_writes_who_what_version_when_and_where_from(self):
        record = consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        self.assertEqual((record.user, record.kind, record.version, record.source),
                         (self.user, 'pd', '1', 'register'))
        self.assertIsNotNone(record.given_at)
        self.assertIsNone(record.revoked_at)

    def test_no_ip_or_user_agent_is_stored(self):
        names = {f.name for f in ConsentRecord._meta.get_fields()}
        self.assertFalse({n for n in names if 'ip' in n.split('_') or 'agent' in n or 'ua' == n})
        self.assertEqual(names, {'id', 'user', 'kind', 'version', 'given_at', 'source',
                                 'revoked_at', 'superseded_at'})

    def test_grant_is_idempotent(self):
        first = consent.grant(self.user, PD, ConsentRecord.Source.GATE)
        second = consent.grant(self.user, PD, ConsentRecord.Source.GATE)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ConsentRecord.objects.filter(user=self.user).count(), 1)

    def test_revoke_keeps_the_row(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        self.assertEqual(consent.revoke(self.user, AI), 1)
        self.assertEqual(ConsentRecord.objects.filter(user=self.user, kind=AI).count(), 1)
        self.assertFalse(consent.has_current(self.user, AI))
        self.assertIsNotNone(ConsentRecord.objects.get(user=self.user, kind=AI).revoked_at)

    def test_regrant_after_revoke_makes_a_new_active_row_and_keeps_history(self):
        consent.grant(self.user, AI, ConsentRecord.Source.CHAT)
        consent.revoke(self.user, AI)
        consent.grant(self.user, AI, ConsentRecord.Source.PROFILE)
        rows = ConsentRecord.objects.filter(user=self.user, kind=AI)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows.filter(revoked_at__isnull=True).count(), 1)
        self.assertTrue(consent.has_current(self.user, AI))

    def test_kinds_are_independent(self):
        consent.grant(self.user, PD, ConsentRecord.Source.GATE)
        self.assertTrue(consent.has_current(self.user, PD))
        self.assertFalse(consent.has_current(self.user, AI))

    def test_a_new_edition_supersedes_the_old_one_without_deleting_it(self):
        consent.grant(self.user, PD, ConsentRecord.Source.REGISTER)
        with override_settings(LEGAL={**settings.LEGAL, 'docs_version': '2'}):
            self.assertFalse(consent.has_current(self.user, PD))
            consent.grant(self.user, PD, ConsentRecord.Source.GATE)
            self.assertTrue(consent.has_current(self.user, PD))
        rows = ConsentRecord.objects.filter(user=self.user, kind=PD).order_by('pk')
        self.assertEqual([r.version for r in rows], ['1', '2'])
        self.assertIsNotNone(rows[0].superseded_at)
        self.assertEqual(rows.filter(revoked_at__isnull=True, superseded_at__isnull=True).count(), 1)

    def test_database_refuses_a_second_active_row(self):
        consent.grant(self.user, PD, ConsentRecord.Source.GATE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConsentRecord.objects.create(user=self.user, kind=PD, version='1',
                                         source=ConsentRecord.Source.GATE)

    def test_guest_has_no_consent(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(consent.has_current(AnonymousUser(), PD))
