"""Сессия R, фаза 5: данные страницы результата и «Показать ответ».

Потери на записи (`review.format_losses`), статусы строк и счётчики фильтров, свои
попытки и место — только владельцу. Эталон и решение неотвеченного в HTML не попадают:
их отдаёт `practice_check` — проверкой или «Показать ответ» — и ничего не пишет.
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp import review
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import answer_all, load_demo, make_full_variant

User = get_user_model()

ANSWERS = {5: '25000', 9: '98.0', 11: '-0.12', 13: '11 800', 14: '160 ед', 17: '1,607'}


def card(html, number):
    """Строка разбора задания: и старая разметка `vp-r-N`, и новая `zN` (фаза 6)."""
    for marker in (f'id="z{number}"', f'id="vp-r-{number}"'):
        if marker in html:
            rest = html.split(marker, 1)[1]
            # До начала следующей строки разбора, какой бы разметкой она ни была.
            ends = [rest.find(m) for m in ('id="z', 'id="vp-r-', '</article>') if m in rest]
            return rest[:min(ends)] if ends else rest
    raise AssertionError(f'нет строки задания {number}')


class ResultDataTests(TestCase):
    def setUp(self):
        self.variant = load_demo('10')
        self.owner = Client()
        self.owner.force_login(User.objects.create_user('vp_rr', password='p12345'))
        self.owner.post(reverse('vp:start', args=[self.variant.slug]))
        self.attempt = VPAttempt.objects.get(variant=self.variant)
        self.owner.post(reverse('vp:save', args=[self.attempt.public_code]),
                        json.dumps({'answers': [{'item': n, 'raw': raw}
                                                for n, raw in ANSWERS.items()]}),
                        content_type='application/json')
        self.owner.post(reverse('vp:finish', args=[self.attempt.public_code]))
        self.attempt.refresh_from_db()
        self.url = reverse('vp:result', args=[self.attempt.public_code])
        self.practice = reverse('vp:practice', args=[self.attempt.public_code])

    def test_format_losses_and_counters(self):
        self.assertEqual(self.attempt.score, Decimal('5.00'))
        losses = review.format_losses(self.attempt)
        self.assertEqual(losses['points'], Decimal('25'))
        self.assertEqual([(i['number'], i['given'], i['fix']) for i in losses['items']],
                         [(9, '98.0', '98,0'), (11, '-0.12', '-0,12'), (13, '11 800', '11800'),
                          (14, '160 ед', '160'), (17, '1,607', '1,61')])
        self.assertEqual(losses['with_fix'], Decimal('30'))
        self.assertEqual(losses['number_lost'], Decimal('65'))
        counts = {f['code']: f['count']
                  for f in self.owner.get(self.url).context['status_filters']}
        self.assertEqual(counts, {'all': 18, 'errors': 0, 'fmt': 5, 'none': 12, 'ok': 1})

    def test_wrong_number_in_wrong_format_is_not_a_format_loss(self):
        other = Client()
        other.force_login(User.objects.create_user('vp_rr3', password='p12345'))
        variant = load_demo('11')
        other.post(reverse('vp:start', args=[variant.slug]))
        attempt = VPAttempt.objects.get(variant=variant)
        other.post(reverse('vp:save', args=[attempt.public_code]),
                   json.dumps({'answers': [{'item': 5, 'raw': '-999 999.5'}]}),
                   content_type='application/json')
        other.post(reverse('vp:finish', args=[attempt.public_code]))
        attempt.refresh_from_db()
        self.assertEqual(review.format_losses(attempt)['points'], Decimal('0'))
        self.assertEqual(review.format_losses(attempt)['items'], [])
        row = next(r for r in review.tests_review(attempt) if r['number'] == 5)
        self.assertEqual(row['status'], 'bad')

    def test_rows_texts(self):
        rows = {r['number']: r for r in self.owner.get(self.url).context['tests']}
        self.assertEqual((rows[9]['status'], rows[9]['given_text'], rows[9]['right_text']),
                         ('fmt', '98.0', '98'))
        self.assertEqual((rows[16]['status'], rows[16]['given_text'], rows[16]['right_text']),
                         ('none', '–', ''))
        self.assertEqual(rows[5]['status'], 'ok')
        # Эталона и решения неотвеченного нет уже в данных, а не только в шаблоне.
        self.assertEqual((rows[16]['solution'], rows[16]['right']), ('', ''))
        self.assertFalse(any(o['right'] for o in rows[1]['options']))     # тест 1 пуст
        self.assertNotIn('[[', rows[3]['lead'])
        self.assertEqual(rows[18]['shared']['number'], 17)
        self.assertNotIn('shared', rows[17])

    def test_blank_item_has_no_solution_and_no_right_answer_in_html(self):
        html = self.owner.get(self.url).content.decode()
        self.assertNotIn('1000 = 2 · 1000 / P', html)
        self.assertNotIn('Верный ответ', card(html, 16))

    def snapshot(self):
        return list(VPAnswer.objects.order_by('pk').values_list('pk', 'raw', 'score', 'updated_at'))

    def test_reveal_gives_answer_and_solution_and_writes_nothing(self):
        before = self.snapshot()
        response = self.owner.post(self.practice, json.dumps({'item': 16, 'reveal': True}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['right'], '2')
        self.assertIn('1000 = 2 · 1000 / P', response.json()['solution'])
        self.assertEqual(self.snapshot(), before)

    def test_reveal_is_for_the_owner_of_a_submitted_attempt_only(self):
        stranger = Client()
        stranger.force_login(User.objects.create_user('vp_rr2', password='p12345'))
        body = json.dumps({'item': 16, 'reveal': True})
        self.assertEqual(stranger.post(self.practice, body,
                                       content_type='application/json').status_code, 404)
        other = load_demo('11')
        stranger.post(reverse('vp:start', args=[other.slug]))
        open_attempt = VPAttempt.objects.get(variant=other)
        url = reverse('vp:practice', args=[open_attempt.public_code])
        self.assertEqual(stranger.post(url, body, content_type='application/json').status_code, 404)

    def test_owner_side_column_data(self):
        context = self.owner.get(self.url).context
        self.assertEqual([a['is_this'] for a in context['own_attempts']], [True])
        self.assertEqual(context['place'], 1)
        self.assertEqual(context['board_url'], reverse('vp:index') + '?board=10')
        self.assertEqual(context['invite_url'], '')


class ChainDefinitionsTests(TestCase):
    def test_answered_word_has_its_definition(self):
        variant = make_full_variant('vp-chain-def')
        attempt = answer_all(variant)
        rows = review.chain_review(attempt)
        self.assertTrue(rows and all(not r['blank'] for r in rows))
        self.assertTrue(all(r['statement'] for r in rows))
