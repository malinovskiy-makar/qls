// Проверка ИНТЕРФЕЙСА calc2 в реальном браузере (математику проверяет соседний
// calc2_math.mjs, он же подключён к manage.py test).
//
// Этот файл в manage.py test НЕ подключён намеренно: он поднимает второй браузер
// и удлиняет обычный прогон, а проверяет вещи, которые ломаются реже расчётов.
// Запускать руками, когда трогаешь панели, ленту, экспорт или тексты:
//
//   ./venv/Scripts/python.exe manage.py runserver 8099 --noreload
//   node calc2/tests/calc2_ui.mjs
//
// Параметры через env: CALC2_BASE_URL, CALC2_USER, CALC2_PASS.
// Что покрыто: секция «Оформление» (заголовок, названия осей, свои точки),
// цветовые пикеры кривых, подписи кривых при разных масштабах, попап формул и
// KaTeX-предпросмотр, сборка .tex и ответ PDF-эндпоинта, вложенность
// «Что изучаем», геометрия иконок, ширина ленты-пульта, тексты без длинных тире.
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });

// Действие, которое не проходит, должно падать быстро: иначе прогон из-за
// пары сломанных проверок растягивается на десятки минут.
page.setDefaultTimeout(12000);
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(900);
const ready = await page.evaluate(() => typeof redrawAll === 'function' && typeof STATE === 'object');
if (!ready) { console.error('SKIP: функции calc2 не загрузились'); await browser.close(); process.exit(3); }

const checks = [];
const t = async (name, fn) => {
  // Пишем результат сразу: по обрыву прогона видно, на чём он встал.
  let row;
  const t0 = Date.now();
  try { const r = await fn(); row = [r === true ? 'OK' : 'FAIL', name, r === true ? '' : String(r)]; }
  catch (e) { row = ['ERR', name, e.message]; }
  checks.push(row);
  process.stdout.write(row[0].padEnd(4) + ' [' + (Date.now() - t0) + 'ms] ' + name + (row[2] ? '  -> ' + row[2].slice(0, 120) : '') + String.fromCharCode(10));
};

/* Панель ввода открывается со всеми свёрнутыми карточками, поэтому перед
   настоящим щелчком нужно развернуть панель и все складные блоки над целью.
   Щелчок из page.evaluate этого не требует: он проходит и по скрытому узлу. */
const reveal = async (sel) => {
  await page.evaluate((s) => {
    if (typeof setToolsOpen === 'function') setToolsOpen(true);
    const el = document.querySelector(s);
    if (!el) return;
    // П2: карточка модели живёт внутри блока, а блоки на главном экране
    // закрыты. Открываем нужный блок (и убираем сетку карточек блоков).
    const grp = el.closest && el.closest('.picker-group');
    if (grp && !grp.classList.contains('open')) {
      const blocks = document.getElementById('picker-blocks');
      if (blocks) blocks.classList.add('hidden');
      document.querySelectorAll('#scene-picker .picker-group')
        .forEach(g => g.classList.toggle('open', g === grp));
      const back = document.getElementById('picker-back');
      if (back) back.classList.add('shown');
    }
    let n = el;
    while (n && n !== document.body) {
      const foldable = n.classList && (n.classList.contains('fold-body') || n.classList.contains('picker-grid'));
      if (foldable && !n.classList.contains('open') && n.id) {
        const btn = document.querySelector('[aria-controls="' + n.id + '"]');
        if (btn) btn.click();
      }
      n = n.parentElement;
    }
    el.scrollIntoView({ block: 'center' });
  }, sel);
  await page.waitForTimeout(140);
};
const clickUI = async (sel, opts) => { await reveal(sel); return page.click(sel, opts); };
const selectUI = async (sel, val) => { await reveal(sel); return page.selectOption(sel, val); };
const fillUI = async (sel, val) => { await reveal(sel); return page.fill(sel, val); };

await t('окно сценариев открыто', () => page.locator('#scene-picker').isVisible());
await t('#sec-mode удалён', async () => (await page.locator('#sec-mode').count()) === 0 || 'ещё есть');
await t('#sec-scenes удалён', async () => (await page.locator('#sec-scenes').count()) === 0 || 'ещё есть');
await t('#sec-view есть', async () => (await page.locator('#sec-view').count()) === 1 || 'нет секции');

// Входим в сцену «Спрос и предложение».
await clickUI('.scard[data-scene="sd"]');
await page.waitForTimeout(400);

await t('равновесие 50/50 не сломано', () => page.evaluate(() => {
  const e = STATE.eq; return (Math.abs(e.Q - 50) < .3 && Math.abs(e.P - 50) < .3) || JSON.stringify(e);
}));

await t('заголовок графика рисуется', async () => {
  await page.evaluate(() => { const e = document.getElementById('inp-gtitle');
    e.value = 'Рынок хлеба'; e.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForTimeout(250);
  return await page.evaluate(() =>
    [...document.querySelectorAll('#chart text')].some(n => n.textContent === 'Рынок хлеба') || 'нет текста в SVG');
});

await t('своё имя оси X попадает на график', async () => {
  await page.evaluate(() => { const e = document.getElementById('inp-xname');
    e.value = 'Батоны'; e.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForTimeout(250);
  return await page.evaluate(() =>
    [...document.querySelectorAll('#chart text')].some(n => n.textContent === 'Батоны') || 'нет метки оси');
});

await t('плейсхолдер оси Y = сценовое название', async () =>
  (await page.getAttribute('#inp-yname', 'placeholder')) === 'P' || 'плейсхолдер не P');

await t('своя точка ставится и подписывается', async () => {
  await page.evaluate(() => { addMarkAt(30, 70); STATE.marks[0].text = 'Мой ориентир'; redrawAll(); });
  await page.waitForTimeout(200);
  // У имени точки есть дочерний <title> с подсказкой о переименовании,
  // поэтому сверяем собственные текстовые узлы.
  return await page.evaluate(() =>
    [...document.querySelectorAll('#chart text')].some(n =>
      [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.nodeValue).join('') === 'Мой ориентир')
    || 'нет подписи точки');
});

// Название кривой и имя точки правятся двойным щелчком прямо на графике.
await t('двойной щелчок по имени точки открывает правку', async () => {
  const dbg = (m) => process.stdout.write('    .. ' + m + String.fromCharCode(10));
  dbg('before dblclick');
  await page.locator('#chart text', { hasText: 'Мой ориентир' }).first().dblclick();
  dbg('after dblclick');
  await page.waitForTimeout(220);
  const n = await page.locator('#pt-rename').count();
  dbg('count=' + n);
  const v = n ? await page.locator('#pt-rename').inputValue() : '';
  if (n) {
    await fillUI('#pt-rename', 'Точка A');
    dbg('filled');
    await page.press('#pt-rename', 'Enter');
    dbg('pressed');
    await page.waitForTimeout(220);
  }
  const saved = await page.evaluate(() => STATE.marks[0].text);
  dbg('saved=' + saved);
  return (n === 1 && v === 'Мой ориентир' && saved === 'Точка A')
    || `полей ${n}, было «${v}», стало «${saved}»`;
});

await t('своё имя точки вернулось в список слева', () => page.evaluate(() => {
  const inp = document.querySelector('#mark-list input[type=text]');
  return (inp && inp.value === 'Точка A') || 'в списке «' + (inp && inp.value) + '»';
}));

await t('точка показывает координаты', () => page.evaluate(() => {
  STATE.marks[0].text = 'Мой ориентир'; redrawAll();
  return true;
}));

await t('координаты точки на графике', () => page.evaluate(() =>
  [...document.querySelectorAll('#chart text')].some(n => n.textContent === '(30; 70)') || 'нет координат'));

/* П29: значений кривых у точки больше нет — ни галочки в списке, ни строк на
   графике. Подпись из четырёх строк накрывала сам график. */
await t('значений кривых у точки нет', () => page.evaluate(() => {
  STATE.marks[0].showCurves = true; redrawAll();
  const onChart = [...document.querySelectorAll('#chart text')].some(n => /^D = /.test(n.textContent));
  const inList = [...document.querySelectorAll('#mark-list .chk')].some(l => /значения кривых/i.test(l.textContent));
  delete STATE.marks[0].showCurves; redrawAll();
  return (!onChart && !inList) || `на графике ${onChart}, в списке ${inList}`;
}));

await t('пикеры цвета есть у каждой кривой', async () =>
  (await page.locator('#curve-list input[type=color]').count()) === 2 || 'не 2 пикера');

await t('пикер меняет цвет только своей кривой', () => page.evaluate(() => {
  const before = STATE.curves[1].color;
  STATE.curves[0].color = '#123456'; STATE.curves[0].colorCustom = true; redrawAll();
  const strokes = [...document.querySelectorAll('#chart .curves path')].map(p => p.getAttribute('stroke'));
  return (strokes.includes('#123456') && STATE.curves[1].color === before) || strokes.join(',');
}));

await t('своё имя кривой идёт в чип пульта', () => page.evaluate(() => {
  STATE.curves[0].label = 'Спрос-1';
  return curveChipLabel(STATE.curves[0]) === 'Спрос-1…' || curveChipLabel(STATE.curves[0]) === 'Спрос-1'
    ? true : curveChipLabel(STATE.curves[0]);
}));

await t('смена сцены очищает оформление', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); pickScene('mono'); closePicker(); });
  await page.waitForTimeout(300);
  return await page.evaluate(() =>
    (STATE.graphTitle === '' && STATE.axisXName === '' && STATE.marks.length === 0) ||
    JSON.stringify({ t: STATE.graphTitle, x: STATE.axisXName, m: STATE.marks.length }));
});

await t('монополия 40/60 не сломана', () => page.evaluate(() =>
  (Math.abs(STATE.mono.Qm - 40) < .3 && Math.abs(STATE.mono.Pm - 60) < .3) || JSON.stringify(STATE.mono)));

// ── Фаза 2: пикеры у кривых издержек ────────────────────────────────────
await page.evaluate(() => { resetSceneMemory(); openPicker(); pickScene('costs'); closePicker(); });
await page.waitForTimeout(400);

await t('у пяти кривых издержек есть пикеры', async () => {
  const n = await page.locator('#sec-costs .cpick[data-col^="cost"]').count();
  return n === 5 || `пикеров ${n}`;
});

await t('ключи цвета уникальны (MP ≠ MC и т.п.)', () => page.evaluate(() => {
  const keys = [...document.querySelectorAll('.cpick[data-col]')].map(i => i.dataset.col);
  const dup = keys.filter((k, i) => keys.indexOf(k) !== i);
  return dup.length === 0 || 'дубли: ' + dup.join(',');
}));

/* --- П34: шесть предложенных цветов везде, где выбирают цвет ------------ */
await t('в меню цвета шесть образцов и «Свой цвет»', () => page.evaluate(() => {
  const btn = document.querySelector('.cpick[data-col="costMC"] .cpick-btn');
  if (!btn) return 'кнопки цвета нет';
  btn.click();
  const menu = document.querySelector('.cpick-menu');
  if (!menu) return 'меню не открылось';
  const n = menu.querySelectorAll('.cpick-sw').length;
  const own = !!menu.querySelector('.cpick-own input[type=color]');
  const inBody = menu.parentElement === document.body;   // не обрезается панелью
  closeColorMenu();
  return (n === 6 && own && inBody) || `образцов ${n}, свой ${own}, в body ${inBody}`;
}));

await t('светлая и тёмная тема дают разные шесть цветов', () => page.evaluate(() => {
  const root = document.documentElement, was = root.getAttribute('data-theme');
  root.setAttribute('data-theme', 'light');  const light = paletteSix().join(',');
  root.setAttribute('data-theme', 'dark');   const dark = paletteSix().join(',');
  if (was) root.setAttribute('data-theme', was); else root.removeAttribute('data-theme');
  refreshColors();
  return (light !== dark && /#c74440/i.test(light)) || `светлая ${light} / тёмная ${dark}`;
}));

// Пикер лежит внутри <label class="chk"> рядом с галочкой. Проверяем, что клик по
// нему НЕ переключает галочку (браузер не пробрасывает клик с вложенного
// интерактивного элемента на элемент, к которому привязан label).
await t('клик по пикеру не сбрасывает галочку кривой', () => page.evaluate(() => {
  const chk = document.getElementById('chk-mc');
  const pick = document.querySelector('.cpick[data-col="costMC"] .cpick-btn');
  const before = chk.checked;
  pick.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
  const after = chk.checked;
  closeColorMenu();
  return after === before || `галочка была ${before}, стала ${after}`;
}));

await t('цвет MP не тянет за собой MC', () => page.evaluate(() => {
  STATE.colorOverride = { prodMP: '#00ccdd' }; redrawAll();
  const token = getComputedStyle(document.documentElement).getPropertyValue('--cost-mc').trim();
  return (COL.prodMP === '#00ccdd' && COL.costMC.toLowerCase() === token.toLowerCase())
    || `prodMP=${COL.prodMP}, costMC=${COL.costMC}, токен=${token}`;
}));

await t('свой цвет MC доходит до графика', () => page.evaluate(() => {
  STATE.colorOverride.costMC = '#ff00aa'; redrawAll();
  const used = [...document.querySelectorAll('#chart path')].map(p => p.getAttribute('stroke'));
  return used.includes('#ff00aa') || 'MC не перекрасилась';
}));

await t('свой цвет не трогает соседние кривые', () => page.evaluate(() => {
  const atc = COL.costATC, token = getComputedStyle(document.documentElement).getPropertyValue('--cost-atc').trim();
  return atc === token || `ATC=${atc}, токен=${token}`;
}));

await t('токен --cost-mc в CSS не изменился', () => page.evaluate(() =>
  getComputedStyle(document.documentElement).getPropertyValue('--cost-mc').trim() !== '#ff00aa'
    || 'токен перезаписан!'));

await t('издержки: min AVC при Q=3 не сломан', () => page.evaluate(() => {
  STATE.colorOverride = {}; redrawAll();
  return Math.abs(STATE.minAVC.Q - 3) < .15 || JSON.stringify(STATE.minAVC);
}));

// ── Фаза 3: подписи кривых не пропадают ─────────────────────────────────
// У подписи бывает дочерний <title> с всплывающей подсказкой, и он попадает в
// textContent. Берём только собственные текстовые узлы — то, что видно на холсте.
const svgTexts = () => page.evaluate(() => [...document.querySelectorAll('#chart text')]
  .map(n => [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.nodeValue).join('')));

await t('подписи MC/ATC/AVC видны при обычном масштабе', async () => {
  const tx = await svgTexts();
  return ['MC', 'ATC', 'AVC'].every(s => tx.includes(s)) || 'есть: ' + tx.join('|');
});

await t('подписи не исчезают, когда кривые ушли за верх окна', async () => {
  // Раньше это был тот самый баг: MC при Q=0.96·Qmax выше Pmax → подпись не рисовалась.
  await page.evaluate(() => { setRanges(10, 12); redrawAll(); });
  await page.waitForTimeout(200);
  const tx = await svgTexts();
  return ['MC', 'ATC', 'AVC'].every(s => tx.includes(s)) || 'пропали, осталось: ' + tx.join('|');
});

await t('подписи держатся и при сильном сжатии по Q', async () => {
  await page.evaluate(() => { setRanges(2, 50); redrawAll(); });
  await page.waitForTimeout(200);
  const tx = await svgTexts();
  return ['MC', 'ATC'].every(s => tx.includes(s)) || 'осталось: ' + tx.join('|');
});

await t('подписи не вылезают за поле графика', () => page.evaluate(() => {
  const box = document.getElementById('chart').getBoundingClientRect();
  const bad = [...document.querySelectorAll('#chart text')].filter(n => {
    const r = n.getBoundingClientRect();
    return r.width > 0 && (r.right > box.right + 1 || r.left < box.left - 1);
  }).map(n => n.textContent);
  return bad.length === 0 || 'вылезли: ' + bad.join('|');
}));

await t('D и S подписаны на рыночном графике', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); pickScene('sd'); closePicker(); });
  await page.waitForTimeout(350);
  const tx = await svgTexts();
  return (tx.includes('D') && tx.includes('S')) || 'есть: ' + tx.join('|');
});

// ── Фаза 4: подсказки формул и KaTeX-предпросмотр ───────────────────────
await t('KaTeX загрузился на странице calc2', () => page.evaluate(() => typeof katex !== 'undefined' || 'katex не определён'));

await t('Math.js → LaTeX: степень', () => page.evaluate(() =>
  /Q.*\^.*\{?2/.test(mathToTex('Q^2')) || mathToTex('Q^2')));
await t('Math.js → LaTeX: корень', () => page.evaluate(() =>
  mathToTex('sqrt(100 - Q^2)').includes('\\sqrt') || mathToTex('sqrt(100 - Q^2)')));
await t('Math.js → LaTeX: дробь', () => page.evaluate(() =>
  mathToTex('120/(Q + 1)').includes('\\frac') || mathToTex('120/(Q + 1)')));
await t('недописанная формула не роняет предпросмотр', () => page.evaluate(() => {
  const s = mathToTex('100 - ');
  return typeof s === 'string' || 'упало';
}));

// Формула набирается прямо в строке: пока поле не в работе, поверх него лежит
// та же запись, но напечатанная. Отдельного блока под полем больше нет.
// Сцены открываются со свёрнутой панелью, а нам нужны настоящие щелчки по
// полю и кнопке — разворачиваем и подводим секцию к глазам.
await page.evaluate(() => {
  setToolsOpen(true);
  const s = document.getElementById('sec-curves');
  if (s) s.scrollIntoView({ block: 'center' });
});
await page.waitForTimeout(300);
await t('формула показана набранной прямо в строке', async () => {
  await page.evaluate(() => setFieldValue(document.getElementById('inp-formula'), '100 - 2*Q'));
  await page.waitForTimeout(280);
  return await page.evaluate(() => {
    const inp = document.getElementById('inp-formula');
    if (inp._mf) {
      // С MathLive формула живёт в самом поле: проверяем, что она туда доехала.
      return /frac|cdot|100/.test(inp._mf.value) || 'поле пустое: ' + inp._mf.value;
    }
    const ts = document.querySelector('#sec-curves .f-typeset');
    return (ts && ts.classList.contains('has')) || 'запасная накладка пуста';
  });
});

await t('поле формулы можно править прямо в строке', async () => {
  await reveal('#inp-formula');
  return await page.evaluate(() => {
    const inp = document.getElementById('inp-formula');
    if (!inp._mf) return true;                 // без MathLive правится обычный input
    inp._mf.focusField();
    return document.activeElement === inp._mf || 'фокус мимо поля';
  });
});

await t('пустое поле остаётся пустым', async () => {
  await page.evaluate(() => setFieldValue(document.getElementById('inp-formula'), ''));
  await page.waitForTimeout(200);
  return await page.evaluate(() => {
    const inp = document.getElementById('inp-formula');
    if (inp._mf) return !inp._mf.value.trim() || 'в поле осталось: ' + inp._mf.value;
    const ts = document.querySelector('#sec-curves .f-typeset');
    return !ts.classList.contains('show') || 'накладка на пустом поле';
  });
});

// Корень прежней поломки: блок предпросмотра под полем схлопывался на потере
// фокуса, всё под ним уезжало вверх, и щелчок по «Добавить» не доходил, потому
// что между нажатием и отпусканием кнопка успевала сдвинуться. Проверяем
// геометрию напрямую: строка формулы не меняет высоту при уходе фокуса.
await t('уход фокуса из формулы не двигает кнопку «Добавить»', async () => {
  await page.evaluate(() => {
    const inp = document.getElementById('inp-formula');
    if (inp._mf) inp._mf.focusField(); else inp.focus();
    setFieldValue(inp, '100 - 2*Q');
  });
  await page.waitForTimeout(200);
  const before = await page.evaluate(() =>
    document.getElementById('btn-add-curve').getBoundingClientRect().top);
  await page.evaluate(() => document.getElementById('inp-formula').blur());
  await page.waitForTimeout(250);
  const after = await page.evaluate(() =>
    document.getElementById('btn-add-curve').getBoundingClientRect().top);
  return Math.abs(after - before) < 0.5 || `кнопка уехала на ${(after - before).toFixed(1)} px`;
});

await t('кривая добавляется настоящим щелчком по кнопке', async () => {
  await page.evaluate(() => { STATE.curves = []; renderCurveList(); redrawAll(); });
  await selectUI('#new-role', '');
  await page.evaluate(() => setFieldValue(document.getElementById('inp-formula'), '100 - Q'));
  // Панель прокручиваемая и кнопка может оказаться за её краем, поэтому
  // воспроизводим последовательность браузера: нажатие, потеря фокуса, щелчок.
  await page.evaluate(() => {
    const btn = document.getElementById('btn-add-curve');
    const opt = { bubbles: true, cancelable: true, view: window };
    btn.dispatchEvent(new MouseEvent('mousedown', opt));
    document.getElementById('inp-formula').blur();
    btn.dispatchEvent(new MouseEvent('mouseup', opt));
    btn.click();
  });
  await page.waitForTimeout(300);
  return await page.evaluate(() =>
    (STATE.curves.length === 1 && STATE.curves[0].expr === '100 - Q')
    || JSON.stringify(STATE.curves.map(c => c.expr)));
});

await t('кнопка открывает клавиатуру из трёх разделов', async () => {
  await page.evaluate(() => document.getElementById('fh-formula').click());
  await page.waitForTimeout(250);
  return await page.evaluate(() => {
    const kb = document.querySelector('.mkbd.open');
    if (!kb) return 'клавиатура не открылась';
    const tabs = kb.querySelectorAll('.mkbd-tab').length;
    const active = kb.querySelectorAll('.mkbd-pane.active').length;
    const keys = kb.querySelectorAll('.mk').length;
    return (tabs === 3 && active === 1 && keys > 60) || `разделов ${tabs}, открыт ${active}, клавиш ${keys}`;
  });
});

await t('клавиша ставит символ в поле, не стирая набранное', async () => {
  return await page.evaluate(() => {
    const inp = document.getElementById('inp-formula');
    if (inp._mf) inp._mf.value = '';
    setFieldValue(inp, '');
    const kb = document.querySelector('.mkbd.open');
    const keys = [...kb.querySelectorAll('.mk')];
    const hit = (t) => { const b = keys.find(x => x.textContent === t); if (b) b.click(); };
    hit('1'); hit('0'); hit('0'); hit('−'); hit('Q');
    return inp.value.replace(/\s/g, '') === '100-Q' || `в поле «${inp.value}»`;
  });
});

// Раздел «Примеры формул» из клавиатуры убран: он повторял раздел «Функции»,
// а вернуться из него к клавиатуре было нечем. В подвале остался один вход —
// конструктор кусочной функции.
// Задвоенный рендер при первом входе: запасная накладка оставалась висеть
// поверх собранного поля MathLive и уходила лишь после правки в строке.
await t('формула показана один раз, накладки поверх поля нет', () => page.evaluate(() => {
  const inp = document.getElementById('inp-formula');
  const ts = inp.closest('.f-slot').querySelector('.f-typeset');
  if (!inp._mf) return true;                      // без MathLive накладка и есть поле
  return !ts.classList.contains('show') || 'накладка видна поверх поля';
}));

await t('в подвале клавиатуры только кусочная функция', () => page.evaluate(() => {
  const kb = document.querySelector('.mkbd.open');
  if (!kb) return 'клавиатура не открыта';
  const names = [...kb.querySelectorAll('.mkbd-foot button')].map(b => b.textContent.trim());
  const ok = (names.length === 1 && /Кусочн/.test(names[0]));
  kb.classList.remove('open');            // дальше тесты открывают её сами
  return ok || 'в подвале: ' + names.join(' | ');
}));

await t('своё имя кривой заменяет родовое D на графике', async () => {
  await page.evaluate(() => {
    if (!STATE.curves.length) { addCurve('100 - Q'); setRole(STATE.curves[0], 'demand'); }
    STATE.curves[0].label = 'Спрос молодёжи'; redrawAll();
  });
  await page.waitForTimeout(200);
  const tx = await svgTexts();
  return (tx.includes('Спрос молодёжи') && !tx.includes('D')) || 'есть: ' + tx.join('|');
});

// ── Фаза 8: один вход вместо двух ───────────────────────────────────────
await page.evaluate(() => { resetSceneMemory(); openPicker(); pickScene('sd'); closePicker(); });
await page.waitForTimeout(350);

await t('структура рынка и вмешательство вложены в «Что изучаем»', () => page.evaluate(() => {
  const an = document.getElementById('sec-analysis');
  return (an.contains(document.getElementById('sec-tax')) &&
          an.contains(document.getElementById('sec-mono'))) || 'секции всё ещё отдельные';
}));

await t('заголовок верхнего уровня в панели один', () => page.evaluate(() => {
  // Заголовок секции стал складной кнопкой карточки (Фаза 5), а название внутри
  // неё лежит в <b> рядом с иконкой блока (П9). Берём именно его: рядом стоит
  // вопросик-подсказка, и его «?» попал бы в textContent всей кнопки.
  // Внутри «Что изучаем» заголовков верхнего уровня быть не должно.
  const own = (n) => {
    const b = n.querySelector(':scope > b');
    if (b) return b.textContent.trim();
    return [...n.childNodes].filter(x => x.nodeType === 3).map(x => x.nodeValue).join('').trim();
  };
  const head = document.querySelector('#sec-analysis > .fold-btn > span');
  const inner = document.querySelectorAll('#sec-analysis .section-title').length;
  if (!head) return 'у секции нет складного заголовка';
  if (own(head) !== 'Что изучаем') return 'заголовок: ' + own(head);
  return inner === 0 || 'внутри ещё ' + inner + ' заголовков верхнего уровня';
}));

await t('вмешательство работает: налог t=20 даёт Q1=40', () => page.evaluate(() => {
  setType('tax'); setTax(20); redrawAll();
  const Q1 = STATE.tx / STATE.tax;
  return Math.abs(Q1 - 40) < 0.3 || 'Q1=' + Q1;
}));

await t('монополия из вложенной секции по-прежнему включается', () => page.evaluate(() => {
  setTax(0); setMarket('monopoly'); redrawAll();
  const ok = STATE.market === 'monopoly';
  setMarket('comp'); redrawAll();
  return ok || 'структура не переключилась';
}));

await t('сценарий «Эластичность» прячет вмешательство, как раньше', () => page.evaluate(() => {
  setScenario('elasticity');
  const tax = document.getElementById('sec-tax').style.display;
  const pane = document.getElementById('scn-pane-elast').style.display;
  setScenario('none');
  return (tax === 'none' && pane !== 'none') || `tax=${tax}, pane=${pane}`;
}));

await t('возврат к «Равновесию» возвращает вмешательство', () => page.evaluate(() => {
  const tax = document.getElementById('sec-tax').style.display;
  return tax !== 'none' || 'вмешательство не вернулось';
}));

// ── Фаза 5: экспорт ─────────────────────────────────────────────────────
await page.evaluate(() => { resetSceneMemory(); openPicker(); pickScene('tax'); closePicker(); });
await page.waitForTimeout(400);

await t('окно экспорта открывается по кнопке дока', async () => {
  await page.evaluate(() => document.getElementById('dock-export').click());
  await page.waitForTimeout(250);
  return await page.locator('#export-modal.open').count() === 1 || 'окно не открылось';
});

await t('заголовок подставился из названия сцены', async () =>
  (await page.inputValue('#exp-title')).length > 0 || 'поле пустое');

await t('.tex собирается и содержит кривые', () => page.evaluate(() => {
  const tex = buildTex('Рынок хлеба', 'fig:bread');
  const plots = (tex.match(/\\addplot/g) || []).length;
  return (plots >= 4 && tex.includes('\\begin{axis}')) || `\\addplot: ${plots}`;
}));

await t('кривая с формулой выгружается формулой, а не точками', () => page.evaluate(() => {
  const tex = buildTex('', '');
  const byFormula = (tex.match(/\\addplot\[[^\]]*domain=/g) || []).length;
  return byFormula >= 2 || `формулой выгружено ${byFormula} кривых`;
}));

await t('.tex несёт заголовок, label и заливки', () => page.evaluate(() => {
  const tex = buildTex('Рынок хлеба', 'fig:bread');
  const ok = tex.includes('\\caption{Рынок хлеба}') && tex.includes('\\label{fig:bread}')
             && tex.includes('\\fill[');
  return ok || tex.slice(0, 400);
}));

await t('.tex под обычный pdflatex, кириллица через T2A', () => page.evaluate(() => {
  const tex = buildTex('Рынок хлеба', '');
  return (tex.includes('\\usepackage[T2A]{fontenc}') && tex.includes('\\usepackage[utf8]{inputenc}')
          && tex.includes('\\usepackage[english,russian]{babel}')
          && tex.includes('\\usepackage{pgfplots}')
          && !tex.includes('fontspec') && !tex.includes('unicode-math')) || tex.slice(0, 300);
}));

// Экранная геометрия и есть источник .tex, поэтому масштаб проверяем прямым
// пересчётом: точка равновесия на холсте обязана попасть в ту же точку картинки.
await t('границы осей .tex совпадают с экранными', () => page.evaluate(() => {
  const tex = buildTex('', '');
  const want = 'xmin=' + (Math.round(CONFIG.Qmin * 10000) / 10000) +
               ', xmax=' + (Math.round(CONFIG.Qmax * 10000) / 10000);
  return tex.includes(want) || 'ждали ' + want;
}));

await t('после зума .tex берёт НОВЫЕ границы, а не исходные', async () => {
  await page.evaluate(() => { CONFIG.Qmax = 60; CONFIG.Pmax = 60; markViewDirty(); redrawAll(); });
  await page.waitForTimeout(200);
  const ok = await page.evaluate(() => buildTex('', '').includes('xmax=60'));
  await page.evaluate(() => resetZoom());
  await page.waitForTimeout(200);
  return ok || 'в файле остались старые границы';
});

// Экспорт читает НАРИСОВАННЫЙ холст, поэтому подпись сначала должна попасть
// на график: без redrawAll её в SVG ещё нет и проверять нечего.
await t('.tex экранирует опасные символы в подписях', () => page.evaluate(() => {
  STATE.axisXName = 'Доля 50% & выше';
  redrawAll();
  const tex = buildTex('', '');
  STATE.axisXName = ''; redrawAll();
  return tex.includes('50\\% \\& выше') || 'нет экранирования';
}));

await t('label чистится от посторонних символов', () => page.evaluate(() => {
  const tex = buildTex('t', 'fig: хлеб/2');
  const m = tex.match(/\\label\{([^}]*)\}/);
  return (m && /^[A-Za-z0-9:_-]*$/.test(m[1])) || (m ? m[1] : 'нет label');
}));

await t('пунктирная кривая S+t попала в .tex при налоге', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="tax"]');
  await page.waitForTimeout(300);
  return await page.evaluate(() => {
    const tex = buildTex('', '');
    return tex.includes('dashed') || 'нет пунктира';
  });
});

await t('свои точки попадают в .tex с подписью', () => page.evaluate(() => {
  addMarkAt(20, 80); STATE.marks[STATE.marks.length - 1].text = 'Ориентир'; redrawAll();
  const tex = buildTex('', '');
  STATE.marks = []; redrawAll();
  return tex.includes('Ориентир') || 'подписи нет';
}));

await t('в режиме издержек выгружаются кривые издержек', () => page.evaluate(() => {
  resetSceneMemory(); openPicker(); pickScene('costs'); closePicker(); redrawAll();
  const tex = buildTex('', '');
  // Названия кривых уходят в .tex подписями узлов, как и на экране.
  return (tex.includes('{MC}') || tex.includes('MC};')) && tex.includes('ATC') || tex.slice(0, 200);
}));

// Раньше .tex собирался из формул рыночной сцены, поэтому во всех остальных
// сюжетах выходила пустая или чужая картинка. Проверяем несколько разных.
await t('.tex не пустой в любом режиме, не только рыночном', async () => {
  const scenes = ['m-optimum', 'adas', 'consumer', 'labor-mono', 'ppf', 'ineq', 'prod'];
  const thin = [];
  for (const s of scenes) {
    await page.evaluate(() => { resetSceneMemory(); openPicker(); });
    await clickUI(`.scard[data-scene="${s}"]`);
    await page.waitForTimeout(260);
    const n = await page.evaluate(() => {
      const tex = buildTex('', '');
      return (tex.match(/\\addplot|\\fill|\\node/g) || []).length;
    });
    if (n < 4) thin.push(`${s}:${n}`);
  }
  return thin.length === 0 || 'мало элементов — ' + thin.join(', ');
});

await t('PNG собирается в canvas без ошибок', () => page.evaluate(() => new Promise(res => {
  const node = document.getElementById('chart');
  const clone = node.cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  const src = new XMLSerializer().serializeToString(clone);
  const img = new Image();
  img.onload = () => {
    const cv = document.createElement('canvas');
    cv.width = 400; cv.height = 300;
    cv.getContext('2d').drawImage(img, 0, 0, 400, 300);
    res(cv.toDataURL('image/png').length > 1000 || 'пустая картинка');
  };
  img.onerror = () => res('SVG не отрисовался в картинку');
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(src);
})));

await t('серверный эндпоинт PDF отвечает осмысленно', async () => {
  const r = await page.evaluate(async (url) => {
    const b = new FormData();
    b.append('tex', '\\documentclass{article}\\begin{document}x\\end{document}');
    b.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    const res = await fetch(url, { method: 'POST', body: b });
    return res.status;
  }, await page.evaluate(() => CALC2_PDF_URL));
  // 200 — xelatex есть и собрал; 503 — сервер честно говорит, что не умеет.
  return [200, 503].includes(r) || `код ${r}`;
});

await t('опасные команды в .tex отклоняются сервером', async () => {
  const r = await page.evaluate(async (url) => {
    const b = new FormData();
    b.append('tex', '\\documentclass{article}\\begin{document}\\input{/etc/passwd}\\end{document}');
    b.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    const res = await fetch(url, { method: 'POST', body: b });
    return res.status;
  }, await page.evaluate(() => CALC2_PDF_URL));
  return [400, 503].includes(r) || `код ${r} (ожидался отказ)`;
});

// ── Фаза 6: полировка ───────────────────────────────────────────────────
await t('иконки карточек: три толщины линий, не одиннадцать', () => page.evaluate(() => {
  const w = new Set();
  document.querySelectorAll('#scene-picker .scard-spec [stroke-width]')
    .forEach(n => w.add(n.getAttribute('stroke-width')));
  const arr = [...w].sort();
  return arr.length <= 3 || 'толщин ' + arr.length + ': ' + arr.join(',');
}));
await t('иконки: один радиус маркеров и один пунктир', () => page.evaluate(() => {
  const r = new Set(), d = new Set();
  document.querySelectorAll('#scene-picker .scard-spec circle[r]').forEach(n => r.add(n.getAttribute('r')));
  document.querySelectorAll('#scene-picker .scard-spec [stroke-dasharray]').forEach(n => d.add(n.getAttribute('stroke-dasharray')));
  return (r.size <= 1 && d.size <= 1) || `радиусов ${r.size}, пунктиров ${d.size}`;
}));

await page.evaluate(() => { resetSceneMemory(); openPicker(); pickScene('tax'); closePicker(); });
await page.waitForTimeout(400);

await t('панели не перекрывают график', () => page.evaluate(() => {
  const g = document.getElementById('graph-wrap').getBoundingClientRect();
  const bad = [];
  ['tools-panel', 'params-panel', 'dock'].forEach(id => {
    const e = document.getElementById(id) || document.querySelector('.' + id);
    if (!e) return;
    const b = e.getBoundingClientRect();
    const over = Math.min(g.right, b.right) - Math.max(g.left, b.left);
    if (over > 1) bad.push(id + ' на ' + Math.round(over) + 'px');
  });
  return !bad.length || bad.join(', ');
}));

await t('регуляторы сцены живут в правой панели', () => page.evaluate(() => {
  const n = document.querySelectorAll('#params-body .pchip, #params-body .field').length;
  return n > 0 || 'в панели параметров пусто';
}));

await t('в аналитике число крупнее подписи', () => page.evaluate(() => {
  const b = document.querySelector('#sb-body .stat b'), s = document.querySelector('#sb-body .stat span');
  if (!b || !s) return 'нет строк в табло';
  const bs = parseFloat(getComputedStyle(b).fontSize), ss = parseFloat(getComputedStyle(s).fontSize);
  return bs >= ss + 3 || `число ${bs}px, подпись ${ss}px`;
}));

await t('панель параметров наполняется и в сцене «Труд»', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); pickScene('labor'); closePicker(); });
  await page.waitForTimeout(450);
  return await page.evaluate(() => {
    const n = document.querySelectorAll('#params-body .pchip, #params-body .field').length;
    return n > 0 || 'в панели параметров пусто';
  });
});

// ── Фаза 9: тексты ──────────────────────────────────────────────────────
// Проверяем то, что реально видит человек: собранный DOM во всех сценах,
// а не исходник шаблона (в комментариях кода тире допустимы).
const SCENES = ['sd', 'tax', 'ceil', 'mono', 'elast', 'ext', 'smallopen', 'costs', 'ppf',
                'labor', 'ineq', 'consumer', 'adas', 'laffer', 'islm',
                'm-tangent', 'm-optimum', 'm-transform', 'm-minmax', 'm-constraint'];
const dashHits = [];
for (const sc of SCENES) {
  await page.evaluate((s) => { resetSceneMemory(); openPicker(); pickScene(s); closePicker(); }, sc);
  await page.waitForTimeout(160);
  const hit = await page.evaluate(() => {
    const bad = [];
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walk.nextNode())) {
      const tag = n.parentElement && n.parentElement.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE') continue;
      if (n.nodeValue.includes('—')) bad.push(n.nodeValue.trim().slice(0, 70));
    }
    document.querySelectorAll('[title], [aria-label], [placeholder], [data-tip]').forEach(e => {
      ['title', 'aria-label', 'placeholder', 'data-tip'].forEach(a => {
        const v = e.getAttribute(a);
        if (v && v.includes('—')) bad.push(a + '=' + v.slice(0, 60));
      });
    });
    return bad;
  });
  if (hit.length) dashHits.push(sc + ': ' + hit.slice(0, 2).join(' | '));
}
await t('в интерфейсе нет длинных тире (21 сцена)', () =>
  dashHits.length === 0 || dashHits.slice(0, 3).join('  //  '));

await t('нет ИИ-штампов в видимом тексте', () => page.evaluate(() => {
  const pats = ['Это не просто', 'Важно отметить', 'Стоит отметить', 'Следует отметить',
                'Таким образом', 'В заключение', 'мощный инструмент', 'играет важную роль'];
  const txt = document.body.innerText;
  const found = pats.filter(p => txt.includes(p));
  return found.length === 0 || found.join(', ');
}));

/* --- Переименование ключевых точек прямо на графике --------------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.evaluate(() => { resetSceneMemory(); openPicker(); });
await clickUI('.scard[data-scene="m-optimum"]');
await page.waitForTimeout(420);

/* У подписи висит дочерний <title> с всплывающей подсказкой, поэтому берём
   текст без него. Собственными текстовыми узлами больше не обойтись: с Фазы 9
   индексы печатаются отдельными tspan, и «x» со звёздочкой лежит в трёх узлах. */
await t('машина сама подписала максимум, минимум и перегиб', () => page.evaluate(() => {
  const own = (el) => {
    const c = el.cloneNode(true);
    [...c.querySelectorAll('title')].forEach(t => t.remove());
    return c.textContent;
  };
  const names = [...document.querySelectorAll('#chart text')].map(own);
  const has = (re) => names.some(s => re.test(s));
  // Подпись называет обе величины: x∗ — где, y∗ — сколько (звёздочка верхним индексом).
  return (has(/^max: x[*∗] = /) && has(/^min: x[*∗] = /) && has(/^перегиб: x[*∗] = /))
    || names.join(' | ');
}));

await t('двойной щелчок по подписи открывает переименование', async () => {
  await page.locator('#chart text', { hasText: 'max' }).first().dblclick();
  await page.waitForTimeout(220);
  const n = await page.locator('#pt-rename').count();
  const v = n ? await page.locator('#pt-rename').inputValue() : '';
  return (n === 1 && /^max: /.test(v)) || `полей ${n}, значение «${v}»`;
});

await t('Enter сохраняет своё имя точки', async () => {
  await fillUI('#pt-rename', 'Точка выхода');
  await page.press('#pt-rename', 'Enter');
  await page.waitForTimeout(300);
  return await page.evaluate(() => {
    const own = (el) => Array.prototype.filter.call(el.childNodes, n => n.nodeType === 3)
      .map(n => n.nodeValue).join('');
    const onChart = [...document.querySelectorAll('#chart text')].some(t => own(t) === 'Точка выхода');
    const gone = !document.getElementById('pt-rename');
    return (onChart && gone && STATE.pointNames.ext0 === 'Точка выхода')
           || JSON.stringify({ onChart, gone, names: STATE.pointNames });
  });
});

await t('своё имя точки уходит в экспорт, подсказка нет', () => page.evaluate(() => {
  const tex = buildTex('', '');
  return (tex.includes('Точка выхода') && !tex.includes('переименовать'))
         || 'имя ' + tex.includes('Точка выхода') + ', подсказка ' + tex.includes('переименовать');
}));

await t('Esc отменяет переименование', async () => {
  await page.locator('#chart text', { hasText: 'перегиб' }).first().dblclick();
  await page.waitForTimeout(200);
  await fillUI('#pt-rename', 'НЕ СОХРАНЯТЬ');
  await page.press('#pt-rename', 'Escape');
  await page.waitForTimeout(260);
  return await page.evaluate(() =>
    !Object.values(STATE.pointNames).includes('НЕ СОХРАНЯТЬ') || 'сохранилось вопреки Esc');
});

await t('смена сцены сбрасывает свои имена точек', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="m-tangent"]');
  await page.waitForTimeout(330);
  return await page.evaluate(() =>
    Object.keys(STATE.pointNames).length === 0 || JSON.stringify(STATE.pointNames));
});

/* --- Роль кривой спрашивается до формулы -------------------------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.evaluate(() => { resetSceneMemory(); openPicker(); });
await clickUI('.scard[data-scene="sd"]');
await page.evaluate(() => { STATE.curves = []; curveCounter = 0; STATE.params = {}; renderCurveList(); redrawAll(); });
await page.waitForTimeout(320);

await t('справка подстраивается под выбранную роль', async () => {
  const want = { '': 'PQ', demand: 'DEMAND', supply: 'SUPPLY', mc: 'MC', tc: 'TC', atc: 'ATC' };
  const bad = [];
  for (const role of Object.keys(want)) {
    await selectUI('#new-role', role);
    await page.waitForTimeout(120);
    const k = await page.evaluate(() => curveHelpKind());
    if (k !== want[role]) bad.push(`${role || 'обычная'}: ${k}`);
  }
  return bad.length === 0 || bad.join(', ');
});

await t('для издержек форма «объём от цены» скрыта', async () => {
  await selectUI('#new-role', 'mc');
  await page.waitForTimeout(140);
  const hidden = await page.evaluate(() =>
    document.getElementById('curve-form-seg').style.display === 'none' && STATE.curveForm === 'PQ');
  await selectUI('#new-role', 'demand');
  await page.waitForTimeout(140);
  const shown = await page.evaluate(() =>
    document.getElementById('curve-form-seg').style.display !== 'none');
  return (hidden && shown) || `скрыт ${hidden}, показан ${shown}`;
});

await t('кривая добавляется сразу со своей ролью', async () => {
  await page.evaluate(() => { STATE.curves = []; renderCurveList(); redrawAll(); });
  await selectUI('#new-role', 'mc');
  await page.evaluate(() => setFieldValue(document.getElementById('inp-formula'), '20'));
  await clickUI('#btn-add-curve');
  await page.waitForTimeout(220);
  return await page.evaluate(() => {
    const c = STATE.curves[0];
    // Поле формулы очищается только при успешном добавлении.
    const cleared = document.getElementById('inp-formula').value === '';
    return (c && c.role === 'mc' && cleared) || JSON.stringify({ role: c && c.role, cleared });
  });
});

// Подсказка формы записи идёт за выбранной ролью: примеров-попапа больше нет,
// но роль по-прежнему объясняется прямо под полем.
await t('подсказка под полем называет именно эту роль', async () => {
  await page.evaluate(() => {
    const sel = document.getElementById('new-role');
    sel.value = 'mc'; sel.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.waitForTimeout(200);
  const hint = await page.locator('#curve-form-hint').textContent();
  const ph = await page.getAttribute('#inp-formula', 'placeholder');
  return (/Предельные издержки/.test(hint) && /20/.test(ph || '')) || (hint + ' | ' + ph);
});

/* --- Прилипание своих точек к кривым ----------------------------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.evaluate(() => { resetSceneMemory(); openPicker(); });
await clickUI('.scard[data-scene="sd"]');   // D = 100 − Q, S = Q, равновесие (50; 50)
await page.waitForTimeout(340);

await t('щелчок рядом с кривой садится на кривую', () => page.evaluate(() => {
  const { mx, my } = mainScales();
  const h = snapPointAt(mx(30), my(72));       // мимо спроса на 2 по цене
  if (!h) return 'не прилипло';
  // На спросе D = 100 − Q цена и количество обязаны сойтись в сумме к 100.
  return (h.name === 'D' && Math.abs(h.x + h.y - 100) < 0.5) || JSON.stringify(h);
}));

await t('рядом с перекрестьем точка садится в пересечение', () => page.evaluate(() => {
  const { mx, my } = mainScales();
  const h = snapPointAt(mx(49), my(51));
  return (h && h.cross && Math.abs(h.x - 50) < 0.2 && Math.abs(h.y - 50) < 0.2)
         || JSON.stringify(h);
}));

await t('в пустом месте ничего не притягивается', () => page.evaluate(() => {
  const { mx, my } = mainScales();
  // При Q = 20 спрос даёт 80, предложение 20: цена 55 далека от обеих кривых.
  return snapPointAt(mx(20), my(55)) === null || 'притянуло на пустом месте';
}));

await t('точка на кривой скользит по ней при перетаскивании', () => page.evaluate(() => {
  const { mx, my } = mainScales();
  const h = snapPointAt(mx(70), my(72));       // рядом с предложением S = Q
  if (!h) return 'не прилипло к S';
  addMarkAt(h.x, h.y, h.cross ? null : h.name);
  const m = STATE.marks[STATE.marks.length - 1];
  if (m.snapTo !== 'S') return 'привязка: ' + m.snapTo;
  const f = markSnapFn(m);
  if (!f) return 'функция кривой не нашлась';
  m.x = 30; m.y = f(30);                        // как при перетаскивании
  const ok = Math.abs(m.y - 30) < 1e-6;         // на S = Q высота равна Q
  STATE.marks = []; renderMarkList(); redrawAll();
  return ok || 'после сдвига y = ' + m.y;
}));

await t('подсказка показывает, куда сядет точка, и убирается', () => page.evaluate(() => {
  const { mx, my } = mainScales();
  armMark(true);
  showSnapHint(snapPointAt(mx(30), my(71)));
  const shown = !!document.getElementById('snap-hint');
  armMark(false);                               // снятие режима убирает кружок
  return (shown && !document.getElementById('snap-hint')) || `показан ${shown}`;
}));

/* --- Легенда закрашенных областей -------------------------------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));

await t('легенда называет области в сцене налога', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="tax"]');
  await page.waitForTimeout(350);
  const names = await page.evaluate(() => [...document.querySelectorAll('#chart .legend text')].map(t =>
      [...t.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('')));
  const want = ['CS', 'PS', 'Tx', 'DWL'];
  return want.every(w => names.includes(w)) || names.join(' | ');
});

await t('субсидия подписана расходом, а не сбором', async () => {
  await page.evaluate(() => { setType('subsidy'); setTax(20); });
  await page.waitForTimeout(300);
  const names = await page.evaluate(() => [...document.querySelectorAll('#chart .legend text')].map(t =>
      [...t.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('')));
  const titles = await page.evaluate(() =>
    [...document.querySelectorAll('#chart .legend text title')].map(t => t.textContent));
  const ok = names.includes('GS') && titles.includes('Расход бюджета') && !titles.includes('Сбор бюджета');
  await page.evaluate(() => { setType('tax'); setTax(20); });
  await page.waitForTimeout(200);
  return ok || names.join(' | ');
});

await t('легенда собирается и в других режимах', async () => {
  const thin = [];
  for (const s of ['mono', 'labor', 'ppf', 'laffer', 'ext']) {
    await page.evaluate(() => { resetSceneMemory(); openPicker(); });
    await clickUI(`.scard[data-scene="${s}"]`);
    await page.waitForTimeout(300);
    const n = await page.evaluate(() => document.querySelectorAll('#chart .legend text').length);
    if (n < 1) thin.push(s);
  }
  return thin.length === 0 || 'без легенды: ' + thin.join(', ');
});

await t('легенда попадает в экспорт вместе с графиком', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="tax"]');
  await page.waitForTimeout(330);
  return await page.evaluate(() => {
    const tex = buildTex('', '');
    return (tex.includes('{Tx}') && tex.includes('{DWL}')) || 'подписей нет в .tex';
  });
});

await t('легенда выключается галочкой', async () => {
  await page.evaluate(() => { STATE.showLegend = false; redrawAll(); });
  const off = await page.evaluate(() => document.querySelectorAll('#chart .legend').length);
  await page.evaluate(() => { STATE.showLegend = true; redrawAll(); });
  const on = await page.evaluate(() => document.querySelectorAll('#chart .legend').length);
  return (off === 0 && on === 1) || `выкл ${off}, вкл ${on}`;
});

await t('легенда стоит выше поля графика, не поверх кривых', () => page.evaluate(() => {
  const t0 = document.querySelector('#chart .legend text');
  if (!t0) return 'легенды нет';
  const gw = document.getElementById('graph-wrap').getBoundingClientRect();
  const b0 = t0.getBoundingClientRect();
  return (b0.x > gw.x + gw.width / 2 && b0.y > gw.y + gw.height / 2)
    || 'легенда не в правом нижнем углу';
}));

/* --- Клавиатура и конструктор кусочной функции ------------------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.evaluate(() => { resetSceneMemory(); openPicker(); });
await clickUI('.scard[data-scene="sd"]');
await page.evaluate(() => { STATE.curves = []; curveCounter = 0; STATE.params = {}; renderCurveList(); redrawAll(); });
await page.waitForTimeout(320);
await clickUI('#fh-formula');
await page.waitForTimeout(220);

await t('в разделе функций есть всё нужное экономике', async () => {
  return await page.evaluate(() => {
    const kb = document.querySelector('.mkbd.open');
    if (!kb) return 'клавиатура закрыта';
    const tabs = [...kb.querySelectorAll('.mkbd-tab')];
    const fn = tabs.find(t => /Функц/.test(t.textContent));
    if (!fn) return 'нет раздела функций';
    fn.click();
    const labels = [...kb.querySelectorAll('.mkbd-pane.active .mk')].map(b => b.textContent);
    const need = ['√', '|x|', 'ln', 'log', 'sin', 'min', 'max', '≤', '≥', '≠'];
    const miss = need.filter(n => labels.indexOf(n) < 0);
    return !miss.length || 'нет: ' + miss.join(', ');
  });
});

await t('раздел букв даёт латиницу и греческие', async () => {
  return await page.evaluate(() => {
    const kb = document.querySelector('.mkbd.open');
    const tabs = [...kb.querySelectorAll('.mkbd-tab')];
    const ab = tabs.find(t => /Букв/.test(t.textContent));
    if (!ab) return 'нет раздела букв';
    ab.click();
    const labels = [...kb.querySelectorAll('.mkbd-pane.active .mk')].map(b => b.textContent);
    const need = ['a', 'z', 'α', 'β', 'π', 'Δ'];
    const miss = need.filter(n => labels.indexOf(n) < 0);
    return !miss.length || 'нет: ' + miss.join(', ');
  });
});

await t('печать слэша даёт дробь, крышки — степень', async () => {
  const has = await page.evaluate(() => !!document.getElementById('inp-formula')._mf);
  if (!has) return true;                       // без MathLive поле обычное, проверять нечего
  await page.evaluate(() => { const m = document.getElementById('inp-formula')._mf; m.value = ''; m.focusField(); });
  await page.waitForTimeout(120);
  await page.keyboard.type('100-Q/2', { delay: 25 });
  await page.waitForTimeout(200);
  const r1 = await page.evaluate(() => ({ tex: document.getElementById('inp-formula')._mf.value,
                                          txt: document.getElementById('inp-formula').value }));
  if (!/frac/.test(r1.tex)) return 'дроби нет: ' + r1.tex;
  await page.evaluate(() => { const m = document.getElementById('inp-formula')._mf; m.value = ''; m.focusField(); });
  await page.waitForTimeout(120);
  await page.keyboard.type('Q^2', { delay: 25 });
  await page.waitForTimeout(200);
  const r2 = await page.evaluate(() => document.getElementById('inp-formula').value);
  return r2.replace(/\s/g, '') === 'Q^(2)' || 'степень: ' + r2;
});

/* ── Русская раскладка ────────────────────────────────────────────────
   MathLive не находит кириллическую раскладку в своих таблицах и переходит на
   запасной путь, где читает ФИЗИЧЕСКИЙ код клавиши. Точка в русской раскладке
   сидит на той же клавише, где слэш в английской, — и вместо «0.5» получалась
   дробь. Проверяем настоящими событиями клавиатуры через CDP: обычный
   page.keyboard задать key и code по отдельности не умеет. */
const cdp = await page.context().newCDPSession(page);
const rawKey = async (key, code, vk) => {
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, text: key,
                                             windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key, code,
                                             windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
};
const clearFormula = async () => {
  await page.evaluate(() => { const m = document.getElementById('inp-formula')._mf; m.value = ''; m.focusField(); });
  await page.waitForTimeout(150);
};

await t('русская точка остаётся точкой, а не дробью', async () => {
  const has = await page.evaluate(() => !!document.getElementById('inp-formula')._mf);
  if (!has) return true;                       // без MathLive поле обычное, проверять нечего
  await clearFormula();
  await rawKey('0', 'Digit0', 48);
  await rawKey('.', 'Slash', 191);             // русская раскладка: точка на клавише слэша
  await rawKey('5', 'Digit5', 53);
  await page.waitForTimeout(220);
  const r = await page.evaluate(() => ({ tex: document.getElementById('inp-formula')._mf.value,
                                         txt: document.getElementById('inp-formula').value }));
  if (/frac/.test(r.tex)) return 'вышла дробь: ' + r.tex;
  return r.txt.replace(/\s/g, '') === '0.5' || 'в поле: ' + r.txt;
});

await t('настоящий слэш по-прежнему даёт дробь', async () => {
  const has = await page.evaluate(() => !!document.getElementById('inp-formula')._mf);
  if (!has) return true;
  await clearFormula();
  await rawKey('1', 'Digit1', 49);
  await rawKey('/', 'Slash', 191);
  await rawKey('2', 'Digit2', 50);
  await page.waitForTimeout(220);
  const tex = await page.evaluate(() => document.getElementById('inp-formula')._mf.value);
  return /frac/.test(tex) || 'дроби нет: ' + tex;
});

await t('конструктор кусочной собирает верную запись', async () => {
  await page.evaluate(() => {
    const kb = document.querySelector('.mkbd.open') || document.querySelector('.mkbd');
    const b = [...kb.querySelectorAll('.mkbd-foot button')].find(x => /Кусочн/.test(x.textContent));
    if (b) b.click(); else openPiecewise(document.getElementById('inp-formula'), 'Q');
  });
  await page.waitForTimeout(280);
  // Число кусков задаётся числом, а не выбором из готовых вариантов.
  const nOk = await page.evaluate(() => {
    const c = document.getElementById('pw-count');
    if (!c) return false;
    c.value = '3'; c.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  });
  if (!nOk) return 'нет поля числа кусков';
  await page.waitForTimeout(220);
  const rowsN = await page.evaluate(() => document.querySelectorAll('#pw-rows .pw-row').length);
  if (rowsN !== 3) return 'строк ' + rowsN;
  // Поля формул теперь набираются MathLive, а исходный input под ним скрыт,
  // поэтому заполняем их так же, как это делает сам движок ввода.
  await page.evaluate(() => {
    const rows = [...document.querySelectorAll('#pw-rows .pw-row')];
    const put = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); };
    const data = [['100 - Q', '0', '40'], ['60', '40', '70'], ['20', '70', '']];
    rows.forEach((r, i) => {
      put(r.querySelector('.f-slot input[type=text]'), data[i][0]);
      const bs = r.querySelectorAll('input.pw-bound');
      put(bs[0], data[i][1]);
      put(bs[1], data[i][2]);
    });
  });
  await page.waitForTimeout(220);
  await clickUI('#pw-apply');
  await page.waitForTimeout(220);
  return await page.evaluate(() => {
    const expr = document.getElementById('inp-formula').value;
    const r = compileFormula(expr);
    if (r.error) return 'не компилируется: ' + r.error;
    const at = (q) => r.compiled.evaluate({ x: q, Q: q, L: q });
    return (at(10) === 90 && at(50) === 60 && at(90) === 20) || `${expr} → ${at(10)}/${at(50)}/${at(90)}`;
  });
});

await t('кусочная кривая строится движком', () => page.evaluate(() => {
  addCurve(document.getElementById('inp-formula').value);
  const c = STATE.curves[STATE.curves.length - 1];
  return (c.linear === null && evalCurve(c, 10) === 90 && evalCurve(c, 90) === 20)
         || JSON.stringify({ lin: c.linear, v10: evalCurve(c, 10), v90: evalCurve(c, 90) });
}));

/* --- Зум колесом и тачпадом ------------------------------------------- */
// Проверка экспорта выше оставила своё модальное окно открытым, а оно ловит
// указатель поверх графика. Закрываем, иначе колесо до холста не доедет.
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.waitForTimeout(150);
await page.evaluate(() => { resetSceneMemory(); openPicker(); });
await clickUI('.scard[data-scene="sd"]');
await page.waitForTimeout(320);

await t('колесо к себе приближает график', async () => {
  const before = await page.evaluate(() => CONFIG.Qmax);
  await page.mouse.move(700, 450);
  await page.mouse.wheel(0, -300);
  await page.waitForTimeout(220);
  const after = await page.evaluate(() => CONFIG.Qmax);
  return after < before || `${before} → ${after}`;
});

await t('колесо от себя отдаляет', async () => {
  const before = await page.evaluate(() => CONFIG.Qmax);
  await page.mouse.wheel(0, 600);
  await page.waitForTimeout(220);
  const after = await page.evaluate(() => CONFIG.Qmax);
  return after > before || `${before} → ${after}`;
});

await t('поля «Оси» идут за колесом', () => page.evaluate(() =>
  Math.abs(parseFloat(document.getElementById('inp-qmax').value) - CONFIG.Qmax) < 1e-6 || 'поле отстало'));

await t('двойной щелчок возвращает масштаб сцены', async () => {
  await page.dblclick('#graph-wrap', { position: { x: 300, y: 250 } });
  await page.waitForTimeout(280);
  return await page.evaluate(() => (CONFIG.Qmax === 100 && CONFIG.Pmax === 100 && !STATE.zoomLock) || CONFIG.Qmax);
});

await t('в математике окно тянется к курсору', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="m-optimum"]');
  await page.waitForTimeout(320);
  const b = await page.evaluate(() => [STATE.mathXmin, STATE.mathXmax]);
  await page.mouse.move(500, 400);
  await page.mouse.wheel(0, -300);
  await page.waitForTimeout(220);
  const a = await page.evaluate(() => [STATE.mathXmin, STATE.mathXmax]);
  // Окно сузилось и сместилось несимметрично: курсор был левее середины.
  const narrower = (a[1] - a[0]) < (b[1] - b[0]);
  const shifted = Math.abs((a[0] + a[1]) / 2 - (b[0] + b[1]) / 2) > 1e-6;
  return (narrower && shifted) || `${b} → ${a}`;
});

await t('авто-подгонка сцены не сбивает ручной зум', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="adas"]');
  await page.waitForTimeout(360);
  await page.mouse.move(700, 450);
  await page.mouse.wheel(0, -400);
  await page.waitForTimeout(220);
  const zoomed = await page.evaluate(() => CONFIG.Qmax);
  await page.evaluate(() => redrawAll());
  await page.waitForTimeout(200);
  const after = await page.evaluate(() => CONFIG.Qmax);
  return after === zoomed || `${zoomed} → ${after}`;
});

/* --- Правка формулы прямо в карточке кривой ---------------------------- */
await page.evaluate(() => { resetSceneMemory(); openPicker(); });
await clickUI('.scard[data-scene="sd"]');
await page.waitForTimeout(320);
await page.evaluate(() => setToolsOpen(true));
await page.waitForTimeout(180);

await t('у каждой кривой есть поле формулы', async () =>
  (await page.locator('.curve-expr-inp').count()) === 2 || 'полей: ' + (await page.locator('.curve-expr-inp').count()));

await t('правка формулы пересчитывает равновесие', async () => {
  await reveal('.curve-expr-inp');
  await page.locator('.curve-expr-inp').first().fill('200 - 2*Q');
  await page.waitForTimeout(300);
  return await page.evaluate(() => {
    const e = STATE.eq;
    return (Math.abs(e.Q - 66.667) < .1 && Math.abs(e.P - 66.667) < .1) || JSON.stringify(e);
  });
});

await t('правка сохраняет роль, цвет и id кривой', () => page.evaluate(() =>
  (STATE.curves[0].role === 'demand' && STATE.curves[0].id === 1) || JSON.stringify(STATE.curves[0])));

await t('битая формула не сносит кривую', async () => {
  await reveal('.curve-expr-inp');
  await page.locator('.curve-expr-inp').first().fill('200 - 2*');
  await page.waitForTimeout(250);
  const bad = await page.evaluate(() => document.querySelector('.curve-expr-inp').classList.contains('bad'));
  const kept = await page.evaluate(() => STATE.curves[0].expr);
  return (bad && kept === '200 - 2*Q') || `подсветка ${bad}, формула ${kept}`;
});

/* --- Пикер цвета не убивает собственную палитру ------------------------ */
await t('правка цвета не пересобирает список кривых', () => page.evaluate(() => {
  const inp = document.querySelector('#curve-list input[type=color]');
  if (!inp) return 'пикера нет';
  inp.value = '#123456';
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  // Если бы список перерисовался, узел был бы уже другим и нативная палитра
  // браузера захлопнулась бы на первом же клике по градиенту.
  return document.querySelector('#curve-list input[type=color]') === inp || 'узел заменён';
}));

await t('цвет из пикера доехал до кривой', () => page.evaluate(() =>
  STATE.curves[0].color === '#123456' || STATE.curves[0].color));

/* --- Построение графиков: список функций растёт сам --------------------- */
await page.evaluate(() => { resetSceneMemory(); openPicker(); });
await clickUI('.scard[data-scene="m-graph"]');
await page.waitForTimeout(400);
await page.evaluate(() => setToolsOpen(true));
await page.waitForTimeout(180);

await t('сцена открывается пустой: ни одной кривой', () => page.evaluate(() =>
  (STATE.curves.length === 0 && STATE.mode === 'graph') || `кривых ${STATE.curves.length}, режим ${STATE.mode}`));

await t('в списке ровно одна пустая строка', async () =>
  (await page.locator('#graph-rows .grow').count()) === 1
  || 'строк: ' + (await page.locator('#graph-rows .grow').count()));

await t('начали печатать — строка стала кривой, снизу новая пустая', async () => {
  await page.evaluate(() => {
    const inp = document.querySelector('#graph-rows .grow .f-slot input');
    inp.value = 'x^2 - 4';
    inp.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(300);
  const rows = await page.locator('#graph-rows .grow').count();
  const n = await page.evaluate(() => STATE.curves.length);
  return (rows === 2 && n === 1) || `строк ${rows}, кривых ${n}`;
});

await t('вторая функция добавляется так же', async () => {
  await page.evaluate(() => {
    const inps = document.querySelectorAll('#graph-rows .grow .f-slot input');
    const last = inps[inps.length - 1];
    last.value = '2*x + 1';
    last.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(300);
  const rows = await page.locator('#graph-rows .grow').count();
  const n = await page.evaluate(() => STATE.curves.length);
  return (rows === 3 && n === 2) || `строк ${rows}, кривых ${n}`;
});

await t('обе кривые нарисованы', () => page.evaluate(() =>
  document.querySelectorAll('#chart path[data-curve]').length === 2
  || 'линий: ' + document.querySelectorAll('#chart path[data-curve]').length));

await t('видна отрицательная часть плоскости', () => page.evaluate(() =>
  (CONFIG.Qmin < 0 && CONFIG.Pmin < 0 && STATE.firstQuad === false)
  || JSON.stringify({ q: CONFIG.Qmin, p: CONFIG.Pmin, fq: STATE.firstQuad })));

await t('у сцены нет «Аналитики»', () => page.evaluate(() => {
  const p = document.getElementById('params-panel');
  const s = document.getElementById('scoreboard');
  return (p.classList.contains('empty') && s.classList.contains('hidden'))
    || `панель пустая ${p.classList.contains('empty')}, расчёты скрыты ${s.classList.contains('hidden')}`;
}));

await t('свои точки и площади остались', () => page.evaluate(() => {
  const view = document.getElementById('sec-view');
  const area = document.getElementById('sec-areascalc');
  return (view.style.display !== 'none' && area.style.display !== 'none')
    || 'секции спрятаны';
}));

await t('буква из формулы даёт ползунок', async () => {
  await page.evaluate(() => {
    const inps = document.querySelectorAll('#graph-rows .grow .f-slot input');
    const last = inps[inps.length - 1];
    last.value = 'kx';
    last.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(320);
  return await page.evaluate(() => {
    const names = Object.keys(STATE.params || {});
    return (names.length === 1 && names[0] === 'k') || 'параметры: ' + names.join(',');
  });
});

await t('удаление строки убирает кривую', async () => {
  const before = await page.evaluate(() => STATE.curves.length);
  await page.evaluate(() => document.querySelector('#graph-rows .grow .btn-icon').click());
  await page.waitForTimeout(260);
  const after = await page.evaluate(() => STATE.curves.length);
  return after === before - 1 || `${before} → ${after}`;
});

await t('в других сценах «Аналитика» вернулась', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="sd"]');
  await page.waitForTimeout(340);
  return await page.evaluate(() => {
    const p = document.getElementById('params-panel');
    const s = document.getElementById('scoreboard');
    return (!p.classList.contains('empty') && !s.classList.contains('hidden')) || 'панель всё ещё пустая';
  });
});

/* ── Фаза 4. Правая панель — «Аналитика» ──────────────────────────────
   Ползунки сверху и всегда открыты, ниже два свёрнутых блока: расчёты и
   разбор. Кнопки «включить аналитику» в полосе иконок больше нет. */
await t('правая панель называется «Аналитика»', () => page.evaluate(() => {
  const h = document.querySelector('#params-panel .side-head h2');
  return (h && h.textContent.trim() === 'Аналитика') || 'заголовок: ' + (h ? h.textContent : 'нет');
}));

await t('кнопки аналитики в полосе иконок нет', () => page.evaluate(() =>
  !document.getElementById('dock-score') || 'кнопка ещё есть'));

await t('ползунки открыты и не сворачиваются', () => page.evaluate(() => {
  const body = document.getElementById('params-body');
  if (!body) return 'нет #params-body';
  if (body.closest('.fold-body')) return 'ползунки внутри складного блока';
  return getComputedStyle(body).display !== 'none' || 'ползунки спрятаны';
}));

await t('расчёты и разбор свёрнуты по умолчанию', () => page.evaluate(() => {
  const bad = [];
  [['sb-btn', 'sb-fold'], ['ex-btn', 'ex-fold']].forEach(([b, f]) => {
    const btn = document.getElementById(b), box = document.getElementById(f);
    if (!btn || !box) { bad.push(b + ': нет узла'); return; }
    if (btn.getAttribute('aria-expanded') !== 'false') bad.push(b + ': развёрнут');
    if (box.classList.contains('open')) bad.push(f + ': открыт');
  });
  return !bad.length || bad.join('; ');
}));

await t('блок «Ключевые значения» раскрывается щелчком', async () => {
  await clickUI('#sb-btn');
  await page.waitForTimeout(180);
  const r = await page.evaluate(() => {
    const box = document.getElementById('sb-fold');
    const txt = document.getElementById('sb-body').textContent;
    return { open: box.classList.contains('open'), len: txt.trim().length };
  });
  await clickUI('#sb-btn');
  return (r.open && r.len > 0) || JSON.stringify(r);
});

await t('панели левая и правая одной ширины', async () => {
  await page.evaluate(() => { setToolsOpen(true); setParamsOpen(true); });
  await page.waitForTimeout(320);
  return await page.evaluate(() => {
    const l = document.getElementById('tools-panel').getBoundingClientRect().width;
    const r = document.getElementById('params-panel').getBoundingClientRect().width;
    return Math.abs(l - r) < 1.5 || `слева ${Math.round(l)}, справа ${Math.round(r)}`;
  });
});

await t('разбор уезжает из расчётов в «Объяснение модели»', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="ppf"]');
  await page.waitForTimeout(420);
  return await page.evaluate(() => {
    const sb = document.getElementById('sb-body'), ex = document.getElementById('ex-body');
    if (sb.querySelector('.sb-note')) return 'врезка осталась в расчётах';
    if (!ex.querySelector('.sb-note')) return 'врезки нет в объяснении';
    if (/Как это получилось/.test(ex.textContent)) return 'внутренний заголовок не снят';
    return document.getElementById('explain').classList.contains('hidden') ? 'блок разбора спрятан' : true;
  });
});

/* ── Фаза 5. Панель ввода — список карточек ───────────────────────────
   Все блоки закрыты, у каждого свой заголовок, раскрытый меняет фон,
   первая видимая карточка выделена. */
await t('все карточки панели ввода закрыты', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="sd"]');
  await page.waitForTimeout(340);
  await page.evaluate(() => setToolsOpen(true));
  await page.waitForTimeout(200);
  return await page.evaluate(() => {
    const bad = [];
    document.querySelectorAll('#tools-panel .tools-body > .section').forEach(sec => {
      const btn = sec.querySelector(':scope > .fold-btn');
      if (!btn) { bad.push((sec.id || '?') + ': нет заголовка'); return; }
      if (btn.getAttribute('aria-expanded') !== 'false') bad.push((sec.id || '?') + ': раскрыт');
      if (!(btn.querySelector('span') || {}).textContent) bad.push((sec.id || '?') + ': заголовок пуст');
    });
    return !bad.length || bad.join('; ');
  });
});

await t('первая видимая карточка выделена одна', () => page.evaluate(() => {
  const all = [...document.querySelectorAll('#tools-panel .tools-body > .section')];
  const marked = all.filter(s => s.classList.contains('first-card'));
  const firstVisible = all.find(s => s.style.display !== 'none');
  return (marked.length === 1 && marked[0] === firstVisible)
    || 'выделено ' + marked.length + ', первая видимая ' + (firstVisible ? firstVisible.id : 'нет');
}));

await t('раскрытая карточка отличается фоном', async () => {
  await clickUI('#sec-curves > .fold-btn');
  await page.waitForTimeout(180);
  const r = await page.evaluate(() => {
    const sec = document.getElementById('sec-curves');
    const body = sec.querySelector(':scope > .fold-body');
    return { open: body.classList.contains('open'), card: sec.classList.contains('open-card'),
             bg: getComputedStyle(sec).backgroundColor };
  });
  await page.evaluate(() => document.querySelector('#sec-curves > .fold-btn').click());
  const closed = await page.evaluate(() => getComputedStyle(document.getElementById('sec-curves')).backgroundColor);
  return (r.open && r.card && r.bg !== closed) || JSON.stringify(r) + ' закрытая ' + closed;
});

/* ── П2. Первый экран: десять карточек блоков по две в ряд ───────────
   Щелчок по карточке убирает остальные и показывает модели этого блока. */
await t('карточки блоков без номеров, ни один блок не раскрыт', async () => {
  // Первый вход: сцены ещё не выбирали, поэтому видна полная карта блоков.
  // Возврат ИЗ сюжета ведёт в его блок — это проверяет следующий случай (Н5).
  await page.evaluate(() => { resetSceneMemory(); STATE.sceneKey = null; openPicker(); });
  await page.waitForTimeout(200);
  return await page.evaluate(() => {
    const bad = [];
    const cards = [...document.querySelectorAll('#picker-blocks .bcard')];
    if (cards.length !== 10) bad.push('карточек ' + cards.length);
    cards.forEach(c => {
      const nm = (c.querySelector('.bcard-name') || {}).textContent || '';
      if (/^ *[0-9]+ *·/.test(nm)) bad.push('номер в «' + nm.trim() + '»');
    });
    const open = document.querySelectorAll('#scene-picker .picker-group.open').length;
    if (open) bad.push('раскрыто блоков: ' + open);
    return !bad.length || bad.join('; ');
  });
});

/* Н5. Из сюжета «назад» ведёт РОВНО на предыдущий экран: в тот блок, где этот
   сюжет лежит, а не в общий список десяти. Прежнее правило (П2, всегда полная
   карта) отменено. */
await t('из сюжета возврат ведёт в его блок (Н5)', async () => {
  return await page.evaluate(() => {
    const bad = [];
    [['laffer', 'Избранные сюжеты'], ['mono-nat', 'Несовершенная конкуренция'],
     ['m-tangent', 'Математика']].forEach(([key, want]) => {
      closePicker(); pickScene(key); openPicker();
      const g = document.querySelector('#scene-picker .picker-group.open');
      const got = g ? (g.querySelector('.picker-group-open-name') || {}).textContent : null;
      if (got !== want) bad.push(key + ': «' + got + '» вместо «' + want + '»');
      if (!document.getElementById('picker-blocks').classList.contains('hidden')) {
        bad.push(key + ': список блоков не спрятан');
      }
    });
    closePicker();
    return !bad.length || bad.join('; ');
  });
});

await t('открыт один блок за раз, есть возврат', async () => {
  await page.evaluate(() => { STATE.sceneKey = null; openPicker(); });
  await page.waitForTimeout(120);
  await page.click('#picker-blocks .bcard:nth-child(1)');
  await page.waitForTimeout(160);
  await page.evaluate(() => document.getElementById('picker-back').click());
  await page.waitForTimeout(120);
  await page.click('#picker-blocks .bcard:nth-child(2)');
  await page.waitForTimeout(160);
  return await page.evaluate(() => {
    const open = document.querySelectorAll('#scene-picker .picker-group.open').length;
    const back = document.getElementById('picker-back').classList.contains('shown');
    return (open === 1 && back) || `открытых блоков: ${open}, возврат ${back}`;
  });
});

await t('свободного холста нет ни в окне, ни в маршрутах', () => page.evaluate(() =>
  (!document.querySelector('.scard[data-scene="free"]') && typeof SCENE_ROUTE.free === 'undefined')
  || 'холст ещё на месте'));

/* ── Наблюдатель за размером холста ───────────────────────────────────
   Перерисовка пересоздаёт содержимое #graph-wrap, поэтому наблюдение легко
   зацикливается: перерисовал — размер «изменился» — перерисовал снова.
   Проверяем, что число перерисовок конечно и равно числу действий, а в покое
   не растёт вовсе. */
await t('свёртывание панели не запускает вечную перерисовку', async () => {
  await page.evaluate(() => { STATE.resizeRedraws = 0; });
  for (let i = 0; i < 5; i++) {
    await page.evaluate(() => setToolsOpen(false));
    await page.waitForTimeout(240);
    await page.evaluate(() => setToolsOpen(true));
    await page.waitForTimeout(240);
  }
  const afterClicks = await page.evaluate(() => STATE.resizeRedraws);
  await page.waitForTimeout(1200);              // спокойная пауза без действий
  const idle = await page.evaluate(() => STATE.resizeRedraws);
  if (idle !== afterClicks) return `в покое прибавилось ${idle - afterClicks} перерисовок`;
  return afterClicks <= 12 || `на 10 щелчков ${afterClicks} перерисовок`;
});

/* ── Фаза 7. Площади ──────────────────────────────────────────────────
   Вершины набираются щелчками по графику с примагничиванием к особым точкам,
   списка с галочками нет, у числовых полей нет крутилок. */
await t('списка вершин с галочками больше нет', () => page.evaluate(() =>
  !document.getElementById('ac-points') || 'список ещё в разметке'));

await t('у числовых полей калькулятора нет крутилок', () => page.evaluate(() => {
  const inp = document.querySelector('.app input[type=number]');
  if (!inp) return 'числовых полей не нашлось';
  const st = getComputedStyle(inp);
  const look = st.appearance || st.MozAppearance || st.webkitAppearance;
  return look === 'textfield' || 'appearance: ' + look;
}));

await t('режим «Между точками» взводит набор вершин', async () => {
  await page.evaluate(() => { openPicker(); });
  await clickUI('.scard[data-scene="sd"]');
  await page.waitForTimeout(340);
  return await page.evaluate(() => {
    setAreaCalcMode('poly');
    const ok = STATE.vertArm === true;
    return ok || 'режим не взведён';
  });
});

await t('щелчок по графику ставит вершину', async () => {
  await page.evaluate(() => { clearAreaVerts(); setAreaCalcMode('poly'); });
  const box = await page.locator('#chart').boundingBox();
  await page.mouse.click(box.x + box.width * 0.35, box.y + box.height * 0.45);
  await page.waitForTimeout(380);
  await page.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.62);
  await page.waitForTimeout(380);
  const n = await page.evaluate(() => (STATE.areaVerts || []).length);
  return n === 2 || 'вершин набрано: ' + n;
});

await t('вершина садится в особую точку и называет её', async () => {
  // Проверяем сам механизм доводки: щелчок мимо на десяток пикселей обязан
  // дать ровно ту особую точку. Настоящий щелчок по холсту проверен выше,
  // здесь важна арифметика примагничивания, а не попадание мышью.
  return await page.evaluate(() => {
    setAreaCalcMode('poly'); clearAreaVerts();
    const { mx, my } = mainScales();
    const p = keyTargets().filter(k => /пересечение D и S/.test(k.name))[0];
    if (!p) return 'особой точки «пересечение D и S» нет';
    const hit = snapVertexAt(mx(p.x) + 9, my(p.y) - 8);
    setAreaCalcMode('curve');
    if (!hit || !hit.key) return 'вершина не прилипла к особой точке';
    if (Math.abs(hit.x - p.x) > 1e-6 || Math.abs(hit.y - p.y) > 1e-6) return 'прилипла не туда';
    return /пересечение D и S/.test(hit.name) || 'без имени: ' + hit.name;
  });
});

await t('надписи «Пока нет своих точек» нет', () => page.evaluate(() =>
  !/Пока нет своих точек/.test(document.getElementById('mark-list').textContent)
  || 'надпись на месте'));

/* ── Фаза 8. Сцены КТВ ────────────────────────────────────────────────
   На графике нет подписей вида «Xмакс=», «производство» всплывает по
   наведению, регулятор мировой цены собран в одном месте. */
await t('на графике КТВ нет подписей вида «Xмакс=»', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="tradeprice"]');
  await page.waitForTimeout(420);
  return await page.evaluate(() => {
    setTradeScenario('A'); redrawAll();
    const bad = [...document.querySelectorAll('#chart text')]
      .map(n => n.textContent).filter(t => /макс\s*=|п\s*=/.test(t));
    return !bad.length || 'остались: ' + bad.join(', ');
  });
});

await t('«производство» спрятано и всплывает по наведению', () => page.evaluate(() => {
  const lab = [...document.querySelectorAll('#chart .hover-label')]
    .filter(g => /производство/.test(g.textContent))[0];
  if (!lab) return 'подписи «производство» нет вовсе';
  return getComputedStyle(lab).display === 'none' || 'подпись видна сразу';
}));

await t('регулятор мировой цены собран в правой панели', async () => {
  await page.evaluate(() => { setTradeScenario('B'); redrawAll(); });
  await page.waitForTimeout(260);
  return await page.evaluate(() => {
    const f = document.getElementById('tb-price-field');
    if (!f) return 'поля цены нет';
    if (!f.querySelector('#tb-price-slider')) return 'ползунка нет в поле';
    if (!f.querySelector('#inp-tb-price')) return 'точного поля нет рядом';
    return !!f.closest('#params-body') || 'поле не в правой панели';
  });
});

await t('ползунок и точное поле мировой цены синхронны', async () => {
  await page.evaluate(() => {
    const sl = document.getElementById('tb-price-slider');
    sl.value = '1.8';
    sl.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForTimeout(300);
  const v = await page.evaluate(() => parseFloat(document.getElementById('inp-tb-price').value));
  await page.evaluate(() => { STATE.tbManualPrice = null; redrawAll(); });
  return Math.abs(v - 1.8) < 0.06 || 'в поле ' + v;
});

/* ── Фаза 9. Математика в подписях и остатки CONFIG ──────────────────
   Звёздочка на графике стала верхним индексом, подпись не лежит на оси,
   прямоугольник обрезки считается по шкалам сцены. */
await t('в подписях на графике нет звёздочки вместо индекса', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="m-optimum"]');
  await page.waitForTimeout(420);
  return await page.evaluate(() => {
    STATE.mathFormula = 'x^3 - 3*x'; setMathWindow(-3, 3, -6, 6);
    STATE.mathInflect = true; redrawAll();
    const raw = [...document.querySelectorAll('#chart text')].filter(t => {
      const own = [...t.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('');
      return /[*]/.test(own);
    }).map(t => t.textContent.slice(0, 30));
    if (raw.length) return 'сырая звёздочка в: ' + raw.join(' | ');
    const sup = [...document.querySelectorAll('#chart text')].filter(t => t.querySelector('tspan[dy]'));
    return sup.length >= 3 || 'подписей с индексом: ' + sup.length;
  });
});

await t('подпись перегиба не лежит на оси', () => page.evaluate(() => {
  const { my } = mathScales();
  const axisY = my(0);
  const inf = [...document.querySelectorAll('#chart text')].filter(t => /перегиб/.test(t.textContent))[0];
  if (!inf) return 'подписи перегиба нет';
  const d = Math.abs(parseFloat(inf.getAttribute('y')) - axisY);
  return d >= 18 || 'до оси всего ' + Math.round(d) + ' px';
}));

await t('прямоугольник обрезки считается по шкалам сцены', () => page.evaluate(() => {
  const r = document.querySelector('#plot-clip rect');
  if (!r) return 'обрезки нет';
  const { mx } = mathScales();
  const [px0, px1] = mx.range();
  const x = parseFloat(r.getAttribute('x')), w = parseFloat(r.getAttribute('width'));
  // Окно «Математики» уходит в минус: прямоугольник обязан начинаться у левого
  // края поля, а не там, куда его увела бы граница из CONFIG.
  return (Math.abs(x - px0) < 2 && Math.abs(w - (px1 - px0)) < 2)
    || 'обрезка ' + Math.round(x) + '…' + Math.round(x + w) + ', поле ' + Math.round(px0) + '…' + Math.round(px1);
}));

await t('в рыночной сцене подпись равновесия тоже с индексом', async () => {
  await page.evaluate(() => { resetSceneMemory(); openPicker(); });
  await clickUI('.scard[data-scene="sd"]');
  await page.waitForTimeout(400);
  return await page.evaluate(() => {
    const raw = [...document.querySelectorAll('#chart text')].filter(t => {
      const own = [...t.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('');
      return /[*]/.test(own);
    });
    return !raw.length || 'сырых звёздочек: ' + raw.length;
  });
});

console.log('\n' + checks.map(([s, n, d]) => `${s.padEnd(4)} ${n}${d ? '  → ' + d : ''}`).join('\n'));
const bad = checks.filter(c => c[0] !== 'OK').length;
if (errors.length) console.log('\nОшибки страницы:\n' + errors.slice(0, 10).join('\n'));
console.log(`\nИтог: ${checks.length - bad}/${checks.length} прошло, ошибок страницы: ${errors.length}`);
await browser.close();
process.exit(bad || errors.length ? 1 : 0);
