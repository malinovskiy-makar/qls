# -*- coding: utf-8 -*-
u"""Типизация тестов: команда classify_test_types.

Что здесь сторожится:

1. Команда НЕ ТРОГАЕТ содержание. Пишется одно поле problem_type, а
   statement, answer и solution обязаны остаться байт в байт теми же.
   Это запрет P0 корневого CLAUDE.md, и цена нарушения известна: свип
   Батча 2 испортил 233 поля в 195 задачах.
2. Откат возвращает прежнее значение поля, включая пустое.
3. Полноценная задача с подпунктами типа НЕ получает. На этой ловушке
   эвристика прошлой сессии насчитала 3 366 «тестов» там, где их 2 730.
4. Голое число в ответе тестом задачу не делает.
5. Расхождение сигналов не пишется никогда.

Зубастость. Каждый тест устроен так, чтобы покраснеть при снятии правила:
проверка содержания сравнивает хэши ВСЕХ трёх полей у ВСЕХ задач набора,
а не одной; ловушка подпунктов проверяется вместе с задачей-двойником,
которая тип получить обязана, иначе тест был бы зелёным и у команды,
которая не пишет вообще ничего.
"""
import hashlib
import json
import os
import tempfile

from django.test import TestCase

from problems.management.commands.classify_test_types import (
    B_DISPUTED, B_FULL_PROBLEM, T_ALL, T_BOOL, T_NUM, T_ONE,
    Command, combine, looks_like_subtasks, signal_content,
    solvehub_signal, split_inline_options,
)
from problems.models import Problem, Source, SourceReference

SOURCE_NAME = 'SolveHub — банк задач по экономике'


def fingerprint(problem):
    u"""Отпечаток содержания задачи: три поля, которые трогать запрещено."""
    raw = u'\x00'.join([problem.statement or '', problem.answer or '',
                        problem.solution or ''])
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


class ClassifyTestTypesBase(TestCase):

    def setUp(self):
        self.source = Source.objects.create(name=SOURCE_NAME)
        self.command = Command()

    def make(self, key, statement, answer, solution='', problem_type=''):
        problem = Problem.objects.create(
            title=statement[:60], statement=statement, answer=answer,
            solution=solution, problem_type=problem_type,
            status=Problem.Status.PUBLISHED)
        SourceReference.objects.create(problem=problem, source=self.source,
                                       problem_number=key)
        return problem

    @staticmethod
    def passport(is_test, check_type):
        return {'is_test': is_test, 'check_type': check_type, 'title': ''}


class ContentSignalTests(ClassifyTestTypesBase):
    u"""Сигнал 2 разбирает то, что лежит в банке."""

    def test_inline_options_block_is_parsed(self):
        question, options = split_inline_options(
            'Что из перечисленного верно?\n\n'
            'Варианты ответа:\n\n1. первое\n2. второе\n3. третье')
        self.assertEqual(question, 'Что из перечисленного верно?')
        self.assertEqual(options, ['первое', 'второе', 'третье'])

    def test_broken_numbering_is_refused(self):
        # Дыра в нумерации значит, что за варианты принято что-то другое.
        _, options = split_inline_options(
            'Вопрос\n\nВарианты ответа:\n\n1. первое\n3. третье')
        self.assertIsNone(options)

    def test_single_choice_recognised(self):
        problem = self.make(
            'k1',
            'Кривая спроса имеет отрицательный наклон из-за эффекта:\n\n'
            'Варианты ответа:\n\n1. дохода\n2. замещения\n3. богатства',
            '2. замещения')
        verdict, _ = signal_content(problem)
        self.assertEqual(verdict, T_ONE)

    def test_multiple_choice_recognised(self):
        problem = self.make(
            'k2',
            'Выберите все верные утверждения:\n\n'
            'Варианты ответа:\n\n1. первое\n2. второе\n3. третье',
            '1. первое\n3. третье')
        verdict, _ = signal_content(problem)
        self.assertEqual(verdict, T_ALL)

    def test_true_false_recognised(self):
        problem = self.make('k3', 'Монополия всегда получает прибыль.', 'Неверно')
        verdict, _ = signal_content(problem)
        self.assertEqual(verdict, T_BOOL)


class SubtaskTrapTests(ClassifyTestTypesBase):
    u"""Ловушка: полноценная задача с подпунктами это не тест."""

    SUBTASKS = (
        'Фирма работает на рынке совершенной конкуренции.\n\n'
        'а) Выведите функцию предложения фирмы.\n'
        'б) Найдите равновесную цену.\n')

    def test_subtask_problem_is_not_a_test(self):
        problem = self.make('s1', self.SUBTASKS, '4')
        self.assertTrue(looks_like_subtasks(problem))
        verdict, _ = signal_content(problem)
        self.assertEqual(verdict, B_FULL_PROBLEM)

    def test_subtask_problem_gets_no_type_end_to_end(self):
        u"""Задача с подпунктами и тест-двойник в одном прогоне.

        Двойник обязателен: без него тест был бы зелёным и у команды,
        которая просто ничего не пишет.
        """
        trap = self.make('s1', self.SUBTASKS, '4')
        real = self.make(
            's2',
            'Что из перечисленного относится к инвестициям?\n\n'
            'Варианты ответа:\n\n1. покупка станка\n2. покупка акции\n'
            '3. выплата зарплаты',
            '1. покупка станка')
        raw = {
            's1': self.passport(False, 'single_freetext'),
            's2': self.passport(True, 'single_choice'),
        }
        items = self.command.analyse(
            self.source, raw,
            {'signal': solvehub_signal,
             'key': lambda p, sid: p.source_references.first().problem_number,
             'mode': 'classify'})
        by_id = {item['problem'].id: item['final'] for item in items}
        self.assertEqual(by_id[trap.id], B_FULL_PROBLEM)
        self.assertEqual(by_id[real.id], T_ONE)

    def test_lettered_options_without_imperative_are_not_subtasks(self):
        # «а)» само по себе задачей не делает: у теста тоже бывают буквы.
        problem = self.make(
            's3',
            'Верно ли утверждение?\n\nВарианты ответа:\n\n1. Верно\n2. Неверно',
            '1. Верно')
        self.assertFalse(looks_like_subtasks(problem))


class NumericVerdictTests(ClassifyTestTypesBase):
    u"""Число в ответе тестом задачу не делает."""

    def test_numeric_content_alone_does_not_override_source(self):
        # Источник говорит «полноценная задача», содержимое видит число.
        # Спором это не считается, и тип не пишется.
        final, _ = combine(B_FULL_PROBLEM, T_NUM)
        self.assertEqual(final, B_FULL_PROBLEM)

    def test_numeric_claim_against_source_is_never_written(self):
        problem = self.make('n1', 'Посчитайте выручку фирмы при Q равном 10.', '4')
        verdict, _ = signal_content(problem)
        self.assertEqual(verdict, T_NUM)
        raw = {'n1': self.passport(False, 'single_freetext')}
        items = self.command.analyse(
            self.source, raw,
            {'signal': solvehub_signal,
             'key': lambda p, sid: 'n1', 'mode': 'classify'})
        self.assertEqual(items[0]['final'], B_FULL_PROBLEM)
        self.assertNotIn(items[0]['final'], (T_NUM,))


class DisagreementTests(ClassifyTestTypesBase):
    u"""Расхождение сигналов не пишется никогда."""

    def test_source_type_unconfirmed_by_content_is_disputed(self):
        final, _ = combine(T_BOOL, T_ONE)
        self.assertEqual(final, B_DISPUTED)
        final, _ = combine(T_ONE, B_FULL_PROBLEM)
        self.assertEqual(final, B_DISPUTED)

    def test_content_type_against_source_is_disputed(self):
        final, _ = combine(B_FULL_PROBLEM, T_ONE)
        self.assertEqual(final, B_DISPUTED)

    def test_agreement_is_written(self):
        final, _ = combine(T_BOOL, T_BOOL)
        self.assertEqual(final, T_BOOL)

    def test_multichoice_with_single_correct_is_written_as_multi(self):
        # Решение владельца: формат задаёт источник, один верный вариант
        # в мультивыборе законен.
        final, _ = combine(T_ALL, T_ONE)
        self.assertEqual(final, T_ALL)

    def test_reverse_direction_is_still_disputed(self):
        # Обратное направление исключением не является: источник назвал
        # одиночный выбор, а ответов несколько, и это противоречие.
        final, _ = combine(T_ONE, T_ALL)
        self.assertEqual(final, B_DISPUTED)


class WriteAndRevertTests(ClassifyTestTypesBase):
    u"""Боевая запись, неприкосновенность содержания и откат."""

    def build(self):
        u"""Набор из четырёх задач: две пишутся, две нет."""
        self.one = self.make(
            'w1',
            'Что относится к инвестициям?\n\nВарианты ответа:\n\n'
            '1. станок\n2. акция\n3. зарплата',
            '1. станок', solution='Решение первое.')
        self.boolean = self.make(
            'w2', 'Монополия всегда получает прибыль.', 'Неверно',
            solution='Решение второе.', problem_type='старое значение')
        self.trap = self.make(
            'w3',
            'Фирма на рынке.\n\nа) Выведите функцию.\nб) Найдите цену.\n',
            '7', solution='Решение третье.')
        # Обратное направление исключения про мультивыбор: источник назвал
        # одиночный выбор, а ответов оказалось два. Это противоречие, и
        # запись не делается.
        self.disputed = self.make(
            'w4',
            'Что из перечисленного верно:\n\nВарианты ответа:\n\n'
            '1. первое\n2. второе\n3. третье',
            '1. первое\n2. второе', solution='Решение четвёртое.')
        return {
            'w1': self.passport(True, 'single_choice'),
            'w2': self.passport(True, 'true_false'),
            'w3': self.passport(False, 'single_freetext'),
            'w4': self.passport(True, 'single_choice'),
        }

    def analyse(self, raw):
        return self.command.analyse(
            self.source, raw,
            {'signal': solvehub_signal,
             'key': lambda p, sid: p.source_references.first().problem_number,
             'mode': 'classify'})

    def test_confirm_writes_only_agreed_and_keeps_content_intact(self):
        raw = self.build()
        every = list(Problem.objects.order_by('id'))
        before = {p.id: fingerprint(p) for p in every}

        with tempfile.TemporaryDirectory() as folder:
            journal = os.path.join(folder, 'applied.json')
            changed, planned = self.command.do_confirm(self.analyse(raw), journal)

            self.assertEqual(changed, 2)
            self.assertEqual(planned, 2)

            # Содержание не тронуто ни у одной задачи набора.
            for problem in Problem.objects.order_by('id'):
                self.assertEqual(fingerprint(problem), before[problem.id],
                                 'изменилось содержание задачи %d' % problem.id)

            self.one.refresh_from_db()
            self.boolean.refresh_from_db()
            self.trap.refresh_from_db()
            self.disputed.refresh_from_db()
            self.assertEqual(self.one.problem_type, T_ONE)
            self.assertEqual(self.boolean.problem_type, T_BOOL)
            self.assertEqual(self.trap.problem_type, '')
            self.assertEqual(self.disputed.problem_type, '')

            with open(journal, encoding='utf-8') as fh:
                saved = json.load(fh)
            self.assertEqual(saved[str(self.boolean.id)]['before'],
                             'старое значение')
            self.assertEqual(saved[str(self.one.id)]['before'], '')

    def test_revert_restores_previous_values(self):
        raw = self.build()
        with tempfile.TemporaryDirectory() as folder:
            journal = os.path.join(folder, 'applied.json')
            self.command.do_confirm(self.analyse(raw), journal)
            restored, total = self.command.do_revert(journal)

            self.assertEqual(restored, 2)
            self.assertEqual(total, 2)
            self.one.refresh_from_db()
            self.boolean.refresh_from_db()
            # Пустое значение возвращается пустым, а не остаётся типом.
            self.assertEqual(self.one.problem_type, '')
            self.assertEqual(self.boolean.problem_type, 'старое значение')

    def test_confirm_is_idempotent(self):
        raw = self.build()
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, 'first.json')
            second = os.path.join(folder, 'second.json')
            self.command.do_confirm(self.analyse(raw), first)
            changed, planned = self.command.do_confirm(self.analyse(raw), second)
            # Второй прогон обязан не менять ничего.
            self.assertEqual(changed, 0)
            self.assertEqual(planned, 2)
