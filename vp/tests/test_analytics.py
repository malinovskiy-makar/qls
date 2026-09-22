"""Аналитика раздела: события страниц, отправка через существующий `/api/track/`, воронка
(сессия 4, ADR 0127).

События считает сервер и кладёт в контекст (`vp_events`), браузер отдаёт их `weco.track`.
Здесь проверяется серверная половина целиком: что положено, когда и сколько раз, что
положенное принимает настоящий `/api/track/` и что по записанному считается воронка.
Клики «Поделиться» и «Дорешать» шлёт `result.js` — их проверяет браузерный раннер.
"""
import io
import json
import re
from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models_platform import Event
from vp.funnel import funnel
from vp.models import VPAttempt
from vp.tests.helpers import at
from vp.tests.test_review import chain_word, make_review_variant

User = get_user_model()

T0 = datetime(2026, 9, 26, 10, 0, 0, tzinfo=dt_timezone.utc)
EVENTS_JSON = re.compile(r'<script id="vp-events" type="application/json">(.*?)</script>', re.S)
VISITOR = '0f8fad5b-d9cb-469f-a165-70867728950e'


def events_in(html):
    """События, как они лежат в разметке страницы (то, что прочтёт `vp/js/track.js`)."""
    found = EVENTS_JSON.search(html)
    return json.loads(found.group(1)) if found else []


class EventsBase(TestCase):
    def setUp(self):
        cache.clear()
        self.variant = make_review_variant('vp-an')
        # Стена регистрации (22.09.2026): старт и сдача бывают только у вошедшего,
        # поэтому и воронка меряется на нём. Посадочную по-прежнему смотрит любой.
        self.guest = Client()
        self.guest.force_login(
            get_user_model().objects.create_user('vp_an', password='p12345'))

    def start(self, client=None, **post):
        client = client or self.guest
        response = client.post(reverse('vp:start', args=['vp-an']), post)
        self.assertEqual(response.status_code, 302)
        return VPAttempt.objects.order_by('-id').first()

    def get(self, name, *args, client=None):
        response = (client or self.guest).get(reverse(name, args=args))
        self.assertEqual(response.status_code, 200)
        return response

    def submit_with(self, answers, client=None, **post):
        """Сдача через настоящие ручки: сохранение пачкой, потом «Сдать»."""
        client = client or self.guest
        attempt = VPAttempt.objects.order_by('-id').first()
        if answers:
            client.post(reverse('vp:save', args=[attempt.public_code]),
                        json.dumps({'answers': [{'item': n, 'raw': raw} for n, raw in answers.items()]}),
                        content_type='application/json')
        response = client.post(reverse('vp:finish', args=[attempt.public_code]), post)
        self.assertRedirects(response, reverse('vp:result', args=[attempt.public_code]),
                             fetch_redirect_response=False)
        attempt.refresh_from_db()
        return attempt


class PageEventsTests(EventsBase):
    def test_landing_open(self):
        response = self.get('vp:index')
        self.assertEqual(response.context['vp_events'], [{'name': 'vp_landing_open', 'props': {}}])
        self.assertEqual(events_in(response.content.decode()), response.context['vp_events'])

    def test_intro_open_carries_the_variant(self):
        response = self.get('vp:intro', 'vp-an')
        self.assertEqual(response.context['vp_events'],
                         [{'name': 'vp_intro_open', 'props': {'variant': 'vp-an'}}])

    def test_start_is_reported_by_the_take_page_and_only_once(self):
        attempt = self.start(with_timer='0')
        first = self.get('vp:take', attempt.public_code)
        self.assertEqual(events_in(first.content.decode()),
                         [{'name': 'vp_start', 'props': {'variant': 'vp-an', 'with_timer': False}}])
        self.assertEqual(self.get('vp:take', attempt.public_code).context['vp_events'], [])   # перезагрузка

    def test_start_with_timer_says_so(self):
        attempt = self.start(with_timer='1')
        events = self.get('vp:take', attempt.public_code).context['vp_events']
        self.assertEqual(events[0]['props']['with_timer'], True)

    def test_resuming_an_unfinished_attempt_is_not_a_new_start(self):
        attempt = self.start(with_timer='1')
        self.get('vp:take', attempt.public_code)                                 # первый показ забрал событие
        again = self.start(with_timer='0')                                       # «Продолжить вариант»
        self.assertEqual(again.pk, attempt.pk)
        self.assertEqual(self.get('vp:take', attempt.public_code).context['vp_events'], [])

    def test_pages_without_events_do_not_carry_the_script(self):
        attempt = self.start()
        self.get('vp:take', attempt.public_code)                                 # событие забрано
        html = self.get('vp:take', attempt.public_code).content.decode()
        self.assertNotIn('id="vp-events"', html)
        self.assertIn('vp/js/take.js', html)                                     # свои скрипты на месте

    def test_take_page_keeps_its_own_scripts_next_to_the_events_script(self):
        attempt = self.start()
        html = self.get('vp:take', attempt.public_code).content.decode()
        for script in ('vp/js/track.js', 'vp/js/take.js', 'platform/exam_timer.js'):
            self.assertIn(script, html)


class SubmitAndResultEventsTests(EventsBase):
    def result(self, attempt, client=None):
        return self.get('vp:result', attempt.public_code, client=client)

    def test_submit_event_has_the_score_answers_time_and_auto(self):
        with at(T0):
            attempt = self.start(with_timer='1')
        with at(T0 + timedelta(seconds=754)):
            attempt = self.submit_with({1: chain_word(1), 2: chain_word(2), 3: 'мимо'})
            events = self.result(attempt).context['vp_events']
        submit, opened = events
        self.assertEqual(submit['name'], 'vp_submit')
        self.assertEqual(submit['props'], {
            'variant': 'vp-an', 'score': 4.0, 'answered': 3, 'seconds_used': 754, 'auto': False})
        self.assertEqual(opened, {'name': 'vp_result_open', 'props': {'variant': 'vp-an', 'own': True}})

    def test_submit_is_reported_once_per_browser_the_open_is_reported_every_time(self):
        attempt = self.start()
        attempt = self.submit_with({1: chain_word(1)})
        first = [e['name'] for e in self.result(attempt).context['vp_events']]
        second = [e['name'] for e in self.result(attempt).context['vp_events']]
        self.assertEqual(first, ['vp_submit', 'vp_result_open'])
        self.assertEqual(second, ['vp_result_open'])

    def test_auto_submit_reports_the_whole_limit_as_time_used(self):
        with at(T0):
            attempt = self.start(with_timer='1')
        with at(T0 + timedelta(hours=1)):
            self.guest.get(reverse('vp:take', args=[attempt.public_code]))       # ленивая автосдача
            events = self.result(attempt).context['vp_events']
        self.assertEqual(events[0]['props']['auto'], True)
        self.assertEqual(events[0]['props']['seconds_used'], 1800)
        self.assertEqual(events[0]['props']['answered'], 0)

    def test_untimed_attempt_reports_the_real_time(self):
        with at(T0):
            attempt = self.start(with_timer='0')
        with at(T0 + timedelta(seconds=5400)):
            attempt = self.submit_with({})
            events = self.result(attempt).context['vp_events']
        self.assertEqual(events[0]['props']['seconds_used'], 5400)
        self.assertEqual(events[0]['props']['auto'], False)

    def test_a_stranger_opening_a_shared_result_reports_only_the_open_and_not_as_own(self):
        attempt = self.start()
        attempt = self.submit_with({1: chain_word(1)})
        stranger = Client()
        events = self.result(attempt, client=stranger).context['vp_events']
        self.assertEqual(events, [{'name': 'vp_result_open', 'props': {'variant': 'vp-an', 'own': False}}])

    def test_the_stranger_does_not_use_up_the_owners_submit_event(self):
        attempt = self.start()
        attempt = self.submit_with({})
        self.result(attempt, client=Client())
        self.assertEqual([e['name'] for e in self.result(attempt).context['vp_events']],
                         ['vp_submit', 'vp_result_open'])

    def test_events_carry_no_names_no_codes_no_answers(self):
        user = User.objects.create_user('vp_evt_login', password='p12345', first_name='Лев', last_name='Тайный')
        client = Client()
        client.force_login(user)
        attempt = self.start(client)
        attempt = self.submit_with({1: chain_word(1)}, client=client)
        html = self.result(attempt, client=client).content.decode()
        payload = json.dumps(events_in(html), ensure_ascii=False)
        for private in ('vp_evt_login', 'Лев', 'Тайный', attempt.public_code, chain_word(1)):
            self.assertNotIn(private, payload)


class ThroughTheExistingEndpointTests(EventsBase):
    """События страниц принимает существующий `/api/track/`: своего эндпоинта раздел не заводит."""

    def send(self, client, html, path):
        events = [{'name': e['name'], 'path': path, 'props': e['props']} for e in events_in(html)]
        client.cookies['weco_vid'] = VISITOR
        response = client.post('/api/track/', json.dumps({'events': events}),
                               content_type='application/json', HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_events_from_the_pages_are_stored_with_their_props(self):
        html = self.get('vp:index').content.decode()
        self.send(self.guest, html, '/vp/')
        attempt = self.start(with_timer='1')
        self.send(self.guest, self.get('vp:take', attempt.public_code).content.decode(), f'/vp/a/{attempt.public_code}/')
        attempt = self.submit_with({1: chain_word(1)})
        self.send(self.guest, self.get('vp:result', attempt.public_code).content.decode(), f'/vp/r/{attempt.public_code}/')
        names = list(Event.objects.order_by('pk').values_list('name', flat=True))
        self.assertEqual(names, ['vp_landing_open', 'vp_start', 'vp_submit', 'vp_result_open'])
        submit = Event.objects.get(name='vp_submit')
        self.assertEqual(submit.props['variant'], 'vp-an')
        self.assertEqual(submit.props['score'], 2.0)
        self.assertEqual(submit.props['answered'], 1)
        self.assertIs(submit.props['auto'], False)
        self.assertIsInstance(submit.props['seconds_used'], int)
        start = Event.objects.get(name='vp_start')
        self.assertIs(start.props['with_timer'], True)
        self.assertEqual(Event.objects.get(name='vp_result_open').props['own'], True)


def track(name, visitor, ts=None, **props):
    event = Event.objects.create(name=name, visitor=visitor, path='/vp/', page_key='vp', props=props)
    if ts is not None:
        Event.objects.filter(pk=event.pk).update(ts=ts)
    return event


class FunnelTests(TestCase):
    def setUp(self):
        # А: посадочная дважды → старт → сдача. Б: посадочная → старт, не сдал. В: посадочная,
        # ушёл. Г: пришёл по прямой ссылке на вариант — старт и сдача без посадочной.
        for name in ('vp_landing_open', 'vp_landing_open', 'vp_start', 'vp_submit'):
            track(name, 'A')
        track('vp_landing_open', 'B')
        track('vp_start', 'B')
        track('vp_landing_open', 'V')
        track('vp_start', 'G')
        track('vp_submit', 'G')
        track('vp_result_open', 'A')                                              # не шаг воронки

    def test_counts_people_not_events(self):
        self.assertEqual(funnel(), {
            'landing': 3, 'start': 3, 'submit': 2, 'landing_and_start': 2, 'start_and_submit': 2})

    def test_landing_to_start_and_start_to_submit_are_separate_transitions(self):
        data = funnel()
        self.assertEqual(round(100 * data['landing_and_start'] / data['landing']), 67)      # А и Б из А, Б, В
        self.assertEqual(round(100 * data['start_and_submit'] / data['start']), 67)         # А и Г из А, Б, Г

    def test_period_bounds(self):
        Event.objects.all().delete()
        track('vp_landing_open', 'old', ts=T0 - timedelta(days=3))
        track('vp_landing_open', 'new', ts=T0)
        track('vp_start', 'new', ts=T0)
        self.assertEqual(funnel(since=T0)['landing'], 1)
        self.assertEqual(funnel(until=T0)['landing'], 1)
        self.assertEqual(funnel(since=T0 - timedelta(days=4), until=T0 + timedelta(seconds=1))['landing'], 2)

    def test_the_command_prints_the_funnel(self):
        out = io.StringIO()
        call_command('vp_funnel', stdout=out)
        text = out.getvalue()
        self.assertIn('Открыли посадочную:        3', text)
        self.assertIn('Начали вариант:            3  (из открывших посадочную: 2, 67 %)', text)
        self.assertIn('Сдали вариант:             2  (из начавших: 2, 67 %)', text)

    def test_the_command_takes_dates_and_survives_an_empty_table(self):
        Event.objects.all().delete()
        out = io.StringIO()
        call_command('vp_funnel', since='2026-09-24', until='2026-09-30', stdout=out)
        self.assertIn('Открыли посадочную:        0', out.getvalue())
        self.assertIn('из открывших посадочную: 0, –', out.getvalue())
