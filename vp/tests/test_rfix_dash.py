"""Сессия R-fix, фаза 3: в разделе нет длинного тире «—» вне комментариев.

`scripts/check_em_dash.py` находил «—» в `drill.js`: это был знак длинного минуса в наборе
регулярки «±». Знаки теперь записаны кодами (`\\u2014` и соседи) — сканеру чисто, а регулярка
по-прежнему узнаёт все шесть знаков, которые сервер считает длинным минусом
(`vp.scoring._LONG_MINUS`).
"""
import importlib.util
import os
import re
from pathlib import Path

from django.test import SimpleTestCase

from vp import scoring

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / 'vp' / 'static' / 'vp' / 'js'


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

    def test_plus_minus_regex_knows_every_long_minus(self):
        for name in ('drill.js', 'take.js'):
            source = (JS / name).read_text(encoding='utf-8')
            sets = re.findall(r'/\^\[-((?:\\u[0-9a-fA-F]{4})+)\]/', source)
            self.assertEqual(len(sets), 1, name)
            codes = {chr(int(c, 16)) for c in re.findall(r'\\u([0-9a-fA-F]{4})', sets[0])}
            self.assertEqual(codes, set(scoring._LONG_MINUS), name)
