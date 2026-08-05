/*
 * Форма работы ученика (домашка и контрольная) — защита от случайной сдачи.
 *
 * ⚠️ ЗАЧЕМ. Нажатие Shift+Return в поле решения ОТПРАВИЛО КОНТРОЛЬНУЮ. Без
 * подтверждения, без предупреждения, посреди работы. Причина не в нашем
 * коде, а в самом HTML: браузер делает «неявную отправку формы» по Enter в
 * текстовом поле — всегда, когда в форме одно текстовое поле, и почти
 * всегда, когда в ней есть кнопка отправки. Наша форма содержала и то и
 * другое.
 *
 * Правило простое: РАБОТУ ОТПРАВЛЯЕТ ТОЛЬКО КНОПКА. Return и Shift+Return
 * в текстовых полях — перенос строки, и ничего больше.
 *
 * Второе: перед сдачей спрашиваем подтверждение С ФАКТАМИ — сколько задач
 * без ответа и сколько осталось времени. «Вы уверены?» без цифр ученику
 * ничего не даёт: он не помнит, на скольких задачах не дописал.
 *
 * Наружу торчит window.WorkForm — им же пользуется exam.js, чтобы читать
 * ответы одной и той же меркой (иначе счётчик «без ответа» в диалоге и
 * автосохранение начнут расходиться).
 */
(function () {
  'use strict';

  function readCard(card) {
    if (!card) { return { answer: '', solution: '' }; }
    var answer = '';
    var checked = card.querySelectorAll(
      'input[type=radio]:checked, input[type=checkbox]:checked');
    if (checked.length) {
      answer = Array.prototype.map.call(checked, function (input) {
        return input.value;
      }).join(', ');
    } else {
      var short = card.querySelector('input.answer-short');
      answer = short ? short.value.trim() : '';
    }
    var area = card.querySelector('textarea.answer-text');
    return { answer: answer, solution: area ? area.value : '' };
  }

  function answered(card) {
    var payload = readCard(card);
    return Boolean((payload.answer || '').trim()
      || (payload.solution || '').trim());
  }

  /** Сколько задач осталось без ответа. Считаем ТОЛЬКО те карточки, где
   * есть поля ввода: уже сданная задача «без ответа» быть не может. */
  function countUnanswered(scope) {
    var count = 0;
    (scope || document).querySelectorAll('.problem-card').forEach(
      function (card) {
        if (!card.querySelector('.answer-area label')) { return; }
        if (!card.querySelector(
          'input.answer-short, textarea.answer-text, input[type=radio], '
          + 'input[type=checkbox]')) { return; }
        if (!answered(card)) { count += 1; }
      });
    return count;
  }

  function humanTime(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) {
      return '';
    }
    var minutes = Math.floor(seconds / 60);
    if (minutes >= 60) {
      return Math.floor(minutes / 60) + ' ч ' + (minutes % 60) + ' мин';
    }
    if (minutes >= 1) { return minutes + ' мин'; }
    return 'меньше минуты';
  }

  /** Подтверждение сдачи с фактами. true — ученик подтвердил. */
  function confirmSubmit(options) {
    options = options || {};
    var lines = [];
    var unanswered = options.unanswered;
    if (unanswered === undefined) { unanswered = countUnanswered(); }
    if (unanswered > 0) {
      lines.push('Без ответа осталось задач: ' + unanswered + '.');
    } else {
      lines.push('Ответы есть у всех задач.');
    }
    var left = humanTime(options.secondsLeft);
    if (left) { lines.push('До конца работы: ' + left + '.'); }
    lines.push(options.warning
      || 'После отправки дописать будет нельзя.');
    lines.push('');
    lines.push(options.question || 'Отправить работу?');
    return window.confirm(lines.join('\n'));
  }

  /** Запрещает неявную отправку формы по Enter.
   *
   * В textarea Enter и Shift+Enter оставляем как есть — это перенос
   * строки. В строке ввода и в переключателях Enter гасим: там браузер
   * трактует его как «отправить». */
  function guardEnter(form) {
    if (!form || form.dataset.enterGuarded === '1') { return; }
    form.dataset.enterGuarded = '1';
    form.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter') { return; }
      var target = event.target;
      var tag = (target.tagName || '').toLowerCase();
      if (tag === 'textarea') { return; }
      if (tag === 'button' || (tag === 'input' && target.type === 'submit')) {
        return;   // по кнопке отправлять можно — она для этого и есть
      }
      event.preventDefault();
    });
  }

  window.WorkForm = {
    readCard: readCard,
    answered: answered,
    countUnanswered: countUnanswered,
    confirmSubmit: confirmSubmit,
    guardEnter: guardEnter,
    humanTime: humanTime
  };

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('form[data-work-form]').forEach(function (form) {
      guardEnter(form);

      var button = form.querySelector('[data-work-submit]');
      if (!button) { return; }
      button.addEventListener('click', function (event) {
        if (form.dataset.confirmed === '1') { return; }
        event.preventDefault();
        if (!confirmSubmit({
          question: button.dataset.confirmQuestion || 'Отправить работу?',
          warning: button.dataset.confirmWarning
        })) { return; }
        form.dataset.confirmed = '1';
        form.submit();
      });
    });
  });
})();
