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
from game.views import (parse_exact_number, build_summary, allocate_quotas,
                        mistakes_by_topic, build_mistakes_run)


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
        self.assertEqual(reason, 'нужен рисунок')

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

    def test_array_table_allowed(self):
        # \begin{array} + \hline — реконструированная таблица (KaTeX её
        # рендерит): игра ТЕПЕРЬ такой вопрос берёт (структура сохранена)
        p = make_test_problem(
            statement=r'Данные: $$\begin{array}{|c|c|}\hline A & B \\\hline\end{array}$$ '
                      r'Что выбрать?')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)

    def test_cases_allowed(self):
        # \begin{cases} — кусочная функция (cases в TALL_MATH_ENVS): не брак
        p = make_test_problem(
            statement=r'Издержки $TC(Q) = \begin{cases} Q^{2} & Q \le 1 \\ '
                      r'2Q-1 & Q> 1 \end{cases}$. Что верно?')
        q, opts, correct, reason = extract_question(p)
        self.assertIsNone(reason)

    def test_stray_hline_without_array_rejected(self):
        # \hline вне корректного array-блока — битая вёрстка, по-прежнему брак
        p = make_test_problem(statement=r'Мусор \hline посреди текста. Что?')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'битый LaTeX / вёрстка')

    def test_pseudo_table_double_bar_rejected(self):
        # «| |» вне array — псевдотаблица из битого парсинга, брак
        p = make_test_problem(statement='Ряд | | 5 | | 7 значений. Что верно?')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'битый LaTeX / вёрстка')

    def test_table_reference_without_table_rejected(self):
        # ссылка «в таблице», но таблицы нет — брак
        p = make_test_problem(statement='В таблице выше найдите максимум.')
        q, opts, correct, reason = extract_question(p)
        self.assertEqual(reason, 'нужна таблица')

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

    def test_numeric_payload_carries_unit_without_answer(self):
        p = make_numeric_problem(answer='64')
        GameQuestion.objects.create(
            problem=p, question=p.statement, question_type='numeric',
            options=[], correct_value='64', unit='%', difficulty=2,
            topics=[], lang='ru')
        r = self.client.get('/game/api/session/start/?mode=classic')
        q = r.json()['question']
        self.assertEqual(q['type'], 'numeric')
        self.assertEqual(q['unit'], '%')
        self.assertNotIn('correct', json.dumps(q))

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
        # за ошибку время больше не снимается — снимается жизнь
        self.assertEqual(d2['time_delta'], 0)
        self.assertEqual(d2['lives'], 2)

    def test_skip(self):
        q = self.start()
        d = self.client.post('/game/api/answer/',
                             json.dumps({'question_id': q['id'], 'choice': None}),
                             content_type='application/json').json()
        self.assertEqual(d['result'], 'skip')
        self.assertEqual(d['time_delta'], 0)   # пропуск бесплатный
        self.assertEqual(d['lives'], 3)        # и жизнь за него не берут

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


class LivesTests(TestCase):
    """Жизни вместо штрафа временем: ошибка стоит жизнь, третья завершает
    забег, пропуск не стоит ничего. Очки и серию считает сервер.

    Конец по времени сервером не проверяется: таймер живёт на клиенте
    (см. views.py), сервер узнаёт причину 'time' только при завершении
    забега — это проверяет FinishTests."""

    def setUp(self):
        self.client = Client()
        for i in range(12):
            p = make_test_problem(statement=f'Вопрос номер {i}?', answer='A')
            GameQuestion.objects.create(
                problem=p, question=p.statement,
                options=['Фирмы', 'Страны', 'Планеты', 'Климат'],
                correct_index=0, difficulty=2, topics=[], lang='ru')

    def start(self):
        return self.client.get('/game/api/session/start/').json()

    def answer(self, qid, choice):
        return self.client.post(
            '/game/api/answer/', json.dumps({'question_id': qid, 'choice': choice}),
            content_type='application/json')

    def next_id(self):
        return self.client.get('/game/api/question/').json()['question']['id']

    def test_start_reports_full_lives(self):
        d = self.start()
        self.assertEqual(d['lives'], 3)
        self.assertEqual(d['mode']['lives'], 3)

    def test_wrong_costs_one_life_and_no_time(self):
        qid = self.start()['question']['id']
        d = self.answer(qid, 2).json()
        self.assertEqual(d['result'], 'wrong')
        self.assertEqual(d['lives'], 2)
        self.assertEqual(d['time_delta'], 0)
        self.assertNotIn('game_over', d)

    def test_game_over_exactly_on_third_mistake(self):
        qid = self.start()['question']['id']
        lives = []
        for i in range(3):
            d = self.answer(qid, 2).json()
            lives.append(d['lives'])
            if i < 2:
                self.assertNotIn('game_over', d)  # забег продолжается
            else:
                self.assertEqual(d['game_over']['reason'], 'lives')
                # выбыл на третьем вопросе — номер в забеге, не индекс
                self.assertEqual(d['game_over']['question_number'], 3)
            qid = self.next_id() if i < 2 else qid
        self.assertEqual(lives, [2, 1, 0])

    def test_answer_after_game_over_409(self):
        qid = self.start()['question']['id']
        for i in range(3):
            self.answer(qid, 2)
            if i < 2:
                qid = self.next_id()
        r = self.answer(qid, 2)
        self.assertEqual(r.status_code, 409)   # забег уже кончился

    def test_skip_touches_nothing(self):
        """Пропуск: жизни целы, время цело, комбо цело."""
        qid = self.start()['question']['id']
        for _ in range(3):          # набираем серию 3 → множитель ×2
            self.answer(qid, 0)
            qid = self.next_id()
        d = self.client.post(
            '/game/api/answer/', json.dumps({'question_id': qid, 'choice': None}),
            content_type='application/json').json()
        self.assertEqual(d['result'], 'skip')
        self.assertEqual(d['lives'], 3)
        self.assertEqual(d['time_delta'], 0)
        self.assertEqual(d['streak'], 3)       # серия не порвалась
        # и следующий верный идёт уже по множителю ×2 (серия продолжилась)
        d2 = self.answer(self.next_id(), 0).json()
        self.assertEqual(d2['streak'], 4)
        self.assertEqual(d2['points'], 200)

    def test_wrong_breaks_combo(self):
        qid = self.start()['question']['id']
        for _ in range(3):
            self.answer(qid, 0)
            qid = self.next_id()
        d = self.answer(qid, 2).json()
        self.assertEqual(d['streak'], 0)
        self.assertEqual(d['best_streak'], 3)  # лучшая серия помнится

    def test_score_counted_by_server_with_multiplier(self):
        """Очки считает сервер: 100 × множитель серии."""
        qid = self.start()['question']['id']
        points, score = [], 0
        for _ in range(4):
            d = self.answer(qid, 0).json()
            points.append(d['points'])
            score = d['score']
            qid = self.next_id()
        # серии 1,2 → ×1; серии 3,4 → ×2
        self.assertEqual(points, [100, 100, 200, 200])
        self.assertEqual(score, 600)

    def test_lives_remain_while_run_continues(self):
        """Две ошибки — забег жив: конец только по жизням в ноль."""
        qid = self.start()['question']['id']
        self.answer(qid, 2)
        d = self.answer(self.next_id(), 2).json()
        self.assertEqual(d['lives'], 1)
        self.assertNotIn('game_over', d)
        # и следующий вопрос по-прежнему выдаётся
        r = self.client.get('/game/api/question/')
        self.assertIn('question', r.json())


def log_row(outcome='correct', topics=('Спрос и предложение',), difficulty=3,
            number=1, elapsed_ms=3000, running_score=100, running_combo=1,
            lives_after=3, question_id=1, question_type='single'):
    """Одна запись журнала забега — как её пишет api_answer."""
    return {
        'question_id': question_id, 'number': number, 'topics': list(topics),
        'difficulty': difficulty, 'question_type': question_type,
        'outcome': outcome, 'elapsed_ms': elapsed_ms,
        'running_score': running_score, 'running_combo': running_combo,
        'lives_after': lives_after,
    }


def fake_state(log, mode='blitz', score=0, best_streak=0, lives=3, ended=None):
    """Состояние забега с подставленным журналом (для агрегатора)."""
    return {'mode': mode, 'topic': None, 'seen': [], 'answered': {},
            'lives': lives, 'score': score, 'streak': 0,
            'best_streak': best_streak, 'ended': ended, 'log': log}


class SummaryTests(TestCase):
    """Агрегатор сводки: чистая функция журнала, базу не трогает."""

    def test_accuracy_counts_attempts_not_skips(self):
        """Точность = верные / (верные + неверные). Пропуск не ответ и
        точность не портит — иначе честный пропуск был бы хуже угадывания."""
        s = build_summary(fake_state([
            log_row(outcome='correct'), log_row(outcome='correct'),
            log_row(outcome='wrong'), log_row(outcome='skip'),
            log_row(outcome='skip'),
        ]))
        self.assertEqual((s['correct'], s['wrong'], s['skipped']), (2, 1, 2))
        self.assertEqual(s['total'], 3)         # попыток, а не показов
        self.assertEqual(s['accuracy'], 67)     # 2/3

    def test_empty_log_does_not_divide_by_zero(self):
        s = build_summary(fake_state([]))
        self.assertEqual(s['accuracy'], 0)
        self.assertEqual(s['total'], 0)
        self.assertEqual(s['topic_rows'], [])
        self.assertEqual(s['score_curve'], [])

    def test_topic_breakdown_and_order(self):
        """По каждой теме — верно/неверно/пропуск; вперёд идут темы
        с ошибками (на них экран и работа над ошибками)."""
        s = build_summary(fake_state([
            log_row(topics=('Спрос и предложение',), outcome='correct'),
            log_row(topics=('Спрос и предложение',), outcome='wrong'),
            log_row(topics=('Эластичность',), outcome='wrong'),
            log_row(topics=('Эластичность',), outcome='wrong'),
            log_row(topics=('Издержки',), outcome='correct'),
            log_row(topics=('Издержки',), outcome='skip'),
        ]))
        rows = {r['topic']: r for r in s['topic_rows']}
        self.assertEqual(rows['Эластичность']['wrong'], 2)
        self.assertEqual(rows['Эластичность']['accuracy'], 0)
        self.assertEqual(rows['Спрос и предложение']['accuracy'], 50)
        self.assertEqual(rows['Издержки']['skip'], 1)
        self.assertEqual(rows['Издержки']['total'], 2)
        # порядок: больше ошибок — выше
        self.assertEqual([r['topic'] for r in s['topic_rows']][0], 'Эластичность')

    def test_question_with_two_topics_counts_in_both(self):
        s = build_summary(fake_state([
            log_row(topics=('Спрос и предложение', 'Эластичность'), outcome='wrong'),
        ]))
        self.assertEqual({r['topic']: r['wrong'] for r in s['topic_rows']},
                         {'Спрос и предложение': 1, 'Эластичность': 1})

    def test_question_without_topics_not_lost(self):
        """Вопрос без тем не исчезает — иначе его ошибка пропала бы из сводки."""
        s = build_summary(fake_state([log_row(topics=(), outcome='wrong')]))
        self.assertEqual([r['topic'] for r in s['topic_rows']], ['Без темы'])

    def test_difficulty_groups(self):
        s = build_summary(fake_state([
            log_row(difficulty=1, outcome='correct'),
            log_row(difficulty=2, outcome='wrong'),
            log_row(difficulty=3, outcome='correct'),
            log_row(difficulty=5, outcome='correct'),
            log_row(difficulty=4, outcome='skip'),
        ]))
        d = {g['key']: g for g in s['difficulty']}
        self.assertEqual((d['easy']['total'], d['easy']['correct']), (2, 1))
        self.assertEqual((d['medium']['total'], d['medium']['correct']), (1, 1))
        self.assertEqual((d['hard']['total'], d['hard']['correct']), (2, 1))

    def test_time_buckets(self):
        """Границы корзин: значение попадает в ту, где lo <= t < hi."""
        s = build_summary(fake_state([
            log_row(elapsed_ms=500),      # 0–2
            log_row(elapsed_ms=2000),     # ровно граница → 2–4
            log_row(elapsed_ms=3999),     # 2–4
            log_row(elapsed_ms=9000),     # 8–10
            log_row(elapsed_ms=14000),    # 10–15
            log_row(elapsed_ms=30000),    # ровно граница → >30
            log_row(elapsed_ms=99000),    # >30
        ]))
        counts = {b['title']: b['count'] for b in s['time_buckets']}
        self.assertEqual(counts['0–2 с'], 1)
        self.assertEqual(counts['2–4 с'], 2)
        self.assertEqual(counts['4–6 с'], 0)
        self.assertEqual(counts['8–10 с'], 1)
        self.assertEqual(counts['10–15 с'], 1)
        self.assertEqual(counts['>30 с'], 2)
        self.assertEqual(sum(b['count'] for b in s['time_buckets']), 7)

    def test_max_combo_is_multiplier_of_best_streak(self):
        s = build_summary(fake_state([log_row()], best_streak=7))
        self.assertEqual(s['best_streak'], 7)
        self.assertEqual(s['max_multiplier'], 3)   # серия 6..8 → ×3

    def test_curves_follow_question_order(self):
        s = build_summary(fake_state([
            log_row(number=1, running_score=100, running_combo=1),
            log_row(number=2, running_score=200, running_combo=2),
            log_row(number=3, running_score=200, running_combo=0, outcome='wrong'),
        ]))
        self.assertEqual(s['score_curve'], [100, 200, 200])
        self.assertEqual(s['combo_curve'], [1, 2, 0])
        self.assertEqual(s['last_number'], 3)


class FinishTests(TestCase):
    """Завершение забега: причина, сводка, две концовки."""

    def setUp(self):
        self.client = Client()
        for i in range(8):
            p = make_test_problem(statement=f'Вопрос номер {i}?', answer='A')
            GameQuestion.objects.create(
                problem=p, question=p.statement,
                options=['Фирмы', 'Страны', 'Планеты', 'Климат'],
                correct_index=0, difficulty=2, topics=['Эластичность'],
                lang='ru')

    def start(self):
        return self.client.get('/game/api/session/start/').json()['question']['id']

    def answer(self, qid, choice, elapsed_ms=None):
        body = {'question_id': qid, 'choice': choice}
        if elapsed_ms is not None:
            body['elapsed_ms'] = elapsed_ms
        return self.client.post('/game/api/answer/', json.dumps(body),
                                content_type='application/json').json()

    def next_id(self):
        return self.client.get('/game/api/question/').json()['question']['id']

    def finish(self, reason='time'):
        r = self.client.post('/game/api/session/finish/',
                             json.dumps({'reason': reason}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        return r.json()['summary']

    def test_finish_by_time_with_lives_left(self):
        """Конец по времени при жизнях > 0: причину знает только клиент."""
        qid = self.start()
        self.answer(qid, 0)
        self.answer(self.next_id(), 2)      # одна ошибка
        s = self.finish('time')
        self.assertEqual(s['ended_reason'], 'time')
        self.assertEqual(s['lives_left'], 2)
        self.assertEqual((s['correct'], s['wrong']), (1, 1))

    def test_finish_by_lives_ignores_client_reason(self):
        """Конец по жизням при времени > 0: слово клиента сервер не перебивает."""
        qid = self.start()
        for i in range(3):
            self.answer(qid, 2)
            if i < 2:
                qid = self.next_id()
        s = self.finish('time')             # клиент врёт, что вышло время
        self.assertEqual(s['ended_reason'], 'lives')
        self.assertEqual(s['lives_left'], 0)
        self.assertEqual(s['last_number'], 3)

    def test_finish_by_done(self):
        qid = self.start()
        self.answer(qid, 0)
        s = self.finish('done')
        self.assertEqual(s['ended_reason'], 'done')

    def test_unknown_reason_falls_back_to_time(self):
        self.answer(self.start(), 0)
        s = self.finish('чепуха')
        self.assertEqual(s['ended_reason'], 'time')

    def test_finish_is_idempotent(self):
        self.answer(self.start(), 0)
        first = self.finish('time')
        second = self.finish('time')
        self.assertEqual(first['score'], second['score'])
        self.assertEqual(first['ended_reason'], second['ended_reason'])

    def test_finish_without_session_400(self):
        r = self.client.post('/game/api/session/finish/', json.dumps({}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_summary_carries_elapsed_from_client(self):
        qid = self.start()
        self.answer(qid, 0, elapsed_ms=1500)
        self.answer(self.next_id(), 0, elapsed_ms=12000)
        s = self.finish('time')
        counts = {b['title']: b['count'] for b in s['time_buckets']}
        self.assertEqual(counts['0–2 с'], 1)
        self.assertEqual(counts['10–15 с'], 1)

    def test_elapsed_garbage_does_not_break_summary(self):
        """Мусор в elapsed_ms не роняет забег — поле игрока не должно быть
        способом положить сводку."""
        qid = self.start()
        for bad in ('ерунда', -5, 10 ** 12, None):
            self.client.post(
                '/game/api/answer/',
                json.dumps({'question_id': qid, 'choice': None, 'elapsed_ms': bad}),
                content_type='application/json')
            qid = self.next_id()
        s = self.finish('time')
        self.assertEqual(s['time_buckets'][0]['count'], 4)   # все в корзину 0–2

    def test_summary_topics_come_from_journal(self):
        qid = self.start()
        self.answer(qid, 2)
        s = self.finish('time')
        self.assertEqual(s['topic_rows'][0]['topic'], 'Эластичность')
        self.assertEqual(s['topic_rows'][0]['wrong'], 1)


class QuotaTests(TestCase):
    """Раздача мест целевого забега по темам — метод наибольшего остатка."""

    def test_two_topics_seven_three(self):
        """Контрольная арифметика: 2 ошибки в A, 1 в B на 10 мест.
        10·2/3 = 6,67 → 6 целых; 10·1/3 = 3,33 → 3 целых; девять роздано,
        десятое — теме с бо́льшим остатком (A) → 7/3."""
        q = allocate_quotas({'A': 2, 'B': 1}, 10)
        self.assertEqual(q, {'A': 7, 'B': 3})
        self.assertEqual(sum(q.values()), 10)

    def test_single_topic_takes_everything(self):
        self.assertEqual(allocate_quotas({'A': 1}, 10), {'A': 10})

    def test_three_equal_topics_sum_to_ten(self):
        """Поровну не делится — но в сумме обязано выйти ровно 10."""
        q = allocate_quotas({'A': 1, 'B': 1, 'C': 1}, 10)
        self.assertEqual(sum(q.values()), 10)
        self.assertEqual(sorted(q.values()), [3, 3, 4])

    def test_tie_is_deterministic(self):
        """Одинаковый вход — одинаковый выход (ничья решается именем)."""
        a = allocate_quotas({'Спрос': 1, 'Издержки': 1, 'Налоги': 1}, 10)
        b = allocate_quotas({'Налоги': 1, 'Издержки': 1, 'Спрос': 1}, 10)
        self.assertEqual(a, b)

    def test_no_mistakes_no_quotas(self):
        self.assertEqual(allocate_quotas({}, 10), {})
        self.assertEqual(allocate_quotas({'A': 0}, 10), {})

    def test_mistakes_by_topic_counts_only_wrong(self):
        log = [
            log_row(topics=('A',), outcome='wrong'),
            log_row(topics=('A',), outcome='correct'),
            log_row(topics=('A',), outcome='skip'),
            log_row(topics=('B',), outcome='wrong'),
        ]
        self.assertEqual(mistakes_by_topic(log), {'A': 1, 'B': 1})

    def test_mistake_with_two_topics_counts_in_both(self):
        """Какая из двух тем подвела — неизвестно; делить ошибку пополам
        было бы выдумкой, поэтому засчитываем обеим."""
        log = [log_row(topics=('A', 'B'), outcome='wrong')]
        self.assertEqual(mistakes_by_topic(log), {'A': 1, 'B': 1})

    def test_mistake_without_topics_is_not_targetable(self):
        log = [log_row(topics=(), outcome='wrong')]
        self.assertEqual(mistakes_by_topic(log), {})


class MistakesRunBuildTests(TestCase):
    """Сборка списка вопросов целевого забега (чистая функция)."""

    def rows(self, spec):
        """spec: {id: [темы]} → [(id, [темы])]"""
        return [(pk, topics) for pk, topics in spec.items()]

    def test_quotas_respected(self):
        rows = self.rows({i: ['A'] for i in range(1, 21)})
        rows += self.rows({i: ['B'] for i in range(21, 41)})
        got = build_mistakes_run(rows, {'A': 7, 'B': 3}, 10)
        self.assertEqual(len(got), 10)
        self.assertEqual(len([p for p in got if p <= 20]), 7)
        self.assertEqual(len([p for p in got if p > 20]), 3)

    def test_no_duplicates_when_question_in_two_topics(self):
        """Вопрос в двух темах ошибок не должен попасть в забег дважды."""
        rows = self.rows({1: ['A', 'B'], 2: ['A'], 3: ['B'], 4: ['A', 'B']})
        got = build_mistakes_run(rows, {'A': 3, 'B': 3}, 6)
        self.assertEqual(len(got), len(set(got)))
        self.assertEqual(sorted(got), [1, 2, 3, 4])   # больше в пуле нет

    def test_shortfall_filled_from_other_mistake_topics(self):
        """В теме не хватило под квоту — добираем из других тем ошибок."""
        rows = self.rows({1: ['A'], 2: ['A']})
        rows += self.rows({i: ['B'] for i in range(3, 20)})
        got = build_mistakes_run(rows, {'A': 7, 'B': 3}, 10)
        self.assertEqual(len(got), 10)
        self.assertEqual(sorted([p for p in got if p <= 2]), [1, 2])  # все, что есть

    def test_shortfall_filled_from_any_question_of_type(self):
        """Тем ошибок не хватило совсем — добираем любыми того же типа."""
        rows = self.rows({1: ['A']})
        rows += self.rows({i: ['Другое'] for i in range(2, 30)})
        got = build_mistakes_run(rows, {'A': 10}, 10)
        self.assertEqual(len(got), 10)
        self.assertIn(1, got)

    def test_short_pool_gives_short_run_without_crash(self):
        """Вопросов меньше десяти — забег просто короче, это не ошибка."""
        rows = self.rows({1: ['A'], 2: ['A']})
        got = build_mistakes_run(rows, {'A': 10}, 10)
        self.assertEqual(sorted(got), [1, 2])

    def test_empty_pool_gives_empty_run(self):
        self.assertEqual(build_mistakes_run([], {'A': 10}, 10), [])

    def test_unseen_questions_preferred(self):
        """Тот же принцип, что в обычном забеге: сначала невиданные."""
        rows = self.rows({i: ['A'] for i in range(1, 11)})
        got = build_mistakes_run(rows, {'A': 3}, 3, seen_before=list(range(1, 8)))
        self.assertEqual(sorted(got), [8, 9, 10])   # только невиданные


class MistakesRunApiTests(TestCase):
    """Целевой забег через API: фильтры типа/языка/тем, крайние случаи."""

    def setUp(self):
        self.client = Client()
        # по 12 single-вопросов на две темы + шум других типов и языков
        for topic in ('Эластичность', 'Издержки'):
            for i in range(12):
                p = make_test_problem(statement=f'{topic} вопрос {i}?', answer='A')
                GameQuestion.objects.create(
                    problem=p, question=p.statement,
                    options=['Фирмы', 'Страны', 'Планеты', 'Климат'],
                    correct_index=0, difficulty=2, topics=[topic], lang='ru')
        # ловушки: тот же текст, но другой тип и другой язык
        for i in range(12):
            p = make_test_problem(statement=f'Данетка {i}?', answer='A')
            GameQuestion.objects.create(
                problem=p, question=p.statement, question_type='boolean',
                options=['Верно', 'Неверно'], correct_index=0, difficulty=2,
                topics=['Эластичность'], lang='ru')
            p2 = make_test_problem(statement=f'English {i}?', answer='A')
            GameQuestion.objects.create(
                problem=p2, question=p2.statement,
                options=['Firms', 'States', 'Planets', 'Climate'],
                correct_index=0, difficulty=2, topics=['Эластичность'],
                lang='en')

    def play_with_mistakes(self):
        """Забег с двумя ошибками в «Эластичности» и одной в «Издержках»."""
        r = self.client.get('/game/api/session/start/').json()
        qid = r['question']['id']
        made = {'Эластичность': 0, 'Издержки': 0}
        while sum(made.values()) < 3:
            gq = GameQuestion.objects.get(id=qid)
            topic = gq.topics[0]
            need = {'Эластичность': 2, 'Издержки': 1}[topic]
            choice = 2 if made[topic] < need else 0     # 2 = неверный
            if made[topic] < need:
                made[topic] += 1
            self.client.post('/game/api/answer/',
                             json.dumps({'question_id': qid, 'choice': choice}),
                             content_type='application/json')
            nxt = self.client.get('/game/api/question/').json()
            if 'question' not in nxt:
                break
            qid = nxt['question']['id']
        return made

    def test_start_mistakes_without_previous_run_400(self):
        r = self.client.get('/game/api/session/start_mistakes/')
        self.assertEqual(r.status_code, 400)

    def test_clean_run_has_no_mistakes_run(self):
        """Ошибок нет — целевой забег не собирается (на экране и кнопки нет)."""
        qid = self.client.get('/game/api/session/start/').json()['question']['id']
        self.client.post('/game/api/answer/',
                         json.dumps({'question_id': qid, 'choice': 0}),
                         content_type='application/json')
        self.client.post('/game/api/session/finish/', json.dumps({'reason': 'time'}),
                         content_type='application/json')
        r = self.client.get('/game/api/session/start_mistakes/')
        self.assertEqual(r.status_code, 400)

    def test_mistakes_run_uses_only_error_topics_type_and_lang(self):
        self.play_with_mistakes()
        self.client.post('/game/api/session/finish/', json.dumps({'reason': 'time'}),
                         content_type='application/json')
        r = self.client.get('/game/api/session/start_mistakes/')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d['ok'])
        self.assertTrue(d['mistakes_run'])
        self.assertEqual(d['mode']['key'], 'blitz')     # режим тот же
        self.assertEqual(d['lives'], 3)                 # жизни свежие

        # проходим забег до конца и смотрим, из чего он собран
        ids = [d['question']['id']]
        while True:
            nxt = self.client.get('/game/api/question/').json()
            if 'question' not in nxt:
                break
            ids.append(nxt['question']['id'])
        self.assertEqual(len(ids), 10)                  # ровно N вопросов
        got = GameQuestion.objects.filter(id__in=ids)
        self.assertEqual({g.question_type for g in got}, {'single'})  # тип режима
        self.assertEqual({g.lang for g in got}, {'ru'})               # только ru
        topics = [g.topics[0] for g in got]
        self.assertEqual(set(topics), {'Эластичность', 'Издержки'})
        # пропорция ошибок 2:1 → метод наибольшего остатка даёт 7/3
        self.assertEqual(topics.count('Эластичность'), 7)
        self.assertEqual(topics.count('Издержки'), 3)

    def test_mistakes_run_is_a_normal_run_with_summary(self):
        """Целевой забег — обычный забег: те же жизни, тот же финал."""
        self.play_with_mistakes()
        self.client.post('/game/api/session/finish/', json.dumps({'reason': 'time'}),
                         content_type='application/json')
        qid = self.client.get('/game/api/session/start_mistakes/').json()['question']['id']
        for i in range(3):
            self.client.post('/game/api/answer/',
                             json.dumps({'question_id': qid, 'choice': 2}),
                             content_type='application/json')
            if i < 2:
                qid = self.client.get('/game/api/question/').json()['question']['id']
        s = self.client.post('/game/api/session/finish/', json.dumps({'reason': 'time'}),
                             content_type='application/json').json()['summary']
        self.assertEqual(s['ended_reason'], 'lives')
        self.assertEqual(s['wrong'], 3)

    def test_mistakes_run_survives_deleted_question(self):
        """Пул пересобрали между сборкой очереди и выдачей — не падаем."""
        self.play_with_mistakes()
        self.client.post('/game/api/session/finish/', json.dumps({'reason': 'time'}),
                         content_type='application/json')
        d = self.client.get('/game/api/session/start_mistakes/').json()
        # сносим все вопросы, кроме уже выданного первого
        GameQuestion.objects.exclude(id=d['question']['id']).delete()
        nxt = self.client.get('/game/api/question/').json()
        self.assertTrue(nxt.get('exhausted'))


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

    def test_numeric_with_table_accepted(self):
        # numeric-вопрос со ссылкой на таблицу И реконструированной таблицей:
        # берём; разметка массива не раздувает лимит длины (reading_length)
        arr = (r'$$\begin{array}{|l|c|}\hline \text{Годовой доход} & '
               r'\text{Ставка} \\ \hline \text{до } 5 & 13 \\ \hline'
               r'\text{свыше } 5 & 15 \\ \hline\end{array}$$')
        p = make_numeric_problem(
            statement='В таблице дана шкала налога. ' + arr
                      + ' Сколько заплатит Тихон? ' + ('слово ' * 60))
        q, value, reason = extract_numeric(p)
        self.assertIsNone(reason)
        self.assertIn(r'\begin{array}', q)

    def test_question_quality_rules_apply(self):
        # Общие фильтры качества (длина, рисунок) работают и для numeric —
        # но лимит длины мягче (700, не 300): Классика даёт 600 с на вопрос,
        # расчётные региональные задачи длиннее куцых тестовых вопросов.
        p = make_numeric_problem(statement='На основе графика найдите цену.')
        self.assertEqual(extract_numeric(p)[2], 'нужен рисунок')
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

    def test_numeric_unit_from_reference_note(self):
        p = make_numeric_problem(answer='64')
        SourceReference.objects.create(
            problem=p, source=self.source, stage='региональный',
            year=2021, grade='10',
            note='7 б. за верный ответ; единица ответа: %; общий вопрос')
        self._run()
        gq = GameQuestion.objects.get(problem=p)
        self.assertEqual(gq.unit, '%')

    def test_no_unit_note_means_empty_unit(self):
        p = make_numeric_problem(answer='5')
        SourceReference.objects.create(
            problem=p, source=self.source, stage='региональный', year=2020)
        self._run()
        self.assertEqual(GameQuestion.objects.get(problem=p).unit, '')


class PoolDedupTests(TestCase):
    """Схлопывание повторов на сборке пула: одинаковый текст+варианты — один
    вопрос в пуле (побеждает более свежий year), в базе ничего не меняется."""

    @classmethod
    def setUpTestData(cls):
        cls.source = Source.objects.create(
            name='ВсОШ — региональный этап', kind='олимпиада')

    def _run(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('build_game_pool', stdout=StringIO())

    def test_same_text_and_options_collapse_newer_year_wins(self):
        old = make_test_problem(answer='A')
        new = make_test_problem(answer='A')
        SourceReference.objects.create(
            problem=old, source=self.source, year=2018, grade='9')
        SourceReference.objects.create(
            problem=new, source=self.source, year=2022, grade='9')
        self._run()
        self.assertEqual(
            GameQuestion.objects.filter(
                problem__in=[old, new]).count(), 1)
        survivor = GameQuestion.objects.get(problem__in=[old, new])
        self.assertEqual(survivor.problem_id, new.id)
        self.assertEqual(survivor.year, 2022)
        # в базе обе задачи остались нетронутыми — дедуп только в пуле
        self.assertTrue(Problem.objects.filter(id=old.id).exists())
        self.assertTrue(Problem.objects.filter(id=new.id).exists())

    def test_tie_on_year_smaller_id_wins(self):
        a = make_test_problem(answer='A')
        b = make_test_problem(answer='A')
        SourceReference.objects.create(
            problem=a, source=self.source, year=2020, grade='9')
        SourceReference.objects.create(
            problem=b, source=self.source, year=2020, grade='10')
        self._run()
        survivor = GameQuestion.objects.get(problem__in=[a, b])
        self.assertEqual(survivor.problem_id, min(a.id, b.id))

    def test_numeric_same_text_different_answer_both_kept(self):
        # одинаковое условие, но разный числовой ответ (варианты одной задачи
        # по годам) — это РАЗНЫЕ вопросы, оба должны остаться в пуле
        p1 = make_numeric_problem(statement='Найдите равновесную цену.',
                                  answer='50')
        p2 = make_numeric_problem(statement='Найдите равновесную цену.',
                                  answer='64')
        self._run()
        self.assertEqual(
            GameQuestion.objects.filter(problem__in=[p1, p2]).count(), 2)
        values = set(GameQuestion.objects.filter(problem__in=[p1, p2])
                     .values_list('correct_value', flat=True))
        self.assertEqual(values, {'50', '64'})

    def test_different_options_not_collapsed(self):
        p1 = make_test_problem(answer='A',
                               options=('Фирмы', 'Страны', 'Планеты', 'Климат'))
        p2 = make_test_problem(answer='A',
                               options=('Рынки', 'Банки', 'Заводы', 'Домохозяйства'))
        self._run()
        self.assertEqual(
            GameQuestion.objects.filter(problem__in=[p1, p2]).count(), 2)


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
