/* А2 24.10: общий помощник приборов сессии — открыть страницу с открытым «Ответом» и снять его содержимое.
   dumpAnswer(page) → { groups: [{head, cells: [{src, lab, not, val, was}]}], blocks: [{id, title, rows}] } */
import { chromium } from 'playwright';
import { keepAnswerOpen, answerShown } from '../../calc2/tests/answer_open.mjs';

export const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';

export async function openPage(width = 1440) {
  const browser = keepAnswerOpen(await chromium.launch());
  const page = await (await browser.newContext({ viewport: { width, height: 950 } })).newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const run = (code) => page.evaluate(async (c) => { const out = (new Function(c))(); await new Promise(r => setTimeout(r, 120)); return out; }, code);
  return { browser, page, errs, run, shown: () => answerShown(page) };
}

export const MKT = `
  var setDS = function (scene, d, s) {
    resetSceneMemory(); pickScene(scene);
    if (d) updateCurveExpr(STATE.curves.find(function (c) { return c.role === 'demand'; }), d);
    var low = STATE.curves.find(function (c) { return c.role === 'supply' || c.role === 'mc'; });
    if (low && s) updateCurveExpr(low, s);
    redrawAll();
  };
`;

/* Снимок «Ответа» после сборки (ждём кадр и таймер scheduleAnswer). */
export async function dumpAnswer(page) {
  await page.waitForTimeout(450);
  return page.evaluate(() => {
    const t = (el) => { if (!el) return ''; const c = el.cloneNode(true); c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove()); return c.textContent.replace(/[\s   ​]+/g, ' ').trim(); };
    const shown = (el) => { for (let n = el; n && n.id !== 'params-panel'; n = n.parentElement) { if (n.hidden) return false; const cs = getComputedStyle(n); if (cs.display === 'none' || cs.visibility === 'hidden') return false; } return true; };
    const groups = [...document.querySelectorAll('#ans-hero > .ans-group')].map(g => ({
      head: t(g.querySelector('.ans-ghead')),
      cells: [...g.querySelectorAll('.ans-cell')].map(c => ({ src: c.dataset.src, lab: t(c.querySelector('.ans-lab')), not: t(c.querySelector('.ans-not')), val: t(c.querySelector('.ans-val')), was: t(c.querySelector('.ans-was')) })),
    }));
    const status = [...document.querySelectorAll('#ans-status .ans-status')].map(t);
    const blocks = [...document.querySelectorAll('#sb-body > [id]')].filter(shown).map(b => {
      const title = t(b.querySelector(':scope > .section-title')) || getComputedStyle(b, '::before').content.replace(/^"|"$/g, '');
      const rows = [...b.querySelectorAll('.stat, .sb-subsec, tr')].filter(shown).map(r => t(r)).filter(Boolean);
      return { id: b.id, title: title === 'none' ? '' : title, rows };
    }).filter(b => b.rows.length);
    return { groups, status, blocks };
  });
}

/* Короткая строка для таблицы README: «Группа: подпись = значение (было) · …». */
export function brief(d) {
  return d.groups.map(g => (g.head ? '[' + g.head + '] ' : '') + g.cells.map(c => (c.lab + (c.not ? ' ' + c.not : '') + ' = ' + c.val + (c.was ? ' (' + c.was + ')' : ''))).join('; ')).join(' | ');
}
