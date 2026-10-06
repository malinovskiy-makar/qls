// Состояние модели: чистый старт, память сессии по моделям.
/* ---------------------------------------------------------------------
   ⚠️ КАНОНИЧЕСКИЙ СТАРТ МОДЕЛИ (редизайн 10.2026, фаза 1).

   Двадцать два маршрута из сорока четырёх только переключают режим
   (setMode, setMathSub, setLaborStruct, setMacroModel…) и наследовали входы
   своей семьи от того, что открывали раньше: точку касания x₀, МРОТ после
   первого входа в труд, второй спрос монополии после «Монополиста и
   внешнего рынка», границы ползунков, поднятые человеком, цены потребителя
   из соседней карточки. Одна и та же модель открывалась по-разному в
   зависимости от порядка — а значит, «отличие от старта», на котором
   держатся автосохранение, ссылка и сброс, не было определено вовсе.

   Чинить маршруты по одному значило бы держать сорок четыре списка «что
   сбросить» в согласии с литералом STATE. Вместо этого снимается ЧИСТОЕ
   состояние — ровно то, что видит модель на свежей странице: простые поля
   STATE и состояние формы (значения, границы ползунков, пометка
   boundsByHand, видимость узлов, нажатость сегментов) в конце загрузки, до
   первой модели. Вход в модель возвращает к нему, и только потом маршрут
   ставит свою обстановку. На свежей странице возврат ничего не меняет,
   поэтому контрольные числа и базовый снимок совпадают по построению.

   Расчёт сцен этот файл не трогает: он кладёт на место входы, а считает
   по-прежнему redrawAll.
   --------------------------------------------------------------------- */

/* Поля STATE, которые не являются входами модели и не переносятся ни в
   чистый старт, ни в память: следы мыши, пиксели панелей, ключ модели
   (его ставит pickScene). */
const MODEL_STATE_SKIP = new Set(['panels', 'pointerPx', 'pointerPy', 'roller', 'hoverCross', 'armedCurve',
  'sceneKey', 'resizeRedraws']);

/* Глубокая копия ПРОСТЫХ данных. Скомпилированные формулы, функции сцен и
   объекты с прототипом не копируются: это кэши расчёта, их пересобирает
   перерисовка. Такое поле возвращается как NO_COPY и не трогается. */
const NO_COPY = { noCopy: true };
function plainCopy(v, depth) {
  if (v === null || typeof v !== 'object') return typeof v === 'function' ? NO_COPY : v;
  if ((depth || 0) > 12) return NO_COPY;
  if (Array.isArray(v)) {
    const out = [];
    for (let i = 0; i < v.length; i++) { const x = plainCopy(v[i], (depth || 0) + 1); if (x === NO_COPY) return NO_COPY; out.push(x); }
    return out;
  }
  const pr = Object.getPrototypeOf(v);
  if (pr !== Object.prototype && pr !== null) return NO_COPY;
  const out = {};
  for (const k of Object.keys(v)) { const x = plainCopy(v[k], (depth || 0) + 1); if (x === NO_COPY) return NO_COPY; out[k] = x; }
  return out;
}

/* ── Состояние формы ──────────────────────────────────────────────────
   Всё, что сцена держит в разметке, а не в STATE: значения полей, границы
   и шаг ползунков, пометка «границы поставил человек», инлайновая
   видимость узлов (ею setMode и обработчики галочек прячут секции и
   регуляторы — CODE_NOTES, раздел 1: менять её способ нельзя), нажатость
   кнопок-сегментов и тумблеров. Холст и окно выбора не входят.
   ⚠️ Окна (.modal, .pop: «Поделиться», «Скачать», «Кусочная функция»,
   «Как писать формулы»…) тоже не входят: их поля — не модель. Иначе ссылка
   «Поделиться» несла в себе текст прошлой ссылки и росла от раза к разу, а
   открытие окна давало пустой шаг «Отменить» (независимое ревью фазы 11). */
function formNodes() {
  const app = document.querySelector('.app');
  if (!app) return [];
  return [...app.querySelectorAll('[id]')].filter(el => !el.closest('#chart, #graph-wrap svg, .modal, .pop'));
}
function captureForm() {
  const out = {};
  formNodes().forEach(el => {
    const r = { d: el.style.display };
    const t = el.tagName;
    if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') {
      r.v = el.value;
      if (el.type === 'checkbox' || el.type === 'radio') r.c = el.checked;
      if (el.type === 'range' || el.type === 'number') {
        r.min = el.getAttribute('min'); r.max = el.getAttribute('max'); r.step = el.getAttribute('step');
        r.bbh = el.dataset.boundsByHand || '';
      }
    }
    if (t === 'BUTTON') {
      r.cls = el.className;
      ['aria-pressed', 'aria-checked', 'aria-selected', 'aria-expanded'].forEach(a => {
        if (el.hasAttribute(a)) (r.aria = r.aria || {})[a] = el.getAttribute(a);
      });
    }
    out[el.id] = r;
  });
  // Тумблеры segToToggle (99-boot.js) без id: по порядку в разметке.
  out['@toggles'] = [...document.querySelectorAll('.app .tgl-sw')].map(el => [el.className, el.getAttribute('aria-checked')]);
  return out;
}
function applyForm(f) {
  if (!f) return;
  const changedFormula = [];
  formNodes().forEach(el => {
    const r = f[el.id];
    if (!r) return;
    if (el.style.display !== r.d) el.style.display = r.d;
    const t = el.tagName;
    if ('v' in r && el.value !== r.v) {
      if (t === 'INPUT' && (el.type === 'range' || el.type === 'number')) {
        // Границы сначала: иначе браузер зажмёт значение старыми границами.
        if (r.min == null) el.removeAttribute('min'); else el.setAttribute('min', r.min);
        if (r.max == null) el.removeAttribute('max'); else el.setAttribute('max', r.max);
      }
      el.value = r.v;
      if (el._mf) changedFormula.push(el);
    }
    if ('c' in r && el.checked !== r.c) el.checked = r.c;
    if ('min' in r) {
      if (r.min == null) el.removeAttribute('min'); else if (el.getAttribute('min') !== r.min) el.setAttribute('min', r.min);
      if (r.max == null) el.removeAttribute('max'); else if (el.getAttribute('max') !== r.max) el.setAttribute('max', r.max);
      if (r.step == null) el.removeAttribute('step'); else if (el.getAttribute('step') !== r.step) el.setAttribute('step', r.step);
      if (r.bbh) el.dataset.boundsByHand = r.bbh; else delete el.dataset.boundsByHand;
      if ('v' in r && el.value !== r.v) el.value = r.v;   // после границ — ещё раз, без зажима
    }
    if ('cls' in r && el.className !== r.cls) el.className = r.cls;
    if (r.aria) Object.entries(r.aria).forEach(([a, v]) => { if (el.getAttribute(a) !== v) el.setAttribute(a, v); });
  });
  const tg = [...document.querySelectorAll('.app .tgl-sw')];
  (f['@toggles'] || []).forEach((x, i) => {
    const el = tg[i]; if (!el) return;
    if (el.className !== x[0]) el.className = x[0];
    if (x[1] != null && el.getAttribute('aria-checked') !== x[1]) el.setAttribute('aria-checked', x[1]);
  });
  // Поле формулы MathLive показывает свою запись: переписываем её молча,
  // без события input (оно применило бы формулу к сцене).
  changedFormula.forEach(inp => {
    try { inp._mf.value = mathToLatexField(inp.value); } catch (e) {}
  });
  // Правки на месте (makeEditableValue) перерисовывают свой текст сами.
  document.querySelectorAll('.app .edval').forEach(el => { if (typeof el._repaint === 'function') el._repaint(); });
}

/* ── STATE ──────────────────────────────────────────────────────────── */
function captureStatePlain() {
  const out = {};
  Object.keys(STATE).forEach(k => {
    if (MODEL_STATE_SKIP.has(k)) return;
    const c = plainCopy(STATE[k], 0);
    if (c !== NO_COPY) out[k] = c;
  });
  return out;
}
function applyStatePlain(s) {
  if (!s) return;
  Object.keys(s).forEach(k => { STATE[k] = plainCopy(s[k], 0); });
}

/* Списки, которые сцены строят кодом из STATE: после возврата входов их надо
   пересобрать, иначе строки покажут прежнее. */
function rerenderModelLists() {
  if (typeof renderGraphRows === 'function' && document.getElementById('graph-rows') && STATE.mode === 'graph') renderGraphRows();
  if (typeof renderMmRows === 'function' && document.getElementById('mm-rows')) renderMmRows();
  if (typeof renderPpfSumRows === 'function') renderPpfSumRows();
  if (typeof renderIneqGroupsTable === 'function') renderIneqGroupsTable();
  if (typeof renderMarkList === 'function') renderMarkList();
  if (typeof renderVertList === 'function') renderVertList();
}

/* Узлы, которые сцены пишут ТЕКСТОМ по состоянию (пояснения каскада
   вмешательства, подписи способа ввода издержек и т. п.): в форме их нет,
   поэтому после возврата входов их пересобирают те же функции, что и при
   обычной правке. Каждая только читает STATE и пишет разметку. */
/* После возврата входов пульт обязан пересобраться: чипы букв держат ссылку
   на объект параметра, с которым их собрали, и после замены STATE.params
   показывали бы прежние границы. Тот же приём, что в resetDecor. Кэши
   расчёта, привязанные к подписи входов (costsSig и т. п.), гасим: их данные
   (скомпилированные формулы) в простом состоянии не хранятся. */
function forceRebuildAfterApply() {
  const panel = document.getElementById('params-panel');
  if (panel && typeof PULT_REBUILD !== 'undefined') { panel._extraSig = PULT_REBUILD; panel._curveSig = PULT_REBUILD; }
  Object.keys(STATE).forEach(k => { if (/Sig$/.test(k)) STATE[k] = null; });
}

function syncUiFromState() {
  ['applyIntervCascade', 'syncTaxHint', 'syncPcHint', 'syncQuotaHint', 'syncLabelSizeSeg', 'syncCostsInputMode']
    .forEach(fn => { if (typeof window[fn] === 'function') window[fn](); });
}

/* ── Чистый старт ───────────────────────────────────────────────────── */
let _pristine = null;
function capturePristine() {
  _pristine = {
    keys: new Set(Object.keys(STATE)),   // поля, которые сцены заводят позже, при возврате убираются
    state: captureStatePlain(),
    form: captureForm(),
    view: { Qmin: CONFIG.Qmin, Qmax: CONFIG.Qmax, Pmin: CONFIG.Pmin, Pmax: CONFIG.Pmax },
    /* Поля графика тоже: сцены «Математики» берут CONFIG.margin как есть, и
       «Касательная» после «Спроса и предложения» получала поля на 2 px уже. */
    margin: Object.assign({}, CONFIG.margin),
  };
}
function restorePristine() {
  if (!_pristine) return;
  applyForm(_pristine.form);
  // Поля, которых на свежей странице нет (consFit, ppfCompare… сцены заводят их
  // при первом расчёте): их присутствие уже отличало бы модель от свежей.
  Object.keys(STATE).forEach(k => { if (!_pristine.keys.has(k) && !MODEL_STATE_SKIP.has(k)) delete STATE[k]; });
  applyStatePlain(_pristine.state);
  CONFIG.Qmin = _pristine.view.Qmin; CONFIG.Qmax = _pristine.view.Qmax;
  CONFIG.Pmin = _pristine.view.Pmin; CONFIG.Pmax = _pristine.view.Pmax;
  Object.assign(CONFIG.margin, _pristine.margin);
  rerenderModelLists();
}

/* ── Память сессии: «ушёл в другую модель и вернулся — мои правки на месте» ──
   Прежний снимок (SNAPSHOT_KEYS, 60-overlays.js) держал оформление, формулы
   и ставку, а цены потребителя, мировую цену, МРОТ, макро и границы
   ползунков переживали уход только потому, что их никто не сбрасывал.
   Теперь вход сбрасывает всё к чистому старту, поэтому память хранит ВСЕ
   входы: простые поля STATE по ссылке (вход в другую модель заменяет их
   копиями из чистого старта, и сохранённое никто не правит) и форму. */
function captureMemory() {
  const st = {};
  Object.keys(STATE).forEach(k => { if (!MODEL_STATE_SKIP.has(k)) st[k] = STATE[k]; });
  return { state: st, form: captureForm(), margin: Object.assign({}, CONFIG.margin) };
}
function applyMemory(m) {
  if (!m) return;
  applyForm(m.form);
  Object.keys(m.state).forEach(k => { STATE[k] = m.state[k]; });
  if (m.margin) Object.assign(CONFIG.margin, m.margin);
  forceRebuildAfterApply();
  syncUiFromState();
  rerenderModelLists();
}

/* ── Слой состояния: собрать модель в простой объект и применить обратно ──
   (редизайн 10.2026, фаза 2). Этим объектом пользуются история, автосохранение
   и ссылка «Поделиться». В нём ПОЛНЫЕ входы модели, а не отличия от старта:
   ссылка обязана открывать то же самое и после того, как стартовые значения
   в коде поменяются.

   Кривые — единственный вход, в котором лежат скомпилированные формулы. Они
   сохраняются простыми полями (запись, форма, роль, цвет, имя, видимость,
   разбор прямой), а формула при применении пересобирается теми же функциями,
   что и при наборе: compileFormula и buildCurveFromQP. Суммарные кривые
   «Сложения» пересобирает sumRebuild на первой же перерисовке. */
const MODEL_STATE_VERSION = 1;
const CURVE_CODE_KEYS = new Set(['compiled', 'fn', 'srcCompiled']);
function serializeCurves(list) {
  return (list || []).map(c => {
    const o = {};
    // Какие служебные поля у кривой были: пересборка заводит ровно их.
    o._code = Object.keys(c).filter(k => CURVE_CODE_KEYS.has(k));
    Object.keys(c).forEach(k => {
      if (CURVE_CODE_KEYS.has(k)) return;
      const x = plainCopy(c[k], 0);
      if (x !== NO_COPY) o[k] = x;
    });
    return o;
  });
}
function rebuildCurves(list) {
  return (list || []).map(o => {
    const c = plainCopy(o, 0);
    const code = c._code || ['compiled', 'fn'];
    delete c._code;
    code.forEach(k => { c[k] = null; });
    if (c.kind === 'sum' || c.kind === 'vertical' || !c.expr) return c;
    if (c.srcForm === 'QP') {
      const b = buildCurveFromQP(c.expr);
      if (!b.error) { c.fn = b.fn; c.srcCompiled = b.srcCompiled; }
    } else {
      const r = compileFormula(c.expr);
      if (!r.error) c.compiled = r.compiled;
    }
    return c;
  });
}

/* Ключ модели для хранения: синонимы tax и tax-adv — та же модель «Налоги и
   субсидии» (84-picker.js), и в автосохранении и ссылке у неё один ключ. */
function modelKeyOf(key) {
  const k = key || STATE.sceneKey;
  return (k === 'tax' || k === 'tax-adv') ? 'taxes' : k;
}

function collectModelState() {
  const state = captureStatePlain();
  state.curves = serializeCurves(STATE.curves);
  return {
    v: MODEL_STATE_VERSION,
    key: modelKeyOf(),
    // Маршрут-синоним (tax, tax-adv) хранится отдельно: у них свои тексты разбора.
    route: STATE.sceneKey,
    state,
    form: captureForm(),
    view: { Qmin: CONFIG.Qmin, Qmax: CONFIG.Qmax, Pmin: CONFIG.Pmin, Pmax: CONFIG.Pmax },
    margin: Object.assign({}, CONFIG.margin),
    counters: { curve: curveCounter, mark: markCounter, area: areaCalcCounter },
  };
}

/* Применить собранное: модель открывается с канонического старта (pickScene
   без памяти сессии), затем поверх кладутся входы. Порядок обязателен: форма
   (границы ползунков раньше значений), потом STATE, потом пересборка
   списков, пульта и холста. */
function applyModelState(s) {
  if (!s || s.v !== MODEL_STATE_VERSION || !s.key || !SCENE_ROUTE[s.key]) return false;
  const route = (s.route && SCENE_ROUTE[s.route] && modelKeyOf(s.route) === s.key) ? s.route : s.key;
  forgetSceneSnapshot(route);
  pickScene(route);
  applyForm(s.form);
  Object.keys(s.state).forEach(k => {
    if (k === 'curves') return;
    STATE[k] = plainCopy(s.state[k], 0);
  });
  STATE.curves = rebuildCurves(s.state.curves);
  STATE._sumSig = null;   // суммарные кривые пересобрать заново
  forceRebuildAfterApply();
  if (s.margin) Object.assign(CONFIG.margin, s.margin);
  if (s.view) { CONFIG.Qmin = s.view.Qmin; CONFIG.Qmax = s.view.Qmax; CONFIG.Pmin = s.view.Pmin; CONFIG.Pmax = s.view.Pmax; }
  if (s.counters) { curveCounter = s.counters.curve; markCounter = s.counters.mark; areaCalcCounter = s.counters.area; }
  syncUiFromState();
  rerenderModelLists();
  renderCurveList();
  if (typeof updatePult === 'function') updatePult();
  redrawAll();
  if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
  return true;
}
