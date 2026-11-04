// Разведка Э1: видимые тексты, прямоугольники и снимки исходного состояния.
import { chromium } from 'playwright';
import fs from 'node:fs';
const out = '.calc2-astra-local/e1-before';
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
await context.addInitScript(() => {
  localStorage.setItem('calc2.v1.answerHidden', '0');
  localStorage.setItem('theme', 'light');
});
const page = await context.newPage();
await page.goto((process.env.CALC2_BASE_URL || 'http://127.0.0.1:8113') + '/calc2/', { waitUntil: 'load' });
await page.waitForFunction(() => typeof pickScene === 'function' && typeof math !== 'undefined');
await page.evaluate(() => document.fonts.ready);
const scenes = 'ppf ppfsum tradeprice ceil quota consumer monoexport elast prod costs m-tangent mono-d1 m-minmax labor-bilat m-transform m-optimum'.split(' ');
for (const scene of scenes) {
  await page.evaluate(key => {
    resetSceneMemory(); pickScene(key);
    if (key === 'consumer') { STATE.consType = 'compl'; STATE.consA = 1; STATE.consB = 2; redrawAll(); }
    if (key === 'ceil') { setType('floor'); setPRegFields(50); redrawAll(); }
  }, scene);
  await page.waitForTimeout(700);
  const data = await page.evaluate(() => {
    const visible = e => e.getClientRects().length && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden';
    const box = e => { const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
    const txt = e => { const c=e.cloneNode(true); c.querySelectorAll('.katex-mathml').forEach(x=>x.remove());return c.textContent.trim(); };
    return {
      labels: [...document.querySelectorAll('#chart text')].filter(visible).map(e=>({text:txt(e),cls:e.getAttribute('class'),box:box(e)})),
      answer: [...document.querySelectorAll('#params-panel .stat, #params-panel .ans-cell')].filter(visible).map(e=>({text:txt(e),cls:e.className,w:e.clientWidth,sw:e.scrollWidth,html:e.outerHTML.slice(0,800)})),
      regulators: [...document.querySelectorAll('#tools-panel .reg-eq')].filter(visible).map(e=>({text:txt(e),html:e.innerHTML.slice(0,500)})),
      paths: [...document.querySelectorAll('#chart path[stroke]')].map(e=>({stroke:e.getAttribute('stroke'),clip:!!e.closest('[clip-path]'),cls:e.getAttribute('class'),d:e.getAttribute('d')?.slice(0,80)})),
    };
  });
  fs.writeFileSync(`${out}/${scene}.json`, JSON.stringify(data,null,2));
  await page.screenshot({ path: `${out}/${scene}.png` });
  console.log(scene + ': ' + JSON.stringify({overflow:data.answer.filter(x=>x.sw>x.w+1).map(x=>[x.text,x.w,x.sw]),labels:data.labels.filter(x=>x.cls!=='axis-num').map(x=>x.text),regulators:data.regulators.map(x=>x.text)}));
}
await browser.close();
