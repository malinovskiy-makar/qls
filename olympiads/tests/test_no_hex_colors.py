"""Ни одного шестнадцатеричного цвета в стилях раздела.

Исключений нет. Свой цвет в разделе означает, что он не поедет вместе с
палитрой при следующей её правке и однажды окажется единственным пятном
старого набора на экране.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STYLES = (Path(settings.BASE_DIR) / 'olympiads' / 'templates' /
          'olympiads' / '_styles.html')

# #abc, #abcd, #aabbcc, #aabbccdd — все четыре записи цвета.
HEX_COLOR = re.compile(
    r'#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b')


class NoHexColorsTests(SimpleTestCase):

    def test_styles_partial_has_no_hex_colors(self):
        text = STYLES.read_text(encoding='utf-8')
        found = HEX_COLOR.findall(text)
        self.assertEqual(
            found, [],
            'В {} найдены свои цвета: {}. Только токены из '
            '_tokens.html.'.format(STYLES.name, found))

    def test_the_check_itself_catches_a_colour(self):
        """Сторож самого сторожа: регулярка обязана ловить все четыре записи."""
        for sample in ('#fff', '#ffff', '#ffffff', '#ffffffff'):
            self.assertTrue(HEX_COLOR.search('color: %s;' % sample), sample)
        # А это не цвет: якорь и идентификатор в разметке трогать нельзя.
        self.assertFalse(HEX_COLOR.search('href="#top"'))
