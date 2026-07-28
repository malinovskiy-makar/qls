# -*- coding: utf-8 -*-
"""Тесты инфраструктуры ручного ревью внешнего вида (ветка feat/review-snapshots).

Три слоя:
- модель ReviewVerdict (уникальность пары задача+ревьюер);
- import_review_verdicts (идемпотентность, обновление свежим, валидация);
- export_review_bundle (снимок = боевой рендер: всё раскрыто, KaTeX локальный,
  манифест с категориями, зафлагованные задачи не попадают).
"""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.test import TestCase

from problems.models import Problem, ProblemPart, ReviewVerdict
from problems.review_categories import BUNDLE_FORMAT, CATEGORY_KEYS, VERDICTS_FORMAT
from problems.tests.factories import link_source, make_problem, make_source


def write_verdicts_file(tmpdir, verdicts, reviewer='Тест', **extra):
    """Файл вердиктов ровно в том виде, в каком его скачивает reviewer.html."""
    payload = {
        'format': VERDICTS_FORMAT,
        'bundle_id': 'test_bundle',
        'reviewer': reviewer,
        'exported_at': '2026-07-21T12:00:00.000Z',
        'count': len(verdicts),
        'verdicts': verdicts,
    }
    payload.update(extra)
    path = Path(tmpdir) / 'verdicts.json'
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return path


class ReviewVerdictModelTests(TestCase):
    def test_one_verdict_per_problem_and_reviewer(self):
        p = make_problem()
        ReviewVerdict.objects.create(problem=p, category='perfect', reviewer='К')
        with self.assertRaises(IntegrityError):
            ReviewVerdict.objects.create(problem=p, category='junk', reviewer='К')

    def test_different_reviewers_can_both_vote(self):
        p = make_problem()
        ReviewVerdict.objects.create(problem=p, category='perfect', reviewer='К')
        ReviewVerdict.objects.create(problem=p, category='junk', reviewer='М')
        self.assertEqual(p.review_verdicts.count(), 2)


class ImportVerdictsTests(TestCase):
    def setUp(self):
        self.p1 = make_problem(statement='Задача один $Q=10$.')
        self.p2 = make_problem(statement='Задача два.')

    def _import(self, path, **opts):
        out = StringIO()
        call_command('import_review_verdicts', str(path), stdout=out, **opts)
        return out.getvalue()

    def test_import_creates_and_skips_unknown_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'category': 'perfect',
                 'comment': '', 'at': '2026-07-21T10:00:00.000Z'},
                {'problem_id': self.p2.id, 'category': 'broken_formula',
                 'comment': 'слиплись дроби', 'at': '2026-07-21T10:01:00.000Z'},
                {'problem_id': 999999, 'category': 'junk', 'comment': '', 'at': ''},
            ])
            out = self._import(path)
        self.assertEqual(ReviewVerdict.objects.count(), 2)
        v2 = ReviewVerdict.objects.get(problem=self.p2)
        self.assertEqual(v2.category, 'broken_formula')
        self.assertEqual(v2.comment, 'слиплись дроби')
        self.assertEqual(v2.reviewer, 'Тест')
        self.assertEqual(v2.created_at.isoformat(), '2026-07-21T10:01:00+00:00')
        self.assertIn('новых 2', out)
        self.assertIn('пропущено (нет такой задачи) 1', out)
        # сводка по категориям — человеческими названиями
        self.assertIn('Сломанная формула: 1', out)

    def test_reimport_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'category': 'perfect',
                 'comment': '', 'at': '2026-07-21T10:00:00.000Z'},
            ])
            self._import(path)
            out = self._import(path)
        self.assertEqual(ReviewVerdict.objects.count(), 1)
        self.assertIn('без изменений 1', out)

    def test_newer_verdict_updates_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'category': 'perfect',
                 'comment': '', 'at': '2026-07-21T10:00:00.000Z'}]))
            out = self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'category': 'disputed',
                 'comment': 'передумал', 'at': '2026-07-21T11:00:00.000Z'}]))
        self.assertEqual(ReviewVerdict.objects.count(), 1)
        v = ReviewVerdict.objects.get()
        self.assertEqual((v.category, v.comment), ('disputed', 'передумал'))
        self.assertIn('обновлено 1', out)

    def test_reviewer_option_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'category': 'perfect',
                 'comment': '', 'at': ''}]), reviewer='Ксения')
        self.assertEqual(ReviewVerdict.objects.get().reviewer, 'Ксения')

    def test_unknown_category_rejects_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'category': 'nonsense',
                 'comment': '', 'at': ''}])
            with self.assertRaisesMessage(CommandError, 'Неизвестные категории'):
                self._import(path)
        self.assertEqual(ReviewVerdict.objects.count(), 0)

    def test_wrong_format_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [], format='something-else')
            with self.assertRaisesMessage(CommandError, 'Неожиданный формат'):
                self._import(path)


class ExportBundleTests(TestCase):
    def setUp(self):
        self.source = make_source(name='Тестовый сборник')
        self.visible = make_problem(
            statement='Спрос $Q_d = 100 - P$. Найдите равновесие.',
            answer='$P^* = 50$', solution='Приравниваем $100-P=P$, отсюда $P=50$.')
        ProblemPart.objects.create(problem=self.visible, label='а',
                                   statement='Найдите $P^*$.', answer='50', order=1)
        link_source(self.visible, self.source)
        self.flagged = make_problem(statement='Зафлагованная задача.', flagged=True)
        link_source(self.flagged, self.source)

    def _export(self, out_dir, **opts):
        out = StringIO()
        call_command('export_review_bundle', out=str(out_dir), stdout=out, **opts)
        return out.getvalue()

    def test_bundle_snapshot_is_offline_and_expanded(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / 'bundle_x'
            self._export(out_dir, source_id=self.source.id)

            # манифест: только видимая задача, категории на месте
            manifest = json.loads((out_dir / 'manifest.json').read_text())
            self.assertEqual(manifest['format'], BUNDLE_FORMAT)
            self.assertEqual(manifest['count'], 1)
            self.assertEqual([p['id'] for p in manifest['problems']],
                             [self.visible.id])
            self.assertEqual([c['key'] for c in manifest['categories']],
                             CATEGORY_KEYS)
            self.assertEqual(manifest['problems'][0]['source'], 'Тестовый сборник')

            # оболочка и js-зеркало манифеста
            self.assertTrue((out_dir / 'reviewer.html').exists())
            self.assertIn('window.REVIEW_MANIFEST',
                          (out_dir / 'manifest.js').read_text())

            # снимок: боевой HTML, но офлайн и всё раскрыто
            snap = (out_dir / 'snapshots' / f'{self.visible.id}.html').read_text()
            self.assertIn('review-snapshot-overrides', snap)
            self.assertNotIn('cdn.jsdelivr.net', snap)
            self.assertIn('../assets/vendor/katex/katex.min.css', snap)
            self.assertIn('Приравниваем', snap)          # решение в снимке
            self.assertIn('Найдите $P^*$', snap)         # подпункт в снимке
            self.assertNotIn('href="/static/', snap)
            self.assertNotIn('src="/static/', snap)

            # вендор KaTeX скопирован вместе со шрифтами
            self.assertTrue((out_dir / 'assets/vendor/katex/katex.min.js').exists())
            self.assertTrue(list((out_dir / 'assets/vendor/katex/fonts').glob('*.woff2')))

            # зафлагованной задачи в пакете нет
            self.assertFalse((out_dir / 'snapshots' / f'{self.flagged.id}.html').exists())

    def test_ids_file_keeps_order_and_drops_invisible(self):
        second = make_problem(statement='Вторая видимая задача.')
        with tempfile.TemporaryDirectory() as tmp:
            ids_file = Path(tmp) / 'ids.txt'
            ids_file.write_text(
                f'{second.id}\n{self.flagged.id}\n{self.visible.id}\n')
            out_dir = Path(tmp) / 'bundle_ids'
            out = self._export(out_dir, ids_file=str(ids_file))
            manifest = json.loads((out_dir / 'manifest.json').read_text())
        # порядок файла сохранён, зафлагованная выброшена с предупреждением
        self.assertEqual([p['id'] for p in manifest['problems']],
                         [second.id, self.visible.id])
        self.assertIn('Пропущено 1', out)

    def test_requires_exactly_one_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError):
                self._export(Path(tmp) / 'b')
