"""
Гигиена шаблонов: то, что рендер отдаёт на экран, но никто не считает
ошибкой.

⚠️ МНОГОСТРОЧНЫЙ `{# … #}` НЕ КОММЕНТАРИЙ. Лексер Django ищет комментарий
регуляркой `\\{#.*?#\\}` БЕЗ флага DOTALL — точка не совпадает с переносом
строки. Поэтому `{#`, у которого `#}` стоит на следующей строке, комментарием
не становится и печатается на страницу КАК ТЕКСТ. Ни `manage.py check`, ни
рендер, ни один питон-тест этого не заметят: страница отдаёт 200, шаблон
валиден, просто на экране у репетитора висит служебная фраза в фигурных
скобках.

Дефект чинили дважды глазами (в двух разных местах, в двух разных сессиях)
и оба раза он появился снова. Третий раз ловим проверкой.
"""
import os
import re

from django.conf import settings
from django.test import TestCase

# Куда не ходим: чужой код и сгенерированные отчёты.
SKIP_PARTS = ('venv', 'node_modules', os.sep + 'reports' + os.sep,
              os.sep + 'backups' + os.sep, os.sep + 'materials' + os.sep,
              os.sep + 'staticfiles' + os.sep)


def template_files():
    for root, dirs, files in os.walk(settings.BASE_DIR):
        if any(part in root + os.sep for part in SKIP_PARTS):
            dirs[:] = []
            continue
        for name in files:
            if name.endswith('.html'):
                yield os.path.join(root, name)


class DjangoCommentTests(TestCase):

    def test_no_multiline_hash_comments(self):
        """`{# … #}` через перенос строки печатается на экран как текст."""
        offenders = []
        for path in template_files():
            with open(path, encoding='utf-8') as handle:
                source = handle.read()
            for match in re.finditer(r'\{#', source):
                end = source.find('#}', match.end())
                fragment = (source[match.start():end] if end != -1
                            else source[match.start():match.start() + 60])
                if end == -1 or '\n' in fragment:
                    line = source[:match.start()].count('\n') + 1
                    offenders.append('%s:%d — %s'
                                     % (os.path.relpath(path,
                                                        settings.BASE_DIR),
                                        line,
                                        fragment[:70].replace('\n', ' ⏎ ')))
        self.assertEqual(
            offenders, [],
            'Многострочный {# #} печатается на страницу как текст. '
            'Используйте {%% comment %%}…{%% endcomment %%}:\n'
            + '\n'.join(offenders))

    def test_comment_tags_are_balanced(self):
        """Незакрытый `{% comment %}` съедает остаток страницы молча."""
        offenders = []
        for path in template_files():
            with open(path, encoding='utf-8') as handle:
                source = handle.read()
            opened = len(re.findall(r'\{%\s*comment\s*.*?%\}', source))
            closed = len(re.findall(r'\{%\s*endcomment\s*%\}', source))
            if opened != closed:
                offenders.append('%s: comment=%d endcomment=%d'
                                 % (os.path.relpath(path, settings.BASE_DIR),
                                    opened, closed))
        self.assertEqual(offenders, [], '\n'.join(offenders))
