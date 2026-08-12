"""
Фаза 6 сессии 9 — обзор группы.

Питон видит здесь три вещи: что теплокарта получает ВЫБРАННЫЙ период, что
уровень для цветной метки считает общая `level_of`, и что сортировка везде
идёт через один партиал. Остальное (полоса прокрутки, растворение края,
сам клик по заголовку) проверяет `scripts/session9_overview.js` исполнением.
"""
import io
import os
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from problems import stats
from problems.tests.factories import make_problem, make_user

ROOT = settings.BASE_DIR


def read(path):
    with io.open(os.path.join(ROOT, path), encoding='utf-8') as handle:
        return handle.read()


class HeatmapPeriodTests(TestCase):
    """6.1 — теплокарта слушается переключателя, а не игнорирует его."""

    def setUp(self):
        from problems.models import StudentGroup

        self.tutor = make_user('hp_tutor', role='teacher')
        self.student = make_user('hp_student', role='student')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        self.client.force_login(self.tutor)

    def _url(self, period):
        return (reverse('teacher:group_detail', args=[self.group.pk])
                + '?tab=overview&period=' + period)

    def test_period_reaches_the_matrix(self):
        from datetime import timedelta

        from django.utils import timezone

        from problems.models import LearningEvent, Topic

        topic = Topic.objects.create(name='Эластичность', slug='hp-el')
        problem = make_problem('Условие')
        problem.topics.add(topic)
        old = LearningEvent.objects.create(
            user=self.student, source='homework', event_type='solved',
            topic=topic, catalog_problem=problem)
        LearningEvent.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=90))

        matrix_all = self.client.get(self._url('all')).context['matrix']
        matrix_day = self.client.get(self._url('day')).context['matrix']
        cell_all = next(c for c in matrix_all['columns']
                        if c['name'] == 'Эластичность')
        cell_day = next(c for c in matrix_day['columns']
                        if c['name'] == 'Эластичность')
        self.assertEqual(cell_all['attempted'], 1)
        self.assertEqual(cell_day['attempted'], 0,
                         'событие трёхмесячной давности не должно попадать '
                         'в период «День»')

    def test_all_time_note_is_gone(self):
        """Пометка «за всё время» стала бы враньём.

        ⚠️ Ищем РАЗМЕТКУ, а не имя класса: набор стилей вклеен в `<style>`
        страницы, и по имени тест находил бы совпадение в комментарии CSS.
        Та же ловушка, что с кружком-счётчиком в фазе 4.
        """
        html = self.client.get(self._url('month')).content.decode()
        self.assertNotIn('class="panel-allt"', html)
        self.assertNotIn('за всё время', html)


class WorkHistoryLevelsTests(TestCase):
    """6.4 — цвет процента берётся из общего правила, а не заводит своё."""

    def test_levels_come_from_level_of(self):
        got = {'open': Decimal('9'), 'test': Decimal('2')}
        could = {'open': Decimal('10'), 'test': Decimal('10')}
        row = stats._work_percents(got, could)
        self.assertEqual(row['open_percent'], 90)
        self.assertEqual(row['open_level'], stats.level_of(90))
        self.assertEqual(row['test_percent'], 20)
        self.assertEqual(row['test_level'], stats.level_of(20))
        self.assertEqual(row['mark_level'], stats.level_of(row['mark']))

    def test_no_data_has_no_level(self):
        """Прочерк не красится: «нет данных» — не плохой результат."""
        got = {'open': Decimal('0'), 'test': Decimal('0')}
        could = {'open': Decimal('0'), 'test': Decimal('0')}
        row = stats._work_percents(got, could)
        self.assertIsNone(row['open_percent'])
        self.assertEqual(row['open_level'], 'none')

    def test_template_does_not_paint_the_dash(self):
        text = read('teacher/templates/teacher/_work_history.html')
        # Метка стоит ТОЛЬКО внутри ветки «процент есть».
        self.assertNotIn('k-level--none', text)


class OneSortingMechanismTests(TestCase):
    """6.3 — сортировка одна на кабинет, второго механизма нет."""

    PAGES = (
        'teacher/templates/teacher/groups/detail.html',
        'teacher/templates/teacher/student_progress.html',
    )

    def test_partial_is_included_where_tables_live(self):
        for path in self.PAGES:
            with self.subTest(path=path):
                self.assertIn('_table_sort.html', read(path))

    def test_no_second_sorter_left(self):
        """Свой сортировщик в шаблоне — это будущее второе поведение."""
        for path in self.PAGES:
            with self.subTest(path=path):
                text = read(path)
                self.assertNotIn("th:not(.no-sort)", text)

    def test_sortable_tables_are_marked(self):
        self.assertIn('data-sortable',
                      read('teacher/templates/teacher/_work_history.html'))
        self.assertIn('data-sortable',
                      read('teacher/templates/teacher/groups/_overview.html'))


class ScrollFadeTests(TestCase):
    """6.2 — полосу прячем, прокрутку оставляем, край растворяем."""

    def test_style_hides_only_the_bar(self):
        css = read('problems/templates/platform/_stats_style.html')
        self.assertIn('scrollbar-width: none', css)
        self.assertIn('::-webkit-scrollbar { display: none', css)
        # Прокрутка обязана остаться.
        self.assertIn('.stats-table-wrap { overflow-x: auto; }', css)

    def test_fade_turns_off_at_the_end(self):
        css = read('problems/templates/platform/_stats_style.html')
        self.assertIn('.fade-box.is-end::after', css)
