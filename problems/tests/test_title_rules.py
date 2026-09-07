# -*- coding: utf-8 -*-
from django.test import TestCase

from problems.enrich import title_rules


class ClassifyCurrentTitleTests(TestCase):

    def test_пустой_заголовок_это_A(self):
        self.assertEqual(
            title_rules.classify_current_title('', 'Условие задачи.'),
            title_rules.CATEGORY_EMPTY_OR_STUB)

    def test_заглушка_тире_это_A(self):
        self.assertEqual(
            title_rules.classify_current_title('—', 'Условие задачи.'),
            title_rules.CATEGORY_EMPTY_OR_STUB)

    def test_заглушка_разное_это_A(self):
        self.assertEqual(
            title_rules.classify_current_title('Разное 3', 'Условие задачи.'),
            title_rules.CATEGORY_EMPTY_OR_STUB)

    def test_латex_разметка_это_B(self):
        self.assertEqual(
            title_rules.classify_current_title(
                r'Найти \(P^*\)', 'Совсем другое условие про рынок труда.'),
            title_rules.CATEGORY_BROKEN)

    def test_кракозябры_это_B(self):
        self.assertEqual(
            title_rules.classify_current_title(
                'Ce\x0eu\x00 zag\x0bolovok', 'Совсем другое условие.'),
            title_rules.CATEGORY_BROKEN)

    def test_имя_файла_это_B(self):
        self.assertEqual(
            title_rules.classify_current_title(
                'zadacha_12_final.docx', 'Совсем другое условие про налоги.'),
            title_rules.CATEGORY_BROKEN)

    def test_длиннее_80_символов_это_B(self):
        long_title = 'Очень ' * 20 + 'длинный заголовок'
        self.assertGreater(len(long_title), 80)
        self.assertEqual(
            title_rules.classify_current_title(long_title, 'Другое условие.'),
            title_rules.CATEGORY_BROKEN)

    def test_заголовок_префикс_условия_это_C(self):
        statement = 'Монополист выбирает цену на рынке кофе, максимизируя прибыль.'
        title = 'Монополист выбирает цену на рынке кофе'
        self.assertEqual(
            title_rules.classify_current_title(title, statement),
            title_rules.CATEGORY_ECHO)

    def test_заголовок_похож_на_начало_условия_это_C(self):
        statement = 'Фирма максимизирует прибыль при заданной технологии производства.'
        # 85%+ похоже на первые 60 символов условия, но не точный префикс
        title = 'Фирма максимизирует прибыль при заданой технологии'
        self.assertEqual(
            title_rules.classify_current_title(title, statement),
            title_rules.CATEGORY_ECHO)

    def test_нормальный_короткий_заголовок_это_D(self):
        self.assertEqual(
            title_rules.classify_current_title(
                'Дуополия Курно', 'Две фирмы конкурируют по Курно на рынке.'),
            title_rules.CATEGORY_KEEP)
