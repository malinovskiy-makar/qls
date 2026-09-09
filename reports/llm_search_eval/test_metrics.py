# -*- coding: utf-8 -*-
"""Метрики замера на рукотворных примерах с заранее известным ответом.

Каждое число здесь посчитано руками и записано в комментарии рядом.
Метрика, проверенная «тем же кодом, что её считает», не проверена вовсе.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import metrics  # noqa: E402


class PrecisionTests(unittest.TestCase):
    #: id → метка: 2 годится, 1 спорно, 0 не годится.
    LABELS = {1: 2, 2: 0, 3: 2, 4: 1, 5: 2, 6: 0}

    def test_три_годных_из_пяти(self):
        # [1(2), 2(0), 3(2), 4(1), 5(2)] → годных 3 из 5 = 0,6
        self.assertAlmostEqual(
            metrics.precision_at_k([1, 2, 3, 4, 5], self.LABELS, 5), 0.6)

    def test_спорное_не_считается_годным(self):
        # [4(1), 2(0)] → ни одного годного
        self.assertAlmostEqual(
            metrics.precision_at_k([4, 2], self.LABELS, 2), 0.0)

    def test_выдача_короче_k_делится_на_её_длину(self):
        # [1(2), 2(0)] при k=5 → 1 годный из 2 показанных = 0,5.
        # Делить на 5 значило бы штрафовать систему за то, что кандидатов
        # в пуле меньше пяти, — это свойство пула, а не выдачи.
        self.assertAlmostEqual(
            metrics.precision_at_k([1, 2], self.LABELS, 5), 0.5)

    def test_неразмеченный_кандидат_не_считается_годным(self):
        # [1(2), 99(нет метки)] → 1 из 2
        self.assertAlmostEqual(
            metrics.precision_at_k([1, 99], self.LABELS, 2), 0.5)

    def test_пустая_выдача_даёт_ноль(self):
        self.assertEqual(metrics.precision_at_k([], self.LABELS, 5), 0.0)


class PrecisionAmongLabelledTests(unittest.TestCase):
    """Верхняя оценка: неразмеченные не считаются вовсе.

    Нужна ровно там, где разметка неполная и её полнота у систем разная:
    строгая метрика тогда наказывает не за плохую выдачу, а за то, что
    кандидата никто не смотрел. Две границы вместе честнее одной.
    """

    LABELS = {1: 2, 2: 0, 3: 2}

    def test_неразмеченные_не_участвуют(self):
        # [1(2), 99(нет), 2(0)] → среди размеченных 1 годный из 2 = 0,5
        self.assertAlmostEqual(
            metrics.precision_among_labelled([1, 99, 2], self.LABELS, 3), 0.5)

    def test_совсем_без_разметки_даёт_none_а_не_ноль(self):
        # Ноль означал бы «всё плохо», а тут «мерить нечем».
        self.assertIsNone(
            metrics.precision_among_labelled([98, 99], self.LABELS, 3))

    def test_вся_выдача_годная(self):
        self.assertAlmostEqual(
            metrics.precision_among_labelled([1, 3], self.LABELS, 2), 1.0)


class NdcgTests(unittest.TestCase):
    def test_идеальный_порядок_даёт_единицу(self):
        labels = {1: 2, 2: 2, 3: 1, 4: 0}
        self.assertAlmostEqual(
            metrics.ndcg_at_k([1, 2, 3, 4], labels, 4), 1.0)

    def test_обратный_порядок_хуже_идеального(self):
        labels = {1: 2, 2: 2, 3: 1, 4: 0}
        good = metrics.ndcg_at_k([1, 2, 3, 4], labels, 4)
        bad = metrics.ndcg_at_k([4, 3, 2, 1], labels, 4)
        self.assertLess(bad, good)

    def test_число_на_известном_примере(self):
        # Выдача [4(0), 1(2)]. Прирост 2^метка − 1: 0 и 3.
        # DCG = 0/log2(2) + 3/log2(3) = 3/1,584963 = 1,892789
        # Идеал [1(2), 4(0)]: 3/1 + 0 = 3. nDCG = 0,630930
        labels = {1: 2, 4: 0}
        self.assertAlmostEqual(
            metrics.ndcg_at_k([4, 1], labels, 2), 0.6309297535714575)

    def test_без_единой_годной_метки_ноль(self):
        self.assertEqual(metrics.ndcg_at_k([1, 2], {1: 0, 2: 0}, 2), 0.0)

    def test_спорное_весит_меньше_годного(self):
        # Прирост «спорно» = 2^1 − 1 = 1 против 3 у «годится».
        one = metrics.ndcg_at_k([1], {1: 1, 2: 2}, 1)
        two = metrics.ndcg_at_k([2], {1: 1, 2: 2}, 1)
        self.assertLess(one, two)


class ThreeGoodTests(unittest.TestCase):
    def test_ровно_три_годных_в_топ5_засчитывается(self):
        labels = {1: 2, 2: 2, 3: 2, 4: 0, 5: 0}
        self.assertTrue(metrics.has_n_good([1, 2, 3, 4, 5], labels, 3, 5))

    def test_два_годных_не_засчитывается(self):
        labels = {1: 2, 2: 2, 3: 1, 4: 0, 5: 0}
        self.assertFalse(metrics.has_n_good([1, 2, 3, 4, 5], labels, 3, 5))

    def test_третий_годный_за_пределом_топ5_не_спасает(self):
        labels = {1: 2, 2: 2, 6: 2}
        self.assertFalse(
            metrics.has_n_good([1, 2, 3, 4, 5, 6], labels, 3, 5))


class CoverageTests(unittest.TestCase):
    def test_доля_размеченных_в_выдаче(self):
        # [1, 2, 99] при метках на 1 и 2 → 2/3
        self.assertAlmostEqual(
            metrics.labelled_share([1, 2, 99], {1: 2, 2: 0}, 3), 2 / 3)

    def test_пустая_выдача_даёт_ноль(self):
        self.assertEqual(metrics.labelled_share([], {1: 2}, 3), 0.0)


class RecallTests(unittest.TestCase):
    def test_якорь_в_топ5_засчитан(self):
        self.assertEqual(metrics.anchor_recall([[9, 1, 2, 3, 4], [1]],
                                               [9, 9], 5), 0.5)

    def test_якорь_за_топ5_не_засчитан(self):
        self.assertEqual(metrics.anchor_recall([[1, 2, 3, 4, 5, 9]], [9], 5),
                         0.0)

    def test_без_запросов_ноль_а_не_деление_на_ноль(self):
        self.assertEqual(metrics.anchor_recall([], [], 5), 0.0)


if __name__ == '__main__':
    unittest.main()
