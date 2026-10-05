/* Ночная сессия. Проверка левой панели числами по всем 41 сцене:
   ровно три карточки, один порядок, «Ввод функций» раскрыт, две другие
   свёрнуты, запрещённые заголовки не встречаются, начинка не потерялась.
     node calc2/tests/night_panel_check.mjs [--before файл.json] */
import { chromium } from 'playwright';
import fs from 'fs';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const bArg = process.argv.indexOf('--before');
const BEFORE = bArg > 0 ? JSON.parse(fs.readFileSync(process.argv[bArg + 1], 'utf8')) : null;

/* ПЕРЕНАЦЕЛЕНО (редизайн 10.2026, фаза 5а): у «Условия» по макету две
   карточки сверх трёх прежних — «Параметры» и «Вмешательство государства»
   (только там, где им есть что показать); карточки больше не сворачиваются,
   первая называется «Функции». Обязательные три — в каждой сцене. */
const WANT = ['sec-input', 'sec-params', 'sec-tax', 'sec-show', 'sec-view', 'sec-areascalc'];
const MUST = ['sec-input', 'sec-view', 'sec-areascalc'];
const FORBIDDEN = ['Что изучаем', 'Структура рынка', 'Излишки'];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', process.env.CALC2_USER || 'admin');
await page.fill('#id_password', process.env.CALC2_PASS || 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const data = await page.evaluate(async (FORB) => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const rows = [];
  for (const k of Object.keys(SCENE_ROUTE)) {
    resetSceneMemory(); pickScene(k); await wait(200);
    const cards = [...document.querySelectorAll('#tools-panel .tools-body > .section')]
      .filter(s => s.style.display !== 'none' && s.offsetParent !== null)
      .map(s => {
        const btn = s.querySelector(':scope > .fold-btn');
        const head = s.querySelector(':scope > .sec-head');
        const body = s.querySelector(':scope > .fold-body');
        return { id: s.id,
                 name: head ? head.textContent.trim() : '(без заголовка)',
                 fold: !!btn,
                 open: body ? body.classList.contains('open') : null,
                 controls: body ? [...body.querySelectorAll('input,select,button,textarea')]
                                    .filter(e => e.offsetParent !== null).length : 0 };
      });
    // Видимый текст левой панели — ищем запрещённые заголовки.
    const seen = [];
    const walk = (el) => {
      if (!el.offsetParent && el !== document.getElementById('tools-panel')) return;
      for (const ch of el.children) walk(ch);
    };
    const panel = document.getElementById('tools-panel');
    /* Свои текстовые узлы, а не «листья»: у подзаголовка «Структура рынка»
       внутри стоит кнопка-вопросик, и по фильтру «без детей» он в замер не
       попадал. */
    const visText = [...panel.querySelectorAll('*')]
      .filter(e => e.offsetParent !== null)
      .map(e => [...e.childNodes].filter(n => n.nodeType === 3)
                                 .map(n => n.nodeValue).join('').trim())
      .filter(Boolean).join(' | ');
    FORB.forEach(t => { if (visText.indexOf(t) >= 0) seen.push(t); });
    rows.push({ key: k, name: SCENE_NAMES[k] || k, cards, forbidden: seen,
                totalControls: cards.reduce((a, c) => a + c.controls, 0) });
  }
  return rows;
}, FORBIDDEN);

let ok = true;
const fail = (m) => { console.log('FAIL ' + m); ok = false; };
const ids = r => r.cards.map(c => c.id);
const badCount = data.filter(r => MUST.some(id => ids(r).indexOf(id) < 0) || ids(r).some(id => WANT.indexOf(id) < 0));
const badOrder = data.filter(r => ids(r).join() !== WANT.filter(id => ids(r).indexOf(id) >= 0).join());
const badOpen  = data.filter(r => !r.cards.length || r.cards.some(c => c.fold || c.open !== true));
const badName  = data.filter(r => !r.cards[0] || r.cards[0].name !== 'Функции');
const badForb  = data.filter(r => r.forbidden.length);
const empty    = data.filter(r => !r.cards[0] || r.cards[0].controls === 0);

console.log('сцен проверено: ' + data.length);
console.log('обязательные три на месте, чужих нет: ' + (data.length - badCount.length) + '/' + data.length);
console.log('порядок input→params→tax→view→areas: ' + (data.length - badOrder.length) + '/' + data.length);
console.log('все карточки раскрыты, кнопок сворачивания нет: ' + (data.length - badOpen.length) + '/' + data.length);
console.log('первая карточка названа «Функции»: ' + (data.length - badName.length) + '/' + data.length);
console.log('без запрещённых заголовков:    ' + (data.length - badForb.length) + '/' + data.length);
console.log('в «Вводе функций» есть органы управления: ' + (data.length - empty.length) + '/' + data.length);
if (badCount.length) fail('не тот набор карточек: ' + badCount.map(r => r.key + '(' + ids(r).join(',') + ')').join(', '));
if (badOrder.length) fail('другой порядок: ' + badOrder.map(r => r.key + ' [' + r.cards.map(c=>c.id).join('→') + ']').join('; '));
if (badOpen.length)  fail('не то состояние раскрытия: ' + badOpen.map(r => r.key + ' [' + r.cards.map(c=>c.open + (c.fold ? '(кнопка)' : '')).join(',') + ']').join('; '));
if (badName.length)  fail('первая карточка названа иначе: ' + badName.map(r => r.key + ' «' + (r.cards[0]||{}).name + '»').join('; '));
if (badForb.length)  fail('видны убранные заголовки: ' + badForb.map(r => r.key + ' ' + JSON.stringify(r.forbidden)).join('; '));
if (empty.length)    fail('пустой «Ввод функций»: ' + empty.map(r => r.key).join(', '));

if (BEFORE) {
  console.log('\nсверка начинки со снимком ДО перестройки:');
  const bm = {}; BEFORE.forEach(r => bm[r.key] = r);
  const lost = [];
  data.forEach(r => {
    const b = bm[r.key]; if (!b) return;
    const was = b.cards.reduce((a, c) => a + c.controls, 0);
    if (r.totalControls < was) lost.push(r.key + ': было ' + was + ', стало ' + r.totalControls);
  });
  console.log('  сцен, где органов управления стало МЕНЬШЕ: ' + lost.length);
  lost.forEach(l => console.log('    ' + l));
  if (lost.length) fail('панель потеряла содержимое');
}
if (errs.length) fail('ошибки страницы: ' + errs.slice(0, 3).join(' | '));
await browser.close();
console.log('\nИТОГ: ' + (ok ? 'левая панель одинакова во всех 41 сцене' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
