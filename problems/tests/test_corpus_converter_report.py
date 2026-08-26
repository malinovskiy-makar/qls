from django.test import SimpleTestCase

from problems.corpus_converter.report import render_entry, render_report


class RenderEntryTests(SimpleTestCase):
    def test_entry_has_before_after_and_id(self):
        entry = render_entry(
            problem_id=53709,
            source_label='ILE',
            before={'statement': '\\textbf{Старое}'},
            after={'statement_md': '**Старое**'},
        )
        self.assertIn('53709', entry)
        self.assertIn('ILE', entry)
        self.assertIn('\\textbf{Старое}', entry)
        self.assertIn('**Старое**', entry)


class RenderReportTests(SimpleTestCase):
    def test_report_includes_title_and_all_entries(self):
        report = render_report('Пилот конвертера', ['ENTRY_ONE', 'ENTRY_TWO'], 'сводка warnings')
        self.assertIn('Пилот конвертера', report)
        self.assertIn('ENTRY_ONE', report)
        self.assertIn('ENTRY_TWO', report)
        self.assertIn('сводка warnings', report)
