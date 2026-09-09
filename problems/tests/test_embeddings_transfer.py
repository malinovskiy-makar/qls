# -*- coding: utf-8 -*-
"""Вывоз текстов → ввоз векторов → офлайн-замер. Без сети и без модели.

Смысл всей конструкции: база на арендованную видеокарту НЕ ЕДЕТ. Туда едут
тексты отпечатка, обратно — векторы, а замер семнадцати вариантов идёт по
файлам, и в банк въезжает ровно один победитель. Значит проверять надо не
«команда не падает», а четыре вещи, каждая из которых при поломке стоит
целой аренды:

* круговой прогон: экспорт → подставные векторы → импорт → в базе ровно те
  векторы, провенанс проставлен, защищённые поля не тронуты;
* импорт ОТКАЗЫВАЕТСЯ при чужой спецификации, неверной размерности,
  разошедшемся хеше и непройденной сверке билда;
* гейт допрогона на входе экспорта;
* `search_eval --vectors` даёт те же числа, что и по базе, если файл
  содержит те же векторы.
"""
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.embedding_config import (
    ACTIVE_SPEC_NAME, EMBEDDING_DIM, EMBEDDING_FORMULA_VERSION,
    EMBEDDING_MODEL_BUILD,
)
from problems.embedding_provenance import protected_fingerprint
from problems.management.commands import embeddings_import_vectors as imp
from problems.management.commands.embeddings_check_build import compare_versions
from problems.models import Problem

ПИНЫ = {'sentence_transformers': '5.1.2', 'transformers': '4.57.6',
        'tokenizers': '0.22.2', 'torch': '2.13.0'}


def случайные_векторы(n, seed=0):
    rng = np.random.default_rng(seed)
    m = rng.standard_normal((n, EMBEDDING_DIM)).astype(np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


class ЭкспортИмпортTestCase(TestCase):
    """Общая обвязка: банк из нескольких задач и каталог для файлов."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.problems = [
            Problem.objects.create(
                statement='Задача %d про конкурентный рынок кофе.' % i,
                title='Заголовок %d' % i, content_status='ok',
                enrichment_source='run2')
            for i in range(6)
        ]
        self.texts = self.tmp / 'texts.jsonl'
        self.state = self.tmp / 'STATE.json'

    def экспорт(self, spec='v1', scope='all', **kwargs):
        buf = StringIO()
        call_command('embeddings_export_texts', spec=spec, out=str(self.texts),
                     scope=scope, stdout=buf, **kwargs)
        строки = [json.loads(s) for s in
                  self.texts.read_text(encoding='utf-8').strip().splitlines()]
        return строки[0], строки[1:], buf.getvalue()

    def привезти(self, шапка, строки, prefix='vec', *, spec=None, version=None,
                 vectors=None, dim=EMBEDDING_DIM, versions=None, sample=False):
        """Подставные «привезённые с видеокарты» файлы."""
        путь = self.tmp / prefix
        m = случайные_векторы(len(строки)) if vectors is None else vectors
        if dim != EMBEDDING_DIM:
            m = m[:, :dim]
        путь.with_suffix('.f32').write_bytes(
            np.asarray(m, dtype=np.float32).tobytes(order='C'))
        мета = {
            'kind': 'embedding_vectors',
            'spec': spec or шапка['spec'],
            'version': шапка['version'] if version is None else version,
            'source_kind': шапка['kind'],
            'model_name': шапка['model_name'],
            'model_build': шапка['model_build'],
            'max_seq_length': шапка['max_seq_length'],
            'device': 'cuda', 'dtype': 'float32', 'dim': dim,
            'rows': len(строки), 'sample': sample,
            'ids': [с['id'] for с in строки],
            'hashes': [с['hash'] for с in строки],
            'versions': versions or dict(ПИНЫ, python='3.13.0'),
        }
        путь.with_suffix('.meta.json').write_text(
            json.dumps(мета, ensure_ascii=False), encoding='utf-8')
        return str(путь), m

    def сверка_пройдена(self, spec='v1'):
        self.state.write_text(json.dumps({
            'build_check_passed': True,
            'build_check': {'spec': spec, 'min_cosine': 0.99999,
                            'median_cosine': 0.999999},
        }), encoding='utf-8')

    def импорт(self, prefix, **kwargs):
        buf = StringIO()
        call_command('embeddings_import_vectors', vectors=prefix,
                     state=str(self.state), stdout=buf, **kwargs)
        return buf.getvalue()


class ExportGateTests(ЭкспортИмпортTestCase):
    """⚠️ Гейт допрогона — механический, а не «не забудь». Порядок фаз не
    гарантирует, что векторы считаются по банку ПОСЛЕ допрогона; гарантирует
    проверка."""

    def test_гейт_не_пускает_пока_есть_остатки_run1(self):
        self.problems[0].enrichment_source = 'run1'
        self.problems[0].content_status = 'needs_fix'
        self.problems[0].save()
        with self.assertRaises(CommandError) as ctx:
            self.экспорт()
        self.assertIn('ГЕЙТ ДОПРОГОНА', str(ctx.exception))
        self.assertFalse(self.texts.exists())

    def test_задачи_junk_с_меткой_run1_гейт_не_держат(self):
        """У 1 343 задач-junk метка `run1` остаётся законно: в манифест
        допрогона они не входили."""
        self.problems[0].enrichment_source = 'run1'
        self.problems[0].content_status = 'junk'
        self.problems[0].save()
        шапка, строки, _ = self.экспорт()
        self.assertEqual(len(строки), 6)
        self.assertEqual(шапка['run1_leftovers'], 0)

    def test_флаг_снимает_гейт_осознанно(self):
        self.problems[0].enrichment_source = 'run1'
        self.problems[0].save()
        шапка, строки, _ = self.экспорт(allow_run1_leftovers=True)
        self.assertEqual(шапка['run1_leftovers'], 1)


class ExportShapeTests(ЭкспортИмпортTestCase):

    def test_шапка_описывает_на_каком_состоянии_банка_собран_файл(self):
        шапка, строки, _ = self.экспорт(spec='v2')
        self.assertEqual(шапка['spec'], 'v2')
        self.assertEqual(шапка['version'], 2)
        self.assertEqual(шапка['rows'], 6)
        self.assertEqual(len(строки), 6)
        self.assertEqual(шапка['enrichment_source'], {'run2': 6})
        self.assertIn('max_seq_length', шапка)
        self.assertIn('blocks', шапка)

    def test_порядок_строк_по_id_и_это_контракт(self):
        """Порядок строк файла — порядок строк матрицы, привезённой обратно.
        Разойдётся — векторы молча достанутся чужим задачам."""
        _шапка, строки, _ = self.экспорт()
        self.assertEqual([с['id'] for с in строки],
                         sorted(p.id for p in self.problems))

    def test_срез_prod_уже_среза_all(self):
        Problem.objects.filter(pk=self.problems[0].pk).update(
            status=Problem.Status.PUBLISHED)
        _ш, все, _ = self.экспорт(scope='all')
        _ш2, прод, _ = self.экспорт(scope='prod')
        self.assertEqual(len(все), 6)
        self.assertEqual(len(прод), 1)

    def test_команда_не_меняет_банк(self):
        до = protected_fingerprint(Problem.objects.all())
        self.экспорт(spec='v2')
        self.assertEqual(до, protected_fingerprint(Problem.objects.all()))


class RoundTripTests(ЭкспортИмпортTestCase):
    """Круговой прогон: экспорт → подставные векторы → импорт."""

    def test_векторы_доезжают_до_тех_же_задач_с_провенансом(self):
        шапка, строки, _ = self.экспорт()
        prefix, m = self.привезти(шапка, строки)
        self.сверка_пройдена()
        до = protected_fingerprint(Problem.objects.exclude(pk=None)
                                   .only('pk'))  # свип по всем полям ниже

        вывод = self.импорт(prefix, apply=True)

        self.assertIn('Записано 6 векторов', вывод)
        for i, с in enumerate(строки):
            p = Problem.objects.get(pk=с['id'])
            np.testing.assert_allclose(
                np.frombuffer(bytes(p.embedding), dtype=np.float32), m[i],
                rtol=0, atol=0)
            self.assertEqual(p.embedding_version, шапка['version'])
            self.assertEqual(p.embedding_model_build, EMBEDDING_MODEL_BUILD)
            self.assertEqual(p.embedding_source_hash, с['hash'])
            self.assertIsNotNone(p.embedding_built_at)
        self.assertTrue(до)     # отпечаток посчитался — свип отработал внутри

    def test_без_apply_ничего_не_пишется(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки)
        self.сверка_пройдена()
        вывод = self.импорт(prefix)
        self.assertIn('Это план', вывод)
        self.assertFalse(Problem.objects.exclude(embedding=None).exists())

    def test_защищённые_поля_не_тронуты(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки)
        self.сверка_пройдена()
        # `embedding` входит в PROTECTED_FIELDS, поэтому сравниваем отпечаток
        # по текстам, а не по всему набору: ввоз векторов ИМЕННО их и меняет.
        тексты = lambda: list(Problem.objects.order_by('pk').values_list(  # noqa: E731
            'statement', 'solution', 'answer', 'title'))
        до = тексты()
        self.импорт(prefix, apply=True)
        self.assertEqual(до, тексты())


class ImportRefusalTests(ЭкспортИмпортTestCase):
    """Ввоз — единственный шаг, который пишет в банк. Отказов здесь больше,
    чем во всех остальных командах вместе, и каждый оплачен."""

    def test_чужая_спецификация_отказ(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки, spec='v2_focus')
        self.сверка_пройдена()
        with self.assertRaises(CommandError) as ctx:
            self.импорт(prefix, apply=True)
        self.assertIn('спецификации', str(ctx.exception))

    def test_чужая_версия_формулы_отказ(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки, version=777)
        self.сверка_пройдена()
        with self.assertRaises(CommandError) as ctx:
            self.импорт(prefix, apply=True)
        self.assertIn('Версия формулы', str(ctx.exception))

    def test_неверная_размерность_отказ(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки, dim=512)
        self.сверка_пройдена()
        with self.assertRaises(CommandError):
            self.импорт(prefix, apply=True)

    def test_разошедшийся_хеш_пропускает_задачу_и_говорит_об_этом(self):
        """Поля правились после вывоза — вектор такой задаче уже не
        соответствует, и ставить его значило бы соврать в провенансе."""
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки)
        self.сверка_пройдена()
        чужой = self.problems[0]
        Problem.objects.filter(pk=чужой.pk).update(title='Другой заголовок')

        вывод = self.импорт(prefix, apply=True)

        self.assertIn('Записано 5 векторов', вывод)
        self.assertIn('текст изменился после вывоза: 1', вывод)
        self.assertIsNone(Problem.objects.get(pk=чужой.pk).embedding)

    def test_без_пройденной_сверки_билда_отказ(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки)
        with self.assertRaises(CommandError) as ctx:
            self.импорт(prefix, apply=True)
        self.assertIn('сверка билда', str(ctx.exception).lower())

    def test_сверка_на_другой_спецификации_не_считается(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки)
        self.сверка_пройдена(spec='v2_focus')
        with self.assertRaises(CommandError) as ctx:
            self.импорт(prefix, apply=True)
        self.assertIn('Пройдите сверку', str(ctx.exception))

    def test_файл_выборки_ввозить_нельзя(self):
        """`gpu_encode --sample 200` — сверка билда, а не прогон. Ввезти его
        значило бы стереть векторы у всех остальных задач."""
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки[:2], sample=True)
        self.сверка_пройдена()
        with self.assertRaises(CommandError) as ctx:
            self.импорт(prefix, apply=True)
        self.assertIn('ВЫБОРКИ', str(ctx.exception))

    def test_нулевые_векторы_это_мусор_а_не_данные(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(
            шапка, строки, vectors=np.zeros((len(строки), EMBEDDING_DIM),
                                            dtype=np.float32))
        self.сверка_пройдена()
        with self.assertRaises(CommandError) as ctx:
            self.импорт(prefix, apply=True)
        self.assertIn('норма', str(ctx.exception))

    def test_nan_в_файле_отказ(self):
        шапка, строки, _ = self.экспорт()
        m = случайные_векторы(len(строки))
        m[2][0] = np.nan
        prefix, _m = self.привезти(шапка, строки, vectors=m)
        self.сверка_пройдена()
        with self.assertRaises(CommandError) as ctx:
            self.импорт(prefix, apply=True)
        self.assertIn('NaN', str(ctx.exception))


class CompareVersionsTests(TestCase):
    """Токенизация и пулинг живут в библиотеке, а не в весах модели: мажорный
    подъём сдвинет векторы, и ни одна проверка этого не покажет."""

    def test_совпадение_молчит(self):
        отказы, замечания = compare_versions(dict(ПИНЫ), ПИНЫ)
        self.assertEqual(отказы, [])
        self.assertEqual(замечания, [])

    def test_суффикс_cuda_сборки_допустим_но_в_отчёт(self):
        """На арендованной машине CUDA-колесо, дома CPU-колесо. Веса и
        токенизация те же — это ожидаемо, но молчать об этом нельзя."""
        отказы, замечания = compare_versions(
            dict(ПИНЫ, torch='2.13.0+cu121'), ПИНЫ)
        self.assertEqual(отказы, [])
        self.assertEqual(len(замечания), 1)
        self.assertIn('суффикс сборки', замечания[0])

    def test_мажорное_расхождение_отказ(self):
        отказы, _зам = compare_versions(dict(ПИНЫ, transformers='5.0.0'), ПИНЫ)
        self.assertEqual(len(отказы), 1)
        self.assertIn('мажорное', отказы[0])

    def test_минорное_расхождение_в_отчёт_но_не_отказ(self):
        отказы, замечания = compare_versions(
            dict(ПИНЫ, tokenizers='0.22.9'), ПИНЫ)
        self.assertEqual(отказы, [])
        self.assertIn('минорное', замечания[0])


class SearchEvalVectorsTests(ЭкспортИмпортTestCase):
    """`search_eval --vectors` обязан дать те же числа, что и по базе, если
    в файле те же векторы. Иначе офлайн-замер меряет не то, что банк."""

    def setUp(self):
        super().setUp()
        self.m = случайные_векторы(len(self.problems), seed=7)
        for вектор, задача in zip(self.m, self.problems):
            Problem.objects.filter(pk=задача.pk).update(
                embedding=вектор.tobytes(order='C'),
                status=Problem.Status.PUBLISHED,
                needs_quality_review=False, hidden_pending_review=False,
                content_status='ok')
        набор = {
            'name': 'тест', 'mode': 'text',
            'cases': [{'query': 'конкурентный рынок кофе',
                       'relevant_ids': [self.problems[0].id],
                       'hard_negative_ids': None}],
        }
        self.набор = self.tmp / 'set.json'
        self.набор.write_text(json.dumps(набор, ensure_ascii=False),
                              encoding='utf-8')

    def _замер(self, **kwargs):
        from problems.management.commands import search_eval as se
        буфер = StringIO()
        вектор_запроса = self.m[0]

        def кодировщик():
            return lambda тексты: np.stack([вектор_запроса] * len(list(тексты)))

        отчёт = self.tmp / ('%s.json' % (kwargs.get('vectors') or 'db')).replace(
            str(self.tmp) + '\\', '')
        with mock.patch.object(se, '_кодировщик_модели', кодировщик):
            call_command('search_eval', set=str(self.набор), scope='all',
                         out=str(отчёт), stdout=буфер, **kwargs)
        return json.loads(отчёт.read_text(encoding='utf-8'))

    def test_числа_из_файла_совпадают_с_числами_из_базы(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки, vectors=self.m)
        по_базе = self._замер()
        по_файлу = self._замер(vectors=prefix)
        for k in ('recall', 'mrr_10', 'ndcg_10', 'index_size'):
            self.assertEqual(по_базе['slices']['all'][k],
                             по_файлу['slices']['all'][k], k)

    def test_задачи_вне_файла_считаются_как_нет_в_индексе(self):
        """Состав индекса определяет `index_queryset`, а не файл: своего
        фильтра у измерителя нет намеренно."""
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки[:3], vectors=self.m[:3])
        отчёт = self._замер(vectors=prefix)
        self.assertEqual(отчёт['slices']['all']['index_size'], 3)

    def test_замер_по_файлу_не_трогает_банк(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки, vectors=self.m)
        до = protected_fingerprint(Problem.objects.all())
        self._замер(vectors=prefix)
        self.assertEqual(до, protected_fingerprint(Problem.objects.all()))

    def test_векторы_запросов_из_файла_дают_тот_же_ответ(self):
        """⚠️ Ради этого пути всё и затевалось: корпус и запрос кодируются
        одним билдом, на одной машине, одним прогоном."""
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки, vectors=self.m)
        q_prefix = self.tmp / 'q'
        q_prefix.with_suffix('.f32').write_bytes(
            np.asarray([self.m[0]], dtype=np.float32).tobytes(order='C'))
        q_prefix.with_suffix('.meta.json').write_text(json.dumps({
            'kind': 'embedding_vectors', 'source_kind': 'embedding_queries',
            'spec': шапка['spec'], 'version': шапка['version'],
            'rows': 1, 'ids': [0], 'hashes': [строки[0]['hash']],
            'dtype': 'float32', 'max_seq_length': шапка['max_seq_length'],
            'versions': dict(ПИНЫ, python='3.13.0'),
        }), encoding='utf-8')

        по_модели = self._замер(vectors=prefix)
        по_файлу = self._замер(vectors=prefix, query_vectors=str(q_prefix))
        self.assertEqual(по_модели['slices']['all']['recall'],
                         по_файлу['slices']['all']['recall'])

    def test_разные_версии_библиотек_у_корпуса_и_запросов_отказ(self):
        шапка, строки, _ = self.экспорт()
        prefix, _m = self.привезти(шапка, строки, vectors=self.m)
        q_prefix = self.tmp / 'q_bad'
        q_prefix.with_suffix('.f32').write_bytes(
            np.asarray([self.m[0]], dtype=np.float32).tobytes(order='C'))
        q_prefix.with_suffix('.meta.json').write_text(json.dumps({
            'kind': 'embedding_vectors', 'source_kind': 'embedding_queries',
            'spec': шапка['spec'], 'version': шапка['version'],
            'rows': 1, 'ids': [0], 'hashes': [строки[0]['hash']],
            'dtype': 'float32', 'max_seq_length': шапка['max_seq_length'],
            'versions': dict(ПИНЫ, transformers='9.9.9'),
        }), encoding='utf-8')
        with self.assertRaises(CommandError) as ctx:
            self._замер(vectors=prefix, query_vectors=str(q_prefix))
        self.assertIn('ОДНИМ билдом', str(ctx.exception))


class ActiveSpecVersionTests(ЭкспортИмпортTestCase):
    """Сессия перехода на v2_focus_repeat (09.09.2026): активная
    спецификация — версия 95, и ввоз проставляет её всем задачам."""

    def test_активная_спецификация_версии_95(self):
        self.assertEqual(ACTIVE_SPEC_NAME, 'v2_focus_repeat')
        self.assertEqual(EMBEDDING_FORMULA_VERSION, 95)

    def test_ввоз_проставляет_версию_95_у_всех(self):
        шапка, строки, _ = self.экспорт(spec=ACTIVE_SPEC_NAME)
        prefix, _m = self.привезти(шапка, строки)
        self.сверка_пройдена(spec=ACTIVE_SPEC_NAME)
        self.импорт(prefix, apply=True)
        versions = set(Problem.objects.exclude(embedding=None)
                       .values_list('embedding_version', flat=True))
        self.assertEqual(versions, {95})


class ImportModuleTests(TestCase):

    def test_норма_вектора_проверяется_широким_допуском(self):
        """Ловим не «чуть-чуть не единица», а мусор: нулевой или
        разошедшийся вектор."""
        self.assertLess(imp.NORM_MIN, 1.0)
        self.assertGreater(imp.NORM_MAX, 1.0)
