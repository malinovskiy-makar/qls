import * as pw from 'playwright';import{readFile}from'node:fs/promises';
let total=0,bad=0;const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
const check=(name,ok,value)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(value):''));};
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/47-firm-market.draft.js','utf8')});
 const exists=await p.evaluate(()=>typeof firmMarketSolve==='function');check(engine+' ядро',exists);if(!exists){await b.close();continue;}
 const solve=(c,D,n)=>p.evaluate(({c,D,n})=>{const r=firmMarketSolve(c,D,n);return{...r,firm:undefined,D:undefined};},{c,D,n});
 let r=await solve({},'Q=100-4*P',10);check(engine+' старт15/4/40/14',near(r.P,15)&&near(r.q,4)&&near(r.Q,40)&&near(r.profit,14),r);
 r=await solve({expr:'2*Q^2'},'Q=140-P',10);check(engine+' 7.5 P40 Q100',near(r.P,40)&&near(r.Q,100),r);
 r=await solve({expr:'Q^2+10*Q+25',period:'lr'},'Q=150-P',10);check(engine+' 7.18а20/5/26',near(r.P,20)&&near(r.q,5)&&near(r.n,26)&&near(r.profit,0),r);
 r=await solve({expr:'Q^2+10*Q+25'},'Q=290-P',26);check(engine+' 7.18б30/10/75',near(r.P,30)&&near(r.q,10)&&near(r.profit,75),r);
 r=await solve({expr:'Q^2+10*Q+25',period:'lr'},'Q=290-P',26);check(engine+' 7.18в n54',near(r.P,20)&&near(r.n,54)&&near(r.profit,0),r);
 r=await solve({expr:'Q^2+10*Q+25',period:'lr'},'Q=151-P',26);check(engine+' дробное n26.2',near(r.n,26.2),r);
 r=await solve({},'P=25-Q/4',10);check(engine+' обратный спрос',near(r.P,15)&&near(r.q,4),r);
 r=await solve({expr:'16*Q-Q^2'},'Q=96-2*P',10);check(engine+' скачок0→80 приP8 допустимый конец',near(r.P,8)&&near(r.q,8)&&near(r.Q,80),r);
 r=await solve({expr:'16*Q-Q^2'},'Q=56-2*P',10);check(engine+' внутри скачка не ложное равновесие',!r.found&&r.gap?.outputs?.[1]===80&&near(r.gap.P,8),r);
 r=await solve({expr:'16*Q'},'Q=100-P',10);check(engine+' плоскаяMC даётq8.4 приP16',near(r.P,16)&&near(r.q,8.4)&&near(r.Q,84),r);
 r=await solve({expr:'Q^2',K:5},'Q=100-P',10);check(engine+' мощностьP50 q5',near(r.P,50)&&near(r.q,5),r);
 r=await solve({expr:'Q^2',tax:{type:'unit',rate:10}},'Q=100-P',10);check(engine+' налогP25 q7.5',near(r.P,25)&&near(r.q,7.5),r);
 r=await solve({expr:'Q^2',tax:{type:'revenue',rate:25}},'Q=100-P',10);check(engine+' налогвыручкаP400/19 q150/19',near(r.P,400/19)&&near(r.q,150/19),r);
 r=await solve({expr:'Q^2',period:'lr'},'Q=100-P',10);check(engine+' недостигнутый положительный q LR невыдуман',!!r.error&&!r.found,r);
 r=await solve({expr:'16*Q',period:'lr'},'Q=100-P',10);check(engine+' линейныеTC LR неоднозначны',near(r.P,16)&&r.nonunique&&r.ranges.length>0,r);
 await b.close();
}
console.log(`Э11 ядро: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
