/**
 * Разведка «сырой LaTeX на экране проверки».
 *
 * Открывает экран проверки под репетитором и ищет ДВА признака:
 *  • блоки .katex-error (KaTeX сдался и напечатал исходник красным);
 *  • конечные элементы внутри .katex с цветом rgb(204,0,0) — то же самое,
 *    но когда класс ошибки не проставлен.
 * Плюс снимает страницу.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/latex_probe.js [порт] [подпись]
 */
const { chromium } = require('playwright');
const path = require('path');

const PORT = process.argv[2] || '8199';
const TAG = process.argv[3] || 'до';
const BASE = `http://127.0.0.1:${PORT}`;
const URL_REVIEW = `${BASE}/teacher/groups/2/submissions/112/`;
const OUT = path.join('reports', 'review', `ф01-экран-проверки-latex-${TAG}.png`);

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1200 } });
  const page = await ctx.newPage();

  // вход
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  const resp = await page.goto(URL_REVIEW);
  console.log('код ответа экрана проверки:', resp.status());
  if (resp.status() !== 200) { await browser.close(); process.exit(1); }
  await page.waitForTimeout(1500);

  const found = await page.evaluate(() => {
    const errs = [...document.querySelectorAll('.katex-error')]
      .map(e => e.textContent.slice(0, 90));
    // красный текст на конечных элементах внутри .katex — неизвестный макрос
    const reds = [];
    document.querySelectorAll('.katex *').forEach(el => {
      if (el.children.length) return;
      const c = getComputedStyle(el).color;
      if (c === 'rgb(204, 0, 0)') reds.push(el.textContent.slice(0, 40));
    });
    // сырой текст с признаками TeX прямо в теле страницы
    const raw = [];
    document.querySelectorAll('.card, .k-card, .rv-block, p, div').forEach(el => {
      if (el.children.length) return;
      const t = el.textContent || '';
      if (/\\begin\{|\\hline|\\frac|\\text\{/.test(t)) raw.push(t.slice(0, 90));
    });
    return { errs, reds, raw };
  });

  console.log('katex-error блоков:', found.errs.length);
  found.errs.forEach(t => console.log('   ', JSON.stringify(t)));
  console.log('красных конечных элементов внутри .katex:', found.reds.length);
  found.reds.slice(0, 10).forEach(t => console.log('   ', JSON.stringify(t)));
  console.log('сырой TeX в тексте страницы:', found.raw.length);
  found.raw.slice(0, 5).forEach(t => console.log('   ', JSON.stringify(t)));

  await page.screenshot({ path: OUT, fullPage: true });
  console.log('снимок:', OUT);
  await browser.close();
  process.exit(found.errs.length + found.reds.length + found.raw.length ? 2 : 0);
})();
