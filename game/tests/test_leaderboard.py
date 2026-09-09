# -*- coding: utf-8 -*-
u"""Лидерборд и личная статистика (фаза 6).

Здесь же живут ОТРИЦАТЕЛЬНЫЕ тесты границ: «свой прошёл» без парного
«чужой не прошёл» границей не считается.
"""
import datetime

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import User
from game import config, leaderboard as lb
from game.models import GameResult, make_result_code


def run(user, mode='blitz', score=100, correct=10, avg_ms=3000,
        ranked=True, unfiltered=True, when=None, wrong=0):
    r = GameResult.objects.create(
        code=make_result_code(), mode=mode, user=user, score=score,
        correct_count=correct, wrong_count=wrong, avg_correct_ms=avg_ms,
        ranked=ranked, is_unfiltered=unfiltered,
        economy_version=config.ECONOMY_VERSION)
    if when is not None:
        GameResult.objects.filter(pk=r.pk).update(created_at=when)
        r.refresh_from_db()
    return r


class BoardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(username='anya', password='p12345')
        self.b = User.objects.create_user(username='boris', password='p12345')
        self.c = User.objects.create_user(username='vera', password='p12345')

    def test_personal_record_not_the_sum(self):
        u"""В таблице ЛИЧНЫЙ РЕКОРД, а не сумма и не среднее: иначе выигрывал
        бы тот, кто больше сыграл, а не тот, кто лучше."""
        run(self.a, score=100)
        run(self.a, score=300)
        run(self.a, score=200)
        run(self.b, score=250)
        rows = lb.top('blitz', 'all', 'score')
        self.assertEqual([(r['username'], r['value']) for r in rows],
                         [('anya', 300), ('boris', 250)])

    def test_one_row_per_player(self):
        for _ in range(5):
            run(self.a, score=100)
        self.assertEqual(len(lb.top('blitz', 'all', 'score')), 1)

    def test_tie_is_broken_by_who_got_there_first(self):
        u"""Без этого правила порядок одинаковых результатов менялся бы сам
        собой между обновлениями, а человек читает это как «меня обогнали».

        ⚠️ ГРАНИЦА ЭТОГО ТЕСТА, ЧЕСТНО. Он закрепляет НАПРАВЛЕНИЕ правила:
        поменяй `achieved` на `-achieved` — покраснеет. А вот снятие
        правила целиком на SQLite он НЕ ловит: база случайно возвращает
        группы ровно в нужном порядке, и проверено это подложенным
        дефектом, а не предположением. На PostgreSQL (прод и джоб `tests`
        в CI) порядок групп ничем не гарантирован, и там снятие правила
        поймается. Держать тест стоит: направление он стережёт везде.
        """
        # ⚠️ Порядок достижения — ОБРАТНЫЙ порядку создания игроков. Так
        # исключено случайное совпадение с тем, как база вернёт группы:
        # без правила о ничьей ожидаемый и полученный списки окажутся
        # зеркальными, а не одинаковыми. Двух игроков для этого мало —
        # проверено подложенным дефектом, тест оставался зелёным.
        now = timezone.now()
        run(self.a, score=200, when=now - datetime.timedelta(hours=1))
        run(self.b, score=200, when=now - datetime.timedelta(hours=3))
        run(self.c, score=200, when=now - datetime.timedelta(hours=5))
        rows = lb.top('blitz', 'all', 'score')
        self.assertEqual([r['username'] for r in rows],
                         ['vera', 'boris', 'anya'])

    def test_week_window_excludes_eight_days_ago(self):
        run(self.a, score=500,
            when=timezone.now() - datetime.timedelta(days=8))
        run(self.b, score=100)
        week = [r['username'] for r in lb.top('blitz', 'week', 'score')]
        alltime = [r['username'] for r in lb.top('blitz', 'all', 'score')]
        self.assertEqual(week, ['boris'])
        self.assertEqual(alltime, ['anya', 'boris'])

    def test_unranked_runs_never_reach_the_board(self):
        run(self.a, score=9999, ranked=False)
        run(self.b, score=10)
        self.assertEqual([r['username'] for r in lb.top('blitz', 'all', 'score')],
                         ['boris'])

    def test_anonymous_runs_never_reach_the_board(self):
        run(None, score=9999, ranked=True)
        run(self.b, score=10)
        self.assertEqual([r['username'] for r in lb.top('blitz', 'all', 'score')],
                         ['boris'])

    def test_speed_board_needs_enough_correct_answers(self):
        u"""Среднее по двум ответам — не среднее, а случайность."""
        run(self.a, avg_ms=500, correct=config.SPEED_BOARD_MIN_CORRECT - 1)
        run(self.b, avg_ms=4000, correct=config.SPEED_BOARD_MIN_CORRECT)
        rows = lb.top('blitz', 'all', 'speed')
        self.assertEqual([r['username'] for r in rows], ['boris'])

    def test_speed_board_is_ascending(self):
        run(self.a, avg_ms=4000, correct=12)
        run(self.b, avg_ms=1500, correct=12)
        self.assertEqual([r['username'] for r in lb.top('blitz', 'all', 'speed')],
                         ['boris', 'anya'])

    def test_correct_and_speed_boards_ignore_filtered_runs(self):
        u"""Под фильтром по теме легко набрать длинную серию на знакомом
        материале, и доска перестала бы сравнивать умение."""
        run(self.a, correct=99, avg_ms=100, unfiltered=False)
        run(self.b, correct=11, avg_ms=3000, unfiltered=True)
        self.assertEqual([r['username'] for r in lb.top('blitz', 'all', 'correct')],
                         ['boris'])
        self.assertEqual([r['username'] for r in lb.top('blitz', 'all', 'speed')],
                         ['boris'])

    def test_score_board_does_accept_filtered_runs(self):
        u"""Очки уже учли отсутствие множителя ×1,3 — второй раз наказывать
        незачем."""
        run(self.a, score=200, unfiltered=False)
        self.assertEqual(len(lb.top('blitz', 'all', 'score')), 1)

    def test_boards_are_per_mode(self):
        run(self.a, mode='rapid', score=999)
        run(self.b, mode='blitz', score=10)
        self.assertEqual([r['username'] for r in lb.top('blitz', 'all', 'score')],
                         ['boris'])


class MyRowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.me = User.objects.create_user(username='ya', password='p12345')
        self.others = [User.objects.create_user(username='u%d' % i,
                                                password='p12345')
                       for i in range(25)]

    def test_me_outside_the_top_still_gets_a_place(self):
        for i, u in enumerate(self.others):
            run(u, score=1000 + i)
        run(self.me, score=5)
        row = lb.my_row(self.me, 'blitz', 'all', 'score')
        self.assertIsNotNone(row)
        self.assertEqual(row['place'], 26)
        self.assertNotIn(self.me.username,
                         [r['username'] for r in lb.top('blitz', 'all', 'score')])

    def test_me_is_none_without_runs(self):
        self.assertIsNone(lb.my_row(self.me, 'blitz', 'all', 'score'))

    def test_me_is_none_for_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(lb.my_row(AnonymousUser(), 'blitz', 'all', 'score'))
        self.assertIsNone(lb.my_row(None, 'blitz', 'all', 'score'))


class CacheIsolationTests(TestCase):
    u"""⚠️ САМОЕ СТРАШНОЕ МЕСТО ВСЕЙ ДОСКИ: чужая строка «я» в общем кэше."""

    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(username='anya', password='p12345')
        self.b = User.objects.create_user(username='boris', password='p12345')
        run(self.a, score=300)
        run(self.b, score=100)

    def test_my_row_is_never_shared_between_players(self):
        self.client.force_login(self.a)
        da = self.client.get(reverse('game:leaderboard')).json()
        self.client.logout()
        self.client.force_login(self.b)
        db = self.client.get(reverse('game:leaderboard')).json()
        self.assertEqual(da['me']['username'], 'anya')
        self.assertEqual(db['me']['username'], 'boris')
        self.assertNotEqual(da['me']['value'], db['me']['value'])

    def test_highlight_is_not_baked_into_the_cache(self):
        self.client.force_login(self.a)
        da = self.client.get(reverse('game:leaderboard')).json()
        self.client.logout()
        self.client.force_login(self.b)
        db = self.client.get(reverse('game:leaderboard')).json()
        mine_a = [r['username'] for r in da['rows'] if r['is_me']]
        mine_b = [r['username'] for r in db['rows'] if r['is_me']]
        self.assertEqual(mine_a, ['anya'])
        self.assertEqual(mine_b, ['boris'])

    def test_anonymous_sees_the_board_but_no_highlight(self):
        d = self.client.get(reverse('game:leaderboard')).json()
        self.assertEqual(len(d['rows']), 2)
        self.assertIsNone(d['me'])
        self.assertFalse(any(r['is_me'] for r in d['rows']))


class LeakTests(TestCase):
    u"""Наружу уходит ровно то, что доска обещает показать."""

    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(username='anya', password='p12345',
                                          email='anya@example.com')
        run(self.a, score=300)

    def test_public_rows_carry_no_internal_ids_or_profile_fields(self):
        d = self.client.get(reverse('game:leaderboard')).json()
        row = d['rows'][0]
        self.assertEqual(set(row),
                         {'place', 'username', 'value', 'achieved_at', 'is_me'})
        # Набор ключей выше уже доказывает, что внутреннего id в строке нет.
        # Поиском подстроки это не проверить: «1,» совпадает с «"place": 1,».
        body = self.client.get(reverse('game:leaderboard')).content.decode()
        for leak in ('example.com', 'password', 'user_id', 'email',
                     'is_staff', 'first_name'):
            self.assertNotIn(leak, body, leak)


class MyStatsBoundaryTests(TestCase):
    u"""ОТРИЦАТЕЛЬНЫЕ тесты границы личной статистики."""

    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(username='anya', password='p12345')
        self.b = User.objects.create_user(username='boris', password='p12345')
        run(self.a, score=300, correct=12)
        run(self.b, score=50, correct=3)

    def test_anonymous_is_turned_away(self):
        r = self.client.get(reverse('game:my_stats'))
        self.assertIn(r.status_code, (302, 403), r.status_code)

    def test_own_stats_are_returned(self):
        self.client.force_login(self.a)
        d = self.client.get(reverse('game:my_stats')).json()
        self.assertEqual(d['stats']['best_score'], 300)
        self.assertEqual(d['stats']['runs'], 1)

    def test_no_parameter_can_ask_for_someone_elses_stats(self):
        u"""⚠️ Параметра «чей» здесь нет и не будет: он немедленно превратил
        бы личную статистику в публичную по перебору номеров."""
        self.client.force_login(self.b)
        for probe in ({'user': self.a.id}, {'user_id': self.a.id},
                      {'username': 'anya'}, {'me': self.a.id}):
            d = self.client.get(reverse('game:my_stats'), probe).json()
            self.assertEqual(d['stats']['best_score'], 50,
                             'параметр %r пробил границу' % probe)

    def test_stats_are_per_mode(self):
        self.client.force_login(self.a)
        d = self.client.get(reverse('game:my_stats'), {'mode': 'rapid'}).json()
        self.assertEqual(d['stats']['runs'], 0)

    def test_place_is_reported(self):
        self.client.force_login(self.b)
        d = self.client.get(reverse('game:my_stats')).json()
        self.assertEqual(d['stats']['place'], 2)
        self.assertEqual(d['stats']['total_players'], 2)


class ApiShapeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(username='anya', password='p12345')
        run(self.a, score=300, correct=12)

    def test_garbage_parameters_fall_back_instead_of_crashing(self):
        d = self.client.get(reverse('game:leaderboard'),
                            {'mode': 'ой', 'period': 'век',
                             'metric': 'магия'}).json()
        self.assertEqual(d['mode'], config.DEFAULT_MODE)
        self.assertEqual(d['period'], 'all')
        self.assertEqual(d['metric'], 'score')

    def test_first_tab_comes_with_the_page_so_it_does_not_blink(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        self.assertIn('"leaderboard"', html)


class MyHistoryBoundaryTests(TestCase):
    u"""История забегов: только про себя, и она с СЕРВЕРА (08.09.2026).

    ⚠️ ПОЧЕМУ ПЕРЕЕХАЛА. Прежняя история жила в localStorage браузера:
    терялась при смене браузера, а два источника истории разъехались бы при
    первом же расхождении. Источник теперь один — `GameResult`.
    """

    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(username='hist_a', password='p12345')
        self.b = User.objects.create_user(username='hist_b', password='p12345')

    def url(self):
        return reverse('game:my_history')

    def test_anonymous_gets_403_not_a_redirect(self):
        u"""⚠️ Эндпоинт зовёт fetch: редирект вернул бы ему HTML входа."""
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r['Content-Type'].split(';')[0], 'application/json')

    def test_no_parameter_can_ask_for_someone_elses_history(self):
        u"""Параметра «чей» нет и не будет: перебор номеров сделал бы личную
        историю публичной. То же правило, что у `api_my_stats`."""
        run(self.a, score=999, correct=30)
        run(self.b, score=11, correct=1)
        self.client.force_login(self.b)
        for probe in ({'user': self.a.id}, {'user_id': self.a.id},
                      {'username': 'hist_a'}, {'me': self.a.id}):
            d = self.client.get(self.url(), probe).json()
            self.assertEqual([r['score'] for r in d['runs']], [11],
                             'параметр %r пробил границу' % probe)

    def test_an_empty_history_is_empty_not_zeroed(self):
        u"""⚠️ Нуля забегов не бывает «в среднем»: `avg` тут None, не ноль.

        Иначе экран нарисовал бы сравнение с выдуманным средним.
        """
        self.client.force_login(self.a)
        d = self.client.get(self.url()).json()
        self.assertEqual(d['runs'], [])
        self.assertIsNone(d['avg'])
        self.assertEqual(d['total'], 0)

    def test_runs_come_oldest_first_and_are_capped(self):
        u"""На графике время идёт слева направо, и хвост ограничен."""
        from game import leaderboard as lb
        for i in range(lb.HISTORY_LIMIT + 5):
            run(self.a, score=i, correct=1)
        self.client.force_login(self.a)
        d = self.client.get(self.url()).json()
        self.assertEqual(len(d['runs']), lb.HISTORY_LIMIT)
        scores = [r['score'] for r in d['runs']]
        self.assertEqual(scores, sorted(scores), 'порядок не по возрастанию')
        self.assertEqual(scores[-1], lb.HISTORY_LIMIT + 4)   # последний забег
        self.assertEqual(d['total'], lb.HISTORY_LIMIT + 5)

    def test_the_average_is_over_all_runs_not_just_the_listed_ones(self):
        u"""⚠️ «Как я играю обычно» и «как шли последние раунды» — разные
        вопросы. Считать среднее по двадцати значило бы менять смысл слова
        «обычно» вместе с длиной списка."""
        from game import leaderboard as lb
        for _ in range(lb.HISTORY_LIMIT):
            run(self.a, score=100, correct=10)
        run(self.a, score=0, correct=0, wrong=10, avg_ms=None)
        self.client.force_login(self.a)
        d = self.client.get(self.url()).json()
        total = lb.HISTORY_LIMIT + 1
        self.assertEqual(d['total'], total)
        self.assertEqual(d['avg']['score'],
                         round(100 * lb.HISTORY_LIMIT / total))

    def test_history_is_per_mode(self):
        run(self.a, mode='blitz', score=500, correct=20)
        run(self.a, mode='bullet', score=70, correct=4)
        self.client.force_login(self.a)
        d = self.client.get(self.url(), {'mode': 'bullet'}).json()
        self.assertEqual([r['score'] for r in d['runs']], [70])

    def test_a_missing_speed_never_becomes_a_zero(self):
        u"""«В среднем ноль миллисекунд» — не факт, а отсутствие факта."""
        run(self.a, score=100, correct=5, avg_ms=None)
        self.client.force_login(self.a)
        d = self.client.get(self.url()).json()
        self.assertIsNone(d['avg']['avg_correct_ms'])


class RecordsPanelTests(TestCase):
    u"""Панель «Мои рекорды»: серверные данные, никаких новых таблиц.

    ⚠️ ГДЕ ЖИВЁТ. Панель отдаёт `api_my_stats` полем `panel`, а не свой
    эндпоинт: это ровно «личная статистика, только про себя», и граница у
    неё та же самая — второй эндпоинт означал бы второе место, где ту же
    границу надо не забыть удержать.
    """

    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(username='rec_a', password='p12345')
        self.b = User.objects.create_user(username='rec_b', password='p12345')

    def panel(self, mode='all', user=None):
        self.client.force_login(user or self.a)
        return self.client.get(reverse('game:my_stats'),
                               {'panel_mode': mode}).json()['panel']

    def test_a_player_without_runs_gets_no_numbers_at_all(self):
        u"""⚠️ Числовой инвариант: у игрока без забегов панель пуста.

        Нули вместо статистики — выдуманные числа: их на экране быть не
        должно, а «сыграно 0 раундов, точность 0 %» читается как факт.
        """
        p = self.panel()
        self.assertEqual(p['runs'], 0)
        self.assertEqual(set(p), {'mode', 'runs'})

    def test_aggregates_match_a_second_count_over_game_result(self):
        u"""Числовой инвариант фазы: считаем двумя способами и сверяем."""
        run(self.a, mode='blitz', score=300, correct=12, wrong=3, avg_ms=2000)
        run(self.a, mode='blitz', score=500, correct=20, wrong=0, avg_ms=3000)
        run(self.a, mode='bullet', score=90, correct=5, wrong=5, avg_ms=1000)

        rows = GameResult.objects.filter(user=self.a,
                                         economy_version=config.ECONOMY_VERSION)
        correct = sum(r.correct_count for r in rows)
        attempts = sum(r.correct_count + r.wrong_count for r in rows)
        speeds = [r.avg_correct_ms for r in rows if r.avg_correct_ms]

        p = self.panel('all')
        self.assertEqual(p['runs'], rows.count())
        self.assertEqual(p['best_score'], max(r.score for r in rows))
        self.assertEqual(p['accuracy'], round(100 * correct / attempts))
        self.assertEqual(p['avg_correct_ms'],
                         int(sum(speeds) / len(speeds)))

    def test_one_mode_counts_only_that_mode(self):
        run(self.a, mode='blitz', score=300, correct=12)
        run(self.a, mode='bullet', score=90, correct=5)
        self.assertEqual(self.panel('blitz')['runs'], 1)
        self.assertEqual(self.panel('blitz')['best_score'], 300)

    def test_someone_elses_runs_never_leak_in(self):
        run(self.a, score=100, correct=5)
        run(self.b, score=9999, correct=99)
        p = self.panel('all', user=self.a)
        self.assertEqual(p['runs'], 1)
        self.assertEqual(p['best_score'], 100)

    def test_the_record_line_is_a_running_maximum(self):
        u"""Линия рекорда показывает, КОГДА игрок себя обошёл."""
        for score in (100, 50, 300, 200):
            run(self.a, score=score, correct=5)
        p = self.panel('all')
        self.assertEqual([r['score'] for r in p['timeline']],
                         [100, 50, 300, 200])
        self.assertEqual([r['best'] for r in p['timeline']],
                         [100, 100, 300, 300])

    def test_topic_accuracy_is_aggregated_from_the_runs_themselves(self):
        u"""Новой таблицы нет: разбивка лежит полем в каждом забеге."""
        GameResult.objects.create(
            code=make_result_code(), mode='blitz', user=self.a, score=10,
            correct_count=1, wrong_count=1,
            economy_version=config.ECONOMY_VERSION,
            topic_breakdown=[{'topic': 'Эластичность', 'correct': 1, 'wrong': 1}])
        GameResult.objects.create(
            code=make_result_code(), mode='blitz', user=self.a, score=10,
            correct_count=2, wrong_count=0,
            economy_version=config.ECONOMY_VERSION,
            topic_breakdown=[{'topic': 'Эластичность', 'correct': 2, 'wrong': 0}])
        rows = {r['topic']: r for r in self.panel('all')['topic_rows']}
        self.assertEqual(rows['Эластичность']['correct'], 3)
        self.assertEqual(rows['Эластичность']['total'], 4)
        self.assertEqual(rows['Эластичность']['accuracy'], 75)

    def test_activity_covers_exactly_thirty_days(self):
        from game import leaderboard as lb
        run(self.a, score=100, correct=5)
        days = self.panel('all')['activity']
        self.assertEqual(len(days), lb.ACTIVITY_DAYS)
        self.assertEqual(sum(d['count'] for d in days), 1)

    def test_the_leader_has_no_gap_above_and_that_is_not_zero(self):
        u"""⚠️ Ноль читался бы как «догнал». Выше никого — это None."""
        run(self.a, mode='blitz', score=1000, correct=40)
        self.assertIsNone(self.panel('blitz')['place']['gap'])

    def test_the_gap_is_the_distance_to_the_neighbour_above(self):
        run(self.a, mode='blitz', score=400, correct=20)
        run(self.b, mode='blitz', score=650, correct=30)
        place = self.panel('blitz', user=self.a)['place']
        self.assertEqual(place['place'], 2)
        self.assertEqual(place['gap'], 250)

    def test_anonymous_is_turned_away_from_the_panel_too(self):
        r = self.client.get(reverse('game:my_stats'), {'panel_mode': 'all'})
        self.assertIn(r.status_code, (302, 403), r.status_code)
