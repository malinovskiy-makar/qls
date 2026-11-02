// Э5: общие издержки и сравнение ценовой дискриминации с единой ценой.
// Старая запись без левой части означает MC; явная TC=… задаёт общие затраты.
function d3CostMode() {
  const s=splitCurveLhs(STATE.d3MC);
  return !s.error&&lhsKey(s.lhs)==='TC'?'tc':'mc';
}
function discriminationMR(c,q) {
  if(c.linear)return c.linear.b+2*c.linear.a*q;
  if(!Object.prototype.hasOwnProperty.call(c,'_discrMR')){
    const e=mrFormula(c),curve=e?makeCurve(e):null;
    Object.defineProperty(c,'_discrMR',{value:curve&&!curve.error?curve:null,configurable:true});
  }
  return c._discrMR?evalCurve(c._discrMR,q):marginalRevenue(c,q);
}
// Уточнение стационарного кандидата до точности double: погрешность корня
// в 1e-9 после умножения на цену превращалась в ложное «≈ 4 050,000».
function discriminationRoot(f,q,lo,hi) {
  for(let i=0;i<6;i++){
    const h=Math.max(1e-5,Math.abs(q)*1e-5),y=f(q),s=(f(q+h)-f(q-h))/(2*h);
    const next=q-y/s;
    if(!Number.isFinite(next)||next<lo||next>hi||Math.abs(f(next))>Math.abs(y))break;
    if(next===q)break;q=next;
  }
  return q;
}
function discriminationSpan(cs,mc) {
  let span=naturalSpanQ(cs)*2;
  if(mc.linear?.a>0){
    const price=Math.max(...cs.map(c=>evalCurve(c,0)));
    span=Math.max(span,2*(price-mc.linear.b)/mc.linear.a);
  }
  return span;
}
function discriminationCost(expr) {
  const s=splitCurveLhs(expr);
  if(s.error)return {error:s.error};
  const raw=makeCurve(expr);
  if(raw.error)return {error:raw.error};
  if(lhsKey(s.lhs)!=='TC')return {curve:raw,fc:0,vc:q=>integrate(x=>mcFloor(evalCurve(raw,x)),0,q)};
  const fc=evalCurve(raw,0),de=derivativeExpr(s.rhs,'Q');
  if(!Number.isFinite(fc))return {error:'TC должна быть определена при Q = 0: это постоянные издержки.'};
  const curve=de?makeCurve(de):{fn:q=>curveDeriv(raw,q)};
  if(curve.error)return {error:curve.error};
  return {curve,fc,tc:raw,vc:q=>evalCurve(raw,q)-fc};
}

function discriminationComparison(c1,c2,cost,q1,q2) {
  if(!c1.linear||!c2.linear)return discriminationPriceComparison([c1,c2],cost,[q1,q2]);
  const built=sumDemandCurves([c1,c2]);
  if(built.error)return {error:built.error};
  const {segs,kinks,Dfn}=built,mc=q=>evalCurve(cost.curve,q);
  const at=q=>segs.find(s=>q>=s.q0-1e-9&&q<s.q1-1e-9)||segs[segs.length-1];
  const D={fn:Dfn};
  const span=discriminationSpan([c1,c2],cost.curve);
  const qEnd=[c1,c2].every(c=>c.linear&&c.linear.a<=0)?segs[segs.length-1].q1:undefined;
  const options={extra:kinks,vc:cost.vc,span,qEnd,refine:discriminationRoot};
  const best=monoBestOutput(q=>discriminationMR(at(q).D,q),mc,D,options);
  const efficient=monoBestOutput(Dfn,mc,D,{...options,tr:q=>integrateBroken(Dfn,0,q,kinks)});
  const welfareMax=efficient.profit;
  const result=(a,b,p1,p2)=>{
    const Q=a+b,tr=a*p1+b*p2,vc=cost.vc(Q);
    const cs=[integrate(x=>evalCurve(c1,x)-p1,0,a),integrate(x=>evalCurve(c2,x)-p2,0,b)];
    const sw=cs[0]+cs[1]+tr-vc;
    return {q1:a,q2:b,Qtot:Q,P1:a>1e-9?p1:null,P2:b>1e-9?p2:null,
      profit:tr-vc-cost.fc,cs,dwl:Math.max(0,welfareMax-sw)};
  };
  const Q=best.Q||0,P=Q>0?Dfn(Q):Math.max(evalCurve(c1,0),evalCurve(c2,0));
  const quantity=(c)=>Math.max(0,c.linear?(c.linear.a<0?(P-c.linear.b)/c.linear.a:0):(invCurve(c,P)||0));
  const amounts=[c1,c2].map(c=>Q>0?quantity(c):0);
  const flat=[c1,c2].findIndex(c=>c.linear?.a===0&&Math.abs(c.linear.b-P)<1e-8);
  if(flat>=0)amounts[flat]+=Math.max(0,Q-amounts[0]-amounts[1]);
  const uniform=result(amounts[0],amounts[1],P,P);
  uniform.P=Q>0?P:null;uniform.candidates=best.cands;uniform.alts=best.alts;
  const discrimination=result(q1,q2,evalCurve(c1,q1),evalCurve(c2,q2));
  return {discrimination,uniform,delta:discrimination.profit-uniform.profit,fc:cost.fc,
    efficient:{Q:efficient.Q,sw:welfareMax}};
}

// Нелинейная сумма: ищем кандидатов по цене. Это убирает вложенную инверсию
// P(Qsum(P)) внутри каждого шага поиска MR=MC. На границах подключения групп
// есть отдельные кандидаты; стационарные точки перебираются на каждом участке.
function discriminationPriceComparison(cs,cost,allocation) {
  const mc=q=>evalCurve(cost.curve,q),span=discriminationSpan(cs,cost.curve);
  const heads=cs.map(c=>evalCurve(c,0)),cache=new Map();
  const flat=Math.max(0,...cs.filter(c=>c.linear?.a===0).map(c=>c.linear.b));
  const quantity=(c,P)=>{
    const top=evalCurve(c,0);if(P>=top)return 0;
    if(c.linear)return c.linear.a<0?(P-c.linear.b)/c.linear.a:0;
    let lo=0,hi=span;
    for(let i=0;i<24&&Number.isFinite(evalCurve(c,hi))&&evalCurve(c,hi)>P;i++)hi*=2;
    for(let i=0;i<60;i++){
      const mid=(lo+hi)/2,v=evalCurve(c,mid);
      if(Number.isFinite(v)&&v>P)lo=mid;else hi=mid;
    }
    const q=(lo+hi)/2;
    return Math.abs(evalCurve(c,q)-P)<=1e-6*Math.max(1,Math.abs(P))?q:NaN;
  };
  const at=P=>{
    if(cache.has(P))return cache.get(P);
    const qs=cs.map(c=>quantity(c,P)),Q=qs[0]+qs[1];
    const slope=qs.reduce((s,q,i)=>s+(q>1e-9&&! (cs[i].linear?.a===0)?1/curveDeriv(cs[i],q):0),0);
    const row={P,qs,Q,slope};cache.set(P,row);return row;
  };
  const cuts=[...new Set([flat,...heads.filter(p=>p>flat)])].sort((a,b)=>a-b);
  const profits=P=>{const a=at(P);return a.Q+(P-mc(a.Q))*a.slope;};
  const social=P=>{const a=at(P);return P-mc(a.Q);};
  const stationary=f=>{
    const out=[];
    for(let i=0;i<cuts.length-1;i++){
      const lo=cuts[i],hi=cuts[i+1],eps=(hi-lo)*1e-9;
      monoRootsIn(f,lo+eps,hi-eps).forEach(p=>out.push(discriminationRoot(f,p,lo,hi)));
    }
    return out;
  };
  const integral=(c,q)=>{
    if(!(q>0))return 0;
    if(c.linear)return c.linear.b*q+c.linear.a*q*q/2;
    let last=null;
    for(let n=16;n<=16384;n*=2){
      const h=q/n;let sum=evalCurve(c,0)+evalCurve(c,q);
      for(let i=1;i<n;i++)sum+=(i%2?4:2)*evalCurve(c,i*h);
      const value=sum*h/3;
      if(last!=null&&Math.abs(value-last)<Math.max(1e-9,Math.abs(value)*1e-12))return value;
      last=value;
    }
    return last;
  };
  const metrics=(qs,prices)=>{
    const Q=qs[0]+qs[1],tr=qs.reduce((s,q,i)=>s+q*prices[i],0),vc=cost.vc(Q);
    const surplus=qs.map((q,i)=>integral(cs[i],q)-q*prices[i]);
    return {q1:qs[0],q2:qs[1],Qtot:Q,P1:qs[0]>1e-9?prices[0]:null,P2:qs[1]>1e-9?prices[1]:null,
      profit:tr-vc-cost.fc,cs:surplus,sw:surplus[0]+surplus[1]+tr-vc};
  };
  const row=P=>{const a=at(P);return {...metrics(a.qs,[P,P]),P:a.Q>0?P:null};};
  const zero={...metrics([0,0],[0,0]),P:null};
  const extra=[];
  if(flat>0){
    const a=at(flat),base=a.Q,index=cs.findIndex(c=>c.linear?.a===0&&c.linear.b===flat);
    const best=monoBestOutput(()=>flat,mc,null,{qEnd:Infinity,span,vc:cost.vc,refine:discriminationRoot,extra:[base],tr:q=>flat*q});
    const candidates=best.cands.filter(c=>c.Q>=base-1e-8).concat({Q:base,profit:flat*base-cost.vc(base)});
    candidates.sort((a,b)=>b.profit-a.profit);
    const qs=a.qs.slice();qs[index]+=Math.max(0,candidates[0].Q-base);
    extra.push({...metrics(qs,[flat,flat]),P:flat});
  }
  const valid=r=>Number.isFinite(r.profit)&&Number.isFinite(r.sw);
  const choices=[zero,...cuts.map(row),...stationary(profits).map(row),...extra].filter(valid);
  choices.sort((a,b)=>b.profit-a.profit||b.Qtot-a.Qtot);
  const uniform=choices[0];uniform.candidates=choices.map(r=>({Q:r.Qtot,P:r.P,profit:r.profit+cost.fc}));
  uniform.alts=choices.slice(1).filter(r=>Math.abs(r.profit-uniform.profit)<1e-6&&Math.abs(r.Qtot-uniform.Qtot)>1e-8).map(r=>r.Qtot);
  const socialChoices=[zero,...cuts.map(row),...stationary(social).map(row),...extra].filter(valid).sort((a,b)=>b.sw-a.sw);
  const bestSocial=socialChoices[0],d=metrics(allocation,allocation.map((q,i)=>evalCurve(cs[i],q)));
  d.dwl=Math.max(0,bestSocial.sw-d.sw);uniform.dwl=Math.max(0,bestSocial.sw-uniform.sw);
  return {discrimination:d,uniform,delta:d.profit-uniform.profit,fc:cost.fc,efficient:{Q:bestSocial.Qtot,sw:bestSocial.sw}};
}

function discriminationTable(d) {
  const c=d.comparison;
  if(!c)return '';
  if(c.error)return '<div class="warn">Сравнение с единой ценой: '+ffEsc(c.error)+'</div>';
  const a=c.discrimination,b=c.uniform;
  const rows=[['Цена группы 1',a.P1,b.P1],['Цена группы 2',a.P2,b.P2],
    ['Объём группы 1',a.q1,b.q1],['Объём группы 2',a.q2,b.q2],['Общий выпуск',a.Qtot,b.Qtot],
    ['Прибыль',a.profit,b.profit],['Прирост прибыли',c.delta,0],
    ['$CS_1$',a.cs[0],b.cs[0]],['$CS_2$',a.cs[1],b.cs[1]],['$DWL$',a.dwl,b.dwl]];
  const number=v=>v==null?'—':fmt(v);
  const absent=[b.q1<1e-9?'1':'',b.q2<1e-9?'2':''].filter(Boolean);
  return '<table class="tx-table d3-comparison"><caption>Сравнение способов продажи</caption>'
    +'<thead><tr><th></th><th>Дискриминация</th><th>Единая цена</th></tr></thead><tbody>'
    +rows.map(([label,x,y])=>'<tr><td>'+label+'</td><td>'+number(x)+'</td><td>'+number(y)+'</td></tr>').join('')
    +'</tbody></table>'+(absent.length?'<div class="hint">При единой цене '+(absent.length===2?'группы 1 и 2 не покупают':'группа '+absent[0]+' не покупает')+' товар.</div>':'')
    +'<div class="hint">Постоянные издержки FC = '+fmt(c.fc)+' учтены в прибыли обоих способов продажи.</div>';
}

// В панели группы MC берётся от общего выпуска при фиксированном выпуске другой.
function discriminationGroupMC(curve,other) {
  const e=curveFormula(curve);
  if(e){
    const shifted=prepExpr(e).replace(/\bQ\b/g,'(Q+('+CalcNumber.expression(other)+'))');
    const c=makeCurve(shifted);if(!c.error)return c;
  }
  return {fn:q=>evalCurve(curve,q+other)};
}
