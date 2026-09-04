/* Окно «Все фильтры» каталога: живое обновление выдачи без закрытия окна.
 *
 * Решение владельца 04.09.2026: каждый клик в окне подгружает список и
 * счётчик за окном, адрес в строке браузера обновляется (ссылку можно
 * скопировать), окно остаётся открытым для следующего выбора.
 * https://app.notion.com/p/3d0b11c92bc1819ea747f0463024bd6a
 *
 * Как устроено:
 *   состояние (Set-ы и одиночные значения) → buildQuery() → GET
 *   api_filter_state с задержкой 150 мс и отменой прежнего запроса →
 *   подмена #ct-results и #ct-chips полученной разметкой, обновление
 *   всех [data-count], «Найдено», бейджа на «Все фильтры»,
 *   history.replaceState(url). Окно не перерисовывается целиком:
 *   меняются только aria-pressed и числа.
 *
 * ⚠️ ЧИСЛА СЧИТАЕТ СЕРВЕР (catalog/filters.py), здесь их только показывают.
 * ⚠️ ИМЕНА ПАРАМЕТРОВ — РОВНО КАК В catalog/filters.py::PARAM: их сверяет
 *    тест catalog/tests/test_catalog_modal.py, читая этот файл.
 * ⚠️ ИМЕНА ТЕГОВ КЛАДУТСЯ ЧЕРЕЗ textContent: таблица тегов засорена
 *    импортом, это чужой текст, разметку из него собирать нельзя.
 * ⚠️ БЕЗ ЭТОГО ФАЙЛА СТРАНИЦА РАБОТАЕТ: форма поиска и крестики чипов —
 *    серверные ссылки; скрипт лишь перехватывает их.
 */
(function () {
  'use strict';

  var stateEl = document.getElementById('ct-filter-state');
  var dlg = document.getElementById('ct-all');
  var openBtn = document.getElementById('ct-all-open');
  if (!stateEl || !dlg || !openBtn || typeof dlg.showModal !== 'function') return;
  var boot = JSON.parse(stateEl.textContent);

  var PARAM = {
    topics: 'topic', tags: 'tag', difficulties: 'difficulty', kind: 'type',
    test_type: 'test_type', character: 'character', sources: 'source',
    features: 'feature', has_solution: 'has_solution'
  };
  var LISTS = ['topics', 'tags', 'difficulties', 'sources', 'features'];
  var CHIP_LIMIT = 3;      /* больше тем или тегов в полосе — один чип «N тем ▾» */
  var DEBOUNCE = 150;      /* мс между кликом и запросом */
  var TAG_DEBOUNCE = 200;  /* мс между вводом и подсказкой тега */

  var state = {
    topics: new Set(boot.active.topics), tags: new Set(boot.active.tags),
    difficulties: new Set(boot.active.difficulties), sources: new Set(boot.active.sources),
    features: new Set(boot.active.features),
    kind: boot.active.kind || '', test_type: boot.active.test_type || '',
    character: boot.active.character || '', has_solution: !!boot.active.has_solution,
    q: boot.active.q || '', view: boot.view || 'rows',
    expandTopics: false, expandTags: false
  };

  /* ── Помощники ───────────────────────────────────────────────────── */
  function fmt(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }
  function plural(n, forms) {
    var a = n % 10, b = n % 100;
    return forms[(a === 1 && b !== 11) ? 0 : (a >= 2 && a <= 4 && (b < 10 || b >= 20)) ? 1 : 2];
  }
  function toggleSet(set, value) { if (set.has(value)) set.delete(value); else set.add(value); }
  function q(sel, root) { return (root || document).querySelector(sel); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* Адрес из состояния — те же имена, что печатает сервер. */
  function buildQuery(s) {
    var params = new URLSearchParams();
    if (s.q) params.append('q', s.q);
    if (s.view && s.view !== 'rows') params.append('view', s.view);
    Object.keys(PARAM).forEach(function (key) {
      var name = PARAM[key];
      if (LISTS.indexOf(key) >= 0) { s[key].forEach(function (v) { params.append(name, v); }); }
      else if (key === 'has_solution') { if (s.has_solution) params.append(name, '1'); }
      else if (s[key]) { params.append(name, s[key]); }
    });
    return params.toString();
  }
  function resetHref() {
    var params = new URLSearchParams();
    if (state.q) params.append('q', state.q);
    if (state.view && state.view !== 'rows') params.append('view', state.view);
    var query = params.toString();
    return boot.urls.page + (query ? '?' + query : '');
  }

  /* ── Запрос живого состояния ─────────────────────────────────────── */
  var timer = null, controller = null, seq = 0;
  function refresh() {
    syncDialog();
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (controller) controller.abort();
      controller = new AbortController();
      var query = buildQuery(state);
      var mine = ++seq;
      fetch(boot.urls.state + (query ? '?' + query : ''),
            { signal: controller.signal, headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { if (!r.ok) { throw new Error('HTTP ' + r.status); } return r.json(); })
        .then(function (data) { if (mine === seq) { applyResponse(data); } })
        .catch(function (err) { if (err && err.name !== 'AbortError') { showError(true); } });
    }, DEBOUNCE);
  }
  function applyResponse(data) {
    showError(false);
    var results = document.getElementById('ct-results');
    if (results) {
      var tpl = document.createElement('template');
      tpl.innerHTML = data.results_html.trim();
      if (tpl.content.firstElementChild) { results.replaceWith(tpl.content.firstElementChild); }
    }
    var chips = document.getElementById('ct-chips');
    if (chips) { chips.innerHTML = data.chips_html; collapseChips(); }
    updateCounts(data.counts || {});
    setFound(data.total);
    setBadge(data.selected_count);
    if (data.url) { history.replaceState(null, '', data.url); }
  }
  function showError(on) { var el = document.getElementById('ct-all-err'); if (el) { el.hidden = !on; } }

  function updateCounts(counts) {
    qa('[data-count]').forEach(function (el) {
      var parts = el.dataset.count.split(':');
      var group = parts[0], value = parts.slice(1).join(':');
      var n = group === 'has_solution' ? counts.has_solution : (counts[group] || {})[value];
      if (n === undefined) { return; }
      el.textContent = fmt(n);
      var owner = el.closest('[aria-pressed]');
      if (owner) { owner.classList.toggle('is-zero', n === 0); }
    });
    qa('[data-count-sum]').forEach(function (el) {
      var acc = el.closest('.fl-acc');
      var sum = 0;
      qa('[data-topic]', acc).forEach(function (tile) {
        var n = (counts.topic || {})[tile.dataset.topic];
        if (n !== undefined) { sum += n; }
      });
      el.textContent = fmt(sum);
    });
  }
  function setFound(total) {
    var found = document.getElementById('found-n'), show = document.getElementById('show-n'),
        word = document.getElementById('show-w');
    if (found) {
      found.textContent = fmt(total);
      found.classList.add('is-bump');
      setTimeout(function () { found.classList.remove('is-bump'); }, 300);
    }
    if (show) { show.textContent = fmt(total); }
    if (word) { word.textContent = plural(total, ['задачу', 'задачи', 'задач']); }
  }
  function setBadge(n) {
    var badge = q('.n', openBtn);
    if (n) {
      if (!badge) { badge = document.createElement('span'); badge.className = 'n'; openBtn.appendChild(document.createTextNode(' ')); openBtn.appendChild(badge); }
      badge.textContent = String(n);
    } else if (badge) { badge.previousSibling && badge.previousSibling.nodeType === 3 && badge.previousSibling.remove(); badge.remove(); }
    var reset = document.getElementById('strip-reset');
    if (reset) { reset.hidden = !n; reset.href = resetHref(); }
  }

  /* ── Полоса чипов: больше трёх тем или тегов — один чип «N тем ▾» ── */
  function collapseChips() {
    [['topic', 'expandTopics', ['тема', 'темы', 'тем']],
     ['tag', 'expandTags', ['тег', 'тега', 'тегов']]].forEach(function (spec) {
      var kind = spec[0], flag = spec[1], forms = spec[2];
      var chips = qa('#ct-chips .chip[data-chip="' + kind + '"]');
      if (chips.length <= CHIP_LIMIT) { return; }
      var expanded = state[flag];
      chips.forEach(function (c) { c.hidden = !expanded; });
      var more = document.createElement('button');
      more.type = 'button';
      more.className = 'chip chip--more' + (expanded ? ' is-open' : '');
      more.dataset.expand = kind;
      var label = document.createElement('b');
      label.textContent = expanded ? 'свернуть' : chips.length + ' ' + plural(chips.length, forms);
      more.appendChild(label);
      var caret = document.createElement('span');
      caret.className = 'caret';
      more.appendChild(caret);
      var anchor = expanded ? chips[chips.length - 1].nextSibling : chips[0];
      chips[0].parentNode.insertBefore(more, anchor);
    });
  }

  /* ── Синхронизация окна с состоянием ───────────────────────────────── */
  function pressed(sel, test) {
    qa(sel, dlg).forEach(function (b) { b.setAttribute('aria-pressed', String(test(b.dataset))); });
  }
  function syncDialog() {
    pressed('[data-topic]', function (d) { return state.topics.has(d.topic); });
    pressed('[data-tag]', function (d) { return state.tags.has(d.tag); });
    pressed('[data-src]', function (d) { return state.sources.has(d.src); });
    pressed('[data-diff]', function (d) { return state.difficulties.has(d.diff); });
    pressed('[data-feat]', function (d) { return state.features.has(d.feat); });
    pressed('[data-kind]', function (d) { return state.kind === d.kind; });
    pressed('[data-ttype]', function (d) { return state.test_type === d.ttype; });
    pressed('[data-char]', function (d) { return state.character === d.char; });
    var sub = document.getElementById('test-types');
    if (sub) { sub.classList.toggle('is-on', state.kind === 'test'); }
    var sw = document.getElementById('sol-switch');
    if (sw) { sw.checked = state.has_solution; }
    qa('.fl-acc', dlg).forEach(function (acc) {
      var n = qa('[data-topic]', acc).filter(function (t) { return state.topics.has(t.dataset.topic); }).length;
      var sel = q('[data-acc-sel]', acc);
      if (sel) { sel.textContent = n ? String(n) : ''; }
    });
    var counts = { topic: state.topics.size, tag: state.tags.size, difficulty: state.difficulties.size,
                   feature: state.features.size, source: state.sources.size,
                   kind: state.kind ? 1 : 0, character: state.character ? 1 : 0 };
    qa('[data-block-sel]', dlg).forEach(function (el) {
      var n = counts[el.dataset.blockSel] || 0;
      el.textContent = n ? 'выбрано ' + n : '';
    });
    qa('[data-clear]', dlg).forEach(function (b) {
      if (b.dataset.clear === 'all') { return; }
      b.hidden = !counts[b.dataset.clear];
    });
    renderTagGroups();
  }
  function setOpen(acc, open) {
    acc.classList.toggle('is-open', open);
    var head = q('.fl-acc-head', acc);
    if (head) { head.setAttribute('aria-expanded', String(open)); }
  }

  /* ── Теги: группы по выбранным темам + поиск по слову ─────────────── */
  var tagCache = {};
  var tagSearch = { q: '', tags: [] };
  var tagTimer = null;
  function topicMeta(id) {
    var tile = q('[data-topic="' + id + '"]', dlg);
    return { name: tile ? q('.fl-tile-l', tile).textContent : '',
             section: tile ? tile.dataset.section : 'tools' };
  }
  function loadTopicTags(id) {
    if (!tagCache[id]) {
      tagCache[id] = fetch(boot.urls.tags + '?topic=' + encodeURIComponent(id))
        .then(function (r) { return r.json(); })
        .then(function (d) { return d.tags || []; })
        .catch(function () { return []; });
    }
    return tagCache[id];
  }
  function pill(tag, on) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'fl-pill';
    b.dataset.tag = String(tag.id);
    b.setAttribute('aria-pressed', String(on));
    b.appendChild(document.createTextNode(tag.name));
    if (tag.count !== undefined && tag.count !== null) {
      var n = document.createElement('span');
      n.className = 'fl-tile-n';
      n.textContent = fmt(tag.count);
      b.appendChild(document.createTextNode(' '));
      b.appendChild(n);
    }
    return b;
  }
  function tagGroup(title, tags, section, chosenOnly) {
    var wrap = document.createElement('div');
    wrap.className = 'fl-tag-group';
    if (section) { wrap.style.setProperty('--gc', 'var(--map-g-' + section + ')'); }
    var head = document.createElement('div');
    head.className = 'fl-tag-group-h';
    if (section) { var dot = document.createElement('span'); dot.className = 'dot'; head.appendChild(dot); }
    head.appendChild(document.createTextNode(title));
    if (!chosenOnly) {
      var more = document.createElement('span');
      more.className = 'more';
      more.textContent = tags.length + ' ' + plural(tags.length, ['тег', 'тега', 'тегов']);
      head.appendChild(more);
    }
    wrap.appendChild(head);
    var pills = document.createElement('div');
    pills.className = 'fl-pills';
    tags.forEach(function (tag) { pills.appendChild(pill(tag, state.tags.has(String(tag.id)))); });
    wrap.appendChild(pills);
    return wrap;
  }
  var renderSeq = 0;
  function renderTagGroups() {
    var root = document.getElementById('tag-groups');
    var input = document.getElementById('tag-input');
    if (!root || !input) { return; }
    var needle = input.value.trim().toLowerCase();
    var topics = Array.from(state.topics);
    var mine = ++renderSeq;
    Promise.all(topics.map(loadTopicTags)).then(function (lists) {
      if (mine !== renderSeq) { return; }
      var shown = {};
      var groups = [];
      topics.forEach(function (id, i) {
        var list = lists[i].filter(function (t) { return !needle || t.name.toLowerCase().indexOf(needle) >= 0; });
        list.forEach(function (t) { shown[t.id] = true; });
        if (!list.length) { return; }            /* у темы без тегов группы нет */
        var meta = topicMeta(id);
        groups.push(tagGroup(meta.name, list, meta.section, false));
      });
      if (tagSearch.q && tagSearch.q === input.value.trim()) {
        var found = tagSearch.tags.filter(function (t) { return !shown[t.id]; });
        found.forEach(function (t) { shown[t.id] = true; });
        if (found.length) { groups.push(tagGroup('Найдено по слову', found, '', false)); }
      }
      /* Выбранные теги, которых нет ни в одной группе, — своей группой сверху:
         иначе выбранное было бы спрятано от того, кто его выбрал. */
      var chosen = qa('#ct-chips .chip[data-chip="tag"]').map(function (c) {
        var x = q('[data-remove]', c);
        return { id: x ? x.dataset.remove.split(':').slice(1).join(':') : '', name: c.firstChild ? c.firstChild.textContent : '' };
      }).filter(function (t) { return t.id && state.tags.has(t.id) && !shown[t.id]; });
      root.textContent = '';
      if (chosen.length) { root.appendChild(tagGroup('Выбранные теги', chosen, '', true)); }
      groups.forEach(function (g) { root.appendChild(g); });
      var empty = document.createElement('p');
      empty.className = 'fl-tag-empty';
      empty.id = 'tag-empty';
      if (!topics.length && !needle) {
        empty.textContent = 'Выберите тему слева: здесь появятся её теги. Или начните вводить название тега.';
        root.appendChild(empty);
      } else if (!groups.length) {
        empty.textContent = 'Ничего не нашлось: попробуйте другое слово.';
        root.appendChild(empty);
      }
    });
  }

  /* ── События ───────────────────────────────────────────────────────── */
  function clearGroup(key) {
    if (key === 'topic' || key === 'all') { state.topics.clear(); }
    if (key === 'tag' || key === 'all') { state.tags.clear(); }
    if (key === 'difficulty' || key === 'all') { state.difficulties.clear(); }
    if (key === 'source' || key === 'all') { state.sources.clear(); }
    if (key === 'feature' || key === 'all') { state.features.clear(); }
    if (key === 'kind' || key === 'all') { state.kind = ''; state.test_type = ''; }
    if (key === 'character' || key === 'all') { state.character = ''; }
    if (key === 'all') { state.has_solution = false; }
  }
  function removeChip(spec) {
    var i = spec.indexOf(':');
    var kind = i < 0 ? spec : spec.slice(0, i), value = i < 0 ? '' : spec.slice(i + 1);
    if (kind === 'topic') { state.topics.delete(value); }
    else if (kind === 'tag') { state.tags.delete(value); }
    else if (kind === 'source') { state.sources.delete(value); }
    else if (kind === 'feature') { state.features.delete(value); }
    else if (kind === 'difficulty') { state.difficulties.clear(); }
    else if (kind === 'kind') { state.kind = ''; state.test_type = ''; }
    else if (kind === 'character') { state.character = ''; }
    else if (kind === 'solution') { state.has_solution = false; }
  }

  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-acc-toggle],[data-topic],[data-tag],[data-src],[data-diff],[data-feat],[data-kind],[data-ttype],[data-char],[data-clear],[data-remove],[data-expand]');
    if (!t) { return; }
    var d = t.dataset;
    if (d.accToggle !== undefined) {
      var acc = t.closest('.fl-acc');
      setOpen(acc, !acc.classList.contains('is-open'));
      return;
    }
    if (d.expand) {
      if (d.expand === 'topic') { state.expandTopics = !state.expandTopics; } else { state.expandTags = !state.expandTags; }
      qa('#ct-chips .chip--more').forEach(function (m) { m.remove(); });
      qa('#ct-chips .chip').forEach(function (c) { c.hidden = false; });
      collapseChips();
      return;
    }
    if (d.topic !== undefined) { toggleSet(state.topics, d.topic); }
    else if (d.tag !== undefined) { toggleSet(state.tags, d.tag); }
    else if (d.src !== undefined) { toggleSet(state.sources, d.src); }
    else if (d.diff !== undefined) { toggleSet(state.difficulties, d.diff); }
    else if (d.feat !== undefined) { toggleSet(state.features, d.feat); }
    else if (d.kind !== undefined) { state.kind = state.kind === d.kind ? '' : d.kind; if (state.kind !== 'test') { state.test_type = ''; } }
    else if (d.ttype !== undefined) { state.test_type = state.test_type === d.ttype ? '' : d.ttype; if (state.test_type) { state.kind = 'test'; } }
    else if (d.char !== undefined) { state.character = state.character === d.char ? '' : d.char; }
    else if (d.clear !== undefined) { e.preventDefault(); clearGroup(d.clear); }
    else if (d.remove !== undefined) { e.preventDefault(); removeChip(d.remove); }
    refresh();
  });
  var sw = document.getElementById('sol-switch');
  if (sw) { sw.addEventListener('change', function () { state.has_solution = sw.checked; refresh(); }); }

  var tagInput = document.getElementById('tag-input');
  if (tagInput) {
    tagInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); } });
    tagInput.addEventListener('input', function () {
      var needle = tagInput.value.trim();
      clearTimeout(tagTimer);
      if (needle.length < 2) { tagSearch = { q: '', tags: [] }; renderTagGroups(); return; }
      renderTagGroups();
      tagTimer = setTimeout(function () {
        fetch(boot.urls.tags + '?q=' + encodeURIComponent(needle), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
          .then(function (r) { return r.json(); })
          .then(function (d) { tagSearch = { q: needle, tags: d.tags || [] }; renderTagGroups(); })
          .catch(function () {});
      }, TAG_DEBOUNCE);
    });
  }

  /* ── Открыть и закрыть ─────────────────────────────────────────────── */
  function openAll() {
    syncDialog();
    var accs = qa('.fl-acc', dlg);
    var anyOpen = false;
    accs.forEach(function (acc) {
      var open = qa('[data-topic]', acc).some(function (t) { return state.topics.has(t.dataset.topic); });
      setOpen(acc, open);
      anyOpen = anyOpen || open;
    });
    if (!anyOpen && accs.length) { setOpen(accs[0], true); }
    dlg.showModal();
  }
  openBtn.addEventListener('click', openAll);
  var closeBtn = document.getElementById('all-close'), showBtn = document.getElementById('all-show');
  if (closeBtn) { closeBtn.addEventListener('click', function () { dlg.close(); }); }
  if (showBtn) { showBtn.addEventListener('click', function () { dlg.close(); }); }
  dlg.addEventListener('click', function (e) { if (e.target === dlg) { dlg.close(); } });   /* клик по затемнению */

  /* Стартовая полоса: чипы пришли с сервера все — схлопнуть лишние. */
  collapseChips();
  syncDialog();
})();
