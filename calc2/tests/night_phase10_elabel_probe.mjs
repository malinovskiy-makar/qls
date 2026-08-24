/* Ночная сессия. ФАЗА 10 — буква E без звёздочки и с ореолом.
     node calc2/tests/night_phase10_elabel_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', process.env.CALC2_USER || 'admin');
await page.fill('#id_password', process.env.CALC2_PASS || 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
let ok = true;
const rep = (n, pass, d) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + n + (d ? '  -> ' + d : '')); if (!pass) ok = false; };

const r = await page.evaluate(async () => {
  const wait = ms => new Promise(res => setTimeout(res, ms));
  const halo = cssVar('--halo');
  const look = () => [...document.querySelectorAll('#chart text.point-name')].map(t => ({
    txt: (t.textContent || '').trim(),
    own: [...t.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('').trim(),
    stroke: t.getAttribute('stroke'), sw: +t.getAttribute('stroke-width'),
    order: t.getAttribute('paint-order'), fs: +t.getAttribute('font-size'),
  }));
  const out = {};
  for (const k of ['sd', 'tax', 'ceil', 'labor', 'smallopen', 'elast', 'ext']) {
    resetSceneMemory(); pickScene(k); await wait(300);
    out[k] = look();
  }
  out.halo = halo;
  // Тёмная тема: ореол обязан переехать вместе с фоном.
  setCalcTheme('dark'); await wait(300);
  resetSceneMemory(); pickScene('sd'); await wait(350);
  out.dark = { halo: cssVar('--halo'), names: look() };
  setCalcTheme('light'); await wait(250);
  return out;
});
console.log(JSON.stringify(r, null, 1));

const all = ['sd', 'tax', 'ceil', 'labor', 'smallopen', 'elast', 'ext'].flatMap(k => r[k].map(p => ({ k, p })));
/* Текст подписи лежит в tspan (renderLabelText набирает индексы отдельными
   узлами), поэтому имя берём из textContent; own — только для поиска СЫРОЙ
   звёздочки, той самой, что канон запрещает. */
const eqs = all.filter(x => /^E/.test(x.p.txt));
/* Буква равновесия стоит не в каждой сцене: там, где государство вмешалось,
   на холсте живут другие точки. Считаем, сколько нашлось, и требуем, чтобы
   она вообще была — а дальше проверяем КАЖДУЮ найденную. */
console.log('     подписи-имена точек по сценам: ' + all.map(x => x.k + ':' + x.p.txt).join(', '));
rep('подпись равновесия найдена', eqs.length >= 2, 'нашлось ' + eqs.length
    + ' (' + eqs.map(x => x.k).join(', ') + ')');
rep('звёздочки у буквы равновесия нет нигде',
    eqs.every(x => x.p.txt === 'E' || x.p.txt === 'E′'),
    eqs.map(x => x.k + ':«' + x.p.txt + '»').join(', '));
rep('сырых звёздочек нет ни в одном имени точки',
    all.every(x => !/[*]/.test(x.p.own) && !/[*]/.test(x.p.txt)),
    all.filter(x => /[*]/.test(x.p.txt)).map(x => x.k + ':' + x.p.txt).join(', '));
rep('ореол рисуется ПЕРЕД буквой', all.every(x => x.p.order === 'stroke'));
rep('ореол цветом фона', all.every(x => x.p.stroke === r.halo), all[0] && all[0].p.stroke + ' vs ' + r.halo);
rep('ореол шире прежнего (5 px против 2,5)', all.every(x => x.p.sw >= 5),
    'ширины: ' + [...new Set(all.map(x => x.p.sw))].join(', '));
rep('в тёмной теме ореол переезжает за фоном',
    r.dark.names.length > 0 && r.dark.names.every(p => p.stroke === r.dark.halo),
    r.dark.halo + ' / ' + (r.dark.names[0] || {}).stroke);
if (errs.length) rep('без ошибок страницы', false, errs.slice(0, 3).join(' | '));
await browser.close();
console.log('\nИТОГ: ' + (ok ? 'буква E чистая и с ореолом' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
