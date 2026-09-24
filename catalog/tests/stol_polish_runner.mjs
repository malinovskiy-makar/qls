/* Полировка «Стола» 24.09.2026 числами в настоящем браузере.

   Решение «зелёный/красный» принимает `catalog/tests/test_stol_polish_browser.py`;
   здесь только замеры. Журнал сессии — `claude/JOURNAL_STOL_POLISH_20260924.md`.

   Запуск руками (нужны адрес, сессия вошедшего и id задач):
     POLISH_BASE_URL=http://127.0.0.1:8000 POLISH_SESSION=… POLISH_PROBLEM=… \
     POLISH_PROBLEM2=… node catalog/tests/stol_polish_runner.mjs

   Печатает одну строку `###POLISH-JSON###{...}`. Коды возврата: 0 — прогон
   дошёл до конца, 3 — браузер не поднялся. */
import { chromium } from 'playwright';

const BASE = process.env.POLISH_BASE_URL || 'http://127.0.0.1:8000';
const SESSION = process.env.POLISH_SESSION || '';
const P1 = process.env.POLISH_PROBLEM || '';
const P2 = process.env.POLISH_PROBLEM2 || '';
/* Задача с самой длинной строкой свойств (фаза 4): в тесте — синтетическая,
   руками — самая длинная в локальной базе. */
const PLONG = process.env.POLISH_LONG || '';

let browser;
try {
  /* Без `--hide-scrollbars`: Playwright в безголовом режиме прячет полосы
     прокрутки, и ширину тонкой полосы (фаза 3) было бы нечем мерить. */
  browser = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'] });
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

const out = {};
async function fresh(opts = {}) {
  const ctx = await browser.newContext({
    viewport: { width: opts.width || 1440, height: opts.height || 900 },
    reducedMotion: 'reduce',
  });
  await ctx.addInitScript(`try { localStorage.setItem('theme', ${JSON.stringify(opts.theme || 'light')}); } catch (e) {}`);
  if (opts.panels) {
    await ctx.addInitScript(`try { if (!sessionStorage.getItem('__polishPanels')) { localStorage.setItem('weco_stol', ${JSON.stringify(JSON.stringify(opts.panels))}); sessionStorage.setItem('__polishPanels', '1'); } } catch (e) {}`);
  }
  if (opts.login !== false && SESSION) {
    await ctx.addCookies([{ name: 'sessionid', value: SESSION, url: BASE }]);
  }
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(BASE + (opts.path || '/catalog/'), { waitUntil: 'load' });
  return { ctx, page, errors };
}
const shown = (page, sel) => page.evaluate(s => {
  const el = document.querySelector(s);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return !el.hidden && getComputedStyle(el).display !== 'none' && r.width > 0 && r.height > 0;
}, sel);
const rect = (page, sel) => page.evaluate(s => {
  const el = document.querySelector(s);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
}, sel);

try {
  /* ── Фаза 1: совет один раз, потом ⓘ ─────────────────────────────────── */
  if (P1 && SESSION) {
    const { ctx, page, errors } = await fresh({ path: '/catalog/problem/' + P1 + '/', panels: { rail: false, help: true } });
    const box = {};
    box.cleanCard = await shown(page, '#help-tipcard');
    box.cleanInfo = await shown(page, '#help-info');
    await page.click('#help-tip-ok');
    box.afterOkCard = await shown(page, '#help-tipcard');
    box.afterOkInfo = await shown(page, '#help-info');
    box.key = await page.evaluate(() => localStorage.getItem('weco_help_tip_seen'));
    await page.reload({ waitUntil: 'load' });
    box.reloadCard = await shown(page, '#help-tipcard');
    box.reloadInfo = await shown(page, '#help-info');
    await page.evaluate(id => weco.stol.open(Number(id)), P2);
    await page.waitForFunction(id => weco.stol.state.problemId === Number(id), P2);
    box.swapCard = await shown(page, '#help-tipcard');
    box.swapInfo = await shown(page, '#help-info');
    await page.hover('#help-info');
    box.hoverPop = await shown(page, '#help-info-pop');
    box.popText = await page.evaluate(() => document.querySelector('#help-info-pop').textContent);
    box.cardText = await page.evaluate(() => document.querySelector('#help-tipcard p').textContent);
    box.popTop = (await rect(page, '#help-info-pop')).top;
    box.btnBottom = (await rect(page, '#help-info')).bottom;
    box.expanded = await page.getAttribute('#help-info', 'aria-expanded');
    await page.keyboard.press('Escape');
    box.escPop = await shown(page, '#help-info-pop');
    box.errors = errors;
    out.tip = box;
    await ctx.close();
  }

  /* ── Фаза 2: строка лимита после ответа чата ─────────────────────────────
     Остаток до реплики — 6 (строка скрыта), после — 5 (строка видна). */
  if (P2 && SESSION) {
    const { ctx, page, errors } = await fresh({ path: '/catalog/problem/' + P2 + '/', panels: { rail: false, help: true } });
    const box = {};
    box.before = await page.evaluate(() => ({ hidden: document.querySelector('#sv-limit').hidden,
                                             n: document.querySelector('#sv-remaining').textContent }));
    await page.fill('#ai-text', 'Как решать?');
    await page.click('#ai-send');
    await page.waitForFunction(() => document.querySelector('#sv-remaining').textContent !== '6', null, { timeout: 15000 }).catch(() => {});
    box.after = await page.evaluate(() => ({ hidden: document.querySelector('#sv-limit').hidden,
                                            n: document.querySelector('#sv-remaining').textContent,
                                            text: document.querySelector('#sv-limit').textContent }));
    box.errors = errors;
    out.limit = box;
    await ctx.close();
  }

  /* ── Фаза 3: «свернуть» слева, тонкие полосы, значок пункта без кружка ─── */
  if (P1 && SESSION) {
    for (const theme of ['light', 'dark']) {
      const { ctx, page, errors } = await fresh({ theme, path: '/catalog/problem/' + P1 + '/', panels: { rail: true, help: true } });
      const box = await page.evaluate(() => {
        const r = el => el.getBoundingClientRect();
        const panel = document.querySelector('.help-panel');
        const collapse = document.querySelector('.help-head [data-stol="help"]');
        const title = document.querySelector('.help-head .help-title b');
        const reset = document.querySelector('#help-reset');
        /* Переполнить ленту помощи и список ленты, чтобы полоса появилась. */
        const bars = {};
        for (const sel of ['.help-body', '.rail-list']) {
          const el = document.querySelector(sel);
          const pad = document.createElement('div');
          pad.style.cssText = 'height: 3000px; flex: none';
          el.appendChild(pad);
          bars[sel] = { gutter: el.offsetWidth - el.clientWidth, over: el.scrollHeight > el.clientHeight,
                        width: el.offsetWidth };
          pad.remove();
        }
        const ask = document.querySelector('.part-ask');
        const cs = getComputedStyle(ask);
        const probe = document.createElement('span');
        probe.style.color = 'var(--accent-ink)';
        document.body.appendChild(probe);
        const accentInk = getComputedStyle(probe).color;
        probe.remove();
        const svg = ask.querySelector('svg').getBoundingClientRect();
        const ab = r(ask);
        return {
          collapseGap: r(collapse).left - r(panel).left,
          collapseFirst: document.querySelector('.help-head').firstElementChild === collapse,
          resetLeft: reset ? r(reset).left : null, titleRight: r(title).right,
          bars,
          ask: { bg: cs.backgroundColor, border: cs.borderTopWidth, svgW: svg.width, w: ab.width, h: ab.height,
                 color: cs.color, accentInk },
        };
      });
      box.errors = errors;
      out['p3 ' + theme] = box;
      await ctx.close();
    }
  }

  /* ── Фаза 4: «Теги · N» не прыгает; длинная строка свойств не вылезает ──── */
  if (PLONG) {
    const path = '/catalog/problem/' + PLONG + '/';
    {
      const { ctx, page, errors } = await fresh({ path, panels: { rail: true, help: true } });
      const box = {};
      box.before = await rect(page, '.pp-tags-btn');
      await page.click('.pp-tags-btn');
      box.open = await rect(page, '.pp-tags-btn');
      box.expanded = await page.getAttribute('.pp-tags-btn', 'aria-expanded');
      box.listShown = await shown(page, '#pp-tags-list');
      box.listTop = (await rect(page, '#pp-tags-list')).top;
      box.subBottom = (await rect(page, '.pp-sub')).bottom;
      await page.click('.pp-tags-btn');
      box.closed = await rect(page, '.pp-tags-btn');
      box.listShownAfter = await shown(page, '#pp-tags-list');
      box.expandedAfter = await page.getAttribute('.pp-tags-btn', 'aria-expanded');
      box.errors = errors;
      out.tags = box;
      await ctx.close();
    }
    const states = { none: { rail: false, help: false }, rail: { rail: true, help: false },
                     help: { rail: false, help: true }, both: { rail: true, help: true } };
    out.propRow = {};
    for (const width of [1440, 1280, 1100]) {
      for (const [name, panels] of Object.entries(states)) {
        const { ctx, page, errors } = await fresh({ width, path, panels });
        const box = await page.evaluate(() => {
          const col = document.querySelector('.desk-col');
          const c = col.getBoundingClientRect();
          const btn = document.querySelector('.pp-tags-btn');
          const words = [...document.querySelectorAll('.pp-sub-words > *')].map(e => e.getBoundingClientRect());
          return { colRight: c.right, btnRight: btn ? btn.getBoundingClientRect().right : null,
                   wordsRight: Math.max(...words.map(r => r.right)), words: words.length,
                   scrollWidth: col.scrollWidth, clientWidth: col.clientWidth,
                   btnTop: btn ? btn.getBoundingClientRect().top : null,
                   subTop: document.querySelector('.pp-sub').getBoundingClientRect().top };
        });
        box.errors = errors;
        out.propRow[width + ' ' + name] = box;
        await ctx.close();
      }
    }
  }

  /* ── Фаза 5: в «Фокусе» панели открываются поверх, фокус остаётся ──────── */
  if (P1 && SESSION) {
    const { ctx, page, errors } = await fresh({ path: '/catalog/problem/' + P1 + '/', panels: { rail: false, help: true } });
    const snap = () => page.evaluate(() => {
      const vis = s => { const el = document.querySelector(s); if (!el) return false;
        const r = el.getBoundingClientRect(); return getComputedStyle(el).display !== 'none' && r.width > 0 && r.height > 0; };
      const w = s => Math.round(document.querySelector(s).getBoundingClientRect().width * 10) / 10;
      return { focus: document.body.classList.contains('stol-is-focus'), nav: vis('.site-nav'),
               help: vis('.help-panel'), helpW: w('.help-panel'), rail: vis('.stol-rail'), railW: w('.stol-rail'),
               colX: document.querySelector('.desk-col').getBoundingClientRect().left,
               dataHelp: document.querySelector('.desk').getAttribute('data-help'),
               dataRail: document.querySelector('.desk').getAttribute('data-rail') };
    });
    const store = () => page.evaluate(() => localStorage.getItem('weco_stol'));
    const box = { storeBefore: await store(), normalBefore: await snap() };
    for (const panel of ['help', 'rail']) {
      await page.keyboard.press('f');
      const inFocus = await snap();
      await page.click('.tb-focus-only[data-stol="' + panel + '"]');
      const opened = await snap();
      await page.keyboard.press('Escape');
      const esc1 = await snap();
      await page.keyboard.press('Escape');
      const esc2 = await snap();
      box[panel] = { inFocus, opened, esc1, esc2 };
    }
    /* Клавиша ] и клик мимо. */
    await page.keyboard.press('f');
    await page.keyboard.press(']');
    box.keyOpen = await snap();
    await page.mouse.click(720, 600);
    box.clickAway = await snap();
    /* Выделение условия → «Обсудить с ИИ» → помощь поверх, фокус включён. */
    await page.evaluate(() => {
      const el = document.querySelector('.stm .math-content') || document.querySelector('.stm');
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    });
    await page.waitForSelector('.ask-pop:not([hidden])', { timeout: 5000 });
    await page.click('.ask-pop');
    box.askPop = await snap();
    await page.keyboard.press('Escape');
    await page.keyboard.press('Escape');
    box.normalAfter = await snap();
    box.storeAfter = await store();
    box.errors = errors;
    out.focus = box;
    await ctx.close();
  }

  /* ── Фаза 6: метки у названия, ровные колонки темы и сложности ────────── */
  if (SESSION) {
    const rowsBox = () => {
      const rows = [...document.querySelectorAll('#ct-rows .rail-row')];
      const R = el => el ? el.getBoundingClientRect() : null;
      return {
        n: rows.length,
        rows: rows.map(r => {
          const t = R(r.querySelector('.rail-title')), m = r.querySelector('.rail-marks > *');
          const topic = R(r.querySelector('.rail-topic')), stars = R(r.querySelector('.rail-stars'));
          return { titleRight: t.right, markLeft: m ? R(m).left : null,
                   topicLeft: topic ? topic.left : null, topicW: topic ? topic.width : null,
                   starsRight: stars ? stars.right : null,
                   metaMarks: r.querySelectorAll('.rail-meta .rail-mark, .rail-meta .rail-saved, .rail-meta .rail-hw').length,
                   bg: getComputedStyle(r).backgroundColor };
        }),
        docW: document.documentElement.scrollWidth, winW: innerWidth,
      };
    };
    for (const theme of ['light', 'dark']) {
      const { ctx, page, errors } = await fresh({ theme, path: '/catalog/' });
      await page.mouse.move(5, 5);
      const box = await page.evaluate(rowsBox);
      box.errors = errors;
      out['rows ' + theme] = box;
      await ctx.close();
    }
    for (const width of [1024, 390]) {
      const { ctx, page } = await fresh({ width, height: width < 760 ? 844 : 900, path: '/catalog/' });
      out['rows doc ' + width] = await page.evaluate(() => ({ docW: document.documentElement.scrollWidth, winW: innerWidth }));
      await ctx.close();
    }
    /* Узкая лента рядом с задачей: те же строки, метки не наезжают на название. */
    {
      const { ctx, page, errors } = await fresh({ path: '/catalog/', panels: { rail: true, help: true } });
      const first = await page.evaluate(() => Number(document.querySelector('#ct-rows .rail-row').getAttribute('data-id')));
      await page.evaluate(id => weco.stol.open(id), first);
      await page.waitForFunction(id => weco.stol.state.problemId === id && weco.stol.state.view === 'stol', first);
      await page.waitForTimeout(300);
      out.narrow = await page.evaluate(() => {
        const rows = [...document.querySelectorAll('#stol-rail-list .rail-row')];
        return { railW: document.querySelector('.stol-rail').getBoundingClientRect().width, n: rows.length,
                 overlaps: rows.filter(r => { const m = r.querySelector('.rail-marks > *');
                   return m && m.getBoundingClientRect().left < r.querySelector('.rail-title').getBoundingClientRect().right - 1; }).length,
                 withMarks: rows.filter(r => r.querySelector('.rail-marks > *')).length,
                 docW: document.documentElement.scrollWidth, winW: innerWidth };
      });
      out.narrow.errors = errors;
      await ctx.close();
    }
  }
} catch (e) {
  out.error = String(e && e.stack || e);
}
await browser.close();
console.log('###POLISH-JSON###' + JSON.stringify(out));
