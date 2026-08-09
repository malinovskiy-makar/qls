// Матрица покрытия «общая фича × сцена». Только чтение: ничего не меняет,
// открывает каждую карточку окна сценариев и смотрит, какие общие механизмы
// в ней реально доступны.
//
//   ./venv/Scripts/python.exe manage.py runserver 8099 --noreload
//   node calc2/tests/audit_matrix.mjs > reports/calc2_matrix_before.md
import { chromium } from 'playwright';

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
      if (!/^(inp-|ext-input|ma-|cons-custom|ineq-formula|mm-|gr-)/.test(i.id)) return false;
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
  r.rules = await page.evaluate(() => {
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

    // П31: точки липнут к кривым И к осям; П54: зум и панорама живут везде.
    let snapAxes = false;
    try { snapAxes = (typeof snapTargets === 'function') && snapTargets().some(t => t.kind === 'axis'); } catch (e) {}
    const zoomOk = typeof zoomBy === 'function' && typeof resetZoom === 'function';
    let panOk = false;
    try { panOk = typeof panByPixels === 'function'; } catch (e) {}

    return { noK, bars: bars.length, picks: picks.length, rawColor,
             wheelOk, keyOk, nums: nums.length, snapAxes, zoomOk, panOk };
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
const broken = { noK: [], bars: [], color: [], num: [], snap: [], zoom: [] };
for (const [key, name, r] of rows) {
  const u = r.rules;
  if (!u.noK) broken.noK.push(key);
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
say('П35/П48 видимая полоса прокрутки', broken.bars);
say('П34 голый выбор цвета', broken.color);
say('П16 числовое поле листается', broken.num);
say('П31 оси не цель прилипания', broken.snap);
say('П53/П54 зум или панорама недоступны', broken.zoom);

console.log('\nОшибок страницы: ' + errors.length);
errors.slice(0, 10).forEach(e => console.log('  ' + e));
await browser.close();
