/* «Стол»: корзина репетитора (README §7, снимки 21–25; решение владельца 17.09.2026).

   Файл подключается только репетитору (`is_tutor` в `stol.html`). Корзина —
   список `{id, t}` в `localStorage` под ключом с id пользователя: переживает
   фильтры, поиск, открытие задач без перезагрузки и саму перезагрузку.

   Галочки — в строках обеих лент (`.rail-check[data-basket]`, рисует сервер) и
   кнопка «+ В корзину» над задачей (`#basket-toggle`). Строки подменяются
   фильтрами, лентой и `?pane=1` — их состояние перерисовывается наблюдателем
   за DOM, а клики ловит один слушатель документа.

   Полоса: «Выбрано N» (список) · «В домашку ▾» → `add_problems` (позиции
   домашки) → зелёная плашка, корзина очищается · «PDF или TeX» → подборка
   `collection/from-basket/` → конструктор · «×» — очистить. Названия задач и
   работ — только через textContent. */
(function () {
  'use strict';
  var bar = document.getElementById('basket');
  var cfgNode = document.getElementById('basket-cfg');
  if (!bar || !cfgNode) return;
  var cfg = JSON.parse(cfgNode.textContent);
  var KEY = 'weco_basket_' + cfg.uid;
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
  function $(id) { return document.getElementById(id); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function plural(n, forms) {
    var a = n % 100, b = n % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b === 1) return forms[0];
    return b > 1 && b < 5 ? forms[1] : forms[2];
  }

  /* ── Хранилище ────────────────────────────────────────────────────── */
  function load() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY) || '[]');
      return Array.isArray(v) ? v.filter(function (x) { return x && Number(x.id); }) : [];
    } catch (e) { return []; }
  }
  var items = load();
  function save() { try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) { /* приватное окно */ } }
  function has(id) { return items.some(function (x) { return x.id === id; }); }
  function toggle(id, title) {
    if (has(id)) items = items.filter(function (x) { return x.id !== id; });
    else if (items.length < cfg.max) items.push({ id: id, t: title || '' });
    save();
    paint();
  }
  function clear() { items = []; save(); paint(); }
  /* Другая вкладка поменяла корзину — показать то же. */
  window.addEventListener('storage', function (e) { if (e.key === KEY) { items = load(); paint(); } });

  /* ── Отрисовка: галочки, кнопка над задачей, полоса ─────────────────── */
  function paintMarks() {
    qa('.rail-check[data-basket]').forEach(function (el) {
      var on = has(Number(el.getAttribute('data-basket')));
      if (el.getAttribute('aria-checked') !== String(on)) el.setAttribute('aria-checked', String(on));
    });
    var btn = $('basket-toggle');
    if (btn) {
      var on = has(Number(btn.getAttribute('data-basket')));
      btn.setAttribute('aria-pressed', String(on));
      btn.textContent = on ? 'В корзине' : '+ В корзину';
      btn.classList.toggle('is-on', on);
    }
  }
  function paint() {
    paintMarks();
    bar.hidden = !items.length;
    document.body.classList.toggle('has-basket', !!items.length);
    $('basket-n').textContent = String(items.length);
    var list = $('basket-items');
    list.textContent = '';
    items.slice().reverse().forEach(function (x) {
      var li = document.createElement('li');
      var t = document.createElement('span');
      t.className = 'basket-item-t';
      t.textContent = x.t || ('Задача ' + x.id);
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'basket-item-x';
      b.setAttribute('data-drop', String(x.id));
      b.setAttribute('aria-label', 'Убрать из корзины');
      b.textContent = '×';
      li.appendChild(t);
      li.appendChild(b);
      list.appendChild(li);
    });
    if (!items.length) closePops();
  }

  /* Строки подменяются фильтрами, лентой и `?pane=1`: состояние галочек —
     по наблюдателю, один раз за кадр. */
  var pending = false;
  new MutationObserver(function () {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; paintMarks(); });
  }).observe(document.getElementById('stol-app') || document.body, { childList: true, subtree: true });

  /* ── Клики: галочка строки (строка при этом не открывается), кнопка задачи ── */
  function onMark(e) {
    var el = e.target.closest('.rail-check[data-basket], #basket-toggle');
    if (!el) return false;
    e.preventDefault();
    e.stopPropagation();
    toggle(Number(el.getAttribute('data-basket')), el.getAttribute('data-basket-title'));
    return true;
  }
  document.addEventListener('click', onMark, true);
  document.addEventListener('keydown', function (e) {
    if ((e.key === ' ' || e.key === 'Enter') && e.target.classList && e.target.classList.contains('rail-check')) onMark(e);
  }, true);

  /* ── Всплывающие: список и меню домашек ───────────────────────────── */
  function pop(id, btnId, open) {
    var p = $(id), b = $(btnId);
    if (!p || !b) return;
    p.hidden = !open;
    b.setAttribute('aria-expanded', String(open));
  }
  function closePops() { pop('basket-list', 'basket-count', false); pop('basket-hw', 'basket-hw-btn', false); }
  $('basket-count').addEventListener('click', function () {
    var open = $('basket-list').hidden;
    closePops();
    pop('basket-list', 'basket-count', open);
  });
  var hwBtn = $('basket-hw-btn');
  if (hwBtn) hwBtn.addEventListener('click', function () {
    var open = $('basket-hw').hidden;
    closePops();
    pop('basket-hw', 'basket-hw-btn', open);
  });
  $('basket-items').addEventListener('click', function (e) {
    var b = e.target.closest('[data-drop]');
    if (b) toggle(Number(b.getAttribute('data-drop')));
  });
  $('basket-clear').addEventListener('click', clear);
  $('basket-x').addEventListener('click', clear);
  document.addEventListener('click', function (e) { if (!e.target.closest('#basket')) closePops(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePops(); });

  /* ── Отправка ─────────────────────────────────────────────────────── */
  function post(url, payload) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw d; return d; }); });
  }
  function ids() { return items.map(function (x) { return x.id; }); }
  function done(text, error) {
    var box = $('basket-done');
    $('basket-done-t').textContent = text;
    box.classList.toggle('is-error', !!error);
    box.hidden = false;
    $('basket-done-ok').focus();
  }
  $('basket-done-ok').addEventListener('click', function () { $('basket-done').hidden = true; });

  var busy = false;
  var hwMenu = $('basket-hw');
  if (hwMenu) hwMenu.addEventListener('click', function (e) {
    var row = e.target.closest('[data-hw]');
    if (!row || busy || !items.length) return;
    busy = true;
    closePops();
    var name = row.getAttribute('data-hw-name');
    post(cfg.addUrl.replace('/0/', '/' + row.getAttribute('data-hw') + '/'), { problem_ids: ids() })
      .then(function (d) {
        var parts = [d.added
          ? 'Добавлено в «' + name + '»: ' + d.added + ' ' + plural(d.added, ['задача', 'задачи', 'задач'])
          : 'Эти задачи уже есть в «' + name + '»'];
        if (d.added && d.already) parts.push('уже были там: ' + d.already);
        if (d.refused && d.refused.length) parts.push('скрыты из каталога и не добавлены: ' + d.refused.length);
        done(parts.join(', '));
        /* Число задач в меню и пометки «в N домашках» у добавленных строк. */
        var sub = row.querySelector('.basket-hw-sub');
        var n = Number(sub.getAttribute('data-hw-n')) + d.added, to = sub.getAttribute('data-hw-to');
        sub.setAttribute('data-hw-n', String(n));
        sub.textContent = n + ' ' + plural(n, ['задача', 'задачи', 'задач']) + (to ? ' · ' + to : '');
        (d.added_ids || []).forEach(markAdded);
        clear();
      })
      .catch(function () { done('Не получилось добавить: попробуйте ещё раз.', true); })
      .then(function () { busy = false; });
  });
  function markAdded(id) {
    qa('.rail-row[data-id="' + id + '"] .rail-meta').forEach(function (meta) {
      var hw = meta.querySelector('.rail-hw');
      if (!hw) {
        hw = document.createElement('span');
        hw.className = 'rail-hw';
        hw.setAttribute('data-hw-n', '0');
        meta.insertBefore(hw, meta.querySelector('.rail-saved'));
      }
      var n = Number(hw.getAttribute('data-hw-n')) + 1;
      hw.setAttribute('data-hw-n', String(n));
      hw.textContent = 'в ' + n + ' ' + plural(n, ['домашке', 'домашках', 'домашках']);
    });
  }

  $('basket-pdf').addEventListener('click', function () {
    if (busy || !items.length) return;
    busy = true;
    post(cfg.pdfUrl, { problem_ids: ids() })
      .then(function (d) { location.href = d.url; })
      .catch(function () { busy = false; done('Не получилось собрать подборку: попробуйте ещё раз.', true); });
  });

  paint();
})();
