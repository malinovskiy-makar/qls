/* Длинная ночная сессия 24.08: четыре дефекта приёмки, сюжет сложения,
   диагностика хвостов, шрифты. ФАЗА 15 — контактный лист для утренней
   приёмки. Снимки берёт calc2/tests/shot.mjs (светлая тема, 1440 px) и
   складывает в reports/calc2_long_night/index.html: страница открывается
   двойным щелчком, сервер для просмотра не нужен.
     node calc2/tests/night2_contact_sheet.mjs */
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const OUT = 'reports/calc2_long_night';
const SHOTS = path.join(OUT, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });
/* ⚠️ БЛОК «КЛЮЧЕВЫЕ ЗНАЧЕНИЯ» ОТКРЫВАЕТСЯ РУКАМИ. Он свёрнут по умолчанию,
   и первые снимки показывали пустую полоску вместо тех самых чисел, ради
   которых сессия и затевалась. Открываем и его, и «Объяснение модели». */
const OPEN = "setToolsOpen(true); setParamsOpen(true); var b1=document.getElementById('sb-btn'); if (b1 && b1.getAttribute('aria-expanded') !== 'true') b1.click(); ";

const PLAN = [
  { g: 'Новый сюжет · сложение спросов и предложений', f: '01-sum-main.png', scene: 'sdsum',
    setup: OPEN + "redrawAll();",
    cap: 'Как открывается сюжет: две группы спроса, две группы предложения',
    num: 'D₁ 100−Q, D₂ 60−Q, S₁ Q, S₂ Q+20 · равновесие (70; 45)' },
  { g: 'Новый сюжет · сложение спросов и предложений', f: '02-sum-panel.png', scene: 'sdsum',
    setup: OPEN + "var e=document.getElementById('scoreboard'); if(e) e.scrollIntoView(); redrawAll();",
    cap: 'Аналитика по группам и аналитическая запись суммарных кривых',
    num: 'D₁ 55 и 1512,5 · D₂ 15 и 112,5 · вместе 70 и 1625' },
  { g: 'Новый сюжет · сложение спросов и предложений', f: '03-sum-three.png', scene: 'sdsum',
    setup: OPEN + "sumSetCount('D', 3); redrawAll();",
    cap: 'Три группы спроса: у суммарной кривой два излома',
    num: 'участок с наклоном 1/3 записан дробью (200 − Q)/3, а не «0,333»' },
  { g: 'Новый сюжет · сложение спросов и предложений', f: '04-sum-one.png', scene: 'sdsum',
    setup: OPEN + "sumSetCount('D', 1); sumSetCount('S', 1); redrawAll();",
    cap: 'По одной группе с каждой стороны: изломов нет, обычный рынок',
    num: 'сумма из одной группы совпадает с самой группой' },

  { g: 'Четыре дефекта приёмки · табло ключевых значений', f: '05-ceiling.png', scene: 'ceil',
    setup: OPEN + "setType('ceiling'); setPReg(30); redrawAll();",
    cap: 'Потолок цены 30 — было «Q* 50, P* 50»',
    num: 'Pc 30 · Qd 70 · Qs 30 · дефицит 40 · DWL 400 · «Рынок при потолке цены»' },
  { g: 'Четыре дефекта приёмки · табло ключевых значений', f: '06-floor.png', scene: 'ceil',
    setup: OPEN + "setType('floor'); setPReg(70); redrawAll();",
    cap: 'Пол цены 70 — было «Q* 50, P* 50»',
    num: 'Pf 70 · Qd 30 · Qs 70 · избыток 40 · DWL 400 · «Рынок при поле цены»' },
  { g: 'Четыре дефекта приёмки · табло ключевых значений', f: '07-ceiling-free.png', scene: 'ceil',
    setup: OPEN + "setType('ceiling'); setPReg(70); redrawAll();",
    cap: 'Потолок 70 не связывает — равновесие настоящее, табло прежнее',
    num: 'Q* 50 · P* 50 · заголовок снова «Равновесие D = S»' },
  { g: 'Четыре дефекта приёмки · табло ключевых значений', f: '08-tax.png', scene: 'taxes',
    setup: OPEN + "setTaxForm('unit'); setTaxSide('seller'); setTax(20); redrawAll();",
    cap: 'Налог 20: одной цены на рынке больше нет',
    num: 'Q 40 · Pb 60 · Ps 40 · «Рынок после налога»' },
  { g: 'Четыре дефекта приёмки · табло ключевых значений', f: '09-quota.png', scene: 'quota',
    setup: OPEN + "setQuota(40); setQuotaPos(0.5); redrawAll();",
    cap: 'Квота 40: цена не определена, она в коридоре',
    num: 'Q 40 · P 50 · коридор 40…60 · «Рынок при квоте»' },

  { g: 'Четыре дефекта приёмки · запись формул', f: '10-piecewise.png', scene: 'sd',
    setup: OPEN + "var i=document.getElementById('curve-expr-1'); PW.rows=[]; PW.n=2;"
         + " openPiecewise(i,'Q'); document.getElementById('pw-apply').click();"
         + " setTimeout(function(){}, 0); redrawAll();"
         + " var cb=document.querySelector('#curve-list .curve-row input[type=checkbox]'); cb.click(); cb.click();",
    cap: 'Кусочная в поле после пересборки строки кривой',
    num: 'список из двух условий на одном уровне, без вложенности и без «иначе ∞»' },
  { g: 'Четыре дефекта приёмки · запись формул', f: '11-2P.png', scene: 'sd',
    setup: OPEN + "var i=document.getElementById('curve-expr-1'); i.value='100-2P';"
         + " i.dispatchEvent(new Event('input',{bubbles:true})); redrawAll(); updatePult();",
    cap: '«100-2P» без звёздочки — было горизонталью на 98, молча',
    num: 'наклон −0,5, свободный член 50, сдвиг D = 0, ручка посередине' },

  { g: 'Диагностика хвостов', f: '12-ktv-kink.png', scene: 'trade',
    setup: OPEN + "var i=document.getElementById('inp-ppft');"
         + " i.value='(X >= 0 and X < 40) ? 100 - 0.5*X : (X >= 40 ? 160 - 2*X : NaN)';"
         + " i.dispatchEvent(new Event('input',{bubbles:true}));"
         + " var p=document.getElementById('inp-ppft-price'); p.value='1';"
         + " p.dispatchEvent(new Event('change',{bubbles:true}));"
         + " document.getElementById('btn-ppft-apply').click();",
    cap: 'КТВ по ВОГНУТОЙ кусочной КПВ: касание липнет к излому',
    num: 'производство (40; 80) · Xмакс 120 · Yмакс 120 · было (0; 100)' },
  { g: 'Диагностика хвостов', f: '13-fonts.png', scene: 'costs',
    setup: OPEN + "redrawAll();",
    cap: 'Подписи графика набраны математикой: MC, ATC, AVC, AFC прямым, Q и P наклонным',
    num: 'опись: 108 случаев → 84; подписи графика 44 → 20' },
];

const errs = [];
for (const s of PLAN) {
  const r = execFileSync('node',
    ['calc2/tests/shot.mjs', s.scene, path.join(SHOTS, s.f), 'light', s.setup],
    { encoding: 'utf-8', env: { ...process.env, SHOT_W: '1440' } });
  if (r.includes('ОШИБКИ')) errs.push(s.f + ': ' + r.split('ОШИБКИ:')[1].trim().slice(0, 200));
  console.log('снят  ' + s.f.padEnd(20) + s.cap);
}

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const groups = [];
PLAN.forEach(s => {
  let g = groups.find(x => x.name === s.g);
  if (!g) { g = { name: s.g, items: [] }; groups.push(g); }
  g.items.push(s);
});
const cards = list => list.map(s => `
      <figure class="shot">
        <a href="shots/${s.f}" target="_blank"><img src="shots/${s.f}" alt="${esc(s.cap)}" loading="lazy"></a>
        <figcaption><b>${esc(s.cap)}</b><span>${esc(s.num)}</span></figcaption>
      </figure>`).join('');

const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>calc2 · длинная ночная сессия 24.08</title>
<style>
  :root { color-scheme: light; }
  body { margin: 0; padding: 28px 32px 60px; background: #f6f7f9; color: #10141c;
         font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  h2 { font-size: 17px; margin: 34px 0 12px; padding-top: 18px; border-top: 1px solid #dfe3e8; }
  p.lead { margin: 0 0 4px; color: #4a5361; max-width: 78ch; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(430px, 1fr)); gap: 18px; }
  .shot { margin: 0; background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; overflow: hidden; }
  .shot img { display: block; width: 100%; height: auto; }
  .shot figcaption { display: block; padding: 9px 12px; font-size: 13px; border-top: 1px solid #eceff3; }
  .shot figcaption span { display: block; margin-top: 3px; color: #6b7482; font-size: 12px;
                          font-family: ui-monospace, monospace; }
  .note { background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 14px 16px;
          margin: 14px 0 0; max-width: 96ch; }
  .note ul { margin: 8px 0 0; padding-left: 20px; }
  .warn { border-color: #e0b4b4; background: #fff8f8; }
</style></head><body>
<h1>calc2 · длинная ночная сессия 24 августа</h1>
<p class="lead">Ветка <code>feat/calc2-interv-night</code>. Светлая тема, ширина окна 1440&nbsp;px.
Под каждым снимком написано, что на нём и какие числа он обязан показывать. Числа проверены
постоянными проверками в <code>calc2/tests/calc2_math.mjs</code>.</p>
<div class="note">
  <b>Что смотреть в первую очередь.</b>
  <ul>
    <li><b>Табло «Ключевые значения»</b> при потолке, поле, налоге и квоте: раньше там стояло
        равновесие БЕЗ вмешательства («Q* 50, P* 50»), теперь — то, что на рынке на самом деле.
        Снимок 07 показывает обратное: НЕсвязывающий потолок равновесия не отменяет, и табло
        обязано остаться прежним.</li>
    <li><b>Новый сюжет сложения.</b> Проверьте излом суммарного спроса в (40;&nbsp;60) и
        суммарного предложения в (20;&nbsp;20), а в правой панели — что излишки по группам
        (1512,5 и 112,5) складываются ровно в 1625.</li>
    <li><b>Запись кусочной</b> (снимок 10): условия идут списком на одном уровне. Раньше после
        первой же пересборки строки кривой в поле появлялась матрёшка с «иначе&nbsp;∞».</li>
    <li><b>Шрифты</b> (снимок 13): обозначения на графике набраны шрифтами KaTeX — переменная
        наклонная, многобуквенное обозначение прямое.</li>
  </ul>
</div>
<div class="note warn">
  <b>Решено за владельца — проверьте, согласны ли.</b>
  <ul>
    <li>Роли блоков разведены: «Ключевые значения» отвечают «что сейчас», «Вмешательство» —
        «как изменилось». Блок «Излишки» по-прежнему показывает CS и PS ДО вмешательства
        со своей оговоркой.</li>
    <li>В сюжете сложения вторая группа предложения взята как <code>Q + 20</code>, а не
        <code>Q − 20</code>, как написано в задании: только так сходятся все остальные числа
        инварианта (излом (20;&nbsp;20), S₂ = 25 при цене 45, равновесие (70;&nbsp;45)).</li>
    <li>Область кусочной, не покрытая ни одним условием, строкой не печатается вовсе —
        функция там просто не определена.</li>
  </ul>
</div>
${groups.map(g => `<h2>${esc(g.name)}</h2><div class="grid">${cards(g.items)}</div>`).join('\n')}
${errs.length ? `<div class="note warn"><b>Ошибки страницы при съёмке:</b><ul>${errs.map(e => '<li>' + esc(e) + '</li>').join('')}</ul></div>` : ''}
</body></html>`;
fs.writeFileSync(path.join(OUT, 'index.html'), html);
console.log('\nЛист: ' + path.join(OUT, 'index.html') + '  (снимков: ' + PLAN.length + ')');
if (errs.length) console.log('ОШИБКИ СТРАНИЦЫ при съёмке:\n' + errs.join('\n'));
