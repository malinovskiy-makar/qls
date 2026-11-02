import * as pw from 'playwright';import{readFile}from'node:fs/promises';
let total=0,bad=0;const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-7*Math.max(1,Math.abs(b));
function check(name,ok,r){total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(r):''));}
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/49-trade-policy.draft.js','utf8')});
 const exists=await p.evaluate(()=>typeof tradeCountry==='function');check(engine+' ядро',exists);if(!exists){await b.close();continue;}
 const solve=(mono,D,S,Pw,policy={},ban='free')=>p.evaluate(({mono,D,S,Pw,policy,ban})=>(mono?tradeMono:tradeCountry)(D,S,Pw,policy,ban),{mono,D,S,Pw,policy,ban});
 const tax=(target,rate,kind='tax',form='unit')=>({target,rate,kind,form});
 const rows=[
 ['свободный экспорт',{},'free',[80,80,40,100,0,60,0]],
 ['9.23а',tax('producer',20),'free',[80,60,40,60,0,20,1200]],
 ['9.23б смена направления',tax('producer',40),'free',[80,40,40,20,20,0,800]],
 ['9.23в внутри',tax('internal',10),'free',[90,80,30,100,0,70,300]],
 ['9.23г потребителям',tax('consumer',10),'free',[90,80,30,100,0,70,300]],
 ['9.23д пошлина',tax('trade',15),'free',[65,65,55,70,0,15,225]],
 ['9.23е субсидия',tax('trade',10,'subsidy'),'free',[90,90,30,120,0,90,-900]],
 ['субсидия производителю',tax('producer',10,'subsidy'),'free',[80,90,40,120,0,80,-1200]],
 ['субсидия потребителю',tax('consumer',10,'subsidy'),'free',[70,80,50,100,0,50,-500]],
 ['9.25в',tax('internal',20),'free',[100,80,20,100,0,80,400]],
 ['9.25г',tax('producer',25),'free',[80,55,40,50,0,10,1250]],
 ['9.25д запрет ввоза',tax('producer',45),'noimport',[90,45,30,30,0,0,1350]],
 ['45 без запрета',tax('producer',45),'free',[80,35,40,10,30,0,450]],
 ];
 for(const[name,t,ban,v]of rows){const r=await solve(false,'Q=120-P','Q=2*P-60',80,t,ban);check(engine+' '+name,['Pc','Pp','Qd','Qs','Im','Ex','budget'].every((k,i)=>near(r[k],v[i]))&&r.Im*r.Ex===0,r);}
 for(const[name,t,v]of[
 ['свободный импорт',{},[30,30,70,30,40,0]],
 ['тариф',tax('trade',10),[40,40,60,40,20,200]],
 ['производителям',tax('producer',10),[30,20,70,20,50,200]],
 ['потребителям',tax('consumer',10),[40,30,60,30,30,600]],
 ['внутри',tax('internal',10),[30,20,70,20,50,200]],
 ['субсидия ввоза',tax('trade',10,'subsidy'),[20,20,80,20,60,-600]],
 ['субсидия производителям',tax('producer',10,'subsidy'),[30,40,70,40,30,-400]],
 ]){const r=await solve(false,'100-Q','Q',30,t);check(engine+' импорт '+name,['Pc','Pp','Qd','Qs','Im','budget'].every((k,i)=>near(r[k],v[i]))&&r.Ex===0,r);if(name==='производителям'||name==='потребителям'||name==='субсидия производителям')check(engine+' потери50 '+name,near(r.free.sw-r.sw,50)&&near(r.dwlProd+r.dwlCons,50),r);}
 for(const[name,t,v]of[
 ['без налога',{},[50,25,75,25,0]],
 ['производителю',tax('producer',10),[40,25,75,15,400]],
 ['внутри',tax('internal',10),[50,20,80,30,200]],
 ['экспорт субсидия',tax('trade',10,'subsidy'),[60,20,80,40,-400]],
 ['экспорт пошлина',tax('trade',10),[40,30,70,10,100]],
 ['акциз 37.5%',tax('internal',37.5,'tax','buyer'),[50,10,90,40,337.5]],
 ]){const r=await solve(true,'100-Q','Q',50,t);check(engine+' монополист '+name,['Q','Qd','Pc','Ex','budget'].every((k,i)=>near(r[k],v[i]))&&r.Im===0,r);}
 await b.close();
}
console.log(`Э12 ядро: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
