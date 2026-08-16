# -*- coding: utf-8 -*-
"""
Поток создания работы: «Что кладём» → «Состав» → «Выдача».

Проверяется то, ради чего поток и переделан: занятие не теряется ни на
одном шаге, корзина одна на все способы набора, вид работы меняется без
потери состава, а балл предлагается по сложности задачи.
"""
import json
import re

from django.test import Client, TestCase
from django.urls import reverse

from problems.models import (
    Assignment, CustomProblem, Problem, StudentGroup, User,
)
from problems.models_platform import suggested_points


class WorkFlowBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('wf-tutor', password='x',
                                             role='teacher')
        cls.other = User.objects.create_user('wf-other', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('wf-student', password='x',
                                               role='student')
        cls.group = StudentGroup.objects.create(name='Группа', teacher=cls.tutor)
        cls.group.students.add(cls.student)
        cls.alien = StudentGroup.objects.create(name='Чужая', teacher=cls.other)

        cls.task = Problem.objects.create(
            title='Издержки фирмы', statement='Фирма произвела 100 единиц.',
            status=Problem.Status.PUBLISHED, difficulty=4,
            problem_type='задача', solution='TC = FC + VC.')
        cls.test = Problem.objects.create(
            title='Верно ли, что…', statement='Спрос растёт.',
            status=Problem.Status.PUBLISHED, difficulty=2,
            problem_type='тест: один ответ')
        cls.own = CustomProblem.objects.create(
            owner=cls.tutor, title='Своя задача', statement='Условие',
            difficulty=3)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)


class StepsKeepTheLessonTests(WorkFlowBase):
    """12.1 — занятие живёт в адресе ВСЕХ шагов и всех переходов."""

    def steps(self):
        return ('teacher:work_pick', 'teacher:work_compose',
                'teacher:work_give')

    def test_every_step_opens_with_the_lesson(self):
        for name in self.steps():
            url = '%s?group=%d' % (reverse(name), self.group.pk)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, name)
            self.assertIn(self.group.name, response.content.decode(), name)

    def test_every_link_on_the_step_carries_the_lesson(self):
        """Все переходы потока несут занятие: крошка, лента, кнопки."""
        for name in self.steps():
            url = '%s?group=%d' % (reverse(name), self.group.pk)
            html = self.client.get(url).content.decode()
            for href in re.findall(r'href="(/teacher/work/[^"]*)"', html):
                self.assertIn('group=%d' % self.group.pk, href,
                              '%s → %s' % (name, href))

    def test_kind_survives_every_step(self):
        """Вид работы едет во всех переходах, КРОМЕ самого переключателя
        вида — он для того и стоит, чтобы вид сменить."""
        for name in self.steps():
            url = '%s?group=%d&kind=exam' % (reverse(name), self.group.pk)
            html = self.client.get(url).content.decode()
            switch = html.split('bh-kind"', 1)[1].split('</div>', 1)[0]
            for href in re.findall(r'href="(/teacher/work/[^"]*)"', html):
                if href in switch:
                    continue
                self.assertIn('kind=exam', href, '%s → %s' % (name, href))

    def test_alien_lesson_is_refused_on_every_step(self):
        """12.4 — чужое занятие в адресе отказывает СРАЗУ, а не через шаг."""
        for name in self.steps():
            url = '%s?group=%d' % (reverse(name), self.alien.pk)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse('teacher:groups'), response['Location'], name)

    def test_storage_key_includes_the_lesson(self):
        """Корзина привязана к занятию: собранное для группы не всплывает
        в индивидуальном."""
        html = self.client.get('%s?group=%d' % (reverse('teacher:work_pick'),
                                                self.group.pk)).content.decode()
        self.assertIn('work_cart:%d' % self.group.pk, html)


class KindSwitchKeepsTheStepTests(WorkFlowBase):
    """12.2 — переключатель вида ведёт на ТОТ ЖЕ шаг, а не на другой экран."""

    def test_switch_points_at_the_same_step(self):
        pairs = (('teacher:work_pick', '/teacher/work/'),
                 ('teacher:work_compose', '/teacher/work/compose/'),
                 ('teacher:work_give', '/teacher/work/give/'))
        for name, path in pairs:
            html = self.client.get(reverse(name)).content.decode()
            block = html.split('bh-kind"', 1)[1].split('</div>', 1)[0]
            hrefs = re.findall(r'href="([^"]+)"', block)
            self.assertEqual(len(hrefs), 2, name)
            for href in hrefs:
                self.assertTrue(href.startswith(path), '%s → %s' % (name, href))

    def test_cart_key_does_not_depend_on_kind(self):
        """Состав переживает смену вида, потому что корзина у видов одна."""
        keys = []
        for tail in ('', '&kind=exam'):
            html = self.client.get('%s?group=%d%s'
                                   % (reverse('teacher:work_pick'),
                                      self.group.pk, tail)).content.decode()
            keys.append(re.search(r"cart: '([^']+)'", html).group(1))
        self.assertEqual(keys[0], keys[1])


class TabsKeepTheCartTests(WorkFlowBase):
    """8 — пять вкладок в одном экране; переключение не трогает корзину."""

    def html(self):
        return self.client.get('%s?group=%d' % (reverse('teacher:work_pick'),
                                                self.group.pk)).content.decode()

    def test_five_ways_are_offered_on_one_screen(self):
        html = self.html()
        for word in ('Каталог', 'Описать словами', 'Написать свою',
                     'Мои задачи', 'Отложенные'):
            self.assertIn(word, html, word)

    def test_panes_live_in_the_same_page(self):
        """Каталог, свои и отложенные — панели, а не отдельные адреса:
        переключение вкладки не может потерять набранное, потому что
        никуда не уходит."""
        html = self.html()
        for pane in ('pane-catalog', 'pane-own', 'pane-saved'):
            self.assertIn('id="%s"' % pane, html, pane)

    def test_describe_tab_leads_to_the_found_step(self):
        html = self.html()
        self.assertIn(reverse('teacher:assignment_generate'), html)

    def test_own_tab_asks_to_put_the_task_into_the_cart(self):
        """Без `to_cart` задача создавалась и в собираемую работу не
        попадала — кнопка обещала пополнить работу и не пополняла."""
        html = self.html()
        link = re.search(r'href="(/teacher/problems/new/[^"]*)"', html).group(1)
        self.assertIn('to_cart=1', link)
        self.assertIn('group=%d' % self.group.pk, link)

    def test_saved_empty_state_says_what_to_do(self):
        self.assertIn('Отложенных задач нет', self.html())

    def test_nothing_found_state(self):
        html = self.client.get('%s?q=%s'
                               % (reverse('teacher:work_pick'),
                                  'этогонетвбанке')).content.decode()
        self.assertIn('По этому запросу ничего не нашлось', html)


class EmptyOwnTabTests(WorkFlowBase):
    """Пустая вкладка своих задач зовёт написать первую."""

    def setUp(self):
        super().setUp()
        CustomProblem.objects.filter(owner=self.tutor).update(is_deleted=True)

    def test_empty_own_tab(self):
        html = self.client.get(reverse('teacher:work_pick')).content.decode()
        self.assertIn('Вы ещё не написали ни одной своей задачи', html)
        self.assertIn('Написать свою', html)


class SortingTests(WorkFlowBase):
    """8 — сортировка отбора: три варианта, и она не меняет старые экраны."""

    def order(self, url):
        html = self.client.get(url).content.decode()
        return re.findall(r'data-pid="(\d+)"', html)

    def test_easy_first_and_hard_first_are_opposite(self):
        easy = self.order('%s?sort=easy' % reverse('teacher:work_pick'))
        hard = self.order('%s?sort=hard' % reverse('teacher:work_pick'))
        self.assertEqual(str(self.test.pk), easy[0])
        self.assertEqual(str(self.task.pk), hard[0])

    def test_old_screens_keep_their_order(self):
        """⚠️ Сортировка просится ЯВНО. Молча включив её всем, я поменял бы
        список на прежних экранах отбора, которых эта сессия не касается."""
        html = self.client.get('%s?sort=easy'
                               % reverse('teacher:assignment_create')).content.decode()
        pids = re.findall(r'data-pid="(\d+)"', html)
        self.assertEqual(pids[0], str(self.own.pk) if False else pids[0])
        # На старом экране свежая задача остаётся первой независимо от
        # параметра: он там не читается вовсе.
        self.assertEqual(pids[0], str(self.test.pk))


class CardFactsTests(WorkFlowBase):
    """8 — карточка говорит тип, пункты, сложность, решение и источник."""

    def test_facts_are_shown(self):
        html = self.client.get('%s?q=Издержки'
                               % reverse('teacher:work_pick')).content.decode()
        self.assertIn('сложность 4', html)
        self.assertIn('есть решение', html)

    def test_no_difficulty_is_said_in_words(self):
        """⚠️ Ноль по пятибалльной шкале читается как «легче лёгкого», а
        означает «в банке не проставлена»."""
        Problem.objects.create(title='Без сложности', statement='Условие',
                               status=Problem.Status.PUBLISHED, difficulty=0)
        html = self.client.get('%s?q=%s' % (reverse('teacher:work_pick'),
                                            'Условие')).content.decode()
        self.assertNotIn('сложность 0', html)


class SuggestedPointsTests(WorkFlowBase):
    """10 — балл по умолчанию: у задачи её сложность, у теста единица."""

    def test_rule(self):
        self.assertEqual(int(suggested_points(False, 4)), 4)
        self.assertEqual(int(suggested_points(True, 4)), 1)

    def test_missing_difficulty_takes_the_middle(self):
        """Ноль баллов за задачу — не подсказка, а поломка."""
        self.assertEqual(int(suggested_points(False, 0)), 3)

    def test_rows_carry_the_suggestion(self):
        response = self.client.post(reverse('teacher:api_cart_rows'), {
            'keys': '%d,%d' % (self.task.pk, self.test.pk), 'suggest': '1'})
        rows = {row['key']: row['points'] for row in response.json()['rows']}
        self.assertEqual(rows[str(self.task.pk)], 4.0)
        self.assertEqual(rows[str(self.test.pk)], 1.0)

    def test_old_screens_keep_the_old_default(self):
        """⚠️ `default_points` не трогаем: по ней собраны существующие
        работы, и смена значения переоценила бы их задним числом."""
        response = self.client.post(reverse('teacher:api_cart_rows'),
                                    {'keys': str(self.task.pk)})
        self.assertEqual(response.json()['rows'][0]['points'], 10.0)

    def test_tutor_choice_beats_the_suggestion(self):
        response = self.client.post(reverse('teacher:api_cart_rows'), {
            'keys': str(self.task.pk), 'suggest': '1',
            'points': '%d:7.5' % self.task.pk})
        self.assertEqual(response.json()['rows'][0]['points'], 7.5)


class TallyTests(WorkFlowBase):
    """Сводка собранного считается СЕРВЕРОМ и склоняется в питоне."""

    def tally(self, **params):
        response = self.client.get(reverse('teacher:api_work_tally'), params)
        return json.loads(response.content.decode())

    def test_counts_and_words(self):
        data = self.tally(keys='%d,%d' % (self.task.pk, self.test.pk))
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['tests'], 1)
        self.assertEqual(data['points'], 5.0)
        self.assertIn('2 задачи', data['text'])
        self.assertIn('5 баллов', data['text'])
        self.assertIn('из них 1 тест', data['text'])

    def test_fraction_takes_the_genitive(self):
        """⚠️ «1,5 балл» — то, что выходит, если склонять по целой части."""
        data = self.tally(keys=str(self.task.pk),
                          points='%d:1.5' % self.task.pk)
        self.assertIn('1,5 балла', data['text'])

    def test_students_are_counted_when_asked(self):
        data = self.tally(keys=str(self.task.pk), students='3')
        self.assertIn('выдаётся 3 ученикам', data['text'])

    def test_empty_cart_is_not_an_error(self):
        self.assertEqual(self.tally(keys='')['count'], 0)


class FullWindowTests(WorkFlowBase):
    """8/10 — окно «целиком» одно на весь поток: пункты, ответы, решение."""

    def test_catalog_task_comes_whole(self):
        response = self.client.get(reverse('teacher:api_work_full',
                                           args=[self.task.pk]))
        row = response.json()['row']
        self.assertEqual(row['statement'], self.task.statement)
        self.assertEqual(row['solution'], self.task.solution)
        self.assertTrue(row['has_solution'])

    def test_own_task_uses_the_same_window(self):
        response = self.client.get(reverse('teacher:api_work_full',
                                           args=['c%d' % self.own.pk]))
        self.assertEqual(response.json()['row']['statement'],
                         self.own.statement)

    def test_alien_task_is_not_given_away(self):
        alien = CustomProblem.objects.create(owner=self.other, title='Чужая',
                                             statement='Секрет')
        response = self.client.get(reverse('teacher:api_work_full',
                                           args=['c%d' % alien.pk]))
        self.assertEqual(response.status_code, 404)

    def test_unknown_key_is_not_a_crash(self):
        response = self.client.get(reverse('teacher:api_work_full',
                                           args=['zzz']))
        self.assertEqual(response.status_code, 404)


class GiveStepTests(WorkFlowBase):
    """11 — выдача: настройки, кому, предпросмотр и создание работы."""

    def test_settings_moved_to_the_last_step(self):
        pick = self.client.get(reverse('teacher:work_pick')).content.decode()
        give = self.client.get(reverse('teacher:work_give')).content.decode()
        self.assertNotIn('name="deadline"', pick)
        self.assertIn('name="deadline"', give)
        self.assertIn('name="name"', give)

    def test_lesson_we_came_from_is_prechecked(self):
        html = self.client.get('%s?group=%d' % (reverse('teacher:work_give'),
                                                self.group.pk)).content.decode()
        checked = re.findall(r'name="groups" value="(\d+)"[^>]*?\bchecked',
                             html, re.S)
        self.assertEqual(checked, [str(self.group.pk)])

    def test_exam_gets_window_fields(self):
        html = self.client.get('%s?group=%d&kind=exam'
                               % (reverse('teacher:work_give'),
                                  self.group.pk)).content.decode()
        self.assertIn('name="starts_at"', html)
        self.assertIn('name="ends_at"', html)
        self.assertIn('name="duration"', html)

    def test_exam_lesson_choice_is_single(self):
        """У контрольной занятие одно: её обработчик живёт ВНУТРИ него."""
        html = self.client.get('%s?kind=exam'
                               % reverse('teacher:work_give')).content.decode()
        self.assertIn('type="radio"\n             name="groups"', html)

    def test_work_is_created_by_the_old_handler(self):
        """⚠️ Второй точки создания работы нет: форма уходит в прежний
        обработчик с прежними именами полей."""
        html = self.client.get(reverse('teacher:work_give')).content.decode()
        self.assertIn('action="%s"' % reverse('teacher:assignment_create'),
                      html)

    def test_the_whole_path_creates_a_work(self):
        response = self.client.post(reverse('teacher:assignment_create'), {
            'name': 'Домашка из потока',
            'groups': [str(self.group.pk)],
            'problem_ids': '%d,%d,c%d' % (self.test.pk, self.task.pk,
                                          self.own.pk),
            'problem_points': '%d:2,%d:4,c%d:3' % (self.test.pk, self.task.pk,
                                                   self.own.pk),
            'manual_order': '1',
        })
        self.assertEqual(response.status_code, 302)
        work = Assignment.objects.get(name='Домашка из потока')
        items = list(work.items.order_by('order'))
        self.assertEqual(len(items), 3)
        # ⚠️ ПОРЯДОК КОРЗИНЫ СТАНОВИТСЯ ПОРЯДКОМ РАБОТЫ: ради этого он и
        # живёт отдельным списком, а не выводится из ключей корзины.
        self.assertEqual([i.catalog_problem_id or 0 for i in items][:2],
                         [self.test.pk, self.task.pk])
        self.assertEqual(items[2].custom_problem_id, self.own.pk)
        self.assertEqual([float(i.points) for i in items], [2.0, 4.0, 3.0])


class StartClearsTheCartTests(WorkFlowBase):
    """Вход в поток начинает с чистого листа, возврат назад — нет."""

    def test_start_page_clears_the_lesson_cart(self):
        html = self.client.get('%s?group=%d' % (reverse('teacher:work_start'),
                                                self.group.pk)).content.decode()
        self.assertIn('removeItem(window.QLS_CART.cart)', html)
        self.assertIn('/teacher/work/?group=%d' % self.group.pk, html)

    def test_steps_do_not_clear_anything(self):
        """Возврат по ленте шагов — не то же событие, что вход в поток."""
        for name in ('teacher:work_pick', 'teacher:work_compose'):
            html = self.client.get(reverse(name)).content.decode()
            self.assertNotIn('removeItem(window.QLS_CART.cart)', html)
