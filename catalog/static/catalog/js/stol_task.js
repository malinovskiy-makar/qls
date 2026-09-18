/* «Стол»: всё, что живёт внутри открытой задачи (README §3–§5).
 *
 * Сохранить, скопировать ссылку, решение с подтверждением, подсказки
 * уровнями, отправка решения на проверку ИИ с файлами, тест как игра,
 * чат по задаче с режимами, файлами и историей, «Как прошло?», нижняя
 * панель телефона.
 *
 * ⚠️ `weco.stolTask.init(root)` ЗОВЁТСЯ ЗАНОВО ПОСЛЕ КАЖДОЙ ПОДМЕНЫ ЗАДАЧИ
 * (ответ `?pane=1`, `stol.js`). Поэтому слушатели вешаются только на узлы
 * внутри `root` — они уходят вместе с подменённой разметкой, — а общие для
 * документа (клавиши теста, делегирование кликов) зарегистрированы один раз
 * и обращаются к текущей задаче через `cur`. Второй вызов `init` на тех же
 * узлах ничего не удваивает: узел помечается `data-bound`.
 *
 * Настройки задачи — JSON в `.stol-cfg` центра. Разметку результата
 * проверки рисует сервер (`_attempt_result.html`), подсказки и реплики
 * кладутся узлами через textContent — сырые данные в innerHTML не идут.
 * ⚠️ Наружу уходит текст решения и вопрос — ничего из профиля.
 * ⚠️ В модель уходят последние шесть реплик (ADR 0080); при открытии задачи
 *    разговор поднимается из журнала `ChatTurn`.
 */
(function () {
  'use strict';
  window.weco = window.weco || {};
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
  var HISTORY_LIMIT = 6;
  var FILES_PER_TURN = 3;
  var cur = null;          /* текущая задача: { cfg, root, test, chat, ... } */

  function post(url, payload) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json().then(function (d) { d._status = r.status; return d; }); });
  }
  function math(el) { if (el && typeof window.renderMathIn === 'function') window.renderMathIn(el); }
  function once(el) {
    if (!el || el.hasAttribute('data-bound')) return false;
    el.setAttribute('data-bound', '');
    return true;
  }
  function plural(n, forms) {
    var a = n % 10, b = n % 100;
    return forms[(a === 1 && b !== 11) ? 0 : (a >= 2 && a <= 4 && (b < 10 || b >= 20)) ? 1 : 2];
  }

  /* ── Сохранить и скопировать ссылку ─────────────────────────────────── */
  function bindBar(t) {
    var save = t.$('save-btn');
    if (once(save)) {
      save.addEventListener('click', function () {
        save.disabled = true;
        post(save.dataset.url, { catalog_problem_id: save.dataset.problem })
          .then(function (d) {
            save.classList.toggle('is-on', !!d.saved);
            save.setAttribute('aria-pressed', d.saved ? 'true' : 'false');
            save.setAttribute('aria-label', d.saved ? 'Сохранено' : 'Сохранить');
            save.title = d.saved ? 'Сохранено' : 'Сохранить';
          })
          .catch(function () { save.title = 'Не получилось'; })
          .then(function () { save.disabled = false; });
      });
    }
    var copy = t.$('copy-btn');
    if (once(copy)) {
      copy.addEventListener('click', function () {
        var done = function () {
          copy.classList.add('tb-btn--copied');
          copy.title = 'Ссылка скопирована';
          setTimeout(function () { copy.classList.remove('tb-btn--copied'); copy.title = 'Скопировать ссылку'; }, 1600);
        };
        if (window.weco.track) weco.track('copy_link', { from: 'problem' });
        if (navigator.clipboard) { navigator.clipboard.writeText(location.href).then(done, done); } else { done(); }
      });
    }
  }

  /* ── «Как прошло?» и следы помощи в прогрессе (ADR 0119) ──────────────── */
  function progress(t, payload) {
    if (!t.cfg.progressUrl) return Promise.resolve(null);
    return post(t.cfg.progressUrl, payload);
  }
  function bindHow(t) {
    var how = t.$('how');
    if (!once(how)) return;
    var next = t.$('how-next');
    how.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-how]');
      if (!btn || btn.disabled) return;
      var again = btn.getAttribute('aria-pressed') === 'true';
      progress(t, { status: again ? null : btn.getAttribute('data-how') }).then(function (d) {
        if (!d || d.error) return;
        how.querySelectorAll('[data-how]').forEach(function (b) {
          b.setAttribute('aria-pressed', !again && b === btn ? 'true' : 'false');
        });
        /* После отметки справа «Дальше ›» (README §3) — если есть куда. */
        if (next) next.hidden = again || !next.getAttribute('href');
        document.dispatchEvent(new CustomEvent('weco:progress', { detail: d }));
      });
    });
  }
  function solutionViewed(t) {
    t.solutionViewedBefore = !t.submitted;
    progress(t, { solution_viewed: true });
    var self = t.$('how') && t.$('how').querySelector('[data-how="self"]');
    if (self) { self.disabled = true; self.title = 'Решение уже открыто'; }
  }

  /* ── Решение: мягкое подтверждение, потом раскрытие ────────────────────── */
  function bindSolution(t) {
    var btn = t.$('sol-btn'), sol = t.$('sol'), box = t.$('sol-confirm');
    if (!once(btn) || !sol) return;
    function reveal() {
      sol.classList.add('is-on');
      btn.disabled = true;
      btn.textContent = 'Решение открыто';
      if (box) box.classList.remove('is-on');
      solutionViewed(t);
      math(sol);
    }
    t.revealSolution = reveal;
    btn.addEventListener('click', function () {
      if (t.submitted || !box) { reveal(); } else { box.classList.add('is-on'); }
    });
    if (t.$('sol-yes')) t.$('sol-yes').addEventListener('click', reveal);
    if (t.$('sol-no')) t.$('sol-no').addEventListener('click', function () { box.classList.remove('is-on'); });
  }

  /* ── Подсказки уровнями: по одной, счётчик «сколько осталось» ─────────── */
  function bindHints(t) {
    var btn = t.$('hint-btn'), list = t.$('hints');
    if (!once(btn) || !list || !t.cfg.hintUrl || !t.cfg.hintTotal) return;
    var n = 0, busy = false;
    function ask() {
      if (busy || n >= t.cfg.hintTotal) return;
      busy = true;
      fetch(t.cfg.hintUrl + (n + 1) + '/', { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (d) {
          n = d.n;
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
          list.appendChild(card);
          math(text);
          var left = d.total - n;
          var badge = document.getElementById('strip-hints');
          if (badge) { badge.textContent = String(left); badge.hidden = !left; }
          if (n < d.total) {
            var num = btn.querySelector('.n');
            if (num) num.textContent = (n + 1) + ' из ' + d.total;
          } else {
            btn.hidden = true;
            if (t.$('hint-done')) t.$('hint-done').hidden = false;
          }
          document.dispatchEvent(new CustomEvent('weco:hint', { detail: { n: n, total: d.total } }));
        })
        .catch(function () { t.say('Не удалось получить подсказку, попробуйте ещё раз.'); })
        .then(function () { busy = false; });
    }
    t.askHint = ask;
    btn.addEventListener('click', ask);
  }

  /* ── Фото или файл к попытке и отправка решения на проверку ─────────── */
  function bindAttempt(t) {
    var pending = [];
    var input = t.$('att-input'), add = t.$('att-add'), box = t.$('sv-attach');
    var submit = t.$('sv-submit'), field = t.$('sv-text'), busyEl = t.$('chk-busy'),
        holder = t.$('chk-holder'), note = t.$('sv-note');
    t.say = function (text) { if (note) { note.textContent = text || ''; note.hidden = !text; } };
    function renderFiles() {
      if (!box) return;
      box.querySelectorAll('.att').forEach(function (el) { el.remove(); });
      pending.forEach(function (f) {
        var chip = document.createElement('span');
        chip.className = 'att';
        var thumb = document.createElement('span');
        thumb.className = 'thumb';
        thumb.textContent = f.kind === 'application/pdf' ? 'PDF' : 'IMG';
        chip.appendChild(thumb);
        chip.appendChild(document.createTextNode(f.name));
        var x = document.createElement('button');
        x.type = 'button'; x.className = 'x'; x.setAttribute('aria-label', 'Убрать файл'); x.textContent = '×';
        x.addEventListener('click', function () {
          pending = pending.filter(function (g) { return g.id !== f.id; });
          renderFiles();
        });
        chip.appendChild(x);
        box.insertBefore(chip, add);
      });
      if (add) add.disabled = pending.length >= (t.cfg.maxFiles || 3);
    }
    if (once(add) && input && t.cfg.fileUrl) {
      add.addEventListener('click', function () { input.click(); });
      input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        input.value = '';
        if (!file) return;
        var form = new FormData();
        form.append('file', file);
        form.append('pending', pending.map(function (f) { return f.id; }).join(','));
        add.disabled = true;
        fetch(t.cfg.fileUrl, { method: 'POST', credentials: 'same-origin',
                               headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, body: form })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.error) { t.say(d.message || 'Файл не принят.'); return; }
            t.say('');
            pending.push({ id: d.id, name: d.name, kind: d.kind });
          })
          .catch(function () { t.say('Не удалось загрузить файл, попробуйте ещё раз.'); })
          .then(renderFiles);
      });
    }
    if (!once(submit) || !field || !holder || !t.cfg.attemptUrl) return;
    var label = submit.textContent.trim();
    function setBusy(on) {
      if (busyEl) busyEl.hidden = !on;
      submit.disabled = on;
      submit.lastChild.textContent = on ? 'Проверяю…' : (holder.firstElementChild ? 'Отправить ещё раз' : label);
    }
    submit.addEventListener('click', function () {
      var text = field.value.trim();
      if (!text && !pending.length) { field.focus(); return; }
      t.say('');
      setBusy(true);
      post(t.cfg.attemptUrl, { problem_id: t.cfg.problemId, text: text,
                               file_ids: pending.map(function (f) { return f.id; }),
                               solution_viewed_before: !!t.solutionViewedBefore })
        .then(function (d) {
          setBusy(false);
          if (d.error) { t.say(d.message || 'Проверка не удалась, попробуйте ещё раз.'); return; }
          /* Разметку результата рисует сервер тем же партиалом, что при открытии. */
          holder.innerHTML = d.html;
          t.submitted = true;
          pending = [];
          renderFiles();
          var rest = t.$('sv-remaining');
          if (rest && d.remaining !== undefined) rest.textContent = d.remaining;
          setBusy(false);
          math(holder);
          var chk = t.$('chk');
          if (chk) chk.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        })
        .catch(function () { setBusy(false); t.say('Не удалось отправить решение, попробуйте ещё раз.'); });
    });
    t.retry = function () {
      field.focus();
      var sv = t.$('sv');
      if (sv) sv.scrollIntoView({ block: 'start', behavior: 'smooth' });
    };
  }

  /* ── Тест как игра (этап 7, README §5): выбор, всё-или-ничего, разбор ─── */
  function bindTest(t) {
    var tq = t.$('tq'), tcfg = t.cfg.test;
    if (!once(tq) || !tcfg || !tcfg.checkUrl) return;
    var opts = Array.prototype.slice.call(tq.querySelectorAll('.opt'));
    var sel = [], mode = 'play', attempt = 1, correct = null, count = null, busy = false;
    var msgWrong = t.$('msg-wrong'), msgOk = t.$('msg-ok'), msgShow = t.$('msg-show'), cnt = t.$('msg-cnt');
    var rowPlay = t.$('row-play'), rowDone = t.$('row-done'), expl = t.$('expl'), tryEl = t.$('tq-try');
    var checkBtn = t.$('check-btn'), why = t.$('check-why'), revealBtn = t.$('reveal-btn');
    var againBtn = t.$('again-btn'), askWhy = t.$('ask-why'), okSub = t.$('ok-sub'), showLabels = t.$('show-labels');
    var whyText = why ? why.textContent : '';
    function nth(n) { return (n === 2 ? 'со ' : 'с ') + n + '-й попытки'; }
    function isDone() { return mode === 'solved' || mode === 'revealed'; }
    function render() {
      var done = isDone();
      opts.forEach(function (o) {
        var l = o.getAttribute('data-l'), on = sel.indexOf(l) >= 0;
        o.setAttribute('aria-pressed', on ? 'true' : 'false');
        o.classList.remove('is-hit', 'is-wrong', 'is-missed', 'is-skip');
        o.disabled = done;
        var note = o.querySelector('.opt-note');
        if (note) note.textContent = '';
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
      if (expl) expl.classList.toggle('is-on', done);
      if (done && expl) math(expl);
      checkBtn.disabled = !sel.length || busy;
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
      if (!cnt.hidden) cnt.textContent = 'верных вариантов: ' + count;
      if (askWhy) askWhy.setAttribute('data-ask', correct ? 'Объясни, почему в этом тесте верно именно: ' + correct.join(', ') : '');
    }
    function toggle(l) {
      if (isDone() || busy) return;
      var i = sel.indexOf(l);
      if (!tcfg.multi) { sel = i >= 0 ? [] : [l]; }
      else if (i >= 0) { sel.splice(i, 1); }
      else { sel.push(l); }
      if (mode === 'wrong') mode = 'play';
      why.textContent = whyText;
      render();
    }
    function shake() { tq.classList.remove('is-shake'); void tq.offsetWidth; tq.classList.add('is-shake'); }
    function check() {
      if (!sel.length || isDone() || busy) return;
      busy = true;
      render();
      post(tcfg.checkUrl, { labels: sel.slice() })
        .then(function (d) {
          if (d.error) { why.textContent = d.message || 'Не удалось проверить, попробуйте ещё раз.'; why.hidden = false; return; }
          attempt = d.attempt;
          if (window.weco.track) weco.track('test_answer', { problem_id: t.cfg.problemId, correct: !!d.correct, attempt: d.attempt });
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
          document.dispatchEvent(new CustomEvent('weco:progress', { detail: d }));
        })
        .catch(function () { why.textContent = 'Не удалось проверить, попробуйте ещё раз.'; why.hidden = false; })
        .then(function () { busy = false; render(); });
    }
    function reveal() {
      if (isDone() || busy) return;
      busy = true;
      post(tcfg.revealUrl, {})
        .then(function (d) {
          if (!d.correct_labels) return;
          correct = d.correct_labels.slice();
          mode = 'revealed';
          showLabels.textContent = correct.join(', ');
          document.dispatchEvent(new CustomEvent('weco:progress', { detail: d }));
        })
        .catch(function () {})
        .then(function () { busy = false; render(); });
    }
    function again() {
      sel = []; attempt = 1; mode = 'play'; correct = null; count = null;
      why.textContent = whyText;
      render();
    }
    opts.forEach(function (o) { o.addEventListener('click', function () { toggle(o.getAttribute('data-l')); }); });
    checkBtn.addEventListener('click', check);
    revealBtn.addEventListener('click', reveal);
    againBtn.addEventListener('click', again);
    t.test = {
      reveal: reveal,
      key: function (e) {
        var key = (e.key || '').toLowerCase();
        var idx = /^[1-9]$/.test(key) ? parseInt(key, 10) - 1 : tcfg.labels.indexOf(key);
        if (idx >= 0 && idx < opts.length) { toggle(opts[idx].getAttribute('data-l')); return true; }
        if (e.key === 'Enter' && !rowPlay.hidden) { check(); return true; }
        return false;
      }
    };
    render();
  }

  /* ── Чат по задаче: режимы, файлы к реплике, история ──────────────────
     Решение владельца 15.09.2026: три режима над полем, скрепка для фото или
     PDF. Номер разговора — один на открытие задачи. */
  function bindChat(t) {
    var aiIn = t.$('ai-in'), aiText = t.$('ai-text'), aiBody = t.$('ai-body'), aiSend = t.$('ai-send');
    if (!once(aiIn) || !aiText || !aiBody || !aiSend || !t.cfg.chatUrl) return;
    var history = [];
    var thread = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 3 | 8)).toString(16);
      });
    var attached = [];
    var clip = t.$('ai-clip'), fileIn = t.$('ai-file'), att = t.$('ai-att'), attStatus = t.$('ai-att-status'), tpl = t.$('ai-chip-tpl');
    function showAttached(label) {
      if (!att) return;
      att.querySelectorAll('.ai-chip').forEach(function (c) { c.remove(); });
      attached.forEach(function (file, index) {
        var chip = tpl.content.firstElementChild.cloneNode(true);
        chip.querySelector('.ai-chip-name').textContent = file.name;
        chip.querySelector('.ai-chip-x').addEventListener('click', function () { attached.splice(index, 1); showAttached(); });
        att.appendChild(chip);
      });
      if (attStatus) { attStatus.textContent = label || ''; attStatus.hidden = !label; }
      att.hidden = !(attached.length || label);
    }
    function fileLinks(files) {
      var box = document.createElement('div');
      box.className = 'ai-files';
      files.forEach(function (file) {
        var a = document.createElement('a');
        a.href = file.url; a.target = '_blank'; a.rel = 'noopener';
        if (/^image\//.test(file.mime || '')) {
          var img = document.createElement('img');
          img.className = 'ai-thumb'; img.src = file.url; img.alt = file.name;
          a.appendChild(img);
        } else {
          a.textContent = file.name;
        }
        box.appendChild(a);
      });
      return box;
    }
    function bubble(cls, text, files) {
      var el = document.createElement('div');
      el.className = 'ai-msg ' + cls;
      el.textContent = text;
      if (files && files.length) el.appendChild(fileLinks(files));
      aiBody.appendChild(el);
      aiBody.scrollTop = aiBody.scrollHeight;
      return el;
    }
    function typing() {
      var el = document.createElement('div');
      el.className = 'ai-msg ai-msg--ai';
      var dots = document.createElement('span');
      dots.className = 'typing';
      for (var i = 0; i < 3; i++) dots.appendChild(document.createElement('i'));
      el.appendChild(dots);
      aiBody.appendChild(el);
      aiBody.scrollTop = aiBody.scrollHeight;
      return el;
    }
    function sync() {
      aiIn.classList.toggle('has-text', aiText.value.trim().length > 0);
      aiText.style.height = 'auto';
      aiText.style.height = Math.min(120, aiText.scrollHeight) + 'px';
    }
    function send(text, mode) {
      mode = mode || 'free';
      text = (text || aiText.value).trim();
      if (!text) return;
      var files = attached.slice();
      bubble('ai-msg--me', text, files);
      aiText.value = '';
      sync();
      var payload = { problem_id: t.cfg.problemId, message: text, mode: mode, thread: thread,
                      history: history.slice(-HISTORY_LIMIT) };
      if (files.length) payload.attachment_ids = files.map(function (f) { return f.id; });
      if (window.weco.track) weco.track('chat_send', { problem_id: t.cfg.problemId, mode: mode, has_file: files.length > 0, files: files.length });
      attached = [];
      showAttached();
      var wait = typing();
      post(t.cfg.chatUrl, payload)
        .then(function (d) {
          var reply = d.reply || d.message || 'Не получилось ответить, попробуйте ещё раз.';
          wait.textContent = reply;
          if (d.note) {
            var line = document.createElement('div');
            line.className = 'ai-msg-note';
            line.textContent = d.note;
            wait.appendChild(line);
          }
          math(wait);
          aiBody.scrollTop = aiBody.scrollHeight;
          history.push({ role: 'me', text: text }, { role: 'ai', text: reply });
          history = history.slice(-HISTORY_LIMIT);
          var rest = t.$('sv-remaining');
          if (rest && d.remaining !== undefined) rest.textContent = d.remaining;
        })
        .catch(function () { wait.textContent = 'Не получилось ответить, попробуйте ещё раз.'; });
    }
    t.chat = { send: send, focus: function () { aiText.focus({ preventScroll: true }); } };
    /* Разговор переживает перезагрузку и смену задачи: свои реплики по этой
       задаче из журнала `ChatTurn` — пузырями с формулами и ссылками на файлы. */
    if (t.cfg.chatHistoryUrl) {
      fetch(t.cfg.chatHistoryUrl, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : { turns: [] }; })
        .then(function (d) {
          if (cur !== t) return;
          (d.turns || []).forEach(function (turn) {
            bubble('ai-msg--me', turn.message, turn.attachments);
            math(bubble('ai-msg--ai', turn.reply));
            history.push({ role: 'me', text: turn.message }, { role: 'ai', text: turn.reply });
          });
          history = history.slice(-HISTORY_LIMIT);
        })
        .catch(function () { /* без истории чат работает как раньше */ });
    }
    aiText.addEventListener('input', sync);
    aiText.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
    aiSend.addEventListener('click', function () { send(); });
    var sug = t.$('ai-sug');
    if (sug) sug.querySelectorAll('[data-mode]').forEach(function (b) {
      b.addEventListener('click', function () {
        var mode = b.getAttribute('data-mode'), typed = aiText.value.trim();
        /* Проверять нечего — ни текста, ни файла: подсказка вместо пустого запроса. */
        if (mode === 'check' && !typed && !attached.length) { bubble('ai-msg--ai', t.cfg.chatCheckEmpty); return; }
        send(typed || b.getAttribute('data-prompt') || b.textContent.trim(), mode);
      });
    });
    if (clip && fileIn && t.cfg.chatUploadUrl) {
      clip.addEventListener('click', function () { fileIn.click(); });
      var upload = function (file) {
        var form = new FormData();
        form.append('file', file);
        form.append('problem_id', t.cfg.problemId);
        return fetch(t.cfg.chatUploadUrl, { method: 'POST', credentials: 'same-origin',
                                            headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, body: form })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.error) { bubble('ai-msg--ai', d.message || 'Файл не принят.'); return; }
            attached.push({ id: d.id, name: d.name || 'файл', mime: d.mime, url: d.url });
          })
          .catch(function () { bubble('ai-msg--ai', 'Не удалось загрузить файл, попробуйте ещё раз.'); });
      };
      /* Файлы — по одному (сервер принимает один на запрос), лишние сверх трёх —
         честной строкой в чате, а не молча. */
      fileIn.addEventListener('change', function () {
        var files = Array.prototype.slice.call(fileIn.files || []);
        fileIn.value = '';
        if (!files.length) return;
        var room = FILES_PER_TURN - attached.length;
        if (files.length > room) {
          bubble('ai-msg--ai', 'Не больше трёх файлов к одной реплике.');
          files = files.slice(0, Math.max(0, room));
        }
        if (!files.length) return;
        clip.disabled = true;
        showAttached('Загружаем файл…');
        files.reduce(function (chain, file) { return chain.then(function () { return upload(file); }); }, Promise.resolve())
          .then(function () { clip.disabled = false; showAttached(); });
      });
    }
    sync();
  }

  /* ── Вход: одна задача на экране, узлы ищутся внутри неё ─────────────── */
  function init(root) {
    root = root || document;
    var cfgEl = root.querySelector('.stol-cfg');
    if (!cfgEl) { cur = null; return null; }
    var t = { root: root, cfg: JSON.parse(cfgEl.textContent), submitted: false, solutionViewedBefore: false };
    t.$ = function (id) { var el = root.querySelector('#' + id); return el; };
    t.say = function () {};
    cur = t;
    bindBar(t);
    bindAttempt(t);
    bindSolution(t);
    bindHints(t);
    bindHow(t);
    bindTest(t);
    bindChat(t);
    return t;
  }

  /* ── Общие для документа слушатели — один раз на страницу ─────────────── */
  document.addEventListener('click', function (e) {
    if (!cur) return;
    if (e.target.closest('[data-retry]') && cur.retry) { cur.retry(); return; }
    var ask = e.target.closest('[data-ask]');
    if (ask && cur.chat && ask.dataset.ask) { cur.chat.send(ask.dataset.ask); return; }
    /* Телефон и полоска помощи: кнопки зовут действия задачи, а не дублируют их. */
    var btn = e.target.closest('[data-phone], [data-help-open]');
    if (!btn) return;
    var what = btn.getAttribute('data-phone') || btn.getAttribute('data-help-open');
    if (window.weco.stol && weco.stol.openPanel) weco.stol.openPanel('help');
    if (what === 'hint' && cur.askHint) { cur.askHint(); }
    else if (what === 'ai' && cur.chat) { cur.chat.focus(); }
    else if (what === 'sol') { var sb = cur.$('sol-btn'); if (sb && !sb.disabled) { sb.click(); sb.scrollIntoView({ block: 'center', behavior: 'smooth' }); } }
    else if (what === 'reveal' && cur.test) { cur.test.reveal(); }
  });
  /* Клавиатура теста: 1–9 и буквы меток выбирают, Enter проверяет; в полях молчим. */
  document.addEventListener('keydown', function (e) {
    if (!cur || !cur.test) return;
    var el = e.target;
    if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable)) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (cur.test.key(e)) e.preventDefault();
  });

  weco.stolTask = { init: init, current: function () { return cur; } };
})();
