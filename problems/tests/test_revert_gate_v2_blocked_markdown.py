# -*- coding: utf-8 -*-
"""Тесты отката content_format для 15 задач фикс-пака МатЭк.

Карточка Notion «15 задач уже стоят на content_format=markdown, но новый
шлюз их блокирует»: render_preflight_v2 (переведена render_legacy_sources,
fa93497/7952ff5) отбраковывает их, но команда render_legacy_sources
намеренно не снимает markdown с уже стоящих задач — только сигнал. Здесь
разовый откат ровно этих 15 id на content_format='plain', без правки
statement/answer/solution/human_review.
"""
import json

from django.core.management import CommandError, call_command
from django.test import TestCase

from problems.models import Problem
from problems.tests.factories import make_problem

# Ровно список из карточки Notion (id: 3cab11c9-2bc1-81d0-ade2-f49d13029441).
TARGET_IDS = [26603, 26632, 27371, 27422, 27496, 27509, 28772, 28775,
             28791, 28827, 28828, 28935, 29146, 29300, 29789]


def _make_targets(**extra):
    """Создать все 15 целевых задач с markdown, вернуть {id: Problem}."""
    out = {}
    for pid in TARGET_IDS:
        out[pid] = make_problem(
            id=pid, content_format=Problem.ContentFormat.MARKDOWN,
            human_review=Problem.HumanReview.DEFECT,
            statement=f'Условие #{pid}: $x = {pid}$.',
            answer=f'Ответ #{pid}', solution=f'Решение #{pid}',
            **extra,
        )
    return out


class RevertGateV2BlockedMarkdownTests(TestCase):

    def test_apply_reverts_exactly_the_fifteen_and_nothing_else(self):
        _make_targets()
        # Посторонняя markdown-задача — контроль «ни одна больше».
        other = make_problem(id=99999,
                             content_format=Problem.ContentFormat.MARKDOWN,
                             statement='Чужая задача, не трогать: $y=1$.')

        call_command('revert_gate_v2_blocked_markdown', '--apply')

        # Три живых id из списка карточки — точечная проверка.
        for pid in (26603, 27371, 29789):
            p = Problem.objects.get(id=pid)
            self.assertEqual(p.content_format, Problem.ContentFormat.PLAIN)
            self.assertEqual(p.statement, f'Условие #{pid}: $x = {pid}$.')
            self.assertEqual(p.answer, f'Ответ #{pid}')
            self.assertEqual(p.solution, f'Решение #{pid}')
            self.assertEqual(p.human_review, Problem.HumanReview.DEFECT)

        # Все 15 разом.
        reverted = Problem.objects.filter(
            id__in=TARGET_IDS, content_format=Problem.ContentFormat.PLAIN)
        self.assertEqual(reverted.count(), 15)

        other.refresh_from_db()
        self.assertEqual(other.content_format, Problem.ContentFormat.MARKDOWN)

    def test_dry_run_by_default_writes_nothing(self):
        _make_targets()

        call_command('revert_gate_v2_blocked_markdown')

        still_markdown = Problem.objects.filter(
            id__in=TARGET_IDS, content_format=Problem.ContentFormat.MARKDOWN)
        self.assertEqual(still_markdown.count(), 15)

    def test_apply_writes_backup_snapshot(self):
        _make_targets()

        call_command('revert_gate_v2_blocked_markdown', '--apply')

        from django.conf import settings
        import os
        backup_path = os.path.join(
            settings.BASE_DIR, 'reports', 'corpus_converter_scaleup',
            'gate_v2_blocked_revert_backup.json')
        with open(backup_path, encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(payload['count'], 15)
        snapshot_ids = {row['problem_id'] for row in payload['problems']}
        self.assertEqual(snapshot_ids, set(TARGET_IDS))
        for row in payload['problems']:
            self.assertEqual(row['content_format_before'], 'markdown')

    def test_missing_id_aborts_before_any_write(self):
        targets = _make_targets()
        # Одной задачи из пятнадцати не существует в базе.
        targets[26603].delete()

        with self.assertRaisesMessage(CommandError, '26603'):
            call_command('revert_gate_v2_blocked_markdown', '--apply')

        # Ничего не записалось — даже у существующих 14.
        untouched = Problem.objects.filter(
            id__in=TARGET_IDS, content_format=Problem.ContentFormat.MARKDOWN)
        self.assertEqual(untouched.count(), 14)

    def test_second_apply_raises_because_nothing_left_to_revert(self):
        _make_targets()
        call_command('revert_gate_v2_blocked_markdown', '--apply')

        with self.assertRaisesMessage(CommandError, 'ожида'):
            call_command('revert_gate_v2_blocked_markdown', '--apply')

    def test_dry_run_after_apply_reports_zero_without_error(self):
        _make_targets()
        call_command('revert_gate_v2_blocked_markdown', '--apply')

        # Не должно падать — сухой прогон после отката просто видит 0.
        call_command('revert_gate_v2_blocked_markdown')
