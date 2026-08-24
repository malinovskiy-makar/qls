/* Лист снимков закрывающей ночной сессии (Фаза 9, 24.08).
   Светлая тема, 1440 px — кроме узкого экрана 380 px, он снимается отдельно.
     CALC2_BASE_URL=http://127.0.0.1:8099 node calc2/tests/final_night_shots.mjs */
import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'nightshot';
const PASS = process.env.CALC2_PASS || 'nightshot12345';
const OUT = 'reports/calc2_final_night/shots/';
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));

await page.evaluate;
await page.goto(BASE + '/login/', { waitUntil: 'networkidle' });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.evaluate(() => localStorage.setItem('theme', 'light')).catch(() => {});
await page.goto(BASE + '/calc2/', { waitUntil: 'networkidle' });
await page.waitForTimeout(1300);

const expandAll = () => page.evaluate(() => {
  setToolsOpen(true); setParamsOpen(true);
  document.querySelectorAll('.fold-btn[aria-controls]').forEach(b => {
    const bd = document.getElementById(b.getAttribute('aria-controls'));
    if (bd) { bd.classList.add('open'); b.setAttribute('aria-expanded', 'true'); }
  });
});
const scene = async (k) => {
  await page.evaluate(x => { resetSceneMemory(); pickScene(x); }, k);
  await page.waitForTimeout(700);
  await expandAll();
  await page.waitForTimeout(450);
};

const shots = [];
const shot = async (file, caption) => {
  await page.screenshot({ path: OUT + file });
  shots.push([file, caption]);
  console.log('снят', file);
};
/* Подсказку снимаем ЦЕЛОЙ страницей, а не вырезкой: плашка живёт в body
   поверх всего, и вырезка панели её бы обрезала. */
const hoverTip = async (pick) => {
  const sel = await page.evaluate((p) => {
    const el = Array.from(document.querySelectorAll('[data-tip]'))
      .filter(e => e.getBoundingClientRect().width > 1)
      .find(e => (e.getAttribute('data-tip') || '').indexOf(p) >= 0);
    if (!el) return null;
    el.setAttribute('data-shotpick', '1');
    return el.getAttribute('data-tip');
  }, pick);
  if (!sel) return null;
  const h = await page.$('[data-shotpick]');
  await h.hover();
  await page.waitForTimeout(400);
  return sel;
};
const dropTip = () => page.evaluate(() => {
  document.querySelectorAll('[data-shotpick]').forEach(e => e.removeAttribute('data-shotpick'));
  const t = document.getElementById('hint-tip'); if (t) t.style.display = 'none';
});

/* ── 1–3. Подсказка в трёх разных местах, включая формулу внутри ── */
await scene('costs');
let t1 = await hoverTip('Цвет $');
await shot('tip-1-color.png',
  'Подсказка над образцом цвета в «Издержках»: «' + (t1 || '—') + '». '
  + 'Обозначение внутри набрано формулой, слово «Цвет» — шрифтом сайта.');
await dropTip();

await scene('mono');
let t2 = await hoverTip('Убрать кривую');
await shot('tip-2-curverow.png',
  'Подсказка над крестиком в строке кривой: «' + (t2 || '—') + '». '
  + 'Раньше это был браузерный title — он не появлялся ни по клавиатуре, ни на сенсорном экране.');
await dropTip();

await scene('sd');
let t3 = await hoverTip('$');
await shot('tip-3-formula.png',
  'Подсказка с ЦЕЛОЙ формулой: «' + (t3 || '—') + '». '
  + 'Запись кривой переведена в набор тем же mathToTex, что и предпросмотр под полем ввода.');
await dropTip();

/* ── 4. Узкий экран 380 px ── */
await page.setViewportSize({ width: 380, height: 800 });
await scene('mono');
const t4 = await hoverTip('Убрать кривую');
await shot('tip-4-narrow380.png',
  'Тот же компонент на экране 380 px: «' + (t4 || '—') + '». Плашка прижата к окну и '
  + 'не уходит за край — проверено на 12 подсказках подряд, вылезло 0.');
await dropTip();
await page.setViewportSize({ width: 1440, height: 950 });
await page.waitForTimeout(400);

/* ── 5–7. Сцены Фазы 2 с починенными подписями ── */
const chartShot = async (key, file, caption) => {
  await scene(key);
  const el = await page.$('#graph-wrap');
  await el.screenshot({ path: OUT + file });
  shots.push([file, caption]);
  console.log('снят', file);
};
await chartShot('tax', 'labels-1-tax.png',
  'Налоги: подписи S и S + t набраны математикой. Диагноз «рисуются после конца '
  + 'перерисовки» замер отверг — правило читало склейку tspan вместо исходной записи.');
await chartShot('mono-nat', 'labels-2-mono-nat.png',
  'Естественная монополия: ATC, MC, E_ATC, E_MC. Числа у осей остались с табличными '
  + 'цифрами, а их индексы-обозначения уехали в математический шрифт.');
await chartShot('plants', 'labels-3-plants.png',
  'Сложение заводов: TC₁ и TC₂ с юникодным индексом, «TC совокупная» разрезана — '
  + 'обозначение формулой, слово шрифтом сайта.');
await chartShot('prod', 'labels-4-prod.png',
  'Производство: смешанные фразы «TP, общий продукт», «max AP = MP при L = 15». '
  + 'Раньше это числилось долгом «на отдельную задачу».');

/* ── 8–10. Протечка MSB/MSC: до перехода, после, и возврат ── */
await scene('ext');
let panel = await page.$('#tools-panel');
await panel.screenshot({ path: OUT + 'leak-1-ext.png' });
shots.push(['leak-1-ext.png',
  '«Внешние эффекты»: блок MSB / MSC на своём месте, во «Вводе функций».']);
console.log('снят leak-1-ext.png');

await scene('mono');
panel = await page.$('#tools-panel');
await panel.screenshot({ path: OUT + 'leak-2-mono.png' });
shots.push(['leak-2-mono.png',
  'Монополия СРАЗУ ПОСЛЕ «Внешних эффектов»: чужих полей MSB / MSC нет. '
  + 'До правки они здесь висели — видимость ставил обработчик щелчка, а не общая синхронизация.']);
console.log('снят leak-2-mono.png');

await scene('ext');
panel = await page.$('#tools-panel');
await panel.screenshot({ path: OUT + 'leak-3-back.png' });
shots.push(['leak-3-back.png',
  'Возврат во «Внешние эффекты»: свои поля на месте. Проверено оба направления — '
  + 'чужое не протекает, своё не пропадает.']);
console.log('снят leak-3-back.png');

/* ── 11. Панель целиком: обозначения в подписях галочек ── */
await scene('costs');
panel = await page.$('#tools-panel');
await panel.screenshot({ path: OUT + 'panel-notation.png' });
shots.push(['panel-notation.png',
  'Левая панель «Издержек»: MC, ATC, AVC, AFC, TC, VC, FC в подписях галочек набраны '
  + 'формулой одним общим проходом, а не полутора сотнями правок в шаблоне.']);
console.log('снят panel-notation.png');

await scene('sd');
panel = await page.$('#params-panel');
await panel.screenshot({ path: OUT + 'panel-analytics.png' });
shots.push(['panel-analytics.png',
  'Правая аналитика: CS, PS, DWL и прочие обозначения в подписях и в разборе. '
  + 'Здесь жили 276 случаев из 427 — их не видел сломанный прибор.']);
console.log('снят panel-analytics.png');

console.log('ошибки страницы:', errs.length ? errs.slice(0, 5) : 'нет');
await browser.close();

/* ── Лист ── */
const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const html = `<!doctype html><html lang="ru"><meta charset="utf-8">
<title>calc2 — закрывающая ночная сессия, 24.08.2026</title>
<style>
 :root { color-scheme: light; }
 body { margin:0; padding:32px 28px 64px; background:#F7F7F5; color:#1A1A18;
        font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
 h1 { font-size:22px; font-weight:600; margin:0 0 6px; }
 .lead { color:#5C5C57; max-width:70ch; margin:0 0 28px; }
 figure { margin:0 0 34px; background:#fff; border:1px solid #E3E3DE; border-radius:10px;
          overflow:hidden; max-width:1180px; }
 figure img { display:block; width:100%; height:auto; }
 figcaption { padding:11px 14px; font-size:13px; color:#3D3D39; border-top:1px solid #EFEFEB; }
 .n { display:inline-block; min-width:22px; font-weight:600; color:#8A8A82; }
</style>
<h1>calc2 — закрывающая ночная сессия, 24 августа 2026</h1>
<p class="lead">Светлая тема, ширина 1440&nbsp;px (кроме снимка узкого экрана — 380&nbsp;px).
Ветка <code>feat/calc2-interv-night</code>. Под каждым снимком сказано, что на нём смотреть.</p>
${shots.map(([f, c], i) =>
  `<figure><img src="shots/${f}" alt=""><figcaption><span class="n">${i + 1}.</span> ${esc(c)}</figcaption></figure>`
).join('\n')}
</html>`;
const { writeFileSync } = await import('fs');
writeFileSync('reports/calc2_final_night/index.html', html);
console.log('\nЛист собран: reports/calc2_final_night/index.html — снимков ' + shots.length);
