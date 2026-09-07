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
        """⚠️ Переведён на экономику v2. Абсолютные числа здесь больше не
        сверяются — их сторожит game/tests/test_scoring.py по контрольным
        значениям задания. Здесь проверяется ОТНОШЕНИЕ: тот же вопрос на
        последней жизни стоит ровно в LAST_LIFE_MULTIPLIER раз дороже."""
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'blitz'}).json()
        qid = d['question']['id']
        first = self._answer(qid, 0)          # 3 жизни — множителя нет
        self.assertGreater(first['points'], 0)

        # две ошибки → осталась одна жизнь
        for _ in range(2):
            qid = self._next()
            self._answer(qid, 1)
        qid = self._next()
        last = self._answer(qid, 0)
        self.assertEqual(last['lives'], 1)
        # Серия после двух ошибок снова 1, вопросы одинаковые, время ответа
        # в тесте пренебрежимо мало у обоих — остаётся только множитель.
        self.assertAlmostEqual(last['points'] / first['points'],
                               config.LAST_LIFE_MULTIPLIER, places=2)

    def test_client_gets_the_multiplier_from_config(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual(cfg['last_life_multiplier'],
                         config.LAST_LIFE_MULTIPLIER)


class PointsByDifficultyTests(TestCase):
    """Очки по сложности ВКЛЮЧЕНЫ (экономика v2).

    Раньше здесь был задел с нейтральными значениями: таблица существовала,
    но все пятеро стоили одинаково. Задача «включить очки по сложности
    после накопления статистики» закрыта — таблица боевая.
    """

    def test_every_level_has_its_own_price(self):
        vals = [config.BASE_BY_DIFFICULTY[d]
                for d in range(config.DIFFICULTY_MIN, config.DIFFICULTY_MAX + 1)]
        self.assertEqual(len(set(vals)), 5, 'сложности стоят одинаково')
        self.assertEqual(vals, sorted(vals), 'дороже должно быть сложнее')

    def test_scoring_goes_through_the_table(self):
        """Начисление читает таблицу, а не константу."""
        make_q(difficulty=5)
        d = self.client.get(reverse('game:session_start'),
                            {'mode': 'blitz'}).json()
        body = self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': d['question']['id'], 'choice': 0}),
            content_type='application/json').json()
        # 5★ отвечен мгновенно и без фильтров: база 250, бонус за скорость
        # и ×1,3 за отсутствие фильтров — итог заведомо больше базы 3★.
        self.assertGreater(body['points'], config.BASE_BY_DIFFICULTY[3])

    def test_client_gets_the_table_not_a_single_number(self):
        """Подсказки на экране обязаны знать реальные цены сложностей."""
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual({int(k): v for k, v in
                          cfg['base_by_difficulty'].items()},
                         config.BASE_BY_DIFFICULTY)
        self.assertEqual(cfg['economy_version'], config.ECONOMY_VERSION)


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


class ShareCardIsGoneTests(TestCase):
    u"""Карточки результата на canvas больше нет (08.09.2026).

    ⚠️ ЧТО БЫЛО. Класс `ShareCardTests` сторожил рисование карточки: два
    размера (1200×630 и 1080×1350 под сторис), ожидание шрифтов, тёмный фон
    независимо от темы сайта, пустую полосу под будущий домен, кривую счёта
    и ленту рекорда. Решением владельца 08.09.2026 всё это удалено вместе с
    тремя кнопками из четырёх: остаётся одна кнопка «Поделиться», ведущая
    на публичную страницу результата.

    Проверки не выброшены, а ПЕРЕВЁРНУТЫ: карточка не имеет права вернуться
    незамеченной, а вместе с ней — три захардкоженных цвета, которые были
    осознанным исключением из правила «каждый цвет через var(--…)».
    """

    def setUp(self):
        with open(TEMPLATE, encoding='utf-8') as f:
            self.page = f.read()

    def test_nothing_of_the_card_is_left(self):
        for gone in ('drawShareCard', 'drawCurve', 'drawHearts', 'drawDonut',
                     'drawRecordRibbon', 'cardFont', 'withFonts',
                     'CARD_SIZES', 'CARD_LAYOUT', 'document.fonts.ready',
                     'НОВЫЙ РЕКОРД', 'linkBand'):
            self.assertNotIn(gone, self.page, gone)

    def test_the_hardcoded_card_palette_left_with_it(self):
        u"""Набор CARD жил как осознанное исключение из канона: canvas не
        читает CSS-переменные, а картинка уезжала наружу. Картинки нет —
        исключению не место.

        ⚠️ Проверяется САМ НАБОР и его собственные цвета, а не любой хекс в
        файле: рядом живёт конфетти со своей палитрой, и оно к карточке
        отношения не имеет. Тест, который цеплял бы и его, краснел бы на
        ровном месте."""
        self.assertNotIn('var CARD = {', self.page)
        for colour in ("'#0d0d12'", "'#161b25'", "'#4a4a55'", "'#96969f'"):
            self.assertNotIn(colour, self.page, colour)
