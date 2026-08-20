/* ФАЗА 8. ПЕРЕИМЕНОВАНИЕ ТОЧКИ И КРИВОЙ НА ХОЛСТЕ.

   Правка открывается НАСТОЯЩИМ двойным щелчком по подписи: предмет фазы — что
   человек видит и делает, а не то, что можно позвать функцией.

   Запуск: node scripts/calc2_rename_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/rename.json';
const BASE = `http://127.0.0.1:${PORT}`;
const ok = [], bad = [];
const check = (c, w) => (c ? ok : bad).push(w);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
  const open = async (key) => {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(1000);
  };
  const labelSpot = () => {
    const t = document.querySelector('#chart text.curve-name');
    if (!t) return null;
    const r = t.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2, text: t.textContent.trim() };
  };

  await open('sd');
  const spot = await page.evaluate(labelSpot);
  check(!!spot, 'на холсте есть подпись кривой: «' + (spot ? spot.text : '') + '»');
  await page.mouse.dblclick(spot.x, spot.y);
  await page.waitForTimeout(400);

  const look = await page.evaluate(() => {
    const inp = document.getElementById('pt-rename');
    if (!inp) return null;
    const cs = getComputedStyle(inp);
    const lab = Array.from(document.querySelectorAll('#chart text.curve-name'))
      .filter(t => getComputedStyle(t).visibility === 'hidden').length;
    return {
      bg: cs.backgroundColor, border: cs.borderTopWidth,
      dash: cs.borderBottomStyle, dashColor: cs.borderBottomColor,
      width: +inp.getBoundingClientRect().width.toFixed(1),
      selected: inp.selectionStart === 0 && inp.selectionEnd === inp.value.length,
      value: inp.value, hiddenLabels: lab,
    };
  });
  check(!!look, 'двойной щелчок открыл правку прямо на холсте');
  if (look) {
    check(/rgba\(0, 0, 0, 0\)|transparent/.test(look.bg), 'фона у поля нет: ' + look.bg);
    check(parseFloat(look.border) === 0, 'рамки у поля нет: ' + look.border);
    check(look.dash === 'dashed', 'подчёркивание пунктирное: ' + look.dash);
    check(/190, 24, 93|255, 77, 148/.test(look.dashColor), 'пунктир акцентный: ' + look.dashColor);
    check(look.selected, 'содержимое выделено целиком');
    check(look.hiddenLabels === 1, 'сама подпись на время правки спрятана (текст не двоится)');

    const w0 = look.width;
    await page.keyboard.type('Длинное имя кривой');
    await page.waitForTimeout(250);
    const w1 = await page.evaluate(() => +document.getElementById('pt-rename').getBoundingClientRect().width.toFixed(1));
    check(w1 > w0 + 10, 'подчёркивание тянется за словом: ' + w0 + ' → ' + w1);

    // не вылезает за холст
    const inside = await page.evaluate(() => {
      const inp = document.getElementById('pt-rename');
      const wrap = document.getElementById('graph-wrap').getBoundingClientRect();
      const r = inp.getBoundingClientRect();
      return { left: +(r.left - wrap.left).toFixed(1), right: +(wrap.right - r.right).toFixed(1),
               lines: Math.round(r.height / parseFloat(getComputedStyle(inp).fontSize)) };
    });
    check(inside.left >= -0.5 && inside.right >= -0.5,
          'поле целиком внутри холста: слева ' + inside.left + ', справа ' + inside.right);

    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    const afterEsc = await page.evaluate(() => ({
      gone: !document.getElementById('pt-rename'),
      text: (document.querySelector('#chart text.curve-name') || {}).textContent,
      visible: document.querySelector('#chart text.curve-name')
        ? getComputedStyle(document.querySelector('#chart text.curve-name')).visibility : null,
    }));
    check(afterEsc.gone, 'Escape закрыл правку');
    check((afterEsc.text || '').trim() === spot.text, 'Escape отменил: имя прежнее «' + afterEsc.text + '»');
    check(afterEsc.visible === 'visible', 'подпись снова видна');
  }

  // пустое имя откатывается
  const spot2 = await page.evaluate(labelSpot);
  await page.mouse.dblclick(spot2.x, spot2.y);
  await page.waitForTimeout(350);
  await page.evaluate(() => { const i = document.getElementById('pt-rename'); i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(450);
  const afterEmpty = await page.evaluate(() => (document.querySelector('#chart text.curve-name') || {}).textContent);
  check((afterEmpty || '').trim() === spot2.text, 'пустое имя не сохранилось: «' + afterEmpty + '»');

  // сохранение по Enter
  const spot3 = await page.evaluate(labelSpot);
  await page.mouse.dblclick(spot3.x, spot3.y);
  await page.waitForTimeout(350);
  await page.keyboard.type('Спрос жителей');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  const saved = await page.evaluate(() =>
    Array.from(document.querySelectorAll('#chart text.curve-name')).map(t => t.textContent.trim()));
  check(saved.some(t => /Спрос жителей/.test(t)), 'Enter сохранил новое имя: ' + JSON.stringify(saved));

  fs.writeFileSync(OUT, JSON.stringify({ ok, bad, look, pageErrors: errs }, null, 1), 'utf8');
  console.log('\n── ФАЗА 8 ─────────────────────────────────────────');
  ok.forEach(t => console.log('  v ' + t));
  bad.forEach(t => console.log('  X ' + t));
  console.log('\nитог: ' + ok.length + ' сошлось, ' + bad.length + ' нет · ошибок страницы: ' + errs.length);
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})();
