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
#: Инструкция в шапке — дословно по заданию сессии «Экзамен A2».
VERBATIM_INSTRUCTION = (
    'Задача годится для экзамена, если: 1) условие полное и понятно без '
    'картинки; 2) вы согласны с ответом — решили сами или проверили решение '
    'банка; 3) в ней есть хотя бы одно число, которое можно проверить. Если '
    'в вопросе просят несколько чисел — нажмите «+ ещё число» и подпишите '
    'каждое (P, Q, прибыль). Если пункт просит объяснить, построить график '
    'или вывести формулу — отметьте у него «не проверяется». Число — без '
    'единиц; проценты — числом процентов (25, а не 0,25) и галочка. Ни '
    'одного проверяемого числа — «Не годится». Сомневаетесь — «Пропустить» '
    'и комментарий.'
)


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
        self.assertEqual(INSTRUCTION, VERBATIM_INSTRUCTION)
        self.assertIn(INSTRUCTION, self.html)
        self.assertNotIn('резерв', self.html)
        last = build_page(self.rows, self.records, 4, 4, SEED)
        self.assertIn('резерв', last)
        self.assertTrue(page_data(last)['reserve'])

    def test_proposal_in_data_and_hint_per_kind(self):
        cards = self.html.split('<section class="qx-card"')[1:]
        data = page_data(self.html)['cards']
        hints = {'extracted': 'ключ извлечён программой — проверьте',
                 'none': 'ответа в банке нет — впишите из решения'}
        # 20 — exact: подписи нет; Q = 7 — extracted; 25% — проценты с галочкой.
        self.assertEqual(data[0]['asks'][0]['kind'], 'exact')
        for text in hints.values():
            self.assertNotIn(text, cards[0])
        self.assertEqual(data[1]['asks'][0]['kind'], 'extracted')
        self.assertIn(hints['extracted'], cards[1])
        self.assertEqual(data[1]['asks'][0]['value'], '7')
        self.assertEqual((data[2]['asks'][1]['value'], data[2]['asks'][1]['percent']),
                         ('25', True))

    def test_none_kind_gets_its_own_hint(self):
        record_none = record(104, answer='вырастет')
        topic = {'id': 1, 'name': 'Тема', 'order': 1}
        row = candidate_row(record_none, topic, 1, 4, SEED)
        self.assertEqual(row['asks'][0]['kind'], 'none')
        html = build_page([row], {104: record_none}, 1, 4, SEED)
        self.assertIn('ответа в банке нет — впишите из решения', html)
        self.assertNotIn('ключ извлечён программой', html)

    def test_every_ask_has_skip_and_add_controls(self):
        self.assertEqual(self.html.count('class="qx-ask"'), 4)   # 1 + 1 + 2 вопроса
        self.assertEqual(self.html.count('не проверяется (ответ не число)'), 4)
        self.assertEqual(self.html.count('class="qx-add"'), 4)

    def test_state_key_has_version_suffix(self):
        self.assertIn(
            "'qls-ai-exam-v0-' + DATA.seed + '-chunk' + DATA.chunk + '-f2'", self.html)
        self.assertIn("'ai_exam_review_chunk' + DATA.chunk + '_' + name + '.json'", self.html)

    def test_warnings_cover_missing_number_and_unlabelled_numbers(self):
        self.assertIn('нет числа', self.html)
        self.assertIn('без подписей', self.html)


def value(v, label='', unit='', percent=False, tol=''):
    return {'label': label, 'value': v, 'unit': unit, 'percent': percent, 'tol': tol}


def sample_export():
    """Образец выгрузки страницы — ровно та форма, что собирает payload().

    101 — одно число без подписи; 102 — «не годится»; 103 — подпункт «а» с
    двумя подписанными числами и подпункт «б» с процентами.
    """
    return {
        'format': review.FORMAT, 'seed': SEED, 'chunk': 1, 'reviewer': 'Анна',
        'exported_at': '2026-10-08T10:00:00.000Z',
        'rows': [
            {'id': 101, 'verdict': 'ok', 'reason': '', 'comment': '',
             'asks': [{'part_id': None, 'skip': False, 'values': [value('20')]}]},
            {'id': 102, 'verdict': 'bad', 'reason': 'not_numeric', 'comment': 'формула',
             'asks': [{'part_id': None, 'skip': False, 'values': [value('7')]}]},
            {'id': 103, 'verdict': 'ok', 'reason': '', 'comment': '',
             'asks': [{'part_id': 501, 'skip': False,
                       'values': [value('30', 'P', 'руб.', tol='0,5'),
                                  value('12', 'Q')]},
                      {'part_id': 502, 'skip': False,
                       'values': [value('25', percent=True)]}]},
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

    def test_one_number_without_label_is_fine(self):
        good, complaints = review.validate_review(sample_export(), self.by_id)
        self.assertEqual(complaints, [])
        self.assertEqual(good[0]['asks'][0]['values'][0]['label'], '')

    def test_two_labelled_numbers_in_one_ask_are_fine(self):
        good, complaints = review.validate_review(sample_export(), self.by_id)
        self.assertEqual(complaints, [])
        self.assertEqual(len(good[2]['asks'][0]['values']), 2)

    def test_one_skipped_and_one_filled_ask_are_fine(self):
        def mutate(p):
            p['rows'][2]['asks'][0] = {'part_id': 501, 'skip': True, 'values': []}
        good, complaints = self.broken(mutate)
        self.assertEqual(complaints, [])
        self.assertEqual(len(good), 3)

    def test_two_numbers_plus_skipped_ask_is_fine(self):
        # Ровно то, что отдаёт страница: у «а» два подписанных числа, «б» не проверяется.
        def mutate(p):
            p['rows'][2]['asks'][1] = {'part_id': 502, 'skip': True, 'values': []}
        good, complaints = self.broken(mutate)
        self.assertEqual(complaints, [])
        self.assertEqual([len(a['values']) for a in good[2]['asks']], [2, 0])

    def test_skipped_ask_ignores_leftover_values(self):
        # Страница гасит строки пропущенного вопроса, но не обязана их стирать.
        def mutate(p):
            p['rows'][2]['asks'][0]['skip'] = True
            p['rows'][2]['asks'][0]['values'] = [value('мусор')]
        _good, complaints = self.broken(mutate)
        self.assertEqual(complaints, [])

    def test_each_complaint_kind(self):
        def row(p, i):
            return p['rows'][i]

        def ask(p, i, j=0):
            return p['rows'][i]['asks'][j]

        cases = [
            (review.UNKNOWN_ID, lambda p: row(p, 0).update(id=999)),
            (review.UNKNOWN_VERDICT, lambda p: row(p, 0).update(verdict='maybe')),
            (review.KEY_SHAPE, lambda p: row(p, 2)['asks'].pop()),
            (review.KEY_SHAPE, lambda p: ask(p, 2, 1).update(part_id=777)),
            (review.KEY_VALUE, lambda p: ask(p, 0)['values'][0].update(value='двадцать')),
            (review.KEY_VALUE, lambda p: ask(p, 0)['values'][0].update(value='')),
            (review.BAD_TOL, lambda p: ask(p, 0)['values'][0].update(tol='-1')),
            (review.BAD_TOL, lambda p: ask(p, 0)['values'][0].update(tol='много')),
            (review.NO_REASON, lambda p: row(p, 1).update(reason='')),
            (review.NO_REVIEWER, lambda p: p.update(reviewer='  ')),
            # Новые виды формата 2.
            (review.NO_VALUES, lambda p: ask(p, 0).update(values=[])),
            (review.LABELS, lambda p: ask(p, 2)['values'][1].update(label='')),
            (review.LABELS, lambda p: ask(p, 2)['values'][1].update(label=' p ')),
            (review.ALL_SKIPPED,
             lambda p: [ask(p, 2, 0).update(skip=True), ask(p, 2, 1).update(skip=True)]),
        ]
        for kind, mutate in cases:
            with self.subTest(kind=kind):
                good, complaints = self.broken(mutate)
                self.assertIn(kind, [c['kind'] for c in complaints])
                if kind != review.NO_REVIEWER:
                    # Соседние годные строки не пропадают.
                    self.assertEqual(len(good), 2)

    def test_format_one_is_no_longer_accepted(self):
        payload = sample_export()
        payload['format'] = 'ai_exam_review/1'
        with self.assertRaises(ValueError):
            review.validate_review(payload, self.by_id)

    def test_not_a_review_file_is_an_error(self):
        for payload in (None, [], {'format': 'other/1', 'rows': []},
                        {'format': review.FORMAT}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                review.validate_review(payload, self.by_id)

    def test_skip_and_bad_rows_need_no_asks(self):
        payload = sample_export()
        payload['rows'][1]['asks'] = []
        payload['rows'].append({'id': 103, 'verdict': 'skip', 'reason': '',
                                'comment': 'не уверен', 'asks': []})
        good, complaints = review.validate_review(payload, self.by_id)
        self.assertEqual(complaints, [])
        self.assertEqual(len(good), 4)
