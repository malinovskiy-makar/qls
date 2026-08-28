# -*- coding: utf-8 -*-
"""Фазы 4-5 сессии 2026-08-27: текстовые окружения и реестр макросов."""
from django.test import SimpleTestCase

from problems.corpus_converter.macros import (
    KNOWN_UNRESOLVED_MACROS, apply_macro_fixes, find_unresolved_macros,
)
from problems.corpus_converter.text_env import convert_text_environments


class QuoteTests(SimpleTestCase):
    """#30058: `\\begin{quote}` виден сырым (коды QUOTE, R-ENV)."""

    def test_30058_quote_wrapper_removed_text_kept(self):
        text = ('сделал заявление:\n \\begin{quote}\n Денег нет, но вы держитесь!\n'
                ' \\end{quote}\nдалее по тексту')
        result = convert_text_environments(text)
        self.assertNotIn(r'\begin{quote}', result)
        self.assertNotIn(r'\end{quote}', result)
        self.assertIn('Денег нет, но вы держитесь!', result)

    def test_nested_wrappers_unwrapped_recursively(self):
        text = r'\begin{center}\begin{quote}текст\end{quote}\end{center}'
        result = convert_text_environments(text)
        self.assertEqual(result.strip(), 'текст')


class FloatAndCaptionTests(SimpleTestCase):
    def test_figure_wrapper_removed_caption_text_kept(self):
        text = r'\begin{figure}\caption{График спроса}\label{fig:1}\end{figure}'
        result = convert_text_environments(text)
        self.assertNotIn(r'\begin{figure}', result)
        self.assertIn('График спроса', result)
        self.assertNotIn(r'\label', result)

    def test_booktabs_rules_removed(self):
        text = r'\toprule Чистые продажи \midrule Производство \bottomrule'
        result = convert_text_environments(text)
        for cmd in (r'\toprule', r'\midrule', r'\bottomrule'):
            self.assertNotIn(cmd, result)
        self.assertIn('Чистые продажи', result)

    def test_href_becomes_plain_text(self):
        # Тега `a` в allow-list нет, ссылку строить нечем — остаётся текст.
        self.assertEqual(
            convert_text_environments(r'см. \href{https://x.ru}{тут}').strip(),
            'см. тут')

    def test_section_title_text_kept(self):
        self.assertIn('Задача 5', convert_text_environments(r'\section{Задача 5}'))


class MathUntouchedTests(SimpleTestCase):
    """Внутри формулы `\\text{}`/`\\label` имеют другой смысл — не трогаем."""

    def test_math_token_passed_through_verbatim(self):
        text = r'формула $\text{если } x \le 3$ и \begin{quote}цитата\end{quote}'
        result = convert_text_environments(text)
        self.assertIn(r'$\text{если } x \le 3$', result)
        self.assertNotIn(r'\begin{quote}', result)

    def test_display_math_untouched(self):
        text = r'\[\begin{cases}a & b\end{cases}\]'
        self.assertEqual(convert_text_environments(text), text)


class MacroFixTests(SimpleTestCase):
    """Раздел 7 аудита: опечатки чиним, неизвестное — не гадаем."""

    def test_41118_tilde_typo_fixed(self):
        self.assertEqual(apply_macro_fixes(r'q < \Tilde{p}'), r'q < \tilde{p}')

    def test_known_typos_fixed(self):
        self.assertEqual(apply_macro_fixes(r'\tesxt{a}'), r'\text{a}')
        self.assertEqual(apply_macro_fixes(r'\qaud'), r'\quad')
        self.assertEqual(apply_macro_fixes(r'\rig'), r'\Rightarrow')

    def test_fix_does_not_eat_longer_command(self):
        # `\rig` не имеет права съесть `\right`, `\Tilde` — `\Tilder`.
        self.assertEqual(apply_macro_fixes(r'\right)'), r'\right)')
        self.assertEqual(apply_macro_fixes(r'\Tilder'), r'\Tilder')

    def test_42463_unknown_macro_not_guessed(self):
        # `\soso` остаётся как есть — его поймает шлюз кодом MACRO.
        self.assertIn(r'\soso', apply_macro_fixes(r'x=1\soso y=2'))
        self.assertIn(r'\soso', KNOWN_UNRESOLVED_MACROS)

    def test_unresolved_macros_read_from_katex_messages(self):
        messages = [
            'KaTeX parse error: Undefined control sequence: \\soso at position 3',
            'KaTeX parse error: Undefined control sequence: \\headic at position 9',
            "KaTeX parse error: Can't use function '$' in math mode",
        ]
        self.assertEqual(find_unresolved_macros(messages), [r'\soso', r'\headic'])

    def test_non_macro_errors_are_not_reported_as_macros(self):
        self.assertEqual(
            find_unresolved_macros(["KaTeX parse error: Can't use function '$'"]), [])
