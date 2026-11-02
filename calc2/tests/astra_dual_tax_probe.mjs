/* Э4: два независимых бюджетных инструмента, затем история и ссылка. */
import * as pw from 'playwright';
import {keepAnswerOpen} from './answer_open.mjs';
import {installShownReader,parseShown} from './parse_shown.mjs';
let total=0,bad=0;
const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
for(const engine of (process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);
 const p=await b.newPage({viewport:{width:1440,height:950},reducedMotion:'reduce'}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');await installShownReader(p);
 const ready=await p.evaluate(()=>typeof addSecondTax==='function');check(engine+' вторая строка существует',ready);
 if(!ready){await b.close();continue;}
 const setup=async()=>p.evaluate(()=>{
  resetSceneMemory();pickScene('taxes');
  updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),'Q=180-P');
  updateCurveExpr(STATE.curves.find(c=>c.role==='supply'),'Q=3P-60');
  renderCurveList();setType('subsidy');setTaxForm('unit');setTaxSide('buyer');setTax(12);historyBaseline();
 });
 const read=async()=>p.evaluate(()=>({eq:STATE.taxEq,pair:STATE.taxPair,budget:STATE.budget,cs:STATE.csTax,ps:STATE.psTax,dwl:STATE.dwl,
  axes:[...document.querySelectorAll('#chart text.coord-num')].map(e=>e.textContent),
  texts:[...document.querySelectorAll('#ans-hero .ans-val')].map(__readShownText),
  table:[...document.querySelectorAll('#info-tax .tx-table tr')].map(r=>[...r.children].map(__readShownText)),
  paths:document.querySelectorAll('#chart [data-tax-pair-curve]').length,
  wedges:document.querySelectorAll('#chart [data-tax-pair-wedge]').length,
  katex:document.querySelectorAll('.katex-error').length,tex:buildTex('','')}));
 await setup();await p.locator('#tax-add-second').click();
 await p.evaluate(()=>setSecondTax({type:'tax',form:'unit',side:'seller',rate:24}));await p.evaluate(()=>buildAnswer());
 let r=await read();
 for(const [k,v]of Object.entries({Q:111,Pb:69,Ps:57,Pm:81}))check(engine+' 9.13д '+k,near(r.eq[k],v),r.eq);
 for(const [k,v]of Object.entries({budget:1332,cs:6160.5,ps:2053.5,dwl:54}))check(engine+' 9.13д '+k,near(r[k],v),r[k]);
 check(engine+' налог +2664',r.pair.items.some(x=>near(x.budget,2664)),r.pair);
 check(engine+' субсидия −1332',r.pair.items.some(x=>near(x.budget,-1332)),r.pair);
 check(engine+' две сдвинутые кривые',r.paths===2,r.paths);
 check(engine+' два самостоятельных клина',r.wedges===2,r.wedges);
 check(engine+' рынок 81 виден в ответе',r.texts.some(x=>near(parseShown(x),81)),r.texts);
 check(engine+' статьи бюджета видны',r.table.some(x=>x.some(t=>near(parseShown(t),2664)))&&r.table.some(x=>x.some(t=>near(parseShown(t),-1332))),r.table);
 check(engine+' KaTeX без ошибок',r.katex===0,r.katex);
 check(engine+' экспорт обеих функций',r.tex.includes('81')&&r.tex.includes('111'),r.tex.slice(-700));
 const exportState=await p.evaluate(()=>{
  const before=JSON.stringify(compactModelState(collectModelState())),tex=buildTex('','');
  const after=JSON.stringify(compactModelState(collectModelState()));
  return{same:before===after,records:[...document.querySelectorAll('#chart [data-tax-pair-curve]')].map(e=>math.evaluate(e.dataset.expr,{Q:11})),
   plots:tex.split('\n').filter(l=>l.includes('addplot')&&l.includes('192')).length};
 });
 check(engine+' обе кривые объявляют правильную формулу экспорту',exportState.records.length===2&&near(exportState.records[0],181)&&near(exportState.records[1],143/3),exportState);
 check(engine+' бумажный прогон сохраняет состояние',exportState.same,exportState);
 check(engine+' сдвинутый спрос экспортирован формулой',exportState.plots>0,exportState);
 const link=await p.evaluate(()=>shareLinkOf());
 const clone=await b.newPage();await clone.goto(link);await clone.waitForFunction(()=>STATE.taxPair&&STATE.taxActive);
 check(engine+' ссылка сохраняет вторую строку',await clone.evaluate(()=>STATE.taxSecond.rate===24&&Math.abs(STATE.taxEq.Pm-81)<1e-6));await clone.close();
 const self=await p.evaluate(()=>{setSelfMode(true);buildAnswer();return{fields:document.querySelectorAll('#ans-hero .self-inp').length,
  axes:[...document.querySelectorAll('#chart text.coord-num')].map(e=>e.textContent),
  Q:[...document.querySelectorAll('#ans-hero .ans-cell')].findIndex(c=>selfNot(c)==='Q'),
  P:[...document.querySelectorAll('#ans-hero .ans-cell')].findIndex(c=>selfNot(c)==='Pm'),
  hidden:!selfPointOpen(111,81)};});
 await p.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 check(engine+' самопроверка скрывает новую цену',self.fields===5&&self.hidden&&!self.axes.some(x=>/\d/.test(x)),self);
 for(const [i,value]of [[self.Q,'111'],[self.P,'81']])if(i>=0){const c=p.locator('#ans-hero .ans-cell').nth(i);await c.locator('.self-inp').fill(value);await c.locator('.self-check').click();}
 check(engine+' правильный ответ открывает рыночную точку',await p.evaluate(()=>selfPointOpen(111,81)));
 await p.evaluate(()=>{setSelfMode(false);buildAnswer();});
 await p.evaluate(()=>{historyCheck();historyBaseline();historyMark('ставка второго инструмента');setSecondTax({rate:30});historyCheck();});
 await p.evaluate(()=>historyUndo());check(engine+' отмена второй ставки',await p.evaluate(()=>STATE.taxSecond.rate===24&&Math.abs(STATE.taxEq.Q-111)<1e-6));
 await p.evaluate(()=>historyRedo());check(engine+' повтор второй ставки',await p.evaluate(()=>STATE.taxSecond.rate===30&&Math.abs(STATE.taxEq.Q-106.5)<1e-6));
 await setup();await p.evaluate(()=>{setType('tax');setTaxForm('vat');setTax(20);addSecondTax();setSecondTax({type:'subsidy',form:'subbuyer',rate:10});buildAnswer();});r=await read();
 check(engine+' НДС и процентная субсидия Q',near(r.eq.Q,116),r.eq);
 check(engine+' НДС и процентная субсидия разные базы',near(r.eq.Pb,64)&&near(r.eq.Ps,176/3)&&near(r.budget,1856/3),r);
 // Независимый перебор количества: ни формула равновесия, ни решатель приложения здесь не вызываются.
 let best={gap:Infinity};for(let i=0;i<=180000;i++){const q=i/1000,pb=180-q,ps=20+q/3,gap=Math.abs(pb-ps-.2*ps+.1*pb);if(gap<best.gap)best={gap,q,pb,ps};}
 check(engine+' две процентные формы совпадают с перебором',Math.abs(r.eq.Q-best.q)<.0011,best);
 await setup();await p.evaluate(()=>{addSecondTax();setSecondTax({type:'tax',form:'unit',side:'seller',rate:12});buildAnswer();});r=await read();
 check(engine+' взаимная компенсация сохраняет оба потока',near(r.budget,0)&&near(r.eq.Q,120)&&near(r.eq.Pm,72)&&r.pair.items.some(x=>near(x.budget,1440))&&r.pair.items.some(x=>near(x.budget,-1440)),r.pair);
 check(engine+' нулевое сальдо не прячет клинья',r.wedges===2,r.wedges);
 await p.evaluate(()=>{removeSecondTax();buildAnswer();});r=await read();
 check(engine+' удаление возвращает одиночную субсидию',!r.pair&&near(r.eq.Q,129)&&near(r.budget,-1548),r);
 await p.evaluate(()=>{addSecondTax();setTax(0);setSecondTax({type:'tax',form:'unit',rate:24});});r=await read();
 check(engine+' нулевая первая ставка не отключает вторую',near(r.eq.Q,102)&&near(r.budget,2448),r.eq);
 await p.evaluate(()=>pickScene('sd'));check(engine+' другая модель чистая',await p.evaluate(()=>!STATE.taxSecond&&!STATE.taxPair));
 check(engine+' нет JS ошибок',!errors.length,errors);await b.close();
}
console.log(`Э4: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
