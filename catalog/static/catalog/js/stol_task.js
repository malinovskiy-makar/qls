/* «Стол»: всё, что живёт внутри открытой задачи (README §3–§5).
 *
 * Центр: сохранить, скопировать ссылку, «Как прошло?», «спросить ИИ про этот
 * пункт», «Обсудить с ИИ» по выделению условия и «Ответить» по фрагменту ответа ИИ, тест как игра.
 * Помощь: лестница, одна лента по времени (подсказки, реплики, проверка
 * решения, подтверждение и решение, ответ по пункту), поле для разговора и
 * проверки решения с файлами, строка «что уже использовано».
 *
 * ⚠️ `weco.stolTask.init(root)` ЗОВЁТСЯ ЗАНОВО ПОСЛЕ КАЖДОЙ ПОДМЕНЫ ЗАДАЧИ
 * (ответ `?pane=1`, `stol.js`). Слушатели вешаются только на узлы внутри
 * `root` — они уходят вместе с подменённой разметкой; общие для документа
 * (клавиши теста, делегирование кликов, выделение текста) зарегистрированы
 * один раз и обращаются к текущей задаче через `cur`. Повторный `init` на тех
 * же узлах ничего не удваивает: узел помечается `data-bound`.
 *
 * Разметку карточек дают шаблоны `<template>` панели помощи и сервер
 * (`_attempt_result.html`); данные кладутся через textContent — сырое в
 * innerHTML не идёт. Ответ ИИ — лёгкая разметка из узлов (абзацы, списки,
 * жирный) и формулы общим конвейером `renderMathIn`.
 * ⚠️ Наружу уходит текст решения, реплика и цитата условия — ничего из профиля.
 * ⚠️ В модель уходят последние шесть реплик (ADR 0080).
 */
(function () {
  'use strict';
  window.weco = window.weco || {};
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
  var HISTORY_LIMIT = 6;
  var FILES_PER_TURN = 3;
  var QUOTE_MAX = 300;
  var cur = null;          /* текущая задача: { cfg, root, ... } */

  function post(url, payload) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json().then(function (d) { d._status = r.status; return d; }); });
  }
  function upload(url, form) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', body: form,
                        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); });
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
  function tpl(root, id) {
    var t = root.querySelector('#' + id);
    return t ? t.content.firstElementChild.cloneNode(true) : null;
  }
  /* ⚠️ ТЕКСТ БЕЗ ЗАДВОЕННЫХ ФОРМУЛ (24.09.2026). KaTeX рисует каждую формулу
     дважды: невидимую копию MathML для чтецов экрана и видимую HTML. У
     `innerText`/`textContent` и у выделения обе копии, и в цитату чата
     уходило «x↵x и↵y↵y». Здесь копия MathML срезается. */
  function plainText(node) {
    if (!node) return '';
    var copy = node.cloneNode(true);
    Array.prototype.forEach.call(copy.querySelectorAll('.katex-mathml'), function (m) { m.remove(); });
    return copy.textContent.replace(/\s+/g, ' ').trim();
  }
  window.weco.plainText = plainText;
  /* Карточка из разметки СЕРВЕРА (решение, ответ к пункту — ADR 0129): её
     рисуют наши партиалы с экранированием, как при загрузке страницы. */
  function fromHtml(html) {
    var box = document.createElement('template');
    box.innerHTML = String(html || '').trim();
    return box.content.firstElementChild;
  }

  /* ── Ответ ИИ: лёгкая разметка узлами ─────────────────────────────────
     Сначала «экранирование» — текст кладётся только через textContent; потом
     абзацы (пустая строка), списки («- », «* », «1. »), жирный (**…**).
     Формула «$$…$$» на своей строке остаётся своим абзацем — KaTeX сделает
     её блочной. Длина не режется: ответ показывается целиком. */
  function inline(parent, text) {
    text.split(/(\*\*[^*\n]+\*\*)/).forEach(function (piece) {
      if (/^\*\*[^*\n]+\*\*$/.test(piece)) {
        var b = document.createElement('b'); b.textContent = piece.slice(2, -2); parent.appendChild(b);
      } else if (piece) {
        parent.appendChild(document.createTextNode(piece));
      }
    });
  }
  function rich(el, text) {
    el.textContent = '';
    /* Строки блока идут подряд: пункты списка собираются в список, прочие — в
       абзац; «План:» над пунктами остаётся абзацем над списком. */
    String(text || '').replace(/\r/g, '').split(/\n{2,}/).forEach(function (block) {
      var box = null, kind = '';
      block.split('\n').forEach(function (l) {
        if (!l.trim()) return;
        var bullet = /^\s*[-*•]\s+/.test(l), number = /^\s*\d+[.)]\s+/.test(l);
        var want = bullet ? 'ul' : number ? 'ol' : 'p';
        if (want !== kind) { box = document.createElement(want); kind = want; el.appendChild(box); }
        if (want === 'p') {
          if (box.childNodes.length) box.appendChild(document.createElement('br'));
          inline(box, l);
        } else {
          var li = document.createElement('li');
          inline(li, l.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, ''));
          box.appendChild(li);
        }
      });
    });
    math(el);
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
    /* Телефон: меню задачи «≡» (лента, ссылка, «Ошибка в задаче?») зовёт те же кнопки. */
    var menuBtn = t.$('tb-menu-btn'), menuPop = t.$('tb-menu-pop');
    if (menuBtn && once(menuBtn)) {
      menuBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = menuPop.hidden;
        menuPop.hidden = !open;
        menuBtn.setAttribute('aria-expanded', String(open));
      });
      menuPop.addEventListener('click', function (e) {
        var item = e.target.closest('button');
        if (!item) return;
        menuPop.hidden = true;
        menuBtn.setAttribute('aria-expanded', 'false');
        var proxy = item.getAttribute('data-proxy');
        if (proxy) { var target = t.root.querySelector(proxy); if (target) target.click(); }
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

  /* ── Помощь: лестница, лента, «что уже использовано» ─────────────────── */
  function bindHelp(t) {
    var feed = t.$('help-feed'), ladder = t.$('help-ladder'), used = t.$('help-used');
    var hintBtn = t.$('hint-btn');
    if (!feed || !once(feed)) return;
    t.hintsOpened = feed.querySelectorAll('.feed-hint').length;
    t.solutionShown = !!feed.querySelector('.feed-sol');
    /* Прокрутка — только внутри ленты: `scrollIntoView` двигал бы и страницу. */
    var body = t.$('help-body');
    t.reveal = function (card) {
      if (!body || !card) return;
      var r = card.getBoundingClientRect(), b = body.getBoundingClientRect();
      if (r.bottom > b.bottom) body.scrollTop += Math.min(r.bottom - b.bottom + 8, r.top - b.top);
    };
    t.feed = function (card) {
      if (ladder) ladder.hidden = true;
      feed.appendChild(card);
      t.reveal(card);
      return card;
    };
    function paintUsed() {
      if (!used) return;
      var total = Number(used.getAttribute('data-total')) || 0, parts = [];
      if (t.hintsOpened) parts.push('подсказок ' + t.hintsOpened + ' из ' + total);
      if (t.solutionShown) parts.push('решение');
      /* С заглавной (24.09.2026): «Подсказок 4 из 4 · решение», «Решение». */
      var line = parts.length ? parts.join(' · ') : 'пока ничем не пользовались';
      used.textContent = line.charAt(0).toUpperCase() + line.slice(1);
    }
    t.paintUsed = paintUsed;

    /* Подсказки по одной; сервер пишет `hints_opened` (перезагрузка покажет их же). */
    var busy = false;
    t.askHint = function () {
      var total = t.cfg.hintTotal || 0;
      if (busy || !t.cfg.hintUrl || t.hintsOpened >= total) return;
      busy = true;
      fetch(t.cfg.hintUrl + (t.hintsOpened + 1) + '/', { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (d) {
          t.hintsOpened = d.n;
          var card = tpl(t.root, 'help-hint-tpl');
          card.querySelector('.feed-k-l').textContent = 'Подсказка ' + d.n + ' из ' + d.total + (d.part ? ' · пункт ' + d.part + ')' : '');
          card.querySelector('.feed-t').textContent = d.text;
          card.querySelector('.feed-note').hidden = !(d.ai && !d.reviewed);
          math(t.feed(card));
          var left = d.total - d.n;
          var badge = document.getElementById('strip-hints');
          if (badge) { badge.textContent = String(left); badge.parentNode.hidden = !left; }
          var phone = document.getElementById('phone-hints');
          if (phone) { phone.textContent = String(left); phone.hidden = !left; }
          if (hintBtn) {
            hintBtn.hidden = !left;
            var n = hintBtn.querySelector('.n'); if (n) n.textContent = (d.n + 1) + ' из ' + d.total;
          }
          paintUsed();
        })
        .catch(function () { t.say('Не удалось получить подсказку, попробуйте ещё раз.'); })
        .then(function () { busy = false; });
    };
    if (hintBtn && once(hintBtn)) hintBtn.addEventListener('click', t.askHint);

    /* Гостю вместо решения и ответов — приглашение к регистрации (ADR 0129). */
    t.invite = function () {
      var shown = feed.querySelector('.feed-invite');
      if (shown) { t.reveal(shown); return; }
      var card = tpl(t.root, 'help-invite-tpl');
      if (card) t.feed(card);
    };

    /* Решение: сначала подтверждение карточкой, потом само решение (README §4).
       Решения в разметке нет: оно приходит запросом после «Открыть». */
    t.askSolution = function () {
      if (t.cfg.guest) { t.invite(); return; }
      if (t.solutionShown) { var s = feed.querySelector('.feed-sol'); t.reveal(s); return; }
      if (feed.querySelector('.feed-confirm')) return;
      var box = tpl(t.root, 'help-confirm-tpl');
      if (!box) return;
      t.feed(box);
      box.querySelector('[data-confirm="yes"]').addEventListener('click', function () {
        box.remove();
        post(t.cfg.solutionUrl, {}).then(function (d) {
          var sol = d && d.html ? fromHtml(d.html) : null;
          if (!sol) { t.say('Не удалось открыть решение, попробуйте ещё раз.'); return; }
          shownSolution(sol);
        }).catch(function () { t.say('Не удалось открыть решение, попробуйте ещё раз.'); });
      });
      box.querySelector('[data-confirm="no"]').addEventListener('click', function () { box.remove(); });
    };
    function shownSolution(sol) {
      math(t.feed(sol));
      t.solutionShown = true;
      t.solutionViewedBefore = !t.submitted;
      var solBtn = t.$('sol-btn'); if (solBtn) solBtn.hidden = true;
      progress(t, { solution_viewed: true });
      var self = t.$('how') && t.$('how').querySelector('[data-how="self"]');
      if (self) { self.disabled = true; self.title = 'Решение уже открыто'; }
      paintUsed();
    }

    /* Ответ по одному пункту — только при ответах в данных (решение 17.09).
       Ответ приходит запросом, гостю — приглашение (ADR 0129). */
    t.askPart = function () {
      if (t.cfg.guest) { t.invite(); return; }
      if (feed.querySelector('.feed-parts')) return;
      var box = tpl(t.root, 'help-parts-tpl');
      if (!box) return;
      t.feed(box);
      box.addEventListener('click', function (e) {
        var b = e.target.closest('[data-part]');
        if (!b) return;
        box.remove();
        post(t.cfg.solutionUrl, { part: Number(b.getAttribute('data-part')) }).then(function (d) {
          var card = d && d.html ? fromHtml(d.html) : null;
          if (card) math(t.feed(card)); else t.say('Не удалось открыть ответ, попробуйте ещё раз.');
        }).catch(function () { t.say('Не удалось открыть ответ, попробуйте ещё раз.'); });
      });
    };

    t.root.querySelectorAll('[data-step]').forEach(function (b) {
      if (!once(b)) return;
      b.addEventListener('click', function () { t.step(b.getAttribute('data-step')); });
    });

    /* «Решить заново» (решение владельца 24.09.2026, ADR 0130): подтверждение
       карточкой в ленте, затем экран — как у новой задачи. Сервер чистит
       только экран ученика; статистика репетитора и переписка в базе те же. */
    var resetBtn = t.$('help-reset');
    if (resetBtn && once(resetBtn) && t.cfg.resetUrl) resetBtn.addEventListener('click', function () {
      if (window.weco.stol && weco.stol.openPanel) weco.stol.openPanel('help');
      var shown = feed.querySelector('.feed-reset');
      if (shown) { t.reveal(shown); return; }
      var box = tpl(t.root, 'help-reset-tpl');
      if (!box) return;
      t.feed(box);
      box.querySelector('[data-confirm="no"]').addEventListener('click', function () { box.remove(); });
      box.querySelector('[data-confirm="yes"]').addEventListener('click', function () {
        post(t.cfg.resetUrl, {}).then(function (d) {
          if (d && d.error) { box.remove(); t.say('Не получилось начать заново, попробуйте ещё раз.'); return; }
          if (window.weco.track) weco.track('help_reset', { problem_id: t.cfg.problemId });
          location.reload();
        }).catch(function () { box.remove(); t.say('Не получилось начать заново, попробуйте ещё раз.'); });
      });
    });
  }
  function step(t, what) {
    if (window.weco.stol && weco.stol.openPanel) weco.stol.openPanel('help');
    if (what === 'hint' && t.askHint) t.askHint();
    else if (what === 'sol' && t.askSolution) t.askSolution();
    else if (what === 'part' && t.askPart) t.askPart();
    else if (what === 'reveal' && t.test) t.test.reveal();
    else if (what === 'ai' && t.chat) t.chat.focus();
  }

  /* ── Поле помощи: разговор с ИИ и проверка решения ─────────────────────
     Режимы «Теория / Как решать / Проверь решение» — свойство реплики
     (решение 15.09.2026). «Проверь решение» при доступной модели проверки —
     попытка (`/catalog/api/attempt/`, балл и шаги карточкой), иначе реплика
     чата в режиме проверки. Файлы держатся в браузере и уходят при отправке —
     туда, куда уходит реплика: к чату или к попытке. */
  function bindComposer(t) {
    var aiIn = t.$('ai-in'), aiText = t.$('ai-text'), aiSend = t.$('ai-send');
    if (!aiIn || !once(aiIn) || !aiText || !aiSend) return;
    var history = [];
    var thread = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 3 | 8)).toString(16);
      });
    var files = [];                          /* [{file, name}] — ещё не загружены */
    var quote = '', quoteSource = 'statement';  /* statement | reply («Ответить») */
    var clip = t.$('ai-clip'), fileIn = t.$('ai-file'), att = t.$('ai-att'), attStatus = t.$('ai-att-status');
    var quoteBox = t.$('ai-quote');

    function showFiles(label) {
      if (!att) return;
      att.querySelectorAll('.ai-chip').forEach(function (c) { c.remove(); });
      files.forEach(function (f, i) {
        var chip = document.createElement('span');
        chip.className = 'ai-chip';
        var name = document.createElement('span'); name.className = 'ai-chip-name'; name.textContent = f.name;
        var x = document.createElement('button');
        x.type = 'button'; x.className = 'ai-chip-x'; x.setAttribute('aria-label', 'Убрать файл'); x.textContent = '×';
        x.addEventListener('click', function () { files.splice(i, 1); showFiles(); });
        chip.appendChild(name); chip.appendChild(x);
        att.appendChild(chip);
      });
      if (attStatus) { attStatus.textContent = label || ''; attStatus.hidden = !label; }
      att.hidden = !(files.length || label);
      if (clip) clip.disabled = files.length >= FILES_PER_TURN;
    }
    function setQuote(text, source) {
      quote = String(text || '').replace(/\s+/g, ' ').trim().slice(0, QUOTE_MAX);
      quoteSource = source === 'reply' ? 'reply' : 'statement';
      if (!quoteBox) return;
      quoteBox.querySelector('.ai-quote-t').textContent = quote ? '«' + quote + '»' : '';
      quoteBox.hidden = !quote;
    }
    if (quoteBox) quoteBox.querySelector('button').addEventListener('click', function () { setQuote(''); });

    function fileLinks(list) {
      var box = document.createElement('div');
      box.className = 'ai-files';
      list.forEach(function (file) {
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
    function bubble(mine, text, extra) {
      var el = document.createElement('div');
      el.className = 'ai-msg ' + (mine ? 'ai-msg--me' : 'ai-msg--ai');
      if (mine) {
        if (extra && extra.quote) {
          var q = document.createElement('div'); q.className = 'ai-msg-quote'; q.textContent = '«' + extra.quote + '»';
          el.appendChild(q);
        }
        var body = document.createElement('div'); body.textContent = text; el.appendChild(body);
        if (extra && extra.files && extra.files.length) el.appendChild(fileLinks(extra.files));
      } else if (text) {
        rich(el, text);
      }
      return t.feed(el);
    }
    function typing() {
      var el = bubble(false, '');
      var dots = document.createElement('span');
      dots.className = 'typing';
      for (var i = 0; i < 3; i++) dots.appendChild(document.createElement('i'));
      el.appendChild(dots);
      return el;
    }
    function sync() {
      aiIn.classList.toggle('has-text', aiText.value.trim().length > 0);
      aiText.style.height = 'auto';
      /* ⚠️ Скрытая панель даёт scrollHeight = 0: высота прижималась к 24 px, и
         одна строка переполняла поле — вылезала толстая системная полоса
         (24.09.2026). Меряем только видимое поле; полоса — только когда
         текст выше потолка 120 px. */
      if (!aiText.scrollHeight) { aiText.style.height = ''; return; }
      aiText.style.height = Math.min(120, aiText.scrollHeight) + 'px';
      aiText.style.overflowY = aiText.scrollHeight > 120 ? 'auto' : 'hidden';
    }
    /* Загрузить выбранные файлы туда, куда уходит реплика; ответ — [{id,…}]. */
    function sendFiles(url, extra) {
      var done = [];
      return files.reduce(function (chain, f) {
        return chain.then(function () {
          var form = new FormData();
          form.append('file', f.file);
          if (extra) Object.keys(extra).forEach(function (k) { form.append(k, extra[k](done)); });
          return upload(url, form).then(function (d) {
            if (d.error) throw new Error(d.message || 'Файл не принят.');
            done.push(d);
          });
        });
      }, Promise.resolve()).then(function () { return done; });
    }

    function chat(text, mode) {
      if (!t.cfg.chatUrl) return;
      var own = files.slice(), q = quote, qs = quoteSource;
      showFiles(own.length ? 'Загружаем файл…' : '');
      var upl = own.length && t.cfg.chatUploadUrl
        ? sendFiles(t.cfg.chatUploadUrl, { problem_id: function () { return t.cfg.problemId; } })
        : Promise.resolve([]);
      files = []; setQuote(''); aiText.value = ''; sync();
      upl.then(function (uploaded) {
        showFiles();
        var shown = uploaded.map(function (d) { return { url: d.url, mime: d.mime, name: d.name || 'файл' }; });
        bubble(true, text, { quote: q, files: shown });
        var payload = { problem_id: t.cfg.problemId, message: text, mode: mode, thread: thread,
                        history: history.slice(-HISTORY_LIMIT) };
        if (q) { payload.quote = q; payload.quote_source = qs; }
        if (uploaded.length) payload.attachment_ids = uploaded.map(function (d) { return d.id; });
        if (window.weco.track) weco.track('chat_send', { problem_id: t.cfg.problemId, mode: mode, has_file: uploaded.length > 0, files: uploaded.length, quote: !!q });
        var wait = typing();
        return post(t.cfg.chatUrl, payload).then(function (d) {
          t.limit(d.error === 'limit' ? 0 : d.remaining);
          var reply = d.reply || d.message || 'Не получилось ответить, попробуйте ещё раз.';
          rich(wait, reply);
          t.reveal(wait);
          if (d.note) {
            var line = document.createElement('div');
            line.className = 'ai-msg-note';
            line.textContent = d.note;
            wait.appendChild(line);
          }
          history.push({ role: 'me', text: text }, { role: 'ai', text: reply });
          history = history.slice(-HISTORY_LIMIT);
        }).catch(function () { wait.textContent = 'Не получилось ответить, попробуйте ещё раз.'; });
      }).catch(function (err) { showFiles(); bubble(false, err.message || 'Не удалось загрузить файл, попробуйте ещё раз.'); });
    }

    function attempt(text) {
      var own = files.slice();
      if (!text && !own.length) { bubble(false, t.cfg.chatCheckEmpty || 'Напишите решение или приложите фото.'); return; }
      var busyCard = tpl(t.root, 'help-busy-tpl');
      files = []; setQuote(''); aiText.value = ''; sync(); showFiles();
      bubble(true, text || 'Решение на фото', {});
      if (busyCard) t.feed(busyCard);
      var upl = own.length && t.cfg.fileUrl
        ? sendFiles(t.cfg.fileUrl, { pending: function (done) { return done.map(function (d) { return d.id; }).join(','); } })
        : Promise.resolve([]);
      upl.then(function (uploaded) {
        return post(t.cfg.attemptUrl, { problem_id: t.cfg.problemId, text: text,
                                        file_ids: uploaded.map(function (d) { return d.id; }),
                                        solution_viewed_before: !!t.solutionViewedBefore });
      }).then(function (d) {
        if (busyCard) busyCard.remove();
        if (d.error === 'limit') t.limit(0);
        if (d.error) { bubble(false, d.message || 'Проверка не удалась, попробуйте ещё раз.'); return; }
        var old = t.$('chk-holder'); if (old) old.removeAttribute('id');
        var card = document.createElement('div');
        card.className = 'feed-card feed-chk';
        card.id = 'chk-holder';
        /* Разметку результата рисует сервер тем же партиалом, что при открытии. */
        card.innerHTML = d.html;
        math(t.feed(card));
        t.submitted = true;
        t.limit(d.remaining);
      }).catch(function (err) {
        if (busyCard) busyCard.remove();
        bubble(false, (err && err.message) || 'Не удалось отправить решение, попробуйте ещё раз.');
      });
    }

    function send(mode, fallback) {
      var text = aiText.value.trim();
      if (mode === 'check' && t.cfg.attemptUrl) { attempt(text); return; }
      if (mode === 'check' && !text && !files.length) { bubble(false, t.cfg.chatCheckEmpty); return; }
      text = text || fallback || '';
      if (!text) return;
      chat(text, mode);
    }
    t.chat = {
      send: function (text) { aiText.value = text; send('free'); },
      focus: function () { aiText.focus({ preventScroll: true }); },
      prefill: function (prefix, q, source) {
        if (q !== undefined) setQuote(q, source);
        if (prefix && aiText.value.indexOf(prefix) !== 0) aiText.value = prefix + aiText.value;
        sync();
        aiText.focus({ preventScroll: true });
        aiText.setSelectionRange(aiText.value.length, aiText.value.length);
      },
      quote: setQuote
    };
    /* Разговор переживает перезагрузку и смену задачи: свои реплики по этой
       задаче из журнала `ChatTurn` — в ленту до новых карточек. */
    if (t.cfg.chatHistoryUrl) {
      fetch(t.cfg.chatHistoryUrl, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : { turns: [] }; })
        .then(function (d) {
          if (cur !== t || !(d.turns || []).length) return;
          (d.turns || []).forEach(function (turn) {
            bubble(true, turn.message, { files: turn.attachments, quote: turn.quote });
            bubble(false, turn.reply);
            history.push({ role: 'me', text: turn.message }, { role: 'ai', text: turn.reply });
          });
          history = history.slice(-HISTORY_LIMIT);
        })
        .catch(function () { /* без истории поле работает как раньше */ });
    }
    aiText.addEventListener('input', sync);
    aiText.addEventListener('focus', sync);
    aiText.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send('free'); } });
    aiSend.addEventListener('click', function () { send('free'); });
    var sug = t.$('ai-sug');
    if (sug) sug.querySelectorAll('[data-mode]').forEach(function (b) {
      b.addEventListener('click', function () { send(b.getAttribute('data-mode'), b.getAttribute('data-prompt')); });
    });
    if (clip && fileIn) {
      clip.addEventListener('click', function () { fileIn.click(); });
      fileIn.addEventListener('change', function () {
        var picked = Array.prototype.slice.call(fileIn.files || []);
        fileIn.value = '';
        var room = FILES_PER_TURN - files.length;
        if (picked.length > room) {
          bubble(false, 'Не больше трёх файлов к одной реплике.');
          picked = picked.slice(0, Math.max(0, room));
        }
        picked.forEach(function (f) { files.push({ file: f, name: f.name }); });
        showFiles();
      });
    }
    sync();
  }

  /* ── Тест как игра (этап 7, README §5): выбор, всё-или-ничего, разбор ─── */
  function bindTest(t) {
    var tq = t.$('tq'), tcfg = t.cfg.test;
    if (!once(tq) || !tcfg || !tcfg.checkUrl) return;
    var opts = Array.prototype.slice.call(tq.querySelectorAll('.opt'));
    var sel = [], tried = [], mode = 'play', attempt = 1, correct = null, count = null, busy = false;
    var msgWrong = t.$('msg-wrong'), msgOk = t.$('msg-ok'), msgShow = t.$('msg-show'), cnt = t.$('msg-cnt');
    var rowPlay = t.$('row-play'), rowDone = t.$('row-done'), expl = t.$('expl'), tryEl = t.$('tq-try');
    var checkBtn = t.$('check-btn'), why = t.$('check-why'), revealBtn = t.$('reveal-btn');
    var againBtn = t.$('again-btn'), askWhy = t.$('ask-why'), okSub = t.$('ok-sub'), showLabels = t.$('show-labels');
    function nth(n) { return (n === 2 ? 'со ' : 'с ') + n + '-й попытки'; }
    function isDone() { return mode === 'solved' || mode === 'revealed'; }
    function render() {
      var done = isDone();
      opts.forEach(function (o) {
        var l = o.getAttribute('data-l'), on = sel.indexOf(l) >= 0, was = tried.indexOf(l) >= 0;
        o.setAttribute('aria-pressed', on ? 'true' : 'false');
        o.classList.remove('is-hit', 'is-wrong', 'is-missed', 'is-skip', 'is-tried');
        /* Ошибочный вариант одиночного теста второй раз не выбирается (README §5). */
        o.disabled = done || was;
        var note = o.querySelector('.opt-note');
        note.textContent = '';
        if (done && correct) {
          var right = correct.indexOf(l) >= 0;
          if (right && (on || mode === 'revealed')) { o.classList.add('is-hit'); note.textContent = 'верно'; }
          else if (on || was) { o.classList.add('is-wrong'); note.textContent = 'вы выбирали'; }
          else if (right) { o.classList.add('is-missed'); note.textContent = 'надо было выбрать'; }
          else { o.classList.add('is-skip'); }
        } else if (was) {
          o.classList.add('is-tried'); note.textContent = 'не то';
        }
      });
      msgWrong.classList.toggle('is-on', mode === 'wrong');
      msgOk.classList.toggle('is-on', mode === 'solved');
      msgShow.classList.toggle('is-on', mode === 'revealed');
      rowPlay.hidden = done;
      rowDone.hidden = !done;
      if (expl) { expl.classList.toggle('is-on', done); if (done) math(expl); }
      checkBtn.disabled = !sel.length || busy;
      tryEl.textContent = 'попытка ' + attempt;
      if (mode === 'solved') okSub.textContent = 'Верно ' + nth(attempt);
      cnt.hidden = !(mode === 'wrong' && count !== null);
      if (!cnt.hidden) cnt.textContent = 'верных вариантов: ' + count;
      if (askWhy) askWhy.setAttribute('data-ask', correct ? 'Объясни, почему в этом тесте верно именно: ' + correct.join(', ') : '');
    }
    function fail(text) { why.textContent = text; why.hidden = false; }
    function toggle(l) {
      if (isDone() || busy || tried.indexOf(l) >= 0) return;
      var i = sel.indexOf(l);
      if (!tcfg.multi) { sel = i >= 0 ? [] : [l]; }
      else if (i >= 0) { sel.splice(i, 1); }
      else { sel.push(l); }
      if (mode === 'wrong') mode = 'play';
      why.hidden = true;
      render();
    }
    function shake() { tq.classList.remove('is-shake'); void tq.offsetWidth; tq.classList.add('is-shake'); }
    function check() {
      if (!sel.length || isDone() || busy) return;
      busy = true;
      render();
      post(tcfg.checkUrl, { labels: sel.slice() })
        .then(function (d) {
          if (d.error) { fail(d.message || 'Не удалось проверить, попробуйте ещё раз.'); return; }
          attempt = d.attempt;
          if (window.weco.track) weco.track('test_answer', { problem_id: t.cfg.problemId, correct: !!d.correct, attempt: d.attempt });
          if (d.correct) {
            mode = 'solved';
            correct = sel.slice();
          } else {
            mode = 'wrong';
            if (!tcfg.multi) tried.push(sel[0]);
            sel = [];
            attempt = d.attempt + 1;
            count = (d.correct_count === undefined || d.correct_count === null) ? null : d.correct_count;
            shake();
          }
          document.dispatchEvent(new CustomEvent('weco:progress', { detail: d }));
        })
        .catch(function () { fail('Не удалось проверить, попробуйте ещё раз.'); })
        .then(function () { busy = false; render(); });
    }
    function reveal() {
      if (isDone() || busy) return;
      /* Верный вариант — это ответ: гостю приглашение (ADR 0129). */
      if (t.cfg.guest) {
        if (window.weco.stol && weco.stol.openPanel) weco.stol.openPanel('help');
        if (t.invite) t.invite();
        return;
      }
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
      sel = []; tried = []; attempt = 1; mode = 'play'; correct = null; count = null;
      why.hidden = true;
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

  /* ── Совет помощи один раз, дальше ⓘ у слова «Помощь» ──────────────────
     Решение владельца 24.09.2026. Сервер рисует и карточку, и ⓘ скрытыми —
     без мигания; здесь открывается одно из двух. Прочтением считается только
     «Понятно»: взял подсказку сразу — карточка уходит вместе с лестницей и
     покажется на следующей задаче. Помнит браузер ученика (`localStorage`),
     в приватном окне хранилища может не быть — тогда совет просто
     показывается снова. */
  var TIP_KEY = 'weco_help_tip_seen';
  function tipSeen() {
    try { return !!window.localStorage.getItem(TIP_KEY); } catch (e) { return false; }
  }
  var tipPop = null;       /* открытая всплывающая подсказка ⓘ: { btn, pop, via } */
  function closeTipPop() {
    if (!tipPop) return;
    tipPop.pop.hidden = true;
    tipPop.btn.setAttribute('aria-expanded', 'false');
    tipPop = null;
  }
  function openTipPop(btn, pop, via) {
    if (tipPop && tipPop.pop !== pop) closeTipPop();
    pop.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    tipPop = { btn: btn, pop: pop, via: via };
  }
  function bindTip(t) {
    closeTipPop();         /* задачу подменили — подсказка прежней ушла с разметкой */
    var card = t.$('help-tipcard'), info = t.$('help-info'), pop = t.$('help-info-pop');
    var seen = tipSeen();
    if (card) card.hidden = seen;
    if (info) info.hidden = !seen;
    var ok = t.$('help-tip-ok');
    if (ok && once(ok)) ok.addEventListener('click', function () {
      try { window.localStorage.setItem(TIP_KEY, '1'); } catch (e) { /* приватное окно */ }
      if (card) card.hidden = true;
      if (info) info.hidden = false;
    });
    if (!info || !pop || !once(info)) return;
    info.addEventListener('pointerenter', function (e) {
      if (e.pointerType === 'mouse' && !tipPop) openTipPop(info, pop, 'hover');
    });
    info.addEventListener('pointerleave', function (e) {
      if (e.pointerType === 'mouse' && tipPop && tipPop.pop === pop) closeTipPop();
    });
    /* Палец и клавиатура: нажатие открывает и закрывает. Мышь уже открыла
       наведением — нажатие подсказку не гасит. */
    info.addEventListener('click', function () {
      if (tipPop && tipPop.pop === pop) {
        if (tipPop.via === 'hover') { tipPop.via = 'click'; return; }
        closeTipPop();
      } else openTipPop(info, pop, 'click');
    });
  }
  /* Esc и клик мимо закрывают подсказку ⓘ. Перехват на `window` до слушателей
     «Стола»: первый Esc гасит подсказку, а не выходит из фокуса. */
  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && tipPop) { closeTipPop(); e.stopPropagation(); }
  }, true);
  document.addEventListener('click', function (e) {
    if (tipPop && !tipPop.btn.contains(e.target)) closeTipPop();
  });

  /* ── Вход: одна задача на экране, узлы ищутся внутри неё ─────────────── */
  function init(root) {
    root = root || document;
    var cfgEl = root.querySelector('.stol-cfg');
    if (!cfgEl) { cur = null; return null; }
    var t = { root: root, cfg: JSON.parse(cfgEl.textContent), submitted: false, solutionViewedBefore: false };
    t.$ = function (id) { return root.querySelector('#' + id); };
    t.say = function (text) { if (text && t.feed) { var p = document.createElement('p'); p.className = 'feed-card feed-err'; p.textContent = text; t.feed(p); } };
    t.step = function (what) { step(t, what); };
    /* Строка лимита ИИ (решение владельца 24.09.2026): счётчик общий на чат и
       проверку; видна, когда осталось не больше `limitWarnAt`. */
    t.limit = function (n) {
      var line = t.$('sv-limit'), num = t.$('sv-remaining');
      if (!line || !num || n === undefined || n === null) return;
      num.textContent = n;
      line.hidden = n > t.cfg.limitWarnAt;
    };
    cur = t;
    bindBar(t);
    bindHow(t);
    bindHelp(t);
    bindTip(t);
    bindComposer(t);
    bindTest(t);
    return t;
  }

  /* ── Общие для документа слушатели — один раз на страницу ─────────────── */
  /* Меню задачи на телефоне закрывается тапом мимо. */
  document.addEventListener('click', function (e) {
    if (e.target.closest('.tb-menu')) return;
    Array.prototype.forEach.call(document.querySelectorAll('.tb-menu-pop'), function (p) { p.hidden = true; });
  });
  document.addEventListener('click', function (e) {
    if (!cur) return;
    var ask = e.target.closest('[data-ask]');
    if (ask && cur.chat && ask.dataset.ask) { if (weco.stol && weco.stol.openPanel) weco.stol.openPanel('help'); cur.chat.send(ask.dataset.ask); return; }
    /* «Спросить ИИ про этот пункт»: цитата пункта и «Пункт б): » в поле. */
    var part = e.target.closest('[data-ask-part]');
    if (part && cur.chat) {
      var li = part.closest('.part');
      if (weco.stol && weco.stol.openPanel) weco.stol.openPanel('help');
      cur.chat.prefill('Пункт ' + li.getAttribute('data-part-label') + ': ', plainText(li.querySelector('.math-content')));
      return;
    }
    /* Телефон и полоска помощи зовут те же ступени, что и лестница. */
    var btn = e.target.closest('[data-phone], [data-help-open]');
    if (btn) cur.step(btn.getAttribute('data-phone') || btn.getAttribute('data-help-open'));
  });
  /* Клавиатура теста: 1–9 и буквы меток выбирают, Enter проверяет; в полях молчим. */
  document.addEventListener('keydown', function (e) {
    if (!cur || !cur.test) return;
    var el = e.target;
    if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable)) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (cur.test.key(e)) e.preventDefault();
  });

  /* «Обсудить с ИИ»: выделил фрагмент условия — тёмная кнопка у выделения,
     цитата до 300 знаков уходит в реплику (README §3). «Ответить» (24.09.2026,
     как в ChatGPT и Claude): то же на фрагменте ответа помощника — цитата
     уходит с пометкой «ответ помощника» (`quote_source: reply`). */
  var pop = null;
  function hidePop() { if (pop) pop.hidden = true; }
  function selectionHit() {
    var s = window.getSelection();
    if (!s || s.isCollapsed || !s.rangeCount) return null;
    var node = s.anchorNode && (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement);
    if (!node || !node.closest) return null;
    var source = node.closest('#stol-center .stm') ? 'statement'
      : node.closest('#help-feed .ai-msg--ai') ? 'reply' : '';
    if (!source) return null;
    var box = document.createElement('div');
    box.appendChild(s.getRangeAt(0).cloneContents());
    var text = plainText(box);
    return text.length >= 2 ? { text: text, source: source, rect: s.getRangeAt(0).getBoundingClientRect() } : null;
  }
  document.addEventListener('mouseup', function () {
    setTimeout(function () {
      var hit = cur && cur.chat ? selectionHit() : null;
      if (!hit) { hidePop(); return; }
      if (!pop) {
        pop = document.createElement('button');
        pop.type = 'button';
        pop.className = 'ask-pop';
        pop.addEventListener('mousedown', function (e) { e.preventDefault(); });
        pop.addEventListener('click', function () {
          var h = selectionHit();
          hidePop();
          if (!h || !cur || !cur.chat) return;
          if (weco.stol && weco.stol.openPanel) weco.stol.openPanel('help');
          cur.chat.prefill('', h.text, h.source);
        });
        document.body.appendChild(pop);
      }
      pop.textContent = hit.source === 'reply' ? 'Ответить' : 'Обсудить с ИИ';
      pop.hidden = false;
      pop.style.left = Math.max(8, hit.rect.left + hit.rect.width / 2 - 70 + window.scrollX) + 'px';
      pop.style.top = (hit.rect.top + window.scrollY - 44) + 'px';
    }, 0);
  });
  document.addEventListener('mousedown', function (e) { if (pop && e.target !== pop) hidePop(); });

  weco.stolTask = { init: init, current: function () { return cur; } };
})();
