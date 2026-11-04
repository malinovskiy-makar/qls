/* Второй тур: реальные демоверсии 9/10/11, экран и сохранение сценариев R. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const base = process.env.VP_TOUR2_BASE;
const codes = JSON.parse(process.env.VP_TOUR2_CODES);
const shots = process.env.VP_TOUR2_SHOTS;
const browser = await chromium.launch({headless:true});
const report = {screens:0, controls:[], views:[]};
async function context(touch) {
  const ctx = await browser.newContext({
    viewport:touch ? {width:390,height:844} : {width:1280,height:900},
    isMobile:touch, hasTouch:touch,
  });
  await ctx.addCookies([{name:'sessionid',value:process.env.VP_TOUR2_SESSION,url:base}]);
  return ctx;
}
async function loaded(page, band) {
  await page.goto(`${base}/vp/a/${codes[band]}/`);
  await page.locator('#vp-in-11').waitFor();
  await page.waitForFunction(() => document.querySelectorAll('.katex').length > 0);
  await page.evaluate(() => document.fonts.ready);
}
async function saved(page, action) {
  const [response] = await Promise.all([
    page.waitForResponse(r=>r.url().includes('/save/') && r.request().method()==='POST'), action(),
  ]);
  assert.equal(response.status(),200);
  return response.request().postDataJSON();
}
try {
  for (const band of ['9','10','11']) {
    for (const touch of [false,true]) {
      const ctx = await context(touch);
      const page = await ctx.newPage();
      page.on('dialog', dialog=>{ throw new Error('Unexpected native dialog: '+dialog.type()); });
      await loaded(page,band);
      if (band==='10' && !touch) {
        const radio=page.locator('#vp-item-4 input[type=radio]').first();
        await saved(page,()=>radio.click());
        assert.equal(await radio.isChecked(),true);
        const removed=await saved(page,()=>radio.click());
        const row=removed.answers.find(answer=>answer.item===4);
        assert.ok(row && !Object.hasOwn(row.raw,'1'), 'Removed choice leaked into autosave');
        assert.equal(await radio.isChecked(),false);
        await page.locator('[data-flag="7"]').click();
        await page.locator('[data-flag="12"]').click();
        await page.reload();
        assert.equal(await page.locator('#vp-item-4 input:checked').count(),0);
        for (const n of [7,12]) assert.equal(await page.locator(`[data-flag="${n}"]`).getAttribute('aria-pressed'),'true');
        report.controls.push('deselect_saved','flags_persist');
      }
      if (band==='10' && touch) {
        const field=page.locator('#vp-in-11');
        const sign=page.locator('[data-pm="11"]');
        assert.equal(await sign.isVisible(),true);
        await field.fill('0,12');
        await saved(page,()=>sign.click());
        assert.equal(await field.inputValue(),'-0,12');
        await saved(page,()=>sign.click());
        assert.equal(await field.inputValue(),'0,12');
        await saved(page,()=>sign.click());
        await page.reload();
        assert.equal(await field.inputValue(),'-0,12');
        report.controls.push('touch_sign_saved');
      }
      for (const theme of ['light','dark']) {
        // Product theme toggle is hidden in the phone header; use the same
        // persisted preference that a pupil selects before entering a variant.
        await page.evaluate(value=>{localStorage.setItem('theme',value);},theme);
        await page.reload();
        await page.waitForFunction(value=>(document.documentElement.dataset.theme || 'light')===value,theme);
        await page.waitForFunction(() => document.querySelectorAll('.katex').length > 0);
        await page.evaluate(() => document.fonts.ready);
        await page.locator('#vp-in-11').scrollIntoViewIfNeeded();
        const view=await page.evaluate(()=>({
          width:innerWidth,contentWidth:document.documentElement.scrollWidth,
          errors:document.querySelectorAll('.katex-error').length,
          numbers:[...document.querySelectorAll('section.vp-item')].map(e=>e.id),
        }));
        assert.equal(view.errors,0,`${band} KaTeX errors`);
        assert.ok(view.contentWidth<=view.width+1,`${band} horizontal overflow`);
        assert.equal(view.numbers.length,band==='9'?17:18);
        assert.equal(new Set(view.numbers).size,view.numbers.length);
        const file=`${band}-${touch?'phone':'desktop'}-${theme}.png`;
        await page.screenshot({path:`${shots}/${file}`});
        report.views.push({band,touch,theme,...view,file});report.screens++;
      }
      if (band === '11' && !touch) {
        for (const width of [768, 1024]) {
          await page.setViewportSize({width, height:1024});
          const clipped = await page.evaluate(() => {
            const canvas = document.createElement('canvas');
            const measure = canvas.getContext('2d');
            return [...document.querySelectorAll('.vp-gaprow select')].flatMap(select => {
              const style = getComputedStyle(select);
              measure.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
              const available = select.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
              return [...select.options].filter(option => measure.measureText(option.text).width > available + 1)
                .map(option => ({id:select.id, text:option.text, available}));
            });
          });
          assert.deepEqual(clipped, [], `Gap choices clipped at ${width}px`);
        }
      }
      await ctx.close();
    }
  }
  // A real completed attempt catches truncation of TeX in the result lead.
  const resultContext = await context(false);
  const resultPage = await resultContext.newPage();
  await loaded(resultPage,'11');
  await resultPage.locator('#vp-submit').click();
  await resultPage.locator('#vp-confirm').click();
  await resultPage.waitForURL(`**/vp/r/${codes['11']}/`);
  assert.equal(await resultPage.locator('#z16 .vp-zlead').textContent(),
    'В закрытой экономике функция совокупного потребления домохозяйств имеет вид…');
  await resultPage.locator('a[data-z="16"]').click();
  await resultPage.waitForFunction(() => document.querySelectorAll('#z16 .katex').length > 0);
  assert.equal(await resultPage.locator('.katex-error').count(),0);
  await resultPage.locator('#z16').scrollIntoViewIfNeeded();
  await resultPage.screenshot({path:`${shots}/11-result-math.png`});
  report.result={mathLeadIntact:true,fullFormulaRendered:true,file:'11-result-math.png'};
  await resultPage.setViewportSize({width:768, height:1024});
  for (const path of ['/vp/my/', '/vp/vp-2tur-2026-demo-11/']) {
    await resultPage.goto(base + path);
    const columns = await resultPage.evaluate(() => {
      const positions = row => [...row.children].filter(e => getComputedStyle(e).display !== 'none')
        .map(e => ({x:e.getBoundingClientRect().x, width:e.getBoundingClientRect().width}));
      return {head:positions(document.querySelector('.vp-arow.is-head')),
        row:positions(document.querySelector('.vp-arow:not(.is-head)'))};
    });
    assert.equal(columns.head.length, columns.row.length, `History columns differ at ${path}`);
    columns.head.forEach((column, index) => {
      assert.ok(Math.abs(column.x - columns.row[index].x) <= 2, `History heading misaligned at ${path}, column ${index}`);
    });
  }
  await resultContext.close();
  fs.writeFileSync(`${shots}/checks.json`,JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
