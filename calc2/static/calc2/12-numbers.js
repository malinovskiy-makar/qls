const CalcNumber = (() => {
// Единая запись чисел calc2, принятое правило 29.10, Э3.
// PSLQ, Ferguson–Bailey: https://www.davidhbailey.com/dhbpapers/pslq.pdf, §3–5.
// Это поиск короткой записи численного результата, не доказательство его точности.
const gcd=(a,b)=>{a=Math.abs(a);b=Math.abs(b);while(b){const t=a%b;a=b;b=t;}return a||1;};
const frac=(p,q)=>{if(q<0){p=-p;q=-q;}const g=gcd(p,q);return[p/g,q/g];};
const squarefree=Array.from({length:999},(_,i)=>i+2).filter(c=>{for(let k=2;k*k<=c;k++)if(c%(k*k)===0)return false;return true;});
// Проверяем найденное соотношение с 30 десятичными разрядами. В double
// вычитание больших слагаемых иногда делает ложный радикал «точным».
const fixedScale=10n**30n, fixedRoots=new Map();
function fixed(v){
  const [m,e='0']=String(v).toLowerCase().split('e');
  const decimals=(m.split('.')[1]||'').length,n=BigInt(m.replace('.',''));
  const power=30+Number(e)-decimals;
  return power>=0?n*10n**BigInt(power):n/10n**BigInt(-power);
}
function fixedRoot(c){
  if(fixedRoots.has(c))return fixedRoots.get(c);
  const n=BigInt(c)*fixedScale*fixedScale;
  let x=1n<<BigInt(Math.ceil(n.toString(2).length/2)),y=(x+n/x)/2n;
  while(y<x){x=y;y=(x+n/x)/2n;}
  fixedRoots.set(c,x);return x;
}
function radicalClose(v,a,b,c,tolerance){
  const exact=BigInt(a[0])*fixedScale/BigInt(a[1])+BigInt(b[0])*fixedRoot(c)/BigInt(b[1]);
  const d=fixed(v)-exact;return(d<0n?-d:d)<=fixed(tolerance);
}
function quadratic(v,co){
  let [C,B,A]=co;if(!A)return null;
  const g=gcd(gcd(A,B),C);A/=g;B/=g;C/=g;
  if(A<0){A=-A;B=-B;C=-C;}
  const a=frac(-B,2*A);if(a[1]>100)return null;
  const D=BigInt(B)**2n-4n*BigInt(A)*BigInt(C);if(D<=0n)return null;
  for(const c of squarefree){
    if(D%BigInt(c))continue;
    const sq=D/BigInt(c),s=Math.round(Math.sqrt(Number(sq)));
    if(BigInt(s)**2n!==sq)continue;
    let b=frac(s,2*A);if(b[1]>100)return null;
    if(v<a[0]/a[1])b=[-b[0],b[1]];
    const found=a[0]/a[1]+b[0]/b[1]*Math.sqrt(c);
    // Простое квадратное число допускает погрешность численного решателя.
    // Для сложной записи нужна точность double: иначе произвольное число
    // легко ошибочно представить длинной комбинацией радикалов.
    const cost=Math.abs(a[0])+a[1]+Math.abs(b[0])+b[1]+c;
    const conditioning=(Math.abs(a[0]/a[1])+Math.abs(b[0]/b[1])*Math.sqrt(c))/Math.max(1,Math.abs(v));
    const simple=cost<=256||(a[1]===1&&b[1]===1&&conditioning<=100);
    const tolerance=simple?2e-8:4*Number.EPSILON*Math.max(1,Math.abs(v));
    if(Math.abs(v-found)<=tolerance&&radicalClose(v,a,b,c,tolerance))return{a,b,c};
  }
  return null;
}
function relation(x,accept){
  // Это всегда задача размерности 3. Плоские буферы сохраняют порядок
  // арифметики PSLQ, но не создают map/slice/коэффициенты на каждом из
  // сотен тысяч внутренних шагов при движении ставки. Пределы, допуски
  // и проверка найденного радикала с 30 знаками остались прежними.
  const norm=Math.hypot(...x),y=new Float64Array([x[0]/norm,x[1]/norm,x[2]/norm]);
  const s0=Math.hypot(...y),s1=Math.hypot(y[1],y[2]),s2=Math.hypot(y[2]);
  const H=new Float64Array([s1/s0,0,-y[1]*y[0]/(s0*s1),s2/s1,
    -y[2]*y[0]/(s0*s1),-y[2]*y[1]/(s1*s2)]);
  const B=new Float64Array([1,0,0,0,1,0,0,0,1]);
  const rejected=new Float64Array(9).fill(NaN);
  const reduce=()=>{for(let i=1;i<3;i++)for(let j=i-1;j>=0;j--){
    if(Math.abs(H[3*j])<1e-25)return false;
    const t=Math.round(H[2*i+j]/H[3*j]);
    y[j]+=t*y[i];for(let k=0;k<=j;k++)H[2*i+k]-=t*H[2*j+k];
    for(let k=0;k<3;k++)B[3*k+j]+=t*B[3*k+i];
  }
  for(let k=0;k<9;k++)if(!Number.isSafeInteger(B[k])||Math.abs(B[k])>1e9)return false;
  return true;};
  for(let iter=0;iter<100;iter++){
    if(!reduce())return null;
    for(let j=0;j<3;j++){
      // Нулевая редукция оставляет тот же столбец. Чистая проверка уже
      // отвергла его: повторять невязку, gcd и поиск радикала незачем.
      if(B[j]===rejected[3*j]&&B[3+j]===rejected[3*j+1]&&B[6+j]===rejected[3*j+2])continue;
      const a=B[j]*x[0],b=B[3+j]*x[1],c=B[6+j]*x[2];
      const residual=Math.abs(((0+a)+b)+c);
      if(residual>1e-9*Math.max(1,Math.abs(a),Math.abs(b),Math.abs(c)))continue;
      rejected[3*j]=B[j];rejected[3*j+1]=B[3+j];rejected[3*j+2]=B[6+j];
      const r=accept([B[j],B[3+j],B[6+j]]);if(r)return r;
    }
    const m=1.2*Math.abs(H[3])>Math.abs(H[0])?1:0;
    const ym=y[m];y[m]=y[m+1];y[m+1]=ym;
    for(let j=0;j<2;j++){const h=H[2*m+j];H[2*m+j]=H[2*(m+1)+j];H[2*(m+1)+j]=h;}
    for(let i=0;i<3;i++){
      const b=B[3*i+m];B[3*i+m]=B[3*i+m+1];B[3*i+m+1]=b;
      const r=rejected[3*m+i];rejected[3*m+i]=rejected[3*(m+1)+i];rejected[3*(m+1)+i]=r;
    }
    if(m===0){
      const n=Math.hypot(H[0],H[1]),a=H[0]/n,b=H[1]/n;
      for(let i=0;i<3;i++){const h=H[2*i];H[2*i]=a*h+b*H[2*i+1];H[2*i+1]=-b*h+a*H[2*i+1];}
    }
  }
  return null;
}
function recognize(v){
  const fast=relation([1,v,v*v],co=>quadratic(v,co));if(fast)return fast;
  let best=null,score=Infinity;
  for(const c of squarefree){
    const root=Math.sqrt(c);
    const r=relation([1,v,root],([C,B,R])=>{
      if(!B||!R)return null;
      const a=frac(-C,B),b=frac(-R,B);
      if(a[1]>100||b[1]>100)return null;
      const found=a[0]/a[1]+b[0]/b[1]*root;
      const conditioning=(Math.abs(a[0]/a[1])+Math.abs(b[0]/b[1])*root)/Math.max(1,Math.abs(v));
      const simple=a[1]===1&&b[1]===1&&conditioning<=100;
      const tolerance=simple?2e-8:4*Number.EPSILON*Math.max(1,Math.abs(v));
      return Math.abs(v-found)<=tolerance&&radicalClose(v,a,b,c,tolerance)?{a,b,c}:null;
    });
    if(r){const cost=Math.abs(r.a[0])+r.a[1]+Math.abs(r.b[0])+r.b[1]+c;if((cost<=10000||(r.a[1]===1&&r.b[1]===1))&&cost<score){best=r;score=cost;}}
  }
  return best;
}

const cache=new Map();
// Во время интерактивного кадра собираем недостающие записи для рабочего
// потока. Поиск радикала никогда не нужен для положения самой кривой.
let collecting = null;
function collect(fn) {
  const previous = collecting, values = new Set();
  collecting = values;
  try { fn(); } finally { collecting = previous; }
  return [...values];
}
function seed(records) {
  if (cache.size + records.length > 4096) cache.clear();
  records.forEach(r => cache.set(r.value, r));
}
const integer=v=>Math.abs(v).toLocaleString('en-US',{useGrouping:false,maximumFractionDigits:0}).replace(/\B(?=(\d{3})+(?!\d))/g,'\u202f');
const sign=v=>v<0?'−':'';
// Численный поиск равновесия и интеграл дают шум порядка 10⁻⁹.
// Без этой границы 100/3, найденное бисекцией, превращалось в «≈ 33,333».
const close=(a,b)=>Math.abs(a-b)<=Math.max(2e-8,8*Number.EPSILON*Math.abs(a));
function decimal(v,d=3,fixed=false){
  let s=Math.abs(v)<1e21?Math.abs(v).toFixed(d):Math.abs(v).toLocaleString('en-US',{useGrouping:false,minimumFractionDigits:d,maximumFractionDigits:d});
  if(!fixed)s=s.replace(/\.?0+$/,'');
  const parts=s.split('.');
  return (Number(s)===0?'':sign(v))+integer(Number(parts[0]))+(parts[1]?','+parts[1]:'');
}
function rational(v,max){
  for(let q=1;q<=max;q++){
    const p=Math.round(v*q);
    // Большой знаменатель не получает тот же допуск, что 1/3: иначе
    // кубический корень мог случайно стать дробью вроде 1193/202.
    const tolerance=Math.max(2e-8/q,8*Number.EPSILON*Math.abs(v));
    if(Number.isSafeInteger(p)&&Math.abs(v-p/q)<=tolerance)return frac(p,q);
  }
  return null;
}
function fraction(p,q,tex=false){
  if(q===1)return tex?(p<0?'-':'')+integer(p).replace(/\u202f/g,'~'):sign(p)+integer(p);
  return tex?(p<0?'-':'')+'\\tfrac{'+integer(p).replace(/\u202f/g,'~')+'}{'+q+'}':sign(p)+integer(p)+'/'+q;
}
function radical(r,tex=false){
  const [ap,aq]=r.a,[bp,bq]=r.b;
  const term=tex?(Math.abs(bp)===1?'':integer(bp).replace(/\u202f/g,'~'))+'\\sqrt{'+r.c+'}'
    :(Math.abs(bp)===1?'':integer(bp))+'√'+r.c;
  const root=bq===1?term:tex?'\\tfrac{'+term+'}{'+bq+'}':term+'/'+bq;
  return (ap?fraction(ap,aq,tex)+(bp<0?(tex?' - ':' − '):' + '):(bp<0?(tex?'-':'−'):''))+root;
}
function classify(v, exact=false){
  if(!Number.isFinite(v)){
    const infinity=v===Infinity||v===-Infinity;
    return{kind:'special',text:infinity?sign(v)+'∞':'не определено',tex:infinity?(v<0?'-':'')+'\\infty':'\\text{не определено}',value:v};
  }
  if(cache.has(v))return cache.get(v);
  let r;
  const rounded=Math.abs(v)<1e18?Math.round(v*1000)/1000:v;
  if(close(v,rounded)){
    const text=decimal(rounded);
    r={kind:'decimal',text,tex:text.replace(/−/g,'-').replace(/\u202f/g,'~').replace(/,/g,'{,}')};
  }else{
    const f=rational(v,1000);
    if(f)r={kind:'fraction',text:fraction(...f),tex:fraction(...f,true)};
    else{
      if (collecting && !exact) {
        collecting.add(v);
        return {kind:'pending', text:'…', tex:'\\ldots', value:v};
      }
      const rad=recognize(v);
      if(rad)r={kind:'radical',text:radical(rad),tex:radical(rad,true)};
      else{const text=decimal(v,3,true);r={kind:'approx',text:'≈ '+text,tex:'\\approx '+text.replace(/−/g,'-').replace(/\u202f/g,'~').replace(/,/g,'{,}')};}
    }
  }
  r.value=v;
  if(cache.size>4096)cache.clear();cache.set(v,r);return r;
}
function format(v,{percent=false,tex=false}={}){
  const r=classify(v);let text=tex?r.tex:r.text;
  if(r.kind==='pending')return text;
  if(!percent)return text;
  const unit=tex?'\\,\\%':' %';
  if(r.kind==='decimal')return text+unit;
  const f=rational(v,1000);
  const approx=decimal(v,2,true);
  const a=tex?approx.replace(/−/g,'-').replace(/\u202f/g,'~').replace(/,/g,'{,}'):approx;
  return (f?fraction(...f,tex)+unit+(tex?' \\approx ':' ≈ '):(tex?'\\approx ':'≈ '))+a+unit;
}
// В произведении или после внешнего минуса a+b√c остаётся одним числом.
function factor(v,{tex=false}={}){
  const r=classify(v),s=format(v,{tex});
  return r.kind==='radical'&&/ [−+] /.test(r.text)?(tex?'\\left('+s+'\\right)':'('+s+')'):s;
}
// Поля и формулы, которые движок будет считать, сохраняют машинную точность.
function expression(v,{atomic=false}={}){
  const r=classify(v,true);
  if(r.kind==='approx'||r.kind==='special')return atomic&&v<0?'('+String(v)+')':String(v);
  const s=r.text.replace(/\u202f/g,'').replace(/−/g,'-').replace(/,/g,'.').replace(/(\d)√(\d+)/g,'$1*sqrt($2)').replace(/√(\d+)/g,'sqrt($1)');
  return atomic&&(v<0||!/^[\d.]+(?:e[+-]?\d+)?$/i.test(s))?'('+s+')':s;
}
// Набранные дроби и радикалы сохраняют ровно ту же запись в KaTeX/TeX.
function texText(s){
  return String(s)
    .replace(/(\d[\d\u202f~]*)?√(\d+)(?:\/(\d+))?/g,(_,n,c,q)=>{
      const term=(n||'').replace(/\u202f/g,'~')+'\\sqrt{'+c+'}';
      return q?'\\tfrac{'+term+'}{'+q+'}':term;
    })
    .replace(/(\d[\d\u202f~]*)\/(\d[\d\u202f~]*)/g,(_,p,q)=>'\\tfrac{'+p.replace(/\u202f/g,'~')+'}{'+q.replace(/\u202f/g,'~')+'}')
    .replace(/≈/g,'\\approx ').replace(/∞/g,'\\infty ')
    .replace(/=\s*\\approx\b/g,'\\approx ');
}
function parse(raw){
  let s=String(raw??'').trim();if(!s||s.length>300)return null;
  const approximate=s.startsWith('≈');
  s=approximate?s.slice(1):s.split('≈')[0];
  s=s.replace(/[\s\u200b]/g,'').replace(/[−–]/g,'-').replace(/,/g,'.').replace(/[°∘%]$/,'');
  const decimalMatch=/^[+-]?\d+(?:\.(\d+))?$/.exec(s);
  const digits=decimalMatch?(decimalMatch[1]?.length||0):null;
  s=s.replace(/(\d)√(\d+(?:\.\d+)?)/g,'$1*sqrt($2)').replace(/√(\d+(?:\.\d+)?)/g,'sqrt($1)').replace(/√\(/g,'sqrt(');
  if(!/^[\d.eE+\-*/()sqrt]+$/.test(s))return null;
  try{
    const node=math.parse(s);let safe=true;
    node.traverse(n=>{
      if(n.isConstantNode||n.isParenthesisNode)return;
      if(n.isOperatorNode&&['+','-','*','/'].includes(n.op))return;
      if(n.isFunctionNode&&n.fn.name==='sqrt'&&n.args.length===1)return;
      if(n.isSymbolNode&&n.name==='sqrt')return;
      safe=false;
    });
    if(!safe)return null;
    const value=node.evaluate();return Number.isFinite(value)?{value,digits,approximate}:null;
  }catch(e){return null;}
}
function readText(el){
  if(!el)return '';
  if(el.dataset?.valueText!==undefined)return el.dataset.valueText;
  const c=el.cloneNode(true);
  c.querySelectorAll('[data-value-text]').forEach(n=>{n.textContent=n.dataset.valueText;});
  // Готовая формула без исходного data-value-text: структура MathML
  // сохраняет дробную черту и корень, в отличие от textContent HTML KaTeX.
  const mathText=n=>{
    if(n.nodeType===3)return n.textContent;
    if(n.localName==='annotation')return '';
    const parts=[...n.childNodes].map(mathText);
    if(n.localName==='mfrac'){
      const plainNumber=/^[−-]?\d+(?:[.,]\d+)?$/;
      const plainRoot=/^\d*√\d+$/;
      const wrap=s=>plainNumber.test(s)||plainRoot.test(s)?s:'('+s+')';
      return wrap(parts[0])+'/'+wrap(parts[1]);
    }
    if(n.localName==='msqrt'){const s=parts.join('');return '√'+(/^\d+$/.test(s)?s:'('+s+')');}
    return parts.join('');
  };
  c.querySelectorAll('.katex').forEach(k=>{
    const m=k.querySelector('.katex-mathml math');
    if(m&&m.querySelector('mfrac,msqrt'))k.textContent=mathText(m);
  });
  c.querySelectorAll('.katex-mathml, annotation').forEach(n=>n.remove());
  return c.textContent.replace(/[\s\u200b]+/g,' ').trim();
}
return {classify,format,factor,expression,texText,parse,readText,recognize,collect,seed};
})();
