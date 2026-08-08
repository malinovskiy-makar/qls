// Готовые сцены, окно выбора сценария, маршруты карточек.
/* ---------------------------------------------------------------------
   ГОТОВЫЕ СЦЕНЫ (Задача 4) — заполнение типовой задачи одним кликом.
   Кнопка = программный вызов тех же действий, что делает пользователь
   руками: очистка кривых, ввод формул, назначение ролей, переключение
   режима и установка параметра. Никакой новой логики — только композиция.
   --------------------------------------------------------------------- */
function loadScene(name) {
  STATE.sceneKey = name;   // и при выборе из «Готовых сцен», и из окна сценариев
  // Чистый старт: кривые, сценарий анализа и параметры вмешательства — с нуля.
  STATE.curves = []; curveCounter = 0;
  STATE.scenario = 'none';
  STATE.tax = 0; STATE.pReg = 0;
  // Вид ставки тоже сбрасываем: иначе адвалорная «протекает» из прошлой сцены
  // (та же болезнь, что была у типа вмешательства). Карточка «Процентные
  // налоги» включает адвалорную сама, уже после loadScene.
  setTaxKind('unit');
  ['tax-slider', 'tax-input', 'pc-slider', 'pc-input'].forEach(id => { const e = document.getElementById(id); if (e) e.value = 0; });
  const tv = document.getElementById('tax-val'); if (tv) tv.textContent = '0';
  const pv = document.getElementById('pc-val'); if (pv) pv.textContent = '0';

  if (name === 'free') {
    // Пустой холст: обычный рынок без готовых кривых. Режим ставим явно, иначе
    // он остаётся от прошлой сцены («Математика» после математического сюжета),
    // и холст ведёт себя не как холст.
    setMode('market');
    setMarket('comp'); setType('tax'); setScenario('none');
  } else if (name === 'sd' || name === 'tax' || name === 'ceil' || name === 'mono') {
    setMode('market');                 // setMode сам ставит setRanges(100, 100)
    addCurve('100 - Q'); setRole(STATE.curves[0], 'demand');   // спрос — всегда первая кривая
    if (name === 'mono') {
      addCurve('20'); setRole(STATE.curves[1], 'mc');          // постоянные предельные издержки
      setMarket('monopoly');
      setType('tax');   // детерминированный старт вмешательства (как в конкуренции) — иначе
                        // тип «протекает» из прошлой сцены и пульт показывал бы не то поле
    } else {
      addCurve('Q'); setRole(STATE.curves[1], 'supply');
      setMarket('comp');
      if (name === 'tax')  { setType('tax');     setTax(20); }
      else if (name === 'ceil') { setType('ceiling'); setPReg(30); }
      else { setType('tax'); }                                  // 'sd' — чистое равновесие
    }
  } else if (name === 'elast' || name === 'ext') {
    // Фаза 2: эластичность и внешние эффекты — конкурентный рынок D = 100 − Q, S = Q.
    setMode('market');
    addCurve('100 - Q'); setRole(STATE.curves[0], 'demand');
    addCurve('Q');       setRole(STATE.curves[1], 'supply');
    setMarket('comp');
    if (name === 'elast') {
      STATE.elastQ = null; STATE.elastQS = null;   // точки встанут в «умные» стартовые позиции
      setScenario('elasticity');
    } else {
      STATE.extSign = 'neg'; STATE.extExpr = '20'; STATE.applyPigou = false;
      const ei = document.getElementById('ext-input'); if (ei) ei.value = '20';
      const ep = document.getElementById('ext-pigou'); if (ep) ep.checked = false;
      setExtSign('neg');
      setScenario('externality');
    }
  } else if (name === 'smallopen') {
    // Фаза 4в: малая открытая экономика. Автаркия D=100−Q, S=Q даёт P*=50, Q*=50;
    // при Pw=30 страна импортирует 40 (Qd=70, Qs=30).
    setMode('market');
    addCurve('100 - Q'); setRole(STATE.curves[0], 'demand');
    addCurve('Q');       setRole(STATE.curves[1], 'supply');
    setMarket('comp');
    STATE.openTool = 'none'; STATE.openTariff = 10; STATE.openQuota = 20;
    setOpenTool('none');
    setOpenPw(30);
    setScenario('openecon');
  } else if (name === 'monoexport') {
    // Фаза 4г: обёртка над дискриминацией 3-й степени — второй сегмент горизонтален (Pw).
    setMode('market');
    addCurve('100 - Q'); setRole(STATE.curves[0], 'demand');
    addCurve('Q');       setRole(STATE.curves[1], 'mc');
    setMarket('monopoly');
    STATE.d3World = true;
    STATE.d3D1 = '100 - Q'; STATE.d3D2 = '50'; STATE.d3MC = 'Q';
    const a = document.getElementById('inp-d3-1'), b = document.getElementById('inp-d3-2'), c = document.getElementById('inp-d3-mc');
    if (a) a.value = STATE.d3D1; if (b) b.value = STATE.d3D2; if (c) c.value = STATE.d3MC;
    applyD3WorldLabels();
    setMonoMode('discr3');
  } else if (name === 'costs') {
    const tcInp = document.getElementById('inp-tc'), fcInp = document.getElementById('inp-fc');
    STATE.costsTC = 'Q^3 - 6*Q^2 + 15*Q + 18'; STATE.costsFC = 18;
    if (tcInp) tcInp.value = STATE.costsTC;
    if (fcInp) fcInp.value = STATE.costsFC;
    setMode('costs');                  // setMode сам ставит setRanges(10, 50)
  } else if (name === 'ppf') {
    const ppfInp = document.getElementById('inp-ppf');
    // Уравнение целиком: строка принимает и такую запись, и «x = …», и неявную.
    STATE.ppfFormula = 'y = 100 - x'; STATE.ppfX = null;
    STATE.ppfCompare = false; STATE.ppfFormula2 = 'y = 80 - 0.8*x';
    STATE.ppfName1 = 'КПВ'; STATE.ppfName2 = 'КПВ 2';
    STATE.bundleOn = false; STATE.ppfShowIn = true; STATE.ppfShowOut = false;
    if (ppfInp) ppfInp.value = STATE.ppfFormula;
    const i2 = document.getElementById('inp-ppf2b'); if (i2) i2.value = STATE.ppfFormula2;
    const box = document.getElementById('ppf-second'); if (box) box.style.display = 'none';
    const cb = document.getElementById('btn-ppf-compare'); if (cb) cb.textContent = 'Сравнить с другой КПВ';
    const bo = document.getElementById('chk-bundle'); if (bo) bo.checked = false;
    const br = document.getElementById('bundle-row'); if (br) br.style.display = 'none';
    setMode('ppf');                    // setMode сам ставит setRanges(100, 100)
    setPpfSub('single');               // сцена показывает одиночную КПВ
  }
}

/* ---------------------------------------------------------------------
   ЭКРАН 1 — окно выбора сценария.
   Карточки не несут своей логики: каждая лишь композирует уже имеющиеся
   действия движка (loadScene / setMode / setPpfSub), затем закрывает окно.
   --------------------------------------------------------------------- */
function closePicker() {
  const p = document.getElementById('scene-picker');
  if (p) { p.classList.add('hidden'); p.setAttribute('inert', ''); }
  const app = document.querySelector('.app');
  if (app) app.removeAttribute('inert');
  const back = document.getElementById('scene-back');
  if (back) back.focus();   // вернуть фокус в сцену (а не «потерять» его на скрытой карточке)
  _sceneOpen = true;
  flushMathfields();   // сцена открыта — можно собирать поля формул
  redrawAll();   // график стал видимым — пересчитать размеры под холст
}
function openPicker() {
  const p = document.getElementById('scene-picker');
  if (!p) return;
  p.classList.remove('hidden');
  p.removeAttribute('inert');
  const app = document.querySelector('.app');
  if (app) app.setAttribute('inert', '');   // рабочее место под окном — не фокусируется
  const first = p.querySelector('.scard:not([disabled])');
  if (first) first.focus();
}
/* ---------------------------------------------------------------------
   БЛОКИ 1–10 · МАРШРУТЫ КАРТОЧЕК
   Карточка окна выбора = базовая сцена плюс подрежим. Ключ карточки может
   быть составным ('mono-nat'), базовую сцену возвращает baseScene(): на неё
   по-прежнему смотрят пульт-лента и вся прежняя логика.
     base — базовая сцена (если отличается от ключа карточки);
     run  — что сделать при выборе. Только композиция УЖЕ имеющихся действий
            движка: своей математики у карточки нет;
     lock — id элементов, которые карточка зафиксировала. Переключатели
            соседних моделей прячутся, чтобы сюжет не путал студента другими
            темами. Всё, чего нет в списке, остаётся доступным.
   Полный набор переключателей живёт в «Свободном холсте»: у него lock пуст.
   --------------------------------------------------------------------- */
const L_MARKET  = 'market-struct-row';   // Конкуренция / Монополия
const L_MONOSUB = 'mono-submode';        // Обычная / Дискр. 1° / 3° / Составной / Естественная
const L_INTERV  = 'sec-tax';             // весь блок «Вмешательство государства»
const L_TAXKIND = 'taxkind-row';         // Специфический / Адвалорный
const L_TAXSIDE = 'taxside-row';         // Налог платит: продавец / покупатель

const SCENE_ROUTE = {
  /* --- Блок 1 · Математика ------------------------------------------ */
  'm-graph':      { run: () => { STATE.curves = []; curveCounter = 0; STATE.params = {};
                                 setMode('graph'); renderGraphRows(); } },
  'm-tangent':    { run: () => { setMode('math'); setMathSub('tangent'); },    lock: ['math-seg'] },
  'm-optimum':    { run: () => { setMode('math'); setMathSub('optimum'); },    lock: ['math-seg'] },
  'm-transform':  { run: () => { setMode('math'); setMathSub('transform'); },  lock: ['math-seg'] },
  'm-minmax':     { run: () => { setMode('math'); setMathSub('minmax'); },     lock: ['math-seg'] },
  'm-constraint': { run: () => { setMode('math'); setMathSub('constraint'); }, lock: ['math-seg'] },

  /* --- Блок 2 · КПВ и КТВ ------------------------------------------- */
  ppf:        { run: () => loadScene('ppf'),                                              lock: ['ppf-seg'] },
  ppfsum:     { run: () => { setMode('ppf'); setPpfSub('sum'); },                          lock: ['ppf-seg'] },
  trade:      { run: () => { setMode('ppf'); setPpfSub('trade'); setTradeScenario('A'); }, lock: ['ppf-seg'] },
  tradeprice: { run: () => { setMode('ppf'); setPpfSub('trade'); setTradeScenario('B'); }, lock: ['ppf-seg'] },

  /* --- Блок 3 · Совершенная конкуренция ------------------------------ */
  sd:    { run: () => loadScene('sd'),    lock: [L_MARKET, L_INTERV] },
  tax:   { run: () => loadScene('tax'),
           lock: [L_MARKET, L_TAXKIND, 'seg-ceil', 'seg-floor'] },
  // Адвалорная ставка — тот же сюжет налога, но ставка в процентах: не сдвиг, а поворот S.
  'tax-adv': { base: 'tax',
               run: () => { loadScene('tax'); setTaxKind('advalorem'); setTax(20); },
               lock: [L_MARKET, L_TAXKIND, 'seg-ceil', 'seg-floor'] },
  ceil:  { run: () => loadScene('ceil'),
           lock: [L_MARKET, L_TAXKIND, L_TAXSIDE, 'seg-tax', 'seg-sub'] },
  elast: { run: () => loadScene('elast'), lock: [L_MARKET, L_INTERV] },
  ext:   { run: () => loadScene('ext'),   lock: [L_MARKET, L_INTERV] },

  /* --- Блок 4 · Теория фирмы ---------------------------------------- */
  costs:    { run: () => { loadScene('costs'); setCostsSub('costs'); },      lock: ['costs-seg'] },
  prod:     { base: 'costs', run: () => { loadScene('costs'); setCostsSub('production'); }, lock: ['costs-seg'] },
  plants:   { base: 'costs', run: () => { loadScene('costs'); setCostsSub('plants'); },     lock: ['costs-seg'] },
  isoquant: { base: 'costs', run: () => { loadScene('costs'); setCostsSub('isoquant'); },   lock: ['costs-seg'] },

  /* --- Блок 5 · Несовершенная конкуренция ---------------------------- */
  mono:       { run: () => { loadScene('mono'); setMonoMode('simple'); },  lock: [L_MARKET, L_MONOSUB] },
  'mono-nat': { base: 'mono', run: () => { loadScene('mono'); setMonoMode('natural'); }, lock: [L_MARKET, L_MONOSUB, L_INTERV] },
  'mono-d1':  { base: 'mono', run: () => { loadScene('mono'); setMonoMode('discr1'); },  lock: [L_MARKET, L_MONOSUB, L_INTERV] },
  'mono-d3':  { base: 'mono', run: () => { loadScene('mono'); setMonoMode('discr3'); },  lock: [L_MARKET, L_MONOSUB, L_INTERV] },
  'mono-kink':{ base: 'mono', run: () => { loadScene('mono'); setMonoMode('kinked'); },  lock: [L_MARKET, L_MONOSUB, L_INTERV] },

  /* --- Блок 6 · Рынок труда ------------------------------------------ */
  labor:         { run: () => { setMode('labor'); setLaborStruct('competition'); }, lock: ['labor-seg'] },
  'labor-mono':  { base: 'labor', run: () => { setMode('labor'); setLaborStruct('monopsony'); }, lock: ['labor-seg'] },
  'labor-union': { base: 'labor', run: () => { setMode('labor'); setLaborStruct('union'); },     lock: ['labor-seg'] },
  'labor-bilat': { base: 'labor', run: () => { setMode('labor'); setLaborStruct('bilateral'); }, lock: ['labor-seg'] },

  /* --- Блок 7 · Международная торговля -------------------------------- */
  smallopen:  { run: () => loadScene('smallopen'),  lock: [L_MARKET, L_INTERV] },
  monoexport: { run: () => loadScene('monoexport'), lock: [L_MARKET, L_MONOSUB, L_INTERV] },

  /* --- Блок 8 · Выбор потребителя ------------------------------------- */
  consumer: { run: () => { setMode('consumer'); setConsSlutsky(false); }, lock: ['cons-slutsky-row'] },
  'cons-slutsky': { base: 'consumer',
                    run: () => { setMode('consumer'); setConsSlutsky(true); },
                    lock: ['cons-slutsky-row'] },

  /* --- Блок 9 · Макроэкономика ---------------------------------------- */
  adas:     { run: () => { setMode('macro'); setMacroModel('adas'); },     lock: ['macro-seg'] },
  islm:     { run: () => { setMode('macro'); setMacroModel('islm'); },     lock: ['macro-seg'] },
  phillips: { run: () => { setMode('macro'); setMacroModel('phillips'); }, lock: ['macro-seg'] },
  money:    { run: () => { setMode('macro'); setMacroModel('money'); },    lock: ['macro-seg'] },
  loanable: { run: () => { setMode('macro'); setMacroModel('loanable'); }, lock: ['macro-seg'] },
  fx:       { run: () => { setMode('macro'); setMacroModel('fx'); },       lock: ['macro-seg'] },

  /* --- Блок 10 · Избранные сюжеты -------------------------------------- */
  ineq:   { run: () => setMode('inequality') },
  laffer: { run: () => { setMode('macro'); setMacroModel('laffer'); }, lock: ['macro-seg'] },

  /* --- Свободный холст: ничего не заперто ------------------------------ */
  free: { run: () => { STATE.curves = []; curveCounter = 0; STATE.scenario = 'none';
                       setMode('market'); renderCurveList(); } },
};

/* Базовая сцена карточки. Пульт-лента и прочая логика различают сюжеты по
   базовой сцене, а не по ключу карточки: 'mono-nat' для них по-прежнему 'mono'. */
function baseScene(key) {
  const k = key || STATE.sceneKey;
  const r = SCENE_ROUTE[k];
  return (r && r.base) || k;
}

/* Прячет переключатели, которые карточка уже зафиксировала. Работает классом
   (не инлайновым display), поэтому не конфликтует с обычной логикой видимости:
   та распоряжается style.display как раньше, а класс просто перекрывает её. */
function applyCardScope() {
  document.querySelectorAll('.scoped-off').forEach(el => el.classList.remove('scoped-off'));
  const r = SCENE_ROUTE[STATE.sceneKey];
  if (!r || !r.lock) return;
  r.lock.forEach(id => { const el = document.getElementById(id); if (el) el.classList.add('scoped-off'); });
}

/* Из какого блока сцена. Название берём прямо из окна сценариев: карточка
   лежит в своей секции, у секции есть заголовок. Отдельный список пришлось бы
   держать в согласии с окном вручную, а так он всегда верен. */
function sceneBlockLabel(key) {
  const card = document.querySelector('.scard[data-scene="' + key + '"]');
  const grp = card && card.closest('.picker-group');
  const lab = grp && grp.querySelector('.picker-group-label');
  if (!lab) return '';
  const t = lab.textContent.replace(/^\s*\d+\s*·\s*/, '').trim();
  return (t === 'Пустой холст') ? '' : t;
}

function pickScene(key) {
  resetDecor();           // новая сцена — чистое оформление (Фаза 1)
  STATE.zoomLock = false; // и свой масштаб, а не унаследованный от колеса
  const r = SCENE_ROUTE[key] || SCENE_ROUTE.free;
  r.run();
  // Ключ карточки ставим ПОСЛЕ run: loadScene внутри пишет туда своё имя
  // базовой сцены, и составной ключ ('mono-nat') иначе бы потерялся.
  STATE.sceneKey = key;
  const nm = document.getElementById('scene-name');
  if (nm) nm.textContent = SCENE_NAMES[key] || 'Сцена';
  const bl = document.getElementById('scene-block');
  if (bl) bl.textContent = sceneBlockLabel(key);
  if (typeof collapseCards === 'function') collapseCards();   // новая сцена — все карточки закрыты
  if (typeof updatePult === 'function') updatePult();   // показать/спрятать пульт под выбранную сцену
  // Меньше загромождения: пресетные сцены открываются со свёрнутыми «Инструментами»
  // (разворачиваются иконкой-ползунками в доке). «Свободный холст» — развёрнуты сразу:
  // там пользователь сам добавляет кривые, настройка нужна под рукой.
  setToolsOpen(key === 'free');
  closePicker();
}

