/* Э3: длинные дроби и радикалы в действующем интерфейсе. */
import * as pw from 'playwright';
import fs from 'node:fs';
import {keepAnswerOpen} from './answer_open.mjs';
import {installShownReader} from './parse_shown.mjs';
let total=0,bad=0;
const check=(name,ok,detail)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(detail):''));};
const scenes=['fraction','radical','root-list','production'];
for(const engine of (process.env.ENGINES||'chromium,webkit').split(',')){
  const browser=await pw[engine].launch();keepAnswerOpen(browser);
  for(const width of (process.env.WIDTHS||'1440,1280').split(',').map(Number))for(const theme of ['light','dark']){
    const context=await browser.newContext({viewport:{width,height:950},reducedMotion:'reduce'});
    await context.addInitScript(t=>localStorage.setItem('theme',t),theme);
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(process.env.CALC2_BASE_URL+'/calc2/');await page.waitForFunction(()=>typeof CalcNumber==='object');
    await installShownReader(page);
    for(const scene of scenes){
      await page.evaluate(scene=>{
        resetSceneMemory();
        if(scene==='fraction'||scene==='radical'){
          pickScene('sd');
          updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),scene==='fraction'?'Q=100-2P':'100-Q');
          updateCurveExpr(STATE.curves.find(c=>c.role==='supply'),scene==='fraction'?'Q':'Q^2/100');
          renderCurveList();
        }else if(scene==='root-list'){
          pickScene('m-graph');STATE.curves=[];curveCounter=0;addCurve('x^3-3*x');renderGraphRows();
        }else pickScene('prod');
        redrawAll();buildAnswer();
      },scene);
      await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(450);
      const r=await page.evaluate(()=>{
        const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
        const values=[...document.querySelectorAll('#ans-hero .ans-val')].filter(visible);
        const over=[...document.querySelectorAll('#params-panel .stat')].filter(visible)
          .filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({text:__readShownText(e),width:e.clientWidth,scroll:e.scrollWidth}));
        // Радикал KaTeX имеет вынос глифа на 2 px за собственный inline-box.
        // Проверяется доступное место ячейки, а не тесный box самого глифа.
        for(const e of values){const r=e.getBoundingClientRect(),cell=e.closest('.ans-group').getBoundingClientRect();
          if(r.left<cell.left+1||r.left+e.scrollWidth>cell.right-2)over.push({text:__readShownText(e),left:r.left,right:r.left+e.scrollWidth,cellRight:cell.right});}
        const svg=document.getElementById('chart'),box=svg.getBoundingClientRect();
        const clipped=[...svg.querySelectorAll('text.coord-num')].filter(visible).filter(e=>{
          const r=e.getBoundingClientRect();return r.left<box.left+1||r.right>box.right-1||r.bottom>box.bottom-1;
        }).map(e=>({text:e.textContent,left:e.getBoundingClientRect().left,edge:box.left}));
        return{over,values:values.map(__readShownText),katexErrors:[...document.querySelectorAll('.katex-error')].filter(visible).map(e=>e.textContent),
          wide:document.documentElement.scrollWidth>innerWidth+1,clipped};
      });
      const name=[engine,width,theme,scene].join('/');
      check(name+' числа ответа видны',r.values.length>0,r);
      check(name+' строки помещаются',!r.over.length&&!r.wide,r.over);
      check(name+' формулы без ошибок',!r.katexErrors.length,r.katexErrors);
      check(name+' подписи ключевых делений внутри холста',!r.clipped.length,r.clipped);
      if(process.env.SHOTS==='1'){
        fs.mkdirSync('.calc2-astra-local/e3-shots',{recursive:true});
        await page.screenshot({path:'.calc2-astra-local/e3-shots/'+name.replaceAll('/','-')+'.png'});
      }
    }
    check([engine,width,theme].join('/')+' нет ошибок JavaScript',!errors.length,errors);
    await context.close();
  }
  await browser.close();
}
console.log(`Вид Э3: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
