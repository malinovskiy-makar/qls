// Э2E дня 30.10 (основа — ночной Э9): сквозной проход раздела «Олимпиады» глазами ученика.
// День: любое нативное окно (alert/confirm/prompt) — провал; «Завершить тур» и «Сдать тур» —
// через своё окно раздела; «Разборы тура» открывают PDF; у 59997 три пункта без «(4 балла)»;
// --dark — тёмная тема.
// Без времени: главная → ВсОШ → 2025/26, 11 класс → 2 тур → «Без времени» → задание 6
// текстом → «Сдать задание» (проверка подставным поставщиком) → «Оспорить оценку» →
// «Завершить тур» → результат. На время: «На время» → задание 6 — лист фото →
// «Сдать тур» → очередь проверки → результат. Ширина 1280 или 390 (--phone).
// Запуск: node e2e.mjs --login-file=<логин:пароль> [--phone]
// Снимки — shots/E9/<ширина>-NN-<шаг>.png; итог «прошло N / всего M»; ошибки консоли считаются.
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '../../../node_modules/playwright/index.mjs';

const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:8097';
const phone = process.argv.includes('--phone');
const loginFile = (process.argv.find(a => a.startsWith('--login-file=')) || '').split('=')[1];
const [user, pass] = fs.readFileSync(loginFile, 'utf8').trim().split(':');
const W = phone ? 390 : 1280;
const dark = process.argv.includes('--dark');
const TAG = `${W}${dark ? '-dark' : ''}`;
const OUT = path.resolve(new URL('../shots/E2E', import.meta.url).pathname);
fs.mkdirSync(OUT, { recursive: true });
const SHEET = path.resolve(new URL('../../night_olymp_20261030/tools/sheet_sample.png', import.meta.url).pathname);
const STUDENT = 'а) Оптимум производителей: X_A/1000 = p, X_B/200 = p. Рынок X: 1200p = 1800 − 600p², p* = 1. '
  + 'Альфа производит 1000, потребляет 550, экспорт 450. Бета производит 200, потребляет 650, импорт 450. '
  + 'б) p̄ = 0,9. Альфа: X = 900, потребление 528,9, экспорт 371,1. Бета покрывает остаток сама: X_B = 287,8, '
  + 'потребление 658,8. в) p̂ = 2/3. Экспорт Альфы 173,3. Бета: X_B = 200 · 2/3 = 133,3, потребление 306,6 — '
  + 'потребители проигрывают.';

const results = [];
const check = (name, ok, detail = '') => { results.push(!!ok); console.log(`${ok ? 'прошло' : 'ПРОВАЛ'} [${TAG}] ${name} ${detail}`); };
let step = 0;
const shot = async (page, name) => { step += 1; await page.screenshot({ path: path.join(OUT, `${TAG}-${String(step).padStart(2, '0')}-${name}.png`), fullPage: true }); };

const browser = await chromium.launch();
const context = await browser.newContext(phone ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
  : { viewport: { width: 1280, height: 900 } });
await context.addCookies([{ name: 'weco_consent', value: 'necessary', url: BASE }]);
await context.addInitScript((t) => { try { localStorage.setItem('theme', t); } catch (e) {} }, dark ? 'dark' : 'light');
const page = await context.newPage();
const consoleErrors = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => consoleErrors.push(String(e)));
let native = 0;
page.on('dialog', d => { native += 1; d.dismiss(); });
const dlg = page.locator('#om-dlg');

await page.goto(BASE + '/login/');
await page.fill('input[name="username"]', user);
await page.fill('input[name="password"]', pass);
await Promise.all([page.waitForLoadState('networkidle'), page.click('form [type="submit"]')]);

// ── Главная → ВсОШ ──
await page.goto(BASE + '/olympiads/', { waitUntil: 'networkidle' });
await shot(page, 'home');
const vsLink = page.locator(phone ? '.om-phone a.om-phl[href="/olympiads/vseros/"]' : '.om-desk a.hl-name[href="/olympiads/vseros/"]').first();
await Promise.all([page.waitForURL('**/olympiads/vseros/'), vsLink.click()]);
check('главная → страница ВсОШ', page.url().endsWith('/olympiads/vseros/'));
await shot(page, 'vseros');

// ── Клетка 2025/26, 11 класс → панель туров ──
let cell;
if (phone) {
  cell = page.locator('.om-phone .ph-row', { hasText: '2025/26' }).locator('a.om-cell').first();
} else {
  cell = page.locator('.om-desk tr', { hasText: '2025/26' }).first().locator('a.om-cell').nth(2);
}
await cell.click();
const panel = page.locator(phone ? '.om-phone [data-panel]:not([hidden]) .om-panel' : '.om-desk tr.om-prow:not([hidden]) .om-panel');
check('панель туров раскрылась под строкой (JS)', await panel.count() === 1 && (await panel.innerText()).includes('11 класс'));
await shot(page, 'panel');

// ── 2 тур → «Без времени» → вход ──
const tour2 = panel.locator('.om-tour', { hasText: '2 тур' });
await Promise.all([page.waitForURL('**/variant/**'), tour2.getByRole('link', { name: 'Без времени' }).click()]);
check('вход в тур открыт', (await page.locator('h1').innerText()).includes('2 тур'));
await shot(page, 'intro');
await Promise.all([page.waitForURL('**/take/'), page.locator('.om-mode', { hasText: 'Без времени' }).getByRole('button', { name: 'Начать' }).click()]);
check('режим «Без времени» начат', page.url().includes('/take/') && (await page.locator('.om-free-hd').innerText()).includes('без времени'));

// ── Задание 6: решение текстом → «Сдать задание» ──
await page.locator('.om-tn', { hasText: 'Задание 6' }).click();
const pane = page.locator('.om-taskpane:not([hidden])');
check('открыто задание 6', (await pane.locator('.om-task__t').innerText()).startsWith('6.'));
const parts = await pane.locator('.om-task .om-part > b').allInnerTexts();
const taskText = await pane.locator('.om-task').innerText();
check('у 59997 три пункта а, б, в по одному разу, без «(4 балла)» в тексте',
  parts.join(',') === 'а,б,в' && !/\(\s*4 балла\s*\)/.test(taskText) && (taskText.match(/Представим/g) || []).length === 1, parts.join(','));
await pane.locator('.om-sol__seg label', { hasText: 'Текст' }).click();
await pane.locator('textarea.om-area').fill(STUDENT);
await shot(page, 'free-text');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), pane.getByRole('button', { name: 'Сдать задание' }).click()]);
const done = page.locator('.om-taskpane:not([hidden]) .om-check');
const doneText = await done.innerText();
check('проверка по критериям: 8 из 12', doneText.includes('8 из 12') && doneText.includes('Проверено ИИ по критериям жюри'), doneText.slice(0, 80).replace(/\s+/g, ' '));
await shot(page, 'free-checked');

// ── «Оспорить оценку» → реплика ──
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), done.getByRole('link', { name: 'Оспорить оценку' }).click()]);
const chat = page.locator('[data-dispute]');
check('панель «Оспорить оценку» открыта, строка критерия подсвечена', await chat.count() === 1 && await page.locator('.om-crit--on').count() === 1);
await chat.locator('[data-dispute-text]').fill('Я нашёл производство Беты из X_B/200 = p. Почему за это ноль?');
await chat.locator('.ai-send').click();
await page.waitForFunction(() => { const m = document.querySelectorAll('[data-dispute-log] .ai-msg--ai'); return m.length && m[m.length - 1].textContent.length > 5 && m[m.length - 1].textContent !== '…'; }, null, { timeout: 15000 });
const replyText = await chat.locator('.ai-msg--ai').last().innerText();
check('ответ чата получен, балл не изменился', replyText.includes('K14') && (await done.innerText()).includes('8 из 12'), replyText.slice(0, 60));
await shot(page, 'dispute');

// ── «Завершить тур» → результат ──
await page.locator('.om-tn').last().click();
await page.locator('.om-taskpane:not([hidden]) #finish-btn').click();
check('«Завершить тур» → своё окно «Завершить тур?»', await dlg.evaluate(d => d.open) && (await dlg.innerText()).includes('Завершить тур?'));
await shot(page, 'free-finish-dialog');
await Promise.all([page.waitForURL('**/result/**'), dlg.getByRole('button', { name: 'Завершить тур' }).click()]);
await page.waitForLoadState('networkidle');
const res1 = await page.locator('.om-res-top').innerText();
check('результат «без времени»: тур сдан', res1.includes('2 тур сдан') && res1.includes('без времени'), res1.replace(/\s+/g, ' ').slice(0, 70));
await shot(page, 'free-result');

// ── На время: лист с компьютера (на телефоне — «Сфотографировать») → «Сдать тур» ──
await page.goto(BASE + page.url().replace(BASE, '').replace('result/', '?mode=timed'), { waitUntil: 'networkidle' });
await Promise.all([page.waitForURL('**/take/'), page.locator('.om-mode', { hasText: 'На время' }).getByRole('button', { name: 'Начать' }).click()]);
check('полоса тура с таймером вместо шапки', await page.locator('.om-ttbar #timer').count() === 1 && !(await page.locator('nav.site-nav').isVisible()));
await page.locator('.om-tn', { hasText: 'Задание 6' }).click();
const tpane = page.locator('.om-taskpane:not([hidden])');
const input = phone ? tpane.locator('label.om-cam input[type=file]') : tpane.locator('label.om-desk-only input[type=file]');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), input.setInputFiles(SHEET)]);
const sheets = await page.locator('.om-taskpane:not([hidden]) .om-sheets figure').count();
check('лист загружен и виден под заданием', sheets === 1, String(sheets));
await shot(page, 'timed-sheet');
await page.locator('.om-ttbar #finish-btn').click();
check('«Сдать тур» → своё окно со списком заданий', await dlg.evaluate(d => d.open) && (await dlg.innerText()).includes('есть решение'));
await shot(page, 'timed-finish-dialog');
await Promise.all([page.waitForURL('**/result/**'), dlg.getByRole('button', { name: 'Сдать тур' }).click()]);
// Очередь проверки: страница опрашивает check-next и перезагружается сама.
await page.waitForFunction(() => !document.querySelector('[data-queue]'), null, { timeout: 60000 }).catch(() => {});
await page.waitForLoadState('networkidle');
const res2 = await page.locator('.om-res-top').innerText();
const row6 = await page.locator('.om-res-row', { hasText: 'Торговля' }).first().innerText();
check('результат «на время»: очередь прошла, задание 6 — 8 из 12', !(await page.locator('[data-queue]').count()) && row6.includes('8 из 12'), row6.replace(/\s+/g, ' ').slice(0, 80));
check('результат «на время»: тур сдан на время', res2.includes('на время'));
await shot(page, 'timed-result');

// ── «Разборы тура» открывают PDF (наша копия) ──
const sol = page.getByRole('link', { name: 'Разборы тура' });
const href = await sol.getAttribute('href');
const pdf = await page.request.get(BASE + href);
check('«Разборы тура» → PDF 200, своя копия', href.startsWith('/olympiads/') && pdf.status() === 200
  && pdf.headers()['content-type'] === 'application/pdf', `${href} ${pdf.status()} ${pdf.headers()['content-type']}`);

check('ошибок консоли браузера нет', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
check('нативных окон 0', native === 0, `(было ${native})`);
await browser.close();
console.log(`ИТОГО [${TAG}]: прошло ${results.filter(Boolean).length} / всего ${results.length}`);
process.exitCode = results.every(Boolean) ? 0 : 1;
