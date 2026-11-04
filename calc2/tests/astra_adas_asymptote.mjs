import*as pw from'playwright';let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch(),p=await b.newPage();await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');
 const r=await p.evaluate(()=>{resetSceneMemory();pickScene('adas');STATE.macro.adas.ad='1600/(Y-400)';STATE.macro.adas.sras='(Y+500)/2500';STATE.macro.adas.lras=2000;CONFIG.Qmax=5070;CONFIG.Pmax=5;STATE.zoomLock=true;redrawKeepingWindow();const path=document.querySelector('#chart path[data-expr-name="AD"]'),pts=path?.__data__||[],bridges=[];for(let i=1;i<pts.length;i++){const a=pts[i-1],b=pts[i];if(a&&b&&a[0]<400&&b[0]>400)bridges.push([a,b]);}return{bridges,neg:pts.filter(p=>p&&p[1]<-1e-9).length,finite:pts.every(p=>!p||p.every(Number.isFinite)),eq:STATE.macroRes?.eq};});
 check(engine+' AD не соединяет ветви через асимптоту400',!r.bridges.length&&r.finite,r);check(engine+' AD только в первой четверти, равновесие2000/1',!r.neg&&Math.abs(r.eq?.Q-2000)<1e-6&&Math.abs(r.eq?.P-1)<1e-6,r);await b.close();
}
console.log(`Асимптота AD: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
