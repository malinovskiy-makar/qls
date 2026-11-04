// Relative regression: cold exact-number formatting in one Node process.
// The frozen c9 reference is needed because machine-dependent ms limits lie.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import reference from './fixtures/pslq_reference.mjs';
const source=fs.readFileSync(new URL('../static/calc2/12-numbers.js',import.meta.url),'utf8');
const start=source.indexOf('function relation('),end=source.indexOf('function recognize(',start);
assert(start>=0&&end>start,'PSLQ entry points not found');
const old=source.slice(0,start)+reference.toString()+'\n'+source.slice(end);
const load=code=>new Function(code+';return CalcNumber;')();
const current=load(source),before=load(old);
const values=[-11.055555557625098,533.5555555596121,1067.1111111070547,
 -32.83333333941789,522.7222222182071,1045.4444444484598,
 ...Array.from({length:48},(_,i)=>Math.cbrt(i+101)),
 ...Array.from({length:16},(_,i)=>97/99+83/97*Math.sqrt(5+7*i))];
// Warm both algorithms on OTHER values; measured values stay uncached.
for(let k=2;k<18;k++){before.classify(Math.cbrt(k));current.classify(Math.cbrt(k));}
const times={before:0,current:0};
for(let i=0;i<values.length;i++){
 const result={};
 for(const [name,api]of(i%2?[['current',current],['before',before]]:[['before',before],['current',current]])){
  const t=performance.now();result[name]=api.classify(values[i]);times[name]+=performance.now()-t;
 }
 assert.deepEqual(result.current,result.before,`Exact-number result changed at ${values[i]}`);
}
const ratio=times.current/times.before;
console.log(JSON.stringify({values:values.length,times,ratio}));
// A generous relative guard: observed speedup is ~4x. Returning the original
// allocation-heavy loop is ~1x and must fail even on a fast CI host.
assert(ratio<.75,`Exact-number performance regression: ratio ${ratio.toFixed(3)} (limit 0.75)`);
