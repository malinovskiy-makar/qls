/* ФАЗА 1 ревью 19.08. ОПИСЬ ВСЕХ СЦЕН ВКЛАДКИ «ГРАФИКИ».

   Человек смотрел четыре сцены из сорока одной, а правки лягут на все. Опись
   снимается прибором, не глазами, и отвечает ровно на те вопросы, от которых
   зависят фазы 2–12.

   ⚠️ ГЛАВНОЕ ПРАВИЛО ЗАМЕРА: прибор обязан мерить то, что видит человек.
   Поэтому здесь нигде не спрашивается «есть ли такая функция» — спрашивается,
   что лежит в живом DOM после того, как сцена открылась и отрисовалась.

   Запуск: node scripts/calc2_inventory_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/inventory.json';
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

/* Снимок одной открытой сцены. Всё считается по живому DOM. */
const snap = () => {
  const svgEl = document.querySelector('#chart');
  const box = svgEl ? svgEl.getBoundingClientRect() : null;
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return false;
    const c = getComputedStyle(el);
    return c.visibility !== 'hidden' && c.display !== 'none' && parseFloat(c.opacity || '1') > 0.02;
  };
  const ownText = (n) => Array.from(n.childNodes)
    .filter(c => c.nodeType === 3).map(c => c.nodeValue).join('').trim();

  /* 1–2. Пути внутри группы кривых: видимые, дорожки захвата, ручки сцены. */
  const paths = Array.from(document.querySelectorAll('g.curves path'));
  const bands = [], visible = [];
  paths.forEach(p => {
    const c = getComputedStyle(p);
    const rec = {
      cursor: c.cursor,
      width: +(parseFloat(c.strokeWidth) || 0).toFixed(2),
      skipExport: p.getAttribute('data-skip-export') === '1',
      curveId: p.getAttribute('data-curve') || null,
    };
    // Дорожка захвата — та, что помечена как невыгружаемая либо прозрачна.
    const transparent = /transparent|rgba\(0, 0, 0, 0\)/.test(c.stroke || '');
    if (rec.skipExport || transparent) bands.push(rec); else visible.push(rec);
  });
  const grabs = Array.from(document.querySelectorAll('#chart *'))
    .filter(el => getComputedStyle(el).cursor === 'grab')
    .map(el => el.tagName.toLowerCase());

  /* 3. Кружки ключевых точек. */
  const crosses = Array.from(document.querySelectorAll('g.crosses circle')).map(el => {
    const c = getComputedStyle(el);
    return { r: +(parseFloat(el.getAttribute('r')) || 0).toFixed(1), cursor: c.cursor,
             opacity: +(parseFloat(c.opacity) || 1).toFixed(2) };
  });

  /* 4. Строки «Ключевых значений»: сколько колонок в сетке и какие виды. */
  const statRows = Array.from(document.querySelectorAll('.sb-body .stat')).filter(vis).map(el => {
    const c = getComputedStyle(el);
    return {
      cls: el.className,
      cols: c.gridTemplateColumns,
      colCount: (c.gridTemplateColumns || '').trim().split(/\s+(?![^(]*\))/).filter(Boolean).length,
      h: +el.getBoundingClientRect().height.toFixed(1),
      txt: el.textContent.replace(/\s+/g, ' ').trim().slice(0, 60),
    };
  });
  const panelW = (() => {
    const p = document.querySelector('.sb-body');
    return p ? +p.getBoundingClientRect().width.toFixed(1) : null;
  })();

  /* 5. Два текста, которые снимаются работой. */
  const bodyTxt = document.body.innerText || '';
  const resetWhy = Array.from(document.querySelectorAll('.side-reset__why')).filter(vis).length;
  /* Блок пустого состояния — `.k-empty`; их на странице несколько (пустые
     состояния разных панелей), поэтому считаем ИМЕННО тот, что говорит про
     функции, и только видимый. */
  const emptyBlock = Array.from(document.querySelectorAll('.k-empty'))
    .filter(el => vis(el) && /Пока ни одной функции/.test(el.textContent)).length;
  void bodyTxt;

  /* 6. Можно ли в сцене вписывать формулы. */
  const mf = Array.from(document.querySelectorAll('math-field')).filter(vis);
  const fRows = Array.from(document.querySelectorAll('.f-row')).filter(vis);
  const edvals = Array.from(document.querySelectorAll('.f-slot .edval')).filter(vis).length;
  const kbdSizes = Array.from(document.querySelectorAll('.f-kbd')).filter(vis).map(el => {
    const r = el.getBoundingClientRect();
    const slot = el.closest('.f-row') && el.closest('.f-row').querySelector('math-field');
    const sr = slot ? slot.getBoundingClientRect() : null;
    return { kbd: +r.height.toFixed(1), field: sr ? +sr.height.toFixed(1) : null };
  });

  /* 7. Чекбоксы. */
  const chks = Array.from(document.querySelectorAll('.chk input[type=checkbox]')).map(el => {
    const c = getComputedStyle(el);
    return { w: +(parseFloat(c.width) || 0).toFixed(1), h: +(parseFloat(c.height) || 0).toFixed(1),
             appearance: c.appearance || c.webkitAppearance, accent: c.accentColor,
             visible: vis(el) };
  });

  /* 8. Подписи координат ВНУТРИ поля построения: «P*=50», «Q1=40» и подобные.
     Признак — текст со знаком равенства и числом, лежащий на холсте. */
  const coordLabels = [];
  if (box) {
    Array.from(document.querySelectorAll('#chart text')).filter(vis).forEach(el => {
      const t = (ownText(el) || el.textContent || '').trim();
      if (!/^[^=]{0,8}=\s*−?-?\d/.test(t)) return;
      const r = el.getBoundingClientRect();
      coordLabels.push({ t, x: +(r.left - box.left).toFixed(1), y: +(r.top - box.top).toFixed(1),
                         cls: el.getAttribute('class') || '' });
    });
  }

  /* 9. Границы области по умолчанию — прямо у шкал сцены. */
  let dom = null;
  try {
    const s = mainScales();
    dom = { x: s.mx.domain().map(v => +v.toFixed(3)), y: s.my.domain().map(v => +v.toFixed(3)) };
  } catch (e) { dom = null; }

  /* 10. Подписи, вышедшие за холст. */
  const outside = [];
  if (box) {
    Array.from(document.querySelectorAll('#chart text')).filter(vis).forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.left < box.left - 0.5 || r.right > box.right + 0.5 ||
          r.top < box.top - 0.5 || r.bottom > box.bottom + 0.5) {
        outside.push({ t: (el.textContent || '').trim().slice(0, 18),
                       dx: +Math.min(r.left - box.left, box.right - r.right).toFixed(1) });
      }
    });
  }

  /* 11. Ползунки-параметры (для фаз 9 и 12). */
  const params = Array.from(document.querySelectorAll('.param-chip, .pchip')).filter(vis)
    .map(el => (el.getAttribute('data-param') || el.textContent.replace(/\s+/g, ' ').trim().slice(0, 24)));

  return {
    curves: (typeof STATE === 'object' && STATE.curves) ? STATE.curves.length : null,
    visiblePaths: visible.length,
    bands, grabs, crosses,
    statRows, panelW,
    resetWhy, emptyBlock,
    mathFields: mf.length, fRows: fRows.length, edvals, kbdSizes,
    chks, coordLabels, domain: dom, outside, params,
  };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  console.log('сцен:', scenes.length);

  const res = {};
  for (const key of scenes) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(1000);          // меньше 600 мс: STATE.curves ещё пуст
    /* ⚠️ СЦЕНА ОТКРЫВАЕТСЯ СО ВСЕМИ ЗАКРЫТЫМИ КАРТОЧКАМИ, И ЭТО МЕНЯЕТ ЗАМЕР.
       Первая версия прибора нашла ноль строк «Ключевых значений», ноль полей
       формул и ноль видимых чекбоксов на всех сорока одной сцене — и это было
       неправдой прибора, а не свойством продукта: `collapseCards()` закрывает
       блоки, а поля формул вдобавок собираются ЛЕНИВО и только когда видны
       (очередь `_mfWaiting`). Пока блок закрыт, поля не существует вовсе.
       Поэтому раскрываем всё и даём кадр на сборку полей. */
    await page.evaluate(() => {
      document.querySelectorAll('#tools-panel .section, #params-panel .section, .sb .section')
        .forEach(sec => { if (sec.id) openSection(sec.id); });
      document.querySelectorAll('.fold-btn').forEach(b => {
        if (b.getAttribute('aria-expanded') === 'false') b.click();
      });
    });
    await page.waitForTimeout(700);
    res[key] = await page.evaluate(snap);
    process.stdout.write('.');
  }
  console.log('');
  fs.writeFileSync(OUT, JSON.stringify({ scenes: res, pageErrors: errs }, null, 1), 'utf8');
  await browser.close();
  console.log('записано:', OUT, '· ошибок страницы:', errs.length);
})();
