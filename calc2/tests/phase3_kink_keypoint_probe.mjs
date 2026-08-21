// Фаза 3 — излом кусочной функции обязан вести себя как обычная ключевая
// точка: без наведения — просто серая точка, по наведению — подпись с
// координатами и значок закрепки, как у пересечения с осью.
//   node calc2/tests/phase3_kink_keypoint_probe.mjs
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

// Сцена «Совершенная конкуренция» с готовой кусочной кривой D: излом даёт
// сам конструктор задачи — используем пример из аудита ("Q < 40 ? … : …").
const setup = await page.evaluate(() => {
  resetSceneMemory();
  pickScene('sd');
  const D = STATE.curves.find(c => c.role === 'demand');
  D.expr = 'Q < 40 ? 100 - Q : 80 - 0.5*Q';
  D.compiled = compileFormula(D.expr).compiled;
  D.linear = null;
  invalidateKeyTargets();
  redrawAll();
  armCurve(curveShortName(D));
  const kink = keyTargets().find(p => p.kind === 'kink');
  return { kink: kink ? { x: kink.x, y: kink.y, name: kink.name } : null, armed: STATE.armedCurve };
});
report('излом найден и кривая взведена', !!setup.kink && !!setup.armed, JSON.stringify(setup));

await page.waitForTimeout(300);

// Экранные координаты излома.
const px = await page.evaluate(() => {
  const s = mainScales();
  const p = keyTargets().find(k => k.kind === 'kink');
  const rect = document.getElementById('chart').getBoundingClientRect();
  return { x: rect.left + s.mx(p.x), y: rect.top + s.my(p.y) };
});

// До наведения: подписи с координатами быть не должно — точка серая, без плашки.
const before = await page.evaluate(() => {
  const labs = [...document.querySelectorAll('.crosses .cross-label')];
  return { visibleLabels: labs.filter(l => getComputedStyle(l).display !== 'none').length,
           kinkAxisEls: document.querySelectorAll('.kink-axis').length,
           dashedLines: [...document.querySelectorAll('.crosses > line')].length };
});
report('до наведения подписи скрыты', before.visibleLabels === 0, JSON.stringify(before));
report('нет больше самостийного пунктира к осям у излома', before.kinkAxisEls === 0 && before.dashedLines === 0, JSON.stringify(before));

// Наведение на излом.
await page.mouse.move(px.x, px.y);
await page.waitForTimeout(200);
const hovered = await page.evaluate(() => {
  const labs = [...document.querySelectorAll('.crosses .cross-label')];
  const visible = labs.find(l => getComputedStyle(l).display !== 'none');
  const pin = visible ? visible.querySelector('.cross-pin') : null;
  return { visibleCount: labs.filter(l => getComputedStyle(l).display !== 'none').length,
           text: visible ? visible.textContent.trim() : null, hasPin: !!pin };
});
report('по наведению всплыла подпись с координатами', hovered.visibleCount === 1 && /\(.*;.*\)/.test(hovered.text || ''), JSON.stringify(hovered));
report('у подписи есть значок правки (закрепки)', hovered.hasPin, JSON.stringify(hovered));

// Щелчок по значку закрепки добавляет точку в список.
const before2 = await page.evaluate(() => (STATE.marks || []).length);
await page.evaluate(() => {
  const lab = [...document.querySelectorAll('.crosses .cross-label')].find(l => getComputedStyle(l).display !== 'none');
  const pin = lab.querySelector('.cross-pin');
  pin.dispatchEvent(new MouseEvent('click', { bubbles: true }));
});
await page.waitForTimeout(150);
const after2 = await page.evaluate(() => (STATE.marks || []).length);
report('щелчок по значку закрепляет излом в список точек', after2 === before2 + 1, `${before2} -> ${after2}`);

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'излом ведёт себя как обычная ключевая точка' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
