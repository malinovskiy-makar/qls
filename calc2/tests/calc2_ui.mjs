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
  try { const r = await fn(); checks.push([r === true ? 'OK' : 'FAIL', name, r === true ? '' : String(r)]); }
  catch (e) { checks.push(['ERR', name, e.message]); }
};

await t('окно сценариев открыто', () => page.locator('#scene-picker').isVisible());
await t('#sec-mode удалён', async () => (await page.locator('#sec-mode').count()) === 0 || 'ещё есть');
await t('#sec-scenes удалён', async () => (await page.locator('#sec-scenes').count()) === 0 || 'ещё есть');
await t('#sec-view есть', async () => (await page.locator('#sec-view').count()) === 1 || 'нет секции');

// Входим в сцену «Спрос и предложение».
await page.click('.scard[data-scene="sd"]');
await page.waitForTimeout(400);

await t('равновесие 50/50 не сломано', () => page.evaluate(() => {
  const e = STATE.eq; return (Math.abs(e.Q - 50) < .3 && Math.abs(e.P - 50) < .3) || JSON.stringify(e);
}));

await t('заголовок графика рисуется', async () => {
  await page.fill('#inp-gtitle', 'Рынок хлеба');
  await page.waitForTimeout(250);
  return await page.evaluate(() =>
    [...document.querySelectorAll('#chart text')].some(n => n.textContent === 'Рынок хлеба') || 'нет текста в SVG');
});

await t('своё имя оси X попадает на график', async () => {
  await page.fill('#inp-xname', 'Батоны');
  await page.waitForTimeout(250);
  return await page.evaluate(() =>
    [...document.querySelectorAll('#chart text')].some(n => n.textContent === 'Батоны') || 'нет метки оси');
});

await t('плейсхолдер оси Y = сценовое название', async () =>
  (await page.getAttribute('#inp-yname', 'placeholder')) === 'P' || 'плейсхолдер не P');

await t('своя точка ставится и подписывается', async () => {
  await page.evaluate(() => { addMarkAt(30, 70); STATE.marks[0].text = 'Мой ориентир'; redrawAll(); });
  await page.waitForTimeout(200);
  return await page.evaluate(() =>
    [...document.querySelectorAll('#chart text')].some(n => n.textContent === 'Мой ориентир') || 'нет подписи точки');
});

await t('точка показывает координаты', () => page.evaluate(() =>
  [...document.querySelectorAll('#chart text')].some(n => n.textContent === '(30; 70)') || 'нет координат'));

await t('точка показывает значения кривых', () => page.evaluate(() => {
  STATE.marks[0].showCurves = true; redrawAll();
  return [...document.querySelectorAll('#chart text')].some(n => /^D = 70$/.test(n.textContent)) || 'нет значения D';
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
  await page.evaluate(() => { openPicker(); pickScene('mono'); closePicker(); });
  await page.waitForTimeout(300);
  return await page.evaluate(() =>
    (STATE.graphTitle === '' && STATE.axisXName === '' && STATE.marks.length === 0) ||
    JSON.stringify({ t: STATE.graphTitle, x: STATE.axisXName, m: STATE.marks.length }));
});

await t('монополия 40/60 не сломана', () => page.evaluate(() =>
  (Math.abs(STATE.mono.Qm - 40) < .3 && Math.abs(STATE.mono.Pm - 60) < .3) || JSON.stringify(STATE.mono)));

// ── Фаза 2: пикеры у кривых издержек ────────────────────────────────────
await page.evaluate(() => { openPicker(); pickScene('costs'); closePicker(); });
await page.waitForTimeout(400);

await t('у пяти кривых издержек есть пикеры', async () => {
  const n = await page.locator('#sec-costs input[type=color][data-col^="cost"]').count();
  return n === 5 || `пикеров ${n}`;
});

await t('ключи цвета уникальны (MP ≠ MC и т.п.)', () => page.evaluate(() => {
  const keys = [...document.querySelectorAll('input.swatch-pick[data-col]')].map(i => i.dataset.col);
  const dup = keys.filter((k, i) => keys.indexOf(k) !== i);
  return dup.length === 0 || 'дубли: ' + dup.join(',');
}));

// Пикер лежит внутри <label class="chk"> рядом с галочкой. Проверяем, что клик по
// нему НЕ переключает галочку (браузер не пробрасывает клик с вложенного
// интерактивного элемента на элемент, к которому привязан label).
await t('клик по пикеру не сбрасывает галочку кривой', () => page.evaluate(() => {
  const chk = document.getElementById('chk-mc');
  const pick = document.querySelector('input[data-col="costMC"]');
  const before = chk.checked;
  pick.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
  return chk.checked === before || `галочка была ${before}, стала ${chk.checked}`;
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
const svgTexts = () => page.evaluate(() => [...document.querySelectorAll('#chart text')].map(n => n.textContent));

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
  await page.evaluate(() => { openPicker(); pickScene('sd'); closePicker(); });
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

await t('предпросмотр под полем формулы рендерит математику', async () => {
  await page.fill('#inp-formula', '100 - 2*Q');
  await page.waitForTimeout(200);
  return await page.evaluate(() => {
    const p = document.querySelector('#sec-curves .f-preview');
    return (p && p.classList.contains('has') && p.querySelector('.katex') !== null)
      || (p ? 'нет .katex: ' + p.innerHTML.slice(0, 60) : 'нет .f-preview');
  });
});

await t('пустое поле прячет предпросмотр', async () => {
  await page.fill('#inp-formula', '');
  await page.waitForTimeout(150);
  return await page.evaluate(() => {
    const p = document.querySelector('#sec-curves .f-preview');
    return !p.classList.contains('has') || 'предпросмотр остался';
  });
});

await t('в попапе примеры набраны математикой, не текстом', async () => {
  await page.evaluate(() => document.getElementById('fh-formula').click());
  await page.waitForTimeout(250);
  return await page.evaluate(() => {
    const pop = document.getElementById('fp-formula');
    const n = pop.querySelectorAll('.f-ex .f-ex-math .katex').length;
    return n === 4 || `формул с KaTeX: ${n}`;
  });
});

await t('клик по примеру подставляет его в поле', async () => {
  // Панель прокручиваемая, поэтому кликаем программно, а не курсором.
  await page.evaluate(() => document.querySelector('#fp-formula .f-ex').click());
  await page.waitForTimeout(200);
  const v = await page.inputValue('#inp-formula');
  return v === '100 - 2*Q' || `в поле «${v}»`;
});

await t('после подстановки предпросмотр обновился, попап закрылся', () => page.evaluate(() => {
  const pop = document.getElementById('fp-formula');
  const p = document.querySelector('#sec-curves .f-preview');
  return (!pop.classList.contains('open') && p.classList.contains('has')) || 'попап открыт или предпросмотр пуст';
}));

await t('своё имя кривой заменяет родовое D на графике', async () => {
  await page.evaluate(() => { STATE.curves[0].label = 'Спрос молодёжи'; redrawAll(); });
  await page.waitForTimeout(200);
  const tx = await svgTexts();
  return (tx.includes('Спрос молодёжи') && !tx.includes('D')) || 'есть: ' + tx.join('|');
});

// ── Фаза 8: один вход вместо двух ───────────────────────────────────────
await page.evaluate(() => { openPicker(); pickScene('sd'); closePicker(); });
await page.waitForTimeout(350);

await t('структура рынка и вмешательство вложены в «Что изучаем»', () => page.evaluate(() => {
  const an = document.getElementById('sec-analysis');
  return (an.contains(document.getElementById('sec-tax')) &&
          an.contains(document.getElementById('sec-mono'))) || 'секции всё ещё отдельные';
}));

await t('заголовок верхнего уровня в панели один', () => page.evaluate(() => {
  const titles = [...document.querySelectorAll('#sec-analysis .section-title')].map(n => n.textContent);
  return (titles.length === 1 && titles[0] === 'Что изучаем') || titles.join('|');
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
await page.evaluate(() => { openPicker(); pickScene('tax'); closePicker(); });
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
  const draws = (tex.match(/\\draw\[/g) || []).length;
  return (draws >= 10 && tex.includes('\\begin{tikzpicture}')) || `\\draw: ${draws}`;
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
          && !tex.includes('fontspec') && !tex.includes('pgfplots')) || tex.slice(0, 300);
}));

// Экранная геометрия и есть источник .tex, поэтому масштаб проверяем прямым
// пересчётом: точка равновесия на холсте обязана попасть в ту же точку картинки.
await t('масштаб .tex совпадает с экранным', () => page.evaluate(() => {
  const svg = document.getElementById('chart');
  const c = svg.querySelector('circle');
  if (!c) return 'на сцене нет точек';
  const W = svg.clientWidth, H = svg.clientHeight, k = 16 / W;
  const wantX = (+c.getAttribute('cx') * k).toFixed(3);
  const wantY = ((H - +c.getAttribute('cy')) * k).toFixed(3);
  const tex = buildTex('', '');
  return tex.includes('(' + wantX + ',' + wantY + ') circle') || `ждали (${wantX},${wantY})`;
}));

await t('.tex обрезает кривые тем же прямоугольником, что экран', () => page.evaluate(() => {
  const tex = buildTex('', '');
  return (tex.includes('\\begin{scope}') && tex.includes('\\clip ')
          && (tex.match(/\\begin\{scope\}/g) || []).length === (tex.match(/\\end\{scope\}/g) || []).length)
         || 'обрезка не сошлась';
}));

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
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="tax"]');
  await page.waitForTimeout(300);
  return await page.evaluate(() => {
    const tex = buildTex('', '');
    return tex.includes('dash pattern=on') || 'нет пунктира';
  });
});

await t('свои точки попадают в .tex с подписью', () => page.evaluate(() => {
  addMarkAt(20, 80); STATE.marks[STATE.marks.length - 1].text = 'Ориентир'; redrawAll();
  const tex = buildTex('', '');
  STATE.marks = []; redrawAll();
  return tex.includes('Ориентир') || 'подписи нет';
}));

await t('в режиме издержек выгружаются кривые издержек', () => page.evaluate(() => {
  openPicker(); pickScene('costs'); closePicker(); redrawAll();
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
    await page.evaluate(() => openPicker());
    await page.click(`.scard[data-scene="${s}"]`);
    await page.waitForTimeout(260);
    const n = await page.evaluate(() => {
      const tex = buildTex('', '');
      return (tex.match(/\\draw|\\fill|\\node/g) || []).length;
    });
    if (n < 20) thin.push(`${s}:${n}`);
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

await page.evaluate(() => { openPicker(); pickScene('tax'); closePicker(); });
await page.waitForTimeout(400);

await t('лента-пульта укладывается в нижнее поле графика', () => page.evaluate(() => {
  const h = document.getElementById('pult').getBoundingClientRect().height;
  return h <= CONFIG.margin.bottom || `высота ленты ${Math.round(h)}px при поле ${CONFIG.margin.bottom}px`;
}));

await t('все регуляторы ленты одной ширины по базе', () => page.evaluate(() => {
  const els = [...document.querySelectorAll('#pult .pult-cchip, #pult .pult-xchip, #pult .field')];
  const bases = new Set(els.map(e => getComputedStyle(e).flexBasis));
  return (els.length > 0 && bases.size === 1) || `баз ${bases.size}: ${[...bases].join(',')}`;
}));

await t('в табло число крупнее подписи', () => page.evaluate(() => {
  const b = document.querySelector('#sb-body .stat b'), s = document.querySelector('#sb-body .stat span');
  if (!b || !s) return 'нет строк в табло';
  const bs = parseFloat(getComputedStyle(b).fontSize), ss = parseFloat(getComputedStyle(s).fontSize);
  return bs >= ss + 3 || `число ${bs}px, подпись ${ss}px`;
}));

await t('лента остаётся в поле и в сцене «Труд»', async () => {
  await page.evaluate(() => { openPicker(); pickScene('labor'); closePicker(); });
  await page.waitForTimeout(450);
  return await page.evaluate(() => {
    const h = document.getElementById('pult').getBoundingClientRect().height;
    return h <= CONFIG.margin.bottom || `высота ${Math.round(h)}px при поле ${CONFIG.margin.bottom}px`;
  });
});

// ── Фаза 9: тексты ──────────────────────────────────────────────────────
// Проверяем то, что реально видит человек: собранный DOM во всех сценах,
// а не исходник шаблона (в комментариях кода тире допустимы).
const SCENES = ['sd', 'tax', 'ceil', 'mono', 'elast', 'ext', 'smallopen', 'costs', 'ppf',
                'labor', 'ineq', 'consumer', 'adas', 'laffer', 'islm',
                'm-tangent', 'm-optimum', 'm-transform', 'm-inverse', 'm-minmax', 'm-constraint'];
const dashHits = [];
for (const sc of SCENES) {
  await page.evaluate((s) => { openPicker(); pickScene(s); closePicker(); }, sc);
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
await page.evaluate(() => openPicker());
await page.click('.scard[data-scene="m-optimum"]');
await page.waitForTimeout(420);

// У подписи висит дочерний <title> с всплывающей подсказкой, поэтому всюду
// ниже берём только собственные текстовые узлы, а не textContent.
await t('машина сама подписала максимум, минимум и перегиб', () => page.evaluate(() => {
  const own = (el) => Array.prototype.filter.call(el.childNodes, n => n.nodeType === 3)
    .map(n => n.nodeValue).join('');
  const names = [...document.querySelectorAll('#chart text')].map(own);
  const has = (re) => names.some(s => re.test(s));
  return (has(/^max /) && has(/^min /) && has(/^перегиб/)) || names.join(' | ');
}));

await t('щелчок по подписи открывает переименование', async () => {
  await page.locator('#chart text', { hasText: 'max' }).first().click();
  await page.waitForTimeout(220);
  const n = await page.locator('#pt-rename').count();
  const v = n ? await page.locator('#pt-rename').inputValue() : '';
  return (n === 1 && /^max /.test(v)) || `полей ${n}, значение «${v}»`;
});

await t('Enter сохраняет своё имя точки', async () => {
  await page.fill('#pt-rename', 'Точка выхода');
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
  await page.locator('#chart text', { hasText: 'перегиб' }).first().click();
  await page.waitForTimeout(200);
  await page.fill('#pt-rename', 'НЕ СОХРАНЯТЬ');
  await page.press('#pt-rename', 'Escape');
  await page.waitForTimeout(260);
  return await page.evaluate(() =>
    !Object.values(STATE.pointNames).includes('НЕ СОХРАНЯТЬ') || 'сохранилось вопреки Esc');
});

await t('смена сцены сбрасывает свои имена точек', async () => {
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="m-tangent"]');
  await page.waitForTimeout(330);
  return await page.evaluate(() =>
    Object.keys(STATE.pointNames).length === 0 || JSON.stringify(STATE.pointNames));
});

/* --- Роль кривой спрашивается до формулы -------------------------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.evaluate(() => openPicker());
await page.click('.scard[data-scene="free"]');
await page.waitForTimeout(320);

await t('справка подстраивается под выбранную роль', async () => {
  const want = { '': 'PQ', demand: 'DEMAND', supply: 'SUPPLY', mc: 'MC', tc: 'TC', atc: 'ATC' };
  const bad = [];
  for (const role of Object.keys(want)) {
    await page.selectOption('#new-role', role);
    await page.waitForTimeout(120);
    const k = await page.evaluate(() => curveHelpKind());
    if (k !== want[role]) bad.push(`${role || 'обычная'}: ${k}`);
  }
  return bad.length === 0 || bad.join(', ');
});

await t('для издержек форма «объём от цены» скрыта', async () => {
  await page.selectOption('#new-role', 'mc');
  await page.waitForTimeout(140);
  const hidden = await page.evaluate(() =>
    document.getElementById('curve-form-seg').style.display === 'none' && STATE.curveForm === 'PQ');
  await page.selectOption('#new-role', 'demand');
  await page.waitForTimeout(140);
  const shown = await page.evaluate(() =>
    document.getElementById('curve-form-seg').style.display !== 'none');
  return (hidden && shown) || `скрыт ${hidden}, показан ${shown}`;
});

await t('кривая добавляется сразу со своей ролью', async () => {
  await page.evaluate(() => { STATE.curves = []; renderCurveList(); redrawAll(); });
  await page.selectOption('#new-role', 'mc');
  await page.fill('#inp-formula', '20');
  await page.click('#btn-add-curve');
  await page.waitForTimeout(220);
  return await page.evaluate(() => {
    const c = STATE.curves[0];
    // Поле формулы очищается только при успешном добавлении.
    const cleared = document.getElementById('inp-formula').value === '';
    return (c && c.role === 'mc' && cleared) || JSON.stringify({ role: c && c.role, cleared });
  });
});

await t('заголовок справки называет именно эту роль', async () => {
  await page.click('#fh-formula');
  await page.waitForTimeout(220);
  const title = await page.locator('#fp-formula .f-pop-title').first().textContent();
  await page.click('#fh-formula');   // закрыть, чтобы не мешал дальше
  await page.waitForTimeout(120);
  return title.includes('Предельные издержки') || title;
});

/* --- Прилипание своих точек к кривым ----------------------------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.evaluate(() => openPicker());
await page.click('.scard[data-scene="sd"]');   // D = 100 − Q, S = Q, равновесие (50; 50)
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
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="tax"]');
  await page.waitForTimeout(350);
  const names = await page.evaluate(() =>
    [...document.querySelectorAll('#chart .legend text')].map(t => t.textContent));
  const want = ['Излишек покупателя (CS)', 'Излишек продавца (PS)', 'Сбор бюджета', 'Потери общества (DWL)'];
  return want.every(w => names.includes(w)) || names.join(' | ');
});

await t('субсидия подписана расходом, а не сбором', async () => {
  await page.evaluate(() => { setType('subsidy'); setTax(20); });
  await page.waitForTimeout(300);
  const names = await page.evaluate(() =>
    [...document.querySelectorAll('#chart .legend text')].map(t => t.textContent));
  const ok = names.includes('Расход бюджета') && !names.includes('Сбор бюджета');
  await page.evaluate(() => { setType('tax'); setTax(20); });
  await page.waitForTimeout(200);
  return ok || names.join(' | ');
});

await t('легенда собирается и в других режимах', async () => {
  const thin = [];
  for (const s of ['mono', 'labor', 'ppf', 'laffer', 'ext']) {
    await page.evaluate(() => openPicker());
    await page.click(`.scard[data-scene="${s}"]`);
    await page.waitForTimeout(300);
    const n = await page.evaluate(() => document.querySelectorAll('#chart .legend text').length);
    if (n < 1) thin.push(s);
  }
  return thin.length === 0 || 'без легенды: ' + thin.join(', ');
});

await t('легенда попадает в экспорт вместе с графиком', async () => {
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="tax"]');
  await page.waitForTimeout(330);
  return await page.evaluate(() => {
    const tex = buildTex('', '');
    return (tex.includes('Сбор бюджета') && tex.includes('Потери общества')) || 'подписей нет в .tex';
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
  return (+t0.getAttribute('y') < CONFIG.margin.top) || 'заехала в поле графика';
}));

/* --- Справка «?»: палитра операций и конструктор кусочной -------------- */
await page.evaluate(() => document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open')));
await page.evaluate(() => openPicker());
await page.click('.scard[data-scene="free"]');
await page.waitForTimeout(320);
await page.click('#fh-formula');
await page.waitForTimeout(220);

await t('в справке есть палитра операций', async () => {
  const groups = await page.locator('#fp-formula .f-pal-group').count();
  const btns = await page.locator('#fp-formula .f-pal').count();
  return (groups >= 5 && btns >= 25) || `групп ${groups}, кнопок ${btns}`;
});

await t('кусочки подставляются по курсору, а не затирают строку', async () => {
  await page.evaluate(() => {
    const i = document.getElementById('inp-formula');
    i.value = '100'; i.dispatchEvent(new Event('input', { bubbles: true }));
    i.setSelectionRange(3, 3);
  });
  const btns = await page.locator('#fp-formula .f-pal').all();
  for (const btn of btns) {
    if ((await btn.textContent()).trim() === 'sqrt( )') { await btn.click(); break; }
  }
  await page.waitForTimeout(150);
  const v = await page.inputValue('#inp-formula');
  const caret = await page.evaluate(() => document.getElementById('inp-formula').selectionStart);
  // Курсор должен встать ВНУТРИ скобок (между «(» и «)»), чтобы можно было
  // сразу писать дальше: у «100sqrt()» это позиция 8.
  return (v === '100sqrt()' && caret === 8) || `${v}, курсор ${caret}`;
});

await t('конструктор кусочной собирает верную запись', async () => {
  await page.locator('#fp-formula .f-pal.wide').click();
  await page.waitForTimeout(280);
  const segs = await page.locator('#pw-count .seg-btn').all();
  await segs[1].click();                     // три куска
  await page.waitForTimeout(180);
  const rows = await page.locator('#pw-rows .pw-row').all();
  if (rows.length !== 3) return 'строк ' + rows.length;
  await rows[1].locator('input[type=text]').first().fill('60');
  await rows[1].locator('input.pw-bound').fill('70');
  await rows[2].locator('input[type=text]').first().fill('20');
  await page.waitForTimeout(220);
  await page.click('#pw-apply');
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
await page.evaluate(() => openPicker());
await page.click('.scard[data-scene="sd"]');
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
  await page.dblclick('#graph-wrap', { position: { x: 700, y: 450 } });
  await page.waitForTimeout(280);
  return await page.evaluate(() => (CONFIG.Qmax === 100 && CONFIG.Pmax === 100 && !STATE.zoomLock) || CONFIG.Qmax);
});

await t('в математике окно тянется к курсору', async () => {
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="m-optimum"]');
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
  await page.evaluate(() => openPicker());
  await page.click('.scard[data-scene="adas"]');
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
await page.evaluate(() => openPicker());
await page.click('.scard[data-scene="sd"]');
await page.waitForTimeout(320);
await page.evaluate(() => setToolsOpen(true));
await page.waitForTimeout(180);

await t('у каждой кривой есть поле формулы', async () =>
  (await page.locator('.curve-expr-inp').count()) === 2 || 'полей: ' + (await page.locator('.curve-expr-inp').count()));

await t('правка формулы пересчитывает равновесие', async () => {
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

console.log('\n' + checks.map(([s, n, d]) => `${s.padEnd(4)} ${n}${d ? '  → ' + d : ''}`).join('\n'));
const bad = checks.filter(c => c[0] !== 'OK').length;
if (errors.length) console.log('\nОшибки страницы:\n' + errors.slice(0, 10).join('\n'));
console.log(`\nИтог: ${checks.length - bad}/${checks.length} прошло, ошибок страницы: ${errors.length}`);
await browser.close();
process.exit(bad || errors.length ? 1 : 0);
