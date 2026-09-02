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

from problems.tests.tree import project_files

# Что эта проверка не считает своим предметом: сгенерированное и привозное.
# Чужие рабочие копии, venv и кэши инструментов отсекает общий обходчик —
# здесь перечисляется только то, что специфично для этой проверки.
SKIP_NAMES = ('reports', 'backups', 'materials', 'staticfiles')


def template_files():
    return project_files(settings.BASE_DIR, '.html', SKIP_NAMES)


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
