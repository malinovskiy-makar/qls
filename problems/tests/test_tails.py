"""
Ревью 17.08.2026, завершающая сессия, фаза 2 — семь хвостов.

2.1 кнопка «Мои задачи» уходит с экрана «Ученики» (адрес и вкладка живы);
2.2 на спокойной карточке занятия об одном говорят один раз;
2.3 подписи тем в матрице различимы;
2.4 верхний блок статистики выровнен влево целиком;
2.5 ссылка из промахов в игре ведёт в каталог по этой теме;
2.6 темы у демо-партий проставляются досевом;
2.7 мёртвого шаблона статистики группы больше нет.
"""
import os
import re

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup
from problems.tests.factories import make_user
from problems.tests.tree import project_files

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


def without_styles(html):
    """Страница без `<style>`: набор вклеен в неё, и проверка «надписи нет»
    иначе ловит собственный комментарий к правилу. Наступали восемь раз."""
    return re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)


class MyProblemsButtonTests(TestCase):
    """2.1 — кнопки на экране «Ученики» нет, всё остальное цело."""

    def setUp(self):
        self.tutor = make_user('tl_tutor', role='teacher')
        self.client.force_login(self.tutor)

    def test_button_is_gone_from_the_students_screen(self):
        html = without_styles(
            self.client.get(reverse('teacher:groups')).content.decode())
        self.assertNotIn('Мои задачи', html)

    def test_two_ways_to_start_a_lesson_are_still_there(self):
        html = self.client.get(reverse('teacher:groups')).content.decode()
        self.assertIn('+ Группа', html)
        self.assertIn('+ Ученик', html)

    def test_address_of_my_problems_still_works(self):
        self.assertEqual(
            self.client.get(reverse('teacher:problem_list')).status_code, 200)

    def test_tab_inside_the_work_flow_survives(self):
        html = self.client.get(reverse('teacher:work_pick')).content.decode()
        self.assertIn('Мои задачи', html)


class CalmCardTests(TestCase):
    """2.2 — одна фраза вместо двух."""

    def test_page_says_it_once(self):
        tutor = make_user('tc_tutor', role='teacher')
        lesson = StudentGroup.objects.create(name='Тихое', teacher=tutor)
        lesson.students.set([make_user('tc_st', role='student')])
        self.client.force_login(tutor)
        html = without_styles(
            self.client.get(reverse('teacher:groups')).content.decode())
        self.assertIn('Работ на проверке нет', html)
        self.assertNotIn('Всё вовремя', html)

    def test_template_has_no_second_phrase(self):
        page = read('teacher', 'templates', 'teacher', 'groups', 'list.html')
        self.assertNotIn('Всё вовремя', page)


class MatrixLabelTests(TestCase):
    """2.3 — 23 темы различаются с первого взгляда."""

    def test_limit_fits_twenty_plus_characters(self):
        from problems.stats import MATRIX_LABEL_LIMIT

        self.assertGreaterEqual(MATRIX_LABEL_LIMIT, 20)
        self.assertLessEqual(MATRIX_LABEL_LIMIT, 22)

    def test_two_longest_theories_differ(self):
        """Пример владельца: две «Теории» обязаны читаться по-разному."""
        from problems.stats import _matrix_label

        first = _matrix_label('Теория потребителя и полезность')
        second = _matrix_label('Теория фирмы: производство и издержки')
        self.assertNotEqual(first, second)
        # Различие не в одном хвостовом знаке: слова должны быть разные.
        self.assertNotEqual(first.split()[1], second.split()[1])

    def test_no_two_canonical_topics_collapse_into_one_label(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems.stats import _matrix_label

        labels = [_matrix_label(name) for name in CANONICAL]
        self.assertEqual(len(labels), len(set(labels)))

    def test_ceiling_matches_the_limit(self):
        """Высота шапки посчитана по замеру ~7,6 px на символ."""
        from problems.stats import MATRIX_LABEL_LIMIT

        style = read('problems', 'templates', 'platform',
                     '_stats_style.html')
        rule = re.search(r'\.matrix-head \{([^}]*)\}', style)
        ceiling = int(re.search(r'max-height:\s*(\d+)px',
                                rule.group(1)).group(1))
        self.assertGreaterEqual(ceiling, MATRIX_LABEL_LIMIT * 7.6)

    def test_ellipsis_only_when_something_was_cut(self):
        from problems.stats import _matrix_label

        self.assertEqual(_matrix_label('Международная торговля'),
                         'Международная торговля')
        self.assertTrue(
            _matrix_label('Теория потребителя и полезность').endswith('…'))


class HeroAlignmentTests(TestCase):
    """2.4 — все четыре ячейки верхнего блока выровнены влево."""

    def test_cells_are_left_aligned(self):
        style = read('problems', 'templates', 'platform',
                     '_stats_style.html')
        rule = re.search(r'\.hero-cell \{([^}]*)\}', style)
        self.assertIsNotNone(rule)
        self.assertIn('text-align: left', rule.group(1))
        self.assertNotIn('center', rule.group(1))


class GameMissLinkTests(TestCase):
    """2.5 — ссылка ведёт в каталог по теме, а не в игру целиком."""

    def _block(self):
        page = read('problems', 'templates', 'platform', 'stats.html')
        start = page.index('class="miss-go"')
        return page[start:page.index('</div>', start)]

    def test_link_goes_to_the_catalog_with_the_topic(self):
        block = self._block()
        self.assertIn("{% url 'catalog:problem_list' %}?topic=", block)
        self.assertIn('row.topic_id', block)

    def test_no_link_into_the_game_as_a_whole(self):
        self.assertNotIn("{% url 'game:page' %}", self._block())

    def test_catalog_really_reads_the_topic_parameter(self):
        """Обещание должно исполняться каталогом, а не только выглядеть."""
        from problems.models import Topic

        topic = Topic.objects.create(name='Проверочная тема')
        response = self.client.get(
            reverse('catalog:problem_list') + '?topic=%d' % topic.pk)
        self.assertEqual(response.status_code, 200)
        # ⚠️ КЛЮЧА `f_topic` В КОНТЕКСТЕ БОЛЬШЕ НЕТ. Активные фильтры
        # каталога живут в общем компоненте (`catalog/filters.py`), и
        # второй копии их состояния рядом не заводится. Требование то же:
        # каталог обязан ПРОЧИТАТЬ параметр темы, а не просто открыться.
        # Темы с 04.09.2026 — список (множественный выбор в каталоге).
        self.assertEqual(response.context['filters']['active']['topics'],
                         [str(topic.pk)])


class DemoGameTopicsTests(TestCase):
    """2.6 — досев темы уже созданным партиям.

    ⚠️ Боевая база в тестах не участвует: здесь проверяется САМ КОД досева.
    Что нужно сделать с базой владельца — сказано в отчёте сессии, команда
    в этой сессии не запускалась.
    """

    def test_backfill_fills_blank_game_events(self):
        from django.utils import timezone

        from problems.management.commands.seed_platform_demo import Command
        from problems.models import LearningEvent, Topic

        Topic.objects.create(name='Инфляция и безработица')
        student = make_user('dg_student', role='student')
        for _ in range(4):
            LearningEvent.objects.create(user=student, source='game',
                                         event_type='failed')
        Command()._history([student], timezone.now())
        blank = LearningEvent.objects.filter(user=student, source='game',
                                             topic__isnull=True).count()
        self.assertEqual(blank, 0)

    def test_misses_block_needs_a_topic(self):
        """Без темы строка промахов бесполезна — целиться в «Без темы» нечем."""
        from problems.models import LearningEvent, Topic
        from problems.stats import game_miss_topics

        student = make_user('dg_miss', role='student')
        LearningEvent.objects.create(user=student, source='game',
                                     event_type='failed')
        rows = LearningEvent.objects.filter(user=student, source='game')
        self.assertEqual(game_miss_topics(rows), [])

        topic = Topic.objects.create(name='Монетарная политика')
        rows.update(topic=topic)
        self.assertEqual(game_miss_topics(
            LearningEvent.objects.filter(user=student,
                                         source='game'))[0]['name'],
            'Монетарная политика')


class DeadTemplateTests(TestCase):
    """2.7 — мёртвого шаблона статистики группы больше нет."""

    def test_file_is_deleted(self):
        self.assertFalse(os.path.exists(os.path.join(
            ROOT, 'teacher', 'templates', 'teacher', 'groups', 'stats.html')))

    def test_nothing_renders_it(self):
        # ⚠️ Имя удалённого шаблона собирается из кусков: иначе проверка
        # ловит СЕБЯ САМУ — тот же класс дефекта, что «имя класса в
        # комментарии CSS», только в питоне.
        needle = 'teacher/groups/' + 'stats' + '.html'
        # ⚠️ Обход идёт общим обходчиком: он не заходит в чужие рабочие
        # копии внутри репозитория. Прежний список исключений про них не
        # знал, и проверка нашла бы удалённый шаблон живым — в дереве
        # соседней ветки. Подробности — `problems/tests/tree.py`.
        hits = []
        for path in project_files(ROOT, ('.py', '.html'), ('reports',)):
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue
            if needle in read(path):
                hits.append(os.path.relpath(path, ROOT))
        self.assertEqual(hits, [])

    def test_group_stats_address_still_redirects(self):
        """Адрес не умер: он и раньше был редиректом на обзор."""
        tutor = make_user('dt_tutor', role='teacher')
        group = StudentGroup.objects.create(name='Гр', teacher=tutor)
        self.client.force_login(tutor)
        response = self.client.get(
            reverse('teacher:group_stats', args=[group.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('tab=overview', response['Location'])
