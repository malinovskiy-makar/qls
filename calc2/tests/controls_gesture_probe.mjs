/* Настоящие мышь/касание: общий слайдер и ранее отдельные ручки на графике. */
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import{chromium,webkit}from'playwright';
const args=process.argv.slice(2),arg=(k,d)=>{const i=args.indexOf('--'+k);return i<0?d:args[i+1];};
const engine=arg('browser','chromium'),width=+arg('width','1024'),height=+arg('height','768'),touch=args.includes('--touch');
const out=path.resolve(arg('out','reports/controls-gestures'));fs.mkdirSync(out,{recursive:true});
const browser=await({chromium,webkit})[engine].launch(),context=await browser.newContext({viewport:{width,height},hasTouch:touch,isMobile:touch,locale:'ru-RU'}),page=await context.newPage();
const report={engine,width,height,touch,checks:[],errors:[]},check=(name,ok,data)=>{report.checks.push({name,ok:!!ok,data});assert(ok,name+': '+JSON.stringify(data));};
page.on('pageerror',e=>report.errors.push(e.message));
const settled=()=>page.waitForFunction(()=>!TaxMotion.pending&&!InputSnap.active,null,{timeout:20000});
let cdp;
async function gesture(from,to){
 if(touch&&engine==='chromium'){
  cdp=await context.newCDPSession(page);await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[from]});
  for(let i=1;i<=24;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:from.x+(to.x-from.x)*i/24,y:from.y+(to.y-from.y)*i/24}]});
  return async()=>{await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach();};
 }
 await page.mouse.move(from.x,from.y);await page.mouse.down();await page.mouse.move(to.x,to.y,{steps:24});return()=>page.mouse.up();
}
try{
 await page.goto((process.env.CALC2_BASE_URL||'http://127.0.0.1:8153')+'/calc2/?m=sdsum',{waitUntil:'networkidle'});
 await page.evaluate(async()=>{await document.fonts.ready;setAnswerHidden(false);setToolsOpen(true);});
 const cookie=page.getByRole('button',{name:'Только необходимые'});if(await cookie.isVisible())await cookie.click();
 for(const key of arg('models','sdsum,consumer,ineq,elast,ppf,plants').split(',')){
  await page.evaluate(k=>{InputSnap.cancel();TaxMotion.cancel();cancelRangeAnim();resetSceneMemory();pickScene(k);setAnswerHidden(false);setToolsOpen(['sdsum','plants'].includes(k));if(k==='ppf'){STATE.bundleOn=true;STATE.bundleX=1;STATE.bundleY=1;redrawAll();}historyBaseline();},key);
  await page.waitForFunction(()=>!_rangeAnimating&&_labelFrame==null);
  const selector=key==='sdsum'?'.sc-curve input[type=range]':key==='consumer'?'#chart circle[r="11"][fill="transparent"]':key==='ineq'?'#chart circle[r="12"][fill="transparent"]':key==='elast'?'#chart circle[r="13"][fill="transparent"]':'#chart .bundle-grab';
  const locator=key==='plants'?page.locator('#pl-q-slider'):key==='sdsum'?page.locator('.app input[type=range]:visible').first():page.locator(selector).first();
  await locator.scrollIntoViewIfNeeded();const b=await locator.boundingBox();
  await page.screenshot({path:path.join(out,key+'-before.png')});
  const from=await locator.evaluate(el=>{
   const r=el.getBoundingClientRect();
   for(const dx of [.5,.3,.7,.1,.9])for(const dy of [.5,.3,.7,.1,.9]){
    const p={x:r.x+r.width*dx,y:r.y+r.height*dy};if(document.elementFromPoint(p.x,p.y)===el)return p;
   }
   throw Error('No exposed drag target');
  });
  const to={x:from.x+(key==='ineq'?0:Math.min(28,width*.05)),y:from.y-(['sdsum','plants'].includes(key)?0:16)};
  await page.evaluate(()=>{
   window.__gestureBefore=JSON.stringify(collectModelState().state);window.__axis=[sx(0),sy(0),W,H];window.__draws=0;
   window.__oldScene=redrawScene;window.redrawScene=function(...args){__draws++;return __oldScene.apply(this,args);};
   window.__beforeUndo=histOf().undo.length;
  });
  console.log(key,from,to,await page.evaluate(p=>{const e=document.elementFromPoint(p.x,p.y);return{hit:e?.outerHTML?.slice(0,300),height:innerHeight};},from));
  const up=await gesture(from,to);await page.waitForTimeout(500);
  const held=await page.evaluate(()=>({pending:TaxMotion.pending,held:TaxMotion.held,draws:__draws,
   changed:__gestureBefore!==JSON.stringify(collectModelState().state),axis:__axis.map((n,i)=>Math.abs(n-[sx(0),sy(0),W,H][i])),
   undo:histOf().undo.length-__beforeUndo,loaders:document.querySelectorAll('.calc-value-loader').length,
   labels:[...document.querySelectorAll('#chart .coord-num')].filter(e=>getComputedStyle(e).visibility!=='hidden').length}));
  check(key+' updates while held',held.pending&&held.held&&held.changed&&held.draws>=2,held);
  check(key+' stable plane and single gesture',Math.max(...held.axis)<.05&&held.undo===0&&held.labels===0,held);
  if(key==='sdsum')check('summary uses dots',held.loaders>0,held.loaders);
  await page.screenshot({path:path.join(out,key+'-held.png')});await up();await settled();
  await page.evaluate(()=>{window.redrawScene=__oldScene;});await page.waitForTimeout(1200);
  const end=await page.evaluate(()=>({loaders:document.querySelectorAll('.calc-value-loader').length,undo:histOf().undo.length-__beforeUndo,touched:_histTouched,label:_histLabel,active:InputSnap.active,held:TaxMotion.held,draws:__draws,labelFrame:_labelFrame,range:_rangeAnimating}));
  check(key+' finished once',!end.loaders&&end.undo===1,end);
 }
 // Символьный сертификат не принимает кривую за прямую по нескольким точкам.
 check('affine certificate excludes nonlinear curves',await page.evaluate(()=>ppfAffine('100-2*x')?.[0]===-2&&ppfAffine('100-x+1e-16*x^3')===null&&ppfAffine('x<40?100-x:120-2*x')===null));
 const oracle=await page.evaluate(()=>{
  let calls=0,maxError=0;
  for(let i=1;i<=40;i++){
   const a=10+i,b=.2+i/17,c=20+i*.7,d=.3+i/23,f=x=>{calls++;return a-b*x;},g=x=>{calls++;return c-d*x;},xm=a/b,ym=c/d,X=(xm+ym)*i/41;
   f._affine=[-b,a];g._affine=[-d,c];
   const got=maxAllocY(f,g,X,xm,ym),lo=Math.max(0,X-ym),hi=Math.min(xm,X);
   const expected=a+c-d*X+Math.max((d-b)*lo,(d-b)*hi);maxError=Math.max(maxError,Math.abs(got-expected));
  }return{calls,maxError};
 });
 check('linear allocation is exact without a grid scan',oracle.calls<=160&&oracle.maxError<1e-10,oracle);
 check('no browser errors',!report.errors.length,report.errors);
}finally{await browser.close();fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));}
