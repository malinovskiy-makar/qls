"""Сторож источников. Главное, что он проверяет, — он НЕ трогает данные."""
import hashlib
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from olympiads.models import (FactSource, FactUpdateProposal, Olympiad,
                              OlympiadLevelYear)

MODULE = 'olympiads.management.commands.check_fact_sources'
BODY = b'<html>utverzhdennyj perechen</html>'
OTHER = b'<html>perechen izmenilsya</html>'


def sha(body):
    return hashlib.sha256(body).hexdigest()


class CheckFactSourcesTests(TestCase):

    def setUp(self):
        self.source = FactSource.objects.create(
            url='https://example.test/perechen', title='Перечень',
            doc_type='order', content_hash=sha(BODY))
        self.olympiad = Olympiad.objects.create(
            slug='vs', name_full='Тестовая', name_short='ТЕСТ',
            organizer='Никто', kind=Olympiad.Kind.PERECHEN)
        # Ровно ОДИН факт на источнике — иначе «ровно одно предложение»
        # означало бы разное при разном числе фактов.
        OlympiadLevelYear.objects.create(
            olympiad=self.olympiad, academic_year='2025/26', level=1,
            approval_status='approved', source=self.source)

    def test_unchanged_source_makes_no_proposals(self):
        with patch(MODULE + '.fetch', return_value=(BODY, 200)):
            call_command('check_fact_sources', delay=0, verbosity=0)
        self.assertEqual(FactUpdateProposal.objects.count(), 0)
        self.source.refresh_from_db()
        self.assertEqual(self.source.http_status, 200)

    def test_changed_source_makes_exactly_one_proposal(self):
        with patch(MODULE + '.fetch', return_value=(OTHER, 200)):
            call_command('check_fact_sources', delay=0, verbosity=0)
        self.assertEqual(FactUpdateProposal.objects.count(), 1)
        proposal = FactUpdateProposal.objects.get()
        self.assertEqual(proposal.target_model, 'OlympiadLevelYear')
        self.assertIn(sha(OTHER)[:16], proposal.new_value)

    def test_changed_source_does_not_touch_the_fact(self):
        """Данные остаются как были — правит человек, а не сторож."""
        with patch(MODULE + '.fetch', return_value=(OTHER, 200)):
            call_command('check_fact_sources', delay=0, verbosity=0)
        level = OlympiadLevelYear.objects.get()
        self.assertEqual(level.level, 1)
        self.assertEqual(level.approval_status, 'approved')

    def test_second_run_does_not_pile_up_proposals(self):
        """Сторож ходит по расписанию — за неделю накопилось бы семь копий."""
        with patch(MODULE + '.fetch', return_value=(OTHER, 200)):
            call_command('check_fact_sources', delay=0, verbosity=0)
            call_command('check_fact_sources', delay=0, verbosity=0)
        self.assertEqual(FactUpdateProposal.objects.count(), 1)

    def test_unreachable_source_keeps_the_old_hash(self):
        """⚠️ Сайт лёг на десять минут — это не изменение факта."""
        with patch(MODULE + '.fetch', return_value=(None, 503)):
            call_command('check_fact_sources', delay=0, verbosity=0)
        self.source.refresh_from_db()
        self.assertEqual(self.source.content_hash, sha(BODY))
        self.assertEqual(self.source.http_status, 503)
        self.assertEqual(FactUpdateProposal.objects.count(), 0)

    def test_non_http_source_is_not_opened(self):
        """⚠️ Адрес источника — данные. `file:` сторож открывать не должен.

        Находка bandit B310, и она настоящая: адреса вводит человек в
        админке, а `urlopen` честно исполнил бы `file:///etc/passwd`.
        """
        from olympiads.management.commands.check_fact_sources import fetch

        body, status = fetch('file:///etc/passwd')
        self.assertIsNone(body)
        self.assertIsNone(status)

    def test_dry_run_writes_nothing(self):
        with patch(MODULE + '.fetch', return_value=(OTHER, 200)):
            call_command('check_fact_sources', dry_run=True, delay=0,
                         verbosity=0)
        self.assertEqual(FactUpdateProposal.objects.count(), 0)
        self.source.refresh_from_db()
        self.assertEqual(self.source.content_hash, sha(BODY))
        self.assertIsNone(self.source.http_status)
