// Фаза 5, пункт 2 — при вводе координаты своей точки подпись «x = » не
// должна пропадать; исчезать полагается только плейсхолдеру «?».
//   node calc2/tests/phase5_coord_prefix_probe.mjs
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

await page.evaluate(() => {
  resetSceneMemory(); pickScene('sd');
  if (typeof setToolsOpen === 'function') setToolsOpen(true);
  const btn = document.getElementById('marks-btn');
  if (btn && btn.getAttribute('aria-expanded') !== 'true') btn.click();
});
await page.waitForTimeout(200);
// «Добавить точку» -> координатами.
await page.evaluate(() => {
  const add = document.querySelector('.btn-mark-add');
  if (add) add.click();
});
await page.waitForTimeout(150);
await page.evaluate(() => {
  const seg = document.querySelector('#mark-list .tgl-lab');
  // Тумблер уже стоит на «Ввести координаты» по умолчанию — просто найдём поле X.
});
await page.waitForTimeout(100);

const before = await page.evaluate(() => {
  const row = document.querySelector('#mark-list .mark-row');
  const pfx = row ? row.querySelector('.mark-num-prefix') : null;
  return { hasPrefix: !!pfx, prefixText: pfx ? (pfx.querySelector('.katex-html') || pfx).textContent.trim() : null };
});
report('до правки приставка «x =» на месте', before.hasPrefix, JSON.stringify(before));

// Кликаем в редактируемое значение X и печатаем цифру.
await page.evaluate(() => {
  const row = document.querySelector('#mark-list .mark-row');
  const val = row.querySelector('.edval');
  val.click();
});
await page.waitForTimeout(100);
const mid = await page.evaluate(() => {
  const row = document.querySelector('#mark-list .mark-row');
  const pfx = row.querySelector('.mark-num-prefix');
  const val = row.querySelector('.edval');
  return { prefixVisible: !!pfx && pfx.offsetParent !== null, prefixText: (pfx.querySelector('.katex-html') || pfx).textContent.trim(),
           editing: val.classList.contains('editing'), valueText: val.textContent };
});
report('приставка «x =» осталась видна ВО ВРЕМЯ правки', mid.prefixVisible && /Q/.test(mid.prefixText), JSON.stringify(mid));
report('редактируемое поле реально в режиме правки', mid.editing, JSON.stringify(mid));

await page.keyboard.type('55');
await page.waitForTimeout(100);
const typed = await page.evaluate(() => {
  const row = document.querySelector('#mark-list .mark-row');
  const pfx = row.querySelector('.mark-num-prefix');
  const val = row.querySelector('.edval');
  return { prefixText: (pfx.querySelector('.katex-html') || pfx).textContent.trim(), valueText: val.textContent.trim() };
});
report('после набора «55» приставка всё ещё «x =», значение — «55»', /Q/.test(typed.prefixText) && typed.valueText === '55', JSON.stringify(typed));

await page.keyboard.press('Enter');
await page.waitForTimeout(150);
const after = await page.evaluate(() => {
  const row = document.querySelector('#mark-list .mark-row');
  const mk = (STATE.marks || [])[0];
  return { x: mk ? mk.x : null };
});
report('координата действительно применилась', after.x === 55, JSON.stringify(after));

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'приставка не пропадает' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
