# -*- coding: utf-8 -*-
u"""Зачётность забега и анти-чит (фаза 5).

Забег попадает в таблицу, только если выполнены ВСЕ условия сразу. Каждая
причина незачётности проверяется отдельно: «просто не поехал» читается как
поломка, и человеку показывается именно та причина, которая сработала.
"""
import datetime
import json
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import Problem, User
from game import config, views
from game import state as run_state
from game.models import GameQuestion, GameResult, GameSet, make_result_code

MSK = ZoneInfo('Europe/Moscow')


def make_q(difficulty=3, qtype='single', **kw):
    p = Problem.objects.create(
        title='Т', statement='Условие про рынок.',
        problem_type='тест: один ответ', answer='а',
        status=Problem.Status.PUBLISHED)
    defaults = dict(
        question_type=qtype, question='Что произойдёт со спросом?',
        options=['вырастет', 'упадёт', 'не изменится'], correct_index=0,
        difficulty=difficulty, topics=['Спрос и предложение'], lang='ru')
    defaults.update(kw)
    return GameQuestion.objects.create(problem=p, **defaults)


class RunHelper(TestCase):
    u"""Общая машинка: сыграть забег и завершить его."""

    def setUp(self):
        for _ in range(40):
            make_q()

    def login(self):
        u = User.objects.create_user(username='igrok', password='pw12345')
        self.client.force_login(u)
        return u

    def play(self, correct=6, query='', finish=True):
        u"""Сыграть забег: `correct` верных ответов подряд."""
        d = self.client.get(reverse('game:session_start')
                            + '?mode=blitz' + query).json()
        self.assertTrue(d.get('ok'), d)
        qid = d['question']['id']
        for _ in range(correct):
            gq = GameQuestion.objects.get(id=qid)
            self.client.post(
                reverse('game:answer'),
                json.dumps({'question_id': qid, 'choice': gq.correct_index}),
                content_type='application/json')
            nxt = self.client.get(reverse('game:question')).json()
            if not nxt.get('question'):
                break
            qid = nxt['question']['id']
        if not finish:
            return None
        return self.client.post(reverse('game:session_finish'),
                                json.dumps({'reason': 'time'}),
                                content_type='application/json').json()


class UnrankedReasonsTests(RunHelper):
    u"""Семь причин незачётности — по тесту на каждую."""

    def test_anonymous(self):
        self.play()
        r = GameResult.objects.get()
        self.assertFalse(r.ranked)
        self.assertEqual(r.unranked_reason, 'anonymous')

    def test_too_few_correct(self):
        self.login()
        self.play(correct=config.RANKED_MIN_CORRECT - 1)
        r = GameResult.objects.get()
        self.assertFalse(r.ranked)
        self.assertEqual(r.unranked_reason, 'too_few_correct')

    def test_difficulty_filter(self):
        self.login()
        self.play(query='&stars=3')
        r = GameResult.objects.get()
        self.assertFalse(r.ranked)
        self.assertEqual(r.unranked_reason, 'difficulty_filter')

    def test_topic_filter_stays_ranked(self):
        u"""Темы меняют, ЧТО решаешь, а не КАК ТРУДНО."""
        self.login()
        self.play(query='&topics=%D0%A1%D0%BF%D1%80%D0%BE%D1%81+%D0%B8+'
                        '%D0%BF%D1%80%D0%B5%D0%B4%D0%BB%D0%BE%D0%B6%D0%B5%D0%BD%D0%B8%D0%B5')
        r = GameResult.objects.get()
        self.assertTrue(r.ranked, r.unranked_reason)
        self.assertFalse(r.is_unfiltered)

    def test_mistakes_run(self):
        self.login()
        # Сначала обычный забег с ошибкой — иначе работе над ошибками нечего
        # брать; потом целевой забег по её темам.
        d = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        qid = d['question']['id']
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': qid, 'choice': 1}),
                         content_type='application/json')
        self.client.post(reverse('game:session_finish'), json.dumps({'reason': 'time'}),
                         content_type='application/json')
        GameResult.objects.all().delete()
        started = self.client.get(reverse('game:session_start_mistakes')).json()
        if not started.get('ok'):
            self.skipTest('целевой забег не собрался на этих данных')
        qid = started['question']['id']
        gq = GameQuestion.objects.get(id=qid)
        self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid, 'choice': gq.correct_index}),
            content_type='application/json')
        self.client.post(reverse('game:session_finish'), json.dumps({'reason': 'done'}),
                         content_type='application/json')
        r = GameResult.objects.get()
        self.assertFalse(r.ranked)
        self.assertEqual(r.unranked_reason, 'mistakes_run')

    def test_set_run(self):
        u"""У набора, дуэли и вызова дня своя доска."""
        self.login()
        ids = list(GameQuestion.objects.values_list('id', flat=True)[:6])
        gset = GameSet.objects.create(code=make_result_code(), mode='blitz',
                                      kind='custom', question_ids=ids,
                                      filter_snapshot={})
        d = self.client.get(reverse('game:session_start_set',
                                    args=[gset.code])).json()
        self.assertTrue(d.get('ok'), d)
        qid = d['question']['id']
        for _ in range(6):
            gq = GameQuestion.objects.get(id=qid)
            self.client.post(
                reverse('game:answer'),
                json.dumps({'question_id': qid, 'choice': gq.correct_index}),
                content_type='application/json')
            nxt = self.client.get(reverse('game:question')).json()
            if not nxt.get('question'):
                break
            qid = nxt['question']['id']
        self.client.post(reverse('game:session_finish'), json.dumps({'reason': 'done'}),
                         content_type='application/json')
        r = GameResult.objects.get()
        self.assertFalse(r.ranked)
        self.assertEqual(r.unranked_reason, 'set_run')

    def test_time_overrun(self):
        u"""Забег не может идти дольше запаса плюс вся прибавка плюс минута.

        Больше — значит вкладку держали на паузе: очки считает сервер, а вот
        времени на подумать так можно взять сколько угодно.
        """
        self.login()
        limit = int((config.MODES['blitz']['duration']
                     * (1 + config.TIME_BONUS_CAP_FACTOR) + 60) * 1000)
        ok, reason = views._rank_run(
            _req(self.client), {'mode': 'blitz', 'filter': {}},
            {'correct': 9, 'wrong': 1}, limit + 1)
        self.assertFalse(ok)
        self.assertEqual(reason, 'time_overrun')
        ok2, _ = views._rank_run(
            _req(self.client), {'mode': 'blitz', 'filter': {}},
            {'correct': 9, 'wrong': 1}, limit - 1)
        self.assertTrue(ok2)

    def test_every_reason_has_human_text(self):
        u"""Игрок обязан прочитать причину словами, а не код."""
        for key, text in config.UNRANKED_REASONS:
            self.assertTrue(text and not text.isupper(), key)
        self.assertEqual(len(config.UNRANKED_TEXT), 8)


def _req(client):
    u"""Запрос с тем же вошедшим пользователем, что у клиента."""
    from django.test import RequestFactory
    r = RequestFactory().get('/game/')
    from django.contrib.auth.models import AnonymousUser
    r.user = User.objects.filter(username='igrok').first() or AnonymousUser()
    return r


class RankedRunTests(RunHelper):
    u"""Забег, который ДОЛЖЕН попасть в таблицу."""

    def test_clean_run_is_ranked(self):
        self.login()
        d = self.play()
        r = GameResult.objects.get()
        self.assertTrue(r.ranked, r.unranked_reason)
        self.assertEqual(r.unranked_reason, '')
        self.assertTrue(r.is_unfiltered)
        self.assertEqual(r.economy_version, config.ECONOMY_VERSION)
        self.assertTrue(d['summary']['ranked'])

    def test_server_side_numbers_are_saved(self):
        self.login()
        self.play()
        r = GameResult.objects.get()
        self.assertGreater(r.raw_score, 0)
        self.assertIsNotNone(r.wall_ms)
        self.assertIsNotNone(r.avg_correct_ms)
        self.assertEqual(r.wrong_count, 0)
        self.assertAlmostEqual(r.accuracy_mult, 1.0)

    def test_fractional_combo_survives_the_database(self):
        u"""⚠️ Множители v2 дробные. В целом поле 1,25 молча становилось
        единицей, и серия из четырёх выглядела как её отсутствие."""
        r = GameResult.objects.create(code=make_result_code(), mode='blitz',
                                      max_combo=1.25)
        r.refresh_from_db()
        self.assertAlmostEqual(r.max_combo, 1.25)


class QuotaTests(RunHelper):
    u"""Квота зачётных забегов: 10 на режим за МОСКОВСКИЕ сутки."""

    def _fill(self, user, n, when=None):
        for _ in range(n):
            r = GameResult.objects.create(
                code=make_result_code(), mode='blitz', ranked=True, user=user)
            if when is not None:
                GameResult.objects.filter(pk=r.pk).update(created_at=when)

    def test_eleventh_run_of_the_day_is_not_ranked(self):
        u = self.login()
        self._fill(u, config.RANKED_RUNS_PER_DAY)
        self.play()
        last = GameResult.objects.order_by('-created_at').first()
        self.assertFalse(last.ranked)
        self.assertEqual(last.unranked_reason, 'quota_exceeded')

    def test_tenth_run_still_counts(self):
        u = self.login()
        self._fill(u, config.RANKED_RUNS_PER_DAY - 1)
        self.play()
        last = GameResult.objects.order_by('-created_at').first()
        self.assertTrue(last.ranked, last.unranked_reason)

    def test_yesterday_does_not_eat_todays_quota(self):
        u = self.login()
        yesterday = timezone.now() - datetime.timedelta(days=1)
        self._fill(u, config.RANKED_RUNS_PER_DAY, when=yesterday)
        self.play()
        last = GameResult.objects.order_by('-created_at').first()
        self.assertTrue(last.ranked, last.unranked_reason)

    def test_quota_is_per_mode(self):
        u = self.login()
        for _ in range(config.RANKED_RUNS_PER_DAY):
            GameResult.objects.create(code=make_result_code(), mode='rapid',
                                      ranked=True, user=u)
        self.play()
        last = GameResult.objects.filter(mode='blitz').first()
        self.assertTrue(last.ranked, last.unranked_reason)

    def test_day_boundary_is_moscow_not_utc(self):
        u"""⚠️ По UTC «сегодня» кончалось бы в три часа ночи, и игрок,
        играющий вечером, получал бы два дневных лимита подряд.

        Момент подаём в UTC, а не в московской зоне: иначе перевод не
        проверяется вовсе — `.date()` от уже московского времени даст тот
        же ответ, что и правильный перевод.
        """
        utc_evening = datetime.datetime(2026, 9, 1, 21, 30,
                                        tzinfo=datetime.timezone.utc)
        self.assertEqual(utc_evening.date(), datetime.date(2026, 9, 1))
        # По Москве это уже 2 сентября, 00:30 — и квота считается по нему.
        self.assertEqual(views._moscow_day(utc_evening),
                         datetime.date(2026, 9, 2))
        utc_morning = datetime.datetime(2026, 9, 2, 20, 59,
                                        tzinfo=datetime.timezone.utc)
        self.assertEqual(views._moscow_day(utc_morning),
                         datetime.date(2026, 9, 2))

    def test_quota_line_is_empty_for_anonymous(self):
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        r = RequestFactory().get('/game/')
        r.user = AnonymousUser()
        self.assertEqual(views._quota_line(r), '')


class AntiCheatTests(RunHelper):
    u"""Что клиент НЕ должен получать раньше времени."""

    def test_question_payload_has_no_problem_id(self):
        u"""По problem_id задача открывалась в каталоге вместе с ответом —
        то есть подсмотреть можно было ДО ответа."""
        d = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        self.assertNotIn('problem_id', d['question'])

    def test_answer_response_has_problem_id(self):
        u"""Ссылку «в каталог» клиент собирает отсюда — когда уже поздно."""
        d = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        qid = d['question']['id']
        body = self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid, 'choice': 0}),
            content_type='application/json').json()
        self.assertIn('problem_id', body)
        self.assertIsNotNone(body['problem_id'])

    def test_answer_time_is_measured_by_the_server(self):
        u"""Клиентское `elapsed_ms` в очки не входит: его подделывает любой,
        кто откроет консоль."""
        d = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        qid = d['question']['id']
        gq = GameQuestion.objects.get(id=qid)
        honest = self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid, 'choice': gq.correct_index}),
            content_type='application/json').json()
        # Тот же вопрос, но клиент врёт про мгновенный ответ.
        d2 = self.client.get(reverse('game:session_start') + '?mode=blitz').json()
        qid2 = d2['question']['id']
        gq2 = GameQuestion.objects.get(id=qid2)
        liar = self.client.post(
            reverse('game:answer'),
            json.dumps({'question_id': qid2, 'choice': gq2.correct_index,
                        'elapsed_ms': 1}),
            content_type='application/json').json()
        self.assertEqual(honest['points'], liar['points'],
                         'клиентское время повлияло на очки')

    def test_issued_at_is_stored_server_side(self):
        self.client.get(reverse('game:session_start') + '?mode=blitz')
        state = run_state.load_by_id(
            self.client.session[run_state.RUN_ID_KEY])
        self.assertTrue(state.get('issued_at'))
        self.assertTrue(state.get('started_at'))
