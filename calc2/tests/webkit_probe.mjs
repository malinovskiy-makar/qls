/* SAFARI — ВВОД В ПОЛЯ ОТРЕЗКА И ПОЛЕ «СНАЧАЛА САМ» (13.10.2026, часть 3).

     ./venv313/bin/python manage.py runserver 8099 --noreload --settings=config.settings_check
     npx playwright install webkit        # один раз: движок Safari в кэш пользователя, в репозиторий ничего
     node calc2/tests/webkit_probe.mjs    # ENGINES=webkit — только WebKit; ONLY=А,Б — по разделам

   Владелец смотрит сайт в Safari. Прибор гоняет одно и то же в WebKit (движок Safari) и в Chromium.
   Нет WebKit на машине — громкий пропуск этого движка (код 2, если не прошёл ни один).

   А. «Построение графиков», поля «Ответ ищем на отрезке»: «-60» в «от», «200» и «50» в «до» набираются
      посимвольно с паузами 300 мс → значение поля равно набранному, фокус до Enter в этом поле; после
      Enter STATE.ansA/ansB равны введённому, отрезок ответа (_ansSeg) пересчитан. То же с помехой: между
      цифрами перерисовка, а строка «хочет» переехать (под #graph-rows подсунут чужой узел) — пока человек
      в строке, она стоит, фокус не теряется (Safari, 13.10: «после каждой цифры окно думает, что ты
      закончил ввод»). Уход из строки щелчком применяет набранное.
   Б. «Сначала сам», ячейка «Пересекает ось x», набрано «2; -2», «Проверить»; 1280 и 1440, светлая и тёмная
      тема: прокрутка колонки «Ответ» по горизонтали 0; поле вместе с 4 px кольца фокуса целиком внутри
      видимой области колонки (пересечение обрезок всех предков с overflow ≠ visible); «Проверить» целиком
      видна. В Safari 13.10 левая рамка, скругление и кольцо поля были срезаны краем блока #scoreboard.
*/
import { webkit, chromium } from 'playwright';
import { keepAnswerOpen, answerShown } from './answer_open.mjs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = process.env.ONLY || '';
const ENGINES = (process.env.ENGINES || 'webkit,chromium').split(',');
const want = (sec) => !ONLY || ONLY.includes(sec);

let bad = 0, total = 0, ran = 0;
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length))); }
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : ''));
}

async function open(ctx, model) {
  const page = await ctx.newPage();
  page._errs = [];
  page.on('pageerror', e => page._errs.push(e.message));
  await page.goto(`${BASE}/calc2/?m=${model}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  if (!(await page.evaluate(() => typeof pickScene === 'function'))) { console.log('calc2 не загрузился'); process.exit(3); }
  ok(model + ' ' + page.viewportSize().width + ': предусловие: «Ответ» открыт (#params-panel > .side-inner видна)', await answerShown(page));
  await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
  return page;
}
const fieldState = (page, id) => page.evaluate((id) => ({
  v: document.getElementById(id).value,
  a: document.activeElement && document.activeElement.id,
  A: STATE.ansA, B: STATE.ansB, segA: _ansSeg && _ansSeg.a, segB: _ansSeg && _ansSeg.b,
}), id);

// Набор text посимвольно с паузами; noise — помеха между цифрами. Возвращает «фокус держался».
async function typeSlow(page, id, text, noise) {
  await page.click('#' + id, { clickCount: 3 });
  await page.waitForTimeout(300);
  let held = true, last = null;
  for (const ch of text) {
    await page.keyboard.type(ch);
    await page.waitForTimeout(300);
    if (noise) { await page.evaluate(noise); await page.waitForTimeout(300); }
    last = await fieldState(page, id);
    if (last.a !== id) held = false;
  }
  return { held, last };
}
// Помеха: строка «хочет» переехать (чужой узел встал между #graph-rows и строкой) и перерисовка.
const NOISE = () => {
  const gr = document.getElementById('graph-rows');
  let n = document.getElementById('__probe_wedge');
  if (!n) { n = document.createElement('div'); n.id = '__probe_wedge'; }
  gr.after(n);
  redrawAll();
};

async function sectionA(ctx, eng) {
  head(`А · ${eng}: поля отрезка «Построения графиков»`);
  for (const noisy of [false, true]) {
    const tag = noisy ? ' (с помехой)' : '';
    const page = await open(ctx, 'm-graph');
    const steps = [['ans-a', '-60', -60, 'A'], ['ans-b', '200', 200, 'B'], ['ans-b', '50', 50, 'B']];
    for (const [id, text, num, key] of steps) {
      const { held, last } = await typeSlow(page, id, text, noisy ? NOISE : null);
      ok(`«${text}» в «${id === 'ans-a' ? 'от' : 'до'}»${tag}: значение поля`, last.v === text, `«${last.v}»`);
      ok(`«${text}»${tag}: фокус в поле до Enter`, held, `activeElement = ${last.a}`);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(500);
      const s = await fieldState(page, id);
      ok(`«${text}»${tag}: после Enter STATE.ans${key} = ${num}`, s[key] === num, `ansA ${s.A}, ansB ${s.B}`);
      ok(`«${text}»${tag}: отрезок ответа пересчитан`, (key === 'A' ? s.segA : s.segB) === num, `_ansSeg ${s.segA}…${s.segB}`);
    }
    // Уход из строки щелчком (не Enter) тоже применяет.
    const { last } = await typeSlow(page, 'ans-b', '80', noisy ? NOISE : null);
    ok(`«80»${tag}: набрано`, last.v === '80', `«${last.v}»`);
    await page.click('#graph-wrap', { position: { x: 30, y: 30 } });
    await page.waitForTimeout(600);
    const s = await fieldState(page, 'ans-b');
    ok(`«80»${tag}: уход щелчком применяет`, s.B === 80 && s.segB === 80, `ansB ${s.B}, _ansSeg.b ${s.segB}`);
    ok(`ошибок страницы нет${tag}`, page._errs.length === 0, page._errs.slice(0, 2).join(' | '));
    await page.close();
  }
}

async function sectionB(browser, eng) {
  head(`Б · ${eng}: поле «Сначала сам» целиком в колонке`);
  for (const W of [1280, 1440]) for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: W, height: 860 }, colorScheme: scheme });
    const page = await open(ctx, 'm-graph');
    await page.click('#btn-self');
    await page.waitForTimeout(800);
    const tag = `${W}, ${scheme === 'dark' ? 'тёмная' : 'светлая'}`;
    const found = await page.evaluate(() => {
      const c = [...document.querySelectorAll('#ans-hero .ans-cell')]
        .find(c => /Пересекает ось/.test((c.querySelector('.ans-lab') || {}).textContent || ''));
      const i = c && c.querySelector('.self-row .self-inp');
      if (i) i.id = '__probe_self';
      return !!i;
    });
    ok(`${tag}: есть поле ячейки «Пересекает ось x»`, found);
    if (!found) { await ctx.close(); continue; }
    await page.click('#__probe_self');
    await page.keyboard.type('2; -2', { delay: 60 });
    await page.waitForTimeout(200);
    const measure = () => page.evaluate(() => {
      const i = document.getElementById('__probe_self');
      const btn = i.closest('.self-row').querySelector('.self-check');
      // Видимая область: пересечение коробок обрезки всех предков с overflow ≠ visible.
      let L = -1e9, R = 1e9, T = -1e9, B = 1e9, sl = 0;
      for (let p = i.parentElement; p && p !== document.documentElement; p = p.parentElement) {
        const cs = getComputedStyle(p);
        sl = Math.max(sl, p.scrollLeft);
        if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
          const r = p.getBoundingClientRect();
          const l = r.left + p.clientLeft, t = r.top + p.clientTop;
          L = Math.max(L, l); R = Math.min(R, l + p.clientWidth);
          T = Math.max(T, t); B = Math.min(B, t + p.clientHeight);
        }
      }
      const ir = i.getBoundingClientRect(), br = btn.getBoundingClientRect();
      const col = document.querySelector('#params-panel .side-scroll');
      return {
        focus: document.activeElement === i, sl, colSl: col ? col.scrollLeft : 0,
        inp: [ir.left - 4, ir.right + 4, ir.top - 4, ir.bottom + 4], btn: [br.left, br.right, br.top, br.bottom],
        box: [L, R, T, B],
      };
    });
    const inside = (r, b) => r[0] >= b[0] - 0.5 && r[1] <= b[1] + 0.5 && r[2] >= b[2] - 0.5 && r[3] <= b[3] + 0.5;
    const fmt = (r) => r.map(v => Math.round(v * 10) / 10).join(', ');
    const m1 = await measure();
    ok(`${tag}: фокус в поле после набора`, m1.focus);
    ok(`${tag}: прокрутка колонки по горизонтали 0 (фокус)`, m1.sl === 0 && m1.colSl === 0, `scrollLeft ${m1.sl}`);
    ok(`${tag}: поле + 4 px кольца внутри видимой области (фокус)`, inside(m1.inp, m1.box), `поле ${fmt(m1.inp)}; видно ${fmt(m1.box)}`);
    await page.click('#__probe_self ~ .self-check, .self-row:has(#__probe_self) .self-check');
    await page.waitForTimeout(500);
    const m2 = await measure();
    ok(`${tag}: прокрутка по горизонтали 0 (после «Проверить»)`, m2.sl === 0 && m2.colSl === 0, `scrollLeft ${m2.sl}`);
    ok(`${tag}: поле + 4 px кольца внутри видимой области (после «Проверить»)`, inside(m2.inp, m2.box), `поле ${fmt(m2.inp)}; видно ${fmt(m2.box)}`);
    ok(`${tag}: «Проверить» целиком видна`, inside(m2.btn, m2.box), `кнопка ${fmt(m2.btn)}; видно ${fmt(m2.box)}`);
    if (process.env.SHOTS) {
      await page.focus('#__probe_self');
      await page.screenshot({ path: `${process.env.SHOTS}/self_${eng}_${W}_${scheme}.png`, clip: { x: W - 380, y: 0, width: 380, height: 520 } });
    }
    ok(`${tag}: ошибок страницы нет`, page._errs.length === 0, page._errs.slice(0, 2).join(' | '));
    await ctx.close();
  }
}

for (const eng of ENGINES) {
  const bt = eng === 'webkit' ? webkit : chromium;
  let browser;
  try { browser = keepAnswerOpen(await bt.launch()); }   // «Ответ» открыт (ADR 0150, answer_open.mjs)
  catch (e) { console.log(`\n!!! ${eng} не запускается — НЕ ПРОВЕРЕНО в этом движке (npx playwright install ${eng})`); continue; }
  ran++;
  if (want('А')) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await sectionA(ctx, eng);
    await ctx.close();
  }
  if (want('Б')) await sectionB(browser, eng);
  await browser.close();
}

console.log(`\nИТОГ: ${total - bad} из ${total}` + (bad ? ` — ПРОВАЛОВ ${bad}` : ''));
process.exit(ran === 0 ? 2 : (bad ? 1 : 0));
