# -*- coding: utf-8 -*-
"""Разбор вариантов теста из хвоста условия (`problems/test_options_parse.py`).

Решение владельца 15.09.2026: варианты, вписанные текстом в конец условия,
переносятся в подпункты. Ложное срабатывание здесь хуже пропуска — вырезанные
подвопросы испортили бы задачу, — поэтому половина фикстур про отказ.
"""
from django.test import SimpleTestCase

from problems.test_options_parse import (
    boolean_correct_label, correct_labels, cut_boolean_tail, formula_worse, parse_options,
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


class RepeatedNumberTests(SimpleTestCase):
    """«1. (1) текст»: номер строки, повторённый в варианте, — не текст (решение 15.09)."""

    def test_number_in_brackets_equal_to_label_is_dropped(self):
        parsed = parse_options('Что будет с кофе?\n1. (1) спрос растёт;\n2. (2) спрос падает.')
        self.assertEqual(parsed.options, (('1', 'спрос растёт'), ('2', 'спрос падает')))

    def test_number_with_bracket_or_dot_equal_to_label_is_dropped(self):
        self.assertEqual(parse_options('Вопрос?\n1. 1) да\n2. 2) нет').options,
                         (('1', 'да'), ('2', 'нет')))
        self.assertEqual(
            parse_options('Когда прибыль максимальна?\n1. 1. $P = MC$\n2. 2. $P = AC$').options,
            (('1', '$P = MC$'), ('2', '$P = AC$')))

    def test_other_numbers_stay_in_the_text(self):
        # Номер не равен метке — это текст варианта (ссылка на пункты условия).
        self.assertEqual(parse_options('Какие верны?\n1. (2) и (3)\n2. (3) и (4)').options,
                         (('1', '(2) и (3)'), ('2', '(3) и (4)')))
        # Число без пробела после точки и число без скобки — тоже текст.
        self.assertEqual(parse_options('Сколько?\n1. 1.5 млн\n2. 2.5 млн').options,
                         (('1', '1.5 млн'), ('2', '2.5 млн')))
        self.assertEqual(parse_options('Сколько?\n1) 1 000 рублей\n2) 2 000 рублей').options,
                         (('1', '1 000 рублей'), ('2', '2 000 рублей')))

    def test_answer_with_repeated_number_still_matches(self):
        parsed = parse_options('Что будет с кофе?\n1. (1) спрос растёт;\n2. (2) спрос падает.')
        self.assertEqual(correct_labels('2. (2) спрос падает;', parsed), {'2'})
        self.assertEqual(correct_labels('спрос растёт', parsed), {'1'})


class BooleanTailTests(SimpleTestCase):
    """Хвост «Верно/Неверно» у «верно/неверно» с плитками (решение 15.09)."""

    def test_one_line_tail_is_cut(self):
        for tail in ('1) Верно  2) Неверно', 'а) верно\tб) неверно', 'Верно Неверно'):
            with self.subTest(tail=tail):
                self.assertEqual(cut_boolean_tail('Спрос растёт.\n\n\n%s\n' % tail),
                                 ('Спрос растёт.', 'boolean_tail'))

    def test_two_line_tail_is_cut_with_header(self):
        for tail in ('1. Верно.\n2. Неверно.', '1. 1) Верно\n2. 2) Неверно',
                     '(1) верно;\n\n(2) неверно'):
            with self.subTest(tail=tail):
                self.assertEqual(cut_boolean_tail('Спрос растёт.\n%s' % tail),
                                 ('Спрос растёт.', 'boolean_tail'))
        self.assertEqual(
            cut_boolean_tail('Спрос растёт.\nВарианты ответа:\n\n1) Верно\n2) Неверно'),
            ('Спрос растёт.', 'boolean_tail'))

    def test_statement_text_is_not_a_tail(self):
        for text in ('Верно ли, что спрос растёт?',
                     'Спрос растёт.\nНеверно, что цена падает.',
                     'Спрос растёт.\n1) Верно 2) Неверно, если цена растёт.',
                     'Спрос растёт.\n1) Верно',
                     'Спрос растёт.\n1) Верно\n2) Верно',
                     'Спрос растёт.\n1) Верно 2) Неверно 3) Не знаю',
                     'Спрос растёт.\n2) Верно\n3) Неверно',
                     'Спрос растёт.\n1) Да\n2) Нет'):
            with self.subTest(text=text):
                self.assertEqual(cut_boolean_tail(text), (None, 'no_tail'))
        self.assertEqual(cut_boolean_tail('1) Верно\n2) Неверно'), (None, 'empty_stem'))


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
