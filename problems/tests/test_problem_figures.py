# -*- coding: utf-8 -*-
"""Фаза B сессии 2026-08-28: отдельный контролируемый путь для картинок.

Главное здесь — НЕ happy-path, а `SecurityPerimeterTests`. Владелец
поставил условие явно: общий санитайзер и его allow-list не меняются, и
любой код, который в итоге позволит просочиться произвольному `src` из
ТЕКСТА задачи, — провал, даже если остальные тесты зелёные.
"""
import re

from django.test import SimpleTestCase, TestCase

from problems.corpus_converter.tikz_render import (
    MARKER_RE, block_hash, extract_tikz_blocks, make_marker, sanitize_svg,
)
from problems.figures import render_figures
from problems.models import Problem, ProblemFigure
from problems.rendering import render_markdown

_IMG_RE = re.compile(r'<img[^>]*>', re.I)


def imgs(html):
    return _IMG_RE.findall(html)


class MarkerFormatTests(SimpleTestCase):
    """Маркер — чистый текст без атрибутов, тело только hex."""

    def test_marker_is_plain_text_and_survives_sanitizer(self):
        marker = make_marker('a' * 64)
        rendered = render_markdown('текст ' + marker + ' дальше')
        self.assertIn(marker, rendered)
        self.assertEqual(imgs(rendered), [])

    def test_marker_regex_accepts_only_64_hex(self):
        self.assertTrue(MARKER_RE.fullmatch(make_marker('0' * 64)))
        for bad in ('../../etc/passwd', 'https://attacker.example/x.svg',
                    'a' * 63, 'a' * 65, 'A' * 64, 'zz' + 'a' * 62, '1;DROP'):
            self.assertIsNone(MARKER_RE.fullmatch('[[FIGURE:' + bad + ']]'),
                              'маркер не должен принимать ' + repr(bad))


class ExtractionTests(SimpleTestCase):
    """TikZ вырезается из текста и заменяется маркером."""

    def test_complete_tikzpicture_extracted(self):
        # Форма живого #31019.
        text = ('Стоимость портфеля:\n\n$$\n\\begin{tikzpicture}\n'
                ' \\draw [<->] (-3, -3) -- (0, 0) -- (3, -3);\n'
                '\\end{tikzpicture}\n$$\n')
        out, blocks = extract_tikz_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn('tikzpicture', out)
        self.assertIn(make_marker(blocks[0][0]), out)

    def test_bare_addplot_run_is_wrapped_and_extracted(self):
        # Форма живого #30164: \addplot без обёртки tikzpicture/axis.
        text = ('С учётом ограничения:\n'
                ' \\addplot[only marks, mark=*] coordinates {(4, 44)};\n'
                ' \\addplot[red, domain=4:8] {52 - 0.5*x^2};\n')
        out, blocks = extract_tikz_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn('addplot', out)
        self.assertIn('\\begin{axis}', blocks[0][1])
        self.assertIn('\\begin{tikzpicture}', blocks[0][1])

    def test_text_without_tikz_untouched(self):
        text = 'Обычное условие с формулой $x + 1$ и без графиков.'
        out, blocks = extract_tikz_blocks(text)
        self.assertEqual((out, blocks), (text, []))

    def test_hash_is_stable_and_content_addressed(self):
        src = '\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}'
        self.assertEqual(block_hash(src), block_hash(src))
        self.assertNotEqual(block_hash(src), block_hash(src + ' x'))
        self.assertRegex(block_hash(src), r'^[0-9a-f]{64}$')

    def test_extraction_is_idempotent(self):
        text = ('$$\n\\begin{tikzpicture}\\draw (0,0)--(1,1);'
                '\\end{tikzpicture}\n$$')
        once, _ = extract_tikz_blocks(text)
        twice, blocks2 = extract_tikz_blocks(once)
        self.assertEqual(once, twice)
        self.assertEqual(blocks2, [])


class SvgSanitizerTests(SimpleTestCase):
    """SVG чистится ДО записи в базу — второй рубеж, не единственный."""

    def test_script_removed_with_content(self):
        svg = '<svg><script>alert(1)</script><circle r="1"/></svg>'
        out = sanitize_svg(svg)
        self.assertNotIn('script', out.lower())
        self.assertNotIn('alert', out)

    def test_event_handlers_removed(self):
        out = sanitize_svg('<svg><circle r="1" onload="alert(1)"/></svg>')
        self.assertNotIn('onload', out.lower())
        self.assertNotIn('alert', out)

    def test_foreign_object_removed(self):
        out = sanitize_svg('<svg><foreignObject><b>x</b></foreignObject></svg>')
        self.assertNotIn('foreignobject', out.lower())

    def test_external_href_removed(self):
        svg = ('<svg><image xlink:href="https://attacker.example/x.png"/>'
               '<a href="https://attacker.example">t</a></svg>')
        out = sanitize_svg(svg)
        self.assertNotIn('attacker.example', out)

    def test_internal_use_reference_preserved(self):
        """dvisvgm рисует глифы через <use xlink:href='#id'> — это надо СОХРАНИТЬ.

        Найдено визуальной проверкой: пока `use` и `xlink:href` вырезались
        целиком, все 118 картинок на странице предпросмотра имели
        naturalWidth 0 — санитайзер «обезопасил» их до нечитаемости.
        Внутренняя ссылка никуда не ведёт и ничего не исполняет.
        """
        svg = ("<svg><defs><path id='g1-49' d='M0 0 L1 1'/></defs>"
               "<g><use x='1' y='2' xlink:href='#g1-49'/></g></svg>")
        out = sanitize_svg(svg)
        self.assertIn('<use', out)
        self.assertIn("xlink:href='#g1-49'", out)
        self.assertIn("id='g1-49'", out)

    def test_external_use_reference_removed(self):
        svg = "<svg><use xlink:href='https://attacker.example/x.svg#g'/></svg>"
        out = sanitize_svg(svg)
        self.assertNotIn('attacker.example', out)

    def test_data_uri_href_removed(self):
        svg = "<svg><use xlink:href='data:image/svg+xml;base64,AAAA'/></svg>"
        self.assertNotIn('data:', sanitize_svg(svg))

    def test_javascript_uri_href_removed(self):
        svg = '<svg><use xlink:href="javascript:alert(1)"/></svg>'
        self.assertNotIn('javascript:', sanitize_svg(svg).lower())

    def test_protocol_relative_href_removed(self):
        svg = "<svg><use xlink:href='//attacker.example/x.svg'/></svg>"
        self.assertNotIn('attacker.example', sanitize_svg(svg))

    def test_external_image_element_removed(self):
        svg = "<svg><image href='https://attacker.example/p.png' width='9'/></svg>"
        out = sanitize_svg(svg)
        self.assertNotIn('attacker.example', out)
        self.assertNotIn('<image', out)

    def test_geometry_preserved(self):
        svg = '<svg width="10" height="10"><path d="M0 0 L1 1"/></svg>'
        out = sanitize_svg(svg)
        self.assertIn('path', out)
        self.assertIn('M0 0 L1 1', out)


class FigureDisplayTests(TestCase):
    """Happy-path: маркер превращается в img из СВОЕЙ строки БД."""

    def setUp(self):
        self.problem = Problem.objects.create(statement='условие', answer='ответ')
        self.figure = ProblemFigure.objects.create(
            problem=self.problem, tikz_hash='b' * 64,
            tikz_source='\\begin{tikzpicture}\\end{tikzpicture}',
            svg='<svg><circle r="1"/></svg>',
        )

    def test_known_marker_becomes_img(self):
        html = render_markdown('график: ' + make_marker('b' * 64))
        out = render_figures(html, self.problem)
        found = imgs(out)
        self.assertEqual(len(found), 1)
        self.assertIn('/catalog/figure/' + str(self.figure.pk) + '.svg', found[0])

    def test_src_comes_from_db_not_from_text(self):
        # В тексте нет и не может быть URL — только hex-хеш.
        html = render_markdown(make_marker('b' * 64))
        out = render_figures(html, self.problem)
        self.assertIn(str(self.figure.pk), out)
        self.assertNotIn('b' * 64, out)


class SecurityPerimeterTests(TestCase):
    """Регрессия на КЛАСС атаки «произвольный src из текста задачи».

    Проверяется не один вектор, а вся граница: подделанный маркер,
    сырой тег, чужая картинка, несуществующий хеш. Ни один из них не
    имеет права дать рабочий img.
    """

    def setUp(self):
        self.problem = Problem.objects.create(statement='условие', answer='ответ')
        self.other = Problem.objects.create(statement='чужая', answer='ответ')
        self.foreign_figure = ProblemFigure.objects.create(
            problem=self.other, tikz_hash='c' * 64,
            tikz_source='src', svg='<svg/>',
        )

    def _render(self, raw_text):
        return render_figures(render_markdown(raw_text), self.problem)

    def test_marker_with_url_body_yields_no_img(self):
        out = self._render('[[FIGURE:https://attacker.example/x.svg]]')
        self.assertEqual(imgs(out), [])

    def test_marker_with_path_traversal_yields_no_img(self):
        out = self._render('[[FIGURE:../../../etc/passwd]]')
        self.assertEqual(imgs(out), [])

    def test_marker_with_relative_path_yields_no_img(self):
        out = self._render('[[FIGURE:/media/anything.svg]]')
        self.assertEqual(imgs(out), [])

    def test_raw_img_tag_in_problem_text_yields_no_img(self):
        """Сырой <img> из текста задачи не становится картинкой.

        Санитайзер ЭКРАНИРУЕТ тег, а не вырезает: на экране остаётся
        видимый текст `<img src=...>`, но работающего элемента нет. Это
        и есть нужное свойство — проверяем именно его, а не отсутствие
        подстроки: сам по себе текст, который написал автор, безвреден.
        """
        out = self._render('<img src="https://attacker.example/x.svg">')
        self.assertEqual(imgs(out), [])          # рабочего <img> нет
        self.assertNotIn('<img', out)            # и никакого сырого тега
        self.assertIn('&lt;img', out)            # ровно экранированный текст

    def test_raw_svg_tag_in_problem_text_yields_no_svg(self):
        """То же для <svg onload=...>: тег экранирован, обработчик мёртв."""
        out = self._render('<svg onload="alert(1)"><circle r="1"/></svg>')
        self.assertNotIn('<svg', out)            # рабочего элемента нет
        self.assertIn('&lt;svg', out)            # только экранированный текст
        # `onload` присутствует лишь как символы внутри экранированного
        # текста, атрибутом ни на чём не висит.
        self.assertNotIn('<circle', out)

    def test_markdown_image_syntax_yields_no_img(self):
        out = self._render('![подпись](https://attacker.example/x.svg)')
        self.assertEqual(imgs(out), [])

    def test_unknown_but_wellformed_hash_yields_no_img(self):
        # Формат правильный, строки в базе нет — картинки быть не должно.
        out = self._render(make_marker('d' * 64))
        self.assertEqual(imgs(out), [])

    def test_foreign_problem_figure_is_not_reachable(self):
        # Хеш существует, но принадлежит ДРУГОЙ задаче: подставить чужую
        # картинку через текст своей задачи нельзя.
        out = self._render(make_marker('c' * 64))
        self.assertEqual(imgs(out), [])
        self.assertNotIn('/catalog/figure/' + str(self.foreign_figure.pk) + '.svg', out)

    def test_uppercase_hash_is_not_accepted(self):
        ProblemFigure.objects.create(
            problem=self.problem, tikz_hash='e' * 64,
            tikz_source='src', svg='<svg/>')
        out = self._render('[[FIGURE:' + 'E' * 64 + ']]')
        self.assertEqual(imgs(out), [])
