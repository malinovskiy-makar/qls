/* Общая часть приборов редизайна calc2: страница, ожидание, наблюдение,
   сравнение слепков и действия над органами. Слой экрана (layer_old /
   layer_new) и адрес сервера задаёт configure(). Используют snapshot.mjs и
   state_probe.mjs. */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const INPAGE = fs.readFileSync(path.join(HERE, 'inpage.js'), 'utf8');
let layer = null, BASE = '', LAYER = 'old', W = 1324, H = 638;
/* Размер окна, при котором холст 732×590 (CODE_NOTES 12): старый экран —
   1324×638, новый — 1440×760 (инвариант раскладки). На равном холсте
   геометрия сверяется строго, с допуском 0,002 px. */
export const viewportFor = (layerName) => layerName === 'new' ? [1440, 760] : [1324, 638];
export function configure(o) {
  layer = o.layer; BASE = o.base; LAYER = o.layerName;
  const [w, h] = viewportFor(o.layerName);
  W = o.w || w; H = o.h || h;
}
export const viewport = () => ({ width: W, height: H });

/* ── Браузер и страница ─────────────────────────────────────────────── */
export async function fresh(browser, theme) {
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

export async function settle(page) {
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

export async function openKey(browser, key, theme) {
  const f = await fresh(browser, theme);
  await layer.enter(f.page, key);
  await settle(f.page);
  await f.page.evaluate(() => redrawAll());   // перерисовка уже со всеми шрифтами
  await settle(f.page);
  await layer.expand(f.page);
  await settle(f.page);
  return f;
}

export async function observe(page) {
  const [state, windows, geometry, controls, popups, chartSize] = await page.evaluate(() => [
    window.__RD.stateDump(), window.__RD.windows(), window.__RD.geometry(false), window.__RD.controls(), window.__RD.popups(),
    (() => { const c = document.getElementById('chart'); const r = c && c.getBoundingClientRect(); return r ? [Math.round(r.width), Math.round(r.height)] : null; })(),
  ]);
  const answer = await layer.answer(page);
  return { state, windows, geometry, controls, popups, answer, chartSize };
}

/* ── Сравнение слепков ─────────────────────────────────────────────── */
export const J = (o) => JSON.stringify(o);
export function stateDiff(a, b) {
  const out = {};
  const keys = new Set([...Object.keys(a || {}), ...Object.keys(b || {})]);
  keys.forEach(k => { if (J(a[k]) !== J(b[k])) out[k] = b[k] === undefined ? '∅' : b[k]; });
  return out;
}
export function controlsDiff(a, b) {
  const ma = new Map(a.map(c => [c.key, c])), mb = new Map(b.map(c => [c.key, c]));
  const revealed = b.filter(c => !ma.has(c.key));
  const hidden = a.filter(c => !mb.has(c.key)).map(c => c.key);
  const props = {};
  b.forEach(c => { const o = ma.get(c.key); if (o && J(o.props) !== J(c.props)) props[c.key] = c.props; });
  return { revealed, hidden, props };
}

/* Ответ хранится по частям и только изменившиеся: подсказки (tips) одинаковы
   почти у всех шагов и весят больше всего остального. */
export function answerDiff(a, b) {
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
export function geomDiff(a, b) {
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
export const NO_EFFECT = [
  [/^#(sb-btn|ex-btn)$|fold-btn/, 'сворачивание карточки: прибор раскрыл всё заранее, закрытая карточка в перечне органов остаётся (пункт (д) закрытого списка)'],
];
/* Описания действий, которыми слой нового экрана заменил орган по закрытому
   списку (layer_new.actOverride): «секция всегда раскрыта», «кнопки нет,
   запись уже в модели». Такой шаг законно ничего не меняет. */
export const OVERRIDDEN = new Set();
export function noEffectReason(c, start) {
  for (const [re, why] of NO_EFFECT) if (re.test(c.key)) return why;
  if (c.key === '#ac-clear' && start && !(start.state.areaCalcList || []).length && !(start.state.areaVerts || []).length)
    return 'посчитанных площадей и вершин в стартовом состоянии нет: «Убрать всё» нечего убирать';
  // «Построить» без правки поля применяет ту же запись; действие этих кнопок
  // проверяется шагами набора в их поля (layer.afterFormula нажимает их там).
  if (/^#(btn-[a-z0-9]+-apply|ineq-(incomes|formula)-apply)$/.test(c.key))
    return 'кнопка «Построить» без правки поля: запись та же (пункт (а) закрытого списка)';
  if (/preset/.test(c.key)) return 'образец уже стоит в стартовом состоянии';
  if (c.key === '#btn-tb-reset') return 'ручной мировой цены в стартовом состоянии нет: возвращать к автоматической нечего';
  /* ⚠️ Дефект старого кода (не чинится, в отчёт): у type=number в Chromium нет
     selectionStart, и подмена запятой в 99-boot.js дописывает «.» к значению,
     которое браузер тут же обнуляет — «6,5» превращается в «5». Если цель шага
     с половинкой, а стартовое значение целое, набор с запятой возвращает старт. */
  if (c.kind === 'input:number' && /^#ma-/.test(c.key)) return 'запятая в числовом поле обнуляет набор (дефект 99-boot.js), значение вернулось к стартовому';
  // Вкладка или вариант, который уже выбран: щелчок по нему ничего не меняет.
  if (c.props && (c.props.active || c.props.pressed === 'true')) return 'уже выбранный вариант';
  return null;
}

/* ── Действия над органом ───────────────────────────────────────────── */
// Новое значение числа: внутри границ, с дробной частью там, где шаг дробный.
export function pickTarget(cur, min, max, step) {
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
export const comma = (v) => String(+(+v).toFixed(6)).replace('.', ',');

export function mutateFormula(val, key, sceneKey) {
  const v = String(val || '').trim();
  if (!v) return /^m-/.test(sceneKey) ? '2x+1' : '40-Q';
  return null;   // непустое поле: дописываем «+5» в конец (см. act)
}

/* Орган ищется до трёх раз с паузой: под нагрузкой машины меню или окно,
   открытое прошлым шагом, дорисовывается не сразу, и первый поиск промахивался
   (второй прогон снимка 05.10: «орган не найден» у elast и ext). */
export async function handleOf(page, key) {
  for (let i = 0; i < 3; i++) {
    const h = await page.evaluateHandle((k) => window.__RD.findControl(k), key);
    const el = h.asElement();
    if (el) return el;
    await page.waitForTimeout(400);
  }
  return null;
}

/* Прокрутка до органа — ДО щелчка и с паузой: выпадающий список calc2
   закрывается на любое событие scroll (82-input.js:1909), а Playwright
   прокручивает прямо перед нажатием, и событие приходит уже после открытия. */
export async function clickHandle(page, el) {
  try { await el.scrollIntoViewIfNeeded({ timeout: 1500 }); } catch (e) {}
  await page.waitForTimeout(120);
  /* 8 с, а не 2,5: под нагрузкой Playwright не успевал дождаться готовности
     органа, прибор щёлкал программно, и шаг шёл другим путём событий. */
  try { await el.click({ timeout: 8000 }); return 'click'; } catch (e) {
    await el.evaluate(x => x.click());
    return 'click(js)';
  }
}

/* Привести орган в другое значение так, как это сделал бы человек.
   Возвращает описание действия или бросает исключение «не найден». */
export async function act(page, c, sceneKey) {
  // Слой нового экрана сам выполняет действие над органом, заменённым по
  // закрытому списку (например, «Построить» → набор уже применён).
  if (layer.actOverride) { const r = await layer.actOverride(page, c, sceneKey); if (r != null) { OVERRIDDEN.add(r); return r; } }
  let el = await handleOf(page, layer.mapKey(c.key));
  // Орган переехал в закрытое меню (новый экран): слой открывает меню и ищет снова.
  if (!el && layer.reveal && await layer.reveal(page, layer.mapKey(c.key))) el = await handleOf(page, layer.mapKey(c.key));
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
export function steppable(c, all) {
  if (c.props && c.props.disabled) return false;
  // Карточки окна выбора меняют модель целиком: их паритет — пункт (г)
  // закрытого списка и обход всех 44 ключей, а не шаг внутри модели.
  if (c.picker) return false;
  return true;
}
export function kbdFamily(list) {
  const out = []; let n = 0;
  list.forEach(c => {
    if (/mkbd|kbd|>button\.mk(\[|$|~)/.test(c.key)) { if (n++ < 3) out.push(c); }
    else out.push(c);
  });
  return out;
}


/* Закрыть всё временное (окна, меню) средствами слоя. */
export async function layerClose(page) { if (layer && layer.closeTransient) await layer.closeTransient(page); }
