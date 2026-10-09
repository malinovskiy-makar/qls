/* Снимки приёмки сессии «Математика 2» (ADR 0143), 1440 × 900, светлая тема:
     node calc2/tests/math_shots.mjs [папка]        (по умолчанию reports/calc2_math)
   1-graph-start.png      — «Построение графиков» на старте (окно по функции);
   2-self-hover-root.png  — «Сначала сам», наведение на корень: «(?; ?)»;
   3-self-after-answer.png — после верного «2; −2»: «(2; 0)», закрепка доступна.
   Нужен сервер на 8099 (settings_check). */
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const DIR = process.argv[2] || 'reports/calc2_math';
fs.mkdirSync(DIR, { recursive: true });

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
await page.evaluate(() => { if (typeof setCalcTheme === 'function') setCalcTheme('light'); resetSceneMemory(); });
await page.goto(`${BASE}/calc2/?m=m-graph`, { waitUntil: 'networkidle' });
await page.waitForTimeout(2500);   // окно «Построения графиков» успевает устояться
await page.screenshot({ path: `${DIR}/1-graph-start.png` });

// «Сначала сам»: взвести кривую щелчком и навести на корень (2; 0).
await page.click('#btn-self');
await page.waitForTimeout(400);
const hover = async (x, y) => {
  const p = await page.evaluate(([x, y]) => {
    const { mx, my } = mainScales();
    const r = document.getElementById('chart').getBoundingClientRect();
    return [r.left + mx(x), r.top + my(y)];
  }, [x, y]);
  await page.mouse.move(p[0], p[1]);
  await page.waitForTimeout(350);
  return p;
};
const arm = async () => {
  // Щелчок по кривой в точке x = 3 (не ключевая): кривая взводится.
  const p = await page.evaluate(() => {
    const { mx, my } = mainScales();
    const r = document.getElementById('chart').getBoundingClientRect();
    return [r.left + mx(3), r.top + my(5)];
  });
  await page.mouse.click(p[0], p[1]);
  await page.waitForTimeout(400);
};
await arm();
await hover(2, 0);
await page.screenshot({ path: `${DIR}/2-self-hover-root.png` });

// Верный ответ на ось x: «2; −2».
const cellInput = await page.evaluateHandle(() => {
  // Ось величины — data-not (с сессии 3 у математики обозначение не выносится в значение, ADR 0144).
  const c = [...document.querySelectorAll('#ans-hero .ans-cell')].find(c => /ось/.test(c.textContent) && c.dataset.not === 'x');
  return c ? c.querySelector('.self-inp') : null;
});
if (cellInput && (await cellInput.evaluate(e => !!e))) {
  await cellInput.asElement().fill('2; −2');
  await cellInput.asElement().press('Enter');
  await page.waitForTimeout(400);
}
await page.mouse.move(5, 5);
await page.waitForTimeout(300);
if (!(await page.evaluate(() => !!STATE.armedCurve))) await arm();
await hover(2, 0);
await page.screenshot({ path: `${DIR}/3-self-after-answer.png` });

if (errs.length) console.log('ОШИБКИ: ' + errs.slice(0, 5).join(' | '));
console.log('снимки: ' + DIR);
await browser.close();
