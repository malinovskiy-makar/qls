"""
Обзор кабинета 13.08.2026, фаза 9 — создание работы.

Пункты владельца 57, 58, 59, 60, 62, 63.
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


def _crumb_text(html):
    """Крошка строкой, как её видит глаз.

    ⚠️ Стрелку рисует CSS (ревью 15.08, фаза 2), в разметке её нет —
    собираем из текстов звеньев. Та же сборка, что в `test_obzor_nav`.
    """
    found = re.search(r'<nav class="crumbs"[^>]*>(.*?)</nav>', html, re.S)
    if not found:
        return ''
    parts = re.findall(r'<(?:a|span)\b[^>]*>(.*?)</(?:a|span)>',
                       found.group(1), re.S)
    clean = [re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', part)).strip()
             for part in parts]
    return ' → '.join(part for part in clean if part)


class Base(TestCase):
    def setUp(self):
        self.tutor = make_user('ob_tutor', role='teacher')
        self.group = StudentGroup.objects.create(name='Группа А',
                                                 teacher=self.tutor)
        self.group.students.set([make_user('ob_s1', role='student')])
        self.client.force_login(self.tutor)


class OwnProblemHeaderTests(Base):
    """9.1 — «Написать свою» в контексте создания получает общую шапку."""

    def _in_build(self):
        return self.client.get(
            reverse('teacher:problem_new')
            + '?to_cart=1&group=%d' % self.group.pk).content.decode()

    def test_only_one_crumb_in_build_context(self):
        html = self._in_build()
        self.assertEqual(html.count('<nav class="crumbs"'), 1)

    def test_that_crumb_is_the_common_one(self):
        # ⚠️ Стрелку рисует CSS (ревью 15.08, фаза 2) — собираем строку из
        # звеньев так же, как её видит глаз.
        self.assertEqual(_crumb_text(self._in_build()),
                         'Ученики → Группа А → новая работа')

    def test_common_header_parts_are_there(self):
        html = self._in_build()
        self.assertIn('Новая работа', html)
        self.assertIn('bh-kind__opt', html)
        self.assertEqual(html.count('<span class="k-tile__name">'), 3)

    def test_from_my_problems_the_old_crumb_stays(self):
        html = self.client.get(reverse('teacher:problem_new')).content.decode()
        self.assertIn('Мои задачи', _crumb_text(html))
        # Общей шапки нет: ни переключателя вида, ни плиток способа.
        self.assertNotIn('<a class="bh-kind__opt', html)
        self.assertNotIn('<span class="k-tile__name">', html)


class KindSwitcherTests(Base):
    """9.2 — вид работы стал компактным переключателем."""

    def _html(self):
        return self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % self.group.pk).content.decode()

    def test_kind_is_not_a_tile_anymore(self):
        html = self._html()
        self.assertNotIn('k-tiles bh-kind', html)
        # ⚠️ Считаем РАЗМЕТКУ: имя класса встречается ещё и в правилах
        # набора, которые вклеены в <style> страницы.
        self.assertEqual(html.count('<a class="bh-kind__opt'), 2)

    def test_only_three_tiles_left_on_the_screen(self):
        """Плиток было пять одного размера — какие главные, понять нельзя."""
        self.assertEqual(self._html().count('<span class="k-tile__name">'), 3)

    def test_the_note_is_not_lost(self):
        html = self._html()
        self.assertIn('решают дома, срок сдачи', html)

    def test_the_note_follows_the_chosen_kind(self):
        html = self.client.get(
            reverse('teacher:exam_create', args=[self.group.pk])).content.decode()
        note = re.search(r'class="bh-kind__note">(.*?)<', html).group(1)
        self.assertEqual(note, 'ограниченное время, окно')

    def test_switcher_is_lighter_than_the_tiles(self):
        kit = read('templates', '_kit.html')
        block = kit.split('.bh-kind__opt {')[1].split('}')[0]
        self.assertIn('font-size: 12px', block)
        # Заливки у невыбранного нет — только у активного сегмента.
        self.assertNotIn('background:', block)

    def test_switcher_keeps_the_group(self):
        html = self._html()
        links = re.findall(r'<a class="bh-kind__opt[^"]*"\s+href="([^"]+)"', html)
        self.assertEqual(len(links), 2)
        for href in links:
            self.assertTrue('group=%d' % self.group.pk in href
                            or '/groups/%d/' % self.group.pk in href, href)


class SummaryCardTests(Base):
    """9.3 — «0 тестов» называется вслух."""

    def test_zero_is_spelled_out(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        block = page.split('function paint()')[1].split('}')[0]
        self.assertIn('if (o || t)', block)

    def test_empty_state_still_says_nothing_chosen(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        self.assertIn("'ничего не выбрано'", page)


class ColumnOrderTests(Base):
    """9.4 — сверху что за работа, снизу чем наполняем."""

    def _aside(self, html):
        """Правая колонка целиком.

        ⚠️ Режем по `<aside class="hw-sidebar` БЕЗ закрывающей кавычки:
        с ревью 15.08 панель ещё и обёртка растворения краёв, и в атрибуте
        рядом стоят `fade-box fade-box--y`.
        """
        return html.split('<aside class="hw-sidebar')[1]

    def _order(self, html):
        """Порядок блоков правой колонки по их заголовкам."""
        return re.findall(r'class="ws-title"[^>]*>(.*?)<', self._aside(html))

    def test_homework_settings_stand_above_the_cart(self):
        html = self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % self.group.pk).content.decode()
        order = self._order(html)
        self.assertEqual(order[:3],
                         ['Настройки работы', 'Кому выдать', 'Выбранные задачи'])

    def test_exam_uses_the_same_order(self):
        """Разводить порядок на двух конструкторах нельзя."""
        html = self.client.get(
            reverse('teacher:exam_create',
                    args=[self.group.pk])).content.decode()
        order = self._order(html)
        self.assertEqual(order[:3],
                         ['Настройки работы', 'Кому выдать',
                          'Задачи контрольной'])

    def test_button_stayed_last(self):
        html = self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % self.group.pk).content.decode()
        aside = self._aside(html)
        self.assertLess(aside.index('cart-list'), aside.index('id="submit-btn"'))

    def test_button_ids_did_not_change(self):
        """Их ищет `_picker_js` — переименование сломало бы подсказку."""
        html = self.client.get(
            reverse('teacher:assignment_create')).content.decode()
        self.assertIn('id="submit-btn"', html)
        self.assertIn('id="submit-why"', html)

    def test_only_one_button_on_the_page(self):
        for url in (reverse('teacher:assignment_create'),
                    reverse('teacher:exam_create', args=[self.group.pk])):
            html = self.client.get(url).content.decode()
            self.assertEqual(html.count('id="submit-btn"'), 1, url)


class SubmitLabelTests(Base):
    """9.5 — надпись кнопки следует за видом работы."""

    def test_homework_says_homework(self):
        html = self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % self.group.pk).content.decode()
        self.assertIn('Создать домашку', html)

    def test_switching_to_exam_leads_to_the_exam_button(self):
        """Переключатель ведёт в конструктор контрольной — там своя надпись."""
        html = self.client.get(
            reverse('teacher:assignment_create')
            + '?group=%d' % self.group.pk).content.decode()
        links = re.findall(r'<a class="bh-kind__opt[^"]*"\s+href="([^"]+)"', html)
        exam_url = links[1].replace('&amp;', '&')
        self.assertEqual(exam_url,
                         reverse('teacher:exam_create', args=[self.group.pk]))
        exam_html = self.client.get(exam_url).content.decode()
        self.assertIn('Создать контрольную', exam_html)
        self.assertNotIn('Создать домашку', exam_html)

    def test_without_a_group_the_exam_constructor_does_not_exist(self):
        """Он живёт ВНУТРИ занятия: без номера адрес не собирается.

        Это ограничение, а не дефект надписи: переключатель уводит на
        «Описать словами», где кнопки создания нет вовсе.
        """
        html = self.client.get(reverse('teacher:assignment_create')).content.decode()
        links = re.findall(r'<a class="bh-kind__opt[^"]*"\s+href="([^"]+)"', html)
        self.assertIn('kind=exam', links[1])
        self.assertIn('generate', links[1])


class FiltersRowTests(Base):
    """9.6 — ряд отбора разложен ровно."""

    def test_no_second_set_of_rules_for_the_same_class(self):
        """Второй набор стоял ниже и побеждал первый — отсюда и разъезд."""
        css = read('teacher', 'templates', 'teacher', '_picker_style.html')
        self.assertEqual(css.count('.filters-row .k-select-wrap {'), 1)
        self.assertEqual(css.count('.filters-row .k-select {'), 1)

    def test_selects_have_a_bounded_basis(self):
        css = read('teacher', 'templates', 'teacher', '_picker_style.html')
        block = css.split('.filters-row .k-select-wrap {')[1].split('}')[0]
        self.assertIn('flex: 1 1', block)
        self.assertIn('max-width', block)
        self.assertNotIn('flex: 0 1 auto', block)

    def test_select_can_shrink(self):
        """Без `min-width: 0` список не даёт себя сжать ниже длинной строки."""
        css = read('teacher', 'templates', 'teacher', '_picker_style.html')
        block = css.split('.filters-row .k-select {')[1].split('}')[0]
        self.assertIn('min-width: 0', block)

    def test_buttons_do_not_stretch(self):
        css = read('teacher', 'templates', 'teacher', '_picker_style.html')
        self.assertIn('.filters-row .k-btn { flex: 0 0 auto; }', css)

    def test_all_seven_controls_are_still_there(self):
        html = self.client.get(reverse('teacher:assignment_create')).content.decode()
        row = html.split('class="filters-row"')[1].split('</form>')[0]
        for name in ('name="q"', 'name="topic"', 'name="difficulty"',
                     'name="type"', 'name="has_solution"'):
            self.assertIn(name, row)
        self.assertIn('Найти', row)
        self.assertIn('Сброс', row)
