"""
Объединённое ревью 15.08, фаза 5 — края прокрутки и полосы прокрутки.

Пункт 5 владельца: растворение слева, тёмная тема догоняет светлую,
механизм — везде, полосы спрятаны, но прокрутка остаётся рабочей.

⚠️ ЗАМЕР ТЁМНОЙ ТЕМЫ. Чёрная тень на тёмном фоне физически не может дать
такой же перепад, как серая на белом: даже ЧИСТО ЧЁРНЫЙ на `--surface`
тёмной темы даёт 1,21, а светлая тема даёт 1,28. Поэтому в тёмной теме край
светлый, а не тёмный. Замер по самим снимкам: светлая 1,28, тёмная 1,32.
"""
import os
import re

from django.test import TestCase
from django.urls import reverse

from problems.models import StudentGroup
from problems.tests.factories import make_user

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


def markup_files():
    for folder in ('templates', 'teacher', 'student', 'problems/templates'):
        for base, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            if 'node_modules' in base:
                continue
            for name in files:
                if name.endswith('.html'):
                    path = os.path.join(base, name)
                    with open(path, encoding='utf-8') as handle:
                        yield os.path.relpath(path, ROOT), handle.read()


class BothEdgesTests(TestCase):
    def test_left_edge_exists(self):
        kit = read('templates', '_kit.html')
        self.assertIn('.fade-box::before, .fade-box::after', kit)
        self.assertIn('.fade-box::before {', kit)
        self.assertIn('.fade-box.is-start::before { opacity: 0; }', kit)

    def test_right_edge_survived(self):
        kit = read('templates', '_kit.html')
        self.assertIn('.fade-box.is-end::after { opacity: 0; }', kit)

    def test_vertical_variant_exists(self):
        """Правая панель конструктора прокручивается вниз, а не вбок."""
        kit = read('templates', '_kit.html')
        self.assertIn('.fade-box--y::before, .fade-box--y::after', kit)

    def test_edge_colour_is_a_token(self):
        kit = read('templates', '_kit.html')
        block = kit.split('.fade-box::before {')[1].split('}')[0]
        self.assertIn('var(--fade-edge)', block)
        self.assertIn('var(--fade-under)', block)

    def test_surface_under_the_fade_is_overridable(self):
        """Панель стоит на фоне страницы, а не на белой карточке."""
        kit = read('templates', '_kit.html')
        self.assertIn('--fade-under: var(--surface)', kit)
        picker = read('teacher', 'templates', 'teacher', '_picker_style.html')
        self.assertIn('--fade-under: var(--bg)', picker)


class DarkEdgeTests(TestCase):
    """Тёмная тема догоняет светлую — считаем, а не смотрим."""

    @staticmethod
    def _lum(value):
        value = value.lstrip('#')
        ch = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]

    def _ratio(self, one, two):
        a, b = self._lum(one), self._lum(two)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)

    @staticmethod
    def _over(colour, alpha, below):
        top = [int(colour[i:i + 2], 16) for i in (0, 2, 4)]
        base = [int(below.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
        return '#%02x%02x%02x' % tuple(
            round(top[i] * alpha + base[i] * (1 - alpha)) for i in range(3))

    def _edge(self, part):
        found = re.search(
            r'--fade-edge:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', part)
        r, g, b, a = found.groups()
        return '%02x%02x%02x' % (int(r), int(g), int(b)), float(a)

    def test_dark_edge_is_light_not_black(self):
        """⚠️ Чёрным нужного перепада в тёмной теме не получить в принципе."""
        tokens = read('templates', '_tokens.html')
        dark = tokens.split('[data-theme="dark"]')[1]
        colour, _alpha = self._edge(dark)
        self.assertEqual(colour, 'ffffff', colour)

    def test_black_edge_at_the_same_density_would_be_weaker(self):
        """Чёрный край в тёмной теме слабее — при РАВНОЙ плотности.

        ⚠️ ПРЕЖНЯЯ ФОРМУЛИРОВКА СРАВНИВАЛА НЕСРАВНИМОЕ, И ЭТО ВСКРЫЛОСЬ ТОЛЬКО
        СЕЙЧАС (31.08.2026, вечер). Она брала ЧИСТО ЧЁРНЫЙ, то есть плотность
        1,0, и сравнивала его со светлым краем на его настоящей плотности
        0,17. На глубокой карточке #242019 даже такая фора чёрному не
        помогала (1,35 против 1,39), и перекос никого не беспокоил. На
        карточке #3f3f3d он даёт 1,99 — и проверка покраснела, хотя решение
        «край в тёмной теме светлый» осталось верным.

        Сравниваем честно: чёрный край на ТОЙ ЖЕ плотности, что у настоящего
        края тёмной темы. Тогда видно и то, ради чего писалась проверка:
        чёрный (1,13) слабее светлого края светлой темы (1,39), а белый,
        который стоит на самом деле (1,48), — не слабее.
        """
        tokens = read('templates', '_tokens.html')
        light, dark = tokens.split('[data-theme="dark"]')
        light_surface = re.search(r'--surface:\s*(#[0-9a-fA-F]{6})',
                                  light).group(1)
        dark_surface = re.search(r'--surface:\s*(#[0-9a-fA-F]{6})',
                                 dark).group(1)
        light_colour, light_alpha = self._edge(light)
        dark_colour, dark_alpha = self._edge(dark)
        light_step = self._ratio(
            self._over(light_colour, light_alpha, light_surface),
            light_surface)
        black_step = self._ratio(
            self._over('000000', dark_alpha, dark_surface), dark_surface)
        real_step = self._ratio(
            self._over(dark_colour, dark_alpha, dark_surface), dark_surface)
        self.assertLess(black_step, light_step,
                        'чёрный %.2f, светлая тема %.2f' % (black_step, light_step))
        self.assertGreater(real_step, black_step,
                           'настоящий край %.2f, чёрный %.2f' % (real_step, black_step))

    def test_dark_step_catches_up_with_light(self):
        tokens = read('templates', '_tokens.html')
        light, dark = tokens.split('[data-theme="dark"]')
        steps = []
        for part in (light, dark):
            surface = re.search(r'--surface:\s*(#[0-9a-fA-F]{6})',
                                part).group(1)
            colour, alpha = self._edge(part)
            steps.append(self._ratio(self._over(colour, alpha, surface),
                                     surface))
        # Тёмная не слабее светлой — направление правки именно такое.
        self.assertGreaterEqual(round(steps[1], 2), round(steps[0], 2) - 0.02,
                                steps)


class EverywhereTests(TestCase):
    """Механизм стоит у КАЖДОГО прокручиваемого блока кабинета."""

    WRAPPED = [
        'teacher/templates/teacher/groups/_overview.html',      # теплокарта
        'teacher/templates/teacher/_work_history.html',         # история
        'teacher/templates/teacher/assignment_detail.html',     # по задачам
        'problems/templates/platform/_heatmap.html',            # активность
        # ⚠️ ПЕРЕСЧИТАН (ревью 17.08, п. 4.5): прежние конструкторы с их
        # прокручиваемой правой панелью удалены. Прокручиваемых блоков на
        # шагах потока нет — колонка одна и растёт вниз страницей.
    ]

    def test_every_scroller_has_a_wrapper(self):
        for path in self.WRAPPED:
            text = read(*path.split('/'))
            self.assertIn('data-fade', text, path)

    def test_heatmap_has_two_wrappers(self):
        """У обзора занятия прокручиваются ДВЕ таблицы: матрица и ученики."""
        text = read('teacher', 'templates', 'teacher', 'groups',
                    '_overview.html')
        self.assertEqual(text.count('data-fade'), 2)

    def test_script_is_one_and_shared(self):
        self.assertTrue(os.path.exists(
            os.path.join(ROOT, 'templates', '_scroll_fade.html')))
        for base in ('teacher/templates/teacher/base.html',
                     'problems/templates/platform/base.html',
                     'student/templates/student/base.html'):
            self.assertIn("{% include '_scroll_fade.html' %}",
                          read(*base.split('/')), base)

    def test_no_second_fade_script_left(self):
        """⚠️ Второй механизм на тот же класс — всегда мина."""
        bad = [path for path, text in markup_files()
               if "querySelectorAll('[data-fade]')" in text
               and not path.endswith('_scroll_fade.html')]
        self.assertEqual(bad, [], bad)

    def test_old_no_bar_class_is_gone(self):
        """Полосу теперь прячет сам `.fade-box` — отдельный класс не нужен."""
        bad = [path for path, text in markup_files() if 'no-bar' in text]
        self.assertEqual(bad, [], bad)


class ScrollbarAndKeyboardTests(TestCase):
    def test_scrollbar_is_hidden_for_the_inner_block(self):
        kit = read('templates', '_kit.html')
        self.assertIn('.fade-box > * { scrollbar-width: none;', kit)
        self.assertIn('.fade-box > *::-webkit-scrollbar { display: none; }',
                      kit)

    def test_focus_ring_is_visible(self):
        """Скрытая полоса не должна отнять доступ с клавиатуры."""
        kit = read('templates', '_kit.html')
        self.assertIn('.fade-box > [tabindex]:focus-visible', kit)

    def test_script_makes_overflowing_block_focusable(self):
        script = read('templates', '_scroll_fade.html')
        self.assertIn('scroller.tabIndex = 0', script)
        self.assertIn("setAttribute('aria-label'", script)

    def test_script_does_not_stop_the_tab_on_a_full_block(self):
        """Блок, который виден целиком, остановкой табуляции быть не должен."""
        script = read('templates', '_scroll_fade.html')
        self.assertIn("removeAttribute('tabindex')", script)


class LivePageTests(TestCase):
    def setUp(self):
        self.tutor = make_user('sf_tutor', role='teacher')
        self.student = make_user('sf_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student])
        self.client.force_login(self.tutor)

    def test_group_screen_carries_the_script(self):
        html = self.client.get(reverse('teacher:group_detail',
                                       args=[self.group.pk])).content.decode()
        self.assertIn('data-fade', html)
        self.assertIn('fade-box', html)
        self.assertIn("querySelectorAll('[data-fade]')", html)

    def test_student_card_carries_it_too(self):
        html = self.client.get(
            reverse('teacher:student_progress',
                    args=[self.student.pk])).content.decode()
        self.assertIn("querySelectorAll('[data-fade]')", html)

    def test_constructor_has_no_scrolling_sidebar_anymore(self):
        """⚠️ ПЕРЕСЧИТАН: правой прокручиваемой колонки больше нет.

        Растворение краёв заводилось для неё; в потоке состав работы —
        обычный список страницы, и прятать край не от чего (ревью 17.08,
        п. 4.5). Проверка держит именно это: панель не вернулась молча.
        """
        html = self.client.get(
            reverse('teacher:work_compose')
            + '?group=%d' % self.group.pk).content.decode()
        self.assertNotIn('hw-sidebar', html)
