import * as pw from'playwright';let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
let seed=8155;const rnd=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};
const cases=Array.from({length:30},()=>{const a=80+20*rnd(),b=.2+.5*rnd(),I0=40,d=1+3*rnd(),G=20,T=10,Xn=0,k=.5+rnd(),h=.5+rnd(),c0=20,P=1+2*rnd(),rate=1+5*rnd(),A=a-b*T+I0+G,output=(A-d*rate)/(1-b),Ms=P*(c0+k*output-h*rate),B=Ms/P-c0,den=h*(1-b)+d*k;return{c:{a,b,I0,d,G,T,Xn,P,Ms,md:c0+'+'+k+'*Y-'+h+'*r'},Y:(h*A+d*B)/den,r:(k*A-(1-b)*B)/den,kg:h/den,kt:-b*h/den};});
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 for(const[c,i]of cases.map((c,i)=>[c,i])){const r=await p.evaluate(c=>{const r=islmSolve(c);return{Y:r.eq?.Q,r:r.eq?.P,kg:r.kG,kt:r.kT,error:r.error};},c.c);check(engine+' независимая система двух уравнений '+i,near(r.Y,c.Y)&&near(r.r,c.r)&&near(r.kg,c.kg)&&near(r.kt,c.kt),{r,want:c});}
 for(const[c,w]of[
  [{a:10,b:0,I0:0,d:1,G:0,T:0,Xn:0,md:'Y^2-r',Ms:10,P:1},{Y:4,r:6,kg:1/9}],
  [{md:'.4*Y',Ms:200,P:1},{Y:500,r:26,kg:0}],
  [{md:'100-2*r',Ms:80,P:1},{Y:516,r:10,kg:5}],
  [{Ms:420.8,P:2},{Y:526,r:0,kg:2.5}]
 ]){const r=await p.evaluate(c=>{const r=islmSolve(c);return{Y:r.eq?.Q,r:r.eq?.P,kg:r.kG,error:r.error};},c);check(engine+' особая LM '+c.md,near(r.Y,w.Y)&&near(r.r,w.r)&&near(r.kg,w.kg),{r,w});}
 const invalid=await p.evaluate(()=>[{b:1},{P:0},{Ms:-1},{d:-1},{a:10,b:0,I0:0,d:0,G:0,T:0,Xn:0,md:'(r-1)*(r-3)+10',Ms:10,P:1}].map(c=>islmSolve(c).error));check(engine+' границы и неоднозначное равновесие',invalid.every(Boolean)&&/несколько/.test(invalid.at(-1)),invalid);
 const shock=await p.evaluate(()=>{const p={input:'params',params:islmDefaults(),shock:{G:16,T:0,Ms:64},holdRate:false};const r=islmScenario(p);return{Y:r.changes?.Y,r:r.changes?.r,I:r.changes?.I,crowding:r.crowdingY,crowdingI:r.crowdingI,error:r.error};});check(engine+' совместный шок G16 Ms64 сохраняет ставку',near(shock.Y,80)&&near(shock.r,0)&&near(shock.I,0)&&near(shock.crowding,40)&&near(shock.crowdingI,8),shock);
 await b.close();
}
console.log(`Края Э8: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
