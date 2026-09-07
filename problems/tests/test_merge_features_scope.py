# -*- coding: utf-8 -*-
"""Особенности при мерже ЧАСТИЧНОГО журнала (найдено 07.09.2026).

⚠️ Ошибка, ради которой файл существует, и её цена. `apply_features` идёт по
ВСЕМ активным задачам (кодовые особенности от состава прогона не зависят —
таблица в условии есть или её нет), а модельные берёт из
`model_keys_by_id.get(pid, set())`. Для задачи, которой в журнале НЕТ,
словарь отдаёт пустое множество, и «желаемый» набор получается без единой
модельной особенности — то есть все её модельные связи снимаются.

Пока журнал был полным (боевой прогон run2 на 37 тысячах), это не всплывало:
в журнале была почти каждая задача. Допрогон 07.09 подал журнал на 1 740
задач — и мерж снял модельные особенности у остальных: **18 771 связь
`source='model'` превратилась в 1 019**, задач с особенностями стало 21 518
вместо 27 517. Поймано сверкой отпечатка полей до и после (14 784 чужие
задачи изменились), банк восстановлен из бэкапа фазы 0.

Правило после починки: **прогон отвечает только за задачи своего журнала.**
Модельные особенности задачи вне журнала остаются как были; кодовые
пересчитываются у всех, как и раньше.
"""
import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.enrich import layout
from problems.models import Feature, Problem, ProblemFeature


class FeaturesOutsideJournalTests(TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.journal = self.tmp / 'run.jsonl'
        self.features = layout.ensure_features()

        self.в_журнале = Problem.objects.create(
            statement='Задача из журнала.', answer='1',
            problem_type='единственный_выбор')
        self.вне_журнала = Problem.objects.create(
            statement='Задача, которой в журнале нет.', answer='2',
            problem_type='единственный_выбор')

        # У обеих задач уже стоит модельная особенность — от прошлого прогона.
        for задача in (self.в_журнале, self.вне_журнала):
            ProblemFeature.objects.create(
                problem=задача, feature=self.features['параметры'],
                source='model')

        self._write([{
            'problem_id': self.в_журнале.id,
            'features_1': ['на_доказательство'],
            'task_nature': 'расчётная', 'text_quality': 'чистая',
            'problem_type': 'единственный_выбор',
        }])

    def _write(self, rows):
        with io.open(self.journal, 'w', encoding='utf-8') as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    def _run(self):
        call_command('merge_enrichment_v2', '--apply', parsed=str(self.journal),
                     no_run1=True, out=str(self.tmp / 'out.json'),
                     sample_html=str(self.tmp / 'sample.html'), verbosity=0)

    def _модельные(self, задача):
        return set(ProblemFeature.objects
                   .filter(problem=задача, source__in=('model', 'both'))
                   .values_list('feature__key', flat=True))

    def test_задача_вне_журнала_сохраняет_модельные_особенности(self):
        """Главный тест файла. Прогон отвечает только за свой журнал."""
        self._run()
        self.assertEqual(self._модельные(self.вне_журнала), {'параметры'})

    def test_задача_из_журнала_получает_полную_замену(self):
        """Для охваченных задач замена остаётся полной: журнал — источник
        правды о том, что модель увидела в ЭТОЙ задаче сейчас."""
        self._run()
        self.assertEqual(self._модельные(self.в_журнале), {'на_доказательство'})

    def test_кодовые_особенности_считаются_у_всех(self):
        """Кодовая половина от состава прогона не зависела и не зависит:
        таблица в условии есть или её нет."""
        ProblemPartless = Problem.objects.create(
            statement='Задача с разбалловкой.', answer='3',
            problem_type='единственный_выбор')
        from problems.models import Rubric
        Rubric.objects.create(problem=ProblemPartless)
        self._run()
        коды = set(ProblemFeature.objects
                   .filter(problem=ProblemPartless, source='code')
                   .values_list('feature__key', flat=True))
        self.assertIn('есть_разбалловка', коды)

    def test_общее_число_связей_не_обваливается(self):
        """Сторож на само явление: мерж журнала из одной задачи не имеет права
        уполовинить таблицу связей."""
        до = ProblemFeature.objects.filter(source__in=('model', 'both')).count()
        self._run()
        после = ProblemFeature.objects.filter(source__in=('model', 'both')).count()
        self.assertGreaterEqual(после, до)

    def test_пересечение_модели_и_кода_остаётся_both_у_задачи_вне_журнала(self):
        """`графическое_решение` считают оба. У задачи вне журнала модельная
        половина сохраняется, значит метка обязана остаться `both`, а не
        съехать в `code` — иначе следующий мерж посчитает её кодовой и
        потеряет ответ модели уже законно."""
        from problems.models import ProblemFigure
        ProblemFeature.objects.filter(problem=self.вне_журнала).delete()
        ProblemFeature.objects.create(
            problem=self.вне_журнала,
            feature=self.features['графическое_решение'], source='both')
        ProblemFigure.objects.create(problem=self.вне_журнала,
                                     source_field='solution',
                                     image_data=b'x' * 10)
        self._run()
        связь = ProblemFeature.objects.get(
            problem=self.вне_журнала,
            feature=Feature.objects.get(key='графическое_решение'))
        self.assertEqual(связь.source, 'both')
