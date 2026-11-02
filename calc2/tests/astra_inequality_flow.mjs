import * as pw from'playwright';import fs from'node:fs';import{keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);
 for(const width of[1440,1280])for(const theme of['light','dark']){
  const p=await b.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.addInitScript(t=>localStorage.setItem('theme',t),theme);await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');await p.evaluate(()=>{resetSceneMemory();openModelByUser('ineq');});const n=[engine,width,theme].join('/');
  await p.locator('#ineq-add-group').click();check(n+' добавление группы',await p.locator('#ineq-groups-table .ineq-grow').count()===6);
  await p.evaluate(()=>{STATE.ineqGroups=[25,75];STATE.ineqPops=[50,50];renderIneqGroupsTable();redrawAll();});
  const incomeInputs=p.locator('#ineq-groups-table [data-field="income"]');
  await incomeInputs.nth(0).fill('80');await incomeInputs.nth(0).press('Tab');check(n+' ошибка суммы не нормируется',await p.evaluate(()=>!STATE.ineqStats&&/100%/.test(STATE.ineqWarn)));
  await incomeInputs.nth(1).fill('20');await incomeInputs.nth(1).press('Tab');check(n+' ввод сортирует группы по доходу',await p.evaluate(()=>Math.abs(STATE.ineqStats?.gini-.3)<1e-8&&ineqNumber(STATE.ineqGroups[0])===20));
  await p.evaluate(()=>{STATE.ineqGroups=[25,75];renderIneqGroupsTable();redrawAll();});
  await p.locator('#ineq-add-country').click();check(n+' добавление страны',await p.locator('#ineq-b-groups-table .ineq-grow').count()===2);
  await p.locator('#ineq-a-pop').fill('4');await p.locator('#ineq-a-pop').press('Tab');
  check(n+' реальный ввод весов:13.14',await p.evaluate(()=>Math.abs(STATE.ineqStats.gini-17/40)<1e-8&&STATE.ineqCountries.every(c=>Math.abs(c.stats.gini-.25)<1e-8)));
  const link=await p.evaluate(()=>shareLinkOf()),clone=await b.newPage();await clone.goto(link);await clone.waitForFunction(()=>STATE.ineqCountryB);
  check(n+' ссылка сохраняет страны, группы и веса',await clone.evaluate(()=>Math.abs(STATE.ineqStats?.gini-17/40)<1e-8&&document.getElementById('ineq-a-pop').value==='4'));await clone.close();
  await p.evaluate(()=>{historyCheck();historyBaseline();});await p.locator('#ineq-remove-country').click();await p.evaluate(()=>{historyCheck();historyUndo();});
  check(n+' отмена удаления страны',await p.locator('#ineq-b-pop').isVisible()&&await p.evaluate(()=>Math.abs(STATE.ineqStats?.gini-17/40)<1e-8));
  await p.evaluate(()=>historyRedo());check(n+' повтор удаления страны',!await p.locator('#ineq-b-pop').count());await p.evaluate(()=>historyUndo());
  await p.locator('#ineq-group-mode [data-mode="counts"]').click();await p.locator('#ineq-b-group-mode [data-mode="counts"]').click();check(n+' переключение на численности сохраняет G',await p.evaluate(()=>Math.abs(STATE.ineqStats?.gini-17/40)<1e-8));
  await p.locator('#ineq-in-formula').click();await p.evaluate(()=>{const e=document.getElementById('ineq-formula');e.value='p^2';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));});
  await p.locator('#ineq-b-input [data-input="formula"]').click();await p.evaluate(()=>{const e=document.getElementById('ineq-b-formula');e.value='p';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));});
  await p.locator('#ineq-a-pop').fill('3');await p.locator('#ineq-a-pop').press('Tab');await p.waitForTimeout(250);
  check(n+' реальный ввод формул:13.18',await p.evaluate(()=>Math.abs(STATE.ineqStats?.gini-3/8)<1e-8));
  const copy=await p.locator('#info-final .ff-copy').getAttribute('data-ff-expr');check(n+' итоговая функция копируется',await p.evaluate(e=>Math.abs(math.evaluate(e,{p:.5})-2/9)<1e-8&&Math.abs(math.evaluate(e,{p:.9})-.8)<1e-8,copy));
  const exp=await p.evaluate(()=>{const before=JSON.stringify(compactModelState(collectModelState()));const tex=buildTex('','');return{same:before===JSON.stringify(compactModelState(collectModelState())),stats:buildTex._stats,length:tex.length};});check(n+' экспорт без изменения состояния',exp.same&&exp.length>500,exp);check(n+' экспорт соответствует рисунку',Object.entries(exp.stats||{}).filter(([k])=>/Mismatch|NoRec/.test(k)).every(([,v])=>!v),exp.stats);
  await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(150);const layout=await p.evaluate(()=>({wide:document.documentElement.scrollWidth>innerWidth+1,errors:[...document.querySelectorAll('.katex-error')].map(e=>e.textContent),overflow:[...document.querySelectorAll('.ineq-grow,.ineq-country,#info-final .ff')].filter(e=>e.offsetWidth&&e.scrollWidth>e.clientWidth+2).map(e=>e.className)}));check(n+' форма и ответ помещаются',!layout.wide&&!layout.errors.length&&!layout.overflow.length,layout);
  if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e7-shots',{recursive:true});await p.screenshot({path:'.calc2-astra-local/e7-shots/'+n.replaceAll('/','-')+'.png'});}
  await p.evaluate(()=>{setSelfMode(true);buildAnswer();});check(n+' самопроверка скрывает функцию',!await p.locator('#info-final').isVisible());check(n+' без ошибок JS',!errors.length,errors);await p.close();
 }
 await b.close();
}
console.log(`Поток Э7: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
