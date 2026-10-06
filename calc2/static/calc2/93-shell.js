// Шапка модели и панель холста нового экрана (редизайн 10.2026, фаза 5а).
/* ---------------------------------------------------------------------
   Здесь только обвязка кнопок: «Все модели», переключатель модели, статус
   «Сохранено», «Отменить» и «Повторить», «Поделиться», «Развернуть
   график», масштаб в процентах. Своей логики модели нет: история, ссылка и
   сохранение живут в 91-session.js, масштаб — в 52-modes.js.
   --------------------------------------------------------------------- */

/* Блок модели над её именем — из окна выбора: карточка лежит в своём блоке,
   у блока есть подпись. Второй список держать в согласии не нужно. */
function modelBlockOf(key) {
  const card = document.querySelector('#scene-picker .scard[data-scene="' + CSS.escape(key || '') + '"]');
  const g = card ? card.closest('.picker-group') : null;
  return g ? (g.getAttribute('aria-label') || '') : '';
}
function syncModelHead() {
  const b = document.getElementById('model-block');
  if (b) b.textContent = modelBlockOf(STATE.sceneKey);
  const c = (typeof historyCan === 'function') ? historyCan() : { undo: false, redo: false };
  const u = document.getElementById('btn-undo'), r = document.getElementById('btn-redo');
  if (u) u.disabled = !c.undo;
  if (r) r.disabled = !c.redo;
}

/* Масштаб в процентах: стартовое окно модели к нынешнему (по оси x главной
   панели). У сцен со своими панелями считаем по первой. */
let _zoomBase = null;
function syncZoomLevel() {
  const el = document.getElementById('zoom-level');
  if (!el || typeof viewWindow !== 'function') return;
  let w;
  try { w = viewWindow((STATE.panels && STATE.panels[0]) ? STATE.panels[0].id : undefined); } catch (e) { return; }
  if (!w) return;
  const span = Math.abs(w.x1 - w.x0);
  if (!_zoomBase || _zoomBase.key !== STATE.sceneKey || !STATE.viewDirty) _zoomBase = { key: STATE.sceneKey, span };
  const pct = span > 0 ? Math.round(100 * _zoomBase.span / span) : 100;
  el.textContent = pct + ' %';
}

/* «Развернуть график»: колонки прячутся классом (не атрибутом hidden: по
   нему fieldActive решил бы, что поля умерли, CODE_NOTES 1), холст берёт всю
   ширину. При возврате поля формул в колонках достраиваются заново
   (CODE_NOTES 13.5): показ колонки перерисовку сам не вызывает. */
function setFocusMode(on) {
  document.body.classList.toggle('cv-focus', !!on);
  const b = document.getElementById('btn-focus');
  if (b) {
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.setAttribute('data-tip', on ? 'Вернуть колонки' : 'Развернуть график');
    b.setAttribute('aria-label', on ? 'Вернуть колонки' : 'Развернуть график');
  }
  if (!on) afterColumnShown();
}
function afterColumnShown() {
  ['flushMathfieldsSoon', 'refitFinalMathSoon', 'fitFormulaFieldsSoon'].forEach(fn => {
    if (typeof window[fn] === 'function') window[fn]();
  });
}

/* Инструмент холста: «Курсор», «Точка», «Площадь» (README макета, 7.1).
   Своих режимов нет — это прежние «Добавить точку → Указать на графике» и
   «Площади → Между точками»; состояние спрашивается у canvasMode(). */
function syncToolSeg() {
  const m = (typeof canvasMode === 'function') ? canvasMode() : 'look';
  [['tool-cursor', 'look'], ['tool-point', 'mark'], ['tool-area', 'vert']].forEach(([id, want]) => {
    const b = document.getElementById(id);
    if (b) b.setAttribute('aria-pressed', m === want ? 'true' : 'false');
  });
}
function setTool(which) {
  if (STATE.markArm && which !== 'mark' && typeof cancelMarkDraft === 'function') cancelMarkDraft();
  if (STATE.vertArm && which !== 'vert' && typeof armVerts === 'function') armVerts(false);
  if (which === 'mark' && !STATE.markArm) {
    if (typeof startMarkDraft === 'function') startMarkDraft();
    const m = (typeof pendingMark === 'function') ? pendingMark() : null;
    if (m) { m.mode = 'graph'; if (typeof renderMarkList === 'function') renderMarkList(); }
    if (typeof armMark === 'function') armMark(true);
  }
  if (which === 'vert' && !STATE.vertArm && typeof setAreaCalcMode === 'function') setAreaCalcMode('poly');
  syncToolSeg();
}

function wireShell() {
  [['tool-cursor', 'look'], ['tool-point', 'mark'], ['tool-area', 'vert']].forEach(([id, w]) => {
    const b = document.getElementById(id);
    if (b) b.addEventListener('click', () => setTool(w));
  });
  const sw = document.getElementById('model-switch');
  if (sw) {
    sw.setAttribute('aria-haspopup', 'dialog');
    sw.setAttribute('aria-expanded', 'false');
    // Переключатель модели — окно под шапкой (README макета, раздел 10).
    sw.addEventListener('click', (e) => { e.stopPropagation(); (typeof openSwitcher === 'function') ? openSwitcher(sw) : openPicker(); });
  }
  // 760–1239 px: «Ответ» выезжает панелью справа.
  const ab = document.getElementById('btn-answer');
  const setAns = (on) => {
    document.body.classList.toggle('ans-open', on);
    if (ab) ab.setAttribute('aria-expanded', on ? 'true' : 'false');
    if (on) afterColumnShown();
  };
  if (ab) ab.addEventListener('click', () => setAns(!document.body.classList.contains('ans-open')));
  /* Открытая панель ложится поверх правого края холста вместе с кнопкой
     «Ответ»: закрывают её крестик в шапке, Esc и щелчок мимо панели. */
  const ax = document.getElementById('ans-x');
  if (ax) ax.addEventListener('click', () => { setAns(false); if (ab && ab.offsetParent) ab.focus({ preventScroll: true }); });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !document.body.classList.contains('ans-open')) return;
    if (document.querySelector('.pop.open, .modal.open, .cpick-menu.open')) return;
    setAns(false);
  });
  document.addEventListener('pointerdown', (e) => {
    if (!document.body.classList.contains('ans-open')) return;
    if (e.target.closest('#params-panel, #btn-answer, .pop, .modal, .cpick-menu, #hint-tip')) return;
    setAns(false);
  }, true);
  // Телефон: вкладки «Условие» / «Ответ» / «Разбор»; каждая показанная колонка
  // достраивает поля формул и перемеряет формулы (COVERAGE, раздел 8).
  const tabs = document.querySelectorAll('#ph-tabs .ph-tab');
  const setTab = (name) => {
    ['cond', 'ans', 'ex'].forEach(t => document.body.classList.toggle('ph-' + t, t === name));
    tabs.forEach(b => b.setAttribute('aria-selected', b.dataset.tab === name ? 'true' : 'false'));
    afterColumnShown();
  };
  tabs.forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
  setTab('cond');
  const u = document.getElementById('btn-undo'), r = document.getElementById('btn-redo');
  if (u) u.addEventListener('click', () => { if (typeof historyUndo === 'function') historyUndo(); });
  if (r) r.addEventListener('click', () => { if (typeof historyRedo === 'function') historyRedo(); });
  // «Поделиться» открывает окно со ссылкой (92-ui-kit.js, фаза 5б).
  const fb = document.getElementById('btn-focus');
  if (fb) fb.addEventListener('click', () => setFocusMode(!document.body.classList.contains('cv-focus')));
  // Статус сохранения: «Сохраняю…» на время записи, через 650 мс снова «Сохранено».
  const st = document.getElementById('save-status-text');
  let stT = null;
  window.addEventListener('calc2:saving', () => { if (st) st.textContent = 'Сохраняю…'; clearTimeout(stT); });
  window.addEventListener('calc2:saved', () => {
    clearTimeout(stT);
    stT = setTimeout(() => { if (st) st.textContent = 'Сохранено'; }, 650);
  });
  window.addEventListener('calc2:history', syncModelHead);
  window.addEventListener('calc2:changing', syncZoomLevel);
  syncModelHead();
  wirePhoneMore();
}

/* ── Телефон: лист «Действия» за кнопкой «⋯» (README макета, раздел 3) ─────
   На узком экране в шапке модели и в панели холста места нет, поэтому
   «Повторить», «Сбросить» и кнопки масштаба переезжают строками в лист. Узлы
   те же (с теми же id и обработчиками), не копии: шире 759 px они
   возвращаются на прежнее место. «Сбросить» и «Повторить» закрывают лист,
   масштаб — нет: его жмут подряд. */
const PH_MORE = [['btn-redo', 'Повторить'], ['btn-model-reset', null], ['dock-export', null], ['btn-zoomout', 'Отдалить'], ['btn-zoomin', 'Приблизить']];
/* «Сначала сам» на телефоне — в шапке «Ответа» (README макета, 9): в шапке
   модели места нет (README 3: «Все модели», имя, «Отменить», «⋯», «Поделиться»). */
const PH_ANSWER = ['btn-self'];
const _phHome = {};
function phMoreLayout(phone) {
  const list = document.getElementById('ph-more-list');
  if (!list) return;
  if (!phone && typeof closePop === 'function') {
    const pop = document.getElementById('ph-more-pop');
    if (pop && pop.classList.contains('open')) closePop();
  }
  const ansHead = document.querySelector('#params-panel .col-head');
  PH_ANSWER.forEach(id => {
    const b = document.getElementById(id);
    if (!b || !ansHead) return;
    if (!_phHome[id]) _phHome[id] = { parent: b.parentElement, next: b.nextSibling };
    if (phone) { if (b.parentElement !== ansHead) ansHead.appendChild(b); return; }
    const h = _phHome[id];
    if (b.parentElement === h.parent) return;
    if (h.next && h.next.parentElement === h.parent) h.parent.insertBefore(b, h.next);
    else h.parent.appendChild(b);
  });
  PH_MORE.forEach(([id, label]) => {
    const b = document.getElementById(id);
    if (!b) return;
    if (!_phHome[id]) _phHome[id] = { parent: b.parentElement, next: b.nextSibling };
    if (label && !b.querySelector(':scope > .ph-lab')) {
      const t = document.createElement('span');
      t.className = 'ph-lab'; t.textContent = label;
      b.appendChild(t);
    }
    if (phone) { if (b.parentElement !== list) list.appendChild(b); return; }
    const h = _phHome[id];
    if (b.parentElement === h.parent) return;
    if (h.next && h.next.parentElement === h.parent) h.parent.insertBefore(b, h.next);
    else h.parent.appendChild(b);
  });
}
function wirePhoneMore() {
  const btn = document.getElementById('btn-ph-more');
  const pop = document.getElementById('ph-more-pop');
  if (!btn || !pop) return;
  btn.addEventListener('click', (e) => { e.stopPropagation(); openPop(btn, pop, { noFocus: true }); });
  const x = document.getElementById('ph-more-x');
  if (x) x.addEventListener('click', () => closePop());
  pop.addEventListener('click', (e) => {
    const b = e.target.closest('#btn-redo, #btn-model-reset, #dock-export');
    if (b) setTimeout(() => { if (pop.classList.contains('open')) closePop(); }, 0);
  });
  const mq = window.matchMedia('(max-width: 759px)');
  phMoreLayout(mq.matches);
  const on = () => phMoreLayout(mq.matches);
  if (mq.addEventListener) mq.addEventListener('change', on); else mq.addListener(on);
}
