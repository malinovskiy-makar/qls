// Снимки страниц раздела для У7/У8: node shot.mjs <папка> <ширина> <имя=путь>... [--login-file=…] [--dark]
// Путь может начинаться с «free:<комплект>:<задание>» — тогда сначала «Без времени» → «Начать».
// Нативное окно (alert/confirm/prompt) — провал (печатается).
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '../../../node_modules/playwright/index.mjs';

const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:8097';
const args = process.argv.slice(2);
const [dir, width] = args;
const login = (args.find(a => a.startsWith('--login-file=')) || '').split('=')[1];
const dark = args.includes('--dark');
const pages = args.slice(2).filter(a => !a.startsWith('--'));
const OUT = path.resolve(new URL('../shots/' + dir, import.meta.url).pathname);
fs.mkdirSync(OUT, { recursive: true });
const W = parseInt(width, 10);
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: W, height: W < 600 ? 844 : 900 },
  colorScheme: dark ? 'dark' : 'light', ...(W < 600 ? { isMobile: true, hasTouch: true } : {}) });
await context.addCookies([{ name: 'weco_consent', value: 'necessary', url: BASE }]);
const page = await context.newPage();
let native = 0;
page.on('dialog', d => { native += 1; d.dismiss(); });
if (login) {
  const [u, p] = fs.readFileSync(login, 'utf8').trim().split(':');
  await page.goto(BASE + '/login/');
  await page.fill('input[name="username"]', u);
  await page.fill('input[name="password"]', p);
  await Promise.all([page.waitForLoadState('networkidle'), page.click('form [type="submit"]')]);
}
for (const spec of pages) {
  const name = spec.slice(0, spec.indexOf('='));
  const target = spec.slice(spec.indexOf('=') + 1);
  if (target.startsWith('dispute:')) {
    // dispute:<комплект>:<задание>:<задача> — «Без времени», текст, «Сдать задание», спор.
    const [, kit, task, problem] = target.split(':');
    await page.goto(`${BASE}/olympiads/vseros/variant/${kit}/?mode=free`, { waitUntil: 'networkidle' });
    await Promise.all([page.waitForURL('**/take/**'),
      page.locator('.om-mode', { hasText: 'Без времени' }).getByRole('button', { name: 'Начать' }).click()]);
    const base = page.url().split('?')[0];
    await page.goto(base + '?task=' + task, { waitUntil: 'networkidle' });
    const pane = page.locator('.om-taskpane:not([hidden])');
    await pane.locator('.om-sol__seg label', { hasText: 'Текст' }).click();
    await pane.locator('textarea.om-area').fill('а) p* = 1, Альфа экспортирует 450. б) Бета покрывает остаток сама. в) Потребители проигрывают.');
    await Promise.all([page.waitForEvent('load'), pane.getByRole('button', { name: 'Сдать задание' }).click()]);
    await page.goto(`${base}?task=${task}&dispute=${problem}#dispute`, { waitUntil: 'networkidle' });
    await page.mouse.wheel(0, 900);
    await page.waitForTimeout(300);
  } else if (target.startsWith('free:')) {
    const [, kit, task] = target.split(':');
    await page.goto(`${BASE}/olympiads/vseros/variant/${kit}/?mode=free`, { waitUntil: 'networkidle' });
    await Promise.all([page.waitForURL('**/take/**'),
      page.locator('.om-mode', { hasText: 'Без времени' }).getByRole('button', { name: 'Начать' }).click()]);
    await page.goto(page.url().split('?')[0] + '?task=' + task, { waitUntil: 'networkidle' });
  } else {
    await page.goto(BASE + target, { waitUntil: 'networkidle' });
  }
  const file = path.join(OUT, `${name}-${W}${dark ? '-dark' : ''}.png`);
  await page.screenshot({ path: file, fullPage: !args.includes('--viewport') });
  console.log('снимок', file.replace(process.cwd() + '/', ''));
}
console.log('нативных окон:', native);
await browser.close();
