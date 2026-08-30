# -*- coding: utf-8 -*-
r"""Восстановление картинок легаси-источников из сырых Overleaf-архивов.

Проверяется то, на чём этот конвейер может тихо испортить банк:
границы задачи в исходнике (чужой график хуже отсутствующего) и правило
дописывания маркера (текст не должен меняться сверх маркера).

Каждый тест здесь соответствует дефекту, который БЫЛ найден на живых
данных, а не придуман для галочки: номера задач в комментариях — из
боевого прогона 2026-08-30.
"""
import os
import tempfile

from django.test import SimpleTestCase

from problems.corpus_converter import raw_units as ru

BS = chr(92)


def tex(*lines):
    return '\n'.join(lines)


class UnitBoundsTests(SimpleTestCase):
    """Границы одной задачи внутри листочка на много задач."""

    def test_problem_macro_splits_neighbours(self):
        text = tex(
            BS + r'problem Первая задача про спрос.',
            BS + r'includegraphics{first.png}',
            BS + r'problem Вторая задача про предложение.',
            BS + r'includegraphics{second.png}',
        )
        start = text.index('Вторая')
        left, right = ru.unit_bounds(text, start, start + 6)
        refs = [ref for _off, ref in ru.figures_in_unit(text, left, right)]
        self.assertEqual(refs, ['second.png'],
                         'в блок второй задачи заехала картинка первой')

    def test_item_is_not_a_separator_when_problem_exists(self):
        """`\\item` внутри задачи — подпункт, а не новая задача.

        Если бы он резал блок, картинка после первого подпункта потерялась
        бы у задачи, которой принадлежит."""
        text = tex(
            BS + r'problem Задача с подпунктами.',
            BS + r'item Пункт а.',
            BS + r'item Пункт б.',
            BS + r'includegraphics{plot.png}',
        )
        start = text.index('Задача')
        left, right = ru.unit_bounds(text, start, start + 6)
        self.assertEqual(
            [ref for _o, ref in ru.figures_in_unit(text, left, right)],
            ['plot.png'])

    def test_item_is_a_separator_when_file_has_no_problem_macro(self):
        """Живой дефект #37247: в `05/main.tex` задачи — это `\\item`,
        разделителей `\\problem` нет, и блок вырастал до целого раздела в
        18 607 символов. Задаче приписывались три чужих графика."""
        text = tex(
            BS + r'section*{Экономические циклы}',
            BS + r'item Первый вопрос про безработицу.',
            BS + r'includegraphics{Cycle_1.png}',
            BS + r'item Второй вопрос про инфляцию.',
            BS + r'includegraphics{Cycle_2.png}',
        )
        start = text.index('Второй')
        left, right = ru.unit_bounds(text, start, start + 6)
        self.assertEqual(
            [ref for _o, ref in ru.figures_in_unit(text, left, right)],
            ['Cycle_2.png'])

    def test_oversized_block_falls_back_to_window(self):
        """Разделителей нет вовсе — блок не должен стать всем документом."""
        filler = 'слово ' * 4000
        text = filler + 'ЯКОРЬ ' + filler + BS + 'includegraphics{far.png}'
        start = text.index('ЯКОРЬ')
        left, right = ru.unit_bounds(text, start, start + 5)
        self.assertLessEqual(right - left, 2 * ru.FALLBACK_PAD + 16)
        self.assertEqual(ru.figures_in_unit(text, left, right), [])


class FieldRoutingTests(SimpleTestCase):
    """Картинка после `\\solution` принадлежит разбору, а не условию."""

    def test_figure_before_solution_goes_to_statement(self):
        text = (BS + r'problem Условие.' + BS + r'includegraphics{a.png}'
                + BS + r'solution Разбор.')
        off = text.index('a.png')
        self.assertEqual(ru.field_for(text, 0, len(text), off), 'statement')

    def test_figure_after_solution_goes_to_solution(self):
        text = (BS + r'problem Условие.' + BS + r'solution Разбор.'
                + BS + r'includegraphics{b.png}')
        off = text.index('b.png')
        self.assertEqual(ru.field_for(text, 0, len(text), off), 'solution')


class ResolveImageTests(SimpleTestCase):
    """LaTeX ищет файл по нескольким папкам и сам подставляет расширение."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = self.dir.name
        os.makedirs(os.path.join(self.root, 'pics'), exist_ok=True)
        for name in ('pics/plot.png', 'near.jpg'):
            path = os.path.join(self.root, name.replace('/', os.sep))
            with open(path, 'wb') as fh:
                fh.write(b'x')

    def test_relative_path(self):
        self.assertIsNotNone(
            ru.resolve_image('pics/plot.png', self.root, self.root))

    def test_extension_is_guessed(self):
        """108 живых ссылок написаны без расширения — без подстановки они
        считались бы «файлом, которого нет»."""
        self.assertIsNotNone(
            ru.resolve_image('pics/plot', self.root, self.root))

    def test_graphicspath_directory(self):
        self.assertIsNotNone(
            ru.resolve_image('plot.png', self.root, self.root,
                             extra_dirs=['pics/']))

    def test_missing_file_is_none(self):
        self.assertIsNone(
            ru.resolve_image('pics/nothing.png', self.root, self.root))

    def test_parent_escape_does_not_reach_outside(self):
        """Ссылка `../secret` не должна вытащить файл вне проекта."""
        outside = os.path.join(self.root, 'outside.png')
        with open(outside, 'wb') as fh:
            fh.write(b'x')
        inner = os.path.join(self.root, 'pics')
        self.assertIsNone(ru.resolve_image('../outside.png', inner, inner))

    def test_parent_escape_in_the_middle_does_not_reach_outside(self):
        """`..` в СЕРЕДИНЕ пути не ловится очисткой начала строки —
        поэтому проверяется итоговый путь, а не текст ссылки."""
        outside = os.path.join(self.root, 'outside.png')
        with open(outside, 'wb') as fh:
            fh.write(b'x')
        inner = os.path.join(self.root, 'pics')
        self.assertIsNone(
            ru.resolve_image('sub/../../outside.png', inner, inner))


class GraphicsPathTests(SimpleTestCase):
    def test_multiple_directories(self):
        text = BS + r'graphicspath{{img/}{figures/}}'
        self.assertEqual(ru.graphics_dirs(text), ['img/', 'figures/'])

    def test_absent(self):
        self.assertEqual(ru.graphics_dirs('нет такой команды'), [])


class MarkerAppendRuleTests(SimpleTestCase):
    """Правило дописывания маркера — то же, что в команде.

    Живой дефект боевого прогона: первый вариант делал `.strip()` целиком
    и снимал ВЕДУЩИЕ переводы строк у #42522, #30502, #28355 и #27513.
    Текст обязан меняться ровно на маркер и ни на что больше."""

    @staticmethod
    def append(current, marker):
        if marker in current:
            return current
        return (current.rstrip() + '\n\n' + marker
                if current.strip() else marker)

    def test_leading_whitespace_survives(self):
        before = '\n\n  Условие задачи.'
        after = self.append(before, '[[FIGURE:aa]]')
        self.assertTrue(after.startswith('\n\n  Условие задачи.'))

    def test_empty_field_gets_bare_marker(self):
        self.assertEqual(self.append('', '[[FIGURE:aa]]'), '[[FIGURE:aa]]')
        self.assertEqual(self.append('   \n', '[[FIGURE:aa]]'),
                         '[[FIGURE:aa]]')

    def test_second_marker_appends(self):
        once = self.append('Условие.', '[[FIGURE:aa]]')
        twice = self.append(once, '[[FIGURE:bb]]')
        self.assertEqual(twice, 'Условие.\n\n[[FIGURE:aa]]\n\n[[FIGURE:bb]]')

    def test_repeat_is_idempotent(self):
        once = self.append('Условие.', '[[FIGURE:aa]]')
        self.assertEqual(self.append(once, '[[FIGURE:aa]]'), once)
