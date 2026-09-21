# -*- coding: utf-8 -*-
u"""Экран раунда в настоящем браузере (фаза P2, ADR 0109 и 0110).

Раннер `browser_round.mjs`: отсчёт 3-2-1, нет прокрутки на 1440×800 (Блиц с
пятью вариантами, Классика с условием в 600 знаков), время «m:ss», шапка сайта
скрыта, сетка вариантов, разбор ошибки 3000 ± 100 мс между pause и resume, пробел
раньше, ответ сразу после разбора уходит только после подкачки вопроса, чип
рекорда у вошедшего и его отсутствие у гостя, телефон 390×844 без прокрутки
вбок и с кнопками от 44 px.

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

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_round.mjs')
CHECKS = {'countdown_holds_question_and_clock', 'enter_skips_countdown',
          'blitz_five_options_no_scroll', 'timer_is_m_ss', 'site_header_hidden',
          'option_grid_three_columns', 'guest_has_no_record_chip',
          'digits_do_not_answer_during_reveal', 'reveal_pause_to_resume_3000ms',
          'space_ends_reveal_early', 'classic_600_chars_no_scroll', 'student_record_chip',
          'mobile_reveal_no_side_scroll_targets_44', 'answer_waits_for_prefetch'}

LONG = ('Фирма-монополист выпускает товар с функцией спроса Q = 120 − 2P и постоянными '
        'предельными издержками MC = 20. Государство вводит потоварный налог t на каждую '
        'проданную единицу и хочет, чтобы выпуск монополиста сократился ровно на четверть '
        'по сравнению с исходным равновесием без налога. При этом фирма продолжает '
        'максимизировать прибыль, а кривая спроса и издержки не меняются. Найдите ставку '
        'налога t, при которой это условие выполняется, и укажите её числом без единиц '
        'измерения. Дроби можно записывать через слэш, а десятичные — через запятую. '
        'Ответ округлите до двух знаков после запятой, если потребуется.')


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium, а проверка 3000 ± 100 мс под конкуренцией за процессор краснела бы
# по чужой вине. Живой сервер и браузер поделить между воркерами нельзя.
@tag('game', 'browser', 'serial')
class RoundBrowserTest(StaticLiveServerTestCase):
    def setUp(self):
        cache.clear()
        for key, options in (('blitz', ['Фирмы', 'Страны', 'Планеты', 'Климат', 'Никто']),
                             ('classic', [])):
            qtype = config.MODES[key]['question_type']
            for i in range(config.MIN_PLAYABLE + 4):
                text = (LONG + ' №%d' % i) if key == 'classic' else 'Вопрос %d: что изучает микроэкономика?' % i
                problem = Problem.objects.create(title='', statement=text, answer='',
                                                 problem_type='тест: один ответ', status='published')
                GameQuestion.objects.create(
                    problem=problem, question_type=qtype, question=text, options=options,
                    correct_index=0, correct_value='30', difficulty=3, topics=[], lang='ru')
        self.student = User.objects.create_user(username='round_student', password='p12345')
        GameResult.objects.create(user=self.student, mode='blitz', score=1260, correct_count=9,
                                  total_count=10, wrong_count=1, ranked=True,
                                  economy_version=config.ECONOMY_VERSION)

    def test_round_screen(self):
        self.client.force_login(self.student)
        data = run_node(self, RUNNER, {
            'RUSH_BASE_URL': self.live_server_url,
            'RUSH_SESSION': self.client.cookies[settings.SESSION_COOKIE_NAME].value,
        }, 300)
        self.assertEqual(set(data['checks']), CHECKS, data.get('error'))
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'экран раунда:\n%s' % failed)
