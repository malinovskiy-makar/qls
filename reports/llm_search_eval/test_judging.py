# -*- coding: utf-8 -*-
"""Разметка пула судьями: карточка, пачки, разбор вердиктов, слияние.

⚠️ ЧЕСТНО: этот модуль написан ДО тестов, в нарушение порядка. Гарантию,
которую даёт «посмотри, как тест краснеет», здесь заменяет проверка
зубастости: каждый дефект возвращается в код мутацией и обязан покраснить
свой тест (`mutations.py`). Без этой проверки тесты ниже стоили бы ровно
столько же, сколько зелёная галочка.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import judging  # noqa: E402


ROW = {
    'id': 42,
    'topics': ['Олигополия и теория игр'],
    'tags': ['дуополия'],
    'concepts': ['равновесие Курно'],
    'problem_type': 'расчётная',
    'difficulty': 3,
    'title': 'Налог на дуополию',
    'given': 'Г' * 500,
    'find': 'Н' * 500,
    'statement': 'У' * 1000,
}


class CardTests(unittest.TestCase):
    def test_в_карточке_есть_все_поля(self):
        text = judging.card(ROW)
        for name in ('id: 42', 'тема:', 'теги:', 'понятия:', 'тип:',
                     'сложность:', 'заголовок:', 'дано:', 'найти:',
                     'условие:'):
            self.assertIn(name, text)

    def test_условие_обрезано_шестьюстами_знаками(self):
        text = judging.card(ROW)
        body = text.split('условие: ')[1]
        self.assertEqual(len(body), 600)

    def test_дано_и_найти_обрезаны_тремястами(self):
        text = judging.card(ROW)
        self.assertEqual(len(text.split('дано: ')[1].split('\n')[0]), 300)
        self.assertEqual(len(text.split('найти: ')[1].split('\n')[0]), 300)

    def test_пустые_поля_не_роняют_карточку(self):
        text = judging.card({'id': 7})
        self.assertIn('id: 7', text)

    def test_сложность_ноль_не_превращается_в_пустоту(self):
        # 0 и None у сложности — разное, а `or` их сливает.
        self.assertIn('сложность: 0', judging.card({'id': 1, 'difficulty': 0}))


class BatchTests(unittest.TestCase):
    def test_пачки_по_двадцать_пять(self):
        got = judging.batches(list(range(60)))
        self.assertEqual([len(b) for b in got], [25, 25, 10])

    def test_ни_один_кандидат_не_потерян(self):
        ids = list(range(141))
        self.assertEqual(sum(judging.batches(ids), []), ids)

    def test_пустой_пул_даёт_пустой_список(self):
        self.assertEqual(judging.batches([]), [])


class ParseTests(unittest.TestCase):
    def test_обычный_ответ(self):
        labels, missing, extra = judging.parse_verdicts(
            {'1': 2, '2': 0}, [1, 2])
        self.assertEqual(labels, {1: 2, 2: 0})
        self.assertEqual((missing, extra), ([], []))

    def test_пропущенный_кандидат_назван_а_не_занулён(self):
        # «Модель про него не сказала» и «модель сказала ноль» — разное.
        labels, missing, _ = judging.parse_verdicts({'1': 2}, [1, 2])
        self.assertNotIn(2, labels)
        self.assertEqual(missing, [2])

    def test_чужой_id_уходит_в_лишние(self):
        labels, _, extra = judging.parse_verdicts({'1': 2, '99': 2}, [1])
        self.assertEqual(labels, {1: 2})
        self.assertEqual(extra, ['99'])

    def test_метка_вне_шкалы_прижимается_к_границе(self):
        labels, _, _ = judging.parse_verdicts({'1': 7, '2': -3}, [1, 2])
        self.assertEqual(labels, {1: 2, 2: 0})

    def test_нечисловая_метка_не_роняет_пачку(self):
        labels, _, extra = judging.parse_verdicts({'1': 'да', '2': 1}, [1, 2])
        self.assertEqual(labels, {2: 1})
        self.assertEqual(extra, ['1'])


class MergeTests(unittest.TestCase):
    def test_оба_годится_дают_годится(self):
        got = judging.merge({1: 2}, {1: 2})
        self.assertEqual(got[1]['label'], 2)
        self.assertFalse(got[1]['disagreement'])

    def test_оба_не_годится_дают_не_годится(self):
        self.assertEqual(judging.merge({1: 0}, {1: 0})[1]['label'], 0)

    def test_спор_годится_против_не_годится_даёт_спорно_с_флагом(self):
        got = judging.merge({1: 2}, {1: 0})
        self.assertEqual(got[1]['label'], 1)
        self.assertTrue(got[1]['disagreement'])

    def test_годится_против_спорно_тоже_спорно(self):
        got = judging.merge({1: 2}, {1: 1})
        self.assertEqual(got[1]['label'], 1)
        self.assertTrue(got[1]['disagreement'])

    def test_оба_спорно_это_согласие(self):
        got = judging.merge({1: 1}, {1: 1})
        self.assertEqual(got[1]['label'], 1)
        self.assertFalse(got[1]['disagreement'])

    def test_один_судья_промолчал_метка_помечена_неполной(self):
        got = judging.merge({1: 2}, {})
        self.assertEqual(got[1]['label'], 2)
        self.assertTrue(got[1]['partial'])


class MergeRuleTests(unittest.TestCase):
    """Три правила слияния меток судей, решение владельца 10.09.2026.

    Считаются все три, основным становится то, у которого согласие с
    ручной разметкой владельца по шкале «годится / не годится» выше.
    Два других идут в отчёт строками чувствительности: если выводы от
    правила не зависят, это надо показать, а не утверждать.
    """

    def rule(self, name, a, b):
        return judging.merge({1: a}, {1: b}, rule=name)[1]['label']

    def test_согласие_годится_только_при_обоих_двойках(self):
        self.assertEqual(self.rule('согласие', 2, 2), 2)
        self.assertEqual(self.rule('согласие', 2, 1), 1)
        self.assertEqual(self.rule('согласие', 2, 0), 1)
        self.assertEqual(self.rule('согласие', 0, 0), 0)

    def test_мягкое_засчитывает_одну_двойку(self):
        self.assertEqual(self.rule('мягкое', 2, 0), 2)
        self.assertEqual(self.rule('мягкое', 2, 1), 2)
        self.assertEqual(self.rule('мягкое', 1, 0), 1)
        self.assertEqual(self.rule('мягкое', 0, 0), 0)

    def test_строгое_роняет_пару_от_одного_нуля(self):
        self.assertEqual(self.rule('строгое', 2, 2), 2)
        self.assertEqual(self.rule('строгое', 2, 0), 0)
        self.assertEqual(self.rule('строгое', 2, 1), 1)
        self.assertEqual(self.rule('строгое', 1, 1), 1)

    def test_три_правила_расходятся_на_спорной_паре(self):
        got = {name: self.rule(name, 2, 0)
               for name in ('согласие', 'мягкое', 'строгое')}
        self.assertEqual(got, {'согласие': 1, 'мягкое': 2, 'строгое': 0})

    def test_флаг_разногласия_от_правила_не_зависит(self):
        for name in ('согласие', 'мягкое', 'строгое'):
            self.assertTrue(
                judging.merge({1: 2}, {1: 0}, rule=name)[1]['disagreement'])

    def test_неизвестное_правило_ошибка_а_не_тихий_откат(self):
        with self.assertRaises(ValueError):
            judging.merge({1: 2}, {1: 2}, rule='как-нибудь')


class AgreementTests(unittest.TestCase):
    MANUAL = {1: 2, 2: 0, 3: 1, 4: 2}

    def test_точное_совпадение(self):
        got = judging.agreement({1: 2, 2: 0, 3: 1, 4: 0}, self.MANUAL)
        self.assertAlmostEqual(got['точное совпадение'], 0.75)

    def test_спорное_выброшено_из_бинарной_доли(self):
        # Пара 3 (спорно у человека) в бинарный счёт не входит.
        got = judging.agreement({1: 2, 2: 0, 3: 2, 4: 2}, self.MANUAL)
        self.assertEqual(got['пар без «спорно»'], 3)
        self.assertAlmostEqual(got['годится / не годится'], 1.0)

    def test_считаются_только_общие_пары(self):
        got = judging.agreement({1: 2}, self.MANUAL)
        self.assertEqual(got['общих пар'], 1)

    def test_без_общих_пар_не_делим_на_ноль(self):
        self.assertEqual(judging.agreement({}, self.MANUAL)['общих пар'], 0)


if __name__ == '__main__':
    unittest.main()
