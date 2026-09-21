/* Экран результата ВП, владелец попытки: «Поделиться» и «Дорешать вне зачёта».
 *
 * ⚠️ «Дорешать» НИЧЕГО не сохраняет: ответ уходит в `practice_check`, а тот ни в базу, ни в
 * балл не пишет. Всё, что приходит с сервера, вставляется как ТЕКСТ (`textContent`), не как
 * разметка. Эталона на странице до проверки нет — его отдаёт только этот запрос.
 */
(function () {
  'use strict';

  var csrfField = document.querySelector('input[name=csrfmiddlewaretoken]');
  var csrf = csrfField ? csrfField.value : '';
  var urlNode = document.getElementById('vp-practice-url');
  var practiceUrl = urlNode ? JSON.parse(urlNode.textContent) : '';

  /* ── Поделиться: ссылка в буфер обмена, без внешних сервисов ───────────── */
  var share = document.getElementById('vp-share');
  var note = document.getElementById('vp-share-note');
  var noteText = note ? note.textContent : '';

  function copyFallback(text) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (error) { ok = false; }
    document.body.removeChild(area);
    return ok;
  }

  function shared(ok) {
    if (!note) return;
    note.textContent = ok ? 'Ссылка скопирована. Её откроет любой, но ваших ответов не увидит.'
                          : 'Не получилось скопировать. Скопируйте адрес страницы из строки браузера.';
    window.setTimeout(function () { note.textContent = noteText; }, 4000);
  }

  if (share) {
    share.addEventListener('click', function () {
      var link = window.location.origin + window.location.pathname;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(function () { shared(true); },
                                                  function () { shared(copyFallback(link)); });
      } else {
        shared(copyFallback(link));
      }
    });
  }

  /* ── Дорешать вне зачёта ───────────────────────────────────────────────── */
  function value(box, kind) {
    var form = box.querySelector('[data-practice-form]');
    if (kind === 'short_text') return form.elements.raw.value;
    var marked = Array.prototype.map.call(
      form.querySelectorAll('input[name=raw]:checked'), function (input) { return input.value; });
    return kind === 'multi' ? marked : (marked[0] || '');
  }

  function show(out, text, tone) {
    out.textContent = text;
    out.className = 'vp-practice-out' + (tone ? ' is-' + tone : '');
  }

  function check(box) {
    var kind = box.getAttribute('data-kind');
    var out = box.querySelector('[data-practice-out]');
    var raw = value(box, kind);
    if (!raw || !raw.length) { show(out, 'Сначала ответьте.', 'bad'); return; }
    show(out, 'Проверяем…', '');
    fetch(practiceUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      credentials: 'same-origin',
      body: JSON.stringify({ item: Number(box.getAttribute('data-item')), raw: raw })
    }).then(function (response) {
      return response.json().then(function (data) { return { ok: response.ok, data: data }; });
    }).then(function (reply) {
      if (!reply.ok) { show(out, reply.data.error || 'Не удалось проверить.', 'bad'); return; }
      if (reply.data.is_correct) show(out, 'Верно: ' + reply.data.right, 'ok');
      else show(out, 'Неверно. Верный ответ: ' + reply.data.right, 'bad');
    }).catch(function () {
      show(out, 'Нет связи. Попробуйте ещё раз.', 'bad');
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-practice]'), function (box) {
    var open = box.querySelector('[data-practice-open]');
    var form = box.querySelector('[data-practice-form]');
    open.addEventListener('click', function () {
      var hidden = form.hidden;
      form.hidden = !hidden;
      open.setAttribute('aria-expanded', hidden ? 'true' : 'false');
      if (hidden) {
        var first = form.querySelector('input');
        if (first) first.focus();
      }
    });
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      check(box);
    });
  });
})();
