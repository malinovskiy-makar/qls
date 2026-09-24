# -*- coding: utf-8 -*-
"""Бот тратит $0 при любом User-Agent и любом адресе (24.09.2026, ADR 0128).

Инвариант фазы: платный вызов переранжирования делает ТОЛЬКО запрос
собственного скрипта страницы — с заголовком `X-Weco-Search: 1`, кукой
посетителя и User-Agent не бота, в пределах квот и суточного потолка.
Полная загрузка `/catalog/?q=` и `/catalog/map/?q=` не платит никогда.
"""
import importlib
import json
import logging
import time
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from catalog import rerank, rerank_gate
from catalog.tests.test_rerank import _FakeProvider, _FakeReply, _row
from problems.models import AiUsageLog
from problems.models_platform import SearchLog
from problems.tests.factories import make_problem, make_topic, make_user

BROWSER = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36')
GOOGLEBOT = ('Mozilla/5.0 (compatible; Googlebot/2.1; '
             '+http://www.google.com/bot.html)')
VISITOR = '0f8fad5b-d9cb-469f-a165-70867728950e'


@override_settings(SMART_SEARCH_RERANK=True)
class _Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        topic = make_topic('Монополия и ценовая дискриминация')
        cls.problems = [make_problem('Монополист выбирает цену %d.' % i,
                                     title='Монополия %d' % i, topic=topic)
                        for i in range(3)]

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.ids = [p.pk for p in self.problems]

    def _api(self, agent=BROWSER, header=True, cookie=True, q='монополист'):
        extra = {}
        if agent is not None:
            extra['HTTP_USER_AGENT'] = agent
        if header:
            extra['HTTP_X_WECO_SEARCH'] = '1'
        if cookie:
            self.client.cookies['weco_vid'] = VISITOR
        with mock.patch('catalog.views._search_ids', return_value=(self.ids, {}, False)), \
                mock.patch('catalog.rerank.apply', return_value=(self.ids[::-1], 'rerank')) as apply:
            response = self.client.get(reverse('catalog:api_filter_state'), {'q': q}, **extra)
        return response, apply


class WhoMayPayTests(_Base):

    def test_everything_in_place_pays(self):
        response, apply = self._api()
        apply.assert_called_once()
        self.assertEqual(response['X-Smart-Search'], 'rerank')

    def test_crawler_user_agent_never_pays(self):
        response, apply = self._api(agent=GOOGLEBOT)
        apply.assert_not_called()
        self.assertEqual(response['X-Smart-Search'], 'bot')

    def test_empty_user_agent_never_pays(self):
        for agent in (None, ''):
            response, apply = self._api(agent=agent)
            apply.assert_not_called()
            self.assertEqual(response['X-Smart-Search'], 'bot')

    def test_without_page_script_header_never_pays(self):
        response, apply = self._api(header=False)
        apply.assert_not_called()
        self.assertEqual(response['X-Smart-Search'], 'deferred')

    def test_without_visitor_cookie_never_pays(self):
        response, apply = self._api(cookie=False)
        apply.assert_not_called()
        self.assertEqual(response['X-Smart-Search'], 'bot')

    def test_full_page_loads_never_pay_whoever_asks(self):
        for url in (reverse('catalog:problem_list'), reverse('catalog:topic_map')):
            for agent in (BROWSER, GOOGLEBOT, ''):
                with self.subTest(url=url, agent=agent), \
                        mock.patch('catalog.views._search_ids', return_value=(self.ids, {}, False)), \
                        mock.patch('catalog.rerank.apply') as apply:
                    response = self.client.get(url, {'q': 'монополист'},
                                               HTTP_USER_AGENT=agent, HTTP_X_WECO_SEARCH='1')
                    self.assertEqual(response.status_code, 200)
                    apply.assert_not_called()
                    expected = 'bot' if agent == GOOGLEBOT else 'deferred'
                    self.assertEqual(response['X-Smart-Search'], expected)

    def test_deferred_page_asks_the_script_and_sets_the_visitor_cookie(self):
        with mock.patch('catalog.views._search_ids', return_value=(self.ids, {}, False)):
            response = self.client.get(reverse('catalog:problem_list'), {'q': 'монополист'},
                                       HTTP_USER_AGENT=BROWSER)
        self.assertIn('data-search-deferred', response.content.decode())
        self.assertIn('weco_vid', response.cookies)
        # Строку журнала пишет запрос скрипта — уже с настоящим статусом.
        self.assertEqual(SearchLog.objects.count(), 0)

    def test_map_with_query_is_noindex(self):
        html = self.client.get(reverse('catalog:topic_map'), {'q': 'монополист'}).content.decode()
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
        plain = self.client.get(reverse('catalog:topic_map')).content.decode()
        self.assertNotIn('noindex', plain)


class QuotaTests(_Base):
    """Квоты считают только реально оплаченные вызовы; кэш — бесплатно."""

    def _request(self, user=None, ip='5.6.7.8', visitor=VISITOR):
        request = RequestFactory().get('/catalog/api/filter-state/', HTTP_X_REAL_IP=ip,
                                       HTTP_USER_AGENT=BROWSER, HTTP_X_WECO_SEARCH='1')
        request.COOKIES['weco_vid'] = visitor
        request.user = user or AnonymousUser()
        return request

    def _apply(self, request, query, runs):
        def fake_run(q):
            runs.append(q)
            return rerank.RerankResult([2, 1], 'rerank')
        with mock.patch.object(rerank, '_run', side_effect=fake_run):
            return rerank.apply(request.user, query, request=request)

    @override_settings(SMART_SEARCH_QUOTA_VISITOR=2)
    def test_visitor_quota(self):
        runs = []
        for n in range(2):
            self.assertEqual(self._apply(self._request(), 'запрос %d' % n, runs)[1], 'rerank')
        self.assertEqual(self._apply(self._request(), 'третий', runs), (None, 'quota'))
        self.assertEqual(len(runs), 2)
        # Повтор уже оплаченного — из кэша, квоту не тратит и проходит.
        self.assertEqual(self._apply(self._request(), 'запрос 0', runs)[1], 'rerank')
        self.assertEqual(len(runs), 2)
        # Другой посетитель с другого адреса — свои счётчики.
        other = self._request(ip='9.9.9.9', visitor='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee')
        self.assertEqual(self._apply(other, 'четвёртый', runs)[1], 'rerank')

    @override_settings(SMART_SEARCH_QUOTA_VISITOR=1, SMART_SEARCH_QUOTA_USER=3)
    def test_signed_in_user_has_own_larger_quota(self):
        user = make_user('quota_user')
        runs = []
        for n in range(3):
            self.assertEqual(self._apply(self._request(user=user), 'у %d' % n, runs)[1], 'rerank')
        self.assertEqual(self._apply(self._request(user=user), 'у 3', runs), (None, 'quota'))

    @override_settings(SMART_SEARCH_QUOTA_IP=2, SMART_SEARCH_QUOTA_VISITOR=100)
    def test_ip_quota_across_visitors(self):
        runs = []
        for n in range(2):
            visitor = 'vvvvvvvv-%04d-4ccc-8ddd-eeeeeeeeeeee' % n
            self.assertEqual(self._apply(self._request(visitor=visitor), 'ip %d' % n, runs)[1], 'rerank')
        last = self._request(visitor='zzzzzzzz-bbbb-4ccc-8ddd-eeeeeeeeeeee')
        self.assertEqual(self._apply(last, 'ip 2', runs), (None, 'quota'))


class SharedCacheTests(_Base):

    def test_repeat_after_worker_restart_does_not_pay_again(self):
        runs = []

        def fake_run(q):
            runs.append(q)
            return rerank.RerankResult([2, 1], 'rerank')

        with mock.patch.object(rerank, '_run', side_effect=fake_run):
            rerank.rerank('Монополия')
        # «Перезапуск воркера»: модуль загружается заново, память процесса
        # о прежних запросах теряется; общий кэш (Redis) — нет.
        importlib.reload(rerank)
        with mock.patch.object(rerank, '_run', side_effect=fake_run):
            second = rerank.rerank('  монополия ')
        self.assertEqual(len(runs), 1)
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.ids, [2, 1])

    def test_failure_is_not_cached(self):
        results = [rerank.RerankResult([], 'fallback', reason='таймаут'),
                   rerank.RerankResult([3, 1], 'rerank')]
        with mock.patch.object(rerank, '_run', side_effect=results) as run:
            first = rerank.rerank('олигополия')
            second = rerank.rerank('олигополия')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(first.status, 'fallback')
        self.assertEqual(second.status, 'rerank')


class SpendTests(_Base):

    @override_settings(SMART_SEARCH_RERANK_BATCH_SIZE=1)
    def test_partial_spend_is_recorded(self):
        """Одна пачка из двух упала — деньги за ответившую в потолке."""
        rows = {1: _row(1), 2: _row(2)}

        def script(system_blocks, user_text, schema, model, max_tokens, timeout):
            if user_text == 'id=2':
                # Падает ПОЗЖЕ ответившей пачки — иначе порядок потоков случаен.
                time.sleep(0.3)
                raise RuntimeError('пачка упала')
            return _FakeReply(json.dumps({'rows': [{'id': 1, 'score': 50},
                                                   {'id': 2, 'score': 40}]}))

        with mock.patch.object(rerank, 'user_text',
                               side_effect=lambda q, cards: 'id=%s' % cards[0]['id']), \
                mock.patch.object(rerank, 'build_pool', return_value=([1, 2], {'bm25': 2}, rows)), \
                mock.patch.object(rerank, '_get_provider', return_value=_FakeProvider(script)):
            result = rerank._run('монополия')
        self.assertEqual(result.status, 'fallback')
        row = AiUsageLog.objects.get(kind=rerank.USAGE_KIND)
        self.assertGreater(row.cost_usd, 0)

    @override_settings(AI_DAILY_COST_CAPS={'search_rerank': 0.5})
    def test_budget_status_and_one_warning_per_day(self):
        AiUsageLog.objects.create(user=None, kind=rerank.USAGE_KIND, model_name='glm',
                                  cost_usd=Decimal('0.6'))
        request = QuotaTests._request(self)
        with mock.patch.object(rerank, '_run') as run, \
                self.assertLogs('catalog.rerank_gate', logging.WARNING) as logs:
            self.assertEqual(rerank.apply(request.user, 'первый', request=request), (None, 'budget'))
            self.assertEqual(rerank.apply(request.user, 'второй', request=request), (None, 'budget'))
        run.assert_not_called()
        self.assertEqual(len(logs.records), 1)
        self.assertIn('исчерпан суточный потолок', logs.output[0])

    def test_rerank_spend_command_only_reads(self):
        AiUsageLog.objects.create(user=None, kind=rerank.USAGE_KIND, model_name='glm',
                                  cost_usd=Decimal('0.3'))
        before = AiUsageLog.objects.count()
        out = StringIO()
        call_command('rerank_spend', '--days', '3', stdout=out)
        self.assertIn('0.3000', out.getvalue())
        self.assertEqual(AiUsageLog.objects.count(), before)


class RerankBotTests(TestCase):

    def test_markers(self):
        rf = RequestFactory()
        for agent in ('python-requests/2.31', 'curl/8.4', 'Mozilla/5.0 HeadlessChrome/120',
                      'Mozilla/5.0 (compatible; YandexRenderResourcesBot/1.0)',
                      'TelegramBot (like TwitterBot)', 'Some-Crawler bot/1.0', ''):
            self.assertTrue(rerank_gate.seo.is_rerank_bot(rf.get('/', HTTP_USER_AGENT=agent)), agent)
        self.assertFalse(rerank_gate.seo.is_rerank_bot(rf.get('/', HTTP_USER_AGENT=BROWSER)))
        # Страницу пустой User-Agent получает как все.
        self.assertFalse(rerank_gate.seo.is_crawler(rf.get('/', HTTP_USER_AGENT='')))
