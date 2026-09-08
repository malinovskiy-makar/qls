# -*- coding: utf-8 -*-
u"""«Тревога» Wecon Rush: виньетка, сердцебиение, покраснение (фаза 2).

Условие тревоги одно на два повода: последние 10 % СТАРТОВОГО запаса
режима или последняя жизнь. Абсолютных порогов («амбер < 15 с, красный
< 7 с») больше нет — они были одинаковыми для Пули и Классики, у которых
запас отличается в десять раз.

Арифметику проверяет `alarm_check.mjs`: он вырезает функции прямо из
game.html и считает ими, а не копией — копия разъехалась бы с боевым
кодом при первой правке порога.
"""
import io
import re
import os
import shutil
import subprocess
import unittest

from django.conf import settings
from django.test import SimpleTestCase, TestCase

RUNNER = os.path.join(os.path.dirname(__file__), 'alarm_check.mjs')
PAGE = 'game/templates/game/game.html'
SOUND = 'game/static/game/sound.js'


def read(path):
    return io.open(path, encoding='utf-8').read()


def no_comments(text):
    u"""Текст без комментариев JS.

    ⚠️ БЕЗ ЭТОГО ПРОВЕРКИ ОБМАНЫВАЕТ СОБСТВЕННЫЙ КОММЕНТАРИЙ. Поймано на
    фазе 14: убрали вызов `wake()` из `thump()`, а тест остался зелёным —
    строку `wake()` он нашёл в комментарии над убранным вызовом. Тест,
    который не краснеет, — это не тест.
    """
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', text)


def body_of(src, header):
    u"""Тело функции или блока от `header` до парной закрывающей скобки.

    Нужно именно тело, а не «где-то в файле»: вызов `clearAlarm()` рядом с
    `endRun`, но не внутри него, дефект не чинит.
    """
    start = src.index(header) + len(header)   # header кончается на `{`
    depth = 1
    i = start
    while depth:
        ch = src[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        i += 1
    return src[start:i]


class AlarmArithmeticTest(SimpleTestCase):
    u"""Три контрольные точки задания плюс границы окна и темп."""

    def test_alarm_numbers(self):
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node не найден — пропускаю арифметику тревоги')
        if not os.path.exists(RUNNER):
            raise unittest.SkipTest('раннер не найден: %s' % RUNNER)
        try:
            res = subprocess.run([node, RUNNER], cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, timeout=120,
                                 encoding='utf-8', errors='replace')
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise unittest.SkipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        self.assertEqual(res.returncode, 0, out)
        self.assertIn('ok:', out)


class SoundModuleTests(SimpleTestCase):
    u"""2.2 Сердцебиение вместо фонового гула."""

    def test_sound_js_parses(self):
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node не найден')
        res = subprocess.run([node, '--check', SOUND],
                             cwd=str(settings.BASE_DIR), capture_output=True,
                             text=True, encoding='utf-8', errors='replace')
        self.assertEqual(res.returncode, 0,
                         (res.stdout or '') + (res.stderr or ''))

    def test_low_layer_is_gone(self):
        u"""Гул и сердцебиение — два звука об одной опасности; остаётся один."""
        src = read(SOUND)
        self.assertNotIn('lowLayer', src)
        self.assertNotIn('lowLayerOn', src)
        page = read(PAGE)
        self.assertNotIn('lowLayerOn', page)
        self.assertNotIn('lowLayerOff', page)
        self.assertNotIn('lowPulse', page)

    def test_heartbeat_api(self):
        src = read(SOUND)
        for name in ('start:', 'set:', 'stop:'):
            self.assertIn(name, src, name)
        self.assertIn('heartbeat: heartbeat', src)

    def test_thump_is_two_hits_sliding_down(self):
        u"""«Туп-туп»: синус 55 → 40 Гц, второй удар через 140 мс и тише."""
        src = read(SOUND)
        self.assertIn('osc.frequency.setValueAtTime(55, t0)', src)
        self.assertIn('exponentialRampToValueAtTime(40, t0 + 0.12)', src)
        self.assertIn('thump(t0, 0.5)', src)
        self.assertIn('thump(t0 + 0.14, 0.3)', src)

    def test_scheduler_uses_audio_clock_not_setinterval(self):
        u"""setInterval плывёт на десятки миллисекунд — удары зашатались бы."""
        src = read(SOUND)
        self.assertIn('ctx.currentTime', src)
        self.assertNotIn('setInterval(', src)   # вызова нет; в комментарии слово есть

    def test_beat_event_fires_even_with_sound_off(self):
        u"""По удару пульсируют виньетка и полоса. Замолчи планировщик вместе
        со звуком — картинка застыла бы у играющих без звука."""
        import re as _re
        src = read(SOUND)
        self.assertIn("new CustomEvent('rush:beat')", src)
        # ⚠️ Проверяем СТРУКТУРОЙ, а не порядком строк: сдвинуть строку внутрь
        # условия можно, не меняя порядка, и проверка по индексам это проспит.
        # Под условием enabled() обязаны лежать ТОЛЬКО два удара звука.
        m = _re.search(r'if \(enabled\(\) && !hb\.silent\) \{(.*?)\n    \}',
                       src, _re.S)
        self.assertIsNotNone(m, 'условие звука в beatAt не найдено')
        guarded = m.group(1)
        self.assertIn('thump(t0, 0.5)', guarded)
        self.assertIn('thump(t0 + 0.14, 0.3)', guarded)
        self.assertNotIn('rush:beat', guarded,
                         'событие удара оказалось ПОД условием звука: '
                         'без звука картинка перестанет пульсировать')
        self.assertNotIn('var delay', guarded)

    def test_master_volume_stays_quiet(self):
        self.assertIn('master.gain.value = 0.18;', read(SOUND))


class SoundSurvivesSleepAndDeviceChangeTests(SimpleTestCase):
    u"""Звук перестаёт пропадать (08.09.2026).

    ⚠️ ПРИЧИНА ОДНОЙ НЕ НАЗЫВАЕТСЯ. Владелец видел пропажу звука на
    Windows; воспроизвести её на разборе не удалось, и утверждать «дело
    было в этом» нечестно. Известны ТРИ механизма, и все три лечатся одним
    приёмом — самовосстановлением контекста:

    1. Chrome на Windows усыпляет AudioContext при уходе со вкладки, и
       state становится `suspended`.
    2. resume() звала только tone(), а сердцебиение (thump) — нет: после
       сна пульс молчал, хотя ноты играли.
    3. Смена устройства вывода (воткнули наушники) оставляет контекст в
       состоянии `running`, но звука в нём больше нет; лечится только
       пересозданием.

    Проверяется наличие всех трёх лечений: закрытый контекст, спящий
    контекст, неподвижные часы.
    """

    def setUp(self):
        self.src = read(SOUND)

    def test_wake_exists_and_resumes(self):
        self.assertIn('function wake() {', self.src)
        body = no_comments(body_of(self.src, 'function wake() {'))
        self.assertIn("c.state !== 'running'", body)
        self.assertIn('c.resume()', body)

    def test_tone_thump_and_heartbeat_all_wake_first(self):
        u"""Механизм 2: раньше будила только tone(), и пульс молчал.

        ⚠️ Комментарии вырезаются: рядом с вызовом стоит объяснение, в
        котором тоже написано `wake()`, и без чистки проверка находила бы
        его вместо вызова (поймано мутацией на фазе 14).
        """
        for header in ('function tone(opts) {',
                       'function thump(t0, vol) {'):
            body = no_comments(body_of(self.src, header))
            self.assertIn('= wake();', body, header)
            self.assertNotIn('var c = ctx;', body, header)
        # heartbeat.start — метод объекта, не функция
        start = no_comments(self.src.split('start: function (bpm) {', 1)[1]
                            .split('},', 1)[0])
        self.assertIn('wake();', start)
        self.assertNotIn('audio();', start)

    def test_closed_context_is_recreated(self):
        u"""Механизм 1 (крайний случай): закрытый контекст — не живой объект."""
        body = no_comments(body_of(self.src, 'function audio() {'))
        self.assertIn("ctx.state === 'closed'", body)
        self.assertIn('ctx = null; master = null;', body)

    def test_a_stopped_clock_counts_as_a_dead_context(self):
        u"""Механизм 3: running, а currentTime стоит — контекст мёртв."""
        body = no_comments(body_of(self.src, 'function watchClock(replay) {'))
        self.assertIn('c.currentTime !== was', body)
        self.assertIn("c.state !== 'running'", body)
        self.assertIn('respawn()', body)

    def test_the_retry_happens_exactly_once(self):
        u"""⚠️ Бесконечная цепочка пересозданий хуже тишины."""
        body = no_comments(body_of(self.src, 'function watchClock(replay) {'))
        self.assertIn('if (clock.retried) return;', body)
        self.assertIn('clock.retried = true;', body)
        # И снимается, как только часы пошли: вторая смена наушников за
        # сессию тоже должна лечиться.
        self.assertIn('clock.retried = false;', body)

    def test_respawn_reschedules_the_heartbeat(self):
        u"""Часы нового контекста идут с нуля — иначе пульс замолчал бы."""
        body = no_comments(body_of(self.src, 'function respawn() {'))
        self.assertIn('hb.next = hbNow() + 0.05;', body)

    def test_returning_to_the_tab_wakes_the_sound(self):
        self.assertIn("addEventListener('visibilitychange'", self.src)
        self.assertEqual(self.src.count("'visibilitychange'"), 1)

    def test_nothing_here_can_break_the_game(self):
        u"""Весь новый код — под try/catch, как beatApi и rush() на странице."""
        for header in ('function wake() {',
                       'function respawn() {',
                       'function watchClock(replay) {'):
            self.assertIn('try {', body_of(self.src, header), header)


class AlarmPaintTests(TestCase):
    u"""2.1, 2.3 Виньетка, таймер и полоса."""

    def setUp(self):
        self.src = read(PAGE)

    def test_vignette_is_reused_with_an_alarm_state(self):
        # ⚠️ Сверяем СУЩЕСТВО правила, а не селектор подстрокой: правило
        # `body.figfull .vignette.alarm {` тоже содержит «.vignette.alarm {»,
        # и проверка на подстроку проспала бы пропажу самой тревоги.
        self.assertIn('.vignette.alarm {\n  opacity: 1;\n  box-shadow: none;\n'
                      '  background: radial-gradient(', self.src)
        self.assertIn('.vignette.on { animation: vin', self.src)   # вспышка цела

    def test_centre_stays_transparent_and_is_sized_from_the_scene(self):
        u"""Красная кайма не имеет права наползти на условие задачи."""
        self.assertIn('transparent 55%', self.src)
        self.assertIn('--al-rx', self.src)
        self.assertIn('--al-ry', self.src)
        self.assertIn('getBoundingClientRect()', self.src)
        self.assertIn('var ALARM_PAD = 24;', self.src)

    def test_edge_opacity_grows_with_alarm(self):
        self.assertIn('calc(25% + var(--alarm, 0) * 20%)', self.src)

    def test_pulse_follows_the_beat_event(self):
        self.assertIn("window.addEventListener('rush:beat'", self.src)
        self.assertIn('.vignette.alarm.beat { animation: alarmBeat', self.src)
        self.assertIn('.time-fill.beat { animation: barBeat', self.src)

    def test_reduced_motion_keeps_the_alarm_but_drops_the_pulse(self):
        self.assertIn('.vignette.alarm.beat { animation: none; }', self.src)
        self.assertIn('if (REDUCED || !alarmOn) return;', self.src)

    def test_timer_digits_redden_with_alarm(self):
        self.assertIn('color: color-mix(in srgb, var(--rush-bad) '
                      'calc(var(--alarm, 0) * 100%),', self.src)
        # Десятые при < 10 с не потеряны.
        self.assertIn("timeLeft <= 10 ? timeLeft.toFixed(1)", self.src)

    def test_bar_colour_is_a_gradient_not_three_steps(self):
        u"""Амбер на полосе больше не используется, ступеней mid/low нет."""
        self.assertNotIn('.time-fill.mid', self.src)
        self.assertNotIn('.time-fill.low', self.src)
        self.assertNotIn('--rush-time-mid', self.src)
        self.assertNotIn('--rush-time-low', self.src)
        self.assertIn('background: color-mix(in srgb, var(--rush-bad) '
                      'calc(var(--alarm, 0) * 100%),\n                        '
                      'var(--rush-time-hi));', self.src)

    def test_last_life_no_longer_has_its_own_frame(self):
        u"""Раньше рамка последней жизни жила отдельно и на исходе времени
        накладывалась на виньетку времени — два красных об одном и том же."""
        self.assertNotIn('last-life-frame', self.src)
        self.assertNotIn('lastLifeBreath', self.src)

    def test_sound_button_is_an_icon_not_a_typographic_note(self):
        self.assertNotIn("'♪'", self.src)
        self.assertIn('ICONS.sound_on', self.src)
        self.assertIn('ICONS.sound_off', self.src)
        icons = read('templates/_icons.html')
        self.assertIn('sound_on:', icons)
        self.assertIn('sound_off:', icons)

    def test_sound_state_key_is_unchanged(self):
        u"""Ключ хранения звука — тот же, что был на ветке: переименование
        игры не должно сбрасывать выбор игроков."""
        self.assertIn("var KEY = 'econ_rush_sound';", read(SOUND))


class AlarmIsClearedOnRunEndTests(SimpleTestCase):
    u"""Красная кайма не переживает забег (08.09.2026).

    ⚠️ ЧТО БЫЛО. Класс `alarm` вешает на `#vignette` только `paintAlarm()`,
    а её зовёт игровой цикл. После `show('finished')` цикл кончается, и
    снять класс становится некому — а `#vignette` лежит `fixed; inset: 0`
    поверх всего. Кайма переживала экран результата и возвращалась на
    стартовый: игра живёт в одной странице на три экрана.

    Дефект был виден не всегда: если забег кончался, когда времени было
    много, последний `paintAlarm()` успевал снять класс сам. Красным он
    оставался, только когда забег кончался В КРАСНОЙ ЗОНЕ — последние 10 %
    запаса режима или последняя жизнь. Отсюда «после некоторых партий».
    """

    def setUp(self):
        self.src = read(PAGE)

    def test_clear_alarm_is_defined_once_and_actually_clears(self):
        # ⚠️ Комментарии вырезаются везде в этом классе: рядом с вызовами
        # стоят объяснения, и без чистки проверка могла бы найти имя
        # функции в тексте про неё, а не сам вызов.
        self.assertEqual(self.src.count('function clearAlarm('), 1)
        body = no_comments(body_of(self.src, 'function clearAlarm() {'))
        self.assertIn("classList.remove('alarm'", body)
        self.assertIn('--alarm', body)
        self.assertIn('alarmOn = false;', body)
        self.assertIn("beatApi('stop')", body)

    def test_end_of_run_clears_it(self):
        body = no_comments(body_of(self.src, 'function endRun(reason) {'))
        self.assertIn('clearAlarm(', body)
        # ⚠️ Прежний голый `beatApi('stop')` из endRun убран: он теперь
        # внутри clearAlarm. Два места, гасящие звук, разъедутся.
        self.assertNotIn("beatApi('stop')", body)

    def test_quitting_mid_run_clears_it(self):
        u"""Кнопка выхода `btn-quit`.

        ⚠️ Вызов стоит в `quitRun`, а не в `openQuit`: `btn-quit` только
        открывает окно подтверждения, а забег за ним ПРОДОЛЖАЕТСЯ, и снятая
        там кайма вернулась бы следующим же кадром. Бросают забег в
        `quitRun` — туда вызов и поставлен.
        """
        self.assertIn("$('btn-quit').addEventListener('click', openQuit);",
                      self.src)
        self.assertIn('clearAlarm(', no_comments(body_of(self.src, 'function quitRun() {')))

    def test_a_new_run_starts_clean(self):
        self.assertIn('clearAlarm(', no_comments(body_of(self.src, 'function startRun(opts) {')))

    def test_three_call_sites_at_least(self):
        u"""Числовой инвариант: определение одно, вызовов не меньше трёх."""
        self.assertEqual(self.src.count('function clearAlarm('), 1)
        calls = self.src.count('clearAlarm(') - 1   # минус само определение
        self.assertGreaterEqual(calls, 3, calls)
