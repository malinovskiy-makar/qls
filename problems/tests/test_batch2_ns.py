# -*- coding: utf-8 -*-
"""Тесты классификации new_sentence по происхождению (problems/batch2_ns.py)
и общего трёхуровневого отката revert_with_recleaning."""
from django.test import SimpleTestCase

from problems.batch2_ns import (
    build_fund, classify_field, display_dollar_pairs_balanced,
    origin_normalize, origin_nums, origin_words, wrap_bare_arrays,
    wrap_invariant_holds)
from problems.batch2_unblock import revert_with_recleaning, sweep_field


class OriginNormalizeTests(SimpleTestCase):
    def test_text_wrappers_unwrapped(self):
        self.assertEqual(origin_normalize(r'\text{Цена} & \textbf{Output}'),
                         'Цена Output')

    def test_array_scaffolding_removed(self):
        norm = origin_normalize(
            r'$$\begin{array}{|l|c|}\hline \text{A} & 10 \\ \hline\end{array}$$')
        self.assertNotIn('begin', norm)
        self.assertNotIn('array', norm)
        self.assertNotIn('hline', norm)
        self.assertNotIn('&', norm)
        self.assertNotIn('$', norm)
        self.assertIn('10', norm)

    def test_braced_decimal_and_colon(self):
        self.assertEqual(origin_nums(origin_normalize('1047{,}62')),
                         origin_nums(origin_normalize('1047.62')))

    def test_nums_comma_dot_equal(self):
        self.assertEqual(origin_nums('цена 1047,62 руб'), ['1047.62'])
        self.assertEqual(origin_nums('цена 1047.62 руб'), ['1047.62'])

    def test_nums_trailing_punct_stripped(self):
        self.assertEqual(origin_nums('равно 40.'), ['40'])

    def test_words_case_and_yo(self):
        self.assertEqual(origin_words('Товар товАр отчёт'),
                         ['товар', 'товар', 'отчет'])
        # короткие ярлыки (<3 букв) словами не считаются
        self.assertEqual(origin_words('AD | ЧП'), [])


class ClassifyFieldTests(SimpleTestCase):
    def _fund(self, *texts):
        return build_fund(list(texts))

    def test_table_with_origin_is_table_keep(self):
        nums, words = self._fund(
            'Цена облигации A равна 1047,62; купон 10 процентов.')
        old = 'Информация о них приведена ниже:'
        cur = (old + '\n\n' + r'\begin{array}{|l|c|}\hline'
               r'\text{Цена} & 1047{,}62 \\ \hline \text{купон} & 10 \\ '
               r'\hline\end{array}')
        res = classify_field(old, cur, nums, words)
        self.assertEqual(res['verdict'], 'TABLE_KEEP')

    def test_table_with_foreign_number_reverts(self):
        nums, words = self._fund('Цена облигации A равна 1047,62.')
        old = 'Информация:'
        cur = (old + r' \begin{array}{|c|}\hline \text{Цена} & 999 \\'
               r' \hline\end{array}')
        res = classify_field(old, cur, nums, words)
        self.assertEqual(res['verdict'], 'REVERT')
        self.assertTrue(any('table_block_without_origin' in r
                            for r in res['reasons']))

    def test_table_with_foreign_word_reverts(self):
        nums, words = self._fund('Цена равна 100.')
        old = 'Информация:'
        cur = (old + r' \begin{array}{|c|}\hline \text{Внезапный} & 100 \\'
               r' \hline\end{array}')
        res = classify_field(old, cur, nums, words)
        self.assertEqual(res['verdict'], 'REVERT')

    def test_moved_text_with_origin_is_moved_keep(self):
        # слова и числа фрагмента живут в ДРУГОМ поле той же задачи (фонд)
        nums, words = self._fund('Ответ: выпуск Increase, прибыль Decrease.')
        old = 'Increase'
        cur = 'Increase / Decrease / Increase'
        res = classify_field(old, cur, nums, words)
        self.assertEqual(res['verdict'], 'MOVED_KEEP')

    def test_moved_new_number_without_origin_reverts(self):
        nums, words = self._fund('В корзине было пять яблок и щенок Шарик.')
        old = 'Сколько яблок в корзине?'
        cur = 'Сколько яблок в корзине? Считайте, что яблок было 17 штук.'
        res = classify_field(old, cur, nums, words)
        self.assertEqual(res['verdict'], 'REVERT')
        self.assertTrue(any('new_number_without_origin' in r
                            for r in res['reasons']))

    def test_moved_low_word_coverage_reverts(self):
        nums, words = self._fund('Спрос и предложение.')
        old = 'Спрос.'
        cur = ('Спрос. Совершенно посторонний выдуманный текст про '
               'бабушкин компот и палисадник.')
        res = classify_field(old, cur, nums, words)
        self.assertEqual(res['verdict'], 'REVERT')

    def test_same_field_no_fragments_is_boundary_keep(self):
        nums, words = self._fund('Текст задачи.')
        res = classify_field('Текст задачи.', 'Текст задачи.', nums, words)
        self.assertEqual(res['verdict'], 'MOVED_KEEP')
        self.assertTrue(any('no_new_fragments_on_recheck' in r
                            for r in res['reasons']))


class WrapBareArraysTests(SimpleTestCase):
    BARE = ('Текст до.\n\n'
            r'\begin{array}{|c|c|}\hline 1 & 2 \\ \hline\end{array}'
            '\n\nТекст после.')

    def test_bare_array_wrapped(self):
        wrapped, n = wrap_bare_arrays(self.BARE)
        self.assertEqual(n, 1)
        self.assertIn(r'$$\begin{array}', wrapped)
        self.assertIn(r'\end{array}$$', wrapped)
        self.assertTrue(display_dollar_pairs_balanced(wrapped))
        # больше ничего не изменилось
        self.assertEqual(wrapped.replace('$$', ''), self.BARE)

    def test_already_wrapped_untouched(self):
        already = ('До $$' + r'\begin{array}{|c|}\hline 1 \\ \hline\end{array}'
                   + '$$ после.')
        wrapped, n = wrap_bare_arrays(already)
        self.assertEqual(n, 0)
        self.assertEqual(wrapped, already)

    def test_idempotent(self):
        once, n1 = wrap_bare_arrays(self.BARE)
        twice, n2 = wrap_bare_arrays(once)
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 0)
        self.assertEqual(twice, once)

    def test_two_bare_arrays_both_wrapped(self):
        text = self.BARE + '\n\nЕщё:\n' + \
            r'\begin{array}{|c|}\hline 3 \\ \hline\end{array}'
        wrapped, n = wrap_bare_arrays(text)
        self.assertEqual(n, 2)
        self.assertTrue(display_dollar_pairs_balanced(wrapped))

    def test_inline_math_not_confused(self):
        text = 'Пусть $x=1$ и таблица: ' + \
            r'\begin{array}{|c|}\hline 5 \\ \hline\end{array}'
        wrapped, n = wrap_bare_arrays(text)
        self.assertEqual(n, 1)
        self.assertIn('$x=1$', wrapped)

    def test_no_array_no_change(self):
        wrapped, n = wrap_bare_arrays('Обычный текст с $x=1$.')
        self.assertEqual(n, 0)
        self.assertEqual(wrapped, 'Обычный текст с $x=1$.')

    def test_currency_dollar_becomes_textdollar_inside_block(self):
        # \$ внутри $$...$$ роняет KaTeX боевых страниц (maskEscapedDollars
        # ставит часовой U+E000 до рендера) — внутри блока меняем на
        # \textdollar, снаружи блока \$ не трогаем
        text = ('Цена \\$5 за штуку.\n'
                r'\begin{array}{|c|}\hline 1047{,}62\$ \\ \hline\end{array}')
        wrapped, n = wrap_bare_arrays(text)
        self.assertEqual(n, 1)
        self.assertNotIn('\\$', wrapped.split('$$')[1])
        self.assertIn('\\textdollar', wrapped)
        self.assertIn('Цена \\$5', wrapped)
        self.assertTrue(wrap_invariant_holds(text, wrapped))
        self.assertTrue(display_dollar_pairs_balanced(wrapped))
        # идемпотентность сохранена
        twice, n2 = wrap_bare_arrays(wrapped)
        self.assertEqual(n2, 0)
        self.assertEqual(twice, wrapped)

    def test_wrap_invariant_catches_foreign_change(self):
        self.assertFalse(wrap_invariant_holds('Текст 40.', 'Текст 45.'))


class RevertWithRecleaningTests(SimpleTestCase):
    def test_plain_text_roundtrip(self):
        res = revert_with_recleaning('Простое условие. Цена равна 40 рублям.')
        self.assertEqual(res['level'], 'full')
        self.assertTrue(res['glue_idempotent'])
        self.assertNotEqual(
            sweep_field('Простое условие. Цена равна 40 рублям.',
                        res['final'])['verdict'],
            'digit_sign_change')

    def test_final_never_introduces_digit_change(self):
        # сырой текст с %-комментарием: какой бы уровень ни был принят,
        # пересвип финала против ДО не должен видеть подмену чисел
        raw = ('Задача про ставку 12% годовых % комментарий\n'
               'и вклад 1000 рублей на 2 года.')
        res = revert_with_recleaning(raw)
        self.assertIn(res['level'], ('full', 'glue_only', 'raw'))
        self.assertNotEqual(sweep_field(raw, res['final'])['verdict'],
                            'digit_sign_change')
