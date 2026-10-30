"""Ночь 30.10, Э4: календарь сезона полосами (доска Calendar)."""
import re
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from olympiads import navigator as nav
from olympiads.models import OlympiadEvent, OlympiadFollow

from . import night_fixtures as fx

User = get_user_model()
TODAY = date(2026, 10, 30)
YEAR = '2026/27'
S = OlympiadEvent.DateStatus
K = OlympiadEvent.Kind


class SeasonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.stage = fx.stage(cls.olymp)
        cls.other = fx.olympiad('vp', kind='perechen', manual_rank=50)
        cls.quiet = fx.olympiad('quiet', manual_rank=10)
        make = OlympiadEvent.objects.create
        make(olympiad=cls.other, academic_year=YEAR, kind=K.REGISTRATION_OPEN,
             date_start=date(2026, 8, 20), date_status=S.CONFIRMED)
        make(olympiad=cls.other, academic_year=YEAR, kind=K.REGISTRATION_CLOSE,
             date_start=date(2026, 9, 21), date_status=S.CONFIRMED)
        make(olympiad=cls.other, academic_year=YEAR, kind=K.STAGE,
             approx_text='обычно в ноябре', date_status=S.AWAITING)
        make(olympiad=cls.olymp, academic_year=YEAR, kind=K.STAGE, stage=cls.stage,
             approx_text='в прошлом сезоне финал был 11 апреля',
             date_status=S.APPROX_LAST_YEAR)
        make(olympiad=cls.olymp, academic_year=YEAR, kind=K.RESULTS,
             approx_text='даты устанавливает субъект', date_status=S.AWAITING)
        cls.user = User.objects.create_user('pupil', password='x')

    def season(self, **kw):
        return nav.calendar_season(YEAR, today=TODAY, **kw)

    def test_every_event_is_a_bar_or_an_undated_line(self):
        season = self.season()
        events = OlympiadEvent.objects.filter(academic_year=YEAR).count()
        drawn = sum(len(b['events']) for lane in season['lanes'] for b in lane['bars'])
        undated = sum(len(lane['undated']) for lane in season['lanes'])
        self.assertEqual(drawn + undated, events)
        self.assertEqual(season['events_total'], events)

    def test_registration_pair_is_one_solid_bar(self):
        lane = [l for l in self.season()['lanes'] if l['olympiad'].slug == 'vp'][0]
        reg = [b for b in lane['bars'] if b['word'] == 'Регистрация'][0]
        self.assertEqual((reg['kind'], len(reg['events'])), ('ok', 2))
        self.assertEqual(reg['sub'], '20 авг — 21 сен')

    def test_unconfirmed_event_is_never_solid(self):
        for lane in self.season()['lanes']:
            for bar in lane['bars']:
                if any(not e.is_confirmed for e in bar['events']):
                    self.assertNotEqual(bar['kind'], 'ok')
        lane = [l for l in self.season()['lanes'] if l['olympiad'].slug == 'vs'][0]
        self.assertEqual([b['kind'] for b in lane['bars']], ['est'])
        self.assertTrue(lane['bars'][0]['point'])
        self.assertEqual([u['event'].kind for u in lane['undated']], [K.RESULTS])

    def test_month_from_text_only(self):
        self.assertEqual(nav.months_in_text('обычно в ноябре', YEAR),
                         (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(nav.months_in_text('в марте–апреле', YEAR),
                         (date(2027, 3, 1), date(2027, 4, 30)))
        self.assertIsNone(nav.months_in_text('устанавливает субъект', YEAR))

    def test_today_line_is_at_the_right_place(self):
        # Сетка 1 авг 2026 — 1 июн 2027 = 304 дня; 30 октября — 90-й день.
        self.assertEqual(self.season()['today_pct'], round(100 * 90 / 304, 2))
        self.assertIsNone(nav.calendar_season(YEAR, today=date(2027, 7, 1))['today_pct'])

    def test_olympiad_without_events_is_listed_without_dates(self):
        season = self.season()
        self.assertIn(self.quiet, season['without'])
        self.assertNotIn('quiet', [l['olympiad'].slug for l in season['lanes']])

    def test_followed_olympiad_gets_a_lane(self):
        OlympiadFollow.objects.create(user=self.user, olympiad=self.quiet)
        season = self.season(user=self.user)
        self.assertIn('quiet', [l['olympiad'].slug for l in season['lanes']])
        mine = self.season(user=self.user, only_mine=True)
        self.assertEqual([l['olympiad'].slug for l in mine['lanes']], ['quiet'])


@override_settings(OLYMPIADS_PUBLIC=True)
class CalendarPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.mosh = fx.olympiad('mosh', name_short='МОШ', manual_rank=5)
        cls.user = User.objects.create_user('pupil', password='x')

    def get(self, **params):
        return self.client.get(reverse('olympiads:calendar'), params)

    def test_guest_search_leads_to_login_and_adds_nothing(self):
        html = self.get(q='мош').content.decode()
        self.assertNotIn('name="q"', html)
        self.assertIn('/login/?next=', html)
        self.assertNotIn(reverse('olympiads:follow', args=['mosh']), html)

    def test_search_adds_olympiad_as_a_lane(self):
        self.client.force_login(self.user)
        html = self.get(q='мош').content.decode()
        follow = reverse('olympiads:follow', args=['mosh'])
        self.assertIn(follow, html)
        self.client.post(follow, {'next': reverse('olympiads:calendar')})
        html = self.get().content.decode()
        self.assertTrue(re.search(r'om-cal__name"><a href="/olympiads/mosh/"', html))
