import * as pw from 'playwright';import{keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-7;
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);const p=await b.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 const exists=await p.evaluate(()=>typeof ineqDistribution==='function'&&typeof ineqUnion==='function');check(engine+' движок неравных групп и союза',exists);if(!exists){await b.close();continue;}
 const dist=async c=>p.evaluate(c=>{const r=ineqDistribution(c);return{pts:r.pts,stats:r.stats,error:r.error,expr:r.expr,sorted:r.sorted,pops:r.pops};},c);
 let r=await dist({input:'groups',groups:[30,70],pops:[60,40]});check(engine+' 13.15 Джини0.3',near(r.stats?.gini,.3),r);check(engine+' 13.15 точка(.6,.3)',near(r.pts?.[1]?.[0],.6)&&near(r.pts?.[1]?.[1],.3),r);
 r=await dist({input:'groups',groups:['7/10','3/10'],pops:['2/5','3/5']});check(engine+' сортировка по доходу на человека',near(r.stats?.gini,.3)&&near(r.pts?.[1]?.[0],.6),r);
 r=await dist({input:'groups',groups:[60,40],pops:[90,10]});check(engine+' не сортировка по доле дохода',near(r.pts?.[1]?.[0],.9)&&near(r.stats?.gini,.3),r);
 r=await dist({input:'groups',groups:[30,70],pops:[50,40]});check(engine+' неверная сумма населения — ошибка',!!r.error&&/населени/.test(r.error)&&!r.stats,r);
 r=await dist({input:'groups',groups:[30,60],pops:[60,40]});check(engine+' неверная сумма дохода — ошибка',!!r.error&&/доход/.test(r.error)&&!r.stats,r);
 r=await dist({input:'groups',groups:[8,12,16,24,40]});check(engine+' пять групп без выдуманных децилей',r.stats?.decile==null&&r.stats?.decileAvailable===false&&near(r.stats?.quintile,5),r);
 for(const n of[3,4,5]){r=await dist({input:'incomes',incomes:Array.from({length:n},(_,i)=>i+1).join(',')});check(engine+' '+n+' человек: децили недоступны',r.stats?.decileAvailable===false&&(n===5?r.stats.quintileAvailable:!r.stats.quintileAvailable),r);}
 const union=async(a,c)=>p.evaluate(([a,c])=>{const r=ineqUnion([ineqDistribution(a),ineqDistribution(c)],[a.population||1,c.population||1],[a.totalIncome||1,c.totalIncome||1]);return{pts:r.pts,stats:r.stats,pieces:r.pieces,approx:r.approx,error:r.error,values:r.at?[0,.4,.75,.8,.9,1].map(r.at):null,expr:r.expr};},[a,c]);
 const a={input:'groups',groups:[25,75],pops:[50,50],population:4,totalIncome:1},c={...a,population:1};r=await union(a,c);
 check(engine+' 13.14 Джини17/40',near(r.stats?.gini,17/40),r);check(engine+' 13.14 три точки',[[.4,.125],[.8,.5],[.9,.625]].every(q=>r.pts?.some(t=>near(t[0],q[0])&&near(t[1],q[1]))),r);
 const ac={...a,groupMode:'counts',pops:[2,2],groups:[.125,.375]},cc={...c,groupMode:'counts',pops:[.5,.5],groups:[.5,1.5]};r=await union(ac,cc);check(engine+' 13.14 численность и средний доход',near(r.stats?.gini,17/40)&&near(r.pts?.[1]?.[1],.125),r);
 r=await union({input:'formula',formula:'p^2',population:3},{input:'formula',formula:'p',population:1});check(engine+' 13.18а Джини3/8',near(r.stats?.gini,3/8)&&!r.approx,r);
 check(engine+' 13.18а два точных куска',r.pieces?.length===2&&near(r.pieces[0].hi,.75)&&near(r.values?.[2],.5)&&near(r.values?.[4],.8),r);
 const cp=await p.evaluate(expr=>[.1,.5,.75,.9].map(p=>math.evaluate(expr,{p})),r.expr);check(engine+' копируемая формула13.18',cp.every((x,i)=>near(x,[8*.01/9,2/9,.5,.8][i])),cp);
 r=await union({input:'formula',formula:'p^2'},{input:'formula',formula:'p^2'});check(engine+' пересечение: численно и G≈1/3',r.approx&&Math.abs(r.stats?.gini-1/3)<1e-6&&!r.expr,r);
 for(const formula of['p^.5','2*p','p^2-p/10','NaN']){r=await dist({input:'formula',formula});check(engine+' неверная Лоренца '+formula,!!r.error&&!r.stats,r);}
 await p.evaluate(()=>{resetSceneMemory();openModelByUser('ineq');setIneqInput('formula');STATE.ineqFormula='p^2';redrawAll();updatePult();});check(engine+' α скрыта без буквы',!await p.locator('#ineq-alpha-field').isVisible());
 await p.evaluate(()=>{STATE.ineqFormula='p^alpha';redrawAll();updatePult();});check(engine+' α видна при букве',await p.locator('#ineq-alpha-field').isVisible());
 await p.evaluate(()=>setIneqAlpha(3));await p.waitForTimeout(150);r=await p.evaluate(()=>({f:STATE.ineqFormula,g:STATE.ineqStats?.gini}));check(engine+' α меняет параметр, сохраняет формулу',r.f==='p^alpha'&&near(r.g,.5),r);
 await p.evaluate(()=>{const inp=document.getElementById('ineq-formula');openPiecewise(inp,'p');PW.n=2;PW.rows=[{f:'0.5*p',a:'0',b:'0.5'},{f:'1.5*p-0.5',a:'0.5',b:''}];document.getElementById('pw-apply').click();});
 r=await p.evaluate(()=>({len:STATE.ineqLorenz?.length,g:STATE.ineqStats?.gini,last:STATE.ineqLorenz?.at(-1),error:STATE.ineqWarn}));check(engine+' конструктор корректной кусочной Лоренца',r.len===101&&near(r.g,.25)&&near(r.last?.[1],1),r);
 await p.evaluate(()=>{setIneqInput('groups');ineqAddCountry();STATE.ineqCountryB.input='formula';STATE.ineqCountryB.formula='p^alpha';renderIneqCountryControls(true);redrawAll();updatePult();});check(engine+' α видна для формулы второй страны',await p.locator('#ineq-alpha-field').isVisible());
 check(engine+' нет ошибок JS',!errors.length,errors);await b.close();
}
console.log(`Э7: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
