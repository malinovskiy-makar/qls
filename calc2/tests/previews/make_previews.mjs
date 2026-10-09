/* Генератор превью моделей экрана выбора (ADR 0141).

   Открывает каждую рабочую модель экрана выбора с канонического старта (как
   tex/ci_quick.mjs), делает тот же бумажный прогон и опись, что выгрузка .tex,
   и собирает из описи маленькую векторную картинку: кривые, закраски,
   сплошные отрезки и оси, без чисел, подписей и точек (previews/inpage.js).
   Цвета — именами токенов темы, поэтому превью само перекрашивается при
   смене темы. Итог — calc2/static/calc2/previews.json.

   ./venv313/bin/python manage.py runserver 8099 --settings=config.settings_check --noreload
   node calc2/tests/previews/make_previews.mjs          (CALC2_BASE_URL — сервер)
   CHECK=1 — ничего не писать, только сверить с лежащим файлом (код 1 при расхождении).

   Коды: 0 — файл собран; 1 — дефект (несопоставленный цвет, превью без путей,
   текстовый узел, отпечаток зависит от окна, файл больше 150 КБ);
   3 — calc2 не загрузился; 4 — нет Playwright. */
import fs from 'node:fs';
import path from 'node:path';
import { openPage, openScene, ROOT } from '../tex/lib.mjs';
import { tokenTable, addPreviewScript, PREVIEWS_JSON } from './lib.mjs';

let chromium;
try { ({ chromium } = await import('playwright')); } catch (e) { console.log('Playwright недоступен: ' + e.message); process.exit(4); }

const OUT = PREVIEWS_JSON;
const LIMIT = 150 * 1024;

const tokens = tokenTable();
const t0 = Date.now();
const browser = await chromium.launch();
let f;
try { f = await openPage(browser, {}); } catch (e) { console.log('calc2 не загрузился: ' + e.message.split('\n')[0]); await browser.close(); process.exit(3); }
await addPreviewScript(f.page);
const models = await f.page.evaluate(() => [...document.querySelectorAll('#scene-picker .scard')]
  .map(c => ({ key: c.dataset.scene, soon: c.classList.contains('soon') || c.disabled })));
const keys = models.filter(m => !m.soon).map(m => m.key);

const fails = [];
const out = {};
for (const k of keys) {
  await openScene(f.page, k);
  const r = await f.page.evaluate((t) => window.__PV.build(t), tokens);
  if (r.stats.unknown.length) fails.push(k + ': несопоставленный цвет ' + [...new Set(r.stats.unknown)].join(', '));
  if (!r.p.length) fails.push(k + ': в превью нет ни одного пути');
  out[k] = { vb: r.vb, fp: r.fp, p: r.p };
}
// отпечаток не зависит от окна и темы: тот же обход при 390×844 в тёмной
const narrow = await openPage(browser, { w: 390, h: 844, theme: 'dark' });
await addPreviewScript(narrow.page);
for (const k of keys) {
  await openScene(narrow.page, k);
  const fp = await narrow.page.evaluate((t) => window.__PV.fp(t), tokens);
  if (fp !== out[k].fp) fails.push(k + ': отпечаток при 390×844 (тёмная) ' + fp + ' не тот же, что при 1440×760 (светлая) ' + out[k].fp);
}
const errs = f.errors.concat(narrow.errors);
await browser.close();

const text = '{\n' + keys.map(k => JSON.stringify(k) + ': ' + JSON.stringify(out[k])).join(',\n') + '\n}\n';
if (/"(text|tspan)"|<text/.test(text)) fails.push('в файле текстовый узел');
if (Buffer.byteLength(text) > LIMIT) fails.push('previews.json ' + Buffer.byteLength(text) + ' байт, предел ' + LIMIT);
errs.forEach(e => fails.push('страница: ' + e));
const paths = keys.reduce((s, k) => s + out[k].p.length, 0);
fails.forEach(x => console.log('ПРОВАЛ ' + x));
if (process.env.CHECK) {
  const old = fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8') : '';
  const same = old === text;
  console.log(same ? 'previews.json совпадает с пересборкой побайтно' : 'previews.json РАСХОДИТСЯ с пересборкой');
  process.exit(fails.length || !same ? 1 : 0);
}
if (!fails.length) fs.writeFileSync(OUT, text);
console.log((fails.length ? 'ПРЕВЬЮ НЕ ЗАПИСАНЫ: провалов ' + fails.length : 'ПРЕВЬЮ ЗАПИСАНЫ: ' + path.relative(ROOT, OUT)) +
  ' | моделей ' + keys.length + ', путей ' + paths + ', ' + Buffer.byteLength(text) + ' байт, ' + ((Date.now() - t0) / 1000).toFixed(1) + ' с');
process.exit(fails.length ? 1 : 0);
