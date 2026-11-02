/* Э1, восстановленный план 29.10: проверки видимого результата в Chromium/WebKit.
   ENGINES=chromium,webkit WIDTHS=1440,1280; SHOTS=1 — снимки для ручного просмотра.
   Старые числовые эталоны не используются: геометрия, запись и контрольный уголок. */
import * as pw from 'playwright';
import fs from 'node:fs';
import { keepAnswerOpen, answerShown } from './answer_open.mjs';

const base = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const engines = (process.env.ENGINES || 'chromium').split(',');
const widths = (process.env.WIDTHS || '1440').split(',').map(Number);
const arg = (name, fallback) => { const i=process.argv.indexOf('--'+name); return i<0 ? fallback : process.argv[i+1]; };
const themes = arg('themes','light,dark').split(',');
let total = 0, bad = 0;
function check(name, pass, detail) {
  total++; if (!pass) bad++;
  console.log(`${pass ? 'OK' : 'FAIL'} ${name}${!pass && detail ? ': ' + JSON.stringify(detail) : ''}`);
}

function measure(scene) {
  const checks = [];
  const ck = (name, pass, detail) => checks.push({ name, pass: !!pass, detail });
  const shown = el => el && el.getClientRects().length && getComputedStyle(el).display !== 'none' && getComputedStyle(el).visibility !== 'hidden';
  const text = el => { const c = el.cloneNode(true); c.querySelectorAll('.katex-mathml').forEach(n => n.remove()); return c.textContent.trim(); };
  const labels = [...document.querySelectorAll('#chart text')].filter(shown);
  const labelsMatching = re => labels.filter(e => re.test(text(e)));
  const pair = (a, b, label) => {
    const as = labelsMatching(a), bs = labelsMatching(b);
    ck(label + ': обе подписи видны', as.length > 0 && bs.length > 0);
    const overlap = [];
    for (const x of as) for (const y of bs) {
      if (x === y) continue;
      const p = x.getBoundingClientRect(), q = y.getBoundingClientRect();
      if (Math.min(p.right, q.right) - Math.max(p.left, q.left) > 1 && Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top) > 1) overlap.push([text(x), text(y)]);
    }
    ck(label + ': подписи разнесены', !overlap.length, overlap);
  };
  ck('холст и деления видны', labels.some(e => e.classList.contains('axis-num')));
  const minus = labels.filter(e => /-\s*\d/.test(text(e))).map(text);
  ck('числа на холсте используют минус U+2212', !minus.length, minus);
  if (scene.startsWith('m-')) {
    ck('отрицательные числа действительно проверены', labels.some(e => /[−-]\d/.test(text(e))));
  }
  if (['ppf', 'ppfsum', 'trade', 'm-tangent'].includes(scene)) {
    const rows = [...document.querySelectorAll('#params-panel .stat, #params-panel .ff-math')].filter(shown);
    ck('ответ содержит видимые строки', rows.length > 0);
    const over = rows.filter(e => e.scrollWidth > e.clientWidth + 1).map(e => ({ text:text(e), width:e.clientWidth, content:e.scrollWidth }));
    ck('строки ответа помещаются', !over.length, over);
  }
  if (['m-transform', 'm-optimum', 'm-minmax'].includes(scene)) {
    const paths = [...document.querySelectorAll('#chart path[stroke]')].filter(e => !e.closest('defs') && e.getAttribute('d'));
    ck('пути кривых существуют', paths.length > 0);
    ck('каждая кривая обрезается по полю', paths.every(e => e.closest('[clip-path]')), paths.filter(e => !e.closest('[clip-path]')).map(e => e.getAttribute('stroke')));
  }
  if (scene === 'ceil') {
    const eq = document.querySelector('#pc-field .reg-eq');
    ck('цена набрана единственной формулой', shown(eq) && eq.querySelectorAll('.katex').length === 1);
    ck('нет исходника или тройного текста цены', eq && !/[\\{}]|P[fсc]P/.test(text(eq)), eq && text(eq));
    pair(/^50f/, /^50$/, 'пол цены на равновесии');
  }
  if (scene === 'quota') {
    const range = document.getElementById('quota-price-range');
    ck('коридор остаётся под ценой', shown(range) && /40.*60/.test(text(range)), range && text(range));
    ck('коридор не дублируется в разборе', ![...document.querySelectorAll('.ex-from-cond')].some(e => /коридор от/i.test(text(e))));
  }
  if (scene === 'consumer') {
    const row = [...document.querySelectorAll('#info-consumer .stat')].find(e => /^MRS/.test(text(e)));
    ck('MRS в изломе не определена', row && /не определена/.test(text(row)), row && text(row));
    ck('оптимум комплементов (20; 40)', Math.abs(STATE.cons.base.x - 20) < 1e-4 && Math.abs(STATE.cons.base.y - 40) < 1e-4);
    const paths = [...document.querySelectorAll('#chart path[stroke]')].filter(e => !e.closest('defs'));
    const vertical = paths.some(p => {
      const n = p.getTotalLength();
      for (let i = 0; i < 90; i++) {
        const a = p.getPointAtLength(n*i/100), b = p.getPointAtLength(n*(i+10)/100);
        if (Math.abs(a.x-b.x) < .1 && Math.abs(a.y-b.y) > 10 && Math.abs(a.x-sx(20)) < .1) return true;
      }
      return false;
    });
    ck('у оптимальной кривой есть вертикальная часть уголка', vertical);
  }
  if (scene === 'elast') {
    ck('единичная эластичность подписана один раз', labelsMatching(/\|Ed\|\s*=\s*1/).length === 1);
    pair(/^E$/, /MR.*TR/, 'точка E и условие единичной эластичности');
  }
  if (scene === 'prod') {
    pair(/перегиб TP/, /max AP|AP = MP/, 'максимумы MP и AP');
    ck('обе кривые нижней панели подписаны', labelsMatching(/^MP$/).length === 1 && labelsMatching(/^AP$/).length === 1);
  }
  if (scene === 'costs') {
    pair(/^ATC$/, /^AVC$/, 'ATC и AVC');
    const label = labelsMatching(/^безубыточность$/)[0];
    const area = document.querySelector('.lr-area rect[data-legend="Прибыль фирмы"]');
    ck('прибыль и подпись безубыточности видны', shown(label) && shown(area));
    ck('безубыточность вне заливки прибыли', label && area && (() => {
      const p=label.getBoundingClientRect(), q=area.getBoundingClientRect();
      return p.bottom <= q.top || p.top >= q.bottom || p.right <= q.left || p.left >= q.right;
    })());
  }
  if (scene === 'm-minmax') pair(/^Z$/, /^f2/, 'Z и f₂');
  if (scene === 'mono-d1') {
    ck('нет английского индекса comp', !labels.some(e => /comp/.test(text(e))));
    const profit = labelsMatching(/^Прибыль$/)[0];
    ck('подпись прибыли внутри области между D и MC', profit && (() => {
      const r = profit.getBBox(), x = sx.invert(r.x + r.width/2);
      const d = STATE.curves.find(c => c.role === 'demand');
      return r.y > sy(evalCurve(d,x)) && r.y+r.height < sy(mcAt(x));
    })());
  }
  if (scene === 'monoexport') {
    const row = [...document.querySelectorAll('#info-discr3 .stat')].find(e => /Экспорт/.test(text(e)));
    const all = text(document.getElementById('params-panel'));
    ck('экспорт и мировая цена не выглядят дробью', !/25\s*\/\s*50/.test(all));
    ck('объём экспорта и цена присутствуют', /25/.test(all) && /50/.test(all), row && text(row));
  }
  if (scene === 'm-tangent') {
    const row = [...document.querySelectorAll('#info-math .stat')].find(e => /^Касательная/.test(text(e)));
    ck('уравнение касательной набрано KaTeX', row && row.querySelector('b .katex'));
    const delta = labelsMatching(/^Δx/)[0], panel = STATE.panels.find(p => p.id === 'deriv-top');
    ck('Δx не пересекает ось x', delta && panel && (() => { const r=delta.getBBox(), y=panel.my(0); return r.y+r.height < y-2 || r.y > y+2; })());
    const title = labelsMatching(/^f\(x\), сама/)[0];
    ck('название функции читается поверх кривой', title && +title.getAttribute('stroke-width') >= 3 && title.getAttribute('paint-order') === 'stroke');
  }
  if (scene === 'm-transform') {
    const label=labelsMatching(/^Исходная$/)[0];
    ck('словесное имя кривой набрано шрифтом интерфейса', label && /Montserrat/.test(getComputedStyle(label).fontFamily), label && getComputedStyle(label).fontFamily);
  }
  if (scene === 'ppf') {
    ck('max в главных строках прямым шрифтом', [...document.querySelectorAll('#ans-hero annotation')].some(e => /\\mathrm\{max\}/.test(e.textContent)));
    ck('комплект имеет собственную подпись', labelsMatching(/^Комплект\s*\(/).length > 0);
    const inputs=[...document.querySelectorAll('#inp-bundle-x, #inp-bundle-y')];
    ck('пример в коротком числовом поле не обрезается словом', inputs.length === 2 && inputs.every(e => /^\d+$/.test(e.placeholder)));
  }
  if (scene === 'm-graph') ck('коэффициент и переменная без лишнего пробела', mathToTex('2x+1') === '2x+1');
  if (scene === 'cons-slutsky') ck('изменение потребления без дефиса', !/-\s*\d/.test(text(document.querySelector('#info-consumer'))));
  if (scene === 'labor-bilat') ck('длинное пояснение не лежит на кривых', !labelsMatching(/^Конкретная точка зависит/).length);
  const scroll = document.querySelector('#params-panel .side-scroll'), chat = document.querySelector('.tg-fab');
  if (shown(scroll) && shown(chat)) ck('видимая область ответа заканчивается выше кнопки чата', scroll.getBoundingClientRect().bottom <= chat.getBoundingClientRect().top - 2);
  return checks;
}

const scenes = arg('scenes','ppf ppfsum trade ceil quota consumer elast prod costs m-tangent mono-d1 monoexport m-transform m-optimum m-minmax labor-bilat m-graph cons-slutsky').split(/[ ,]+/);
for (const engine of engines) {
  const browser = await pw[engine].launch(); keepAnswerOpen(browser);
  for (const width of widths) for (const theme of themes) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
    await context.addInitScript(t => localStorage.setItem('theme',t), theme);
    const page = await context.newPage(); const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/calc2/', { waitUntil:'load' });
    await page.waitForFunction(() => typeof pickScene === 'function' && typeof math !== 'undefined');
    await page.evaluate(() => document.fonts.ready);
    for (const scene of scenes) {
      await page.evaluate(key => {
        resetSceneMemory(); pickScene(key);
        if (key === 'consumer') setConsumerType('compl');
        if (key === 'ppf') { STATE.bundleOn=true; STATE.bundleX=1; STATE.bundleY=2; redrawAll(); }
        if (key === 'ceil') { setType('floor'); setPRegFields(50); redrawAll(); }
      }, scene);
      await page.waitForTimeout(450);
      const tag = `${engine}/${width}/${theme}/${scene}`;
      check(tag + ': ответ открыт', await answerShown(page));
      for (const c of await page.evaluate(measure, scene)) check(tag + ': ' + c.name,c.pass,c.detail);
      if (process.env.SHOTS === '1') {
        const dir = '.calc2-astra-local/e1-shots'; fs.mkdirSync(dir,{recursive:true});
        await page.screenshot({path:`${dir}/${engine}-${width}-${theme}-${scene}.png`});
      }
    }
    check(`${engine}/${width}/${theme}: нет ошибок JavaScript`, !errors.length, errors);
    await context.close();
  }
  await browser.close();
}
console.log(`Э1: ${total-bad}/${total}, ошибок ${bad}`);
process.exitCode = bad ? 1 : 0;
