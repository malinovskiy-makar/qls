# -*- coding: utf-8 -*-
"""Журнал поиска каталога и оценка выдачи (18.09.2026, ADR 0117).

⚠️ ГЛАВНЫЙ ИНВАРИАНТ: один поиск человека — одна строка журнала, сколько бы
раз он ни щёлкал фильтры под тем же запросом. Контекст каталога собирается
одним кодом для страницы и для живого обновления фильтров; пиши журнал оба,
нажатие фильтра стало бы строкой.
"""
import csv
import io
import os
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from catalog import search_log
from problems.management.commands.search_export import COLUMNS
from problems.models import User
from problems.models_platform import SearchLog
from problems.tests.factories import make_problem, make_topic

VISITOR = 'visitor-aaaa-1111'
OTHER_VISITOR = 'visitor-bbbb-2222'


class _Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mon = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        cls.el = make_topic('Эластичность', is_canonical=True)
        cls.p1 = make_problem('Монополист с двумя заводами.', topic=cls.mon, difficulty=4)
        cls.p2 = make_problem('Монополист и спрос.', topic=cls.el, difficulty=5)
        cls.hidden = make_problem('Скрытая монополия.', topic=cls.mon, flagged=True)

    def setUp(self):
        self.client.cookies['weco_vid'] = VISITOR
        # Поиск подменён: проверяется журнал, а не ранжирование. Скрытая
        # задача стоит первой — шлюз качества обязан её выбросить.
        patcher = mock.patch('catalog.views._search_ids', return_value=(
            [self.hidden.pk, self.p1.pk, self.p2.pk], {}, True))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _page(self, q='монополия', **params):
        return self.client.get('/catalog/', dict(params, q=q))

    def _live(self, q='монополия', **params):
        return self.client.get(reverse('catalog:api_filter_state'), dict(params, q=q))


class SearchLogWriteTests(_Fixture):

    def test_full_render_writes_one_row_with_the_query(self):
        self._page()
        row = SearchLog.objects.get()
        self.assertEqual((row.query, row.visitor, row.degraded), ('монополия', VISITOR, True))
        self.assertEqual(row.total, 2)
        self.assertLessEqual(len(row.top_ids), search_log.TOP_IDS)

    def test_five_live_filter_clicks_add_no_rows(self):
        self._page()
        for params in ({'topic': self.mon.pk}, {'difficulty': 4}, {'topic': self.el.pk},
                       {'difficulty': 5}, {}):
            self._live(**params)
        self.assertEqual(SearchLog.objects.count(), 1)

    def test_same_query_within_thirty_seconds_is_glued(self):
        self._page()
        self._page(q='  Монополия ')
        self.assertEqual(SearchLog.objects.count(), 1)

    def test_same_query_after_thirty_seconds_is_a_new_row(self):
        self._page()
        SearchLog.objects.update(ts=SearchLog.objects.get().ts - timedelta(seconds=31))
        self._page()
        self.assertEqual(SearchLog.objects.count(), 2)

    def test_another_query_is_a_new_row(self):
        self._page()
        self._page(q='эластичность')
        self.assertEqual(SearchLog.objects.count(), 2)

    def test_live_state_writes_only_on_explicit_log_param(self):
        self._live(log='1')
        self._live(log='1', topic=self.mon.pk)
        self.assertEqual(SearchLog.objects.count(), 1)

    def test_guest_without_cookie_gets_an_empty_visitor(self):
        self.client.cookies.clear()
        self._page()
        self.assertEqual(SearchLog.objects.get().visitor, '')

    def test_flagged_problem_never_reaches_top_ids(self):
        self._page()
        self.assertEqual(SearchLog.objects.get().top_ids, [self.p1.pk, self.p2.pk])

    def test_results_carry_the_log_number_when_searching(self):
        html = self._page().content.decode('utf-8')
        self.assertIn('data-search-log="%d"' % SearchLog.objects.get().pk, html)

    def test_results_have_no_log_number_without_a_query(self):
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertNotIn('data-search-log="', html)
        self.assertEqual(SearchLog.objects.count(), 0)


class SearchRatingTests(_Fixture):

    def setUp(self):
        super().setUp()
        self._page()
        self.row = SearchLog.objects.get()

    def _rate(self, **data):
        payload = {'log': self.row.pk, 'rating': 'no'}
        payload.update(data)
        return self.client.post('/api/search-rating/', payload)

    def test_own_row_is_rated(self):
        self.assertEqual(self._rate(text='Нет задач про картель').status_code, 200)
        self.row.refresh_from_db()
        self.assertEqual((self.row.rating, self.row.rating_text), ('no', 'Нет задач про картель'))
        self.assertIsNotNone(self.row.rated_at)

    def test_someone_elses_row_is_not_found(self):
        self.client.cookies['weco_vid'] = OTHER_VISITOR
        self.assertEqual(self._rate().status_code, 404)
        self.row.refresh_from_db()
        self.assertEqual(self.row.rating, '')

    def test_missing_row_is_not_found(self):
        self.assertEqual(self._rate(log=self.row.pk + 999).status_code, 404)

    def test_second_rating_overwrites_the_first(self):
        self._rate(rating='no')
        self._rate(rating='yes', text='')
        self.row.refresh_from_db()
        self.assertEqual((self.row.rating, self.row.rating_text), ('yes', ''))
        self.assertEqual(SearchLog.objects.count(), 1)

    def test_text_over_three_hundred_is_refused(self):
        self.assertEqual(self._rate(text='я' * 301).status_code, 400)

    def test_unknown_rating_is_refused(self):
        self.assertEqual(self._rate(rating='maybe').status_code, 400)

    def test_logged_in_owner_can_rate_from_another_browser(self):
        user = User.objects.create_user(username='sr_user', password='sr-pass-2026-x')
        self.client.force_login(user)
        self.client.cookies['weco_vid'] = OTHER_VISITOR
        self._page(q='картель')
        row = SearchLog.objects.get(query='картель')
        self.client.cookies['weco_vid'] = 'visitor-cccc-3333'
        self.assertEqual(self._rate(log=row.pk).status_code, 200)

    def test_rating_needs_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        strict.cookies['weco_vid'] = VISITOR
        response = strict.post('/api/search-rating/', {'log': self.row.pk, 'rating': 'yes'})
        self.assertEqual(response.status_code, 403)


class SearchExportTests(_Fixture):

    def test_export_writes_header_rows_and_cuts_by_since(self):
        self._page()
        self._page(q='эластичность')
        old = SearchLog.objects.get(query='монополия')
        SearchLog.objects.filter(pk=old.pk).update(ts=old.ts - timedelta(days=10))
        handle, out = tempfile.mkstemp(suffix='.csv')
        os.close(handle)
        self.addCleanup(os.remove, out)
        since = (SearchLog.objects.get(query='эластичность').ts
                 - timedelta(days=1)).strftime('%Y-%m-%d')
        call_command('search_export', since=since, out=out, stdout=io.StringIO())
        with open(out, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))
        self.assertEqual(tuple(rows[0]), COLUMNS)
        self.assertEqual([r[3] for r in rows[1:]], ['эластичность'])
        self.assertEqual(rows[1][-1], '%d|%d' % (self.p1.pk, self.p2.pk))


class SearchRatingCardTests(_Fixture):
    """Плашка на странице выдачи: разметка, правила показа — одно место."""

    def test_catalog_page_carries_the_card_and_the_corner_stack(self):
        html = self._page().content.decode('utf-8')
        self.assertIn('id="sr-card-tpl"', html)
        self.assertIn('id="corner-stack"', html)
        self.assertIn('Нашли, что искали?', html)

    def test_show_rule_is_every_third_search_and_twenty_minutes(self):
        src = io.open('templates/_search_rating.html', encoding='utf-8').read()
        self.assertIn('var EVERY_NTH = 3;', src)
        self.assertIn('var PAUSE_MS = 20 * 60 * 1000;', src)
        self.assertIn('var DWELL_MS = 15 * 1000;', src)
        self.assertIn('s.n % EVERY_NTH === 0 && now - s.last >= PAUSE_MS', src)
