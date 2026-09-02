# -*- coding: utf-8 -*-
"""Фаза 1.1: инструментированная обёртка считает 429/обрывы/задержки без
сети — сама сеть проверяется живым прогоном, не тестом."""
import threading
from unittest import mock

from django.test import TestCase

from problems.ai import providers
from problems.management.commands import glm_ramp_probe as ramp
from problems.management.commands import pilot_enrich_v2 as pilot


class _FakeReply:
    def __init__(self, text='{}', input_tokens=10, output_tokens=5,
                cache_write_tokens=0, cache_read_tokens=0, reasoning_tokens=0):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_write_tokens = cache_write_tokens
        self.cache_read_tokens = cache_read_tokens
        self.reasoning_tokens = reasoning_tokens


class InstrumentedCompleteFnTests(TestCase):
    def _stats(self):
        return {'latencies': [], 'ok': 0, 'rate_limited': 0,
               'connection_drops': 0, 'fatal': 0}, threading.Lock()

    def test_успешный_вызов_считается_в_ok(self):
        stats, lock = self._stats()
        with mock.patch.object(providers.GLMProvider, 'complete',
                               return_value=_FakeReply()):
            complete_fn = ramp.make_instrumented_glm_complete_fn(stats, lock)
            reply = complete_fn('glm-5.3-flash', ['ядро'], 'текст', {}, 'low')
        self.assertEqual(reply.text, '{}')
        self.assertEqual(stats['ok'], 1)
        self.assertEqual(len(stats['latencies']), 1)
        self.assertEqual(stats['rate_limited'], 0)

    def test_429_считается_и_повторяется_до_успеха(self):
        stats, lock = self._stats()
        limit_error = providers.ProviderError('too many requests', kind='limit')
        with mock.patch.object(
                providers.GLMProvider, 'complete',
                side_effect=[limit_error, limit_error, _FakeReply()]):
            with mock.patch('time.sleep'):  # не ждать реальный backoff в тесте
                complete_fn = ramp.make_instrumented_glm_complete_fn(stats, lock)
                reply = complete_fn('glm-5.3-flash', ['ядро'], 'текст', {}, 'low')
        self.assertEqual(reply.text, '{}')
        self.assertEqual(stats['rate_limited'], 2)
        self.assertEqual(stats['ok'], 1)
        self.assertEqual(len(stats['latencies']), 3)

    def test_обрыв_сети_считается_как_other(self):
        stats, lock = self._stats()
        drop_error = providers.ProviderError('connection reset', kind='other')
        with mock.patch.object(
                providers.GLMProvider, 'complete',
                side_effect=[drop_error, _FakeReply()]):
            with mock.patch('time.sleep'):
                complete_fn = ramp.make_instrumented_glm_complete_fn(stats, lock)
                complete_fn('glm-5.3-flash', ['ядро'], 'текст', {}, 'low')
        self.assertEqual(stats['connection_drops'], 1)
        self.assertEqual(stats['ok'], 1)

    def test_фатальная_ошибка_не_повторяется(self):
        stats, lock = self._stats()
        fatal_error = providers.ProviderError('bad key', kind='no_key')
        with mock.patch.object(providers.GLMProvider, 'complete',
                               side_effect=fatal_error):
            complete_fn = ramp.make_instrumented_glm_complete_fn(stats, lock)
            with self.assertRaises(providers.ProviderError):
                complete_fn('glm-5.3-flash', ['ядро'], 'текст', {}, 'low')
        self.assertEqual(stats['fatal'], 1)
        self.assertEqual(stats['ok'], 0)

    def test_исчерпание_попыток_бросает_последнюю_ошибку(self):
        stats, lock = self._stats()
        limit_error = providers.ProviderError('too many requests', kind='limit')
        with mock.patch.object(providers.GLMProvider, 'complete',
                               side_effect=limit_error):
            with mock.patch('time.sleep'):
                complete_fn = ramp.make_instrumented_glm_complete_fn(stats, lock)
                with self.assertRaises(providers.ProviderError):
                    complete_fn('glm-5.3-flash', ['ядро'], 'текст', {}, 'low')
        self.assertEqual(stats['rate_limited'], ramp.MAX_ATTEMPTS)


class RunOneLevelTests(TestCase):
    """`run_one_level` склеивает `run_variant_concurrent` со статистикой —
    здесь только форма результата, не сеть."""

    def test_метрики_считаются_из_прогона(self):
        problems = [pilot.Problem.objects.create(statement='Задача %d.' % i)
                   for i in range(4)]
        shortlists = {p.id: [] for p in problems}
        variant = {'call1_model': 'glm-5.3-flash', 'call1_effort': 'low',
                  'call2_model': 'glm-5.3-flash', 'call2_effort': 'low',
                  'concepts': True}

        # topic_primary/tags — настоящие id из data/taxonomy.json, поля
        # call2 — точно по CALL2_SCHEMA (difficulty_note, не
        # difficulty_reason; plot/hints обязательны, пусть и null) —
        # иначе check_against_schema() в боевом пути даёт лишний повтор
        # и attempts_total считает не то, что ожидает тест.
        call1_json = ('{"topic_primary": "1", "topics_secondary": [], "tags": ["1.1"], '
                     '"given": "Дано", "find": "Найти", "econ_concepts": ["a","b","c"], '
                     '"concepts_offlist": [], "task_nature": "расчётная", '
                     '"features_1": [], "topic_confidence": "высокая"}')
        call2_json = ('{"search_queries": ["a","b","c","d","e","f","g","h"], '
                     '"text_quality": "чистая", "text_quality_note": "", '
                     '"problem_type": "открытый_ответ", "difficulty": 2, '
                     '"difficulty_note": "просто", '
                     '"answer_consistency": "решение_отсутствует_проверить_нечем", '
                     '"plot": null, "hints": null, '
                     '"title_candidate": "Заголовок Тут"}')

        def fake_complete(blocks, user_text, schema, model, max_tokens, images=None):
            is_call1 = 'topic_primary' in schema.get('properties', {})
            return _FakeReply(call1_json if is_call1 else call2_json)

        with mock.patch.object(providers.GLMProvider, 'complete',
                               side_effect=fake_complete):
            metrics = ramp.run_one_level(problems, variant, shortlists,
                                         workers=2, max_cost=100.0)

        self.assertEqual(metrics['tasks_done'], 4)
        self.assertEqual(metrics['attempts_total'], 8)
        self.assertEqual(metrics['rate_limited'], 0)
        self.assertGreaterEqual(metrics['requests_per_min'], 0)
