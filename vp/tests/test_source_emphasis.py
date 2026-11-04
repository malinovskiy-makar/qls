"""PDF emphasis survives take/result; arbitrary HTML remains inert."""
import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.safestring import SafeString

from vp.formatting import inline_text
from vp.models import VPAttempt
from vp.review import _lead
from vp.tests.helpers import load_demo


class SourceEmphasisTests(SimpleTestCase):
    def test_source_emphasis_and_math(self):
        text = r'<strong>Все <u>неверные</u></strong>: $Q_1 < Q_2$; <em>целое</em>.'
        self.assertEqual(inline_text(text), text.replace('Q_1 <', 'Q_1 &lt;'))

    def test_html_is_inert_even_if_input_is_marked_safe(self):
        text = '<img src=x onerror=alert(1)><u onclick="alert(2)">X</u><script>bad()</script>'
        html = inline_text(SafeString(text))
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('<u', html)
        self.assertIn('&lt;img', html)
        self.assertIn('&quot;', html)

    def test_tags_inside_math_and_encoded_tags_remain_text(self):
        self.assertEqual(inline_text(r'$\text{<u>x</u>}$'),
                         r'$\text{&lt;u&gt;x&lt;/u&gt;}$')
        self.assertEqual(inline_text('&lt;script&gt;'), '&amp;lt;script&amp;gt;')

    def test_unbalanced_or_crossed_tags_are_escaped(self):
        for text in ['<u>text', '<u><em>x</u></em>', '</strong>text']:
            with self.subTest(text=text):
                self.assertNotIn('<', inline_text(text))

    def test_lead_drops_markup_without_truncating_tex(self):
        self.assertEqual(_lead('<u>Цена</u> $P=10$.'), 'Цена $P=10$.')


class SourceEmphasisJourneyTests(TestCase):
    def test_matching_row_and_statement_render_on_take_and_result(self):
        variant = load_demo('9')
        item = variant.items.get(block='matching')
        item.statement = '<strong>Определите</strong> тип <u>выделенного</u> товара.'
        item.options[0]['text'] = 'Приобретение <u>оборудования</u>.'
        item.save()
        self.client.force_login(get_user_model().objects.create_user('vp_emphasis'))
        self.client.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        take = self.client.get(reverse('vp:take', args=[attempt.public_code]))
        self.assertContains(take, '<strong>Определите</strong>')
        self.assertContains(take, '<u>оборудования</u>')
        self.client.post(reverse('vp:save', args=[attempt.public_code]),
                         json.dumps({'answers': [{'item': item.number, 'raw': item.answer}]}),
                         content_type='application/json')
        self.client.post(reverse('vp:finish', args=[attempt.public_code]))
        result = self.client.get(reverse('vp:result', args=[attempt.public_code]))
        self.assertContains(result, '<strong>Определите</strong>')
        self.assertContains(result, '<u>оборудования</u>')
