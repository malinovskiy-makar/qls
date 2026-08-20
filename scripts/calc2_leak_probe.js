/* ФАЗА 12. УТЕЧКА ПАРАМЕТРА МЕЖДУ МОДЕЛЯМИ.

   Контрольный опыт владельца, повторённый настоящими переходами:
     · чистая загрузка → сразу «Потоварные налоги» — сколько ползунков;
     · чистая загрузка → «Построение графиков», вписать x^2-ax → назад ко всем
       блокам → «Потоварные налоги» — сколько ползунков.
   Одна и та же модель, два пути: числа обязаны совпасть.

   Запуск: node scripts/calc2_leak_probe.js <порт> [файл.json] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2-review-19aug/leak.json';
const BASE = `http://127.0.0.1:${PORT}`;
const ok = [], bad = [];
const check = (c, w) => (c ? ok : bad).push(w);

const count = () => {
  const all = Array.from(document.querySelectorAll('.pchip-param'));
  /* ⚠️ Считаем ВИДИМЫЕ чипы: предмет жалобы — ползунок, который человек видит
     в панели, а не узел, оставшийся в разметке под `display: none`. */
  const seen = all.filter(c => c.getBoundingClientRect().height > 0);
  return {
    chips: seen.length,
    hidden: all.length - seen.length,
    where: all.map(c => (c.parentElement && c.parentElement.id) || '?'),
    names: Object.keys(STATE.params || {}),
    scene: STATE.sceneKey,
  };
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
  const fresh = async () => {
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    await page.waitForFunction(
      () => typeof pickScene === 'function' && typeof STATE === 'object', null, { timeout: 20000 });
  };

  // ── путь 1: сразу в налоги ────────────────────────────────────────────
  await fresh();
  await page.evaluate(() => pickScene('tax'));
  await page.waitForTimeout(1100);
  const direct = await page.evaluate(count);
  check(direct.chips === 0, 'прямой путь: ползунков-параметров ' + direct.chips);

  // ── путь 2: через «Построение графиков» с буквой ──────────────────────
  await fresh();
  await page.evaluate(() => pickScene('m-graph'));
  await page.waitForTimeout(1000);
  await page.evaluate(() => {
    const box = document.getElementById('graph-rows');
    if (box) openSection(box.closest('.section').id);
    const i = document.querySelector('#graph-rows .f-slot > input');
    if (i) { i.value = 'x^2-a*x'; i.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  await page.waitForTimeout(1200);
  const inGraph = await page.evaluate(count);
  check(inGraph.chips >= 1, 'в «Построении графиков» ползунок буквы появился: ' + JSON.stringify(inGraph.names));

  // «Назад ко всем блокам» — настоящей кнопкой
  await page.evaluate(() => {
    const b = document.getElementById('scene-back');
    if (b) b.click();
  });
  await page.waitForTimeout(700);
  await page.evaluate(() => pickScene('tax'));
  await page.waitForTimeout(1200);
  const viaGraph = await page.evaluate(count);
  check(viaGraph.chips === direct.chips,
        'через «Построение графиков»: ползунков ' + viaGraph.chips +
        ' (прямым путём ' + direct.chips + '), буквы ' + JSON.stringify(viaGraph.names));

  // ── и обратный переход тоже ───────────────────────────────────────────
  await page.evaluate(() => pickScene('m-graph'));
  await page.waitForTimeout(1000);
  const back = await page.evaluate(count);
  check(true, 'возврат в «Построение графиков»: ползунков ' + back.chips +
        ' ' + JSON.stringify(back.names));

  // ── и по всем сценам разом: после буквы ни одна чужая её не показывает ─
  const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  const leaked = [];
  for (const key of scenes) {
    if (key === 'm-graph') continue;
    await page.evaluate(() => pickScene('m-graph'));
    await page.waitForTimeout(700);
    await page.evaluate(() => {
      const box = document.getElementById('graph-rows');
      if (box) openSection(box.closest('.section').id);
      const i = document.querySelector('#graph-rows .f-slot > input');
      if (i && !i._mf) { i.value = 'x^2-a*x'; i.dispatchEvent(new Event('input', { bubbles: true })); }
      else if (i && i._mf) { i._mf.setValue('x^2-a\\cdot x'); i.dispatchEvent(new Event('input', { bubbles: true })); }
    });
    await page.waitForTimeout(700);
    await page.evaluate(k => pickScene(k), key);
    await page.waitForTimeout(750);
    const r = await page.evaluate(count);
    /* ⚠️ Сцена может заявить букву САМА: «Деформации графика» ведёт свой «a»
       через sceneExtraParams. Своя буква — не утечка, и прибор обязан их
       различать: первая версия объявила дефектом ровно этот случай. */
    const own = await page.evaluate(() => (typeof sceneExtraParams === 'function' ? sceneExtraParams() : []));
    if (r.names.indexOf('a') >= 0 && own.indexOf('a') < 0) leaked.push(key + ' (' + r.chips + ')');
    process.stdout.write('.');
  }
  console.log('');
  check(leaked.length === 0, 'буква «a» не протекла ни в одну из сцен' +
        (leaked.length ? ': ' + leaked.slice(0, 6).join(', ') : ''));

  fs.writeFileSync(OUT, JSON.stringify({ ok, bad, direct, inGraph, viaGraph, leaked, pageErrors: errs }, null, 1), 'utf8');
  console.log('\n── ФАЗА 12 ────────────────────────────────────────');
  ok.forEach(t => console.log('  v ' + t));
  bad.forEach(t => console.log('  X ' + t));
  console.log('\nитог: ' + ok.length + ' сошлось, ' + bad.length + ' нет · ошибок страницы: ' + errs.length);
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})();
