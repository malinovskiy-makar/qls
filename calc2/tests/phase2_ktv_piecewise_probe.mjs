// Фаза 2 — «КТВ. Одна страна»: конструктор кусочной должен строить КТВ БЕЗ
// ручной дописки «y = ». Проверяем ЖИВЫМИ щелчками по настоящим кнопкам
// интерфейса (не evaluate-вызовом внутренних функций).
//   node calc2/tests/phase2_ktv_piecewise_probe.mjs
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

await page.evaluate(() => { resetSceneMemory(); pickScene('trade'); if (typeof setToolsOpen === 'function') setToolsOpen(true); });
await page.waitForTimeout(300);

const before = await page.evaluate(() => ({
  fieldValue: document.getElementById('inp-ppft').value,
  stateFormula: STATE.ppftFormula,
}));
report('поле КТВ изначально БЕЗ приставки "y ="', !/^\s*y\s*=/i.test(before.fieldValue), JSON.stringify(before));

// Панель ввода открывается со всеми свёрнутыми карточками (как в calc2_ui.mjs) —
// разворачиваем складные блоки над целью тем же приёмом, прежде чем щёлкать.
const reveal = async (sel) => {
  await page.evaluate((s) => {
    const el = document.querySelector(s);
    if (!el) return;
    let n = el;
    while (n && n !== document.body) {
      const foldable = n.classList && (n.classList.contains('fold-body') || n.classList.contains('picker-grid'));
      if (foldable && !n.classList.contains('open') && n.id) {
        const btn = document.querySelector('[aria-controls="' + n.id + '"]');
        if (btn) btn.click();
      }
      n = n.parentElement;
    }
    el.scrollIntoView({ block: 'center' });
  }, sel);
  await page.waitForTimeout(140);
};

// «?» у поля открывает не всплывашку с примерами, а клавиатуру (kbd) —
// у неё в подвале своя кнопка «Кусочная функция» (buildKeyboard, 82-input.js).
await reveal('#fh-auto-inp-ppft');
await page.click('#fh-auto-inp-ppft');
await page.waitForTimeout(150);
const pwOpenBtn = await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('.mkbd.open .mkbd-foot button'))
    .find(b => b.textContent.trim() === 'Кусочная функция');
  if (btn) { if (!btn.id) btn.id = '__pw_open_btn'; return '#' + btn.id; }
  return null;
});
report('нашли кнопку «Кусочная функция» в клавиатуре', !!pwOpenBtn, pwOpenBtn);
if (pwOpenBtn) await page.click(pwOpenBtn);
await page.waitForTimeout(150);

const modalOpen = await page.evaluate(() => document.getElementById('pw-modal').classList.contains('open'));
report('окно конструктора открылось', modalOpen);

// Готовые значения по умолчанию (излом в 40) уже стоят — просто «Поставить в поле».
await page.click('#pw-apply');
await page.waitForTimeout(200);

const after = await page.evaluate(() => ({
  fieldValue: document.getElementById('inp-ppft').value,
  stateFormula: STATE.ppftFormula,
  errorShown: (() => { const b = document.getElementById('ppf-error'); return b ? (b.style.display !== 'none' && !!b.textContent) : null; })(),
  parseError: (typeof parsePpfEquation === 'function') ? (parsePpfEquation(STATE.ppftFormula).error || null) : 'нет parsePpfEquation',
  tradeData: STATE.ppfTradeData ? { ok: !!STATE.ppfTradeData.ok || !!STATE.ppfTradeData.xint || Object.keys(STATE.ppfTradeData).length > 0 } : null,
  canvasPaths: document.querySelectorAll('svg#chart path').length,
}));
console.log(JSON.stringify(after, null, 2));

report('запись ушла в поле БЕЗ ручной приставки, но с изломом', after.fieldValue.indexOf('40') >= 0, after.fieldValue);
report('STATE.ppftFormula обновилась (Enter применился)', after.stateFormula === after.fieldValue, `${after.stateFormula} vs ${after.fieldValue}`);
report('parsePpfEquation принимает запись без ручной "y ="', !after.parseError, after.parseError);
report('на холсте есть нарисованные кривые', after.canvasPaths > 0, 'path: ' + after.canvasPaths);

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'КТВ строится без ручной дописки' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
