import*as pw from'playwright';import{readFile}from'node:fs/promises';
let total=0,bad=0;const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
const check=(n,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(r):''));};
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/55-big-trade.draft.js','utf8')});
 const exists=await p.evaluate(()=>typeof bigTradeSolve==='function');check(engine+' ядро',exists);if(!exists){await b.close();continue;}
 const solve=input=>p.evaluate(input=>bigTradeSolve(input),input),tax=(rate,kind='tax',target='trade',form='unit')=>({rate,kind,target,form});
 let r=await solve({});check(engine+' свободная45/30',near(r.Pw,45)&&near(r.volume,30)&&r.importer==='A'&&r.exporter==='B'&&near(r.worldLoss,0),r);
 r=await solve({A:{policy:tax(10)}});check(engine+' тариф10→40/50/40/20/200',near(r.Pw,40)&&near(r.countries?.A.Pc,50)&&near(r.countries?.B.Pc,40)&&near(r.volume,20)&&near(r.countries?.A.budget,200),r);
 check(engine+' благосостояние75/−125/−50',near(r.countries?.A.welfareChange,75)&&near(r.countries?.B.welfareChange,-125)&&near(r.worldChange,-50),r);
 for(const rate of[30,40,100]){r=await solve({A:{policy:tax(rate)}});check(engine+' запретительный'+rate,r.Pw===null&&r.volume===0&&near(r.countries?.A.Pc,60)&&near(r.countries?.B.Pc,30)&&near(r.countries?.A.budget,0)&&near(r.worldLoss,450),r);}
 r=await solve({A:{policy:tax(15)}});check(engine+' максимум сборов15→225',near(r.Pw,37.5)&&near(r.volume,15)&&near(r.countries?.A.Pc,52.5)&&near(r.countries?.A.budget,225),r);
 r=await solve({B:{policy:tax(10,'subsidy')}});check(engine+' субсидия страныB',near(r.Pw,40)&&near(r.countries?.A.Pc,40)&&near(r.countries?.B.Pc,50)&&near(r.volume,40)&&near(r.countries?.B.budget,-400),r);
 r=await solve({A:{policy:tax(10)},B:{policy:tax(5)}});check(engine+' вмешательства обеих стран',near(r.Pw,42.5)&&near(r.volume,15)&&near(r.countries?.A.budget,150)&&near(r.countries?.B.budget,75),r);
 r=await solve({A:{policy:{kind:'quota',quota:20}}});check(engine+' квотаA20',near(r.Pw,40)&&near(r.volume,20)&&near(r.countries?.A.Pc,50)&&near(r.countries?.A.rent,200)&&r.countries.A.budget===0&&near(r.worldLoss,50),r);
 r=await solve({A:{D:'Q=60-P'},B:{D:'Q=120-P'}});check(engine+' направление определяется само',near(r.Pw,45)&&r.importer==='B'&&r.exporter==='A',r);
 r=await solve({A:{ban:'noimport'}});check(engine+' запрет ввозаA',r.volume===0&&r.Pw===null&&near(r.countries?.A.Pc,60)&&near(r.countries?.B.Pc,30),r);
 r=await solve({A:{policy:tax(10,'tax','producer')},B:{policy:tax(5,'subsidy','consumer')}});check(engine+' внутренние и общие каналы',near(r.Pw,48.75)&&near(r.volume,32.5)&&near(r.countries?.A.Pp,38.75)&&near(r.countries?.B.Pc,43.75)&&near(r.countries?.A.budget,387.5)&&near(r.countries?.B.budget,-81.25),r);
 r=await solve({A:{policy:{kind:'quota',quota:10}},B:{policy:{kind:'quota',quota:10}}});check(engine+' две квоты:диапазон мировой цены35…55',r.Pw===null&&near(r.volume,10)&&near(r.priceInterval?.[0],35)&&near(r.priceInterval?.[1],55)&&near(r.worldLoss,200)&&near(r.quotaRent,200),r);
 await b.close();
}
console.log(`Э13 ядро: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
