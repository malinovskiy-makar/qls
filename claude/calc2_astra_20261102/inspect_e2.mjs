import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {chromium} from 'playwright';
import {openPage,openScene} from '../../calc2/tests/tex/lib.mjs';
import {tokenTable,addPreviewScript} from '../../calc2/tests/previews/lib.mjs';
const browser=await chromium.launch(),{page}=await openPage(browser,{});
await addPreviewScript(page);await openScene(page,'m-constraint');
const tokens=tokenTable();
const current=await page.evaluate(t=>__PV.build(t),tokens);
const old=execFileSync('git',['show','HEAD:calc2/static/calc2/10-math-core.js'],{encoding:'utf8'});
const start=old.indexOf('function traceLevelCurve('),end=old.indexOf('// Частные производные',start);
await page.evaluate(code=>{traceLevelCurve=eval('('+code.trim()+')');redrawAll();},old.slice(start,end));
const restored=await page.evaluate(t=>__PV.build(t),tokens);
console.log('PREVIEW:',JSON.stringify({current:current.fp,oldTraceOnly:restored.fp,baseline:JSON.parse(fs.readFileSync('calc2/static/calc2/previews.json'))['m-constraint'].fp}));
// Другая страница исключает диагностическую подмену функции из проверки экспорта.
await page.close();const {page:p}=await openPage(browser,{});await openScene(p,'mono');
const r=await p.evaluate(()=>{
  updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),'180-Q');
  updateCurveExpr(STATE.curves.find(c=>c.role==='mc'),'30');
  setType('subsidy');setTax(150);redrawAll();
  const tex=buildTex('','');return {tex,stats:buildTex._stats,win:[CONFIG.Pmin,CONFIG.Pmax]};
});
fs.mkdirSync('.calc2-astra-local/e2-export',{recursive:true});
fs.writeFileSync('.calc2-astra-local/e2-export/subsidy.tex',r.tex);
console.log('EXPORT:',JSON.stringify({stats:r.stats,win:r.win,lines:r.tex.split('\n').filter(l=>/ymin=|22500|Расход бюджета|120/.test(l))}));
await browser.close();
