# -*- coding: utf-8 -*-
"""Переранжирование пула моделью: карточка, слияние пачек, порядок."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reranking  # noqa: E402


ROW = {
    'id': 42,
    'topics': ['Олигополия и теория игр'],
    'tags': ['дуополия'],
    'concepts': ['равновесие Курно'],
    'find': 'Н' * 400,
    'problem_type': 'расчётная',
    'difficulty': 3,
    'title': 'Налог на дуополию',
    'statement': 'У' * 1000,
}


class CardTests(unittest.TestCase):
    def test_карточка_короткая_и_без_условия(self):
        # Реранкер получает вдвое больше кандидатов в пачке, чем судья, и
        # условие ему не нужно: он не решает, годится ли задача, а
        # раскладывает уже отобранное.
        text = reranking.card(ROW)
        self.assertNotIn('условие', text)
        self.assertIn('найти:', text)

    def test_найти_обрезано_двумястами(self):
        body = reranking.card(ROW).split('найти: ')[1].split('\n')[0]
        self.assertEqual(len(body), 200)

    def test_пометка_о_совпавших_понятиях_попадает_в_карточку(self):
        # Для системы S4: кандидату из ноги S_concept дописывается, сколько
        # понятий запроса он покрыл. Без пометки эта нога неотличима от
        # прочих, и проверить её вклад нечем.
        text = reranking.card(ROW, concept_hits=3)
        self.assertIn('совпало понятий из запроса: 3', text)

    def test_без_пометки_строки_нет_вовсе(self):
        self.assertNotIn('совпало понятий', reranking.card(ROW))


class MergeTests(unittest.TestCase):
    def test_кандидаты_упорядочены_по_убыванию_балла(self):
        got = reranking.merge([{1: 10, 2: 90}, {3: 50}])
        self.assertEqual(got, [2, 3, 1])

    def test_кандидат_без_балла_уходит_в_хвост(self):
        # Оценённый кандидат стоит ВЫШЕ неоценённого, даже если его id
        # больше: иначе тест не отличает «в хвост» от «отсортировать всех
        # по номеру», и правило остаётся никем не сторожимым.
        got = reranking.merge([{2: 10}], all_ids=[1, 2])
        self.assertEqual(got, [2, 1])

    def test_равные_баллы_упорядочены_устойчиво_по_id(self):
        self.assertEqual(reranking.merge([{5: 50, 3: 50}]), [3, 5])

    def test_балл_вне_шкалы_прижимается(self):
        got = reranking.merge([{1: 500, 2: -20}])
        self.assertEqual(got, [1, 2])
        self.assertEqual(reranking.clamp(500), 100)
        self.assertEqual(reranking.clamp(-20), 0)

    def test_пустой_вход_даёт_пустой_список(self):
        self.assertEqual(reranking.merge([]), [])


class SchemaTests(unittest.TestCase):
    def test_схема_пригодна_для_строгого_режима(self):
        # У каждого объекта additionalProperties=false и все свойства в
        # required — иначе Responses API отвечает 400 ещё до модели.
        schema = reranking.SCHEMA
        self.assertFalse(schema['additionalProperties'])
        item = schema['properties']['rows']['items']
        self.assertFalse(item['additionalProperties'])
        self.assertEqual(sorted(item['required']), ['id', 'score'])


if __name__ == '__main__':
    unittest.main()
