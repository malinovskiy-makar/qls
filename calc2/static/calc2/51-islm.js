// IS–LM из параметров; прежний ввод двух кривых остаётся самостоятельным режимом.
function islmDefaults(){return{a:70,b:.8,I0:40,d:.2,G:0,T:6,Xn:0,md:'.4*Y-.4*r',Ms:400,P:2};}
function islmScalar(v){return CalcNumber.parse(String(v))?.value??NaN;}
function macroSimplify(expr){try{return math.simplify(math.rationalize(expr)).toString();}catch(e){return math.simplify(expr).toString();}}
function islmSubstitute(expr,values){return math.parse(expr).transform(n=>n.isSymbolNode&&Object.hasOwn(values,n.name)?math.parse(String(values[n.name])):n).toString();}
function islmAffine(expr,v){
  try{const slope=math.simplify(math.derivative(expr,v));if(math.simplify(math.derivative(slope,v)).toString()!=='0')return null;return{a:slope.toString(),b:macroSimplify(islmSubstitute(expr,{[v]:0}))};}catch(e){return null;}
}
function islmRoots(f,maximum=1e12,scale=1){
  const xs=new Set([0,maximum]);for(let e=-12;e<=12;e+=.1){const x=10**e;if(x<maximum)xs.add(x);}if(maximum<1e10)for(let i=1;i<600;i++)xs.add(maximum*i/600);
  const points=[...xs].sort((a,b)=>a-b),roots=[];const add=x=>{const y=f(x);if(Number.isFinite(y)&&Math.abs(y)<1e-8*Math.max(1,scale)&&!roots.some(r=>Math.abs(r-x)<1e-7*Math.max(1,r,x)))roots.push(x);};
  let px=points[0],py=f(px);if(py===0)add(px);
  for(const x of points.slice(1)){const y=f(x);if(y===0)add(x);if(Number.isFinite(y)&&Number.isFinite(py)&&y*py<0){let lo=px,hi=x,fl=py;for(let k=0;k<70;k++){const mid=(lo+hi)/2,fm=f(mid);if(!Number.isFinite(fm))break;if(fl*fm<=0)hi=mid;else{lo=mid;fl=fm;}}add((lo+hi)/2);}px=x;py=y;}
  return roots;
}
function islmSolve(raw, fixed=null){
  try{
    const c={...islmDefaults(),...raw};for(const k of['a','b','I0','d','G','T','Xn','Ms','P']){c[k]=islmScalar(c[k]);if(!Number.isFinite(c[k]))throw Error('Нужно число для '+k+'.');}
    if(c.b<0||c.b>=1)throw Error('Предельная склонность к потреблению b должна быть от 0 до 1, не включая 1.');
    if(c.d<0)throw Error('Чувствительность инвестиций d должна быть неотрицательной.');if(c.P<=0||c.Ms<0)throw Error('Уровень цен P должен быть положительным, предложение денег – неотрицательным.');
    const A=c.a-c.b*c.T+c.I0+c.G+c.Xn,h=1-c.b;
    const isExpr=macroSimplify('('+CalcNumber.expression(A)+'-('+CalcNumber.expression(c.d)+')*r)/('+CalcNumber.expression(h)+')');
    const yAt=r=>(A-c.d*r)/h;
    const mdExpr=math.parse(prepExpr(c.md)).transform(n=>n.isSymbolNode&&n.name==='i'?new math.SymbolNode('r'):n).toString();
    const mdCompiled=math.parse(mdExpr).compile(),scope=scopeFor(mdExpr,{Y:0,r:0,i:0});
    const md=(Y,r)=>{try{const v=mdCompiled.evaluate({...scope,Y,r,i:r});return typeof v==='number'&&Number.isFinite(v)?v:NaN;}catch(e){return NaN;}};
    const residual=r=>{const Y=yAt(r);return Y>=-1e-8?md(Math.max(0,Y),r)-c.Ms/c.P:NaN;};
    const bound=c.d>0?Math.max(0,A/c.d):1e12,roots=fixed?[fixed.P]:islmRoots(residual,bound,c.Ms/c.P);
    if(fixed&&Math.abs(residual(fixed.P))>1e-7*Math.max(1,c.Ms/c.P))throw Error('При заданной ставке денежный рынок не уравновешен.');
    if(roots.length!==1)throw Error(roots.length?'Есть несколько равновесий IS–LM. Уточните функции: единственную точку выбрать нельзя.':'Равновесие IS–LM с неотрицательными выпуском и ставкой не найдено.');
    const r=roots[0],Y=Math.max(0,yAt(r)),eq={Q:Y,P:r};
    const isCurve=c.d===0?makeVerticalCurve(A/h):macroCurveY(macroSimplify('('+CalcNumber.expression(A)+'-('+CalcNumber.expression(h)+')*Y)/('+CalcNumber.expression(c.d)+')'),['Y']);
    const isRecord={name:'IS',color:COL.D,lhs:'Y',expr:isExpr};
    const affineY=islmAffine(mdExpr,'Y'),affineR=islmAffine(mdExpr,'r');let lmCurve,lmRecord;
    if(affineY&&math.simplify(affineY.a).toString()!=='0'){
      const expr=macroSimplify('('+CalcNumber.expression(c.Ms/c.P)+'-('+affineY.b+'))/('+affineY.a+')'),line=islmAffine(expr,'r');lmRecord={name:'LM',color:COL.S,lhs:'Y',expr};
      if(line){const m=Number(math.evaluate(line.a,scope)),b=Number(math.evaluate(line.b,scope));lmCurve=Math.abs(m)<1e-14?makeVerticalCurve(b):texTag({fn:Y=>(Y-b)/m},'rec',{expr,v:'r',axis:'y'});}
      if(!lmCurve){const compiled=math.parse(expr).compile();lmCurve=texTag({fn:Y=>{const roots=islmRoots(rate=>evalVar(compiled,rate,['r'])-Y,Math.max(1,r*4,CONFIG.Pmax*4),Y);return roots.length===1?roots[0]:NaN;}},'rec',{expr,v:'r',axis:'y'});}
    }else if(affineR&&math.simplify(affineR.a).toString()!=='0'){
      const expr=macroSimplify('('+CalcNumber.expression(c.Ms/c.P)+'-('+affineR.b+'))/('+affineR.a+')');lmCurve=macroCurveY(expr,['Y']);lmRecord={name:'LM',color:COL.S,lhs:'r',expr};
    }else{
      lmCurve={fn:Y=>{const roots=islmRoots(r=>md(Y,r)-c.Ms/c.P,Math.max(1,CONFIG.Pmax*4),c.Ms/c.P);return roots.length===1?roots[0]:NaN;}};lmRecord={name:'LM',color:COL.S,note:'Денежный рынок построен численно по равенству спроса и предложения денег.'};
    }
    if(lmCurve.error)throw Error(lmCurve.error);
    const derivative=(v)=>{try{return Number(math.derivative(mdExpr,v).evaluate({...scope,Y,r}));}catch(e){const d=1e-4*Math.max(1,v==='Y'?Y:r);return v==='Y'?(md(Y+d,r)-md(Y-d,r))/(2*d):(md(Y,r+d)-md(Y,r-d))/(2*d);}};
    const mdY=derivative('Y'),mdR=derivative('r'),den=h*mdR-c.d*mdY,kG=Math.abs(den)>1e-12?mdR/den:null,kT=kG==null?null:-c.b*kG;
    return{config:c,A,h,eq,yAt,md,mdExpr,isCurve,lmCurve,isRecord,lmRecord,kG,kT,kHold:1/h,kTHold:-c.b/h};
  }catch(e){return{error:/^[А-ЯЁ]/.test(e.message)?e.message:mathErrorRu(e.message)};}
}
let _islmCache=null;
function islmScenario(P){
  const config={...islmDefaults(),...(P.params||{})},shock=P.shock||null,key=JSON.stringify([config,shock,!!P.holdRate,STATE.params]);if(_islmCache?.key===key)return _islmCache.result;
  const before=islmSolve(config);if(before.error)return before;
  const delta={G:0,T:0,Ms:0};if(shock)for(const k of Object.keys(delta)){delta[k]=islmScalar(shock[k]??0);if(!Number.isFinite(delta[k]))return{error:'Нужно число для Δ'+k+'.'};}
  const afterConfig={...before.config,G:before.config.G+delta.G,T:before.config.T+delta.T,Ms:before.config.Ms+delta.Ms};
  const after=islmSolve(afterConfig);
  // Вытеснение сравнивает бюджетный шок с неизменным количеством денег.
  // Одновременное увеличение Ms может компенсировать его в текущем сценарии.
  const constantMoney=delta.Ms===0?after:islmSolve({...afterConfig,Ms:before.config.Ms});
  const fixedY=(before.config.a-before.config.b*afterConfig.T+before.config.I0+afterConfig.G+before.config.Xn-before.config.d*before.eq.P)/before.h;
  const holdEq={Q:fixedY,P:before.eq.P},requiredMs=before.config.P*before.md(fixedY,before.eq.P);
  if(P.holdRate&&(fixedY<0||!Number.isFinite(requiredMs)||requiredMs<0))return{error:'При исходной ставке новое равновесие с неотрицательными выпуском и деньгами невозможно.'};
  if(after.error&&!P.holdRate)return after;
  // При фиксированной ставке независимый ΔMs уступает политике ЦБ: сколько
  // денег нужно на самом деле, определяется денежным спросом при новом Y.
  const fixed=P.holdRate?islmSolve({...afterConfig,Ms:requiredMs},holdEq):null;
  if(fixed?.error)return fixed;
  const active=P.holdRate?fixed:after,eq=P.holdRate?holdEq:after.eq;
  const result={base:before.eq,eq,holdEq,normalEq:after.eq||null,requiredMs,requiredDeltaMs:requiredMs-before.config.Ms,
    crowdingY:constantMoney.eq?holdEq.Q-constantMoney.eq.Q:null,crowdingI:constantMoney.eq?before.config.d*(constantMoney.eq.P-before.eq.P):null,changes:{Y:eq.Q-before.eq.Q,r:eq.P-before.eq.P,I:-before.config.d*(eq.P-before.eq.P)},
    kG:before.kG,kT:before.kT,kHold:before.kHold,kTHold:before.kTHold,shock:!!shock,holdRate:!!P.holdRate,before,after:active};
  _islmCache={key,result};return result;
}
function recomputeIslmParameters(){
  renderIslmControls();const r=islmScenario(macroP());STATE.islmResult=r;
  if(r.error){STATE.macroErr=r.error;return;}
  const current=r.after,initial=r.before,hold=texTag({fn:()=>r.base.P},'rec',{expr:CalcNumber.expression(r.base.P),v:'Y'});
  STATE.macroRes={kind:'islm',parameterized:true,eq:r.eq,base:r.base,curves:[[r.shock?"IS′":'IS',current.isCurve,COL.D],[r.holdRate?'LM (ЦБ)':r.shock?"LM′":'LM',r.holdRate?hold:current.lmCurve,COL.S]],vertical:[],extra:r.shock?[['IS',initial.isCurve,COL.D],['LM',initial.lmCurve,COL.S]]:[]};
  applyAutoRanges(niceMax(Math.max(r.base.Q,r.eq.Q,r.holdEq.Q,1)*1.5),niceMax(Math.max(r.base.P,r.eq.P,1)*2));
}
function islmPanelHtml(r){
  const stat=(name,v)=>'<div class="stat"><span>'+name+'</span><b>'+(v==null?'Не определён':fmt(v))+'</b></div>';
  let html=stat('Равновесный выпуск Y',r.eq.Q)+stat('Равновесная ставка r',r.eq.P);
  html+=stat('Мультипликатор G в IS–LM',r.kG)+stat('Мультипликатор T в IS–LM',r.kT)+stat('Мультипликатор G при постоянной r',r.kHold)+stat('Мультипликатор T при постоянной r',r.kTHold);
  if(r.shock){html+=stat('Исходный выпуск Y₀',r.base.Q)+stat('Исходная ставка r₀',r.base.P)+stat('Изменение выпуска ΔY',r.changes.Y)+stat('Изменение ставки Δr',r.changes.r)+stat('Изменение инвестиций ΔI',r.changes.I)+stat('Выпуск при постоянной r',r.holdEq.Q)+stat('Вытеснение выпуска при неизменной Ms',r.crowdingY)+stat('Вытеснение инвестиций при неизменной Ms',r.crowdingI);}
  if(r.holdRate||r.shock)html+=stat('Изменение Ms для сохранения r₀',r.requiredDeltaMs);
  if(r.holdRate)html+='<div class="hint">ЦБ удерживает исходную ставку: предложение денег подстраивается под новый денежный спрос.</div>';
  const records=[r.after.isRecord,r.holdRate?{name:'LM: ЦБ держит ставку',color:COL.S,lhs:'r',expr:CalcNumber.expression(r.base.P)}:r.after.lmRecord];setFinalFunctions(records);return html;
}

function setIslmInput(input){historyMark('Способ ввода IS–LM');macroP().input=input;if(input==='params'&&!macroP().params)macroP().params=islmDefaults();renderIslmControls(true);redrawAll();}
function islmAddShock(){historyMark('Добавить шок');macroP().shock={G:0,T:0,Ms:0};renderIslmControls(true);redrawAll();}
function renderIslmControls(force=false){
  const host=document.getElementById('islm-parameters');if(!host)return;const p=STATE.macro.islm,c={...islmDefaults(),...(p.params||{})},on=p.input==='params';
  document.getElementById('islm-curves').style.display=on?'none':'';host.style.display=on?'':'none';
  document.querySelectorAll('#islm-input-mode button').forEach(b=>b.classList.toggle('active',b.dataset.input===(on?'params':'curves')));
  if(!host.childElementCount){
    host.innerHTML='<div class="hint">$C=a+b(Y-T)$; $I=I_0-dr$.</div><div class="islm-grid" id="islm-goods"></div><div class="field" id="islm-md-field"><label>Спрос на деньги Md/P</label><input type="text" id="islm-md" autocomplete="off"></div><div class="islm-grid" id="islm-money"></div><button type="button" class="btn-sm" id="islm-add-shock">+ шок</button><div id="islm-shock"><div class="islm-shock-head"><b>Шок</b><button type="button" class="btn-sm" id="islm-remove-shock">Удалить шок</button></div><div class="islm-grid" id="islm-deltas"></div></div><label class="chk"><input type="checkbox" id="islm-hold-rate">ЦБ держит ставку</label>';
    const fields=[['a','Автономное потребление a','goods'],['b','Склонность к потреблению b','goods'],['I0','Автономные инвестиции I₀','goods'],['d','Реакция инвестиций d','goods'],['G','Госзакупки G','goods'],['T','Налоги T','goods'],['Xn','Чистый экспорт Xn','goods'],['Ms','Предложение денег Ms','money'],['P','Уровень цен P','money']];
    for(const[key,label,place]of fields){const f=document.createElement('div');f.className='field';f.innerHTML='<label>'+label+'</label><input type="number" step="any" id="islm-'+key+'">';document.getElementById('islm-'+place).appendChild(f);const e=f.querySelector('input');e.value=c[key];e.addEventListener('change',()=>{historyMark('Параметр IS–LM');macroP().params={...islmDefaults(),...(macroP().params||{}),[key]:e.value};redrawAll();});}
    const md=document.getElementById('islm-md');md.value=c.md;equipFormulaField(md.id,'MACRO');liveFormula([md],()=>{macroP().params={...islmDefaults(),...(macroP().params||{}),md:md.value};redrawAll();});wrapFieldInCard(md.closest('.field'),{input:md.id,sym:'M_d/P',name:'Спрос на реальные деньги',prefix:'M_d/P =',col:'S'});
    for(const key of['G','T','Ms']){const f=document.createElement('div');f.className='field';f.innerHTML='<label>Δ'+key+'</label><input type="number" step="any" id="islm-delta-'+key+'">';document.getElementById('islm-deltas').appendChild(f);f.querySelector('input').addEventListener('change',e=>{historyMark('Шок IS–LM');macroP().shock={...(macroP().shock||{G:0,T:0,Ms:0}),[key]:e.target.value};redrawAll();});}
    document.getElementById('islm-add-shock').addEventListener('click',islmAddShock);
    document.getElementById('islm-remove-shock').addEventListener('click',()=>{historyMark('Удалить шок');delete macroP().shock;renderIslmControls(true);redrawAll();});
    document.getElementById('islm-hold-rate').addEventListener('change',e=>{historyMark('Политика ЦБ');macroP().holdRate=e.target.checked;redrawAll();});
  }
  for(const key of['a','b','I0','d','G','T','Xn','Ms','P']){const e=document.getElementById('islm-'+key);if(document.activeElement!==e)e.value=c[key];if(e._editable?._repaint)e._editable._repaint();}
  for(const key of['G','T','Ms']){const e=document.getElementById('islm-delta-'+key);if(document.activeElement!==e)e.value=p.shock?.[key]??0;if(e._editable?._repaint)e._editable._repaint();}
  document.getElementById('islm-add-shock').style.display=p.shock?'none':'';document.getElementById('islm-shock').style.display=p.shock?'':'none';document.getElementById('islm-hold-rate').checked=!!p.holdRate;
  const ms=document.getElementById('islm-delta-Ms');ms.closest('.field').style.display=p.holdRate?'none':'';
  if(force){const md=document.getElementById('islm-md');if(md.value!==c.md)setFormulaFieldQuiet(md,c.md);}
}
