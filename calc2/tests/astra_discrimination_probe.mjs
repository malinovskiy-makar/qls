/* Э5: независимые контрольные числа, FC, выпадение группы и общий TC. */
import * as pw from 'playwright';
import {keepAnswerOpen} from './answer_open.mjs';
let total=0,bad=0;
const check=(name,ok,detail)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(detail):''));};
const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-5;
for(const engine of (process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);
 const p=await b.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),errors=[];
 p.on('pageerror',e=>errors.push(e.message));await p.goto(process.env.CALC2_BASE_URL+'/calc2/');
 await p.waitForFunction(()=>typeof pickScene==='function');
 const setup=async(d2='120-Q',cost='30')=>p.evaluate(({d2,cost})=>{
  resetSceneMemory();pickScene('mono-d3');STATE.d3D1='180-Q';STATE.d3D2=d2;STATE.d3MC=cost;
  for(const [id,text]of [['inp-d3-1',STATE.d3D1],['inp-d3-2',d2],['inp-d3-mc',cost]])setFormulaFieldQuiet(document.getElementById(id),text);
  redrawAll();buildAnswer();
  const d=STATE.discr3;return{q1:d.q1,q2:d.q2,P1:d.P1,P2:d.P2,Q:d.Qtot,comparison:d.comparison};
 },{d2,cost});
 let r=await setup();check(engine+' сравнение существует',!!r.comparison,r);
 if(r.comparison){
  for(const [k,v]of Object.entries({q1:75,q2:45,P1:105,P2:75,Q:120}))check(engine+' 6.25 '+k,near(r[k],v),r[k]);
  const c=r.comparison;
  for(const [tag,x,w]of [['дискриминация',c.discrimination,{profit:7650,dwl:3825}],['единая цена',c.uniform,{P:90,q1:90,q2:30,profit:7200,dwl:3600}]])
   for(const[k,v]of Object.entries(w))check(engine+' 6.25 '+tag+' '+k,near(x[k],v),x[k]);
  check(engine+' 6.25 CS дискриминация',near(c.discrimination.cs[0],2812.5)&&near(c.discrimination.cs[1],1012.5),c);
  check(engine+' 6.25 CS единая',near(c.uniform.cs[0],4050)&&near(c.uniform.cs[1],450),c);
  check(engine+' 6.25 прирост прибыли',near(c.delta,450),c.delta);
  r=await setup('120-Q','TC=30*Q+200');
  check(engine+' FC вычтен в обоих режимах',near(r.comparison?.discrimination.profit,7450)&&near(r.comparison?.uniform.profit,7000),r.comparison);
  r=await setup('40-Q','30');
  check(engine+' единая цена исключает вторую группу',near(r.comparison?.uniform.P,105)&&near(r.comparison?.uniform.q1,75)&&near(r.comparison?.uniform.q2,0),r.comparison);
  check(engine+' прибыль при выпадении группы',near(r.comparison?.uniform.profit,5625)&&near(r.comparison?.delta,25),r.comparison);
  r=await setup('120-Q','TC=0.5*Q^2+30*Q+200');
  check(engine+' TC зависит от общего выпуска',near(r.Q,60)&&near(r.q1,45)&&near(r.q2,15),r);
  check(engine+' общий TC: прибыль и потери',near(r.comparison?.discrimination.profit,3850)&&near(r.comparison?.discrimination.dwl,525)&&near(r.comparison?.uniform.profit,3550)&&near(r.comparison?.uniform.dwl,700),r.comparison);
  // Независимо перебираем единую цену: на верхней ветке оптимум P=130, Q=50.
  // Кандидат P=120, Q=60 на изломе даёт только 3400, поэтому не выбирается.
  let best={profit:-Infinity};for(let i=0;i<=180000;i++){const price=i/1000,a=Math.max(0,180-price),b=Math.max(0,120-price),Q=a+b,profit=price*Q-.5*Q*Q-30*Q-200;if(profit>best.profit)best={profit,price,Q};}
  check(engine+' общий TC: единая цена против независимого перебора',near(r.comparison.uniform.profit,best.profit)&&near(r.comparison.uniform.P,best.price),{got:r.comparison.uniform,best});
  const exp=await p.evaluate(()=>{
   const before=JSON.stringify(compactModelState(collectModelState())),tex=buildTex('','');
   return{same:before===JSON.stringify(compactModelState(collectModelState())),tex:tex.length,
    snap:snapTargetsAll().filter(t=>/^MC/.test(t.name)).map((t,i)=>t.f(i===0?45:15)),
    mc:[...document.querySelectorAll('#chart path[data-expr-name="MC"]')].map((e,i)=>math.evaluate(e.dataset.expr,{Q:i===0?45:15}))};
  });
  check(engine+' экспорт MC учитывает выпуск другой группы',exp.mc.length===2&&exp.mc.every(v=>near(v,90)),exp);
  check(engine+' точки и площади используют те же MC',exp.snap.length===2&&exp.snap.every(v=>near(v,90)),exp);
  check(engine+' бумажный прогон сохраняет модель',exp.same&&exp.tex>500,exp);
  const link=await p.evaluate(()=>shareLinkOf()),clone=await b.newPage();await clone.goto(link);
  await clone.waitForFunction(()=>STATE.discr3?.comparison?.fc===200);
  check(engine+' ссылка несёт TC и сравнение',await clone.evaluate(()=>STATE.d3MC.includes('TC=')&&Math.abs(STATE.discr3.comparison.uniform.profit-3550)<1e-6));await clone.close();
  await p.evaluate(()=>{historyCheck();historyBaseline();historyMark('Общие затраты');const input=document.getElementById('inp-d3-mc');input.value='TC=0.5*Q^2+30*Q+500';input.dispatchEvent(new Event('change',{bubbles:true}));historyCheck();});
  await p.evaluate(()=>historyUndo());check(engine+' отмена TC',await p.evaluate(()=>STATE.discr3.comparison.fc===200));
  await p.evaluate(()=>historyRedo());check(engine+' повтор TC',await p.evaluate(()=>STATE.discr3.comparison.fc===500));
  await p.evaluate(()=>{setSelfMode(true);buildAnswer();});await p.waitForTimeout(150);
  const self=await p.evaluate(()=>({fields:document.querySelectorAll('#ans-hero .self-inp').length,
   hidden:!document.querySelector('.d3-comparison').getClientRects().length,
   axes:[...document.querySelectorAll('#chart text.coord-num')].map(e=>e.textContent)}));
  check(engine+' самопроверка скрывает сравнение и координаты',self.fields>=2&&self.hidden&&!self.axes.some(t=>/\d/.test(t)),self);
  await p.locator('#self-showall').click();
  check(engine+' показать всё открывает сравнение',await p.locator('.d3-comparison').isVisible());
  await p.evaluate(()=>setSelfMode(false));
 }
 const d1=await p.evaluate(()=>{
  resetSceneMemory();pickScene('mono-d1');updateCurveExpr(curveByRoleAny('demand'),'120-Q');
  const c=mcSourceCurveAny();updateCurveExpr(c,'Q^2+30*Q+200');setRole(c,'tc');redrawAll();
  return STATE.discr1;
 });
 check(engine+' 6.27 выпуск 30',near(d1?.Qcomp,30),d1);
 check(engine+' 6.27 прибыль с FC 1150',near(d1?.profit,1150),d1);
 check(engine+' нет ошибок JS',!errors.length,errors);await b.close();
}
console.log(`Э5: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
