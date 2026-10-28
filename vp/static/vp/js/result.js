/* Экран результата ВП, владелец попытки: «Поделиться», разбор по заданиям (фильтры,
 * карта ответов, «Раскрыть все», адрес `#zN`) и «Дорешать вне зачёта» / «Показать ответ».
 * Строки разбора — `<details>`: раскрываются и без скрипта.
 *
 * ⚠️ «Дорешать» НИЧЕГО не сохраняет: ответ уходит в `practice_check`, а тот ни в базу, ни в
 * балл не пишет. Всё, что приходит с сервера, вставляется как ТЕКСТ (`textContent`), не как
 * разметка. Эталона на странице до проверки нет — его отдаёт только этот запрос. KaTeX из
 * общего конвейера (`catalog/base.html`) затем превращает уже вставленный текст в формулы —
 * разметку с сервера по-прежнему не вставляем (`trust: false`).
 */
(function () {
  'use strict';

  var csrfField = document.querySelector('input[name=csrfmiddlewaretoken]');
  var csrf = csrfField ? csrfField.value : '';
  var urlNode = document.getElementById('vp-practice-url');
  var practiceUrl = urlNode ? JSON.parse(urlNode.textContent) : '';
  var variantNode = document.querySelector('[data-variant]');
  var variantSlug = variantNode ? variantNode.getAttribute('data-variant') : '';

  /* Аналитика: `weco.track` шлёт события на существующий /api/track/. Нет `weco`
     (заблокирован) - молча ничего, кнопки от этого работать не перестают. */
  function track(name, props) {
    if (window.weco && window.weco.track) window.weco.track(name, props);
  }

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
      track('vp_share_click', { variant: variantSlug });
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
    if (kind === 'short_text' || kind === 'number') return form.elements.raw.value;
    if (kind === 'match') {
      var pairs = {};
      Array.prototype.forEach.call(form.querySelectorAll('select[data-key]'), function (select) {
        if (select.value !== '') pairs[select.getAttribute('data-key')] = Number(select.value);
      });
      return pairs;
    }
    var marked = Array.prototype.map.call(
      form.querySelectorAll('input[name=raw]:checked'), function (input) { return input.value; });
    return kind === 'multi' ? marked : (marked[0] || '');
  }

  function show(out, text, tone) {
    out.textContent = text;
    // Ответ может содержать формулы $…$: общий конвейер KaTeX из catalog/base.html.
    if (typeof window.renderMathIn === 'function') window.renderMathIn(out);
    out.className = 'vp-practice-out' + (tone ? ' is-' + tone : '');
  }

  /* Решение приходит с сервера текстом и вставляется как текст (не разметка), формулы — KaTeX. */
  function showSolution(box, text) {
    var sol = box.querySelector('[data-practice-sol]');
    if (!sol) return;
    sol.textContent = text ? 'Решение: ' + text : '';
    sol.hidden = !text;
    if (text && typeof window.renderMathIn === 'function') window.renderMathIn(sol);
  }

  function post(box, payload) {
    return fetch(practiceUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      credentials: 'same-origin',
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().then(function (data) { return { ok: response.ok, data: data }; });
    });
  }

  /* «Показать ответ»: эталон и решение без проверки. Тоже ничего не пишет. */
  function reveal(box) {
    var out = box.querySelector('[data-practice-out]');
    var item = Number(box.getAttribute('data-item'));
    show(out, 'Загружаем…', '');
    post(box, { item: item, reveal: true }).then(function (reply) {
      if (!reply.ok) { show(out, reply.data.error || 'Не удалось показать.', 'bad'); return; }
      track('vp_practice_reveal', { variant: variantSlug, item: item });
      show(out, 'Верный ответ: ' + reply.data.right, '');
      showSolution(box, reply.data.solution);
    }).catch(function () {
      show(out, 'Нет связи. Попробуйте ещё раз.', 'bad');
    });
  }

  function check(box) {
    var kind = box.getAttribute('data-kind');
    var out = box.querySelector('[data-practice-out]');
    var raw = value(box, kind);
    var empty = kind === 'match' ? !Object.keys(raw).length : (!raw || !raw.length);
    if (empty) { show(out, 'Сначала ответьте.', 'bad'); return; }
    show(out, 'Проверяем…', '');
    post(box, { item: Number(box.getAttribute('data-item')), raw: raw }).then(function (reply) {
      if (!reply.ok) { show(out, reply.data.error || 'Не удалось проверить.', 'bad'); return; }
      track('vp_practice_check', { variant: variantSlug, item: Number(box.getAttribute('data-item')) });
      if (reply.data.is_correct) show(out, 'Верно: ' + reply.data.right, 'ok');
      else show(out, 'Неверно. Верный ответ: ' + reply.data.right, 'bad');
      showSolution(box, reply.data.solution);
    }).catch(function () {
      show(out, 'Нет связи. Попробуйте ещё раз.', 'bad');
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-practice]'), function (box) {
    var open = box.querySelector('[data-practice-open]');
    var form = box.querySelector('[data-practice-form]');
    if (open) open.addEventListener('click', function () {
      var hidden = form.hidden;
      form.hidden = !hidden;
      open.setAttribute('aria-expanded', hidden ? 'true' : 'false');
      if (hidden) {
        var first = form.querySelector('input, select');
        if (first) first.focus();
      }
    });
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      check(box);
    });
    var revealButton = box.querySelector('[data-practice-reveal]');
    if (revealButton) revealButton.addEventListener('click', function () { reveal(box); });
  });
})();

/* ── Разбор по заданиям: фильтры, карта, «Раскрыть все», #zN ─────────────── */
(function () {
  'use strict';

  var rows = Array.prototype.slice.call(document.querySelectorAll('details.vp-zrow'));
  if (!rows.length) return;
  var filters = Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));
  var groups = Array.prototype.slice.call(document.querySelectorAll('[data-zgroup]'));
  var expand = document.querySelector('[data-expand-all]');
  var reduceMotion = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function matches(status, code) {
    if (code === 'all') return true;
    if (code === 'errors') return status === 'mid' || status === 'bad';
    return status === code;
  }

  function setFilter(code) {
    filters.forEach(function (button) {
      button.setAttribute('aria-pressed', button.getAttribute('data-filter') === code ? 'true' : 'false');
    });
    rows.forEach(function (row) { row.hidden = !matches(row.getAttribute('data-status'), code); });
    // Подпись «Задачи 17–18 · общее условие» — только при полном списке.
    groups.forEach(function (group) { group.hidden = code !== 'all'; });
  }

  function reveal(row) {
    setFilter('all');
    row.open = true;
    row.scrollIntoView({ block: 'start', behavior: reduceMotion ? 'auto' : 'smooth' });
    var summary = row.querySelector('summary');
    if (summary) summary.focus({ preventScroll: true });
  }

  filters.forEach(function (button) {
    button.addEventListener('click', function () { setFilter(button.getAttribute('data-filter')); });
  });

  /* «Показать эти 5 задач» на плашке «Ф» — фильтр «Формат» и прокрутка к таблице. */
  Array.prototype.forEach.call(document.querySelectorAll('[data-filter-go]'), function (button) {
    button.addEventListener('click', function () {
      setFilter(button.getAttribute('data-filter-go'));
      var table = document.getElementById('vp-tests');
      if (table) table.scrollIntoView({ block: 'start', behavior: reduceMotion ? 'auto' : 'smooth' });
    });
  });

  /* Квадрат карты и ссылки «9:» на плашке — фильтр «Все», строка раскрыта, прокрутка к ней. */
  document.addEventListener('click', function (event) {
    var link = event.target.closest ? event.target.closest('a[href^="#z"]') : null;
    if (!link) return;
    var row = document.getElementById(link.getAttribute('href').slice(1));
    if (!row || !row.classList.contains('vp-zrow')) return;
    event.preventDefault();
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, '', link.getAttribute('href'));
    }
    reveal(row);
  });

  if (expand) {
    expand.addEventListener('click', function () {
      var open = expand.getAttribute('aria-pressed') !== 'true';
      rows.forEach(function (row) { if (!row.hidden) row.open = open; });
      expand.setAttribute('aria-pressed', open ? 'true' : 'false');
      expand.textContent = open ? 'Свернуть все' : 'Раскрыть все';
    });
  }

  /* Адрес с #z13 при загрузке раскрывает и показывает 13-ю. */
  function fromHash() {
    var id = window.location.hash.slice(1);
    if (!/^z\d+$/.test(id)) return;
    var row = document.getElementById(id);
    if (row && row.classList.contains('vp-zrow')) reveal(row);
  }
  window.addEventListener('hashchange', fromHash);
  fromHash();
})();

/* ── Змейка 1 тура: чип открывает панель своего слова (без JS — все панели списком) ── */
(function () {
  'use strict';

  var chips = Array.prototype.slice.call(document.querySelectorAll('.vp-cw[data-word]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('[data-panel]'));
  if (!chips.length || !panels.length) return;

  function select(number) {
    chips.forEach(function (chip) {
      chip.setAttribute('aria-pressed', chip.getAttribute('data-word') === number ? 'true' : 'false');
    });
    panels.forEach(function (panel) { panel.hidden = panel.getAttribute('data-panel') !== number; });
  }

  chips.forEach(function (chip) {
    chip.addEventListener('click', function () { select(chip.getAttribute('data-word')); });
  });
  // Сначала — первое неверное слово (там есть что разобрать), иначе первое.
  var first = chips.filter(function (chip) { return chip.classList.contains('is-bad'); })[0] || chips[0];
  select(first.getAttribute('data-word'));
})();
