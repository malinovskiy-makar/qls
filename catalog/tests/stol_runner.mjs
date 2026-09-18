/* «Стол» числами в настоящем браузере (дневная сессия 18.09.2026).

   Зачем: приёмка глазами по снимку пропустила пустое облако фона — снимок
   делался после действия, которое облако перерисовывало. Здесь каждая
   страница открывается ЗАНОВО и меряется до первого клика; всё, что README
   макетов называет числом (ширины, размеры шрифта, прозрачность), меряется
   числом. Решение «зелёный/красный» принимает
   `catalog/tests/test_stol_browser.py`.

   Запуск руками:
     STOL_BASE_URL=http://127.0.0.1:8000 node catalog/tests/stol_runner.mjs

   Печатает одну строку `###STOL-JSON###{...}`: ключ — имя замера, значение —
   сырые числа. Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не
   поднялся. */
import { chromium } from 'playwright';

const BASE = process.env.STOL_BASE_URL || 'http://127.0.0.1:8000';
const TOPIC = process.env.STOL_TOPIC || '';
const DESKTOP = [1280, 1440, 1600, 1920];
const PHONE = [360, 390, 430];

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

const out = {};
async function fresh(width, opts = {}) {
  const ctx = await browser.newContext({
    viewport: { width, height: opts.height || (width < 760 ? 844 : 900) },
    deviceScaleFactor: opts.dpr || 1,
    reducedMotion: opts.reduce ? 'reduce' : 'no-preference',
  });
  await ctx.addInitScript(`try { localStorage.setItem('theme', ${JSON.stringify(opts.theme || 'light')}); } catch (e) {}`);
  const page = await ctx.newPage();
  page.setDefaultTimeout(60000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  if (opts.route) await opts.route(page);
  await page.goto(BASE + (opts.path || '/catalog/'), { waitUntil: 'load' });
  return { ctx, page, errors };
}

/* Облако фона: закрашенные пиксели и максимум альфы канвы — без единого
   действия, только ожидание. */
async function canvasStats(page) {
  return page.evaluate(() => {
    const c = document.querySelector('#stol-bg canvas');
    if (!c || !c.width) return { canvas: false, painted: 0, maxAlpha: 0 };
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let painted = 0, maxAlpha = 0;
    for (let i = 3; i < d.length; i += 4) { if (d[i]) { painted++; if (d[i] > maxAlpha) maxAlpha = d[i]; } }
    return { canvas: true, painted, maxAlpha };
  });
}

try {
  /* ── Вход: облако рисуется само, прозрачность 0,5 (README §6) ──────────── */
  for (const theme of ['light', 'dark']) {
    for (const reduce of [false, true]) {
      const { ctx, page, errors } = await fresh(1440, { theme, reduce, dpr: 2 });
      let st = { painted: 0 };
      for (let t = 0; t < 30 && !st.painted; t++) { await page.waitForTimeout(500); st = await canvasStats(page); }
      out['bg ' + theme + (reduce ? ' reduce' : '')] = Object.assign(st, { errors });
      await ctx.close();
    }
  }

  /* ── Вход: размеры из README §1–§2, нет горизонтальной прокрутки ─────────── */
  for (const width of DESKTOP.concat(PHONE)) {
    const { ctx, page, errors } = await fresh(width);
    out['entry ' + width] = await page.evaluate(() => {
      const px = (el, p) => el ? parseFloat(getComputedStyle(el)[p]) : null;
      const w = sel => { const el = document.querySelector(sel); return el ? Math.round(el.getBoundingClientRect().width) : null; };
      const chip = document.querySelector('.se-chip');
      return {
        scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
        titleSize: px(document.querySelector('.se-title'), 'fontSize'),
        searchWidth: w('.se-search'), colWidth: w('.se-col'),
        chipHeight: chip ? Math.round(chip.getBoundingClientRect().height) : null,
        fieldSize: px(document.getElementById('ct-q'), 'fontSize'),
      };
    });
    out['entry ' + width].errors = errors;
    await ctx.close();
  }

  /* ── Выпадашки чипов: ширины 400/250/280, не выше 430 и не ниже края окна ── */
  {
    const { ctx, page } = await fresh(1280, { height: 800 });
    const dd = {};
    for (const key of ['topic', 'difficulty', 'kind']) {
      const btn = page.locator('[data-dd="' + key + '"]');
      if (!(await btn.count())) continue;
      await btn.click();
      dd[key] = await page.evaluate(k => {
        const r = document.getElementById('se-dd-' + k).getBoundingClientRect();
        return { width: Math.round(r.width), height: Math.round(r.height), bottom: Math.round(r.bottom), vh: innerHeight };
      }, key);
      await page.keyboard.press('Escape');
    }
    out['dropdowns 1280x800'] = dd;
    await ctx.close();
  }

  /* ── Отклик выбора при медленном ответе состояния: сразу, не через секунды ── */
  if (TOPIC) {
    const { ctx, page } = await fresh(1440, {
      route: p => p.route('**/api/filter-state/**', async r => { await new Promise(res => setTimeout(res, 3000)); r.continue(); }),
    });
    await page.click('[data-dd="topic"]');
    await page.click('#se-dd-topic [data-topic="' + TOPIC + '"]');
    await page.waitForTimeout(150);
    out['loading feedback'] = await page.evaluate(t => ({
      loading: document.getElementById('stol-entry').classList.contains('is-loading'),
      busyShown: getComputedStyle(document.querySelector('#se-dd-topic .se-dd-busy')).display !== 'none',
      skeletonRows: document.querySelectorAll('#ct-rows .rail-skel').length,
      pressed: document.querySelector('#se-dd-topic [data-topic="' + t + '"]').getAttribute('aria-pressed'),
    }), TOPIC);
    await ctx.close();
  }
} catch (e) {
  out.error = String(e && e.stack || e);
}
await browser.close();
console.log('###STOL-JSON###' + JSON.stringify(out));
