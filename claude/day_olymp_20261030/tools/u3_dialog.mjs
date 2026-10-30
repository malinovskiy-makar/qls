// У3: своё окно раздела вместо браузерного. Охрана: любое нативное окно
// (alert/confirm/prompt) — провал проверки.
// «Без времени»: «Сдать задание» без решения → окно → Esc / «Вернуться к решению»
// (ничего не сдано) → «Сдать без решения» (сдано); «Завершить тур» → окно →
// «Вернуться» → «Завершить тур» → результат. «На время»: «Сдать тур» → окно со
// списком заданий и остатком времени, фокус внутри → Esc → «Сдать тур» → результат.
// Запуск: node u3_dialog.mjs --login-file=<логин:пароль> [--phone]
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '../../../node_modules/playwright/index.mjs';

const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:8097';
const KIT = process.env.KIT || '562';
const phone = process.argv.includes('--phone');
const loginFile = (process.argv.find(a => a.startsWith('--login-file=')) || '').split('=')[1];
const [user, pass] = fs.readFileSync(loginFile, 'utf8').trim().split(':');
const W = phone ? 390 : 1280;
const OUT = path.resolve(new URL('../shots/U3', import.meta.url).pathname);
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail = '') => { results.push(!!ok); console.log(`${ok ? 'прошло' : 'ПРОВАЛ'} [${W}] ${name} ${detail}`); };

const browser = await chromium.launch();
const context = await browser.newContext(phone ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
  : { viewport: { width: 1280, height: 900 } });
await context.addCookies([{ name: 'weco_consent', value: 'necessary', url: BASE }]);
const page = await context.newPage();
let native = 0;
const consoleErrors = [];
page.on('dialog', d => { native += 1; d.dismiss(); });
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => consoleErrors.push(String(e)));

await page.goto(BASE + '/login/');
await page.fill('input[name="username"]', user);
await page.fill('input[name="password"]', pass);
await Promise.all([page.waitForLoadState('networkidle'), page.click('form [type="submit"]')]);

const dlg = page.locator('#om-dlg');
const isOpen = async () => dlg.evaluate(d => d.open);

// ── Без времени ──
await page.goto(`${BASE}/olympiads/vseros/variant/${KIT}/?mode=free`, { waitUntil: 'networkidle' });
await Promise.all([page.waitForURL('**/take/**'),
  page.locator('.om-mode', { hasText: 'Без времени' }).getByRole('button', { name: 'Начать' }).click()]);
const firstTab = page.locator('.om-tn').first();
await firstTab.click();
let pane = page.locator('.om-taskpane:not([hidden])');
await pane.getByRole('button', { name: 'Сдать задание' }).click();
check('«Сдать задание» без решения → своё окно', await isOpen() && (await dlg.innerText()).replace(/\u00a0/g, ' ').includes('Сдать задание без решения? Балл — 0'));
await page.screenshot({ path: path.join(OUT, `${W}-free-empty.png`) });
const focusInside = await page.evaluate(() => document.getElementById('om-dlg').contains(document.activeElement));
check('фокус внутри окна', focusInside);
await page.keyboard.press('Escape');
check('Esc закрыл окно, задание не сдано', !(await isOpen()) && !(await firstTab.innerText()).includes(' из '));
await pane.getByRole('button', { name: 'Сдать задание' }).click();
await dlg.getByRole('button', { name: 'Вернуться к решению' }).click();
check('«Вернуться к решению» закрыл окно, задание не сдано', !(await isOpen()) && page.url().includes('/take/'));
await pane.getByRole('button', { name: 'Сдать задание' }).click();
await Promise.all([page.waitForEvent('load'), dlg.getByRole('button', { name: 'Сдать без решения' }).click()]);
check('«Сдать без решения» сдал задание, тур открыт', page.url().includes('/take/') && /· /.test(await page.locator('.om-tn').first().innerText()));

const tabs = page.locator('.om-tn');
await tabs.last().click();
const finish = page.locator('.om-taskpane:not([hidden]) #finish-btn');
await finish.click();
const total = await tabs.count();
check('«Завершить тур» → своё окно «Завершить тур?»', await isOpen() && (await dlg.innerText()).includes('Завершить тур?')
  && (await dlg.innerText()).includes(`Не сдано заданий: ${total - 1} из ${total}`));
await page.screenshot({ path: path.join(OUT, `${W}-free-finish.png`) });
await dlg.getByRole('button', { name: 'Вернуться к решению' }).click();
check('«Вернуться» — тур не завершён', !(await isOpen()) && page.url().includes('/take/'));
await finish.click();
await Promise.all([page.waitForURL('**/result/**'), dlg.getByRole('button', { name: 'Завершить тур' }).click()]);
check('«Завершить тур» в окне → результат', page.url().includes('/result/'));

// ── На время ──
await page.goto(`${BASE}/olympiads/vseros/variant/${KIT}/?mode=timed`, { waitUntil: 'networkidle' });
await Promise.all([page.waitForURL('**/take/**'),
  page.locator('.om-mode', { hasText: 'На время' }).getByRole('button', { name: 'Начать' }).click()]);
pane = page.locator('.om-taskpane:not([hidden])');
await pane.locator('.om-sol__seg label', { hasText: 'Текст' }).click();
await pane.locator('textarea.om-area').fill('Решение первого задания.');
await page.locator('.om-ttbar #finish-btn').click();
const text = await dlg.innerText();
check('«Сдать тур» → своё окно со списком и временем', await isOpen() && text.includes('Сдать тур?')
  && text.includes('есть решение') && text.includes('нет решения') && text.includes('До конца тура'));
const amber = await dlg.locator('[data-dlg-ok]').evaluate(b => b.classList.contains('om-amber'));
check('кнопка «Сдать тур» — янтарь бренда', amber);
await page.screenshot({ path: path.join(OUT, `${W}-timed-finish.png`) });
await page.keyboard.press('Escape');
check('Esc — тур не сдан', !(await isOpen()) && page.url().includes('/take/'));
await page.locator('.om-ttbar #finish-btn').click();
await Promise.all([page.waitForURL('**/result/**'), dlg.getByRole('button', { name: 'Сдать тур' }).click()]);
check('«Сдать тур» в окне → результат', page.url().includes('/result/'));

check('нативных окон 0', native === 0, `(было ${native})`);
check('ошибок консоли 0', consoleErrors.length === 0, consoleErrors.slice(0, 2).join(' | '));
await browser.close();
console.log(`итог [${W}]: прошло ${results.filter(Boolean).length} / всего ${results.length}`);
process.exit(results.every(Boolean) ? 0 : 1);
