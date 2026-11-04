/* Первый эталон новой модели; независимые числа проверяются до записи. */
import fs from'node:fs';import{chromium}from'playwright';
import*as L from'../../calc2/tests/redesign/lib.mjs';import*as layer from'../../calc2/tests/redesign/layer_old.mjs';
import{keepAnswerOpen}from'../../calc2/tests/answer_open.mjs';
const target='calc2/tests/redesign/baseline/bigopen.json';
if(fs.existsSync(target))throw Error('Первый эталон уже существует; перезапись запрещена.');
L.configure({layer,base:process.env.CALC2_BASE_URL,layerName:'old'});
const browser=await chromium.launch();keepAnswerOpen(browser);
try{
 const f=await L.openKey(browser,'bigopen','light');
 const valid=await f.page.evaluate(()=>{const r=STATE.bigTradeResult;return Math.abs(r.Pw-45)<1e-7&&Math.abs(r.volume-30)<1e-7&&r.importer==='A'&&r.exporter==='B'&&Math.abs(r.countries.A.cs-2812.5)<1e-7&&Math.abs(r.countries.B.ps-1012.5)<1e-7&&STATE.panels.length===2&&STATE.bigTrade.view==='countries';});
 if(!valid||f.errors.length)throw Error('Старт не прошёл независимый контроль. '+f.errors.join(';'));
 const start=await L.observe(f.page),controls=start.controls,keys=['mf:#big-A-D','mf:#big-A-S','mf:#big-B-D','mf:#big-B-S'];
 const chosen=keys.map(key=>controls.find(c=>c.key===key));if(chosen.some(x=>!x))throw Error('Нет четырёх полей формул.');
 const record={key:'bigopen',source:'Новая модель Э13; первый эталон03.11 после независимой проверки45/30, CSA2812.5, PSB1012.5.',start,controls,steps:chosen.map(c=>({path:[c.key],kind:c.kind,effect:'model'})),errors:[]};
 fs.writeFileSync(target,JSON.stringify(record,null,2)+'\n',{flag:'wx'});console.log(target,controls.length+' органов, '+chosen.length+' настоящие правки формул');
}finally{await browser.close();}
