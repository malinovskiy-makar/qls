"""Команда `import_problem_attributes`: сухой прогон, запись двух полей,
обратимый снимок, идемпотентность, включение групп фильтра данными."""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.http import QueryDict
from django.test import TestCase

from catalog import filters
from problems.models import Problem
from problems.tests.factories import make_problem, make_topic


class ImportProblemAttributesTests(TestCase):
    def setUp(self):
        self.topic = make_topic('Эластичность')
        self.p1 = make_problem('Первая задача $Q=2P$.', topic=self.topic,
                               solution='Решение первой.', answer='42')
        self.p2 = make_problem('Вторая задача.', topic=self.topic)
        self.p3 = make_problem('Третья, не в файле.', topic=self.topic)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _file(self, rows):
        path = os.path.join(self.tmp.name, 'attrs.jsonl')
        with open(path, 'w', encoding='utf-8') as fh:
            for row in rows:
                fh.write((row if isinstance(row, str) else json.dumps(row, ensure_ascii=False)) + '\n')
        return path

    def _run(self, path, apply=False):
        out = StringIO()
        call_command('import_problem_attributes', path, apply=apply,
                     snapshot_dir=os.path.join(self.tmp.name, 'undo'), stdout=out)
        return out.getvalue()

    def _rows(self):
        return [{'id': self.p1.pk, 'character': 'quant', 'features': ['graph']},
                {'id': self.p2.pk, 'features': ['table', 'graph', 'graph']}]

    def test_dry_run_changes_nothing(self):
        out = self._run(self._file(self._rows()))
        self.assertIn('Изменится: 2 (характер: 1, особенности: 2)', out)
        self.assertIn('Сухой прогон', out)
        self.p1.refresh_from_db()
        self.assertEqual((self.p1.character, self.p1.features), ('', []))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, 'undo')))

    def test_apply_changes_exactly_the_listed_problems_and_only_two_fields(self):
        out = self._run(self._file(self._rows()), apply=True)
        self.assertIn('Записано: 2 задач', out)
        for problem in (self.p1, self.p2, self.p3):
            problem.refresh_from_db()
        self.assertEqual((self.p1.character, self.p1.features), ('quant', ['graph']))
        self.assertEqual((self.p2.character, self.p2.features), ('', ['graph', 'table']))
        self.assertEqual((self.p3.character, self.p3.features), ('', []))
        self.assertEqual((self.p1.statement, self.p1.solution, self.p1.answer),
                         ('Первая задача $Q=2P$.', 'Решение первой.', '42'))
        self.assertEqual(Problem.objects.count(), 3)
        # Снимок старых значений — в формате входа, им же откатывается.
        undo_dir = os.path.join(self.tmp.name, 'undo')
        files = os.listdir(undo_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(undo_dir, files[0]), encoding='utf-8') as fh:
            snapshot = [json.loads(line) for line in fh]
        self.assertEqual(snapshot, [{'id': self.p1.pk, 'character': '', 'features': []},
                                    {'id': self.p2.pk, 'character': '', 'features': []}])
        self._run(self._file(snapshot), apply=True)
        self.p1.refresh_from_db()
        self.assertEqual((self.p1.character, self.p1.features), ('', []))

    def test_second_dry_run_is_zero(self):
        path = self._file(self._rows())
        self._run(path, apply=True)
        out = self._run(path)
        self.assertIn('Изменится: 0', out)
        self.assertIn('без изменений: 2', out)

    def test_groups_and_filter_light_up_after_import(self):
        keys = filters.field_keys(filters.build(
            filters.base_queryset('catalog'), filters.parse(QueryDict('')))[1])
        self.assertNotIn('character', keys)
        self._run(self._file([{'id': self.p1.pk, 'character': 'quant'},
                              {'id': self.p2.pk, 'character': 'quant'}]), apply=True)
        ctx = filters.build(filters.base_queryset('catalog'),
                            filters.parse(QueryDict('')))[1]
        group = next(g for g in ctx['groups'] if g['key'] == 'character')
        self.assertEqual(group['label'], 'Характер задачи')
        self.assertEqual([(o['label'], o['count']) for o in group['options']],
                         [('Количественная', 2)])
        resp = self.client.get('/catalog/', {'character': 'quant'})
        self.assertEqual({c['problem'].pk for c in resp.context['cards']},
                         {self.p1.pk, self.p2.pk})

    def test_bad_line_fails_alone_others_apply(self):
        out = self._run(self._file([
            {'id': self.p1.pk, 'character': 'quant'},
            {'id': self.p2.pk, 'character': 'hard'},
            {'id': 987654321, 'features': ['graph']},
            'это не json',
            {'id': self.p3.pk, 'features': ['graph', 'chart']},
        ]), apply=True)
        self.assertIn('с ошибками: 3', out)
        self.assertIn('не найдено id: 1', out)
        self.assertIn("неизвестный character 'hard'", out)
        self.assertIn('неизвестные features chart', out)
        self.assertIn('Записано: 1 задач', out)
        for problem in (self.p1, self.p2, self.p3):
            problem.refresh_from_db()
        self.assertEqual(self.p1.character, 'quant')
        self.assertEqual((self.p2.character, self.p3.features), ('', []))
