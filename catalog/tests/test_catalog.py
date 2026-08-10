"""
Тесты публичного каталога: список, фильтры, страница задачи, качественный
шлюз, блок похожих, публичный API, случайная задача.
"""

from django.test import TestCase
from django.urls import reverse

from problems.models import Problem
from problems.tests.factories import (
    link_source, make_problem, make_source, make_topic,
)


class CatalogListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.topic_kpv = make_topic('Альтернативные издержки и КПВ')
        cls.topic_dem = make_topic('Спрос и предложение')
        cls.source_a = make_source('Источник А')
        cls.source_b = make_source('Источник Б')

        cls.p_kpv = make_problem('Задача про КПВ и альтернативные издержки.',
                                 topic=cls.topic_kpv, difficulty=2)
        cls.p_dem = make_problem('Задача про спрос и предложение на рынке.',
                                 topic=cls.topic_dem, difficulty=4,
                                 solution='Полное решение.')
        cls.p_flagged = make_problem('Битый рендер $x', topic=cls.topic_kpv,
                                     flagged=True)
        cls.p_draft = make_problem('Черновик.', status=Problem.Status.DRAFT)

        link_source(cls.p_kpv, cls.source_a)
        link_source(cls.p_dem, cls.source_b)

    def test_list_returns_200_and_shows_published(self):
        resp = self.client.get(reverse('catalog:problem_list'))
        self.assertEqual(resp.status_code, 200)
        ids = {c['problem'].pk for c in resp.context['cards']}
        self.assertIn(self.p_kpv.pk, ids)
        self.assertIn(self.p_dem.pk, ids)

    def test_counter_respects_quality_gate_and_status(self):
        """Счётчик каталога не учитывает зафлагованные и черновики."""
        resp = self.client.get(reverse('catalog:problem_list'))
        self.assertEqual(resp.context['total'], 2)
        ids = {c['problem'].pk for c in resp.context['cards']}
        self.assertNotIn(self.p_flagged.pk, ids)
        self.assertNotIn(self.p_draft.pk, ids)

    def test_filter_by_topic(self):
        resp = self.client.get(reverse('catalog:problem_list'),
                               {'topic': self.topic_dem.pk})
        ids = {c['problem'].pk for c in resp.context['cards']}
        self.assertEqual(ids, {self.p_dem.pk})

    def test_filter_by_source(self):
        resp = self.client.get(reverse('catalog:problem_list'),
                               {'source': self.source_a.pk})
        ids = {c['problem'].pk for c in resp.context['cards']}
        self.assertEqual(ids, {self.p_kpv.pk})

    def test_filter_by_difficulty_and_solution(self):
        resp = self.client.get(reverse('catalog:problem_list'),
                               {'difficulty': 4, 'has_solution': '1'})
        ids = {c['problem'].pk for c in resp.context['cards']}
        self.assertEqual(ids, {self.p_dem.pk})

    def test_search_query(self):
        resp = self.client.get(reverse('catalog:problem_list'),
                               {'q': 'КПВ'})
        ids = {c['problem'].pk for c in resp.context['cards']}
        self.assertEqual(ids, {self.p_kpv.pk})


class ProblemDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.topic = make_topic('Эластичность')
        cls.p = make_problem('Видимая задача.', topic=cls.topic)
        cls.p_flagged = make_problem('Скрытая задача.', flagged=True)
        cls.p_draft = make_problem('Черновик.', status=Problem.Status.DRAFT)
        cls.p_hidden_similar = make_problem('Скрытый похожий сосед.',
                                            flagged=True)
        cls.p_visible_similar = make_problem('Видимый похожий сосед.')
        cls.p.similar_problems.set([cls.p_hidden_similar.pk,
                                    cls.p_visible_similar.pk])

    def test_published_problem_page_opens(self):
        resp = self.client.get(
            reverse('catalog:problem_detail', args=[self.p.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_flagged_problem_returns_404(self):
        resp = self.client.get(
            reverse('catalog:problem_detail', args=[self.p_flagged.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_draft_problem_returns_404(self):
        resp = self.client.get(
            reverse('catalog:problem_detail', args=[self.p_draft.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_part_label_single_paren_and_intro(self):
        """H3 этап 4: метка «а)» не превращается в «а))»; над списком
        подпунктов — метка-разделитель."""
        from problems.models import ProblemPart
        p = make_problem('Условие с подпунктами.')
        ProblemPart.objects.create(problem=p, label='а)',
                                   statement='Первый.', order=1)
        ProblemPart.objects.create(problem=p, label='б',
                                   statement='Второй.', order=2)
        resp = self.client.get(
            reverse('catalog:problem_detail', args=[p.pk]))
        html = resp.content.decode()
        self.assertNotIn('а))', html)              # нет двойной скобки
        self.assertIn('>а)<', html)                # «а)» отрисовано
        self.assertIn('>б)<', html)                # голая «б» → «б)»
        self.assertIn('parts-intro', html)         # метка-разделитель

    def test_similar_block_excludes_hidden(self):
        """Блок «Похожие» не содержит зафлагованных задач даже из кэша."""
        resp = self.client.get(
            reverse('catalog:problem_detail', args=[self.p.pk]))
        similar_ids = {item['problem'].pk for item in resp.context['similar']}
        self.assertIn(self.p_visible_similar.pk, similar_ids)
        self.assertNotIn(self.p_hidden_similar.pk, similar_ids)


class CatalogApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.p = make_problem('Задача для API.')
        cls.p_flagged = make_problem('Скрытая.', flagged=True)

    def test_api_returns_problem_json(self):
        resp = self.client.get(
            reverse('catalog:api_problem', args=[self.p.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.p.pk)

    def test_api_404_for_flagged(self):
        resp = self.client.get(
            reverse('catalog:api_problem', args=[self.p_flagged.pk]))
        self.assertEqual(resp.status_code, 404)


class RandomProblemTests(TestCase):
    def test_random_redirects_to_visible_problem(self):
        p = make_problem('Единственная видимая.')
        make_problem('Скрытая.', flagged=True)
        resp = self.client.get(reverse('catalog:random_problem'))
        self.assertRedirects(
            resp, reverse('catalog:problem_detail', args=[p.pk]))

    def test_random_without_problems_redirects_to_list(self):
        resp = self.client.get(reverse('catalog:random_problem'))
        self.assertRedirects(resp, reverse('catalog:problem_list'))


class HomePageTests(TestCase):
    def test_home_opens(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)


class CurrencyEscapeFrontendTests(TestCase):
    """Сессия E: страница задачи с литеральными \\$ отдаёт и данные,
    и расширенную чистку \\$ \\_ \\& \\# со страховочным вызовом
    на DOMContentLoaded.

    ⚠️ С 2026-08-10 сам конвейер живёт в общем партиале
    `templates/_katex_dollars.html` — проверяем его содержимое на странице,
    а не старую метку версии «fix-v2».
    """

    def test_page_contains_escaped_data_and_fix_v2_script(self):
        p = make_problem(
            'She requires \\$10,000 to cover initial setup costs.')
        resp = self.client.get(
            reverse('catalog:problem_detail', args=[p.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # данные с эскейпом дошли до страницы
        self.assertIn('\\$10,000', html)
        # конвейер чистки на странице есть
        self.assertIn('function fixCurrencyDollars', html)
        self.assertIn("split('\\\\_').join('_')", html)
        # страховочный вызов после KaTeX / при недоступном CDN
        self.assertIn("addEventListener('DOMContentLoaded'", html)
        # чистка в раскрывашках вызывается безусловно
        self.assertIn('fixCurrencyDollars(block)', html)

    def test_page_contains_dollar_masking_fix_v3(self):
        """Сессия H3: «\\$» маскируется ДО KaTeX приватным символом, иначе
        auto-render разрезает «\\$» по границе доллара и слэш остаётся виден."""
        p = make_problem(
            'Яблоко стоит 4.53\\$, а банан 1.56\\$ за килограмм.')
        resp = self.client.get(
            reverse('catalog:problem_detail', args=[p.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # данные с двумя валютными \\$ дошли до страницы
        self.assertIn('4.53\\$', html)
        self.assertIn('1.56\\$', html)
        # фикс H3: функция маскировки и её вызов до KaTeX
        self.assertIn('function maskEscapedDollars', html)
        self.assertIn('maskEscapedDollars(document.body)', html)
        # маскировка перед перерендером раскрывашки тоже стоит
        self.assertIn('maskEscapedDollars(block)', html)
