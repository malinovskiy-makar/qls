import*as pw from'playwright';import fs from'node:fs';
let total=0,bad=0;const check=(n,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(r):''));};
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch();
 for(const width of[390,760]){
  const p=await b.newPage({viewport:{width,height:844},reducedMotion:'reduce',isMobile:width===390,hasTouch:width===390}),name=engine+'/'+width;await p.goto(process.env.CALC2_BASE_URL+'/calc2/?m=bigopen');await p.waitForFunction(()=>STATE.bigTradeResult);await p.evaluate(()=>setTradePolicy('bigA',{kind:'tax',target:'consumer',form:'buyer',rate:25}));
  if(width===390)await p.locator('#ph-tabs [data-tab="cond"]').click();await p.waitForTimeout(200);
  const r=await p.evaluate(()=>{const nodes=[...document.querySelectorAll('#sec-bigtrade button,#sec-bigtrade input')].filter(e=>e.getBoundingClientRect().width>0),overflow=nodes.filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1||r.left<0;}),short=innerWidth<760?nodes.filter(e=>e.getBoundingClientRect().height<43.5):[];return{page:document.documentElement.scrollWidth-innerWidth,overflow:overflow.map(e=>e.id||e.textContent),short:short.map(e=>[e.id||e.textContent,e.getBoundingClientRect().height]),errors:[...document.querySelectorAll('.katex-error')].length};});
  check(name+' ширина',r.page<=1&&!r.overflow.length&&!r.errors,r);check(name+' касания',!r.short.length,r);
  for(const view of['countries','world']){await p.locator('[data-big-view="'+view+'"]').click();await p.waitForTimeout(100);check(name+' '+view+' геометрия',await p.evaluate(()=>STATE.panels.every(p=>p.x1>p.x0+60&&p.y1>p.y0+100)&&document.documentElement.scrollWidth<=innerWidth+1));if(process.env.SHOTS==='1'){fs.mkdirSync('.calc2-astra-local/e13-shots',{recursive:true});await p.screenshot({path:'.calc2-astra-local/e13-shots/'+view+'-'+engine+'-'+width+'.png'});}}
  await p.evaluate(()=>{setTradePolicy('bigA',{kind:'quota',quota:10});setTradePolicy('bigB',{kind:'quota',quota:10});setSelfMode(true);buildAnswer();});await p.waitForTimeout(100);check(name+' диапазон скрыт',await p.locator('.ans-val:visible').count()===0);
  check(name+' проверка слов и границ',await p.evaluate(()=>checkGuess('Не определено','Не определена')===true&&checkGuess('45','Не определена')===false&&checkGuess('[35;55]','[35;55]')===true&&checkGuess('[35;54]','[35;55]')===false&&checkGuess('(35;55)','[35;55]')===false));await p.close();
 }
 await b.close();
}
console.log(`Э13 узкие окна: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
