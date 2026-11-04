import*as pw from'playwright';
let total=0,bad=0;
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch();
 for(const width of[390,760])for(const key of['smallopen','monoexport']){
  const p=await b.newPage({viewport:{width,height:844},reducedMotion:'reduce',isMobile:width===390,hasTouch:width===390});await p.goto(process.env.CALC2_BASE_URL+'/calc2/?m='+key);await p.waitForFunction(()=>typeof pickScene==='function');await p.evaluate(key=>{resetSceneMemory();openModelByUser(key);setTradePolicy(key==='smallopen'?'open':'mono',{kind:'subsidy',target:'consumer',form:'buyer',rate:25});},key);
  if(width===390)await p.locator('#ph-tabs [data-tab="cond"]').click();await p.waitForTimeout(150);
  const r=await p.evaluate(()=>{const nodes=[...document.querySelectorAll('.trade-policy-controls button,.trade-policy-controls input')].filter(e=>e.getBoundingClientRect().width>0),overflow=nodes.filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1||r.left<0;}),short=innerWidth<760?nodes.filter(e=>e.getBoundingClientRect().height<43.5):[];return{page:document.documentElement.scrollWidth-innerWidth,overflow:overflow.map(e=>e.id||e.textContent),short:short.map(e=>[e.id||e.textContent,e.getBoundingClientRect().height]),errors:[...document.querySelectorAll('.katex-error')].length};});
  for(const[name,ok]of[['ширина',r.page<=1&&!r.overflow.length&&!r.errors],['касания',!r.short.length]]){total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+[engine,width,key,name].join('/')+(!ok?' '+JSON.stringify(r):''));}await p.close();
 }
 await b.close();
}
console.log(`Э12 узкие окна: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
