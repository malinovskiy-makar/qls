"""
Тесты автопроверки ответов (Фаза 18) и валидации конструктора тестов.
"""
from django.test import TestCase

from problems.answer_check import (
    check_custom_problem,
    check_open_answer,
    check_option_answer,
    parse_number,
)
from problems.models import User
from problems.models_platform import CustomProblem, CustomProblemOption
from teacher.views_problems import _validate


class ParseNumberTests(TestCase):

    def test_integers_decimals_fractions(self):
        self.assertEqual(parse_number('42'), 42)
        self.assertEqual(parse_number('0,5'), parse_number('0.5'))
        self.assertEqual(parse_number('1/2'), parse_number('0,5'))
        self.assertEqual(parse_number('-3,5'), parse_number('-7/2'))

    def test_garbage_is_not_zero(self):
        """Мусор — это «не число», а не ноль: «не ответил» и «ответил 0» —
        разные вещи."""
        for value in ('', 'абв', '1/0', None, '--'):
            self.assertIsNone(parse_number(value), value)


class OpenAnswerTests(TestCase):

    def test_exact_number(self):
        self.assertTrue(check_open_answer('30', '30'))
        self.assertTrue(check_open_answer('30', '30,0'))
        self.assertFalse(check_open_answer('30', '31'))

    def test_float_trap(self):
        """0,1 + 0,2 во float даёт 0.30000000000000004. Через Fraction —
        ровно 0,3, и честный ответ засчитывается."""
        from fractions import Fraction
        total = Fraction('0.1') + Fraction('0.2')
        self.assertTrue(check_open_answer(str(total), '0,3'))

    def test_one_third_is_not_zero_33(self):
        self.assertFalse(check_open_answer('1/3', '0,33'))

    def test_tolerance(self):
        self.assertTrue(check_open_answer('0,57', '0,5721', tolerance='0.01'))
        self.assertFalse(check_open_answer('0,57', '0,6', tolerance='0.01'))

    def test_text_answers_compared_as_strings(self):
        self.assertTrue(check_open_answer('Вырастет', ' вырастет '))
        self.assertFalse(check_open_answer('Вырастет', 'упадёт'))


class OptionAnswerTests(TestCase):

    def test_all_or_nothing(self):
        """Частично верный множественный выбор — неверный."""
        self.assertTrue(check_option_answer({1, 2}, [1, 2]))
        self.assertFalse(check_option_answer({1, 2}, [1]))
        self.assertFalse(check_option_answer({1, 2}, [1, 2, 3]))

    def test_empty_answer_is_wrong(self):
        self.assertFalse(check_option_answer({1}, []))


class CustomProblemCheckTests(TestCase):

    def setUp(self):
        self.tutor = User.objects.create_user(username='t_check',
                                              password='x12345',
                                              role='teacher')

    def test_open_without_reference_answer_is_not_auto_checked(self):
        problem = CustomProblem.objects.create(owner=self.tutor,
                                               statement='Обоснуйте.')
        auto, correct = check_custom_problem(problem, 'что-то')
        self.assertFalse(auto)
        self.assertFalse(correct)

    def test_multiple_choice_all_or_nothing(self):
        problem = CustomProblem.objects.create(
            owner=self.tutor, statement='Что верно?',
            kind=CustomProblem.Kind.MULTIPLE)
        a = CustomProblemOption.objects.create(problem=problem, text='А',
                                               is_correct=True, order=0)
        b = CustomProblemOption.objects.create(problem=problem, text='Б',
                                               is_correct=True, order=1)
        CustomProblemOption.objects.create(problem=problem, text='В',
                                           is_correct=False, order=2)

        self.assertEqual(check_custom_problem(problem, f'{a.pk},{b.pk}'),
                         (True, True))
        self.assertEqual(check_custom_problem(problem, f'{a.pk}'),
                         (True, False))


class TestConstructorValidationTests(TestCase):
    """Ошибки должны быть понятными сообщениями, а не 500-й страницей."""

    def test_single_needs_exactly_one_correct(self):
        options = [{'text': 'А', 'is_correct': False},
                   {'text': 'Б', 'is_correct': False}]
        errors = _validate(CustomProblem.Kind.SINGLE, 'Условие', '', options)
        self.assertTrue(any('ровно один' in e for e in errors))

    def test_multiple_needs_at_least_one_correct(self):
        options = [{'text': 'А', 'is_correct': False},
                   {'text': 'Б', 'is_correct': False}]
        errors = _validate(CustomProblem.Kind.MULTIPLE, 'Условие', '', options)
        self.assertTrue(any('хотя бы один' in e for e in errors))

    def test_at_least_two_options(self):
        errors = _validate(CustomProblem.Kind.SINGLE, 'Условие', '',
                           [{'text': 'А', 'is_correct': True}])
        self.assertTrue(any('два варианта' in e for e in errors))

    def test_empty_statement_rejected(self):
        errors = _validate(CustomProblem.Kind.OPEN, '   ', '42', [])
        self.assertTrue(any('пустым' in e for e in errors))

    def test_valid_single_passes(self):
        options = [{'text': 'А', 'is_correct': True},
                   {'text': 'Б', 'is_correct': False}]
        self.assertEqual(
            _validate(CustomProblem.Kind.SINGLE, 'Условие', '', options), [])
