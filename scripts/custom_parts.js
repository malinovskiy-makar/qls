/**
 * Пункты в своей задаче репетитора — сквозная проверка (п. 15.1, 15.2).
 *
 * Репетитор создаёт открытую задачу с двумя пунктами, выдаёт её группе,
 * ученик отвечает на каждый пункт отдельно, автопроверка считает по
 * пунктам, репетитор видит результат.
 *
 * ⚠️ Сценарий сохраняет данные, поэтому работает по ОТДЕЛЬНОЙ базе
 * (`config.settings_check`).
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/custom_parts.js [порт]
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
  const users = { tutor: 'tutor@test.local', student: 'student1@test.local' };
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', users[who]);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();

  await login(page, 'tutor');
  let resp = await page.goto(`${BASE}/teacher/problems/new/`,
                             { waitUntil: 'networkidle' });
  check('экран своей задачи открылся', resp.status() === 200, resp.status());

  await page.fill('#id_title', 'Задача с пунктами (проверка)');
  await page.fill('#id_statement',
    'Функция спроса $Q_d = 100 - 2P$, предложения $Q_s = 4P - 20$.');
  await page.fill('#id_solution',
    'Приравниваем: $100-2P = 4P-20$, отсюда $P^* = 20$, $Q^* = 60$.');

  // липкое ли превью
  const sticky = await page.$eval('.preview',
    (el) => getComputedStyle(el).position);
  check('превью липкое', sticky === 'sticky', sticky);
  await page.waitForTimeout(800);
  const hasSolution = await page.$eval('#preview-solution', (el) => !el.hidden);
  check('решение видно в превью', hasSolution);

  // два пункта
  await page.click('#add-part-btn');
  await page.click('#add-part-btn');
  const rows = await page.$$('.part-row');
  check('добавились два пункта', rows.length === 2, rows.length);

  const parts = await page.$$('.part-row');
  await parts[0].$eval('[name=part_statement]', (el) => {
    el.value = 'Найдите равновесную цену.';
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await parts[0].$eval('[name=part_answer]', (el) => { el.value = '20'; });
  await parts[0].$eval('[name=part_points]', (el) => { el.value = '1'; });
  await parts[1].$eval('[name=part_statement]', (el) => {
    el.value = 'Найдите равновесное количество.';
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await parts[1].$eval('[name=part_answer]', (el) => { el.value = '60'; });
  await parts[1].$eval('[name=part_points]', (el) => { el.value = '3'; });
  await page.waitForTimeout(900);

  const wholeHidden = await page.$eval('#whole-answer', (el) => el.hidden);
  check('общее поле ответа спряталось, когда есть пункты', wholeHidden);
  const pv = await page.$$eval('.pv-part', (n) => n.map((e) => e.textContent.trim()));
  check('пункты видны в превью', pv.length === 2, JSON.stringify(pv));
  await page.screenshot({ path: path.join(SHOTS, 'ф06-своя-задача-пункты.png'),
                          fullPage: true });

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type=submit].k-btn--main'),
  ]);
  const saved = page.url();
  check('задача сохранилась', /\/problems\/\d+\/edit\//.test(saved), saved);
  const backParts = await page.$$('.part-row');
  check('пункты сохранились и вернулись в форму', backParts.length === 2,
        backParts.length);
  const letters = await page.$$eval('.part-label-input',
    (n) => n.map((e) => e.value));
  check('метки проставились буквами',
        letters.join(',') === 'а,б', letters.join(','));

  console.log(`\nитого: ${ok} успешно, ${bad} неудачно`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
