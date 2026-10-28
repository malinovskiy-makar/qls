# -*- coding: utf-8 -*-
"""Контур качества (Q1): стандарт эталонной задачи S1–S10 и разбор формул."""
import shutil
import unittest
from decimal import Decimal

from django.test import SimpleTestCase

from problems.olympiad_contour import katex, run, standard


def card(**kw):
    base = {
        'level': 'ref', 'olympiad': 'mosh', 'ref_key': 'mosh-2020-final-9-v1|1|', 'problem_id': None,
        'event_id': 'mosh-2020-final-9-v1', 'number': '1', 'title': '',
        'statement': 'Фирма продаёт 120 единиц товара по цене 35 рублей.',
        'solution': 'Выручка равна 4200.', 'answer': '4200', 'criteria': '',
        'parts': [], 'test': None, 'max_score': None, 'figures': [],
        'figure_markers_missing': [], 'figure_orphans': [], 'tables_expected': 0,
        'layer': {'text': 'Фирма продаёт 120 единиц товара по цене 35 рублей.', 'scan': False},
        'numbers_ok': True,
        'meta': {'season': '2019/2020', 'stage': 'final', 'grade': '9', 'number': '1',
                 'pdf_url': 'https://mos.olimpiada.ru/x.pdf', 'pdf_official': True},
        'reference_suspect': False, 'solution_expected': True, 'section': '', 'visible': True,
    }
    base.update(kw)
    return base


def codes(fails):
    return {f['code'] for f in fails}


class CleanCardTests(SimpleTestCase):
    def test_clean_card_passes_all_local_checks(self):
        res = standard.check_card(card())
        self.assertEqual(res['fails'], [])
        self.assertNotIn('S3', res['skipped'])


class S1Tests(SimpleTestCase):
    def test_empty_statement(self):
        self.assertIn('empty_statement', codes(standard.s1(card(statement='  [[FIGURE:abc12]] '))))

    def test_service_patterns(self):
        cases = {
            'olympiad_header': 'Московская олимпиада школьников по экономике 2020',
            'continued': 'Продолжение на следующей странице',
            'page_number': 'Страница 2 из 4',
            'tasks_heading': 'ЗАДАЧИ',
            'authors': 'Составители: Иванов И. И., Петров П. П.',
            'answers_heading': 'Ответы и решения',
            'timing_header': 'Время выполнения работы – 90 минут.',
        }
        for code, line in cases.items():
            with self.subTest(code=code):
                text = 'Условие задачи про спрос.\n%s\nЕщё текст.' % line
                self.assertIn(code, codes(standard.s1(card(statement=text))))

    def test_ordinary_text_is_not_service(self):
        text = ('Задания олимпиады бывают разные. Фирма решила 3/4 задачи.\n3/4\n'
                'Ответ: ____________')
        self.assertEqual(standard.s1(card(statement=text)), [])


class S2Tests(SimpleTestCase):
    def parts(self, *items):
        return [{'label': lb, 'text': t, 'points': p, 'answer': ''} for lb, t, p in items]

    def test_points_sum_must_equal_max(self):
        parts = self.parts(('а', 'Найдите (4 балла)', Decimal(4)), ('б', 'Найдите (6 баллов)', Decimal(6)))
        self.assertEqual(standard.s2(card(parts=parts, max_score=10)), [])
        self.assertIn('points_sum', codes(standard.s2(card(parts=parts, max_score=12))))

    def test_no_sum_check_when_points_unknown(self):
        parts = self.parts(('а', 'x', Decimal(4)), ('б', 'y', None))
        self.assertEqual(standard.s2(card(parts=parts, max_score=12)), [])

    def test_label_problems(self):
        parts = self.parts(('а', 'x', None), ('', 'y', None), ('а', 'z', None), ('б', ' ', None))
        self.assertEqual(codes(standard.s2(card(parts=parts))),
                         {'part_without_label', 'duplicate_labels', 'empty_part'})

    def test_text_points(self):
        self.assertEqual(standard.text_points('Найдите (**4 балла**)'), Decimal(4))
        self.assertIsNone(standard.text_points('(2 балла) и (3 балла)'))


class S3Tests(SimpleTestCase):
    def test_alien_number(self):
        c = card(statement='Фирма продаёт 125 единиц товара по цене 35 рублей.')
        self.assertIn('125', standard.alien_numbers(c))
        self.assertIn('number_not_in_pdf', codes(standard.s3(c)))

    def test_thousands_and_label_glue(self):
        # «2 500» в слое = 2500; метка «2» и «500» пункта не склеиваются
        c = card(statement='Доход 2 500 рублей.',
                 parts=[{'label': '2', 'text': '500 штук', 'points': None, 'answer': ''}],
                 layer={'text': 'Доход 2500 рублей. 2) 500 штук', 'scan': False})
        self.assertEqual(standard.s3(c), [])

    def test_scan_and_no_layer_are_skipped(self):
        self.assertEqual(standard.s3(card(statement='999 штук', layer={'text': '', 'scan': True})), [])
        self.assertIn('S3', standard.check_card(card(layer=None))['skipped'])

    def test_section_intro_not_checked(self):
        c = card(statement='Тест включает 30 вопросов.\n\nЦена 35 рублей.', section='Тест включает 30 вопросов.',
                 layer={'text': 'Цена 35 рублей', 'scan': False})
        self.assertEqual(standard.s3(c), [])

    def test_hyphenated_layer_is_joined(self):
        c = card(statement='Число 1250 миллионов', layer={'text': 'Число 12-\n50 мил-\nлионов', 'scan': False})
        self.assertEqual(standard.alien_numbers(c), [])


class S4Tests(SimpleTestCase):
    def test_from_results(self):
        res = [('statement', {'errors': [{'tex': '\\frac{1', 'problem': 'parse'}], 'currency': ['$ за 5$'],
                              'text_in_math': ['$цена товара$'], 'unpaired': 1})]
        self.assertEqual(codes(standard.s4_from_results(res)),
                         {'katex_error', 'currency_dollar', 'text_in_math', 'unpaired_dollar'})

    def test_formula_texts_cover_parts_and_options(self):
        c = card(parts=[{'label': 'а', 'text': '$x$', 'points': None, 'answer': '$y$'}],
                 test={'kind': 'single', 'options': [{'label': '1', 'text': '$z$', 'correct': True}], 'key': '1'})
        fields = {f for f, _t in standard.formula_texts(c)}
        self.assertTrue({'part0', 'part0.answer', 'option0'} <= fields)


@unittest.skipUnless(shutil.which('node'), 'нужен node')
class KatexScriptTests(SimpleTestCase):
    def test_site_parsing(self):
        texts = ['Цена $P=10$', 'стоит 5$ за штуку, а 10$ всего', 'одна $ штука',
                 '$\\left( x $', 'валюта \\$5 и \\$6', '$TR = цена умножить$', '$$a$$ и $Q_{спрос}$']
        r = katex.check_texts(texts)
        self.assertEqual(r[0], {'errors': [], 'currency': [], 'text_in_math': [], 'unpaired': 0})
        self.assertEqual(len(r[1]['currency']), 1)
        self.assertEqual(r[2]['unpaired'], 1)
        self.assertEqual(len(r[3]['errors']), 1)
        self.assertEqual(r[4], r[0])
        self.assertEqual(len(r[5]['text_in_math']), 1)
        self.assertEqual(r[6], r[0])


class S5Tests(SimpleTestCase):
    def fig(self, **kw):
        base = {'name': 'f.png', 'exists': True, 'size': 10, 'opens': True, 'rejected': '', 'flag': '',
                'field': 'statement', 'table_ok': False}
        base.update(kw)
        return base

    def test_figure_problems(self):
        figs = [self.fig(name='a', exists=False), self.fig(name='b', size=0), self.fig(name='c', opens=False),
                self.fig(name='d', rejected='таблица-скриншот'), self.fig(name='e', flag='обрезано')]
        c = card(figures=figs, figure_markers_missing=['abcdef0123'], figure_orphans=['z.png'])
        self.assertEqual(codes(standard.s5(c)), {
            'figure_missing', 'figure_empty', 'figure_broken', 'figure_rejected', 'figure_flag',
            'marker_without_figure', 'figure_orphan'})

    def test_good_figure(self):
        self.assertEqual(standard.s5(card(figures=[self.fig()])), [])


class S6Tests(SimpleTestCase):
    GOOD = '| a | b |\n|---|---|\n| 1 | 2 |'

    def test_good_table(self):
        self.assertEqual(standard.s6(card(statement='Таблица:\n\n' + self.GOOD)), [])

    def test_broken_tables(self):
        self.assertIn('no_separator', codes(standard.s6(card(statement='| a | b |\n| 1 | 2 |'))))
        self.assertIn('ragged_table', codes(standard.s6(card(statement='| a | b |\n|---|---|\n| 1 | 2 | 3 |'))))

    def test_table_lost_and_image(self):
        self.assertIn('table_lost', codes(standard.s6(card(tables_expected=1))))
        fig = {'name': 't.png', 'field': 'statement', 'table_ok': False}
        self.assertIn('table_as_image', codes(standard.s6(card(statement='Данные в таблице ниже.',
                                                                figures=[fig]))))
        self.assertIn('table_mentioned_missing', codes(standard.s6(card(statement='Данные в таблице.'))))
        fig_ok = dict(fig, table_ok=True)
        self.assertEqual(standard.s6(card(statement='Данные в таблице.', figures=[fig_ok])), [])

    def test_table_in_solution_counts_for_expected(self):
        self.assertEqual(standard.s6(card(tables_expected=1, solution=self.GOOD)), [])


class S7Tests(SimpleTestCase):
    def test(self, kind='single', options=None, key='б'):
        options = options if options is not None else [
            {'label': 'а', 'text': 'x', 'correct': False}, {'label': 'б', 'text': 'y', 'correct': True}]
        return {'kind': kind, 'options': options, 'key': key, 'why': ''}

    def test_good_test(self):
        self.assertEqual(standard.s7(card(test=self.test())), [])

    def test_defects(self):
        self.assertIn('few_options', codes(standard.s7(card(test=self.test(options=[
            {'label': 'а', 'text': 'x', 'correct': True}])))))
        no_correct = [{'label': 'а', 'text': 'x', 'correct': False}, {'label': 'б', 'text': 'y', 'correct': False}]
        self.assertIn('no_key', codes(standard.s7(card(test=self.test(options=no_correct, key='')))))
        self.assertIn('key_not_in_options', codes(standard.s7(card(test=self.test(options=no_correct, key='г')))))
        two = [{'label': 'а', 'text': 'x', 'correct': True}, {'label': 'б', 'text': 'y', 'correct': True}]
        self.assertIn('single_many_correct', codes(standard.s7(card(test=self.test(options=two)))))
        self.assertEqual(codes(standard.s7(card(test=self.test(kind='broken')))), {'not_playable'})
        self.assertIn('no_key', codes(standard.s7(card(test=self.test(kind='short', key='')))))
        self.assertEqual(standard.s7(card(test=self.test(kind='short', key='42'))), [])


class S8Tests(SimpleTestCase):
    def test_solution_in_statement(self):
        self.assertIn('solution_in_statement', codes(standard.s8(card(statement='Найдите цену.\nРешение: цена 5'))))
        self.assertEqual(standard.s8(card(statement='Найдите цену.\nОтвет: _________')), [])

    def test_other_number_and_parts(self):
        self.assertIn('solution_other_number', codes(standard.s8(card(solution='Задача 3. Решение…'))))
        parts = [{'label': 'а', 'text': 'x', 'points': None, 'answer': ''},
                 {'label': 'б', 'text': 'y', 'points': None, 'answer': ''}]
        self.assertIn('solution_extra_parts', codes(standard.s8(card(parts=parts, solution='а) 1\nб) 2\nг) 3'))))

    def test_suspect_and_missing_solution(self):
        self.assertIn('criteria_other_task', codes(standard.s8(card(reference_suspect=True))))
        self.assertIn('no_solution', codes(standard.s8(card(solution='', answer=''))))
        self.assertEqual(standard.s8(card(solution='', answer='', solution_expected=False)), [])


class S9Tests(SimpleTestCase):
    def test_meta_and_link(self):
        c = card(meta={'season': '', 'stage': 'final', 'grade': '', 'number': '1', 'pdf_url': '',
                       'pdf_official': None})
        self.assertEqual(codes(standard.s9(c)), {'meta_missing', 'no_pdf_link'})
        c = card(meta=dict(card()['meta'], pdf_official=False))
        self.assertIn('pdf_not_official', codes(standard.s9(c)))

    def test_title_rule_on_bank(self):
        self.assertIn('title_stub', codes(standard.s9(card(level='bank', title='Задача 3'))))
        self.assertIn('title_has_olympiad', codes(standard.s9(card(level='bank', title='Олимпиада и спрос'))))
        long_title = 'Фирма продаёт 120 единиц товара по цене 35 рублей и хочет увеличить выручку вдвое'
        st = long_title + ' за год.'
        self.assertIn('title_text_start', codes(standard.s9(card(level='bank', title=long_title, statement=st))))
        self.assertEqual(standard.s9(card(level='bank', title='Выручка ярмарки')), [])
        self.assertEqual(standard.s9(card(title='')), [])   # эталон: заголовок не проверяется


class S10Tests(SimpleTestCase):
    def test_duplicates_in_event(self):
        a, b = card(ref_key='e|1|'), card(ref_key='e|2|')
        other_event = card(ref_key='f|1|', event_id='other')
        out = standard.s10_groups([a, b, other_event])
        self.assertEqual(set(out), {0, 1})
        self.assertEqual(out[0][0]['code'], 'duplicate_in_event')

    def test_hidden_bank_problem_not_counted(self):
        a = card(level='bank', problem_id=1, visible=True)
        b = card(level='bank', problem_id=2, visible=False)
        self.assertEqual(standard.s10_groups([a, b]), {})


class RunTests(SimpleTestCase):
    def test_check_cards_and_summary(self):
        cards = [card(), card(ref_key='e|2|', number='2', statement='')]
        res = run.check_cards(cards, katex_check=lambda texts: [
            {'errors': [], 'currency': [], 'text_in_math': [], 'unpaired': 0} for _ in texts])
        rows = [run.result_row(c, r) for c, r in zip(cards, res)]
        self.assertEqual([r['passed'] for r in rows], [True, False])
        s = run.summary(rows)[('ref', 'mosh')]
        self.assertEqual((s['total'], s['passed'], s['by_check']['S1']), (2, 1, 1))
        self.assertIn('| mosh | 2 | 1', run.report_md(rows, 'т'))
