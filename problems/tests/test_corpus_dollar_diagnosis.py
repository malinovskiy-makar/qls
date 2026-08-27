# -*- coding: utf-8 -*-
"""Сессия 2026-08-27 (диагностика разрыва $$ между полями, read-only):
тесты на счётчик непарных $$ — reports/corpus_converter_scaleup/
reshalki_dollar_diagnosis.md опирается на его числа, поэтому по брифу
сессии сам счётчик обязан быть протестирован (не только диагностика
без кода)."""
from django.test import SimpleTestCase

from problems.management.commands.corpus_dollar_diagnosis import (
    unescaped_dollar_dollar_positions, field_dollar_info, find_boundary_pairs,
)


class UnescapedDollarDollarPositionsTests(SimpleTestCase):
    """Зеркалит пропуск '\\$' из problems.rendering._protect_math_and_
    currency посимвольно — экранированная валюта не считается разделителем."""

    def test_empty_text(self):
        self.assertEqual(unescaped_dollar_dollar_positions(''), [])

    def test_no_dollars(self):
        self.assertEqual(unescaped_dollar_dollar_positions('обычный текст'), [])

    def test_single_dollar_dollar_pair(self):
        self.assertEqual(unescaped_dollar_dollar_positions('a $$ b $$ c'), [2, 7])

    def test_escaped_currency_not_counted(self):
        # \$100 — экранированная валюта, не разделитель формулы.
        self.assertEqual(unescaped_dollar_dollar_positions('цена \\$100'), [])

    def test_escaped_currency_next_to_real_dollar_dollar(self):
        text = 'заплатил \\$100, теперь формула $$x=1$$'
        positions = unescaped_dollar_dollar_positions(text)
        self.assertEqual(len(positions), 2)

    def test_odd_count_dangling_dollar_dollar(self):
        # Живой паттерн #47081: statement кончается на непарный '$$'.
        text = 'Вопрос?\n\n$$'
        self.assertEqual(unescaped_dollar_dollar_positions(text), [9])

    def test_escaped_dollar_immediately_before_real_dollar_not_miscounted(self):
        # Состязательный случай: '\$' (экранированная валюта) СРАЗУ
        # перед одиночным '$' — без пропуска экранирования наивный
        # посимвольный скан прочитал бы второй символ пары '\$' и
        # следующий за ним '$' как настоящий '$$'-токен (ложный).
        # Это ЕДИНСТВЕННЫЙ случай, где пропуск '\$' меняет результат —
        # использован для методологии «откат → красный → фикс → зелёный».
        text = '\\$$100'  # рантайм-строка: \ $ $ 1 0 0
        self.assertEqual(unescaped_dollar_dollar_positions(text), [])


class FieldDollarInfoTests(SimpleTestCase):
    """(число_токенов, кончается_ли_на_$$, начинается_ли_с_$$)."""

    def test_empty_field(self):
        self.assertEqual(field_dollar_info(''), (0, False, False))

    def test_no_dollar_dollar(self):
        self.assertEqual(field_dollar_info('обычный текст'), (0, False, False))

    def test_balanced_pair_not_boundary(self):
        cnt, ends, starts = field_dollar_info('текст $$x=1$$ ещё текст')
        self.assertEqual(cnt, 2)
        self.assertFalse(ends)
        self.assertFalse(starts)

    def test_trailing_dangling_dollar_dollar(self):
        # Живой хвост statement #47127.
        cnt, ends, starts = field_dollar_info('...используем оба завода. \n\n$$')
        self.assertEqual(cnt, 1)
        self.assertTrue(ends)
        self.assertFalse(starts)

    def test_leading_dangling_dollar_dollar(self):
        # Упрощённый вариант головы solution #47127 (в реальном поле
        # $$-токенов три — см. FindBoundaryPairsTests ниже для точной
        # формы; здесь проверяется только сам leading-флаг на одном
        # токене, '$MC$' — одиночный '$', эта функция его не считает).
        cnt, ends, starts = field_dollar_info('$$\n\nОбе функции $MC$ убывают...')
        self.assertEqual(cnt, 1)
        self.assertTrue(starts)

    def test_trailing_flag_requires_only_whitespace_after(self):
        cnt, ends, starts = field_dollar_info('текст $$ не пусто после')
        self.assertFalse(ends)  # после $$ есть текст, не только пробелы


class FindBoundaryPairsTests(SimpleTestCase):
    """Разрыв между полями: A кончается непарным $$ (нечётное число
    токенов) И B сразу следом начинается непарным $$ (тоже нечётное)."""

    def test_confirms_real_boundary_pattern(self):
        fields = {
            'statement': 'Условие?\n\n$$',
            'answer': '',
            'solution': '$$\n\nТекст решения, других разделителей формул тут нет.',
        }
        pairs = find_boundary_pairs(fields, order=('statement', 'answer', 'solution'))
        self.assertIn(('statement', 'solution'), pairs)

    def test_does_not_confirm_when_both_fields_balanced(self):
        # Оба поля сами по себе целые (чётное число $$) — совпадение
        # положений НЕ значит разрыв, каждое поле полно само по себе.
        fields = {
            'statement': 'Условие с формулой $$x=1$$ и ещё $$y=2$$',
            'answer': '',
            'solution': '$$z=3$$ и $$w=4$$ тоже целое',
        }
        pairs = find_boundary_pairs(fields, order=('statement', 'answer', 'solution'))
        self.assertEqual(pairs, [])

    def test_does_not_confirm_when_only_one_side_dangling(self):
        # statement кончается непарным $$, но solution НЕ начинается с $$ —
        # пары нет, это просто одиночный непарный $$ (см. "прочие").
        fields = {
            'statement': 'Условие?\n\n$$',
            'answer': '',
            'solution': 'Обычный текст решения без единого $$.',
        }
        pairs = find_boundary_pairs(fields, order=('statement', 'answer', 'solution'))
        self.assertEqual(pairs, [])

    def test_real_47127_shape_confirms_statement_solution(self):
        # Точная форма #47127: solution имеет ТРИ $$-токена (нечётно),
        # начинается с $$ — граница подтверждается несмотря на мусорную
        # "формулу" внутри поля, которую эта функция не обязана разбирать.
        fields = {
            'statement': (
                '...использует первый и третий заводы. \n\n$$'
            ),
            'answer': '',
            'solution': (
                '$$\n\n \n\nОбе функции $MC$ убывают, значит...первом\n'
                '$$TC = \\begin{cases}\n 16Q-0.25Q^2 & Q \\leq 32\n\n'
                ' 256+32(Q-32) -(Q-32)^2& Q \\in [32; 50]\n\n'
                ' \\end{cases}$$\n\n'
            ),
        }
        pairs = find_boundary_pairs(fields, order=('statement', 'answer', 'solution'))
        self.assertIn(('statement', 'solution'), pairs)
