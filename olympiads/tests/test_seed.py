"""Команда демонстрационных данных: числа обязаны сойтись ровно."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from olympiads.models import (
    Olympiad, OlympiadBenefit, OlympiadEvent, OlympiadScore, OlympiadVariant,
    RegionalCoordinator, UniversityProgram,
)


class SeedTests(TestCase):

    def test_without_yes_nothing_is_written(self):
        out = StringIO()
        call_command('seed_olympiads_demo', stdout=out)
        self.assertIn('ПЛАН', out.getvalue())
        self.assertEqual(Olympiad.objects.count(), 0)

    def test_with_yes_counts_match_exactly(self):
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertEqual(Olympiad.objects.count(), 21)
        self.assertEqual(
            Olympiad.objects.filter(display_group='main').count(), 16)
        self.assertEqual(
            Olympiad.objects.filter(display_group='related').count(), 5)
        self.assertEqual(UniversityProgram.objects.count(), 7)
        self.assertEqual(OlympiadBenefit.objects.count(), 21)
        self.assertEqual(OlympiadScore.objects.count(), 14)
        self.assertEqual(OlympiadVariant.objects.count(), 12)
        self.assertEqual(RegionalCoordinator.objects.count(), 85)

        vseros = Olympiad.objects.get(slug='vseros')
        self.assertEqual(vseros.stages.count(), 4)
        self.assertEqual(vseros.events.count(), 4)
        # Ни одной конкретной даты у ВсОШ — это и есть правда сезона.
        self.assertEqual(vseros.events.exclude(date_start=None).count(), 0)

    def test_every_olympiad_is_marked_as_placeholder(self):
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertEqual(
            Olympiad.objects.filter(is_placeholder=False).count(), 0)

    def test_forbidden_slugs_are_not_created(self):
        """solvehub, posh, cpm и ege олимпиадами не являются."""
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        for slug in ('solvehub', 'posh', 'cpm', 'ege'):
            self.assertFalse(Olympiad.objects.filter(slug=slug).exists(), slug)

    def test_score_gap_is_kept(self):
        """2022 год по 9 классу пропущен нарочно — блок обязан показать дыру."""
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertFalse(
            OlympiadScore.objects.filter(year=2022, grade=9).exists())

    def test_benefits_include_the_none_case(self):
        """Таблица льгот обязана уметь показать «льготы нет»."""
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertTrue(
            OlympiadBenefit.objects.filter(benefit_type='none').exists())

    def test_wipe_then_seed_is_idempotent(self):
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        call_command('seed_olympiads_demo', '--yes', '--wipe', stdout=StringIO())
        self.assertEqual(Olympiad.objects.count(), 21)
        self.assertEqual(OlympiadEvent.objects.count(), 10)
