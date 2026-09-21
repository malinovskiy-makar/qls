# -*- coding: utf-8 -*-
u"""«Бесконечные тесты» внутри Wecon Rush (решение владельца 15.09.2026).

Без времени, жизней, очков и лидерборда, на игровом пуле: данетки, один и
несколько верных. Практика — отдельная константа, а не запись в MODES: её не
видят лидерборд, карточки режимов, «Мои рекорды» и «работа над ошибками».
"""
import json
import re
from unittest import mock

from django.test import TestCase, override_settings

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
        summary = data['summary']
        self.assertEqual({k: summary[k] for k in ('answered', 'correct', 'wrong', 'skipped', 'accuracy')},
                         {'answered': 2, 'correct': 1, 'wrong': 1, 'skipped': 1, 'accuracy': 50})
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
        m = re.search(r'function openPracticeEnd\(exhausted\) \{(.*?)\n  \}', self.js, re.S)
        self.assertTrue(m and "detail: { open: true }" in m.group(1), 'окно не шлёт weco:modal')
        self.assertTrue("if (state !== 'playing' || pausedAt || practice) return;" in self.js,
                        'пауза практики поднимет таймер после окна')
        self.assertTrue("if (practice) { openPracticeEnd(false); return; }" in self.js)

    def test_hud_hides_time_lives_score_and_combo(self):
        self.assertTrue('body.practice .hud-score, body.practice .hud-clock, body.practice .time-track,\n'
                        'body.practice .hud-lives-wrap, body.practice .hud-combo, body.practice .hud-stat,\n'
                        'body.practice .hud-rec, body.practice #q-points' in self.src)
        self.assertTrue('<span class="pr-qno">Вопрос <b id="pr-number">1</b></span>' in self.src)

    def test_keys_and_track_events(self):
        for needle in ("if (e.key === 'ArrowLeft') { e.preventDefault(); practiceBack(); return; }",
                       "weco.track('practice_start'", "weco.track('practice_end'"):
            self.assertTrue(needle in self.js, 'нет в скрипте: %s' % needle)


# ─── P5: обратимый пропуск, разбор после ответа, итог-экран (решение 17.09.2026) ──

class ReversibleSkipTests(TestCase):
    u"""Сервер: на пропущенный вопрос практики можно ответить позже, в раунде — нет."""

    def setUp(self):
        for number in range(8):
            GameQuestion.objects.create(
                problem=make_problem('Условие %d.' % number), question_type='single',
                question='Вопрос %d' % number, difficulty=2, topics=['Эластичность'],
                lang='ru', **OPTIONS['single'])

    def start(self, mode='practice'):
        return GameQuestion.objects.get(pk=self.client.get(
            '/game/api/session/start/?mode=%s' % mode).json()['question']['id'])

    def post(self, body):
        return self.client.post('/game/api/answer/', json.dumps(body), content_type='application/json')

    def next_question(self):
        return GameQuestion.objects.get(pk=self.client.get('/game/api/question/').json()['question']['id'])

    def state(self):
        return run_state.load_by_id(self.client.session[run_state.RUN_ID_KEY])

    def test_skipped_question_is_answered_later_and_the_log_keeps_one_outcome(self):
        first = self.start()
        self.assertEqual(self.post({'question_id': first.id, 'choice': None}).json()['result'], 'skip')
        self.next_question()
        resp = self.post(_body(first, right=False))
        self.assertEqual((resp.status_code, resp.json()['result']), (200, 'wrong'))
        state = self.state()
        self.assertEqual(state['answered'][str(first.id)], 'wrong')
        entries = [e for e in state['log'] if e['question_id'] == first.id]
        self.assertEqual([(e['outcome'], e['chosen']) for e in entries], [('wrong', [2])])
        self.assertEqual(self.post(_body(first)).status_code, 409)

    def test_question_that_was_not_served_is_refused(self):
        self.start()
        stranger = GameQuestion.objects.exclude(id__in=self.state()['seen']).first()
        self.assertEqual(self.post(_body(stranger)).status_code, 404)

    def test_round_keeps_a_skip_final(self):
        first = self.start('blitz')
        self.post({'question_id': first.id, 'choice': None})
        self.next_question()
        self.assertEqual(self.post(_body(first)).status_code, 409)

    def test_skip_does_not_reveal_the_answer(self):
        u"""Пропуск обратим — значит, верный ответ с ним уходить не должен."""
        first = self.start()
        data = self.post({'question_id': first.id, 'choice': None}).json()
        for leak in ('correct_choices', 'problem_id', 'solution'):
            self.assertNotIn(leak, data)
        answered = self.post(_body(self.next_question(), right=False)).json()
        self.assertEqual(answered['correct_choices'], [1])
        self.assertIn('problem_id', answered)

    def test_summary_after_answering_a_skip(self):
        u"""Инвариант спецификации: 1 верный, 2 ошибки, 2 пропуска, потом ответ на пропуск."""
        results_before = GameResult.objects.count()
        q = [self.start()]
        self.post(_body(q[0]))
        for right in (False, False):
            q.append(self.next_question())
            self.post(_body(q[-1], right=right))
        for _ in range(2):
            q.append(self.next_question())
            self.post({'question_id': q[-1].id, 'choice': None})
        self.post(_body(q[3], right=True))           # вернулись к первому пропуску
        summary = self.client.post('/game/api/session/finish/', '{}',
                                   content_type='application/json').json()['summary']
        self.assertEqual((summary['answered'], summary['correct'], summary['wrong'], summary['skipped']),
                         (4, 2, 2, 1))
        self.assertEqual([(m['number'], m['outcome']) for m in summary['mistakes']],
                         [(2, 'wrong'), (3, 'wrong'), (5, 'skip')])
        wrong = summary['mistakes'][0]
        self.assertEqual((wrong['text'], wrong['topic'], wrong['your'], wrong['right'], wrong['problem_id']),
                         (q[1].question, 'Эластичность', '3', '2', q[1].problem_id))
        self.assertEqual(summary['mistakes'][2]['your'], '')
        self.assertEqual(summary['topics'], [{'topic': 'Эластичность', 'correct': 2, 'wrong': 2,
                                              'skip': 1, 'total': 5}])
        self.assertEqual(GameResult.objects.count(), results_before)


@override_settings(GAME_GENERATED_ENABLED=True)
class GeneratedSolutionTests(TestCase):
    def test_generated_question_brings_its_solution_and_no_problem(self):
        gq = GameQuestion.objects.create(
            problem=None, question_type='single', question='Сгенерированный вопрос', difficulty=2,
            topics=['Эластичность'], lang='ru', is_generated=True,
            gen_solution='120 − 2P = 4P, откуда P = 20.', **OPTIONS['single'])
        first = self.client.get('/game/api/session/start/?mode=practice').json()['question']
        self.assertEqual(first['id'], gq.id)
        data = self.client.post('/game/api/answer/', json.dumps(_body(gq, right=False)),
                                content_type='application/json').json()
        self.assertEqual((data['solution'], data['problem_id']), (gq.gen_solution, None))
        summary = self.client.post('/game/api/session/finish/', '{}',
                                   content_type='application/json').json()['summary']
        self.assertEqual(summary['mistakes'][0]['solution'], gq.gen_solution)


class PracticeScreenSourceTests(TestCase):
    u"""Клиент P5: разбор, лента, листание и итог — по коду страницы."""

    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)

    def body(self, name):
        m = re.search(r'function %s\([^)]*\) \{(.*?)\n  \}' % name, self.js, re.S)
        self.assertIsNotNone(m, '%s не найдена' % name)
        return m.group(1)

    def test_feedback_has_catalog_link_and_solution_and_no_topic(self):
        fb = self.body('paintPracticeFeedback')
        self.assertIn("open.href = '/catalog/problem/' + entry.problemId + '/';", fb)
        self.assertIn('open.hidden = !entry.problemId;', fb)
        self.assertIn("$('pr-fb-sol').hidden = !entry.solution;", fb)
        self.assertNotIn('topic', fb)
        panel = self.src[self.src.index('<div class="pr-fb"'):self.src.index('<div class="pr-foot">')]
        self.assertNotIn('topic', panel)
        self.assertIn('Открыть задачу в каталоге', panel)

    def test_history_keeps_problem_and_solution_of_each_answer(self):
        answer = self.body('practiceAnswer')
        self.assertIn('entry.problemId = d.problem_id || null;', answer)
        self.assertIn("entry.solution = d.solution || '';", answer)
        self.assertIn('paintPracticeFeedback(isAnswered(entry) ? entry : null);', self.body('showPracticeEntry'))

    def test_right_button_is_named_by_situation(self):
        self.assertIn("$('pr-next-text').textContent = !last ? 'Вперёд' : done ? 'Дальше' : 'Пропустить';",
                      self.body('paintPractice'))
        nxt = self.body('practiceNext')
        self.assertIn("if (practiceLog[practiceAt].status === 'live') { skip(); return; }", nxt)

    def test_skipped_entry_stays_answerable_and_answered_is_read_only(self):
        show = self.body('showPracticeEntry')
        self.assertIn('if (isAnswered(entry)) {\n      inputLocked = true;', show)
        self.assertIn("return entry.status === 'correct' || entry.status === 'wrong';", self.js)

    def test_word_resheno_is_gone_and_tallies_are_four(self):
        self.assertNotIn('Решено', self.src)
        for tally in ('id="pr-answered"', 'id="pr-correct"', 'id="pr-wrong"', 'id="pr-skipped"'):
            self.assertIn(tally, self.src)

    def test_hover_on_an_option_is_only_a_border(self):
        self.assertIn('.opt:hover { border-color: var(--accent); }', self.src)
        hovers = re.findall(r'\.opt[^{,]*:hover[^{]*\{([^}]*)\}', self.src)
        self.assertTrue(hovers)
        for rule in hovers:
            self.assertNotIn('green', rule)
            self.assertNotIn('background', rule)

    def test_escape_and_cross_ask_to_finish(self):
        self.assertIn("if (e.key === 'Escape') { e.preventDefault(); openPracticeEnd(false); return; }", self.js)
        self.assertIn("if (practice) { openPracticeEnd(false); return; }", self.body('openQuit'))
        dialog = self.src[self.src.index('id="pr-end"'):]
        dialog = dialog[:dialog.index('</div>\n</div>')]
        for text in ('Закончить?', 'Покажем итог: сколько верных, список ошибок и пропусков, точность по темам.',
                     'Нет, решать дальше', 'Да, к итогу'):
            self.assertIn(text, dialog)

    def test_result_is_a_screen_with_mistakes_topics_and_actions(self):
        final = self.src[self.src.index('<div class="final pr-final"'):]
        for needle in ('id="prf-again"', 'Поменять фильтры', 'На старт', 'id="prf-list"', 'id="prf-bars"',
                       'Ни одной ошибки и ни одного пропуска.', 'не идут ни в таблицу, ни в рекорды'):
            self.assertIn(needle, final)
        self.assertIn("go.addEventListener('click', function () { practiceTopic(t.topic); });",
                      self.body('paintPracticeTopics'))
        topic = self.body('practiceTopic')
        self.assertIn('filter.topics = [topic];', topic)
        self.assertIn('againPractice();', topic)
