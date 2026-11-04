import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium, webkit } from 'playwright';

const base = process.env.VP_POLISH_BASE, out = process.env.VP_POLISH_OUT;
const engine = process.env.VP_POLISH_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch();
const report = {screens:0, themeFrames:[], errors:[]};
const sizes = [[320,568],[375,667],[390,844],[430,932],[768,1024],[1024,768],[1280,720],[1366,768],[1440,800],[1920,1080]];
try {
  for (const signedIn of [false,true]) {
    const ctx = await browser.newContext();
    if (signedIn) await ctx.addCookies([{name:'sessionid',value:process.env.VP_POLISH_SESSION,url:base}]);
    const page = await ctx.newPage();
    page.on('pageerror', e => report.errors.push(String(e)));
    for (const theme of ['light','dark']) for (const [width,height] of sizes) {
      await page.setViewportSize({width,height});
      await page.goto(base+'/vp/');
      await page.evaluate(theme => {
        localStorage.setItem('theme',theme);
        if (theme==='dark') document.documentElement.dataset.theme='dark';
        else document.documentElement.removeAttribute('data-theme');
      },theme);
      const cookie = page.getByRole('button',{name:'Только необходимые',exact:true});
      if (await cookie.isVisible()) await cookie.click();
      await page.evaluate(() => document.fonts.ready);
      assert.equal(await page.locator('#vp-format-band').inputValue(),signedIn?'10':'11');
      const geometry = await page.evaluate(() => {
        const rect = e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,b:r.bottom,r:r.right,h:r.height};};
        return {sw:document.documentElement.scrollWidth,sh:document.documentElement.scrollHeight,
          actions:[...document.querySelector('.vp-land-cta').children].map(rect),
          band:[...document.querySelector('.vp-land-band').children].map(rect),
          probe:rect(document.querySelector('[data-open-probe]')),
          probeInBand:document.querySelector('[data-open-probe]').parentElement.matches('.vp-land-band'),
          labels:[...document.querySelectorAll('.vp-format-label')].map(rect)};
      });
      assert.ok(geometry.sw<=width,`horizontal overflow at ${width}: ${geometry.sw}`);
      assert.equal(geometry.actions.length,3,'hero keeps exactly three original actions');
      assert.ok(geometry.probeInBand,'answer checker belongs to the lower panel');
      assert.equal(geometry.band.length,signedIn?4:2);
      if (width>=1280) {
        assert.ok(geometry.sh<=height,`desktop vertical overflow: ${geometry.sh}`);
        assert.ok(Math.abs(geometry.actions[0].y-geometry.actions[1].y)<2);
        assert.ok(geometry.actions[2].y<geometry.actions[0].b);
        for (let i=1;i<geometry.actions.length;i++)
          assert.ok(geometry.actions[i-1].r+8<=geometry.actions[i].x,'hero actions must keep a visible gap');
        for (const cell of geometry.band) assert.ok(Math.abs(cell.y-geometry.probe.y)<2,'all lower-panel items share one row');
      }
      if (width===390) assert.ok(geometry.actions[0].b<height,'primary CTA below phone fold');
      for (const [i,a] of geometry.labels.entries()) for (const b of geometry.labels.slice(i+1))
        assert.ok(a.r<=b.x || b.r<=a.x || a.b<=b.y || b.b<=a.y,'composition labels overlap');
      if (signedIn && [390,1440].includes(width)) await page.screenshot({path:`${out}/${width}-${theme}.png`,fullPage:true});
      report.screens++;
    }
    await page.setViewportSize({width:390,height:844});
    await page.locator('#vp-format-band').selectOption('9');
    await page.waitForURL('**/vp/?band=9');
    assert.equal(await page.locator('.vp-format-facts strong').first().innerText(),'17');
    await page.reload();
    assert.equal(await page.locator('#vp-format-band').inputValue(),'9');
    await page.locator('[data-board-tab="11"]').click();
    await page.waitForURL('**/vp/?board=11');
    assert.equal(await page.locator('#vp-format-band').inputValue(),'11');
    const opener=page.locator('[data-open-probe]');
    await opener.click();
    assert.ok(await page.locator('#vp-probe-dialog').evaluate(e=>e.open));
    const dialogBox = await page.locator('#vp-probe-dialog').boundingBox();
    assert.ok(dialogBox.x >= 16 && Math.abs(dialogBox.x + dialogBox.width / 2 - 195) < 2,
      'probe dialog must be centered with phone edge spacing');
    assert.ok(Math.abs(dialogBox.y + dialogBox.height / 2 - 422) < 2,
      'probe dialog must be vertically centered');
    assert.equal(await page.locator('#vp-probe-out').innerText(),'');
    for (const [raw,expected] of [['37.5','37,5'],['1 200','1200'],['15%','15'],['3,125','3,13'],['-4,5','засчитают'],['37,50','засчитают']]) {
      await Promise.all([page.waitForResponse(r=>r.url().includes('/format/check/') && r.status()===200),page.locator(`[data-probe="${raw}"]`).click()]);
      await page.waitForFunction(expected=>document.querySelector('#vp-probe-out').textContent.includes(expected),expected);
    }
    await page.locator('#vp-probe-in').fill('42');
    await page.waitForFunction(()=>document.querySelector('#vp-probe').classList.contains('is-ok'));
    await page.locator('#vp-probe-help').click();
    assert.ok(await page.locator('#vp-probe-tip').isVisible());
    assert.ok((await page.locator('#vp-probe-tip').innerText()).includes('поэтому'));
    await page.keyboard.press('Escape');
    assert.ok(await page.locator('#vp-probe-dialog').evaluate(e=>e.open));
    await page.keyboard.press('Escape');
    assert.ok(await opener.evaluate(e=>e===document.activeElement));
    await opener.click();
    await page.setViewportSize({width:390,height:380});
    assert.ok(await page.locator('[data-close-probe]').isVisible());
    await page.locator('[data-close-probe]').click();
    await page.setViewportSize({width:1440,height:800});
    const frames=await page.evaluate(async()=>{
      const start=performance.now(),old=document.documentElement.getAttribute('data-theme');
      document.querySelector('#theme-toggle').click();
      const immediate=document.documentElement.getAttribute('data-theme')!==old;
      await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
      return {immediate,ms:performance.now()-start};
    });
    assert.ok(frames.immediate,'theme attribute delayed');report.themeFrames.push(frames.ms);
    // 1440×800 при масштабе браузера 200% даёт viewport 720×400 CSS px.
    // body.style.zoom не меняет media queries и неверно моделирует browser zoom.
    await page.setViewportSize({width:720,height:400});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'200% viewport overflow');
    await ctx.close();
  }
  const ctx = await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:844}});
  const page=await ctx.newPage();await page.goto(base+'/vp/?band=9');
  await page.locator('#vp-format-band').selectOption('10');
  await page.locator('#vp-format-apply').click();await page.waitForURL('**/vp/?band=10');
  assert.equal(await page.locator('#vp-format-band').inputValue(),'10');
  assert.ok((await page.locator('[data-open-probe]').getAttribute('href')).endsWith('/format/'));
  await ctx.close();
  assert.deepEqual(report.errors,[]);
  fs.writeFileSync(`${out}/report.json`,JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
} finally { await browser.close(); }
