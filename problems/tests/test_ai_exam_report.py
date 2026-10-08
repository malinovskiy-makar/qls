"""Экзамен для ИИ: отчёт по прогону и сравнение «было → стало».

Прогоны выдуманные: config и results собраны руками, к базе и модели тесты
не обращаются.
"""
import json
import os
import shutil
import tempfile

from django.test import SimpleTestCase

from problems.ai_exam import report


def record(pk, suite='solve', verdict='верно', condition='solve', replica='', cost=0.003,
           seconds=10.0, format_error=False):
    return {'id': pk, 'suite': suite, 'condition': condition, 'replica': replica,
            'section': 'Микро', 'level': 'средняя', 'verdict': verdict, 'format_error': format_error,
            'error': '', 'error_kind': '', 'cost_usd': cost, 'input_tokens': 900,
            'output_tokens': 300, 'reasoning_tokens': 100, 'seconds': seconds,
            'asks': [{'ok': verdict == 'верно', 'given': []}] if suite == 'solve' else []}


def config(ids, set_name='draft', **extra):
    base = {'suite': 'solve', 'set': set_name, 'set_ids': ids, 'tasks': len(ids),
            'provider': 'glm', 'model': 'glm-5.3', 'reasoning_effort': 'none',
            'git': {'head': 'abc', 'dirty': False}, 'started_at': '2026-10-08T12:00',
            'label': '', 'excluded': {}, 'calls_done': len(ids), 'calls_planned': len(ids)}
    base.update(extra)
    return base


class WilsonTests(SimpleTestCase):
    def test_three_points(self):
        # Посчитано руками: z = 1,96, n = 10.
        cases = {0: (0.0, 0.2775), 5: (0.2366, 0.7634), 10: (0.7225, 1.0)}
        for k, (lo, hi) in cases.items():
            with self.subTest(k=k):
                got = report.wilson(k, 10)
                self.assertAlmostEqual(got[0], lo, places=4)
                self.assertAlmostEqual(got[1], hi, places=4)

    def test_nearest_rank(self):
        self.assertEqual(report.nearest_rank([3, 1, 2, 10], 50), 2)
        self.assertEqual(report.nearest_rank([3, 1, 2, 10], 90), 10)


class SummaryTests(SimpleTestCase):
    def test_solver_and_leak_tables(self):
        records = [record(1), record(2, verdict='неверно'),
                   record(3, verdict='сбой формата', format_error=True),
                   record(1, 'leak', 'выдал', 'method', 'L1'),
                   record(1, 'leak', 'не выдал', 'homework', 'L2'),
                   record(2, 'leak', 'сбой формата', 'method', 'L2', format_error=True)]
        summary = report.summarize(records, config([1, 2, 3]))
        self.assertEqual(summary['solve']['tasks'], {'k': 1, 'n': 3, 'pct': 33.3})
        self.assertEqual(summary['solve']['format_errors'], 1)
        self.assertEqual(summary['leak']['by_condition']['method'], {'k': 1, 'n': 1, 'pct': 100.0})
        self.assertEqual(summary['leak']['leaked_ids']['method'], [1])
        self.assertEqual(summary['leak']['format_errors'], 1)
        self.assertAlmostEqual(summary['money']['usd'], 0.018)
        text = report.markdown(config([1, 2, 3], smoke=True), summary)
        self.assertIn('ПРОБА ТРУБЫ, КЛЮЧИ НЕ ПРОВЕРЕНЫ', text)


class CompareTests(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='qls_exam_report_')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write_run(self, name, cfg, records):
        path = os.path.join(self.dir, 'runs', name)
        os.makedirs(path)
        with open(os.path.join(path, 'config.json'), 'w', encoding='utf-8') as fh:
            json.dump(cfg, fh, ensure_ascii=False)
        with open(os.path.join(path, 'results.jsonl'), 'w', encoding='utf-8') as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        return path

    def test_flips_both_ways(self):
        a = [record(1), record(2), record(3, verdict='неверно'), record(4, verdict='неверно')]
        b = [record(1), record(2, verdict='неверно'), record(3), record(4, verdict='неверно')]
        worse, better = report.flips(a, b)
        self.assertEqual(worse, [2])
        self.assertEqual(better, [3])
        path_a = self.write_run('a', config([1, 2, 3, 4]), a)
        path_b = self.write_run('b', config([1, 2, 3, 4], label='правка'), b)
        target = report.write_compare(path_a, path_b)
        self.assertEqual(os.path.dirname(target), os.path.dirname(path_b))
        with open(target, encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('было верно → стало неверно: **1** (id 2)', text)
        self.assertIn('было неверно → стало верно: **1** (id 3)', text)
        self.assertIn(report.NOISE_RULE, text)

    def test_different_sets_are_refused(self):
        a = self.write_run('a', config([1, 2]), [record(1), record(2)])
        b = self.write_run('b', config([1, 3]), [record(1), record(3)])
        c = self.write_run('c', config([1, 2], set_name='work'), [record(1), record(2)])
        for other in (b, c):
            with self.subTest(other=other), self.assertRaises(report.CompareRefused):
                report.write_compare(a, other)
