// История по моделям, автосохранение, ссылка «Поделиться», восстановление.
/* ---------------------------------------------------------------------
   Редизайн 10.2026, фаза 3. Всё здесь стоит на слое состояния
   (89-model-state.js): снимок модели — collectModelState(), применение —
   applyModelState(). Расчёт сцен этот файл не трогает.

   ИСТОРИЯ. Прежняя отмена писала шаг в восьми местах, и то, что их не
   звало (ползунки, ручки на холсте, вмешательство, галочки, цвета), отменить
   было нельзя. Теперь шаг пишется там, где модель реально изменилась: после
   каждой перерисовки, когда экран затих на 300 мс, собранное состояние
   сравнивается с последним устойчивым, и если оно другое — прежнее уходит в
   стек отмены этой модели. Поэтому шаг покрывает любое изменение, а снимок
   не ложится на каждый кадр протяжки (решение штаба 13.08: перерисовка 100 мс).
   pushUndo(метка) остаётся единой дверью для мест, которые и раньше
   объявляли «сейчас будет правка»: метка задаёт склейку (правки одного органа
   с паузой меньше 900 мс — один шаг).
   Вне истории только масштаб и сдвиг окна: при отмене окно остаётся тем, что
   на экране.

   ⚠️ ВОССТАНОВЛЕНИЕ НЕ ВНУТРИ pickScene. Приборы зовут pickScene сотни раз;
   если бы она читала localStorage, контрольные числа зависели бы от того, что
   лежит в браузере. Состояние из хранилища и из ссылки поднимается только при
   загрузке страницы (restoreOnLoad) и при выборе модели человеком
   (openModelByUser). resetSceneMemory() чистит и историю.
   --------------------------------------------------------------------- */

const HIST_MAX = 60;          // шагов на модель (не меньше 40 по спецификации)
const HIST_GLUE_MS = 900;     // склейка правок одного органа
const HIST_QUIET_MS = 300;    // затишье после перерисовки: тогда и сверяем
const STORE_PREFIX = 'calc2.v1.';

const _hist = {};             // ключ модели → { undo, redo, last, lastSig, at, label }
let _histLabel = null;        // орган последнего действия человека
let _histTimer = null;
let _histMute = 0;            // > 0 — изменения не пишутся (применение снимка)
let _fromLink = false;        // модель открыта ссылкой: в хранилище не пишем до первой правки
/* Было ли действие человека (ввод, нажатие, pushUndo) с последней сверки.
   Сцены досчитывают себя и после входа (сложение КПВ заводит свои данные
   на следующем кадре): такое изменение — не правка, его история впитывает
   молча, иначе «Отменить» вела бы в недосчитанную модель. */
let _histTouched = false;

function histOf(key) {
  const k = key || modelKeyOf();
  return _hist[k] || (_hist[k] = { undo: [], redo: [], last: null, lastSig: '', at: 0, label: null });
}

/* Подпись состояния для сравнения: без окна и того, что считается от окна
   (масштаб и сдвиг в историю не входят). */
const HIST_VIEW_KEYS = ['zoomLock', 'viewDirty', 'panelWin', 'tanTop', 'tanBot', 'crosses',
  'mathXmin', 'mathXmax', 'mathYmin', 'mathYmax'];
function histSig(s) {
  const st = Object.assign({}, s.state);
  HIST_VIEW_KEYS.forEach(k => { delete st[k]; });
  Object.keys(st).forEach(k => { if (/Sig$/.test(k)) delete st[k]; });
  return JSON.stringify([st, s.form]);
}

/* Раскрытость карточек и панелей — вид рабочего места, а не модель: отмена,
   повтор и «Вернуть» её не трогают (pickScene внутри применения закрыл бы
   карточки, как при входе в новую модель). */
function captureOpenUi() {
  const ids = [];
  document.querySelectorAll('.app .open-card[id], .app .fold-body.open[id], .app .side-part.open-card[id]').forEach(el => ids.push(el.id));
  const tools = document.getElementById('tools-panel'), params = document.getElementById('params-panel');
  return { ids, tools: tools ? !tools.classList.contains('collapsed') : null, params: params ? !params.classList.contains('collapsed') : null };
}
function restoreOpenUi(u) {
  if (!u) return;
  u.ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.classList.contains('fold-body')) {
      el.classList.add('open');
      const btn = document.querySelector('.fold-btn[aria-controls="' + id + '"]');
      if (btn) btn.setAttribute('aria-expanded', 'true');
    } else el.classList.add('open-card');
  });
  if (u.tools !== null && typeof setToolsOpen === 'function') setToolsOpen(u.tools);
  if (u.params !== null && typeof setParamsOpen === 'function') setParamsOpen(u.params);
  if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
}

/* Применить снимок истории, оставив окно тем, что на экране. */
function applyKeepView(s) {
  const cur = collectModelState();
  const t = JSON.parse(JSON.stringify(s));
  t.view = cur.view; t.margin = cur.margin;
  HIST_VIEW_KEYS.forEach(k => { if (k in cur.state) t.state[k] = cur.state[k]; else delete t.state[k]; });
  const ui = captureOpenUi();
  _histMute++;
  try { applyModelState(t); } finally { _histMute--; }
  restoreOpenUi(ui);
}

/* Устойчивое состояние модели: от него считаются следующие правки. */
function historyBaseline() {
  if (!STATE.sceneKey) return;
  _histTouched = false;
  const h = histOf();
  const s = collectModelState();
  h.last = s; h.lastSig = histSig(s); h.at = 0; h.label = null;
  notifyHistory();
}

function historyCheck() {
  _histTimer = null;
  if (_histMute || !STATE.sceneKey || typeof collectModelState !== 'function') return;
  const app = document.querySelector('.app');
  if (app && app.hasAttribute('inert')) return;   // модель под окном выбора
  const h = histOf();
  const s = collectModelState();
  const sig = histSig(s);
  if (!h.last) { h.last = s; h.lastSig = sig; return; }
  if (sig === h.lastSig) return;
  if (!_histTouched) { h.last = s; h.lastSig = sig; return; }
  _histTouched = false;
  const now = Date.now();
  const glue = _histLabel && _histLabel === h.label && (now - h.at) < HIST_GLUE_MS;
  if (!glue) {
    h.undo.push(h.last);
    if (h.undo.length > HIST_MAX) h.undo.shift();
  }
  h.redo.length = 0;
  h.last = s; h.lastSig = sig; h.at = now; h.label = _histLabel;
  _fromLink = false;
  dropShareHash();
  autosaveModel(s);
  notifyHistory();
}

/* Зовётся в конце каждой перерисовки (60-overlays.js, redrawAll). */
function historyAfterRedraw() {
  if (_histMute) return;
  clearTimeout(_histTimer);
  _histTimer = setTimeout(historyCheck, HIST_QUIET_MS);
  if (typeof window.CustomEvent === 'function') window.dispatchEvent(new CustomEvent('calc2:changing'));
}

/* Единая дверь «сейчас будет правка» (pushUndo в 60-overlays.js). */
function historyMark(label) {
  if (label) _histLabel = label;
  _histTouched = true;
}

function historyUndo() {
  clearTimeout(_histTimer); historyCheck();   // незаписанная правка — сначала в историю
  const h = histOf();
  if (!h.undo.length) return false;
  const cur = h.last || collectModelState();
  const prev = h.undo.pop();
  h.redo.push(cur);
  applyKeepView(prev);
  h.last = collectModelState(); h.lastSig = histSig(h.last); h.label = null;
  autosaveModel(h.last);
  notifyHistory();
  return true;
}
function historyRedo() {
  clearTimeout(_histTimer); historyCheck();
  const h = histOf();
  if (!h.redo.length) return false;
  const next = h.redo.pop();
  h.undo.push(h.last || collectModelState());
  applyKeepView(next);
  h.last = collectModelState(); h.lastSig = histSig(h.last); h.label = null;
  autosaveModel(h.last);
  notifyHistory();
  return true;
}
function historyCan() {
  const h = STATE.sceneKey ? histOf() : null;
  return { undo: !!(h && h.undo.length), redo: !!(h && h.redo.length) };
}
function historyClearAll() { Object.keys(_hist).forEach(k => { delete _hist[k]; }); }

function notifyHistory() {
  if (typeof window.CustomEvent === 'function') window.dispatchEvent(new CustomEvent('calc2:history', { detail: historyCan() }));
}

/* Метка действия человека: орган, которого коснулись. По ней склеиваются
   правки одного органа. */
function histLabelOf(el) {
  if (!el || !el.closest) return null;
  const n = el.closest('[id]');
  return n ? n.id : null;
}
['pointerdown', 'keydown', 'input', 'change'].forEach(ev => {
  document.addEventListener(ev, (e) => {
    if (!e.isTrusted) return;   // события, которые шлёт сам код, — не действие человека
    const l = histLabelOf(e.target); if (l) _histLabel = l;
    _histTouched = true;
  }, true);
});

/* ── Хранилище ────────────────────────────────────────────────────────
   localStorage может не быть вовсе (приватное окно, запрет сайта): тогда
   страница работает как раньше, просто ничего не помнит. */
function storeGet(k) { try { return window.localStorage.getItem(STORE_PREFIX + k); } catch (e) { return null; } }
function storeSet(k, v) { try { window.localStorage.setItem(STORE_PREFIX + k, v); return true; } catch (e) { return false; } }

/* Форма в хранилище и в ссылке: значения полей — полностью (это входы),
   видимость и нажатость узлов — только отличия от чистого старта (это
   производное от входов, и без сжатия ссылка выходила втрое длиннее). */
function compactModelState(s) {
  const pf = (_pristine && _pristine.form) || {};
  const form = {};
  Object.entries(s.form).forEach(([id, r]) => {
    if (id === '@toggles') { if (JSON.stringify(r) !== JSON.stringify(pf[id])) form[id] = r; return; }
    const p = pf[id] || {};
    const o = {};
    ['v', 'c', 'min', 'max', 'step', 'bbh'].forEach(k => { if (k in r) o[k] = r[k]; });
    ['d', 'cls'].forEach(k => { if (k in r && r[k] !== p[k]) o[k] = r[k]; });
    if (r.aria && JSON.stringify(r.aria) !== JSON.stringify(p.aria)) o.aria = r.aria;
    if (Object.keys(o).length) form[id] = o;
  });
  return Object.assign({}, s, { form });
}
function expandModelState(c) {
  const pf = (_pristine && _pristine.form) || {};
  const form = {};
  // Массив тумблеров (@toggles) копируется массивом, остальное — объектами.
  Object.entries(pf).forEach(([id, r]) => { form[id] = Array.isArray(r) ? r.slice() : Object.assign({}, r); });
  Object.entries(c.form || {}).forEach(([id, r]) => { form[id] = Array.isArray(r) ? r.slice() : Object.assign(form[id] || {}, r); });
  return Object.assign({}, c, { form });
}

function autosaveModel(s) {
  if (_fromLink) return;
  const key = s.key;
  if (!key) return;
  if (typeof window.CustomEvent === 'function') window.dispatchEvent(new CustomEvent('calc2:saving'));
  const ok = storeSet('model.' + key, JSON.stringify({ t: Date.now(), s: compactModelState(s) }));
  if (ok) {
    let rec = [];
    try { rec = JSON.parse(storeGet('recent') || '[]'); } catch (e) { rec = []; }
    rec = [{ k: key, t: Date.now() }].concat(rec.filter(x => x && x.k !== key)).slice(0, 10);
    storeSet('recent', JSON.stringify(rec));
  }
  if (typeof window.CustomEvent === 'function') window.dispatchEvent(new CustomEvent('calc2:saved', { detail: { ok } }));
}
function forgetAutosaves() {
  try {
    const ks = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k && k.indexOf(STORE_PREFIX) === 0) ks.push(k);
    }
    ks.forEach(k => window.localStorage.removeItem(k));
  } catch (e) { /* хранилища нет — забывать нечего */ }
}
function savedModel(key) {
  try {
    const r = JSON.parse(storeGet('model.' + key) || 'null');
    return r && r.s ? { t: r.t, s: expandModelState(r.s) } : null;
  } catch (e) { return null; }
}
function recentModels() {
  try { return JSON.parse(storeGet('recent') || '[]').filter(x => x && SCENE_ROUTE[x.k]); } catch (e) { return []; }
}

/* ── Адрес: ?m= модели и #s= ссылки ───────────────────────────────────
   Прочие параметры адреса (например, ?texState=1, О22) сохраняются. */
function writeModelToUrl(key) {
  try {
    const u = new URL(location.href);
    if (u.searchParams.get('m') === key) return;
    u.searchParams.set('m', key);
    history.replaceState(history.state, '', u.pathname + '?' + u.searchParams.toString() + u.hash);
  } catch (e) { /* адрес не обязателен */ }
}
function dropShareHash() {
  try {
    if (!/^#s=/.test(location.hash)) return;
    history.replaceState(history.state, '', location.pathname + location.search);
  } catch (e) { /* ничего */ }
}

/* Ссылка: JSON состояния, сжатый deflate-raw (если браузер умеет), в base64url.
   Первый знак после версии говорит, сжато ли: «z» — да, «j» — нет. */
function b64urlEncode(bytes) {
  let s = ''; bytes.forEach(b => { s += String.fromCharCode(b); });
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function b64urlDecode(t) {
  const s = atob(t.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((t.length + 3) % 4));
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}
async function shareLinkOf(s) {
  const json = JSON.stringify(compactModelState(s || collectModelState()));
  const raw = new TextEncoder().encode(json);
  let tag = 'j', bytes = raw;
  if (typeof CompressionStream === 'function') {
    try {
      const cs = new Blob([raw]).stream().pipeThrough(new CompressionStream('deflate-raw'));
      bytes = new Uint8Array(await new Response(cs).arrayBuffer());
      tag = 'z';
    } catch (e) { bytes = raw; tag = 'j'; }
  }
  const u = new URL(location.href);
  u.searchParams.set('m', modelKeyOf());
  return u.origin + u.pathname + '?' + u.searchParams.toString() + '#s=1' + tag + b64urlEncode(bytes);
}
async function decodeShare(hash) {
  // После данных может стоять «&self=1» (галочка «Сначала сам» в окне «Поделиться»).
  const m = /^#s=1([zj])([A-Za-z0-9_-]+)(?:&[A-Za-z0-9_=&-]*)?$/.exec(hash || '');
  if (!m) throw new Error('не тот формат');
  let bytes = b64urlDecode(m[2]);
  if (m[1] === 'z') {
    const ds = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
    bytes = new Uint8Array(await new Response(ds).arrayBuffer());
  }
  const c = JSON.parse(new TextDecoder().decode(bytes));
  if (!c || c.v !== MODEL_STATE_VERSION || !SCENE_ROUTE[c.key]) throw new Error('не та версия или модель');
  return expandModelState(c);
}

/* ── Открытие модели человеком: экран выбора, переключатель, «Продолжить» ──
   Памяти сессии нет — поднимаем автосохранение этой модели. */
function openModelByUser(key) {
  const k = modelKeyOf(key);
  const hadMemory = typeof _sceneSnaps !== 'undefined' && (_sceneSnaps[key] || _sceneSnaps[k]);
  pickScene(key);
  if (!hadMemory) {
    const sv = savedModel(k);
    if (sv) {
      _histMute++;
      try { applyModelState(Object.assign({}, sv.s, { route: key === k ? sv.s.route : key })); } finally { _histMute--; }
    }
  }
  historyBaseline();
}

/* ── Загрузка страницы ────────────────────────────────────────────────
   #s= — открыть состояние из ссылки (в хранилище ничего не пишется, пока
   человек не начнёт править; адрес с #s= уходит после первой правки);
   ?m= — открыть модель с её автосохранением (перезагрузка возвращает модель).
   Ничего из этого нет — окно выбора, как раньше. Возвращает true, если
   модель открыта (асинхронная ссылка — тоже true: модель откроется сама). */
function restoreOnLoad() {
  let params; try { params = new URLSearchParams(location.search); } catch (e) { params = null; }
  const mKey = params && params.get('m');
  const want = mKey && SCENE_ROUTE[mKey] ? mKey : null;
  if (/^#s=/.test(location.hash || '')) {
    const fallback = want || 'sd';
    decodeShare(location.hash).then(s => {
      _fromLink = true;
      _histMute++;
      try { applyModelState(s); } finally { _histMute--; }
      historyBaseline();
    }).catch(() => {
      dropShareHash();
      openModelByUser(fallback);
      if (typeof toast === 'function') toast('Ссылка повреждена: открыта модель «' + (SCENE_NAMES[fallback] || fallback) + '» в исходном виде');
    });
    return true;
  }
  if (want) { openModelByUser(want); return true; }
  return false;
}

/* «Сбросить»: стартовое состояние модели одним шагом истории, тост с
   «Вернуть» возвращает прежнее; запись автосохранения заменяется стартовой. */
function resetModelWithUndo() {
  const key = STATE.sceneKey;
  if (!key) return;
  clearTimeout(_histTimer); historyCheck();
  const h = histOf();
  const before = h.last || collectModelState();
  if (typeof forgetSceneSnapshot === 'function') forgetSceneSnapshot(key);
  const ui = captureOpenUi();
  _histMute++;
  try { pickScene(key); } finally { _histMute--; }
  restoreOpenUi(ui);
  const now = collectModelState();
  if (histSig(now) !== histSig(before)) {
    h.undo.push(before);
    if (h.undo.length > HIST_MAX) h.undo.shift();
    h.redo.length = 0;
  }
  h.last = now; h.lastSig = histSig(now); h.label = null;
  autosaveModel(now);
  notifyHistory();
  if (typeof toast === 'function') toast('Модель сброшена к стартовым функциям', {
    action: 'Вернуть', ms: 6500,
    fn: () => {
      // Успели уйти в другую модель — «Вернуть» прежней модели здесь не к месту.
      if (STATE.sceneKey !== key) return;
      const hh = histOf();
      hh.undo.push(hh.last);
      applyKeepView(before);
      hh.last = collectModelState(); hh.lastSig = histSig(hh.last);
      autosaveModel(hh.last);
      notifyHistory();
    },
  });
}
