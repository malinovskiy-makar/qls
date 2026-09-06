u"""
Тесты слепой перепроверки ответов моделью.

Инварианты, ради которых они написаны:
- наружу не уходит правильный ответ (иначе проверка бессмысленна);
- сравнение точное и по той же функции, что сверяет ввод игрока;
- спорный неразобранный ответ держится ВНЕ игрового пула;
- разбор возвращает задачу в пул и помечает брак штатным вердиктом;
- ни один шаг не трогает `answer` и `solution`.
"""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from game.models import GameQuestion
from problems.models import (AnswerSecondOpinion, Problem, ProblemPart,
                             ReviewVerdict)
from problems.management.commands import answer_second_opinion as aso


def make_problem(**kw):
    defaults = dict(
        title=u'Т', statement=u'Спрос вырос. Что будет с ценой?',
        answer=u'а', solution=u'Решение: цена вырастет.',
        problem_type=u'тест: один ответ', status=Problem.Status.PUBLISHED)
    defaults.update(kw)
    return Problem.objects.create(**defaults)


class BlindRequestTests(TestCase):
    u"""Что уходит модели."""

    def test_answer_never_leaves(self):
        text = aso.user_text(u'Что будет с ценой?',
                             [u'вырастет', u'упадёт'], 'single')
        self.assertIn(u'вырастет', text)
        self.assertNotIn(u'ПРАВИЛЬНЫЙ', text.upper())
        self.assertIn(u'ФОРМА ОТВЕТА', text)

    def test_form_depends_on_type(self):
        self.assertIn(u'одно число',
                      aso.user_text(u'?', [], 'numeric'))
        self.assertIn(u'ВСЕХ верных',
                      aso.user_text(u'?', ['а', 'б'], 'multi'))


class ComparisonTests(TestCase):
    u"""Сравнение ответов — кодом, не глазами."""

    def test_single_index(self):
        self.assertEqual(aso.parse_model_answer('2', 'single',
                                                ['а', 'б', 'в']), 1)

    def test_multi_is_a_set_and_order_does_not_matter(self):
        self.assertEqual(aso.parse_model_answer('3,1', 'multi',
                                                ['а', 'б', 'в']),
                         frozenset([0, 2]))

    def test_numeric_uses_the_players_parser(self):
        u"""0,5 = 0.5 = 1/2 — как и при вводе игрока."""
        from fractions import Fraction
        for text in ('0,5', '0.5', '1/2'):
            self.assertEqual(
                aso.parse_model_answer(text, 'numeric', []),
                Fraction(1, 2), text)

    def test_garbage_is_not_an_answer(self):
        u"""Мусор — это «не разобрал», а не «не сошлось»: иначе каждая
        сорвавшаяся генерация выглядела бы как ошибка банка."""
        self.assertIsNone(aso.parse_model_answer(u'не знаю', 'single',
                                                 ['а', 'б']))
        self.assertIsNone(aso.parse_model_answer('', 'numeric', []))
        self.assertIsNone(aso.parse_model_answer('9', 'single', ['а', 'б']))


class ApplyTests(TestCase):
    u"""Запись мнений и её последствия."""

    def setUp(self):
        self.problem = make_problem()
        for label, ans in ((u'а', u'верно'), (u'б', u'')):
            ProblemPart.objects.create(problem=self.problem, label=label,
                                       statement=u'вариант ' + label,
                                       answer=ans)
        self.gq = GameQuestion.objects.create(
            problem=self.problem, question_type='single',
            question=u'Что будет с ценой?',
            options=[u'вырастет', u'упадёт'], correct_index=0,
            lang='ru', topics=[])

    def _results_file(self, answer, confidence=0.9):
        path = os.path.join(tempfile.mkdtemp(), 'res.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'results': {str(self.gq.id): {
                'answer': answer, 'confidence': confidence}}}, fh)
        return path

    def test_agreement_is_recorded_and_does_not_hide_the_question(self):
        call_command('answer_second_opinion', '--apply',
                     self._results_file('1'), stdout=StringIO())
        op = AnswerSecondOpinion.objects.get()
        self.assertTrue(op.agrees)
        call_command('build_game_pool', verbosity=0)
        self.assertEqual(GameQuestion.objects.filter(
            problem=self.problem).count(), 1)

    def test_dispute_keeps_the_question_out_of_the_pool(self):
        u"""Неверный ключ бьёт молча: задача выглядит безупречно, а жизнь
        снимается за верный ответ. До разбора её в игре быть не должно."""
        call_command('answer_second_opinion', '--apply',
                     self._results_file('2'), stdout=StringIO())
        op = AnswerSecondOpinion.objects.get()
        self.assertFalse(op.agrees)
        call_command('build_game_pool', verbosity=0)
        self.assertEqual(GameQuestion.objects.filter(
            problem=self.problem, is_generated=False).count(), 0)

    def test_unparsed_answer_is_not_a_dispute(self):
        u"""Сорвавшаяся генерация не должна выглядеть как ошибка банка.

        Без этой проверки снятый предохранитель превращал бы каждый
        неразобранный ответ в расхождение — и выкидывал бы из игры
        совершенно исправную задачу."""
        call_command('answer_second_opinion', '--apply',
                     self._results_file(u'затрудняюсь ответить'),
                     stdout=StringIO())
        self.assertEqual(AnswerSecondOpinion.objects.count(), 0)
        call_command('build_game_pool', verbosity=0)
        self.assertEqual(GameQuestion.objects.filter(
            problem=self.problem, is_generated=False).count(), 1)

    def test_texts_are_untouched(self):
        before = (self.problem.statement, self.problem.answer,
                  self.problem.solution)
        call_command('answer_second_opinion', '--apply',
                     self._results_file('2'), stdout=StringIO())
        self.problem.refresh_from_db()
        self.assertEqual((self.problem.statement, self.problem.answer,
                          self.problem.solution), before)


class DisputeReviewTests(TestCase):
    u"""Разбор расхождений ревьюером."""

    def setUp(self):
        self.problem = make_problem()
        self.gq = GameQuestion.objects.create(
            problem=self.problem, question_type='single',
            question=u'Вопрос?', options=[u'а', u'б'], correct_index=0,
            lang='ru', topics=[])
        self.op = AnswerSecondOpinion.objects.create(
            problem=self.problem, model='claude-sonnet-5',
            model_answer='2', bank_answer='0', agrees=False,
            confidence=0.9)

    def _verdict_file(self, value):
        path = os.path.join(tempfile.mkdtemp(), 'v.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'format': 'qls-answer-disputes-v1',
                       'bundle': 'answers_test',
                       'verdicts': {str(self.problem.id): value}}, fh)
        return path

    def test_dry_run_writes_nothing(self):
        call_command('answer_dispute_review', '--import',
                     self._verdict_file('bank_right'), stdout=StringIO())
        self.op.refresh_from_db()
        self.assertFalse(self.op.resolved)

    def test_bank_right_returns_the_question_to_the_pool(self):
        call_command('answer_dispute_review', '--import',
                     self._verdict_file('bank_right'), '--apply',
                     stdout=StringIO())
        self.op.refresh_from_db()
        self.assertTrue(self.op.resolved)
        self.assertEqual(self.op.resolution, 'bank_right')
        self.assertEqual(ReviewVerdict.objects.count(), 0)

    def test_model_right_files_a_standard_verdict(self):
        u"""Второго механизма пометки брака не заводим: дальше работает
        обычный human_review_mark."""
        call_command('answer_dispute_review', '--import',
                     self._verdict_file('model_right'), '--apply',
                     '--reviewer', 'anich', stdout=StringIO())
        verdict = ReviewVerdict.objects.get()
        self.assertEqual(verdict.category, 'wrong_answer')
        self.assertEqual(verdict.reviewer, 'anich')
        self.problem.refresh_from_db()
        self.assertEqual(self.problem.answer, u'а')   # ответ НЕ переписан

    def test_unknown_verdict_is_refused(self):
        with self.assertRaises(CommandError):
            call_command('answer_dispute_review', '--import',
                         self._verdict_file('кто_знает'), '--apply',
                         stdout=StringIO())

    def test_foreign_format_is_refused(self):
        path = os.path.join(tempfile.mkdtemp(), 'v.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'format': 'qls-review-verdicts-v3', 'verdicts': {}}, fh)
        with self.assertRaises(CommandError):
            call_command('answer_dispute_review', '--import', path,
                         '--apply', stdout=StringIO())

    def test_export_makes_a_page_with_both_answers(self):
        out = tempfile.mkdtemp()
        call_command('answer_dispute_review', '--export', '--out', out,
                     '--bundle', 'b1', stdout=StringIO())
        with open(os.path.join(out, 'b1.html'), encoding='utf-8') as fh:
            html = fh.read()
        self.assertIn(u'ответ банка', html)
        self.assertIn(u'ответ модели', html)
        self.assertIn(u'Прав банк', html)
