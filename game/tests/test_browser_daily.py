# -*- coding: utf-8 -*-
u"""Вызов дня и доска дня в настоящем браузере (фаза P4).

Раннер `browser_daily.mjs`: `?auto=1` не показывает стартовый экран до ответа
сервера, страница вызова без прокрутки на 1440×800 и столбиком на телефоне,
доска дня в две колонки на ПК и в ширину экрана на телефоне.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import os

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import tag

from game import config, daily as daily_mod
from game.models import GameQuestion, GameResult, make_code
from game.tests.test_browser_layout import run_node
from problems.models import Problem, User

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_daily.mjs')
CHECKS = {'autostart_no_start_flash', 'daily_desktop_row_no_scroll', 'daily_mobile_column',
          'board_desktop_two_columns', 'board_mobile_fits'}


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
class DailyBrowserTest(StaticLiveServerTestCase):
    def setUp(self):
        cache.clear()
        options = {'boolean': ['Верно', 'Неверно'], 'single': ['Фирмы', 'Страны', 'Планеты', 'Климат'],
                   'multi': ['Доходы', 'Цены', 'Мода', 'Погода'], 'numeric': []}
        for mode in ('bullet', 'blitz', 'rapid', 'classic'):
            qtype = config.MODES[mode]['question_type']
            for i in range(20):
                text = 'Вопрос вызова дня %d: что изучает микроэкономика?' % i
                problem = Problem.objects.create(title='', statement=text, answer='',
                                                 problem_type='тест: один ответ', status='published')
                GameQuestion.objects.create(
                    problem=problem, question_type=qtype, question=text, options=options[qtype],
                    correct_index=0, correct_indices=[0] if qtype == 'multi' else [],
                    correct_value='1' if qtype == 'numeric' else '', difficulty=2,
                    topics=['Спрос и предложение'], lang='ru')
        self.student = User.objects.create_user(username='daily_student', password='p12345')
        blitz = daily_mod.get_daily_set('blitz')
        for i in range(7):
            user = User.objects.create_user(username='player_%d' % i, password='p12345')
            GameResult.objects.create(code=make_code(), user=user, game_set=blitz, mode='blitz',
                                      score=300 - i * 30, correct_count=8, total_count=12,
                                      max_combo=1.5, ended_reason='set_done')
        # Сыгранная Пуля: одна карточка приглушена, на ней счёт и место.
        GameResult.objects.create(code=make_code(), user=self.student, mode='bullet',
                                  game_set=daily_mod.get_daily_set('bullet'), score=120,
                                  correct_count=5, total_count=9, max_combo=1.25, ended_reason='lives')
        self.code = daily_mod.get_daily_set('rapid').code

    def test_daily_pages(self):
        self.client.force_login(self.student)
        data = run_node(self, RUNNER, {
            'RUSH_BASE_URL': self.live_server_url,
            'RUSH_SESSION': self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            'RUSH_DAILY_CODE': self.code,
        }, 300)
        self.assertEqual(set(data['checks']), CHECKS, data.get('error'))
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'вызов дня:\n%s' % failed)
