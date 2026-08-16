/**
 * Личная статистика после ревью 16.08 (фазы 4–5) — проверка ИСПОЛНЕНИЕМ.
 *
 * ⚠️ Питон-тесты видят исходники, но не видят нарисованного: подпись шкалы
 * радара, попавшая под линию, — не ошибка ни для одного из них. Здесь
 * браузер считает координаты и цвета так, как их посчитал Chart.js.
 *
 * Запуск: node scripts/r16_stats_probe.js [порт] [логин]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8211';
const WHO = process.argv[3] || 'student1@test.local';
const BASE = `http://127.0.0.1:${PORT}`;

let passed = 0;
const failures = [];

function check(name, ok, extra) {
  if (ok) { passed += 1; return; }
  failures.push(name + (extra ? ' — ' + extra : ''));
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', WHO);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  const res = await page.goto(`${BASE}/profile/stats/`, { waitUntil: 'networkidle' });
  check('страница статистики отвечает 200', res.status() === 200, String(res.status()));

  // ── Фаза 4: сетка активности ────────────────────────────────────────
  const grid = await page.evaluate(() => ({
    cells: document.querySelectorAll('.act-day').length,
    numbers: [...document.querySelectorAll('.act-grid--days .act-day')]
      .slice(0, 7).map((n) => n.textContent.trim()),
    legend: (document.querySelector('.act-legend') || {}).innerText,
    facts: [...document.querySelectorAll('.act-fact')].length,
    today: document.querySelectorAll('.act-day.is-today').length,
    hint: (document.getElementById('time-hint') || {}).textContent || '',
  }));
  check('сетка нарисована', grid.cells > 20, String(grid.cells));
  check('в клетке стоит число месяца',
        grid.numbers.every((t) => /^\d+$/.test(t)), grid.numbers.join(','));
  check('легенда меряет минуты', /минут в день/.test(grid.legend || ''), grid.legend);
  check('легенда без «меньше — больше»', !/Меньше|Больше/.test(grid.legend || ''));
  check('четыре факта справа', grid.facts === 4, String(grid.facts));
  check('сегодня отмечен один раз', grid.today === 1, String(grid.today));
  check('подпись про минуты', /минут/.test(grid.hint) && !/верных/.test(grid.hint),
        grid.hint.trim());

  // Итог в сетке и карточка «Минут на сайте» обязаны совпасть.
  const totals = await page.evaluate(() => {
    const fact = document.querySelectorAll('.act-fact')[1];
    const card = [...document.querySelectorAll('*')]
      .filter((n) => !n.children.length && /^\d+ мин$/.test(n.textContent.trim()))
      .map((n) => n.textContent.trim());
    return { fact: fact ? fact.querySelector('.act-fact__v').textContent.trim() : null,
             card: card[0] || null };
  });
  check('итог сетки равен карточке минут', totals.fact === totals.card,
        `сетка ${totals.fact} карточка ${totals.card}`);

  // ── Фаза 5: карточки ────────────────────────────────────────────────
  const cards = await page.evaluate(() => {
    const titles = [...document.querySelectorAll('.panel-title')]
      .map((n) => n.innerText.trim());
    return {
      titles,
      hasRing: !!document.getElementById('chart-ring'),
      hasDifficulty: !!document.getElementById('chart-difficulty'),
      logo: !!document.querySelector('.rush-logo .rush'),
      counterColour: null,
    };
  });
  check('«Динамика уровня»', cards.titles.some((t) => /Динамика уровня/.test(t)));
  check('«Ответы за период» убраны',
        !cards.titles.some((t) => /Ответы за период/.test(t)));
  check('кольцо не рисуется', !cards.hasRing);
  check('«Где решаешь»', cards.titles.some((t) => /Где решаешь/.test(t)));
  check('«По сложности»', cards.titles.some((t) => /По сложности/.test(t)));
  check('логотип игры на месте', cards.logo);

  // Радар: подписи шкалы не должны лежать на вертикальной оси.
  const radar = await page.evaluate(() => {
    const el = document.getElementById('chart-radar');
    if (!el || !window.Chart) { return null; }
    const chart = Chart.getChart(el);
    if (!chart) { return null; }
    const scale = chart.scales.r;
    const count = (chart.data.labels || []).length || 1;
    const angle = Math.PI / count;
    const radius = scale.getDistanceFromCenterForValue(80);
    return {
      builtin: scale.options.ticks.display,
      centerX: scale.xCenter,
      labelX: scale.xCenter + radius * Math.sin(angle),
      labelY: scale.yCenter - radius * Math.cos(angle),
      topY: scale.yCenter - radius,
    };
  });
  if (radar) {
    check('встроенные подписи шкалы выключены', radar.builtin === false);
    check('подпись шкалы ушла с вертикальной оси',
          Math.abs(radar.labelX - radar.centerX) > 10,
          `сдвиг ${(radar.labelX - radar.centerX).toFixed(1)} px`);
  } else {
    check('радар нарисован', false, 'графика нет');
  }

  // Розовая пара: в обеих карточках оба тона — акцент, зелёного нет.
  const colours = await page.evaluate(() => {
    const accent = getComputedStyle(document.documentElement)
      .getPropertyValue('--accent').trim().toLowerCase();
    const out = {};
    ['chart-difficulty', 'chart-sources'].forEach((id) => {
      const el = document.getElementById(id);
      const chart = el && window.Chart ? Chart.getChart(el) : null;
      out[id] = chart
        ? chart.data.datasets.map((d) => String(d.backgroundColor).toLowerCase())
        : null;
    });
    out.accent = accent;
    return out;
  });
  ['chart-difficulty', 'chart-sources'].forEach((id) => {
    const list = colours[id];
    if (!list) { check(`${id}: график есть`, false); return; }
    check(`${id}: оба тона — акцент`,
          list.every((c) => c.startsWith(colours.accent)), list.join(' '));
  });

  // Красный кружок счётчика — на экране занятия у репетитора.
  await page.goto(`${BASE}/logout/`, { waitUntil: 'domcontentloaded' }).catch(() => {});
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  await page.goto(`${BASE}/teacher/groups/2/`, { waitUntil: 'domcontentloaded' });
  const badge = await page.evaluate(() => {
    const el = document.querySelector('.k-count');
    if (!el) { return null; }
    const style = getComputedStyle(el);
    return { bg: style.backgroundColor, colour: style.color,
             text: el.textContent.trim() };
  });
  if (badge) {
    check('кружок счётчика красный', /rgb\(192, 57, 43\)/.test(badge.bg), badge.bg);
    check('кружок не пустой', badge.text.length > 0, badge.text);
  } else {
    console.log('  (кружка нет — непроверенных работ не осталось, это не ошибка)');
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
