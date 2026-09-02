# -*- coding: utf-8 -*-
u"""
Состояние забега живёт в кэше, а не в сессии.

Три проверки, ради которых переезд и делался:
- забег переживает смену воркера (состояние адресуется по run_id, а не
  лежит в куке одного игрока);
- забег виден по run_id БЕЗ сессии — это то, что нужно дуэли;
- истёкшее состояние даёт честный `no_run`, а не полузабег.
"""
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from game import state as run_state
from game.models import GameQuestion
from problems.models import Problem


def make_q(qtype='single', **kw):
    p = Problem.objects.create(
        title='Т', statement='Условие про рынок.',
        problem_type='тест: один ответ', answer='а',
        status=Problem.Status.PUBLISHED)
    defaults = dict(
        question_type=qtype, question='Что произойдёт со спросом?',
        options=['вырастет', 'упадёт', 'не изменится'], correct_index=0,
        difficulty=3, topics=['Спрос и предложение'], lang='ru',
        source_group='books')
    defaults.update(kw)
    return GameQuestion.objects.create(problem=p, **defaults)


class RunStateStorageTests(TestCase):

    def setUp(self):
        cache.clear()
        for _ in range(6):
            make_q()

    def start(self, client=None, mode='blitz'):
        c = client or self.client
        return c.get(reverse('game:session_start') + '?mode=' + mode).json()

    def test_session_keeps_only_the_id(self):
        u"""В куке — идентификатор, и больше ничего от забега."""
        self.assertTrue(self.start()['ok'])
        session = dict(self.client.session)
        self.assertIn(run_state.RUN_ID_KEY, session)
        self.assertNotIn(run_state.LEGACY_SESSION_KEY, session)
        run_id = session[run_state.RUN_ID_KEY]
        self.assertEqual(len(run_id), 32)
        # Ни очков, ни жизней, ни журнала в сессии нет.
        blob = json.dumps(session, default=str)
        for field in ('"lives"', '"score"', '"issued_at"', '"log"'):
            self.assertNotIn(field, blob)

    def test_state_is_readable_by_id_without_a_session(self):
        u"""То, ради чего переезжали: дуэли нужен счёт соперника, а сессии
        соперника у сервера нет."""
        self.start()
        run_id = self.client.session[run_state.RUN_ID_KEY]
        state = run_state.load_by_id(run_id)
        self.assertIsNotNone(state)
        self.assertEqual(state['mode'], 'blitz')
        self.assertEqual(state['run_id'], run_id)

    def test_run_survives_a_worker_change(self):
        u"""Два клиента с ОДНОЙ сессией видят один и тот же забег.

        Это и есть смена воркера с точки зрения теста: второй клиент —
        другой процесс, у которого нет ничего, кроме куки сессии.
        """
        self.start()
        self.client.get(reverse('game:question'))
        first = run_state.load_by_id(
            self.client.session[run_state.RUN_ID_KEY])

        other = self.client_class()
        other.cookies = self.client.cookies
        payload = other.get(reverse('game:question')).json()
        self.assertIn('question', payload)

        second = run_state.load_by_id(
            self.client.session[run_state.RUN_ID_KEY])
        self.assertEqual(second['run_id'], first['run_id'])
        # Второй клиент ДОПИСАЛ в тот же забег, а не начал свой.
        self.assertEqual(len(second['seen']), len(first['seen']) + 1)

    def test_expired_state_answers_no_run(self):
        u"""Истёк TTL — честный отказ, а не полузабег."""
        self.start()
        run_id = self.client.session[run_state.RUN_ID_KEY]
        cache.delete(run_state.cache_key(run_id))

        resp = self.client.get(reverse('game:question'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['reason'], 'no_run')
        # Протухший идентификатор из сессии убран: второй заход в кэш зря.
        self.assertNotIn(run_state.RUN_ID_KEY, dict(self.client.session))

    def test_ttl_follows_the_mode(self):
        u"""Срок жизни считается от запаса режима, а не одним числом.

        У Пули минута, у Классики десять — общий TTL был бы либо коротким
        для Классики, либо бессмысленно длинным для Пули.
        """
        self.assertEqual(run_state.ttl_for('bullet'),
                         2 * 60 + run_state.TTL_SLACK)
        self.assertEqual(run_state.ttl_for('classic'),
                         2 * 600 + run_state.TTL_SLACK)
        self.assertGreater(run_state.ttl_for('classic'),
                           run_state.ttl_for('bullet'))

    def test_every_run_gets_its_own_id(self):
        u"""«Сыграть ещё раз» не переиспользует идентификатор."""
        self.start()
        first = self.client.session[run_state.RUN_ID_KEY]
        self.start()
        second = self.client.session[run_state.RUN_ID_KEY]
        self.assertNotEqual(first, second)


class LegacyRunTests(TestCase):
    u"""Забег, начатый ДО выкатки, доигрывается."""

    def setUp(self):
        cache.clear()
        for _ in range(6):
            make_q()

    def test_old_session_state_is_moved_into_the_cache(self):
        self.client.get(reverse('game:session_start') + '?mode=blitz')
        run_id = self.client.session[run_state.RUN_ID_KEY]
        old = run_state.load_by_id(run_id)

        # Возвращаем мир в состояние «до выкатки»: забег в сессии целиком.
        session = self.client.session
        del session[run_state.RUN_ID_KEY]
        old.pop('run_id', None)
        session[run_state.LEGACY_SESSION_KEY] = old
        session.save()
        cache.delete(run_state.cache_key(run_id))

        payload = self.client.get(reverse('game:question')).json()
        self.assertIn('question', payload, 'старый забег не доигрался')
        # И переехал: старого ключа больше нет, новый есть.
        session = dict(self.client.session)
        self.assertNotIn(run_state.LEGACY_SESSION_KEY, session)
        self.assertIn(run_state.RUN_ID_KEY, session)
