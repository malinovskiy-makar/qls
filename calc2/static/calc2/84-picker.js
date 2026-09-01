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
  // Сюжет сложения выключается при входе в любую другую сцену: иначе его
  // суммарные кривые пересобирались бы там, где групп уже нет.
  STATE.sumOn = false; STATE.sumN = { D: 2, S: 2 };
  STATE.tax = 0; STATE.pReg = 0;
  // Ноль — это значение; «не задано» держат отдельные признаки, и они гаснут.
  STATE.pRegSet = false; STATE.quotaSet = false; STATE.openPwSet = false;
  // Вид ставки тоже сбрасываем: иначе адвалорная «протекает» из прошлой сцены
  // (та же болезнь, что была у типа вмешательства). Карточка «Процентные
  // налоги» включает адвалорную сама, уже после loadScene.
  // Каскад вмешательства возвращается к началу: потоварный вид, продавец.
  // Иначе НДС, акциз или «платит покупатель» протекают из прошлой сцены.
  STATE.taxForm = 'unit'; STATE.subKind = 'unit'; STATE.taxSide = 'seller';
  STATE.quota = 0; STATE.quotaPos = 0.5; STATE.qt = null;
  ['quota-slider', 'quota-input'].forEach(id => { const e = document.getElementById(id); if (e) e.value = 0; });
  const qv = document.getElementById('quota-val'); if (qv) qv.textContent = '0';
  const qp = document.getElementById('quota-price-slider'); if (qp) qp.value = 50;
  setTaxKind('unit');
  ['tax-slider', 'tax-input', 'pc-slider', 'pc-input'].forEach(id => { const e = document.getElementById(id); if (e) e.value = 0; });
  const tv = document.getElementById('tax-val'); if (tv) tv.textContent = '0';
  const pv = document.getElementById('pc-val'); if (pv) pv.textContent = '0';

  if (name === 'sd' || name === 'tax' || name === 'taxes' || name === 'ceil'
      || name === 'quota' || name === 'mono') {
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
      if (name === 'tax' || name === 'taxes') { setType('tax'); setTax(20); }
      else if (name === 'ceil') { setType('ceiling'); setPReg(30); }
      // Квота 40 при D = 100 − Q, S = Q: коридор от 40 до 60, цена по центру.
      else if (name === 'quota') { setType('quota'); setQuota(40); setQuotaPos(0.5); }
      else { setType('tax'); }                                  // 'sd' — чистое равновесие
    }
  } else if (name === 'sdsum') {
    /* Порядок как на созвоне: сначала СКОЛЬКО групп, потом сама формула
       каждой. Числа берём из STATE.sumN — их правит поле в левой панели.
       Стартовые формулы — учебный набор, на нём же стоят проверки:
         спрос      P = 100 − Q  и  P = 60 − Q
         предложение P = Q       и  P = Q + 20
       Излом суммарного спроса (40; 60), суммарного предложения (20; 20),
       равновесие (70; 45). */
    setMode('market');
    STATE.sumOn = true;
    setMarket('comp');
    sumBuildScene();
    setType('tax');
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
      /* Сцена открывается ЧИСТОЙ: MSB и MSC равны частным кривым и ВЫКЛЮЧЕНЫ,
         поэтому оптимум совпадает с рыночным равновесием, а DWL равен нулю.
         Расхождение появляется только после того, как человек включит чекбокс
         и поправит формулу. */
      STATE.msbOn = false; STATE.mscOn = false;
      STATE.msbExpr = ''; STATE.mscExpr = '';     // подставятся формулы D и S
      STATE.applyPigou = false;
      const ep = document.getElementById('ext-pigou'); if (ep) ep.checked = false;
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
    // Постоянные затраты отдельным полем не задаются: FC = TC(0) (Б24).
    const tcInp = document.getElementById('inp-tc');
    STATE.costsTC = 'Q^3 - 6*Q^2 + 15*Q + 18';
    if (tcInp) tcInp.value = STATE.costsTC;
    if (typeof setCostsInputMode === 'function') setCostsInputMode('tc');
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
    // П4: поля единиц в новой сцене пустые, кривой комплектов нет.
    ['inp-bundle-x', 'inp-bundle-y', 'inp-bundle-x2', 'inp-bundle-y2',
     'inp-bundle-xt', 'inp-bundle-yt'].forEach(id => {
      const e = document.getElementById(id); if (e) e.value = '';
    });
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

/* А41 · А68. Открыв блок, человек всё ещё видел шапку первого экрана: кикер
   «ГРАФИКИ В ЭКОНОМИКЕ», заголовок «С чего начнём?» и инструкцию «Откройте
   раздел и выберите модель» — уже ПОСЛЕ того, как раздел открыт. Вместе с
   кнопкой возврата это занимало 332 пикселя над первой карточкой, и при
   высоте окна 392 карточка была видна на пятую часть.

   Метка на самом окне; шапку прячет стиль. Одно место на все переходы. */
function setPickerBlockOpen(on) {
  const p = document.getElementById('scene-picker');
  if (p) p.classList.toggle('block-open', !!on);
}

function openPicker() {
  const p = document.getElementById('scene-picker');
  if (!p) return;
  p.classList.remove('hidden');
  p.removeAttribute('inert');
  const app = document.querySelector('.app');
  if (app) app.setAttribute('inert', '');   // рабочее место под окном — не фокусируется
  /* Н5. Из сюжета возвращаемся РОВНО на предыдущий экран, то есть в тот блок,
     где этот сюжет лежит, а не в общий список десяти блоков. (Прежнее правило
     П2 говорило обратное; оно отменено.) Блок ищем по самой карточке текущей
     сцены: так он верен всегда, в том числе после восстановления состояния.
     Если сцены ещё не выбирали, открывается полная карта. */
  const blocks = document.getElementById('picker-blocks');
  const back = document.getElementById('picker-back');
  p.querySelectorAll('.picker-group').forEach(g => g.classList.remove('open'));
  const card = STATE.sceneKey
    ? p.querySelector('.scard[data-scene="' + CSS.escape(STATE.sceneKey) + '"]') : null;
  const group = card ? card.closest('.picker-group') : null;
  if (group) {
    group.classList.add('open');
    if (blocks) blocks.classList.add('hidden');
    if (back) back.classList.add('shown');
    setPickerBlockOpen(true);
  } else {
    if (blocks) blocks.classList.remove('hidden');
    if (back) back.classList.remove('shown');
    setPickerBlockOpen(false);
  }
  const first = group
    ? (group.querySelector('.scard:not([disabled])') || p.querySelector('.bcard'))
    : (p.querySelector('.bcard') || p.querySelector('.scard:not([disabled])'));
  /* ⚠️ ПРОГРАММНЫЙ ФОКУС — НЕ ЗНАЧИТ ВИДИМОЕ КОЛЬЦО. focus() здесь нужен ради
     доступности: открыли окно — Tab и стрелки сразу работают, не нужно
     проходить всю шапку сайта заново. Но браузер не различает «фокус дала
     клавиатура человека» и «фокус дал этот вызов» и рисует :focus-visible
     кольцо в обоих случаях — на первом экране оно появлялось на карточке
     «Математика» сразу после загрузки, ещё до курсора и до Tab. Класс
     no-init-ring на время гасит именно кольцо (сам фокус остаётся —
     скринридер и Enter/стрелки работают как обычно), и снимается на первое
     же настоящее действие человека — мышью или клавиатурой, — после чего
     :focus-visible снова решает браузер сам, как везде. */
  if (first) {
    first.classList.add('no-init-ring');
    first.focus({ preventScroll: true });
    const clearInitRing = () => first.classList.remove('no-init-ring');
    first.addEventListener('blur', clearInitRing, { once: true });
    document.addEventListener('pointerdown', clearInitRing, { once: true });
    /* ⚠️ КОЛЬЦО ВОЗВРАЩАЕТ ТОЛЬКО КЛАВИАТУРНАЯ НАВИГАЦИЯ — Tab и стрелки.
       Прежде его возвращала ЛЮБАЯ клавиша: нажал Escape или начал печатать в
       поле — и на карточке, которую никто не выбирал, снова горело кольцо.
       Тот же признак «фокус дала клавиатура человека», что у подсказок
       (см. `_tipByKeyboard` в 86-workspace.js). */
    const keyRing = (e) => {
      if (e.key !== 'Tab' && e.key.indexOf('Arrow') !== 0) return;
      document.removeEventListener('keydown', keyRing, true);
      clearInitRing();
    };
    document.addEventListener('keydown', keyRing, true);
  }
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
const L_MONOSUB = 'mono-submode';        // Обычная / Дискр. 1° / 3° / Составной / Естественная
const L_INTERV  = 'sec-tax';             // весь блок «Вмешательство государства»
const L_TAXKIND = 'taxkind-row';         // Специфический / Адвалорный
const L_TAXSIDE = 'taxside-row';         // Налог платит: продавец / покупатель

const SCENE_ROUTE = {
  /* --- Блок 1 · Математика ------------------------------------------ */
  /* П60. Сцена открывается ПУСТЫМ холстом, поэтому её единственная карточка
     раскрыта заранее: свёрнутая панель над пустым графиком не сообщает даже
     того, что здесь вообще что-то делают. Во всех остальных сценах карточки
     закрыты по-прежнему — там на холсте уже есть модель, и первый шаг очевиден. */
  /* Своего openSection у маршрута больше нет: карточка «Ввод функций» раскрыта
     во ВСЕХ сценах, и открывает её pickScene одинаково для всех. */
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
  sd:    { run: () => loadScene('sd'),    lock: [L_INTERV] },
  /* Сложение спросов и предложений. Вмешательство здесь заперто: сюжет про
     то, откуда берётся рыночная кривая, а не про то, что с ней делает
     государство. Суммарные кривые и есть D и S этой сцены. */
  sdsum: { run: () => loadScene('sdsum'), lock: [L_INTERV] },
  /* «Налоги и субсидии» — ОДИН сюжет вместо двух карточек (потоварной и
     процентной). Вид налога выбирается внутри, в правой панели, каскадом:
     налог/субсидия → вид → сторона → значение. Старые ключи 'tax' и
     'tax-adv' остались СИНОНИМАМИ: та же базовая сцена, те же запреты,
     различается только предустановка. Ссылки в коде и тестах живы. */
  taxes: { base: 'tax', run: () => loadScene('taxes'),
           lock: ['seg-ceil', 'seg-floor', 'seg-quota'] },
  tax:   { base: 'tax', run: () => loadScene('tax'),
           lock: ['seg-ceil', 'seg-floor', 'seg-quota'] },
  'tax-adv': { base: 'tax',
               run: () => { loadScene('tax'); setTaxForm('vat'); setTax(20); },
               lock: ['seg-ceil', 'seg-floor', 'seg-quota'] },
  ceil:  { run: () => loadScene('ceil'),
           lock: [L_TAXKIND, L_TAXSIDE, 'seg-tax', 'seg-sub', 'seg-quota'] },
  // Квота — прямое ограничение объёма. Внутри сюжета только сама квота:
  // налог, субсидия и фиксированная цена — соседние сюжеты, они заперты.
  quota: { run: () => loadScene('quota'),
           lock: [L_TAXKIND, L_TAXSIDE, 'seg-tax', 'seg-sub', 'seg-ceil', 'seg-floor'] },
  elast: { run: () => loadScene('elast'), lock: [L_INTERV] },
  ext:   { run: () => loadScene('ext'),   lock: [L_INTERV] },

  /* --- Блок 4 · Теория фирмы ---------------------------------------- */
  costs:    { run: () => { loadScene('costs'); setCostsSub('costs'); },      lock: ['costs-seg'] },
  prod:     { base: 'costs', run: () => { loadScene('costs'); setCostsSub('production'); }, lock: ['costs-seg'] },
  plants:   { base: 'costs', run: () => { loadScene('costs'); setCostsSub('plants'); },     lock: ['costs-seg'] },
  isoquant: { base: 'costs', run: () => { loadScene('costs'); setCostsSub('isoquant'); },   lock: ['costs-seg'] },

  /* --- Блок 5 · Несовершенная конкуренция ---------------------------- */
  mono:       { run: () => { loadScene('mono'); setMonoMode('simple'); },  lock: [L_MONOSUB] },
  'mono-nat': { base: 'mono', run: () => { loadScene('mono'); setMonoMode('natural'); }, lock: [L_MONOSUB, L_INTERV] },
  'mono-d1':  { base: 'mono', run: () => { loadScene('mono'); setMonoMode('discr1'); },  lock: [L_MONOSUB, L_INTERV] },
  'mono-d3':  { base: 'mono', run: () => { loadScene('mono'); setMonoMode('discr3'); },  lock: [L_MONOSUB, L_INTERV] },
  'mono-kink':{ base: 'mono', run: () => { loadScene('mono'); setMonoMode('kinked'); },  lock: [L_MONOSUB, L_INTERV] },

  /* --- Блок 6 · Рынок труда ------------------------------------------ */
  labor:         { run: () => { setMode('labor'); setLaborStruct('competition'); }, lock: ['labor-seg'] },
  'labor-mono':  { base: 'labor', run: () => { setMode('labor'); setLaborStruct('monopsony'); }, lock: ['labor-seg'] },
  'labor-union': { base: 'labor', run: () => { setMode('labor'); setLaborStruct('union'); },     lock: ['labor-seg'] },
  'labor-bilat': { base: 'labor', run: () => { setMode('labor'); setLaborStruct('bilateral'); }, lock: ['labor-seg'] },

  /* --- Блок 7 · Международная торговля -------------------------------- */
  smallopen:  { run: () => loadScene('smallopen'),  lock: [L_INTERV] },
  monoexport: { run: () => loadScene('monoexport'), lock: [L_MONOSUB, L_INTERV] },

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
/* ── Блоки окна сценариев (Фаза 6) ───────────────────────────────────
   Десять блоков, шестьдесят карточек. Всё сразу на экране не читается,
   поэтому блоки сворачиваются, а открываются по одному. Заголовок из
   разметки превращается в кнопку, сетка карточек — в её тело: новому блоку
   ничего дополнительно делать не нужно. */
/* Картинки блоков (П2). Это НЕ повтор превью моделей: каждая — саммари того,
   что внутри блока. Геометрия та же, что у карточек моделей и у иконок
   панели: оси и вспомогательное 1.5 · пунктир и второстепенная кривая 2.2 ·
   главная кривая 2.6 · маркер r 3.6 · пунктир «5 4» · заливка-подсказка .16. */
const BLOCK_SPECS = {
  'Математика':
    '<path d="M20 50 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M46 84 V8" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M20 14 C60 92 84 92 130 20" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M62 84 L128 20" stroke="var(--curve-mr)" stroke-width="2.2" stroke-dasharray="5 4"/>' +
    '<circle cx="95" cy="52" r="3.6" fill="var(--ink)" stroke="none"/>',
  'КПВ и КТВ':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M24 16 C86 22 118 44 132 76 L24 76 Z" fill="var(--curve-d)" fill-opacity=".16" stroke="none"/>' +
    '<path d="M24 16 C86 22 118 44 132 76" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M20 40 L146 70" stroke="var(--curve-tax)" stroke-width="2.2" stroke-dasharray="5 4"/>' +
    '<circle cx="76" cy="53" r="3.6" fill="var(--ink)" stroke="none"/>',
  'Совершенная конкуренция':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M26 16 L140 72" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M26 72 L140 16" stroke="var(--curve-s)" stroke-width="2.6"/>' +
    '<circle cx="83" cy="44" r="3.6" fill="var(--ink)" stroke="none"/>',
  'Теория фирмы':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M28 22 C60 84 92 84 138 30" stroke="var(--cost-atc)" stroke-width="2.6"/>' +
    '<path d="M28 70 C74 74 106 46 138 16" stroke="var(--cost-mc)" stroke-width="2.2"/>' +
    '<circle cx="83" cy="66" r="3.6" fill="var(--ink)" stroke="none"/>',
  'Несовершенная конкуренция':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M26 16 L140 72" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M26 16 L83 72" stroke="var(--curve-mr)" stroke-width="2.2" stroke-dasharray="5 4"/>' +
    '<path d="M22 58 H146" stroke="var(--curve-mc)" stroke-width="2.2"/>' +
    '<circle cx="57" cy="37" r="3.6" fill="var(--ink)" stroke="none"/>',
  'Рынок труда':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M26 18 L140 70" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M26 70 L140 18" stroke="var(--curve-s)" stroke-width="2.6"/>' +
    '<path d="M22 32 H146" stroke="var(--curve-reg)" stroke-width="2.2" stroke-dasharray="5 4"/>' +
    '<circle cx="83" cy="44" r="3.6" fill="var(--ink)" stroke="none"/>',
  'Международная торговля':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M26 16 L140 72" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M26 72 L140 16" stroke="var(--curve-s)" stroke-width="2.6"/>' +
    '<rect x="52" y="54" width="62" height="8" fill="var(--curve-tax)" fill-opacity=".16"/>' +
    '<path d="M22 58 H146" stroke="var(--curve-tax)" stroke-width="2.2" stroke-dasharray="5 4"/>',
  'Выбор потребителя':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M26 20 L138 74" stroke="var(--curve-s)" stroke-width="2.2"/>' +
    '<path d="M30 74 C74 70 96 52 100 18" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M52 76 C104 72 126 54 132 22" stroke="var(--curve-d)" stroke-width="2.2" opacity=".4"/>' +
    '<circle cx="72" cy="43" r="3.6" fill="var(--ink)" stroke="none"/>',
  'Макроэкономика':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M26 18 L140 70" stroke="var(--curve-d)" stroke-width="2.6"/>' +
    '<path d="M26 70 L140 24" stroke="var(--curve-s)" stroke-width="2.2"/>' +
    '<path d="M100 12 V76" stroke="var(--curve-reg)" stroke-width="2.2" stroke-dasharray="5 4"/>' +
    '<circle cx="88" cy="46" r="3.6" fill="var(--ink)" stroke="none"/>',
  'Избранные сюжеты':
    '<path d="M18 78 H150" stroke="var(--ink-soft)" stroke-width="1.5"/><path d="M18 78 V12" stroke="var(--ink-soft)" stroke-width="1.5"/>' +
    '<path d="M18 78 L134 14" stroke="var(--ink-soft)" stroke-width="2.2" stroke-dasharray="5 4"/>' +
    '<path d="M18 78 C74 74 112 56 134 14 Z" fill="var(--curve-mr)" fill-opacity=".16" stroke="none"/>' +
    '<path d="M18 78 C74 74 112 56 134 14" stroke="var(--curve-mr)" stroke-width="2.6"/>',
};

function blockSpec(name) {
  const d = BLOCK_SPECS[name];
  if (!d) return '';
  return '<span class="bcard-spec" aria-hidden="true"><svg viewBox="0 0 160 90">'
       + '<g fill="none" stroke-linecap="round">' + d + '</g></svg></span>';
}

/* П2. Главный экран — десять больших карточек блоков по две в ряд. Щелчок по
   карточке плавно убирает остальные и на их месте показывает модели этого
   блока; появляется «Назад ко всем блокам». Второго экрана и маршрутов нет:
   всё на одной странице. Механика та же, что была у сворачивания блоков, —
   поменялось только оформление и то, что открытый блок остаётся один на экране. */
function foldPickerGroups() {
  const inner = document.querySelector('#scene-picker .picker-inner');
  if (!inner || inner._blocks) return;
  inner._blocks = true;

  const blocks = document.createElement('div');
  blocks.className = 'picker-blocks';
  blocks.id = 'picker-blocks';

  const back = document.createElement('button');
  back.type = 'button';
  back.className = 'picker-back';
  back.id = 'picker-back';
  back.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                 + 'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
                 + '<path d="M14 6l-6 6 6 6"/></svg><span>Назад ко всем блокам</span>';

  const showBlocks = () => {
    document.querySelectorAll('#scene-picker .picker-group').forEach(x => x.classList.remove('open'));
    blocks.classList.remove('hidden');
    back.classList.remove('shown');
    setPickerBlockOpen(false);
    inner.scrollIntoView({ block: 'start' });
  };
  back.addEventListener('click', showBlocks);

  const groups = [...document.querySelectorAll('#scene-picker .picker-group')];
  groups.forEach((g, i) => {
    const lab = g.querySelector(':scope > .picker-group-label');
    const grid = g.querySelector(':scope > .picker-grid');
    if (!lab || !grid) return;
    const name = lab.textContent.trim();
    if (!grid.id) grid.id = 'pgrid-' + i;
    grid.classList.add('open');          // внутри открытого блока сетка видна всегда
    lab.remove();

    /* п. 62. СЧЁТЧИК НАЗЫВАЕТ ОБА ЧИСЛА.

       Сначала считали только готовые — «2 модели» при трёх видимых карточках
       читалось как ошибка (решение Н1). Потом стали считать все — и «Выбор
       потребителя: 9 моделей» обещал девять там, где работают две. Оба раза
       одно число отвечало на два разных вопроса: «что здесь будет» и «во что
       можно зайти сейчас». Печатаем оба, и только когда они расходятся. */
    const all = grid.querySelectorAll('.scard').length;
    const n = grid.querySelectorAll('.scard:not(.soon)').length;
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'bcard';
    card.setAttribute('aria-controls', grid.id);
    /* ⚠️ ПЕРЕЧНЯ МОДЕЛЕЙ НА КАРТОЧКЕ БОЛЬШЕ НЕТ, И ЭТО ОДНА ПРАВКА, А НЕ ДВЕ.
       Замер высот десяти карточек: 162, 162, 194, 194, 178, 178, 210, 210,
       178, 178 — пять разных значений. Причина одна: перечень занимал от 32
       до 96 px, а карточки в ряду тянутся по самой высокой. Снятие перечня
       само выравнивает карточки.
       Порядок карточек внутри блока (готовые вперёд, запланированные следом)
       остаётся: он про сетку блока, а не про перечень. */
    card.innerHTML = blockSpec(name)
      + '<span class="bcard-name"></span><span class="bcard-count"></span>';
    card.querySelector('.bcard-name').textContent = name;
    card.querySelector('.bcard-count').textContent = (n === all)
      ? all + ' ' + plural(all, ['модель', 'модели', 'моделей'])
      : n + ' ' + plural(n, ['модель', 'модели', 'моделей']) + ' из ' + all;
    /* п. 64. Запланированные модели уходят в конец сетки блока: на экране
       блока не приходится выбирать нужное среди недоступного. */
    grid.querySelectorAll('.scard.soon').forEach(sc => grid.appendChild(sc));
    card.addEventListener('click', () => {
      blocks.classList.add('hidden');
      groups.forEach(x => x.classList.remove('open'));
      g.classList.add('open');
      back.classList.add('shown');
      setPickerBlockOpen(true);
      inner.scrollIntoView({ block: 'start' });
    });
    blocks.appendChild(card);

    // Заголовок внутри открытого блока: понятно, куда попал.
    const h = document.createElement('div');
    h.className = 'picker-group-open-name';
    h.textContent = name;
    g.insertBefore(h, grid);
  });

  if (groups.length) {
    inner.insertBefore(back, groups[0]);
    inner.insertBefore(blocks, groups[0]);
  }
}

// Склонение числительных: «1 модель», «2 модели», «5 моделей».
function plural(n, forms) {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}

function pickScene(key) {
  // П51: уходя из модели, кладём её состояние на полку — вернёмся, достанем.
  if (STATE.sceneKey && STATE.sceneKey !== key) saveSceneSnapshot(STATE.sceneKey);
  resetDecor();           // П20: новая модель начинается с чистого состояния
  STATE.zoomLock = false; // и своего масштаба, а не унаследованного от колеса
  if (typeof resetPanelWins === 'function') resetPanelWins();   // и окон её панелей
  /* ⚠️ ВХОД В ЛЮБУЮ МОДЕЛЬ ОБНУЛЯЕТ КРИВЫЕ (п. 11).
     Девятнадцать маршрутов из сорока одного зовут loadScene, и он чистит
     STATE.curves сам. Остальные двадцать два (вся «Математика», КПВ, торговля,
     труд, потребитель, макро, неравенство) только переключали режим — и
     получали кривые предыдущей модели. Замер до правки: 22 сцены из 41
     приходили с чужим содержимым; в AD–AS от этого висел в пустоте маркер
     равновесия из монопсонии, а сцена труда открывалась с рыночными D и S
     вместо своих спроса и предложения труда.
     Чинить надо не конкретный переход, а жизненный цикл: маршрут, которому
     кривые нужны, строит их сам сразу после этой строки. */
  STATE.curves = []; curveCounter = 0;
  const r = SCENE_ROUTE[key] || SCENE_ROUTE.sd;
  r.run();
  // Возврат в модель, где уже работали: восстанавливаем именно её изменения.
  // Строго ПОСЛЕ run(): тот ставит сцене её стартовый вид, а снимок его
  // перекрывает. Между моделями при этом не течёт ничего — снимок свой у каждой.
  restoreSceneSnapshot(key);
  // Ключ карточки ставим ПОСЛЕ run: loadScene внутри пишет туда своё имя
  // базовой сцены, и составной ключ ('mono-nat') иначе бы потерялся.
  STATE.sceneKey = key;
  const nm = document.getElementById('scene-name');
  if (nm) nm.textContent = SCENE_NAMES[key] || 'Сцена';
  if (typeof collapseCards === 'function') collapseCards();   // новая сцена — все карточки закрыты
  /* …кроме «Ввода функций»: он раскрыт всегда и во всех моделях (решение
     владельца 22.08). «Точки на графике» и «Площади» остаются свёрнутыми —
     одинаковая структура панели важнее экономии места. */
  if (typeof openSection === 'function') openSection('sec-input');
  if (typeof updatePult === 'function') updatePult();   // показать/спрятать пульт под выбранную сцену
  // Панель ввода открыта, но все карточки в ней закрыты: список заголовков
  // виден сразу, а разворачивается только нужное.
  setToolsOpen(true);
  closePicker();
}

