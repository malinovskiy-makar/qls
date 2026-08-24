/* Фаза 11(а) — где кусочная действительно не рисуется.
   Общий обзор (piecewise_matrix.mjs) даёт 49 полей из 67, но 14 из
   18 «непрошедших» непрошедшие по делу: либо поле держит ЧИСЛО (излома не
   сделать вовсе), либо это MSB, выключенная флажком по умолчанию.
   Здесь проверяются четыре настоящих кандидата и MSB с включённым флажком.
     node calc2/tests/night2_phase11a_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1500, height: 950 } })).newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', 'admin'); await page.fill('#id_password', 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

/* ⚠️ ТОЧКА СТЫКА ЗАДАЁТСЯ РУКАМИ, А НЕ ОТ ОКНА ГРАФИКА.
   Общий обзор берёт стык на 40 % ширины окна по X — и для трёх из этих полей
   промахивается мимо самой кривой: у «Неравенства доходов» кривая Лоренца
   живёт на p ∈ [0; 1], а окно 0…100; у «Денежного рынка» формула написана по
   ставке i (это вертикальная ось, 0…50), а окно по X идёт до 250; у «Сложения
   КПВ» вторая КПВ 60 − 3X упирается в ось уже при X = 20. Стык за пределами
   кривой ничего не меняет на картинке — и обзор объявлял поле сломанным,
   хотя мерил не то. */
const CASES = [
  { scene: 'ppfsum', id: 'inp-ppfsum-1', cut: 8, pre: '' },
  { scene: 'mono-d3', id: 'inp-d3-2', cut: 15, pre: '' },
  { scene: 'money', id: 'ma-md', cut: 20, pre: '' },
  { scene: 'ineq', id: 'ineq-formula', cut: 0.4, pre: "if (typeof setIneqInput === 'function') setIneqInput('formula');" },
  { scene: 'ext', id: 'inp-msb', cut: 40, pre: "var c=document.getElementById('chk-msb'); if(c && !c.checked){c.click();}" },
  /* Поля, ДЕРЖАЩИЕ ЧИСЛО (MC = 20). Общий обзор строит второй кусок как
     полусумму первого с самим собой — у константы это она же, и картинка
     честно не меняется. Здесь второй кусок наклонный, излом настоящий. */
  { scene: 'mono', id: 'curve-expr-2', cut: 40, pre: '' },
  { scene: 'mono-kink', id: 'inp-kink-mc', cut: 40, pre: '' },
  { scene: 'mono-d3', id: 'inp-d3-mc', cut: 40, pre: '' },
  { scene: 'monoexport', id: 'inp-d3-2', cut: 25, pre: '' },
  { scene: 'labor', id: 'inp-msb', cut: 48, pre: "var c=document.getElementById('chk-msb'); if(c && !c.checked){c.click();}" },
];
const out = {};
for (const c of CASES) {
  out[c.scene + ' / ' + c.id] = await page.evaluate(async (cs) => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    resetSceneMemory(); pickScene(cs.scene); setToolsOpen(true);
    await sleep(500);
    if (cs.pre) { (new Function(cs.pre))(); await sleep(400); }
    const f = document.getElementById(cs.id);
    if (!f) return { note: 'поля нет' };
    const shot = () => { let s = 0, n = 0, len = 0;
      document.querySelectorAll('#chart path').forEach(p => { const d = p.getAttribute('d') || '';
        if (!d) return; n++; len += d.length; (d.match(/-?\d+(?:\.\d+)?/g) || []).forEach(x => { s += +x; }); });
      return { paths: n, len, sum: Math.round(s * 1000) / 1000 }; };
    const same = (a, b) => a.paths === b.paths && a.len === b.len && Math.abs(a.sum - b.sum) < 1e-6;
    const kinks = () => { try { return keyTargets().filter(p => p.kind === 'kink' || /излом/.test(p.name || '')).length; } catch (e) { return -1; } };
    const errText = () => [...document.querySelectorAll('.error')]
      .filter(e => e.getClientRects().length).map(e => (e.textContent || '').trim()).filter(Boolean).join(' / ');
    const orig = f.value;
    const before = shot(), kBefore = kinks();
    // Заведомо НЕвырожденная кусочная: второй кусок сшит в точке стыка, но
    // с другим наклоном — излом есть даже если поле держало число.
    const cut = cs.cut;
    const body = orig.indexOf('=') >= 0 ? orig.slice(orig.indexOf('=') + 1).trim() : orig.trim();
    const FN = new Set(['sin','cos','tg','tan','ctg','ln','log','lg','exp','sqrt','abs','min','max','pow','e','pi']);
    const vars = [...new Set((body.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []).filter(x => !FN.has(x.toLowerCase())))];
    const v = vars[0] || 'x';
    const atCut = body.replace(new RegExp('(?<![A-Za-z0-9_])' + v + '(?![A-Za-z0-9_])', 'g'), '(' + cut + ')');
    const pfx = orig.indexOf('=') >= 0 ? orig.slice(0, orig.indexOf('=') + 1) + ' ' : '';
    const rec = pfx + '(' + v + ' < ' + cut + ') ? (' + body + ') : ((' + atCut + ') - 0.7*(' + v + ' - ' + cut + '))';
    f.value = rec;
    ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
    f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await sleep(400);
    let after = shot();
    const btn = [...document.querySelectorAll('#tools-panel button')]
      .filter(b => /Постро/i.test(b.textContent || '') && b.getClientRects().length)[0];
    let usedBtn = false;
    if (same(before, after) && btn) { btn.click(); usedBtn = true; await sleep(500); after = shot(); }
    const res = { variable: v, cut, record: rec.slice(0, 110),
      valueInField: (f.value || '').slice(0, 110),
      accepted: /\?/.test(f.value || ''),
      changed: !same(before, after), usedBtn,
      pathsBefore: before.paths, pathsAfter: after.paths,
      kinksBefore: kBefore, kinksAfter: kinks(), error: errText() };
    f.value = orig;
    ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
    f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    return res;
  }, c);
}
console.log(JSON.stringify(out, null, 1));
if (errs.length) console.log('ОШИБКИ: ' + errs.slice(0, 5).join(' | '));
await browser.close();
