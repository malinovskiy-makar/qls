# -*- coding: utf-8 -*-
"""`profiles_export`: признаки человека для разбора беты — без контактов."""
import csv
import io
import os
import tempfile
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from problems.management.commands.profiles_export import COLUMNS
from problems.models import User

PASSWORD = 'profiles-export-2026'


class ProfilesExportTests(TestCase):

    def setUp(self):
        self.first = User.objects.create_user(username='exp_one', password=PASSWORD,
                                              role='student')
        profile = self.first.profile
        profile.city = '  Москва '
        profile.phone = '+7 900 000-00-00'
        profile.prep_mode = ['self', 'tutor']
        profile.save()
        self.second = User.objects.create_user(username='exp_two', password=PASSWORD,
                                               role='student')
        handle, self.out = tempfile.mkstemp(suffix='.csv')
        os.close(handle)

    def tearDown(self):
        os.remove(self.out)

    def _rows(self, since='2000-01-01'):
        call_command('profiles_export', since=since, out=self.out, stdout=io.StringIO())
        with open(self.out, encoding='utf-8-sig', newline='') as handle:
            return list(csv.reader(handle))

    def test_one_row_per_user_under_the_exact_header(self):
        rows = self._rows()
        self.assertEqual(tuple(rows[0]), COLUMNS)
        self.assertEqual(len(rows) - 1, 2)

    def test_no_phone_login_or_email_column(self):
        header = self._rows()[0]
        for private in ('phone', 'username', 'email', 'first_name', 'last_name'):
            self.assertNotIn(private, header)

    def test_phone_value_does_not_leak_into_any_cell(self):
        rows = self._rows()
        self.assertFalse(any('+7 900' in cell for row in rows for cell in row))

    def test_city_is_trimmed_and_lowercased(self):
        rows = self._rows()
        row = dict(zip(rows[0], rows[1]))
        self.assertEqual(row['city'], 'москва')

    def test_list_answers_are_codes_joined_by_bar(self):
        rows = self._rows()
        row = dict(zip(rows[0], rows[1]))
        self.assertEqual(row['prep_mode'], 'self|tutor')

    def test_since_cuts_older_registrations(self):
        User.objects.filter(pk=self.first.pk).update(
            date_joined=timezone.now() - timedelta(days=30))
        since = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        rows = self._rows(since=since)
        self.assertEqual([r[0] for r in rows[1:]], [str(self.second.pk)])
