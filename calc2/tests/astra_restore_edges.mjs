/* Две ошибки, найденные общим state_probe: компиляция MSB/MSC и отметка равных групп. */
import * as pw from 'playwright';
let total=0,bad=0;
const check=(name,ok,value)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(value):''));};
for(const engine of ['chromium','webkit']){
  const browser=await pw[engine].launch(),page=await browser.newPage();
  await page.goto(process.env.CALC2_BASE_URL+'/calc2/');
  await page.waitForFunction(()=>typeof applyModelState==='function');
  const r=await page.evaluate(()=>{
    resetSceneMemory();openModelByUser('ext');
    STATE.msbOn=true;STATE.mscOn=true;STATE.msbExpr='105-Q';STATE.mscExpr='Q+25';
    recompileSocial();redrawAll();
    const before={Q:STATE.ext.Qopt,P:STATE.ext.Popt},saved=JSON.stringify(collectModelState());
    resetSceneMemory();openModelByUser('sd');applyModelState(JSON.parse(saved));
    const after={Q:STATE.ext.Qopt,P:STATE.ext.Popt};
    resetSceneMemory();openModelByUser('ineq');
    const selected=()=>[...document.querySelectorAll('#ineq-pane-groups .sc-nseg button.active')].map(b=>b.dataset.v);
    const equal=selected();
    STATE.ineqGroups=[2,6,12,25,55];STATE.ineqPops=[10,15,20,25,30];redrawAll();
    const unequal={selected:selected(),error:STATE.ineqDistribution.error||null};
    STATE.ineqPops=[10,15,20,25,40];redrawAll();
    const invalid={selected:selected(),error:STATE.ineqDistribution.error||null};
    const s=JSON.stringify(collectModelState());resetSceneMemory();openModelByUser('sd');applyModelState(JSON.parse(s));
    const restored={selected:selected(),error:STATE.ineqDistribution.error||null};
    setIneqGroupN(5);const recovered={selected:selected(),error:STATE.ineqDistribution.error||null};
    return {before,after,equal,unequal,invalid,restored,recovered};
  });
  check(engine+' MSB=105-Q / MSC=Q+25',Math.abs(r.before.Q-40)<1e-8&&Math.abs(r.before.P-65)<1e-8,r.before);
  check(engine+' восстановлены обе общественные кривые',JSON.stringify(r.after)===JSON.stringify(r.before),r.after);
  check(engine+' исходно пять равных групп',JSON.stringify(r.equal)==='["5"]',r.equal);
  check(engine+' неравные доли снимают отметку пресета',!r.unequal.error&&!r.unequal.selected.length,r.unequal);
  check(engine+' ошибочная сумма также снимает отметку',!!r.invalid.error&&!r.invalid.selected.length,r.invalid);
  check(engine+' ошибка и отметки восстановились',JSON.stringify(r.restored)===JSON.stringify(r.invalid),r.restored);
  check(engine+' возврат к пресету',!r.recovered.error&&JSON.stringify(r.recovered.selected)==='["5"]',r.recovered);
  await browser.close();
}
console.log(`Восстановление: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
