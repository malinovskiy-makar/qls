/* PDF через сайт (доказательство фазы 1 и сценарий приёмки 10): вошедший
   пользователь собирает PDF той же дверью, что кнопка «Скачать → PDF»
   (exportPDFSend: buildTex → POST /calc2/export/pdf/), для пяти моделей
   разных семей; в одной — своя точка, посчитанная площадь и заголовок с
   опасными знаками. Гость получает отказ (PDF только вошедшим).

   node calc2/tests/tex/pdf_site.mjs
   Нужны CALC2_BASE_URL, CALC2_USER, CALC2_PASS (бот приборов) и pdflatex на
   машине сервера. Код возврата 1, если хоть один PDF не собрался или гость
   получил PDF. */
import { chromium } from 'playwright';
import { BASE, prime, openScene } from './lib.mjs';

const USER = process.env.CALC2_USER || 'shot_bot';
const PASS = process.env.CALC2_PASS || '';
const CASES = [
  { key: 'taxes', title: 'Рынок хлеба: 50% & выше' },
  { key: 'labor-bilat', title: '' },
  { key: 'mono-kink', title: 'Ломаный спрос' },
  { key: 'ppfsum', title: '' },
  { key: 'm-tangent', title: 'Производная' },
];

const browser = await chromium.launch();
let bad = 0;
async function send(page, title) {
  return page.evaluate(async (t) => {
    const body = new FormData();
    body.append('tex', buildTex(t, ''));
    body.append('name', exportBaseName());
    body.append('csrfmiddlewaretoken', (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '');
    const r = await fetch(CALC2_PDF_URL, { method: 'POST', body });
    const buf = new Uint8Array(await r.arrayBuffer());
    const head = String.fromCharCode.apply(null, Array.from(buf.slice(0, 5)));
    return { status: r.status, type: r.headers.get('content-type') || '', size: buf.length, head,
             text: head === '%PDF-' ? '' : new TextDecoder().decode(buf.slice(0, 300)) };
  }, title);
}

// Вошедший пользователь
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 760 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  const page = await ctx.newPage();
  page.setDefaultTimeout(60000);
  await page.goto(BASE + '/login/', { waitUntil: 'load' });
  await page.fill('#id_username', USER);
  await page.fill('#id_password', PASS);
  await Promise.all([page.waitForNavigation({ waitUntil: 'load' }), page.press('#id_password', 'Enter')]);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object');
  await prime(page);
  for (const c of CASES) {
    await openScene(page, c.key);
    if (c.key === 'taxes') {
      // своя точка (30; 70) и площадь под спросом на [10; 40] — тот же рецепт, что marks-area в наборе (40-extra)
      await page.evaluate(() => {
        STATE.marks.push(newMark(30, 70, null, 'coords'));
        if (typeof renderMarkList === 'function') renderMarkList();
        syncAreaCalcUI();
        document.getElementById('ac-pick').value = areaTargets()[0].name;
        STATE.acFrom = 10; STATE.acTo = 40; runAreaCalc();
        redrawAll();
      });
      await page.waitForTimeout(400);
    }
    const r = await send(page, c.title);
    const ok = r.status === 200 && r.head === '%PDF-' && /pdf/.test(r.type) && r.size > 2000;
    if (!ok) bad++;
    console.log((ok ? 'PDF ' : 'НЕТ PDF ') + c.key.padEnd(12) + ' код ' + r.status + ' | ' + r.type + ' | ' + r.size + ' байт' + (c.title ? ' | заголовок «' + c.title + '»' : '') + (ok ? '' : ' | ' + r.text.replace(/\s+/g, ' ')));
  }
  await ctx.close();
}
// Гость: страница открыта, PDF — отказ
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 760 }, reducedMotion: 'reduce', locale: 'ru-RU' });
  const page = await ctx.newPage();
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object');
  await prime(page);
  await openScene(page, 'taxes');
  const r = await send(page, '');
  const refused = r.head !== '%PDF-';
  if (!refused) bad++;
  console.log((refused ? 'гостю отказано' : 'ГОСТЬ ПОЛУЧИЛ PDF') + ' | код ' + r.status);
  await ctx.close();
}
await browser.close();
console.log(bad ? 'ПРОВАЛОВ ' + bad : 'PDF через сайт: все ' + CASES.length + ' собрались, гостю отказано');
process.exit(bad ? 1 : 0);
