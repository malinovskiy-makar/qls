/* СВЕРКА СНИМКА НОВОГО ЭКРАНА С БАЗОВЫМ (фаза 0 редизайна calc2).

   node calc2/tests/redesign/compare.mjs --base calc2/tests/redesign/baseline --cur <папка> [--keys a,b] [--labels]

   Что сверяется (PROMPT.md, раздел «Проверки»):
     - слепок STATE и окна: старт и каждый шаг без мыши — расхождение ≤ 1e-9;
       после жеста — не дальше одного пикселя шкалы;
     - ответ: каждое значение базового снимка есть в видимом «Ответе» (строка
       ищется по блоку и номеру), тексты пояснений, предупреждений, разбора и
       подсказок равны (кроме переименований О30); подписи сверяются только с
       флагом --labels (до фазы 6 они те же; дальше меняются по замыслу, §9);
     - геометрия: каждой базовой ломаной своя ломаная в той же панели с
       допуском 0,002 px в пересчёте на единицы модели; лишние пути — провал;
     - органы: у каждого органа базового снимка судьба из PARITY (на месте —
       есть в новом перечне по ключу слоя; заменён — есть замена; убран — нет).
   Код возврата 0 — всё сошлось, 1 — есть расхождения (список печатается).  */
import fs from 'fs';
import path from 'path';
import { fateOf } from './fates.mjs';

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const flag = (k) => argv.includes('--' + k);
const BASE = arg('base', 'calc2/tests/redesign/baseline');
const CUR = arg('cur', 'reports/calc2_redesign/current');
const KEYS = (arg('keys', '') || '').split(',').filter(Boolean);
const LABELS = flag('labels');
const MAXSHOW = +arg('show', '40');
const START_ONLY = flag('start-only');   // только старт и органы: для order_probe
/* Снимок нового экрана (--layer new). Набор органов сверяет быстрый паритет
   (parity_quick.mjs: каждый орган старта найден — сам, по замене из
   fates.mjs или в меню «…» карточки — на 1440, 1024 и 390) и шаги сверки:
   они выполняются по старым ключам через слой нового экрана. Здесь при
   --layer new органы сверяются только там, где ключ совпал, — по свойствам
   (значение, состояние): так ловится чужое значение, оставшееся от прошлой
   модели. Подсказки органов строки кривой (кружок цвета, «Имя на графике и
   роль кривой», «Убрать кривую…») заменены карточкой функции (README макета
   6.1): глаз, меню «…» с теми же действиями. */
const LAYER_NEW = arg('layer', 'old') === 'new';

/* Переименования О30: единственная разрешённая правка существующих текстов. */
const O30 = [
  [/«Ключевых значениях»( справа)?/g, '«Ответе»'],
  [/«Ключевые значения»|Ключевые значения/g, '«Ответ»'],
  [/«Объяснении модели»/g, '«Разборе»'],
  [/«Объяснение модели»|Объяснение модели/g, '«Разбор»'],
  [/во «Вводе функций»/g, 'в «Функциях»'],
  [/«Ввод функций»|Ввод функций/g, '«Функции»'],
  [/«Основных параметрах»/g, '«Параметрах»'],
  [/,? (и )?нажмите «Построить[^»]*»/g, ''],
];
const normText = (s) => {
  let t = String(s || '').replace(/[\s   ​]+/g, ' ').trim();
  O30.forEach(([re, to]) => { t = t.replace(re, to); });
  return t;
};
const normNum = (s) => String(s || '').replace(/[\s   ​]+/g, '').replace(/−/g, '-').replace(',', '.');

function near(a, b, tol) {
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) <= tol * Math.max(1, Math.abs(a), Math.abs(b));
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => near(x, b[i], tol));
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a), kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    return ka.every(k => k in b && near(a[k], b[k], tol));
  }
  return false;
}
/* Где именно разошлось: первый путь с расхождением. */
function whereDiff(a, b, tol, p = '') {
  if (near(a, b, tol)) return null;
  if (a && b && typeof a === 'object' && typeof b === 'object' && !Array.isArray(a) && !Array.isArray(b)) {
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
      if (!(k in b)) return p + '/' + k + ': нет в новом';
      if (!(k in a)) return p + '/' + k + ': лишнее в новом';
      const w = whereDiff(a[k], b[k], tol, p + '/' + k); if (w) return w;
    }
  }
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return p + ': длина ' + a.length + ' → ' + b.length;
    for (let i = 0; i < a.length; i++) { const w = whereDiff(a[i], b[i], tol, p + '[' + i + ']'); if (w) return w; }
  }
  return p + ': ' + JSON.stringify(a).slice(0, 80) + ' → ' + JSON.stringify(b).slice(0, 80);
}

/* ── Геометрия ─────────────────────────────────────────────────────── */
function tolOf(windows, panel) {
  const w = windows && windows.panels && windows.panels[panel];
  if (!w || !w.px) return [1e-6, 1e-6];
  return [0.002 * Math.abs(w.x1 - w.x0) / Math.max(1, w.px[0]) + 1e-9, 0.002 * Math.abs(w.y1 - w.y0) / Math.max(1, w.px[1]) + 1e-9];
}
function applyGeomDiff(start, d) {
  if (!d) return start;
  const out = JSON.parse(JSON.stringify(start));
  ['paths', 'lines', 'rects', 'dots'].forEach(k => {
    if (!d[k]) return;
    const del = new Set(d[k].del);
    out[k] = (out[k] || []).filter((_, i) => !del.has(i)).concat(d[k].add || []);
  });
  if (d.keyPoints) out.keyPoints = d.keyPoints;
  return out;
}
function samePts(a, b, tx, ty) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (Math.abs(a[i][0] - b[i][0]) > tx || Math.abs(a[i][1] - b[i][1]) > ty) return false;
  }
  return true;
}
/* ── Геометрия при РАЗНОМ холсте ───────────────────────────────────────
   Новый экран рисует холст другого размера, и одна и та же кривая выходит
   другими отсчётами (шаг выборки — от ширины в пикселях), линии за краем окна
   продлеваются на другую длину, а метки-засечки имеют размер в пикселях.
   Поэтому при разных px панели картинка сверяется как картинка: внутри окна
   каждая вершина одного пути лежит не дальше 1,5 px от ломаной другого (и
   наоборот), отрезки сравниваются после обрезки окном, кружки ручек (r ≥ 7:
   на новом экране они служебные, data-service) не сравниваются. При равном
   холсте сверка прежняя, строгая. Числа (STATE, табло, ключевые точки)
   сверяются точно в обоих случаях. */
const PIX_TOL = 1.5;
function sameCanvas(w0, w1) {
  const a = (w0 && w0.panels) || {}, b = (w1 && w1.panels) || {};
  return Object.keys(a).every(k => !a[k].px || (b[k] && b[k].px && a[k].px[0] === b[k].px[0] && a[k].px[1] === b[k].px[1]));
}
function unitsOf(w0, w1, panel) {
  const f = (w) => { const q = w && w.panels && w.panels[panel]; return q && q.px ? [Math.abs(q.x1 - q.x0) / Math.max(1, q.px[0]), Math.abs(q.y1 - q.y0) / Math.max(1, q.px[1])] : null; };
  const a = f(w0), b = f(w1);
  if (!a && !b) return null;
  const q = (w0 && w0.panels && w0.panels[panel]) || (w1 && w1.panels && w1.panels[panel]);
  return { ux: Math.max(a ? a[0] : 0, b ? b[0] : 0) || 1e-9, uy: Math.max(a ? a[1] : 0, b ? b[1] : 0) || 1e-9,
           x0: Math.min(q.x0, q.x1), x1: Math.max(q.x0, q.x1), y0: Math.min(q.y0, q.y1), y1: Math.max(q.y0, q.y1) };
}
function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy;
  const t = L ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
function polyNear(A, B, u) {
  // Нормированные пиксели: (x / ux, y / uy). Точки за окном (с запасом 2 px) не сверяются.
  const inW = ([x, y]) => x >= u.x0 - 2 * u.ux && x <= u.x1 + 2 * u.ux && y >= u.y0 - 2 * u.uy && y <= u.y1 + 2 * u.uy;
  const b = B.filter(v => isFinite(v[0]) && isFinite(v[1])).map(([x, y]) => [x / u.ux, y / u.uy]);
  for (const a of A) {
    if (!isFinite(a[0]) || !isFinite(a[1]) || !inW(a)) continue;
    const x = a[0] / u.ux, y = a[1] / u.uy;
    let best = Infinity;
    if (b.length === 1) best = Math.hypot(x - b[0][0], y - b[0][1]);
    for (let i = 1; i < b.length && best > PIX_TOL; i++) best = Math.min(best, segDist(x, y, b[i - 1][0], b[i - 1][1], b[i][0], b[i][1]));
    if (best > PIX_TOL) return false;
  }
  return true;
}
function clipSeg(a, b, u) {
  // Лианг — Барски в единицах модели; null — отрезок целиком за окном.
  let t0 = 0, t1 = 1;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const pq = [[-dx, a[0] - u.x0], [dx, u.x1 - a[0]], [-dy, a[1] - u.y0], [dy, u.y1 - a[1]]];
  for (const [pp, qq] of pq) {
    if (pp === 0) { if (qq < 0) return null; continue; }
    const r = qq / pp;
    if (pp < 0) { if (r > t1) return null; if (r > t0) t0 = r; } else { if (r < t0) return null; if (r < t1) t1 = r; }
  }
  return [[a[0] + t0 * dx, a[1] + t0 * dy], [a[0] + t1 * dx, a[1] + t1 * dy]];
}
function geomMatchLoose(g0, g1, w0, w1, issues, where) {
  let n = 0;
  const used = new Set();
  (g0.paths || []).forEach(p => {
    n++;
    const u = unitsOf(w0, w1, p.panel);
    if (!u) return;
    const j = (g1.paths || []).findIndex((q, i) => !used.has(i) && q.panel === p.panel && q.filled === p.filled && polyNear(p.pts, q.pts, u) && polyNear(q.pts, p.pts, u));
    if (j < 0) issues.push(where + ': путь панели ' + p.panel + ' (' + p.n + ' точек, начало ' + JSON.stringify(p.pts[0]) + ') не найден');
    else used.add(j);
  });
  (g1.paths || []).forEach((q, i) => { if (!used.has(i)) issues.push(where + ': лишний путь панели ' + q.panel + ' (' + q.n + ' точек)'); });
  ['lines', 'rects', 'dots'].forEach(k => {
    const usedK = new Set();
    const prep = (e) => {
      const u = unitsOf(w0, w1, e.panel);
      if (!u) return null;
      if (k === 'dots') {
        if (e.r >= 7) return null;                       // кружок ручки
        const [x, y] = e.c;
        return (x < u.x0 - 2 * u.ux || x > u.x1 + 2 * u.ux || y < u.y0 - 2 * u.uy || y > u.y1 + 2 * u.uy) ? null : { u, pts: [e.c] };
      }
      const c = clipSeg(e.a, e.b, u);
      if (!c) return null;
      // Метка-засечка короче 12 px — размер в пикселях, а не в модели.
      if (Math.hypot((c[1][0] - c[0][0]) / u.ux, (c[1][1] - c[0][1]) / u.uy) < 12) return null;
      return { u, pts: c };
    };
    const near2 = (A, B, u) => A.length === 1
      ? Math.hypot((A[0][0] - B[0][0]) / u.ux, (A[0][1] - B[0][1]) / u.uy) <= PIX_TOL
      : polyNear(A, B, u) && polyNear(B, A, u);
    const cur = (g1[k] || []).map(prep);
    (g0[k] || []).forEach(e => {
      const a = prep(e);
      if (!a) return;
      n++;
      const j = cur.findIndex((q, i) => q && !usedK.has(i) && (g1[k][i].panel === e.panel) && near2(a.pts, q.pts, a.u));
      if (j < 0) issues.push(where + ': ' + k + ' ' + JSON.stringify(k === 'dots' ? [e.c] : [e.a, e.b]) + ' не найден');
      else usedK.add(j);
    });
    cur.forEach((q, i) => { if (q && !usedK.has(i)) issues.push(where + ': лишний ' + k + ' ' + g1[k][i].panel); });
  });
  return n + keyPointsMatch(g0, g1, issues, where);
}
function keyPointsMatch(g0, g1, issues, where) {
  // Ключевые точки — набор: порядок по округлённым координатам (шум 1e-10 его менял).
  const srt = (o) => Object.fromEntries(Object.entries(o || {}).map(([id, l]) => [id, Array.isArray(l) ? l.slice().sort((p, q) =>
    (Math.round(p[0] * 1e6) - Math.round(q[0] * 1e6)) || (Math.round(p[1] * 1e6) - Math.round(q[1] * 1e6)) || String(p[2]).localeCompare(String(q[2]))) : l]));
  const k0 = srt(g0.keyPoints), k1 = srt(g1.keyPoints);
  if (!near(k0 || {}, k1 || {}, 1e-9)) issues.push(where + ': ключевые точки: ' + whereDiff(k0 || {}, k1 || {}, 1e-9));
  return 1;
}
function geomMatch(g0, g1, win0, issues, where, win1) {
  if (win1 && !sameCanvas(win0, win1)) return geomMatchLoose(g0, g1, win0, win1, issues, where);
  let n = 0;
  const used = new Set();
  (g0.paths || []).forEach(p => {
    n++;
    const [tx, ty] = tolOf(win0, p.panel);
    const j = (g1.paths || []).findIndex((q, i) => !used.has('p' + i) && q.panel === p.panel && q.filled === p.filled && samePts(p.pts, q.pts, tx, ty));
    if (j < 0) issues.push(where + ': путь панели ' + p.panel + ' (' + p.n + ' точек, начало ' + JSON.stringify(p.pts[0]) + ') не найден');
    else used.add('p' + j);
  });
  (g1.paths || []).forEach((q, i) => { if (!used.has('p' + i)) issues.push(where + ': лишний путь панели ' + q.panel + ' (' + q.n + ' точек)'); });
  ['lines', 'rects', 'dots'].forEach(k => {
    const usedK = new Set();
    (g0[k] || []).forEach(e => {
      n++;
      const [tx, ty] = tolOf(win0, e.panel);
      const pts = (x) => k === 'dots' ? [x.c] : [x.a, x.b];
      const j = (g1[k] || []).findIndex((q, i) => !usedK.has(i) && q.panel === e.panel && samePts(pts(e), pts(q), tx, ty));
      if (j < 0) issues.push(where + ': ' + k + ' ' + JSON.stringify(pts(e)) + ' не найден');
      else usedK.add(j);
    });
    (g1[k] || []).forEach((q, i) => { if (!usedK.has(i)) issues.push(where + ': лишний ' + k + ' ' + q.panel); });
  });
  n++;
  // Ключевые точки — набор: порядок по округлённым координатам (шум 1e-10 его менял).
  const srt = (o) => Object.fromEntries(Object.entries(o || {}).map(([id, l]) => [id, Array.isArray(l) ? l.slice().sort((p, q) =>
    (Math.round(p[0] * 1e6) - Math.round(q[0] * 1e6)) || (Math.round(p[1] * 1e6) - Math.round(q[1] * 1e6)) || String(p[2]).localeCompare(String(q[2]))) : l]));
  g0 = Object.assign({}, g0, { keyPoints: srt(g0.keyPoints) }); g1 = Object.assign({}, g1, { keyPoints: srt(g1.keyPoints) });
  if (!near(g0.keyPoints || {}, g1.keyPoints || {}, 1e-9)) issues.push(where + ': ключевые точки: ' + whereDiff(g0.keyPoints || {}, g1.keyPoints || {}, 1e-9));
  return n;
}

/* ── Ответ ─────────────────────────────────────────────────────────── */
/* Разбор, исправленный в фазе 1 (журнал, «Принято без вопроса», п. 12): на
   старом экране пять моделей показывали разбор своей СЕМЬИ (ключ кэша
   moveExplanations был общий на семью), хотя в реестре SCENE_EXPLAIN у каждой
   свой текст. Новый экран показывает текст самой модели. Абзацы разбора у
   этих пяти ключей не сверяются, а сверка печатает строку «исправлено». */
const EXPLAIN_FIXED = { isoquant: 'costs', plants: 'costs', prod: 'costs', 'mono-d3': 'mono', 'tax-adv': 'tax' };
let CUR_KEY = '';
let REPLACED_TIPS = new Set();
const noPx = (w) => JSON.parse(JSON.stringify(w || {}, (k, v) => k === 'px' ? undefined : v));
const RESET_NOTES = [];
/* Тексты вариантов, исправленные редизайном (боевой дефект из списка 13:
   в выпадающих списках печаталось «UUU = …» и «DDD = …» вместо «U», «D»).
   Значение органа сверяется строго; заменяется только этот текст. */
const fixedProps = (p) => (p && Array.isArray(p.options))
  ? Object.assign({}, p, { options: p.options.map(o => String(o).replace(/UUU/g, 'U').replace(/DDD/g, 'D')) }) : p;
function answerMatch(a0, a1, issues, where) {
  let n = 0;
  const b1 = new Map((a1.blocks || []).map(b => [b.id, b]));
  (a0.blocks || []).forEach(b => {
    const c = b1.get(b.id);
    if (!c) { issues.push(where + ': блок ' + b.id + ' не показан'); n++; return; }
    b.rows.forEach(r => {
      n++;
      const q = c.rows.find(x => String(x.i) === String(r.i));
      if (!q) { issues.push(where + ': ' + b.id + ' строка ' + r.i + ' «' + r.label + '» нет'); return; }
      if (normNum(q.value) !== normNum(r.value) && !(q.raw != null && normNum(q.raw) === normNum(r.value))) issues.push(where + ': ' + b.id + ' «' + r.label + '» ' + r.value + ' → ' + q.value);
      if (LABELS && normText(q.label) !== normText(r.label)) issues.push(where + ': ' + b.id + ' подпись «' + r.label + '» → «' + q.label + '»');
    });
    n++; if (JSON.stringify(b.tables.map(t => t.map(r => r.map(normText)))) !== JSON.stringify((c.tables || []).map(t => t.map(r => r.map(normText))))) issues.push(where + ': ' + b.id + ' таблица разошлась');
    ['notes', 'warns'].forEach(k => {
      n++;
      const x0 = (b[k] || []).map(normText), x1 = (c[k] || []).map(normText);
      x0.forEach(t => { if (!x1.includes(t)) issues.push(where + ': ' + b.id + ' ' + k + ' пропало: «' + t.slice(0, 70) + '»'); });
    });
    n++; if (JSON.stringify((b.final || []).map(f => [f.tex, f.copy])) !== JSON.stringify((c.final || []).map(f => [f.tex, f.copy]))) issues.push(where + ': ' + b.id + ' итоговая функция разошлась');
  });
  n++; if (normText(a0.title) !== normText(a1.title)) issues.push(where + ': заголовок группы «' + a0.title + '» → «' + a1.title + '»');
  const e1 = (a1.explain || []).map(normText);
  if (EXPLAIN_FIXED[CUR_KEY]) {
    n++; if (!e1.length) issues.push(where + ': разбор пуст');
  } else {
    (a0.explain || []).forEach(p => { n++; if (!e1.includes(normText(p))) issues.push(where + ': абзац разбора пропал: «' + p.slice(0, 70) + '»'); });
  }
  const t1 = new Set((a1.tips || []).map(normText));
  // Подсказки органов, заменённых или убранных по закрытому списку, ушли вместе
  // с органом («Настройки координатной плоскости» у гаечного ключа и т. п.).
  (a0.tips || []).forEach(t => { n++; if (!t1.has(normText(t)) && !REPLACED_TIPS.has(normText(t))) issues.push(where + ': подсказка пропала: «' + t.slice(0, 70) + '»'); });
  return n;
}
function answerAfter(start, d) {
  if (!d) return start;
  const a = JSON.parse(JSON.stringify(start));
  if (d.title !== undefined) a.title = d.title;
  if (d.explain) a.explain = d.explain;
  const m = new Map((a.blocks || []).map(b => [b.id, b]));
  (d.blocks || []).forEach(b => m.set(b.id, b));
  (d.blocksGone || []).forEach(id => m.delete(id));
  a.blocks = d.order ? d.order.map(id => m.get(id)).filter(Boolean) : [...m.values()];
  if (d.tips) { const s = new Set(a.tips || []); d.tips.del.forEach(x => s.delete(x)); d.tips.add.forEach(x => s.add(x)); a.tips = [...s].sort(); }
  return a;
}
/* Ключи состояния, которые описывают РАСКЛАДКУ, а не модель: выбранный угол
   легенды (legendSpot) и место подписей касательной (tanTop, tanBot). Их
   выбирает отрисовка по свободному месту холста, а холст на новом экране
   другого размера и с другими соседями. Окно модели сверяется строго. */
/* crosses — кэш нарисованных пересечений: то, что человек видит, сверяется
   строже, ключевыми точками геометрии (keyTargets). Сам кэш старый код
   держал непоследовательно: в «Производстве» смена сетки в гаечном ключе
   стирала пересечение в начале координат, хотя на холсте оно оставалось. */
const VIEW_KEYS = new Set(['legendSpot', 'tanTop', 'tanBot', 'crosses']);
function stateAfter(start, d) {
  const s = Object.assign({}, start);
  Object.entries(d || {}).forEach(([k, v]) => { if (v === '∅') delete s[k]; else s[k] = v; });
  VIEW_KEYS.forEach(k => delete s[k]);
  return s;
}

/* ── Обход ─────────────────────────────────────────────────────────── */
const files = fs.readdirSync(BASE).filter(f => f.endsWith('.json')).map(f => f.replace(/\.json$/, '')).filter(k => !KEYS.length || KEYS.includes(k)).sort();
let total = 0, bad = 0;
const report = {};
for (const key of files) {
  CUR_KEY = key;
  const issues = [];
  let n = 0;
  const b = JSON.parse(fs.readFileSync(path.join(BASE, key + '.json'), 'utf8'));
  REPLACED_TIPS = new Set((b.controls || []).filter(c => fateOf(c.key).fate !== 'на месте' || (LAYER_NEW && /^#curve-list>/.test(c.key))).map(c => normText(c.label)));
  const cp = path.join(CUR, key + '.json');
  if (!fs.existsSync(cp)) { report[key] = { n: 1, issues: ['нет снимка нового экрана'] }; total++; bad++; continue; }
  const c = JSON.parse(fs.readFileSync(cp, 'utf8'));
  if (c.fatal) issues.push('прибор упал: ' + c.fatal.slice(0, 200));
  if (!c.start) { report[key] = { n: 1, issues: issues.length ? issues : ['снимок без старта'] }; total++; bad += report[key].issues.length; continue; }
  // Ошибки страницы, которые были и на старом экране (тот же текст), — не
  // расхождение: это поведение старого кода (дефект «Сложения» с NaN в пути).
  const errKey = (e) => String(e).replace(/^.*?(console|pageerror): /, '$1: ').replace(/[\d.]+/g, '#');
  const oldErr = new Set((b.errors || []).map(errKey));
  (c.errors || []).forEach(e => { if (!oldErr.has(errKey(e))) issues.push('ошибка страницы: ' + e); });
  // Старт. Место легенды (legendSpot) — кэш раскладки: когда страница не
  // свежая (обход подряд, order_probe), оно зависит от того, что было нарисовано
  // раньше. Модель оно не описывает; в --start-only не сверяется.
  if (START_ONLY) { delete b.start.state.legendSpot; delete c.start.state.legendSpot; }
  n++; const ws = whereDiff(stateAfter(b.start.state, {}), stateAfter(c.start.state, {}), 1e-9); if (ws) issues.push('старт STATE' + ws);
  n++; const ww = whereDiff(noPx(b.start.windows), noPx(c.start.windows), 1e-9); if (ww) issues.push('старт окна' + ww);
  n += answerMatch(b.start.answer, c.start.answer, issues, 'старт');
  n += geomMatch(b.start.geometry, c.start.geometry, b.start.windows, issues, 'старт', c.start.windows);
  // Органы старта: тот же набор ключей и те же свойства.
  if (START_ONLY && c.controls) {
    const m1 = new Map(c.controls.map(x => [x.key, x]));
    (b.controls || []).forEach(x => {
      const y = m1.get(x.key);
      if (LAYER_NEW && (!y || y.kind !== x.kind)) return;
      n++;
      if (!y) issues.push('орган ' + x.key + ' не виден');
      else if (JSON.stringify(fixedProps(x.props)) !== JSON.stringify(y.props)) issues.push('орган ' + x.key + ': ' + JSON.stringify(x.props) + ' → ' + JSON.stringify(y.props));
      else if (JSON.stringify(x.props) !== JSON.stringify(y.props)) RESET_NOTES.push(CUR_KEY + ': ' + x.key + ' — исправлен текст вариантов («UUU», «DDD» → «U», «D»; боевой дефект), значение то же');
    });
    if (!LAYER_NEW) c.controls.forEach(y => { if (!(b.controls || []).some(x => x.key === y.key)) issues.push('лишний орган ' + y.key); });
  }
  // Шаги.
  const cs = new Map((c.steps || []).map(s => [s.path.join(' → '), s]));
  if (!START_ONLY) (b.steps || []).forEach(s0 => {
    let s = s0;
    const id = s.path.join(' → ');
    const t = cs.get(id);
    n++;
    if (!t) { issues.push('шаг ' + id + ': не выполнен'); return; }
    if (t.error) { issues.push('шаг ' + id + ': ' + t.error); return; }
    if (s.effect !== 'model' && s.effectVsOpener !== 'model') return;   // вид, а не модель: судьба органа решается в PARITY
    /* Органы, заменённые по закрытому списку видом рабочего места (в — колонки,
       г — окно выбора, д — карточки, к — кнопки экспорта): их шаг меняет
       раскладку, а не модель, и его паритет — судьба в PARITY.md. */
    if (s.path.some(k => { const f = fateOf(k); return f.fate !== 'на месте' && /^[вгдк]$/.test(f.letter); })) return;
    /* «Сбросить» (пункт (и), COVERAGE О4) возвращает СТАРТ модели. Старый
       «Вернуть исходный вид» в части моделей давал не старт (например, в
       «Торговле по ценам» терял пересечение и путь второй панели: в обходе
       сбрасывалась память, а маршрут модели не повторялся). Шаг сверяется
       со стартом базового снимка, расхождение старого кода печатается. */
    if (s.path[s.path.length - 1] === '#btn-scene-reset') {
      const was = whereDiff(stateAfter(b.start.state, s.state), stateAfter(b.start.state, {}), 1e-9);
      if (was) RESET_NOTES.push(CUR_KEY + ': старый «Вернуть исходный вид» давал не старт (STATE' + was.slice(0, 80) + '), «Сбросить» сверен со стартом');
      s = { path: s.path, effect: s.effect };
    }
    const st0 = stateAfter(b.start.state, s.state), st1 = stateAfter(c.start.state, t.state);
    n++; const d1 = whereDiff(st0, st1, 1e-9); if (d1) issues.push('шаг ' + id + ' STATE' + d1);
    /* Размер панели в пикселях (px) — вид, а не модель: поля графика зависят
       от ширины подписей и истории перерисовок (fitMargins), как и в приборе
       слоя состояния. Окно в единицах модели сверяется строго. */
    n++; const d2 = whereDiff(noPx(s.windows || b.start.windows), noPx(t.windows || c.start.windows), 1e-9); if (d2) issues.push('шаг ' + id + ' окна' + d2);
    n += answerMatch(answerAfter(b.start.answer, s.answer), answerAfter(c.start.answer, t.answer), issues, 'шаг ' + id);
    n += geomMatch(applyGeomDiff(b.start.geometry, s.geometry), applyGeomDiff(c.start.geometry, t.geometry), s.windows || b.start.windows, issues, 'шаг ' + id, t.windows || c.start.windows);
  });
  // Жесты: значение из пикселя — допуск в один пиксель шкалы.
  if (!START_ONLY) (b.gestures || []).forEach((g, i) => {
    n++;
    const h = (c.gestures || []).find(x => x.kind === g.kind && (x.handle || '') === (g.handle || ''));
    if (!h) { issues.push('жест ' + g.kind + ' ' + (g.handle || '') + ': не выполнен'); return; }
    if (g.kind === 'dblclick') return;
    const px = Math.max(...Object.values(b.start.windows.panels || {}).map(w => w.px ? Math.max(Math.abs(w.x1 - w.x0) / w.px[0], Math.abs(w.y1 - w.y0) / w.px[1]) : 0), 1e-9);
    const s0 = stateAfter(b.start.state, g.state), s1 = stateAfter(c.start.state, h.state);
    const changed = Object.keys(g.state || {});
    changed.forEach(k => {
      const w = whereDiff(s0[k], s1[k], 0, '');
      if (!w) return;
      if (!nearAbs(s0[k], s1[k], px * 1.0001)) issues.push('жест ' + g.kind + ' ' + (g.handle || '') + ' ' + k + w);
    });
  });
  // Печать: холст и строки чисел на листе.
  if (!START_ONLY) ['light', 'dark'].forEach(th => {
    const p0 = b.print && b.print[th], p1 = c.print && c.print[th];
    if (!p0) return;
    n++;
    if (!p1 || !p1.chart || !p1.chart[2]) { issues.push('печать ' + th + ': холста на листе нет'); return; }
    const nums = (p0.lines || []).filter(l => /\d/.test(l) && /[=≈]/.test(l)).map(normText);
    const got = new Set((p1.lines || []).map(normText));
    nums.forEach(l => { n++; if (!got.has(l)) issues.push('печать ' + th + ': строки «' + l.slice(0, 60) + '» нет'); });
  });
  total += n; bad += issues.length;
  report[key] = { n, issues };
}
function nearAbs(a, b, tol) {
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) <= tol;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => nearAbs(x, b[i], tol));
  if (a && b && typeof a === 'object' && typeof b === 'object') return Object.keys(a).every(k => nearAbs(a[k], b[k], tol));
  return a === b;
}
fs.mkdirSync(CUR, { recursive: true });
fs.writeFileSync(path.join(CUR, '_compare.json'), JSON.stringify(report, null, 1));
let okKeys = 0;
Object.entries(report).forEach(([k, r]) => {
  if (!r.issues.length) okKeys++;
  console.log((r.issues.length ? '✗ ' : '✓ ') + k + ': проверок ' + r.n + ', расхождений ' + r.issues.length);
  r.issues.slice(0, MAXSHOW).forEach(x => console.log('    ' + x));
  if (EXPLAIN_FIXED[k]) console.log('    разбор: исправлено в фазе 1 — свой текст модели вместо разбора семьи «' + EXPLAIN_FIXED[k] + '»');
});
RESET_NOTES.forEach(x => console.log('  ' + x));
console.log(`\nключей ${okKeys} из ${files.length} без расхождений; проверок ${total}, расхождений ${bad}`);
process.exit(bad ? 1 : 0);
