/**
 * Считает ошибки KaTeX в парах текстов ДО/ПОСЛЕ (седьмой признак шлюза
 * «не навреди», задача 1 сессии 2026-07-28). Ничего в базе не трогает.
 *
 * Вход:  reports/batch2_sweep/render_queue.json  (пишет batch2_revert_damage_audit)
 * Выход: reports/batch2_sweep/render_result.json
 *
 * Почему браузером, а не эвристикой: «сломанная формула» — это то, что решил
 * KaTeX, а не то, что мы про него думаем. Конвейер повторяет боевой из
 * catalog/base.html дословно: маскировка \$ приватным символом, те же
 * разделители в том же порядке ($$ раньше $), throwOnError: false. Считаем
 * узлы .katex-error.
 *
 *   node scripts/katex_render_check.js
 *
 * Запускать из корня проекта (иначе require('playwright') не разрешится).
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = process.cwd();
const KATEX_DIR = path.join(ROOT, 'problems/review_bundle_assets/vendor/katex');
const QUEUE = path.join(ROOT, 'reports/batch2_sweep/render_queue.json');
const OUT = path.join(ROOT, 'reports/batch2_sweep/render_result.json');

// Тот же порядок разделителей, что в catalog/templates/catalog/base.html:
// $$ обязан идти раньше $, иначе auto-render режет $$…$$ как два пустых $…$.
const PAGE = `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>${fs.readFileSync(path.join(KATEX_DIR, 'katex.min.css'), 'utf8')}</style>
<script>${fs.readFileSync(path.join(KATEX_DIR, 'katex.min.js'), 'utf8')}</script>
<script>${fs.readFileSync(path.join(KATEX_DIR, 'contrib/auto-render.min.js'), 'utf8')}</script>
</head><body><div id="box"></div>
<script>
var DOLLAR_SENTINEL = '\\uE000';
function maskEscapedDollars(root) {
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null), node;
  while ((node = walker.nextNode())) {
    if (node.nodeValue.indexOf('\\\\$') !== -1) {
      node.nodeValue = node.nodeValue.split('\\\\$').join(DOLLAR_SENTINEL);
    }
  }
}
window.countErrors = function (text) {
  var box = document.getElementById('box');
  box.textContent = text;
  maskEscapedDollars(box);
  renderMathInElement(box, {
    delimiters: [
      { left: '$$',  right: '$$',  display: true  },
      { left: '$',   right: '$',   display: false },
      { left: '\\\\[', right: '\\\\]', display: true  },
      { left: '\\\\(', right: '\\\\)', display: false }
    ],
    throwOnError: false
  });
  return box.querySelectorAll('.katex-error').length;
};
</script></body></html>`;

(async () => {
  const queue = JSON.parse(fs.readFileSync(QUEUE, 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(PAGE, { waitUntil: 'load' });

  const results = [];
  for (let i = 0; i < queue.length; i++) {
    const item = queue[i];
    const [errOld, errNew] = await page.evaluate(
      ([a, b]) => [window.countErrors(a), window.countErrors(b)],
      [item.old || '', item.new || '']
    );
    results.push({
      kind: item.kind, pid: item.pid, pk: item.pk,
      control: !!item.control, errors_old: errOld, errors_new: errNew
    });
    if ((i + 1) % 50 === 0) console.log(`  ${i + 1}/${queue.length}…`);
  }

  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(results, null, 1), 'utf8');

  const worse = results.filter(r => r.errors_new > r.errors_old);
  const blind = worse.filter(r => r.control);
  console.log(`Проверено полей: ${results.length}`);
  console.log(`Рендер стал хуже: ${worse.length} (из них в контрольной выборке: ${blind.length})`);
  if (blind.length) {
    console.log('Слепые пятна предфильтра:', blind.map(r => '#' + r.pid).join(', '));
  }
  console.log(`→ ${OUT}`);
})();
