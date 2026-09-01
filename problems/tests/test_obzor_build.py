"""
Обзор кабинета 13.08.2026, фаза 9 — создание работы.

Пункты владельца 57, 58, 59, 60, 62, 63.

⚠️ ПЕРЕСЧИТАН В РЕВЬЮ 17.08, п. 4.5. Прежние экраны создания удалены, набор
задач живёт в потоке `/teacher/work/`. Требования владельца не отменялись —
они проверяются там, где эти элементы теперь стоят: общая шапка стала
лентой шагов, правая колонка с настройками — шагом «Выдача», кнопка
создания — полосой собранного. Отдельно отмечено ниже, что именно
изменилось и почему прежнее ожидание больше не верно.
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
        """⚠️ ПЕРЕСЧИТАН: вместо трёх плиток способов — ЛЕНТА ШАГОВ.

        Требование то же и стало строже: экран своей задачи не имеет права
        выпадать из потока. Плитки способов набора удалены с платформы
        вместе со старыми экранами (ревью 17.08, п. 4.2 и 4.5) — их роль
        играют вкладки первого шага.
        """
        html = self._in_build()
        self.assertIn('Новая работа', html)
        self.assertIn('bh-kind__opt', html)
        # ⚠️ Ищем РАЗМЕТКУ, а не имя класса: набор стилей вклеен в
        # `<style>` страницы, и поиск по имени зеленел бы всегда (по
        # проекту наступали на это шесть раз).
        self.assertIn('class="wk-rail"', html)
        self.assertIn('Что кладём', html)
        self.assertIn('Выдача', html)

    def test_from_my_problems_the_old_crumb_stays(self):
        html = self.client.get(reverse('teacher:problem_new')).content.decode()
        self.assertIn('Мои задачи', _crumb_text(html))
        # Шапки потока нет: ни переключателя вида, ни ленты шагов.
        self.assertNotIn('<a class="bh-kind__opt', html)
        self.assertNotIn('class="wk-rail"', html)


class KindSwitcherTests(Base):
    """9.2 — вид работы стал компактным переключателем."""

    def _html(self):
        return self.client.get(
            reverse('teacher:work_pick')
            + '?group=%d' % self.group.pk).content.decode()

    def test_kind_is_not_a_tile_anymore(self):
        html = self._html()
        self.assertNotIn('k-tiles bh-kind', html)
        # ⚠️ Считаем РАЗМЕТКУ: имя класса встречается ещё и в правилах
        # набора, которые вклеены в <style> страницы.
        self.assertEqual(html.count('<a class="bh-kind__opt'), 2)

    def test_ways_to_pick_are_tabs_now(self):
        """⚠️ ПЕРЕСЧИТАН: плитки способов заменены вкладками первого шага.

        Прежнее ожидание («ровно три плитки») относилось к удалённому ряду
        `_build_modes`. Способов по-прежнему три, но они стали вкладками —
        переход между ними больше не теряет набранное (ревью 17.08, п. 4.5).
        """
        html = self._html()
        self.assertNotIn('<span class="k-tile__name">', html)
        for name in ('Искать самому', 'Описать словами', 'Написать свою'):
            self.assertIn(name, html)

    def test_the_note_is_not_lost(self):
        html = self._html()
        self.assertIn('решают дома, срок сдачи', html)

    def test_the_note_follows_the_chosen_kind(self):
        html = self.client.get(
            '%s?group=%d&kind=exam' % (reverse('teacher:work_pick'),
                                       self.group.pk)).content.decode()
        note = re.search(r'class="bh-kind__note">(.*?)<', html).group(1)
        self.assertEqual(note, 'ограниченное время, окно')

    def test_switcher_is_lighter_than_the_tiles(self):
        """⚠️ Проверяется ОТНОШЕНИЕ, а не конкретный кегль.

        Раньше здесь стояло `assertIn('font-size: 12px')`. Проверка ломалась
        от любой правки шкалы, при этом само свойство «переключатель легче
        плиток» не сторожила вовсе: 12 px рядом с плитками в 12 px прошли бы.
        01.09.2026 пол шкалы подняли, 12 стало 13 — и тест покраснел, хотя
        переключатель остался легче плитки (13 против 14).
        """
        import re as _re
        kit = read('templates', '_kit.html')

        def кегль(селектор):
            блок = kit.split(селектор)[1].split('}')[0]
            return float(_re.search(r'font-size:\s*([\d.]+)px', блок).group(1))

        переключатель = кегль('.bh-kind__opt {')
        плитка = кегль('.k-tile__name {')
        self.assertLess(переключатель, плитка,
                        'переключатель обязан быть легче плитки: %s против %s'
                        % (переключатель, плитка))
        # Пол канона для подписи — оба конца обязаны его держать.
        self.assertGreaterEqual(переключатель, 13)
        # Заливки у невыбранного нет — только у активного сегмента.
        block = kit.split('.bh-kind__opt {')[1].split('}')[0]
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
        # ⚠️ ПЕРЕСЧИТАН (визуальная сессия 17.08, п. 2.1): разметка панели
        # переехала в свой партиал — она стоит на двух экранах.
        page = read('teacher', 'templates', 'teacher', '_ask_panel.html')
        block = page.split('function paint()')[1].split('}')[0]
        self.assertIn('if (o || t)', block)

    def test_empty_state_still_says_nothing_chosen(self):
        page = read('teacher', 'templates', 'teacher', '_ask_panel.html')
        self.assertIn("'ничего не выбрано'", page)


class ColumnOrderTests(Base):
    """9.4 — сверху что за работа, снизу чем наполняем."""

    def _give(self, kind='homework'):
        tail = '?group=%d' % self.group.pk
        if kind == 'exam':
            tail += '&kind=exam'
        return self.client.get(reverse('teacher:work_give')
                               + tail).content.decode()

    def _order(self, html):
        """Порядок блоков настроек по их заголовкам."""
        return re.findall(r'class="ws-title"[^>]*>(.*?)<', html)

    def test_homework_settings_stand_above_the_cart(self):
        """⚠️ ПЕРЕСЧИТАН: правой колонки конструктора больше нет.

        Настройки работы спрашиваются на шаге «Выдача», а состав живёт на
        шаге раньше (ревью 17.08, п. 4.5). Порядок внутри настроек прежний
        и по-прежнему проверяется: сначала сама работа, потом кому выдать.
        """
        self.assertEqual(self._order(self._give())[:2],
                         ['Настройки работы', 'Кому выдать'])

    def test_exam_uses_the_same_order(self):
        """Разводить порядок на двух видах работы нельзя."""
        self.assertEqual(self._order(self._give('exam'))[:2],
                         ['Настройки работы', 'Кому выдать'])

    def test_button_stayed_last(self):
        """Кнопка выдачи — последняя на экране, ниже настроек."""
        html = self._give()
        self.assertLess(html.index('Кому выдать'), html.index('id="wk-next"'))

    def test_button_ids_did_not_change(self):
        """⚠️ ПЕРЕСЧИТАН: кнопка создания переехала в полосу собранного.

        Прежние `submit-btn` / `submit-why` принадлежали удалённым
        конструкторам. Их роль играют `wk-next` и `wk-why`, и запрет
        перехода ставит одно место — полоса (ревью 17.08, фаза 12).
        """
        html = self._give()
        self.assertIn('id="wk-next"', html)
        self.assertIn('id="wk-why"', html)

    def test_only_one_button_on_the_page(self):
        for kind in ('homework', 'exam'):
            html = self._give(kind)
            self.assertEqual(html.count('id="wk-next"'), 1, kind)


class SubmitLabelTests(Base):
    """9.5 — надпись кнопки следует за видом работы.

    ⚠️ ПЕРЕСЧИТАН ЦЕЛИКОМ (ревью 17.08, п. 4.5). Надписей «Создать домашку»
    и «Создать контрольную» больше нет: кнопка в потоке одна и называется
    «Выдать работу», а вид работы виден на ленте шагов и в переключателе
    над ней. Требование, ради которого писался класс, — «человек видит, что
    именно он создаёт» — проверяется теперь по этому переключателю и по
    подписи под ним.
    """

    def _give(self, kind='homework'):
        tail = '?group=%d' % self.group.pk
        if kind == 'exam':
            tail += '&kind=exam'
        return self.client.get(reverse('teacher:work_give')
                               + tail).content.decode()

    def test_homework_says_homework(self):
        html = self._give()
        self.assertIn('Выдать работу', html)
        self.assertIn('решают дома, срок сдачи', html)

    def test_switching_to_exam_stays_on_the_same_step(self):
        """⚠️ Переключатель ведёт на ТОТ ЖЕ шаг, а не на другой экран."""
        html = self._give()
        links = re.findall(r'<a class="bh-kind__opt[^"]*"\s+href="([^"]+)"', html)
        exam_url = links[1].replace('&amp;', '&')
        self.assertIn(reverse('teacher:work_give'), exam_url)
        self.assertIn('kind=exam', exam_url)
        exam_html = self.client.get(exam_url).content.decode()
        self.assertIn('ограниченное время, окно', exam_html)

    def test_exam_needs_no_group_in_the_address_anymore(self):
        """⚠️ ПЕРЕСЧИТАН: конструктор контрольной жил ВНУТРИ занятия, и без
        номера адрес не собирался. Теперь занятие выбирают на шаге
        «Выдача», и путь к контрольной есть даже без `?group=`.
        """
        html = self.client.get(reverse('teacher:work_give')).content.decode()
        links = re.findall(r'<a class="bh-kind__opt[^"]*"\s+href="([^"]+)"', html)
        self.assertEqual(len(links), 2)
        self.assertIn('kind=exam', links[1])


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

    def test_no_control_of_the_old_row_was_lost(self):
        """Ни один орган прежнего ряда отбора не потерян при переезде.

        ⚠️ РЯДА `wk-filters` БОЛЬШЕ НЕТ: отбор перешёл на ОБЩИЙ компонент
        фильтров каталога в режиме «панель» (решение владельца
        01.09.2026). Проверка сохраняет прежний смысл — «ни один элемент
        не потерян», — но ищет их там, где они теперь живут: поиск и
        кнопка в форме, остальное группами компонента. Имена групп взяты
        те же, что были у полей старого ряда, поэтому пропажа любой из
        них по-прежнему красит эту проверку.
        """
        from problems.management.commands.apply_topic_mapping import CANONICAL
        from problems.models import Problem, Topic

        # Компонент показывает группу, только если поле размечено хоть у
        # одной задачи, — поэтому проверка сначала заводит такую задачу.
        # Без неё «пусто» и «фильтр потерян» были бы неотличимы.
        topic = Topic.objects.create(name=CANONICAL[0])
        problem = Problem.objects.create(
            statement='Условие для проверки набора фильтров.',
            solution='Решение есть.', difficulty=3,
            status=Problem.Status.PUBLISHED)
        problem.topics.add(topic)

        html = self.client.get(reverse('teacher:work_pick'),
                               {'difficulty': '3'}).content.decode()
        panel = html.split('class="wk-side"')[1].split('</aside>')[0]
        self.assertIn('name="q"', panel)
        self.assertIn('Найти', panel)
        self.assertIn('Сбросить', panel)
        for key in ('topic', 'difficulty', 'kind', 'has_solution'):
            self.assertIn('data-fl="%s"' % key, panel)
