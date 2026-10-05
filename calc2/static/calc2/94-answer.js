// «Ответ»: представление поверх табло (редизайн 10.2026, фаза 6).
/* ---------------------------------------------------------------------
   Сцены по-прежнему пишут свои блоки #info-* (и #sec-eq) в табло #sb-body:
   этим живут печать, «Объяснение модели», ?texState=1 и десятки проверок.
   «Ответ» собирается ПОВЕРХ них и только читает:
     · статус словами — предупреждения сцены (.warn) строкой над числами;
     · главные числа 2×2 — выбранные строки табло (HERO ниже); у ячейки
       «было · Δ» из таблицы «До / После / Δ» той же модели;
     · дальше прежние блоки как группы с заголовками; строка, ставшая главным
       числом, в группе не повторяется (класс .is-hero);
     · «Разбор» — абзацы #ex-body аккордеоном.
   Уже набранный KaTeX не разбирается: значение ячейки — копия узла значения
   той же строки, а у ячейки стоит data-src="блок#номер", по которому прибор
   паритета находит, откуда число.

   ⚠️ СКОРОСТЬ (COVERAGE О32): пересборка не на каждом кадре. Подпись
   содержимого табло сравнивается с прошлой, и «Ответ» пересобирается,
   только когда источник изменился; сам проход откладывается на кадр.
   --------------------------------------------------------------------- */

/* Главные числа модели: строки табло [блок, номер строки] и, если есть,
   строка таблицы «До / После / Δ», откуда брать «было» и Δ. Модели без
   записи главных чисел не получают (нет данных — нет секции). */
const HERO = {
  'm-graph': [['info-graph', 1], ['info-graph', 2]],
  'm-transform': [['info-math', 1]],
  'm-optimum': [['info-math', 0], ['info-math', 1]],
  'm-tangent': [['info-math', 1], ['info-math', 2], ['info-math', 3]],
  'm-minmax': [['info-math', 2]],
  'm-constraint': [['info-math', 0], ['info-math', 1], ['info-math', 2]],
  'ppf': [['info-ppf', 1], ['info-ppf', 2]],
  'ppfsum': [['info-ppfsum', 1], ['info-ppfsum', 2], ['info-ppfsum', 3]],
  'trade': [['info-ppft', 3], ['info-ppft', 4], ['info-ppft', 5]],
  'tradeprice': [['info-tb', 2], ['info-tb', 3]],
  'sd': [['sec-eq', 0], ['sec-eq', 1]],
  'sdsum': [['sec-eq', 0], ['sec-eq', 1]],
  'taxes': [['sec-eq', 0, 'Q'], ['sec-eq', 1, 'P покупателя'], ['sec-eq', 2, 'P продавца'], ['info-tax', 'DWL']],
  'tax': [['sec-eq', 0, 'Q'], ['sec-eq', 1, 'P покупателя'], ['sec-eq', 2, 'P продавца'], ['info-tax', 'DWL']],
  'tax-adv': [['sec-eq', 0, 'Q'], ['sec-eq', 1, 'P покупателя'], ['sec-eq', 2, 'P продавца'], ['info-tax', 'DWL']],
  'ceil': [['sec-eq', 0], ['sec-eq', 2], ['sec-eq', 3], ['sec-eq', 4]],
  'quota': [['sec-eq', 0], ['sec-eq', 1], ['sec-eq', 2]],
  'elast': [['info-elast', 1], ['info-elast', 7]],
  'ext': [['sec-eq', 0], ['sec-eq', 1], ['info-ext', 1], ['info-ext', 2]],
  'prod': [['info-prod', 0], ['info-prod', 1]],
  'costs': [['info-costs', 4], ['info-costs', 6]],
  'plants': [['info-plants', 0], ['info-plants', 1], ['info-plants', 2], ['info-plants', 3]],
  'isoquant': [['info-iso', 0], ['info-iso', 1]],
  'mono': [['info-mono', 0], ['info-mono', 1], ['info-mono', 4], ['info-mono', 5]],
  'mono-nat': [['info-mono', 0], ['info-mono', 1], ['info-nat', 2]],
  'mono-d1': [['info-mono', 0], ['info-mono', 1]],
  'mono-d3': [['info-d3', 0], ['info-d3', 1]],
  'mono-kink': [['info-kink', 0], ['info-kink', 1], ['info-kink', 2]],
  'labor': [['info-labor', 0], ['info-labor', 1]],
  'labor-mono': [['info-labor', 0], ['info-labor', 1], ['info-labor', 4]],
  'labor-union': [['info-labor', 0], ['info-labor', 1]],
  'labor-bilat': [['info-labor', 0], ['info-labor', 1]],
  'smallopen': [['info-open', 2], ['info-open', 3]],
  'monoexport': [['info-d3', 0], ['info-d3', 1]],
  'consumer': [['info-consumer', 0], ['info-consumer', 1]],
  'cons-slutsky': [['info-consumer', 5], ['info-consumer', 6], ['info-consumer', 7]],
  'adas': [['info-macro', 0], ['info-macro', 1]],
  'islm': [['info-macro', 0], ['info-macro', 1]],
  'money': [['info-macro', 1]],
  'loanable': [['info-macro', 0]],
  'fx': [['info-macro', 0], ['info-macro', 1]],
  'laffer': [['info-macro', 0], ['info-macro', 1]],
  'ineq': [['info-inequality', 0], ['info-inequality', 1]],
};

/* Заголовки групп табло в «Ответе». Блок без записи идёт без заголовка. */
const ANSWER_GROUP = {
  'info-areas': 'Излишки', 'info-tax': 'Вмешательство', 'info-sum': 'По группам',
  'info-mono': 'Монополия', 'info-nat': 'Естественная монополия', 'info-costs': 'Издержки',
  'info-prod': 'Производство', 'info-iso': 'Изокванта', 'info-plants': 'Два завода',
  'info-labor': 'Рынок труда', 'info-inequality': 'Неравенство', 'info-consumer': 'Выбор потребителя',
  'info-macro': 'Макро', 'info-math': 'Математика', 'info-elast': 'Эластичность',
  'info-ext': 'Внешние эффекты', 'info-open': 'Открытая экономика', 'info-d3': 'Дискриминация',
  'info-kink': 'Составной спрос', 'info-ppf': 'КПВ', 'info-ppfsum': 'Сумма КПВ',
  'info-ppft': 'Торговля', 'info-tb': 'Торговля двух стран', 'info-graph': 'Функция',
};

/* Подпись строки табло → подпись ячейки и обозначение. «Q* (количество)» →
   «Количество», «Q*»; «Равновесный выпуск Y» → «Равновесный выпуск», «Y»;
   иначе подпись целиком и без обозначения. */
function heroLabel(t) {
  const s = String(t || '').replace(/\u200b/g, '').trim();
  const cap = (x) => x ? x.charAt(0).toUpperCase() + x.slice(1) : x;
  let m = /^([A-Za-zА-Яа-я][^\s()]{0,7})\s*\((.+)\)$/.exec(s);
  if (m && /[A-Za-z]/.test(m[1])) return { caption: cap(m[2].trim()), not: m[1] };
  m = /^(.+?)\s+([A-Za-z][A-Za-z0-9_*∗′]{0,5})$/.exec(s);
  if (m && /[А-Яа-я]/.test(m[1])) return { caption: cap(m[1].trim()), not: m[2] };
  return { caption: cap(s), not: '' };
}

function plainText(el) {
  if (!el) return '';
  const c = el.cloneNode(true);
  c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
  return c.textContent.replace(/[\s   ​]+/g, ' ').trim();
}
function statRows(blk) {
  return blk ? [...blk.querySelectorAll('.stat')].filter(s => !s.closest('.ans-hero')) : [];
}
/* Строка таблицы «До / После / Δ» по подписи первой ячейки. */
function txRow(blkId, label) {
  const blk = document.getElementById(blkId) || document.getElementById('info-tax');
  const tables = blk ? blk.querySelectorAll('table.tx-table') : [];
  for (const t of tables) {
    const head = [...(t.querySelector('tr') || { children: [] }).children].map(plainText);
    for (const tr of t.querySelectorAll('tr')) {
      const cells = [...tr.children];
      if (cells.length < 3 || plainText(cells[0]) !== label) continue;
      const col = (name) => { const i = head.indexOf(name); return i > 0 ? plainText(cells[i]) : ''; };
      return { before: col('До'), after: col('После'), delta: col('Δ') };
    }
  }
  return null;
}

const ANSWER_OPEN = {};   // раскрытые вопросы «Разбора» по моделям
let _answerSig = '';
let _answerMarks = 0;
let _answerQueued = false;
function answerSignature() {
  const sb = document.getElementById('sb-body');
  const ex = document.getElementById('ex-body');
  return String(STATE.sceneKey) + '|' + (sb ? sb.textContent.length + ':' + sb.textContent.slice(0, 4000) : '')
    + '|' + (ex ? ex.innerHTML.length : 0) + '|' + STATE.incBuyer + '|' + STATE.incSeller;
}
function scheduleAnswer() {
  if (_answerQueued) return;
  _answerQueued = true;
  requestAnimationFrame(() => { _answerQueued = false; buildAnswer(); });
}

function buildAnswer() {
  const host = document.getElementById('ans-hero');
  if (!host) return;
  const sig = answerSignature();
  /* Сцена может переписать табло тем же текстом (пометки is-hero при этом
     пропадают): тогда собираем заново, хотя подпись та же. */
  const marks = document.querySelectorAll('#sb-body .stat.is-hero').length;
  if (sig === _answerSig && marks === _answerMarks) return;
  _answerSig = sig;
  document.querySelectorAll('#sb-body .stat.is-hero').forEach(s => s.classList.remove('is-hero'));
  host.innerHTML = '';
  const spec = HERO[STATE.sceneKey];
  const cells = [];
  (spec || []).forEach(h => {
    const [blkId, i, tbl] = h;
    const blk = document.getElementById(blkId);
    if (!blk || !blk.isConnected || blk.style.display === 'none') return;
    if (typeof i === 'number') {
      const row = statRows(blk)[i];
      if (!row) return;
      const lab = row.querySelector(':scope > span'), val = row.querySelector(':scope > b');
      if (!val || !plainText(val)) return;
      row.classList.add('is-hero');
      cells.push({ src: blkId + '#' + i, lab, val, tx: tbl ? txRow(blkId, tbl) : null });
    } else {
      // Главное число из таблицы «До / После / Δ» (потери общества у налогов).
      const r = txRow(blkId, i);
      if (!r || !r.after) return;
      cells.push({ src: blkId + '@' + i, labText: i, valText: r.after, tx: r });
    }
  });
  host.hidden = !cells.length;
  _answerMarks = document.querySelectorAll('#sb-body .stat.is-hero').length;
  // Заголовок группы результатов (README макета, 8): над главными числами.
  const tt = document.getElementById('ans-title');
  const src = document.querySelector('#sec-eq .section-title');
  const shown = src && src.closest('#sec-eq') && document.getElementById('sec-eq').style.display !== 'none' && plainText(src);
  if (tt) { tt.innerHTML = shown ? src.innerHTML : ''; tt.hidden = !shown; }
  host.classList.toggle('ans-hero--one', cells.length === 1);
  cells.forEach(c => {
    const d = document.createElement('div');
    d.className = 'ans-cell';
    d.dataset.src = c.src;
    // Подпись ячейки словами, ниже «обозначение = число» (README макета, 8.3).
    const parts = heroLabel(c.lab ? plainText(c.lab) : c.labText);
    const l = document.createElement('div'); l.className = 'ans-lab'; l.textContent = parts.caption;
    const line = document.createElement('div'); line.className = 'ans-line';
    if (parts.not) {
      const n = document.createElement('span'); n.className = 'ans-not';
      // «Q∗» из табло — звёздочка верхним индексом, как в макете (Q* =).
      const star = /[∗*]$/.test(parts.not);
      const base = parts.not.replace(/[∗*]$/, '');
      if (star && typeof katexInto === 'function' && /^[A-Za-z]{1,3}$/.test(base)) katexInto(n, base + '^{*}');
      else if (typeof paintNotation === 'function') paintNotation(n, parts.not); else n.textContent = parts.not;
      const eq = document.createElement('span'); eq.className = 'ans-eq'; eq.textContent = '=';
      line.append(n, eq);
    }
    const v = document.createElement('span'); v.className = 'ans-val';
    if (c.val) v.innerHTML = c.val.innerHTML; else v.textContent = c.valText;
    const len = plainText(v).replace(/\s/g, '').length;
    v.classList.add(len <= 4 ? 'ans-val--l' : (len <= 6 ? 'ans-val--m' : 'ans-val--s'));
    line.appendChild(v);
    d.append(l, line);
    if (c.tx && c.tx.before) {
      const w = document.createElement('div'); w.className = 'ans-was';
      w.textContent = 'было ' + c.tx.before + (c.tx.delta ? ' · ' + c.tx.delta.replace(/^-/, '−') : '');
      d.appendChild(w);
    }
    host.appendChild(d);
  });
  buildStatus();
  buildBurden();
  buildExplainAccordion();
}

/* «Кто несёт налог» / «Кому достаётся субсидия» (README макета, 8.5): доли
   из бремени, которое сцена уже посчитала (STATE.incBuyer, incSeller —
   40-scenes-market.js). Нет вмешательства или нет исходного рынка — нет секции. */
function buildBurden() {
  const box = document.getElementById('ans-burden');
  if (!box) return;
  const k = STATE.sceneKey;
  const b = +STATE.incBuyer, s = +STATE.incSeller;
  const on = /^(taxes|tax|tax-adv)$/.test(k) && STATE.taxActive && !STATE.taxNoBase
    && isFinite(b) && isFinite(s) && Math.abs(b) + Math.abs(s) > 1e-9;
  box.hidden = !on;
  if (!on) { box.innerHTML = ''; return; }
  const sub = STATE.intervType === 'subsidy';
  const tot = Math.abs(b) + Math.abs(s);
  const pb = Math.abs(b) / tot * 100, ps = 100 - pb;
  const pct = (x) => fmt(Math.round(x)) + '\u202f%';
  const form = (typeof taxFormKey === 'function') ? taxFormKey() : 'unit';
  const pctForm = !!(form && form !== 'unit');
  box.innerHTML = '';
  const h = document.createElement('h3'); h.className = 'col-sub'; h.textContent = sub ? 'Кому достаётся субсидия' : 'Кто несёт налог';
  const bar = document.createElement('div'); bar.className = 'burden-bar';
  bar.setAttribute('role', 'img');
  bar.setAttribute('aria-label', 'Покупатели ' + pct(pb) + ', продавцы ' + pct(ps));
  const bb = document.createElement('span'); bb.className = 'burden-b'; bb.style.width = pb + '%';
  bar.appendChild(bb);
  const cols = document.createElement('div'); cols.className = 'burden-cols';
  const col = (cls, name, v, p) => {
    const c = document.createElement('div'); c.className = 'burden-col ' + cls;
    const n = document.createElement('div'); n.className = 'burden-name'; n.textContent = name;
    const x = document.createElement('div'); x.className = 'burden-val'; x.textContent = fmt(Math.abs(v)) + ' · ' + pct(p);
    c.append(n, x); return c;
  };
  cols.append(col('is-buyer', 'Покупатели', b, pb), col('is-seller', 'Продавцы', s, ps));
  const note = document.createElement('div'); note.className = 'burden-note';
  note.textContent = pctForm ? 'При налоге долей от цены клин растёт вместе с ценой.'
    : 'Не зависит от того, кто платит по закону: переключите сторону, и числа не изменятся.';
  box.append(h, bar, cols, note);
}

/* Статус словами: предупреждения сцены строкой над числами (канон 2.5:
   серая плашка, цветная полоса слева, значок; заливки -tint нет). Сами
   предупреждения остаются на месте в табло — это их источник. */
function buildStatus() {
  const box = document.getElementById('ans-status');
  if (!box) return;
  box.innerHTML = '';
  const warns = [...document.querySelectorAll('#sb-body .warn')].filter(w => w.offsetParent !== null || w.closest('#sb-body'));
  warns.forEach(w => {
    const t = plainText(w);
    if (!t) return;
    const p = document.createElement('div');
    p.className = 'ans-status';
    p.setAttribute('role', 'status');
    p.innerHTML = w.innerHTML;
    box.appendChild(p);
  });
  box.hidden = !box.children.length;
}

/* «Разбор»: каждый абзац с жирным началом — вопрос-кнопка, остальное — ответ;
   абзац «Вывод:» / «Вывод.» — плашка вывода; абзац без жирного начала —
   продолжение предыдущего ответа (COVERAGE О8). Первый вопрос открыт. */
function buildExplainAccordion() {
  const ex = document.getElementById('ex-body');
  if (!ex || ex._accSig === ex.innerHTML.length + ':' + STATE.sceneKey) return;
  ex.querySelectorAll(':scope > .sb-note').forEach((note, ni) => {
    const ps = [...note.querySelectorAll(':scope > p')];
    ps.forEach((p, i) => {
      const b = p.firstElementChild;
      // Жирное НАЧАЛО абзаца: до <b> не должно стоять текста (иначе это выделенное
      // слово посреди фразы, а не вопрос).
      let before = '';
      for (let n = p.firstChild; n && n !== b; n = n.nextSibling) before += n.textContent || '';
      const lead = (b && b.tagName === 'B' && !before.trim()) ? plainText(b) : '';
      p.classList.remove('ex-q', 'ex-out', 'ex-open');
      if (!lead) return;
      if (/^Вывод[.:]/.test(lead)) { p.classList.add('ex-out'); return; }
      p.classList.add('ex-q');
      const mem = ANSWER_OPEN[STATE.sceneKey];
      const id = ni + ':' + i;
      if (mem ? mem.has(id) : (ni === 0 && i === 0)) p.classList.add('ex-open');
      p.dataset.acc = id;
      // Ответ — всё после жирного вопроса: в свой узел, его и прячет аккордеон.
      if (!p.querySelector(':scope > .ex-a')) {
        const a = document.createElement('span');
        a.className = 'ex-a';
        while (b.nextSibling) a.appendChild(b.nextSibling);
        p.appendChild(a);
      }
      if (!b._accWired) {
        b._accWired = true;
        b.setAttribute('role', 'button');
        b.tabIndex = 0;
        const toggle = () => {
          p.classList.toggle('ex-open');
          b.setAttribute('aria-expanded', p.classList.contains('ex-open') ? 'true' : 'false');
          // Раскрытое помнится у каждой модели (README макета, 8.8).
          const set = new Set([...ex.querySelectorAll('p.ex-open[data-acc]')].map(x => x.dataset.acc));
          ANSWER_OPEN[STATE.sceneKey] = set;
        };
        b.addEventListener('click', toggle);
        b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      }
      b.setAttribute('aria-expanded', p.classList.contains('ex-open') ? 'true' : 'false');
    });
  });
  ex._accSig = ex.innerHTML.length + ':' + STATE.sceneKey;
}

/* Табло пишут и вне перерисовки (отложенные расчёты сцен): «Ответ» следит
   за ним сам. Пересборка всё равно откладывается на кадр и сравнивает
   подпись содержимого, поэтому лишней работы на кадре протяжки нет. */
(function watchScoreboard() {
  const sb = document.getElementById('sb-body');
  if (!sb || typeof MutationObserver !== 'function') return;
  new MutationObserver((list) => {
    // Свои пометки is-hero «Ответ» ставит сам — на них не отвечаем.
    if (list.every(m => m.type === 'attributes')) return;
    scheduleAnswer();
  }).observe(sb, { childList: true, subtree: true, characterData: true });
})();
