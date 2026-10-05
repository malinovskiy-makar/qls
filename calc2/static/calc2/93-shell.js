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

function wireShell() {
  const sw = document.getElementById('model-switch');
  if (sw) sw.addEventListener('click', () => openPicker());
  const u = document.getElementById('btn-undo'), r = document.getElementById('btn-redo');
  if (u) u.addEventListener('click', () => { if (typeof historyUndo === 'function') historyUndo(); });
  if (r) r.addEventListener('click', () => { if (typeof historyRedo === 'function') historyRedo(); });
  const sh = document.getElementById('btn-share');
  if (sh) sh.addEventListener('click', async () => {
    try {
      const link = await shareLinkOf();
      let ok = false;
      try { await navigator.clipboard.writeText(link); ok = true; } catch (e) { ok = false; }
      toast(ok ? 'Ссылка скопирована' : 'Не получилось скопировать: разрешите доступ к буферу обмена');
    } catch (e) { toast('Не получилось собрать ссылку'); }
  });
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
}
