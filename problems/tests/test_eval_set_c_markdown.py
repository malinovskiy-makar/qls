# -*- coding: utf-8 -*-
"""С15 — исходник набора C в формате Markdown.

Владелец прислал обновлённый набор (65 строк) не в .docx, как в С14, а в .md,
экспортом из редактора. Формат строки другой, и разбор .docx на нём молча
даёт мусор: остаётся нумерация «27. » в начале и хвост «[]()» от
markdown-ссылки на месте вырезанного адреса. Обе порчи попадают прямо в
поисковый запрос, то есть в измеряемое.

⚠️ ПОВТОР ID — НЕ ОШИБКА И НЕ СКЛЕИВАЕТСЯ. У С14 id 5658 стоял под двумя
разными формулировками, и отчёт С14 назвал это нормой: 58 запросов на 57
уникальных задач. Разные формулировки одной задачи — валидный материал, ради
которого набор и собирается. Склеить их значило бы выкинуть живой запрос
преподавателя и разойтись с базой сравнения «было/стало».
"""
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from problems.management.commands.build_eval_set_c import (
    разобрать_строку,
    читать_строки,
)

СТРОКА_MD = ('27. задача на определение благ роскоши по функции полезности: '
             '[https://weconomics.site/catalog/problem/5658/]'
             '(https://weconomics.site/catalog/problem/5658/)  ')


class РазборСтрокиMarkdownTests(SimpleTestCase):

    def test_из_markdown_ссылки_достаётся_id(self):
        _, pid = разобрать_строку(СТРОКА_MD)
        self.assertEqual(pid, 5658)

    def test_нумерация_строки_не_попадает_в_запрос(self):
        фраза, _ = разобрать_строку(СТРОКА_MD)
        self.assertEqual(
            фраза, 'задача на определение благ роскоши по функции полезности')

    def test_от_markdown_ссылки_не_остаётся_скобок(self):
        """Хвост «[]()» уехал бы в поисковый запрос и мерился бы вместе с ним."""
        фраза, _ = разобрать_строку(СТРОКА_MD)
        for мусор in ('[', ']', '(', ')', 'http'):
            self.assertNotIn(мусор, фраза)

    def test_голая_ссылка_без_формулировки_не_даёт_запроса(self):
        фраза, pid = разобрать_строку(
            '15. [https://weconomics.site/catalog/problem/6406/]'
            '(https://weconomics.site/catalog/problem/6406/)')
        self.assertIsNone(фраза)
        self.assertEqual(pid, 6406)

    def test_формулировка_без_ссылки_не_даёт_id(self):
        фраза, pid = разобрать_строку(
            '21. Задача про сравнение двух вкладов с разными сроками')
        self.assertEqual(фраза, 'Задача про сравнение двух вкладов с разными сроками')
        self.assertIsNone(pid)

    def test_двоеточие_внутри_формулировки_не_режет_её(self):
        """«депозиты, норма резервирования» идут ПОСЛЕ двоеточия у владельца."""
        фраза, pid = разобрать_строку(
            '46. Стандартная задачка на монетарную политику: депозиты, норма '
            'резервирования, кредиты и тд: '
            '[https://weconomics.site/catalog/problem/28052/]'
            '(https://weconomics.site/catalog/problem/28052/)')
        self.assertEqual(pid, 28052)
        self.assertIn('депозиты, норма резервирования', фраза)

    def test_старый_формат_docx_не_сломан(self):
        """В .docx нумерации и скобок нет — разбор обязан работать как в С14."""
        фраза, pid = разобрать_строку(
            'хотеллинг с параметрами и возможностью дискриминировать: '
            'https://weconomics.site/catalog/problem/27181/')
        self.assertEqual(pid, 27181)
        self.assertEqual(
            фраза, 'хотеллинг с параметрами и возможностью дискриминировать')


class ЧтениеИсходникаТests(SimpleTestCase):

    def test_md_читается_построчно(self):
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'set_c.md'
            путь.write_text('1. первая: x\n\n2. вторая: y\n',
                            encoding='utf-8')
            self.assertEqual(читать_строки(путь), ['1. первая: x', '', '2. вторая: y'])

    def test_неизвестное_расширение_отвергается(self):
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'set_c.txt'
            путь.write_text('что-то', encoding='utf-8')
            with self.assertRaises(ValueError):
                читать_строки(путь)
