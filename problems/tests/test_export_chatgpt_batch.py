# -*- coding: utf-8 -*-
"""Пакет случайной выборки на ревью (Фаза 5 брифа import-new-sources).

Главное, что здесь проверяется, — не красота страницы, а три свойства,
без которых пакет бесполезен: выборка воспроизводима по сиду, показ
дословно повторяет ветку боевого шаблона (`markdown` через рендерер,
`plain` через `linebreaksbr`), и ни один файл не выходит за лимит.
"""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from problems.models import Problem, ProblemPart, Source, SourceReference


def run(*args):
    out = StringIO()
    call_command('export_chatgpt_batch', *args, stdout=out, stderr=out)
    return out.getvalue()


class ExportChatgptBatchTests(TestCase):

    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.legacy = Source.objects.create(name='Overleaf Archive 3 (ОШ/ЛШ Олмат)')
        self.new = Source.objects.create(name='SolveHub — банк задач по экономике')
        self.problems = []
        for i in range(40):
            source = self.legacy if i % 2 else self.new
            problem = Problem.objects.create(
                statement=f'Условие {i}: $Q_d = 100 - {i}P$',
                answer=f'ответ {i}',
                content_format=(Problem.ContentFormat.MARKDOWN if i % 2
                                else Problem.ContentFormat.PLAIN),
                status=Problem.Status.DRAFT,
            )
            SourceReference.objects.create(
                problem=problem, source=source, problem_number=str(i))
            self.problems.append(problem)

    def _files(self, out=None):
        out = out or self.out
        return sorted(f for f in os.listdir(out) if f.endswith('.html'))

    def _manifest(self, out=None):
        with open(os.path.join(out or self.out, 'manifest.json'), encoding='utf-8') as f:
            return json.load(f)

    def test_sample_is_reproducible_for_the_same_seed(self):
        second = tempfile.mkdtemp()
        run('--size', '10', '--seed', '777', '--out', self.out)
        run('--size', '10', '--seed', '777', '--out', second)
        self.assertEqual(self._manifest()['ids'], self._manifest(second)['ids'])

    def test_different_seed_gives_different_sample(self):
        second = tempfile.mkdtemp()
        run('--size', '10', '--seed', '777', '--out', self.out)
        run('--size', '10', '--seed', '778', '--out', second)
        self.assertNotEqual(self._manifest()['ids'], self._manifest(second)['ids'])

    def test_sample_covers_whole_bank_not_only_new_sources(self):
        run('--size', '30', '--seed', '20260828', '--out', self.out)
        manifest = self._manifest()
        self.assertIn('Overleaf Archive 3 (ОШ/ЛШ Олмат)', manifest['by_source'])
        self.assertIn('SolveHub — банк задач по экономике', manifest['by_source'])

    def test_markdown_problem_goes_through_production_renderer(self):
        """content_format='markdown' — тот же render_markdown, что в шаблоне."""
        markdown_problem = next(
            p for p in self.problems
            if p.content_format == Problem.ContentFormat.MARKDOWN)
        markdown_problem.statement = 'Жирный **текст** и $x=1$'
        markdown_problem.save()
        run('--ids', str(markdown_problem.id), '--out', self.out)
        body = self._read_all()
        self.assertIn('<strong>текст</strong>', body)

    def test_plain_problem_is_shown_as_the_site_shows_it(self):
        """content_format='plain' — linebreaksbr, БЕЗ markdown. Иначе пакет
        показывал бы не то, что видит ученик."""
        plain = next(p for p in self.problems
                     if p.content_format == Problem.ContentFormat.PLAIN)
        plain.statement = 'Звёздочки **не разметка**\nвторая строка'
        plain.save()
        run('--ids', str(plain.id), '--out', self.out)
        body = self._read_all()
        self.assertIn('**не разметка**', body)
        self.assertNotIn('<strong>не разметка</strong>', body)
        self.assertIn('<br>', body)

    def test_parts_and_answer_are_shown(self):
        problem = self.problems[0]
        ProblemPart.objects.create(
            problem=problem, label='а', statement='пункт а', answer='1', order=0)
        run('--ids', str(problem.id), '--out', self.out)
        body = self._read_all()
        self.assertIn('пункт а', body)
        self.assertIn('ответ 0', body)

    def test_files_respect_the_size_limit(self):
        run('--size', '40', '--seed', '1', '--max-mb', '0.02', '--out', self.out)
        files = self._files()
        self.assertGreater(len(files), 1)
        for name in files:
            size = os.path.getsize(os.path.join(self.out, name))
            self.assertLessEqual(size, 0.02 * 1024 * 1024 * 1.5,
                                 f'{name} вырос за лимит')

    def test_every_sampled_problem_lands_in_exactly_one_file(self):
        run('--size', '40', '--seed', '3', '--max-mb', '0.02', '--out', self.out)
        manifest = self._manifest()
        seen = []
        for entry in manifest['files']:
            seen.extend(entry['ids'])
        self.assertEqual(sorted(seen), sorted(manifest['ids']))
        self.assertEqual(len(seen), len(set(seen)))

    def test_katex_pipeline_is_the_production_one(self):
        """В пакете тот же конвейер KaTeX, что на боевой странице: те же
        разделители, $$ раньше $, маскировка \\$."""
        run('--size', '2', '--seed', '5', '--out', self.out)
        body = self._read_all()
        self.assertIn('renderMathInElement', body)
        self.assertIn("left: '$$'", body)
        self.assertIn('maskEscapedDollars', body)

    def test_nothing_is_written_to_the_database(self):
        before = (Problem.objects.count(), ProblemPart.objects.count())
        run('--size', '20', '--seed', '9', '--out', self.out)
        self.assertEqual(
            (Problem.objects.count(), ProblemPart.objects.count()), before)

    def test_size_larger_than_bank_is_named_not_silently_clipped(self):
        output = run('--size', '9999', '--seed', '2', '--out', self.out)
        self.assertIn('в банке всего 40', output)
        self.assertEqual(len(self._manifest()['ids']), 40)

    def _read_all(self):
        body = ''
        for name in self._files():
            with open(os.path.join(self.out, name), encoding='utf-8') as f:
                body += f.read()
        return body
