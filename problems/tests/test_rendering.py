# -*- coding: utf-8 -*-
"""Рендерер Markdown для условий задач (`problems/rendering.py`).

Подготовка к конвертации корпуса (CORPUS-FORMAT.md §2б) — рендерер узкого
подмножества markdown с math-aware защитой формул и `nh3`-санитайзером.
Эта сессия не трогает содержимое ни одной из существующих 31 694 задач:
рендерер применяется только к `content_format='markdown'`.

Два независимых источника риска проверяются отдельно:

1. Санитайзер должен резать опасные теги/атрибуты, даже если бы
   markdown-it-py каким-то образом пропустил их как есть (defense in
   depth — `_sanitize_html` тестируется напрямую, в обход markdown-it).
2. Полный конвейер `render_markdown` не должен пропускать нагрузки
   `test_xss_payloads.py` — это отдельный тестовый файл (см.
   `MarkdownRendererXssTests` там).

Математика проверяется на byte-точное совпадение через сравнение с тем,
что даёт `django.utils.html.escape` — именно так математика проходит
через СЕГОДНЯШНИЙ `plain`-режим (autoescape), и рендерер обязан выдать
то же самое.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils.html import escape

from problems.rendering import (
    render_markdown, _sanitize_html, _protect_math_and_currency,
)

PROBLEM_DETAIL_TEMPLATE = (
    Path(settings.BASE_DIR) / 'catalog' / 'templates' / 'catalog'
    / 'problem_detail.html'
)


def esc(s):
    return escape(s)


class BoldItalicTests(SimpleTestCase):
    def test_bold(self):
        self.assertIn('<strong>bold</strong>', render_markdown('**bold**'))

    def test_italic(self):
        self.assertIn('<em>italic</em>', render_markdown('*italic*'))

    def test_bold_and_italic_together(self):
        out = render_markdown('**жирный** и *курсив* в одном тексте')
        self.assertIn('<strong>жирный</strong>', out)
        self.assertIn('<em>курсив</em>', out)


class ListTests(SimpleTestCase):
    def test_numbered_list(self):
        out = render_markdown('1. первый\n2. второй')
        self.assertIn('<ol>', out)
        self.assertIn('<li>первый</li>', out)
        self.assertIn('<li>второй</li>', out)

    def test_bulleted_list(self):
        out = render_markdown('- альфа\n- бета')
        self.assertIn('<ul>', out)
        self.assertIn('<li>альфа</li>', out)
        self.assertIn('<li>бета</li>', out)


class TableTests(SimpleTestCase):
    def test_simple_table(self):
        out = render_markdown('| a | b |\n|---|---|\n| 1 | 2 |')
        self.assertIn('<table>', out)
        self.assertIn('<th>a</th>', out)
        self.assertIn('<td>1</td>', out)


class LineBreakTests(SimpleTestCase):
    def test_single_newline_becomes_br(self):
        out = render_markdown('строка один\nстрока два')
        self.assertIn('<br>', out)

    def test_blank_line_starts_new_paragraph(self):
        out = render_markdown('абзац один\n\nабзац два')
        self.assertEqual(out.count('<p>'), 2)


class EmptyInputTests(SimpleTestCase):
    def test_empty_string(self):
        self.assertEqual(render_markdown(''), '')

    def test_none(self):
        self.assertEqual(render_markdown(None), '')


# ---------------------------------------------------------------------------
# Защита математики — граница с markdown-разметкой
# ---------------------------------------------------------------------------

class MathProtectionTests(SimpleTestCase):
    """`$...$` и `$$...$$` не должны быть тронуты markdown-парсером.

    Критерий — то же самое, что дал бы `plain`-режим (autoescape): никакого
    `<em>`/`<strong>` внутри математики из-за `_`/`*`.
    """

    def test_subscript_underscore_survives(self):
        out = render_markdown('дано $x_1$ и $P_D$')
        self.assertIn(esc('$x_1$'), out)
        self.assertIn(esc('$P_D$'), out)
        self.assertNotIn('<em>', out)
        self.assertNotIn('<strong>', out)

    def test_row_break_before_closing_dollar_closes_span(self):
        r"""`\\` перед закрывающим `$` — перенос строки, а не экран доллара.

        Поиск закрытия пропускал `\$` как «экранированный доллар», но в
        `\\$` обратный слеш экранирует ВТОРОЙ СЛЕШ, а `$` после него —
        обычный разделитель. Формула не закрывалась и «съедала» текст до
        следующего `$`; KaTeX отвечал `Can't use function '$' in math
        mode` (25 задач трёх новых источников, живые #62556, #62939).

        Замер по всей базе: расхождение ровно у 25 задач, все — новые
        источники, легаси не задет ни одной."""
        _text, protected = _protect_math_and_currency(
            r'$a = 1 \\$ и текст $b = 2$')
        self.assertEqual(protected, [r'$a = 1 \\$', '$b = 2$'])

    def test_escaped_dollar_inside_math_still_not_a_delimiter(self):
        r"""Обратная сторона: одиночный `\$` внутри формулы — законный
        символ доллара, и закрытием формулы он быть не должен."""
        _text, protected = _protect_math_and_currency(r'цена $x = \$5 + y$ рублей')
        self.assertEqual(protected, [r'$x = \$5 + y$'])

    def test_row_break_before_closing_paren_delimiter(self):
        r"""`\\` перед `\)` не должен съесть сам разделитель `\)`."""
        _text, protected = _protect_math_and_currency(r'формула \(a = 1 \\\) конец')
        self.assertEqual(protected, [r'\(a = 1 \\\)'])

    def test_display_math_with_cases_survives(self):
        formula = r'$$\begin{cases}x + y = 1 \\ x - y = 0\end{cases}$$'
        out = render_markdown('Система: ' + formula)
        self.assertIn(esc(formula), out)
        self.assertNotIn('<em>', out)
        self.assertNotIn('<strong>', out)

    def test_math_with_asterisk_not_turned_into_emphasis(self):
        out = render_markdown('$a * b = c$ — произведение')
        self.assertIn(esc('$a * b = c$'), out)
        self.assertNotIn('<em>', out)

    def test_inline_parens_math_survives(self):
        out = render_markdown(r'формула \(x^2\) в тексте')
        self.assertIn(esc(r'\(x^2\)'), out)

    def test_display_brackets_math_survives(self):
        out = render_markdown(r'формула \[x^2\] отдельно')
        self.assertIn(esc(r'\[x^2\]'), out)

    def test_math_can_be_wrapped_in_bold(self):
        """«жирный+математика вперемешку» — реальный кейс Фазы 4."""
        out = render_markdown('**$x_1$ важно**')
        self.assertIn('<strong>', out)
        self.assertIn(esc('$x_1$'), out)

    def test_dollar_dollar_checked_before_single_dollar(self):
        """`$$` — разделитель раньше `$`, как в _katex_dollars.html и авторендере."""
        out = render_markdown('$$x^2$$ и текст')
        self.assertIn(esc('$$x^2$$'), out)
        self.assertNotIn('<em>', out)

    def test_math_with_html_special_chars_is_escaped(self):
        """`<`/`>` внутри формулы обязаны прийти в HTML экранированными.

        Без escape() при восстановлении математики `$x < 10$` вставляет в
        HTML настоящий `<`. Первая находка фазы зубастости: с пробелом
        после `<` (`$x < 10$`) тест всё равно не краснел — nh3 сам
        переэкранирует одинокий `<`, за которым не следует буква, при
        сериализации разобранного дерева обратно в строку. Дыру показал
        только `<`, за которым СРАЗУ буква (`$a<b$`) — html5-парсер nh3
        читает `<b` как начало тега `<b>`, и всё до ближайшего `>` (в том
        числе значимый текст) съедается как атрибуты чужого тега. Не
        просто «сломалось экранирование» — потерялись данные условия.
        """
        out = render_markdown('дано $x < 10$ и $y > 5$')
        self.assertIn(esc('$x < 10$'), out)
        self.assertIn(esc('$y > 5$'), out)

        out2 = render_markdown('два: $a<b$ рядом $c>d$')
        self.assertIn(esc('$a<b$'), out2)
        self.assertIn(esc('$c>d$'), out2)
        self.assertIn('рядом', out2)


class CurrencyEscapeTests(SimpleTestCase):
    """`\\$100` — экранированная валюта, не математика (см. _katex_dollars.html)."""

    def test_escaped_dollar_survives_with_backslash(self):
        out = render_markdown(r'заплатил \$100 за книгу')
        self.assertIn(r'\$100', out)

    def test_escaped_dollar_does_not_open_a_math_span(self):
        """`\\$100 и $x$` — валюта не должна съесть границу следующей формулы."""
        out = render_markdown(r'заплатил \$100 и решил $x_1$')
        self.assertIn(r'\$100', out)
        self.assertIn(esc('$x_1$'), out)
        self.assertNotIn('<em>', out)

    def test_escaped_dollar_next_to_math(self):
        """Ручной сценарий Фазы 4: \\$100 рядом с $x_1$."""
        out = render_markdown(r'Цена \$100, при этом $x_1 = 5$.')
        self.assertIn(r'\$100', out)
        self.assertIn(esc('$x_1 = 5$'), out)

    def test_bare_dollar_amount_without_escape_is_not_math(self):
        """Без экранирования и без пары `$5` не превращается в формулу-мусор."""
        out = render_markdown('стоит $5 всего')
        self.assertNotIn('<em>', out)
        self.assertNotIn('<strong>', out)


# ---------------------------------------------------------------------------
# Санитайзер: allow-list строгий
# ---------------------------------------------------------------------------

class SanitizerAllowListTests(SimpleTestCase):
    """Проверка allow-list НАПРЯМУЮ на nh3, в обход markdown-it.

    Так проверяется defense-in-depth: даже если бы markdown-it пропустил
    сырой HTML как есть (баг, регрессия настройки html=False), санитайзер
    обязан срезать опасные теги сам по себе.
    """

    def test_allowed_tags_survive(self):
        html = '<p>т<strong>е</strong><em>к</em>ст<ul><li>а</li></ul></p>'
        out = _sanitize_html(html)
        self.assertIn('<strong>', out)
        self.assertIn('<em>', out)
        self.assertIn('<ul>', out)
        self.assertIn('<li>', out)

    def test_script_tag_removed(self):
        out = _sanitize_html('<script>alert(1)</script>текст')
        self.assertNotIn('<script', out)
        self.assertNotIn('alert(1)', out)

    def test_img_tag_removed(self):
        out = _sanitize_html('<img src=x onerror=alert(1)>текст')
        self.assertNotIn('<img', out)
        self.assertNotIn('onerror', out)

    def test_anchor_tag_removed(self):
        out = _sanitize_html('<a href="javascript:alert(1)">клик</a>')
        self.assertNotIn('<a ', out)
        self.assertNotIn('href', out)
        self.assertNotIn('javascript:', out)

    def test_style_tag_removed(self):
        out = _sanitize_html('<style>body{display:none}</style>текст')
        self.assertNotIn('<style', out)
        self.assertNotIn('display:none', out)

    def test_iframe_tag_removed(self):
        out = _sanitize_html('<iframe src="javascript:alert(1)"></iframe>')
        self.assertNotIn('<iframe', out)
        self.assertNotIn('javascript:', out)

    def test_svg_onload_removed(self):
        out = _sanitize_html('<svg onload="alert(1)"></svg>текст')
        self.assertNotIn('<svg', out)
        self.assertNotIn('onload', out)

    def test_on_attributes_stripped_from_allowed_tag(self):
        out = _sanitize_html('<p onclick="alert(1)">текст</p>')
        self.assertNotIn('onclick', out)
        self.assertIn('текст', out)

    def test_no_attributes_survive_at_all_on_allowed_tags(self):
        """attributes={} — строго ноль атрибутов, не только on*."""
        out = _sanitize_html('<p class="x" id="y" data-z="1">текст</p>')
        self.assertNotIn('class=', out)
        self.assertNotIn('id=', out)
        self.assertNotIn('data-z', out)


class EndToEndRendererSanitizationTests(SimpleTestCase):
    """То же самое, но через полный render_markdown — путь, которым реально
    пойдёт условие задачи."""

    def test_script_via_markdown_is_inert(self):
        out = render_markdown('текст <script>alert(1)</script> ещё текст')
        self.assertNotIn('<script', out)

    def test_image_onerror_via_markdown_is_inert(self):
        """`<img ...>` уезжает в markdown-it экранированным текстом ещё
        ДО санитайзера (html: False) — слово «onerror» законно остаётся
        видимым текстом внутри `&lt;img ...&gt;`, это не дыра: браузер
        такой текст не разберёт как тег. Проверяем «живой» тег/атрибут,
        а не голое слово — та же логика, что в test_xss_payloads.py
        (`is_markup` payloads проверяются на RAW-форму, не на подстроку)."""
        out = render_markdown('**жирный** <img src=x onerror=alert(1)>')
        self.assertNotIn('<img ', out)
        self.assertIn(esc('<img src=x onerror=alert(1)>'), out)

    def test_markdown_link_syntax_does_not_produce_anchor(self):
        """`a` не в allow-list, и правило `link` не включено вовсе —
        `[клик](...)` остаётся литеральным текстом, не становится `<a href>`.
        Сам текст адреса безопасно виден на странице (как сегодня видно
        условие с `\\href{javascript:...}` в LaTeX — не тег, не ссылка)."""
        out = render_markdown('[клик](javascript:alert(1))')
        self.assertNotIn('<a ', out)
        self.assertNotIn('href=', out)


# ---------------------------------------------------------------------------
# CSS для таблиц — найдено владельцем на фикстурах 53711/53713: валидный
# <table> без единого правила выглядит слипшимся текстом, «это ещё хуже,
# чем плоский текст». Тесты структурные (читают исходник шаблона, как
# test_xss_payloads.py:test_modal_builds_nodes_not_html), не про пиксели —
# пиксели проверяет владелец глазами. Не завязаны на конкретные имена
# классов дизайн-системы (их у сайта для этого случая нет — см. .stats-table/
# .wk-table в platform/_stats_style.html, тот же язык: вес+цвет у шапки,
# горизонтальные разделители, без сплошной заливки и без width:100%).
# ---------------------------------------------------------------------------

class TableCssTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = PROBLEM_DETAIL_TEMPLATE.read_text(encoding='utf-8')

    def test_table_has_dedicated_css_rule(self):
        self.assertIn('.math-content table', self.source,
                      'нет ни одного правила для <table> внутри .math-content — '
                      'таблица рендерится без единого стиля')

    def test_cells_have_visible_row_separation_and_padding(self):
        """Хотя бы горизонтальный разделитель строк + вертикальный паддинг —
        buквально то, что просил владелец («или хотя бы»)."""
        cell_rules = re.findall(
            r'\.math-content (?:th|td)[^{,]*\{([^}]*)\}', self.source)
        self.assertTrue(cell_rules, 'нет правил для th/td внутри .math-content')
        combined = ' '.join(cell_rules)
        self.assertRegex(combined, r'border(?:-bottom)?\s*:',
                         'ни в одном правиле нет разделителя строк')
        self.assertRegex(combined, r'padding\s*:',
                         'ни в одном правиле нет вертикального паддинга')

    def test_header_is_visually_distinct_from_data_cell(self):
        """`th` обязан отличаться от `td` весом или фоном — иначе шапка не
        читается как шапка (первая жалоба владельца: «слипшиеся строки»)."""
        m = re.search(r'\.math-content th\s*\{([^}]*)\}', self.source)
        self.assertIsNotNone(m, 'нет отдельного правила .math-content th')
        rule = m.group(1)
        self.assertTrue(
            re.search(r'font-weight\s*:\s*(?:[6-9]00|bold)', rule)
            or re.search(r'background', rule),
            'заголовок таблицы ничем не отличим от обычной ячейки: %r' % rule)

    def test_table_does_not_force_full_width(self):
        """Требование владельца: не растягивать таблицу без нужды."""
        m = re.search(r'\.math-content table\s*\{([^}]*)\}', self.source)
        self.assertIsNotNone(m, 'нет правила .math-content table')
        self.assertNotRegex(m.group(1), r'width\s*:\s*100%')

    def test_table_colors_use_design_tokens_not_hardcoded_hex(self):
        """catalog/CLAUDE.md: хардкод hex ломает тёмную тему — цвета только
        через var(--…). Проверка = обе темы поддержаны без дублирования
        правил под [data-theme="dark"]."""
        rules = re.findall(
            r'\.math-content (?:table|th|td)[^{,]*\{([^}]*)\}', self.source)
        for rule in rules:
            self.assertNotRegex(rule, r'#[0-9a-fA-F]{3,8}\b',
                                'хардкод hex-цвета вместо var(--…): %r' % rule)
