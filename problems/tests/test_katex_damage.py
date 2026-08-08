# -*- coding: utf-8 -*-
"""Мера «сломанного рендера KaTeX» — проверка ИСПОЛНЕНИЕМ в браузере.

Зачем именно так. До 2026-08-08 весь шлюз «не навреди» считал узлы
`.katex-error` и был слеп к самому неприятному режиму: неизвестная команда
внутри разобравшейся формулы (`\\tesxt` — опечатка автора, `\\myarray` —
самодельный макрос) печатается цветом ошибки, НО узла `.katex-error` не
создаёт, а соседние куски формулы молча слипаются. Питон-тесты этого не видят
вовсе, текстовые эвристики — тоже: «сломанная формула» это то, что решил
KaTeX. Поэтому здесь поднимается настоящий chromium с вендорным KaTeX 0.16.9.

Тест фиксирует ДВА обязательства меры:
  1. неизвестный макрос ловится (краснота ≥ 1) при нулевом `.katex-error`;
  2. авторский красный (`\\color{#cc0000}`, `\\textcolor{red}`) НЕ считается
     поломкой — иначе шлюз начал бы врать в другую сторону.

Второе — не теоретическая придирка: цвет ошибки KaTeX по умолчанию ровно
`#cc0000`, и наивный детектор «красноты» на авторской раскраске сработал бы.
Мера обходит это подменой `errorColor` на служебный #010203 в песочнице.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import SimpleTestCase

DAMAGE_JS = os.path.join(settings.BASE_DIR, 'scripts', 'katex_damage.js')
NODE_MODULES = os.path.join(settings.BASE_DIR, 'node_modules')

RUNNER = r"""
'use strict';
const { chromium } = require('playwright');
const { buildSandbox } = require(process.env.DAMAGE_JS);

const CASES = JSON.parse(process.env.CASES);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(buildSandbox(), { waitUntil: 'load' });
  const out = {};
  for (const [name, tex] of Object.entries(CASES)) {
    out[name] = await page.evaluate((t) => window.measure(t), tex);
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})();
"""

CASES = {
    # неизвестная команда внутри разобравшейся формулы
    'typo_macro': r'$500\sqrt{P} \tesxt{P}$',
    'custom_macro': r'$\myarray{31}{8p}$',
    'graphics_macro': r'$\includegraphics{a.png}$',
    'two_macros': r'$\myarray{1}$ и ещё $\foo{2}$',
    # третий тихий режим: пары разделителей нет, формула не рендерится вовсе
    'unpaired_dollar': r'$\frac{1}{2$',
    # формула не разобралась целиком
    'double_subscript': r'$Q_D_t(P_t)=110-2P_t$',
    'unknown_env': r'$\begin{foo}a&b\end{foo}$',
    'tikz': r'$\begin{tikzpicture}\draw(0,0);\end{tikzpicture}$',
    # здоровое
    'plain': r'$y = 57 - 2\sqrt{x} + 0{,}5x$',
    'cases_env': r'$Y=\begin{cases}500\sqrt{P}&P\le100\\5000&P>100\end{cases}$',
    'no_math': 'Обычный текст без формул совсем.',
    # авторский красный — НЕ поломка
    'author_cc0000': r'$\color{#cc0000} x+1$',
    'author_red': r'$\textcolor{red}{x+1}$',
    'author_blue': r'$\textcolor{blue}{x+1}$',
}


def _playwright_ready():
    if shutil.which('node') is None:
        return False
    return os.path.isdir(os.path.join(NODE_MODULES, 'playwright'))


@unittest.skipUnless(_playwright_ready(), 'нужны node и playwright в node_modules')
class KatexDamageMeasureTests(SimpleTestCase):
    """Мера поломок рендера, снятая настоящим браузером."""

    measured = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = dict(os.environ)
        env['NODE_PATH'] = NODE_MODULES
        env['DAMAGE_JS'] = DAMAGE_JS
        env['CASES'] = json.dumps(CASES)
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as f:
            f.write(RUNNER)
            path = f.name
        try:
            proc = subprocess.run(['node', path], capture_output=True, text=True,
                                  cwd=settings.BASE_DIR, env=env, timeout=180)
        finally:
            os.unlink(path)
        if proc.returncode != 0:
            raise AssertionError('node упал:\n{}\n{}'.format(proc.stdout, proc.stderr))
        cls.measured = json.loads(proc.stdout)

    # ── режим 2: неизвестная команда, .katex-error НЕ создаётся ──────────

    def test_unknown_macro_is_red_while_katex_error_stays_zero(self):
        """Главное обязательство: опечатка в команде видна мере, хотя
        `.katex-error` молчит. Ровно этот случай шлюз пропускал."""
        for key in ('typo_macro', 'custom_macro', 'graphics_macro'):
            with self.subTest(case=key):
                r = self.measured[key]
                self.assertEqual(r['errors'], 0,
                                 'ожидали ноль .katex-error, иначе тест сторожит не тот режим')
                self.assertGreaterEqual(r['red'], 1, 'краснота обязана поймать неизвестную команду')

    def test_one_broken_macro_counts_once(self):
        """Одна поломка — одна единица. KaTeX выводит каждую формулу дважды
        (видимой вёрсткой и скрытым MathML) и красит внутри вложенную пару
        span'ов; наивный подсчёт давал бы по четыре на одну команду."""
        self.assertEqual(self.measured['typo_macro']['red'], 1)

    def test_two_broken_macros_count_twice(self):
        """Мера обязана расти с числом поломок, иначе сравнение ДО/ПОСЛЕ
        не увидит, что стало хуже на одну команду."""
        self.assertEqual(self.measured['two_macros']['red'], 2)

    # ── режим 3: рендеру нечего показать ─────────────────────────────────

    def test_unpaired_dollar_is_invisible_to_render(self):
        """Непарный `$` — третий тихий режим, и рендер тут бессилен: пары
        разделителей нет, формула не рендерится ВООБЩЕ, на экране остаётся
        сырой текст. Ловится текстовым `unpaired_dollar` из
        problems/diagnostics.py, а не этой мерой. Тест закрепляет границу
        ответственности, чтобы её не искали здесь."""
        r = self.measured['unpaired_dollar']
        self.assertEqual((r['errors'], r['red']), (0, 0))

    # ── режим 1: формула не разобралась ──────────────────────────────────

    def test_unparsable_formula_counted_as_error_not_as_red(self):
        for key in ('double_subscript', 'unknown_env', 'tikz'):
            with self.subTest(case=key):
                r = self.measured[key]
                self.assertEqual(r['errors'], 1)
                self.assertEqual(r['red'], 0, 'узел .katex-error не должен считаться дважды')

    # ── тишина на здоровом ───────────────────────────────────────────────

    def test_healthy_math_is_silent(self):
        for key in ('plain', 'cases_env', 'no_math'):
            with self.subTest(case=key):
                r = self.measured[key]
                self.assertEqual((r['errors'], r['red']), (0, 0))

    # ── авторский цвет — не поломка ──────────────────────────────────────

    def test_author_colour_is_not_damage(self):
        """`\\color{#cc0000}` даёт ровно тот оттенок, которым KaTeX по умолчанию
        красит ошибки. Мера обязана их различать — иначе каждая раскрашенная
        автором формула поехала бы в отчёт как сломанная."""
        for key in ('author_cc0000', 'author_red', 'author_blue'):
            with self.subTest(case=key):
                r = self.measured[key]
                self.assertEqual((r['errors'], r['red']), (0, 0))
