# -*- coding: utf-8 -*-
"""Токены `_tokens.html` доживают до браузера — разбором, а не чтением.

⚠️ ЗАЧЕМ ОТДЕЛЬНАЯ ПРОВЕРКА. Прочитать файл глазами (или регуляркой) мало:
объявление может физически стоять в файле и при этом НЕ СУЩЕСТВОВАТЬ для
браузера. 31.08.2026 так и вышло: объяснение перед `--font-ui` приводило
знаки комментария CSS как пример, браузер закрыл комментарий на середине
абзаца, разбор ошибки доел хвост объяснения до ближайшей точки с запятой —
и `--font-ui` уехал вместе с ним. Токен в файле есть, у браузера его нет,
`font-family: var(--font-ui)` недействителен, ВЕСЬ САЙТ рисуется Times с
засечками. Ни один тест не покраснел: проверки палитры ищут значения
регуляркой по файлу и находят их.

Поэтому здесь стили разбираются так же, как их разбирает браузер:
комментарии снимаются БЕЗ вложенности, блок режется по точке с запятой, и
объявлением считается только то, что стоит В НАЧАЛЕ куска. Съеденный токен
оказывается в середине чужого объявления и находится.

Соседняя проверка `test_css_comments.py` сторожит саму причину (знаки
комментария внутри комментария); эта сторожит следствие и потому переживёт
любую другую причину — опечатку в скобке, пропущенную точку с запятой,
незакрытую кавычку.
"""
import os
import re

from django.conf import settings
from django.test import SimpleTestCase

TOKENS_FILE = os.path.join(str(settings.BASE_DIR), 'templates', '_tokens.html')

# Токены, без которых экран ломается ВИДИМО, а не по мелочи. Список нарочно
# короткий: это не опись палитры (она в test_palette_tokens.py), а список
# того, чья пропажа сразу видна человеку.
MUST_SURVIVE = [
    '--font-ui',                 # пропал → Times с засечками на всём сайте
    '--fs-hero', '--fs-h1', '--fs-h2',
    '--fs-body', '--fs-ui', '--fs-meta',
    '--lh-tight', '--lh-body', '--lh-ui',
    '--bg', '--surface', '--surface-2', '--surface-tool', '--surface-info',
    '--text', '--text2', '--text3',
    '--accent', '--accent-ink', '--brand-amber',
    '--btn-bg', '--on-btn', '--nav-bg',
]

DJANGO_COMMENT = re.compile(
    r'\{#.*?#\}|\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', re.S)


def strip_css_comments(css):
    """Снимает комментарии ТАК ЖЕ, КАК БРАУЗЕР: первое закрытие — конец.

    Никакой вложенности. Если внутри тела встретится ещё один знак
    открытия — он останется обычным текстом, а хвост после первого закрытия
    вернётся в код. Именно это и нужно воспроизвести.
    """
    out, index = [], 0
    while True:
        start = css.find('/*', index)
        if start < 0:
            out.append(css[index:])
            break
        out.append(css[index:start])
        end = css.find('*/', start + 2)
        if end < 0:                      # незакрытый комментарий съедает хвост
            break
        index = end + 2
    return ''.join(out)


def declared_names(css):
    """Имена свойств, которые браузер увидит как объявления.

    Кусок между точками с запятой считается объявлением, только если имя
    стоит в его НАЧАЛЕ. Съеденный токен стоит в середине — и сюда не попадёт.
    """
    names = set()
    for chunk in strip_css_comments(css).split(';'):
        # У первого объявления блока перед именем стоит селектор с фигурной
        # скобкой (`:root {`). Скобка — граница: имя считается от неё.
        for brace in '{}':
            chunk = chunk.rpartition(brace)[2]
        head = chunk.strip().split(':', 1)[0].strip()
        if re.fullmatch(r'--[a-z0-9-]+', head):
            names.add(head)
    return names


class TokensSurviveCssParsingTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(TOKENS_FILE, encoding='utf-8') as handle:
            text = DJANGO_COMMENT.sub('', handle.read())
        blocks = re.findall(r'<style[^>]*>(.*?)</style>', text, re.S)
        cls.css = '\n'.join(blocks)
        cls.names = declared_names(cls.css)

    def test_style_block_found(self):
        self.assertTrue(self.css.strip(),
                        'В _tokens.html не нашлось блока <style> — '
                        'разбирать нечего, проверка стала бы пустой')

    def test_every_key_token_survives_parsing(self):
        missing = [name for name in MUST_SURVIVE if name not in self.names]
        self.assertEqual(
            missing, [],
            'Эти токены есть в файле, но браузер их НЕ увидит — их съел '
            'разбор ошибки в стилях выше по файлу: %s. Ищи лишний знак '
            'закрытия комментария, незакрытую скобку или кавычку ПЕРЕД '
            'первым из них.' % ', '.join(missing))

    def test_font_stack_ends_with_a_real_fallback(self):
        """Резерв обязан кончаться на sans-serif — иначе снова засечки."""
        match = re.search(r'--font-ui\s*:([^;]+);', strip_css_comments(self.css))
        self.assertIsNotNone(match, '--font-ui не найден после разбора')
        value = ' '.join(match.group(1).split())
        self.assertTrue(
            value.rstrip().endswith('sans-serif'),
            'Стек --font-ui обязан кончаться на sans-serif, чтобы при полном '
            'провале загрузки сайт остался без засечек. Сейчас: %r' % value)

    def test_every_face_has_font_display_swap(self):
        """Без swap браузер прячет текст, пока шрифт едет."""
        faces = re.findall(r'@font-face\s*\{(.*?)\}', strip_css_comments(self.css),
                           re.S)
        self.assertTrue(faces, '@font-face не найдено вовсе')
        without = [i for i, body in enumerate(faces, 1)
                   if 'swap' not in body]
        self.assertEqual(without, [],
                         'У начертаний %s нет font-display: swap' % without)

    def test_the_guard_catches_the_real_case(self):
        """Зубастость: тот самый абзац, что съел --font-ui 31.08.2026."""
        broken = (':root {\n'
                  '  /* объяснение, где знаки /* и */ приведены примером */\n'
                  '  --font-ui: Montserrat, sans-serif;\n'
                  '  --fs-body: 16px;\n'
                  '}\n')
        names = declared_names(broken)
        self.assertNotIn('--font-ui', names,
                         'разбор обязан потерять --font-ui на этом образце — '
                         'иначе проверка не воспроизводит поведение браузера')
        self.assertIn('--fs-body', names,
                      'разбор ошибки кончается на точке с запятой, '
                      'следующее объявление обязано выжить')
