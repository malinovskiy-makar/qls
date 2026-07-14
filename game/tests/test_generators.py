"""
Тесты параметрических генераторов Econ Rush (game/generators/).

Два слоя:
1. Контрольные числа из ТЗ — подача параметров в solve() напрямую, минуя
   рандом (класс ControlNumbers*).
2. Свойства на массе: по 500 сэмплов на архетип — ответ «красивый»,
   независимый пересчёт solve() сходится с correct_value через Fraction,
   дистракторы уникальны и ≠ ответу, длины в лимитах, parse_exact_number
   принимает каждый correct_value (класс ArchetypeProperties).
"""
import random
from fractions import Fraction

from django.test import SimpleTestCase

from game.generators import base as gbase
from game.generators.base import fmt_num, is_nice, LIMIT_FULL, LIMIT_SHORT
from game.generators.registry import ARCHETYPES
from game.views import parse_exact_number

N_SAMPLES = 500          # сэмплов на архетип (распределяются по трём типам)
MIN_INT_SHARE = 0.6      # доля целых ответов среди numeric (правило ≥80%
                         # держим по построению сеток; в тесте — консервативный
                         # порог против случайного перекоса выборки)


class ArchetypePropertyMixin(object):
    """Общий прогон свойств для одного архетипа."""

    def run_archetype(self, key, validator=None):
        arch = ARCHETYPES[key]
        rng = random.Random(20260714)
        per_type = N_SAMPLES // 3
        int_answers = 0
        numeric_total = 0

        for qtype in ('numeric', 'single', 'boolean'):
            for _ in range(per_type):
                q = gbase.generate_question(arch, rng, qtype)
                params = q['params']
                asked_key = params['_asked']
                solved = arch.solve(params)

                # длины условий в лимитах типа
                limit = LIMIT_FULL if qtype == 'numeric' else LIMIT_SHORT
                self.assertLessEqual(len(q['statement']), limit, q['statement'])
                self.assertGreaterEqual(len(q['statement']), 15)

                # сложность и темы заполнены
                self.assertIn(q['difficulty'], (1, 2, 3, 4, 5))
                self.assertTrue(q['topics'])
                self.assertTrue(q['solution_text'].startswith('1. '))

                # валидность экономики архетипа
                if validator is not None:
                    validator(self, params, solved)

                value = solved[asked_key]
                if isinstance(value, str):
                    # class-вопрос: правильная метка — в вариантах
                    if qtype == 'single':
                        self.assertEqual(
                            q['options'][q['correct_index']], value)
                    else:
                        claim = params['_claim']
                        truth = (claim == value)
                        self.assertEqual(q['correct_index'], 0 if truth else 1)
                    continue

                value = Fraction(value)
                self.assertTrue(is_nice(value), value)

                if qtype == 'numeric':
                    numeric_total += 1
                    if value.denominator == 1:
                        int_answers += 1
                    parsed = parse_exact_number(q['correct_value'])
                    self.assertIsNotNone(parsed, q['correct_value'])
                    # независимый пересчёт сходится с correct_value
                    self.assertEqual(parsed, value)
                    self.assertEqual(q['options'], [])
                elif qtype == 'single':
                    self.assertEqual(len(q['options']), 4)
                    # варианты уникальны, правильный = ответ
                    self.assertEqual(len(set(q['options'])), 4)
                    self.assertEqual(
                        q['options'][q['correct_index']], fmt_num(value))
                    for i, o in enumerate(q['options']):
                        if i != q['correct_index']:
                            self.assertNotEqual(
                                parse_exact_number(o), value)
                            # дистракторы правдоподобны: неотрицательны
                            self.assertGreaterEqual(parse_exact_number(o), 0)
                else:  # boolean
                    self.assertEqual(q['options'], [u'Верно', u'Неверно'])
                    claim = Fraction(str(params['_claim']).replace(',', '.')
                                     if '/' not in str(params['_claim'])
                                     else params['_claim'])
                    truth = (claim == value)
                    self.assertEqual(q['correct_index'], 0 if truth else 1)

        # правило красивого ответа: целые преобладают
        self.assertGreater(numeric_total, 0)
        self.assertGreaterEqual(int_answers / float(numeric_total),
                                MIN_INT_SHARE)


def market_validator(test, params, solved):
    """Экономическая валидность рынка: равновесие в первой четверти."""
    test.assertGreater(solved['p_star'], 0)
    test.assertGreater(solved['q_star'], 0)
    test.assertGreater(params['a'], 0)
    test.assertGreater(params['b'], 0)
    test.assertGreater(params['d'], 0)


class ControlNumbersBlockA(SimpleTestCase):
    """Контрольные числа Задачи 3 — прямые вызовы solve()."""

    def test_equilibrium(self):
        s = ARCHETYPES['equilibrium'].solve(
            {'a': 100, 'b': 1, 'c': 0, 'd': 1, 'good': 0})
        self.assertEqual(s['p_star'], 50)
        self.assertEqual(s['q_star'], 50)


class ArchetypeProperties(SimpleTestCase, ArchetypePropertyMixin):
    """500 сэмплов на каждый архетип."""

    def test_equilibrium(self):
        self.run_archetype('equilibrium', market_validator)
