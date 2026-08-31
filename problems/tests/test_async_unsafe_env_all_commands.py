# -*- coding: utf-8 -*-
"""Общее правило для ВСЕХ команд, которые трогают DJANGO_ALLOW_ASYNC_UNSAFE:
переменная не имеет права остаться в процессе — ни на импорте модуля, ни
после запуска команды.

Прецедент: `test_render_new_sources.py::AsyncUnsafeEnvTests` проверял
только `render_new_sources.py`. Регрессия нашлась в ЧЕТЫРЁХ ДРУГИХ
командах (разбор CI-прогона 90458899731, 2026-08-31) — точечный образец
её не поймал, потому что не был общим. Список команд ниже собирается
кодом (grep по исходникам `management/commands/`), а не переписывается
руками при каждой новой команде — иначе тест сам устареет так же, как
устарел точечный образец.
"""
import glob
import os
import subprocess
import sys
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from problems.corpus_converter.reshalki_dollar_exclusions import (
    FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT,
)
from problems.models import Problem, Source, SourceReference

VAR = 'DJANGO_ALLOW_ASYNC_UNSAFE'
COMMANDS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'management', 'commands')
#: Команда трогает VAR либо напрямую (`os.environ[...]`), либо через общую
#: обёртку `async_unsafe_for_playwright()` — искать нужно оба маркера,
#: иначе список молча потеряет команды, уже починенные через обёртку.
MARKERS = (VAR, 'async_unsafe_for_playwright')


def commands_touching_the_variable():
    """Имена команд (без `.py`), чей исходник упоминает один из MARKERS."""
    names = []
    for path in sorted(glob.glob(os.path.join(COMMANDS_DIR, '*.py'))):
        name = os.path.basename(path)[:-3]
        if name == '__init__':
            continue
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        if any(marker in text for marker in MARKERS):
            names.append(name)
    return names


class FakeChecker:
    """Заглушка KatexPreflight: браузер в этих тестах не участвует."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def check(self, html):
        return {'errors': [], 'strictHits': [], 'visibleText': ''}

    def check_many(self, htmls):
        return [self.check(h) for h in htmls]

    def widths_many(self, htmls):
        return [[] for _ in htmls]


class AsyncUnsafeEnvAllCommandsTests(TestCase):
    """Ни одна команда, трогающая VAR, не имеет права оставить её
    в os.environ — ни при импорте, ни после запуска."""

    def setUp(self):
        self._saved = os.environ.pop(VAR, None)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop(VAR, None)
        else:
            os.environ[VAR] = self._saved

    def test_the_discovered_list_is_not_stale(self):
        """Подстраховка от опечатки в пути/расширении: список не пуст и
        включает все команды, из-за которых заведён этот тест."""
        names = commands_touching_the_variable()
        for expected in ('corpus_render_codes', 'corpus_render_gate',
                         'render_legacy_sources', 'render_legacy_review_v2',
                         'render_new_sources', 'diagnose_new_sources'):
            self.assertIn(expected, names)

    def test_importing_any_such_command_does_not_set_the_variable(self):
        for name in commands_touching_the_variable():
            with self.subTest(command=name):
                code = (
                    'import os, django;'
                    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
                    'django.setup();'
                    f'import problems.management.commands.{name};'
                    "print('UNSET' if os.environ.get(%r) is None else 'SET')"
                    % VAR
                )
                env = {k: v for k, v in os.environ.items() if k != VAR}
                # Windows: печать по умолчанию идёт в cp1251, а не UTF-8
                # (problems/management/commands/CLAUDE.md, «Кодировка на
                # Windows»); сентинел здесь ASCII специально, чтобы тест не
                # зависел от локали, но PYTHONUTF8 всё равно фиксируем —
                # так надёжнее для будущих сентинелов.
                env['PYTHONUTF8'] = '1'
                result = subprocess.run(
                    [sys.executable, '-c', code], capture_output=True, text=True,
                    env=env, encoding='utf-8', errors='replace')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('UNSET', result.stdout)

    def test_running_corpus_render_codes_restores_the_environment(self):
        import tempfile
        report_dir = tempfile.mkdtemp(prefix='qls-render-codes-report-')
        gate_dir = tempfile.mkdtemp(prefix='qls-render-codes-gate-')
        with mock.patch(
            'problems.corpus_converter.katex_preflight.KatexPreflight',
            FakeChecker,
        ):
            call_command('corpus_render_codes', '--widths',
                         '--report-dir', report_dir, '--gate-dir', gate_dir)
        self.assertTrue(VAR not in os.environ, f'{VAR} осталась в окружении после запуска')

    def test_running_corpus_render_gate_restores_the_environment(self):
        with mock.patch(
            'problems.management.commands.corpus_render_gate.KatexPreflight',
            FakeChecker,
        ):
            call_command('corpus_render_gate', '--fixtures')
        self.assertTrue(VAR not in os.environ, f'{VAR} осталась в окружении после запуска')

    def test_running_render_legacy_sources_restores_the_environment(self):
        import tempfile
        # Инвариант счётчиков команды требует, чтобы принудительно
        # исключаемые id Решалок реально существовали (см. setUp в
        # test_render_legacy_sources.py — тот же приём).
        Source.objects.create(id=16, name='Решалки Олмат (olmat41)')
        for pid in sorted(FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT):
            problem = Problem.objects.create(id=pid, statement='$$x')
            SourceReference.objects.create(problem=problem, source_id=16)
        report_dir = tempfile.mkdtemp(prefix='qls-legacy-report-')
        with mock.patch(
            'problems.management.commands.render_legacy_sources.KatexPreflight',
            FakeChecker,
        ):
            call_command('render_legacy_sources', '--report-dir', report_dir)
        self.assertTrue(VAR not in os.environ, f'{VAR} осталась в окружении после запуска')

    def test_running_render_legacy_review_v2_restores_the_environment(self):
        import tempfile
        out_path = os.path.join(
            tempfile.mkdtemp(prefix='qls-legacy-review-v2-'), 'out.html')
        with mock.patch(
            'problems.management.commands.render_legacy_review_v2.KatexPreflight',
            FakeChecker,
        ), mock.patch(
            'problems.management.commands.render_legacy_review_v2.OUT_PATH',
            out_path,
        ):
            call_command('render_legacy_review_v2')
        self.assertTrue(VAR not in os.environ, f'{VAR} осталась в окружении после запуска')
