# -*- coding: utf-8 -*-
"""Аналитика беты: `/api/track/`, скрипт на страницах, выгрузка (15.09.2026).

Границы доступа (скилл weco-security-boundary-review):

| ресурс | кто | действие | итог | тест |
|---|---|---|---|---|
| /api/track/ | гость, наш Origin, cookie посетителя | записать | 200, user пуст | test_guest_events_are_saved_with_server_page_key |
| /api/track/ | вошедший | записать | 200, user из сессии, не из тела | test_user_comes_from_the_session |
| /api/track/ | без CSRF-токена (sendBeacon) | записать | 200 | test_works_without_csrf_token |
| /api/track/ | чужой Origin | записать | 403, ничего не записано | test_foreign_origin_is_refused |
| /api/track/ | без Origin и Referer | записать | 403 | test_no_origin_is_refused_but_referer_is_enough |
| /api/track/ | без cookie посетителя | записать | 400 | test_visitor_cookie_is_required |
| /api/track/ | больше 50 событий, мусор | записать | 400 | test_batch_limit_and_bad_body |
| /api/track/ | сверх лимита окна | записать | 429 | test_rate_limit_per_visitor |
| /api/track/ | GET | — | 405 | test_get_is_not_allowed |
| /admin/problems/event/ | вошедший не сотрудник | смотреть | 302 на вход | test_admin_list_is_staff_only |
| /admin/problems/event/ | сотрудник | смотреть | 200 | test_admin_list_is_staff_only |

Наружу вьюха не отдаёт ничего, кроме `{ok, saved}`.
"""
import csv
import io
import json
import os
import tempfile
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from problems.feedback_options import page_key_for
from problems.models import User
from problems.models_platform import Event
from problems.tests.factories import make_problem

URL = '/api/track/'
ORIGIN = 'http://testserver'
VISITOR = '0f8fad5b-d9cb-469f-a165-70867728950e'

TEMPLATES_WITH_FEEDBACK = (
    'calendar_stub/templates/calendar_stub/calendar.html',
    'catalog/templates/catalog/base.html',
    'calc2/templates/calc2/calc2.html',
    'templates/registration/register.html',
    'templates/registration/login.html',
    'teacher/templates/teacher/base.html',
    'student/templates/student/base.html',
    'problems/templates/platform/base.html',
    'game/templates/game/game.html',
)


class TrackApiTests(TestCase):

    def setUp(self):
        cache.clear()
        self.client.cookies['weco_vid'] = VISITOR

    def post(self, events, client=None, **headers):
        headers.setdefault('HTTP_ORIGIN', ORIGIN)
        return (client or self.client).post(URL, json.dumps({'events': events}),
                                            content_type='application/json', **headers)

    def test_guest_events_are_saved_with_server_page_key(self):
        response = self.post([{'name': 'page_view', 'path': '/catalog/?q=налог',
                               'props': {'referrer': ''}, 'viewport': '1280x800',
                               'page_key': 'admin'}])
        self.assertEqual(response.status_code, 200)
        event = Event.objects.get()
        self.assertEqual((event.name, event.path, event.visitor),
                         ('page_view', '/catalog/', VISITOR))
        self.assertEqual(event.page_key, page_key_for('/catalog/'))
        self.assertIsNone(event.user)

    def test_user_comes_from_the_session(self):
        user = User.objects.create_user(username='beta', password='pw12345')
        self.client.force_login(user)
        self.client.cookies['weco_vid'] = VISITOR
        self.post([{'name': 'click', 'path': '/game/', 'props': {'text': 'Играть'},
                    'user': 999}])
        self.assertEqual(Event.objects.get().user, user)

    def test_works_without_csrf_token(self):
        strict = self.client_class(enforce_csrf_checks=True)
        strict.cookies['weco_vid'] = VISITOR
        self.assertEqual(self.post([{'name': 'page_leave', 'path': '/', 'duration_ms': 1200}],
                                   client=strict).status_code, 200)
        self.assertEqual(Event.objects.get().duration_ms, 1200)

    def test_foreign_origin_is_refused(self):
        response = self.post([{'name': 'click', 'path': '/'}],
                             HTTP_ORIGIN='https://evil.example')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Event.objects.exists())

    def test_no_origin_is_refused_but_referer_is_enough(self):
        body = json.dumps({'events': [{'name': 'click', 'path': '/'}]})
        self.assertEqual(self.client.post(URL, body, content_type='application/json')
                         .status_code, 403)
        self.assertEqual(self.client.post(URL, body, content_type='application/json',
                                          HTTP_REFERER='http://testserver/catalog/')
                         .status_code, 200)

    def test_visitor_cookie_is_required(self):
        anonymous = self.client_class()
        self.assertEqual(self.post([{'name': 'click', 'path': '/'}], client=anonymous)
                         .status_code, 400)

    def test_batch_limit_and_bad_body(self):
        self.assertEqual(self.post([{'name': 'click', 'path': '/'}] * 51).status_code, 400)
        self.assertEqual(self.client.post(URL, 'не json', content_type='application/json',
                                          HTTP_ORIGIN=ORIGIN).status_code, 400)
        self.assertFalse(Event.objects.exists())

    def test_long_props_are_trimmed_not_refused(self):
        props = {'k%02d' % i: 'x' * 250 for i in range(20)}
        self.assertEqual(self.post([{'name': 'click', 'path': '/', 'props': props}])
                         .status_code, 200)
        saved = Event.objects.get().props
        self.assertTrue(saved, 'props обнулились целиком')
        self.assertLessEqual(len(json.dumps(saved, ensure_ascii=False)), 2000)

    def test_rate_limit_per_visitor(self):
        with mock.patch('problems.views_platform.TRACK_LIMIT', 3):
            self.assertEqual(self.post([{'name': 'a', 'path': '/'}] * 2).status_code, 200)
            self.assertEqual(self.post([{'name': 'b', 'path': '/'}] * 2).status_code, 429)
        self.assertEqual(Event.objects.count(), 2)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


class EventAdminTests(TestCase):

    def test_admin_list_is_staff_only(self):
        Event.objects.create(visitor=VISITOR, page_key='home', path='/', name='page_view')
        url = '/admin/problems/event/'
        self.client.force_login(User.objects.create_user(username='pupil', password='pw12345'))
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(User.objects.create_user(
            username='boss', password='pw12345', is_staff=True, is_superuser=True))
        self.assertEqual(self.client.get(url).status_code, 200)


class TrackScriptTests(TestCase):

    def test_every_template_with_feedback_includes_tracking(self):
        found = []
        for root in ('calendar_stub', 'catalog', 'calc2', 'templates', 'teacher',
                     'student', 'problems', 'game'):
            for folder, _dirs, files in os.walk(root):
                for name in files:
                    if not name.endswith('.html'):
                        continue
                    path = os.path.join(folder, name)
                    with open(path, encoding='utf-8') as handle:
                        text = handle.read()
                    if "{% include '_feedback.html' %}" in text:
                        found.append(path.replace(os.sep, '/'))
                        self.assertTrue("{% include '_track.html' %}" in text,
                                        'нет аналитики в %s' % path)
        self.assertEqual(sorted(found), sorted(TEMPLATES_WITH_FEEDBACK))

    def test_login_page_serves_the_script(self):
        self.assertTrue('track.js' in self.client.get('/login/').content.decode('utf-8'),
                        'скрипт не подключён на входе')

    def test_script_uses_beacon_cookie_and_capture_phase(self):
        with open('static/track.js', encoding='utf-8') as handle:
            source = handle.read()
        self.assertTrue('navigator.sendBeacon' in source)
        self.assertTrue('keepalive: true' in source)
        self.assertTrue('weco_vid=' in source)
        self.assertTrue('}, true);' in source, 'клики не в фазе перехвата')
        self.assertLessEqual(len(source.splitlines()), 200)

    def test_pages_send_explicit_events(self):
        expected = {
            'game/templates/game/game.html': ('game_start', 'game_answer', 'game_end',
                                              'duel_create'),
            'templates/_feedback.html': ('feedback_send',),
            'templates/_problem_report.html': ('report_send',),
            'catalog/templates/catalog/_catalog_js.html': ('problem_open',),
            'catalog/templates/catalog/problem_detail.html': ('copy_link',),
            'catalog/static/catalog/js/problem_page.js': ('test_answer',),
        }
        for path, names in expected.items():
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
            for name in names:
                with self.subTest(path=path, event=name):
                    self.assertTrue("weco.track('%s'" % name in text, 'нет события')


@override_settings(SEMANTIC_SEARCH_ENABLED=False, SMART_SEARCH_RERANK=False)
class SearchStateAttributesTests(TestCase):

    def test_search_results_carry_state_for_the_tracker(self):
        problem = make_problem('Налог на монополиста.')
        with mock.patch('catalog.views._search_ids', return_value=([problem.pk], {}, True)):
            html = self.client.get('/catalog/', {'q': 'налог'}).content.decode('utf-8')
        self.assertTrue('data-search-status="off"' in html, 'нет статуса поиска')
        self.assertTrue('data-search-total="1"' in html, 'нет числа найденного')
        self.assertTrue('data-search-degraded' in html, 'нет признака поиска по словам')

    def test_plain_catalog_has_no_search_state(self):
        self.assertFalse('data-search-status' in
                         self.client.get('/catalog/').content.decode('utf-8'))


class AnalyticsExportTests(TestCase):

    def export(self, **options):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'events.csv')
            call_command('analytics_export', out=out, stdout=io.StringIO(), **options)
            with open(out, encoding='utf-8-sig', newline='') as handle:
                return list(csv.reader(handle))

    def test_writes_csv_with_props_as_json(self):
        Event.objects.create(visitor=VISITOR, page_key='catalog', path='/catalog/',
                             name='search', props={'q_len': 5})
        rows = self.export(since='2020-01-01')
        self.assertEqual(rows[0][:3], ['ts', 'name', 'page_key'])
        self.assertEqual(rows[1][1], 'search')
        self.assertEqual(json.loads(rows[1][-1]), {'q_len': 5})

    def test_formula_like_cells_are_neutralised(self):
        Event.objects.create(visitor='-12345678', page_key='home', path='=cmd|x',
                             name='=HYPERLINK("http://evil")', user_agent='@SUM(1)')
        row = self.export(since='2020-01-01')[1]
        self.assertEqual(row[1], '\'=HYPERLINK("http://evil")')
        self.assertEqual(row[3], "'=cmd|x")
        self.assertEqual(row[5], "'-12345678")
        self.assertEqual(row[9], "'@SUM(1)")

    def test_until_leaves_out_later_days(self):
        event = Event.objects.create(visitor=VISITOR, page_key='home', path='/',
                                     name='page_view')
        Event.objects.filter(pk=event.pk).update(ts='2026-09-20T12:00:00+03:00')
        self.assertEqual(len(self.export(since='2026-09-01', until='2026-09-15')), 1)
