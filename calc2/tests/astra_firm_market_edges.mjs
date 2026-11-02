import * as pw from'playwright';import{readFile}from'node:fs/promises';
let total=0,bad=0;const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6*Math.max(1,Math.abs(b));
const check=(name,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(r):''));};
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/47-firm-market.draft.js','utf8')});
 const solve=(c,D,n)=>p.evaluate(({c,D,n})=>{const r=firmMarketSolve(c,D,n);return{...r,firm:undefined,D:undefined};},{c,D,n});
 for(let i=0;i<50;i++){
  const a=1+i%5,B=1+i%3,A=300+7*i,n=3+i%13,b0=i%17,F=10+i*3,u=i%9;
  const c={expr:`${a}*Q^2+${b0}*Q+${F}`,tax:{type:'unit',rate:u}},P=(2*a*A+n*(b0+u))/(2*a*B+n),q=(P-b0-u)/(2*a),profit=a*q*q-F;
  const r=await solve(c,`Q=${A}-${B}*P`,n);check(engine+' независимаяSR '+i,near(r.P,P)&&near(r.q,q)&&near(r.profit,profit),r);
  const ql=Math.sqrt(F/a),Pl=b0+u+2*Math.sqrt(a*F),nl=(A-B*Pl)/ql;
  const l=await solve({...c,period:'lr'},`Q=${A}-${B}*P`,n);check(engine+' независимаяLR '+i,near(l.P,Pl)&&near(l.q,ql)&&near(l.n,nl)&&near(l.profit,0),l);
 }
 for(const[c,D,n,want]of[
  [{expr:'Q^2'},'Q=100/P',10,{P:Math.sqrt(20),q:Math.sqrt(5)}],
  [{expr:'Q^2'},'P=100/Q',10,{P:Math.sqrt(20),q:Math.sqrt(5)}],
  [{expr:'Q^2'},'P=20',10,{P:20,q:10}],
  [{expr:'Q^4',K:10},'Q=100/P',10,{P:4*Math.pow(2.5,.75),q:Math.pow(2.5,.25)}],
  [{expr:'Q^4+3',period:'lr',K:10},'Q=100-P',10,{P:4,q:1,n:96}],
  [{expr:'Q^2+100',period:'lr',K:5},'Q=100-P',10,{P:25,q:5,n:15}],
  [{expr:'Q^2+100',period:'lr',tax:{type:'lump',rate:125}},'Q=100-P',10,{P:30,q:15,n:14/3}],
 ]){const r=await solve(c,D,n);check(engine+' край '+JSON.stringify([c,D]),Object.entries(want).every(([k,v])=>near(r[k],v)),r);}
 for(const[c,D,n]of[[{},'Q=100+P',10],[{},'Q=100-P',0],[{},'Q=100-P',-3],[{expr:'Q^2',tax:{type:'revenue',rate:101}},'Q=100-P',10]]){const r=await solve(c,D,n);check(engine+' неверныйввод',!!r.error&&!r.found,r);}
 let r=await solve({expr:'16*Q',period:'lr',K:10},'Q=100-P',10);check(engine+' LR плоский участок (0;10]',near(r.P,16)&&r.ranges[0][0]===0&&r.ranges[0][1]===10&&r.rangeClosed[0][0]===false&&r.rangeClosed[0][1]===true,r);
 r=await solve({expr:'Q^2+100*Q'},'Q=50-P',10);check(engine+' нулевая торговля:цены[50;100]',near(r.P,50)&&r.nonunique&&near(r.priceInterval?.[0],50)&&near(r.priceInterval?.[1],100),r);
 r=await solve({expr:'Q^2',tax:{type:'revenue',rate:100}},'Q=50-P',10);check(engine+' налог100%:нулевая торговля,цены[50;∞)',near(r.P,50)&&r.nonunique&&r.priceInterval?.[1]===Infinity,r);
 await b.close();
}
console.log(`Э11 края: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
