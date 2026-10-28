"""Сессия R, фаза 8: тренировка записи ответа `/vp/format/` и пробник.

Проверяет тот же код, что считает баллы (`vp/drill.py` → `vp/scoring.py`). Открыта всем без
входа; проверка — POST с CSRF, мусор и огромное тело — 400, в базу ничего не пишется.
"""
import json

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from vp import drill, scoring

# Что даёт «как в решении», вписанное буквально (решение владельца по таблице промпта).
AS_IN_SOLUTION = ('dot', 'space', 'units', 'minus', 'decimals', 'units', 'decimals', 'units',
                  'ok', 'minus', 'units', 'ok')


class DrillRulesTests(SimpleTestCase):
    def test_right_records_pass_and_literal_ones_are_traps(self):
        self.assertEqual(len(drill.DRILL), 12)
        for i, (shown, _, right) in enumerate(drill.DRILL, start=1):
            with self.subTest(i=i):
                self.assertTrue(scoring.NUMBER_FORMAT.fullmatch(right))
                self.assertTrue(drill.check(i, right)['ok'])
                self.assertEqual(drill.check(i, shown)['reason'], AS_IN_SOLUTION[i - 1])
        self.assertEqual(sum(1 for r in AS_IN_SOLUTION if r != 'ok'), 10)

    def test_texts(self):
        self.assertEqual(drill.check(6, '0,66')['text'], 'Запись верная, но число другое. Верно: «0,67».')
        self.assertEqual(drill.check(9, '37,50')['text'],
                         'Засчитают: лишний ноль после запятой не мешает.')
        self.assertEqual(drill.check(1, '37,5')['text'], 'Засчитают.')
        self.assertEqual(drill.check(1, '37.5')['text'], 'Точка вместо запятой. Верно: «37,5».')
        self.assertEqual(drill.check(4, '−0,12')['text'],
                         'Длинный минус «−». Наберите «-» с клавиатуры: «-0,12».')

    def test_probe(self):
        found = drill.probe('37.5')
        self.assertEqual((found['reason'], found['fix']), ('dot', '37,5'))
        self.assertEqual(found['text'], '0 баллов: точка вместо запятой. Нужно «37,5».')
        self.assertTrue(drill.probe('37,50')['ok'])
        self.assertEqual(drill.probe('')['reason'], 'empty')
        self.assertIn('длинный минус', drill.probe('−5')['text'])


class DrillPageTests(TestCase):
    def test_page_is_open_to_a_guest(self):
        response = Client().get(reverse('vp:drill'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Тренировка записи ответа', html)
        self.assertEqual(html.count('name="raw-'), 12)
        self.assertIn('Проверить все', html)

    def test_form_without_js_draws_the_same_verdicts(self):
        response = Client().post(reverse('vp:drill'), {'raw-1': '37.5', 'raw-9': '37,50'})
        html = response.content.decode()
        self.assertIn('Точка вместо запятой. Верно: «37,5».', html)
        self.assertIn('Засчитают: лишний ноль после запятой не мешает.', html)

    def post(self, client, body, raw=False):
        return client.post(reverse('vp:format_check'), body if raw else json.dumps(body),
                           content_type='application/json')

    def test_check_endpoint(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client, {'i': 3, 'raw': '20'}).status_code, 403)
        client.get(reverse('vp:drill'))
        token = client.cookies['csrftoken'].value
        ok = client.post(reverse('vp:format_check'), json.dumps({'i': 3, 'raw': '20'}),
                         content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()['ok'])
        plain = Client()
        self.assertEqual(self.post(plain, {'raw': '37.5'}).json()['fix'], '37,5')
        self.assertEqual(self.post(plain, 'не json', raw=True).status_code, 400)
        self.assertEqual(self.post(plain, {'i': 13, 'raw': '1'}).status_code, 400)
        self.assertEqual(self.post(plain, {'i': True, 'raw': '1'}).status_code, 400)
        self.assertEqual(self.post(plain, {'raw': 5}).status_code, 400)
        self.assertEqual(self.post(plain, {'raw': '1' * 5000}).status_code, 400)
