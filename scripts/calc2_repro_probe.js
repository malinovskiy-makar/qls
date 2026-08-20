/* ФАЗА 0 сессии 21.08. ВОСПРОИЗВЕСТИ ДВА ДЕФЕКТА ПРИЁМКИ ДО ЕДИНОЙ ПРАВКИ.

   Смысл фазы: сначала увидеть болезнь своими глазами и снять числа, потом
   лечить. Прошлая сессия отчиталась зелёным по обоим местам, значит её приборы
   мерили не то — этот идёт ровно тем путём, каким шёл владелец: щелчок по
   полю, набор с клавиатуры, нажатие «Построить», чтение состояния.

   Запуск: node scripts/calc2_repro_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8099';
const OUT  = process.argv[3] || 'reports/calc2_repro.json';
const BASE = `http://127.0.0.1:${PORT}`;

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

async function openScene(page, key) {
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object',
                             null, { timeout: 20000 });
  await page.evaluate(k => pickScene(k), key);
  await page.waitForTimeout(900);
  await page.evaluate(() => {
    document.querySelectorAll('#tools-panel .section, #params-panel .section, .sb .section')
      .forEach(s => { if (s.id) openSection(s.id); });
    document.querySelectorAll('.fold-btn').forEach(b => {
      if (b.getAttribute('aria-expanded') === 'false') b.click();
    });
  });
  await page.waitForTimeout(650);
}

/* Отпечаток видимых линий кривых — тот же признак, что в приборе параметров:
   непрозрачная обводка, без заливки, не помечен как невыгружаемый. */
const CURVE_SHOT = () => {
  const round = d => String(d || '').replace(/-?\d+\.\d+/g, m => (+m).toFixed(1));
  return [...document.querySelectorAll('#chart path')].filter(p => {
    if (p.getAttribute('data-skip-export') === '1') return false;
    const c = getComputedStyle(p);
    if (!c.stroke || c.stroke === 'none') return false;
    if (/rgba\((?:\d+,\s*){3}0\)|transparent/.test(c.stroke)) return false;
    if (c.fill && c.fill !== 'none' && !/rgba\((?:\d+,\s*){3}0\)/.test(c.fill)) return false;
    if (parseFloat(c.strokeOpacity || '1') < 0.05) return false;
    return (p.getAttribute('d') || '').length > 12;
  }).map(p => round(p.getAttribute('d'))).join('|');
};

async function aimAt(page, id) {
  for (let t = 0; t < 3; t++) {
    const g = await page.evaluate((id) => {
      const inp = document.getElementById(id);
      if (!inp) return null;
      const wrap = inp.closest('.f-wrap') || inp.parentElement;
      let el = inp;
      const mf = wrap && wrap.querySelector('math-field');
      if (mf && mf.getClientRects().length) el = mf;
      if (!el.getClientRects().length) el = wrap;
      if (!el || !el.getClientRects().length) return null;
      el.scrollIntoView({ block: 'center', inline: 'nearest' });
      const r = el.getBoundingClientRect();
      const x = r.x + r.width / 2, y = r.y + r.height / 2;
      const top = document.elementFromPoint(x, y);
      return { x, y, w: r.width, hit: !!(top && (el.contains(top) || top === el)) };
    }, id);
    if (!g) return null;
    if (g.hit || t === 2) return g;
    await page.waitForTimeout(150);
  }
  return null;
}

async function clickButton(page, btnId) {
  const g = await page.evaluate((bid) => {
    const b = document.getElementById(bid);
    if (!b || !b.getClientRects().length) return null;
    b.scrollIntoView({ block: 'center' });
    const r = b.getBoundingClientRect();
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    const top = document.elementFromPoint(x, y);
    return { x, y, hit: !!(top && b.contains(top)) };
  }, btnId);
  if (!g || !g.hit) return false;
  await page.mouse.click(g.x, g.y);
  await page.waitForTimeout(500);
  return true;
}

// Живой набор формулы в поле: щелчок → выделить всё → набрать поверх.
async function typeInto(page, id, text) {
  const g = await aimAt(page, id);
  if (!g || !g.hit) return { ok: false, why: 'щелчок не попадает в поле' };
  await page.mouse.click(g.x, g.y);
  await page.waitForTimeout(120);
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
  await page.keyboard.type(text, { delay: 12 });
  await page.waitForTimeout(250);
  const got = await page.evaluate(i => (document.getElementById(i) || {}).value, id);
  return { ok: true, got };
}

// Геометрия кривой при заданном значении буквы (значение ставим ползунком-состоянием,
// сам факт «двигает ли ползунок» меряет прибор параметров; здесь важна ФОРМУЛА).
async function shotAt(page, letter, value) {
  await page.evaluate(([P, v]) => {
    if (STATE.params && STATE.params[P]) {
      STATE.params[P].min = Math.min(STATE.params[P].min, v);
      STATE.params[P].max = Math.max(STATE.params[P].max, v);
      STATE.params[P].value = v;
    }
    if (typeof STATE.ppfSumData !== 'undefined') STATE.ppfSumData = null;
    redrawAll();
  }, [letter, value]);
  await page.waitForTimeout(400);
  return await page.evaluate(CURVE_SHOT);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await login(page);
  const out = { pageErrors: errs };

  /* ── 0.1 · КПВ: буква в формуле сцены ─────────────────────────────── */
  {
    await openScene(page, 'ppf');
    const before = await page.evaluate(() => ({
      ppfFormula: STATE.ppfFormula, field: (document.getElementById('inp-ppf') || {}).value,
    }));
    const typed = await typeInto(page, 'inp-ppf', 'y = 100 - a*x');
    const built = await clickButton(page, 'btn-ppf-apply');
    const after = await page.evaluate(() => ({
      ppfFormula: STATE.ppfFormula,
      field: (document.getElementById('inp-ppf') || {}).value,
      params: Object.keys(STATE.params || {}),
      paramA: STATE.params && STATE.params.a ? { ...STATE.params.a } : null,
      err: (document.getElementById('ppf-error') || {}).textContent || '',
    }));
    const d1  = await shotAt(page, 'a', 1);
    const d10 = await shotAt(page, 'a', 10);
    out.ppf = { before, typed, built, after,
                dAtA1: d1.slice(0, 240), dAtA10: d10.slice(0, 240),
                curveMoved: d1 !== d10 };
  }

  /* ── 0.1б · КТВ. Одна страна ───────────────────────────────────────── */
  {
    await openScene(page, 'trade');
    const before = await page.evaluate(() => ({
      ppftFormula: STATE.ppftFormula, field: (document.getElementById('inp-ppft') || {}).value,
    }));
    const typed = await typeInto(page, 'inp-ppft', '100 - a*X');
    const built = await clickButton(page, 'btn-ppft-apply');
    const after = await page.evaluate(() => ({
      ppftFormula: STATE.ppftFormula,
      field: (document.getElementById('inp-ppft') || {}).value,
      params: Object.keys(STATE.params || {}),
    }));
    const d1  = await shotAt(page, 'a', 1);
    const d10 = await shotAt(page, 'a', 10);
    out.trade = { before, typed, built, after,
                  dAtA1: d1.slice(0, 240), dAtA10: d10.slice(0, 240),
                  curveMoved: d1 !== d10 };
  }

  /* ── 0.2 · «Составной спрос»: пропали поля формул ──────────────────── */
  const panels = {};
  for (const key of ['sd', 'tax', 'mono', 'mono-kink', 'mono-d3', 'monoexport']) {
    await openScene(page, key);
    panels[key] = await page.evaluate(() => ({
      drawsList: typeof sceneDrawsCurveList === 'function' ? sceneDrawsCurveList() : null,
      mathFields: document.querySelectorAll('math-field').length,
      formulaInputs: [...document.querySelectorAll('#tools-panel input[type=text]')]
        .filter(i => i.getClientRects().length).map(i => i.id).filter(Boolean),
      cards: [...document.querySelectorAll('#tools-panel .section')]
        .filter(s => s.getClientRects().length)
        .map(s => {
          const h = s.querySelector('.section-head, .sec-head, h3, .fold-btn');
          const body = s.querySelector('.section-body, .sec-body');
          return {
            id: s.id,
            title: (h ? h.textContent : '').replace(/\s+/g, ' ').trim().slice(0, 46),
            body: (body ? body.textContent : '').replace(/\s+/g, ' ').trim().slice(0, 80),
          };
        }),
    }));
  }
  out.panels = panels;

  fs.writeFileSync(OUT, JSON.stringify(out, null, 1), 'utf8');
  await browser.close();
  console.log('записано:', OUT, '· ошибок страницы:', errs.length);
})();
