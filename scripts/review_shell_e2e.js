/**
 * Сквозной прогон оболочки ревью v2 настоящим браузером (Playwright).
 *
 * Проверяет ровно то, что делает руками ревьюер, и чего не видят питон-тесты:
 * одиночный вердикт, набор нескольких дефектов с подтверждением по Enter,
 * «Гагно», сброс дефектов нажатием «Идеально», пустой Enter, возобновление
 * после перезагрузки страницы и скачивание файла вердиктов.
 *
 *   node scripts/review_shell_e2e.js reports/review_bundles/aa_20260728
 *
 * Скачанный файл кладётся рядом с пакетом под именем e2e_verdicts.json —
 * его дальше проверяет import_review_verdicts. Запускать из корня проекта.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const bundleDir = path.resolve(process.cwd(), process.argv[2] ||
                               'reports/review_bundles/aa_20260728');
const OUT = path.join(bundleDir, 'e2e_verdicts.json');

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log(`${ok ? '  OK  ' : '  FAIL'} ${name}` +
              (ok ? '' : `\n        ждал ${JSON.stringify(want)}, получил ${JSON.stringify(got)}`));
}

// Состояние оболочки глазами теста: что лежит в localStorage.
const readState = (page) => page.evaluate(() => {
  const key = 'qls_review::' + window.REVIEW_MANIFEST.bundle_id;
  return JSON.parse(localStorage.getItem(key) || '{}');
});
const catsFor = (st, pid) => (st.verdicts[pid] || {}).categories || [];

(async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(bundleDir, 'manifest.json'), 'utf8'));
  const ids = manifest.problems.slice(0, 5).map(p => p.id);
  const url = 'file://' + path.join(bundleDir, 'reviewer.html');

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  const external = [];
  page.on('request', r => { if (!r.url().startsWith('file://')) external.push(r.url()); });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(url);
  await page.waitForFunction(() => !document.getElementById('panel').hidden);

  console.log('1. Одиночный выбор «Идеально» (клавиша 1)');
  await page.keyboard.press('1');
  let st = await readState(page);
  check('вердикт задачи 1 = perfect', catsFor(st, ids[0]), ['perfect']);
  check('перешли к задаче 2', st.idx, 1);

  console.log('2. Множественный выбор дефектов + Enter');
  await page.keyboard.press('2');            // Сломанная формула
  await page.keyboard.press('4');            // Слипшаяся структура
  st = await readState(page);
  check('отмечены два дефекта', catsFor(st, ids[1]), ['broken_formula', 'merged_structure']);
  check('без Enter остаёмся на месте', st.idx, 1);
  await page.keyboard.press('Enter');
  st = await readState(page);
  check('после Enter ушли дальше', st.idx, 2);
  check('дефекты сохранились', catsFor(st, ids[1]), ['broken_formula', 'merged_structure']);

  console.log('3. Повторное нажатие снимает дефект');
  await page.keyboard.press('2');
  await page.keyboard.press('4');
  await page.keyboard.press('4');            // снять
  st = await readState(page);
  check('остался один дефект', catsFor(st, ids[2]), ['broken_formula']);

  console.log('4. «Идеально» поверх отмеченных дефектов их сбрасывает');
  await page.keyboard.press('1');
  st = await readState(page);
  check('дефекты сброшены, остался perfect', catsFor(st, ids[2]), ['perfect']);
  check('и ушли дальше', st.idx, 3);

  console.log('5. «Гагно» (клавиша 0)');
  await page.keyboard.press('3');            // сначала отметим дефект
  await page.keyboard.press('0');
  st = await readState(page);
  check('вердикт = trash, дефект сброшен', catsFor(st, ids[3]), ['trash']);
  check('ушли дальше', st.idx, 4);

  console.log('6. Enter без выбранных категорий ничего не делает');
  const before = (await readState(page)).idx;
  await page.keyboard.press('Enter');
  st = await readState(page);
  check('позиция не изменилась', st.idx, before);
  check('вердикт не появился', catsFor(st, ids[4]), []);
  check('подсказка про пустой Enter показана',
        await page.textContent('#flash'), 'Сначала отметьте категорию — клавиши 1–9 или 0');

  console.log('7. Возобновление после перезагрузки');
  await page.evaluate(() => { document.getElementById('reviewer').value = 'E2E';
                              document.getElementById('reviewer')
                                .dispatchEvent(new Event('change')); });
  await page.reload();
  await page.waitForFunction(() => !document.getElementById('panel').hidden);
  st = await readState(page);
  check('вердикты пережили перезагрузку', catsFor(st, ids[1]),
        ['broken_formula', 'merged_structure']);
  check('позиция пережила перезагрузку', st.idx, before);
  check('имя ревьюера пережило перезагрузку', st.reviewer, 'E2E');
  check('«Гагно» пережило перезагрузку', catsFor(st, ids[3]), ['trash']);

  console.log('8. Скачивание JSON');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.click('#btn-download'),
  ]);
  await download.saveAs(OUT);
  const payload = JSON.parse(fs.readFileSync(OUT, 'utf8'));
  check('формат файла', payload.format, 'qls-review-verdicts-v2');
  check('пакет в файле', payload.bundle_id, manifest.bundle_id);
  check('ревьюер в файле', payload.reviewer, 'E2E');
  check('вердиктов в файле', payload.count, 4);
  check('у вердиктов список categories',
        payload.verdicts.every(v => Array.isArray(v.categories)), true);

  check('внешних запросов нет', external, []);
  check('ошибок JS нет', errors, []);

  await browser.close();
  console.log(`\nСкачанный файл → ${OUT}`);
  console.log(failures ? `ПРОВАЛОВ: ${failures}` : 'Все проверки пройдены.');
  process.exit(failures ? 1 : 0);
})();
