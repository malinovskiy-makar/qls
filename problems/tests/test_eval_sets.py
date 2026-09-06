# -*- coding: utf-8 -*-
"""С14 — сборка и хранение эталонных наборов A/B/C.

⚠️ ПОЧЕМУ НАБОР A СТРОИТСЯ ПО ТЕКСТУ, А НЕ ПО ТАБЛИЦЕ ДУБЛИКАТОВ.
В базе лежат 10 731 пары `DuplicateCandidate` со статусом «подтверждён», и
`EMBEDDINGS.md` предлагает взять эталон оттуда как «размеченный людьми». На
деле человек не смотрел ни одной: `reviewed_by` и `reviewed_at` пусты у всех
10 731, все записи созданы за шесть секунд 08.06.2026, а статус проставила
команда `process_duplicates` автоматически по порогу косинуса ≥ 0,95.

Взять их эталоном — замкнуть круг: пары отобраны по близости ТЕХ САМЫХ
векторов, которые мы собираемся мерить, поэтому recall вышел бы около
единицы и не означал бы ничего. Признак обязан быть независим от измеряемого,
поэтому пары строятся по совпадению нормализованного ТЕКСТА.
"""
import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from problems.eval_sets import (
    group_duplicates_by_text,
    load_eval_set,
    normalize_statement,
    save_eval_set,
)
from problems.search_eval_metrics import EvalCase


class NormalizeTests(SimpleTestCase):
    """Нормализация текста — то, по чему сравниваются задачи."""

    def test_регистр_и_пробелы_не_различают_задачи(self):
        self.assertEqual(normalize_statement('Спрос   РАВЕН\n 10'),
                         normalize_statement('спрос равен 10'))

    def test_е_и_ё_считаются_одной_буквой(self):
        self.assertEqual(normalize_statement('объём'), normalize_statement('объем'))

    def test_разметка_и_знаки_отбрасываются_а_числа_остаются(self):
        # Числа — единственное, что отличает похожие задачи друг от друга,
        # выбросить их значило бы склеить весь банк в одну группу.
        self.assertEqual(normalize_statement(r'$MC = 2Q$, при **Q=10**.'),
                         'mc  2q при q10')

    def test_пустой_текст_даёт_пустую_строку(self):
        self.assertEqual(normalize_statement(None), '')


class GroupDuplicatesTests(SimpleTestCase):
    """Группировка задач с совпадающим текстом."""

    def test_две_задачи_с_одинаковым_текстом_попадают_в_группу(self):
        группы = group_duplicates_by_text(
            [(1, 'А' * 100), (2, 'А' * 100), (3, 'Б' * 100)], min_len=80)
        self.assertEqual(группы, [[1, 2]])

    def test_группа_возвращается_отсортированной_по_id(self):
        группы = group_duplicates_by_text(
            [(9, 'А' * 100), (2, 'А' * 100), (5, 'А' * 100)], min_len=80)
        self.assertEqual(группы, [[2, 5, 9]])

    def test_короткие_тексты_не_группируются(self):
        # «Найдите равновесие.» встречается в банке сотни раз и одинаковой
        # задачей не делает: группа из таких — мусор, а не эталон.
        группы = group_duplicates_by_text(
            [(1, 'Найдите Q.'), (2, 'Найдите Q.')], min_len=80)
        self.assertEqual(группы, [])

    def test_одиночная_задача_группы_не_образует(self):
        self.assertEqual(
            group_duplicates_by_text([(1, 'А' * 100)], min_len=80), [])


class SaveLoadTests(SimpleTestCase):
    """Формат хранения: один файл — один набор, читается обратно без потерь."""

    def test_набор_читается_обратно_тем_же(self):
        случаи = [EvalCase('спрос на бензин', {17}, meta={'строка': 1})]
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'eval_set_test.json'
            save_eval_set(путь, name='C', description='тест',
                          cases=случаи, warnings=['две строки без id'])
            мета, прочитано = load_eval_set(путь)

        self.assertEqual(мета['name'], 'C')
        self.assertEqual(мета['warnings'], ['две строки без id'])
        self.assertEqual(len(прочитано), 1)
        self.assertEqual(прочитано[0].query, 'спрос на бензин')
        self.assertEqual(прочитано[0].relevant_ids, frozenset({17}))
        self.assertEqual(прочитано[0].meta['строка'], 1)

    def test_на_диске_лежит_обучающий_формат(self):
        # Тот же файл позже пойдёт на дообучение (уровень 5), поэтому ключи
        # именно такие: запрос, правильные id, место под трудные отрицательные.
        случаи = [EvalCase('спрос', {17})]
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'eval_set_test.json'
            save_eval_set(путь, name='B', description='тест', cases=случаи)
            данные = json.loads(путь.read_text(encoding='utf-8'))

        случай = данные['cases'][0]
        self.assertEqual(случай['query'], 'спрос')
        self.assertEqual(случай['relevant_ids'], [17])
        self.assertIsNone(случай['hard_negative_ids'])

    def test_режим_набора_сохраняется_и_читается(self):
        # Набор A мерит «задача → задача»: прод берёт УЖЕ ПОСЧИТАННЫЙ вектор
        # задачи (см. cache_similar), а не кодирует её текст заново. Наборы
        # B и C наоборот — текст запроса надо закодировать. Перепутать режимы
        # значит измерить не ту функцию, поэтому он записан в файле явно.
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'eval_set_test.json'
            save_eval_set(путь, name='A', description='тест',
                          cases=[EvalCase('', {2}, meta={'query_problem_id': 1})],
                          mode='problem')
            мета, _ = load_eval_set(путь)
        self.assertEqual(мета['mode'], 'problem')

    def test_режим_по_умолчанию_текстовый(self):
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'eval_set_test.json'
            save_eval_set(путь, name='C', description='тест', cases=[])
            мета, _ = load_eval_set(путь)
        self.assertEqual(мета['mode'], 'text')

    def test_неизвестный_режим_отвергается_при_сохранении(self):
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'eval_set_test.json'
            with self.assertRaises(ValueError):
                save_eval_set(путь, name='X', description='тест', cases=[],
                              mode='как-нибудь')

    def test_набор_без_случаев_сохраняется_и_читается(self):
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'eval_set_test.json'
            save_eval_set(путь, name='D', description='пусто', cases=[])
            мета, прочитано = load_eval_set(путь)
        self.assertEqual(прочитано, [])
        self.assertEqual(мета['count'], 0)
