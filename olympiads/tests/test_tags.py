"""Теги олимпиады: по ним же работают чипы-фильтры на главной."""
from datetime import date, timedelta

from django.test import TestCase

from olympiads.models import (
    Olympiad, OlympiadEvent, OlympiadLevelYear, current_academic_year,
)

from .test_models import make_olympiad


class TagTests(TestCase):

    def test_vsosh_gets_law_bvi_and_no_level(self):
        """У ВсОШ уровня в перечне нет — и первый чип нужен именно ей."""
        olympiad = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH)
        tags = olympiad.tags
        self.assertIn('law_bvi', tags)
        self.assertNotIn('level_1', tags)
        self.assertNotIn('level_23', tags)

    def test_level_two_gets_level_23(self):
        olympiad = make_olympiad('pleh')
        OlympiadLevelYear.objects.create(
            olympiad=olympiad, academic_year=current_academic_year(), level=2)
        self.assertIn('level_23', olympiad.tags)
        self.assertNotIn('level_1', olympiad.tags)

    def test_level_one_gets_level_1(self):
        olympiad = make_olympiad('vp')
        OlympiadLevelYear.objects.create(
            olympiad=olympiad, academic_year=current_academic_year(), level=1)
        self.assertIn('level_1', olympiad.tags)
        self.assertNotIn('level_23', olympiad.tags)

    def test_grade_min_five_gets_young(self):
        olympiad = make_olympiad('sb', grade_min=5, grade_max=11)
        self.assertIn('young', olympiad.tags)

    def test_grade_min_nine_has_no_young(self):
        olympiad = make_olympiad('lom', grade_min=9, grade_max=11)
        self.assertNotIn('young', olympiad.tags)

    def test_registration_open_needs_open_in_past_and_close_in_future(self):
        olympiad = make_olympiad('mosh')
        today = date.today()
        OlympiadEvent.objects.create(
            olympiad=olympiad, academic_year=current_academic_year(),
            kind=OlympiadEvent.Kind.REGISTRATION_OPEN,
            date_status=OlympiadEvent.DateStatus.CONFIRMED,
            date_start=today - timedelta(days=5))
        self.assertNotIn('registration_open', olympiad.tags)

        OlympiadEvent.objects.create(
            olympiad=olympiad, academic_year=current_academic_year(),
            kind=OlympiadEvent.Kind.REGISTRATION_CLOSE,
            date_status=OlympiadEvent.DateStatus.CONFIRMED,
            date_start=today + timedelta(days=5))
        olympiad = Olympiad.objects.get(pk=olympiad.pk)
        self.assertIn('registration_open', olympiad.tags)

    def test_online_and_team_flags(self):
        olympiad = make_olympiad('dano', is_team=True,
                                 has_online_qualifier=True,
                                 has_online_final=True)
        tags = olympiad.tags
        self.assertIn('team', tags)
        self.assertIn('online_qual', tags)
        self.assertIn('online_final', tags)
