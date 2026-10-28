"""Правила двигателя импорта эталона, добавленные ночью 28→29.10.2026 (сессия P1):
числовой отпечаток (гейт 1 И3), заголовки (решение 15.10), тестовые вопросы,
слаг предпринимательства, варианты в одном файле, замена текста официальным,
обновление своих задач из новой версии эталона.

Данные выдуманные, модель не вызывается.
"""
from django.test import SimpleTestCase

from problems.olympiad_audit import bank_match as bm
from problems.olympiad_audit import title_rule as tr


class NumberFingerprintTests(SimpleTestCase):
    """Каждый пример гейта 1 И3 — с обеих сторон: эталон и банк."""

    CASES = [
        (r'Доход $60 \ 000$ руб.', 'Доход 60000 руб.'),
        (r'Цена $900 \ 000$ руб.', 'Цена 900 000 руб.'),
        ('Выручка 200\n000 руб.', 'Выручка 200 000 руб.'),
        (r'Затраты $7\,000$', 'Затраты 7000'),
        ('Выпуск $70~000$', 'Выпуск 70 000'),
        ('Ставка $2{,}5$ %', 'Ставка 2,5 %'),
    ]

    def test_examples_match_both_ways(self):
        for ref, bank in self.CASES:
            with self.subTest(ref=ref):
                self.assertEqual(bm._numbers(ref), bm._numbers(bank))
                self.assertTrue(bm.numbers_compatible(ref, bank))
                self.assertTrue(bm.numbers_compatible(bank, ref))

    def test_decimal_comma_is_not_two_numbers(self):
        self.assertEqual(dict(bm._numbers('$2{,}5$')), {'2.5': 1})

    def test_newline_glues_only_three_digit_groups(self):
        self.assertEqual(dict(bm._numbers('Q = 5\n100 руб.')), {'5': 1, '100': 1})
        self.assertEqual(dict(bm._numbers('200\n000')), {'200000': 1})

    def test_long_left_part_is_not_a_group(self):
        self.assertEqual(dict(bm._numbers('12345 678')), {'12345': 1, '678': 1})

    def test_different_numbers_still_differ(self):
        self.assertFalse(bm.numbers_compatible(r'Доход $60 \ 000$ и 25 %', 'Доход 70 000 и 30 %'))


class TitleRuleTests(SimpleTestCase):
    def test_stubs(self):
        for t in ('', 'ВП по финграмотности 2018/2019, 11 кл., задание 3', 'Задача 2',
                  'Задание 1 (25 баллов)', 'Задание 2.', 'СПРАВКА', 'Тест № 1.',
                  'МОШ по экономике 2009/10, 9 кл., задание тест-1.1'):
            with self.subTest(t=t):
                self.assertTrue(tr.is_stub(t))

    def test_real_titles(self):
        for t in ('Как не потерять деньги?', 'Будь начеку!', 'Тестирование рынка 5',
                  'ОСАГО, ДСАГО и КАСКО'):
            with self.subTest(t=t):
                self.assertFalse(tr.is_stub(t))

    def test_stub_replaced_by_good_candidate(self):
        d = tr.decide('Задание 4', 'Выбор облигации', 'Инвестор выбирает облигацию…')
        self.assertEqual((d['new'], d['changed']), ('Выбор облигации', True))

    def test_official_title_kept(self):
        d = tr.decide('Как не потерять деньги?', 'Диверсификация и риск', 'У Александра есть…')
        self.assertEqual((d['new'], d['changed']), ('Как не потерять деньги?', False))

    def test_bad_candidates_rejected(self):
        self.assertTrue(tr.candidate_problems(''))
        self.assertTrue(tr.candidate_problems('x' * 61))
        self.assertTrue(tr.candidate_problems('Задание 3 про вклады'))
        self.assertTrue(tr.candidate_problems('Олимпиада ВП: вклады'))
        self.assertEqual(tr.candidate_problems('Вклады и инфляция'), [])
        d = tr.decide('Задача 2', 'Задание 2', 'Текст')
        self.assertFalse(d['changed'])

    def test_text_start_short_kept_long_replaced(self):
        st = 'Фирма выпускает товар и продаёт его на рынке. Найдите прибыль.'
        short = tr.decide('Фирма выпускает товар', 'Прибыль фирмы', st)
        self.assertEqual((short['flag'], short['changed']), ('начало текста', False))
        long_st = ('Фирма выпускает товар и продаёт его на рынке совершенной конкуренции, '
                   'где цена задана, а издержки растут. Найдите прибыль.')
        long_title = long_st[:90]
        long = tr.decide(long_title, 'Прибыль фирмы', long_st)
        self.assertEqual((long['flag'], long['new']), ('начало текста', 'Прибыль фирмы'))
