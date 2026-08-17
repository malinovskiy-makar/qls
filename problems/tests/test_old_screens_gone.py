# -*- coding: utf-8 -*-
"""
Остатки старого потока и навигация (ревью 17.08, фаза 4).

4.1 На экране подбора стояли ДВЕ ленты шагов — новая и прежняя.
4.2 «Написать свою» не несла ленты вовсе: человек выпадал из потока.
4.3 Способы набора назывались двумя разными наборами слов.
4.4 Ширина колонки прыгала между шагами (1000 / 1060 / 1100).
4.5 Старые экраны создания жили по прямому адресу мёртвым грузом.
4.6 Заголовок вкладки кабинета — «Ученики — ЭкЗадачи — ЭкЗадачи».
"""
import os
import re

from django.test import Client, TestCase
from django.urls import reverse

from problems.models import Problem, StudentGroup, User

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Формулировки владельца. Второго набора на платформе быть не должно.
WAY_NAMES = (('Искать самому', 'ручной поиск по каталогу'),
             ('Описать словами', 'умный поиск по каталогу'),
             ('Написать свою', 'создание задачи с нуля'))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('og-tutor', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.problem = Problem.objects.create(
            title='Задача', statement='Условие', problem_type='задача',
            status=Problem.Status.PUBLISHED, difficulty=3)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)


class OneStepRailTests(Base):
    """4.1 — лента шагов на экране одна."""

    def test_found_step_has_a_single_rail(self):
        html = self.client.get(reverse('teacher:assignment_generate')
                               ).content.decode()
        self.assertEqual(html.count('class="wk-rail"'), 1)
        # Прежний ряд «1. Запрос — 2. Что нашлось — 3. Конструктор» удалён
        # вместе с разметкой и стилями.
        self.assertNotIn('gen-step', html)
        self.assertNotIn('1. Запрос', html)

    def test_old_strip_styles_are_gone_too(self):
        self.assertNotIn('.gen-step',
                         read('teacher', 'templates', 'teacher',
                              'generate.html'))


class OwnProblemIsInsideTheFlowTests(Base):
    """4.2 — «Написать свою» несёт ту же ленту, что остальные шаги."""

    def page(self):
        return self.client.get(
            '%s?group=%d&to_cart=1' % (reverse('teacher:problem_new'),
                                       self.group.pk)).content.decode()

    def test_the_rail_is_there(self):
        html = self.page()
        self.assertIn('class="wk-rail"', html)
        for word in ('Что кладём', 'Состав', 'Выдача'):
            self.assertIn(word, html)

    def test_first_step_is_the_active_one(self):
        rail = re.search(r'<ol class="wk-rail".*?</ol>', self.page(), re.S)
        self.assertIsNotNone(rail)
        first = rail.group(0).split('</li>')[0]
        self.assertIn('is-on', first)

    def test_lesson_and_kind_are_not_lost(self):
        html = self.client.get(
            '%s?group=%d&to_cart=1&kind=exam'
            % (reverse('teacher:problem_new'), self.group.pk)).content.decode()
        rail = re.search(r'<ol class="wk-rail".*?</ol>', html, re.S).group(0)
        for href in re.findall(r'href="([^"]+)"', rail):
            self.assertIn('group=%d' % self.group.pk, href)
            self.assertIn('kind=exam', href)

    def test_the_old_tiles_are_gone(self):
        # ⚠️ Ищем РАЗМЕТКУ: имя класса живёт ещё и в наборе стилей, который
        # вклеен в `<style>` страницы (по проекту наступали шесть раз).
        self.assertNotIn('<span class="k-tile__name">', self.page())

    def test_editing_from_my_problems_has_no_rail(self):
        """Правка своей задачи к сборке работы отношения не имеет."""
        html = self.client.get(reverse('teacher:problem_new')).content.decode()
        self.assertNotIn('class="wk-rail"', html)


class OneSetOfNamesTests(Base):
    """4.3 — способы набора называются одинаково везде."""

    def test_pick_step_uses_the_owner_wording(self):
        html = self.client.get(reverse('teacher:work_pick')).content.decode()
        for name, note in WAY_NAMES:
            self.assertIn(name, html)
            self.assertIn(note, html)

    def test_the_second_set_of_words_is_gone(self):
        html = self.client.get(reverse('teacher:work_pick')).content.decode()
        # ⚠️ Режем ленту вкладок: «Каталог» — ещё и пункт шапки сайта, и
        # наивный поиск по всей странице краснел бы всегда.
        tabs = html.split('<div class="wk-tabs"')[1].split('</div>')[0]
        for stale in ('>Каталог<', 'умный подбор', 'задача с нуля'):
            self.assertNotIn(stale, tabs, stale)

    def test_own_tabs_keep_their_names(self):
        html = self.client.get(reverse('teacher:work_pick')).content.decode()
        self.assertIn('Мои задачи', html)
        self.assertIn('Отложенные', html)


class OneColumnWidthTests(Base):
    """4.4 — ширина колонки потока задана в одном месте."""

    def test_width_lives_in_the_kit(self):
        self.assertIn('.wk-wrap { max-width:', read('templates', '_kit.html'))

    def test_no_step_overrides_it(self):
        for name in ('pick.html', 'compose.html', 'give.html'):
            text = read('teacher', 'templates', 'teacher', 'work', name)
            self.assertNotIn('.wk-wrap { max-width', text, name)

    def test_found_step_uses_the_same_wrapper(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        self.assertIn('<div class="wk-wrap">', page)
        self.assertNotIn('gen-wrap', page)


class OldScreensAreGoneTests(Base):
    """4.5 — экраны удалены, а создание работы цело."""

    def test_templates_are_deleted(self):
        for name in ('assignment_create.html', 'assignment_build.html',
                     '_build_modes.html', '_build_head.html',
                     '_picker_list.html', '_picker_js.html',
                     '_picker_card.html', '_picker_modal.html'):
            path = os.path.join(ROOT, 'teacher', 'templates', 'teacher', name)
            self.assertFalse(os.path.exists(path), name)
        self.assertFalse(os.path.exists(os.path.join(
            ROOT, 'teacher', 'templates', 'teacher', 'groups',
            'exam_create.html')))

    def test_the_collection_builder_route_is_gone(self):
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse('teacher:assignment_build')

    def test_old_addresses_lead_into_the_flow(self):
        response = self.client.get(reverse('teacher:assignment_create')
                                   + '?group=%d' % self.group.pk)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('teacher:work_pick'), response['Location'])
        self.assertIn('group=%d' % self.group.pk, response['Location'])

    def test_old_exam_address_leads_into_the_flow(self):
        response = self.client.get(
            reverse('teacher:exam_create', args=[self.group.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('kind=exam', response['Location'])

    def test_creating_a_work_still_works(self):
        """⚠️ ГЛАВНОЕ: POST-обработчики удалять было нельзя."""
        response = self.client.post(reverse('teacher:assignment_create'), {
            'name': 'Работа после удаления экранов',
            'groups': [str(self.group.pk)],
            'problem_ids': str(self.problem.pk),
            'points_rule': 'difficulty'})
        self.assertEqual(response.status_code, 302)
        from problems.models import Assignment
        work = Assignment.objects.filter(
            name='Работа после удаления экранов').first()
        self.assertIsNotNone(work)
        self.assertEqual(work.items.count(), 1)

    def test_no_button_leads_to_a_deleted_screen(self):
        pages = ('%s?tab=assignments' % reverse('teacher:group_detail',
                                                args=[self.group.pk]),
                 reverse('teacher:groups'),
                 reverse('teacher:problem_list'),
                 reverse('teacher:work_pick'),
                 reverse('teacher:work_compose'),
                 reverse('teacher:work_give'),
                 reverse('teacher:assignment_generate'))
        dead = (reverse('teacher:assignment_create'),
                '/teacher/assignment/build/',
                '/teacher/groups/%d/exams/new/' % self.group.pk)
        for page in pages:
            html = self.client.get(page).content.decode()
            for url in dead:
                self.assertNotIn('href="%s"' % url, html,
                                 '%s → %s' % (page, url))


class TabTitleTests(Base):
    """4.6 — суффикс «— ЭкЗадачи» добавляется ровно один раз."""

    def screens(self):
        from problems.models import Assignment, AssignmentItem

        work = Assignment.objects.create(name='Работа', author=self.tutor,
                                         group=self.group)
        AssignmentItem.objects.create(assignment=work, order=0,
                                      catalog_problem=self.problem)
        student = User.objects.create_user('og-student', password='x',
                                           role='student')
        self.group.students.add(student)
        return [
            reverse('teacher:groups'),
            reverse('teacher:group_detail', args=[self.group.pk]),
            reverse('teacher:group_assignment', args=[self.group.pk, work.pk]),
            reverse('teacher:group_create'),
            reverse('teacher:problem_list'),
            reverse('teacher:problem_new'),
            reverse('teacher:work_pick'),
            reverse('teacher:work_compose'),
            reverse('teacher:work_give'),
            reverse('teacher:assignment_generate'),
            reverse('teacher:student_progress', args=[student.pk]),
        ]

    def test_suffix_appears_once_on_every_screen(self):
        for url in self.screens():
            html = self.client.get(url).content.decode()
            title = re.search(r'<title>(.*?)</title>', html, re.S)
            self.assertIsNotNone(title, url)
            self.assertEqual(title.group(1).count('ЭкЗадачи'), 1,
                             '%s: %s' % (url, title.group(1)))

    def test_the_suffix_lives_in_the_base_template(self):
        base = read('teacher', 'templates', 'teacher', 'base.html')
        self.assertIn('{% block title %}', base)
        self.assertIn('— ЭкЗадачи</title>', base)

    def test_no_page_adds_it_by_hand(self):
        """⚠️ Проверка обходит ВСЕ шаблоны кабинета: дефект завёлся тем, что
        суффикс дописывали руками на отдельных страницах."""
        base = os.path.join(ROOT, 'teacher', 'templates')
        found = []
        for folder, _, files in os.walk(base):
            for name in files:
                if not name.endswith('.html') or name == 'base.html':
                    continue
                text = read(os.path.join(folder, name))
                for block in re.findall(r'\{% block title %\}(.*?)'
                                        r'\{% endblock %\}', text, re.S):
                    if 'ЭкЗадачи' in block:
                        found.append(os.path.join(folder, name))
        self.assertEqual(found, [], 'суффикс дописан руками: %s' % found)
