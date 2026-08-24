// ФАЗА 3. Матрица «кусочная функция × сцена». Только чтение: скрипт открывает
// конструктор кусочной функции ровно так, как это делает человек (справка у
// поля → «Собрать кусочную функцию» → «Поставить в поле»), и возвращает поле
// в исходное состояние.
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const USER = process.env.CALC2_USER || 'admin';
const PASS = process.env.CALC2_PASS || 'admin12345';

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.setViewportSize({ width: 1500, height: 950 });
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.fill('#id_username', USER);
await page.fill('#id_password', PASS);
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(1500);

const scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
const names = await page.$$eval('.scard', els => Object.fromEntries(
  els.map(e => [e.dataset.scene, (e.querySelector('.scard-name') || e).textContent.trim()])));

const rows = [];
for (const key of scenes) {
  await page.evaluate(k => { pickScene(k); setToolsOpen(true); }, key);
  await page.waitForTimeout(400);
  await page.evaluate(k => {
    const fire = (el, t) => el.dispatchEvent(new Event(t, { bubbles: true }));
    if (k === 'm-graph') {
      const inp = document.querySelector('#graph-rows .grow input[type=text]');
      if (inp) { inp.value = 'x^2 - 4'; ['input', 'change'].forEach(t => fire(inp, t));
                 inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); }
    }
    if (k === 'consumer' || k === 'cons-slutsky') {
      const sel = document.getElementById('cons-type');
      if (sel) { sel.value = 'custom'; fire(sel, 'change'); }
    }
    if (k === 'ineq' && typeof setIneqInput === 'function') setIneqInput('formula');
  }, key);
  await page.waitForTimeout(500);

  let res;
  try {
    res = await page.evaluate(async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      const vis = el => !!(el && el.getClientRects().length);
      const commit = (f) => {
        ['input', 'change'].forEach(t => f.dispatchEvent(new Event(t, { bubbles: true })));
        f.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      };
      const shot = () => {
        let s = 0, n = 0, len = 0;
        document.querySelectorAll('#chart path').forEach(p => {
          const d = p.getAttribute('d') || '';
          if (!d) return;
          n++; len += d.length;
          (d.match(/-?\d+(?:\.\d+)?/g) || []).forEach(x => { s += +x; });
        });
        return { paths: n, len, sum: Math.round(s * 1000) / 1000 };
      };
      const same = (a, b) => a.paths === b.paths && a.len === b.len && Math.abs(a.sum - b.sum) < 1e-6;
      const kinks = () => {
        try {
          return keyTargets().filter(p => p.kind === 'kink' || /излом/.test(p.name || '')).length;
        } catch (e) { return -1; }
      };
      const buildBtns = () => [...document.querySelectorAll('#tools-panel button')]
        .filter(b => /Постро/i.test(b.textContent || '') && vis(b));
      const errText = () => [...document.querySelectorAll('.error')].filter(vis)
        .map(e => (e.textContent || '').trim()).filter(Boolean).join(' / ');

      const fields = FORMULA_FIELDS.filter(i => i.isConnected && fieldActive(i) && (i.value || '').trim().length > 1);
      const out = [];
      for (const f of fields) {
        const orig = f.value;
        const rec = { id: f.id, orig };
        try {
          const before = shot();
          // ── Человеческий путь: справка у поля → «Собрать кусочную функцию».
          const wrap = f.closest('.f-wrap') || f.closest('.grow') || f.parentElement;
          const help = wrap && wrap.querySelector('.f-help');
          let opened = false;
          if (help) {
            help.click(); await sleep(220);
            // Вход в конструктор живёт в подвале виртуальной клавиатуры, а у
            // полей без клавиатуры — в списке примеров формул. Смотрим оба.
            const pw = [...document.querySelectorAll('.mkbd.open button, .f-pop.open button, .f-pop button')]
              .find(b => /кусочн/i.test(b.textContent || ''));
            if (pw) { pw.click(); await sleep(320); opened = document.getElementById('pw-modal').classList.contains('open'); }
          }
          rec.viaHelp = opened;
          if (!opened) {
            // Запасной путь: тот же конструктор, но вызванный напрямую.
            openPiecewise(f, (typeof FORMULA_VAR !== 'undefined' && FORMULA_VAR[f.id]) || 'x');
            await sleep(300);
            opened = document.getElementById('pw-modal').classList.contains('open');
          }
          rec.opened = opened;
          if (!opened) { rec.note = 'конструктор не открылся'; out.push(rec); continue; }

          const v = (typeof PW !== 'undefined' && PW.v) || 'x';
          rec.varName = v;
          /* Куски строим ИЗ ФОРМУЛЫ САМОЙ СЦЕНЫ, а стык ставим внутри её
             нынешнего окна. Готовая пара «100 − Q / 80 − 0,5·Q» была бы нечестной
             проверкой: у математических сюжетов окно [−6; 6], и стык в точке 40
             просто не попадал бы на холст — ноль изломов означал бы промах
             проверки, а не поломку сцены.
             Второй кусок — та же кривая с вдвое меньшим наклоном, сшитая в точке
             стыка: F(c) + 0,5·(F(v) − F(c)). Разрыва нет, излом есть ровно один. */
          let w0 = null;
          try { w0 = viewWindow(); } catch (e) {}
          const lo = w0 ? w0.x0 : 0, hi = w0 ? w0.x1 : 100;
          const cut = Math.round((lo + (hi - lo) * 0.4) * 100) / 100;
          rec.cut = cut;
          const body = orig.indexOf('=') >= 0 ? orig.slice(orig.indexOf('=') + 1).trim() : orig.trim();
          /* Буква, которой написана САМА формула сцены. Подставлять вместо неё
             ту, что предлагает конструктор, нельзя: у рынка труда формула идёт
             от L, а конструктор пишет условие от Q — второй кусок тогда до
             символа совпал бы с первым, и проверка мерила бы саму себя. */
          /* freeSymbols здесь не годится: он ищет БУКВЫ-ПАРАМЕТРЫ и как раз
             выбрасывает переменную сцены — на «100 − Q» отдал бы пустой список.
             Берём имена прямо из записи, отбрасывая имена функций. */
          const FN = new Set(['sin','cos','tg','tan','ctg','ln','log','lg','exp','sqrt','abs','min','max','pow','e','pi']);
          const bodyVars = [...new Set((body.match(/[A-Za-z_][A-Za-z0-9_]*/g) || [])
            .filter(w => !FN.has(w.toLowerCase())))];
          rec.bodyVars = bodyVars;
          const mainVar = bodyVars[0] || v;
          rec.mainVar = mainVar;
          rec.constant = bodyVars.length === 0;      // «20» — излома не сделать вовсе
          const atCut = body.replace(new RegExp('(?<![A-Za-z0-9_])' + mainVar + '(?![A-Za-z0-9_])', 'g'), '(' + cut + ')');
          const want = [
            { f: body, a: '', b: String(cut) },
            { f: '0.5*(' + body + ') + 0.5*(' + atCut + ')', a: String(cut), b: '' },
          ];
          const pwRowsEls = [...document.querySelectorAll('#pw-rows .pw-row')];
          rec.rows = pwRowsEls.length;
          pwRowsEls.slice(0, 2).forEach((row, i) => {
            const ins = [...row.querySelectorAll('input[type=text]')];
            const [ff, aa, bb] = [ins[0], row.querySelector('.pw-bound'), ins[ins.length - 1]];
            const set = (el, val) => { if (!el) return; el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); };
            set(ff, want[i].f); set(aa, want[i].a);
            if (bb && bb !== aa) set(bb, want[i].b);
          });
          await sleep(200);
          // Какой буквой конструктор пишет условие — и совпадает ли она с той,
          // которой написана формула поля.
          try { rec.condVar = pwVar(); } catch (e) {}
          rec.varMismatch = !!(rec.condVar && rec.mainVar
                               && rec.condVar.toLowerCase() !== rec.mainVar.toLowerCase());
          rec.preview = ((document.getElementById('pw-preview') || {}).textContent || '').trim().slice(0, 60);
          document.getElementById('pw-apply').click();
          await sleep(300);
          rec.value = f.value;
          rec.accepted = /\?/.test(f.value || '');       // цепочка условий встала в поле
          commit(f); await sleep(320);
          let after = shot();
          rec.drawnNoBtn = !same(before, after) && after.paths > 0;
          rec.btns = buildBtns().map(b => b.id || (b.textContent || '').trim());
          if (!rec.drawnNoBtn && rec.btns.length) {
            buildBtns()[0].click(); await sleep(400);
            after = shot();
            rec.neededBtn = !same(before, after) && after.paths > 0;
          }
          rec.drawn = rec.drawnNoBtn || !!rec.neededBtn;
          rec.paths = after.paths;
          rec.kinks = kinks();
          try {
            const w = viewWindow ? viewWindow() : (STATE.win || null);
            if (w) rec.win = { x0: w.x0, x1: w.x1, y0: w.y0, y1: w.y1 };
          } catch (e) {}
          try {
            rec.keyPts = keyTargets().map(p => ({ x: Math.round(p.x * 100) / 100, k: p.kind, n: (p.name || '').slice(0, 22) })).slice(0, 12);
          } catch (e) {}
          rec.error = errText();
        } catch (e) { rec.crash = String(e.message).slice(0, 90); }
        try { closePiecewise(); } catch (e) {}
        try { f.value = orig; commit(f); } catch (e) {}
        await sleep(160);
        out.push(rec);
      }
      try { redrawAll(); } catch (e) {}
      return { fields: out };
    });
  } catch (e) { res = { error: String(e.message).slice(0, 140) }; }
  rows.push({ key, name: names[key] || key, ...res });
  process.stdout.write('.');
}
process.stdout.write('\n');
writeFileSync(process.env.OUT || 'phase3.json', JSON.stringify({ rows, errors }, null, 1));
console.log('сцен:', rows.length, 'ошибок страницы:', errors.length);
await browser.close();
