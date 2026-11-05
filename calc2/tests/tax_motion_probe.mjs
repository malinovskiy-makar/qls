/* Настоящий жест, холодный worker, прерывание, движение поля и доступность.
   Времена — свидетельства, а не зависящий от загрузки Mac порог CI.
   Строгие стражи: актуальная геометрия в том же событии, отсутствие тяжёлой
   панели во время жеста, точный ответ, неизменные оси, ограниченный DOM. */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium,webkit} from 'playwright';
const args=process.argv.slice(2),arg=(k,d)=>{const i=args.indexOf('--'+k);return i<0?d:args[i+1];};
const engine=arg('browser','chromium'),width=+arg('width','1440');
const out=path.resolve(arg('out','reports/calc2-tax-motion'));fs.mkdirSync(out,{recursive:true});
const browser=await ({chromium,webkit})[engine].launch();
const page=await browser.newPage({viewport:{width,height:950},locale:'ru-RU'}),errors=[];
const report={engine,width,checks:[],errors};
report.manifestPaths=args.includes('--manifest-paths');
page.on('pageerror',e=>errors.push(e.message));
const check=(name,ok,detail)=>{report.checks.push({name,ok,detail});assert(ok,`${name}: ${JSON.stringify(detail)}`);};
const settled=()=>page.waitForFunction(()=>!TaxMotion.pending,null,{timeout:20000});
const sleep=ms=>page.waitForTimeout(ms);
const snapshot=()=>page.evaluate(()=>({tax:STATE.tax,eq:STATE.taxEq,cs:STATE.csTax,ps:STATE.psTax,budget:STATE.budget,dwl:STATE.dwl,
 hero:document.getElementById('ans-hero').textContent,summary:document.getElementById('info-tax').textContent,
 labels:[...document.querySelectorAll('#chart .coord-num')].map(e=>e.textContent)}));
try{
 if(report.manifestPaths){
  // Те же файлы под именами, которые выдаёт ManifestStaticFilesStorage.
  // Меняем и обычный <script>, и data-атрибуты: поиск по старому имени
  // не должен незаметно включать синхронный fallback.
  await page.context().route('**/static/calc2/*.abc123def456.js*',async route=>{
   const name=path.basename(new URL(route.request().url()).pathname).replace('.abc123def456.js','.js');
   assert(['12-numbers.js','13-number-worker.js'].includes(name));
   await route.fulfill({path:new URL('../static/calc2/'+name,import.meta.url).pathname,contentType:'application/javascript'});
  });
  await page.route('**/calc2/?m=taxes',async route=>{
   const response=await route.fetch();
   const body=(await response.text()).replace(/(calc2\/(?:12-numbers|13-number-worker))\.js/g,'$1.abc123def456.js');
   await route.fulfill({response,body});
  });
 }
 await page.addInitScript(()=>{
  localStorage.setItem('calc2.v1.answerHidden','0');
  // Задерживаем только доставку ответа настоящего worker в тесте гонки.
  window.__numberMessages=[];window.__workerCount=0;window.__workerGate=false;window.__workerQueue=[];
  const Original=Worker;
  window.Worker=class extends Original{
   constructor(...args){super(...args);__workerCount++;}
   set onmessage(callback){super.onmessage=e=>{
    __numberMessages.push(e.data);
    if(__workerGate)__workerQueue.push(()=>callback(e));else callback(e);
   };}
  };
 });
 await page.goto((process.env.CALC2_BASE_URL||'http://127.0.0.1:8099')+'/calc2/?m=taxes',{waitUntil:'networkidle'});
 await page.evaluate(async()=>{await document.fonts.ready;setAnswerHidden(false);setTax(20);});
 const cookie=page.getByRole('button',{name:'Только необходимые'});if(await cookie.isVisible())await cookie.click();
 await sleep(500);
 check('compact normal margin',await page.evaluate(()=>CONFIG.margin.left<100));
 await page.evaluate(()=>{
  const c=STATE.curves.find(c=>c.role==='supply');updateCurveExpr(c,'Q^2/100');renderCurveList();redrawAll();
  window.__calls={};for(const name of ['redrawAll','updateTaxPanel','buildAnswer','simplifyRecord']){
   const fn=window[name];window[name]=function(...args){__calls[name]=(__calls[name]||0)+1;return fn.apply(this,args);};
  }
 });
 await sleep(500);
 const slider=page.locator('#tax-slider');await slider.scrollIntoViewIfNeeded();const box=await slider.boundingBox();
 const range=await slider.evaluate(e=>({min:+e.min,max:+e.max})),at=v=>box.x+8+(box.width-16)*(v-range.min)/(range.max-range.min);
 await page.evaluate(()=>{
  window.__calls={};window.__frames=[];window.__inputs=[];window.__active=true;window.__tasks=[];
  const slider=document.getElementById('tax-slider');
  slider.addEventListener('input',()=>{window.__eventAt=performance.now();},true);
  slider.addEventListener('input',()=>{
   const t=__eventAt,value=Number(slider.value),handler=performance.now()-t;
   const q=(-100+Math.sqrt(50000-400*value))/2;
   const keyPoints=[...document.querySelectorAll('#chart .kp-mark')].map(e=>[+e.dataset.kpX,+e.dataset.kpY]);
   const keyPointsMatch=[STATE.taxEq.Pb,STATE.taxEq.Ps].every(p=>keyPoints.some(([x,y])=>Math.abs(x-q)<1e-7&&Math.abs(y-p)<1e-7));
   __inputs.push({at:t,handler,value,state:STATE.tax,error:Math.abs(STATE.taxEq.Q-q),
    keyPointsMatch,
    path:[...document.querySelectorAll('#chart path[stroke-dasharray="6 4"]')].find(e=>e.getAttribute('d'))?.getAttribute('d')});
   requestAnimationFrame(()=>{__inputs.findLast(s=>s.at===t).toFrame=performance.now()-t;});
  });
  if(PerformanceObserver.supportedEntryTypes.includes('longtask')){
   window.__observer=new PerformanceObserver(list=>__tasks.push(...list.getEntries().map(e=>({start:e.startTime,duration:e.duration}))));
   __observer.observe({type:'longtask'});
  }
  const frame=t=>{if(!__active)return;const b=document.getElementById('chart').getBoundingClientRect();
   __frames.push({t,x:b.x,w:b.width,axis:sx(0),y:sy(0)});requestAnimationFrame(frame);};requestAnimationFrame(frame);
 });
 await page.mouse.move(at(20),box.y+box.height/2);await page.mouse.down();
 for(let i=0;i<100;i++)await page.mouse.move(at(20+55*i/99),box.y+box.height/2);
 // Удержанная ручка — ещё не окончание жеста, даже после паузы.
 await sleep(250);
 const drag=await page.evaluate(()=>{
  __active=false;window.__observer?.disconnect();return{frames:__frames,inputs:__inputs,tasks:__tasks,calls:__calls,
   pending:TaxMotion.pending,loaders:document.querySelectorAll('.calc-value-loader').length,
   visibleLabels:[...document.querySelectorAll('#chart .coord-num')].filter(e=>getComputedStyle(e).visibility!=='hidden').length};
 });
 const span=(list,key)=>Math.max(...list.map(s=>s[key]))-Math.min(...list.map(s=>s[key]));
 const pct=(a,p)=>a.sort((a,b)=>a-b)[Math.ceil(a.length*p)-1];
 report.drag={inputs:drag.inputs.length,frames:drag.frames.length,calls:drag.calls,longTasks:drag.tasks,
  handlerP95:pct(drag.inputs.map(s=>s.handler),.95),
  inputToFrameP95:pct(drag.inputs.map(s=>s.toFrame).filter(Number.isFinite),.95),
  frameIntervalP95:pct(drag.frames.slice(1).map((s,i)=>s.t-drag.frames[i].t),.95)};
 check('native input reaches model in same event',drag.inputs.length>=30&&drag.inputs.every(s=>s.value===s.state&&s.error<1e-7),report.drag);
 check('curve changes with every changed tax',drag.inputs.every((s,i)=>s.path&&(i===0||s.value===drag.inputs[i-1].value||s.path!==drag.inputs[i-1].path)));
 check('hidden labels preserve numeric key points',drag.inputs.every(s=>s.keyPointsMatch));
 check('no panel or formula simplification during gesture',Object.values(drag.calls).every(n=>n===0),drag.calls);
 check('plane and container fixed while held',['x','w','axis','y'].every(key=>span(drag.frames,key)<=1),drag.frames.slice(0,1));
 check('held gesture stays pending',drag.pending&&drag.loaders>0&&drag.visibleLabels===0);
 await page.screenshot({path:path.join(out,`pending-${engine}-${width}.png`)});
 await page.mouse.up();await settled();
 const result=await snapshot();await page.evaluate(()=>{setTax(STATE.tax);buildAnswer();});
 check('async result equals exact synchronous result',JSON.stringify(await snapshot())===JSON.stringify(result));
 check('real worker delivered exact records',await page.evaluate(()=>__workerCount===1&&__numberMessages.some(m=>m.records?.length>0)));

 // Длинная точная запись появляется только после жеста и расширяет поле
 // непрерывным transform. Следующее движение не ждёт этой анимации.
 await page.evaluate(()=>{
  const c=STATE.curves.find(c=>c.role==='supply');updateCurveExpr(c,'Q');redrawAll();setTaxForm('vat');setTax(60);
  TaxMotion.hold();setTax(61,true);
 });
 const origin=await page.evaluate(()=>sx(0));
 const interrupt=await page.evaluate(async()=>{
  TaxMotion.release();
  const g=await new Promise((resolve,reject)=>{
   const start=performance.now();
   const frame=()=>{const el=document.querySelector('[data-tax-plane-motion]');
    if(el&&el.getAnimations()[0]?.currentTime>=60){resolve(el);return;}
    if(performance.now()-start>10000){reject(new Error('Plane animation did not appear'));return;}
    requestAnimationFrame(frame);
   };requestAnimationFrame(frame);
  });
  const m=new DOMMatrix(getComputedStyle(g).transform);
  const before=m.a*sx(0)+m.e;
  TaxMotion.hold();setTax(27,true);
  return{before,after:sx(0),pending:TaxMotion.pending,group:!!document.querySelector('[data-tax-plane-motion]')};
 });
 check('new input interrupts growing field without jump',interrupt.pending&&!interrupt.group&&interrupt.before>origin+1&&Math.abs(interrupt.before-interrupt.after)<=1,{origin,...interrupt});
 await page.evaluate(()=>TaxMotion.release());await settled();

 await page.evaluate(()=>{__workerGate=true;TaxMotion.hold();setTax(Math.sqrt(31)+.137,true);TaxMotion.release();});
 await page.waitForFunction(()=>__workerQueue.length>0,null,{timeout:15000});
 await page.evaluate(()=>{TaxMotion.hold();setTax(41,true);__workerGate=false;__workerQueue.splice(0).forEach(fn=>fn());});
 await sleep(250);
 check('late worker cannot finish a newer held gesture',await page.evaluate(()=>TaxMotion.pending&&STATE.tax===41&&document.body.classList.contains('tax-values-pending')));
 await page.evaluate(()=>window.dispatchEvent(new PointerEvent('pointercancel')));await settled();
 check('pointer cancellation completes current exact answer',(await snapshot()).tax===41);
 await slider.focus();await page.keyboard.down('ArrowRight');await sleep(220);
 check('keyboard gesture stays pending until keyup',await page.evaluate(()=>TaxMotion.pending&&STATE.tax===42));
 await page.keyboard.up('ArrowRight');await settled();
 // Второй инструмент пользуется той же фазой движения и своими прежними
 // экономическими формулами. Эталон ниже решает линейный рынок аналитически.
 for(const variant of ['unit','vat','subbuyer']){
  await page.evaluate(variant=>{setTaxForm('unit');setTax(20);addSecondTax();
   setSecondTax({type:variant==='subbuyer'?'subsidy':'tax',form:variant,rate:0});
  },variant);await sleep(300);
  const pair=await page.evaluate(async variant=>{
   const slider=document.getElementById('tax2-slider'),origin=[sx(0),sy(0)];
   const handlers=[];let error=0,axisDrift=0;__calls={};
   slider.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
   for(let i=0;i<50;i++){
    const rate=(i+1)*.8,t=performance.now();slider.value=rate;slider.dispatchEvent(new Event('input',{bubbles:true}));
    handlers.push(performance.now()-t);
    const q=variant==='unit'?(80-rate)/2:variant==='vat'?80/(2+rate/100):(80+rate)/(2+rate/100);
    const pb=100-q,ps=q,{Q:aq,Pb:ab,Ps:as}=STATE.taxEq;
    // При почти взаимном погашении налога и субсидии ошибка корня
    // умножается на оборот. Сначала независимо проверяем Q и обе цены;
    // интегралы и выплаты сравниваем при уже проверенном корне, как в
    // tax_perf_probe. Допуск решателя/интегратора не меняется.
    const second=variant==='unit'?rate:variant==='vat'?rate/100*as:-rate/100*ab;
    for(const [a,e]of [[STATE.taxEq.Q,q],[STATE.taxEq.Pb,pb],[STATE.taxEq.Ps,ps],
     [STATE.csTax,(100-ab)*aq-aq*aq/2],[STATE.psTax,as*aq-aq*aq/2],
     [STATE.budget,(20+second)*aq],[STATE.dwl,(STATE.eq.Q-aq)**2]]){
     error=Math.max(error,Math.abs(a-e)/Math.max(1,Math.abs(e)));
    }
    axisDrift=Math.max(axisDrift,Math.abs(sx(0)-origin[0]),Math.abs(sy(0)-origin[1]));
    await new Promise(requestAnimationFrame);
   }
   const calls={...__calls};slider.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
   return{variant,error,axisDrift,handlers,calls};
  },variant);
  check('second '+variant+' updates exact geometry immediately',pair.error<1e-9&&pair.axisDrift<=1&&Object.values(pair.calls).every(n=>n===0),pair);
  await settled();const asyncPair=await snapshot();await page.evaluate(()=>{setSecondTax({});buildAnswer();});
  check('second '+variant+' exact answer matches synchronous',JSON.stringify(await snapshot())===JSON.stringify(asyncPair));
 }
 await page.evaluate(()=>removeSecondTax());
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.evaluate(()=>{TaxMotion.hold();setTax(37,true);});await sleep(140);
 check('reduced motion has no infinite animation',await page.evaluate(()=>document.getAnimations().every(a=>a.effect?.getTiming().iterations!==Infinity)));
 await page.evaluate(()=>TaxMotion.release());await settled();
 check('no loader or pending flag after completion',await page.evaluate(()=>!document.querySelector('.calc-value-loader')&&!document.body.classList.contains('tax-values-pending')));
 await page.screenshot({path:path.join(out,`settled-${engine}-${width}.png`)});
 check('no page errors',errors.length===0,errors);
}catch(error){report.failure=error.stack;await page.screenshot({path:path.join(out,`failure-${engine}-${width}.png`)});process.exitCode=1;
}finally{await browser.close();fs.writeFileSync(path.join(out,`motion-${engine}-${width}.json`),JSON.stringify(report,null,2));}
console.log(JSON.stringify(report));
