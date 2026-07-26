"""
Тесты пятого режима «График» (Фаза 7).

Неверные варианты — НЕ выдуманные картинки: это чертёж того же архетипа,
посчитанный на его ТИПОВОЙ ОШИБКЕ (error_variants уже умеет их вычислять
для дистракторов). Новой математики режим не потребовал.
"""
import json
import os
import random
import re

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from game import config
from game.generators import base as gen_base
from game.generators.registry import ARCHETYPES
from game.models import GameQuestion

TEMPLATE = os.path.join(settings.BASE_DIR, 'game', 'templates', 'game',
                        'game.html')
# Архетипы, у которых есть чертёж (эталонные) — только они дают вопросы
# режима «График».
FIGURE_ARCHETYPES = ['monopoly', 'equilibrium', 'tax_subsidy', 'ppf_single']


def make_figure_question(**kw):
    rng = random.Random(4242)
    q = gen_base.generate_figure_choice(ARCHETYPES['equilibrium'], rng)
    defaults = dict(
        problem=None, part=None, question_type='figure_choice',
        question=q['statement'], options=q['options'],
        correct_index=q['correct_index'], difficulty=q['difficulty'],
        topics=q['topics'], lang='ru', is_generated=True,
        generator_key=q['generator_key'], gen_params=q['params'],
        gen_solution=q['solution_text'], figure=q['figure'])
    defaults.update(kw)
    return GameQuestion.objects.create(**defaults)


class GenerationTests(TestCase):
    def test_four_distinct_figures_with_exactly_one_correct(self):
        rng = random.Random(1)
        for key in FIGURE_ARCHETYPES:
            q = gen_base.generate_figure_choice(ARCHETYPES[key], rng)
            self.assertEqual(len(q['options']),
                             gen_base.FIGURE_CHOICE_OPTIONS, key)
            dumps = [json.dumps(o, sort_keys=True) for o in q['options']]
            self.assertEqual(len(set(dumps)), len(dumps),
                             '%s: чертежи повторяются' % key)
            self.assertIsInstance(q['correct_index'], int)
            self.assertTrue(0 <= q['correct_index'] < len(q['options']), key)
            # верный вариант совпадает с чертежом «для разбора»
            self.assertEqual(q['options'][q['correct_index']], q['figure'])

    def test_distractors_are_valid_geometry(self):
        rng = random.Random(7)
        for key in FIGURE_ARCHETYPES:
            q = gen_base.generate_figure_choice(ARCHETYPES[key], rng)
            for fig in q['options']:
                self.assertIn('kind', fig)
                self.assertGreater(fig['xmax'], 0, key)
                self.assertGreater(fig['ymax'], 0, key)
                for ln in fig.get('lines', []):
                    self.assertEqual(len(ln['from']), 2)
                    self.assertEqual(len(ln['to']), 2)

    def test_all_variants_share_one_frame(self):
        """★ Иначе игрок выбирает по числам на осях, а не по экономике.

        Рамка одна по построению: неверные варианты получаются НЕ
        пересчётом figure() на испорченном решении (там менялась бы рамка
        и кривые превращались в обрубки), а сдвигом точек и засечек на
        готовом верном чертеже."""
        rng = random.Random(11)
        for key in FIGURE_ARCHETYPES:
            q = gen_base.generate_figure_choice(ARCHETYPES[key], rng)
            axes = {(o['xmax'], o['ymax']) for o in q['options']}
            self.assertEqual(len(axes), 1, '%s: рамки разъехались' % key)

    def test_curves_are_identical_across_variants(self):
        """Кривые у всех четырёх одни и те же — отличается только то, где
        отмечен оптимум. Иначе неверный вариант виден как «сломанная
        картинка», а не как экономическая ошибка."""
        rng = random.Random(13)
        for key in FIGURE_ARCHETYPES:
            q = gen_base.generate_figure_choice(ARCHETYPES[key], rng)
            solid = [tuple(sorted(
                (ln['role'], tuple(ln['from']), tuple(ln['to']))
                for ln in o.get('lines', []) if not ln.get('dash')))
                for o in q['options']]
            self.assertEqual(len(set(solid)), 1,
                             '%s: сплошные кривые разъехались' % key)

    def test_distractor_marks_are_integers(self):
        """Значение ошибки попадает засечкой на ось: «86,6666» там налезает
        на соседей."""
        rng = random.Random(17)
        for key in FIGURE_ARCHETYPES:
            q = gen_base.generate_figure_choice(ARCHETYPES[key], rng)
            for fig in q['options']:
                for mk in fig.get('marks', []):
                    self.assertEqual(float(mk['at']), int(float(mk['at'])),
                                     '%s: нецелая засечка %s' % (key, mk['at']))

    def test_statement_is_short_and_asks_about_the_figure(self):
        rng = random.Random(3)
        q = gen_base.generate_figure_choice(ARCHETYPES['equilibrium'], rng)
        self.assertLessEqual(len(q['statement']), gen_base.LIMIT_SHORT)
        self.assertIn('чертеж', q['statement'].lower())

    def test_batch_produces_unique_questions(self):
        rng = random.Random(5)
        batch = gen_base.generate_batch(ARCHETYPES['monopoly'], rng,
                                        'figure_choice', 8)
        self.assertGreater(len(batch), 0)
        keys = {(b['statement'], json.dumps(b['options'], sort_keys=True))
                for b in batch}
        self.assertEqual(len(keys), len(batch))

    def test_archetype_without_a_figure_cannot_produce_this_type(self):
        rng = random.Random(2)
        with self.assertRaises(gen_base.GenerationError):
            gen_base.generate_figure_choice(ARCHETYPES['price_index'], rng)


@override_settings(GAME_GENERATED_ENABLED=True)
class ServingTests(TestCase):
    def setUp(self):
        self.gq = make_figure_question()

    def test_correct_index_never_leaks_into_the_question_payload(self):
        """★ Анти-чит: правильный индекс — только в ответе на ответ."""
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        q = d['question']
        self.assertEqual(q['type'], 'figure_choice')
        self.assertEqual(len(q['options']), 4)
        for banned in ('correct_index', 'correct_indices', 'correct_value'):
            self.assertNotIn(banned, q)
        self.assertNotIn('correct', json.dumps(q))

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

    def test_mode_timings_come_from_config(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        self.assertEqual(d['mode']['duration'],
                         config.MODES['figure']['duration'])
        self.assertEqual(d['mode']['time_correct'],
                         config.MODES['figure']['time_correct'])
        self.assertEqual(d['mode']['lives'], config.MODES['figure']['lives'])

    def test_mode_is_on_the_start_screen_when_the_flag_is_on(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual(cfg['pool_counts']['figure'], 1)


@override_settings(GAME_GENERATED_ENABLED=False)
class FlagOffTests(TestCase):
    """Вопросы режима бывают только сгенерированные — при выключенном
    флаге режима нет ни в выдаче, ни на экране."""

    def setUp(self):
        self.gq = make_figure_question()

    def test_pool_count_is_zero(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual(cfg['pool_counts']['figure'], 0)

    def test_starting_the_mode_gives_an_empty_run_not_a_leak(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'figure'}).json()
        self.assertTrue(d['pool_empty'])
        self.assertIsNone(d['question'])


class ClientTests(TestCase):
    """Разметка и логика клиента для режима."""

    def setUp(self):
        with open(TEMPLATE, encoding='utf-8') as f:
            self.src = f.read()

    def test_tiles_are_drawn_by_the_shared_renderer(self):
        """Второго рисователя не заводим ни под каким видом."""
        self.assertIn('window.drawFigure(fig)', self.src)
        self.assertEqual(len(re.findall(r'function drawFigure', self.src)), 0)

    def test_narrow_screen_zooms_a_tile_before_answering(self):
        """На 380px четыре чертежа нечитаемы: первый тап увеличивает,
        второй засчитывает."""
        self.assertIn('function tileClick(i, btn)', self.src)
        self.assertIn("if (!NARROW()) { answer(i); return; }", self.src)
        self.assertIn("if (zoomedTile === btn) { answer(i); return; }", self.src)
        self.assertIn('.opts.opts-figure.has-zoom .opt-tile.zoomed', self.src)

    def test_mode_meta_has_the_figure_entry(self):
        self.assertIn("figure:  { emoji: '📈'", self.src)
        self.assertIn("mock: 'tiles'", self.src)

    def test_keyboard_selects_a_tile(self):
        # клавиши 1–6 уже ведут в answer(i) для не-multi типов
        self.assertIn("if (e.key >= '1' && e.key <= '6')", self.src)
