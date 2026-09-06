"""Фаза 7.1 редизайна каталога: разбор слитных ответов теста.

Пять форм записи одного ответа («аб», «а, б», «а,б», «а б», «АБ») — одно
множество меток; та же функция режет ответ в сборщике игрового пула.
"""
from django.test import TestCase

from game.management.commands.build_game_pool import extract_multi
from problems.answer_check import (
    catalog_test_correct_labels, check_catalog_test, label_set,
)
from problems.models import ProblemPart
from problems.tests.factories import make_problem


class LabelSetTests(TestCase):
    def test_five_forms_are_the_same_set(self):
        for raw in ('аб', 'а, б', 'а,б', 'а б', 'АБ'):
            self.assertEqual(label_set(raw), {'а', 'б'}, raw)

    def test_other_separators_and_debris(self):
        self.assertEqual(label_set('а; б'), {'а', 'б'})
        self.assertEqual(label_set('а) б)'), {'а', 'б'})
        self.assertEqual(label_set('а. в.'), {'а', 'в'})
        self.assertEqual(label_set('  Б, а,, '), {'а', 'б'})
        self.assertEqual(label_set('абвг'), {'а', 'б', 'в', 'г'})

    def test_word_is_one_label_not_letters(self):
        self.assertEqual(label_set('верно'), {'верно'})
        self.assertEqual(label_set('Неверно.'), {'неверно'})
        self.assertEqual(label_set(''), set())
        self.assertEqual(label_set(None), set())
        self.assertEqual(label_set('12'), {'12'})

    def test_known_labels_decide_what_is_glued(self):
        self.assertEqual(label_set('аб', ['а', 'б', 'в', 'г']), {'а', 'б'})
        self.assertEqual(label_set('АБ', ['а)', 'б)']), {'а', 'б'})
        # «да» при вариантах а–г — слово, хотя обе буквы есть в алфавите меток
        self.assertEqual(label_set('да', ['а', 'б', 'в', 'г']), {'да'})
        # буква вне известных меток — строка не режется
        self.assertEqual(label_set('ав', ['а', 'б']), {'ав'})


class GluedAnswerProblemTests(TestCase):
    """Как задача 5999 локально: четыре варианта, ответ записан «аб»."""

    def setUp(self):
        self.problem = make_problem(
            'Выберите все верные утверждения о ценовой дискриминации.',
            problem_type='тест: все верные', answer='аб')
        for i, label in enumerate('абвг', start=1):
            ProblemPart.objects.create(problem=self.problem, label=label,
                                       statement='Утверждение %s о дискриминации' % label,
                                       order=i)

    def test_correct_labels_are_split(self):
        self.assertEqual(catalog_test_correct_labels(self.problem), {'а', 'б'})

    def test_marked_parts_win_over_the_answer_string(self):
        self.problem.parts.filter(label='в').update(answer='верно')
        self.assertEqual(catalog_test_correct_labels(self.problem), {'в'})

    def test_check_accepts_any_form_and_order(self):
        for given in ('аб', 'ба', 'б, а', 'А Б'):
            self.assertEqual(check_catalog_test(self.problem, given), (True, True), given)
        self.assertEqual(check_catalog_test(self.problem, 'а'), (True, False))
        self.assertEqual(check_catalog_test(self.problem, 'абв'), (True, False))

    def test_game_pool_uses_the_same_split(self):
        for raw in ('вг', 'в, г', 'в г'):
            self.problem.answer = raw
            question, options, correct, reason = extract_multi(self.problem)
            self.assertIsNone(reason, (raw, reason))
            self.assertEqual(correct, [2, 3], raw)
        self.problem.answer = 'вд'
        self.assertEqual(extract_multi(self.problem)[3], 'буква ответа не сопоставилась с меткой')
