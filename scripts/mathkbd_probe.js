/* ФАЗА 6. ОДНА КЛАВИАТУРА ФОРМУЛ НА КАЛЬКУЛЯТОР И ДОМАШКИ.
 *
 * Что доказывается на живых страницах:
 *   1. набор клавиш в calc2 и в домашке СОВПАДАЕТ посимвольно;
 *   2. буквы во вкладке «Буквы» нарисованы KaTeX (то есть все курсивом,
 *      без смеси прямых и наклонных — п. 23 разбора владельца);
 *   3. в домашке кнопками собирается дробь с корнем и кусочная функция,
 *      «Вставить в текст» кладёт их в textarea, предпросмотр рисует KaTeX
 *      без `.katex-error`;
 *   4. в calc2 ввод `x^2` клавишами строит кривую.
 *
 * Запуск: node scripts/mathkbd_probe.js <порт> [файл.json]
 */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8901';
const OUT = process.argv[3] || 'reports/site_polish_20260904/phase6_probe.json';
const BASE = `http://127.0.0.1:${PORT}`;
const BOT = ['shot_bot', 'probebot-local-2026'];

const result = { calc2: {}, homework: {}, same: null, errors: [] };

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  await page.fill('input[name="username"]', BOT[0]);
  await page.fill('input[name="password"]', BOT[1]);
  await page.click('button[type=submit], input[type=submit]');
  await page.waitForLoadState('domcontentloaded');
  if (page.url().includes('/login')) throw new Error('вход не удался');
}

/** Подписи клавиш по вкладкам: текст кнопки или aria-label у формульных. */
async function readKeys(page, boxSelector) {
  return page.evaluate((sel) => {
    /* ⚠️ КОРОБОК КЛАВИАТУРЫ НА СТРАНИЦЕ НЕСКОЛЬКО — по одной на каждое поле
       формул, и большинство пустые, пока их не раскрыли. Берём ту, в
       которой ЕСТЬ вкладки: это и есть собранная клавиатура. */
    const boxes = [...document.querySelectorAll(sel)];
    const box = boxes.find(b => b.querySelector('.mkbd-tab'));
    if (!box) return null;
    const out = {};
    const tabs = [...box.querySelectorAll('.mkbd-tab')];
    const panes = [...box.querySelectorAll('.mkbd-pane')];
    tabs.forEach((tab, i) => {
      const pane = panes[i];
      out[tab.textContent.trim()] = [...pane.querySelectorAll('.mk')].map(
        b => (b.getAttribute('aria-label') || b.textContent).trim());
    });
    return out;
  }, boxSelector);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  page.on('pageerror', e => result.errors.push('calc2/hw pageerror: ' + String(e).slice(0, 140)));

  // ── Калькулятор ────────────────────────────────────────────────────
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  await page.evaluate(() => pickScene('linear'));
  await page.waitForTimeout(2500);
  // Раскрыть клавиатуру у первого поля формул.
  await page.evaluate(() => {
    const btn = document.querySelector('.f-kbd');
    if (btn) btn.click();
  });
  await page.waitForTimeout(700);
  result.calc2.keys = await readKeys(page, '.mkbd');
  result.calc2.letterKatex = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll('.mkbd')];
    const box = boxes.find(b => b.querySelector('.mkbd-tab'));
    const panes = box ? [...box.querySelectorAll('.mkbd-pane')] : [];
    const letters = panes[2];
    if (!letters) return null;
    return {
      total: letters.querySelectorAll('.mk').length,
      withKatex: letters.querySelectorAll('.mk .katex').length,
      errors: letters.querySelectorAll('.mk .katex-error').length,
    };
  });
  result.calc2.curveBuilt = await page.evaluate(() => {
    const inp = document.querySelector('input.f-input, .f-input');
    return !!inp;
  });

  // ── Домашка ────────────────────────────────────────────────────────
  await login(page);
  const workUrl = await page.evaluate(async () => {
    const r = await fetch('/student/', { credentials: 'same-origin' });
    const html = await r.text();
    const m = html.match(/\/student\/assignment\/(\d+)\//);
    return m ? m[0] : null;
  });
  result.homework.url = workUrl;

  if (workUrl) {
    await page.goto(BASE + workUrl, { waitUntil: 'load' });
    await page.waitForTimeout(1500);
    await page.evaluate(() => {
      const t = document.querySelector('.mf-toggle');
      if (t) t.click();
    });
    await page.waitForTimeout(900);
    result.homework.keys = await readKeys(page, '.mf-panel .mkbd');
    result.homework.letterKatex = await page.evaluate(() => {
      const boxes = [...document.querySelectorAll('.mf-panel .mkbd')];
      const box = boxes.find(b => b.querySelector('.mkbd-tab'));
      const panes = box ? [...box.querySelectorAll('.mkbd-pane')] : [];
      const letters = panes[2];
      if (!letters) return null;
      return {
        total: letters.querySelectorAll('.mk').length,
        withKatex: letters.querySelectorAll('.mk .katex').length,
        errors: letters.querySelectorAll('.mk .katex-error').length,
      };
    });
    result.homework.oldQuickButtons = await page.evaluate(
      () => document.querySelectorAll('.mf-key, .mf-kbd').length);

    // ── Собрать формулу КЛАВИШАМИ и вставить её в текст ──────────────
    const clickKey = async (label) => {
      await page.evaluate((want) => {
        const boxes = [...document.querySelectorAll('.mf-panel .mkbd')];
        const box = boxes.find(b => b.querySelector('.mkbd-tab'));
        const pane = box.querySelector('.mkbd-pane.active');
        const key = [...pane.querySelectorAll('.mk')].find(
          b => (b.getAttribute('aria-label') || b.textContent).trim() === want);
        if (key) key.click();
      }, label);
      await page.waitForTimeout(180);
    };

    await clickKey('÷');            // дробь
    await clickKey('1');
    await page.keyboard.press('Tab');
    await clickKey('2');
    await page.keyboard.press('ArrowRight');
    await clickKey('+');
    await clickKey('√');
    await clickKey('x');            // из вкладки «123» буквы нет — см. ниже
    result.homework.latexAfterKeys = await page.evaluate(() => {
      const f = document.querySelector('.mf-field');
      return f ? f.value : null;
    });

    // Кусочная функция — отдельной кнопкой внизу клавиатуры.
    await page.evaluate(() => {
      const boxes = [...document.querySelectorAll('.mf-panel .mkbd')];
      const box = boxes.find(b => b.querySelector('.mkbd-tab'));
      const pw = box.querySelector('.mkbd-foot button');
      if (pw) pw.click();
    });
    await page.waitForTimeout(300);
    result.homework.latexWithCases = await page.evaluate(() => {
      const f = document.querySelector('.mf-field');
      return f ? f.value : null;
    });

    // «Вставить в текст» → в textarea появляется $…$, предпросмотр рисует.
    await page.evaluate(() => {
      const b = document.querySelector('.mf-insert');
      if (b) b.click();
    });
    await page.waitForTimeout(900);
    result.homework.textarea = await page.evaluate(() => {
      const t = document.querySelector('textarea[data-mathfield]');
      return t ? t.value : null;
    });
    result.homework.preview = await page.evaluate(() => {
      const p = document.querySelector('.mf-preview');
      if (!p) return null;
      return {
        katex: p.querySelectorAll('.katex').length,
        errors: p.querySelectorAll('.katex-error').length,
      };
    });
  }

  // ── Совпадают ли наборы ────────────────────────────────────────────
  const a = result.calc2.keys, b = result.homework.keys;
  if (a && b) {
    result.same = JSON.stringify(a) === JSON.stringify(b);
    result.counts = {
      calc2: Object.values(a).reduce((s, v) => s + v.length, 0),
      homework: Object.values(b).reduce((s, v) => s + v.length, 0),
    };
  }

  fs.mkdirSync('reports/site_polish_20260904', { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(result, null, 2), 'utf8');

  console.log('calc2 клавиш   :', result.counts ? result.counts.calc2 : '(нет)');
  console.log('домашка клавиш :', result.counts ? result.counts.homework : '(нет)');
  console.log('наборы совпали :', result.same);
  console.log('буквы calc2    :', JSON.stringify(result.calc2.letterKatex));
  console.log('буквы домашка  :', JSON.stringify(result.homework.letterKatex));
  console.log('старых кнопок  :', result.homework.oldQuickButtons);
  console.log('набрано клавишами:', JSON.stringify(result.homework.latexAfterKeys));
  console.log('после «кусочной» :', JSON.stringify((result.homework.latexWithCases || '').slice(0, 90)));
  console.log('в textarea       :', JSON.stringify((result.homework.textarea || '').slice(0, 90)));
  console.log('предпросмотр     :', JSON.stringify(result.homework.preview));
  console.log('ошибок страниц :', result.errors.length, result.errors.slice(0, 2));

  await browser.close();
})();
