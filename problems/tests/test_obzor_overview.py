"""
Обзор кабинета 13.08.2026, фаза 3 — обзор группы.

Пункты владельца 15–18:
  • «Анна Соколова — не сдал»: женское имя, мужской род;
  • заголовки колонок теплокарты обрезаны, полного имени не видно;
  • прокрутка вправо есть, признака «там ещё колонки» нет;
  • «по группе» показывает 100%, когда у двоих из троих прочерк.

⚠️ Пункт 19 (переименовать колонку в «Доля верных: везде / у вас») ОТМЕНЁН
владельцем по ходу работы. Заголовок остаётся прежним, и тест это закрепляет.
"""
import os
import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.models import StudentGroup, Topic
from problems.tests.factories import make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class ImpersonalWordingTests(TestCase):
    """3.1 — формулировки не требуют рода ученика."""

    def setUp(self):
        from problems.models import Assignment, LearningEvent

        self.now = timezone.now()
        self.tutor = make_user('iw_tutor', role='teacher')
        self.anna = make_user('iw_anna', role='student',
                              first_name='Анна', last_name='Соколова')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.anna])
        LearningEvent.objects.create(user=self.anna, source='catalog',
                                     event_type='solved')
        work = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=self.group,
            deadline=self.now - timedelta(days=2))
        work.students.set([self.anna])

    def _reasons(self):
        return [reason for row in stats.needs_attention(self.group)
                for reason in row['reasons']]

    def test_missed_work_is_impersonal(self):
        self.assertIn('работа «Домашка» не сдана', self._reasons())

    def test_no_gendered_verb_anywhere(self):
        for reason in self._reasons():
            self.assertNotIn('не сдал', reason)
            self.assertNotIn('не заходил', reason)

    def test_quiet_student_gets_days_not_a_verb(self):
        from problems.models import LearningEvent

        LearningEvent.objects.filter(user=self.anna).update(
            created_at=self.now - timedelta(days=20))
        reasons = self._reasons()
        self.assertTrue(any(r.startswith('нет активности 20 дн')
                            for r in reasons), reasons)

    def test_student_without_a_single_event_says_so(self):
        from problems.models import LearningEvent

        LearningEvent.objects.filter(user=self.anna).delete()
        self.assertIn('ни одного захода на сайт', self._reasons())

    def test_screen_hint_is_impersonal_too(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        head = page.split('Требуют внимания')[1][:400]
        self.assertNotIn('не сдал', head)

    def test_last_activity_column_is_impersonal(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        self.assertIn('нет активности{% endif %}', page)

    def test_work_history_chip_is_impersonal(self):
        page = read('teacher', 'templates', 'teacher', '_work_history.html')
        self.assertIn('wk-flag--none">не сдана<', page)


class HeatmapTests(TestCase):
    """3.2, 3.5 — подсказки теплокарты."""

    def setUp(self):
        from problems.models import LearningEvent

        self.tutor = make_user('hm_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.students = [make_user('hm_s%d' % i, role='student')
                         for i in range(3)]
        self.group.students.set(self.students)
        # Тема с данными ровно у двоих из троих — тот самый случай владельца.
        self.topic = Topic.objects.filter(
            name='Введение в экономическую теорию').first()
        if self.topic is None:
            # ⚠️ slug у Topic уникален и по умолчанию пуст — без явного
            # значения вторая тема падает об уникальность пустой строки.
            self.topic = Topic.objects.create(
                name='Введение в экономическую теорию', slug='vvedenie')
        for student in self.students[:2]:
            LearningEvent.objects.create(user=student, source='catalog',
                                         event_type='solved', topic=self.topic)
        self.client.force_login(self.tutor)

    def _column(self):
        matrix = stats.group_topic_matrix(self.group, 'all')
        return [c for c in matrix['columns']
                if c['topic_id'] == self.topic.pk][0]

    def test_column_knows_how_many_students_it_covers(self):
        column = self._column()
        self.assertEqual(column['covered'], 2)
        self.assertEqual(column['students'], 3)

    def test_untouched_topic_is_covered_by_nobody(self):
        other = (Topic.objects.filter(name='Эластичность').first()
                 or Topic.objects.create(name='Эластичность',
                                         slug='elastichnost'))
        matrix = stats.group_topic_matrix(self.group, 'all')
        column = [c for c in matrix['columns']
                  if c['topic_id'] == other.pk]
        self.assertTrue(column, 'колонки темы без попыток нет вовсе')
        self.assertEqual(column[0]['covered'], 0)

    def test_group_row_hint_says_by_how_many(self):
        html = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=overview').content.decode()
        self.assertIn('посчитано по 2 из 3 учеников', html)

    def test_column_head_carries_the_full_name(self):
        html = self.client.get(
            reverse('teacher:group_detail', args=[self.group.pk])
            + '?tab=overview').content.decode()
        self.assertIn('data-hint="Введение в экономическую теорию"', html)

    def test_heatmap_uses_no_browser_title(self):
        """`title` в этом проекте признан нерабочим — своя всплывашка."""
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        matrix_part = page.split('Ученики × темы')[1].split(
            'Таблица учеников')[0]
        self.assertNotIn('title="', matrix_part)

    def test_students_table_uses_the_same_mechanism(self):
        """Два механизма подсказок на одном экране — половина «не работает»."""
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        table = page.split('Таблица учеников')[1]
        self.assertNotIn('title="', table)
        self.assertIn("data-hint=\"{{ row.last_active|date:'d.m.Y, H:i' }}\"",
                      table)

    def test_hint_script_listens_to_data_hint(self):
        script = read('templates', '_hint_js.html')
        self.assertNotIn(".closest('.k-hintmark')", script)
        self.assertEqual(script.count(".closest('[data-hint]')"), 5)

    def test_question_marks_still_work(self):
        """Знак вопроса несёт `data-hint`, поэтому продолжает всплывать."""
        mark = read('templates', '_hint.html')
        self.assertIn('data-hint="{{ hint }}"', mark)


class FadeTests(TestCase):
    """3.3 — признак «справа есть ещё колонки»."""

    def test_fade_is_wide_and_two_layered(self):
        css = read('problems', 'templates', 'platform', '_stats_style.html')
        block = css.split('.fade-box::after')[1].split('}')[0]
        self.assertIn('width: 56px', block)
        self.assertIn('var(--fade-edge)', block)
        self.assertIn('var(--surface)', block)

    def test_fade_goes_out_at_the_end_of_the_scroll(self):
        css = read('problems', 'templates', 'platform', '_stats_style.html')
        self.assertIn('.fade-box.is-end::after { opacity: 0; }', css)

    def test_edge_colour_is_defined_in_both_themes(self):
        """Цвет только в одной теме — растворение пропало бы во второй."""
        tokens = read('templates', '_tokens.html')
        light = tokens.split('[data-theme="dark"]')[0]
        dark = tokens.split('[data-theme="dark"]')[1]
        self.assertIn('--fade-edge:', light)
        self.assertIn('--fade-edge:', dark)


class ColumnTitleTests(TestCase):
    """3.4 — ОТМЕНЕНО владельцем: заголовок колонки остаётся прежним."""

    def test_accuracy_column_keeps_its_name(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        self.assertIn('>Доля верных{% include \'_hint.html\'', page)
        self.assertNotIn('Доля верных: везде / у вас', page)

    def test_question_mark_is_still_there(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        row = [line for line in page.split('\n')
               if 'Доля верных' in line and 'th data-type' in line][0]
        self.assertIn("_hint.html", row)
