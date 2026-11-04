import*as pw from'playwright';import fs from'node:fs';import{keepAnswerOpen}from'./answer_open.mjs';
let total=0,bad=0;const check=(name,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(r):''));};
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch();keepAnswerOpen(b);
 for(const width of(process.env.WIDTHS||'1440,1280').split(',').map(Number))for(const theme of['light','dark']){
  const p=await b.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[],name=[engine,width,theme].join('/');p.on('pageerror',e=>errors.push(e.message));await p.addInitScript(t=>localStorage.setItem('theme',t),theme);await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof tradeCountry==='function');await p.evaluate(()=>{resetSceneMemory();openModelByUser('smallopen');});
  const click=(prefix,key,value)=>p.locator('#'+prefix+'-policy-controls [data-trade-key="'+key+'"][data-trade-value="'+value+'"]').click();
  const edit=async(id,value)=>{const el=p.locator('#'+id);await el.fill(value);await el.press('Tab');await p.waitForTimeout(100);};
  const type=async(id,text)=>{await p.evaluate(id=>document.getElementById(id)._mf.focus(),id);await p.waitForTimeout(150);await p.evaluate(id=>document.getElementById(id)._mf.executeCommand('selectAll'),id);await p.keyboard.type(text,{delay:20});await p.keyboard.press('Enter');await p.keyboard.press('Tab');await p.waitForTimeout(250);};
  const values=(mono,want)=>p.evaluate(({mono,want})=>{const r=mono?STATE.discr3?.tradeResult:STATE.open?.tradeResult;return r&&!r.error&&Object.entries(want).every(([k,v])=>Math.abs(r[k]-v)<1e-6);},{mono,want});
  const exportCheck=async(label)=>{const r=await p.evaluate(()=>{const before=JSON.stringify(compactModelState(collectModelState())),tex=buildTex('',''),after=JSON.stringify(compactModelState(collectModelState()));return{same:before===after,len:tex.length,stats:buildTex._stats};});check(name+' '+label+' экспорт и состояние',r.same&&r.len>1000&&Object.entries(r.stats||{}).filter(([k])=>/Mismatch|NoRec/.test(k)).every(([,v])=>!v),r);};
  await p.locator('#oi-tariff').click();check(name+' дерево налога:тариф10',await values(false,{Pc:40,Pp:40,Im:20,budget:200}));
  await click('open','target','producer');check(name+' производителям10',await values(false,{Pc:30,Pp:20,Im:50,budget:200}));
  await click('open','target','consumer');check(name+' потребителям10',await values(false,{Pc:40,Pp:30,Im:30,budget:600}));
  await click('open','target','internal');check(name+' внутренний импорт=производители',await values(false,{Pc:30,Pp:20,Im:50,budget:200}));
  await click('open','form','buyer');await edit('open-policy-rate','25');check(name+' акциз от цены покупателя',await values(false,{Pc:30,Pp:22.5,Qs:22.5,budget:168.75}));
  await type('curve-expr-1','Q=120-P');await type('curve-expr-2','Q=2*P-60');
  await p.locator('#open-pw-field .pchip-editable').click();await p.locator('#open-pw-field .param-eq-input').fill('80');await p.locator('#open-pw-field .param-eq-input').press('Enter');
  await click('open','form','unit');await edit('open-policy-rate','10');check(name+' 9.23в внутренний экспорт',await values(false,{Pc:90,Pp:80,Qd:30,Qs:100,Ex:70,Im:0,budget:300}));
  await click('open','target','producer');await edit('open-policy-rate','40');check(name+' 9.23б смена направления',await values(false,{Pc:80,Pp:40,Qd:40,Qs:20,Ex:0,Im:20,budget:800}));
  await click('open','ban','noimport');await p.evaluate(()=>{historyCheck();historyBaseline();});await edit('open-policy-rate','45');check(name+' 9.25д запрет ввоза',await values(false,{Pc:90,Pp:45,Qd:30,Qs:30,Ex:0,Im:0,budget:1350}));
  await p.evaluate(()=>{historyCheck();historyUndo();});check(name+' отмена ставки',await values(false,{Qd:100/3}));await p.evaluate(()=>historyRedo());check(name+' повтор ставки',await values(false,{budget:1350}));
  const link=await p.evaluate(()=>shareLinkOf()),clone=await b.newPage();await clone.goto(link);await clone.waitForFunction(()=>STATE.open?.tradeResult);check(name+' ссылка:ставка и запрет',await clone.evaluate(()=>STATE.openBan==='noimport'&&STATE.openPolicy.rate==='45'&&Math.abs(STATE.open.tradeResult.budget-1350)<1e-6));await clone.close();
  await exportCheck('налог с запретом');
  await click('open','ban','free');await p.locator('#oi-subsidy').click();await edit('open-policy-rate','10');check(name+' субсидия производителю экспорт80',await values(false,{Pc:80,Pp:90,Qd:40,Qs:120,Ex:80,budget:-1200}));
  await exportCheck('субсидия');
  check(name+' было→стало',await p.locator('#ans-hero .ans-was').count()>=7);
  const layout=await p.evaluate(()=>({wide:document.documentElement.scrollWidth>innerWidth+1,bad:[...document.querySelectorAll('.katex-error')].map(e=>e.textContent),overflow:[...document.querySelectorAll('.trade-policy-controls .seg,.trade-policy-controls .field')].filter(e=>e.offsetWidth&&e.scrollWidth>e.clientWidth+2).map(e=>e.className)}));check(name+' компоновка',!layout.wide&&!layout.bad.length&&!layout.overflow.length,layout);
  if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e12-shots',{recursive:true});await p.screenshot({path:'.calc2-astra-local/e12-shots/small-'+name.replaceAll('/','-')+'.png'});}
  await p.evaluate(()=>{setSelfMode(true);buildAnswer();});check(name+' самопроверка закрывает ответ',await p.locator('.ans-val:visible').count()===0);await p.evaluate(()=>setSelfMode(false));
  await p.evaluate(()=>{resetSceneMemory();openModelByUser('monoexport');});await click('mono','kind','tax');await click('mono','target','producer');check(name+' монополист весь выпуск',await values(true,{Q:40,Qd:25,Pc:75,Ex:15,budget:400}));
  await click('mono','target','internal');check(name+' монополист внутренние сделки',await values(true,{Q:50,Qd:20,Pc:80,Ex:30,budget:200}));
  await click('mono','form','buyer');await edit('mono-policy-rate','37.5');check(name+' монополист акциз37.5',await values(true,{Q:50,Qd:10,Pc:90,Ex:40,budget:337.5}));
  await exportCheck('монополист акциз');await click('mono','ban','noexport');check(name+' монополист без вывоза',await values(true,{Q:250/9,Qd:250/9,Ex:0}));
  await click('mono','ban','free');await click('mono','target','trade');await click('mono','kind','subsidy');await edit('mono-policy-rate','10');check(name+' субсидия вывоза монополисту',await values(true,{Q:60,Qd:20,Pc:80,Ex:40,budget:-400}));
  await exportCheck('монополист субсидия');if(process.env.SHOTS==='1')await p.screenshot({path:'.calc2-astra-local/e12-shots/mono-'+name.replaceAll('/','-')+'.png'});
  check(name+' ошибок JS нет',!errors.length,errors);await p.close();
 }
 await b.close();
}
console.log(`Поток Э12: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
