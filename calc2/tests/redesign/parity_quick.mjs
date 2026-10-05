/* БЫСТРЫЙ ПАРИТЕТ (редизайн calc2, фаза 11): то, что идёт в CI.

   Одна страница, 44 ключа подряд, каждый со свежим состоянием
   (resetSceneMemory + pickScene). Для каждого ключа против базового снимка
   старого экрана (calc2/tests/redesign/baseline/<ключ>.json, раздел start):
     1. органы управления на месте: каждый орган старта старого экрана найден
        на новом — сам, по замене из закрытого списка (fates.mjs) или в
        закрытом меню своей карточки; убранные по (л), (м) и заменённые видом
        рабочего места (в, г, д, к) не ищутся — их судьба в PARITY.md;
     2. видимые числа старта равны базовым: каждая строка табло (блок,
        номер, значение) и итоговая функция.
   Подробная сверка (шаги, жесты, геометрия) — snapshot.mjs + compare.mjs,
   вручную: она идёт часами.

   CALC2_BASE_URL=… node calc2/tests/redesign/parity_quick.mjs
   Код 0 — паритет цел; 1 — расхождения; 3 — calc2 не загрузился (провал);
   4 — Playwright не запустился (пропуск теста).                            */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { fateOf } from './fates.mjs';
import * as layerNew from './layer_new.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const BL = path.join(HERE, 'baseline');
const INPAGE = fs.readFileSync(path.join(HERE, 'inpage.js'), 'utf8');
const keys = fs.readdirSync(BL).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5)).sort();
const t0 = Date.now();

let browser;
try { browser = await chromium.launch(); } catch (e) { console.error('Playwright не запустился: ' + e.message); process.exit(4); }
const ctx = await browser.newContext({ viewport: { width: 1440, height: 760 }, reducedMotion: 'reduce', locale: 'ru-RU' });
await ctx.addInitScript(() => { try { localStorage.setItem('theme', 'light'); } catch (e) {} });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
try {
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof math !== 'undefined' && typeof d3 !== 'undefined', null, { timeout: 30000 });
} catch (e) { console.error('calc2 не загрузился: ' + e.message); await browser.close(); process.exit(3); }
await page.addScriptTag({ content: INPAGE });
await page.evaluate(async () => { const a = []; document.fonts.forEach(f => a.push(f.load().catch(() => null))); await Promise.all(a); });

const norm = (s) => String(s == null ? '' : s).replace(/[\s   ​]+/g, '').replace(/[−–]/g, '-');
let bad = 0, checks = 0;
const issues = [];
for (const key of keys) {
  const rec = JSON.parse(fs.readFileSync(path.join(BL, key + '.json'), 'utf8'));
  const e0 = errors.length;
  await page.evaluate((k) => { resetSceneMemory(); pickScene(k); if (typeof closePicker === 'function') closePicker(); redrawAll(); }, key);
  await page.waitForFunction(() => window.__RD.settled(), null, { timeout: 6000 }).catch(() => null);
  await page.waitForTimeout(120);
  // 1. Органы старта.
  const want = (rec.controls || rec.start.controls || []).filter(c => !c.picker).map(c => c.key);
  const res = await page.evaluate((list) => list.map(k => {
    const el = window.__RD.findControl(k.mapped) || window.__RD.findControlAny(k.mapped);
    return el ? null : k.orig;
  }).filter(Boolean), want.filter(k => {
    const f = fateOf(k);
    return !(f.fate === 'убран' || (f.fate === 'заменён' && /^[авгдк]$/.test(f.letter)));
  }).map(k => ({ orig: k, mapped: layerNew.mapKey(k.replace(/~\d+$/, '')) })));
  checks += want.length;
  res.forEach(k => { bad++; issues.push(key + ': орган ' + k + ' не найден'); });
  // 2. Числа старта.
  const ans = await page.evaluate(() => window.__RD.answerOld());
  const b1 = new Map((ans.blocks || []).map(b => [b.id, b]));
  (rec.start.answer.blocks || []).forEach(b => {
    const c = b1.get(b.id);
    b.rows.forEach(r => {
      checks++;
      const q = c && c.rows.find(x => String(x.i) === String(r.i));
      if (!q) { bad++; issues.push(key + ': ' + b.id + ' строка «' + r.label + '» не показана'); return; }
      if (norm(q.value) !== norm(r.value)) { bad++; issues.push(key + ': ' + b.id + ' «' + r.label + '» ' + r.value + ' → ' + q.value); }
    });
    (b.final || []).forEach((f, i) => {
      checks++;
      const g = c && (c.final || [])[i];
      if (!g || g.copy !== f.copy) { bad++; issues.push(key + ': итоговая функция «' + f.name + '» разошлась'); }
    });
  });
  // Ошибки страницы, которых не было на старом экране.
  const old = new Set((rec.errors || []).map(e => String(e).replace(/[\d.]+/g, '#')));
  errors.slice(e0).forEach(e => { if (!old.has(String(e).replace(/[\d.]+/g, '#'))) { bad++; issues.push(key + ': ошибка страницы ' + e); } });
}
await browser.close();
const sec = ((Date.now() - t0) / 1000).toFixed(1);
issues.slice(0, 60).forEach(x => console.log('  ✗ ' + x));
console.log((bad ? 'ПАРИТЕТ НАРУШЕН' : 'ПАРИТЕТ ЦЕЛ') + ': ключей ' + keys.length + ', проверок ' + checks + ', расхождений ' + bad + ', ' + sec + ' с');
process.exit(bad ? 1 : 0);
