// Регрессии аудита: настоящий код вычислений в Node VM, без браузера/БД.
// Эталоны — аналитические формулы, не копии алгоритмов поиска.
import fs from 'node:fs';
import vm from 'node:vm';
import { execFileSync } from 'node:child_process';
const baseline = process.argv.includes('--baseline');
const elements = new Map();
const ctx = vm.createContext({ console, d3: {select:()=>({})}, document: {
  getElementById: id => elements.get(id) || null, querySelector: () => null,
  querySelectorAll: () => [], documentElement: { getAttribute: () => null },
}, window: {}, getComputedStyle: () => ({ getPropertyValue: () => '' }),
setTimeout: () => 0, clearTimeout: () => {} });
const source = file => baseline && file.startsWith('calc2/static/')
  ? execFileSync('git', ['show', '15bd4a4b:'+file], { encoding: 'utf8' }) : fs.readFileSync(file, 'utf8');
for (const file of ['static/vendor/mathjs-12.4.3/math.min.js', ...[
  '00-config','10-math-core','12-numbers','20-plane','30-curves','40-scenes-market',
  '42-scenes-mono','43-discrimination','50-scenes-macro','54-scenes-ppf','60-overlays',
  '70-scenes-math','80-ui','90-explain',
].map(name => 'calc2/static/calc2/'+name+'.js')]) vm.runInContext(source(file), ctx, { filename: file });
// Заглушены только эффекты представления. Формулы, компиляция, поиск и
// создание содержимого ответа исполняются из файлов продукта без подмены.
vm.runInContext(`applyTradeRanges=()=>{}; function applyAutoRanges(){}; function niceMax(x){return x;} function padMax(x){return x*1.15;}
function setMathWindow(){};function updateResetViewBtn(){};function showPaneError(){};`, ctx);
const run = code => vm.runInContext(code, ctx);
const rows=[];
function check(name, actual, expected, tolerance=0) {
  const ok = typeof expected==='number' ? Number.isFinite(actual) && Math.abs(actual-expected)<=tolerance : actual===expected;
  rows.push({name,ok,actual,expected,tolerance});
  if(!ok) console.log('FAIL',name,JSON.stringify({actual,expected,tolerance}));
}
function test(name, code, expected, tol=0) { try { check(name,run(code),expected,tol); } catch(e){rows.push({name,ok:false,error:e.message});console.log('FAIL',name,e.message);} }
for (const expr of ['100-X^2/100','sqrt(10000-X^2)','100-sqrt(100*X)']) {
  test('M01 отвергнута нелинейная '+expr,`STATE.tbF1=${JSON.stringify(expr)};STATE.tbF2='100-2X';recomputeTradeB();STATE.tradeBData.ok`,false);
}
for (const price of [null,1,2,0.5,3]) {
  const d=run(`STATE.tbF1='100-X';STATE.tbF2='100-2X';STATE.tbManualPrice=${price};recomputeTradeB();STATE.tradeBData`);
  check('M01/E01 линейная постановка '+price,d.ok,true);
  check('E01 допустимость цены '+price,!d.noTrade,price===null||price===1||price===2);
  check('M01 предел обмена '+price,d.E_L,Math.min(100,100/(price||Math.SQRT2)),1e-6);
}
// В этом сюжете поля задают правую часть Y(X), в отличие от общей КПВ.
test('M01 линейная запись с маленькой x',`STATE.tbF1='100-x';STATE.tbF2='100-2*x';recomputeTradeB();STATE.tradeBData.ok`,true);
const cases=[
  ['окружность', '(x-2)^2+(y-2)^2=1','y',[2,3],[2,1]],
  ['нецелый центр', '(x-2.123)^2+(y-1.789)^2=0.49','y',[2.123,2.489],[2.123,1.089]],
  ['отрицательная область', '(x+2)^2+(y+2)^2=1','y',[-2,-1],[-2,-3]],
  ['эллипс', '(x-2)^2/4+(y-3)^2=1','y',[2,4],[2,2]],
  ['наклонная цель', '(x-2)^2+(y-2)^2=1','x+y',[2+Math.SQRT1_2,2+Math.SQRT1_2],[2-Math.SQRT1_2,2-Math.SQRT1_2]],
  ['две компоненты','((x-2)^2+(y-2)^2-1)*((x-6)^2+(y-6)^2-1)=0','y',[6,7],[2,1]],
];
for(const [label,g,f,max,min] of cases) {
  run(`STATE.mode='math';STATE.mathFC=${JSON.stringify(f)};STATE.mathGC=${JSON.stringify(g)};constraintFit();`);
  for(const [want,expected]of [[true,max],[false,min]]) {
    const result=run(`(()=>{const G=parseConstraint(STATE.mathGC),c=compileAB(STATE.mathFC).compiled,F=(a,b)=>c.evaluate({x:a,y:b});const b={xMin:0,yMin:0,...STATE.consFit};const pts=constraintPointsIn(G,b.xMin,b.xMax,b.yMin,b.yMax);const opt=optimizeAlongCurve(F,pts,${want},G,b);return {opt,residual:opt?G(opt.a,opt.b):null};})()`);
    check('M02 '+label+' '+want+' x',result.opt?.a,expected[0],2e-5);
    check('M02 '+label+' '+want+' y',result.opt?.b,expected[1],2e-5);
    check('M02 '+label+' '+want+' допустимость',result.residual,0,1e-6);
  }
}
test('M02 базовый максимум sqrt(xy)',`(()=>{const G=(x,y)=>x+y-10,F=(x,y)=>Math.sqrt(x*y),b={xMin:-12,xMax:12,yMin:-12,yMax:12};return optimizeAlongCurve(F,constraintPointsIn(G,-12,12,-12,12),true,G,b).value;})()`,5,1e-7);
if(!baseline) {
  test('M02 одна замкнутая ветвь окружности',`constraintContoursIn((x,y)=>(x-2)**2+(y-2)**2-1,0,4,0,4).length`,1);
  test('M02 две несвязанные компоненты',`constraintContoursIn((x,y)=>((x-2)**2+(y-2)**2-1)*((x-6)**2+(y-6)**2-1),0,8,0,8).length`,2);
  test('M02 вертикальное ограничение',`constraintContoursIn((x,y)=>x-2,0,4,0,4).flat().every(p=>Math.abs(p[0]-2)<1e-7)`,true);
  test('M02 разрыв не нуль',`constraintContoursIn((x,y)=>1/(x-1.234),0,4,0,4).length`,0);
  test('M02 два равных максимума: неотрицательный представитель',`(()=>{const G=(x,y)=>x*x+y*y-25,b={xMin:-6,xMax:6,yMin:-6,yMax:6};return optimizeAlongCurve((x,y)=>x*y,constraintPointsIn(G,-6,6,-6,6),true,G,b).a;})()`,5/Math.sqrt(2),2e-5);
}
for(const [a,bd,bs,c]of [[100,1,1,0],[300,1,1,0],[200,1,1,0],[83.7,2.1,.7,12.3],[3000,.1,.2,40]]) {
  for(const axis of [10,100,200,1000]) {
    const r=run(`STATE.macroModel='laffer';STATE.macro.laffer={d:'${a}-${bd}Q',s:'${c}+${bs}Q',tmax:${axis}};recomputeMacro();STATE.macroRes`);
    check(`M03 t* a${a} ось${axis}`,r?.best.t,(a-c)/2,1e-6);
    check(`M03 T* a${a} ось${axis}`,r?.best.rev,(a-c)**2/(4*(bd+bs)),1e-5);
    check(`M03 Q* a${a} ось${axis}`,r?.best.Q,(a-c)/(2*(bd+bs)),1e-5);
  }
}
if(!baseline) {
  // D=100-Q²,S=0: Q*=10/√3, t*=200/3, T*=2000/(3√3).
  test('M03 нелинейный максимум',`lafferSolution(buildAnyCurve('100-Q^2'),buildAnyCurve('0')).best.rev`,2000/(3*Math.sqrt(3)),1e-5);
  test('M03 обратная запись Q(P)',`lafferSolution(buildAnyCurve('Q=300-P'),buildAnyCurve('Q=P')).best.t`,150,1e-6);
  test('M03 нет конечной запретительной ставки',`!!lafferSolution(buildAnyCurve('100/Q'),buildAnyCurve('Q')).error`,true);
  test('M03 неоднозначная полка налогового клина',`!!lafferSolution(buildAnyCurve('Q<20?80:100-Q'),buildAnyCurve('0')).error`,true);
}
// E08 проверяет фактически создаваемый HTML, а не поиск строки в исходнике.
elements.set('info-d3',{innerHTML:''});
for(const [pw,q1,q2,mc,expect]of [[20,100/3,0,100/3,false],[60,20,40,60,true],[120,0,120,120,false]]) {
  run(`STATE.d3World=true;STATE.discr3={found:true,q1:${q1},q2:${q2},Qtot:${q1+q2},P1:${100-q1},P2:${pw},mcLevel:${mc},c1:buildAnyCurve('100-Q'),c2:buildAnyCurve('${pw}')};updateDiscr3Panel();`);
  check('E08 равенство трёх только при двух активных рынках Pw'+pw,elements.get('info-d3').innerHTML.includes('<span>$MR_1 = P_w = MC$</span>'),expect);
}
console.log(JSON.stringify({baseline,passed:rows.filter(r=>r.ok).length,total:rows.length,failures:rows.filter(r=>!r.ok)},null,2));
if(process.env.RESULT_JSON)fs.writeFileSync(process.env.RESULT_JSON,JSON.stringify({baseline,rows},null,2)+'\n');
process.exitCode=rows.every(r=>r.ok)?0:1;
