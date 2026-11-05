"""ВП: длинное тире не попадает в интерфейс, скопированный длинный минус — ошибка формата."""
import importlib.util
import os
from pathlib import Path

from django.test import SimpleTestCase

from vp import drill, scoring

ROOT = Path(__file__).resolve().parents[2]


def _checker():
    spec = importlib.util.spec_from_file_location('check_em_dash', ROOT / 'scripts' / 'check_em_dash.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EmDashTests(SimpleTestCase):
    def test_vp_has_no_em_dash_outside_comments(self):
        here = os.getcwd()
        os.chdir(ROOT)                                   # сканер пишет пути от текущей папки
        try:
            found = _checker().scan(['vp'])
        finally:
            os.chdir(here)
        self.assertEqual(found, [])

    def test_copied_long_minus_remains_a_format_error(self):
        # «±» удалена: клавиатура вводит ASCII-минус, а вставленный длинный
        # минус не должен незаметно превращаться в правильную запись.
        self.assertTrue(drill.check(12, '-4,5')['ok'])
        for minus in scoring._LONG_MINUS:
            with self.subTest(minus=minus):
                verdict = drill.check(12, minus + '4,5')
                self.assertFalse(verdict['ok'])
                self.assertEqual(verdict['reason'], 'minus')
