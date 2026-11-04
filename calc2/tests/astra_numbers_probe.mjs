import * as pw from 'playwright';
import {parseShown,shownChangeEquivalent,installShownReader,readShownText} from './parse_shown.mjs';
import {keepAnswerOpen} from './answer_open.mjs';
let total=0,bad=0;
const check=(name,ok,detail)=>{total++;if(!ok)bad++;console.log((ok?'OK ':'FAIL ')+name+(!ok?' '+JSON.stringify(detail):''));};
const noSpace=s=>s.replace(/\s/g,'');
const cases=[
  [.625,'0,625'],[100/3,'100/3'],[171/64,'171/64'],[1/7,'1/7'],
  [5*Math.sqrt(2),'5√2'],[2+Math.sqrt(21)/3,'2 + √21/3'],[Math.cbrt(10),'≈ 2,154'],[-100/3,'−100/3'],[1332,'1 332']
];
for(const [v,s] of cases)check('parseShown '+s,Math.abs(parseShown(s)-v)<(s.includes('≈')?.0005:1e-9));
check('parseShown точный процент до ≈',parseShown('2675/16 % ≈ 167,19 %')===167.1875);
check('изменение сверяется по обоим слагаемым',shownChangeEquivalent('100/3 − 1/3','33,33 − 0,33')&&!shownChangeEquivalent('0 + 40','30 + 10'));
for(const s of ['','foo','1/0','2+','1;2','sqrt(-1)'])check('parseShown отвергает '+s,Number.isNaN(parseShown(s)));
for(const engine of (process.env.ENGINES||'chromium').split(',')){
  const browser=await pw[engine].launch();keepAnswerOpen(browser);
  const page=await browser.newPage({viewport:{width:1440,height:950},reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.CALC2_BASE_URL+'/calc2/');await page.waitForFunction(()=>typeof CalcNumber==='object');
  await installShownReader(page);
  for(const [v,s] of cases){const r=await page.evaluate(v=>({text:fmt(v),tex:CalcNumber.format(v,{tex:true})}),v);check(engine+' запись '+s,noSpace(r.text)===noSpace(s),r);}
  const pct=await page.evaluate(()=>[CalcNumber.format(62.5,{percent:true}),CalcNumber.format(167.1875,{percent:true})]);
  check(engine+' проценты',noSpace(pct[0])==='62,5%'&&noSpace(pct[1])==='2675/16%≈167,19%',pct);
  const precision=await page.evaluate(()=>({
    noisy:[Math.sqrt(3)+1e-10,40-20*Math.sqrt(2)+1e-10,50*(Math.sqrt(5)-1)+1e-10].map(fmt),
    complex:fmt(97/99+83/97*Math.sqrt(997)),
    special:[null,undefined,NaN,Infinity,-Infinity].map(v=>CalcNumber.format(v)),
    large:fmt(1e21),
    guesses:[checkGuess('2,1544','≈ 2,154'),checkGuess('2,155','≈ 2,154'),checkGuess('1,000000001','1'),checkGuess('1000000001','1000000000')],
    linearExact:math.evaluate(fmtLinear(Math.sqrt(2)-1,1-Math.sqrt(3),'X'),{X:2}),
    inputExact:fmtInput(.625),
    compoundTex:mathToTex(String(Math.sqrt(2)-1)+'*X'),
    smallInput:CalcNumber.parse('1e-7')?.value,
    copiedPower:math.evaluate('8^'+ppfNum(1/3)),
    copiedSum:math.evaluate(sumSegExpr(3/7,5/7),{Q:10}),
    ppfBoundary:ppfSnap(100/3),
  }));
  check(engine+' корни после бисекции',precision.noisy.every(v=>v.includes('√')&&!v.includes('≈'))&&noSpace(precision.noisy[2])==='−50+50√5',precision);
  check(engine+' сложный допустимый радикал',Math.abs(parseShown(precision.complex)-(97/99+83/97*Math.sqrt(997)))<1e-12&&!precision.complex.includes('≈'),precision.complex);
  const negativeCases=await page.evaluate(()=>{
    const bad=[];
    for(const k of [...Array.from({length:99},(_,i)=>i+2),206,215,217,256,260,267,278,313,455])if(![8,27,64].includes(k)){
      const result=CalcNumber.classify(Math.cbrt(k));if(result.kind!=='approx')bad.push([k,result.text]);
    }
    return bad;
  });
  check(engine+' кубические корни не выданы за квадратные',!negativeCases.length,negativeCases);
  check(engine+' неопределённое не становится бесконечностью',precision.special.join('|')==='не определено|не определено|не определено|∞|−∞',precision.special);
  check(engine+' большое число не превращается в экспоненту',noSpace(precision.large)==='1000000000000000000000',precision.large);
  check(engine+' точность самопроверки',JSON.stringify(precision.guesses)==='[true,false,false,false]',precision.guesses);
  check(engine+' знак составного коэффициента и свободного члена',Math.abs(precision.linearExact-(2*Math.sqrt(2)-Math.sqrt(3)-1))<1e-12,precision.linearExact);
  check(engine+' числовое поле сохраняет 0.625',precision.inputExact==='0.625',precision.inputExact);
  check(engine+' составной коэффициент сгруппирован в TeX',precision.compoundTex.includes('\\left(')&&precision.compoundTex.includes('\\sqrt{2}'),precision.compoundTex);
  check(engine+' машинная экспонента читается без потери',precision.smallInput===1e-7,precision.smallInput);
  check(engine+' дробная степень в копируемой функции сохраняет скобки',Math.abs(precision.copiedPower-2)<1e-12,precision.copiedPower);
  check(engine+' копируемая сумма сохраняет дробные коэффициенты',Math.abs(precision.copiedSum-65/3)<1e-12,precision.copiedSum);
  check(engine+' граница КПВ сохраняет 100/3',precision.ppfBoundary===100/3,precision.ppfBoundary);
  await page.evaluate(()=>{
    window.__editedNumber=.625;
    const el=makeEditableValue({get:()=>window.__editedNumber,set:v=>{window.__editedNumber=v;},tex:(_,s)=>s});
    el.id='astra-exact-edit';el.style.cssText='position:fixed;left:20px;top:100px;z-index:10000;background:white;padding:10px';document.body.append(el);
  });
  const editable=page.locator('#astra-exact-edit');
  await editable.click();await editable.fill('100/3');await editable.press('Enter');
  check(engine+' редактируемое число принимает дробь целиком',await page.evaluate(()=>Math.abs(window.__editedNumber-100/3)<1e-12));
  await page.evaluate(()=>{window.__editedNumber=Math.cbrt(10);document.getElementById('astra-exact-edit')._repaint();});
  await editable.click();await editable.press('Enter');
  check(engine+' открытие числового поля не округляет модель',await page.evaluate(()=>window.__editedNumber===Math.cbrt(10)));
  await editable.evaluate(el=>el.remove());
  const r=await page.evaluate(()=>{
    resetSceneMemory();pickScene('sd');
    updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),'Q=100-2P');updateCurveExpr(STATE.curves.find(c=>c.role==='supply'),'P=Q');
    redrawAll();buildAnswer();
    return {values:[...document.querySelectorAll('#ans-hero .ans-val')].map(window.__readShownText),
      tex:[...document.querySelectorAll('#ans-hero .ans-val annotation')].map(e=>e.textContent),
      self:[['100/3','100/3'],['33,3','100/3'],['33,33','100/3'],['33','100/3'],['33,4','100/3'],['√2','√2'],['5√2','5√2'],['(33,3;5√2)','(100/3;5√2)'],['(33;5√2)','(100/3;5√2)'],['1,01','1'],['1','1'],['100/','100/3']].map(([a,b])=>[a,b,checkGuess(a,b)]),
      linear:fmtLinear(-.625,5,'X'),
      axes:[...document.querySelectorAll('#chart text.coord-num')].map(e=>e.textContent),
      exportTex:buildTex('','')};
  });
  const expected=[100/3,100/3,2500/9,5000/9,2500/3];
  expected.forEach((v,i)=>check(engine+' ответ '+i,Math.abs(parseShown(r.values[i])-v)<1e-6,r.values[i]));
  check(engine+' дробь набрана KaTeX',r.tex.some(s=>s.includes('\\tfrac{100}{3}')),r.tex);
  const verdicts=[true,true,true,false,false,true,true,true,false,false,true,null];
  r.self.forEach((row,i)=>check(engine+' Сначала сам '+row[0],row[2]===verdicts[i],row));
  check(engine+' коэффициент 0.625 сохранён',r.linear.includes('0.625')&&!r.linear.includes('0.63'),r.linear);
  check(engine+' дробь в ключевом делении оси',r.axes.some(t=>t.includes('100/3')),r.axes);
  check(engine+' дробь в .tex',r.exportTex.includes('\\tfrac{100}{3}'));
  await page.evaluate(()=>{setSelfMode(true);buildAnswer();});
  // Дождаться кадра, который ещё был запланирован предыдущей настройкой модели.
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const cell=page.locator('#ans-hero .ans-cell').first();
  for(const [v,expectedText] of [['33,3','верно'],['100/3','верно'],['33','не сходится']]){
    await cell.locator('.self-inp').fill(v);await cell.locator('.self-check').click();
    const shown=await cell.locator('.self-pill').innerText();check(engine+' настоящее поле '+v,shown.includes(expectedText),shown);
    if(expectedText==='верно')check(engine+' точный ответ у поля '+v,(await cell.locator('.self-detail').innerText()).includes('100/3'));
  }
  await cell.locator('.self-inp').fill('100/');await cell.locator('.self-check').click();
  check(engine+' формат ошибки у поля',(await cell.locator('.self-detail').innerText()).includes('дробь'));
  const other=await page.evaluate(()=>{
    setSelfMode(false);resetSceneMemory();pickScene('sd');
    updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),'100-Q');updateCurveExpr(STATE.curves.find(c=>c.role==='supply'),'Q^2/100');redrawAll();buildAnswer();
    const root=__readShownText(document.querySelector('#ans-hero .ans-val')),csRoot=fmt(STATE.cs);
    resetSceneMemory();pickScene('taxes');
    updateCurveExpr(STATE.curves.find(c=>c.role==='demand'),'Q=100-2P');updateCurveExpr(STATE.curves.find(c=>c.role==='supply'),'Q');
    setType('tax');setTax(1);redrawAll();buildAnswer();
    const was=[...document.querySelectorAll('#ans-hero .ans-was')].map(__readShownText);
    resetSceneMemory();pickScene('prod');redrawAll();buildAnswer();
    const prod={...STATE.prod};
    resetSceneMemory();pickScene('m-graph');STATE.curves=[];curveCounter=0;addCurve('x^3-3*x');renderGraphRows();redrawAll();buildAnswer();
    const zeros=[...document.querySelectorAll('#info-graph .stat')].find(e=>__readShownText(e.querySelector('span')).includes('Пересекает ось x'));
    return{root,csRoot,was,prod,zeros:zeros&&__readShownText(zeros.querySelector('b'))};
  });
  check(engine+' нелинейный рынок: точный корень',other.root.includes('√5')&&Math.abs(parseShown(other.root)-50*(Math.sqrt(5)-1))<1e-8,other.root);
  // Q=100−2P, Pₛ=Q, Pᵦ=Pₛ+1: Q₁=98/3, Pᵦ₁=101/3.
  check(engine+' площадь с большим целым коэффициентом корня',noSpace(other.csRoot)==='7500−2500√5',other.csRoot);
  check(engine+' дроби в было → стало',other.was.some(s=>noSpace(s)==='100/3−2/3')&&other.was.some(s=>noSpace(s)==='100/3+1/3'),other.was);
  check(engine+' производственная функция: AP=MP=225 при L=15',Math.abs(other.prod.maxAP.L-15)<1e-8&&Math.abs(other.prod.mpAtMaxAP-225)<2e-8,other.prod);
  check(engine+' нули x³−3x записаны корнями',other.zeros?.includes('√3')&&!other.zeros.includes('≈'),other.zeros);
  const rootCell=await page.evaluate(()=>{
    resetSceneMemory();pickScene('m-graph');STATE.curves=[];curveCounter=0;addCurve('x^3-10');renderGraphRows();redrawAll();
    setSelfMode(true);buildAnswer();
    return [...document.querySelectorAll('#ans-hero .ans-cell')].findIndex(c=>Math.abs(__parseShown(__readShownText(c.querySelector('.ans-val')))-Math.cbrt(10))<.001);
  });
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  check(engine+' приближённый корень сначала скрыт',rootCell>=0&&!await page.evaluate(()=>selfPointOpen(Math.cbrt(10),0)));
  if(rootCell>=0){
    const rootInput=page.locator('#ans-hero .ans-cell').nth(rootCell);
    await rootInput.locator('.self-inp').fill('2,1544');await rootInput.locator('.self-check').click();
    const rootResult=await page.evaluate(()=>({open:selfPointOpen(Math.cbrt(10),0),values:selfOpenValues(),
      verdict:SELF.verdict,typed:SELF.typed,truth:SELF.vtruth,key:selfKey(),
      cells:[...document.querySelectorAll('#ans-hero .ans-cell')].map(c=>[__readShownText(c.querySelector('.ans-val')),c.querySelector('.self-inp')?.value])}));
    check(engine+' правильная точная запись открывает приближённую точку',rootResult.open,rootResult);
  }else check(engine+' правильная точная запись открывает приближённую точку',false);
  check(engine+' нет JS ошибок',!errors.length,errors);await browser.close();
}
console.log(`Э3: ${total-bad}/${total}, ошибок ${bad}`);process.exitCode=bad?1:0;
