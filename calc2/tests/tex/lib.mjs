/* Общая часть приборов выгрузки .tex (calc2/tests/tex/).

   Где репозиторий и сервер, как открыть страницу, какой сборщик мерить и как
   довести модель до состояния из набора (states.json).

   Сборщик выбирается переменной TEX_ENGINE:
     site  (по умолчанию) — выгрузка самого сайта (texEnterPaper, texCapture,
           texEmit, дверь buildTex);
     proto — прототип из пакета задания (claude/mockups/calc2_tex_20261007/
           proto/texproto.js, путь можно сменить переменной PROTO). Им меряли
           нетронутый код в фазе 0. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(HERE, '..', '..', '..');
export const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
export const ENGINE = process.env.TEX_ENGINE || 'site';
export const PROTO = process.env.PROTO || path.join(ROOT, 'claude/mockups/calc2_tex_20261007/proto/texproto.js');
export const INPAGE = path.join(HERE, 'inpage.js');
export const OUT_ROOT = path.join(ROOT, 'reports', 'calc2_tex');
export const RD = path.join(ROOT, 'calc2/tests/redesign');

/* Страница калькулятора, шрифты загружены, приборы подключены.
   reducedMotion: по умолчанию 'reduce', как у приборов редизайна; старые
   приборы calc2 ходят с обычными переходами — выгрузка обязана давать один
   файл в обоих режимах (motion: 'no-preference'). */
export async function openPage(browser, o) {
  const opt = o || {};
  const ctx = await browser.newContext({ viewport: { width: opt.w || 1440, height: opt.h || 760 }, reducedMotion: opt.motion || 'reduce', locale: 'ru-RU', deviceScaleFactor: opt.scale || 1 });
  await ctx.addInitScript((th) => { try { localStorage.setItem('theme', th); } catch (e) {} }, opt.theme || 'light');
  const page = await ctx.newPage();
  page.setDefaultTimeout(opt.timeout || 30000);
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e.message || e).slice(0, 300)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 300)); });
  await page.goto(BASE + '/calc2/', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 25000 });
  await prime(page);
  return { ctx, page, errors };
}

/* Шрифты — до первого прогона (поля холста считаются по ширине подписей),
   затем приборы и, если нужно, прототип. */
export async function prime(page) {
  await page.evaluate(async () => { const all = []; document.fonts.forEach(f => all.push(f.load().catch(() => null))); await Promise.all(all); await document.fonts.ready; });
  if (ENGINE === 'proto') await page.addScriptTag({ path: PROTO });
  await page.addScriptTag({ path: INPAGE });
  await page.evaluate(() => {
    // набор значения в поле так, как его увидит обработчик страницы
    window.SETF = (id, v) => { const i = document.getElementById(id); if (!i) throw new Error('нет поля ' + id); i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true })); };
  });
}

/* Модель с её стартового состояния. «Сначала сам» снимается явно: режим
   переживает resetSceneMemory() и pickScene(). */
export async function openScene(page, key) {
  await page.evaluate((k) => {
    if (typeof setSelfMode === 'function' && typeof SELF === 'object' && SELF.on) setSelfMode(false);
    if (typeof resetSceneMemory === 'function') resetSceneMemory();
    pickScene(k);
  }, key);
  await page.waitForTimeout(450);
}

export function loadStates() {
  return JSON.parse(fs.readFileSync(path.join(HERE, 'states.json'), 'utf8'));
}
export function loadRecipes() {
  const all = {};
  for (const f of fs.readdirSync(path.join(HERE, 'recipes')).filter(x => x.endsWith('.json')).sort()) {
    const r = JSON.parse(fs.readFileSync(path.join(HERE, 'recipes', f), 'utf8'));
    Object.keys(r).filter(k => !k.startsWith('_')).forEach(k => Object.keys(r[k]).forEach(v => {
      const val = r[k][v];
      all[k + '@' + v] = (val && typeof val === 'object') ? (val.code || '') : val;   // { code, title, label } — заголовок окна «Скачать»
    }));
  }
  return all;
}

/* Шаги и жесты базового снимка редизайна воспроизводятся теми же действиями,
   что в redesign/snapshot.mjs, каждый от свежей загрузки страницы. */
let _rd = null;
export async function redesign() {
  if (_rd) return _rd;
  const L = await import(path.join(RD, 'lib.mjs'));
  const layer = await import(path.join(RD, 'layer_new.mjs'));
  L.configure({ layer, base: BASE, layerName: 'new', w: 1440, h: 760 });
  _rd = L;
  return L;
}
const _bl = {};
export function baselineOf(key) {
  if (!_bl[key]) _bl[key] = JSON.parse(fs.readFileSync(path.join(RD, 'baseline', key + '.json'), 'utf8'));
  return _bl[key];
}
export function controlDesc(bl, k) {
  return (bl.controls || []).find(c => c.key === k) || (bl.inventory && bl.inventory[k] ? { key: k, ...bl.inventory[k] } : null);
}

/* Довести страницу до состояния из набора. Возвращает { f: {ctx,page,errors}, action }.
   recipePage — страница, которую можно переиспользовать для рецептов (свежая
   загрузка не нужна: рецепт начинается с openScene). */
export async function reach(browser, st, recipePage, recipes, hold) {
  if (st.src === 'start' || st.src === 'recipe') {
    let f = recipePage;
    if (!f) f = await openPage(browser, {});
    await openScene(f.page, st.key);
    let action = '';
    if (st.src === 'recipe') {
      const code = recipes[st.recipe];
      if (code == null) throw new Error('нет рецепта ' + st.recipe);
      await f.page.evaluate((c) => { (new Function(c))(); redrawAll(); }, code);
      await f.page.waitForTimeout(650);
      action = code.slice(0, 160);
    }
    return { f, action, reused: true };
  }
  const L = await redesign();
  const f = await L.openKey(browser, st.key, 'light');
  if (hold) hold.f = f;                            // зависшую страницу прибор закроет сам
  await prime(f.page);
  const bl = baselineOf(st.key);
  let action = '';
  if (st.src === 'step') {
    const acts = [];
    for (const k of st.path) {
      const c = controlDesc(bl, k);
      if (!c) throw new Error('орган не найден в базовом снимке: ' + k);
      acts.push(await L.act(f.page, c, st.key)); await L.settle(f.page);
    }
    action = acts.join(' ; ');
  } else if (st.src === 'gesture') {
    action = await gesture(f.page, st, L);
  }
  return { f, action, reused: false };
}

// Жест базового снимка: протяжка ручки на (24, −24) шестью шагами, колесо в центре.
async function gesture(page, st, L) {
  const box = await page.evaluate(() => { const r = document.getElementById('chart').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  if (st.gesture === 'drag') {
    const hs = await page.evaluate(() => window.__RD.handles());
    const h = hs.find(x => x.key === st.handle);
    if (!h) throw new Error('ручка не найдена: ' + st.handle);
    await page.mouse.move(h.x, h.y); await page.mouse.down();
    for (let i = 1; i <= 6; i++) await page.mouse.move(h.x + 4 * i, h.y - 4 * i);
    await page.mouse.up();
  } else if (st.gesture === 'wheel') {
    await page.mouse.move(box.x + box.w / 2, box.y + box.h / 2);
    await page.mouse.wheel(0, -240);
  } else throw new Error('незнакомый жест ' + st.gesture);
  await L.settle(page);
  return st.gesture + (st.handle ? ' ' + st.handle : '');
}

/* Замер одного состояния: бумажный прогон, снимок листа (по желанию), опись,
   сборка, дверь; затем — история и хранилище после затишья. */
export async function auditState(page, opts) {
  await page.evaluate(() => window.__TXA.prepare());
  await page.waitForTimeout(420);                 // затишье истории (300 мс) после перерисовок прибора
  await page.evaluate((o) => window.__TXA.auditBegin(o), { engine: ENGINE, title: opts.title || '', label: opts.label || '' });
  let shot = null;
  if (opts.shot) shot = await page.locator('#chart').screenshot({ type: 'png' }).catch(() => null);
  const r = await page.evaluate((o) => window.__TXA.auditEnd(o), { keepList: !!opts.keepList });
  await page.waitForTimeout(420);                 // таймер истории, если выгрузка его завела, успеет сработать
  r.hist = await page.evaluate((h0) => window.__TXA.histAfter(h0), r.h0);
  delete r.h0;
  r.shot = shot;
  return r;
}

/* Название состояния → имя файла. */
export const safeName = (id) => id.replace(/[@#]/g, (c) => (c === '@' ? '_at_' : '_n_')).replace(/[^A-Za-z0-9_.-]/g, '_');
