/* Аудит выгрузки .tex по набору состояний (прибор tex_audit).

   По каждому состоянию из states.json: довести модель до состояния, бумажный
   прогон, опись, сборка, дверь buildTex; счётчики кривых и областей (SPEC.md,
   раздел 12), «выгрузка ничего не трогает» (состояние, холст, «Отменить»,
   localStorage, события), повторная сборка, время, проверка текста без TeX.

   TEX_ENGINE=proto|site (lib.mjs) — что мерить.
   JOBS=3            потоков (по умолчанию 2)
   KEYS=taxes,mono   только эти модели;  IDS=taxes#start,sd@nl — только эти состояния
   SRC=start,recipe  только эти источники (start, step, gesture, recipe)
   SHOTS=all|start|recipe|none   снимать холст на листе (для контактных листов); по умолчанию start,recipe
   TASK_MS=90000     сторож времени на состояние
   OUT=папка         по умолчанию reports/calc2_tex/audit
   Прерванный прогон продолжается с места: готовые состояния читаются из журнала.

   Пишет в OUT: audit.jsonl (строка на состояние), tex/<отпечаток>.tex,
   shots/<состояние>.paper.png. Сводку печатает summary.mjs. */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { HERE, OUT_ROOT, ENGINE, openPage, reach, auditState, loadStates, loadRecipes, safeName } from './lib.mjs';
import { lintTex } from './lint.mjs';

const OUT = process.env.OUT || path.join(OUT_ROOT, 'audit');
const JOBS = +(process.env.JOBS || 2);
const TASK_MS = +(process.env.TASK_MS || 90000);
const set = (v) => (v ? new Set(v.split(',').map(s => s.trim()).filter(Boolean)) : null);
const KEYS = set(process.env.KEYS), IDS = set(process.env.IDS), SRC = set(process.env.SRC);
const SHOTS = set(process.env.SHOTS || 'start,recipe');
fs.mkdirSync(path.join(OUT, 'tex'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'shots'), { recursive: true });
const logFile = path.join(OUT, 'audit.jsonl');
const done = new Set();
if (fs.existsSync(logFile)) fs.readFileSync(logFile, 'utf8').split('\n').filter(Boolean).forEach(l => { try { done.add(JSON.parse(l).id); } catch (e) {} });
const excl = JSON.parse(fs.readFileSync(path.join(HERE, 'exclusions.json'), 'utf8'));
const recipes = loadRecipes();
const all = loadStates().filter(s => (!KEYS || KEYS.has(s.key)) && (!IDS || IDS.has(s.id)) && (!SRC || SRC.has(s.src)));
const todo = all.filter(s => !done.has(s.id));
console.log('движок', ENGINE, '| состояний', all.length, '| осталось', todo.length, '| исключено именно', all.filter(s => excl[s.id]).length);

const browser = await chromium.launch();
let idx = 0, okN = 0, errN = 0;
const t0 = Date.now();
async function worker() {
  let rp = null;                                   // страница для стартов и рецептов, переиспользуется
  while (idx < todo.length) {
    const st = todo[idx++];
    const rec = { id: st.id, key: st.key, src: st.src, engine: ENGINE };
    if (excl[st.id]) {
      rec.excluded = excl[st.id];
      fs.appendFileSync(logFile, JSON.stringify(rec) + '\n');
      continue;
    }
    let f = null, timer = null;
    const hold = {};
    const guard = new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('страница не ответила за ' + TASK_MS / 1000 + ' с')), TASK_MS); });
    try {
      await Promise.race([guard, (async () => {
        if ((st.src === 'start' || st.src === 'recipe') && !rp) rp = await openPage(browser, {});
        const e0 = (st.src === 'start' || st.src === 'recipe') ? rp.errors.length : 0;   // ошибки страницы — только этого состояния
        const r0 = await reach(browser, st, (st.src === 'start' || st.src === 'recipe') ? rp : null, recipes, hold);
        f = r0.f; rec.action = r0.action;
        const shot = SHOTS && (SHOTS.has('all') || SHOTS.has(st.src));
        const r = await auditState(f.page, { title: st.title || '', label: st.label || '', shot });
        const sha = crypto.createHash('sha1').update(r.tex).digest('hex').slice(0, 12);
        const p = path.join(OUT, 'tex', sha + '.tex');
        if (!fs.existsSync(p)) fs.writeFileSync(p, r.tex);
        if (r.shot) fs.writeFileSync(path.join(OUT, 'shots', safeName(st.id) + '.paper.png'), r.shot);
        const lint = lintTex(r.tex);
        Object.assign(rec, {
          sha, len: r.tex.length, stats: r.stats, warn: r.warn, size: r.size, ms: r.ms,
          doorSame: r.doorSame, repeatSame: r.repeatSame, stateDiff: r.stateDiff, dom: r.dom,
          events: r.events, hist: r.hist, self: r.self, seen: r.seen,
          lint: lint.ok ? null : lint.problems.slice(0, 6), formulas: r.formulas, labels: r.labels, fallback: r.fallback,
          title: st.title || undefined,
        });
        const errs = f.errors.slice(e0);
        if (errs.length) rec.pageErrors = [...new Set(errs)].slice(0, 5);
        okN++;
      })()]);
    } catch (e) {
      rec.err = String(e.message || e).slice(0, 400); errN++;
      // сломанная или зависшая страница рецептов — заводим новую
      if (rp && (!f || f === rp)) { await Promise.race([rp.ctx.close().catch(() => {}), new Promise(r => setTimeout(r, 5000))]); rp = null; }
    }
    clearTimeout(timer);
    if (!f && hold.f) f = hold.f;
    if (f && f !== rp) await Promise.race([f.ctx.close().catch(() => {}), new Promise(r => setTimeout(r, 5000))]);
    fs.appendFileSync(logFile, JSON.stringify(rec) + '\n');
    const n = okN + errN;
    if (n % 25 === 0) console.log(n + '/' + todo.length, 'ок', okN, 'сбоев', errN, Math.round((Date.now() - t0) / 1000) + ' с');
  }
  if (rp) await rp.ctx.close().catch(() => {});
}
await Promise.all(Array.from({ length: JOBS }, worker));
console.log('готово: ок', okN, 'сбоев', errN, Math.round((Date.now() - t0) / 1000) + ' с');
await browser.close();
process.exit(errN ? 1 : 0);
