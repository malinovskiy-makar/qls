"""Этап 3: окно «Все фильтры» — разметка, стартовое состояние, скрипт.

Числа считает сервер, скрипт их показывает; имена параметров адреса в
скрипте обязаны совпадать с `catalog.filters.PARAM` — тест читает файл.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase

from catalog import filters
from problems.models import Tag
from problems.tests.factories import (
    link_source, make_problem, make_source, make_topic,
)

CATALOG_URL = '/catalog/'
BASE = Path(settings.BASE_DIR)


class ModalMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mon = make_topic('Монополия и ценовая дискриминация')
        cls.gdp = make_topic('ВВП и национальные счета')
        cls.src = make_source('Сборник')
        cls.p1 = make_problem('Монополист.', topic=cls.mon, difficulty=5,
                              problem_type='тест: один ответ', solution='Р.')
        cls.p2 = make_problem('ВВП.', topic=cls.gdp, difficulty=2)
        link_source(cls.p1, cls.src)
        cls.tag = Tag.objects.create(name='Курно', slug='kurno')
        cls.p1.tags.add(cls.tag)

    def test_dialog_is_built_from_the_shared_module(self):
        html = self.client.get(CATALOG_URL).content.decode()
        self.assertIn('<dialog class="ct-all" id="ct-all"', html)
        groups = re.findall(r'data-fl="(\w+)"', html)
        self.assertEqual(groups, ['topic', 'kind', 'has_solution', 'tag', 'difficulty', 'source'])
        self.assertIn('<input class="fl-tag-input" type="search" id="tag-input"', html)
        self.assertEqual(re.findall(r'data-acc="(\w+)"', html), ['micro', 'macro'])
        # Тема — плитка-кнопка с aria-pressed и числом под своим ключом.
        self.assertIn('data-topic="%d" data-section="micro" aria-pressed="false"' % self.mon.pk, html)
        self.assertIn('data-count="topic:%d">1<' % self.mon.pk, html)
        self.assertIn('data-count="difficulty:5">1<', html)
        self.assertIn('data-count="kind:test">1<', html)
        # Формат теста в разметке — ВИД (`problems.problem_types`), а не
        # строка `problem_type`: одному виду отвечают два словаря названий.
        self.assertIn('data-count="test_type:single">1<', html)
        self.assertIn('data-count="has_solution">1<', html)
        self.assertIn('data-src="%d" aria-pressed="false"' % self.src.pk, html)
        self.assertIn('data-count="source:%d">1<' % self.src.pk, html)
        self.assertIn('Найдено <b id="found-n">2</b>', html)
        self.assertIn('Показать <b id="show-n">2</b> <span id="show-w">задачи</span>', html)
        # Форматы теста стоят ПОД «Тест» и скрыты, пока тест не выбран.
        self.assertIn('<div class="fl-sub" id="test-types"', html)
        # Групп без данных нет вовсе.
        self.assertNotIn('data-fl="character"', html)
        self.assertNotIn('data-fl="feature"', html)

    def test_selected_state_is_drawn_by_the_server(self):
        html = self.client.get(CATALOG_URL, {
            'topic': self.mon.pk, 'type': 'test', 'test_type': 'single',
            'has_solution': '1', 'difficulty': 5}).content.decode()
        self.assertIn('data-topic="%d" data-section="micro" aria-pressed="true"' % self.mon.pk, html)
        self.assertIn('class="fl-acc is-open" data-acc="micro"', html)
        self.assertIn('data-acc-sel="micro">1<', html)
        self.assertIn('data-block-sel="topic">выбрано 1<', html)
        self.assertIn('class="fl-sub is-on" id="test-types"', html)
        self.assertIn('data-ttype="single" aria-pressed="true"', html)
        self.assertIn('id="sol-switch" checked', html)
        self.assertIn('data-diff="5" aria-pressed="true"', html)
        self.assertIn('data-clear="topic">снять</button>', html)
        self.assertIn('data-clear="difficulty">снять</button>', html)
        state = json.loads(re.search(r'id="ct-filter-state">(.*?)</script>', html).group(1))
        self.assertEqual(state['active']['topics'], [str(self.mon.pk)])
        self.assertEqual(state['active']['difficulties'], ['5'])
        self.assertTrue(state['active']['has_solution'])
        self.assertEqual(state['urls']['state'], '/catalog/api/filter-state/')
        self.assertEqual(state['urls']['tags'], '/catalog/api/tags/')

    def test_old_window_markup_is_gone_and_problem_modal_stays(self):
        html = self.client.get(CATALOG_URL).content.decode()
        for gone in ('details class="fl-chip', 'class="fl-pop"', 'data-tag-box',
                     'fl-opts--next', 'class="fl-group"'):
            self.assertNotIn(gone, html)
        self.assertIn('id="c-modal-backdrop"', html)
        self.assertIn('function openCatalogModal', html)
        self.assertIn('function toggleHwDropdown', html)
        self.assertIn("catalog/js/catalog_filters.js", html)


class ScriptContractTests(SimpleTestCase):
    def test_script_parameter_names_match_filters_param(self):
        path = finders.find('catalog/js/catalog_filters.js')
        self.assertTrue(path, 'скрипт окна не найден статикой')
        src = Path(path).read_text(encoding='utf-8')
        block = re.search(r'var PARAM = \{(.*?)\};', src, re.S).group(1)
        names = dict(re.findall(r"(\w+):\s*'([^']+)'", block))
        self.assertEqual(names, filters.PARAM)
        lists = re.search(r"var LISTS = \[(.*?)\];", src).group(1)
        self.assertEqual(sorted(re.findall(r"'(\w+)'", lists)), sorted(filters.LIST_KEYS))

    def test_script_targets_every_control_of_the_window(self):
        src = Path(finders.find('catalog/js/catalog_filters.js')).read_text(encoding='utf-8')
        # Делегированный обработчик клика обязан слушать КАЖДЫЙ элемент окна и
        # полосы — проверяется сам селектор, а не наличие строки где-то в файле.
        selector = re.search(r"closest\('([^']+)'\)", src[src.index("addEventListener('click'"):]).group(1)
        for hook in ('[data-topic]', '[data-tag]', '[data-diff]', '[data-src]',
                     '[data-feat]', '[data-kind]', '[data-ttype]', '[data-char]',
                     '[data-clear]', '[data-remove]', '[data-expand]', '[data-acc-toggle]'):
            self.assertIn(hook, selector.split(','))
        for hook in ("getElementById('sol-switch')", 'AbortController',
                     'history.replaceState', 'showModal', "'?topic='"):
            self.assertIn(hook, src)
        for promise in ('появится', 'позже', 'скоро', 'demo', 'TODO'):
            self.assertNotIn(promise, src)
