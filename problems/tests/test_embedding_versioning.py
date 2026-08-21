# -*- coding: utf-8 -*-
"""С5 (22.08) — версионирование эмбеддингов.

Раньше «что устарело» было памятью человека в файле embeddings_done_ids.txt:
правишь текст задачи, а её id уже в файле — пересчёт молча пропускал и писал
«осталось 0» (CLAUDE.md, ловушка done-файла). `build_embeddings --stale`
сравнивает четыре новых поля Problem с текущими константами/текстом сам.

Модель эмбеддингов в тестах не грузится — `sentence_transformers` даже не
установлен в dev-окружении (тяжёлая ML-зависимость, импорт в команде
намеренно ленивый, см. build_embeddings.py). Поэтому мокается не атрибут
пакета (патчить нечего — пакета нет), а сам модуль в `sys.modules`: пока
фейковый модуль там, `from sentence_transformers import SentenceTransformer`
внутри команды находит его как настоящий.
"""
import sys
import types
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.test import TestCase

from problems.embedding_config import (
    EMBEDDING_DIM, EMBEDDING_FORMULA_VERSION, EMBEDDING_MODEL_BUILD,
)
from problems.management.commands.build_embeddings import (
    embedding_source_hash, is_stale, problem_to_text,
)
from problems.models import Problem
from problems.tests.factories import make_problem


class _FakeSentenceTransformer:
    """Кодирует чем угодно, лишь бы формы и типы совпадали с настоящей."""

    def __init__(self, *args, **kwargs):
        pass

    def encode(self, texts, **kwargs):
        return np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)


def _fake_sentence_transformers_module():
    module = types.ModuleType('sentence_transformers')
    module.SentenceTransformer = _FakeSentenceTransformer
    return module


class _FakeModelMixin:
    """Подменяет sys.modules['sentence_transformers'] на весь тест."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(
            sys.modules, {'sentence_transformers': _fake_sentence_transformers_module()})
        patcher.start()
        self.addCleanup(patcher.stop)


class StaleSelectionTests(_FakeModelMixin, TestCase):
    """ЧИСЛОВОЙ ИНВАРИАНТ: изменил текст одной задачи → --stale берёт ровно
    её одну, а не 0 (файл забыл) и не все (сравнение сломано)."""

    def test_ровно_одна_изменённая_задача_попадает_в_stale(self):
        неизменная = make_problem(statement='Условие А. Оно не меняется.')
        изменяемая = make_problem(statement='Условие Б, версия первая.')

        # «Эмбеддинг уже посчитан» — реальный прогон --reset, не фикстура:
        # так поля версии/хеша/времени проставляются тем же кодом, что и
        # на проде, а не руками мимо команды.
        call_command('build_embeddings', reset=True, verbosity=0)

        снимок_до = {
            p.id: p.embedding_built_at for p in Problem.objects.all()
        }
        self.assertIsNotNone(снимок_до[неизменная.id])
        self.assertIsNotNone(снимок_до[изменяемая.id])

        изменяемая.statement = 'Условие Б, версия ВТОРАЯ — текст изменён.'
        изменяемая.save(update_fields=['statement'])

        call_command('build_embeddings', stale=True, verbosity=0)

        снимок_после = {
            p.id: p.embedding_built_at for p in Problem.objects.all()
        }
        пересчитанные = [
            pid for pid, время_до in снимок_до.items()
            if снимок_после[pid] != время_до
        ]

        self.assertEqual(
            пересчитанные, [изменяемая.id],
            'Ожидалась ровно одна пересчитанная задача — изменённая. '
            'Пусто значит --stale ничего не нашёл (сравнение сломано); '
            'больше одной значит зацепило лишнее.')

        изменяемая.refresh_from_db()
        self.assertEqual(
            изменяемая.embedding_source_hash,
            embedding_source_hash(problem_to_text(изменяемая)))

    def test_неизменная_задача_не_трогается(self):
        неизменная = make_problem(statement='Условие А. Оно не меняется.')
        call_command('build_embeddings', reset=True, verbosity=0)
        время_до = Problem.objects.get(id=неизменная.id).embedding_built_at

        call_command('build_embeddings', stale=True, verbosity=0)

        время_после = Problem.objects.get(id=неизменная.id).embedding_built_at
        self.assertEqual(время_до, время_после)


class IsStaleUnitTests(TestCase):
    """`is_stale` как чистая функция — без базы и без команды."""

    def test_легаси_запись_без_версии_считается_устаревшей(self):
        problem = make_problem(statement='Что угодно.')
        # embedding_version/model_build/source_hash по умолчанию NULL/'' —
        # ровно состояние «посчитан до С5».
        self.assertIsNone(problem.embedding_version)
        self.assertTrue(is_stale(problem, problem_to_text(problem)))

    def test_совпадающая_версия_и_хеш_не_устарели(self):
        problem = make_problem(statement='Текст без изменений.')
        text = problem_to_text(problem)
        problem.embedding_version = EMBEDDING_FORMULA_VERSION
        problem.embedding_model_build = EMBEDDING_MODEL_BUILD
        problem.embedding_source_hash = embedding_source_hash(text)
        self.assertFalse(is_stale(problem, text))

    def test_смена_версии_формулы_делает_устаревшим_даже_без_правки_текста(self):
        """Подняли EMBEDDING_FORMULA_VERSION — старо ВСЁ, текст не менялся."""
        problem = make_problem(statement='Текст без изменений.')
        text = problem_to_text(problem)
        problem.embedding_version = EMBEDDING_FORMULA_VERSION - 1
        problem.embedding_model_build = EMBEDDING_MODEL_BUILD
        problem.embedding_source_hash = embedding_source_hash(text)
        self.assertTrue(is_stale(problem, text))

    def test_смена_сборки_модели_делает_устаревшим(self):
        problem = make_problem(statement='Текст без изменений.')
        text = problem_to_text(problem)
        problem.embedding_version = EMBEDDING_FORMULA_VERSION
        problem.embedding_model_build = 'другая-сборка'
        problem.embedding_source_hash = embedding_source_hash(text)
        self.assertTrue(is_stale(problem, text))
