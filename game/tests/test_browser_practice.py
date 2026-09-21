# -*- coding: utf-8 -*-
u"""«Бесконечные тесты» в настоящем браузере (фаза P5, ADR 0114).

Раннер `browser_practice.mjs`: полоса и счётчики, разбор после ответа со ссылкой
или решением, обратимый пропуск и просмотр истории, свёртка ленты на 30 вопросах,
«Закончить?» и экран итога, 1440×800 без прокрутки, телефон с листанием внизу.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import os

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings, tag

from game.models import GameQuestion
from game.tests.test_browser_layout import run_node
from problems.models import Problem

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_practice.mjs')
CHECKS = {'hud_filter_and_four_tallies', 'wrong_answer_feedback_with_catalog_link', 'hover_is_border_only',
          'history_is_read_only', 'next_label_by_situation', 'skip_is_reversible',
          'escape_asks_then_result_screen', 'many_questions_fold_and_jump',
          'generated_solution_without_catalog_link', 'desktop_no_scroll_with_solution',
          'mobile_bottom_bar_no_side_scroll', 'mobile_result_no_side_scroll'}
GEN_TOPIC = 'Теория потребителя и полезность'


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
@override_settings(GAME_GENERATED_ENABLED=True)
class PracticeBrowserTest(StaticLiveServerTestCase):
    def setUp(self):
        cache.clear()
        for i in range(40):
            text = 'Вопрос практики %d: что изучает микроэкономика?' % i
            problem = Problem.objects.create(title='', statement=text, answer='',
                                             problem_type='тест: один ответ', status='published')
            GameQuestion.objects.create(
                problem=problem, question_type='single', question=text,
                options=['Фирмы', 'Страны', 'Планеты', 'Климат'], correct_index=0,
                difficulty=2, topics=['Эластичность'], lang='ru')
        for i in range(3):
            GameQuestion.objects.create(
                problem=None, question_type='single', is_generated=True,
                question='Сгенерированный вопрос %d: спрос Qd = 120 − 2P, предложение Qs = 4P. '
                         'Найдите равновесную цену.' % i,
                options=['20', '15', '24', '30', '40'], correct_index=0, difficulty=2,
                topics=[GEN_TOPIC], lang='ru',
                gen_solution='Приравниваем спрос и предложение: 120 − 2P = 4P, откуда 6P = 120 и P = 20. '
                             'Равновесный объём Q = 4 · 20 = 80 – он одинаков по обеим функциям.')

    def test_practice_screen(self):
        data = run_node(self, RUNNER, {'RUSH_BASE_URL': self.live_server_url}, 400)
        self.assertEqual(set(data['checks']), CHECKS, data.get('error'))
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'бесконечные тесты:\n%s' % failed)
