/* Фаза 12 — сцены с ДВУМЯ графиками: связаны ли они.
   Поля разбираются по положению на холсте: у каждого своя полоса. Меняем то,
   что задаёт модель, и смотрим, поменялись ли ОБА поля.
     node calc2/tests/night2_phase12_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin'); await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const rows = [];
for (const key of scenes) {
  const r = await page.evaluate(async (k) => {
    const sleep = ms => new Promise(res => setTimeout(res, ms));
    resetSceneMemory(); pickScene(k); setToolsOpen(true);
    await sleep(520);
    /* ЧИСЛО ПОЛЕЙ СЧИТАЕМ ПО ОСЯМ СО СТРЕЛКАМИ, а не по разрывам между
       путями: разрыв ловил декоративные мелочи и объявлял вторым полем
       наконечник стрелки. У каждого поля своя горизонтальная ось, и она
       единственная линия со стрелкой на конце. */
    const axesY = [].slice.call(document.querySelectorAll('#chart line[marker-end]'))
      .filter(l => Math.abs(+l.getAttribute('y1') - +l.getAttribute('y2')) < 1.5)
      .map(l => +l.getAttribute('y1'))
      .sort((a, b2) => a - b2)
      .filter((v, i, arr) => i === 0 || Math.abs(v - arr[i - 1]) > 8);
    const two = axesY.length >= 2;
    const gap = two ? Math.round(axesY[1] - axesY[0]) : 0;
    // Граница между полями — посередине между их горизонтальными осями.
    const split = two ? (axesY[0] + axesY[1]) / 2 : null;
    if (!two) return { key: k, panes: axesY.length || 1, осей: axesY.length };
    /* ⚠️ ПУТЬ ОТНОСИМ К ПОЛЮ ПО ЕГО ТОЧКАМ, А НЕ ПО РАМКЕ.
       Рамка кривой, уходящей за край, растягивается на оба поля, и по её
       середине путь попадал не туда. Считаем, сколько точек пути лежит выше
       границы и сколько ниже, и складываем подписи в оба поля пропорционально
       — тогда изменение видно в том поле, где оно произошло. */
    const sig = () => {
      const acc = { top: 0, bot: 0, nTop: 0, nBot: 0 };
      [].slice.call(document.querySelectorAll('#chart path')).forEach(p => {
        const d = p.getAttribute('d') || ''; if (!d) return;
        const nums = (d.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
        if (nums.length < 4) return;
        let sTop = 0, sBot = 0, cTop = 0, cBot = 0;
        for (let i = 0; i + 1 < nums.length; i += 2) {
          const y = nums[i + 1];
          if (!two || y < split) { sTop += nums[i] + y; cTop++; } else { sBot += nums[i] + y; cBot++; }
        }
        if (cTop) { acc.top += sTop; acc.nTop++; }
        if (cBot) { acc.bot += sBot; acc.nBot++; }
      });
      return { top: Math.round(acc.top * 100) / 100, bot: Math.round(acc.bot * 100) / 100, nTop: acc.nTop, nBot: acc.nBot };
    };
    const before = sig();
    // Толкаем модель: первое активное поле формулы, иначе первый ползунок панели.
    let poke = null;
    const f = (typeof FORMULA_FIELDS !== 'undefined')
      ? FORMULA_FIELDS.filter(i => i.isConnected && fieldActive(i) && (i.value || '').trim().length > 1)[0] : null;
    if (f) {
      const orig = f.value;
      const body = orig.indexOf('=') >= 0 ? orig.slice(orig.indexOf('=') + 1).trim() : orig.trim();
      const pfx = orig.indexOf('=') >= 0 ? orig.slice(0, orig.indexOf('=') + 1) + ' ' : '';
      f.value = pfx + '0.8*(' + body + ')';
      ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
      f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      poke = 'поле ' + f.id;
      await sleep(450);
      const btn = [].slice.call(document.querySelectorAll('#tools-panel button'))
        .filter(b => /Постро/i.test(b.textContent || '') && b.getClientRects().length)[0];
      if (btn) { btn.click(); poke += ' + кнопка'; await sleep(450); }
    } else {
      const sl = document.querySelector('#params-body input[type=range]');
      if (sl) {
        const mn = parseFloat(sl.min), mx = parseFloat(sl.max);
        sl.value = String(parseFloat(sl.value) + (mx - mn) * 0.2);
        sl.dispatchEvent(new Event('input', { bubbles: true }));
        poke = 'ползунок'; await sleep(450);
      }
    }
    const after = sig();
    return { key: k, panes: two ? 2 : 1, gap: Math.round(gap), poke,
      topChanged: Math.abs(after.top - before.top) > 1e-6,
      botChanged: Math.abs(after.bot - before.bot) > 1e-6,
      before, after };
  }, key);
  rows.push(r);
}
const two = rows.filter(r => r.panes === 2);
console.log(JSON.stringify({ всегоСцен: rows.length, сДвумяПолями: two.length, поля: two }, null, 1));
if (errs.length) console.log('ОШИБКИ: ' + errs.slice(0, 5).join(' | '));
await browser.close();
