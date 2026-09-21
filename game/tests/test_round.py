# -*- coding: utf-8 -*-
u"""Экран раунда (фаза P2 редизайна 17.09.2026): одна полоса HUD, разбор ошибки
три секунды при стоящих часах, отсчёт 3-2-1, окна одной семьёй и брошенный
раунд как незачётный.

Решения владельца — ADR 0109 (разбор при серверной паузе) и ADR 0110 (полоса
HUD). Поведение в браузере (нет прокрутки на 1440×800, m:ss, 3000 ± 100 мс между
pause и resume, отсчёт) держит `test_browser_round.RoundBrowserTest`.
"""
import json
import re
import time

from django.test import TestCase
from django.urls import reverse

from game import config, consumers, leaderboard as lb, views
from game.models import GameQuestion, GameResult
from game.tests.test_page_js import inline_js, page_source
from game.tests.test_ranked import RunHelper
from game.tests.test_sets import make_q, make_set
from problems.models import User


class QuitSavesAsUnrankedTests(RunHelper):
    u"""Брошенный ОБЫЧНЫЙ раунд с ответом — один незачётный GameResult."""

    def answer_one(self, query=''):
        d = self.client.get(reverse('game:session_start') + '?mode=blitz' + query).json()
        self.assertTrue(d.get('ok'), d)
        gq = GameQuestion.objects.get(id=d['question']['id'])
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': gq.id, 'choice': gq.correct_index}),
                         content_type='application/json')
        return d

    def quit(self):
        return self.client.post(reverse('game:session_finish'),
                                json.dumps({'reason': 'quit'}),
                                content_type='application/json')

    def test_student_quit_with_an_answer_is_saved_unranked(self):
        user = self.login()
        before = views._ranked_today(user, 'blitz')
        self.answer_one()
        r = self.quit()
        self.assertEqual(r.status_code, 200, r.content)
        saved = GameResult.objects.get()
        self.assertEqual((saved.ranked, saved.unranked_reason, saved.ended_reason),
                         (False, 'quit', 'quit'))
        s = r.json()['summary']
        self.assertEqual((s['ended_reason'], s['unranked_reason']), ('quit', 'quit'))
        self.assertEqual(s['unranked_text'], 'вы вышли из раунда')
        self.assertEqual(views._ranked_today(user, 'blitz'), before)

    def test_guest_quit_is_saved_with_the_first_reason_anonymous(self):
        self.answer_one()
        self.assertEqual(self.quit().status_code, 200)
        self.assertEqual(GameResult.objects.get().unranked_reason, 'anonymous')

    def test_quit_without_a_single_answer_saves_nothing(self):
        self.login()
        self.client.get(reverse('game:session_start') + '?mode=blitz')
        r = self.quit()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['reason'], 'quit_not_saved')
        self.assertEqual(GameResult.objects.count(), 0)

    def test_quit_from_a_set_keeps_the_attempt(self):
        u"""Набор: выход не сохраняет раунд и попытку не тратит."""
        user = self.login()
        gset = make_set(list(GameQuestion.objects.filter(question_type='single')[:5]))
        d = self.client.get(reverse('game:session_start_set', args=[gset.code])).json()
        self.assertTrue(d.get('ok'), d)
        gq = GameQuestion.objects.get(id=d['question']['id'])
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': gq.id, 'choice': gq.correct_index}),
                         content_type='application/json')
        r = self.quit()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(GameResult.objects.count(), 0)
        from django.test import RequestFactory
        req = RequestFactory().get('/')
        req.user = user
        req.session = self.client.session
        self.assertEqual(views.attempts_used(req, gset), 0)

    def test_quit_is_the_second_reason_right_after_anonymous(self):
        keys = [k for k, _ in config.UNRANKED_REASONS]
        self.assertEqual(keys[:2], ['anonymous', 'quit'])
        self.assertEqual(views._end_reason({}, 'quit'), 'quit')

    def test_a_quit_round_is_not_a_record(self):
        user = self.login()
        GameResult.objects.create(user=user, mode='blitz', score=100, ranked=True,
                                  economy_version=config.ECONOMY_VERSION)
        GameResult.objects.create(user=user, mode='blitz', score=900, ended_reason='quit',
                                  unranked_reason='quit',
                                  economy_version=config.ECONOMY_VERSION)
        self.assertEqual(lb.best_run(user, 'blitz')['score'], 100)
        self.assertEqual(lb.best_scores(user), {'blitz': 100})


class PausedRivalClockTests(TestCase):
    u"""Часы соперника в дуэли не убегают на паузе (разбор ошибки, окно)."""

    def state(self, pauses, spent=60, bonus=0):
        now = time.time()
        return {'mode': 'blitz', 'started_at': now - spent, 'bonus_total': bonus,
                'pauses': pauses}

    def test_closed_pause_is_not_spent_time(self):
        now_ms = int(time.time() * 1000)
        st = self.state([[now_ms - 20000, now_ms - 17000]])
        # Без паузы было бы 60; целые секунды округляются вниз — отсюда допуск.
        self.assertAlmostEqual(consumers.seconds_left_for(st),
                               config.MODES['blitz']['duration'] - 60 + 3, delta=1)

    def test_an_open_pause_counts_up_to_now(self):
        now_ms = int(time.time() * 1000)
        st = self.state([[now_ms - 3000, None]])
        self.assertAlmostEqual(consumers.seconds_left_for(st),
                               config.MODES['blitz']['duration'] - 60 + 3, delta=1)
        self.assertGreater(consumers.seconds_left_for(st),
                           config.MODES['blitz']['duration'] - 60)

    def test_pause_credit_has_the_same_ceiling_as_ranking(self):
        now_ms = int(time.time() * 1000)
        long_pause = [[now_ms - 500000, now_ms - 100000]]   # 400 с паузы
        self.assertEqual(views.paused_ms_now({'pauses': long_pause}, now_ms),
                         config.PAUSE_CAP_SECONDS * 1000)


class QuestionPayloadDifficultyTests(TestCase):
    def test_question_carries_its_effective_difficulty(self):
        q = make_q(12)
        d = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        self.assertTrue(d.get('ok'), d)
        self.assertEqual(d['question']['difficulty'], 3)
        self.assertNotIn('correct_index', d['question'])
        self.assertTrue(q)

    def test_page_config_has_reveal_and_countdown_numbers(self):
        make_q(12)
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        self.assertIn('"reveal_wrong_ms": %d' % config.REVEAL_WRONG_MS, html)
        self.assertIn('"round_countdown_s": %d' % config.ROUND_COUNTDOWN_S, html)
        self.assertEqual(config.REVEAL_WRONG_MS, 3000)


class RoundClientTests(TestCase):
    u"""Код и разметка раунда: то, что сторожится текстом страницы."""

    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)
        i = self.src.index('<section id="screen-play"')
        self.play = self.src[i:self.src.index('<section id="screen-final"')]

    def body(self, name):
        m = re.search(r'function %s\([^)]*\) \{(.*?)\n  \}' % name, self.js, re.S)
        self.assertIsNotNone(m, '%s не найдена' % name)
        return m.group(1)

    def test_wrong_answer_pauses_and_the_end_of_reveal_resumes(self):
        self.assertIn('rushPause();', self.body('revealWrong'))
        self.assertIn('revealTimer = setTimeout(endReveal, ms);', self.body('revealWrong'))
        self.assertIn('var ms = CFG.reveal_wrong_ms || 3000;', self.body('revealWrong'))
        end = self.body('endReveal')
        self.assertIn('if (!modalIsOpen()) rushResume();', end)
        self.assertIn('advance();', end)
        for fn in ('answer', 'submitMulti', 'submitNumeric'):
            self.assertIn('revealWrong();', self.body(fn), fn)
            self.assertNotIn('setTimeout(advance, REDUCED ? 0 : 900)', self.body(fn), fn)
            self.assertNotIn('setTimeout(advance, REDUCED ? 0 : 1300)', self.body(fn), fn)

    def test_practice_has_no_pause(self):
        self.assertIn("if (state !== 'playing' || pausedAt || practice) return;",
                      self.body('rushPause'))

    def test_keys_during_reveal_do_not_answer(self):
        m = re.search(r"if \(revealOn\) \{(.*?)\n        return;\n      \}", self.js, re.S)
        self.assertIsNotNone(m, 'ветки клавиш разбора нет')
        branch = m.group(1)
        self.assertIn('endReveal();', branch)
        self.assertNotIn('answer(', branch)
        # Ветка разбора стоит ДО цифр ответа.
        self.assertLess(self.js.index('if (revealOn) {'),
                        self.js.index("if (e.key >= '1' && e.key <= '6') {"))

    def test_timer_is_minutes_and_seconds(self):
        self.assertIn("$('hud-timer').textContent = clockText(timeLeft);", self.js)
        self.assertIn("return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);",
                      self.body('clockText'))
        self.assertNotIn('toFixed(1)', self.body('paintHud'))

    def test_record_chip_only_with_a_record_and_never_for_practice(self):
        body = self.body('paintBest')
        self.assertIn('if (!vsBest || practice) {', body)
        self.assertIn('vsBest = d.best || null;', self.js)

    def test_site_header_is_hidden_while_playing(self):
        self.assertIn("document.body.classList.toggle('rush-playing', name === 'playing');",
                      self.body('show'))
        self.assertIn('body.rush-playing nav.site-nav', self.src)

    def test_option_grid_keeps_the_number_in_its_own_column(self):
        self.assertIn('display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; '
                      'align-items: start; gap: 12px;', self.src)
        self.assertIn('.opt:last-child:nth-child(odd) { grid-column: 1 / -1; }', self.src)

    def test_countdown_before_a_single_round_but_not_a_duel(self):
        self.assertIn('if (isDuelRun()) { go(); } else { runCountdown(go); }', self.js)
        self.assertIn("var left = CFG.round_countdown_s || 3;", self.body('runCountdown'))
        self.assertIn("if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); finishCountdown(); }",
                      self.js)

    def test_old_scoreboard_and_hint_are_gone_from_the_round(self):
        for gone in ('class="vs"', 'Ваш рекорд', 'ваш рекорд', 'keys-hint'):
            self.assertNotIn(gone, self.play, gone)

    def test_eight_duel_reactions_with_text_labels(self):
        m = re.search(r"var TITLES = \{(.*?)\};", self.js, re.S)
        self.assertIsNotNone(m)
        labels = re.findall(r"(\w+): '([^']+)'", m.group(1))
        self.assertEqual([t for _, t in labels],
                         ['gg', 'вау', 'огонь', 'думаю', 'упс', 'быстро', 'близко', 'удачи'])
        self.assertIn('b.appendChild(document.createTextNode(TITLES[name]));', self.js)

    def test_escape_opens_the_quit_window(self):
        self.assertIn("if (e.key === 'Escape' && !practice && !figFull) { e.preventDefault(); openQuit(); return; }",
                      self.js)

    def test_quit_run_saves_only_a_round_without_a_set(self):
        body = self.body('quitRun')
        self.assertIn("if (!setRun && answered + skippedCount > 0) {", body)
        self.assertIn("endRun('quit');", body)

    def test_quit_dialog_texts_by_kind(self):
        body = self.body('paintQuitDialog')
        for need in ("'Выйти из раунда?'", "'Выйти из вызова дня?'", "'Выйти из набора?'",
                     "'Выйти из дуэли?'", '<b>Попытка не потратится</b>', "'новый рекорд'"):
            self.assertIn(need, body)
        set_branch = body.split('} else if (setRun) {', 1)[1].split('} else {', 1)[0]
        self.assertNotIn('незачётн', set_branch)

    def test_all_windows_are_one_family(self):
        for wid in ('quit-modal', 'pr-end', 'dm-auth', 'gameover-overlay', 'lost-overlay'):
            self.assertRegex(self.src, r'<div class="quit-modal" id="%s"' % wid)
        self.assertIn('>Сыграть ещё раз</button>', self.src)
        self.assertIn('пробуем снова сами, раунд не потерян', self.src)
