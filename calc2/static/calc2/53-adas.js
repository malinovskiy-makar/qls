// AD–AS: исходная экономика, шок, короткий и долгий периоды.
function adasValue(v,name){const x=islmScalar(v);if(!Number.isFinite(x))throw Error('Нужно число для '+name+'.');return x;}
function adasOneRoot(f,label,scale=1){const roots=islmRoots(f,1e12,scale).filter(x=>x>=0);if(roots.length!==1)throw Error(roots.length?'Найдено несколько решений: '+label+'.':'Не найдено решение: '+label+'.');return roots[0];}
function adasCompile(expr,v){const compiled=math.parse(expr).compile(),scope=scopeFor(expr,{[v]:1});return x=>{try{const y=compiled.evaluate({...scope,[v]:x});return typeof y==='number'&&Number.isFinite(y)?y:NaN;}catch(e){return NaN;}};}
function adasInverse(expr,v,fn){
  const scope=scopeFor(expr,{[v]:1}),affine=islmAffine(expr,v);
  if(affine){const a=Number(math.evaluate(affine.a,scope)),b=Number(math.evaluate(affine.b,scope));if(a!==0)return y=>(y-b)/a;return null;}
  // A+B/v — наиболее частая AD. Обращаем аналитически, включая асимптоту.
  try{const reciprocal=macroSimplify(islmSubstitute(expr,{[v]:'1/z'})),line=islmAffine(reciprocal,'z');if(line){const a=Number(math.evaluate(line.a,scope)),b=Number(math.evaluate(line.b,scope));if(a!==0)return y=>a/(y-b);}}catch(e){}
  const cache=new Map();return y=>{if(cache.has(y))return cache.get(y);const roots=islmRoots(x=>fn(x)-y,1e12,Math.max(1,Math.abs(y))),x=roots.length===1?roots[0]:NaN;if(cache.size>3000)cache.clear();cache.set(y,x);return x;};
}
function adasCurve(raw,name,color){
  const split=splitCurveLhs(raw);if(split.error)throw Error(split.error);
  let expr=prepExpr(split.rhs),form=split.form;
  if(!form)form=exprHasLetter(expr,'Pp')&&!exprHasLetter(expr,'Yy')?'QP':'PQ';
  const v=form==='QP'?'P':'Y';expr=math.parse(expr).transform(n=>n.isSymbolNode&&((v==='P'&&n.name==='p')||(v==='Y'&&['x','y'].includes(n.name)))?new math.SymbolNode(v):n).toString();
  const fn=adasCompile(expr,v),inverse=adasInverse(expr,v,fn),pAtY=form==='PQ'?fn:inverse,yAtP=form==='QP'?fn:inverse;
  let c;if(form==='QP'&&!inverse)c=makeVerticalCurve(fn(1));else c=texTag({fn:Y=>pAtY(Y)},'rec',{expr,v,axis:form==='QP'?'y':undefined});
  return Object.assign(c,{pAtY,yAtP,expr,form,record:{name,color,lhs:form==='QP'?'Y':'P',expr}});
}
function adasIntersection(a,b){
  let variable='Y',f,point;
  if(a.yAtP&&b.yAtP){variable='P';f=P=>{const ya=a.yAtP(P),yb=b.yAtP(P);return P>0&&ya>=0&&yb>=0?ya-yb:NaN;};point=P=>({Q:a.yAtP(P),P});}
  else if(a.yAtP||b.yAtP){variable='P';const inv=a.yAtP?a:b,direct=a.yAtP?b:a;f=P=>{const Y=inv.yAtP(P);return P>0&&Y>=0?direct.pAtY(Y)-P:NaN;};point=P=>({Q:inv.yAtP(P),P});}
  else{f=Y=>{const pa=a.pAtY(Y),pb=b.pAtY(Y);return pa>0&&pb>0?pa-pb:NaN;};point=Y=>({Q:Y,P:a.pAtY(Y)});}
  return point(adasOneRoot(f,'пересечение AD и SRAS по '+variable,1000));
}
function adasDemand(c,name='AD'){
  if(c.adMode==='mv'){const M=adasValue(c.M??256,'M'),V=adasValue(c.V??1,'V');if(M<=0||V<=0)throw Error('M и V должны быть положительными.');return adasCurve('Y='+CalcNumber.expression(M*V)+'/P',name,COL.D);}
  return adasCurve(c.ad,name,COL.D);
}
function adasLabor(c,ad){
  const production=prepExpr(c.production||'16*sqrt(L)'),supply=prepExpr(c.laborSupply||'8*w/P'),mplExpr=math.derivative(production,'L').toString();
  const f=adasCompile(production,'L'),mpl=adasCompile(mplExpr,'L');
  const lsExpr=macroSimplify(islmSubstitute(supply,{w:'z',P:1})),ls=adasCompile(lsExpr,'z');
  const L=adasOneRoot(L=>L>0?ls(mpl(L))-L:NaN,'равновесие рынка труда',100),Y=f(L),realW=mpl(L),P=ad.pAtY?.(Y),nominalW=realW*P;
  if(!(Y>0&&realW>0&&P>0&&Number.isFinite(P)))throw Error('Не удалось найти положительное исходное равновесие рынка труда и AD.');
  if(!(mpl(L*1.001)<realW))throw Error('Для SRAS из рынка труда нужна убывающая предельная производительность труда.');
  const toL=adasInverse(production,'L',f);
  if(!toL)throw Error('Выпуск должен зависеть от труда.');
  let power=null;
  // L>0: sqrt(L) можно записать степенью. Без этого Math.js сохраняет
  // sqrt(L)^2 и не распознаёт даже постоянную эластичность 16sqrt(L).
  try{const algebra=math.parse(production).transform(n=>n.isFunctionNode&&n.name==='sqrt'?math.parse('('+n.args[0].toString()+')^(1/2)'):n).toString();
    const elasticity=macroSimplify('L*('+math.derivative(algebra,'L').toString()+')/('+algebra+')');if(!math.parse(elasticity).filter(n=>n.isSymbolNode&&n.name==='L').length){const b=adasCompile(elasticity,'L')(1),a=f(1);if(a>0&&b>0&&b<1)power={a,b};}}catch(e){}
  const curve=(w,name='SRAS')=>{
    if(!(w>0))throw Error('Номинальная зарплата должна быть положительной.');
    if(power){const{a,b}=power,expr=macroSimplify(CalcNumber.expression(a)+'*('+CalcNumber.expression(a*b/w)+'*P)^('+CalcNumber.expression(b/(1-b))+')');return adasCurve('Y='+expr,name,COL.S);}
    const yAtP=P=>{if(!(P>0))return NaN;const roots=islmRoots(L=>L>0?mpl(L)-w/P:NaN,1e12,Math.max(1,w/P));return roots.length===1?f(roots[0]):NaN;},pAtY=Y=>w/mpl(toL(Y));
    return{fn:pAtY,pAtY,yAtP,record:{name,color:COL.S,note:'SRAS построена численно из MPL = w/P при постоянной номинальной зарплате.'}};
  };
  return{base:{L,realW,nominalW},Ystar:Y,baseP:P,curve,at:(eq,w)=>({L:toL(eq.Q),realW:w/eq.P,nominalW:w})};
}
let _adasCache=null;
function adasScenario(c){
  const key=JSON.stringify([c,STATE.params]);if(_adasCache?.key===key)return _adasCache.result;
  try{
    const ad=adasDemand(c),laborEngine=c.srasMode==='labor'?adasLabor(c,ad):null;
    const sras=laborEngine?laborEngine.curve(laborEngine.base.nominalW):adasCurve(c.sras,'SRAS',COL.S),base=adasIntersection(ad,sras);
    const Ystar=laborEngine?laborEngine.Ystar:c.lrasMode==='initial'?base.Q:adasValue(c.lras,'Y*');if(!(Ystar>0))throw Error('Потенциальный выпуск должен быть положительным.');
    const shock=c.shock||null,adAfter=shock?.kind==='ad'?adasDemand({...c,...shock},'AD′'):ad;
    let srasAfter=sras,srW=laborEngine?.base.nominalW;
    if(shock?.kind==='sras'){
      if(laborEngine){srW=adasValue(shock.w??laborEngine.base.nominalW,'новой w');srasAfter=laborEngine.curve(srW,'SRAS′');}
      else srasAfter=adasCurve(shock.sras,'SRAS′',COL.S);
    }
    const sr=shock?adasIntersection(adAfter,srasAfter):base,lr={Q:Ystar,P:adAfter.pAtY?.(Ystar)};
    if(!(lr.P>0&&Number.isFinite(lr.P)))throw Error('Долгосрочное равновесие с положительной ценой не найдено.');
    let adjusted=null;
    if(shock){
      if(laborEngine)adjusted=laborEngine.curve(laborEngine.base.realW*lr.P,'SRAS (LR)');
      else if(isVertical(srasAfter))adjusted=srasAfter;
      else{const delta=lr.P-srasAfter.pAtY(Ystar);if(!Number.isFinite(delta))throw Error('Не удалось сдвинуть SRAS через долгосрочное равновесие.');
        const expr=srasAfter.form==='QP'?islmSubstitute(srasAfter.expr,{P:'(P-('+CalcNumber.expression(delta)+'))'}):'('+srasAfter.expr+')+('+CalcNumber.expression(delta)+')';
        adjusted=adasCurve((srasAfter.form==='QP'?'Y=':'P=')+macroSimplify(expr),'SRAS (LR)',COL.S);
      }
    }
    const change=e=>({Y:base.Q===0?null:100*(e.Q-base.Q)/base.Q,P:100*(e.P-base.P)/base.P});
    const labor=laborEngine?{base:laborEngine.base,sr:laborEngine.at(sr,srW),lr:laborEngine.at(lr,laborEngine.base.realW*lr.P)}:null;
    const records=[ad.record,sras.record,{name:'LRAS',color:COL.MC,lhs:'Y',expr:CalcNumber.expression(Ystar)}];
    if(adAfter!==ad)records.push(adAfter.record);if(srasAfter!==sras)records.push(srasAfter.record);if(adjusted)records.push(adjusted.record);
    const result={base,sr,lr,Ystar,srChange:change(sr),lrChange:change(lr),gapPct:100*(sr.Q-Ystar)/Ystar,labor,ad,sras,adAfter,srasAfter,adjusted,records,shock:!!shock};
    _adasCache={key,result};return result;
  }catch(e){return{error:/^[А-ЯЁ]/.test(e.message)?e.message:mathErrorRu(e.message)};}
}
function recomputeAdasAdvanced(){
  const r=adasScenario(macroP());STATE.adasResult=r;if(r.error){STATE.macroErr=r.error;return;}
  const curves=[['AD',r.ad,COL.D],['SRAS',r.sras,COL.S]],extra=[];
  if(r.adAfter!==r.ad)curves.push(['AD′',r.adAfter,COL.D]);if(r.srasAfter!==r.sras)curves.push(['SRAS′',r.srasAfter,COL.S]);if(r.adjusted)extra.push(['SRAS (LR)',r.adjusted,COL.S]);
  STATE.macroRes={kind:'adas',advanced:true,curves,extra,vertical:[['LRAS',makeVerticalCurve(r.Ystar),COL.MC]],eq:r.sr,lr:r.lr,gap:r.sr.Q-r.Ystar,Ystar:r.Ystar};
  applyAutoRanges(niceMax(Math.max(r.base.Q,r.sr.Q,r.lr.Q,1)*1.4),niceMax(Math.max(r.base.P,r.sr.P,r.lr.P,1)*1.4));
}
function adasPanelHtml(r){
  const stat=(name,v,pct=false)=>'<div class="stat"><span>'+name+'</span><b>'+(v==null?'Не определено':pct?CalcNumber.format(v,{percent:true}):fmt(v))+'</b></div>';
  let html=stat('Краткосрочный выпуск Y₁',r.sr.Q)+stat('Краткосрочный уровень цен P₁',r.sr.P)+stat('Потенциальный выпуск Y*',r.Ystar)+stat('Разрыв выпуска',r.gapPct,true);
  if(r.shock)html+=stat('Исходный выпуск Y₀',r.base.Q)+stat('Исходный уровень цен P₀',r.base.P)+stat('SR: изменение выпуска',r.srChange.Y,true)+stat('SR: инфляция',r.srChange.P,true)+stat('Долгосрочный выпуск Y₂',r.lr.Q)+stat('Долгосрочный уровень цен P₂',r.lr.P)+stat('LR: изменение выпуска',r.lrChange.Y,true)+stat('LR: инфляция',r.lrChange.P,true);
  if(r.labor)for(const[k,label]of[['base','Исходно'],['sr','SR'],['lr','LR']]){const l=r.labor[k];html+=stat(label+': занятость L',l.L)+stat(label+': реальная зарплата w/P',l.realW)+stat(label+': номинальная зарплата w',l.nominalW);}
  setFinalFunctions(r.records);return html;
}
function adasAdvanced(c){return c.adMode==='mv'||c.srasMode==='labor'||c.lrasMode==='initial'||!!c.shock;}
function setAdasMode(key,value){historyMark('Способ ввода AD–AS');macroP()[key]=value;renderAdasControls(true);redrawAll();}
function adasAddShock(){historyMark('Добавить шок AD–AS');const c=macroP();c.shock={kind:'ad',ad:c.ad,sras:c.sras,M:c.M??256,V:c.V??1,w:STATE.adasResult?.labor?.base?.nominalW??1};renderAdasControls(true);redrawAll();}
function renderAdasControls(force=false){
  const root=document.getElementById('macro-pane-adas');if(!root)return;const c=STATE.macro.adas;
  const values={M:c.M??256,V:c.V??1,production:c.production||'16*sqrt(L)',laborSupply:c.laborSupply||'8*w/P'};
  if(!root._advancedReady){
    root._advancedReady=true;
    const seg=(host,id,key,items)=>{const e=document.createElement('div');e.className='seg adas-seg';e.id=id;e.innerHTML=items.map(([v,label])=>'<button type="button" class="seg-btn" data-value="'+v+'">'+label+'</button>').join('');document.getElementById(host).appendChild(e);e.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>setAdasMode(key,b.dataset.value)));};
    seg('adas-ad-mode','adas-ad-seg','adMode',[['formula','Формула AD'],['mv','Из MV = PY']]);
    seg('adas-sras-mode','adas-sras-seg','srasMode',[['formula','Формула SRAS'],['labor','Из рынка труда']]);
    seg('adas-lras-mode','adas-lras-seg','lrasMode',[['number','Задать Y*'],['initial','Изначально LR']]);
    const number=(host,key,label,shock=false)=>{const f=document.createElement('div');f.className='field';f.innerHTML='<label>'+label+'</label><input type="number" step="any" id="adas-'+(shock?'shock-':'')+key+'">';document.getElementById(host).appendChild(f);const e=f.querySelector('input');e.addEventListener('change',()=>{historyMark('Параметр AD–AS');if(shock)macroP().shock={...(macroP().shock||{kind:'ad'}),[key]:e.value};else macroP()[key]=e.value;redrawAll();});};
    number('adas-mv','M','Количество денег M');number('adas-mv','V','Скорость обращения V');
    const formula=(host,key,label,prefix,color,shock=false)=>{const id='adas-'+(shock?'shock-':'')+key,f=document.createElement('div');f.className='field';f.innerHTML='<label>'+label+'</label><input type="text" id="'+id+'" autocomplete="off">';document.getElementById(host).appendChild(f);const e=f.querySelector('input');e.value=shock?(c.shock?.[key]??c[key]??''):values[key];equipFormulaField(id,'MACRO');liveFormula([e],()=>{if(shock)macroP().shock={...(macroP().shock||{kind:'ad'}),[key]:e.value};else macroP()[key]=e.value;redrawAll();});wrapFieldInCard(f,{input:id,sym:prefix.replace(' =',''),name:label,prefix:shock?()=>formPrefix(id,'Y'):prefix+' =',col:color});};
    formula('adas-labor','production','Производственная функция','Y(L)','S');formula('adas-labor','laborSupply','Предложение труда','L_s','MC');
    document.getElementById('adas-shock').innerHTML='<div class="islm-shock-head"><b>Шок</b><button type="button" class="btn-sm" id="adas-remove-shock">Удалить шок</button></div><div class="seg adas-seg" id="adas-shock-kind"><button type="button" class="seg-btn" data-kind="ad">Спрос AD′</button><button type="button" class="seg-btn" data-kind="sras">Предложение SRAS′</button></div><div id="adas-shock-ad-wrap"></div><div id="adas-shock-mv" class="islm-grid"></div><div id="adas-shock-sras-wrap"></div><div id="adas-shock-w-wrap"></div>';
    formula('adas-shock-ad-wrap','ad','Новый совокупный спрос','AD′','D',true);formula('adas-shock-sras-wrap','sras','Новое предложение','SRAS′','S',true);number('adas-shock-mv','M','Новое M',true);number('adas-shock-mv','V','Новое V',true);number('adas-shock-w-wrap','w','Новая номинальная зарплата w',true);
    document.getElementById('adas-add-shock').addEventListener('click',adasAddShock);document.getElementById('adas-remove-shock').addEventListener('click',()=>{historyMark('Удалить шок AD–AS');delete macroP().shock;renderAdasControls(true);redrawAll();});
    document.querySelectorAll('#adas-shock-kind button').forEach(b=>b.addEventListener('click',()=>{historyMark('Вид шока AD–AS');macroP().shock.kind=b.dataset.kind;renderAdasControls(true);redrawAll();}));
  }
  const show=(id,on)=>{document.getElementById(id).style.display=on?'':'none';},labor=c.srasMode==='labor',mv=c.adMode==='mv',srasShock=c.shock?.kind==='sras';
  show('adas-ad-formula',!mv);show('adas-mv',mv);show('adas-sras-formula',!labor);show('adas-labor',labor);show('adas-lras-number',!labor&&c.lrasMode!=='initial');show('adas-lras-mode',!labor);show('adas-lras-auto',labor);
  show('adas-add-shock',!c.shock);show('adas-shock',!!c.shock);show('adas-shock-ad-wrap',!srasShock&&!mv);show('adas-shock-mv',!srasShock&&mv);show('adas-shock-sras-wrap',srasShock&&!labor);show('adas-shock-w-wrap',srasShock&&labor);
  for(const[key,defaultValue]of[['adMode','formula'],['srasMode','formula'],['lrasMode','number']]){const id=key.replace('Mode','');document.querySelectorAll('#adas-'+id+'-seg button').forEach(b=>b.classList.toggle('active',b.dataset.value===(c[key]||defaultValue)));}
  document.querySelectorAll('#adas-shock-kind button').forEach(b=>b.classList.toggle('active',b.dataset.kind===(c.shock?.kind||'ad')));
  for(const[key,v]of Object.entries({...values,'shock-M':c.shock?.M??values.M,'shock-V':c.shock?.V??values.V,'shock-w':c.shock?.w??1})){
    const e=document.getElementById('adas-'+key);if(e.type==='number'){if(document.activeElement!==e)e.value=v;e._editable?._repaint?.();}else if(force&&e.value!==String(v))setFormulaFieldQuiet(e,String(v));
  }
  if(force)for(const key of['ad','sras']){const e=document.getElementById('adas-shock-'+key),v=c.shock?.[key]??c[key];if(e.value!==String(v))setFormulaFieldQuiet(e,String(v));}
}
