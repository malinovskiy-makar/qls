# -*- coding: utf-8 -*-
"""`embeddings_import_vectors --ignore-text-check` — временный ввоз 16.09.

Боевой банк отстал от домашнего с 13.09 (нет тем/тегов/обогащения у ~3 000
задач), поэтому отпечаток текста у большинства строк файла расходится с
боевым текстом. Векторы посчитаны по более богатым ДОМАШНИМ текстам тех же
задач — ключ пускает их в запись, не отвергая как «текст изменился».

Без ключа поведение прежнее ни в одной ветке — эти тесты его тоже проверяют,
не только новую.
"""
import io
import json
import os
import tempfile

import numpy as np
from django.core.management import call_command
from django.test import TestCase

from problems.embedding_config import ACTIVE_SPEC, EMBEDDING_DIM, EMBEDDING_MODEL_BUILD
from problems.embedding_formula import PREFETCH, build_text
from problems.management.commands.embeddings_export_texts import text_hash
from problems.models import Problem
from problems.tests.factories import make_problem

TEXTS = ('Спрос задан функцией Q = 10 - P. Найдите равновесие.',
         'Монополист с издержками TC = Q^2 выбирает выпуск.')


def unit_vector(seed):
    vector = np.random.default_rng(seed).standard_normal(EMBEDDING_DIM)
    return (vector / np.linalg.norm(vector)).astype(np.float32)


class IgnoreTextCheckTests(TestCase):
    """Фикстура: 2 задачи, файл векторов через `embeddings_export_vectors`,
    затем у одной задачи меняем `statement`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = os.path.join(tmp.name, 'vec')
        self.state = os.path.join(tmp.name, 'STATE.json')
        with open(self.state, 'w', encoding='utf-8') as handle:
            json.dump({'build_check_passed': True,
                       'build_check': {'spec': ACTIVE_SPEC.name,
                                       'version': ACTIVE_SPEC.version}}, handle)

        self.ids = []
        self.original_hashes = {}
        for seed, text in enumerate(TEXTS):
            pk = make_problem(text).pk
            problem = Problem.objects.prefetch_related(*PREFETCH).get(pk=pk)
            digest = text_hash(build_text(problem, ACTIVE_SPEC))
            Problem.objects.filter(pk=pk).update(
                embedding=unit_vector(seed).tobytes(order='C'),
                embedding_version=ACTIVE_SPEC.version,
                embedding_model_build=EMBEDDING_MODEL_BUILD,
                embedding_source_hash=digest)
            self.ids.append(pk)
            self.original_hashes[pk] = digest

        call_command('embeddings_export_vectors', out=self.out, all=True,
                     state=self.state, stdout=io.StringIO())

        # Векторы уже на диске — стираем их в базе, как на машине, куда
        # ввозим: там их не было вовсе.
        Problem.objects.filter(pk__in=self.ids).update(
            embedding=None, embedding_source_hash='')

        # Домашний текст задачи 1 «убежал вперёд» боевого — ровно тот
        # сценарий 16.09, ради которого заводится ключ.
        self.changed_id = self.ids[1]
        Problem.objects.filter(pk=self.changed_id).update(
            statement='Изменённое условие задачи после вывоза векторов.')

    def _import(self, **options):
        buf = io.StringIO()
        call_command('embeddings_import_vectors', vectors=self.out,
                     state=self.out + '.state.json', stdout=buf, **options)
        return buf.getvalue()

    # ── без ключа: поведение прежнее ────────────────────────────────────

    def test_without_flag_plan_reports_one_written_one_diverged(self):
        output = self._import()
        self.assertIn('к записи: 1', output)
        self.assertIn('текст изменился после вывоза: 1', output)
        self.assertIn(str(self.changed_id), output)
        self.assertNotIn('ВНИМАНИЕ', output)

    def test_without_flag_apply_writes_only_unchanged(self):
        self._import(apply=True)
        unchanged_id = self.ids[0]

        unchanged = Problem.objects.get(pk=unchanged_id)
        self.assertIsNotNone(unchanged.embedding)
        self.assertEqual(unchanged.embedding_source_hash,
                         self.original_hashes[unchanged_id])

        changed = Problem.objects.get(pk=self.changed_id)
        self.assertIsNone(changed.embedding)
        self.assertEqual(changed.embedding_source_hash, '')

    # ── с ключом --ignore-text-check ────────────────────────────────────

    def test_with_flag_plan_reports_both_written_and_warns(self):
        output = self._import(ignore_text_check=True)
        self.assertIn('к записи: 2', output)
        self.assertIn('текст изменился после вывоза: 0', output)
        self.assertIn('разошлись, но записаны по ключу: 1', output)
        self.assertIn(str(self.changed_id), output)
        self.assertIn('ВНИМАНИЕ', output)
        self.assertIn('без ключа', output)

    def test_with_flag_apply_writes_both_with_hash_from_file(self):
        self._import(ignore_text_check=True, apply=True)

        changed = Problem.objects.get(pk=self.changed_id)
        self.assertIsNotNone(changed.embedding)
        # Хеш ИЗ ФАЙЛА (по домашнему тексту), не пересчитанный по сегодняшним
        # (уже изменённым) полям — иначе провенанс соврал бы о том, каким
        # текстом посчитан вектор.
        self.assertEqual(changed.embedding_source_hash,
                         self.original_hashes[self.changed_id])
        changed_problem = Problem.objects.prefetch_related(*PREFETCH).get(
            pk=self.changed_id)
        self.assertNotEqual(
            changed.embedding_source_hash,
            text_hash(build_text(changed_problem, ACTIVE_SPEC)))

        unchanged = Problem.objects.get(pk=self.ids[0])
        self.assertIsNotNone(unchanged.embedding)
