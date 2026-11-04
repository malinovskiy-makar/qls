import * as pw from'playwright';import{readFile}from'node:fs/promises';
let total=0,bad=0;const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6*Math.max(1,Math.abs(b));
const check=(name,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(r):''));};
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/49-trade-policy.draft.js','utf8')});
 const country=(D,S,Pw,t,ban='free')=>p.evaluate(x=>tradeCountry(...x),[D,S,Pw,t,ban]);
 const mono=(D,S,Pw,t,ban='free')=>p.evaluate(x=>tradeMono(...x),[D,S,Pw,t,ban]);
 // Формулы ожидаемого результата выведены независимо для линейных сторон.
 for(const importing of[false,true])for(const target of['producer','consumer','internal','trade'])for(const kind of['tax','subsidy'])for(const form of target==='trade'?['world']:['seller','buyer']){
  const Pw=importing?20:80,sign=kind==='tax'?1:-1,rate=12.5,s=sign*rate/100,A=form==='seller'?1+s:1/(1-s),tax={target,kind,form,rate};let Pc,Pp;
  if(target==='trade')Pc=Pp=Pw*(1+(importing?s:-s));
  else if(target==='producer'||target==='internal'&&importing){Pc=Pw;Pp=Pw/A;}
  else{Pp=Pw;Pc=A*Pw;}
  const Qd=100-Pc,Qs=Pp,Im=Math.max(0,Qd-Qs),Ex=Math.max(0,Qs-Qd),budget=Pc*Qd-Pp*Qs+Pw*(Ex-Im),cs=Qd**2/2,ps=Qs**2/2;
  const r=await country('100-Q','Q',Pw,tax);check(engine+' процент '+JSON.stringify([importing,target,kind,form]),Object.entries({Pc,Pp,Qd,Qs,Im,Ex,budget,cs,ps}).every(([k,v])=>near(r[k],v)),r);
 }
 for(const form of['seller','buyer'])for(const kind of['tax','subsidy'])for(const target of['internal','consumer','producer','trade']){
  const s=(kind==='tax'?1:-1)*.2,A=target==='trade'?1:form==='seller'?1+s:1/(1-s),pe=target==='trade'?50*(1-s):target==='producer'?50/A:50;
  const q=target==='trade'?(100-pe)/2:(100-A*pe)/2,Q=pe,Pc=100-q,Pp=target==='trade'?Pc:Pc/A,budget=(Pc-Pp)*q+(50-pe)*(Q-q),profit=Pp*q+pe*(Q-q)-Q**2/2;
  const r=await mono('100-Q','Q',50,{kind,target,form:target==='trade'?'world':form,rate:20});check(engine+' монополист процент '+JSON.stringify([form,kind,target]),Object.entries({Q,Qd:q,Pc,Pp,Ex:Q-q,budget,profit}).every(([k,v])=>near(r[k],v)),r);
 }
 for(const Pw of[30,80])for(const quota of[0,10,100]){
  const volume=Math.min(quota,Math.abs(100-2*Pw)),P=Pw<50?(100-volume)/2:(100+volume)/2,Qd=100-P,Qs=P;
  const r=await country('100-Q','Q',Pw,{kind:'quota',quota});check(engine+' квота '+Pw+'/'+quota,near(r.Pc,P)&&near(r.Qd,Qd)&&near(r.Qs,Qs)&&near(r.Im+r.Ex,volume)&&near(r.rent,Math.abs(P-Pw)*volume)&&r.budget===0,r);
 }
 let r=await country('100-Q','Q',30,{kind:'tax',target:'trade',rate:100});check(engine+' запретительный тариф',near(r.Pc,50)&&r.Im===0&&r.Ex===0&&r.budget===0&&near(r.dwlProd+r.dwlCons,400),r);
 r=await country('100-Q','Q',80,{},'noexport');check(engine+' запрет вывоза',near(r.Pc,50)&&r.Im===0&&r.Ex===0,r);
 r=await country('100-Q','Q',50,{kind:'tax',target:'internal',rate:10});check(engine+' два допустимых односторонних режима',r.multiple&&r.alternatives.length===2&&r.alternatives.every(x=>x.Im*x.Ex===0),r);
 r=await country('P=100-Q^2','P=Q^2',30,{});check(engine+' нелинейная страна',near(r.Qd,Math.sqrt(70))&&near(r.Qs,Math.sqrt(30)),r);
 for(const form of['seller','buyer']){r=await country('100-Q','Q',30,{kind:form==='buyer'?'tax':'subsidy',target:'consumer',form,rate:100});check(engine+' вырожденная процентная ставка',!!r.error,r);}
 r=await mono('100-Q','Q',50,{},'noexport');check(engine+' закрытая монополия',near(r.Q,100/3)&&near(r.Pc,200/3)&&r.Ex===0,r);
 r=await mono('100-Q','Q',50,{kind:'quota',quota:10});check(engine+' монополист квота10',near(r.Q,40)&&near(r.Qd,30)&&near(r.Pc,70)&&near(r.Ex,10),r);
 r=await mono('100-Q','TC=Q^2/2+200',50,{kind:'tax',target:'producer',rate:10});check(engine+' TC и постоянные затраты',near(r.Q,40)&&near(r.Qd,25)&&near(r.profit,1225)&&near(r.ps,1425),r);
 r=await mono('100-Q','MC=20-Q',50,{});check(engine+' убывающая MC конец20',near(r.Q,20)&&near(r.Qd,20)&&r.Ex===0&&near(r.profit,1400),r);
 r=await mono('100-Q^2','Q',50,{});check(engine+' нелинейный монополист',r.exact===false&&near(r.Q,50)&&near(r.Qd,Math.sqrt(50/3))&&near(r.Pc,250/3),r);
 const fixtures=JSON.parse(await readFile('calc2/tests/fixtures/astra_trade_grid.json','utf8'));
 for(const [i,row]of fixtures.entries()){
  const c=row.config,r=await mono(`${c.d0}-${c.ds}*Q`,`${c.c0}+(${c.ca})*Q`,c.Pw,c.policy);
  check(engine+' независимый двумерный перебор '+i,!r.error&&r.profit>=row.grid.profit-1e-6&&r.profit-row.grid.profit<.11,{actual:r,grid:row.grid});
 }
 await b.close();
}
console.log(`Э12 края: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
