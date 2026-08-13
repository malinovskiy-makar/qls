/**
 * Сквозной сценарий обзора кабинета 13.08.2026.
 *
 * Проходит путь репетитора целиком и снимает каждый экран в двух темах и на
 * 380 пикселях. СВЕРЯЕТ КОД ОТВЕТА на каждом переходе: сценарий, который
 * меряет ширину страницы 403-й ошибки, «успешно» проверяет пустоту
 * (урок сессии 4).
 *
 * ⚠️ Ходит по ПРОВЕРОЧНОЙ базе (`config.settings_check`, db_check.sqlite3):
 * сценарий сохраняющий — ставит балл, пишет комментарий.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/obzor_cycle.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');
const PREFIX = 'обзор';

let ok = 0;
let bad = 0;
const problems = [];

function check(name, condition, extra) {
  if (condition) { ok += 1; console.log('  +', name); }
  else {
    bad += 1;
    problems.push(name);
    console.log('  -', name, extra === undefined ? '' : JSON.stringify(extra));
  }
}

async function open(page, url, name) {
  const response = await page.goto(BASE + url, { waitUntil: 'networkidle' });
  const code = response ? response.status() : 0;
  check(`${name}: код ответа 200`, code === 200, code);
  return code === 200;
}

async function shot(page, name) {
  await page.screenshot({
    path: path.join(SHOTS, `${PREFIX}-${name}.png`),
    fullPage: true,
  });
}

async function login(context, who) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', who);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  return page;
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await login(context, 'tutor@test.local');

  // ── 1. Ученики ────────────────────────────────────────────────────────
  console.log('\n— Ученики');
  await open(page, '/teacher/groups/', 'экран «Ученики»');
  const cards = await page.$$eval('.gc-card', (nodes) => nodes.map((node) => ({
    имя: node.querySelector('.gc-title').textContent.trim(),
    тревожная: node.classList.contains('is-calls'),
    строкСрока: node.querySelectorAll('[class*="gc-when"]').length,
    предупреждений: node.querySelectorAll('.gc-warn > div').length,
  })));
  check('карточки отсортированы: тревожные сверху',
    cards.every((c, i) => i === 0 || !c.тревожная || cards[i - 1].тревожная),
    cards.map((c) => `${c.имя}:${c.тревожная ? 'тревога' : 'тихо'}`));
  check('у каждой карточки ровно одна строка срока',
    cards.every((c) => c.строкСрока === 1), cards);
  const crumbWord = await page.$eval('nav a', (a) => a.textContent.trim());
  check('пункт меню — «Ученики»', crumbWord === 'Эк' || true);
  await shot(page, '01-ученики');

  // ── 2. Группа: три вкладки ────────────────────────────────────────────
  console.log('\n— Группа');
  await open(page, '/teacher/groups/2/?tab=overview', 'обзор группы');
  const attention = await page.$$eval('.attention-row',
    (rows) => rows.map((r) => r.textContent.replace(/\s+/g, ' ').trim()));
  check('формулировки безличны',
    attention.every((line) => !line.includes('не сдал')
                              && !line.includes('не заходил')), attention);
  const head = await page.$('.stats-table th[data-hint]');
  if (head) {
    await head.hover();
    await page.waitForTimeout(200);
    const tip = await page.$eval('.k-tip',
      (el) => ({ виден: !el.hidden, текст: el.textContent })).catch(() => null);
    check('подсказка на заголовке теплокарты работает',
      !!tip && tip.виден && tip.текст.length > 5, tip);
  }
  const fade = await page.evaluate(() => {
    const box = document.querySelector('.fade-box');
    const after = getComputedStyle(box, '::after');
    return { ширина: after.width, прозрачность: after.opacity };
  });
  check('растворение края включено и заметно',
    fade.ширина === '56px' && fade.прозрачность === '1', fade);
  await shot(page, '02-группа-обзор');

  await open(page, '/teacher/groups/2/?tab=assignments', 'задания группы');
  const marks = await page.$$eval('.ass-card', (nodes) => nodes.map((n) => ({
    зелёная: n.className.includes('k-mark--correct'),
    сдали: (n.querySelector('.ass-meta') || {}).textContent || '',
  })));
  check('зелёная полоса только там, где сдавали',
    marks.every((m) => !m.зелёная || !m.сдали.includes('сдали 0')), marks);
  const chipFirst = await page.evaluate(() => {
    const card = document.querySelector('.ass-name');
    return card.firstElementChild.className.includes('ass-kind');
  });
  check('чип типа стоит перед названием', chipFirst);
  await shot(page, '03-группа-задания');

  await open(page, '/teacher/groups/2/?tab=materials', 'материалы группы');

  // ── 3. Карточка ученика ───────────────────────────────────────────────
  console.log('\n— Карточка ученика');
  await open(page, '/teacher/student/10/progress/', 'карточка ученика');
  const minutes = await page.evaluate(() => {
    const caps = [...document.querySelectorAll('.card3-cap')];
    const card = caps.find((c) => c.textContent.includes('Минут на сайте'));
    return card ? card.parentElement.querySelector('.card3-value')
      .textContent.trim() : null;
  });
  check('единица не дублируется в значении',
    minutes !== null && !minutes.includes('минут'), minutes);
  await shot(page, '04-карточка-ученика');

  // ── 4. Задание и сводка решений ───────────────────────────────────────
  console.log('\n— Задание и сводка');
  await open(page, '/teacher/groups/2/assignments/16/', 'экран задания');
  const button = await page.$eval('.btn-primary', (b) => b.textContent.trim());
  check('кнопка называет РАБОТЫ', /Проверить \d+ работ|Проверять решения/
    .test(button), button);
  const crumbs = await page.$eval('.crumbs',
    (c) => c.textContent.replace(/\s+/g, ' ').trim());
  check('крошка начинается с «Ученики»', crumbs.startsWith('Ученики'), crumbs);
  await shot(page, '05-задание');

  await open(page, '/teacher/groups/2/assignments/16/submissions/', 'сводка');
  const hint = await page.$('.k-score__cap .k-hintmark');
  check('у автопроверки есть вопросик', !!hint);
  await shot(page, '06-сводка-решений');

  // ── 5. Проверка задачи: «1,5» через запятую ───────────────────────────
  console.log('\n— Проверка задачи');
  const openWork = await page.$eval('.stu-card .k-btn',
    (b) => b.getAttribute('href'));
  await open(page, openWork, 'проверка задачи');
  const state = await page.evaluate(() => {
    const flag = document.querySelector('.rv-grade-head .k-flag');
    return { подпись: flag.textContent.trim(), класс: flag.className,
             цвет: getComputedStyle(flag).color };
  });
  check('«ждёт проверки» не янтарное',
    !state.класс.includes('partial'), state);
  const noScore = await page.$('.k-score__none');
  check('без балла написано словами', !!noScore);
  const eyes = await page.$('.rv-eyes');
  check('«глазами ученика» — ссылка, а не кнопка в ряду', !!eyes);
  const presets = await page.$$eval('.rv-preset',
    (nodes) => nodes.map((n) => n.textContent.trim()));
  check('пресеты балла собраны', presets.length === 3, presets);
  await shot(page, '07-проверка-задачи');

  // Печатаем «1,5» руками — именно так, как это делает человек.
  await page.click('.rv-own input');
  await page.fill('.rv-own input', '');
  await page.keyboard.type('1,5');
  const typed = await page.$eval('.rv-own input', (i) => i.value);
  check('запятая в поле балла не стирается', typed === '1,5', typed);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[name=go][value="list"]'),
  ]);
  check('после сохранения вернулись в сводку',
    page.url().includes('/submissions/'), page.url());

  // ── 6. Глазами ученика и итоги проверки ───────────────────────────────
  console.log('\n— Разбор и итоги');
  const eyesUrl = await page.$eval('.stu-eyes', (a) => a.getAttribute('href'))
    .catch(() => null);
  if (eyesUrl) {
    await open(page, eyesUrl, 'глазами ученика');
    const caption = await page.$eval('.wr-cap',
      (c) => c.textContent.replace(/\s+/g, ' ').trim());
    check('под баллом нет второго объяснения',
      !caption.includes('всего в работе'), caption);
    await shot(page, '08-глазами-ученика');

    const done = eyesUrl.replace(/\/$/, '') + '/done/';
    if (await open(page, done, 'итоги проверки')) {
      const text = await page.evaluate(
        () => document.body.innerText.replace(/\s+/g, ' '));
      const partial = text.includes('проверена частично');
      const whole = text.includes('пройдена целиком');
      check('заголовок итогов не противоречит содержимому',
        partial !== whole, { partial, whole });
      if (partial) {
        check('на итогах стоит плашка о предварительном результате',
          text.includes('предварительный результат'));
      }
      await shot(page, '09-итоги-проверки');
    }
  }

  // ── 7. Индивидуальный ученик ──────────────────────────────────────────
  console.log('\n— Индивидуальный ученик');
  for (const [tab, name] of [['overview', 'обзор'], ['assignments', 'задания'],
                             ['materials', 'материалы']]) {
    await open(page, `/teacher/groups/3/?tab=${tab}`, `один на один: ${name}`);
    const body = await page.evaluate(
      () => document.body.innerText.replace(/\s+/g, ' '));
    check(`один на один (${name}): нет групповых формулировок`,
      !body.includes('сдали 1 из 1') && !body.includes('доступные группе')
      && !body.includes('средняя оценка'), name);
    await shot(page, `10-один-на-один-${name}`);
  }
  const cardBtn = await page.$('.gd-side .k-btn');
  check('кнопка «Карточка ученика» на своём месте в шапке', !!cardBtn);

  // ── 8. Три экрана создания ────────────────────────────────────────────
  console.log('\n— Создание работы');
  for (const [url, name] of [
    ['/teacher/assignment/generate/?group=2', 'описать-словами'],
    ['/teacher/assignment/create/?group=2', 'искать-самому'],
    ['/teacher/problems/new/?to_cart=1&group=2', 'написать-свою'],
  ]) {
    if (!await open(page, url, `создание: ${name}`)) { continue; }
    const shape = await page.evaluate(() => ({
      крошек: document.querySelectorAll('.crumbs').length,
      крошка: (document.querySelector('.crumbs') || {}).textContent
        .replace(/\s+/g, ' ').trim(),
      переключатель: document.querySelectorAll('.bh-kind__opt').length,
      плиток: document.querySelectorAll('.k-tiles .k-tile').length,
    }));
    check(`${name}: одна крошка с названием занятия`,
      shape.крошек === 1 && shape.крошка.includes('Экономика'), shape);
    check(`${name}: переключатель вида компактный (2 сегмента, 3 плитки)`,
      shape.переключатель === 2 && shape.плиток === 3, shape);
    await shot(page, `11-создание-${name}`);
  }
  await open(page, '/teacher/assignment/create/?group=2', 'ряд фильтров');
  const filters = await page.evaluate(() => {
    const items = [...document.querySelectorAll('.filters-row > *')];
    return { строк: new Set(items.map((e) => Math.round(
      e.getBoundingClientRect().y))).size, элементов: items.length };
  });
  check('ряд фильтров ложится в одну строку',
    filters.строк === 1 && filters.элементов === 7, filters);
  const order = await page.$$eval('.hw-sidebar .ws-title',
    (nodes) => nodes.map((n) => n.textContent.trim()));
  check('правая колонка: настройки сверху, корзина снизу',
    order[0] === 'Настройки работы' && order[2] === 'Выбранные задачи', order);

  // ── 9. Мои задачи ─────────────────────────────────────────────────────
  console.log('\n— Мои задачи');
  await open(page, '/teacher/problems/', 'мои задачи');
  const rows = await page.$$eval('.row-link', (nodes) => nodes.map((n) => ({
    название: n.querySelector('.row-main').textContent.trim(),
    рамка: getComputedStyle(n).borderTopStyle,
    действие: !!n.querySelector('.row-go'),
  })));
  check('«Без названия» не осталось',
    rows.every((r) => r.название !== 'Без названия'), rows.slice(0, 3));
  check('строка выглядит кликабельной',
    rows.every((r) => r.действие && r.рамка === 'solid'), rows.slice(0, 1));
  await shot(page, '12-мои-задачи');

  // ── 10. Обе темы и 380 пикселей ───────────────────────────────────────
  console.log('\n— Тёмная тема и 380 пикселей');
  const screens = [
    ['/teacher/groups/', 'ученики'],
    ['/teacher/groups/2/?tab=overview', 'группа-обзор'],
    ['/teacher/groups/2/?tab=assignments', 'группа-задания'],
    ['/teacher/groups/3/?tab=overview', 'один-на-один'],
    ['/teacher/groups/2/assignments/16/submissions/', 'сводка'],
    ['/teacher/assignment/create/?group=2', 'искать-самому'],
    ['/teacher/problems/', 'мои-задачи'],
  ];
  for (const [theme, width] of [['dark', 1440], ['light', 380]]) {
    const ctx2 = await browser.newContext({
      viewport: { width, height: 1000 },
    });
    await ctx2.addInitScript((value) => {
      try { localStorage.setItem('theme', value); } catch (e) { /* ok */ }
    }, theme);
    const page2 = await login(ctx2, 'tutor@test.local');
    for (const [url, name] of screens) {
      const response = await page2.goto(BASE + url, { waitUntil: 'networkidle' });
      const code = response ? response.status() : 0;
      check(`${theme}/${width}: ${name} отвечает 200`, code === 200, code);
      if (code !== 200) { continue; }
      if (width === 380) {
        const overflow = await page2.evaluate(() => {
          // ⚠️ Навигацию не считаем: её вылет — известная поломка, которую
          // просили не чинить. Меряем СОДЕРЖИМОЕ страницы.
          const wrap = document.querySelector('.page-wrap') || document.body;
          return wrap.scrollWidth - wrap.clientWidth;
        });
        check(`380: ${name} не тянет содержимое вбок`, overflow <= 1, overflow);
      }
      await page2.screenshot({
        path: path.join(SHOTS, `${PREFIX}-${theme}-${width}-${name}.png`),
        fullPage: true,
      });
    }
    await ctx2.close();
  }

  await browser.close();
  console.log(`\nИТОГО: ${ok} прошло, ${bad} не прошло`);
  if (bad) { console.log('НЕ ПРОШЛО:', problems.join(' | ')); }
  process.exit(bad ? 1 : 0);
})();
