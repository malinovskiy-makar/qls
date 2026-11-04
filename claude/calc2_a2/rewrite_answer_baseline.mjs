/* А2 24.10: эталон главных строк «Ответа» (calc2/tests/redesign/answer_baseline_20261009.json) — ТОЛЬКО для
   моделей, чей старт «Ответа» сменили решения сессии (ADR 0158):
     smallopen  — главные строки свободной торговли: Qd, Qs, импорт, излишки свободной торговли (HERO_STATE);
     labor, labor-mono — на старте МРОТ 45 связывает: группа «С МРОТ»;
     ext        — старт MSC = Q + 20 (решение …81e7…) и SW с внешними издержками (…810e…);
     quota      — цена по умолчанию — цена спроса 60 (…81e0…9219…).
   Формат записи — тот же, что у прибора answer_rows_probe (части «#N.k» склеены в пару «(a;b)»). Любая другая
   модель не трогается: KEYS — закрытый список.
     node claude/calc2_a2/rewrite_answer_baseline.mjs        (сервер на 8099) */
import { chromium } from 'playwright';
import fs from 'fs';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const FILE = 'calc2/tests/redesign/answer_baseline_20261009.json';
const KEYS = ['smallopen', 'labor', 'labor-mono', 'ext', 'quota'];
const base = JSON.parse(fs.readFileSync(FILE, 'utf8'));
const browser = keepAnswerOpen(await chromium.launch());
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
const page = await ctx.newPage();
await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
await page.waitForFunction(() => typeof pickScene === 'function');
for (const key of KEYS) {
  await page.evaluate((k) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, key);
  await page.waitForTimeout(600);
  const cells = await page.evaluate(() => {
    const t = (el) => { if (!el) return ''; const c = el.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ' ').trim(); };
    return [...document.querySelectorAll('#ans-hero .ans-cell')].map(c => ({ cap: t(c.querySelector('.ans-lab')), not: t(c.querySelector('.ans-not')), src: c.dataset.src, val: t(c.querySelector('.ans-val')), was: t(c.querySelector('.ans-was')) }));
  });
  // Части пары — обратно в одну запись, как склеивает прибор.
  const merged = cells.reduce((acc, c) => {
    const m = /^(.+#\d+)\.(\d+)$/.exec(c.src || '');
    if (!m) { acc.push(c); return acc; }
    const last = acc[acc.length - 1];
    if (m[2] === '1' || !last || last.src !== m[1]) acc.push(Object.assign({}, c, { src: m[1], val: '(' + c.val + ';' }));   // «было» — у первой части, как у прибора
    else last.val += c.val;
    return acc;
  }, []).map(c => (/^\(/.test(c.val) && !/\)$/.test(c.val) ? Object.assign(c, { val: c.val + ')' }) : c));
  console.log(key + ': ' + JSON.stringify(base[key]) + '\n  → ' + JSON.stringify(merged));
  base[key] = merged.map(c => ({ src: c.src, cap: c.cap, not: c.not, val: c.val, was: c.was }));   // порядок полей файла
}
fs.writeFileSync(FILE, JSON.stringify(base, null, 1));   // вид файла прежний: отступ 1, без перевода строки в конце
await browser.close();
