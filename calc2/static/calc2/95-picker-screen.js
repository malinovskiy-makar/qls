// Экран выбора: вкладки блоков и сетка карточек с превью; переключатель модели.
/* ---------------------------------------------------------------------
   Решение владельца 09.10 (макет claude/mockups/calc2_picker_20261009/,
   ADR 0141; заменяет вид списка из фазы 8 редизайна 10.2026): сверху
   «Графики» и поиск, ряд «Продолжить · <когда>» и до трёх недавних, ряд
   вкладок из десяти блоков, под ним сетка карточек выбранного блока —
   превью, название, две строки описания; «скоро» — приглушённые карточки
   в конце блока.

   Карточки моделей НЕ создаются заново: это те же кнопки .scard из
   шаблона (их слушает 88-params.js, по ним открывают модели приборы).
   Меняются только раскладка и вид; превью — настоящие графики
   стандартного старта из previews.json (ниже, «Превью моделей»).
   --------------------------------------------------------------------- */

/* Порядок блоков (README макета 04.10, 4.4): по нему стоят вкладки экрана
   и колонки переключателя модели. */
const PICKER_COLUMNS = [
  ['Математика', 'КПВ и КТВ'],
  ['Совершенная конкуренция', 'Теория фирмы'],
  ['Несовершенная конкуренция', 'Рынок труда'],
  ['Международная торговля', 'Выбор потребителя'],
  ['Макроэкономика', 'Избранные сюжеты'],
];

function pkNorm(s) { return String(s || '').toLowerCase().replace(/ё/g, 'е'); }

/* Модели экрана выбора: имя, описание, блок, карточка. */
function pickerModels() {
  return [...document.querySelectorAll('#scene-picker .scard')].map(c => ({
    card: c, key: c.dataset.scene || '', soon: c.classList.contains('soon') || c.disabled,
    name: ((c.querySelector('.scard-name') || {}).textContent || '').trim(),
    desc: ((c.querySelector('.scard-desc') || {}).textContent || '').trim(),
    block: ((c.closest('.picker-group') || {}).getAttribute ? c.closest('.picker-group').getAttribute('aria-label') : '') || '',
  }));
}

/* Поиск (README макета, 4.2): каждое слово обязано найтись; очки за слово —
   начало имени 10, начало слова в имени 8, внутри имени 6, описание 3, имя
   блока 2; у «скоро» −5. Ключевых слов у карточек сайта нет. */
function pickerScore(m, words) {
  const name = pkNorm(m.name), desc = pkNorm(m.desc), block = pkNorm(m.block);
  let score = 0;
  for (const w of words) {
    let s = 0;
    if (name.startsWith(w)) s = 10;
    else if (new RegExp('(^|[\\s(«-])' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(name)) s = 8;
    else if (name.includes(w)) s = 6;
    else if (desc.includes(w)) s = 3;
    else if (block.includes(w)) s = 2;
    if (!s) return 0;
    score += s;
  }
  return score - (m.soon ? 5 : 0);
}

function whenText(t) {
  if (!t) return '';
  const d = (Date.now() - t) / 1000;
  if (d < 90) return 'только что';
  if (d < 3600) return Math.round(d / 60) + ' мин назад';
  if (d < 86400) return Math.round(d / 3600) + ' ч назад';
  const days = Math.round(d / 86400);
  return days === 1 ? 'вчера' : days + ' ' + plural(days, ['день', 'дня', 'дней']) + ' назад';
}

function buildPickerScreen() {
  const p = document.getElementById('scene-picker');
  const inner = p && p.querySelector('.picker-inner');
  if (!inner || inner._screen) return;
  inner._screen = true;
  p.classList.add('pk-screen');

  // Шапка: «Графики» слева, поиск справа (строки про число моделей нет).
  const head = inner.querySelector('.picker-head');
  if (head) {
    const t = head.querySelector('.picker-title'); if (t) t.textContent = 'Графики';
    head.querySelectorAll('.picker-sub').forEach(x => x.remove());
    const search = document.createElement('div');
    search.className = 'pk-search';
    search.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>'
      + '<input type="search" id="picker-search" autocomplete="off" placeholder="Найти модель: налог, КПВ, монополия…" aria-label="Найти модель">'
      + '<button type="button" class="pk-clear" id="picker-clear" aria-label="Очистить поиск" hidden>×</button>';
    head.appendChild(search);
  }

  // Ряд «Продолжить» и недавних, вкладки блоков, строка найденного.
  const cont = document.createElement('div');
  cont.className = 'pk-cont'; cont.id = 'picker-cont';
  const tabs = document.createElement('div');
  tabs.className = 'pk-tabs'; tabs.id = 'picker-tabs';
  tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Блоки моделей');
  const found = document.createElement('div');
  found.className = 'pk-found'; found.id = 'picker-found'; found.hidden = true;
  const none = document.createElement('div');
  none.className = 'pk-none'; none.id = 'picker-none'; none.hidden = true;
  none.innerHTML = '<div class="pk-none-title">Такой модели нет</div><p>Поиск идёт по названиям, описаниям и словам из олимпиадных условий. Попробуйте «налог», «эластичность», «монополия» или «КПВ».</p>';

  // Блоки — панели вкладок в порядке PICKER_COLUMNS (сверху вниз, слева направо).
  const panels = document.createElement('div');
  panels.className = 'pk-panels'; panels.id = 'picker-panels';
  const groups = [...inner.querySelectorAll('.picker-group')];
  const order = PICKER_COLUMNS.flat();
  const rank = (g) => { const i = order.indexOf(g.getAttribute('aria-label') || ''); return i < 0 ? order.length : i; };
  groups.slice().sort((a, b) => rank(a) - rank(b)).forEach((g, i) => {
    const name = g.getAttribute('aria-label') || '';
    g.classList.add('pk-block');
    g.classList.remove('open');
    // Подпись блока теперь на вкладке: прежние заголовки (из шаблона и из
    // лестницы foldPickerGroups) убираем.
    g.querySelectorAll(':scope > .picker-group-label, :scope > .picker-group-open-name').forEach(x => x.remove());
    if (!g.id) g.id = 'pk-block-' + i;
    const grid = g.querySelector(':scope > .picker-grid');
    if (grid) grid.classList.add('open', 'pk-cards');
    const cards = grid ? [...grid.querySelectorAll('.scard')] : [];
    // «Скоро» — в конце блока (лестница их уже переставила, повторяем на случай без неё).
    cards.filter(c => c.classList.contains('soon') || c.disabled).forEach(c => grid.appendChild(c));
    cards.forEach(c => {
      const soon = c.classList.contains('soon') || c.disabled;
      if (!c.querySelector(':scope > .pk-well')) {
        const well = document.createElement('span');
        well.className = 'pk-well' + (soon ? ' pk-well-soon' : '');
        well.setAttribute('aria-hidden', 'true');
        if (soon) well.innerHTML = '<span class="pk-pill">скоро</span>';
        c.insertBefore(well, c.firstChild);
      }
      // Имя блока над названием: видно только во время поиска.
      const blk = document.createElement('span');
      blk.className = 'pk-cblock'; blk.textContent = name;
      const nameHost = c.querySelector(':scope > .scard-head') || c.querySelector(':scope > .scard-name');
      if (nameHost) c.insertBefore(blk, nameHost);
    });
    const n = cards.filter(c => !(c.classList.contains('soon') || c.disabled)).length;
    const tab = document.createElement('button');
    tab.type = 'button'; tab.className = 'pk-tab'; tab.id = 'pk-tab-' + i;
    tab.setAttribute('role', 'tab'); tab.setAttribute('aria-selected', 'false');
    tab.setAttribute('aria-controls', g.id); tab.tabIndex = -1;
    tab.dataset.block = name;
    const a = document.createElement('span'); a.className = 'pk-tname'; a.textContent = name;
    const b = document.createElement('span'); b.className = 'pk-tcount'; b.textContent = String(n);
    tab.append(a, b);
    tab.addEventListener('click', () => selectPickerTab(name, true));
    tabs.appendChild(tab);
    g.setAttribute('role', 'tabpanel'); g.setAttribute('aria-labelledby', tab.id);
    panels.appendChild(g);
  });
  // Клавиатура вкладок: стрелки и Home/End переходят и сразу открывают блок.
  tabs.addEventListener('keydown', (e) => {
    const list = [...tabs.querySelectorAll('.pk-tab')];
    const i = list.indexOf(document.activeElement);
    if (i < 0) return;
    let j = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') j = (i + 1) % list.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') j = (i - 1 + list.length) % list.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = list.length - 1;
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectPickerTab(list[i].dataset.block, true); return; }
    if (j < 0) return;
    e.preventDefault();
    selectPickerTab(list[j].dataset.block, true);
    list[j].focus();
  });

  const anchor = inner.querySelector('#picker-blocks') || inner.querySelector('.picker-group') || null;
  [cont, tabs, found, none, panels].forEach(x => inner.insertBefore(x, anchor && anchor.parentNode === inner ? anchor : null));
  ['picker-blocks', 'picker-back'].forEach(id => { const e = document.getElementById(id); if (e) e.remove(); });

  // Поиск.
  const inp = document.getElementById('picker-search');
  const clr = document.getElementById('picker-clear');
  if (inp) {
    inp.addEventListener('input', () => pickerFilter(inp.value));
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const first = panels.querySelector('.scard.pk-first');
        if (first) { e.preventDefault(); first.click(); }
      }
    });
  }
  if (clr) clr.addEventListener('click', () => { inp.value = ''; pickerFilter(''); inp.focus(); });

  selectPickerTab(pickerDefaultTab(), false);
  loadPickerPreviews(p.dataset.previews);
}

/* ── Вкладки блоков ─────────────────────────────────────────────────────
   Видимый блок — панель с классом .open (тот же класс открывают приборы,
   которым нужна карточка чужого блока). Последняя выбранная вкладка
   помнится в хранилище калькулятора (storeGet / storeSet, 91-session.js:
   обёрнуты в try/catch; resetSceneMemory приборов её стирает). */
function selectPickerTab(name, remember) {
  const tabs = [...document.querySelectorAll('#picker-tabs .pk-tab')];
  if (!tabs.length) return;
  if (!tabs.some(t => t.dataset.block === name)) name = tabs[0].dataset.block;
  tabs.forEach(t => {
    const on = t.dataset.block === name;
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll('#scene-picker .pk-block').forEach(g => g.classList.toggle('open', (g.getAttribute('aria-label') || '') === name));
  if (remember && typeof storeSet === 'function') storeSet('pickerTab', name);
}
function pickerSelectedTab() {
  const t = document.querySelector('#picker-tabs .pk-tab[aria-selected="true"]');
  return t ? t.dataset.block : '';
}
/* Какая вкладка открыта при входе на экран: из модели («Все модели») —
   блок этой модели; иначе последняя выбранная; иначе блок модели из
   «Продолжить»; без истории — «Математика». */
function pickerDefaultTab() {
  const blockOf = (k) => { const m = pickerModels().find(x => x.key === k); return m ? m.block : ''; };
  if (STATE.sceneKey) { const b = blockOf(modelKeyOf(STATE.sceneKey)); if (b) return b; }
  const saved = (typeof storeGet === 'function') ? storeGet('pickerTab') : null;
  if (saved && PICKER_COLUMNS.flat().includes(saved)) return saved;
  const rec = (typeof recentModels === 'function') ? recentModels() : [];
  if (rec[0]) { const b = blockOf(rec[0].k); if (b) return b; }
  return 'Математика';
}
// Зовёт openPicker (84-picker.js) при каждом входе на экран.
function pickerOpenTab() {
  const q = document.getElementById('picker-search');
  if (q && q.value) return;          // запрос остаётся — вкладки под ним не трогаем
  selectPickerTab(pickerDefaultTab(), false);
}

/* ── Превью моделей (ADR 0141) ──────────────────────────────────────────
   previews.json собирает заранее calc2/tests/previews/make_previews.mjs из
   записи при рисовании стандартного старта: кривые и закраски без чисел и
   подписей, цвета — ИМЕНАМИ токенов холста. Картинка вставляется встроенным
   SVG: через <img> переменные темы не работают, а так превью само
   перекрашивается при смене темы. Стили — через CSSOM (style.setProperty):
   атрибут style строкой мог бы упереться в политику безопасности. */
let _pkPreviews = null;
function loadPickerPreviews(url) {
  if (!url || _pkPreviews || typeof fetch !== 'function') return;
  fetch(url, { credentials: 'same-origin' })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { if (!j) return; _pkPreviews = j; fillPickerWells(); renderPickerContinue(); })
    .catch(() => { /* без превью экран остаётся рабочим: пустые колодцы */ });
}
const PK_SVGNS = 'http://www.w3.org/2000/svg';
function pickerPreviewSvg(key) {
  const pv = _pkPreviews && _pkPreviews[key];
  if (!pv) return null;
  const svg = document.createElementNS(PK_SVGNS, 'svg');
  svg.setAttribute('viewBox', pv.vb);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.setAttribute('class', 'pk-pv');
  svg.dataset.model = key;
  pv.p.forEach(q => {
    const el = document.createElementNS(PK_SVGNS, 'path');
    el.setAttribute('d', q.d);
    // толщина в пикселях экрана при любом размере превью
    el.setAttribute('vector-effect', 'non-scaling-stroke');
    const s = el.style;
    if (q.f) { s.setProperty('fill', 'var(--' + q.f + ')'); s.setProperty('fill-opacity', String(q.fo)); }
    else s.setProperty('fill', 'none');
    if (q.s) {
      s.setProperty('stroke', 'var(--' + q.s + ')');
      s.setProperty('stroke-width', q.w + 'px');
      if (q.o != null) s.setProperty('stroke-opacity', String(q.o));
      if (q.da) s.setProperty('stroke-dasharray', q.da);
    } else s.setProperty('stroke', 'none');
    svg.appendChild(el);
  });
  return svg;
}
function fillPickerWells() {
  document.querySelectorAll('#scene-picker .scard:not(.soon):not([disabled]) > .pk-well').forEach(w => {
    if (w.querySelector('svg')) return;
    const svg = pickerPreviewSvg(w.parentNode.dataset.scene);
    if (svg) w.appendChild(svg);
  });
}

/* Отбор по запросу: вкладки прячутся, сетка показывает находки из всех
   блоков подряд (у каждой над названием имя блока), лучшие вперёд;
   совпавший кусок имени выделен; первая рабочая находка подсвечена и
   открывается по Enter. Очистка возвращает вкладки и прежний блок. */
function pickerFilter(q) {
  const words = pkNorm(q).split(/\s+/).filter(Boolean);
  const clr = document.getElementById('picker-clear'); if (clr) clr.hidden = !words.length;
  const cont = document.getElementById('picker-cont');
  const tabs = document.getElementById('picker-tabs');
  const found = document.getElementById('picker-found');
  const none = document.getElementById('picker-none');
  const panels = document.getElementById('picker-panels');
  const models = pickerModels();
  models.forEach(m => {
    const nm = m.card.querySelector('.scard-name');
    if (nm) nm.textContent = m.name;
    m.card.classList.remove('pk-first', 'pk-hit', 'pk-miss');
    m.card.style.removeProperty('order');
  });
  if (panels) panels.classList.toggle('pk-searching', !!words.length);
  if (!words.length) {
    if (cont) cont.hidden = !cont.childElementCount;
    if (tabs) tabs.hidden = false;
    if (found) found.hidden = true;
    if (none) none.hidden = true;
    if (panels) panels.hidden = false;
    selectPickerTab(pickerSelectedTab(), false);
    return;
  }
  if (cont) cont.hidden = true;
  if (tabs) tabs.hidden = true;
  const hits = models.map((m, i) => ({ m, i, s: pickerScore(m, words) })).filter(x => x.s > 0);
  const hitSet = new Set(hits.map(x => x.m.card));
  models.forEach(m => m.card.classList.add(hitSet.has(m.card) ? 'pk-hit' : 'pk-miss'));
  // Порядок в сетке: рабочие по очкам, «скоро» следом; при равенстве — как в блоках.
  hits.slice().sort((a, b) => (a.m.soon - b.m.soon) || (b.s - a.s) || (a.i - b.i))
    .forEach((x, k) => x.m.card.style.setProperty('order', String(k)));
  // Совпавший кусок имени — 600 --accent-ink.
  hits.forEach(({ m }) => {
    const nm = m.card.querySelector('.scard-name');
    if (!nm) return;
    const low = pkNorm(m.name);
    const w = words.find(x => low.includes(x));
    if (!w) return;
    const i = low.indexOf(w);
    nm.innerHTML = '';
    nm.append(document.createTextNode(m.name.slice(0, i)));
    const b = document.createElement('mark'); b.className = 'pk-mark'; b.textContent = m.name.slice(i, i + w.length);
    nm.append(b, document.createTextNode(m.name.slice(i + w.length)));
  });
  const working = hits.filter(x => !x.m.soon).sort((a, b) => (b.s - a.s) || (a.i - b.i));
  if (working[0]) working[0].m.card.classList.add('pk-first');
  const n = working.length;
  if (found) {
    found.hidden = !n;
    found.innerHTML = '';
    if (n) {
      const a = document.createElement('span'); a.textContent = 'Нашлось ' + n + ' ' + plural(n, ['модель', 'модели', 'моделей']);
      const chip = document.createElement('span'); chip.className = 'pk-enter'; chip.textContent = 'Enter откроет «' + working[0].m.name + '»';
      found.append(a, chip);
    }
  }
  if (none) none.hidden = !!n;
  if (panels) panels.hidden = !n;
}

/* «Продолжить» и недавние — один ряд карточек (решение 09.10): большая
   «Продолжить · <когда>» с превью и кнопкой, рядом до трёх недавних моделей
   с превью и временем. Только без запроса; нет истории — ряда нет вовсе.
   Щелчок открывает модель с её состоянием (openModelByUser). */
function renderPickerContinue() {
  const cont = document.getElementById('picker-cont');
  if (!cont) return;
  cont.innerHTML = '';
  const rec = (typeof recentModels === 'function') ? recentModels() : [];
  const models = pickerModels();
  const nameOf = (k) => { const m = models.find(x => x.key === k); return m ? m.name : (SCENE_NAMES[k] || k); };
  const open = (k) => (typeof openModelByUser === 'function' ? openModelByUser : pickScene)(k);
  const thumb = (k) => {
    const t = document.createElement('span'); t.className = 'pk-thumb'; t.setAttribute('aria-hidden', 'true');
    const svg = pickerPreviewSvg(k); if (svg) t.appendChild(svg);
    return t;
  };
  const first = STATE.sceneKey ? { k: modelKeyOf(STATE.sceneKey), t: Date.now() } : rec[0];
  if (first && SCENE_ROUTE[first.k]) {
    const card = document.createElement('button');
    card.type = 'button'; card.className = 'pk-ccard pk-continue'; card.id = 'picker-continue';
    const txt = document.createElement('span'); txt.className = 'pk-ctext';
    const when = document.createElement('span'); when.className = 'pk-when';
    when.textContent = 'Продолжить · ' + whenText(first.t || Date.now());
    const nm = document.createElement('span'); nm.className = 'pk-cname'; nm.textContent = nameOf(first.k);
    txt.append(when, nm);
    const go = document.createElement('span'); go.className = 'pk-go'; go.textContent = 'Продолжить →';
    card.append(thumb(first.k), txt, go);
    card.addEventListener('click', () => open(first.k));
    cont.appendChild(card);
  }
  const recent = rec.filter(x => !first || x.k !== first.k).slice(0, 3);
  if (recent.length) {
    const box = document.createElement('div'); box.className = 'pk-recents';
    recent.forEach(x => {
      const c = document.createElement('button'); c.type = 'button'; c.className = 'pk-ccard pk-recent';
      c.dataset.scene = x.k;
      const txt = document.createElement('span'); txt.className = 'pk-ctext';
      const w = document.createElement('span'); w.className = 'pk-when'; w.textContent = whenText(x.t);
      const nm = document.createElement('span'); nm.className = 'pk-cname'; nm.textContent = nameOf(x.k);
      txt.append(w, nm);
      c.append(thumb(x.k), txt);
      c.addEventListener('click', () => open(x.k));
      box.appendChild(c);
    });
    cont.appendChild(box);
  }
  const q = document.getElementById('picker-search');
  cont.hidden = !cont.childElementCount || !!(q && q.value.trim());
}

/* ── Переключатель модели (README макета, раздел 10) ───────────────────────
   Окно 660 под шапкой модели: поиск и 10 блоков в две колонки; текущая
   модель отмечена, модель с сохранённым состоянием — точкой. «Все модели на
   одном экране →» открывает экран выбора. */
function buildSwitcher() {
  const pop = document.getElementById('switch-pop');
  if (!pop || pop._built) return;
  pop._built = true;
  pop.innerHTML = '';
  const s = document.createElement('div'); s.className = 'pk-search sw-search';
  s.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>'
    + '<input type="search" id="switch-search" autocomplete="off" placeholder="Модель по названию или слову из условия" aria-label="Найти модель">';
  const body = document.createElement('div'); body.className = 'sw-cols'; body.id = 'switch-cols';
  const foot = document.createElement('div'); foot.className = 'sw-foot';
  foot.innerHTML = '<span class="sw-saved"><i class="sw-dot"></i>ваши настройки сохранены: вернётесь, и всё будет на месте</span>';
  const all = document.createElement('button'); all.type = 'button'; all.className = 'sw-all'; all.id = 'switch-all';
  all.textContent = 'Все модели на одном экране →';
  all.addEventListener('click', () => { closePop(); openPicker(); });
  foot.appendChild(all);
  pop.append(s, body, foot);
  const inp = s.querySelector('input');
  inp.addEventListener('input', () => renderSwitcher(inp.value));
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { const f = body.querySelector('.sw-row.sw-first'); if (f) { e.preventDefault(); f.click(); } }
  });
}
function renderSwitcher(q) {
  const body = document.getElementById('switch-cols');
  if (!body) return;
  const words = pkNorm(q).split(/\s+/).filter(Boolean);
  body.innerHTML = '';
  const models = pickerModels();
  const cur = STATE.sceneKey ? modelKeyOf(STATE.sceneKey) : '';
  let first = null;
  PICKER_COLUMNS.flat().forEach(block => {
    const list = models.filter(m => m.block === block && (!words.length || pickerScore(m, words) > 0));
    if (!list.length) return;
    const g = document.createElement('div'); g.className = 'sw-block';
    const h = document.createElement('div'); h.className = 'sw-bname'; h.textContent = block;
    g.appendChild(h);
    list.filter(m => !m.soon).forEach(m => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'sw-row';
      b.dataset.scene = m.key;
      if (m.key === cur) b.classList.add('is-current');
      const t = document.createElement('span'); t.textContent = m.name;
      b.appendChild(t);
      if (typeof savedModel === 'function' && savedModel(m.key)) {
        const d = document.createElement('i'); d.className = 'sw-dot'; d.setAttribute('data-tip', 'Здесь сохранены ваши настройки');
        b.appendChild(d);
      }
      if (!first && words.length) { first = b; b.classList.add('sw-first'); }
      b.addEventListener('click', () => { closePop(); (typeof openModelByUser === 'function' ? openModelByUser : pickScene)(m.key); });
      g.appendChild(b);
    });
    const soon = list.filter(m => m.soon);
    if (soon.length) {
      const line = document.createElement('div'); line.className = 'pk-soon';
      line.innerHTML = '<span class="pk-pill">скоро</span> ';
      const n = document.createElement('span'); n.className = 'pk-soon-names'; n.textContent = soon.map(m => m.name).join(' · ');
      line.appendChild(n); g.appendChild(line);
    }
    body.appendChild(g);
  });
}
function openSwitcher(anchor) {
  buildSwitcher();
  const pop = document.getElementById('switch-pop');
  if (!pop) return;
  const inp = document.getElementById('switch-search');
  if (inp) inp.value = '';
  renderSwitcher('');
  const head = document.getElementById('model-head');
  const top = head ? head.getBoundingClientRect().bottom - 2 : undefined;
  openPop(anchor, pop, { top, noFocus: true });
  if (inp) inp.focus({ preventScroll: true });
}
