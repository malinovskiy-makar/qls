# -*- coding: utf-8 -*-
"""Замена боевого `title` кандидатом: правило корзин и инварианты записи.

Поле видит ученик, правка массовая и необратимая без снимка — поэтому здесь
проверяется не «команда отработала», а пять инвариантов из задания: тексты не
тронуты, изменились ровно посчитанные задачи, имени поля в заголовке не
осталось, длиннее 40 символов среди изменённых нет, `--revert` возвращает
побайтово.
"""
import json
import os
import tempfile
import unittest

from django.core.management import call_command
from django.test import TestCase

from problems import title_replacement as tr
from problems.embedding_provenance import PROTECTED_FIELDS, protected_fingerprint
from problems.models import Problem

try:
    import pymorphy3
except ImportError:  # pragma: no cover — pymorphy3 живёт в requirements/dev.in
    pymorphy3 = None

УСЛОВИЕ = ('Фирма-монополист производит два товара и максимизирует прибыль '
           'при линейном спросе. Найдите равновесную цену.')


def задача(**kwargs):
    kwargs.setdefault('statement', УСЛОВИЕ)
    return Problem.objects.create(**kwargs)


class CandidateUsableTests(TestCase):

    def test_годный_кандидат(self):
        self.assertTrue(tr.candidate_is_usable('Дуополия Курно'))

    def test_негодные_кандидаты(self):
        for плохой in ('', '   ', 'title_candidate', 'title_source',
                       'Задача 12', 'Цена $p$', r'Кривая \alpha',
                       'Очень длинный заголовок, который заведомо не влезает '
                       'в сорок символов'):
            with self.subTest(кандидат=плохой):
                self.assertFalse(tr.candidate_is_usable(плохой))


class EchoTests(TestCase):

    def test_префикс_условия_это_эхо(self):
        self.assertTrue(tr.is_echo_of_statement(
            'Фирма-монополист производит два товара и…', УСЛОВИЕ))

    def test_первое_предложение_это_эхо(self):
        условие = 'Монополия выпускает два товара. Найдите цену.'
        self.assertTrue(tr.is_echo_of_statement(
            'Монополия выпускает два товара', условие))

    def test_короткое_совпадение_эхом_не_считается(self):
        """«Монополия» — начало условия, но это название, а не обрубок."""
        self.assertFalse(tr.is_echo_of_statement('Монополия', УСЛОВИЕ))

    def test_свой_заголовок_не_эхо(self):
        self.assertFalse(tr.is_echo_of_statement(
            'Равновесие Нэша в дилемме заключённого', УСЛОВИЕ))


@unittest.skipIf(pymorphy3 is None, 'pymorphy3 не установлен')
class EconTermTests(TestCase):

    def test_термин_находится_в_любом_падеже(self):
        for заголовок in ('Предельные издержки', 'О предельных издержках',
                          'Эластичность спроса', 'Монополия'):
            with self.subTest(заголовок=заголовок):
                self.assertTrue(tr.has_econ_term(заголовок))

    def test_бессмысленная_кличка_термина_не_содержит(self):
        for заголовок in ('Подсолнух - 2', "It's a life", 'Измерение С-37',
                          'Это сложнее, чем вы думаете'):
            with self.subTest(заголовок=заголовок):
                self.assertFalse(tr.has_econ_term(заголовок))

    def test_общее_слово_термином_не_считается(self):
        """Иначе «Величина Х» осталась бы как авторский заголовок."""
        self.assertFalse(tr.has_econ_term('Величина Х'))


class BucketTests(TestCase):

    def test_A_обрубок_первой_строки(self):
        p = задача(title='Фирма-монополист производит два товара и…',
                   title_candidate='Дуополия Курно',
                   title_source='model-firstline')
        self.assertEqual(tr.bucket(p), 'A')

    def test_B_эхо_среди_kept(self):
        p = задача(title='Фирма-монополист производит два товара и…',
                   title_candidate='Дуополия Курно', title_source='kept')
        self.assertEqual(tr.bucket(p), 'B')

    def test_C_длинный_kept(self):
        p = задача(title='Очень длинный авторский заголовок про монополию и цены',
                   title_candidate='Монополия и цена', title_source='kept')
        self.assertEqual(tr.bucket(p), 'C')

    @unittest.skipIf(pymorphy3 is None, 'pymorphy3 не установлен')
    def test_C_короткий_без_термина(self):
        p = задача(title='Подсолнух - 2', title_candidate='Опцион и погода',
                   title_source='kept')
        self.assertEqual(tr.bucket(p), 'C')

    @unittest.skipIf(pymorphy3 is None, 'pymorphy3 не установлен')
    def test_C_оставляем_короткий_с_термином(self):
        p = задача(title='Равновесие Нэша', title_candidate='Дилемма заключённого',
                   title_source='kept')
        self.assertEqual(tr.bucket(p), 'C-оставляем')

    def test_D_совпадает(self):
        p = задача(title='Дуополия Курно', title_candidate='Дуополия Курно',
                   title_source='model-empty')
        self.assertEqual(tr.bucket(p), 'D-совпадает')

    def test_D_баговый_кандидат(self):
        p = задача(title='Монополия', title_candidate='title_candidate',
                   title_source='title_source')
        self.assertEqual(tr.bucket(p), 'D-кандидат негоден')

    def test_A_проверяется_раньше_B(self):
        """Обрубок первой строки — одновременно и эхо. Если порядок сменить,
        числа корзин разъедутся, а решение владельца привязано к A."""
        p = задача(title='Фирма-монополист производит два товара и…',
                   title_candidate='Дуополия Курно',
                   title_source='model-firstline')
        self.assertEqual(tr.bucket(p), 'A')
        self.assertTrue(tr.is_echo_of_statement(p.title, p.statement))


class ApplyTests(TestCase):

    def setUp(self):
        self.снимок = os.path.join(tempfile.mkdtemp(), 'titles.json')
        self.меняем = задача(title='Фирма-монополист производит два товара и…',
                             title_candidate='Дуополия Курно',
                             title_source='model-firstline')
        self.не_трогаем = задача(title='Монополия',
                                 title_candidate='title_candidate',
                                 title_source='title_source')

    def _apply(self, *args):
        call_command('apply_title_candidates', '--snapshot', self.снимок, *args)

    def test_без_apply_ничего_не_пишется(self):
        self._apply()
        self.меняем.refresh_from_db()
        self.assertEqual(self.меняем.title,
                         'Фирма-монополист производит два товара и…')
        self.assertFalse(os.path.exists(self.снимок))

    def test_пишется_только_title(self):
        до = protected_fingerprint(Problem.objects.all(), PROTECTED_FIELDS)
        кандидат_до = self.меняем.title_candidate
        self._apply('--apply')
        self.меняем.refresh_from_db()
        self.assertEqual(self.меняем.title, 'Дуополия Курно')
        self.assertEqual(self.меняем.title_candidate, кандидат_до)
        self.assertEqual(
            protected_fingerprint(Problem.objects.all(), PROTECTED_FIELDS), до)

    def test_задача_вне_корзин_не_меняется(self):
        self._apply('--apply')
        self.не_трогаем.refresh_from_db()
        self.assertEqual(self.не_трогаем.title, 'Монополия')

    def test_после_замены_нет_имён_полей_и_нет_длинных(self):
        self._apply('--apply')
        self.assertFalse(Problem.objects.filter(
            title__in=sorted(tr.FIELD_NAME_MARKERS)).exists())
        for заголовок in Problem.objects.filter(
                id=self.меняем.id).values_list('title', flat=True):
            self.assertLessEqual(len(заголовок), tr.TITLE_LIMIT)

    def test_снимок_содержит_ровно_изменённые(self):
        self._apply('--apply')
        with open(self.снимок, encoding='utf-8') as fh:
            снимок = json.load(fh)
        self.assertEqual(list(снимок), [str(self.меняем.id)])
        self.assertEqual(снимок[str(self.меняем.id)],
                         'Фирма-монополист производит два товара и…')

    def test_revert_возвращает_побайтово(self):
        было = self.меняем.title
        self._apply('--apply')
        self._apply('--revert', '--apply')
        self.меняем.refresh_from_db()
        self.assertEqual(self.меняем.title, было)

    def test_повторный_прогон_после_замены_даёт_ноль(self):
        """Идемпотентность: после замены `title` равен кандидату, значит
        задача уходит в «D-совпадает» и второй раз не переписывается."""
        self._apply('--apply')
        self.меняем.refresh_from_db()
        self.assertEqual(tr.bucket(self.меняем), 'D-совпадает')

    def test_отчёт_рисуется_и_не_пишет_в_базу(self):
        путь = os.path.join(os.path.dirname(self.снимок), 'review.html')
        self._apply('--report', '--report-path', путь)
        self.assertTrue(os.path.exists(путь))
        with open(путь, encoding='utf-8') as fh:
            html = fh.read()
        self.assertIn('Дуополия Курно', html)
        self.меняем.refresh_from_db()
        self.assertNotEqual(self.меняем.title, 'Дуополия Курно')
