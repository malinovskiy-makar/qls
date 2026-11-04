// Регрессии V01–V05: связь обозначения с объектом, читаемость и мобильная прокрутка.
// Проверяем геометрию живого SVG, а не наличие CSS-строк в исходниках.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium, webkit } from 'playwright';

const engine = process.env.CALC2_VISUAL_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch();
const failures = [];
let screens = 0;
try {
  for (const width of [390, 1440]) for (const theme of ['light', 'dark']) {
    const page = await browser.newPage({viewport: {width, height: 900}, reducedMotion: 'reduce'});
    await page.addInitScript(t => localStorage.setItem('theme', t), theme);
    await page.goto(process.env.CALC2_BASE_URL + '/calc2/');
    await page.waitForFunction(() => typeof pickScene === 'function');
    const cookie = page.getByRole('button', {name: 'Только необходимые', exact: true});
    if (await cookie.isVisible()) await cookie.click();
    await page.evaluate(async () => {
      await Promise.all([...document.fonts].map(f => f.load().catch(() => null)));
      await document.fonts.ready;
    });
    for (const key of ['sd', 'taxes', 'ceil', 'quota', 'mono', 'labor', 'labor-mono', 'consumer', 'cons-slutsky', 'isoquant', 'm-optimum', 'mono-nat']) {
      await page.evaluate(key => {pickScene(key); redrawAll();}, key);
      await page.waitForTimeout(80);
      const found = await page.evaluate(() => {
        const bad = [];
        const chart = document.querySelector('#chart'), box = chart.getBoundingClientRect();
        const rect = e => e.getBoundingClientRect();
        const txt = e => e.getAttribute('data-raw') || e.firstChild?.textContent;
        const hit = (a, b, gap=0) => Math.min(a.right,b.right)-Math.max(a.left,b.left)>-gap && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>-gap;
        const labels = [...chart.querySelectorAll('text')].filter(e => rect(e).width>.5);
        for (const g of chart.querySelectorAll('g.legend')) {
          const swatches = [...g.querySelectorAll('rect')].slice(1);
          [...g.querySelectorAll('text')].forEach((t,i) => {
            if (!swatches[i]) return;
            const a=rect(t),b=rect(swatches[i]);
            if (Math.abs((a.top+a.bottom-b.top-b.bottom)/2)>4) bad.push('V01: legend row '+txt(t));
          });
        }
        for (const t of labels) {
          const r=rect(t);
          if (r.left<box.left-1 || r.right>box.right+1 || r.top<box.top-1 || r.bottom>box.bottom+1)
            bad.push('V03: clipped '+txt(t));
          if (t.__renameHit) {
            const target=rect(t.__renameHit);
            if (target.left>r.left || target.right<r.right || target.top>r.top || target.bottom<r.bottom)
              bad.push('rename target detached '+txt(t)+' '+JSON.stringify({label:r.toJSON(),target:target.toJSON()}));
          }
          if (!t.matches('.point-name')) continue;
          const names=_kpNames.filter(n=>n.sym===(t.getAttribute('data-raw')||t.textContent));
          if (!names.length) {bad.push('V02: missing point anchor '+txt(t)); continue;}
          const distance=Math.min(...names.map(n=>Math.hypot(Math.max(r.left-box.left-n.px,0,n.px-(r.right-box.left)),Math.max(r.top-box.top-n.py,0,n.py-(r.bottom-box.top)))));
          if (distance>18) bad.push('V02: detached '+txt(t)+' '+distance.toFixed(1)+'px');
        }
        const handles=[...chart.querySelectorAll('circle[data-service="handle"]')].filter(e=>rect(e).width>0);
        for (const t of labels.filter(e=>e.matches('.axis-num,.coord-num')))
          if (handles.some(h=>hit(rect(t),rect(h),1))) bad.push('V04: handle covers '+txt(t));
        const coords=labels.filter(e=>e.matches('.coord-num'));
        for (let i=0;i<coords.length;i++) for (const b of coords.slice(i+1))
          if (hit(rect(coords[i]),rect(b),3)) bad.push('V05: coordinate gap '+txt(coords[i])+' / '+txt(b));
        if (document.querySelector('footer,.site-version,.legal-footer')) bad.push('unexpected footer');
        if (innerWidth<760 && document.body.scrollHeight>document.body.clientHeight+1)
          bad.push('phone has a second scrolling body');
        if (document.documentElement.scrollWidth>innerWidth) bad.push('horizontal overflow');
        return bad;
      });
      failures.push(...found.map(detail=>({key,width,theme,detail})));
      if (key==='m-optimum') {
        const target=page.locator('#chart text').filter({hasText:/^max:/}).first();
        // WebKit's automation quads can retain the pre-layout SVG position.
        // Use the rendered DOM rectangle, then a real pointer double-click:
        // this still catches a detached hit target or an overlapping element.
        const a=await target.evaluate(node=>node.getBoundingClientRect().toJSON());
        await page.mouse.dblclick(a.x+a.width/2,a.y+a.height/2);
        const input=page.locator('#pt-rename');
        await input.waitFor({state:'visible'});
        const b=await input.boundingBox();
        if (!b || b.x<0 || b.x+b.width>width || Math.abs(a.y-b.y)>15)
          failures.push({key,width,theme,detail:'inline rename editor left its label'});
        await input.press('Escape');
      }
      screens++;
    }
    await page.close();
  }
} finally { await browser.close(); }
const report={screens,failures};
if (process.env.CALC2_VISUAL_OUT) fs.writeFileSync(process.env.CALC2_VISUAL_OUT,JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
assert.deepEqual(failures,[],'release visual regressions');
