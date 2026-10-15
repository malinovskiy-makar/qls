// Сверка двух описей (panels_inventory.mjs): что было видно «до» и куда делось «после».
//
//   node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs before.json after.json [allow.json]
//
// Проверки по каждой модели:
//   ЧИСЛА   — каждое число, видимое в «Ответе» до (главные строки, изменение «50 − 10», строки табло,
//             ячейки таблиц, кроме столбца «Δ», бремя), видно в «Ответе» после;
//   ТЕКСТ   — каждая поясняющая строка «Ответа» до (заметки блоков табло, оговорки, строка бремени)
//             есть после в «Разборе» или в «Ответе»;
//   СТРОКИ  — каждая строка таблицы «До / После» до (подпись, до, после) видна после строкой таблицы или главной
//             ячейкой, у которой значение — «после», а изменение «50 − 10» начинается с «до»;
//   ВОПРОСЫ — вопросы «Разбора» до есть после;
//   ОРГАНЫ  — каждый орган «Условия» с id до есть после в «Условии», в окне «Вид графика» или в закрытом «⋯»
//             карточки «Условия» (сессия 5, README 1: «переехал в «⋯»»);
//   ЗАКРАСКИ — набор закрасок на холсте на старте тот же;
//   ОШИБКИ  — новых ошибок страницы нет;
//   ТОЧКИ   — (сессия 7, если в обеих описях есть поле pts) каждый орган панели «Точки и площади» до (пустой режим и
//             режим с точками и площадью) есть после в панели или в «⋯» её строк. allow «pts»:
//             [{ "key": "ключ органа", "to": "новый ключ" | null, "why": "причина" }] — переехал (to обязан быть) или
//             убран по закрытому списку (to: null). Без причины запись не действует.
// allow.json — закрытый список сознательно убранного: { "<модель>": { "numbers": ["-450"], "notes": ["…"],
//   "rows": ["Налог t"], "ids": ["btn-howto"], "legend": [], "questions": [{ "q": "…", "to": "…" | null, "why": "…" }] },
//   "*": {…} } — «*» действует на все модели.
//   Каждая запись — с причиной
//   в журнале сессии. Код выхода 1, если осталось хоть одно расхождение вне списка.
import fs from 'fs';

const [bPath, aPath, allowPath] = process.argv.slice(2);
if (!bPath || !aPath) { console.error('нужно: before.json after.json [allow.json]'); process.exit(2); }
const B = JSON.parse(fs.readFileSync(bPath, 'utf8')).models;
const A = JSON.parse(fs.readFileSync(aPath, 'utf8')).models;
const ALLOW = allowPath ? JSON.parse(fs.readFileSync(allowPath, 'utf8')) : {};
const allowOf = (k, kind) => new Set([...((ALLOW['*'] || {})[kind] || []), ...((ALLOW[k] || {})[kind] || [])]);

const NUM = /[−-]?\d{1,3}(?:[    ]\d{3})+(?:[.,]\d+)?|[−-]?\d+(?:[.,]\d+)?/g;
const normNum = (s) => s.replace(/[    ]/g, '').replace(/−/g, '-').replace(',', '.').replace(/^-0+(\.0+)?$/, '0');
const numsOf = (s) => (String(s || '').match(NUM) || []).map(normNum);
/* Текст сравнивается без пробелов и знаков: KaTeX и вложенные узлы по-разному расставляют пробелы
   («TC1(Q)» и «TC 1 ( Q )»), а опись могла обрезать заметку. Хватает первых 60 знаков. */
const normText = (s) => String(s || '').toLowerCase()
  .replace(/[\s   ​⁡]+/g, '')
  .replace(/[«»"“”().,;:!?·*∗′'_{}^\\|]/g, '').replace(/−/g, '-');

function answerNumbers(m) {
  const bag = new Set();
  const add = (s) => numsOf(s).forEach(n => bag.add(n));
  (m.answer.groups || []).forEach(g => g.cells.forEach(c => { add(c.val); add(c.was); }));
  (m.answer.blocks || []).forEach(b => {
    b.stats.forEach(s => add(s.val || s.text));
    b.tables.forEach(t => {
      const head = t[0] || [];
      const dCol = head.findIndex(h => /^Δ$/.test(String(h).trim()));
      t.slice(1).forEach(row => row.forEach((cell, i) => { if (i !== dCol && i > 0) add(cell); }));
    });
  });
  add(m.answer.burden);
  return bag;
}
function answerNumbersAfter(m) {
  // После правки число может стоять где угодно в открытом «Ответе»: берём весь видимый текст колонки.
  const bag = new Set(numsOf(m.answer.text));
  answerNumbers(m).forEach(n => bag.add(n));
  return bag;
}
function notesOf(m) {
  const out = [];
  (m.answer.blocks || []).forEach(b => b.notes.forEach(n => { if (n && n.length > 3) out.push(n); }));
  (m.hints || []).filter(h => h.side === 'R').forEach(h => { if (h.text && h.text.length > 3) out.push(h.text); });
  return [...new Set(out)];
}

let problems = 0;
const lines = [];
for (const k of Object.keys(B)) {
  const b = B[k], a = A[k];
  if (!a) { lines.push(`✗ ${k}: модели нет в описи «после»`); problems++; continue; }
  const miss = [];
  // ЧИСЛА
  const allowN = allowOf(k, 'numbers');
  const after = answerNumbersAfter(a);
  [...answerNumbers(b)].filter(n => !after.has(n) && !allowN.has(n)).forEach(n => miss.push('ЧИСЛО ' + n));
  // ТЕКСТ
  const allowT = [...allowOf(k, 'notes')].map(normText);
  const hay = normText(a.explain.text) + ' ' + normText(a.answer.text);
  notesOf(b).forEach(n => {
    const t = normText(n);
    const key = t.slice(0, 60);
    if (!t || hay.includes(key) || allowT.some(x => x && (t.includes(x.slice(0, 60)) || x.includes(key)))) return;
    miss.push('ТЕКСТ «' + n.slice(0, 90) + '»');
  });
  // СТРОКИ ТАБЛИЦ «До / После»: строка до правки видна после либо строкой таблицы с теми же «до» и «после», либо
  // главной ячейкой, у которой значение — это «после», а изменение «50 − 10» начинается с «до». Мешок чисел этого
  // не ловит: «50» может стоять в другой строке.
  const allowR = [...allowOf(k, 'rows')].map(normText);
  const triples = (m) => {
    const out = [];
    (m.answer.blocks || []).forEach(bl => bl.tables.forEach(t => {
      const head = (t[0] || []).map(h => String(h).trim().toLowerCase());
      const iB = head.indexOf('до'), iA = head.indexOf('после');
      if (iB < 1 || iA < 1) return;
      t.slice(1).forEach(row => {
        const lab = row[0] || '', bN = numsOf(row[iB])[0], aN = numsOf(row[iA])[0];
        if (lab && bN != null && aN != null) out.push({ lab, b: bN, a: aN });
      });
    }));
    return out;
  };
  const tA = triples(a);
  const heroHas = (r) => (a.answer.groups || []).some(g => g.cells.some(c =>
    numsOf(c.val).includes(r.a) && numsOf(c.was)[0] === r.b));
  triples(b).forEach(r => {
    if (tA.some(x => normText(x.lab) === normText(r.lab) && x.b === r.b && x.a === r.a)) return;
    if (heroHas(r)) return;
    if (allowR.includes(normText(r.lab))) return;
    miss.push('СТРОКА «' + r.lab + '» ' + r.b + ' → ' + r.a + ': нет ни строкой таблицы, ни главной ячейкой с «до»');
  });
  // ВОПРОСЫ. allow «questions» (сессия 6): [{ "q": "старый вопрос", "to": "новый вопрос" | null, "why": "причина" }] —
  // вопрос переименован (to — новый текст, он обязан быть после) или убран (to: null). Без причины запись не действует.
  const qa = new Set(a.explain.questions.map(normText));
  const allowQ = [...((ALLOW['*'] || {}).questions || []), ...((ALLOW[k] || {}).questions || [])].filter(x => x && x.q && x.why);
  b.explain.questions.forEach(q => {
    if (qa.has(normText(q))) return;
    const r = allowQ.find(x => normText(x.q) === normText(q));
    if (!r) { miss.push('ВОПРОС «' + q + '»'); return; }
    if (r.to && !qa.has(normText(r.to))) miss.push('ВОПРОС «' + q + '» переименован в «' + r.to + '», но нового нет');
  });
  // ОРГАНЫ
  const allowI = allowOf(k, 'ids');
  const idsAfter = new Set([...a.left, ...a.view, ...(a.menus || [])].map(c => c.id).filter(Boolean));
  b.left.filter(c => c.id).forEach(c => { if (!idsAfter.has(c.id) && !allowI.has(c.id)) miss.push('ОРГАН #' + c.id + ' «' + (c.label || '').slice(0, 40) + '»'); });
  // ЗАКРАСКИ
  const allowL = allowOf(k, 'legend');
  const la = new Set(a.legend), lb = new Set(b.legend);
  b.legend.filter(x => !la.has(x) && !allowL.has(x)).forEach(x => miss.push('ЗАКРАСКА пропала: ' + x));
  a.legend.filter(x => !lb.has(x) && !allowL.has(x)).forEach(x => miss.push('ЗАКРАСКА появилась: ' + x));
  // ПАНЕЛЬ ТОЧЕК (сессия 7)
  if (b.pts && a.pts) {
    const keysOf = (p, withMenus) => new Set([...(p.empty ? p.empty.controls : []), ...(p.filled ? p.filled.controls : []),
      ...(withMenus ? (p.menus || []) : [])].map(c => c.key));
    const ka = keysOf(a.pts, true);
    const allowP = [...((ALLOW['*'] || {}).pts || []), ...((ALLOW[k] || {}).pts || [])].filter(x => x && x.key && x.why);
    [...keysOf(b.pts, true)].forEach(key => {
      if (ka.has(key)) return;
      const r = allowP.find(x => x.key === key);
      if (!r) { miss.push('ПАНЕЛЬ ТОЧЕК: орган «' + key + '»'); return; }
      if (r.to && !ka.has(r.to)) miss.push('ПАНЕЛЬ ТОЧЕК: «' + key + '» переехал в «' + r.to + '», но его нет');
    });
    if (b.pts.filled && a.pts.filled) {
      if (b.pts.filled.rows.marks !== a.pts.filled.rows.marks) miss.push('ПАНЕЛЬ ТОЧЕК: строк точек ' + b.pts.filled.rows.marks + ' → ' + a.pts.filled.rows.marks);
      if (b.pts.filled.rows.areas !== a.pts.filled.rows.areas) miss.push('ПАНЕЛЬ ТОЧЕК: строк площадей ' + b.pts.filled.rows.areas + ' → ' + a.pts.filled.rows.areas);
    }
  }
  // ОШИБКИ
  (a.errors || []).filter(e => !(b.errors || []).includes(e)).forEach(e => miss.push('ОШИБКА ' + e.slice(0, 100)));
  if (miss.length) { problems += miss.length; lines.push(`✗ ${k}: ${miss.length}`); miss.forEach(x => lines.push('    ' + x)); }
  else lines.push(`✓ ${k}`);
}
console.log(lines.join('\n'));
const tips = (M) => Object.values(M).reduce((s, m) => s + (m.tips || 0), 0);
const hints = (M, side) => Object.values(M).reduce((s, m) => s + (m.hints || []).filter(h => !side || h.side === side).length, 0);
console.log(`\nподсказок data-tip на экране: ${tips(B)} → ${tips(A)}; поясняющих строк: Условие ${hints(B, 'L')} → ${hints(A, 'L')}, Ответ ${hints(B, 'R')} → ${hints(A, 'R')}, Вид ${hints(B, 'V')} → ${hints(A, 'V')}`);
console.log(problems ? `\nрасхождений: ${problems}` : '\nрасхождений нет');
process.exit(problems ? 1 : 0);
