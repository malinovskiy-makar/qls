/* Независимый читатель отображённых чисел. Не вызывает форматтер приложения. */
export function parseShown(raw) {
  let s=String(raw??'').trim();
  if(s.startsWith('≈'))s=s.slice(1);else s=s.split('≈')[0];
  s=s.replace(/[\s\u200b]/g,'').replace(/[−–]/g,'-').replace(/,/g,'.').replace(/[°∘%]$/,'').replace(/√/g,'sqrt');
  if(!s||s.length>500)return NaN;
  const tokens=[],rx=/sqrt|\d+(?:\.\d+)?|[()+\-*/]/gy;let at=0,m;
  while(at<s.length){rx.lastIndex=at;m=rx.exec(s);if(!m)return NaN;tokens.push(m[0]);at=rx.lastIndex;}
  let i=0;
  const atom=()=>{
    const t=tokens[i++];
    if(t==='+'||t==='-')return(t==='-'?-1:1)*atom();
    if(t==='sqrt')return Math.sqrt(atom());
    if(t==='('){const v=sum();if(tokens[i++]!==')')throw Error(')');return v;}
    if(!/^\d/.test(t||''))throw Error('number');return Number(t);
  };
  const product=()=>{let v=atom();while(i<tokens.length){const t=tokens[i];if(t==='*'||t==='/'){i++;const r=atom();v=t==='*'?v*r:v/r;}
    else if(t==='sqrt'||t==='('){v*=atom();}else break;}return v;};
  const sum=()=>{let v=product();while(tokens[i]==='+'||tokens[i]==='-'){const t=tokens[i++],r=product();v=t==='+'?v+r:v-r;}return v;};
  try{const v=sum();return i===tokens.length&&Number.isFinite(v)?v:NaN;}catch(e){return NaN;}
}
export function readShownText(el) {
  if(!el)return '';
  if(el.dataset?.valueText!==undefined)return el.dataset.valueText;
  const c=el.cloneNode(true);
  c.querySelectorAll('[data-value-text]').forEach(n=>{n.textContent=n.dataset.valueText;});
  c.querySelectorAll('.katex-mathml,annotation').forEach(n=>n.remove());
  return c.textContent.replace(/[\s\u200b]+/g,' ').trim();
}
export async function installShownReader(page) {
  const content='window.__parseShown='+parseShown.toString()+';window.__readShownText='+readShownText.toString()+';';
  await page.addInitScript({content});
  await page.addScriptTag({content});
}
export function shownNumbers(raw) {
  const s=String(raw??'').replace(/[\s\u200b]/g,'').replace(/[−–]/g,'-');
  const n='\\d+(?:[.,]\\d+)?',r='(?:'+n+')?√'+n+'(?:/'+n+')?',f=n+'(?:/'+n+')?';
  const rx=new RegExp('≈?[+-]?(?:'+r+'|'+f+'(?:[+-]'+r+')?)','g');
  return [...s.matchAll(rx)].map(m=>({raw:m[0],value:parseShown(m[0]),at:m.index}));
}
export function shownEquivalent(actual,expected) {
  const norm=s=>String(s??'').replace(/[\s\u200b]/g,'').replace(/[−–]/g,'-');
  if(norm(actual)===norm(expected))return true;
  const near=(a,b)=>{
    const m=/[.,](\d+)$/.exec(b.raw.replace(/[%°∘]$/,''));
    const tolerance=m?.[1]?.length?Math.pow(10,-m[1].length)/2+1e-8:1e-8;
    return Number.isFinite(a.value)&&Number.isFinite(b.value)&&Math.abs(a.value-b.value)<=tolerance;
  };
  const a0=parseShown(actual),b0=parseShown(expected);
  if(Number.isFinite(a0)&&Number.isFinite(b0))return near({value:a0},{value:b0,raw:norm(expected)});
  const a=shownNumbers(actual),b=shownNumbers(expected);
  if(!a.length||a.length!==b.length)return false;
  const skeleton=(text,nums)=>{let s=norm(text);for(const n of [...nums].reverse())s=s.slice(0,n.at)+'#'+s.slice(n.at+n.raw.length);return s;};
  return skeleton(actual,a)===skeleton(expected,b)&&a.every((n,i)=>near(n,b[i]));
}
/* «До ± изменение» — два числа, а не только их сумма: 30+10 не равно
   0+40 как описание изменения, хотя арифметические итоги совпадают. */
export function shownChangeEquivalent(actual,expected){
  const parts=raw=>{
    const s=String(raw??'').replace(/[\s\u200b]/g,'').replace(/[−–]/g,'-').replace(/^≈/,'');
    let depth=0;
    for(let i=0;i<s.length;i++){
      if(s[i]==='(')depth++;else if(s[i]===')')depth--;
      else if(!depth&&i>0&&/[+-]/.test(s[i])&&!/[eE]/.test(s[i-1]))return[s.slice(0,i),s.slice(i)];
    }
    return null;
  };
  const a=parts(actual),b=parts(expected);
  return !!a&&!!b&&shownEquivalent(a[0],b[0])&&shownEquivalent(a[1],b[1]);
}
