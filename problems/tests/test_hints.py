"""
Фаза 1 сессии 9 — подсказки-вопросики.

Питон-тесты видят здесь ровно две вещи: что `title` со знака убран (иначе
браузерная подсказка всплывала бы поверх своей вторым окошком) и что
рисователь подключён ко ВСЕМ базовым шаблонам, где знак может встретиться.
Что подсказка действительно появляется — проверяет `scripts/hint_check.js`
исполнением в браузере: разметка на месте и текст правильный были и до
починки, не работал сам механизм.
"""
import io
import os
import re

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

ROOT = settings.BASE_DIR

BASES = (
    'teacher/templates/teacher/base.html',
    'problems/templates/platform/base.html',
    'student/templates/student/base.html',
)


def read(path):
    with io.open(os.path.join(ROOT, path), encoding='utf-8') as handle:
        return handle.read()


class HintMarkupTests(SimpleTestCase):
    def test_no_title_attribute(self):
        """`title` убран: две подсказки поверх друг друга — хуже одной."""
        html = render_to_string('_hint.html', {'hint': 'Пояснение к числу'})
        self.assertNotIn('title=', html)

    def test_text_lives_in_data_hint(self):
        html = render_to_string('_hint.html', {'hint': 'Пояснение к числу'})
        self.assertIn('data-hint="Пояснение к числу"', html)

    def test_aria_label_kept(self):
        """Доступное имя обязано остаться — его читают с экрана."""
        html = render_to_string('_hint.html', {'hint': 'Пояснение к числу'})
        self.assertIn('aria-label="Пояснение к числу"', html)

    def test_reachable_by_keyboard(self):
        html = render_to_string('_hint.html', {'hint': 'Пояснение'})
        self.assertIn('tabindex="0"', html)


class HintPluggedEverywhereTests(SimpleTestCase):
    def test_drawer_included_in_every_base(self):
        for path in BASES:
            with self.subTest(path=path):
                self.assertIn("_hint_js.html", read(path))

    def test_style_lives_in_kit(self):
        """Правило `.k-tip` — в наборе деталей, а не в шаблоне одного экрана.

        Тот же класс дефекта, что баг 7.6 и история работ в сессии 8: класс
        используется на нескольких экранах, а стиль лежит в файле, который
        подключают не все.
        """
        kit = read('templates/_kit.html')
        self.assertIn('.k-tip', kit)
        # `display` из набора обязан быть сильнее браузерного [hidden].
        self.assertIn('.k-tip[hidden]', kit)

    def test_tip_is_fixed_and_narrow(self):
        """Плавающий блок, а не вложенный: таблицы обрезают вложенное."""
        kit = read('templates/_kit.html')
        rule = re.search(r'\.k-tip\s*\{(.+?)\}', kit, re.S)
        self.assertIsNotNone(rule)
        body = rule.group(1)
        self.assertIn('position: fixed', body)
        self.assertIn('max-width: 260px', body)
        # Подсказка не перехватывает курсор — иначе мигала бы на границе.
        self.assertIn('pointer-events: none', body)


class HintUsageTests(SimpleTestCase):
    """Где знак уже стоит — там он должен идти через общий партиал."""

    USERS = (
        'teacher/templates/teacher/_work_history.html',
        'teacher/templates/teacher/student_progress.html',
        'teacher/templates/teacher/groups/_overview.html',
        'teacher/templates/teacher/styleguide.html',
    )

    def test_all_places_use_the_partial(self):
        for path in self.USERS:
            with self.subTest(path=path):
                self.assertIn('_hint.html', read(path))

    def test_nobody_hand_rolls_the_mark(self):
        """Своя разметка знака мимо партиала — это будущий второй вид."""
        for path in self.USERS:
            with self.subTest(path=path):
                text = read(path)
                # Класс встречается только внутри включения партиала.
                self.assertNotIn('class="k-hintmark"', text)
