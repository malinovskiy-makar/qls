/* Запись владельца: шкала выпуска сама росла под мышью, а TC становилась ломаной. */
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import{chromium,webkit}from'playwright';
const args=process.argv.slice(2),arg=(k,d)=>{const i=args.indexOf('--'+k);return i<0?d:args[i+1];};
const out=path.resolve(arg('out','reports/plants-range'));fs.mkdirSync(out,{recursive:true});
const browser=await({chromium,webkit})[arg('browser','chromium')].launch(),page=await browser.newPage({viewport:{width:1440,height:950}});
const report={checks:[],errors:[]},check=(name,ok,data)=>{report.checks.push({name,ok:!!ok,data});assert(ok,name+': '+JSON.stringify(data));};
page.on('pageerror',e=>report.errors.push(e.message));
try{
 await page.goto((process.env.CALC2_BASE_URL||'http://127.0.0.1:8153')+'/calc2/?m=plants',{waitUntil:'networkidle'});
 const held=await page.evaluate(()=>{
  setPlantInputRows([{expr:'Q^2',K:null,kind:'sunk'},{expr:'2*Q^2',K:2,kind:'sunk'}]);setPlantsQ(30);STATE.zoomLock=true;
  const sl=document.getElementById('pl-q-slider'),max=+sl.max,rows=[];sl.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:1}));
  for(let i=0;i<25;i++){sl.value=+sl.max*.75;sl.dispatchEvent(new Event('input',{bubbles:true}));rows.push({max:+sl.max,q:STATE.plQ});}
  return{max,rows,pending:TaxMotion.pending};
 });
 check('same pointer position keeps one output and one range',held.pending&&held.rows.every(r=>r.max===held.max&&r.q===held.max*.75),held);
 await page.evaluate(()=>window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerId:1})));
 await page.waitForFunction(()=>!TaxMotion.pending&&!InputSnap.active);
 check('release does not expand range',await page.evaluate(()=>+document.getElementById('pl-q-slider').max)===held.max);
 const precise=await page.evaluate(()=>{const i=document.getElementById('pl-q-input');i.value='73.123456789';i.dispatchEvent(new Event('change',{bubbles:true}));return STATE.plQ;});
 check('manual input keeps all supplied decimals',precise===73.123456789,precise);
 const large=await page.evaluate(()=>{
  setRanges(60,1800);STATE.zoomLock=true;setPlantsQ(640);const r=plantsAt(640);
  const curves=[...document.querySelectorAll('#chart path[data-expr-name]')].filter(e=>['TC','TC_1'].includes(e.dataset.exprName)).map(e=>({name:e.dataset.exprName,points:e.__data__.filter(Boolean).map(p=>p[0])}));
  return{q:STATE.plQ,qs:r.qs,tc:r.tcDirect,mc:r.m,max:+document.getElementById('pl-q-slider').max,curves};
 });
 check('large manual value and independent allocation oracle',large.q===640&&large.qs[0]===638&&large.qs[1]===2&&large.tc===407052&&large.mc===1276&&large.max>=640,large);
 check('visible TC remains sampled at full resolution',large.curves.length>=2&&large.curves.every(c=>c.points.length>=80&&Math.max(...c.points)<=60),large.curves);
 await page.screenshot({path:path.join(out,'large-manual-output.png')});
 const bounds=await page.evaluate(()=>{const s=document.getElementById('pl-q-slider');s.dataset.boundsByHand='1';s.max=100;setPlantsQ(1000);return {max:+s.max,q:STATE.plQ};});
 check('custom range preserved without rounding manual input',bounds.max===100&&bounds.q===1000,bounds);
 check('no page errors',!report.errors.length,report.errors);
}finally{await browser.close();fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify(report));
