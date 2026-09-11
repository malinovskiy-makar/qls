# -*- coding: utf-8 -*-
"""Сопоставление понятий из ответа модели с закрытым словарём EconConcept.

Правило сессии: понятия — ТОЛЬКО из словаря. Всё, что модель придумала
сверх него, идёт в отчёт, а не в пул. Поэтому здесь нет и не должно
появиться нечёткого поиска: «похоже на понятие из словаря» — это уже
новое понятие, и решать про него владельцу, а не коду.

⚠️ У модели `EconConcept` два поля: `canonical` и `section`. Алиасов в
базе НЕТ (проверено в фазе −1), поэтому сопоставление идёт по одному
каноническому имени.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import concepts  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_регистр_не_важен(self):
        self.assertEqual(concepts.normalize('Спрос'), concepts.normalize('спрос'))

    def test_ё_и_е_сводятся(self):
        self.assertEqual(concepts.normalize('твёрдый бюджет'),
                         concepts.normalize('твердый бюджет'))

    def test_лишние_пробелы_схлопываются(self):
        self.assertEqual(concepts.normalize('  кривая   Лоренца '),
                         concepts.normalize('кривая Лоренца'))


class MatchTests(unittest.TestCase):
    DICT = concepts.build_dictionary([
        'Кривая Лоренца', 'Коэффициент Джини', 'Твёрдый бюджет'])

    def test_точное_совпадение_находится(self):
        found, offlist = concepts.match(['Кривая Лоренца'], self.DICT)
        self.assertEqual(found, ['Кривая Лоренца'])
        self.assertEqual(offlist, [])

    def test_другой_регистр_находится(self):
        found, _ = concepts.match(['кривая лоренца'], self.DICT)
        self.assertEqual(found, ['Кривая Лоренца'])

    def test_ё_в_запросе_находит_ё_в_словаре(self):
        found, _ = concepts.match(['твердый бюджет'], self.DICT)
        self.assertEqual(found, ['Твёрдый бюджет'])

    def test_возвращается_каноническое_имя_а_не_как_написала_модель(self):
        found, _ = concepts.match(['КОЭФФИЦИЕНТ  джини'], self.DICT)
        self.assertEqual(found, ['Коэффициент Джини'])

    def test_нечёткого_поиска_нет(self):
        # «Кривая Лоренца по доходам» — другое понятие, а не то же самое.
        found, offlist = concepts.match(['Кривая Лоренца по доходам'], self.DICT)
        self.assertEqual(found, [])
        self.assertEqual(offlist, ['Кривая Лоренца по доходам'])

    def test_подстрока_словаря_тоже_не_совпадение(self):
        found, offlist = concepts.match(['Лоренца'], self.DICT)
        self.assertEqual(found, [])
        self.assertEqual(offlist, ['Лоренца'])

    def test_несловарное_уходит_в_отчёт(self):
        found, offlist = concepts.match(
            ['Кривая Лоренца', 'индекс счастья'], self.DICT)
        self.assertEqual(found, ['Кривая Лоренца'])
        self.assertEqual(offlist, ['индекс счастья'])

    def test_повтор_не_удваивает_находку(self):
        found, _ = concepts.match(['Кривая Лоренца', 'кривая лоренца'],
                                  self.DICT)
        self.assertEqual(found, ['Кривая Лоренца'])

    def test_пустая_строка_не_считается_понятием(self):
        found, offlist = concepts.match(['', '   '], self.DICT)
        self.assertEqual((found, offlist), ([], []))


class ScoreTests(unittest.TestCase):
    def test_понятие_весит_вдвое_против_тега(self):
        # Счёт из задания: совпавшие понятия × 2 + совпавшие теги.
        self.assertEqual(
            concepts.overlap_score({'a', 'b'}, {'t'}, {'a', 'b'}, {'t'}), 5)

    def test_ни_одного_совпадения_даёт_ноль(self):
        self.assertEqual(concepts.overlap_score({'a'}, {'t'}, {'x'}, {'y'}), 0)

    def test_считаются_только_общие(self):
        self.assertEqual(
            concepts.overlap_score({'a', 'b'}, {'t', 'u'}, {'b'}, {'u', 'z'}), 3)


if __name__ == '__main__':
    unittest.main()
