u"""Режим «График» в игре: выдача, анти-чит, флаг, разбор, статистика.

Каскад и сами сюжеты проверяет `test_figure_cascade.py`; здесь — только то,
что происходит с ними ВНУТРИ игры.
"""
import json
import random

from django.test import TestCase, override_settings
from django.urls import reverse

from game import config, stats as stats_mod, views
from game.figures import base as fbase
from game.figures.registry import SCENARIOS, SCENARIO_ORDER
from game.models import ArchetypeStat, GameQuestion

AUDIT = fbase.QUESTION_TYPE


def make_audit_question(scenario_key='cs_triangle', seed=7, **kw):
    u"""Одна строка пула — ровно так же, как её делает команда генерации."""
    sc = SCENARIOS[scenario_key]
    rng = random.Random(seed)
    q = fbase.build_question(sc, rng, config.FIGURE_CLEAN_SHARE)
    q.update(kw)
    return GameQuestion.objects.create(
        problem=None, part=None, question_type=AUDIT,
        question=q['statement'], options=q['options'],
        correct_index=q['correct_index'], correct_value='',
        difficulty=q['difficulty'], topics=q['topics'], lang='ru',
        is_generated=True, generator_key=q['generator_key'],
        gen_params=q['params'], gen_solution=q['solution_text'],
        figure=q['figure'], figure_ref=q['figure_ref'])


@override_settings(GAME_FIGURE_ENABLED=True, GAME_GENERATED_ENABLED=False)
class ServingTests(TestCase):
    def setUp(self):
        self.gq = make_audit_question()

    def test_payload_has_the_figure_and_the_prompt(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        q = d['question']
        self.assertEqual(q['type'], AUDIT)
        self.assertEqual(q['options'], fbase.ANSWER_OPTIONS)
        self.assertTrue(q['figure']['lines'] or q['figure']['polylines'])
        self.assertIn(u'ПЕРВЫЙ', q['prompt'])

    def test_nothing_that_gives_away_the_answer_leaks_into_the_payload(self):
        u"""★ Анти-чит. Ни верного варианта, ни вида ошибки, ни эталона."""
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        q = d['question']
        blob = json.dumps(q, ensure_ascii=False)
        for banned in ('correct_index', 'correct_indices', 'correct_value',
                       'figure_ref', 'gen_params', 'gen_solution',
                       '_inject', '_step', 'injected_step', 'solution'):
            self.assertNotIn(banned, blob, u'в payload утекло «%s»' % banned)
        # и эталонного чертежа там нет даже по содержимому
        self.assertNotEqual(json.dumps(self.gq.figure_ref, sort_keys=True),
                            json.dumps(q['figure'], sort_keys=True)) \
            if self.gq.gen_params['_step'] != fbase.STEP_CLEAN else None

    def test_answer_is_checked_like_a_single_choice(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        qid = d['question']['id']
        body = self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid,
                        'choice': self.gq.correct_index}),
            content_type='application/json').json()
        self.assertTrue(body['correct'])
        self.assertEqual(body['correct_index'], self.gq.correct_index)

    def test_a_wrong_answer_costs_a_life_and_not_time(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        qid = d['question']['id']
        wrong = (self.gq.correct_index + 1) % 4
        body = self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid, 'choice': wrong}),
            content_type='application/json').json()
        self.assertFalse(body['correct'])
        self.assertEqual(body['lives'], config.MODES['figure']['lives'] - 1)
        self.assertEqual(body['time_delta'], 0)

    def test_the_answer_carries_the_reference_figure_and_the_explanation(self):
        u"""★ Разбор ошибок показывает ДВА чертежа — эталон приходит сейчас."""
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        qid = d['question']['id']
        body = self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid, 'choice': 0}),
            content_type='application/json').json()
        self.assertIn('figure', body)
        self.assertIn('figure_ref', body)
        self.assertEqual(body['figure_ref']['xmax'], self.gq.figure['xmax'])
        self.assertTrue(body['solution'])
        self.assertIn(body['injected_step'],
                      list(fbase.STEPS) + [fbase.STEP_CLEAN])

    def test_mode_timings_come_from_config(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        for field in ('duration', 'time_correct', 'time_wrong', 'time_skip',
                      'lives'):
            self.assertEqual(d['mode'][field], config.MODES['figure'][field])
        # числа поставлены рассуждением и подлежат замеру — но они ЭТИ
        self.assertEqual(config.MODES['figure']['duration'], 600)
        self.assertEqual(config.MODES['figure']['time_correct'], 25)

    def test_mode_is_on_the_start_screen(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual(cfg['pool_counts']['figure'], 1)


@override_settings(GAME_FIGURE_ENABLED=False, GAME_GENERATED_ENABLED=True)
class FlagOffTests(TestCase):
    u"""★ Флаг герметичен: выключен — режима нет нигде, и это НЕ 500."""

    def setUp(self):
        self.gq = make_audit_question()

    def test_pool_count_is_zero(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual(cfg['pool_counts']['figure'], 0)

    def test_direct_entry_gives_an_empty_run_not_a_crash(self):
        r = self.client.get(reverse('game:session_start'), {'mode': 'figure'})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d['pool_empty'])
        self.assertIsNone(d['question'])

    def test_the_page_itself_still_opens(self):
        self.assertEqual(self.client.get(reverse('game:page')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('game:page') + '?mode=figure').status_code,
            200)

    def test_the_pool_query_excludes_audit_questions(self):
        self.assertEqual(views._pool_qs().filter(question_type=AUDIT).count(), 0)
        self.assertEqual(
            GameQuestion.objects.filter(question_type=AUDIT).count(), 1)


@override_settings(GAME_FIGURE_ENABLED=True, GAME_GENERATED_ENABLED=False)
class FlagsAreIndependentTests(TestCase):
    u"""★ Флаг «Графика» НЕ связан с флагом семнадцати архетипов.

    Проверяется на СМЕШАННОМ пуле: если бы аудит зависел от
    GAME_GENERATED_ENABLED, на проде (где тот выключен) режим погас бы
    вместе с архетипами.
    """

    def setUp(self):
        self.audit = make_audit_question()
        self.arch = GameQuestion.objects.create(
            problem=None, question_type='numeric', question=u'2 + 2?',
            options=[], correct_value='4', lang='ru', is_generated=True,
            generator_key='equilibrium')
        self.bank = GameQuestion.objects.create(
            problem=None, question_type='single', question=u'вопрос банка',
            options=[u'а', u'б'], correct_index=0, lang='ru',
            is_generated=False)

    def test_audit_survives_the_generated_flag_being_off(self):
        ids = set(views._pool_qs().values_list('id', flat=True))
        self.assertIn(self.audit.id, ids)
        self.assertNotIn(self.arch.id, ids)      # архетип выключен
        self.assertIn(self.bank.id, ids)

    @override_settings(GAME_FIGURE_ENABLED=False, GAME_GENERATED_ENABLED=True)
    def test_archetypes_survive_the_figure_flag_being_off(self):
        ids = set(views._pool_qs().values_list('id', flat=True))
        self.assertNotIn(self.audit.id, ids)
        self.assertIn(self.arch.id, ids)
        self.assertIn(self.bank.id, ids)


@override_settings(GAME_FIGURE_ENABLED=True, GAME_GENERATED_ENABLED=False)
class StatisticsTests(TestCase):
    u"""Статистика — по СЮЖЕТУ и по виду внедрённой ошибки, не по экземпляру."""

    def setUp(self):
        self.gq = make_audit_question()

    def test_scenario_and_variant_counters_both_move(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        qid = d['question']['id']
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': qid,
                                     'choice': self.gq.correct_index}),
                         content_type='application/json')
        by_scenario = ArchetypeStat.objects.get(
            generator_key=self.gq.generator_key)
        self.assertEqual(by_scenario.correct, 1)
        variant = stats_mod.variant_key(self.gq)
        self.assertIsNotNone(variant)
        self.assertEqual(
            ArchetypeStat.objects.get(generator_key=variant).correct, 1)

    def test_variant_key_is_reversible_and_scoped_to_the_mode(self):
        self.assertIn(stats_mod.VARIANT_SEP, stats_mod.variant_key(self.gq))
        other = GameQuestion(question_type='numeric',
                             generator_key='monopoly', gen_params={})
        self.assertIsNone(stats_mod.variant_key(other))

    def test_difficulty_comes_from_the_scenario(self):
        for key in SCENARIO_ORDER:
            gq = make_audit_question(key, seed=11)
            self.assertEqual(gq.difficulty, SCENARIOS[key].difficulty)


@override_settings(GAME_FIGURE_ENABLED=True, GAME_GENERATED_ENABLED=False)
class AnswerDistributionTests(TestCase):
    u"""Распределение верных ответов на 2000 сэмплов: 28/28/28/15 (±4 п.п.)."""

    def test_distribution(self):
        rng = random.Random('mode-distribution')
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        total = 2000
        keys = list(SCENARIO_ORDER)
        for i in range(total):
            q = fbase.build_question(SCENARIOS[keys[i % len(keys)]], rng,
                                     config.FIGURE_CLEAN_SHARE)
            counts[q['correct_index']] += 1
        want_err = 100.0 * (1 - config.FIGURE_CLEAN_SHARE) / 3
        for idx in (0, 1, 2):
            self.assertAlmostEqual(100.0 * counts[idx] / total, want_err,
                                   delta=4.0)
        self.assertAlmostEqual(100.0 * counts[3] / total,
                               100.0 * config.FIGURE_CLEAN_SHARE, delta=4.0)


class PoolLifecycleTests(TestCase):
    u"""Сюжеты обязаны пережить пересборку пула и снос архетипов."""

    def setUp(self):
        self.gq = make_audit_question()

    def test_audit_rows_are_marked_generated(self):
        u"""Иначе build_game_pool снесёт их при первой же пересборке."""
        self.assertTrue(self.gq.is_generated)

    def test_purge_generated_does_not_touch_audit_questions(self):
        from django.core.management import call_command
        from io import StringIO
        GameQuestion.objects.create(
            problem=None, question_type='numeric', question=u'архетип',
            options=[], correct_value='1', lang='ru', is_generated=True,
            generator_key='equilibrium')
        call_command('purge_generated', stdout=StringIO())
        self.assertTrue(GameQuestion.objects.filter(id=self.gq.id).exists())
        self.assertFalse(GameQuestion.objects.filter(
            generator_key='equilibrium').exists())

    def test_purge_figure_questions_removes_only_them(self):
        from django.core.management import call_command
        from io import StringIO
        other = GameQuestion.objects.create(
            problem=None, question_type='numeric', question=u'архетип',
            options=[], correct_value='1', lang='ru', is_generated=True,
            generator_key='equilibrium')
        call_command('purge_figure_questions', stdout=StringIO())
        self.assertFalse(GameQuestion.objects.filter(id=self.gq.id).exists())
        self.assertTrue(GameQuestion.objects.filter(id=other.id).exists())
