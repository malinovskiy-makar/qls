/* Проба карты «Стола» по прямому адресу: выбор = фильтр, Esc, «назад».
   node scripts/stol_probe_map2.mjs [порт] */
import { chromium } from 'playwright';

const PORT = process.argv[2] || '8000';
const OUT = 'reports/stol_20260918/shots/';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
await page.addInitScript(() => localStorage.setItem('weconomics.map.tour.v2', 'done'));
const base = 'http://127.0.0.1:' + PORT;
await page.goto(base + '/catalog/map/', { waitUntil: 'load' });
await page.waitForFunction(() => window.TMAP && TMAP.isReady(), null, { timeout: 30000 });
await page.waitForTimeout(1500);
const boot = await page.evaluate(() => { window.__probeBoot = Math.random(); return window.__probeBoot; });
console.log('direct', JSON.stringify(await page.evaluate(() => ({
  view: document.getElementById('stol-app').dataset.view, cls: document.getElementById('stol-app').className,
  title: document.title, count: document.getElementById('stol-map-count').textContent,
  show: document.getElementById('stol-map-show-l').textContent, reset: document.getElementById('tmap-reset').hidden,
  v: TMAP.view() }))));
await page.screenshot({ path: OUT + 's4_probe_direct_1280.png' });
/* Клик по ближней теме: берём тему с подписью в кадре. */
const pt = await page.evaluate(() => {
  const c = document.getElementById('tmap-canvas').getBoundingClientRect();
  const th = TMAP.nodes().filter((n) => n.k === 'theme' && n.pz > 0 && n.px > 300 && n.px < 850 && n.py > 150 && n.py < 600)
    .sort((a, b) => a.pz - b.pz)[0];
  return { x: c.left + th.px, y: c.top + th.py, l: th.l, db: th.db };
});
await page.mouse.move(pt.x, pt.y);
await page.waitForTimeout(300);
await page.mouse.click(pt.x, pt.y);
await page.waitForTimeout(1500);
console.log('picked', pt.l, JSON.stringify(await page.evaluate(() => ({
  topics: Array.from(weco.filters.state.topics), url: location.pathname + location.search,
  count: document.getElementById('stol-map-count').textContent, names: document.getElementById('stol-map-names').textContent,
  show: document.getElementById('stol-map-show-l').textContent,
  entryTotal: (document.querySelector('#ct-results [data-total]') || {}).dataset }))));
await page.screenshot({ path: OUT + 's4_probe_pick_1280.png' });
await page.mouse.move(640, 790);
await page.keyboard.press('Escape');
await page.waitForTimeout(2200);
console.log('esc', JSON.stringify(await page.evaluate(() => ({
  view: document.getElementById('stol-app').dataset.view, url: location.pathname + location.search,
  chip: (document.querySelector('[data-chip-label="topic"]') || {}).textContent, boot: window.__probeBoot }))));
await page.screenshot({ path: OUT + 's4_probe_after_esc_1280.png' });
await page.goBack();
await page.waitForTimeout(2200);
console.log('back→map', JSON.stringify(await page.evaluate(() => ({
  view: document.getElementById('stol-app').dataset.view, url: location.pathname + location.search, boot: window.__probeBoot,
  picked: TMAP.nodes().filter((n) => n.k === 'theme').length }))));
await page.goForward();
await page.waitForTimeout(2200);
console.log('fwd→entry', JSON.stringify(await page.evaluate(() => ({
  view: document.getElementById('stol-app').dataset.view, url: location.pathname + location.search, boot: window.__probeBoot }))));
console.log('boot kept', boot === await page.evaluate(() => window.__probeBoot));
console.log('errors', JSON.stringify(errors));
await browser.close();
