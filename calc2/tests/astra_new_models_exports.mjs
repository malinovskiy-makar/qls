/* Реальные PNG и серверные PDF двух новых моделей, обе панели/виды. */
import*as pw from'playwright';import fs from'node:fs';
let total=0,bad=0;const check=(n,ok,r)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(r):''));};
const out='.calc2-astra-local/final-exports';fs.mkdirSync(out,{recursive:true});
for(const engine of['chromium','webkit']){
 const b=await pw[engine].launch(),ctx=await b.newContext({viewport:{width:1440,height:950},reducedMotion:'reduce'}),p=await ctx.newPage();
 await p.goto(process.env.CALC2_BASE_URL+'/login/');await p.fill('#id_username','admin');await p.fill('#id_password','admin12345');await Promise.all([p.waitForNavigation(),p.press('#id_password','Enter')]);await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof buildTex==='function');
 for(const[key,view,quota]of[['firmmarket',null,false],['bigopen','countries',false],['bigopen','world',false],['bigopen','world',true]]){
  const name=engine+'-'+key+'-'+(view||'firm')+(quota?'-quota':'');
  await p.evaluate(({key,view,quota})=>{resetSceneMemory();openModelByUser(key);if(view){STATE.bigTrade.view=view;if(quota){setTradePolicy('bigA',{kind:'quota',quota:10});setTradePolicy('bigB',{kind:'quota',quota:10});}else setTradePolicy('bigA',{kind:'tax',target:'trade',form:'unit',rate:10});}redrawAll();},{key,view,quota});await p.waitForTimeout(450);
  const before=await p.evaluate(()=>JSON.stringify(compactModelState(collectModelState())));
  const dl=p.waitForEvent('download');await p.evaluate(()=>exportPNG(2));const d=await dl;await d.saveAs(out+'/'+name+'.png');const png=fs.readFileSync(out+'/'+name+'.png');check(name+' PNG',png.length>10000&&png.subarray(1,4).toString()==='PNG',{bytes:png.length});
  check(name+' PNG сохраняет состояние',before===await p.evaluate(()=>JSON.stringify(compactModelState(collectModelState()))));
  const pdf=await p.evaluate(async()=>{const form=new FormData();form.append('tex',buildTex('',''));form.append('name',exportBaseName());form.append('csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]')?.value||'');const r=await fetch(CALC2_PDF_URL,{method:'POST',body:form}),buf=new Uint8Array(await r.arrayBuffer());return{status:r.status,ct:r.headers.get('content-type'),bytes:[...buf],error:r.status===200?'':new TextDecoder().decode(buf).slice(0,500)};});
  const bytes=Buffer.from(pdf.bytes),ok=pdf.status===200&&pdf.ct.includes('pdf')&&bytes.subarray(0,5).toString()==='%PDF-';check(name+' PDF',ok,{status:pdf.status,bytes:bytes.length,error:pdf.error});if(ok)fs.writeFileSync(out+'/'+name+'.pdf',bytes);
  check(name+' PDF сохраняет состояние',before===await p.evaluate(()=>JSON.stringify(compactModelState(collectModelState()))));
 }
 await b.close();
}
console.log(`Экспорт новых моделей: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
