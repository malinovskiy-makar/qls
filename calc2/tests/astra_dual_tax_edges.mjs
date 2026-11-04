import * as pw from 'playwright';import {keepAnswerOpen} from './answer_open.mjs';
let total=0,bad=0;const check=(n,ok,d)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+n+(!ok?' '+JSON.stringify(d):''));};
const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<1e-6;
const cases=[
 {name:'два потоварных налога',d:'100-Q',s:'Q',a:['tax','unit','buyer',10],b:['tax','unit','seller',10],want:[40,60,40,50,800]},
 {name:'оба платит покупатель',d:'100-Q',s:'Q',a:['tax','unit','buyer',5],b:['tax','unit','buyer',15],want:[40,60,40,40,800]},
 {name:'две субсидии',d:'100-Q',s:'Q',a:['subsidy','unit','seller',10],b:['subsidy','unit','seller',10],want:[60,40,60,40,-1200]},
 {name:'два НДС складываются',d:'100-Q',s:'Q',a:['tax','vat','seller',30],b:['tax','vat','seller',20],want:[40,60,40,60,800]},
 {name:'потоварный покупателю и НДС',d:'100-Q',s:'Q',a:['tax','unit','buyer',10],b:['tax','vat','seller',20],want:[450/11,650/11,450/11,540/11,90000/121]},
 {name:'суммарный акциз ровно 100%',d:'100-Q',s:'Q',a:['tax','excise','seller',50],b:['tax','excise','seller',50],want:[0,100,0,100,0]},
 {name:'суммарная субсидия ровно 100%',d:'100-Q',s:'Q',a:['subsidy','subseller','seller',50],b:['subsidy','subseller','seller',50],want:[100,0,100,0,-10000]},
 {name:'вертикальное предложение',d:'180-Q',s:'Q=100',a:['subsidy','unit','buyer',12],b:['tax','unit','seller',24],want:[100,80,68,92,1200]},
 {name:'вертикальный спрос',d:'Q=100',s:'20+Q/3',a:['subsidy','unit','buyer',12],b:['tax','unit','seller',24],want:[100,196/3,160/3,232/3,1200]},
 {name:'созданный субсидией рынок',d:'100-Q',s:'400+2Q',a:['subsidy','unit','seller',500],b:['tax','unit','seller',50],want:[50,50,500,50,-22500],noBase:true},
 {name:'нелинейное предложение',d:'100-Q',s:'Q^2/100',a:['subsidy','unit','buyer',12],b:['tax','unit','seller',24],want:[-50+10*Math.sqrt(113),150-10*Math.sqrt(113),138-10*Math.sqrt(113),162-10*Math.sqrt(113),12*(-50+10*Math.sqrt(113))]},
];
for(const engine of (process.env.ENGINES||'chromium,webkit').split(',')){
 const browser=await pw[engine].launch();keepAnswerOpen(browser);const p=await browser.newPage({viewport:{width:1440,height:950},reducedMotion:'reduce'});
 await p.goto(process.env.CALC2_BASE_URL+'/calc2/');await p.waitForFunction(()=>typeof addSecondTax==='function');
 for(const c of cases){
  const r=await p.evaluate(c=>{
   resetSceneMemory();pickScene('taxes');
   const errors=[];
   for(const [role,expr]of [['demand',c.d],['supply',c.s]]){
    const i=STATE.curves.findIndex(curve=>curve.role===role),curve=STATE.curves[i];
    if(expr==='Q=100')STATE.curves[i]=makeVerticalCurve(100,{id:curve.id,role,color:curve.color,expr:'100',srcForm:'QP',srcExpr:'100'});
    else{const error=updateCurveExpr(curve,expr);if(error)errors.push(error);}
   }
   renderCurveList();
   setType(c.a[0]);setTaxForm(c.a[1]);setTaxSide(c.a[2]);setTax(c.a[3]);addSecondTax();setSecondTax({type:c.b[0],form:c.b[1],side:c.b[2],rate:c.b[3]});buildAnswer();
   const e=STATE.taxEq;return{errors,actual:e?[e.Q,e.Pb,e.Ps,e.Pm,STATE.budget]:[],noBase:STATE.taxNoBase,dwl:STATE.dwl,pair:STATE.taxPair};
  },c);
  check(engine+' '+c.name+' — входы приняты',!r.errors.length,r.errors);
  check(engine+' '+c.name,c.want.every((v,i)=>near(r.actual[i],v)),r);
  if(c.noBase)check(engine+' нет вымышленного сравнения с исходным рынком',r.noBase&&r.dwl===null,r);
 }
 const edge=await p.evaluate(()=>{
  resetSceneMemory();pickScene('taxes');updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),'Q=180-P');updateCurveExpr(STATE.curves.find(c=>c.role==='supply'),'Q=3P-60');setType('subsidy');setTaxForm('unit');setTaxSide('buyer');setTax(300);addSecondTax();setSecondTax({type:'tax',form:'unit',rate:300});
  const market={eq:STATE.taxEq,Pmax:CONFIG.Pmax};
  setType('tax');setTaxForm('unit');setTax(0);setSecondTax({form:'vat'});setSecondTax({bounds:{min:0,max:500,step:.1},rate:300});
  const free={rate:STATE.taxSecond.rate,Q:STATE.taxEq?.Q,saved:collectModelState()};
  setSecondTax({form:'excise'});setSecondTax({rate:150});const capped=STATE.taxSecond.rate;
  applyModelState(free.saved);const restored={rate:STATE.taxSecond.rate,max:STATE.taxSecond.bounds?.max,Q:STATE.taxEq?.Q};
  const before=STATE.taxEq.Q;CONFIG.Qmax=10000;CONFIG.Pmax=10000;redrawAll();const after=STATE.taxEq.Q;
  setTaxForm('excise');setTax(60);setSecondTax({form:'excise',rate:60});const noMarket=!STATE.taxActive&&!!STATE.taxPair.error;
  return{market,free:{rate:free.rate,Q:free.Q},capped,restored,before,after,noMarket};
 });
 check(engine+' рыночная цена включена в окно',near(edge.market.eq.Pm,360)&&edge.market.Pmax>360,edge.market);
 check(engine+' свободная процентная ставка выше 200',edge.free.rate===300&&near(edge.free.Q,300/7),edge.free);
 check(engine+' строгий предел акциза',edge.capped===99,edge.capped);
 check(engine+' границы ставки восстанавливаются',edge.restored.rate===300&&edge.restored.max===500&&near(edge.restored.Q,300/7),edge.restored);
 check(engine+' расчёт не зависит от окна',near(edge.before,edge.after),edge);
 check(engine+' чрезмерные суммарные ставки не дают ложный рынок',edge.noMarket,edge);
 await browser.close();
}
console.log(`Края Э4: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
