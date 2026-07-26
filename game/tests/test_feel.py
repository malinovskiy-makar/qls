"""
Тесты «ощущений» забега (Фаза 6): эскалация, последняя жизнь, звук,
карточка результата, задел под очки по сложности.
"""
import json
import os
import re

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from game import config
from game.models import GameQuestion, GameSet, make_code
from game.views import escalation_slice
from problems.models import Problem

TEMPLATE = os.path.join(settings.BASE_DIR, 'game', 'templates', 'game',
                        'game.html')
SOUND_JS = os.path.join(settings.BASE_DIR, 'game', 'static', 'game',
                        'sound.js')


def make_q(difficulty=3, qtype='single', **kw):
    p = Problem.objects.create(
        title='Т', statement='Условие', problem_type='тест: один ответ',
        answer='а', status=Problem.Status.PUBLISHED)
    defaults = dict(question_type=qtype, question='Вопрос?',
                    options=['а', 'б', 'в'], correct_index=0,
                    difficulty=difficulty, topics=['Спрос и предложение'],
                    lang='ru', source_group='books')
    defaults.update(kw)
    return GameQuestion.objects.create(problem=p, **defaults)


class EscalationTests(TestCase):
    """Полоса сложности двигается комбо и МЯГКО расширяется при пустоте."""

    def test_bands_come_from_config(self):
        self.assertEqual(config.escalation_band(0), (1, 2))
        self.assertEqual(config.escalation_band(2), (1, 2))
        self.assertEqual(config.escalation_band(3), (2, 3))
        self.assertEqual(config.escalation_band(5), (2, 3))
        self.assertEqual(config.escalation_band(6), (3, 4))
        self.assertEqual(config.escalation_band(9), (4, 5))
        self.assertEqual(config.escalation_band(99), (4, 5))

    def test_slice_picks_the_band(self):
        rows = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)]
        self.assertEqual(sorted(escalation_slice(rows, 0)), [(1, 1), (2, 2)])
        self.assertEqual(sorted(escalation_slice(rows, 9)), [(4, 4), (5, 5)])

    def test_empty_band_widens_instead_of_ending_the_run(self):
        """★ Полоса МЯГКАЯ: пусто в ней — расширяемся, а не роняем забег."""
        rows = [(1, 1)]                       # есть только лёгкий вопрос
        got = escalation_slice(rows, 9)       # комбо просит 4–5
        self.assertEqual(got, rows)

    def test_widening_stops_at_the_nearest_non_empty_band(self):
        rows = [(1, 1), (2, 3)]
        got = escalation_slice(rows, 9)       # 4–5 пусто → 3–5 → нашли 3
        self.assertEqual(got, [(2, 3)])

    def test_empty_input_gives_empty_output(self):
        self.assertEqual(escalation_slice([], 5), [])

    def test_user_filter_is_a_hard_frame(self):
        """Эскалация ходит ВНУТРИ фильтра игрока: она получает уже
        отфильтрованные строки и расширить рамку не может."""
        make_q(difficulty=1)
        hard = make_q(difficulty=5)
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'blitz', 'dmin': 5, 'dmax': 5}).json()
        self.assertEqual(d['question']['id'], hard.id)

    def test_no_escalation_in_a_curated_run(self):
        """В наборе список задан — двигать нечего."""
        easy = [make_q(difficulty=1) for _ in range(3)]
        make_q(difficulty=5)
        gset = GameSet.objects.create(
            code=make_code(), mode='blitz', kind='custom',
            question_ids=[q.id for q in easy], filter_snapshot={})
        d = self.client.get(reverse('game:session_start_set',
                                    args=[gset.code])).json()
        self.assertIn(d['question']['id'], [q.id for q in easy])


class LastLifeTests(TestCase):
    """Множитель последней жизни считает СЕРВЕР."""

    def setUp(self):
        self.qs = [make_q() for _ in range(8)]

    def _answer(self, qid, choice):
        return self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid, 'choice': choice}),
            content_type='application/json').json()

    def _next(self):
        return self.client.get(reverse('game:question')).json()['question']['id']

    def test_multiplier_applies_only_on_the_last_life(self):
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'blitz'}).json()
        qid = d['question']['id']
        first = self._answer(qid, 0)          # 3 жизни — множителя нет
        self.assertEqual(first['points'], config.BASE_POINTS)

        # две ошибки → осталась одна жизнь
        for _ in range(2):
            qid = self._next()
            self._answer(qid, 1)
        qid = self._next()
        last = self._answer(qid, 0)
        self.assertEqual(last['lives'], 1)
        self.assertEqual(last['points'],
                         config.BASE_POINTS * config.LAST_LIFE_MULTIPLIER)

    def test_client_gets_the_multiplier_from_config(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual(cfg['last_life_multiplier'],
                         config.LAST_LIFE_MULTIPLIER)


class PointsByDifficultyTests(TestCase):
    """Задел под очки по сложности: механизм есть, поведение не меняется."""

    def test_values_are_neutral_today(self):
        self.assertEqual(set(config.POINTS_BY_DIFFICULTY.values()),
                         {config.BASE_POINTS})

    def test_every_level_has_a_value(self):
        for level in range(config.DIFFICULTY_MIN, config.DIFFICULTY_MAX + 1):
            self.assertIn(level, config.POINTS_BY_DIFFICULTY)

    def test_scoring_goes_through_the_table(self):
        """Начисление читает таблицу — иначе включить её потом можно будет
        только переписыванием api_answer."""
        make_q(difficulty=5)
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'blitz'}).json()
        with self.settings():
            config.POINTS_BY_DIFFICULTY[5] = 250
            try:
                body = self.client.post(
                    reverse('game:answer'),
                    json.dumps({'question_id': d['question']['id'],
                                'choice': 0}),
                    content_type='application/json').json()
                self.assertEqual(body['points'], 250)
            finally:
                config.POINTS_BY_DIFFICULTY[5] = config.BASE_POINTS


class SoundModuleTests(TestCase):
    """Звук: один вход наружу, состояние в localStorage, не единственный
    канал информации."""

    def setUp(self):
        with open(SOUND_JS, encoding='utf-8') as f:
            self.src = f.read()
        with open(TEMPLATE, encoding='utf-8') as f:
            self.page = f.read()

    def test_module_parses(self):
        import shutil
        import subprocess
        if shutil.which('node') is None:
            self.skipTest('node не установлен')
        p = subprocess.run(['node', '--check', SOUND_JS],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_only_one_global(self):
        self.assertIn('window.rushSound = api;', self.src)
        self.assertEqual(len(re.findall(r'\bwindow\.\w+\s*=', self.src)), 1)

    def test_no_audio_files(self):
        """Синтез, а не сэмплы: ни мегабайтов, ни лицензий."""
        self.assertNotRegex(self.src, r'\.(mp3|wav|ogg|m4a)')
        self.assertIn('AudioContext', self.src)

    def test_state_lives_in_local_storage_and_defaults_to_on(self):
        self.assertIn("'econ_rush_sound'", self.src)
        self.assertIn("localStorage.getItem(KEY) !== 'off'", self.src)

    def test_life_loss_is_a_separate_event_from_a_wrong_answer(self):
        """Игрок обязан слышать разницу: ошибка и сгоревшее сердце — не
        одно и то же событие."""
        self.assertIn('lifeLost:', self.src)
        self.assertIn('wrong:', self.src)
        self.assertIn("'lifeLost'", self.page)

    def test_page_includes_the_module_and_the_toggle(self):
        self.assertIn("{% static 'game/sound.js' %}", self.page)
        self.assertIn("id=\"btn-sound\"", self.page)

    def test_results_screen_is_silent_except_for_a_record(self):
        """На экране результатов звучит только рекорд — это событие."""
        m = re.search(r'function endRun\(reason\) \{(.*?)\n  \}', self.page,
                      re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("rush('over')", body)
        self.assertIn("rush('record')", body)
        # графики строятся отдельно и звука не издают
        charts = re.search(r'function buildCharts\(\) \{(.*?)\n  \}',
                           self.page, re.S)
        self.assertIsNotNone(charts)
        self.assertNotIn('rush(', charts.group(1))


class ShareCardTests(TestCase):
    """Карточка результата: два размера, тёмная, пустая полоса под ссылку."""

    def setUp(self):
        with open(TEMPLATE, encoding='utf-8') as f:
            self.page = f.read()

    def test_two_sizes_are_declared(self):
        self.assertIn("wide:  { w: 1200, h: 630 }", self.page)
        self.assertIn("story: { w: 1080, h: 1350 }", self.page)

    def test_card_waits_for_fonts(self):
        """На системном шрифте карточка выйдет разной на разных
        устройствах — ждём document.fonts.ready до отрисовки."""
        self.assertIn('document.fonts.ready', self.page)
        self.assertRegex(self.page, r'withFonts\(function \(\) \{\s*\n\s*drawShareCard')

    def test_link_band_is_reserved_and_empty(self):
        """Домена нет; 127.0.0.1 на карточке недопустим. Полоса
        зарезервирована фиксированной высотой и пока пустая."""
        m = re.search(r'function drawShareCard\(kind\) \{(.*?)\n  \}\n',
                      self.page, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('linkBand', body)
        self.assertNotIn('shareInfo', body)     # URL на карточку не попадает

    def test_card_is_always_dark(self):
        self.assertIn("bg: '#0d0d12'", self.page)

    def test_curve_is_the_main_element(self):
        self.assertIn('function drawCurve', self.page)
        self.assertIn('combo_curve', self.page)

    def test_record_ribbon_exists(self):
        self.assertIn('НОВЫЙ РЕКОРД', self.page)
