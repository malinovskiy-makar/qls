"""
Тесты Econ Rush: отборщики пула (парсинг), API забега (анти-чит, повторы),
четыре режима (типы вопросов, проверка multi/numeric, «сначала невиданные»).
"""
import json
from fractions import Fraction

from django.test import TestCase, Client

from problems.models import Problem, ProblemPart, Source, SourceReference
from game.models import GameQuestion
from game.management.commands.build_game_pool import (
    extract_question, extract_boolean, extract_multi, extract_numeric)
from game.config import combo_multiplier, MODES
from game.views import parse_exact_number


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


def make_gq(qtype='single', question='Что изучает микроэкономика?',
            options=None, correct_index=None, correct_indices=None,
            correct_value='', lang='ru'):
    """Готовый GameQuestion нужного типа (пул — кэш, парсинг не обязателен)."""
    p = Problem.objects.create(
        title='', statement=question, answer='',
        problem_type='тест: один ответ', status='published')
    if options is None:
        options = {'boolean': ['Верно', 'Неверно'],
                   'numeric': []}.get(qtype, ['Фирмы', 'Страны', 'Планеты', 'Климат'])
    return GameQuestion.objects.create(
        problem=p, question_type=qtype, question=question, options=options,
        correct_index=correct_index, correct_indices=correct_indices,
        correct_value=correct_value, difficulty=2, topics=[], lang=lang)


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

    # ---- Баг 1 (game-modes-9): 6 вариантов и склеенные опции ----

    def test_six_options_accepted(self):
        # олимпиадные тесты бывают а-е — 6 вариантов не должны бракова́ться
        p = make_test_problem(
            answer='F', labels=('A', 'B', 'C', 'D', 'E', 'F'),
            options=('Один', 'Два', 'Три', 'Четыре', 'Пять', 'Шесть'))
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)
        self.assertEqual(len(opts), 6)
        self.assertEqual(correct, 5)

    def test_seven_options_rejected(self):
        p = make_test_problem(
            answer='G', labels=('A', 'B', 'C', 'D', 'E', 'F', 'G'),
            options=('1', '2', '3', '4', '5', '6', '7'))
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'вариантов не 2–6')

    def test_glued_option_rejected(self):
        # вариант, внутри которого не в начале приклеена метка следующего
        # варианта — импорт склеил два подпункта в один (Баг 1б)
        p = make_test_problem(
            answer='A',
            options=('Цена ниже конкурентного уровня д) Фирмы могут '
                     'свободно входить на рынок', 'Страны', 'Планеты', 'Климат'))
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'glued_options')


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


class ExtractBooleanTests(TestCase):
    """Извлекатель данеток: утверждение в statement, варианты Верно/Неверно."""

    def test_converted_one_to_one(self):
        p = make_test_problem(
            statement='Большинство макроэкономических переменных ацикличны.',
            answer='б', labels=('а', 'б'), options=('Верно', 'Неверно'),
            problem_type='тест: верно/неверно')
        q, correct, reason = extract_boolean(p)
        self.assertIsNone(reason)
        self.assertTrue(q.startswith('Большинство'))
        self.assertEqual(correct, 1)  # «б» → Неверно

    def test_correct_index_canonical_despite_part_order(self):
        # подпункты в задаче идут «Неверно, Верно» — correct_index всё равно
        # в каноническом порядке options=['Верно','Неверно']
        p = make_test_problem(
            statement='Спрос падает при росте цены практически всегда.',
            answer='а', labels=('а', 'б'), options=('Неверно', 'Верно'),
            problem_type='тест: верно/неверно')
        q, correct, reason = extract_boolean(p)
        self.assertIsNone(reason)
        self.assertEqual(correct, 1)  # «а» указывает на текст «Неверно»

    def test_nonstandard_options_fallback(self):
        from game.management.commands.build_game_pool import BOOLEAN_FALLBACK
        p = make_test_problem(
            statement='Забастовка авиадиспетчеров сместила кривую спроса.',
            answer='а', labels=('а', 'б'),
            options=('Верно (можно утверждать)', 'Неверно (нельзя утверждать)'),
            problem_type='тест: верно/неверно')
        q, correct, reason = extract_boolean(p)
        self.assertEqual(reason, BOOLEAN_FALLBACK)

    def test_no_answer_letter_rejected(self):
        p = make_test_problem(
            statement='Инфляция всегда снижает реальные доходы населения.',
            answer='', labels=('а', 'б'), options=('Верно', 'Неверно'),
            problem_type='тест: верно/неверно')
        q, correct, reason = extract_boolean(p)
        self.assertEqual(reason, 'правильный ответ не определён')


class ExtractMultiTests(TestCase):
    """Извлекатель «все верные»: correct_indices из букв Problem.answer."""

    def test_letters_mapped_to_indices(self):
        p = make_test_problem(answer='аг', labels=('а', 'б', 'в', 'г'),
                              problem_type='тест: все верные')
        q, opts, indices, reason = extract_multi(p)
        self.assertIsNone(reason)
        self.assertEqual(indices, [0, 3])

    def test_letters_with_separators(self):
        p = make_test_problem(answer='а, в', labels=('а', 'б', 'в', 'г'),
                              problem_type='тест: все верные')
        q, opts, indices, reason = extract_multi(p)
        self.assertIsNone(reason)
        self.assertEqual(indices, [0, 2])

    def test_six_options_correct_indices(self):
        # 6 вариантов (а-е) должны проходить в пул с верными correct_indices
        p = make_test_problem(
            answer='аге', labels=('а', 'б', 'в', 'г', 'д', 'е'),
            options=('Один', 'Два', 'Три', 'Четыре', 'Пять', 'Шесть'),
            problem_type='тест: все верные')
        q, opts, indices, reason = extract_multi(p)
        self.assertIsNone(reason)
        self.assertEqual(len(opts), 6)
        self.assertEqual(indices, [0, 3, 5])

    def test_unmatched_letter_rejected(self):
        p = make_test_problem(answer='ад', labels=('а', 'б', 'в', 'г'),
                              problem_type='тест: все верные')
        q, opts, indices, reason = extract_multi(p)
        self.assertEqual(reason, 'буква ответа не сопоставилась с меткой')

    def test_empty_answer_rejected(self):
        p = make_test_problem(answer='', labels=('а', 'б', 'в', 'г'),
                              problem_type='тест: все верные')
        q, opts, indices, reason = extract_multi(p)
        self.assertEqual(reason, 'правильный ответ не определён')


def make_numeric_problem(statement='Спрос Q=100-P, предложение Q=P. '
                                   'Найдите равновесную цену.',
                         answer='50'):
    """Problem типа «тест: числовой ответ» — без подпунктов, ответ в answer.
    Формат приедет с импортом региональных тестов ВсОШ."""
    return Problem.objects.create(
        title='', statement=statement, answer=answer,
        problem_type='тест: числовой ответ', status='published')


class ExtractNumericTests(TestCase):
    """Извлекатель numeric (Классика): ответ обязан парситься parse_exact_number."""

    def test_integer_answer(self):
        q, value, reason = extract_numeric(make_numeric_problem(answer='50'))
        self.assertIsNone(reason)
        self.assertIn('равновесную цену', q)
        self.assertEqual(value, '50')

    def test_fraction_and_decimal_kept_verbatim(self):
        # Каноническая запись сохраняется как есть — сверять будет
        # parse_exact_number на стороне игры (1/3 останется дробью).
        for ans in ('1/3', '0,4', '-1.25'):
            q, value, reason = extract_numeric(make_numeric_problem(answer=ans))
            self.assertIsNone(reason, ans)
            self.assertEqual(value, ans)

    def test_unparsable_answer_rejected(self):
        for bad in ('см. решение', '50 руб.', '10%', '1/3/4', ''):
            q, value, reason = extract_numeric(make_numeric_problem(answer=bad))
            self.assertIsNotNone(reason, bad)
        self.assertEqual(
            extract_numeric(make_numeric_problem(answer='нет'))[2],
            'ответ не парсится в число')

    def test_answer_whitespace_stripped(self):
        q, value, reason = extract_numeric(make_numeric_problem(answer='  50 '))
        self.assertIsNone(reason)
        self.assertEqual(value, '50')

    def test_question_quality_rules_apply(self):
        # Общие фильтры качества (длина, рисунок) работают и для numeric —
        # но лимит длины мягче (700, не 300): Классика даёт 600 с на вопрос,
        # расчётные региональные задачи длиннее куцых тестовых вопросов.
        p = make_numeric_problem(statement='На основе графика найдите цену.')
        self.assertEqual(extract_numeric(p)[2], 'нужен рисунок/таблица')
        p = make_numeric_problem(statement='Найдите X. ' * 40)
        self.assertIsNone(extract_numeric(p)[2])
        p = make_numeric_problem(statement='Найдите X. ' * 70)
        self.assertEqual(extract_numeric(p)[2], 'условие длиннее 700')

    def test_overlong_answer_rejected(self):
        p = make_numeric_problem(answer='1' * 51)
        self.assertEqual(extract_numeric(p)[2], 'числовой ответ длиннее 50')


class BuildPoolMetadataTests(TestCase):
    """Полный прогон build_game_pool: numeric попадает в пул, stage/year/grade
    денормализуются во все типы вопросов из SourceReference."""

    @classmethod
    def setUpTestData(cls):
        cls.source = Source.objects.create(
            name='ВсОШ — региональный этап', kind='олимпиада')

    def _run(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('build_game_pool', stdout=StringIO())

    def test_numeric_built_with_metadata(self):
        p = make_numeric_problem(answer='1/3')
        SourceReference.objects.create(
            problem=p, source=self.source, stage='региональный',
            year=2023, grade='11', problem_number='7')
        self._run()
        gq = GameQuestion.objects.get(problem=p)
        self.assertEqual(gq.question_type, 'numeric')
        self.assertEqual(gq.options, [])
        self.assertEqual(gq.correct_value, '1/3')
        self.assertEqual((gq.stage, gq.year, gq.grade),
                         ('региональный', 2023, '11'))

    def test_metadata_denormalized_for_choice_types_too(self):
        p = make_test_problem(answer='A')
        SourceReference.objects.create(
            problem=p, source=self.source, stage='региональный',
            year=2023, grade='9')
        self._run()
        gq = GameQuestion.objects.get(problem=p)
        self.assertEqual(gq.question_type, 'single')
        self.assertEqual((gq.stage, gq.year, gq.grade),
                         ('региональный', 2023, '9'))

    def test_no_reference_means_empty_metadata(self):
        p = make_test_problem(answer='A')
        self._run()
        gq = GameQuestion.objects.get(problem=p)
        self.assertEqual((gq.stage, gq.year, gq.grade), ('', None, ''))

    def test_unparsable_numeric_not_in_pool(self):
        p = make_numeric_problem(answer='зависит от вкусов')
        self._run()
        self.assertFalse(GameQuestion.objects.filter(problem=p).exists())


class ParseExactNumberTests(TestCase):
    """Точный разбор числового ответа (fractions.Fraction)."""

    def test_equivalent_forms(self):
        self.assertEqual(parse_exact_number('0,1'), Fraction(1, 10))
        self.assertEqual(parse_exact_number('0.1'), Fraction(1, 10))
        self.assertEqual(parse_exact_number('1/10'), Fraction(1, 10))
        self.assertEqual(parse_exact_number('-2'), Fraction(-2))
        self.assertEqual(parse_exact_number(' 1 / 3 '), Fraction(1, 3))
        self.assertEqual(parse_exact_number('2/6'), Fraction(1, 3))

    def test_inexact_is_not_equal(self):
        self.assertNotEqual(parse_exact_number('0,33'), parse_exact_number('1/3'))

    def test_garbage_is_none(self):
        for bad in ('abc', '', None, '1/0', '1/3/4', '--2', '1.2.3', '/'):
            self.assertIsNone(parse_exact_number(bad), bad)


class ModeStartTests(TestCase):
    """Старт режимов: типы вопросов, тайминги, 400 на неизвестный режим."""

    def setUp(self):
        self.client = Client()
        for i in range(4):
            make_gq('boolean', f'Утверждение {i} про экономику.', correct_index=0)
            make_gq('single', f'Одиночный вопрос {i}?', correct_index=1)
            make_gq('multi', f'Мульти-вопрос {i}?', correct_indices=[0, 2])
            make_gq('numeric', f'Числовой вопрос {i}?', correct_value='0.1')

    def test_start_each_mode(self):
        for mode in ('bullet', 'blitz', 'rapid', 'classic'):
            d = self.client.get('/game/api/session/start/', {'mode': mode}).json()
            self.assertTrue(d.get('ok'), d)
            self.assertEqual(d['mode']['key'], mode)
            self.assertEqual(d['mode']['duration'], MODES[mode]['duration'])
            self.assertEqual(d['mode']['time_skip'], MODES[mode]['time_skip'])
            self.assertEqual(d['question']['type'], MODES[mode]['question_type'])

    def test_default_mode_is_blitz(self):
        d = self.client.get('/game/api/session/start/').json()
        self.assertEqual(d['mode']['key'], 'blitz')

    def test_unknown_mode_400(self):
        r = self.client.get('/game/api/session/start/', {'mode': 'hyperbullet'})
        self.assertEqual(r.status_code, 400)

    def test_only_needed_type_issued(self):
        d = self.client.get('/game/api/session/start/', {'mode': 'bullet'}).json()
        types = {d['question']['type']}
        for _ in range(5):
            r = self.client.get('/game/api/question/').json()
            if r.get('exhausted'):
                break
            types.add(r['question']['type'])
        self.assertEqual(types, {'boolean'})

    def test_payload_leaks_nothing_in_any_mode(self):
        # строковая проверка: ни correct_index, ни correct_indices,
        # ни correct_value (все содержат подстроку 'correct')
        for mode in ('bullet', 'blitz', 'rapid', 'classic'):
            d = self.client.get('/game/api/session/start/', {'mode': mode}).json()
            self.assertNotIn('correct', json.dumps(d['question']), mode)


class MultiAnswerTests(TestCase):
    """Рапид: засчитывается только полное совпадение множеств."""

    def setUp(self):
        self.client = Client()
        for i in range(3):
            make_gq('multi', f'Мульти-вопрос {i}?', correct_indices=[0, 2])

    def start_and_answer(self, payload):
        d = self.client.get('/game/api/session/start/', {'mode': 'rapid'}).json()
        payload['question_id'] = d['question']['id']
        return self.client.post('/game/api/answer/', json.dumps(payload),
                                content_type='application/json')

    def test_full_match_correct_any_order(self):
        d = self.start_and_answer({'choices': [2, 0]}).json()
        self.assertTrue(d['correct'])
        self.assertEqual(d['time_delta'], MODES['rapid']['time_correct'])
        self.assertEqual(d['correct_indices'], [0, 2])

    def test_partial_subset_wrong(self):
        d = self.start_and_answer({'choices': [0]}).json()
        self.assertFalse(d['correct'])
        self.assertEqual(d['time_delta'], MODES['rapid']['time_wrong'])

    def test_superset_wrong(self):
        d = self.start_and_answer({'choices': [0, 1, 2]}).json()
        self.assertFalse(d['correct'])

    def test_null_choices_is_skip(self):
        d = self.start_and_answer({'choices': None}).json()
        self.assertEqual(d['result'], 'skip')
        self.assertEqual(d['time_delta'], MODES['rapid']['time_skip'])

    def test_out_of_range_400(self):
        r = self.start_and_answer({'choices': [0, 7]})
        self.assertEqual(r.status_code, 400)


class NumericAnswerTests(TestCase):
    """Классика: точное равенство значений через Fraction."""

    def setUp(self):
        self.client = Client()

    def start_and_answer(self, correct_value, given):
        make_gq('numeric', f'Найдите x ({correct_value})?',
                correct_value=correct_value)
        d = self.client.get('/game/api/session/start/', {'mode': 'classic'}).json()
        return self.client.post(
            '/game/api/answer/',
            json.dumps({'question_id': d['question']['id'], 'value': given}),
            content_type='application/json')

    def test_equivalent_forms_correct(self):
        for given in ('0,1', '0.1', '1/10'):
            d = self.start_and_answer('0.1', given).json()
            self.assertTrue(d['correct'], given)
            self.assertEqual(d['time_delta'], MODES['classic']['time_correct'])
            self.assertEqual(d['correct_value'], '0.1')

    def test_inexact_decimal_wrong(self):
        d = self.start_and_answer('1/3', '0,33').json()
        self.assertFalse(d['correct'])
        self.assertEqual(d['time_delta'], MODES['classic']['time_wrong'])

    def test_garbage_input_wrong_without_500(self):
        r = self.start_and_answer('0.1', 'сорок два')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['correct'])

    def test_empty_value_is_skip(self):
        d = self.start_and_answer('0.1', '').json()
        self.assertEqual(d['result'], 'skip')
        self.assertEqual(d['time_delta'], MODES['classic']['time_skip'])


class UnseenBetweenRunsTests(TestCase):
    """«Сначала невиданные»: вопросы не повторяются между забегами,
    пока пул режима не исчерпан; после исчерпания — цикл по кругу."""

    def setUp(self):
        self.client = Client()
        for i in range(6):
            make_gq('boolean', f'Утверждение номер {i} об экономике.',
                    correct_index=0)

    def collect_run(self, n):
        """Стартует забег и собирает id первых n выданных вопросов."""
        ids = [self.client.get('/game/api/session/start/',
                               {'mode': 'bullet'}).json()['question']['id']]
        for _ in range(n - 1):
            d = self.client.get('/game/api/question/').json()
            if d.get('exhausted'):
                break
            ids.append(d['question']['id'])
        return ids

    def test_two_runs_do_not_repeat_until_exhausted(self):
        run1 = self.collect_run(3)
        run2 = self.collect_run(3)
        self.assertEqual(len(run1), 3)
        self.assertEqual(len(run2), 3)
        self.assertFalse(set(run1) & set(run2))          # без пересечений
        self.assertEqual(len(set(run1) | set(run2)), 6)  # весь пул за 2 забега

    def test_cycle_restarts_after_pool_seen(self):
        self.collect_run(3)
        self.collect_run(3)  # весь пул видан
        run3 = self.collect_run(6)
        self.assertEqual(len(run3), 6)                   # круг начался заново
        self.assertEqual(len(set(run3)), 6)              # в забеге без повторов
