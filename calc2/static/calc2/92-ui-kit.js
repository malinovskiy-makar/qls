// Набор элементов «Условия» (редизайн 10.2026, фаза 5б): всплывающие окна,
// ползунки под карточками функций, «Как писать формулы», «Поделиться».
/* ---------------------------------------------------------------------
   Своей логики модели здесь нет. Ползунки строит пульт (88-params.js), окно
   цвета — makeColorPicker (60-overlays.js), ссылку — 91-session.js. Здесь
   только место на экране и обвязка окон по README макета, раздел 10:
   одно окно за раз; повторный щелчок по якорю, щелчок мимо и Esc закрывают;
   окно под якорем (+6 px), не ближе 8 px к краю, не помещается — над ним.
   --------------------------------------------------------------------- */

/* ── Всплывающее окно у якоря ─────────────────────────────────────────── */
let _pop = null;   // { el, anchor, onClose }

function placePop(el, anchor, opts) {
  const o = opts || {};
  const r = anchor.getBoundingClientRect();
  el.style.position = 'fixed';
  el.style.left = '0px'; el.style.top = '0px';
  const w = el.offsetWidth, h = el.offsetHeight;
  let top = (o.top != null) ? o.top : r.bottom + 6;
  el.style.maxHeight = '';
  if (o.top == null && top + h > window.innerHeight - 8) {
    // Сверху места больше — над якорем, иначе под ним с прокруткой внутри.
    if (r.top - h - 6 >= 8) top = r.top - h - 6;
    else el.style.maxHeight = Math.max(160, window.innerHeight - top - 8) + 'px';
  }
  let left = o.alignRight ? (r.right - w) : r.left;
  if (o.rightEdge != null) left = window.innerWidth - o.rightEdge - w;
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
  el.style.left = Math.round(left) + 'px';
  el.style.top = Math.round(top) + 'px';
}

function closePop() {
  if (!_pop) return;
  const p = _pop; _pop = null;
  p.el.classList.remove('open');
  if (p.anchor) p.anchor.setAttribute('aria-expanded', 'false');
  document.removeEventListener('pointerdown', onPopOutside, true);
  window.removeEventListener('keydown', onPopKey, true);
  window.removeEventListener('resize', closePop);
  if (typeof p.onClose === 'function') p.onClose();
  // Фокус назад на якорь (DESIGN.md 2.15), если он был в окне.
  if (p.anchor && p.el.contains(document.activeElement)) p.anchor.focus();
}
function onPopOutside(e) {
  if (!_pop) return;
  if (_pop.el.contains(e.target) || (_pop.anchor && _pop.anchor.contains(e.target))) return;
  // Окно цвета и выпадающий список, открытые ИЗ окна, живут в body: щелчок
  // по ним — не щелчок мимо.
  if (e.target.closest && e.target.closest('.cpick-menu, .sel-menu')) return;
  closePop();
}
function onPopKey(e) {
  if (e.key !== 'Escape' || !_pop) return;
  // Сначала закрывается вложенное (выпадающий список, окно цвета).
  if (document.querySelector('.sel-menu, .cpick-menu')) return;
  e.preventDefault(); e.stopPropagation();
  closePop();
}
function openPop(anchor, el, opts) {
  if (_pop && _pop.el === el) { closePop(); return; }
  closePop();
  if (typeof closeColorMenu === 'function') closeColorMenu();
  el.classList.add('open');
  if (anchor) anchor.setAttribute('aria-expanded', 'true');
  placePop(el, anchor, opts);
  _pop = { el, anchor, onClose: opts && opts.onClose };
  setTimeout(() => {
    document.addEventListener('pointerdown', onPopOutside, true);
    window.addEventListener('keydown', onPopKey, true);
    window.addEventListener('resize', closePop);
  }, 0);
  const f = el.querySelector('[autofocus], input, button, [tabindex]');
  if (f && !(opts && opts.noFocus)) f.focus({ preventScroll: true });
}

/* ── Меню «…» карточки функции ────────────────────────────────────────── */
function openFcMenu(anchor, menu) { openPop(anchor, menu, { alignRight: true, noFocus: true }); }
function closeFcMenu() { if (_pop && _pop.el.classList.contains('fc-menu')) closePop(); }

/* ── Ползунки под карточкой своей функции (README макета, 6.1) ─────────────
   Пульт строит их, как прежде, в «Параметрах»: сдвиги в #params-curves,
   буквы в #params-extra. Отсюда они переезжают под карточку своей кривой —
   сдвиг по id кривой, буква под первую карточку, в формуле которой она стоит
   (буквы общие на модель: одна «a» в двух формулах — один ползунок). Буквы
   из полей сцены (КПВ, макро) карточек в списке не имеют и остаются в
   «Параметрах».
   Чип помнит, из какой коробки он родом (data-pult-box) и каким по счёту там
   стоял (data-pult-idx): перед пересборкой списка кривых чипы возвращаются
   домой в том же порядке, а прибор паритета находит их по прежнему месту. */
function tagPultChip(chip, boxId, idx) {
  chip.dataset.pultBox = boxId;
  chip.dataset.pultIdx = String(idx);
}
function clearPultBox(boxId) {
  const box = document.getElementById(boxId);
  if (box) box.innerHTML = '';
  document.querySelectorAll('.pchip[data-pult-box="' + boxId + '"]').forEach(n => n.remove());
}
function pultChip(boxId, sel) {
  return document.querySelector('.pchip[data-pult-box="' + boxId + '"]' + (sel || ''));
}
/* ⚠️ ФОКУС ПЕРЕЖИВАЕТ ПЕРЕЕЗД ПОЛЗУНКА. Карточки пересобираются при каждой
   правке кривой, и ползунок под карточкой уезжает в пульт и обратно. Узел,
   вынутый из документа, теряет фокус: первое «→» с клавиатуры сдвигало
   кривую, а следующие уже двигали окно графика (прибор полной сверки:
   «→»×3 давало +1 вместо +3). Орган с фокусом запоминается при парковке и
   получает фокус обратно, когда встал на место. */
let _sliderFocus = null;
function parkCurveSliders() {
  const a = document.activeElement;
  if (a && a.closest && a.closest('.crow-sliders .pchip[data-pult-box]')) _sliderFocus = a;
  ['params-curves', 'params-extra'].forEach(boxId => {
    const box = document.getElementById(boxId);
    if (!box) return;
    const away = [...document.querySelectorAll('.crow-sliders .pchip[data-pult-box="' + boxId + '"]')];
    if (!away.length) return;
    const all = [...box.children, ...away].filter(n => n.dataset && n.dataset.pultIdx != null);
    all.sort((a, b) => (+a.dataset.pultIdx) - (+b.dataset.pultIdx));
    // Заголовки групп (без индекса) остаются на своих местах.
    all.forEach(n => box.appendChild(n));
  });
}
function placeCurveSliders() {
  const cards = [...document.querySelectorAll('#curve-list .fc-card[data-cid]')];
  if (!cards.length) return;
  const slotOf = (cid) => {
    const card = cards.find(c => c.dataset.cid === String(cid));
    return card ? card.querySelector(':scope > .crow-sliders') : null;
  };
  document.querySelectorAll('.pchip[data-pult-box="params-curves"][data-cid]').forEach(chip => {
    const slot = slotOf(chip.dataset.cid);
    if (slot && chip.parentElement !== slot) slot.appendChild(chip);
  });
  const exprOf = (cid) => {
    const c = STATE.curves.find(x => String(x.id) === String(cid));
    return c ? String(c.srcForm === 'QP' ? (c.srcExpr || c.expr) : c.expr || '') : '';
  };
  document.querySelectorAll('.pchip[data-pult-box="params-extra"][data-param]').forEach(chip => {
    const name = chip.dataset.param;
    const card = cards.find(card => {
      const ex = exprOf(card.dataset.cid);
      if (!ex) return false;
      try { return (typeof freeSymbols === 'function' ? freeSymbols(ex) : []).indexOf(name) >= 0; } catch (e) { return false; }
    });
    const slot = card ? card.querySelector(':scope > .crow-sliders') : null;
    if (slot && chip.parentElement !== slot) slot.appendChild(chip);
  });
  if (_sliderFocus) {
    const f = _sliderFocus; _sliderFocus = null;
    if (f.isConnected && document.activeElement !== f) f.focus({ preventScroll: true });
  }
  // Заголовок группы «Сдвиг кривых» / «Буквы из формул» без своих чипов не нужен.
  ['params-curves', 'params-extra'].forEach(boxId => {
    const box = document.getElementById(boxId);
    if (!box) return;
    const hasChips = !!box.querySelector('.pchip');
    box.querySelectorAll(':scope > .params-group-title').forEach(t => { t.hidden = !hasChips; });
  });
}

/* ── «Как писать формулы» (README макета, раздел 10) ──────────────────────
   Общие примеры из спецификации и, если активно поле с ролью, примеры по
   роли из FORMULA_EXAMPLES (80-ui.js, COVERAGE Р25). */
/* Пример пишется так, как его набирают (это справка по записи), поэтому
   строкой, а не набранной формулой: «Q^2/100» должно быть видно как «^». */
const HOW_TO_ROWS = [
  ['100 − 2Q', 'основная форма: цена от количества, P = f(Q)'],
  ['120 − 2P', 'количество от цены, Q = f(P): пересчитаем сами'],
  ['Qd = 120 − 2P', 'можно с левой частью, как в условии'],
  ['Q^2/100 + 5', 'степень через ^'],
  ['sqrt(Q), ln(Q)', 'корень, логарифм'],
  ['min(Q, 50)', 'минимум и максимум двух функций'],
  ['100 − aQ', 'буква станет ползунком'],
  ['0,5Q', 'дробь через запятую или точку'],
  ['Q < 20 ? 100 − 2Q : 80 − Q', 'выбор по условию; проще кнопкой «…» → «Задать кусками»'],
];
let _howToRole = null;   // последнее поле формулы с ролью, где стоял курсор
function howToBuild(el) {
  el.innerHTML = '';
  const h = document.createElement('div');
  h.className = 'pop-title'; h.textContent = 'Как писать формулы';
  el.appendChild(h);
  const tbl = document.createElement('div');
  tbl.className = 'howto-rows';
  const row = (ex, note) => {
    const r = document.createElement('div'); r.className = 'howto-row';
    const m = document.createElement('span'); m.className = 'howto-ex';
    m.textContent = ex;
    const n = document.createElement('span'); n.className = 'howto-note'; n.textContent = note;
    r.append(m, n); tbl.appendChild(r);
  };
  HOW_TO_ROWS.forEach(([a, b]) => row(a, b));
  el.appendChild(tbl);
  const set = _howToRole && typeof FORMULA_EXAMPLES !== 'undefined' ? FORMULA_EXAMPLES[_howToRole] : null;
  if (set && set.items) {
    const sub = document.createElement('div');
    sub.className = 'howto-sub';
    sub.textContent = 'Примеры для этого поля';
    el.appendChild(sub);
    const t2 = document.createElement('div'); t2.className = 'howto-rows';
    set.items.forEach(([a, b]) => {
      const r = document.createElement('div'); r.className = 'howto-row';
      const m = document.createElement('span'); m.className = 'howto-ex';
      if (typeof renderTex === 'function') renderTex(m, a); else m.textContent = a;
      const n = document.createElement('span'); n.className = 'howto-note'; n.textContent = b;
      r.append(m, n); t2.appendChild(r);
    });
    el.appendChild(t2);
  }
  const foot = document.createElement('div');
  foot.className = 'howto-foot';
  foot.textContent = 'Умножение можно не писать: 2Q = 2·Q. Ошибка в записи не ломает график: он держит последнюю верную запись, пока вы правите.';
  el.appendChild(foot);
}

/* ── «Поделиться» (README макета, раздел 10) ──────────────────────────────
   Ссылку собирает 91-session.js (shareLinkOf). Галочка «Сначала сам»
   дописывает self=1 (режим — фаза 9). */
async function shareFill(el) {
  const inp = el.querySelector('#share-url');
  const self = el.querySelector('#share-self');
  let link = '';
  try { link = await shareLinkOf(); } catch (e) { link = ''; }
  if (link && self && self.checked) link += (link.indexOf('#') >= 0 ? '&' : '#') + 'self=1';
  if (inp) { inp.value = link || 'Не получилось собрать ссылку'; }
  return link;
}

function wireUiKit() {
  // «Как писать формулы» в шапке «Условия».
  const hb = document.getElementById('btn-howto');
  const hp = document.getElementById('howto-pop');
  if (hb && hp) {
    hb.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!hp.classList.contains('open')) howToBuild(hp);
      openPop(hb, hp, { noFocus: false });
    });
  }
  // Последнее поле формулы, где стоял курсор: его роль даёт примеры.
  document.addEventListener('focusin', (e) => {
    const card = e.target.closest && e.target.closest('.fc-card[data-cid]');
    if (!card) return;
    const c = STATE.curves.find(x => String(x.id) === card.dataset.cid);
    const map = { demand: 'DEMAND', supply: 'SUPPLY', mc: 'MC', atc: 'ATC' };
    _howToRole = c ? (map[c.role] || (c.srcForm === 'QP' ? 'QP' : 'PQ')) : null;
  });
  // «Поделиться»: окно со ссылкой и «Копировать».
  const sb = document.getElementById('btn-share');
  const sp = document.getElementById('share-pop');
  if (sb && sp) {
    sb.addEventListener('click', async (e) => {
      e.stopPropagation();
      /* Телефон (COVERAGE, раздел 8; README 3): кнопка сразу копирует ссылку,
         окна с галочкой «Сначала сам» на телефоне нет. */
      if (window.matchMedia && window.matchMedia('(max-width: 759px)').matches) {
        const self = sp.querySelector('#share-self'); if (self) self.checked = false;
        const link = await shareFill(sp);
        let ok = false;
        try { await navigator.clipboard.writeText(link); ok = !!link; } catch (err) { ok = false; }
        toast(ok ? 'Ссылка скопирована' : 'Не получилось скопировать ссылку');
        return;
      }
      if (sp.classList.contains('open')) { closePop(); return; }
      openPop(sb, sp, { alignRight: true, noFocus: true, onClose: () => sb.classList.remove('is-open') });
      sb.classList.add('is-open');
      await shareFill(sp);
      const inp = sp.querySelector('#share-url');
      if (inp) { inp.focus({ preventScroll: true }); inp.select(); }
    });
    const self = sp.querySelector('#share-self');
    if (self) self.addEventListener('change', () => shareFill(sp));
    const copy = sp.querySelector('#share-copy');
    if (copy) copy.addEventListener('click', async () => {
      const link = await shareFill(sp);
      let ok = false;
      try { await navigator.clipboard.writeText(link); ok = true; } catch (e) { ok = false; }
      closePop();
      toast(ok ? 'Ссылка скопирована' : 'Не получилось скопировать: выделите ссылку и скопируйте сами');
    });
  }
}

/* ── «Показать на графике» (README макета, 6.4) ───────────────────────────
   Галочки CS и PS показываются, когда модель эту заливку рисует (метка
   data-legend на холсте); снятая галочка гасит заливку, а строка остаётся,
   иначе вернуть заливку было бы нечем. Галочки областей
   монополии живут здесь же; их видимость по-прежнему решает сцена монополии
   (display у #mono-areas-chk), а в монополии общих CS и PS нет. */
const SHOW_SEEN = {};
function syncShowSection() {
  const sec = document.getElementById('sec-show');
  const list = document.getElementById('show-list');
  if (!sec || !list) return;
  const mono = document.getElementById('mono-areas-chk');
  if (mono && mono.parentElement !== list) list.appendChild(mono);
  const monoOn = !!(mono && mono.style.display !== 'none' && STATE.market === 'monopoly');
  if (mono && !monoOn && mono.style.display !== 'none') mono.style.display = 'none';
  const key = STATE.sceneKey || '';
  const seen = SHOW_SEEN[key] || (SHOW_SEEN[key] = {});
  const colors = {};
  if (typeof svg !== 'undefined' && svg) {
    svg.selectAll('[data-legend]').each(function () {
      const raw = this.getAttribute('data-legend');
      const full = (typeof areaKey === 'function') ? areaKey(raw) : raw;
      const k = (typeof areaShort === 'function') ? areaShort(full) : full;   // «Излишек потребителя (CS)» → «CS»
      if (!k || colors[k]) return;
      colors[k] = this.getAttribute('fill') || '';
    });
  }
  ['CS', 'PS', 'VC'].forEach(k => { if (colors[k]) seen[k] = colors[k]; });
  /* С 14.10 (этап Г, ADR 0152) строки CS и PS живут в «Виде графика» и видны, только если модель
     рисует ИМЕННО их закраску (полное имя): у рынка труда «Излишек фирм» короче тоже «CS», но
     сцена труда признаки showCS / showPS не читает — галочки были мёртвыми. Там строки
     закрасок общие (STATE.areaHidden). */
  const full = {};
  if (typeof svg !== 'undefined' && svg) svg.selectAll('[data-legend]').each(function () { full[areaKey(this.getAttribute('data-legend'))] = 1; });
  if (Array.isArray(_vgDrawnKeys)) _vgDrawnKeys.forEach(k => { full[k] = 1; });
  const FULL = { CS: 'Излишек потребителя (CS)', PS: 'Излишек производителя (PS)' };
  const marketScene = !/^labor/.test(String(STATE.sceneKey || ''));
  const rows = [['show-cs-row', 'chk-cs', 'CS', 'showCS'], ['show-ps-row', 'chk-ps', 'PS', 'showPS']];
  let any = false;
  rows.forEach(([rowId, chkId, k, st]) => {
    const row = document.getElementById(rowId), chk = document.getElementById(chkId);
    if (!row) return;
    /* Строка видна, если заливка нарисована СЕЙЧАС или человек её выключил
       (флаг снят — иначе включить обратно было бы нечем). Это функция состояния
       и картинки, а не пути: после отмены и после перезагрузки набор строк тот
       же (прибор session_probe). Память SHOW_SEEN хранит только цвет образца. */
    const on = !monoOn && marketScene && (!!full[FULL[k]] || STATE[st] === false);
    row.hidden = !on;
    if (on) any = true;
    if (chk && document.activeElement !== chk) chk.checked = !!STATE[st];
  });
  if (monoOn) any = true;
  // Образец каждой строки — тем же цветом, что заливка на холсте.
  list.querySelectorAll('.show-sw[data-area]').forEach(sw => {
    const c = seen[sw.dataset.area] || colors[sw.dataset.area];
    if (c) sw.style.background = c;
  });
  const want = any ? '' : 'none';
  if (sec.style.display !== want) sec.style.display = want;
}

/* ═══ «НА ГРАФИКЕ» В ОКНЕ «ВИД ГРАФИКА» (тихие панели 14.10, этап Г; решение владельца «левая панель
   только про условие, всё, что меняет одну картинку, — в «Вид»», Notion …8142…; ADR 0152) ═══
   Галочки, которые меняют только картинку, переезжают сюда УЗЛАМИ: тот же id, тот же ключ STATE,
   тот же обработчик (88-params.js) — история, ссылка, автосохранение и «Вид по умолчанию» видят их
   как раньше. На старом месте остаётся заглушка .vg-home: строка в «Виде» видна ровно тогда, когда
   логика сцены показала бы галочку на старом месте (hidden, display: none, scoped-off предков).
   Условия (меняют числа «Ответа») остаются в «Условии»: chk-secant, chk-bundle-*, chk-elast-s,
   chk-msb, chk-msc, ext-pigou, chk-lr, chk-labmin, ma-fx-fixed, ineq-redist, «Ставка на оси до». */
// [id узла, группа, имена закрасок, которые прячет его СОБСТВЕННЫЙ признак]
const VG_MOVE = [
  ['chk-tp', 'curves'], ['chk-mp', 'curves'], ['chk-ap', 'curves'],
  ['chk-mc', 'curves'], ['chk-atc', 'curves'], ['chk-avc', 'curves'], ['chk-afc', 'curves'],
  ['chk-tc', 'curves'], ['chk-vc', 'curves'], ['chk-fc', 'curves'],
  ['chk-convex', 'curves'], ['chk-inflect', 'curves'], ['chk-iso-fan', 'curves'], ['chk-cons-fan', 'curves'],
  ['plv-tc', 'curves'], ['tanD', 'curves'], ['mm-name', 'curves'], ['inp-ppfsum-name', 'curves'],
  ['chk-cs', 'areas', ['Излишек потребителя (CS)']], ['chk-ps', 'areas', ['Излишек производителя (PS)']],
  ['chk-mono-cs', 'areas', ['Излишек потребителя (CS)']], ['chk-mono-ps', 'areas', ['Излишек производителя (TR - VC)']],
  ['chk-mono-vc', 'areas', ['Переменные издержки (VC)']],
  ['chk-nat-profit', 'areas'], ['chk-nat-loss', 'areas'],
  ['chk-open-money', 'areas', ['Доход бюджета', 'Рента квоты']], ['chk-open-dwl', 'areas', ['Потери общества (DWL)']],
  ['chk-ppf-in', 'areas', ['Достижимые наборы']], ['chk-ppf-out', 'areas', ['Недостижимые наборы']],
  ['chk-lr-area', 'areas', ['Прибыль фирмы', 'Убыток фирмы']],
  ['chk-ghost', 'more'], ['chk-lab-ghost', 'more'],
];
const _vgRows = [];
let _vgDrawnKeys = [];
function vgList(kind) { return document.querySelector('#wrench-pop .vg-list[data-vg="' + kind + '"]'); }
/* Узел, который переезжает: строка галочки, тумблер с его сегментом, поле подписи, строка цвета. */
function vgNodeOf(id) {
  if (id === 'tanD') { const c = document.querySelector('#tools-panel input[data-col="tanD"], #tools-panel [data-col="tanD"]'); return c ? [c.closest('label') || c] : null; }
  const el = document.getElementById(id);
  if (!el) return null;
  if (id === 'plv-tc') { const seg = el.closest('.seg'); return seg ? [seg._tgl, seg].filter(Boolean) : null; }
  if (el.type === 'checkbox') return [el.closest('label') || el];
  return [el.closest('.field') || el];
}
function vgSetup() {
  const pop = document.getElementById('wrench-pop');
  if (!pop || pop._vg) return;
  pop._vg = true;
  /* ⚠️ ТУМБЛЕРЫ БЕЗ id ФОРМА ПОМНИТ ПО ПОРЯДКУ (@toggles, 89-model-state.js). Переезд тумблера
     заводов в «Вид» сдвинул бы номера соседей в старых ссылках и сохранениях: штампуем порядок
     ДО переезда, форма читает и пишет тумблеры по этому штампу. */
  [...document.querySelectorAll('.app .tgl-sw')].forEach((t, i) => { if (t._tgIdx == null) t._tgIdx = i; });
  VG_MOVE.forEach(([id, kind, covers]) => {
    const nodes = vgNodeOf(id);
    const list = vgList(kind);
    if (!nodes || !nodes.length || !list) return;
    const home = document.createElement('span');
    home.className = 'vg-home'; home.hidden = true;
    nodes[0].before(home);
    const row = document.createElement('div');
    row.className = 'vg-row' + (kind === 'areas' ? ' vg-area' : '');
    home._vgRow = row;   // заглушка знает свою строку: по ней приборы находят органы в прежнем порядке
    nodes.forEach(n => row.appendChild(n));
    list.appendChild(row);
    const rec = { id, kind, row, home, node: nodes[0], covers: covers || [] };
    // Образец закраски — кнопка цвета (STATE.areaColor): цвета закрасок уходят сюда из панели точек.
    if (kind === 'areas' && covers && covers.length && typeof makeColorPicker === 'function') {
      const chk = document.getElementById(id);
      const pick = makeColorPicker(COL.ink, (hex) => { covers.forEach(k => { if (hex) STATE.areaColor[k] = hex; else delete STATE.areaColor[k]; }); redrawAll(); },
        tipName('Цвет: ' + covers[0]));
      pick.classList.add('vg-pick');
      if (chk) chk.after(pick);
      nodes[0].querySelectorAll('.show-sw, span.swatch').forEach(x => x.classList.add('vg-old-sw'));
      rec.pick = pick;
    }
    _vgRows.push(rec);
  });
}
// Видна ли заглушка на старом месте глазами логики сцены (не по раскладке).
function vgHomeShown(home) {
  const root = document.getElementById('tools-panel');
  for (let n = home.parentElement; n && n !== root && n !== document.body; n = n.parentElement) {
    if (n.hidden || (n.style && n.style.display === 'none') || n.classList.contains('scoped-off')) return false;
  }
  return true;
}
const AREA_ID = (k) => 'vg-area-' + String(k).split('').reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7).toString(36);
function syncOnChart() {
  const pop = document.getElementById('wrench-pop');
  const box = pop && pop.querySelector('.vg-onchart');
  if (!box) return;
  const covered = new Set();
  _vgRows.forEach(r => {
    const self = r.node && !(r.node.hidden || (r.node.style && r.node.style.display === 'none'));
    const on = vgHomeShown(r.home) && self;
    if (r.row.hidden === on) r.row.hidden = !on;
    if (on) r.covers.forEach(k => covered.add(k));
    if (on && r.pick && r.covers.length) {
      const c = (STATE.areaColor || {})[r.covers[0]];
      const drawn = document.querySelector('#chart [data-legend="' + CSS.escape(r.covers[0]) + '"]');
      const col = c || (drawn && drawn.getAttribute('fill'));
      const b = r.pick.querySelector('.cpick-btn');
      if (b && col && b.style.background !== col) b.style.background = col;
    }
  });
  // Кривые-производные «Сложения спросов» (рыночные D и S): их карточки собираются заново на каждой
  // сборке списка кривых и сразу переезжают сюда (у них нет поля формулы — «считается по группам»).
  const curves = vgList('curves');
  const fresh = [...document.querySelectorAll('#curve-list > .fc-card')].filter(card => card.querySelector('.crow-auto'));
  // Список кривых собран заново — прежние перенесённые карточки устарели: на их место встают свежие.
  if (fresh.length) {
    [...curves.querySelectorAll(':scope > .vg-deriv')].forEach(r => r.remove());
    document.querySelectorAll('#curve-list > .vg-home').forEach(h => h.remove());
  }
  fresh.forEach(card => {
    const row = document.createElement('div');
    row.className = 'vg-row vg-deriv';
    const home = document.createElement('span');
    home.className = 'vg-home'; home.hidden = true; home._vgRow = row;
    card.before(home);
    row.appendChild(card);
    curves.appendChild(row);
  });
  [...curves.querySelectorAll(':scope > .vg-deriv')].forEach(r => {
    const card = r.firstElementChild;
    const cid = card && card.dataset.cid;
    const alive = cid && (STATE.curves || []).some(c => String(c.id) === cid);
    if (!alive) r.remove();
  });
  // Закраски без своего признака — общий STATE.areaHidden (строка остаётся и у спрятанной).
  const own = new Set((STATE.areaCalcList || []).map(r => areaKey(r.label)));
  const keys = [];
  [..._vgDrawnKeys, ...(STATE.areaHidden || [])].forEach(k => { if (k && !covered.has(k) && !own.has(k) && keys.indexOf(k) < 0) keys.push(k); });
  const areas = vgList('areas');
  const have = new Map([...areas.querySelectorAll(':scope > .vg-gen')].map(r => [r.dataset.key, r]));
  have.forEach((r, k) => { if (keys.indexOf(k) < 0) r.remove(); });
  keys.forEach(k => {
    let r = have.get(k);
    if (!r) {
      r = document.createElement('div');
      r.className = 'vg-row vg-area vg-gen';
      r.dataset.key = k;
      const lab = document.createElement('label'); lab.className = 'chk show-row';
      const chk = document.createElement('input'); chk.type = 'checkbox'; chk.id = AREA_ID(k);
      chk.addEventListener('change', () => {
        const set = new Set(STATE.areaHidden || []);
        if (chk.checked) set.delete(k); else set.add(k);
        STATE.areaHidden = [...set];
        redrawAll();
      });
      const pick = makeColorPicker(COL.ink, (hex) => { if (hex) STATE.areaColor[k] = hex; else delete STATE.areaColor[k]; redrawAll(); }, tipName('Цвет: ' + k));
      pick.classList.add('vg-pick');
      const nm = document.createElement('span'); nm.className = 'show-name'; nm.textContent = String(k).replace(/\s*\([^)]{1,12}\)\s*$/, '');
      const nt = document.createElement('span'); nt.className = 'show-not';
      const short = areaShort(k);
      if (short !== k && typeof paintNotation === 'function') paintNotation(nt, short); else nt.textContent = '';
      lab.append(chk, pick, nm, nt);
      r.appendChild(lab);
      r._chk = chk; r._pick = pick;
    }
    areas.appendChild(r);
    const hidden = (STATE.areaHidden || []).indexOf(k) >= 0;
    if (r._chk.checked === hidden) r._chk.checked = !hidden;
    const drawn = document.querySelector('#chart [data-legend="' + CSS.escape(k) + '"]');
    const col = (STATE.areaColor || {})[k] || (drawn && drawn.getAttribute('fill')) || r._lastCol;
    if (col) { r._lastCol = col; const b = r._pick.querySelector('.cpick-btn'); if (b && b.style.background !== col) b.style.background = col; }
  });
  // Подзаголовки и сама группа — по видимым строкам.
  const vis = (kind) => [...vgList(kind).children].some(x => !x.hidden);
  const c = vis('curves'), a = vis('areas'), m = vis('more');
  box.querySelectorAll('.vg-sub').forEach(h => { h.hidden = !(h.dataset.vg === 'curves' ? c && (a || m) : a && (c || m)); });
  box.hidden = !(c || a || m);
  hideEmptyGroupTitles();
  if (typeof scSync === 'function') scSync();   // карточки полей сцен (сессия 5)
}
/* Заголовок группы «Условия», под которым не осталось ни одного видимого органа, не показывается (правка А3 по
   приёмке 14.10, сессия 5): галочки картинки уехали в «Вид» (ADR 0152), а «Средние и предельные затраты», «Полные
   затраты» в «Издержках фирмы» и «Области» в КПВ остались висеть пустыми. Решение по содержимому, для всех
   моделей: группа заголовка — соседи до следующего такого же заголовка (у h3.sec-head — его раздел); «видно» —
   по вычисленному стилю до «Условия» (колонка бывает спрятана классом, прямоугольников тогда нет). Класс на узле
   без id: вид, не модель. */
const GROUP_TITLE_SEL = '.curve-group-title, .vsub, .section-title, .sc-sec';
const ORGAN_SEL = 'input:not([type=hidden]), button, select, textarea, math-field, .edval, .tgl-sw, [role=switch]';
function hideEmptyGroupTitles() {
  const tp = document.getElementById('tools-panel');
  if (!tp) return;
  const shown = (el) => {
    for (let n = el; n && n !== tp; n = n.parentElement) {
      if (n.hidden) return false;
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    }
    return true;
  };
  const hasOrgan = (nodes) => nodes.some(n => n.nodeType === 1 && ((n.matches(ORGAN_SEL) && shown(n)) || [...n.querySelectorAll(ORGAN_SEL)].some(shown)));
  tp.querySelectorAll(GROUP_TITLE_SEL).forEach(t => {
    if (t.closest('.vg-onchart')) return;
    const group = [];
    for (let n = t.nextElementSibling; n && !n.matches(GROUP_TITLE_SEL); n = n.nextElementSibling) group.push(n);
    t.classList.toggle('grp-empty', !hasOrgan(group));
  });
}
/* ═══ КАРТОЧКИ ФУНКЦИЙ ДЛЯ «ГОЛЫХ» ПОЛЕЙ СЦЕН (тихие панели, сессия 5; README пакета 4, 8; ADR 0153) ═══
   Поле формулы сцены (КПВ, торговля, фирма, монополия) получает тот же вид, что карточка кривой из списка
   (renderCurveList, 80-ui.js): верхний ряд — точка цвета, обозначение KaTeX, имя, «⋯»; ниже поле с приставкой.
   Обёртка — НА МЕСТЕ: узел .field сам становится карточкой, поле, его id, обработчики, оснастка
   (equipFormulaField, fitFormulaField), живая запись (liveFormulaTexts) и видимость от сцен — прежние;
   переносятся только узлы (подпись поля на графике — в «⋯», кнопка цвета — в верхний ряд), новых id нет.
   Глаз ставится только там, где у кривой есть видимость (у полей сцен её нет: видимость кривых, которые
   модель строит сама, — в «Виде», решение …8142…); «⋯» — только если в меню есть пункты; точка-кнопка — если у
   кривой свой выбор цвета (swatch-slot), иначе простой значок цвета роли. */
function wrapFieldInCard(field, o) {
  if (!field || field._scCard) return field ? field._scCard : null;
  const inp = document.getElementById(o.input);
  /* Вариант «число» (сессия 6, В1: LRAS «Потенциальный выпуск» — поле числа, не формула): в строку карточки встаёт
     САМО поле числа (тот же узел и id), без кнопки клавиатуры. */
  const fRow = inp && (o.number ? inp : inp.closest('.f-row'));
  if (!inp || !fRow || !field.contains(fRow)) return null;
  const lab = field.querySelector(':scope > label');
  field.classList.add('fc-card', 'sc-card');
  const top = document.createElement('div');
  top.className = 'crow-top';
  // Точка цвета: свой выбор цвета (узел-слот переезжает из подписи) или значок цвета роли.
  /* Слот выбора цвета (узел с id) переезжает в верхний ряд, даже пустой: у КПВ выбора цвета сейчас нет (слоты
     ppf-color* пусты), тогда рядом встаёт простой значок цвета кривой. */
  let dot = o.slot ? document.getElementById(o.slot) : (o.slotEl || null);
  let slot = null;
  if (dot) { dot.classList.add('sc-dot-slot'); if (!dot.children.length && o.col) { slot = dot; dot = null; } }
  if (!dot && o.col) { dot = document.createElement('span'); dot.className = 'fc-dot'; dot.setAttribute('aria-hidden', 'true'); }
  const sym = document.createElement('span');
  sym.className = 'fc-notation sc-sym';
  const name = document.createElement('span');
  name.className = 'fc-name sc-name';
  if (slot) top.appendChild(slot);
  if (dot) top.appendChild(dot);
  top.append(sym, name);
  // Меню «⋯»: только если есть что положить.
  let more = null;
  const items = (o.menu || []).map(x => (typeof x === 'string' ? document.getElementById(x) : x)).filter(Boolean);
  if (items.length) {
    more = document.createElement('div');
    more.className = 'crow-more fc-menu';
    more.setAttribute('role', 'dialog');
    more.setAttribute('aria-label', 'Настройки: ' + (o.name || ''));
    items.forEach(n => {
      if (n.tagName === 'BUTTON') { n.classList.add('fc-mi'); more.appendChild(n); return; }   // кнопка пунктом меню
      const l = document.createElement('div');
      l.className = 'fc-menu-lab'; l.textContent = n._scMenuLab || 'Подпись на графике';
      more.append(l, n);
    });
    const gear = document.createElement('button');
    gear.type = 'button'; gear.className = 'btn-icon crow-gear fc-ico';
    gear.setAttribute('aria-label', 'Настройки: ' + (o.name || ''));
    gear.setAttribute('aria-haspopup', 'dialog');
    gear.setAttribute('aria-expanded', 'false');
    gear.innerHTML = ICON_DOTS;
    gear.addEventListener('click', (e) => { e.stopPropagation(); if (more.classList.contains('open')) { closeFcMenu(); return; } openFcMenu(gear, more); });
    top.appendChild(gear);
  }
  // Строка формулы: приставка и прежний ряд поля (f-row: поле, клавиатура).
  const line = document.createElement('div');
  line.className = 'crow-formula';
  fRow.before(line);
  if (o.prefix) {
    const pre = document.createElement('span');
    pre.className = 'fc-prefix'; pre.setAttribute('aria-hidden', 'true');
    line.appendChild(pre);
    field._scPre = pre;
  }
  line.appendChild(fRow);
  if (o.number) inp.classList.add('sc-numfield');
  field.insertBefore(top, field.firstChild);
  if (more) line.after(more);
  // Прежняя подпись: её текст пишет сцена — остаётся, спрятана классом; иначе убирается.
  if (lab) { if (o.keepLabel) lab.classList.add('sc-old-label'); else lab.remove(); }
  field._scCard = { o, dot, sym, name, top, more };
  paintCard(field);
  return field._scCard;
}
/* Обозначение, имя, приставка и цвет значка — по состоянию (у «Монополиста и внешнего рынка» поля те же, что у
   дискриминации 3-й степени, а смысл другой): зовётся на каждой перерисовке. */
function paintCard(field) {
  const c = field._scCard; if (!c) return;
  const v = (x) => (typeof x === 'function' ? x() : x);
  const sym = v(c.o.sym), name = v(c.o.name), pre = v(c.o.prefix);
  if (c.sym._tex !== sym) { c.sym._tex = sym; katexInto(c.sym, sym); }
  if (c.name.textContent !== name) c.name.textContent = name;
  if (field._scPre && field._scPre._tex !== pre) { field._scPre._tex = pre; katexInto(field._scPre, String(pre).replace(' =', '\\,=')); }
  if (c.dot && c.dot.classList.contains('fc-dot')) {
    const cv = v(c.o.col), col = COL[cv] || cv || '';   // ключ палитры COL или сам цвет
    if (c.dot._col !== col) { c.dot._col = col; c.dot.style.background = col; }
  }
}

/* Карточки моделей сессии 5 (README 8): поле → обозначение, имя, приставка, цвет, «⋯». */
const SC_CARDS = [
  { m: 'ppf', input: 'inp-ppf', sym: '\\text{КПВ}', name: 'Производственные возможности', slot: 'ppf-color1', col: () => STATE.ppfColor1 || COL.D, menu: ['ppf-name1-row'] },
  { m: 'ppf', input: 'inp-ppf2b', sym: '\\text{КПВ}_2', name: 'Для сравнения', slot: 'ppf-color2', col: () => STATE.ppfColor2 || COL.S, menu: [() => { const i = document.getElementById('inp-ppf-name2'); return i && i.closest('.field'); }] },
  { m: 'trade', input: 'inp-ppft', sym: '\\text{КПВ}', name: 'Страна', prefix: 'Y =', col: 'D' },
  { m: 'tradeprice', input: 'inp-tb1', sym: '\\text{КПВ}_1', name: 'Страна 1', prefix: 'Y =', col: 'D' },
  { m: 'tradeprice', input: 'inp-tb2', sym: '\\text{КПВ}_2', name: 'Страна 2', prefix: 'Y =', col: 'S' },
  { m: 'prod', input: 'inp-prod', sym: '\\mathrm{TP}', name: 'Производственная функция', prefix: 'Q =', col: 'prodTP' },
  { m: 'costs', input: 'inp-tc', sym: '\\mathrm{TC}', name: 'Суммарные затраты', prefix: '\\mathrm{TC} =', col: 'costTC', menu: ['btn-costs-preset'] },
  { m: 'costs', input: 'inp-cmc', sym: '\\mathrm{MC}', name: 'Предельные затраты', prefix: '\\mathrm{MC} =', col: 'costMC' },
  { m: 'costs', input: 'inp-catc', sym: '\\mathrm{ATC}', name: 'Средние общие', prefix: '\\mathrm{ATC} =', col: 'costATC' },
  { m: 'costs', input: 'inp-cavc', sym: '\\mathrm{AVC}', name: 'Средние переменные', prefix: '\\mathrm{AVC} =', col: 'costAVC' },
  { m: 'plants', input: 'inp-pl1', sym: '\\mathrm{TC}_1', name: 'Завод 1', prefix: '\\mathrm{TC}_1 =', col: 'tax' },
  { m: 'plants', input: 'inp-pl2', sym: '\\mathrm{TC}_2', name: 'Завод 2', prefix: '\\mathrm{TC}_2 =', col: 'reg' },
  { m: 'isoquant', input: 'inp-iso', sym: 'Q', name: 'Производственная функция', prefix: 'Q =', col: 'isoq' },
  // «Монополист и внешний рынок» — те же поля, что у дискриминации 3-й степени (STATE.d3World): подписи пишет
  // сцена (applyD3WorldLabels) — они остаются спрятанными, карточка берёт смысл по состоянию.
  { m: 'mono-d3', input: 'inp-d3-1', sym: () => (STATE.d3World ? 'D' : 'D_1'), name: () => (STATE.d3World ? 'Внутренний спрос' : 'Спрос рынка 1'), prefix: 'P =', col: 'D', keepLabel: true },
  { m: 'mono-d3', input: 'inp-d3-2', sym: () => (STATE.d3World ? 'P_w' : 'D_2'), name: () => (STATE.d3World ? 'Мировая цена' : 'Спрос рынка 2'), prefix: () => (STATE.d3World ? 'P_w =' : 'P ='), col: () => (STATE.d3World ? 'reg' : 'D'), keepLabel: true },
  { m: 'mono-d3', input: 'inp-d3-mc', sym: '\\mathrm{MC}', name: () => (STATE.d3World ? 'Предельные издержки от общего выпуска' : 'Предельные издержки'), prefix: '\\mathrm{MC} =', col: 'S', keepLabel: true },
  { m: 'mono-kink', input: 'inp-ki-1', sym: 'D_1', name: 'Спрос 1', prefix: 'P =', col: 'D' },
  { m: 'mono-kink', input: 'inp-ki-2', sym: 'D_2', name: 'Спрос 2', prefix: 'P =', col: 'D' },
  { m: 'mono-kink', input: 'inp-ki-3', sym: 'D_3', name: 'Спрос 3, необязательно', prefix: 'P =', col: 'D' },
  { m: 'mono-kink', input: 'inp-kp-1', sym: 'D_1', name: 'Верхний кусок', prefix: 'P =', col: 'D' },
  { m: 'mono-kink', input: 'inp-kp-2', sym: 'D_2', name: 'Нижний кусок', prefix: 'P =', col: 'D' },
  { m: 'mono-kink', input: 'inp-kink-mc', sym: '\\mathrm{MC}', name: 'Предельные издержки', prefix: '\\mathrm{MC} =', col: 'S' },
  // Макро (сессия 6, этап В; README 8; макет 05_left_Adas): без глаза и «⋯» (видимости и меню у этих кривых нет),
  // точка — простой значок цвета кривой (цвета сцены, 50-scenes-macro.js).
  { m: 'adas', input: 'ma-lras', sym: '\\mathrm{LRAS}', name: 'Потенциальный выпуск', prefix: 'Y^{*} =', col: 'MC', number: true },
  { m: 'adas', input: 'ma-sras', sym: '\\mathrm{SRAS}', name: 'Краткосрочное предложение', prefix: 'P =', col: 'S' },
  { m: 'adas', input: 'ma-ad', sym: '\\mathrm{AD}', name: 'Совокупный спрос', prefix: 'P =', col: 'D' },
  { m: 'islm', input: 'ma-is', sym: '\\mathrm{IS}', name: 'Равновесие рынка товаров', prefix: 'r =', col: 'D' },
  { m: 'islm', input: 'ma-lm', sym: '\\mathrm{LM}', name: 'Равновесие денежного рынка', prefix: 'r =', col: 'S' },
  { m: 'money', input: 'ma-md', sym: 'M_d', name: 'Спрос на деньги', prefix: 'M =', col: 'D' },
  { m: 'loanable', input: 'ma-ls', sym: 'S', name: 'Сбережения', prefix: 'S =', col: 'S' },
  { m: 'loanable', input: 'ma-ld', sym: 'D', name: 'Частные инвестиции', prefix: 'D =', col: 'D' },
  { m: 'fx', input: 'ma-fxd', sym: 'D', name: 'Спрос на валюту', prefix: 'Q =', col: 'D' },
  { m: 'fx', input: 'ma-fxs', sym: 'S', name: 'Предложение валюты', prefix: 'Q =', col: 'S' },
  { m: 'laffer', input: 'ma-lafd', sym: 'D', name: 'Спрос', prefix: 'P =', col: 'D' },
  { m: 'laffer', input: 'ma-lafs', sym: 'S', name: 'Предложение', prefix: 'P =', col: 'S' },
  // Математика (сессия 6, Г3): «Деформации», «Оптимум», «Касательная» — общее поле f (подпись math-f-label пишет
  // сюжет — остаётся спрятанной). Точка — цвет кривой f; у «Касательной» — кнопка цвета tanF (scMathSync).
  { m: 'm-math', input: 'inp-mathf', sym: 'f', name: 'Функция', prefix: 'y =', col: () => (STATE.mathSub === 'tangent' ? COL.tanF : COL.D), keepLabel: true },
  // Неравенство (сессия 6, Г1): способ «Формула» — карточка L.
  { m: 'ineq', input: 'ineq-formula', sym: 'L', name: 'Функция Лоренца', prefix: 'L(p) =', col: 'S' },
];
/* Строки ползунков (README 4): подпись словами слева, «обозначение = значение» справа. Обозначение регулятора
   берёт shortRegulatorName (88-params.js) отсюда. */
const SC_PROWS = {
  'ppft-price-field': ['Мировая цена', 'Px/Py', 'trade'], 'tb-price-field': ['Мировая цена', 'Pw', 'tradeprice'],
  'lr-price-field': ['Цена', 'P', 'costs'], 'pl-q-field': ['Совокупный выпуск', 'Q', 'plants'],
  'union-wage-field': ['Зарплата профсоюза', 'W', 'labor'], 'labmin-field': ['Минимальная зарплата', 'W_min', 'labor'],
  'open-pw-field': ['Мировая цена', 'Pw', 'smallopen'],
  // Сессия 6, Б2: «Новая цена товара x» и P_{x₁} (shortRegulatorName резал «Px₁» до «…», Notion …81b4…).
  'cons-px1-row': ['Новая цена товара $x$', 'P_{x_1}', 'consumer'],
  'ma-dg-field': ['Дефицит бюджета', '\\Delta G', 'loanable'], 'ma-fx-fixed-field': ['Курс', 'e', 'fx'],
  'ineq-alpha-field': ['Параметр', '\\alpha', 'ineq'], 'mathx0-field': ['Точка', 'x_0', 'm-math'],
};
/* Буква, которая является переменной оси модели макро (r у «Заёмных средств», i, e, Y…), ползунка не получает
   (сессия 6, В5; Notion …8187…): замер claude/panels_s6/dead_r_loanable.json — сдвиг r не меняет ни «Ответ», ни один
   узел холста, ни .tex. STATE.params не трогаем (старт, ссылки и автосохранения прежние): фильтр — только при сборке
   ползунков (buildPultExtra, 88-params.js). */
function scAxisLetter(n) {
  if (STATE.mode !== 'macro' || typeof MACRO === 'undefined' || !MACRO[STATE.macroModel] || !scOn(STATE.macroModel)) return false;
  return (MACRO[STATE.macroModel].vars || []).indexOf(n) >= 0;
}
/* Подписи строк чисел словами (сессия 6): [id поля] → подпись; $…$ — набор KaTeX. */
const SC_NLABELS = { 'cons-px': 'Цена товара $x$', 'cons-py': 'Цена товара $y$', 'cons-i': 'Доход',
  'ma-ms': 'Предложение денег $M_s$', 'ma-lafmax': 'Ставка на оси до',
  'ma-pe': 'Ожидаемая инфляция $\\pi^{e}$', 'ma-ustar': 'Естественная безработица $u^{*}$', 'ma-beta': 'Наклон $\\beta$' };
/* Модели без карточек функций (сессия 6, В3: «Кривая Филлипса»): заголовок карточки ввода — «Параметры», а не
   «Функции» (scSync), второго заголовка нет. */
const SC_NO_FUNCS = (m) => scOn(m) && m === 'phillips';
function scFirstCardName() {
  const k = STATE.mode === 'macro' ? STATE.macroModel : null;
  return k && SC_NO_FUNCS(k) ? 'Параметры' : null;
}
/* Слова с формулами: «Цена товара $x$» — текст и KaTeX кусками (подпись строки, имя ползунка). */
function scWords(el, text) {
  el.textContent = '';
  String(text).split(/(\$[^$]+\$)/).forEach(part => {
    if (!part) return;
    if (/^\$[^$]+\$$/.test(part)) { const k = document.createElement('span'); k.className = 'sc-tex'; katexInto(k, part.slice(1, -1)); el.appendChild(k); }
    else el.appendChild(document.createTextNode(part));
  });
}
// Строки чисел (подпись слева, поле 76 × 36 справа): [id поля, модель].
const SC_NROWS = [['inp-bundle-x', 'ppf'], ['inp-bundle-y', 'ppf'], ['inp-bundle-x2', 'ppfsum'], ['inp-bundle-y2', 'ppfsum'],
  ['inp-bundle-xt', 'trade'], ['inp-bundle-yt', 'trade'], ['iso-w', 'isoquant'], ['iso-r', 'isoquant'], ['iso-c', 'isoquant'],
  ['inp-nat-fc', 'mono-nat'], ['cons-px', 'consumer'], ['cons-py', 'consumer'], ['cons-i', 'consumer'],
  ['ma-pe', 'phillips'], ['ma-ustar', 'phillips'], ['ma-beta', 'phillips'], ['ma-ms', 'money'], ['ma-lafmax', 'laffer']];
// Раздел «Параметры»: заголовок встаёт перед первым узлом параметров панели модели — [id, модель].
const SC_PARAM_HEAD = [['chk-bundle-1', 'ppf'], ['chk-bundle-2', 'ppfsum'], ['ppft-price-field', 'trade'], ['tb-price-field', 'tradeprice'],
  ['chk-lr', 'costs'], ['pl-q-field', 'plants'], ['iso-w', 'isoquant'], ['inp-nat-fc', 'mono-nat'], ['labmin-block', 'labor'],
  ['open-pw-field', 'smallopen'], ['cons-px', 'consumer'], ['ma-ms', 'money'], ['ma-dg-field', 'loanable'], ['ma-fx-fixed', 'fx'], ['ma-lafmax', 'laffer']];
// Сегменты вместо тумблера пары подписей: [id левой кнопки полосы, модель].
const SC_SEGS = [['cm-tc', 'costs'], ['ki-indiv', 'mono-kink'], ['un-monopoly', 'labor'], ['ineq-rd-tax', 'ineq']];
/* Модели, переведённые на карточки и строки параметров (сессия 5: по одной модели, у каждой свой коммит — откат
   модели снимает её из списка). Ключ — семейство: 'mono-d3' включает и «Монополиста и внешний рынок» (те же поля),
   'labor' — все четыре модели рынка труда. */
const SC_ON = new Set(['ppf', 'ppfsum', 'trade', 'tradeprice', 'prod', 'costs', 'plants', 'isoquant', 'mono-d3', 'mono-kink', 'mono-nat', 'labor', 'smallopen', 'consumer', 'adas', 'islm', 'phillips', 'money', 'loanable', 'fx', 'laffer', 'ineq', 'm-graph', 'm-math']);
const scOn = (m) => SC_ON.has(m);
function scProw(id) { const r = SC_PROWS[id]; return r && scOn(r[2]) ? r : null; }
function scParamAnchor(el) {
  if (!el) return null;
  // «Рыночная цена» в «Издержках» стоит своим блоком с чертой сверху — заголовок встаёт перед блоком.
  if (el.id === 'chk-lr') { const l = el.closest('label'); return (l && l.parentElement && l.parentElement.id !== 'costs-pane-costs') ? l.parentElement : l; }
  if (el.type === 'checkbox') return el.closest('label') || el;
  if (el.id === 'iso-w' || el.id === 'cons-px') return el.closest('.row') || el.closest('.field');
  if (el.tagName === 'INPUT') return el.closest('.field') || el;
  return el;
}
function scSetup() {
  SC_CARDS.forEach(o => {
    if (!scOn(o.m)) return;
    const inp = document.getElementById(o.input);
    const field = inp && inp.closest('.field');
    if (!field) return;
    const menu = (o.menu || []).map(x => (typeof x === 'function' ? x() : x));
    wrapFieldInCard(field, Object.assign({}, o, { menu }));
  });
  if (scOn('consumer')) scConsumerCard();
  if (scOn('ineq')) scIneqSetup();
  if (scOn('m-math')) scMathSetup();
  Object.keys(SC_PROWS).forEach(id => {
    const f = document.getElementById(id);
    if (!f || f._scRow || !scProw(id)) return;
    f._scRow = true;
    f.classList.add('sc-prow');
    const nm = document.createElement('span');
    nm.className = 'sc-pname'; scWords(nm, SC_PROWS[id][0]);
    f.insertBefore(nm, f.firstChild);
  });
  SC_NROWS.forEach(([id, m]) => {
    if (!scOn(m)) return;
    const i = document.getElementById(id);
    const f = i && i.closest('.field');
    if (!f) return;
    f.classList.add('sc-nrow');
    const lab = SC_NLABELS[id] && f.querySelector(':scope > label');
    if (lab && !lab._scWords) { lab._scWords = true; scWords(lab, SC_NLABELS[id]); }
    const row = f.parentElement;
    if (row && row.classList.contains('row')) row.classList.add('sc-nrows');
  });
  SC_PARAM_HEAD.forEach(([id, m]) => {
    if (!scOn(m)) return;
    const a = scParamAnchor(document.getElementById(id));
    if (!a || (a.previousElementSibling && a.previousElementSibling.classList.contains('sc-sec'))) return;
    const h = document.createElement('div');
    h.className = 'sc-sec'; h.textContent = 'Параметры';   // не .section-title: внутри «Функций» заголовков верхнего уровня нет (calc2_ui)
    a.before(h);
  });
  SC_SEGS.forEach(([id, m]) => {
    if (!scOn(m)) return;
    const b = document.getElementById(id);
    const seg = b && b.closest('.seg');
    if (!seg) return;
    seg.classList.add('sc-seg');
    if (seg._tgl) seg._tgl.classList.add('sc-tgl-off');
  });
  // «Сравнить с другой КПВ» — пунктирной «Добавить …» после второй карточки.
  const cmp = document.getElementById('btn-ppf-compare'), second = document.getElementById('ppf-second');
  if (scOn('ppf') && cmp && second && second.nextElementSibling !== cmp) second.after(cmp);
  // «Сколько КПВ»: степпер вокруг прежнего поля числа (оно хранит значение и слушает ввод).
  const n = document.getElementById('inp-ppfsum-n');
  if (scOn('ppfsum') && n && !n._scStep) {
    n._scStep = true;
    const f = n.closest('.field');
    if (f) f.classList.add('sc-step-row');
    const box = document.createElement('span');
    box.className = 'sc-stepper';
    n.before(box);
    const step = (d, label) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'sc-step'; b.textContent = d < 0 ? '−' : '+';
      b.setAttribute('aria-label', label);
      b.addEventListener('click', () => {
        const lo = +n.min || 2, hi = +n.max || 5, v = Math.max(lo, Math.min(hi, (parseInt(n.value, 10) || lo) + d));
        if (String(v) === n.value) return;
        n.value = String(v);
        n.dispatchEvent(new Event('input', { bubbles: true }));
      });
      return b;
    };
    box.append(step(-1, 'Меньше КПВ'), n, step(1, 'Больше КПВ'));
  }
  scSync();
}
// По состоянию на каждой перерисовке: смысл карточек «Дискриминации» / «Внешнего рынка», цвета значков.
function scSync() {
  document.querySelectorAll('#tools-panel .sc-card').forEach(paintCard);
  // Заголовок карточки ввода («Функции»; у модели без функций — «Параметры»). Узел без id: вид, не модель.
  const hb = document.querySelector('#sec-input > h3.sec-head span > b');
  if (hb) {
    if (hb._scOwn == null) hb._scOwn = hb.textContent;
    const want = scFirstCardName() || hb._scOwn;
    if (hb.textContent !== want) hb.textContent = want;
  }
  scConsumerSync();
  scIneqSync();
  scGraphRows();
  scMathSync();
  scParamsCont();
  const cmp = document.getElementById('btn-ppf-compare');
  if (cmp) { const on = STATE.ppfCompare ? '1' : '0'; if (cmp.dataset.on !== on) cmp.dataset.on = on; }
}

/* ═══ Карточка U «Полезность» (сессия 6, Б1–Б2; README 4, 8; макет 05_left_Consumer; ADR 0154) ═══
   У полезности нет одного поля формулы — вид задаётся списком, параметры числами, «Своя формула» полем. Карточка —
   новый узел без id (вид); органы с id ПЕРЕЕЗЖАЮТ в неё узлами: поле списка вида (cons-type, системный select под
   upgradeSelect), строки a и b (cons-ab-row), k (cons-k-row), своя формула (cons-custom-row). Их видимость ставит
   сцена (applyConsumerTypeUI) инлайновым display — не трогаем. Подписи a, b пишет сцена (cons-a-lbl, cons-b-lbl:
   «a (степень x)») — остаются, спрятаны классом; рядом буквы KaTeX. Точка — цвет кривых безразличия простым
   значком (выбор цвета — в «Виде», строка «Веер кривых безразличия»); глаза и «⋯» нет (веер — в «Виде»). */
const CONS_TYPE_TEX = {
  cobb: 'U = x^{a}\\cdot y^{b}', subs: 'U = a\\cdot x + b\\cdot y',
  compl: 'U = \\min(x/a,\\ y/b)', quasi: 'U = x + k\\cdot\\sqrt{y}',
};
function scConsumerCard() {
  const sec = document.getElementById('sec-consumer');
  const sel = document.getElementById('cons-type');
  const typeField = sel && sel.closest('.field');
  const firstRow = document.getElementById('cons-px') && document.getElementById('cons-px').closest('.row');
  if (!sec || !typeField || !firstRow || sec._scU) return;
  sec._scU = true;
  // Без data-tip (подсказок нет, решение …81eb…): подпись для диктора — aria-label кнопки.
  if (typeof upgradeSelect === 'function') upgradeSelect('cons-type');
  if (sel.previousElementSibling && sel.previousElementSibling.classList.contains('sel-btn')) sel.previousElementSibling.setAttribute('aria-label', 'Вид полезности');
  const card = document.createElement('div');
  card.className = 'fc-card sc-card sc-ucard';
  const top = document.createElement('div'); top.className = 'crow-top';
  const dot = document.createElement('span'); dot.className = 'fc-dot'; dot.setAttribute('aria-hidden', 'true');
  const sym = document.createElement('span'); sym.className = 'fc-notation sc-sym';
  const name = document.createElement('span'); name.className = 'fc-name sc-name'; name.textContent = 'Полезность';
  katexInto(sym, 'U');
  top.append(dot, sym, name);
  const tl = typeField.querySelector(':scope > label'); if (tl) tl.classList.add('sc-old-label');
  typeField.classList.add('sc-utype');
  const fml = document.createElement('div'); fml.className = 'sc-ufml'; fml.setAttribute('aria-hidden', 'true');
  card.append(top, typeField, fml);
  // a и b — буквой KaTeX и числом плашкой в одну строку; k — так же.
  const letterRow = (inpId, letter) => {
    const i = document.getElementById(inpId); const f = i && i.closest('.field');
    if (!f) return;
    const l = f.querySelector(':scope > label'); if (l) l.classList.add('sc-old-label');
    const k = document.createElement('span'); k.className = 'sc-letter'; katexInto(k, letter);
    f.insertBefore(k, i);
    f.classList.add('sc-lrow');
    i.classList.add('sc-num');
  };
  letterRow('cons-a', 'a'); letterRow('cons-b', 'b'); letterRow('cons-k', 'k');
  ['cons-ab-row', 'cons-k-row'].forEach(id => { const e = document.getElementById(id); if (e) card.appendChild(e); });
  // Своя формула: строка поля карточки (приставка «U =», поле MathLive, клавиатура) — сам узел cons-custom-row.
  const cr = document.getElementById('cons-custom-row');
  if (cr) {
    const l = cr.querySelector(':scope > label'); if (l) l.classList.add('sc-old-label');
    const fr = cr.querySelector('.f-row');
    if (fr && !cr.querySelector('.fc-prefix')) {
      const pre = document.createElement('span'); pre.className = 'fc-prefix'; pre.setAttribute('aria-hidden', 'true');
      katexInto(pre, 'U(x,\\,y)\\,=');
      fr.before(pre);
    }
    cr.classList.add('crow-formula');
    card.appendChild(cr);
  }
  firstRow.before(card);
  scConsumerSync();
}
function scConsumerSync() {
  const card = document.querySelector('#sec-consumer .sc-ucard');
  if (!card) return;
  const t = STATE.consType;
  // Сцена ставит вид свойством (setConsumerType: sel.value = t) без события — кнопка списка перерисовывается здесь.
  const sel = document.getElementById('cons-type');
  if (sel && sel._paint) sel._paint();
  const fml = card.querySelector('.sc-ufml');
  const tex = CONS_TYPE_TEX[t] || '';
  if (fml && fml._tex !== tex) { fml._tex = tex; if (tex) katexInto(fml, tex); else fml.textContent = ''; }
  if (fml) fml.classList.toggle('sc-off', !tex);   // у своей формулы формулы вида нет — её место занимает поле
  const dot = card.querySelector('.fc-dot');
  const col = COL.indiff || '';
  if (dot && dot._col !== col) { dot._col = col; dot.style.background = col; }
}

/* ═══ Неравенство доходов (сессия 6, Г1; README 4, 8) ═══
   «Число групп» — сегмент «5 групп | 10 групп»: источник правды — прежний список ineq-ngroups (под upgradeSelect),
   кнопки сегмента без id пишут в него и шлют change (как кнопки кривых площади пишут в ac-pick). Группы — строки
   чисел плашкой (строки пересобирает сцена, renderIneqGroupsTable: вид ставится на каждой перерисовке). Ползунки τ и
   T — строки параметра: слова слева, «τ = 0» справа (их значение пишет и сцена в ineq-tau-val, здесь — вид). */
function scIneqSetup() {
  const sel = document.getElementById('ineq-ngroups');
  const f = sel && sel.closest('.field');
  if (f && !f._scIneq) {
    f._scIneq = true;
    f.classList.add('sc-segrow');
    const seg = document.createElement('div');
    seg.className = 'seg sc-nseg'; seg.setAttribute('role', 'radiogroup'); seg.setAttribute('aria-label', 'Число групп');
    [['5', '5 групп'], ['10', '10 групп']].forEach(([v, t]) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'seg-btn'; b.textContent = t; b.dataset.v = v;
      b.setAttribute('role', 'radio');
      b.addEventListener('click', () => {
        if (sel.value === v) return;
        sel.value = v; if (sel._paint) sel._paint();
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      });
      seg.appendChild(b);
    });
    sel.before(seg);
    const sb = sel.previousElementSibling && sel.previousElementSibling.previousElementSibling;   // кнопка-список upgradeSelect
    f.querySelectorAll(':scope > .sel-btn').forEach(x => x.classList.add('sc-gone'));
    void sb;
  }
  [['ineq-tau-field', 'ineq-tau', 'Прогрессивность'], ['ineq-transfer-field', 'ineq-transfer', 'Трансферт, % дохода']].forEach(([fid, sid, words]) => {
    const fld = document.getElementById(fid), sl = document.getElementById(sid);
    if (!fld || !sl || fld._scRow) return;
    fld._scRow = true;
    fld.classList.add('sc-prow', 'sc-prow-own');
    const lab = fld.querySelector(':scope > label'); if (lab) lab.classList.add('sc-old-label');
    const nm = document.createElement('span'); nm.className = 'sc-pname'; nm.textContent = words;
    const val = document.createElement('span'); val.className = 'sc-pval'; val.setAttribute('aria-hidden', 'true');
    fld.insertBefore(val, fld.firstChild); fld.insertBefore(nm, val);
    sl.addEventListener('input', scIneqSync);
  });
  scIneqSync();
}
function scIneqSync() {
  const sel = document.getElementById('ineq-ngroups');
  const seg = document.querySelector('#tools-panel .sc-nseg');
  if (sel && seg) seg.querySelectorAll('.seg-btn').forEach(b => {
    const on = b.dataset.v === sel.value;
    b.classList.toggle('active', on); b.setAttribute('aria-checked', on ? 'true' : 'false');
  });
  document.querySelectorAll('#ineq-groups-table > div').forEach(r => {
    if (r._scRow) return;
    r._scRow = true;
    r.classList.add('sc-grow');
    const i = r.querySelector('input'); if (i) { i.classList.add('sc-num'); i.style.flex = ''; }
  });
  [['ineq-tau', '\\tau', ''], ['ineq-transfer', 'T', '\\,\\%']].forEach(([sid, sym, unit]) => {
    const sl = document.getElementById(sid); const f = sl && sl.closest('.sc-prow-own'); if (!f) return;
    const v = f.querySelector('.sc-pval'); const tex = sym + ' = ' + fmt(+sl.value) + unit;
    if (v && v._tex !== tex) { v._tex = tex; katexInto(v, tex); }
  });
}

/* ═══ «Построение графиков»: каждая функция — карточка (сессия 6, Г2; README 8) ═══
   Строку (.grow) собирает сцена двумя путями: полная пересборка (renderGraphRows) и «рождение» следующей пустой
   строки после первого ввода (graphRowInput, 60-overlays.js) — оборачиваем в обоих (и на каждой перерисовке, на
   случай третьего). Строка САМА становится карточкой: тот же узел, поле и его id (graph-f-N), обработчики; узлы
   переезжают: выбор цвета — точкой-кнопкой в верхний ряд, «Имя на графике» и крестик «Убрать функцию» — в «⋯».
   Последняя пустая строка — пунктирная карточка «Новая функция»: точка — простой значок (до первой записи цвет и
   имя там ничего не делают: if (!row._curve) return), «⋯» нет; после первой записи — обычная карточка. */
function scGraphRows(box) {
  box = box || document.getElementById('graph-rows');
  if (!box || !scOn('m-graph')) return;
  box.querySelectorAll(':scope > .grow').forEach(row => {
    if (row._scG) return;
    const pick = row.querySelector(':scope > .cpick');
    const fwrap = row.querySelector(':scope > .f-slot');
    const del = row.querySelector(':scope > .btn-icon');
    const name = row.querySelector(':scope > .grow-name');
    if (!fwrap) return;
    row._scG = true;
    row.classList.add('fc-card', 'sc-card', 'sc-gcard');
    const top = document.createElement('div'); top.className = 'crow-top';
    const dot = document.createElement('span'); dot.className = 'fc-dot'; dot.setAttribute('aria-hidden', 'true');
    const sym = document.createElement('span'); sym.className = 'fc-notation sc-sym';
    const nm = document.createElement('span'); nm.className = 'fc-name sc-name';
    if (pick) { pick.classList.add('sc-dot-slot'); top.appendChild(pick); }
    top.append(dot, sym, nm);
    const more = document.createElement('div');
    more.className = 'crow-more fc-menu'; more.setAttribute('role', 'dialog'); more.setAttribute('aria-label', 'Настройки функции');
    if (name) { const l = document.createElement('div'); l.className = 'fc-menu-lab'; l.textContent = 'Имя на графике'; more.append(l, name); }
    if (del) { del.classList.add('fc-mi'); del.textContent = 'Убрать функцию'; more.appendChild(del); }
    const gear = document.createElement('button');
    gear.type = 'button'; gear.className = 'btn-icon crow-gear fc-ico';
    gear.setAttribute('aria-label', 'Настройки функции'); gear.setAttribute('aria-haspopup', 'dialog'); gear.setAttribute('aria-expanded', 'false');
    gear.innerHTML = ICON_DOTS;
    gear.addEventListener('click', (e) => { e.stopPropagation(); if (more.classList.contains('open')) { closeFcMenu(); return; } openFcMenu(gear, more); });
    top.appendChild(gear);
    const line = document.createElement('div'); line.className = 'crow-formula';
    const pre = document.createElement('span'); pre.className = 'fc-prefix'; pre.setAttribute('aria-hidden', 'true');
    katexInto(pre, 'y\\,=');
    row.insertBefore(top, row.firstChild);
    top.after(line);
    line.append(pre, fwrap);
    line.after(more);
    row._scParts = { pick, dot, sym, nm, gear, pre, del };
  });
  scGraphSync(box);
}
function scGraphSync(box) {
  box = box || document.getElementById('graph-rows');
  if (!box) return;
  const taken = new Set((STATE.curves || []).filter(c => !c.role).map(c => c._auto).filter(Boolean));
  const nextLetter = (typeof AUTO_CURVE_LETTERS !== 'undefined' ? AUTO_CURVE_LETTERS : ['f']).find(l => !taken.has(l)) || 'f';
  box.querySelectorAll(':scope > .grow.sc-gcard').forEach(row => {
    const p = row._scParts; if (!p) return;
    const c = row._curve, isNew = !c;
    row.classList.toggle('sc-gnew', isNew);
    if (p.pick) p.pick.classList.toggle('sc-gone', isNew);
    p.dot.classList.toggle('sc-gone', !isNew);
    p.gear.classList.toggle('sc-gone', isNew);
    if (isNew) { const b = p.pick && p.pick.querySelector('.cpick-btn'); const col = (b && b.style.background) || ''; if (p.dot._col !== col) { p.dot._col = col; p.dot.style.background = col; } }
    const short = isNew ? nextLetter : curveShortName(c);
    const tex = /^[A-Za-z]$/.test(short) ? short : (typeof texifyName === 'function' ? texifyName(short) : '\\text{' + short + '}');
    if (p.sym._tex !== tex) { p.sym._tex = tex; katexInto(p.sym, tex); }
    const want = isNew ? 'Новая функция' : 'Функция';
    if (p.nm.textContent !== want) p.nm.textContent = want;
    const inp = row.querySelector('.f-slot input[id]');
    const eq = !!(inp && /=/.test(String(inp.value || '')));
    p.pre.classList.toggle('sc-gone', eq);   // уравнение — без приставки
  });
}

/* ═══ «Математика»: «Деформации», «Оптимум», «Касательная» (сессия 6, Г3) ═══
   У «Касательной» выбор цвета f (кнопка cpick data-col="tanF", была в группе «Цвета кривых») — точка-кнопка карточки f
   (узел переезжает; в других сюжетах — простой значок цвета кривой). Группа «Цвета кривых» — простой <label>, его
   hideEmptyGroupTitles не видит: когда обе строки переехали (f — в карточку, f′ — в «Вид»), группа прячется явно.
   «Шаг Δx» — строка параметра (дорожка внутри data-no-regulator, upgradeRegulator её не берёт: здесь только вид). */
function scMathSetup() {
  const card = document.getElementById('math-row-f');
  const pick = document.querySelector('#math-pane-tangent .cpick[data-col="tanF"]');
  if (card && card._scCard && pick && !pick._scMoved) {
    pick._scMoved = true;
    const lab = pick.closest('label');
    const grp = lab && lab.closest('.field');
    pick.classList.add('sc-dot-slot', 'sc-tanf');
    card._scCard.top.insertBefore(pick, card._scCard.top.firstChild);
    if (lab) lab.classList.add('sc-gone');
    if (grp) grp.classList.add('sc-mcolors');
  }
  const f = document.getElementById('mathdx-field'), sl = document.getElementById('mathdx-slider');
  if (f && sl && !f._scRow) {
    f._scRow = true;
    f.classList.add('sc-prow', 'sc-prow-own');
    const lab = f.querySelector(':scope > label'); if (lab) lab.classList.add('sc-old-label');
    const nm = document.createElement('span'); nm.className = 'sc-pname'; nm.textContent = 'Шаг';
    const val = document.createElement('span'); val.className = 'sc-pval'; val.setAttribute('aria-hidden', 'true');
    f.insertBefore(val, f.firstChild); f.insertBefore(nm, val);
    sl.addEventListener('input', scMathSync);
  }
  scMathSync();
}
function scMathSync() {
  const card = document.getElementById('math-row-f');
  const c = card && card._scCard;
  if (c) {
    const tan = STATE.mathSub === 'tangent';
    const pick = c.top.querySelector('.sc-tanf');
    if (pick) pick.classList.toggle('sc-gone', !tan);
    if (c.dot) c.dot.classList.toggle('sc-gone', tan);
  }
  const grp = document.querySelector('#math-pane-tangent .sc-mcolors');
  if (grp) {
    // Видимый орган в группе остался? (строка f′ уехала в «Вид» — на её месте заглушка .vg-home)
    const left = [...grp.querySelectorAll('input, button, .cpick')].some(e => !e.closest('.sc-gone, .vg-home') && getComputedStyle(e).display !== 'none');
    grp.classList.toggle('sc-gone', !left);
  }
  const sl = document.getElementById('mathdx-slider'); const f = sl && sl.closest('.sc-prow-own');
  if (f) { const v = f.querySelector('.sc-pval'); const tex = '\\Delta x = ' + fmt(+sl.value); if (v && v._tex !== tex) { v._tex = tex; katexInto(v, tex); } }
}
/* Раздел ползунков «Параметры» (#sec-params) идёт ПРОДОЛЖЕНИЕМ «Параметров» карточки ввода, если там уже есть такой
   заголовок (строка отрезка ответа, .sc-sec): два заголовка «Параметры» подряд читались как ошибка. Класс на узле с id
   — не инлайновый стиль: в форму модели не идёт. */
function scParamsCont() {
  const sp = document.getElementById('sec-params'), si = document.getElementById('sec-input');
  if (!sp || !si) return;
  const shown = (e) => { for (let n = e; n && n !== si; n = n.parentElement) { const cs = getComputedStyle(n); if (n.hidden || cs.display === 'none') return false; } return true; };
  const head = [...si.querySelectorAll('.sc-sec, #ans-seg-row')].some(e => !e.classList.contains('grp-empty') && shown(e));
  const on = head && getComputedStyle(sp).display !== 'none';
  if (sp.classList.contains('sc-cont') !== on) sp.classList.toggle('sc-cont', on);
}

/* Спрятанная человеком закраска (общий признак STATE.areaHidden) не рисуется: узел уходит из
   холста до легенды, PNG и .tex (они собирают то, что нарисовано). Протяжки (клин налога) —
   отдельные узлы без data-legend, они остаются. Зовётся из drawOverlays рядом с applyAreaColors. */
function applyAreaHidden() {
  const hid = new Set(STATE.areaHidden || []);
  const own = new Set((STATE.areaCalcList || []).map(r => areaKey(r.label)));
  const drawn = [];
  if (typeof svg === 'undefined' || !svg) { _vgDrawnKeys = drawn; return; }
  svg.selectAll('[data-legend]').each(function () {
    const k = areaKey(this.getAttribute('data-legend'));
    if (!k || own.has(k)) return;
    if (drawn.indexOf(k) < 0) drawn.push(k);
    if (hid.has(k)) this.remove();
  });
  _vgDrawnKeys = drawn;
}
/* id органов «На графике» — «Вид по умолчанию» возвращает их форму к старту модели. */
function vgFormIds() {
  const box = document.querySelector('#wrench-pop .vg-onchart');
  return box ? [...box.querySelectorAll('[id]')].map(e => e.id) : [];
}
