# -*- coding: utf-8 -*-
"""Второй проход очереди «на утро» (problems/olympiad_audit/claude_recheck.py) на
выдуманных страницах: закрытие без модели, страницы запроса, порог уверенности и
цитата, проверки правки, сборка vN.1. Модель не вызывается, база не нужна."""
import json
import os
import shutil
import tempfile

from django.test import SimpleTestCase

from problems.olympiad_audit import claude_eyes as ce
from problems.olympiad_audit import claude_recheck as cr


def no_katex(segments):
    return [None] * len(segments)


def row(number, src=(), **kw):
    base = {'event_id': 'ev', 'number': number, 'task_variant': '', 'title': '',
            'statement_md': 'Цена товара 120 рублей, спрос Q = 40 - P.', 'parts': [], 'figures': [],
            'solution_figures': [], 'solution_md': '', 'answer': '', 'criteria_md': '',
            'source_pages': list(src), 'solution_pages': [], 'criteria_pages': []}
    base.update(kw)
    return base


def fake_ds(rows, digitized='/nowhere', pages=5):
    manifest = {'f.pdf#p%d' % n: {'file': 'f.pdf', 'page': n, 'page_dir': 'pages/0123456789abcdef',
                                  'png': 'x.png'} for n in range(1, pages + 1)}
    return ce.DataSet('vp', digitized, rows, manifest, 'v7', 'v7.1')


def item(kind, fid='ev|1|#statement', unit='vp_0123456789abcdef_p2', **kw):
    base = {'kind': kind, 'fid': fid, 'unit': unit, 'why': 'уверенность 0.50 < 0.60',
            'field': 'statement_md', 'text': '', 'model': 'claude-sonnet-5-5', 'set': 'vp', 'pngs': []}
    base.update(kw)
    return base


FRAG = {'fid': 'ev|1|#statement', 'group': 'statement', 'refs': ['f.pdf#p2'], 'editable': True,
        'fields': {'title': '', 'statement_md': 'Цена товара 120 рублей, спрос Q = 40 - P.',
                   'parts': [], 'figures': 0}}
PAGES = [('f.pdf#p2', 'проверяемая')]
LAYER = ['Цена товара 120 рублей, спрос Q = 40 - P. Найдите равновесие при налоге 10 рублей. '
         + 'Ответы записывайте в бланк разборчиво. ' * 5]


def answer(decision='fix', confidence=0.95, evidence='Найдите равновесие при налоге 10 рублей', **kw):
    base = {'id': 'i1', 'decision': decision, 'confidence': confidence, 'evidence': evidence,
            'classes': ['missing_text'],
            'fixes': {'statement_md': 'Цена товара 120 рублей, спрос Q = 40 - P. '
                                      'Найдите равновесие при налоге 10 рублей.'}}
    base.update(kw)
    return base


class AutoCloseTests(SimpleTestCase):
    def test_figure_present_and_unconfirmed_haiku_closed(self):
        items = [item(cr.KIND_FIGURE, why='такой рисунок уже есть в эталоне'),
                 item(cr.KIND_UNLISTED, fid='', model='claude-haiku-5-5'),
                 item(cr.KIND_UNLISTED, fid='', model='claude-haiku-5-5', unit='не проверялась'),
                 item(cr.KIND_FIX)]
        todo, closed = cr.auto_close(items, {'vp_0123456789abcdef_p2'})
        self.assertEqual([c['note'] for c in closed],
                         ['рисунок уже есть в эталоне', 'находка Haiku, Sonnet по той же странице её не подтвердил'])
        self.assertEqual([t['unit'] for t in todo], ['не проверялась', 'vp_0123456789abcdef_p2'])

    def test_group_items_ids_per_unit(self):
        groups = cr.group_items([item(cr.KIND_FIX), item(cr.KIND_DEFECT), item(cr.KIND_FIX, unit='u2')])
        self.assertEqual([i['iid'] for i in groups['vp_0123456789abcdef_p2']], ['i1', 'i2'])
        self.assertEqual([i['iid'] for i in groups['u2']], ['i1'])


class PagesTests(SimpleTestCase):
    def test_own_pages_then_neighbours(self):
        rows = {'ev|1|': row('1', src=['f.pdf#p2', 'f.pdf#p3'])}
        ds = fake_ds(list(rows.values()))
        unit = {'pages': ['f.pdf#p2']}
        pages = cr.request_pages(unit, [item(cr.KIND_FIX)], rows, ds.manifest)
        self.assertEqual(pages, [('f.pdf#p1', 'соседняя'), ('f.pdf#p2', 'проверяемая'),
                                 ('f.pdf#p3', 'проверяемая'), ('f.pdf#p4', 'соседняя')])
        frags = cr.fragments_for([item(cr.KIND_FIX)], {'ev|1|#statement': 'u'}, rows, pages)
        self.assertTrue(frags['ev|1|#statement']['editable'])

    def test_first_page_has_no_previous(self):
        ds = fake_ds([], pages=2)
        pages = cr.request_pages({'pages': ['f.pdf#p1']}, [], {}, ds.manifest)
        self.assertEqual(pages, [('f.pdf#p1', 'проверяемая'), ('f.pdf#p2', 'соседняя')])


class EvidenceTests(SimpleTestCase):
    def test_quote_must_be_on_page_layer(self):
        self.assertTrue(cr.evidence_on_page('при налоге 10 рублей', LAYER[0]))
        self.assertFalse(cr.evidence_on_page('при субсидии 10 рублей фирмам', LAYER[0]))
        self.assertFalse(cr.evidence_on_page('при налоге 15 рублей', LAYER[0]))     # чужое число
        self.assertFalse(cr.evidence_on_page('', LAYER[0]))

    def test_scan_without_layer_needs_some_quote(self):
        self.assertTrue(cr.evidence_on_page('Найдите равновесие', ''))
        self.assertTrue(cr.evidence_on_page('X2 = K*(1+i)^2/3 (+1 балл)', 'стр. 3 \x0c'))  # слой-огрызок = скан
        self.assertFalse(cr.evidence_on_page('—', ''))

    def test_hyphen_and_letters_only_words(self):
        layer = LAYER[0] + ' Вершины лежат на ребрах доде-\nкаэдра. Издержки TC = 120 ln(100).' * 3
        self.assertTrue(cr.evidence_on_page('на ребрах додекаэдра', layer))
        self.assertTrue(cr.evidence_on_page('TC = 120ln(100)', layer))
        self.assertFalse(cr.evidence_on_page('на гранях икосаэдра', layer))


class CheckItemTests(SimpleTestCase):
    def check(self, ans, frag=FRAG, it=None):
        return cr.check_item(it or item(cr.KIND_FIX), ans, frag, PAGES, LAYER, katex=no_katex)

    def test_confident_fix_with_quote_accepted(self):
        res = self.check(answer())
        self.assertEqual(res['resolution'], 'fixed')
        self.assertEqual(res['fixes'][0].field, 'statement_md')

    def test_below_09_stays_in_queue(self):
        res = self.check(answer(confidence=0.85))
        self.assertEqual(res['resolution'], 'queue')
        self.assertIn('уверенность 0.85 < 0.90', res['reasons'])

    def test_quote_not_on_page_stays(self):
        res = self.check(answer(evidence='этого текста на странице нет вовсе'))
        self.assertEqual(res['resolution'], 'queue')
        self.assertIn('нет цитаты со страницы', res['reasons'])

    def test_fix_runs_first_pass_checks(self):
        ans = answer(fixes={'statement_md': 'Цена товара 120 рублей, спрос Q = 40 - P. Налог 99 рублей.'})
        res = self.check(ans)
        self.assertEqual(res['resolution'], 'queue')
        self.assertTrue(any('чужие числа: 99' in r for r in res['reasons']))
        res = self.check(answer(), frag=dict(FRAG, editable=False))
        self.assertEqual(res['resolution'], 'queue')

    def test_keep_closes_and_human_stays(self):
        self.assertEqual(self.check(answer(decision='keep', fixes={}))['resolution'], 'closed')
        res = self.check(answer(decision='human', fixes={}))
        self.assertEqual(res['resolution'], 'queue')
        self.assertIn('модель оставила человеку', res['reasons'])
        self.assertEqual(self.check(None)['reasons'], ['нет ответа по позиции'])

    def test_figure_needs_valid_frame(self):
        ok = self.check(answer(decision='figure', figure_bboxes=[{'page': 1, 'bbox': [0.1, 0.1, 0.5, 0.5]}]))
        self.assertEqual(ok['resolution'], 'figure')
        self.assertEqual(ok['figures'][0]['page_ref'], 'f.pdf#p2')
        bad = self.check(answer(decision='figure', figure_bboxes=[{'page': 3, 'bbox': [0.1, 0.1, 0.5, 0.5]}]))
        self.assertEqual(bad['resolution'], 'queue')
        crit = self.check(answer(decision='figure', figure_bboxes=[{'page': 1, 'bbox': [0.1, 0.1, 0.5, 0.5]}]),
                          frag=dict(FRAG, group='criteria'))
        self.assertEqual(crit['resolution'], 'queue')


class RoundsTests(SimpleTestCase):
    def test_retry_only_near_threshold_decisions(self):
        near = {'resolution': 'queue', 'decision': 'fix', 'confidence': 0.85}
        self.assertTrue(cr.needs_retry([(item(cr.KIND_FIX), near)]))
        self.assertFalse(cr.needs_retry([(item(cr.KIND_FIX), dict(near, confidence=0.5))]))
        self.assertFalse(cr.needs_retry([(item(cr.KIND_FIX), dict(near, decision='human'))]))
        self.assertFalse(cr.needs_retry([(item(cr.KIND_FIX), dict(near, resolution='fixed'))]))

    def test_merge_keeps_first_and_fills_queue_only(self):
        a, b = item(cr.KIND_FIX), item(cr.KIND_DEFECT)
        first = [(a, {'resolution': 'fixed'}), (b, {'resolution': 'queue'})]
        second = [(a, {'resolution': 'queue'}), (b, {'resolution': 'closed'})]
        self.assertEqual([r['resolution'] for _, r in cr.merge_rounds(first, second)], ['fixed', 'closed'])
        second = [(a, {'resolution': 'closed'}), (b, {'resolution': 'queue'})]
        self.assertEqual([r['resolution'] for _, r in cr.merge_rounds(first, second)], ['fixed', 'queue'])


class DedupeTests(SimpleTestCase):
    def test_same_field_and_same_finding_merged(self):
        queue = [item(cr.KIND_FIX), item(cr.KIND_FIX, unit='u2'), item(cr.KIND_FIX, field='parts'),
                 item(cr.KIND_UNLISTED, fid='', text='Задача 4. Фирма «Альфа»'),
                 item(cr.KIND_UNLISTED, fid='', text='Задача 4. Фирма «Альфа»', unit='u3'),
                 item(cr.KIND_UNLISTED, fid='', text='Задача 5. Банк «Бета»')]
        out = cr.dedupe_queue(queue)
        self.assertEqual(len(out), 4)
        self.assertIn('повторялась 2 раза', out[0]['why'])
        self.assertNotIn('повторялась', out[1]['why'])


class BuildTests(SimpleTestCase):
    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.mkdtemp()
        Image.new('RGB', (1000, 1000), 'white').save(os.path.join(self.tmp, 'x.png'))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_build_applies_only_accepted_and_keeps_queue(self):
        rows = [row('1', src=['f.pdf#p2']), row('2', src=['f.pdf#p2'])]
        ds = fake_ds(rows, digitized=self.tmp)
        fixed = cr.check_item(item(cr.KIND_FIX), answer(), FRAG, PAGES, LAYER, katex=no_katex)
        queued = cr.check_item(item(cr.KIND_DEFECT, fid='ev|2|#statement'), answer(confidence=0.5),
                               dict(FRAG, fid='ev|2|#statement'), PAGES, LAYER, katex=no_katex)
        closed = [dict(item(cr.KIND_FIGURE), resolution='closed', note='рисунок уже есть в эталоне')]
        res = cr.build(ds, [(item(cr.KIND_FIX), fixed),
                            (item(cr.KIND_DEFECT, fid='ev|2|#statement'), queued)], closed, katex=no_katex)
        self.assertTrue(res['invariants']['ok'])
        self.assertEqual(res['invariants']['queue_in'], 3)
        self.assertEqual(res['invariants']['queue_out'], 1)
        out = ce.read_jsonl(res['path'])
        self.assertIn('налоге 10 рублей', out[0]['statement_md'])
        self.assertEqual(out[0]['claude_recheck']['fields'], ['statement_md'])
        self.assertEqual(out[1]['statement_md'], rows[1]['statement_md'])
        self.assertNotIn('налоге', rows[0]['statement_md'])                # вход не тронут
        self.assertTrue(res['path'].replace('\\', '/').endswith('v7.1/reference_problems_v7.1.jsonl'))
        morning = ce.read_jsonl(os.path.join(self.tmp, 'v7.1', 'morning_v7.1.jsonl'))
        self.assertEqual(morning[0]['fid'], 'ev|2|#statement')
        self.assertIn('второй проход', morning[0]['why'])

    def test_build_figure_cropped_and_duplicate_closed(self):
        old = {'page': 2, 'page_dir': 'pages/0123456789abcdef', 'bbox_norm': [0.1, 0.1, 0.5, 0.5]}
        rows = [row('1', src=['f.pdf#p2']), row('2', src=['f.pdf#p2'], figures=[old])]
        ds = fake_ds(rows, digitized=self.tmp)
        fig = {'resolution': 'figure', 'note': '',
               'figures': [{'page_ref': 'f.pdf#p2', 'bbox': [0.1, 0.1, 0.5, 0.5], 'caption': 'график'}]}
        res = cr.build(ds, [(item(cr.KIND_FIGURE), fig),
                            (item(cr.KIND_FIGURE, fid='ev|2|#statement'), fig)], [], katex=no_katex)
        self.assertTrue(res['invariants']['ok'])
        self.assertEqual(len(res['figures']), 1)
        self.assertEqual(res['figures'][0]['value']['path'], 'v7.1/figures_v7.1/ev_1_r1.png')
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'v7.1', 'figures_v7.1', 'ev_1_r1.png')))
        self.assertEqual([d['resolution'] for d in res['done']], ['figure', 'closed'])
        layer = json.load(open(os.path.join(self.tmp, 'v7.1', 'claude_recheck_v7.1.json'), encoding='utf-8'))
        self.assertEqual(len(layer['resolved']), 2)

    def test_second_frame_of_same_figure_and_eyes_rejection(self):
        os.makedirs(os.path.join(self.tmp, 'audit_claude'))
        with open(os.path.join(self.tmp, 'audit_claude', 'figures_rejected.txt'), 'w', encoding='utf-8') as h:
            h.write('ev_2_r1.png  # срезаны подписи осей\n')
        ds = fake_ds([row('1', src=['f.pdf#p2']), row('2', src=['f.pdf#p2'])], digitized=self.tmp)
        twice = {'resolution': 'figure', 'note': '', 'figures': [
            {'page_ref': 'f.pdf#p2', 'bbox': [0.1, 0.1, 0.5, 0.5], 'caption': 'КПВ'},
            {'page_ref': 'f.pdf#p2', 'bbox': [0.11, 0.1, 0.5, 0.51], 'caption': 'КПВ'}]}
        res = cr.build(ds, [(item(cr.KIND_FIGURE), twice),
                            (item(cr.KIND_FIGURE, fid='ev|2|#statement'), twice)], [], katex=no_katex)
        self.assertEqual([f['value']['path'] for f in res['figures']], ['v7.1/figures_v7.1/ev_1_r1.png'])
        self.assertEqual(len(res['queue']), 1)
        self.assertIn('забракована при просмотре глазами', res['queue'][0]['why'])

    def test_stale_field_not_applied_breaks_invariants(self):
        rows = [row('1', src=['f.pdf#p2'])]
        ds = fake_ds(rows, digitized=self.tmp)
        fixed = cr.check_item(item(cr.KIND_FIX), answer(), dict(FRAG, fields=dict(FRAG['fields'],
                              statement_md='другой прежний текст 120 40')), PAGES, LAYER, katex=no_katex)
        res = cr.build(ds, [(item(cr.KIND_FIX), fixed)], [], katex=no_katex)
        self.assertFalse(res['invariants']['ok'])
        self.assertEqual(res['invariants']['layer_not_applied'][0][2], 'поле изменилось после аудита')
