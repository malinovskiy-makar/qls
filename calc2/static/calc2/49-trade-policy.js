/* Три канала: внутренние сделки, ввоз, вывоз. Цены в клине —
   цена покупателя = A·цена продавца + B. */
function tradeChannels(raw={},Pw=0){
  const p={kind:'none',target:'trade',form:'unit',rate:0,...raw};
  const rate=CalcNumber.parse(String(p.rate))?.value;
  if(p.kind!=='none'&&p.kind!=='quota'&&(!(rate>=0)||!Number.isFinite(rate)))return{error:'Ставка должна быть неотрицательной.'};
  const sign=p.kind==='subsidy'?-1:1,r=sign*(rate||0),one=()=>({A:1,B:0});
  let w=one();
  if(p.kind!=='none'&&p.kind!=='quota'){
    if(p.form==='unit')w.B=r;
    else if(p.target==='trade')w.B=r*Pw/100;
    else if(p.form==='seller')w.A=1+r/100;
    else if(p.form==='buyer')w.A=1/(1-r/100);
    else return{error:'Неизвестная форма вмешательства.'};
    if(!(w.A>0)||!Number.isFinite(w.A))return{error:'При этой процентной ставке связь цен вырождается. Используйте ставку меньше 100 %.'};
  }
  const domestic=one(),imports=one(),exports=one();
  if(['internal','consumer','producer'].includes(p.target))Object.assign(domestic,w);
  if(['trade','consumer'].includes(p.target))Object.assign(imports,w);
  if(['trade','producer'].includes(p.target))Object.assign(exports,w);
  return{domestic,imports,exports,policy:p};
}
const tradeBuyer=(w,p)=>w.A*p+w.B;
const tradeSeller=(w,p)=>(p-w.B)/w.A;
function tradeCurve(expr,demand){
  const built=buildAnyCurve(expr),curve=makeCurve(expr);if(built.error||curve.error)return{error:built.error||curve.error};
  if(curve.linear&&(demand?curve.linear.a>=0:curve.linear.a<=0))return{error:demand?'Спрос должен убывать.':'Предложение должно возрастать.'};
  const at=P=>{
    if(built.form==='QP'){try{return Math.max(0,built.srcCompiled.evaluate(paramScope({P,p:P})));}catch(e){return NaN;}}
    if(curve.linear)return Math.max(0,(P-curve.linear.b)/curve.linear.a);
    const f=q=>evalCurve(curve,q)-P,edge=f(0);
    if(demand?edge<=0:edge>=0)return 0;
    let hi=1;for(let i=0;i<80&&(demand?f(hi)>0:f(hi)<0);i++)hi*=2;
    if(!Number.isFinite(f(hi))||!(demand?f(hi)<=0:f(hi)>=0))return NaN;
    return firmMarketBisect(f,0,hi);
  };
  let previous=demand?Infinity:-Infinity;
  for(const P of[0,.1,1,10,100,1000,1e5]){const q=at(P);if(Number.isFinite(q)){if(demand?q>previous+1e-7:q<previous-1e-7)return{error:'Кривая должна быть монотонной по цене.'};previous=q;}}
  return{curve,at};
}
function tradeAutark(D,S,w){
  const excess=p=>D.at(tradeBuyer(w,p))-S.at(p);let hi=1;
  for(let i=0;i<100&&excess(hi)>0;i++)hi*=2;
  if(!(excess(0)>=0&&excess(hi)<=0))return null;
  const Pp=firmMarketBisect(excess,0,hi),Pc=tradeBuyer(w,Pp);
  return{Pc,Pp,Qd:D.at(Pc),Qs:S.at(Pp),Im:0,Ex:0,mode:'closed'};
}
function tradeCountry(Dexpr,Sexpr,Pw,policy={},ban='free',options={}){
  const D=typeof Dexpr==='string'?tradeCurve(Dexpr,true):Dexpr,S=typeof Sexpr==='string'?tradeCurve(Sexpr,false):Sexpr,w=tradeChannels(policy,Pw);
  if(D.error||S.error||w.error)return{error:D.error||S.error||w.error};
  if(!(Pw>=0)||!Number.isFinite(Pw))return{error:'Мировая цена должна быть неотрицательной.'};
  const freeD=D.at(Pw),freeS=S.at(Pw),freeImport=freeD>=freeS,solutions=[];
  const finish=r=>{
    const domestic=Math.min(r.Qd,r.Qs),budget=(r.Pc-r.Pp)*domestic+(r.Pc-Pw)*r.Im+(Pw-r.Pp)*r.Ex;
    if(options.details===false)return{...r,Pw,domestic,budget:policy.kind==='quota'?0:budget,rent:policy.kind==='quota'?budget:0,channels:w};
    const cs=integrate(q=>evalCurve(D.curve,q)-r.Pc,0,r.Qd),ps=integrate(q=>r.Pp-evalCurve(S.curve,q),0,r.Qs);
    const csFree=integrate(q=>evalCurve(D.curve,q)-Pw,0,freeD),psFree=integrate(q=>Pw-evalCurve(S.curve,q),0,freeS);
    return{...r,Pw,domestic,budget:policy.kind==='quota'?0:budget,rent:policy.kind==='quota'?budget:0,cs,ps,sw:cs+ps+(policy.kind==='quota'?0:budget),
      free:{Pc:Pw,Pp:Pw,Qd:freeD,Qs:freeS,Im:Math.max(0,freeD-freeS),Ex:Math.max(0,freeS-freeD),cs:csFree,ps:psFree,sw:csFree+psFree,budget:0,dwlProd:0,dwlCons:0},
      dwlProd:Math.abs(integrate(q=>evalCurve(S.curve,q)-Pw,Math.min(freeS,r.Qs),Math.max(freeS,r.Qs))),dwlCons:Math.abs(integrate(q=>Pw-evalCurve(D.curve,q),Math.min(r.Qd,freeD),Math.max(r.Qd,freeD))),channels:w};
  };
  if(policy.kind==='quota'){
    const limit=CalcNumber.parse(String(policy.quota??0))?.value;if(!(limit>=0))return{error:'Квота должна быть неотрицательной.'};
    const aut=options.autark||tradeAutark(D,S,w.domestic);if(!aut)return{error:'Автаркическое равновесие не найдено.'};
    const forbidden=freeImport?ban==='noimport':ban==='noexport',amount=forbidden?0:Math.min(limit,Math.abs(freeD-freeS));
    const f=P=>D.at(P)-S.at(P)-(freeImport?amount:-amount),P=amount===0?aut.Pc:firmMarketBisect(f,Math.min(Pw,aut.Pc),Math.max(Pw,aut.Pc));
    return finish({Pc:P,Pp:P,Qd:D.at(P),Qs:S.at(P),Im:freeImport?amount:0,Ex:freeImport?0:amount,mode:amount===0?'closed':freeImport?'import':'export'});
  }
  const add=(Pc,Pp,mode)=>{const Qd=D.at(Pc),Qs=S.at(Pp),flow=mode==='import'?Qd-Qs:Qs-Qd;if(Number.isFinite(Qd)&&Number.isFinite(Qs)&&flow>1e-8)solutions.push({Pc,Pp,Qd,Qs,Im:mode==='import'?flow:0,Ex:mode==='export'?flow:0,mode});};
  if(ban!=='noimport'){const Pc=tradeBuyer(w.imports,Pw);add(Pc,tradeSeller(w.domestic,Pc),'import');}
  if(ban!=='noexport'){const Pp=tradeSeller(w.exports,Pw);add(tradeBuyer(w.domestic,Pp),Pp,'export');}
  if(!solutions.length){
    const aut=options.autark||tradeAutark(D,S,w.domestic);if(!aut)return{error:'Равновесие без торговли не найдено.'};
    const importClosed=ban==='noimport'||aut.Pc<=tradeBuyer(w.imports,Pw)+1e-7;
    const exportClosed=ban==='noexport'||aut.Pp>=tradeSeller(w.exports,Pw)-1e-7;
    if(!importClosed||!exportClosed)return{error:'Не найден согласованный режим торговли.'};
    solutions.push(aut);
  }
  const chosen=solutions.find(r=>r.mode===(freeImport?'import':'export'))||solutions[0];
  return{...finish(chosen),alternatives:solutions.length>1?solutions.map(finish):[],multiple:solutions.length>1};
}

/* Экспортирующий монополист: внутренний спрос и внешний канал с
   постоянной чистой ценой. Импорт для перепродажи в эту модель не входит. */
function tradeMono(Dexpr,costExpr,Pw,policy={},ban='free'){
  const D=makeCurve(Dexpr),sp=splitCurveLhs(costExpr),cost=firmSupplyBuild({expr:costExpr,mode:lhsKey(sp.lhs)==='TC'?'tc':'mc'}),w=tradeChannels(policy,Pw);
  if(D.error||cost.error||w.error)return{error:D.error||cost.error||w.error};
  if(!(Pw>=0)||!Number.isFinite(Pw))return{error:'Мировая цена должна быть неотрицательной.'};
  const pe=tradeSeller(w.exports,Pw),a=D.linear?.a/w.domestic.A,b=(D.linear?.b-w.domestic.B)/w.domestic.A;
  let limit=ban==='noexport'?0:policy.kind==='quota'?CalcNumber.parse(String(policy.quota??0))?.value:Infinity;
  if(!(limit>=0))return{error:'Квота должна быть неотрицательной.'};
  const exact=!!D.linear&&D.linear.a<0&&cost.exact;
  if(!exact)return tradeMonoNumeric(D,cost,Pw,w,limit);
  const qEnd=Math.max(0,-D.linear.b/D.linear.a),qStar=Math.max(0,Math.min(qEnd,(pe-b)/(2*a))),cap=Math.min(cost.K,qEnd+limit);
  const allocation=Q=>Math.max(0,Q-limit,Math.min(Q,qStar,qEnd));
  const revenue=(Q,q=allocation(Q))=>(b+a*q)*q+pe*(Q-q),profit=Q=>revenue(Q)-cost.tc(Q);
  const candidates=new Set([0]),limits=[];let unbounded=false;
  for(const piece of cost.pieces){
    const lo=piece.lo,hi=Math.min(piece.hi,cap);if(hi<lo)continue;
    const cuts=[lo,hi,...[qStar,qStar+limit,qEnd].filter(x=>x>lo&&x<hi)].sort((x,y)=>x-y);
    for(let i=1;i<cuts.length;i++){
      const l=cuts[i-1],h=cuts[i],mid=Number.isFinite(h)?(l+h)/2:l+Math.max(1,l);
      const alpha=mid<qStar||mid>qStar+limit?1:0,beta=alpha?(mid>qStar+limit?-limit:0):qStar;
      const c=[b*beta+a*beta*beta-pe*beta-piece.c[0],b*alpha+2*a*alpha*beta+pe*(1-alpha)-piece.c[1],a*alpha*alpha-piece.c[2],-piece.c[3]];
      for(const Q of[l,h,...firmPolyRoots(firmPolyDerivative(c))].filter(x=>Number.isFinite(x)&&x>=l&&x<=h&&x<=cap)){
        const value=firmPolyAt(c,Q),actual=profit(Q);
        if(Number.isFinite(actual)&&Math.abs(actual-value)<1e-7*Math.max(1,Math.abs(actual)))candidates.add(Q);else limits.push({Q,profit:value});
      }
      if(h===Infinity){const lead=c.slice(1).filter(x=>x!==0).at(-1);if(lead>0)unbounded=true;}
    }
  }
  if(unbounded)return{error:'Конечного оптимального выпуска нет: прибыль растёт без предела.',unbounded:true};
  const rows=[...candidates].map(Q=>({Q,q:allocation(Q),profit:profit(Q)})).filter(r=>Number.isFinite(r.profit)).sort((x,y)=>y.profit-x.profit||y.Q-x.Q),best=rows[0];
  if(!best)return{error:'Оптимум не найден.'};
  if(limits.some(x=>x.profit>best.profit+1e-7))return{error:'Верхняя грань прибыли находится на открытой границе и не достигается.'};
  return tradeMonoResult(D,cost,Pw,w,best,policy,{exact:true,alternatives:rows.slice(1).filter(x=>Math.abs(x.profit-best.profit)<1e-7)});
}
function tradeMonoResult(D,cost,Pw,w,best,policy,extra={}){
  const {Q,q}=best,Ex=Math.max(0,Q-q),Pc=evalCurve(D,q),Pp=tradeSeller(w.domestic,Pc),Pe=tradeSeller(w.exports,Pw);
  const budget=(Pc-Pp)*q+(Pw-Pe)*Ex,cs=integrate(x=>evalCurve(D,x)-Pc,0,q),profit=Pp*q+Pe*Ex-cost.tc(Q);
  return{Q,Qs:Q,Qd:q,Pc,Pp,Pe,Pw,Im:0,Ex,budget:policy.kind==='quota'?0:budget,rent:0,cs,ps:profit+cost.fc,profit,sw:cs+profit+cost.fc+budget,...extra};
}
function tradeGolden(f,lo,hi){
  const r=(Math.sqrt(5)-1)/2;let a=hi-r*(hi-lo),b=lo+r*(hi-lo),fa=f(a),fb=f(b);
  for(let i=0;i<80;i++){if(fa>fb){hi=b;b=a;fb=fa;a=hi-r*(hi-lo);fa=f(a);}else{lo=a;a=b;fa=fb;b=lo+r*(hi-lo);fb=f(b);}}return(lo+hi)/2;
}
function tradeMaxNumeric(f,lo,hi){
  if(!(hi>lo))return{Q:lo,value:f(lo)};
  const xs=Array.from({length:241},(_,i)=>lo+(hi-lo)*i/240),ys=xs.map(f),candidates=[lo,hi];
  for(let i=1;i<240;i++)if(ys[i]>=ys[i-1]&&ys[i]>=ys[i+1])candidates.push(tradeGolden(f,xs[i-1],xs[i+1]));
  return candidates.map(Q=>({Q,value:f(Q)})).filter(r=>Number.isFinite(r.value)).sort((a,b)=>b.value-a.value)[0];
}
function tradeMonoNumeric(D,cost,Pw,w,limit){
  const pe=tradeSeller(w.exports,Pw),cap=Number.isFinite(cost.K)?cost.K:Math.min(1e6,cost.searchTop||1e6),cache=new Map();
  const at=Q=>{if(cache.has(Q))return cache.get(Q);const lo=Math.max(0,Q-limit),tc=cost.tc(Q),dom=q=>{const P=evalCurve(D,q);return P>=0?tradeSeller(w.domestic,P)*q+pe*(Q-q)-tc:-Infinity;};
    let r;if(D.linear?.a<0){const a=D.linear.a/w.domestic.A,b=(D.linear.b-w.domestic.B)/w.domestic.A,q=Math.max(lo,Math.min(Q,(pe-b)/(2*a)));r={Q:q,value:dom(q)};}else r=tradeMaxNumeric(dom,lo,Q);
    const row={Q,q:r?.Q??0,profit:r?.value??-Infinity};cache.set(Q,row);return row;};
  // Логарифмические окна не теряют малый оптимум на большой области.
  const cuts=[0];for(let x=1e-6;x<cap;x*=4)cuts.push(x);cuts.push(cap);
  const rows=[];for(let i=1;i<cuts.length;i++){const r=tradeMaxNumeric(Q=>at(Q).profit,cuts[i-1],cuts[i]);if(r)rows.push(at(r.Q));}
  rows.sort((a,b)=>b.profit-a.profit);const best=rows[0];
  if(!best||!Number.isFinite(best.profit))return{error:'Численный оптимум не найден.'};
  if(best.Q>=cap*(1-1e-8)&&!Number.isFinite(cost.K))return{error:'Выпуск выгодно увеличивать за пределы численного поиска.',approximate:true};
  return tradeMonoResult(D,cost,Pw,w,best,w.policy,{exact:false,searchTop:cap});
}

function tradePolicyState(prefix){
  if(prefix==='bigA'||prefix==='bigB'){const c=STATE.bigTrade?.[prefix.slice(-1)]||{};return{policy:{kind:'none',target:'trade',form:'unit',rate:10,quota:20,...c.policy},ban:c.ban||'free',legacy:false};}
  if(prefix==='open')return{policy:STATE.openPolicy||{kind:STATE.openTool==='tariff'?'tax':STATE.openTool==='quota'?'quota':'none',target:'trade',form:'unit',rate:STATE.openTariff??10,quota:STATE.openQuota??20},ban:STATE.openBan||'free',legacy:!STATE.openPolicy};
  return{policy:STATE.monoTrade||{kind:'none',target:'trade',form:'unit',rate:10,quota:20},ban:STATE.monoTradeBan||'free',legacy:!STATE.monoTrade};
}
function setTradePolicy(prefix,patch,ban){
  const old=tradePolicyState(prefix);historyMark('Вмешательство в торговлю');
  const policy={...old.policy,...patch};
  if(patch.target)policy.form='unit';
  if(prefix==='open'){STATE.openPolicy=policy;STATE.openBan=ban||old.ban;STATE.openTool='none';}
  else if(prefix==='bigA'||prefix==='bigB'){const key=prefix.slice(-1);STATE.bigTrade={...STATE.bigTrade,[key]:{...STATE.bigTrade[key],policy,ban:ban||old.ban}};}
  else{STATE.monoTrade=policy;STATE.monoTradeBan=ban||old.ban;}
  redrawAll();
}
function tradeControlsHTML(prefix,withKind=true){
  const seg=(key,items)=>'<div class="seg trade-'+key+'">'+items.map(([v,label])=>'<button type="button" class="seg-btn" data-trade-key="'+key+'" data-trade-value="'+v+'">'+label+'</button>').join('')+'</div>';
  return'<label class="trade-control-label">Торговля</label>'+seg('ban',[['free','Свободная'],['noimport','Запрет ввоза'],['noexport','Запрет вывоза']])+
    (withKind?'<label class="trade-control-label">Вмешательство</label>'+seg('kind',[['none','Нет'],['tax','Налог'],['subsidy','Субсидия'],['quota','Квота']]):'')+
    '<div class="trade-details">'+seg('target',[['trade','Торговля'],['internal','Внутри страны'],['consumer','Потребителям'],['producer','Производителям']])+
    '<div class="hint hint-keep trade-direction"></div>'+seg('form',[['unit','Потоварный'],['seller','НДС'],['buyer','Акциз'],['world','% мировой цены']])+
    '<div class="field trade-value"><label for="'+prefix+'-policy-rate">Ставка</label><input id="'+prefix+'-policy-rate" type="text" inputmode="decimal" data-plain="1" value="10"></div></div>'+
    '<div class="field trade-quota-value"><label for="'+prefix+'-policy-quota">Квота</label><input id="'+prefix+'-policy-quota" type="text" inputmode="decimal" data-plain="1" value="20"></div>';
}
function renderTradePolicyControls(){
  for(const prefix of['open','mono','bigA','bigB']){
    const host=document.getElementById(prefix+'-policy-controls');if(!host)continue;
    const big=prefix.startsWith('big'),on=big?STATE.sceneKey==='bigopen':prefix==='open'?STATE.sceneKey==='smallopen':STATE.sceneKey==='monoexport';host.style.display=on?'':'none';
    if(!host._wired){
      host.innerHTML=tradeControlsHTML(prefix,prefix!=='open');host._wired=true;
      host.querySelectorAll('[data-trade-key]').forEach(b=>b.addEventListener('click',()=>{const key=b.dataset.tradeKey,value=b.dataset.tradeValue;setTradePolicy(prefix,key==='ban'?{}:{[key]:value},key==='ban'?value:null);}));
      for(const key of['rate','quota'])host.querySelector('#'+prefix+'-policy-'+key).addEventListener('change',e=>setTradePolicy(prefix,{[key]:e.target.value}));
    }
    if(!on)continue;
    const {policy:p,ban,legacy}=tradePolicyState(prefix),active=p.kind==='tax'||p.kind==='subsidy',r=big?STATE.bigTradeResult?.countries?.[prefix.slice(-1)]:prefix==='open'?STATE.open?.tradeResult:STATE.discr3?.tradeResult;
    host.querySelectorAll('[data-trade-key]').forEach(b=>b.classList.toggle('active',(b.dataset.tradeKey==='ban'?ban:p[b.dataset.tradeKey])===b.dataset.tradeValue));
    host.querySelector('.trade-details').style.display=active?'':'none';host.querySelector('.trade-quota-value').style.display=p.kind==='quota'&&!(prefix==='open'&&legacy)?'':'none';
    host.querySelector('.trade-value').style.display=prefix==='open'&&legacy?'none':'';
    const exp=prefix==='mono'||(r?r.Ex>0||!r.Im&&r.free?.Ex>0:STATE.open?.importing===false),dir=exp?'вывоз':'ввоз';
    host.querySelector('.trade-direction').textContent=p.target==='trade'?(prefix==='open'&&legacy&&STATE.openTool==='tariff'?'Пошлина на ввоз (тариф)':p.kind==='subsidy'?'Субсидия '+(exp?'вывоза':'ввоза'):'Пошлина на '+dir):
      p.target==='internal'?'Сделки своих производителей со своими потребителями':p.target==='consumer'?'Внутренние покупки и ввоз':'Внутренние продажи и вывоз';
    host.querySelectorAll('[data-trade-key="form"]').forEach(b=>{
      const value=b.dataset.tradeValue;b.style.display=(p.target==='trade'?value==='unit'||value==='world':value!=='world')?'':'none';
      if(value==='seller')b.textContent=p.kind==='subsidy'?'% цены продавца':'НДС: % цены продавца';
      if(value==='buyer')b.textContent=p.kind==='subsidy'?'% цены покупателя':'Акциз: % цены покупателя';
    });
    for(const key of['rate','quota']){const input=host.querySelector('#'+prefix+'-policy-'+key);if(document.activeElement!==input)input.value=p[key]??(key==='rate'?10:20);}
    if(prefix==='open'){
      [['oi-none','none'],['oi-tariff','tax'],['oi-subsidy','subsidy'],['oi-quota','quota']].forEach(([id,k])=>document.getElementById(id)?.classList.toggle('active',p.kind===k));
      if(!legacy){document.getElementById('open-tariff-field').style.display='none';document.getElementById('open-quota-field').style.display='none';}
    }
  }
}
let _tradeOpenCache=null,_tradeMonoCache=null;
function recomputeTradeOpen(){
  const {policy,ban}=tradePolicyState('open');
  const source=c=>c?.srcForm==='QP'&&c.srcExpr?'Q = '+c.srcExpr:curveFormula(c);
  const de=source(STATE.D),se=source(STATE.S),key=JSON.stringify([de,se,STATE.openPw,policy,ban,STATE.params]);
  if(_tradeOpenCache?.key!==key)_tradeOpenCache={key,result:tradeCountry(de,se,STATE.openPw,policy,ban)};
  const r=_tradeOpenCache.result,free=r.free||{};
  STATE.open={Pw:STATE.openPw,tradeResult:r,error:r.error,Qd:free.Qd,Qs:free.Qs,Qd1:r.Qd,Qs1:r.Qs,P1:r.Pc,csFree:free.cs,psFree:free.ps,swFree:free.sw,cs1:r.cs,ps1:r.ps,sw1:r.sw,money:r.budget,dwlProd:r.dwlProd,dwlCons:r.dwlCons,dwlTotal:(r.dwlProd||0)+(r.dwlCons||0),importing:r.Im>0,volume:(free.Im||0)+(free.Ex||0),vol1:(r.Im||0)+(r.Ex||0),aut:STATE.eq,tool:policy.kind};
}
function recomputeTradeMono(){
  const {policy,ban}=tradePolicyState('mono'),Pw=evalCurve(makeCurve(STATE.d3D2),0),key=JSON.stringify([STATE.d3D1,STATE.d3MC,Pw,policy,ban,STATE.params]);
  if(_tradeMonoCache?.key!==key){const result=tradeMono(STATE.d3D1,STATE.d3MC,Pw,policy,ban);result.free=tradeMono(STATE.d3D1,STATE.d3MC,Pw);_tradeMonoCache={key,result};}
  const r=_tradeMonoCache.result,cost=discriminationCost(STATE.d3MC);
  STATE.discr3={tradeResult:r,c1:makeCurve(STATE.d3D1),c2:makeCurve(STATE.d3D2),cm:cost.curve,found:!r.error,Qtot:r.Q,q1:r.Qd,q2:r.Ex,P1:r.Pc,P2:Pw,mcLevel:r.Pe,gain:r.profit};
}
function tradeAnswerRows(r,mono=false){
  const flow=r.Im>0?['Импорт','Im']:['Экспорт','Ex'];
  return[['Цена потребителей Pc','Pc','Результат'],['Цена производителей Pp','Pp','Результат'],['Потребление Qd','Qd','Результат'],['Выпуск Qs','Qs','Результат'],[...flow,'Результат'],
    [r.budget<0?'Расход бюджета':'Доход бюджета','budget','Благосостояние'],['Излишек потребителей CS','cs','Благосостояние'],['Излишек производителей PS','ps','Благосостояние'],
    ...(mono?[['Прибыль Π','profit','Благосостояние']]:[['Потери производства','dwlProd','Потери'],['Потери потребления','dwlCons','Потери']]),['Благосостояние SW','sw','Благосостояние']];
}
function tradeHero(id,r,mono=false){if(!r||r.error)return[[id,'*']];return tradeAnswerRows(r,mono).map(([,key],i)=>[id,i,null,null,null,{before:r.free?.[key]}]);}
function updateTradePanel(id,r,mono=false){
  if(TaxMotion.drawing)return;
  const box=document.getElementById(id);if(!box)return;
  if(r.error){box.innerHTML='<div class="warn">'+ffEsc(r.error)+'</div>';return;}
  box.innerHTML=tradeAnswerRows(r,mono).map(([label,key,group])=>'<div class="stat ans-main" data-ans-group="'+group+'"><span>'+label+'</span><b>'+fmt(key==='budget'?Math.abs(r[key]):r[key])+'</b></div>').join('')+
    (r.rent?'<div class="stat"><span>Рента квоты</span><b>'+fmt(r.rent)+'</b></div><div class="hint">Рента не считается доходом бюджета: получатель зависит от распределения лицензий.</div>':'')+
    (r.Im+r.Ex<1e-8?'<div class="hint">Внешней торговли нет.</div>':'')+
    (r.multiple?'<div class="hint">При запрете одновременного ввоза и вывоза возможны два режима. Показано направление исходной свободной торговли. Другой режим: '+r.alternatives.filter(a=>a.mode!==r.mode).map(a=>(a.Im>0?'импорт ':'экспорт ')+fmt(a.Im+a.Ex)+', Pc = '+fmt(a.Pc)+', Pp = '+fmt(a.Pp)).join('; ')+'.</div>':'')+
    (r.exact===false?'<div class="hint">Приближённый поиск оптимума на 0 ≤ Q ≤ '+fmt(r.searchTop)+'.</div>':'');
}
function drawTradeCountryAreas(r,D,S){
  if(r.error)return;const g=svg.append('g').attr('clip-path','url(#plot-clip)');
  const band=(a,b,lo,hi,color,name)=>{if(!(b>a)||typeof lo==='number'&&typeof hi==='number'&&Math.abs(lo-hi)<1e-9)return;const xs=Array.from({length:161},(_,i)=>a+(b-a)*i/160),f=v=>typeof v==='number'?()=>v:q=>evalCurve(v,q),area=d3.area().x(q=>sx(q)).y0(q=>sy(f(lo)(q))).y1(q=>sy(f(hi)(q)));markArea(g.append('path').datum(xs).attr('d',area).attr('fill',color).attr('opacity',.18).attr('data-legend',name),{from:a,to:b,lo,hi});};
  if(STATE.showCS)band(0,r.Qd,r.Pc,D,COL.D,'Излишек потребителей');
  if(STATE.showPS)band(0,r.Qs,S,r.Pp,COL.S,'Излишек производителей');
  if(STATE.showOpenMoney){band(0,r.domestic,r.Pp,r.Pc,COL.tax,'Бюджет внутренних сделок');if(r.Im>0)band(r.Qs,r.Qd,r.Pw,r.Pc,COL.tax,'Бюджет ввоза');if(r.Ex>0)band(r.Qd,r.Qs,r.Pp,r.Pw,COL.tax,'Бюджет вывоза');}
  if(STATE.showOpenDwl&&r.free){band(Math.min(r.free.Qd,r.Qd),Math.max(r.free.Qd,r.Qd),r.Pw,D,COL.dwl,'Потери потребления');band(Math.min(r.free.Qs,r.Qs),Math.max(r.free.Qs,r.Qs),S,r.Pw,COL.dwl,'Потери производства');}
}
function drawTradeCountryLines(r){
  if(r.error)return;const g=svg.append('g'),ox=sx(0),oy=sy(0),seen=[];
  for(const[value,name,color]of[[r.Pw,'w',COL.reg],[r.Pc,'c',COL.D],[r.Pp,'p',COL.S]]){if(seen.some(x=>Math.abs(x-value)<1e-8))continue;seen.push(value);g.append('line').attr('x1',ox).attr('x2',sx(CONFIG.Qmax)).attr('y1',sy(value)).attr('y2',sy(value)).attr('stroke',color).attr('stroke-width',1.7).attr('stroke-dasharray',name==='w'?null:'6 4');axisValueY(g,ox,sy(value),fmt(value),name);}
  for(const[Q,P,color,name]of[[r.Qd,r.Pc,COL.D,'d'],[r.Qs,r.Pp,COL.S,'s']]){g.append('line').attr('x1',sx(Q)).attr('x2',sx(Q)).attr('y1',sy(P)).attr('y2',oy).attr('stroke',COL.inkSoft).attr('stroke-dasharray','4 3');g.append('circle').attr('cx',sx(Q)).attr('cy',sy(P)).attr('r',4).attr('fill',color);if(name==='d'||Math.abs(r.Qd-r.Qs)>1e-8)axisValueX(g,sx(Q),oy,fmt(Q),name);}
  if(r.Im+r.Ex>1e-8){g.append('line').attr('x1',sx(Math.min(r.Qd,r.Qs))).attr('x2',sx(Math.max(r.Qd,r.Qs))).attr('y1',sy(r.Pw)).attr('y2',sy(r.Pw)).attr('stroke',r.Im>0?COL.D:COL.S).attr('stroke-width',5).attr('opacity',.5);haloText(g,sx((r.Qd+r.Qs)/2),sy(r.Pw)-12,(r.Im>0?'Импорт = ':'Экспорт = ')+fmt(r.Im+r.Ex),'middle','auto');}
  attachOpenPwDrag(g.append('rect').attr('x',ox).attr('y',sy(r.Pw)-10).attr('width',sx(CONFIG.Qmax)-ox).attr('height',20).attr('fill','transparent').style('cursor','grab'));
}
function drawTradeMono(){
  const d=STATE.discr3,r=d.tradeResult;svg.selectAll('*').remove();addDefs();
  if(r.error){drawGrid();drawAxes();updateTradePanel('info-d3',r,true);return;}
  const cost=discriminationCost(STATE.d3MC),model=firmSupplyBuild({expr:STATE.d3MC,mode:lhsKey(splitCurveLhs(STATE.d3MC).lhs)==='TC'?'tc':'mc'}),w=tradeChannels(tradePolicyState('mono').policy,r.Pw),de=curveFormula(d.c1),mr=mrFormula(d.c1),netMR=mr?macroSimplify('(('+mr+')-('+CalcNumber.expression(w.domestic.B)+'))/'+CalcNumber.expression(w.domestic.A)):null;
  applyAutoRanges(padMax(Math.max(r.Q*1.25,r.Qd*1.5,curveZeroQ(d.c1,1e5)||0)),padMax(Math.max(r.Pw,r.Pc,evalCurve(d.c1,0))));makeScales();drawGrid();drawAxes();
  const g=svg.append('g').attr('clip-path','url(#plot-clip)'),line=d3.line().defined(x=>x&&Number.isFinite(x[1])&&x[1]>=0).x(x=>sx(x[0])).y(x=>sy(x[1]));
  const band=(a,b,lo,hi,color,name)=>{if(!(b>a)||typeof lo==='number'&&typeof hi==='number'&&Math.abs(lo-hi)<1e-9)return;const f=v=>typeof v==='number'?()=>v:q=>evalCurve(v,q),area=d3.area().x(q=>sx(q)).y0(q=>sy(f(lo)(q))).y1(q=>sy(f(hi)(q))),xs=Array.from({length:161},(_,i)=>a+(b-a)*i/160);markArea(g.append('path').datum(xs).attr('d',area).attr('fill',color).attr('opacity',.16).attr('data-legend',name),{from:a,to:b,lo,hi});};
  if(STATE.showCS)band(0,r.Qd,r.Pc,d.c1,COL.D,'Излишек потребителей');
  if(STATE.showPS){band(0,r.Qd,cost.curve,r.Pp,COL.S,'Излишек внутренних продаж');band(r.Qd,r.Q,cost.curve,r.Pe,COL.S,'Излишек экспорта');}
  band(0,r.Qd,r.Pp,r.Pc,COL.tax,'Бюджет внутренних сделок');band(r.Qd,r.Q,r.Pe,r.Pw,COL.tax,'Бюджет вывоза');
  for(const[name,fn,expr,color,dash]of[['D',q=>evalCurve(d.c1,q),de,COL.D,null],['MR после',q=>(discriminationMR(d.c1,q)-w.domestic.B)/w.domestic.A,netMR,COL.MR,'6 4'],['MC',q=>evalCurve(cost.curve,q),curveFormula(cost.curve),COL.S,null]]){
    const end=name==='MC'?Math.min(CONFIG.Qmax,model.K):CONFIG.Qmax,pts=Array.from({length:401},(_,i)=>{const q=end*i/400;return[q,fn(q)];}),path=g.append('path').datum(pts).attr('d',line).attr('fill','none').attr('stroke',color).attr('stroke-width',2.5).attr('stroke-dasharray',dash);if(expr)markExpr(path,expr,'Q',[0,end],{name});else markNumeric(path,'численная производная',name);labelCurve(g,q=>q<=end?fn(q):NaN,name,color,{key:'trade-mono-'+name});
  }
  const gl=svg.append('g');for(const[P,name]of[[r.Pw,'w'],...(Math.abs(r.Pe-r.Pw)>1e-8?[[r.Pe,'e']]:[])]){gl.append('line').attr('x1',sx(0)).attr('x2',sx(CONFIG.Qmax)).attr('y1',sy(P)).attr('y2',sy(P)).attr('stroke',COL.reg).attr('stroke-dasharray',name==='w'?null:'6 4');axisValueY(gl,sx(0),sy(P),fmt(P),name);}
  for(const[Q,P,name]of[[r.Qd,r.Pc,'M'],[r.Q,r.Pe,'Σ']]){if(name==='Σ'&&r.Ex<1e-8)continue;const px=sx(Q),py=sy(P);gl.append('circle').attr('cx',px).attr('cy',py).attr('r',4).attr('fill',COL.ink);gl.append('line').attr('x1',px).attr('x2',px).attr('y1',py).attr('y2',sy(0)).attr('stroke',COL.inkSoft).attr('stroke-dasharray','4 3');axisValueX(gl,px,sy(0),fmt(Q),name==='M'?'1':'Σ');if(name==='M')axisValueY(gl,sx(0),py,fmt(P),'c');pointName(gl,px,py,name,COL.ink);}
  if(r.Ex>0){gl.append('line').attr('x1',sx(r.Qd)).attr('x2',sx(r.Q)).attr('y1',sy(r.Pe)).attr('y2',sy(r.Pe)).attr('stroke',COL.S).attr('stroke-width',5).attr('opacity',.4);haloText(gl,sx((r.Q+r.Qd)/2),sy(r.Pe)-12,'Экспорт = '+fmt(r.Ex),'middle','auto');}
  updateTradePanel('info-d3',r,true);
}
