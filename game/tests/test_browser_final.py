# -*- coding: utf-8 -*-
u"""Экран итога в настоящем браузере (фаза P3, ADR 0111).

Раннер `browser_final.mjs`: счёт и основная кнопка на первом экране 1440×800,
ошибки списком без клика, без очков нет «Где набрано», гостю — строка входа
вместо истории, дата итога в часовом поясе зрителя, телефон без прокрутки вбок.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import os

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import tag

from game import config
from game.models import GameQuestion, GameResult
from game.tests.test_browser_layout import run_node
from problems.models import Problem, User

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_final.mjs')
CHECKS = {'score_and_first_action_above_800', 'misses_listed_without_a_click',
          'student_compares_with_history', 'zero_points_no_points_card',
          'guest_login_line_instead_of_history', 'date_in_the_viewers_time_zone',
          'mobile_final_no_side_scroll'}


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
class FinalBrowserTest(StaticLiveServerTestCase):
    def setUp(self):
        cache.clear()
        qtype = config.MODES['blitz']['question_type']
        topics = ['Спрос и предложение', 'Эластичность', 'Монополия']
        for i in range(40):
            text = 'Вопрос итога %d: что изучает микроэкономика?' % i
            problem = Problem.objects.create(title='', statement=text, answer='',
                                             problem_type='тест: один ответ', status='published')
            GameQuestion.objects.create(
                problem=problem, question_type=qtype, question=text,
                options=['Фирмы', 'Страны', 'Планеты', 'Климат'], correct_index=0,
                difficulty=1 + i % 5, topics=[topics[i % 3]], lang='ru')
        self.student = User.objects.create_user(username='final_student', password='p12345')
        for score in (120, 260):
            GameResult.objects.create(user=self.student, mode='blitz', score=score, ranked=True,
                                      correct_count=6, total_count=8, wrong_count=2, skip_count=1,
                                      economy_version=config.ECONOMY_VERSION)

    def test_final_screen(self):
        self.client.force_login(self.student)
        data = run_node(self, RUNNER, {
            'RUSH_BASE_URL': self.live_server_url,
            'RUSH_SESSION': self.client.cookies[settings.SESSION_COOKIE_NAME].value,
        }, 400)
        self.assertEqual(set(data['checks']), CHECKS, data.get('error'))
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'экран итога:\n%s' % failed)
