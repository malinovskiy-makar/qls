/**
 * Мера поломок рендера для ПРОИЗВОЛЬНОГО списка текстов (а не пар ДО/ПОСЛЕ,
 * как katex_render_check.js). Ничего не пишет в базу.
 *
 * Вход  — JSON-массив `[{ "key": "…", "text": "…" }, …]`
 * Выход — JSON-массив `[{ "key": "…", "errors": N, "red": N }, …]`
 *
 * `errors` — узлы `.katex-error` (формула не разобралась целиком);
 * `red`    — неизвестные команды внутри разобравшихся формул (`\tesxt`,
 *            `\myarray`): узла `.katex-error` они не создают. Устройство меры
 *            и защита от авторского \color{#cc0000} — в scripts/katex_damage.js.
 *
 *   node scripts/katex_measure_texts.js вход.json выход.json
 *
 * Запускать из корня проекта (иначе require('playwright') не разрешится).
 */
'use strict';

const fs = require('fs');
const { chromium } = require('playwright');
const { buildSandbox } = require('./katex_damage');

const [, , IN, OUT] = process.argv;
if (!IN || !OUT) {
  console.error('Использование: node scripts/katex_measure_texts.js вход.json выход.json');
  process.exit(2);
}

(async () => {
  const items = JSON.parse(fs.readFileSync(IN, 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(buildSandbox(), { waitUntil: 'load' });

  const out = [];
  for (let i = 0; i < items.length; i++) {
    const r = await page.evaluate((t) => window.measure(t), items[i].text || '');
    out.push({ key: items[i].key, errors: r.errors, red: r.red });
    if ((i + 1) % 200 === 0) console.log(`  ${i + 1}/${items.length}…`);
  }

  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1), 'utf8');

  const bad = out.filter(r => r.errors || r.red);
  console.log(`Измерено текстов: ${out.length}`);
  console.log(`С поломкой рендера: ${bad.length}` +
              ` (.katex-error: ${out.filter(r => r.errors).length},` +
              ` краснота: ${out.filter(r => r.red).length})`);
  console.log(`→ ${OUT}`);
})();
