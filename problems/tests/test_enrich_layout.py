# -*- coding: utf-8 -*-
"""Раскладка журнала обогащения v2 по боевым полям.

Проверяются правила, а не факт записи: пустой кандидат не затирает боевое,
значение вне справочника не пишется вовсе, состояние текста только
ухудшается, а слабый первый прогон не перекрывает второй.
"""
import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.enrich import layout
from problems.models import Problem


class ConceptMatchTests(TestCase):
    """Понятие сверяется со словарём; чего в словаре нет — диагностика."""

    def setUp(self):
        self.lookup = layout.concept_lookup({'предельные издержки': '', 'монополия': ''})

    def test_канон_находится_при_другом_регистре_и_пробелах(self):
        found, missing = layout.match_concepts(['  Предельные   Издержки '], self.lookup)
        self.assertEqual(found, ['предельные издержки'])
        self.assertEqual(missing, [])

    def test_чего_нет_в_словаре_уходит_в_offlist(self):
        found, missing = layout.match_concepts(['монополия', 'кривая Энгеля'], self.lookup)
        self.assertEqual(found, ['монополия'])
        self.assertEqual(missing, ['кривая Энгеля'])

    def test_повтор_не_даёт_второй_связи(self):
        found, _missing = layout.match_concepts(['монополия', 'Монополия'], self.lookup)
        self.assertEqual(found, ['монополия'])


class ScalarFieldTests(TestCase):
    """Тексты и короткие значения из закрытых списков."""

    def test_пустой_кандидат_в_результат_не_попадает(self):
        values, invalid = layout.row_scalar_fields(
            {'given': '   ', 'find': '', 'task_nature': ''})
        self.assertEqual(values, {})
        self.assertEqual(invalid, {})

    def test_валидное_короткое_значение_проходит(self):
        values, invalid = layout.row_scalar_fields({'task_nature': 'расчётная'})
        self.assertEqual(values['task_nature'], 'расчётная')
        self.assertEqual(invalid, {})

    def test_значение_вне_справочника_не_пишется_и_видно(self):
        values, invalid = layout.row_scalar_fields({'text_quality': 'ужасная'})
        self.assertNotIn('text_quality', values)
        self.assertEqual(invalid, {'text_quality': 'ужасная'})

    def test_поисковые_запросы_чистятся_от_пустых(self):
        values, _invalid = layout.row_scalar_fields(
            {'search_queries': ['монополия', '', '  ', 'налог']})
        self.assertEqual(values['search_queries'], ['монополия', 'налог'])


class ContentStatusTests(TestCase):
    """Чистка сильнее модели: повышений не бывает."""

    def test_не_задача_даёт_junk(self):
        self.assertEqual(layout.content_status_for('ok', 'не_задача', None), 'junk')
        self.assertEqual(layout.content_status_for('ok', 'чистая', 'не_задача'), 'junk')

    def test_серьёзные_дефекты_дают_needs_fix(self):
        self.assertEqual(
            layout.content_status_for('ok', 'серьёзные_дефекты', None), 'needs_fix')

    def test_чистый_текст_не_поднимает_needs_fix_до_ok(self):
        """Главное правило: `content_cleanup` смотрел на структуру текста,
        модель — на смысл. Отменять чистку моделью нельзя."""
        self.assertEqual(layout.content_status_for('needs_fix', 'чистая', None), 'needs_fix')

    def test_junk_не_понижается_никогда(self):
        self.assertEqual(layout.content_status_for('junk', 'чистая', None), 'junk')

    def test_needs_fix_ухудшается_до_junk(self):
        self.assertEqual(layout.content_status_for('needs_fix', 'не_задача', None), 'junk')


class CodeFeatureTests(TestCase):
    """Шесть особенностей, которые считает код по данным банка."""

    def test_многопунктовая_по_числу_подпунктов(self):
        self.assertIn('многопунктовая',
                      layout.code_features('Условие', ['а', 'б'], False, 2, False, False))
        self.assertNotIn('многопунктовая',
                         layout.code_features('Условие', ['а'], False, 1, False, False))

    def test_разбалловка_по_тексту_и_по_рубрике(self):
        self.assertIn('есть_разбалловка',
                      layout.code_features('За это 5 баллов', [], False, 0, False, False))
        self.assertIn('есть_разбалловка',
                      layout.code_features('Условие', [], False, 0, True, False))

    def test_таблица_и_график_в_условии(self):
        self.assertIn('табличка_в_условии',
                      layout.code_features(r'\begin{tabular}{cc}', [], False, 0, False, False))
        self.assertIn('график_в_условии',
                      layout.code_features('Условие', [], True, 0, False, False))

    def test_английский_по_доле_латиницы(self):
        english = ('A monopolist faces a linear demand curve and chooses '
                   'the profit maximizing output level')
        self.assertIn('на_английском',
                      layout.code_features(english, [], False, 0, False, False))
        self.assertNotIn('на_английском',
                         layout.code_features('Монополист выбирает выпуск',
                                              [], False, 0, False, False))

    def test_графическое_решение_ставится_и_кодом(self):
        """Картинка у РЕШЕНИЯ — прямое доказательство особенности, которую
        модель поставить не может: в вызов 1 картинка решения не подаётся
        (решение владельца 02.09.2026, объединение по ИЛИ)."""
        self.assertIn('графическое_решение',
                      layout.code_features('Условие', [], False, 0, False, False,
                                           has_solution_figure=True))
        self.assertNotIn('графическое_решение',
                         layout.code_features('Условие', [], False, 0, False, False))

    def test_модель_и_код_на_графическом_решении_дают_both(self):
        from problems.enrich import features as feat
        code = layout.code_features('Условие', [], False, 0, False, False,
                                    has_solution_figure=True)
        merged = layout.merge_feature_sources({'графическое_решение'}, code)
        self.assertEqual(merged['графическое_решение'], feat.BY_BOTH)

    def test_олимпиада_только_по_привязке(self):
        """⚠️ Признак выводится из `OlympiadRef`, а не из источника: у
        агрегаторов источник врёт (HANDOFF_OLYMPIADS §2.4)."""
        self.assertIn('с_реальной_олимпиады',
                      layout.code_features('Условие', [], False, 0, False, True))
        self.assertNotIn('с_реальной_олимпиады',
                         layout.code_features('Условие', [], False, 0, False, False))


class CharacterMappingTests(TestCase):
    """`task_nature` → `Problem.character` (решение владельца 07.09.2026)."""

    def test_расчётная_это_количественная(self):
        from problems.enrich.features import character_for
        self.assertEqual(character_for('расчётная'), 'quant')

    def test_теоретическая_и_качественная_это_качественная(self):
        from problems.enrich.features import character_for
        self.assertEqual(character_for('теоретическая'), 'qual')
        self.assertEqual(character_for('качественная'), 'qual')

    def test_не_задача_остаётся_без_разметки(self):
        from problems.enrich.features import character_for
        self.assertEqual(character_for('не_задача'), '')
        self.assertEqual(character_for(''), '')


class Run1BranchTests(TestCase):
    """Ветка первого прогона: данные есть, но помечены и боевого не трогают."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run2 = self.tmp / 'run2.jsonl'
        self.run1 = self.tmp / 'run1.jsonl'
        self.in_both = Problem.objects.create(
            title='Есть во втором', statement='Условие A', answer='1',
            problem_type='старый_тип')
        self.only_run1 = Problem.objects.create(
            title='Только в первом', statement='Условие B', answer='2',
            problem_type='старый_тип')
        self._write(self.run2, [{
            'problem_id': self.in_both.id, 'given': 'дано из run2',
            'task_nature': 'расчётная', 'text_quality': 'чистая',
            'problem_type': 'единственный_выбор',
        }])
        self._write(self.run1, [{
            'problem_id': self.only_run1.id, 'given': 'дано из run1',
            'task_nature': 'качественная', 'text_quality': 'чистая',
            'problem_type': 'единственный_выбор',
        }])

    @staticmethod
    def _write(path, rows):
        with io.open(path, 'w', encoding='utf-8') as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    def _run(self):
        call_command('merge_enrichment_v2', '--apply',
                     parsed=str(self.run2), parsed_run1=str(self.run1),
                     out=str(self.tmp / 'out.json'),
                     sample_html=str(self.tmp / 'sample.html'), verbosity=0)
        self.in_both.refresh_from_db()
        self.only_run1.refresh_from_db()

    def test_задача_из_первого_прогона_получает_поля_и_пометку(self):
        self._run()
        self.assertEqual(self.only_run1.given, 'дано из run1')
        self.assertEqual(self.only_run1.enrichment_source, 'run1')

    def test_первый_прогон_заполняет_тип_там_где_второго_нет(self):
        """«run1 не перекрывает run2» значит «не пишет ПОВЕРХ данных второго
        прогона», а не «не пишет вовсе»: у этой задачи данных run2 нет ни
        одного, и без типа она выпала бы из инварианта «ноль активных без
        problem_type»."""
        self._run()
        self.assertEqual(self.only_run1.problem_type, 'единственный_выбор')

    def test_легаси_открытый_ответ_разводится_а_не_теряется(self):
        """Журнал первого прогона несёт отменённое значение
        `problem_type='открытый_ответ'` (557 активных задач). Схема v2 его не
        знает; без разведения задача осталась бы вовсе без типа — то есть вне
        каталога и вне инварианта «ноль активных без problem_type»."""
        self._write(self.run1, [{'problem_id': self.only_run1.id,
                                 'problem_type': 'открытый_ответ',
                                 'task_nature': 'расчётная'}])
        self._run()
        self.assertEqual(self.only_run1.problem_type, 'задача с развёрнутым ответом')

    def test_забракованная_строка_run2_не_считается_покрытием(self):
        """Строка с `defect: true` данных не даёт. Если считать её покрытием,
        задача останется с легаси-типом навсегда — так #7468 сорвала инвариант
        на первой записи 07.09.2026."""
        self._write(self.run2, [{'problem_id': self.in_both.id, 'defect': True,
                                 'problem_type': 'единственный_выбор'}])
        self._write(self.run1, [{'problem_id': self.in_both.id,
                                 'problem_type': 'верно_неверно',
                                 'task_nature': 'качественная'}])
        self._run()
        self.assertEqual(self.in_both.problem_type, 'верно_неверно')
        self.assertEqual(self.in_both.enrichment_source, 'run1')

    def test_второй_прогон_помечен_run2_и_тип_переписан(self):
        self._run()
        self.assertEqual(self.in_both.enrichment_source, 'run2')
        self.assertEqual(self.in_both.problem_type, 'единственный_выбор')

    def test_пустой_кандидат_не_затирает_непустое_боевое(self):
        Problem.objects.filter(pk=self.in_both.pk).update(given='было в базе')
        self._write(self.run2, [{'problem_id': self.in_both.id, 'given': ''}])
        self._run()
        self.assertEqual(self.in_both.given, 'было в базе')


class SourceTagTests(Run1BranchTests):
    """`--source-tag` (07.09.2026, журнал ТРЕТЬЕГО прогона).

    ⚠️ Метка вычислялась жёстко из двух вариантов: `'run1' if row['_run1']
    else 'run2'`. Журнал третьего прогона она пометила бы как `run2`, и в
    банке осталась бы неправда — поле утверждало бы, что данные из второго
    прогона. Прослеживаемость после этого не восстановить ничем: запрос
    «кто ещё на слабых данных» перестаёт работать навсегда.
    """

    def _run(self, **kwargs):
        call_command('merge_enrichment_v2', '--apply',
                     parsed=str(self.run2), parsed_run1=str(self.run1),
                     out=str(self.tmp / 'out.json'),
                     sample_html=str(self.tmp / 'sample.html'), verbosity=0,
                     **kwargs)
        self.in_both.refresh_from_db()
        self.only_run1.refresh_from_db()

    def test_по_умолчанию_метка_прежняя(self):
        self._run()
        self.assertEqual(self.in_both.enrichment_source, 'run2')

    def test_флаг_метит_основной_журнал(self):
        self._run(source_tag='run3')
        self.assertEqual(self.in_both.enrichment_source, 'run3')

    def test_подмешанные_из_run1_метятся_run1_независимо_от_флага(self):
        """Флаг именует ОСНОВНОЙ журнал. Задачи, взятые из `--parsed-run1`,
        и правда оттуда — переименовать их значило бы соврать во второй раз."""
        self._run(source_tag='run3')
        self.assertEqual(self.only_run1.enrichment_source, 'run1')

    def test_умолчание_совпадает_с_константой(self):
        from problems.management.commands.merge_enrichment_v2 import (
            DEFAULT_SOURCE_TAG, RUN1_SOURCE_TAG,
        )
        self.assertEqual(DEFAULT_SOURCE_TAG, 'run2')
        self.assertEqual(RUN1_SOURCE_TAG, 'run1')
