# -*- coding: utf-8 -*-
u"""Стартовый экран Wecon Rush: правки раскладки по списку владельца (15.09.2026).

Решение владельца: без макета, только очевидные дефекты раскладки — переносы,
наезды, дубли, неровные высоты. Здесь разметка, стили и скрипт, на которых
держатся правки; сами числа раскладки меряет браузер
(`test_browser_layout.StartScreenBrowserTest`).
"""
from django.test import TestCase
from django.urls import reverse

from game.tests.test_page_js import inline_js, page_source


class StartScreenLayoutTests(TestCase):
    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)

    def page(self):
        return self.client.get(reverse('game:page')).content.decode('utf-8')

    def test_the_duplicate_line_of_entry_links_is_gone(self):
        self.assertFalse('>Дуэль с другом</a>' in self.page(), 'строка ссылок над карточками осталась')
        self.assertTrue('if (link) {' in self.js, 'привязка к ссылке без проверки на null')

    def test_duel_card_and_window_say_create_a_duel(self):
        html = self.page()
        for needle in ('<b>Создать дуэль</b><small>соперник по ссылке или коду</small>',
                       '<b id="dmodal-title">Создать дуэль</b>',
                       'id="dm-create">Создать дуэль<'):
            self.assertTrue(needle in html, 'нет: %s' % needle)
        self.assertFalse('Бросить вызов</b>' in html, 'осталось «Бросить вызов»')

    def test_entry_row_is_four_then_two_then_one(self):
        for needle in ('grid-template-columns: repeat(4, minmax(0, 1fr));',
                       '@media (max-width: 720px) {\n'
                       '  .entry-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }',
                       '@media (max-width: 480px) {\n'
                       '  .entry-row { grid-template-columns: 1fr; }'):
            self.assertTrue(needle in self.src, 'нет: %s' % needle)

    def test_leaderboard_tabs_segments_rows_and_footer(self):
        for needle in ('flex-wrap: nowrap;\n           overflow-x: auto; scrollbar-width: none; }',
                       '<div class="lb-segs">',
                       '.lb-row .vl { grid-column: 3; grid-row: 1 / span 2; text-align: right;',
                       '.lb-row .dt { grid-column: 2; grid-row: 2;'):
            self.assertTrue(needle in self.src, 'нет: %s' % needle)
        self.assertFalse('.lb-seg + .lb-seg' in self.src, 'второй сегмент снова со сдвигом')
        for needle in ("a.href = '/login/?next=/game/';", "a.textContent = 'Войти';"):
            self.assertTrue(needle in self.js, 'нет в подвале доски: %s' % needle)
        self.assertFalse('Войдите, чтобы попасть в таблицу' in self.js, 'старая строка подвала')

    def test_filter_button_shows_the_count_badge(self):
        self.assertTrue("n.className = 'n';" in self.js and 'n.textContent = rows.length;' in self.js,
                        'нет бейджа числа фильтров')
        self.assertTrue('.filter-open .n {' in self.src, 'бейдж без стиля')
