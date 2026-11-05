/* Свободная протяжка → удобное число при отпускании. Только жест ввода:
   формулы, точный ввод, восстановление и вычисленные результаты не округляем. */
const InputSnap = (() => {
  let gesture=null, frame=0;
  const keys=new Set(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown']);
  const reduce=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  const range=el=>el instanceof HTMLInputElement&&el.type==='range'&&!!el.closest('.app');
  function step(span) {
    const raw=Math.abs(span)/100;
    if(!(raw>0)||!Number.isFinite(raw))return 1;
    const power=10**Math.floor(Math.log10(raw));
    return [1,2,5,10].reduce((best,n)=>Math.abs(Math.log(raw/(n*power)))<Math.abs(Math.log(raw/(best*power)))?n:best,1)*power;
  }
  function rounded(value,unit,min=-Infinity,max=Infinity) {
    // Сетка от нуля, а не от случайной дробной нижней границы.
    const n=Number((Math.round(value/unit)*unit).toPrecision(14));
    return Math.max(min,Math.min(max,n));
  }
  function exact(sl,value) { sl.step='any';sl.value=value; }
  function dragValue(value) {
    // Три дополнительных разряда внутри конечного шага: при приближении
    // мелкие движения не теряются. Ручной ввод вообще не проходит округление.
    if(!gesture)return value;
    return Number(value.toFixed(Math.min(14,Math.max(3,3-Math.floor(Math.log10(gesture.unit))))));
  }
  function spanFor(sl) {
    let span=+sl.max-(sl.min===''?0:+sl.min);
    const yIds=['open-pw-slider','lr-price-slider','union-wage-slider','labmin-slider','pc-slider','quota-price-slider'];
    const xIds=['quota-slider','open-quota-slider','pl-q-slider','mathx0-slider'];
    const unitTax=(sl.id==='tax-slider'&&taxFormKey()==='unit')||(sl.id==='tax2-slider'&&STATE.taxSecond?.form==='unit');
    if(unitTax||yIds.includes(sl.id)||sl.closest('[data-cid]'))span=Math.min(span,Math.abs(CONFIG.Pmax-CONFIG.Pmin));
    if(xIds.includes(sl.id))span=Math.min(span,Math.abs(CONFIG.Qmax-CONFIG.Qmin));
    return span;
  }
  function cancel() {
    cancelAnimationFrame(frame);frame=0;
    const g=gesture;gesture=null;g?.cancel?.();
    if(g)TaxMotion.release();
  }
  function begin(sl,options={}) {
    cancel();
    if(!sl)return;
    const min=sl.min===''?0:+sl.min,max=sl.max===''?100:+sl.max;
    const get=options.get||(()=>+sl.value);
    const set=options.set||(value=>{exact(sl,value);sl.dispatchEvent(new Event('input',{bubbles:true}));});
    exact(sl,get());
    gesture={sl,get,set,min,max,unit:step(spanFor(sl)),start:get(),scene:STATE.sceneKey,done:options.done,cancel:options.cancel,
      native:!!options.native,keyboard:!!options.keyboard,ending:false};
    TaxMotion.hold();
  }
  function finish(immediate=false) {
    const g=gesture;
    if(!g||g.ending)return;
    const from=g.get(),to=rounded(from,g.unit,g.min,g.max);
    if(from===g.start||Math.abs(to-from)<1e-12){cancel();g.done?.();return;}
    g.ending=true;
    const done=()=>{g.set(to);cancel();g.done?.();if(typeof historyAfterRedraw==='function')historyAfterRedraw();};
    if(immediate||g.keyboard||reduce()){done();return;}
    const start=performance.now();
    const tick=now=>{
      if(gesture!==g)return;
      if(STATE.sceneKey!==g.scene||!g.sl.isConnected){cancel();return;}
      const t=Math.min(1,(now-start)/100);
      if(t===1){done();return;}
      g.set(from+(to-from)*(1-(1-t)**3));
      frame=requestAnimationFrame(tick);
    };
    frame=requestAnimationFrame(tick);
  }
  document.addEventListener('pointerdown',event=>{
    if(range(event.target))begin(event.target,{native:true});else cancel();
  },true);
  window.addEventListener('pointerup',()=>{if(gesture?.native)finish();},true);
  window.addEventListener('pointercancel',()=>finish(true),true);
  window.addEventListener('blur',()=>finish(true));
  document.addEventListener('keydown',event=>{
    const sl=event.target;
    if(!range(sl)||!keys.has(event.key)){if(event.key!=='Shift')cancel();return;}
    event.preventDefault();
    if(gesture?.sl!==sl||!gesture.keyboard)begin(sl,{native:true,keyboard:true});
    const g=gesture,up=['ArrowRight','ArrowUp','PageUp'].includes(event.key);
    const at=g.get()/g.unit,count=event.key.startsWith('Page')?10:1;
    let value=((up?Math.floor(at+1e-10):Math.ceil(at-1e-10))+(up?count:-count))*g.unit;
    if(event.key==='Home')value=g.min;if(event.key==='End')value=g.max;
    g.set(rounded(value,g.unit,g.min,g.max));
  },true);
  document.addEventListener('keyup',event=>{if(keys.has(event.key)&&gesture?.keyboard)finish(true);},true);
  document.addEventListener('focusout',event=>{if(gesture?.native&&gesture.sl===event.target)finish(true);},true);
  return {begin,finish,cancel,exact,step,rounded,dragValue,get active(){return !!gesture;}};
})();
