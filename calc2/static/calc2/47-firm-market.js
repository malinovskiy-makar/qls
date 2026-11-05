/* Конкурентный рынок одинаковых фирм: цена определяется спросом и n·qs. */
function firmMarketBisect(f,lo,hi){
  let fl=f(lo);for(let k=0;k<80;k++){const mid=(lo+hi)/2,fm=f(mid);if(!Number.isFinite(fm))return null;if(fl*fm<=0)hi=mid;else{lo=mid;fl=fm;}}return(lo+hi)/2;
}
function firmMarketDemand(expr){
  const b=buildAnyCurve(expr);if(b.error)return b;
  const curve=makeCurve(expr),safe=f=>x=>{try{const y=f(x);return Number.isFinite(y)?y:NaN;}catch(e){return NaN;}};
  if(b.form==='PQ'&&b.linear?.a===0)return{curve,price:b.linear.b,horizontal:true,at:()=>NaN,exact:true};
  let at;
  if(b.form==='QP')at=safe(P=>Math.max(0,b.srcCompiled.evaluate(paramScope({P,p:P}))));
  else if(b.linear){if(b.linear.a>=0)return{error:'Спрос должен убывать при повышении цены.'};at=P=>Math.max(0,(P-b.linear.b)/b.linear.a);}
  else at=safe(P=>{
    const f=Q=>evalCurve(curve,Q)-P,zero=f(0);if(zero<=0)return 0;
    let hi=1;for(let i=0;i<60&&f(hi)>0;i++)hi*=2;
    if(!(f(hi)<=0))return NaN;return firmMarketBisect(f,0,hi);
  });
  let prev=Infinity;for(const P of[0,.01,.1,1,10,100,1000,1e4]){const q=at(P);if(Number.isFinite(q)){if(q>prev+1e-7*Math.max(1,q))return{error:'Спрос должен убывать при повышении цены.'};prev=q;}}
  return{curve,at,exact:!!(b.linear||b.srcLinear),source:b};
}
function firmMarketContains(r,q){
  const near=(a,b)=>Math.abs(a-b)<=1e-7*Math.max(1,Math.abs(a),Math.abs(b));
  return !r.unattained&&!r.unbounded&&((r.outputs||[]).some(x=>near(x,q))||(r.intervals||[]).some((x,i)=>{
    const ends=r.intervalClosed?.[i]||[true,false];return(q>x[0]||ends[0]&&near(q,x[0]))&&(q<x[1]||ends[1]&&near(q,x[1]));
  }));
}
function firmMarketSolve(config={},demand='Q = 100 - 4*P',nInput=10){
  const firm=firmSupplyBuild(config),D=firmMarketDemand(demand),n=CalcNumber.parse(String(nInput))?.value;
  if(firm.error||D.error)return{error:firm.error||D.error,firm,D};
  const lr=firm.config.period==='lr',result={firm,D,n,lr,exact:firm.exact&&D.exact};
  const finish=(P,q,number=n,extra={})=>({...result,P,q,Q:q*number,n:number,profit:firm.tax.alpha*P*q-(q>0?firm.tc(q)+firm.tax.unit*q+firm.tax.lump:firm.zeroCost),found:true,...extra});
  if(lr){
    const P=firm.shutdown;
    if(!Number.isFinite(P)||P<0)return{...result,error:'Нет конечного равновесия со свободным входом при неотрицательной цене.'};
    const r=firm.at(P),positive=(r.outputs||[]).filter(q=>q>1e-8),ranges=(r.intervals||[]).filter(x=>x[1]>0);
    if(!firm.exact&&!positive.length){
      // Численный минимум может оказаться на машинный эпсилон ниже
      // безубыточности. Восстанавливаем положительный кандидат справа,
      // затем обязательно проверяем его средние затраты при исходной P.
      const q=firm.at(P+1e-8*Math.max(1,P)).Q;
      if(q>1e-8&&Number.isFinite(q)){
        const average=(firm.tc(q)+firm.tax.unit*q+firm.tax.lump)/(firm.tax.alpha*q);
        if(Math.abs(average-P)<1e-7*Math.max(1,P))positive.push(q);
      }
    }
    if(D.horizontal)return{...result,error:'При горизонтальном спросе объём рынка и число фирм не определены однозначно.'};
    const Q=D.at(P);if(!Number.isFinite(Q))return{...result,error:'Не удалось определить спрос при цене ухода.'};
    if(!positive.length&&!ranges.length)return{...result,P,Q,error:'Минимум средних издержек не достигается при положительном конечном выпуске. Конечного числа фирм нет.'};
    if(r.unattained||r.unbounded)return{...result,error:'При цене ухода нет конечного оптимального выпуска.'};
    const rangeClosed=ranges.map(range=>{const i=(r.intervals||[]).indexOf(range),ends=r.intervalClosed?.[i]||[true,false];return[range[0]>0&&ends[0],ends[1]];});
    let q=positive.at(-1);if(ranges.length){const range=ranges.at(-1),ends=rangeClosed.at(-1);q=Number.isFinite(range[1])?(ends[1]?range[1]:(range[0]+range[1])/2):Math.max(1,range[0]+1);}
    if(!(q>0)||!Number.isFinite(q))return{...result,error:'Выпуск действующей фирмы не определён однозначно.'};
    const alternatives=positive.map(x=>({q:x,n:Q/x}));
    return finish(P,q,Q/q,{Q,alternatives,nonunique:positive.length>1||ranges.length>0,ranges,rangeClosed,zeroDemand:Q===0});
  }
  if(!(n>0)||!Number.isFinite(n))return{...result,error:'Число фирм n должно быть положительным.'};
  if(D.horizontal){const P=D.price;if(!(P>=0))return{...result,error:'Цена спроса должна быть неотрицательной.'};const r=firm.at(P);if(!Number.isFinite(r.Q))return{...result,error:'При этой цене конечного рыночного объёма нет.'};return finish(P,r.Q,n,{nonunique:r.tie,outputSet:r});}
  const matches=[],tryPrice=P=>{
    if(!Number.isFinite(P)||P<0)return;const Q=D.at(P),q=Q/n,r=firm.at(P);
    if(Number.isFinite(Q)&&firmMarketContains(r,q)&&!matches.some(x=>Math.abs(x.P-P)<1e-7*Math.max(1,P)))matches.push(finish(P,q));
  };
  for(const p of firm.schedule.points)tryPrice(p.P);
  if(firm.exact){
    for(const row of firm.schedule.rows){
      if(row.unattained||row.expr==='Infinity')continue;
      const code=math.compile(row.expr),f=P=>D.at(P)-n*code.evaluate({P});
      let lo=row.lo,hi=row.hi,fl=f(lo);
      // Например Qd=100/P определён только при P>0: не превращаем
      // неопределённую границу в отсутствие внутреннего пересечения.
      if(!Number.isFinite(fl)){lo+=Math.max(1e-12,Math.abs(lo)*1e-12);fl=f(lo);}
      if(!Number.isFinite(hi)){hi=Math.max(1,lo+1);for(let i=0;i<100&&f(hi)>0;i++)hi*=2;}
      const fh=f(hi);
      if(row.expr==='0'&&Number.isFinite(fl)&&fh===0){
        let a=lo,b=hi;for(let i=0;i<80;i++){const x=(a+b)/2;if(D.at(x)>0)a=x;else b=x;}
        const P=(a+b)/2,r=firm.at(P);if(firmMarketContains(r,0))matches.push(finish(P,0,n,{priceInterval:[P,row.hi],nonunique:row.hi>P+1e-8}));
        continue;
      }
      if(Math.abs(fl)<1e-9)tryPrice(lo);if(Math.abs(fh)<1e-9)tryPrice(hi);
      if(Number.isFinite(fl)&&Number.isFinite(fh)&&fl*fh<0)tryPrice(firmMarketBisect(f,lo,hi));
    }
  }else{
    const f=P=>D.at(P)-n*firm.at(P).Q;let lo=0,hi=1;
    if(!Number.isFinite(f(lo)))lo=1e-12;
    for(let i=0;i<60&&f(hi)>0;i++)hi*=2;
    if(f(lo)*f(hi)<=0)tryPrice(firmMarketBisect(f,lo,hi));
  }
  matches.sort((a,b)=>a.P-b.P||(a.priceInterval?-1:0)-(b.priceInterval?-1:0));
  if(matches.length)return{...matches[0],equilibria:matches.map(x=>({P:x.P,q:x.q,Q:x.Q,profit:x.profit})),nonunique:matches.length>1||matches[0].nonunique};
  const gap=firm.schedule.points.find(r=>{const target=D.at(r.P)/n,qs=r.outputs||[];return qs.length>1&&target>qs[0]&&target<qs.at(-1);});
  return{...result,found:false,gap:gap?{P:gap.P,Q:D.at(gap.P),outputs:gap.outputs.map(q=>n*q)}:null,error:gap?'Спрос попадает в скачок предложения. Равновесия с одинаковым выпуском всех фирм нет.':'Равновесие при неотрицательной цене не найдено.'};
}

let _firmMarketCache=null;
function renderFirmMarketControls(){
  const on=STATE.sceneKey==='firmmarket',host=document.getElementById('firm-market-inputs');if(!host)return;
  host.style.display=on?'':'none';
  if(!host._wired){
    const D=document.getElementById('firm-market-demand'),n=document.getElementById('firm-market-n');
    liveFormula([D],()=>{STATE.firmMarket={...(STATE.firmMarket||{}),demand:D.value};redrawAll();});
    n.addEventListener('change',()=>{historyMark('Число фирм');STATE.firmMarket={...(STATE.firmMarket||{}),n:n.value};redrawAll();});host._wired=true;
  }
  const lr=STATE.costsSupply?.period==='lr',n=document.getElementById('firm-market-n');
  document.getElementById('firm-market-n-row').style.display=lr?'none':'';
  if(on&&document.activeElement!==n)n.value=STATE.firmMarket?.n??10;
  const price=document.getElementById('lr-price-field');if(on&&price)price.style.display='none';
  const only=document.getElementById('firm-mc-only');if(only)only.disabled=on;
}
function firmMarketScaledRecord(m,n){
  const scale=r=>({...r,Q:r.Q*n,outputs:(r.outputs||[]).map(q=>q*n),intervals:(r.intervals||[]).map(x=>x.map(q=>q*n))});
  const scaled={...m,schedule:{rows:m.schedule.rows.map(r=>({...r,expr:r.expr==='Infinity'?'Infinity':macroSimplify(CalcNumber.expression(n)+'*('+r.expr+')')})),points:m.schedule.points.map(scale)}};
  if(m.priceIndependent)scaled.priceIndependent=scale(m.priceIndependent);
  return{...firmFinalRecord(scaled),name:'Предложение рынка',lhs:'Q_s'};
}
function updateFirmMarketPanel(r){
  if(TaxMotion.drawing)return;
  const box=document.getElementById('info-costs'),stat=(group,label,value)=>'<div class="stat ans-main" data-ans-group="'+group+'"><span>'+label+'</span><b>'+value+'</b></div>';
  const price=document.getElementById('firm-market-price-value');if(price)price.textContent=r.found?fmt(r.P):'–';
  let html='';
  if(r.error)html='<div class="warn">'+ffEsc(r.error)+'</div>';
  else{
    html=stat('Рынок','Цена P',fmt(r.P))+stat('Рынок','Совокупный выпуск Q',fmt(r.Q))+stat('Рынок','Число фирм n',fmt(r.n));
    if(r.lr)html+='<div class="hint">Не всегда, но обычно в задачах требуется найти целое число фирм.</div>';
    html+=stat('Фирма','Выпуск фирмы q',fmt(r.q))+stat('Фирма','Прибыль фирмы Π',fmt(r.profit))+stat('Фирма','Прибыль всех фирм',fmt(r.profit*r.n));
    html+=stat('Фирма',r.lr?'Цена ухода с рынка (min ATC)':'Цена закрытия',fmt(r.firm.shutdown));
    if(r.nonunique)html+='<div class="hint">Равновесие не единственное. '+(r.lr?'При этой цене разные положительные выпуски дают нулевую прибыль; им отвечают разные числа фирм.':'Показан один из равновыгодных вариантов.')+'</div>';
    if(r.lr&&r.alternatives?.length>1)html+='<div class="hint">'+r.alternatives.map(x=>'q = '+fmt(x.q)+', n = '+fmt(x.n)).join('; ')+'</div>';
    if(r.lr&&r.ranges?.length)html+='<div class="hint">Допустимый выпуск действующей фирмы: '+firmOutputText({intervals:r.ranges,intervalClosed:r.rangeClosed})+'. Число фирм определяется как Q/q.</div>';
    if(r.priceInterval)html+='<div class="hint">Торговли нет. Равновесные цены: ['+fmt(r.priceInterval[0])+'; '+(Number.isFinite(r.priceInterval[1])?fmt(r.priceInterval[1])+']':'∞)')+'.</div>';
    if(r.zeroDemand)html+='<div class="hint">При цене ухода спрос равен нулю: действующих фирм нет.</div>';
    if(!r.exact)html+='<div class="hint">Приближённый расчёт равновесия.</div>';
  }
  box.innerHTML=html;
  if(r.firm&&!r.firm.error){const records=[{...firmFinalRecord(r.firm),lhs:'q_s'}];if(r.n>0&&Number.isFinite(r.n))records.push(firmMarketScaledRecord(r.firm,r.n));setFinalFunctions(records);}
}
function firmMarketPanel(id,gx0,gx1,title,xMax,pMax,eq){
  const left=gx0+(W<500?32:46),right=gx1-18,top=64,bottom=H-42;
  const wnd=panelWin(id,0,xMax,0,pMax),mx=d3.scaleLinear().domain([wnd.x0,wnd.x1]).range([left,right]),my=d3.scaleLinear().domain([wnd.y0,wnd.y1]).range([bottom,top]);
  const panel=registerPanel(id,mx,my,{x0:left,x1:right,y0:top,y1:bottom}),g=svg.append('g').attr('data-firm-market-panel',id),cid=id+'-clip';
  svg.select('defs').append('clipPath').attr('id',cid).append('rect').attr('x',left).attr('y',top).attr('width',Math.max(0,right-left)).attr('height',Math.max(0,bottom-top));
  drawGrid(mx,my,g);
  g.append('line').attr('x1',left).attr('x2',right).attr('y1',bottom).attr('y2',bottom).attr('stroke',COL.ink).attr('stroke-width',1.5).attr('marker-end','url(#arrow)');
  g.append('line').attr('x1',left).attr('x2',left).attr('y1',bottom).attr('y2',top).attr('stroke',COL.ink).attr('stroke-width',1.5).attr('marker-end','url(#arrow)');
  g.append('text').attr('x',(left+right)/2).attr('y',top-12).attr('text-anchor','middle').attr('font-size',FS.base).attr('font-weight',600).attr('fill',COL.ink).text(title);
  g.append('text').attr('x',right+4).attr('y',bottom+4).attr('font-size',FS.base).attr('fill',COL.inkSoft).text(id.endsWith('firm')?'q':'Q');
  g.append('text').attr('x',left-4).attr('y',top-2).attr('text-anchor','end').attr('font-size',FS.base).attr('fill',COL.inkSoft).text('P');
  for(const value of mx.ticks(3)){if(value<=0||eq&&Math.abs(value-eq.Q)<.1*(wnd.x1-wnd.x0))continue;haloText(g,mx(value),bottom+12,fmt(value),'middle','hanging').attr('class','axis-num');}
  for(const value of my.ticks(3)){if(value<=0||eq&&Math.abs(value-eq.P)<.1*(wnd.y1-wnd.y0))continue;haloText(g,left-5,my(value),fmt(value),'end','middle').attr('class','axis-num');}
  const curves=g.append('g').attr('clip-path','url(#'+cid+')'),line=d3.line().defined(d=>d&&Number.isFinite(d[0])&&Number.isFinite(d[1])).x(d=>mx(d[0])).y(d=>my(d[1]));
  const path=(pts,color,width,name,expr,domain,axis,dash)=>{const p=curves.append('path').datum(pts).attr('fill','none').attr('stroke',color).attr('stroke-width',width).attr('d',line);if(dash)p.attr('stroke-dasharray',dash);if(expr)markExpr(p,expr,axis==='y'?'P':'Q',domain,{axis,name});else markNumeric(p,'кривая рассчитана численно',name);return p;};
  const label=(name,Q,P,color)=>{if(Q<wnd.x0||Q>wnd.x1||P<wnd.y0||P>wnd.y1)return;renderLabelText(g.append('text').attr('x',mx(Q)+5).attr('y',my(P)-8).attr('font-size',FS.large).attr('fill',color).attr('paint-order','stroke').attr('stroke',COL.halo).attr('stroke-width',2.5),name);};
  function point(){if(!eq||!Number.isFinite(eq.Q)||!Number.isFinite(eq.P))return;const px=mx(eq.Q),py=my(eq.P);if(px<left||px>right||py<top||py>bottom)return;
    curves.append('line').attr('x1',px).attr('x2',px).attr('y1',py).attr('y2',bottom).attr('stroke',COL.inkSoft).attr('stroke-dasharray','4 3');
    curves.append('line').attr('x1',left).attr('x2',px).attr('y1',py).attr('y2',py).attr('stroke',COL.inkSoft).attr('stroke-dasharray','4 3');
    curves.append('circle').attr('cx',px).attr('cy',py).attr('r',4.5).attr('fill',COL.ink).attr('stroke',COL.halo).attr('stroke-width',1.5);label('E',eq.Q,eq.P,COL.ink);
    haloText(g,px,bottom+12,fmt(eq.Q),'middle','hanging').attr('class','coord-num');haloText(g,left-5,py,fmt(eq.P),'end','middle').attr('class','coord-num');noteAxisX(g,px,fmt(eq.Q),'',id);noteAxisY(g,py,fmt(eq.P),'',id);
  }
  return{...panel,wnd,g,curves,path,label,point};
}
function firmMarketDrawSupply(panel,m,n=1,old=false){
  const {mx,my,wnd,curves,path,label}=panel,color=COL.S,width=old?1.5:3.6,name=old?'S₀':'S';
  if(m.priceIndependent?.intervals?.length)return;
  if(m.exact){
    for(const row of m.schedule.rows){if(row.unattained||row.expr==='Infinity')continue;const lo=Math.max(0,row.lo,wnd.y0),hi=Math.min(row.hi,wnd.y1);if(hi<=lo)continue;const raw=CalcNumber.expression(n)+'*('+row.expr+')',expr=TaxMotion.drawing?raw:macroSimplify(raw),c=math.compile(expr),pts=Array.from({length:101},(_,i)=>{const P=lo+(hi-lo)*i/100;return[c.evaluate({P}),P];});path(pts,color,width,name,expr,[lo,hi],'y',old?'6 4':null);}
    for(const r of m.schedule.points){if(r.P<wnd.y0||r.P>wnd.y1)continue;const points=(r.outputs||[]).filter(Number.isFinite).map(q=>n*q),ranges=r.intervals||[];
      const segment=(a,b,dash)=>curves.append('line').attr('x1',mx(a)).attr('x2',mx(b)).attr('y1',my(r.P)).attr('y2',my(r.P)).attr('stroke',color).attr('stroke-width',width).attr('stroke-dasharray',dash);
      if(ranges.length)ranges.forEach(x=>segment(n*x[0],Math.min(n*x[1],wnd.x1),old?'6 4':null));
      else if(points.length>1)segment(points[0],points.at(-1),'4 4').attr('data-supply-jump','1');
      if(!old&&(r.tie||r.P===m.shutdown))points.forEach(Q=>curves.append('circle').attr('cx',mx(Q)).attr('cy',my(r.P)).attr('r',4).attr('fill',color).attr('stroke',COL.halo));
    }
  }else{const pts=[];let prev=null;for(let i=0;i<=150;i++){const P=Math.max(0,wnd.y0)+(wnd.y1-Math.max(0,wnd.y0))*i/150,Q=n*m.at(P).Q;if(prev!==null&&Math.abs(Q-prev)>(wnd.x1-wnd.x0)*.1)pts.push(null);pts.push([Q,P]);prev=Q;}path(pts,color,width,name,null,null,'y',old?'6 4':null);}
  if(!old){for(const f of[.72,.55,.9,.35]){const P=wnd.y1*f,Q=n*m.at(P).Q;if(Q>0&&Q<wnd.x1*.9){label('S',Q,P,color);break;}}}
}
function redrawFirmMarket(){
  renderFirmMarketControls();recomputeCosts();
  STATE.lr=null;delete STATE.firmSupplyResult;
  const input=STATE.firmMarket||{n:10,demand:'Q = 100 - 4*P'},key=JSON.stringify([firmSupplyConfig(),input,STATE.params]);
  if(_firmMarketCache?.key!==key)_firmMarketCache={key,result:firmMarketSolve(firmSupplyConfig(),input.demand,input.n)};
  const r=_firmMarketCache.result;STATE.firmMarketResult=r;
  svg.selectAll('*').remove();addDefs();clearPanels();
  const m=r.firm,q=r.found?r.q:3,Q=r.found?r.Q:40,P=r.found?r.P:r.gap?.P||15,n=r.n>0?r.n:10;
  const pMax=padMax(Math.max(1,P*1.7,Number.isFinite(m?.shutdown)?m.shutdown*1.3:0)),qMax=padMax(Math.max(1,q*1.8)),QMax=padMax(Math.max(1,Q*1.8));
  const left=W<500?16:64,mid=left+(W-left)/2;
  const fp=firmMarketPanel('firm-market-firm',left,mid,'Фирма',qMax,pMax,r.found?{Q:q,P}:null),mp=firmMarketPanel('firm-market-market',mid,W,'Рынок',QMax,pMax,r.found?{Q,P}:null);
  if(m&&!m.error){
    if(r.found){
      fp.path([[0,P],[fp.wnd.x1,P]],COL.price||COL.reg,1.5,'P',CalcNumber.expression(P),[0,fp.wnd.x1]);
      if(STATE.lrArea&&q>0){const atc=P-r.profit/q;fp.curves.append('rect').attr('x',fp.mx(0)).attr('width',fp.mx(q)-fp.mx(0)).attr('y',fp.my(Math.max(P,atc))).attr('height',Math.abs(fp.my(atc)-fp.my(P))).attr('fill',r.profit>=0?COL.tax:COL.S).attr('opacity',.16);}
    }
    const E=costExprs();for(const[name,fn]of[['TC',costTC],['VC',costVC],['FC',()=>m.fc],['AFC',costAFC],['AVC',costAVC],['ATC',costATC],['MC',costMC]]){
      if(!STATE['show'+name]||!costHas(name))continue;const end=Math.min(fp.wnd.x1,m.K),pts=[];
      const pieces=m.exact?m.pieces:[{lo:0,hi:end}];for(const piece of pieces){const lo=Math.max(1e-8,fp.wnd.x0,piece.lo),hi=Math.min(end,piece.hi);if(hi<=lo)continue;if(pts.length)pts.push(null);for(let i=0;i<=160;i++){const x=lo+(hi-lo)*i/160,eps=Math.min((hi-lo)*1e-7,1e-9*Math.max(1,Math.abs(x))),at=i===0?x+eps:i===160?x-eps:x,y=fn(at);pts.push(Number.isFinite(y)&&y>=0&&y<fp.wnd.y1*4?[x,y]:null);}}
      fp.path(pts,COL['cost'+name],2,name,E[name],[Math.max(0,fp.wnd.x0),end]);
      const candidate=pts.filter(x=>x&&x[0]<fp.wnd.x1*.83&&x[1]>fp.wnd.y1*.08&&x[1]<fp.wnd.y1*.88).at(-1);if(candidate)fp.label(name,...candidate,COL['cost'+name]);
    }
    if(m.tax.type!=='none'){const before=STATE.firmSupply?.before||firmSupplyBuild({...m.config,tax:{type:'none'}});if(!before.error){firmMarketDrawSupply(fp,before,1,true);firmMarketDrawSupply(mp,before,n,true);}}
    firmMarketDrawSupply(fp,m);firmMarketDrawSupply(mp,m,n);
  }
  if(r.D&&!r.D.error){const curve=r.D.curve,pts=Array.from({length:301},(_,i)=>{const x=Math.max(0,mp.wnd.x0)+(mp.wnd.x1-Math.max(0,mp.wnd.x0))*i/300,y=evalCurve(curve,x);return Number.isFinite(y)&&y>=0&&y<mp.wnd.y1*4?[x,y]:null;});const path=mp.path(pts,COL.D,2.5,'D');markCurve(path,curve,null,'D');const candidate=pts.filter(x=>x&&x[0]>mp.wnd.x1*.6&&x[1]>mp.wnd.y1*.1).at(-1);if(candidate)mp.label('D',...candidate,COL.D);}
  fp.point();mp.point();svg.append('line').attr('x1',mid).attr('x2',mid).attr('y1',52).attr('y2',H-30).attr('stroke',COL.grid);
  updateFirmMarketPanel(r);
}
