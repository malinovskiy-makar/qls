"""
Шаг «Что нашлось» после ревью 16.08 (фаза 9).

9.1 Сводка «просили — набрали» первой строкой, с кнопкой добора.
9.2 У каждой найденной задачи видны две строки условия и кнопка «Целиком».
9.3 Строка без результатов объясняет ОБА выхода.
9.4 Внизу — сколько разборов осталось, а не стоимость и модель.
"""
import os

from django.test import TestCase

from problems import hw_generator


def read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as handle:
        return handle.read()


class TestsInTextTests(TestCase):
    """⚠️ Про типы задач модель не спрашивают — читаем ФРАЗУ."""

    def test_not_mentioned_at_all(self):
        self.assertIsNone(hw_generator.tests_in_text('задачи по эластичности'))

    def test_mentioned_without_a_number(self):
        self.assertEqual(hw_generator.tests_in_text('добавь тесты'), 0)

    def test_number_is_read(self):
        self.assertEqual(hw_generator.tests_in_text('4 задачи и 2 теста'), 2)
        self.assertEqual(hw_generator.tests_in_text('нужно 3 теста'), 3)

    def test_number_survives_a_word_between(self):
        self.assertEqual(
            hw_generator.tests_in_text('и ещё 5 коротких тестов'), 5)


class PlanSummaryTests(TestCase):
    """Сводка считает то, что попросили, и то, что набрали."""

    def preview(self, kind, picked):
        return {'row': {'kind': kind}, 'picked': picked}

    def test_full_house_is_green(self):
        lines = hw_generator.plan_summary(
            [self.preview('open', 4)], {'open': 4, 'test': 0},
            {'open': 4, 'test': 0})
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['state'], 'ok')
        self.assertEqual(lines[0]['got'], 4)
        self.assertFalse(lines[0]['missing'])

    def test_settings_say_zero_but_the_query_asked(self):
        """⚠️ Тот самый случай владельца."""
        lines = hw_generator.plan_summary(
            [self.preview('open', 4)], {'open': 4, 'test': 0},
            {'open': 4, 'test': 0}, mentioned=2)
        tests = [line for line in lines if line['kind'] == 'test'][0]
        self.assertEqual(tests['state'], 'off')
        self.assertEqual(tests['got'], 0)
        self.assertEqual(tests['need'], 2)
        self.assertTrue(tests['show_need'])
        self.assertIn('в настройках стоит', tests['why'])
        self.assertEqual(tests['missing'], 2)

    def test_number_is_never_invented(self):
        """Тесты названы без числа — «из N» не печатаем вовсе."""
        lines = hw_generator.plan_summary(
            [self.preview('open', 4)], {'open': 4, 'test': 0},
            {'open': 4, 'test': 0}, mentioned=0)
        tests = [line for line in lines if line['kind'] == 'test'][0]
        self.assertFalse(tests['show_need'])
        self.assertEqual(tests['missing'], hw_generator.DEFAULT_FILL)

    def test_shortfall_is_named(self):
        lines = hw_generator.plan_summary(
            [self.preview('open', 2)], {'open': 5, 'test': 0},
            {'open': 5, 'test': 0})
        self.assertEqual(lines[0]['state'], 'short')
        self.assertEqual(lines[0]['missing'], 3)
        self.assertIn('меньше', lines[0]['why'])

    def test_button_label_is_declined_in_python(self):
        """⚠️ Шаблонный `pluralize` с тремя формами отдаёт пустую строку."""
        lines = hw_generator.plan_summary(
            [self.preview('open', 4)], {'open': 4, 'test': 0},
            {'open': 4, 'test': 0}, mentioned=2)
        tests = [line for line in lines if line['kind'] == 'test'][0]
        self.assertEqual(tests['fill_label'], 'Доискать 2 теста')

    def test_nothing_is_shown_when_nothing_was_asked(self):
        lines = hw_generator.plan_summary(
            [self.preview('open', 4)], {'open': 4, 'test': 0},
            {'open': 4, 'test': 0}, mentioned=None)
        self.assertEqual([line['kind'] for line in lines], ['open'])


class MarkupTests(TestCase):

    def test_summary_stands_before_the_rows(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        # ⚠️ Ищем РАЗМЕТКУ: имена обоих классов стоят ещё и в стилях,
        # вклеенных в ту же страницу, и там порядок обратный.
        self.assertLess(page.index('class="gen-tally"'),
                        page.index('class="plan-block"'))

    def test_candidate_shows_two_lines_and_a_button(self):
        row = read('teacher', 'templates', 'teacher', '_cand_row.html')
        self.assertIn('cand-lead', row)
        self.assertIn('cand-full', row)
        self.assertIn('Целиком', row)

    def test_preview_is_cut_by_css_not_by_characters(self):
        """Резать число символов значит рвать формулу посередине."""
        style = read('teacher', 'templates', 'teacher', '_picker_style.html')
        self.assertIn('-webkit-line-clamp: 2', style)

    def test_empty_row_names_both_ways_out(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        self.assertIn('это бесплатно, к модели обращаться не нужно', page)
        self.assertIn('доберите задачу из каталога', page)

    def test_cost_and_model_left_the_screen(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        body = page.split('{% block extra_js %}')[0]
        self.assertNotIn('cost_usd', body)
        self.assertNotIn('usage.model', body)
        self.assertIn('осталось {{ left_today', body)

    def test_remaining_is_recounted_before_drawing(self):
        """⚠️ Контекст собирается ДО обращения к модели."""
        view = read('teacher', 'views_generate.py')
        self.assertIn('def _refresh_left', view)
        # Объявление плюс два вызова: разбор запроса и переиск/добор.
        self.assertEqual(view.count('_refresh_left(context'), 3)


class FillActionTests(TestCase):
    """Кнопка добора не ходит к модели."""

    def test_fill_shares_the_research_branch(self):
        view = read('teacher', 'views_generate.py')
        self.assertIn("if action in ('research', 'fill')", view)
        # Ветка обращения к модели — только у `parse`.
        parse = view[view.index("if action == 'parse'"):
                     view.index("if action in ('research', 'fill')")]
        self.assertIn('parse_request', parse)
        rest = view[view.index("if action in ('research', 'fill')"):]
        self.assertNotIn('parse_request', rest)

    def test_fill_row_needs_a_kind_and_a_count(self):
        view = read('teacher', 'views_generate.py')
        piece = view[view.index('def _fill_row'):view.index('def _read_plan')]
        self.assertIn("kind not in ('open', 'test')", piece)
        self.assertIn('if missing <= 0', piece)
