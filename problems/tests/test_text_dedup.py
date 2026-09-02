"""Утилиты сопоставления текстов задач — `problems/text_dedup.py`.

Тест намеренно НЕ трогает базу (`SimpleTestCase`): проверяется чистая
арифметика строк, а не запросы. Команда `find_olympiad_text_duplicates`
проверяется отдельно, в `test_find_olympiad_text_duplicates.py`.

⚠️ ГЛАВНОЕ ЗДЕСЬ — `extract_numeric_tokens`. Она стоит воротами перед
записью в `OlympiadRef`: два условия с одинаковой структурой фразы, но
разными исходными данными («$P = 100 - Q$» вместо «$P = 90 - 2Q$») — это
РАЗНАЯ задача с другим ответом, а не копия, даже при сходстве текста 98 %.
"""
from collections import Counter

from django.test import SimpleTestCase

from problems.text_dedup import (
    extract_numeric_tokens,
    fuzzy_ratio,
    normalize_for_compare,
    numeric_tokens_match,
    text_fingerprint,
)


class ExtractNumericTokensTests(SimpleTestCase):
    """Числа условия как мультимножество: порядок неважен, состав — критичен."""

    def test_перестановка_чисел_не_меняет_мультимножество(self):
        """Случай из задания: те же числа, переставленные местами."""
        a = extract_numeric_tokens('P = 100 - 2Q, Q = 30')
        b = extract_numeric_tokens('Q = 30, P = 100 - 2Q')
        self.assertEqual(a, b)
        self.assertTrue(numeric_tokens_match(a, b))

    def test_другое_число_ломает_совпадение(self):
        """100 против 90 — разные исходные данные, значит разная задача."""
        a = extract_numeric_tokens('P = 100 - 2Q')
        b = extract_numeric_tokens('P = 90 - 2Q')
        self.assertNotEqual(a, b)
        self.assertFalse(numeric_tokens_match(a, b))

    def test_это_мультимножество_а_не_множество(self):
        """Число, повторённое дважды, не то же самое, что одно число.

        Иначе «фирма A и фирма B выпускают по 10» совпало бы с «фирма
        выпускает 10», а это разные условия.
        """
        self.assertNotEqual(
            extract_numeric_tokens('10 и 10'),
            extract_numeric_tokens('10'),
        )
        self.assertEqual(extract_numeric_tokens('10 и 10'), Counter({'10': 2}))

    def test_запятая_и_точка_один_и_тот_же_разделитель(self):
        self.assertEqual(
            extract_numeric_tokens('цена 0,5'),
            extract_numeric_tokens('цена 0.5'),
        )

    def test_латеховская_запятая_читается_как_разделитель(self):
        """«0{,}5» — то же число, что «0,5». Регулярка взята из text_clean."""
        self.assertEqual(
            extract_numeric_tokens('$0{,}5$'),
            extract_numeric_tokens('0,5'),
        )

    def test_хвостовые_нули_не_создают_разных_чисел(self):
        """100 и 100,0 — одно число, записанное по-разному."""
        self.assertEqual(
            extract_numeric_tokens('Q = 100'),
            extract_numeric_tokens('Q = 100,0'),
        )

    def test_знак_числа_учитывается(self):
        """−5 и 5 — разные числа. Урок свипа Батча 2 про подмену знака."""
        self.assertNotEqual(
            extract_numeric_tokens('прибыль -5'),
            extract_numeric_tokens('прибыль 5'),
        )

    def test_юникодный_минус_равен_дефису(self):
        self.assertEqual(
            extract_numeric_tokens('−5'),
            extract_numeric_tokens('-5'),
        )

    def test_пустой_текст_даёт_пустое_мультимножество(self):
        self.assertEqual(extract_numeric_tokens(''), Counter())
        self.assertEqual(extract_numeric_tokens(None), Counter())
        self.assertTrue(numeric_tokens_match(
            extract_numeric_tokens(''), extract_numeric_tokens('текст без чисел')))


class NormalizeForCompareTests(SimpleTestCase):
    """Нормализация ДЛЯ СРАВНЕНИЯ. Числа и знаки не трогает вовсе."""

    def test_регистр_и_пробелы_схлопываются(self):
        self.assertEqual(
            normalize_for_compare('  Фирма   МАКСИМИЗИРУЕТ\n\tприбыль '),
            'фирма максимизирует прибыль',
        )

    def test_неразрывный_пробел_это_пробел(self):
        self.assertEqual(
            normalize_for_compare('цена равна'),
            normalize_for_compare('цена равна'),
        )

    def test_все_виды_тире_сводятся_к_одному(self):
        """Источники пишут минус по-разному; для сравнения это одно и то же."""
        for dash in ('‐', '‑', '–', '—', '−'):
            self.assertEqual(
                normalize_for_compare(f'спрос {dash} предложение'),
                'спрос - предложение',
            )

    def test_числа_остаются_нетронутыми(self):
        """Предохранитель: нормализация не имеет права менять числа."""
        text = 'P = 100 - 2Q, при Q = 30,5 и -7'
        self.assertEqual(
            extract_numeric_tokens(text),
            extract_numeric_tokens(normalize_for_compare(text)),
        )

    def test_отпечаток_устойчив_и_различает(self):
        self.assertEqual(
            text_fingerprint(normalize_for_compare('Фирма  максимизирует')),
            text_fingerprint(normalize_for_compare('фирма максимизирует')),
        )
        self.assertNotEqual(
            text_fingerprint('фирма максимизирует'),
            text_fingerprint('фирма минимизирует'),
        )


class FuzzyRatioTests(SimpleTestCase):
    """rapidfuzz отдаёт 0..100 — наружу выпускаем долю 0..1."""

    def test_одинаковый_текст_даёт_единицу(self):
        self.assertEqual(fuzzy_ratio('спрос и предложение', 'спрос и предложение'), 1.0)

    def test_значение_лежит_в_единичном_отрезке(self):
        r = fuzzy_ratio('спрос и предложение', 'спрос и предложение фирмы')
        self.assertGreater(r, 0.0)
        self.assertLess(r, 1.0)

    def test_порядок_слов_ЗНАЧИМ(self):
        """Обоснование выбора fuzz.ratio вместо token_sort_ratio.

        token_sort_ratio отсортировал бы слова и объявил эти две фразы
        одинаковыми. В олимпиадной экономике словарь беден и повторяем
        («спрос», «предложение», «фирма»), поэтому сортировка слов
        надувала бы сходство РАЗНЫХ задач — а порядок слов в настоящей
        копии сохраняется.
        """
        self.assertLess(
            fuzzy_ratio('спрос превышает предложение', 'предложение превышает спрос'),
            1.0,
        )
