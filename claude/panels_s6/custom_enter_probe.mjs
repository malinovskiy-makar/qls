/* «Своя формула» потребителя: применяется ли набор без Enter (сессия 6, находка; Notion «Надо»).
   node claude/panels_s6/custom_enter_probe.mjs <сервер> */
import * as pw from 'playwright';
const base = process.argv[2];
const b = await pw.chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
await p.goto(base + '/calc2/'); await p.waitForFunction(() => typeof pickScene === 'function' && typeof d3 !== 'undefined');
await p.evaluate(() => { resetSceneMemory(); pickScene('consumer'); closePicker(); setConsumerType('custom'); redrawAll(); });
await p.waitForTimeout(1200);
const before = await p.evaluate(() => STATE.consCustom + ' | ' + JSON.stringify(STATE.cons && [STATE.cons.x, STATE.cons.y]));
const mf = await p.$('#cons-custom-row math-field');
await mf.click(); await p.keyboard.press('Meta+a'); await p.keyboard.type('x*y^2'); await p.waitForTimeout(1500);
const typed = await p.evaluate(() => STATE.consCustom + ' | ' + JSON.stringify(STATE.cons && [STATE.cons.x, STATE.cons.y]));
await p.keyboard.press('Enter'); await p.waitForTimeout(600); console.log('enter', await p.evaluate(() => STATE.consCustom)); await p.mouse.click(700, 400); await p.waitForTimeout(1200);
const blurred = await p.evaluate(() => STATE.consCustom + ' | ' + JSON.stringify(STATE.cons && [STATE.cons.x, STATE.cons.y]));
console.log({ before, typed, blurred });
await b.close();
