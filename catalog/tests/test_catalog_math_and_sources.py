"""Формулы и картинки в каталоге, ссылка на первоисточник (17.09.2026).

Карточки и «Похожие» — сырой TeX без токенов картинок; модалка «Условие»
получает текст, отрисованный тем же партиалом, что страница задачи (с
картинками); KaTeX зовётся и после подмены выдачи фильтром. Чип источника —
внешняя ссылка, если адрес есть.
"""
import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from problems.models import Problem, ProblemFigure
from problems.tests.factories import link_source, make_problem, make_source, make_topic

PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
    '0000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')
FIGURE_HASH = 'b' * 64


class CatalogMathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.topic = make_topic('Эластичность', is_canonical=True)
        cls.problem = make_problem(
            'Посмотрите на график [[FIGURE:%s]] и найдите $Q_d = 10 - P$.' % FIGURE_HASH,
            topic=cls.topic, content_format=Problem.ContentFormat.MARKDOWN)
        ProblemFigure.objects.create(problem=cls.problem, tikz_hash=FIGURE_HASH,
                                     tikz_source='import', image_data=PNG_1PX,
                                     content_type='image/png', source_field='import')

    def test_card_has_tex_and_no_figure_token(self):
        html = self.client.get(reverse('catalog:problem_list')).content.decode('utf-8')
        self.assertFalse('[[FIGURE:' in html, 'токен картинки в карточке')
        self.assertTrue('$Q_d = 10 - P$' in html, 'формула не дошла до карточки как TeX')

    def test_filter_response_has_no_figure_token(self):
        resp = self.client.get(reverse('catalog:api_filter_state'), {'topic': self.topic.pk})
        self.assertFalse('[[FIGURE:' in json.loads(resp.content)['results_html'], 'токен в выдаче фильтра')

    def test_modal_api_renders_figure_like_the_page(self):
        data = self.client.get(reverse('catalog:api_problem', args=[self.problem.pk])).json()
        self.assertTrue('<img' in data['statement_html'], 'в модалке нет картинки')
        self.assertTrue('problem-figure' in data['statement_html'], 'картинка не тем механизмом')
        self.assertFalse('[[FIGURE:' in data['statement_html'], 'токен в модалке')

    def test_katex_runs_after_filter_swap_and_show_more(self):
        # Модалки «Условие» на входе «Стола» больше нет (решение 17.09.2026):
        # условие показывает сама задача. Подменённые куски выдачи — фильтр
        # и «Показать ещё» — идут тем же конвейером формул.
        base = Path(settings.BASE_DIR)
        filters_js = (base / 'catalog/static/catalog/js/catalog_filters.js').read_text(encoding='utf-8')
        stol_js = (base / 'catalog/static/catalog/js/stol.js').read_text(encoding='utf-8')
        base_html = (base / 'catalog/templates/catalog/base.html').read_text(encoding='utf-8')
        self.assertTrue('function renderMathIn(root)' in base_html, 'нет общего конвейера формул')
        self.assertTrue('window.renderMathIn(fresh)' in filters_js, 'выдача фильтра без KaTeX')
        self.assertTrue('window.renderMathIn(fresh)' in stol_js, '«Показать ещё» без KaTeX')


class SourceLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ile = make_source('ILE (iloveeconomics.ru)')
        cls.matek = make_source('МатЭк 57 школы')
        cls.with_url = make_problem('Задача ILE со ссылкой.')
        link_source(cls.with_url, cls.ile, url='https://www.iloveeconomics.ru/z/6246')
        cls.ile_no_url = make_problem('Задача ILE без ссылки.')
        link_source(cls.ile_no_url, cls.ile)
        cls.matek_problem = make_problem('Задача МатЭк.')
        link_source(cls.matek_problem, cls.matek)
        cls.evil = make_problem('Задача со ссылкой-сценарием.')
        link_source(cls.evil, cls.matek, url='javascript:alert(1)')

    def page(self, problem):
        return self.client.get(reverse('catalog:problem_detail', args=[problem.pk])).content.decode('utf-8')

    def test_page_chip_is_external_link(self):
        html = self.page(self.with_url)
        self.assertTrue('<a class="pp pp--src" href="https://www.iloveeconomics.ru/z/6246" '
                        'target="_blank" rel="noopener">' in html, 'чип источника не ссылка')
        self.assertTrue('class="pp-ext" width="12" height="12"' in html, 'нет значка внешней ссылки')

    def test_ile_without_url_links_home(self):
        self.assertTrue('href="https://iloveeconomics.ru/" target="_blank"' in self.page(self.ile_no_url),
                        'ILE без адреса не ведёт на главную')

    def test_matek_chip_is_plain_text(self):
        html = self.page(self.matek_problem)
        self.assertTrue('<span class="pp pp--src">МатЭк 57 школы</span>' in html, 'чип МатЭк не текстом')

    def test_javascript_url_is_never_a_link(self):
        html = self.page(self.evil)
        self.assertFalse('javascript:alert' in html, 'адрес-сценарий попал в страницу')

    def test_modal_api_source_links(self):
        data = self.client.get(reverse('catalog:api_problem', args=[self.with_url.pk])).json()
        self.assertEqual(data['source_links'], [{'name': 'ILE (iloveeconomics.ru)',
                                                 'url': 'https://www.iloveeconomics.ru/z/6246'}])
        data = self.client.get(reverse('catalog:api_problem', args=[self.evil.pk])).json()
        self.assertEqual(data['source_links'], [{'name': 'МатЭк 57 школы', 'url': ''}])
