// Неравные группы и союз стран. Доходы сортируются на человека; численность сохраняется.
function ineqNumber(v) {
  try { return CalcNumber.parse(String(v).replace(/%\s*$/, '').trim())?.value??NaN; } catch(e) { return NaN; }
}
function ineqShares(values, label) {
  const ns=values.map(ineqNumber);if(ns.some(v=>!Number.isFinite(v)||v<0))throw Error(label+': нужны неотрицательные числа.');
  const anyPercent=values.some(v=>/%/.test(String(v))),sum=ns.reduce((a,b)=>a+b,0);
  const fractions=!anyPercent&&Math.abs(sum-1)<1e-8;
  const out=ns.map((v,i)=>/%/.test(String(values[i]))?v/100:fractions?v:(anyPercent&&v<=1?v:v/100));
  const total=out.reduce((a,b)=>a+b,0);if(Math.abs(total-1)>1e-8)throw Error('Сумма долей '+label+' должна быть 100% (или 1). Сейчас '+CalcNumber.format(total*100,{percent:true})+'.');
  return out;
}
function ineqWeightedPoints(pops,shares) {
  const pts=[[0,0]];let p=0,s=0;for(let i=0;i<pops.length;i++){p+=pops[i];s+=shares[i];pts.push([p,s]);}pts[pts.length-1]=[1,1];return pts;
}
function ineqSimplify(expr){try{return math.simplify(math.rationalize(expr)).toString();}catch(e){return math.simplify(expr).toString();}}
function ineqPieceExpr(pieces) {
  let expr='NaN';for(let i=pieces.length-1;i>=0;i--)expr='(p '+(i?'>'+CalcNumber.expression(pieces[i].lo):'>=0')+' and p <= '+CalcNumber.expression(pieces[i].hi)+') ? ('+pieces[i].expr+') : ('+expr+')';
  return pieces.length===1?pieces[0].expr:expr;
}
function ineqLinePieces(pts) {
  return pts.slice(1).map((b,i)=>{const a=pts[i],m=(b[1]-a[1])/(b[0]-a[0]),c=a[1]-m*a[0];return{lo:a[0],hi:b[0],expr:ineqSimplify(CalcNumber.expression(m)+'*p+('+CalcNumber.expression(c)+')')};});
}
function ineqIntegrate(f) {
  let last=null;for(let n=16;n<=16384;n*=2){let sum=f(0)+f(1);for(let i=1;i<n;i++)sum+=(i%2?4:2)*f(i/n);const v=sum/(3*n);if(last!=null&&Math.abs(v-last)<1e-11)return v;last=v;}return last;
}
function ineqStatsFor(r) {
  const s=inequalityStats(r.pts);if(r.area!=null)s.gini=1-2*r.area;
  if(r.continuous&&!r.approx){let lo=0,hi=1;for(let i=0;i<80;i++){const a=lo+(hi-lo)/3,b=hi-(hi-lo)/3;if(a-r.at(a)<b-r.at(b))lo=a;else hi=b;}s.hooverP=(lo+hi)/2;s.hoover=s.hooverP-r.at(s.hooverP);}
  const boundary=p=>r.continuous||r.pts.some(x=>Math.abs(x[0]-p)<1e-9);
  s.decileAvailable=boundary(.1)&&boundary(.9);s.quintileAvailable=boundary(.2)&&boundary(.8);
  const ratio=p=>{const lo=r.at(p),hi=1-r.at(1-p);return lo>1e-12?hi/lo:hi>1e-12?Infinity:null;};
  s.decile=s.funds=s.decileAvailable?ratio(.1):null;s.quintile=s.quintileAvailable?ratio(.2):null;
  return s;
}
function ineqHasAlpha(expr=STATE.ineqFormula) {return /(?:\balpha\b|α)/.test(String(expr));}
function ineqAlphaActive(){return (STATE.ineqInput==='formula'&&ineqHasAlpha())||(STATE.ineqCountryB?.input==='formula'&&ineqHasAlpha(STATE.ineqCountryB.formula));}
function ineqFormulaExpr(expr) {
  const raw=prepExpr(expr),scope=scopeFor(raw,{alpha:STATE.ineqAlpha,α:STATE.ineqAlpha});
  return math.parse(raw).transform(n=>n.isSymbolNode?(n.name==='x'?new math.SymbolNode('p'):n.name!=='p'&&typeof scope[n.name]==='number'?new math.ConstantNode(scope[n.name]):n):n).toString();
}
function ineqDistribution(c) {
  try {
    if(c.input==='formula') {
      const expr=ineqFormulaExpr(c.formula||'p^2'),compiled=math.parse(expr).compile(),at=p=>Number(compiled.evaluate({p}));
      const pts=[];for(let i=0;i<=100;i++)pts.push([i/100,at(i/100)]);
      if(pts.some(q=>!Number.isFinite(q[1])))throw Error('Функция должна вычисляться на всём [0,1].');
      if(Math.abs(at(0))>1e-8||Math.abs(at(1)-1)>1e-8)throw Error('Нужно L(0)=0 и L(1)=1.');
      let prev=at(0),slope=-Infinity;
      for(let i=1;i<=1000;i++){const y=at(i/1000),m=(y-prev)*1000;if(!Number.isFinite(y)||m< -1e-7||m<slope-1e-6)throw Error('Кривая Лоренца должна быть неубывающей и выпуклой.');prev=y;slope=m;}
      let derivative;try{derivative=math.derivative(expr,'p').compile();}catch(e){}
      const quantile=p=>{let v;try{v=derivative?.evaluate({p});}catch(e){}if(Number.isFinite(v))return Math.max(0,v);const lo=Math.max(0,p-1e-7),hi=Math.min(1,p+1e-7);return(at(hi)-at(lo))/(hi-lo);};
      const r={pts,at,expr,pieces:[{lo:0,hi:1,expr}],continuous:true,area:ineqIntegrate(at),min:quantile(0),max:quantile(1),quantile};r.stats=ineqStatsFor(r);return r;
    }
    let pops,shares,sorted,raw;
    if(c.input==='incomes') {
      const xs=parseNumberList(c.incomes);if(xs.length<2||xs.some(v=>v<0||!Number.isFinite(v)))throw Error('Введите хотя бы два неотрицательных дохода.');
      const total=xs.reduce((a,b)=>a+b,0);if(!(total>0))throw Error('Суммарный доход должен быть положительным.');pops=xs.map(()=>1/xs.length);shares=xs.map(x=>x/total);raw=xs;
    }else{
      const groups=c.groups||[8,12,16,24,40],ps=c.pops||groups.map(()=>100/groups.length);if(!groups.length||ps.length!==groups.length)throw Error('У каждой группы нужны численность и доход.');raw=groups;
      if(c.groupMode==='counts') {
        const counts=ps.map(ineqNumber),means=groups.map(ineqNumber);if(counts.some(v=>!Number.isFinite(v)||!(v>0))||means.some(v=>!Number.isFinite(v)||v<0))throw Error('Численность должна быть положительной, средний доход — неотрицательным.');
        const N=counts.reduce((a,b)=>a+b,0),I=counts.reduce((s,n,i)=>s+n*means[i],0);if(!(I>0))throw Error('Суммарный доход должен быть положительным.');pops=counts.map(n=>n/N);shares=counts.map((n,i)=>n*means[i]/I);
      }else {pops=ineqShares(ps,'населения');shares=ineqShares(groups,'дохода');if(pops.some(v=>v<=0))throw Error('Доля населения каждой группы должна быть положительной.');}
    }
    sorted=pops.map((p,i)=>({p,s:shares[i],i})).sort((a,b)=>a.s/a.p-b.s/b.p||a.i-b.i);
    const reordered=sorted.some((x,i)=>x.i!==i);pops=sorted.map(x=>x.p);shares=sorted.map(x=>x.s);const pts=ineqWeightedPoints(pops,shares),at=p=>lorenzAt(pts,p),pieces=ineqLinePieces(pts);
    const r={pts,pops,shares,at,pieces,expr:ineqPieceExpr(pieces),reordered,sorted:sorted.map(x=>x.i),raw,min:shares[0]/pops[0],max:shares.at(-1)/pops.at(-1),continuous:false};r.stats=ineqStatsFor(r);return r;
  }catch(e){return{error:e.message};}
}
function ineqUnion(ds,populations,incomes) {
  if(ds.some(d=>d.error))return{error:ds.map((d,i)=>d.error?'Страна '+(i?'B':'A')+': '+d.error:'').filter(Boolean).join(' ')};
  const ns=populations.map(ineqNumber),ys=incomes.map(ineqNumber);if(ns.some(x=>!Number.isFinite(x)||x<=0)||ys.some(x=>!Number.isFinite(x)||x<=0))return{error:'Население и суммарный доход каждой страны должны быть положительными.'};
  const nt=ns.reduce((a,b)=>a+b,0),yt=ys.reduce((a,b)=>a+b,0),pw=ns.map(x=>x/nt),iw=ys.map(x=>x/yt);
  const assemble=bins=>{
    bins.sort((a,b)=>a.s/a.p-b.s/b.p);const pts=ineqWeightedPoints(bins.map(x=>x.p),bins.map(x=>x.s)),at=p=>lorenzAt(pts,p);return{pts,at};
  };
  if(ds.every(d=>d.pops)) {
    const bins=ds.flatMap((d,j)=>d.pops.map((p,i)=>({p:p*pw[j],s:d.shares[i]*iw[j]}))),r=assemble(bins);r.pops=bins.map(x=>x.p);r.shares=bins.map(x=>x.s);r.pieces=ineqLinePieces(r.pts);r.expr=ineqPieceExpr(r.pieces);r.stats=ineqStatsFor(r);return r;
  }
  const order=[0,1].sort((a,b)=>ds[a].min*iw[a]/pw[a]-ds[b].min*iw[b]/pw[b]),[a,b]=order;
  if(ds[a].max*iw[a]/pw[a]<=ds[b].min*iw[b]/pw[b]+1e-10) {
    let pc=0,ic=0,area=0;const pieces=[],pts=[[0,0]];
    for(const j of order){const d=ds[j],w=pw[j],v=iw[j];
      for(const s of d.pieces){const sub=math.parse('(p-('+CalcNumber.expression(pc)+'))/('+CalcNumber.expression(w)+')');const body=math.parse(s.expr).transform(n=>n.isSymbolNode&&n.name==='p'?sub:n).toString();const expr=ineqSimplify(CalcNumber.expression(ic)+'+('+CalcNumber.expression(v)+')*('+body+')');pieces.push({lo:pc+w*s.lo,hi:pc+w*s.hi,expr});}
      for(const q of d.pts.slice(1))pts.push([pc+w*q[0],ic+v*q[1]]);area+=w*ic+w*v*(d.area??lorenzAreaUnder(d.pts));pc+=w;ic+=v;
    }
    pts[pts.length-1]=[1,1];const compiled=pieces.map(s=>math.parse(s.expr).compile()),at=p=>{const i=pieces.findIndex(s=>p<=s.hi+1e-12);return Number(compiled[i<0?pieces.length-1:i].evaluate({p}));};
    const r={pts,at,pieces,expr:ineqPieceExpr(pieces),area,continuous:ds.every(d=>d.continuous)};r.stats=ineqStatsFor(r);return r;
  }
  // Пересекающиеся диапазоны: объединяем всё более мелкие квантили, сохраняя
  // в каждом точную массу дохода L(b)−L(a). Сходимость Джини проверяется явно.
  let previous=null,r;
  for(let n=512;n<=16384;n*=2){
    const bins=ds.flatMap((d,j)=>d.pops?d.pops.map((p,i)=>({p:p*pw[j],s:d.shares[i]*iw[j]})):Array.from({length:n},(_,i)=>({p:pw[j]/n,s:iw[j]*(d.at((i+1)/n)-d.at(i/n))})));
    r=assemble(bins);r.continuous=ds.every(d=>d.continuous);r.stats=ineqStatsFor(r);r.approx=true;r.resolution=n;r.errorBound=previous==null?null:Math.abs(previous-r.stats.gini);
    if(previous!=null&&r.errorBound<1e-8)break;previous=r.stats.gini;
  }
  return r;
}
function ineqFirstConfig(){return{input:STATE.ineqInput,groups:STATE.ineqGroups,pops:STATE.ineqPops,groupMode:STATE.ineqGroupMode,incomes:STATE.ineqIncomes,formula:STATE.ineqFormula};}
let _ineqResultCache=null;
function ineqCalculate() {
  const a=ineqFirstConfig(),b=STATE.ineqCountryB||null,weights=[STATE.ineqPopulation??1,STATE.ineqTotalIncome??1],key=JSON.stringify([a,b,weights,STATE.ineqAlpha,STATE.params]);
  if(_ineqResultCache?.key===key)return _ineqResultCache;
  const first=ineqDistribution(a),countries=b?[first,ineqDistribution(b)]:null,result=b?ineqUnion(countries,[weights[0],b.population??1],[weights[1],b.totalIncome??1]):first;
  _ineqResultCache={key,first,countries,result};return _ineqResultCache;
}

// Первую страну продолжают хранить старые поля: прежние ссылки открываются.
function ineqGroupConfig(second){return second?STATE.ineqCountryB:ineqFirstConfig();}
function ineqWriteGroups(second,c){if(second)Object.assign(STATE.ineqCountryB,c);else{STATE.ineqGroups=c.groups;STATE.ineqPops=c.pops;STATE.ineqGroupMode=c.groupMode||'shares';}}
function ineqSetGroupMode(second,mode){
  const c=ineqGroupConfig(second),r=ineqDistribution({...c,input:'groups'});historyMark('Способ ввода групп');
  if(!r.error)ineqWriteGroups(second,{groupMode:mode,pops:r.pops.map(x=>x*100),groups:mode==='counts'?r.shares.map((s,i)=>s/r.pops[i]):r.shares.map(s=>s*100)});
  else ineqWriteGroups(second,{...c,groupMode:mode});
  ineqMasterDetach();renderIneqGroupsTable();redrawAll();
}
function ineqAddGroup(second){
  const c=ineqGroupConfig(second),g=c.groups.slice(),ps=(c.pops||g.map(()=>100/g.length)).slice(),i=g.length-1;
  historyMark('Добавить группу');const half=ineqNumber(ps[i])/2;ps[i]=half;ps.push(half);
  if(c.groupMode==='counts')g.push(g[i]);else{const h=ineqNumber(g[i])/2;g[i]=h;g.push(h);}
  ineqWriteGroups(second,{groups:g,pops:ps,groupMode:c.groupMode});ineqMasterDetach();renderIneqGroupsTable();redrawAll();
}
function ineqRemoveGroup(second,i){const c=ineqGroupConfig(second);if(c.groups.length<2)return;historyMark('Удалить группу');ineqWriteGroups(second,{...c,groups:c.groups.filter((_,j)=>j!==i),pops:(c.pops||c.groups.map(()=>100/c.groups.length)).filter((_,j)=>j!==i)});ineqMasterDetach();renderIneqGroupsTable();redrawAll();}
function ineqRenderRows(box,second){
  if(!box)return;const c=ineqGroupConfig(second);if(!c)return;const groups=c.groups||[25,75],pops=c.pops||groups.map(()=>100/groups.length),counts=c.groupMode==='counts';
  const sig=groups.length+'|'+counts;
  if(box._ineqSig!==sig){box._ineqSig=sig;box.innerHTML='';groups.forEach((v,i)=>{
    const row=document.createElement('div');row.className='ineq-grow';row.innerHTML='<span class="ineq-group-title">Группа '+(i+1)+'</span><button type="button" class="btn btn-ghost ineq-remove" aria-label="Удалить группу '+(i+1)+'">×</button><label><span>'+(counts?'Численность':'Население, %')+'</span><input type="text" data-plain="1" inputmode="decimal" autocomplete="off" data-field="pop" aria-label="'+(counts?'Численность':'Доля населения')+' группы '+(i+1)+'"></label><label><span>'+(counts?'Средний доход':'Доход, %')+'</span><input type="text" data-plain="1" inputmode="decimal" autocomplete="off" data-field="income" aria-label="'+(counts?'Средний доход':'Доля дохода')+' группы '+(i+1)+'"></label>';
    row.querySelectorAll('input').forEach(inp=>inp.addEventListener('change',()=>{if(!inp.isConnected)return;const cc=ineqGroupConfig(second),gs=cc.groups.slice(),pp=(cc.pops||gs.map(()=>100/gs.length)).slice();historyMark('Изменить группу');if(inp.dataset.field==='pop')pp[i]=inp.value;else gs[i]=inp.value;ineqWriteGroups(second,{groups:gs,pops:pp,groupMode:cc.groupMode});ineqMasterDetach();redrawAll();}));
    row.querySelector('button').addEventListener('click',()=>ineqRemoveGroup(second,i));box.appendChild(row);
  });}
  if(!second){const sel=document.getElementById('ineq-ngroups');if(sel)sel.value=(!counts&&pops.every(x=>Math.abs(ineqNumber(x)-ineqNumber(pops[0]))<1e-9))?String(groups.length):'';}
  box.querySelectorAll('.ineq-grow').forEach((row,i)=>{for(const[key,value]of[['pop',pops[i]],['income',groups[i]]]){const e=row.querySelector('[data-field="'+key+'"]');if(document.activeElement!==e)e.value=value;}row.querySelector('button').disabled=groups.length===1;});
  const mode=document.getElementById(second?'ineq-b-group-mode':'ineq-group-mode');if(mode){if(!mode.childElementCount){for(const[v,label]of[['shares','Доли'],['counts','Численность и доход']]){const b=document.createElement('button');b.type='button';b.className='seg-btn';b.dataset.mode=v;b.textContent=label;b.addEventListener('click',()=>ineqSetGroupMode(second,v));mode.appendChild(b);}}mode.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.mode===(counts?'counts':'shares')));}
}
function ineqAddCountry(){
  if(STATE.ineqCountryB)return;historyMark('Добавить страну');STATE.ineqPopulation=1;STATE.ineqTotalIncome=1;
  STATE.ineqCountryB={input:'groups',groups:[25,75],pops:[50,50],groupMode:'shares',formula:'p^2',population:1,totalIncome:1};renderIneqCountryControls(true);redrawAll();
}
function renderIneqCountryControls(force=false){
  const alpha=document.getElementById('ineq-alpha-field');if(alpha)alpha.style.display=ineqAlphaActive()?'':'none';
  const host=document.getElementById('ineq-countries'),add=document.getElementById('ineq-add-country');if(!host)return;
  const c=STATE.ineqCountryB;if(add)add.style.display=c?'none':'';
  if(!c){if(host.childElementCount){host.innerHTML='';for(let i=FORMULA_FIELDS.length-1;i>=0;i--)if(!FORMULA_FIELDS[i].isConnected)FORMULA_FIELDS.splice(i,1);}return;}
  if(!host.childElementCount){
    host.innerHTML='<div class="ineq-country"><b>Страна A</b><div class="ineq-weights"><label><span>Население</span><input id="ineq-a-pop" type="text" data-plain="1" inputmode="decimal"></label><label><span>Общий доход</span><input id="ineq-a-income" type="text" data-plain="1" inputmode="decimal"></label></div></div><div class="ineq-country"><div class="ineq-country-head"><b>Страна B</b><button type="button" class="btn btn-ghost" id="ineq-remove-country">Удалить страну</button></div><div class="ineq-weights"><label><span>Население</span><input id="ineq-b-pop" type="text" data-plain="1" inputmode="decimal"></label><label><span>Общий доход</span><input id="ineq-b-income" type="text" data-plain="1" inputmode="decimal"></label></div><div class="seg" id="ineq-b-input"><button type="button" class="seg-btn" data-input="groups">Группы</button><button type="button" class="seg-btn" data-input="formula">Формула</button></div><div id="ineq-b-groups-pane"><div class="seg ineq-group-mode" id="ineq-b-group-mode"></div><div id="ineq-b-groups-table"></div><button type="button" class="btn-sm" id="ineq-b-add-group">+ группа</button></div><div class="field" id="ineq-b-formula-field"><label>Кривая Лоренца страны B</label><input type="text" id="ineq-b-formula" autocomplete="off"></div></div><div class="hint">Можно вводить относительные величины: население 4 и 1 означает 4 : 1; общий доход 1 и 1 — равные доходы стран.</div>';
    for(const[id,second,key]of[['ineq-a-pop',false,'population'],['ineq-a-income',false,'totalIncome'],['ineq-b-pop',true,'population'],['ineq-b-income',true,'totalIncome']])document.getElementById(id).addEventListener('change',e=>{historyMark('Вес страны');if(second)STATE.ineqCountryB[key]=e.target.value;else STATE[key==='population'?'ineqPopulation':'ineqTotalIncome']=e.target.value;redrawAll();});
    document.getElementById('ineq-remove-country').addEventListener('click',()=>{historyMark('Удалить страну');delete STATE.ineqCountryB;renderIneqCountryControls(true);redrawAll();});
    document.querySelectorAll('#ineq-b-input button').forEach(b=>b.addEventListener('click',()=>{historyMark('Ввод страны B');STATE.ineqCountryB.input=b.dataset.input;renderIneqCountryControls(true);redrawAll();}));
    document.getElementById('ineq-b-add-group').addEventListener('click',()=>ineqAddGroup(true));
    const input=document.getElementById('ineq-b-formula');input.value=c.formula||'p^2';equipFormulaField(input.id,'MATHF');liveFormula([input],()=>{if(STATE.ineqCountryB){STATE.ineqCountryB.formula=input.value;redrawAll();}});
    wrapFieldInCard(input.closest('.field'),{input:input.id,sym:'L_B',name:'Кривая Лоренца страны B',prefix:'L_B(p) =',col:'S'});
  }
  for(const[id,v]of[['ineq-a-pop',STATE.ineqPopulation??1],['ineq-a-income',STATE.ineqTotalIncome??1],['ineq-b-pop',c.population??1],['ineq-b-income',c.totalIncome??1]]){const e=document.getElementById(id);if(document.activeElement!==e)e.value=v;}
  document.querySelectorAll('#ineq-b-input button').forEach(b=>b.classList.toggle('active',b.dataset.input===c.input));
  document.getElementById('ineq-b-groups-pane').style.display=c.input==='groups'?'':'none';document.getElementById('ineq-b-formula-field').style.display=c.input==='formula'?'':'none';
  ineqRenderRows(document.getElementById('ineq-b-groups-table'),true);
  if(force){const input=document.getElementById('ineq-b-formula');if(input.value!==c.formula)setFormulaFieldQuiet(input,c.formula||'p^2');}
}
