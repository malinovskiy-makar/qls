/* Первый эталон НОВОЙ карточки Э11; прежние снимки не перезаписываются.
   Математические числа проверяются независимо до записи снимка. */
import fs from'node:fs';import{chromium}from'playwright';
import*as L from'../../calc2/tests/redesign/lib.mjs';import*as layer from'../../calc2/tests/redesign/layer_old.mjs';
import{keepAnswerOpen}from'../../calc2/tests/answer_open.mjs';
const target='calc2/tests/redesign/baseline/firmmarket.json';
if(fs.existsSync(target))throw Error('Первый эталон уже существует; перезапись запрещена.');
L.configure({layer,base:process.env.CALC2_BASE_URL,layerName:'old'});
const browser=await chromium.launch();keepAnswerOpen(browser);
try{
 const f=await L.openKey(browser,'firmmarket','light');
 const valid=await f.page.evaluate(()=>{const r=STATE.firmMarketResult;return r.P===15&&r.q===4&&r.Q===40&&r.profit===14&&r.n===10&&STATE.panels.length===2&&!document.getElementById('lr-price-field').offsetHeight;});
 if(!valid||f.errors.length)throw Error('Старт не прошёл независимый контроль. '+f.errors.join(';'));
 const start=await L.observe(f.page),controls=start.controls,keys=['mf:#firm-market-demand','mf:#inp-tc'];
 const chosen=keys.map(key=>controls.find(c=>c.key===key));if(chosen.some(x=>!x))throw Error('Нет обоих полей формул в наблюдаемом старте.');
 const record={key:'firmmarket',source:'Новая модель Э11, решение29.10; первый эталон03.11 после проверки15/4/40/14/n10.',start,controls,steps:chosen.map(c=>({path:[c.key],kind:c.kind,effect:'model'})),errors:[]};
 fs.writeFileSync(target,JSON.stringify(record,null,2)+'\n',{flag:'wx'});console.log(target,controls.length+' органов, '+chosen.length+' настоящие правки формул');
}finally{await browser.close();}
