# -*- coding: utf-8 -*-
"""Разбор вариантов теста из хвоста условия (`problems/test_options_parse.py`).

Решение владельца 15.09.2026: варианты, вписанные текстом в конец условия,
переносятся в подпункты. Ложное срабатывание здесь хуже пропуска — вырезанные
подвопросы испортили бы задачу, — поэтому половина фикстур про отказ.
"""
from django.test import SimpleTestCase

from problems.test_options_parse import (
    boolean_correct_label, correct_labels, formula_worse, parse_options,
    parse_with_reason,
)


class ParseOptionsTests(SimpleTestCase):

    def test_numbered_lettered_with_header_and_semicolons(self):
        parsed = parse_options(
            'Кто устанавливает ключевую ставку в России?\n\nВарианты ответа:\n\n'
            '1. (a) Правительство Российской Федерации;\n'
            '2. (b) Центральный банк Российской Федерации;\n'
            '3. (c) Министерство финансов.')
        self.assertEqual((parsed.style, parsed.header), ('numbered_lettered', True))
        self.assertEqual(parsed.stem, 'Кто устанавливает ключевую ставку в России?')
        self.assertEqual(parsed.options, (
            ('a', 'Правительство Российской Федерации'),
            ('b', 'Центральный банк Российской Федерации'),
            ('c', 'Министерство финансов')))
        self.assertEqual(parsed.aliases, {'1': 'a', '2': 'b', '3': 'c'})

    def test_numbered_without_header_trims_ends_and_spaces(self):
        parsed = parse_options('Что растёт при инфляции?\n1) цены.\n2)   зарплаты;\n3) ничего')
        self.assertEqual((parsed.style, parsed.header), ('numbered', False))
        self.assertEqual(parsed.options, (('1', 'цены'), ('2', 'зарплаты'), ('3', 'ничего')))

    def test_cyrillic_letters(self):
        parsed = parse_options('Выберите верное.\nа) спрос растёт\nб) спрос падает')
        self.assertEqual(parsed.style, 'lettered')
        self.assertEqual([label for label, _text in parsed.options], ['а', 'б'])

    def test_latin_letters_with_short_header(self):
        parsed = parse_options('Choose one.\nВАРИАНТЫ.\nA. demand\nB. supply')
        self.assertTrue(parsed.header)
        self.assertEqual(parsed.stem, 'Choose one.')
        self.assertEqual([label for label, _text in parsed.options], ['a', 'b'])

    def test_header_spellings(self):
        for header in ('Варианты ответов:', 'варианты', 'Варианты ответа.'):
            with self.subTest(header=header):
                self.assertTrue(parse_options('Вопрос?\n%s\n1) да\n2) нет' % header).header)

    def test_gap_in_numbering_is_rejected(self):
        self.assertEqual(parse_with_reason('Вопрос?\n1) a\n2) b\n4) c'),
                         (None, 'mixed_style'))

    def test_numbered_subquestions_with_verbs_are_rejected(self):
        self.assertEqual(
            parse_with_reason('Спрос Q = 10 - P, предложение Q = P.\n'
                              '1. Найдите равновесие.\n2. Постройте график.'),
            (None, 'verb_like_subquestion'))

    def test_single_option_line_is_not_a_block(self):
        self.assertEqual(parse_with_reason('Вопрос?\n1) единственная строка'),
                         (None, 'no_block'))

    def test_text_after_the_block_means_no_tail(self):
        self.assertEqual(parse_with_reason('Вопрос?\n1) да\n2) нет\nПояснение к задаче.'),
                         (None, 'no_block'))

    def test_mixed_styles_are_rejected(self):
        self.assertEqual(parse_with_reason('Вопрос?\n1) да\nб) нет'), (None, 'mixed_style'))

    def test_block_without_stem_is_rejected(self):
        self.assertEqual(parse_with_reason('1) да\n2) нет'), (None, 'empty_stem'))

    def test_empty_option_text_is_rejected(self):
        self.assertEqual(parse_with_reason('Вопрос?\n1) да\n2) ;'), (None, 'mixed_style'))


class CorrectLabelsTests(SimpleTestCase):

    def setUp(self):
        self.lettered = parse_options(
            'Кто устанавливает ставку?\nВарианты ответа:\n'
            '1. (a) Правительство;\n2. (b) Центральный банк;\n3. (c) Минфин.')
        self.numbered = parse_options(
            'Что входит в ВВП?\n1. потребления\n2. инвестиций\n3. дохода\n4. 3%')

    def test_whole_option_line(self):
        self.assertEqual(correct_labels('2. (b) Центральный банк;', self.lettered), {'b'})

    def test_option_text_with_and_without_number(self):
        self.assertEqual(correct_labels('3. дохода', self.numbered), {'3'})
        self.assertEqual(correct_labels('инвестиций', self.numbered), {'2'})

    def test_marks(self):
        self.assertEqual(correct_labels('124', self.numbered), {'1', '2', '4'})
        self.assertEqual(correct_labels('b', self.lettered), {'b'})
        self.assertEqual(correct_labels('2', self.lettered), {'b'})

    def test_several_lines_for_multi(self):
        self.assertEqual(correct_labels('1. потребления;\n2. инвестиций;', self.numbered),
                         {'1', '2'})

    def test_ambiguous_or_unknown_answer_gives_nothing(self):
        numbers = parse_options('Сколько?\n1) 2\n2) 4\n3) 6')
        # «2» — и метка второго варианта, и текст первого: не угадываем.
        self.assertEqual(correct_labels('2', numbers), set())
        self.assertEqual(correct_labels('Министерство культуры', self.lettered), set())


class BooleanTests(SimpleTestCase):

    def test_word_answers(self):
        self.assertEqual(boolean_correct_label('Верно', 'Утверждение.'), 'а')
        self.assertEqual(boolean_correct_label('неверно', 'Утверждение.'), 'б')

    def test_number_is_looked_up_in_the_statement(self):
        self.assertEqual(boolean_correct_label('1', 'Утверждение.\n1) Да\n2) Нет'), 'а')
        self.assertEqual(boolean_correct_label('2', 'Утверждение.\n1) Верно  2) Неверно'), 'б')
        self.assertEqual(boolean_correct_label('2. нет', 'Утверждение.\n1. да\n2. нет'), 'б')

    def test_unknown_answer_gives_none(self):
        self.assertIsNone(boolean_correct_label('3', 'Утверждение.\n1) Да\n2) Нет'))
        self.assertIsNone(boolean_correct_label('может быть', 'Утверждение.'))


class FormulaTests(SimpleTestCase):

    def test_broken_dollars_or_braces_are_worse(self):
        self.assertTrue(formula_worse('$a$ и $b$', '$a$ и $b'))
        self.assertTrue(formula_worse('{x}', '{x'))

    def test_cutting_a_whole_formula_or_escaped_dollar_is_fine(self):
        self.assertFalse(formula_worse('$a$\n1) $b$', '$a$'))
        self.assertFalse(formula_worse('\\$20 и $x$', '\\$20'))
