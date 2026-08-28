# -*- coding: utf-8 -*-
"""Шлюз рендера для трёх новых источников (Фаза 4 брифа import-new-sources).

Настоящий KaTeX здесь не поднимается: браузер — это про `render_preflight_v2`,
у которого свои тесты. Здесь проверяется то, что вокруг него: кого команда
берёт в кандидаты, кого не трогает никогда, что она пишет и что НЕ пишет.
"""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.corpus_converter.preflight_gate import GateVerdict
from problems.models import Problem, Source, SourceReference

SHKOLKOVO = 'Школково — банк задач по экономике'
SOLVEHUB = 'SolveHub — банк задач по экономике'
LESH = 'ЛЭШ 2026 — Гамма'


class FakeChecker:
    """Заглушка браузера: он в этих тестах не участвует."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def check_many(self, htmls):
        return [None] * len(htmls)


def run(*args, verdicts=None):
    """`verdicts` — словарь id задачи -> проходит ли шлюз.

    Подменяется `verdict_for()` — настоящий шов команды, а не выдуманная
    для теста дырка: команда спрашивает вердикт ровно там."""
    verdicts = verdicts or {}

    def fake_verdict(problem, checker):
        ok = verdicts.get(problem.id, True)
        return GateVerdict(ok, [] if ok else ['K-ERR'],
                           [] if ok else ['тестовый отказ'])

    out = StringIO()
    with mock.patch(
        'problems.management.commands.render_new_sources.KatexPreflight',
        FakeChecker,
    ), mock.patch(
        'problems.management.commands.render_new_sources.verdict_for',
        fake_verdict,
    ):
        call_command('render_new_sources', *args, stdout=out, stderr=out)
    return out.getvalue()


class RenderNewSourcesTests(TestCase):

    def setUp(self):
        self.sources = {
            name: Source.objects.create(name=name)
            for name in (SHKOLKOVO, SOLVEHUB, LESH)
        }

    def _problem(self, source_name, **kwargs):
        problem = Problem.objects.create(
            statement=kwargs.pop('statement', 'Условие $x=1$'), **kwargs)
        SourceReference.objects.create(
            problem=problem, source=self.sources[source_name],
            problem_number=str(problem.id))
        return problem

    def test_dry_run_is_default_and_changes_nothing(self):
        problem = self._problem(SHKOLKOVO)
        run()
        problem.refresh_from_db()
        self.assertEqual(problem.content_format, Problem.ContentFormat.PLAIN)

    def test_pass_gets_markdown_on_apply(self):
        problem = self._problem(SOLVEHUB)
        run('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.content_format, Problem.ContentFormat.MARKDOWN)

    def test_fail_stays_plain(self):
        good = self._problem(SOLVEHUB)
        bad = self._problem(SOLVEHUB)
        run('--apply', verdicts={bad.id: False})
        good.refresh_from_db()
        bad.refresh_from_db()
        self.assertEqual(good.content_format, Problem.ContentFormat.MARKDOWN)
        self.assertEqual(bad.content_format, Problem.ContentFormat.PLAIN)

    def test_approved_problems_are_never_candidates(self):
        """Абсолютный инвариант проекта: подтверждённое человеком не трогаем."""
        approved = self._problem(
            SHKOLKOVO, human_review=Problem.HumanReview.APPROVED)
        output = run('--apply')
        approved.refresh_from_db()
        self.assertEqual(approved.content_format, Problem.ContentFormat.PLAIN)
        self.assertIn('approved исключено: 1', output)

    def test_legacy_problems_are_out_of_scope(self):
        """Команда работает ТОЛЬКО по трём новым источникам."""
        legacy_source = Source.objects.create(name='Overleaf Archive 3 (ОШ/ЛШ Олмат)')
        legacy = Problem.objects.create(statement='Легаси')
        SourceReference.objects.create(problem=legacy, source=legacy_source)
        run('--apply')
        legacy.refresh_from_db()
        self.assertEqual(legacy.content_format, Problem.ContentFormat.PLAIN)

    def test_markdown_is_never_removed(self):
        """Команда только СТАВИТ markdown. Снятие — отдельное решение
        владельца, а не побочный эффект прогона шлюза."""
        already = self._problem(
            LESH, content_format=Problem.ContentFormat.MARKDOWN)
        output = run('--apply', verdicts={already.id: False})
        already.refresh_from_db()
        self.assertEqual(already.content_format, Problem.ContentFormat.MARKDOWN)
        self.assertIn('уже стоят на markdown, но НЕ проходят', output)

    def test_texts_are_never_touched(self):
        problem = self._problem(SOLVEHUB, answer='ответ', solution='решение')
        run('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, 'Условие $x=1$')
        self.assertEqual(problem.answer, 'ответ')
        self.assertEqual(problem.solution, 'решение')

    def test_problem_count_invariant(self):
        self._problem(SOLVEHUB)
        before = Problem.objects.count()
        run('--apply')
        self.assertEqual(Problem.objects.count(), before)

    def test_source_filter(self):
        shkolkovo = self._problem(SHKOLKOVO)
        solvehub = self._problem(SOLVEHUB)
        run('--apply', '--source', 'solvehub')
        shkolkovo.refresh_from_db()
        solvehub.refresh_from_db()
        self.assertEqual(shkolkovo.content_format, Problem.ContentFormat.PLAIN)
        self.assertEqual(solvehub.content_format, Problem.ContentFormat.MARKDOWN)

    def test_limit_is_named_in_output(self):
        for _ in range(3):
            self._problem(SOLVEHUB)
        output = run('--apply', '--limit', '2')
        self.assertIn('--limit 2', output)
        self.assertEqual(
            Problem.objects.filter(
                content_format=Problem.ContentFormat.MARKDOWN).count(), 2)

    def test_missing_source_row_fails_loudly(self):
        """Источника нет в базе — значит импорт не выполнялся; молча
        отчитаться «кандидатов 0» нельзя."""
        Source.objects.filter(name=SOLVEHUB).delete()
        with self.assertRaises(CommandError) as ctx:
            run('--apply')
        self.assertIn(SOLVEHUB, str(ctx.exception))
