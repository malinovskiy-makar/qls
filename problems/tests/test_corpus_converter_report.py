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

    def test_list_value_renders_one_item_per_line(self):
        entry = render_entry(
            problem_id=1,
            source_label='Школково',
            before={'criteria_tex': 'raw'},
            after={'rubric_criteria': [
                {'name': '(a) crit one', 'max_points': 3.0},
                {'name': '(б) crit two', 'max_points': 2.0},
            ]},
        )
        self.assertIn('rubric_criteria:', entry)
        self.assertIn("- {'name': '(a) crit one', 'max_points': 3.0}", entry)
        self.assertIn("- {'name': '(б) crit two', 'max_points': 2.0}", entry)


class RenderReportTests(SimpleTestCase):
    def test_report_includes_title_and_all_entries(self):
        report = render_report('Пилот конвертера', ['ENTRY_ONE', 'ENTRY_TWO'], 'сводка warnings')
        self.assertIn('Пилот конвертера', report)
        self.assertIn('ENTRY_ONE', report)
        self.assertIn('ENTRY_TWO', report)
        self.assertIn('сводка warnings', report)
