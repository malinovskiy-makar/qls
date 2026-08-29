# -*- coding: utf-8 -*-
"""С14 — команда `search_eval` целиком, на синтетической базе.

Векторы здесь выставлены руками, поэтому правильный ответ известен заранее и
проверяется не «похоже на правду», а точным числом. Модель не грузится: в
режиме 'problem' (набор A) она не нужна вовсе — берутся уже посчитанные
векторы задач, ровно как это делает прод в `cache_similar`.

⚠️ ОТДЕЛЬНО ПРОВЕРЯЕТСЯ, ЧТО КОМАНДА НЕ ПИШЕТ В БАЗУ. Измеритель обязан быть
доступен только на чтение: он гоняется по живому банку, и правка `statement`
или `embedding` замером испортила бы ровно то, что мы измеряем.
"""
import contextlib
import json
import tempfile
from unittest import mock
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.eval_sets import save_eval_set
from problems.models import Problem
from problems.search_eval_metrics import EvalCase
from problems.tests.factories import make_problem

DIM = 1024


def вектор(*первые):
    """Вектор размерности корпуса: заданное начало, дальше нули."""
    import numpy as np
    v = np.zeros(DIM, dtype=np.float32)
    for i, x in enumerate(первые):
        v[i] = x
    return v.tobytes()


class SearchEvalCommandTests(TestCase):

    def setUp(self):
        # Задача 1 — запрос. Задача 2 — её точный «дубль» (тот же вектор).
        # Задача 3 — про другое (ортогональный вектор).
        self.p1 = self._задача('первая', вектор(1, 0))
        self.p2 = self._задача('вторая', вектор(1, 0))
        self.p3 = self._задача('третья', вектор(0, 1))

    def _задача(self, title, blob, **поля):
        p = make_problem(title=title)
        значения = {'status': Problem.Status.PUBLISHED,
                    'needs_quality_review': False,
                    'hidden_pending_review': False,
                    'embedding': blob}
        значения.update(поля)
        Problem.objects.filter(pk=p.pk).update(**значения)
        return Problem.objects.get(pk=p.pk)

    def _прогон(self, случаи, mode='problem', encoder=None, **опции):
        with tempfile.TemporaryDirectory() as d:
            набор = Path(d) / 'set.json'
            отчёт = Path(d) / 'report.json'
            save_eval_set(набор, name='T', description='тест',
                          cases=случаи, mode=mode)
            # Кодировщик подменяется патчем модуля, а НЕ параметром команды:
            # тестовому параметру в боевом коде не место, и путь «команда
            # сама берёт модель» тогда остался бы непроверенным.
            патч = mock.patch(
                'problems.management.commands.search_eval._кодировщик_модели',
                return_value=encoder)
            with патч if encoder is not None else contextlib.nullcontext():
                call_command('search_eval', set=str(набор), out=str(отчёт),
                             verbosity=0, **опции)
            return json.loads(отчёт.read_text(encoding='utf-8'))

    def test_правильный_ответ_рядом_даёт_полный_recall(self):
        случай = EvalCase('', {self.p2.pk}, meta={'query_problem_id': self.p1.pk})
        отчёт = self._прогон([случай])
        срез = отчёт['slices']['prod']
        self.assertEqual(срез['recall']['5'], 1.0)
        self.assertEqual(срез['mrr_10'], 1.0)

    def test_далёкий_ответ_в_топ_1_не_попадает(self):
        случай = EvalCase('', {self.p3.pk}, meta={'query_problem_id': self.p1.pk})
        отчёт = self._прогон([случай], ks=[1, 5])
        self.assertEqual(отчёт['slices']['prod']['recall']['1'], 0.0)

    def test_сама_задача_запроса_из_выдачи_исключена(self):
        # Иначе первое место всегда занимала бы она сама (косинус = 1), и
        # любая метрика «Похожих задач» была бы завышена на одну позицию.
        случай = EvalCase('', {self.p2.pk}, meta={'query_problem_id': self.p1.pk})
        отчёт = self._прогон([случай])
        первый = отчёт['slices']['prod']['cases'][0]
        self.assertNotIn(self.p1.pk, первый['ranked_ids'])

    def test_недостижимый_ответ_считается_отдельно_а_не_промахом(self):
        скрытая = self._задача('скрытая', вектор(1, 0), hidden_pending_review=True)
        случай = EvalCase('', {скрытая.pk}, meta={'query_problem_id': self.p1.pk})
        отчёт = self._прогон([случай], scope='prod')
        срез = отчёт['slices']['prod']
        self.assertEqual(срез['unreachable_count'], 1)
        self.assertAlmostEqual(срез['unreachable_share'], 1.0)

    def test_срез_всего_банка_видит_то_чего_не_видит_срез_прода(self):
        скрытая = self._задача('скрытая', вектор(1, 0), hidden_pending_review=True)
        случай = EvalCase('', {скрытая.pk}, meta={'query_problem_id': self.p1.pk})
        отчёт = self._прогон([случай], scope='both')
        self.assertEqual(отчёт['slices']['prod']['unreachable_count'], 1)
        self.assertEqual(отчёт['slices']['all']['unreachable_count'], 0)
        self.assertEqual(отчёт['slices']['all']['recall']['5'], 1.0)

    def test_главное_число_разрыв_попадает_в_отчёт(self):
        случай = EvalCase('', {self.p2.pk}, meta={'query_problem_id': self.p1.pk})
        отчёт = self._прогон([случай])
        self.assertIn('gap_50_5', отчёт['slices']['prod'])

    def test_размер_индекса_записан_в_отчёт(self):
        # Без него цифры нечитаемы: recall по пяти тысячам задач и по
        # тридцати одной тысяче — разные утверждения.
        случай = EvalCase('', {self.p2.pk}, meta={'query_problem_id': self.p1.pk})
        отчёт = self._прогон([случай])
        self.assertEqual(отчёт['slices']['prod']['index_size'], 3)

    def test_команда_не_меняет_защищённые_поля(self):
        поля = ('statement', 'solution', 'answer', 'embedding',
                'content_format', 'human_review')
        до = list(Problem.objects.order_by('id').values('id', *поля))
        случай = EvalCase('', {self.p2.pk}, meta={'query_problem_id': self.p1.pk})
        self._прогон([случай], scope='both')
        после = list(Problem.objects.order_by('id').values('id', *поля))
        self.assertEqual(до, после)

    def test_текстовый_режим_кодирует_запрос_переданным_кодировщиком(self):
        # Модель в прогоне тестов не грузится: 2,12 ГБ ради проверки склейки
        # — это минуты на каждый прогон CI. Проверяется именно склейка:
        # «строка -> вектор -> ранжирование -> метрика».
        import numpy as np

        def кодировщик(тексты):
            # «дубль» ищет то, что лежит в направлении первой оси.
            return np.stack([
                np.eye(DIM, dtype=np.float32)[0 if t == 'дубль' else 1]
                for t in тексты
            ])

        случай = EvalCase('дубль', {self.p2.pk})
        отчёт = self._прогон([случай], mode='text', encoder=кодировщик)
        self.assertEqual(отчёт['slices']['prod']['recall']['5'], 1.0)
