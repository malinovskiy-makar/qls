/* Ночная сессия «левая панель». ФАЗА 13 — контактный лист для утренней приёмки.
   Собирает снимки ВСЕХ 41 сцены (светлая тема, 1440 px) плюс тёмную тему и
   узкий экран 380 px для пяти опорных моделей, и складывает их в
   reports/calc2_panel_night/index.html — страница открывается двойным щелчком,
   сервер для просмотра не нужен.
     node calc2/tests/night_contact_sheet.mjs */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const OUT = 'reports/calc2_panel_night';
const SHOTS = path.join(OUT, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

// Эталон новой панели идёт первым — с него владелец начинает смотреть.
const FIRST = 'sd';
// Пять опорных моделей: рынок, вмешательство, КПВ, фирма, математика.
const EXTRA = ['sd', 'tax', 'ppf', 'costs', 'm-graph'];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', process.env.CALC2_USER || 'admin');
await page.fill('#id_password', process.env.CALC2_PASS || 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const keys = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const names = await page.evaluate(() => {
  const o = {}; Object.keys(SCENE_ROUTE).forEach(k => o[k] = SCENE_NAMES[k] || k); return o;
});
const order = [FIRST].concat(keys.filter(k => k !== FIRST));

const shoot = async (key, file, theme, width) => {
  await page.setViewportSize({ width, height: 900 });
  await page.evaluate(t => { if (typeof setCalcTheme === 'function') setCalcTheme(t); }, theme);
  await page.evaluate(k => { resetSceneMemory(); pickScene(k); }, key);
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(SHOTS, file) });
};

const light = [];
for (const k of order) {
  const f = k + '.png';
  await shoot(k, f, 'light', 1440);
  light.push({ key: k, name: names[k], file: f });
  console.log('снят  ' + k.padEnd(14) + names[k]);
}
const dark = [], narrow = [];
for (const k of EXTRA) {
  await shoot(k, k + '__dark.png', 'dark', 1440);
  dark.push({ key: k, name: names[k], file: k + '__dark.png' });
  await shoot(k, k + '__380.png', 'light', 380);
  narrow.push({ key: k, name: names[k], file: k + '__380.png' });
  console.log('снят  ' + k.padEnd(14) + '(тёмная тема и 380 px)');
}
await browser.close();

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const cards = list => list.map((s, i) => `
      <figure class="shot">
        <a href="shots/${s.file}" target="_blank"><img src="shots/${s.file}" alt="${esc(s.name)}" loading="lazy"></a>
        <figcaption><b>${i + 1}. ${esc(s.name)}</b><span>${esc(s.key)}</span></figcaption>
      </figure>`).join('');

const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>calc2 · левая панель — контактный лист ночной сессии</title>
<style>
  :root { color-scheme: light; }
  body { margin: 0; padding: 28px 32px 60px; background: #f6f7f9; color: #10141c;
         font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  h2 { font-size: 17px; margin: 34px 0 12px; padding-top: 18px; border-top: 1px solid #dfe3e8; }
  p.lead { margin: 0 0 4px; color: #4a5361; max-width: 70ch; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 18px; }
  .shot { margin: 0; background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; overflow: hidden; }
  .shot img { display: block; width: 100%; height: auto; }
  .shot figcaption { display: flex; justify-content: space-between; align-items: baseline;
                     gap: 10px; padding: 8px 11px; font-size: 13px; border-top: 1px solid #eceff3; }
  .shot figcaption span { color: #8a93a0; font-size: 11px; font-family: ui-monospace, monospace; }
  .first { border-color: #b23a67; box-shadow: 0 0 0 2px rgba(178,58,103,.18); }
  .note { background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 14px 16px;
          margin: 14px 0 0; max-width: 90ch; }
  .note ul { margin: 8px 0 0; padding-left: 20px; }
</style></head><body>
<h1>calc2 · левая панель — контактный лист</h1>
<p class="lead">Ночная сессия 22.08. Светлая тема, ширина окна 1440&nbsp;px, все 41 сцена.
Первым идёт «Спрос и предложение» — эталон новой панели.</p>
<div class="note">
  <b>Что смотреть.</b>
  <ul>
    <li>В каждой модели ровно три карточки: «Ввод функций» (раскрыта), «Точки на графике», «Площади».</li>
    <li>Над ними — имя модели и кнопка «Вернуть исходный вид».</li>
    <li>«Что изучаем», «Структура рынка» и «Излишки» из панели ушли; вмешательство государства — справа.</li>
    <li>В «Вводе функций» — готовые поля модели и кнопка «Добавить кривую» под ними.</li>
    <li>Справа ползунки называются «Сдвиг D», стоят по центру и выровнены по левому краю дорожки.</li>
    <li>У точки равновесия одна буква «E» без звёздочки, кривые сквозь неё не проходят.</li>
  </ul>
</div>
<h2>Все модели · светлая тема · 1440&nbsp;px</h2>
<div class="grid">${cards(light)}</div>
<h2>Тёмная тема · 1440&nbsp;px · пять опорных моделей</h2>
<div class="grid">${cards(dark)}</div>
<h2>Узкий экран · 380&nbsp;px · пять опорных моделей</h2>
<div class="grid">${cards(narrow)}</div>
${errs.length ? '<h2>Ошибки страницы при съёмке</h2><pre>' + esc(errs.join('\n')) + '</pre>' : ''}
</body></html>`;

fs.writeFileSync(path.join(OUT, 'index.html'), html.replace('class="shot">\n        <a href="shots/' + light[0].file,
  'class="shot first">\n        <a href="shots/' + light[0].file));
console.log('\nконтактный лист: ' + path.join(OUT, 'index.html'));
console.log('снимков: ' + (light.length + dark.length + narrow.length)
  + ' (светлая ' + light.length + ', тёмная ' + dark.length + ', узкий экран ' + narrow.length + ')');
if (errs.length) console.log('ошибки страницы: ' + errs.length + '\n' + errs.slice(0, 5).join('\n'));
