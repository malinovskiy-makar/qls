import * as pw from'playwright';import{keepAnswerOpen}from'./answer_open.mjs';let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);const p=await b.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');const exists=await p.evaluate(()=>typeof adasScenario==='function');check(engine+' расчёт AD–AS с шоком существует',exists);if(!exists){await b.close();continue;}
 const solve=async c=>p.evaluate(c=>{resetSceneMemory();pickScene('adas');STATE.macro.adas={...STATE.macro.adas,...c};redrawAll();const r=STATE.adasResult;return{error:r?.error,base:r?.base,sr:r?.sr,lr:r?.lr,Ystar:r?.Ystar,srChange:r?.srChange,lrChange:r?.lrChange,gapPct:r?.gapPct,labor:r?.labor,records:r?.records,adjusted:r?.adjusted?evalCurve(r.adjusted,r.lr.Q):null};},c);
 let r=await solve({ad:'Y=400+1600/P',sras:'Y=2500*P-500',lrasMode:'initial',shock:{kind:'ad',ad:'Y=400+4275/P'}});
 check(engine+' 14.52 исходно Y2000 P1',near(r.base?.Q,2000)&&near(r.base?.P,1)&&near(r.Ystar,2000),r);
 check(engine+' 14.52 SR Y3250 P1.5',near(r.sr?.Q,3250)&&near(r.sr?.P,1.5),r);
 check(engine+' 14.52 проценты от исходной точки',near(r.srChange?.Y,62.5)&&near(r.srChange?.P,50)&&near(r.gapPct,62.5),r);
 check(engine+' 14.52 LR P171/64 и инфляция167.1875',near(r.lr?.Q,2000)&&near(r.lr?.P,171/64)&&near(r.lrChange?.P,167.1875),r);
 check(engine+' сдвинутая SRAS проходит через LR',near(r.adjusted,171/64),r.adjusted);
 for(const[sras,V,wantP,pc]of[['P=1',1.3,1,30],['Y=100*P',1.69,1.3,69]]){r=await solve({adMode:'mv',M:100,V:1,sras,lrasMode:'initial',shock:{kind:'ad',M:100,V}});check(engine+' 14.53 V'+V,near(r.sr?.Q,130)&&near(r.sr?.P,wantP)&&near(r.lrChange?.P,pc)&&near(r.gapPct,30),r);}
 r=await solve({adMode:'mv',M:256,V:1,srasMode:'labor',production:'16*sqrt(L)',laborSupply:'8*w/P',shock:{kind:'ad',M:576,V:1}});
 check(engine+' 14.54 исходно L16 Y64 P4 w8',near(r.base?.Q,64)&&near(r.base?.P,4)&&near(r.labor?.base?.L,16)&&near(r.labor?.base?.nominalW,8),r);
 check(engine+' 14.54 SR Y96 P6 ΔY32',near(r.sr?.Q,96)&&near(r.sr?.P,6)&&near(r.sr.Q-r.base.Q,32),r);
 check(engine+' 14.54 SR фиксированная w8 L36',near(r.labor?.sr?.nominalW,8)&&near(r.labor?.sr?.L,36)&&near(r.labor?.sr?.realW,4/3),r.labor);
 check(engine+' 14.54 LR Y64 P9 w18',near(r.lr?.Q,64)&&near(r.lr?.P,9)&&near(r.labor?.lr?.nominalW,18)&&near(r.labor?.lr?.L,16),r);
 check(engine+' 14.54 функции AD256/P SRAS16P',await p.evaluate(()=>{const r=STATE.adasResult;return Math.abs(r.ad.yAtP(4)-64)<1e-6&&Math.abs(r.sras.yAtP(6)-96)<1e-6&&r.records.some(x=>x.name==='SRAS'&&x.expr);}),r.records);
 r=await solve({ad:'P=100-Y',sras:'P=Y',lrasMode:'initial',shock:{kind:'sras',sras:'P=Y+20'}});check(engine+' шок предложения: SR40/60, LR возвращается50/50',near(r.sr?.Q,40)&&near(r.sr?.P,60)&&near(r.lr?.Q,50)&&near(r.lr?.P,50),r);
 check(engine+' нет ошибок JS',!errors.length,errors);await b.close();
}
console.log(`Э9: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
