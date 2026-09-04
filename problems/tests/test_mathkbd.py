# -*- coding: utf-8 -*-
"""Клавиатура формул — одна на весь сайт (ADR 0075).

⚠️ ЭТАЛОН ЗАШИТ ЗДЕСЬ ПОСИМВОЛЬНО, И ЭТО ГЛАВНОЕ В ЭТОМ ФАЙЛЕ. Раскладку
переносили из `calc2/static/calc2/82-input.js` в общий модуль, и соблазн
«заодно поправить» при переносе — самый естественный на свете. Эталон снят с
версии на ветке `main` ДО переноса: 5 рядов базы, 5 групп функций, 4 группы
букв, 111 клавиш. Любое расхождение — либо осознанная правка раскладки (тогда
меняется и эталон, отдельным решением), либо потеря при переносе.
"""
import io
import re

from django.test import SimpleTestCase

MODULE = 'static/mathkbd/mathkbd.js'
CALC2 = 'calc2/static/calc2/82-input.js'
CALC2_PAGE = 'calc2/templates/calc2/calc2.html'
MATHFIELD_PARTIAL = 'problems/templates/platform/_mathfield.html'
MATHFIELD_JS = 'problems/static/platform/mathfield.js'

# ── Эталон: подписи клавиш из 82-input.js на ветке main ─────────────────
REF_BASE = [
    ['7', '8', '9', '(', ')'],
    ['4', '5', '6', '×', '÷'],
    ['1', '2', '3', '−', '+'],
    ['0', ',', '=', 'x²', 'xⁿ'],
    ['xₙ', '√', '|x|', '⌫', '✕'],
]
REF_FUNCS = [
    ['Корни и модуль', ['√', 'ⁿ√', '|x|']],
    ['Степень и логарифм', ['xⁿ', 'eˣ', 'ln', 'log']],
    ['Тригонометрия', ['sin', 'cos', 'tan']],
    ['Сравнения', ['<', '>', '≤', '≥', '≠']],
    ['Выбор', ['min', 'max', 'если']],
]
REF_LETTERS = [
    ['Латинские буквы', list('abcdefghijklmnopqrstuvwxyz')],
    ['Заглавные', list('ABCDEFGHIKLMNPQRSTVWXYZ')],
    ['Греческие', ['α', 'β', 'γ', 'δ', 'ε', 'θ', 'λ', 'μ', 'π', 'ρ', 'σ',
                   'τ', 'φ', 'ω', 'Δ', 'Σ']],
    ['Знаки', ['∞', '%', '≈']],
]
REF_TOTAL = (sum(len(row) for row in REF_BASE)
             + sum(len(keys) for _, keys in REF_FUNCS)
             + sum(len(keys) for _, keys in REF_LETTERS))


def read(path):
    return io.open(path, encoding='utf-8').read()


def labels_in(block):
    """Подписи клавиш из куска исходника: первый элемент каждого массива.

    Разбираем текстом, а не исполняя JS: питон-тест не должен зависеть от
    node. Подпись — первая строка в литерале `['подпись', ...]`.
    """
    return re.findall(r"\[\s*'((?:[^'\\]|\\.)*)'", block)


class LayoutMovedVerbatimTests(SimpleTestCase):
    """Раскладка перенесена дословно — ни клавиши не потеряно."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = read(MODULE)

    def _block(self, name):
        start = self.src.index('var %s = [' % name)
        depth = 0
        i = self.src.index('[', start)
        for k in range(i, len(self.src)):
            if self.src[k] == '[':
                depth += 1
            elif self.src[k] == ']':
                depth -= 1
                if depth == 0:
                    return self.src[i:k + 1]
        self.fail('не закрылся массив %s' % name)

    def test_base_rows(self):
        block = self._block('MKBD_BASE')
        found = labels_in(block)
        expected = [label for row in REF_BASE for label in row]
        self.assertEqual(found[:len(expected)], expected)

    def test_function_groups(self):
        block = self._block('MKBD_FUNCS')
        for label, keys in REF_FUNCS:
            self.assertIn("'%s'" % label, block, label)
            for key in keys:
                self.assertIn("['%s'" % key, block, '%s / %s' % (label, key))

    def test_letter_groups(self):
        block = self._block('MKBD_LETTERS')
        for label, keys in REF_LETTERS:
            self.assertIn("'%s'" % label, block, label)
        # Латинские и заглавные строятся из строки — проверяем саму строку.
        self.assertIn("'abcdefghijklmnopqrstuvwxyz'", block)
        self.assertIn("'ABCDEFGHIKLMNPQRSTVWXYZ'", block)
        for key in REF_LETTERS[2][1] + REF_LETTERS[3][1]:
            self.assertIn("['%s'" % key, block, key)

    def test_total_key_count_is_the_reference_one(self):
        """111 клавиш — столько было в калькуляторе до переноса."""
        self.assertEqual(REF_TOTAL, 111)


class NoSecondCopyTests(SimpleTestCase):
    """Второй копии раскладки в репозитории нет."""

    def test_calc2_has_no_layout_of_its_own(self):
        src = read(CALC2)
        self.assertNotIn('MKBD_', src,
                         'раскладка вернулась в 82-input.js — это вторая копия')

    def test_calc2_uses_the_shared_module(self):
        self.assertIn('window.MathKbd.build', read(CALC2))

    def test_homework_has_no_quick_keys_of_its_own(self):
        """Четыре ряда своих кнопок в домашке — это и была вторая клавиатура."""
        src = read(MATHFIELD_JS)
        self.assertNotIn('var QUICK', src)
        self.assertNotIn("'mf-key'", src)
        self.assertIn('window.MathKbd.build', src)

    def test_homework_no_longer_opens_the_builtin_keyboard(self):
        """Встроенная клавиатура MathLive спорила бы с нашей."""
        src = read(MATHFIELD_JS)
        self.assertNotIn("'mf-kbd'", src)
        self.assertNotIn('mathVirtualKeyboard.visible =\n', src)
        # Политика «вручную» ОСТАЁТСЯ: иначе встроенная всплывёт сама.
        self.assertIn('math-virtual-keyboard-policy', src)


class BothScreensLoadTheSameFileTests(SimpleTestCase):
    """Калькулятор и домашки подключают ОДИН и тот же файл."""

    def test_both_templates_reference_mathkbd(self):
        for path in (CALC2_PAGE, MATHFIELD_PARTIAL):
            src = read(path)
            self.assertIn("mathkbd/mathkbd.js", src, path)
            self.assertIn("mathkbd/mathkbd.css", src, path)

    def test_calc2_loads_it_before_its_own_input_script(self):
        """`82-input.js` зовёт `MathKbd.build` — модуль обязан быть раньше."""
        src = read(CALC2_PAGE)
        self.assertLess(src.index('mathkbd/mathkbd.js'),
                        src.index('calc2/82-input.js'))

    def test_partial_loads_it_before_mathfield(self):
        src = read(MATHFIELD_PARTIAL)
        self.assertLess(src.index('mathkbd/mathkbd.js'),
                        src.index('platform/mathfield.js'))


class LettersAreDrawnByKatexTests(SimpleTestCase):
    """П23: буквы рисуются KaTeX, то есть все математическим курсивом.

    ⚠️ ПРИЧИНА БЫЛА НЕ В КОДЕ, А В ШРИФТЕ. Подпись печаталась обычным
    текстом, и наклон зависел от того, есть ли у начертания интерфейсного
    шрифта данная буква в курсиве — отсюда смесь прямых и наклонных
    заглавных, которую видел владелец. Теперь смеси быть не может по
    построению.
    """

    def setUp(self):
        self.src = read(MODULE)

    def test_letters_sections_are_marked_as_formula(self):
        for label in ('Латинские буквы', 'Заглавные', 'Греческие'):
            self.assertIn("'%s': 1" % label, self.src, label)

    def test_signs_stay_plain_text(self):
        """Цифры и знаки прямые и в TeX — их рисовать формулой незачем."""
        self.assertNotIn("'Знаки': 1", self.src)

    def test_katex_is_used_with_a_fallback(self):
        """KaTeX может не загрузиться — клавиатура обязана остаться живой."""
        self.assertIn('katex.renderToString', self.src)
        self.assertIn('button.textContent = key[0]', self.src)

    def test_labels_stay_readable_for_screen_readers(self):
        """Разметку KaTeX чтец экрана прочитает не так — нужен aria-label."""
        self.assertIn("b.setAttribute('aria-label', key[0])", self.src)
