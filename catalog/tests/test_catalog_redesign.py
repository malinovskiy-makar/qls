"""Редизайн каталога, этап 1: поле поиска, полоса выбранного, карточки.

Промпт владельца 04.09.2026 и решения Notion (04.09): поле — единственный
герой, бегущая подсказка общая с главной, карта в высоту поля с подписью
из данных, полоса — только выбранное, карточки без номера и без таблицы,
превью без сирот, заголовок-обрезок не показывается.
"""
import json
import os
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from catalog import filters, placeholder_phrases as phrases, topic_blocks
from catalog.preview import cut_words, looks_like_statement_cut, preview_text
from catalog.taxonomy_map import JSON_PATH
from problems.tests.factories import (
    link_source, make_problem, make_source, make_topic,
)

BASE = Path(settings.BASE_DIR)
CATALOG_URL = '/catalog/'


def _results_section(html):
    """Разметка блока найденных задач — между открывающим и закрывающим тегами."""
    start = html.index('<section class="ct-results"')
    return html[start:html.index('</section>', start)]


def _card_html(html, problem):
    """Разметка одной карточки по адресу задачи."""
    href = reverse('catalog:problem_detail', args=[problem.pk])
    pos = html.index('href="%s"' % href)
    start = html.rindex('<a class="ct-card"', 0, pos)
    return html[start:html.index('</a>', pos)]


# ── 1.1 Бегущая подсказка и поле ─────────────────────────────────────────

class TypingPlaceholderTests(TestCase):
    def test_catalog_page_carries_all_eleven_phrases(self):
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertEqual(len(phrases.CATALOG_PHRASES), 11)
        for item in phrases.CATALOG_PHRASES:
            self.assertIn(item['text'], html)
        self.assertIn('Смотри, мне нужен кач про Канье Веста', html)
        # Первая фраза лежит в разметке — она же статичная подсказка.
        self.assertIn('placeholder="%s"' % phrases.CATALOG_PHRASES[0]['text'], html)
        self.assertIn(phrases.CATALOG_STOP_TEXT, html)

    def test_home_page_carries_the_same_six_phrases(self):
        html = self.client.get('/').content.decode()
        self.assertEqual(len(phrases.HOME_PHRASES), 6)
        for item in phrases.HOME_PHRASES:
            self.assertIn(item['text'], html)
        self.assertIn('placeholder="%s"' % phrases.HOME_PHRASES[0]['text'], html)
        self.assertTrue(phrases.HOME_PHRASES[4].get('muse'))

    def test_exactly_one_typing_implementation_in_the_repository(self):
        """grep SLIPS по шаблонам и статике даёт ровно один файл — партиал."""
        hits = []
        for root in ('templates', 'catalog', 'problems', 'teacher', 'student',
                     'game', 'calc2', 'olympiads', 'calendar_stub'):
            for dirpath, _dirs, files in os.walk(BASE / root):
                if 'node_modules' in dirpath or '/tests' in dirpath:
                    continue
                for name in files:
                    if not name.endswith(('.html', '.js')):
                        continue
                    path = Path(dirpath) / name
                    if 'SLIPS' in path.read_text(encoding='utf-8', errors='ignore'):
                        # as_posix — чтобы на Windows путь сравнивался с тем же
                        # эталоном, что на Mac и в CI.
                        hits.append(path.relative_to(BASE).as_posix())
        self.assertEqual(hits, ['templates/_typing_placeholder.html'])


class SearchFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.topic = make_topic('Эластичность')
        make_problem('Задача про эластичность спроса.', topic=cls.topic)

    def test_field_is_the_hero_with_buttons_inside(self):
        html = self.client.get(CATALOG_URL).content.decode()
        for needle in ('<form class="ask"', 'id="ct-q"', 'class="ask-hint"',
                       'class="ask-busy"', 'id="ask-clear"', 'id="ask-go"',
                       'Ищем по смыслу: точные слова не нужны'):
            self.assertIn(needle, html)
        # Отдельных кнопок «Найти» и «Очистить» больше нет.
        self.assertNotIn('>Найти<', html)
        self.assertNotIn('>Очистить<', html)

    def test_active_filters_ride_inside_the_form(self):
        html = self.client.get(CATALOG_URL, {'topic': self.topic.pk}).content.decode()
        form = html[html.index('<form class="ask"'):html.index('</form>')]
        self.assertIn('name="topic" value="%d"' % self.topic.pk, form)


# ── 1.2 Карта и полоса ───────────────────────────────────────────────────

class MapCaptionTests(TestCase):
    def test_caption_follows_map_data(self):
        nodes = [{'k': 'theme'}] * 3 + [{'k': 'tag'}] * 5
        fake = (json.dumps({'nodes': nodes}), '"fake-etag"')
        with mock.patch('catalog.views._topic_map_payload', return_value=fake):
            html = self.client.get(CATALOG_URL).content.decode()
        self.assertIn('<b>Карта тем</b> · 3&nbsp;темы, 5&nbsp;тегов', html)

    def test_caption_matches_the_real_map_file(self):
        data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
        themes = sum(1 for n in data['nodes'] if n['k'] == 'theme')
        tags = len(data['nodes']) - themes
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertIn('<b>Карта тем</b> · %d&nbsp;' % themes, html)
        self.assertIn(', %d&nbsp;' % tags, html)

    def test_no_literal_caption_left_in_template(self):
        src = (BASE / 'catalog/templates/catalog/problem_list.html').read_text(encoding='utf-8')
        self.assertNotIn('29 тем', src)
        self.assertNotIn('343 тега', src)


class StripTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mon = make_topic('Монополия и ценовая дискриминация')
        cls.gdp = make_topic('ВВП и национальные счета')
        cls.source = make_source('Сборник')
        cls.p1 = make_problem('Монополист с линейным спросом.', topic=cls.mon,
                              difficulty=4, solution='Решение.',
                              problem_type='тест: один ответ')
        cls.p2 = make_problem('Считаем ВВП по расходам.', topic=cls.gdp,
                              difficulty=2)
        link_source(cls.p1, cls.source)

    def test_nothing_selected_means_no_chips_badge_or_reset(self):
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertIn('id="ct-all-open"', html)
        self.assertNotIn('data-chip=', html)
        # «Сбросить» есть в разметке для скрипта, но скрыта, пока нечего снимать.
        self.assertIn('data-clear="all" hidden>Сбросить</a>', html)
        self.assertNotIn('<span class="n">', html)
        # Старые пять чипов-групп каталог больше не подключает.
        self.assertNotIn('class="fl-chip', html)

    def test_selected_filters_become_chips_in_owner_order(self):
        resp = self.client.get(CATALOG_URL, {
            'topic': self.mon.pk, 'difficulty': 4, 'has_solution': '1',
            'type': 'тест: один ответ', 'source': self.source.pk,
        })
        html = resp.content.decode()
        kinds = re.findall(r'data-chip="(\w+)"', html)
        self.assertEqual(kinds, ['topic', 'difficulty', 'kind', 'solution', 'source'])
        labels = re.findall(r'data-chip="\w+"[^>]*>([^<]+)<a', html)
        self.assertEqual(labels, ['Монополия и ценовая дискриминация', '★ 4',
                                  'Тест · один верный', 'С решением ✓', 'Сборник'])
        self.assertIn('<span class="n">5</span>', html)
        self.assertIn('class="strip-reset" id="strip-reset" href=', html)
        self.assertNotIn('data-clear="all" hidden>', html)
        # Чип темы окрашен блоком: монополия — «Микро» (пять цветов, решение 05.09).
        self.assertIn('class="chip chip--g" style="--gc: var(--map-g-micro)"', html)
        self.assertEqual(len(resp.context['cards']), 1)

    def test_chip_cross_removes_only_its_own_filter(self):
        html = self.client.get(CATALOG_URL, {'topic': self.mon.pk,
                                             'difficulty': 4}).content.decode()
        hrefs = dict(re.findall(r'href="([^"]+)" data-remove="(\w+):', html))
        by_kind = {kind: href for href, kind in hrefs.items()}
        self.assertNotIn('topic=', by_kind['topic'])
        self.assertIn('difficulty=4', by_kind['topic'])
        self.assertNotIn('difficulty=', by_kind['difficulty'])
        self.assertIn('topic=%d' % self.mon.pk, by_kind['difficulty'])

    def test_active_source_keeps_its_chip_even_at_zero_count(self):
        """Источник выбран, под остальными фильтрами у него ноль — чип есть."""
        html = self.client.get(CATALOG_URL, {'source': self.source.pk,
                                             'difficulty': 2}).content.decode()
        self.assertEqual(re.findall(r'data-chip="(\w+)"', html),
                         ['difficulty', 'source'])
        self.assertIn('data-chip="source">Сборник<a', html)
        self.assertIn('<span class="n">2</span>', html)

    def test_chips_are_a_key_of_the_shared_filters_module(self):
        active = filters.parse({'topic': str(self.mon.pk), 'has_solution': '1'})
        _qs, ctx = filters.build(filters.base_queryset('catalog'), active)
        self.assertEqual([c['kind'] for c in ctx['chips']], ['topic', 'solution'])
        self.assertEqual(ctx['chips'][0]['section'], 'micro')

    def test_difficulty_label_collapses_ranges(self):
        self.assertEqual(filters.difficulty_label([4]), '★ 4')
        self.assertEqual(filters.difficulty_label([4, 5]), '★ 4–5')
        self.assertEqual(filters.difficulty_label(['5', '2', '4']), '★ 2, 4–5')
        self.assertEqual(filters.difficulty_label([1, 2, 3]), '★ 1–3')


# ── 1.3 Карточки ─────────────────────────────────────────────────────────

CUT_TITLE = 'Известно, что монополист получает максимальную выр'
CUT_STATEMENT = ('Известно, что монополист получает максимальную выручку в точке '
                 '$P=20$, $Q=40$. Найдите функцию спроса.')


class CardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mon = make_topic('Монополия и ценовая дискриминация')
        cls.p_cut = make_problem(CUT_STATEMENT, title=CUT_TITLE, topic=cls.mon)
        cls.p_named = make_problem('На школьной ярмарке спрос задан как $Q_d = 120 - P$.',
                                   title='Вмешательство — 5', topic=cls.mon,
                                   difficulty=4, solution='Полное решение.')
        cls.p_test = make_problem('Выберите верные утверждения.',
                                  title='Выберите верные утверждения.',
                                  problem_type='тест: все верные')
        cls.p_test_plain = make_problem('Что такое инфляция?', title='Инфляция',
                                        problem_type='тест')

    def test_no_number_and_no_table_anywhere(self):
        html = self.client.get(CATALOG_URL).content.decode()
        results = _results_section(html)
        self.assertNotIn('ct-card-id', html)
        self.assertNotIn('№', results)
        self.assertNotIn('>Таблица<', html)
        self.assertIn('>Строки<', html)
        self.assertIn('>Галерея<', html)

    def test_table_address_falls_back_to_rows(self):
        resp = self.client.get(CATALOG_URL, {'view': 'table'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['view_mode'], 'rows')
        self.assertNotIn('<table', resp.content.decode())

    def test_preview_keeps_formula_text_without_orphans(self):
        cards = {c['problem'].pk: c for c in self.client.get(CATALOG_URL).context['cards']}
        preview = cards[self.p_cut.pk]['preview']
        self.assertIn('P=20', preview)
        self.assertIn('Q=40', preview)
        self.assertNotIn(' , ', preview)
        self.assertNotIn(' .', preview)

    def test_title_shown_only_when_it_is_a_name(self):
        cards = {c['problem'].pk: c for c in self.client.get(CATALOG_URL).context['cards']}
        self.assertFalse(cards[self.p_cut.pk]['show_title'])
        self.assertTrue(cards[self.p_named.pk]['show_title'])
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertNotIn('<div class="ct-card-title">%s</div>' % CUT_TITLE, html)
        self.assertIn('<div class="ct-card-title">Вмешательство — 5</div>', html)

    def test_stars_only_when_difficulty_is_set(self):
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertNotIn('☆', _card_html(html, self.p_cut))
        self.assertNotIn('ct-stars', _card_html(html, self.p_cut))
        self.assertIn('★★★★☆', _card_html(html, self.p_named))

    def test_topic_chip_only_when_there_is_a_topic(self):
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertNotIn('tchip', _card_html(html, self.p_test))
        self.assertIn('<span class="tchip" style="--gc: var(--map-g-micro)">'
                      'Монополия и ценовая дискриминация</span>',
                      _card_html(html, self.p_named))

    def test_test_format_label(self):
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertIn('<span class="ct-kind">тест · выбор всех верных</span>',
                      _card_html(html, self.p_test))
        self.assertIn('<span class="ct-kind">тест</span>',
                      _card_html(html, self.p_test_plain))
        self.assertNotIn('ct-kind', _card_html(html, self.p_named))

    def test_gallery_is_the_same_card_without_duplicate_title(self):
        html = self.client.get(CATALOG_URL, {'view': 'gallery'}).content.decode()
        results = _results_section(html)
        self.assertIn('class="ct-gallery"', results)
        self.assertEqual(results.count('Вмешательство — 5'), 1)
        self.assertNotIn('ct-card-id', results)


class PreviewTextTests(SimpleTestCase):
    def test_formulas_become_text(self):
        self.assertEqual(
            preview_text(CUT_STATEMENT),
            'Известно, что монополист получает максимальную выручку в точке '
            'P=20, Q=40. Найдите функцию спроса.')
        self.assertEqual(preview_text(r'Доля $\frac{a}{b}$ и $x \cdot y \le 3$.'),
                         'Доля a/b и x · y ≤ 3.')
        self.assertEqual(preview_text(r'Спрос \(Q_{d} = 10 \times P\) растёт.'),
                         'Спрос Q_d = 10 × P растёт.')
        self.assertEqual(preview_text(r'Скобки $\left(a+b\right)$ и \[x \ge 2\].'),
                         'Скобки (a+b) и x ≥ 2.')

    def test_long_formula_becomes_ellipsis_without_orphans(self):
        long = '$$' + ' + '.join('x_%d^{2}' % i for i in range(12)) + '$$'
        text = preview_text('Минимизируйте ( %s ), где x — вектор.' % long)
        self.assertEqual(text, 'Минимизируйте (…), где x — вектор.')
        for orphan in (' , ', ' .', ' ?,', '( )'):
            self.assertNotIn(orphan, text)

    def test_literal_dollar_survives(self):
        self.assertEqual(preview_text(r'Цена \$5 за штуку.'), 'Цена $5 за штуку.')

    def test_looks_like_statement_cut(self):
        self.assertTrue(looks_like_statement_cut(CUT_TITLE, CUT_STATEMENT))
        self.assertTrue(looks_like_statement_cut(CUT_TITLE + '…', CUT_STATEMENT))
        self.assertTrue(looks_like_statement_cut('Задача про спрос —', 'Другое условие.'))
        self.assertTrue(looks_like_statement_cut('Ж' * 71, 'Другое условие.'))
        self.assertFalse(looks_like_statement_cut('Ж' * 71 + '.', 'Другое условие.'))
        self.assertFalse(looks_like_statement_cut('Вмешательство — 5', CUT_STATEMENT))
        self.assertFalse(looks_like_statement_cut('', CUT_STATEMENT))

    def test_cut_words_never_splits_a_number(self):
        self.assertEqual(cut_words('Доход равен 3000 рублей в месяц', 16), 'Доход равен…')
        self.assertEqual(cut_words('коротко', 16), 'коротко')


# ── Пять блоков тем и цвет по разделу карты ─────────────────────────────

class TopicBlocksTests(SimpleTestCase):
    def test_block_order_is_the_owners(self):
        self.assertEqual([k for k, _l, _n in topic_blocks.BLOCKS],
                         ['micro', 'macro', 'fin', 'math', 'other'])

    def test_every_listed_name_lands_in_its_block(self):
        for key, _label, names in topic_blocks.BLOCKS:
            for name in names:
                self.assertEqual(topic_blocks.block_of(name), key, name)

    def test_sections_match_the_map_file(self):
        data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
        for node in data['nodes']:
            if node['k'] == 'theme':
                self.assertEqual(topic_blocks.section_of(node['l']), node['g'], node['l'])
        # Цвет = блок (пять цветов, решение 05.09): «Международная торговля»
        # стоит в Микро словами владельца и красится тем же блоком.
        self.assertEqual(topic_blocks.section_of('Монополия и ценовая дискриминация'), 'micro')
        self.assertEqual(topic_blocks.section_of('Международная торговля'), 'micro')
        self.assertEqual(topic_blocks.block_of('Международная торговля'), 'micro')

    def test_names_are_matched_loosely(self):
        self.assertEqual(topic_blocks.block_of('спрос  и предложение'), 'micro')
        self.assertEqual(topic_blocks.block_of('Ценовая политика'), 'other')
        self.assertEqual(topic_blocks.section_of('Ценовая политика'), 'other')
