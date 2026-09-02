"""Оценка качества версии задачи — `problems/olympiad_quality.py`.

Счёт нужен ровно для одного: сравнить версии ОДНОЙ задачи внутри кластера
дублей и пометить лучшую. Ничего не скрывается и не удаляется.

Каждый сигнал проверяется отдельно: тест обязан краснеть, если этот сигнал
перестанут учитывать. Ради этого проверяется не только итоговый счёт, но и
конкретное слагаемое — иначе выпавший сигнал маскировался бы соседним.
"""
from django.test import SimpleTestCase

from problems.olympiad_quality import (
    COMPONENT_NAMES,
    explain,
    pick_best,
    quality_components,
    quality_score,
)

# Условие длиной ровно LENGTH_CAP: прибавка за объём уже на потолке, и
# сигналы не путаются с ней.
CLEAN = 'Фирма максимизирует прибыль. ' * 40


def score(**kwargs):
    kwargs.setdefault('text', CLEAN)
    return quality_score(quality_components(**kwargs))


class ОтдельныеСигналыTests(SimpleTestCase):

    def test_вердикт_ревьюера_решает_сильнее_всех(self):
        approved = quality_components(text=CLEAN, human_review='approved')
        defect = quality_components(text=CLEAN, human_review='defect')
        self.assertEqual(approved['human_review'], 3.0)
        self.assertEqual(defect['human_review'], -3.0)
        self.assertGreater(quality_score(approved), quality_score(defect))

    def test_пустой_вердикт_нейтрален(self):
        """Не смотрели — не значит плохо."""
        self.assertEqual(
            quality_components(text=CLEAN, human_review='')['human_review'], 0.0)

    def test_статус_duplicate_бьёт_сильнее_draft(self):
        components = {s: quality_components(text=CLEAN, status=s)['status']
                      for s in ('published', 'draft', 'hidden', 'duplicate')}
        self.assertEqual(components['published'], 0.0)
        self.assertLess(components['draft'], components['published'])
        self.assertLess(components['hidden'], components['draft'])
        self.assertLess(components['duplicate'], components['hidden'])

    def test_шлюз_качества_условия_учитывается(self):
        self.assertLess(
            score(needs_quality_review=True), score(needs_quality_review=False))

    def test_шлюз_качества_решения_весит_меньше_чем_условия(self):
        """Дефект решения задачу не скрывает — значит и весить должен меньше."""
        by_statement = quality_components(
            text=CLEAN, needs_quality_review=True)['quality_gate']
        by_solution = quality_components(
            text=CLEAN, solution_needs_review=True)['solution_gate']
        self.assertLess(by_statement, by_solution)
        self.assertLess(by_solution, 0.0)

    def test_потерянная_картинка_понижает_счёт(self):
        """Маркер в тексте есть, строки ProblemFigure нет — рисунок потерян."""
        с_картинкой = quality_components(
            text=CLEAN + '[[FIGURE:abc]]', figure_rows=1)
        без_картинки = quality_components(
            text=CLEAN + '[[FIGURE:abc]]', figure_rows=0)
        self.assertEqual(с_картинкой['figures_missing'], 0.0)
        self.assertEqual(без_картинки['figures_missing'], -1.0)

    def test_потери_картинок_считаются_но_не_бесконечно(self):
        """Две потери и десять — одинаково «рисунка нет»."""
        две = quality_components(text=CLEAN + '[[FIGURE:a]][[FIGURE:b]]')
        десять = quality_components(text=CLEAN + '[[FIGURE:x]]' * 10)
        self.assertEqual(две['figures_missing'], -2.0)
        self.assertEqual(десять['figures_missing'], -2.0)

    def test_признаки_порчи_текста_понижают_счёт(self):
        """Непарный доллар — один из шести признаков text_clean.defects()."""
        грязный = quality_components(text=CLEAN + ' $x + 1')
        self.assertLess(грязный['text_defects'], 0.0)
        self.assertEqual(quality_components(text=CLEAN)['text_defects'], 0.0)

    def test_markdown_ценится_выше_легаси_plain(self):
        self.assertGreater(
            quality_components(text=CLEAN, content_format='markdown')['content_format'],
            quality_components(text=CLEAN, content_format='plain')['content_format'])

    def test_пустые_подпункты_понижают_счёт(self):
        self.assertLess(
            quality_components(text=CLEAN, part_statements=['а', '', ''])['empty_parts'],
            quality_components(text=CLEAN, part_statements=['а', 'б', 'в'])['empty_parts'])

    def test_обрезанное_условие_проигрывает_полному(self):
        self.assertLess(
            quality_components(text='коротко')['length'],
            quality_components(text=CLEAN)['length'])

    def test_прибавка_за_длину_упирается_в_потолок(self):
        """Иначе длинная, но грязная версия перевесила бы короткую и чистую."""
        self.assertEqual(quality_components(text='а' * 1000)['length'], 1.0)
        self.assertEqual(quality_components(text='а' * 50000)['length'], 1.0)


class ЧтоНЕВходитВСчётTests(SimpleTestCase):

    def test_hidden_pending_review_не_является_сигналом_качества(self):
        """Это «человек ЕЩЁ НЕ СМОТРЕЛ», а не «плохо».

        Флаг стоит у 26 832 задач из 41 307 — почти две трети банка.
        Считать его признаком плохого значило бы наказывать задачу за то,
        что до неё не дошла очередь.
        """
        self.assertNotIn('hidden_pending_review', COMPONENT_NAMES)
        self.assertNotIn('hidden_pending_review', quality_components(text=CLEAN))


class ВыборЛучшегоTests(SimpleTestCase):

    def test_побеждает_наибольший_счёт(self):
        best, tie = pick_best({10: 1.0, 20: 5.0, 30: 3.0})
        self.assertEqual(best, 20)
        self.assertFalse(tie)

    def test_при_ничьей_побеждает_наименьший_id(self):
        """Правило детерминировано: иначе победитель менялся бы от прогона."""
        best, tie = pick_best({77: 2.0, 12: 2.0, 45: 2.0})
        self.assertEqual(best, 12)
        self.assertTrue(tie)

    def test_пустой_кластер_не_роняет(self):
        self.assertEqual(pick_best({}), (None, False))


class ОбъяснениеTests(SimpleTestCase):

    def test_показываются_только_различающиеся_слагаемые(self):
        победитель = quality_components(text=CLEAN, human_review='approved')
        соперник = quality_components(text=CLEAN, human_review='defect')
        why = explain(победитель, соперник)
        self.assertEqual(list(why), ['human_review'])
        self.assertEqual(why['human_review'], (3.0, -3.0))

    def test_одинаковые_версии_объяснять_нечем(self):
        одинаково = quality_components(text=CLEAN)
        self.assertEqual(explain(одинаково, dict(одинаково)), {})

    def test_у_каждого_слагаемого_есть_человеческое_имя(self):
        self.assertEqual(set(quality_components(text=CLEAN)), set(COMPONENT_NAMES))
