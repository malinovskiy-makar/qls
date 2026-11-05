/* Все модели: немедленный численный кадр, одно построение, точный итог.
   Времена сохраняем для сравнения, а не превращаем загрузку Mac в порог CI. */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium,webkit} from 'playwright';
const args=process.argv.slice(2),arg=(k,d)=>{const i=args.indexOf('--'+k);return i<0?d:args[i+1];};
const engine=arg('browser','chromium'),width=+arg('width','1440'),height=+arg('height','950');
const out=path.resolve(arg('out','reports/controls-motion'));fs.mkdirSync(out,{recursive:true});
const browser=await({chromium,webkit})[engine].launch(),page=await browser.newPage({viewport:{width,height},hasTouch:args.includes('--touch'),locale:'ru-RU'});
const report={engine,width,height,cases:[],errors:[]};page.on('pageerror',e=>report.errors.push(e.message));
try{
 await page.goto((process.env.CALC2_BASE_URL||'http://127.0.0.1:8153')+'/calc2/?m=sdsum',{waitUntil:'networkidle'});
 await page.evaluate(async()=>{await document.fonts.ready;setToolsOpen(true);setAnswerHidden(false);});
 await page.addScriptTag({path:new URL('./redesign/inpage.js',import.meta.url).pathname});
 await page.evaluate(()=>{
  window.__motionSelect=()=>[...document.querySelectorAll('.app input[type=range]')].filter(el=>el.getBoundingClientRect().width>0);
  window.__motionRead=()=>{
   const state=__RD.stateDump(),numbers={};
   // Вид, подписи и служебные диапазоны — не результаты расчёта.
   const skip=/^(?:curves\.[0-9]+\.(?:labelPos|labelT)|panels|mathX|mathY|label|labDrag|resize|margin|pult|view|canvas|left|right)/;
   const walk=(v,k)=>{if(skip.test(k))return;if(typeof v==='number')numbers[k]=v;else if(v&&typeof v==='object')Object.entries(v).forEach(([a,b])=>walk(b,k?k+'.'+a:a));};walk(state,'');
   const marks=[...document.querySelectorAll('#chart .kp-mark')].map(e=>[+e.dataset.kpX,+e.dataset.kpY]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
   const geometry=[...document.querySelectorAll('#chart path,#chart line,#chart circle')].map(e=>['d','x1','y1','x2','y2','cx','cy','r'].map(a=>e.getAttribute(a)).join(',')).join('|');
   return{numbers,marks,path:geometry};
  };
  window.__motionDiff=(a,b)=>{
   const keys=new Set([...Object.keys(a.numbers),...Object.keys(b.numbers)]);
   return [...keys].filter(k=>Math.abs((a.numbers[k]??Infinity)-(b.numbers[k]??Infinity))>1e-7*Math.max(1,Math.abs(a.numbers[k]||0),Math.abs(b.numbers[k]||0))).map(k=>[k,a.numbers[k],b.numbers[k]]);
  };
 });
 const keys=arg('models',args.includes('--extras')?'ineq:alpha,ineq:tax,ineq:transfer,smallopen:tariff,smallopen:quota,labor-union:wagefloor,m-tangent:secant,fx:fixed':'').split(',').filter(Boolean);if(!keys.length)keys.push(...await page.evaluate(()=>Object.keys(SCENE_ROUTE).filter(k=>!['tax','tax-adv'].includes(k))));
 for(const key of keys){
  for(const variant of (args.includes('--parameters')?['parameter']:['default'])){
   const controls=await page.evaluate(async({key,variant})=>{
    InputSnap.cancel();TaxMotion.cancel();cancelRangeAnim();resetSceneMemory();pickScene(key.split(':')[0]);setToolsOpen(true);setAnswerHidden(false);
    if(key==='ineq:alpha'){STATE.ineqFormula='p^alpha';setIneqInput('formula');setIneqAlpha(2);}
    if(key==='ineq:tax'||key==='ineq:transfer'){const c=document.getElementById('ineq-redist');c.checked=true;c.dispatchEvent(new Event('change',{bubbles:true}));setIneqRedistTool(key.split(':')[1]);}
    if(key.startsWith('smallopen:'))setOpenTool(key.split(':')[1]);
    if(key==='labor-union:wagefloor')setUnionModel('wagefloor');
    if(key==='m-tangent:secant'){const c=document.getElementById('chk-secant');c.checked=true;c.dispatchEvent(new Event('change',{bubbles:true}));}
    if(key==='fx:fixed'){const c=document.getElementById('ma-fx-fixed');c.checked=true;c.dispatchEvent(new Event('change',{bubbles:true}));}
    if(variant==='parameter'){
     const inp=key==='ppf'?document.getElementById('inp-ppf'):FORMULA_FIELDS.filter(i=>i.isConnected&&fieldActive(i)).find(i=>i.value&& !/[=;?:]/.test(i.value));
     if(!inp)return [];
     inp.value=key==='ppf'?'a*(100-x)':'a*('+inp.value+')';inp.dispatchEvent(new Event('change',{bubbles:true}));
     inp.dispatchEvent(new Event('input',{bubbles:true}));
     await new Promise(r=>setTimeout(r,350));
     if(!STATE.params?.a)return [];
     STATE.params.a.min=.5;STATE.params.a.max=1.5;STATE.params.a.value=1;updatePult();redrawAll();
     document.querySelectorAll('.pchip-param input[type=range]').forEach(sl=>{sl.min=.5;sl.max=1.5;sl.value=1;});
    }
    cancelRangeAnim();STATE.zoomLock=true;
    return __motionSelect().map((el,i)=>({id:el.id,index:i,cid:el.closest('[data-cid]')?.dataset.cid,param:!!el.closest('.pchip-param')})).filter(c=>variant!=='parameter'||c.param);
   },{key,variant});
   for(const c of controls){
    const row={key,variant,control:c};report.cases.push(row);
    try{
     Object.assign(row,await page.evaluate(c=>{
      const sl=c.id?document.getElementById(c.id):__motionSelect()[c.index],min=+sl.min,max=+sl.max,start=+sl.value;
      const v=Math.max(min,Math.min(max,start+(start>min+(max-min)*.8?-1:1)*(max-min)*.02731));
      const before=__motionRead(),axis=[sx(0),sy(0),W,H],panel=document.getElementById('sb-body')?.innerHTML;
      const original=redrawScene;let draws=0;window.redrawScene=function(...a){draws++;return original.apply(this,a);};
      sl.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:1}));sl.value=v;
      const t=performance.now();sl.dispatchEvent(new Event('input',{bubbles:true}));const ms=performance.now()-t;
      window.redrawScene=original;
      const live=__motionRead(),pending=TaxMotion.pending,held=TaxMotion.held,connected=sl.isConnected;
      const stable=axis.every((v,i)=>Math.abs(v-[sx(0),sy(0),W,H][i])<.05);
      const panelStable=panel===document.getElementById('sb-body')?.innerHTML;
      InputSnap.cancel();TaxMotion.cancel();redrawAll();buildAnswer();
      const exact=__motionRead(),differences=__motionDiff(live,exact);
      return{ms,draws,pending,held,connected,stable,panelStable,differences,changed:before.path!==live.path,
       marksMatch:JSON.stringify(live.marks)===JSON.stringify(exact.marks),value:v,fields:Object.keys(live.numbers).length,
       ok:draws===1&&pending&&held&&connected&&stable&&panelStable&&!differences.length};
     },c));
     // Пауза с нажатой кнопкой не завершает ни числа, ни жест.
     await page.evaluate(c=>{const sl=c.id?document.getElementById(c.id):__motionSelect()[c.index];sl.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:1}));sl.value=+sl.value+(+sl.max-+sl.min)*.0137;sl.dispatchEvent(new Event('input',{bubbles:true}));},c);
     await page.waitForTimeout(160);
     row.pause=await page.evaluate(()=>TaxMotion.pending&&TaxMotion.held);
     await page.evaluate(()=>window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerId:1})));
     await page.waitForFunction(()=>!TaxMotion.pending&&!InputSnap.active,null,{timeout:20000});
     row.released=await page.evaluate(()=>!document.querySelector('.calc-value-loader')&&!document.body.classList.contains('tax-values-pending'));
     row.ok&&=row.pause&&row.released;
    }catch(e){row.ok=false;row.error=e.message;await page.evaluate(()=>{InputSnap.cancel();TaxMotion.cancel();});}
    console.log(JSON.stringify(row));
   }
  }
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
 }
}finally{await browser.close();fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));}
const failed=report.cases.filter(c=>!c.ok);console.log(JSON.stringify({cases:report.cases.length,failed:failed.length,errors:report.errors}));
assert(!failed.length&&!report.errors.length,'control motion regressions');
