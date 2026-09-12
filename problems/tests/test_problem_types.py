# -*- coding: utf-8 -*-
"""Таксономия `problem_type` — одна точка правды на каталог и на игру.

Зачем эти тесты. Обогащение v2 переписало `problem_type` новыми именами
(`единственный_выбор` и соседи), а каталог сравнивал поле со строками
СТАРОГО словаря. Итог: живых интерактивных виджетов теста в каталоге стало
ноль на весь банк, при том что игра работала — у неё случайно оказались оба
словаря сразу. Сторож ниже ловит ровно этот класс расхождения: он требует,
чтобы ОБЕ поверхности читали `problems.problem_types`, и чтобы обе
понимали ОБА словаря названий. Второй словарь никуда не денется — старым
размечен боевой сервер.
"""
from django.test import TestCase

from catalog import filters, testplay
from problems import problem_types as PT
from problems.hw_generator import is_test_problem
from problems.models import Problem, ProblemPart
from problems.tests.factories import make_problem

#: По одному живому имени каждого вида из КАЖДОГО словаря.
OLD_NAMES = {
    PT.SINGLE: 'тест: один ответ',
    PT.BOOLEAN: 'тест: верно/неверно',
    PT.MULTI: 'тест: все верные',
    PT.NUMERIC: 'тест: числовой ответ',
}
V2_NAMES = {
    PT.SINGLE: 'единственный_выбор',
    PT.BOOLEAN: 'верно_неверно',
    PT.MULTI: 'множественный_выбор',
    PT.NUMERIC: 'тест: короткий ответ',
}

#: Значения банка, которые тестом НЕ являются и не должны им стать.
NOT_TESTS = (
    'задача с развёрнутым ответом', 'несколько_подвопросов', 'не_задача',
    'сопоставление', '', None, 'что-то новое',
)


class TaxonomyTests(TestCase):
    def test_both_dictionaries_cover_all_four_kinds(self):
        for kind in PT.TEST_KINDS:
            self.assertEqual(PT.test_kind(OLD_NAMES[kind]), kind, OLD_NAMES[kind])
            self.assertEqual(PT.test_kind(V2_NAMES[kind]), kind, V2_NAMES[kind])

    def test_non_tests_are_not_tests(self):
        for value in NOT_TESTS:
            self.assertIsNone(PT.test_kind(value), repr(value))
            self.assertFalse(PT.is_test(value), repr(value))

    def test_types_by_kind_is_the_inverse_of_the_dictionary(self):
        seen = set()
        for kind, values in PT.TYPES_BY_KIND.items():
            self.assertTrue(values, kind)     # у вида есть хоть одно имя
            for value in values:
                self.assertEqual(PT.TEST_KIND_BY_TYPE[value], kind)
                seen.add(value)
        self.assertEqual(seen, set(PT.TEST_TYPE_VALUES))

    def test_v2_values_are_a_subset_with_a_kind(self):
        self.assertTrue(PT.V2_TYPE_VALUES <= set(PT.TEST_TYPE_VALUES))


class BothSurfacesReadTheSameSourceTests(TestCase):
    """Каталог и игра берут сопоставление ИЗ ОДНОГО МЕСТА, а не из копий."""

    def test_game_pool_dictionary_is_the_shared_one(self):
        from game.management.commands.build_game_pool import (
            GAME_TYPES, TAXONOMY_V2_GAME_TYPES,
        )
        self.assertEqual(GAME_TYPES, dict(PT.TEST_KIND_BY_TYPE))
        self.assertEqual(set(TAXONOMY_V2_GAME_TYPES), set(PT.V2_TYPE_VALUES))

    def test_catalog_filter_offers_kinds_not_raw_strings(self):
        self.assertEqual([value for value, _label in filters.TEST_TYPES],
                         list(PT.TEST_KINDS))


class WidgetLivesOnBothDictionariesTests(TestCase):
    """Виджет каталога включается от ОБОИХ словарей — это и был баг."""

    def _make(self, problem_type, answer, labels):
        problem = make_problem('Условие.', problem_type=problem_type,
                               answer=answer)
        for i, label in enumerate(labels, start=1):
            ProblemPart.objects.create(problem=problem, label=label,
                                       statement='Вариант %s' % label, order=i)
        return problem

    def test_single_and_multi_play_under_v2_names(self):
        single = self._make(V2_NAMES[PT.SINGLE], 'б', 'абвг')
        game = testplay.game_of(single)
        self.assertIsNotNone(game, 'единственный_выбор не получил виджета')
        self.assertFalse(game['multi'])
        self.assertEqual(game['correct'], {'б'})

        multi = self._make(V2_NAMES[PT.MULTI], 'аб', 'абвг')
        game = testplay.game_of(multi)
        self.assertIsNotNone(game, 'множественный_выбор не получил виджета')
        self.assertTrue(game['multi'])
        self.assertEqual(game['correct'], {'а', 'б'})

    def test_old_names_keep_playing(self):
        """Боевой сервер размечен старым словарём — он не должен погаснуть."""
        old_multi = self._make(OLD_NAMES[PT.MULTI], 'аб', 'абвг')
        self.assertTrue(testplay.game_of(old_multi)['multi'])
        old_single = self._make(OLD_NAMES[PT.SINGLE], 'б', 'абвг')
        self.assertFalse(testplay.game_of(old_single)['multi'])

    def test_numeric_has_no_option_widget_by_design(self):
        """`numeric` — короткий ответ, вариантов у него нет вовсе.

        Поля ввода короткого ответа в каталоге сегодня НЕ СУЩЕСТВУЕТ, и
        заводить его — отдельная работа. Пока его нет, честный ответ
        `game_of` — None, а не пустой виджет.
        """
        for name in (OLD_NAMES[PT.NUMERIC], V2_NAMES[PT.NUMERIC]):
            problem = make_problem('Сколько?', problem_type=name, answer='42')
            self.assertIsNone(testplay.game_of(problem), name)

    def test_open_problem_never_gets_a_widget(self):
        problem = self._make('задача с развёрнутым ответом', 'а', 'абв')
        self.assertIsNone(testplay.game_of(problem))


class QuerySideAgreesWithPythonSideTests(TestCase):
    """Отбор в базе и признак в Python обязаны совпадать до задачи."""

    def setUp(self):
        self.by_type = {}
        for name in list(OLD_NAMES.values()) + list(V2_NAMES.values()) + [
                'задача с развёрнутым ответом', 'несколько_подвопросов']:
            self.by_type[name] = make_problem('Условие.', problem_type=name)

    def test_filter_kind_test_matches_is_test(self):
        base = Problem.objects.all()
        active = dict(filters.parse({}), kind='test')
        in_db = set(filters.apply(base, active).values_list('problem_type', flat=True))
        in_python = {name for name in self.by_type if PT.is_test(name)}
        self.assertEqual(in_db, in_python)

    def test_filter_kind_open_is_the_complement(self):
        base = Problem.objects.all()
        active = dict(filters.parse({}), kind='open')
        in_db = set(filters.apply(base, active).values_list('problem_type', flat=True))
        self.assertEqual(in_db, {name for name in self.by_type if not PT.is_test(name)})

    def test_filter_by_kind_picks_up_both_dictionaries(self):
        base = Problem.objects.all()
        for kind in PT.TEST_KINDS:
            active = dict(filters.parse({}), kind='test', test_type=kind)
            names = set(filters.apply(base, active)
                        .values_list('problem_type', flat=True))
            self.assertEqual(names, {OLD_NAMES[kind], V2_NAMES[kind]}, kind)

    def test_homework_picker_sees_the_same_tests(self):
        for name, problem in self.by_type.items():
            self.assertEqual(is_test_problem(problem), PT.is_test(name), name)
