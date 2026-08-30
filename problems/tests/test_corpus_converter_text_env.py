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



class LeftoverTextCommandsTests(SimpleTestCase):
    r"""Команды, которые доезжали до экрана сырыми у трёх новых источников.

    Все случаи взяты из прогона `diagnose_new_sources` по 9 608 задачам:
    код `R-CMD` стоит у 492 задач из 542 отказов, и 97 из них ломались
    ТОЛЬКО этими командами. Числа в скобках — сколько задач лечит правка.
    """

    def test_53987_ldots_outside_math_becomes_ellipsis(self):
        r"""`\ldots` в прозе (65 задач): «фирмы 3, 4, \ldots) с теми же»."""
        text = r'появляются фирмы 3, 4, \ldots) с теми же технологиями'
        result = convert_text_environments(text)
        self.assertNotIn(r'\ldots', result)
        self.assertIn('…', result)

    def test_54413_ldots_with_empty_braces(self):
        r"""`\ldots{}` — та же команда с пустой группой (живой #54413)."""
        result = convert_text_environments(r'Днём обещают дожди\ldots{} — ответил')
        self.assertNotIn(r'\ldots', result)
        self.assertNotIn('{}', result)
        self.assertIn('дожди…', result)

    def test_ldots_inside_math_is_not_touched(self):
        r"""Внутри формулы `\ldots` рисует KaTeX — трогать нельзя."""
        text = r'номера $i \in \{1, 2, 3, \ldots, n + 2\}$ фирм'
        self.assertEqual(convert_text_environments(text), text)

    def test_54179_hfill_dropped(self):
        r"""`\hfill (3 балла)` (14 задач): выключка в HTML смысла не имеет."""
        result = convert_text_environments(
            r'функция спроса $L^D = 220 - 10W$ \hfill (3 балла)')
        self.assertNotIn(r'\hfill', result)
        self.assertIn('(3 балла)', result)

    def test_53833_checkmark_becomes_symbol(self):
        r"""`\checkmark` в прозе (5 задач) — обычная галочка."""
        result = convert_text_environments(r'$TC_{LR}(8) = 32$. \checkmark')
        self.assertNotIn(r'\checkmark', result)
        self.assertIn('✓', result)

    def test_53730_boxed_outside_math_unwrapped(self):
        r"""`Ответ: \boxed{(b)}` (3 задачи) — рамку не нарисовать, текст важен."""
        result = convert_text_environments(r'Ответ: \boxed{(b)}')
        self.assertNotIn(r'\boxed', result)
        self.assertIn('(b)', result)

    def test_boxed_inside_math_is_not_touched(self):
        r"""Внутри формулы `\boxed` рисует сам KaTeX."""
        text = r'Итог $\boxed{x = 1}$ найден'
        self.assertEqual(convert_text_environments(text), text)

    def test_size_switches_dropped(self):
        r"""`\small` и `\footnotesize` — размеры, их задаёт CSS.

        В `_DROP_COMMANDS_RE` уже были `large`/`scriptsize`/`tiny`, а
        `small` и `footnotesize` пропущены — чистая дыра в списке."""
        result = convert_text_environments(r'\small текст \footnotesize мельче')
        self.assertNotIn(r'\small', result)
        self.assertNotIn(r'\footnotesize', result)
        self.assertIn('текст', result)
        self.assertIn('мельче', result)

    def test_vertical_skips_dropped(self):
        r"""`\smallskip`/`\medskip`/`\bigskip` — вертикальные отбивки."""
        result = convert_text_environments(
            '\\smallskip\nабзац\n\\medskip\nвторой\n\\bigskip')
        for cmd in (r'\smallskip', r'\medskip', r'\bigskip'):
            self.assertNotIn(cmd, result)
        self.assertIn('абзац', result)
        self.assertIn('второй', result)

    def test_53909_heading_with_math_in_argument(self):
        r"""`\subsubsection*{... $t \to \infty$ ...}` (живой #53909).

        Аргумент с формулой внутри лексер режет на три токена, и прежний
        `_KEEP_ARG_RE` не видел команду целиком — она доезжала до экрана."""
        text = r'\subsubsection*{2. Предельный переход при $t \to \infty$}'
        result = convert_text_environments(text)
        self.assertNotIn(r'\subsubsection', result)
        self.assertIn('Предельный переход', result)
        self.assertIn(r'$t \to \infty$', result)

    def test_54399_footnote_with_nested_command(self):
        r"""`\footnote{... \textit{...} ...}` (живой #54399).

        Вложенная группа: `[^{}]*` в прежнем шаблоне такую не берёт."""
        text = (r'экономистов.\footnote{Fuller, Dan. «Consensus» '
                r'\textit{The Journal of Economic Education} 45.2 (2014).} Среди')
        result = convert_text_environments(text)
        self.assertNotIn(r'\footnote', result)
        self.assertNotIn(r'\textit', result)
        self.assertIn('The Journal of Economic Education', result)
        self.assertIn('Среди', result)

    def test_53748_float_placement_option_dropped(self):
        r"""`\begin{figure}[htpb]` оставлял на экране строку `[htpb]`.

        Шлюз этого НЕ ловит: в `[htpb]` нет обратного слеша. Найдено
        свипом — 319 задач трёх источников."""
        text = '\\begin{figure}[htpb]\n\\centering\nподпись\n\\end{figure}'
        result = convert_text_environments(text)
        self.assertNotIn('[htpb]', result)
        self.assertIn('подпись', result)

    def test_currency_symbols(self):
        r"""`\pounds`/`\euro` — обычные символы валют (2 задачи)."""
        result = convert_text_environments(r'цена \pounds 100 и \euro 50')
        self.assertNotIn(r'\pounds', result)
        self.assertNotIn(r'\euro', result)
        self.assertIn('£', result)
        self.assertIn('€', result)

    def test_unbalanced_brace_left_alone(self):
        r"""Незакрытая скобка — сломанный материал, а не повод съесть хвост.

        Счётчик скобок обязан сдаться и оставить текст как есть: шлюз
        честно забракует такую задачу, а молчаливая потеря текста — P0."""
        text = r'начало \textbf{без закрытия и дальше важный текст'
        result = convert_text_environments(text)
        self.assertIn('важный текст', result)

    def test_63316_forced_line_break_becomes_newline(self):
        r"""`\\` вне математики — принудительный перенос строки LaTeX.

        До правки доезжал до экрана обратным слешем: «покупателей.\
        Группа A» (живой #63316). Имени команды в `\\` нет, поэтому
        `R-CMD` шлюза его не ловил, а KaTeX молчал — математики тут нет.
        Найдено свипом по корпусу: 174 задачи из PASS, 834 случая.

        В `render_markdown` стоит `breaks: True`, поэтому одиночный
        перевод строки даёт ровно `<br>` — семантика LaTeX сохраняется.
        """
        text = 'группы покупателей.' + '\\\\' + ' **Группа A** Спрос'
        result = convert_text_environments(text)
        self.assertNotIn('\\', result)
        self.assertIn('покупателей.\n**Группа A**', result)

    def test_63299_line_break_before_newline_not_doubled(self):
        r"""`\\` перед переводом строки не должен рождать пустую строку.

        `\\` + `\n` в LaTeX — один перенос. Если оставить оба, markdown
        увидит пустую строку и разорвёт абзац (живой #63299)."""
        text = 'торговую точку.' + '\\\\' + '\n* Равновесием называется'
        result = convert_text_environments(text)
        self.assertNotIn('\\', result)
        self.assertIn('торговую точку.\n* Равновесием', result)

    def test_59624_line_breaks_split_separate_functions(self):
        r"""Три функции спроса, склеенные в одну строку (живой #59624)."""
        text = 'Q(s) = -2 + P ' + '\\\\' + ' Q(d) = 12 — 2P ' + '\\\\' + ' Q(d) = 3'
        result = convert_text_environments(text)
        self.assertNotIn('\\', result)
        self.assertEqual(result.count('\n'), 2)

    def test_line_break_with_spacing_argument(self):
        r"""`\\[2mm]` — тот же перенос с отбивкой; отбивку не рисуем."""
        result = convert_text_environments('первая' + '\\\\[2mm]' + 'вторая')
        self.assertNotIn('\\', result)
        self.assertNotIn('[2mm]', result)
        self.assertIn('первая\nвторая', result)

    def test_line_break_inside_math_untouched(self):
        r"""ВНУТРИ математики `\\` — разделитель строк `cases`/матрицы.

        Тронуть его — сломать формулу, которая сейчас рендерится."""
        text = r'$$\begin{cases} x = 1 \\ y = 2 \end{cases}$$'
        result = convert_text_environments(text)
        self.assertIn(r'x = 1 \\ y = 2', result)

    def test_line_break_inside_tabular_untouched(self):
        r"""ВНУТРИ `tabular` `\\` — конец строки таблицы, не текста."""
        text = ('\\begin{tabular}{ll}\nа & б \\\\ в & г\n'
                '\\end{tabular}')
        result = convert_text_environments(text)
        self.assertIn('а & б \\\\ в & г', result)
