# -*- coding: utf-8 -*-
"""
Шаг «Что кладём» — пять панелей одного экрана (фаза 2, mockup-work-step).

Причина, а не симптом. Из того, что «Описать словами» и «Написать свою»
были отдельными адресами, росло всё остальное: две ленты шагов на одном
экране, отсутствие ленты на другом, прыгающая ширина колонки. Симптомы
чинила функциональная сессия; здесь чинится причина.

  2.1 пять способов — панели одного экрана, переключение ничего не теряет;
  2.2 лента ВСЕГДА из трёх шагов; «Что нашлось» — второе состояние панели;
  2.3 названия способов одни на платформу, число ушло из скобок в подпись;
  2.5 поиск вдвое шире, выбор сортировки убран, счётчик в ряду с кнопками;
  2.6 положенная в работу карточка красится, а не приглушается;
  2.7 три кнопки под условием — в одной грамматике, списки не браузерные;
  2.8 счётчик обращений — отдельной строкой;
  2.9 выбранная задача помечена ОДНОЙ заливкой.
"""
import os
import re

from django.test import Client, TestCase
from django.urls import reverse

from problems.models import (
    CustomProblem, Problem, SavedProblem, StudentGroup, User,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class PickBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('lp-tutor', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Занятие',
                                                teacher=cls.tutor)
        cls.task = Problem.objects.create(
            title='Издержки фирмы', statement='Условие задачи',
            status=Problem.Status.PUBLISHED, problem_type='задача',
            difficulty=4, solution='Разбор')
        cls.mine = CustomProblem.objects.create(
            owner=cls.tutor, title='Моя', statement='Своё условие',
            kind=CustomProblem.Kind.OPEN, difficulty=2)
        SavedProblem.objects.create(owner=cls.tutor, catalog_problem=cls.task)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def page(self, query=''):
        response = self.client.get(reverse('teacher:work_pick') + query)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


# ══════════════════════════════════════════════════════════════════════════
# 2.1 — пять панелей одного экрана
# ══════════════════════════════════════════════════════════════════════════
class FivePanelsTests(PickBase):

    def test_four_panels_live_on_the_screen_itself(self):
        html = self.page()
        for pane in ('pane-catalog', 'pane-ai', 'pane-own', 'pane-saved'):
            self.assertIn('id="%s"' % pane, html, pane)

    def test_describing_no_longer_takes_you_away(self):
        """«Описать словами» была ссылкой на отдельный адрес."""
        html = self.page()
        self.assertIn('data-pane="pane-ai"', html)
        self.assertNotIn('href="%s"' % reverse('teacher:assignment_generate'),
                         html)

    def test_the_old_address_leads_into_the_panel(self):
        moved = self.client.get(reverse('teacher:assignment_generate')
                                + '?group=%d' % self.group.pk)
        self.assertEqual(moved.status_code, 302)
        self.assertIn('tab=ai', moved['Location'])
        self.assertIn('group=%d' % self.group.pk, moved['Location'])

    def test_the_address_says_which_panel_is_open(self):
        html = self.page('?tab=ai')
        opened = re.search(r'id="pane-ai" ([^>]*)>', html).group(1)
        self.assertNotIn('hidden', opened)
        closed = re.search(r'id="pane-catalog" ([^>]*)>', html).group(1)
        self.assertIn('hidden', closed)

    def test_the_lesson_and_the_kind_survive_the_switch(self):
        """Переключение вкладки — это показ панели, а не переход."""
        html = self.page('?group=%d&kind=exam&tab=ai' % self.group.pk)
        self.assertIn('group=%d' % self.group.pk, html)
        self.assertIn('kind=exam', html)

    def test_switching_a_tab_does_not_touch_the_cart(self):
        """Корзина живёт в хранилище занятия и вкладке не подчиняется."""
        script = read('teacher', 'templates', 'teacher', 'work', 'pick.html')
        tabs = script.split("tabs.addEventListener")[1].split('});')[0]
        for word in ('removeItem', 'clear('):
            self.assertNotIn(word, tabs, 'вкладка трогает корзину')

    def test_every_state_wears_the_same_row_of_ways(self):
        """Ряд способов — ОДИН партиал на все три места."""
        for path in (('teacher', 'templates', 'teacher', 'work', 'pick.html'),
                     ('teacher', 'templates', 'teacher', 'generate.html'),
                     ('problems', 'templates', 'platform',
                      'problem_form.html')):
            self.assertIn('teacher/work/_ways.html', read(*path), path[-1])

    def test_the_editor_stays_a_link_and_says_why(self):
        """Единственная вкладка-ссылка объяснена прямо в разметке."""
        ways = read('teacher', 'templates', 'teacher', 'work', '_ways.html')
        self.assertIn('ЕДИНСТВЕННАЯ ССЫЛКА ИЗ ПЯТИ', ways)


# ══════════════════════════════════════════════════════════════════════════
# 2.2 — лента всегда из трёх шагов
# ══════════════════════════════════════════════════════════════════════════
class ThreeStepsAlwaysTests(PickBase):

    def found(self):
        response = self.client.post(reverse('teacher:assignment_generate'), {
            'step_action': 'parse', 'text': 'издержки',
            'count_open': 1, 'count_test': 0,
            'min_difficulty': 1, 'max_difficulty': 5})
        return response.content.decode()

    def test_pick_has_three(self):
        self.assertEqual(self.page().count('class="wk-rail__s'), 3)

    def test_found_state_has_three_too(self):
        self.assertEqual(self.found().count('class="wk-rail__s'), 3)

    def test_the_editor_has_three(self):
        html = self.client.get(reverse('teacher:problem_new')
                               + '?to_cart=1').content.decode()
        self.assertEqual(html.count('class="wk-rail__s'), 3)

    def test_the_fourth_step_is_gone_from_the_partial(self):
        head = read('teacher', 'templates', 'teacher', 'work', '_head.html')
        self.assertNotIn('{% if found %}', head)

    def test_the_first_step_stays_lit_while_searching(self):
        """Разбор запроса — это по-прежнему первый шаг."""
        html = self.found()
        first = html.split('class="wk-rail__s')[1]
        self.assertTrue(first.startswith(' is-on'), first[:40])


# ══════════════════════════════════════════════════════════════════════════
# 2.3 — названия
# ══════════════════════════════════════════════════════════════════════════
class WayNamesTests(PickBase):

    NAMES = (('Искать самому', 'ручной поиск по каталогу'),
             ('Описать словами', 'умный поиск по каталогу'),
             ('Написать свою', 'создание задачи с нуля'))

    def test_the_three_ways_are_named_exactly(self):
        html = self.page()
        for name, note in self.NAMES:
            self.assertIn(name, html)
            self.assertIn(note, html)

    def test_the_count_moved_out_of_the_brackets(self):
        html = self.page()
        self.assertIn('1 написанная вами', html)
        self.assertIn('1 закладка каталога', html)
        self.assertNotIn('Мои задачи (', html)
        self.assertNotIn('Отложенные (', html)

    def test_names_are_the_same_on_every_state(self):
        pages = [self.page(),
                 self.client.get(reverse('teacher:problem_new')
                                 + '?to_cart=1').content.decode()]
        for html in pages:
            for name, note in self.NAMES:
                self.assertIn(name, html)
                self.assertIn(note, html)


# ══════════════════════════════════════════════════════════════════════════
# 2.5 — панель «Искать самому»
# ══════════════════════════════════════════════════════════════════════════
class CatalogPanelTests(PickBase):

    def test_search_is_twice_as_wide(self):
        kit = read('templates', '_kit.html')
        rule = re.search(r'\.wk-filters \{([^}]*)\}', kit).group(1)
        self.assertIn('grid-template-columns: 2fr 1fr 1fr 1fr', rule)

    def test_the_sort_control_is_gone(self):
        html = self.page()
        self.assertNotIn('name="sort"', html)
        self.assertNotIn('id="wk-sort"', html)

    def test_the_order_itself_did_not_change(self):
        """Порядок остался «сначала подходящие по теме», просто молча."""
        plain = re.findall(r'data-pid="(\d+)"', self.page())
        asked = re.findall(r'data-pid="(\d+)"', self.page('?sort=easy'))
        self.assertEqual(plain, asked)

    def test_the_counter_stands_with_the_buttons(self):
        html = self.page()
        row = html.split('class="wk-frow"')[1].split('</div>')[0]
        self.assertIn('Найти', row)
        self.assertIn('Сброс', row)
        self.assertIn('wk-count', row)


# ══════════════════════════════════════════════════════════════════════════
# 2.6 / 2.9 — выбор говорит заливкой, а не прозрачностью
# ══════════════════════════════════════════════════════════════════════════
class ChosenIsFilledTests(TestCase):

    def test_card_in_the_work_is_filled_not_dimmed(self):
        kit = read('templates', '_kit.html')
        rule = re.search(r'\.wk-card\.is-added \{([^}]*)\}', kit).group(1)
        self.assertIn('background: var(--green-tint)', rule)
        self.assertNotIn('opacity', rule)

    def test_the_button_answers_instead_of_going_grey(self):
        kit = read('templates', '_kit.html')
        rule = re.search(r'\.k-btn\.added[^{]*\{([^}]*)\}', kit).group(1)
        self.assertIn('opacity: 1', rule)
        self.assertIn('var(--green-tint)', rule)

    def test_picked_candidate_has_one_fill_and_no_second_border(self):
        markup = read('teacher', 'templates', 'teacher', 'generate.html')
        rule = re.search(r'\.cand\.is-picked \{([^}]*)\}', markup).group(1)
        self.assertIn('var(--green-tint)', rule)
        self.assertNotIn('accent', rule)

    def test_taken_candidate_is_not_dimmed_either(self):
        markup = read('teacher', 'templates', 'teacher', 'generate.html')
        self.assertNotIn('.cand.is-taken { opacity', markup)


# ══════════════════════════════════════════════════════════════════════════
# 2.7 / 2.8 — панель «Написать свою» и счётчик обращений
# ══════════════════════════════════════════════════════════════════════════
class OwnPanelTests(PickBase):

    def editor(self):
        return self.client.get(reverse('teacher:problem_new')
                               + '?to_cart=1').content.decode()

    def test_three_buttons_share_one_grammar(self):
        row = self.editor().split('id="statement-tools"')[1].split('</div>')[0]
        self.assertIn('Вставить график', row)
        self.assertIn('Создать график ↗', row)
        script = read('problems', 'static', 'platform', 'mathfield.js')
        self.assertIn("'Вставить формулу'", script)
        self.assertNotIn("'∑ Формула'", script)

    def test_the_formula_button_stands_before_the_outgoing_link(self):
        script = read('problems', 'static', 'platform', 'mathfield.js')
        self.assertIn('insertBefore(toggle, outgoing)', script)

    def test_selects_are_not_native(self):
        html = self.editor()
        for field in ('id_kind', 'id_topic', 'id_difficulty'):
            self.assertIn('<select class="k-select" id="%s"' % field, html,
                          field)
        # Стрелку рисует обёртка — без неё родная как раз и пропадёт.
        self.assertGreaterEqual(html.count('k-select-wrap'), 3)

    def test_the_letter_is_pressed_against_the_bracket(self):
        markup = read('problems', 'templates', 'platform',
                      'problem_form.html')
        rule = re.search(r'\.part-chip input \{([^}]*)\}', markup).group(1)
        self.assertIn('text-align: right', rule)

    def test_the_usage_counter_stands_on_its_own_line(self):
        panel = read('teacher', 'templates', 'teacher', '_ask_panel.html')
        actions = panel.split('class="gen-actions"')[1].split('</div>')[0]
        self.assertNotIn('gen-used', actions)
        self.assertIn('<div class="gen-used">', panel)


class AskPanelIsOneSourceTests(TestCase):
    """Разметка панели одна на два места — иначе они разойдутся."""

    def test_both_screens_include_the_same_partial(self):
        for path in (('teacher', 'templates', 'teacher', 'work', 'pick.html'),
                     ('teacher', 'templates', 'teacher', 'generate.html')):
            self.assertIn('teacher/_ask_panel.html', read(*path), path[-1])

    def test_styles_travel_with_it(self):
        """⚠️ Правила в файле, который второй экран не подключает, — знакомый
        по проекту класс дефекта."""
        for path in (('teacher', 'templates', 'teacher', 'work', 'pick.html'),
                     ('teacher', 'templates', 'teacher', 'generate.html')):
            self.assertIn('teacher/_ask_style.html', read(*path), path[-1])
