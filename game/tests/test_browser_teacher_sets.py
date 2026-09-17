# -*- coding: utf-8 -*-
u"""Сборка игрового набора учителем в настоящем браузере (фаза P7, ADR 0116).

Раннер `browser_teacher_sets.mjs`: набор переживает смену темы, «Показать ещё 20» и
перезагрузку страницы, стрелки меняют порядок, смена режима спрашивает, сохранение
чистит черновик; сборка и страница набора на телефоне без прокрутки вбок.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import os

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import tag

from game.models import GameQuestion, GameResult, GameSet, make_code
from game.tests.test_browser_layout import run_node
from problems.models import Problem, User

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_teacher_sets.mjs')
CHECKS = {'set_survives_filters_and_paging', 'set_restored_after_reload', 'arrows_reorder_question_ids',
          'mode_switch_asks_when_not_empty', 'save_clears_the_draft', 'builder_and_detail_mobile_no_side_scroll'}


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
class TeacherSetsBrowserTest(StaticLiveServerTestCase):
    def setUp(self):
        cache.clear()
        topics = ['Монополия', 'Рынок труда']
        for i in range(60):
            text = 'Вопрос для набора %d: что происходит с ценой?' % i
            problem = Problem.objects.create(title='', statement=text, answer='', problem_type='тест: один ответ',
                                             status='published')
            GameQuestion.objects.create(problem=problem, question_type='single', question=text,
                                        options=['(a) растёт;', 'падает', 'не меняется'], correct_index=0,
                                        difficulty=1 + i % 5, topics=[topics[i % 2]], lang='ru', source_group='vsosh')
        for i in range(5):
            text = 'Данетка %d: спрос падает при росте цены.' % i
            problem = Problem.objects.create(title='', statement=text, answer='', problem_type='тест: один ответ',
                                             status='published')
            GameQuestion.objects.create(problem=problem, question_type='boolean', question=text,
                                        options=['Верно', 'Неверно'], correct_index=0, difficulty=2,
                                        topics=['Монополия'], lang='ru')
        self.teacher = User.objects.create_user(username='browser_teacher', password='p12345', role='teacher')
        gset = GameSet.objects.create(code=make_code(), mode='blitz', kind='custom', title='Готовый набор',
                                      author=self.teacher, attempts_allowed=1,
                                      question_ids=list(GameQuestion.objects.filter(question_type='single')
                                                        .values_list('id', flat=True)[:5]))
        GameResult.objects.create(code=make_code(), mode='blitz', game_set=gset, user=None, score=90,
                                  correct_count=3, total_count=5)

    def test_builder(self):
        self.client.force_login(self.teacher)
        data = run_node(self, RUNNER, {
            'RUSH_BASE_URL': self.live_server_url,
            'RUSH_SESSION': self.client.cookies[settings.SESSION_COOKIE_NAME].value,
        }, 300)
        self.assertEqual(set(data['checks']), CHECKS, data.get('error'))
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'сборка набора:\n%s' % failed)
