/* Воспроизвести отдельные задачи широкого прогона и показать подробности:
   счётчики, панели и оси, записи, которые не сошлись.

   IDS='costs#123,m-graph#12' node one.mjs
   MODE=all IDS='taxes#start' node one.mjs      все пути с их записями
   OUT=папка …                                  ещё и .tex с картинкой холста */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { ROOT, BASE, PROTO } from './lib.mjs';

const RD = path.join(ROOT, 'calc2/tests/redesign');
const L = await import(path.join(RD, 'lib.mjs'));
const layer = await import(path.join(RD, 'layer_new.mjs'));
const IDS = (process.env.IDS || '').split(',').filter(Boolean);
const OUT = process.env.OUT || '';
if (!IDS.length) { console.log('задай IDS, например IDS=taxes#start'); process.exit(2); }
L.configure({ layer, base: BASE, layerName: 'new', w: 1440, h: 760 });
const browser = await chromium.launch();
for (const id of IDS) {
  const [key, idx] = id.split('#');
  const bl = JSON.parse(fs.readFileSync(path.join(RD, 'baseline', key + '.json'), 'utf8'));
  const desc = (k) => (bl.controls || []).find(c => c.key === k) || (bl.inventory && bl.inventory[k] ? { key: k, ...bl.inventory[k] } : null);
  const st = idx === 'start' ? { path: [] } : bl.steps[+idx];
  const f = await L.openKey(browser, key, 'light');
  const acts = [];
  for (const c of st.path.map(desc)) { acts.push(await L.act(f.page, c, key)); await L.settle(f.page); }
  await f.page.addScriptTag({ path: PROTO });
  const r = await f.page.evaluate((mode) => {
    redrawAll(); redrawAll();
    const leave = TXP.enterPaper();
    const list = TXP.capture();
    const em = TXP.emit(list, {});
    const out = { stats: em.stats, warn: list.warn, tex: em.tex, rows: [], panels: list.panels.map(p => ({ id: p.id, оси: (p.ax.xLine ? 'x' : '-') + (p.ax.yLine ? 'y' : '-'), делений: [p.ax.xt.length, p.ax.yt.length], x: p.xd, y: p.yd })) };
    list.panels.forEach(p => p.items.forEach(it => {
      if (it.kind !== 'path') return;
      const bad = (it.rec && !it.rec.ok) || (it.area && !it.area.ok);
      if (mode !== 'all' && !bad) return;
      out.rows.push({ панель: p.id, вид: (it.fl ? 'область' : 'кривая'), форма: it.shape, узлов: it.pts.length, rec: it.rec ? { ok: it.rec.ok, expr: it.rec.expr, v: it.rec.v, axis: it.rec.axis, lo: it.rec.lo, hi: it.rec.hi, samples: it.rec.samples, maxErr: it.rec.maxErr, between: it.rec.between, why: it.rec.why, name: it.rec.name } : null, area: it.area ? { ok: it.area.ok, a: it.area.a, b: it.area.b, lo: it.area.lo, hi: it.area.hi, maxErr: it.area.maxErr, areaErr: it.area.areaErr, why: it.area.why } : null, nodes: it.nodes || null, начало: it.pts.slice(0, 2), конец: it.pts.slice(-2) });
    }));
    leave();
    return out;
  }, process.env.MODE || '');
  console.log('=== ' + id + '  ' + acts.join(' ; '));
  console.log(JSON.stringify(r.stats), r.warn);
  console.log('панели', JSON.stringify(r.panels));
  r.rows.forEach(b => console.log(JSON.stringify(b)));
  if (OUT) { fs.mkdirSync(OUT, { recursive: true }); fs.writeFileSync(path.join(OUT, id.replace('#', '_n_') + '.tex'), r.tex); await f.page.locator('#chart').screenshot({ path: path.join(OUT, id.replace('#', '_n_') + '.png') }); }
  await f.ctx.close();
}
await browser.close();
