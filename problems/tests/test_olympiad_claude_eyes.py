# -*- coding: utf-8 -*-
"""Аудит «глазами Claude» (problems/olympiad_audit/claude_eyes.py) на выдуманных
страницах: разбор ответа, отказ при чужом числе, вырезка по рамке, единицы,
слой правок, хвосты v6, сведение моделей. Модель не вызывается, база не нужна."""
import json
import os
import shutil
import tempfile
import unittest

from django.test import SimpleTestCase

from problems.olympiad_audit import claude_eyes as ce


def no_katex(segments):
    return [None] * len(segments)


def make_unit(fields=None, editable=True, group='statement'):
    fields = fields or {'title': '', 'statement_md': 'Цена товара 120 рублей, спрос Q = 40 - P.',
                        'parts': [], 'figures': 0}
    return {'unit': 'vp_abc_p1', 'set': 'vp', 'pages': ['f.pdf#p1'],
            'fragments': [{'fid': 'ev|1|#' + group, 'group': group, 'editable': editable,
                           'own_pages': [1], 'fields': fields,
                           'task': {'event_id': 'ev', 'number': '1', 'task_variant': ''}}]}


def reply(fixes, defects=None, confidence=0.9, fid='ev|1|#statement'):
    return {'tasks': [{'fid': fid, 'verdict': 'needs_fix', 'defects': defects or [
        {'class': 'missing_text', 'what': 'пропуск', 'evidence': ''}],
        'fixes': fixes, 'confidence': confidence}], 'unlisted': []}


class ParseReplyTests(SimpleTestCase):
    def test_fenced_json(self):
        data = ce.parse_reply('```json\n{"tasks": [{"fid": "a"}], "unlisted": []}\n```')
        self.assertEqual(data['tasks'][0]['fid'], 'a')
        self.assertNotIn('_parse_error', data)

    def test_text_around_json(self):
        data = ce.parse_reply('Вот ответ: {"tasks": []} спасибо')
        self.assertEqual(data['tasks'], [])
        self.assertNotIn('_parse_error', data)

    def test_garbage_and_wrong_shape(self):
        self.assertIn('_parse_error', ce.parse_reply('не json'))
        self.assertIn('_parse_error', ce.parse_reply('{"blocks": []}'))
        self.assertIn('_parse_error', ce.parse_reply(None))

    def test_parse_error_rejects_unit(self):
        acc, rej, _ = ce.check_unit(make_unit(), ce.parse_reply('мусор'), [''], katex=no_katex)
        self.assertEqual(acc, [])
        self.assertIn('не разобран', rej[0][1])


class NumbersTests(SimpleTestCase):
    def test_thousands_and_decimal(self):
        self.assertEqual(ce.numbers('выручка 1 000 000 руб.'), {'1000000'})
        self.assertEqual(ce.numbers('$1\\,500$'), {'1500'})
        self.assertEqual(ce.numbers('$0{,}5$ и 0,5'), {'0', '5'})


class CheckUnitTests(SimpleTestCase):
    page = 'Цена товара 120 рублей, спрос Q = 40 - P. Таблица: 2019 год 350 тыс.'

    def test_alien_number_rejected(self):
        new = 'Цена товара 120 рублей, спрос Q = 40 - P. Доход 777 рублей.'
        acc, rej, _ = ce.check_unit(make_unit(), reply({'statement_md': new}), [self.page],
                                    katex=no_katex)
        self.assertEqual(acc, [])
        self.assertTrue(any('чужие числа: 777' in r for r in rej[0].reasons))

    def test_number_from_page_layer_accepted(self):
        new = 'Цена товара 120 рублей, спрос Q = 40 - P.\n\n| год | объём |\n|---|---|\n| 2019 | 350 |'
        acc, rej, _ = ce.check_unit(make_unit(), reply({'statement_md': new}), [self.page],
                                    katex=no_katex)
        self.assertEqual(len(acc), 1, rej)
        self.assertEqual(acc[0].field, 'statement_md')

    def test_number_from_evidence_accepted_on_scan(self):
        new = 'Цена товара 120 рублей, спрос Q = 40 - P. Издержки 65.'
        rep = reply({'statement_md': new}, defects=[{'class': 'missing_text', 'what': 'x',
                                                     'evidence': 'Издержки 65.'}])
        acc, rej, _ = ce.check_unit(make_unit(), rep, [''], katex=no_katex)
        self.assertEqual(len(acc), 1, rej)

    def test_not_editable_low_confidence_answer_and_shrink(self):
        long_old = 'Цена товара 120 рублей. ' * 10
        unit = make_unit({'title': '', 'statement_md': long_old, 'parts': [], 'figures': 0},
                         editable=False)
        rep = reply({'statement_md': 'Цена 120. Ответ: 120'}, confidence=0.3)
        _, rej, _ = ce.check_unit(unit, rep, [long_old], katex=no_katex)
        reasons = ' | '.join(rej[0].reasons)
        for part in ('editable=false', 'уверенность', '«Ответ:»', 'урезано'):
            self.assertIn(part, reasons)

    def test_foreign_field_and_fid(self):
        rep = reply({'solution_md': 'Цена 120'})
        rep['tasks'].append({'fid': 'чужой', 'fixes': {}})
        _, rej, _ = ce.check_unit(make_unit(), rep, [self.page], katex=no_katex)
        self.assertTrue(any('не из группы' in ' '.join(r.reasons) for r in rej if hasattr(r, 'reasons')))
        self.assertTrue(any(r == ('чужой', 'чужой fid') for r in rej if isinstance(r, tuple)))

    def test_katex_error_rejected(self):
        new = 'Цена товара 120 рублей, спрос $Q = 40 - P$.'
        acc, rej, _ = ce.check_unit(make_unit(), reply({'statement_md': new}), [self.page],
                                    katex=lambda segs: ['KaTeX parse error'] * len(segs))
        self.assertEqual(acc, [])
        self.assertIn('KaTeX', ' '.join(rej[0].reasons))

    def test_parts_shape(self):
        rep = reply({'parts': [{'label': 'а', 'text': 'Найдите Q при цене 120.'}]})
        acc, rej, _ = ce.check_unit(make_unit(), rep, [self.page], katex=no_katex)
        self.assertEqual(len(acc), 1, rej)
        rep = reply({'parts': 'а) текст'})
        _, rej, _ = ce.check_unit(make_unit(), rep, [self.page], katex=no_katex)
        self.assertIn('parts не список', ' '.join(rej[0].reasons))


@unittest.skipUnless(shutil.which('node'), 'нужен node')
class KatexTests(SimpleTestCase):
    def test_real_katex(self):
        errors = ce.katex_errors([('x^2 + \\frac{1}{2}', False), ('\\frac{1}{', False),
                                  ('\\tesxt{цена}', False)])
        self.assertIsNone(errors[0])
        self.assertIsNotNone(errors[1])
        self.assertIsNotNone(errors[2])


class CropTests(SimpleTestCase):
    def setUp(self):
        from PIL import Image, ImageDraw
        self.tmp = tempfile.mkdtemp()
        self.png = os.path.join(self.tmp, 'p1.png')
        image = Image.new('RGB', (1000, 2000), 'white')
        ImageDraw.Draw(image).rectangle((200, 400, 599, 799), fill='black')
        image.save(self.png)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_crop_by_normalized_bbox(self):
        from PIL import Image
        out = os.path.join(self.tmp, 'fig', 'c1.png')
        size = ce.crop_figure(self.png, [0.2, 0.2, 0.6, 0.4], out, margin=0)
        self.assertEqual(size, (400, 400))
        with Image.open(out) as image:
            self.assertEqual(image.getpixel((200, 200)), (0, 0, 0))
            self.assertEqual(image.size, (400, 400))

    def test_margin_clamped_to_page(self):
        size = ce.crop_figure(self.png, [0.0, 0.0, 0.5, 0.5], os.path.join(self.tmp, 'c2.png'),
                              margin=0.05)
        self.assertEqual(size, (550, 1100))

    def test_bad_bbox(self):
        for bbox in ([0.5, 0.2, 0.4, 0.4], [0, 0, 1, 1], [0.1, 0.1, 0.11, 0.11], 'x', [1, 2]):
            self.assertIsNone(ce.crop_figure(self.png, bbox, os.path.join(self.tmp, 'c3.png')))

    def test_contact_sheet(self):
        out = ce.contact_sheet([self.png, self.png], os.path.join(self.tmp, 'sheet.png'))
        self.assertTrue(os.path.exists(out))


def fake_ds(rows, pages=('f.pdf#p1', 'f.pdf#p2', 'f.pdf#p3', 'f.pdf#p4', 'f.pdf#p5')):
    manifest = {ref: {'file': 'f.pdf', 'page': int(ref.rsplit('#p', 1)[1]),
                      'page_dir': 'pages/0123456789abcdef', 'png': 'x.png'} for ref in pages}
    return ce.DataSet('vp', '/nowhere', rows, manifest, 'v6', 'v7')


def row(number, src=(), sol=(), crit=(), **kw):
    base = {'event_id': 'ev', 'number': number, 'task_variant': '', 'title': '',
            'statement_md': 'Условие %s' % number, 'parts': [], 'figures': [], 'solution_figures': [],
            'solution_md': '', 'answer': '', 'criteria_md': '', 'source_pages': list(src),
            'solution_pages': list(sol), 'criteria_pages': list(crit)}
    base.update(kw)
    return base


class UnitsTests(SimpleTestCase):
    def test_group_lives_on_first_page(self):
        ds = fake_ds([row('1', src=['f.pdf#p1', 'f.pdf#p2']), row('2', src=['f.pdf#p2'],
                                                                   sol=['f.pdf#p5'])])
        units, skipped = ce.build_units(ds)
        self.assertEqual(skipped, [])
        self.assertEqual(units['vp_0123456789abcdef_p1']['pages'], ['f.pdf#p1', 'f.pdf#p2'])
        self.assertEqual([f['fid'] for f in units['vp_0123456789abcdef_p2']['fragments']],
                         ['ev|2|#statement'])
        self.assertEqual(units['vp_0123456789abcdef_p5']['fragments'][0]['group'], 'solution')

    def test_too_long_group_not_editable(self):
        ds = fake_ds([row('1', sol=['f.pdf#p1', 'f.pdf#p2', 'f.pdf#p3', 'f.pdf#p4', 'f.pdf#p5'])])
        units, _ = ce.build_units(ds, max_pages=4)
        frag = units['vp_0123456789abcdef_p1']['fragments'][0]
        self.assertFalse(frag['editable'])
        self.assertEqual(len(units['vp_0123456789abcdef_p1']['pages']), 4)

    def test_unknown_page_skipped(self):
        ds = fake_ds([row('1', src=['other.pdf#p1'])])
        units, skipped = ce.build_units(ds)
        self.assertEqual(units, {})
        self.assertEqual(skipped[0][1], 'statement')

    def test_prompt_lists_pages_and_fragments(self):
        ds = fake_ds([row('1', src=['f.pdf#p1'])])
        units, _ = ce.build_units(ds)
        text = ce.unit_prompt(units['vp_0123456789abcdef_p1'])
        self.assertIn('Страница 1: f.pdf, стр. 1', text)
        self.assertIn('"fid": "ev|1|#statement"', text)


class LayerTests(SimpleTestCase):
    def test_apply_only_if_field_unchanged(self):
        rows = [row('1', statement_md='старое')]
        good = {'key': 'ev|1|', 'field': 'statement_md', 'value': 'новое', 'old_sha1': ce._sha('старое')}
        stale = dict(good, field='title', old_sha1=ce._sha('было'))
        out, log = ce.apply_layer(rows, [good, stale])
        self.assertEqual(out[0]['statement_md'], 'новое')
        self.assertEqual(rows[0]['statement_md'], 'старое')     # вход не тронут
        self.assertEqual([x[2] for x in log], ['applied', 'поле изменилось после аудита'])

    def test_figure_entry_appended(self):
        out, log = ce.apply_layer([row('1')], [{'key': 'ev|1|', 'field': 'figure', 'target': 'figures',
                                                'value': {'path': 'v7/figures_v7/a.png'}}])
        self.assertEqual(out[0]['figures'], [{'path': 'v7/figures_v7/a.png'}])


class ResolveTests(SimpleTestCase):
    def rec(self, model, verdict='needs_fix', accepted=True):
        return {'unit': 'u1', 'model': model, 'parse_error': '',
                'verdicts': {'ev|1|#statement': {'verdict': verdict, 'defects': [], 'confidence': 0.9}},
                'accepted': ([{'fid': 'ev|1|#statement', 'field': 'statement_md', 'value': model,
                               'old_sha1': 'x'}] if accepted else []),
                'rejected': [], 'figures': [], 'unlisted': []}

    def test_haiku_alone_is_not_applied(self):
        res = ce.resolve({'claude-haiku-5-5': [self.rec('claude-haiku-5-5')]})
        self.assertEqual(res['fixes'], {})
        self.assertIn('нет второго мнения', res['rejected']['ev|1|#statement'][0]['reasons'][0])

    def test_sonnet_overrides_haiku(self):
        res = ce.resolve({'claude-haiku-5-5': [self.rec('claude-haiku-5-5')],
                          'claude-sonnet-5-5': [self.rec('claude-sonnet-5-5', verdict='ok', accepted=False)]})
        self.assertEqual(res['fixes'], {})
        self.assertEqual(res['final']['ev|1|#statement']['verdict'], 'ok')
        res = ce.resolve({'claude-haiku-5-5': [self.rec('claude-haiku-5-5')],
                          'claude-sonnet-5-5': [self.rec('claude-sonnet-5-5')]})
        self.assertEqual(res['fixes']['ev|1|#statement'][0]['value'], 'claude-sonnet-5-5')


class TailRulesTests(SimpleTestCase):
    def test_title_question_into_statement(self):
        r = row('тест-7', year=2012, title='Эластичность спроса выше:',
                statement_md='**Тест 1.**\n\n1. вариант а;\n2. вариант б.')
        out, log, removed = ce.tail_rules_econ([r], 'mosh')
        self.assertEqual(out[0]['title'], '')
        self.assertEqual(out[0]['statement_md'],
                         '**Тест 1.**\n\nЭластичность спроса выше:\n\n1. вариант а;\n2. вариант б.')
        self.assertEqual(removed, {})
        # ВП и другие годы правило не трогает
        self.assertEqual(ce.tail_rules_econ([r], 'vp')[0][0]['title'], 'Эластичность спроса выше:')
        self.assertEqual(ce.tail_rules_econ([dict(r, year=2015)], 'mosh')[0][0]['title'],
                         'Эластичность спроса выше:')

    def test_task10_into_task3(self):
        t3 = row('3', event_id='mosh-2011-final-10-v1', statement_md='...\n5. Определите долю рынка. (10 баллов)',
                 solution_md='чужое решение')
        t10 = row('10', event_id='mosh-2011-final-10-v1', statement_md='Определите долю рынка.',
                  solution_md='Решение задачи 3', solution_pages=['f.pdf#p8'])
        out, log, removed = ce.tail_rules_econ([t3, t10], 'mosh')
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['solution_md'], 'Решение задачи 3')
        self.assertEqual(out[0]['solution_md_v6'], 'чужое решение')
        self.assertIn('mosh-2011-final-10-v1|10|', removed)


class AnswerEntriesTests(SimpleTestCase):
    def rows(self):
        parts = [{'label': str(i), 'text': 'вариант %d' % i} for i in range(1, 5)]
        return [row('тест-1', parts=parts), row('тест-2', parts=parts, answer='2'), row('тест-3', parts=parts)]

    def test_accepts_only_existing_option_for_empty_answer(self):
        replies = [{'event_id': 'ev', 'answers': [
            {'number': 'тест-1', 'answer': '3', 'evidence': '1 – 3', 'confidence': 0.9},
            {'number': 'тест-2', 'answer': '4', 'evidence': '2 – 4', 'confidence': 0.9},
            {'number': 'тест-3', 'answer': '7', 'evidence': '3 – 7', 'confidence': 0.9},
            {'number': 'тест-9', 'answer': '1', 'evidence': '', 'confidence': 0.9}]}]
        entries, rejected = ce.answer_entries(self.rows(), replies, {'ev': 'Ключ: 1 – 3; 2 – 4; 3 – 7'})
        self.assertEqual([(e['key'], e['value']) for e in entries], [('ev|тест-1|', '3')])
        reasons = {num: why for _, num, why in rejected}
        self.assertIn('ответ уже есть', reasons['тест-2'])
        self.assertIn('нет такого варианта', reasons['тест-3'])
        self.assertIn('нет такого теста', reasons['тест-9'])

    def test_evidence_must_be_in_key_layer(self):
        replies = [{'event_id': 'ev', 'answers': [
            {'number': 'тест-1', 'answer': '3', 'evidence': '11 – 3', 'confidence': 0.9}]}]
        entries, rejected = ce.answer_entries(self.rows(), replies, {'ev': 'Ключ: 1 – 3'})
        self.assertEqual(entries, [])
        self.assertIn('цитаты нет в ключе', rejected[0][2])


class TailVersusClaudeTests(SimpleTestCase):
    def test_claude_fix_wins_over_title_rule(self):
        r = row('тест-7', year=2012, title='Вопрос:', statement_md='1. а;\n2. б.', event_id='mosh-x')
        out, log, _ = ce.tail_rules_econ([r], 'mosh', skip_keys={'mosh-x|тест-7|'})
        self.assertEqual(out[0]['title'], 'Вопрос:')
        self.assertEqual(log, [])


class JobAndRawTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_job_file_and_raw_roundtrip(self):
        ds = fake_ds([row('1', src=['f.pdf#p1'])])
        ds.digitized = self.tmp
        units, _ = ce.build_units(ds)
        unit = units['vp_0123456789abcdef_p1']
        path = ce.write_job(unit, ds, os.path.join(self.tmp, 'jobs'))
        self.assertIn('ev|1|#statement', open(path, encoding='utf-8').read())
        self.assertIsNone(ce.load_raw(ds, 'claude-sonnet-5-5', unit['unit']))
        ce.save_raw(ds, 'claude-sonnet-5-5', unit['unit'], json.dumps({'tasks': []}), 'agent')
        self.assertEqual(ce.load_raw(ds, 'claude-sonnet-5-5', unit['unit'])['source'], 'agent')

    def test_custom_id_safe(self):
        self.assertEqual(ce.custom_id('vp_abc_p1'), 'vp_abc_p1')
        long = ce.custom_id('x' * 100)
        self.assertLessEqual(len(long), 64)

    def test_cost(self):
        usage = {'input_tokens': 1_000_000, 'output_tokens': 1_000_000}
        self.assertAlmostEqual(ce.usage_cost('claude-sonnet-5-5', usage), 6.0)
        self.assertAlmostEqual(ce.usage_cost('claude-haiku-5-5', usage), 0.30)
