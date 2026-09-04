# -*- coding: utf-8 -*-
"""Радар «Разделы экономики» считает настоящую работу, а не «рандомные числа».

До 04.09.2026 радар раскладывал темы по КЛЮЧЕВЫМ СЛОВАМ в названии
(`'монопол' in name` → «Фирма и рынки»), и владелец справедливо говорил, что
числа на нём непонятно откуда. Теперь блок темы берётся из общего модуля
`problems/sections.py` по точному имени.

Главная проверка здесь — не форма ответа, а СМЫСЛ: ученик, решавший задачи
ровно по двум блокам, обязан увидеть ненулевые значения ровно в этих двух
блоках и нули во всех остальных.
"""
from django.test import TestCase

from problems import stats
from problems.models import LearningEvent, Problem, Topic, User


class SectionRadarShapeTests(TestCase):
    """Форма ответа: пять осей в договорённом порядке, подписи короткие."""

    def test_five_axes_in_order(self):
        radar = stats.section_radar(None, rows=[])
        self.assertEqual([r['name'] for r in radar],
                         ['Микро', 'Макро', 'Финансы', 'Математика', 'Прочее'])

    def test_empty_user_gets_zeros_not_noise(self):
        radar = stats.section_radar(None, rows=[])
        self.assertEqual([r['attempted'] for r in radar], [0, 0, 0, 0, 0])
        self.assertEqual([r['accuracy'] for r in radar], [0, 0, 0, 0, 0])


class SectionRadarCountsTests(TestCase):
    """Числа попадают в тот блок, которому тема действительно принадлежит."""

    def _radar(self, rows):
        return {r['name']: r for r in stats.section_radar(None, rows=rows)}

    def test_topic_lands_in_its_own_section(self):
        rows = [
            {'name': 'Монополия и ценовая дискриминация', 'attempted': 4, 'solved': 2},
            {'name': 'Фискальная политика', 'attempted': 6, 'solved': 3},
        ]
        radar = self._radar(rows)
        self.assertEqual(radar['Микро']['attempted'], 4)
        self.assertEqual(radar['Макро']['attempted'], 6)
        self.assertEqual(radar['Финансы']['attempted'], 0)

    def test_accuracy_is_computed_per_section(self):
        rows = [
            {'name': 'Эластичность', 'attempted': 10, 'solved': 7},
            {'name': 'Спрос и предложение', 'attempted': 10, 'solved': 3},
        ]
        radar = self._radar(rows)
        # Оба «Микро»: 20 попыток, 10 верных → 50 %.
        self.assertEqual(radar['Микро']['attempted'], 20)
        self.assertEqual(radar['Микро']['accuracy'], 50)

    def test_unknown_topic_goes_to_other_not_to_a_guess(self):
        """Раньше «Монополия на рынке мороженого» уехала бы в чужой блок.

        Именно на таком угадывании по подстроке и строились неверные числа.
        """
        rows = [{'name': 'Монополия на рынке мороженого',
                 'attempted': 5, 'solved': 5}]
        radar = self._radar(rows)
        self.assertEqual(radar['Прочее']['attempted'], 5)
        self.assertEqual(radar['Микро']['attempted'], 0)


class SectionRadarLiveUserTests(TestCase):
    """Сквозная проверка: настоящий ученик, настоящие события, настоящие темы."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='radar_probe', password='x' * 12, role='student')
        # slug задаём руками: он уникален, а из кириллицы slugify даёт
        # пустую строку — вторая тема упёрлась бы в ограничение.
        self.topics = {}
        for index, name in enumerate((
                'Эластичность',                       # Микро
                'Фискальная политика',                # Макро
                'Финансы и финансовые инструменты')):  # Финансы
            self.topics[name] = Topic.objects.create(
                name=name, slug='radar-probe-%d' % index)

    def _solve(self, topic_name, correct, wrong):
        topic = self.topics[topic_name]
        # Радар считает по теме СОБЫТИЯ (LearningEvent.topic); задача нужна
        # лишь потому, что служебные отметки без задачи в счёт не идут.
        problem = Problem.objects.create(statement='условие')
        for _ in range(correct):
            LearningEvent.objects.create(
                user=self.user, event_type='solved', source='catalog',
                catalog_problem=problem, topic=topic)
        for _ in range(wrong):
            LearningEvent.objects.create(
                user=self.user, event_type='failed', source='catalog',
                catalog_problem=problem, topic=topic)

    def test_only_touched_sections_are_non_zero(self):
        """Решал по двум блокам — ненулевые ровно два, остальные нули."""
        self._solve('Эластичность', correct=3, wrong=1)          # Микро: 4/3
        self._solve('Фискальная политика', correct=1, wrong=3)   # Макро: 4/1

        radar = {r['name']: r for r in stats.section_radar(self.user, 'all')}

        self.assertEqual(radar['Микро']['attempted'], 4)
        self.assertEqual(radar['Микро']['accuracy'], 75)
        self.assertEqual(radar['Макро']['attempted'], 4)
        self.assertEqual(radar['Макро']['accuracy'], 25)

        for empty in ('Финансы', 'Математика', 'Прочее'):
            self.assertEqual(radar[empty]['attempted'], 0,
                             'блок %s получил чужие попытки' % empty)
            self.assertEqual(radar[empty]['accuracy'], 0)

    def test_third_section_lights_up_only_when_touched(self):
        self._solve('Эластичность', correct=2, wrong=0)
        before = {r['name']: r['attempted']
                  for r in stats.section_radar(self.user, 'all')}
        self.assertEqual(before['Финансы'], 0)

        self._solve('Финансы и финансовые инструменты', correct=5, wrong=0)
        after = {r['name']: r['attempted']
                 for r in stats.section_radar(self.user, 'all')}
        self.assertEqual(after['Финансы'], 5)
        self.assertEqual(after['Микро'], 2, 'чужой блок изменился сам собой')
