"""Значки «Стола» (README §9): только SVG из общего набора, один рисунок на имя.

Набора два — `templates/_icon.html` (разметка) и `templates/_icons.html`
(скрипты). Экраны «Стола» зовут значки по имени; имя, которого нет в наборе,
молча рисует пустоту, а два разных рисунка под одним именем — разные значки
на двух страницах. Появился 19.09.2026 (S7 «Стола»).
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)
_RX_MARKUP = re.compile(r"\{% if name == '([a-z_]+)' %\}(<svg.*?</svg>)\{% endif %\}", re.S)
_RX_SCRIPT = re.compile(r"^\s*([a-z_]+): '(<svg.*?</svg>)',?$", re.M)
_RX_USE = re.compile(r"_icon\.html' with name='([a-z_]+)'")


def _sets():
    markup = dict(_RX_MARKUP.findall((BASE / 'templates/_icon.html').read_text(encoding='utf-8')))
    script = dict(_RX_SCRIPT.findall((BASE / 'templates/_icons.html').read_text(encoding='utf-8')))
    return markup, script


class StolIconsTests(SimpleTestCase):

    def test_every_icon_used_by_stol_exists(self):
        markup, _script = _sets()
        files = [BASE / 'catalog/templates/catalog/stol.html', BASE / 'catalog/templates/catalog/_problem_test.html']
        files += sorted((BASE / 'catalog/templates/catalog/stol').glob('*.html'))
        missing = {}
        for path in files:
            names = set(_RX_USE.findall(path.read_text(encoding='utf-8')))
            lost = sorted(names - set(markup))
            if lost:
                missing[path.name] = lost
        self.assertEqual(missing, {})

    def test_icons_added_for_stol_are_identical_in_both_sets(self):
        markup, script = _sets()
        for name in ('network', 'sparkle', 'grid', 'minus', 'refresh', 'menu'):
            with self.subTest(icon=name):
                self.assertIn(name, markup)
                self.assertIn(name, script)
                self.assertEqual(markup[name], script[name])
