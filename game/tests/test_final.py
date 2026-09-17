# -*- coding: utf-8 -*-
u"""Итог раунда (фаза P3 редизайна 17.09.2026, ADR 0111): данные сервера.

Сводка: полоски по звёздам и очки по темам. Финиш: места в таблице, прошлый
рекорд по правилу «рекорд — лучший зачётный раунд», итог вызова дня (доска
дня, место, серия, следующий вызов), остаток попыток набора и данные дуэли
для «Реванша». Разметку и код экрана держит `test_final_screen.py`.
"""
import json

from django.test import TestCase
from django.urls import reverse

from game import config, daily as daily_mod, leaderboard as lb
from game.models import GameQuestion, GameResult
from game.tests.test_ranked import RunHelper, make_q
from game.tests.test_sets import make_set
from problems.models import User


def answer(client, qid, right=True, skip=False):
    gq = GameQuestion.objects.get(id=qid)
    body = {'question_id': qid}
    if not skip:
        body['choice'] = gq.correct_index if right else (gq.correct_index + 1) % len(gq.options)
    return client.post(reverse('game:answer'), json.dumps(body),
                       content_type='application/json').json()


def finish(client, reason='time'):
    return client.post(reverse('game:session_finish'), json.dumps({'reason': reason}),
                       content_type='application/json').json()


def play_set(client, code, correct=2):
    d = client.get(reverse('game:session_start_set', args=[code])).json()
    assert d.get('ok'), d
    qid = d['question']['id']
    for _ in range(correct):
        answer(client, qid)
        nxt = client.get(reverse('game:question')).json()
        if not nxt.get('question'):
            break
        qid = nxt['question']['id']
    return finish(client, 'done')


class SummaryFieldsTests(RunHelper):
    def test_stars_split_outcomes_by_effective_difficulty(self):
        d = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        qid = d['question']['id']
        for kind in ('right', 'wrong', 'skip', 'right'):
            answer(self.client, qid, right=kind == 'right', skip=kind == 'skip')
            qid = self.client.get(reverse('game:question')).json()['question']['id']
        s = finish(self.client)['summary']
        self.assertEqual(s['stars'], [{'stars': 3, 'total': 4, 'correct': 2,
                                       'wrong': 1, 'skip': 1}])

    def test_topic_rows_carry_the_points_of_their_questions(self):
        s = self.play(correct=4)['summary']
        row = s['topic_rows'][0]
        self.assertEqual(row['topic'], 'Спрос и предложение')
        self.assertEqual(row['points'], sum(s['points_seq']))
        self.assertGreater(row['points'], 0)


class RankedExtrasTests(RunHelper):
    def test_ranked_student_gets_places_and_beats_the_previous_record(self):
        user = self.login()
        GameResult.objects.create(user=user, mode='blitz', score=10, ranked=True,
                                  economy_version=config.ECONOMY_VERSION)
        s = self.play(correct=6)['summary']
        self.assertTrue(s['ranked'], s.get('unranked_reason'))
        self.assertEqual(s['places'], {'week': 1, 'all': 1})
        self.assertEqual(s['record'], {'is_record': True, 'prev_best': 10})

    def test_a_lower_score_is_not_a_record(self):
        user = self.login()
        GameResult.objects.create(user=user, mode='blitz', score=99999, ranked=True,
                                  economy_version=config.ECONOMY_VERSION)
        s = self.play(correct=6)['summary']
        self.assertEqual(s['record'], {'is_record': False, 'prev_best': 99999})

    def test_unranked_record_does_not_count_as_the_previous_best(self):
        user = self.login()
        GameResult.objects.create(user=user, mode='blitz', score=99999, ranked=False,
                                  economy_version=config.ECONOMY_VERSION)
        s = self.play(correct=6)['summary']
        self.assertEqual(s['record'], {'is_record': False, 'prev_best': None})

    def test_unranked_round_has_no_places_and_no_record(self):
        s = self.play(correct=6)['summary']      # гость
        self.assertFalse(s['ranked'])
        self.assertNotIn('record', s)
        self.assertNotIn('places', s)

    def test_played_at_is_the_saved_moment(self):
        self.login()
        first = self.play(correct=6)['summary']['played_at']
        again = finish(self.client)['summary']['played_at']
        saved = GameResult.objects.get()
        self.assertEqual(first, saved.created_at.isoformat(timespec='seconds'))
        self.assertEqual(again, first)


class SetVariantsTests(TestCase):
    def setUp(self):
        for _ in range(12):
            make_q()
        for _ in range(12):
            make_q(qtype='boolean', options=['Верно', 'Неверно'])
        self.user = User.objects.create_user(username='itog', password='pw12345')
        self.client.force_login(self.user)

    def test_daily_leads_to_the_day_board_with_place_streak_and_next(self):
        gset = daily_mod.get_daily_set('blitz')
        data = play_set(self.client, gset.code)
        s = data['summary']
        self.assertTrue(data['share']['set']['board_url'].endswith(
            reverse('game:daily_board', args=['blitz'])))
        self.assertEqual(s['daily']['board_url'], reverse('game:daily_board', args=['blitz']))
        self.assertEqual((s['daily']['place'], s['daily']['total'], s['daily']['streak']),
                         (1, 1, 1))
        nxt = s['daily']['next']
        first_other = [m for m in config.MODES if m != 'blitz'
                       and daily_mod.get_daily_set(m, create=False)][0]
        self.assertEqual(nxt['mode'], first_other)
        self.assertTrue(nxt['url'].endswith('/?auto=1'))

    def test_teacher_set_says_how_many_attempts_are_left(self):
        gset = make_set(list(GameQuestion.objects.filter(question_type='single')[:5]),
                        attempts_allowed=2)
        s = play_set(self.client, gset.code)['summary']
        self.assertEqual(s['attempts_left'], 1)
        self.assertNotIn('daily', s)

    def test_duel_knows_whether_the_rival_has_played_and_how_to_rematch(self):
        gset = make_set(list(GameQuestion.objects.filter(question_type='single')[:5]),
                        kind='duel', title='Дуэль · Блиц', author=self.user)
        s = play_set(self.client, gset.code)['summary']
        self.assertEqual(s['duel']['url'], reverse('game:duel', args=[gset.code]))
        self.assertFalse(s['duel']['rival_done'])
        self.assertIn('rematch=' + gset.code, s['duel']['rematch_url'])
        self.assertIn('mode=blitz', s['duel']['rematch_url'])
        rival = User.objects.create_user(username='sopernik', password='pw12345')
        self.client.force_login(rival)
        self.assertTrue(play_set(self.client, gset.code)['summary']['duel']['rival_done'])


class RecordRuleTests(TestCase):
    u"""Одно правило личного рекорда: лучший ЗАЧЁТНЫЙ раунд режима."""

    def setUp(self):
        self.user = User.objects.create_user(username='rekord', password='pw12345')

    def result(self, score, ranked, mode='blitz'):
        return GameResult.objects.create(user=self.user, mode=mode, score=score,
                                         ranked=ranked, correct_count=5, wrong_count=1,
                                         skip_count=2,
                                         economy_version=config.ECONOMY_VERSION)

    def test_without_ranked_rounds_there_is_no_record_anywhere(self):
        self.result(900, ranked=False)
        self.assertIsNone(lb.best_run(self.user, 'blitz'))
        self.assertEqual(lb.best_scores(self.user), {})
        self.assertIsNone(lb.personal_stats(self.user, 'blitz')['best_score'])
        panel = lb.records_panel(self.user, 'blitz')
        self.assertIsNone(panel['best_score'])
        self.assertEqual(panel['mode_rows'][0]['score'], 0)

    def test_the_record_ignores_a_higher_unranked_round(self):
        self.result(300, ranked=True)
        self.result(900, ranked=False)
        self.assertEqual(lb.best_run(self.user, 'blitz')['score'], 300)
        self.assertEqual(lb.personal_stats(self.user, 'blitz')['best_score'], 300)
        panel = lb.records_panel(self.user, 'all')
        self.assertEqual(panel['best_score'], 300)
        self.assertEqual([r['best'] for r in panel['timeline']], [300, 300])
        # Счётчики — по всем раундам, это не рекорд.
        self.assertEqual(panel['runs'], 2)

    def test_history_average_has_correct_and_skipped_per_round(self):
        self.result(300, ranked=True)
        GameResult.objects.create(user=self.user, mode='blitz', score=100, ranked=False,
                                  correct_count=2, wrong_count=0, skip_count=1,
                                  economy_version=config.ECONOMY_VERSION)
        avg = lb.run_history(self.user, 'blitz')['avg']
        self.assertEqual((avg['correct'], avg['skipped']), (3.5, 1.5))
