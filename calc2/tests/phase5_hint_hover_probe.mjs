// Фаза 5, пункт 1 — подсказки «?» в «Точки на графике» и «Площади»
// раскрываются по наведению и прячутся, когда мышь ушла.
//   node calc2/tests/phase5_hint_hover_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let ok = true;
const report = (name, pass, detail) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + name + (detail ? '  -> ' + detail : '')); if (!pass) ok = false; };

async function checkHover(popId, btnAriaControls, sectionBtnId) {
  await page.evaluate(({ sectionBtnId }) => {
    resetSceneMemory(); pickScene('sd');
    if (typeof setToolsOpen === 'function') setToolsOpen(true);
    const btn = document.getElementById(sectionBtnId);
    if (btn && btn.getAttribute('aria-expanded') !== 'true') btn.click();
  }, { sectionBtnId });
  await page.waitForTimeout(200);
  const box = await page.evaluate((pid) => {
    const btn = document.querySelector('[data-pop="' + pid + '"]');
    const r = btn.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, popId);
  const before = await page.evaluate((pid) => document.getElementById(pid).classList.contains('open'), popId);
  await page.mouse.move(box.x, box.y);
  await page.waitForTimeout(80);
  const hovered = await page.evaluate((pid) => document.getElementById(pid).classList.contains('open'), popId);
  await page.mouse.move(5, 5);
  await page.waitForTimeout(300);
  const after = await page.evaluate((pid) => document.getElementById(pid).classList.contains('open'), popId);
  return { before, hovered, after };
}

const marks = await checkHover('hp-marks', null, 'marks-btn');
report('«Точки на графике»: закрыта без наведения', marks.before === false, JSON.stringify(marks));
report('«Точки на графике»: открылась по наведению', marks.hovered === true, JSON.stringify(marks));
report('«Точки на графике»: закрылась, когда мышь ушла', marks.after === false, JSON.stringify(marks));

const areas = await checkHover('hp-areascalc', null, 'areascalc-btn');
report('«Площади»: закрыта без наведения', areas.before === false, JSON.stringify(areas));
report('«Площади»: открылась по наведению', areas.hovered === true, JSON.stringify(areas));
report('«Площади»: закрылась, когда мышь ушла', areas.after === false, JSON.stringify(areas));

// Контроль: щелчок (доступность с клавиатуры/на сенсорном экране) по-прежнему работает.
const clickStill = await page.evaluate(() => {
  const btn = document.querySelector('[data-pop="hp-marks"]');
  const pop = document.getElementById('hp-marks');
  btn.click();
  const opened = pop.classList.contains('open');
  btn.click();
  const closed = !pop.classList.contains('open');
  return { opened, closed };
});
report('щелчок по «?» по-прежнему открывает/закрывает (доступность)', clickStill.opened && clickStill.closed, JSON.stringify(clickStill));

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'подсказки раскрываются по наведению' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
