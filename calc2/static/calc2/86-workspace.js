// Рабочее место: шапка, панели, меню координатной плоскости.
/* ---------------------------------------------------------------------
   ЭКРАН 2 — рабочее место «Сцена».
   Перекомпоновка: те же контролы и те же #info-* блоки, лишь переставленные.
   Вторичные секции (режим/сцены/оси) → в раскрывашку «Все настройки»;
   блоки результатов → в плавающее табло справа.
   --------------------------------------------------------------------- */
const SCENE_NAMES = {
  sd: 'Спрос и предложение', sdsum: 'Сложение спросов и предложений',
  tax: 'Потоварные налоги и субсидии', ceil: 'Пол и потолок цены',
  mono: 'Стандартная монополия', elast: 'Эластичность', ext: 'Внешние эффекты',
  costs: 'Издержки фирмы', ppf: 'Построение КПВ',
  // п. 67. Ровно то же, что написано на карточке блока «Рынок труда».
  labor: 'Конкурентный рынок труда', ineq: 'Неравенство доходов',
  consumer: 'Кривые безразличия',
  adas: 'AD–AS', phillips: 'Кривая Филлипса', money: 'Денежный рынок',
  loanable: 'Рынок заёмных средств', fx: 'Валютный рынок', laffer: 'Кривая Лаффера', islm: 'IS–LM',
  // Международная торговля — четыре РАЗНЫЕ модели, названия разводят их явно
  // (Фаза 4): первые две — рикардианские, через КПВ и альтернативные издержки;
  // третья — частичное равновесие по ЦЕНЕ; четвёртая — фирма с рыночной властью.
  ppfsum: 'Сложение КПВ',
  trade: 'КТВ. Одна страна',
  tradeprice: 'КТВ. Две страны-партнёра',
  smallopen: 'Малая открытая экономика',
  monoexport: 'Монополист и внешний рынок',
  // Математика (Фаза 7) — общий инструментарий, вне экономических моделей.
  'm-graph': 'Построение графиков',
  'm-tangent': 'Функция и её производная наглядно', 'm-optimum': 'Максимумы и минимумы',
  'm-transform': 'Деформации графика',
  'm-minmax': 'Функции min и max', 'm-constraint': 'Оптимум при ограничении',
  // Карточки, разложенные из подрежимов при переходе на 10 блоков.
  taxes: 'Налоги и субсидии',
  quota: 'Квоты',
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
const RESULT_IDS = ['info-graph', 'info-areas', 'info-sum', 'info-tax', 'info-mono', 'info-nat', 'info-costs',
  'info-prod', 'info-iso', 'info-plants', 'info-labor',
  'info-inequality', 'info-consumer', 'info-macro', 'info-math', 'info-elast', 'info-ext', 'info-open', 'info-d3', 'info-kink',
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
/* ⚠️ ГАШЕНИЕ ОТЛОЖЕННОЕ, А НЕ НЕМЕДЛЕННОЕ. Немедленное давало по две записи
   в каждое табло за кадр («пусто», потом содержимое) и сводило на нет проверку
   «текст не изменился — набирать нечего» (см. guardPanelBoxes в 60-overlays.js).
   Помечаем «погасить, если никто не напишет»; гасит помеченные
   flushPendingPanelClears в конце перерисовки. Смысл тот же, а перенабора нет. */
function clearResultPanels() {
  /* ⚠️ info-final ГАСИТСЯ ЗДЕСЬ, ХОТЯ В RESULT_IDS ЕГО НЕТ, И ОДНО ИЗ ДРУГОГО
     НЕ СЛЕДУЕТ. В том списке он не значится нарочно (иначе relocateForScene
     унёс бы его в конец табло), но гасить его надо ровно так же: иначе
     итоговая функция прошлой сцены пережила бы переключение и стояла бы
     первой строкой в чужой модели. */
  ['info-eq', 'info-final'].concat(RESULT_IDS).forEach(id => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e._panelGuarded) { e._pendingClear = true; return; }
    e.innerHTML = '';
  });
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
  if (p) {
    p.classList.toggle('collapsed', !open);
    /* На узком экране правая панель сворачивается сама (А57). Пометка
       «открыл человек» отменяет это правило: раз развернул руками, панель
       остаётся развёрнутой. */
    p.classList.toggle('user-open', !!open);
  }
  const b = document.getElementById(btnId);
  if (b) {
    b.setAttribute('aria-expanded', open ? 'true' : 'false');
    // Подпись идёт за состоянием: свёрнутая панель предлагает открыть, открытая — закрыть.
    b.setAttribute('data-tip', open ? 'Закрыть меню' : 'Открыть меню');
    if (typeof syncTipLabels === 'function') syncTipLabels();   // и подпись для чтеца тоже
  }
  /* Панель раскрыли — поля формул внутри стали видны и собираются (А56).
     Без этого поле, добавленное при свёрнутой панели, оставалось обычным
     текстовым окошком до следующей перерисовки. */
  if (open && typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
}
function setToolsOpen(open) { setSideOpen('tools-panel', 'tools-toggle', open); }
function setParamsOpen(open) { setSideOpen('params-panel', 'params-toggle', open); }

/* А53. Раньше в двух сюжетах «Аналитики» не было вовсе: считалось, что в
   построении графиков и в деформациях считать нечего. На деле блоки всё равно
   открывались и оказывались ПУСТЫМИ, а «Построение графиков» это первая сцена,
   которую открывает новый человек: он раскрывал объяснение и видел пустоту.

   Считать там есть что: нули функции, её экстремумы, пересечения кривых между
   собой, вид деформации и то, как она двигает график. Пустой список остаётся
   пустым только пока не введена ни одна формула. */
function hasAnalytics() { return true; }

/* Разбор «как это получилось» сцены пишут внутрь своего блока расчётов. Здесь
   он одним проходом уезжает в «Объяснение модели»: так новому блоку аналитики
   ничего дополнительно делать не нужно, достаточно поставить врезку .sb-note.
   Внутренний заголовок «Как это получилось» снимаем — он стал дублем названия
   блока; свои заголовки («Почему КТВ ломается») остаются. */
function moveExplanations() {
  const from = document.getElementById('sb-body');
  const to = document.getElementById('ex-body');
  if (!from || !to) return;
  /* ⚠️ ПЕРЕЕЗД — ОДНОРАЗОВАЯ ОПЕРАЦИЯ, А НЕ ЕЖЕКАДРОВАЯ.
     Врезка ЗАБИРАЕТСЯ из табло, поэтому после переезда в табло её больше нет.
     Пока табло переписывалось на каждом кадре, врезка появлялась заново и
     переезжала заново — и это выглядело как работающий цикл. Теперь табло с
     тем же текстом не переписывается (см. guardPanelBoxes), и такой проход
     просто вычистил бы «Объяснение модели» досуха: замер 25.08 — разбор в
     «Построении графиков» становился пустым на втором кадре.
     Ничего в табло не изменилось и сцена та же — значит разбор уже на месте. */
  const scene = String(STATE.mode) + '|' + (typeof baseScene === 'function' ? baseScene() : '');
  const changed = (typeof panelsChangedSinceLastPass === 'function') ? panelsChangedSinceLastPass() : true;
  if (!changed && to._explainFor === scene && to.children.length) return;
  to._explainFor = scene;
  to.innerHTML = '';
  /* ⚠️ ВРЕЗКА КОПИРУЕТСЯ, А НЕ ЗАБИРАЕТСЯ, И ЭТО ГЛАВНОЕ ЗДЕСЬ.
     Раньше узел ПЕРЕНОСИЛСЯ: после переноса в табло его не оставалось, и
     повторный проход собирать было нечего. Работало это только потому, что
     табло переписывалось заново на каждом кадре и врезка появлялась снова.
     Как только табло перестало переписываться без надобности, перенос стал
     одноразовым: первый проход уносил врезку, второй чистил «Объяснение
     модели» досуха — и разбор пропадал навсегда (замер 25.08: в «Построении
     графиков» ноль символов вместо тысячи с лишним).

     Копируем. Оригинал остаётся в табло, но переименовывается в
     `.sb-note-src` и скрывается стилем. Два следствия, и оба нужны:
       • проход стал повторяемым — собирать всегда есть что;
       • проверка «врезка не осталась в расчётах» по-прежнему верна: класса
         `.sb-note` в табло нет ни одного. */
  from.querySelectorAll('.sb-note, .sb-note-src').forEach(src => {
    const copy = src.cloneNode(true);
    copy.classList.remove('sb-note-src');
    copy.classList.add('sb-note');
    const h = copy.querySelector('b');
    if (h && h.textContent.trim() === 'Как это получилось') h.remove();
    src.classList.remove('sb-note');
    src.classList.add('sb-note-src');
    to.appendChild(copy);
  });
  /* Н29. Сцена, которая разбор не пишет, берёт его из общего реестра
     (90-explain.js). Свой разбор сцены главнее: если она что-то положила в
     табло, реестр не подключается. */
  if (!to.children.length && typeof sceneExplainHtml === 'function') {
    const html = sceneExplainHtml();
    if (html) to.innerHTML = html;
  }
  /* Пересечение вне первой четверти — отдельный абзац В КОНЦЕ разбора, а не
     вместо него. Общий рассказ сцены при этом остаётся на месте: он про то,
     как модель устроена, а этот абзац — про конкретную ловушку в введённых
     сейчас формулах. */
  if (typeof offQuadExplainHtml === 'function') {
    const extra = offQuadExplainHtml();
    if (extra) to.insertAdjacentHTML('beforeend', extra);
  }
  /* Тем же приёмом — разбор выбранной процентной формы налога или субсидии:
     соотношение цен и формула сбора. Абзац про конкретную форму, а не про
     устройство модели, поэтому он идёт в конец, а не вместо общего рассказа. */
  if (typeof pctFormExplainHtml === 'function') {
    const pct = pctFormExplainHtml();
    if (pct) to.insertAdjacentHTML('beforeend', pct);
  }
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
  'sec-curves': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 18C10 18 13 9 18 6" stroke-width="2.6"/>',
  // Построение графиков: две кривые.
  'sec-graph': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 18c4-2 6-8 13-12" stroke-width="2.6"/><path d="M5 8c5 4 8 7 13 9" stroke-width="2.2" stroke-dasharray="5 4"/>',
  // Равновесие: пересечение и точка.
  'sec-eq': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 6l13 12M5 18L18 6" stroke-width="2.2"/><circle cx="11.5" cy="12" r="3.6" stroke-width="2.6"/>',
  // Излишки: закрашенная область.
  // Ввод функций: кривая на осях — единственная карточка ввода во всех сценах.
  'sec-input': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 17c5 0 9-4 13-11" stroke-width="2.6"/>',
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
  'sec-view': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><circle cx="9" cy="14" r="3.6" fill="currentColor" stroke="none"/><circle cx="16" cy="8" r="3.6" fill="currentColor" stroke="none"/>',
  // Площади: заштрихованная фигура под кривой.
  'sec-areascalc': '<path d="M4 20V4M4 20h16" stroke-width="1.5"/><path d="M5 19V9l13 10z" fill="currentColor" fill-opacity=".16" stroke="none"/><path d="M5 9l13 10" stroke-width="2.6"/>',
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

/* Три буквы «А» и размер, который каждая ставит (Н31). Список один на файл:
   раньше кнопки и функция отметки активной знали разные числа, и активной
   подсвечивалась не та буква, по которой щёлкнули. */
const LABEL_SIZES = [['lbl-s', 10], ['lbl-m', 14], ['lbl-l', 18]];

// Отметить активную букву «А» под текущий размер подписей (П50).
function syncLabelSizeSeg() {
  const map = {};
  LABEL_SIZES.forEach(([id, size]) => { map[size] = id; });
  const want = map[+STATE.labelSize] || 'lbl-m';
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

/* ⚠️ ПОДПИСЬ «ВВОД ФУНКЦИЙ» ПРИНАДЛЕЖИТ КАРТОЧКЕ, В КОТОРОЙ ЕСТЬ ЧТО ВВОДИТЬ.

   Правило Н34 («первая карточка везде называется одинаково») стояло на голом
   «первая видимая», и договор о параметрах его подсёк: в «Составном спросе»,
   «Дискриминации 3-й степени» и «Монополисте на внешнем рынке» карточка общего
   списка кривых теперь спрятана, первой видимой становится «Излишки» — и она
   получала чужое имя. Владелец на приёмке увидел ровно это: заголовок обещает
   ввод функций, под ним галочки излишков.

   Реестр ниже отвечает на вопрос «эта карточка существует ради ввода функций».
   Имя достаётся первой ВИДИМОЙ карточке из реестра; не видно ни одной — не
   переименовываем никого, каждая карточка остаётся под своим именем. Врать
   заголовком хуже, чем потерять единообразие в трёх сюжетах из сорока одного. */
/* Карточка ввода теперь ровно одна на все модели: поля разных сцен лежат
   внутри неё вложенными блоками (#sec-curves, #sec-costs и прочие), а имя
   «Ввод функций» стоит в разметке и никуда не переезжает. Реестр оставлен —
   на нём держится выделение первой карточки в syncFirstCard. */
const INPUT_CARDS = ['sec-input'];

/* Карточка, внутри которой лежит живое поле формулы. У трёх монопольных
   сюжетов свои поля стоят во вложенном блоке «Структура рынка», то есть внутри
   «Что изучаем»: реестром такое не выразить, спрашиваем сами поля. */
function cardWithFormula(all) {
  const live = (typeof FORMULA_FIELDS !== 'undefined' ? FORMULA_FIELDS : [])
    .filter(i => typeof fieldActive === 'function' && fieldActive(i));
  for (const s of all) {
    if (s.style.display === 'none') continue;
    if (live.some(i => s.contains(i))) return s;
  }
  return null;
}

/* Ярче остальных — карточка, с которой начинают: сцена открывается со всеми
   закрытыми блоками, и глаз должен сразу видеть, куда нажимать. Это та, где
   вводят формулы; нет такой вовсе — первая видимая, как было. */
function syncFirstCard() {
  const all = [...document.querySelectorAll('#tools-panel .tools-body > .section')];
  const visible = all.filter(s => s.style.display !== 'none');
  const named = visible.find(s => INPUT_CARDS.indexOf(s.id) >= 0) || null;
  const first = cardWithFormula(all) || visible[0] || null;
  all.forEach(s => s.classList.toggle('first-card', s === first));
  /* Н34. Своё имя карточки помним: перестанет быть первой — вернётся. */
  all.forEach(s => {
    const b = s.querySelector(':scope > .fold-btn span > b');
    if (!b) return;
    if (s === named) {
      if (b.dataset.ownName === undefined) b.dataset.ownName = b.textContent;
      b.textContent = 'Ввод функций';
    } else if (b.dataset.ownName !== undefined) {
      b.textContent = b.dataset.ownName;
    }
  });
}

function wireScene() {
  const rst = document.getElementById('btn-scene-reset');
  if (rst) rst.addEventListener('click', resetCurrentScene);

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

  /* Сохранения графиков в базу нет, и кнопки-заглушки в полосе тоже больше
     нет (п. 68): она занимала второе место и умела только сказать «появится
     в следующей версии». Появится сохранение — вернётся и кнопка. */

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
    /* Один кусок — законная запись, а не вырожденный случай: так задают
       функцию, определённую ТОЛЬКО на отрезке (вне его кривой нет). Нижняя
       граница была 2 и отрезала этот случай без причины. */
    if (!isFinite(n) || n < 1 || n > 12) return;
    PW.n = n;
    renderPw();
  });
  /* Сколько групп спроса и сколько предложения (сюжет сложения). Меняем
     число — добавляются или убираются ТОЛЬКО хвостовые группы, уже набранные
     формулы остаются на месте. */
  [['sum-nd', 'D'], ['sum-ns', 'S']].forEach(([id, side]) => {
    const e = document.getElementById(id);
    if (!e) return;
    e.addEventListener('input', () => {
      const n = parseInt(e.value, 10);
      if (!isFinite(n) || n < 1 || n > 8) return;
      if (typeof sumSetCount === 'function') sumSetCount(side, n);
    });
  });
  const pwApply = document.getElementById('pw-apply');
  if (pwApply) pwApply.addEventListener('click', () => {
    if (PW.inp) {
      // Движку — цепочку условий, полю — одну фигурную скобку. Правится она
      // прямо в строке: разбор скобки обратно в выражение умеет latexToMath.
      // Приставка («y = », «P = ») читается из ТЕКУЩЕГО значения поля и
      // сохраняется — см. pwPrefixOf: без неё КПВ и «Неравенство доходов»
      // либо путают «>=» условия со знаком равенства, либо просто не
      // разбирают голую запись.
      const prefix = pwPrefixOf(PW.inp.value);
      setFieldValue(PW.inp, prefix + pwFormula());
      if (PW.inp._mf) { PW.inp._mf.value = prefix + pwLatex(); PW.inp._mf.focusField(); }
      else PW.inp.focus();
      /* Поле применяется по Enter или по своей кнопке «Построить», не по
         одному вводу текста (см. applyPpf/applyIneqFm) — setFieldValue выше
         только пишет текст и будит предпросмотр, но НЕ применяет его. Тот же
         Enter, каким уже пользуется MathLive-поле при пересылке в inp
         (см. `mf.addEventListener('keydown', ...)` выше), доводит дело до
         конца и здесь. */
      PW.inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    }
    closePiecewise();
  });
  const expPng = document.getElementById('exp-png');
  if (expPng) expPng.addEventListener('click', () => exportPNG(2));   // 2× — читаемо в печати
  const expTex = document.getElementById('exp-tex');
  if (expTex) expTex.addEventListener('click', () => exportTex());
  const expPdf = document.getElementById('exp-pdf');
  if (expPdf) expPdf.addEventListener('click', () => exportPDF());

  // «Ко всем моделям».
  const back = document.getElementById('scene-back');
  if (back) back.addEventListener('click', () => openPicker());

  wireWrench();
  wireHintButtons();
  wireTips();               // п. 78–81: одна плашка на все подсказки

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
/* П9. Вернуть текущую модель к исходному виду: забыть её снимок и заново
   выполнить маршрут карточки. Снимок удаляем ПЕРЕД pickScene — иначе он тут
   же восстановит ровно то, что мы отменяем. Другие модели не трогаем: у
   каждой снимок свой. */
function resetCurrentScene() {
  const key = STATE.sceneKey;
  if (!key) return;
  if (typeof forgetSceneSnapshot === 'function') forgetSceneSnapshot(key);
  pickScene(key);
  if (typeof toast === 'function') toast('Модель вернулась к исходному виду');
}

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
/* Снимок границ плоскости: `null` означает «взять текущие». */
function quadWindow(src) {
  if (src) return src;
  return { qa: CONFIG.Qmin, qb: CONFIG.Qmax, pa: CONFIG.Pmin, pb: CONFIG.Pmax };
}
// Два окна считаются тем же самым с точностью до тысячной доли размаха.
function quadSameWindow(a, b) {
  if (!a || !b) return false;
  const e = Math.max(1e-6, Math.abs(b.qb - b.qa) * 1e-3, Math.abs(b.pb - b.pa) * 1e-3);
  return Math.abs(a.qa - b.qa) < e && Math.abs(a.qb - b.qb) < e
      && Math.abs(a.pa - b.pa) < e && Math.abs(a.pb - b.pb) < e;
}

/* ── ТОЧКИ, КОТОРЫЕ СЦЕНА ПОКАЗЫВАЕТ ВНЕ ПЕРВОЙ ЧЕТВЕРТИ ──────────────
   Их ровно три вида, и все три названы решением владельца о правиле первой
   четверти: центр поворота при процентном налоге, пересечение кривых вне
   четверти и конец продолжения предельной кривой.

   ⚠️ СПИСОК БЕРЁТСЯ У НАРИСОВАННОГО, А НЕ У ВТОРОЙ КОПИИ ПРАВИЛА.
   Продолжение предельной кривой рисуют четыре сцены, и докуда оно тянется,
   знает только сам рисователь (`drawMarginalCurve`: до нуля породившей
   кривой). Переписывать это условие здесь значило бы завести вторую точку
   правды, которая разойдётся с первой. Поэтому хвосты читаются с холста по
   их собственной пометке `data-marginal-tail`, а пиксели переводятся обратно
   теми же шкалами. Две точки, которые сцена знает точно, берутся из модели. */
function offQuadShownPoints() {
  const pts = [];
  if (STATE.offEq && isFinite(STATE.offEq.Q) && isFinite(STATE.offEq.P)) {
    pts.push([STATE.offEq.Q, STATE.offEq.P]);
  }
  if (typeof taxPivotPoint === 'function') {
    const p = taxPivotPoint();
    if (p && isFinite(p.Q) && isFinite(p.P)) pts.push([p.Q, p.P]);
  }
  if (typeof sx === 'function' && typeof sy === 'function') {
    document.querySelectorAll('path[data-marginal-tail]').forEach(el => {
      String(el.getAttribute('d') || '').split(/(?=[ML])/).forEach(tok => {
        const m = tok.match(/[ML]\s*(-?[\d.eE+]+)[,\s]+(-?[\d.eE+]+)/);
        if (!m) return;
        const q = sx.invert(+m[1]), p = sy.invert(+m[2]);
        if (isFinite(q) && isFinite(p)) pts.push([q, p]);
      });
    });
  }
  // Интересны только те, что ДЕЙСТВИТЕЛЬНО лежат вне первой четверти.
  return pts.filter(([q, p]) => q < -1e-9 || p < -1e-9);
}

/* Раздвинуть окно так, чтобы такие точки попали в кадр с запасом по краю.
   Возвращает true, если окно действительно изменилось.

   Решение владельца 25.08: «снятая галочка „только первая четверть“ сама
   раздвигает окно до точек вне четверти». Запас — восьмая часть нынешнего
   окна: точка, легшая ровно на границу, читается как обрыв кривой, а не как
   то, что нам хотели показать. */
function fitWindowToOffQuad() {
  const pts = offQuadShownPoints();
  if (!pts.length) return false;                 // показывать нечего — окно не трогаем
  let qa = CONFIG.Qmin, qb = CONFIG.Qmax, pa = CONFIG.Pmin, pb = CONFIG.Pmax;
  const padQ = Math.max(1e-9, (qb - qa) * 0.08);
  const padP = Math.max(1e-9, (pb - pa) * 0.08);
  pts.forEach(([q, p]) => {
    if (q - padQ < qa) qa = q - padQ;
    if (q + padQ > qb) qb = q + padQ;
    if (p - padP < pa) pa = p - padP;
    if (p + padP > pb) pb = p + padP;
  });
  const same = (a, b) => Math.abs(a - b) < 1e-9;
  if (same(qa, CONFIG.Qmin) && same(qb, CONFIG.Qmax)
      && same(pa, CONFIG.Pmin) && same(pb, CONFIG.Pmax)) return false;
  CONFIG.Qmin = qa; CONFIG.Qmax = qb; CONFIG.Pmin = pa; CONFIG.Pmax = pb;
  /* Окно перестало быть масштабом сцены, значит и авто-подгонка молчит, и
     кнопка «Вернуть исходный вид» на месте — ровно как после колеса мыши. */
  STATE.viewDirty = true;
  return true;
}

function setFirstQuad(on) {
  const before = quadWindow(null);       // окно ДО переключения — для обратного хода
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
    /* ⚠️ ВЫКЛЮЧЕНИЕ ОБЯЗАНО ВЕРНУТЬ РОВНО ТО ОКНО, ЧТО БЫЛО ДО ВКЛЮЧЕНИЯ.
       Раньше обратного хода не было вовсе: включение считало новые границы по
       одной формуле, выключение — по другой, и «−10…10» после двух щелчков
       превращалось в «−5…20». Ноль уезжал в левый нижний угол, и вернуть
       прежний вид было нечем, кроме сброса всей сцены.
       Память самоочищается: она годится, только пока окно ровно то, которое
       мы сами и сделали. Тронул границы руками, колесом или панорамой — от
       памяти отказываемся и считаем по прежней формуле. */
    if (CONFIG.Qmin < 0) { CONFIG.Qmax -= CONFIG.Qmin; CONFIG.Qmin = 0; }
    if (CONFIG.Pmin < 0) { CONFIG.Pmax -= CONFIG.Pmin; CONFIG.Pmin = 0; }
    STATE.quadSaved = { was: quadWindow(before), made: quadWindow(null) };
  } else {
    const saved = STATE.quadSaved;
    if (saved && quadSameWindow(saved.made, quadWindow(null))) {
      CONFIG.Qmin = saved.was.qa; CONFIG.Qmax = saved.was.qb;
      CONFIG.Pmin = saved.was.pa; CONFIG.Pmax = saved.was.pb;
    } else {
      if (CONFIG.Qmin >= 0) CONFIG.Qmin = -(CONFIG.Qmax - CONFIG.Qmin) * 0.25;
      if (CONFIG.Pmin >= 0) CONFIG.Pmin = -(CONFIG.Pmax - CONFIG.Pmin) * 0.25;
    }
    STATE.quadSaved = null;
  }
  syncViewFields();
  redrawAll();
  /* ⚠️ РАЗДВИГАЕМ ПОСЛЕ ОТРИСОВКИ, И ТОЛЬКО ПРИ СНЯТИИ ГАЛОЧКИ.
     До отрисовки продолжений предельных кривых на холсте ещё нет, и спросить
     у них, докуда они тянутся, невозможно. Второй перерисовки не боимся: это
     один щелчок человека, а не кадр панорамирования.

     Разовость важна: дальше окном распоряжается человек. Колесо и панорама
     сюда не заходят, потому что setFirstQuad зовёт только сама галочка. */
  if (!STATE.firstQuad && STATE.mode !== 'math' && fitWindowToOffQuad()) {
    syncViewFields();
    redrawAll();
  }
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

  /* ⚠️ ПЛАШКА НЕ САДИТСЯ НА СОСЕДНИЙ УПРАВЛЯЮЩИЙ ЭЛЕМЕНТ.

     Правило то же, что уже записано про холст: всплывающее появляется ровно
     там, где рука ведёт указатель, и закрывает собой то, к чему рука шла.
     Здесь оно ловилось на кнопке возврата: подсказка «Ко всем моделям»
     всплывала вниз и накрывала текст кнопки «Вернуть исходный вид».

     Место выбирается перебором: снизу, сверху, справа, слева. Берём первое,
     которое помещается в окно и не накрывает ни одной кнопки, поля или
     ссылки, кроме той, к которой подсказка относится. Не нашлось ни одного —
     остаётся прежнее нижнее, лишь бы плашка была видна. */
  const clampX = (x) => Math.max(8, Math.min(window.innerWidth - w - 8, x));
  const clampY = (y) => Math.max(8, Math.min(window.innerHeight - h - 8, y));
  const midX = clampX(b.left + b.width / 2 - w / 2);
  const midY = clampY(b.top + b.height / 2 - h / 2);
  const spots = [
    { x: midX, y: b.bottom + 8 },
    { x: midX, y: b.top - h - 8 },
    { x: b.right + 8, y: midY },
    { x: b.left - w - 8, y: midY },
  ];
  const controls = Array.from(document.querySelectorAll(
    'button, input, select, textarea, a[href], [data-tip]'));
  const covers = (x, y) => controls.some(el => {
    if (el === dot || el.contains(dot) || dot.contains(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    return x < r.right - 1 && x + w > r.left + 1 && y < r.bottom - 1 && y + h > r.top + 1;
  });
  let spot = null;
  for (const s of spots) {
    if (s.x < 8 || s.x + w > window.innerWidth - 8) continue;
    if (s.y < 8 || s.y + h > window.innerHeight - 8) continue;
    if (covers(s.x, s.y)) continue;
    spot = s; break;
  }
  const left = spot ? spot.x : midX;
  let top = spot ? spot.y : b.bottom + 8;
  if (!spot && top + h > window.innerHeight - 8) top = Math.max(8, b.top - h - 8);
  t.style.left = Math.round(left) + 'px';
  t.style.top = Math.round(top) + 'px';
}
function hideHintTip() {
  const t = document.getElementById('hint-tip');
  if (t) t.style.display = 'none';
}

/* ═══ п. 78–81. ОДНА СИСТЕМА ПОДСКАЗОК ════════════════════════════════

   Было две. Знаки «?» показывали свою плашку рядом с собой; кнопки полосы,
   стрелки панелей и кнопки над графиком — собственные тёмные подписи через
   `::after`, нарисованные правилами CSS. Отсюда три беды сразу:

   · п. 79. Подпись `::after` держится, пока держится `:focus-visible`, а он
     остаётся ПОСЛЕ нажатия. Плашка «назад» висела поверх заголовка модели,
     пока человек работал в другом конце экрана. Две сразу тоже ловились:
     одна по наведению, другая по фокусу.
   · п. 78. Две системы — два вида, две геометрии, два набора правил.
   · п. 81. Текст подписи и текст для чтеца расходились, потому что жили в
     разных атрибутах и правились по отдельности.

   Теперь плашка ОДНА на весь калькулятор — тот же узел, что у знаков «?».
   Их физически не может быть две. Показывается по наведению, по фокусу с
   клавиатуры и по касанию; гаснет по уходу, по нажатию, по Escape и при
   смене модели. Текст один: `data-tip` копируется в `aria-label`, поэтому
   разойтись им негде.                                                     */
let _tipByKeyboard = false;   // последнее действие человека было с клавиатуры
function tipText(el) { return (el.getAttribute('data-tip') || '').trim(); }

/* ═══ МАТЕМАТИКА ВНУТРИ ПОДСКАЗКИ ══════════════════════════════════════

   Решение владельца 24.08: подсказки переводятся с браузерного `title` и
   простого текста на этот компонент, потому что 64 математических обозначения
   сидели именно в подсказках, а простой текст формулу нести не умеет.

   Плашка набирает формулой всё, что стоит между знаками доллара — это делает
   `renderMathIn` в `showHintTip`. Значит здесь одна забота: расставить знаки
   доллара вокруг обозначений, а слова оставить словами.

   ⚠️ СПИСОК ОБОЗНАЧЕНИЙ — ТОТ ЖЕ, ПО КОТОРОМУ СЧИТАЕТ АУДИТ ШРИФТОВ
   (`calc2/tests/night2_font_audit.mjs`). Разойдутся списки — разойдутся и
   числа: прибор будет считать одно, разметка чинить другое, и «починено N»
   перестанет что-либо значить.                                              */
const TIP_WORDS = ['SRAS', 'LRAS', 'Wmin', 'MPL', 'MRP', 'ATC', 'AVC', 'AFC', 'DWL',
  'MSB', 'MSC', 'GDP', 'MC', 'MR', 'TC', 'FC', 'VC', 'TR', 'TP', 'MP', 'AP',
  'Qd', 'Qs', 'Pd', 'Ps', 'Pb', 'Pw', 'Pc', 'Pf', 'Qm', 'Pm', 'Qc', 'Px', 'Py',
  'CS', 'PS', 'AD', 'AS', 'IS', 'LM', 'SW'];
const TIP_LETTERS = ['P', 'Q', 'D', 'S', 'L', 'K', 'X', 'Y', 'W', 'U', 'M', 'E'];
const TIP_SUBS = { '\u2080': '0', '\u2081': '1', '\u2082': '2', '\u2083': '3', '\u2084': '4' };
const TIP_RE = new RegExp(
  '(^|[^A-Za-zА-Яа-я0-9_$\\\\])(' + TIP_WORDS.join('|') + '|' + TIP_LETTERS.join('|') + ')'
  + '([\u2080-\u2084]?)(?![A-Za-zА-Яа-я0-9_$])', 'g');

/* Как набирается одно обозначение. Сплошные прописные («MC», «DWL») уходят
   прямым шрифтом — это делает `texAbbrev` сам. Прописная с хвостом («Pw»,
   «Qd») — это буква с индексом, а не произведение двух букв. */
function tipTex(word, sub) {
  const idx = TIP_SUBS[sub] || '';
  if (/^[A-Z]{2,}$/.test(word)) return word + (idx ? '_{' + idx + '}' : '');
  const m = /^([A-Z])([A-Za-z0-9]+)$/.exec(word);
  if (m) return m[1] + '_{\\text{' + m[2] + '}' + idx + '}';
  return word + (idx ? '_{' + idx + '}' : '');
}

/* Разметить обозначения в готовом человеческом тексте: «Мировая цена Pw» →
   «Мировая цена $P_{\\text{w}}$». Слова не трогаем вообще. */
function tipName(text) {
  return String(text == null ? '' : text).replace(
    TIP_RE, (all, pre, word, sub) => pre + '$' + tipTex(word, sub) + '$');
}

/* Формула целиком (запись кривой) — набирается формулой целиком. Перевод в
   LaTeX делает тот же `mathToTex`, что и предпросмотр под полем ввода: иначе
   одна и та же запись выглядела бы в двух местах по-разному. */
function tipExpr(expr) {
  const s = String(expr == null ? '' : expr).trim();
  if (!s) return '';
  if (typeof mathToTex !== 'function') return s;
  const tex = mathToTex(s);
  return tex ? '$' + tex + '$' : s;
}

/* Текст подсказки для чтеца экрана: доллары — разметка набора, вслух их не
   читают. */
function tipPlain(text) { return String(text || '').replace(/\$/g, ''); }

/* ═══════════════════════════════════════════════════════════════════════
   ИТОГОВАЯ ФУНКЦИЯ — ОДНО МЕСТО НА ВЕСЬ КАЛЬКУЛЯТОР
   (решение владельца 26.08, ADR 0028)

   Аналитическая запись посчитанной кривой — это ВЕЛИЧИНА, а не разбор. До
   26.08 каждая сцена печатала её по-своему и клала внутрь врезки `.sb-note`,
   а общий проход `moveExplanations` уносил все такие врезки в «Объяснение
   модели» и гасил оригинал стилем. Попасть в «Ключевые значения» она физически
   не могла: замер 26.08 — запись суммарной КПВ стояла седьмым абзацем из семи
   в свёрнутом по умолчанию блоке.

   Здесь она верстается ЕДИНСТВЕННЫЙ раз; сцены только отдают данные.

   ⚠️ КЛАССА `sb-note` ВНУТРИ БЛОКА БЫТЬ НЕ ДОЛЖНО НИ НА ОДНОМ УЗЛЕ — иначе
   `moveExplanations` унесёт его туда же, откуда мы вышли. На это стоит
   постоянная проверка.
   ═══════════════════════════════════════════════════════════════════════ */

const FF_MAX_PX = 15;   // канонический кегль записи: крупнее чисел табло (13)
const FF_MIN_PX = 13;   // ниже НЕ опускаемся — подгонку до 10 владелец забраковал

function ffEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ⚠️ ПЕРЕВОД В LaTeX ДЕЛАЕТ ТОЛЬКО `mathToLatexField` (82-input.js).
   Он умеет кусочную цепочку через `condChainToCases`: печатает «если»
   по-русски, сворачивает `Q ≥ a ∧ Q < b` в `a ≤ Q < b` и проглатывает
   служебный хвост NaN. Звать `mathToTex` напрямую здесь ЗАПРЕЩЕНО — это
   ровно источник дефекта «подсказка печатает ∞ и английское if». */
function ffLatexOf(o) {
  let tex = (o && o.latex) ? String(o.latex) : '';
  if (!tex) {
    const e = String((o && o.expr) == null ? '' : o.expr).trim();
    if (!e) return '';
    tex = (typeof mathToLatexField === 'function') ? mathToLatexField(e) : e;
  }
  return (o && o.lhs) ? (o.lhs + ' = ' + tex) : tex;
}

/**
 * Разметка одного блока «Итоговая функция».
 * @param {string}  o.name   человеческое имя: «Рыночный спрос $D$», «Суммарная КПВ»
 * @param {string}  o.color  цвет кривой — ТОТ ЖЕ, которым нарисована линия
 * @param {string}  o.expr   запись в синтаксисе Math.js: для копирования и для .tex
 * @param {string} [o.latex] готовый LaTeX; не передан — считается из expr
 * @param {string} [o.lhs]   левая часть равенства («P», «Y»); в expr её нет,
 *                           потому что expr обязан вставляться обратно в поле
 * @param {string} [o.note]  короткая приписка («построена численно»)
 */
function finalFunctionHtml(o) {
  if (!o) return '';
  const tex = ffLatexOf(o);
  const note = o.note ? String(o.note) : '';
  if (!tex && !note) return '';
  const color = o.color || 'var(--text)';
  let h = '<div class="ff" style="--ff-c: ' + ffEsc(color) + '">';
  h += '<div class="ff-top"><span class="ff-eyebrow">Итоговая функция</span>';
  if (o.expr) h += '<button class="ff-copy" type="button" data-tip="Скопировать запись"'
                 + ' data-ff-expr="' + ffEsc(o.expr) + '">копировать</button>';
  h += '</div>';
  h += '<div class="ff-name">' + (o.name || '') + '</div>';
  /* Сам LaTeX едет и в атрибуте: вторую форму записи (условие под формулой)
     собирать надо из исходника, а из набранного KaTeX его уже не достать. */
  if (tex) h += '<div class="ff-math" data-ff-tex="' + ffEsc(tex) + '">$' + tex + '$</div>';
  if (note) h += '<div class="ff-note">' + note + '</div>';
  h += '</div>';
  return h;
}

/* ВТОРАЯ ФОРМА ЗАПИСИ: условие куска уходит на свою строку ПОД формулу,
   фигурная скобка остаётся, кегль не трогается (решение владельца 26.08).
   Возвращает null, если это не фигурная скобка или в ней меньше двух кусков. */
function ffCasesStacked(tex) {
  const s = String(tex || '');
  const B = '\\begin{cases}', E = '\\end{cases}';
  const i = s.indexOf(B), j = s.lastIndexOf(E);
  if (i < 0 || j <= i) return null;
  const head = s.slice(0, i), tail = s.slice(j + E.length);
  const rows = s.slice(i + B.length, j).split('\\\\').map(r => r.trim()).filter(r => r.length);
  if (rows.length < 2) return null;
  const out = rows.map(r => {
    const k = r.indexOf('&');
    if (k < 0) return r;
    const body = r.slice(0, k).trim().replace(/,\s*$/, '');
    const cond = r.slice(k + 1).trim();
    if (!body || !cond) return r;
    /* `gathered` KaTeX 0.16 понимает; кегль условия снижается ГРУППОЙ, вместе
       со словом «если», если оно в условии уже стоит. */
    return '\\begin{gathered}' + body + '\\\\[-2pt]{\\footnotesize ' + cond + '}\\end{gathered}';
  });
  return head + B + out.join('\\\\[4pt]') + E + tail;
}

/* Набрать запись в узел заново (обе формы идут одним путём). */
function ffTypeset(host, tex) {
  host.textContent = '$' + tex + '$';
  if (typeof renderMathIn === 'function') renderMathIn(host);
  return host.querySelector('.katex');
}

/* ПРАВИЛО ШИРИНЫ (решение владельца 26.08, исполнять буквально).
     ШАГ 1. Обычная форма, кегль 15 px.
     ШАГ 2. Мерить ВНУТРЕННИЙ узел `.katex`, а не внешний: у обрезанной
            записи внешний узел показывает «влезло».
     ШАГ 3. Шире контейнера — вторая форма (условие под формулой).
     ШАГ 4. И она шире — кегль ступенями до 13 px, НИЖЕ 13 НЕ ОПУСКАТЬ.
            Дальше горизонтальная прокрутка с затуханием у правого края.
   Подгонка вниз до 10 px, как делает fitPanelMath, здесь ЗАПРЕЩЕНА: ровно её
   владелец и забраковал. */
/* Возвращает false, если померить было НЕЧЕМ: панель свёрнута, ширина нулевая.
   ⚠️ Это не мелочь. Панель «Ключевые значения» на входе в сцену бывает
   свёрнута, и подгонка, сделанная в этот момент, молча ничего не делала:
   запись оставалась в первой форме и торчала за край, как только человек
   панель раскрывал. Не смогли померить — значит подгонка не сделана, и
   повторить её надо при следующей возможности. */
function fitFinalMath(root) {
  const box = root || document.getElementById('info-final');
  if (!box) return true;
  let measured = true;
  box.querySelectorAll('.ff-math').forEach(host => {
    host.classList.remove('ff-scroll');
    host.removeAttribute('data-ff-form');
    host.style.fontSize = '';
    const tex = host.getAttribute('data-ff-tex') || '';
    let k = host.querySelector('.katex');
    if (!k || !tex) return;
    const have = host.clientWidth;
    if (!(have > 0)) { measured = false; return; }
    const over = () => k.getBoundingClientRect().width > have - 1;
    if (!over()) return;
    const alt = ffCasesStacked(tex);
    if (alt && alt !== tex) {
      k = ffTypeset(host, alt) || k;
      /* Пометка «набрано второй формой» — для проверок и для выгрузки: сам
         `data-ff-tex` остаётся ИСХОДНЫМ, иначе повторная подгонка складывала
         бы вторую форму из второй формы. */
      host.setAttribute('data-ff-form', 'stacked');
      if (!over()) return;
    }
    for (let px = FF_MAX_PX - 1; px >= FF_MIN_PX; px--) {
      host.style.fontSize = px + 'px';
      if (!over()) return;
    }
    host.classList.add('ff-scroll');
  });
  return measured;
}

/* Скопировать запись в синтаксисе Math.js: её можно вставить обратно в поле
   формулы. Clipboard недоступен (не защищённый контекст) — идём запасным
   путём, а не молчим. */
function ffCopyText(text) {
  const ok = () => toast('Запись скопирована');
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(ok, () => ffCopyFallback(text));
    return;
  }
  ffCopyFallback(text);
}
function ffCopyFallback(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  let done = false;
  try { done = document.execCommand('copy'); } catch (e) { done = false; }
  ta.remove();
  toast(done ? 'Запись скопирована' : 'Скопировать не удалось — выделите запись и нажмите Ctrl+C');
}
function wireFinalCopy() {
  if (wireFinalCopy._done) return;
  wireFinalCopy._done = true;
  document.addEventListener('click', (e) => {
    const b = e.target && e.target.closest ? e.target.closest('.ff-copy') : null;
    if (!b) return;
    e.preventDefault();
    ffCopyText(b.getAttribute('data-ff-expr') || '');
  });
}

/**
 * Показать итоговые функции сцены. [] | [rec] | [rec, rec] → в #info-final.
 * ⚠️ Контейнер защищён guardPanelBoxes: тот же текст — табло не переписывается.
 * Ломать это нельзя, кадр 47 → 13 мс достигнут именно отказом от перенабора.
 */
function setFinalFunctions(list) {
  const box = document.getElementById('info-final');
  if (!box) return;
  wireFinalCopy();
  const html = (list || []).filter(Boolean).map(finalFunctionHtml).join('');
  const same = (box._ffHtml === html);
  box.innerHTML = html;                  // guardPanelBoxes сам решит, писать ли
  box._ffHtml = html;
  /* Подгонку повторяем, пока она хоть раз не удалась по-настоящему: та же
     запись при свёрнутой панели меряется нулевой шириной. */
  if (same && box._ffFitDone) return;
  if (!html) { box._ffFitDone = true; return; }
  if (!same && typeof renderMathIn === 'function') renderMathIn(box);
  box._ffFitDone = fitFinalMath(box);
}

/* Панель раскрыли — подогнать ширину заново. Пока панель была свёрнута,
   мерить было нечем, и подгонка не делалась (см. fitFinalMath). */
function refitFinalMathSoon() {
  const box = document.getElementById('info-final');
  if (!box || box._ffFitDone) return;
  box._ffFitDone = fitFinalMath(box);
}

/* Подпись в РАЗМЕТКЕ (не на холсте), в которой сидит обозначение: «D», «CS»,
   «MC, предельные затраты». Обозначения уезжают в формулу, слова остаются
   словами. Разбор — тот же tipName, что у подсказок: одно место правды на
   весь калькулятор.

   Строку без обозначений печатаем текстом и KaTeX не зовём вовсе: разбор
   формул дорогой, а список кривых перерисовывается на каждое изменение. */
/* ── ОБОЗНАЧЕНИЯ В ГОТОВОЙ РАЗМЕТКЕ ПАНЕЛЕЙ ──────────────────────────────

   Подписи галочек и полей написаны в шаблоне и в сценах человеческим текстом:
   «MC, предельные затраты», «Показывать PS (TR − VC)», «Цена Px». Править их
   по одной значило бы полторы сотни правок в шаблоне и в девяти файлах сцен,
   и следующая новая подпись всё равно приехала бы обычным шрифтом.

   Поэтому разметка ставится ОДНИМ проходом по дереву панели: обозначения
   оборачиваются долларами тем же tipName, а дальше их набирает renderMathIn.
   Прогон идёт после каждой перерисовки; повторно ничего не портится, потому
   что набранное уже лежит внутри .katex и обходом не берётся.

   ⚠️ ЧЕГО НЕ КАСАЕМСЯ: поля ввода и предпросмотр формулы (там доллар — знак,
   а не разметка), готовые формулы KaTeX и MathLive, блоки кода с записью
   Math.js. В этих местах доллар обязан остаться буквальным. */
function markNotationsIn(root) {
  if (!root || typeof tipName !== 'function') return;
  /* ⚠️ СТРОКУ «ИМЯ = ЗНАЧЕНИЕ» РАЗМЕТЧИК НЕ ТРОГАЕТ.
     Её и так набирает формулой paintEqLabel, а имя для неё читается обратно из
     той же подписи. Разметив её здесь, мы кормили бы чтение собственным
     выводом: «Цена P» → «Цена $P$» → на экране «Цена PPP» (замер 24.08). */
  const SKIP = '.katex, math-field, input, textarea, code, script, style, '
             + '.f-typeset, .mf-hidden, .param-eq, .pchip-label, .reg-eq';
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => {
      const v = n.nodeValue;
      if (!v || v.indexOf('$') >= 0) return NodeFilter.FILTER_REJECT;
      if (!/[A-Z]/.test(v)) return NodeFilter.FILTER_REJECT;   // латиницы нет — обозначений нет
      const el = n.parentElement;
      if (!el || el.closest(SKIP)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const jobs = [];
  for (let n = walk.nextNode(); n; n = walk.nextNode()) jobs.push(n);
  let touched = 0;
  jobs.forEach(n => {
    const marked = tipName(n.nodeValue);
    if (marked === n.nodeValue) return;
    n.nodeValue = marked;
    touched += 1;
  });
  if (touched && typeof renderMathIn === 'function') renderMathIn(root);
}

function paintNotation(el, text) {
  if (!el) return;
  const src = String(text == null ? '' : text);
  const marked = (typeof tipName === 'function') ? tipName(src) : src;
  if (marked === src) { el.textContent = src; return; }
  el.textContent = marked;
  if (typeof renderMathIn === 'function') renderMathIn(el);
  else el.textContent = src;
}

function showTipFor(el) {
  const t = tipText(el);
  if (!t) return;
  showHintTip(el, t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'));
}

function wireTips() {
  const near = (e) => (e.target && e.target.closest) ? e.target.closest('[data-tip]') : null;
  // Наведение и уход. pointerover/out всплывают, поэтому хватает двух
  // слушателей на весь документ, и новые кнопки подключаются сами.
  document.addEventListener('pointerover', (e) => { const el = near(e); if (el) showTipFor(el); });
  document.addEventListener('pointerout', (e) => { if (near(e)) hideHintTip(); });
  /* Клавиатура: фокус показывает, уход прячет. ⚠️ ТОЛЬКО фокус С КЛАВИАТУРЫ.

     Обычный `focus` приходит и от мыши, и ПРОГРАММНО: закрытие окна выбора
     само переводит фокус на кнопку возврата, и плашка всплывала при каждом
     входе в модель, а гасла только по следующему действию. Это та же п. 79,
     пришедшая с другой стороны.

     Псевдокласс `:focus-visible` тут не помощник: браузер считает
     программный фокус «видимым», пока страница не видела ни одного действия
     человека, — проверено, плашка всплывала и с ним. Поэтому клавиатуру
     отслеживаем сами: Tab и стрелки поднимают флаг, любое нажатие
     указателем его снимает. */
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' || e.key.indexOf('Arrow') === 0) _tipByKeyboard = true;
  }, true);
  document.addEventListener('pointerdown', () => { _tipByKeyboard = false; }, true);
  document.addEventListener('focusin', (e) => {
    const el = near(e);
    if (el && _tipByKeyboard) showTipFor(el);
  });
  document.addEventListener('focusout', (e) => { if (near(e)) hideHintTip(); });
  /* ⚠️ НАЖАТИЕ ГАСИТ ПОДСКАЗКУ. Ровно здесь была п. 79: после щелчка фокус
     остаётся на кнопке, и подпись, привязанная к фокусу, не уходила никогда.
     Человек уже нажал — объяснять ему нечего. */
  document.addEventListener('click', (e) => { if (near(e)) hideHintTip(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideHintTip(); });
  syncTipLabels();
}

/* п. 81. Один текст на подпись и на чтеца. Своего `aria-label` у кнопки с
   подсказкой нет: он собирается из того же `data-tip`, и разойтись им негде.
   Зовётся и после смены подписи (стрелки панелей меняют её на «Открыть» и
   «Закрыть»). */
function syncTipLabels() {
  document.querySelectorAll('[data-tip]').forEach(el => {
    const t = tipText(el);
    if (!t) return;
    const own = (el.textContent || '').trim();
    if (!own) el.setAttribute('aria-label', tipPlain(t));   // у кнопки-иконки своего текста нет
  });
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
  /* 2. Заголовок секции (обычный или складной).
     ⚠️ ИДЁМ ВВЕРХ, ПОКА ЗАГОЛОВОК НЕ НАЙДЁТСЯ, А НЕ ОСТАНАВЛИВАЕМСЯ НА ПЕРВОЙ
     СЕКЦИИ. Секции вложены друг в друга, и у внутренних заголовка часто нет
     НАМЕРЕННО (#sec-curves, #sec-mono). Прежний closest('.section') брал
     ближайшую, не находил у неё заголовка и сдавался — а подсказка при этом
     прекрасно относилась к заголовку карточки этажом выше. Так у монополии
     обе подсказки оставались без якоря и получали по пустой строке с «?». */
  let sec = hint.closest('.section');
  while (sec) {
    const fold = sec.querySelector(':scope > .fold-btn > span');
    if (fold) return fold;
    const title = sec.querySelector(':scope > .section-title');
    if (title) return title;
    sec = sec.parentElement ? sec.parentElement.closest('.section') : null;
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
  /* ⚠️ ПЯТОГО ШАГА БОЛЬШЕ НЕТ, И ЭТО НЕ УПУЩЕНИЕ.
     Здесь заводилась подсказке СВОЯ пустая строка `.help-anchor`, и ровно
     оттуда брались одинокие «?» посреди панели: вопросик появлялся там, где
     пояснять нечего — рядом с ним не было ни подписи, ни заголовка. Чаще
     всего это подсказки вложенной секции `#sec-curves`, у которой своего
     заголовка нет НАМЕРЕННО, поэтому шаг 2 (closest('.section')) до якоря не
     доходил. Замер 25.08: в «Спросе и предложении» два таких вопросика из
     трёх видимых, и живых подсказок у сцены при этом ноль.

     Вопросик появляется только рядом с тем, что он поясняет. Не нашлось
     подходящего якоря — подсказка остаётся обычным абзацем (hintsToDots на
     null просто ничего не делает), и это честнее пустой строки со знаком. */
  return null;
}

/* ⚠️ ВОПРОСИК ЖИВЁТ РОВНО СТОЛЬКО, СКОЛЬКО ЖИВА ЕГО ПОДСКАЗКА.
   Вопросик вешается на заголовок ОДИН РАЗ и остаётся на нём навсегда, а
   подсказки под ним у каждой модели свои. У общего заголовка (например, у
   карточки «Ввод функций») собираются подсказки нескольких моделей сразу, и
   после перехода в другую модель на видимом заголовке висел знак от чужих,
   уже спрятанных подсказок. Прячем знак, у которого не осталось ни одной
   живой подсказки; проход идёт после applyCardScope, иначе он не увидел бы
   `scoped-off` у переключателей соседних моделей. */
/* ⚠️ АНАЛИТИЧЕСКАЯ ЗАПИСЬ ОБЯЗАНА ПОМЕЩАТЬСЯ В ПАНЕЛЬ ПО ШИРИНЕ.
   Врезка `.sb-note` не умела ничего с широкой формулой: `\begin{cases}` KaTeX
   рисует одним неразрывным элементом, переносить его негде, и запись просто
   вылезала за правый край. Замер 25.08, «Сложение спросов» с четырьмя
   группами: содержимое 239 px во врезке шириной 215, панель 268.

   Прокрутку не заводим — горизонтальная полоса в тексте разбора читается как
   поломка, да и заметить её там некому. Подбираем кегль вниз, как это делает
   поле формулы, и с тем же уговором: нижний предел есть, и он 10 px. Ниже
   формулу в панели уже не прочесть, и честнее показать, что она не влезла,
   чем нарисовать нечитаемое. От основных 14,5 px это запас в треть — хватает
   на четыре участка с большим запасом.

   Меряем ВРЕЗКУ, а не формулу: у врезки есть своя ширина и своя прокрутка, а
   у формулы вокруг ещё и текст, который переносится сам. */
const PANEL_MATH_MIN_PX = 10;
function fitPanelMath(root) {
  root = root || document.getElementById('params-panel');
  if (!root) return;
  root.querySelectorAll('.sb-note').forEach(note => {
    const maths = [].slice.call(note.querySelectorAll('.katex'));
    if (!maths.length) return;
    maths.forEach(k => { k.style.fontSize = ''; });
    const have = note.clientWidth;
    if (!have || note.scrollWidth <= have + 1) return;
    const bases = maths.map(k => parseFloat(getComputedStyle(k).fontSize) || 14.5);
    /* ⚠️ ЦЕЛИМСЯ НА ПАРУ ПИКСЕЛЕЙ УЖЕ, ЧЕМ ВЛЕЗАЕТ. `scrollWidth` — целое, и
       округление скрывало недобор: замер показывал «215 в 215», а правый край
       формулы торчал за врезку на 1,8 px. Запас в два пикселя эту щель
       закрывает и на ответ не влияет. */
    let scale = 1;
    for (let step = 0; step < 8; step++) {
      const need = note.scrollWidth;
      if (need <= have - 1) break;
      scale = scale * (have - 2) / need;
      let atFloor = true;
      maths.forEach((k, i) => {
        const px = Math.max(PANEL_MATH_MIN_PX, bases[i] * scale);
        if (px > PANEL_MATH_MIN_PX) atFloor = false;
        k.style.fontSize = px + 'px';
      });
      if (atFloor) break;
    }
  });
}

function syncHintDots(root) {
  root = root || document.getElementById('tools-panel');
  if (!root) return;
  root.querySelectorAll('.help-dot').forEach(dot => {
    const hints = dot._hints || [];
    const live = hints.filter(h => h.isConnected && h.style.display !== 'none'
                                  && fieldActive(h.parentElement || h));
    dot.style.display = live.length ? '' : 'none';
  });
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
    /* «Точки на графике» и «Площади» открываются ПО НАВЕДЕНИЮ (решение
       владельца 21.08): подсказка нужна прямо в момент работы с холстом, и
       щелчок ради нового чтения каждый раз — лишний шаг. Метка на самой
       кнопке (data-pop-trigger), а не список секций: как и с манипуляторами
       сцены, список забудут дополнить у новой секции. Клик остаётся —
       для клавиатуры и сенсорного экрана наведения не бывает вовсе.
       Уход в саму плашку не должен её гасить, поэтому таймер общий у кнопки
       и плашки (тот же приём, что у значка закрепки ключевой точки). */
    if (btn.getAttribute('data-pop-trigger') === 'hover') {
      let leaveTimer = null;
      const openNow = () => {
        if (leaveTimer) { clearTimeout(leaveTimer); leaveTimer = null; }
        pop.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      };
      const closeSoon = () => {
        if (leaveTimer) clearTimeout(leaveTimer);
        leaveTimer = setTimeout(() => {
          leaveTimer = null;
          pop.classList.remove('open');
          btn.setAttribute('aria-expanded', 'false');
        }, 160);
      };
      btn.addEventListener('pointerenter', openNow);
      btn.addEventListener('pointerleave', closeSoon);
      pop.addEventListener('pointerenter', openNow);
      pop.addEventListener('pointerleave', closeSoon);
    }
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
  // П50 · Н31: три буквы А вместо числового поля. 10 · 14 · 18.
  LABEL_SIZES.forEach(([id, size]) => {
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


/* ── Печать (А58) ─────────────────────────────────────────────────────────
   Правил печати не было ни одного: Ctrl+P выводил страницу как есть, вместе
   с рейкой значков, обеими панелями и тёмным фоном. Стили печати оставляют на
   листе только график; здесь наполняем его шапку и подвал — название модели и
   ключевые значения, иначе лист выходит безымянным.

   Тёмная тема на бумаге не нужна: на время печати переключаемся на светлую и
   возвращаем как было. */
function fillPrintBlocks() {
  const title = document.getElementById('print-title');
  if (title) {
    title.textContent = STATE.graphTitle
      || SCENE_NAMES[STATE.sceneKey] || 'График';
  }
  const stats = document.getElementById('print-stats');
  if (!stats) return;
  stats.innerHTML = '';
  const src = document.getElementById('sb-body');
  if (!src) return;
  // Берём только строки со значениями: разбор на бумаге ни к чему.
  src.querySelectorAll('.stat').forEach(row => {
    const clone = row.cloneNode(true);
    stats.appendChild(clone);
  });
}

let _printTheme = null;
let _printViewBox = null;
/* П72. ⚠️ БЕЗ `viewBox` ПЕЧАТНЫЙ РАЗМЕР ХОЛСТА НЕ МАСШТАБИРУЕТ РИСУНОК.
   Печатный стиль задаёт `#chart` ширину 100 % и высоту 15 cm, но рисунок
   внутри SVG нарисован в пикселях экрана: без системы координат браузеру
   нечего пересчитывать, и он просто обрезает лишнее — картинка прижималась
   к левому верхнему углу, а ось количества уходила за нижний край листа.
   `viewBox` ставим перед печатью по фактическому размеру холста и снимаем
   после (П74): на экране он не нужен, а `preserveAspectRatio` при живом
   перетаскивании кривых сместил бы координаты указателя. */
function setPrintViewBox(on) {
  const svg = document.getElementById('chart');
  if (!svg) return;
  if (on) {
    if (_printViewBox === null) _printViewBox = svg.getAttribute('viewBox') || '';
    const w = svg.clientWidth || parseFloat(svg.getAttribute('width')) || 0;
    const h = svg.clientHeight || parseFloat(svg.getAttribute('height')) || 0;
    if (w > 0 && h > 0) {
      svg.setAttribute('viewBox', '0 0 ' + Math.round(w) + ' ' + Math.round(h));
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    }
    return;
  }
  if (_printViewBox === null) return;
  if (_printViewBox) svg.setAttribute('viewBox', _printViewBox);
  else svg.removeAttribute('viewBox');
  svg.removeAttribute('preserveAspectRatio');
  _printViewBox = null;
}

window.addEventListener('beforeprint', () => {
  fillPrintBlocks();
  setPrintViewBox(true);
  const root = document.documentElement;
  _printTheme = root.getAttribute('data-theme');
  if (_printTheme === 'dark') {
    root.setAttribute('data-theme', 'light');
    if (typeof redrawAll === 'function') redrawAll();
  }
});
window.addEventListener('afterprint', () => {
  const root = document.documentElement;
  if (_printTheme === 'dark') {
    root.setAttribute('data-theme', 'dark');
  }
  _printTheme = null;
  setPrintViewBox(false);
  /* П74. Холст возвращается к прежнему размеру ВСЕГДА, а не только после
     тёмной темы: печатный стиль растянул его на всю ширину листа, и без
     перерисовки на экране оставалась растянутая картинка.
     ⚠️ Перерисовка идёт СЛЕДУЮЩИМ КАДРОМ. В момент `afterprint` печатные
     правила уже сняты, но раскладка ещё не пересчитана: замер даёт ширину
     печатного листа, и холст перерисовывается по ней — то есть остаётся
     растянутым, только теперь по своей же вине. */
  if (typeof redrawAll === 'function') {
    requestAnimationFrame(() => requestAnimationFrame(() => redrawAll()));
  }
});
