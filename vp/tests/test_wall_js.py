"""Решение окна стены «уходить с экрана или остаться» (`vpWallLeave` в vp/js/wall.js, S2c).

Функция чистая, поэтому проверяется таблицей через node без браузера. Нет node – тест
ПРОПУСКАЕТСЯ, как браузерные в test_browser.py.

⚠️ Таблица держит главный запрет S2c: на экране 03 (`okOnly`) ответ `no_sub` НЕ уводит
со страницы – иначе перезагрузка снова покажет 03 и страница ходила бы по кругу.
"""
import json
import shutil
import subprocess

from django.conf import settings
from django.test import SimpleTestCase

WALL_JS = str(settings.BASE_DIR / 'vp' / 'static' / 'vp' / 'js' / 'wall.js')

# (okOnly, ответ wall/state, ожидаемое решение)
CASES = [
    # 02: уходим на любой ответ бота
    (False, {'step': 'contact', 'tg': 'waiting'}, None),
    (False, {'step': 'contact', 'tg': 'none'}, None),
    (False, {'step': 'contact', 'tg': 'ok'}, 'ok'),
    (False, {'step': 'survey', 'tg': 'ok'}, 'ok'),
    (False, {'step': 'contact', 'tg': 'no_sub'}, 'nosub'),
    (False, {'step': 'contact', 'tg': 'error'}, 'nosub'),
    (False, {'step': 'play', 'tg': 'none'}, 'ok'),
    # 03: только подтверждённая подписка (или стена пройдена другим путём)
    (True, {'step': 'contact', 'tg': 'no_sub'}, None),
    (True, {'step': 'contact', 'tg': 'error'}, None),
    (True, {'step': 'contact', 'tg': 'waiting'}, None),
    (True, {'step': 'contact', 'tg': 'none'}, None),
    (True, {'step': 'contact', 'tg': 'ok'}, 'ok'),
    (True, {'step': 'survey', 'tg': 'no_sub'}, 'ok'),
    # нет ответа (сеть, 403) – остаёмся
    (True, None, None),
    (False, None, None),
]


class WallLeaveTableTests(SimpleTestCase):
    def test_table(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден – таблица wall.js не запускалась')
        script = ('const {vpWallLeave} = require(%s);'
                  'const cases = %s;'
                  'console.log(JSON.stringify(cases.map(c => vpWallLeave(c[0], c[1]))));'
                  % (json.dumps(WALL_JS), json.dumps([[c[0], c[1]] for c in CASES])))
        result = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        got = json.loads(result.stdout)
        for (ok_only, state, expected), actual in zip(CASES, got):
            self.assertEqual(actual, expected, 'okOnly=%s state=%s' % (ok_only, state))


# Сценарий самого скрипта без браузера: заглушки DOM, `fetch` и таймеров. Окно без showModal
# (`modal` ложно) – скрипт тогда не трогает <dialog> и только опрашивает.
SCENARIO = r'''
const answers = JSON.parse(process.argv[2]);
const okOnly = process.argv[3] === '1';
const replaced = [];
let timerFn = null, fetched = 0;
const attrs = okOnly ? {'data-poll': '/vp/wall/state/?v=x', 'data-poll-ok-only': ''} : {'data-variant': 'x'};
const waiting = {hidden: false, getAttribute: n => n === 'data-poll' ? '/vp/wall/state/?v=x' : null};
const dialog = {
  addEventListener() {}, querySelector: s => (!okOnly && s === '[data-screen="waiting"]') ? waiting : null,
  getAttribute: n => n in attrs ? attrs[n] : null, hasAttribute: n => n in attrs, open: true,
};
global.document = {getElementById: () => dialog, visibilityState: 'visible'};
global.window = {location: {pathname: '/vp/x/', search: '', href: 'http://t/vp/x/',
  replace: u => replaced.push(u)}, setInterval: f => { timerFn = f; return 1; },
  clearInterval() { timerFn = null; }, setTimeout: f => f(), weco: null, history: {}};
global.fetch = () => { const a = answers[fetched++]; return Promise.resolve({ok: true, json: () => Promise.resolve(a)}); };
require(process.argv[1]);
(async () => {
  for (let i = 0; i < answers.length; i++) {
    if (!timerFn) break;
    timerFn();
    await new Promise(r => setImmediate(r));
    await new Promise(r => setImmediate(r));
  }
  console.log(JSON.stringify({replaced, fetched}));
})();
'''


class WallScriptScenarioTests(SimpleTestCase):
    def run_scenario(self, answers, ok_only):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден – сценарий wall.js не запускался')
        result = subprocess.run(
            [node, '-e', SCENARIO, WALL_JS, json.dumps(answers), '1' if ok_only else '0'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_screen_03_stays_on_no_sub_and_leaves_on_ok(self):
        no_sub = {'step': 'contact', 'tg': 'no_sub'}
        out = self.run_scenario([no_sub, no_sub, no_sub], ok_only=True)
        self.assertEqual(out, {'replaced': [], 'fetched': 3})
        out = self.run_scenario([no_sub, no_sub, no_sub, {'step': 'contact', 'tg': 'ok'}], ok_only=True)
        self.assertEqual(out, {'replaced': ['/vp/x/?wall=1'], 'fetched': 4})

    def test_screen_02_leaves_on_no_sub(self):
        out = self.run_scenario([{'step': 'contact', 'tg': 'waiting'},
                                 {'step': 'contact', 'tg': 'no_sub'}], ok_only=False)
        self.assertEqual(out, {'replaced': ['/vp/x/?wall=1'], 'fetched': 2})
