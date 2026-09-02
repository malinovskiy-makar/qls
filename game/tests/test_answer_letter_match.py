# -*- coding: utf-8 -*-
u"""Сопоставление буквы ответа с меткой подпункта.

В Сборнике АА встречается ЛАТИНСКАЯ «a» при кириллических метках
«а, б, в, г». На глаз буквы неразличимы, а по коду это разные символы,
и задача молча выпадала из пула с причиной «буква ответа не сопоставилась
с меткой». Замер 2026-09-02: так терялось 6 задач, каждая с виду
правильная.

Зубастость. Мало проверить, что латинская «a» теперь ложится на метку:
тест обязан покраснеть и в обратную сторону, если кто-то расширит
таблицу двойников до различимых пар. Поэтому рядом стоит проверка,
что «m» НЕ считается «м»: подменять различимые буквы значило бы гадать.
"""
from django.test import TestCase

from game.management.commands.build_game_pool import (
    extract_multi, extract_question, normalize_label,
)
from problems.models import Problem, ProblemPart


def make(answer, labels=('а', 'б', 'в', 'г'),
         options=('первое', 'второе', 'третье', 'четвёртое'),
         problem_type='тест: один ответ'):
    problem = Problem.objects.create(
        title='', statement='Что из перечисленного верно про рынок труда?',
        answer=answer, problem_type=problem_type, status='published')
    for order, (label, text) in enumerate(zip(labels, options)):
        ProblemPart.objects.create(problem=problem, label=label,
                                   statement=text, answer='', order=order)
    return problem


class NormalizeLabelTests(TestCase):

    def test_latin_lookalikes_fold_to_cyrillic(self):
        self.assertEqual(normalize_label('a'), 'а')
        self.assertEqual(normalize_label('E'), 'е')
        self.assertEqual(normalize_label('c'), 'с')

    def test_distinguishable_letters_are_left_alone(self):
        # «m» похожа на «м», но различима. Подмена была бы гаданием.
        self.assertNotEqual(normalize_label('m'), 'м')
        self.assertNotEqual(normalize_label('h'), 'н')

    def test_trailing_punctuation_still_stripped(self):
        self.assertEqual(normalize_label('Б).'), 'б')


class LatinAnswerLetterTests(TestCase):

    def test_latin_a_matches_cyrillic_label(self):
        problem = make('a')
        _, _, correct, reason = extract_question(problem)
        self.assertIsNone(reason)
        self.assertEqual(correct, 0)

    def test_latin_a_inside_multi_answer(self):
        problem = make('aг', problem_type='тест: все верные')
        _, _, indices, reason = extract_multi(problem)
        self.assertIsNone(reason)
        self.assertEqual(indices, [0, 3])

    def test_letter_outside_labels_is_still_refused(self):
        # Буква, которой нет среди меток, по-прежнему брак: это не
        # начертание, а отсутствующий подпункт.
        problem = make('бвд', labels=('а', 'б', 'в', 'г'),
                       problem_type='тест: все верные')
        _, _, _, reason = extract_multi(problem)
        self.assertEqual(reason, 'буква ответа не сопоставилась с меткой')

    def test_numeric_answer_under_multi_is_still_refused(self):
        # Ответ «32000» под типом «все верные» это дефект данных,
        # а не начертание. Молча принимать его нельзя.
        problem = make('32000', problem_type='тест: все верные')
        _, _, _, reason = extract_multi(problem)
        self.assertEqual(reason, 'буква ответа не сопоставилась с меткой')
