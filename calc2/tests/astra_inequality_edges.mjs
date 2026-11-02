import * as pw from'playwright';let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
let seed=731;const rnd=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};
// Независимая формула Джини: средняя попарная разность индивидуальных доходов.
const gini=(p,y)=>{const N=p.reduce((a,b)=>a+b,0),I=p.reduce((a,v,i)=>a+v*y[i],0);return p.reduce((s,v,i)=>s+p.reduce((t,w,j)=>t+v*w*Math.abs(y[i]-y[j]),0),0)/(2*N*I);};
const cases=Array.from({length:40},()=>{const n=2+Math.floor(rnd()*8),m=2+Math.floor(rnd()*8),p=Array.from({length:n},()=>1+Math.floor(rnd()*100)),q=Array.from({length:m},()=>1+Math.floor(rnd()*100)),y=p.map(()=>Math.floor(rnd()*100)),z=q.map(()=>Math.floor(rnd()*100));return{p,q,y,z,g:gini([...p,...q],[...y,...z])};});
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 for(const[c,i]of cases.map((c,i)=>[c,i])){const r=await p.evaluate(c=>{const a=ineqDistribution({input:'groups',groupMode:'counts',pops:c.p,groups:c.y}),b=ineqDistribution({input:'groups',groupMode:'counts',pops:c.q,groups:c.z});return ineqUnion([a,b],[c.p.reduce((a,b)=>a+b),c.q.reduce((a,b)=>a+b)],[c.p.reduce((s,n,i)=>s+n*c.y[i],0),c.q.reduce((s,n,i)=>s+n*c.z[i],0)]).stats?.gini;},c);check(engine+' независимые попарные разности '+i,Math.abs(r-c.g)<1e-10,{r,want:c.g});}
 const r=await p.evaluate(()=>{const start=performance.now(),d=ineqUnion([ineqDistribution({input:'formula',formula:'p^2'}),ineqDistribution({input:'formula',formula:'p'})],[1,1],[1,1]);return{g:d.stats.gini,approx:d.approx,res:d.resolution,error:d.errorBound,ms:performance.now()-start};});check(engine+' перекрытие Uniform(0,2) и доход1:5/24',Math.abs(r.g-5/24)<1e-7&&r.approx,r);check(engine+' численное объединение <5с',r.ms<5000,r);
 const rd=await p.evaluate(()=>{resetSceneMemory();pickScene('ineq');STATE.ineqPops=[60,40];STATE.ineqGroups=[30,70];STATE.ineqRedistOn=true;STATE.ineqTau=.5;recomputeInequality();return{g:STATE.ineqRedist.stats.gini,pts:STATE.ineqRedist.lorenz};});check(engine+' налог учитывает население: G .15',Math.abs(rd.g-.15)<1e-9,rd);
 const reversed=await p.evaluate(()=>ineqUnion([ineqDistribution({input:'formula',formula:'p'}),ineqDistribution({input:'formula',formula:'p^2'})],[1,3],[1,1]).stats.gini);check(engine+' перестановка стран не меняет13.18',Math.abs(reversed-3/8)<1e-9,reversed);
 const bads=await p.evaluate(()=>[[0,100],[-1,101],['Infinity',1]].map(pops=>!!ineqDistribution({input:'groups',groupMode:'counts',pops,groups:[10,20]}).error));check(engine+' нулевая отрицательная бесконечная численность',bads.every(Boolean),bads);
 await b.close();
}
console.log(`Края Э7: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
