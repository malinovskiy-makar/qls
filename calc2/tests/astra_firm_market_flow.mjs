import*as pw from'playwright';import fs from'node:fs';import{keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(name,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(r):''));};
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const browser=await pw[engine].launch();keepAnswerOpen(browser);
 for(const width of(process.env.WIDTHS||'1440,1280').split(',').map(Number))for(const theme of['light','dark']){
  const p=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[],name=[engine,width,theme].join('/');p.on('pageerror',e=>errors.push(e.message));await p.addInitScript(t=>localStorage.setItem('theme',t),theme);await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof firmMarketSolve==='function');await p.evaluate(()=>{resetSceneMemory();openModelByUser('firmmarket');});await p.waitForTimeout(150);
  const edit=async(id,value)=>{const input=p.locator('#'+id);await input.fill(value);await input.press('Tab');await p.waitForTimeout(80);};
  const type=async(id,text)=>{await p.evaluate(id=>document.getElementById(id)._mf.focus(),id);await p.waitForTimeout(180);await p.evaluate(id=>document.getElementById(id)._mf.executeCommand('selectAll'),id);await p.keyboard.type(text,{delay:25});await p.keyboard.press('Enter');await p.keyboard.press('Tab');await p.waitForTimeout(350);};
  const values=want=>p.evaluate(want=>{const r=STATE.firmMarketResult;return!!r?.found&&Object.entries(want).every(([key,value])=>Math.abs(r[key]-value)<1e-6);},want);
  check(name+' карточка активна и названа',await p.locator('#scene-name').textContent()==='Рынок и фирма в СК'&&await p.locator('.scard[data-scene="firmmarket"]').isEnabled());
  check(name+' старт15/4/40/14',await values({P:15,q:4,Q:40,profit:14}));
  check(name+' обе панели и общая цена',await p.evaluate(()=>STATE.panels.length===2&&STATE.panels[0].id==='firm-market-firm'&&STATE.panels[1].id==='firm-market-market'&&JSON.stringify(STATE.panels[0].my.domain())===JSON.stringify(STATE.panels[1].my.domain())));
  check(name+' скачок рынка умножен на10',await p.evaluate(()=>{const line=document.querySelector('[data-firm-market-panel="firm-market-market"] [data-supply-jump]'),panel=STATE.panels.find(x=>x.id==='firm-market-market');return!!line&&Math.abs(panel.mx.invert(+line.getAttribute('x2'))-30)<1e-8&&Math.abs(panel.my.invert(+line.getAttribute('y1'))-6)<1e-8;}));
  check(name+' цена не управляется ползунком',!await p.locator('#lr-price-field').isVisible()&&await p.evaluate(()=>!pultRegulatorIds().includes('lr-price-field')));
  await type('inp-tc','Q^2+10*Q+25');await type('firm-market-demand','Q=150-P');await p.locator('#firm-period [data-value="lr"]').click();check(name+' реальные формулы7.18а',await values({P:20,q:5,n:26,profit:0}));
  check(name+' LR скрывает n и типFC',!await p.locator('#firm-market-n-row').isVisible()&&!await p.locator('#firm-fixed-wrap').isVisible());
  await p.evaluate(()=>{historyCheck();historyBaseline();});await type('firm-market-demand','Q=151-P');check(name+' дробное n26.2',await values({n:26.2})&&await p.locator('#info-costs').textContent().then(s=>s.includes('обычно в задачах требуется найти целое число фирм')));
  await p.evaluate(()=>{historyCheck();historyUndo();});check(name+' отмена спроса',await values({n:26}));await p.evaluate(()=>historyRedo());check(name+' повтор спроса',await values({n:26.2}));
  await p.locator('#firm-period [data-value="sr"]').click();await edit('firm-market-n','26');await type('firm-market-demand','Q=290-P');check(name+' 7.18б цена с рынка30',await values({P:30,q:10,profit:75}));
  await p.locator('#firm-period [data-value="lr"]').click();check(name+' 7.18в n54',await values({P:20,n:54,profit:0}));await p.locator('#firm-period [data-value="sr"]').click();check(name+' SR сохраняет заданное n26',await values({P:30,n:26,q:10}));
  await edit('firm-capacity','5');check(name+' мощность:P160 q5',await values({P:160,q:5,Q:130}));
  const link=await p.evaluate(()=>shareLinkOf()),clone=await browser.newPage();await clone.goto(link);await clone.waitForFunction(()=>STATE.firmMarketResult?.found);check(name+' ссылка туда и обратно',await clone.evaluate(()=>STATE.sceneKey==='firmmarket'&&STATE.firmMarketResult.P===160&&STATE.firmMarket.n==='26'&&STATE.costsSupply.K==='5'&&STATE.panels.length===2));await clone.close();
  await edit('firm-capacity','');await p.locator('#firm-tax-type [data-value="unit"]').click();await edit('firm-tax-rate','10');check(name+' налог фирме10 в равновесии',await values({P:275/7,q:135/14,profit:Math.pow(135/14,2)-25}));
  await p.evaluate(async()=>{await document.fonts.ready;redrawAll();});await p.waitForTimeout(100);
  const exported=await p.evaluate(()=>{const before=compactModelState(collectModelState()),tex=buildTex('',''),after=compactModelState(collectModelState());return{same:JSON.stringify(before)===JSON.stringify(after),stats:buildTex._stats,len:tex.length};});check(name+' экспорт сохраняет состояние',exported.same&&exported.len>1000,exported);check(name+' две панели выгружаются без расхождения',Object.entries(exported.stats||{}).filter(([key])=>/Mismatch|NoRec/.test(key)).every(([,v])=>!v),exported.stats);
  const copies=await p.locator('#info-final .ff-copy').evaluateAll(es=>es.map(e=>e.dataset.ffExpr));check(name+' функции фирмы и рынка копируются',copies.length===2&&await p.evaluate(c=>Math.abs(math.evaluate(c[1],{P:40})-26*math.evaluate(c[0],{P:40}))<1e-7,copies),copies);
  const layout=await p.evaluate(()=>({wide:document.documentElement.scrollWidth>innerWidth+1,bad:[...document.querySelectorAll('.katex-error')].map(e=>e.textContent),overflow:[...document.querySelectorAll('#firm-market-inputs .field,#firm-supply-controls .seg,#info-final .ff')].filter(e=>e.offsetWidth&&e.scrollWidth>e.clientWidth+2).map(e=>e.id||e.className)}));check(name+' компоновка без переполнения',!layout.wide&&!layout.bad.length&&!layout.overflow.length,layout);
  if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e11-shots',{recursive:true});await p.screenshot({path:'.calc2-astra-local/e11-shots/'+name.replaceAll('/','-')+'.png'});}
  await p.evaluate(()=>{setSelfMode(true);buildAnswer();});check(name+' сначала сам скрывает цену и формулы',!await p.locator('#firm-market-price-value').isVisible()&&!await p.locator('#info-final').isVisible());await p.evaluate(()=>setSelfMode(false));
  await p.locator('#cm-curves').click();await type('inp-cmc','3*Q');await p.locator('#firm-tax-type [data-value="none"]').click();check(name+' MC без других затрат',await values({P:870/29,q:290/29}));
  check(name+' толькоMC выбран, лишние средние скрыты',await p.locator('#firm-mc-only').isChecked()&&await p.locator('#firm-mc-only').isDisabled()&&!await p.locator('#inp-catc').locator('xpath=ancestor::*[contains(@class,"fc-card")][1]').isVisible());
  check(name+' нет ошибокJS',!errors.length,errors);await p.close();
 }
 await browser.close();
}
console.log(`Поток Э11: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
