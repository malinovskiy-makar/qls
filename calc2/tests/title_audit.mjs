// Заголовки моделей по всем сценам (фаза 6, пункты А3 и А54).
// Проверяет, что название не обрезано многоточием ни в одной сцене, и меряет,
// сколько строк оно занимает. Прогоняется на двух ширинах окна: узкой, где
// панель ужимается до 232px, и широкой.
// Запуск: node calc2/tests/title_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);

const keys = await page.evaluate(() => Object.keys(SCENE_ROUTE));
let bad = 0;
for (const width of [860, 1440]) {
  await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(200);
  const rows = [];
  for (const k of keys) {
    const r = await page.evaluate(async (key) => {
      pickScene(key);
      await new Promise(res => setTimeout(res, 160));
      const el = document.getElementById('scene-name');
      if (!el) return null;
      const cs = getComputedStyle(el);
      const lh = parseFloat(cs.lineHeight) || 20;
      const rect = el.getBoundingClientRect();
      return {
        text: el.textContent.trim(),
        cut: el.scrollWidth > el.clientWidth + 1 || cs.textOverflow === 'ellipsis',
        clipped: el.scrollHeight > el.clientHeight + 1,
        lines: Math.round(rect.height / lh),
        boxW: Math.round(rect.width),
        headH: Math.round(document.querySelector('.side-head').getBoundingClientRect().height),
      };
    }, k);
    rows.push([k, r]);
  }
  const cut = rows.filter(([, r]) => r && (r.cut || r.clipped));
  const byLines = {};
  rows.forEach(([, r]) => { if (r) byLines[r.lines] = (byLines[r.lines] || 0) + 1; });
  const heads = new Set(rows.map(([, r]) => r && r.headH));
  console.log(`ширина окна ${width}: обрезано ${cut.length}, строк ${JSON.stringify(byLines)}, высота шапки ${[...heads].join('/')}`);
  cut.forEach(([k, r]) => console.log(`  ! ${k}: «${r.text}» (место ${r.boxW}px)`));
  rows.filter(([, r]) => r && r.lines >= 3).forEach(([k, r]) =>
    console.log(`  3 строки: ${k} «${r.text}» (место ${r.boxW}px)`));
  bad += cut.length;
  if (heads.size > 1) { console.log('  ! высота шапки скачет между сценами'); bad++; }
}
await browser.close();
console.log(bad ? `\nОбрезанных заголовков: ${bad}` : '\nНи один заголовок не обрезан.');
process.exit(bad ? 1 : 0);
