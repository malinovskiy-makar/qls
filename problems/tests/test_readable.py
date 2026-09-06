# -*- coding: utf-8 -*-
"""
Читаемость и наложения (ревью 17.08, фаза 3).

Контраст МЕРЯЕТСЯ, а не оценивается на глаз — тем же способом, что уже
закреплён для кружка счётчика (`--on-error`, ревью 16.08). Прозрачность
считается ПОВЕРХ поверхности: полупрозрачная заливка на белой карточке и
на тёмной — разные цвета, и сравнивать текст с `rgba(...)` напрямую значит
мерить контраст с прозрачностью.
"""
import re

from django.test import Client, TestCase
from django.urls import reverse

from problems.models import User

TOKENS = 'templates/_tokens.html'
STATS_STYLE = 'problems/templates/platform/_stats_style.html'
HISTORY = 'teacher/templates/teacher/_work_history.html'
CARDS = 'teacher/templates/teacher/groups/submissions_by_student.html'
HINT_JS = 'templates/_hint_js.html'
PROBLEM_FORM = 'problems/templates/platform/problem_form.html'


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def hex_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def over(top, bottom, alpha):
    """Полупрозрачный цвет поверх непрозрачного."""
    return tuple(top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3))


def luminance(rgb):
    def channel(value):
        value = value / 255
        return (value / 12.92 if value <= 0.03928
                else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = (channel(part) for part in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return round((high + 0.05) / (low + 0.05), 2)


def token(theme_css, name):
    match = re.search(r'--%s:\s*([^;]+);' % re.escape(name), theme_css)
    return match.group(1).strip() if match else None


def themes():
    """Светлый и тёмный наборы токенов отдельными кусками файла."""
    css = read(TOKENS)
    dark_at = css.index('[data-theme="dark"]')
    return css[:dark_at], css[dark_at:]


class ActivityCellContrastTests(TestCase):
    """3.1 — цифра дня читается на всех четырёх уровнях заливки.

    ⚠️ ПЛОТНОСТИ БЕРУТСЯ ИЗ ТОКЕНОВ, А НЕ ПОВТОРЯЮТСЯ ЗДЕСЬ ЧИСЛАМИ
    (31.08.2026). Раньше `LEVELS` держал копию `.22/.45/.70` из
    `_stats_style.html`, и копия жила своей жизнью: поменяли бы шкалу в CSS —
    тест мерил бы прежнюю и остался бы зелёным на сломанном экране. Теперь
    источник один — `templates/_tokens.html`, по токену на уровень, и шкалы
    у тем РАЗНЫЕ (акцент в темах разной светлоты).

    Чтобы тест остался сторожем, а не просто перестал падать, он проверяет
    ДВЕ вещи сразу: числа приходят из токенов (вернут .70 — контраст упадёт
    и тест покраснеет) И `_stats_style.html` действительно берёт эти токены,
    а не свои зашитые доли (`test_scale_lives_in_tokens_only`). Без второй
    половины плотность можно было бы зашить обратно в CSS мимо токена, и
    измерение опять поехало бы мимо экрана.
    """

    AA = 4.5

    def levels(self, theme_css):
        """Плотности уровней 1–3 из токенов темы; четвёртый — сплошной."""
        out = []
        for level in (1, 2, 3):
            raw = token(theme_css, 'act-a%d' % level)
            self.assertIsNotNone(raw, 'нет токена --act-a%d' % level)
            out.append((level, float(raw)))
        return tuple(out) + ((4, 1.0),)

    def measure(self, theme_css):
        accent = token(theme_css, 'accent-rgb')
        self.assertIsNotNone(accent, 'нет токена --accent-rgb')
        accent = tuple(int(part) for part in accent.split(','))
        surface = hex_rgb(token(theme_css, 'surface'))
        ink = hex_rgb(token(theme_css, 'act-ink'))
        ink_solid = hex_rgb(token(theme_css, 'act-ink-solid'))
        out = {}
        for level, alpha in self.levels(theme_css):
            background = over(accent, surface, alpha)
            paint = ink_solid if level == 4 else ink
            out[level] = contrast(paint, background)
        return out

    def test_scale_lives_in_tokens_only(self):
        """Шкала объявлена в обеих темах, а CSS берёт её и ничего не зашивает."""
        light, dark = themes()
        for name, css in (('светлая', light), ('тёмная', dark)):
            for level in (1, 2, 3):
                raw = token(css, 'act-a%d' % level)
                self.assertIsNotNone(raw, '%s: нет --act-a%d' % (name, level))
                self.assertTrue(0 < float(raw) < 1,
                                '%s: --act-a%d = %s' % (name, level, raw))
        style = read(STATS_STYLE)
        for level in (1, 2, 3):
            rule = re.search(r'\.act-l%d\s*\{([^}]*)\}' % level, style)
            self.assertIsNotNone(rule, 'нет правила .act-l%d' % level)
            body = rule.group(1)
            self.assertIn('var(--act-a%d)' % level, body,
                          'уровень %d не берёт плотность из токена' % level)
            self.assertIsNone(
                re.search(r'rgba\([^)]*?,\s*[.\d]+\s*\)', body),
                'уровень %d снова зашил плотность числом: %s' % (level, body.strip()))

    def test_levels_are_distinguishable(self):
        """Уровни должны РАЗЛИЧАТЬСЯ, а не только нести читаемый текст.

        Пять ступеней одного цвета легко сделать читаемыми и при этом
        неразличимыми: если соседние заливки отличаются на 1,02, теплокарта
        перестаёт быть картой. Порог 1,15 — ниже него разницу на клетке
        34×34 px глазом уже не поймать.
        """
        for name, css in (('светлая', themes()[0]), ('тёмная', themes()[1])):
            accent = tuple(int(p) for p in token(css, 'accent-rgb').split(','))
            surface = hex_rgb(token(css, 'surface'))
            fills = [surface] + [over(accent, surface, alpha)
                                 for _level, alpha in self.levels(css)]
            for step in range(len(fills) - 1):
                value = contrast(fills[step], fills[step + 1])
                self.assertGreaterEqual(
                    value, 1.15,
                    '%s тема, ступень %d→%d: перепад заливки %s'
                    % (name, step, step + 1, value))

    def test_light_theme_passes_aa(self):
        light, _ = themes()
        for level, value in self.measure(light).items():
            self.assertGreaterEqual(
                value, self.AA,
                'светлая тема, уровень %d: контраст %s' % (level, value))

    def test_dark_theme_passes_aa(self):
        _, dark = themes()
        for level, value in self.measure(dark).items():
            self.assertGreaterEqual(
                value, self.AA,
                'тёмная тема, уровень %d: контраст %s' % (level, value))

    def test_fill_is_a_colour_not_a_faded_cell(self):
        """⚠️ `opacity` у клетки гасит и цифру — этого правила быть не должно."""
        css = read(STATS_STYLE)
        for level in (1, 2, 3):
            rule = re.search(r'\.act-l%d\s*\{([^}]*)\}' % level, css)
            self.assertIsNotNone(rule, 'нет правила .act-l%d' % level)
            self.assertNotIn('opacity', rule.group(1),
                             'уровень %d гасит клетку целиком' % level)
            self.assertIn('--accent-rgb', rule.group(1))

    def test_both_themes_define_both_inks(self):
        light, dark = themes()
        for name in ('accent-rgb', 'act-ink', 'act-ink-solid'):
            self.assertIsNotNone(token(light, name), 'светлая: нет %s' % name)
            self.assertIsNotNone(token(dark, name), 'тёмная: нет %s' % name)


class ChartCaptionTests(TestCase):
    """3.2 — подпись стоит ПОД графиками, а не поверх подписей оси."""

    def test_label_is_outside_the_sized_box(self):
        """`.chart-box` — контейнер заданной высоты; текст внутри её ломает.

        ⚠️ Разметка переехала в общий партиал `platform/_activity_panel.html`
        (ревью 17.08, фаза 6): блок активности стал один на два экрана.
        Проверка та же, только файл другой.
        """
        html = read('problems/templates/platform/_activity_panel.html')
        block = html[html.index('chart-weekday') - 400:
                     html.index('chart-hour') + 200]
        # Подпись графика обязана стоять ДО открытия `.chart-box`.
        self.assertNotIn('<div class="chart-box">\n      <div class="panel-hint"',
                         block, 'подпись снова внутри контейнера высоты')
        self.assertIn('<div class="chart-box"><canvas id="chart-weekday">',
                      block)


class NoDimmingTests(TestCase):
    """3.4 — смысл называется словами, а не прозрачностью."""

    def test_history_rows_are_not_faded(self):
        css = read(STATS_STYLE)
        self.assertNotIn('tr.is-idle td { opacity', css)
        self.assertNotIn('is-idle', read(HISTORY))

    def test_student_cards_are_not_faded(self):
        card = read(CARDS)
        self.assertNotIn('.stu-card.is-idle { opacity', card)
        self.assertNotIn(' is-idle', card)

    def test_history_says_it_in_words(self):
        self.assertIn('никто не сдал', read(HISTORY))


class HintPlacementTests(TestCase):
    """3.5 — правило размещения общее, а не заплатка одного экрана."""

    def test_tooltip_is_anchored_below_the_block(self):
        js = read(HINT_JS)
        self.assertIn('.k-card, .stu-card', js,
                      'подсказка не знает про блок, который объясняет')
        self.assertIn('frame.bottom + gap', js)

    def test_tall_blocks_keep_the_old_anchor(self):
        """Клетка теплокарты внутри панели не имеет права уехать вниз."""
        js = read(HINT_JS)
        self.assertIn('BLOCK_LIMIT', js)

    def test_rule_lives_in_one_place(self):
        """Второго расчёта положения на платформе нет."""
        import subprocess

        found = subprocess.run(
            ['grep', '-rl', 'k-tip', 'templates', 'teacher/templates',
             'problems/templates', 'student/templates'],
            capture_output=True, text=True).stdout.split()
        # Стиль (`_kit.html`) и механизм (`_hint_js.html`) — и всё.
        self.assertLessEqual(len(found), 2, 'k-tip живёт в %s' % found)


class PartFieldsTests(TestCase):
    """3.3 — подписи полей пункта не налезают друг на друга."""

    def test_labels_may_wrap(self):
        css = read(PROBLEM_FORM)
        rule = re.search(r'\.part-grid label\s*\{([^}]*)\}', css)
        self.assertIsNotNone(rule)
        self.assertNotIn('nowrap', rule.group(1),
                         'неразрывная подпись вылезает из сжатой колонки')

    def test_fields_stay_on_one_line(self):
        css = read(PROBLEM_FORM)
        rule = re.search(r'\.part-grid\s*\{([^}]*)\}', css)
        self.assertIn('align-items: end', rule.group(1))

    def test_editor_still_opens(self):
        tutor = User.objects.create_user('pf-tutor', password='x',
                                         role='teacher')
        client = Client()
        client.force_login(tutor)
        page = client.get(reverse('teacher:problem_new'))
        self.assertEqual(page.status_code, 200)
        self.assertIn('part-grid', page.content.decode())
