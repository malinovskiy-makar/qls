import*as pw from'playwright';import fs from'node:fs';import{keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(n,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(r):''));};
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);
 for(const width of(process.env.WIDTHS||'1440,1280').split(',').map(Number))for(const theme of['light','dark']){
  const p=await b.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[],name=[engine,width,theme].join('/');p.on('pageerror',e=>errors.push(e.message));await p.addInitScript(t=>localStorage.setItem('theme',t),theme);await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof bigTradeSolve==='function');await p.evaluate(()=>{resetSceneMemory();openModelByUser('bigopen');});await p.waitForTimeout(350);
  const click=(key,field,value)=>p.locator('#big'+key+'-policy-controls [data-trade-key="'+field+'"][data-trade-value="'+value+'"]').click();
  const edit=async(id,value)=>{const el=p.locator('#'+id);await el.fill(value);await el.press('Tab');await p.waitForTimeout(120);};
  const type=async(id,text)=>{await p.evaluate(id=>document.getElementById(id)._mf.focus(),id);await p.waitForTimeout(100);await p.evaluate(id=>document.getElementById(id)._mf.executeCommand('selectAll'),id);await p.keyboard.type(text,{delay:15});await p.keyboard.press('Enter');await p.keyboard.press('Tab');await p.waitForTimeout(250);};
  const value=async(P,T)=>p.evaluate(({P,T})=>{const r=STATE.bigTradeResult;return !r.error&&(P===null?r.Pw===null:Math.abs(r.Pw-P)<1e-6)&&Math.abs(r.volume-T)<1e-6;},{P,T});
  const exp=async(label)=>{const r=await p.evaluate(()=>{const a=JSON.stringify(compactModelState(collectModelState())),tex=buildTex('','');const after=compactModelState(collectModelState()),before=JSON.parse(a),diff=[];const walk=(a,b,path)=>{if(JSON.stringify(a)===JSON.stringify(b))return;if(a&&b&&typeof a==='object'&&typeof b==='object'){for(const key of new Set([...Object.keys(a),...Object.keys(b)]))walk(a[key],b[key],path+'.'+key);}else diff.push([path,a,b]);};walk(before,after,'');return{same:a===JSON.stringify(after),diff,len:tex.length,stats:buildTex._stats};});check(name+' '+label+' TeX',r.same&&r.len>1000&&Object.entries(r.stats||{}).filter(([k])=>/Mismatch|NoRec/.test(k)).every(([,v])=>!v),r);};
  check(name+' старт45/30',await value(45,30));
  check(name+' 4 карточки и 2 графика',await p.evaluate(()=>[...document.querySelectorAll('#sec-bigtrade .sc-card')].length===4&&STATE.panels.length===2));
  check(name+' общая цена',await p.evaluate(()=>JSON.stringify(STATE.panels[0].my.domain())===JSON.stringify(STATE.panels[1].my.domain())));
  check(name+' точки привязаны к своей стране',await p.evaluate(()=>{const ts=snapTargetsAll();return ts.length===4&&ts.find(x=>x.name==='D_A').panel==='big-A'&&ts.find(x=>x.name==='D_B').f(10)===50;}));
  await click('A','kind','tax');check(name+' тарифA10→40/20',await value(40,20));
  await p.waitForTimeout(150);check(name+' было→стало',await p.locator('#ans-hero .ans-was').count()>=20);
  await exp('две страны');
  if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e13-shots',{recursive:true});await p.screenshot({path:'.calc2-astra-local/e13-shots/countries-'+name.replaceAll('/','-')+'.png'});}
  await p.locator('[data-big-view="world"]').click();check(name+' мировой вид',await p.evaluate(()=>STATE.panels.length===1&&STATE.panels[0].id==='big-world'&&document.querySelector('[data-big-world="ED"]').getAttribute('stroke-dasharray')==='6 4'));
  await exp('мировой рынок');if(process.env.SHOTS==='1')await p.screenshot({path:'.calc2-astra-local/e13-shots/world-'+name.replaceAll('/','-')+'.png'});
  await click('B','kind','tax');await edit('bigB-policy-rate','5');check(name+' обе страны42.5/15',await value(42.5,15));
  await p.evaluate(()=>{historyCheck();historyBaseline();});await edit('bigA-policy-rate','15');check(name+' ставка15→40/10',await value(40,10));await p.evaluate(()=>{historyCheck();historyUndo();});check(name+' отмена',await value(42.5,15));await p.evaluate(()=>historyRedo());check(name+' повтор',await value(40,10));
  const link=await p.evaluate(()=>shareLinkOf()),clone=await b.newPage();await clone.goto(link);await clone.waitForFunction(()=>STATE.bigTradeResult);check(name+' ссылка с обоими вмешательствами',await clone.evaluate(()=>Math.abs(STATE.bigTradeResult.Pw-40)<1e-6&&STATE.bigTrade.view==='world'&&STATE.bigTrade.B.policy.rate==='5'));await clone.close();
  await click('A','kind','none');await click('B','kind','none');await type('big-A-D','Q=60-P');await type('big-B-D','Q=120-P');check(name+' формулы меняют направление',await p.evaluate(()=>STATE.bigTradeResult.importer==='B'&&STATE.bigTradeResult.exporter==='A'&&Math.abs(STATE.bigTradeResult.Pw-45)<1e-6));
  await p.locator('[data-big-view="countries"]').click();await p.evaluate(()=>{const a=STATE.panels.find(p=>p.id==='big-A');panelZoomBy(a.id,.8,(a.x0+a.x1)/2,(a.y0+a.y1)/2);redrawAll();});check(name+' зум сохраняет общую цену',await p.evaluate(()=>JSON.stringify(STATE.panels[0].my.domain())===JSON.stringify(STATE.panels[1].my.domain())));
  await p.evaluate(()=>{panelPanBy('big-B',10,25);redrawAll();});check(name+' панорама сохраняет общую цену',await p.evaluate(()=>JSON.stringify(STATE.panels[0].my.domain())===JSON.stringify(STATE.panels[1].my.domain())));await exp('зум/панорама');
  await p.evaluate(()=>{delete STATE.panelWin;redrawAll();});await click('A','kind','quota');await edit('bigA-policy-quota','10');await click('B','kind','quota');await edit('bigB-policy-quota','10');check(name+' две квоты: диапазон',await p.evaluate(()=>Math.abs(STATE.bigTradeResult.priceInterval[0]-35)<1e-6&&Math.abs(STATE.bigTradeResult.priceInterval[1]-55)<1e-6&&Math.abs(STATE.bigTradeResult.quotaRent-200)<1e-6));await exp('квоты');
  await p.locator('[data-big-view="world"]').click();await exp('диапазон цены');
  await click('A','kind','tax');await edit('bigA-policy-rate','40');await click('B','kind','none');check(name+' запретительный тариф',await value(null,0));await exp('нет торговли');
  await p.evaluate(()=>{setSelfMode(true);buildAnswer();});check(name+' самопроверка',await p.locator('.ans-val:visible').count()===0);await p.evaluate(()=>setSelfMode(false));
  const layout=await p.evaluate(()=>({wide:document.documentElement.scrollWidth>innerWidth+1,bad:[...document.querySelectorAll('.katex-error')].map(e=>e.textContent),overflow:[...document.querySelectorAll('.trade-policy-controls .seg,.trade-policy-controls .field')].filter(e=>e.offsetWidth&&e.scrollWidth>e.clientWidth+2).map(e=>e.className)}));check(name+' компоновка',!layout.wide&&!layout.bad.length&&!layout.overflow.length,layout);
  check(name+' JS без ошибок',!errors.length,errors);await p.close();
 }
 await b.close();
}
console.log(`Э13 поток: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
