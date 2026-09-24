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
  if (opts.init) await ctx.addInitScript(opts.init);
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
      /* «Beta 1.0» прячется вместе со сменой вида, без перезагрузки. */
      version: getComputedStyle(document.querySelector('.site-version')).display,
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
                                             version: getComputedStyle(document.querySelector('.site-version')).display,
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
    /* 24.09.2026: прокрутка до конца — низ обеих панелей ровно у низа окна,
       пустой полосы под ними нет; «Beta 1.0» на задаче не показывается. */
    for (const [width, height] of [[1440, 900], [900, 1200]]) {
      const { ctx, page, errors } = await fresh(width, { path: process.env.STOL_PROBLEM, height,
                                                         panels: { rail: true, help: true } });
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.waitForTimeout(250);
      const box = await page.evaluate(() => {
        const bottom = sel => { const el = document.querySelector(sel); return el ? Math.round(el.getBoundingClientRect().bottom) : null; };
        const ver = document.querySelector('.site-version');
        return { rail: bottom('.desk-side--rail'), help: bottom('.desk-side--help'), inner: window.innerHeight,
                 version: ver ? getComputedStyle(ver).display : 'нет' };
      });
      box.errors = errors;
      out['bottom ' + width + 'x' + height] = box;
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

  /* ── S4: карта тем по прямому адресу — свежая страница, без кликов (README §6) ── */
  const NO_TOUR = "try { localStorage.setItem('weconomics.map.tour.v2', 'done'); } catch (e) {}";
  const mapPath = '/catalog/map/' + (TOPIC ? '?topic=' + TOPIC : '');
  async function mapReady(page) {
    await page.waitForFunction(() => window.TMAP && TMAP.isReady(), null, { timeout: 30000 });
  }
  for (const width of DESKTOP) {
    const { ctx, page, errors } = await fresh(width, { path: mapPath, init: NO_TOUR });
    await mapReady(page);
    let painted = 0;
    for (let t = 0; t < 30 && !painted; t++) {
      await page.waitForTimeout(300);
      painted = await page.evaluate(() => {
        const c = document.getElementById('tmap-canvas');
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        /* Движок льёт фон сплошь: считаем пиксели, отличные от фона в углу. */
        let n = 0;
        for (let i = 0; i < d.length; i += 4) if (d[i] !== d[0] || d[i + 1] !== d[1] || d[i + 2] !== d[2]) n++;
        return n;
      });
    }
    out['map ' + width] = await page.evaluate(() => {
      const r = sel => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const b = el.getBoundingClientRect();
        return { w: Math.round(b.width), h: Math.round(b.height), top: Math.round(b.top),
                 right: Math.round(innerWidth - b.right), bottom: Math.round(innerHeight - b.bottom) };
      };
      const app = document.getElementById('stol-app');
      return { view: app.dataset.view, on: app.classList.contains('is-map-on'),
               scrollWidth: document.documentElement.scrollWidth, innerWidth: innerWidth,
               panel: r('.stol-map .tmap-panel'), foot: r('.stol-map .tmap-foot'), back: r('.tmap-back'),
               entryHidden: getComputedStyle(document.getElementById('stol-entry')).visibility === 'hidden',
               bodyScroll: getComputedStyle(document.body).overflow,
               picked: TMAP.picked().map(id => String(TMAP.nodes().find(n => n.id === id).db)),
               count: document.getElementById('stol-map-count').textContent,
               show: document.getElementById('stol-map-show-l').textContent,
               exits: [...document.querySelectorAll('[data-map-exit]')].map(a => a.getAttribute('href')),
               v: TMAP.view() };
    });
    out['map ' + width].painted = painted;
    out['map ' + width].errors = errors;
    await ctx.close();
  }

  /* ── S4: переход «вход → карта → вход» без перезагрузки, 1,25 с (README §6) ── */
  if (TOPIC) {
    const { ctx, page, errors } = await fresh(1440, { path: '/catalog/?topic=' + TOPIC, init: NO_TOUR });
    await page.waitForFunction(() => {
      const h = document.getElementById('stol-bg').__tmapPreview;
      return h && h.stats().state === 'live';
    }, null, { timeout: 30000 });
    const boot = await page.evaluate(() => window.__stolBoot);
    await page.hover('#se-map');
    await page.waitForFunction(() => window.TMAP && TMAP.isReady(), null, { timeout: 30000 });
    await page.click('#se-map');
    const trace = await page.evaluate(() => new Promise(res => {
      const rows = [], t0 = performance.now();
      (function tick() {
        const v = window.TMAP ? TMAP.view() : null;
        rows.push({ ms: Math.round(performance.now() - t0), t: v && v.transit ? v.transit.t : null });
        if (performance.now() - t0 < 2600) requestAnimationFrame(tick); else res(rows);
      })();
    }));
    const opened = await page.evaluate(() => {
      const app = document.getElementById('stol-app');
      const op = sel => Number(getComputedStyle(document.querySelector(sel)).opacity);
      return { boot: window.__stolBoot, url: location.pathname + location.search, view: app.dataset.view,
               on: app.classList.contains('is-map-on'), v: TMAP.view(),
               panels: [op('.stol-map .tmap-head'), op('.stol-map .tmap-panel'), op('.stol-map .tmap-foot')],
               entryHidden: getComputedStyle(document.getElementById('stol-entry')).visibility === 'hidden' };
    });
    await page.click('.tmap-back');
    await page.waitForFunction(() => document.getElementById('stol-app').dataset.view === 'entry', null, { timeout: 10000 });
    await page.waitForTimeout(700);
    const back = await page.evaluate(() => ({
      boot: window.__stolBoot, url: location.pathname + location.search,
      mapHidden: document.getElementById('stol-map').hidden,
      bg: document.getElementById('stol-bg').__tmapPreview.stats().state,
      bgVisible: getComputedStyle(document.querySelector('#stol-bg canvas')).visibility === 'visible',
      search: Number(getComputedStyle(document.querySelector('.se-search')).opacity) }));
    const moving = trace.filter(r => r.t !== null && r.t > 0 && r.t < 1);
    out['map transition'] = { boot, trace: moving.map(r => r.t), first: moving.length ? moving[0].ms : null,
                              last: moving.length ? moving[moving.length - 1].ms : null, opened, back, errors };
    await ctx.close();
  }

  /* ── S4: выбор на карте = фильтр каталога (клик по узлу темы) ─────────── */
  if (TOPIC) {
    const { ctx, page, errors } = await fresh(1440, { path: '/catalog/map/', init: NO_TOUR });
    await mapReady(page);
    let pt = null;
    for (let t = 0; t < 40 && !pt; t++) {
      await page.waitForTimeout(250);
      pt = await page.evaluate(db => {
        const c = document.getElementById('tmap-canvas').getBoundingClientRect();
        const n = TMAP.nodes().find(x => String(x.db) === db && x.k === 'theme');
        if (!n || n.pz < 0) return null;
        const x = c.left + n.px, y = c.top + n.py;
        return document.elementFromPoint(x, y) === document.getElementById('tmap-canvas') ? { x, y } : null;
      }, TOPIC);
    }
    if (pt) {
      await page.mouse.move(pt.x, pt.y);
      await page.waitForTimeout(150);
      await page.mouse.click(pt.x, pt.y);
      await page.waitForTimeout(300);
    }
    out['map pick'] = Object.assign({ clicked: !!pt }, await page.evaluate(() => ({
      topics: Array.from(weco.filters.state.topics), url: location.pathname + location.search,
      count: document.getElementById('stol-map-count').textContent,
      show: document.getElementById('stol-map-show-l').textContent })), { errors });
    await ctx.close();
  }

  /* ── S4: prefers-reduced-motion — без движения, только смена ─────────── */
  {
    const { ctx, page, errors } = await fresh(1440, { reduce: true, init: NO_TOUR });
    await page.hover('#se-map');
    await page.waitForFunction(() => window.TMAP && TMAP.isReady(), null, { timeout: 30000 });
    await page.click('#se-map');
    await page.waitForTimeout(250);
    out['map reduce'] = await page.evaluate(() => ({ view: document.getElementById('stol-app').dataset.view,
      on: document.getElementById('stol-app').classList.contains('is-map-on'), transit: TMAP.view().transit }));
    out['map reduce'].errors = errors;
    await ctx.close();
  }

  /* ── S5: корзина репетитора (README §7) — галочка не открывает строку, корзина
     переживает перезагрузку, «В домашку» → плашка, корзина пуста, пометка растёт ── */
  if (process.env.STOL_TEACHER_SESSION && TOPIC) {
    const asTeacher = async p => p.context().addCookies([{ name: 'sessionid', value: process.env.STOL_TEACHER_SESSION, url: BASE }]);
    const { ctx, page, errors } = await fresh(1280, { path: '/catalog/?topic=' + TOPIC, route: asTeacher });
    const boot = await page.evaluate(() => window.__stolBoot);
    const ids = await page.$$eval('#ct-rows .rail-row', rs => rs.slice(0, 3).map(r => r.dataset.id));
    for (const n of [1, 2, 3]) await page.click('#ct-rows .rail-row:nth-child(' + n + ') .rail-check');
    /* Подмена задачи асинхронна: ждём, не открылась ли она после ответа `?pane=1`. */
    await page.waitForTimeout(1500);
    const picked = await page.evaluate(() => ({ boot: window.__stolBoot, path: location.pathname,
      view: document.getElementById('stol-app').dataset.view,
      bar: !document.getElementById('basket').hidden, n: document.getElementById('basket-n').textContent,
      checked: document.querySelectorAll('#ct-rows .rail-check[aria-checked="true"]').length,
      status: document.querySelectorAll('#ct-rows .rail-status').length,
      barBox: (b => ({ left: Math.round(b.left), right: Math.round(innerWidth - b.right), bottom: Math.round(innerHeight - b.bottom) }))(document.getElementById('basket').getBoundingClientRect()),
      scrollWidth: document.documentElement.scrollWidth, innerWidth }));
    await page.reload({ waitUntil: 'load' });
    const reloaded = await page.evaluate(() => ({ n: document.getElementById('basket-n').textContent,
      checked: document.querySelectorAll('#ct-rows .rail-check[aria-checked="true"]').length }));
    await page.click('#basket-hw-btn');
    await page.click('#basket-hw [data-hw]');
    await page.waitForSelector('#basket-done:not([hidden])');
    const added = await page.evaluate(first => ({ text: document.getElementById('basket-done-t').textContent,
      bar: !document.getElementById('basket').hidden, stored: localStorage.getItem(Object.keys(localStorage).find(k => k.indexOf('weco_basket_') === 0)),
      hw: (document.querySelector('#ct-rows .rail-row[data-id="' + first + '"] .rail-hw') || {}).textContent || '' }), ids[0]);
    out['basket'] = { boot, picked, reloaded, added, errors };
    await ctx.close();
  }

  /* ── S6: телефон (README §8) — шторка «Тема» ставит фильтр, задача без
     перезагрузки со свёрнутыми панелями, подсказка в шторке, ширина ≤ окна ── */
  if (TOPIC && process.env.STOL_SESSION) {
    const asStudent = async p => p.context().addCookies([{ name: 'sessionid', value: process.env.STOL_SESSION, url: BASE }]);
    for (const width of PHONE) {
      const { ctx, page, errors } = await fresh(width, { route: asStudent, init: NO_TOUR });
      const wide = () => page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      const box = { entryOver: await wide(), errors,
        entryFab: await page.evaluate(() => [...document.querySelectorAll('.tg-fab')].filter(x => getComputedStyle(x).display !== 'none').length) };
      const boot = await page.evaluate(() => window.__stolBoot);
      await page.click('[data-dd="topic"]');
      box.sheet = await page.evaluate(() => {
        const r = document.getElementById('se-dd-topic').getBoundingClientRect();
        return { left: Math.round(r.left), right: Math.round(innerWidth - r.right), bottom: Math.round(innerHeight - r.bottom),
                 tall: Math.round(r.height / innerHeight * 100), head: (document.querySelector('#se-dd-topic .se-dd-head b') || {}).textContent };
      });
      await page.click('#se-dd-topic [data-topic="' + TOPIC + '"]');
      await page.waitForFunction(t => weco.filters.state.topics.has(t), TOPIC);
      await page.click('#se-dd-topic [data-dd-close]');
      await page.waitForFunction(() => !document.getElementById('stol-entry').classList.contains('is-loading'));
      box.filter = await page.evaluate(() => ({ url: location.search, closed: document.getElementById('se-dd-topic').hidden }));
      /* Обычная задача (у теста вопрос крупнее): условие 15,5 по README §8. */
      const pid = process.env.STOL_PROBLEM.match(/\d+/)[0];
      await page.click('#ct-rows .rail-row[data-id="' + pid + '"]');
      await page.waitForSelector('#stol-center .stm');
      box.problem = await page.evaluate(b => ({ same: window.__stolBoot === b, view: document.getElementById('stol-app').dataset.view,
        help: document.getElementById('stol').dataset.help, rail: document.getElementById('stol').dataset.rail,
        over: document.documentElement.scrollWidth - innerWidth,
        statement: parseFloat(getComputedStyle(document.querySelector('#stol-center .stm .math-content')).fontSize),
        back: !!document.querySelector('.tb-back') && getComputedStyle(document.querySelector('.tb-back')).display !== 'none',
        fab: [...document.querySelectorAll('.tg-fab')].filter(x => getComputedStyle(x).display !== 'none').length }), boot);
      if (await page.$('.stol-phonebar [data-phone="hint"]')) {
        await page.click('.stol-phonebar [data-phone="hint"]');
        await page.waitForSelector('#help-feed .feed-hint, .help-panel .feed-hint');
        box.help = await page.evaluate(() => {
          const r = document.querySelector('.help-panel').getBoundingClientRect();
          return { top: Math.round(r.top), bottom: Math.round(innerHeight - r.bottom), help: document.getElementById('stol').dataset.help,
                   hint: document.querySelectorAll('.help-panel .feed-hint').length,
                   top1: document.elementFromPoint(innerWidth / 2, 400).closest('.help-panel') !== null };
        });
      }
      await ctx.close();
      const map = await fresh(width, { path: '/catalog/map/?topic=' + TOPIC, init: NO_TOUR });
      await map.page.waitForFunction(() => window.TMAP && TMAP.isReady(), null, { timeout: 30000 });
      await map.page.waitForTimeout(500);
      box.map = await map.page.evaluate(() => ({ over: document.documentElement.scrollWidth - innerWidth,
        panel: getComputedStyle(document.querySelector('.stol-map .tmap-panel')).display,
        foot: (r => ({ left: Math.round(r.left), right: Math.round(innerWidth - r.right) }))(document.querySelector('.stol-map .tmap-foot').getBoundingClientRect()),
        W: TMAP.view().W, H: TMAP.view().H, tall: TMAP.view().tall,
        /* Форма корпуса на экране: высота разлёта узлов к ширине (README §8 — вертикальный). */
        shape: (ns => +((Math.max(...ns.map(n => n.py)) - Math.min(...ns.map(n => n.py))) /
                        (Math.max(...ns.map(n => n.px)) - Math.min(...ns.map(n => n.px)))).toFixed(2))(TMAP.nodes().filter(n => n.pz > 0)) }));
      box.map.errors = map.errors;
      await map.ctx.close();
      out['phone ' + width] = box;
    }
  }
} catch (e) {
  out.error = String(e && e.stack || e);
}
await browser.close();
console.log('###STOL-JSON###' + JSON.stringify(out));
