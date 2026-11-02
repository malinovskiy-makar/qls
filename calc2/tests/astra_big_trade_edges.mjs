import*as pw from'playwright';import{readFile}from'node:fs/promises';
let total=0,bad=0;const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6*Math.max(1,Math.abs(b));
const check=(n,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(r):''));};
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/55-big-trade.draft.js','utf8')});
 const solve=input=>p.evaluate(input=>bigTradeSolve(input),input);
 for(let i=0;i<24;i++){
  const a=1+i%3,b=1+(i+1)%3,autA=80+2*i,autB=40+i,tA=5+i%7,tB=3+i%5,P0=(a*autA+b*autB)/(a+b),P=(a*autA+b*autB-a*tA+b*tB)/(a+b),PA=P+tA,PB=P-tB,T=2*a*(autA-PA),A=2*a*autA,B=2*b*autB;
  const welfare=(head,slope,price,budget=0)=>(head-slope*price)**2/(2*slope)+slope*price**2/2+budget;
  const wa=welfare(A,a,PA,tA*T)-welfare(A,a,P0),wb=welfare(B,b,PB,tB*T)-welfare(B,b,P0);
  const r=await solve({A:{D:`Q=${A}-${a}*P`,S:`Q=${a}*P`,policy:{kind:'tax',target:'trade',rate:tA}},B:{D:`Q=${B}-${b}*P`,S:`Q=${b}*P`,policy:{kind:'tax',target:'trade',rate:tB}}});
  check(engine+' аналитическое равновесие '+i,near(r.Pw,P)&&near(r.volume,T)&&near(r.countries?.A.Pc,PA)&&near(r.countries?.B.Pc,PB),r);
  check(engine+' независимые излишки '+i,near(r.countries?.A.welfareChange,wa)&&near(r.countries?.B.welfareChange,wb)&&near(r.worldChange,wa+wb),r);
 }
 let r=await solve({A:{policy:{kind:'tax',target:'trade',form:'world',rate:20}},B:{policy:{kind:'tax',target:'trade',form:'world',rate:25}}});check(engine+' обе пошлины в процентах Pw',near(r.Pw,600/13)&&near(r.volume,120/13)&&near(r.countries?.A.budget,14400/169)&&near(r.countries?.B.budget,18000/169),r);
 r=await solve({B:{policy:{kind:'subsidy',target:'trade',form:'world',rate:20}}});check(engine+' процентная субсидия B',near(r.Pw,450/11)&&near(r.volume,420/11)&&near(r.countries?.B.budget,-37800/121),r);
 r=await solve({A:{D:'P=120-Q',S:'P=Q'},B:{D:'P=60-Q',S:'P=Q'}});check(engine+' обратная запись',near(r.Pw,45)&&near(r.volume,30),r);
 r=await solve({A:{D:'P=120-Q^2',S:'P=Q^2'},B:{D:'P=60-Q^2',S:'P=Q^2'}});check(engine+' нелинейные стороны',!r.error&&near(r.countries.A.Im,r.countries.B.Ex)&&near(r.countries.A.Pc,r.countries.B.Pc)&&r.Pw>30&&r.Pw<60,r);
 r=await solve({A:{D:'Q=60-P'}});check(engine+' одинаковые страны:общая автаркическая цена',near(r.Pw,30)&&r.volume===0&&near(r.worldLoss,0),r);
 for(const input of[{A:{D:'Q=100+P'}},{B:{policy:{kind:'tax',target:'consumer',form:'buyer',rate:100}}}]){r=await solve(input);check(engine+' неверный ввод',!!r.error,r);}
 await b.close();
}
console.log(`Э13 края: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
