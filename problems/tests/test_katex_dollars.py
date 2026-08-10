"""
Литеральный доллар внутри формулы — проверка ИСПОЛНЕНИЕМ.

Что было. Маскировщик `maskEscapedDollars` заменял ВСЕ «\\$» приватным
символом \\uE000, в том числе внутри «$$…$$». KaTeX такой символ не
принимает вовсе и при `throwOnError: false` печатает ВСЮ формулу красным
исходником — так экран проверки показывал таблицу КПВ сырым кодом
(задача #360 демо-базы: «\\text{Ср-ва произв., млрд \\$}»).

Питон-тесты этого не видят: страница отдаёт 200, дефект живёт в браузере.
Поэтому функции из общего партиала `_katex_dollars.html` вырезаются из
шаблона и исполняются в node на контрольных строках.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import TestCase

PARTIAL = os.path.join(settings.BASE_DIR, 'templates', '_katex_dollars.html')

# Шаблоны, которые обязаны брать конвейер долларов из общей точки правды.
USERS_OF_PARTIAL = [
    os.path.join('catalog', 'templates', 'catalog', 'base.html'),
    os.path.join('student', 'templates', 'student', 'base.html'),
    os.path.join('teacher', 'templates', 'teacher', 'base.html'),
    os.path.join('problems', 'templates', 'platform', 'base.html'),
    os.path.join('teacher', 'templates', 'teacher', 'assignment_print.html'),
]

SENTINEL = ''


def partial_script():
    """Вернуть JS из партиала (между тегами <script>)."""
    with open(PARTIAL, encoding='utf-8') as fh:
        text = fh.read()
    match = re.search(r'<script>(.*)</script>', text, re.S)
    assert match, 'в партиале нет тега <script>'
    return match.group(1)


class MaskOutsideMathTests(unittest.TestCase):
    """Маскируем только те доллары, что стоят ВНЕ формул."""

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which('node')

    def run_cases(self, cases):
        """cases — список строк; вернуть список результатов maskOutsideMath."""
        if not self.node:
            self.skipTest('node не установлен')
        script = (partial_script() + '\n'
                  + 'var cases = ' + repr(cases).replace("'", '"') + ';\n'
                  + 'console.log(JSON.stringify(cases.map(maskOutsideMath)));\n')
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(script)
            path = fh.name
        try:
            out = subprocess.run([self.node, path], capture_output=True,
                                 text=True, timeout=30)
            self.assertEqual(out.returncode, 0, out.stderr)
            import json
            return json.loads(out.stdout)
        finally:
            os.unlink(path)

    def test_dollar_inside_display_math_survives(self):
        """Внутри «$$…$$» «\\$» остаётся собой — его рисует сам KaTeX."""
        src = r'$$\text{млрд \$} + 1$$'
        got, = self.run_cases([src])
        self.assertEqual(got, src)
        self.assertNotIn(SENTINEL, got)

    def test_dollar_inside_inline_math_survives(self):
        src = r'\(\text{\$}\)'
        got, = self.run_cases([src])
        self.assertEqual(got, src)

    def test_dollar_in_prose_is_masked(self):
        """Вне формул маскировка нужна: иначе доллар станет разделителем."""
        got, = self.run_cases([r'цена 5\$ за штуку'])
        self.assertEqual(got, 'цена 5' + SENTINEL + ' за штуку')

    def test_prose_and_math_together(self):
        """Смешанный случай: в прозе замаскировано, в формуле — нет."""
        got, = self.run_cases([r'5\$ и $P=10$ и \$7'])
        self.assertEqual(got, '5' + SENTINEL + ' и $P=10$ и ' + SENTINEL + '7')

    def test_text_without_escapes_is_untouched(self):
        """Быстрый выход: строку без «\\$» не трогаем вовсе."""
        for src in ['обычный текст', '$P=10$', r'$$\frac{a}{b}$$']:
            got, = self.run_cases([src])
            self.assertEqual(got, src)

    def test_unclosed_delimiter_is_not_math(self):
        """Незакрытый доллар формулой не считается — маскируем как прозу.

        Важно: закрывающий разделитель ищется В ОБХОД «\\$». Иначе доллар
        валюты закрыл бы чужую формулу, и в неё уехал бы кусок прозы.
        """
        got, = self.run_cases([r'$P=10 и 5\$'])
        self.assertEqual(got, '$P=10 и 5' + SENTINEL)

    def test_escaped_dollar_does_not_close_inline_math(self):
        src = r'$a\$b$'
        got, = self.run_cases([src])
        self.assertEqual(got, src)


class PartialIsSinglePointTests(TestCase):
    """Конвейер долларов написан ОДИН раз и подключается включением."""

    def test_no_template_defines_its_own_mask(self):
        for rel in USERS_OF_PARTIAL:
            path = os.path.join(settings.BASE_DIR, rel)
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
            self.assertNotIn('function maskEscapedDollars', text,
                             '%s завёл свою копию маскировщика' % rel)
            self.assertIn("_katex_dollars.html", text,
                          '%s не подключает общий партиал' % rel)

    def test_no_raw_private_char_in_sources(self):
        """Невидимый символ в исходнике — ловушка; пишем его эскейпом."""
        for rel in USERS_OF_PARTIAL + ['templates/_katex_dollars.html']:
            path = os.path.join(settings.BASE_DIR, rel)
            with open(path, encoding='utf-8') as fh:
                self.assertNotIn(SENTINEL, fh.read(), rel)
