# -*- coding: utf-8 -*-
"""С14, Уровень 0 — метрики измерителя поиска.

Это ядро замера, и оно намеренно оторвано от Django и от модели: на вход
приходит уже готовый список id в порядке выдачи, на выходе — числа. Поэтому
проверить его можно на игрушечных наборах, где правильный ответ виден глазом
и посчитан на бумаге, а не «примерно похож на правду».

⚠️ ЧИСЛА В ТЕСТАХ ПОСЧИТАНЫ РУКАМИ, А НЕ СНЯТЫ С РЕАЛИЗАЦИИ. Это весь смысл:
метрика, подогнанная под собственный вывод, зелёная всегда и не ловит ничего.
Формулы, по которым считались ожидания:

    recall@k = |правильные ∩ первые k| / |правильные|
    MRR@k    = 1 / (позиция первого правильного), 0 если его нет в первых k
    nDCG@k   = DCG / IDCG,  DCG = Σ rel_i / log2(i + 1),  i от 1
"""
import math

from django.test import SimpleTestCase

from problems.search_eval_metrics import (
    EvalCase,
    aggregate,
    evaluate_case,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
)


class RecallTests(SimpleTestCase):
    """recall@k — доля правильных ответов, попавших в первые k."""

    def test_единственный_правильный_на_третьем_месте_попадает_в_топ_5(self):
        self.assertEqual(recall_at_k([1, 2, 3, 4, 5, 6], {3}, 5), 1.0)

    def test_единственный_правильный_на_третьем_месте_не_попадает_в_топ_2(self):
        self.assertEqual(recall_at_k([1, 2, 3, 4, 5, 6], {3}, 2), 0.0)

    def test_из_двух_правильных_найден_один(self):
        # правильные {3, 99}, в топ-5 попал только 3 → 1/2
        self.assertEqual(recall_at_k([1, 2, 3, 4, 5], {3, 99}, 5), 0.5)

    def test_k_больше_длины_выдачи_не_ломается(self):
        self.assertEqual(recall_at_k([1, 2, 3], {3}, 50), 1.0)

    def test_пустая_выдача_даёт_ноль(self):
        self.assertEqual(recall_at_k([], {3}, 5), 0.0)

    def test_без_правильных_ответов_метрика_не_определена(self):
        # Ни одного эталонного id — делить не на что. Молча вернуть 0 нельзя:
        # это неотличимо от «искали и не нашли», а значит завысит долю провалов.
        with self.assertRaises(ValueError):
            recall_at_k([1, 2, 3], set(), 5)


class MrrTests(SimpleTestCase):
    """MRR@k — обратный ранг ПЕРВОГО правильного ответа."""

    def test_правильный_на_первом_месте_даёт_единицу(self):
        self.assertEqual(mrr_at_k([7, 1, 2], {7}, 10), 1.0)

    def test_правильный_на_третьем_месте_даёт_одну_треть(self):
        self.assertAlmostEqual(mrr_at_k([1, 2, 7], {7}, 10), 1 / 3)

    def test_правильный_за_пределами_k_даёт_ноль(self):
        self.assertEqual(mrr_at_k([1, 2, 3, 4, 5, 6, 7], {7}, 5), 0.0)

    def test_считается_первый_правильный_а_не_лучший(self):
        # Правильные {2, 3}: первый встретился на 2-й позиции → 1/2.
        self.assertAlmostEqual(mrr_at_k([1, 2, 3], {2, 3}, 10), 1 / 2)


class NdcgTests(SimpleTestCase):
    """nDCG@k при бинарной релевантности."""

    def test_правильный_на_первом_месте_даёт_единицу(self):
        self.assertAlmostEqual(ndcg_at_k([7, 1, 2], {7}, 10), 1.0)

    def test_один_правильный_на_третьем_месте(self):
        # DCG = 1/log2(4) = 0.5 ; IDCG = 1/log2(2) = 1 → 0.5
        self.assertAlmostEqual(ndcg_at_k([1, 2, 7], {7}, 10), 0.5)

    def test_два_правильных_на_первом_и_третьем_месте(self):
        # DCG  = 1/log2(2) + 1/log2(4) = 1 + 0.5 = 1.5
        # IDCG = 1/log2(2) + 1/log2(3) = 1 + 0.6309297... = 1.6309297...
        ожидание = 1.5 / (1 + 1 / math.log2(3))
        self.assertAlmostEqual(ndcg_at_k([7, 1, 9], {7, 9}, 10), ожидание)

    def test_ничего_не_найдено_даёт_ноль(self):
        self.assertEqual(ndcg_at_k([1, 2, 3], {7}, 10), 0.0)


class EvaluateCaseTests(SimpleTestCase):
    """Один запрос целиком: все метрики разом плюс признак недостижимости."""

    def test_недостижимый_ответ_помечается_и_не_считается_промахом_поиска(self):
        # Правильный id 42 в индексе отсутствует (нет эмбеддинга): поиск не
        # мог его вернуть физически. Это ОТДЕЛЬНАЯ категория, а не 0 recall:
        # смешав их, мы будем чинить поиск там, где чинить надо корпус.
        случай = EvalCase(query='спрос', relevant_ids={42})
        итог = evaluate_case(случай, ranked_ids=[1, 2, 3], index_ids={1, 2, 3},
                             ks=(5,))
        self.assertTrue(итог['unreachable'])
        self.assertEqual(итог['recall'][5], 0.0)

    def test_достижимый_ответ_не_помечается_недостижимым(self):
        случай = EvalCase(query='спрос', relevant_ids={2})
        итог = evaluate_case(случай, ranked_ids=[1, 2, 3], index_ids={1, 2, 3},
                             ks=(5,))
        self.assertFalse(итог['unreachable'])
        self.assertEqual(итог['recall'][5], 1.0)

    def test_частично_достижимый_ответ_недостижимым_не_считается(self):
        # Из двух правильных один в индексе есть — запрос измерим.
        случай = EvalCase(query='спрос', relevant_ids={2, 42})
        итог = evaluate_case(случай, ranked_ids=[1, 2, 3], index_ids={1, 2, 3},
                             ks=(5,))
        self.assertFalse(итог['unreachable'])


class AggregateTests(SimpleTestCase):
    """Свод по набору: средние и главное число — разрыв recall@50 − recall@5."""

    def test_разрыв_считается_как_recall50_минус_recall5(self):
        # Запрос 1: правильный на 1-м месте  → recall@5 = 1, recall@50 = 1
        # Запрос 2: правильный на 30-м месте → recall@5 = 0, recall@50 = 1
        # Среднее: recall@5 = 0.5, recall@50 = 1.0, разрыв = 0.5
        выдача1 = list(range(1, 61))
        выдача2 = list(range(1, 61))
        свод = aggregate([
            evaluate_case(EvalCase('q1', {1}), выдача1, set(выдача1), (5, 50)),
            evaluate_case(EvalCase('q2', {30}), выдача2, set(выдача2), (5, 50)),
        ], ks=(5, 50))
        self.assertAlmostEqual(свод['recall'][5], 0.5)
        self.assertAlmostEqual(свод['recall'][50], 1.0)
        self.assertAlmostEqual(свод['gap_50_5'], 0.5)
        self.assertEqual(свод['queries'], 2)

    def test_доля_недостижимых_считается_отдельно(self):
        свод = aggregate([
            evaluate_case(EvalCase('q1', {1}), [1, 2], {1, 2}, (5,)),
            evaluate_case(EvalCase('q2', {99}), [1, 2], {1, 2}, (5,)),
        ], ks=(5,))
        self.assertAlmostEqual(свод['unreachable_share'], 0.5)

    def test_пустой_набор_не_делит_на_ноль(self):
        свод = aggregate([], ks=(5,))
        self.assertEqual(свод['queries'], 0)
        self.assertEqual(свод['recall'][5], 0.0)
