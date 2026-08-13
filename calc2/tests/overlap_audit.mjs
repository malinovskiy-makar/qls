// Наложения подписей на холсте (фаза 7, пункт А60).
// Собирает прямоугольники всех ВИДИМЫХ подписей и ищет пересечения больше
// двух пикселей по обеим осям.
// Запуск: node calc2/tests/overlap_audit.mjs   (нужен живой сервер на 8099)
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';
const SCENES = (process.env.SCENES || 'tax,sd,mono,ceil,elast,costs,labor,adas,ppf,smallopen').split(',');

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);

let total = 0;
for (const key of SCENES) {
  const bad = await page.evaluate(async (k) => {
    pickScene(k);
    await new Promise(r => setTimeout(r, 420));
    const items = [];
    document.querySelectorAll('#chart text').forEach(t => {
      const r = t.getBoundingClientRect();
      if (r.width < 0.5 || r.height < 0.5) return;
      const own = Array.prototype.filter.call(t.childNodes, n => n.nodeType === 3)
        .map(n => n.nodeValue).join('').trim();
      if (!own) return;
      items.push({ own, x: r.left, y: r.top, w: r.width, h: r.height,
                   axis: t.classList.contains('axis-num') });
    });
    const out = [];
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j];
        const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        if (ox > 2 && oy > 2) out.push({ a: a.own, b: b.own, ox: Math.round(ox), oy: Math.round(oy) });
      }
    }
    return { count: items.length, out };
  }, key);
  total += bad.out.length;
  console.log(`${key.padEnd(11)} подписей ${String(bad.count).padStart(3)}  наложений ${bad.out.length}`);
  bad.out.slice(0, 6).forEach(o => console.log(`   «${o.a}» × «${o.b}»  на ${o.ox}×${o.oy} px`));
}
await browser.close();
console.log(total ? `\nВсего наложений: ${total}` : '\nНаложений подписей нет.');
process.exit(total ? 1 : 0);
