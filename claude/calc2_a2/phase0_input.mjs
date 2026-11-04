/* Фаза 0 А2: квота — пределы ползунка «Цена внутри коридора»; ввод «P=100-2P» в поле D по символу. */
import { openPage, dumpAnswer, brief, MKT } from './dump.mjs';
const { browser, page, errs, run } = await openPage();
await run(MKT + `setDS('quota', '100-Q', 'Q'); setQuota(40);`);
const q = await run(`var s = document.getElementById('quota-pos-slider') || document.querySelector('[id*=quota][id*=pos]');
  var ids = [...document.querySelectorAll('[id*=quota]')].map(e => e.id + ':' + e.tagName + (e.type ? '/' + e.type : '') + (e.min !== undefined && e.min !== '' ? ' [' + e.min + '…' + e.max + '] =' + e.value : ''));
  return { ids, qt: STATE.qt && { P: STATE.qt.P, Plo: STATE.qt.Plo, Phi: STATE.qt.Phi, cs: STATE.qt.cs, ps: STATE.qt.ps, dwl: STATE.qt.dwl }, pos: STATE.quotaPos };`);
console.log('квота 40:', JSON.stringify(q, null, 1));
await run(`resetSceneMemory(); pickScene('sd'); redrawAll();`);
await page.waitForTimeout(400);
const mf = page.locator('#curve-list .fc-card').first().locator('math-field');
await mf.click();
await page.keyboard.press('Meta+a');
const seen = [];
for (const ch of 'P=100-2P') {
  await page.keyboard.type(ch);
  await page.waitForTimeout(350);   // дребезг поля 220 мс
  seen.push(await run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; }); return ch + ' → expr «' + d.expr + '», eq ' + (STATE.eq ? STATE.eq.Q.toFixed(2) + ';' + STATE.eq.P.toFixed(2) : 'нет');`.replace('ch +', JSON.stringify(ch) + ' +')));
}
await page.keyboard.press('Enter');
await page.waitForTimeout(600);
seen.push(await run(`var d = STATE.curves.find(function (c) { return c.role === 'demand'; }); var card = document.querySelector('#curve-list .fc-card');
  var prob = card.querySelector('.field-problem, .fp-msg, [role=alert]');
  return 'Enter → expr «' + d.expr + '», eq ' + (STATE.eq ? STATE.eq.Q.toFixed(2) + ';' + STATE.eq.P.toFixed(2) : 'нет') + ', ошибка: «' + (prob ? prob.textContent : '') + '»';`));
console.log(seen.join('\n'));
console.log('Ошибок страницы: ' + errs.length);
await browser.close();
