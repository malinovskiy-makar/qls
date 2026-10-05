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
function parkCurveSliders() {
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
