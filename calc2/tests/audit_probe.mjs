// Разведка DOM: какие поля ввода и вспомогательные кнопки реально видны в сцене.
import { chromium } from 'playwright';
const BASE = 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin');
await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

for (const key of (process.argv[2] || 'free,sd,ppf,m-tangent,costs').split(',')) {
  await page.evaluate(k => { pickScene(k); setToolsOpen(true); }, key);
  await page.waitForTimeout(400);
  const r = await page.evaluate(() => {
    const vis = el => !!(el && el.getClientRects().length);
    const tp = document.getElementById('tools-panel');
    return {
      toolsPanelClass: tp ? tp.className : 'НЕТ',
      allInputs: [...document.querySelectorAll('#tools-panel input')].map(i => `${i.type}#${i.id}${vis(i) ? '' : '(скрыт)'}`),
      mathFields: [...document.querySelectorAll('math-field')].map(m => (m.id || m.className) + (vis(m) ? '' : '(скрыт)')),
      btnClasses: [...new Set([...document.querySelectorAll('#tools-panel button')].filter(vis).map(b => b.className))],
      visibleSections: [...document.querySelectorAll('#tools-panel .section')].filter(vis).map(s => s.id),
      hints: [...document.querySelectorAll('#tools-panel .hint')].filter(vis).length,
      paramsPanel: [...document.querySelectorAll('#params-panel input, #params-body input, .params-body input')].map(i => i.type + '#' + i.id),
      paramsIds: [...document.querySelectorAll('[id*="param"]')].map(e => e.id),
    };
  });
  console.log('\n===== ' + key + ' =====');
  console.log(JSON.stringify(r, null, 1));
}
await browser.close();
