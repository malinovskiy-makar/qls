# -*- coding: utf-8 -*-
u"""Страница дуэли `/game/d/<код>/` (фаза P3, ADR 0112): приглашение, ожидание,
сравнение для обоих.

Баг с боя 17.09.2026: автор не видел сравнения с соперником — пара строилась
«автор + я», а у автора «я» и есть автор; в шапке утекало «150 вопр.».
"""
import re

from django.test import TestCase
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.timezone import localtime

from game import state as run_state, views
from game.models import GameResult, GameSet
from problems.models import User


class DuelPageStatesTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username='avtor', password='p12345')
        self.rival = User.objects.create_user(username='lengler', password='p12345')
        self.gset = GameSet.objects.create(code='DUEL0001', mode='bullet', kind='duel',
                                           author=self.author, question_ids=list(range(1, 151)))
        self.url = reverse('game:duel', args=[self.gset.code])

    def result(self, user, score, outcomes, **extra):
        fields = dict(correct_count=outcomes.count('correct'), wrong_count=outcomes.count('wrong'),
                      skip_count=outcomes.count('skip'), max_combo=1.25, ended_reason='lives')
        fields.update(extra)
        return GameResult.objects.create(
            game_set=self.gset, user=user, mode='bullet', score=score,
            question_outcomes=[{'question_id': i + 1, 'number': i + 1, 'outcome': o}
                               for i, o in enumerate(outcomes)], **fields)

    def page(self, user=None):
        if user is not None:
            self.client.force_login(user)
        else:
            self.client.logout()
        return self.client.get(self.url)

    def test_author_sees_the_comparison_too(self):
        self.result(self.author, 52, ['correct', 'wrong', 'correct', 'wrong', 'wrong'])
        self.result(self.rival, 185, ['correct', 'correct', 'wrong', 'correct', 'correct',
                                      'wrong', 'correct', 'wrong'])
        for viewer, verdict in ((self.author, 'Победа за lengler'), (self.rival, 'Вы победили')):
            r = self.page(viewer)
            html = r.content.decode('utf-8')
            self.assertIn('class="du-compare"', html, viewer.username)
            self.assertEqual(r.context['compare']['verdict'], verdict)
            self.assertTrue(r.context['compare']['cards'][0]['is_me'])
        line = r.context['compare']['line']
        self.assertEqual(line, '185 : 52 · разрыв 133 очка · оба выбыли по жизням')
        # Дата вызова в шапке сравнения — не пустое место перед «·».
        self.assertIn('<span>%s · без фильтров · код DUEL0001</span>'
                      % date_format(localtime(self.gset.created), 'j E'), html)

    def test_one_result_says_the_rival_has_not_come_and_has_no_table(self):
        self.result(self.author, 52, ['correct', 'wrong'])
        r = self.page(self.author)
        html = r.content.decode('utf-8')
        self.assertNotIn('class="du-compare"', html)
        self.assertIn('Соперник ещё не пришёл', html)

    def test_rival_waiting_for_an_author_who_is_still_playing(self):
        self.result(self.rival, 90, ['correct'])
        run_id = run_state.new_run_id()
        state = {'run_id': run_id, 'mode': 'bullet', 'log': [], 'ended': None}
        run_state.save_by_id(state)
        run_state.duel_register_run(self.gset.code, self.author.id, run_id)
        html = self.page(self.rival).content.decode('utf-8')
        self.assertIn('avtor ещё играет', html)

    def test_no_queue_size_on_any_view(self):
        self.result(self.author, 52, ['correct'])
        for viewer in (None, self.rival, self.author):
            html = self.page(viewer).content.decode('utf-8')
            # Только содержимое страницы дуэли: у шапки сайта в стилях есть свой z-index 150.
            body = html.split('class="du-page', 1)[1].split('<script', 1)[0]
            self.assertIsNone(re.search(r'\b150\b', body), viewer)
            self.assertNotIn('вопр.', body)
            self.assertNotIn('бросает вызов', body)

    def test_invitation_for_a_guest_and_a_signed_in_rival(self):
        guest = self.page().content.decode('utf-8')
        self.assertIn('<span>avtor</span> зовёт вас на дуэль', guest)
        self.assertIn('>Войти, чтобы принять</a>', guest)
        self.assertIn('верный +2 с', guest)
        rival = self.page(self.rival).content.decode('utf-8')
        self.assertIn('>Принять вызов</a>', rival)
        self.assertNotIn('Попытка уже использована', rival)

    def test_each_row_highlights_at_most_one_cell(self):
        self.result(self.author, 300, ['correct'] * 3, avg_correct_ms=2000, wall_ms=60000)
        self.result(self.rival, 300, ['correct'] * 3, avg_correct_ms=1500, wall_ms=None)
        html = self.page(self.rival).content.decode('utf-8')
        table = html.split('<table class="du-compare">', 1)[1].split('</table>', 1)[0]
        rows = re.findall(r'<tr><th scope="row">(.*?)</th>(.*?)</tr>', table)
        self.assertEqual(len(rows), 8)
        for label, cells in rows:
            self.assertLessEqual(cells.count('class="w"'), 1, label)
        marks = dict((label, cells.count('class="w"')) for label, cells in rows)
        self.assertEqual(marks['Очки'], 0)               # ничья по очкам
        self.assertEqual(marks['Секунд на верный'], 1)   # быстрее lengler
        self.assertEqual(marks['Продержался'], 0)        # замера нет


class DuelVerdictTests(TestCase):
    u"""Вердикт, разрыв и фраза «кто что взял» — на трёх наборах чисел."""

    def setUp(self):
        self.a = User.objects.create_user(username='anna', password='p12345')
        self.b = User.objects.create_user(username='boris', password='p12345')
        self.gset = GameSet.objects.create(code='DUEL0002', mode='blitz', kind='duel',
                                           author=self.a, question_ids=[11, 12, 13, 14, 15])

    def pair(self, sa, sb, oa, ob, ra='lives', rb='lives'):
        def make(user, score, outcomes, reason):
            return GameResult(game_set=self.gset, user=user, mode='blitz', score=score,
                              correct_count=outcomes.count('correct'),
                              wrong_count=outcomes.count('wrong'), skip_count=outcomes.count('skip'),
                              max_combo=1, ended_reason=reason, id=1 if user == self.a else 2,
                              question_outcomes=[{'question_id': 11 + i, 'outcome': o}
                                                 for i, o in enumerate(outcomes)])
        return make(self.a, sa, oa, ra), make(self.b, sb, ob, rb)

    def test_win_for_the_viewer(self):
        a, b = self.pair(400, 150, ['correct', 'correct', 'wrong'], ['correct', 'wrong'])
        cmp_ = views._duel_compare(self.gset, a, b, mine=a)
        self.assertEqual(cmp_['verdict'], 'Вы победили')
        self.assertEqual(cmp_['line'], '400 : 150 · разрыв 250 очков · оба выбыли по жизням')
        self.assertEqual(cmp_['story'], 'Первый взяли оба. Второй – только вы. '
                                        'Дальше boris уже не было.')

    def test_loss_seen_by_the_rival_on_the_left(self):
        a, b = self.pair(400, 150, ['correct', 'correct', 'wrong'], ['correct', 'wrong'],
                         rb='time')
        cmp_ = views._duel_compare(self.gset, a, b, mine=b)
        self.assertEqual(cmp_['verdict'], 'Победа за anna')
        self.assertEqual([c['name'] for c in cmp_['cards']], ['boris', 'anna'])
        self.assertEqual(cmp_['line'], '400 : 150 · разрыв 250 очков · у вас: время вышло, '
                                       'anna: жизни кончились')
        self.assertEqual(cmp_['story'], 'Первый взяли оба. Второй – только anna. '
                                        'Дальше вас уже не было.')

    def test_draw_seen_by_a_third_person(self):
        a, b = self.pair(222, 222, ['wrong', 'correct'], ['correct', 'wrong'], ra='time', rb='time')
        cmp_ = views._duel_compare(self.gset, a, b, mine=None)
        self.assertEqual(cmp_['verdict'], 'Ничья')
        self.assertEqual(cmp_['line'], '222 : 222 · у обоих вышло время')
        self.assertEqual(cmp_['story'], 'Второй – только anna; первый – только boris.')
        self.assertFalse(any(c['win'] for c in cmp_['cards']))
