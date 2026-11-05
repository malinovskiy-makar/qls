/* Ставка — обратная связь о вводе: одинаковая короткая запись с холодным
   и заполненным кэшем, без изменения модели, при удержании мыши/пальца. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {chromium,webkit} from 'playwright';
const args=process.argv.slice(2),arg=(k,d)=>{const i=args.indexOf('--'+k);return i<0?d:args[i+1];};
const engine=arg('browser','chromium'),width=+arg('width','1024'),height=+arg('height','768');
const theme=arg('theme','light'),touch=args.includes('--touch');
const out=path.resolve(arg('out','reports/rate-label'));fs.mkdirSync(out,{recursive:true});
const browser=await({chromium,webkit})[engine].launch();
const context=await browser.newContext({viewport:{width,height},hasTouch:touch,isMobile:touch});
const page=await context.newPage(),report={engine,width,height,theme,touch,checks:[],samples:[],errors:[]};
page.on('pageerror',e=>report.errors.push(e.message));
const check=(name,ok,data)=>report.checks.push({name,ok:!!ok,data});
const settled=()=>page.waitForFunction(()=>!InputSnap.active&&!TaxMotion.pending);
const compact=s=>s.replace(/[\s\u202f\u00a0]/g,'');
const short=(s,expected)=>compact(s).includes(expected)&&!/[\/…√]/.test(s);
const read=()=>page.evaluate(()=>({tax:STATE.tax,q:STATE.taxEq.Q,pending:TaxMotion.pending,
 side:CalcNumber.readText(document.querySelector('#tax-field .reg-eq')),
 graph:[...document.querySelectorAll('#chart text')].map(e=>e.textContent).find(s=>/^t\s*=/.test(s)),
 loaders:[...document.querySelectorAll('#ans-strip b')].every(e=>getComputedStyle(e).color==='rgba(0, 0, 0, 0)'&&e.querySelector('.calc-value-loader')),
 axes:[sx(0),sy(0)]}));
async function holdSlider(selector){
 const sl=page.locator(selector);await sl.scrollIntoViewIfNeeded();const b=await sl.boundingBox();
 const pt={x:b.x+b.width*.2,y:b.y+b.height/2};
 if(touch&&engine==='chromium'){
  const cdp=await context.newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[pt]});
  return async()=>{await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach();};
 }
 await page.mouse.move(pt.x,pt.y);await page.mouse.down();return()=>page.mouse.up();
}
try{
 await page.goto((process.env.CALC2_BASE_URL||'http://127.0.0.1:8153')+'/calc2/?m=taxes',{waitUntil:'networkidle'});
 await page.evaluate(async theme=>{await document.fonts.ready;document.documentElement.dataset.theme=theme;setToolsOpen(true);setTax(20);},theme);
 const cookie=page.getByRole('button',{name:'Только необходимые'});if(await cookie.isVisible())await cookie.click();
 const up=await holdSlider('#tax-slider');
 const origin=(await read()).axes;
 for(const [value,expected] of [[27.388123456,'27,388'],[23539/441,'53,376'],[18,'18'],[.00000123456,'0,00000123']]){
  const pair=[];
  for(const warm of [false,true]){
   const inputValue=await page.evaluate(({value,warm})=>{if(warm)CalcNumber.classify(value);const sl=document.getElementById('tax-slider');sl.value=value;sl.dispatchEvent(new Event('input',{bubbles:true}));return sl.valueAsNumber;},{value,warm});
   const s=await read();pair.push(s);report.samples.push({value,warm,...s});
   check(`short label ${value} warm=${warm}`,short(s.graph||'',expected)&&short(s.side,expected),s);
   check(`model stays precise ${value} warm=${warm}`,s.tax===inputValue&&Math.abs(s.q-(100-inputValue)/2)<1e-8,s);
   check(`held indicators and axes ${value} warm=${warm}`,s.pending&&s.loaders&&s.axes.every((v,i)=>Math.abs(v-origin[i])<.05),s);
  }
  check(`cache does not change labels ${value}`,pair[0].graph===pair[1].graph&&pair[0].side===pair[1].side,pair);
 }
 await page.evaluate(()=>{const sl=document.getElementById('tax-slider');sl.value=23539/441;sl.dispatchEvent(new Event('input',{bubbles:true}));});
 await page.waitForTimeout(650);
 check('pause with mouse held keeps short rate',short((await read()).graph||'','53,376')&&(await read()).pending);
 await page.screenshot({path:path.join(out,'held.png')});
 await up();await settled();const end=await read();
 check('release uses automatic step',end.tax===53&&short(end.graph||'','53')&&short(end.side,'53'),end);
 // Та же ставка тянется непосредственно за клин. Панель должна идти за ней
 // уже во время движения, а не догонять после полного redrawAll.
 await page.locator('#chart').scrollIntoViewIfNeeded();
 const handle=await page.evaluate(()=>{const r=document.querySelector('#chart circle[r="7"]').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};});
 await page.mouse.move(handle.x,handle.y);await page.mouse.down();
 await page.mouse.move(handle.x,handle.y-21.7,{steps:8});
 const graphDrag=await read();
 const expected=String(Number(graphDrag.tax.toFixed(3))).replace('.',',');
 check('graph drag updates both labels before release',short(graphDrag.graph||'',expected)&&short(graphDrag.side,expected)&&graphDrag.pending,graphDrag);
 await page.mouse.up();await settled();
 // Второе вмешательство и процентный знак используют тот же способ показа.
 await page.evaluate(()=>{setTax(20);addSecondTax();setSecondTax({form:'vat',rate:10});});
 const up2=await holdSlider('#tax2-slider');
 await page.evaluate(()=>{const sl=document.getElementById('tax2-slider');sl.value=23539/441;sl.dispatchEvent(new Event('input',{bubbles:true}));});
 const second=await page.evaluate(()=>({rate:STATE.taxSecond.rate,inputValue:document.getElementById('tax2-slider').valueAsNumber,side:CalcNumber.readText(document.getElementById('tax2-value')),
  graph:document.querySelector('[data-tax-pair-wedge="2"] text')?.textContent,pending:TaxMotion.pending}));
 check('second percentage rate stays short and precise',second.rate===second.inputValue&&Math.abs(second.rate-23539/441)<1e-12&&short(second.side,'53,376')&&short(second.graph||'','53,376')&&second.graph.includes('%')&&second.pending,second);
 await up2();await settled();await page.evaluate(()=>removeSecondTax());
 await page.locator('#tax-field .reg-eq').click();const editor=page.locator('#tax-field input.param-eq-input');
 await editor.fill('73.4689');await editor.press('Enter');await settled();
 check('manual value is not rounded by preview',await page.evaluate(()=>STATE.tax===73.4689));
 check('exact notation restored outside gesture',await page.evaluate(()=>document.querySelector('#chart text')!==null&&[...document.querySelectorAll('#chart text')].some(e=>e.textContent==='t='+CalcNumber.format(STATE.tax))));
 check('no browser errors',!report.errors.length,report.errors);
}finally{fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));await browser.close();}
const failed=report.checks.filter(c=>!c.ok);console.log(JSON.stringify({engine,width,height,checks:report.checks.length,failed}));
assert.equal(failed.length,0,'rate label regressions');
