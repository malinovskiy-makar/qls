// Фаза 4 — полупустое поле: конструктор кусочной не должен падать и не должен
// подставлять пустоту, когда разобрать формулу поля нечего (пусто, набрано
// наполовину, одно число). Проверка числами, ничего не чиним, если и так верно.
//   node calc2/tests/phase4_empty_field_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', e => console.log('PAGEERROR:', e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

let ok = true;
const report = (name, pass, detail) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + name + (detail ? '  -> ' + detail : '')); if (!pass) ok = false; };

const cases = [
  { scene: 'costs', field: 'inp-tc', kind: 'TC', value: '', label: 'пустое поле (TC)' },
  { scene: 'ppf', field: 'inp-ppf', kind: 'PPF', value: '100 - ', label: 'набрано наполовину «100 - » (PPF)' },
  { scene: 'sd', field: null, kind: 'DEMAND', value: '42', label: 'только число «42» (рыночный D)' },
  { scene: 'iso', field: 'inp-iso', kind: 'ISO', value: '   ', label: 'одни пробелы (ISO)' },
];

for (const c of cases) {
  const r = await page.evaluate(async ({ scene, field, kind, value }) => {
    resetSceneMemory(); pickScene(scene);
    await new Promise(res => setTimeout(res, 200));
    let inp = field ? document.getElementById(field) : null;
    if (!inp) {
      // Первая формульная строка сцены (например, спрос на рынке).
      inp = document.querySelector('.curve-expr-inp');
    }
    if (!inp) return { error: 'поле не найдено' };
    inp.value = value;
    let crashed = null, v = null, opened = null;
    try {
      const fallback = (typeof FORMULA_VAR !== 'undefined' && FORMULA_VAR[kind]) || 'x';
      v = pwVarForField(inp, fallback);
      openPiecewise(inp, v);
      opened = document.getElementById('pw-modal').classList.contains('open');
      closePiecewise();
    } catch (e) { crashed = String(e.message || e); }
    return { v, crashed, opened, fallbackExpected: (typeof FORMULA_VAR !== 'undefined' && FORMULA_VAR[kind]) || 'x' };
  }, c);
  report(c.label, !r.crashed && !!r.v && r.opened === true, JSON.stringify(r));
}

await browser.close();
console.log('\nИТОГ: ' + (ok ? 'полупустое поле ведёт себя предсказуемо' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
