/* Проба корзины репетитора «Стола» (S5, 18.09.2026) на демо-репетиторе.
   Сначала: manage.py shell -c "exec(open('scripts/stol_demo_teacher.py', encoding='utf-8').read())"
   node scripts/stol_probe_basket.mjs [порт] */
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';

const PORT = process.argv[2] || '8000';
const BASE = 'http://127.0.0.1:' + PORT;
const PY = process.platform === 'win32' ? 'venv313\\Scripts\\python.exe' : 'venv313/bin/python';
const code = [
  'from django.contrib.sessions.backends.db import SessionStore',
  'from django.contrib.auth import get_user_model, BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY',
  "u = get_user_model().objects.get(username='stol-teacher@test.local')",
  's = SessionStore()', 's[SESSION_KEY] = str(u.pk)',
  "s[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'",
  's[HASH_SESSION_KEY] = u.get_session_auth_hash()', 's.create()', "print('KEY=' + s.session_key)",
].join('\n');
const key = execFileSync(PY, ['manage.py', 'shell', '-c', code], { encoding: 'utf8' }).match(/KEY=(\w+)/)[1];
const OUT = 'reports/stol_20260918/shots/';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addCookies([{ name: 'sessionid', value: key, url: BASE }]);
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
await page.goto(BASE + '/catalog/?topic=843', { waitUntil: 'load' });
await page.waitForTimeout(1000);
const rows = await page.$$eval('#ct-rows .rail-row', (rs) => rs.slice(0, 6).map((r) => ({
  id: r.dataset.id, check: !!r.querySelector('.rail-check'), status: !!r.querySelector('.rail-status'),
  hw: (r.querySelector('.rail-hw') || {}).textContent || '' })));
console.log('rows', JSON.stringify(rows));
for (const n of [1, 3, 5]) await page.click('#ct-rows .rail-row:nth-child(' + n + ') .rail-check');
const after = await page.evaluate(() => ({ path: location.pathname, bar: !document.getElementById('basket').hidden,
  n: document.getElementById('basket-n').textContent,
  checked: [...document.querySelectorAll('#ct-rows .rail-check[aria-checked="true"]')].length }));
console.log('after clicks', JSON.stringify(after));
await page.screenshot({ path: OUT + 's5_probe_basket.png' });
await page.click('#basket-count');
await page.waitForTimeout(200);
await page.screenshot({ path: OUT + 's5_probe_list.png' });
await page.click('#basket-hw-btn');
await page.waitForTimeout(200);
await page.screenshot({ path: OUT + 's5_probe_hw.png' });
await page.click('#basket-hw [data-hw]');
await page.waitForSelector('#basket-done:not([hidden])');
console.log('done', JSON.stringify(await page.evaluate(() => ({ t: document.getElementById('basket-done-t').textContent,
  bar: !document.getElementById('basket').hidden, hw: [...document.querySelectorAll('#ct-rows .rail-hw')].map((x) => x.textContent) }))));
await page.screenshot({ path: OUT + 's5_probe_done.png' });
await page.click('#basket-done-ok');
/* Задача: «+ В корзину» → «В корзине», полоса «Выбрано 1». */
await page.click('#ct-rows .rail-row:nth-child(2) .rail-title');
await page.waitForSelector('#stol-center .stm');
await page.click('#basket-toggle');
console.log('problem', JSON.stringify(await page.evaluate(() => ({ path: location.pathname,
  btn: document.getElementById('basket-toggle').textContent, n: document.getElementById('basket-n').textContent,
  how: !!document.getElementById('how') }))));
await page.screenshot({ path: OUT + 's5_probe_problem.png' });
await page.click('#basket-pdf');
await page.waitForURL('**/catalog/collection/**');
console.log('pdf', page.url(), (await page.title()));
console.log('errors', JSON.stringify(errors));
await browser.close();
