"""
Фаза 2 сессии 9 — единая таксономия тем.

Что здесь закреплено:
  • канон вырос до 23, обе новые темы стоят на согласованных местах;
  • список тем ОДИН на все четыре поверхности (каталог, статистика, подбор,
    игра) — второй источник правды был бы первым шагом к прежнему разъезду;
  • команда перевешивания двигает ВСЕ ссылки на тему, включая снимок в
    учебном событии: без него посторонняя колонка в теплокарте осталась бы;
  • команда идемпотентна и без `--confirm` ничего не пишет.
"""
import io

from django.core.management import call_command
from django.test import TestCase

from problems import topic_merge
from problems.management.commands.apply_topic_mapping import (
    ADAS, CANONICAL, GDP, INFL, INTRO,
)


def run(*args):
    """Прогоняет команду и возвращает её вывод текстом."""
    out = io.StringIO()
    call_command('merge_topics', *args, stdout=out)
    return out.getvalue()


class CanonListTests(TestCase):
    def test_canon_has_twenty_three_topics(self):
        self.assertEqual(len(CANONICAL), 23)
        self.assertEqual(len(set(CANONICAL)), 23, 'в каноне есть дубли')

    def test_intro_goes_first(self):
        """Вводная тема — первая: с неё начинается курс."""
        self.assertEqual(CANONICAL[0], INTRO)

    def test_adas_stands_next_to_the_macro_block(self):
        """AD-AS — сразу после «ВВП и национальные счета»."""
        self.assertEqual(CANONICAL[CANONICAL.index(GDP) + 1], ADAS)

    def test_adas_is_no_longer_swallowed_by_growth(self):
        """«Совокупный спрос» больше не падает в «Экономический рост».

        Пока своей темы не было, ключи «ad-as» и «совокупный спрос» стояли
        у GROWTH — и AD-AS считался ростом и циклами.
        """
        from problems.management.commands.apply_topic_mapping import classify

        self.assertEqual(classify('Совокупный спрос и совокупное предложение'),
                         ADAS)
        self.assertEqual(classify('Модель AD-AS'), ADAS)


class OneListEverywhereTests(TestCase):
    """Все четыре поверхности читают ОДИН список."""

    def setUp(self):
        from problems.models import Topic
        for index, name in enumerate(CANONICAL):
            Topic.objects.get_or_create(name=name,
                                        defaults={'slug': 'one-%d' % index})

    def test_catalog_atlas(self):
        from catalog.views import _canonical_topics

        self.assertEqual([t.name for t in _canonical_topics()], list(CANONICAL))

    def test_statistics(self):
        from problems import stats

        self.assertEqual([t.name for t in stats.canonical_topics()],
                         list(CANONICAL))

    def test_homework_picker(self):
        from problems import hw_generator

        self.assertEqual(list(hw_generator.canonical_topics()), list(CANONICAL))

    def test_game_chips_read_the_same_list(self):
        """Чипы тем Econ Rush строятся из того же списка, без своей копии."""
        import io as _io
        import os

        from django.conf import settings

        path = os.path.join(settings.BASE_DIR, 'game', 'views.py')
        with _io.open(path, encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn('apply_topic_mapping import', text)
        self.assertIn('CANONICAL', text)


class MergeTableTests(TestCase):
    def test_every_target_is_canonical(self):
        """Перевесить на неканоническую тему — значит не починить ничего."""
        for old, new in topic_merge.table_rows():
            with self.subTest(old=old):
                self.assertIn(new, CANONICAL)

    def test_no_topic_maps_to_itself(self):
        for old, new in topic_merge.table_rows():
            self.assertNotEqual(old, new)

    def test_new_canonical_are_in_the_canon(self):
        for name in topic_merge.NEW_CANONICAL:
            self.assertIn(name, CANONICAL)


class MergeCommandTests(TestCase):
    """Механика переноса — на маленькой базе, собранной вручную."""

    def setUp(self):
        from problems.models import (StudentGroup, StudentTopicProgress, Topic)
        from problems.models_platform import LearningEvent
        from problems.tests.factories import make_problem, make_user

        for index, name in enumerate(CANONICAL):
            Topic.objects.get_or_create(name=name,
                                        defaults={'slug': 'mc-%d' % index})
        self.old = Topic.objects.create(name='Безработица', slug='mc-old')
        self.new = Topic.objects.get(name=INFL)

        self.student = make_user('tm_student', role='student')
        self.tutor = make_user('tm_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.add(self.student)

        self.problem = make_problem('Условие про безработицу')
        self.problem.topics.add(self.old)

        LearningEvent.objects.create(user=self.student, source='homework',
                                     event_type='solved', topic=self.old,
                                     catalog_problem=self.problem)
        StudentTopicProgress.objects.create(student=self.student,
                                            topic=self.old, attempted=5,
                                            solved=3)

    def test_dry_run_changes_nothing(self):
        from problems.models_platform import LearningEvent

        text = run()
        self.assertIn('Холостой прогон', text)
        self.assertEqual(LearningEvent.objects.filter(topic=self.old).count(), 1)
        self.assertEqual(self.problem.topics.filter(pk=self.old.pk).count(), 1)

    def test_confirm_moves_the_problem(self):
        run('--confirm')
        names = set(self.problem.topics.values_list('name', flat=True))
        self.assertIn(INFL, names)
        self.assertNotIn('Безработица', names)

    def test_confirm_moves_the_event_snapshot(self):
        """⚠️ Главное. Тема в статистике берётся из снимка в событии.

        Без переноса событий посторонняя колонка в теплокарте осталась бы —
        то есть ровно то, на что жаловался владелец, не починилось бы.
        """
        from problems.models_platform import LearningEvent

        run('--confirm')
        self.assertEqual(LearningEvent.objects.filter(topic=self.old).count(), 0)
        self.assertEqual(LearningEvent.objects.filter(topic=self.new).count(), 1)

    def test_confirm_moves_topic_progress(self):
        from problems.models import StudentTopicProgress

        run('--confirm')
        row = StudentTopicProgress.objects.get(student=self.student,
                                               topic=self.new)
        self.assertEqual(row.attempted, 5)
        self.assertEqual(row.solved, 3)

    def test_progress_rows_are_summed_not_lost(self):
        """У прогресса ключ (ученик, тема): при слиянии счётчики складываются.

        Простой `update` упёрся бы в уникальность и уронил бы команду.
        """
        from problems.models import StudentTopicProgress

        StudentTopicProgress.objects.create(student=self.student,
                                            topic=self.new, attempted=2,
                                            solved=1)
        run('--confirm')
        rows = StudentTopicProgress.objects.filter(student=self.student)
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.topic_id, self.new.pk)
        self.assertEqual(row.attempted, 7)
        self.assertEqual(row.solved, 4)

    def test_second_run_finds_nothing(self):
        run('--confirm')
        text = run()
        self.assertIn('Перевешивать нечего', text)

    def test_old_topic_row_survives(self):
        """Строку темы не удаляем: у неё каскадные потомки."""
        from problems.models import Topic

        run('--confirm')
        self.assertTrue(Topic.objects.filter(pk=self.old.pk).exists())


class NoForeignColumnsTests(TestCase):
    """Обещание владельца: посторонних колонок в статистике не остаётся."""

    def test_heatmap_and_progress_show_only_canon(self):
        from problems.models import StudentGroup, Topic
        from problems.models_platform import LearningEvent
        from problems.tests.factories import make_problem, make_user
        from problems import stats

        for index, name in enumerate(CANONICAL):
            Topic.objects.get_or_create(name=name,
                                        defaults={'slug': 'nf-%d' % index})
        old = Topic.objects.create(name='Деньги и банки', slug='nf-old')
        student = make_user('nf_student', role='student')
        tutor = make_user('nf_tutor', role='teacher')
        group = StudentGroup.objects.create(name='Гр', teacher=tutor)
        group.students.add(student)
        problem = make_problem('Условие про банки')
        problem.topics.add(old)
        LearningEvent.objects.create(user=student, source='homework',
                                     event_type='solved', topic=old,
                                     catalog_problem=problem)

        before = stats.group_topic_matrix(group, 'all')
        self.assertEqual(len(before['columns']), len(CANONICAL) + 1,
                         'до перевешивания посторонняя колонка обязана быть')

        run('--confirm')
        after = stats.group_topic_matrix(group, 'all')
        self.assertEqual(len(after['columns']), len(CANONICAL))
        self.assertEqual([c['name'] for c in after['columns']],
                         list(CANONICAL))
