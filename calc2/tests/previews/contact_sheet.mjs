/* Контактный лист превью моделей (ADR 0141): все рабочие модели экрана выбора
   на одном листе, светлая и тёмная тема. Превью рисует сама страница
   (pickerPreviewSvg из 95-picker-screen.js), колодец — цвет холста, как на
   экране выбора.

   node calc2/tests/previews/contact_sheet.mjs [папка]   (по умолчанию reports/calc2_picker) */
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import { ROOT, BASE } from '../tex/lib.mjs';

const OUT = path.resolve(process.argv[2] || path.join(ROOT, 'reports', 'calc2_picker'));
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
for (const theme of ['light', 'dark']) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  await ctx.addInitScript((t) => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
  const page = await ctx.newPage();
  await page.goto(BASE + '/calc2/', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof pickerPreviewSvg === 'function' && document.querySelector('#scene-picker .pk-pv'));
  const n = await page.evaluate((th) => {
    const sheet = document.createElement('div');
    sheet.id = 'pv-sheet';
    sheet.style.cssText = 'position:fixed;inset:0;z-index:9999;overflow:auto;background:var(--bg);padding:24px;font:13px/1.3 system-ui;color:var(--text);display:grid;grid-template-columns:repeat(7,1fr);gap:12px;align-content:start';
    const cap = document.createElement('div');
    cap.style.cssText = 'grid-column:1/-1;font-size:16px;font-weight:600';
    cap.textContent = 'Превью моделей из записи при рисовании · тема: ' + (th === 'dark' ? 'тёмная' : 'светлая');
    sheet.appendChild(cap);
    const cards = [...document.querySelectorAll('#scene-picker .scard:not(.soon):not([disabled])')];
    cards.forEach(c => {
      const cell = document.createElement('div');
      const well = document.createElement('div');
      well.style.cssText = 'height:118px;padding:8px 10px;background:var(--canvas);border:1px solid var(--border-soft);border-radius:10px;display:flex';
      const svg = pickerPreviewSvg(c.dataset.scene);
      svg.style.cssText = 'width:100%;height:100%;display:block;overflow:visible';
      well.appendChild(svg);
      const nm = document.createElement('div');
      nm.style.cssText = 'margin-top:4px';
      nm.textContent = c.dataset.scene + ' · ' + ((c.querySelector('.scard-name') || {}).textContent || '').trim();
      cell.append(well, nm);
      sheet.appendChild(cell);
    });
    document.body.appendChild(sheet);
    return cards.length;
  }, theme);
  const h = await page.evaluate(() => document.getElementById('pv-sheet').scrollHeight);
  await page.setViewportSize({ width: 1440, height: h });
  await page.screenshot({ path: path.join(OUT, 'previews_contact_' + theme + '.png') });
  console.log(theme + ': превью ' + n);
  await ctx.close();
}
await browser.close();
