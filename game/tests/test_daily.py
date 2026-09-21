"""
Тесты вызова дня (Фаза 4).

Ключевой инвариант: набор дня строится ДЕТЕРМИНИРОВАННО от даты и режима.
Крона нет (бесплатный хостинг засыпает), набор создаётся лениво при первом
обращении — и если бы список был случайным, «первое обращение» решало бы,
во что играет весь день весь мир.
"""
import datetime
import json
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from game import config
from game import daily as daily_mod
from game.models import GameQuestion, GameResult, GameSet, make_code
from problems.models import Problem

User = get_user_model()


def make_q(n, qtype='single'):
    out = []
    for i in range(n):
        p = Problem.objects.create(
            title='Т%d' % i, statement='Условие %d' % i,
            problem_type='тест: один ответ', answer='а',
            status=Problem.Status.PUBLISHED)
        out.append(GameQuestion.objects.create(
            problem=p, question_type=qtype, question='Вопрос %d?' % i,
            options=['а', 'б', 'в'], correct_index=0, difficulty=3,
            topics=['Спрос и предложение'], lang='ru'))
    return out


class SeedTests(TestCase):
    """Сид воспроизводим — это и есть замена крону."""

    def test_same_day_and_mode_give_the_same_list(self):
        ids = list(range(1, 200))
        day = datetime.date(2026, 7, 26)
        a = daily_mod.pick_daily_questions(day, 'blitz', ids)
        b = daily_mod.pick_daily_questions(day, 'blitz', ids)
        self.assertEqual(a, b)
        self.assertEqual(len(a), config.DAILY_SIZE['blitz'])

    def test_order_of_candidates_does_not_matter(self):
        """Кандидаты приходят из базы в произвольном порядке — набор от
        этого меняться не должен."""
        day = datetime.date(2026, 7, 26)
        a = daily_mod.pick_daily_questions(day, 'blitz', list(range(1, 200)))
        b = daily_mod.pick_daily_questions(day, 'blitz',
                                           list(reversed(range(1, 200))))
        self.assertEqual(a, b)

    def test_different_days_give_different_lists(self):
        ids = list(range(1, 200))
        a = daily_mod.pick_daily_questions(datetime.date(2026, 7, 26),
                                           'blitz', ids)
        b = daily_mod.pick_daily_questions(datetime.date(2026, 7, 27),
                                           'blitz', ids)
        self.assertNotEqual(a, b)

    def test_different_modes_give_different_lists(self):
        ids = list(range(1, 200))
        day = datetime.date(2026, 7, 26)
        a = daily_mod.pick_daily_questions(day, 'blitz', ids)
        b = daily_mod.pick_daily_questions(day, 'bullet', ids)
        self.assertNotEqual(a, b)

    def test_small_pool_gives_a_short_set_not_a_crash(self):
        got = daily_mod.pick_daily_questions(datetime.date(2026, 7, 26),
                                             'blitz', [1, 2, 3])
        self.assertEqual(sorted(got), [1, 2, 3])

    def test_empty_pool_gives_nothing(self):
        self.assertEqual(
            daily_mod.pick_daily_questions(datetime.date(2026, 7, 26),
                                           'blitz', []), [])


class DailySetTests(TestCase):
    def setUp(self):
        self.qs = make_q(30)

    def test_set_is_created_lazily_and_reused(self):
        first = daily_mod.get_daily_set('blitz')
        second = daily_mod.get_daily_set('blitz')
        self.assertEqual(first.id, second.id)
        self.assertEqual(GameSet.objects.filter(kind='daily').count(), 1)

    def test_recreating_the_same_day_gives_the_same_questions(self):
        """★ Пересоздание в тот же день обязано дать ТОТ ЖЕ набор."""
        gset = daily_mod.get_daily_set('blitz')
        ids = list(gset.question_ids)
        gset.delete()
        again = daily_mod.get_daily_set('blitz')
        self.assertEqual(again.question_ids, ids)

    def test_one_set_per_mode_per_day(self):
        for mode in ('bullet', 'blitz', 'rapid', 'classic'):
            daily_mod.get_daily_set(mode)
        # bullet/rapid/classic пула нет — наборов у них не будет
        self.assertEqual(
            GameSet.objects.filter(kind='daily', day=daily_mod.today()).count(),
            1)

    def test_next_day_gives_a_new_set(self):
        today = daily_mod.today()
        a = daily_mod.get_daily_set('blitz', today)
        b = daily_mod.get_daily_set('blitz', today + datetime.timedelta(days=1))
        self.assertNotEqual(a.id, b.id)
        self.assertNotEqual(a.question_ids, b.question_ids)

    def test_size_comes_from_config(self):
        gset = daily_mod.get_daily_set('blitz')
        self.assertEqual(gset.size, config.DAILY_SIZE['blitz'])

    def test_set_is_closed_after_its_day(self):
        yesterday = daily_mod.today() - datetime.timedelta(days=1)
        gset = daily_mod.get_daily_set('blitz', yesterday)
        url = reverse('game:session_start_set', args=[gset.code])
        self.assertEqual(self.client.get(url).status_code, 409)

    def test_moscow_midnight_is_the_cutoff(self):
        tz = daily_mod.daily_tzinfo()
        reset = daily_mod.next_reset()
        local = reset.astimezone(tz)
        self.assertEqual((local.hour, local.minute), (0, 0))
        self.assertGreater(reset, timezone.now())


class DailyPagesTests(TestCase):
    def setUp(self):
        self.qs = make_q(30)

    def test_daily_page_lists_available_modes(self):
        r = self.client.get(reverse('game:daily'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Вызов дня')
        self.assertContains(r, 'Блиц')

    def test_board_opens_and_says_nobody_played(self):
        r = self.client.get(reverse('game:daily_board', args=['blitz']))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ещё никто не прошёл')

    def test_unknown_mode_is_404(self):
        r = self.client.get(reverse('game:daily_board', args=['чепуха']))
        self.assertEqual(r.status_code, 404)

    def test_yesterday_board_is_available_by_date(self):
        yesterday = daily_mod.today() - datetime.timedelta(days=1)
        daily_mod.get_daily_set('blitz', yesterday)
        r = self.client.get(reverse('game:daily_board_day',
                                    args=['blitz', yesterday.isoformat()]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'вызов закрыт')

    def test_bad_date_is_404(self):
        r = self.client.get(reverse('game:daily_board_day',
                                    args=['blitz', 'вчера']))
        self.assertEqual(r.status_code, 404)


class DailyBoardTests(TestCase):
    def setUp(self):
        self.qs = make_q(30)
        self.gset = daily_mod.get_daily_set('blitz')

    def _result(self, user, score, minutes=0):
        r = GameResult.objects.create(
            code=make_code(), mode='blitz', game_set=self.gset, user=user,
            score=score, correct_count=score // 100, total_count=10,
            max_combo=2, ended_reason='set_done')
        if minutes:
            GameResult.objects.filter(pk=r.pk).update(
                created_at=timezone.now() + datetime.timedelta(minutes=minutes))
        return r

    def test_sorted_by_score_then_by_finish_time(self):
        a = User.objects.create_user(username='a', password='pw12345')
        b = User.objects.create_user(username='b', password='pw12345')
        c = User.objects.create_user(username='c', password='pw12345')
        self._result(b, 500, minutes=5)     # тот же счёт, но позже
        self._result(a, 500, minutes=1)     # раньше — выше
        self._result(c, 900, minutes=9)
        top, _mine, total = daily_mod.board_rows(self.gset)
        self.assertEqual([r['name'] for r in top], ['c', 'a', 'b'])
        self.assertEqual(total, 3)

    def test_anonymous_result_is_not_on_the_board(self):
        """Аноним играет свободно и видит свой результат, но у него нет
        имени — на доску он не попадает."""
        u = User.objects.create_user(username='u', password='pw12345')
        self._result(u, 300)
        self._result(None, 9999)            # аноним с огромным счётом
        top, _mine, total = daily_mod.board_rows(self.gset)
        self.assertEqual(total, 1)
        self.assertEqual(top[0]['name'], 'u')

    def test_my_row_is_shown_separately_when_out_of_top(self):
        me = User.objects.create_user(username='me', password='pw12345')
        for i in range(5):
            u = User.objects.create_user(username='u%d' % i, password='pw12345')
            self._result(u, 1000 + i)
        self._result(me, 10)
        top, my_row, _total = daily_mod.board_rows(self.gset, me, limit=3)
        self.assertEqual(len(top), 3)
        self.assertIsNotNone(my_row)
        self.assertEqual(my_row['name'], 'me')
        self.assertEqual(my_row['place'], 6)

    def test_my_row_is_not_duplicated_when_inside_top(self):
        me = User.objects.create_user(username='me2', password='pw12345')
        self._result(me, 900)
        top, my_row, _total = daily_mod.board_rows(self.gset, me, limit=50)
        self.assertIsNone(my_row)
        self.assertTrue(top[0]['is_me'])


class DailyAttemptTests(TestCase):
    def setUp(self):
        self.qs = make_q(30)
        self.gset = daily_mod.get_daily_set('blitz')
        self.url = reverse('game:session_start_set', args=[self.gset.code])

    def test_second_attempt_is_refused(self):
        User.objects.create_user(username='u', password='pw12345')
        self.client.login(username='u', password='pw12345')
        d = self.client.get(self.url).json()
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': d['question']['id'],
                                     'choice': 0}),
                         content_type='application/json')
        self.client.post(reverse('game:session_finish'),
                         json.dumps({'reason': 'done'}),
                         content_type='application/json')
        self.assertEqual(self.client.get(self.url).status_code, 409)

    def test_anonymous_can_play(self):
        """Игра публичная: стены с логином на вызове дня нет."""
        self.assertEqual(self.client.get(self.url).status_code, 200)


# ─── P4: серия дней, страница вызова, одна доска дня (решение 17.09.2026) ──

def daily_set(mode, day, questions):
    """Набор вызова на любой день — без пула режима (у Пули в тестах его нет)."""
    return GameSet.objects.create(
        code=make_code(), mode=mode, kind='daily', day=day,
        question_ids=[q.id for q in questions], attempts_allowed=1)


def played(user, gset, score=100, when=None, reason='set_done', accuracy_right=8):
    r = GameResult.objects.create(
        code=make_code(), mode=gset.mode, game_set=gset, user=user, score=score,
        correct_count=accuracy_right, total_count=10, max_combo=3, ended_reason=reason)
    if when is not None:
        GameResult.objects.filter(pk=r.pk).update(created_at=when)
    return r


def main_of(html):
    """Только содержимое страницы: в стилях шапки сайта свои слова («Сегодня такой экран…»)."""
    return html.split('<main', 1)[1].split('</main>', 1)[0]


def visible_text(html):
    """Разметка без адресов ссылок: код набора в `href` игроку не виден."""
    return re.sub(r'href="[^"]*"', '', html)


class StreakTests(TestCase):
    """Серия дней: засчитан день, в который сыгран хотя бы один вызов."""

    def setUp(self):
        self.qs = make_q(12)
        self.user = User.objects.create_user(username='seria', password='pw12345')
        self.today = daily_mod.today()

    def day(self, back):
        return self.today - datetime.timedelta(days=back)

    def play_days(self, *backs, mode='blitz'):
        for back in backs:
            gset = (GameSet.objects.filter(kind='daily', mode=mode, day=self.day(back)).first()
                    or daily_set(mode, self.day(back), self.qs))
            played(self.user, gset)

    def test_no_rounds_no_streak(self):
        got = daily_mod.streak_for(self.user, today=self.today)
        self.assertEqual((got['current'], got['best']), (0, 0))

    def test_chain_up_to_yesterday_counts_while_today_is_not_played(self):
        self.play_days(3, 2, 1)
        got = daily_mod.streak_for(self.user, today=self.today)
        self.assertEqual(got['current'], 3)
        self.assertFalse(got['played_today'])
        self.play_days(0)
        got = daily_mod.streak_for(self.user, today=self.today)
        self.assertEqual((got['current'], got['played_today']), (4, True))

    def test_a_missed_day_breaks_the_chain(self):
        self.play_days(4, 3, 1)
        got = daily_mod.streak_for(self.user, today=self.today)
        self.assertEqual((got['current'], got['best']), (1, 2))

    def test_two_challenges_in_one_day_are_one_day(self):
        self.play_days(1)
        self.play_days(1, mode='bullet')
        self.assertEqual(daily_mod.streak_for(self.user, today=self.today)['current'], 1)

    def test_round_saved_after_midnight_counts_for_the_day_of_its_set(self):
        """Раунд вчерашнего набора, сохранённый в 00:01, — это вчера, а не сегодня."""
        gset = daily_set('blitz', self.day(1), self.qs)
        tz = daily_mod.daily_tzinfo()
        after_midnight = datetime.datetime.combine(self.today, datetime.time(0, 1), tzinfo=tz)
        played(self.user, gset, when=after_midnight)
        got = daily_mod.streak_for(self.user, today=self.today)
        self.assertEqual((got['current'], got['played_today']), (1, False))
        self.assertEqual([d['hit'] for d in got['week'] if d['is_today']], [False])

    def test_best_is_never_below_current(self):
        self.play_days(9, 8, 2, 1, 0)
        got = daily_mod.streak_for(self.user, today=self.today)
        self.assertEqual((got['current'], got['best']), (3, 3))
        self.assertGreaterEqual(got['best'], got['current'])

    def test_anonymous_has_no_streak_and_no_error(self):
        self.assertEqual(daily_mod.played_pairs(AnonymousUser()), set())
        self.assertEqual(daily_mod.streak_for(AnonymousUser(), today=self.today)['current'], 0)


class DailyPageP4Tests(TestCase):
    """Страница `/game/daily/` по макету Daily."""

    def setUp(self):
        self.qs = make_q(30)
        self.bool_qs = make_q(20, qtype='boolean')
        self.today = daily_mod.today()
        self.me = User.objects.create_user(username='marina', password='pw12345')

    def page(self):
        r = self.client.get(reverse('game:daily'))
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    def test_no_set_codes_in_visible_markup_and_play_links_autostart(self):
        html = self.page()
        sets = list(GameSet.objects.filter(kind='daily', day=self.today))
        self.assertEqual({s.mode for s in sets}, {'blitz', 'bullet'})
        for gset in sets:
            self.assertNotIn(gset.code, visible_text(html))
            self.assertIn('/game/s/%s/?auto=1' % gset.code, html)
        self.assertEqual(html.count('?auto=1'), 2)
        self.assertIn('15 данеток · 1 мин', html)
        self.assertIn('12 вопросов · 2 мин', html)

    def test_played_card_has_no_play_link_and_shows_score_and_place(self):
        blitz = daily_mod.get_daily_set('blitz')
        other = User.objects.create_user(username='lengler', password='pw12345')
        played(other, blitz, score=640)
        played(self.me, blitz, score=186)
        self.client.force_login(self.me)
        html = self.page()
        self.assertNotIn('/game/s/%s/?auto=1' % blitz.code, html)
        self.assertEqual(html.count('?auto=1'), 1)
        self.assertIn('сыграно 1 из 2', html)
        self.assertIn('Доска и разбор вопросов', html)
        self.assertRegex(html, r'<b>186</b><span>ваш счёт · 2-е место из 2</span>')
        self.assertIn('Вы · marina', html)

    def test_top_five_with_medals_and_count(self):
        blitz = daily_mod.get_daily_set('blitz')
        for i in range(7):
            played(User.objects.create_user(username='p%d' % i, password='pw12345'),
                   blitz, score=100 + i)
        html = self.page()
        card = html.split('data-mode="blitz"')[1].split('</section>')[0]
        self.assertEqual(card.count('<li class="dy-row'), 5)
        self.assertEqual(card.count('gb-medal m'), 3)
        self.assertIn('<b>7</b>', card)
        self.assertIn('p6', card)
        self.assertNotIn('p1<', card)

    def test_yesterday_winner_or_nobody(self):
        ysets = daily_set('blitz', self.today - datetime.timedelta(days=1), self.qs)
        played(User.objects.create_user(username='sonya', password='pw12345'), ysets, score=230)
        html = self.page()
        blitz = html.split('data-mode="blitz"')[1].split('</section>')[0]
        bullet = html.split('data-mode="bullet"')[1].split('</section>')[0]
        self.assertIn('Вчера: 1-е место – sonya · 230', blitz)
        self.assertIn('Вчера никто не играл', bullet)
        yday = (self.today - datetime.timedelta(days=1)).isoformat()
        self.assertIn(reverse('game:daily_board_day', args=['bullet', yday]), bullet)

    def test_guest_meter_has_login_and_no_streak(self):
        html = self.page()
        meter = html.split('class="gb-card dy-meter"')[1].split('</section>')[0]
        self.assertNotIn('Серия', meter)
        self.assertNotIn('серия', meter.split('<p>')[0])
        self.assertIn('Войти', meter)
        self.assertIn('Новый вызов через', meter)

    def test_student_meter_has_streak_week_and_best(self):
        for back in (2, 1):
            played(self.me, daily_set('blitz', self.today - datetime.timedelta(days=back), self.qs))
        self.client.force_login(self.me)
        meter = self.page().split('class="gb-card dy-meter"')[1].split('</section>')[0]
        self.assertIn('Серия', meter)
        self.assertIn('2 дня', meter)
        self.assertIn('сыграйте сегодня любой вызов, чтобы не прервать', meter)
        self.assertEqual(meter.count('class="dy-day'), 7)
        self.assertNotIn('Войти', meter)

    def test_guest_who_played_sees_played_card_without_place(self):
        blitz = daily_mod.get_daily_set('blitz')
        result = played(None, blitz, score=77)
        session = self.client.session
        session['econ_rush_set_results'] = {blitz.code: result.code}
        session['econ_rush_sets_played'] = [blitz.code]
        session.save()
        card = self.page().split('data-mode="blitz"')[1].split('</section>')[0]
        self.assertIn('сыгран', card)
        self.assertIn('<b>77</b><span>ваш счёт</span>', card)
        self.assertNotIn('?auto=1', card)

    def test_query_count_does_not_grow_with_players(self):
        self.client.force_login(self.me)
        self.page()                       # первый заход создаёт наборы дня
        with CaptureQueriesContext(connection) as empty:
            self.page()
        blitz = daily_mod.get_daily_set('blitz', create=False)
        bullet = daily_mod.get_daily_set('bullet', create=False)
        yday = daily_set('blitz', self.today - datetime.timedelta(days=1), self.qs)
        for i in range(12):
            u = User.objects.create_user(username='q%d' % i, password='pw12345')
            for gset in (blitz, bullet, yday):
                played(u, gset, score=10 * i)
        with CaptureQueriesContext(connection) as full:
            self.page()
        self.assertEqual(len(full), len(empty))
        self.assertLessEqual(len(full), 12)


class DayBoardP4Tests(TestCase):
    """Одна доска дня по макету DailyBoard."""

    def setUp(self):
        self.qs = make_q(30)
        self.today = daily_mod.today()
        self.yday = self.today - datetime.timedelta(days=1)

    def board(self, mode='blitz', day=None, status=200):
        args = [mode] if day is None else [mode, day.isoformat()]
        name = 'game:daily_board' if day is None else 'game:daily_board_day'
        r = self.client.get(reverse(name, args=args))
        self.assertEqual(r.status_code, status)
        return main_of(r.content.decode()) if status == 200 else r

    def test_past_day_without_a_set_is_an_empty_board_not_404(self):
        long_ago = self.today - datetime.timedelta(days=5)
        html = self.board(day=long_ago)
        self.assertIn('В этот день вызов никто не сыграл', html)
        self.assertIn('В этот день никто не играл.', html)
        self.assertIn('вызов закрыт', html)
        self.assertFalse(GameSet.objects.filter(kind='daily', day=long_ago).exists())
        self.assertNotIn('Сегодня', html)
        self.assertNotIn('будь первым', html.lower())
        self.assertNotIn('будьте первым', html.lower())

    def test_future_day_and_nonsense_are_404(self):
        self.board(day=self.today + datetime.timedelta(days=1), status=404)
        self.board(mode='чепуха', status=404)

    def test_today_board_is_empty_with_today_words_and_play(self):
        html = self.board()
        gset = daily_mod.get_daily_set('blitz', create=False)
        self.assertIn('Сегодня этот вызов ещё никто не прошёл', html)
        self.assertIn('Сегодня · ', html)
        self.assertIn('/game/s/%s/?auto=1' % gset.code, html)
        self.assertIn('Где ошиблись', html)
        self.assertNotIn('посыпались', html)

    def test_question_texts_today_only_after_own_attempt(self):
        gset = daily_mod.get_daily_set('blitz')
        someone = User.objects.create_user(username='first', password='pw12345')
        played(someone, gset)
        GameResult.objects.filter(game_set=gset).update(question_outcomes=[
            {'question_id': qid, 'outcome': 'correct'} for qid in gset.question_ids])
        text = GameQuestion.objects.get(id=gset.question_ids[0]).question
        html = self.board()
        self.assertNotIn(text, html)
        self.assertIn('текст откроется после вашей попытки', html)
        self.client.force_login(someone)
        html = self.board()
        self.assertIn(text, html)
        self.assertNotIn('текст откроется после вашей попытки', html)

    def test_question_texts_of_a_closed_day_are_open_to_everyone(self):
        gset = daily_set('blitz', self.yday, self.qs[:5])
        r = played(User.objects.create_user(username='vchera', password='pw12345'), gset)
        GameResult.objects.filter(pk=r.pk).update(question_outcomes=[
            {'question_id': q.id, 'outcome': 'wrong'} for q in self.qs[:5]])
        html = self.board(day=self.yday)
        self.assertIn(self.qs[0].question, html)
        self.assertNotIn('текст откроется после вашей попытки', html)
        self.assertIn('gb-q hard', html)

    def test_second_board_address_redirects_to_the_day_board(self):
        gset = daily_set('blitz', self.yday, self.qs)
        r = self.client.get(reverse('game:set_board', args=[gset.code]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], reverse('game:daily_board_day',
                                                args=['blitz', self.yday.isoformat()]))
        today_set = daily_mod.get_daily_set('blitz')
        r = self.client.get(reverse('game:set_board', args=[today_set.code]))
        self.assertEqual(r['Location'], reverse('game:daily_board', args=['blitz']))

    def test_own_row_is_visible_when_eleventh(self):
        gset = daily_mod.get_daily_set('blitz')
        for i in range(10):
            played(User.objects.create_user(username='top%d' % i, password='pw12345'),
                   gset, score=1000 + i)
        me = User.objects.create_user(username='eleventh', password='pw12345')
        played(me, gset, score=5)
        self.client.force_login(me)
        html = self.board()
        self.assertIn('Вы · eleventh', html)
        self.assertIn('<td>11</td>', html)
        self.assertIn('и ещё 1 – показаны первые 10', html)
        self.assertIn('11-е место из 11', html)
        self.assertIn('Страница результата', html)

    def test_endings_are_words(self):
        gset = daily_mod.get_daily_set('blitz')
        played(User.objects.create_user(username='a1', password='pw12345'), gset, 30, reason='lives')
        played(User.objects.create_user(username='a2', password='pw12345'), gset, 20, reason='time')
        played(User.objects.create_user(username='a3', password='pw12345'), gset, 10)
        html = self.board()
        for word in ('кончились жизни', 'вышло время', 'прошёл все вопросы'):
            self.assertIn(word, html)
        GameResult.objects.filter(game_set=gset).update(max_combo=1.25)
        self.assertIn('>×1,25<', self.board())

    def test_day_stepper_stops_at_the_first_set_and_at_today(self):
        daily_set('blitz', self.yday, self.qs)
        html = self.board(day=self.yday)
        self.assertIn('Вчера · ', html)
        self.assertNotIn('aria-label="Предыдущий день"', html)
        self.assertIn('href="%s" aria-label="Следующий день"'
                      % reverse('game:daily_board', args=['blitz']), html)
        html = self.board()
        self.assertIn('href="%s" aria-label="Предыдущий день"'
                      % reverse('game:daily_board_day', args=['blitz', self.yday.isoformat()]), html)
        self.assertNotIn('aria-label="Следующий день"', html)

    def test_finish_of_yesterdays_set_leads_to_yesterdays_board(self):
        self.assertEqual(daily_mod.board_url('blitz', self.yday),
                         reverse('game:daily_board_day', args=['blitz', self.yday.isoformat()]))
        self.assertEqual(daily_mod.board_url('blitz', self.today),
                         reverse('game:daily_board', args=['blitz']))


class AutostartTests(TestCase):
    """`?auto=1`: стартовый экран невидим до ответа сервера (P4.2, п. 4)."""

    def setUp(self):
        make_q(30)
        self.gset = daily_mod.get_daily_set('blitz')

    def test_autostart_page_hides_the_start_screen_from_the_first_paint(self):
        url = reverse('game:set_page', args=[self.gset.code])
        html = self.client.get(url + '?auto=1').content.decode()
        self.assertIn('class="screen active autostarting"', html)
        html = self.client.get(url).content.decode()
        self.assertNotIn('autostarting"', html)

    def test_script_lifts_the_veil_on_any_screen_change_and_on_refusal(self):
        from game.tests.test_page_js import inline_js, page_source
        js = inline_js(page_source())
        show = js.split('function show(name) {')[1].split('\n  }')[0]
        self.assertIn("screens.start.classList.remove('autostarting')", show)
        notice = js.split('function showStartNotice(text) {')[1].split('\n  }')[0]
        self.assertIn("screens.start.classList.remove('autostarting')", notice)


class BaseStyleBlockTests(TestCase):
    """Найдено в P4: `extra_style` у базы каталога сам стоит ВНУТРИ `<style>`.

    Вложенный `<style>` в этом блоке не ошибка разметки, а тихая потеря: первое
    правило после тега становится битым селектором и выбрасывается браузером
    (так пропадали `.du-page`, `.de-wrap`, `.st-wrap`, `.bd-wrap`).
    """

    def test_game_pages_put_bare_rules_into_extra_style(self):
        import glob
        import os
        from django.conf import settings
        bad = []
        for path in glob.glob(os.path.join(settings.BASE_DIR, 'game', 'templates', 'game', '*.html')):
            src = open(path, encoding='utf-8').read()
            if "extends 'catalog/base.html'" not in src:
                continue
            block = re.search(r'\{% block extra_style %\}(.*?)\{% endblock %\}', src, re.S)
            if block and '<style' in block.group(1):
                bad.append(os.path.basename(path))
        self.assertEqual(bad, [])
