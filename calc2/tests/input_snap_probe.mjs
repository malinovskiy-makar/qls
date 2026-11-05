/* Регрессии пользовательского контракта: реальные жесты, три раскладки,
   точный ввод, одна отмена, видимость ожидающих значений и бездействие после них. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {chromium,webkit} from 'playwright';
const args=process.argv.slice(2),arg=(k,d)=>{const i=args.indexOf('--'+k);return i<0?d:args[i+1];};
const engine=arg('browser','chromium'),width=+arg('width','1024'),height=+arg('height','850');
const theme=arg('theme','light'),touch=args.includes('--touch');
const out=path.resolve(arg('out','reports/input-snap'));fs.mkdirSync(out,{recursive:true});
const browser=await({chromium,webkit})[engine].launch();
const context=await browser.newContext({viewport:{width,height},hasTouch:touch,isMobile:touch,locale:'ru-RU'});
const page=await context.newPage(),report={engine,width,height,theme,touch,checks:[],errors:[]};
page.on('pageerror',e=>report.errors.push(e.message));
const check=(name,ok,data)=>{report.checks.push({name,ok,data});assert(ok,name+': '+JSON.stringify(data));};
const near=(a,b,t=1e-8)=>Math.abs(a-b)<t;
const settled=()=>page.waitForFunction(()=>!InputSnap.active&&!TaxMotion.pending);
async function motion(selector,from=.31,to=.4673){
 const sl=page.locator(selector);await sl.scrollIntoViewIfNeeded();const b=await sl.boundingBox();assert(b);
 const point=t=>({x:b.x+8+(b.width-16)*t,y:b.y+b.height/2});
 const start=point(from),end=point(to);
 if(touch&&engine==='chromium'){
  const cdp=await context.newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]});
  for(let i=1;i<=24;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:start.x+(end.x-start.x)*i/24,y:start.y}]});
  return async()=>{await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach();};
 }
 await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:24});
 return()=>page.mouse.up();
}
try{
 await page.goto((process.env.CALC2_BASE_URL||'http://127.0.0.1:8147')+'/calc2/?m=taxes',{waitUntil:'networkidle'});
 await page.evaluate(async theme=>{
  await document.fonts.ready;document.documentElement.dataset.theme=theme;setAnswerHidden(false);setToolsOpen(true);
  setTax(20);historyClearAll();historyBaseline();
 },theme);
 const cookie=page.getByRole('button',{name:'Только необходимые'});if(await cookie.isVisible())await cookie.click();
 await page.waitForTimeout(250);
 const steps=await page.evaluate(()=>[1,10,100,1000].map(v=>InputSnap.step(v)));
 check('automatic scale examples',JSON.stringify(steps)==='[0.01,0.1,1,10]',steps);
 await page.evaluate(()=>{
  window.__snapFrames=[];window.__snapInputs=[];window.__record=true;
  const rect=()=>{const e=document.querySelector('#graph-wrap').getBoundingClientRect();return[e.x+scrollX,e.y+scrollY,e.width,e.height,sx(0),sy(0)];};
  window.__startRect=rect();const loop=t=>{if(__record){__snapFrames.push({t,rect:rect()});requestAnimationFrame(loop);}};requestAnimationFrame(loop);
  document.getElementById('tax-slider').addEventListener('input',e=>{
   __snapInputs.push({value:STATE.tax,q:STATE.taxEq?.Q,at:performance.now()});
  });
 });
 const up=await motion('#tax-slider');
 await page.waitForTimeout(800); // Дольше таймера истории; палец/мышь ещё держит ручку.
 const held=await page.evaluate(()=>({tax:STATE.tax,active:InputSnap.active,pending:TaxMotion.pending,
  undo:histOf().undo.length,rect:__snapFrames.at(-1)?.rect,initial:__startRect,
  strip:[...document.querySelectorAll('#ans-strip b')].map(el=>({color:getComputedStyle(el).color,
   loader:!!el.querySelector('.calc-value-loader'),display:el.querySelector('.calc-value-loader')&&getComputedStyle(el.querySelector('.calc-value-loader')).display})),
  stripDisplay:getComputedStyle(document.querySelector('#ans-strip')).display,
  samples:__snapInputs,frames:__snapFrames}));
 report.held=held;check('continuous during held gesture',held.active&&held.pending&&Math.abs(held.tax-Math.round(held.tax))>1e-3,held.tax);
 check('no history split while held',held.undo===0,held.undo);
 check('graph reacts in each input',held.samples.length>5&&held.samples.every(r=>near(r.q,(100-r.value)/2)),held.samples.length);
 check('strip numbers masked and animated',held.strip.length>0&&held.strip.every(r=>r.color==='rgba(0, 0, 0, 0)'&&r.loader&&r.display==='block'),held.strip);
 const drift=held.frames.map(f=>f.rect.map((v,i)=>Math.abs(v-held.initial[i]))).flat();
 check('no layout or axis drift during gesture',Math.max(...drift)<.05,Math.max(...drift));
 await page.screenshot({path:path.join(out,'pending.png')});
 await up();await settled();await page.evaluate(()=>{__record=false;});
 const end=await page.evaluate(()=>({tax:STATE.tax,sl:+document.getElementById('tax-slider').value,undo:histOf().undo.length}));
 check('nearest whole tax after release',near(end.tax,Math.round(held.tax)),{held:held.tax,end});
 await page.waitForTimeout(750);
 check('one undo including snap',await page.evaluate(()=>histOf().undo.length===1));
 await page.evaluate(()=>historyUndo());check('undo restores prior tax',near(await page.evaluate(()=>STATE.tax),20));
 await page.evaluate(()=>historyRedo());check('redo restores final tax',near(await page.evaluate(()=>STATE.tax),end.tax));
 // Ввод через тот же редактор числа, которым пользуется человек.
 await page.locator('#tax-field .reg-eq').click();
 const editor=page.locator('#tax-field input.param-eq-input');
 await editor.fill('73.4689');await editor.press('Enter');await settled();await page.waitForTimeout(400);
 check('manual exact tax survives release and idle',near(await page.evaluate(()=>STATE.tax),73.4689));
 await page.locator('#tax-slider').focus();await page.keyboard.press('ArrowRight');await settled();
 check('keyboard uses auto step',near(await page.evaluate(()=>STATE.tax),74));
 await page.emulateMedia({reducedMotion:'reduce'});
 const release=await motion('#tax-slider',.4,.5137);await release();await settled();
 check('reduced motion no infinite animations',await page.evaluate(()=>document.getAnimations().every(a=>a.effect?.getTiming().iterations!==Infinity)));
 await page.emulateMedia({reducedMotion:'no-preference'});
 // MC: и ползунок сдвига, и сама линия используют ту же сетку.
 await page.evaluate(()=>{pickScene('mono');setToolsOpen(true);});await page.waitForTimeout(200);
 const mc=await page.evaluate(()=>mcDragCurve().id),selector='[data-cid="'+mc+'"] input[type=range]';
 const mcUp=await motion(selector,.51,.6173);const mid=await page.locator(selector).inputValue();await mcUp();await settled();
 const mcEnd=await page.evaluate(()=>({b:mcDragCurve().linear.b,base:curveShiftBase(mcDragCurve())}));
 check('MC slider finishes on auto grid',near(mcEnd.b-mcEnd.base,Math.round(+mid)),{mid,mcEnd});
 await page.locator('#chart').scrollIntoViewIfNeeded();
 const raw=await page.evaluate(()=>{const c=mcDragCurve();return {x:sx(20),y:sy(evalCurve(c,20)),to:sy(evalCurve(c,20)+13.468),left:document.querySelector('#chart').getBoundingClientRect().left,top:document.querySelector('#chart').getBoundingClientRect().top};});
 await page.mouse.move(raw.left+raw.x,raw.top+raw.y);await page.mouse.down();await page.mouse.move(raw.left+raw.x,raw.top+raw.to,{steps:20});await page.mouse.up();await settled();
 const mcGraph=await page.evaluate(()=>({b:mcDragCurve().linear.b,base:curveShiftBase(mcDragCurve()),active:InputSnap.active}));
 check('MC graph handle finishes on same grid',near(mcGraph.b-mcGraph.base,Math.round(mcGraph.b-mcGraph.base)),mcGraph);
 await page.locator('[data-cid="'+mc+'"] .reg-eq').click();
 const mcEditor=page.locator('[data-cid="'+mc+'"] input.param-eq-input');await mcEditor.fill('13.4689');await mcEditor.press('Enter');await page.waitForTimeout(300);
 check('manual exact MC shift preserved',await page.evaluate(()=>Math.abs(mcDragCurve().linear.b-curveShiftBase(mcDragCurve())-13.4689)<1e-9));
 await page.screenshot({path:path.join(out,'settled.png')});
 check('no browser errors',!report.errors.length,report.errors);
}finally{
 fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));await browser.close();
}
console.log(JSON.stringify({engine,width,height,theme,touch,checks:report.checks.length}));
