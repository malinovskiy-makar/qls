"""
Тесты вызова дня (Фаза 4).

Ключевой инвариант: набор дня строится ДЕТЕРМИНИРОВАННО от даты и режима.
Крона нет (бесплатный хостинг засыпает), набор создаётся лениво при первом
обращении — и если бы список был случайным, «первое обращение» решало бы,
во что играет весь день весь мир.
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
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
        self.assertContains(r, 'архивная доска')

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
