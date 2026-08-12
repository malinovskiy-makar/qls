"""
Фаза 7 сессии 9 — карточка ученика у репетитора.

7.1 переключатель периодов, которому подчиняются блоки;
7.2 минуты на сайте — по расстоянию между событиями, а не по счётчику;
7.3 прогресс по темам одним блоком в две колонки.
"""
import io
import os
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems import stats
from problems.templatetags.ru import prep_o, prepositional
from problems.tests.factories import make_problem, make_user

ROOT = settings.BASE_DIR


def read(path):
    with io.open(os.path.join(ROOT, path), encoding='utf-8') as handle:
        return handle.read()


class MinutesOnSiteTests(TestCase):
    """7.2 — считаем время присутствия, а не пустое поле счётчика."""

    def setUp(self):
        self.student = make_user('mos_student', role='student')

    def _events(self, *offsets_minutes):
        from problems.models import LearningEvent

        base = timezone.now() - timedelta(hours=3)
        for offset in offsets_minutes:
            event = LearningEvent.objects.create(
                user=self.student, source='homework', event_type='solved')
            LearningEvent.objects.filter(pk=event.pk).update(
                created_at=base + timedelta(minutes=offset))

    def test_one_sitting_counts_from_first_to_last(self):
        self._events(0, 10, 25)
        self.assertEqual(stats.minutes_on_site(self.student, 'all'), 25)

    def test_long_pause_breaks_the_sitting(self):
        """Перерыв дольше получаса — это уход, а не работа."""
        self._events(0, 10, 200, 210)
        self.assertEqual(stats.minutes_on_site(self.student, 'all'), 20)

    def test_single_event_gives_zero(self):
        """Момент известен, длительность — нет. Ноль честнее выдумки."""
        self._events(0)
        self.assertEqual(stats.minutes_on_site(self.student, 'all'), 0)

    def test_nothing_is_zero(self):
        self.assertEqual(stats.minutes_on_site(self.student, 'all'), 0)

    def test_counter_field_is_not_used(self):
        """⚠️ Ровно та поломка, с которой началась фаза.

        Событие с заполненным `time_spent_seconds`, но одинокое, раньше
        давало минуты; события подряд БЕЗ счётчика давали ноль. Теперь
        наоборот, и это правильно: счётчик боевой код не пишет.
        """
        from problems.models import LearningEvent

        LearningEvent.objects.create(user=self.student, source='exam',
                                     event_type='solved',
                                     time_spent_seconds=6000)
        self.assertEqual(stats.minutes_on_site(self.student, 'all'), 0)

    def test_game_counts_as_time_on_site(self):
        from problems.models import LearningEvent

        base = timezone.now() - timedelta(hours=2)
        for offset in (0, 12):
            event = LearningEvent.objects.create(
                user=self.student, source='game', event_type='solved')
            LearningEvent.objects.filter(pk=event.pk).update(
                created_at=base + timedelta(minutes=offset))
        self.assertEqual(stats.minutes_on_site(self.student, 'all'), 12)

    def test_overview_takes_minutes_from_here(self):
        self._events(0, 10, 25)
        self.assertEqual(stats.overview(self.student, 'all')['minutes'], 25)


class RankingHalvesTests(TestCase):
    """Сильные и слабые половины не пересекаются."""

    def test_halves_do_not_overlap(self):
        rows = [{'name': 'Тема %d' % i, 'attempted': 10,
                 'accuracy': 100 - i * 5} for i in range(8)]
        result = stats.strongest_weakest(None, rows=rows)
        strong = {r['name'] for r in result['strong']}
        weak = {r['name'] for r in result['weak']}
        self.assertEqual(len(strong), 5)
        self.assertEqual(strong & weak, set(),
                         'тема не может быть и сильной, и слабой сразу')

    def test_five_in_each_half_when_there_is_data(self):
        rows = [{'name': 'Тема %d' % i, 'attempted': 10,
                 'accuracy': 100 - i * 5} for i in range(20)]
        result = stats.strongest_weakest(None, rows=rows)
        self.assertEqual(len(result['strong']), 5)
        self.assertEqual(len(result['weak']), 5)


class TopicPairsTests(TestCase):
    """7.3 — один блок, две половины, вторая сборка не заведена."""

    def setUp(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems.models import Topic

        for index, name in enumerate(CANONICAL):
            Topic.objects.get_or_create(name=name,
                                        defaults={'slug': 'tp-%d' % index})
        self.student = make_user('tp_student', role='student')

    def test_rows_carry_both_halves(self):
        data = stats.topic_progress_pairs(self.student)
        self.assertTrue(data['rows'])
        row = data['rows'][0]
        self.assertIn('open', row)
        self.assertIn('test', row)
        self.assertIn('total_open', data)
        self.assertIn('total_test', data)

    def test_halves_match_the_old_cards(self):
        """Числа те же, что давали две отдельные карточки."""
        pairs = stats.topic_progress_pairs(self.student)
        alone = stats.topic_progress(self.student, kind='open')
        self.assertEqual([r['name'] for r in alone['rows']],
                         [r['name'] for r in pairs['rows']])
        self.assertEqual(alone['total']['percent'],
                         pairs['total_open']['percent'])

    def test_row_is_dim_only_when_both_halves_are_empty(self):
        data = stats.topic_progress_pairs(self.student)
        for row in data['rows']:
            expected = (row['open'] is None or row['open']['empty']) and \
                (row['test'] is None or row['test']['empty'])
            self.assertEqual(row['empty'], expected, row['name'])

    def test_one_partial_draws_both_halves(self):
        """Три копии разметки шкалы — три разных вида после первой правки."""
        text = read('teacher/templates/teacher/student_progress.html')
        self.assertEqual(text.count('_tp_half.html'), 4,
                         'две половины строки плюс две половины «Всего»')


class StudentCardScreenTests(TestCase):
    def setUp(self):
        from problems.models import (Assignment, AssignmentItem, StudentGroup,
                                     Submission, TeacherFeedback)

        self.tutor = make_user('sp_tutor', role='teacher')
        self.student = make_user('sp_student', role='student',
                                 first_name='Иван', last_name='Петров')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)
        work = Assignment.objects.create(name='ДЗ', author=self.tutor,
                                         group=self.group)
        work.students.add(self.student)
        item = AssignmentItem.objects.create(
            assignment=work, order=0, catalog_problem=make_problem('Условие'),
            points=Decimal('10'))
        sub = Submission.objects.create(student=self.student, assignment=work,
                                        problem_item=item, status='reviewed')
        TeacherFeedback.objects.create(submission=sub, score=Decimal('8'),
                                       reviewed_by=self.tutor)
        self.client.force_login(self.tutor)

    def _url(self, period=None):
        url = reverse('teacher:student_progress', args=[self.student.pk])
        return url + ('?period=' + period if period else '')

    def test_period_switcher_is_there(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.context['period'], 'month')
        self.assertEqual(list(resp.context['periods']), list(stats.PERIODS))

    def test_unknown_period_falls_back_to_month(self):
        self.assertEqual(self.client.get(self._url('позавчера')
                                         ).context['period'], 'month')

    def test_minutes_card_is_on_the_screen(self):
        html = self.client.get(self._url()).content.decode()
        self.assertIn('Минут на сайте', html)

    def test_notes_placeholder_is_declined(self):
        html = self.client.get(self._url()).content.decode()
        self.assertIn('Полезная информация об Иване Петрове', html)

    def test_one_progress_block_not_two(self):
        html = self.client.get(self._url()).content.decode()
        self.assertIn('Прогресс по темам', html)
        self.assertNotIn('Прогресс по задачам', html)
        self.assertNotIn('Прогресс по тестам', html)


class PrepositionalTests(TestCase):
    """Склонение имени — подпись в поле, а не документ: границы честные."""

    CASES = {
        'Иван Петров': 'об Иване Петрове',
        'Пётр Иванов': 'о Петре Иванове',
        'Анна Соколова': 'об Анне Соколовой',
        'Сергей Дмитриев': 'о Сергее Дмитриеве',
        'Дмитрий Ли': 'о Дмитрии Ли',
        'Юлия Синицына': 'о Юлии Синицыной',
        'Игорь Бондарь': 'об Игоре Бондаре',
    }

    def test_known_shapes(self):
        for name, expected in self.CASES.items():
            with self.subTest(name=name):
                got = '%s %s' % (prep_o(name), prepositional(name))
                self.assertEqual(got, expected)

    def test_unknown_shape_is_left_alone(self):
        """Лучше именительный падеж, чем выдуманное окончание."""
        self.assertEqual(prepositional('student1'), 'student1')
        self.assertEqual(prepositional(''), '')
        self.assertEqual(prepositional(None), '')
