# -*- coding: utf-8 -*-
"""Проверки числовой эвристики разведки дедупа.

Django не нужен — модуль чистый. Запуск:
    venv313/Scripts/python.exe -m unittest scripts.test_dedup_recon_numbers -v
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.dedup_recon_numbers import (  # noqa: E402
    compare_numbers, extract_numbers, jaccard,
)


class ИзвлечениеЧисел(unittest.TestCase):
    def test_простые_целые(self):
        self.assertEqual(extract_numbers('Цена 100, объём 25'), {'100', '25'})

    def test_запятая_как_десятичный_разделитель(self):
        self.assertEqual(extract_numbers('эластичность 1,5'), {'1.5'})

    def test_точка_и_запятая_дают_одно_число(self):
        self.assertEqual(extract_numbers('1,5'), extract_numbers('1.5'))

    def test_пробел_как_разделитель_тысяч(self):
        self.assertEqual(extract_numbers('доход 1 000 000 рублей'), {'1000000'})

    def test_тысячи_с_пробелом_и_без_совпадают(self):
        self.assertEqual(extract_numbers('1 000'), extract_numbers('1000'))

    def test_хвостовой_ноль_дроби_не_плодит_число(self):
        self.assertEqual(extract_numbers('12,50'), extract_numbers('12.5'))

    def test_целое_с_нулевой_дробью_равно_целому(self):
        self.assertEqual(extract_numbers('12.0'), extract_numbers('12'))

    def test_пустой_текст(self):
        self.assertEqual(extract_numbers(''), set())
        self.assertEqual(extract_numbers(None), set())

    def test_текст_без_чисел(self):
        self.assertEqual(extract_numbers('Объясните эффект дохода'), set())

    def test_проценты_дают_число(self):
        self.assertEqual(extract_numbers('ставка 7%'), {'7'})

    def test_разметка_latex_не_даёт_чисел(self):
        # \begin{tabular}{|c|c|} — это разметка таблицы, а не данные задачи.
        self.assertEqual(
            extract_numbers(r'\begin{tabular}{|c|c|} \multicolumn{2}{c}{шапка}'),
            set())


class СравнениеПар(unittest.TestCase):
    def test_одинаковые_числа(self):
        self.assertEqual(compare_numbers('Q = 100 - 2P', 'Q = 100 - 2P'),
                         'совпадают')

    def test_один_и_тот_же_сюжет_с_разными_параметрами(self):
        # Ровно тот случай, ради которого эвристика и заведена.
        self.assertEqual(compare_numbers('Q = 100 - 2P', 'Q = 300 - 7P'),
                         'не совпадают')

    def test_частичное_пересечение(self):
        self.assertEqual(compare_numbers('цена 10 и 20', 'цена 10 и 55'),
                         'частично')

    def test_оба_без_чисел(self):
        self.assertEqual(compare_numbers('теория', 'теория'), 'оба без чисел')

    def test_числа_только_у_одной(self):
        self.assertEqual(compare_numbers('цена 10', 'теория'),
                         'числа только у одной')


class ДоляОбщихЧисел(unittest.TestCase):
    def test_полное_совпадение(self):
        self.assertEqual(jaccard('10 и 20', '20 и 10'), 1.0)

    def test_полное_расхождение(self):
        self.assertEqual(jaccard('10', '20'), 0.0)

    def test_половина(self):
        self.assertAlmostEqual(jaccard('10 20', '10 30'), 1 / 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
