/**
 * Считает поломки рендера KaTeX в парах текстов ДО/ПОСЛЕ (седьмой признак
 * шлюза «не навреди»). Ничего в базе не трогает.
 *
 * Вход:  reports/batch2_sweep/render_queue.json  (пишет batch2_revert_damage_audit)
 * Выход: reports/batch2_sweep/render_result.json
 *
 * Почему браузером, а не эвристикой: «сломанная формула» — это то, что решил
 * KaTeX, а не то, что мы про него думаем.
 *
 * ⚠️ С 2026-08-08 считаются ДВА режима поломки, а не один (решение Notion
 * 3b6b11c92bc181839c18ddaceb1e19f3):
 *   errors_* — узлы `.katex-error`: формула не разобралась целиком;
 *   red_*    — неизвестная команда внутри разобравшейся формулы (`\tesxt`,
 *              `\myarray`): `.katex-error` НЕ создаётся, команда печатается
 *              служебным цветом, соседние куски молча слипаются.
 * Прежняя версия считала только первое и была слепа ко второму, поэтому все
 * замеры ухудшения рендера до этой даты — нижние оценки.
 *
 * Устройство меры и способ отличить ошибку от авторского \color{#cc0000} —
 * в scripts/katex_damage.js.
 *
 *   node scripts/katex_render_check.js
 *   node scripts/katex_render_check.js --queue <вход.json> --out <выход.json>
 *
 * Запускать из корня проекта (иначе require('playwright') не разрешится).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { buildSandbox } = require('./katex_damage');

const ROOT = process.cwd();

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const QUEUE = path.resolve(ROOT, arg('--queue', 'reports/batch2_sweep/render_queue.json'));
const OUT = path.resolve(ROOT, arg('--out', 'reports/batch2_sweep/render_result.json'));

(async () => {
  const queue = JSON.parse(fs.readFileSync(QUEUE, 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(buildSandbox(), { waitUntil: 'load' });

  const results = [];
  for (let i = 0; i < queue.length; i++) {
    const item = queue[i];
    const [before, after] = await page.evaluate(
      ([a, b]) => [window.measure(a), window.measure(b)],
      [item.old || '', item.new || '']
    );
    results.push({
      kind: item.kind, pid: item.pid, pk: item.pk,
      control: !!item.control,
      errors_old: before.errors, errors_new: after.errors,
      red_old: before.red, red_new: after.red
    });
    if ((i + 1) % 50 === 0) console.log(`  ${i + 1}/${queue.length}…`);
  }

  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(results, null, 1), 'utf8');

  const worseErr = results.filter(r => r.errors_new > r.errors_old);
  const worseRed = results.filter(r => r.red_new > r.red_old);
  const worse = results.filter(r => r.errors_new > r.errors_old || r.red_new > r.red_old);
  const onlyRed = worseRed.filter(r => r.errors_new <= r.errors_old);
  const blind = worse.filter(r => r.control);
  console.log(`Проверено полей: ${results.length}`);
  console.log(`Рендер стал хуже: ${worse.length}`);
  console.log(`  из них по .katex-error: ${worseErr.length}`);
  console.log(`  из них по красноте:     ${worseRed.length} (видны ТОЛЬКО ей: ${onlyRed.length})`);
  console.log(`  из них в контрольной выборке: ${blind.length}`);
  if (blind.length) {
    console.log('Слепые пятна предфильтра:', blind.map(r => '#' + r.pid).join(', '));
  }
  console.log(`→ ${OUT}`);
})();
