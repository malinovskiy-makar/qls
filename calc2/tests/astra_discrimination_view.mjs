import * as pw from 'playwright';import fs from 'node:fs';
import {keepAnswerOpen} from './answer_open.mjs';
import {installShownReader} from './parse_shown.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
for(const engine of (process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);
 for(const width of [1440,1280])for(const theme of ['light','dark']){
  const p=await b.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));await p.addInitScript(t=>localStorage.setItem('theme',t),theme);
  await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof discriminationComparison==='function');await installShownReader(p);
  await p.evaluate(()=>{
   resetSceneMemory();pickScene('mono-d3');
   for(const [id,text]of [['inp-d3-1','180-Q'],['inp-d3-2','120-Q'],['inp-d3-mc','TC=30*Q+200']]){
    const input=document.getElementById(id);input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
   }
  });
  await p.waitForFunction(()=>STATE.discr3?.comparison?.fc===200);await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(350);
  const name=[engine,width,theme].join('/');
  await p.locator('.d3-comparison').scrollIntoViewIfNeeded();
  const r=await p.evaluate(()=>{
   const table=document.querySelector('.d3-comparison'),card=document.getElementById('inp-d3-mc').closest('.fc-card,.field');
   const cells=[...table.querySelectorAll('th,td')];
   const overlaps=cells.filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent);
   const panel=document.getElementById('params-panel');
   return{params:Object.keys(STATE.params||{}),approx:table.textContent.includes('≈'),profit:STATE.discr3.comparison.discrimination.profit,wide:document.documentElement.scrollWidth>innerWidth+1,
    tableWidth:table.getBoundingClientRect().width,panelWidth:panel.getBoundingClientRect().width,overlaps,
    rows:[...table.querySelectorAll('tbody tr')].map(e=>__readShownText(e)),
    name:card.querySelector('.fc-name')?.textContent,prefix:card.querySelector('.fc-prefix')?.textContent,
    errors:[...document.querySelectorAll('.katex-error')].map(e=>e.textContent)};
  });
  check(name+' ввод TC через поле дошёл до расчёта',Math.abs(r.profit-7450)<1e-6,r);
  check(name+' карточка показывает общие издержки',r.name==='Общие издержки от общего выпуска'&&!r.prefix,r);
  check(name+' вся сравнительная таблица помещается',!r.wide&&!r.overlaps.length&&r.tableWidth<=r.panelWidth&&r.rows.length===10,r);
  check(name+' обозначение TC не стало параметром',!r.params.includes('TC'),r.params);
  check(name+' точные контрольные числа без знака приближения',!r.approx,r.rows);
  check(name+' нет ошибок формул',!r.errors.length,r.errors);
  if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e5-shots',{recursive:true});await p.screenshot({path:'.calc2-astra-local/e5-shots/'+name.replaceAll('/','-')+'.png'});}
  await p.evaluate(()=>{resetSceneMemory();pickScene('mono-d1');updateCurveExpr(curveByRoleAny('demand'),'120-Q');renderCurveList();redrawAll();});
  const cid=await p.evaluate(()=>mcSourceCurveAny().id),card=p.locator(`.fc-card[data-cid="${cid}"]`);
  await card.locator('.crow-gear').click();await card.locator('.role-sel').selectOption('tc');
  await p.evaluate(id=>{const input=document.getElementById('curve-expr-'+id);input.value='Q^2+30*Q+200';input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));},cid);
  await p.waitForFunction(()=>Math.abs(STATE.discr1?.profit-1150)<1e-5);
  const d=await p.evaluate(()=>({role:curveByRoleAny('tc')?.role,profit:STATE.discr1.profit,
   curves:[...document.querySelectorAll('#chart path[data-expr]')].map(e=>({name:e.dataset.name,expr:e.dataset.expr})),text:document.getElementById('info-mono').textContent}));
  check(name+' роль TC выбирается через меню',d.role==='tc'&&Math.abs(d.profit-1150)<1e-5,d);
  check(name+' TC не нарисована на оси цены',!d.curves.some(c=>/Q\s*\^\s*2/.test(c.expr)),d);
  if(process.env.SHOTS==='1')await p.screenshot({path:'.calc2-astra-local/e5-shots/d1-'+name.replaceAll('/','-')+'.png'});
  const fit=await p.evaluate(()=>{
   requestFormulaFit();redrawAll();const before=CONFIG.Pmax;
   updateCurveExpr(curveByRoleAny('tc'),'Q^2+30*Q+10000');requestFormulaFit();redrawAll();
   return{before,after:CONFIG.Pmax,names:snapTargetsAll().map(t=>t.name)};
  });
  check(name+' FC не меняют ценовое окно и не создают невидимую кривую',fit.before===fit.after&&!fit.names.includes('TC')&&fit.names.includes('MC'),fit);
  check(name+' нет ошибок JS',!errors.length,errors);await p.close();
 }
 await b.close();
}
console.log(`Вид Э5: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
