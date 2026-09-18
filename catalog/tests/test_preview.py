"""Решение, повторяющее условие: копия и пересказ (аудит P0 «Стола», 18.09.2026).

Примеры — живые тексты из аудита (`reports/catalog_stol_20260917/AUDIT.md`),
укороченные: 63315 (начинается со всего условия), 2056 (цитирует кусок
условия внутри рассуждения), 27019 (короткий ответ из слов условия).
"""
from django.test import SimpleTestCase

from catalog.preview import solution_is_statement_copy, strip_statement_retell

STATEMENT_63315 = (
    'Монополист продает электроэнергию. Функция спроса единственного покупателя '
    'имеет вид $Q=\\sqrt{20-P}$. Первые $k$ единиц товара продаются по цене $p_1$; '
    'каждая последующая единица — по цене $p_2$, где $p_1>p_2>0$.\n'
    'Покупатель самостоятельно выбирает объем покупки.')
SOLUTION_63315 = STATEMENT_63315 + '\n\nПокупатель купит $Q>k$, если излишек не меньше нуля.'

STATEMENT_2056 = ('На рассматриваемом рынке выполняются законы спроса и предложения. '
                  'Известно, что произведение эластичностей постоянно и равно (–1). '
                  'Определите равновесное количество товара до вмешательства государства.')
SOLUTION_2056 = ('«На рассматриваемом рынке выполняются законы спроса и предложения». '
                 'Отсюда получаем, что одна эластичность постоянна и равна 1.')

STATEMENT_27019 = ('Внучка предлагает деду убраться у него дома, дед обычно зарабатывает '
                   '$100$ р. в час, поэтому дед отказывается. Кто прав и почему?')


class RetellTests(SimpleTestCase):

    def test_full_statement_at_the_start_is_cut(self):
        self.assertEqual(strip_statement_retell(STATEMENT_63315, SOLUTION_63315),
                         'Покупатель купит $Q>k$, если излишек не меньше нуля.')

    def test_partial_quote_inside_reasoning_is_kept(self):
        self.assertEqual(strip_statement_retell(STATEMENT_2056, SOLUTION_2056), SOLUTION_2056)

    def test_solution_that_is_only_the_statement_is_left_as_is(self):
        self.assertEqual(strip_statement_retell(STATEMENT_63315, STATEMENT_63315),
                         STATEMENT_63315)


class CopyTests(SimpleTestCase):

    def test_statement_repeated_as_solution_is_a_copy(self):
        self.assertTrue(solution_is_statement_copy(STATEMENT_2056, STATEMENT_2056 + ' '))

    def test_short_answer_from_statement_words_is_not_a_copy(self):
        self.assertFalse(solution_is_statement_copy(STATEMENT_27019, 'Дед прав'))

    def test_real_solution_is_not_a_copy(self):
        self.assertFalse(solution_is_statement_copy(STATEMENT_2056, SOLUTION_2056))
