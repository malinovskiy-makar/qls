"""Экзамен для ИИ: страница проверки и формат разметки ai_exam_review/1.

Банк выдуманный: записи — словари, к базе тесты не обращаются.
"""
import json
import re

from django.test import SimpleTestCase

from problems.ai_exam import review
from problems.ai_exam.page import INSTRUCTION, build_page
from problems.ai_exam.sampling import candidate_row, prepare

SEED = 20261007
#: Метки, которых на слепой странице быть не должно ни в каком виде.
OPINION_MARK = 'ОТВЕТ-МОДЕЛИ-31337'


def record(pk, answer='20', parts=()):
    return prepare([{
        'id': pk, 'title': '', 'answer': answer,
        'statement': 'Спрос $Q = 100 - 2P$, издержки $TC = 10Q$. Найдите выпуск.',
        'solution': 'Решение: $MR = MC$, откуда $Q = 45$.',
        'problem_type': 'задача с развёрнутым ответом', 'difficulty': 3,
        'task_nature': 'расчётная', 'answer_consistency': 'согласован',
        'text_quality': 'чистая', 'solution_needs_review': False,
        'multiple_problems': False, 'dup_group': '', 'dup_is_best': False,
        'parts': [dict(p) for p in parts], 'topics': [1], 'source': 'Источник',
        'source_id': 1,
        # Второе мнение в записи ЕСТЬ — на страницу оно попасть не должно.
        'opinion': {'agrees': False, 'resolved': False, 'resolution': 'model_right',
                    'model_answer': OPINION_MARK},
    }])[0]


def bank():
    records = [
        record(101),
        record(102, answer='Q = 7'),
        record(103, answer='', parts=[
            {'id': 501, 'label': 'а', 'statement': 'Найдите $P$.', 'answer': '30'},
            {'id': 502, 'label': 'б', 'statement': 'Найдите выручку.', 'answer': '25%'},
        ]),
    ]
    topic = {'id': 1, 'name': 'Монополия и ценовая дискриминация', 'order': 1}
    rows = [candidate_row(r, topic, 1, i + 1, SEED) for i, r in enumerate(records)]
    return rows, {r['id']: r for r in records}


def page_data(html):
    match = re.search(r'<script type="application/json" id="qx-data">(.*?)</script>',
                      html, re.S)
    return json.loads(match.group(1))


class PageTests(SimpleTestCase):
    def setUp(self):
        self.rows, self.records = bank()
        self.html = build_page(self.rows, self.records, 1, 4, SEED)

    def test_one_card_per_candidate(self):
        self.assertEqual(self.html.count('<section class="qx-card"'), len(self.rows))
        for row in self.rows:
            self.assertIn('https://weconomics.ai/catalog/problem/%d/' % row['id'], self.html)

    def test_page_is_blind(self):
        lowered = self.html.lower()
        for mark in ('answer_consistency', 'human_review', 'second_opinion',
                     'answersecondopinion', 'второе мнение', 'мнение модели',
                     'model_right', 'согласован', OPINION_MARK.lower()):
            with self.subTest(mark=mark):
                self.assertNotIn(mark, lowered)

    def test_no_external_resources(self):
        self.assertIsNone(re.search(r'<link\b', self.html, re.I))
        self.assertIsNone(re.search(r'<script[^>]*\ssrc\s*=', self.html, re.I))
        self.assertIsNone(re.search(r'\s(?:src|href)\s*=\s*["\']?(?:https?:)?//',
                                    self.html, re.I))
        self.assertIsNone(re.search(r'@import', self.html))

    def test_katex_is_embedded(self):
        self.assertIn('renderMathInElement', self.html)
        self.assertIn('.katex', self.html)
        self.assertIn('data:font/woff2;base64,', self.html)

    def test_data_is_valid_json(self):
        data = page_data(self.html)
        self.assertEqual(data['format'], review.FORMAT)
        self.assertEqual((data['seed'], data['chunk'], data['reserve']), (SEED, 1, False))
        self.assertEqual([c['id'] for c in data['cards']], [101, 102, 103])
        self.assertEqual([a['part_id'] for a in data['cards'][2]['asks']], [501, 502])

    def test_instruction_verbatim_and_reserve_word(self):
        self.assertIn(INSTRUCTION, self.html)
        self.assertNotIn('резерв', self.html)
        last = build_page(self.rows, self.records, 4, 4, SEED)
        self.assertIn('резерв', last)
        self.assertTrue(page_data(last)['reserve'])

    def test_key_prefilled_and_doubtful_key_flagged(self):
        cards = self.html.split('<section class="qx-card"')[1:]
        hint = 'ключ извлечён программой — проверьте'
        self.assertNotIn(hint, cards[0])          # 20 — exact
        self.assertIn(hint, cards[1])             # Q = 7 — extracted
        self.assertIn('value="7"', cards[1])
        self.assertIn('value="25"', cards[2])     # 25% — число процентов
        self.assertIn('checked', cards[2])        # и галочка «это проценты»

    def test_state_key_holds_seed_and_chunk(self):
        self.assertIn("'qls-ai-exam-v0-' + DATA.seed + '-chunk' + DATA.chunk", self.html)
        self.assertIn("'ai_exam_review_chunk' + DATA.chunk + '_' + name + '.json'", self.html)


def sample_export():
    """Образец выгрузки страницы — ровно та форма, что собирает payload()."""
    return {
        'format': review.FORMAT, 'seed': SEED, 'chunk': 1, 'reviewer': 'Анна',
        'exported_at': '2026-10-08T10:00:00.000Z',
        'rows': [
            {'id': 101, 'verdict': 'ok', 'reason': '', 'comment': '',
             'key': [{'part_id': None, 'value': '20', 'unit': '', 'percent': False,
                      'tol': ''}]},
            {'id': 102, 'verdict': 'bad', 'reason': 'not_numeric', 'comment': 'формула',
             'key': [{'part_id': None, 'value': '7', 'unit': '', 'percent': False,
                      'tol': ''}]},
            {'id': 103, 'verdict': 'ok', 'reason': '', 'comment': '',
             'key': [{'part_id': 501, 'value': '30', 'unit': 'руб.', 'percent': False,
                      'tol': '0,5'},
                     {'part_id': 502, 'value': '25', 'unit': '', 'percent': True,
                      'tol': ''}]},
        ],
    }


class ValidateReviewTests(SimpleTestCase):
    def setUp(self):
        rows, _records = bank()
        self.by_id = {r['id']: r for r in rows}

    def test_sample_export_passes(self):
        good, complaints = review.validate_review(sample_export(), self.by_id)
        self.assertEqual(complaints, [])
        self.assertEqual([r['id'] for r in good], [101, 102, 103])

    def broken(self, mutate):
        payload = sample_export()
        mutate(payload)
        return review.validate_review(payload, self.by_id)

    def test_each_complaint_kind(self):
        def row(p, i):
            return p['rows'][i]

        cases = [
            (review.UNKNOWN_ID, lambda p: row(p, 0).update(id=999)),
            (review.UNKNOWN_VERDICT, lambda p: row(p, 0).update(verdict='maybe')),
            (review.KEY_SHAPE, lambda p: row(p, 2)['key'].pop()),
            (review.KEY_SHAPE, lambda p: row(p, 2)['key'][1].update(part_id=777)),
            (review.KEY_VALUE, lambda p: row(p, 0)['key'][0].update(value='двадцать')),
            (review.KEY_VALUE, lambda p: row(p, 0)['key'][0].update(value='')),
            (review.BAD_TOL, lambda p: row(p, 0)['key'][0].update(tol='-1')),
            (review.BAD_TOL, lambda p: row(p, 0)['key'][0].update(tol='много')),
            (review.NO_REASON, lambda p: row(p, 1).update(reason='')),
            (review.NO_REVIEWER, lambda p: p.update(reviewer='  ')),
        ]
        for kind, mutate in cases:
            with self.subTest(kind=kind):
                good, complaints = self.broken(mutate)
                self.assertIn(kind, [c['kind'] for c in complaints])
                if kind != review.NO_REVIEWER:
                    # Соседние годные строки не пропадают.
                    self.assertEqual(len(good), 2)

    def test_not_a_review_file_is_an_error(self):
        for payload in (None, [], {'format': 'other/1', 'rows': []},
                        {'format': review.FORMAT}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                review.validate_review(payload, self.by_id)

    def test_skip_and_bad_rows_need_no_key(self):
        payload = sample_export()
        payload['rows'][1]['key'] = []
        payload['rows'].append({'id': 103, 'verdict': 'skip', 'reason': '',
                                'comment': 'не уверен', 'key': []})
        good, complaints = review.validate_review(payload, self.by_id)
        self.assertEqual(complaints, [])
        self.assertEqual(len(good), 4)
