"""Правило нуля: всё на экране — из данных или не показывается.

Решение владельца 04.09.2026
(https://app.notion.com/p/3d1b11c92bc181f2a58fca64235ef298): у проекта уже
был случай, когда числа «для примера» остались в шаблоне навсегда. Этот
набор сторожит три вещи:

  1. на ПУСТОЙ базе экраны каталога рендерятся без единого числа в тексте,
     кроме нулевых счётчиков и чисел, которые приходят из данных карты
     (файл `catalog/data/topic_map.json` — тоже данные, не литерал);
  2. в шаблонах каталога нет слов-обещаний («появится», «скоро», «пример»
     и т. д.) — ни в тексте страницы, ни в строках скриптов;
  3. подпись карты следует за данными карты.

Дополняется на каждом этапе редизайна (окно фильтров, страница задачи,
тест).
"""
import html as html_lib
import json
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase

BASE = Path(settings.BASE_DIR)

# Слова-обещания и заглушки, запрещённые в интерфейсе (§0.5 промпта).
FORBIDDEN = (
    r'появится', r'позже', r'скоро', r'в разработке', r'пример', r'demo',
    r'todo', r'placeholder', r'lorem',
)
_RX_FORBIDDEN = re.compile(r'(?<![\w-])(' + '|'.join(FORBIDDEN) + r')(?![\w-])',
                           re.IGNORECASE)

# Число в тексте: цифры (с пробелами-разделителями тысяч), не приклеенные
# к буквам — «3D» числом не считается, «5 090» считается.
_RX_NUMBER = re.compile(r'(?<![\w.,:/-])\d[\d  ]*(?![\w])')

_RX_SCRIPT = re.compile(r'<script\b[^>]*>.*?</script>', re.DOTALL | re.IGNORECASE)
_RX_STYLE = re.compile(r'<style\b[^>]*>.*?</style>', re.DOTALL | re.IGNORECASE)
_RX_HTML_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
_RX_TAG = re.compile(r'<[^>]+>')
_RX_DJANGO_COMMENT = re.compile(r'{%\s*comment\s*%}.*?{%\s*endcomment\s*%}', re.DOTALL)
_RX_DJANGO_INLINE = re.compile(r'{#.*?#}', re.DOTALL)
_RX_DJANGO_TAG = re.compile(r'{%.*?%}|{{.*?}}', re.DOTALL)
# Блок стилей шаблона и CSS-комментарии — не текст для человека:
# `::placeholder` там — псевдоэлемент, а не слово.
_RX_STYLE_BLOCK = re.compile(r'{%\s*block extra_style\s*%}.*?{%\s*endblock\s*%}', re.DOTALL)
_RX_CSS_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
_RX_JS_COMMENT = re.compile(r'/\*.*?\*/|(?<![:\'"])//[^\n]*', re.DOTALL)
_RX_JS_STRING = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`",
                           re.DOTALL)


def visible_text(html):
    """Текст страницы, как его увидит человек: без скриптов, стилей и тегов.

    Пробелы схлопнуты (и неразрывный тоже): «<b>0</b> задач» — это «0 задач».
    """
    text = _RX_SCRIPT.sub(' ', html)
    text = _RX_STYLE.sub(' ', text)
    text = _RX_HTML_COMMENT.sub(' ', text)
    text = _RX_TAG.sub(' ', text)
    return re.sub(r'[\s\xa0]+', ' ', html_lib.unescape(text))


def numbers_in(text):
    return {re.sub(r'[\s ]+', '', m.group(0)) for m in _RX_NUMBER.finditer(text)}


def template_user_text(source):
    """Текст шаблона, который может дойти до человека: разметка без
    комментариев и тегов плюс строковые литералы скриптов."""
    src = _RX_DJANGO_COMMENT.sub(' ', source)
    src = _RX_DJANGO_INLINE.sub(' ', src)
    src = _RX_HTML_COMMENT.sub(' ', src)
    src = _RX_STYLE_BLOCK.sub(' ', src)
    src = _RX_CSS_COMMENT.sub(' ', src)
    strings = []
    for block in _RX_SCRIPT.findall(src):
        body = _RX_JS_COMMENT.sub(' ', block)
        for m in _RX_JS_STRING.finditer(body):
            strings.append(next(g for g in m.groups() if g is not None))
    src = _RX_SCRIPT.sub(' ', src)
    src = _RX_STYLE.sub(' ', src)
    src = _RX_DJANGO_TAG.sub(' ', src)
    src = _RX_TAG.sub(' ', src)
    return html_lib.unescape(src) + '\n' + '\n'.join(strings)


def _map_numbers():
    from catalog.taxonomy_map import JSON_PATH
    data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
    themes = sum(1 for n in data['nodes'] if n['k'] == 'theme')
    return {str(themes), str(len(data['nodes']) - themes)}


class EmptyCatalogTests(TestCase):
    """База пуста: ни одного числа, кроме нулей и чисел карты."""

    def test_catalog_page_has_no_numbers(self):
        resp = self.client.get('/catalog/')
        self.assertEqual(resp.status_code, 200)
        found = numbers_in(visible_text(resp.content.decode()))
        allowed = {'0'} | _map_numbers()
        self.assertEqual(found - allowed, set(),
                         'числа не из данных: %s' % sorted(found - allowed))
        self.assertIn('0 задач', visible_text(resp.content.decode()))

    def test_catalog_page_shows_no_selection_ui(self):
        html = self.client.get('/catalog/').content.decode()
        self.assertNotIn('data-chip=', html)
        self.assertNotIn('ct-card', _RX_SCRIPT.sub('', html).split('<section class="ct-results"')[1])


class MapCaptionFollowsDataTests(TestCase):
    def test_caption_changes_with_the_map_file(self):
        nodes = [{'k': 'theme'}] * 2 + [{'k': 'tag'}] * 7
        fake = (json.dumps({'nodes': nodes}), '"etag-2-7"')
        with mock.patch('catalog.views._topic_map_payload', return_value=fake):
            text = visible_text(self.client.get('/catalog/').content.decode())
        self.assertIn('Карта тем · 2 темы, 7 тегов', text)


class NoPromisesInTemplatesTests(SimpleTestCase):
    """В шаблонах каталога нет слов-обещаний и заглушек."""

    TEMPLATES = ('catalog/templates/catalog', 'templates/_typing_placeholder.html')

    def _files(self):
        for rel in self.TEMPLATES:
            path = BASE / rel
            if path.is_file():
                yield path
            else:
                # Партиалы `*_css.html` — чистый CSS, текста для человека там нет.
                yield from (f for f in sorted(path.glob('*.html'))
                            if not f.name.endswith('_css.html'))

    def test_no_forbidden_words(self):
        offenders = {}
        for path in self._files():
            text = template_user_text(path.read_text(encoding='utf-8'))
            hits = sorted({m.group(1).lower() for m in _RX_FORBIDDEN.finditer(text)})
            if hits:
                offenders[str(path.relative_to(BASE))] = hits
        self.assertEqual(offenders, {})
