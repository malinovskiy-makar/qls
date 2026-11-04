/* Широкий прогон: 44 старта и шаги базового снимка редизайна, меняющие холст
   (calc2/tests/redesign/baseline/*.json). Каждый шаг — от свежей загрузки
   страницы, теми же действиями, что в snapshot.mjs, затем сборка файла.

   node replay.mjs                   все задачи (823 на e165aff), 2 потока
   JOBS=3 KEYS=taxes,mono node replay.mjs
   LIMIT=5 node replay.mjs           не больше пяти шагов на модель
   Прерванный прогон продолжается с места: готовые задачи читаются из журнала.

   Пишет в OUT: replay.jsonl (строка на задачу: счётчики, отпечаток файла,
   «состояние то же», «повтор тот же», время сборки) и tex/<отпечаток>.tex.
   Сводку печатает replay_sum.py. */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { ROOT, BASE, PROTO, OUT_ROOT } from './lib.mjs';

const RD = path.join(ROOT, 'calc2/tests/redesign');
const L = await import(path.join(RD, 'lib.mjs'));
const layer = await import(path.join(RD, 'layer_new.mjs'));
const OUT = process.env.OUT || path.join(OUT_ROOT, 'replay');
const JOBS = +(process.env.JOBS || 2);
const ONLY = process.env.KEYS ? new Set(process.env.KEYS.split(',')) : null;
const LIMIT = +(process.env.LIMIT || 0);
const TASK_MS = +(process.env.TASK_MS || 90000);
L.configure({ layer, base: BASE, layerName: 'new', w: 1440, h: 760 });
fs.mkdirSync(path.join(OUT, 'tex'), { recursive: true });
const logFile = path.join(OUT, 'replay.jsonl');
const done = new Set();
if (fs.existsSync(logFile)) fs.readFileSync(logFile, 'utf8').split('\n').filter(Boolean).forEach(l => { try { done.add(JSON.parse(l).id); } catch (e) {} });

function tasksOf() {
  const tasks = [];
  for (const f of fs.readdirSync(path.join(RD, 'baseline')).filter(x => x.endsWith('.json')).sort()) {
    const bl = JSON.parse(fs.readFileSync(path.join(RD, 'baseline', f), 'utf8'));
    if (ONLY && !ONLY.has(bl.key)) continue;
    const desc = (k) => (bl.controls || []).find(c => c.key === k) || (bl.inventory && bl.inventory[k] ? { key: k, ...bl.inventory[k] } : null);
    tasks.push({ id: bl.key + '#start', key: bl.key, path: [], ctl: [] });
    const seen = new Set(); let n = 0;
    (bl.steps || []).forEach((st, i) => {
      if (!st.geometry) return;                        // шаг холст не менял
      const h = crypto.createHash('sha1').update(JSON.stringify([st.geometry, st.windows || null])).digest('hex');
      if (seen.has(h)) return; seen.add(h);            // такой холст уже есть
      const ctl = st.path.map(desc);
      if (ctl.some(x => !x)) return;
      if (LIMIT && n >= LIMIT) return; n++;
      tasks.push({ id: bl.key + '#' + i, key: bl.key, path: st.path, ctl });
    });
  }
  return tasks;
}
const tasks = tasksOf();
const todo = tasks.filter(t => !done.has(t.id));
console.log('задач', tasks.length, 'осталось', todo.length);
const browser = await chromium.launch();
let idx = 0, okN = 0, errN = 0;
const t0 = Date.now();
async function worker() {
  while (idx < todo.length) {
    const t = todo[idx++];
    const rec = { id: t.id, key: t.key, path: t.path };
    let f = null;
    /* Сторож времени на задачу: страница, ушедшая в долгий расчёт, не должна
       останавливать весь прогон (замер: mono-kink, шаг 60 — кусочная функция
       в третьем поле спроса — в песочнице не заканчивается за десять минут). Контекст закрывается, задача идёт в сбои. */
    let timer = null;
    const guard = new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('страница не ответила за ' + TASK_MS / 1000 + ' с')), TASK_MS); });
    try {
     await Promise.race([guard, (async () => {
      f = await L.openKey(browser, t.key, 'light');
      const acts = [];
      for (const c of t.ctl) { acts.push(await L.act(f.page, c, t.key)); await L.settle(f.page); }
      rec.action = acts.join(' ; ');
      await f.page.addScriptTag({ path: PROTO });
      const r = await f.page.evaluate(() => {
        try {
          const flat = (o, pre, out) => { if (o && typeof o === 'object') { Object.keys(o).forEach(k => flat(o[k], pre ? pre + '.' + k : k, out)); } else out[pre] = o; return out; };
          redrawAll(); redrawAll();              // экран в неподвижной точке: поля холста досчитываются вторым кадром
          const s0 = flat(collectModelState(), '', {});
          const t0 = performance.now();
          const a = TXP.build({});
          const ms = Math.round(performance.now() - t0);
          const s1 = flat(collectModelState(), '', {});
          const diff = [];
          new Set([...Object.keys(s0), ...Object.keys(s1)]).forEach(k => { if (JSON.stringify(s0[k]) !== JSON.stringify(s1[k])) { const num = typeof s0[k] === 'number' && typeof s1[k] === 'number'; if (num && Math.abs(s0[k] - s1[k]) <= 1e-6 * Math.max(1, Math.abs(s0[k]))) return; diff.push(k + ': ' + JSON.stringify(s0[k]) + ' → ' + JSON.stringify(s1[k])); } });
          const b = TXP.build({});
          const texts = document.querySelectorAll('#chart text').length;
          return { tex: a.tex, stats: a.stats, warn: a.warn, ms, stateSame: diff.length === 0, stateDiff: diff.slice(0, 12), repeatSame: a.tex === b.tex, self: !!(typeof SELF === 'object' && SELF.on), domTexts: texts };
        } catch (e) { return { err: String(e && e.stack || e).slice(0, 600) }; }
      });
      if (r.err) { rec.err = r.err; errN++; }
      else {
        const sha = crypto.createHash('sha1').update(r.tex).digest('hex').slice(0, 12);
        const p = path.join(OUT, 'tex', sha + '.tex');
        if (!fs.existsSync(p)) fs.writeFileSync(p, r.tex);
        Object.assign(rec, { sha, stats: r.stats, warn: r.warn, ms: r.ms, stateSame: r.stateSame, stateDiff: r.stateDiff, repeatSame: r.repeatSame, self: r.self, len: r.tex.length });
        okN++;
      }
      if (f.errors.length) rec.pageErrors = f.errors.slice(0, 5);
     })()]);
    } catch (e) {
      rec.actErr = String(e.message || e).slice(0, 300); errN++;
    }
    clearTimeout(timer);
    if (f) await Promise.race([f.ctx.close().catch(() => {}), new Promise(r => setTimeout(r, 5000))]);
    fs.appendFileSync(logFile, JSON.stringify(rec) + '\n');
    const n = okN + errN;
    if (n % 20 === 0) console.log(n + '/' + todo.length, 'ок', okN, 'сбоев', errN, Math.round((Date.now() - t0) / 1000) + ' с');
  }
}
await Promise.all(Array.from({ length: JOBS }, worker));
console.log('готово: ок', okN, 'сбоев', errN, Math.round((Date.now() - t0) / 1000) + ' с');
await browser.close();
