/* ФАЗА 1 сессии 21.08. ДОГОВОР О ПАРАМЕТРАХ — ЖИВОЙ ПРОГОН ПО ВСЕМ ПОЛЯМ.

   Чем отличается от прибора 20.08 (`calc2_params_probe.js`): тот считал рычаг
   рабочим, если поменялась картинка в ПИКСЕЛЯХ. Этого мало в обе стороны.

     · Сцена, которая подгоняет оси под свою кривую, при линейной формуле даёт
       БАЙТ В БАЙТ ту же картинку: прямая от перехвата до перехвата всегда
       спанит те же пиксели, меняются только числа на осях. Прибор 20.08
       отчитался «двигает», владелец увидел неподвижную линию — и оба правы.
     · Панельные сюжеты (производство, дискриминация) рисуют в своих системах
       координат, и главные шкалы про них ничего не знают.

   Поэтому меряем ТРИ поверхности сразу и печатаем их порознь:
     picture — видимые линии кривых в пикселях (то, что видит глаз);
     window  — домен осей (Qmin/Qmax/Pmin/Pmax);
     numbers — текст «Ключевых значений» (разбор сцены).
   Рычаг живой, если сдвинулась хоть одна. Рычаг МОЛЧИТ, если не сдвинулась ни
   одна. Рычаг ОБМАНЫВАЕТ, если сдвинулись окно и числа, а картинка нет.

   Запуск: node scripts/calc2_paramlive_probe.js <порт> <файл.json> [сцены,через,запятую] */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8099';
const OUT  = process.argv[3] || 'reports/calc2_paramlive.json';
const BASE = `http://127.0.0.1:${PORT}`;
const MAX_FIELDS = 4;

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

async function openScene(page, key) {
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object',
                             null, { timeout: 20000 });
  await page.evaluate(k => pickScene(k), key);
  await page.waitForTimeout(900);
  await page.evaluate(() => {
    document.querySelectorAll('#tools-panel .section, #params-panel .section, .sb .section')
      .forEach(s => { if (s.id) openSection(s.id); });
    document.querySelectorAll('.fold-btn').forEach(b => {
      if (b.getAttribute('aria-expanded') === 'false') b.click();
    });
  });
  await page.waitForTimeout(650);
}

/* Три поверхности одним снимком. Признак видимой линии тот же, что у прибора
   20.08: непрозрачная обводка, без заливки, не помечена как невыгружаемая. */
const SHOT = () => {
  const round = d => String(d || '').replace(/-?\d+\.\d+/g, m => (+m).toFixed(1));
  const picture = [...document.querySelectorAll('#chart path')].filter(p => {
    if (p.getAttribute('data-skip-export') === '1') return false;
    const c = getComputedStyle(p);
    if (!c.stroke || c.stroke === 'none') return false;
    if (/rgba\((?:\d+,\s*){3}0\)|transparent/.test(c.stroke)) return false;
    if (c.fill && c.fill !== 'none' && !/rgba\((?:\d+,\s*){3}0\)/.test(c.fill)) return false;
    if (parseFloat(c.strokeOpacity || '1') < 0.05) return false;
    return (p.getAttribute('d') || '').length > 12;
  }).map(p => round(p.getAttribute('d'))).join('|');
  /* ⚠️ ПРЯМАЯ КРИВАЯ — ЭТО <line>, А НЕ <path>. Мини-панели дискриминации
     рисуют линейные спросы отрезками, и отпечаток по одним путям объявил
     исправную сцену неподвижной: правка «Рынок 1» меняла и отрезки, и все
     подписи делений, а прибор смотрел мимо. Тот же изъян был у прибора 20.08. */
  const lines = [...document.querySelectorAll('#chart line')].filter(l => {
    if (l.getAttribute('data-skip-export') === '1') return false;
    const c = getComputedStyle(l);
    if (!c.stroke || c.stroke === 'none') return false;
    if (parseFloat(c.strokeOpacity || '1') < 0.05) return false;
    return true;
  }).map(l => ['x1', 'y1', 'x2', 'y2'].map(a => (+l.getAttribute(a)).toFixed(1)).join(',')).join(';');
  const labels = [...document.querySelectorAll('#chart text')]
    .map(t => (t.textContent || '').trim()).join('/');
  const win = [CONFIG.Qmin, CONFIG.Qmax, CONFIG.Pmin, CONFIG.Pmax].map(v => (+v).toFixed(3)).join(',');
  const numbers = [...document.querySelectorAll('#params-panel .stat, .sb .stat, #tools-panel .stat')]
    .map(e => (e.textContent || '').replace(/\s+/g, ' ').trim()).join(' | ');
  /* ⚠️ ГЕОМЕТРИЯ КРИВЫХ И ПОДПИСИ ОСЕЙ СЧИТАЮТСЯ ПОРОЗНЬ. Сложив их в один
     отпечаток, прибор снова начинает врать в свою пользу: сцена, которая
     подгоняет оси под кривую, меняет ЧИСЛА на осях, а сама линия остаётся
     байт в байт — и «картинка изменилась» скрывает ровно ту болезнь, ради
     которой прибор написан. */
  return { curves: picture + '#' + lines, labels, win, numbers };
};

// Вставить букву в формулу (та же логика, что в приборе 20.08 — правило одно).
function withLetter(orig, P) {
  const whole = String(orig || '');
  const eq = whole.search(/(?<![<>=!])=(?!=)/);
  const head = eq >= 0 ? whole.slice(0, eq + 1) : '';
  const s = eq >= 0 ? whole.slice(eq + 1) : whole;
  const put = (text, base) => ({ text: head + text, base });
  let m = s.match(/(?<![\w.])(\d+(?:\.\d+)?)\s*\*/);
  if (m) return put(s.replace(m[0], P + '*'), +m[1]);
  const re = /(?<![\w.\\])([A-Za-z][A-Za-z0-9]?)(?!\s*\()/g;
  let hit;
  while ((hit = re.exec(s)) !== null) {
    const name = hit[1];
    if (name === P) return null;
    if (/^(min|max|abs|log|ln|exp|sqrt|sin|cos|tan|e|pi)$/i.test(name)) continue;
    return put(s.slice(0, hit.index) + P + '*' + s.slice(hit.index), 1);
  }
  const num = s.match(/(?<![\w.])(\d+(?:\.\d+)?)(?![\d.])/);
  if (num) return put(s.replace(num[0], P + '*' + num[1]), 1);
  return null;
}

async function aimAt(page, id, pick) {
  for (let tries = 0; tries < 3; tries++) {
    const g = await page.evaluate(([id, pick]) => {
      const inp = document.getElementById(id);
      if (!inp) return null;
      const wrap = inp.closest('.f-wrap') || inp.parentElement;
      let el = inp;
      if (pick === 'field') {
        const mf = wrap && wrap.querySelector('math-field');
        if (mf && mf.getClientRects().length) el = mf;
      }
      if (!el.getClientRects().length) el = wrap;
      if (!el || !el.getClientRects().length) return null;
      el.scrollIntoView({ block: 'center', inline: 'nearest' });
      const r = el.getBoundingClientRect();
      const x = r.x + r.width / 2, y = r.y + r.height / 2;
      const top = document.elementFromPoint(x, y);
      return { x, y, w: r.width, h: r.height,
               hit: !!(top && (el.contains(top) || top === el || (el.shadowRoot && top === el))) };
    }, [id, pick]);
    if (!g) return null;
    if (g.hit || tries === 2) return g;
    await page.waitForTimeout(150);
  }
  return null;
}

async function aimButton(page, id, rx) {
  return await page.evaluate(([id, rx]) => {
    const inp = document.getElementById(id);
    const sec = inp && inp.closest('.section, .subsec, .field-block, #tools-panel');
    if (!sec) return null;
    const b = [...sec.querySelectorAll('button')].filter(x =>
      x.getClientRects().length && new RegExp(rx).test(x.textContent.trim()));
    if (!b.length) return null;
    b[0].scrollIntoView({ block: 'center' });
    const r = b[0].getBoundingClientRect();
    const x = r.x + r.width / 2, y = r.y + r.height / 2;
    const top = document.elementFromPoint(x, y);
    return { id: b[0].id, x, y, hit: !!(top && b[0].contains(top)) };
  }, [id, rx]);
}

const norm = t => String(t || '').replace(/\s+/g, '').toLowerCase();

/* ⚠️ ФОРМУЛЫ СЦЕН ЛЕЖАТ НЕ ТОЛЬКО В КОРНЕ СОСТОЯНИЯ. Макро держит их в
   STATE.macro[модель].is, и плоский обход по Object.keys(STATE) их не видел:
   шесть макросцен отчитались «буквы нет в состоянии» на исправном коде.
   Обходим до третьего уровня. */
const WALK = `(() => {
  const out = [];
  const seen = new Set();
  const walk = (o, path, depth) => {
    if (!o || depth > 3 || seen.has(o)) return;
    if (typeof o === 'object') seen.add(o);
    Object.keys(o).forEach(k => {
      const v = o[k], p = path ? path + '.' + k : k;
      if (typeof v === 'string') { if (v.length > 1) out.push([p, v]); }
      else if (v && typeof v === 'object' && depth < 3) walk(v, p, depth + 1);
    });
  };
  walk(STATE, '', 0);
  (STATE.curves || []).forEach((c, i) => { if (c && c.expr) out.push(['curves[' + i + '].expr', c.expr]); });
  return out;
})()`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await login(page);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  let scenes = await page.evaluate(() => Object.keys(SCENE_ROUTE));
  const only = process.argv[4];
  if (only) scenes = scenes.filter(k => only.split(',').indexOf(k) >= 0);
  console.log('сцен:', scenes.length);

  const out = {};
  for (const key of scenes) {
    await openScene(page, key);
    const plan = await page.evaluate((MAXF) => {
      const live = (typeof FORMULA_FIELDS !== 'undefined' ? FORMULA_FIELDS : [])
        .filter(i => typeof fieldActive === 'function' && fieldActive(i));
      const filled = live.filter(i => (i.value || '').trim().length > 0);
      const fs = filled.length ? filled : live.slice(0, 1);
      const busy = (typeof sceneReserved === 'function') ? sceneReserved() : new Set();
      const P = ['a', 'k', 'm', 'n', 'z'].find(n => !busy.has(n)) || 'z';
      return { letter: P, total: fs.length,
               ids: fs.slice(0, MAXF).map(i => ({ id: i.id, val: i.value })) };
    }, MAX_FIELDS);

    const rec = { letter: plan.letter, fieldsTotal: plan.total, fields: [] };

    for (const f of plan.ids) {
      const mod = String(f.val || '').trim()
        ? withLetter(f.val, plan.letter)
        : { text: '10 - ' + plan.letter + '*x', base: 1, seeded: true };
      if (!mod) { rec.fields.push({ id: f.id, was: f.val, skip: 'некуда-вставить-букву' }); continue; }
      const row = { id: f.id, was: f.val, want: mod.text };

      await openScene(page, key);

      const stateBefore = await page.evaluate(w => eval(w), WALK);
      const typed = await aimAt(page, f.id, 'field');
      if (!typed || typed.w < 4) { row.input = 'поле не видно'; rec.fields.push(row); continue; }
      if (!typed.hit) { row.input = 'щелчок не попадает в поле'; rec.fields.push(row); continue; }
      await page.mouse.click(typed.x, typed.y);
      await page.waitForTimeout(120);
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
      await page.keyboard.type(mod.text, { delay: 12 });
      await page.waitForTimeout(250);

      let got = await page.evaluate(id => (document.getElementById(id) || {}).value, f.id);
      row.typedInto = got;
      row.typeOk = norm(got) === norm(mod.text);
      if (!row.typeOk) {
        await page.evaluate(([id, t]) => {
          const i = document.getElementById(id);
          if (!i) return;
          i.value = t; i.dispatchEvent(new Event('input', { bubbles: true }));
        }, [f.id, mod.text]);
        await page.waitForTimeout(120);
      }

      const btn = await aimButton(page, f.id, '^Построить');
      if (btn && btn.hit) { row.applyBy = 'кнопка'; await page.mouse.click(btn.x, btn.y); }
      else {
        row.applyBy = 'Enter';
        const back = await aimAt(page, f.id, 'field');
        if (back && back.hit) await page.mouse.click(back.x, back.y);
        await page.keyboard.press('Enter');
      }
      await page.waitForTimeout(500);
      const alive = await page.evaluate(() => typeof STATE === 'object' && !!document.getElementById('chart'))
        .catch(() => false);
      if (!alive) { row.lost = 'страница ушла после применения'; rec.fields.push(row); continue; }

      /* Где осела формула и осталась ли в ней буква. Ищем по ВСЕМУ состоянию:
         сцены держат свои формулы в разных полях, общего реестра нет. */
      /* ⚠️ СРАВНИВАЕМ СОСТОЯНИЕ ДО И ПОСЛЕ, А НЕ ИЩЕМ ПОХОЖЕЕ ПО ВСЕМУ STATE.
         Первая версия объявляла подменой чужое поле, у которого умолчание
         случайно совпало по форме («tbF2 = 100 - 2*X» под набранное
         «100 - a*X»): пять ложных тревог из шести. Подмена — это когда
         ИЗМЕНИВШЕЕСЯ от нашего применения поле держит число там, где набрана
         буква. */
      const after = await page.evaluate(([id, P, want, prev, WALK_SRC]) => { try {
        const n = t => String(t || '').replace(/\s+/g, '').toLowerCase();
        const strings = eval(WALK_SRC);
        const was = new Map(prev);
        const changed = strings.filter(([k, v]) => was.get(k) !== v);
        const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const nw = n(want);
        const subRx = new RegExp('^' + nw.split(P).map(esc).join('(-?\\d+(?:\\.\\d+)?)') + '$');
        return {
          slider: !!(STATE.params && STATE.params[P]),
          fieldNow: (document.getElementById(id) || {}).value,
          changedKeys: changed.map(([k]) => k),
          exact: changed.filter(([, v]) => n(v) === nw).map(([k]) => k),
          anyLetter: changed.filter(([, v]) =>
            new RegExp('(^|[^a-z0-9])' + P + '([^a-z0-9]|$)', 'i').test(n(v))).map(([k]) => k),
          substituted: changed.filter(([, v]) => n(v) !== nw && subRx.test(n(v))).map(([k, v]) => k + '=' + v),
          err: [...document.querySelectorAll('.f-why, #ppf-error, .err, .error')]
                 .filter(e => e.getClientRects().length && e.textContent.trim())
                 .map(e => e.textContent.trim().slice(0, 60)),
        };
        } catch (e) { return { probeError: String(e && e.message).slice(0, 140) }; }
      }, [f.id, plan.letter, mod.text, stateBefore, WALK]);
      Object.assign(row, after);

      if (!after.slider) { row.verdict = 'ползунка нет'; rec.fields.push(row); continue; }

      // Ручку тянем мышью — как человек. Полосу заранее раздвигаем: крайние
      // положения увели бы кривую туда, где её на холсте не видно вовсе.
      /* ⚠️ ЗНАЧЕНИЕ БЕРЁТСЯ РЯДОМ С ПРЕЖНИМ ЧИСЛОМ (урок 20.08). Наугад
         поставленная единица делает у «20 − 0.1·Y» отвесную IS, пересечения с
         LM нет вовсе — и прибор ругается на собственную подстановку. Первая
         версия этого прогона так и объявила «МОЛЧИТ» исправную сцену IS–LM. */
      await page.evaluate(([P, base]) => {
        const p = STATE.params[P];
        /* ⚠️ ШАГ СУЖАЕТСЯ ВМЕСТЕ С ПОЛОСОЙ. Полоса 0.04…0.22 при шаге 0.1
           даёт ручке два положения, и мышь её не сдвигает вовсе: прибор
           объявил «МОЛЧИТ» две исправные строки IS–LM, где молчал он сам. */
        p.min = base * 0.4; p.max = base * 2.2; p.value = base;
        p.step = Math.max((p.max - p.min) / 100, 1e-6);
        const pl = document.getElementById('params-panel'); if (pl) pl._extraSig = PULT_REBUILD;
        if (typeof updatePult === 'function') updatePult();
        redrawAll();
      }, [plan.letter, mod.base]);
      await page.waitForTimeout(400);

      const sl = await page.evaluate((P) => {
        const chips = [...document.querySelectorAll('.pchip-param')];
        for (const c of chips) {
          const t = (c.textContent || '').replace(/\s+/g, '');
          const r = c.querySelector('input[type=range]');
          if (r && r.getClientRects().length && t.indexOf(P) >= 0) {
            r.scrollIntoView({ block: 'center' });
            const b = r.getBoundingClientRect();
            return { x: b.x, y: b.y + b.height / 2, w: b.width };
          }
        }
        return null;
      }, plan.letter);
      if (!sl) { row.verdict = 'ползунок не виден'; rec.fields.push(row); continue; }

      const before = await page.evaluate(SHOT);
      const vBefore = await page.evaluate(P => STATE.params[P].value, plan.letter);
      await page.mouse.move(sl.x + sl.w * 0.5, sl.y);
      await page.mouse.down();
      await page.mouse.move(sl.x + sl.w * 0.85, sl.y, { steps: 8 });
      await page.mouse.up();
      await page.waitForTimeout(650);
      const vAfter = await page.evaluate(P => STATE.params[P].value, plan.letter);
      const shot = await page.evaluate(SHOT);

      row.value = vBefore + '→' + vAfter;
      row.dragMovedHandle = (vBefore !== vAfter);
      row.curves  = (before.curves !== shot.curves);
      row.labels  = (before.labels !== shot.labels);
      row.window  = (before.win !== shot.win);
      row.numbers = (before.numbers !== shot.numbers);
      row.verdict = (!row.curves && !row.labels && !row.window && !row.numbers) ? 'МОЛЧИТ'
                  : (!row.curves ? 'кривая не шелохнулась' : 'живой');
      rec.fields.push(row);
    }
    out[key] = rec;
    process.stdout.write('.');
  }
  console.log('');
  fs.writeFileSync(OUT, JSON.stringify({ scenes: out, pageErrors: errs }, null, 1), 'utf8');
  await browser.close();
  console.log('записано:', OUT, '· ошибок страницы:', errs.length);
})();
