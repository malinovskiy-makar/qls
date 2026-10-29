# -*- coding: utf-8 -*-
"""Контур качества (Q1): проверка отображения, автоисправления, очередь."""
import io
import shutil
import unittest

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings, tag
from PIL import Image

from problems.olympiad_contour import autofix, queue, render, views

HAS_NODE = bool(shutil.which('node'))


def png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), 'white').save(buf, 'PNG')
    return buf.getvalue()


class _Qs(list):
    def all(self):
        return self


class FakeFigure:
    def __init__(self, pk, data=b'', svg=''):
        self.pk, self.image_data, self.svg = pk, data, svg


class FakePart:
    def __init__(self, label, statement, answer=''):
        self.label, self.statement, self.answer = label, statement, answer


class FakeProblem:
    def __init__(self, statement, parts=(), figures=(), solution='', answer=''):
        self.statement, self.solution, self.answer = statement, solution, answer
        self.parts = _Qs(parts)
        self.figures = _Qs(figures)


def page(statement_html, solution_html=''):
    sol = '<section id="q-solution"><div class="math-content">%s</div></section>' % solution_html
    return ('<html><body><script>var x = "$ \\\\frac";</script><main><div class="stol-app">'
            '<section class="stm"><div class="math-content">%s</div></section></div>%s</main>'
            '</body></html>' % (statement_html, sol if solution_html else ''))


def fake_katex(texts, outside=False, full=False):
    """Без node: формула — «$…$», ошибка — если внутри «\\bad»."""
    out = []
    for t in texts:
        res = {'errors': [], 'currency': [], 'text_in_math': [], 'unpaired': 0, 'outside': t}
        if '\\bad' in t:
            res['errors'].append({'tex': '\\bad', 'problem': 'KaTeX parse error'})
        out.append(res)
    return out


class ParsePageTests(SimpleTestCase):
    def test_blocks_places_tables_images(self):
        html = page('<p>Условие</p><table><tr><td>1</td></tr></table><img src="/catalog/figure/7.svg">',
                    'Решение')
        p = render.parse_page(html)
        self.assertEqual([pl for pl, _t in p.nodes], ['условие', 'условие', 'решение'])
        self.assertEqual(p.tables, 1)
        self.assertEqual(p.imgs, [('условие', '/catalog/figure/7.svg')])

    def test_script_text_ignored(self):
        html = page('<p>x</p><script type="application/json">{"tex": "\\\\frac"}</script><style>.a{}</style>')
        self.assertEqual([t for _p, t in render.parse_page(html).nodes], ['x'])


class RChecksTests(SimpleTestCase):
    def codes(self, problem, html):
        return {f['code'] for f in render.r_checks(problem, html, katex_check=fake_katex)}

    def test_clean_page(self):
        pr = FakeProblem('Найдите выручку фирмы', figures=[FakeFigure(7, png_bytes())])
        html = page('<p>Найдите выручку фирмы</p><img src="/catalog/figure/7.svg">')
        self.assertEqual(self.codes(pr, html), set())

    def test_raw_markup_and_long_word(self):
        pr = FakeProblem('Текст задачи')
        # строки неразобранной таблицы приходят отдельными узлами (перенос — <br>)
        html = page('<p>Текст задачи **жирно**<br>| a | b |<br>\\frac{1}{2} [[FIGURE:ab12] &amp;lt; %s</p>'
                    % ('x' * 70))
        self.assertTrue({'raw_bold', 'raw_table', 'raw_tex', 'raw_figure_marker', 'raw_html_entity',
                         'long_word'} <= self.codes(pr, html))

    def test_katex_error_and_images(self):
        pr = FakeProblem('Задача', figures=[FakeFigure(7, b'not a png'), FakeFigure(8)])
        html = page('<p>Задача $\\bad$</p><img src="/catalog/figure/7.svg"><img src="/catalog/figure/8.svg">'
                    '<img src="/catalog/figure/9.svg"><img src="http://evil/x.png">')
        self.assertTrue({'katex_error', 'img_broken', 'img_empty', 'img_foreign', 'img_unknown_src'}
                        <= self.codes(pr, html))

    def test_table_not_rendered_and_text_cut(self):
        pr = FakeProblem('Спрос задан таблицей\n\n| P | Q |\n|---|---|\n| 1 | 2 |\n\nНайдите равновесие рынка',
                         parts=[FakePart('а', 'Посчитайте излишки')])
        html = page('<p>Спрос задан таблицей</p>')
        self.assertTrue({'table_not_rendered', 'text_cut'} <= self.codes(pr, html))


@unittest.skipUnless(HAS_NODE, 'нужен node')
class RChecksNodeTests(SimpleTestCase):
    def test_real_katex_per_text_node(self):
        pr = FakeProblem('Цена')
        # формула, разорванная тегом, — два узла: «$» без пары в каждом
        html = page('<p>Цена $P = <em>10</em>$ и $\\left( x$</p>')
        codes = {f['code'] for f in render.r_checks(pr, html)}
        self.assertIn('raw_dollar', codes)


class BChecksTests(SimpleTestCase):
    def test_codes(self):
        bad = {'scroll': True, 'scroll_px': 30, 'overflow': ['TABLE'], 'katex_err': 1, 'red': 2,
               'broken_img': ['/x'], 'wide_table': 1}
        good = {'scroll': False, 'overflow': [], 'katex_err': 0, 'red': 0, 'broken_img': [], 'wide_table': 0}
        fails = render.b_checks({'status': 200, 'widths': {'390': bad, '1280': good}})
        self.assertEqual({f['code'] for f in fails}, {'page_scroll', 'element_overflow', 'katex_error_dom',
                                                      'red_text', 'img_not_loaded', 'table_too_wide'})
        self.assertEqual(render.b_checks({'status': 200, 'widths': {'390': good, '1280': good}}), [])
        self.assertEqual(render.b_checks({'status': 404})[0]['code'], 'load_error')

    def test_contact_sample_even(self):
        olymp = {i: ('vp' if i < 50 else 'mosh') for i in range(100)}
        s = render.contact_sample(list(range(100)), olymp, 10)
        self.assertEqual(sum(olymp[i] == 'vp' for i in s), 5)
        self.assertEqual(s, render.contact_sample(list(range(100)), olymp, 10))


class PreviewGateTests(SimpleTestCase):
    @override_settings(QUALITY_CONTOUR_PREVIEW=False)
    def test_preview_off_is_404(self):
        with self.assertRaises(Http404):
            views.preview(RequestFactory().get('/_quality/problem/1/'), 1)

    def test_default_settings_have_no_preview(self):
        self.assertFalse(views.enabled())


class AutofixPureTests(SimpleTestCase):
    def test_number_space_and_entity(self):
        self.assertEqual(autofix.fix_number_space('1  000 и 2  500, а  б'), '1 000 и 2 500, а  б')
        self.assertEqual(autofix.fix_html_entity('a &amp;lt; b &nbsp;c &amp; d'), 'a < b  c & d')

    def test_strip_left_right(self):
        self.assertEqual(autofix.strip_left_right('\\left( x \\right. + \\left\\{ y'), '( x  + \\{ y')

    def test_currency_fix_positions(self):
        res = {'currency': ['$ за штуку, а 10$'], 'math': ['$ за штуку, а 10$', '$x+1$']}
        self.assertEqual(autofix.currency_fix('стоит 5$ за штуку, а 10$ всего, $x+1$', res),
                         'стоит 5\\$ за штуку, а 10\\$ всего, $x+1$')
        self.assertIsNone(autofix.currency_fix('нет формул', res))
        # сбитая пара выше по тексту — не валюта, а след поломки: не правим
        self.assertIsNone(autofix.currency_fix('стоит 5$ за штуку, а 10$ всего, $x+1$', dict(res, unpaired=1)))
        # цифра только у одного «$» — не однозначно
        res2 = {'currency': ['$ Б) При введении налога'], 'math': ['$ Б) При введении налога, и $']}
        self.assertIsNone(autofix.currency_fix('=120.$ Б) При введении налога, и $ а', res2))

    def test_number_space_only_digit_groups(self):
        self.assertEqual(autofix.fix_number_space('$L = 100  2x$ и 12  34'), '$L = 100  2x$ и 12  34')
        self.assertEqual(autofix.fix_number_space('1,5  000 и 25  000'), '1,5  000 и 25 000')


@unittest.skipUnless(HAS_NODE, 'нужен node')
class AutofixKatexTests(SimpleTestCase):
    def test_propose(self):
        texts = ['стоит 5$ за штуку, а 10$ всего, формула $x+1$', 'Найдите $\\left( \\frac{1}{2} $ и $y$',
                 'Решите $5x = 10$', 'Число 1  000']
        out = autofix.propose(texts)
        self.assertEqual(out[0], ('стоит 5\\$ за штуку, а 10\\$ всего, формула $x+1$', ['currency']))
        self.assertEqual(out[1], ('Найдите $( \\frac{1}{2} $ и $y$', ['left_right']))
        self.assertEqual(out[2], (None, []))
        self.assertEqual(out[3], ('Число 1 000', ['number_space']))
        # рядом остаются «формулы» из одних сумм — правка была бы частичной, отдаём людям
        table = 'Суммы $10 + $ и далее: стоит 5$ за штуку, а 10$ всего'
        self.assertEqual(autofix.propose([table])[0], (None, []))


class QueueTests(SimpleTestCase):
    def card(self, **kw):
        base = {'level': 'bank', 'olympiad': 'vp', 'ref_key': 'vp-2020-final-9-v1|1|', 'problem_id': 5,
                'statement': 'Число 1  000', 'solution': '', 'answer': '', 'criteria': '',
                'parts': [{'pk': 1, 'label': 'а', 'text': 'x', 'answer': ''}], 'test': None,
                'page_images': ['p1.png'], 'visible': True}
        base.update(kw)
        return base

    def test_item_format(self):
        it = queue.make_item(self.card(), 'S6', 'no_separator: | a |', codes=['no_separator'])
        self.assertEqual(it['item_id'], 'q1_contour:vp:5:S6')
        for key in ('item_id', 'source', 'olympiad', 'ref_key', 'problem_id', 'check', 'details',
                    'page_images', 'current', 'proposed', 'confidence'):
            self.assertIn(key, it)
        self.assertEqual(set(it['current']), {'statement', 'parts', 'solution', 'answer', 'criteria',
                                              'options', 'key'})
        self.assertEqual(it['severity'], 'major')
        self.assertEqual(queue.severity('S7', ['no_key']), 'blocker')
        self.assertEqual(queue.severity('S9', ['title_stub']), 'minor')
        self.assertEqual(queue.severity('R3', ['raw_bold']), 'blocker')

    def test_autofix_items(self):
        with unittest.mock.patch.object(autofix, 'propose', lambda texts: [
                (t.replace('1  000', '1 000'), ['number_space']) if '1  000' in t else (None, [])
                for t in texts]):
            items = queue.autofix_items([self.card(parts=[{'pk': 1, 'label': 'а', 'text': 'Ещё 1  000', 'answer': ''}])])
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertTrue(it['auto'])
        self.assertEqual(it['confidence'], 1.0)
        self.assertEqual(it['item_id'], 'q1_contour:vp:5:R3:auto')
        self.assertEqual(it['proposed']['statement'], 'Число 1 000')
        self.assertEqual(it['proposed']['parts'][0], {'pk': 1, 'label': 'а', 'text': 'Ещё 1 000', 'answer': ''})

    def test_shame_free(self):
        self.assertTrue(queue._shame_free({'failed_checks': ['S9']}, {'failed_checks': ['B4']}))
        self.assertFalse(queue._shame_free({'failed_checks': ['S9']}, {'failed_checks': ['R3']}))
        self.assertFalse(queue._shame_free({'failed_checks': ['S6']}, {'failed_checks': []}))


BROKEN_PAGE = '''<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
<main><div class="math-content">
<p>Текст</p><span class="katex-error" style="color:#cc0000">\\bad</span>
<img src="missing-%s.png">
<div style="width:2000px">широкий блок</div>
<div style="overflow-x:auto;max-width:100%%"><div style="width:3000px">в прокрутке — не вылет</div></div>
<table style="display:block;overflow-x:auto;max-width:100%%"><tr><td style="min-width:3000px">x</td></tr></table>
</div></main></body></html>'''


# serial: Chromium отдельным процессом node (как у остальных браузерных классов,
# docs/TESTING.md) — восемь браузеров разом в параллельном шаге не нужны.
@tag('serial')
class RenderScriptBrowserTests(SimpleTestCase):
    """Замеры B1–B4 браузерного скрипта на странице с заведомыми поломками."""

    def test_measure(self):
        import json
        import os
        import subprocess
        import tempfile
        import uuid

        from django.conf import settings
        if not HAS_NODE or not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('нет node или playwright в node_modules')
        with tempfile.TemporaryDirectory() as tmp:
            page_path = os.path.join(tmp, 'p.html')
            with open(page_path, 'w', encoding='utf-8') as handle:
                handle.write(BROKEN_PAGE % uuid.uuid4().hex)
            out = os.path.join(tmp, 'out.jsonl')
            cfg = {'jobs': [{'pid': 1, 'url': 'file:///' + page_path.replace('\\', '/')}], 'out': out,
                   'html_dir': None, 'shot_dir': None, 'shots': [], 'concurrency': 1, 'widths': [390, 1280]}
            cfg_path = os.path.join(tmp, 'jobs.json')
            with open(cfg_path, 'w', encoding='utf-8') as handle:
                json.dump(cfg, handle)
            script = os.path.join(settings.BASE_DIR, 'scripts', 'olympiad_contour_render.js')
            subprocess.run(['node', script, cfg_path], check=True, capture_output=True, timeout=180)
            with open(out, encoding='utf-8') as handle:
                rec = json.loads(handle.readline())
        m = rec['widths']['390']
        self.assertNotIn('error', rec)
        self.assertTrue(m['scroll'])
        self.assertEqual(len(m['overflow']), 1, m['overflow'])     # только широкий блок, не прокрутка
        self.assertEqual((m['katex_err'], m['red']), (1, 1))
        self.assertEqual(len(m['broken_img']), 1)
        self.assertEqual(m['wide_table'], 1)
        fails = render.b_checks(dict(rec, status=200))
        self.assertTrue({'page_scroll', 'element_overflow', 'katex_error_dom', 'red_text', 'img_not_loaded',
                         'table_too_wide'} <= {f['code'] for f in fails})


import unittest.mock  # noqa: E402 — нужен только QueueTests
