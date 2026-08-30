# -*- coding: utf-8 -*-
"""Боевой рендер легаси-источников: что команда пишет и чего не пишет.

Настоящий KaTeX здесь не поднимается — браузер это про
`render_preflight_v2`, у него свои тесты. Здесь проверяется то, что
вокруг: кого берут в кандидаты, какой текст ложится в базу и какой
НЕ ложится.

Главный предмет проверки — сессия 2026-08-29. До неё команда ставила
только флаг `content_format`, а шлюз судил канонизированный текст,
которого в базе нет: сайт показывал сохранённый. Замер по 500 случайным
кандидатам дал 70 задач из 465 PASS (15,1 %), которые шаблон показал бы
сломанными. Теперь команда сохраняет ровно тот текст, который проверила,
— как у новых источников ([ADR 0033](../../docs/adr/0033-new-sources-store-converted-text.md)).
"""
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from problems.corpus_converter.preflight_gate import GateVerdict
from problems.corpus_converter.reshalki_dollar_exclusions import (
    FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT,
)
from problems.models import Problem, ProblemPart, Source, SourceReference

ARCHIVE3 = 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'
MATEK = 'МатЭк — Overleaf архивы (2021–2025)'
LSH2025 = 'ЛШ Олмат 2025 (Overleaf)'
RESHALKI = 'Решалки Олмат (olmat41)'

#: Вложенный `enumerate` — живой минимальный случай неидемпотентности,
#: сжатый из #43186 (Archive 3). Первый проход снимает только внешний
#: уровень, второй съедает содержимое целиком:
#: `\begin{enumerate}\n \begin{enumerate}...` -> `1. \begin{enumerate}...` -> `1. `
NESTED_ENUMERATE = (
    '\\begin{enumerate}\n \\begin{enumerate}\n \\end{enumerate}\n'
    '\\end{enumerate}'
)

#: Текст, который конвертер ЗАМЕТНО меняет (тире), и меняет устойчиво.
DASHES_RAW = 'Два соседа --- Андрей и Дима --- живут вместе.'
DASHES_CANON = 'Два соседа — Андрей и Дима — живут вместе.'

REPORT_DIR = tempfile.mkdtemp(prefix='qls-legacy-report-')


class FakeChecker:
    """Заглушка браузера: в этих тестах он не участвует."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def check_many(self, htmls):
        return [None] * len(htmls)


def run(*args, ok=True):
    """Прогон команды с подменённым шлюзом.

    Подменяется `render_preflight_v2` — настоящий шов команды: именно
    там она спрашивает вердикт."""

    def fake_gate(blocks, checker, raw_statement='', available_figures=None):
        return GateVerdict(ok, [] if ok else ['K-ERR'],
                           [] if ok else ['тестовый отказ'])

    out = StringIO()
    with mock.patch(
        'problems.management.commands.render_legacy_sources.KatexPreflight',
        FakeChecker,
    ), mock.patch(
        'problems.management.commands.render_legacy_sources.render_preflight_v2',
        fake_gate,
    ):
        call_command('render_legacy_sources', *args,
                     '--report-dir', REPORT_DIR, stdout=out, stderr=out)
    return out.getvalue()


class RenderLegacySourcesTests(TestCase):

    def setUp(self):
        for sid, name in ((14, ARCHIVE3), (13, MATEK),
                          (3, LSH2025), (16, RESHALKI)):
            Source.objects.create(id=sid, name=name)
        # Три принудительно исключаемые Решалки обязаны существовать:
        # команда прибавляет их к сверке чисел безусловно.
        for pid in sorted(FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT):
            self._problem(16, id=pid, statement='$$x')

    def _problem(self, source_id, statement='Условие $x=1$', **kwargs):
        problem = Problem.objects.create(statement=statement, **kwargs)
        SourceReference.objects.create(problem=problem, source_id=source_id)
        return problem

    # --- что команда ПИШЕТ ------------------------------------------

    def test_apply_saves_canonical_statement(self):
        """В базу ложится проверенный шлюзом текст, а не исходник."""
        p = self._problem(14, statement=DASHES_RAW)
        run('--apply')
        p.refresh_from_db()
        self.assertEqual(p.statement, DASHES_CANON)
        self.assertEqual(p.content_format, Problem.ContentFormat.MARKDOWN)

    def test_apply_saves_canonical_parts(self):
        """Подпункты тоже сохраняются канонизированными, адресуются по pk."""
        p = self._problem(14, statement='Условие')
        part = ProblemPart.objects.create(
            problem=p, label='а', statement=DASHES_RAW, answer='1', order=0)
        run('--apply')
        part.refresh_from_db()
        self.assertEqual(part.statement, DASHES_CANON)

    def test_dry_run_writes_nothing(self):
        """Без --apply не меняется ни текст, ни флаг."""
        p = self._problem(14, statement=DASHES_RAW)
        run()
        p.refresh_from_db()
        self.assertEqual(p.statement, DASHES_RAW)
        self.assertEqual(p.content_format, Problem.ContentFormat.PLAIN)

    # --- чего команда НЕ пишет --------------------------------------

    def test_non_idempotent_text_is_not_written(self):
        """Текст, который конвертер портит на втором проходе, не пишется.

        Иначе повторный прогон «доедал» бы задачу, а проверка
        идемпотентности никогда не давала бы ноль."""
        p = self._problem(14, statement=NESTED_ENUMERATE)
        run('--apply')
        p.refresh_from_db()
        self.assertEqual(p.statement, NESTED_ENUMERATE)
        self.assertEqual(p.content_format, Problem.ContentFormat.PLAIN)

    def test_approved_problem_is_never_touched(self):
        """Подтверждённую человеком задачу не трогаем ни текстом, ни флагом."""
        p = self._problem(14, statement=DASHES_RAW,
                          human_review=Problem.HumanReview.APPROVED)
        run('--apply')
        p.refresh_from_db()
        self.assertEqual(p.statement, DASHES_RAW)
        self.assertEqual(p.content_format, Problem.ContentFormat.PLAIN)

    def test_gate_failure_leaves_text_alone(self):
        """Не прошло шлюз — текст остаётся исходным."""
        p = self._problem(14, statement=DASHES_RAW)
        run('--apply', ok=False)
        p.refresh_from_db()
        self.assertEqual(p.statement, DASHES_RAW)
        self.assertEqual(p.content_format, Problem.ContentFormat.PLAIN)

    # --- инварианты --------------------------------------------------

    def test_counts_do_not_change(self):
        """Задач и подпунктов ровно столько же, сколько было."""
        p = self._problem(14, statement=DASHES_RAW)
        ProblemPart.objects.create(problem=p, label='а',
                                   statement=DASHES_RAW, answer='1', order=0)
        before = (Problem.objects.count(), ProblemPart.objects.count())
        run('--apply')
        after = (Problem.objects.count(), ProblemPart.objects.count())
        self.assertEqual(before, after)

    def test_second_dry_run_reports_nothing_to_change(self):
        """Идемпотентность: после записи сухой прогон даёт ноль."""
        self._problem(14, statement=DASHES_RAW)
        run('--apply')
        out = run()
        self.assertIn('Будет изменено: 0', out)
