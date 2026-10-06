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
// Холст 732×590: старый экран — окно 1324×638, новый — 1440×760.
const NEWL = arg('layer', 'old') === 'new';
const W = +arg('width', NEWL ? '1440' : '1324'), H = +arg('height', NEWL ? '760' : '638');
const layer = await import(path.join(HERE, 'layer_' + LAYER + '.mjs'));
/* Повтор: новый экран проходит РОВНО шаги базового снимка (а не открывает
   органы заново), иначе сравнивать было бы нечего. --replay <папка снимка>. */
const REPLAY = arg('replay', '');

import * as L from './lib.mjs';
const { fresh, settle, openKey, observe, J, stateDiff, controlsDiff, answerDiff, geomDiff, noEffectReason, act, steppable, kbdFamily } = L;
L.configure({ layer, base: BASE, layerName: LAYER, w: W, h: H });

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
      await runStep(browser, key, start, pathCtl, rec, 9, null, st);
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

async function runStep(browser, key, start, pathCtl, rec, depth = 1, parent = null, expected = null) {
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
      /* Повтор сценария (--replay) идёт от старта, без «открывшего» шага: если
         и в базовом снимке шаг относительно старта ничего не менял (закрыть
         окно, которое сам же открыл), «ничего» и есть его действие. */
      const asBase = expected && expected.effect === 'none'
        ? 'как в базовом снимке: шаг возвращает к старту (относительно открывшего — ' + (expected.effectVsOpener || 'none') + ')'
        /* Цвет для строки без кривой (пустая строка «Построения графиков»):
           модель не меняется и в базовом снимке, там менялся только вид кнопки. */
        : (expected && expected.effect !== 'model' && /cpick-sw/.test(step.path[step.path.length - 1])
          ? 'как в базовом снимке: цвет строки без кривой модель не меняет' : null);
      const why = noEffectReason(pathCtl[pathCtl.length - 1], start) || acts.find(a => L.OVERRIDDEN.has(a)) || asBase;
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
    /* Ошибки страницы — без повторов: одна и та же ошибка старого кода (путь
       с NaN в «Сложении») печаталась то четыре, то пять раз в зависимости от
       числа перерисовок, и файл снимка дрожал. */
    if (rec.errors) rec.errors = [...new Set(rec.errors.map(e => e.replace(/(Expected number, ").*$/, '$1…')))];
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
