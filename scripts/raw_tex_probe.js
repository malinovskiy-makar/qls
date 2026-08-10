/**
 * Сырой TeX на экранах кабинета — замер, а не впечатление.
 *
 * Открывает переданные адреса и считает на каждом:
 *  • блоки .katex-error (KaTeX сдался и напечатал исходник);
 *  • куски сырого TeX прямо в тексте страницы (\begin{, \frac, \[ … \]);
 *  • красные конечные элементы внутри .katex (неизвестный макрос без класса
 *    ошибки — их не видно ни в консоли, ни по .katex-error).
 *
 * Запускать ИЗ КОРНЯ проекта:
 *   node scripts/raw_tex_probe.js <порт> <адрес> [адрес…]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8199';
const PATHS = process.argv.slice(3);
const BASE = `http://127.0.0.1:${PORT}`;

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  let total = 0;
  for (const url of PATHS) {
    const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
    if (resp.status() !== 200) {
      console.log(`${url} — КОД ${resp.status()}, пропускаю`);
      total += 1;
      continue;
    }
    await page.waitForTimeout(900);
    const found = await page.evaluate(() => {
      const errs = [...document.querySelectorAll('.katex-error')]
        .map((e) => e.textContent.slice(0, 70));
      const reds = [];
      document.querySelectorAll('.katex *').forEach((el) => {
        if (el.children.length) { return; }
        if (getComputedStyle(el).color === 'rgb(204, 0, 0)') {
          reds.push(el.textContent.slice(0, 40));
        }
      });
      const raw = [];
      const SKIP = ['SCRIPT', 'STYLE', 'TEMPLATE', 'TEXTAREA'];
      document.querySelectorAll('body *').forEach((el) => {
        if (el.children.length || el.closest('.katex')) { return; }
        // Свой же код страницы сырым TeX не считаем.
        if (SKIP.indexOf(el.tagName) !== -1 || el.closest('template')) { return; }
        const t = el.textContent || '';
        if (/\\begin\{|\\frac|\\hline|\\\[|\\\]|\\text\{/.test(t)) {
          raw.push(t.replace(/\s+/g, ' ').slice(0, 70));
        }
      });
      return { errs, reds, raw };
    });
    const sum = found.errs.length + found.reds.length + found.raw.length;
    total += sum;
    console.log(`${url} — ошибок ${found.errs.length}, красных ${found.reds.length}, сырого ${found.raw.length}`);
    [...found.errs, ...found.reds, ...found.raw].slice(0, 6)
      .forEach((t) => console.log('     ', JSON.stringify(t)));
  }
  console.log('\nвсего находок:', total);
  await browser.close();
  process.exit(total ? 2 : 0);
})();
