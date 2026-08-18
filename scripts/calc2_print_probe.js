/* ФАЗА 7. Замер печати: что уходит на лист и что остаётся на экране после.
   Отвечает на пункты 71–74 аудита.
   Запуск: node scripts/calc2_print_probe.js <порт> [сцена]                   */
const { chromium } = require('playwright');
const PORT = process.argv[2] || '8601';
const KEY  = process.argv[3] || 'tax';
const BASE = `http://127.0.0.1:${PORT}`;
(async () => {
  const br = await chromium.launch();
  const p = await br.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto(BASE + '/login/');
  if (p.url().includes('login')) {
    await p.fill('input[name="username"]', 'student1');
    await p.fill('input[name="password"]', 'student12345');
    await p.click('button[type=submit], input[type=submit]');
    await p.waitForLoadState('domcontentloaded');
  }
  await p.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await p.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  await p.evaluate(k => pickScene(k), KEY);
  await p.waitForTimeout(600);

  const before = await p.evaluate(() => {
    const s = document.getElementById('chart');
    return { w: Math.round(s.getBoundingClientRect().width), h: Math.round(s.getBoundingClientRect().height),
             viewBox: s.getAttribute('viewBox') || '—' };
  });
  await p.emulateMedia({ media: 'print' });
  await p.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  await p.waitForTimeout(400);
  const on = await p.evaluate(() => {
    const vis = (sel) => { const e = document.querySelector(sel); if (!e) return 'нет'; 
      const c = getComputedStyle(e); return (c.display === 'none' || c.visibility === 'hidden') ? 'скрыт' : 'ВИДЕН'; };
    const s = document.getElementById('chart');
    const st = document.getElementById('print-stats');
    return { nav: vis('nav'), dock: vis('.dock'), side: vis('.side'),
             viewBox: s.getAttribute('viewBox') || '—',
             chart: Math.round(s.getBoundingClientRect().width) + '×' + Math.round(s.getBoundingClientRect().height),
             statsW: st ? Math.round(st.getBoundingClientRect().width) : -1,
             pageW: Math.round(document.body.getBoundingClientRect().width) };
  });
  /* ⚠️ ПОРЯДОК ВАЖЕН И ПОВТОРЯЕТ БРАУЗЕР: печатные стили снимаются ПЕРЕД
     событием afterprint. Обратный порядок мерил бы перерисовку в печатной
     раскладке, и «холст не вернулся» было бы выдумкой самого прибора. */
  await p.emulateMedia({ media: 'screen' });
  await p.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await p.waitForTimeout(900);
  const after = await p.evaluate(() => {
    const s = document.getElementById('chart');
    return { w: Math.round(s.getBoundingClientRect().width), h: Math.round(s.getBoundingClientRect().height),
             viewBox: s.getAttribute('viewBox') || '—' };
  });
  console.log('до печати  ', JSON.stringify(before));
  console.log('при печати ', JSON.stringify(on));
  console.log('после      ', JSON.stringify(after));
  console.log('П71 шапка скрыта:', on.nav === 'скрыт' || on.nav === 'нет');
  console.log('П72 viewBox задан:', on.viewBox !== '—');
  console.log('П73 таблица уже листа:', on.statsW > 0 && on.statsW < on.pageW * 0.75);
  console.log('П74 холст вернулся:', after.w === before.w && after.h === before.h && after.viewBox === before.viewBox);
  await br.close();
})();
