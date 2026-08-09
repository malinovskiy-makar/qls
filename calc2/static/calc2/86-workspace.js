// Рабочее место: шапка, панели, меню координатной плоскости.
/* ---------------------------------------------------------------------
   ЭКРАН 2 — рабочее место «Сцена».
   Перекомпоновка: те же контролы и те же #info-* блоки, лишь переставленные.
   Вторичные секции (режим/сцены/оси) → в раскрывашку «Все настройки»;
   блоки результатов → в плавающее табло справа.
   --------------------------------------------------------------------- */
const SCENE_NAMES = {
  sd: 'Спрос и предложение', tax: 'Потоварные налоги и субсидии', ceil: 'Пол и потолок цены',
  mono: 'Стандартная монополия', elast: 'Эластичность', ext: 'Внешние эффекты',
  costs: 'Издержки фирмы', ppf: 'Построение КПВ',
  labor: 'Рынок труда: совершенная конкуренция', ineq: 'Неравенство доходов',
  consumer: 'Кривые безразличия',
  adas: 'AD–AS', phillips: 'Кривая Филлипса', money: 'Денежный рынок',
  loanable: 'Рынок заёмных средств', fx: 'Валютный рынок', laffer: 'Кривая Лаффера', islm: 'IS–LM',
  // Международная торговля — четыре РАЗНЫЕ модели, названия разводят их явно
  // (Фаза 4): первые две — рикардианские, через КПВ и альтернативные издержки;
  // третья — частичное равновесие по ЦЕНЕ; четвёртая — фирма с рыночной властью.
  ppfsum: 'Сложение КПВ',
  trade: 'КТВ через заданную цену',
  tradeprice: 'КТВ через торговлю двух стран',
  smallopen: 'Малая открытая экономика',
  monoexport: 'Монополист и внешний рынок',
  // Математика (Фаза 7) — общий инструментарий, вне экономических моделей.
  'm-graph': 'Построение графиков',
  'm-tangent': 'Функция и её производная наглядно', 'm-optimum': 'Максимумы и минимумы',
  'm-transform': 'Деформации графика',
  'm-minmax': 'Функции min и max', 'm-constraint': 'Оптимум при ограничении',
  // Карточки, разложенные из подрежимов при переходе на 10 блоков.
  'tax-adv': 'Процентные налоги и субсидии',
  prod: 'Производственная функция', plants: 'Сложение заводов',
  isoquant: 'Изокванта и изокоста',
  'mono-nat': 'Естественная монополия', 'mono-d1': 'Дискриминация 1-й степени',
  'mono-d3': 'Дискриминация 3-й степени', 'mono-kink': 'Составной спрос',
  'labor-mono': 'Монопсония', 'labor-union': 'Вмешательство профсоюза',
  'labor-bilat': 'Двусторонняя монополия',
  'cons-slutsky': 'Декомпозиция по Слуцкому',
};
// Блоки результатов в табло (порядок = порядок показа). info-eq переносим вместе
// с секцией sec-eq (она несёт заголовок «Равновесие»), остальные — голыми div'ами.
// info-areacalc сюда НЕ входит: посчитанная площадь остаётся в своей секции
// «Площади», рядом с кнопкой, которая её посчитала.
const RESULT_IDS = ['info-areas', 'info-tax', 'info-mono', 'info-nat', 'info-costs',
  'info-prod', 'info-iso', 'info-plants', 'info-labor',
  'info-inequality', 'info-consumer', 'info-macro', 'info-math', 'info-elast', 'info-shift', 'info-ext', 'info-open', 'info-d3', 'info-kink',
  'info-ppf', 'info-ppfsum', 'info-ppft', 'info-tb'];

/* Записать значение в поле формулы и разбудить его слушателей. Отдельная
   функция, потому что поле формулы со временем меняло природу (обычный input,
   затем поле с набранной записью), а мест вставки много. */
function setFieldValue(inp, text) {
  if (!inp) return;
  inp.value = text;
  inp.dispatchEvent(new Event('input', { bubbles: true }));
}

function relocateForScene() {
  const sb = document.getElementById('sb-body');
  if (sb) {
    const eq = document.getElementById('sec-eq'); if (eq) sb.appendChild(eq);
    RESULT_IDS.forEach(id => { const el = document.getElementById(id); if (el) sb.appendChild(el); });
  }
}

// Очистка всех блоков табло перед перерисовкой: активный режим заполнит свои,
// чужие останутся пустыми (CSS прячет пустые) — без устаревших чисел из прошлого режима.
function clearResultPanels() {
  ['info-eq'].concat(RESULT_IDS).forEach(id => { const e = document.getElementById(id); if (e) e.innerHTML = ''; });
  // Площадь живёт в своей секции и переживает перерисовку: её очищает
  // только «Убрать» рядом с кнопкой расчёта.
}

// Маленький тост для заглушек («сохранить/экспорт — скоро»).
function toast(msg) {
  let t = document.getElementById('calc2-toast');
  if (!t) { t = document.createElement('div'); t.id = 'calc2-toast'; t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2400);
}

function dockActive(id, on) {
  const b = document.getElementById(id);
  if (b) { b.classList.toggle('active', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); }
}
/* Сворачивание боковых панелей. Панель не уезжает за экран, а ужимается до
   полосы со стрелкой — график при этом становится шире, поэтому после
   анимации ширины его надо перерисовать (этим занимается ResizeObserver). */
function setSideOpen(panelId, btnId, open) {
  const p = document.getElementById(panelId);
  if (p) p.classList.toggle('collapsed', !open);
  const b = document.getElementById(btnId);
  if (b) {
    b.setAttribute('aria-expanded', open ? 'true' : 'false');
    // Подпись идёт за состоянием: свёрнутая панель предлагает открыть, открытая — закрыть.
    b.setAttribute('data-tip', open ? 'Закрыть меню' : 'Открыть меню');
  }
}
function setToolsOpen(open) { setSideOpen('tools-panel', 'tools-toggle', open); }
function setParamsOpen(open) { setSideOpen('params-panel', 'params-toggle', open); }

/* Где считать нечего, «Аналитики» нет вовсе. Это построение графиков и
   деформации — там нет ни равновесия, ни площадей, ни разбора, только сама
   кривая. */
const NO_ANALYTICS = { 'm-graph': true, 'm-transform': true };
function hasAnalytics() { return !NO_ANALYTICS[STATE.sceneKey]; }

/* Разбор «как это получилось» сцены пишут внутрь своего блока расчётов. Здесь
   он одним проходом уезжает в «Объяснение модели»: так новому блоку аналитики
   ничего дополнительно делать не нужно, достаточно поставить врезку .sb-note.
   Внутренний заголовок «Как это получилось» снимаем — он стал дублем названия
   блока; свои заголовки («Почему КТВ ломается») остаются. */
function moveExplanations() {
  const from = document.getElementById('sb-body');
  const to = document.getElementById('ex-body');
  if (!from || !to) return;
  to.innerHTML = '';
  from.querySelectorAll('.sb-note').forEach(note => {
    const h = note.querySelector('b');
    if (h && h.textContent.trim() === 'Как это получилось') h.remove();
    to.appendChild(note);
  });
}

/* Правая панель показывает ровно то, что есть: ползунки, расчёты, разбор.
   Пустых блоков не бывает, а если пусто всё — панели на экране нет. */
function syncAnalyticsPanel() {
  moveExplanations();
  const on = hasAnalytics();
  const sb = document.getElementById('sb-body');
  const ex = document.getElementById('ex-body');
  const hasValues = on && !!sb && sb.textContent.trim().length > 0;
  const hasExplain = on && !!ex && ex.textContent.trim().length > 0;
  const score = document.getElementById('scoreboard');
  if (score) score.classList.toggle('hidden', !hasValues);
  const expl = document.getElementById('explain');
  if (expl) expl.classList.toggle('hidden', !hasExplain);
  const body = document.getElementById('params-body');
  const hasKnobs = !!body && !!body.querySelector('input, select, button');
  const empty = document.getElementById('params-empty');
  if (empty) empty.style.display = (hasKnobs || !(hasValues || hasExplain)) ? 'none' : '';
  const panel = document.getElementById('params-panel');
  if (panel) panel.classList.toggle('empty', !(hasKnobs || hasValues || hasExplain));
}

/* ── Панель ввода: список карточек (Фаза 5) ──────────────────────────
   Раньше в панели вперемешку жили три разных вида блока: складные секции,
   нескладные подзаголовки и безымянные куски. Отличались они только кеглем,
   поэтому панель читалась сплошной лентой. Теперь каждая смысловая часть —
   своя карточка с ярким заголовком, и все они закрыты: сцена открывается
   спокойной, а нужное разворачивается щелчком.

   Заголовки превращаются в складные кнопки одним проходом, поэтому новая
   секция получает карточку бесплатно, без единой строчки в разметке. */
const FOLD_CHEVRON = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
  ' stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';

// Имена для секций, у которых своего заголовка в разметке нет.
const SECTION_NAMES = {
  'sec-costs': 'Фирма',
  'sec-labor': 'Рынок труда',
  'sec-inequality': 'Неравенство доходов',
  'sec-consumer': 'Выбор потребителя',
  'sec-ppf': 'КПВ и торговля',
  'sec-macro': 'Макроэкономика',
  'sec-math': 'Математика',
};

/* П9. Иконка у каждого блока панели ввода — в той же геометрии, что превью
   моделей в окне сценариев: только три толщины линии (оси 1.5 · вспомогательная
   2.2 · главная кривая 2.6), маркер r 3.6, пунктир «5 4». Так иконки читаются
   как одна семья с карточками, а не как набор из случайных наборов.
   Рисуем в viewBox 24×24 и красим currentColor: цвет берётся у заголовка. */
const SECTION_ICONS = {
  // Кривые: оси и одна кривая.
  'sec-curves': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 17c5 0 9-4 13-11" stroke-width="2.6"/>',
  // Построение графиков: две кривые.
  'sec-graph': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 18c4-2 6-8 13-12" stroke-width="2.6"/><path d="M5 8c5 4 8 7 13 9" stroke-width="2.2" stroke-dasharray="5 4"/>',
  // Равновесие: пересечение и точка.
  'sec-eq': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 6l13 12M5 18L18 6" stroke-width="2.2"/><circle cx="11.5" cy="12" r="3.6" stroke-width="2.6"/>',
  // Излишки: закрашенная область.
  'sec-areas': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 6l12 12H5z" fill="currentColor" fill-opacity=".16" stroke-width="2.6"/>',
  // Что изучаем: кривая и штриховая «до».
  'sec-analysis': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 17c5 0 9-4 13-11" stroke-width="2.6"/><path d="M5 12c5 0 9-3 13-7" stroke-width="2.2" stroke-dasharray="5 4" opacity=".4"/>',
  // Монополия: спрос и вдвое круче MR.
  'sec-mono': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 6l13 12" stroke-width="2.6"/><path d="M5 6l7 12" stroke-width="2.2" stroke-dasharray="5 4"/>',
  // Вмешательство: клин между кривыми.
  'sec-tax': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 6l13 12M5 18L18 6" stroke-width="2.2"/><rect x="8" y="9" width="7" height="6" fill="currentColor" fill-opacity=".16" stroke-width="2.6"/>',
  // Фирма: U-образные средние издержки.
  'sec-costs': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 7c4 9 8 9 13 1" stroke-width="2.6"/>',
  // Рынок труда: спрос и предложение труда.
  'sec-labor': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 7l13 10" stroke-width="2.6"/><path d="M5 17L18 7" stroke-width="2.2"/>',
  // Неравенство: кривая Лоренца под диагональю.
  'sec-inequality': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M4 20L18 5" stroke-width="2.2" stroke-dasharray="5 4"/><path d="M4 20c7 0 11-5 14-15" stroke-width="2.6"/>',
  // Потребитель: бюджетная линия и кривая безразличия.
  'sec-consumer': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 17L18 6" stroke-width="2.2"/><path d="M6 18c6 0 10-4 11-11" stroke-width="2.6"/>',
  // КПВ: вогнутая граница.
  'sec-ppf': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 5c8 1 12 6 13 14" stroke-width="2.6"/>',
  // Макро: AD и вертикальная LRAS.
  'sec-macro': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 6l13 12" stroke-width="2.6"/><path d="M13 5v14" stroke-width="2.2"/>',
  // Математика: парабола.
  'sec-math': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 5c3 12 8 12 13 1" stroke-width="2.6"/>',
  // Точки на графике: точка с проекциями.
  'sec-view': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M4 10h9M13 20v-10" stroke-width="2.2" stroke-dasharray="5 4"/><circle cx="13" cy="10" r="3.6" stroke-width="2.6"/>',
  // Цвета областей: три образца.
  'sec-areacolors': '<rect x="4" y="6" width="16" height="4" rx="1.5" fill="currentColor" fill-opacity=".16" stroke-width="2.2"/><rect x="4" y="14" width="16" height="4" rx="1.5" fill="currentColor" fill-opacity=".16" stroke-width="2.6"/>',
  // Площади: заштрихованная фигура под кривой.
  'sec-areascalc': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 8c5 1 9 5 12 11H5z" fill="currentColor" fill-opacity=".16" stroke-width="2.6"/>',
};

function sectionIcon(secId) {
  const d = SECTION_ICONS[secId];
  if (!d) return '';
  return '<svg class="sec-ico" aria-hidden="true" viewBox="0 0 24 24" fill="none" '
       + 'stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">' + d + '</svg>';
}

function cardifySections() {
  document.querySelectorAll('#tools-panel .tools-body > .section').forEach(sec => {
    if (sec._card) return;
    sec._card = true;
    sec.classList.add('card');
    const had = sec.querySelector(':scope > .fold-btn');
    if (had) {                                   // складной заголовок уже был
      had.setAttribute('aria-expanded', 'false');
      const box = document.getElementById(had.getAttribute('aria-controls'));
      if (box) box.classList.remove('open');
      sec.classList.remove('open-card');
      // Иконку такому заголовку тоже даём: он размечен в шаблоне вручную,
      // но выглядеть должен как остальные (П9).
      const sp = had.querySelector(':scope > span');
      if (sp && !sp.querySelector('.sec-ico')) {
        const txt = sp.textContent.trim();
        sp.innerHTML = sectionIcon(sec.id) + '<b></b>';
        sp.querySelector('b').textContent = txt;
      }
      return;
    }
    const title = sec.querySelector(':scope > .section-title');
    const name = (title ? title.textContent.trim() : '') || SECTION_NAMES[sec.id] || 'Настройки';
    const bodyId = (sec.id || 'sec') + '-fold';
    const btn = document.createElement('button');
    btn.className = 'fold-btn';
    btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('aria-controls', bodyId);
    btn.innerHTML = '<span>' + sectionIcon(sec.id) + '<b></b></span>' + FOLD_CHEVRON;
    btn.querySelector('span > b').textContent = name;
    const body = document.createElement('div');
    body.className = 'fold-body';
    body.id = bodyId;
    if (title) title.remove();
    while (sec.firstChild) body.appendChild(sec.firstChild);
    sec.appendChild(btn);
    sec.appendChild(body);
  });
  wireFolds();
  syncFirstCard();
}

// Новая сцена открывается со всеми закрытыми карточками: что было развёрнуто
// в прошлом сюжете, к новому отношения не имеет.
function collapseCards() {
  document.querySelectorAll('#tools-panel .tools-body > .section').forEach(sec => {
    const btn = sec.querySelector(':scope > .fold-btn');
    const box = sec.querySelector(':scope > .fold-body');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    if (box) box.classList.remove('open');
    sec.classList.remove('open-card');
  });
}

// Отметить активную букву «А» под текущий размер подписей (П50).
function syncLabelSizeSeg() {
  const map = { 12: 'lbl-s', 16: 'lbl-m', 20: 'lbl-l' };
  const want = map[+STATE.labelSize] || 'lbl-s';
  document.querySelectorAll('#lblsize-seg .seg-btn')
    .forEach(b => b.classList.toggle('active', b.id === want));
}

/* Раскрыть карточку по её id. Нужна, когда блок должен открыться не от щелчка
   по заголовку, а сам: закрепка ключевой точки кладёт точку в «Точки на
   графике», и закрытый блок читался бы как «ничего не произошло» (П38). */
function openSection(secId) {
  const sec = document.getElementById(secId);
  if (!sec) return;
  const btn = sec.querySelector(':scope > .fold-btn');
  const box = sec.querySelector(':scope > .fold-body');
  if (btn) btn.setAttribute('aria-expanded', 'true');
  if (box) box.classList.add('open');
  sec.classList.add('open-card');
  setToolsOpen(true);                     // сама панель тоже могла быть свёрнута
  if (box && box.scrollIntoView) box.scrollIntoView({ block: 'nearest' });
}

/* Первая видимая карточка ярче остальных: сцена открывается со всеми
   закрытыми блоками, и глаз должен сразу видеть, куда нажимать. */
function syncFirstCard() {
  const all = document.querySelectorAll('#tools-panel .tools-body > .section');
  let first = null;
  all.forEach(s => { if (!first && s.style.display !== 'none') first = s; });
  all.forEach(s => s.classList.toggle('first-card', s === first));
}

function wireScene() {
  const tools = document.getElementById('tools-panel');
  const params = document.getElementById('params-panel');

  // Стрелки сворачивания у самих панелей.
  const tTog = document.getElementById('tools-toggle');
  if (tTog) tTog.addEventListener('click', () => setToolsOpen(tools.classList.contains('collapsed')));
  const pTog = document.getElementById('params-toggle');
  if (pTog) pTog.addEventListener('click', () => setParamsOpen(params.classList.contains('collapsed')));

  // Тема.
  const dTheme = document.getElementById('dock-theme');
  if (dTheme) dTheme.addEventListener('click', () => toggleCalcTheme());

  // Сохранение графиков в базу — задача следующей сессии, кнопка пока заглушка.
  const dSave = document.getElementById('dock-save');
  if (dSave) dSave.addEventListener('click', () => toast('Сохранение графиков в профиль появится в следующей версии'));

  // Экспорт: окно с заголовком и подписью, затем PNG / .tex / PDF.
  const dExport = document.getElementById('dock-export');
  if (dExport) dExport.addEventListener('click', () => openExport());
  const expClose = document.getElementById('exp-close');
  if (expClose) expClose.addEventListener('click', () => closeExport());
  const expModal = document.getElementById('export-modal');
  if (expModal) expModal.addEventListener('click', (e) => { if (e.target === expModal) closeExport(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && expModal && expModal.classList.contains('open')) closeExport();
  });

  // Конструктор кусочной функции: собранная запись уходит в то поле формулы,
  // из справки которого его открыли.
  const pwModal = document.getElementById('pw-modal');
  const pwClose = document.getElementById('pw-close');
  if (pwClose) pwClose.addEventListener('click', () => closePiecewise());
  if (pwModal) pwModal.addEventListener('click', (e) => { if (e.target === pwModal) closePiecewise(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && pwModal && pwModal.classList.contains('open')) closePiecewise();
  });
  // Число кусков задаётся числом: два, три, а понадобится семь — тоже можно.
  const pwCount = document.getElementById('pw-count');
  if (pwCount) pwCount.addEventListener('input', () => {
    const n = parseInt(pwCount.value, 10);
    if (!isFinite(n) || n < 2 || n > 12) return;
    PW.n = n;
    renderPw();
  });
  const pwApply = document.getElementById('pw-apply');
  if (pwApply) pwApply.addEventListener('click', () => {
    if (PW.inp) {
      // Движку — цепочку условий, полю — одну фигурную скобку. Правится она
      // прямо в строке: разбор скобки обратно в выражение умеет latexToMath.
      setFieldValue(PW.inp, pwFormula());
      if (PW.inp._mf) { PW.inp._mf.value = pwLatex(); PW.inp._mf.focusField(); }
      else PW.inp.focus();
    }
    closePiecewise();
  });
  const expPng = document.getElementById('exp-png');
  if (expPng) expPng.addEventListener('click', () => exportPNG(2));   // 2× — читаемо в печати
  const expTex = document.getElementById('exp-tex');
  if (expTex) expTex.addEventListener('click', () => exportTex());
  const expPdf = document.getElementById('exp-pdf');
  if (expPdf) expPdf.addEventListener('click', () => exportPDF());

  // «Назад к сценариям».
  const back = document.getElementById('scene-back');
  if (back) back.addEventListener('click', () => openPicker());

  wireWrench();
  wireHintButtons();

  // График перерисовываем, когда меняется его РАЗМЕР, а не только окно:
  // сворачивание панели меняет ширину холста, и без этого кривые остались бы
  // нарисованными по старой геометрии.
  /* Наблюдатель за размером холста. Тонкое место: redrawAll пересоздаёт всё
     содержимое #graph-wrap, наблюдаемый размер от этого «меняется», и
     наблюдатель зовёт перерисовку снова. Флаг с requestAnimationFrame такой
     цикл НЕ разрывает — он лишь ограничивает его одной перерисовкой за кадр,
     и страница никогда не приходит в покой. Поэтому три предохранителя. */
  const gw = document.getElementById('graph-wrap');
  if (gw && typeof ResizeObserver === 'function') {
    let lastW = 0, lastH = 0, pending = false, burst = 0, off = false;
    const size = () => { const r = gw.getBoundingClientRect(); return [r.width, r.height]; };
    const ro = new ResizeObserver(() => {
      if (off || pending) return;
      const [w, h] = size();
      // 1. Меньше пикселя по обеим осям — считаем, что размер не менялся.
      if (Math.abs(w - lastW) < 1 && Math.abs(h - lastH) < 1) return;
      lastW = w; lastH = h;
      // 3. Пять срабатываний подряд без участия человека — это самоподдержка.
      if (++burst > 5) {
        off = true;
        ro.unobserve(gw);
        console.warn('calc2: холст перерисовывал сам себя пять раз подряд — наблюдатель размера выключен до следующего действия.');
        return;
      }
      pending = true;
      // 2. На время перерисовки наблюдение снимаем: перерисовка физически не
      //    может вызвать сама себя. Возвращаем уже в следующем кадре.
      ro.unobserve(gw);
      requestAnimationFrame(() => {
        STATE.resizeRedraws = (STATE.resizeRedraws || 0) + 1;
        redrawAll();
        requestAnimationFrame(() => {
          pending = false;
          const s = size(); lastW = s[0]; lastH = s[1];
          if (!off) ro.observe(gw);
        });
      });
    });
    const s0 = size(); lastW = s0[0]; lastH = s0[1];
    ro.observe(gw);
    // Счётчик обнуляет любое действие человека: настоящее изменение окна,
    // щелчок или клавиша. Выключенный предохранителем наблюдатель тогда же
    // возвращается к работе.
    const calm = () => { burst = 0; if (off) { off = false; ro.observe(gw); } };
    window.addEventListener('resize', calm);
    document.addEventListener('pointerdown', calm, true);
    document.addEventListener('keydown', calm, true);
  }
}

/* ---------------------------------------------------------------------
   МЕНЮ НАСТРОЕК КООРДИНАТНОЙ ПЛОСКОСТИ (Фаза 2).
   Сюда переехали бывшие секции «Все настройки» и «Сетка»: границы осей,
   шаг делений, названия осей, вид сетки, легенда и заголовок графика.
   --------------------------------------------------------------------- */
function setWrenchOpen(open) {
  const pop = document.getElementById('wrench-pop');
  const btn = document.getElementById('btn-wrench');
  if (!pop) return;
  pop.classList.toggle('open', open);
  if (btn) { btn.classList.toggle('on', open); btn.setAttribute('aria-expanded', open ? 'true' : 'false'); }
  if (open) syncViewFields();
}

// Применить границы из полей меню. Пустое или битое поле не трогает ось.
function applyViewBounds() {
  const num = (id) => {
    const e = document.getElementById(id);
    const v = e ? parseFloat(e.value) : NaN;
    return isFinite(v) ? v : null;
  };
  const x0 = num('inp-qmin'), x1 = num('inp-qmax'), y0 = num('inp-pmin'), y1 = num('inp-pmax');
  if (STATE.mode === 'math') {
    const a = (x0 == null ? STATE.mathXmin : x0), b = (x1 == null ? STATE.mathXmax : x1);
    const c = (y0 == null ? STATE.mathYmin : y0), d = (y1 == null ? STATE.mathYmax : y1);
    if (!(b > a) || !(d > c)) return;
    setMathWindow(a, b, c, d);
  } else {
    const a = (x0 == null ? CONFIG.Qmin : x0), b = (x1 == null ? CONFIG.Qmax : x1);
    const c = (y0 == null ? CONFIG.Pmin : y0), d = (y1 == null ? CONFIG.Pmax : y1);
    if (!(b > a) || !(d > c)) return;
    CONFIG.Qmin = a; CONFIG.Qmax = b; CONFIG.Pmin = c; CONFIG.Pmax = d;
    cancelRangeAnim();
  }
  markViewDirty();
  redrawAll();
}

/* Переключатель «только первая четверть». Включили — окно подтягивается к нулю;
   выключили — открывается отрицательная часть плоскости. Работает и в
   экономических сценах, и в «Математике». */
function setFirstQuad(on) {
  STATE.firstQuad = !!on;
  const c = document.getElementById('chk-quad');
  if (c && c.checked !== STATE.firstQuad) c.checked = STATE.firstQuad;
  if (STATE.mode === 'math') {
    setMathWindow(STATE.mathXmin, STATE.mathXmax, STATE.mathYmin, STATE.mathYmax);
    if (!STATE.firstQuad && STATE.mathXmin >= 0 && STATE.mathYmin >= 0) {
      // Возвращаемся к полному плану: показываем и отрицательную часть.
      const w = STATE.mathXmax - STATE.mathXmin, h = STATE.mathYmax - STATE.mathYmin;
      setMathWindow(-w * 0.5, STATE.mathXmax, -h * 0.5, STATE.mathYmax);
    }
  } else if (STATE.firstQuad) {
    if (CONFIG.Qmin < 0) { CONFIG.Qmax -= CONFIG.Qmin; CONFIG.Qmin = 0; }
    if (CONFIG.Pmin < 0) { CONFIG.Pmax -= CONFIG.Pmin; CONFIG.Pmin = 0; }
  } else {
    if (CONFIG.Qmin >= 0) CONFIG.Qmin = -(CONFIG.Qmax - CONFIG.Qmin) * 0.25;
    if (CONFIG.Pmin >= 0) CONFIG.Pmin = -(CONFIG.Pmax - CONFIG.Pmin) * 0.25;
  }
  syncViewFields();
  redrawAll();
}

function setGridMode(mode) {
  STATE.showGrid = (mode !== 'off');
  STATE.gridDense = (mode === 'dense');
  [['grid-dense', 'dense'], ['grid-plain', 'plain'], ['grid-off', 'off']].forEach(([id, m]) => {
    const b = document.getElementById(id); if (b) b.classList.toggle('active', m === mode);
  });
  redrawAll();
}

/* Вопросики с пояснениями. Кнопка знает id своего блока, поэтому новый
   вопросик добавляется одной парой тегов, без правки кода. */
/* ── Инструкции под вопросиком (Фаза 5) ───────────────────────────────
   Абзац-объяснение посреди панели нужен один раз, а висит всегда. Прячем его
   и ставим у ближайшего заголовка вопросик: навёл — текст всплыл, увёл — исчез.

   Сам абзац остаётся в разметке и только скрыт: сцены правят его текстом
   (у внешнего эффекта он меняется со знаком), и подсказка всплывает уже с
   новым содержимым. Формулы внутри печатаются как формулы (Фаза 4). */
function hintTip() {
  let t = document.getElementById('hint-tip');
  if (!t) {
    t = document.createElement('div');
    t.id = 'hint-tip';
    t.setAttribute('role', 'tooltip');
    document.body.appendChild(t);
  }
  return t;
}

function showHintTip(dot, html) {
  const t = hintTip();
  t.innerHTML = html;
  renderMathIn(t);
  t.style.display = 'block';
  const b = dot.getBoundingClientRect();
  const w = t.offsetWidth, h = t.offsetHeight;
  let left = b.left + b.width / 2 - w / 2;
  left = Math.max(8, Math.min(window.innerWidth - w - 8, left));
  let top = b.bottom + 8;
  if (top + h > window.innerHeight - 8) top = Math.max(8, b.top - h - 8);
  t.style.left = Math.round(left) + 'px';
  t.style.top = Math.round(top) + 'px';
}
function hideHintTip() {
  const t = document.getElementById('hint-tip');
  if (t) t.style.display = 'none';
}

/* Куда повесить вопросик. Порядок от самого крупного заголовка к самому
   мелкому: подпись, стоящая ближе всего к объяснению, и есть его хозяин.
   Отдельная строка с одним «?» посреди панели читается как обломок, поэтому
   она — последнее средство. */
function hintAnchor(hint) {
  // 1. Подзаголовок своего блока: ближайший .vsub ВЫШЕ подсказки.
  let n = hint;
  while (n && n !== document.body) {
    let prev = n.previousElementSibling;
    while (prev) {
      if (prev.classList && prev.classList.contains('vsub')) return prev;
      const inner = prev.querySelector && prev.querySelector('.vsub');
      if (inner) return inner;
      prev = prev.previousElementSibling;
    }
    if (n.classList && n.classList.contains('section')) break;
    n = n.parentElement;
  }
  // 2. Заголовок секции (обычный или складной).
  const sec = hint.closest('.section');
  if (sec) {
    const fold = sec.querySelector(':scope > .fold-btn > span');
    if (fold) return fold;
    const title = sec.querySelector(':scope > .section-title');
    if (title) return title;
  }
  // 3. Подпись поля, внутри которого лежит объяснение.
  const field = hint.closest('.field, .f-wrap');
  const lab = field && field.querySelector(':scope > label');
  if (lab) return lab;
  // 4. Предыдущая подпись-галочка: вопросик встаёт прямо в её строку.
  let prev = hint.previousElementSibling;
  while (prev) {
    if (prev.tagName === 'LABEL') return prev;
    prev = prev.previousElementSibling;
  }
  // 5. Своя строка. Сюда попадают подсказки, у которых заголовка нет вовсе.
  const own = document.createElement('div');
  own.className = 'help-anchor';
  hint.parentNode.insertBefore(own, hint);
  return own;
}

function hintsToDots(root) {
  root = root || document.getElementById('tools-panel');
  if (!root) return;
  root.querySelectorAll('.hint').forEach(hint => {
    if (hint._dotted || hint.classList.contains('hint-keep')) return;
    const anchor = hintAnchor(hint);
    if (!anchor) return;                 // некуда вешать — оставляем абзац как был
    hint._dotted = true;
    hint.classList.add('hint-hidden');

    let dot = anchor.querySelector(':scope > .help-dot');
    if (!dot) {
      dot = document.createElement('button');
      dot.type = 'button';
      dot.className = 'help-dot';
      dot.textContent = '?';
      dot.setAttribute('aria-label', 'Подсказка');
      dot._hints = [];
      anchor.appendChild(dot);
      // У одного заголовка может висеть несколько подсказок, и часть из них
      // сцена прячет (у внешнего эффекта свой текст на каждый знак). Показываем
      // только те, что сейчас в силе; спрятана ли секция — решает fieldActive,
      // а собственный display:none абзаца проверяем отдельно.
      const live = (h) => h.style.display !== 'none' && fieldActive(h.parentElement || h);
      const show = () => {
        const on = dot._hints.filter(live);
        showHintTip(dot, (on.length ? on : dot._hints).map(h => h.innerHTML).join('<hr>'));
      };
      dot.addEventListener('pointerenter', show);
      dot.addEventListener('focus', show);
      dot.addEventListener('pointerleave', hideHintTip);
      dot.addEventListener('blur', hideHintTip);
      dot.addEventListener('click', (e) => { e.preventDefault(); show(); });
    }
    dot._hints.push(hint);
  });
}

function wireHintButtons() {
  document.querySelectorAll('.hint-btn[data-pop]').forEach(btn => {
    const pop = document.getElementById(btn.getAttribute('data-pop'));
    if (!pop) return;
    btn.setAttribute('aria-expanded', 'false');
    btn.addEventListener('click', () => {
      const open = pop.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
}

function wireWrench() {
  const btn = document.getElementById('btn-wrench');
  const pop = document.getElementById('wrench-pop');
  if (btn) btn.addEventListener('click', (e) => {
    e.stopPropagation();
    setWrenchOpen(!pop.classList.contains('open'));
  });
  // Щелчок мимо меню закрывает его; внутри — нет.
  document.addEventListener('pointerdown', (e) => {
    if (!pop || !pop.classList.contains('open')) return;
    if (pop.contains(e.target) || (btn && btn.contains(e.target))) return;
    setWrenchOpen(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && pop && pop.classList.contains('open')) setWrenchOpen(false);
  });

  // П53: приблизить и отдалить — от центра видимой области, как клавиши «+»/«−».
  const zi = document.getElementById('btn-zoomin');
  if (zi) zi.addEventListener('click', () => zoomStep(1 / 1.25));
  const zo = document.getElementById('btn-zoomout');
  if (zo) zo.addEventListener('click', () => zoomStep(1.25));
  const rv = document.getElementById('btn-resetview');
  if (rv) rv.addEventListener('click', () => resetZoom());

  ['inp-qmin', 'inp-qmax', 'inp-pmin', 'inp-pmax'].forEach(id => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('change', () => applyViewBounds());
  });
  [['inp-xstep', 'xStep'], ['inp-ystep', 'yStep']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('input', () => {
      const v = parseFloat(e.value);
      STATE[key] = (isFinite(v) && v > 0) ? v : 0;
      redrawAll();
    });
  });
  [['inp-xname', 'axisXName'], ['inp-yname', 'axisYName']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('input', () => { STATE[key] = e.value.trim(); redrawAll(); });
  });
  [['grid-dense', 'dense'], ['grid-plain', 'plain'], ['grid-off', 'off']].forEach(([id, m]) => {
    const b = document.getElementById(id); if (b) b.addEventListener('click', () => setGridMode(m));
  });
  const leg = document.getElementById('chk-legend');
  if (leg) leg.addEventListener('change', () => { STATE.showLegend = leg.checked; redrawAll(); });
  const quad = document.getElementById('chk-quad');
  if (quad) quad.addEventListener('change', () => setFirstQuad(quad.checked));
  const gt = document.getElementById('inp-gtitle');
  if (gt) gt.addEventListener('input', () => { STATE.graphTitle = gt.value; redrawAll(); });
  const ls = document.getElementById('inp-lblsize');
  if (ls) ls.addEventListener('input', () => { STATE.labelSize = parseFloat(ls.value); redrawAll(); });
  // П50: три буквы А вместо числового поля. 12 · 16 · 20.
  [['lbl-s', 12], ['lbl-m', 16], ['lbl-l', 20]].forEach(([id, size]) => {
    const b = document.getElementById(id);
    if (!b) return;
    b.addEventListener('click', () => {
      STATE.labelSize = size;
      document.querySelectorAll('#lblsize-seg .seg-btn')
        .forEach(x => x.classList.toggle('active', x === b));
      redrawAll();
    });
  });
  syncLabelSizeSeg();
  // Цвет заголовка — тем же пикером, что и у кривых.
  const slot = document.getElementById('gtitle-color-slot');
  if (slot && !slot.firstChild) {
    slot.appendChild(makeColorPicker(STATE.titleColor || cssVar('--ink'),
      (hex) => { STATE.titleColor = hex; redrawAll(); }, 'Цвет названия графика'));
  }
}

