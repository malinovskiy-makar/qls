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

  /* ── Фото или файл: грузится сразу, к попытке привязывается при отправке ── */
  var pendingFiles = [];
  var attInput = $('att-input'), attAdd = $('att-add'), attBox = $('sv-attach');
  function renderFiles() {
    if (!attBox) { return; }
    Array.prototype.forEach.call(attBox.querySelectorAll('.att'), function (el) { el.remove(); });
    pendingFiles.forEach(function (f) {
      var chip = document.createElement('span');
      chip.className = 'att';
      var thumb = document.createElement('span');
      thumb.className = 'thumb';
      thumb.textContent = f.kind === 'application/pdf' ? 'PDF' : 'IMG';
      chip.appendChild(thumb);
      chip.appendChild(document.createTextNode(f.name));
      var x = document.createElement('button');
      x.type = 'button';
      x.className = 'x';
      x.setAttribute('aria-label', 'Убрать файл');
      x.textContent = '×';
      x.addEventListener('click', function () {
        pendingFiles = pendingFiles.filter(function (g) { return g.id !== f.id; });
        renderFiles();
      });
      chip.appendChild(x);
      attBox.insertBefore(chip, attAdd);
    });
    if (attAdd) { attAdd.disabled = pendingFiles.length >= (cfg.maxFiles || 3); }
  }
  if (attInput && attAdd && cfg.fileUrl) {
    attAdd.addEventListener('click', function () { attInput.click(); });
    attInput.addEventListener('change', function () {
      var file = attInput.files && attInput.files[0];
      attInput.value = '';
      if (!file) { return; }
      var form = new FormData();
      form.append('file', file);
      form.append('pending', pendingFiles.map(function (f) { return f.id; }).join(','));
      attAdd.disabled = true;
      fetch(cfg.fileUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, body: form })
        .then(function (r) { return r.json().then(function (d) { d._status = r.status; return d; }); })
        .then(function (d) {
          if (d.error) { say(d.message || 'Файл не принят.'); return; }
          say('');
          pendingFiles.push({ id: d.id, name: d.name, kind: d.kind });
        })
        .catch(function () { say('Не удалось загрузить файл, попробуйте ещё раз.'); })
        .then(renderFiles);
    });
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
      if (!text && !pendingFiles.length) { field.focus(); return; }
      say('');
      setBusy(true);
      post(cfg.attemptUrl, { problem_id: cfg.problemId, text: text,
                             file_ids: pendingFiles.map(function (f) { return f.id; }),
                             solution_viewed_before: !!window.solutionViewedBefore })
        .then(function (d) {
          setBusy(false);
          if (d.error) { say(d.message || 'Проверка не удалась, попробуйте ещё раз.'); return; }
          holder.innerHTML = d.html;
          window.attemptSubmitted = true;
          pendingFiles = [];
          renderFiles();
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

  /* ── Тест как игра (этап 7): выбор, проверка всё-или-ничего, разбор ── */
  var tq = $('tq'), tcfg = cfg.test;
  if (tq && tcfg && tcfg.checkUrl) {
    var opts = Array.prototype.slice.call(tq.querySelectorAll('.opt'));
    var sel = [], mode = 'play', attempt = 1, correct = null, count = null, tqBusy = false;
    var msgWrong = $('msg-wrong'), msgOk = $('msg-ok'), msgShow = $('msg-show'), cnt = $('msg-cnt');
    var rowPlay = $('row-play'), rowDone = $('row-done'), expl = $('expl'), tryEl = $('tq-try');
    var checkBtn = $('check-btn'), why = $('check-why'), revealBtn = $('reveal-btn');
    var againBtn = $('again-btn'), askWhy = $('ask-why'), okSub = $('ok-sub'), showLabels = $('show-labels');
    var whyText = why ? why.textContent : '';
    function plural(n, forms) {
      var a = n % 10, b = n % 100;
      return forms[(a === 1 && b !== 11) ? 0 : (a >= 2 && a <= 4 && (b < 10 || b >= 20)) ? 1 : 2];
    }
    function nth(n) { return (n === 2 ? 'со ' : 'с ') + n + '-й попытки'; }
    function isDone() { return mode === 'solved' || mode === 'revealed'; }
    function renderTest() {
      var done = isDone();
      opts.forEach(function (o) {
        var l = o.getAttribute('data-l'), on = sel.indexOf(l) >= 0;
        o.setAttribute('aria-pressed', on ? 'true' : 'false');
        o.classList.remove('is-hit', 'is-wrong', 'is-missed', 'is-skip');
        o.disabled = done;
        var note = o.querySelector('.opt-note');
        if (note) { note.textContent = ''; }
        if (done && correct) {
          var right = correct.indexOf(l) >= 0;
          if (on && right) { o.classList.add('is-hit'); note.textContent = 'вы выбрали · верно'; }
          else if (on) { o.classList.add('is-wrong'); note.textContent = 'вы выбрали · неверно'; }
          else if (right) { o.classList.add('is-missed'); note.textContent = 'надо было выбрать'; }
          else { o.classList.add('is-skip'); }
        }
      });
      msgWrong.classList.toggle('is-on', mode === 'wrong');
      msgOk.classList.toggle('is-on', mode === 'solved');
      msgShow.classList.toggle('is-on', mode === 'revealed');
      rowPlay.hidden = done;
      rowDone.hidden = !done;
      if (expl) { expl.classList.toggle('is-on', done); }
      checkBtn.disabled = !sel.length || tqBusy;
      why.hidden = !!sel.length;
      if (mode === 'solved') {
        tryEl.textContent = 'Решено ' + nth(attempt);
      } else if (mode === 'revealed') {
        var made = attempt - 1;
        tryEl.textContent = made ? 'Ответ показан после ' + made + ' ' + plural(made, ['попытки', 'попыток', 'попыток']) : 'Ответ показан';
      } else {
        tryEl.textContent = 'Попытка ' + attempt;
      }
      cnt.hidden = !(mode === 'wrong' && count !== null);
      if (!cnt.hidden) { cnt.textContent = 'верных вариантов: ' + count; }
      if (askWhy) { askWhy.setAttribute('data-ask', correct ? 'Объясни, почему в этом тесте верно именно: ' + correct.join(', ') : ''); }
    }
    function toggleOpt(l) {
      if (isDone() || tqBusy) { return; }
      var i = sel.indexOf(l);
      if (!tcfg.multi) { sel = i >= 0 ? [] : [l]; }
      else if (i >= 0) { sel.splice(i, 1); }
      else { sel.push(l); }
      if (mode === 'wrong') { mode = 'play'; }
      why.textContent = whyText;
      renderTest();
    }
    function shake() {
      tq.classList.remove('is-shake');
      void tq.offsetWidth;
      tq.classList.add('is-shake');
    }
    function checkTest() {
      if (!sel.length || isDone() || tqBusy) { return; }
      tqBusy = true;
      renderTest();
      post(tcfg.checkUrl, { labels: sel.slice() })
        .then(function (d) {
          if (d.error) { why.textContent = d.message || 'Не удалось проверить, попробуйте ещё раз.'; why.hidden = false; return; }
          attempt = d.attempt;
          if (d.correct) {
            mode = 'solved';
            correct = sel.slice();
            okSub.textContent = attempt === 1 ? 'С первой попытки.' : nth(attempt).charAt(0).toUpperCase() + nth(attempt).slice(1) + ', и это тоже считается.';
          } else {
            mode = 'wrong';
            attempt = d.attempt + 1;
            count = (d.correct_count === undefined || d.correct_count === null) ? null : d.correct_count;
            shake();
          }
        })
        .catch(function () { why.textContent = 'Не удалось проверить, попробуйте ещё раз.'; why.hidden = false; })
        .then(function () { tqBusy = false; renderTest(); });
    }
    function revealTest() {
      if (isDone() || tqBusy) { return; }
      tqBusy = true;
      post(tcfg.revealUrl, {})
        .then(function (d) {
          if (!d.correct_labels) { return; }
          correct = d.correct_labels.slice();
          mode = 'revealed';
          showLabels.textContent = correct.join(', ');
        })
        .catch(function () {})
        .then(function () { tqBusy = false; renderTest(); });
    }
    function againTest() {
      sel = []; attempt = 1; mode = 'play'; correct = null; count = null;
      why.textContent = whyText;
      renderTest();
    }
    opts.forEach(function (o) { o.addEventListener('click', function () { toggleOpt(o.getAttribute('data-l')); }); });
    checkBtn.addEventListener('click', checkTest);
    revealBtn.addEventListener('click', revealTest);
    againBtn.addEventListener('click', againTest);
    /* Клавиатура: 1–9 и буквы меток выбирают, Enter проверяет; в полях ввода молчим. */
    document.addEventListener('keydown', function (e) {
      var t = e.target;
      if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.isContentEditable)) { return; }
      if (e.altKey || e.ctrlKey || e.metaKey) { return; }
      var key = (e.key || '').toLowerCase();
      var idx = /^[1-9]$/.test(key) ? parseInt(key, 10) - 1 : tcfg.labels.indexOf(key);
      if (idx >= 0 && idx < opts.length) { toggleOpt(opts[idx].getAttribute('data-l')); e.preventDefault(); return; }
      if (e.key === 'Enter' && !rowPlay.hidden) { checkTest(); e.preventDefault(); }
    });
    renderTest();
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
