import * as pw from 'playwright';import{readFile}from'node:fs/promises';import{keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);const p=await b.newPage({viewport:{width:1440,height:1000}});await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/46-firm-supply.draft.js','utf8')});
 const exists=await p.evaluate(()=>typeof firmSupplyBuild==='function');check(engine+' новое ядро существует',exists);if(!exists){await b.close();continue;}
 const solve=async(c,prices)=>p.evaluate(({c,prices})=>{const m=firmSupplyBuild(c);if(m.error)return m;return{shutdown:m.shutdown,K:m.K,exact:m.exact,rows:m.schedule.rows.map(r=>({lo:r.lo,hi:r.hi,expr:r.expr})),values:prices.map(P=>{const r=m.at(P);return{...r,branch:undefined};})};},{c,prices});
 let r=await solve({},[5,6,15]);check(engine+' старт shutdown6, Q0/3/4, прибыль14',near(r.shutdown,6)&&near(r.values?.[0].Q,0)&&near(r.values?.[2].Q,4)&&near(r.values?.[2].profit,14),r);check(engine+' при P6 безразлично 0 или3',r.values?.[1].outputs.length===2&&r.values[1].outputs.every((q,i)=>near(q,[0,3][i])),r);
 check(engine+' старт итоговая функция даёт корень',await p.evaluate(()=>{const m=firmSupplyBuild({});return m.schedule.rows.some(r=>r.expr?.includes('sqrt')&&Math.abs(math.evaluate(r.expr,{P:15})-4)<1e-8);}),r.rows);
 r=await solve({expr:'Q^2+10*Q+100'},[0,10,30]);check(engine+' 7.1б shutdown10,Q10, прибыль0',near(r.shutdown,10)&&near(r.values?.[2].Q,10)&&near(r.values?.[2].profit,0),r);
 r=await solve({expr:'16*Q'},[15,16,17]);check(engine+' 7.2а постоянная MC:0/интервал/∞',near(r.values?.[0].Q,0)&&r.values?.[1].intervals.some(x=>near(x[0],0)&&x[1]===Infinity)&&r.values?.[2].unbounded,r);
 // Playwright сохраняет Infinity при evaluate; JSON только печатает его null.
 check(engine+' интервал до бесконечности',await p.evaluate(()=>firmSupplyBuild({expr:'16*Q'}).at(16).intervals.some(x=>x[0]===0&&x[1]===Infinity)));
 r=await solve({expr:'16*Q-Q^2'},[7,8,9]);check(engine+' 7.2б вогнутые TC:cap8,shutdown8',near(r.K,8)&&near(r.shutdown,8)&&near(r.values?.[0].Q,0)&&near(r.values?.[2].Q,8),r);check(engine+' 7.2б tie0/8',r.values?.[1].outputs.some(q=>near(q,0))&&r.values?.[1].outputs.some(q=>near(q,8)),r);
 r=await solve({expr:'Q^2+20*Q',K:10},[10,30,50]);check(engine+' 7.2в K10:0/5/10',r.values?.every((x,i)=>near(x.Q,[0,5,10][i])),r);
 r=await solve({expr:'Q^2+400',kind:'quasi'},[39,40,60]);check(engine+' 7.2г quasi shutdown40,0/20/30',near(r.shutdown,40)&&r.values?.every((x,i)=>near(x.Q,[0,20,30][i]))&&r.values[1].outputs.some(q=>near(q,0)),r);
 for(const[type,kind,rate,want]of[['unit','tax',10,5],['unit','subsidy',10,15],['revenue','tax',25,7.5],['revenue','subsidy',25,12.5]]){r=await solve({expr:'Q^2',tax:{type,kind,rate}},[20]);check(engine+' 7.3 '+type+'/'+kind,near(r.values?.[0].Q,want),r);}
 r=await solve({expr:'3*Q',mode:'mc',K:20},[30,90]);check(engine+' 7.7в MC интегрируется, K20',near(r.values?.[0].Q,10)&&near(r.values?.[0].profit,150)&&near(r.values?.[1].Q,20),r);
 r=await solve({expr:'12-Q',mode:'mc'},[5,6,7]);check(engine+' 7.7г MC убывает:cap12,shutdown6',near(r.K,12)&&near(r.shutdown,6)&&near(r.values?.[0].Q,0)&&near(r.values?.[2].Q,12)&&r.values[1].outputs.some(q=>near(q,0)),r);
 for(const[period,want]of[['sr',30],['lr',50]]){r=await solve({expr:'Q^2+30*Q+100',period},[40]);check(engine+' 7.16 '+period,near(r.shutdown,want)&&near(r.values?.[0].Q,period==='sr'?5:0),r);}
 for(const[kind,shut,Q,profit]of[['sunk',0,10,-125],['quasi',30,0,0]]){r=await solve({expr:'Q^2+100',kind,tax:{type:'lump',rate:125}},[20,30,40]);check(engine+' аккордный '+kind,near(r.shutdown,shut)&&near(r.values?.[0].Q,Q)&&near(r.values?.[0].profit,profit)&&near(r.values?.[2].Q,20)&&near(r.values?.[2].profit,175),r);}
 r=await solve({expr:'Q <= 5 ? Q^2 : 10*Q-25',K:10},[8,10,12]);check(engine+' кусочная TC:Q4,интервал[5;10],Q10',near(r.values?.[0].Q,4)&&r.values?.[1].intervals.some(x=>near(x[0],5)&&near(x[1],10))&&near(r.values?.[2].Q,10),r);
 r=await solve({expr:'Q^2+100',tax:{type:'revenue',rate:100}},[0,20,100]);check(engine+' налог100%:всегда Q0,убытокFC',r.values?.every(x=>x.Q===0&&x.profit===-100),r);
 r=await solve({expr:'Q^2',kind:'quasi',tax:{type:'revenue',rate:100}},[20]);check(engine+' налог100% quasi:закрытие без затрат',near(r.values?.[0].Q,0)&&near(r.values?.[0].profit,0),r);
 r=await solve({expr:'Q <= 5 ? Q^2 : NaN'},[20]);check(engine+' конец кусочной TC — настоящая граница5',near(r.K,5)&&near(r.values?.[0].Q,5)&&near(r.values?.[0].profit,75),r);
 await b.close();
}
console.log(`Э10 ядро: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
