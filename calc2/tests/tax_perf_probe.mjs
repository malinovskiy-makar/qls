/* Налог: немедленный расчёт, один кадр геометрии, неподвижная плоскость.
 * CALC2_BASE_URL=http://127.0.0.1:8147 node calc2/tests/tax_perf_probe.mjs
 * --browser chromium|webkit --width 1440|390 --theme light|dark
 * --cases unit,thirds,radical,vat --steps 200 --out DIR
 * --baseline-dir DIR подаёт исходные JS через route (для сравнения, не подмены
 * математики). --measure-only сохраняет доказательства без требований починки.
 * Время зависит от машины; строгие проверки — числа, геометрия и лишняя работа.
 */
import fs from 'node:fs';
import path from 'node:path';
import {chromium, webkit} from 'playwright';

const args=process.argv.slice(2);
const arg=(key,fallback)=>{const i=args.indexOf('--'+key);return i<0?fallback:args[i+1];};
const engine=arg('browser','chromium'),width=+arg('width','1440'),theme=arg('theme','light');
const steps=+arg('steps','200'),cases=arg('cases','unit,thirds').split(',');
const out=path.resolve(arg('out','reports/calc2-tax-perf'));
const baseline=arg('baseline-dir',''),measureOnly=args.includes('--measure-only');
const runs=arg('runs',baseline?'baseline':'current').split(',');
const base=process.env.CALC2_BASE_URL||'http://127.0.0.1:8099';
const browser=await ({chromium,webkit})[engine].launch();
fs.mkdirSync(out,{recursive:true});
const reports=[],failures=[];
const check=(condition,message)=>{if(!condition)failures.push(message);};
const pct=(a,p)=>a.slice().sort((a,b)=>a-b)[Math.ceil(a.length*p)-1];
const delta=a=>Math.max(...a)-Math.min(...a);

try {
 for(let round=0;round<runs.length;round++){
 const run=runs[round];
 for(const name of cases){
  const ctx=await browser.newContext({viewport:{width,height:900},locale:'ru-RU'});
  await ctx.addInitScript(theme=>{localStorage.setItem('theme',theme);localStorage.setItem('calc2.v1.answerHidden','0');},theme);
  if(run==='baseline')await ctx.route('**/static/calc2/*.js*',async route=>{
   const file=path.join(baseline,path.basename(new URL(route.request().url()).pathname));
   if(fs.existsSync(file))await route.fulfill({path:file,contentType:'application/javascript'});else await route.continue();
  });
  const page=await ctx.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/calc2/?m=taxes',{waitUntil:'networkidle'});
  await page.evaluate(async name=>{
   await document.fonts.ready;setAnswerHidden(false);
   const expr={thirds:'2Q',radical:'Q^2/100'}[name];
   if(expr){
    const supply=STATE.curves.find(c=>c.role==='supply');
    updateCurveExpr(supply,expr);renderCurveList();
    const input=document.querySelector(`#curve-list .fc-card[data-cid="${supply.id}"] .curve-expr-inp`);
    if(input?.value!==expr)throw new Error(`Visible supply formula differs from ${expr}`);
   }
   redrawAll();if(name==='vat')setTaxForm('vat');setTax(20);
  },name);
  await page.waitForTimeout(900);
  const cdp=engine==='chromium'?await ctx.newCDPSession(page):null;
  const memory=async()=>{
   if(!cdp)return {nodes:await page.locator('*').count()};
   await cdp.send('HeapProfiler.collectGarbage');
   return {...await cdp.send('Memory.getDOMCounters'),...await cdp.send('Runtime.getHeapUsage')};
  };
  const before=await memory();
  await page.evaluate(()=>{
   window.__taxPerfCalls={};
   for(const name of ['redrawAll','redrawScene','recompute','updateTaxPanel','buildAnswer','renderCurveList']){
    const original=window[name];
    window[name]=function(...args){__taxPerfCalls[name]=(__taxPerfCalls[name]||0)+1;return original.apply(this,args);};
   }
  });
  const data=await page.evaluate(async ({steps,name})=>{
   const rect=id=>{const r=document.getElementById(id).getBoundingClientRect();return [r.x,r.y,r.width,r.height];};
   const geometry=()=>({wrap:rect('graph-wrap'),chart:rect('chart'),tools:rect('tools-panel'),answer:rect('params-panel'),
    origin:[sx(0),sy(0)],plot:[...sx.range(),...sy.range()],margin:{...CONFIG.margin},
    window:[CONFIG.Qmin,CONFIG.Qmax,CONFIG.Pmin,CONFIG.Pmax]});
   const read=()=>({eq:STATE.eq,taxEq:STATE.taxEq,cs:STATE.csTax,ps:STATE.psTax,budget:STATE.budget,dwl:STATE.dwl});
   const raf=()=>new Promise(requestAnimationFrame),frames=[],samples=[];
   const start=geometry(),slider=document.getElementById('tax-slider');
   slider.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
   let mathError=0,areaRelativeError=0,labelOverflow=0,inputLag=0;
   for(let i=0;i<steps;i++){
    await raf();
    const value=i<steps/2?i*200/steps:200-i*200/steps;
    const t=performance.now();slider.value=value;slider.dispatchEvent(new Event('input',{bubbles:true}));
    const handler=performance.now()-t,numbers=read();
    inputLag=Math.max(inputLag,Math.abs(STATE.tax-Number(slider.value)));
    const rate=STATE.tax,b=name==='thirds'?2:1;
    const q=name==='radical'?(-100+Math.sqrt(50000-400*rate))/2
     :name==='vat'?100/(2+rate/100):(100-rate)/(1+b);
    const pb=100-q,ps=name==='radical'?q*q/100:b*q;
    const actual=STATE.taxEq||{Q:STATE.eq.Q,Pb:STATE.eq.P,Ps:STATE.eq.P};
    const comparisons=[[actual.Q,q],[actual.Pb,pb],[actual.Ps,ps],
     [STATE.budget??0,(pb-ps)*q]];
    const q0=STATE.eq.Q,aq=actual.Q;
    const welfare=x=>100*x-x*x/2-(name==='radical'?x*x*x/300:b*x*x/2);
    // c9 uses 1000 trapezoids, or 400 per piece for base surplus.
    // For S=Q²/100, |f''|=.02:
    // the independent error bound is |f''| L³/(12 n²). Keep the old
    // integrator and solver tolerances; don't demand impossible 1e-9 areas.
    // Areas use the already checked equilibrium to avoid counting root error twice.
    const areaBound=(length,n=1000)=>name==='radical'?Math.abs(length)**3/(600*n*n):0;
    const areas=[[rate===0?STATE.cs:STATE.csTax,(100-actual.Pb)*aq-aq*aq/2,0],
     [rate===0?STATE.ps:STATE.psTax,actual.Ps*aq-(name==='radical'?aq**3/300:b*aq*aq/2),areaBound(aq,rate===0?400:1000)],
     [STATE.dwl??0,welfare(q0)-welfare(aq),areaBound(q0-aq)]];
    for(const [a,e]of areas)areaRelativeError=Math.max(areaRelativeError,Math.abs(a-e)/Math.max(1,Math.abs(e)));
    comparisons.push(...areas);
    for(const [a,e,bound=0]of comparisons){if(typeof a!=='number'||!Number.isFinite(a))mathError=Infinity;
     else mathError=Math.max(mathError,Math.max(0,Math.abs(a-e)-bound)/Math.max(1,Math.abs(e)));}
    const sync=geometry();await raf();const first=geometry();await raf();
    const frame=geometry(),elapsed=performance.now()-t;
    frames.push(sync,first,frame);
    const chart=document.getElementById('chart').getBoundingClientRect();
    for(const label of document.querySelectorAll('#chart text.coord-num')){
     if(label.getAttribute('text-anchor')==='middle')continue;
     const r=label.getBoundingClientRect();
     labelOverflow=Math.max(labelOverflow,chart.left+1-r.left,r.right-(chart.left+sx(0)-1));
    }
    samples.push({value:STATE.tax,handler,elapsed,numbers});
   }
   const calls={...__taxPerfCalls};
   const visibleCoordinates=[...document.querySelectorAll('#chart .coord-num')].filter(e=>getComputedStyle(e).visibility!=='hidden').length;
   slider.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
   return {start,frames,samples,mathError,areaRelativeError,labelOverflow,inputLag,calls,visibleCoordinates};
  },{steps,name});
  await page.waitForFunction(()=>typeof TaxMotion==='undefined'||!TaxMotion.pending,null,{timeout:15000});
  const settled=await page.evaluate(()=>{
   const chart=document.getElementById('chart').getBoundingClientRect();let overflow=0;
   for(const e of document.querySelectorAll('#chart .coord-num')){
    if(e.getAttribute('text-anchor')==='middle')continue;
    const r=e.getBoundingClientRect();overflow=Math.max(overflow,chart.left+1-r.left,r.right-chart.left-sx(0)+1);
   }
   return {calls:{...__taxPerfCalls},overflow,labels:document.querySelectorAll('#chart .coord-num').length,
    hero:document.getElementById('ans-hero').textContent,summary:document.getElementById('info-tax').textContent,
    animations:document.getAnimations().filter(a=>a.effect?.getTiming().iterations===Infinity).length};
  });
  await page.waitForTimeout(900);
  const idle=await page.evaluate(()=>({...__taxPerfCalls}));
  await page.evaluate(()=>{setTax(STATE.tax);buildAnswer();});
  const exact=await page.evaluate(()=>({hero:document.getElementById('ans-hero').textContent,summary:document.getElementById('info-tax').textContent}));
  // Одинаковое конечное состояние отделяет удержание DOM от нового содержания.
  await page.evaluate(()=>setTax(20));await page.waitForTimeout(900);
  const after=await memory();
  const all=[data.start,...data.frames];
  const geometry={};
  for(const key of ['wrap','chart','origin','plot','window']){
   geometry[key]=all[0][key].map((_,i)=>delta(all.map(g=>g[key][i])));
  }
  const summary={name,engine,width,theme,steps,run,round,p50:pct(data.samples.map(s=>s.handler),.5),
   p95:pct(data.samples.map(s=>s.handler),.95),frameP95:pct(data.samples.map(s=>s.elapsed),.95),
   calls:data.calls,geometry,mathError:data.mathError,areaRelativeError:data.areaRelativeError,labelOverflow:data.labelOverflow,inputLag:data.inputLag,before,after,
   settleRedraw:(settled.calls.redrawAll||0)-(data.calls.redrawAll||0),
   idleRedraw:(idle.redrawAll||0)-(settled.calls.redrawAll||0),settled,errors};
  console.log(JSON.stringify(summary));reports.push({summary,data});
  await page.screenshot({path:path.join(out,`${name}-${engine}-${width}-${theme}-${round}-${run}.png`)});
  if(!measureOnly){
   check((data.calls.redrawAll||0)===0,`${name}: ${data.calls.redrawAll} полных перестроек во время жеста`);
   check(data.calls.redrawScene===steps,`${name}: ${data.calls.redrawScene} сборок SVG на ${steps} вводов`);
   check(data.calls.recompute===steps,`${name}: ${data.calls.recompute} расчётов на ${steps} вводов`);
   check((data.calls.updateTaxPanel||0)===0&&(data.calls.buildAnswer||0)===0,`${name}: тяжёлая панель обновляется во время жеста`);
   check(data.visibleCoordinates===0,`${name}: меняющиеся координаты видны во время жеста`);
   if(name==='unit')check(data.start.margin.left<100,`${name}: постоянное широкое поле ${data.start.margin.left} px`);
   check(data.inputLag===0,`${name}: расчёт отстаёт от ввода на ${data.inputLag}`);
   check((data.calls.renderCurveList||0)===0,`${name}: пересозданы поля функций`);
   check(geometry.wrap.every(x=>x<=1)&&geometry.chart.every(x=>x<=1),`${name}: движется контейнер`);
   check(geometry.origin.every(x=>x<=1)&&geometry.plot.every(x=>x<=1),`${name}: движется координатная плоскость`);
   check(geometry.window.every(x=>x===0),`${name}: изменилось окно модели`);
   check(data.mathError<1e-9,`${name}: ошибка чисел ${data.mathError}`);
   check(data.labelOverflow<=1,`${name}: точная подпись вышла из своего поля на ${data.labelOverflow} px`);
   check(settled.overflow<=1&&settled.labels>0,`${name}: точные подписи после жеста отсутствуют или не помещаются (${settled.overflow} px)`);
   check(settled.hero===exact.hero&&settled.summary===exact.summary,`${name}: отложенный ответ отличается от синхронного точного`);
   check(summary.settleRedraw>=1&&summary.settleRedraw<=6,`${name}: неконтролируемые перестройки при завершении ${summary.settleRedraw}`);
   check(settled.animations===0,`${name}: индикатор продолжает жить после ответа`);
   check(summary.idleRedraw===0,`${name}: перерисовки после затишья`);
   check(after.nodes-before.nodes<500,`${name}: удержано ${after.nodes-before.nodes} узлов DOM`);
   if(cdp)check(after.jsEventListeners-before.jsEventListeners<20,`${name}: накапливаются слушатели`);
   check(!errors.length,`${name}: ${errors.join('; ')}`);
  }
  await ctx.close();
 }
 }
} finally {await browser.close();}
fs.writeFileSync(path.join(out,`result-${engine}-${width}-${theme}.json`),JSON.stringify({reports,failures},null,2));
console.log(failures.length?'FAIL: '+failures.join('\n'):'PASS: '+cases.length+' сценариев');
process.exitCode=failures.length?1:0;
