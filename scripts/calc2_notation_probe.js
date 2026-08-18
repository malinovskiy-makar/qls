/* ДОБАВКА В. Реестр обозначений: буква → величина → где используется.
   Пункты 46 и 47 («одна система подписи осей», «одна грамматика названия
   точки») нельзя закрыть на глаз: сцен 41 рабочая из 58 объявленных, и никто
   не помнит, какая буква занята. Проверка это уже показала — казалось, что
   `I` занят инвестициями, а он свободен: оси IS–LM подписаны `Y` и `r, %`,
   а `I` встречается только внутри имени кривой `IS`.

   Скрипт обходит все сцены и выписывает три вещи:
     1) подписи осей (класс `axis-name` плюс имена, объявленные сценой);
     2) имена кривых (класс `curve-name`);
     3) обозначения точек (класс `point-name`).
   Классы проставляются в единых точках печати подписи — `drawAxes`,
   `drawPlaneAxes`, `labelCurve`, `pointLabel`. Собирать по «коротким текстам»
   нельзя: деление оси «60» тоже короткое.

   Запуск: node scripts/calc2_notation_probe.js <порт> <файл.json> [сцены|all] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT   = process.argv[2] || '8601';
const OUT    = process.argv[3] || 'reports/calc2-canon/notation.json';
const SCENES = (process.argv[4] || 'all').split(',');
const BASE   = `http://127.0.0.1:${PORT}`;

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

const grab = () => {
  const svgEl = document.querySelector('#chart');
  if (!svgEl) return null;
  /* Подпись почти всегда собрана из tspan; `<title>` на экран не идёт
     (он есть у легенды) и в реестр попасть не должен. */
  const say = (n) => {
    const t = Array.from(n.childNodes).filter(c => c.nodeType === 3)
      .map(c => c.nodeValue).join('').trim();
    return t || Array.from(n.querySelectorAll('tspan')).map(x => x.textContent).join('').trim();
  };
  const byClass = (cls) => Array.from(svgEl.querySelectorAll('text.' + cls))
    .map(say).filter(Boolean);
  return {
    title: (document.querySelector('#scene-title') || {}).textContent || '',
    axisNames: byClass('axis-name'),
    curveNames: byClass('curve-name'),
    pointNames: byClass('point-name'),
    declared: {
      x: STATE.axisXName || STATE.axisXDefault || '',
      y: STATE.axisYName || STATE.axisYDefault || '',
    },
  };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => console.log('ОШИБКА СТРАНИЦЫ:', e.message));
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  let scenes = SCENES;
  if (scenes.length === 1 && scenes[0] === 'all')
    scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  console.log('сцен:', scenes.length);

  const res = {};
  for (const key of scenes) {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(600);
    res[key] = await page.evaluate(grab);
  }
  fs.writeFileSync(OUT, JSON.stringify(res, null, 1), 'utf8');

  /* ── Сводка: буква → где встречается ─────────────────────────── */
  const use = new Map();      // обозначение → { осей: [], кривых: [], точек: [] }
  const put = (sym, kind, scene) => {
    if (!sym) return;
    if (!use.has(sym)) use.set(sym, { ось: [], кривая: [], точка: [] });
    const r = use.get(sym);
    if (r[kind].indexOf(scene) < 0) r[kind].push(scene);
  };
  for (const key of Object.keys(res)) {
    const r = res[key]; if (!r) continue;
    r.axisNames.forEach(s => put(s, 'ось', key));
    r.curveNames.forEach(s => put(s, 'кривая', key));
    r.pointNames.forEach(s => put(s, 'точка', key));
  }
  const rows = Array.from(use.entries()).sort((a, b) => a[0].localeCompare(b[0], 'ru'));
  console.log('\n── ОСИ ────────────────────────────────────────────────');
  for (const key of Object.keys(res)) {
    const r = res[key]; if (!r) continue;
    console.log(String(key).padEnd(14), '· оси:', (r.axisNames.join(' | ') || '—').padEnd(30),
                '· объявлено:', r.declared.x + ' / ' + r.declared.y);
  }
  console.log('\n── ОБОЗНАЧЕНИЯ ────────────────────────────────────────');
  rows.forEach(([sym, r]) => {
    const parts = [];
    if (r['ось'].length) parts.push('ось: ' + r['ось'].length + ' (' + r['ось'].slice(0, 4).join(',') + ')');
    if (r['кривая'].length) parts.push('кривая: ' + r['кривая'].length);
    if (r['точка'].length) parts.push('точка: ' + r['точка'].length);
    console.log(String(sym).padEnd(24), parts.join(' · '));
  });
  /* Конфликт — одно обозначение в двух РАЗНЫХ ролях. Молча не чиним:
     по указанию плана он идёт в отчёт отдельным списком. */
  console.log('\n── КОНФЛИКТЫ (одно обозначение в двух ролях) ──────────');
  let n = 0;
  rows.forEach(([sym, r]) => {
    const kinds = ['ось', 'кривая', 'точка'].filter(k => r[k].length);
    if (kinds.length > 1) { n++; console.log(String(sym).padEnd(24), kinds.join(' + ')); }
  });
  if (!n) console.log('нет');
  await browser.close();
})();
