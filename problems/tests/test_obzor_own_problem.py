"""
Обзор кабинета 13.08.2026, фаза 10 — экран своей задачи.

Пункты владельца 66, 67, 68, 69.

⚠️ 67 и 68 (липкое превью и решение в превью) оказались УЖЕ СДЕЛАННЫМИ —
сессия 8. Проверено браузером: превью держится на месте при прокрутке до
«Эталонного решения», и решение в нём рисуется. Тесты ниже закрепляют это,
чтобы не отвалилось молча: питон видит только разметку и стили, само
поведение проверял сценарий.
"""
import os
import re

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup
from problems.tests.factories import make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class Base(TestCase):
    def setUp(self):
        self.tutor = make_user('op_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.client.force_login(self.tutor)

    def html(self):
        return self.client.get(reverse('teacher:problem_new')).content.decode()


class StickyPreviewTests(Base):
    """10.1 — превью липкое (было сделано в сессии 8, закрепляем)."""

    def test_preview_is_sticky(self):
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        block = page.split('.preview {')[1].split('}')[0]
        self.assertIn('position: sticky', block)
        self.assertIn('top:', block)

    def test_column_is_not_stretched(self):
        """⚠️ `sticky` не работает, если колонка растянута по высоте."""
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        block = page.split('.editor {')[1].split('}')[0]
        self.assertIn('align-items: start', block)

    def test_tall_preview_scrolls_inside_itself(self):
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        block = page.split('.preview {')[1].split('}')[0]
        self.assertIn('max-height', block)
        self.assertIn('overflow: auto', block)

    def test_single_column_turns_stickiness_off(self):
        """На узком экране колонки одна под другой — липнуть не к чему."""
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        narrow = page.split('@media (max-width: 900px)')[1].split('}')[1]
        self.assertIn('position: static', narrow)


class PreviewSolutionTests(Base):
    """10.2 — превью показывает и решение."""

    def test_preview_has_a_place_for_the_solution(self):
        html = self.html()
        self.assertIn('id="preview-solution"', html)
        self.assertIn('id="preview-solution-body"', html)
        self.assertIn('Эталонное решение', html)

    def test_solution_field_feeds_the_preview(self):
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        self.assertIn("solution.addEventListener('input', schedule)", page)

    def test_solution_is_hidden_while_empty(self):
        html = self.html()
        block = re.search(r'<div class="pv-sol" id="preview-solution"([^>]*)>',
                          html).group(1)
        self.assertIn('hidden', block)

    def test_no_second_preview_under_the_field(self):
        """Два «как будет выглядеть» показывали бы одно и то же дважды."""
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        solution = page.split('id="id_solution"')[1][:200]
        self.assertIn('data-mathfield-preview="0"', solution)

    def test_the_math_is_rendered_in_the_solution_too(self):
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        self.assertIn('previewSolutionBody', page.split('renderMathInElement')[0])


class WeightHintTests(Base):
    """10.3 — подпись про вес только при пунктах."""

    def test_hint_is_hidden_when_there_are_no_parts(self):
        html = self.html()
        block = re.search(r'<span class="k-hint" id="parts-weight-hint"[^>]*>',
                          html).group(0)
        self.assertIn('hidden', block)

    def test_the_same_function_shows_it(self):
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        sync = page.split('function syncParts()')[1].split('function addPart')[0]
        self.assertIn("getElementById('parts-weight-hint')", sync)
        self.assertIn('weightHint.hidden = !has', sync)

    def test_hint_is_visible_when_the_problem_already_has_parts(self):
        from problems.models_platform import CustomProblem, CustomProblemPart

        problem = CustomProblem.objects.create(owner=self.tutor,
                                               statement='Условие')
        CustomProblemPart.objects.create(problem=problem, order=0,
                                         label='а', statement='Пункт')
        html = self.client.get(
            reverse('teacher:problem_edit', args=[problem.pk])).content.decode()
        block = re.search(r'<span class="k-hint" id="parts-weight-hint"([^>]*)>',
                          html).group(1)
        self.assertNotIn('hidden', block)


class ToolsRowTests(Base):
    """10.4 — три кнопки одного веса в одной строке."""

    def test_both_graph_controls_are_kit_buttons(self):
        html = self.html()
        row = html.split('id="statement-tools"')[1].split('</div>')[0]
        self.assertEqual(row.count('k-btn k-btn--plain k-btn--sm'), 2)
        self.assertNotIn('k-btn--quiet', row)

    def test_the_arrow_is_kept_on_the_outgoing_link(self):
        html = self.html()
        row = html.split('id="statement-tools"')[1].split('</div>')[0]
        self.assertIn('Создать новый график ↗', row)

    def test_the_field_says_where_the_formula_button_goes(self):
        html = self.html()
        self.assertIn('data-mathfield-tools="#statement-tools"', html)

    def test_the_script_honours_that(self):
        script = read('problems', 'static', 'platform', 'mathfield.js')
        self.assertIn("getAttribute('data-mathfield-tools')", script)
        self.assertIn('k-btn k-btn--plain k-btn--sm', script)

    def test_without_the_attribute_nothing_changes(self):
        """Остальные поля с формулами не должны заметить правки."""
        script = read('problems', 'static', 'platform', 'mathfield.js')
        block = script.split("var toolsSelector")[1].split('var body')[0]
        self.assertIn('panel.appendChild(toggle)', block)

    def test_row_paddings_are_tightened(self):
        """Три кнопки не помещались в 404 пикселя ровно на пять."""
        page = read('problems', 'templates', 'platform', 'problem_form.html')
        self.assertIn('.ed-tools .k-btn, .ed-tools .mf-toggle', page)
