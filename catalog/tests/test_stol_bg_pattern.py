"""Водяные «W» на фоне: нет на входе каталога и на карте тем, есть на задаче.

Решение владельца 18.09.2026: на входе и на открытой карте фоном служит
облако карты тем — второй слой узора сверху делает экран грязным; на открытой
задаче фон спокойный, и «W» остаются, как на всех остальных страницах сайта.
Узор — псевдоэлементы `body::before/::after` (`templates/_tokens.html`), экран
гасит его атрибутом `<body data-bg-pattern="off">`; при смене вида без
перезагрузки его переключает `weco.stol.setView` (`stol.js`).
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from problems.tests.factories import make_problem

BASE = Path(settings.BASE_DIR)
BODY = re.compile(r'<body[^>]*>')


def body_tag(response):
    html = response.content.decode()
    return BODY.search(html, html.index("</head>")).group(0)


class PatternPerViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.problem = make_problem('Монополист выбирает выпуск.')

    def test_entry_and_map_have_no_pattern(self):
        for url in (reverse('catalog:problem_list'), reverse('catalog:topic_map')):
            self.assertIn('data-bg-pattern="off"', body_tag(self.client.get(url)), url)

    def test_problem_and_other_pages_keep_the_pattern(self):
        for url in (reverse('catalog:problem_detail', args=[self.problem.pk]), '/'):
            self.assertNotIn('data-bg-pattern', body_tag(self.client.get(url)), url)


class PatternSwitchSourceTests(SimpleTestCase):

    def test_tokens_hide_both_layers_by_the_attribute(self):
        src = (BASE / 'templates/_tokens.html').read_text(encoding='utf-8')
        self.assertIn('body[data-bg-pattern="off"]::before,\nbody[data-bg-pattern="off"]::after { display: none; }', src)

    def test_view_switch_turns_the_pattern_on_only_for_the_problem(self):
        src = (BASE / 'catalog/static/catalog/js/stol.js').read_text(encoding='utf-8')
        self.assertIn("if (view === 'stol') { delete document.body.dataset.bgPattern; } "
                      "else { document.body.dataset.bgPattern = 'off'; }", src)
