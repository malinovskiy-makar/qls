// Замер Фазы 5 (Б12, Б39, Б40): сколько строк табло, где значение налезает на
// подпись, и сколько составных значений осталось в ячейке для числа.
//   node calc2/tests/panel_overlap_probe.mjs
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

const keys = await page.evaluate(() =>
  Object.keys(SCENE_ROUTE).filter(k => !(SCENE_ROUTE[k] || {}).soon));

let overlaps = 0, composite = 0, rows = 0;
const bad = [];
for (const k of keys) {
  const r = await page.evaluate(async (key) => {
    resetSceneMemory();
    pickScene(key);
    // Оба блока правой панели свёрнуты по умолчанию — раскрываем.
    ['sb-btn', 'ex-btn'].forEach(id => {
      const b = document.getElementById(id);
      if (b && b.getAttribute('aria-expanded') !== 'true') b.click();
    });
    await new Promise(res => setTimeout(res, 260));
    const out = { rows: 0, over: [], comp: [] };
    document.querySelectorAll('.sb-body .stat').forEach(row => {
      const lab = row.querySelector(':scope > span');
      const val = row.querySelector(':scope > b');
      if (!lab || !val) return;
      /* Мерим НАПЕЧАТАННЫЙ текст, а не коробку. У подписи колонка может
         сжаться до нуля (minmax(0, 1fr)), но сам текст при этом никуда не
         девается и вылезает за свою колонку — ровно это и видно глазом.
         getBoundingClientRect у элемента отдал бы пустую коробку и наложения
         не заметил; Range по содержимому отдаёт настоящие чернила. */
      const inkOf = (el) => {
        const r = document.createRange(); r.selectNodeContents(el);
        const b = r.getBoundingClientRect();
        return (b.width > 0 && b.height > 0) ? b : el.getBoundingClientRect();
      };
      const lr = inkOf(lab), vr = inkOf(val);
      if (!(lr.width > 0 && vr.width > 0)) return;
      out.rows++;
      // Налезание: прямоугольники подписи и значения пересекаются по обеим осям.
      const overX = Math.min(lr.right, vr.right) - Math.max(lr.left, vr.left);
      const overY = Math.min(lr.bottom, vr.bottom) - Math.max(lr.top, vr.top);
      if (overX > 1 && overY > 1 && !row.classList.contains('stat-stack'))
        out.over.push((lab.textContent || '').trim().slice(0, 34));
      /* Составное значение, оставшееся в ячейке для числа. У значения, которое
         сцена набрала формулой сама (.stat-own), textContent это тройка
         «MathML + исходная запись + видимый текст» — читаем только видимое,
         иначе один знак равенства сходит за два. */
      const vis = row.classList.contains('stat-own')
        ? Array.from(val.querySelectorAll('.katex-html')).map(e => e.textContent).join(' ').trim()
        : (val.textContent || '').trim();
      const raw = vis;
      if (!row.classList.contains('stat-stack') && /=[^=]*[,;][^=]*=/.test(raw))
        out.comp.push((lab.textContent || '').trim().slice(0, 34));
    });
    return out;
  }, k);
  rows += r.rows;
  overlaps += r.over.length;
  composite += r.comp.length;
  if (r.over.length || r.comp.length) bad.push(`${k}: налезаний ${r.over.length} ${r.over.join(' / ')}  составных ${r.comp.length} ${r.comp.join(' / ')}`);
}
await browser.close();
console.log('строк табло всего:               ' + rows + ' (сцен ' + keys.length + ')');
console.log('значение налезает на подпись:    ' + overlaps);
console.log('составных в ячейке для числа:    ' + composite);
bad.forEach(b => console.log('  ' + b));
