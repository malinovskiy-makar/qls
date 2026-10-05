/* СЛОЙ СОСТОЯНИЯ: собрать → сбросить → применить (фаза 2 редизайна calc2).

   Для каждого ключа базового снимка: свежая страница, модель, НАКОПЛЕННЫЙ
   сценарий правок (подряд все шаги первого уровня с эффектом на модель:
   поля, ползунки, списки, сегменты, галочки), слепок A; затем
   collectModelState() → JSON → resetSceneMemory() → другая модель →
   applyModelState(), слепок B. A и B обязаны совпасть: STATE (1e-9), значения
   органов, набор видимых органов, ответ, геометрия. Синонимы tax и tax-adv
   дают ключ taxes.

   node calc2/tests/redesign/state_probe.mjs --base calc2/tests/redesign/baseline [--keys a,b] [--out DIR]
   Код возврата 0 — все ключи сошлись.                                        */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import * as L from './lib.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const BL = arg('base', path.join(HERE, 'baseline'));
const OUT = path.resolve(arg('out', 'reports/calc2_redesign/state'));
const LAYER = arg('layer', 'old');
const JOBS = +arg('jobs', '4');
const layer = await import(path.join(HERE, 'layer_' + LAYER + '.mjs'));
L.configure({ layer, base: BASE, layerName: LAYER });
const KEYS = (arg('keys', '') || '').split(',').filter(Boolean);
const keys = fs.readdirSync(BL).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5)).filter(k => !KEYS.length || KEYS.includes(k));
fs.mkdirSync(OUT, { recursive: true });

const EDIT_KINDS = /^(input:(range|number|text|checkbox)|math-field|select|exact|bounds|edval|switch)$/;
const SKIP = /^#(scene-back|dock-export|tools-toggle|params-toggle|btn-scene-reset|btn-zoom(in|out)|btn-wrench|ac-clear)$|hint-btn|swatch|fold-btn|crow-gear|btn-icon/;
function scenario(rec) {
  return (rec.steps || []).filter(s => s.path.length === 1 && s.effect === 'model' && !SKIP.test(s.path[0])
    && (EDIT_KINDS.test(s.kind) || /seg|tk-|tgl|-btn$|^#(seg|tk|ki|cm|plv|un|mc|mm|tsb|ineq-rd|ac)-/.test(s.path[0])))
    .map(s => (rec.controls || []).find(c => c.key === s.path[0])).filter(Boolean);
}

const browser = await chromium.launch();
const results = {};
const queue = keys.slice();
async function worker() {
  while (queue.length) {
    const key = queue.shift();
    const rec = JSON.parse(fs.readFileSync(path.join(BL, key + '.json'), 'utf8'));
    const out = { key, done: [], skipped: [], issues: [] };
    const f = await L.openKey(browser, key, 'light');
    try {
      for (const c of scenario(rec)) {
        try { await L.act(f.page, c, key); await L.settle(f.page); out.done.push(c.key); }
        catch (e) { out.skipped.push(c.key + ': ' + String(e.message || e).slice(0, 80)); await L.layerClose(f.page); }
      }
      await L.layerClose(f.page);
      await L.settle(f.page);
      const A = await L.observe(f.page);
      const s = await f.page.evaluate(() => JSON.stringify(collectModelState()));
      out.bytes = s.length;
      out.savedKey = JSON.parse(s).key;
      const other = /^m-/.test(key) ? 'sd' : 'm-graph';
      await f.page.evaluate(([o, js]) => { resetSceneMemory(); pickScene(o); }, [other, s]);
      await L.settle(f.page);
      await f.page.evaluate((js) => applyModelState(JSON.parse(js)), s);
      await L.settle(f.page);
      await layer.expand(f.page);
      await L.settle(f.page);
      const B = await L.observe(f.page);
      // Допуск 1e-9, как у инварианта «слепок STATE»: корни ищутся численно.
      const nearV = (a, b) => (typeof a === 'number' && typeof b === 'number') ? Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b))
        : (Array.isArray(a) && Array.isArray(b)) ? a.length === b.length && a.every((x, i) => nearV(x, b[i]))
        : (a && b && typeof a === 'object' && typeof b === 'object') ? Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => nearV(a[k], b[k])) : a === b;
      /* Ленивые кэши расчёта: их заполняет только тот расчёт, которому они
         нужны, и в слепке A может остаться значение от более ранней правки.
         mcFlat — вид кривой MC, его заполняет расчёт прибыли (44-scenes-firm.js:467)
         только при включённой «Цене и прибыли». */
      /* *Sig — подписи входов кэша (costsSig…): применение их гасит, чтобы кэш
         пересчитался, а в подрежимах, которым кэш не нужен, его никто не считает. */
      const LAZY = new Set(['mcFlat']);
      const sd = Object.fromEntries(Object.entries(L.stateDiff(A.state, B.state)).filter(([k]) => !LAZY.has(k) && !/Sig$/.test(k) && !nearV(A.state[k], B.state[k])));
      /* Строки «Построения графиков» нумеруются счётчиком (graph-f-N) и при
         пересборке получают новые номера: ключи органов сравниваем по порядку. */
      const renum = (list) => { const m = new Map(); let n = 0; return list.map(c => { const k = c.key.replace(/graph-f-(\d+)/g, (_, d) => { if (!m.has(d)) m.set(d, ++n); return 'graph-f-#' + m.get(d); }); return Object.assign({}, c, { key: k }); }); };
      A.controls = renum(A.controls); B.controls = renum(B.controls);
      Object.keys(sd).forEach(k => {
        const a = A.state[k], b = B.state[k];
        let where = '';
        if (Array.isArray(a) && Array.isArray(b)) {
          const i = a.findIndex((x, j) => !nearV(x, b[j]));
          if (i >= 0 && a[i] && typeof a[i] === 'object') { const f = Object.keys(Object.assign({}, a[i], b[i] || {})).find(q => !nearV(a[i][q], (b[i] || {})[q])); where = '[' + i + '].' + f + ': ' + String(JSON.stringify(a[i][f])).slice(0, 80) + ' → ' + String(JSON.stringify((b[i] || {})[f])).slice(0, 80); }
        }
        out.issues.push('STATE ' + k + (where ? where : ': ' + String(JSON.stringify(a)).slice(0, 90) + ' → ' + String(JSON.stringify(b)).slice(0, 90)) + (k === 'mcFlat' ? ' (lrOn ' + A.state.lrOn + ', costsMode ' + A.state.costsMode + ')' : ''));
      });
      // Окна сравниваются в единицах модели; размер панели в пикселях — вид, а не
      // модель (поля графика зависят от истории перерисовок, fitMargins).
      const noPx = (w) => JSON.stringify(w, (k, v) => k === 'px' ? undefined : v);
      if (noPx(A.windows) !== noPx(B.windows)) out.issues.push('окна ' + noPx(A.windows).slice(0, 120) + ' → ' + noPx(B.windows).slice(0, 120));
      const cd = L.controlsDiff(A.controls, B.controls);
      cd.revealed.forEach(c => out.issues.push('лишний орган ' + c.key));
      cd.hidden.forEach(k => out.issues.push('пропал орган ' + k));
      Object.entries(cd.props).forEach(([k, p]) => out.issues.push('орган ' + k + ': ' + L.J((A.controls.find(x => x.key === k) || {}).props) + ' → ' + L.J(p)));
      // Синонимы: ключ сцены tax-adv после применения — taxes, это и есть один ключ модели.
      if (/^tax(-adv)?$/.test(key)) out.issues = out.issues.filter(x => !/^STATE sceneKey/.test(x));
      const nz = (t) => String(t).replace(/[\s\u200b]+/g, '');
      (A.answer.blocks || []).forEach(b => {
        const c = (B.answer.blocks || []).find(x => x.id === b.id);
        if (!c) { out.issues.push('ответ: блок ' + b.id + ' пропал'); return; }
        b.rows.forEach((r, i) => { const q = c.rows[i]; if (!q || nz(q.value) !== nz(r.value) || nz(q.label) !== nz(r.label)) out.issues.push('ответ ' + b.id + ' «' + r.label + '» ' + r.value + ' → ' + (q ? '«' + q.label + '» ' + q.value : 'нет')); });
        b.notes.forEach(t => { if (!c.notes.some(x => nz(x) === nz(t))) out.issues.push('ответ ' + b.id + ' пояснение пропало «' + t.slice(0, 70) + '»'); });
        b.warns.forEach(t => { if (!c.warns.some(x => nz(x) === nz(t))) out.issues.push('ответ ' + b.id + ' предупреждение пропало «' + t.slice(0, 70) + '»'); });
      });
      if (nz(A.answer.title) !== nz(B.answer.title)) out.issues.push('заголовок «' + A.answer.title + '» → «' + B.answer.title + '»');
      const e0 = (A.answer.explain || []).map(nz), e1 = (B.answer.explain || []).map(nz);
      if (L.J(e0) !== L.J(e1)) out.issues.push('разбор: ' + (A.answer.explain || []).length + ' → ' + (B.answer.explain || []).length + ' абзацев; первый различающийся «' + ((A.answer.explain || []).find((p, i) => nz(p) !== e1[i]) || '').slice(0, 90) + '» → «' + ((B.answer.explain || []).find((p, i) => nz(p) !== e0[i]) || '').slice(0, 90) + '»');
      // Геометрия — с допуском задания: 0,002 px в пересчёте на единицы модели.
      const tol = (panel) => { const w = A.windows.panels[panel]; return w && w.px ? [0.002 * Math.abs(w.x1 - w.x0) / w.px[0], 0.002 * Math.abs(w.y1 - w.y0) / w.px[1]] : [1e-6, 1e-6]; };
      const near = (p, q) => p.panel === q.panel && p.pts.length === q.pts.length && p.pts.every((a, i) => { const [tx, ty] = tol(p.panel); return Math.abs(a[0] - q.pts[i][0]) <= tx + 1e-9 && Math.abs(a[1] - q.pts[i][1]) <= ty + 1e-9; });
      const used = new Set();
      (A.geometry.paths || []).forEach(p => { const j = (B.geometry.paths || []).findIndex((q, i) => !used.has(i) && near(p, q)); if (j < 0) out.issues.push('геометрия: путь ' + p.panel + ' (' + p.n + ') не найден'); else used.add(j); });
      if ((B.geometry.paths || []).length !== used.size) out.issues.push('геометрия: лишних путей ' + ((B.geometry.paths || []).length - used.size));
      ['lines', 'rects', 'dots'].forEach(k => { if ((A.geometry[k] || []).length !== (B.geometry[k] || []).length) out.issues.push('геометрия: ' + k + ' ' + (A.geometry[k] || []).length + ' → ' + (B.geometry[k] || []).length); });
      if (L.J(A.geometry.keyPoints) !== L.J(B.geometry.keyPoints)) {
        const ka = A.geometry.keyPoints, kb = B.geometry.keyPoints;
        // Порядок — по округлённым координатам: шум 1e-10 менял сортировку слепка.
        const srt = (l) => Array.isArray(l) ? l.slice().sort((p, q) => (Math.round(p[0] * 1e6) - Math.round(q[0] * 1e6)) || (Math.round(p[1] * 1e6) - Math.round(q[1] * 1e6)) || (p[2] < q[2] ? -1 : p[2] > q[2] ? 1 : 0)) : l;
        const kn = (a0, b0) => { const a = srt(a0), b = srt(b0); return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((p, i) => Math.abs(p[0] - b[i][0]) <= 1e-9 * Math.max(1, Math.abs(p[0])) && Math.abs(p[1] - b[i][1]) <= 1e-9 * Math.max(1, Math.abs(p[1])) && p[2] === b[i][2]); };
        Object.keys(ka).forEach(id => { const x = L.J(ka[id]), y = L.J(kb[id]); if (!kn(ka[id], kb[id])) out.issues.push('ключевые точки ' + id + ': ' + x.slice(0, 160) + ' → ' + (y || '').slice(0, 160)); });
      }
      if (/^tax(-adv)?$|^taxes$/.test(key) && out.savedKey !== 'taxes') out.issues.push('ключ ' + out.savedKey + ' вместо taxes');
      out.errors = f.errors.slice();
      out.errors.forEach(e => out.issues.push('ошибка страницы: ' + e));
    } catch (e) { out.issues.push('прибор: ' + String(e.stack || e).slice(0, 300)); }
    await f.ctx.close();
    results[key] = out;
    console.log((out.issues.length ? '✗ ' : '✓ ') + key + `: правок ${out.done.length} (пропущено ${out.skipped.length}), JSON ${out.bytes} байт, ключ ${out.savedKey}` + (out.issues.length ? '\n    ' + out.issues.slice(0, 12).join('\n    ') : ''));
  }
}
await Promise.all(Array.from({ length: Math.min(JOBS, keys.length) }, worker));
await browser.close();
fs.writeFileSync(path.join(OUT, 'state_probe.json'), JSON.stringify(results, null, 1));
const bad = Object.values(results).filter(r => r.issues.length).length;
console.log(`\nсошлось ${keys.length - bad} из ${keys.length}`);
process.exit(bad ? 1 : 0);
