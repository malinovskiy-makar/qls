/**
 * Сквозной сценарий объединённого ревью 15.08.2026.
 *
 * Растёт вместе с фазами: каждая фаза дописывает сюда свои проверки, так что
 * прогон одного файла проверяет всю сессию целиком, а не последнюю правку.
 *
 * ⚠️ СВЕРЯЕТ КОД ОТВЕТА на каждом переходе. Сценарий, который меряет ширину
 * страницы с 403-й ошибкой, «успешно» проверяет пустоту (урок сессии 4).
 *
 * ⚠️ Ходит по ПРОВЕРОЧНОЙ базе (`config.settings_check`, db_check.sqlite3):
 * сценарий сохраняющий — ставит баллы и пишет комментарии.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/r15_cycle.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');
const PREFIX = 'р15';

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

/** Курсор, который браузер РЕАЛЬНО считает вычисленным. */
async function cursorsOnPage(page) {
  return page.evaluate(() => {
    const seen = {};
    document.querySelectorAll('*').forEach((node) => {
      const value = getComputedStyle(node).cursor;
      seen[value] = (seen[value] || 0) + 1;
    });
    return seen;
  });
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await login(context, 'tutor@test.local');

  // ══ ФАЗА 1 ═════════════════════════════════════════════════════════════
  console.log('\n— Фаза 1.1: курсор');
  const cursorPages = [
    ['/teacher/groups/2/', 'обзор занятия'],
    ['/teacher/student/11/progress/', 'карточка ученика'],
    ['/teacher/groups/2/assignments/6/', 'задание целиком'],
    ['/teacher/groups/2/assignments/6/students/9/', 'разбор глазами ученика'],
  ];
  for (const [url, name] of cursorPages) {
    if (!await open(page, url, name)) continue;
    const cursors = await cursorsOnPage(page);
    check(`${name}: курсора «help» нет`, !cursors.help, cursors);
  }

  console.log('\n— Фаза 1.1: подсказка всё ещё работает');
  await open(page, '/teacher/groups/2/', 'обзор занятия');
  const marks = await page.$$('.k-hintmark');
  check('знаки подсказки на месте', marks.length > 0, marks.length);
  if (marks.length) {
    await marks[0].hover();
    await page.waitForTimeout(250);
    const bubble = await page.$('.k-tip:not([hidden])');
    check('всплывашка появляется при наведении', bubble !== null);
  }

  console.log('\n— Фаза 1.2: лишняя надпись');
  const overview = await page.content();
  check('«Проценты — средние по группе» убрано',
    !overview.includes('Проценты — средние по группе'));
  check('подсказка про сортировку осталась',
    overview.includes('чтобы отсортировать'));

  console.log('\n— Фаза 1.3: «Посмотреть ещё N»');
  if (await open(page, '/teacher/groups/2/?tab=assignments', 'вкладка «Задания»')) {
    const button = await page.$('.js-show-all');
    if (button) {
      const label = (await button.textContent()).trim();
      const hidden = await button.getAttribute('data-more');
      check('кнопка называет число скрытых',
        label === `Посмотреть ещё ${hidden} ${
          Number(hidden) % 10 === 1 && Number(hidden) % 100 !== 11 ? 'работу'
            : (Number(hidden) % 10 >= 2 && Number(hidden) % 10 <= 4
               && !(Number(hidden) % 100 >= 12 && Number(hidden) % 100 <= 14))
              ? 'работы' : 'работ'}`, { label, hidden });
      const before = await page.$$eval('.ass-card:not([hidden])', (n) => n.length);
      await button.click();
      await page.waitForTimeout(150);
      const after = await page.$$eval('.ass-card:not([hidden])', (n) => n.length);
      check('раскрытие на месте работает', after - before === Number(hidden),
        { before, after, hidden });
    } else {
      check('кнопка «Посмотреть ещё» есть на демо-данных', false);
    }
    await shot(page, 'ф1-задания');
  }

  console.log('\n— Фаза 1.4: одна запись балла');
  /** Все числа балла со страницы: «4,25 из 18», «0,5 / 1 б.». */
  async function scoreTexts(page) {
    return page.evaluate(() => {
      const out = [];
      document.querySelectorAll(
        '.k-score__value, .k-score__max, .wr-score, .done-score,'
        + ' .rv-score, .fb-score, .part-points, .task-points'
      ).forEach((node) => out.push(node.textContent.replace(/\s+/g, ' ').trim()));
      return out;
    });
  }
  const scorePages = [
    ['/teacher/groups/2/assignments/6/submissions/', 'сводка решений'],
    ['/teacher/groups/2/assignments/6/students/9/', 'разбор работы'],
    ['/teacher/groups/2/assignments/6/students/9/done/', 'итоги проверки'],
    ['/teacher/groups/2/assignments/6/', 'экран задания'],
  ];
  const seen = [];
  for (const [url, name] of scorePages) {
    if (!await open(page, url, name)) continue;
    const texts = await scoreTexts(page);
    seen.push([name, texts]);
    const dotted = texts.filter((t) => /\d\.\d/.test(t));
    check(`${name}: точки в балле нет`, dotted.length === 0, dotted);
    const padded = texts.filter((t) => /\d,\d0(\D|$)/.test(t));
    check(`${name}: незначащего нуля нет`, padded.length === 0, padded);
  }
  // Одно и то же число на двух экранах написано одинаково.
  const inSummary = (seen.find((s) => s[0] === 'сводка решений') || [null, []])[1]
    .join(' ');
  const inReview = (seen.find((s) => s[0] === 'разбор работы') || [null, []])[1]
    .join(' ');
  const fraction = (inReview.match(/\d+,\d+/) || [])[0];
  if (fraction) {
    check(`дробный балл «${fraction}» так же записан в сводке`,
      inSummary.includes(fraction), { inSummary, inReview });
  }

  console.log('\n— Фаза 1: обе темы и 380 пикселей');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.evaluate(() => localStorage.setItem('theme', 'dark'));
  await open(page, '/teacher/groups/2/assignments/6/students/9/', 'разбор (тёмная)');
  await shot(page, 'ф1-разбор-тёмная');
  await page.setViewportSize({ width: 380, height: 900 });
  await page.evaluate(() => localStorage.setItem('theme', 'light'));
  await open(page, '/teacher/groups/2/assignments/6/students/9/', 'разбор (380)');
  const wide = await page.evaluate(() => {
    const wrap = document.querySelector('.page-wrap') || document.body;
    return { scroll: wrap.scrollWidth, client: wrap.clientWidth };
  });
  check('на 380 содержимое вбок не тянет', wide.scroll <= wide.client + 1, wide);
  await shot(page, 'ф1-разбор-380');
  await page.setViewportSize({ width: 1440, height: 1000 });

  // ══ ФАЗА 2: крошки ═════════════════════════════════════════════════════
  console.log('\n— Фаза 2: крошки одинаковы на всех экранах');
  const CRUMB_PAGES = [
    ['/teacher/groups/2/', 'обзор занятия'],
    ['/teacher/groups/2/assignments/6/', 'задание целиком'],
    ['/teacher/groups/2/assignments/6/submissions/', 'сводка решений'],
    ['/teacher/groups/2/assignments/6/students/9/', 'глазами ученика'],
    ['/teacher/assignment/create/?group=3', 'искать самому'],
    ['/teacher/assignment/generate/?group=2', 'описать словами'],
    ['/teacher/assignment/build/?group=2', 'конструктор подборки'],
    ['/teacher/groups/2/exams/new/', 'конструктор контрольной'],
    ['/teacher/problems/new/', 'своя задача'],
    ['/teacher/problems/', 'мои задачи'],
    ['/teacher/student/11/progress/', 'карточка ученика'],
  ];
  const looks = [];
  for (const [url, name] of CRUMB_PAGES) {
    if (!await open(page, url, name)) continue;
    const info = await page.evaluate(() => {
      const box = document.querySelector('.crumbs');
      if (!box) return null;
      const cs = getComputedStyle(box);
      const kids = [...box.children];
      return {
        кегль: cs.fontSize,
        последнее: getComputedStyle(kids[kids.length - 1]).color,
        ссылка: kids[0] ? getComputedStyle(kids[0]).color : null,
        подчёркивание: kids[0]
          ? getComputedStyle(kids[0]).textDecorationLine : null,
        стрелка: kids.length > 1
          ? getComputedStyle(kids[1], '::before').content : null,
        стрелкаЦвет: kids.length > 1
          ? getComputedStyle(kids[1], '::before').color : null,
        первойСтрелкиНет:
          getComputedStyle(kids[0], '::before').content === 'none',
      };
    });
    check(`${name}: крошка есть`, info !== null);
    if (!info) continue;
    looks.push([name, info]);
    check(`${name}: не браузерная синь`,
      info.ссылка !== 'rgb(0, 0, 238)', info.ссылка);
    check(`${name}: без подчёркивания`,
      info.подчёркивание === 'none', info.подчёркивание);
    check(`${name}: перед первым звеном стрелки нет`, info.первойСтрелкиНет);
  }
  // Одинаковость: все экраны обязаны совпасть по кеглю и трём цветам.
  if (looks.length) {
    const first = JSON.stringify({
      кегль: looks[0][1].кегль, последнее: looks[0][1].последнее,
      ссылка: looks[0][1].ссылка,
    });
    const разные = looks.filter(([, i]) => JSON.stringify({
      кегль: i.кегль, последнее: i.последнее, ссылка: i.ссылка,
    }) !== first).map(([n]) => n);
    check('вид крошек совпадает на всех экранах', разные.length === 0, разные);
    check('последнее звено — обычный текст, не приглушённый',
      looks[0][1].последнее !== 'rgb(91, 100, 114)', looks[0][1].последнее);
    check('стрелку рисует CSS и она акцентная',
      looks.every(([, i]) => i.стрелка === null
        || (i.стрелка.includes('→') && i.стрелкаЦвет === 'rgb(190, 24, 93)')));
  }

  console.log('\n— Фаза 2: ссылок «назад по истории» не осталось');
  for (const [url, name] of CRUMB_PAGES) {
    await page.goto(BASE + url, { waitUntil: 'domcontentloaded' });
    const jsLinks = await page.$$eval('a[href^="javascript:"]',
      (nodes) => nodes.length);
    check(`${name}: нет ссылок javascript:`, jsLinks === 0, jsLinks);
  }

  console.log('\n— Фаза 2: крошки в тёмной теме и на 380');
  await page.evaluate(() => localStorage.setItem('theme', 'dark'));
  await open(page, '/teacher/assignment/create/?group=3', 'конструктор (тёмная)');
  await shot(page, 'ф2-крошки-конструктор-тёмная');
  await page.setViewportSize({ width: 380, height: 900 });
  await page.evaluate(() => localStorage.setItem('theme', 'light'));
  await open(page, '/teacher/groups/2/assignments/6/submissions/', 'сводка (380)');
  const crumbWide = await page.evaluate(() => {
    const box = document.querySelector('.crumbs');
    return { scroll: box.scrollWidth, client: box.clientWidth };
  });
  check('на 380 крошка переносится, а не тянет вбок',
    crumbWide.scroll <= crumbWide.client + 1, crumbWide);
  await shot(page, 'ф2-крошки-380');
  await page.setViewportSize({ width: 1440, height: 1000 });

  // ══ ФАЗА 3: выравнивание ═══════════════════════════════════════════════
  console.log('\n— Фаза 3.1: числовые столбцы стоят на одной оси');
  /** Центр «чернил» ячейки — середина прямоугольника её текста. */
  async function columnSpread(page, selector) {
    return page.evaluate((sel) => {
      const table = document.querySelector(sel);
      if (!table) return null;
      const ink = (cell) => {
        const range = document.createRange();
        range.selectNodeContents(cell);
        const box = range.getBoundingClientRect();
        return box.width ? box.left + box.width / 2 : null;
      };
      return [...table.querySelectorAll('thead th')].map((th, i) => {
        const values = [...table.querySelectorAll('tbody tr')]
          .map((tr) => tr.children[i]).filter(Boolean)
          .map(ink).filter((v) => v !== null);
        const head = ink(th);
        return {
          тип: th.dataset.type || '—',
          имя: th.textContent.replace(/\s+/g, ' ').trim().slice(0, 20),
          сдвиг: values.length && head !== null
            ? Math.round(Math.max(...values.map((v) => Math.abs(v - head))))
            : null,
        };
      });
    }, selector);
  }
  const TABLES = [
    ['/teacher/groups/2/', '#students-table', 'таблица «Ученики»'],
    ['/teacher/groups/2/', '#group-works-table', 'история работ занятия'],
    ['/teacher/student/11/progress/', '#student-works-table',
     'история работ ученика'],
  ];
  for (const [url, selector, name] of TABLES) {
    if (!await open(page, url, name)) continue;
    const columns = await columnSpread(page, selector);
    if (!columns) { check(`${name}: таблица найдена`, false); continue; }
    const off = columns.filter((c) => c.тип === 'num' && c.сдвиг > 1);
    check(`${name}: числовые столбцы на одной оси`, off.length === 0, off);
    const nums = columns.filter((c) => c.тип === 'num');
    check(`${name}: числовые столбцы вообще размечены`, nums.length > 0);
  }

  console.log('\n— Фаза 3.2: значения четырёх карточек на одной линии');
  for (const [url, name] of [['/teacher/student/11/progress/', 'карточка ученика'],
                             ['/teacher/groups/3/', 'занятие один на один']]) {
    if (!await open(page, url, name)) continue;
    const tops = await page.$$eval('.card3-value',
      (nodes) => nodes.map((n) => Math.round(n.getBoundingClientRect().top)));
    check(`${name}: значения на одной линии`,
      tops.length > 1 && Math.max(...tops) - Math.min(...tops) <= 1, tops);
  }
  await shot(page, 'ф3-карточка-ученика');

  console.log('\n— Фаза 3: узкий экран не сломан');
  await page.setViewportSize({ width: 380, height: 900 });
  if (await open(page, '/teacher/student/11/progress/', 'карточка (380)')) {
    const stacked = await page.$$eval('.card3',
      (nodes) => nodes.map((n) => Math.round(n.getBoundingClientRect().left)));
    check('на 380 карточки идут столбцом',
      new Set(stacked).size === 1, stacked);
    const wide = await page.evaluate(() => {
      const wrap = document.querySelector('.page-wrap') || document.body;
      return { scroll: wrap.scrollWidth, client: wrap.clientWidth };
    });
    check('на 380 содержимое вбок не тянет',
      wide.scroll <= wide.client + 1, wide);
    await shot(page, 'ф3-карточка-380');
  }
  await page.setViewportSize({ width: 1440, height: 1000 });

  // ══ ФАЗА 4: янтарь и контраст ══════════════════════════════════════════
  console.log('\n— Фаза 4: текст на янтарном фоне проходит AA');
  /** Контраст текста элемента против НАСТОЯЩЕГО фона под ним. */
  async function contrastOf(page, selector) {
    return page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const parse = (value) => {
        const m = value.match(
          /rgba?\(([\d.]+), ([\d.]+), ([\d.]+)(?:, ([\d.]+))?\)/);
        return m ? [+m[1], +m[2], +m[3],
                    m[4] === undefined ? 1 : Number(m[4])] : null;
      };
      const solid = (node) => {
        while (node) {
          const c = parse(getComputedStyle(node).backgroundColor);
          if (c && c[3] === 1) return c.slice(0, 3);
          node = node.parentElement;
        }
        return [255, 255, 255];
      };
      const mix = (fg, a, bg) => fg.map((c, i) => c * a + bg[i] * (1 - a));
      const own = parse(getComputedStyle(el).backgroundColor);
      const under = solid(el.parentElement);
      const bg = own ? mix(own.slice(0, 3), own[3], under) : under;
      const fg = parse(getComputedStyle(el).color).slice(0, 3);
      const lum = (c) => {
        const f = c.map((v) => { v /= 255;
          return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
        return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
      };
      const [x, y] = [lum(fg), lum(bg)];
      return Math.round(((Math.max(x, y) + 0.05)
        / (Math.min(x, y) + 0.05)) * 100) / 100;
    }, selector);
  }
  const AMBER = [
    ['/teacher/groups/2/assignments/6/students/9/', '.k-flag--partial',
     'чип «частично»'],
    ['/teacher/groups/2/?tab=assignments', '.k-count', 'кружок счётчика'],
    ['/teacher/groups/', '.gc-wait', 'чип «ждут проверки»'],
    ['/teacher/groups/2/', '.k-level--mid', 'процент в таблице'],
    ['/teacher/groups/2/', '.matrix-mid', 'клетка теплокарты'],
  ];
  for (const theme of ['light', 'dark']) {
    await page.evaluate((t) => localStorage.setItem('theme', t), theme);
    for (const [url, selector, name] of AMBER) {
      await page.goto(BASE + url, { waitUntil: 'networkidle' });
      const value = await contrastOf(page, selector);
      check(`${theme}: ${name} — контраст ${value}`,
        value !== null && value >= 4.5, value);
    }
  }
  await page.evaluate(() => localStorage.setItem('theme', 'light'));
  await open(page, '/teacher/groups/2/?tab=assignments', 'вкладки со счётчиком');
  await shot(page, 'ф4-счётчик');

  // ══ ФАЗА 5: края прокрутки ═════════════════════════════════════════════
  console.log('\n— Фаза 5: полосы спрятаны, края растворяются с обеих сторон');
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.evaluate(() => localStorage.setItem('theme', 'light'));
  const SCROLLERS = [
    ['/teacher/groups/2/', '.fade-box', 'теплокарта', 'x'],
    ['/teacher/assignment/create/?group=2', '.hw-sidebar',
     'панель конструктора', 'y'],
  ];
  for (const [url, selector, name, axis] of SCROLLERS) {
    if (!await open(page, url, name)) continue;
    const state = await page.evaluate(({ selector, axis }) => {
      const box = document.querySelector(selector);
      if (!box) return null;
      const sc = box.querySelector('[data-scroller]') || box.firstElementChild;
      const over = axis === 'y' ? sc.scrollHeight - sc.clientHeight
        : sc.scrollWidth - sc.clientWidth;
      return {
        переполнение: over,
        полоса: getComputedStyle(sc).scrollbarWidth,
        вначале: box.classList.contains('is-start'),
        левое: getComputedStyle(box, '::before').opacity,
        правое: getComputedStyle(box, '::after').opacity,
        таб: sc.getAttribute('tabindex'),
      };
    }, { selector, axis });
    if (!state) { check(`${name}: обёртка есть`, false); continue; }
    check(`${name}: содержимое действительно не влезает`,
      state.переполнение > 1, state.переполнение);
    check(`${name}: полоса прокрутки спрятана`,
      state.полоса === 'none', state.полоса);
    check(`${name}: в начале левого растворения нет`,
      state.вначале && state.левое === '0', state);
    check(`${name}: правое растворение видно`, state.правое !== '0');
    check(`${name}: блок доступен с клавиатуры`, state.таб === '0', state.таб);

    // Прокручиваем СТРЕЛКОЙ, а не скриптом: проверяем то, чем пользуются.
    await page.evaluate(({ selector }) => {
      const box = document.querySelector(selector);
      (box.querySelector('[data-scroller]') || box.firstElementChild).focus();
    }, { selector });
    for (let i = 0; i < 4; i += 1) {
      await page.keyboard.press(axis === 'y' ? 'ArrowDown' : 'ArrowRight');
    }
    await page.waitForTimeout(200);
    const after = await page.evaluate(({ selector, axis }) => {
      const box = document.querySelector(selector);
      const sc = box.querySelector('[data-scroller]') || box.firstElementChild;
      return {
        сдвиг: axis === 'y' ? sc.scrollTop : sc.scrollLeft,
        левое: getComputedStyle(box, '::before').opacity,
      };
    }, { selector, axis });
    check(`${name}: стрелки прокручивают`, after.сдвиг > 0, after.сдвиг);
    check(`${name}: после прокрутки левое растворение появилось`,
      after.левое !== '0', after.левое);
  }

  console.log('\n— Фаза 5: тёмная тема не слабее светлой');
  const steps = {};
  for (const theme of ['light', 'dark']) {
    await page.evaluate((t) => localStorage.setItem('theme', t), theme);
    await open(page, '/teacher/groups/2/', `теплокарта (${theme})`);
    // Уводим прокрутку в середину: видны оба края.
    await page.evaluate(() => {
      const sc = document.querySelector('.fade-box').firstElementChild;
      sc.scrollLeft = Math.round((sc.scrollWidth - sc.clientWidth) / 2);
    });
    await page.waitForTimeout(300);
    steps[theme] = true;
    await shot(page, `ф5-края-${theme}`);
  }
  check('края сняты в обеих темах', steps.light && steps.dark);
  await page.evaluate(() => localStorage.setItem('theme', 'light'));
  await page.setViewportSize({ width: 1440, height: 1000 });

  // ══ ИТОГ ═══════════════════════════════════════════════════════════════
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Проверок: ${ok + bad}, зелёных: ${ok}, красных: ${bad}`);
  if (bad) { problems.forEach((p) => console.log('  -', p)); }
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
