# -*- coding: utf-8 -*-
u"""Варианты, вшитые в текст условия (путь SolveHub).

У SolveHub нет ни одного подпункта ProblemPart: варианты стоят в самом
statement блоком «Варианты ответа:», а Problem.answer называет правильный
номером строки. До этой правки все 2 730 тестов источника отсеивались
сборщиком пула с причиной «вариантов не 2–6», сколько бы типов им ни
проставили.

Зубастость. Каждая проверка ломается при снятии правила:
рваная нумерация обязана дать отказ (иначе за варианты примут случайные
строки), путь подпунктов обязан работать по-прежнему (иначе правка тихо
сломала бы Сборник АА), а вопрос обязан НЕ содержать текста вариантов
(иначе игрок увидел бы ответы в самом вопросе).
"""
from django.test import TestCase

from game.management.commands.build_game_pool import (
    BOOLEAN_FALLBACK, extract_boolean, extract_multi, extract_question,
    inline_choice,
)
from problems.models import Problem, ProblemPart

SINGLE = (
    'Отрицательный наклон кривой совокупного спроса не объясняется эффектом:'
    '\n\nВарианты ответа:\n\n'
    '1. реального богатства\n2. процентной ставки\n3. дохода\n'
    '4. импортных закупок\n')

MULTI = (
    'Выберите все верные утверждения о монополии:\n\nВарианты ответа:\n\n'
    '1. цена выше предельных издержек\n'
    '2. выпуск ниже конкурентного\n'
    '3. кривая спроса горизонтальна\n')


def make(statement, answer, problem_type='тест: один ответ'):
    return Problem.objects.create(
        title='', statement=statement, answer=answer,
        problem_type=problem_type, status='published')


class InlineChoiceTests(TestCase):

    def test_block_is_split_into_question_and_options(self):
        problem = make(SINGLE, '3. дохода')
        head, options, positions = inline_choice(problem)
        self.assertEqual(
            head,
            'Отрицательный наклон кривой совокупного спроса не объясняется '
            'эффектом:')
        self.assertEqual(options, ['реального богатства', 'процентной ставки',
                                   'дохода', 'импортных закупок'])
        self.assertEqual(positions, [2])

    def test_wrapped_option_line_is_glued_to_previous(self):
        problem = make(
            'Вопрос про эластичность:\n\nВарианты ответа:\n\n'
            '1. спрос эластичен по цене\n   и это устойчиво\n2. спрос неэластичен\n',
            '2. спрос неэластичен')
        _, options, _ = inline_choice(problem)
        self.assertEqual(options[0], 'спрос эластичен по цене и это устойчиво')

    def test_broken_numbering_is_refused(self):
        # Дыра в нумерации значит, что за варианты принято что-то другое.
        problem = make('Вопрос\n\nВарианты ответа:\n\n1. первое\n3. третье\n',
                       '1. первое')
        self.assertEqual(inline_choice(problem), (None, None, None))

    def test_no_marker_means_no_inline_options(self):
        problem = make('Обычное условие без вариантов.', '5')
        self.assertEqual(inline_choice(problem), (None, None, None))


class InlineExtractorTests(TestCase):

    def test_single_is_extracted_and_question_hides_options(self):
        problem = make(SINGLE, '3. дохода')
        question, options, correct, reason = extract_question(problem)
        self.assertIsNone(reason)
        self.assertEqual(correct, 2)
        self.assertEqual(len(options), 4)
        # Вопрос обязан не содержать сами варианты: иначе ответ виден в тексте.
        self.assertNotIn('Варианты ответа', question)
        self.assertNotIn('импортных закупок', question)

    def test_single_without_answer_is_rejected(self):
        problem = make(SINGLE, '')
        _, _, _, reason = extract_question(problem)
        self.assertEqual(reason, 'правильный ответ не определён')

    def test_single_with_two_answers_is_rejected(self):
        # Два номера в ответе у «одного верного» это противоречие, не выбор.
        problem = make(SINGLE, '1. реального богатства\n3. дохода')
        _, _, _, reason = extract_question(problem)
        self.assertEqual(reason, 'правильный ответ не определён')

    def test_multi_collects_every_named_option(self):
        problem = make(MULTI,
                       '1. цена выше предельных издержек\n'
                       '2. выпуск ниже конкурентного',
                       problem_type='тест: все верные')
        question, options, indices, reason = extract_multi(problem)
        self.assertIsNone(reason)
        self.assertEqual(indices, [0, 1])
        self.assertEqual(len(options), 3)
        self.assertNotIn('горизонтальна', question)

    def test_boolean_without_parts_reads_answer_word(self):
        problem = make('Монополия всегда получает положительную прибыль.',
                       'Неверно', problem_type='тест: верно/неверно')
        question, correct, reason = extract_boolean(problem)
        self.assertIsNone(reason)
        self.assertEqual(correct, 1)
        self.assertEqual(question,
                         'Монополия всегда получает положительную прибыль.')

    def test_boolean_without_parts_and_odd_answer_falls_back(self):
        problem = make('Утверждение про рынок труда.', 'скорее верно',
                       problem_type='тест: верно/неверно')
        _, _, reason = extract_boolean(problem)
        self.assertEqual(reason, BOOLEAN_FALLBACK)


class ParityWithParts(TestCase):
    u"""Путь подпунктов обязан работать как раньше: это Сборник АА."""

    def build(self, answer='б'):
        problem = Problem.objects.create(
            title='', statement='Что из перечисленного относится к активам?',
            answer=answer, problem_type='тест: один ответ', status='published')
        for order, (label, text) in enumerate(
                [('а', 'кредит банка'), ('б', 'станок'), ('в', 'налог')]):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement=text, answer='', order=order)
        return problem

    def test_parts_path_still_wins_over_inline(self):
        problem = self.build()
        question, options, correct, reason = extract_question(problem)
        self.assertIsNone(reason)
        self.assertEqual(correct, 1)
        self.assertEqual(options, ['кредит банка', 'станок', 'налог'])
        # Вопрос берётся целиком из statement, как и до правки.
        self.assertEqual(question, 'Что из перечисленного относится к активам?')

    def test_parts_path_still_rejects_unknown_answer_letter(self):
        problem = self.build(answer='я')
        _, _, _, reason = extract_question(problem)
        self.assertEqual(reason, 'правильный ответ не определён')
