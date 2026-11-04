import * as pw from'playwright';let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6*Math.max(1,Math.abs(b));
let seed=91454;const rnd=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};
const cases=Array.from({length:30},()=>{const A=150+100*rnd(),b=.4+rnd(),C=10+20*rnd(),d=.5+rnd(),shock=20+40*rnd(),Y0=(A-C)/(b+d),P0=C+d*Y0,Y1=(A+shock-C)/(b+d),P1=C+d*Y1;return{c:{ad:'P='+A+'-'+b+'*Y',sras:'P='+C+'+'+d+'*Y',lrasMode:'initial',shock:{kind:'ad',ad:'P='+(A+shock)+'-'+b+'*Y'}},want:{Y0,P0,Y1,P1,P2:P0+shock,dy:100*(Y1-Y0)/Y0,dp:100*(P1-P0)/P0}};});
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof adasScenario==='function');await p.evaluate(()=>{resetSceneMemory();pickScene('adas');});
 for(const[c,i]of cases.map((c,i)=>[c,i])){const r=await p.evaluate(c=>{const r=adasScenario(c);return{Y0:r.base?.Q,P0:r.base?.P,Y1:r.sr?.Q,P1:r.sr?.P,P2:r.lr?.P,dy:r.srChange?.Y,dp:r.srChange?.P,error:r.error};},c.c);check(engine+' независимая линейная система '+i,Object.entries(c.want).every(([k,v])=>near(r[k],v)),{r,want:c.want});}
 for(const beta of[.25,1/3,.5,2/3,.8]){
  const A=12,k=5,eta=1.2,M=200,ratio=2.3,L=(k*(A*beta)**eta)**(1/(1+eta*(1-beta))),Y=A*L**beta,P=M/Y,w=A*beta*L**(beta-1)*P;
  const r=await p.evaluate(c=>{const r=adasScenario(c);return{base:r.base,sr:r.sr,lr:r.lr,labor:r.labor,error:r.error};},{adMode:'mv',M,V:1,srasMode:'labor',production:A+'*L^('+beta+')',laborSupply:k+'*(w/P)^'+eta,shock:{kind:'ad',M:M*ratio,V:1}});
  check(engine+' независимая Cobb–Douglas beta='+beta,near(r.base?.Q,Y)&&near(r.base?.P,P)&&near(r.sr?.Q,Y*ratio**beta)&&near(r.sr?.P,P*ratio**(1-beta))&&near(r.lr?.P,P*ratio)&&near(r.labor?.sr?.nominalW,w),r);
 }
 const F=L=>Math.sqrt(L)+Math.pow(L,.25),mpl=L=>.5/Math.sqrt(L)+.25/Math.pow(L,.75),L0=4,k=L0/mpl(L0),M=10,P0=M/F(L0),w=mpl(L0)*P0;
 let lo=L0,hi=10000;for(let i=0;i<100;i++){const mid=(lo+hi)/2;if(40*mpl(mid)/F(mid)>w)lo=mid;else hi=mid;}const L1=(lo+hi)/2;
 const general=await p.evaluate(c=>{const r=adasScenario(c);return{base:r.base,sr:r.sr,lr:r.lr,labor:r.labor,error:r.error};},{adMode:'mv',M,V:1,srasMode:'labor',production:'sqrt(L)+L^.25',laborSupply:k+'*w/P',shock:{kind:'ad',M:40,V:1}});
 check(engine+' произвольная производственная функция',near(general.base?.Q,F(L0))&&near(general.sr?.Q,F(L1))&&near(general.sr?.P,40/F(L1))&&near(general.labor?.sr?.L,L1)&&near(general.labor?.sr?.nominalW,w),general);
 const invalid=await p.evaluate(()=>[{adMode:'mv',M:0,V:1,sras:'P=Y',lrasMode:'initial'},{ad:'P=100-Y',sras:'P=Y',lras:-1},{adMode:'mv',M:100,V:1,srasMode:'labor',production:'L^2',laborSupply:'w/P'}].map(c=>adasScenario(c).error));check(engine+' неверные условия дают понятную ошибку',invalid.every(Boolean),invalid);
 const ru=await p.evaluate(()=>[adasScenario({ad:'P=)',sras:'P=Y',lras:10}).error,islmSolve({md:'Y-('}).error]);check(engine+' ошибки формул по-русски',ru.every(e=>typeof e==='string'&&/^[А-ЯЁ]/.test(e)&&!/Unexpected|expected|Undefined/.test(e)),ru);
 await b.close();
}
console.log(`Края Э9: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
