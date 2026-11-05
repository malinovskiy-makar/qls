/* Реальные запросы и поля: телефон, планшет, гибрид, компьютер и выключенный JS. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {chromium, webkit} from 'playwright';

const base=process.env.VP_KEYPAD_BASE;
const shots=process.env.VP_KEYPAD_SHOTS;
const report={touch:0,desktop:0,nojs:0};
const right=['37,5','25000','20','-0,12','1,61','0,67','3,13','1200,5','37,5','-0,13','7,25','-4,5'];
async function saved(page, action) {
  const [response]=await Promise.all([page.waitForResponse(r=>r.url().includes('/save/') && r.request().method()==='POST'),action()]);
  assert.equal(response.status(),200);
  return response.request().postDataJSON();
}
for(const engine of [chromium,webkit]) {
  const browser=await engine.launch();
  try {
    for(const [width,height,mobile] of [[320,700,true],[390,844,true],[1024,768,true],[810,1080,false]]) {
      const ctx=await browser.newContext({viewport:{width,height},hasTouch:true,isMobile:mobile});
      await ctx.addCookies([{name:'sessionid',value:process.env.VP_KEYPAD_SESSION,url:base}]);
      const page=await ctx.newPage();
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base+'/vp/format/');
      const panel=page.locator('#vp-number-keypad');
      const field=page.locator('#vp-drill-12');
      const key=k=>panel.locator(`[data-number-key="${k}"]`);
      const type=async text=>{for(const k of text)await key(k).tap();};
      assert.equal(await field.getAttribute('inputmode'),'none');
      assert.equal(await page.locator('[data-pm], [data-pm-drill]').count(),0);
      await field.tap();
      await type('-4,5');
      assert.equal(await field.inputValue(),'-4,5',engine.name()+' '+width);
      // Клавиши не вызывают blur/проверку каждого промежуточного знака.
      assert.equal((await page.locator('#vp-drill-out-12').innerText()).trim(),'–');
      await Promise.all([page.waitForResponse(r=>r.url().includes('/format/check/')),key('next').tap()]);
      await page.waitForFunction(()=>document.querySelector('#vp-drill-out-12').textContent==='Засчитают.');
      assert.equal(await panel.isVisible(),false);
      // Каретка, вставка, выделение и удаление в середине, затем лимит длины.
      await field.tap();
      await field.evaluate(e=>{e.focus();e.setSelectionRange(1,4);});
      await type('0,12');
      assert.equal(await field.inputValue(),'-0,12');
      await field.evaluate(e=>e.setSelectionRange(3,4));
      await key('delete').tap();
      assert.equal(await field.inputValue(),'-0,2');
      await field.evaluate(e=>e.setSelectionRange(0,0));await key('delete').tap();
      assert.equal(await field.inputValue(),'-0,2');
      await field.fill('1'.repeat(40));await key('9').tap();assert.equal((await field.inputValue()).length,40);
      await field.evaluate(e=>e.setSelectionRange(0,40));await key('5').tap();assert.equal(await field.inputValue(),'5');
      await key('hide').tap();assert.equal(await panel.isVisible(),false);
      await field.tap();assert.equal(await panel.isVisible(),true);
      await field.press('Escape');assert.equal(await panel.isVisible(),false);
      // Каждое из 12 чисел достижимо: кнопка «Далее» проверяет и переводит фокус.
      for(let i=1;i<=12;i++){
        const f=page.locator('#vp-drill-'+i);await f.fill('');await f.tap();await type(right[i-1]);
        await key('next').tap();
        await page.waitForFunction(n=>document.querySelector('[data-i="'+n+'"]').classList.contains('is-ok'),i);
        if(i<12)assert.equal(await page.locator(':focus').getAttribute('id'),'vp-drill-'+(i+1));
      }
      // С физической клавиатуры точка не заменяется и остаётся ошибкой ВШЭ.
      const first=page.locator('#vp-drill-1');await first.fill('37.5');await first.press('Enter');
      await page.waitForFunction(()=>document.querySelector('#vp-drill-out-1').textContent.includes('Точка вместо запятой'));
      await field.tap();await field.fill('-4,5');
      for(const theme of ['light','dark']) {
        await page.evaluate(t=>{localStorage.setItem('theme',t);},theme);
        await page.reload();
        await field.tap();await field.fill('-4,5');
        await page.waitForFunction(()=>document.activeElement.getBoundingClientRect().bottom<=document.querySelector('#vp-number-keypad').getBoundingClientRect().top);
        const layout=await page.evaluate(()=>{
          const p=document.querySelector('#vp-number-keypad').getBoundingClientRect();
          const f=document.activeElement.getBoundingClientRect();
          return {width:innerWidth,scroll:document.documentElement.scrollWidth,panel:p.width,top:p.top,fieldBottom:f.bottom,
            fieldTop:f.top,headerBottom:document.querySelector('.site-nav').getBoundingClientRect().bottom,
            buttons:[...document.querySelectorAll('#vp-number-keypad button')].map(b=>{const r=b.getBoundingClientRect();return {w:r.width,h:r.height};})};
        });
        assert.ok(layout.scroll<=layout.width+1,JSON.stringify(layout));
        assert.ok(layout.panel<=420 && layout.panel<=layout.width);
        assert.ok(layout.fieldBottom<=layout.top,JSON.stringify(layout));
        assert.ok(layout.fieldTop>=layout.headerBottom,JSON.stringify(layout));
        assert.ok(layout.buttons.every(b=>b.w>=44 && b.h>=44));
        await page.screenshot({animations:'disabled',path:`${shots}/${engine.name()}-${width}-${theme}.png`});
      }
      if(width===390) {
        await page.setViewportSize({width:844,height:390});
        await page.waitForFunction(()=>{
          const f=document.activeElement.getBoundingClientRect();
          return f.bottom<=document.querySelector('#vp-number-keypad').getBoundingClientRect().top &&
            f.top>=document.querySelector('.site-nav').getBoundingClientRect().bottom;
        });
        await page.screenshot({animations:'disabled',path:`${shots}/${engine.name()}-landscape.png`});
        await page.setViewportSize({width,height});
      }
      // Реальная попытка: каждая клавиша попадает в прежнее автосохранение.
      await page.goto(base+'/vp/a/kp-live/');
      const answer=page.locator('#vp-in-11');await answer.fill('');await answer.tap();await type('-0,12');
      await saved(page,()=>key('next').tap());
      assert.equal(await page.locator(':focus').getAttribute('id'),'vp-in-12');
      await page.reload();assert.equal(await answer.inputValue(),'-0,12');
      // Завершение ввода последнего числа не сдаёт вариант и не открывает подтверждение.
      const last=page.locator('#vp-in-18');await last.tap();await key('next').tap();
      assert.ok(page.url().includes('/vp/a/'));assert.equal(await panel.isVisible(),false);
      await page.locator('#vp-submit').click();assert.equal(await panel.isVisible(),false);
      // Дорешивание: число уходит на проверку, записанный балл не меняется.
      await page.goto(base+'/vp/r/kp-result/');
      const practice=page.locator('[data-practice][data-kind="number"]').first();
      const details=practice.locator('xpath=ancestor::details[1]');
      if(await details.count())await details.evaluate(e=>{e.open=true;});
      const opener=practice.locator('[data-practice-open]');
      if(await opener.isVisible())await opener.click();
      const raw=practice.locator('input[name="raw"]');await raw.tap();await type('-4,5');
      assert.equal(await key('next').textContent(),'Проверить');
      const [checked]=await Promise.all([page.waitForResponse(r=>r.url().includes('/practice-check/')),key('next').tap()]);
      assert.equal(checked.request().postDataJSON().raw,'-4,5');
      assert.equal(checked.status(),200);
      assert.deepEqual(errors,[]);
      report.touch++;await ctx.close();
    }
    for(const js of [true,false]) {
      const ctx=await browser.newContext({viewport:{width:1280,height:900},javaScriptEnabled:js});
      const page=await ctx.newPage();await page.goto(base+'/vp/format/');
      const field=page.locator('#vp-drill-12');await field.fill('-4,5');
      assert.equal(await field.getAttribute('inputmode'),'text');
      assert.equal(await page.locator('#vp-number-keypad').isVisible(),false);
      assert.equal(await page.locator('[data-pm-drill]').count(),0);
      if(js){await field.press('Enter');await page.waitForFunction(()=>document.querySelector('#vp-drill-out-12').textContent==='Засчитают.');report.desktop++;}
      else{await page.getByRole('button',{name:'Проверить все',exact:true}).click();assert.equal(await page.locator('#vp-drill-out-12').textContent(),'Засчитают.');report.nojs++;}
      await ctx.close();
    }
  }finally{await browser.close();}
}
fs.writeFileSync(`${shots}/checks.json`,JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
