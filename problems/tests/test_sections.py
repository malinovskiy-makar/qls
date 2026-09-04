# -*- coding: utf-8 -*-
"""Пять блоков разделов — сторож единственной точки правды.

Что здесь проверяется и почему именно это:

* покрытие 29 и 23 — чтобы новая тема не «провалилась в Прочее» молча;
* `section_of` по точному имени — чтобы никто не вернул сопоставление по
  подстрокам, из-за которого радар статистики показывал неверные числа;
* порядок блоков — он одинаков на всех экранах и это видимое обещание.
"""
from django.test import SimpleTestCase

from problems.management.commands.apply_topic_mapping import CANONICAL
from problems.sections import (
    CANONICAL_SECTION,
    SECTIONS,
    SECTION_KEYS,
    V2_SECTION_BY_NUMBER,
    V2_TOPIC_NAMES,
    grouped,
    section_of,
)


class SectionsShapeTests(SimpleTestCase):
    """Форма справочника: пять блоков в договорённом порядке."""

    def test_five_sections_in_agreed_order(self):
        self.assertEqual(
            SECTIONS,
            (('micro', 'Микро'), ('macro', 'Макро'), ('fin', 'Финансы'),
             ('math', 'Математика'), ('other', 'Прочее')),
        )


class V2CoverageTests(SimpleTestCase):
    """Все 29 тем таксономии v2 разложены, и ни одна не забыта."""

    def test_all_29_numbers_covered(self):
        self.assertEqual(sorted(V2_SECTION_BY_NUMBER), list(range(1, 30)))

    def test_every_number_has_a_known_section(self):
        unknown = {n: s for n, s in V2_SECTION_BY_NUMBER.items()
                   if s not in SECTION_KEYS}
        self.assertEqual(unknown, {})

    def test_borders_match_owner_decision(self):
        """Границы блоков — решение владельца 04.09, а не догадка."""
        self.assertEqual(V2_SECTION_BY_NUMBER[1], 'micro')     # Введение
        self.assertEqual(V2_SECTION_BY_NUMBER[15], 'micro')    # Межд. торговля
        self.assertEqual(V2_SECTION_BY_NUMBER[16], 'macro')    # Открытая экономика
        self.assertEqual(V2_SECTION_BY_NUMBER[23], 'macro')    # Рост и циклы
        self.assertEqual(V2_SECTION_BY_NUMBER[24], 'fin')
        self.assertEqual(V2_SECTION_BY_NUMBER[25], 'fin')
        self.assertEqual(V2_SECTION_BY_NUMBER[26], 'other')    # Поведенческая
        self.assertEqual(V2_SECTION_BY_NUMBER[27], 'math')
        self.assertEqual(V2_SECTION_BY_NUMBER[28], 'math')
        self.assertEqual(V2_SECTION_BY_NUMBER[29], 'other')    # Другое

    def test_names_cover_all_29(self):
        self.assertEqual(sorted(V2_TOPIC_NAMES), list(range(1, 30)))


class CanonicalCoverageTests(SimpleTestCase):
    """Все 23 живые темы разложены — ровно 23 ключа, ни одного лишнего."""

    def test_exactly_23_keys(self):
        self.assertEqual(len(CANONICAL_SECTION), 23)

    def test_every_canonical_topic_is_placed(self):
        missing = [name for name in CANONICAL if name not in CANONICAL_SECTION]
        self.assertEqual(
            missing, [],
            'тема живого канона не разложена по блокам — на экране она '
            'молча уедет в «Прочее»',
        )

    def test_no_stray_keys(self):
        stray = [name for name in CANONICAL_SECTION if name not in CANONICAL]
        self.assertEqual(stray, [], 'в словаре есть темы, которых нет в каноне')

    def test_every_section_used(self):
        used = set(CANONICAL_SECTION.values())
        self.assertEqual(used, set(SECTION_KEYS),
                         'какой-то блок не получил ни одной живой темы')


class SectionOfTests(SimpleTestCase):
    """Сопоставление по ТОЧНОМУ имени, без подстрок."""

    def test_known_canonical_names(self):
        self.assertEqual(section_of('Монополия и ценовая дискриминация'), 'micro')
        self.assertEqual(section_of('Фискальная политика'), 'macro')
        self.assertEqual(section_of('Финансы и финансовые инструменты'), 'fin')
        self.assertEqual(section_of('Математика и оптимизация'), 'math')
        self.assertEqual(section_of('Поведенческая экономика'), 'other')

    def test_known_v2_names(self):
        self.assertEqual(section_of('Международная торговля'), 'micro')
        self.assertEqual(section_of('Открытая экономика и валютный рынок'), 'macro')
        self.assertEqual(section_of('Данные, статистика и причинность'), 'math')

    def test_unknown_name_falls_to_other(self):
        self.assertEqual(section_of('Такой темы нет в проекте'), 'other')
        self.assertEqual(section_of(''), 'other')
        self.assertEqual(section_of(None), 'other')

    def test_substring_does_not_decide(self):
        """Раньше «монопол» в названии утаскивало тему в чужой блок.

        Проверяем именно это: похожее, но НЕ каноническое имя обязано уйти
        в «Прочее», а не быть угаданным по куску слова.
        """
        self.assertEqual(section_of('Монополия на рынке мороженого'), 'other')
        self.assertEqual(section_of('Спрос'), 'other')

    def test_whitespace_is_forgiven(self):
        self.assertEqual(section_of('  Эластичность  '), 'micro')


class GroupedTests(SimpleTestCase):
    """Сборка блоков для экрана."""

    def test_order_and_content(self):
        names = ['Фискальная политика', 'Эластичность',
                 'Математика и оптимизация', 'Спрос и предложение']
        result = grouped(names)
        self.assertEqual([k for k, _, _ in result], ['micro', 'macro', 'math'])
        self.assertEqual(result[0][2], ['Эластичность', 'Спрос и предложение'])
        self.assertEqual(result[1][1], 'Макро')

    def test_empty_sections_are_dropped(self):
        result = grouped(['Эластичность'])
        self.assertEqual([k for k, _, _ in result], ['micro'])

    def test_empty_input(self):
        self.assertEqual(grouped([]), [])
