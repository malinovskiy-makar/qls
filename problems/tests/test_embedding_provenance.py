# -*- coding: utf-8 -*-
"""Провенанс эмбеддингов (С13): легаси-backfill и защита текстов задач.

Три роли сторожатся здесь по отдельности.

1. **Отпечаток защищённых полей.** Сессия С13 имеет право писать только в
   четыре учётных поля. Отпечаток обязан ловить правку текста и обязан НЕ
   реагировать на запись учётных полей — иначе он либо бесполезен, либо
   краснеет на законной работе.
2. **Честность легаси-значений.** У старых векторов нет исторического хеша
   текста. Записать туда хеш ТЕКУЩЕГО текста — соврать в сторону «вектор
   актуален» ровно для тех задач, которые после пересчёта правили.
3. **Разбор журнала применения.** Журнал АА адресует правки к двум таблицам,
   и id подпункта нельзя путать с id задачи.
"""
import json
from datetime import datetime, timezone as dt_timezone

from django.test import SimpleTestCase, TestCase

from problems import embedding_provenance as prov
from problems.models import Problem, ProblemPart


class ProtectedFingerprintTests(TestCase):
    """Отпечаток защищённых полей: что он обязан ловить и что пропускать."""

    def setUp(self):
        self.problem = Problem.objects.create(
            title='Монополия', statement='Спрос P = 100 - Q.',
            answer='Q = 25', solution='MR = MC',
        )

    def test_отпечаток_меняется_при_правке_statement(self):
        """Без этого свип-тест Фазы 0 не поймал бы порчу текста.

        Отпечаток — единственное, что стоит между сессией и молчаливой
        правкой условия: если он слеп к statement, проверка «до/после»
        превращается в ритуал.
        """
        before = prov.protected_fingerprint(Problem.objects.all())
        Problem.objects.filter(pk=self.problem.pk).update(statement='Другое условие')
        self.assertNotEqual(before, prov.protected_fingerprint(Problem.objects.all()))

    def test_отпечаток_не_меняется_при_записи_учётных_полей(self):
        """Законная работа Фазы 0 не имеет права краснить свип-тест."""
        before = prov.protected_fingerprint(Problem.objects.all())
        Problem.objects.filter(pk=self.problem.pk).update(
            embedding_version=0,
            embedding_model_build='bge-m3/st-fp32',
            embedding_built_at=prov.LEGACY_BUILT_AT,
        )
        self.assertEqual(before, prov.protected_fingerprint(Problem.objects.all()))

    def test_отпечаток_ловит_правку_embedding(self):
        """Вектор тоже защищён: эта сессия не пересчитывает эмбеддинги."""
        before = prov.protected_fingerprint(Problem.objects.all())
        Problem.objects.filter(pk=self.problem.pk).update(embedding=b'\x00' * 8)
        self.assertNotEqual(before, prov.protected_fingerprint(Problem.objects.all()))

    def test_отпечаток_переживает_bytes_и_memoryview(self):
        """BinaryField отдаёт memoryview, а не bytes — прямой hash() падал бы.

        Ловушка описана в docs/EMBEDDINGS.md и уже стреляла в этом проекте.
        """
        Problem.objects.filter(pk=self.problem.pk).update(embedding=b'\x01\x02\x03')
        first = prov.protected_fingerprint(Problem.objects.all())
        second = prov.protected_fingerprint(Problem.objects.all())
        self.assertEqual(first, second)


class LegacyValuesTests(SimpleTestCase):
    """Какие значения честно записать легаси-вектору."""

    def test_задача_с_вектором_получает_дату_и_сборку(self):
        values = prov.legacy_values(has_embedding=True)
        self.assertEqual(values['embedding_built_at'], prov.LEGACY_BUILT_AT)
        self.assertEqual(values['embedding_model_build'], prov.LEGACY_MODEL_BUILD)
        self.assertEqual(values['embedding_version'], prov.LEGACY_FORMULA_VERSION)

    def test_хеш_текста_остаётся_пустым(self):
        """Главная защита от лжи в противоположную сторону.

        Хеш ТЕКУЩЕГО текста сказал бы «вектор актуален» ровно про те задачи,
        чей текст правили ПОСЛЕ пересчёта (aa_fixed, МатЭк) — то есть про
        те самые, ради которых диагностика и затевалась.
        """
        self.assertEqual(prov.legacy_values(has_embedding=True)['embedding_source_hash'], '')

    def test_задача_без_вектора_получает_все_четыре_пустыми(self):
        values = prov.legacy_values(has_embedding=False)
        self.assertIsNone(values['embedding_version'])
        self.assertIsNone(values['embedding_built_at'])
        self.assertEqual(values['embedding_model_build'], '')
        self.assertEqual(values['embedding_source_hash'], '')

    def test_легаси_версия_не_совпадает_с_боевой(self):
        """Легаси-метка обязана оставлять вектор устаревшим.

        Если бы она совпала с EMBEDDING_FORMULA_VERSION, backfill объявил бы
        31 694 неизвестных вектора актуальными одним движением.
        """
        from problems.embedding_config import EMBEDDING_FORMULA_VERSION

        self.assertNotEqual(prov.LEGACY_FORMULA_VERSION, EMBEDDING_FORMULA_VERSION)


class LegacyStalenessTests(TestCase):
    """После backfill вектор обязан остаться устаревшим."""

    def test_легаси_запись_считается_устаревшей(self):
        from problems.management.commands.build_embeddings import is_stale, problem_to_text

        problem = Problem.objects.create(statement='Условие', embedding=b'\x00' * 4)
        Problem.objects.filter(pk=problem.pk).update(**prov.legacy_values(has_embedding=True))
        problem.refresh_from_db()
        self.assertTrue(is_stale(problem, problem_to_text(problem)))


class ApplyLogTests(SimpleTestCase):
    """Разбор журнала применения: две таблицы, id подпункта — не id задачи."""

    LOG = [
        {'table': 'problems_problem', 'id': '5475', 'field': 'statement',
         'part_label': '', 'old': 'a', 'new': 'b'},
        {'table': 'problems_problempart', 'id': '76278', 'problem_id': '5648',
         'field': 'statement', 'part_label': 'а)', 'old': 'c', 'new': 'd'},
        {'table': 'problems_problempart', 'id': '76279', 'problem_id': '5648',
         'field': 'statement', 'part_label': 'б)', 'old': 'e', 'new': 'f'},
    ]

    def test_id_подпункта_не_считается_id_задачи(self):
        """76278 — это ProblemPart.pk. Считать его задачей — завысить охват.

        Наивный разбор по полю `id` даёт 3 «задачи» вместо 2 и приписывает
        правку задаче #76278, которой в журнале нет вовсе.
        """
        self.assertEqual(prov.apply_log_problem_ids(self.LOG), {5475, 5648})

    def test_правки_одной_задачи_не_считаются_дважды(self):
        self.assertEqual(len(prov.apply_log_problem_ids(self.LOG)), 2)


class StaleIntersectionTests(SimpleTestCase):
    """Пересечение множеств: что считать устаревшим ретроспективно."""

    JULY = datetime(2026, 7, 4, tzinfo=dt_timezone.utc)
    AUGUST = datetime(2026, 8, 27, tzinfo=dt_timezone.utc)

    def test_правка_после_пересчёта_делает_вектор_устаревшим(self):
        self.assertTrue(prov.stale_after(edited_at=self.AUGUST, built_at=self.JULY))

    def test_правка_до_пересчёта_вектор_не_трогает(self):
        self.assertFalse(prov.stale_after(edited_at=self.JULY, built_at=self.AUGUST))

    def test_без_вектора_устаревания_нет(self):
        """Нет вектора — это отдельная категория, а не «устарел».

        Смешать их значило бы предложить владельцу пересчитать то, чего
        никогда не считали, под видом починки.
        """
        self.assertFalse(prov.stale_after(edited_at=self.AUGUST, built_at=None))
