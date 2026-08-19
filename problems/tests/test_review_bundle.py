# -*- coding: utf-8 -*-
"""Тесты инфраструктуры ручного ревью внешнего вида.

Четыре слоя:
- категории (единственная точка правды — problems/review_categories.py);
- модель ReviewVerdict (строка на пару задача×категория, ключ bundle+задача+категория);
- import_review_verdicts (ОБА формата v1/v2, идемпотентность, валидация);
- export_review_bundle (снимок = боевой рендер: всё раскрыто, KaTeX локальный,
  манифест с категориями, зафлагованные задачи не попадают).
"""
import json
import re
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.test import TestCase

from problems.models import Problem, ProblemPart, ReviewVerdict
from problems.review_categories import (BUNDLE_FORMAT, CATEGORY_KEYS,
                                        EXCLUSIVE_KINDS, REVIEW_CATEGORIES,
                                        VERDICTS_FORMAT, VERDICTS_FORMAT_V1)
from problems.tests.factories import link_source, make_problem, make_source

REVIEWER_HTML = (Path(__file__).resolve().parents[1]
                 / 'review_bundle_assets' / 'reviewer.html')


def write_verdicts_file(tmpdir, verdicts, reviewer='Тест', name='verdicts.json', **extra):
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
    path = Path(tmpdir) / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return path


class CategoriesTests(TestCase):
    """Категории живут в manifest/коде категорий, а не в разметке оболочки."""

    def test_trash_category_declared(self):
        trash = next(c for c in REVIEW_CATEGORIES if c['key'] == 'trash')
        self.assertEqual(trash['label'], 'Гагно')
        self.assertEqual(trash['hint'], 'в мусор целиком')
        self.assertEqual(trash['kind'], 'trash')

    def test_perfect_keeps_its_hotkey(self):
        # На «1» наработана моторика 2 401 задачи — клавишу двигать нельзя.
        perfect = next(c for c in REVIEW_CATEGORIES if c['key'] == 'perfect')
        self.assertEqual(perfect['hotkey'], '1')

    def test_trash_hotkey_is_not_next_to_perfect(self):
        keys = '1234567890'
        perfect = next(c for c in REVIEW_CATEGORIES if c['key'] == 'perfect')['hotkey']
        trash = next(c for c in REVIEW_CATEGORIES if c['key'] == 'trash')['hotkey']
        self.assertGreater(abs(keys.index(perfect) - keys.index(trash)), 1)

    def test_exactly_two_exclusive_kinds_and_eight_defects(self):
        # Дефектных категорий стало восемь: 2026-08-19 к семи прежним добавлена
        # `fixed_wrong` («Починил не то») для пакетов разбора уже починенных
        # задач. Она отвечает на вопрос «что не так с ПРАВКОЙ», а не «что не
        # так с задачей», поэтому заведена отдельно от `other`.
        exclusive = [c for c in REVIEW_CATEGORIES if c['kind'] in EXCLUSIVE_KINDS]
        defects = [c for c in REVIEW_CATEGORIES if c['kind'] == 'defect']
        self.assertEqual(sorted(c['key'] for c in exclusive), ['perfect', 'trash'])
        self.assertEqual(len(defects), 8)
        self.assertIn('fixed_wrong', [c['key'] for c in defects])

    def test_hotkeys_are_unique(self):
        hot = [c['hotkey'] for c in REVIEW_CATEGORIES]
        self.assertEqual(len(hot), len(set(hot)))

    def test_shell_builds_buttons_from_manifest(self):
        """Кнопки строятся из манифеста, а подписи категорий в код не зашиты.

        Комментарии из проверки вырезаются — они как раз ОБЪЯСНЯЮТ поведение
        и обязаны называть категории по-русски.
        """
        html = REVIEWER_HTML.read_text(encoding='utf-8')
        code = re.sub(r'<!--[\s\S]*?-->', '', html)      # комментарии HTML
        code = re.sub(r'(?m)^\s*//.*$', '', code)         # комментарии JS
        self.assertIn('M.categories', code)
        self.assertIn('cats.forEach', code)
        for cat in REVIEW_CATEGORIES:
            if cat['key'] in ('perfect', 'trash'):
                continue  # эти два названы в подсказке по клавишам осознанно
            self.assertNotIn(cat['label'], code,
                             'подпись «%s» зашита в оболочку' % cat['label'])


class ReviewVerdictModelTests(TestCase):
    def test_one_row_per_bundle_problem_category(self):
        p = make_problem()
        ReviewVerdict.objects.create(bundle='b1', problem=p, category='perfect',
                                     reviewer='К')
        with self.assertRaises(IntegrityError):
            ReviewVerdict.objects.create(bundle='b1', problem=p,
                                         category='perfect', reviewer='К')

    def test_several_categories_for_one_problem(self):
        """Множественный выбор — это несколько строк с общим комментарием."""
        p = make_problem()
        for cat in ('broken_formula', 'junk', 'broken_table'):
            ReviewVerdict.objects.create(bundle='b1', problem=p, category=cat,
                                         reviewer='К', comment='всё сразу')
        self.assertEqual(p.review_verdicts.count(), 3)
        self.assertEqual({v.comment for v in p.review_verdicts.all()}, {'всё сразу'})

    def test_same_problem_in_two_bundles(self):
        p = make_problem()
        ReviewVerdict.objects.create(bundle='b1', problem=p, category='perfect')
        ReviewVerdict.objects.create(bundle='b2', problem=p, category='perfect')
        self.assertEqual(p.review_verdicts.count(), 2)


class ImportVerdictsTests(TestCase):
    def setUp(self):
        self.p1 = make_problem(statement='Задача один $Q=10$.')
        self.p2 = make_problem(statement='Задача два.')

    def _import(self, path, **opts):
        out = StringIO()
        call_command('import_review_verdicts', str(path), stdout=out, **opts)
        return out.getvalue()

    def test_import_v2_creates_and_skips_unknown_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['perfect'],
                 'comment': '', 'at': '2026-07-21T10:00:00.000Z'},
                {'problem_id': self.p2.id, 'categories': ['broken_formula'],
                 'comment': 'слиплись дроби', 'at': '2026-07-21T10:01:00.000Z'},
                {'problem_id': 999999, 'categories': ['junk'], 'comment': '', 'at': ''},
            ])
            out = self._import(path)
        self.assertEqual(ReviewVerdict.objects.count(), 2)
        v2 = ReviewVerdict.objects.get(problem=self.p2)
        self.assertEqual(v2.category, 'broken_formula')
        self.assertEqual(v2.comment, 'слиплись дроби')
        self.assertEqual(v2.reviewer, 'Тест')
        self.assertEqual(v2.bundle, 'test_bundle')
        self.assertEqual(v2.created_at.isoformat(), '2026-07-21T10:01:00+00:00')
        self.assertIn('новых 2', out)
        self.assertIn('пропущено (нет такой задачи) 1', out)
        # сводка по категориям — человеческими названиями
        self.assertIn('Сломанная формула: 1', out)

    def test_import_v1_still_understood(self):
        """2 401 вердикт по ILE лежат в v1 — формат обязан читаться как есть."""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(
                tmp,
                [{'problem_id': self.p1.id, 'category': 'perfect',
                  'comment': 'ок', 'at': '2026-07-21T10:00:00.000Z'}],
                format=VERDICTS_FORMAT_V1)
            out = self._import(path)
        v = ReviewVerdict.objects.get()
        self.assertEqual((v.category, v.comment), ('perfect', 'ок'))
        self.assertIn(VERDICTS_FORMAT_V1, out)

    def test_v1_and_v2_of_same_verdict_do_not_duplicate(self):
        """Один и тот же вердикт в двух форматах — одна строка, не две."""
        with tempfile.TemporaryDirectory() as tmp:
            self._import(write_verdicts_file(
                tmp, [{'problem_id': self.p1.id, 'category': 'junk',
                       'comment': 'мусор', 'at': '2026-07-21T10:00:00.000Z'}],
                format=VERDICTS_FORMAT_V1, name='v1.json'))
            out = self._import(write_verdicts_file(
                tmp, [{'problem_id': self.p1.id, 'categories': ['junk'],
                       'comment': 'мусор', 'at': '2026-07-21T10:00:00.000Z'}],
                name='v2.json'))
        self.assertEqual(ReviewVerdict.objects.count(), 1)
        self.assertIn('без изменений 1', out)

    def test_multiple_categories_become_rows_with_same_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id,
                 'categories': ['broken_formula', 'junk', 'broken_table'],
                 'comment': 'всё сразу', 'at': '2026-07-21T10:00:00.000Z'}])
            self._import(path)
        rows = ReviewVerdict.objects.filter(problem=self.p1)
        self.assertEqual(rows.count(), 3)
        self.assertEqual({r.category for r in rows},
                         {'broken_formula', 'junk', 'broken_table'})
        self.assertEqual({r.comment for r in rows}, {'всё сразу'})

    def test_reimport_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['perfect', 'junk'],
                 'comment': '', 'at': '2026-07-21T10:00:00.000Z'},
            ])
            self._import(path)
            out = self._import(path)
        self.assertEqual(ReviewVerdict.objects.count(), 2)
        self.assertIn('без изменений 2', out)

    def test_dropped_category_is_removed_on_reimport(self):
        """Снятый ревьюером дефект должен исчезнуть, а не остаться навсегда."""
        with tempfile.TemporaryDirectory() as tmp:
            self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['junk', 'broken_table'],
                 'comment': '', 'at': '2026-07-21T10:00:00.000Z'}], name='a.json'))
            out = self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['junk'],
                 'comment': '', 'at': '2026-07-21T11:00:00.000Z'}], name='b.json'))
        self.assertEqual([v.category for v in ReviewVerdict.objects.all()], ['junk'])
        self.assertIn('снято 1', out)

    def test_newer_verdict_updates_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['perfect'],
                 'comment': '', 'at': '2026-07-21T10:00:00.000Z'}], name='a.json'))
            out = self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['disputed'],
                 'comment': 'передумал', 'at': '2026-07-21T11:00:00.000Z'}],
                name='b.json'))
        self.assertEqual(ReviewVerdict.objects.count(), 1)
        v = ReviewVerdict.objects.get()
        self.assertEqual((v.category, v.comment), ('disputed', 'передумал'))
        self.assertIn('новых 1', out)
        self.assertIn('снято 1', out)

    def test_trash_verdict_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['trash'],
                 'comment': '', 'at': ''}]))
        self.assertEqual(ReviewVerdict.objects.get().category, 'trash')
        self.assertIn('Гагно: 1', out)

    def test_reviewer_option_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['perfect'],
                 'comment': '', 'at': ''}]), reviewer='Ксения')
        self.assertEqual(ReviewVerdict.objects.get().reviewer, 'Ксения')

    def test_other_reviewers_verdicts_are_not_silently_overwritten(self):
        """Ключ идемпотентности без ревьюера — чужой вердикт затёрся бы молча."""
        ReviewVerdict.objects.create(bundle='test_bundle', problem=self.p1,
                                     category='perfect', reviewer='Анич')
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['perfect'],
                 'comment': '', 'at': ''}], reviewer='Ксения')
            with self.assertRaisesMessage(CommandError, 'другого ревьюера'):
                self._import(path)
        self.assertEqual(ReviewVerdict.objects.get().reviewer, 'Анич')

    def test_bundle_separates_same_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['perfect'],
                 'comment': '', 'at': ''}], name='a.json'))
            self._import(write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['junk'],
                 'comment': '', 'at': ''}], name='b.json'), bundle='other')
        self.assertEqual(ReviewVerdict.objects.count(), 2)
        self.assertEqual({v.bundle for v in ReviewVerdict.objects.all()},
                         {'test_bundle', 'other'})

    def test_unknown_category_rejects_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_verdicts_file(tmp, [
                {'problem_id': self.p1.id, 'categories': ['nonsense'],
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
