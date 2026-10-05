// Экран выбора одним экраном и переключатель модели (редизайн 10.2026, фаза 8).
/* ---------------------------------------------------------------------
   README макета, разделы 4 и 10. Прежнее окно выбора было двухуровневым:
   десять карточек блоков, щелчок — сетка моделей блока (пункт (г)
   закрытого списка). Теперь все блоки на одном экране, в пяти колонках;
   над ними поиск, «Продолжить» и «Недавние».

   Карточки моделей НЕ создаются заново: это те же кнопки .scard из
   шаблона (их слушает 88-params.js, по ним открывают модели приборы).
   Меняются только раскладка и вид: строка — имя модели; схема и описание
   уходят в превью при наведении и фокусе. Запланированные модели («скоро»)
   — одной приглушённой строкой в конце блока.
   --------------------------------------------------------------------- */

/* Блоки в колонках: [первый, второй] сверху вниз (README макета, 4.4). */
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

  // Шапка: «Графики», строка про модели, справа поиск.
  const head = inner.querySelector('.picker-head');
  const working = pickerModels().filter(m => !m.soon).length;
  if (head) {
    const t = head.querySelector('.picker-title'); if (t) t.textContent = 'Графики';
    const sub = head.querySelector('.picker-sub');
    if (sub) sub.textContent = working + ' ' + plural(working, ['модель', 'модели', 'моделей'])
      + ' олимпиадной экономики. Меняете функции, и график с ответом сразу пересчитываются.';
    const search = document.createElement('div');
    search.className = 'pk-search';
    search.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>'
      + '<input type="search" id="picker-search" autocomplete="off" placeholder="Найти модель: налог, КПВ, монополия…" aria-label="Найти модель">'
      + '<button type="button" class="pk-clear" id="picker-clear" aria-label="Очистить поиск" hidden>×</button>';
    const left = document.createElement('div');
    left.className = 'pk-headtext';
    while (head.firstChild) left.appendChild(head.firstChild);
    head.append(left, search);
  }

  // «Продолжить» и «Недавние», строка найденного.
  const cont = document.createElement('div');
  cont.className = 'pk-cont'; cont.id = 'picker-cont';
  const found = document.createElement('div');
  found.className = 'pk-found'; found.id = 'picker-found'; found.hidden = true;
  const none = document.createElement('div');
  none.className = 'pk-none'; none.id = 'picker-none'; none.hidden = true;
  none.innerHTML = '<div class="pk-none-title">Такой модели нет</div><p>Поиск идёт по названиям, описаниям и словам из олимпиадных условий. Попробуйте «налог», «эластичность», «монополия» или «КПВ».</p>';

  // Пять колонок по два блока.
  const cols = document.createElement('div');
  cols.className = 'pk-cols'; cols.id = 'picker-cols';
  const groups = [...inner.querySelectorAll('.picker-group')];
  const byName = new Map(groups.map(g => [g.getAttribute('aria-label') || '', g]));
  PICKER_COLUMNS.forEach(names => {
    const col = document.createElement('div');
    col.className = 'pk-col';
    names.forEach(n => {
      const g = byName.get(n);
      if (!g) return;
      byName.delete(n);
      col.appendChild(g);
    });
    cols.appendChild(col);
  });
  // Блок, которого нет в раскладке (появится новый) — в последнюю колонку.
  byName.forEach(g => cols.lastChild.appendChild(g));

  groups.forEach((g, i) => {
    g.classList.add('open', 'pk-block');
    // Подпись блока: прежняя лестница (foldPickerGroups) её снимает и ставит
    // свою «открытую» — берём имя из aria-label и собираем заголовок заново.
    g.querySelectorAll(':scope > .picker-group-open-name').forEach(x => x.remove());
    let lab = g.querySelector(':scope > .picker-group-label');
    if (!lab) {
      lab = document.createElement('div');
      lab.className = 'picker-group-label';
      lab.textContent = g.getAttribute('aria-label') || '';
      g.insertBefore(lab, g.firstChild);
    }
    const grid = g.querySelector(':scope > .picker-grid');
    if (grid && !grid.id) grid.id = 'pgrid-' + i;
    if (grid) grid.classList.add('open', 'pk-list');
    const n = grid ? grid.querySelectorAll('.scard:not(.soon):not([disabled])').length : 0;
    if (lab) {
      lab.classList.add('pk-head');
      const name = lab.textContent.trim();
      lab.innerHTML = '';
      const a = document.createElement('span'); a.className = 'pk-bname'; a.textContent = name;
      const b = document.createElement('span'); b.className = 'pk-bcount'; b.textContent = String(n);
      lab.append(a, b);
    }
    // «Скоро» — одной приглушённой строкой в конце блока.
    const soon = grid ? [...grid.querySelectorAll('.scard.soon, .scard[disabled]')] : [];
    if (soon.length) {
      const line = document.createElement('div');
      line.className = 'pk-soon';
      line.innerHTML = '<span class="pk-pill">скоро</span> ';
      const names = document.createElement('span');
      names.className = 'pk-soon-names';
      names.textContent = soon.map(c => ((c.querySelector('.scard-name') || {}).textContent || '').trim()).join(' · ');
      line.appendChild(names);
      soon.forEach(c => { c.classList.add('pk-soon-card'); });
      g.appendChild(line);
    }
    grid && grid.querySelectorAll('.scard').forEach(c => c.classList.add('pk-row'));
  });

  const firstGroup = groups[0];
  const anchor = inner.querySelector('#picker-blocks') || firstGroup;
  inner.insertBefore(cont, anchor);
  inner.insertBefore(found, anchor);
  inner.insertBefore(none, anchor);
  inner.insertBefore(cols, anchor);
  ['picker-blocks', 'picker-back'].forEach(id => { const e = document.getElementById(id); if (e) e.remove(); });

  // Превью при наведении и фокусе на строке.
  const pv = document.createElement('div');
  pv.className = 'pk-preview'; pv.id = 'picker-preview';
  pv.setAttribute('role', 'tooltip'); pv.hidden = true;
  p.appendChild(pv);
  const showPv = (card) => {
    const m = pickerModels().find(x => x.card === card);
    if (!m || m.soon) { pv.hidden = true; return; }
    pv.innerHTML = '';
    const spec = card.querySelector('.scard-spec');
    if (spec) { const s = spec.cloneNode(true); s.className = 'pk-pv-spec'; pv.appendChild(s); }
    const b = document.createElement('div'); b.className = 'pk-pv-block'; b.textContent = m.block;
    const n = document.createElement('div'); n.className = 'pk-pv-name'; n.textContent = m.name;
    const d = document.createElement('div'); d.className = 'pk-pv-desc'; d.textContent = m.desc;
    pv.append(b, n, d);
    pv.hidden = false;
    const r = card.getBoundingClientRect();
    const colIdx = [...cols.children].indexOf(card.closest('.pk-col'));
    let left = colIdx >= 3 ? r.left - 314 : r.right + 14;
    left = Math.max(8, Math.min(left, window.innerWidth - pv.offsetWidth - 8));
    let top = Math.max(8, Math.min(r.top - 28, window.innerHeight - pv.offsetHeight - 8));
    pv.style.left = left + 'px'; pv.style.top = top + 'px';
  };
  const hidePv = () => { pv.hidden = true; };
  cols.addEventListener('pointerover', (e) => { const c = e.target.closest('.scard.pk-row'); if (c) showPv(c); });
  cols.addEventListener('pointerout', (e) => { const c = e.target.closest('.scard.pk-row'); if (c && !c.contains(e.relatedTarget)) hidePv(); });
  cols.addEventListener('focusin', (e) => { const c = e.target.closest('.scard.pk-row'); if (c) showPv(c); });
  cols.addEventListener('focusout', hidePv);
  p.addEventListener('scroll', hidePv, true);

  // Поиск.
  const inp = document.getElementById('picker-search');
  const clr = document.getElementById('picker-clear');
  if (inp) {
    inp.addEventListener('input', () => pickerFilter(inp.value));
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const first = cols.querySelector('.scard.pk-first');
        if (first) { e.preventDefault(); first.click(); }
      }
    });
  }
  if (clr) clr.addEventListener('click', () => { inp.value = ''; pickerFilter(''); inp.focus(); });
}

/* Отбор по запросу: в блоке только найденные строки, блоки с находками
   встают подряд; совпавший кусок имени выделен; первая рабочая находка
   подсвечена и открывается по Enter. */
function pickerFilter(q) {
  const words = pkNorm(q).split(/\s+/).filter(Boolean);
  const clr = document.getElementById('picker-clear'); if (clr) clr.hidden = !words.length;
  const cont = document.getElementById('picker-cont');
  const found = document.getElementById('picker-found');
  const none = document.getElementById('picker-none');
  const cols = document.getElementById('picker-cols');
  const models = pickerModels();
  models.forEach(m => {
    const nm = m.card.querySelector('.scard-name');
    if (nm) nm.textContent = m.name;
    m.card.classList.remove('pk-first', 'pk-hit', 'pk-miss');
  });
  document.querySelectorAll('#scene-picker .pk-block').forEach(g => g.classList.remove('pk-miss'));
  if (cols) cols.classList.toggle('pk-searching', !!words.length);
  if (!words.length) {
    if (cont) cont.hidden = !cont.childElementCount;
    if (found) found.hidden = true;
    if (none) none.hidden = true;
    if (cols) cols.hidden = false;
    return;
  }
  if (cont) cont.hidden = true;
  const hits = models.map(m => ({ m, s: pickerScore(m, words) })).filter(x => x.s > 0);
  const hitSet = new Set(hits.map(x => x.m.card));
  models.forEach(m => m.card.classList.toggle(hitSet.has(m.card) ? 'pk-hit' : 'pk-miss', true));
  document.querySelectorAll('#scene-picker .pk-block').forEach(g => {
    const any = [...g.querySelectorAll('.scard')].some(c => hitSet.has(c));
    g.classList.toggle('pk-miss', !any);
    const soon = g.querySelector('.pk-soon');
    if (soon) soon.hidden = ![...g.querySelectorAll('.scard.pk-soon-card')].some(c => hitSet.has(c));
  });
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
  const working = hits.filter(x => !x.m.soon).sort((a, b) => b.s - a.s);
  if (working[0]) working[0].m.card.classList.add('pk-first');
  const n = hits.filter(x => !x.m.soon).length;
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
  if (cols) cols.hidden = !n;
}

/* «Продолжить» и «Недавние» (README макета, 4.3): только без запроса, нет
   сохранённых моделей — ряда нет. Щелчок открывает модель с её состоянием. */
function renderPickerContinue() {
  const cont = document.getElementById('picker-cont');
  if (!cont) return;
  cont.innerHTML = '';
  const rec = (typeof recentModels === 'function') ? recentModels() : [];
  const models = pickerModels();
  const nameOf = (k) => { const m = models.find(x => x.key === k); return m ? m.name : (SCENE_NAMES[k] || k); };
  const open = (k) => (typeof openModelByUser === 'function' ? openModelByUser : pickScene)(k);
  const first = STATE.sceneKey ? { k: modelKeyOf(STATE.sceneKey), t: Date.now() } : rec[0];
  if (first && SCENE_ROUTE[first.k]) {
    const card = document.createElement('button');
    card.type = 'button'; card.className = 'pk-continue'; card.id = 'picker-continue';
    const m = models.find(x => x.key === first.k);
    const spec = m && m.card.querySelector('.scard-spec');
    const mini = document.createElement('span'); mini.className = 'pk-mini';
    if (spec) mini.appendChild(spec.cloneNode(true));
    const txt = document.createElement('span'); txt.className = 'pk-ctext';
    const when = document.createElement('span'); when.className = 'pk-when';
    when.textContent = 'Продолжить с того места' + (first.t ? ' · ' + whenText(first.t) : '');
    const nm = document.createElement('span'); nm.className = 'pk-cname'; nm.textContent = nameOf(first.k);
    txt.append(when, nm);
    const go = document.createElement('span'); go.className = 'pk-go'; go.textContent = 'Продолжить →';
    card.append(mini, txt, go);
    card.addEventListener('click', () => open(first.k));
    cont.appendChild(card);
  }
  const chips = rec.filter(x => !first || x.k !== first.k).slice(0, 3);
  if (chips.length) {
    const box = document.createElement('div'); box.className = 'pk-recent';
    const lab = document.createElement('span'); lab.className = 'pk-recent-lab'; lab.textContent = 'Недавние';
    box.appendChild(lab);
    chips.forEach(x => {
      const c = document.createElement('button'); c.type = 'button'; c.className = 'pk-chip';
      const a = document.createElement('span'); a.textContent = nameOf(x.k);
      const b = document.createElement('span'); b.className = 'pk-chip-when'; b.textContent = whenText(x.t);
      c.append(a, b);
      c.addEventListener('click', () => open(x.k));
      box.appendChild(c);
    });
    cont.appendChild(box);
  }
  cont.hidden = !cont.childElementCount;
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
