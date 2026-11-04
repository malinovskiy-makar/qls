/* Свойства выгрузки, которые не видны на одном файле:
     • один и тот же файл при четырёх окнах и двух темах;
     • повторная сборка даёт тот же файл;
     • после выгрузки состояние модели то же, холст тот же (число узлов,
       теги, атрибуты; числовые атрибуты — с точностью до шага доводки подписей);
     • время сборки.

   node checks.mjs                    восемь моделей по умолчанию
   KEYS=all node checks.mjs           все 44
   DIFF=1 …                           показать первую различающуюся строку */
import { chromium } from 'playwright';
import crypto from 'node:crypto';
import { openPage, openScene } from './lib.mjs';

const VARIANTS = [
  { name: '1440×760 светлая', w: 1440, h: 760, theme: 'light' },
  { name: '1024×700 тёмная', w: 1024, h: 700, theme: 'dark' },
  { name: '1280×900 светлая', w: 1280, h: 900, theme: 'light' },
  { name: '390×844 тёмная (телефон)', w: 390, h: 844, theme: 'dark' },
];
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
    await page.waitForTimeout(400);
    const r = await page.evaluate(() => {
      const chart = document.getElementById('chart');
      const snap = () => { const rows = []; chart.querySelectorAll('*').forEach(e => { const a = {}; for (const at of e.attributes) a[at.name] = at.value; rows.push([e.tagName, a, e.children.length ? '' : (e.textContent || '')]); }); return rows; };
      const num = /-?\d+\.?\d*(?:e-?\d+)?/g;
      const noise = (k, v) => (k === 'crosses' ? undefined : v);     // у пересечений шум в последнем знаке
      const dom0 = snap(), st0 = JSON.stringify(collectModelState(), noise);
      const t0 = performance.now(); const a = TXP.build({});
      const t1 = performance.now(); const b = TXP.build({});
      const t2 = performance.now();
      const dom1 = snap(), st1 = JSON.stringify(collectModelState(), noise);
      let same = dom0.length === dom1.length, maxDelta = 0;
      if (same) for (let i = 0; i < dom0.length && same; i++) {
        const [g0, a0, x0] = dom0[i], [g1, a1, x1] = dom1[i];
        if (g0 !== g1 || x0 !== x1 || Object.keys(a0).length !== Object.keys(a1).length) { same = false; break; }
        for (const k of Object.keys(a0)) {
          if (a0[k] === a1[k]) continue;
          const n0 = (a0[k].match(num) || []).map(Number), n1 = (String(a1[k]).match(num) || []).map(Number);
          if (a0[k].replace(num, '#') !== String(a1[k]).replace(num, '#') || n0.length !== n1.length) { same = false; break; }
          n0.forEach((q, j) => { maxDelta = Math.max(maxDelta, Math.abs(q - n1[j])); });
        }
      }
      const box = chart.getBoundingClientRect();
      return { tex: a.tex, same2: a.tex === b.tex, ms: [Math.round(t1 - t0), Math.round(t2 - t1)], domSame: same, maxDelta, stateSame: st0 === st1, shown: [Math.round(box.width), Math.round(box.height)] };
    });
    (out[key] = out[key] || []).push(Object.assign({ v: v.name, sha: sha(r.tex) }, r));
  }
  await ctx.close();
}
let bad = 0; const ms = [];
for (const key of KEYS) {
  const rows = out[key];
  const allSame = rows.every(r => r.sha === rows[0].sha);
  const clean = rows.every(r => r.same2 && r.domSame && r.maxDelta <= 0.5 && r.stateSame);
  if (!allSame || !clean) bad++;
  rows.forEach(r => ms.push(r.ms[0]));
  console.log(key.padEnd(13), allSame ? 'файл одинаков во всех окнах' : 'ФАЙЛ РАЗНЫЙ', rows.map(r => r.sha).join(' '));
  rows.forEach(r => console.log('    ', r.v.padEnd(26), 'повтор', r.same2 ? 'тот же' : 'ДРУГОЙ', '| мс', r.ms.join('/'), '| холст вернулся', r.domSame ? (r.maxDelta ? 'да, сдвиг до ' + r.maxDelta.toFixed(3) + ' px' : 'да') : 'НЕТ', '| состояние', r.stateSame ? 'то же' : 'ИЗМЕНИЛОСЬ', '| холст', r.shown.join('×')));
  if (!allSame && process.env.DIFF) {
    const a = rows[0].tex.split('\n'), b = rows.find(r => r.sha !== rows[0].sha).tex.split('\n');
    for (let i = 0; i < Math.max(a.length, b.length); i++) if (a[i] !== b[i]) { console.log('   строка', i + 1); console.log('     A:', (a[i] || '').slice(0, 300)); console.log('     B:', (b[i] || '').slice(0, 300)); break; }
  }
}
ms.sort((a, b) => a - b);
console.log('время сборки, мс: медиана', ms[ms.length >> 1], '| 95 %', ms[Math.floor(ms.length * 0.95)], '| наибольшее', ms[ms.length - 1]);
console.log(bad ? 'моделей с расхождением: ' + bad + ' из ' + KEYS.length : 'расхождений нет: ' + KEYS.length + ' из ' + KEYS.length);
await browser.close();
process.exit(bad ? 1 : 0);
