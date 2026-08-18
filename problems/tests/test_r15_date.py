# -*- coding: utf-8 -*-
"""Фаза 10 объединённого ревью 15.08: своё поле даты и свой календарь.

⚠️ ЧТО ИМЕННО БЫЛО СЛОМАНО. Замер владельца: набор «20082026 1830» с
клавиатуры ПОКАЗЫВАЛСЯ в поле, но значение оставалось ПУСТЫМ — работа
создавалась без срока, и репетитор об этом не узнавал. Принимался только
формат «20.08.2026, 18:30» со всеми разделителями.

Разбор маски проверяется ИСПОЛНЕНИЕМ в node: дефект живёт в JavaScript, и
питон-тест его не увидит — страница отдаёт 200 при любой ошибке скрипта.
Живой календарь (мышь, клавиатура, лист снизу) снимает браузерный сценарий
`scripts/r15_date_probe.js`.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from django.template.loader import render_to_string
from django.test import TestCase

NODE = shutil.which('node')

# Пробы: набранное → что обязано уехать на сервер.
# ⚠️ Первая строка — тот самый случай владельца.
PROBES = [
    ['20082026 1830', '2026-08-20T18:30', 'без единого разделителя'],
    ['20.08.2026, 18:30', '2026-08-20T18:30', 'полный формат'],
    ['20/08/2026 18.30', '2026-08-20T18:30', 'слэш и точка'],
    ['20082026', '2026-08-20T23:59', 'дата без времени — время по умолчанию'],
    ['01012027', '2027-01-01T23:59', 'первое января'],
    ['29022028', '2028-02-29T23:59', 'високосный год'],
    ['', '', 'пусто — законный ответ «срока нет»'],
    # ⚠️ ДВУЗНАЧНЫЙ ГОД (ревью 16.08, п. 3.1). Понимается ровно потому, что
    # набранный разделитель ЗАКРЫВАЕТ поле года, а не потому, что мы
    # угадали: «140826 2000» и «14.08.26, 20:00» разбираются одинаково.
    ['140826 2000', '2026-08-14T20:00', 'двузначный год через пробел'],
    ['14.08.26, 20:00', '2026-08-14T20:00', 'двузначный год с точками'],
    ['14.08.26', '2026-08-14T23:59', 'двузначный год без времени'],
]

# Пробы, которые обязаны ОТКАЗАТЬ со словами, а не молча дать пустоту.
REFUSALS = [
    ['2008', 'дата набрана не до конца'],
    ['200820261', 'время набрано не до конца'],
    ['20082026 2560', 'часов и минут таких не бывает'],
    ['31022026', 'такой даты нет в календаре'],
    ['32082026', 'такого дня нет'],
    ['14.08.202, 20:00', 'год набран не до конца'],
]

# ⚠️ ГРАНИЦЫ СРОКА (ревью 16.08, п. 3.2). Проверяем отдельно и с ЯВНЫМИ
# границами: иначе тест зависел бы от того, какое сегодня число, и однажды
# покраснел бы сам собой.
BOUNDS = ['2026-08-16', '2027-12-31']
BOUND_PROBES = [
    ['15082026', False, 'вчерашний день не принимается'],
    ['16082026', True, 'сегодня — можно'],
    ['31122027', True, 'последний разрешённый день'],
    ['01012028', False, 'дальше границы — нельзя'],
]

# ⚠️ Границы разбора и границы формата — РАЗНЫЕ вопросы, поэтому пробы
# формата идут с заведомо широкими границами. Иначе «високосный 2028» из
# проверки календаря превратился бы в проверку потолка.
WIDE = ['2000-01-01', '2099-12-31']

HARNESS = r"""
%(functions)s

function boundsOf(pair) {
  return { min: dateFromIso(pair[0] + 'T00:00'),
           max: dateFromIso(pair[1] + 'T23:59') };
}
var wide = boundsOf(%(wide)s);

var out = { masked: [], parsed: [], refused: [], bounded: [] };
%(probes)s.forEach(function (probe) {
  out.masked.push(maskOf(fieldsOf(probe[0])));
  var result = parse(probe[0], '23:59', wide);
  out.parsed.push(result.why ? null : result.iso);
});
%(refusals)s.forEach(function (probe) {
  var result = parse(probe[0], '23:59', wide);
  out.refused.push(result.why || null);
});
var tight = boundsOf(%(bounds)s);
%(bound_probes)s.forEach(function (probe) {
  var result = parse(probe[0], '23:59', tight);
  out.bounded.push(result.why ? result.why : null);
});
console.log(JSON.stringify(out));
"""


def _functions():
    """Чистые функции разбора — прямо из боевого скрипта, не копией.

    ⚠️ Копировать их в тест нельзя: копия перестанет отличаться от
    оригинала ровно в тот день, когда оригинал починят.
    """
    page = render_to_string('teacher/_date_field_js.html')
    script = re.search(r'<script>(.*?)</script>', page, re.S).group(1)
    # ⚠️ ПЕРЕСЧИТАН 16.08: `digitsOf` больше нет — разделители теперь
    # значат «поле кончилось», и разбор идёт по полям (`fieldsOf`), а не
    # по сплошной строке цифр. Плюс появились границы срока.
    wanted = ('pad', 'fieldsOf', 'maskOf', 'dateFromIso', 'human',
              'outOfBounds', 'parse')
    out = []
    for name in wanted:
        found = re.search(r'\n  function %s\(.*?\n  \}\n' % name, script, re.S)
        assert found, 'функция %s пропала из скрипта поля даты' % name
        out.append(found.group(0))
    return '\n'.join(out)


@unittest.skipIf(NODE is None, 'node не установлен')
class DateMaskTests(TestCase):
    """Маска и разбор — исполнением, а не чтением."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        dump = lambda value: json.dumps(value, ensure_ascii=False)
        source = HARNESS % {'functions': _functions(),
                            'probes': dump(PROBES),
                            'refusals': dump(REFUSALS),
                            'wide': dump(WIDE),
                            'bounds': dump(BOUNDS),
                            'bound_probes': dump(BOUND_PROBES)}
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, 'probe.js')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(source)
        run = subprocess.run([NODE, path], capture_output=True, text=True,
                             encoding='utf-8')
        assert run.returncode == 0, run.stderr
        cls.result = json.loads(run.stdout)
        shutil.rmtree(folder, ignore_errors=True)

    def test_digits_only_input_becomes_a_real_value(self):
        """⚠️ ТОТ САМЫЙ ДЕФЕКТ: «20082026 1830» без разделителей."""
        self.assertEqual(self.result['parsed'][0], '2026-08-20T18:30')

    def test_every_probe_parses(self):
        for index, probe in enumerate(PROBES):
            self.assertEqual(self.result['parsed'][index], probe[1], probe[2])

    def test_mask_puts_the_separators_itself(self):
        self.assertEqual(self.result['masked'][0], '20.08.2026, 18:30')
        self.assertEqual(self.result['masked'][3], '20.08.2026')

    def test_partial_input_never_passes_silently(self):
        """Неполный ввод объясняется словами, а не обнуляется молча."""
        for index, probe in enumerate(REFUSALS):
            why = self.result['refused'][index]
            self.assertTrue(why, probe[1])
            self.assertTrue(len(why) > 10, 'объяснение слишком короткое')

    def test_impossible_date_is_refused_by_the_calendar(self):
        """31 февраля обязано быть отказом, а не 3 марта."""
        self.assertIn('календаре', self.result['refused'][3])

    def test_two_digit_year_means_twenty_something(self):
        """⚠️ Ревью 16.08, п. 3.1: «140826 2000» это 2026 год, не 2620.

        Прошлая сессия объявила двузначный год непонимаемым, и это было
        верно ДЛЯ ТОЙ маски: она выбрасывала разделители, и «14.08.26 20:00»
        превращалось в сплошное «1408262000», где 2620 и 26 неотличимы.
        Разделитель теперь закрывает поле — и различать стало чем.
        """
        for text, want, why in PROBES:
            if not text.startswith('1408') and not text.startswith('140826'):
                continue
            index = [p[0] for p in PROBES].index(text)
            self.assertEqual(self.result['parsed'][index], want, why)

    def test_year_without_separator_stays_four_digits(self):
        """Цена размена названа вслух: слитный набор — только полный год.

        «1408262000» без разделителей — это 14.08.2620, и иначе быть не
        может: различать нечем. Двузначный год требует разделителя ровно
        так, как его и набирают руками.
        """
        index = [p[0] for p in PROBES].index('20082026 1830')
        self.assertEqual(self.result['parsed'][index], '2026-08-20T18:30')

    def test_bounds_are_enforced_with_words(self):
        """⚠️ Ревью 16.08, п. 3.2: раньше сегодня и позже 2027 — отказ."""
        for index, probe in enumerate(BOUND_PROBES):
            why = self.result['bounded'][index]
            if probe[1]:
                self.assertIsNone(why, probe[2])
            else:
                self.assertTrue(why, probe[2])
                self.assertTrue(len(why) > 15, why)

    def test_refusal_never_shows_a_sample_value(self):
        """⚠️ Ревью 16.08, п. 3.4: жалоба не подсказывает значение.

        Прежнее «Нужны часы и минуты: 18:30» читалось как «поставьте
        18:30» — то есть как прежнее значение поля. Формат стоит в
        placeholder, и повторять его в жалобе незачем.
        """
        for why in self.result['refused']:
            self.assertNotRegex(why or '', r'\d\d:\d\d')
            self.assertNotRegex(why or '', r'\d\d\.\d\d\.\d\d')


class DateFieldMarkupTests(TestCase):
    """Договор с сервером не изменился, родного календаря больше нет."""

    def field(self):
        return render_to_string('teacher/_date_field.html', {
            'field_name': 'deadline', 'field_id': 'id_deadline',
            'default_time': '23:59'})

    def test_value_still_lives_in_a_named_native_field(self):
        markup = self.field()
        self.assertIn('type="datetime-local"', markup)
        self.assertIn('name="deadline"', markup)
        self.assertIn('id="id_deadline"', markup)

    def test_native_picker_is_gone(self):
        """⚠️ Двух календарей на одном поле быть не должно."""
        script = render_to_string('teacher/_date_field_js.html')
        self.assertNotIn('showPicker', script)

    def test_native_field_is_hidden_when_the_script_worked(self):
        kit = render_to_string('_kit.html')
        self.assertIn('.k-date.is-ready .k-date__native { display: none; }',
                      kit)

    def test_calendar_template_is_included_once(self):
        """⚠️ Поле стоит на странице трижды, `<template>` — один раз."""
        self.assertNotIn('k-date-pop-tpl', self.field())
        self.assertIn('k-date-pop-tpl',
                      render_to_string('teacher/_date_field_js.html'))

    def test_two_steps_in_one_window(self):
        script = render_to_string('teacher/_date_field_js.html')
        self.assertIn('k-cal__step--date', script)
        self.assertIn('k-cal__step--time', script)
        self.assertIn('data-cal-done', script)

    def test_today_and_clear_are_there(self):
        script = render_to_string('teacher/_date_field_js.html')
        self.assertIn('data-cal-today', script)
        self.assertIn('data-cal-clear', script)
        self.assertIn('>Сегодня<', script)
        self.assertIn('>Очистить<', script)

    def test_narrow_screen_opens_a_bottom_sheet(self):
        kit = render_to_string('_kit.html')
        piece = kit.split('@media (max-width: 520px)')[-1]
        self.assertIn('.k-date.is-open .k-cal { position: fixed', piece)

    def test_keyboard_moves_by_days(self):
        script = render_to_string('teacher/_date_field_js.html')
        self.assertIn('ArrowLeft', script)
        self.assertIn('ArrowDown', script)
        self.assertIn("event.key === 'Escape'", script)


class TimeIsANumberTests(TestCase):
    """⚠️ Ревью 16.08, п. 3.6: время — крупное число, а не поля ввода."""

    def script(self):
        return render_to_string('teacher/_date_field_js.html')

    def test_no_input_boxes_left_in_the_time_panel(self):
        """Владелец назвал прежние прокручиваемые списки «окошками»."""
        script = self.script()
        panel = script.split('k-cal__step--time')[1].split('</template>')[0]
        self.assertNotIn('<input', panel)
        self.assertNotIn('k-cal__list', panel)
        self.assertNotIn('k-cal__pick', panel)

    def test_hour_and_minute_are_buttons(self):
        """Кнопки, а не `<span>`: их берёт Tab и слышит читалка."""
        script = self.script()
        self.assertIn('data-time-part="hour"', script)
        self.assertIn('data-time-part="minute"', script)
        self.assertIn('aria-label="Часы"', script)

    def test_typing_arrows_and_wheel_all_work(self):
        script = self.script()
        for piece in ('function typeDigit', 'ArrowUp', "'wheel'",
                      'function bump'):
            self.assertIn(piece, script)

    def test_escape_undoes_and_enter_confirms(self):
        script = self.script()
        panel = script[script.index('function onTimeKeys'):]
        self.assertIn("event.key === 'Escape'", panel)
        self.assertIn('stopEdit(true)', panel)
        self.assertIn("event.key === 'Enter'", panel)

    def test_active_number_has_no_frame_only_an_underline(self):
        kit = render_to_string('_kit.html')
        rules = kit[kit.index('.k-time {'):kit.index('.k-cal__foot--time')]
        self.assertIn('border: 0', rules)
        self.assertIn('border-bottom: 2px solid transparent', rules)
        self.assertIn('.k-time__num.is-on', rules)


class DateFieldLayoutTests(TestCase):
    """⚠️ Ревью 16.08, п. 3.5: значок календаря не уезжает от сообщения."""

    def test_icon_is_positioned_from_the_row_not_the_whole_box(self):
        markup = render_to_string('teacher/_date_field.html', {
            'field_name': 'deadline', 'field_id': 'id_deadline'})
        # Сообщение — СНАРУЖИ ряда: иначе оно растягивает то, от чего
        # считается кнопка, и значок уезжает вниз и вправо.
        row = markup[markup.index('k-date__row'):markup.index('k-date__err')]
        self.assertIn('k-date__pick', row)
        self.assertNotIn('k-date__err', row)
        kit = render_to_string('_kit.html')
        self.assertIn('.k-date__row { position: relative; }', kit)


class SubmitIsLockedByABadDateTests(TestCase):
    """⚠️ Ревью 16.08, п. 3.3: красное поле запирает выдачу.

    Пока кнопка оставалась активной, уходило ПРЕЖНЕЕ значение из родного
    поля: на экране одно, на сервер другое — и заметить это нечем.
    """

    def test_both_gates_count_a_bad_date(self):
        """⚠️ ПЕРЕСЧИТАН (ревью 17.08, п. 4.5): шлюз остался ОДИН.

        Их было два — у прежнего конструктора и у шага «Выдача», — и
        проверялось, что оба считают красное поле причиной запрета.
        Конструктор удалён; требование стало сильнее: запрет ставит одно
        место, полоса собранного, и второго шлюза нигде нет.
        """
        with open('teacher/templates/teacher/work/give.html',
                  encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn(".k-date__text.is-bad", text)
        self.assertIn("out.push('проверьте ", text)

    def test_the_reason_names_the_field(self):
        markup = render_to_string('teacher/_work_settings.html', {
            'is_exam': False, 'form': {}})
        self.assertIn('data-what="срок сдачи"', markup)


class DateFieldOnScreensTests(TestCase):
    """Поле стоит на всех трёх сроках и скрипт подключён один раз."""

    def test_all_three_fields_use_the_partial(self):
        with open('teacher/templates/teacher/_work_settings.html',
                  encoding='utf-8') as fh:
            panel = fh.read()
        for name in ('deadline', 'starts_at', 'ends_at'):
            self.assertIn("field_name='%s'" % name, panel)
        # Четыре включения на три поля: у срока сдачи их два — своё в
        # ветке контрольной (окно) и своё в ветке домашки (лимит).
        self.assertEqual(panel.count('_date_field.html'), 4)
