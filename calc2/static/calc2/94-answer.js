// «Ответ»: представление поверх табло (редизайн 10.2026, фаза 6).
/* ---------------------------------------------------------------------
   Сцены по-прежнему пишут свои блоки #info-* (и #sec-eq) в табло #sb-body:
   этим живут печать, «Объяснение модели» и десятки проверок.
   «Ответ» собирается ПОВЕРХ них и только читает:
     · статус словами — предупреждения сцены (.warn) строкой над числами;
     · главные величины — выбранные строки табло (HERO ниже) СТРОКАМИ ПО
       ГРУППАМ (решение владельца 09.10, ADR 0144): у группы заголовок, в
       группе одна величина на строку, подпись слева, значение справа, один
       кегль у всех значений; у строки «было · Δ» из таблицы «До / После / Δ»;
     · дальше прежние блоки тем же видом строк; строка, ставшая главной, в
       блоке не повторяется (класс .is-hero), блок без своих строк прячется;
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
/* '*' — все строки блока с пометкой .ans-main, по порядку (ADR 0143): у
   «Математики» число главных величин зависит от модели и от числа кривых. */
const HERO = {
  'm-graph': [['info-graph', '*']],
  'm-transform': [['info-math', '*']],
  'm-optimum': [['info-math', '*']],
  'm-tangent': [['info-math', '*']],
  'm-minmax': [['info-math', '*']],
  'm-constraint': [['info-math', '*']],
  'ppf': [['info-ppf', 1], ['info-ppf', 2]],
  'ppfsum': [['info-ppfsum', 1], ['info-ppfsum', 2], ['info-ppfsum', 3]],
  'trade': [['info-ppft', 3], ['info-ppft', 4], ['info-ppft', 5]],
  'tradeprice': [['info-tb', 2], ['info-tb', 3]],
  /* Четвёртый элемент — [подпись, обозначение] вместо разбора подписи табло:
     «CS (потребитель)» в «Ответе» читается как «Излишек потребителя», CS = … */
  'sd': [['sec-eq', 0], ['sec-eq', 1],
    ['info-areas', 0, null, ['Излишек потребителя', 'CS']],
    ['info-areas', 1, null, ['Излишек производителя', 'PS']],
    ['info-areas', 2, null, ['Общественное благосостояние', 'SW']]],
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

/* Заголовки групп «Ответа» по блоку табло. Блок без записи идёт без
   заголовка; у #sec-eq заголовок свой (копия .section-title); у «Математики»
   группы задают сами строки (data-ans-group, 70-scenes-math.js). */
const ANSWER_GROUP = {
  'info-areas': 'Излишки', 'info-tax': 'Вмешательство', 'info-sum': 'По группам',
  'info-mono': 'Монополия', 'info-nat': 'Естественная монополия', 'info-costs': 'Издержки',
  'info-prod': 'Производство', 'info-iso': 'Изокванта', 'info-plants': 'Два завода',
  'info-labor': 'Рынок труда', 'info-inequality': 'Неравенство', 'info-consumer': 'Выбор потребителя',
  'info-macro': 'Равновесие', 'info-math': 'Математика', 'info-elast': 'Эластичность',
  'info-ext': 'Внешние эффекты', 'info-open': 'Открытая экономика', 'info-d3': 'Дискриминация',
  'info-kink': 'Составной спрос', 'info-ppf': 'КПВ', 'info-ppfsum': 'Сумма КПВ',
  'info-ppft': 'Торговля', 'info-tb': 'Торговля двух стран', 'info-graph': 'Функция',
};

/* Подпись строки табло → подпись ячейки и обозначение. «Q* (количество)» →
   «Количество», «Q*»; «Равновесный выпуск Y» → «Равновесный выпуск», «Y»;
   иначе подпись целиком и без обозначения. */
/* Голое сокращение в подписи табло («DWL») — в ячейке словами и обозначением,
   как в макете: «Потери общества», «DWL = 225» (README 8.3). */
const HERO_WORDS = { DWL: 'Потери общества', CS: 'Излишек покупателя', PS: 'Излишек продавца' };
function heroLabel(t) {
  const s = String(t || '').replace(/\u200b/g, '').trim();
  if (HERO_WORDS[s]) return { caption: HERO_WORDS[s], not: s };
  const cap = (x) => x ? x.charAt(0).toUpperCase() + x.slice(1) : x;
  // «Q∗ (количество)»: обозначение, ПРОБЕЛ, слова в скобках. «f(x0)» — запись
  // функции, а не подпись со словами: её не режем.
  let m = /^([A-Za-zА-Яа-я][^\s()]{0,7})\s+\((.+)\)$/.exec(s);
  if (m && /[A-Za-z]/.test(m[1])) return { caption: cap(m[2].trim()), not: m[1] };
  m = /^(.+?)\s+([A-Za-z][A-Za-z0-9_*∗′]{0,5})$/.exec(s);
  if (m && /[А-Яа-я]/.test(m[1])) return { caption: cap(m[1].trim()), not: m[2] };
  return { caption: /^[A-Za-z]/.test(s) ? s : cap(s), not: '' };
}

/* Обозначение из подписи табло → TeX: заглавные в несколько букв (MC, DWL,
   CS) — прямым шрифтом; иначе буква и индекс («Qm» → Q_m, «X0» → X_0,
   «Wп» → W_п); звёздочка — верхним индексом. Не разобрали — null. */
function notationTex(t) {
  let s = String(t || '').replace(/[\u200b\s]/g, '');
  if (!s) return null;
  const star = /[∗*]$/.test(s); s = s.replace(/[∗*]$/, '');
  const sup = star ? '^{*}' : '';
  if (/^[A-Z]{2,4}$/.test(s)) return '\\mathrm{' + s + '}' + sup;
  const m = /^([A-Za-z])([A-Za-z0-9А-Яа-я]{0,4})$/.exec(s);
  if (!m) return null;
  const sub = m[2] ? '_{' + (/[А-Яа-я]/.test(m[2]) ? '\\text{' + m[2] + '}' : m[2]) + '}' : '';
  return m[1] + sub + sup;
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
  // Таблица «До / После» живёт в блоке вмешательства, а строка главного числа —
  // в блоке равновесия (Q, цены): ищем в своём блоке, потом во вмешательстве.
  const own = document.getElementById(blkId);
  let tables = own ? [...own.querySelectorAll('table.tx-table')] : [];
  if (!tables.length) { const tx = document.getElementById('info-tax'); tables = tx ? [...tx.querySelectorAll('table.tx-table')] : []; }
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
    + '|' + (ex ? ex.innerHTML.length : 0) + '|' + STATE.incBuyer + '|' + STATE.incSeller
    // Отрезок ответа: ручной отрезок с теми же числами ответа меняет строку под шапкой.
    + '|' + (typeof _ansSeg !== 'undefined' && _ansSeg ? _ansSeg.a + ':' + _ansSeg.b : '');
}
function scheduleAnswer() {
  if (_answerQueued) return;
  _answerQueued = true;
  requestAnimationFrame(() => { _answerQueued = false; buildAnswer(); });
}

/* Модель «Математики» и «Построения графиков»: у её строк обозначение из
   подписи в значение не выносится («Пересекает ось x» → «−2; 2»). */
function answerIsMath() { return STATE.mode === 'math' || STATE.mode === 'graph'; }

/* Копия подписи строки табло без приписки .ans-ctx («, кривая f»): в
   «Ответе» её роль у заголовка группы. */
function labelCopy(lab) {
  const c = lab.cloneNode(true);
  c.querySelectorAll('.ans-ctx').forEach(x => x.remove());
  return c;
}

/* Значение строки «Ответа». Число — формулой прямым шрифтом; список и точки
   — по куску на значение, куски не рвутся, перенос (если весь список не
   влез даже в строку целиком) — только между ними; «нет» — приглушённо;
   прочее (фраза, «L = 10, MP = 300») — копией табло. Текст значения тот же,
   что у строки-источника: по нему сверяют паритет и «Сначала сам». */
const ANS_ITEM = /^\(?[−-]?\d[\d\s\u00a0\u202f\u2009]*([.,]\d+)?(;[−-]?\d[\d\s\u00a0\u202f\u2009]*([.,]\d+)?)?\)?(°|∘|\s?%)?$/;
function answerValueInto(v, srcEl, srcText) {
  const raw = srcEl ? plainText(srcEl) : String(srcText || '');
  if (/^нет$/i.test(raw)) { v.textContent = 'нет'; v.classList.add('ans-val--none'); return; }
  const pureNum = /^[−-]?\d[\d\s\u00a0\u202f\u2009]*([.,]\d+)?(\s?%)?$/.test(raw);
  if (typeof katexInto === 'function' && pureNum) {
    /* Пробелы — неразрывные (~), чтобы в тексте осталось «1 250», как в
       строке-источнике; запятая дроби без отбивки. */
    const tx = raw.replace(/^-/, '−').replace(/[\s\u00a0\u202f\u2009]+/g, '~').replace(/,/g, '{,}').replace(/%/g, '\\%').replace(/−/g, '\\text{−}');
    katexInto(v, '\\mathrm{' + tx + '}');
    return;
  }
  // Список чисел или точек через «;»: делим по «;» вне скобок.
  const items = [];
  let depth = 0, cur = '';
  for (const ch of raw) {
    if (ch === '(') depth++;
    if (ch === ')') depth--;
    if (ch === ';' && depth === 0) { items.push(cur.trim()); cur = ''; } else cur += ch;
  }
  items.push(cur.trim());
  if (items.length > 1 && typeof katexInto === 'function' && typeof statToTex === 'function'
      && items.every(it => ANS_ITEM.test(it.replace(/;\s+/g, ';')))) {
    v.innerHTML = '';
    items.forEach((it, k) => {
      const u = document.createElement('span'); u.className = 'ans-item';
      katexInto(u, statToTex(it));
      if (k < items.length - 1) {
        const sep = document.createElement('span'); sep.className = 'ans-sep'; sep.textContent = ';';
        u.appendChild(sep);
      }
      v.appendChild(u);
      // Место переноса без пробела в тексте: текст значения — побайтно табло («−2;2»).
      if (k < items.length - 1) v.appendChild(document.createElement('wbr'));
    });
    return;
  }
  if (srcEl) v.innerHTML = srcEl.innerHTML; else v.textContent = raw;
}

/* Заголовок группы: у кривой «Построения графиков» — цветная точка и запись
   «f(x) = x² − 4» (строка табло data-ans-head); иначе — текст, в котором
   $…$ набирается формулой, или готовая разметка заголовка табло. */
function answerGroupHead(g) {
  const h = document.createElement('h3');
  h.className = 'ans-ghead';
  if (g.head) {
    const dot = document.createElement('span'); dot.className = 'ans-gdot'; dot.setAttribute('aria-hidden', 'true');
    if (g.head.dataset.color) dot.style.background = g.head.dataset.color;
    const f = document.createElement('span'); f.className = 'ans-gform';
    if (!(typeof katexInto === 'function' && katexInto(f, g.head.dataset.tex || ''))) f.textContent = g.head.dataset.tex || '';
    h.append(dot, f);
  } else if (g.html) {
    h.innerHTML = g.html;
  } else {
    h.textContent = g.title;
    if (/\$/.test(g.title) && typeof renderMathIn === 'function') renderMathIn(h);
  }
  return h;
}

/* Строка об отрезке ответа под шапкой (только «Математика» и «Построение
   графиков», у «С ограничением» отрезка нет): числа живые, из _ansSeg. */
function buildSegNote() {
  const note = document.getElementById('ans-seg-note');
  if (!note) return;
  const row = document.getElementById('ans-seg-row');
  const on = answerIsMath() && typeof _ansSeg !== 'undefined' && _ansSeg && row && row.style.display !== 'none';
  note.hidden = !on;
  if (!on) { note.textContent = ''; return; }
  const f = (typeof ansFmt === 'function') ? ansFmt : fmt;
  note.textContent = 'Ищем на отрезке $x$ от ' + f(_ansSeg.a) + ' до ' + f(_ansSeg.b) + '. Масштаб графика на ответ не влияет.';
  if (typeof renderMathIn === 'function') renderMathIn(note);
}

/* Блок табло, все строки которого ушли в «Ответ» (или в заголовок группы),
   не показывается вовсе: иначе от него оставался голый заголовок
   («Излишки» без строк у «Спроса и предложения»). */
function hideDrainedBlocks() {
  const sb = document.getElementById('sb-body');
  if (!sb) return;
  /* Та же величина второй строкой в другом блоке (у потолка цены «Дефицит 40»
     стоит и в равновесии, и под таблицей «До / После»): в колонке — один раз.
     Сравниваются подпись и значение строки-источника главной величины. */
  const key = (r) => plainText(r.querySelector(':scope > span')).replace(/\s+/g, '') + '=' + plainText(r.querySelector(':scope > b')).replace(/\s+/g, '');
  const heroKeys = new Set([...sb.querySelectorAll('.stat.is-hero')].map(key));
  sb.querySelectorAll('.stat').forEach(r => {
    r.classList.toggle('ans-dup', !r.classList.contains('is-hero') && heroKeys.has(key(r)));
  });
  const ownText = (el) => [...el.childNodes].some(n => n.nodeType === 3 && /\S/.test(n.nodeValue));
  [...sb.children].forEach(blk => {
    if (!blk.id) return;
    blk.classList.remove('ans-drained');
    if (!blk.querySelector('.stat.is-hero, .stat[data-ans-head], .stat.ans-dup')) return;
    const left = [...blk.querySelectorAll('*')].some(el => !el.closest('.section-title, .katex-mathml')
      && el.getClientRects().length && ownText(el));
    if (!left) blk.classList.add('ans-drained');
  });
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
  const specRows = [];
  (spec || []).forEach(h => {
    const [blkId, i, tbl] = h;
    if (i === '*') {
      const blk = document.getElementById(blkId);
      const rows = statRows(blk);
      rows.forEach((r, k) => { if (r.classList.contains('ans-main')) specRows.push([blkId, k, tbl]); });
    } else specRows.push(h);
  });
  specRows.forEach(h => {
    const [blkId, i, tbl, over] = h;
    const blk = document.getElementById(blkId);
    if (!blk || !blk.isConnected || blk.style.display === 'none') return;
    if (typeof i === 'number') {
      const row = statRows(blk)[i];
      if (!row) return;
      const lab = row.querySelector(':scope > span'), val = row.querySelector(':scope > b');
      if (!val || !plainText(val)) return;
      row.classList.add('is-hero');
      cells.push({ src: blkId + '#' + i, blk, row, lab, val, over, group: row.dataset.ansGroup || '', tx: tbl ? txRow(blkId, tbl) : null });
    } else {
      // Главное число из таблицы «До / После / Δ» (потери общества у налогов).
      const r = txRow(blkId, i);
      if (!r || !r.after) return;
      cells.push({ src: blkId + '@' + i, blk, labText: i, valText: r.after, tx: r, tableRow: true });
    }
  });
  host.hidden = !cells.length;
  _answerMarks = document.querySelectorAll('#sb-body .stat.is-hero').length;
  const isMath = answerIsMath();
  /* Группы: строки подряд с одним ключом. Ключ — data-ans-group строки
     (математика) или блок табло; строка из таблицы «До / После» стоит в группе
     предыдущей строки (потери общества — в «Рынке после налога»). */
  const eqTitle = document.querySelector('#sec-eq > .section-title');
  const eqShown = eqTitle && document.getElementById('sec-eq').style.display !== 'none' && plainText(eqTitle);
  const groups = [];
  cells.forEach(c => {
    let key, g = null;
    if (c.tableRow && groups.length) key = groups[groups.length - 1].key;
    else if (c.group) key = 'g:' + c.group;
    else key = 'b:' + c.src.replace(/[#@].*$/, '');
    const last = groups[groups.length - 1];
    if (last && last.key === key) { last.cells.push(c); return; }
    g = { key, cells: [c], title: '' };
    if (c.group) {
      g.head = [...c.blk.querySelectorAll('.stat[data-ans-head]')].find(x => x.dataset.ansHead === c.group) || null;
      g.title = c.group;
    } else {
      const blkId = c.src.replace(/[#@].*$/, '');
      if (blkId === 'sec-eq' && eqShown) g.html = eqTitle.innerHTML;
      else g.title = ANSWER_GROUP[blkId] || '';
    }
    groups.push(g);
  });
  groups.forEach(g => {
    const box = document.createElement('div');
    box.className = 'ans-group';
    if (g.head || g.html || g.title) box.appendChild(answerGroupHead(g));
    g.cells.forEach(c => box.appendChild(answerRow(c, isMath)));
    host.appendChild(box);
  });
  buildSegNote();
  buildStatus();
  buildBurden();
  buildExplainAccordion();
  // Строка главных чисел над холстом (760–1239 px, «Ответ» выезжает).
  const strip = document.getElementById('ans-strip');
  if (strip) {
    strip.innerHTML = '';
    host.querySelectorAll('.ans-cell').forEach(c => {
      const s = document.createElement('span');
      const n = c.querySelector('.ans-not'), v = c.querySelector('.ans-val'), l = c.querySelector('.ans-lab');
      s.textContent = (n && plainText(n) ? plainText(n) : (l ? plainText(l) : '')) + ' = ';
      const b = document.createElement('b'); b.textContent = v ? plainText(v) : '';
      s.appendChild(b); strip.appendChild(s);
    });
  }
  // Обозначения в подписях строк («Весь ресурс на X») — формулой, как во всей панели.
  if (typeof markNotationsIn === 'function') markNotationsIn(host);
  hideDrainedBlocks();
  if (typeof applySelf === 'function') applySelf();
}

/* Строка «Ответа»: подпись слева, значение справа, «было · Δ» под значением.
   Классы .ans-cell / .ans-lab / .ans-not / .ans-val / .ans-was и data-src —
   прежние (меняется вид, а не смысл): по ним работают паритет и «Сначала сам».
   data-not — обозначение величины («x», «Q*»): по нему «Сначала сам» узнаёт
   ось, даже когда обозначение не выносится в значение (математика). */
function answerRow(c, isMath) {
  const d = document.createElement('div');
  d.className = 'ans-cell';
  d.dataset.src = c.src;
  const labText = c.lab ? plainText(labelCopy(c.lab)) : c.labText;
  let parts = c.over ? { caption: c.over[0], not: c.over[1] } : heroLabel(labText);
  /* Значение со своим «=» («L = 15, AP = 225»): обозначение остаётся в
     подписи («Максимум AP»), иначе выходило «AP = L = 15, AP = 225». */
  if (!c.over && parts.not && /=/.test(c.val ? plainText(c.val) : String(c.valText || ''))) parts = { caption: labText, not: '', keep: parts.not };
  if (parts.not || parts.keep) d.dataset.not = parts.not || parts.keep;
  const l = document.createElement('div'); l.className = 'ans-lab';
  const line = document.createElement('div'); line.className = 'ans-line';
  if (isMath || (!parts.not && c.lab)) {
    // Подпись как в табло, вместе с набранными формулой обозначениями.
    if (c.lab) l.append(...labelCopy(c.lab).childNodes); else l.textContent = labText;
  } else {
    l.textContent = parts.caption;
  }
  if (parts.not && !isMath) {
    const n = document.createElement('span'); n.className = 'ans-not';
    // Обозначение — всегда формулой (правило 46 DESIGN.md): «Q∗» → Q*, «X0» → X₀.
    const tex = notationTex(parts.not);
    if (tex && typeof katexInto === 'function') katexInto(n, tex);
    else if (typeof paintNotation === 'function') paintNotation(n, parts.not); else n.textContent = parts.not;
    const eq = document.createElement('span'); eq.className = 'ans-eq'; eq.textContent = '=';
    line.append(n, eq);
  }
  const v = document.createElement('span'); v.className = 'ans-val';
  answerValueInto(v, c.val || null, c.valText);
  line.appendChild(v);
  d.append(l, line);
  if (c.tx && c.tx.before) {
    const w = document.createElement('div'); w.className = 'ans-was';
    w.textContent = 'было ' + c.tx.before + (c.tx.delta ? ' · ' + c.tx.delta.replace(/^-/, '−') : '');
    d.appendChild(w);
  }
  return d;
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
  /* Предупреждение в табло спрятано стилем (оно стоит здесь строкой), поэтому
     по offsetParent не судим: отсеиваем только то, что спрятала САМА СЦЕНА —
     hidden, инлайновый display:none или scoped-off у узла и предков (блок
     чужой сцены). Прежнее условие было истинно всегда. */
  const sceneHidden = (w) => { for (let n = w; n && n.id !== 'sb-body'; n = n.parentElement) { if (n.hidden || (n.style && n.style.display === 'none') || n.classList.contains('scoped-off')) return true; } return false; };
  const warns = [...document.querySelectorAll('#sb-body .warn')].filter(w => !sceneHidden(w));
  warns.forEach(w => {
    const t = plainText(w);
    if (!t) return;
    const p = document.createElement('div');
    p.className = 'ans-status' + (/\d/.test(t) ? ' has-num' : '');
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
