/**
 * Рендер полей одобренных задач настоящим KaTeX — признаки «в» и «г»
 * проверки перед выкладкой (publication_holes_check). Ничего не меняет.
 *
 * Песочница и мера поломки — общие со шлюзом «не навреди»
 * (scripts/katex_damage.js). Второй меры не заводим: разошлась бы с той,
 * которой мерили все прежние правки.
 *
 * Два режима поломки различаются намеренно:
 *   errors > 0  — формула не разобралась целиком, на экране видна ошибка;
 *   red    > 0  — формула разобралась, но внутри НЕИЗВЕСТНАЯ команда
 *                 (\myarray, \tesxt). Узла ошибки нет, команда молча
 *                 выброшена, соседние куски слипаются. Это и есть признак «г».
 *
 * ⚠️ Слипшиеся числа ищем ТОЛЬКО там, где red > 0. Иначе ловушка: KaTeX
 * законно ставит числитель вплотную к знаменателю, и \frac{1}{2} в
 * textContent выглядит как «12» — на здоровой формуле это не поломка.
 *
 *   node scripts/holes_render_check.js --queue <вход.json> --out <выход.json>
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

const QUEUE = path.resolve(ROOT, arg('--queue', 'reports/publication_check/render_queue.json'));
const OUT = path.resolve(ROOT, arg('--out', 'reports/publication_check/render_result.json'));

/** Числовые токены строки. Служит для сверки «до рендера» и «после». */
function numbers(text) {
  return (String(text).match(/\d+/g) || []);
}

/**
 * Числа, появившиеся ТОЛЬКО после рендера. Если команда выброшена и «31»
 * склеилось с «8», в отрендеренном тексте возникнет «318», которого в
 * исходнике не было ни одним токеном.
 */
function gluedNumbers(source, rendered) {
  const was = new Set(numbers(source));
  const out = [];
  for (const n of numbers(rendered)) {
    if (!was.has(n) && n.length >= 3 && !out.includes(n)) out.push(n);
  }
  return out;
}

(async () => {
  const queue = JSON.parse(fs.readFileSync(QUEUE, 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(buildSandbox(), { waitUntil: 'load' });

  // Видимый текст поверх меры: скрытую копию MathML выбрасываем, иначе в
  // текст попадёт ИСХОДНИК формулы из <annotation> и сверка чисел ослепнет.
  await page.evaluate(() => {
    window.visibleText = function () {
      const box = document.getElementById('box').cloneNode(true);
      box.querySelectorAll('.katex-mathml').forEach((n) => n.remove());
      return box.textContent || '';
    };
  });

  const results = [];
  let errFields = 0;
  let redFields = 0;

  for (let i = 0; i < queue.length; i++) {
    const item = queue[i];
    const res = await page.evaluate((text) => {
      const m = window.measure(text);
      return { m: m, text: window.visibleText() };
    }, item.text || '');

    const row = {
      pid: item.pid,
      field: item.field,
      errors: res.m.errors,
      red: res.m.red,
    };
    if (res.m.errors) errFields++;
    if (!res.m.errors && res.m.red) {
      redFields++;
      row.glued = gluedNumbers(item.text || '', res.text);
    }
    if (row.errors || row.red) results.push(row);

    if ((i + 1) % 1000 === 0) {
      process.stdout.write('  ...' + (i + 1) + ' / ' + queue.length + '\n');
    }
  }

  await browser.close();
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(results, null, 1), 'utf8');

  const glued = results.filter((r) => r.glued && r.glued.length).length;
  process.stdout.write(
    'Полей прогнано: ' + queue.length +
    '; с ошибкой рендера: ' + errFields +
    '; с выброшенной командой: ' + redFields +
    ' (из них со слипшимися числами: ' + glued + ')\n');
  process.stdout.write('Результат: ' + OUT + '\n');
})();
