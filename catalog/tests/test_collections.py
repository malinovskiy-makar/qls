"""
Тесты конструктора подборок и экспорта в .tex / PDF.
"""

import json

from django.test import TestCase
from django.urls import reverse

from problems.models import Collection
from problems.tests.factories import make_problem


def make_collection(name='Подборка', template_type=Collection.HOMEWORK):
    return Collection.objects.create(name=name, template_type=template_type)


class CollectionConstructorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.p1 = make_problem('Первая задача подборки.')
        cls.p2 = make_problem('Вторая задача подборки.')
        cls.p_flagged = make_problem('Скрытая задача.', flagged=True)

    def test_create_collection_redirects_to_token_page(self):
        resp = self.client.post(reverse('catalog:collection_new'),
                                {'name': 'Моя КР', 'template_type': 'test'})
        col = Collection.objects.get(name='Моя КР')
        self.assertTrue(col.token)
        self.assertRedirects(
            resp, reverse('catalog:collection_detail', args=[col.token]))

    def test_collection_page_opens(self):
        col = make_collection()
        resp = self.client.get(
            reverse('catalog:collection_detail', args=[col.token]))
        self.assertEqual(resp.status_code, 200)

    def test_add_remove_problem(self):
        col = make_collection()
        url_add = reverse('catalog:collection_add', args=[col.token])
        resp = self.client.post(
            url_add, json.dumps({'problem_id': self.p1.pk}),
            content_type='application/json')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(col.problems.count(), 1)

        url_remove = reverse('catalog:collection_remove', args=[col.token])
        resp = self.client.post(
            url_remove, json.dumps({'problem_id': self.p1.pk}),
            content_type='application/json')
        self.assertEqual(resp.json()['count'], 0)

    def test_reorder(self):
        col = make_collection()
        col.problems.set([self.p1, self.p2])
        col.problem_order = [self.p1.pk, self.p2.pk]
        col.save()
        resp = self.client.post(
            reverse('catalog:collection_reorder', args=[col.token]),
            json.dumps({'order': [self.p2.pk, self.p1.pk]}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        col.refresh_from_db()
        self.assertEqual(col.problem_order, [self.p2.pk, self.p1.pk])

    def test_flagged_problem_hidden_in_collection_panel(self):
        """Зафлагованная задача, попавшая в подборку, не видна на странице."""
        col = make_collection()
        col.problems.set([self.p1, self.p_flagged])
        resp = self.client.get(
            reverse('catalog:collection_detail', args=[col.token]))
        ids = {p.pk for p in resp.context['coll_problems']}
        self.assertEqual(ids, {self.p1.pk})


class CollectionExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.col = make_collection('Экспортная')
        cls.p = make_problem('Задача с формулой $MC=2Q$ и процентом 50%.',
                             answer='42', solution='Решение: подставить.')
        cls.p_flagged = make_problem('Скрытая.', flagged=True)
        cls.col.problems.set([cls.p, cls.p_flagged])
        cls.col.problem_order = [cls.p.pk, cls.p_flagged.pk]
        cls.col.save()

    def setUp(self):
        # С 24.09 ответы и решения в файле — только вошедшему (ADR 0129).
        from problems.tests.factories import make_user
        self.client.force_login(make_user('col_export_reader'))

    def test_export_page_opens(self):
        resp = self.client.get(
            reverse('catalog:collection_export', args=[self.col.token]))
        self.assertEqual(resp.status_code, 200)
        ids = {p.pk for p in resp.context['problems']}
        self.assertNotIn(self.p_flagged.pk, ids)

    def test_tex_download_contains_problem(self):
        resp = self.client.get(
            reverse('catalog:collection_download_tex', args=[self.col.token]),
            {'show_answers': '1', 'show_solutions': '1'})
        self.assertEqual(resp.status_code, 200)
        tex = resp.content.decode('utf-8')
        self.assertIn(r'\documentclass', tex)
        self.assertIn('$MC=2Q$', tex)        # формулы не экранируются
        self.assertIn('42', tex)             # ответ включён
        self.assertNotIn('Скрытая', tex)     # зафлагованная не попала

    def test_generate_latex_no_exception(self):
        from catalog.latex_export import generate_latex
        tex = generate_latex(self.col, show_answers=True, show_solutions=True)
        self.assertIn(r'\begin{document}', tex)

    def test_pdf_download_responds(self):
        """POST на PDF: либо настоящий PDF, либо fallback .tex — без исключений."""
        resp = self.client.post(
            reverse('catalog:collection_download_pdf', args=[self.col.token]),
            {'show_answers': '1'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(len(resp.content) > 0)
        self.assertIn(resp['Content-Type'],
                      ('application/pdf', 'text/plain; charset=utf-8'))


class CollectionBankProtectionTests(TestCase):
    """Подборка — лист для урока, а не выгрузка банка (24.09.2026, ADR 0129)."""

    def setUp(self):
        from django.core.cache import cache

        from catalog import views as catalog_views
        from problems.tests.factories import make_problem, make_user

        cache.clear()
        self.views = catalog_views
        self.make_problem = make_problem
        self.user = make_user('col_exporter')
        self.collection = Collection.objects.create(name='Лист')
        self.visible = make_problem('Видимая задача подборки.', answer='42',
                                    solution='Решение видимой задачи подборки длиннее тридцати.')
        self.collection.problems.add(self.visible)
        self.collection.problem_order = [self.visible.pk]
        self.collection.save()

    def _add(self, problem_id):
        return self.client.post(reverse('catalog:collection_add', args=[self.collection.token]),
                                {'problem_id': problem_id})

    def test_hidden_problem_cannot_be_added(self):
        hidden = self.make_problem('Непроверенная задача.', hidden_pending_review=True)
        self.assertEqual(self._add(hidden.pk).status_code, 404)
        self.assertFalse(self.collection.problems.filter(pk=hidden.pk).exists())

    def test_no_more_than_fifty(self):
        extra = [self.make_problem('Задача %d.' % i) for i in range(self.views.COLLECTION_MAX)]
        statuses = [self._add(p.pk).status_code for p in extra]
        self.assertEqual(statuses.count(200), self.views.COLLECTION_MAX - 1)
        self.assertEqual(statuses[-1], 400)
        self.assertEqual(self.collection.problems.count(), self.views.COLLECTION_MAX)

    def test_answers_export_only_signed_in_and_limited(self):
        tex = reverse('catalog:collection_download_tex', args=[self.collection.token])
        # Условия без ответов — всем, как раньше.
        self.assertEqual(self.client.get(tex).status_code, 200)
        for flags in ({'show_answers': '1'}, {'show_solutions': '1'}):
            self.assertEqual(self.client.get(tex, flags).status_code, 403)
        self.client.force_login(self.user)
        for _ in range(self.views.EXPORTS_WITH_ANSWERS_PER_DAY):
            self.assertEqual(self.client.get(tex, {'show_answers': '1'}).status_code, 200)
        self.assertEqual(self.client.get(tex, {'show_solutions': '1'}).status_code, 429)
        # Без ответов — без счётчика.
        self.assertEqual(self.client.get(tex).status_code, 200)
