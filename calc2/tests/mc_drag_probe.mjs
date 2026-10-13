/* MC В МОНОПОЛИИ ТЯНЕТСЯ МЫШЬЮ (решение владельца 13.10, Notion …811c…, ADR 0149).

     ./venv313/bin/python manage.py runserver 8099 --noreload --settings=config.settings_check
     node calc2/tests/mc_drag_probe.mjs        # ONLY=АБВГДЕЖ — по разделам

   А. ?m=mono (D = 100 − Q, MC = 20): протяжка линии MC вверх до 40 → в списке «40», ползунок «Сдвиг MC» = 20,
      Qm = 30, Pm = 70; вниз до 0 → Qm = 50, Pm = 50.
   Б. «Отменить» после затишья возвращает MC одним шагом (0 → 40 → 20).
   В. Режим «Точки и площади»: протяжка по линии MC её не двигает, щелчок ставит точку на MC.
   Г. Спрос D мышью не двигается (геометрия и формулы до и после протяжки совпадают).
   Д. Где тянется: mono, mono-nat, mono-d1 — есть полоса; mono-d3, mono-kink, monoexport (у MC нет ползунка
      сдвига) — нет; на сенсорном экране полоса не уже 44 px; узлы полосы не идут в выгрузку (data-skip-export).
   Е. Границы ползунка «Сдвиг MC» одни и те же: обычное открытие, ссылка «Поделиться» после протяжки до 40,
      «Отменить» (карточка …81ef…).
   Ж. «Разбор» «Стандартной монополии» со ставкой говорит о сдвиге MC, а не «кривой предложения S»; у «Налогов
      и субсидий» — прежний текст про S (карточка …8134…).
*/
import { chromium } from 'playwright';
import { keepAnswerOpen, answerShown } from './answer_open.mjs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const ONLY = process.env.ONLY || '';
const want = (s) => !ONLY || ONLY.includes(s);
let bad = 0, total = 0;
function head(s) { console.log('\n=== ' + s + ' ' + '='.repeat(Math.max(0, 62 - s.length))); }
function ok(label, cond, detail) {
  total++; if (!cond) bad++;
  console.log('  ' + (cond ? 'OK  ' : 'FAIL') + ' ' + label + (detail ? '  — ' + detail : ''));
}
const near = (a, b, e) => Math.abs(a - b) <= (e || 0.01);

const browser = await chromium.launch();
/* «Ответ» от 1240 px закрыт по умолчанию (решение 14.10, Notion …81de…, ADR 0150): прибор открывает его,
   как у человека, однажды открывшего «Ответ»; первая проверка — колонка видна (answer_open.mjs). */
keepAnswerOpen(browser);
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));

let _preDone = false;
async function open(p, model) {
  await p.goto(`${BASE}/calc2/?m=${model}`, { waitUntil: 'networkidle' });
  await p.waitForTimeout(1200);
  if (!_preDone) { _preDone = true; ok('предусловие: «Ответ» открыт (#params-panel > .side-inner видна)', await answerShown(p)); }
  if (!(await p.evaluate(() => typeof pickScene === 'function'))) { console.log('calc2 не загрузился'); process.exit(3); }
}
// Точка модели (q; p) → экран.
const toScreen = (p, q, v) => p.evaluate(([q, v]) => {
  const s = document.getElementById('chart'), r = s.getBoundingClientRect(), vb = s.viewBox.baseVal;
  const kx = vb && vb.width ? r.width / vb.width : 1, ky = vb && vb.height ? r.height / vb.height : 1;
  return { x: r.x + sx(q) * kx, y: r.y + sy(v) * ky };
}, [q, v]);
const state = (p) => p.evaluate(() => {
  const mc = STATE.curves.find(c => c.role === 'mc'), d = STATE.curves.find(c => c.role === 'demand');
  const chip = mc && document.querySelector('.pchip[data-pult-box="params-curves"][data-cid="' + mc.id + '"]');
  const sl = chip && chip.querySelector('input[type=range]');
  const row = mc && document.querySelector('.curve-row[data-cid="' + mc.id + '"]');
  const field = row && row.querySelector('input.curve-expr-inp');
  // Видимое поле MathLive — то же значение, что и скрытое под ним.
  const mf = field && field._mf;
  return {
    mc: mc && mc.expr, d: d && d.expr, field: field ? field.value : null, mf: mf ? mf.value : null,
    shift: sl ? +sl.value : null, min: sl ? +sl.min : null, max: sl ? +sl.max : null,
    Qm: STATE.mono && STATE.mono.Qm, Pm: STATE.mono && STATE.mono.Pm,
    marks: (STATE.marks || []).map(m => ({ x: m.x, y: m.y, on: typeof markOnText === 'function' ? markOnText(m) : '' })),
    band: !!document.querySelector('#chart [data-mc-drag]'),
  };
});
// Протяжка линии MC от уровня a до уровня b при Q = q.
async function dragMc(p, a, b, q) {
  const s = await toScreen(p, q || 60, a), e = await toScreen(p, q || 60, b);
  await p.mouse.move(s.x, s.y);
  await p.mouse.down();
  await p.mouse.move(s.x, (s.y + e.y) / 2, { steps: 6 });
  await p.mouse.move(e.x, e.y, { steps: 6 });
  await p.mouse.up();
  await p.waitForTimeout(500);
}

if (want('А') || want('Б')) {
  await open(page, 'mono');
  const s0 = await state(page);
  ok('mono: старт D = 100 − Q, MC = 20, полоса захвата MC есть', /^100\s*-\s*Q$/.test(s0.d) && s0.mc === '20' && s0.band, JSON.stringify(s0));
  const cur = await page.evaluate(() => { const b = document.querySelector('#chart [data-mc-drag]'); return b && getComputedStyle(b).cursor; });
  ok('курсор над полосой — grab', cur === 'grab', cur);
  if (want('А')) head('А. Протяжка MC вверх и вниз');
  await dragMc(page, 20, 40);
  const s1 = await state(page);
  ok('MC протянута до 40: в списке «40»', s1.mc === '40' && s1.field === '40' && (s1.mf == null || s1.mf === '40'), `expr ${s1.mc}, поле ${s1.field}, MathLive ${s1.mf}`);
  ok('ползунок «Сдвиг MC» = 20', near(s1.shift, 20), String(s1.shift));
  ok('Qm = 30, Pm = 70', near(s1.Qm, 30, 0.05) && near(s1.Pm, 70, 0.05), `Qm ${s1.Qm}, Pm ${s1.Pm}`);
  ok('спрос D не тронут', s1.d === s0.d, s1.d);
  await page.waitForTimeout(500);      // затишье: шаг истории
  await dragMc(page, 40, 0);
  const s2 = await state(page);
  ok('MC протянута до 0: Qm = 50, Pm = 50', s2.mc === '0' && near(s2.Qm, 50, 0.05) && near(s2.Pm, 50, 0.05), `MC ${s2.mc}, Qm ${s2.Qm}, Pm ${s2.Pm}`);
  ok('ползунок «Сдвиг MC» = −20', near(s2.shift, -20), String(s2.shift));
  if (want('Б')) {
    head('Б. «Отменить» после затишья');
    await page.waitForTimeout(600);
    await page.click('#btn-undo');
    await page.waitForTimeout(500);
    const u1 = await state(page);
    ok('«Отменить»: MC снова 40 одним шагом', u1.mc === '40' && near(u1.shift, 20), `MC ${u1.mc}, сдвиг ${u1.shift}`);
    await page.click('#btn-undo');
    await page.waitForTimeout(500);
    const u2 = await state(page);
    ok('ещё «Отменить»: MC снова 20', u2.mc === '20' && near(u2.shift, 0), `MC ${u2.mc}, сдвиг ${u2.shift}`);
  }
}

if (want('В')) {
  head('В. Режим «Точки и площади»: MC не тянется, щелчок ставит точку');
  await open(page, 'mono');
  await page.evaluate(() => setPtsMode(true));
  await page.waitForTimeout(300);
  const b0 = await state(page);
  ok('в режиме полосы захвата нет', !b0.band);
  await dragMc(page, 20, 45, 70);
  const s1 = await state(page);
  ok('протяжка по MC её не двигает', s1.mc === '20' && near(s1.shift, 0), `MC ${s1.mc}`);
  const n0 = s1.marks.length;
  const pt = await toScreen(page, 70, 20);
  await page.mouse.click(pt.x, pt.y);
  await page.waitForTimeout(400);
  const s2 = await state(page);
  const mk = s2.marks[s2.marks.length - 1] || {};
  ok('щелчок по MC ставит точку на MC', s2.marks.length === n0 + 1 && near(mk.y, 20, 0.6), `точек ${n0} → ${s2.marks.length}, ${JSON.stringify(mk)}`);
  await page.evaluate(() => setPtsMode(false));
  await page.waitForTimeout(300);
  ok('после выхода из режима полоса снова есть', (await state(page)).band);
}

if (want('Г')) {
  head('Г. Спрос D мышью не двигается');
  await open(page, 'mono');
  const shot = () => page.evaluate(() => {
    const d = STATE.curves.find(c => c.role === 'demand');
    const p = [...document.querySelectorAll('#chart path[data-hit="' + d.id + '"]')][0];
    return { d: d.expr, path: p ? p.getAttribute('d') : null };
  });
  const before = await shot();
  // Точка на D, где нет MC: Q = 30, P = 70.
  const s = await toScreen(page, 30, 70);
  const hit = await page.evaluate(([x, y]) => { const e = document.elementFromPoint(x, y); return e && (e.getAttribute('data-hit-name') || e.getAttribute('data-mc-drag') || e.tagName); }, [s.x, s.y]);
  await page.mouse.move(s.x, s.y); await page.mouse.down();
  await page.mouse.move(s.x, s.y + 80, { steps: 10 }); await page.mouse.up();
  await page.waitForTimeout(500);
  const after = await shot();
  ok('щелчок попадает в полосу D', hit === 'D', String(hit));
  ok('после протяжки D формула и линия те же', before.d === after.d && before.path === after.path, `${before.d} → ${after.d}`);
}

if (want('Д')) {
  head('Д. Где MC тянется');
  for (const [m, yes] of [['mono', 1], ['mono-nat', 1], ['mono-d1', 1], ['mono-d3', 0], ['mono-kink', 0], ['monoexport', 0], ['sd', 0], ['taxes', 0]]) {
    await open(page, m);
    const r = await page.evaluate(() => {
      const b = document.querySelector('#chart [data-mc-drag]');
      const g = b && b.closest('[data-skip-export]');
      return { band: !!b, skip: !!(b && b.getAttribute('data-skip-export') === '1' && g) };
    });
    ok(`${m}: полоса захвата MC ${yes ? 'есть' : 'нет'}`, r.band === !!yes, JSON.stringify(r));
    if (yes) ok(`${m}: узлы полосы помечены data-skip-export`, r.skip);
  }
  // MC, сдвинутая мышью в mono-nat, — та же дверь: ползунок едет следом.
  await open(page, 'mono-nat');
  await dragMc(page, 20, 30, 40);
  const n = await state(page);
  ok('mono-nat: MC протянута до 30, ползунок = 10', n.mc === '30' && near(n.shift, 10), `MC ${n.mc}, сдвиг ${n.shift}`);
  const tctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const tp = await tctx.newPage();
  await open(tp, 'mono');
  const w = await tp.evaluate(() => { const b = document.querySelector('#chart [data-mc-drag]'); return b ? +b.getAttribute('stroke-width') : 0; });
  ok('телефон: полоса захвата MC не уже 44 px', w >= 44, w + ' px');
  await tctx.close();
}

if (want('Е')) {
  head('Е. Границы ползунка «Сдвиг MC»: открытие, ссылка, «Отменить»');
  await open(page, 'mono');
  const s0 = await state(page);
  await dragMc(page, 20, 40);
  const s1 = await state(page);
  const link = await page.evaluate(async () => shareLinkOf());
  const p2 = await ctx.newPage();
  await p2.goto(link, { waitUntil: 'networkidle' });
  await p2.waitForTimeout(1500);
  const s2 = await state(p2);
  await p2.close();
  ok('обычное открытие: границы −50…50', s0.min === -50 && s0.max === 50, `${s0.min}…${s0.max}`);
  ok('после протяжки до 40: границы те же', s1.min === s0.min && s1.max === s0.max, `${s1.min}…${s1.max}`);
  ok('ссылка «Поделиться»: «Сдвиг MC» = 20, границы те же', near(s2.shift, 20) && s2.min === s0.min && s2.max === s0.max, `сдвиг ${s2.shift}, ${s2.min}…${s2.max}`);
  await page.waitForTimeout(600);
  await page.click('#btn-undo');
  await page.waitForTimeout(500);
  const s3 = await state(page);
  ok('«Отменить»: MC 20, границы те же', s3.mc === '20' && s3.min === s0.min && s3.max === s0.max, `MC ${s3.mc}, ${s3.min}…${s3.max}`);
}

if (want('Ж')) {
  head('Ж. «Разбор» про налог в монополии');
  const exText = async (model) => {
    await open(page, model);
    await page.evaluate(() => { const s = document.querySelector('#sec-tax input[type=range]'); s.value = 20; s.dispatchEvent(new Event('input', { bubbles: true })); });
    await page.waitForTimeout(800);
    return page.evaluate(() => {
      const c = document.getElementById('ex-body').cloneNode(true);
      c.querySelectorAll('.katex-mathml').forEach(x => x.remove());
      return c.textContent.replace(/\s+/g, ' ');
    });
  };
  const m = await exText('mono');
  ok('mono со ставкой: абзац про сдвиг MC («MC + t»)', /Потоварный налог на производителя: предельные издержки MC сдвигаются вверх/.test(m) && /MC \+ t/.test(m), m.slice(0, 140));
  ok('mono: нет «кривая предложения S»', !/кривая предложения S/.test(m));
  const t = await exText('taxes');
  ok('taxes: прежний текст «кривая предложения S сдвигается»', /кривая предложения S сдвигается вверх/.test(t), t.slice(0, 140));
}

ok('ошибок страницы нет', errs.length === 0, errs.slice(0, 3).join(' | '));
await browser.close();
console.log(`\nИТОГ: ${total - bad} из ${total}` + (bad ? ` — ПРОВАЛОВ ${bad}` : ''));
process.exit(bad ? 1 : 0);
