import * as pw from 'playwright';import {keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);const p=await b.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 const setup=async(rows,Q)=>p.evaluate(({rows,Q})=>{resetSceneMemory();pickScene('plants');setPlantInputRows(rows.map(([expr,K,kind])=>({expr,K:K??null,kind:kind||'sunk'})));STATE.plQ=Q;renderPlantRows(true);redrawAll();return{r:plantsAt(Q),pieces:STATE.plants?.pieces,error:STATE.plErr};},{rows,Q});
 let r=await setup([['10*Q'],['Q^2']],12);
 check(engine+' 4.18г раздел7/5',near(r.r?.q1,7)&&near(r.r?.q2,5),r);
 check(engine+' 4.18г TC95 MC10 интеграл95',near(r.r?.tcDirect,95)&&near(r.r?.m,10)&&near(r.r?.vc,95),r);
 check(engine+' 4.18г куски Q² и10Q−25',r.pieces?.length===2&&near(r.pieces[0].a,1)&&near(r.pieces[0].hi,5)&&near(r.pieces[1].b,10)&&near(r.pieces[1].c,-25),r.pieces);
 r=await setup([['10*Q'],['6*Q']],12);
 check(engine+' угловое решение0/12 TC72',near(r.r?.q1,0)&&near(r.r?.q2,12)&&near(r.r?.tcDirect,72)&&near(r.r?.vc,72),r);
 check(engine+' угол не назван равенством MC',!await p.locator('#info-plants').textContent().then(t=>/MC.\s*=\s*MC./.test(t)));
 r=await setup([['Q^2'],['Q^2']],12);check(engine+' 4.19а TC=Q²/2',r.pieces?.length===1&&near(r.pieces[0].a,.5)&&near(r.r?.tcDirect,72),r);
 const rows=[['Q^2+5',4],['.5*Q^2+12',null,'quasi'],['3*Q',6]];
 for(const[Q,qs,tc]of[[3,[1.5,0,1.5],11.75],[8,[2,0,6],27],[10,[4,0,6],39],[12,[2,4,6],47]]){
  r=await setup(rows,Q);check(engine+' независимый Python Q'+Q,r.r?.qs.every((q,i)=>near(q,qs[i]))&&near(r.r.tcDirect,tc),r);
  check(engine+' мощности соблюдены Q'+Q,r.r?.qs[0]<=4+1e-8&&r.r?.qs[2]<=6+1e-8,r.r);
 }
 r=await setup([['16*Q-Q^2',8],['10*Q']],10);check(engine+' вогнутые затраты: глобальный минимум',near(r.r?.q1,8)&&near(r.r?.q2,2)&&near(r.r?.tcDirect,84),r);
 r=await setup([['Q^2',3],['2*Q^2',4]],8);check(engine+' выше суммарной мощности нет ответа',!r.r&&!r.error,r);
 r=await setup([['Q^2+12',null,'quasi']],0);check(engine+' закрытый завод не платит квазипостоянные',near(r.r?.tcDirect,0),r);
 r=await setup([['Q^2+12']],0);check(engine+' невозвратные при нуле остаются',near(r.r?.tcDirect,12),r);
 r=await setup([['10*Q'],['Q^2']],12);
 const unbounded=await p.evaluate(()=>{setPlantInputRows([{expr:'Q^2',K:null,kind:'sunk'},{expr:'2*Q^2',K:null,kind:'sunk'}]);STATE.plQ=180;redrawAll();return plantsAt(180);});
 check(engine+' без K нет прежнего фиктивного предела100',near(unbounded?.q1,120)&&near(unbounded?.q2,60)&&near(unbounded?.tcDirect,21600),unbounded);
 const axis=await p.locator('#chart text.axis-name').allTextContents();check(engine+' ось TC',axis.includes('TC')&&!axis.includes('P'),axis);
 await p.evaluate(()=>setPlantsView('mc'));const mc=await p.locator('#chart path[data-expr-name]').evaluateAll(es=>es.map(e=>e.dataset.exprName));check(engine+' сумма MC и обе исходные',mc.includes('MC')&&mc.includes('MC_1')&&mc.includes('MC_2'),mc);
 check(engine+' нет ошибок JS',!errors.length,errors);await b.close();
}
console.log(`Э6: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
