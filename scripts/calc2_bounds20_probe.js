/* ФАЗЫ 4.3 и 4.4 сессии 20.08. РЕДАКТОР ГРАНИЦ И ТОЧНОЕ ЗНАЧЕНИЕ ПАРАМЕТРА.

   Прошлый прибор по границам соврал ровно потому, что не ходил живым путём:
   он ставил значение присваиванием и записал в отчёт «значение 50 при полосе
   −5…3 дало границы 46…54», тогда как живой щелчок мышью давал 150 — поле не
   выделялось, и цифры дописывались к прежнему числу.

   Здесь всё делается указателем и клавиатурой: щелчок по числу, набор, Tab,
   Enter. Ни одного присваивания в состояние.

   Запуск: node scripts/calc2_bounds20_probe.js <порт> */
const { chromium } = require('playwright');
const PORT = process.argv[2] || '8701';
const BASE = `http://127.0.0.1:${PORT}`;
let ok = 0, bad = 0;
const say = (name, got, want) => {
  const good = JSON.stringify(got) === JSON.stringify(want);
  if (good) ok++; else bad++;
  console.log((good ? '✓ ' : '✗ ') + name + ' = ' + JSON.stringify(got) + (good ? '' : ' (ожид ' + JSON.stringify(want) + ')'));
};

async function seedParam(page) {
  // «Построение графиков»: пустой холст, вписываем функцию с буквой живым набором.
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
  await page.evaluate(() => pickScene('m-graph'));
  await page.waitForTimeout(900);
  // Карточки панели закрыты, а поля формул собираются лениво и только когда видны.
  await page.evaluate(() => {
    document.querySelectorAll('#tools-panel .section, #params-panel .section').forEach(s => { if (s.id) openSection(s.id); });
    document.querySelectorAll('.fold-btn').forEach(b => { if (b.getAttribute('aria-expanded') === 'false') b.click(); });
  });
  await page.waitForTimeout(600);
  const g = await page.evaluate(() => {
    const i = (typeof FORMULA_FIELDS !== 'undefined' ? FORMULA_FIELDS.filter(fieldActive)[0] : null) ||
              document.getElementById('inp-formula');
    if (!i) return null;
    const w = i.closest('.f-wrap') || i.parentElement;
    const m = w && w.querySelector('math-field');
    const el = (m && m.getClientRects().length) ? m : i;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  await page.mouse.click(g.x, g.y);
  await page.keyboard.type('10 - a*x', { delay: 15 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(700);
}

// Координаты видимого элемента с проверкой попадания.
async function aim(page, sel, idx) {
  return await page.evaluate(([sel, idx]) => {
    const el = [...document.querySelectorAll(sel)].filter(e => e.getClientRects().length)[idx || 0];
    if (!el) return null;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    return { x, y, hit: !!(el.contains(document.elementFromPoint(x, y)) || document.elementFromPoint(x, y) === el) };
  }, [sel, idx]);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }

  // ── 4.4. Точное значение параметра НАБИРАЕТСЯ ПОВЕРХ, а не дописывается.
  await seedParam(page);
  say('ползунок буквы завёлся', await page.evaluate(() => !!(STATE.params && STATE.params.a)), true);
  let a = await aim(page, '.pchip-param .pchip-label.pchip-editable, .pchip-param .param-eq', 0);
  say('строка «a = 1» доступна щелчку', !!(a && a.hit), true);
  await page.mouse.click(a.x, a.y);
  await page.waitForTimeout(200);
  await page.keyboard.type('50', { delay: 25 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  say('набор 50 поверх 1 даёт 50, а не 150',
      await page.evaluate(() => STATE.params.a.value), 50);
  say('полоса переехала вокруг 50, ширина цела',
      await page.evaluate(() => [+STATE.params.a.min, +STATE.params.a.max]), [40, 60]);

  // ── 4.3. Пустое поле границы возвращает прежнее значение.
  await seedParam(page);
  await page.evaluate(() => { STATE.params.a.min = -5; STATE.params.a.max = 3;
    const pl = document.getElementById('params-panel'); if (pl) pl._extraSig = PULT_REBUILD;
    updatePult(); redrawAll(); });
  await page.waitForTimeout(400);
  let b = await aim(page, '.pchip-param .param-bound', 0);
  say('нижняя граница доступна щелчку', !!(b && b.hit), true);
  await page.mouse.click(b.x, b.y);
  await page.waitForTimeout(300);
  say('редактор границ открылся',
      await page.evaluate(() => document.querySelectorAll('.param-editor.open .edval').length), 3);
  await page.keyboard.type('-1', { delay: 25 });
  await page.keyboard.press('Tab');
  await page.waitForTimeout(200);
  say('Tab привёл во второе поле и открыл правку',
      await page.evaluate(() => {
        const f = [...document.querySelectorAll('.param-editor.open .edval')];
        return f.indexOf(document.activeElement) === 1 && document.activeElement.classList.contains('editing');
      }), true);
  await page.keyboard.type('1', { delay: 25 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  say('границы стали −1…1', await page.evaluate(() => [+STATE.params.a.min, +STATE.params.a.max]), [-1, 1]);
  say('значение подтянулось к ближайшей границе',
      await page.evaluate(() => STATE.params.a.value), 1);

  // Третий заход: границу открыли и НИЧЕГО не вписали — прежнее обязано уцелеть.
  await seedParam(page);
  await page.evaluate(() => { STATE.params.a.min = -5; STATE.params.a.max = 3; STATE.params.a.value = 2;
    const pl = document.getElementById('params-panel'); if (pl) pl._extraSig = PULT_REBUILD;
    updatePult(); redrawAll(); });
  await page.waitForTimeout(400);
  b = await aim(page, '.pchip-param .param-bound', 1);
  await page.mouse.click(b.x, b.y);
  await page.waitForTimeout(300);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  say('пустой ввод не тронул границы',
      await page.evaluate(() => [+STATE.params.a.min, +STATE.params.a.max]), [-5, 3]);
  say('и не обнулил значение', await page.evaluate(() => STATE.params.a.value), 2);
  const sl = await page.evaluate(() => {
    const r = document.querySelector('.pchip-param input[type=range]');
    return r ? [r.min, r.max, r.value] : null;
  });
  say('ползунок остался рабочим', sl, ['-5', '3', '2']);

  console.log('\n=== границы и значение: ' + ok + ' прошло, ' + bad + ' провалено; ошибок страницы ' + errs.length + ' ===');
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
