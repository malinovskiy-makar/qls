/* Обход 42 моделей: поля формул в карточках — кегль, нужно/есть (сессия 6, А1, рабочий замер).
   node claude/panels_s6/fit_scan.mjs [ширина] [движок]   BASE, CSS (доп. стиль для пробы) */
import * as pw from 'playwright';
const W = +(process.argv[2] || 1280), engine = process.argv[3] || 'chromium';
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const ALL = 'm-graph m-transform m-optimum m-tangent m-minmax m-constraint ppf ppfsum trade tradeprice sd sdsum taxes ceil quota elast ext prod costs plants isoquant mono mono-nat mono-d1 mono-d3 mono-kink labor labor-mono labor-union labor-bilat smallopen monoexport consumer cons-slutsky adas islm phillips money loanable fx ineq laffer'.split(' ');
const b = await pw[engine].launch();
const ctx = await b.newContext({ viewport: { width: W, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
await ctx.addInitScript(() => { try { localStorage.clear(); localStorage.setItem('theme', 'light'); } catch (e) {} });
const page = await ctx.newPage();
await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
await page.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined');
if (process.env.CSS) await page.addStyleTag({ content: process.env.CSS });
for (const k of (process.env.KEYS ? process.env.KEYS.split(' ') : ALL)) {
  await page.evaluate((k) => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, k);
  await page.waitForTimeout(700);
  const r = await page.evaluate(() => [...document.querySelectorAll('#tools-panel math-field')].filter(e => e.getClientRects().length).map(m => {
    const c = m.shadowRoot && m.shadowRoot.querySelector('.ML__content');
    const id = (m.parentElement.querySelector('input[id]') || {}).id;
    return { id, card: !!m.closest('.fc-card'), fs: getComputedStyle(m).fontSize, need: c && c.scrollWidth, have: c && c.clientWidth, tall: /begin\{cases/.test(m.value) };
  }));
  const badOnes = r.filter(x => x.need > x.have + 1);
  console.log(k.padEnd(13), r.map(x => x.id + ':' + x.fs + (x.card ? '' : '(голое)') + (x.tall ? '(кус)' : '') + (x.need > x.have + 1 ? ' РЕЖЕТСЯ ' + x.need + '>' + x.have : '')).join('  '));
}
await b.close();
