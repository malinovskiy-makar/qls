// Матрица покрытия «общая фича × сцена». Только чтение: ничего не меняет,
// открывает каждую карточку окна сценариев и смотрит, какие общие механизмы
// в ней реально доступны.
//
//   ./venv/Scripts/python.exe manage.py runserver 8099 --noreload
//   node calc2/tests/audit_matrix.mjs > reports/calc2_matrix_before.md
import { chromium } from 'playwright';
import { readFileSync, readdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));

await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(1200);

const scenes = await page.$$eval('.scard:not(.soon)', els =>
  els.map(e => [e.dataset.scene, (e.querySelector('.scard-name') || e).textContent.trim()]));

const rows = [];
for (const [key, name] of scenes) {
  await page.evaluate(k => { pickScene(k); setToolsOpen(true); }, key);
  await page.waitForTimeout(340);
  const r = await page.evaluate(() => {
    const vis = el => !!(el && el.getClientRects().length);
    // Все видимые поля ввода формул: текстовые поля внутри видимых секций.
    // Формульным считаем поле, у которого есть подпись/подсказка про формулу
    // либо значение похоже на выражение.
    // Видимость считаем так же, как движок (fieldActive): сцена прячет секции
    // через display:none, а свёрнутая панель поля не отменяет.
    const allText = [...document.querySelectorAll('#tools-panel input[type=text]')];
    const formulaInputs = allText.filter(i => {
      if (i.classList.contains('pw-bound')) return false;   // границы куска, не формула
      if (!/^(inp-|ma-|cons-custom|ineq-formula|mm-|gr-)/.test(i.id)) return false;
      if (/name|title|label/.test(i.id)) return false;
      return typeof fieldActive === 'function' ? fieldActive(i) : vis(i);
    });
    const upgraded = formulaInputs.filter(i => !!i._mf);
    const kbd = formulaInputs.filter(i => {
      const w = i.closest('.f-wrap');
      return !!(w && w.querySelector('.f-kbd'));
    });
    const help = formulaInputs.filter(i => {
      const w = i.closest('.f-wrap');
      return !!(w && w.querySelector('.f-help'));
    });
    let crosses = 0;
    try { crosses = (typeof crossPoints === 'function') ? crossPoints().length : 0; } catch (e) {}
    let snaps = 0;
    try { snaps = (typeof snapTargets === 'function') ? snapTargets().length : 0; } catch (e) {}
    const drawnCrosses = document.querySelectorAll('.crosses circle').length;
    const pbody = document.getElementById('params-body') || document.getElementById('params-panel');
    const ranges = pbody ? [...pbody.querySelectorAll('input[type=range]')].filter(vis).length : 0;
    const bounds = pbody ? pbody.querySelectorAll('.param-bound').length : 0;
    return {
      fields: formulaInputs.length,
      mf: upgraded.length,
      kbd: kbd.length,
      help: help.length,
      params: (typeof paramsAllowed === 'function') ? paramsAllowed() : null,
      ranges, bounds,
      roller: snaps > 0,
      snaps,
      crosses, drawnCrosses,
      katex: document.querySelectorAll('#sb-body .katex').length,
      sbLen: (document.getElementById('sb-body') || {}).textContent?.trim().length || 0,
      foldPoints: !!document.querySelector('#sec-view .fold-btn'),
      hints: [...document.querySelectorAll('#tools-panel .hint')].filter(vis).length,
      mode: STATE.mode,
    };
  });
  /* Н7: буква-параметр обязана менять КАЖДУЮ формулу сцены. Подставляем в поле
     букву вместо числового коэффициента, отдаём полю те же события, что и
     живой ввод (сцены применяют формулу по change/Enter, а не по вводу), потом
     двигаем ползунок и смотрим, изменилась ли картинка. */
  r.par = await page.evaluate(() => {
    const commit = (f) => { ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
                            f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); };
    /* Отпечаток картинки. Берём геометрию кривых ЦЕЛИКОМ (обрезанный путь прячет
       расхождение в хвосте) и текст табло: у части сюжетов буква меняет числа
       разбора, а линии остаются на месте, потому что оси подстроились. */
    const shot = () => [...document.querySelectorAll('#chart path')].map(p => p.getAttribute('d') || '').join('|')
      + '#' + ((document.getElementById('sb-body') || {}).textContent || '').trim();
    const fields = (typeof FORMULA_FIELDS !== 'undefined' ? FORMULA_FIELDS : [])
      .filter(i => typeof fieldActive === 'function' && fieldActive(i) && (i.value || '').trim().length > 2);
    /* Буква для пробы — свободная: у сцены есть свои занятые обозначения
       (ставка t, зарплата w, а в «Оптимуме при ограничении» a и b это оси),
       и подставлять их нельзя, иначе проверка ругалась бы на замысел. */
    const busy = (typeof sceneReserved === 'function') ? sceneReserved() : new Set();
    const P = ['a', 'k', 'm', 'n', 'z'].find(n => !busy.has(n)) || 'z';
    const dead = [];
    let tested = 0;
    for (const f of fields) {
      const orig = f.value;
      /* Буква встаёт на место первого числового множителя, а ползунок ставим
         РЯДОМ с прежним числом. Ставить наугад единицу нельзя: у «20 − 0.1·Y»
         это даёт отвесную IS, пересечения с LM нет, и проверка ругалась бы на
         собственную подстановку, а не на калькулятор. */
      let num = null;
      // Буква ВМЕСТО множителя: её естественное значение — сам этот множитель.
      let mod = orig.replace(/(?<![\w.])(\d+(?:\.\d+)?)\s*\*/, (m0, d) => { num = +d; return P + '*'; });
      // Буква ПЕРЕД числом: она множитель, её естественное значение — единица.
      if (mod === orig) mod = orig.replace(/(?<![\w.^])(\d+(?:\.\d+)?)(?![\d.])/, (m0, d) => { num = 1; return P + '*' + d; });
      if (mod === orig || num === null) continue;
      const base = (isFinite(num) && num !== 0) ? num : 1;
      try {
        f.value = mod; commit(f); redrawAll();
        if (!STATE.params || !STATE.params[P]) { dead.push(f.id + ':нет-ползунка'); }
        else {
          tested++;
          const p = STATE.params[P];
          p.min = Math.min(p.min, base * 0.4); p.max = Math.max(p.max, base * 2);
          p.value = base; redrawAll(); const s1 = shot();
          p.value = base * 1.6; redrawAll(); const s2 = shot();
          if (s1 === s2) dead.push(f.id + ':не-влияет');
        }
      } catch (e) { dead.push(f.id + ':!' + String(e.message).slice(0, 20)); }
      f.value = orig; commit(f);
    }
    redrawAll();
    return { tested, dead };
  });

  // Сетка: считаем линии в трёх режимах переключателя. Раньше в «Математике»
  // и в панелях торговли сетки не было совсем, и это не ловилось ничем.
  r.grid = await page.evaluate(() => {
    const n = () => document.querySelectorAll('svg#chart g.grid line').length;
    const was = STATE.gridDense ? 'dense' : (STATE.showGrid ? 'plain' : 'off');
    setGridMode('dense'); const dense = n();
    setGridMode('plain'); const plain = n();
    setGridMode('off');   const off = n();
    setGridMode(was);
    return { dense, plain, off };
  });
  // ── Сквозные правила (П55): проверяем их на КАЖДОЙ сцене, а не выборочно.
  r.rules = await page.evaluate(async () => {
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const vis = el => !!(el && el.getClientRects().length);

    // П45: нигде на экране нет «k» вместо тысяч. Смотрим и подписи внутри
    // графика, и числа в панелях: сокращение вылезало и там, и там.
    const kRe = /(^|[\s(;=])\d+(?:[.,]\d+)?\s?[kKкК]\b/;
    let noK = true;
    const texts = [...document.querySelectorAll('svg#chart text')].map(t => t.textContent || '');
    document.querySelectorAll('#params-body .pchip-val, #sb-body b, .area-cell, .vert-row')
      .forEach(e => texts.push(e.textContent || ''));
    // Проверяем и сам форматтер: он общий на все числа калькулятора.
    if (typeof fmt === 'function' && (/[kK]/.test(fmt(5000)) || /[kK]/.test(fmt(12345)))) noK = false;
    if (texts.some(t => kRe.test(t))) noK = false;

    /* Б15: дробная часть в русском интерфейсе отделяется ЗАПЯТОЙ. Проверяем и
       сам форматчик (он общий на весь калькулятор), и напечатанное на экране:
       точка между цифрами в подписи графика или в табло — нарушение. */
    const dotRe = /(^|[\s(;=])\d+\.\d/;
    let commaOk = true;
    if (typeof fmt === 'function' && (/\d\.\d/.test(fmt(3.67)) || !/3,67/.test(fmt(3.67)))) commaOk = false;
    const dotHits = texts.filter(t => dotRe.test(t)).slice(0, 3);
    if (dotHits.length) commaOk = false;

    // П35, П48: полос прокрутки не видно ни в панелях, ни в гаечном ключе.
    // Смотрим фактическую ширину полосы, а не наличие overflow.
    const bars = [...document.querySelectorAll('.app *')].filter(el => {
      if (!vis(el)) return false;
      return (el.offsetWidth - el.clientWidth > 2 && el.scrollHeight > el.clientHeight)
          || (el.offsetHeight - el.clientHeight > 2 && el.scrollWidth > el.clientWidth);
    });

    // П34: у каждого места выбора цвета шесть образцов и кнопка «Свой цвет».
    // Считаем и в свёрнутых карточках: карточки закрыты по умолчанию, а голый
    // input[type=color] внутри закрытой карточки — такое же нарушение.
    const scope = '#tools-panel, #params-body, #wrench-pop';
    const picks = [...document.querySelectorAll(scope)]
      .reduce((n, box) => n + box.querySelectorAll('.cpick').length, 0);
    const rawColor = [...document.querySelectorAll(scope)]
      .reduce((n, box) => n + [...box.querySelectorAll('input[type=color]')]
        .filter(i => !i.closest('.cpick')).length, 0);

    // П16: числовое поле не листается колесом и стрелками.
    const nums = [...document.querySelectorAll('.app input[type=number]')].filter(vis);
    let wheelOk = true, keyOk = true;
    if (nums.length) {
      const el = nums[0], before = el.value;
      el.focus();
      el.dispatchEvent(new WheelEvent('wheel', { deltaY: -120, bubbles: true, cancelable: true }));
      if (el.value !== before) wheelOk = false;
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true }));
      if (el.value !== before) keyOk = false;
      el.blur();
    }

    /* Н75, Н60: короткое значение правится прямо в строке, прямоугольного поля
       ввода не видно ни в одном состоянии. Поля ФОРМУЛ не в счёт: они живут в
       .f-wrap и работают через MathLive. Раскрываем все складные блоки и меню
       плоскости, иначе половина полей просто не на экране. */
    document.querySelectorAll('#tools-panel .fold-btn').forEach(b => {
      if (b.getAttribute('aria-expanded') !== 'true') b.click();
    });
    const wr = document.getElementById('btn-wrench');
    if (wr && wr.getAttribute('aria-expanded') !== 'true') wr.click();
    const boxed = [];
    let fieldsSeen = 0;
    document.querySelectorAll('input[type=number], input[type=text]').forEach(i => {
      if (!vis(i) || i.closest('.f-wrap') || i.classList.contains('curve-expr-inp')) return;
      fieldsSeen++;
      const cs = getComputedStyle(i);
      const bg = cs.backgroundColor;
      if (cs.borderTopWidth !== '0px' || cs.borderLeftWidth !== '0px'
          || (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent')) {
        boxed.push(i.id || i.className || '(без имени)');
      }
    });
    if (wr && wr.getAttribute('aria-expanded') === 'true') wr.click();

    /* Н24: подпись оси не налезает ни на что. Сравниваем её прямоугольник со
       всеми прочими надписями холста и с легендой. Пустых подписей не бывает:
       у каждой сцены есть имя обеих осей (или сцена ставит своё). */
    const axisNames = [...document.querySelectorAll('#chart text.axis-name')];
    const otherTexts = [...document.querySelectorAll('#chart text')]
      .filter(t => !t.classList.contains('axis-name'));
    const legendEl = document.querySelector('#chart .legend');
    const rc = (e) => e.getBoundingClientRect();
    const hits = (a, b) => !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
    const axisClash = [];
    axisNames.forEach(an => {
      otherTexts.forEach(o => { if (hits(rc(an), rc(o))) axisClash.push(an.textContent + '/' + o.textContent.slice(0, 10)); });
      if (legendEl && hits(rc(an), rc(legendEl))) axisClash.push(an.textContent + '/легенда');
    });

    /* П31: точки липнут к кривым И к осям. Оси лежат не в snapTargets (там
       кривые вида y = f(x), по ним ищутся экстремумы), а считаются отдельно —
       проверяем, что прилипание к ним реально срабатывает у самой оси. */
    let snapAxes = false;
    try {
      const s = (typeof mainScales === 'function') ? mainScales() : null;
      if (s) snapAxes = !!axisSnapAt(s.mx(0) + 2, s.my(0) - 40);
    } catch (e) {}
    /* П53, П54: зум и панорама должны РАБОТАТЬ на каждом графике, а не просто
       существовать функциями. Меряем окно сцены до и после: колесо обязано
       менять размах, панорама — сдвигать окно, возврат масштаба — вернуть. */
    let zoomOk = false, panOk = false;
    try {
      // У сюжета про производную две независимые панели: и зум, и сдвиг ведут
      // ТУ, над которой курсор, а главные шкалы сцены при этом не двигаются.
      // Поэтому там меряем окно самой панели, а не mainScales.
      const panel = (STATE.mode === 'math' && STATE.mathSub === 'tangent') ? 'top' : null;
      const span = () => {
        if (panel) { const w = tanWin(panel); return [w.xmax - w.xmin, w.xmin]; }
        const s = mainScales();
        return [s.mx.domain()[1] - s.mx.domain()[0], s.mx.domain()[0]];
      };
      const gw = document.getElementById('graph-wrap');
      const r = gw.getBoundingClientRect();
      const py = panel ? (tangentLayout().top + 20) : r.height / 2;
      // Ждём между шагами: у части сцен переезд осей идёт с задержкой (дебаунс
      // и плавный твин), и мгновенный замер поймал бы состояние на полпути.
      const [w0] = span();
      zoomBy(0.8, r.width / 2, py); await wait(520);
      const [w1] = span();
      zoomOk = Math.abs(w1 - w0) > Math.abs(w0) * 1e-3;
      /* Панорама проверяется В ОБЕ стороны и на ПРИБЛИЖЁННОМ поле. Раньше тянули
         только влево на полном масштабе, и проверка молчала о том, что после
         зума окно стоит началом в нуле, а возврат в первую четверть гасит тягу
         вправо и вверх: две стороны из четырёх не работали вовсе. */
      resetZoom(); await wait(520);
      zoomBy(0.5, r.width / 2, py); await wait(520);
      const [, xA] = span();
      panByPixels(-60, 0, panel); await wait(320);
      const [, xB] = span();
      panByPixels(120, 0, panel); await wait(320);
      const [, xC] = span();
      panOk = Math.abs(xB - xA) > 1e-9 && Math.abs(xC - xB) > 1e-9;
      resetZoom(); await wait(120);
    } catch (e) {}

    return { noK, commaOk, dotHits, bars: bars.length, picks: picks.length, rawColor,
             wheelOk, keyOk, nums: nums.length, snapAxes, zoomOk, panOk,
             boxed, fieldsSeen, axisNames: axisNames.length, axisClash };
  });
  rows.push([key, name, r]);
}

const yn = v => v ? '+' : '–';
// Сетка считается рабочей, если подробная гуще простой, простая есть, а «нет» — это ноль линий.
const gridOk = r => r.grid.dense > r.grid.plain && r.grid.plain > 0 && r.grid.off === 0;
const frac = (a, b) => b === 0 ? '—' : (a === b ? '+ ' + a : a + '/' + b);
console.log('| Сцена | режим | LaTeX-ввод | клавиатура | «?» | параметры | ползунки: с границами / всего | прокатывание | ключевые точки | сетка: подробно/просто/нет | KaTeX в аналитике | абзацы-инструкции | свернуть точки |');
console.log('|---|---|---|---|---|---|---|---|---|---|---|---|---|');
for (const [key, name, r] of rows) {
  console.log(`| ${key} · ${name} | ${r.mode} | ${frac(r.mf, r.fields)} | ${frac(r.kbd, r.fields)} | ${frac(r.help, r.fields)} | ${yn(r.params)} | ${r.bounds} / ${r.ranges} | ${yn(r.roller)} | ${r.drawnCrosses}/${r.crosses} | ${r.grid.dense}/${r.grid.plain}/${r.grid.off}${gridOk(r) ? ' +' : ' !'} | ${r.katex} (текст ${r.sbLen}) | ${r.hints} | ${yn(r.foldPoints)} |`);
}
const badGrid = rows.filter(([, , r]) => !gridOk(r));
console.log('\nСцен со сломанной сеткой: ' + badGrid.length + (badGrid.length ? ' (' + badGrid.map(x => x[0]).join(', ') + ')' : ''));

// ── Таблица «сквозное правило × сцена» (П55) ──────────────────────────
console.log('\n## Сквозные правила по сценам\n');
console.log('| Сцена | П45 нет «k» | П35/П48 полос прокрутки | П34 выборов цвета (голых) | П16 колесо/стрелки | П31 оси как цель | П53/П54 зум и панорама |');
console.log('|---|---|---|---|---|---|---|');
const broken = { noK: [], comma: [], bars: [], color: [], num: [], snap: [], zoom: [], par: [], boxed: [] };
for (const [key, name, r] of rows) {
  if (r.par && r.par.dead.length) broken.par.push(key + ' (' + r.par.dead.join(', ') + ')');
  if (r.rules && r.rules.boxed && r.rules.boxed.length) broken.boxed.push(key + ' (' + r.rules.boxed.join(', ') + ')');
  const u = r.rules;
  if (!u.noK) broken.noK.push(key);
  if (!u.commaOk) broken.comma.push(key + (u.dotHits && u.dotHits.length ? ' (' + u.dotHits.join(' | ').slice(0, 40) + ')' : ''));
  if (u.bars > 0) broken.bars.push(key);
  if (u.rawColor > 0) broken.color.push(key);
  if (!u.wheelOk || !u.keyOk) broken.num.push(key);
  if (!u.snapAxes) broken.snap.push(key);
  if (!u.zoomOk || !u.panOk) broken.zoom.push(key);
  console.log(`| ${key} · ${name} | ${yn(u.noK)} | ${u.bars === 0 ? '+ нет' : '! ' + u.bars} | ${u.picks}${u.rawColor ? ' (! ' + u.rawColor + ')' : ''} | ${yn(u.wheelOk && u.keyOk)} (${u.nums}) | ${yn(u.snapAxes)} | ${yn(u.zoomOk && u.panOk)} |`);
}
const say = (t, arr) => console.log(`${t}: ${arr.length ? arr.length + ' (' + arr.slice(0, 8).join(', ') + ')' : 'нарушений нет'}`);
console.log('');
say('П45 «k» в числах', broken.noK);
say('Б15 точка вместо десятичной запятой', broken.comma);
say('П35/П48 видимая полоса прокрутки', broken.bars);
say('П34 голый выбор цвета', broken.color);
say('П16 числовое поле листается', broken.num);
say('П31 оси не цель прилипания', broken.snap);
say('П53/П54 зум или панорама недоступны', broken.zoom);
const axClash = [], noAxName = [];
let axTotal = 0;
for (const [key, , r] of rows) {
  const u = r.rules || {};
  axTotal += (u.axisNames || 0);
  if (!u.axisNames) noAxName.push(key);
  if (u.axisClash && u.axisClash.length) axClash.push(key + ' (' + u.axisClash.join(', ') + ')');
}
say('Н24 подпись оси налезает', axClash);
console.log('  (подписей осей всего: ' + axTotal + ', сцен без подписи: ' + noAxName.length + ')');
/* Н70: кнопка умной клавиатуры обязана быть у КАЖДОГО поля формулы в каждой
   сцене. Поля сюжета «Функции min и max» собирались вручную и получали только
   математический набор, без кнопки и без вопросика. */
const noKbd = [], noHelp = [];
let fFields = 0;
for (const [key, , r] of rows) {
  fFields += r.fields;
  if (r.kbd < r.fields) noKbd.push(key + ' (' + r.kbd + '/' + r.fields + ')');
  if (r.help < r.fields) noHelp.push(key + ' (' + r.help + '/' + r.fields + ')');
}
say('Н70 поле формулы без кнопки клавиатуры', noKbd);
say('Н70 поле формулы без вопросика', noHelp);
console.log('  (полей формул всего: ' + fFields + ')');
console.log('Н75 прямоугольное поле ввода: '
  + (broken.boxed.length ? broken.boxed.length + '\n  ' + broken.boxed.join('\n  ') : 'нарушений нет')
  + '\n  (проверено полей: '
  + rows.reduce((s2, [, , r]) => s2 + ((r.rules && r.rules.fieldsSeen) || 0), 0) + ')');
console.log('Н7 буква-параметр не влияет на формулу: '
  + (broken.par.length ? broken.par.length + '\n  ' + broken.par.join('\n  ') : 'нарушений нет')
  + '\n  (проверено полей: ' + rows.reduce((s, [, , r]) => s + (r.par ? r.par.tested : 0), 0) + ')');

/* ── Свх-4б: оборванные связи ────────────────────────────────────────────
   Класс дефекта, который не даёт ни ошибки, ни следа: контрол переделали,
   а обработчик остался висеть на элементе, которого в разметке уже нет, и
   кнопка молча ничего не делает. Проверка статическая: сверяем каждый
   getElementById и querySelector('#…') из скриптов с id в шаблоне и с теми,
   что скрипты создают сами. */
const HERE = dirname(fileURLToPath(import.meta.url));
const CALC2 = join(HERE, '..');
const tpl = readFileSync(join(CALC2, 'templates', 'calc2', 'calc2.html'), 'utf8');
const jsFiles = readdirSync(join(CALC2, 'static', 'calc2')).filter(f => f.endsWith('.js')).sort();
const jsAll = jsFiles.map(f => readFileSync(join(CALC2, 'static', 'calc2', f), 'utf8')).join('\n');

const known = new Set();
for (const m of tpl.matchAll(/\sid=["']([^"']+)["']/g)) known.add(m[1]);
// id, которые скрипты вешают сами: el.id = '…', .attr('id', '…'), разметка в
// шаблонных строках и суффикс-имена, собранные из idAttr.
for (const re of [/\.id\s*=\s*["'`]([A-Za-z][\w:.-]*)["'`]/g,
                  /\.attr\(\s*['"]id['"]\s*,\s*['"]([\w-]+)['"]/g,
                  /id=\\?["']([A-Za-z][\w-]*)/g]) {
  for (const m of jsAll.matchAll(re)) known.add(m[1]);
}
/* Часть id приезжает в помощник аргументом: addPultXChip(…, 'ineq-master-slider')
   ставит его ползунку, а подпись значения получает тот же id с суффиксом.
   Находим такие помощники по телу (в нём есть «.id = <имя параметра>»), затем
   собираем строки из их вызовов и все суффиксы, которые помощник приклеивает. */
const suffixes = [''];
for (const m of jsAll.matchAll(/\.id\s*=\s*(\w+)\s*\+\s*['"]([\w-]+)['"]/g)) suffixes.push(m[2]);
for (const fn of jsAll.matchAll(/function\s+(\w+)\s*\(([^)]*)\)\s*\{/g)) {
  const [name, params] = [fn[1], fn[2].split(',').map(s => s.trim())];
  const body = jsAll.slice(fn.index, fn.index + 2500);
  const idParam = params.find(p => new RegExp(`\\.id\\s*=\\s*${p}\\b`).test(body));
  if (!idParam) continue;
  for (const call of jsAll.matchAll(new RegExp(`\\b${name}\\s*\\(([^;]*?)\\)\\s*;`, 'g'))) {
    for (const s of call[1].matchAll(/['"]([\w-]+)['"]/g)) {
      suffixes.forEach(suf => known.add(s[1] + suf));
    }
  }
}
const orphans = [];
for (const f of jsFiles) {
  const src = readFileSync(join(CALC2, 'static', 'calc2', f), 'utf8').split('\n');
  src.forEach((line, i) => {
    /* Сверяем две формы записи: одиночную строку и тернарник. Раньше ловилась
       только первая, и getElementById(k === 1 ? 'inp-ppf1' : 'inp-ppf2')
       проезжал мимо — оба id были мёртвыми, а проверка молчала. Склейку
       ('mm-' + i) и вложенный вызов (getAttribute) не трогаем: там имя
       собирается на лету, сверять статически нечего. */
    for (const call of line.matchAll(/getElementById\(([^()]*)\)/g)) {
      const arg = call[1].trim();
      const one = arg.match(/^["']([\w:.-]+)["']$/);
      const tern = arg.match(/\?\s*["']([\w:.-]+)["']\s*:\s*["']([\w:.-]+)["']\s*$/);
      const ids = one ? [one[1]] : (tern ? [tern[1], tern[2]] : []);
      for (const id of ids) if (!known.has(id)) orphans.push(`${f}:${i + 1} ${id}`);
    }
    for (const m of line.matchAll(/querySelector(?:All)?\(\s*["']#([\w-]+)/g)) {
      if (!known.has(m[1])) orphans.push(`${f}:${i + 1} #${m[1]}`);
    }
  });
}
console.log('\n## Оборванные связи (Свх-4б)\n');
console.log('Свх-4б обработчик на несуществующем элементе: '
  + (orphans.length ? orphans.length + '\n  ' + orphans.join('\n  ') : 'нарушений нет'));

/* ── Долг-2: та же проверка со стороны РЕЕСТРОВ ─────────────────────────────
   Прошлый раз показал, что бывает и обратная потеря: div#info-math числился в
   RESULT_IDS, но в разметке его не было совсем, и весь блок «Математика»
   месяцами оставался без «Ключевых значений». Обработчика там нет, поэтому
   проверка «каждый getElementById указывает на живой элемент» такое не ловит.
   Здесь идём от списков: каждый id, перечисленный в реестре кода, обязан
   существовать в разметке (или создаваться скриптами). */
const REGISTRIES = [
  ['RESULT_IDS', /const RESULT_IDS = \[([\s\S]*?)\];/],
  ['SECTION_NAMES', /const SECTION_NAMES = \{([\s\S]*?)\n\};/],
  ['SECTION_ICONS', /const SECTION_ICONS = \{([\s\S]*?)\n\};/],
  ['FORMULA_FIELD_KINDS', /const FORMULA_FIELD_KINDS = \{([\s\S]*?)\n\};/],
  ['REGULATOR_SHORT', /const REGULATOR_SHORT = \{([\s\S]*?)\n\};/],
  ['PULT_MOVABLE', /const PULT_MOVABLE = \[([\s\S]*?)\];/],
  ['LABEL_SIZES', /const LABEL_SIZES = \[([\s\S]*?)\];/],
  ['SCENE_ROUTE.lock', /const SCENE_ROUTE = \{([\s\S]*?)\n\};/],
];
const regMissing = [];
let regChecked = 0, regIds = 0;
for (const [name, re] of REGISTRIES) {
  const m = jsAll.match(re);
  if (!m) { regMissing.push(name + ': реестр не найден в коде'); continue; }
  regChecked++;
  // Ключи-строки реестра. Для SCENE_ROUTE берём только содержимое lock: [...].
  const body = (name === 'SCENE_ROUTE.lock')
    ? (m[1].match(/lock:\s*\[([^\]]*)\]/g) || []).join(' ')
    : m[1];
  const ids = new Set();
  for (const s of body.matchAll(/['"]([a-z][\w-]*)['"]/gi)) ids.add(s[1]);
  for (const id of ids) {
    // В реестрах лежат и не-id (имена сцен, подписи) — сверяем только те, что
    // похожи на id разметки: с дефисом либо уже известные.
    if (!/-/.test(id)) continue;
    regIds++;
    if (!known.has(id)) regMissing.push(name + ': ' + id);
  }
}
console.log('\nДолг-2 реестр ссылается на несуществующий элемент: '
  + (regMissing.length ? regMissing.length + '\n  ' + regMissing.join('\n  ') : 'нарушений нет')
  + '\n  (реестров проверено: ' + regChecked + ', сверено id: ' + regIds + ')');

console.log('\nОшибок страницы: ' + errors.length);
errors.slice(0, 10).forEach(e => console.log('  ' + e));
await browser.close();
