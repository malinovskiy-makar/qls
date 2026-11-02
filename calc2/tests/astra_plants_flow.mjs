import * as pw from 'playwright';import fs from'node:fs';import {keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);
 for(const width of[1440,1280])for(const theme of['light','dark']){
 const p=await b.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.addInitScript(t=>localStorage.setItem('theme',t),theme);
 await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof pickScene==='function');await p.evaluate(()=>{resetSceneMemory();openModelByUser('plants');});
 const n=[engine,width,theme].join('/');
 await p.locator('#plant-add').click();check(n+' добавлен третий завод',await p.locator('#inp-pl3').locator('xpath=ancestor::div[contains(@class,"fc-card")][1]').isVisible());
 await p.evaluate(()=>{const e=document.getElementById('inp-pl3');e.value='3*Q';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));});
 const card=p.locator('#inp-pl1').locator('xpath=ancestor::div[contains(@class,"fc-card")][1]');
 await card.locator('.plant-options input').fill('4');await card.locator('.plant-options input').press('Tab');
 const card2=p.locator('#inp-pl2').locator('xpath=ancestor::div[contains(@class,"fc-card")][1]');
 await card2.locator('[data-kind="quasi"]').click();
 check(n+' настройки дошли до расчёта',await p.evaluate(()=>STATE.plants.specs.length===3&&STATE.plants.specs[0].K===4&&STATE.plants.specs[1].kind==='quasi'&&STATE.plants.specs[2].expr==='3*Q'));
 const link=await p.evaluate(()=>shareLinkOf()),clone=await b.newPage();await clone.goto(link);await clone.waitForFunction(()=>STATE.plants?.specs?.length===3);
 check(n+' ссылка с тремя заводами и мощностью',await clone.evaluate(()=>document.getElementById('inp-pl3')?.value==='3*Q'&&STATE.plants.specs[0].K===4));await clone.close();
 const exportResult=await p.evaluate(()=>{const before=JSON.stringify(compactModelState(collectModelState())),tex=buildTex('','');return{same:before===JSON.stringify(compactModelState(collectModelState())),stats:buildTex._stats,tex:tex.length};});
 check(n+' экспорт сохраняет состояние',exportResult.same&&exportResult.tex>500,exportResult);
 check(n+' формулы экспорта совпали с рисунком',Object.entries(exportResult.stats||{}).filter(([k])=>/Mismatch|NoRec/.test(k)).every(([,v])=>!v),exportResult.stats);
 await p.evaluate(()=>{historyCheck();historyBaseline();});await p.locator('#inp-pl3').locator('xpath=ancestor::div[contains(@class,"fc-card")][1]').locator('.plant-remove').click();
 await p.evaluate(()=>{historyCheck();historyUndo();});check(n+' отмена удаления',await p.locator('#inp-pl3').locator('xpath=ancestor::div[contains(@class,"fc-card")][1]').isVisible());
 await p.evaluate(()=>historyRedo());check(n+' повтор удаления',!await p.locator('#inp-pl3').count());
 await p.evaluate(()=>{setPlantInputRows([{expr:'10*Q',K:null,kind:'sunk'},{expr:'Q^2',K:null,kind:'sunk'}]);STATE.plQ=12;renderPlantRows(true);redrawAll();buildAnswer();});
 await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(200);
 const layout=await p.evaluate(()=>({wide:document.documentElement.scrollWidth>innerWidth+1,bad:[...document.querySelectorAll('.katex-error')].map(e=>e.textContent),
  overflowing:[...document.querySelectorAll('#plant-rows .fc-card,#info-final .ff')].filter(e=>e.scrollWidth>e.clientWidth+2).map(e=>e.className)}));
 const formula=await p.locator('#info-final .ff-copy').getAttribute('data-ff-expr');const values=await p.evaluate(expr=>[0,5,12].map(Q=>math.evaluate(expr,{Q})),formula);check(n+' копируемая итоговая функция',values.every((x,i)=>Math.abs(x-[0,25,95][i])<1e-7),{formula,values});
 check(n+' мощность в общем стиле числовых полей',await p.locator('#plant-rows .plant-options input').first().evaluate(e=>getComputedStyle(e).borderBottomStyle==='dashed'));
 check(n+' карточки и формула помещаются',!layout.wide&&!layout.overflowing.length&&!layout.bad.length,layout);
 if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e6-shots',{recursive:true});await p.screenshot({path:'.calc2-astra-local/e6-shots/'+n.replaceAll('/','-')+'.png'});}
 await p.evaluate(()=>{setSelfMode(true);buildAnswer();});check(n+' самопроверка скрывает итоговую функцию',!await p.locator('#info-final').isVisible());
 check(n+' нет ошибок JS',!errors.length,errors);await p.close();
 }
 await b.close();
}
console.log(`Поток Э6: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
