"""Проверка олимпиадных задач людьми (Q3, 29.10.2026): загрузчики очередей, склейка
карточек, формат решений, применение каждого решения, reference_overrides в импорте,
выборка приёмки и интервал Уилсона. Данные выдуманные."""
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from problems.models import Problem, ProblemPart, ProblemVersion, Source, SourceReference
from problems.olympiad_audit import registry
from problems.olympiad_review import acceptance as acc
from problems.olympiad_review import apply as ap
from problems.olympiad_review import common, decisions as dc, overrides as ovr, queue, sources

EV = 'vp-2015-final-11-v1'
PDF = 'raw/pdf/2015_11.pdf'


def _row(number, statement, **extra):
    row = {'event_id': EV, 'number': str(number), 'task_variant': '', 'title': f'Задача {number}',
           'year': 2015, 'academic_year': '2014/2015', 'stage': 'final', 'grade': '11',
           'statement_md': statement, 'parts': [], 'figures': [], 'solution_figures': [],
           'solution_md': 'Решение.', 'answer': '42', 'criteria_md': '', 'max_score': 10,
           'source_file': [PDF], 'source_pages': [PDF + '#p2'], 'solution_pages': [],
           'official': True, 'source': 'official', 'needs_eyes': False, 'numbers_ok': True}
    row.update(extra)
    return row


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as h:
        for r in rows:
            h.write(json.dumps(r, ensure_ascii=False) + '\n')


class _DataRoot(TestCase):
    """Временный корень данных олимпиад с эталоном ВП v7.1 и страницами."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        env = mock.patch.dict(os.environ, {'OLYMPIAD_DATA_ROOT': os.path.join(self.tmp, 'olympiads'),
                                           'OLYMPIAD_QUALITY_DIR': os.path.join(self.tmp, 'quality')})
        env.start()
        self.addCleanup(env.stop)
        self.audit = Path(self.tmp) / 'olympiads' / registry.get('vp').audit_dir
        self.dig = self.audit / 'digitized'
        self.rows = [_row(1, 'Спрос $Q = 100 - 2P$, предложение $Q = 3P$. Найдите равновесие.'),
                     _row(2, 'Фирма с издержками $TC = q^2$ продаёт по цене 10. Найдите:\n\nа) выпуск\n\nб) прибыль',
                          parts=[{'label': 'а', 'text': 'выпуск'}, {'label': 'б', 'text': 'прибыль'}])]
        _write_jsonl(self.dig / 'v7.1' / 'reference_problems_v7.1.jsonl', self.rows)
        _write_jsonl(self.dig / 'inventory.jsonl', [{'file': PDF, 'page_dir': 'pages/abcd'}])
        (self.dig / 'pages' / 'abcd').mkdir(parents=True)
        for n in (1, 2, 3):
            (self.dig / 'pages' / 'abcd' / f'p{n}.png').write_bytes(b'png')
        self.png = str(self.dig / 'pages' / 'abcd' / 'p2.png')

    def morning(self, rows):
        path = self.dig / 'v7.1' / 'morning_v7.1.jsonl'
        _write_jsonl(path, rows)
        return [str(path)]


def _m(kind, fid, field='', text='', why='уверенность 0.85 < 0.90', iid='i1'):
    return {'kind': kind, 'fid': fid, 'unit': 'vp_abcd_p2', 'why': why, 'field': field, 'text': text,
            'model': 'm', 'set': 'vp', 'pngs': [], 'iid': iid}


class LoadersTests(_DataRoot):
    def test_ref_key_from_fid(self):
        self.assertEqual(sources.p2_ref_key(f'{EV}|3|#statement'), f'{EV}:3')
        self.assertEqual(sources.p2_ref_key(f'{EV}|тест-2|v2#solution'), f'{EV}:тест-2:v2')

    def test_parse_parts_text(self):
        got = sources.parse_parts_text('а) выпуск 5\nб) прибыль\nравна 15', ['а', 'б'])
        self.assertEqual(got, [{'label': 'а', 'text': 'выпуск 5'}, {'label': 'б', 'text': 'прибыль\nравна 15'}])
        self.assertIsNone(sources.parse_parts_text('1 выпуск\n2 прибыль', ['а', 'б']))
        self.assertIsNone(sources.parse_parts_text('а) выпуск', ['а', 'б']))

    def test_p2_kinds_missing_proposal_and_pages(self):
        items, missing = sources.load_p2(self.morning([
            _m('правка не принята', f'{EV}|1|#statement', 'statement_md',
               'Спрос $Q = 100 - 2P$, предложение $Q = 3P$. Найдите равновесную цену.'),
            _m('дефект без правки', f'{EV}|2|#solution', iid='i2'),
            _m('на странице есть, в эталоне нет', '', text='Задание 7', iid='i3'),
        ]))
        self.assertEqual(len(items), 2)
        self.assertEqual(len(missing), 1)
        fix = next(i for i in items if i['ref_key'] == f'{EV}:1')
        self.assertIsNone(fix['problem_id'])
        self.assertIn('равновесную цену', fix['proposed']['statement'])
        self.assertEqual(set(fix['proposed']), {'statement'})
        self.assertEqual(fix['current_from'], 'reference')
        self.assertEqual(fix['page_images'], [self.png])
        self.assertAlmostEqual(fix['confidence'], 0.85)
        defect = next(i for i in items if i['ref_key'] == f'{EV}:2')
        self.assertIsNone(defect['proposed'])
        self.assertEqual([p['label'] for p in defect['current']['parts']], ['а', 'б'])
        self.assertEqual(len({i['item_id'] for i in items}), 2)

    def test_truncated_proposal_is_not_offered(self):
        items, _ = sources.load_p2(self.morning([
            _m('правка не принята', f'{EV}|1|#statement', 'statement_md', 'x' * 3000)]))
        self.assertIsNone(items[0]['proposed'])
        self.assertIn('обрезан', items[0]['details'])

    def test_created_vs_linked_problem(self):
        src = Source.objects.create(name='src')
        made = Problem.objects.create(statement='как в эталоне', content_format='markdown')
        SourceReference.objects.create(problem=made, source=src, problem_number=f'{EV}:1')
        linked = Problem.objects.create(statement='свой текст банка', content_format='markdown')
        SourceReference.objects.create(problem=linked, source=src, problem_number='МатЭк 5')
        SourceReference.objects.create(problem=linked, source=src, problem_number=f'{EV}:2')
        items, _ = sources.load_p2(self.morning([
            _m('дефект без правки', f'{EV}|1|#statement'),
            _m('правка не принята', f'{EV}|2|#statement', 'statement_md', 'новый текст', iid='i2')]))
        by = {i['ref_key']: i for i in items}
        self.assertEqual(by[f'{EV}:1']['problem_id'], made.id)
        self.assertEqual(by[f'{EV}:1']['current_from'], 'reference')
        self.assertEqual(by[f'{EV}:2']['problem_id'], linked.id)
        self.assertEqual(by[f'{EV}:2']['current']['statement'], 'свой текст банка')
        self.assertIsNone(by[f'{EV}:2']['proposed'])
        self.assertIn('текст у неё свой', by[f'{EV}:2']['details'])

    def test_common_format_options_to_parts(self):
        path = os.path.join(self.tmp, 'q1.jsonl')
        _write_jsonl(path, [{'item_id': 'q1:vp:x:S7', 'source': 'q1_contour', 'olympiad': 'vp',
                             'ref_key': 'x', 'problem_id': None, 'check': 'S7', 'details': 'ключ',
                             'page_images': [], 'current': {'statement': 'Вопрос', 'options': ['да', 'нет'],
                                                            'key': '2'},
                             'proposed': None, 'confidence': None, 'auto': True}])
        item = sources.load_common(path)[0]
        self.assertEqual(item['current']['parts'], [{'label': '1', 'statement': 'да', 'answer': ''},
                                                    {'label': '2', 'statement': 'нет', 'answer': 'верно'}])
        self.assertTrue(item['auto'])


def _it(item_id, pid=None, key=None, olympiad='vp', **kw):
    base = {k: None for k in common.ITEM_KEYS}
    base.update(item_id=item_id, problem_id=pid, ref_key=key, olympiad=olympiad, source='s',
                check='c', details='d', page_images=[], current={'statement': 's'}, proposed=None)
    base.update(kw)
    return base


class QueueTests(SimpleTestCase):
    def test_merge_by_problem_and_key(self):
        cards = queue.merge([_it('a', pid=1, key='k1'), _it('b', pid=1, key='k2'), _it('c', key='k2'),
                             _it('d', key='k9'), _it('e', pid=2)])
        groups = sorted(sorted(c['items']) for c in cards)
        self.assertEqual(groups, [['a', 'b', 'c'], ['d'], ['e']])
        self.assertEqual(next(c for c in cards if 'a' in c['items'])['item_id'], 'p1')

    def test_proposals_merge_and_clash(self):
        card = queue.merge([_it('a', pid=1, proposed={'answer': '5'}),
                            _it('b', pid=1, proposed={'answer': '6', 'solution': 'x'})])[0]
        self.assertEqual(card['proposed'], {'answer': '5', 'solution': 'x'})
        self.assertEqual(card['proposed_clash'], ['answer'])

    def test_build_priority_closed_auto_and_counts(self):
        items = [_it('m', pid=5, olympiad='mosh'), _it('v', pid=6, olympiad='vp'),
                 _it('f', pid=7, olympiad='vp-fingram'), _it('h', pid=8, olympiad='mosh'),
                 _it('x', pid=9), _it('z', pid=10, auto=True, proposed={'answer': '1'})]
        cards, auto, summary = queue.build(items, closed={'x'}, is_visible=lambda pid: pid == 8)
        self.assertEqual([c['item_id'] for c in cards], ['p8', 'p6', 'p5', 'p7'])
        self.assertEqual([a['item_id'] for a in auto], ['z'])
        self.assertEqual(summary['карточек'], 4)
        self.assertEqual(summary['позиций людям'] - summary['карточек'], summary['склеено (позиций − карточек)'])


def _dec(item, decision='ok', reviewer='Андрей', ts='2026-10-29T10:00', **kw):
    return dict({'item_id': item, 'decision': decision, 'edited': {}, 'reviewer': reviewer,
                 'comment': '', 'ts': ts}, **kw)


class DecisionFormatTests(SimpleTestCase):
    def test_validate(self):
        self.assertEqual(dc.validate(_dec('p1')), [])
        self.assertTrue(dc.validate(_dec('p1', 'delete')))
        self.assertTrue(dc.validate(_dec('p1', 'edit')))
        self.assertTrue(dc.validate(_dec('p1', 'edit', edited={'color': 'x'})))
        self.assertEqual(dc.validate(_dec('p1', 'edit', edited={'answer': '5'})), [])
        self.assertTrue(dc.validate({'item_id': 'a', 'reviewer': 'A', 'defects': ['bad']}, 'acceptance'))
        self.assertTrue(dc.validate({'item_id': 'a', 'reviewer': 'A', 'defects': []}, 'acceptance'))
        self.assertEqual(dc.validate({'item_id': 'a', 'reviewer': 'A', 'defects': ['table']},
                                     'acceptance'), [])

    def test_merge_latest_dispute_and_skip(self):
        files = [('f1', {'pack_id': 'P1', 'decisions': [
                    _dec('a', 'ok', ts='1'), _dec('a', 'hide', ts='2'),
                    _dec('b', 'ok'), _dec('c', 'skip')]}),
                 ('f2', {'pack_id': 'P1', 'decisions': [
                    _dec('b', 'hide', reviewer='Анич'), _dec('c', 'ok', reviewer='Анич')]})]
        chosen, disputes = dc.merge(files)
        self.assertEqual(chosen[('P1', 'a')]['decision'], 'hide')
        self.assertEqual([d['item_id'] for d in disputes], ['b'])
        self.assertEqual(chosen[('P1', 'c')]['decision'], 'ok')
        self.assertNotIn(('P1', 'b'), chosen)

    def test_load_files_rejects_bad_rows(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = os.path.join(tmp, 'd.json')
        with open(path, 'w', encoding='utf-8') as h:
            json.dump({'pack_id': 'P', 'decisions': [_dec('a', 'maybe')]}, h)
        with self.assertRaises(dc.DecisionError):
            dc.load_files([path])


class ApplyTests(_DataRoot):
    def setUp(self):
        super().setUp()
        self.p = Problem.objects.create(title='Т', statement='Старое условие', answer='1',
                                        solution='Реш', content_format='markdown', status='published')
        ProblemPart.objects.create(problem=self.p, label='а', statement='пункт а', answer='', order=0)
        self.files = ap.Files(os.environ['OLYMPIAD_QUALITY_DIR'])

    def card(self, **kw):
        current = sources.Bank.fields(self.p)[0]
        card = {'item_id': f'p{self.p.id}', 'olympiad': 'vp', 'ref_key': f'{EV}:1', 'problem_id': self.p.id,
                'kind': 'fix', 'items': ['i1', 'i2'], 'current': current, 'proposed': None,
                'base': {k: common.field_sha(v) for k, v in current.items()}}
        card.update(kw)
        return card

    def run_apply(self, pairs):
        actions = ap.plan(pairs, self.files)
        journal = ap.execute(actions, self.files, journal_path=Path(self.tmp) / 'j.json')
        return actions, journal

    def test_accept_proposed_with_version_repeat_and_rollback(self):
        card = self.card(proposed={'statement': 'Новое условие', 'answer': '2'})
        pairs = [(card, _dec(card['item_id'], 'accept_proposed', pack_id='P'))]
        actions, journal = self.run_apply(pairs)
        self.p.refresh_from_db()
        self.assertEqual((self.p.statement, self.p.answer), ('Новое условие', '2'))
        self.assertEqual(ProblemVersion.objects.filter(problem=self.p).count(), 1)
        self.assertEqual(ProblemVersion.objects.get(problem=self.p).snapshot['statement'], 'Старое условие')
        self.assertEqual(sum(1 for a in ap.plan(pairs, self.files) if a['kind'] in ap.WRITE_KINDS), 0)
        closed = common.read_jsonl(self.files.closed())
        self.assertEqual(sorted(r['item'] for r in closed), ['i1', 'i2'])
        ap.rollback(journal)
        self.p.refresh_from_db()
        self.assertEqual((self.p.statement, self.p.answer), ('Старое условие', '1'))
        self.assertEqual(ProblemVersion.objects.filter(problem=self.p).count(), 0)
        self.assertFalse(self.files.closed().exists())

    def test_edit_parts_in_place_and_added(self):
        card = self.card()
        edited = {'parts': [{'label': 'а', 'statement': 'пункт а, исправлен', 'answer': '5'},
                            {'label': 'б', 'statement': 'новый пункт', 'answer': ''}]}
        actions, journal = self.run_apply([(card, _dec(card['item_id'], 'edit', edited=edited, pack_id='P'))])
        parts = list(self.p.parts.order_by('order', 'id').values_list('label', 'statement', 'answer'))
        self.assertEqual(parts, [('а', 'пункт а, исправлен', '5'), ('б', 'новый пункт', '')])
        ap.rollback(journal)
        self.assertEqual(list(self.p.parts.values_list('statement', flat=True)), ['пункт а'])

    def test_fewer_parts_and_changed_base_are_conflicts(self):
        card = self.card()
        acts = ap.plan([(card, _dec(card['item_id'], 'edit', edited={'parts': []}, pack_id='P'))], self.files)
        self.assertEqual([a['kind'] for a in acts], ['conflict'])
        Problem.objects.filter(pk=self.p.pk).update(statement='Кто-то поправил')
        acts = ap.plan([(card, _dec(card['item_id'], 'edit', edited={'statement': 'Моё'}, pack_id='P'))],
                       self.files)
        self.assertEqual([a['kind'] for a in acts], ['conflict'])
        self.assertIn('не то, что было в пакете', acts[0]['why'])

    def test_hide_not_a_task_ok_skip(self):
        other = Problem.objects.create(statement='вторая', content_format='markdown')
        c1 = self.card()
        c2 = dict(self.card(), item_id=f'p{other.id}', problem_id=other.id, items=['o1'])
        acts, journal = self.run_apply([(c1, _dec(c1['item_id'], 'hide', pack_id='P')),
                                        (c2, _dec(c2['item_id'], 'not_a_task', pack_id='P'))])
        self.p.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((self.p.content_status, other.content_status), ('needs_fix', 'junk'))
        self.assertEqual(Problem.objects.count(), 2)
        ap.rollback(journal)
        self.p.refresh_from_db()
        self.assertEqual(self.p.content_status, 'ok')
        ok = ap.plan([(c1, _dec(c1['item_id'], 'ok', pack_id='P'))], self.files)
        self.assertEqual([a['kind'] for a in ok], ['close'])
        ap._save_json(self.files.index(), {c1['item_id']: {'pack': 'P', 'reviewer': 'Андрей'}})
        acts, journal = self.run_apply([(c1, _dec(c1['item_id'], 'skip', pack_id='P'))])
        self.assertEqual([a['kind'] for a in acts], ['requeue'])
        self.assertEqual(ap._load_index(self.files.index()), {})
        ap.rollback(journal)
        self.assertIn(c1['item_id'], ap._load_index(self.files.index()))

    def test_reference_rows_go_to_overrides(self):
        fix = {'item_id': f'r:{EV}:1', 'olympiad': 'vp', 'ref_key': f'{EV}:1', 'problem_id': None,
               'kind': 'fix', 'items': ['x1'], 'current': {'statement': 'a'}, 'proposed': {'statement': 'b'},
               'base': {}}
        pair = dict(fix, item_id=f'r:{EV}:2', ref_key=f'{EV}:2', kind='pair', items=['x2'],
                    pair_bank={'id': 777, 'fields': {}}, proposed=None)
        pairs = [(fix, _dec(fix['item_id'], 'accept_proposed', pack_id='P')),
                 (pair, _dec(pair['item_id'], 'accept_proposed', pack_id='P'))]
        acts, journal = self.run_apply(pairs)
        lines = common.read_jsonl(common.overrides_path('vp'))
        self.assertEqual([(r['ref_key'], r['action']) for r in lines], [(f'{EV}:1', 'edit'), (f'{EV}:2', 'link')])
        self.assertEqual(lines[0]['fields'], {'statement': 'b'})
        self.assertEqual(lines[1]['bank_id'], 777)
        self.assertEqual(sum(1 for a in ap.plan(pairs, self.files) if a['kind'] in ap.WRITE_KINDS), 0)
        ok = ap.plan([(pair, _dec(pair['item_id'], 'ok', pack_id='Q'))], self.files)
        self.assertEqual(next(a for a in ok if a['kind'] == 'override')['line']['action'], 'new')
        ap.rollback(journal)
        self.assertFalse(common.overrides_path('vp').exists())

    def test_rehearsal_files_are_redirected(self):
        redirect = Path(self.tmp) / 'reh'
        files = ap.Files(os.environ['OLYMPIAD_QUALITY_DIR'], redirect=redirect)
        fix = {'item_id': 'r:k', 'olympiad': 'vp', 'ref_key': 'k', 'problem_id': None, 'kind': 'fix',
               'items': ['x'], 'current': {}, 'proposed': None, 'base': {}}
        ap.execute(ap.plan([(fix, _dec('r:k', 'hide', pack_id='P'))], files), files,
                   journal_path=redirect / 'j.json')
        self.assertFalse(common.overrides_path('vp').exists())
        self.assertTrue(any(redirect.glob('*reference_overrides.jsonl')))

    def test_auto_fixes_become_accept_decisions(self):
        path = Path(self.tmp) / 'auto.jsonl'
        _write_jsonl(path, [{'item_id': 'q1:vp:1:S4', 'auto': True, 'problem_id': self.p.id,
                             'olympiad': 'vp', 'ref_key': None, 'check': 'S4',
                             'current': {'statement': 'Старое условие'}, 'proposed': {'statement': 'Старое  условие'}},
                            {'item_id': 'q1:vp:2:S1', 'auto': False, 'proposed': {'statement': 'x'}}])
        pairs = ap.auto_cards(path)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][1]['decision'], 'accept_proposed')
        self.assertEqual(pairs[0][1]['reviewer'], ap.AUTO_REVIEWER)


    def test_rollback_truncates_to_previous_content(self):
        path = self.files.closed()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"item": "раньше"}\n', encoding='utf-8')
        card = self.card()
        _a, journal = self.run_apply([(card, _dec(card['item_id'], 'ok', pack_id='P'))])
        self.assertEqual(len(common.read_jsonl(path)), 3)
        ap.rollback(journal)
        self.assertEqual(common.read_jsonl(path), [{'item': 'раньше'}])


class OverridesTests(SimpleTestCase):
    def test_load_latest_wins_fields_accumulate(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = os.path.join(tmp, 'o.jsonl')
        _write_jsonl(path, [{'ref_key': 'k', 'action': 'edit', 'fields': {'answer': '1'}},
                            {'ref_key': 'k', 'action': 'edit', 'fields': {'statement': 's'}},
                            {'ref_key': 'z', 'action': 'boom'}])
        got = ovr.load(path)
        self.assertEqual(list(got), ['k'])
        self.assertEqual(got['k']['fields'], {'answer': '1', 'statement': 's'})

    def test_apply_fields_and_decisions(self):
        built = {'statement': 'old', 'answer': '', 'parts': []}
        ovr.apply_fields(built, {'action': 'edit', 'fields': {'statement': 'new', 'parts': [
            {'label': 'а', 'statement': 'p', 'answer': '1'}]}})
        self.assertEqual(built['statement'], 'new')
        self.assertEqual(built['parts'][0]['statement_md'], 'p')
        self.assertEqual(ovr.as_import_decision({'ref_key': 'k', 'action': 'link', 'bank_id': '5'})['bank_id'], 5)
        self.assertEqual(ovr.as_import_decision({'ref_key': 'k', 'action': 'new'})['decision'], 'new')
        self.assertEqual(ovr.as_import_decision({'ref_key': 'k', 'action': 'not_a_task'})['decision'], 'skip')
        self.assertIsNone(ovr.as_import_decision({'ref_key': 'k', 'action': 'ok'}))
        self.assertTrue(ovr.reviewed({'action': 'ok'}))
        self.assertFalse(ovr.reviewed({'action': 'not_a_task'}))


class ImportHonoursOverridesTests(TestCase):
    """import_olympiad_reference: правка человека в поля, «не задача» — пропуск,
    needs_eyes с решением человека — пишется."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.dig = os.path.join(self.tmp, 'digitized')
        os.makedirs(self.dig)
        self.out = os.path.join(self.tmp, 'out')
        os.makedirs(self.out)
        Source.objects.create(name=registry.get('vp').official_source_name)
        with open(os.path.join(self.out, 'bank_candidates.json'), 'w', encoding='utf-8') as h:
            json.dump({'meta': {}, 'candidates': {}}, h)

    def run_import(self, rows, overrides):
        queue_path = os.path.join(self.dig, 'reference_problems_v7.1.jsonl')
        _write_jsonl(queue_path, rows)
        ov = os.path.join(self.tmp, 'reference_overrides.jsonl')
        _write_jsonl(ov, overrides)
        with open(os.devnull, 'w', encoding='utf-8') as quiet:
            call_command('import_olympiad_reference', '--olympiad', 'vp', '--queue', queue_path,
                         '--digitized', self.dig, '--out-dir', self.out, '--no-katex',
                         '--overrides', ov, '--apply', '--yes-i-have-owner-approval', stdout=quiet)

    def test_overrides_applied(self):
        long = ('Спрос на рынке задан функцией Q = 120 - 3P, предложение Q = 2P - 10. '
                'Государство вводит налог 5 рублей с единицы. Найдите новое равновесие {}.')
        rows = [_row(1, long.format('и выручку')), _row(2, long.format('и потери')),
                _row(3, long.format('и излишки'), needs_eyes=True)]
        self.run_import(rows, [
            {'ref_key': f'{EV}:1', 'action': 'edit', 'fields': {'statement': 'Исправлено человеком.'}},
            {'ref_key': f'{EV}:2', 'action': 'not_a_task'},
            {'ref_key': f'{EV}:3', 'action': 'ok'}])
        made = {sr.problem_number: sr.problem for sr in SourceReference.objects.select_related('problem')}
        self.assertEqual(made[f'{EV}:1'].statement, 'Исправлено человеком.')
        self.assertNotIn(f'{EV}:2', made)
        self.assertIn(f'{EV}:3', made)


class AcceptanceTests(SimpleTestCase):
    def test_sample_deterministic_and_uniform(self):
        strata = {(2015, 'final'): list(range(0, 50)), (2016, 'final'): list(range(100, 150)),
                  (2017, 'final'): list(range(200, 250)), (2017, 'qualifying'): list(range(300, 310))}
        a = acc.stratified_sample(strata, 100, 20261029)
        self.assertEqual(a, acc.stratified_sample(strata, 100, 20261029))
        self.assertNotEqual(a, acc.stratified_sample(strata, 100, 1))
        self.assertEqual(len(a), len(set(a)))
        layer = lambda x: x // 100   # noqa: E731
        counts = {k: sum(1 for x in a if layer(x) == k) for k in range(4)}
        self.assertEqual(counts, {0: 30, 1: 30, 2: 30, 3: 10})
        self.assertEqual(len(acc.stratified_sample({(1, 'f'): [1, 2]}, 100, 1)), 2)

    def test_wilson(self):
        lo, hi = acc.wilson(0, 100)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.0370, places=3)
        lo, hi = acc.wilson(3, 100)
        self.assertAlmostEqual(lo, 0.0103, places=3)
        self.assertAlmostEqual(hi, 0.0845, places=3)
        self.assertEqual(acc.wilson(0, 0), (0.0, 1.0))

    def test_verdict_and_report(self):
        self.assertEqual(acc.verdict(2, 100), 'можно открывать')
        self.assertEqual(acc.verdict(3, 100), 'нельзя открывать')
        self.assertTrue(acc.verdict(0, 50).startswith('мало данных'))
        card = lambda pid: {'olympiad': 'vp', 'problem_id': pid, 'ref_key': None, 'current': {}}  # noqa: E731
        rows = [(card(1), {'reviewer': 'А', 'defects': ['table'], 'comment': 'x'}),
                (card(1), {'reviewer': 'Б', 'defects': []}),
                (card(2), {'reviewer': 'Б', 'defects': [], 'no_defects': True})]
        summary, bad = acc.report(rows)
        self.assertEqual(summary['vp']['просмотрено'], 2)
        self.assertEqual(summary['vp']['с дефектом'], 1)
        items = acc.defect_items(bad)
        self.assertEqual(items[0]['problem_id'], 1)
        self.assertEqual(items[0]['source'], 'acceptance')


class UpdateWholeProblemAndOverridesTests(TestCase):
    """update_olympiad_reference: конфликт в подпунктах — задача не обновляется целиком;
    правка человека из reference_overrides не затирается новой версией эталона."""

    def setUp(self):
        from problems.tests import test_import_reference_engine2 as eng
        self.eng = eng
        self.base = eng._EngineBase(methodName='run')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)

    def write(self, name, rows):
        path = os.path.join(self.base.tmp, name)
        _write_jsonl(path, rows)
        return path

    def update(self, journal, old, new, *extra):
        call_command('update_olympiad_reference', '--olympiad', self.eng.ENTR, '--journal', journal,
                     '--old', old, '--new', new, '--old-digitized', self.base.dig, '--new-digitized',
                     self.base.dig, '--out-dir', self.base.tmp, '--apply', '--yes-i-have-owner-approval',
                     *extra, stdout=self.eng._quiet())

    def test_parts_conflict_blocks_whole_problem(self):
        eng = self.eng
        text = eng.LONG + '\n\n1) Найдите выручку\n\n2) Найдите прибыль'
        old = [eng._r(1, text, parts=[{'label': '1', 'text': 'Найдите выручку'},
                                      {'label': '2', 'text': 'Найдите прибыль'}], answer='1) 10 2) 5')]
        journal = self.base.apply(old)
        p = Problem.objects.get(source_references__problem_number=f'{eng.EV}:1')
        new = [eng._r(1, eng.LONG + '\n\n1) Найдите выручку', parts=[{'label': '1', 'text': 'Найдите выручку'}],
                      answer='1) 10', title='Новый заголовок')]
        self.update(journal, self.write('o.jsonl', old), self.write('n.jsonl', new))
        p.refresh_from_db()
        self.assertEqual(p.parts.count(), 2)
        self.assertEqual(ProblemVersion.objects.filter(problem=p).count(), 0)
        self.assertNotEqual(p.title, 'Новый заголовок')

    def test_override_survives_new_version(self):
        eng = self.eng
        ov = self.write('ov.jsonl', [{'ref_key': f'{eng.EV}:1', 'action': 'edit',
                                      'fields': {'statement': 'Текст, исправленный человеком.'}}])
        old = [eng._r(1, eng.LONG)]
        old_path = self.write('o.jsonl', old)
        queue = os.path.join(self.base.dig, 'reference_problems_v2.jsonl')
        _write_jsonl(queue, old)
        with open(os.path.join(self.base.out, 'bank_candidates.json'), 'w', encoding='utf-8') as h:
            json.dump({'meta': {}, 'candidates': {}}, h)
        call_command('import_olympiad_reference', '--olympiad', eng.ENTR, '--queue', queue, '--digitized',
                     self.base.dig, '--out-dir', self.base.out, '--no-katex', '--bundle-date', '20261029',
                     '--overrides', ov, '--apply', '--yes-i-have-owner-approval', stdout=eng._quiet())
        journal = os.path.join(self.base.out, sorted(f for f in os.listdir(self.base.out)
                                                     if f.startswith('import_') and 'dryrun' not in f)[-1])
        p = Problem.objects.get(source_references__problem_number=f'{eng.EV}:1')
        self.assertEqual(p.statement, 'Текст, исправленный человеком.')
        new = [eng._r(1, eng.LONG + ' Новое предложение эталона.', answer='43')]
        self.update(journal, old_path, self.write('n.jsonl', new), '--overrides', ov)
        p.refresh_from_db()
        self.assertEqual(p.statement, 'Текст, исправленный человеком.')
        self.assertEqual(p.answer, '43')

