# -*- coding: utf-8 -*-
u"""«Бесконечные тесты» внутри Wecon Rush (решение владельца 15.09.2026).

Без времени, жизней, очков и лидерборда, на игровом пуле: данетки, один и
несколько верных. Практика — отдельная константа, а не запись в MODES: её не
видят лидерборд, карточки режимов, «Мои рекорды» и «работа над ошибками».
"""
import json
import re
from unittest import mock

from django.test import TestCase

from game import config, state as run_state, views
from game.models import GameQuestion, GameResult
from game.tests.test_page_js import inline_js, page_source
from problems.tests.factories import make_problem

OPTIONS = {
    'boolean': dict(options=['Верно', 'Неверно'], correct_index=0),
    'single': dict(options=['спрос', 'предложение', 'цена'], correct_index=1),
    'multi': dict(options=['а', 'б', 'в'], correct_indices=[0, 2]),
    'numeric': dict(options=[], correct_value='5'),
}


def _question(qtype, number):
    return GameQuestion.objects.create(
        problem=make_problem('Условие %s %d.' % (qtype, number)), question_type=qtype,
        question='Вопрос %s %d' % (qtype, number), difficulty=2, topics=[], lang='ru',
        **OPTIONS[qtype])


def _body(q, right=True):
    """Тело ответа на вопрос `q`: верное или заведомо неверное."""
    if q.question_type == 'multi':
        return {'question_id': q.id, 'choices': q.correct_indices if right else [1]}
    wrong = (q.correct_index + 1) % len(q.options)
    return {'question_id': q.id, 'choice': q.correct_index if right else wrong}


class PracticeConfigTests(TestCase):
    def test_practice_is_a_separate_constant_not_a_mode(self):
        self.assertNotIn('practice', config.MODES)
        self.assertEqual(config.PRACTICE['key'], 'practice')
        self.assertEqual(config.practice_modes(), ('bullet', 'blitz', 'rapid'))
        self.assertEqual(run_state.ttl_for('practice'), 2 * 60 * 60)


class PracticeApiTests(TestCase):
    def setUp(self):
        for qtype in OPTIONS:
            for number in range(3):
                _question(qtype, number)

    def start(self, mode='practice'):
        resp = self.client.get('/game/api/session/start/?mode=%s' % mode)
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def run_state(self):
        return run_state.load_by_id(self.client.session[run_state.RUN_ID_KEY])

    def answer(self, body):
        return self.client.post('/game/api/answer/', json.dumps(body),
                                content_type='application/json').json()

    def next_question(self):
        return GameQuestion.objects.get(pk=self.client.get('/game/api/question/').json()['question']['id'])

    def test_start_state_has_no_duration_lives_or_record(self):
        data = self.start()
        self.assertTrue(data['ok'] and data['mode']['practice'])
        self.assertIsNone(data['lives'])
        self.assertIsNone(data['best'])
        state = self.run_state()
        self.assertEqual((state['practice'], state['duration'], state['lives']), (True, None, None))

    def test_only_test_types_are_served_and_all_of_them(self):
        types = {self.start()['question']['type']}
        while True:
            data = self.client.get('/game/api/question/').json()
            if data.get('exhausted'):
                break
            types.add(data['question']['type'])
        self.assertEqual(types, {'boolean', 'single', 'multi'})
        self.assertEqual(len(self.run_state()['seen']), 9)

    def test_answer_keeps_score_and_shows_correct_choices(self):
        q = GameQuestion.objects.get(pk=self.start()['question']['id'])
        data = self.answer(_body(q))
        self.assertEqual((data['result'], data['practice']), ('correct', True))
        expected = q.correct_indices if q.question_type == 'multi' else [q.correct_index]
        self.assertEqual(data['correct_choices'], expected)
        for absent in ('score', 'lives', 'time_delta', 'streak'):
            self.assertFalse(absent in data, 'в ответе практики есть %s' % absent)
        self.assertEqual(self.run_state()['score'], 0)

    def test_regular_round_has_no_correct_choices(self):
        q = GameQuestion.objects.get(pk=self.start('blitz')['question']['id'])
        data = self.answer(_body(q))
        self.assertTrue('score' in data, 'обычный раунд без очков')
        self.assertFalse('correct_choices' in data, 'поле практики в обычном раунде')

    def test_finish_is_a_summary_without_result_record_or_mistakes_run(self):
        first = GameQuestion.objects.get(pk=self.start()['question']['id'])
        self.answer(_body(first, right=False))
        self.answer(_body(self.next_question()))
        self.answer({'question_id': self.next_question().id, 'choice': None})
        data = self.client.post('/game/api/session/finish/', '{}',
                                content_type='application/json').json()
        self.assertEqual(data['summary'],
                         {'answered': 2, 'correct': 1, 'skipped': 1, 'accuracy': 50})
        self.assertFalse(GameResult.objects.exists())
        self.assertFalse(views.LAST_KEY in self.client.session, 'практика стала «работой над ошибками»')

    def test_leaderboard_ignores_practice_and_counts_add_up(self):
        board = self.client.get('/game/api/leaderboard/?mode=practice').json()
        self.assertEqual(board['mode'], config.DEFAULT_MODE)
        counts = self.client.get('/game/api/pool_counts/').json()
        three = sum(counts['counts'][key] for key in ('bullet', 'blitz', 'rapid'))
        self.assertEqual((counts['practice'], three), (9, 9))
        self.assertFalse('practice' in counts['counts'], 'практика попала в счётчики режимов')
        self.assertEqual(counts['total'], sum(counts['counts'].values()))

    def test_start_page_has_the_band_with_its_count(self):
        html = self.client.get('/game/').content.decode()
        # С 17.09.2026 вход — ячейка нижней полосы стартового экрана (ADR 0108).
        for needle in ('<div class="st-card cell" id="practice-band">', 'Бесконечные тесты</h2>',
                       'без времени, жизней и очков: просто решайте',
                       '"practice": {"title": "Бесконечные тесты", "count": 9}'):
            self.assertTrue(needle in html, 'нет на стартовой: %s' % needle)


class PracticeWithoutEscalationTests(TestCase):
    u"""В практике серии нет, и эскалация по комбо держала бы её на лёгких вечно."""

    def test_hard_question_is_not_held_back_at_zero_streak(self):
        easy = GameQuestion.objects.create(
            problem=make_problem('Лёгкое.'), question_type='boolean', question='Лёгкое',
            difficulty=1, topics=[], lang='ru', **OPTIONS['boolean'])
        hard = GameQuestion.objects.create(
            problem=make_problem('Трудное.'), question_type='boolean', question='Трудное',
            difficulty=5, topics=[], lang='ru', **OPTIONS['boolean'])
        # Выбор «самый поздний номер» вместо случайного: при серии 0 полоса
        # раунда — 1–2 звезды, и трудного вопроса в ней нет вовсе.
        with mock.patch('game.views.random.choice', side_effect=max):
            first = self.client.get('/game/api/session/start/?mode=practice').json()['question']
        self.assertEqual(first['id'], hard.id)
        self.assertNotEqual(first['id'], easy.id)


class PracticeClientTests(TestCase):
    u"""Клиент практики: окно считается окном, паузы нет, HUD без времени и очков."""

    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)

    def test_end_window_is_a_modal_and_practice_has_no_pause(self):
        self.assertTrue("'#pr-end:not([hidden])'" in self.js, 'окно практики не в modalIsOpen')
        m = re.search(r'function openPracticeEnd\(summaryNow\) \{(.*?)\n  \}', self.js, re.S)
        self.assertTrue(m and "detail: { open: true }" in m.group(1), 'окно не шлёт weco:modal')
        self.assertTrue("if (state !== 'playing' || pausedAt || practice) return;" in self.js,
                        'пауза практики поднимет таймер после окна')
        self.assertTrue("if (practice) { openPracticeEnd(false); return; }" in self.js)

    def test_hud_hides_time_lives_score_and_combo(self):
        self.assertTrue('body.practice .hud-score, body.practice .timer-box, body.practice .time-track,\n'
                        'body.practice .hud-lives, body.practice .hud-combo { display: none; }' in self.src)
        self.assertTrue('Вопрос <b id="pr-number">1</b> · верных <b id="pr-correct">0</b>' in self.src)

    def test_keys_and_track_events(self):
        for needle in ("if (e.key === 'ArrowLeft') { e.preventDefault(); practiceBack(); return; }",
                       "weco.track('practice_start'", "weco.track('practice_end'"):
            self.assertTrue(needle in self.js, 'нет в скрипте: %s' % needle)
