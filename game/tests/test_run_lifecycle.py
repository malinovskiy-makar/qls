# -*- coding: utf-8 -*-
u"""Жизнь раунда Wecon Rush: брошенный раунд, run_id, момент конца (24.09.2026).

* 7.2 — брошенный раунд (закрыли вкладку, перезагрузили, ушли) сохраняется
  незачётным при следующем старте; раунд, уже законченный сервером по жизням,
  — со своей причиной; раунд по набору брошенным не сохраняется.
* 7.2 — `ended_at`: позднее сохранение не раздувает `wall_ms` до ложного
  `time_overrun`.
* 7.3 — ответ и финиш несут `run_id`; чужой раунд — 409.
"""
import json

from django.urls import reverse

from game import state as run_state
from game.models import GameQuestion, GameResult
from game.tests.test_ranked import RunHelper
from game.tests.test_sets import make_q, make_set


class RunLifecycleTests(RunHelper):

    def _start(self, query=''):
        d = self.client.get(reverse('game:session_start') + '?mode=blitz' + query).json()
        self.assertTrue(d.get('ok'), d)
        return d

    def _answer(self, qid, right=True, run_id=None):
        gq = GameQuestion.objects.get(id=qid)
        body = {'question_id': qid,
                'choice': gq.correct_index if right else (gq.correct_index + 1) % 4}
        if run_id:
            body['run_id'] = run_id
        return self.client.post(reverse('game:answer'), json.dumps(body),
                                content_type='application/json')

    def test_start_returns_run_id(self):
        d = self._start()
        self.assertTrue(d.get('run_id'))

    def test_abandoned_round_is_saved_as_quit_on_next_start(self):
        self.login()
        first = self._start()
        self._answer(first['question']['id'])
        self.assertEqual(GameResult.objects.count(), 0)
        self._start()          # вкладку закрыли, человек начал новый раунд
        saved = GameResult.objects.get()
        self.assertEqual(saved.ended_reason, 'quit')
        self.assertFalse(saved.ranked)
        self.assertEqual(saved.unranked_reason, 'quit')

    def test_round_ended_by_lives_keeps_its_reason(self):
        self.login()
        first = self._start()
        qid = first['question']['id']
        for _ in range(first['lives']):
            d = self._answer(qid, right=False).json()
            if d.get('game_over'):
                break
            qid = self.client.get(reverse('game:question')).json()['question']['id']
        self._start()
        self.assertEqual(GameResult.objects.get().ended_reason, 'lives')

    def test_round_without_answers_is_not_saved(self):
        self._start()
        self._start()
        self.assertEqual(GameResult.objects.count(), 0)

    def test_abandoned_set_round_is_not_saved(self):
        qs = [make_q(1)[0] for _ in range(6)]
        gset = make_set(qs)
        d = self.client.get(reverse('game:session_start_set', args=[gset.code])).json()
        self._answer(d['question']['id'])
        self._start()
        self.assertEqual(GameResult.objects.count(), 0)

    def test_wrong_run_id_is_409_for_answer_and_finish(self):
        d = self._start()
        response = self._answer(d['question']['id'], run_id='chuzhoy-raund')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['reason'], 'run_mismatch')
        finish = self.client.post(reverse('game:session_finish'),
                                  json.dumps({'reason': 'time', 'run_id': 'chuzhoy-raund'}),
                                  content_type='application/json')
        self.assertEqual(finish.status_code, 409)
        self.assertEqual(GameResult.objects.count(), 0)
        # Свой run_id — проходит.
        ok = self.client.post(reverse('game:session_finish'),
                              json.dumps({'reason': 'time', 'run_id': d['run_id']}),
                              content_type='application/json')
        self.assertEqual(ok.status_code, 200)

    def test_late_save_measures_wall_time_to_the_end_not_to_the_save(self):
        u"""Раунд кончился по жизням, вкладку закрыли, сохранили через час."""
        self.login()
        d = self._start()
        qid = d['question']['id']
        for _ in range(6):
            self._answer(qid)
            qid = self.client.get(reverse('game:question')).json()['question']['id']
        for _ in range(d['lives']):
            r = self._answer(qid, right=False).json()
            if r.get('game_over'):
                break
            qid = self.client.get(reverse('game:question')).json()['question']['id']
        # «Час назад»: раунд начался и кончился по жизням час назад, финиш —
        # сейчас (вкладку закрыли во время «игра окончена»).
        state = run_state.load_by_id(d['run_id'])
        self.assertEqual(state['ended'], 'lives')
        shift = 3600
        state['started_at'] -= shift
        state['ended_at'] -= shift
        run_state.save_by_id(state)
        self.client.post(reverse('game:session_finish'), json.dumps({'reason': 'quit'}),
                         content_type='application/json')
        saved = GameResult.objects.get()
        self.assertEqual(saved.ended_reason, 'lives')
        self.assertLess(saved.wall_ms, 600 * 1000)
        self.assertNotEqual(saved.unranked_reason, 'time_overrun')

    def test_state_keeps_ended_at(self):
        d = self._start()
        self.client.post(reverse('game:session_finish'), json.dumps({'reason': 'time'}),
                         content_type='application/json')
        state = run_state.load_by_id(d['run_id'])
        self.assertTrue(state.get('ended_at'))
