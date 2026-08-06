"""
Автосохранение контрольной ПОСЛЕ СДАЧИ — проверка исполнением, не чтением.

Что нашла ручная проверка (лог сервера): в 04:17:05 контрольная сдана, в
04:17:41 прилетел ещё один автосейв и получил 409. Сервер отработал верно,
но клиент обязан прекратить попытки сразу после сдачи, а не стучаться в
закрытую дверь ещё полминуты.

Питон-тесты этого класса не видят вовсе: дефект живёт в JavaScript, а
`TestCase` его не исполняет. Здесь `exam.js` запускается в node с
подставными DOM, fetch и таймерами — и мы жмём «Завершить» так же, как
ученик, после чего дёргаем ВСЕ пять источников автосохранения.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import TestCase

PLATFORM = os.path.join(settings.BASE_DIR, 'problems', 'static', 'platform')
EXAM_JS = os.path.join(PLATFORM, 'exam.js')
TIMER_JS = os.path.join(PLATFORM, 'exam_timer.js')
FORM_JS = os.path.join(PLATFORM, 'work_form.js')

# Подставной браузер: ровно столько, сколько трогает exam.js.
HARNESS = r"""
var log = { fetches: [], submitted: 0 };
var listeners = {};
var intervalFns = [];

function makeNode(id) {
  return {
    id: id, dataset: {}, classList: { toggle: function () {},
                                      add: function () {},
                                      remove: function () {} },
    textContent: '', className: '', value: '', style: {},
    addEventListener: function (name, fn) {
      (listeners[id + ':' + name] = listeners[id + ':' + name] || []).push(fn);
    },
    // Карточка задачи с одним коротким полем ответа — минимум, на котором
    // автосохранение вообще уезжает.
    querySelectorAll: function (selector) {
      var list = (selector.indexOf('answer-short') >= 0)
        ? [{ value: 'ответ', dataset: {}, trim: null }] : [];
      list.forEach = Array.prototype.forEach;
      return list;
    },
    querySelector: function () { return null; },
    submit: function () { log.submitted += 1; }
  };
}

var nodes = {};
['save-state', 'timer', 'exam-form', 'finish-btn', 'answered-count',
 'item-1'].forEach(function (id) { nodes[id] = makeNode(id); });
nodes['timer'].dataset.seconds = '600';

globalThis.document = {
  cookie: 'csrftoken=x',
  getElementById: function (id) { return nodes[id] || null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function (name, fn) {
    (listeners['doc:' + name] = listeners['doc:' + name] || []).push(fn);
  }
};
globalThis.window = globalThis;
globalThis.addEventListener = function (name, fn) {
  (listeners['win:' + name] = listeners['win:' + name] || []).push(fn);
};
globalThis.confirm = function () { return true; };
globalThis.EXAM = { autosaveUrl: '/save/', timeUrl: '/time/', itemIds: [1] };
globalThis.performance = { now: function () { return 0; } };

globalThis.fetch = function (url, options) {
  log.fetches.push(url);
  return Promise.resolve({
    ok: true, status: 200,
    json: function () { return Promise.resolve({ seconds_remaining: 600 }); }
  });
};
globalThis.setInterval = function (fn) {
  intervalFns.push(fn);
  return intervalFns.length;
};
globalThis.clearInterval = function (id) { intervalFns[id - 1] = null; };
globalThis.setTimeout = function (fn) { return 0; };
globalThis.clearTimeout = function () {};

function fire(key) {
  (listeners[key] || []).forEach(function (fn) { fn({ preventDefault: function () {} }); });
}
"""

DRIVE = r"""
fire('doc:DOMContentLoaded');
// Ученик пишет ответ — автосохранение работает.
fire('item-1:change');
var before = log.fetches.length;

// Нажал «Завершить».
fire('finish-btn:click');

// Дальше дёргаем ВСЕ источники автосохранения, какие есть на странице:
// ввод, смена варианта, потеря фокуса, повтор по таймеру, возврат связи.
fire('item-1:input');
fire('item-1:change');
fire('item-1:focusout');
intervalFns.forEach(function (fn) { if (fn) { fn(); } });
fire('win:online');

// Даём осесть всем промисам fetch (их несколько уровней .then), потом
// печатаем итог.
var settle = Promise.resolve();
for (var i = 0; i < 20; i += 1) { settle = settle.then(function () {}); }
settle.then(function () {
  console.log(JSON.stringify({
    beforeFinish: before,
    afterFinish: log.fetches.length,
    submitted: log.submitted,
    liveIntervals: intervalFns.filter(Boolean).length
  }));
});
"""


def code_only(path):
    """Текст файла без комментариев."""
    with open(path, encoding='utf-8') as f:
        source = f.read()
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return '\n'.join(line for line in source.splitlines()
                     if not line.strip().startswith('//'))


def run_exam_js(script):
    parts = [HARNESS]
    for path in (TIMER_JS, FORM_JS, EXAM_JS):
        with open(path, encoding='utf-8') as f:
            parts.append(f.read())
    parts.append(script)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as f:
        f.write('\n'.join(parts))
        path = f.name
    try:
        proc = subprocess.run(['node', path], capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        return json.loads(proc.stdout)
    finally:
        os.unlink(path)


@unittest.skipIf(shutil.which('node') is None, 'node не установлен')
class AutosaveStopsAfterSubmitTests(TestCase):

    def test_no_autosave_after_finish(self):
        """ГЛАВНЫЙ ТЕСТ ФАЗЫ: после «Завершить» — ни одного запроса."""
        result = run_exam_js(DRIVE)
        self.assertGreater(result['beforeFinish'], 0,
                           'до сдачи автосохранение вообще не работало — '
                           'тест проверяет не то, что нужно')
        self.assertEqual(result['afterFinish'], result['beforeFinish'],
                         'автосохранение продолжает стучаться после сдачи')

    def test_form_is_submitted_exactly_once(self):
        result = run_exam_js(DRIVE)
        self.assertEqual(result['submitted'], 1)

    def test_intervals_are_cleared(self):
        """Повторы и опрос времени гасятся, а не «просто ничего не делают»:
        вернувшийся из bfcache таймер иначе воскреснет вместе со страницей."""
        result = run_exam_js(DRIVE)
        self.assertEqual(result['liveIntervals'], 0)

    def test_every_entry_point_checks_the_flag(self):
        """Флаг проверяется в самой очереди, а не только в кнопке.

        Источников сохранения пять; закрыть один и забыть остальные — ровно
        та ошибка, из-за которой запросы и шли после сдачи.
        """
        source = code_only(EXAM_JS)
        for entry in ('function enqueue', 'function pump', 'function send',
                      'function retryPending', 'function schedule'):
            start = source.index(entry)
            head = source[start:start + 220]
            self.assertIn('stopped', head,
                          '%s не проверяет флаг остановки' % entry)
