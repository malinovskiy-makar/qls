/* Обрезка аватара в настоящем браузере (24.09.2026).

   Зачем: на бою после выбора любой картинки `#pf-crop-img` получал
   `scale(0)` — окно мерилось, пока <dialog> ещё закрыт, и круг шириной 0
   давал нулевой масштаб. Юнит-тест этого не видит: нужны настоящая раскладка
   и настоящий <dialog>. Решение «зелёный/красный» принимает
   `problems/tests/test_profile_crop_browser.py`.

   Печатает одну строку `###CROP-JSON###{...}`: по ключу на ширину окна.
   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся. */
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

const BASE = process.env.CROP_BASE_URL || 'http://127.0.0.1:8000';
const SESSION = process.env.CROP_SESSION || '';
const PNG = readFileSync(process.env.CROP_PNG);
const WIDTHS = [1440, 390];

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

const out = {};
for (const width of WIDTHS) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 760 ? 844 : 900 } });
  const host = new URL(BASE).hostname;
  await ctx.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const row = { errors };
  try {
    await page.goto(BASE + '/profile/?tab=data', { waitUntil: 'load' });
    /* До выбора файла закрытое окно не должно занимать место (телефон:
       display:flex из медиазапроса перебивал скрытие закрытого <dialog>). */
    row.closedDisplay = await page.$eval('#pf-crop', d => getComputedStyle(d).display);
    await page.setInputFiles('#pf-ava-file', { name: 'foto.png', mimeType: 'image/png', buffer: PNG });
    await page.waitForSelector('#pf-crop[open]');
    await page.waitForFunction(() => {
      const t = getComputedStyle(document.getElementById('pf-crop-img')).transform;
      return t && t !== 'none';
    });
    Object.assign(row, await page.evaluate(() => {
      const img = document.getElementById('pf-crop-img');
      const m = new DOMMatrixReadOnly(getComputedStyle(img).transform);
      const a = img.getBoundingClientRect();
      const h = document.getElementById('pf-crop-hole').getBoundingClientRect();
      return {
        scale: m.a,
        hole: h.width,
        /* Картинка целиком покрывает круг: допуск в полпикселя на округление. */
        covers: a.left <= h.left + 0.5 && a.top <= h.top + 0.5
          && a.right >= h.right - 0.5 && a.bottom >= h.bottom - 0.5,
      };
    }));
    const [response] = await Promise.all([
      page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/profile/')),
      page.click('#pf-crop-save'),
    ]);
    row.postStatus = response.status();
    await page.waitForLoadState('load');
    row.finalUrl = page.url();
  } catch (e) {
    row.fail = String(e && e.message || e);
  }
  out[width] = row;
  await ctx.close();
}
await browser.close();
console.log('###CROP-JSON###' + JSON.stringify(out));
