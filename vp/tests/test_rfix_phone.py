"""Сессия R-fix, фаза 1: на 390 px страницы раздела не уезжают вбок.

Браузерный тест (`test_browser.py`) идёт только на PostgreSQL с Playwright, поэтому здесь
сторожим сами правила стилей, которые держат ширину: замер глазами — в журнале R-fix
(`scrollWidth == clientWidth` на 390 px). Правило ищется по точному селектору — в общем
блоке или в блоке телефона `@media (max-width: 760px)`.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

STYLES = Path(__file__).resolve().parents[1] / 'templates' / 'vp' / '_styles.html'
PHONE = '@media (max-width: 760px) {'


def _phone_block(css):
    start = css.index(PHONE) + len(PHONE)
    depth, i = 1, start
    while depth:
        depth += {'{': 1, '}': -1}.get(css[i], 0)
        i += 1
    return css[start:i - 1]


def _rule(css, selector):
    """Объявления правила с ТОЧНО таким селектором: {'свойство': 'значение'}."""
    found = re.search(r'(?m)^\s*' + re.escape(selector) + r' \{([^}]*)\}', css)
    if not found:
        return {}
    pairs = (d.split(':', 1) for d in found.group(1).split(';') if ':' in d)
    return {k.strip(): v.strip() for k, v in pairs}


class PhoneWidthStyleTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = STYLES.read_text(encoding='utf-8')
        cls.phone = _phone_block(cls.css)

    def test_row_heading_clips_its_formula(self):
        # Без position: relative служебный слой KaTeX уходил из-под обрезки (649 px).
        zq = _rule(self.css, '.vp-zq')
        self.assertEqual(zq.get('overflow'), 'hidden')
        self.assertEqual(zq.get('position'), 'relative')
        self.assertEqual(zq.get('min-width'), '0')

    def test_long_formulas_and_tables_scroll_inside(self):
        self.assertEqual(_rule(self.css, '.vp-zbody .katex-display').get('overflow-x'), 'auto')
        self.assertEqual(_rule(self.css, '.vp-scroll').get('overflow-x'), 'auto')
        filters = _rule(self.phone, '.vp-zfilters')
        self.assertEqual(filters.get('flex-wrap'), 'nowrap')
        self.assertEqual(filters.get('overflow-x'), 'auto')

    def test_format_loss_plaque_stacks_on_phone(self):
        self.assertEqual(_rule(self.phone, '.vp-res-loss').get('flex-wrap'), 'wrap')
        self.assertEqual(_rule(self.phone, '.vp-res-loss-main').get('flex'), '1 1 calc(100% - 42px)')
        self.assertEqual(_rule(self.phone, '.vp-res-loss > .vp-btn').get('flex'), '1 1 100%')

    def test_intro_how_column_goes_under_block_name(self):
        self.assertEqual(_rule(self.phone, '.vp-intro-table tr').get('display'), 'grid')
        self.assertEqual(_rule(self.phone, '.vp-intro-table th:last-child').get('display'), 'none')
        how = _rule(self.phone, '.vp-intro-table td.vp-intro-how')
        self.assertEqual(how.get('grid-column'), '2 / -1')
        self.assertEqual(how.get('white-space'), 'normal')
