/* Ночная сессия «вмешательство государства и внешние эффекты». ФАЗА 7 —
   контактный лист для утренней приёмки. Снимки берёт calc2/tests/shot.mjs
   (светлая тема, ширина 1440 px), каждый со своей настройкой сцены, и
   складывает в reports/calc2_interv_night/index.html: страница открывается
   двойным щелчком, сервер для просмотра не нужен.
     node calc2/tests/interv_contact_sheet.mjs */
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const OUT = 'reports/calc2_interv_night';
const SHOTS = path.join(OUT, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

// Каждый снимок: файл, сцена, настройка сцены, подпись, к какому разделу листа.
const PLAN = [
  { g: 'Четыре вида вмешательства', f: '01-tax.png', scene: 'taxes',
    setup: "setTaxForm('unit'); setTaxSide('seller'); setTax(20); redrawAll();",
    cap: 'Налог · потоварный, ставка t = 20',
    num: 'Q₁ = 40, Pb = 60, Ps = 40, сбор = 800, DWL = 100' },
  { g: 'Четыре вида вмешательства', f: '02-vat.png', scene: 'taxes',
    setup: "setTaxForm('vat'); setTax(20); redrawAll();",
    cap: 'Налог · НДС, ставка τ = 20 %',
    num: 'Q₁ = 45,45, Pb = 54,55, Ps = 45,45, сбор = 413,22, DWL = 20,66' },
  { g: 'Четыре вида вмешательства', f: '03-subsidy.png', scene: 'taxes',
    setup: "setType('subsidy'); setTaxKind('unit'); setTax(20); redrawAll();",
    cap: 'Субсидия · потоварная, ставка s = 20',
    num: 'Q₁ = 60, расход бюджета 1200, DWL = 100' },
  { g: 'Четыре вида вмешательства', f: '04-ceiling.png', scene: 'ceil',
    setup: "setType('ceiling'); setPReg(30); document.getElementById('chk-ghost').click();",
    cap: 'Потолок цены 30 · включено «было → стало»',
    num: 'Qd = 70, Qs = 30, дефицит 40, торговля 30, DWL = 400' },
  { g: 'Четыре вида вмешательства', f: '05-floor.png', scene: 'ceil',
    setup: "setType('floor'); setPReg(70); document.getElementById('chk-ghost').click();",
    cap: 'Пол цены 70 · включено «было → стало»',
    num: 'Qs = 70, Qd = 30, избыток 40, торговля 30, DWL = 400' },
  { g: 'Четыре вида вмешательства', f: '06-quota.png', scene: 'quota',
    setup: "setQuota(40); setQuotaPos(0.5); redrawAll();",
    cap: 'Квота 40 · цена по центру коридора',
    num: 'коридор [40; 60], цена 50, CS = PS = 1200, CS+PS = 2400, DWL = 100' },

  { g: 'Квота · три положения ползунка внутри коридора', f: '07-quota-lo.png', scene: 'quota',
    setup: "setQuota(40); setQuotaPos(0); redrawAll();",
    cap: 'Цена у нижней границы коридора',
    num: 'P = 40, CS = 1600, PS = 800, CS+PS = 2400, DWL = 100' },
  { g: 'Квота · три положения ползунка внутри коридора', f: '08-quota-mid.png', scene: 'quota',
    setup: "setQuota(40); setQuotaPos(0.5); redrawAll();",
    cap: 'Цена посередине коридора',
    num: 'P = 50, CS = 1200, PS = 1200, CS+PS = 2400, DWL = 100' },
  { g: 'Квота · три положения ползунка внутри коридора', f: '09-quota-hi.png', scene: 'quota',
    setup: "setQuota(40); setQuotaPos(1); redrawAll();",
    cap: 'Цена у верхней границы коридора',
    num: 'P = 60, CS = 800, PS = 1600, CS+PS = 2400, DWL = 100' },

  { g: 'Внешние эффекты · три состояния', f: '10-ext-off.png', scene: 'ext',
    setup: "redrawAll();",
    cap: 'Как открывается сцена: MSB и MSC выключены',
    num: 'общественных кривых на графике нет, оптимум = рынку (Q = 50), DWL = 0' },
  { g: 'Внешние эффекты · три состояния', f: '11-ext-neg.png', scene: 'ext',
    setup: "document.getElementById('chk-msc').click(); var i = document.getElementById('inp-msc');"
         + " i.value = 'Q + 20'; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change'));",
    cap: 'Отрицательный эффект: включена MSC = Q + 20',
    num: 'рынок Q = 50, оптимум Q = 40, P = 60, DWL = 100, налог Пигу 20' },
  { g: 'Внешние эффекты · три состояния', f: '12-ext-pos.png', scene: 'ext',
    setup: "document.getElementById('chk-msb').click(); var i = document.getElementById('inp-msb');"
         + " i.value = '120 - Q'; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change'));",
    cap: 'Положительный эффект: включена MSB = 120 − Q',
    num: 'рынок Q = 50, оптимум Q = 60, P = 60, DWL = 100, субсидия 20' },
];

const errs = [];
for (const s of PLAN) {
  const r = execFileSync('node',
    ['calc2/tests/shot.mjs', s.scene, path.join(SHOTS, s.f), 'light', s.setup],
    { encoding: 'utf-8', env: { ...process.env, SHOT_W: '1440' } });
  if (r.includes('ОШИБКИ')) errs.push(s.f + ': ' + r.split('ОШИБКИ:')[1].trim().slice(0, 200));
  console.log('снят  ' + s.f.padEnd(18) + s.cap);
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
<title>calc2 · вмешательство государства и внешние эффекты</title>
<style>
  :root { color-scheme: light; }
  body { margin: 0; padding: 28px 32px 60px; background: #f6f7f9; color: #10141c;
         font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  h2 { font-size: 17px; margin: 34px 0 12px; padding-top: 18px; border-top: 1px solid #dfe3e8; }
  p.lead { margin: 0 0 4px; color: #4a5361; max-width: 74ch; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(430px, 1fr)); gap: 18px; }
  .shot { margin: 0; background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; overflow: hidden; }
  .shot img { display: block; width: 100%; height: auto; }
  .shot figcaption { display: block; padding: 9px 12px; font-size: 13px; border-top: 1px solid #eceff3; }
  .shot figcaption span { display: block; margin-top: 3px; color: #6b7482; font-size: 12px;
                          font-family: ui-monospace, monospace; }
  .note { background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 14px 16px;
          margin: 14px 0 0; max-width: 92ch; }
  .note ul { margin: 8px 0 0; padding-left: 20px; }
</style></head><body>
<h1>calc2 · вмешательство государства и внешние эффекты</h1>
<p class="lead">Ночная сессия 24.08, ветка <code>feat/calc2-interv-night</code>.
Светлая тема, ширина окна 1440&nbsp;px. Под каждым снимком написано, что на нём и какие числа
он обязан показывать.</p>
<div class="note">
  <b>Что смотреть.</b>
  <ul>
    <li>Карточка налогов на главном экране теперь одна: «Налоги и субсидии». Вид налога
        (потоварный, НДС, акциз) выбирается внутри, в правой панели.</li>
    <li>Выбор идёт сверху вниз и по одной ветке: у НДС и акциза не спрашивают, кто платит,
        у субсидии нет кнопки «Акциз», у потолка нет ни вида, ни стороны.</li>
    <li>У квоты закрашен КОРИДОР возможных цен: цена внутри него не определена однозначно.
        Три снимка подряд показывают, как излишки перетекают, а их сумма и потери стоят на месте.</li>
    <li>В сюжете внешних эффектов полей издержек больше нет. MSB и MSC живут во «Вводе функций»
        слева, по умолчанию выключены и равны частным кривым; кривые D и S не переименованы.</li>
    <li>«Было&nbsp;→&nbsp;стало» у пола и потолка показывает исходное равновесие пунктиром.</li>
  </ul>
</div>
${groups.map(g => `<h2>${esc(g.name)}</h2>\n<div class="grid">${cards(g.items)}</div>`).join('\n')}
${errs.length ? '<h2>Ошибки страницы при съёмке</h2><pre>' + esc(errs.join('\n')) + '</pre>' : ''}
</body></html>`;

fs.writeFileSync(path.join(OUT, 'index.html'), html);
console.log('\nконтактный лист: ' + path.join(OUT, 'index.html'));
console.log('снимков: ' + PLAN.length);
if (errs.length) console.log('ошибки страницы: ' + errs.length + '\n' + errs.join('\n'));
