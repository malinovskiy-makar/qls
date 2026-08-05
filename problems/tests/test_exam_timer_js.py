"""
Часы контрольной, проверенные БЕЗ браузера.

Зачем отдельный файл: питон-тесты сорока сценариев контрольной не увидели
дефекта, который человек нашёл за минуту — перевёл системные часы на десять
минут назад, и цифра на экране выросла на десять минут. На сервере всё было
верно; врал ПОКАЗ. Дефект жил в JavaScript, а JavaScript ни `manage.py check`,
ни рендер шаблона, ни `TestCase` не исполняют.

Здесь исполняем: `exam_timer.js` загружается в node с ПОДСТАВНЫМИ часами,
и мы двигаем время как ученик двигал бы системное.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import TestCase

TIMER_JS = os.path.join(settings.BASE_DIR, 'problems', 'static', 'platform',
                        'exam_timer.js')
EXAM_JS = os.path.join(settings.BASE_DIR, 'problems', 'static', 'platform',
                       'exam.js')


def code_only(path):
    """Текст файла без комментариев — иначе проверка «нет Date.now» падает
    на строчке комментария, которая объясняет, почему его нет."""
    import re

    with open(path, encoding='utf-8') as f:
        source = f.read()
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return '\n'.join(line for line in source.splitlines()
                     if not line.strip().startswith('//'))


def run_node(script):
    """Гоняет кусок JS в node вместе с `exam_timer.js`. Возвращает разобранный
    JSON из stdout."""
    with open(TIMER_JS, encoding='utf-8') as f:
        source = f.read()
    body = source + '\n' + script
    with tempfile.NamedTemporaryFile('w', suffix='.mjs', delete=False,
                                     encoding='utf-8') as f:
        f.write(body)
        path = f.name
    try:
        proc = subprocess.run(['node', path], capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        return json.loads(proc.stdout)
    finally:
        os.unlink(path)


@unittest.skipIf(shutil.which('node') is None, 'node не установлен')
class ExamTimerJsTests(TestCase):
    """Ровно тот класс дефектов, который питон-тесты не видят."""

    def test_device_clock_jump_does_not_change_the_display(self):
        """ГЛАВНЫЙ ТЕСТ СЕССИИ.

        Часы устройства уводим на десять минут назад — показанный остаток
        обязан остаться прежним. Раньше клиент сверялся по значению,
        посчитанному от подкрученных часов, и цифра прыгала вперёд.
        """
        result = run_node("""
          // Монотонные часы (performance.now) идут своим ходом; системные
          // (Date.now) ученик крутит как хочет.
          var mono = 0;
          var timer = globalThis.ExamTimer.create({
            seconds: 2400, clock: function () { return mono; }
          });
          var before = timer.remaining();
          // Прошла минута реального времени.
          mono += 60 * 1000;
          var afterMinute = timer.remaining();
          // Ученик перевёл системные часы на 10 минут назад. Монотонные
          // часы этого не заметили — значит и остаток не должен.
          Date.now = function () { return 0; };
          var afterHack = timer.remaining();
          console.log(JSON.stringify({
            before: before, afterMinute: afterMinute, afterHack: afterHack
          }));
        """)
        self.assertEqual(result['before'], 2400)
        self.assertEqual(result['afterMinute'], 2340)
        self.assertEqual(result['afterHack'], 2340,
                         'подкрутка системных часов сдвинула показ')

    def test_timer_source_never_calls_date_now(self):
        """`Date.now()` в часах контрольной запрещён на уровне текста файла.

        Мягкая формулировка «мы им не пользуемся» держится ровно до первой
        правки. Держим проверкой — по КОДУ, комментарии из проверки убраны
        (в них про `Date.now()` как раз и написано, почему его нельзя).
        """
        for path in (TIMER_JS, EXAM_JS):
            for banned in ('Date.now', 'new Date'):
                self.assertNotIn(banned, code_only(path),
                                 '%s: %s в коде часов'
                                 % (os.path.basename(path), banned))

    def test_server_can_only_take_time_away(self):
        """Сверка с сервером УМЕНЬШАЕТ остаток и никогда не увеличивает.

        Незаконных источников прибавки два: подкрученные часы устройства и
        (при сервере на той же машине) подкрученные часы сервера. Законного
        нет ни одного.
        """
        result = run_node("""
          var mono = 0;
          var timer = globalThis.ExamTimer.create({
            seconds: 600, clock: function () { return mono; }
          });
          var grew = timer.applyServer(1200);      // сервер «дал» больше
          var afterGrew = timer.remaining();
          var shrank = timer.applyServer(300);     // сервер отнял
          var afterShrank = timer.remaining();
          var jitter = timer.applyServer(298);     // сетевая задержка
          var afterJitter = timer.remaining();
          console.log(JSON.stringify({
            grew: grew, afterGrew: afterGrew,
            shrank: shrank, afterShrank: afterShrank,
            jitter: jitter, afterJitter: afterJitter
          }));
        """)
        self.assertEqual(result['grew'], 'ignored')
        self.assertEqual(result['afterGrew'], 600)
        self.assertEqual(result['shrank'], 'accepted')
        self.assertEqual(result['afterShrank'], 300)
        self.assertEqual(result['jitter'], 'skipped')
        self.assertEqual(result['afterJitter'], 300)

    def test_zero_and_expired(self):
        """Ноль — это конец, а не отрицательное число на экране."""
        result = run_node("""
          var mono = 0;
          var timer = globalThis.ExamTimer.create({
            seconds: 5, clock: function () { return mono; }
          });
          mono += 100 * 1000;
          console.log(JSON.stringify({
            left: timer.remaining(), expired: timer.expired(),
            text: timer.text()
          }));
        """)
        self.assertEqual(result['left'], 0)
        self.assertTrue(result['expired'])
        self.assertEqual(result['text'], '00:00')

    def test_exam_js_parses_and_polls_the_server_on_a_timer(self):
        """`exam.js` парсится и сверяется с сервером по таймеру.

        Сверка «только вместе с автосохранением» — ровно тот дефект, из-за
        которого смотрящий на часы ученик не сверялся с сервером никогда.
        """
        proc = subprocess.run(['node', '--check', EXAM_JS],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        code = code_only(EXAM_JS)
        self.assertIn('pollTime', code)
        self.assertIn('setInterval(pollTime, 15000)', code)
        self.assertIn('enterTimeUp', code)
