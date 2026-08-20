/* Замер п. 30 и п. 31: галочка «Только первая четверть» держит окно при
   панорамировании, а появление кнопки возврата масштаба не двигает соседние
   кнопки. Запуск: node scripts/calc2_view_probe.js */
const { chromium } = require('playwright');
const BASE='http://127.0.0.1:8601';
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1440,height:900}});
p.on('pageerror',e=>console.log('ОШИБКА:',e.message));
await p.goto(BASE+'/login/',{waitUntil:'domcontentloaded'});
if(p.url().includes('login')){await p.fill('input[name="username"]','student1');await p.fill('input[name="password"]','student12345');await p.click('button[type=submit], input[type=submit]');await p.waitForLoadState('domcontentloaded');}
await p.goto(BASE+'/calc2/',{waitUntil:'load'});
await p.waitForFunction(()=>typeof pickScene==='function',null,{timeout:20000});
await p.evaluate(()=>{closePicker&&closePicker();pickScene('sd');});
await p.waitForTimeout(700);
const r=await p.evaluate(()=>{
  const wrenchTop=()=>Math.round(document.getElementById('btn-wrench').getBoundingClientRect().top);
  const before=wrenchTop();
  STATE.firstQuad=true;
  panByPixels(-400,-400); panByPixels(-400,-400);
  const onQ={q:CONFIG.Qmin,p:CONFIG.Pmin};
  const afterZoomBtn=wrenchTop();
  resetZoom();
  STATE.firstQuad=false;
  panByPixels(-400,-400);
  const offQ={q:CONFIG.Qmin,p:CONFIG.Pmin};
  resetZoom();
  return {before, afterZoomBtn, onQ, offQ, ticks: document.querySelectorAll('#chart text.axis-num').length};
});
console.log('ключ до появления кнопки:', r.before, '· после:', r.afterZoomBtn,
            r.before===r.afterZoomBtn ? '· НЕ СДВИНУЛСЯ ✓' : '· СДВИНУЛСЯ ✗');
console.log('галочка включена → Qmin/Pmin:', r.onQ.q.toFixed(2), r.onQ.p.toFixed(2),
            (r.onQ.q>=-1e-9 && r.onQ.p>=-1e-9) ? '· в четверти ✓' : '· пробило ✗');
console.log('галочка снята → Qmin/Pmin:', r.offQ.q.toFixed(2), r.offQ.p.toFixed(2),
            (r.offQ.q<0||r.offQ.p<0) ? '· свободно ✓' : '· не двинулось ✗');
await b.close();})();
