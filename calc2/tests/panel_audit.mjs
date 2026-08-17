// Наполнение правой панели по всем сценам (фаза 4, пункты А53 и А5).
// Меряет ВИДИМЫЙ текст в блоках «Ключевые значения» и «Объяснение модели».
// Запуск: node calc2/tests/panel_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const MIN_EXPLAIN = +(process.env.MIN_EXPLAIN || 800);

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1440, height: 950 });
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
    await new Promise(res => setTimeout(res, 420));
    // Раскрываем оба складных блока, иначе внутри ничего не измерить.
    ['sb-btn', 'ex-btn'].forEach(id => {
      const b = document.getElementById(id);
      if (b && b.getAttribute('aria-expanded') !== 'true') b.click();
    });
    await new Promise(res => setTimeout(res, 260));
    const visText = (root) => {
      if (!root) return '';
      let out = '';
      root.querySelectorAll('*').forEach(() => {});
      const walk = (n) => {
        if (n.nodeType === 3) { out += n.nodeValue; return; }
        if (n.nodeType !== 1) return;
        const cs = getComputedStyle(n);
        if (cs.display === 'none' || cs.visibility === 'hidden') return;
        // KaTeX кладёт рядом с формулой её исходную запись — считать дважды нельзя.
        if (n.classList && (n.classList.contains('katex-mathml') || n.tagName === 'ANNOTATION')) return;
        n.childNodes.forEach(walk);
      };
      walk(root);
      return out.replace(/\s+/g, ' ').trim();
    };
    return {
      stats: visText(document.getElementById('sb-body')).length,
      explain: visText(document.getElementById('ex-body')).length,
    };
  }, k);
  rows.push([k, r]);
}
await browser.close();

let empty = 0, thin = 0;
console.log('сцена          Ключевые   Объяснение');
rows.forEach(([k, r]) => {
  const flagS = r.stats === 0;
  const flagE = r.explain === 0 ? 'ПУСТО' : (r.explain < MIN_EXPLAIN ? 'мало' : '');
  if (r.explain === 0 || r.stats === 0) empty++;
  else if (r.explain < MIN_EXPLAIN) thin++;
  console.log(
    ((flagS || flagE) ? '! ' : '  ') + k.padEnd(14) +
    String(r.stats).padStart(6) + '   ' + String(r.explain).padStart(6) + '  ' + flagE
  );
});
console.log(`\nПустых блоков: ${empty}; короче ${MIN_EXPLAIN} знаков: ${thin}`);
process.exit(empty || thin ? 1 : 0);
