# -*- coding: utf-8 -*-
"""Сборка пула кандидатов: слияние, дедуп-группы, тип запроса, инварианты.

Запуск:
    venv313\\Scripts\\python.exe -m unittest discover -s reports/llm_search_eval -p "test_*.py"

Что здесь стережётся:
  - RRF считает по РАНГАМ, а не по весам: у косинуса и у BM25 разные
    шкалы, и складывать их напрямую значило бы подгонять на глаз;
  - из дедуп-группы в пул попадает ровно один — фаворит. Две копии одной
    задачи в пуле удваивают вес одной находки во всех метриках сразу;
  - инварианты падают, а не предупреждают: пул вне границ 30…200 или с
    невидимой задачей ломает сравнение систем молча.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import poolbuild  # noqa: E402


class RrfTests(unittest.TestCase):
    def test_общий_кандидат_поднимается_выше_одиночного(self):
        merged = poolbuild.rrf_merge({'dense': [1, 2, 3], 'bm25': [3, 1, 9]})
        self.assertEqual(merged[0], 1)

    def test_первый_у_обеих_ног_остаётся_первым(self):
        merged = poolbuild.rrf_merge({'dense': [7, 1], 'bm25': [7, 2]})
        self.assertEqual(merged[0], 7)

    def test_вес_считается_по_рангу_с_k_60(self):
        # Первое место даёт 1/61, второе — 1/62. Проверяем само число,
        # иначе «k=60» останется словом в комментарии.
        self.assertAlmostEqual(poolbuild.rrf_weight(0), 1 / 61)
        self.assertAlmostEqual(poolbuild.rrf_weight(1), 1 / 62)

    def test_пустая_нога_не_ломает_слияние(self):
        self.assertEqual(poolbuild.rrf_merge({'dense': [5], 'bm25': []}), [5])


class DedupTests(unittest.TestCase):
    #: id → (группа, фаворит ли)
    GROUPS = {10: ('g1', True), 11: ('g1', False), 12: ('g2', True), 13: (None, False)}

    def test_из_группы_остаётся_фаворит(self):
        # Фаворит стоит ВТОРЫМ намеренно: иначе тест не отличает «оставили
        # фаворита» от «оставили первого попавшегося», и правило про
        # фаворита оказывается никем не сторожимым.
        kept, dropped = poolbuild.collapse_dedup([11, 10, 12, 13], self.GROUPS)
        self.assertEqual(kept, [10, 12, 13])
        self.assertEqual(dropped, [{'id': 11, 'group': 'g1', 'kept': 10}])

    def test_убранный_записан_с_пометкой_и_причиной(self):
        _, dropped = poolbuild.collapse_dedup([10, 11], self.GROUPS)
        self.assertEqual(dropped, [{'id': 11, 'group': 'g1', 'kept': 10}])

    def test_задача_без_группы_проходит_как_есть(self):
        kept, _ = poolbuild.collapse_dedup([13], self.GROUPS)
        self.assertEqual(kept, [13])

    def test_без_фаворита_остаётся_первый_по_рангу(self):
        # Фаворит группы может быть невидим поиску — тогда представителем
        # становится лучший из тех, кто в пул всё-таки попал.
        groups = {20: ('g9', False), 21: ('g9', False)}
        kept, dropped = poolbuild.collapse_dedup([21, 20], groups)
        self.assertEqual(kept, [21])
        self.assertEqual(dropped[0]['kept'], 21)

    def test_порядок_исходного_списка_сохраняется(self):
        kept, _ = poolbuild.collapse_dedup([12, 10, 13], self.GROUPS)
        self.assertEqual(kept, [12, 10, 13])


class QueryTypeTests(unittest.TestCase):
    """Правило владельца от 10.09: тип решает ТОЛЬКО длина, ≤4 слов —
    короткий. Прежняя проверка на глагол снята: она относила к описательным
    «найти равновесие», хотя это ровно та короткая формулировка, ради
    которой владелец и собрал отдельный файл коротких запросов."""

    def test_короткий_запрос(self):
        self.assertEqual(poolbuild.query_type('цена бессрочной облигации'),
                         'короткий')

    def test_четыре_слова_ещё_короткий(self):
        self.assertEqual(poolbuild.query_type('кривая Лоренца и Джини'),
                         'короткий')

    def test_пять_слов_уже_описательный(self):
        self.assertEqual(
            poolbuild.query_type('кривая Лоренца и коэффициент Джини'),
            'описательный')

    def test_глагол_на_тип_больше_не_влияет(self):
        self.assertEqual(poolbuild.query_type('найти равновесие'), 'короткий')

    def test_два_слова_из_файла_коротких(self):
        self.assertEqual(poolbuild.query_type('монополия налог'), 'короткий')

    def test_пунктуация_не_считается_словом(self):
        self.assertEqual(poolbuild.query_type('спрос, предложение — равновесие'),
                         'короткий')


class InvariantTests(unittest.TestCase):
    def setUp(self):
        self.visible = set(range(1, 600))
        self.groups = {}

    def check(self, pool):
        poolbuild.check_pool('q01', pool, self.visible, self.groups)

    def test_пул_в_границах_проходит(self):
        self.check(list(range(1, 51)))

    def test_маленький_пул_роняет(self):
        with self.assertRaises(poolbuild.PoolInvariantError):
            self.check(list(range(1, 20)))

    def test_большой_пул_роняет(self):
        with self.assertRaises(poolbuild.PoolInvariantError):
            self.check(list(range(1, 400)))

    def test_невидимая_задача_роняет(self):
        with self.assertRaises(poolbuild.PoolInvariantError):
            self.check(list(range(1, 50)) + [9999])

    def test_две_задачи_из_одной_группы_роняют(self):
        self.groups = {5: ('g1', True), 6: ('g1', False)}
        with self.assertRaises(poolbuild.PoolInvariantError):
            self.check(list(range(1, 51)))

    def test_повтор_id_роняет(self):
        with self.assertRaises(poolbuild.PoolInvariantError):
            self.check(list(range(1, 51)) + [7])


if __name__ == '__main__':
    unittest.main()
