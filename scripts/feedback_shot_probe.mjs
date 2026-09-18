/* Проба кадра снимка обратной связи (ночь 18.09.2026, A1.1).

   Зачем: html2canvas снимал весь документ, и длинные страницы сервер не
   принимал. Какой набор ключей кадра даёт ровно видимую область — решает
   эта проба, а не память: на странице две полосы (синяя в самом верху,
   розовая на 2 010 px), страница прокручена на 2 000 px. Верный кадр —
   высотой с окно, с розовой полосой у верхнего края и без синей.

   Запуск: node scripts/feedback_shot_probe.mjs [порт]  (сервер уже поднят) */
import { chromium } from 'playwright';

const PORT = process.argv[2] || '8611';
const URL = 'http://127.0.0.1:' + PORT + '/catalog/';

/* Второй кандидат: клон документа прокручен как страница. */
const VARIANTS = {
  a: {},
  b: { scrollXFromPage: true },
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(URL, { waitUntil: 'load' });
let failed = false;
for (const [name, v] of Object.entries(VARIANTS)) {
  const r = await page.evaluate(async (v) => {
    const mk = (top, color) => {
      const d = document.createElement('div');
      d.style.cssText = 'position:absolute;left:0;width:100%;height:40px;z-index:99999;'
        + 'top:' + top + 'px;background:' + color;
      document.body.appendChild(d);
      return d;
    };
    document.body.style.minHeight = '4000px';
    const bands = [mk(0, '#0066ff'), mk(2010, '#ff0066')];
    window.scrollTo(0, 2000);
    const opts = weco.feedback.shotOptions();
    if (v.scrollXFromPage) { opts.scrollX = window.scrollX; opts.scrollY = window.scrollY; }
    const canvas = await html2canvas(document.documentElement, opts);
    const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.8));
    const img = await createImageBitmap(blob);
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const px = ctx.getImageData(Math.floor(img.width / 2), 20, 1, 1).data;
    const all = ctx.getImageData(0, 0, img.width, img.height).data;
    let blue = 0;
    for (let i = 0; i < all.length; i += 4) {
      if (all[i] < 40 && Math.abs(all[i + 1] - 0x66) < 40 && all[i + 2] > 215) blue++;
    }
    bands.forEach(b => b.remove());
    return { h: img.height, w: img.width, client: document.documentElement.clientHeight,
             px: [px[0], px[1], px[2]], blue };
  }, v);
  const pink = Math.abs(r.px[0] - 0xff) <= 40 && r.px[1] <= 40 && Math.abs(r.px[2] - 0x66) <= 40;
  const ok = r.h <= r.client + 2 && pink && r.blue === 0;
  console.log(`вариант ${name}: снимок ${r.w}×${r.h} (окно ${r.client}), пиксель строки 20 = rgb(${r.px}),`
    + ` синих пикселей ${r.blue} → ${ok ? 'ПРОШЁЛ' : 'не прошёл'}`);
  if (name === 'a' && !ok) failed = true;
}
/* Страницы, где Chrome отдаёт color-mix() как color(srgb …): до правки
   html2canvas падал на них целиком. Достаточно, что снимок вообще есть. */
for (const path of ['/catalog/problem/63315/', '/game/']) {
  await page.goto('http://127.0.0.1:' + PORT + path, { waitUntil: 'load' });
  const r = await page.evaluate(async () => {
    try {
      const c = await html2canvas(document.documentElement, weco.feedback.shotOptions());
      return c.width + '×' + c.height;
    } catch (e) { return 'ОШИБКА ' + e; }
  });
  console.log(path + ': ' + r);
  if (r.startsWith('ОШИБКА')) failed = true;
}
await browser.close();
process.exit(failed ? 1 : 0);
