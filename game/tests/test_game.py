"""
Тесты Econ Rush: отборщик пула (парсинг) + API забега (анти-чит, повторы).
"""
import json

from django.test import TestCase, Client

from problems.models import Problem, ProblemPart
from game.models import GameQuestion
from game.management.commands.build_game_pool import extract_question
from game.config import combo_multiplier


def make_test_problem(statement='Что изучает микроэкономика?',
                      answer='A', labels=('A', 'B', 'C', 'D'),
                      options=('Фирмы', 'Страны', 'Планеты', 'Климат'),
                      marks=None, problem_type='тест: один ответ'):
    """Собирает Problem с подпунктами-вариантами как в реальном импорте."""
    p = Problem.objects.create(
        title='', statement=statement, answer=answer,
        problem_type=problem_type, status='published')
    for i, (label, text) in enumerate(zip(labels, options)):
        mark = ''
        if marks:
            mark = marks[i]
        ProblemPart.objects.create(problem=p, label=label, statement=text,
                                   answer=mark, order=i)
    return p


class ExtractQuestionTests(TestCase):
    """Отборщик пула: валидные и невалидные кейсы парсинга."""

    def test_valid_by_label(self):
        # правильный ответ определяется буквой из Problem.answer
        p = make_test_problem(answer='C')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertEqual(correct, 2)
        self.assertEqual(len(opts), 4)

    def test_valid_by_mark(self):
        # правильный ответ определяется меткой «верно» в подпункте
        p = make_test_problem(answer='', marks=['', 'верно', '', ''])
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertEqual(correct, 1)

    def test_conflict_signals_rejected(self):
        # буква говорит A, метка «верно» стоит на B — брак, не гадаем
        p = make_test_problem(answer='A', marks=['', 'верно', '', ''])
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'конфликт сигналов правильного ответа')

    def test_no_correct_rejected(self):
        p = make_test_problem(answer='')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'правильный ответ не определён')

    def test_long_statement_rejected(self):
        p = make_test_problem(statement='Ы' * 301)
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'условие длиннее 300')

    def test_figure_reference_rejected(self):
        p = make_test_problem(statement='Определите по графику ниже равновесную цену.')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'нужен рисунок/таблица')

    def test_broken_latex_rejected(self):
        p = make_test_problem(statement=r'Что тут: \begin{itemize} мусор?')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'битый LaTeX / вёрстка')

    def test_unbalanced_dollars_rejected(self):
        p = make_test_problem(statement='Цена $P растет. Что дальше?')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'непарные $')

    def test_newlines_collapsed(self):
        # PDF-нарезка склеивается в одну строку
        p = make_test_problem(statement='Что изучает\nмикроэкономика,  а?')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertEqual(q, 'Что изучает микроэкономика, а?')

    def test_label_normalization_like_student_check(self):
        # нормализация меток та же, что в автопроверке ученика: «а)» == «А»
        p = make_test_problem(answer='б)', labels=('а', 'б'),
                              options=('Верно', 'Неверно'),
                              problem_type='тест: верно/неверно')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertEqual(correct, 1)

    # ---- Баг 1: display-формулы на карточке ----

    def test_simple_display_formula_becomes_inline(self):
        # $$...$$ без высоких конструкций сжимается в строчный режим,
        # иначе на карточке текст рвётся вокруг формулы
        p = make_test_problem(statement='Функция спроса $$Q = 100 - P$$ дана нам.')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertNotIn('$$', q)
        self.assertIn('$Q = 100 - P$', q)

    def test_dfrac_converted_to_frac_even_inline(self):
        # \dfrac форсирует display-style дробь даже внутри строчной формулы
        p = make_test_problem(statement=r'Цена равна $P = \dfrac{a}{b}$, найдите Q.')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertNotIn('dfrac', q)
        self.assertIn(r'\frac{a}{b}', q)

    def test_tall_formula_with_cases_stays_display(self):
        # \begin{cases} — высокая конструкция, не сжимаем, но и не бракуем
        stmt = (r'Издержки заданы \[TC(q) = \begin{cases} 0, & q=0; \\ '
                r'5q, & q>0; \end{cases}\] Что верно про издержки фирмы?')
        p = make_test_problem(statement=stmt, answer='A')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertIn(r'\begin{cases}', q)
        self.assertIn(r'\[', q)

    def test_unsupported_environment_rejected(self):
        # \begin{tabular} — не математическое окружение, по-прежнему брак
        p = make_test_problem(
            statement=r'Смотри \begin{tabular}{c} X \end{tabular} тут для ответа.')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'битый LaTeX / вёрстка')

    def test_array_with_hline_table_rejected(self):
        # \begin{array} + \hline — визуальная таблица, а не система уравнений
        p = make_test_problem(
            statement=r'Данные: $$\begin{array}{|c|c|}\hline A & B \\\hline\end{array}$$ '
                      r'Что выбрать?')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'битый LaTeX / вёрстка')

    # ---- Баг 2: огрызки меток в начале/конце вопроса ----

    def test_orphaned_closing_paren_stripped(self):
        p = make_test_problem(
            statement=') Коэффициент эластичности суммы налоговых сборов положителен.')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertTrue(q.startswith('Коэффициент'), q)

    def test_leading_letter_label_stripped(self):
        p = make_test_problem(statement='б) Коэффициент эластичности равен единице?')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertTrue(q.startswith('Коэффициент'), q)

    def test_trailing_open_paren_stripped(self):
        p = make_test_problem(statement='Определите равновесную цену на рынке (')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertFalse(q.endswith('('), q)

    def test_option_leading_digit_not_mistaken_for_label(self):
        # у вариантов ведущая цифра часто настоящее число («-$1400», «0.75%») —
        # чистку меток к ним не применяем вовсе (см. extract_question)
        p = make_test_problem(options=(r'-\$1400', '0.75%', '4.0', '10.0%'))
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertIn(r'-\$1400', opts)
        self.assertIn('0.75%', opts)


class ComboTests(TestCase):
    def test_combo_multiplier_steps(self):
        self.assertEqual([combo_multiplier(s) for s in (0, 1, 2, 3, 5, 6, 8, 9, 20)],
                         [1, 1, 1, 2, 2, 3, 3, 4, 4])


class GameApiTests(TestCase):
    """API забега: анти-чит, повторный ответ, несуществующий id."""

    def setUp(self):
        self.client = Client()
        for i in range(6):
            p = make_test_problem(statement=f'Вопрос номер {i}?', answer='A')
            GameQuestion.objects.create(
                problem=p, question=p.statement,
                options=['Фирмы', 'Страны', 'Планеты', 'Климат'],
                correct_index=0, difficulty=2, topics=[], lang='ru')

    def start(self):
        r = self.client.get('/game/api/session/start/')
        self.assertEqual(r.status_code, 200)
        return r.json()['question']

    def test_question_payload_has_no_correct_index(self):
        q = self.start()
        self.assertNotIn('correct_index', q)
        self.assertNotIn('correct', json.dumps(q))
        r = self.client.get('/game/api/question/')
        self.assertNotIn('correct_index', json.dumps(r.json()['question']))

    def test_answer_correct_and_wrong(self):
        q = self.start()
        r = self.client.post('/game/api/answer/',
                             json.dumps({'question_id': q['id'], 'choice': 0}),
                             content_type='application/json')
        d = r.json()
        self.assertTrue(d['correct'])
        self.assertEqual(d['correct_index'], 0)
        self.assertEqual(d['time_delta'], 5)   # блиц (режим по умолчанию)
        # следующий вопрос — неверный ответ
        q2 = self.client.get('/game/api/question/').json()['question']
        d2 = self.client.post('/game/api/answer/',
                              json.dumps({'question_id': q2['id'], 'choice': 2}),
                              content_type='application/json').json()
        self.assertFalse(d2['correct'])
        self.assertEqual(d2['time_delta'], -5)

    def test_skip(self):
        q = self.start()
        d = self.client.post('/game/api/answer/',
                             json.dumps({'question_id': q['id'], 'choice': None}),
                             content_type='application/json').json()
        self.assertEqual(d['result'], 'skip')
        self.assertEqual(d['time_delta'], -3)  # блиц (режим по умолчанию)

    def test_repeat_answer_409(self):
        q = self.start()
        self.client.post('/game/api/answer/',
                         json.dumps({'question_id': q['id'], 'choice': 0}),
                         content_type='application/json')
        r = self.client.post('/game/api/answer/',
                             json.dumps({'question_id': q['id'], 'choice': 1}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 409)

    def test_unknown_question_404(self):
        self.start()
        r = self.client.post('/game/api/answer/',
                             json.dumps({'question_id': 999999, 'choice': 0}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_answer_without_session_400(self):
        r = self.client.post('/game/api/answer/',
                             json.dumps({'question_id': 1, 'choice': 0}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_no_repeats_and_exhaustion(self):
        seen = {self.start()['id']}
        for _ in range(6):
            d = self.client.get('/game/api/question/').json()
            if d.get('exhausted'):
                break
            self.assertNotIn(d['question']['id'], seen)
            seen.add(d['question']['id'])
        self.assertEqual(len(seen), 6)          # весь пул выдан без повторов
        d = self.client.get('/game/api/question/').json()
        self.assertTrue(d.get('exhausted'))     # и корректно исчерпан

    def test_bad_topic_400(self):
        r = self.client.get('/game/api/session/start/', {'topic': 'Нет такой'})
        self.assertEqual(r.status_code, 400)
