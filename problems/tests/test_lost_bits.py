"""
Ревью 17.08.2026, завершающая сессия, фаза 3 — семь потерянных мелочей.

3.1 стрелки порядка и ручка перетаскивания читаются как органы управления;
3.2 пустые темы свёрнуты, пустое состояние «Сильных и слабых» — не плашка;
3.3 у косой черты в паре чисел есть воздух;
3.4 галочка строки запроса и галочка задачи различаются весом и местом;
3.5 дробная доля объясняется там, где на неё смотрят;
3.6 правая зона карточек задания одной ширины, три строки сжаты до двух;
3.7 кнопка создания и счётчик стоят на одной горизонтали.
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


# --- замер контраста: те же формулы, что в остальных проверках проекта ---
def _lin(channel):
    channel /= 255
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def contrast(front, back):
    first, second = _lum(_rgb(front)), _lum(_rgb(back))
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def token(name, dark=False):
    """Значение токена из `templates/_tokens.html` — светлое или тёмное."""
    css = read('templates', '_tokens.html')
    part = css[css.index('[data-theme="dark"]'):] if dark else css[
        :css.index('[data-theme="dark"]')]
    found = re.search(r'--%s:\s*(#[0-9a-fA-F]{6})' % name, part)
    return found.group(1)


class OrderControlsTests(TestCase):
    """3.1 — стрелки и ручка различимы, и это подтверждено числом."""

    def setUp(self):
        self.css = read('teacher', 'templates', 'teacher', 'work',
                        'compose.html')

    def _rule(self, selector):
        found = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', self.css)
        self.assertIsNotNone(found, selector)
        return found.group(1)

    def test_grip_is_no_longer_the_faintest_ink(self):
        self.assertIn('var(--text2)', self._rule('.wk-grip'))
        self.assertNotIn('var(--text3)', self._rule('.wk-grip'))

    def test_grip_contrast_is_measured(self):
        """Замер, а не «на глаз»: обе темы против поверхности карточки."""
        light = contrast(token('text2'), token('surface'))
        dark = contrast(token('text2', dark=True), token('surface', dark=True))
        self.assertGreaterEqual(light, 5.5, 'светлая %.2f' % light)
        self.assertGreaterEqual(dark, 5.5, 'тёмная %.2f' % dark)
        # И это заметно выше прежнего значения — иначе правка ничего не даёт.
        self.assertGreater(light, contrast(token('text3'), token('surface')))

    def test_arrow_border_is_visible_ink(self):
        """Рамка на `--border` (.12) читалась как случайная царапина."""
        rule = self._rule('.wk-move button')
        self.assertIn('var(--num-line)', rule)

    def test_disabled_state_is_colour_not_opacity(self):
        """⚠️ Приглушения прозрачностью на платформе не осталось нигде."""
        rule = self._rule('.wk-move button:disabled')
        self.assertNotIn('opacity', rule)
        self.assertIn('color:', rule)


class EmptyTopicsTests(TestCase):
    """3.2 — двадцать пустых строк уезжают под раскрывашку."""

    def setUp(self):
        from django.core.cache import cache

        from problems.models import LearningEvent, Topic

        cache.clear()
        self.tutor = make_user('lb_tutor', role='teacher')
        self.student = make_user('lb_student', role='student',
                                 first_name='Мария', last_name='Ким')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student, make_user('lb_x',
                                                         role='student')])
        # ⚠️ Темы обязаны быть КАНОНИЧЕСКИМИ: строки прогресса строятся по
        # канону (`stats.canonical_topics`), и на выдуманных названиях
        # пустых строк не появляется вовсе — проверка «пустые свёрнуты»
        # зеленела бы на пустоте.
        from problems.management.commands.apply_topic_mapping import CANONICAL

        self.topics = [Topic.objects.create(name=name, slug='lb-t%d' % index)
                       for index, name in enumerate(CANONICAL[:4])]
        LearningEvent.objects.create(user=self.student, source='catalog',
                                     event_type='solved',
                                     topic=self.topics[0])
        self.client.force_login(self.tutor)

    def test_server_splits_the_rows(self):
        from problems import stats

        data = stats.topic_progress_pairs(self.student, period='all')
        self.assertIn('filled', data)
        self.assertIn('blank', data)
        # Разбиение — ровно то же множество, никого не потеряли.
        self.assertEqual(len(data['filled']) + len(data['blank']),
                         len(data['rows']))
        self.assertTrue(all(row['empty'] for row in data['blank']))
        self.assertFalse(any(row['empty'] for row in data['filled']))

    def test_page_folds_them_under_one_line(self):
        html = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.student.pk])).content.decode()
        self.assertIn('без ответов за период', html)
        self.assertIn('k-details', html)

    def test_fold_uses_the_common_element(self):
        page = read('teacher', 'templates', 'teacher', '_topic_progress.html')
        self.assertIn('class="k-details tp-rest-fold"', page)
        self.assertIn('<summary>', page)

    def test_total_row_never_hides_inside_the_fold(self):
        page = read('teacher', 'templates', 'teacher', '_topic_progress.html')
        self.assertLess(page.index('</details>'), page.index('tp-total'))

    def test_markup_is_shared_by_both_screens(self):
        for path in (('teacher', 'templates', 'teacher',
                      'student_progress.html'),
                     ('teacher', 'templates', 'teacher', 'groups',
                      '_overview.html')):
            self.assertIn('teacher/_topic_progress.html', read(*path))

    def test_ranking_empty_state_is_not_a_slab(self):
        page = read('templates', '_ranking.html')
        self.assertIn('rank-none', page)
        self.assertNotIn('empty-note', page)
        rule = re.search(r'\.rank-none \{([^}]*)\}',
                         read('problems', 'templates', 'platform',
                              '_stats_style.html'))
        self.assertIsNotNone(rule)
        self.assertNotIn('background', rule.group(1))
        self.assertNotIn('padding', rule.group(1))


class PairSlashTests(TestCase):
    """3.3 — «13% / 13%» вместо «13%/13%»."""

    def test_gap_gives_air_on_both_sides(self):
        rule = re.search(r'\.k-pair \{([^}]*)\}', read('templates',
                                                       '_kit.html'))
        gap = int(re.search(r'gap:\s*(\d+)px', rule.group(1)).group(1))
        self.assertGreaterEqual(gap, 6)


class TwoCheckboxesTests(TestCase):
    """3.4 — разные по цене действия выглядят по-разному."""

    def test_row_checkbox_is_the_big_one_and_sits_in_the_head(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        head = page[page.index('<div class="q-top">'):]
        head = head[:head.index('</button>')]
        self.assertIn('k-check--box', head)
        self.assertIn('name="row_keep"', head)

    def test_row_checkbox_is_not_inside_the_button(self):
        """⚠️ Галочка внутри `<button>` сворачивала бы карточку."""
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        button = page[page.index('<button type="button" class="q-head"'):]
        button = button[:button.index('</button>')]
        self.assertNotIn('row_keep', button)

    def test_problem_checkbox_is_the_ordinary_one(self):
        row = read('teacher', 'templates', 'teacher', '_cand_row.html')
        label = row[row.index('<label class="k-check'):]
        label = label[:label.index('</label>')]
        self.assertNotIn('k-check--box', label)
        self.assertIn('cand-pick', label)

    def test_row_checkbox_is_still_submitted(self):
        """Имя поля не менялось: сервер читает его как раньше."""
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        self.assertIn('name="row_keep"', page)


class FractionHintTests(TestCase):
    """3.5 — «0,4 / 3» объясняется на виду."""

    def test_hint_explains_the_fraction(self):
        page = read('teacher', 'templates', 'teacher', '_topic_progress.html')
        hint = page[page.index('class="panel-hint"'):]
        hint = hint[:hint.index('</div>')]
        self.assertIn('весом', hint)
        self.assertIn('дробн', hint)


class AssignmentCardEdgeTests(TestCase):
    """3.6 — правый край списка встал на одну вертикаль."""

    def setUp(self):
        self.css = read('teacher', 'templates', 'teacher', 'groups',
                        'detail.html')

    def test_all_three_states_share_one_zone(self):
        page = self.css
        block = page[page.index('<div class="ass-side">'):]
        block = block[:block.index('{% endfor %}')]
        for state in ('needs_you', 'running'):
            self.assertIn(state, block)
        self.assertIn('ass-figures', block)

    def test_zone_has_a_fixed_width(self):
        rule = re.search(r'\.ass-side \{([^}]*)\}', self.css)
        self.assertIsNotNone(rule)
        self.assertIn('width:', rule.group(1))

    def test_checked_card_shows_two_lines_not_three(self):
        """Сложность переехала в подсказку — отдельной строки её больше нет."""
        page = self.css
        figures = page[page.index('<div class="ass-figures">'):]
        figures = figures[:figures.index('</div>')]
        self.assertNotIn('<div>{{ row.difficulty_label }}', figures)
        self.assertIn('difficulty_hint', figures)

    def test_hint_text_carries_the_value(self):
        from teacher.views_groups import assignment_stats  # noqa: F401

        source = read('teacher', 'views_groups.py')
        block = source[source.index("'difficulty_hint'"):]
        block = block[:block.index('),\n') + 2]
        self.assertIn('difficulty_label', block)
        self.assertIn('по шкале от', block)


class AssignmentsTabHeadTests(TestCase):
    """3.7 — кнопка и счётчик на одной горизонтали."""

    def setUp(self):
        self.tutor = make_user('at_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([make_user('at_st', role='student')])
        self.client.force_login(self.tutor)

    def test_button_and_counter_share_one_row(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    'detail.html')
        head = page[page.index('{% elif tab == \'assignments\' %}'):]
        head = head[head.index('<div class="ass-head">'):]
        head = head[:head.index('</div>')]
        self.assertIn('work_start', head)
        self.assertIn('ass-waiting-count', head)

    def test_counter_is_not_drawn_twice(self):
        """Шапок со счётчиком было ДВЕ — своя у списка и своя у кнопки."""
        page = read('teacher', 'templates', 'teacher', 'groups',
                    'detail.html')
        self.assertEqual(page.count('class="ass-waiting-count"'), 1)
        self.assertEqual(page.count('<div class="ass-head">'), 1)

    def test_tab_still_renders(self):
        response = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=assignments')
        self.assertEqual(response.status_code, 200)
