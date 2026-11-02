/* Предложение фирмы — максимум прибыли по всем кандидатам, а не один
   корень MC=P. Точная ветвь: кусочные TC до третьей степени. */
function firmPolynomial(node, degree=3) {
  const zero=()=>Array(degree+1).fill(0),constant=v=>{const c=zero();c[0]=v;return c;};
  const multiply=(a,b)=>{const c=Array(2*degree+1).fill(0);a.forEach((x,i)=>b.forEach((y,j)=>c[i+j]+=x*y));return c.slice(degree+1).some(v=>v!==0)?null:c.slice(0,degree+1);};
  function walk(n){
    if(n.isParenthesisNode)return walk(n.content);
    if(n.isSymbolNode&&['Q','q','x'].includes(n.name)){const c=zero();c[1]=1;return c;}
    let variable=false;n.traverse(x=>{if(x.isSymbolNode&&['Q','q','x'].includes(x.name))variable=true;});
    if(!variable){try{const v=n.compile().evaluate(paramScope({}));return Number.isFinite(v)?constant(v):null;}catch(e){return null;}}
    if(!n.isOperatorNode)return null;const cs=n.args.map(walk);if(cs.some(c=>!c))return null;
    if(n.fn==='unaryMinus')return cs[0].map(v=>-v);if(n.fn==='unaryPlus')return cs[0];
    if(n.fn==='add'||n.fn==='subtract')return cs[0].map((v,i)=>v+(n.fn==='add'?1:-1)*cs[1][i]);
    if(n.fn==='multiply')return multiply(cs[0],cs[1]);
    if(n.fn==='divide'&&cs[1].slice(1).every(v=>v===0)&&cs[1][0]!==0)return cs[0].map(v=>v/cs[1][0]);
    if(n.fn==='pow'&&cs[1].slice(1).every(v=>v===0)&&Number.isInteger(cs[1][0])&&cs[1][0]>=0&&cs[1][0]<=degree){let c=constant(1);for(let i=0;i<cs[1][0];i++){c=multiply(c,cs[0]);if(!c)return null;}return c;}
    return null;
  }
  return walk(typeof node==='string'?math.parse(prepExpr(node)):node);
}
const firmPolyAt=(c,q)=>c.reduceRight((s,v)=>s*q+v,0);
const firmPolyDerivative=c=>c.slice(1).map((v,i)=>v*(i+1));
function firmPolyExpr(c,v='Q'){
  const xs=[];for(let i=c.length-1;i>=0;i--)if(c[i]!==0)xs.push(CalcNumber.expression(c[i],{atomic:true})+(i?'*'+v+(i>1?'^'+i:''):''));
  return macroSimplify(xs.join('+')||'0');
}
function firmPolyRoots(c){
  while(c.length>1&&c.at(-1)===0)c=c.slice(0,-1);
  if(c.length===1)return[];if(c.length===2)return[-c[0]/c[1]];
  if(c.length===3)return plantsQuadraticRoots(c[2],c[1],c[0]);
  const crit=firmPolyRoots(firmPolyDerivative(c)),bound=1+Math.max(...c.slice(0,-1).map(x=>Math.abs(x/c.at(-1))));
  const xs=[-bound,...crit.filter(x=>x>-bound&&x<bound).sort((a,b)=>a-b),bound],out=[];
  const f=x=>firmPolyAt(c,x);for(const x of xs)if(Math.abs(f(x))<1e-9)out.push(x);
  for(let i=1;i<xs.length;i++){let lo=xs[i-1],hi=xs[i],fl=f(lo);if(fl*f(hi)>=0)continue;for(let k=0;k<80;k++){const m=(lo+hi)/2,fm=f(m);if(fl*fm<=0)hi=m;else{lo=m;fl=fm;}}out.push((lo+hi)/2);}return out;
}
function firmPolynomialPieces(expr,mode,K){
  let node=liftConditional(math.parse(prepExpr(expr))),cuts=[0,K],unsupported=false;
  const boundary=(left,right)=>{const a=firmPolynomial(left),b=firmPolynomial(right);if(!a||!b){unsupported=true;return;}firmPolyRoots(a.map((v,i)=>v-b[i])).forEach(x=>{if(x>0&&x<K)cuts.push(x);});};
  node.traverse(n=>{if(!n.isConditionalNode&&n.type!=='ConditionalNode')return;n.condition.traverse(c=>{
    if(c.type==='RelationalNode'){if(!Array.isArray(c.params)){unsupported=true;return;}for(let i=1;i<c.params.length;i++)boundary(c.params[i-1],c.params[i]);}
    else if(c.isOperatorNode&&['smaller','smallerEq','larger','largerEq','equal','unequal'].includes(c.fn))boundary(c.args[0],c.args[1]);
  });});
  if(unsupported)return null;
  cuts=[...new Set(cuts)].sort((a,b)=>a-b);
  const leaf=(n,q)=>{while(n.isParenthesisNode)n=n.content;if(n.type==='ConditionalNode')return leaf(n.condition.compile().evaluate(paramScope(axisScope(q)))?n.trueExpr:n.falseExpr,q);return n;};
  const pieces=[];let offset=0;
  for(let i=1;i<cuts.length;i++){
    const lo=cuts[i-1],hi=cuts[i],mid=Number.isFinite(hi)?(lo+hi)/2:lo+Math.max(1,lo);
    const branch=leaf(node,mid);if((branch.isSymbolNode&&['NaN','undefined'].includes(branch.name))||(branch.isConstantNode&&Number.isNaN(branch.value)))continue;let c=firmPolynomial(branch);if(!c)return null;
    if(mode==='mc'){if(c[3]!==0)return null;c=[0,c[0],c[1]/2,c[2]/3];c[0]=offset-firmPolyAt(c,lo);if(Number.isFinite(hi))offset=firmPolyAt(c,hi);}
    const boundary=q=>{if(mode==='mc')return true;const other=firmPolynomial(leaf(node,q));return !!other&&Math.abs(firmPolyAt(other.map((v,i)=>v-c[i]),q))<1e-10*Math.max(1,Math.abs(firmPolyAt([0,...c.slice(1)],q)));};
    pieces.push({lo,hi,c,loClosed:boundary(lo),hiClosed:Number.isFinite(hi)?boundary(hi):false});
  }
  return pieces;
}
function firmTax(t={}){
  const type=t.type||'none',sgn=t.kind==='subsidy'?-1:1,rate=CalcNumber.parse(String(t.rate??0))?.value;
  if(type!=='none'&&(!Number.isFinite(rate)||rate<0))throw Error('Ставка должна быть неотрицательным числом.');
  const alpha=type==='revenue'?1-sgn*rate/100:1;
  if(alpha<0)throw Error('Налог на выручку должен быть не больше 100 %.');
  return{alpha,unit:type==='unit'?sgn*rate:0,lump:type==='lump'?sgn*rate:0,type,kind:t.kind||'tax',rate:rate||0};
}
function firmSupplyBuild(raw={}){
  try{
    const c={expr:'Q^3-6*Q^2+15*Q+18',mode:'tc',period:'sr',kind:'sunk',...raw},sp=splitCurveLhs(c.expr);
    if(sp.error)throw Error(sp.error);if(sp.lhs&&lhsKey(sp.lhs)!==(c.mode==='mc'?'MC':'TC'))throw Error('Используйте '+(c.mode==='mc'?'MC':'TC')+' = …');
    c.expr=sp.rhs;const parsed=compileFormula(sp.rhs);if(parsed.error)throw Error(parsed.error);
    let K=c.K==null||c.K===''?Infinity:CalcNumber.parse(String(c.K))?.value;if(!(K>=0))throw Error('Мощность K должна быть неотрицательной.');
    const tax=firmTax(c.tax),original=firmPolynomialPieces(sp.rhs,c.mode,K);
    if(tax.alpha===0)return firmZeroRevenue(c,tax);
    if(!original)return firmSupplyNumeric({...c,expr:sp.rhs},tax,K,parsed.compiled);
    if(original.length)K=Math.min(K,original.at(-1).hi);
    const fc=c.mode==='mc'?0:parsed.compiled.evaluate(paramScope(axisScope(0)));
    if(!Number.isFinite(fc)||fc<0)throw Error('Постоянные издержки TC(0) должны быть конечными и неотрицательными.');
    const avoidable=c.period==='lr'||c.kind==='quasi',zeroCost=avoidable?0:fc+tax.lump;
    let autoCap=null;
    for(const p of original){const mc=firmPolyDerivative(p.c);for(const q of firmPolyRoots(mc))if(q>Math.max(0,p.lo)&&q<=p.hi&&firmPolyAt(firmPolyDerivative(mc),q)<0){K=Math.min(K,q);autoCap=K;}}
    const pieces=original.filter(p=>p.lo<K).map(p=>({...p,hi:Math.min(p.hi,K),hiClosed:K<p.hi?true:p.hiClosed}));
    const model={config:c,tax,K,autoCap,fc,zeroCost,avoidable,pieces,exact:true,candidates:[]};
    model.tc=q=>{if(q<0||q>K)return NaN;if(c.mode==='mc'){const p=pieces.find(x=>q>=x.lo&&q<=x.hi);return p?firmPolyAt(p.c,q):q===0?0:NaN;}return parsed.compiled.evaluate(paramScope(axisScope(q)));};
    model.mc=q=>{const p=pieces.find(x=>q>=x.lo&&q<=x.hi);return p?firmPolyAt(firmPolyDerivative(p.c),q):NaN;};
    model.netCost=q=>{if(q===0)return 0;const p=pieces.find(x=>q>=x.lo&&q<=x.hi&&(q!==x.lo||x.loClosed)&&(q!==x.hi||x.hiClosed));if(!p)return NaN;const net=p.c.slice();net[0]+=tax.lump-zeroCost;net[1]+=tax.unit;return firmPolyAt(net,q);};
    const add=b=>{b.id=model.candidates.length;model.candidates.push(b);};
    add({kind:'fixed',Q:0,cost:0,lo:0,hi:Infinity,expr:'0',attained:true});
    function endpoint(q,net){const cost=firmPolyAt(net,q),actual=model.netCost(q),attained=Math.abs(actual-cost)<1e-8*Math.max(1,Math.abs(actual));if(q===0&&attained)return;if(model.candidates.some(b=>b.kind==='fixed'&&b.Q===q&&Math.abs(b.cost-cost)<1e-9&&b.attained===attained))return;add({kind:'fixed',Q:q,cost,lo:0,hi:Infinity,expr:CalcNumber.expression(q),attained});}
    for(const p of pieces){
      const net=p.c.slice();net[0]+=tax.lump-zeroCost;net[1]+=tax.unit;
      const mc=firmPolyDerivative(net),split=[p.lo,p.hi,...firmPolyRoots(firmPolyDerivative(mc)).filter(q=>q>p.lo&&q<p.hi)].sort((a,b)=>a-b);
      for(const q of[p.lo,p.hi].filter(Number.isFinite))endpoint(q,net);
      for(let i=1;i<split.length;i++){
        const loQ=split[i-1],hiQ=split[i],mid=Number.isFinite(hiQ)?(loQ+hiQ)/2:loQ+Math.max(1,loQ);
        endpoint(loQ,net);if(Number.isFinite(hiQ))endpoint(hiQ,net);
        const slope=firmPolyAt(firmPolyDerivative(mc),mid);
        if(mc.slice(1).every(v=>v===0)){
          const P=mc[0]/tax.alpha;
          if(P>=0)add({kind:'flat',lo:P,hi:P,loQ,hiQ,net,loClosed:loQ===0?net[0]===0:p.loClosed,hiClosed:p.hiClosed,expr:null,attained:true});
          if(!Number.isFinite(hiQ))add({kind:'infinite',lo:Math.max(0,P),threshold:P,hi:Infinity,expr:'Infinity',attained:false});
        }else if(slope>0){
          const lo=Math.max(0,firmPolyAt(mc,loQ)/tax.alpha),hi=Number.isFinite(hiQ)?firmPolyAt(mc,hiQ)/tax.alpha:Infinity;
          if(hi<lo)continue;
          let expr;
          if(!mc[2])expr=macroSimplify('('+CalcNumber.expression(tax.alpha)+'*P-('+CalcNumber.expression(mc[0])+'))/('+CalcNumber.expression(mc[1])+')');
          else expr=macroSimplify('(-('+CalcNumber.expression(mc[1])+')+sqrt(('+CalcNumber.expression(mc[1])+')^2-4*('+CalcNumber.expression(mc[2])+')*(('+CalcNumber.expression(mc[0])+')-('+CalcNumber.expression(tax.alpha)+')*P)))/(2*('+CalcNumber.expression(mc[2])+'))');
          add({kind:'curve',lo,hi,loQ,hiQ,mc,net,expr,attained:true});
        }
      }
    }
    model.at=P=>firmSupplyAt(model,P);model.shutdown=firmShutdown(model);
    model.schedule=firmSupplySchedule(model);return model;
  }catch(e){return{error:/^[А-ЯЁ]/.test(e.message)?e.message:mathErrorRu(e.message)};}
}
function firmZeroRevenue(c,tax){
  const base=firmSupplyBuild({...c,tax:{type:'none'}});if(base.error)return base;
  const r=base.at(0),expr=r.unbounded?'Infinity':r.unattained?'NaN':CalcNumber.expression(r.Q);
  return{...base,config:c,tax,priceIndependent:r,shutdown:r.Q===0&&!r.tie?Infinity:-Infinity,
    at:P=>Number.isFinite(P)&&P>=0?{...r,P}:{error:'Цена должна быть неотрицательной.'},
    schedule:{rows:[{lo:0,hi:Infinity,expr,unattained:r.unattained}],points:[r]}};
}
function firmCandidateAt(m,b,P){
  if(P<b.lo-1e-9||P>b.hi+1e-9)return null;
  if(b.kind==='infinite')return P>b.threshold+1e-9?{Q:Infinity,gain:Infinity,branch:b}:null;
  if(b.kind==='fixed')return{Q:b.Q,gain:m.tax.alpha*P*b.Q-b.cost,branch:b,attained:b.attained};
  if(b.kind==='flat'){if(Math.abs(P-b.lo)>1e-9)return null;const q=b.loClosed?b.loQ:Number.isFinite(b.hiQ)?(b.loQ+b.hiQ)/2:b.loQ+1;return{Q:q,gain:m.tax.alpha*P*q-firmPolyAt(b.net,q),interval:[b.loQ,b.hiQ],intervalClosed:[b.loClosed,b.hiClosed],branch:b,attained:true};}
  const target=m.tax.alpha*P,roots=plantsQuadraticRoots(b.mc[2]||0,b.mc[1]||0,b.mc[0]-target),q=roots.find(x=>x>=b.loQ-1e-7&&x<=b.hiQ+1e-7&&firmPolyAt(firmPolyDerivative(b.mc),x)>=-1e-7);
  if(q===undefined)return null;const Q=Math.max(b.loQ,Math.min(b.hiQ,q)),cost=firmPolyAt(b.net,Q),actual=m.netCost(Q);return{Q,gain:m.tax.alpha*P*Q-cost,branch:b,attained:Math.abs(actual-cost)<1e-8*Math.max(1,Math.abs(actual))};
}
function firmSupplyAt(m,P){
  if(m.error)return m;if(!Number.isFinite(P)||P<0)return{error:'Цена должна быть неотрицательной.'};
  const cs=m.candidates.map(b=>firmCandidateAt(m,b,P)).filter(Boolean),best=Math.max(...cs.map(x=>x.gain));
  if(best===Infinity)return{P,Q:Infinity,profit:Infinity,outputs:[],intervals:[],unbounded:true};
  const winners=cs.filter(x=>Math.abs(x.gain-best)<1e-8*Math.max(1,Math.abs(best))),attained=winners.filter(x=>x.attained!==false);
  const outputs=[...new Set(attained.map(x=>x.Q))].sort((a,b)=>a-b),intervals=attained.filter(x=>x.interval).map(x=>x.interval);
  const intervalClosed=attained.filter(x=>x.interval).map(x=>x.intervalClosed),last=intervals.at(-1),ends=intervalClosed.at(-1);
  const Q=last?(Number.isFinite(last[1])&&ends[1]?last[1]:ends[0]?last[0]:Number.isFinite(last[1])?(last[0]+last[1])/2:last[0]+1):outputs.at(-1);
  return{P,Q:Q??null,profit:best-m.zeroCost,outputs,intervals,intervalClosed,unattained:!attained.length,branch:attained.at(-1)?.branch||winners[0]?.branch,tie:outputs.length>1||intervals.length>0};
}
function firmSupplySchedule(m){
  const cuts=Number.isFinite(m.shutdown)&&m.shutdown>=0?[0,m.shutdown]:[0],bs=m.candidates.filter(b=>b.kind!=='flat'&&b.kind!=='infinite');
  for(const b of m.candidates)for(const p of[b.lo,b.hi])if(Number.isFinite(p)&&p>=0)cuts.push(p);
  for(let i=0;i<bs.length;i++)for(let j=0;j<i;j++){
    const a=bs[i],b=bs[j],lo=Math.max(a.lo,b.lo),hi=Math.min(a.hi,b.hi);if(hi<=lo)continue;
    const f=P=>{const x=firmCandidateAt(m,a,P),y=firmCandidateAt(m,b,P);return x&&y?x.gain-y.gain:NaN;};
    let left=lo,right=Number.isFinite(hi)?hi:Math.max(1,lo+1),fl=f(left),fr=f(right);
    if(!Number.isFinite(hi)){
      if(fl===0)continue;
      const qa=firmCandidateAt(m,a,right)?.Q,qb=firmCandidateAt(m,b,right)?.Q,dq=qa-qb;
      // Кандидаты лежат на упорядоченных неперекрывающихся участках Q.
      // Если разность прибыли уже уходит от нуля, пересечения дальше нет.
      if((dq!==0&&Math.sign(fl)===Math.sign(dq))||(a.kind==='fixed'&&b.kind==='fixed'&&dq===0))continue;
      for(let k=0;k<1024&&fl*fr>=0&&Number.isFinite(fr);k++){right=right*2+1;fr=f(right);}
    }
    if(fl*fr<0){for(let k=0;k<75;k++){const mid=(left+right)/2,fm=f(mid);if(fl*fm<=0){right=mid;fr=fm;}else{left=mid;fl=fm;}}cuts.push((left+right)/2);}
  }
  cuts.sort((a,b)=>a-b);const xs=cuts.filter((x,i)=>!i||x-cuts[i-1]>1e-8*Math.max(1,x));xs.push(Infinity);
  const rows=[];
  for(let i=1;i<xs.length;i++){
    const lo=xs[i-1],hi=xs[i],P=Number.isFinite(hi)?(lo+hi)/2:lo+Math.max(1,lo),r=m.at(P),expr=r.unbounded?'Infinity':r.branch?.expr;
    const last=rows.at(-1);if(last&&last.expr===expr&&last.unattained===r.unattained)last.hi=hi;else rows.push({lo,hi,expr,branch:r.branch,unattained:r.unattained});
  }
  const boundaries=[...new Set([0,...rows.flatMap(r=>[r.lo,r.hi]).filter(Number.isFinite),...m.candidates.filter(b=>b.kind==='flat').map(b=>b.lo)])].sort((a,b)=>a-b);
  return{rows,points:boundaries.map(P=>m.at(P))};
}
function firmShutdown(m){
  let price=Infinity;
  for(const p of m.pieces){
    const c=p.c.slice();c[0]+=m.tax.lump-m.zeroCost;c[1]+=m.tax.unit;
    const candidates=[p.lo,p.hi,...firmPolyRoots([-c[0],0,c[2],2*c[3]]).filter(q=>q>p.lo&&q<p.hi)];
    for(const q of candidates){
      let v;if(q===0)v=c[0]>0?Infinity:c[0]<0?-Infinity:c[1];
      else if(q===Infinity)v=c[3]>0||c[2]>0?Infinity:c[3]<0||c[2]<0?-Infinity:c[1];
      else v=firmPolyAt(c,q)/q;
      price=Math.min(price,v/m.tax.alpha);
    }
  }
  return price;
}
/* Общая функция: численная сетка + все найденные стационарные точки.
   Ограничение поиска сообщается явно, край не называется бесконечностью. */
function firmSupplyNumeric(c,tax,K,compiled){
  const evaluate=q=>{try{const v=compiled.evaluate(paramScope(axisScope(q)));return Number.isFinite(v)?v:NaN;}catch(e){return NaN;}};
  let derivative=null;if(c.mode!=='mc'){const e=derivativeExpr(c.expr,'Q');if(e)derivative=compileFormula(e).compiled;}
  const mc=c.mode==='mc'?evaluate:q=>{try{if(derivative)return derivative.evaluate(paramScope(axisScope(q)));}catch(e){}const h=Math.max(1e-7,q*1e-5);return(evaluate(q+h)-evaluate(Math.max(0,q-h)))/(q+h-Math.max(0,q-h));};
  let top=Number.isFinite(K)?K:1e6;
  function grid(top){const xs=[0,top];for(let e=-9;e<=6;e+=.025){const q=10**e;if(q<top)xs.push(q);}if(Number.isFinite(K))for(let i=1;i<800;i++)xs.push(top*i/800);return[...new Set(xs)].sort((a,b)=>a-b);}
  let xs=grid(top),autoCap=null;
  const root=(f,a,b)=>{let fa=f(a);for(let i=0;i<70;i++){const z=(a+b)/2,fz=f(z);if(fa*fz<=0)b=z;else{a=z;fa=fz;}}return(a+b)/2;};
  for(let i=1;i<xs.length;i++){const a=mc(xs[i-1]),b=mc(xs[i]);if(a>0&&b<=0){autoCap=root(mc,xs[i-1],xs[i]);K=Math.min(K,autoCap);top=K;xs=grid(top);break;}}
  let tc=evaluate;
  if(c.mode==='mc'){
    const integral=[0];for(let i=1;i<xs.length;i++){const a=xs[i-1],b=xs[i];integral[i]=integral[i-1]+integrate(mc,a,b,20);}
    tc=q=>{if(q===0)return 0;let lo=0,hi=xs.length-1;while(hi-lo>1){const mid=(lo+hi)>>1;if(xs[mid]<=q)lo=mid;else hi=mid;}return integral[lo]+integrate(mc,xs[lo],q,40);};
  }
  let fc=c.mode==='mc'?0:tc(0);const fcKind=Number.isFinite(fc)?'exact':'limit';if(!Number.isFinite(fc)){const a=tc(1e-10),b=tc(1e-12);if(Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<1e-7)fc=Math.abs(b)<1e-7?0:b;}
  if(!Number.isFinite(fc)||fc<0)throw Error('Постоянные издержки TC(0) не определены или отрицательны.');
  const avoidable=c.period==='lr'||c.kind==='quasi',zeroCost=avoidable?0:fc+tax.lump;
  const m={config:c,tax,K,autoCap,fc,zeroCost,avoidable,tc,mc,fcKind,exact:false,searchTop:top,schedule:{rows:[],points:[]},cache:new Map()};
  const value=q=>q===0?0:tc(q)+tax.unit*q+tax.lump-zeroCost,vs=xs.map(value),ms=xs.map(mc);
  m.at=P=>{
    if(m.cache.has(P))return m.cache.get(P);if(!Number.isFinite(P)||P<0)return{error:'Цена должна быть неотрицательной.'};
    const target=tax.alpha*P-tax.unit,candidates=xs.map((Q,i)=>({Q,gain:tax.alpha*P*Q-vs[i]}));
    for(let i=1;i<xs.length;i++)if((ms[i-1]-target)*(ms[i]-target)<0){const Q=root(q=>mc(q)-target,xs[i-1],xs[i]);candidates.push({Q,gain:tax.alpha*P*Q-value(Q)});}
    const finite=candidates.filter(x=>Number.isFinite(x.gain)),best=Math.max(...finite.map(x=>x.gain)),winner=finite.reduce((a,b)=>b.gain>a.gain?b:a),outputs=[winner.Q];
    const r={P,Q:winner.Q,profit:best-zeroCost,outputs:[...new Set(outputs)].sort((a,b)=>a-b),intervals:[],approx:true,boundary:!Number.isFinite(K)&&winner.Q===top};r.tie=r.outputs.some(q=>Math.abs(q-r.Q)>1e-4*Math.max(1,r.Q));m.cache.set(P,r);return r;
  };
  const average=q=>q>0?value(q)/(tax.alpha*q):Infinity;
  let bestI=1;for(let i=2;i<xs.length;i++)if(average(xs[i])<average(xs[bestI]))bestI=i;
  let lo=xs[Math.max(1,bestI-1)],hi=xs[Math.min(xs.length-1,bestI+1)];for(let i=0;i<75;i++){const a=lo+(hi-lo)/3,b=hi-(hi-lo)/3;if(average(a)<average(b))hi=b;else lo=a;}
  m.shutdown=Math.min(average(xs[bestI]),average((lo+hi)/2));return m;
}

function firmSupplyConfig(){return{expr:STATE.costsMode==='curves'?STATE.costsMCx:STATE.costsTC,mode:STATE.costsMode==='curves'?'mc':'tc',...(STATE.costsSupply||{})};}
let _firmSupplyCache=null;
function recomputeFirmSupply(){
  renderFirmSupplyControls();
  if(STATE.costsMode==='curves'&&!STATE.costsMCOnly){STATE.firmSupply=null;return;}
  const c=firmSupplyConfig(),key=JSON.stringify([c,STATE.params]);
  if(_firmSupplyCache?.key===key){STATE.firmSupply=_firmSupplyCache.model;return;}
  const model=firmSupplyBuild(c);STATE.firmSupply=model;_firmSupplyCache={key,model};
  if(!model.error&&model.tax.type!=='none')model.before=firmSupplyBuild({...c,tax:{type:'none'}});
}
function recomputeFirmSupplyPrice(){
  const m=STATE.firmSupply;if(!m||m.error)return;
  const r=m.at(Number(STATE.lrPrice));STATE.firmSupplyResult=r;
  const finite=Number.isFinite(r.Q),Q=finite?r.Q:null;
  const roots=Q===0&&m.exact?m.candidates.filter(b=>b.kind==='curve').map(b=>firmCandidateAt(m,b,r.P)?.Q).filter(q=>q>0):[];
  const flat=m.exact&&m.pieces.length===1&&m.pieces[0].c.slice(2).every(x=>x===0);
  STATE.lr={P:STATE.lrPrice,Q,Qmc:Q>0?Q:roots.length?Math.max(...roots):null,profit:r.profit,atc:Q>0?STATE.lrPrice-r.profit/Q:NaN,avc:Q>0?(m.tc(Q)-m.fc)/Q:NaN,
    fc:m.zeroCost,shutdown:Q===0,shutPrice:m.shutdown,shutIsPoint:!!m.schedule.points.find(x=>Math.abs(x.P-m.shutdown)<1e-8&&x.outputs?.some(q=>q>0)),breakeven:realMin(STATE.minATC)?.val??null,
    note:r.unbounded?'Конечного оптимума нет: выпуск выгодно наращивать без предела.':r.unattained?'Максимум не достигается: можно приближаться к границе, которая не входит в область функции.':r.boundary?'Выпуск выгодно увеличивать за пределы численного поиска.':flat?(r.intervals?.length?'MC постоянна: единственного оптимума нет, любой выпуск в указанном интервале равноценен.':Q===0?'MC постоянна; цена ниже неё: выгодно не производить вовсе.':null):null};
}
function firmOutputText(r,tex=false){
  const f=x=>x===Infinity?(tex?'\\infty':'∞'):tex?CalcNumber.format(x,{tex:true}):fmt(x);
  if(r.unbounded)return f(Infinity);if(r.unattained)return tex?'\\text{нет максимума}':'Максимум не достигается';
  if(r.intervals?.length)return r.intervals.map((x,i)=>{const ends=r.intervalClosed?.[i]||[true,Number.isFinite(x[1])];return(ends[0]?'[':'(')+f(x[0])+'; '+f(x[1])+(ends[1]?']':')');}).join(tex?' \\cup ':' ∪ ');
  return(r.tie&&r.outputs?.length?r.outputs:[r.Q]).map(f).join(tex?' \\;\\text{или}\\; ':'; ');
}
function firmFinalRecord(m){
  const rec={name:'Предложение фирмы',color:COL.S,lhs:'Q_s'};
  if(m.priceIndependent)return{...rec,expr:m.priceIndependent.unattained?'NaN':CalcNumber.expression(m.priceIndependent.Q),latex:firmOutputText(m.priceIndependent,true)+' \\quad(P \\ge 0)',note:'При налоге 100 % выручка полностью поступает в бюджет: оптимальный выпуск от цены не зависит.'};
  if(!m.exact)return{...rec,note:'Предложение найдено численно на 0 ≤ Q ≤ '+fmt(m.searchTop)+'. Кусочная формула для этой функции не выведена.'};
  const lines=[],copy=[];
  const special=m.schedule.points.filter(r=>r.tie||r.unattained||r.unbounded&&r.P===0);
  const at=P=>special.find(r=>Math.abs(r.P-P)<1e-8*Math.max(1,P));
  for(const r of special){lines.push({p:r.P,tex:firmOutputText(r,true)+', & P = '+CalcNumber.format(r.P,{tex:true})});copy.push('(P == '+CalcNumber.expression(r.P)+' ? '+(r.unattained?'NaN':r.Q===Infinity?'Infinity':CalcNumber.expression(r.Q))+' : ');}
  for(const row of m.schedule.rows){
    let cond;if(row.lo===0)cond=Number.isFinite(row.hi)?'P '+(at(row.hi)?'<':'\\le')+' '+CalcNumber.format(row.hi,{tex:true}):'P \\ge 0';
    else cond=CalcNumber.format(row.lo,{tex:true})+(at(row.lo)?' < P':' \\le P')+(Number.isFinite(row.hi)?' '+(at(row.hi)?'<':'\\le')+' '+CalcNumber.format(row.hi,{tex:true}):'');
    const body=row.unattained?'\\text{нет максимума}':row.expr==='Infinity'?'\\infty':mathToTex(row.expr);
    lines.push({p:row.lo+.00000001,tex:body+', & '+cond});
    copy.push('(P '+(Number.isFinite(row.hi)?'< '+CalcNumber.expression(row.hi):'>= 0')+' ? '+(row.unattained?'NaN':row.expr)+' : ');
  }
  rec.latex='\\begin{cases}'+lines.sort((a,b)=>a.p-b.p).map(r=>r.tex).join('\\\\')+'\\end{cases}';rec.expr=copy.join('')+'NaN'+')'.repeat(copy.length);
  if(special.some(r=>r.tie))rec.note='В точке безразличия равновыгодны все показанные выпуски. Копируемая формула выбирает один из них.';
  return rec;
}
function updateFirmSupplyPanel(box){
  const m=STATE.firmSupply;if(m.error){box.innerHTML='<div class="warn">'+ffEsc(m.error)+'</div>';return;}
  const r=STATE.firmSupplyResult||m.at(STATE.lrPrice),stat=(label,value,main=false)=>'<div class="stat'+(main?' ans-main':'')+'"><span>'+label+'</span><b>'+value+'</b></div>';
  let html=stat('Выпуск Q'+(r.tie?' — безразлично':''),firmOutputText(r),true)+stat(r.unattained?'Верхняя грань прибыли':'Прибыль Π',r.unbounded?'∞':fmt(r.profit),true)+stat('Цена P',fmt(r.P));
  html+=stat(m.config.period==='lr'?'Цена ухода с рынка (min ATC)':m.avoidable?'Цена закрытия (с квазипостоянными)':'Цена закрытия (min AVC)',m.priceIndependent?(r.tie?'Все цены: безразличие':r.Q===0?'При любой цене фирма закрыта':'При любой цене фирма работает'):m.shutdown===Infinity?'Нет производства':fmt(m.shutdown));
  html+=stat('Постоянные затраты FC',fmt(m.fc));
  if(m.config.mode==='mc')html+='<div class="hint">TC — интеграл MC от нуля; других издержек нет.</div>';
  if(m.autoCap!=null)html+=stat('Предел убывающей MC',fmt(m.autoCap));
  if(m.tax.type!=='none'){const budget=(1-m.tax.alpha)*r.P*(r.Q||0)+m.tax.unit*(r.Q||0)+(r.Q>0||!m.avoidable?m.tax.lump:0);html+=stat('Налог фирме / субсидия (−)',Number.isFinite(budget)?fmt(budget):'Не ограничен');}
  if(STATE.lr?.note)html+='<div class="hint">'+STATE.lr.note+'</div>';
  if(!m.exact)html+='<div class="hint">Приближённый расчёт. Поиск на 0 ≤ Q ≤ '+fmt(m.searchTop)+'.</div>';
  if(r.Q===0)html+='<div class="hint">Фирма не производит.'+(m.zeroCost>0?' Невозвратные затраты остаются: '+fmt(m.zeroCost)+'.':' Издержек можно избежать.')+'</div>';
  setFinalFunctions([firmFinalRecord(m)]);box.innerHTML=html;
}
function drawFirmSupply(){
  const m=STATE.firmSupply;if(!m||m.error)return;
  const g=svg.append('g').attr('class','firm-supply').attr('clip-path','url(#plot-clip)'),line=d3.line().defined(x=>x&&Number.isFinite(x[0])&&Number.isFinite(x[1])).x(x=>sx(x[0])).y(x=>sy(x[1]));
  function draw(model,old=false){
    const color=COL.S,name=old?'S₀':'S',width=old?1.5:3.6;
    if(model.priceIndependent?.intervals?.length)return;
    const path=(pts,expr,domain)=>{const p=g.append('path').datum(pts).attr('fill','none').attr('stroke',color).attr('stroke-width',width).attr('d',line);if(old)p.attr('stroke-dasharray','6 4');if(expr)markExpr(p,expr,'P',domain,{axis:'y',name});else markNumeric(p,'численное предложение фирмы',name);return p;};
    if(model.exact){
      for(const row of model.schedule.rows){if(row.expr==='Infinity'||row.unattained)continue;const lo=Math.max(0,row.lo,CONFIG.Pmin),hi=Math.min(row.hi,CONFIG.Pmax);if(hi<=lo)continue;const e=math.compile(row.expr),pts=Array.from({length:101},(_,i)=>{const P=lo+(hi-lo)*i/100,Q=Number(e.evaluate({P}));return Q>=0?[Q,P]:null;});path(pts,row.expr,[lo,hi]);}
      for(const r of model.schedule.points){if(r.P<0||r.P>CONFIG.Pmax)continue;const intervals=r.intervals||[],outputs=(r.outputs||[]).filter(Number.isFinite);
        if(intervals.length)intervals.forEach(x=>{const lo=Math.max(0,x[0]),hi=Math.min(CONFIG.Qmax,x[1]);if(hi>lo)g.append('line').attr('x1',sx(lo)).attr('x2',sx(hi)).attr('y1',sy(r.P)).attr('y2',sy(r.P)).attr('stroke',color).attr('stroke-width',width).attr('stroke-dasharray',old?'6 4':null);});
        else if(outputs.length>1)g.append('line').attr('x1',sx(outputs[0])).attr('x2',sx(outputs.at(-1))).attr('y1',sy(r.P)).attr('y2',sy(r.P)).attr('stroke',color).attr('stroke-width',old?1:1.8).attr('stroke-dasharray','4 4').attr('data-supply-jump','1');
        if(!old&&(r.tie||r.P===model.shutdown))outputs.forEach(Q=>g.append('circle').attr('cx',sx(Q)).attr('cy',sy(r.P)).attr('r',4).attr('fill',color).attr('stroke',COL.halo).attr('stroke-width',1.2));
      }
    }else{let prev=null;const pts=[];for(let i=0;i<=200;i++){const P=Math.max(0,CONFIG.Pmin)+(CONFIG.Pmax-Math.max(0,CONFIG.Pmin))*i/200,r=model.at(P);if(prev!=null&&Math.abs(r.Q-prev)>CONFIG.Qmax*.1)pts.push(null);pts.push([r.Q,P]);prev=r.Q;}path(pts);}
    if(!old){const candidates=[.72,.55,.9,.35].map(k=>{const P=CONFIG.Pmax*k,r=model.at(P);return{P,Q:r.Q};}),point=candidates.find(x=>x.Q>0&&x.Q<CONFIG.Qmax*.92);if(point)renderLabelText(g.append('text').attr('x',sx(point.Q)+8).attr('y',sy(point.P)-10).attr('font-size',FS.large).attr('fill',COL.S).attr('paint-order','stroke').attr('stroke',COL.halo).attr('stroke-width',2.5),'S');}
  }
  if(m.before&&!m.before.error)draw(m.before,true);draw(m);
}
function firmCostExpressions(m){
  if(!m.exact)return{};const chunks=m.pieces.map(p=>'(Q <= '+(Number.isFinite(p.hi)?CalcNumber.expression(p.hi):'Infinity')+' ? ('+firmPolyExpr(p.c)+') : '),tc=chunks.join('')+'NaN'+')'.repeat(chunks.length),fc=CalcNumber.expression(m.fc);
  return{TC:tc,MC:m.config.mode==='mc'?m.config.expr:derivativeExpr(m.config.expr,'Q'),ATC:'('+tc+')/Q',AVC:'(('+tc+')-('+fc+'))/Q',AFC:'('+fc+')/Q',VC:'('+tc+')-('+fc+')',FC:fc};
}
function renderFirmSupplyControls(){
  const host=document.getElementById('firm-supply-controls');if(!host)return;
  if(!host.childElementCount){
    host.innerHTML='<label class="chk" id="firm-mc-only-row"><input type="checkbox" id="firm-mc-only">Только MC, других издержек нет</label><div id="firm-supply-options"><div class="field sc-nrow"><label>Не больше K единиц</label><input id="firm-capacity" type="text" data-plain="1" placeholder="Нет"></div><div class="seg sc-seg firm-seg" id="firm-period"><button type="button" class="seg-btn" data-value="sr">Краткосрочный (SR)</button><button type="button" class="seg-btn" data-value="lr">Долгосрочный (LR)</button></div><div id="firm-fixed-wrap"><div class="firm-fixed-label">Постоянные издержки</div><div class="seg sc-seg firm-seg" id="firm-fixed"><button type="button" class="seg-btn" data-value="sunk">Невозвратные</button><button type="button" class="seg-btn" data-value="quasi">Квазипостоянные</button></div></div><div class="firm-tax-card"><div class="sc-sec">Налог фирме</div><div class="seg sc-seg firm-seg" id="firm-tax-type"><button type="button" class="seg-btn" data-value="none">Нет</button><button type="button" class="seg-btn" data-value="unit">Потоварный</button><button type="button" class="seg-btn" data-value="revenue">% выручки</button><button type="button" class="seg-btn" data-value="lump">Аккордный</button></div><div id="firm-tax-options"><div class="seg sc-seg firm-seg" id="firm-tax-kind"><button type="button" class="seg-btn" data-value="tax">Налог</button><button type="button" class="seg-btn" data-value="subsidy">Субсидия</button></div><div class="field sc-nrow"><label id="firm-tax-label">Ставка</label><input id="firm-tax-rate" type="text" data-plain="1" value="10"></div></div></div></div>';
    const set=(key,value)=>{historyMark('Предложение фирмы');STATE.costsSupply={...(STATE.costsSupply||{}),[key]:value};redrawAll();};
    const taxSet=(key,value)=>set('tax',{type:'none',kind:'tax',rate:10,...(STATE.costsSupply?.tax||{}),[key]:value});
    for(const[id,key]of[['firm-period','period'],['firm-fixed','kind']])host.querySelectorAll('#'+id+' button').forEach(b=>b.addEventListener('click',()=>set(key,b.dataset.value)));
    for(const[id,key]of[['firm-tax-type','type'],['firm-tax-kind','kind']])host.querySelectorAll('#'+id+' button').forEach(b=>b.addEventListener('click',()=>taxSet(key,b.dataset.value)));
    document.getElementById('firm-capacity').addEventListener('change',e=>set('K',e.target.value));document.getElementById('firm-tax-rate').addEventListener('change',e=>taxSet('rate',e.target.value));
    document.getElementById('firm-mc-only').addEventListener('change',e=>{historyMark('Только предельные затраты');STATE.costsMCOnly=e.target.checked;redrawAll();});
  }
  const c=STATE.costsSupply||{},t=c.tax||{},curves=STATE.costsMode==='curves';
  document.getElementById('firm-mc-only-row').style.display=curves?'':'none';document.getElementById('firm-mc-only').checked=!!STATE.costsMCOnly;
  document.getElementById('firm-supply-options').style.display=!curves||STATE.costsMCOnly?'':'none';
  for(const id of['inp-catc','inp-cavc']){const f=document.getElementById(id)?.closest('.fc-card,.field');if(f)f.style.display=curves&&STATE.costsMCOnly?'none':'';}
  for(const[id,value]of[['firm-period',c.period||'sr'],['firm-fixed',c.kind||'sunk'],['firm-tax-type',t.type||'none'],['firm-tax-kind',t.kind||'tax']])host.querySelectorAll('#'+id+' button').forEach(b=>b.classList.toggle('active',b.dataset.value===value));
  document.getElementById('firm-fixed-wrap').style.display=c.period==='lr'?'none':'';document.getElementById('firm-tax-options').style.display=t.type&&t.type!=='none'?'':'none';
  for(const[id,value]of[['firm-capacity',c.K??''],['firm-tax-rate',t.rate??10]]){const e=document.getElementById(id);if(document.activeElement!==e)e.value=value;}
  document.getElementById('firm-tax-label').textContent=t.type==='revenue'?'Ставка, %':'Ставка';
}
