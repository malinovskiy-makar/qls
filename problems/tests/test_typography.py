# -*- coding: utf-8 -*-
u"""Типографика: длинного тире в тексте сайта нет.

Правило владельца: в текстах, которые видит пользователь, длинное тире «—»
не используем. Максимум короткое «–» (U+2013), и только там, где оно
действительно нужно.

⚠️ РАНЬШЕ ЭТОТ ТЕСТ СТОРОЖИЛ ДОЛГ, ТЕПЕРЬ НОЛЬ. В нём был список
`DEBT` с замеренными числами по каталогам и правило «только уменьшаться»:
так область доводилась до конца по частям, чтобы не заводить красный тест,
к которому все привыкнут. 2026-09-02 долг закрыт целиком (271 знак в 70
файлах), и правило стало простым: НОЛЬ ПО ВСЕМУ САЙТУ.

Комментарии не в счёт: их пользователь не видит. Что именно вырезается —
в `scripts/check_em_dash.py`.
"""
import json
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

SCANNER = os.path.join('scripts', 'check_em_dash.py')


def scan(paths=()):
    res = subprocess.run(
        [sys.executable, SCANNER, '--json'] + list(paths),
        cwd=str(settings.BASE_DIR), capture_output=True, text=True,
        encoding='utf-8', errors='replace')
    assert res.returncode in (0, 1), res.stderr
    return json.loads(res.stdout)


class EmDashTests(SimpleTestCase):

    def test_the_whole_site_stays_at_zero(self):
        u"""Ноль во всех каталогах, чей текст видит пользователь."""
        data = scan()
        self.assertEqual(
            data['total'], 0,
            u'В тексте сайта снова появилось длинное тире:\n'
            + '\n'.join('  %s: %d' % (f['file'], f['count'])
                        for f in data['files']))

    def test_scanner_ignores_comments(self):
        u"""Комментарий пользователь не видит — считать его нечестно."""
        sys.path.insert(0, os.path.join(str(settings.BASE_DIR), 'scripts'))
        from check_em_dash import strip_comments
        self.assertNotIn('—', strip_comments('{# тире — тут #}x', '.html'))
        self.assertNotIn('—', strip_comments('<!-- тире — тут -->x', '.html'))
        self.assertNotIn('—', strip_comments('/* тире — тут */x', '.css'))
        self.assertNotIn('—', strip_comments('x\n// тире — тут', '.js'))
        self.assertNotIn('—', strip_comments('x\n# тире — тут', '.py'))
        # А ВОТ ЭТО — видимый текст, и он обязан считаться.
        self.assertIn('—', strip_comments('<p>тире — тут</p>', '.html'))

    def test_scanner_does_not_eat_urls(self):
        u"""`https://` — не комментарий; срежь его, и тире внутри строки
        перестало бы считаться."""
        sys.path.insert(0, os.path.join(str(settings.BASE_DIR), 'scripts'))
        from check_em_dash import strip_comments
        src = "var u = 'https://example.com'; // тире — тут\nvar t = 'а — б';"
        out = strip_comments(src, '.js')
        self.assertIn('example.com', out)
        self.assertIn('а — б', out)
        self.assertNotIn('тире — тут', out)

    def test_comment_keeps_the_line_numbering(self):
        u"""Вырезанный комментарий не должен сдвигать номера строк.

        Раньше многострочный комментарий вырезался целиком, и всё, что
        стояло ПОСЛЕ него, сканер показывал на чужих строках. Счётчик от
        этого не страдал, поэтому баг жил незамеченным — и по выводу
        сканера правились не те места.
        """
        sys.path.insert(0, os.path.join(str(settings.BASE_DIR), 'scripts'))
        from check_em_dash import strip_comments
        src = '<p>раз</p>\n{% comment %}\nдва\nтри\n{% endcomment %}\n<p>а — б</p>'
        out = strip_comments(src, '.html')
        self.assertEqual(len(out.split('\n')), len(src.split('\n')))
        lines = [i + 1 for i, ln in enumerate(out.split('\n')) if '—' in ln]
        self.assertEqual(lines, [6])
