// Фаза −1 сессии «рынок труда»: на коде до сессии (сервер 8098, bfb74cc3) открыть каждую из четырёх моделей труда со
// старта, снять состояние collectModelState() и ссылку shareLinkOf(...) (автосохранение без правки не пишется) и
// числа «Ответа» — в claude/calc2_labor/fixtures/old_<ключ>.json.
//   node claude/calc2_labor/make_fixtures.mjs [base] [папка]
import { chromium } from 'playwright';
import fs from 'fs';
import { keepAnswerOpen } from '../../calc2/tests/answer_open.mjs';
const BASE = process.argv[2] || 'http://127.0.0.1:8098';
const DIR = process.argv[3] || 'claude/calc2_labor/fixtures';
const KEYS = ['labor', 'labor-mono', 'labor-union', 'labor-bilat'];
const browser = keepAnswerOpen(await chromium.launch());
const out = {};
for (const key of KEYS) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'ru-RU' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(BASE + '/calc2/?m=' + key, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const r = await page.evaluate(async () => {
    const s = collectModelState();
    const vis = (id) => { const e = document.getElementById(id); return !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden'); };
    const chk = document.getElementById('chk-labmin');
    const chkLabel = chk && chk.closest('label');
    return {
      state: s,
      link: await shareLinkOf(s),
      answer: Array.from(document.querySelectorAll('#info-labor .stat, #info-labor .hint, #info-labor .sb-subsec'))
        .map(e => e.textContent.replace(/\s+/g, ' ').trim()),
      nums: {
        laborEq: STATE.laborEq, laborMono: STATE.laborMono, laborUnion: STATE.laborUnion,
        laborBilateral: STATE.laborBilateral, laborMin: STATE.laborMin, laborMinWelfare: STATE.laborMinWelfare,
        laborMinOn: STATE.laborMinOn, laborMinW: STATE.laborMinW, laborStruct: STATE.laborStruct,
        curves: STATE.curves.map(c => ({ role: c.role, text: c.text || c.expr || c.raw })),
      },
      chkLabminShown: !!(chkLabel && chkLabel.getClientRects().length && getComputedStyle(chkLabel).display !== 'none'),
      minLineDrawn: Array.from(document.querySelectorAll('#chart text')).some(t => /min/.test(t.textContent)),
      labminFieldShown: vis('labmin-field'),
    };
  });
  r.errors = errors;
  fs.writeFileSync(`${DIR}/old_${key}.json`, JSON.stringify({ base: BASE, code: 'bfb74cc3', made: new Date().toISOString(), ...r }, null, 1));
  out[key] = { answer: r.answer, minOn: r.nums.laborMinOn, minW: r.nums.laborMinW, curves: r.nums.curves,
               chkShown: r.chkLabminShown, minLine: r.minLineDrawn, errors };
  await ctx.close();
}
console.log(JSON.stringify(out, null, 1));
await browser.close();
