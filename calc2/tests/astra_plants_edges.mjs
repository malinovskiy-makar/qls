import * as pw from'playwright';import fs from'node:fs';
const cases=JSON.parse(fs.readFileSync(new URL('./fixtures/astra_plants_grid.json',import.meta.url)));
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof plantsExactPieces==='function');
 for(const[c,x]of cases.entries()){
  const r=await p.evaluate(x=>{const ss=x.rows.map(r=>({...r,poly:{a:r.a,b:r.b,c:r.c}})),ps=plantsExactPieces(ss),r=plantsExactAt(ps,x.Q,ss);return r;},x);
  // Сеточный минимум не ниже непрерывного; ошибка округления квадратичных
  // гладких участков при шаге .02 меньше .01 для этих коэффициентов.
  check(engine+' Python-перебор '+c,r&&r.tcDirect<=x.tc+1e-6&&r.tcDirect>=x.tc-.011,{got:r,want:x});
 }
 const large=await p.evaluate(()=>{const ss=plantsCompile([{expr:'Q^2+100000000000000',K:null,kind:'quasi'},{expr:'2*Q^2',K:null,kind:'sunk'}]);return plantsExactAt(plantsExactPieces(ss),20000000,ss);});
 check(engine+' большой FC: точка включения не пропущена',large&&Math.abs(large.q1-40000000/3)<1e-5&&Math.abs(large.tcDirect-(1e14+8e14/3))<1,large);
 const extra=await p.evaluate(()=>{
  resetSceneMemory();pickScene('plants');setPlantInputRows([{expr:'Q^3',K:null,kind:'sunk'},{expr:'Q^3',K:null,kind:'sunk'}]);STATE.plQ=8;
  const t=performance.now();redrawAll();const r=plantsAt(8),time=performance.now()-t;return{r,time,error:STATE.plErr};
 });
 check(engine+' нелинейные Q³: равный раздел',extra.r&&Math.abs(extra.r.q1-4)<1e-5&&Math.abs(extra.r.q2-4)<1e-5&&Math.abs(extra.r.tcDirect-128)<1e-5,extra);
 check(engine+' численный способ честно помечен',extra.r?.approx===true,extra);
 check(engine+' нелинейный расчёт не блокирует интерфейс',extra.time<5000,extra.time);console.log('PERF',engine,extra.time.toFixed(1)+' ms');
 await b.close();
}
console.log(`Края Э6: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
