# -*- coding: utf-8 -*-
"""Вывоз готовых векторов файлом (`embeddings_export_vectors`) и ввоз обратно.

Круговой обмен (15.09.2026): три задачи с векторами → вывоз → векторы в базе
стёрты → `embeddings_import_vectors` с отметкой сверки из вывоза → векторы
побайтно те же, хеш формулы совпадает с пересчитанным по полям задачи.

⚠️ Спецификация — всегда АКТИВНАЯ (`ACTIVE_SPEC`), не зашитая строкой: три
модуля, зашитые на `v1`, краснеют с 09.09 при любой другой.
"""
import io
import json
import os
import tempfile

import numpy as np
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.embedding_config import (
    ACTIVE_SPEC, EMBEDDING_DIM, EMBEDDING_MODEL_BUILD,
)
from problems.embedding_formula import PREFETCH, build_text
from problems.management.commands.embeddings_export_texts import text_hash
from problems.models import Problem
from problems.tests.factories import make_problem

TEXTS = ('Спрос задан функцией Q = 10 - P. Найдите равновесие.',
         'Монополист с издержками TC = Q^2 выбирает выпуск.',
         'Государство вводит потоварный налог на продавцов.')


def unit_vector(seed):
    vector = np.random.default_rng(seed).standard_normal(EMBEDDING_DIM)
    return (vector / np.linalg.norm(vector)).astype(np.float32)


class ExportVectorsTests(TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = os.path.join(tmp.name, 'vec')
        self.state = os.path.join(tmp.name, 'STATE.json')
        self._write_state(True, ACTIVE_SPEC.name)
        self.ids = []
        for seed, text in enumerate(TEXTS):
            pk = make_problem(text).pk
            problem = Problem.objects.prefetch_related(*PREFETCH).get(pk=pk)
            Problem.objects.filter(pk=pk).update(
                embedding=unit_vector(seed).tobytes(order='C'),
                embedding_version=ACTIVE_SPEC.version,
                embedding_model_build=EMBEDDING_MODEL_BUILD,
                embedding_source_hash=text_hash(build_text(problem, ACTIVE_SPEC)))
            self.ids.append(pk)

    def _write_state(self, passed, spec_name):
        with open(self.state, 'w', encoding='utf-8') as handle:
            json.dump({'build_check_passed': passed,
                       'build_check': {'spec': spec_name,
                                       'version': ACTIVE_SPEC.version}}, handle)

    def _export(self, **options):
        call_command('embeddings_export_vectors', out=self.out, state=self.state,
                     stdout=io.StringIO(), **options)

    def _meta(self):
        with open(self.out + '.meta.json', encoding='utf-8') as handle:
            return json.load(handle)

    def _vectors(self):
        return {pk: bytes(blob) for pk, blob in Problem.objects
                .filter(pk__in=self.ids).values_list('pk', 'embedding')}

    def test_round_trip_through_import_is_byte_exact(self):
        before = self._vectors()
        self._export(all=True)
        Problem.objects.filter(pk__in=self.ids).update(
            embedding=None, embedding_source_hash='')

        call_command('embeddings_import_vectors', vectors=self.out,
                     state=self.out + '.state.json', apply=True,
                     stdout=io.StringIO())

        self.assertEqual(self._vectors(), before)
        for problem in (Problem.objects.filter(pk__in=self.ids)
                        .prefetch_related(*PREFETCH)):
            self.assertEqual(problem.embedding_source_hash,
                             text_hash(build_text(problem, ACTIVE_SPEC)))

    def test_default_scope_is_the_visible_catalog(self):
        Problem.objects.filter(pk=self.ids[0]).update(hidden_pending_review=True)
        self._export()
        meta = self._meta()
        self.assertEqual(meta['scope'], 'catalog')
        self.assertEqual(meta['ids'], self.ids[1:])
        self.assertEqual(os.path.getsize(self.out + '.f32'), 2 * EMBEDDING_DIM * 4)

    def test_vectors_of_another_formula_stay_home(self):
        Problem.objects.filter(pk=self.ids[0]).update(
            embedding_version=ACTIVE_SPEC.version + 1)
        self._export(all=True)
        self.assertEqual(self._meta()['ids'], self.ids[1:])

    def test_refuses_without_a_passed_build_check(self):
        self._write_state(False, ACTIVE_SPEC.name)
        with self.assertRaises(CommandError):
            self._export(all=True)
        self._write_state(True, 'другая_спецификация')
        with self.assertRaises(CommandError):
            self._export(all=True)
        self.assertFalse(os.path.exists(self.out + '.f32'))
