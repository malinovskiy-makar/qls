// Матрица покрытия «общая фича × сцена». Только чтение: ничего не меняет,
// открывает каждую карточку окна сценариев и смотрит, какие общие механизмы
// в ней реально доступны.
//
//   ./venv/Scripts/python.exe manage.py runserver 8099 --noreload
//   node calc2/tests/audit_matrix.mjs > reports/calc2_matrix_before.md
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));

await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(1200);

const scenes = await page.$$eval('.scard:not(.soon)', els =>
  els.map(e => [e.dataset.scene, (e.querySelector('.scard-name') || e).textContent.trim()]));

const rows = [];
for (const [key, name] of scenes) {
  await page.evaluate(k => { pickScene(k); setToolsOpen(true); }, key);
  await page.waitForTimeout(340);
  const r = await page.evaluate(() => {
    const vis = el => !!(el && el.getClientRects().length);
    // Все видимые поля ввода формул: текстовые поля внутри видимых секций.
    // Формульным считаем поле, у которого есть подпись/подсказка про формулу
    // либо значение похоже на выражение.
    // Видимость считаем так же, как движок (fieldActive): сцена прячет секции
    // через display:none, а свёрнутая панель поля не отменяет.
    const allText = [...document.querySelectorAll('#tools-panel input[type=text]')];
    const formulaInputs = allText.filter(i => {
      if (i.classList.contains('pw-bound')) return false;   // границы куска, не формула
      if (!/^(inp-|ext-input|ma-|cons-custom|ineq-formula|mm-|gr-)/.test(i.id)) return false;
      if (/name|title|label/.test(i.id)) return false;
      return typeof fieldActive === 'function' ? fieldActive(i) : vis(i);
    });
    const upgraded = formulaInputs.filter(i => !!i._mf);
    const kbd = formulaInputs.filter(i => {
      const w = i.closest('.f-wrap');
      return !!(w && w.querySelector('.f-kbd'));
    });
    const help = formulaInputs.filter(i => {
      const w = i.closest('.f-wrap');
      return !!(w && w.querySelector('.f-help'));
    });
    let crosses = 0;
    try { crosses = (typeof crossPoints === 'function') ? crossPoints().length : 0; } catch (e) {}
    let snaps = 0;
    try { snaps = (typeof snapTargets === 'function') ? snapTargets().length : 0; } catch (e) {}
    const drawnCrosses = document.querySelectorAll('.crosses circle').length;
    const pbody = document.getElementById('params-body') || document.getElementById('params-panel');
    const ranges = pbody ? [...pbody.querySelectorAll('input[type=range]')].filter(vis).length : 0;
    const bounds = pbody ? pbody.querySelectorAll('.param-bound').length : 0;
    return {
      fields: formulaInputs.length,
      mf: upgraded.length,
      kbd: kbd.length,
      help: help.length,
      params: (typeof paramsAllowed === 'function') ? paramsAllowed() : null,
      ranges, bounds,
      roller: snaps > 0,
      snaps,
      crosses, drawnCrosses,
      katex: document.querySelectorAll('#sb-body .katex').length,
      sbLen: (document.getElementById('sb-body') || {}).textContent?.trim().length || 0,
      foldPoints: !!document.querySelector('#sec-view .fold-btn'),
      hints: [...document.querySelectorAll('#tools-panel .hint')].filter(vis).length,
      mode: STATE.mode,
    };
  });
  rows.push([key, name, r]);
}

const yn = v => v ? '+' : '–';
const frac = (a, b) => b === 0 ? '—' : (a === b ? '+ ' + a : a + '/' + b);
console.log('| Сцена | режим | LaTeX-ввод | клавиатура | «?» | параметры | ползунки: с границами / всего | прокатывание | ключевые точки | KaTeX в аналитике | абзацы-инструкции | свернуть точки |');
console.log('|---|---|---|---|---|---|---|---|---|---|---|---|');
for (const [key, name, r] of rows) {
  console.log(`| ${key} · ${name} | ${r.mode} | ${frac(r.mf, r.fields)} | ${frac(r.kbd, r.fields)} | ${frac(r.help, r.fields)} | ${yn(r.params)} | ${r.bounds} / ${r.ranges} | ${yn(r.roller)} | ${r.drawnCrosses}/${r.crosses} | ${r.katex} (текст ${r.sbLen}) | ${r.hints} | ${yn(r.foldPoints)} |`);
}
console.log('\nОшибок страницы: ' + errors.length);
errors.slice(0, 10).forEach(e => console.log('  ' + e));
await browser.close();
