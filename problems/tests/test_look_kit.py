# -*- coding: utf-8 -*-
"""
Сквозные элементы визуальной сессии 17.08 (фаза 1, мокап mockup-elements).

Три вещи, от которых зависят все экраны кабинета сразу, — поэтому и
проверяются они в наборе деталей, а не на одном экране:

  1.1 число правится без поля ввода (`.k-num`);
  1.2 чип — сигнал, а не подпись: цвет остался у сложности и решения,
      тип отличается контуром, число пунктов чипом быть перестало;
  1.3 одно слово и один знак для «раскрыть».

⚠️ Контраст считаем ЧИСЛОМ, а не глазом: на этой ветке уже ловилось, что
`--error` в тёмной теме светлый и белым по нему выходит 2,78:1.
"""
import os
import re

from django.test import TestCase

from teacher.picker import card_facts

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


# ── Контраст: те же формулы, что в `test_obzor_review`. ────────────────────
def _lum(value):
    value = value.lstrip('#')
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(one, two):
    first, second = _lum(one), _lum(two)
    top, bottom = max(first, second), min(first, second)
    return (top + 0.05) / (bottom + 0.05)


def over(colour, alpha, below):
    """Полупрозрачный цвет поверх фона → сплошной."""
    top = [int(colour.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    base = [int(below.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    return '#%02x%02x%02x' % tuple(
        round(top[i] * alpha + base[i] * (1 - alpha)) for i in range(3))


class FakeProblem:
    def __init__(self, difficulty=0, solution=''):
        self.difficulty = difficulty
        self.solution = solution


# ══════════════════════════════════════════════════════════════════════════
# 1.1 — число без поля ввода
# ══════════════════════════════════════════════════════════════════════════
class NumberWithoutABoxTests(TestCase):

    def setUp(self):
        self.kit = read('templates', '_kit.html')
        self.rule = re.search(r'\n\.k-num \{(.*?)\}', self.kit, re.S)

    def test_kit_declares_the_element(self):
        self.assertIsNotNone(self.rule, 'правила .k-num в наборе нет')

    def test_only_the_bottom_line_is_left(self):
        body = self.rule.group(1)
        self.assertIn('border: 0', body)
        self.assertIn('border-bottom: 1px dashed var(--num-line)', body)
        self.assertIn('background: transparent', body)

    def test_tap_area_is_at_least_44px(self):
        """В полосу толщиной в пиксель пальцем не попасть."""
        found = re.search(r'min-height: (\d+)px', self.rule.group(1))
        self.assertIsNotNone(found, 'высота области нажатия не задана')
        self.assertGreaterEqual(int(found.group(1)), 44)

    def test_browser_arrows_are_hidden(self):
        self.assertIn('.k-num::-webkit-inner-spin-button', self.kit)
        self.assertIn('-moz-appearance: textfield', self.rule.group(1))

    def test_hover_and_focus_speak_with_the_line(self):
        self.assertIn('.k-num:hover { border-bottom-color: var(--accent);',
                      self.kit)
        self.assertIn('.k-num:focus { outline: 0; '
                      'border-bottom: 2px solid var(--accent);', self.kit)

    def test_error_is_written_with_two_classes_and_beats_hover(self):
        """⚠️ Одним классом линия ошибки синела бы от движения мыши."""
        self.assertIn('.k-num.k-num--bad, .k-num.k-num--bad:hover', self.kit)

    def test_error_says_why_in_words(self):
        self.assertIn('.k-num__why', self.kit)
        script = read('templates', '_num_js.html')
        self.assertIn('не больше ', script)
        self.assertIn('не меньше ', script)

    def test_line_colour_is_a_token_in_both_themes(self):
        tokens = read('templates', '_tokens.html')
        self.assertEqual(tokens.count('--num-line:'), 2,
                         'токен линии объявлен не в обеих темах')

    def test_arrows_and_escape_are_handled_by_the_script(self):
        script = read('templates', '_num_js.html')
        self.assertIn("event.key === 'ArrowUp'", script)
        self.assertIn("event.key === 'Escape'", script)

    def test_enter_is_deliberately_not_intercepted(self):
        """Гасить Enter значило бы поменять поведение форм проверки."""
        script = read('templates', '_num_js.html')
        self.assertNotIn("event.key === 'Enter'", script)

    def test_script_is_wired_into_every_base(self):
        for base in ('teacher/templates/teacher/base.html',
                     'student/templates/student/base.html',
                     'problems/templates/platform/base.html'):
            self.assertIn("{% include '_num_js.html' %}", read(*base.split('/')),
                          '%s не подключает скрипт чисел' % base)

    def test_a_real_input_is_kept_underneath(self):
        """⚠️ Нарисовать число `span`-ом значило бы сломать ввод."""
        for path in (('teacher', 'templates', 'teacher', 'work',
                      'compose.html'),
                     ('teacher', 'templates', 'teacher', 'generate.html'),
                     ('problems', 'templates', 'platform',
                      'problem_form.html')):
            markup = read(*path)
            for match in re.finditer(r'class="k-num[^"]*"', markup):
                start = markup.rfind('<', 0, match.start())
                self.assertTrue(markup.startswith('<input', start),
                                '%s: .k-num не на поле ввода' % path[-1])


class NumbersHaveNoBoxesLeftTests(TestCase):
    """Ни одного числа в рамке на пяти экранах из задания."""

    FIVE = (
        ('teacher', 'templates', 'teacher', 'work', 'compose.html'),
        ('teacher', 'templates', 'teacher', 'generate.html'),
        ('problems', 'templates', 'platform', 'problem_form.html'),
    )

    def test_no_rimmed_number_class_is_left(self):
        for path in self.FIVE:
            markup = read(*path)
            self.assertNotIn('k-input--num', markup,
                             '%s: осталось число в рамке' % path[-1])

    def test_page_rules_do_not_bring_the_border_back(self):
        """⚠️ Правило страницы специфичнее правила набора и стоит ниже."""
        markup = read('problems', 'templates', 'platform', 'problem_form.html')
        self.assertIn('.form-field input[type=text]:not(.k-num)', markup)


# ══════════════════════════════════════════════════════════════════════════
# 1.2 — чипы
# ══════════════════════════════════════════════════════════════════════════
class ChipsAreSignalsTests(TestCase):

    def setUp(self):
        self.kit = read('templates', '_kit.html')

    def test_three_kinds_and_no_more(self):
        for kind in ('type', 'diff', 'sol'):
            self.assertIn('.k-chip.k-chip--%s {' % kind, self.kit)

    def test_modifiers_are_written_with_two_classes(self):
        """⚠️ Одним классом модификатор проигрывает страничным правилам."""
        for kind in ('type', 'diff', 'sol'):
            self.assertNotIn('\n.k-chip--%s {' % kind, self.kit)

    def test_type_chip_has_no_fill(self):
        rule = re.search(r'\.k-chip\.k-chip--type \{([^}]*)\}', self.kit)
        self.assertIn('background: transparent', rule.group(1))

    def test_the_old_single_grey_chip_is_gone(self):
        self.assertNotIn('.wk-chip {', self.kit)
        card = read('teacher', 'templates', 'teacher', 'work', '_card.html')
        self.assertNotIn('wk-chip', card)

    def test_kind_chip_became_contour_too(self):
        rule = re.search(r'\n\.k-kind \{([^}]*)\}', self.kit)
        self.assertIn('background: transparent', rule.group(1))

    def test_colour_never_говорит_alone(self):
        """Цвет всегда в паре со знаком: ★ у сложности, ✓ у решения."""
        facts = card_facts(FakeProblem(difficulty=3, solution='есть'),
                           is_test=False, parts_count=0)
        by_kind = {fact['kind']: fact['text'] for fact in facts}
        self.assertTrue(by_kind['diff'].startswith('★'))
        self.assertTrue(by_kind['sol'].startswith('✓'))

    def test_parts_count_is_not_a_chip_anymore(self):
        facts = card_facts(FakeProblem(), is_test=False, parts_count=2)
        note = [fact for fact in facts if fact['kind'] == 'note']
        self.assertEqual(len(note), 1)
        self.assertEqual(note[0]['text'], '2 пункта')

    def test_nothing_is_printed_when_there_is_nothing(self):
        facts = card_facts(FakeProblem(), is_test=True, parts_count=0)
        self.assertEqual([fact['kind'] for fact in facts], ['type'])
        self.assertEqual(facts[0]['text'], 'тест')

    def test_difficulty_keeps_its_words_in_a_hint(self):
        """«★ 3» коротко, но само по себе ничего не объясняет."""
        facts = card_facts(FakeProblem(difficulty=3), is_test=False,
                           parts_count=0)
        self.assertEqual(facts[1]['hint'], 'сложность 3 из 5')

    def test_type_is_read_by_the_stripe_too(self):
        """Тест — акцент, задача — нейтральная граница (п. 1.2)."""
        self.assertIn('.k-type.k-type--test { border-left: 3px solid '
                      'var(--accent); }', self.kit)
        self.assertIn('.k-type.k-type--task { border-left: 3px solid '
                      'var(--border); }', self.kit)

    def test_green_is_left_to_its_one_meaning(self):
        """⚠️ Зелёный занят решением: полоса «задача» им быть не может."""
        self.assertNotIn('.k-type.k-type--task { border-left: 3px solid '
                         'var(--green); }', self.kit)


class ChipContrastTests(TestCase):
    """Текст на цветной подложке — не ниже 4,5:1 в ОБЕИХ темах."""

    LIGHT = {'amber-ink': '#8a5200', 'amber-tint': '#fff7e8',
             'green': '#1d7e45', 'green-tint': '#e9faf0',
             'text2': '#5b6472', 'surface': '#ffffff'}
    # В тёмной теме подложки заданы через rgba — кладём их на поверхность.
    DARK = {'amber-ink': '#ffc25e',
            'amber-tint': over('#f5a623', .15, '#161b25'),
            'green': '#3fc77f',
            'green-tint': over('#3fc77f', .15, '#161b25'),
            'text2': '#a7aebc', 'surface': '#161b25'}

    def _check(self, palette, name):
        pairs = (('amber-ink', 'amber-tint'), ('green', 'green-tint'),
                 ('text2', 'surface'))
        for ink, back in pairs:
            value = ratio(palette[ink], palette[back])
            self.assertGreaterEqual(
                value, 4.5,
                '%s: %s на %s даёт %.2f:1' % (name, ink, back, value))

    def test_light(self):
        self._check(self.LIGHT, 'светлая')

    def test_dark(self):
        self._check(self.DARK, 'тёмная')


# ══════════════════════════════════════════════════════════════════════════
# 1.3 — раскрытие
# ══════════════════════════════════════════════════════════════════════════
class OneWayToExpandTests(TestCase):

    def setUp(self):
        self.kit = read('templates', '_kit.html')

    def test_kit_owns_the_look(self):
        self.assertIn('.k-disc {', self.kit)
        self.assertIn('.k-disc__tri {', self.kit)

    def test_the_sign_turns_and_is_not_swapped(self):
        """⚠️ «▸»→«▾» — два разных глифа: надпись рядом дёргалась вбок."""
        self.assertIn('.k-disc[aria-expanded="true"] .k-disc__tri '
                      '{ transform: rotate(90deg); }', self.kit)
        for path in (('teacher', 'templates', 'teacher', 'generate.html'),
                     ('teacher', 'templates', 'teacher', 'groups',
                      '_style.html'),
                     ('student', 'templates', 'student', '_work_style.html')):
            self.assertNotIn("content: '▾ '", read(*path),
                             '%s: подмена глифа осталась' % path[-1])

    def test_details_get_the_same_sign(self):
        for selector in ('.k-details > summary', '.gen-examples > summary',
                         'details.fold > summary', '.pf-fold > summary'):
            self.assertIn(selector, self.kit)

    def test_one_word_across_the_platform(self):
        """«Показать целиком» на одном шаге и «Целиком» на соседнем."""
        for path in (('teacher', 'templates', 'teacher', 'work',
                      'compose.html'),
                     ('teacher', 'templates', 'teacher', 'work', '_card.html'),
                     ('teacher', 'templates', 'teacher', '_cand_row.html'),
                     ('teacher', 'templates', 'teacher', 'work', 'pick.html')):
            self.assertNotIn('Показать целиком', read(*path),
                             '%s: второе название того же действия' % path[-1])

    def test_buttons_carry_aria(self):
        card = read('teacher', 'templates', 'teacher', 'work', '_card.html')
        self.assertIn('aria-expanded="false"', card)
        self.assertIn('aria-controls="full-{{ key }}"', card)

    def test_expanded_takes_the_whole_card(self):
        self.assertIn('.wk-full { flex: 1 0 100%;', self.kit)

    def test_the_truncated_line_goes_away(self):
        """Иначе условие печатается дважды: обрезанное и целиком."""
        pick = read('teacher', 'templates', 'teacher', 'work', 'pick.html')
        self.assertIn('lead.hidden = true', pick)

    def test_label_is_changed_without_wiping_the_sign(self):
        pick = read('teacher', 'templates', 'teacher', 'work', 'pick.html')
        self.assertIn('.k-disc__lbl', pick)
        self.assertNotIn("more.textContent = 'Целиком'", pick)


class ReducedMotionTests(TestCase):
    """Поворот и переливы выключаются по просьбе системы."""

    def test_block_exists_and_covers_the_new_motion(self):
        kit = read('templates', '_kit.html')
        block = re.search(
            r'@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}',
            kit, re.S)
        self.assertIsNotNone(block, 'блока prefers-reduced-motion нет')
        body = block.group(1)
        for selector in ('.k-disc__tri', '.k-chip', '.k-num'):
            self.assertIn(selector, body, '%s не гасится' % selector)
