"""
Форма работы ученика: Enter не отправляет, сдача спрашивает подтверждение.

Этот класс дефектов питон-тесты не видят в принципе — они не нажимают
клавиш. Shift+Return однажды сдал контрольную посреди работы, и ни один из
сорока тестов контрольных этого не заметил: сервер получил корректный POST
и корректно его принял. Ошибка была в том, что POST вообще случился.

Здесь проверяем две вещи:
1. Логику `work_form.js` — исполнением в node с подставным событием;
2. Разметку — что защита ПОДКЛЮЧЕНА на обеих страницах (домашка и
   контрольная). Работающая функция, которую забыли позвать, — ровно то,
   как дефект и вернётся.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from django.conf import settings
from django.test import TestCase

WORK_FORM_JS = os.path.join(settings.BASE_DIR, 'problems', 'static',
                            'platform', 'work_form.js')
EXAM_JS = os.path.join(settings.BASE_DIR, 'problems', 'static', 'platform',
                       'exam.js')
HOMEWORK_TPL = os.path.join(settings.BASE_DIR, 'student', 'templates',
                            'student', 'assignment_detail.html')
EXAM_TPL = os.path.join(settings.BASE_DIR, 'student', 'templates', 'student',
                        'exam_take.html')


def run_node(script):
    """Гоняет `work_form.js` в node с минимальными заглушками DOM."""
    with open(WORK_FORM_JS, encoding='utf-8') as f:
        source = f.read()
    stub = """
    // Заглушки ровно того, чем пользуется work_form.js.
    var listeners = {};
    globalThis.document = {
      addEventListener: function (name, fn) { listeners[name] = fn; },
      querySelectorAll: function () { return []; }
    };
    globalThis.window = globalThis;
    globalThis.confirm = function (message) {
      globalThis.__lastConfirm = message;
      return globalThis.__confirmAnswer !== false;
    };
    """
    body = stub + source + '\n' + script
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
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
class WorkFormJsTests(TestCase):

    def test_enter_in_a_text_input_is_blocked(self):
        """ГЛАВНЫЙ ТЕСТ ФАЗЫ 0.6.

        Enter в строке ввода — не «отправить работу». Именно неявная
        отправка формы браузером и сдала контрольную по Shift+Return.
        """
        result = run_node("""
          var handler = null;
          var form = {
            dataset: {},
            addEventListener: function (name, fn) { handler = fn; }
          };
          globalThis.WorkForm.guardEnter(form);

          function press(tag, type, shift) {
            var prevented = false;
            handler({
              key: 'Enter', shiftKey: Boolean(shift),
              target: { tagName: tag, type: type },
              preventDefault: function () { prevented = true; }
            });
            return prevented;
          }

          console.log(JSON.stringify({
            input: press('INPUT', 'text'),
            inputShift: press('INPUT', 'text', true),
            radio: press('INPUT', 'radio'),
            textarea: press('TEXTAREA'),
            textareaShift: press('TEXTAREA', undefined, true),
            submitButton: press('BUTTON')
          }));
        """)
        self.assertTrue(result['input'], 'Enter в строке ввода не заблокирован')
        self.assertTrue(result['inputShift'], 'Shift+Enter не заблокирован')
        self.assertTrue(result['radio'])
        # В поле решения Enter обязан оставаться переносом строки.
        self.assertFalse(result['textarea'])
        self.assertFalse(result['textareaShift'])
        # По кнопке отправлять можно — она для этого и есть.
        self.assertFalse(result['submitButton'])

    def test_confirmation_carries_facts(self):
        """Подтверждение содержит цифры, а не «Вы уверены?»."""
        result = run_node("""
          globalThis.__confirmAnswer = true;
          var ok = globalThis.WorkForm.confirmSubmit({
            unanswered: 3, secondsLeft: 605, question: 'Завершить контрольную?'
          });
          var clean = globalThis.WorkForm.confirmSubmit({
            unanswered: 0, secondsLeft: null
          });
          console.log(JSON.stringify({
            ok: ok, message: globalThis.__lastConfirm, clean: clean
          }));
        """)
        self.assertTrue(result['ok'])

        result2 = run_node("""
          globalThis.__confirmAnswer = true;
          globalThis.WorkForm.confirmSubmit({unanswered: 3, secondsLeft: 605});
          console.log(JSON.stringify({message: globalThis.__lastConfirm}));
        """)
        message = result2['message']
        self.assertIn('Без ответа осталось задач: 3', message)
        self.assertIn('10 мин', message)
        self.assertIn('дописать будет нельзя', message)

    def test_cancel_means_cancel(self):
        result = run_node("""
          globalThis.__confirmAnswer = false;
          console.log(JSON.stringify({
            answer: globalThis.WorkForm.confirmSubmit({unanswered: 1})
          }));
        """)
        self.assertFalse(result['answer'])


class WorkFormWiringTests(TestCase):
    """Защита ПОДКЛЮЧЕНА на обеих страницах.

    Рабочая функция, которую забыли позвать, — ровно то, как дефект
    возвращается после рефакторинга.
    """

    def _read(self, path):
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_homework_form_is_guarded(self):
        source = self._read(HOMEWORK_TPL)
        self.assertIn('data-work-form', source)
        self.assertIn('data-work-submit', source)

    def test_exam_page_loads_the_guard_and_calls_it(self):
        self.assertIn('work_form.js', self._read(EXAM_TPL))
        exam_js = self._read(EXAM_JS)
        self.assertIn('WorkForm.guardEnter', exam_js)
        self.assertIn('WorkForm.confirmSubmit', exam_js)

    def test_exam_finish_button_is_not_a_submit(self):
        """Кнопка «Завершить» — `type="button"`.

        Кнопка отправки внутри формы включает неявную отправку по Enter
        обратно, даже с перехватчиком: браузеры разные.
        """
        source = self._read(EXAM_TPL)
        self.assertIn('type="button" class="btn-submit" id="finish-btn"',
                      source)
