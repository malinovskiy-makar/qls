"""Стена 2 тура, правило: `vp/wall.py` и стена в `vp.views.start` (docs/VP.md, ADR 0168).

Проверка серверная, поэтому тесты бьют по `start` напрямую. Во всех тестах со
стеной включён хотя бы один путь контакта, иначе всё уходит в `?wall=closed`.
"""
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from vp import checks, landing, wall
from vp.models import VPAttempt, VPWall
from vp.tests.helpers import load_demo, make_published

User = get_user_model()

#: Стена включена, путь Telegram настроен подставными значениями.
WALL_ON = override_settings(
    VP_WALL_ENABLED=True, VP_WALL_TG_ENABLED=True, MAIL_ENABLED=False,
    TELEGRAM_BOT_TOKEN='000:test-token', TELEGRAM_BOT_USERNAME='test_wall_bot',
    TELEGRAM_WEBHOOK_SECRET='test-secret')


class WallCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def setUp(self):
        self.user = User.objects.create_user('wall_u', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)

    def start(self, client=None, slug=None, with_timer='1'):
        return (client or self.client).post(
            reverse('vp:start', args=[slug or self.variant.slug]), {'with_timer': with_timer})

    def wall_url(self, slug=None, state='1'):
        return '/vp/%s/?wall=%s' % (slug or self.variant.slug, state)

    def give(self, contact='tg', survey=False):
        VPWall.objects.update_or_create(user=self.user, defaults={
            'contact_via': contact, 'contact_at': timezone.now() if contact else None,
            'grade': '10' if survey else '', 'tour2_status': 'passed' if survey else '',
            'source': 'friend' if survey else '',
            'survey_at': timezone.now() if survey else None})


class StartRuleTests(WallCase):
    @override_settings(VP_WALL_ENABLED=False)
    def test_wall_off_start_creates_attempt_as_before(self):
        response = self.start()
        attempt = VPAttempt.objects.get()
        self.assertRedirects(response, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)

    @WALL_ON
    def test_no_contact_goes_to_wall_without_attempt(self):
        response = self.start(with_timer='0')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], self.wall_url())
        self.assertEqual(VPAttempt.objects.count(), 0)
        self.assertEqual(VPWall.objects.filter(user=self.user).count(), 1)
        self.assertEqual(self.client.session[wall.SESSION_NEXT],
                         {'slug': self.variant.slug, 'with_timer': False})

    @WALL_ON
    def test_guest_without_timer_goes_to_register_and_keeps_the_mode(self):
        guest = Client()
        response = self.start(client=guest, with_timer='0')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/register/?next='))
        self.assertIn('%3Fwall%3D1', response['Location'])
        self.assertIs(guest.session[wall.SESSION_NEXT]['with_timer'], False)
        self.assertEqual(VPAttempt.objects.count(), 0)

    @WALL_ON
    def test_verified_email_alone_is_not_a_contact(self):
        self.user.email = 'wall@example.ru'
        self.user.email_verified_at = timezone.now()
        self.user.save()
        response = self.start()
        self.assertEqual(response['Location'], self.wall_url())
        self.assertEqual(wall.step(self.user), 'contact')

    @WALL_ON
    def test_contact_without_survey_still_walls(self):
        self.give('tg', survey=False)
        self.assertEqual(self.start()['Location'], self.wall_url())
        self.assertEqual(VPAttempt.objects.count(), 0)

    @WALL_ON
    def test_contact_and_survey_start_the_attempt(self):
        self.give('email', survey=True)
        response = self.start()
        attempt = VPAttempt.objects.get()
        self.assertRedirects(response, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)

    def test_unfinished_attempt_returns_without_wall(self):
        with override_settings(VP_WALL_ENABLED=False):
            first = self.start()
        with WALL_ON:
            again = self.start()
        self.assertEqual(again['Location'], first['Location'])
        self.assertEqual(VPAttempt.objects.count(), 1)

    @WALL_ON
    def test_staff_meets_the_wall_on_tour2_but_not_on_tour1(self):
        self.user.is_staff = True
        self.user.save()
        self.assertEqual(self.start()['Location'], self.wall_url())
        tour1 = make_published('wall-t1')
        response = self.start(slug=tour1.slug)
        attempt = VPAttempt.objects.get(variant=tour1)
        self.assertRedirects(response, reverse('vp:take', args=[attempt.public_code]),
                             fetch_redirect_response=False)

    @override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=False, TELEGRAM_BOT_TOKEN='',
                       TELEGRAM_BOT_USERNAME='', TELEGRAM_WEBHOOK_SECRET='')
    def test_no_paths_at_all_closes_the_entrance(self):
        with self.assertLogs('vp.views', 'WARNING'):
            response = self.start()
        self.assertEqual(response['Location'], self.wall_url(state='closed'))
        self.assertEqual(VPAttempt.objects.count(), 0)


class PassContactTests(TestCase):
    def test_first_path_stays(self):
        user = User.objects.create_user('wall_pc', password='p12345')
        self.assertEqual(wall.pass_contact(user, 'email'), 'email')
        self.assertEqual(wall.pass_contact(user, 'tg'), 'email')
        self.assertEqual(VPWall.objects.get(user=user).contact_via, 'email')


class StudentBandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('wall_band', password='p12345')
        VPWall.objects.create(user=self.user, grade='11')

    def request(self, query=None, session_band=None):
        request = RequestFactory().get('/vp/', query or {})
        request.user = self.user
        request.session = SessionStore()
        if session_band:
            request.session['vp_band'] = session_band
        return request

    def test_survey_grade_when_nothing_chosen(self):
        self.assertEqual(landing.student_band(self.request()), '11')

    def test_tab_choice_in_session_beats_survey(self):
        self.assertEqual(landing.student_band(self.request(session_band='10')), '10')

    def test_explicit_band_beats_everything(self):
        self.assertEqual(landing.student_band(self.request({'band': '9'})), '9')


class WallCheckTests(TestCase):
    FULL = dict(DEBUG=False, VP_WALL_ENABLED=True, TELEGRAM_BOT_TOKEN='000:t',
                TELEGRAM_BOT_USERNAME='b', TELEGRAM_WEBHOOK_SECRET='s', MAIL_ENABLED=True)

    def test_warning_when_token_is_empty(self):
        with override_settings(**{**self.FULL, 'TELEGRAM_BOT_TOKEN': ''}):
            found = checks.wall_paths_configured(None)
        self.assertEqual([w.id for w in found], ['vp.W001'])
        self.assertIn('TELEGRAM_BOT_TOKEN', found[0].msg)

    def test_silent_when_everything_is_set(self):
        with override_settings(**self.FULL):
            self.assertEqual(checks.wall_paths_configured(None), [])
