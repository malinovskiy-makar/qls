/* Тренажёр ВП в настоящем браузере: пять ручных сценариев владельца, состояния
   таймера, «время вышло», офлайн и телефон.

   Раннер ходит по живому серверу тестового прогона как обычный ГОСТЬ (без входа) и
   печатает результат машинно-разбираемой строкой после ###VP-JSON###. Решение
   «зелёный/красный» принимает питон-тест `vp/tests/test_browser.py`.

   Сценарии владельца:
     1. начать вариант с таймером, заполнить поля, перезагрузить — всё на месте;
     2. пройти змейку от первого поля до тридцатого только клавишей Enter;
     3. «Сдать» с пятью пустыми — в окне ровно пять номеров, клик возвращает к заданию;
     4. телефон: при фокусе нет зума, шапка не закрывает поле;
     5. тёмная тема на любом экране.

   Сессия 4 (ADR 0127): посадочная `/vp/` (десктоп и телефон 390 px, контраст в обеих темах),
   посадочная отдаёт события скрипту аналитики (что они доходят до базы, сверяет питон) и шапка
   персонала (8 пунктов) на десяти ширинах — новый пункт меню не должен распирать страницу.

   Запуск руками против живого сервера:
     VP_BASE_URL=http://127.0.0.1:8000 VP_SHOT_DIR=/tmp/vp node vp/tests/browser_take.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер или страница не поднялись.
   Красные проверки раннер не роняет: их читает питон.                            */
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = process.env.VP_BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = process.env.VP_SHOT_DIR || '';
const out = { checks: {}, attempts: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail: detail === undefined ? null : detail }; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
async function shot(page, name, full = false) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: full });
}

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

// ---- общие помощники, исполняемые внутри страницы ---------------------------------
const noHScroll = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth <= document.documentElement.clientWidth);
const activeInfo = (page) => page.evaluate(() => {
  const a = document.activeElement;
  const box = a && a.closest ? a.closest('.vp-item') : null;
  return { id: a ? a.id : '', item: box ? box.dataset.n : null, tag: a ? a.tagName : '' };
});
const timerSeconds = (page) => page.evaluate(() => {
  const m = /(\d+):(\d+)/.exec(document.getElementById('vp-timer').textContent);
  return m ? (+m[1]) * 60 + (+m[2]) : null;
});
const visibleBelowBar = (page, selector) => page.evaluate((sel) => {
  const el = document.querySelector(sel);
  const bar = document.getElementById('vp-bar').getBoundingClientRect();
  const r = el.getBoundingClientRect();
  return { top: Math.round(r.top), barBottom: Math.round(bar.bottom), bottom: Math.round(r.bottom),
           vh: window.innerHeight, ok: r.top >= bar.bottom - 1 && r.bottom <= window.innerHeight + 1 };
}, selector);

/* Контраст WCAG по цветам, которые браузер реально нарисовал: цвет текста против
   эффективного фона (полупрозрачные слои смешиваются с родителями). */
async function contrastOf(page, selectors) {
  return page.evaluate((sels) => {
    const parse = (c) => {
      const m = c.match(/rgba?\(([^)]+)\)/);
      if (!m) return [0, 0, 0, 1];
      const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const blend = (top, bottom) => {
      const a = top[3];
      return [top[0] * a + bottom[0] * (1 - a), top[1] * a + bottom[1] * (1 - a), top[2] * a + bottom[2] * (1 - a), 1];
    };
    const bgOf = (el) => {
      const chain = [];
      for (let n = el; n; n = n.parentElement) chain.push(parse(getComputedStyle(n).backgroundColor));
      let base = parse(getComputedStyle(document.body).backgroundColor);
      if (base[3] === 0) base = [255, 255, 255, 1];
      for (let i = chain.length - 1; i >= 0; i--) if (chain[i][3] > 0) base = blend(chain[i], base);
      return base;
    };
    const lum = (c) => {
      const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
      return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
    };
    const res = {};
    for (const sel of sels) {
      let worst = null;
      for (const el of document.querySelectorAll(sel)) {
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height || !(el.textContent || el.value || '').trim()) continue;
        const fg = blend(parse(getComputedStyle(el).color), bgOf(el));
        const bg = bgOf(el);
        const l1 = lum(fg), l2 = lum(bg);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        if (worst === null || ratio < worst) worst = ratio;
      }
      if (worst !== null) res[sel] = Math.round(worst * 100) / 100;
    }
    return res;
  }, selectors);
}
const lowContrast = (res, min = 4.5) => Object.entries(res).filter(([, v]) => v < min);
/* Переключение темы для замера. ⚠️ Тема плавно перекрашивает страницу (0,2 с): замер
   посреди перехода видит цвета «между» и даёт ложные 1,05:1. На время замера
   переходы выключены. */
const setTheme = (page, dark) => page.evaluate((d) => {
  if (!document.getElementById('vp-test-no-transition')) {
    const style = document.createElement('style');
    style.id = 'vp-test-no-transition';
    style.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
    document.head.appendChild(style);
  }
  if (d) document.documentElement.setAttribute('data-theme', 'dark');
  else document.documentElement.removeAttribute('data-theme');
}, dark);

const TAKE_SELECTORS = ['.vp-item-text', '.vp-input', '.vp-opt span', '.vp-timer', '.vp-timer-cap', '.vp-count',
  '.vp-bar-name', '.vp-bar-sub', '.vp-btn', '.vp-cell', '.vp-note', '.vp-h2', '.vp-mute', '.vp-affix',
  '.vp-legend span', '.vp-rail-cap', '.vp-item-num'];
const INTRO_SELECTORS = ['.vp-h1', '.vp-h2', '.vp-sub', '.vp-table td', '.vp-stack', '.vp-note', '.vp-mode b',
  '.vp-mode span span', '.vp-btn', '.vp-mute', '.vp-eyebrow', '.vp-big'];
const LANDING_SELECTORS = ['.vp-h1', '.vp-lead', '.vp-h2', '.vp-h3', '.vp-stack p', '.vp-text', '.vp-table th',
  '.vp-table td', '.vp-mute', '.vp-eyebrow', '.vp-btn', '.vp-vrow-main b', '.vp-chain-demo span', '.vp-pill'];
const RESULT_SELECTORS = ['.vp-score-num b', '.vp-score-num span', '.vp-mute', '.vp-h3', '.vp-brow-name',
  '.vp-brow-score', '.vp-brow-pct', '.vp-btn', '.vp-cmp-head', '.vp-cmp-axis span', '.vp-cmp-label',
  '.vp-crow-n', '.vp-crow-mine', '.vp-crow-right', '.vp-crow-right b', '.vp-crow-pts', '.vp-clink',
  '.vp-crow-text', '.vp-tcard-n', '.vp-tcard-title', '.vp-tcard-score', '.vp-tcard-text', '.vp-tcard-line',
  '.vp-topt', '.vp-topt-n', '.vp-tag', '.vp-math', '.vp-solution summary', '.vp-cta-card h2', '.vp-cta-card p',
  '.vp-cta-btn', '.vp-cta-link', '.vp-practice-out'];

async function contrastBothThemes(page, prefix, selectors) {
  await setTheme(page, false);
  const light = lowContrast(await contrastOf(page, selectors));
  check(`${prefix}.contrast_light`, light.length === 0, light);
  await setTheme(page, true);
  const dark = lowContrast(await contrastOf(page, selectors));
  check(`${prefix}.contrast_dark`, dark.length === 0, dark);
  await setTheme(page, false);
}

async function startAttempt(page, slug, timer = true) {
  await page.goto(`${BASE}/vp/${slug}/`, { waitUntil: 'load', timeout: 30000 });
  if (!timer) await page.check('input[name=with_timer][value="0"]');
  await Promise.all([
    page.waitForURL(/\/vp\/a\/[^/]+\/$/, { timeout: 30000 }),
    page.click('button:has-text("Начать вариант")'),
  ]);
  await page.waitForSelector('#vp-form', { timeout: 15000 });
  return page.url().split('/a/')[1].replace(/\/$/, '');
}

try {
  // ==================================================================== ДЕСКТОП
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await desktop.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
  const page = await desktop.newPage();

  // ---- посадочная /vp/
  const lp = await desktop.newPage();
  await lp.goto(`${BASE}/vp/`, { waitUntil: 'load', timeout: 30000 });
  check('d.landing_six_sections', (await lp.locator('.vp-sec').count()) === 6, await lp.locator('.vp-sec h2').allInnerTexts());
  check('d.landing_block_table_five_rows', (await lp.locator('.vp-table--blocks tbody tr').count()) === 5);
  check('d.landing_chain_example_four_words', (await lp.locator('.vp-chain-demo span').count()) === 4,
    await lp.locator('.vp-chain-demo').allInnerTexts());
  check('d.landing_lists_four_variants', (await lp.locator('.vp-vrow').count()) === 4);
  check('d.landing_no_hscroll', await noHScroll(lp));
  check('d.landing_nav_item_is_active', await lp.evaluate(() => {
    // Подпись — первый текстовый узел: метка NEW у пункта лежит в <span>, и `textContent` был бы «Тренажёр ВПNEW».
    const active = [...document.querySelectorAll('nav.site-nav > .nav-links .nav-link.is-active')]
      .map((a) => a.firstChild.textContent.trim());
    return active.length === 1 && active[0] === 'Тренажёр ВП';
  }));
  await shot(lp, 'landing_light_desktop', true);
  await contrastBothThemes(lp, 'd.landing', LANDING_SELECTORS);
  await setTheme(lp, true);
  await shot(lp, 'landing_dark_desktop', true);
  await setTheme(lp, false);
  // Тело `sendBeacon` Playwright не отдаёт, поэтому сами события сверяет питон по таблице `Event`
  // (`test_browser.check_database`); здесь – что скрипт аналитики и список событий на странице есть.
  check('d.landing_events_are_on_the_page', await lp.evaluate(() => {
    const node = document.getElementById('vp-events');
    return !!node && JSON.parse(node.textContent).some((e) => e.name === 'vp_landing_open')
      && !!(window.weco && typeof window.weco.track === 'function');
  }));
  await Promise.all([lp.waitForURL(/\/vp\/vp-ui\/$/, { timeout: 30000 }), lp.click('a[href="/vp/vp-ui/"]')]);
  check('d.landing_go_opens_the_variant', /Пробный вариант/.test(await lp.textContent('h1')), await lp.textContent('h1'));
  check('d.intro_events_are_on_the_page', await lp.evaluate(() => {
    const node = document.getElementById('vp-events');
    return !!node && JSON.parse(node.textContent).some((e) => e.name === 'vp_intro_open' && e.props.variant === 'vp-ui');
  }));
  await lp.close();

  // ---- шапка персонала: восемь пунктов не распирают страницу ни на одной ширине
  const staffSession = process.env.VP_STAFF_SESSION || '';
  if (staffSession) {
    const staffCtx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await staffCtx.addCookies([{ name: 'sessionid', value: staffSession, url: BASE }]);
    const sp2 = await staffCtx.newPage();
    await sp2.goto(`${BASE}/vp/`, { waitUntil: 'load', timeout: 30000 });
    check('d.nav_staff_has_eight_items_or_burger', await sp2.evaluate(() =>
      document.querySelectorAll('nav.site-nav > .nav-links .nav-link').length === 8), await sp2.evaluate(() =>
      [...document.querySelectorAll('nav.site-nav > .nav-links .nav-link')].map((a) => a.textContent.trim())));
    for (const w of [390, 821, 900, 980, 981, 1161, 1300, 1421, 1440, 1500, 1920]) {
      await sp2.setViewportSize({ width: w, height: 900 });
      await sleep(150);
      const wide = await sp2.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
      check(`d.nav_staff_fits_${w}`, wide.sw <= wide.iw, wide);
    }
    await staffCtx.close();
  }

  // ---- вход
  await page.goto(`${BASE}/vp/vp-ui/`, { waitUntil: 'load', timeout: 30000 });
  check('d.intro_five_blocks', (await page.locator('#vp-blocks tr').count()) === 5,
    await page.locator('#vp-blocks tr').allInnerTexts());
  check('d.intro_no_hscroll', await noHScroll(page));
  // Абзац со жирным словом не должен быть flex-контейнером: иначе фрагмент вываливается
  // отдельной строкой посреди предложения.
  check('d.intro_snake_paragraph_is_flowing_text', await page.evaluate(() => {
    const p = [...document.querySelectorAll('.vp-card p')].find((e) => /Каждый следующий ответ/.test(e.textContent));
    return !!p && getComputedStyle(p).display === 'block' && !!p.querySelector('b');
  }));
  await shot(page, 'intro_light_desktop', true);
  await contrastBothThemes(page, 'd.intro', INTRO_SELECTORS);
  await setTheme(page, true);
  await shot(page, 'intro_dark_desktop', true);
  await setTheme(page, false);

  // ---- сценарий 1 и 2: старт, змейка на Enter
  const code = await startAttempt(page, 'vp-ui');
  out.attempts.desktop = code;
  const takeUrl = page.url();
  check('d.start_goes_to_attempt', /\/vp\/a\/[A-Za-z0-9_-]{12}\/$/.test(takeUrl), takeUrl);
  check('d.all_44_items', (await page.locator('.vp-item').count()) === 44);
  check('d.take_no_hscroll', await noHScroll(page));
  check('d.take_hides_feedback_fab', await page.evaluate(() => {
    const fab = document.querySelector('.tg-fab');
    return !fab || getComputedStyle(fab).display === 'none';
  }));
  await shot(page, 'take_light_desktop_top');

  await page.focus('#vp-in-1');
  let walkFail = null;
  const t0 = await timerSeconds(page);
  for (let i = 1; i <= 30; i++) {
    await page.keyboard.type('слово' + i);
    await page.keyboard.press('Enter');
    if (i < 30) {
      const a = await activeInfo(page);
      if (a.id !== 'vp-in-' + (i + 1)) { walkFail = { step: i, got: a }; break; }
    }
  }
  check('d.enter_walk_1_to_30', walkFail === null, walkFail);
  const afterWalk = await activeInfo(page);
  check('d.enter_after_last_goes_to_31', afterWalk.item === '31', afterWalk);
  check('d.enter_never_submits', page.url() === takeUrl);
  check('d.counter_30', (await page.textContent('#vp-answered')) === '30', await page.textContent('#vp-answered'));
  check('d.tiles_30', (await page.locator('#vp-grid .vp-cell.is-answered').count()) === 30);

  // ---- сценарий 1: перезагрузка — всё на месте
  await page.fill('#vp-in-30', 'ПОСЛЕДНЕЕ');
  const beforeReload = await timerSeconds(page);
  await page.reload({ waitUntil: 'load' });
  await page.waitForSelector('#vp-form');
  const values = await page.$$eval('.vp-input', (els) => els.map((e) => e.value));
  const expected = Array.from({ length: 30 }, (_, i) => (i === 29 ? 'ПОСЛЕДНЕЕ' : 'слово' + (i + 1)));
  const wrong = values.map((v, i) => [i + 1, v, expected[i]]).filter(([, v, e]) => v !== e);
  check('d.reload_keeps_all_30', wrong.length === 0, wrong.slice(0, 5));
  check('d.reload_keeps_last_typed', values[29] === 'ПОСЛЕДНЕЕ', values[29]);
  const afterReload = await timerSeconds(page);
  check('d.timer_continues', afterReload !== null && afterReload <= beforeReload && beforeReload - afterReload < 30 && afterReload < 1800,
    { t0, beforeReload, afterReload });
  check('d.counter_30_after_reload', (await page.textContent('#vp-answered')) === '30');

  // ---- сценарий 3: окно сдачи с пятью пустыми
  for (const n of [31, 32, 33, 34]) await page.locator(`#vp-item-${n} input[type=radio]`).first().check();
  for (const n of [36, 37, 38, 39, 41]) await page.locator(`#vp-item-${n} input[type=checkbox]`).first().check();
  await page.locator('#vp-item-43 input[type=radio]').first().check();
  await page.fill('#vp-in-17', '');                       // стёрли: пустое
  check('d.counter_after_marks', (await page.textContent('#vp-answered')) === '39', await page.textContent('#vp-answered'));
  await page.click('#vp-submit');
  check('d.dialog_opens', await page.locator('#vp-dialog').evaluate((d) => d.open));
  const chips = await page.locator('#vp-dialog-chips .vp-chip').allInnerTexts();
  check('d.dialog_five_numbers_exact', JSON.stringify(chips) === JSON.stringify(['17', '35', '40', '42', '44']), chips);
  const dialogText = await page.textContent('#vp-dialog-text');
  check('d.dialog_text', /Осталось \d\d:\d\d, и не отвечено 5 заданий\. Неотвеченное засчитывается как ноль\./.test(dialogText), dialogText);
  await shot(page, 'dialog_light_desktop');
  await page.click('#vp-dialog-chips .vp-chip:has-text("17")');
  await sleep(900);
  check('d.chip_closes_dialog', !(await page.locator('#vp-dialog').evaluate((d) => d.open)));
  const at17 = await activeInfo(page);
  check('d.chip_returns_to_item17', at17.id === 'vp-in-17', at17);
  const vis17 = await visibleBelowBar(page, '#vp-in-17');
  check('d.item17_visible_below_header', vis17.ok, vis17);
  check('d.item17_marked_current', await page.evaluate(() =>
    document.getElementById('vp-item-17').classList.contains('is-current')
    && !!document.querySelector('#vp-grid .vp-cell.is-current[data-n="17"]')));
  await page.click('#vp-submit');
  await page.click('#vp-back');
  check('d.back_button_keeps_page', !(await page.locator('#vp-dialog').evaluate((d) => d.open)) && page.url() === takeUrl);
  await shot(page, 'take_light_desktop_mid');

  // ---- сценарий 5: тёмная тема на экране прохождения
  await page.click('#vp-theme');
  check('d.theme_toggle_take', await page.evaluate(() =>
    document.documentElement.getAttribute('data-theme') === 'dark' && localStorage.getItem('theme') === 'dark'));
  await shot(page, 'take_dark_desktop_mid');
  await page.click('#vp-theme');
  check('d.theme_toggle_back', await page.evaluate(() =>
    !document.documentElement.hasAttribute('data-theme') && localStorage.getItem('theme') === 'light'));
  await page.evaluate(() => window.scrollTo(0, 0));
  await contrastBothThemes(page, 'd.take', TAKE_SELECTORS);
  await setTheme(page, true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await shot(page, 'take_dark_desktop_top');
  await setTheme(page, false);

  // ---- сдача
  await page.click('#vp-submit');
  await Promise.all([page.waitForURL(/\/vp\/r\/[^/]+\/$/, { timeout: 30000 }), page.click('#vp-confirm')]);
  const resultUrl = page.url();
  check('d.submit_goes_to_result', /\/vp\/r\//.test(resultUrl), resultUrl);
  check('d.result_score_present', /^\d+(,\d+)?$/.test((await page.textContent('.vp-score-num b')).trim()),
    await page.textContent('.vp-score-num b'));
  check('d.result_has_five_blocks', (await page.locator('.vp-brow').count()) === 5);
  check('d.result_no_hscroll', await noHScroll(page));
  await shot(page, 'result_light_desktop', true);
  await contrastBothThemes(page, 'd.result', RESULT_SELECTORS);
  await setTheme(page, true);
  await shot(page, 'result_dark_desktop', true);
  await setTheme(page, false);
  await page.click('#theme-toggle');
  check('d.result_theme_toggle', await page.evaluate(() => document.documentElement.getAttribute('data-theme') === 'dark'));
  await page.click('#theme-toggle');
  // ---- разбор: змейка цепочкой, тесты, «дорешать вне зачёта»
  check('d.review_chain_30_rows', (await page.locator('#vp-chain .vp-crow').count()) === 30);
  check('d.review_tests_14_cards', (await page.locator('#vp-tests .vp-tcard').count()) === 14);
  check('d.review_link_broken_named', await page.evaluate(() => {
    const broken = document.querySelector('.vp-clink.is-broken');
    return !!broken && /здесь цепь порвалась: следующий ответ должен был начинаться на «./.test(broken.textContent);
  }));
  check('d.review_five_practice_buttons', (await page.locator('[data-practice-open]').count()) === 5);
  check('d.review_share_button', (await page.locator('#vp-share').count()) === 1);
  await page.click('#vp-share');
  check('d.share_click_copies_the_link', await page.evaluate(async (expected) => {
    try { return (await navigator.clipboard.readText()) === expected; } catch (e) { return 'нет доступа к буферу'; }
  }, resultUrl) === true, resultUrl);
  check('d.comparison_shown', await page.evaluate(() => /Выше, чем у \d+% прошедших этот вариант/.test(
    (document.querySelector('.vp-cmp-head') || {}).textContent || '')
    && !!document.querySelector('.vp-cmp-you') && !!document.querySelector('.vp-cmp-med')));
  check('d.comparison_marker_inside_scale', await page.evaluate(() => {
    const scale = document.querySelector('.vp-cmp-scale').getBoundingClientRect();
    const you = document.querySelector('.vp-cmp-you').getBoundingClientRect();
    return you.left >= scale.left - 2 && you.right <= scale.right + 2;
  }));
  const pageBefore = await page.content();
  const scoreBefore = (await page.textContent('.vp-score-num b')).trim();
  await page.locator('#vp-r-17 [data-practice-open]').click();
  check('d.practice_form_opens', await page.locator('#vp-r-17 [data-practice-form]').isVisible());
  await page.fill('#vp-pr-17', 'неверноеслово');
  await page.click('#vp-r-17 [data-practice-form] button[type=submit]');
  let wrongText = '';
  try {
    await page.waitForFunction(() => /Неверно\. Верный ответ: /.test(
      document.querySelector('#vp-r-17 [data-practice-out]').textContent), null, { timeout: 15000 });
    wrongText = await page.textContent('#vp-r-17 [data-practice-out]');
  } catch (e) { wrongText = (await page.textContent('#vp-r-17 [data-practice-out]')) || ''; }
  const reference17 = wrongText.replace(/^.*Верный ответ:\s*/, '').trim();
  check('d.practice_wrong_gives_reference', /^Неверно\. Верный ответ: \S+$/.test(wrongText), wrongText);
  check('d.practice_reference_was_not_on_page', reference17.length > 0 && !pageBefore.includes(reference17), reference17);
  await shot(page, 'result_practice_wrong_desktop');
  await page.fill('#vp-pr-17', reference17);
  await page.click('#vp-r-17 [data-practice-form] button[type=submit]');
  let rightText = '';
  try {
    await page.waitForFunction(() => /^Верно: /.test(
      document.querySelector('#vp-r-17 [data-practice-out]').textContent), null, { timeout: 15000 });
    rightText = await page.textContent('#vp-r-17 [data-practice-out]');
  } catch (e) { rightText = (await page.textContent('#vp-r-17 [data-practice-out]')) || ''; }
  check('d.practice_right_says_right', rightText === 'Верно: ' + reference17, rightText);
  await page.locator('#vp-r-35 [data-practice-open]').click();
  await page.locator('#vp-r-35 input[name=raw]').first().check();
  await page.click('#vp-r-35 [data-practice-form] button[type=submit]');
  let choiceText = '';
  try {
    await page.waitForFunction(() => /^(Верно|Неверно)/.test(
      document.querySelector('#vp-r-35 [data-practice-out]').textContent), null, { timeout: 15000 });
    choiceText = await page.textContent('#vp-r-35 [data-practice-out]');
  } catch (e) { choiceText = (await page.textContent('#vp-r-35 [data-practice-out]')) || ''; }
  check('d.practice_choice_is_checked', /^(Верно: |Неверно\. Верный ответ: )\d+\. /.test(choiceText), choiceText);
  check('d.practice_score_unchanged', (await page.textContent('.vp-score-num b')).trim() === scoreBefore, scoreBefore);
  check('d.practice_says_it_does_not_count', /На балл не влияет, он уже записан/.test(
    await page.textContent('#vp-r-17 [data-practice-form]')));
  await shot(page, 'result_review_desktop', true);
  // после сдачи назад на страницу прохождения не попасть
  await page.goto(takeUrl, { waitUntil: 'load' });
  check('d.take_after_submit_redirects', /\/vp\/r\//.test(page.url()), page.url());

  // ---- чужой браузер: публичный результат, но не попытка
  const stranger = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const sp = await stranger.newPage();
  const shared = await sp.goto(resultUrl, { waitUntil: 'load' });
  const sharedText = await sp.textContent('body');
  check('d.public_result_open', shared.status() === 200 && /из 100/.test(sharedText), shared.status());
  check('d.public_result_no_answers', !/слово\d|ПОСЛЕДНЕЕ/.test(sharedText));
  const references = [...fs.readFileSync('data/vp/_selftest.yaml', 'utf8').matchAll(/^\s+answer: (.+?)\s*$/gm)]
    .map((m) => m[1]);
  check('d.public_result_references_loaded', references.length === 30, references.length);
  const sharedHtml = await sp.content();
  const leaked = references.filter((word) => sharedHtml.includes(word));
  check('d.public_result_no_reference', leaked.length === 0, leaked);
  check('d.public_result_no_review_blocks', (await sp.locator('#vp-chain, #vp-tests, [data-practice], #vp-share').count()) === 0
    && !/эталон/.test(sharedText));
  check('d.public_result_repeat_button', (await sp.locator('a:has-text("Пройти этот же вариант")').count()) === 1);
  check('d.public_result_comparison', /Выше, чем у \d+% прошедших этот вариант/.test(sharedText));
  await shot(sp, 'result_public_desktop', true);
  await contrastBothThemes(sp, 'd.public', RESULT_SELECTORS);
  const foreign = await sp.goto(takeUrl, { waitUntil: 'load' });
  check('d.foreign_take_404', foreign.status() === 404, foreign.status());
  await stranger.close();
  // События копятся в браузере и уходят пачкой раз в пять секунд: ждём последнюю, потом закрываем.
  await sleep(6500);
  await desktop.close();

  // ============================================================ СЦЕНАРИЙ 4: ТЕЛЕФОН
  const phone = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  });
  const mp = await phone.newPage();
  const mlp = await phone.newPage();
  await mlp.goto(`${BASE}/vp/`, { waitUntil: 'load', timeout: 30000 });
  check('m.landing_no_hscroll', await noHScroll(mlp));
  await shot(mlp, 'landing_light_phone', true);
  await contrastBothThemes(mlp, 'm.landing', LANDING_SELECTORS);
  await setTheme(mlp, true);
  await shot(mlp, 'landing_dark_phone', true);
  await setTheme(mlp, false);
  await mlp.click('.nav-burger');
  check('m.landing_burger_lists_the_item', await mlp.evaluate(() => [...document.querySelectorAll('.nav-panel .nav-link')]
    .some((a) => a.firstChild.textContent.trim() === 'Тренажёр ВП' && a.classList.contains('is-active'))));
  await mlp.click('.nav-burger');
  const goButton = mlp.locator('.vp-vrow a.vp-btn').first();
  await goButton.scrollIntoViewIfNeeded();
  const goBox = await goButton.boundingBox();
  check('m.landing_go_button_fits_and_is_tappable', !!goBox && goBox.height >= 44 && goBox.x >= 0 && goBox.x + goBox.width <= 390, goBox);
  await Promise.all([mlp.waitForURL(/\/vp\/vp-[a-z]+\/$/, { timeout: 30000 }), goButton.tap()]);
  check('m.landing_go_button_opens_a_variant', /\/vp\/vp-[a-z]+\/$/.test(mlp.url()), mlp.url());
  await mlp.close();
  await mp.goto(`${BASE}/vp/vp-ui/`, { waitUntil: 'load', timeout: 30000 });
  check('m.intro_no_hscroll', await noHScroll(mp));
  await shot(mp, 'intro_light_phone', true);
  out.attempts.phone = await startAttempt(mp, 'vp-ui');
  check('m.take_no_hscroll', await noHScroll(mp));
  check('m.strip_visible_rail_hidden', await mp.evaluate(() => {
    const strip = document.getElementById('vp-strip');
    const rail = document.querySelector('.vp-rail');
    return getComputedStyle(strip).display !== 'none' && getComputedStyle(rail).display === 'none';
  }));
  const fonts = await mp.$$eval('.vp-input', (els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
  check('m.inputs_16px', fonts.length === 30 && fonts.every((f) => f >= 16), { min: Math.min(...fonts), n: fonts.length });
  const heights = await mp.$$eval('.vp-opt', (els) => els.map((e) => e.getBoundingClientRect().height));
  check('m.options_44px', heights.length > 0 && heights.every((h) => h >= 43.5), { min: Math.min(...heights), n: heights.length });
  check('m.viewport_meta_no_zoom_lock', await mp.evaluate(() => {
    const c = document.querySelector('meta[name=viewport]').getAttribute('content') || '';
    return !/maximum-scale|user-scalable\s*=\s*(no|0)/i.test(c);
  }));
  const barH = await mp.evaluate(() => ({
    bar: Math.round(document.getElementById('vp-bar').getBoundingClientRect().height),
    css: getComputedStyle(document.documentElement).getPropertyValue('--vp-bar-h').trim() }));
  check('m.header_height_reasonable', barH.bar > 0 && barH.bar <= 160 && barH.css === barH.bar + 'px', barH);
  await shot(mp, 'take_light_phone_top');

  // тап по плитке 12 → поле не под шапкой; потом плитка 30 — полоса едет за текущей
  await mp.tap('#vp-strip .vp-cell[data-n="12"]');
  await sleep(1000);
  const vis12 = await visibleBelowBar(mp, '#vp-in-12');
  check('m.tap_cell_focus_not_under_header', vis12.ok, vis12);
  check('m.tap_cell_focus_is_input', (await activeInfo(mp)).id === 'vp-in-12');
  await mp.fill('#vp-in-12', 'слово12');
  await shot(mp, 'take_light_phone_item12');
  // Enter на телефоне: следующее поле тоже не под шапкой
  await mp.keyboard.press('Enter');
  await sleep(700);
  const vis13 = await visibleBelowBar(mp, '#vp-in-13');
  check('m.enter_next_not_under_header', vis13.ok, vis13);
  await mp.tap('#vp-strip .vp-cell[data-n="30"]');
  await sleep(1000);
  check('m.strip_follows_current', await mp.evaluate(() => {
    const strip = document.getElementById('vp-strip');
    const cell = strip.querySelector('.vp-cell[data-n="30"]').getBoundingClientRect();
    const box = strip.getBoundingClientRect();
    return cell.left >= box.left - 1 && cell.right <= box.right + 1;
  }));
  await mp.evaluate(() => window.scrollTo(0, 0));
  await mp.fill('#vp-in-1', 'абум');
  await mp.tap('#vp-submit');
  await sleep(300);
  check('m.dialog_fits', await mp.evaluate(() => {
    const r = document.getElementById('vp-dialog').getBoundingClientRect();
    return document.getElementById('vp-dialog').open && r.left >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight;
  }));
  await shot(mp, 'dialog_light_phone');
  await mp.tap('#vp-back');
  await setTheme(mp, true);
  await mp.evaluate(() => window.scrollTo(0, 0));
  await shot(mp, 'take_dark_phone_top');
  await contrastBothThemes(mp, 'm.take', TAKE_SELECTORS);
  await mp.tap('#vp-submit');
  await Promise.all([mp.waitForURL(/\/vp\/r\//, { timeout: 30000 }), mp.tap('#vp-confirm')]);
  check('m.result_no_hscroll', await noHScroll(mp));
  await shot(mp, 'result_light_phone', true);
  await phone.close();

  // ================================================== ИНВАРИАНТ: 12 полей → 12 строк
  const inv = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const ip = await inv.newPage();
  out.attempts.invariant = await startAttempt(ip, 'vp-ui');
  await ip.focus('#vp-in-1');
  for (let i = 1; i <= 12; i++) { await ip.keyboard.type('поле' + i); await ip.keyboard.press('Enter'); }
  let saved = false;
  for (let k = 0; k < 40 && !saved; k++) {
    await sleep(500);
    saved = (await ip.textContent('#vp-save-state')).trim() === 'сохранено';
  }
  check('i.twelve_saved_indicator', saved, await ip.textContent('#vp-save-state'));
  await inv.close();

  // ============================================================= СОСТОЯНИЯ ТАЙМЕРА
  const tctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const tp = await tctx.newPage();
  out.attempts.warn = await startAttempt(tp, 'vp-warn');
  const warn = await tp.evaluate(() => ({
    clock: document.getElementById('vp-clock').className,
    banner: document.getElementById('vp-banner').textContent,
    hidden: document.getElementById('vp-banner').hidden,
    cap: document.getElementById('vp-timer-cap').textContent }));
  check('t.warn_state', /is-warn/.test(warn.clock) && !/is-danger/.test(warn.clock) && !warn.hidden
    && warn.cap === 'осталось пять минут', warn);
  check('t.warn_banner_lists_missed', /Осталось пять минут\. Не отвечено 44 задания: 1, 2, 3/.test(warn.banner), warn.banner);
  await tp.fill('#vp-in-1', 'абум');
  const banner2 = await tp.textContent('#vp-banner');
  check('t.warn_banner_updates_on_answer', /Не отвечено 43 задания: 2, 3/.test(banner2), banner2);
  await shot(tp, 'take_warn_desktop');
  await setTheme(tp, true);
  await shot(tp, 'take_warn_dark_desktop');
  const warnDark = lowContrast(await contrastOf(tp, ['.vp-banner', '.vp-timer', '.vp-timer-cap']));
  await setTheme(tp, false);
  const warnLight = lowContrast(await contrastOf(tp, ['.vp-banner', '.vp-timer', '.vp-timer-cap']));
  check('t.warn_contrast_both_themes', warnDark.length === 0 && warnLight.length === 0, { warnLight, warnDark });

  // офлайн: индикатор честный, после возврата связи ответ доезжает
  await tctx.setOffline(true);
  await tp.fill('#vp-in-2', 'офлайн');
  await sleep(600);
  const offState = await tp.evaluate(() => ({ cls: document.getElementById('vp-save-state').className,
    text: document.getElementById('vp-save-state').textContent }));
  check('t.offline_indicator', /is-offline/.test(offState.cls) && /нет связи/.test(offState.text), offState);
  await tctx.setOffline(false);
  let back = false;
  for (let k = 0; k < 60 && !back; k++) {
    await sleep(500);
    back = (await tp.textContent('#vp-save-state')).trim() === 'сохранено';
  }
  check('t.online_saved', back, await tp.textContent('#vp-save-state'));
  await tctx.close();

  const dctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const dp = await dctx.newPage();
  out.attempts.danger = await startAttempt(dp, 'vp-danger');
  const danger = await dp.evaluate(() => ({
    clock: document.getElementById('vp-clock').className,
    banner: document.getElementById('vp-banner').textContent,
    cap: document.getElementById('vp-timer-cap').textContent }));
  check('t.danger_state', /is-danger/.test(danger.clock) && /Работа сдастся сама/.test(danger.banner)
    && danger.cap === 'последняя минута', danger);
  await shot(dp, 'take_danger_desktop');
  await setTheme(dp, true);
  await shot(dp, 'take_danger_dark_desktop');
  const dangerDark = lowContrast(await contrastOf(dp, ['.vp-banner', '.vp-timer', '.vp-timer-cap']));
  await setTheme(dp, false);
  const dangerLight = lowContrast(await contrastOf(dp, ['.vp-banner', '.vp-timer', '.vp-timer-cap']));
  check('t.danger_contrast_both_themes', dangerDark.length === 0 && dangerLight.length === 0, { dangerLight, dangerDark });
  await dctx.close();

  // ============================================= ВРЕМЯ ВЫШЛО: сдалось само, введённое засчитано
  const fctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const fp = await fctx.newPage();
  out.attempts.fast = await startAttempt(fp, 'vp-fast');
  await fp.fill('#vp-in-1', 'абум');
  let redirected = false;
  try {
    await fp.waitForURL(/\/vp\/r\//, { timeout: 30000 });
    redirected = true;
  } catch (e) { /* остаёмся на странице — проверка ниже покраснеет */ }
  check('t.timeup_redirects_to_result', redirected, fp.url());
  if (redirected) {
    const text = await fp.textContent('body');
    check('t.timeup_result_says_auto', /сдано по истечении времени/.test(text) && /00:10 из 00:10/.test(text),
      (text.match(/[^.]*по истечении[^.]*/) || [''])[0]);
    await shot(fp, 'result_timeup_desktop', true);
  }
  await fctx.close();
} catch (e) {
  out.error = String(e && e.stack ? e.stack : e);
}

await browser.close();
console.log('###VP-JSON###' + JSON.stringify(out));
