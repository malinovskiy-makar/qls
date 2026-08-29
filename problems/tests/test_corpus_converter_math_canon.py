# -*- coding: utf-8 -*-
"""Фаза 1 сессии 2026-08-27: канонизация math (Шаг 2 архитектуры аудита).

Отдельная стадия ПОСЛЕ `convert_text_field`, а не правка внутри него.
Причина: у `convert_text_field` есть свой проверенный контракт и тесты
(`test_corpus_converter_core.py`, живые регрессии #41612/#26337), и
менять его семантику молча — ровно та ошибка, из-за которой прежний
шлюз считал себя готовым. Канонизация добавляется поверх, старый этап
остаётся дословно прежним.
"""
from django.test import SimpleTestCase

from problems.corpus_converter.core import convert_text_field
from problems.corpus_converter.math_canon import (
    canonicalize, normalize_unicode_operators, strip_nested_delimiters,
    wrap_natural_language,
)


class NestedDelimiterTests(SimpleTestCase):
    """K-ERR аудита: вложенный `$` внутри display math роняет KaTeX."""

    def test_30172_nested_dollars_inside_display_math(self):
        # Живой #30172: внутри \[..\] стоят $x=0$ и $y=0$ — KaTeX падает
        # с «Can't use function '$' in math mode» (воспроизведено в Фазе -1).
        text = ('\\[\nTR=\n\\begin{cases}\n 12-3x+2x, & x\\leq3 \\xrightarrow{} $x=0$'
                '\n\n 4-\\frac{x}{3}+2x, & x\\geq3 \\xrightarrow{} $y=0$\n\\end{cases}\n\\]')
        result = canonicalize(text)
        self.assertNotIn('$x=0$', result)
        self.assertIn('x=0', result)
        self.assertIn('y=0', result)

    def test_strip_nested_handles_all_four_pairs(self):
        self.assertEqual(strip_nested_delimiters(r'a $b$ \(c\) \[d\] $$e$$ f'),
                         'a b c d e f')

    def test_strip_nested_is_recursive(self):
        self.assertEqual(strip_nested_delimiters(r'$\(x\)$'), 'x')


class BareEnvironmentTests(SimpleTestCase):
    """R-ENV аудита: math-окружение вне разделителей остаётся сырым текстом."""

    def test_bare_equation_star_gets_display_wrapper(self):
        # ⚠️ Аудит советовал «equation* снаружи убрать». Прямой замер
        # настоящим KaTeX 0.16.9 показал, что окружение ПОДДЕРЖИВАЕТСЯ —
        # снимать его не нужно, достаточно обёртки $$. Тест закрепляет
        # замеренное поведение, а не рекомендацию.
        text = '\\begin{equation*}\nx = y + 1\n\\end{equation*}'
        result = canonicalize(text)
        self.assertTrue(result.strip().startswith('$$'))
        self.assertTrue(result.strip().endswith('$$'))
        self.assertIn('\\begin{equation*}', result)

    def test_multline_replaced_with_supported_equivalent(self):
        # Замер: KaTeX 0.16.9 даёт «No such environment: multline».
        text = '\\begin{multline*}\na + b \\\\ + c\n\\end{multline*}'
        result = canonicalize(text)
        self.assertNotIn('multline', result)
        self.assertIn('\\begin{gathered}', result)

    def test_eqnarray_replaced_with_aligned(self):
        text = r'\begin{eqnarray}a & = & b\end{eqnarray}'
        result = canonicalize(text)
        self.assertNotIn('eqnarray', result)
        self.assertIn('\\begin{aligned}', result)

    def test_subequations_wrapper_removed(self):
        text = r'\begin{subequations}\begin{aligned}a & = b\end{aligned}\end{subequations}'
        result = canonicalize(text)
        self.assertNotIn('subequations', result)
        self.assertIn('\\begin{aligned}', result)

    def test_bare_cases_gets_display_wrapper_and_keeps_environment(self):
        # cases — внутреннее окружение: обёртка $$ нужна, но само
        # \begin{cases} обязано остаться, иначе KaTeX не построит скобку.
        text = r'\begin{cases}a & b \\ c & d\end{cases}'
        result = canonicalize(text)
        self.assertIn(r'\begin{cases}', result)
        self.assertTrue(result.strip().startswith('$$'))

    def test_environment_already_inside_math_not_double_wrapped(self):
        text = r'$$\begin{cases}a & b \\ c & d\end{cases}$$'
        self.assertEqual(canonicalize(text).count('$$'), 2)

    def test_non_math_environment_left_for_phase4(self):
        # quote/tabular — не математика, их маршрут другой (семантический
        # HTML). Канонизация math их не трогает и не портит.
        text = r'\begin{quote}цитата\end{quote}'
        self.assertIn(r'\begin{quote}', canonicalize(text))


class NaturalLanguageTests(SimpleTestCase):
    """K-TEXT аудита: русский текст в math mode слипается в кашу."""

    def test_30081_russian_condition_wrapped_in_text(self):
        # Живой #30081: «если» дважды внутри cases, без \text{}.
        text = (r'$$Q(L, K) = \min[L^2, K] = \begin{cases}L^2, & если L^2 \leq K; '
                r'\\ K, & если L^2 > K,\end{cases}$$')
        result = canonicalize(text)
        self.assertIn(r'\text{если }', result)
        self.assertNotIn('& если', result)

    def test_30528_already_wrapped_text_not_double_wrapped(self):
        # Живой #30528: там \text{если } УЖЕ стоит — второй обёртки быть
        # не должно, иначе получится \text{\text{если }}.
        text = r'$Q_s = \begin{cases} 100, \; \text{если } P \geq 0.2 \end{cases}$'
        result = canonicalize(text)
        self.assertNotIn(r'\text{\text{', result)
        self.assertEqual(result.count(r'\text{'), 1)

    def test_trailing_space_kept_inside_braces(self):
        # В math mode пробел вне \text{} игнорируется: без пробела ВНУТРИ
        # скобок «если» слиплось бы со следующим символом.
        self.assertEqual(wrap_natural_language('& если x'), r'& \text{если }x')

    def test_multiword_russian_phrase_wrapped_as_one(self):
        result = wrap_natural_language('& если покупатель приобретает товар')
        self.assertIn(r'\text{если покупатель приобретает товар}', result)

    def test_latin_and_math_untouched(self):
        self.assertEqual(wrap_natural_language(r'x \leq 3 \cdot Q_s'),
                         r'x \leq 3 \cdot Q_s')


class UnicodeOperatorTests(SimpleTestCase):
    """Шаг 2 аудита: `≤ ≥ ∈ → √` и типографские минусы — в TeX-команды."""

    def test_comparison_operators(self):
        self.assertEqual(normalize_unicode_operators('a ≤ b ≥ c ≠ d'),
                         r'a \le  b \ge  c \ne  d')

    def test_membership_and_arrow(self):
        self.assertEqual(normalize_unicode_operators('x ∈ A → B'),
                         r'x \in  A \to  B')

    def test_sqrt_takes_following_token(self):
        self.assertEqual(normalize_unicode_operators('√x'), r'\sqrt{x}')
        self.assertEqual(normalize_unicode_operators('√{ab}'), r'\sqrt{ab}')

    def test_typographic_minus_becomes_ascii(self):
        self.assertEqual(normalize_unicode_operators('5 − 3'), '5 - 3')

    def test_applied_only_inside_math(self):
        # Тире в обычном тексте — типографика, её нормализует core, а не
        # эта функция. Канонизация math не должна лезть в прозу.
        text = 'обычный текст — с тире и знаком ≤ вне формулы'
        self.assertEqual(canonicalize(text), text)


class CurrencyEscapingTests(SimpleTestCase):
    """DOLLAR аудита: мало ОПОЗНАТЬ валюту — надо не дать браузеру её спарить.

    Замерено настоящим KaTeX: после одной лишь канонизации #26828/#35228
    оставались с `K-TEXT`, потому что голый `$` в выводе браузерный
    auto-render всё равно спаривал с соседним.
    """

    def test_26828_suffix_currency_escaped_in_output(self):
        text = 'стоимость около 3000$ за тонну, снижение до 1300$ за тонну'
        result = canonicalize(text)
        self.assertIn(r'3000\$', result)
        self.assertIn(r'1300\$', result)

    def test_35228_prefix_currency_escaped_in_output(self):
        text = 'ожидала заработать $200 в магазине, заработала только $150.'
        result = canonicalize(text)
        self.assertIn(r'\$200', result)
        self.assertIn(r'\$150', result)

    def test_real_math_dollars_not_escaped(self):
        text = r'при $\lambda > x$ найдите $x$.'
        result = canonicalize(text)
        self.assertNotIn(r'\$', result)
        self.assertIn(r'$\lambda > x$', result)

    def test_already_escaped_currency_stays_single_escaped(self):
        self.assertEqual(canonicalize(r'цена \$100'), r'цена \$100')


class PipelineTests(SimpleTestCase):
    """Совместимость со стадией 1 и идемпотентность."""

    def test_41612_stage1_output_survives_canonicalization(self):
        # Живая регрессия прошлых сессий: #41612 чинится стадией 1
        # (разделители строк cases). Канонизация не должна её ломать —
        # только добавить \text{} вокруг русского условия.
        text = ('\\[ U^\\theta(q,p) = \n\\begin{cases}\n'
                '\\theta\\sqrt{q} - p, & если покупатель приобретает товар \n\n'
                '0, & если отказывается от покупки\n\\end{cases} \\]')
        stage1 = convert_text_field(text)
        self.assertEqual(stage1['warnings'], [])
        result = canonicalize(stage1['text_md'])
        self.assertIn(r'\\', result)               # разделитель строк на месте
        self.assertIn(r'\text{', result)           # русское условие обёрнуто
        self.assertIn(r'\begin{cases}', result)

    def test_canonicalize_is_idempotent(self):
        for text in [
            r'$$\begin{cases}L^2, & если x \leq K \\ K, & если x > K\end{cases}$$',
            '\\begin{equation*}\nx = y\n\\end{equation*}',
            r'\[a $b$ c\]',
            'обычный текст без формул',
        ]:
            once = canonicalize(text)
            self.assertEqual(canonicalize(once), once, f'не идемпотентно: {text!r}')

    def test_plain_text_unchanged(self):
        text = 'Фирма производит товар. Найдите равновесие.'
        self.assertEqual(canonicalize(text), text)
