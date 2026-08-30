# -*- coding: utf-8 -*-
r"""Три обобщения конвертера по кодам аудита COMM, EMPTY-MATH, BRACE.

Главная опасность здесь — не «не почистили», а «съели текст». В базе
лежит уже деградировавший текст: импорт потерял слеш у `\%`, и в
середине фразы процент от комментария не отличить. Поэтому половина
тестов ниже — про то, что НЕ трогается.
"""
from django.test import SimpleTestCase

from problems.corpus_converter.core import (
    convert_text_field, drop_empty_math, strip_title_note, unwrap_leading_brace,
)

BS = chr(92)


class TitleNoteTests(SimpleTestCase):
    """Помета автора на строке заголовка снимается."""

    def test_author_name_after_title_is_removed(self):
        self.assertEqual(
            strip_title_note('Производство и издержки %Соня П\n\nТекст'),
            'Производство и издержки\n\nТекст')

    def test_topic_tag_is_removed(self):
        self.assertEqual(
            strip_title_note('Ноу хау! %верхняя огибающая\n\nДальше'),
            'Ноу хау!\n\nДальше')

    def test_note_with_space_after_percent(self):
        self.assertEqual(
            strip_title_note('Блиц по издержкам % бета лш 57 2024\n\nX'),
            'Блиц по издержкам\n\nX')

    def test_only_the_first_line_is_touched(self):
        text = 'Заголовок %помета\n\nВ теле 20% и ещё % что-то'
        self.assertEqual(strip_title_note(text),
                         'Заголовок\n\nВ теле 20% и ещё % что-то')

    def test_single_line_field_without_newline(self):
        self.assertEqual(strip_title_note('Читеры %авторское'), 'Читеры')

    def test_idempotent(self):
        once = strip_title_note('Альфа и Тау %парабола\n\nX')
        self.assertEqual(strip_title_note(once), once)


class TitleNoteMustNotEatTextTests(SimpleTestCase):
    """Живые проценты из корпуса — их снятие съело бы конец фразы."""

    def test_digit_before_percent_is_a_percent_sign(self):
        text = 'Ставка выросла на 20% за год\n\nДальше'
        self.assertEqual(strip_title_note(text), text)

    def test_thin_space_percent_after_number_survives(self):
        """#4085: в исходнике `30\\,\\%`, в базе слеш уже потерян."""
        text = 'составляет меньше 30' + BS + ',% всего населения'
        self.assertEqual(strip_title_note(text), text)

    def test_percent_after_math_survives(self):
        """#30061: `$(100i)$ %, то долг…` — снятие съело бы предложение."""
        text = 'ставка процента равна $(100i)$ %, то долг будет равен $S_1$'
        self.assertEqual(strip_title_note(text), text)

    def test_percent_inside_parentheses_survives(self):
        """#34178: `($APC$) равна (в %)?`"""
        text = 'склонность ($APC$) равна (в %)? Это доля дохода.'
        self.assertEqual(strip_title_note(text), text)

    def test_percent_after_variable_in_math_survives(self):
        """#39669: `скидка $x$ % (где $x>0$)`"""
        text = 'ему полагается скидка $x$ % (где $x >0$) на кофе'
        self.assertEqual(strip_title_note(text), text)

    def test_escaped_percent_is_not_a_comment(self):
        text = 'Доля равна 50' + BS + '% населения'
        self.assertEqual(strip_title_note(text), text)


class EmptyMathTests(SimpleTestCase):

    def test_empty_display_math_removed(self):
        self.assertEqual(drop_empty_math('текст $$$$ хвост'), 'текст  хвост')

    def test_empty_display_math_with_spaces_removed(self):
        self.assertEqual(drop_empty_math('a $$  $$ b'), 'a  b')

    def test_empty_bracket_math_removed(self):
        self.assertEqual(drop_empty_math('a ' + BS + '[' + BS + '] b'), 'a  b')

    def test_real_math_untouched(self):
        text = 'цена $$p=2q+1$$ здесь'
        self.assertEqual(drop_empty_math(text), text)

    def test_inline_math_pair_untouched(self):
        """`$x$` — не пустой разделитель, трогать нельзя."""
        text = 'пусть $x$ и $y$'
        self.assertEqual(drop_empty_math(text), text)

    def test_idempotent(self):
        once = drop_empty_math('a $$$$ b')
        self.assertEqual(drop_empty_math(once), once)


class LeadingBraceTests(SimpleTestCase):

    def test_title_in_braces_is_unwrapped(self):
        self.assertEqual(unwrap_leading_brace('{Подарочная}\n\nТекст'),
                         'Подарочная\n\nТекст')

    def test_nested_braces_left_alone(self):
        """Внутри свои скобки — это чужая разметка, не остаток команды."""
        text = '{a {b} c}\n\nТекст'
        self.assertEqual(unwrap_leading_brace(text), text)

    def test_braces_inside_a_sentence_left_alone(self):
        text = 'множество {1, 2, 3} задано\n\nX'
        self.assertEqual(unwrap_leading_brace(text), text)

    def test_idempotent(self):
        once = unwrap_leading_brace('{Двоечники и физика}\n\nX')
        self.assertEqual(unwrap_leading_brace(once), once)


class PipelineTests(SimpleTestCase):
    """Через весь конвейер, а не только через отдельную функцию."""

    def test_all_three_through_convert_text_field(self):
        out = convert_text_field('{Подарочная} %Соня П\n\nЦена $$$$ равна 5')
        self.assertNotIn('%', out['text_md'])
        self.assertNotIn('$$$$', out['text_md'])
        self.assertIn('Подарочная', out['text_md'])
        self.assertNotIn('{Подарочная}', out['text_md'])

    def test_pipeline_is_idempotent(self):
        once = convert_text_field('{Блиц} %Авторская\n\nтекст $$$$ и 20%')['text_md']
        twice = convert_text_field(once)['text_md']
        self.assertEqual(once, twice)

    def test_pipeline_keeps_percent_sign(self):
        out = convert_text_field('Рост на 20% за год')['text_md']
        self.assertIn('20% за год', out)
