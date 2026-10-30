/* Подсказки города и школы: один скрипт на анкету (шаги «Город» и «Школа») и на профиль.
   Адреса — /welcome/api/cities/ и /welcome/api/schools/ (`problems/views_onboarding.py`),
   разметка — обёртка `.ob-ac[data-ac]` вокруг поля. Стили — `suggest.css`. Повторный вызов
   `init` на том же поле безопасен (метка `data-ac-ready`). */
(function () {
  'use strict';

  function initSuggest(box) {
    var input = box.querySelector('input');
    var url = box.getAttribute('data-ac');
    if (!input || !url || box.hasAttribute('data-ac-ready')) return;
    box.setAttribute('data-ac-ready', '');
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
    // Поле с открытым списком поднимается над соседями (раунд 3): иначе поле ниже
    // рисовалось поверх списка, и щелчок попадал в него, а не в вариант.
    var field = box.closest('.ob-field, .pf-field');
    var timer = null, items = [], rows = [], active = -1, seq = 0, pressing = false;

    function close() {
      list.hidden = true; box.classList.remove('is-open');
      if (field) field.classList.remove('is-ac-open');
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
    function choose(value, row) {
      input.value = value;
      close();
      if (done) done.hidden = false;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      // Выбрал школу, а «Город» пуст — город из записи школы.
      if (cityInput && row && row.city && !cityInput.value.trim()) {
        cityInput.value = row.city;
        var cityDone = cityInput.parentNode.querySelector('.ob-ac-done');
        if (cityDone) cityDone.hidden = false;
        cityInput.dispatchEvent(new Event('input', { bubbles: true }));
      }
      box.dispatchEvent(new CustomEvent('ob-chosen', { bubbles: true }));
    }
    function pick(index) { if (index >= 0 && index < items.length) choose(items[index], rows[index]); }
    // Список целиком в видимой части окна: на телефоне его не закрывают ни липкая
    // «Дальше», ни экранная клавиатура (visualViewport).
    function keepVisible() {
      var view = window.visualViewport ? window.visualViewport.height : window.innerHeight;
      var next = document.querySelector('.ob-next-wrap');
      var cover = next && getComputedStyle(next).position === 'sticky' ? next.offsetHeight : 0;
      var bottom = list.getBoundingClientRect().bottom;
      var top = input.getBoundingClientRect().top;
      var over = bottom - (view - cover - 8);
      if (over > 0) window.scrollBy(0, Math.min(over, Math.max(0, top - 8)));
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
        var main = document.createElement('span');
        main.className = 'ob-opt-main';
        var name = mark(r.label || r.value, query);
        name.className = 'ob-opt-name' + (r.full ? ' ob-opt-name--full' : '');
        main.appendChild(name);
        // Вторая строка серым: регион у города, город (и регион) у школы.
        if (r.sub) { var sub = document.createElement('span'); sub.className = 'ob-opt-sub'; sub.textContent = r.sub; main.appendChild(sub); }
        li.appendChild(main);
        li.setAttribute('data-i', i);
        list.appendChild(li);
      });
      rows = results.slice();
      var own = document.createElement('li');
      own.className = 'ob-opt ob-opt--own';
      own.id = listId + '-own';
      own.setAttribute('role', 'option');
      own.textContent = 'Нет в списке – оставить «' + query.trim() + '»';
      own.setAttribute('data-i', results.length);
      list.appendChild(own);
      items.push(query.trim());
      rows.push(null);
      list.hidden = false; box.classList.add('is-open');
      if (field) field.classList.add('is-ac-open');
      input.setAttribute('aria-expanded', 'true');
      highlight(0);
      keepVisible();
    }
    // Выбор — по pointerdown с preventDefault (раунд 3): поле не теряет фокус, и
    // `blur` не закрывает список раньше выбора. Мышь выбирает сразу; палец — по
    // отпусканию (click), чтобы длинный список можно было листать, не выбирая.
    function optionAt(target) { var li = target.closest ? target.closest('.ob-opt') : null; return li ? +li.getAttribute('data-i') : -1; }
    list.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      pressing = true;
      if (e.pointerType === 'mouse' && e.button === 0) pick(optionAt(e.target));
    });
    list.addEventListener('click', function (e) { if (!list.hidden) pick(optionAt(e.target)); });
    document.addEventListener('pointerup', function () { setTimeout(function () { pressing = false; }, 0); });
    document.addEventListener('pointercancel', function () { pressing = false; });
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
      // Своё `input` из choose() (оживить «Дальше», подставить город) — не ввод
      // человека: на него список не открываем (иначе он открывался заново с «Нет в
      // списке – оставить «Москва»» и накрывал поле ниже).
      if (e.isTrusted === false) return;
      if (done) done.hidden = true;
      clearTimeout(timer);
      timer = setTimeout(ask, 150);
    });
    input.addEventListener('keydown', function (e) {
      if (list.hidden) return;
      var count = list.querySelectorAll('.ob-opt').length;
      if (e.key === 'ArrowDown') { e.preventDefault(); highlight((active + 1) % count); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight((active - 1 + count) % count); }
      else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(active); }
      else if (e.key === 'Tab' && active >= 0) { pick(active); }
      else if (e.key === 'Escape') { close(); }
    });
    // Закрытие по уходу из поля — только если указатель не держит список.
    input.addEventListener('blur', function () {
      setTimeout(function () { if (!pressing && !list.matches(':hover')) close(); }, 120);
    });
    if (done && input.value.trim()) done.hidden = false;
  }

  function init(root) {
    (root || document).querySelectorAll('.ob-ac[data-ac]').forEach(initSuggest);
  }
  window.WecoSuggest = { init: init };
  init(document);
})();
