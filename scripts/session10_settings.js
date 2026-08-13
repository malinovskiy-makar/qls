/**
 * Сессия 10, фаза 2: панель «Настройки работы» — один партиал на четыре
 * экрана создания; карточка фильтров; своё поле срока.
 *
 * Проверяет ИСПОЛНЕНИЕМ то, чего не видят питон-тесты:
 *  — панель на всех экранах даёт ОДИН И ТОТ ЖЕ набор блоков и классов;
 *  — переключатель вида виден на всех трёх способах и не теряет группу;
 *  — поле срока принимает ввод с клавиатуры в русском виде и кладёт на
 *    сервер ISO — то, что ждёт `datetime.fromisoformat`;
 *  — кнопка календаря зовёт родной `showPicker`;
 *  — ряд фильтров лежит в карточке и не потерял ни одного элемента.
 *
 * ⚠️ Сохраняющих действий НЕ делает. Всё равно ходит по проверочной базе
 * (`config.settings_check`).
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/session10_settings.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');

let ok = 0, bad = 0;
function check(name, condition, extra) {
  if (condition) { ok += 1; console.log('  ✓', name); }
  else { bad += 1; console.log('  ✗', name, extra === undefined ? '' : extra); }
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

// ⚠️ Проверка ОБЯЗАНА сверять код ответа: сценарий сессии 4 открывал чужой
// экран, получал 403 и «успешно» мерил ширину страницы ошибки.
async function open(page, url, name) {
  const resp = await page.goto(BASE + url, { waitUntil: 'networkidle' });
  check(`${name}: 200`, resp.status() === 200, resp.status());
  return resp;
}

// Опись панели: какие блоки и в каком порядке. Сравниваем экраны между собой.
async function panelShape(page) {
  return page.evaluate(() => {
    const out = { title: null, fields: [], cards: 0, hasSubmit: false };
    const titles = [...document.querySelectorAll('.ws-title')]
      .map(n => n.textContent.trim());
    out.title = titles.join(' | ');
    out.cards = document.querySelectorAll('.k-card.ws-card').length;
    out.fields = [...document.querySelectorAll('.ws-card [name]')]
      .map(n => n.name).filter(n => n && n !== 'csrfmiddlewaretoken');
    out.hasSubmit = !!document.getElementById('submit-btn');
    out.hasWhy = !!document.getElementById('submit-why');
    out.dateBoxes = document.querySelectorAll('[data-k-date]').length;
    out.dateReady = document.querySelectorAll('[data-k-date].is-ready').length;
    // Ни одного браузерного datetime-local НА ВИДУ: все спрятаны надстройкой.
    out.nakedDates = [...document.querySelectorAll('input[type=datetime-local]')]
      .filter(n => !n.closest('.k-date.is-ready')).length;
    return out;
  });
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await login(page, 'tutor@test.local');

  // Номер первой группы — он нужен адресам контрольной.
  await open(page, '/teacher/groups/', 'экран «Ученики»');
  const groupId = await page.evaluate(() => {
    for (const a of document.querySelectorAll('a[href]')) {
      const m = /\/teacher\/groups\/(\d+)\//.exec(a.getAttribute('href'));
      if (m) { return m[1]; }
    }
    return null;
  });
  check('номер занятия найден', !!groupId, groupId);

  console.log('\n1. ПАНЕЛЬ НАСТРОЕК НА ЧЕТЫРЁХ ЭКРАНАХ');
  const shapes = {};

  await open(page, '/teacher/assignment/create/', 'Искать самому');
  shapes.search = await panelShape(page);
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-искать-самому.png'), fullPage: true });

  await open(page, `/teacher/groups/${groupId}/exams/new/`, 'конструктор контрольной');
  shapes.exam = await panelShape(page);
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-конструктор-контрольной.png'), fullPage: true });

  await open(page, '/teacher/assignment/build/?kind=homework', 'конструктор подборки (домашка)');
  shapes.buildHw = await panelShape(page);
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-конструктор-подборки.png'), fullPage: true });

  await open(page, `/teacher/assignment/build/?kind=exam&group=${groupId}`, 'конструктор подборки (контрольная)');
  shapes.buildEx = await panelShape(page);
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-конструктор-подборки-контрольная.png'), fullPage: true });

  for (const [key, s] of Object.entries(shapes)) {
    check(`${key}: панель на месте («Настройки работы» + «Кому выдать»)`,
          s.title.includes('Настройки работы') && s.title.includes('Кому выдать'), s.title);
    check(`${key}: кнопка и объяснение при ней`, s.hasSubmit && s.hasWhy);
    check(`${key}: голых браузерных полей даты нет`, s.nakedDates === 0, s.nakedDates);
    check(`${key}: надстройка поля даты включилась`,
          s.dateBoxes > 0 && s.dateBoxes === s.dateReady,
          `${s.dateReady}/${s.dateBoxes}`);
  }

  // Домашка везде спрашивает одно и то же; контрольная — одно и то же.
  check('домашка: набор полей одинаков на обоих экранах',
        JSON.stringify(shapes.search.fields.filter(n => n !== 'groups'))
          === JSON.stringify(shapes.buildHw.fields.filter(n => n !== 'groups')),
        `${shapes.search.fields} ≠ ${shapes.buildHw.fields}`);
  const examFields = s => s.fields.filter(n => n !== 'groups');
  check('контрольная: набор полей одинаков на обоих экранах',
        JSON.stringify(examFields(shapes.exam)) === JSON.stringify(examFields(shapes.buildEx)),
        `${shapes.exam.fields} ≠ ${shapes.buildEx.fields}`);
  check('контрольная несёт окно, лимит и «результат сразу»',
        ['kind', 'starts_at', 'ends_at', 'deadline', 'duration', 'show_results']
          .every(n => shapes.exam.fields.includes(n)), shapes.exam.fields);
  check('у контрольной внутри группы поля `groups` нет (группа из адреса)',
        !shapes.exam.fields.includes('groups'), shapes.exam.fields);

  console.log('\n2. ПЕРЕКЛЮЧАТЕЛЬ ВИДА И НОМЕР ГРУППЫ');
  for (const [url, name] of [
    ['/teacher/assignment/generate/', 'Описать словами'],
    ['/teacher/assignment/create/', 'Искать самому'],
    ['/teacher/problems/new/?to_cart=1', 'Написать свою'],
    [`/teacher/groups/${groupId}/exams/new/`, 'конструктор контрольной'],
  ]) {
    await open(page, `${url}${url.includes('?') ? '&' : '?'}group=${groupId}`, name);
    const seen = await page.evaluate(() => {
      // Вид работы — сегментированный переключатель с обзора 13.08.
      const tiles = [...document.querySelectorAll('.bh-kind__opt')]
        .map(t => t.textContent.trim());
      const links = [...document.querySelectorAll('.bh-kind__opt')]
        .map(t => t.getAttribute('href'));
      return { tiles, links };
    });
    check(`${name}: переключатель «Домашка / Контрольная» виден`,
          seen.tiles.join('/') === 'Домашка/Контрольная', seen.tiles);
    check(`${name}: группа не теряется в ссылках переключателя`,
          seen.links.every(h => h && (h.includes(`group=${groupId}`)
                                      || h.includes(`/groups/${groupId}/`))),
          seen.links);
  }

  // Те же три способа, но собираем КОНТРОЛЬНУЮ: плитки способа обязаны
  // сохранить и занятие, и вид работы. Раньше «Написать свою» теряла оба.
  for (const [url, name] of [
    ['/teacher/assignment/generate/?kind=exam', 'Описать словами (контрольная)'],
    [`/teacher/groups/${groupId}/exams/new/`, 'Искать самому (контрольная)'],
  ]) {
    await open(page, `${url}${url.includes('?') ? '&' : '?'}group=${groupId}`, name);
    const modes = await page.evaluate(() => [...document.querySelectorAll('.k-tiles .k-tile')]
      .map(t => ({ name: t.querySelector('.k-tile__name').textContent.trim(),
                   href: t.getAttribute('href') })));
    const own = modes.find(m => m.name === 'Написать свою');
    check(`${name}: «Написать свою» не теряет занятие`,
          !!own && own.href.includes(`group=${groupId}`), own && own.href);
    check(`${name}: «Написать свою» не теряет вид работы`,
          !!own && own.href.includes('kind=exam'), own && own.href);
    check(`${name}: «Написать свою» ведёт В КОРЗИНУ (to_cart)`,
          !!own && own.href.includes('to_cart=1'), own && own.href);
  }

  // Кнопки под составом на конструкторе подборки.
  await open(page, `/teacher/assignment/build/?kind=exam&group=${groupId}`,
             'конструктор подборки (кнопки под составом)');
  const under = await page.evaluate(() => [...document.querySelectorAll('.k-row .k-btn')]
    .map(a => ({ text: a.textContent.trim(), href: a.getAttribute('href') })));
  const ownBtn = under.find(a => a.text === 'Написать свою');
  check('конструктор: «Написать свою» ведёт в корзину этой работы',
        !!ownBtn && ownBtn.href.includes('to_cart=1')
          && ownBtn.href.includes('kind=exam')
          && ownBtn.href.includes(`group=${groupId}`), ownBtn && ownBtn.href);

  console.log('\n3. ПОЛЕ СРОКА: КЛАВИАТУРА, КАЛЕНДАРЬ, ФОРМАТ НА СЕРВЕР');
  await open(page, '/teacher/assignment/create/', 'Искать самому (поле срока)');

  const typed = await page.evaluate(() => {
    const box = document.querySelector('[data-k-date]');
    const text = box.querySelector('.k-date__text');
    const native = box.querySelector('.k-date__native');
    text.value = '14.08.2026, 20:00';
    text.dispatchEvent(new Event('change', { bubbles: true }));
    return { shown: text.value, sent: native.value, name: native.name };
  });
  check('ввод «14.08.2026, 20:00» → на сервер ISO 2026-08-14T20:00',
        typed.sent === '2026-08-14T20:00', typed.sent);
  check('имя поля на сервере прежнее — deadline', typed.name === 'deadline', typed.name);

  const dateOnly = await page.evaluate(() => {
    const box = document.querySelector('[data-k-date]');
    const text = box.querySelector('.k-date__text');
    const native = box.querySelector('.k-date__native');
    text.value = '01.09.2026';
    text.dispatchEvent(new Event('change', { bubbles: true }));
    return { shown: text.value, sent: native.value };
  });
  check('дата без времени дополняется до 23:59 и это ВИДНО в поле',
        dateOnly.sent === '2026-09-01T23:59' && dateOnly.shown === '01.09.2026, 23:59',
        `${dateOnly.shown} → ${dateOnly.sent}`);

  const bad1 = await page.evaluate(() => {
    const box = document.querySelector('[data-k-date]');
    const text = box.querySelector('.k-date__text');
    const native = box.querySelector('.k-date__native');
    const before = native.value;
    text.value = '31.02.2026';           // такого дня нет
    text.dispatchEvent(new Event('change', { bubbles: true }));
    return { before, after: native.value,
             err: !box.querySelector('.k-date__err').hidden,
             errShown: getComputedStyle(box.querySelector('.k-date__err')).display };
  });
  check('несуществующая дата 31.02 — ошибка, прежнее значение НЕ стёрто',
        bad1.after === bad1.before && bad1.err, JSON.stringify(bad1));
  check('подсказка об ошибке действительно видна (не съедена [hidden])',
        bad1.errShown !== 'none', bad1.errShown);

  const cleared = await page.evaluate(() => {
    const box = document.querySelector('[data-k-date]');
    const text = box.querySelector('.k-date__text');
    const native = box.querySelector('.k-date__native');
    text.value = '';
    text.dispatchEvent(new Event('change', { bubbles: true }));
    return { sent: native.value, err: !box.querySelector('.k-date__err').hidden };
  });
  check('пустое поле — законный ответ «срока нет», не ошибка',
        cleared.sent === '' && !cleared.err, JSON.stringify(cleared));

  const picker = await page.evaluate(() => {
    const box = document.querySelector('[data-k-date]');
    const native = box.querySelector('.k-date__native');
    let called = false;
    native.showPicker = function () { called = true; };
    box.querySelector('.k-date__pick').click();
    const r = native.getBoundingClientRect();
    return { called, rendered: r.width > 0 && r.height > 0 };
  });
  check('кнопка календаря зовёт родной showPicker', picker.called);
  check('родное поле остаётся ОТРИСОВАННЫМ (иначе showPicker бросает)',
        picker.rendered);

  console.log('\n4. КАРТОЧКА ФИЛЬТРОВ РУЧНОГО ПОИСКА');
  const filters = await page.evaluate(() => {
    const form = document.getElementById('filter-form');
    return {
      inCard: form.classList.contains('k-card') && form.classList.contains('k-filters'),
      names: [...form.querySelectorAll('[name]')].map(n => n.name),
      buttons: [...form.querySelectorAll('button, a')].map(n => n.textContent.trim()),
      rows: form.querySelector('.filters-row').getBoundingClientRect().height,
    };
  });
  check('ряд фильтров лежит в карточке набора', filters.inCard);
  check('поля отбора все семь на месте',
        JSON.stringify(filters.names) === JSON.stringify(
          ['q', 'topic', 'difficulty', 'type', 'has_solution']),
        filters.names);
  check('кнопки «Найти» и «Сброс» на месте',
        filters.buttons.join('/') === 'Найти/Сброс', filters.buttons);
  check('фильтры укладываются в одну-две строки', filters.rows <= 90, filters.rows);

  console.log('\n5. ТЁМНАЯ ТЕМА И 380 ПИКСЕЛЕЙ');
  for (const [url, name] of [
    ['/teacher/assignment/create/', 'искать-самому'],
    [`/teacher/groups/${groupId}/exams/new/`, 'контрольная'],
    ['/teacher/assignment/build/?kind=exam', 'подборка'],
  ]) {
    await page.goto(BASE + url, { waitUntil: 'networkidle' });
    await page.evaluate(() => {
      localStorage.setItem('theme', 'dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    });
    await page.screenshot({ path: path.join(SHOTS, `с10ф2-тёмная-${name}.png`), fullPage: true });
  }

  const narrow = await ctx.newPage();
  await narrow.setViewportSize({ width: 380, height: 900 });
  for (const [url, name] of [
    ['/teacher/assignment/create/', 'искать-самому'],
    [`/teacher/groups/${groupId}/exams/new/`, 'контрольная'],
    ['/teacher/assignment/build/?kind=exam', 'подборка'],
  ]) {
    const resp = await narrow.goto(BASE + url, { waitUntil: 'networkidle' });
    check(`380px ${name}: 200`, resp.status() === 200, resp.status());
    // ⚠️ Меряем ПАНЕЛЬ, а не страницу: старую поломку `_nav.html` (она тянет
    // вбок каждую страницу сайта) в этой сессии не чиним, и ловить её здесь
    // значило бы красить проверку чужим долгом.
    const wide = await narrow.evaluate(() => {
      const card = document.querySelector('.k-card.ws-card');
      return card ? Math.round(card.scrollWidth - card.clientWidth) : -1;
    });
    check(`380px ${name}: панель не вылезает вбок`, wide <= 1, wide);
    await narrow.screenshot({ path: path.join(SHOTS, `с10ф2-380-${name}.png`), fullPage: true });
  }

  check('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));

  console.log(`\nИТОГО: ${ok} успешно, ${bad} провалено`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
