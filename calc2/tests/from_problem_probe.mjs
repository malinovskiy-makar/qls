/* ВХОД В «ГРАФИКИ» ИЗ ЗАДАЧИ: /calc2/?m=<модель>&from=<id задачи> (ADR 0145).

   Кнопка «Построить в «Графиках»» на странице задачи каталога ведёт сюда.
   Вход живёт как открытая ссылка «Поделиться»: модель в СТАРТОВОМ виде,
   автосохранение этой модели не затирается, пока человек не начнёт править;
   с первой правки `from` уходит из адреса. Над холстом — «← Вернуться к задаче».

   Проверки:
     1. каждый ключ модели из catalog/calc2_link.py: открыта эта модель, строка
        видна, адрес /catalog/problem/1/, ошибок страницы 0;
     2. автосохранение taxes: вход из задачи — старт на экране, запись прежняя
        побайтно; перезагрузка без правок — снова старт и запись прежняя; одна
        правка — `from` ушёл, запись = новое состояние; смена модели — строки нет;
     3. from=abc / 1x / 1234567890 — строки нет, модель открыта; m=нет_такой&from=5 —
        экран выбора; ошибок 0;
     4. 390 px: строка видна и целиком в окне, горизонтальной прокрутки нет;
     5. подпись отрезка «Площадей» у sd после «D»: «на отрезке [0; 100]»
        (дефект «на отрезке[0 ;100]», карточка Notion 3f4b11c9-…-c7349a9ff247).

   Запуск: node calc2/tests/from_problem_probe.mjs [http://127.0.0.1:8099]
   (сервер с --settings=config.settings_check). Код возврата 1 при любой
   проваленной проверке. */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const BASE = process.argv[2] || 'http://127.0.0.1:8099';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const STORE_KEY = 'calc2.v1.model.taxes';

// Ключи моделей — из таблиц модуля каталога (строки «'…': 'ключ',»; имена
// моделей в MODEL_NAMES кириллицей и под шаблон не подпадают).
const linkPy = fs.readFileSync(path.join(ROOT, 'catalog', 'calc2_link.py'), 'utf8');
const tables = linkPy.slice(linkPy.indexOf('TAG_TO_MODEL = {'), linkPy.indexOf('MODEL_NAMES = {'));
const KEYS = [...new Set([...tables.matchAll(/^\s+'[^']+': '([a-z0-9-]+)',$/gm)].map(m => m[1]))].sort();

const fails = [];
const ok = (cond, msg) => { if (!cond) fails.push(msg); };

const browser = await chromium.launch();

async function context(viewport) {
  const ctx = await browser.newContext({ viewport: viewport || { width: 1440, height: 760 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript(() => { try { if (!localStorage.getItem('theme')) localStorage.setItem('theme', 'light'); } catch (e) {} });
  const page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
  return { ctx, page, errors };
}
async function open(page, query) {
  await page.goto(BASE + '/calc2/' + query, { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object');
  await page.waitForTimeout(900);   // затишье истории 300 мс и досчёт сцены
}
const back = (page) => page.evaluate(() => {
  const a = document.getElementById('cv-back');
  return { shown: !!a && !a.hidden && a.getBoundingClientRect().height > 0, href: a ? a.getAttribute('href') : null };
});
const record = (page) => page.evaluate((k) => localStorage.getItem(k), STORE_KEY);
const fromInUrl = (page) => page.evaluate(() => new URLSearchParams(location.search).has('from'));

// 1. Все модели из таблиц.
{
  const { ctx, page, errors } = await context();
  for (const key of KEYS) {
    await open(page, '?m=' + encodeURIComponent(key) + '&from=1');
    const sk = await page.evaluate(() => STATE.sceneKey);
    const b = await back(page);
    ok(sk === key, 'модель ' + key + ': открыта ' + sk);
    ok(b.shown && b.href === '/catalog/problem/1/', 'модель ' + key + ': строка возврата ' + JSON.stringify(b));
  }
  ok(!errors.length, 'модели: ошибки страницы ' + errors.join(' | '));
  console.log('1. моделей проверено: ' + KEYS.length);
  await ctx.close();
}

// 2. Автосохранение не затирается до первой правки.
{
  const { ctx, page, errors } = await context();
  await open(page, '?m=taxes');
  const start = await page.evaluate(() => STATE.tax);
  await page.evaluate(() => { setToolsOpen(true); setParamsOpen(true); });
  await page.focus('#tax-slider');
  for (let i = 0; i < 5; i++) await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(1300);
  const saved = await record(page);
  const edited = await page.evaluate(() => STATE.tax);
  ok(saved && edited !== start, 'автосохранение: правка ставки не записалась ' + JSON.stringify([start, edited, !!saved]));

  await open(page, '?m=taxes&from=5');
  ok(await page.evaluate(() => STATE.tax) === start, 'из задачи: ставка не стартовая');
  ok(await record(page) === saved, 'из задачи: запись автосохранения изменилась без правки');
  ok((await back(page)).href === '/catalog/problem/5/', 'из задачи: адрес строки возврата');

  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function'); await page.waitForTimeout(900);
  ok(await page.evaluate(() => STATE.tax) === start, 'перезагрузка без правок: ставка не стартовая');
  ok(await record(page) === saved, 'перезагрузка без правок: запись изменилась');
  ok(await fromInUrl(page), 'перезагрузка без правок: from пропал из адреса');

  await page.evaluate(() => { setToolsOpen(true); setParamsOpen(true); });
  await page.focus('#tax-slider');
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(1300);
  const after = await record(page);
  const now = await page.evaluate(() => STATE.tax);
  ok(!(await fromInUrl(page)), 'первая правка: from остался в адресе');
  ok(after && after !== saved && JSON.parse(after).s.state.tax === now, 'первая правка: запись не равна новому состоянию');
  ok((await back(page)).shown, 'первая правка: строка возврата пропала, а модель та же');
  ok(/[?&]m=taxes(&|$)/.test(await page.evaluate(() => location.search)), 'первая правка: потерян ?m=');

  await page.evaluate(() => openModelByUser('sd')); await page.waitForTimeout(600);
  ok(!(await back(page)).shown, 'смена модели: строка возврата осталась');
  ok(!errors.length, 'автосохранение: ошибки страницы ' + errors.join(' | '));
  console.log('2. автосохранение: старт ' + start + ', правка ' + edited + ', после входа из задачи ' + now);
  await ctx.close();
}

// 3. Чужой from и чужая модель.
{
  const { ctx, page, errors } = await context();
  for (const bad of ['abc', '1x', '1234567890', '', '-1', '1.5']) {
    await open(page, '?m=ceil&from=' + encodeURIComponent(bad));
    const r = await page.evaluate(() => STATE.sceneKey);
    ok(r === 'ceil' && !(await back(page)).shown, 'from=' + JSON.stringify(bad) + ': ' + r);
  }
  await open(page, '?m=' + encodeURIComponent('нет_такой') + '&from=5');
  const picker = await page.evaluate(() => {
    const p = document.getElementById('scene-picker');
    return !!p && !p.classList.contains('hidden') && !STATE.sceneKey;
  });
  ok(picker && !(await back(page)).shown, 'm=нет_такой: не экран выбора');
  ok(!errors.length, 'чужой from: ошибки страницы ' + errors.join(' | '));
  await ctx.close();
}

// 4. Телефон 390.
{
  const { ctx, page, errors } = await context({ width: 390, height: 844 });
  await open(page, '?m=taxes&from=1');
  const r = await page.evaluate(() => {
    const a = document.getElementById('cv-back').getBoundingClientRect();
    const svg = document.getElementById('chart').getBoundingClientRect();
    return { top: a.top, bottom: a.bottom, h: a.height, left: a.left, right: a.right,
             svgW: Math.round(svg.width), svgH: Math.round(svg.height),
             sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth };
  });
  ok(r.h >= 44 && r.top >= 0 && r.bottom <= 844 && r.left >= 0 && r.right <= 390, '390: строка возврата не в окне ' + JSON.stringify(r));
  ok(r.sw <= r.cw, '390: горизонтальная прокрутка ' + r.sw + ' > ' + r.cw);
  ok(!errors.length, '390: ошибки страницы ' + errors.join(' | '));
  console.log('4. 390: строка ' + Math.round(r.h) + ' px, холст ' + r.svgW + '×' + r.svgH);
  await ctx.close();
}

// 5. Подпись отрезка площади (sd → «Точки и площади» → «+ Под кривой» → «D»).
/* С 13.10 (ADR 0148) раздел «Площади» живёт в панели режима: без входа в режим он не на
   экране, и замер зазоров по невидимым узлам дал бы нули, то есть «прошёл» бы вхолостую. */
{
  const { ctx, page, errors } = await context();
  await open(page, '?m=sd');
  const text = await page.evaluate(async () => {
    setToolsOpen(true);
    setPtsMode(true);
    const mode = document.getElementById('ac-curve');
    if (mode) mode.click();
    await new Promise(r => setTimeout(r, 300));
    const d = [...document.querySelectorAll('#ac-pick-btns .ac-cbtn')].find(b => b.dataset.name === 'D');
    if (d) d.click();
    await new Promise(r => setTimeout(r, 400));
    const el = document.getElementById('ac-range');
    if (!el) return null;
    // Невидимая копия формулы KaTeX для чтецов экрана утроила бы цифры (calc2/CLAUDE.md).
    const c = el.cloneNode(true);
    c.querySelectorAll('.katex-mathml, annotation').forEach(n => n.remove());
    return c.textContent.replace(/\s+/g, ' ').trim();
  });
  // Зазоры глазом: «[» вплотную к «0», «0» вплотную к «;» (не больше 1,5 px).
  const gaps = await page.evaluate(() => {
    const el = document.getElementById('ac-range');
    const kids = [...el.children];
    const open = kids.find(k => k.textContent === '['), semi = kids.find(k => k.textContent.trim() === ';');
    const vals = kids.filter(k => k.classList.contains('edval'));
    if (!open || !semi || vals.length !== 2) return null;
    const R = (n) => n.getBoundingClientRect();
    const ink = (n) => { const r = document.createRange(); r.selectNodeContents(n); return r.getBoundingClientRect(); };
    return { openToVal: Math.round((ink(vals[0]).left - R(open).right) * 10) / 10,
             valToSemi: Math.round((R(semi).left - ink(vals[0]).right) * 10) / 10 };
  });
  const shown = await page.evaluate(() => !!document.getElementById('ac-range').getClientRects().length);
  ok(shown, 'подпись отрезка не на экране (панель режима не открыта)');
  ok(gaps && gaps.openToVal <= 1.5 && gaps.valToSemi <= 1.5, 'подпись отрезка, зазоры: ' + JSON.stringify(gaps));
  ok(text === 'на отрезке [0; 100]', 'подпись отрезка: ' + JSON.stringify(text));
  ok(!errors.length, 'подпись отрезка: ошибки страницы ' + errors.join(' | '));
  console.log('5. подпись отрезка: ' + JSON.stringify(text) + ', зазоры ' + JSON.stringify(gaps));
  await ctx.close();
}

await browser.close();
if (fails.length) {
  console.log('ПРОВАЛЕНО ' + fails.length + ':');
  fails.forEach(f => console.log('  x ' + f));
  process.exit(1);
}
console.log('from_problem_probe: все проверки зелёные');
