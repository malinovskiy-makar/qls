// ФАЗА 2. Матрица «параметр × сцена». Только чтение состояния: скрипт вписывает
// букву в поле, двигает ползунок и возвращает поле как было.
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(1500);

const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const names = await page.$$eval('.scard', els => Object.fromEntries(
  els.map(e => [e.dataset.scene, (e.querySelector('.scard-name') || e).textContent.trim()])));

const rows = [];
for (const key of scenes) {
  await page.evaluate(k => { pickScene(k); setToolsOpen(true); }, key);
  await page.waitForTimeout(400);
  /* Пять сцен открываются БЕЗ единого поля формулы на экране: у «Построения
     графиков» холст пуст, у потребителя и у неравенства поле прячется за
     выбором способа ввода. Делаем ровно то, что сделал бы человек, который
     хочет вписать формулу, и только потом меряем. */
  await page.evaluate(k => {
    const fire = (el, t) => el.dispatchEvent(new Event(t, { bubbles: true }));
    if (k === 'm-graph') {
      const inp = document.querySelector('#graph-rows .grow input[type=text]');
      if (inp) { inp.value = 'x^2 - 4'; ['input', 'change'].forEach(t => fire(inp, t));
                 inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); }
    }
    if (k === 'consumer' || k === 'cons-slutsky') {
      const sel = document.getElementById('cons-type');
      if (sel) { sel.value = 'custom'; fire(sel, 'change'); }
    }
    if (k === 'ineq' && typeof setIneqInput === 'function') setIneqInput('formula');
  }, key);
  await page.waitForTimeout(500);
  let res;
  try {
    res = await page.evaluate(async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      const vis = el => !!(el && el.getClientRects().length);
      const commit = (f) => {
        ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
        f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      };
      // Отпечаток — ЧИСЛО: сумма всех чисел во всех путях кривых, округлённая.
      const shot = () => {
        let s = 0, n = 0, len = 0;
        document.querySelectorAll('#chart path').forEach(p => {
          const d = p.getAttribute('d') || '';
          if (!d) return;
          n++; len += d.length;
          (d.match(/-?\d+(?:\.\d+)?/g) || []).forEach(x => { s += +x; });
        });
        return { paths: n, len, sum: Math.round(s * 1000) / 1000 };
      };
      const same = (a, b) => a.paths === b.paths && a.len === b.len && Math.abs(a.sum - b.sum) < 1e-6;

      const buildBtns = () => [...document.querySelectorAll('#tools-panel button')]
        .filter(b => /Постро/i.test(b.textContent || '') && vis(b));
      const chipFor = (P) => [...document.querySelectorAll('#params-body .pchip-param')]
        .find(c => {
          const t = (c.querySelector('.pchip-lab') || c).textContent || '';
          return new RegExp('(^|[^A-Za-z])' + P + '($|[^A-Za-z])').test(t.replace(/\s+/g, ''))
              || t.trim().startsWith(P);
        });

      const busy = (typeof sceneReserved === 'function') ? sceneReserved() : new Set();
      const P = ['a', 'k', 'm', 'n', 'z'].find(x => !busy.has(x)) || 'z';

      const fields = FORMULA_FIELDS.filter(i => i.isConnected && fieldActive(i) && (i.value || '').trim().length > 2);
      const sleeping = FORMULA_FIELDS.filter(i => i.isConnected && !fieldActive(i)).map(i => i.id);
      const out = [];
      for (const f of fields) {
        const orig = f.value;
        let base = null;
        let mod = orig.replace(/(?<![\w.])(\d+(?:\.\d+)?)\s*\*/, (m0, d) => { base = +d; return P + '*'; });
        if (mod === orig) mod = orig.replace(/(?<![\w.^])(\d+(?:\.\d+)?)(?![\d.])/, (m0, d) => { base = 1; return P + '*' + d; });
        // Числа для замены нет вовсе («x^2»): буква встаёт множителем ко всей
        // правой части. Её естественное значение — единица.
        if (mod === orig || base === null) {
          base = 1;
          const eq = orig.indexOf('=');
          mod = eq >= 0 ? orig.slice(0, eq + 1) + ' ' + P + '*(' + orig.slice(eq + 1).trim() + ')'
                        : P + '*(' + orig.trim() + ')';
        }
        const rec = { id: f.id, orig, mod, base, letter: P };
        try {
          f.value = mod; commit(f);
          await sleep(320);
          let chip = chipFor(P);
          rec.btns = buildBtns().map(b => b.id || b.textContent.trim());
          if (!chip && rec.btns.length) {
            buildBtns()[0].click(); await sleep(320);
            chip = chipFor(P);
            if (chip) rec.needBtnForSlider = true;
          }
          rec.slider = !!chip;
          if (chip) {
            const sl = chip.querySelector('input[type=range]');
            rec.hasRange = !!sl;
            if (sl) {
              const min = +sl.min, max = +sl.max;
              const clamp = v => Math.max(min, Math.min(max, v));
              const start = +sl.value;
              rec.from = start;
              const s0 = shot();
              const cands = [base * 1.6, base * 0.5, base * 3, start + (max - min) * 0.3, min, max]
                .map(clamp).filter(v => Math.abs(v - start) > 1e-9);
              let moved = false, at = null;
              for (const v of [...new Set(cands)]) {
                sl.value = v;
                sl.dispatchEvent(new Event('input', { bubbles: true }));
                await sleep(140);
                const s1 = shot();
                if (!same(s0, s1)) { moved = true; at = v; rec.after = s1; break; }
              }
              rec.to = at;
              rec.before = s0;
              rec.changed = moved;
              if (!moved) {
                // Не поменялось само — пробуем «Построить».
                const bs = buildBtns();
                if (bs.length) {
                  bs[0].click(); await sleep(360);
                  const s2 = shot();
                  rec.changedAfterBtn = !same(s0, s2);
                  rec.after = s2;
                }
              }
            }
          }
        } catch (e) { rec.error = String(e.message).slice(0, 80); }
        try { f.value = orig; commit(f); } catch (e) {}
        await sleep(120);
        out.push(rec);
      }
      try { redrawAll(); } catch (e) {}
      return { letter: P, mode: STATE.mode, fields: out, sleeping };
    });
  } catch (e) { res = { error: String(e.message).slice(0, 120) }; }
  rows.push({ key, name: names[key] || key, ...res });
  process.stdout.write('.');
}
process.stdout.write('\n');
writeFileSync(process.env.OUT || 'phase2.json', JSON.stringify({ rows, errors }, null, 1));
console.log('сцен:', rows.length, 'ошибок страницы:', errors.length);
await browser.close();
