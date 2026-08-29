# -*- coding: utf-8 -*-
"""Фазы 6-7 сессии 2026-08-27: новый шлюз `render_preflight_v2`.

Проверки, не требующие браузера (SOL-LEAK, EMPTY, ENV-BAL, порядок
блоков), гоняются со стубом-рендерером — быстро и в общем прогоне.
Настоящий KaTeX по живым фикстурам аудита прогоняется отдельной
командой `corpus_gate_fixtures` (браузер в юнит-тестах поднимать нельзя:
он требует playwright и DJANGO_ALLOW_ASYNC_UNSAFE).
"""
import re

from django.test import SimpleTestCase

from problems.corpus_converter.preflight_gate import (
    build_blocks, convert_problem_v2, polish_field, render_preflight_v2,
)
from problems.corpus_converter.sol_leak import detect_solution_leak

_TAG_RE = re.compile(r'<[^>]+>')


class StubChecker:
    """Заменяет браузер: KaTeX-ошибок не выдумывает, но видимый текст
    считает честно — этого хватает для проверок R-ENV/R-CMD/PLOT."""

    def check(self, html):
        return {
            'fragmentCount': 0,
            'errors': [],
            'strictHits': [],
            'visibleText': _TAG_RE.sub(' ', html or ''),
        }

    def check_many(self, htmls):
        return [self.check(h) for h in htmls]


class SolutionLeakTests(SimpleTestCase):
    """#30145/#30153/#30155/#30160 — 47 задач Archive 3 по замеру."""

    def test_numbered_marker_detected(self):
        leaked, why = detect_solution_leak('[9] Решение:\n\nЕсли есть выбор')
        self.assertTrue(leaked)
        self.assertIn('условия', why)

    def test_bare_marker_detected(self):
        self.assertTrue(detect_solution_leak('Решение: далее текст')[0])

    def test_normal_statement_not_flagged(self):
        self.assertFalse(detect_solution_leak('Фирма производит товар.')[0])

    def test_word_reshenie_inside_text_not_flagged(self):
        # «Решение» в середине условия — обычное слово, не маркер.
        self.assertFalse(
            detect_solution_leak('Обоснуйте решение фирмы о выходе.')[0])

    def test_gate_blocks_on_leak(self):
        blocks = [('Условие', '[7] Решение: текст', 'текст')]
        verdict = render_preflight_v2(blocks, StubChecker(),
                                      raw_statement='[7] Решение: текст')
        self.assertFalse(verdict.ok)
        self.assertIn('SOL-LEAK', verdict.codes)


class StructureGateTests(SimpleTestCase):
    def test_41924_lost_part_blocks(self):
        blocks = [('Условие', 'Государство вводит налог', 'Государство вводит налог'),
                  ('Часть г', '3.', '3.')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertFalse(verdict.ok)
        self.assertIn('EMPTY', verdict.codes)

    def test_3989_empty_upstream_blocks_as_needs_content(self):
        blocks = [('Условие', '', ''), ('Часть а', '', ''), ('Часть б', '', '')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertFalse(verdict.ok)
        self.assertIn('EMPTY-SRC', verdict.codes)

    def test_unbalanced_environment_blocks(self):
        # #30113: \begin{equation*} без закрывающего.
        blocks = [('Условие', 'src', r'$$\begin{equation*} x = y$$')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertFalse(verdict.ok)
        self.assertIn('ENV-BAL', verdict.codes)

    def test_clean_problem_passes(self):
        blocks = [('Условие', 'Фирма производит товар', 'Фирма производит товар')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertTrue(verdict.ok, verdict.details)
        self.assertEqual(verdict.codes, [])


class RawTexGateTests(SimpleTestCase):
    def test_raw_plot_command_blocks(self):
        blocks = [('Условие', 'src', r'график \addplot coordinates {(1,2)}')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertFalse(verdict.ok)
        self.assertIn('PLOT', verdict.codes)

    def test_raw_environment_in_visible_text_blocks(self):
        blocks = [('Условие', 'src', r'текст \begin{unknownenv} тело \end{unknownenv}')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertFalse(verdict.ok)
        self.assertIn('R-ENV', verdict.codes)

    def test_leftover_tex_command_blocks(self):
        # Живые #4073/#35255: непарный `$$` съедался сканером как пустая
        # пара, поэтому в видимый текст не попадал, а соседний \sqrt{2}
        # в список маркеров не входил — карточка проходила, хотя ученик
        # видел сырой TeX. Найдено проверкой готовой страницы v2.
        blocks = [('Решение', 'src', r'упражнение: x = 5 - 5 / \sqrt{2}$$ Однако')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertFalse(verdict.ok)
        self.assertIn('R-CMD', verdict.codes)

    def test_escaped_symbols_are_not_leftover_commands(self):
        # `\$`, `\%`, `\&` — экранированные символы, а не команды:
        # боевой fixCurrencyDollars показывает их обычными знаками.
        blocks = [('Условие', 'src', r'цена \$100 и \% ставка и \& знак')]
        verdict = render_preflight_v2(blocks, StubChecker())
        self.assertTrue(verdict.ok, verdict.details)


class PipelineTests(SimpleTestCase):
    """Конвейер v2 не ломает контракт стадии 1 и идемпотентен."""

    def test_polish_is_idempotent(self):
        for text in [r'$$\begin{cases}a & если x\end{cases}$$',
                     r'\begin{quote}цитата\end{quote}',
                     'стоимость 3000$ за тонну и ещё 1300$',
                     r'q < \Tilde{p}']:
            once = polish_field(text)
            self.assertEqual(polish_field(once), once, f'не идемпотентно: {text!r}')

    def test_v2_applies_all_phases(self):
        result = convert_problem_v2(
            statement=r'\begin{quote}цена 3000$ за тонну\end{quote}',
            answer='', solution=r'q < \Tilde{p}', existing_parts=[])
        self.assertNotIn(r'\begin{quote}', result['statement_md'])
        self.assertIn(r'3000\$', result['statement_md'])
        self.assertIn(r'\tilde', result['solution_md'])

    def test_build_blocks_matches_render_order(self):
        result = convert_problem_v2(statement='условие', answer='ответ',
                                    solution='решение',
                                    existing_parts=[('а', 'первый')])
        blocks = build_blocks('условие', [('а', 'первый')], 'ответ', 'решение', result)
        self.assertEqual([b[0] for b in blocks],
                         ['Условие', 'Часть а', 'Ответ', 'Решение'])

    def test_v2_preserves_stage1_cases_repair(self):
        # Живая регрессия #41612 обязана пережить все новые фазы.
        text = ('\\[ U^\\theta(q,p) = \n\\begin{cases}\n'
                '\\theta\\sqrt{q} - p, & если покупатель приобретает товар \n\n'
                '0, & если отказывается от покупки\n\\end{cases} \\]')
        result = convert_problem_v2(statement=text, existing_parts=[])
        self.assertIn(r'\\', result['statement_md'])
        self.assertIn(r'\begin{cases}', result['statement_md'])
        self.assertIn(r'\text{', result['statement_md'])
