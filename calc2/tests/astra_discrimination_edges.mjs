import * as pw from 'playwright';
import {keepAnswerOpen} from './answer_open.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
const near=(a,b,t=1e-5)=>Number.isFinite(a)&&Math.abs(a-b)<t;
for(const engine of (process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);const p=await b.newPage({viewport:{width:1440,height:950},reducedMotion:'reduce'});
 await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof discriminationComparison==='function');
 const run=async(d1,d2,tc)=>p.evaluate(({d1,d2,tc})=>{
  resetSceneMemory();pickScene('mono-d3');STATE.d3D1=d1;STATE.d3D2=d2;STATE.d3MC=tc;
  const t=performance.now();redrawAll();const d=STATE.discr3;
  return {found:d.found,Q:d.Qtot,q1:d.q1,q2:d.q2,c:d.comparison,ms:performance.now()-t};
 },{d1,d2,tc});
 let r=await run('180-Q','120-Q','TC=30*Q+10000');
 check(engine+' большие FC учитываются без изменения переменного оптимума',near(r.Q,120)&&near(r.c?.discrimination.profit,-2350)&&near(r.c?.uniform.profit,-2800),r);
 r=await run('180-Q','120-Q','TC=300*Q+200');
 check(engine+' нулевой выпуск: таблица остаётся и FC учитываются',!r.found&&near(r.c?.discrimination.profit,-200)&&near(r.c?.uniform.profit,-200)&&near(r.c?.discrimination.dwl,0),r);
 r=await run('180-Q','20-Q','30');
 check(engine+' при дискриминации тоже может выпасть группа',near(r.q1,75)&&near(r.q2,0)&&r.c?.discrimination.P2===null&&near(r.c?.delta,0),r);
 r=await run('100-Q','80-2*Q','20');
 check(engine+' неодинаковые наклоны: единая цена и прибыль',near(r.c?.uniform.P,170/3)&&near(r.c?.uniform.profit,6050/3)&&near(r.c?.uniform.dwl,3025/3)&&near(r.c?.delta,100/3),r);
 r=await run('120-Q','80-Q','160-4*Q');
 check(engine+' минимум MR=MC отвергнут: выбрана граница',near(r.c?.uniform.Qtot,40)&&near(r.c?.uniform.profit,0)&&r.c?.uniform.alts.some(q=>near(q,0)),r);
 r=await run('1000-Q','800-Q','30');
 check(engine+' ответ за пределами первоначального окна',near(r.Q,870)&&near(r.c?.uniform.P,465)&&near(r.c?.delta,5000),r);
 // При цене выше горизонтальной группы она не покупает. Сравниваются оба кандидата.
 r=await run('100-Q','50','Q');
 check(engine+' горизонтальная группа: общий оптимум',near(r.q1,25)&&near(r.q2,25),r);
 check(engine+' горизонтальная группа: единая цена',near(r.c?.uniform.P,200/3)&&near(r.c?.uniform.profit,5000/3)&&near(r.c?.delta,625/3),r);
 r=await run('100-Q','80','Q');
 check(engine+' горизонтальная группа принимает остаток при единой цене',near(r.c?.uniform.P,80)&&near(r.c?.uniform.q1,20)&&near(r.c?.uniform.q2,60)&&near(r.c?.uniform.profit,3200)&&near(r.c?.delta,100),r);
 r=await run('100','80','Q');
 check(engine+' две горизонтальные группы',near(r.q1,100)&&near(r.q2,0)&&near(r.c?.uniform.P,100)&&near(r.c?.uniform.profit,5000),r);
 r=await run('Q=180-P','Q=120-P','TC=30*Q+200');
 check(engine+' спрос записан как Q(P)',near(r.c?.uniform.P,90)&&near(r.c?.discrimination.profit,7450),r);
 if(process.env.CHECK!=='linear'){
  r=await run('180-Q^2','120-Q^2','30');
  let best={profit:-Infinity};for(let i=0;i<=180000;i++){const P=i/1000,a=Math.sqrt(Math.max(0,180-P)),b=Math.sqrt(Math.max(0,120-P)),profit=(P-30)*(a+b);if(profit>best.profit)best={P,profit};}
  check(engine+' нелинейные группы: дискриминация',near(r.q1,Math.sqrt(50))&&near(r.q2,Math.sqrt(30)),r);
  check(engine+' нелинейные группы: единая цена против перебора',near(r.c?.uniform.P,best.P,.001)&&near(r.c?.uniform.profit,best.profit,.0001),{r,best});
  check(engine+' нелинейное сравнение не блокирует интерфейс',r.ms<3000,r.ms);
  console.log('PERF '+engine+' нелинейный пересчёт '+r.ms.toFixed(1)+' ms');
 }
 await b.close();
}
console.log(`Края Э5: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
