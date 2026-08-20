# -*- coding: utf-8 -*-
"""Тесты первой волны починки (Сборник АА).

Четыре слоя:
- словарь исходов (problems/repair_outcomes.py — единственная точка правды);
- импорт формата qls-repair-verdicts-v1 (исход -> категории, цитаты, отказы);
- оболочка разбора (кнопки строятся ИЗ словаря, на экране есть объяснение
  модели и пометка шлюза, свои классы не сталкиваются с классами KaTeX);
- шлюз сверяет ЗАПИСЬ ЦЕЛИКОМ, а не поле с полем.
"""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from problems.models import Problem, ReviewVerdict
from problems.repair_outcomes import (OUTCOME_KEYS, PUBLISHABLE,
                                      REPAIR_OUTCOMES, REPAIR_VERDICTS_FORMAT,
                                      categories_for)
from problems.review_categories import CATEGORY_KEYS
from problems.management.commands.human_review_mark import SUPERSEDES
from problems.management.commands.repair_gate import record_pair
from problems.management.commands.repair_wave1_export import (
    Command as ExportCommand, apply_fields, changed_map)
from problems.text_clean import same_numbers_and_signs
from problems.tests.factories import make_problem

BUNDLE = 'repair_aa_20260728'


def write_file(tmpdir, verdicts, reviewer='анич', fmt=REPAIR_VERDICTS_FORMAT):
    payload = {
        'format': fmt,
        'bundle_id': BUNDLE,
        'source_bundle': 'aa_20260728',
        'reviewer': reviewer,
        'exported_at': '2026-08-20T09:00:00.000Z',
        'count': len(verdicts),
        'verdicts': verdicts,
    }
    path = Path(tmpdir) / 'repairs.json'
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return path


class OutcomeVocabularyTests(TestCase):
    """Словарь исходов — про ПОЧИНКУ, а не про дефект."""

    def test_five_outcomes_and_unique_keys(self):
        self.assertEqual(len(REPAIR_OUTCOMES), 5)
        self.assertEqual(len(set(OUTCOME_KEYS)), 5)

    def test_hotkeys_unique_and_are_digits_one_to_five(self):
        keys = [o['hotkey'] for o in REPAIR_OUTCOMES]
        self.assertEqual(keys, ['1', '2', '3', '4', '5'])

    def test_only_one_outcome_publishes(self):
        self.assertEqual(PUBLISHABLE, ['fixed_perfect'])

    def test_every_outcome_has_label_and_hint(self):
        for o in REPAIR_OUTCOMES:
            self.assertTrue(o['label'].strip(), o['key'])
            self.assertTrue(o['hint'].strip(), o['key'])

    def test_categories_for_perfect(self):
        self.assertEqual(categories_for('fixed_perfect', ['broken_formula']),
                         ['perfect'])

    def test_categories_for_partial_keeps_origin(self):
        self.assertEqual(categories_for('fixed_partial', ['junk', 'other']),
                         ['junk', 'other'])

    def test_categories_for_broke_is_fixed_wrong(self):
        self.assertEqual(categories_for('broke', ['junk']), ['fixed_wrong'])

    def test_categories_for_later_is_empty(self):
        """Отложенная задача вердикта не получает: молчание честнее оценки."""
        self.assertEqual(categories_for('later', ['junk']), [])

    def test_origin_without_categories_falls_back(self):
        # Пустой список означал бы «вердикта нет» и стёр бы след второго прохода.
        self.assertEqual(categories_for('not_fixed', []), ['other'])

    def test_all_produced_categories_are_known(self):
        for key in OUTCOME_KEYS:
            for cat in categories_for(key, ['broken_formula']):
                self.assertIn(cat, CATEGORY_KEYS, key)

    def test_bundle_supersedes_first_pass(self):
        """Без этого починенная задача осталась бы скрытой навсегда."""
        self.assertEqual(SUPERSEDES.get(BUNDLE), 'aa_20260728')


class RepairImportTests(TestCase):
    def setUp(self):
        self.p1 = make_problem(statement='Задача один $Q=10$.')
        self.p2 = make_problem(statement='Задача два.')
        self.p3 = make_problem(statement='Задача три.')

    def _import(self, path, **opts):
        out = StringIO()
        call_command('import_review_verdicts', str(path), stdout=out, **opts)
        return out.getvalue()

    def test_perfect_outcome_becomes_perfect_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, [
                {'problem_id': self.p1.id, 'outcome': 'fixed_perfect',
                 'comment': '', 'origin_categories': ['broken_formula'],
                 'quotes': [], 'at': '2026-08-20T09:00:00.000Z'},
            ])
            out = self._import(path)
        v = ReviewVerdict.objects.get(problem=self.p1)
        self.assertEqual(v.category, 'perfect')
        self.assertEqual(v.bundle, BUNDLE)
        self.assertIn('Починил, идеально: 1', out)

    def test_partial_outcome_keeps_origin_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, [
                {'problem_id': self.p2.id, 'outcome': 'fixed_partial',
                 'comment': 'скобка осталась',
                 'origin_categories': ['other', 'junk'],
                 'quotes': [], 'at': ''},
            ])
            self._import(path)
        cats = sorted(ReviewVerdict.objects.filter(problem=self.p2)
                      .values_list('category', flat=True))
        self.assertEqual(cats, ['junk', 'other'])

    def test_later_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, [
                {'problem_id': self.p3.id, 'outcome': 'later', 'comment': '',
                 'origin_categories': ['junk'], 'quotes': [], 'at': ''},
            ])
            self._import(path)
        self.assertEqual(ReviewVerdict.objects.filter(problem=self.p3).count(), 0)

    def test_quotes_survive_with_side_field_and_view(self):
        quote = {'text': 'Рост цен на груши', 'note': 'тут пробел пропал',
                 'side': 'after', 'field': 'Условие', 'view': 'rendered',
                 'at': '2026-08-20T09:01:00.000Z'}
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, [
                {'problem_id': self.p1.id, 'outcome': 'fixed_partial',
                 'comment': '', 'origin_categories': ['other'],
                 'quotes': [quote], 'at': ''},
            ])
            out = self._import(path)
        v = ReviewVerdict.objects.get(problem=self.p1)
        self.assertEqual(v.quotes, [quote])
        self.assertIn('Цитат: 1', out)

    def test_unknown_outcome_refuses_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, [
                {'problem_id': self.p1.id, 'outcome': 'почти_починил',
                 'comment': '', 'origin_categories': ['junk'],
                 'quotes': [], 'at': ''},
            ])
            with self.assertRaises(CommandError):
                self._import(path)
        self.assertEqual(ReviewVerdict.objects.count(), 0)

    def test_import_is_idempotent(self):
        rows = [{'problem_id': self.p1.id, 'outcome': 'fixed_perfect',
                 'comment': '', 'origin_categories': ['junk'],
                 'quotes': [], 'at': ''}]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, rows)
            self._import(path)
            self._import(path)
        self.assertEqual(ReviewVerdict.objects.count(), 1)

    def test_old_review_format_still_understood(self):
        """Формат оценок починки не имеет права сломать импорт вердиктов ревью."""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(
                tmp,
                [{'problem_id': self.p1.id, 'categories': ['perfect'],
                  'comment': '', 'at': ''}],
                fmt='qls-review-verdicts-v2')
            self._import(path)
        self.assertEqual(ReviewVerdict.objects.get(problem=self.p1).category,
                         'perfect')


def demo_screen(**over):
    """Экран-образец для проверок оболочки."""
    base = {
        'pid': 5533, 'cats': ['other'], 'comment': 'скобка',
        'action': 'fixed', 'explain': 'Убрала осиротевшую скобку в начале.',
        'edit_chars': 2,
        'before': {'statement': ') Рост цен на груши', 'solution': '',
                   'answer': 'а', 'parts': []},
        'after': {'statement': 'Рост цен на груши', 'solution': '',
                  'answer': 'а', 'parts': []},
        'gate': {'id': 5533, 'gate_passed': True, 'gate_flags': [],
                 'gate_labels': []},
    }
    base.update(over)
    return base


class ShellTests(TestCase):
    """Оболочка разбора: строится из словаря, показывает модель и шлюз."""

    def _page(self, screens):
        return ExportCommand().page(screens, head='')

    def _screen(self, **over):
        return demo_screen(**over)
    def test_buttons_come_from_the_vocabulary(self):
        html = self._page([self._screen()])
        for o in REPAIR_OUTCOMES:
            self.assertIn('data-key="%s"' % o['key'], html)
            self.assertIn(o['label'], html)

    def test_defect_categories_are_not_buttons(self):
        """Категории дефекта на этом экране — справка, а не кнопки."""
        html = self._page([self._screen()])
        self.assertNotIn('data-key="broken_formula"', html)
        self.assertNotIn('data-key="merged_structure"', html)

    def test_model_explanation_is_on_screen(self):
        html = self._page([self._screen()])
        self.assertIn('Что сказала модель', html)
        self.assertIn('Убрала осиротевшую скобку в начале.', html)

    def test_first_pass_category_and_comment_shown_as_reference(self):
        html = self._page([self._screen()])
        self.assertIn('Первый проход', html)
        self.assertIn('Прочее (с комментарием)', html)
        self.assertIn('скобка', html)

    def test_gate_verdict_shown_both_ways(self):
        ok = self._page([self._screen()])
        self.assertIn('Шлюз пройден', ok)
        bad = self._page([self._screen(gate={
            'id': 5533, 'gate_passed': False,
            'gate_flags': ['numbers_changed'],
            'gate_labels': ['изменилась последовательность чисел и знаков']})])
        self.assertIn('Шлюз НЕ пройден', bad)
        self.assertIn('изменилась последовательность чисел и знаков', bad)

    def test_refusal_screen_says_there_is_no_edit(self):
        html = self._page([self._screen(
            action='unclear', explain='Вариантов ответа в базе нет.',
            after={'statement': ') Рост цен на груши', 'solution': '',
                   'answer': 'а', 'parts': []}, gate=None)])
        self.assertIn('дефект непонятен', html)
        self.assertIn('модель текст не правила', html)

    def test_both_sides_rendered_raw_hidden(self):
        html = self._page([self._screen()])
        self.assertIn('qls-body qls-render', html)
        self.assertIn('qls-body qls-raw" hidden', html)

    def test_field_blocks_carry_side_and_name_for_quotes(self):
        html = self._page([self._screen()])
        self.assertIn('data-side="before"', html)
        self.assertIn('data-side="after"', html)
        self.assertIn('data-field="Условие"', html)

    def test_no_class_collides_with_katex(self):
        """KaTeX сам раздаёт узлам эти классы, а CSS матчит по ТОКЕНУ."""
        html = self._page([self._screen()])
        for token in ('text', 'mord', 'base', 'strut', 'mfrac', 'sqrt'):
            self.assertNotIn('class="%s"' % token, html)
            self.assertNotIn('.%s{' % token, html)

    def test_screen_id_carries_no_hint_of_gate_or_edit_size(self):
        """Иначе человек начнёт судить по подсказке, а не по существу."""
        passed = self._screen(pid=100)
        failed = self._screen(pid=200, edit_chars=900, gate={
            'id': 200, 'gate_passed': False, 'gate_flags': ['numbers_changed'],
            'gate_labels': ['изменилась последовательность чисел и знаков']})
        html = self._page([passed, failed])
        self.assertIn('id="qls-s0" data-pid="100"', html)
        self.assertIn('id="qls-s1" data-pid="200"', html)

    def test_export_format_is_declared_in_payload(self):
        html = self._page([self._screen()])
        self.assertIn(REPAIR_VERDICTS_FORMAT, html)

    def test_origin_categories_travel_with_the_file(self):
        """Импорт не должен зависеть от того, что сейчас в базе."""
        html = self._page([self._screen()])
        self.assertIn('"origin"', html)
        self.assertIn('"5533": ["other"]', html)

    def test_shell_seam_exposed_for_the_browser_check(self):
        html = self._page([self._screen()])
        self.assertIn('window.QLS_SHELL', html)
        self.assertIn('buildDoc', html)


class ApplyFieldsTests(TestCase):
    def test_patch_replaces_only_named_fields(self):
        before = {'statement': 'A', 'solution': 'B', 'answer': 'C',
                  'parts': [{'label': 'а', 'statement': 'x', 'answer': ''}]}
        after = apply_fields(before, {'statement': 'A!'})
        self.assertEqual(after['statement'], 'A!')
        self.assertEqual(after['solution'], 'B')
        self.assertEqual(after['parts'], before['parts'])

    def test_patch_does_not_mutate_the_original(self):
        before = {'statement': 'A', 'parts': []}
        apply_fields(before, {'statement': 'Z'})
        self.assertEqual(before['statement'], 'A')

    def test_changed_map_marks_only_touched_blocks(self):
        before = {'statement': 'A', 'answer': 'C', 'parts': []}
        after = {'statement': 'A!', 'answer': 'C', 'parts': []}
        marks = changed_map(before, after)
        self.assertTrue(marks['Условие'])
        self.assertFalse(marks['Ответ'])

    def test_changed_map_survives_duplicate_part_labels(self):
        """В банке есть пары подпунктов с одинаковой меткой — словарь их схлопнул бы."""
        before = {'statement': '', 'parts': [
            {'label': 'а', 'statement': 'первый', 'answer': ''},
            {'label': 'а', 'statement': 'второй', 'answer': ''}]}
        after = {'statement': '', 'parts': [
            {'label': 'а', 'statement': 'первый', 'answer': ''},
            {'label': 'а', 'statement': 'второй!', 'answer': ''}]}
        self.assertTrue(changed_map(before, after)['Пункт а'])


class SelectionCleanupTests(TestCase):
    """Цитата с формулы не имеет права приезжать удвоенной скрытым MathML."""

    def test_shell_reads_selection_through_the_cleaner(self):
        html = ExportCommand().page([demo_screen()], head='')
        self.assertIn('function selectionText(sel)', html)
        self.assertIn('var text = selectionText(sel);', html)
        self.assertNotIn("String(sel).trim()", html)

    def test_cleaner_strips_mathml_and_annotation(self):
        html = ExportCommand().page([demo_screen()], head='')
        self.assertIn(".katex-mathml, annotation", html)


class GateWholeRecordTests(TestCase):
    """Шлюз сверяет ЗАПИСЬ ЦЕЛИКОМ — иначе краснеет на самой починке."""

    def test_moving_answer_out_of_statement_passes(self):
        # Именно на этом полевая сверка дала 37 ложных провалов из 64.
        before = {'statement': 'Сколько стоит? Ответ: 5', 'solution': '',
                  'answer': '', 'parts': []}
        rec_before, rec_after = record_pair(
            before, {'statement': 'Сколько стоит?', 'answer': '5'})
        self.assertTrue(same_numbers_and_signs(rec_before, rec_after))

    def test_splitting_options_into_parts_passes(self):
        before = {'statement': '', 'solution': '', 'answer': '',
                  'parts': [{'label': 'д', 'statement': '2 сырника\nе) 7 сырников',
                             'answer': ''}]}
        patch = {'parts': [
            {'label': 'д', 'statement': '2 сырника', 'answer': ''},
            {'label': 'е', 'statement': '7 сырников', 'answer': ''}]}
        rec_before, rec_after = record_pair(before, patch)
        self.assertTrue(same_numbers_and_signs(rec_before, rec_after))

    def test_lost_number_is_caught(self):
        before = {'statement': 'Цена 40 руб.', 'solution': '', 'answer': '',
                  'parts': []}
        rec_before, rec_after = record_pair(before, {'statement': 'Цена руб.'})
        self.assertFalse(same_numbers_and_signs(rec_before, rec_after))

    def test_latex_comma_is_normalised_before_comparison(self):
        before = {'statement': 'Доля 0{,}5 от дохода', 'solution': '',
                  'answer': '', 'parts': []}
        rec_before, rec_after = record_pair(
            before, {'statement': 'Доля 0,5 от дохода'})
        self.assertTrue(same_numbers_and_signs(rec_before, rec_after))
