/* БАЗОВЫЙ СНИМОК calc2: что есть в каждой модели и что делает каждый орган.

   Фаза 0 редизайна (claude/mockups/calc2_redesign_20261004/PROMPT.md).
   Для каждого из 44 ключей SCENE_ROUTE, каждый раз в НОВОМ контексте браузера
   с пустым хранилищем, прибор записывает:
     - перечень органов управления при раскрытом всём (ключ, вид, подпись,
       секция, границы и шаг, значение);
     - видимый ответ: строки табло (блок, номер, подпись, значение), заголовок
       группы, таблицы, пояснения, предупреждения, итоговую функцию, абзацы
       разбора, тексты подсказок;
     - слепок STATE (всё простое, кроме пикселей и следов мыши) и окна панелей;
     - геометрию холста в координатах модели по панелям;
     - то же после СЦЕНАРИЯ ПРАВОК: каждый орган приводится в другое значение,
       каждый шаг — от стартового состояния (свежая загрузка); то, что орган
       открыл (меню, окно, редактор), правится вторым уровнем;
     - жесты: каждая ручка холста тянется настоящей мышью, колесо, двойной щелчок;
     - печать в обеих темах (сначала beforeprint, потом emulateMedia);
     - снимки экрана в обеих темах (в reports/, не в git).

   Как найти орган и как прочитать ответ, знает СЛОЙ (layer_old.mjs для
   старого экрана, layer_new.mjs для нового); сценарий и запись общие.

   Запуск (сервер calc2 на CALC2_BASE_URL):
     node calc2/tests/redesign/snapshot.mjs --layer old --out calc2/tests/redesign/baseline \
       [--keys sd,taxes] [--jobs 4] [--shots reports/calc2_redesign/old] [--no-steps] [--no-gestures]
   Код возврата: 0 — снято, 1 — провал прибора (орган не найден, шаг без
   эффекта, старт дрейфует, ошибки страницы), 3 — calc2 не загрузился.       */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const flag = (k) => argv.includes('--' + k);
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const LAYER = arg('layer', 'old');
const OUT = arg('out', path.join(HERE, LAYER === 'old' ? 'baseline' : 'current'));
const SHOTS = arg('shots', '');
const JOBS = +arg('jobs', '4');
const W = +arg('width', '1324'), H = +arg('height', '638');
const layer = await import(path.join(HERE, 'layer_' + LAYER + '.mjs'));
const INPAGE = fs.readFileSync(path.join(HERE, 'inpage.js'), 'utf8');
/* Повтор: новый экран проходит РОВНО шаги базового снимка (а не открывает
   органы заново), иначе сравнивать было бы нечего. --replay <папка снимка>. */
const REPLAY = arg('replay', '');

/* ── Браузер и страница ─────────────────────────────────────────────── */
async function fresh(browser, theme) {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, reducedMotion: 'reduce', locale: 'ru-RU' });
  /* Хранилище пустое, кроме темы: тема — общий ключ сайта, без него страница
     берёт тему системы, и прогон зависел бы от машины. */
  await ctx.addInitScript((t) => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme || 'light');
  const page = await ctx.newPage();
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 300)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 300)); });
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 25000 });
  await page.addScriptTag({ content: INPAGE });
  await page.evaluate((l) => { window.__RD_LAYER = l; }, LAYER);
  /* Все объявленные шрифты — до первого слепка. Поля графика считаются по
     измеренной ширине подписей (fitMargins, 20-plane.js), а шрифты KaTeX
     грузятся лениво: первая показанная формула догружала шрифт, и следующая
     перерисовка сдвигала поля на доли пикселя. Без этого шаг «открыть
     подсказку» менял геометрию, а два прогона давали разные файлы. */
  await page.evaluate(async () => {
    const all = []; document.fonts.forEach(f => all.push(f.load().catch(() => null)));
    await Promise.all(all);
    await document.fonts.ready;
  });
  return { ctx, page, errors };
}

async function settle(page) {
  await page.evaluate(() => document.fonts.ready);
  const t0 = Date.now();
  while (Date.now() - t0 < 6000) {
    const ok = await page.evaluate(() => window.__RD.settled());
    if (ok) break;
    await page.waitForTimeout(60);
  }
  await page.waitForTimeout(330);   // дребезг формул 220 мс (82-input.js:1340) с запасом
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  const t1 = Date.now();
  while (Date.now() - t1 < 3000) {
    const ok = await page.evaluate(() => window.__RD.settled());
    if (ok) break;
    await page.waitForTimeout(60);
  }
}

async function openKey(browser, key, theme) {
  const f = await fresh(browser, theme);
  await layer.enter(f.page, key);
  await settle(f.page);
  await f.page.evaluate(() => redrawAll());   // перерисовка уже со всеми шрифтами
  await settle(f.page);
  await layer.expand(f.page);
  await settle(f.page);
  return f;
}

async function observe(page) {
  const [state, windows, geometry, controls, popups, chartSize] = await page.evaluate(() => [
    window.__RD.stateDump(), window.__RD.windows(), window.__RD.geometry(false), window.__RD.controls(), window.__RD.popups(),
    (() => { const c = document.getElementById('chart'); const r = c && c.getBoundingClientRect(); return r ? [Math.round(r.width), Math.round(r.height)] : null; })(),
  ]);
  const answer = await layer.answer(page);
  return { state, windows, geometry, controls, popups, answer, chartSize };
}

/* ── Сравнение слепков ─────────────────────────────────────────────── */
const J = (o) => JSON.stringify(o);
function stateDiff(a, b) {
  const out = {};
  const keys = new Set([...Object.keys(a || {}), ...Object.keys(b || {})]);
  keys.forEach(k => { if (J(a[k]) !== J(b[k])) out[k] = b[k] === undefined ? '∅' : b[k]; });
  return out;
}
function controlsDiff(a, b) {
  const ma = new Map(a.map(c => [c.key, c])), mb = new Map(b.map(c => [c.key, c]));
  const revealed = b.filter(c => !ma.has(c.key));
  const hidden = a.filter(c => !mb.has(c.key)).map(c => c.key);
  const props = {};
  b.forEach(c => { const o = ma.get(c.key); if (o && J(o.props) !== J(c.props)) props[c.key] = c.props; });
  return { revealed, hidden, props };
}

/* Ответ хранится по частям и только изменившиеся: подсказки (tips) одинаковы
   почти у всех шагов и весят больше всего остального. */
function answerDiff(a, b) {
  const out = {};
  ['title', 'explain'].forEach(k => { if (J(a[k]) !== J(b[k])) out[k] = b[k]; });
  // Блоки: только изменившиеся (по id), исчезнувшие — списком id.
  const ma = new Map((a.blocks || []).map(x => [x.id, x])), mb = new Map((b.blocks || []).map(x => [x.id, x]));
  const ch = (b.blocks || []).filter(x => J(ma.get(x.id)) !== J(x));
  const gone = (a.blocks || []).filter(x => !mb.has(x.id)).map(x => x.id);
  if (ch.length) out.blocks = ch;
  if (gone.length) out.blocksGone = gone;
  if (J((a.blocks || []).map(x => x.id)) !== J((b.blocks || []).map(x => x.id))) out.order = (b.blocks || []).map(x => x.id);
  // Подсказки: что добавилось и что пропало.
  const ta = new Set(a.tips || []), tb = new Set(b.tips || []);
  const add = [...tb].filter(x => !ta.has(x)), del = [...ta].filter(x => !tb.has(x));
  if (add.length || del.length) out.tips = { add, del };
  return Object.keys(out).length ? out : null;
}
/* Геометрия шага — разность со стартовой: номера удалённых элементов
   стартовых списков (списки отсортированы) и добавленные элементы. */
function geomDiff(a, b) {
  const out = {};
  ['paths', 'lines', 'rects', 'dots'].forEach(k => {
    const sa = (a[k] || []).map(J), sb = new Set((b[k] || []).map(J));
    const del = []; sa.forEach((x, i) => { if (!sb.has(x)) del.push(i); });
    const sa2 = new Set(sa);
    const add = (b[k] || []).filter(x => !sa2.has(J(x)));
    if (del.length || add.length) out[k] = { del, add };
  });
  if (J(a.keyPoints) !== J(b.keyPoints)) out.keyPoints = b.keyPoints;
  return Object.keys(out).length ? out : null;
}

/* Органы, у которых шаг законно не меняет ничего наблюдаемого. Каждая
   строка с причиной; всё прочее без эффекта — провал прибора. */
const NO_EFFECT = [
  [/^#(sb-btn|ex-btn)$|fold-btn/, 'сворачивание карточки: прибор раскрыл всё заранее, закрытая карточка в перечне органов остаётся (пункт (д) закрытого списка)'],
];
function noEffectReason(c, start) {
  for (const [re, why] of NO_EFFECT) if (re.test(c.key)) return why;
  if (c.key === '#ac-clear' && start && !(start.state.areaCalcList || []).length && !(start.state.areaVerts || []).length)
    return 'посчитанных площадей и вершин в стартовом состоянии нет: «Убрать всё» нечего убирать';
  // «Построить» без правки поля применяет ту же запись; действие этих кнопок
  // проверяется шагами набора в их поля (layer.afterFormula нажимает их там).
  if (/^#(btn-[a-z0-9]+-apply|ineq-(incomes|formula)-apply)$/.test(c.key))
    return 'кнопка «Построить» без правки поля: запись та же (пункт (а) закрытого списка)';
  if (/preset/.test(c.key)) return 'образец уже стоит в стартовом состоянии';
  // Вкладка или вариант, который уже выбран: щелчок по нему ничего не меняет.
  if (c.props && (c.props.active || c.props.pressed === 'true')) return 'уже выбранный вариант';
  return null;
}

/* ── Действия над органом ───────────────────────────────────────────── */
// Новое значение числа: внутри границ, с дробной частью там, где шаг дробный.
function pickTarget(cur, min, max, step) {
  cur = +cur; min = (min === '' || min == null) ? NaN : +min; max = (max === '' || max == null) ? NaN : +max;
  const st = (step === 'any' || step === '' || step == null) ? 0.5 : +step;
  const span = (isFinite(min) && isFinite(max)) ? (max - min) : Math.max(10, Math.abs(cur) || 10);
  let t = cur + Math.max(st, span * 0.13);
  if (isFinite(max) && t > max) t = cur - Math.max(st, span * 0.13);
  if (isFinite(min) && t < min) t = (min + (isFinite(max) ? max : min + span)) / 2;
  // Дробный шаг — значение с половинкой, набирается «…,5» с запятой (О31).
  if (st < 1) { t = Math.floor(t) + 0.5; if (isFinite(max) && t > max) t -= 1; if (isFinite(min) && t < min) t += 1; }
  else t = Math.round(t / st) * st;
  if (t === cur) t = cur + (st || 1);
  return t;
}
const comma = (v) => String(+(+v).toFixed(6)).replace('.', ',');

function mutateFormula(val, key, sceneKey) {
  const v = String(val || '').trim();
  if (!v) return /^m-/.test(sceneKey) ? '2x+1' : '40-Q';
  return null;   // непустое поле: дописываем «+5» в конец (см. act)
}

async function handleOf(page, key) {
  const h = await page.evaluateHandle((k) => window.__RD.findControl(k), key);
  const el = h.asElement();
  return el;
}

/* Прокрутка до органа — ДО щелчка и с паузой: выпадающий список calc2
   закрывается на любое событие scroll (82-input.js:1909), а Playwright
   прокручивает прямо перед нажатием, и событие приходит уже после открытия. */
async function clickHandle(page, el) {
  try { await el.scrollIntoViewIfNeeded({ timeout: 1500 }); } catch (e) {}
  await page.waitForTimeout(120);
  try { await el.click({ timeout: 2500 }); return 'click'; } catch (e) {
    await el.evaluate(x => x.click());
    return 'click(js)';
  }
}

/* Привести орган в другое значение так, как это сделал бы человек.
   Возвращает описание действия или бросает исключение «не найден». */
async function act(page, c, sceneKey) {
  // Слой нового экрана сам выполняет действие над органом, заменённым по
  // закрытому списку (например, «Построить» → набор уже применён).
  if (layer.actOverride) { const r = await layer.actOverride(page, c, sceneKey); if (r != null) return r; }
  const el = await handleOf(page, layer.mapKey(c.key));
  if (!el) throw new Error('орган не найден: ' + c.key);
  const k = c.kind;
  if (k === 'input:range') {
    await el.focus();
    const atMax = await el.evaluate(x => +x.value >= +x.max);
    const key = atMax ? 'ArrowLeft' : 'ArrowRight';
    for (let i = 0; i < 3; i++) await page.keyboard.press(key);
    return key + '×3';
  }
  if (k === 'input:number') {
    const p = c.props;
    const t = pickTarget(p.value, p.min, p.max, p.step);
    await el.click({ clickCount: 3 }).catch(() => el.focus());
    await page.keyboard.press('Meta+A');
    await page.keyboard.type(comma(t), { delay: 20 });
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    return 'набор ' + comma(t);
  }
  if (k === 'input:color') {
    // Системное окно выбора цвета не нажать: значение ставится так же, как
    // его ставит само окно, — событиями input и change.
    await el.fill('#2a7f62');
    return 'цвет #2a7f62';
  }
  if (k === 'edval') {
    // Правка на месте (makeEditableValue): щелчок открывает поле, Enter применяет.
    const was = await el.evaluate(x => x.textContent);
    await clickHandle(page, el);
    await page.waitForTimeout(100);
    const num = /^[\s\d,.\u2212-]+$/.test(was) && was.trim();
    const t = num ? comma(Math.floor(parseFloat(was.replace(/\u2212/g, '-').replace(',', '.')) * 1.5) + 0.5) : 'Ж';
    await page.keyboard.press('Meta+A');
    await page.keyboard.type(t, { delay: 20 });
    await page.keyboard.press('Enter');
    return 'правка «' + t + '»';
  }
  if (k === 'input:checkbox' || k === 'input:radio' || k === 'switch') {
    return clickHandle(page, el);
  }
  if (k === 'input:text' || k === 'textarea') {
    const v = c.props.value || '';
    const isList = /^[\d.\s,;-]+$/.test(v) && /[,;]/.test(v);
    const add = isList ? ', 55' : (/^[\d\s.+*/()-]*$/.test(v) && v ? '+5' : 'Ж');
    await el.click();
    await page.keyboard.press('End');
    await page.keyboard.type(add, { delay: 20 });
    const applied = await layer.afterFormula(page, c.key);
    return 'дописано «' + add + '»' + (applied ? ' + ' + applied : '');
  }
  if (k === 'math-field') {
    const empty = mutateFormula(c.props.value, c.key, sceneKey);
    /* Фокус, пауза, курсор в конец, набор (приём night2_phase0_probe.mjs:27-36):
       первый фокус поля выделяет всё через setTimeout 0 (82-input.js:1176), и
       набранный сразу знак уходил в выделение — «+» терялся, получалось «Q5». */
    const before = await el.evaluate(mf => mf.value);
    await el.evaluate(mf => { mf.focus(); });
    await page.waitForTimeout(150);
    await el.evaluate(mf => { mf.executeCommand('moveToMathfieldEnd'); });
    await page.waitForTimeout(50);
    const add = empty || '+5';
    await page.keyboard.type(add, { delay: 30 });
    const after = await el.evaluate(mf => mf.value);
    // MathLive переписывает запись по-своему («^{3}» → «^3»), поэтому сверяем
    // только то, что набранное встало в конец.
    if (!empty && !after.replace(/\s/g, '').endsWith('+5')) {
      throw new Error('набор в поле формулы не удался: «' + before + '» → «' + after + '»');
    }
    await page.waitForTimeout(350);
    const applied = await layer.afterFormula(page, c.key);
    return (empty ? 'набор «' + empty + '»' : 'дописано «+5»') + (applied ? ' + ' + applied : '');
  }
  if (k === 'select') {
    const opts = c.props.options || [];
    const vals = opts.map(o => o.split('=')[0]);
    const i = vals.indexOf(c.props.value);
    const next = vals[(i + 1) % vals.length];
    await el.selectOption(next);
    return 'выбор ' + next;
  }
  if (k === 'exact') {
    await clickHandle(page, el);
    await page.waitForTimeout(80);
    const info = await page.evaluate(() => {
      const a = document.activeElement;
      if (!a || a.tagName !== 'INPUT') return null;
      const f = a.closest('.field, .pchip, [id]');
      const sl = f && f.querySelector('input[type=range]');
      return { v: a.value, min: sl ? sl.min : '', max: sl ? sl.max : '', step: sl ? sl.step : '' };
    });
    if (!info) throw new Error('точный ввод не открылся: ' + c.key);
    const t = pickTarget(info.v, info.min, info.max, info.step);
    await page.keyboard.type(comma(t), { delay: 20 });
    await page.keyboard.press('Enter');
    return 'точное ' + comma(t);
  }
  if (k === 'bounds') {
    // Число границы написано на самой кнопке («−50», «50»); редактор открывает
    // пустое поле contenteditable (88-params.js:404-420).
    const cur = await el.evaluate(x => parseFloat(x.textContent.replace(/\u2212/g, '-').replace(/\s/g, '').replace(',', '.')));
    await clickHandle(page, el);
    await page.waitForTimeout(120);
    const ok = await page.evaluate(() => { const a = document.activeElement; return !!a && (a.tagName === 'INPUT' || a.isContentEditable); });
    if (!ok) throw new Error('редактор границ не открылся: ' + c.key);
    const t = isFinite(cur) ? (cur === 0 ? 5.5 : Math.floor(cur * 1.5) + 0.5) : 5.5;
    await page.keyboard.press('Meta+A');
    await page.keyboard.type(comma(t), { delay: 20 });
    await page.keyboard.press('Enter');
    return 'граница ' + comma(t);
  }
  // Кнопка «?»: подсказка открывается наведением (86-workspace.js:1464-1510);
  // щелчок по уже открытой наведением подсказке её закрывает.
  if (/hint-btn/.test(c.key)) { await el.hover(); await page.waitForTimeout(250); return 'наведение'; }
  // Кнопки, переключатели, образцы цвета, всё прочее — щелчок.
  return clickHandle(page, el);
}

/* Органы, которые прибор правит. Клавиши клавиатуры формул — одна семья:
   правятся первые три, остальные только описываются в перечне. */
function steppable(c, all) {
  if (c.props && c.props.disabled) return false;
  // Карточки окна выбора меняют модель целиком: их паритет — пункт (г)
  // закрытого списка и обход всех 44 ключей, а не шаг внутри модели.
  if (c.picker) return false;
  return true;
}
function kbdFamily(list) {
  const out = []; let n = 0;
  list.forEach(c => {
    if (/mkbd|kbd|>button\.mk(\[|$|~)/.test(c.key)) { if (n++ < 3) out.push(c); }
    else out.push(c);
  });
  return out;
}

/* ── Один ключ модели целиком ───────────────────────────────────────── */
async function snapKey(browser, key) {
  const rec = { key, layer: LAYER, base: BASE, size: [W, H], errors: [], failures: [], inventory: {} };
  // Старт.
  let f = await openKey(browser, key, 'light');
  const start = await observe(f.page);
  rec.chartSize = start.chartSize;
  rec.start = { state: start.state, windows: start.windows, answer: start.answer, geometry: start.geometry, popups: start.popups };
  rec.controls = start.controls;
  rec.handles = await f.page.evaluate(() => window.__RD.handles());
  rec.errors.push(...f.errors.map(e => 'старт: ' + e));
  if (SHOTS) {
    fs.mkdirSync(SHOTS, { recursive: true });
    await f.page.screenshot({ path: path.join(SHOTS, key + '-light.png') });
  }
  await f.ctx.close();
  if (SHOTS) {
    const d = await openKey(browser, key, 'dark');
    await d.page.screenshot({ path: path.join(SHOTS, key + '-dark.png') });
    await d.ctx.close();
  }

  // Сценарий правок.
  rec.steps = [];
  if (REPLAY && !flag('no-steps')) {
    const bl = JSON.parse(fs.readFileSync(path.join(REPLAY, key + '.json'), 'utf8'));
    const desc = (k) => (bl.controls || []).find(c => c.key === k) || (bl.inventory && bl.inventory[k] ? { key: k, ...bl.inventory[k] } : null);
    for (const st of bl.steps || []) {
      const pathCtl = st.path.map(desc);
      if (pathCtl.some(x => !x)) { rec.failures.push(key + ' · ' + st.path.join(' → ') + ': нет описания органа в снимке'); continue; }
      await runStep(browser, key, start, pathCtl, rec, 9);
    }
  } else if (!flag('no-steps')) {
    const list = kbdFamily(start.controls.filter(c => steppable(c, start.controls)));
    for (const c of list) {
      await runStep(browser, key, start, [c], rec);
    }
  }

  // Жесты.
  rec.gestures = [];
  if (!flag('no-gestures')) {
    for (const hd of rec.handles) rec.gestures.push(await gesture(browser, key, start, { kind: 'drag', handle: hd }));
    rec.gestures.push(await gesture(browser, key, start, { kind: 'wheel' }));
    rec.gestures.push(await gesture(browser, key, start, { kind: 'dblclick' }));
  }

  // Печать.
  rec.print = {};
  for (const theme of ['light', 'dark']) rec.print[theme] = await printView(browser, key, theme);
  return rec;
}

async function runStep(browser, key, start, pathCtl, rec, depth = 1, parent = null) {
  const f = await openKey(browser, key, 'light');
  const step = { path: pathCtl.map(c => c.key), kind: pathCtl[pathCtl.length - 1].kind };
  try {
    const pre = await f.page.evaluate(() => window.__RD.stateDump());
    if (J(pre) !== J(start.state)) {
      step.startDrift = Object.keys(stateDiff(start.state, pre));
      rec.failures.push(key + ' · ' + step.path.join(' → ') + ': старт перед шагом не равен стартовому (' + step.startDrift.join(', ') + ')');
    }
    const acts = [];
    for (let i = 0; i < pathCtl.length; i++) {
      acts.push(await act(f.page, pathCtl[i], key));
      await settle(f.page);
    }
    step.action = acts.join(' ; ');
    const o = await observe(f.page);
    const sd = stateDiff(start.state, o.state);
    const wd = J(start.windows) !== J(o.windows);
    const ad = answerDiff(start.answer, o.answer);
    const gd = geomDiff(start.geometry, o.geometry);
    const cd = controlsDiff(start.controls, o.controls);
    const pd = J(start.popups) !== J(o.popups);
    step.state = sd;
    if (wd) step.windows = o.windows;
    if (ad) step.answer = ad;
    if (gd) step.geometry = gd;
    if (pd) step.popups = o.popups;
    // Открывшиеся органы: в шаге только ключи, описание — один раз в rec.inventory.
    cd.revealed.forEach(c => { if (!rec.inventory[c.key]) rec.inventory[c.key] = { kind: c.kind, label: c.label, section: c.section, props: c.props, via: step.path.join(' → ') }; });
    if (cd.revealed.length) step.revealed = cd.revealed.map(c => c.key);
    if (cd.hidden.length) step.hidden = cd.hidden;
    if (Object.keys(cd.props).length) step.props = cd.props;
    // Подсказки (tips) меняются вместе с набором видимых органов: это вид, а не модель.
    const am = ad && Object.keys(ad).some(k => k !== 'tips');
    step.effect = (Object.keys(sd).length || wd || am || gd) ? 'model'
      : (Object.keys(cd.props).length ? 'props' : (cd.revealed.length || cd.hidden.length || pd || ad ? 'ui' : 'none'));
    // Второй уровень сравнивается с состоянием после открывшего шага: «Закрыть»
    // возвращает к старту, и это и есть её действие.
    if (parent) {
      const pdiff = stateDiff(parent.state, o.state), pc = controlsDiff(parent.controls, o.controls);
      const pa = answerDiff(parent.answer, o.answer), pg = geomDiff(parent.geometry, o.geometry);
      const pp = J(parent.popups) !== J(o.popups), pw = J(parent.windows) !== J(o.windows);
      step.effectVsOpener = (Object.keys(pdiff).length || pw || pg || (pa && Object.keys(pa).some(k => k !== 'tips'))) ? 'model'
        : (Object.keys(pc.props).length ? 'props' : (pc.revealed.length || pc.hidden.length || pp || pa ? 'ui' : 'none'));
    }
    if ((parent ? step.effectVsOpener : step.effect) === 'none') {
      const why = noEffectReason(pathCtl[pathCtl.length - 1], start);
      if (why) step.noEffect = why;
      else rec.failures.push(key + ' · ' + step.path.join(' → ') + ': шаг без наблюдаемого эффекта (' + step.action + ')');
    }
    if (f.errors.length) { step.errors = f.errors.slice(); rec.errors.push(...f.errors.map(e => step.path.join(' → ') + ': ' + e)); }
    rec.steps.push(step);
    await f.ctx.close();
    // Второй уровень: орган открыл меню, окно или редактор — правим то, что открылось.
    /* Третий уровень — только внутрь окна (.modal): конструктор кусочной
       функции открывается из меню поля («?» → «Собрать кусочную функцию»). */
    const subOk = (c) => depth === 1 || (depth === 2 && /^#(pw|export|ff)-|modal/.test(c.section || ''));
    if (depth <= 2 && cd.revealed.length && step.effect !== 'model') {
      const fresh_ = parent ? controlsDiff(parent.controls, o.controls).revealed : cd.revealed;
      const subs = kbdFamily(fresh_.filter(c => steppable(c, fresh_) && subOk(c)));
      for (const s of subs) await runStep(browser, key, start, [...pathCtl, s], rec, depth + 1, o);
    }
  } catch (e) {
    step.error = String(e.message || e).slice(0, 300);
    rec.failures.push(key + ' · ' + step.path.join(' → ') + ': ' + step.error);
    rec.steps.push(step);
    await f.ctx.close();
  }
}

async function gesture(browser, key, start, g) {
  const f = await openKey(browser, key, 'light');
  const out = { kind: g.kind };
  try {
    const box = await f.page.evaluate(() => { const r = document.getElementById('chart').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
    const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
    if (g.kind === 'drag') {
      out.handle = g.handle.key;
      const hs = await f.page.evaluate(() => window.__RD.handles());
      const h = hs.find(x => x.key === g.handle.key);
      if (!h) throw new Error('ручка не найдена: ' + g.handle.key);
      out.from = [h.x - box.x, h.y - box.y];
      out.by = [24, -24];
      await f.page.mouse.move(h.x, h.y);
      await f.page.mouse.down();
      for (let i = 1; i <= 6; i++) await f.page.mouse.move(h.x + 4 * i, h.y - 4 * i);
      await f.page.mouse.up();
    } else if (g.kind === 'wheel') {
      await f.page.mouse.move(cx, cy);
      await f.page.mouse.wheel(0, -240);
    } else if (g.kind === 'dblclick') {
      // Двойной щелчок возвращает исходный масштаб: сначала колесо, потом он.
      await f.page.mouse.move(cx, cy);
      await f.page.mouse.wheel(0, -240);
      await settle(f.page);
      out.zoomed = await f.page.evaluate(() => window.__RD.windows());
      await f.page.mouse.dblclick(box.x + box.w * 0.85, box.y + box.h * 0.15);   // пустой угол: в центре бывает точка
    }
    await settle(f.page);
    const o = await observe(f.page);
    out.state = stateDiff(start.state, o.state);
    if (J(start.windows) !== J(o.windows)) out.windows = o.windows;
    const ad = answerDiff(start.answer, o.answer);
    if (ad) out.answer = ad;
    out.effect = (Object.keys(out.state).length || out.windows || out.answer) ? 'model' : 'none';
    if (g.kind === 'dblclick') out.effect = J(out.zoomed) !== J(start.windows) && !out.windows ? 'reset' : 'нет сброса';
  } catch (e) { out.error = String(e.message || e).slice(0, 300); }
  await f.ctx.close();
  return out;
}

/* Печать: сначала событие beforeprint (оно кладёт название, строки чисел и
   светлую тему, 86-workspace.js:1794), потом эмуляция печатной среды. */
async function printView(browser, key, theme) {
  const f = await openKey(browser, key, theme);
  await f.page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  await f.page.emulateMedia({ media: 'print' });
  await f.page.waitForTimeout(250);
  const r = await f.page.evaluate(() => {
    const c = document.getElementById('chart');
    const cr = c ? c.getBoundingClientRect() : null;
    const txt = (document.body.innerText || '').split('\n').map(s => s.replace(/\s+/g, ' ').trim()).filter(Boolean);
    return { chart: cr ? [Math.round(cr.width), Math.round(cr.height), getComputedStyle(c).display !== 'none'] : null,
             lines: txt, bg: getComputedStyle(document.body).backgroundColor };
  });
  await f.page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await f.ctx.close();
  return r;
}

/* Запись: верхний уровень и каждый шаг — своей строкой, внутри без отступов.
   Так файл и читается в diff, и весит в разы меньше записи с отступами. */
function dump(rec) {
  const lines = ['{'];
  const ks = Object.keys(rec);
  ks.forEach((k, i) => {
    const v = rec[k];
    const tail = i < ks.length - 1 ? ',' : '';
    if (Array.isArray(v) && v.length && typeof v[0] === 'object') {
      lines.push(JSON.stringify(k) + ': [');
      v.forEach((x, j) => lines.push(' ' + JSON.stringify(x) + (j < v.length - 1 ? ',' : '')));
      lines.push(']' + tail);
    } else if (k === 'inventory' || k === 'start') {
      lines.push(JSON.stringify(k) + ': {');
      const kk = Object.keys(v);
      kk.forEach((x, j) => lines.push(' ' + JSON.stringify(x) + ': ' + JSON.stringify(v[x]) + (j < kk.length - 1 ? ',' : '')));
      lines.push('}' + tail);
    } else lines.push(JSON.stringify(k) + ': ' + JSON.stringify(v) + tail);
  });
  lines.push('}');
  return lines.join('\n') + '\n';
}

/* ── Обход ключей ───────────────────────────────────────────────────── */
const browser = await chromium.launch();
let keys = (arg('keys', '') || '').split(',').filter(Boolean);
if (!keys.length) {
  const f = await fresh(browser, 'light').catch(e => { console.error('calc2 не загрузился:', e.message); process.exit(3); });
  keys = await f.page.evaluate(() => Object.keys(SCENE_ROUTE));
  await f.ctx.close();
}
fs.mkdirSync(OUT, { recursive: true });
const queue = keys.slice();
const failures = [];
const t0 = Date.now();
async function worker() {
  while (queue.length) {
    const key = queue.shift();
    const t = Date.now();
    let rec;
    try { rec = await snapKey(browser, key); } catch (e) {
      rec = { key, fatal: String(e.stack || e).slice(0, 800), failures: [key + ': ' + String(e.message || e)] };
    }
    fs.writeFileSync(path.join(OUT, key + '.json'), dump(rec));
    failures.push(...(rec.failures || []));
    if (rec.errors && rec.errors.length) failures.push(...rec.errors.map(e => key + ' · ошибка страницы: ' + e));
    console.log(`${key}: органов ${rec.controls ? rec.controls.length : '?'}, шагов ${rec.steps ? rec.steps.length : '?'}, `
      + `жестов ${rec.gestures ? rec.gestures.length : '?'}, провалов ${(rec.failures || []).length}, ${((Date.now() - t) / 1000).toFixed(0)} с`);
  }
}
await Promise.all(Array.from({ length: Math.min(JOBS, keys.length) }, worker));
await browser.close();
console.log(`\nключей ${keys.length}, ${((Date.now() - t0) / 1000).toFixed(0)} с, провалов ${failures.length}`);
failures.slice(0, 200).forEach(f => console.log('  ПРОВАЛ ' + f));
process.exit(failures.length ? 1 : 0);
