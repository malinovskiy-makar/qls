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

# Пробы: набранные цифры → что обязано уехать на сервер.
# ⚠️ Первая строка — тот самый случай владельца.
PROBES = [
    ['20082026 1830', '2026-08-20T18:30', 'без единого разделителя'],
    ['20.08.2026, 18:30', '2026-08-20T18:30', 'полный формат'],
    ['20/08/2026 18.30', '2026-08-20T18:30', 'слэш и точка'],
    ['20082026', '2026-08-20T23:59', 'дата без времени — время по умолчанию'],
    ['01012027', '2027-01-01T23:59', 'первое января'],
    ['29022028', '2028-02-29T23:59', 'високосный год'],
    ['', '', 'пусто — законный ответ «срока нет»'],
]

# Пробы, которые обязаны ОТКАЗАТЬ со словами, а не молча дать пустоту.
REFUSALS = [
    ['2008', 'дата набрана не до конца'],
    ['200820261', 'время набрано не до конца'],
    ['20082026 2560', 'часов и минут таких не бывает'],
    ['31022026', 'такой даты нет в календаре'],
    ['32082026', 'такого дня нет'],
]

HARNESS = r"""
%(functions)s

var out = { masked: [], parsed: [], refused: [] };
%(probes)s.forEach(function (probe) {
  var digits = digitsOf(probe[0]);
  out.masked.push(maskOf(digits));
  var result = parse(digits, '23:59');
  out.parsed.push(result.why ? null : result.iso);
});
%(refusals)s.forEach(function (probe) {
  var result = parse(digitsOf(probe[0]), '23:59');
  out.refused.push(result.why || null);
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
    wanted = ('pad', 'digitsOf', 'maskOf', 'parse')
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
        source = HARNESS % {'functions': _functions(),
                            'probes': json.dumps(PROBES, ensure_ascii=False),
                            'refusals': json.dumps(REFUSALS,
                                                   ensure_ascii=False)}
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, 'probe.js')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(source)
        run = subprocess.run([NODE, path], capture_output=True, text=True)
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
