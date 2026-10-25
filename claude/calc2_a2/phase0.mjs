/* Фаза 0 сессии А2 (24.10): замер «до». Ничего не чинит — печатает, что «Ответ» показывает сейчас.
     node claude/calc2_a2/phase0.mjs   (сервер на 8099)   JSON=1 — полный снимок */
import { openPage, dumpAnswer, brief, MKT } from './dump.mjs';

const { browser, page, errs, run, shown } = await openPage();
console.log('предусловие «Ответ» открыт:', await shown());
export const CASES = [
  ['smallopen, Pw 30, без вмешательства', `resetSceneMemory(); pickScene('smallopen'); redrawAll();`],
  ['smallopen, тариф 10', `resetSceneMemory(); pickScene('smallopen'); STATE.openTariff = 10; setOpenTool('tariff');`],
  ['smallopen, квота ввоза 20', `resetSceneMemory(); pickScene('smallopen'); STATE.openQuota = 20; setOpenTool('quota');`],
  ['labor-mono, старт (МРОТ 45)', `resetSceneMemory(); pickScene('labor-mono'); redrawAll();`],
  ['labor, старт (МРОТ 45)', `resetSceneMemory(); pickScene('labor'); redrawAll();`],
  ['mono D 120 − P, MC 2Q + 30, без вмешательства', MKT + `setDS('mono', '120-P', '2*Q+30');`],
  ['mono, налог 45', MKT + `setDS('mono', '120-P', '2*Q+30'); setType('tax'); setTax(45); redrawAll();`],
  ['mono, субсидия 30', MKT + `setDS('mono', '120-P', '2*Q+30'); setType('subsidy'); setTax(30); redrawAll();`],
  ['mono, потолок 90', MKT + `setDS('mono', '120-P', '2*Q+30'); setType('ceiling'); setPReg(90); redrawAll();`],
  ['ceil, пол 70', MKT + `setDS('ceil', '100-Q', 'Q'); setType('floor'); setPReg(70); redrawAll();`],
  ['ceil, потолок 40', MKT + `setDS('ceil', '100-Q', 'Q'); setType('ceiling'); setPReg(40); redrawAll();`],
  ['ext, старт', `resetSceneMemory(); pickScene('ext'); redrawAll();`],
  ['ext, MSC = Q + 20 включена', `resetSceneMemory(); pickScene('ext'); STATE.mscExpr = 'Q + 20'; STATE.mscOn = true; syncSocialFields(); recompileSocial(); redrawAll();`],
  ['quota, квота 40', MKT + `setDS('quota', '100-Q', 'Q'); setQuota(40);`],
  ['mono D 120 − P, MC 160 − 4Q', MKT + `setDS('mono', '120-P', '160-4*Q');`],
  ['mono D 100 − Q, MC 20', MKT + `setDS('mono', '100-Q', '20');`],
];
for (const [name, code] of CASES) {
  await run(code);
  const d = await dumpAnswer(page);
  console.log('— ' + name + '\n   ' + (d.status.length ? '{' + d.status.join(' / ') + '} ' : '') + brief(d));
  console.log('   блоки: ' + d.blocks.map(b => b.id + (b.title ? ' «' + b.title + '»' : '') + ': ' + b.rows.join(' · ')).join(' ‖ '));
  if (process.env.JSON) console.log(JSON.stringify(d));
}
console.log('\nОшибок страницы: ' + errs.length + (errs.length ? ' | ' + errs.slice(0, 3).join(' | ') : ''));
await browser.close();
