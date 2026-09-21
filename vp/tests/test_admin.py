from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from vp.models import VPItem
from vp.tests.helpers import make_full_variant


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username='root', password='x', email='r@example.com')
        cls.variant = make_full_variant()

    def setUp(self):
        self.client.force_login(self.user)

    def get(self, name, **params):
        return self.client.get(reverse(name), params)

    def test_variant_list_shows_item_count(self):
        response = self.get('admin:vp_vpvariant_changelist')
        self.assertContains(response, self.variant.slug)
        self.assertContains(response, '44')

    def test_item_search_by_number_and_text(self):
        url = 'admin:vp_vpitem_changelist'
        self.assertEqual(self.get(url, q='17').context['cl'].result_count, 1)
        self.assertEqual(self.get(url, q='"Задание 4"').context['cl'].result_count, 6)
        # Нечисловой запрос не должен ронять поиск по номеру.
        self.assertEqual(self.get(url, q='несуществующее').status_code, 200)

    def test_item_filters_by_block(self):
        response = self.get('admin:vp_vpitem_changelist', block='snake')
        self.assertEqual(response.context['cl'].result_count, 30)

    def test_saving_answer_recomputes_chain_letters(self):
        item = VPItem.objects.get(variant=self.variant, number=1)
        data = {
            'variant': self.variant.pk, 'number': 1, 'block': 'snake',
            'kind': 'short_text', 'intro': '', 'statement': 'Задание 1',
            'prefix': '', 'suffix': '', 'options': '[]', 'correct': '[]',
            'answer': 'Ёмкость рынка', 'accepted': '[]', 'points': '2.00',
            'wrong_penalty': '0.00', 'figure': '', 'figure_caption': '',
            'figure_source': '', 'table_html': '', 'solution': '',
        }
        response = self.client.post(
            reverse('admin:vp_vpitem_change', args=[item.pk]), data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual((item.chain_first, item.chain_second), ('е', 'м'))

    def test_variant_page_warns_when_points_sum_differs_from_max_score(self):
        self.variant.max_score = D('98.00')   # сумма заданий 100,00
        self.variant.save()
        response = self.client.get(
            reverse('admin:vp_vpvariant_change', args=[self.variant.pk]))
        self.assertContains(
            response, 'Сумма баллов заданий 100,00 ≠ max_score 98,00; пересчитывается импортом.')
        self.assertContains(response, 'class="warning"')

    def test_variant_page_is_quiet_when_sums_agree(self):
        response = self.client.get(
            reverse('admin:vp_vpvariant_change', args=[self.variant.pk]))
        self.assertNotContains(response, 'пересчитывается импортом')
        self.assertNotContains(response, 'class="warning"')

    def test_warning_does_not_recompute_max_score(self):
        self.variant.max_score = D('98.00')
        self.variant.save()
        self.client.get(reverse('admin:vp_vpvariant_change', args=[self.variant.pk]))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.max_score, D('98.00'))

    def test_add_page_has_no_warning(self):
        response = self.client.get(reverse('admin:vp_vpvariant_add'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'пересчитывается импортом')
