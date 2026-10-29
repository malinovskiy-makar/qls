/* Вход и регистрация (раунд 2): глаз у пароля и шесть ячеек кода из письма.
   Всё — поверх обычной формы: без скрипта поле пароля и поле кода работают сами. */
(function () {
  'use strict';

  // Глаз «показать пароль»: переключает тип поля и подпись для диктора.
  document.querySelectorAll('[data-pw-eye]').forEach(function (eye) {
    var input = eye.parentNode.querySelector('input');
    if (!input) return;
    eye.hidden = false;
    eye.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      eye.setAttribute('aria-pressed', show ? 'true' : 'false');
      eye.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
      input.focus();
    });
  });

  // Код из письма: настоящее поле `code` прячется, вместо него — N ячеек.
  // Вставка всего кода заполняет все ячейки; после последней цифры форма уходит сама.
  document.querySelectorAll('input[data-code-cells]').forEach(function (field) {
    var count = parseInt(field.getAttribute('data-code-cells'), 10) || 6;
    var form = field.form;
    var row = document.createElement('div');
    row.className = 'au-cells';
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', 'Код из письма');
    var cells = [];
    for (var i = 0; i < count; i++) {
      var cell = document.createElement('input');
      cell.className = 'au-cell ym-disable-keys';
      cell.type = 'text';
      cell.inputMode = 'numeric';
      cell.maxLength = 1;
      cell.autocomplete = i === 0 ? 'one-time-code' : 'off';
      cell.setAttribute('aria-label', 'Цифра ' + (i + 1) + ' из ' + count);
      cells.push(cell);
      row.appendChild(cell);
    }
    field.type = 'hidden';
    field.removeAttribute('autofocus');
    field.parentNode.insertBefore(row, field);

    var sent = false;
    function sync() {
      var code = cells.map(function (c) { return c.value; }).join('');
      field.value = code;
      cells.forEach(function (c) { c.classList.toggle('is-filled', !!c.value); });
      if (code.length === count && /^\d+$/.test(code) && !sent) {
        sent = true;
        form.requestSubmit ? form.requestSubmit() : form.submit();
      }
    }
    function fill(from, digits) {
      for (var k = 0; k < digits.length && from + k < count; k++) cells[from + k].value = digits[k];
      var next = Math.min(from + digits.length, count - 1);
      cells[next].focus();
      sync();
    }
    cells.forEach(function (cell, index) {
      cell.addEventListener('input', function () {
        var digits = cell.value.replace(/\D/g, '');
        cell.value = '';
        if (digits) fill(index, digits.split('')); else sync();
      });
      cell.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' && !cell.value && index > 0) {
          cells[index - 1].value = '';
          cells[index - 1].focus();
          sync();
          e.preventDefault();
        } else if (e.key === 'ArrowLeft' && index > 0) {
          cells[index - 1].focus();
        } else if (e.key === 'ArrowRight' && index < count - 1) {
          cells[index + 1].focus();
        }
      });
      cell.addEventListener('paste', function (e) {
        var text = (e.clipboardData || window.clipboardData).getData('text') || '';
        var digits = text.replace(/\D/g, '').slice(0, count);
        if (!digits) return;
        e.preventDefault();
        fill(0, digits.split(''));
      });
      cell.addEventListener('focus', function () { cell.select(); });
    });
    cells[0].focus();
  });
})();

/* Онбординг /welcome/ — раунд 2 (макет docs/design/onboarding_r2/).
   ПРОГРЕССИВНОЕ УЛУЧШЕНИЕ: без скрипта каждый шаг — обычная страница и форма,
   плитка одиночного выбора — кнопка отправки. Скрипт добавляет:
   - автопереход после одиночного выбора через 280 мс (видна галочка);
   - смену шага без перезагрузки: запрос, анимация, адрес в history.pushState,
     «Назад» браузера работает;
   - «Дальше» выезжает после первого выбора; «Пока не решил» гасит остальные цели;
   - «Другое» разворачивает поле; подсказки городов и школ; экран сборки плана.
   При «уменьшить движение» всё то же, но без движения и задержек. */
(function () {
  'use strict';

  var main = document.getElementById('ob-main');
  if (!main) return;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var PICK_DELAY = reduced ? 0 : 280;
  var LEAVE_TIME = reduced ? 0 : 200;
  var busy = false;

  function later(fn, ms) { return ms ? setTimeout(fn, ms) : fn(); }
  function isStepUrl(url) {
    var path = new URL(url, location.href).pathname;
    return path.indexOf('/welcome/') === 0 && !/^\/welcome\/(build|plan)\//.test(path);
  }

  // ── Смена шага ────────────────────────────────────────────────────────
  function swap(html, url, dir, push) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var fresh = doc.getElementById('ob-main');
    if (!fresh) { location.assign(url); return; }
    var same = main.getAttribute('data-ob-step') === fresh.getAttribute('data-ob-step');
    var old = main.querySelector('.ob-q');
    if (old) old.classList.add(same ? 'ob-stage-out' : (dir === 'back' ? 'ob-leave-back' : 'ob-leave'));
    // Шапка остаётся на месте: полоса доезжает до нового значения сама (transition).
    var bar = document.querySelector('.ob-bar'), freshBar = doc.querySelector('.ob-bar');
    if (bar && freshBar) {
      bar.setAttribute('aria-valuenow', freshBar.getAttribute('aria-valuenow'));
      bar.firstElementChild.style.width = freshBar.firstElementChild.style.width;
    }
    var n = document.querySelector('.ob-bar-n'), freshN = doc.querySelector('.ob-bar-n');
    if (n && freshN) n.textContent = freshN.textContent;
    var back = document.querySelector('.ob-back'), freshBack = doc.querySelector('.ob-back');
    if (back && freshBack) back.outerHTML = freshBack.outerHTML;
    later(function () {
      // Разметка — ответ нашего же сервера на свой адрес (/welcome/, тот же источник,
      // шаблоны Django с экранированием): то же, что переход на страницу. Скрипты
      // в innerHTML не исполняются, а на шагах их и нет.
      main.innerHTML = fresh.innerHTML;
      main.setAttribute('data-ob-step', fresh.getAttribute('data-ob-step') || '');
      main.setAttribute('data-ob-stage', fresh.getAttribute('data-ob-stage') || '');
      var q = main.querySelector('.ob-q');
      if (q && !same && !reduced) q.classList.add(dir === 'back' ? 'ob-enter-back' : 'ob-enter');
      document.title = doc.title;
      if (push) history.pushState({ ob: 1 }, '', url);
      window.scrollTo(0, 0);
      init(main);
      var h = main.querySelector('.ob-h');
      if (h) h.focus({ preventScroll: true });
      busy = false;
    }, LEAVE_TIME);
  }

  function go(url, options, dir, push) {
    if (busy) return;
    busy = true;
    options = options || {};
    options.credentials = 'same-origin';
    options.headers = { 'X-Requested-With': 'fetch' };
    fetch(url, options).then(function (response) {
      var final = response.url || url;
      if (!response.ok && response.status !== 400) throw new Error(response.status);
      if (!isStepUrl(final)) { location.assign(final); return null; }
      return response.text().then(function (html) { swap(html, final, dir, push); });
    }).catch(function () {
      busy = false;
      if (options.method === 'POST' && options.form) options.form.submit();
      else location.assign(url);
    });
  }

  function submitForm(form, submitter) {
    var data;
    try { data = new FormData(form, submitter); } catch (e) {
      data = new FormData(form);
      if (submitter && submitter.name) data.append(submitter.name, submitter.value);
    }
    go(form.getAttribute('action') || location.href,
       { method: 'POST', body: data, form: form }, 'forward', true);
  }

  // Плитка одиночного выбора: галочка → через 280 мс дальше.
  document.addEventListener('click', function (e) {
    var tile = e.target.closest('[data-ob-auto] button[name][type="submit"]');
    if (!tile || busy) return;
    var form = tile.form;
    if (tile.hasAttribute('data-ob-other-toggle')) { e.preventDefault(); openOther(form, tile); return; }
    if (!tile.classList.contains('ob-t')) return;      // «Готово» у «Другое» — обычная отправка ниже
    e.preventDefault();
    form.querySelectorAll('button.ob-t[name="' + tile.name + '"]').forEach(function (other) {
      var on = other === tile;
      other.setAttribute('aria-pressed', on ? 'true' : 'false');
      other.classList.toggle(other.classList.contains('k-tile') ? 'k-tile--on' : 'is-on', on);
    });
    tile.classList.add('is-picking');
    later(function () { submitForm(form, tile); }, PICK_DELAY);
  });

  // Остальные формы шагов — без перезагрузки; уходящие со страницы (почта, группа) — как есть.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!main.contains(form) || form.hasAttribute('data-ob-leave') || form.hasAttribute('data-ob-plain')) return;
    var action = form.getAttribute('action');
    if (action && !isStepUrl(action)) return;
    e.preventDefault();
    if (!busy) submitForm(form, e.submitter);
  });

  // «Назад» в шапке и «Изменить» у класса.
  document.addEventListener('click', function (e) {
    var link = e.target.closest('[data-ob-back], [data-ob-link]');
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    go(link.href, { method: 'GET' }, link.hasAttribute('data-ob-back') ? 'back' : 'forward', true);
  });
  window.addEventListener('popstate', function () {
    if (isStepUrl(location.href)) go(location.href, { method: 'GET' }, 'back', false);
  });
  history.replaceState({ ob: 1 }, '', location.href);

  // ── «Другое» ──────────────────────────────────────────────────────────
  function openOther(form, pill) {
    form.querySelectorAll('button.ob-pill').forEach(function (other) {
      var on = other === pill;
      other.setAttribute('aria-pressed', on ? 'true' : 'false');
      other.classList.toggle('is-on', on);
    });
    var box = form.querySelector('[data-ob-other]');
    if (!box) return;
    box.classList.remove('is-folded');
    box.classList.add('is-opening');
    pill.setAttribute('aria-expanded', 'true');
    var input = box.querySelector('input');
    if (input) input.focus();
  }

  // ── Множественный выбор, «Дальше», поля ───────────────────────────────
  function initMulti(form) {
    var wrap = form.querySelector('[data-ob-next]');
    function sync(changed) {
      if (changed && changed.hasAttribute('data-ob-exclusive') && changed.checked) {
        form.querySelectorAll('input[type="checkbox"][name="' + changed.name + '"]').forEach(function (box) {
          if (box !== changed) box.checked = false;
        });
      } else if (changed && changed.checked) {
        var lone = form.querySelector('input[data-ob-exclusive][name="' + changed.name + '"]');
        if (lone) lone.checked = false;
      }
      form.querySelectorAll('label.ob-t').forEach(function (label) {
        var box = label.querySelector('input');
        if (!box) return;
        label.classList.toggle(label.classList.contains('k-tile') ? 'k-tile--on' : 'is-on', box.checked);
        if (box === changed) {
          label.classList.remove('is-picking'); void label.offsetWidth; label.classList.add('is-picking');
        }
      });
      if (!wrap) return;
      var groups = {}, ready = true;
      form.querySelectorAll('input[type="checkbox"]').forEach(function (box) {
        groups[box.name] = groups[box.name] || box.checked;
      });
      Object.keys(groups).forEach(function (name) { if (!groups[name]) ready = false; });
      var any = Object.keys(groups).some(function (name) { return groups[name]; });
      if (form.hasAttribute('data-ob-fields')) {
        form.querySelectorAll('input[required]').forEach(function (input) {
          if (!input.value.trim()) ready = false;
        });
        wrap.querySelector('button').disabled = !ready;
        return;
      }
      var hidden = wrap.classList.contains('is-hidden');
      if (any && hidden) { wrap.classList.remove('is-hidden'); wrap.classList.add('is-showing'); }
      if (!any) wrap.classList.add('is-hidden');
    }
    form.addEventListener('change', function (e) { sync(e.target); });
    form.addEventListener('input', function () { sync(null); });
    if (wrap && !form.hasAttribute('data-ob-fields') && !form.querySelector('input[type="checkbox"]:checked')) {
      wrap.classList.add('is-hidden');
    }
    sync(null);
  }

  // ── Подсказки городов и школ ──────────────────────────────────────────
  function initSuggest(box) {
    var input = box.querySelector('input');
    var url = box.getAttribute('data-ac');
    if (!input || !url) return;
    var list = document.createElement('ul');
    var listId = input.id + '-list';
    list.className = 'ob-dd';
    list.id = listId;
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    box.appendChild(list);
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', listId);
    var done = box.querySelector('.ob-ac-done');
    var cityInput = box.hasAttribute('data-ac-city') ? document.getElementById(box.getAttribute('data-ac-city')) : null;
    var timer = null, items = [], active = -1, seq = 0;

    function close() {
      list.hidden = true; box.classList.remove('is-open');
      input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant');
      active = -1;
    }
    function mark(text, query) {
      var span = document.createElement('span');
      var low = text.toLowerCase().replace(/ё/g, 'е'), q = query.toLowerCase().replace(/ё/g, 'е').trim();
      var at = q ? low.indexOf(q) : -1;
      if (at < 0) { span.textContent = text; return span; }
      span.appendChild(document.createTextNode(text.slice(0, at)));
      var m = document.createElement('mark');
      m.textContent = text.slice(at, at + q.length);
      span.appendChild(m);
      span.appendChild(document.createTextNode(text.slice(at + q.length)));
      return span;
    }
    function choose(value) {
      input.value = value;
      close();
      if (done) done.hidden = false;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      box.dispatchEvent(new CustomEvent('ob-chosen', { bubbles: true }));
    }
    function highlight(index) {
      var options = list.querySelectorAll('.ob-opt');
      options.forEach(function (opt, i) { opt.classList.toggle('is-hi', i === index); opt.setAttribute('aria-selected', i === index ? 'true' : 'false'); });
      active = index;
      if (options[index]) {
        input.setAttribute('aria-activedescendant', options[index].id);
        options[index].scrollIntoView({ block: 'nearest' });
      }
    }
    function render(query, results) {
      list.innerHTML = '';
      items = results.map(function (r) { return r.value; });
      results.forEach(function (r, i) {
        var li = document.createElement('li');
        li.className = 'ob-opt';
        li.id = listId + '-' + i;
        li.setAttribute('role', 'option');
        if (r.number) { var num = document.createElement('span'); num.className = 'ob-opt-num'; num.textContent = r.number; li.appendChild(num); }
        li.appendChild(mark(r.label || r.value, query));
        if (r.sub) { var sub = document.createElement('span'); sub.className = 'ob-opt-sub'; sub.textContent = r.sub; li.appendChild(sub); }
        li.addEventListener('mousedown', function (e) { e.preventDefault(); choose(r.value); });
        list.appendChild(li);
      });
      var own = document.createElement('li');
      own.className = 'ob-opt ob-opt--own';
      own.id = listId + '-own';
      own.setAttribute('role', 'option');
      own.textContent = 'Нет в списке – оставить «' + query.trim() + '»';
      own.addEventListener('mousedown', function (e) { e.preventDefault(); choose(query.trim()); });
      list.appendChild(own);
      items.push(query.trim());
      list.hidden = false; box.classList.add('is-open');
      input.setAttribute('aria-expanded', 'true');
      highlight(results.length ? 0 : -1);
    }
    function ask() {
      var query = input.value;
      if (!query.trim()) { close(); return; }
      var params = new URLSearchParams({ q: query });
      if (cityInput) params.set('city', cityInput.value);
      var mine = ++seq;
      fetch(url + '?' + params.toString(), { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.ok ? r.json() : { results: [] }; })
        .then(function (data) { if (mine === seq && document.activeElement === input) render(query, data.results || []); })
        .catch(function () {});
    }
    input.addEventListener('input', function (e) {
      if (e.isTrusted !== false && done) done.hidden = true;
      clearTimeout(timer);
      timer = setTimeout(ask, 150);
    });
    input.addEventListener('keydown', function (e) {
      if (list.hidden) return;
      var count = list.querySelectorAll('.ob-opt').length;
      if (e.key === 'ArrowDown') { e.preventDefault(); highlight((active + 1) % count); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight((active - 1 + count) % count); }
      else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); choose(items[active]); }
      else if (e.key === 'Escape') { close(); }
    });
    input.addEventListener('blur', function () { setTimeout(close, 120); });
    if (done && input.value.trim()) done.hidden = false;
  }

  function initSchool(form) {
    var school = form.querySelector('[data-ob-school]');
    var city = form.querySelector('#ob-city');
    if (!school || !city || city.value.trim()) return;
    school.hidden = true;
    function reveal() {
      if (!city.value.trim() || !school.hidden) return;
      school.hidden = false;
      school.classList.add('ob-anim-up');
    }
    form.addEventListener('ob-chosen', function (e) { if (e.target.contains(city)) { reveal(); var s = school.querySelector('input'); if (s) s.focus(); } });
    city.addEventListener('change', reveal);
  }

  // ── «Скопировать» код приглашения ─────────────────────────────────────
  function initCopy(root) {
    root.querySelectorAll('[data-copy]').forEach(function (button) {
      button.addEventListener('click', function () {
        var source = document.querySelector('[data-copy-src]');
        if (!source || !navigator.clipboard) return;
        navigator.clipboard.writeText(source.textContent.trim()).then(function () {
          button.textContent = 'Скопировано';
        });
      });
    });
  }

  // ── Сборка плана: строки по одной, потом заготовки карточек, потом дальше ──
  function initBuild(root) {
    var build = root.querySelector('[data-ob-build]');
    if (!build) return;
    var target = build.getAttribute('data-ob-target');
    if (reduced) { location.replace(target); return; }
    var lines = build.querySelectorAll('.ob-build-lines li').length;
    var shown = lines * 450 + 700;
    setTimeout(function () { build.classList.add('is-leaving'); }, shown);
    setTimeout(function () { location.replace(target); }, shown + 650);
  }

  function init(root) {
    root.querySelectorAll('form[data-ob-multi]').forEach(initMulti);
    root.querySelectorAll('.ob-ac[data-ac]').forEach(initSuggest);
    root.querySelectorAll('form.ob-school').forEach(initSchool);
    initCopy(root);
    initBuild(root);
  }
  init(main);
})();
