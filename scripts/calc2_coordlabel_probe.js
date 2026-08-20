/* ФАЗА 3 сессии 20.08. ПОДПИСИ КООРДИНАТ НА ОСЯХ.

   Два вопроса на каждую из 41 сцены:
     1. стоит ли хоть одна подпись координаты ВНУТРИ первой четверти
        (там их быть не должно: цена левее оси цены, количество ниже оси
        количества — решение владельца 19.08);
     2. не пропадают ли подписи при ДРОБНОМ значении. Для этого в поле формулы
        сцены вписывается буква, её ползунок ставится в дробное значение, и
        число подписей сравнивается с тем, что было при целых значениях.

   Второй вопрос и есть суть дефекта: `axisValueX/Y` получали от сцен уже
   набранную строку («54,55»), а на входе стояла проверка `isFinite`, для
   которой запятая — не число. Подпись просто не рисовалась.

   Запуск: node scripts/calc2_coordlabel_probe.js <порт> <файл.json> [сцены] */
const { chromium } = require('playwright');
const fs = require('fs');
const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2_coordlabels.json';
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
  await page.waitForTimeout(950);
}

/* Снимок подписей координат. «Внутри первой четверти» считается по НАСТОЯЩЕЙ
   рамке текста, а не по атрибуту x: у подписи с индексом рамка шире числа. */
const SNAP = () => {
  const own = n => Array.from(n.childNodes).filter(c => c.nodeType === 3).map(c => c.nodeValue).join('').trim();
  const ox = (typeof sx === 'function') ? sx(0) : 0;
  const oy = (typeof sy === 'function') ? sy(0) : 0;
  const list = [...document.querySelectorAll('#chart text.coord-num')].map(t => {
    let b = { x: 0, y: 0, width: 0, height: 0 };
    try { b = t.getBBox(); } catch (e) {}
    return { text: t.getAttribute('data-raw') || own(t) || t.textContent.trim(),
             x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1),
             anchor: t.getAttribute('text-anchor') };
  });
  // Подпись цены обязана целиком лежать левее оси; подпись количества — ниже оси.
  const inside = list.filter(l => (l.x + l.w > ox + 1) && (l.y + l.h < oy - 1));
  const rightOfAxis = list.filter(l => l.anchor !== 'middle' && l.x + l.w > ox + 1);
  return { ox: +ox.toFixed(1), oy: +oy.toFixed(1), n: list.length, list, inside, rightOfAxis };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  let scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  const only = process.argv[4];
  if (only) scenes = scenes.filter(k => only.split(',').indexOf(k) >= 0);
  console.log('сцен:', scenes.length);

  const out = {};
  for (const key of scenes) {
    await openScene(page, key);
    const base = await page.evaluate(SNAP);
    /* Дробные значения. Букву в формулу не вписываем: у большинства сцен есть
       свои числовые органы (ставка, цена), и дробность проще получить ими. Общий
       для всех способ — ползунок буквы, поэтому берём первое поле формулы. */
    const frac = await page.evaluate(() => {
      const live = (typeof FORMULA_FIELDS !== 'undefined' ? FORMULA_FIELDS : [])
        .filter(i => typeof fieldActive === 'function' && fieldActive(i) && (i.value || '').trim());
      if (!live.length) return null;
      const f = live[0];
      const busy = (typeof sceneReserved === 'function') ? sceneReserved() : new Set();
      const P = ['a', 'k', 'm', 'n', 'z'].find(n => !busy.has(n)) || 'z';
      const orig = f.value;
      const re = /(?<![\w.\\])([A-Za-z][A-Za-z0-9]?)(?!\s*\()/;
      const hit = re.exec(orig);
      if (!hit) return null;
      f.value = orig.slice(0, hit.index) + P + '*' + orig.slice(hit.index);
      ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
      f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      // Кнопка «Построить» рядом — сцена применяет формулу только ею.
      const sec = f.closest('.section, .subsec, #tools-panel');
      if (sec) { const b = [...sec.querySelectorAll('button')]
        .find(x => x.getClientRects().length && /^Построить/.test(x.textContent.trim())); if (b) b.click(); }
      redrawAll();
      if (!STATE.params || !STATE.params[P]) return { letter: P, noSlider: true };
      STATE.params[P].value = 1.37;     // заведомо дробное
      redrawAll();
      return { letter: P, value: 1.37 };
    });
    let after = null;
    if (frac && !frac.noSlider) { await page.waitForTimeout(450); after = await page.evaluate(SNAP); }
    out[key] = { base, frac, after };
    process.stdout.write('.');
  }
  console.log('');
  fs.writeFileSync(OUT, JSON.stringify({ scenes: out, pageErrors: errs }, null, 1), 'utf8');
  await browser.close();
  console.log('записано:', OUT, '· ошибок страницы:', errs.length);
})();
