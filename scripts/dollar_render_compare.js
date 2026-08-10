/**
 * Замер «правка не смеет ухудшить рендер» для маскировки литеральных долларов.
 *
 * Берёт условия задач с «\$», прогоняет их через ДВА маскировщика — старый
 * (маскирует все доллары подряд) и новый (только вне формул) — и считает
 * блоки .katex-error в обоих случаях. Конвейер дословно повторяет боевой:
 * те же разделители, «$$» раньше «$», throwOnError: false.
 *
 * Запускать ИЗ КОРНЯ проекта:
 *   node scripts/dollar_render_compare.js <файл.json> [выходной .md]
 * где файл.json — список пар [id, текст].
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SRC = process.argv[2];
const OUT = process.argv[3] || path.join('reports', 'review', 'ф01-замер-рендера.md');

// Новый маскировщик читаем ИЗ ПАРТИАЛА — чтобы мерить то, что стоит в бою.
function partialScript() {
  const text = fs.readFileSync(path.join('templates', '_katex_dollars.html'), 'utf8');
  const m = text.match(/<script>([\s\S]*)<\/script>/);
  if (!m) throw new Error('в партиале нет <script>');
  return m[1];
}

(async () => {
  const rows = JSON.parse(fs.readFileSync(SRC, 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  // ⚠️ `<!doctype html>` ОБЯЗАТЕЛЕН: без него страница уходит в quirks mode,
  // и KaTeX отказывается рисовать вообще — замер показал бы «ноль ошибок»
  // просто потому, что не рисовалось ничего. Та же ловушка, что на печатном
  // листке.
  await page.setContent('<!doctype html><html><body><div id="host"></div></body></html>');
  await page.addScriptTag({ url: 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js' });
  await page.addScriptTag({ url: 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js' });
  await page.addScriptTag({ content: partialScript() });

  const res = await page.evaluate((rows) => {
    const DELIMS = [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false },
    ];
    // Старый маскировщик — как было до правки: все «\$» подряд.
    function maskAll(s) { return s.split('\\$').join(DOLLAR_SENTINEL); }

    function errorsFor(text, masker) {
      const host = document.getElementById('host');
      host.textContent = masker(text);
      renderMathInElement(host, { delimiters: DELIMS, throwOnError: false });
      return host.querySelectorAll('.katex-error').length;
    }

    const out = { total: rows.length, worse: [], better: [], sameBad: 0,
                  oldErrors: 0, newErrors: 0 };
    for (const [id, text] of rows) {
      const before = errorsFor(text, maskAll);
      const after = errorsFor(text, maskOutsideMath);
      out.oldErrors += before;
      out.newErrors += after;
      if (after > before) out.worse.push([id, before, after]);
      else if (after < before) out.better.push([id, before, after]);
      else if (before > 0) out.sameBad += 1;
    }
    return out;
  }, rows);

  const lines = [
    '# Замер рендера: маскировка литеральных долларов',
    '',
    `Условий в выборке: **${res.total}** (видимые задачи каталога с «\\$»).`,
    '',
    `| | ошибок KaTeX |`,
    `|---|---|`,
    `| было (маскировали всё подряд) | **${res.oldErrors}** |`,
    `| стало (маскируем только вне формул) | **${res.newErrors}** |`,
    '',
    `Стало хуже: **${res.worse.length}**. Стало лучше: **${res.better.length}**.`,
    `Осталось сломанным (дефект самого текста): ${res.sameBad}.`,
    '',
  ];
  if (res.worse.length) {
    lines.push('## Стало хуже (это стоп-сигнал)', '');
    res.worse.slice(0, 40).forEach(([id, b, a]) =>
      lines.push(`- задача #${id}: было ${b}, стало ${a}`));
    lines.push('');
  }
  if (res.better.length) {
    lines.push('## Починилось', '');
    res.better.slice(0, 40).forEach(([id, b, a]) =>
      lines.push(`- задача #${id}: было ${b}, стало ${a}`));
    if (res.better.length > 40) lines.push(`- …и ещё ${res.better.length - 40}`);
  }
  fs.writeFileSync(OUT, lines.join('\n') + '\n');
  console.log(`было ошибок: ${res.oldErrors}, стало: ${res.newErrors}`);
  console.log(`хуже: ${res.worse.length}, лучше: ${res.better.length}`);
  console.log('отчёт:', OUT);
  await browser.close();
  process.exit(res.worse.length ? 2 : 0);
})();
