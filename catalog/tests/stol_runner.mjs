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
  /* Метка загрузки документа: меняется только при настоящей перезагрузке. */
  await ctx.addInitScript('window.__stolBoot = Date.now() + Math.random();');
  if (opts.panels) {
    await ctx.addInitScript(`try { localStorage.setItem('weco_stol', ${JSON.stringify(JSON.stringify(opts.panels))}); } catch (e) {}`);
  }
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
  /* ── S2: задача без перезагрузки, «назад» к той же выдаче, «Дальше» ──── */
  if (TOPIC) {
    const { ctx, page, errors } = await fresh(1440, { path: '/catalog/?topic=' + TOPIC });
    const boot = await page.evaluate(() => window.__stolBoot);
    const ids = await page.$$eval('#ct-rows .rail-row', rows => rows.map(r => Number(r.dataset.id)));
    await page.click('#ct-rows .rail-row');
    await page.waitForSelector('#stol-center .stm');
    const opened = await page.evaluate(() => ({
      boot: window.__stolBoot, path: location.pathname,
      view: document.getElementById('stol-app').dataset.view,
      statement: !!document.querySelector('#stol-center .stm .math-content'),
      helpOpen: document.getElementById('stol').dataset.help,
      railOpen: document.getElementById('stol').dataset.rail,
      pos: (document.getElementById('tb-pos') || {}).textContent || '' }));
    await page.click('#tb-next');
    await page.waitForFunction(first => location.pathname !== '/catalog/problem/' + first + '/', ids[0]);
    await page.waitForSelector('#stol-center .stm');
    const next = await page.evaluate(() => ({ boot: window.__stolBoot, path: location.pathname }));
    await page.goBack();
    await page.waitForFunction(first => location.pathname === '/catalog/problem/' + first + '/', ids[0]);
    await page.goBack();
    await page.waitForFunction(() => document.getElementById('stol-app').dataset.view === 'entry');
    const back = await page.evaluate(() => ({ boot: window.__stolBoot, path: location.pathname + location.search,
                                             rows: document.querySelectorAll('#ct-rows .rail-row').length }));
    out['no reload'] = { boot, ids, opened, next, back, errors };
    await ctx.close();
  }

  /* ── S2: колонка условия 680 при любых панелях, ширины панелей ─────────── */
  if (process.env.STOL_PROBLEM) {
    const states = {
      'rail-closed help-open': { rail: false, help: true }, 'rail-open help-open': { rail: true, help: true },
      'rail-closed help-closed': { rail: false, help: false }, 'rail-open help-closed': { rail: true, help: false },
    };
    for (const width of DESKTOP) {
      for (const [name, panels] of Object.entries(states)) {
        const { ctx, page, errors } = await fresh(width, { path: process.env.STOL_PROBLEM, panels });
        const box = await page.evaluate(() => {
          const w = sel => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect(); return Math.round(r.width); };
          const px = (sel, p) => { const el = document.querySelector(sel); return el ? parseFloat(getComputedStyle(el)[p]) : null; };
          return { col: w('#stol-center'), rail: w('.stol-rail'), help: w('.help-panel'),
                   railStrip: w('.stol-strip--rail'), helpStrip: w('.stol-strip--help'),
                   title: px('.pd-title', 'fontSize'), statement: px('#stol-center .stm', 'fontSize'),
                   scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth };
        });
        box.errors = errors;
        out['desk ' + width + ' ' + name] = box;
        await ctx.close();
      }
    }
    for (const width of PHONE) {
      const { ctx, page, errors } = await fresh(width, { path: process.env.STOL_PROBLEM });
      const box = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
      box.errors = errors;
      out['desk ' + width] = box;
      await ctx.close();
    }
  }
  /* ── S3: помощь и тест у вошедшего ученика (чат — подставной поставщик) ── */
  if (process.env.STOL_SESSION) {
    const login = async ctx => ctx.addCookies([{ name: 'sessionid', value: process.env.STOL_SESSION, url: BASE }]);
    /* Длинный ответ ИИ показывается целиком: 5 000 знаков, ни одного не срезано. */
    {
      const long = 'Шаг решения с формулой $MR = MC$. '.repeat(160).slice(0, 5000);
      const { ctx, page, errors } = await fresh(1440, {
        path: process.env.STOL_PROBLEM,
        route: async p => { await login(p.context()); await p.route('**/api/chat/', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ reply: long }) })); },
      });
      await page.fill('#ai-text', 'Объясни решение подробно');
      await page.click('#ai-send');
      await page.waitForFunction(() => document.querySelectorAll('#help-feed .ai-msg--ai .katex').length > 0);
      out['long reply'] = await page.evaluate(n => {
        const el = [...document.querySelectorAll('#help-feed .ai-msg--ai')].pop();
        const clone = el.cloneNode(true);
        clone.querySelectorAll('.katex').forEach(k => k.replaceWith('F'));
        return { steps: (el.textContent.match(/Шаг решения/g) || []).length, want: n,
                 overflow: el.scrollHeight > el.clientHeight + 2 && getComputedStyle(el).overflowY === 'hidden' };
      }, (long.match(/Шаг решения/g) || []).length);
      out['long reply'].errors = errors;
      await ctx.close();
    }
    /* «Спросить ИИ про этот пункт»: «Пункт а): » в поле и цитата пункта. */
    {
      const { ctx, page, errors } = await fresh(1440, { path: process.env.STOL_PROBLEM, route: async p => login(p.context()) });
      await page.click('.part-ask');
      out['part ask'] = await page.evaluate(() => ({
        field: document.getElementById('ai-text').value,
        quote: document.querySelector('#ai-quote .ai-quote-t').textContent,
        quoteShown: !document.getElementById('ai-quote').hidden,
        focused: document.activeElement && document.activeElement.id,
      }));
      out['part ask'].errors = errors;
      await ctx.close();
    }
    /* Тест: ошибочный вариант краснеет «не то» и второй раз не выбирается (README §5). */
    if (process.env.STOL_TEST) {
      const { ctx, page, errors } = await fresh(1440, { path: process.env.STOL_TEST, route: async p => login(p.context()) });
      await page.click('.opt[data-l="a"]');
      await page.click('#check-btn');
      await page.waitForSelector('.opt.is-tried');
      await page.click('.opt[data-l="a"]', { force: true });
      out['test tried'] = await page.evaluate(() => {
        const a = document.querySelector('.opt[data-l="a"]');
        return { note: a.querySelector('.opt-note').textContent, disabled: a.disabled,
                 pressed: a.getAttribute('aria-pressed'), wrongShown: document.getElementById('msg-wrong').classList.contains('is-on'),
                 check: document.getElementById('check-btn').disabled,
                 rowsVisible: [...document.querySelectorAll('.tq-row')].filter(r => r.offsetParent !== null).map(r => r.id) };
      });
      await page.click('.opt[data-l="b"]');
      await page.click('#check-btn');
      await page.waitForSelector('.opt.is-hit');
      out['test solved'] = await page.evaluate(() => ({
        ok: document.getElementById('ok-sub').textContent,
        tried: document.querySelector('.opt[data-l="a"] .opt-note').textContent,
        hit: document.querySelector('.opt[data-l="b"] .opt-note').textContent,
        why: (document.querySelector('#expl .b') || {}).textContent || '',
        rowsVisible: [...document.querySelectorAll('.tq-row')].filter(r => r.offsetParent !== null).map(r => r.id) }));
      out['test tried'].errors = errors;
      await ctx.close();
    }
  }
} catch (e) {
  out.error = String(e && e.stack || e);
}
await browser.close();
console.log('###STOL-JSON###' + JSON.stringify(out));
