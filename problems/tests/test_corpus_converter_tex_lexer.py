# -*- coding: utf-8 -*-
"""Фаза 0 сессии 2026-08-27: TeX-aware лексер — фундамент нового шлюза.

Фикстуры — живые фрагменты из карточек аудита
(`reports/corpus_converter_scaleup/weconomics_converter_render_audit.md`),
а не выдуманные строки: аудит нашёл дефекты на этих задачах настоящим
KaTeX, значит и лексер обязан их различать на них же.
"""
from django.test import SimpleTestCase

from problems.corpus_converter.tex_lexer import (
    TokenKind, tokenize, environment_balance, strip_tex_comments_lexed,
)


def kinds(text):
    return [t.kind for t in tokenize(text)]


def of_kind(text, kind):
    return [t for t in tokenize(text) if t.kind == kind]


class CurrencyTests(SimpleTestCase):
    """`$` рядом с суммой не должен открывать формулу (класс DOLLAR аудита)."""

    def test_26828_suffix_currency_does_not_open_math(self):
        # Живой фрагмент #26828: два `$` после чисел. Прежде они спаривались
        # и весь абзац между ними уезжал в math mode.
        text = ('стоимость алюминия составляла около 3000$ за тонну. Компания '
                '«РУСАЛ» использовала заводы. После снижения цены до 1300$ за тонну')
        self.assertEqual(of_kind(text, TokenKind.INLINE_MATH), [])
        self.assertIn('3000', ''.join(t.raw for t in tokenize(text)))

    def test_35228_prefix_currency_does_not_open_math(self):
        # Живой фрагмент #35228: `$200`, `$150`, `$300`.
        text = ('Она ожидала заработать $200 в своём магазине сегодня, но '
                'заработала только $150. Однако ей нужно заплатить на $300 меньше.')
        self.assertEqual(of_kind(text, TokenKind.INLINE_MATH), [])

    def test_35228_real_math_still_recognised(self):
        # В той же задаче `$\lambda > x$` — настоящая формула, её ломать нельзя.
        text = r'Наталья предпочтёт оценивать совместно при $\lambda > x$. Найдите $x$.'
        maths = of_kind(text, TokenKind.INLINE_MATH)
        self.assertEqual([m.body for m in maths], [r'\lambda > x', 'x'])

    def test_escaped_dollar_is_currency_never_delimiter(self):
        text = r'цена \$100 и ещё \$200 сверху'
        self.assertEqual(of_kind(text, TokenKind.INLINE_MATH), [])

    def test_space_separated_suffix_currency(self):
        text = 'заплатили 200 $ за штуку, потом ещё 300 $ сверху'
        self.assertEqual(of_kind(text, TokenKind.INLINE_MATH), [])


class MathSpillTests(SimpleTestCase):
    """MATH-SPILL: проза, захваченная в math mode, — это не формула."""

    def test_prose_between_dollars_is_not_math(self):
        text = ('$Q_1$ штук продали, а потом директор завода принял решение '
                'закрыть цех полностью и уволить рабочих $Q_2$')
        # первая пара `$Q_1$` — честная формула
        maths = of_kind(text, TokenKind.INLINE_MATH)
        self.assertIn('Q_1', [m.body for m in maths])
        # проза между ними формулой не стала
        self.assertFalse(any('директор' in m.body for m in maths))

    def test_30081_connectives_inside_formula_stay_math(self):
        # Живой #30081: «если» дважды внутри cases — это законная формула,
        # а НЕ проза. Служебные связки не должны ломать распознавание.
        text = (r'$Q(L, K) = \min[L^2, K] = \begin{cases}L^2, & если L^2 \leq K; '
                r'\\ K, & если L^2 > K,\end{cases}$')
        maths = of_kind(text, TokenKind.INLINE_MATH)
        self.assertEqual(len(maths), 1)
        self.assertIn(r'\begin{cases}', maths[0].body)


class EnvironmentTests(SimpleTestCase):
    """Окружения вне math — отдельный токен, а не текст (R-ENV аудита)."""

    def test_bare_cases_outside_math_is_environment_token(self):
        text = r'формула \begin{cases}a & b \\ c & d\end{cases} конец'
        envs = of_kind(text, TokenKind.ENVIRONMENT)
        self.assertEqual([e.name for e in envs], ['cases'])

    def test_environment_inside_math_is_not_separate_token(self):
        text = r'$$\begin{cases}a & b \\ c & d\end{cases}$$'
        self.assertEqual(of_kind(text, TokenKind.ENVIRONMENT), [])
        self.assertEqual(len(of_kind(text, TokenKind.DISPLAY_MATH)), 1)

    def test_30113_unbalanced_equation_is_reported(self):
        # Живой #30113: `\begin{equation*}` без закрывающего.
        text = ('\\begin{equation*}\nVariant =\n \\begin{cases}\n 1 &если $T \\leq 300$\n'
                ' \\end{cases}\n')
        balanced, unclosed, unopened = environment_balance(text)
        self.assertFalse(balanced)
        self.assertEqual(unclosed, ['equation*'])

    def test_balanced_nested_environments(self):
        text = r'\begin{equation*}\begin{cases}a\end{cases}\end{equation*}'
        balanced, unclosed, unopened = environment_balance(text)
        self.assertTrue(balanced)
        self.assertEqual((unclosed, unopened), ([], []))

    def test_stray_end_without_begin_is_reported(self):
        text = r'текст \end{cases} ещё текст'
        balanced, unclosed, unopened = environment_balance(text)
        self.assertFalse(balanced)
        self.assertEqual(unopened, ['cases'])


class CommentTests(SimpleTestCase):
    """COMMENT: `%` — комментарий, но `20%` и `\\%` — нет."""

    def test_line_comment_removed(self):
        text = 'первая строка\n% это редакторская заметка\nвторая строка'
        self.assertNotIn('редакторская', strip_tex_comments_lexed(text))
        self.assertIn('вторая строка', strip_tex_comments_lexed(text))

    def test_percent_after_number_is_not_comment(self):
        text = 'ставка выросла на 20% за год'
        self.assertEqual(strip_tex_comments_lexed(text), text)

    def test_escaped_percent_is_not_comment(self):
        text = r'ставка выросла на 20\% за год'
        self.assertEqual(strip_tex_comments_lexed(text), text)

    def test_mid_line_comment_removed_but_text_before_kept(self):
        text = 'видимый текст % скрытая заметка\nследующая строка'
        result = strip_tex_comments_lexed(text)
        self.assertIn('видимый текст', result)
        self.assertNotIn('скрытая заметка', result)

    def test_percent_inside_math_is_not_comment(self):
        text = r'$x \% y$ и текст'
        self.assertIn(r'\%', strip_tex_comments_lexed(text))


class DisplayMathTests(SimpleTestCase):
    def test_all_four_delimiter_pairs(self):
        self.assertEqual(kinds('$$a$$'), [TokenKind.DISPLAY_MATH])
        self.assertEqual(kinds(r'\[a\]'), [TokenKind.DISPLAY_MATH])
        self.assertEqual(kinds(r'\(a\)'), [TokenKind.INLINE_MATH])
        self.assertEqual(kinds('$a$'), [TokenKind.INLINE_MATH])

    def test_double_dollar_wins_over_single(self):
        # `$$` обязан проверяться раньше `$` — иначе `$$x$$` читается как
        # две пустые inline-формулы (боевой порядок из _katex_dollars.html).
        toks = tokenize('$$x$$')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].body, 'x')

    def test_unclosed_dollar_stays_text(self):
        # Незакрытый разделитель формулой не считается — так же ведёт себя
        # боевой _protect_math_and_currency.
        text = r'начало $x + 1 без закрытия'
        self.assertEqual(of_kind(text, TokenKind.INLINE_MATH), [])

    def test_roundtrip_preserves_original_text(self):
        # Инвариант лексера: склейка raw всех токенов == исходный текст.
        for text in [
            r'$$a$$ текст \begin{cases}x\end{cases} ещё $y$',
            'стоимость 3000$ за тонну и ещё 1300$',
            r'% комментарий' + '\nтекст',
            r'\[v = \begin{cases}(c-r)^a & \text{если } c \geq 0\end{cases}\]',
        ]:
            self.assertEqual(''.join(t.raw for t in tokenize(text)), text)
