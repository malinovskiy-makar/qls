/* Выгрузка «Разбора» по 42 моделям: перенесённые абзацы (.ex-from-cond, .ex-from-answer), вопросы и ответы.
   node claude/panels_s5/razbor_dump.mjs <out.json>   (BASE=… — сервер, по умолчанию 8099) */
import { chromium } from 'playwright';
import fs from 'fs';
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const ALL = 'm-graph m-transform m-optimum m-tangent m-minmax m-constraint ppf ppfsum trade tradeprice sd sdsum taxes ceil quota elast ext prod costs plants isoquant mono mono-nat mono-d1 mono-d3 mono-kink labor labor-mono labor-union labor-bilat smallopen monoexport consumer cons-slutsky adas islm phillips money loanable fx ineq laffer';
const KEYS = (process.env.KEYS || ALL).split(/\s+/).filter(Boolean);
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
await ctx.addInitScript(() => { try { localStorage.clear(); localStorage.setItem('theme', 'light'); localStorage.setItem('calc2.v1.answerHidden', '0'); } catch (e) {} });
const p = await ctx.newPage();
await p.goto(BASE + '/calc2/'); await p.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined');
const out = {};
for (const k of KEYS) {
  await p.evaluate(k => { resetSceneMemory(); pickScene(k); closePicker(); redrawAll(); }, k);
  await p.waitForTimeout(700);
  await p.evaluate(() => { const b = document.getElementById('ex-bar'); if (b && !document.body.classList.contains('ex-shown')) b.click(); });
  await p.waitForTimeout(250);
  out[k] = await p.evaluate(() => {
    const txt = (e) => { const c = e.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' ').trim(); };
    const body = document.getElementById('ex-body');
    const mono = (e) => [e, ...e.querySelectorAll('*')].some(x => !x.closest('.katex') && /mono|Menlo|Courier/i.test(getComputedStyle(x).fontFamily) && x.textContent.trim());
    // Перенесённые абзацы: из «Условия», из «Ответа» и пояснение вмешательства (абзац .sb-note без <p> — сам абзац).
    // На коде до сессии 5 у абзаца вмешательства нет класса ex-from-interv — узнаём его по тексту #sec-tax .hint-current.
    const cur = document.querySelector('#sec-tax .hint-current');
    const curT = cur ? txt(cur) : null;
    const isInterv = (e) => e.classList.contains('ex-from-interv') || (curT && e.classList.contains('sb-note') && txt(e) === curT);
    const tr = [...body.querySelectorAll(':scope > .ex-from-cond > p, :scope > .ex-from-answer > p, :scope > .sb-note')].filter(e => e.tagName === 'P' || isInterv(e)).map(e => {
      const r = e.getBoundingClientRect();
      return { from: isInterv(e) ? 'interv' : e.parentElement.classList.contains('ex-from-cond') ? 'cond' : 'answer', text: txt(e), html: e.innerHTML.slice(0, 600), mono: mono(e), top: r.top, bottom: r.bottom, mt: getComputedStyle(e).marginTop, mb: getComputedStyle(e).marginBottom };
    });
    // Вопросы и ответы «Разбора» вне перенесённых блоков: перенесённый абзац с жирным началом сам выглядит вопросом.
    const own = (e) => !e.closest('.ex-from-cond, .ex-from-answer, .ex-from-interv');
    const qs = [...body.querySelectorAll('p.ex-q')].filter(own).map(txt);
    const as = [...body.querySelectorAll('.ex-a')].filter(own).map(txt);
    const intro = [...body.querySelectorAll(':scope > .sb-note:not(.ex-from-cond):not(.ex-from-answer)')].map(txt);
    return { tr, qs, as, intro };
  });
}
await b.close();
fs.writeFileSync(process.argv[2] || 'razbor.json', JSON.stringify(out, null, 1));
console.log('моделей ' + Object.keys(out).length + ', перенесённых абзацев ' + Object.values(out).reduce((a, m) => a + m.tr.length, 0));
