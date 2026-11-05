/* Глобальное сложение квадратичных затрат: перебор границ и стационарных
   разделов для каждой пары кусков, затем нижняя огибающая всех кандидатов.
   В отличие от равенства MC, сюда входят вогнутые TC, мощности и закрытие. */
function plantsPolynomial(expr) {
  const add=(a,b,k=1)=>a.map((v,i)=>v+k*b[i]);
  const mul=(a,b)=>{const c=Array(5).fill(0);a.forEach((x,i)=>b.forEach((y,j)=>c[i+j]+=x*y));return c.slice(3).some(x=>Math.abs(x)>1e-12)?null:c.slice(0,3);};
  function walk(n){
    if(n.isParenthesisNode)return walk(n.content);
    if(n.isSymbolNode&&['Q','q','x','L'].includes(n.name))return[0,1,0];
    if(!n.toString().match(/\b[QqxL]\b/)){try{const v=n.compile().evaluate(paramScope({}));return Number.isFinite(v)?[v,0,0]:null;}catch(e){return null;}}
    if(!n.isOperatorNode)return null;
    const xs=n.args.map(walk);if(xs.some(x=>!x))return null;
    if(n.fn==='unaryMinus')return xs[0].map(x=>-x);
    if(n.fn==='unaryPlus')return xs[0];
    if(n.fn==='add')return add(xs[0],xs[1]);
    if(n.fn==='subtract')return add(xs[0],xs[1],-1);
    if(n.fn==='multiply')return mul(xs[0],xs[1]);
    if(n.fn==='divide'&&xs[1][1]===0&&xs[1][2]===0&&xs[1][0]!==0)return xs[0].map(x=>x/xs[1][0]);
    if(n.fn==='pow'&&xs[1][1]===0&&xs[1][2]===0){if(xs[1][0]===0)return[1,0,0];if(xs[1][0]===1)return xs[0];if(xs[1][0]===2)return mul(xs[0],xs[0]);}
    return null;
  }
  try {const c=walk(math.parse(prepExpr(expr)));return c?{a:c[2],b:c[1],c:c[0]}:null;}catch(e){return null;}
}
const plantsValue=(s,q)=>(s.a*q+s.b)*q+s.c;
function plantsQuadraticRoots(a,b,c){
  if(a===0)return b===0?[]:[-c/b];
  let d=b*b-4*a*c;const de=1e-12*Math.max(1,b*b,Math.abs(4*a*c));if(d<-de)return[];if(Math.abs(d)<de)d=0;d=Math.sqrt(Math.max(0,d));
  const z=-.5*(b+Math.sign(b||1)*d);return z===0?[0]:[z/a,c/z];
}
function plantsCandidate(f,g,u,v){
  let lo=0,hi=Infinity;
  function ge(a,b){if(Math.abs(a)<1e-12)return b>=-1e-9;if(a>0)lo=Math.max(lo,-b/a);else hi=Math.min(hi,-b/a);return lo<=hi+1e-9;}
  if(!ge(u,v-f.lo)||!ge(1-u,-v-g.lo))return null;
  if(Number.isFinite(f.hi)&&!ge(-u,f.hi-v))return null;
  if(Number.isFinite(g.hi)&&!ge(u-1,g.hi+v))return null;
  if(hi<lo-1e-8||hi<0)return null;lo=Math.max(0,lo);if(hi<lo)hi=lo;
  return{a:f.a*u*u+g.a*(1-u)*(1-u),
    b:2*f.a*u*v+f.b*u-2*g.a*(1-u)*v+g.b*(1-u),
    c:f.a*v*v+f.b*v+f.c+g.a*v*v-g.b*v+g.c,lo,hi,
    alloc:f.alloc.map(([k,t])=>[k*u,k*v+t]).concat(g.alloc.map(([k,t])=>[k*(1-u),t-k*v]))};
}
function plantsEnvelope(cs){
  const cuts=[0];cs.forEach(s=>{cuts.push(s.lo);if(Number.isFinite(s.hi))cuts.push(s.hi);});
  for(let i=0;i<cs.length;i++)for(let j=0;j<i;j++){
    const a=cs[i],b=cs[j],lo=Math.max(a.lo,b.lo),hi=Math.min(a.hi,b.hi);
    if(lo>hi)continue;
    plantsQuadraticRoots(a.a-b.a,a.b-b.b,a.c-b.c).forEach(q=>{if(q>lo+1e-8&&q<hi-1e-8)cuts.push(q);});
  }
  cuts.sort((a,b)=>a-b);const xs=cuts.filter((x,i)=>!i||x-cuts[i-1]>1e-8*Math.max(1,Math.abs(x)));
  if(cs.some(s=>!Number.isFinite(s.hi)))xs.push(Infinity);
  const best=q=>{let out=null,v=Infinity;for(const s of cs){if(q<s.lo-1e-8||q>s.hi+1e-8)continue;const z=plantsValue(s,q);if(z<v-1e-9*Math.max(1,Math.abs(z))){v=z;out=s;}}return out;};
  const same=(a,b)=>a&&b&&Math.abs(a.a-b.a)<1e-10&&Math.abs(a.b-b.b)<1e-9&&Math.abs(a.c-b.c)<1e-8&&a.alloc.length===b.alloc.length&&a.alloc.every((x,i)=>x.every((v,j)=>Math.abs(v-b.alloc[i][j])<1e-9));
  const out=[];
  for(let i=0;i<xs.length-1;i++){
    const lo=xs[i],hi=xs[i+1],mid=Number.isFinite(hi)?(lo+hi)/2:lo+Math.max(1,Math.abs(lo));
    const s=best(mid);if(!s)continue;const last=out.at(-1);
    if(same(last,s)&&Math.abs(last.hi-lo)<1e-8)last.hi=hi;else out.push({...s,lo,hi});
  }
  // Изолированные точки (например, закрытый завод при Q=0) не теряются.
  for(const q of xs.filter(Number.isFinite)){
    const s=best(q);if(!s)continue;
    const covered=out.some(x=>q>=x.lo-1e-8&&q<=x.hi+1e-8&&Math.abs(plantsValue(x,q)-plantsValue(s,q))<1e-7);
    if(!covered)out.push({...s,lo:q,hi:q});
  }
  return out.sort((a,b)=>a.lo-b.lo||a.hi-b.hi);
}
function plantsConvolve(a,b){
  const candidates=[];
  for(const f of a)for(const g of b){
    const choices=[[0,f.lo],[1,-g.lo]];
    if(Number.isFinite(f.hi))choices.push([0,f.hi]);
    if(Number.isFinite(g.hi))choices.push([1,-g.hi]);
    if(f.a+g.a>1e-12)choices.push([g.a/(f.a+g.a),(g.b-f.b)/(2*(f.a+g.a))]);
    for(const [u,v]of choices){const s=plantsCandidate(f,g,u,v);if(s)candidates.push(s);}
  }
  return plantsEnvelope(candidates);
}
function plantsExactPieces(specs){
  let pieces=[{a:0,b:0,c:0,lo:0,hi:0,alloc:[]}];
  for(const p of specs){
    if(!p.poly)return null;
    const raw=[{...p.poly,lo:0,hi:p.K,alloc:[[1,0]]},
      {a:0,b:0,c:p.kind==='quasi'?0:p.poly.c,lo:0,hi:0,alloc:[[0,0]]}];
    pieces=plantsConvolve(pieces,raw);
  }
  return pieces;
}
function plantsExactAt(pieces,Q,specs){
  let best=null;
  for(const s of pieces){
    if(Q<s.lo-1e-8||Q>s.hi+1e-8)continue;
    const qs=s.alloc.map(([u,v],i)=>Math.min(specs[i].K,Math.max(0,u*Q+v)));
    if(Math.abs(qs.reduce((a,b)=>a+b,0)-Q)>1e-6)continue;
    const tc=qs.reduce((sum,q,i)=>sum+(q<1e-9&&specs[i].kind==='quasi'?0:plantsValue(specs[i].poly,q)),0);
    if(!best||tc<best.tcDirect-1e-8)best={Q,qs,q1:qs[0]||0,q2:qs[1]||0,tcDirect:tc,m:2*s.a*Q+s.b,piece:s};
  }
  if(best){
    const edges=pieces.filter(s=>s.hi>s.lo&&(Math.abs(Q-s.lo)<1e-8||Math.abs(Q-s.hi)<1e-8));
    const ms=edges.map(s=>2*s.a*Q+s.b);
    if(edges.some(s=>Math.abs(plantsValue(s,Q)-best.tcDirect)>1e-6)||ms.some(m=>Math.abs(m-best.m)>1e-7)){
      best.m=null;best.mcLimits=ms;
    }
  }
  return best;
}

function plantInputRows(){
  const n=STATE.plCount??2;
  return Array.from({length:n},(_,i)=>({expr:i===0?STATE.pl1:i===1?STATE.pl2:(STATE.plMore||[])[i-2]||'Q^2',
    K:(STATE.plCaps||[])[i]??null,kind:(STATE.plKinds||[])[i]||'sunk'}));
}
function setPlantInputRows(rows){
  STATE.plCount=rows.length;STATE.pl1=rows[0]?.expr||'Q^2';STATE.pl2=rows[1]?.expr||'2*Q^2';
  STATE.plMore=rows.slice(2).map(r=>r.expr);STATE.plCaps=rows.map(r=>r.K);STATE.plKinds=rows.map(r=>r.kind);
}
function addPlant(){historyMark('Добавить завод');const rows=plantInputRows();rows.push({expr:'Q^2',K:null,kind:'sunk'});setPlantInputRows(rows);renderPlantRows(true);redrawAll();}
function removePlant(i){const rows=plantInputRows();if(rows.length<2)return;historyMark('Удалить завод');rows.splice(i,1);setPlantInputRows(rows);renderPlantRows(true);redrawAll();}
function plantCost(p,q){if(q<-1e-8||q>p.K+1e-8)return Infinity;if(q<1e-9&&p.kind==='quasi')return 0;try{return p.compiled.evaluate(paramScope(axisScope(q)));}catch(e){return NaN;}}
function plantMarginal(p,q){if(p.poly)return 2*p.poly.a*q+p.poly.b;try{if(p.mc)return p.mc.evaluate(paramScope(axisScope(q)));}catch(e){}return finiteDerivative(x=>plantCost(p,x),q,0);}
function plantsCompile(rows){
  return rows.map((r,i)=>{
    const sp=splitCurveLhs(r.expr);if(sp.error)throw new Error(sp.error);
    if(sp.lhs&&lhsKey(sp.lhs)!=='TC')throw new Error('Завод '+(i+1)+': используйте TC = …');
    const raw=sp.rhs,result=compileFormula(raw);if(result.error)throw new Error('Завод '+(i+1)+': '+result.error);
    const K=r.K==null||r.K===''?Infinity:Number(r.K);if(!(K>=0))throw new Error('Мощность завода должна быть неотрицательной.');
    const p={...r,K,expr:raw,compiled:result.compiled,poly:plantsPolynomial(raw)},de=derivativeExpr(raw,'Q');
    p.mc=de?compileFormula(de).compiled:null;p.fc=plantCost({...p,kind:'sunk'},0);
    if(!Number.isFinite(p.fc))throw new Error('Завод '+(i+1)+': TC должна быть определена при Q = 0.');return p;
  });
}
/* Для произвольных формул — полный динамический перебор сеточных разделов,
   затем уточнение всех пар. Приближённый результат явно помечен; равенство MC
   не подменяет сравнение затрат. Мощности и закрытые заводы входят в перебор. */
function plantsGrid(specs,Q,N=400){
  if(Q===0)return{Q,qs:specs.map(()=>0),tcDirect:specs.reduce((s,p)=>s+plantCost(p,0),0),m:NaN,approx:true,step:0};
  const h=Q/N,choices=[],costs=specs.map(p=>Array.from({length:N+1},(_,k)=>k*h>p.K+h?Infinity:plantCost(p,Math.min(k*h,p.K))));
  let dp=Array(N+1).fill(Infinity);dp[0]=0;
  for(let i=0;i<specs.length;i++){
    const next=Array(N+1).fill(Infinity),take=Array(N+1).fill(0),max=Math.min(N,Math.ceil(specs[i].K/h));
    for(let q=0;q<=N;q++)for(let k=0;k<=Math.min(q,max);k++){
      const v=dp[q-k]+costs[i][k];if(v<next[q]){next[q]=v;take[q]=k;}
    }choices.push(take);dp=next;
  }
  if(!Number.isFinite(dp[N]))return null;
  const qs=Array(specs.length);let rem=N;
  for(let i=specs.length-1;i>=0;i--){const k=choices[i][rem];qs[i]=Math.min(k*h,specs[i].K);rem-=k;}
  let gap=Q-qs.reduce((a,b)=>a+b,0);
  for(let i=0;i<qs.length&&gap>1e-9;i++){const add=Math.min(gap,specs[i].K-qs[i]);qs[i]+=add;gap-=add;}
  if(gap>1e-6)return null;
  for(let turn=0;turn<5;turn++){
    let changed=false;
    for(let i=0;i<qs.length;i++)for(let j=0;j<i;j++){
      const sum=qs[i]+qs[j],lo=Math.max(0,sum-specs[j].K),hi=Math.min(sum,specs[i].K);
      const value=x=>plantCost(specs[i],x)+plantCost(specs[j],sum-x);
      const fn=x=>plantMarginal(specs[i],x)-plantMarginal(specs[j],sum-x);
      const cs=[lo,hi,qs[i],...monoRootsIn(fn,lo,hi,100)];let best=qs[i],v=value(best);
      for(const x of cs){const y=value(x);if(y<v-1e-9){v=y;best=x;}}
      if(Math.abs(best-qs[i])>1e-9)changed=true;qs[i]=best;qs[j]=sum-best;
    }if(!changed)break;
  }
  const active=qs.map((q,i)=>q>1e-7&&q<specs[i].K-1e-7?plantMarginal(specs[i],q):NaN).filter(Number.isFinite);
  return{Q,qs,tcDirect:qs.reduce((s,q,i)=>s+plantCost(specs[i],q),0),m:active.length?active[0]:NaN,approx:true,step:h};
}
function plantsIntegral(pieces,Q){
  let sum=0;for(const s of pieces){const a=Math.max(0,s.lo),b=Math.min(Q,s.hi);if(b>a)sum+=s.a*(b*b-a*a)+s.b*(b-a);}return sum;
}
function plantsAt(Q){
  const p=STATE.plants;if(!p||!Number.isFinite(Q)||Q<0||Q>p.capacity+1e-8)return null;
  if(p.cache.has(Q))return p.cache.get(Q);
  const r=p.pieces?plantsExactAt(p.pieces,Q,p.specs):plantsGrid(p.specs,Q);if(!r)return null;
  r.q1=r.qs[0]||0;r.q2=r.qs[1]||0;r.fc=p.fc;
  r.vc=p.pieces?plantsIntegral(p.pieces,Q):null;
  r.jumps=r.vc==null?null:r.tcDirect-p.fc-r.vc;
  if(!p.pieces)p.cache.set(Q,r);return r;
}
function recomputePlants(){
  const rows=plantInputRows(),sig=JSON.stringify([rows,STATE.params||{},Math.max(30,Number(STATE.plQ)||0)]);
  renderPlantRows();
  const qs=document.getElementById('pl-q-slider'),qi=document.getElementById('pl-q-input'),qv=document.getElementById('pl-q-val');
  if(qs)qs.value=STATE.plQ;if(qi&&document.activeElement!==qi)qi.value=STATE.plQ;if(qv)qv.textContent=fmt(STATE.plQ);
  if(STATE.plantsSig===sig&&STATE.plants)return;
  STATE.plants=null;STATE.plErr=null;STATE.plantsSig=sig;
  try{
    const specs=plantsCompile(rows),capacity=specs.reduce((s,p)=>s+p.K,0),pieces=plantsExactPieces(specs);
    const horizon=Math.min(capacity,Math.max(30,(Number(STATE.plQ)||0)*1.5));
    const p={specs,pieces,capacity,Qtot:horizon,qMax:horizon,cache:new Map(),fc:specs.reduce((s,p)=>s+(p.kind==='quasi'?0:p.fc),0),table:[]};
    STATE.plants=p;
    const qs=new Set([0,horizon,Math.min(horizon,STATE.plQ)]);
    for(let i=1;i<=(pieces?120:24);i++)qs.add(horizon*i/(pieces?120:24));
    if(pieces)pieces.forEach(s=>{if(s.lo<=horizon)qs.add(s.lo);if(s.hi<=horizon)qs.add(s.hi);});
    p.table=[...qs].sort((a,b)=>a-b).map(q=>plantsAt(q)).filter(Boolean);p.mMax=Math.max(1,...p.table.map(r=>r.m).filter(Number.isFinite));
    p.at=q=>plantsAt(q); // вычисляемое состояние не сериализуется в ссылку
    // Диапазон не следует за текущим Q: иначе одна позиция мыши каждый
    // кадр означает всё больший выпуск. Расширяем только для ввода вне шкалы.
    const sl=document.getElementById('pl-q-slider');
    if(sl&&!sl.dataset.boundsByHand&&!InputSnap.active&&!TaxMotion.held&&Number(STATE.plQ)>Number(sl.max))sl.max=Math.max(30,Math.ceil(horizon));
    const inp=document.getElementById('pl-q-input');if(inp){if(Number.isFinite(capacity))inp.max=capacity;else inp.removeAttribute('max');}
  }catch(e){STATE.plants=null;STATE.plErr=e.message;}
}
function plantsShownAt(q){const p=STATE.plants;if(!p)return null;if(p.pieces)return plantsAt(q);return{Q:q,tcDirect:interpY(p.table.map(r=>[r.Q,r.tcDirect]),q),m:interpY(p.table.map(r=>[r.Q,r.m]),q)};}
function plantsExpr(s,mc=false){
  const a=mc?0:s.a,b=mc?2*s.a:s.b,c=mc?s.b:s.c,terms=[];
  if(Math.abs(a)>1e-12)terms.push(CalcNumber.expression(a,{atomic:true})+'*Q^2');
  if(Math.abs(b)>1e-12)terms.push(CalcNumber.expression(b,{atomic:true})+'*Q');
  if(Math.abs(c)>1e-12||!terms.length)terms.push(CalcNumber.expression(c,{atomic:true}));
  const raw=terms.join('+');if(TaxMotion.drawing)return raw;try{return math.simplify(raw).toString();}catch(e){return raw;}
}
function redrawPlants(){
  recomputePlants();const p=STATE.plants,mc=STATE.plView==='mc';
  if(p){const top=Math.max(1,...p.table.map(r=>mc?r.m:r.tcDirect).filter(Number.isFinite));applyAutoRanges(padMax(p.Qtot||1),padMax(top));}
  makeScales();svg.selectAll('*').remove();addDefs();drawGrid();drawAxes('Q',mc?'MC':'TC');
  const error=document.getElementById('pl-error');if(error){error.textContent=STATE.plErr||'';error.style.display=STATE.plErr?'block':'none';}
  if(!p){updatePlantsPanel();return;}
  const g=svg.append('g').attr('clip-path','url(#plot-clip)'),colors=[COL.tax,COL.reg,COL.D,COL.S,COL.MR];
  const line=d3.line().defined(d=>d&&Number.isFinite(d[1])).x(d=>sx(d[0])).y(d=>sy(d[1]));
  p.specs.forEach((s,i)=>{
    const hi=Math.min(s.K,p.Qtot,CONFIG.Qmax),fn=q=>mc?plantMarginal(s,q):plantCost(s,q),points=Array.from({length:161},(_,k)=>{const q=hi*k/160;return[q,fn(q)];});
    const path=g.append('path').datum(points).attr('fill','none').attr('stroke',colors[i%colors.length]).attr('stroke-width',2).attr('stroke-dasharray','6 4').attr('d',line);
    const expr=mc?derivativeExpr(s.expr,'Q'):s.expr,name=(mc?'MC_':'TC_')+(i+1);
    if(s.kind==='quasi'&&!mc&&s.fc!==0){points[0]=null;path.datum(points).attr('d',line);}
    if(expr)markExpr(path,expr,'Q',[0,hi],{name});else markNumeric(path,'численная производная затрат',name);
    labelCurve(g,q=>q<=hi?fn(q):NaN,name,colors[i%colors.length],{key:'plant-'+i,from:.9-i%3*.15});
  });
  const totalName=mc?'MC':'TC',totalColor=mc?COL.MC:COL.D;
  if(p.pieces){
    p.pieces.filter(s=>s.hi>s.lo&&s.lo<Math.min(p.Qtot,CONFIG.Qmax)).forEach(s=>{
      const lo=s.lo,hi=Math.min(s.hi,p.Qtot,CONFIG.Qmax),expr=plantsExpr(s,mc),pts=Array.from({length:81},(_,i)=>{const q=lo+(hi-lo)*i/80;return[q,mc?2*s.a*q+s.b:plantsValue(s,q)];});
      markExpr(g.append('path').datum(pts).attr('fill','none').attr('stroke',totalColor).attr('stroke-width',2.8).attr('d',line),expr,'Q',[lo,hi],{name:totalName});
    });
  }else markNumeric(g.append('path').datum(p.table.map(r=>[r.Q,mc?r.m:r.tcDirect])).attr('fill','none').attr('stroke',totalColor).attr('stroke-width',2.8).attr('d',line),'приближённый минимум затрат по сеточному перебору',totalName);
  labelCurve(g,q=>{const r=plantsShownAt(q);return r?(mc?r.m:r.tcDirect):NaN;},totalName,totalColor,{key:'plant-total',from:.72});
  const r=plantsAt(Number(STATE.plQ));
  if(r){const v=mc?r.m:r.tcDirect;if(Number.isFinite(v)){
    const og=svg.append('g'),px=sx(r.Q),py=sy(v),ox=sx(0),oy=sy(0);
    og.append('line').attr('x1',ox).attr('y1',py).attr('x2',px).attr('y2',py).attr('stroke',COL.inkSoft).attr('stroke-dasharray','4 3');
    og.append('line').attr('x1',px).attr('y1',py).attr('x2',px).attr('y2',oy).attr('stroke',COL.inkSoft).attr('stroke-dasharray','4 3');
    og.append('circle').attr('cx',px).attr('cy',py).attr('r',4.5).attr('fill',COL.ink);axisValueX(og,px,oy,fmt(r.Q),'');axisValueY(og,ox,py,fmt(v),'');
    if(mc)r.qs.forEach((q,i)=>{if(q<=0)return;og.append('circle').attr('cx',sx(q)).attr('cy',py).attr('r',3).attr('fill',colors[i%colors.length]);haloText(og,sx(q),py-10-i%2*16,'Q_'+(i+1)+'='+fmt(q),'middle','auto');});
  }}
  updatePlantsPanel();
}
function plantsFinalRecord(p){
  const record={name:'Совокупные издержки',color:COL.D};
  if(!p.pieces)return{...record,note:'Построена численно: минимальная сумма затрат по допустимым разделам выпуска. Для этих функций явная формула не найдена.'};
  const rows=[];let expr='NaN';
  for(const s of p.pieces){
    const lo=plantsAt(s.lo),hi=Number.isFinite(s.hi)?plantsAt(s.hi):null;
    const closedLo=lo&&Math.abs(lo.tcDirect-plantsValue(s,s.lo))<1e-7,closedHi=hi&&Math.abs(hi.tcDirect-plantsValue(s,s.hi))<1e-7;
    const cond=s.lo===s.hi?'Q == '+CalcNumber.expression(s.lo):'Q '+(closedLo?'>=':'>')+' '+CalcNumber.expression(s.lo)+(Number.isFinite(s.hi)?' and Q '+(closedHi?'<=':'<')+' '+CalcNumber.expression(s.hi):'');
    rows.push({body:plantsExpr(s),cond});
  }
  for(let i=rows.length-1;i>=0;i--)expr='('+rows[i].cond+') ? ('+rows[i].body+') : ('+expr+')';
  if(rows.length===1&&p.pieces[0].hi===Infinity)expr=rows[0].body;
  return{...record,expr,lhs:'\\mathrm{TC}'};
}
function updatePlantsPanel(){
  if(TaxMotion.drawing)return;
  const box=document.getElementById('info-plants');if(!box)return;const p=STATE.plants;
  if(!p){setFinalFunctions([]);box.innerHTML='<div class="warn">'+ffEsc(STATE.plErr||'Введите функции затрат заводов.')+'</div>';return;}
  const r=plantsAt(Number(STATE.plQ));let html='';const stat=(name,value)=>'<div class="stat"><span>'+name+'</span><b>'+value+'</b></div>';
  if(r){
    html+=stat('Совокупный выпуск Q',fmt(r.Q));r.qs.slice(0,2).forEach((q,i)=>html+=stat('Завод '+(i+1)+': Q'+(i+1),fmt(q)));
    html+=stat('Совокупные предельные издержки MC',Number.isFinite(r.m)?fmt(r.m):'–');
    r.qs.slice(2).forEach((q,i)=>html+=stat('Завод '+(i+3)+': Q'+(i+3),fmt(q)));
    html+=stat('Совокупные издержки TC', (r.approx?'≈ ':'')+fmt(r.tcDirect));
    if(r.fc)html+=stat('Невозвратные постоянные издержки',fmt(r.fc));
    if(r.vc!=null)html+=stat('∫ MC(q)dq (сверка)',fmt(r.vc));
    const naive=p.specs.reduce((sum,plant)=>sum+plantCost(plant,r.Q),0);
    if(p.specs.length>1&&Number.isFinite(naive))html+=stat(p.specs.length===2?'«Сумма в лоб» TC₁(Q)+TC₂(Q)':'«Сумма в лоб» всех TCᵢ(Q)',fmt(naive));
    if(r.jumps!=null&&Math.abs(r.jumps)>1e-7)html+=stat('Пуски и скачки затрат',fmt(r.jumps));
    if(r.mcLimits)html+='<div class="hint">В этой точке TC имеет излом или скачок: единственное значение MC не определено.</div>';
    const limits=r.qs.map((q,i)=>q<1e-8?'Завод '+(i+1)+' не работает':Math.abs(q-p.specs[i].K)<1e-8?'Завод '+(i+1)+' достиг мощности':null).filter(Boolean);
    if(limits.length)html+='<div class="hint">'+limits.join('. ')+'.</div>';
    if(r.approx)html+='<div class="hint">Численный перебор с шагом '+fmt(r.step)+' и уточнением раздела. Результат приближённый.</div>';
  }else html+='<div class="warn">'+(Number(STATE.plQ)>p.capacity?'Выпуск больше суммарной мощности заводов ('+fmt(p.capacity)+'). Уменьшите Q или увеличьте мощность.':'Не удалось найти допустимый раздел выпуска. Проверьте области определения формул и мощности.')+'</div>';
  setFinalFunctions([plantsFinalRecord(p)]);
  html+='<div class="hint">TC – минимум суммы затрат при делении общего выпуска. Равенство MC относится только к работающим заводам, которые не достигли мощности. При квазипостоянных затратах сравнивается также закрытие завода; скачки TC считаются отдельно от интеграла MC.</div>';
  box.innerHTML=html;
}
function renderPlantRows(force=false){
  const host=document.getElementById('plant-rows');if(!host)return;const rows=plantInputRows();
  rows.forEach((r,i)=>{
    const id='inp-pl'+(i+1);let input=document.getElementById(id),field=input?.closest('.field');
    if(!input){field=document.createElement('div');field.className='field';input=document.createElement('input');input.type='text';input.id=id;input.autocomplete='off';field.appendChild(input);host.appendChild(field);input.value=r.expr;
      equipFormulaField(id,'TC');liveFormula([input],()=>{const rs=plantInputRows();if(!input.isConnected||!rs[i])return;rs[i].expr=input.value;setPlantInputRows(rs);redrawAll();});}
    field.style.display='';LHS_FIELD_IDS.add(id);
    if(force&&input.value!==r.expr)setFormulaFieldQuiet(input,r.expr);
    if(!field._scCard)wrapFieldInCard(field,{input:id,sym:'\\mathrm{TC}_{'+(i+1)+'}',name:'Завод '+(i+1),prefix:()=>splitCurveLhs(input.value).lhs?'':'\\mathrm{TC}_{'+(i+1)+'} =',col:['tax','reg','D','S','MR'][i%5]});
    if(!field._plantOptions){
      const options=document.createElement('div');options.className='plant-options';options.innerHTML='<label><span>Не больше K</span><input type="number" min="0" step="any" placeholder="без предела" aria-label="Мощность завода '+(i+1)+'"></label><div class="hint">Постоянные издержки</div><div class="seg"><button type="button" class="seg-btn" data-kind="sunk">Невозвратные</button><button type="button" class="seg-btn" data-kind="quasi">Квази&shy;постоянные</button></div><button type="button" class="btn btn-ghost plant-remove">Удалить завод</button>';
      field.appendChild(options);field._plantOptions=options;
      options.querySelector('input').addEventListener('change',e=>{const v=e.target.value===''?null:Number(e.target.value);if(v!=null&&(!(v>=0)||!Number.isFinite(v))){e.target.setCustomValidity('Введите неотрицательную мощность.');return;}e.target.setCustomValidity('');historyMark('Мощность завода');const rs=plantInputRows();rs[i].K=v;setPlantInputRows(rs);redrawAll();});
      options.querySelectorAll('[data-kind]').forEach(b=>b.addEventListener('click',()=>{historyMark('Постоянные издержки');const rs=plantInputRows();rs[i].kind=b.dataset.kind;setPlantInputRows(rs);redrawAll();}));
      options.querySelector('.plant-remove').addEventListener('click',()=>removePlant(i));
    }
    const options=field._plantOptions,k=options.querySelector('input');if(document.activeElement!==k)k.value=r.K??'';
    options.querySelectorAll('[data-kind]').forEach(b=>{const on=b.dataset.kind===r.kind;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
    options.querySelector('.plant-remove').disabled=rows.length===1;
    if(field._scCard)field._scCard.o.prefix=()=>splitCurveLhs(input.value).lhs?'':'\\mathrm{TC}_{'+(i+1)+'} =';
    paintCard(field);
  });
  host.querySelectorAll('input[id^="inp-pl"]').forEach(input=>{if(Number(input.id.slice(6))>rows.length){if(Number(input.id.slice(6))<=2)input.closest('.field').style.display='none';else input.closest('.field').remove();}});
  for(let i=FORMULA_FIELDS.length-1;i>=0;i--)if(!FORMULA_FIELDS[i].isConnected)FORMULA_FIELDS.splice(i,1);
}
