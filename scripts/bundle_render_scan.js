/**
 * Прогон меры «сломанного рендера» по ВСЕМУ офлайн-пакету ревью.
 * Только читает: открывает каждый снимок в chromium и считает поломки.
 *
 * Заодно проверяет, что пакет действительно офлайновый: любой запрос не по
 * file:// — это внешняя зависимость, и у ревьюера без интернета страница
 * поедет.
 *
 * ⚠️ На снимках цвет ошибки боевой (#cc0000), а его может написать и автор
 * задачи (`\color{#cc0000}`). Поэтому найденное здесь — КАНДИДАТЫ; их список
 * надо подтвердить прогоном текстов через песочницу katex_damage, где
 * errorColor подменён служебным оттенком. Кандидатов обычно единицы, так что
 * подтверждение дешёвое.
 *
 *   node scripts/bundle_render_scan.js reports/review_bundles/<пакет> [выход.json]
 *
 * Запускать из корня проекта (иначе require('playwright') не разрешится).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { livePageCounterSource } = require('./katex_damage');

const BUNDLE = process.argv[2];
const OUT = process.argv[3] || null;
if (!BUNDLE) {
  console.error('Использование: node scripts/bundle_render_scan.js <каталог пакета> [выход.json]');
  process.exit(2);
}

const manifest = JSON.parse(
  fs.readFileSync(path.join(BUNDLE, 'manifest.json'), 'utf8'));
const problems = manifest.problems || manifest;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const external = new Set();
  page.on('request', (r) => {
    const u = r.url();
    if (!u.startsWith('file://') && !u.startsWith('data:')) external.add(u);
  });

  const hits = [];
  let katexTotal = 0;
  for (let i = 0; i < problems.length; i++) {
    const file = path.resolve(BUNDLE, problems[i].file);
    await page.goto('file://' + file, { waitUntil: 'load' });
    const r = await page.evaluate(livePageCounterSource());
    const n = await page.evaluate(() => document.querySelectorAll('.katex').length);
    katexTotal += n;
    if (r.errors || r.redCandidates) {
      hits.push({ id: problems[i].id, errors: r.errors, red: r.redCandidates });
    }
    if ((i + 1) % 250 === 0) console.log(`  ${i + 1}/${problems.length}…`);
  }
  await browser.close();

  console.log(`Снимков просмотрено: ${problems.length}`);
  console.log(`Формул отрисовано:   ${katexTotal}`);
  console.log(`Задач с поломкой рендера: ${hits.length}`);
  console.log(`  с .katex-error: ${hits.filter(h => h.errors).length}`);
  console.log(`  с красными командами (кандидаты): ${hits.filter(h => h.red).length}`);
  if (hits.length) {
    console.log('  ' + hits.map(h => `#${h.id}(${h.errors}/${h.red})`).join(', '));
  }
  console.log(`Внешних запросов: ${external.size}` +
              (external.size ? ' — ' + [...external].slice(0, 5).join(', ') : ' (пакет офлайновый)'));

  if (OUT) {
    fs.writeFileSync(OUT, JSON.stringify(
      { scanned: problems.length, katex: katexTotal, hits,
        external: [...external] }, null, 1), 'utf8');
    console.log(`→ ${OUT}`);
  }
})();
