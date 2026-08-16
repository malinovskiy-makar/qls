/**
 * Таблицы платформы после ревью 16.08 (фаза 6) — ЗАМЕР, а не осмотр.
 *
 * ⚠️ Питон-тест видит атрибут `data-type`, но не видит, совпал ли центр
 * заголовка с центрами значений: это делает браузер. Здесь считаются
 * реальные координаты каждого столбца.
 *
 * Запуск: node scripts/r16_tables_probe.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8211';
const BASE = `http://127.0.0.1:${PORT}`;

let passed = 0;
const failures = [];

function check(name, ok, extra) {
  if (ok) { passed += 1; return; }
  failures.push(name + (extra ? ' — ' + extra : ''));
}

async function login(page, who) {
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', who);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

/** Центры заголовка и всех значений нетекстового столбца. */
async function columnDrift(page) {
  return page.evaluate(() => {
    const out = [];
    // ⚠️ МЕРЯЕМ СОДЕРЖИМОЕ ЦЕЛИКОМ, А НЕ ПЕРВЫЙ ВЛОЖЕННЫЙ УЗЕЛ. Ячейки
    // одного столбца всегда одной ширины — сравнивать их рамки бесполезно,
    // а «первый элемент» у заголовка со знаком вопроса это сам знак, и
    // проверка мерила бы положение значка. `Range` по содержимому даёт
    // настоящий видимый размах текста и чипов.
    const range = document.createRange();
    const centre = (node) => {
      range.selectNodeContents(node);
      let box = range.getBoundingClientRect();
      if (!box.width) { box = node.getBoundingClientRect(); }
      return box.width ? box.left + box.width / 2 : null;
    };
    document.querySelectorAll('table').forEach((table, tableIndex) => {
      const heads = [...table.querySelectorAll('thead th')];
      heads.forEach((head, index) => {
        const type = head.getAttribute('data-type');
        // Текстовые столбцы читаются слева — их и не центрируем.
        if (type !== 'num' && type !== 'date') { return; }
        const headCentre = centre(head);
        if (headCentre === null) { return; }
        let worst = 0;
        [...table.querySelectorAll('tbody tr')].forEach((row) => {
          const cell = row.children[index];
          if (!cell || cell.hasAttribute('colspan')) { return; }
          const value = centre(cell);
          if (value === null) { return; }
          worst = Math.max(worst, Math.abs(value - headCentre));
        });
        out.push({ table: tableIndex, column: head.textContent.trim().slice(0, 20),
                   drift: Math.round(worst) });
      });
    });
    return out;
  });
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));

  await login(page, 'tutor@test.local');

  const screens = [
    ['обзор занятия', '/teacher/groups/2/'],
    ['карточка ученика', '/teacher/student/9/progress/'],
    ['сводка решений', '/teacher/groups/2/assignments/6/submissions/?view=problems'],
    ['мои задачи', '/teacher/problems/'],
  ];
  for (const [name, url] of screens) {
    const res = await page.goto(BASE + url, { waitUntil: 'networkidle' });
    check(`${name}: отвечает 200`, res.status() === 200, String(res.status()));
    if (res.status() !== 200) { continue; }
    const drift = await columnDrift(page);
    const bad = drift.filter((d) => d.drift > 2);
    check(`${name}: центры столбцов совпадают`, bad.length === 0,
          bad.map((d) => `${d.column}=${d.drift}px`).join(', '));
  }

  // Каталог — сторона ученика.
  // ⚠️ Каталог без единого фильтра показывает АТЛАС ТЕМ, а не таблицу
  // (нулевое состояние) — тогда мерить было бы нечего.
  const cat = await page.goto(`${BASE}/catalog/?view=table&difficulty=3`,
                              { waitUntil: 'networkidle' });
  check('каталог: отвечает 200', cat.status() === 200, String(cat.status()));
  const catalogAlign = await page.evaluate(() => {
    const head = document.querySelector('th.col-diff');
    if (!head) { return null; }
    return getComputedStyle(head).textAlign;
  });
  check('каталог: числовой столбец по центру', catalogAlign === 'center',
        String(catalogAlign));

  // 6.2 — таблица учеников выше матрицы.
  await page.goto(`${BASE}/teacher/groups/2/`, { waitUntil: 'networkidle' });
  const order = await page.evaluate(() => {
    const titles = [...document.querySelectorAll('.panel-title')]
      .map((n) => n.textContent.trim());
    return { students: titles.indexOf('Ученики'),
             matrix: titles.indexOf('Ученики × темы') };
  });
  check('«Ученики» выше «Ученики × темы»',
        order.students >= 0 && order.matrix >= 0
        && order.students < order.matrix, JSON.stringify(order));

  // 6.3 — первый столбец матрицы стоит на месте при прокрутке.
  const frozen = await page.evaluate(async () => {
    const name = document.querySelector('td.matrix-name');
    if (!name) { return null; }
    const scroller = name.closest('.stats-table-wrap');
    const before = name.getBoundingClientRect().left;
    scroller.scrollLeft = 240;
    await new Promise((r) => requestAnimationFrame(r));
    const after = name.getBoundingClientRect().left;
    const style = getComputedStyle(name);
    return { before, after, moved: Math.abs(after - before),
             scrolled: scroller.scrollLeft,
             position: style.position, shadow: style.boxShadow,
             background: style.backgroundColor };
  });
  if (frozen) {
    check('матрица действительно прокрутилась', frozen.scrolled > 100,
          String(frozen.scrolled));
    check('имена остались на месте', frozen.moved < 1,
          `сдвиг ${frozen.moved.toFixed(1)} px`);
    check('у закреплённого столбца своя заливка',
          frozen.background !== 'rgba(0, 0, 0, 0)', frozen.background);
    check('у края тень', frozen.shadow !== 'none', frozen.shadow);
  } else {
    check('матрица нарисована', false, 'нет клеток');
  }

  check('ошибок в консоли нет', errors.length === 0, errors.join(' | '));

  await browser.close();
  console.log(`\nПроверок пройдено: ${passed}`);
  if (failures.length) {
    console.log('НЕ ПРОШЛО:');
    failures.forEach((f) => console.log('  ✗ ' + f));
    process.exit(1);
  }
  console.log('Все проверки зелёные.');
})();
