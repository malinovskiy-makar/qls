// У6: «Сдать задание» не должно завершать тур — сценарий гонки автосохранения.
//
// Режим «Без времени», тур 2 ВсОШ 2025/26, 11 кл. (комплект 562). Задание 6:
// текст решения → «Сдать задание», причём ответ `item/` придерживается на 3 с, а
// автосохранение этого задания уходит на сервер на 1 с позже (так в жизни
// бывает при синхронной ИИ-проверке: страница ещё жива, задание уже сдано).
// Затем задание 7 так же. Итог: попытка НЕ сдана, открыта страница заданий.
// Нативные окна (alert/confirm/prompt) — ПРИНИМАЮТСЯ и считаются (план: «где окна
// принимаются»); число печатается.
// Запуск: node u6_race.mjs --login-file=<логин:пароль>
import fs from 'node:fs';
import { chromium } from '../../../node_modules/playwright/index.mjs';

const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:8097';
const loginFile = (process.argv.find(a => a.startsWith('--login-file=')) || '').split('=')[1];
const [user, pass] = fs.readFileSync(loginFile, 'utf8').trim().split(':');
const results = [];
const check = (name, ok, detail = '') => { results.push(!!ok); console.log(`${ok ? 'прошло' : 'ПРОВАЛ'} ${name} ${detail}`); };

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
await context.addCookies([{ name: 'weco_consent', value: 'necessary', url: BASE }]);
const page = await context.newPage();
let dialogs = 0;
page.on('dialog', d => { dialogs += 1; d.accept(); });

await page.goto(BASE + '/login/');
await page.fill('input[name="username"]', user);
await page.fill('input[name="password"]', pass);
await Promise.all([page.waitForLoadState('networkidle'), page.click('form [type="submit"]')]);

await page.goto(BASE + '/olympiads/vseros/variant/562/?mode=free', { waitUntil: 'networkidle' });
await Promise.all([page.waitForURL('**/take/**'),
  page.locator('.om-mode', { hasText: 'Без времени' }).getByRole('button', { name: 'Начать' }).click()]);

// Ответ «Сдать задание» придерживаем, автосохранение отпускаем позже.
await page.route('**/item/', async route => {
  const response = await route.fetch({ maxRedirects: 0 });
  await new Promise(r => setTimeout(r, 3000));
  await route.fulfill({ response });
});
await page.route('**/autosave/', async route => {
  await new Promise(r => setTimeout(r, 1000));
  await route.continue();
});

for (const number of ['6', '7']) {
  if (!page.url().includes('/take/')) break;   // тур уже завершён — дефект У6
  await page.locator('.om-tn', { hasText: 'Задание ' + number }).click();
  const pane = page.locator('.om-taskpane:not([hidden])');
  await pane.locator('.om-sol__seg label', { hasText: 'Текст' }).click();
  await pane.locator('textarea.om-area').fill('Решение задания ' + number + ': считаем оптимум, p = 1.');
  await pane.getByRole('button', { name: 'Сдать задание' }).click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
}
const url = page.url();
check('после двух «Сдать задание» открыта страница заданий, а не результат', url.includes('/take/'), url.replace(BASE, ''));
const tabs = url.includes('/take/') ? await page.locator('.om-tn').allInnerTexts() : [];
const open = tabs.filter(t => !/ · (\d|сдано|решения нет|не проверено)/.test(t.split('\n')[0])).length;
check('открыты все задания, кроме двух сданных', tabs.length > 0 && open === tabs.length - 2, `открыто ${open} из ${tabs.length}`);
console.log(`нативных окон: ${dialogs}`);
await browser.close();
console.log(`итог: прошло ${results.filter(Boolean).length} / всего ${results.length}`);
process.exit(results.every(Boolean) ? 0 : 1);
