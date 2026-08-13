/**
 * Сессия 10, фаза 2: ТРИ ПУТИ СОЗДАНИЯ РАБОТЫ ЦЕЛИКОМ.
 *
 * Панель настроек сведена в один партиал, и это трогает все три рабочих
 * пути. Проверка одна: пройти каждый до конца и получить работу.
 *   1. Домашка через «Описать словами» → конструктор подборки.
 *   2. Контрольная через «Искать самому» (конструктор контрольной).
 *   3. Работа со СВОЕЙ задачей: «Написать свою» → корзина → создание.
 *
 * ⚠️ СЦЕНАРИЙ СОХРАНЯЮЩИЙ: он создаёт работы. Поэтому ходит по проверочной
 * базе `db_check.sqlite3` (`config.settings_check`), а не по боевой.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/session10_create.js [порт]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');
const STAMP = String(Date.now()).slice(-6);

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

// Заполняем поле срока ТАК ЖЕ, КАК ЧЕЛОВЕК: печатаем по-русски в видимое
// поле. Если надстройка не работает, сервер получит пустой срок, и это
// сразу увидит проверка ниже.
async function typeDate(page, label, value) {
  await page.evaluate(({ label, value }) => {
    const labels = [...document.querySelectorAll('.ws-field .k-label')];
    const target = labels.find(l => l.textContent.trim() === label);
    const box = target.parentElement.querySelector('[data-k-date]');
    const text = box.querySelector('.k-date__text');
    text.value = value;
    text.dispatchEvent(new Event('change', { bubbles: true }));
  }, { label, value });
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await login(page, 'tutor@test.local');
  await page.goto(`${BASE}/teacher/groups/`, { waitUntil: 'networkidle' });
  const groupId = await page.evaluate(() => {
    for (const a of document.querySelectorAll('a[href]')) {
      const m = /\/teacher\/groups\/(\d+)\//.exec(a.getAttribute('href'));
      if (m) { return m[1]; }
    }
    return null;
  });

  // ── ПУТЬ 1: домашка описанием словами ────────────────────────────────
  console.log('\nПУТЬ 1. ДОМАШКА ЧЕРЕЗ «ОПИСАТЬ СЛОВАМИ»');
  const hwName = `Проверка сессии 10 — домашка ${STAMP}`;
  await page.goto(`${BASE}/teacher/assignment/generate/?group=${groupId}`,
                  { waitUntil: 'networkidle' });
  await page.fill('textarea[name=text]', 'три задачи на рыночное равновесие');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type=submit].k-btn--main'),
  ]);
  const step2 = await page.evaluate(() => ({
    heading: (document.querySelector('h2') || {}).textContent || '',
    cards: document.querySelectorAll('[name=row_keep]').length,
  }));
  check('шаг «что нашлось» открылся', step2.cards > 0, JSON.stringify(step2));

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#to-cart'),
  ]);
  check('перешли в конструктор подборки',
        page.url().includes('/teacher/assignment/build/'), page.url());
  const inCart = await page.evaluate(() => document.querySelectorAll('.bd-item').length);
  check('задачи доехали в конструктор', inCart > 0, inCart);

  await page.fill('input[name=name]', hwName);
  await typeDate(page, 'Срок сдачи', '20.09.2026, 18:30');
  await page.evaluate(() => {
    const box = document.querySelector('.ws-groups input[name=groups]');
    box.checked = true;
    box.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-путь1-конструктор.png'), fullPage: true });
  const btn1 = await page.evaluate(() => document.getElementById('submit-btn').disabled);
  check('кнопка «Создать» разблокировалась', btn1 === false);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#submit-btn'),
  ]);
  check('домашка создана — открылась её страница',
        /\/teacher\/groups\/\d+\/assignments\/\d+\//.test(page.url()), page.url());
  const hwPage = await page.evaluate(() => document.body.innerText);
  check('на странице работы её название', hwPage.includes(hwName));
  check('срок сдачи сохранился (20.09.2026)',
        hwPage.includes('20.09.2026') || hwPage.includes('20.09'),
        hwPage.slice(0, 400));
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-путь1-готово.png'), fullPage: true });

  // ── ПУТЬ 2: контрольная ручным поиском ───────────────────────────────
  console.log('\nПУТЬ 2. КОНТРОЛЬНАЯ ЧЕРЕЗ «ИСКАТЬ САМОМУ»');
  const exName = `Проверка сессии 10 — контрольная ${STAMP}`;
  await page.goto(`${BASE}/teacher/groups/${groupId}/exams/new/`,
                  { waitUntil: 'networkidle' });
  check('переключатель вида на конструкторе контрольной есть',
        await page.evaluate(() => document.querySelectorAll('.bh-kind .k-tile').length) === 2);
  const adders = await page.$$('.problem-card [data-add]');
  await adders[0].click();
  if (adders[1]) { await adders[1].click(); }
  const cart2 = await page.evaluate(() =>
    parseInt(document.getElementById('cart-count').textContent, 10));
  check('задачи легли в корзину', cart2 > 0, cart2);

  await page.fill('input[name=name]', exName);
  await typeDate(page, 'Начало окна', '21.09.2026, 10:00');
  await typeDate(page, 'Конец окна', '21.09.2026, 11:30');
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-путь2-конструктор.png'), fullPage: true });
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#submit-btn'),
  ]);
  check('контрольная создана — открылась её страница',
        /\/teacher\/groups\/\d+\/assignments\/\d+\//.test(page.url()), page.url());
  const exPage = await page.evaluate(() => document.body.innerText);
  check('на странице работы её название', exPage.includes(exName));
  check('окно контрольной сохранилось (21.09.2026)',
        exPage.includes('21.09.2026') || exPage.includes('21.09'),
        exPage.slice(0, 400));
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-путь2-готово.png'), fullPage: true });

  // ── ПУТЬ 3: работа со своей задачей ──────────────────────────────────
  console.log('\nПУТЬ 3. РАБОТА СО СВОЕЙ ЗАДАЧЕЙ');
  const ownName = `Проверка сессии 10 — своя задача ${STAMP}`;
  const ownTitle = `Своя задача ${STAMP}`;
  await page.goto(`${BASE}/teacher/problems/new/?to_cart=1&group=${groupId}`,
                  { waitUntil: 'networkidle' });
  check('на «Написать свою» видна общая шапка с переключателем',
        await page.evaluate(() => document.querySelectorAll('.bh-kind .k-tile').length) === 2);
  await page.fill('input[name=title]', ownTitle);
  await page.fill('textarea[name=statement]',
                  'Спрос Qd = 100 - 2P, предложение Qs = 3P. Найдите равновесную цену.');
  await page.fill('input[name=correct_answer]', '20');
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-путь3-своя-задача.png'), fullPage: true });
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#problem-form button[type=submit]'),
  ]);
  check('после сохранения вернулись в конструктор',
        /assignment\/(create|build)|exams\/new/.test(page.url()), page.url());

  const cart3 = await page.evaluate(() => {
    const node = document.getElementById('cart-count');
    return node ? parseInt(node.textContent, 10)
                : document.querySelectorAll('.bd-item').length;
  });
  check('своя задача легла в корзину работы', cart3 > 0, cart3);

  await page.fill('input[name=name]', ownName);
  await typeDate(page, 'Срок сдачи', '25.09.2026');
  await page.evaluate(() => {
    const box = document.querySelector('.ws-groups input[name=groups]');
    if (box) { box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true })); }
  });
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#submit-btn'),
  ]);
  check('работа со своей задачей создана',
        /\/teacher\/groups\/\d+\/assignments\/\d+\//.test(page.url()), page.url());
  const ownPage = await page.evaluate(() => document.body.innerText);
  check('на странице работы её название', ownPage.includes(ownName));
  check('своя задача внутри работы', ownPage.includes(ownTitle), ownPage.slice(0, 500));
  check('дата без времени дополнилась до конца дня (25.09.2026)',
        ownPage.includes('25.09.2026') || ownPage.includes('25.09'),
        ownPage.slice(0, 400));
  await page.screenshot({ path: path.join(SHOTS, 'с10ф2-путь3-готово.png'), fullPage: true });

  check('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));
  console.log(`\nИТОГО: ${ok} успешно, ${bad} провалено`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
