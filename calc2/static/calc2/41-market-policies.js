// Два одновременно действующих налога/субсидии. Решение 29.10, Э4.
// Одиночный инструмент продолжает пользоваться прежним расчётом.
function taxPairOn() {
  return STATE.sceneKey === 'taxes' && !!STATE.taxSecond && STATE.market !== 'monopoly'
    && STATE.scenario === 'none' && ['tax','subsidy'].includes(STATE.intervType);
}
function taxPolicy(type,form,side,rate) {
  const pct=PCT_FORMS[form];
  form=pct&&pct.type===type?form:'unit';
  return {type,form,side:form==='unit'&&side==='buyer'?'buyer':'seller',rate:Math.max(0,Number(rate)||0)};
}
function taxPairPolicies() {
  const second=STATE.taxSecond;
  return [taxPolicy(STATE.intervType,taxFormKey(),STATE.taxSide,STATE.tax),
    taxPolicy(second.type,second.form,second.side,second.rate)];
}
function taxPairRateMax(policy) {
  const pf=PCT_FORMS[policy.form];
  const custom=Number(policy.bounds?.max),usual=pf?PCT_MAX_FREE:unitRateMax();
  const max=Number.isFinite(custom)&&custom>0?custom:usual;
  return pf?.capped?Math.min(PCT_CAP,max):max;
}
function addSecondTax() {
  if(STATE.sceneKey!=='taxes'||STATE.taxSecond)return false;
  pushUndo();STATE.taxSecond={type:'tax',form:'unit',side:'seller',rate:0};
  syncTaxPairUI();redrawAll();return true;
}
function removeSecondTax() {
  if(!STATE.taxSecond)return;
  pushUndo();delete STATE.taxSecond;syncTaxPairUI();redrawAll();
}
function setSecondTax(patch,interactive=false) {
  if(!STATE.taxSecond)return;
  const old=STATE.taxSecond,next={...old,...patch};
  if(!['tax','subsidy'].includes(next.type))return;
  // Выбор другой формы обнуляет ставку, как у первого каскада.
  if((next.type!==old.type||next.form!==old.form)&&!('rate' in patch))next.rate=0;
  const policy=taxPolicy(next.type,next.form,next.side,next.rate);
  if(next.type===old.type&&next.form===old.form&&next.bounds){
    const {min,max,step}=next.bounds;
    if([min,max,step].every(Number.isFinite)&&min>=0&&max>min&&step>0)policy.bounds={min,max,step};
  }
  policy.rate=Math.max(policy.bounds?.min||0,Math.min(policy.rate,taxPairRateMax(policy)));
  STATE.taxSecond=policy;
  if(interactive&&TaxMotion.supported())TaxMotion.render(syncTaxPairUI);
  else {
    if(TaxMotion.pending)TaxMotion.cancel();
    syncTaxPairUI();redrawAll();
  }
}

function taxPairCurve(base,m,b) {
  if(isVertical(base))return {kind:'vertical',atQ:base.atQ,finalLhs:'Q',finalExpr:TaxMotion.drawing?'':CalcNumber.expression(base.atQ)};
  const fn=q=>m*evalCurve(base,q)+b;
  if(TaxMotion.drawing)return {fn,texExpr:''};
  const wrap=e=>simplifyRecord('('+e+')*('+m+')+('+b+')');
  if(base.srcForm==='QP'&&m!==0)return qpAfter(base,'(Q-('+b+'))/('+m+')',fn,wrap);
  return {fn,texExpr:wrap(curveFormula(base)||base.expr||'0')};
}
function recomputeTaxPair() {
  const items=taxPairPolicies();
  // Pb−Ps = u + tb·Pb + ts·Ps. Каждая процентная ставка берётся
  // от СВОЕЙ конечной цены; множители двух инструментов не перемножаются.
  let u=0,tb=0,ts=0,buyerUnits=0;
  for(const p of items){
    const signed=p.rate*(p.type==='subsidy'?-1:1),pf=PCT_FORMS[p.form];
    if(pf){if(pf.base==='buyer')tb+=signed/100;else ts+=signed/100;}
    else{u+=signed;if(p.side==='buyer')buyerUnits+=signed;}
  }
  const beta=1-tb,alpha=1+ts;
  const pair=STATE.taxPair={items,u,tb,ts,buyerUnits,error:null};
  if(!STATE.D||!STATE.S){pair.error='Задайте спрос и предложение.';return;}
  const D=STATE.D,S=STATE.S;
  let Q=null,Pb=null,Ps=null;
  STATE.taxAfterD=taxPairCurve(D,1,-buyerUnits);
  if(Math.abs(beta)>1e-12)STATE.taxAfterS=taxPairCurve(S,alpha/beta,u/beta-buyerUnits);
  else if(!isVertical(S)&&Math.abs(alpha)>1e-12){
    const z=findEquilibrium({fn:()=>1},{fn:q=>1+alpha*evalCurve(S,q)+u});
    const q=z?.Q;
    if(q!=null)STATE.taxAfterS={kind:'vertical',atQ:q,finalLhs:'Q',finalExpr:TaxMotion.drawing?'':CalcNumber.expression(q)};
  }
  STATE.taxCurveOn=!!(STATE.taxAfterD||STATE.taxAfterS);
  if(isVertical(D)&&isVertical(S)){pair.error='Две вертикальные кривые не определяют единственную цену.';return;}
  if(isVertical(D)){
    Q=D.atQ;Ps=evalCurve(S,Q);Pb=Math.abs(beta)>1e-12?(alpha*Ps+u)/beta:null;
  }else if(isVertical(S)){
    Q=S.atQ;Pb=evalCurve(D,Q);Ps=Math.abs(alpha)>1e-12?(beta*Pb-u)/alpha:null;
  }else{
    // Тот же поиск, что у одного инструмента: модель задаёт область и
    // плотность сетки; растягивание окна не меняет найденный корень.
    const eq=STATE.taxAfterS?findEquilibrium(STATE.taxAfterD,STATE.taxAfterS):null;
    if(eq){Q=eq.Q;Pb=evalCurve(D,Q);Ps=evalCurve(S,Q);}
  }
  if(Q===null||Pb===null||Ps===null||![Q,Pb,Ps].every(Number.isFinite)||Q<0||Pb< -1e-8||Ps< -1e-8){
    pair.error='При этих двух инструментах равновесия в первой четверти нет.';return;
  }
  Pb=Math.max(0,Pb);Ps=Math.max(0,Ps);
  const Pm=Pb-buyerUnits;
  if(Pm< -1e-8){pair.error='Рыночная цена получилась отрицательной: допустимого равновесия нет.';return;}
  items.forEach(p=>{
    const pf=PCT_FORMS[p.form],sign=p.type==='subsidy'?-1:1;
    p.wedge=sign*p.rate*(pf?(pf.base==='buyer'?Pb:Ps)/100:1);
    p.budget=p.wedge*Q;
  });
  STATE.taxEq={Q,Pb,Ps,Pm:Math.max(0,Pm)};
  STATE.budget=items.reduce((sum,p)=>sum+p.budget,0);
  STATE.tx=Math.abs(STATE.budget);
  STATE.csTax=integrateBroken(q=>quadPrice(D,q)-Pb,0,Q,quadBreaks(D,Q));
  STATE.psTax=integrateBroken(q=>Ps-quadPrice(S,q),0,Q,quadBreaks(S,Q));
  STATE.taxActive=true;STATE.taxNoBase=!STATE.eq;
  if(STATE.eq){
    const Q0=STATE.eq.Q;
    STATE.dwl=areaBetween(q=>evalCurve(D,q)-evalCurve(S,q),Math.min(Q,Q0),Math.max(Q,Q0));
    STATE.incBuyer=Pb-STATE.eq.P;STATE.incSeller=STATE.eq.P-Ps;
  }
}

function syncTaxPairUI() {
  const root=document.getElementById('tax-pair-controls');if(!root)return;
  const available=STATE.sceneKey==='taxes'&&['tax','subsidy'].includes(STATE.intervType);
  root.hidden=!available;
  if(!root._ready){
    root._ready=true;
    root.innerHTML=`<button type="button" class="btn btn-quiet sc-add" id="tax-add-second">+ ещё одно</button>
      <div class="tax-second" id="tax-second-row" hidden>
        <div class="tax-second-head"><span>Второе вмешательство</span><button type="button" class="btn btn-quiet" id="tax-remove-second" aria-label="Убрать второе вмешательство">Убрать</button></div>
        <div class="seg" data-tax2="type"><button type="button" class="seg-btn" data-value="tax">Налог</button><button type="button" class="seg-btn" data-value="subsidy">Субсидия</button></div>
        <div class="seg tax-second-forms" data-tax2="form"><button type="button" class="seg-btn" data-value="unit">Потоварный</button><button type="button" class="seg-btn" data-base="seller"></button><button type="button" class="seg-btn" data-base="buyer"></button></div>
        <div class="sc-siderow" data-tax2-side><span class="sc-sidelab"></span><div class="seg" data-tax2="side"><button type="button" class="seg-btn" data-value="seller">Продавец</button><button type="button" class="seg-btn" data-value="buyer">Покупатель</button></div></div>
        <div class="field tax-second-rate" id="tax2-field"><div class="tax-second-value"><span>Ставка</span><span class="tax-second-equation"><span data-tax2-letter></span><span data-tax2-value></span><span data-tax2-unit></span></span></div><div class="param-track"><button type="button" class="param-bound" data-tax2-bound="min" aria-label="Нижняя граница второй ставки"></button><input type="range" id="tax2-slider" min="0" max="100" step="0.1" value="0" aria-label="Ставка второго вмешательства"><button type="button" class="param-bound" data-tax2-bound="max" aria-label="Верхняя граница второй ставки"></button></div><div class="param-editor"></div></div>
      </div>`;
    root.querySelector('#tax-add-second').addEventListener('click',addSecondTax);
    root.querySelector('#tax-remove-second').addEventListener('click',removeSecondTax);
    root.querySelectorAll('[data-tax2] button').forEach(button=>button.addEventListener('click',()=>{
      pushUndo();setSecondTax({[button.parentElement.dataset.tax2]:button.dataset.value});
    }));
    TaxMotion.bindInput(root.querySelector('#tax2-slider'));
    root.querySelector('#tax2-slider').addEventListener('input',e=>setSecondTax({rate:+e.target.value},true));
    const ed=makeEditableValue({get:()=>STATE.taxSecond?.rate||0,set:v=>setSecondTax({rate:v},true),
      min:0,tex:(_,text)=>CalcNumber.texText(text)});
    const field=root.querySelector('#tax2-field'),slider=root.querySelector('#tax2-slider');
    const bounds=attachBoundsEditor(field,field.querySelector('.param-editor'),'Ставка 2',key=>slider[key],(key,value)=>{
      const next={min:+slider.min,max:+slider.max,step:STATE.taxSecond?.bounds?.step||.1,[key]:+value};
      const pf=PCT_FORMS[STATE.taxSecond?.form];
      if(pf?.capped)next.max=Math.min(PCT_CAP,next.max);
      if(next.min>=0&&next.max>next.min&&next.step>0)setSecondTax({bounds:next});
    });
    root.querySelectorAll('[data-tax2-bound]').forEach(el=>el.addEventListener('click',()=>bounds.open(el.dataset.tax2Bound)));
    ed.id='tax2-value';ed.setAttribute('aria-label','Ставка второго вмешательства');root.querySelector('[data-tax2-value]').append(ed);
  }
  const p=STATE.taxSecond;
  root.querySelector('#tax-add-second').hidden=!!p;root.querySelector('#tax-second-row').hidden=!p;
  if(!p)return;
  const sub=p.type==='subsidy';
  // Не заменять текстовые узлы под указателем: в WebKit это отменяет click,
  // если отложенная перерисовка случилась между mousedown и mouseup.
  const text=(el,value)=>{if(el.textContent!==value)el.textContent=value;};
  root.querySelectorAll('[data-base]').forEach(el=>{
    const key=el.dataset.base==='seller'?(sub?'subseller':'vat'):(sub?'subbuyer':'excise');
    el.dataset.value=key;text(el,PCT_FORMS[key].label);
  });
  root.querySelectorAll('[data-tax2] button').forEach(el=>{
    const active=p[el.parentElement.dataset.tax2]===el.dataset.value;
    el.classList.toggle('active',active);el.setAttribute('aria-pressed',String(active));
  });
  root.querySelector('[data-tax2-side]').hidden=p.form!=='unit';
  text(root.querySelector('.sc-sidelab'),sub?'Получает':'Платит');
  const letter=p.form==='unit'?(sub?'s_2=':'t_2='):'\\tau_2=';
  const label=root.querySelector('[data-tax2-letter]');
  if(label.dataset.tex!==letter){label.dataset.tex=letter;katexInto(label,letter);}
  text(root.querySelector('[data-tax2-unit]'),p.form==='unit'?'':'%');
  const slider=root.querySelector('#tax2-slider');
  slider.min=p.bounds?.min||0;slider.max=taxPairRateMax(p);InputSnap.exact(slider,p.rate);
  text(root.querySelector('[data-tax2-bound=min]'),boundText(+slider.min));
  text(root.querySelector('[data-tax2-bound=max]'),boundText(+slider.max));
  root.querySelector('#tax2-value')._repaint();
}

function drawTaxPairCurves() {
  const pair=STATE.taxPair;if(!pair||!STATE.taxCurveOn)return;
  const entries=[[STATE.D,STATE.taxAfterD,"D'",Math.abs(pair.buyerUnits)>1e-12],
    [STATE.S,STATE.taxAfterS,"S'",pair.items.some(p=>p.side==='seller'&&p.rate>0)]];
  entries.forEach(([base,after,name,on])=>{
    if(!base||!after||!on)return;
    const g=svg.append('g').attr('clip-path','url(#plot-clip)');
    const pts=isVertical(after)?[[after.atQ,0],[after.atQ,CONFIG.Pmax]]
      :Array.from({length:401},(_,i)=>{const q=CONFIG.Qmax*i/400,v=evalCurve(after,q);return Number.isFinite(v)?[q,v]:null;});
    const line=d3.line().defined(d=>d!==null).x(d=>sx(d[0])).y(d=>sy(d[1]));
    const path=g.append('path').datum(pts).attr('fill','none').attr('stroke',base.color)
      .attr('stroke-width',2).attr('stroke-dasharray','6 4').attr('data-tax-pair-curve',name).attr('d',line);
    if(isVertical(after))markExpr(path,CalcNumber.expression(after.atQ),'P',null,{axis:'y'});
    else if(!after.texExpr&&after.recY)markExpr(path,after.recY,'P',null,{axis:'y'});
    else markExpr(path,after);
    if(isVertical(after))haloText(g,sx(after.atQ)+8,sy(CONFIG.Pmax*.8),name,'start','middle');
    else labelCurve(g,q=>evalCurve(after,q),name,base.color,{from:.82});
  });
}
function drawTaxPairPoints() {
  if(!STATE.taxActive)return;
  const {Q,Pb,Ps,Pm}=STATE.taxEq,pair=STATE.taxPair,ox=sx(0),oy=sy(0),x=sx(Q),g=svg.append('g');
  const dash=(x1,y1,x2,y2)=>g.append('line').attr('x1',x1).attr('y1',y1).attr('x2',x2).attr('y2',y2)
    .attr('stroke',COL.inkSoft).attr('stroke-width',1).attr('stroke-dasharray','4 3');
  dash(x,sy(Math.max(Pb,Ps,Pm)),x,oy);axisValueX(g,x,oy,fmt(Q),'1');
  const prices=[[Pb,'b',COL.D],[Ps,'s',COL.S]];
  if(Math.abs(Pm-Pb)>1e-8&&Math.abs(Pm-Ps)>1e-8)prices.push([Pm,'m',COL.ink]);
  prices.forEach(([price,tag,color])=>{
    dash(x,sy(price),ox,sy(price));axisValueY(g,ox,sy(price),fmt(price),tag);
    g.append('circle').attr('cx',x).attr('cy',sy(price)).attr('r',4).attr('fill',color).attr('stroke',COL.halo).attr('stroke-width',1.5);
  });
  // Сначала покупательские выплаты, затем продавцу: промежуточная точка — Pm.
  const order=pair.items.map((p,i)=>({...p,index:i})).sort((a,b)=>(a.side==='buyer'?0:1)-(b.side==='buyer'?0:1));
  let cursor=Pb;
  order.forEach((p,i)=>{
    if(!p.rate)return;
    const end=cursor-p.wedge,px=x+12+i*18,top=sy(Math.max(cursor,end)),bottom=sy(Math.min(cursor,end)),mid=(top+bottom)/2;
    const group=g.append('g').attr('data-tax-pair-wedge',p.index+1);
    group.append('line').attr('x1',px).attr('x2',px).attr('y1',top).attr('y2',bottom).attr('stroke',COL.ink).attr('stroke-width',2);
    [top,bottom].forEach(y=>group.append('line').attr('x1',px-4).attr('x2',px+4).attr('y1',y).attr('y2',y).attr('stroke',COL.ink));
    const sym=p.form==='unit'?(p.type==='tax'?'t':'s'):'τ';
    haloText(group,px+9,mid,sym+'_'+(p.index+1)+' = '+CalcNumber.format(p.rate,{percent:p.form!=='unit'}),'start','middle');
    let startY,startRate;
    const hit=group.append('rect').attr('x',px-8).attr('y',Math.min(top,mid-10)).attr('width',16).attr('height',Math.max(bottom-top,20))
      .attr('fill','transparent').style('cursor','grab').attr('data-service','tax-pair-drag');
    hit.call(d3.drag().container(()=>svg.node()).on('start',event=>{
      pushUndo();startY=event.y;startRate=p.rate;
      InputSnap.begin(document.getElementById(p.index===0?'tax-slider':'tax2-slider'),{
        get:()=>p.index===0?STATE.tax:STATE.taxSecond.rate,
        set:v=>p.index===0?setTax(v,true):setSecondTax({rate:v},true)});
      TaxMotion.hold();document.body.style.cursor='grabbing';
    }).on('drag',event=>{
      let change=sy.invert(event.y)-sy.invert(startY);
      const pf=PCT_FORMS[p.form],base=pf?(pf.base==='buyer'?Pb:Ps):1;
      if(pf){if(base<=0)return;change=change/base*100;}
      if(p.index===0)setTax(startRate+change,true);else setSecondTax({rate:startRate+change},true);
    }).on('end',()=>{InputSnap.finish();document.body.style.cursor='';TaxMotion.release();}));
    cursor=end;
  });
}
function taxPairExplainHtml() {
  const pair=STATE.taxPair;if(!pair)return '';
  return '<div class="sb-note"><p>Каждый инструмент даёт свой клин между ценой покупателя и продавца. '+
    'Потоварная ставка – сумма на единицу товара, процентная – доля выбранной конечной цены.</p>'+
    '<p>$P_b-P_s=u+\\tau_b P_b+\\tau_s P_s$. Здесь $u$ – сумма потоварных ставок, '+
    '$\\tau_b$ и $\\tau_s$ – суммы ставок от цен покупателя и продавца. Субсидия входит со знаком минус.</p>'+
    '<p>Цена рынка $P_m$ – платёж продавцу до его расчётов с бюджетом. Бюджет показывает каждый сбор и расход отдельно, '+
    'а сальдо равно их сумме: $T=(P_b-P_s)Q$.</p></div>';
}
function updateTaxPairPanel(box) {
  const pair=STATE.taxPair;
  const finals=[[STATE.D,STATE.taxAfterD,'Спрос',"D'",Math.abs(pair.buyerUnits)>1e-12],
    [STATE.S,STATE.taxAfterS,'Предложение',"S'",pair.items.some(p=>p.side==='seller'&&p.rate>0)]];
  setFinalFunctions(finals.filter(([base,after,,,on])=>base&&after&&on&&(after.finalExpr||after.texExpr))
    .map(([base,after,name,tag])=>({name:name+' после вмешательств $'+tag+'$',color:base.color,lhs:after.finalLhs||'P',expr:after.finalExpr||after.texExpr})));
  if(pair.error){box.innerHTML='<div class="warn">'+pair.error+'</div>';return;}
  if(!STATE.taxActive){box.innerHTML='';return;}
  const e=STATE.taxEq,b=STATE.eq;
  const rows=[['Q',b?.Q,e.Q],['P рынка',b?.P,e.Pm],['P покупателя',b?.P,e.Pb],['P продавца',b?.P,e.Ps],
    ['CS',STATE.cs,STATE.csTax],['PS',STATE.ps,STATE.psTax],
    ...pair.items.map((p,i)=>[(p.type==='tax'?'Налог':'Субсидия')+' '+(i+1),0,p.budget]),
    ['Бюджет (сальдо)',0,STATE.budget],['SW',b?STATE.cs+STATE.ps:null,STATE.csTax+STATE.psTax+STATE.budget]];
  if(b)rows.push(['DWL',0,STATE.dwl]);
  let html='<table class="tx-table"><tr><th></th>'+(b?'<th>До</th>':'')+'<th>После</th>'+(b?'<th>Δ</th>':'')+'</tr>';
  rows.forEach(([label,before,after])=>{
    const signed=/^(Налог|Субсидия) /.test(label);
    html+='<tr><td>'+label+'</td>'+(b?'<td>'+fmt(before)+'</td>':'')+'<td>'+(signed?fmtDiff(after,0):fmt(after))+'</td>'+
      (b?'<td>'+fmtDiff(after,before)+'</td>':'')+'</tr>';
  });
  html+='</table>';
  if(!b)html+='<div class="hint">Исходного равновесия не было: сравнение «до и после» и DWL не определены.</div>';
  box.innerHTML=html;
}
