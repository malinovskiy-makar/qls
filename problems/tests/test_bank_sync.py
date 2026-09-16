"""Синхронизация банка обновлением: export → искажение → apply (ADR 0107).

«Вторая база» в тестах — та же тестовая база после искажения: пакет снят с
правильного состояния, потом состояние портится так, как оно отстаёт на бою
(другой заголовок, другой тег, лишний подпункт, снятый флаг темы), и apply
обязан вернуть ровно пакет.
"""
import shutil
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems import bank_sync
from problems.models import (Feature, Hint, Problem, ProblemFeature, ProblemFigure,
                             ProblemPart, Tag, Topic)
from problems.tests.factories import link_source, make_problem, make_source, make_topic


class BankSyncTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.runs = 0
        self.canon = make_topic('Эластичность', is_canonical=True)
        self.tag = Tag.objects.create(name='Эластичность спроса', slug='el', kind='canonical')
        self.legacy = Tag.objects.create(name='монополия', slug='mono', kind='legacy')
        self.feature = Feature.objects.create(key='graph', label='График', counted_by='code')
        source = make_source('ILE / iloveeconomics.ru')
        self.problems = []
        for i in range(3):
            p = make_problem(statement='Условие %d: $Q = %d$' % (i, i), title='Задача %d' % i,
                             answer=str(i), search_queries=['спрос', i])
            p.topics.add(self.canon)
            p.tags.add(self.tag)
            ProblemPart.objects.create(problem=p, label='а', order=0, statement='Найдите Q',
                                       answer='1', points=Decimal('1.5'))
            ProblemPart.objects.create(problem=p, label='б', order=1, statement='Найдите P', answer='2')
            link_source(p, source, url='https://iloveeconomics.ru/z/%d' % i)
            Hint.objects.create(problem=p, order=1, text='Подсказка %d' % i)
            ProblemFeature.objects.create(problem=p, feature=self.feature, source='code')
            self.problems.append(p)
        ProblemFigure.objects.create(problem=self.problems[0], tikz_hash='a' * 64, tikz_source='%',
                                     image_data=b'\x89PNG\x00\x01', content_type='image/png')
        self.ids = [p.id for p in self.problems]

    # ── помощники ────────────────────────────────────────────────────────
    def export(self, name='pkg', fields=''):
        out = self.tmp / name
        ids_file = self.tmp / (name + '_ids.txt')
        ids_file.write_text(' '.join(map(str, self.ids)), encoding='utf-8')
        call_command('bank_sync_export', '--ids-file', str(ids_file), '--out', str(out),
                     '--fields', fields, stdout=StringIO())
        return out

    def apply(self, package, *args):
        self.runs += 1
        report = self.tmp / ('report_%d' % self.runs)
        out = StringIO()
        call_command('bank_sync_apply', '--package', str(package), '--report', str(report),
                     *args, stdout=out)
        return report, out.getvalue()

    def state(self):
        """Всё, что трогает синхронизация, вместе с pk строк и справочниками."""
        rows = list(bank_sync.collect(self.ids, list(bank_sync.ALL_FIELDS), bank_sync.ref_maps()))
        refs = [list(model.objects.order_by('pk').values()) for model in (Topic, Tag, Feature)]
        return rows, refs

    def distort(self):
        a, b, c = self.problems
        Problem.objects.filter(pk=a.pk).update(title='Обрубок', statement='Искажено')
        b.tags.remove(self.tag)
        b.tags.add(self.legacy)
        ProblemPart.objects.create(problem=c, label='в', order=2, statement='лишний', answer='3')
        ProblemPart.objects.filter(problem=b, order=0).update(answer='999')
        ProblemFigure.objects.filter(problem=a).delete()
        Topic.objects.filter(pk=self.canon.pk).update(is_canonical=False)

    # ── тесты ────────────────────────────────────────────────────────────
    def test_apply_restores_package_exactly(self):
        package = self.export()
        self.distort()
        _report, out = self.apply(package, '--apply')
        self.assertTrue('Снимок для отката' in out, out)
        again = self.export('again')
        self.assertEqual((package / 'problems.jsonl').read_text(encoding='utf-8'),
                         (again / 'problems.jsonl').read_text(encoding='utf-8'))
        self.assertEqual((package / 'refs.json').read_text(encoding='utf-8'),
                         (again / 'refs.json').read_text(encoding='utf-8'))
        b = self.problems[1]
        self.assertEqual(list(b.tags.values_list('name', flat=True)), ['Эластичность спроса'])
        self.assertFalse(ProblemPart.objects.filter(problem=self.problems[2], order=2).exists())

    def test_dry_run_writes_nothing(self):
        package = self.export()
        self.distort()
        before = self.state()
        report, out = self.apply(package)
        self.assertEqual(before, self.state())
        self.assertTrue('сухой прогон' in out, out)
        text = (report / 'REPORT.md').read_text(encoding='utf-8')
        self.assertTrue('| title | 1 |' in text, 'в отчёте нет счётчика заголовка')
        self.assertFalse(list(report.glob('snapshot_*.json')), 'сухой прогон оставил снимок')

    def test_second_apply_changes_nothing(self):
        package = self.export()
        self.distort()
        self.apply(package, '--apply')
        report, out = self.apply(package, '--apply')
        self.assertTrue('Изменений нет.' in out, out)
        self.assertFalse(list(report.glob('snapshot_*.json')), 'пустой прогон оставил снимок')

    def test_revert_returns_state_byte_for_byte(self):
        package = self.export()
        self.distort()
        before = self.state()
        report, _out = self.apply(package, '--apply')
        self.assertNotEqual(before, self.state())
        snapshot = next(report.glob('snapshot_*.json'))
        call_command('bank_sync_apply', '--revert', str(snapshot), stdout=StringIO())
        self.assertEqual(before, self.state())

    def test_fields_title_changes_only_title(self):
        package = self.export()
        self.distort()
        self.apply(package, '--apply', '--fields', 'title')
        a = Problem.objects.get(pk=self.problems[0].pk)
        self.assertEqual(a.title, 'Задача 0')
        self.assertEqual(a.statement, 'Искажено')
        self.assertTrue(self.problems[1].tags.filter(pk=self.legacy.pk).exists())
        self.assertFalse(Topic.objects.get(pk=self.canon.pk).is_canonical)

    def test_part_with_dependents_is_kept_and_reported(self):
        package = self.export()
        c = self.problems[2]
        extra = ProblemPart.objects.create(problem=c, label='в', order=2, answer='3')
        Hint.objects.create(problem=c, part=extra, order=5, text='к лишнему подпункту')
        report, out = self.apply(package, '--apply', '--fields', 'parts')
        self.assertTrue(ProblemPart.objects.filter(pk=extra.pk).exists())
        self.assertTrue('не удалено 1' in out, out)
        text = (report / 'REPORT.md').read_text(encoding='utf-8')
        self.assertTrue('problems.Hint' in text, 'в отчёте не названа ссылка')

    def test_problem_missing_in_db_is_not_created(self):
        package = self.export()
        Problem.objects.filter(pk=self.problems[2].pk).delete()
        _report, out = self.apply(package, '--apply')
        self.assertTrue('нет в базе: 1' in out, out)
        self.assertFalse(Problem.objects.filter(pk=self.problems[2].pk).exists())

    def test_revert_keeps_edit_made_after_sync(self):
        package = self.export()
        self.distort()
        report, _out = self.apply(package, '--apply')
        Problem.objects.filter(pk=self.problems[0].pk).update(title='Правка редактора')
        snapshot = next(report.glob('snapshot_*.json'))
        call_command('bank_sync_apply', '--revert', str(snapshot), stdout=StringIO())
        a = Problem.objects.get(pk=self.problems[0].pk)
        self.assertEqual(a.title, 'Правка редактора')
        self.assertEqual(a.statement, 'Искажено')
        revert_md = snapshot.with_name(snapshot.stem + '_REVERT.md').read_text(encoding='utf-8')
        self.assertTrue('поле изменили после синхронизации' in revert_md, 'конфликт не назван')

    def test_corrupted_package_is_rejected(self):
        package = self.export()
        path = package / 'problems.jsonl'
        path.write_text(path.read_text(encoding='utf-8').replace('Задача 0', 'Задача X'),
                        encoding='utf-8')
        with self.assertRaises(CommandError):
            self.apply(package)
