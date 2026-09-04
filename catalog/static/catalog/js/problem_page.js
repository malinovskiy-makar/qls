/* Страница задачи: отправка решения на проверку ИИ и чат по задаче.
 *
 * Этап 5 редизайна каталога (решения владельца 04.09.2026). Разметку
 * результата рисует сервер (`_attempt_result.html`), скрипт только шлёт
 * запросы и подменяет блоки. Без ключа ИИ ни кнопки, ни карточки чата на
 * странице нет — тогда этот файл не находит своих узлов и молчит.
 *
 * ⚠️ Наружу уходит текст решения и вопрос — ничего из профиля.
 * ⚠️ История чата живёт только здесь, последние шесть реплик (ADR 0072).
 */
(function () {
  'use strict';
  var cfgEl = document.getElementById('pd-config');
  if (!cfgEl) { return; }
  var cfg = JSON.parse(cfgEl.textContent);
  var $ = function (id) { return document.getElementById(id); };
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
  var HISTORY_LIMIT = 6;

  function post(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json().then(function (d) { d._status = r.status; return d; }); });
  }

  /* ── Проверка решения ──────────────────────────────────────────────── */
  var submit = $('sv-submit'), field = $('sv-text'), busy = $('chk-busy'),
      holder = $('chk-holder'), remaining = $('sv-remaining'), note = $('sv-note');
  function setBusy(on) {
    if (busy) { busy.hidden = !on; }
    if (submit) { submit.disabled = on; submit.textContent = on ? 'Проверяю…' : (holder && holder.firstElementChild ? 'Отправить ещё раз' : submit.dataset.label); }
  }
  function say(text) { if (note) { note.textContent = text || ''; note.hidden = !text; } }
  if (submit && field && holder && cfg.attemptUrl) {
    submit.dataset.label = submit.textContent.trim();
    submit.addEventListener('click', function () {
      var text = field.value.trim();
      if (!text) { field.focus(); return; }
      say('');
      setBusy(true);
      post(cfg.attemptUrl, { problem_id: cfg.problemId, text: text,
                             solution_viewed_before: !!window.solutionViewedBefore })
        .then(function (d) {
          setBusy(false);
          if (d.error) { say(d.message || 'Проверка не удалась, попробуйте ещё раз.'); return; }
          holder.innerHTML = d.html;
          window.attemptSubmitted = true;
          if (remaining && d.remaining !== undefined) { remaining.textContent = d.remaining; }
          setBusy(false);
          var chk = $('chk');
          if (chk) { chk.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
        })
        .catch(function () { setBusy(false); say('Не удалось отправить решение, попробуйте ещё раз.'); });
    });
  }
  document.addEventListener('click', function (e) {
    var retry = e.target.closest('[data-retry]');
    if (retry && field) {
      /* Текст попытки остаётся в поле — человек правит, а не пишет заново. */
      field.focus();
      var sv = $('sv');
      if (sv) { sv.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
      return;
    }
    var ask = e.target.closest('[data-ask]');
    if (ask && chat) { chat.send(ask.dataset.ask); }
  });

  /* ── Подсказки уровнями: по одной, счётчик «сколько осталось» ─────── */
  function renderMath(el) {
    if (typeof maskEscapedDollars === 'function') { maskEscapedDollars(el); }
    if (typeof renderMathInElement !== 'undefined') {
      renderMathInElement(el, { delimiters: [
        { left: '$$', right: '$$', display: true }, { left: '$', right: '$', display: false },
        { left: '\\[', right: '\\]', display: true }, { left: '\\(', right: '\\)', display: false }
      ], throwOnError: false, trust: false });
    }
    if (typeof fixCurrencyDollars === 'function') { fixCurrencyDollars(el); }
  }
  var hintBtn = $('hint-btn'), hints = $('hints');
  if (hintBtn && hints && cfg.hintUrl && cfg.hintTotal) {
    var hintN = 0, hintBusy = false;
    hintBtn.addEventListener('click', function () {
      if (hintBusy || hintN >= cfg.hintTotal) { return; }
      hintBusy = true;
      fetch(cfg.hintUrl + (hintN + 1) + '/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { if (!r.ok) { throw new Error('HTTP ' + r.status); } return r.json(); })
        .then(function (d) {
          hintN = d.n;
          var card = document.createElement('div');
          card.className = 'hint';
          var k = document.createElement('span');
          k.className = 'k';
          k.textContent = 'Подсказка ' + d.n + (d.part ? ' · пункт ' + d.part + ')' : '');
          var body = document.createElement('div');
          var text = document.createElement('div');
          text.textContent = d.text;
          body.appendChild(text);
          if (d.ai && !d.reviewed) {
            var note = document.createElement('div');
            note.className = 'ai';
            note.textContent = 'сгенерировано ИИ, не проверено человеком';
            body.appendChild(note);
          }
          card.appendChild(k);
          card.appendChild(body);
          hints.appendChild(card);
          renderMath(text);
          if (hintN < d.total) {
            hintBtn.innerHTML = '';
            hintBtn.appendChild(document.createTextNode('💡 Ещё подсказка '));
            var n = document.createElement('span');
            n.className = 'n';
            n.id = 'hint-n';
            n.textContent = (hintN + 1) + ' из ' + d.total;
            hintBtn.appendChild(n);
          } else {
            hintBtn.hidden = true;
            var done = $('hint-done');
            if (done) { done.hidden = false; }
          }
        })
        .catch(function () { say('Не удалось получить подсказку, попробуйте ещё раз.'); })
        .then(function () { hintBusy = false; });
    });
  }

  /* ── Чат по задаче ─────────────────────────────────────────────────── */
  var chat = null;
  var aiIn = $('ai-in'), aiText = $('ai-text'), aiBody = $('ai-body'), aiSend = $('ai-send');
  if (aiIn && aiText && aiBody && aiSend && cfg.chatUrl) {
    var history = [];
    function bubble(cls, text) {
      var el = document.createElement('div');
      el.className = 'ai-msg ' + cls;
      el.textContent = text;
      aiBody.appendChild(el);
      aiBody.scrollTop = aiBody.scrollHeight;
      return el;
    }
    function typing() {
      var el = document.createElement('div');
      el.className = 'ai-msg ai-msg--ai';
      var dots = document.createElement('span');
      dots.className = 'typing';
      for (var i = 0; i < 3; i++) { dots.appendChild(document.createElement('i')); }
      el.appendChild(dots);
      aiBody.appendChild(el);
      aiBody.scrollTop = aiBody.scrollHeight;
      return el;
    }
    function syncAi() {
      aiIn.classList.toggle('has-text', aiText.value.trim().length > 0);
      aiText.style.height = 'auto';
      aiText.style.height = Math.min(120, aiText.scrollHeight) + 'px';
    }
    function send(text) {
      text = (text || aiText.value).trim();
      if (!text) { return; }
      var sug = $('ai-sug');
      if (sug) { sug.remove(); }
      bubble('ai-msg--me', text);
      aiText.value = '';
      syncAi();
      var wait = typing();
      post(cfg.chatUrl, { problem_id: cfg.problemId, message: text, history: history.slice(-HISTORY_LIMIT) })
        .then(function (d) {
          var reply = d.reply || d.message || 'Не получилось ответить, попробуйте ещё раз.';
          wait.textContent = reply;
          aiBody.scrollTop = aiBody.scrollHeight;
          history.push({ role: 'me', text: text }, { role: 'ai', text: reply });
          history = history.slice(-HISTORY_LIMIT);
          if (remaining && d.remaining !== undefined) { remaining.textContent = d.remaining; }
        })
        .catch(function () { wait.textContent = 'Не получилось ответить, попробуйте ещё раз.'; });
    }
    chat = { send: send };
    aiText.addEventListener('input', syncAi);
    aiText.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
    aiSend.addEventListener('click', function () { send(); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-q]'), function (b) {
      b.addEventListener('click', function () { aiText.value = b.dataset.q; syncAi(); aiText.focus(); });
    });
    syncAi();
  }
})();
