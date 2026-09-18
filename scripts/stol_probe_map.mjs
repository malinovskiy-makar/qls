/* Проба перехода «вход ↔ карта» (README §6, 18.09.2026): кадры по времени и
   состояние камеры. node scripts/stol_probe_map.mjs [порт] [ширина] [dark]
   Снимки — reports/stol_20260918/shots/s4_probe_*.png */
import { chromium } from 'playwright';

const PORT = process.argv[2] || '8000';
const WIDTH = Number(process.argv[3] || 1440);
const DARK = process.argv[4] === 'dark';
const OUT = 'reports/stol_20260918/shots/';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: WIDTH, height: 900 }, colorScheme: DARK ? 'dark' : 'light' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
if (DARK) await page.addInitScript(() => localStorage.setItem('theme', 'dark'));
await page.addInitScript(() => localStorage.setItem('weconomics.map.tour.v2', 'done'));
await page.goto('http://127.0.0.1:' + PORT + '/catalog/?topic=843', { waitUntil: 'load' });
await page.waitForFunction(() => {
  const h = document.getElementById('stol-bg').__tmapPreview;
  return h && h.stats().state === 'live';
}, null, { timeout: 30000 });
await page.waitForTimeout(500);
const tag = WIDTH + (DARK ? '_dark' : '');
await page.screenshot({ path: OUT + 's4_probe_' + tag + '_0entry.png' });
await page.click('#se-map');
const t0 = Date.now();
for (const ms of [150, 500, 800, 1250, 2000, 3500]) {
  await page.waitForTimeout(Math.max(0, ms - (Date.now() - t0)));
  const v = await page.evaluate(() => window.TMAP ? TMAP.view() : null);
  console.log('enter', ms, JSON.stringify(v));
  await page.screenshot({ path: OUT + 's4_probe_' + tag + '_1enter_' + ms + '.png' });
}
console.log('state', JSON.stringify(await page.evaluate(() => ({
  view: document.getElementById('stol-app').dataset.view, cls: document.getElementById('stol-app').className,
  url: location.pathname + location.search, count: document.getElementById('stol-map-count').textContent,
  names: document.getElementById('stol-map-names').textContent,
  scrollW: document.documentElement.scrollWidth, innerW: innerWidth }))));
await page.click('.tmap-back');
const t1 = Date.now();
for (const ms of [300, 900, 1800]) {
  await page.waitForTimeout(Math.max(0, ms - (Date.now() - t1)));
  await page.screenshot({ path: OUT + 's4_probe_' + tag + '_2leave_' + ms + '.png' });
}
console.log('back', JSON.stringify(await page.evaluate(() => ({
  view: document.getElementById('stol-app').dataset.view, url: location.pathname + location.search,
  bg: document.getElementById('stol-bg').__tmapPreview.stats().state }))));
console.log('errors', JSON.stringify(errors));
await browser.close();
