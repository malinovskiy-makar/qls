import * as pw from 'playwright';import fs from 'node:fs';
import {keepAnswerOpen} from './answer_open.mjs';import {installShownReader} from './parse_shown.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
for(const engine of (process.env.ENGINES||'chromium,webkit').split(',')){
 const browser=await pw[engine].launch();keepAnswerOpen(browser);
 for(const width of (process.env.WIDTHS||'1440,1280').split(',').map(Number))for(const theme of (process.env.THEMES||'light,dark').split(',')){
  const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});
  await page.addInitScript(t=>localStorage.setItem('theme',t),theme);
  await page.goto(process.env.CALC2_BASE_URL+'/calc2/');await page.waitForFunction(()=>typeof addSecondTax==='function');await installShownReader(page);
  await page.evaluate(()=>{resetSceneMemory();pickScene('taxes');updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),'Q=180-P');updateCurveExpr(STATE.curves.find(c=>c.role==='supply'),'Q=3P-60');renderCurveList();setType('subsidy');setTaxForm('unit');setTaxSide('buyer');setTax(12);});
  await page.locator('#tax-add-second').click();
  const edit=page.locator('#tax2-value');await edit.click();await edit.fill('24');await edit.press('Enter');
  await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(500);
  const name=[engine,width,theme].join('/');
  const geometry=await page.evaluate(()=>{
   const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
   const svg=document.getElementById('chart'),box=svg.getBoundingClientRect();
   const axes=[...svg.querySelectorAll('text.coord-num')].filter(visible).filter(e=>{const r=e.getBoundingClientRect();return r.left<box.left+1||r.right>box.right-1||r.bottom>box.bottom-1;}).map(e=>e.textContent);
   const labels=[...svg.querySelectorAll('[data-tax-pair-wedge] text')].map(e=>({text:e.textContent,r:e.getBoundingClientRect().toJSON()}));
   const hits=[];for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++){const a=labels[i].r,b=labels[j].r;if(Math.min(a.right,b.right)>Math.max(a.left,b.left)&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top))hits.push([labels[i].text,labels[j].text]);}
   const root=document.getElementById('tax-pair-controls'),row=document.getElementById('tax-second-row');
   return{axes,hits,wide:document.documentElement.scrollWidth>innerWidth+1,controlOverflow:root.scrollWidth>root.clientWidth+1,
    addVisible:visible(document.getElementById('tax-add-second')),rate:STATE.taxSecond.rate,eq:STATE.taxEq,
    value:document.getElementById('tax2-value').textContent,katex:[...document.querySelectorAll('.katex-error')].filter(visible).map(e=>e.textContent),
    rowHeight:row.getBoundingClientRect().height,labels};
  });
  check(name+' настоящий ввод второй ставки',geometry.rate===24&&Math.abs(geometry.eq.Q-111)<1e-6,geometry);
  check(name+' третьего инструмента не предлагают',!geometry.addVisible,geometry);
  check(name+' панель помещается',!geometry.wide&&!geometry.controlOverflow,geometry);
  check(name+' обе подписи клиньев читаются',geometry.labels.length===2&&!geometry.hits.length,geometry);
  check(name+' все цены внутри холста',!geometry.axes.length,geometry.axes);
  check(name+' формулы без ошибок',!geometry.katex.length,geometry.katex);
  if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e4-shots',{recursive:true});await page.screenshot({path:'.calc2-astra-local/e4-shots/'+name.replaceAll('/','-')+'.png'});}
  if(width===1440&&theme==='light'){
   const drag=page.locator('[data-tax-pair-wedge="2"] [data-service="tax-pair-drag"]');
   const box=await drag.boundingBox(),delta=await page.evaluate(()=>sy(0)-sy(6));
   const stack=await page.evaluate(({x,y})=>document.elementsFromPoint(x,y).slice(0,5).map(e=>({tag:e.tagName,cl:e.getAttribute('class'),service:e.dataset.service})),{x:box.x+box.width/2,y:box.y+box.height/2});
   const x=Math.round(box.x+box.width/2),y=Math.round(box.y+box.height/2),endY=Math.round(y-delta);
   const expectedRate=24+(y-endY)*6/delta;
   await page.mouse.move(x,y);await page.mouse.down();
   await page.mouse.move(x,endY);await page.mouse.up();
   const moved=await page.evaluate(()=>({second:STATE.taxSecond.rate,first:STATE.tax}));
   check(name+' перетаскивание второго клина меняет только его',Math.abs(moved.second-expectedRate)<1e-6&&moved.first===12,{moved,expectedRate,box,delta,stack});
   // d3 отменяет случайный click сразу после drag до следующей задачи.
   await page.waitForTimeout(50);
   await page.locator('[data-tax2-bound=max]').click();
   const bound=page.locator('#tax2-field .param-editor .edval').nth(1);await bound.fill('500');await bound.press('Enter');
   check(name+' настоящая правка верхней границы',await page.evaluate(()=>STATE.taxSecond.bounds?.max===500&&document.getElementById('tax2-slider').max==='500'));
  }
  await page.locator('[data-tax2=form] [data-base=seller]').click();
  check(name+' форма обнуляет ставку',await page.evaluate(()=>STATE.taxSecond.form==='vat'&&STATE.taxSecond.rate===0));
  await page.locator('[data-tax2=type] [data-value=subsidy]').click();
  await page.locator('[data-tax2=form] [data-base=buyer]').click();
  await edit.click();await edit.fill('10');await edit.press('Enter');
  check(name+' каскад процентной субсидии',await page.evaluate(()=>STATE.taxSecond.form==='subbuyer'&&STATE.taxSecond.rate===10&&document.querySelector('[data-tax2-side]').hidden));
  await page.locator('#tax-remove-second').click();
  check(name+' строка удаляется',await page.evaluate(()=>!STATE.taxSecond&&!STATE.taxPair));
  await page.close();
 }
 await browser.close();
}
console.log(`Вид Э4: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
