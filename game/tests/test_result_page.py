# -*- coding: utf-8 -*-
u"""Публичная страница результата `/game/r/<код>/` (фаза P6, ADR 0115).

Ник игрока (у анонимного — «Игрок»), исход словами для всех пяти причин,
склонение «очко / очка / очков», главная кнопка по роду раунда, место в таблице
только у зачётного, страница без входа и без записи в базу.
"""
import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from game import config, daily as daily_mod
from game.models import GameResult, make_code
from game.tests.test_sets import make_q, make_set
from game.views import points_word
from problems.models import User


class ResultPageP6Tests(TestCase):
    def setUp(self):
        self.qs = make_q(5)
        self.sonya = User.objects.create_user(username='Sonya_kitty', password='pw12345')

    def result(self, **kw):
        data = dict(code=make_code(), mode='blitz', score=225, correct_count=11, total_count=14,
                    wrong_count=1, max_combo=1.5, ended_reason='time')
        data.update(kw)
        return GameResult.objects.create(**data)

    def page(self, result, status=200):
        r = self.client.get(reverse('game:result', args=[result.code]))
        self.assertEqual(r.status_code, status)
        return r.content.decode()

    def test_nick_for_a_player_and_player_for_anonymous(self):
        html = self.page(self.result(user=self.sonya))
        self.assertIn('<p class="nm">Sonya_kitty</p>', html)
        self.assertIn('Sonya_kitty: 225 очков в Wecon Rush', html)
        self.assertIn('Вызвать Sonya_kitty на дуэль', html)
        anon = self.page(self.result(user=None))
        self.assertIn('<p class="nm">Игрок</p>', anon)
        self.assertIn('<title>225 очков в Wecon Rush', anon)
        self.assertNotIn('Вызвать Игрок', anon)

    def test_five_endings_have_five_words(self):
        words = set()
        for reason in ('lives', 'time', 'set_done', 'pool_empty', 'quit'):
            html = self.page(self.result(ended_reason=reason))
            words.add(html.split('<b id="ending">', 1)[1].split('</b>', 1)[0])
        self.assertEqual(words, {'жизни кончились', 'время вышло', 'прошёл набор до конца',
                                 'вопросы кончились', 'вышел из раунда'})

    def test_points_are_declined(self):
        expected = {1: 'очко', 2: 'очка', 5: 'очков', 11: 'очков', 21: 'очко', 22: 'очка',
                    25: 'очков', 101: 'очко', 111: 'очков', 201: 'очко'}
        self.assertEqual({n: points_word(n) for n in expected}, expected)
        self.assertIn('<title>22 очка в Wecon Rush', self.page(self.result(score=22)))

    def test_primary_button_by_kind_of_round(self):
        html = self.page(self.result())
        self.assertIn('href="/game/?mode=blitz">', html)
        self.assertIn('Сыграть в Блиц', html)
        self.assertIn('обогнать 225', html)
        custom = make_set(self.qs, title='Контрольная')
        html = self.page(self.result(game_set=custom))
        self.assertIn('href="%s"' % reverse('game:set_page', args=[custom.code]), html)
        self.assertIn('Сыграть этот же набор', html)
        self.assertIn('набор «Контрольная»', html)
        today = daily_mod.get_daily_set('blitz')
        html = self.page(self.result(game_set=today))
        self.assertIn('href="%s?auto=1"' % reverse('game:set_page', args=[today.code]), html)
        past = make_set(self.qs, kind='daily', day=daily_mod.today() - datetime.timedelta(days=2),
                        code=make_code())
        html = self.page(self.result(game_set=past))
        self.assertIn('href="%s"' % reverse('game:daily'), html)
        self.assertIn('Сегодняшний вызов дня', html)

    def test_duel_button_leads_a_guest_to_log_in_first(self):
        html = self.page(self.result(user=self.sonya))
        self.assertIn('href="/login/?next=/game/%3Fduel%3Dblitz"', html)
        self.client.force_login(User.objects.create_user(username='viewer', password='pw12345'))
        self.assertIn('href="/game/?duel=blitz"', self.page(self.result(user=self.sonya)))

    def test_place_badge_only_for_a_ranked_round(self):
        ranked = self.result(user=self.sonya, ranked=True, economy_version=config.ECONOMY_VERSION)
        self.assertIn('1-е место в таблице Блица', self.page(ranked))
        unranked = self.result(user=self.sonya, ranked=False, unranked_reason='quit')
        html = self.page(unranked)
        self.assertNotIn('место в таблице', html)
        self.assertIn('не в таблице: раунд прерван выходом', html)

    def test_lives_left_when_it_can_be_computed(self):
        self.assertIn('осталось 2 жизни из 3', self.page(self.result(wrong_count=1)))
        self.assertNotIn('из 3</span>', self.page(self.result(ended_reason='lives', wrong_count=3)))

    def test_open_for_everyone_without_writes_and_constant_queries(self):
        result = self.result(user=self.sonya, ranked=True, economy_version=config.ECONOMY_VERSION)
        with CaptureQueriesContext(connection) as few:
            self.page(result)
        for i in range(15):
            u = User.objects.create_user(username='p%d' % i, password='pw12345')
            self.result(user=u, score=100 + i, ranked=True, economy_version=config.ECONOMY_VERSION)
        with CaptureQueriesContext(connection) as many:
            self.page(result)
        self.assertEqual(len(few), len(many))
        self.assertLessEqual(len(many), 6)
        writes = [q['sql'] for q in many.captured_queries
                  if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writes, [])
        self.assertEqual(self.client.head(reverse('game:result', args=[result.code])).status_code, 200)
