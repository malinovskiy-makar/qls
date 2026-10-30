// Э6: две страницы. Компьютер (1280, вошедший ученик) открывает задание тура на
// время; телефон (390, без входа) открывает ссылку из QR и грузит лист; компьютер
// обязан увидеть лист не позже 5 с. Потом тур сдаётся во второй вкладке —
// опрос первой должен остановиться, а ссылка телефона — ответить 410.
// Запуск: node phone_flow.mjs <путь задания> --login-file=<файл логин:пароль>
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '../../../node_modules/playwright/index.mjs';

const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:8097';
const take = process.argv[2];
const loginFile = (process.argv.find(a => a.startsWith('--login-file=')) || '').split('=')[1];
const [user, pass] = fs.readFileSync(loginFile, 'utf8').trim().split(':');
const OUT = path.resolve(new URL('../shots/E6', import.meta.url).pathname);
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail = '') => { results.push(ok); console.log(`${ok ? 'прошло' : 'ПРОВАЛ'} ${name} ${detail}`); };

// Лист — настоящий PNG, нарисованный Pillow (tools/sheet_sample.png).
const sheetPath = path.resolve(new URL('./sheet_sample.png', import.meta.url).pathname);

const browser = await chromium.launch();
const desk = await browser.newContext({ viewport: { width: 1280, height: 900 } });
await desk.addCookies([{ name: 'weco_consent', value: 'necessary', url: BASE }]);
const page = await desk.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
await page.goto(BASE + '/login/');
await page.fill('input[name="username"]', user);
await page.fill('input[name="password"]', pass);
await Promise.all([page.waitForLoadState('networkidle'), page.click('form [type="submit"]')]);
await page.goto(BASE + take, { waitUntil: 'networkidle' });
const block = page.locator('.om-taskpane:not([hidden]) [data-phone]');
check('блок «С телефона» с QR на экране', await block.count() === 1);
const token = await block.getAttribute('data-token');
const itemId = await block.getAttribute('data-item');
const before = await page.locator(`[data-sheets="${itemId}"] figure`).count();
await page.screenshot({ path: path.join(OUT, 'flow-1-desk-before.png') });

const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
await phone.addCookies([{ name: 'weco_consent', value: 'necessary', url: BASE }]);
const ph = await phone.newPage();
const resp = await ph.goto(`${BASE}/olympiads/u/${token}/`, { waitUntil: 'networkidle' });
check('телефон открывает ссылку без входа', resp.status() === 200, String(resp.status()));
const t0 = Date.now();
await Promise.all([ph.waitForNavigation({ waitUntil: 'networkidle' }),
  ph.setInputFiles('.om-ph-gal input[type=file]', sheetPath)]);
await ph.screenshot({ path: path.join(OUT, 'flow-2-phone-after.png'), fullPage: true });
let seenMs = null;
try {
  await page.waitForFunction(([id, n]) => document.querySelectorAll(`[data-sheets="${id}"] figure`).length > n,
    [itemId, before], { timeout: 5000, polling: 200 });
  seenMs = Date.now() - t0;
} catch (e) { /* не увидел за 5 с */ }
check('компьютер видит лист с телефона не позже 5 с', seenMs !== null && seenMs <= 5000, seenMs === null ? 'не увидел' : `${seenMs} мс`);
check('«телефон подключён» на компьютере', (await page.locator('.om-taskpane:not([hidden]) [data-phone-state]').innerText()).includes('телефон подключён'));
await page.screenshot({ path: path.join(OUT, 'flow-3-desk-after.png') });

// Сдача тура во второй вкладке; первая продолжает опрос — он должен остановиться.
const polls = [];
let closedAt = null;
page.on('request', r => { if (r.url().includes('/sheets/?item=')) polls.push(Date.now()); });
page.on('response', async r => {
  if (!r.url().includes('/sheets/?item=') || closedAt) return;
  try { if ((await r.json()).closed) closedAt = Date.now(); } catch (e) { /* страница ушла */ }
});
const other = await desk.newPage();
await other.goto(BASE + take, { waitUntil: 'networkidle' });
other.on('dialog', d => d.accept());
await Promise.all([other.waitForNavigation({ waitUntil: 'networkidle' }), other.click('#finish-btn')]);
const submittedAt = Date.now();
await page.waitForTimeout(8000);
// Правило: после первого ответа `closed` — ни одного запроса опроса (exam.js
// может ещё и увести страницу на результат — тогда запросов нет тем более).
const after = closedAt ? polls.filter(t => t > closedAt + 50) : polls.filter(t => t > submittedAt);
check('опрос остановился после сдачи', closedAt !== null || after.length === 0,
  `ответ closed ${closedAt ? 'получен' : 'не пришёл'}, запросов после него ${after.length}`);
check('после closed запросов нет', after.length === 0, String(after.length));
const gone = await ph.goto(`${BASE}/olympiads/u/${token}/`);
check('ссылка телефона после сдачи — 410', gone.status() === 410, String(gone.status()));
check('ошибок JS на компьютере нет', errors.length === 0, errors.join(' | '));
await browser.close();
console.log(`ИТОГО: прошло ${results.filter(Boolean).length} / всего ${results.length}`);
process.exitCode = results.every(Boolean) ? 0 : 1;
