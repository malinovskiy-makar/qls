# -*- coding: utf-8 -*-
"""ВРЕМЕННАЯ репродукция (удалить после проверки): находка ревью —
после glue_pdf_lines --confirm отчёт dry_run_stats.md утверждает
«База НЕ менялась», хотя база реально изменена.
"""
import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from problems.tests.factories import link_source, make_problem, make_source

SCRATCH = ('/private/tmp/claude-501/-Users-makarmalinovskiy-Downloads-qls-platform/'
           '6af8191f-acd0-4801-8c32-69e08d8e6d94/scratchpad')


class ConfirmStatsMdReproTests(TestCase):
    def test_confirm_run_stats_md_claims_db_untouched(self):
        source = make_source(name='PDF-источник (репро)')
        p = make_problem(
            statement='Налог на продажи товаров\nявляется регрессивным.')
        link_source(p, source)

        report_dir = os.path.join(SCRATCH, 'repro_glue_lines')
        out = StringIO()
        with mock.patch(
                'problems.management.commands.glue_pdf_lines.REPORT_DIR',
                report_dir):
            call_command('glue_pdf_lines', '--source-id', str(source.id),
                         '--confirm', stdout=out)

        p.refresh_from_db()
        db_changed = (
            p.statement == 'Налог на продажи товаров является регрессивным.')

        stats_path = os.path.join(report_dir, 'dry_run_stats.md')
        with open(stats_path, encoding='utf-8') as f:
            content = f.read()

        print('=== REPRO RESULTS ===')
        print('DB_CHANGED_AFTER_CONFIRM =', db_changed)
        print('DB_STATEMENT =', repr(p.statement))
        print('STATS_MD_FIRST_LINES:')
        for line in content.splitlines()[:4]:
            print('   ', repr(line))
        print('STATS_CLAIMS_DB_UNTOUCHED =', ('База НЕ менялась' in content))
        print('STATS_HEADER_SAYS_DRYRUN =',
              ('dry-run' in content.splitlines()[0]))
        print('COMMAND_STDOUT_TAIL:')
        for line in out.getvalue().splitlines()[-6:]:
            print('   ', line)
        print('=== END REPRO ===')

        # Находка реальна, только если ОБА условия истинны одновременно:
        self.assertTrue(db_changed, 'база не изменилась — репро не удалось')
        self.assertIn('База НЕ менялась', content)
