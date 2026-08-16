# -*- coding: utf-8 -*-
"""
Парность комментариев в стилях (ревью 17.08).

⚠️ ЗАЧЕМ ЭТА ПРОВЕРКА. В наборе деталей комментарий закрывался ДВАЖДЫ:
первое закрытие стояло на середине, дальше шёл обычный текст. Разборщик
CSS принимает такой текст за начало селектора и ищет фигурную скобку —
то есть съедает его ВМЕСТЕ СО СЛЕДУЮЩИМ ПРАВИЛОМ. Так пропали чип типа
задачи (печатался обычным текстом на всех экранах, где он стоит) и
основной цвет полосы типа.

Ни `manage.py check`, ни рендер, ни питон-тесты этого не видят: страница
отдаёт 200 с любой ошибкой в стилях. Нашлось скриншотом — и это дорогой
способ ловить опечатку.

⚠️ ЗНАК ЗАКРЫТИЯ ВНУТРИ ТЕКСТА КОММЕНТАРИЯ — ЭТО ЗАКРЫТИЕ, даже в
кавычках и в обратных апострофах. Наступили на это прямо при написании
объяснения к первой находке.
"""
import os
import re

from django.conf import settings
from django.test import SimpleTestCase

# Комментарии Django (`{# … #}` и `{% comment %}`) вырезаются до разбора
# стилей, поэтому считаем по тексту, из которого они убраны.
DJANGO_COMMENT = re.compile(r'\{#.*?#\}|\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}',
                            re.S)


def css_blocks(text):
    """Куски `<style>` шаблона плюс сам файл, если он целиком стилевой."""
    text = DJANGO_COMMENT.sub('', text)
    blocks = re.findall(r'<style[^>]*>(.*?)</style>', text, re.S)
    if blocks:
        return blocks
    # Партиалы набора вставляются внутрь `<style>` целиком.
    return [text] if '{' in text and '<html' not in text else []


def unbalanced(text):
    """Номера строк с лишним закрытием и остаток открытых комментариев."""
    extra, depth = [], 0
    for number, line in enumerate(text.split('\n'), 1):
        index = 0
        while index < len(line):
            if line.startswith('/*', index):
                depth += 1
                index += 2
                continue
            if line.startswith('*/', index):
                depth -= 1
                if depth < 0:
                    extra.append(number)
                    depth = 0
                index += 2
                continue
            index += 1
    return extra, depth


def template_files():
    """Все шаблоны проекта — стили лежат и в общих партиалах, и в экранах."""
    roots = [os.path.join(settings.BASE_DIR, 'templates')]
    for app in os.listdir(settings.BASE_DIR):
        folder = os.path.join(settings.BASE_DIR, app, 'templates')
        if os.path.isdir(folder):
            roots.append(folder)
    for root in roots:
        for base, _, names in os.walk(root):
            for name in names:
                if name.endswith('.html'):
                    yield os.path.join(base, name)


class CssCommentsAreBalancedTests(SimpleTestCase):

    def test_no_stray_closing(self):
        broken = []
        for path in template_files():
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
            for block in css_blocks(text):
                extra, _ = unbalanced(block)
                if extra:
                    broken.append('%s: строки %s'
                                  % (os.path.relpath(path, settings.BASE_DIR),
                                     extra))
        self.assertEqual(broken, [], 'Лишнее закрытие комментария в стилях — '
                                     'следующее правило будет съедено: %s'
                                     % '; '.join(broken))

    def test_no_comment_left_open(self):
        broken = []
        for path in template_files():
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
            for block in css_blocks(text):
                _, depth = unbalanced(block)
                if depth:
                    broken.append(os.path.relpath(path, settings.BASE_DIR))
        self.assertEqual(broken, [], 'Незакрытый комментарий в стилях: %s'
                                     % ', '.join(broken))

    def test_the_guard_catches_the_real_case(self):
        """Проверка на зубастость: тот самый обломок, что жил в наборе."""
        sample = ('/* подпись */\n'
                  '   продолжение подписи */\n'
                  '.k-kind { color: red; }\n')
        extra, _ = unbalanced(sample)
        self.assertEqual(extra, [2])
