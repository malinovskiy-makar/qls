// Длинные точные координаты естественной монополии: шрифт, рамки и зазоры.
import * as pw from 'playwright';
let total = 0, bad = 0;
const check = (name, ok, detail) => {total++; if (!ok) bad++; console.log((ok ? 'OK ' : 'FAIL ') + name + (ok ? '' : ' ' + JSON.stringify(detail)));};
for (const engine of ['chromium', 'webkit']) {
  const browser = await pw[engine].launch();
  for (const width of [1440, 1280, 390]) for (const theme of ['light', 'dark']) for (const motion of ['reduce', 'no-preference']) {
    const page = await browser.newPage({viewport: {width, height: 900}, reducedMotion: motion});
    await page.addInitScript(t => localStorage.setItem('theme', t), theme);
    await page.goto(process.env.CALC2_BASE_URL + '/calc2/?m=mono-nat');
    await page.waitForFunction(() => typeof redrawAll === 'function');
    await page.evaluate(async () => {await Promise.all([...document.fonts].map(f => f.load().catch(() => null))); await document.fonts.ready;});
    await page.waitForTimeout(350);
    const r = await page.evaluate(() => {
      const chart = document.getElementById('chart'), box = chart.getBoundingClientRect();
      const labels = [...chart.querySelectorAll('text.coord-num')].map(t => {
        const b = t.getBoundingClientRect();
        return {text: t.textContent, x: b.x - box.x, y: b.y - box.y, w: b.width, h: b.height,
          size: parseFloat(getComputedStyle(t).fontSize), target: +t.getAttribute('font-size')};
      });
      const outside = labels.filter(b => b.x < 0 || b.y < 0 || b.x + b.w > box.width || b.y + b.h > box.height);
      const overlap = labels.flatMap((a, i) => labels.slice(i + 1).filter(b => Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 1 && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 1).map(b => [a.text, b.text]));
      return {count: labels.length, outside, overlap, sizes: labels.map(b => [b.size, b.target])};
    });
    const name = [engine, width, theme, motion].join('/');
    check(name + ' шесть точных координат внутри холста', r.count === 6 && !r.outside.length, r);
    check(name + ' подписи не пересекаются', !r.overlap.length, r.overlap);
    check(name + ' окончательный кегль', r.sizes.every(([a, b]) => Math.abs(a - b) < .01), r.sizes);
    await page.close();
  }
  await browser.close();
}
console.log(`Natural labels: ${total - bad}/${total}, ошибок ${bad}`);
process.exitCode = bad ? 1 : 0;
