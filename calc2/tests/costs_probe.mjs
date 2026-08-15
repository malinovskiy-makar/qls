// Разовый замер Фазы 1 (Б24–Б27): что показывает сцена «Издержки фирмы» на
// наборе функций TC, включая те, у которых точек закрытия и безубыточности
// физически нет. Печатает таблицу для отчёта.
//   node calc2/tests/costs_probe.mjs
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const FNS = [
  ['Q^3 - 6*Q^2 + 15*Q + 18', 'классическая U-образная'],
  ['Q^2 + 18', 'линейно растущая MC, минимума AVC нет'],
  ['20*Q', 'постоянная MC, ни минимума, ни оптимума'],
  ['Q^3 - 6*Q^2 + 15*Q', 'нулевые постоянные, AFC = 0, ATC = AVC'],
  ['0.5*Q^2 + 10*Q + 50', 'минимум AVC на краю, у ATC минимум есть'],
  ['Q^2*sqrt(Q) + 30', 'нецелая степень'],
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);

const rows = [];
for (const [tc, note] of FNS) {
  const r = await page.evaluate((tcExpr) => {
    resetSceneMemory();
    pickScene('costs');
    STATE.costsTC = tcExpr; STATE.lrOn = true; STATE.lrPrice = 15.54;
    redrawAll();
    const box = document.getElementById('info-costs');
    const text = (box ? box.innerText : '').replace(/\s+/g, ' ').trim();
    const fi = STATE.costsFCInfo || {};
    const lr = STATE.lr || {};
    return {
      fc: fi.kind + (isFinite(fi.val) ? (' = ' + fi.val.toFixed(2)) : ''),
      atcKind: (STATE.minATC || {}).kind || 'нет',
      atcQ: (STATE.minATC || {}).Q,
      avcKind: (STATE.minAVC || {}).kind || 'нет',
      avcQ: (STATE.minAVC || {}).Q,
      lrQ: lr.Q, shutdown: !!lr.shutdown, note: lr.note ? lr.note.slice(0, 70) : '',
      panel: text.slice(0, 400),
    };
  }, tc);
  rows.push([tc, note, r]);
}
await browser.close();

for (const [tc, note, r] of rows) {
  console.log('\n=== TC = ' + tc + '   (' + note + ')');
  console.log('  FC:        ' + r.fc);
  console.log('  min ATC:   ' + r.atcKind + (r.atcKind === 'interior' ? ' Q=' + r.atcQ.toFixed(2) : ''));
  console.log('  min AVC:   ' + r.avcKind + (r.avcKind === 'interior' ? ' Q=' + r.avcQ.toFixed(2) : ''));
  console.log('  выпуск:    ' + (r.lrQ == null ? 'нет оптимума' : r.lrQ.toFixed(2)) + (r.shutdown ? ' (закрытие)' : ''));
  if (r.note) console.log('  пояснение: ' + r.note + '…');
  console.log('  ПАНЕЛЬ:    ' + r.panel);
}
