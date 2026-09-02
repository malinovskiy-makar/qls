# -*- coding: utf-8 -*-
u"""Типографика: длинного тире в тексте сайта нет.

Правило владельца: в текстах, которые видит пользователь, длинное тире «—»
не используем. Максимум короткое «–» (U+2013), и только там, где оно
действительно нужно.

⚠️ ЭТОТ ТЕСТ СТОРОЖИТ УЖЕ ВЫЧИЩЕННУЮ ОБЛАСТЬ, А НЕ ВЕСЬ САЙТ. Область
перечислена в `CLEAN` и держится на нуле. Остальное — записанный долг:
числа в `DEBT` не выдумка, а замер, и они обязаны только УМЕНЬШАТЬСЯ.
Поставить сюда «весь сайт» и оставить тест красным значило бы завести
красный тест, к которому все привыкнут, — а он должен быть либо зелёным,
либо поводом остановиться.

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

# Область, доведённая до нуля. Сюда можно только добавлять.
CLEAN = [
    'game',
    'templates',
    os.path.join('problems', 'templates', 'platform', 'stats.html'),
]

# ⚠️ ЗАМЕР, А НЕ ОЦЕНКА (2026-09-02, сессия «Wecon Rush», фаза 9).
# Верхняя граница долга по каталогам. Число обязано только уменьшаться:
# выросло — значит кто-то принёс новое длинное тире в текст сайта.
DEBT = {
    'teacher': 141,
    'student': 33,
    'problems': 35,
    'catalog': 27,
    'calc2': 21,
    'calendar_stub': 14,
}


def scan(paths):
    res = subprocess.run(
        [sys.executable, SCANNER, '--json'] + list(paths),
        cwd=str(settings.BASE_DIR), capture_output=True, text=True,
        encoding='utf-8', errors='replace')
    assert res.returncode in (0, 1), res.stderr
    return json.loads(res.stdout)


class EmDashTests(SimpleTestCase):

    def test_clean_area_stays_at_zero(self):
        data = scan(CLEAN)
        self.assertEqual(
            data['total'], 0,
            'В вычищенной области снова появилось длинное тире:\n'
            + '\n'.join('  %s: %d' % (f['file'], f['count'])
                        for f in data['files']))

    def test_debt_only_shrinks(self):
        u"""Долг по остальным каталогам не растёт.

        Тест не требует нуля — он требует, чтобы стало не хуже. Так область
        доводится до конца по частям, а не одним неподъёмным заходом.
        """
        grew = []
        for app, was in sorted(DEBT.items()):
            now = scan([app])['total']
            if now > was:
                grew.append('%s: было %d, стало %d' % (app, was, now))
        self.assertEqual(grew, [],
                         'Длинное тире вернулось в текст сайта:\n  '
                         + '\n  '.join(grew))

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
