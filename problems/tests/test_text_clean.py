"""
Санитайзер текстов: чинит оформление, НЕ ТРОГАЕТ числа и знаки.

Проверяются все виды порчи из списка ручной проверки, и на каждом —
главное правило проекта: последовательность чисел и знаков после чистки
обязана совпасть с исходной.
"""
from django.test import TestCase

from problems import text_clean
from problems.text_clean import clean, defects, number_tokens, preview_title


class KeepsNumbersTests(TestCase):
    """ГЛАВНОЕ ПРАВИЛО: чистка не меняет ни числа, ни знаки."""

    SAMPLES = [
        '$x$и $y$фирма производит 40 и 60 единиц.',
        'Издержки $TC = 2Q^2 + 10$рублей, при $Q=5$получаем 60.',
        'Эластичность равна $-1{,}22$и это больше 1 по модулю.',
        'Найдите $min(P, 100)$ при $P = -20$.',
        'Труд ($L) и капитал равны 8 и 12.',
        'Про-\nизводительность выросла на 15%.',
        'Корень √︀ выпал, но 25 осталось.',
        'Непарный $ доллар и число 7.',
    ]

    def test_numbers_never_change(self):
        for text in self.SAMPLES:
            self.assertEqual(number_tokens(text), number_tokens(clean(text)),
                             'чистка изменила числа: %r' % text)

    def test_latex_decimal_comma_is_the_same_number(self):
        self.assertEqual(number_tokens('0{,}5'), number_tokens('0,5'))

    def test_sign_flip_would_be_caught(self):
        """Проверка сверки: подмена знака обязана ловиться."""
        self.assertNotEqual(number_tokens('прирост -20'),
                            number_tokens('прирост +20'))


class SpacingTests(TestCase):
    """Самый массовый класс: 465 задач и 1 177 подпунктов (перепись)."""

    def test_space_after_math(self):
        self.assertEqual(clean('$x$и $y$фирма'), '$x$ и $y$ фирма')

    def test_space_before_math(self):
        self.assertEqual(clean('товары$x$'), 'товары $x$')

    def test_existing_space_is_not_doubled(self):
        self.assertEqual(clean('цена $P$ равна'), 'цена $P$ равна')

    def test_punctuation_after_math_stays_glued(self):
        """«$P$,» — запятая приклеена правильно, разлеплять нечего."""
        self.assertEqual(clean('цена $P$, спрос $Q$.'), 'цена $P$, спрос $Q$.')

    def test_display_math_is_not_split(self):
        text = 'Формула $$TC = FC + VC$$ и дальше текст.'
        self.assertEqual(clean(text), text)


class OperatorTests(TestCase):

    def test_bare_min_inside_math_gets_a_slash(self):
        self.assertEqual(clean('$min(a,b)$'), '$\\min(a,b)$')

    def test_operator_outside_math_is_untouched(self):
        self.assertEqual(clean('минимум min по тексту $x$'),
                         'минимум min по тексту $x$')

    def test_already_escaped_operator_is_left_alone(self):
        self.assertEqual(clean('$\\min(a,b)$'), '$\\min(a,b)$')

    def test_variable_named_like_operator_prefix_is_safe(self):
        """`minimum` — не оператор, слеш ему не нужен."""
        self.assertEqual(clean('$minimum$'), '$minimum$')


class BracketTests(TestCase):
    """«($L)» только считаем: замер нашёл в банке ровно один такой
    фрагмент, и это «($200 тыс. в год)» — доллар-валюта. Автоправка
    превратила бы цену в формулу."""

    def test_open_bracket_is_reported_not_fixed(self):
        self.assertEqual(clean('труд ($L)'), 'труд ($L)')
        self.assertIn('bracket_across_math', defects('труд ($L)'))

    def test_currency_dollar_is_not_turned_into_math(self):
        text = 'высокие зарплаты учёным ($200 тыс. в год).'
        self.assertEqual(clean(text), text)

    def test_normal_parenthetical_math_is_untouched(self):
        self.assertEqual(clean('(см. $x$)'), '(см. $x$)')


class UntouchedTests(TestCase):
    """Сомнительное не чиним — только считаем."""

    def test_hyphen_break_is_not_joined(self):
        """«денежно-\\nкредитную» склеилось бы в порчу — правило проекта."""
        text = 'денежно-\nкредитную политику'
        self.assertEqual(clean(text), text)
        self.assertIn('hyphen_break', defects(text))

    def test_stray_root_is_only_reported(self):
        text = 'осталось √︀ вместо формулы'
        self.assertEqual(clean(text), text)
        self.assertIn('stray_root', defects(text))

    def test_odd_dollars_are_only_reported(self):
        self.assertIn('odd_dollars', defects('текст $x и всё'))

    def test_clean_text_has_no_defects(self):
        self.assertEqual(defects('Обычный текст с формулой $x + 1$ внутри.'),
                         set())


class DefectListsTests(TestCase):
    """Списки «чиним» и «только считаем» покрывают все виды порчи."""

    def test_every_defect_is_classified(self):
        classified = set(text_clean.FIXED_AUTOMATICALLY) | set(
            text_clean.REPORTED_ONLY)
        self.assertEqual(classified, set(text_clean.DEFECT_NAMES))


class PreviewTitleTests(TestCase):
    """Название в списках: обрезка ПО ГРАНИЦЕ СЛОВА."""

    class FakeProblem(object):
        pk = 7

        def __init__(self, title='', statement=''):
            self.title = title
            self.statement = statement

    def test_title_wins(self):
        problem = self.FakeProblem(title='Издержки фирмы', statement='...')
        self.assertEqual(preview_title(problem), 'Издержки фирмы')

    def test_statement_is_cut_on_a_word_boundary(self):
        """Ровно тот случай с ручной проверки: «...Всего в шта-»."""
        problem = self.FakeProblem(statement=(
            'Фирма производит товары $x$и $y$, используя труд нанятых '
            'работников. Всего в штате компании двадцать человек.'))
        preview = preview_title(problem, limit=90)
        self.assertTrue(preview.endswith('…'))
        self.assertFalse(preview.rstrip('…').endswith('-'))
        # Обрыв посреди слова запрещён: последнее слово целое.
        body = preview.rstrip('…').strip()
        self.assertIn(body.split()[-1], problem.statement)

    def test_statement_is_cleaned_before_cutting(self):
        problem = self.FakeProblem(statement='Фирма выпускает $x$и $y$.')
        self.assertIn('$x$ и', preview_title(problem))

    def test_empty_problem_falls_back_to_id(self):
        self.assertEqual(preview_title(self.FakeProblem()), 'Задача #7')
