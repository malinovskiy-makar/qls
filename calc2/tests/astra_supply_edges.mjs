import * as pw from'playwright';import{readFile}from'node:fs/promises';
const cases=JSON.parse(await readFile(new URL('./fixtures/astra_supply_grid.json',import.meta.url),'utf8'));
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};const near=(a,b,t=1e-6)=>Number.isFinite(a)&&Math.abs(a-b)<t;
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');if(process.argv.includes('--draft'))await p.addScriptTag({content:await readFile('.calc2-astra-local/46-firm-supply.draft.js','utf8')});
 for(const[i,x]of cases.entries()){
  const r=await p.evaluate(x=>{const m=firmSupplyBuild(x.config);if(m.error)return m;const r=m.at(x.P);return{Q:r.Q,profit:r.profit,K:m.K};},x);
  check(engine+' независимый Python-перебор '+i,r.profit>=x.profit-1e-6&&r.profit<x.profit+.001&&near(r.K,x.effectiveK),{r,x});
 }
 const extras=await p.evaluate(()=>{
  const solve=(c,P)=>{const m=firmSupplyBuild(c);if(m.error)return m;const r=m.at(P);return{error:m.error,shutdown:m.shutdown,Q:r.Q,profit:r.profit,tie:r.tie,outputs:r.outputs,unattained:r.unattained,approx:r.approx,exact:m.exact};};
  return{
   huge:solve({expr:'Q^2+100000000000000'},20),
   hugeRoot:solve({expr:'Q^3+100000000000000'},6),
   hugeEntry:(()=>{const m=firmSupplyBuild({expr:'Q^2+1e30',kind:'quasi'}),r=m.schedule.rows.find(r=>r.lo<3e15&&r.hi>3e15);return{shutdown:m.shutdown,Q:r?math.evaluate(r.expr,{P:3e15}):null};})(),
   hugeSwitch:(()=>{const m=firmSupplyBuild({expr:'Q <= 1 ? Q^2 : Q^2+1e30'}),r=m.schedule.rows.find(r=>r.lo<3e15&&r.hi>3e15);return{Q:r?math.evaluate(r.expr,{P:3e15}):null};})(),
   negativeShutdown:solve({expr:'Q^2',tax:{type:'unit',kind:'subsidy',rate:10}},0),
   openFlat:(()=>{const m=firmSupplyBuild({expr:'Q < 2 ? Q : 10*Q',K:8});return m.at(1).intervalClosed;})(),
   numericZero:solve({expr:'Q^4+100',K:10},0),
   flatK:solve({expr:'16*Q',K:10},16),
   pieceJump:solve({expr:'Q <= 2 ? 10*Q : Q^2+4',K:8},5),
   openLimit:solve({expr:'Q < 2 ? Q : 10*Q',K:8},5),
   mcPiece:solve({expr:'Q <= 2 ? 2*Q : 4',mode:'mc',K:8},5),
   numeric:solve({expr:'Q^4+100',K:10},32),
   numericMC:solve({expr:'4*Q^3',mode:'mc',K:10},32),
   numericLR:solve({expr:'Q^4+3',period:'lr',K:10},4),
   noK:solve({expr:'Q^2'},1000),
   zeroK:solve({expr:'Q^2+100',K:0},100),
   chain:solve({expr:'0 <= Q <= 5 ? Q^2 : NaN'},20),
   invalid:firmSupplyBuild({expr:'Q^2',K:-1}).error,
  };
 });
 check(engine+' большой FC не меняет выпуск',near(extras.huge.Q,10),extras.huge);
 check(engine+' большой FC и иррациональный выпуск',near(extras.hugeRoot.Q,Math.sqrt(2)),extras.hugeRoot);
 check(engine+' большой порог входа в итоговой функции',near(extras.hugeEntry.shutdown/1e15,2)&&near(extras.hugeEntry.Q/1e15,1.5),extras.hugeEntry);
 check(engine+' большой переход между положительными выпусками',near(extras.hugeSwitch.Q/1e15,1.5),extras.hugeSwitch);
 check(engine+' субсидия:истинная цена закрытия-10',near(extras.negativeShutdown.shutdown,-10)&&near(extras.negativeShutdown.Q,5),extras.negativeShutdown);
 check(engine+' открытый конец интервала не включён',extras.openFlat?.some(x=>x[0]===true&&x[1]===false),extras.openFlat);
 check(engine+' численная нулевая цена:один нулевой выпуск',near(extras.numericZero.Q,0)&&extras.numericZero.outputs?.length===1,extras.numericZero);
 check(engine+' конечная горизонтальная MC:весь интервал',extras.flatK.tie&&near(extras.flatK.Q,10),extras.flatK);
 check(engine+' кусочный скачок затрат:глобально Q2.5',near(extras.pieceJump.Q,2.5)&&near(extras.pieceJump.profit,2.25),extras.pieceJump);
 check(engine+' открытый край:супремум не выдан за максимум',extras.openLimit.unattained&&extras.openLimit.Q===null,extras.openLimit);
 check(engine+' кусочная MC:интеграл непрерывен',near(extras.mcPiece.Q,8)&&near(extras.mcPiece.profit,12),extras.mcPiece);
 check(engine+' Q^4:численно Q2,прибыль-52',near(extras.numeric.Q,2)&&near(extras.numeric.profit,-52)&&extras.numeric.approx,extras.numeric);
 check(engine+' MC4Q^3:интеграл16,прибыль48',near(extras.numericMC.Q,2)&&near(extras.numericMC.profit,48,1e-4),extras.numericMC);
 check(engine+' численный LR:shutdown4,нет выдуманной точности',near(extras.numericLR.shutdown,4,1e-5)&&extras.numericLR.approx,extras.numericLR);
 check(engine+' без K оптимум не зависит от окна200',near(extras.noK.Q,500),extras.noK);
 check(engine+' K0:фирма закрыта,FC остаются',near(extras.zeroK.Q,0)&&near(extras.zeroK.profit,-100),extras.zeroK);
 check(engine+' двойное неравенство задаёт конец5',near(extras.chain.Q,5)&&near(extras.chain.profit,75)&&extras.chain.exact,extras.chain);
 check(engine+' отрицательная мощность:русская ошибка',typeof extras.invalid==='string'&&extras.invalid.includes('Мощность'),extras.invalid);
 await b.close();
}
console.log(`Края Э10: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
