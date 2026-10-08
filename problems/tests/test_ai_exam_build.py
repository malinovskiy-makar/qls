"""Экзамен для ИИ: сейф, приём разметки, сборка (problems/ai_exam/build.py).

Кандидаты и выгрузки выдуманные; к базе тесты не обращаются.
"""
import json
import os
import shutil
import tempfile
from collections import Counter

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from problems.ai_exam import build

SEED = 20261007
SECTIONS = ('Микро', 'Макро', 'Финансы')


def candidates(per_chunk=58, chunks=4):
    """Выдуманные кандидаты: блоки по кругу 3:2:1 внутри каждой пачки."""
    rows, pk = [], 1000
    pattern = ('Микро', 'Микро', 'Микро', 'Макро', 'Макро', 'Финансы')
    for chunk in range(1, chunks + 1):
        for n in range(1, per_chunk + 1):
            pk += 1
            rows.append({'id': pk, 'section': pattern[n % len(pattern)],
                         'topic': 'Тема', 'level': 'средняя', 'difficulty': 3,
                         'statement_hash': 'h%d' % pk, 'chunk': chunk, 'n': n, 'seed': SEED,
                         'asks': [{'part_id': None, 'label': '', 'bank_answer': '5',
                                   'value': '5', 'unit': '', 'percent': False,
                                   'kind': 'exact'}]})
    return rows


def ok_row(pk, value='5', percent=False):
    return {'id': pk, 'verdict': 'ok', 'reason': '', 'comment': '',
            'asks': [{'part_id': None, 'skip': False,
                      'values': [{'label': '', 'value': value, 'unit': '',
                                  'percent': percent, 'tol': ''}]}]}


def payload(rows, reviewer='Anna', chunk=1, exported_at='2026-10-08T10:00:00Z'):
    return {'format': 'ai_exam_review/2', 'seed': SEED, 'chunk': chunk,
            'reviewer': reviewer, 'exported_at': exported_at, 'rows': rows}


def hashes(cands):
    return {c['id']: c['statement_hash'] for c in cands}


class SafeTests(SimpleTestCase):
    def test_forty_from_chunks_one_to_three_in_proportion(self):
        cands = candidates()
        info = build.mark_safe(cands, SEED, '2026-10-08')
        chunk_of = {c['id']: c['chunk'] for c in cands}
        self.assertEqual(len(info['ids']), 40)
        self.assertEqual(len(set(info['ids'])), 40)
        self.assertTrue(all(chunk_of[pk] in (1, 2, 3) for pk in info['ids']))
        # В пачках 1–3: Микро 87, Макро 60, Финансы 27 из 174 → 20,00 / 13,79 / 6,21;
        # наибольший остаток отдаёт последнее место Макро.
        sizes = Counter(c['section'] for c in cands if c['chunk'] != 4)
        self.assertEqual(dict(sizes), {'Микро': 87, 'Макро': 60, 'Финансы': 27})
        self.assertEqual(info['by_section'], {'Микро': 20, 'Макро': 14, 'Финансы': 6})
        section_of = {c['id']: c['section'] for c in cands}
        self.assertEqual(Counter(section_of[pk] for pk in info['ids']),
                         Counter(info['by_section']))

    def test_ids_are_in_hash_order_and_repeatable(self):
        cands = candidates()
        first = build.mark_safe(cands, SEED, '2026-10-08')
        again = build.mark_safe(list(reversed(cands)), SEED, '2026-10-09')
        self.assertEqual(first['ids'], again['ids'])
        self.assertEqual(first['ids'], sorted(first['ids'], key=lambda pk: build.safe_hash(SEED, pk)))
        self.assertNotEqual(first['ids'], build.mark_safe(cands, SEED + 1, '')['ids'])

    def test_largest_remainder(self):
        self.assertEqual(build.largest_remainder({'a': 1, 'b': 1, 'c': 1}, 2),
                         {'a': 1, 'b': 1, 'c': 0})
        self.assertEqual(sum(build.largest_remainder({'a': 7, 'b': 3}, 40).values()), 40)


class MarkSafeCommandTests(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='qls_exam_build_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        with open(os.path.join(self.dir, 'candidates.jsonl'), 'w', encoding='utf-8') as fh:
            for row in candidates():
                fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    def _safe(self):
        with open(os.path.join(self.dir, 'safe_candidates.json'), encoding='utf-8') as fh:
            return json.load(fh)

    def test_written_once_without_force(self):
        call_command('ai_exam_build', '--mark-safe', '--dir', self.dir, stdout=open(os.devnull, 'w'))
        first = self._safe()
        self.assertEqual(first['seed'], SEED)
        self.assertEqual(len(first['ids']), 40)
        with self.assertRaises(CommandError):
            call_command('ai_exam_build', '--mark-safe', '--seed', '1', '--dir', self.dir,
                         stdout=open(os.devnull, 'w'))
        self.assertEqual(self._safe(), first)
        call_command('ai_exam_build', '--mark-safe', '--seed', '1', '--force', '--dir', self.dir,
                     stdout=open(os.devnull, 'w'))
        self.assertEqual(self._safe()['seed'], 1)


class AcceptTests(SimpleTestCase):
    def setUp(self):
        self.cands = candidates()
        self.first = self.cands[0]['id']

    def accept(self, files, fresh=None):
        return build.accept(self.cands, files, fresh if fresh is not None else hashes(self.cands))

    def test_older_export_of_same_reviewer_and_chunk_is_not_read(self):
        old = payload([ok_row(self.first)], reviewer='Anna',
                      exported_at='2026-10-08T09:00:00Z')
        new = payload([dict(ok_row(self.first), verdict='bad', reason='statement')],
                      reviewer='  anna ', exported_at='2026-10-08T12:00:00Z')
        result = self.accept([{'name': 'b_old.json', 'payload': old},
                              {'name': 'a_new.json', 'payload': new}])
        self.assertEqual(result['read'], ['a_new.json'])
        self.assertEqual(result['stale'], ['b_old.json'])
        self.assertEqual(result['status'][self.first], build.BAD)

    def test_two_reviewers_disagree_is_conflict(self):
        result = self.accept([
            {'name': 'a.json', 'payload': payload([ok_row(self.first, '5')], reviewer='Anna')},
            {'name': 'b.json', 'payload': payload([ok_row(self.first, '6')], reviewer='Boris')}])
        self.assertEqual(result['status'][self.first], build.CONFLICT)
        self.assertNotIn(self.first, result['good'])
        self.assertEqual({who for who, _v, _r in result['detail'][self.first]},
                         {'Anna', 'Boris'})

    def test_ok_against_bad_is_conflict_not_last_wins(self):
        result = self.accept([
            {'name': 'a.json', 'payload': payload([ok_row(self.first)], reviewer='Anna',
                                                  exported_at='2026-10-08T09:00:00Z')},
            {'name': 'b.json', 'payload': payload(
                [dict(ok_row(self.first), verdict='bad', reason='other')], reviewer='Boris',
                exported_at='2026-10-08T23:00:00Z')}])
        self.assertEqual(result['status'][self.first], build.CONFLICT)

    def test_two_reviewers_agree_is_good_with_both(self):
        result = self.accept([
            {'name': 'a.json', 'payload': payload([ok_row(self.first, '5')], reviewer='Anna')},
            {'name': 'b.json', 'payload': payload([ok_row(self.first, '5,0')], reviewer='Boris')}])
        self.assertEqual(result['status'][self.first], build.GOOD)
        self.assertEqual(result['good'][self.first]['reviewers'], ['Anna', 'Boris'])

    def test_changed_statement_excludes(self):
        fresh = hashes(self.cands)
        fresh[self.first] = 'другой'
        second = self.cands[1]['id']
        del fresh[second]
        result = self.accept([{'name': 'a.json', 'payload': payload(
            [ok_row(self.first), ok_row(second)])}], fresh)
        self.assertEqual(result['status'][self.first], build.HASH_CHANGED)
        self.assertEqual(result['status'][second], build.HASH_CHANGED)
        self.assertEqual(result['good'], {})

    def test_bad_row_does_not_drop_neighbours(self):
        second = self.cands[1]['id']
        rows = [dict(ok_row(self.first), verdict='может быть'), ok_row(second)]
        result = self.accept([{'name': 'a.json', 'payload': payload(rows)},
                              {'name': 'junk.json', 'payload': {'format': 'чужой'}},
                              {'name': 'broken.json', 'error': 'не читается'}])
        self.assertEqual(result['status'][second], build.GOOD)
        self.assertEqual(result['status'][self.first], build.UNREVIEWED)
        self.assertEqual([c['kind'] for c in result['complaints']], ['unknown_verdict'])
        self.assertEqual([name for name, _e in result['not_review']], ['junk.json', 'broken.json'])

    def test_categories_sum_to_candidates(self):
        ids = [c['id'] for c in self.cands]
        rows_a = [ok_row(ids[0]), dict(ok_row(ids[1]), verdict='skip'),
                  dict(ok_row(ids[2]), verdict='bad', reason='statement'), ok_row(ids[3])]
        fresh = hashes(self.cands)
        fresh[ids[3]] = 'правили'
        result = self.accept([
            {'name': 'a.json', 'payload': payload(rows_a, reviewer='Anna')},
            {'name': 'b.json', 'payload': payload([ok_row(ids[0], '7')], reviewer='Boris')}],
            fresh)
        counts = Counter(result['status'].values())
        self.assertEqual(counts[build.CONFLICT], 1)
        self.assertEqual(counts[build.SKIP], 1)
        self.assertEqual(counts[build.BAD], 1)
        self.assertEqual(counts[build.HASH_CHANGED], 1)
        self.assertEqual(sum(counts[c] for c in build.CATEGORIES), len(self.cands))


class AssembleTests(SimpleTestCase):
    def setUp(self):
        self.cands = candidates()
        self.safe = build.mark_safe(self.cands, SEED, '2026-10-08')['ids']

    def run_build(self, ok_ids):
        by_chunk = {}
        for c in self.cands:
            if c['id'] in ok_ids:
                by_chunk.setdefault(c['chunk'], []).append(ok_row(c['id']))
        files = [{'name': 'chunk%d.json' % k, 'payload': payload(rows, chunk=k)}
                 for k, rows in by_chunk.items()]
        accepted = build.accept(self.cands, files, hashes(self.cands))
        built = build.assemble(self.cands, self.safe, accepted['good'])
        return accepted, built, build.invariants(self.cands, self.safe, accepted, built)

    def test_final_thirty_plus_hundred_twenty_without_overlap(self):
        accepted, built, inv = self.run_build({c['id'] for c in self.cands})
        self.assertTrue(built['final'])
        self.assertEqual(len(built['safe']), 30)
        self.assertEqual(len(built['work']), 120)
        self.assertEqual([r['id'] for r in built['safe']], self.safe[:30])
        work = {r['id'] for r in built['work']}
        # Годные кандидаты сейфа сверх тридцати в работу не идут.
        self.assertFalse(work & set(self.safe))
        self.assertEqual(inv['сейф ∩ рабочий'], 0)
        self.assertEqual(inv['повторов id'], 0)
        self.assertEqual(inv['сумма категорий'], len(self.cands))
        # Порядок рабочего — (пачка, номер), резерв последним.
        order = [(r['chunk'], r['n']) for r in built['work']]
        self.assertEqual(order, sorted(order))
        self.assertTrue(all(r['chunk'] in (1, 2, 3) for r in built['work']))

    def test_short_is_draft_without_safe_candidates(self):
        ok = {c['id'] for c in self.cands if c['chunk'] == 1}
        accepted, built, inv = self.run_build(ok)
        self.assertFalse(built['final'])
        self.assertEqual(built['safe'], [])
        draft = {r['id'] for r in built['draft']}
        self.assertTrue(draft)
        self.assertFalse(draft & set(self.safe))
        self.assertEqual(draft, ok - set(self.safe))
        self.assertEqual(inv['safe_candidates ∩ черновик'], 0)
        report = build.build_report(self.cands, {'seed': SEED, 'ids': self.safe},
                                    accepted, built, inv, '2026-10-08')
        self.assertIn('ЧЕРНОВИК', report)
        self.assertNotIn('НУЖНО РЕШЕНИЕ ВЛАДЕЛЬЦА', report)

    def test_owner_decision_when_safe_short_after_full_review(self):
        # Пачки 1–3 проверены целиком, но кандидаты сейфа почти все «не годится».
        files = []
        for k in (1, 2, 3):
            rows = [ok_row(c['id']) if c['id'] not in self.safe[:15]
                    else dict(ok_row(c['id']), verdict='bad', reason='statement')
                    for c in self.cands if c['chunk'] == k]
            files.append({'name': 'c%d.json' % k, 'payload': payload(rows, chunk=k)})
        accepted = build.accept(self.cands, files, hashes(self.cands))
        built = build.assemble(self.cands, self.safe, accepted['good'])
        inv = build.invariants(self.cands, self.safe, accepted, built)
        self.assertFalse(built['final'])
        report = build.build_report(self.cands, {'seed': SEED, 'ids': self.safe},
                                    accepted, built, inv, '2026-10-08')
        self.assertIn('НУЖНО РЕШЕНИЕ ВЛАДЕЛЬЦА', report)

    def test_empty_reviews(self):
        accepted, built, inv = self.run_build(set())
        self.assertFalse(built['final'])
        self.assertEqual(Counter(accepted['status'].values())[build.UNREVIEWED], len(self.cands))
        report = build.build_report(self.cands, {'seed': SEED, 'ids': self.safe},
                                    accepted, built, inv, '2026-10-08')
        self.assertIn('Разметки нет', report)
