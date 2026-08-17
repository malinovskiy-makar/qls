# -*- coding: utf-8 -*-
"""
Визуальная сессия 17.08, фаза 6 — остатки: единый лист работы, поля текста,
обрезка названий тем, край прокрутки, счёт работ в достижениях.

⚠️ Счёт работ здесь ЕДИНСТВЕННОЕ изменение функции за сессию (п. 6.7), и
проверяется он на живых записях, а не по тексту файла: одна сданная работа
из четырёх задач — это одна работа.
"""
import re
from decimal import Decimal

from django.test import TestCase

from problems.models import (Assignment, Problem, StudentGroup, Submission,
                             User)
from problems.models_platform import AssignmentItem

SHEET = 'teacher/templates/teacher/work/_sheet_js.html'
KIT = 'templates/_kit.html'
COMPOSE = 'teacher/templates/teacher/work/compose.html'
GIVE = 'teacher/templates/teacher/work/give.html'
TOKENS = 'templates/_tokens.html'


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


class OneSheetTests(TestCase):
    """6.1 — одна разметка листа, а не три разных."""

    def test_both_previews_call_the_shared_painter(self):
        for path in (COMPOSE, GIVE):
            page = read(path)
            self.assertIn('teacher/work/_sheet_js.html', page, path)
            self.assertIn('window.QLS_SHEET.paint', page, path)

    def test_neither_screen_paints_its_own_task(self):
        """Своей сборки строки задачи на экранах не осталось."""
        for path in (COMPOSE, GIVE):
            page = read(path)
            self.assertNotIn("className = 'wk-eyes__task'", page, path)
            self.assertNotIn("className = 'wk-paper__task'", page, path)

    def test_sheet_shows_what_the_print_sheet_shows(self):
        source = read(SHEET)
        for piece in ('row.section', 'points_text', 'sheet-task__part',
                      'sheet-task__opt'):
            self.assertIn(piece, source, piece)

    def test_rules_live_in_the_kit_not_on_one_screen(self):
        """Класс на двух экранах — правила в наборе."""
        kit = read(KIT)
        self.assertIn('.sheet-task {', kit)
        self.assertIn('.sheet-task__pts', kit)
        for path in (COMPOSE, GIVE):
            self.assertNotIn('.sheet-task {', read(path), path)

    def test_points_word_is_declined_by_python(self):
        """Правило трёх русских форм не копируется на клиент."""
        from problems.assignment_rows import points_text

        self.assertEqual(points_text(Decimal('1')), '1 балл')
        self.assertEqual(points_text(Decimal('3')), '3 балла')
        self.assertEqual(points_text(Decimal('10')), '10 баллов')
        self.assertNotIn('баллов', read(SHEET))


class OptionsAsLettersTests(TestCase):
    """6.2 — варианты буквами, лишнего поля под тестом нет."""

    def test_options_are_printed_with_their_letter(self):
        source = read(SHEET)
        block = source[source.index('choices.forEach'):]
        block = block[:block.index('});')]
        self.assertIn("esc(choice.label) + ') '", block)

    def test_no_bullet_list_for_options(self):
        self.assertNotIn('wk-opts', read(SHEET))

    def test_field_is_skipped_when_there_are_ready_options(self):
        source = read(SHEET)
        self.assertIn('!parts.length && !choices.length', source)


class TextAreaTests(TestCase):
    """6.3 — нативной ручки размера нет, высота по содержимому."""

    def test_kit_forbids_the_native_handle(self):
        rule = re.search(r'\.k-area \{([^}]*)\}', read(KIT))
        self.assertIsNotNone(rule)
        self.assertIn('resize: none', rule.group(1))

    def test_growth_script_is_wired_into_both_bases(self):
        for path in ('teacher/templates/teacher/base.html',
                     'problems/templates/platform/base.html'):
            self.assertIn("_area_js.html", read(path), path)

    def test_height_is_reset_before_measuring(self):
        """`scrollHeight` не уменьшается сам — без сброса поле не сжимается."""
        source = read('templates/_area_js.html')
        self.assertIn("area.style.height = 'auto'", source)

    def test_save_button_carries_weight(self):
        # ⚠️ ПЕРЕСЧИТАНО 17.08: блок заметок переехал в общий партиал —
        # он стоит и на карточке ученика, и на обзоре индивидуального
        # занятия. Проверка та же, файл другой.
        page = read('teacher/templates/teacher/_tutor_note.html')
        block = page[page.index('class="note-form"'):]
        block = block[:block.index('</form>')]
        self.assertIn('k-btn--main', block)
        self.assertNotIn('k-btn--quiet', block)


class TopicLabelCutTests(TestCase):
    """6.4 — обрезка по границе слова, всегда с многоточием."""

    def test_word_boundary_and_ellipsis(self):
        from problems.stats import MATRIX_LABEL_LIMIT, _matrix_label

        self.assertEqual(_matrix_label('Вмешательство государства'),
                         'Вмешательство…')
        self.assertEqual(_matrix_label('Международная торговля'),
                         'Международная…')
        # Короткое название не получает обещания продолжения.
        self.assertEqual(_matrix_label('Рынок труда'), 'Рынок труда')
        self.assertLessEqual(len('Вмешательство'), MATRIX_LABEL_LIMIT)

    def test_no_cut_in_the_middle_of_a_word_for_canonical_topics(self):
        """Ни одна каноническая тема не режется посреди слова."""
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems.stats import _matrix_label

        for name in CANONICAL:
            short = _matrix_label(name)
            if not short.endswith('…'):
                continue
            body = short[:-1]
            # Обрезанное слово обязано целиком встречаться в названии.
            self.assertIn(body, name, name)
            # Дальше — либо конец, либо пробел, либо снятая хвостовая
            # пунктуация («Теория фирмы:» → «Теория фирмы…»).
            tail = name[len(body):len(body) + 1]
            self.assertIn(tail, (' ', '', ',', ';', ':', '.', '-', '–', '—'),
                          '%s → %s' % (name, short))

    def test_template_prints_the_server_side_label(self):
        page = read('teacher/templates/teacher/groups/_overview.html')
        self.assertIn('column.short', page)
        self.assertNotIn('column.name|truncatechars', page)

    def test_ceiling_fits_the_longest_label(self):
        """Потолок высоты обязан вмещать подпись, иначе срежет многоточие."""
        style = read('problems/templates/platform/_stats_style.html')
        rule = re.search(r'\.matrix-head \{([^}]*)\}', style)
        found = re.search(r'max-height:\s*(\d+)px', rule.group(1))
        self.assertIsNotNone(found)
        self.assertGreaterEqual(int(found.group(1)), 114)


class ScrollEdgeTests(TestCase):
    """6.5 — край прокрутки заметнее, и в обеих темах одинаково."""

    def values(self):
        css = read(TOKENS)
        dark_at = css.index('[data-theme="dark"]')
        return [re.search(r'--fade-edge:\s*rgba\([^)]*?,\s*\.(\d+)\)', part)
                for part in (css[:dark_at], css[dark_at:])]

    def test_both_themes_got_denser(self):
        light, dark = self.values()
        self.assertIsNotNone(light)
        self.assertIsNotNone(dark)
        self.assertGreaterEqual(int(light.group(1)), 17)
        self.assertGreaterEqual(int(dark.group(1)), 13)


class DifficultyHintTests(TestCase):
    """6.6 — величина объясняет себя."""

    def test_hint_sits_next_to_the_number(self):
        page = read('teacher/templates/teacher/groups/detail.html')
        block = page[page.index('row.difficulty_label'):]
        block = block[:block.index('</div>')]
        self.assertIn('_hint.html', block)


class WorkCountTests(TestCase):
    """6.7 — одна сданная работа из N задач это ОДНА работа."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('wc_tutor', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('wc_student', password='x',
                                               role='student')
        group = StudentGroup.objects.create(name='Г', teacher=cls.tutor)
        group.students.add(cls.student)
        cls.work = Assignment.objects.create(name='Домашка', author=cls.tutor,
                                             group=group, kind='homework')
        cls.exam = Assignment.objects.create(name='Контрольная',
                                             author=cls.tutor, group=group,
                                             kind='exam')
        # ⚠️ У СДАЧ РАЗНЫЕ МОМЕНТЫ. Именно это и ломало счёт: `Meta.ordering`
        # подмешивает `submitted_at` в SELECT DISTINCT, и при равных
        # значениях дефект не воспроизводится вовсе.
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        for work, count in ((cls.work, 4), (cls.exam, 3)):
            for index in range(count):
                problem = Problem.objects.create(
                    title='З%s%d' % (work.pk, index), statement='…')
                item = AssignmentItem.objects.create(
                    assignment=work, order=index, catalog_problem=problem,
                    points=Decimal('1'))
                Submission.objects.create(
                    assignment=work, student=cls.student, problem_item=item,
                    problem=problem, status='submitted',
                    submitted_at=now - timedelta(minutes=index))

    def test_facts_count_works_not_rows(self):
        from problems.gamification import user_facts

        facts = user_facts(self.student)
        self.assertEqual(facts['homeworks_submitted'], 1,
                         'домашка из четырёх задач это одна домашка')
        self.assertEqual(facts['exams_taken'], 1,
                         'контрольная из трёх задач это одна контрольная')

    def test_the_fix_is_the_same_one_line_as_in_stats(self):
        source = read('problems/gamification.py')
        block = source[source.index("'homeworks_submitted'"):]
        block = block[:block.index("'active_days'")]
        self.assertEqual(block.count('.order_by()'), 2)
