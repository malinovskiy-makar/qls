"""Правила, ради которых модели раздела вообще заведены отдельно."""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from olympiads.models import (
    Olympiad, OlympiadEvent, OlympiadLevelYear, current_academic_year,
)


def make_olympiad(slug='x', **kwargs):
    defaults = dict(
        name_full='Олимпиада ' + slug, name_short=slug.upper(),
        organizer='Кто-то', kind=Olympiad.Kind.PERECHEN,
    )
    defaults.update(kwargs)
    return Olympiad.objects.create(slug=slug, **defaults)


class EventDateRuleTests(TestCase):
    """Неподтверждённая дата не имеет права быть конкретной.

    Школьник читает число как факт и планирует по нему регистрацию.
    """

    def setUp(self):
        self.olympiad = make_olympiad('vs', kind=Olympiad.Kind.VSOSH)

    def test_awaiting_with_date_is_rejected(self):
        event = OlympiadEvent(
            olympiad=self.olympiad, academic_year='2026/27',
            kind=OlympiadEvent.Kind.STAGE,
            date_status=OlympiadEvent.DateStatus.AWAITING,
            date_start=date(2027, 1, 20), approx_text='обычно в январе',
        )
        with self.assertRaises(ValidationError) as caught:
            event.full_clean()
        self.assertIn('date_start', caught.exception.error_dict)

    def test_approx_without_text_is_rejected(self):
        event = OlympiadEvent(
            olympiad=self.olympiad, academic_year='2026/27',
            kind=OlympiadEvent.Kind.STAGE,
            date_status=OlympiadEvent.DateStatus.APPROX_LAST_YEAR,
            date_start=None, approx_text='   ',
        )
        with self.assertRaises(ValidationError) as caught:
            event.full_clean()
        self.assertIn('approx_text', caught.exception.error_dict)

    def test_confirmed_without_date_is_rejected(self):
        event = OlympiadEvent(
            olympiad=self.olympiad, academic_year='2026/27',
            kind=OlympiadEvent.Kind.STAGE,
            date_status=OlympiadEvent.DateStatus.CONFIRMED,
            date_start=None, approx_text='',
        )
        with self.assertRaises(ValidationError) as caught:
            event.full_clean()
        self.assertIn('date_start', caught.exception.error_dict)

    def test_confirmed_with_date_passes_and_shows_number(self):
        event = OlympiadEvent(
            olympiad=self.olympiad, academic_year='2026/27',
            kind=OlympiadEvent.Kind.STAGE,
            date_status=OlympiadEvent.DateStatus.CONFIRMED,
            date_start=date(2026, 9, 24),
        )
        event.full_clean()
        self.assertEqual(event.display_date, '24 сентября, 2026')

    def test_unconfirmed_shows_words_not_a_number(self):
        event = OlympiadEvent(
            olympiad=self.olympiad, academic_year='2026/27',
            kind=OlympiadEvent.Kind.STAGE,
            date_status=OlympiadEvent.DateStatus.AWAITING,
            approx_text='график ещё не опубликован',
        )
        event.full_clean()
        self.assertEqual(event.display_date, 'график ещё не опубликован')
        self.assertIsNone(event.day_number)


class LevelYearTests(TestCase):

    def test_null_level_is_allowed_for_vsosh(self):
        """У ВсОШ уровня нет вовсе — она не в перечне. Это не пробел."""
        olympiad = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH)
        row = OlympiadLevelYear(
            olympiad=olympiad, academic_year='2026/27', level=None,
            approval_status=OlympiadLevelYear.ApprovalStatus.APPROVED,
        )
        row.full_clean()
        row.save()
        self.assertIsNone(olympiad.level_for('2026/27'))

    def test_two_levels_for_one_year_are_rejected(self):
        olympiad = make_olympiad('mosh')
        OlympiadLevelYear.objects.create(
            olympiad=olympiad, academic_year='2026/27', level=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OlympiadLevelYear.objects.create(
                    olympiad=olympiad, academic_year='2026/27', level=2)


class SortKeyTests(TestCase):

    def test_vsosh_is_first_even_with_zero_rank_and_zero_problems(self):
        """Уровня у ВсОШ нет, ранг ноль, задач ноль — и всё равно первая."""
        vsosh = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH,
                              manual_rank=0)
        top = make_olympiad('mosh', kind=Olympiad.Kind.PERECHEN,
                            manual_rank=999)
        OlympiadLevelYear.objects.create(
            olympiad=top, academic_year=current_academic_year(), level=1)
        order = sorted([top, vsosh], key=lambda o: o.sort_key())
        self.assertEqual([o.slug for o in order], ['vseros', 'mosh'])

    def test_level_beats_manual_rank(self):
        year = current_academic_year()
        first = make_olympiad('a', manual_rank=1)
        second = make_olympiad('b', manual_rank=500)
        OlympiadLevelYear.objects.create(
            olympiad=first, academic_year=year, level=1)
        OlympiadLevelYear.objects.create(
            olympiad=second, academic_year=year, level=3)
        order = sorted([second, first], key=lambda o: o.sort_key())
        self.assertEqual([o.slug for o in order], ['a', 'b'])

    def test_no_level_goes_after_level_three(self):
        year = current_academic_year()
        levelled = make_olympiad('c', manual_rank=0)
        OlympiadLevelYear.objects.create(
            olympiad=levelled, academic_year=year, level=3)
        plain = make_olympiad('d', manual_rank=900)
        order = sorted([plain, levelled], key=lambda o: o.sort_key())
        self.assertEqual([o.slug for o in order], ['c', 'd'])
