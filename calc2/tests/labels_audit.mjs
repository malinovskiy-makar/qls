// Подписи величин на холсте (фаза 8, пункты А28 и А29).
// «Текстовой формулой» считаем подпись, где латинская буква стоит вплотную к
// цифре или к юникодному индексу, а разметки индекса нет: «Pb=60», «Q₁=40».
// Запуск: node calc2/tests/labels_audit.mjs   (нужен живой сервер на 8099)
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
let total = 0;
const rows = [];
for (const k of keys) {
  const r = await page.evaluate(async (key) => {
    pickScene(key);
    await new Promise(res => setTimeout(res, 340));
    const bad = [];
    let all = 0, typeset = 0;
    document.querySelectorAll('#chart text').forEach(t => {
      const rect = t.getBoundingClientRect();
      if (rect.width < 0.5) return;
      if (t.classList.contains('axis-num')) return;   // деления осей — просто числа
      const own = Array.prototype.filter.call(t.childNodes, n => n.nodeType === 3)
        .map(n => n.nodeValue).join('');
      const subs = t.querySelectorAll('tspan[dy]').length;
      const full = t.textContent || '';
      if (!full.trim()) return;
      all++;
      if (subs) typeset++;
      // Осталась ли в СОБСТВЕННОМ тексте (не в tspan) слипшаяся величина.
      if (/[A-Za-z][0-9₀-₉]|[0-9₀-₉][A-Za-z]/.test(own)) bad.push(full.trim().slice(0, 24));
    });
    return { all, typeset, bad };
  }, k);
  total += r.bad.length;
  rows.push([k, r]);
}
await browser.close();

console.log('сцена          подписей  с индексами  текстовых формул');
rows.forEach(([k, r]) => {
  console.log((r.bad.length ? '! ' : '  ') + k.padEnd(14) +
    String(r.all).padStart(6) + String(r.typeset).padStart(12) + String(r.bad.length).padStart(16) +
    (r.bad.length ? '  ' + r.bad.slice(0, 4).join(', ') : ''));
});
console.log(total ? `\nТекстовых формул: ${total}` : '\nВсе величины на холсте набраны с индексами.');
process.exit(total ? 1 : 0);
