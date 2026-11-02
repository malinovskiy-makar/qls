/* Аудит эталонов; --append-new-computed разрешает только добавления из белого списка. */
import {chromium} from 'playwright';
import fs from 'node:fs';
import * as L from '../../calc2/tests/redesign/lib.mjs';
const dir='calc2/tests/redesign/baseline';
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1440,height:760},reducedMotion:'reduce'});
await page.goto(process.env.CALC2_BASE_URL+'/calc2/');await page.waitForFunction(()=>typeof pickScene==='function');
await page.addScriptTag({content:L.INPAGE});
const ignore=new Set(['crosses','sceneKey','legendSpot','tanTop','tanBot']);
function diff(a,b,path='',out=[]){
  if(JSON.stringify(a)===JSON.stringify(b))return out;
  if(a&&b&&typeof a==='object'&&typeof b==='object'&&!Array.isArray(a)&&!Array.isArray(b)){
    for(const k of new Set([...Object.keys(a),...Object.keys(b)])){
      if(!path&&(ignore.has(k)||/Sig$/.test(k)))continue;
      if(!path&&k==='areaHidden'&&!(k in a)&&Array.isArray(b[k])&&!b[k].length)continue;
      diff(a[k],b[k],path?path+'.'+k:k,out);
    }
  }else out.push({path,kind:a===undefined?'added':b===undefined?'removed':'changed',before:a,after:b});
  return out;
}
const report=[];
for(const file of fs.readdirSync(dir).filter(f=>f.endsWith('.json'))){
  const key=file.slice(0,-5),old=JSON.parse(fs.readFileSync(dir+'/'+file));
  await page.evaluate(k=>{resetSceneMemory();pickScene(k);},key);await L.settle(page);await page.evaluate(()=>redrawAll());await L.settle(page);
  const state=await page.evaluate(()=>window.__RD.stateDump());
  const changes=diff(old.start.state,state);if(changes.length){report.push({key,changes});console.log(JSON.stringify({key,changes}));}
}
fs.mkdirSync('.calc2-astra-local/audit',{recursive:true});fs.writeFileSync('.calc2-astra-local/audit/e2-starts.json',JSON.stringify(report,null,2));
await browser.close();
if(process.argv.includes('--append-new-computed')) {
  if(fs.realpathSync('.')!=='/private/tmp/calc2-astra-local-20261102/calc2-astra-work')throw Error('Only isolated execution checkout');
  const models=new Set(['mono','mono-d1','mono-d3','mono-kink','mono-nat','monoexport']);
  const allowed=new Set(['mono.alts','mono.dwlAlts','mono.gain','discr3.alts','discr3.gain','kinked.alts','kinked.dwlAlts','kinked.noProd']);
  const plans=[];
  for(const row of report){
    if(!models.has(row.key))throw Error('Unexpected changed model: '+row.key);
    const file=dir+'/'+row.key+'.json',original=fs.readFileSync(file),rec=JSON.parse(original);
    for(const change of row.changes){
      if(change.kind==='added'&&allowed.has(change.path)){
        if(change.path.startsWith('discr3.')&&!['mono-d3','monoexport'].includes(row.key))throw Error('Unexpected discr3');
        if(change.path.startsWith('kinked.')&&row.key!=='mono-kink')throw Error('Unexpected kinked');
      }else if(row.key==='mono-kink'&&change.path==='kinked.cands'&&change.kind==='changed'){
        const old=change.before.map(x=>JSON.stringify(x));
        const retained=change.after.filter(x=>old.includes(JSON.stringify(x)));
        if(JSON.stringify(retained)!==JSON.stringify(change.before))throw Error('An old candidate changed');
        const added=change.after.filter(x=>!old.includes(JSON.stringify(x)));
        if(added.length!==2||!added.some(x=>x.Q===0&&x.kind==='Q = 0'&&x.profit===0)||!added.some(x=>x.Q===160&&x.kind==='граница'&&x.profit===-3200))throw Error('Unexpected candidates');
      }else throw Error('Old value or unapproved path changed: '+row.key+'.'+change.path);
      const [parent,key]=change.path.split('.');rec.start.state[parent][key]=change.after;
    }
    // stateDump сортирует ключи, а старый stateDiff сравнивает сериализацию.
    for(const parent of new Set(row.changes.map(c=>c.path.split('.')[0]))) {
      const obj=rec.start.state[parent];rec.start.state[parent]=Object.fromEntries(Object.keys(obj).sort().map(k=>[k,obj[k]]));
    }
    const data=original.toString().replace(/("start": \{\n "state": )([^\n]+)(\n)/,
      (_,prefix,line,end)=>prefix+JSON.stringify(rec.start.state)+','+end);
    if(JSON.stringify(JSON.parse(data))!==JSON.stringify(rec))throw Error('Baseline layout not recognized');
    plans.push({file,original,data});
  }
  // Все 44 модели и все старые значения проверены ДО первой записи.
  const backup='.calc2-astra-local/audit/baseline-before';fs.mkdirSync(backup,{recursive:true});
  for(const p of plans){
    fs.writeFileSync(backup+'/'+p.file.split('/').pop(),p.original);
    fs.writeFileSync(p.file+'.astra-tmp',p.data);fs.renameSync(p.file+'.astra-tmp',p.file);
  }
  console.log('APPENDED computed fields only:',plans.length,'models; old values preserved');
}
