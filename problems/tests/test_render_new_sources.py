# -*- coding: utf-8 -*-
"""Шлюз рендера для трёх новых источников (Фаза 4 брифа import-new-sources).

Настоящий KaTeX здесь не поднимается: браузер — это про `render_preflight_v2`,
у которого свои тесты. Здесь проверяется то, что вокруг него: кого команда
берёт в кандидаты, кого не трогает никогда, что она пишет и что НЕ пишет.
"""
import os
import tempfile
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


#: Отчёты тестов уходят во ВРЕМЕННУЮ папку. Без этого прогон набора
#: писал в reports/import_new_sources/ репозитория и затирал настоящие
#: файлы — 933 предупреждения Школково превращались в четыре тестовых.
REPORT_DIR = tempfile.mkdtemp(prefix='qls-report-')


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
        call_command('render_new_sources', *args, '--report-dir', REPORT_DIR,
                     stdout=out, stderr=out)
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

    def test_flag_fails_marks_only_failing(self):
        """Критерий готовности: дефект либо починен, либо ЯВНО помечен.

        `hidden_pending_review` значит «человек ещё не смотрел», а
        `needs_quality_review` — «это плохо». Разные вещи, и отказ шлюза
        обязан ставить именно вторую."""
        good = self._problem(SOLVEHUB)
        bad = self._problem(SOLVEHUB)
        run('--apply', '--flag-fails', verdicts={bad.id: False})
        good.refresh_from_db()
        bad.refresh_from_db()
        self.assertFalse(good.needs_quality_review)
        self.assertTrue(bad.needs_quality_review)

    def test_flag_fails_needs_apply(self):
        """Без `--apply` флаг не ставится: сухой прогон ничего не пишет."""
        bad = self._problem(SOLVEHUB)
        run('--flag-fails', verdicts={bad.id: False})
        bad.refresh_from_db()
        self.assertFalse(bad.needs_quality_review)

    def test_flag_fails_is_off_by_default(self):
        bad = self._problem(SOLVEHUB)
        run('--apply', verdicts={bad.id: False})
        bad.refresh_from_db()
        self.assertFalse(bad.needs_quality_review)

    def test_flag_fails_also_marks_markdown_that_now_fails(self):
        """Задача уже на markdown, но шлюз её больше не пропускает.

        Снимать markdown команда не вправе (решение владельца), но
        промолчать о дефекте — тем более: помечаем."""
        bad = self._problem(SOLVEHUB,
                            content_format=Problem.ContentFormat.MARKDOWN)
        run('--apply', '--flag-fails', verdicts={bad.id: False})
        bad.refresh_from_db()
        self.assertEqual(bad.content_format, Problem.ContentFormat.MARKDOWN)
        self.assertTrue(bad.needs_quality_review)

    def test_flag_fails_does_not_publish_anything(self):
        """Инвариант сессии: draft и hidden_pending_review не трогаются."""
        bad = self._problem(SOLVEHUB, status='draft',
                            hidden_pending_review=True)
        run('--apply', '--flag-fails', verdicts={bad.id: False})
        bad.refresh_from_db()
        self.assertEqual(bad.status, 'draft')
        self.assertTrue(bad.hidden_pending_review)

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


class AsyncUnsafeEnvTests(TestCase):
    """Команда не имеет права оставлять DJANGO_ALLOW_ASYNC_UNSAFE в процессе.

    Поймано полным прогоном, а не рассуждением. Переменная нужна на время
    работы браузера (синхронный playwright + ORM), но если она остаётся,
    `check --deploy` в том же процессе начинает ругаться `async.E001` —
    «не выставляйте DJANGO_ALLOW_ASYNC_UNSAFE в развёртывании», — и
    падает `test_production_settings.test_check_deploy_is_clean`. Django
    импортирует модули команд при автопоиске, а тесты команду ещё и
    запускают, поэтому проверяются оба случая: импорт и прогон.
    """

    VAR = 'DJANGO_ALLOW_ASYNC_UNSAFE'

    def setUp(self):
        self.sources = {
            name: Source.objects.create(name=name)
            for name in (SHKOLKOVO, SOLVEHUB, LESH)
        }
        self._saved = os.environ.pop(self.VAR, None)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop(self.VAR, None)
        else:
            os.environ[self.VAR] = self._saved

    def test_importing_the_module_does_not_set_the_variable(self):
        import subprocess
        import sys

        code = (
            'import os, django;'
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
            'django.setup();'
            'import problems.management.commands.render_new_sources;'
            f"print(os.environ.get('{self.VAR}', 'НЕ ЗАДАНА'))"
        )
        env = {k: v for k, v in os.environ.items() if k != self.VAR}
        result = subprocess.run(
            [sys.executable, '-c', code], capture_output=True, text=True,
            env=env, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('НЕ ЗАДАНА', result.stdout)

    def test_running_the_command_restores_the_environment(self):
        problem = Problem.objects.create(statement='Условие $x=1$')
        SourceReference.objects.create(
            problem=problem, source=self.sources[SOLVEHUB], problem_number='1')
        run('--apply')
        self.assertNotIn(self.VAR, os.environ)
