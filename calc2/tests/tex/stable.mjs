/* Свойства выгрузки, которые не видны на одном файле (прибор tex_stable):
     • один и тот же файл при четырёх окнах и двух темах (Т6) и при обычных
       переходах вместо «меньше движения» (пятый вариант);
     • повторная сборка даёт тот же файл;
     • после выгрузки состояние модели, холст, стек «Отменить», localStorage
       те же, событий «модель изменилась» во время выгрузки нет (Т7);
     • время сборки.
   Файл берётся НАСТОЯЩЕЙ дверью buildTex (у прототипа — TXP.build).

   node calc2/tests/tex/stable.mjs                восемь моделей по умолчанию
   KEYS=all node calc2/tests/tex/stable.mjs       все 44
   VARIANTS=2 …                                   только первые два окна (тест CI)
   DIFF=1 …                                       показать первую различающуюся строку */
import { chromium } from 'playwright';
import crypto from 'node:crypto';
import { ENGINE, openPage, openScene } from './lib.mjs';

const ALL = [
  { name: '1440×760 светлая', w: 1440, h: 760, theme: 'light' },
  { name: '1024×700 тёмная', w: 1024, h: 700, theme: 'dark' },
  { name: '1280×900 светлая', w: 1280, h: 900, theme: 'light' },
  { name: '390×844 тёмная (телефон)', w: 390, h: 844, theme: 'dark' },
  { name: '1440×760 светлая, переходы', w: 1440, h: 760, theme: 'light', motion: 'no-preference' },
];
const VARIANTS = ALL.slice(0, +(process.env.VARIANTS || ALL.length));
const browser = await chromium.launch();
const sha = (s) => crypto.createHash('sha1').update(s).digest('hex').slice(0, 10);
const out = {};
let KEYS = (process.env.KEYS || 'taxes,sdsum,prod,mono-d3,m-tangent,costs,labor-bilat,cons-slutsky').split(',');
for (const v of VARIANTS) {
  const { ctx, page } = await openPage(browser, v);
  if (KEYS[0] === 'all') KEYS = await page.evaluate(() => Object.keys(SCENE_NAMES));
  for (const key of KEYS) {
    await openScene(page, key);
    await page.evaluate(() => { redrawAll(); redrawAll(); });
    await page.waitForTimeout(450);                 // затишье истории после перерисовок прибора
    const r = await page.evaluate((eng) => {
      const A = window.__TXA, E = A.engine(eng);
      const noise = (k, val) => (k === 'crosses' ? undefined : val);     // у пересечений шум в последнем знаке
      const dom0 = A.domSnap(), st0 = JSON.stringify(collectModelState(), noise), h0 = A.histSnap();
      const ev = A.listen();
      const t0 = performance.now(); const a = E.door('', '');
      const t1 = performance.now(); const b = E.door('', '');
      const t2 = performance.now();
      ev.stop();
      const dom1 = A.domSnap(), st1 = JSON.stringify(collectModelState(), noise);
      const cmp = A.domCompare(dom0, dom1);
      const box = document.getElementById('chart').getBoundingClientRect();
      window.__h0 = h0;
      return { tex: a, same2: a === b, ms: [Math.round(t1 - t0), Math.round(t2 - t1)], domSame: cmp.same, maxDelta: cmp.maxDelta, why: cmp.why, stateSame: st0 === st1, events: ev.got, shown: [Math.round(box.width), Math.round(box.height)] };
    }, ENGINE);
    await page.waitForTimeout(450);                 // таймер истории, если выгрузка его завела, успеет сработать
    r.hist = await page.evaluate(() => window.__TXA.histAfter(window.__h0));
    (out[key] = out[key] || []).push(Object.assign({ v: v.name, sha: sha(r.tex) }, r));
  }
  await ctx.close();
}
let bad = 0; const ms = [];
for (const key of KEYS) {
  const rows = out[key];
  const allSame = rows.every(r => r.sha === rows[0].sha);
  const ev = (r) => r.events['calc2:changing'] + r.events['calc2:history'];
  const histOk = (r) => r.hist.undo[0] === r.hist.undo[1] && r.hist.redo[0] === r.hist.redo[1] && r.hist.lsSame;
  const clean = rows.every(r => r.same2 && r.domSame && r.stateSame && !ev(r) && histOk(r));
  if (!allSame || !clean) bad++;
  rows.forEach(r => ms.push(r.ms[0]));
  console.log(key.padEnd(13), allSame ? 'файл одинаков во всех окнах' : 'ФАЙЛ РАЗНЫЙ', rows.map(r => r.sha).join(' '));
  rows.forEach(r => console.log('    ', r.v.padEnd(28), 'повтор', r.same2 ? 'тот же' : 'ДРУГОЙ', '| мс', r.ms.join('/'),
    '| холст вернулся', r.domSame ? (r.maxDelta ? 'да, сдвиг до ' + r.maxDelta.toFixed(3) + ' px' : 'да') : 'НЕТ (' + r.why + ')',
    '| состояние', r.stateSame ? 'то же' : 'ИЗМЕНИЛОСЬ', '| история', histOk(r) ? 'та же' : 'ДРУГАЯ ' + JSON.stringify(r.hist),
    '| событий', ev(r), '| холст', r.shown.join('×')));
  if (!allSame && process.env.DIFF) {
    const a = rows[0].tex.split('\n'), b = rows.find(r => r.sha !== rows[0].sha).tex.split('\n');
    for (let i = 0; i < Math.max(a.length, b.length); i++) if (a[i] !== b[i]) { console.log('   строка', i + 1); console.log('     A:', (a[i] || '').slice(0, 300)); console.log('     B:', (b[i] || '').slice(0, 300)); break; }
  }
}
ms.sort((a, b) => a - b);
console.log('время сборки (дверь), мс: медиана', ms[ms.length >> 1], '| 95 %', ms[Math.floor(ms.length * 0.95)], '| наибольшее', ms[ms.length - 1]);
console.log(bad ? 'моделей с расхождением: ' + bad + ' из ' + KEYS.length : 'расхождений нет: ' + KEYS.length + ' из ' + KEYS.length);
await browser.close();
process.exit(bad ? 1 : 0);
