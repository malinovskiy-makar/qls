# -*- coding: utf-8 -*-
u"""Пауза раунда: сервер фиксирует её своими часами, в зачёт — с потолком.

Решение владельца 15.09.2026: раунд с открытым окном (обратная связь,
«Плохая задача?», выход) не снимается с таблицы лидеров. Пауза не «со слов
клиента»: начало и конец пишет сервер, в зачёт — не больше
`PAUSE_CAP_SECONDS` и `PAUSE_MAX_COUNT` пауз.
"""
import json
import os
from unittest import mock

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from game import config, views
from game import state as run_state
from game.models import GameQuestion
from game.tests.test_ranked import make_q
from problems.models import User

T0 = 1_800_000_000_000          # мс: условный момент, дальше только смещения
LIMIT_MS = int((config.MODES['blitz']['duration']
                * (1 + config.TIME_BONUS_CAP_FACTOR) + 60) * 1000)
TEMPLATE = os.path.join(settings.BASE_DIR, 'game', 'templates', 'game', 'game.html')


def at(ms):
    """Часы сервера показывают `ms`."""
    return mock.patch('game.views._now_ms', return_value=ms)


class PauseApiTests(TestCase):

    def setUp(self):
        for _ in range(12):
            make_q()
        started = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        self.assertTrue(started.get('ok'), started)
        self.qid = started['question']['id']

    def post(self, name, body=None):
        return self.client.post(reverse('game:' + name), json.dumps(body or {}),
                                content_type='application/json')

    def state(self):
        return run_state.load_by_id(self.client.session[run_state.RUN_ID_KEY])

    def answer(self):
        gq = GameQuestion.objects.get(id=self.qid)
        return self.post('answer', {'question_id': self.qid,
                                    'choice': gq.correct_index})

    def test_pause_and_resume_are_stamped_by_the_server_clock(self):
        with at(T0):
            self.assertEqual(self.post('pause', {'at': 1}).status_code, 200)
        with at(T0 + 30_000):
            self.assertEqual(self.post('resume', {'at': 999}).status_code, 200)
        self.assertEqual(self.state()['pauses'], [[T0, T0 + 30_000]])

    def test_answer_during_open_pause_is_409_and_closes_it(self):
        with at(T0):
            self.post('pause')
        with at(T0 + 5_000):
            response = self.answer()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['reason'], 'paused')
        self.assertEqual(self.state()['pauses'], [[T0, T0 + 5_000]])
        self.assertEqual(self.state()['answered'], {})
        # Пауза закрыта этим запросом — повтор ответа проходит.
        self.assertEqual(self.answer().status_code, 200)

    def test_question_during_open_pause_is_409(self):
        with at(T0):
            self.post('pause')
        response = self.client.get(reverse('game:question'))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['reason'], 'paused')

    def test_finish_closes_an_open_pause(self):
        with at(T0):
            self.post('pause')
        with at(T0 + 7_000):
            self.post('session_finish', {'reason': 'time'})
        self.assertEqual(self.state()['pauses'], [[T0, T0 + 7_000]])

    def test_clicking_the_window_many_times_does_not_grow_the_state(self):
        for i in range(20):
            with at(T0 + i * 10_000):
                self.post('pause')
            with at(T0 + i * 10_000 + 1_000):
                self.post('resume')
        self.assertEqual(len(self.state()['pauses']), config.PAUSE_MAX_COUNT + 1)

    def test_pause_without_a_round_is_no_run(self):
        response = self.client_class().post(reverse('game:pause'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['reason'], 'no_run')

    def test_pause_needs_csrf_and_post(self):
        strict = self.client_class(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse('game:pause')).status_code, 403)
        self.assertEqual(self.client.get(reverse('game:pause')).status_code, 405)


class CreditedPauseTests(SimpleTestCase):

    def test_credit_is_capped_at_the_ceiling(self):
        state = {'pauses': [[0, 100_000], [200_000, 300_000]]}
        self.assertEqual(views.credited_pause_ms(state),
                         config.PAUSE_CAP_SECONDS * 1000)

    def test_only_the_first_pauses_count(self):
        state = {'pauses': [[i * 10_000, i * 10_000 + 1_000] for i in range(7)]}
        self.assertEqual(views.credited_pause_ms(state),
                         config.PAUSE_MAX_COUNT * 1_000)

    def test_open_pause_is_not_credited(self):
        self.assertEqual(views.credited_pause_ms({'pauses': [[0, None]]}), 0)


class RankWithPauseTests(TestCase):

    def setUp(self):
        self.request = RequestFactory().get('/game/')
        self.request.user = User.objects.create_user(username='igrok',
                                                     password='pw12345')

    def rank(self, pauses, wall_ms):
        state = {'mode': 'blitz', 'filter': {}, 'pauses': pauses}
        return views._rank_run(self.request, state,
                               {'correct': 9, 'wrong': 1}, wall_ms)

    def test_thirty_second_pause_keeps_a_twenty_second_overrun_on_the_board(self):
        self.assertEqual(self.rank([[0, 30_000]], LIMIT_MS + 20_000), (True, ''))
        self.assertEqual(self.rank([], LIMIT_MS + 20_000), (False, 'time_overrun'))

    def test_pause_beyond_the_ceiling_does_not_help(self):
        self.assertEqual(self.rank([[0, 600_000]], LIMIT_MS + 121_000),
                         (False, 'time_overrun'))
        self.assertEqual(self.rank([[0, 600_000]], LIMIT_MS + 119_000), (True, ''))


class ClientPauseTests(SimpleTestCase):

    def setUp(self):
        from game.tests.test_page_js import page_source
        self.html = page_source()   # разметка экранов — в game/_*.html

    def test_window_tells_the_server_about_the_pause(self):
        self.assertTrue("tellServer('/game/api/pause/')" in self.html,
                        'пауза не уходит на сервер')
        self.assertTrue("tellServer('/game/api/resume/')" in self.html,
                        'конец паузы не уходит на сервер')

    def test_answer_and_question_wait_for_the_pause_queue(self):
        self.assertTrue("return api('/game/api/answer/'" in self.html,
                        'ответ не ждёт очередь паузы')
        self.assertTrue("return api('/game/api/question/'" in self.html,
                        'вопрос не ждёт очередь паузы')

    def test_paused_answer_unlocks_instead_of_skipping_the_question(self):
        paused = self.html.find("d.reason === 'paused'")
        conflict = self.html.find('d.status === 409')
        self.assertTrue(0 <= paused < conflict,
                        'ответ на паузе принят бы за «уже отвечен»: вопрос пропал бы')
