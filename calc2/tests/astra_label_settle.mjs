import * as pw from'playwright';import fs from'node:fs';import*as L from'./redesign/lib.mjs';import*as layer from'./redesign/layer_old.mjs';let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
L.configure({layer,base:process.env.CALC2_BASE_URL,layerName:'old'});
for(const engine of(process.env.ENGINES||'chromium,webkit').split(',')){
 const b=await pw[engine].launch(),f=await L.fresh(b,'light'),p=f.page;await p.evaluate(()=>openModelByUser('mono-nat'));await L.settle(p);await p.evaluate(()=>redrawAll());await L.settle(p);await layer.expand(p);await L.settle(p);
 const rec=JSON.parse(fs.readFileSync('calc2/tests/redesign/baseline/mono-nat.json')),c=rec.controls.find(c=>c.key==='mf:#curve-expr-1');await L.act(p,c,'mono-nat');await p.waitForTimeout(1400);
 check(engine+' после правки формулы доступна отмена',await p.evaluate(()=>historyCan().undo));
 await p.evaluate(()=>{window.framesAfterEdit=0;const old=redrawAll;redrawAll=function(){window.framesAfterEdit++;return old();};});await p.waitForTimeout(400);const count=await p.evaluate(()=>window.framesAfterEdit);check(engine+' подписи перестали вызывать кадры',count<=1,count);
 const undo=await p.evaluate(()=>{historyUndo();return STATE.D.expr;});check(engine+' отмена вернула спрос100−Q',await p.evaluate(e=>Math.abs(math.evaluate(e,{Q:40})-60)<1e-8,undo),undo);
 const redo=await p.evaluate(()=>{historyRedo();return STATE.D.expr;});check(engine+' повтор вернул спрос105−Q',await p.evaluate(e=>Math.abs(math.evaluate(e,{Q:40})-65)<1e-8,redo),redo);await b.close();
}
console.log(`Стабилизация подписей: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
