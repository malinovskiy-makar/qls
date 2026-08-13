"""
Обзор кабинета 13.08.2026, фаза 11 — «Мои задачи».

Пункты владельца 70, 71:
  • три задачи из шести назывались «Без названия»;
  • у строки не было ни кнопки, ни признака, что по ней можно нажать.
"""
import os
import re

from django.test import TestCase
from django.urls import reverse

from problems.models_platform import CustomProblem
from problems.tests.factories import make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class MyProblemsTests(TestCase):
    def setUp(self):
        self.tutor = make_user('mp_tutor', role='teacher')
        self.named = CustomProblem.objects.create(
            owner=self.tutor, title='Монополия и излишки',
            statement='Условие про монополию.')
        self.unnamed = CustomProblem.objects.create(
            owner=self.tutor, title='',
            statement='Спрос задан функцией Qd = 100 - 2P, предложение '
                      'Qs = 3P. Найдите равновесную цену и объём.')
        self.client.force_login(self.tutor)

    def _rows(self):
        html = self.client.get(reverse('teacher:problem_list')).content.decode()
        return re.findall(r'<span class="row-main">(.*?)</span>', html, re.S)

    # ---- 11.1 название ------------------------------------------------
    def test_no_more_without_a_name(self):
        for row in self._rows():
            self.assertNotIn('Без названия', row)

    def test_unnamed_shows_the_beginning_of_the_statement(self):
        rows = self._rows()
        found = [r.strip() for r in rows if r.strip().startswith('Спрос задан')]
        self.assertEqual(len(found), 1, rows)
        self.assertTrue(found[0].endswith('…'), found[0])

    def test_the_name_wins_when_it_is_there(self):
        self.assertIn('Монополия и излишки', [r.strip() for r in self._rows()])

    def test_cut_is_on_a_word_boundary(self):
        """Обрубок посреди слова читать нельзя — правило `preview_title`."""
        row = [r.strip() for r in self._rows() if r.strip().startswith('Спрос')][0]
        self.assertNotIn('-…', row)
        self.assertFalse(re.search(r'[а-яА-Я]…$', row) and len(row) > 82, row)

    def test_the_same_helper_as_everywhere(self):
        """Второй обрезки заголовка в проекте нет."""
        view = read('teacher', 'views_problems.py')
        self.assertIn('from problems.text_clean import preview_title', view)

    def test_a_problem_without_a_statement_still_has_a_line(self):
        empty = CustomProblem.objects.create(owner=self.tutor, title='',
                                             statement='')
        rows = [r.strip() for r in self._rows()]
        self.assertIn('Задача #%d' % empty.pk, rows)

    # ---- 11.2 кликабельность ------------------------------------------
    def test_row_says_what_it_does(self):
        html = self.client.get(reverse('teacher:problem_list')).content.decode()
        self.assertEqual(html.count('class="row-go"'), 2)
        self.assertIn('правка →', html)

    def test_whole_row_is_a_link(self):
        html = self.client.get(reverse('teacher:problem_list')).content.decode()
        self.assertIn('<a class="row-link" href="%s"'
                      % reverse('teacher:problem_edit', args=[self.named.pk]),
                      html)

    def test_row_styles_live_in_the_kit(self):
        """Они лежали в стилях экрана группы, который этот экран не подключает.

        ⚠️ Ровно поэтому строка и была голой браузерной ссылкой: ни карточки,
        ни рамки, ни наведения.
        """
        kit = read('templates', '_kit.html')
        self.assertIn('.row-link {', kit)
        self.assertIn('.row-link:hover', kit)
        self.assertIn('.row-go {', kit)

    def test_no_second_set_of_the_same_rules(self):
        style = read('teacher', 'templates', 'teacher', 'groups',
                     '_style.html')
        self.assertNotIn('.row-link {', style)
        self.assertNotIn('.row-link:hover', style)

    def test_the_kit_is_included_on_this_screen(self):
        base = read('problems', 'templates', 'platform', 'base.html')
        self.assertIn("_kit.html", base)

    def test_keyboard_gets_a_focus_ring(self):
        """Наведения нет ни у клавиатуры, ни на сенсорном экране."""
        kit = read('templates', '_kit.html')
        self.assertIn('.row-link:focus-visible', kit)
