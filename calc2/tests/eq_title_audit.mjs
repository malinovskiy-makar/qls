// Заголовок раздела равновесия по всем сценам (фаза 3, пункты А51/А52).
// Печатает для каждой карточки: показан ли раздел, какой у него заголовок и
// что внутри. Ни в одной монопольной сцене не должно стоять «D = S».
// Запуск: node calc2/tests/eq_title_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);

const keys = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const rows = [];
for (const k of keys) {
  const r = await page.evaluate(async (key) => {
    pickScene(key);
    await new Promise(res => setTimeout(res, 380));
    const sec = document.getElementById('sec-eq');
    // Раздел живёт в свёрнутом блоке «Ключевые значения», поэтому смотрим на
    // собственное display, а не на размеры: свёрнутый блок даёт нули у всего.
    const vis = sec ? getComputedStyle(sec).display !== 'none' : false;
    const t = sec && sec.querySelector('.section-title');
    const body = document.getElementById('info-eq');
    return {
      shown: vis,
      title: t ? t.textContent.trim() : '',
      body: body ? body.textContent.trim().slice(0, 46) : '',
      mono: typeof isMonopolyScene === 'function' ? isMonopolyScene() : false,
    };
  }, k);
  rows.push([k, r]);
}
await browser.close();

let bad = 0;
console.log('сцена         моноп  показан  заголовок                        внутри');
rows.forEach(([k, r]) => {
  const wrong = r.shown && r.mono && /D\s*=\s*S/.test(r.title);
  const stuck = r.shown && r.mono && /Отметьте|Появятся/.test(r.body);
  if (wrong || stuck) bad++;
  console.log(
    (wrong || stuck ? '! ' : '  ') + k.padEnd(13) +
    (r.mono ? 'да ' : '   ').padEnd(7) +
    (r.shown ? 'да ' : 'нет').padEnd(9) +
    r.title.padEnd(33) + r.body
  );
});
console.log(bad ? `\nОшибок: ${bad}` : '\nНи в одной монопольной сцене «D = S» не показывается.');
process.exit(bad ? 1 : 0);
