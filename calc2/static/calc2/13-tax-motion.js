/* Интерактивный налог и MC: математика и геометрия сейчас, точная запись отдельно.
   Это состояние представления, оно не входит в STATE/историю/ссылку. */
const TaxMotion = (() => {
  const workerSource = document.currentScript.dataset.worker;
  const numbersSource = document.currentScript.dataset.numbers;
  const motionPreference=matchMedia('(prefers-reduced-motion: reduce)');
  const loaderFrames=Array.from({length:181},(_,i)=>{
    const phase=i/180,air=phase<=1/3,u=air?phase*3:(phase-1/3)*1.5;
    const travel=(1-Math.cos(Math.PI*u))/2;
    const x=air?24*(1-travel):24*travel,y=(air?-11:2.2)*Math.sin(Math.PI*u)**2;
    return {offset:phase,transform:`translate(${x.toFixed(5)}px,${y.toFixed(5)}px)`};
  });
  let pending=false, drawing=false, finishing=false, held=false, generation=0;
  let timer, worker=null, sequence=0, loadingSince=0;
  let loaderAnimations=[];
  const jobs=new Map();
  let planeAnimation=null, planeGroup=null, left=null, viewKey='';
  const reduced=()=>motionPreference.matches;
  const supported=()=>STATE.mode==='market' && (['mono','mono-nat','mono-d1'].includes(STATE.sceneKey) || (STATE.market!=='monopoly'
    && ['taxes','tax','tax-adv'].includes(STATE.sceneKey)
    && ['tax','subsidy'].includes(STATE.intervType)));

  function prepare(values) {
    if (!values.length) return Promise.resolve();
    if (!worker) {
      const numbers=new URL(numbersSource,document.baseURI).href;
      const url=new URL(workerSource,document.baseURI);
      url.searchParams.set('numbers',numbers);
      worker=new Worker(url);
      worker.onmessage=({data})=>{
        const job=jobs.get(data.id); if(!job)return;
        jobs.delete(data.id);
        if(data.error)job.reject(new Error(data.error));
        else { CalcNumber.seed(data.records); job.resolve(); }
      };
      worker.onerror=error=>{
        jobs.forEach(job=>job.reject(error));jobs.clear();
        worker.terminate();worker=null;
      };
    }
    return new Promise((resolve,reject)=>{
      const id=++sequence;jobs.set(id,{resolve,reject});worker.postMessage({id,values});
    });
  }
  function indicators(on) {
    // buildAnswer может заменить узлы раньше завершения ожидания. Храним
    // сами анимации, чтобы бесконечные эффекты не удерживали удалённый DOM.
    loaderAnimations.forEach(a=>a.cancel());loaderAnimations=[];
    document.body.classList.toggle('tax-values-pending',on);
    const panel=document.getElementById('params-panel');
    if(panel)panel.setAttribute('aria-busy',String(on));
    document.querySelectorAll('.calc-value-loader').forEach(el=>{
      el.getAnimations({subtree:true}).forEach(a=>a.cancel());el.remove();
    });
    if(on)document.querySelectorAll('#ans-hero .ans-val, #ans-strip b').forEach(el=>{
      const loader=document.createElement('span');loader.className='calc-value-loader';
      loader.setAttribute('aria-hidden','true');
      for(let i=0;i<3;i++){
        const dot=document.createElement('i');loader.appendChild(dot);
        if(!reduced())loaderAnimations.push(dot.animate(loaderFrames,{duration:1800,
          delay:-600*i-(performance.now()-loadingSince),iterations:Infinity,easing:'linear'}));
      }
      el.appendChild(loader);
    });
  }
  function stopPlane() {
    if(!planeAnimation)return;
    const matrix=new DOMMatrix(getComputedStyle(planeGroup).transform);
    left=matrix.a*CONFIG.margin.left+matrix.e;
    CONFIG.margin.left=left;
    planeAnimation.cancel();planeAnimation=null;
    if(planeGroup.isConnected)planeGroup.replaceWith(...planeGroup.childNodes);
    planeGroup=null;
  }
  function cancel() {
    generation++;clearTimeout(timer);stopPlane();
    pending=false;held=false;indicators(false);
    document.body.classList.remove('tax-values-loading');
  }
  function margin(base) {
    const key=JSON.stringify([STATE.sceneKey,W,labelScale(),STATE.intervType,STATE.taxForm,STATE.taxSide,
      STATE.taxSecond&&[STATE.taxSecond.type,STATE.taxSecond.form,STATE.taxSecond.side],
      STATE.curves.map(c=>[c.expr,c.srcExpr,c.visible]),CONFIG.Qmin,CONFIG.Qmax,CONFIG.Pmin,CONFIG.Pmax]);
    if(viewKey!==key){viewKey=key;left=null;}
    return Math.max(base,left||0);
  }
  function reserve(width) { left=Math.max(left||0,width); }
  function hold() {
    if(!supported())return;
    held=true;generation++;clearTimeout(timer);
    if(planeAnimation)planeAnimation.pause();
  }
  function release() { if(!held)return;held=false;schedule(); }
  function bindInput(input) {
    input.addEventListener('pointerdown',hold);
    input.addEventListener('keydown',event=>{
      if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(event.key))hold();
    });
    input.addEventListener('keyup',release);input.addEventListener('blur',release);
  }
  function schedule() {
    clearTimeout(timer);
    if(pending&&!held)timer=setTimeout(settle,120);
  }
  function render(updateControls) {
    generation++;clearTimeout(timer);stopPlane();
    if(!pending){
      pending=true;loadingSince=performance.now();indicators(true);
      document.body.classList.add('tax-values-loading');
    }
    drawing=true;
    try {
      CalcNumber.collect(()=>{
        if(updateControls)updateControls();
        bumpModelSpan();redrawScene();drawOverlays();applyLabelSize();
        typesetChartLabels();applyLabelInk();markServiceNodes();
        if(typeof selfCanvas==='function')selfCanvas();
      });
    } finally {drawing=false;}
    if(typeof historyAfterRedraw==='function')historyAfterRedraw();
    schedule();
  }
  function complete() {
    pending=false;
    indicators(false);document.body.classList.remove('tax-values-loading');
    const hero=document.getElementById('ans-hero');
    if(hero&&!reduced())hero.animate([{opacity:.4},{opacity:1}],{duration:120});
  }
  function movePlane(from,to) {
    if(reduced()||Math.abs(to-from)<1){complete();return;}
    const node=svg.node(),group=document.createElementNS(node.namespaceURI,'g');
    group.setAttribute('data-tax-plane-motion','');
    [...node.children].filter(el=>el.tagName.toLowerCase()!=='defs').forEach(el=>group.append(el));
    node.append(group);planeGroup=group;
    const scale=(W-CONFIG.margin.right-from)/(W-CONFIG.margin.right-to);
    const offset=from-scale*to;
    const animation=group.animate([
      {transform:`matrix(${scale},0,0,1,${offset},0)`},{transform:'matrix(1,0,0,1,0,0)'}
    ],{duration:240,easing:'cubic-bezier(.23,1,.32,1)'});
    planeAnimation=animation;
    animation.onfinish=()=>{
      if(planeAnimation!==animation)return;
      group.replaceWith(...group.childNodes);planeAnimation=null;planeGroup=null;complete();
    };
  }
  async function settle() {
    if(!pending||held)return;
    stopPlane();
    const current= generation, from=CONFIG.margin.left;
    finishing=true;
    try {
      // Сначала собираем ВСЕ потребители чисел, включая открытый «Ответ».
      // Неизвестные записи не запускают PSLQ в браузерном кадре.
      for(let pass=0;pass<5;pass++){
        const missing=CalcNumber.collect(()=>{
          redrawAll();buildAnswer();
          const label=document.getElementById('tax-val');if(label)label.textContent=fmt(STATE.tax);
        });
        indicators(true);
        if(!missing.length)break;
        finishing=false;await prepare(missing);
        if(current!==generation||!pending||held)return;
        finishing=true;
        if(pass===4)throw new Error('Не удалось подготовить точные значения');
      }
      finishing=false;await document.fonts.ready;
      if(current!==generation||!pending||held)return;
      finishing=true;
      // К моменту замера все координаты уже точные. Старое поле не задаёт
      // постоянного резерва: после жеста допускается и плавное сужение.
      left=null;_coordMarginLeft=0;fitMargins();
      const base=CONFIG.margin.left;
      let width=0;
      svg.node().querySelectorAll('text.coord-num').forEach(el=>{
        if(el.getAttribute('text-anchor')!=='middle')width=Math.max(width,el.getBoundingClientRect().width);
      });
      const limit=Math.max(0,W-Math.min(160,W*.4));
      const target=Math.max(base,Math.min(limit,Math.ceil(width)+18));
      left=Math.abs(target-from)<=8?Math.max(from,target):target;
      redrawAll();buildAnswer();indicators(true);
      movePlane(from,CONFIG.margin.left);
    } catch(error) {
      // Ошибка рабочего потока не превращается в бесконечный индикатор.
      // Точный штатный путь остаётся доступен, без изменения формата чисел.
      if(current===generation){cancel();redrawAll();buildAnswer();}
      console.error('Точная запись чисел:',error);
    } finally {finishing=false;}
  }
  window.addEventListener('pointerup',release);
  window.addEventListener('pointercancel',release);
  window.addEventListener('blur',release);
  motionPreference.addEventListener('change',()=>{
    if(pending)indicators(true);
    if(reduced()&&planeAnimation)planeAnimation.finish();
  });
  return {supported,render,hold,release,cancel,margin,reserve,bindInput,
    get pending(){return pending;},get drawing(){return drawing;},get finishing(){return finishing;}};
})();
