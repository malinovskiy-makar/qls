/* Два рынка с эндогенной мировой ценой. Связь стран — ровно баланс
   фактических потоков, рассчитанных общим движком трёх каналов. */
function bigTradeDefaults(){return{A:{D:'Q = 120 - P',S:'Q = P'},B:{D:'Q = 60 - P',S:'Q = P'},view:'countries'};}
function bigTradePrepare(c){
  const D=tradeCurve(c.D,true),S=tradeCurve(c.S,false),w=tradeChannels(c.policy||{},0);
  if(D.error||S.error||w.error)return{error:D.error||S.error||w.error};
  return{...c,D,S,autark:tradeAutark(D,S,w.domestic)};
}
function bigTradeAt(c,P,details=false){return tradeCountry(c.D,c.S,P,c.policy||{},c.ban||'free',{details,autark:c.autark});}
function bigTradeEquilibrium(input){
  const prepared={A:bigTradePrepare(input.A),B:bigTradePrepare(input.B)};
  if(prepared.A.error||prepared.B.error)return{error:prepared.A.error||prepared.B.error};
  const cache=new Map(),at=P=>{
    if(cache.has(P))return cache.get(P);
    const countries={};for(const key of['A','B'])countries[key]=bigTradeAt(prepared[key],P);
    const error=countries.A.error||countries.B.error,result={countries,error,excess:error?NaN:countries.A.Im+countries.B.Im-countries.A.Ex-countries.B.Ex};cache.set(P,result);return result;
  };
  let lo=0,hi=1,a=at(lo),b=at(hi);
  if(a.error)return{error:a.error};
  for(let i=0;i<100&&b.excess>0;i++){hi*=2;b=at(hi);}
  if(b.error)return{error:b.error};
  if(!(a.excess>=0&&b.excess<=0))return{error:'При неотрицательной мировой цене совместное равновесие не найдено.'};
  let P=a.excess===0?lo:b.excess===0?hi:(lo+hi)/2,r=at(P);
  for(let i=0;i<90&&Math.abs(r.excess)>1e-11;i++){
    if(r.excess>0)lo=P;else hi=P;P=(lo+hi)/2;r=at(P);
    if(r.error)return{error:r.error};
  }
  if(Math.abs(r.excess)>1e-7)return{error:'Потоки стран не совпали: для выбранных вмешательств непрерывное равновесие не найдено.'};
  let priceInterval=null;
  if(r.countries.A.Im+r.countries.A.Ex>1e-8){
    let l=0,h=P;for(let i=0;i<70;i++){const mid=(l+h)/2;if(at(mid).excess>1e-10)l=mid;else h=mid;}const lower=(l+h)/2;
    l=P;h=Math.max(1,P*2);for(let i=0;i<60&&Math.abs(at(h).excess)<=1e-10;i++)h*=2;
    for(let i=0;i<70;i++){const mid=(l+h)/2;if(at(mid).excess<-1e-10)h=mid;else l=mid;}const upper=(l+h)/2;
    if(upper-lower>1e-6){priceInterval=[lower,upper];P=(lower+upper)/2;r=at(P);}
  }
  r={...r,countries:{A:bigTradeAt(prepared.A,P,true),B:bigTradeAt(prepared.B,P,true)}};
  const {A,B}=r.countries,volume=(A.Im+A.Ex+B.Im+B.Ex)/2,noTrade=volume<1e-8;
  const common=Math.max(A.Pc,A.Pp,B.Pc,B.Pp)-Math.min(A.Pc,A.Pp,B.Pc,B.Pp)<1e-7;
  return{Pw:priceInterval||noTrade&&!common?null:P,shadowPw:P,priceInterval,volume:noTrade?0:volume,countries:r.countries,noTrade,
    worldSW:A.sw+B.sw+A.rent+B.rent,quotaRent:A.rent+B.rent,importer:A.Im>B.Im?'A':B.Im>A.Im?'B':null,
    exporter:A.Ex>B.Ex?'A':B.Ex>A.Ex?'B':null,multiple:!!priceInterval||A.multiple||B.multiple};
}
function bigTradeSolve(raw={}){
  const defaults=bigTradeDefaults(),input={...defaults,...raw,A:{...defaults.A,...raw.A},B:{...defaults.B,...raw.B}},current=bigTradeEquilibrium(input);
  if(current.error)return current;
  const base=bigTradeEquilibrium({A:{...input.A,policy:{},ban:'free'},B:{...input.B,policy:{},ban:'free'}});
  if(base.error)return{error:base.error};
  for(const key of['A','B']){
    const r=current.countries[key],before=base.countries[key];r.free=before;r.welfareChange=r.sw-before.sw;r.loss=-r.welfareChange;
  }
  return{...current,base,worldChange:current.worldSW-base.worldSW,worldLoss:base.worldSW-current.worldSW};
}

let _bigTradeCache=null;
function renderBigTradeControls(){
  const host=document.getElementById('sec-bigtrade'),views=document.getElementById('bigtrade-view'),on=STATE.sceneKey==='bigopen';
  if(!host||!views)return;host.style.display=on?'':'none';views.style.display=on?'':'none';
  if(!host._wired){
    for(const key of['A','B'])for(const role of['D','S']){
      const input=document.getElementById('big-'+key+'-'+role);
      liveFormula([input],()=>{STATE.bigTrade={...(STATE.bigTrade||bigTradeDefaults()),[key]:{...(STATE.bigTrade||bigTradeDefaults())[key],[role]:input.value}};redrawAll();});
    }
    views.querySelectorAll('[data-big-view]').forEach(b=>b.addEventListener('click',()=>{historyMark('Вид рынков');STATE.bigTrade={...STATE.bigTrade,view:b.dataset.bigView};redrawAll();}));host._wired=true;
  }
  views.querySelectorAll('[data-big-view]').forEach(b=>b.classList.toggle('active',b.dataset.bigView===(STATE.bigTrade?.view||'countries')));
}
function bigTradeRows(r){
  if(!r||r.error)return[];
  const price=x=>x.priceInterval?'['+fmt(x.priceInterval[0])+'; '+fmt(x.priceInterval[1])+']':x.Pw===null?'Не определена':x.Pw;
  const rows=[['Мировой рынок','Мировая цена Pw',price(r),r.base.Pw],['Мировой рынок','Объём торговли',r.volume,r.base.volume]];
  for(const key of['A','B']){
    const c=r.countries[key],before=c.free,group='Страна '+key,flow=c.Im>0||!c.Ex&&before.Im>0?'Im':'Ex';
    for(const[label,k]of[['Цена потребителей Pc','Pc'],['Цена производителей Pp','Pp'],['Потребление Qd','Qd'],['Выпуск Qs','Qs'],[flow==='Im'?'Импорт':'Экспорт',flow],['Излишек потребителей CS','cs'],['Излишек производителей PS','ps'],[c.budget<0?'Расход бюджета':'Доход бюджета','budget'],['Благосостояние SW','sw'],['Изменение благосостояния','welfareChange']])rows.push([group,label,k==='budget'?Math.abs(c[k]):c[k],k==='budget'?Math.abs(before[k]):k==='welfareChange'?0:before[k]]);
    if(c.rent>1e-7&&!r.priceInterval)rows.push([group,'Рента квоты',c.rent,0]);
  }
  if(r.quotaRent>1e-7)rows.push(['Мир','Рента квот',r.quotaRent,0]);
  rows.push(['Мир','Потери мира',r.worldLoss,0]);return rows;
}
function bigTradeHero(){
  const r=STATE.bigTradeResult;if(!r||r.error)return[['info-bigtrade','*']];
  const changed=['A','B'].some(k=>{const c=STATE.bigTrade?.[k]||{};return c.policy?.kind&&c.policy.kind!=='none'||c.ban&&c.ban!=='free';});
  return bigTradeRows(r).map(([g,label,value,before],i)=>['info-bigtrade',i,null,null,null,{g,...(changed&&typeof value==='number'&&typeof before==='number'?{before}:{})}]);
}
function updateBigTradePanel(r){
  const box=document.getElementById('info-bigtrade');
  box.innerHTML=r.error?'<div class="warn">'+ffEsc(r.error)+'</div>':bigTradeRows(r).map(([g,label,value])=>'<div class="stat ans-main" data-ans-group="'+g+'"><span>'+label+'</span><b>'+(typeof value==='number'?fmt(value):value)+'</b></div>').join('')+
    (r.noTrade?'<div class="hint">Внешней торговли нет. В каждой стране – внутреннее равновесие.</div>':'')+
    (r.priceInterval?'<div class="hint">Квоты фиксируют объём, но не единственную мировую цену. Рента между странами зависит от цены внутри указанного диапазона; показана её общая сумма.</div>':'')+
    (r.quotaRent>1e-7?'<div class="hint">Квотная рента включена в итог мира. В SW отдельных стран она не включена: получатель зависит от распределения лицензий.</div>':'')+
    (r.multiple&&!r.priceInterval?'<div class="hint">Вмешательство допускает несколько односторонних торговых режимов. Выбран режим, продолжающий исходное направление торговли.</div>':'');
}
function bigTradeSyncPriceWindow(id){
  if(STATE.sceneKey!=='bigopen'||!['big-A','big-B'].includes(id))return;
  const other=id==='big-A'?'big-B':'big-A',p=STATE.panels.find(x=>x.id===other),w=STATE.panelWin[id];
  if(p&&w)STATE.panelWin[other]={x0:p.mx.domain()[0],x1:p.mx.domain()[1],y0:w.y0,y1:w.y1};
}
function bigTradePanelBand(panel,a,b,lo,hi,color,name){
  if(!(b>a)||typeof lo==='number'&&typeof hi==='number'&&Math.abs(lo-hi)<1e-9)return;
  const f=v=>typeof v==='number'?()=>v:q=>evalCurve(v,q),xs=Array.from({length:161},(_,i)=>a+(b-a)*i/160),area=d3.area().x(q=>panel.mx(q)).y0(q=>panel.my(f(lo)(q))).y1(q=>panel.my(f(hi)(q)));
  markArea(panel.curves.append('path').datum(xs).attr('d',area).attr('fill',color).attr('opacity',.16).attr('data-legend',name),{from:a,to:b,lo,hi});
}
function bigTradeCountryPlot(panel,key,c,prepared,Pw){
  const{mx,my,curves,g,wnd}=panel,D=prepared.D.curve,S=prepared.S.curve;
  if(STATE.showCS)bigTradePanelBand(panel,0,c.Qd,c.Pc,D,COL.D,'CS');
  if(STATE.showPS)bigTradePanelBand(panel,0,c.Qs,S,c.Pp,COL.S,'PS');
  for(const[name,curve,color]of[['D',D,COL.D],['S',S,COL.S]]){
    const pts=Array.from({length:301},(_,i)=>{const Q=Math.max(0,wnd.x0)+(wnd.x1-Math.max(0,wnd.x0))*i/300,P=evalCurve(curve,Q);return Number.isFinite(P)&&P>=0&&P<wnd.y1*4?[Q,P]:null;});
    markCurve(panel.path(pts,color,2.5,name+'_'+key),curve,null,name+'_'+key);
    const label=pts.filter(p=>p&&p[0]>wnd.x1*.5&&p[0]<wnd.x1*.85&&p[1]>wnd.y1*.12&&p[1]<wnd.y1*.85).at(-1);if(label)panel.label(name+'_'+key,...label,color);
  }
  const seen=[];
  for(const[P,name,color]of[[c.Pc,'c',COL.D],[c.Pp,'p',COL.S],...(Pw===null?[]:[[Pw,'w',COL.reg]])]){
    if(seen.some(x=>Math.abs(x-P)<1e-7)||P<wnd.y0||P>wnd.y1)continue;seen.push(P);
    panel.path([[Math.max(0,wnd.x0),P],[wnd.x1,P]],color,1.2,'P_'+name,CalcNumber.expression(P),[Math.max(0,wnd.x0),wnd.x1],null,'5 4');
    haloText(g,panel.x0-5,my(P),fmt(P),'end','middle',{noFlip:true}).attr('class','coord-num');noteAxisY(g,my(P),fmt(P),name,panel.id);
  }
  const closeX=Math.abs(mx(c.Qd)-mx(c.Qs))<(measureText(fmt(c.Qd),FS.small)+measureText(fmt(c.Qs),FS.small))/2+10;
  for(const[Q,P,name,color]of[[c.Qd,c.Pc,'d',COL.D],[c.Qs,c.Pp,'s',COL.S]]){
    curves.append('line').attr('x1',mx(Q)).attr('x2',mx(Q)).attr('y1',my(P)).attr('y2',panel.y1).attr('stroke',COL.inkSoft).attr('stroke-dasharray','4 3');
    curves.append('circle').attr('cx',mx(Q)).attr('cy',my(P)).attr('r',4).attr('fill',color);
    if(Q>=wnd.x0&&Q<=wnd.x1&&(name==='d'||Math.abs(c.Qs-c.Qd)>1e-7)){
      g.selectAll('text.axis-num').filter(function(){const x=+this.getAttribute('x'),y=+this.getAttribute('y');return y>panel.y1&&Math.abs(x-mx(Q))<measureText(fmt(Q),FS.small)+8;}).remove();
      haloText(g,mx(Q),panel.y1+10+(closeX&&name==='s'?15:0),fmt(Q),'middle','hanging').attr('class','coord-num').attr('data-big-axis-x',name);noteAxisX(g,mx(Q),fmt(Q),name,panel.id);
    }
  }
  if(c.Im+c.Ex>1e-8){const P=c.Im>0?c.Pc:c.Pp;curves.append('line').attr('x1',mx(Math.min(c.Qd,c.Qs))).attr('x2',mx(Math.max(c.Qd,c.Qs))).attr('y1',my(P)).attr('y2',my(P)).attr('stroke',c.Im>0?COL.D:COL.S).attr('stroke-width',5).attr('opacity',.55);panel.label((c.Im>0?'Im':'Ex')+' = '+fmt(c.Im+c.Ex),(c.Qs+c.Qd)/2,P,COL.ink);}
}
function bigTradeWorldPlot(panel,r,input,prepared){
  const importer=r.importer||r.base.importer||'A',exporter=r.exporter||r.base.exporter||'B';
  const before={};for(const key of['A','B'])before[key]=bigTradePrepare({...input[key],policy:{},ban:'free'});
  for(const[key,field,name,color]of[[importer,'Im','ED',COL.D],[exporter,'Ex','ES',COL.S]]){
    const changed=input[key].policy?.kind&&input[key].policy.kind!=='none'||input[key].ban&&input[key].ban!=='free';
    for(const old of changed?[true,false]:[false]){
      const c=old?before[key]:prepared[key],pts=Array.from({length:401},(_,i)=>{const P=Math.max(0,panel.wnd.y0)+(panel.wnd.y1-Math.max(0,panel.wnd.y0))*i/400,v=bigTradeAt(c,P);return!v.error&&v[field]>1e-8?[v[field],P]:null;});
      panel.path(pts,color,old?1.5:2.6,name+(old?'₀':''),null,null,'y',!old&&changed?'6 4':null).attr('data-big-world',name+(old?'0':''));
      const label=pts.filter(x=>x&&x[0]>panel.wnd.x1*.45&&x[0]<panel.wnd.x1*.82&&x[1]>panel.wnd.y1*.12&&x[1]<panel.wnd.y1*.85).at(-1);if(label)panel.label(name+(old?'₀':''),...label,color);
    }
  }
  if(r.Pw!==null&&r.volume>0){
    const a=r.countries[importer],b=r.countries[exporter];
    if(input[importer].policy?.kind!=='quota')bigTradePanelBand(panel,0,r.volume,r.Pw,a.Pc,COL.tax,'Бюджет ввоза');
    if(input[exporter].policy?.kind!=='quota')bigTradePanelBand(panel,0,r.volume,b.Pp,r.Pw,COL.tax,'Бюджет вывоза');
    panel.point();
  }else if(r.priceInterval){panel.curves.append('line').attr('x1',panel.mx(r.volume)).attr('x2',panel.mx(r.volume)).attr('y1',panel.my(r.priceInterval[0])).attr('y2',panel.my(r.priceInterval[1])).attr('stroke',COL.ink).attr('stroke-width',4);panel.label('Pw ∈ ['+fmt(r.priceInterval[0])+'; '+fmt(r.priceInterval[1])+']',r.volume,r.priceInterval[1],COL.ink);}
}
function redrawBigTrade(){
  const input=STATE.bigTrade||bigTradeDefaults(),key=JSON.stringify([input.A,input.B,STATE.params]);
  if(_bigTradeCache?.key!==key)_bigTradeCache={key,result:bigTradeSolve(input),prepared:{A:bigTradePrepare(input.A),B:bigTradePrepare(input.B)}};
  const r=_bigTradeCache.result;STATE.bigTradeResult=r;svg.selectAll('*').remove();addDefs();clearPanels();
  // У этих панелей собственные поля. Общая вертикаль CONFIG здесь не
  // используется; её замер шрифта не должен менять состояние при экспорте.
  CONFIG.margin.left=46;
  if(r.error){drawGrid();drawAxes();updateBigTradePanel(r);return;}
  const prepared=_bigTradeCache.prepared,pMax=padMax(Math.max(1,...['A','B'].flatMap(k=>[r.countries[k].Pc*1.5,r.countries[k].Pp*1.5,prepared[k].autark?.Pc*1.3||0])));
  const left=W<500?8:40,mid=left+(W-left)/2;
  if(input.view==='world'){
    const qMax=padMax(Math.max(1,r.volume*1.8,r.base.volume*1.8)),p=firmMarketPanel('big-world',left,W,'Мировой рынок',qMax,pMax,r.Pw===null||!r.volume?null:{P:r.Pw,Q:r.volume});bigTradeWorldPlot(p,r,input,prepared);
  }else{
    for(const[key,gx0,gx1]of[['A',left,mid],['B',mid,W]]){
      const c=r.countries[key],qMax=padMax(Math.max(1,c.Qd*1.45,c.Qs*1.45)),p=firmMarketPanel('big-'+key,gx0,gx1,'Страна '+key,qMax,pMax,{Q:c.Qd,P:c.Pc});bigTradeCountryPlot(p,key,c,prepared[key],r.Pw);
    }
    svg.append('line').attr('x1',mid).attr('x2',mid).attr('y1',52).attr('y2',H-30).attr('stroke',COL.grid);
  }
  updateBigTradePanel(r);
}
function bigTradeSmallLegend(seen){
  const g=svg.append('g').attr('class','legend').style('pointer-events','none'),items=seen.map(e=>({e,label:areaShort(e.key)}));
  const widths=items.map(x=>measureText(x.label,FS.base,600)+30),total=widths.reduce((a,b)=>a+b,0);let x=W-total-8;
  items.forEach(({e,label},i)=>{g.append('rect').attr('x',x).attr('y',12).attr('width',11).attr('height',11).attr('rx',3).attr('fill',e.color).attr('opacity',.45);g.append('text').attr('x',x+16).attr('y',22).attr('font-size',FS.base).attr('fill',COL.ink).text(label);x+=widths[i];});
}
