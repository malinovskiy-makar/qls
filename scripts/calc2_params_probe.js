/* ФАЗА 1 сессии 20.08. ЖИВАЯ ПРОВЕРКА ПАРАМЕТРОВ ВО ВСЕХ СЦЕНАХ.

   Урок, ради которого прибор переписан: проверка, которая ставит значение
   параметра присваиванием (`p.value = 1.6; redrawAll()`), доказывает только то,
   что рисовальщик читает STATE. Человек до STATE не дотягивается — он щёлкает
   по полю, набирает формулу клавиатурой, жмёт «Построить» и тащит ручку
   ползунка мышью. Ровно этот путь здесь и проходится.

   Что меряется на каждом поле формулы каждой сцены:
     1. набор с клавиатуры доехал до поля без искажений (MathLive посередине);
     2. применение тем же органом, каким применяет человек (кнопка или Enter);
     3. появился ли ползунок для буквы;
     4. настоящее перетаскивание ручки ползунка мышью двигает кривую;
     5. осталась ли буква в том месте состояния, где сцена держит формулу.

   ⚠️ Сравниваются ТОЛЬКО видимые линии кривых: полосы захвата, заливки
   областей и вспомогательные пути из отпечатка исключены. Иначе «изменилось»
   даёт подвижка дорожки захвата, а человек видит неподвижную кривую.

   Запуск: node scripts/calc2_params_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8701';
const OUT  = process.argv[3] || 'reports/calc2_params_sweep.json';
const BASE = `http://127.0.0.1:${PORT}`;
const MAX_FIELDS = 4;          // больше на сцену не встречается; если встретится — пометим

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
  // Карточки панелей закрыты, а поля формул собираются лениво и только когда видны.
  await page.evaluate(() => {
    document.querySelectorAll('#tools-panel .section, #params-panel .section, .sb .section')
      .forEach(s => { if (s.id) openSection(s.id); });
    document.querySelectorAll('.fold-btn').forEach(b => {
      if (b.getAttribute('aria-expanded') === 'false') b.click();
    });
  });
  await page.waitForTimeout(650);
}

/* Отпечаток видимых линий: путь с настоящей обводкой, без заливки, не помеченный
   как невыгружаемый. Округление до десятой пикселя гасит дрожь численных методов. */
const CURVE_SHOT = () => {
  const round = d => String(d || '').replace(/-?\d+\.\d+/g, m => (+m).toFixed(1));
  return [...document.querySelectorAll('#chart path')].filter(p => {
    if (p.getAttribute('data-skip-export') === '1') return false;
    const c = getComputedStyle(p);
    if (!c.stroke || c.stroke === 'none') return false;
    if (/rgba\((?:\d+,\s*){3}0\)|transparent/.test(c.stroke)) return false;
    if (c.fill && c.fill !== 'none' && !/rgba\((?:\d+,\s*){3}0\)/.test(c.fill)) return false;
    if (parseFloat(c.strokeOpacity || '1') < 0.05) return false;
    return (p.getAttribute('d') || '').length > 12;
  }).map(p => round(p.getAttribute('d'))).join('|');
};

/* Собрать формулу с буквой. Два случая, и у каждого своё естественное значение
   буквы: буква ВМЕСТО множителя наследует его число, буква ПЕРЕД переменной
   начинает с единицы. Наугад поставленная единица у «20 − 0.1·Y» даёт отвесную
   IS, пересечения с LM нет, и прибор ругался бы на собственную подстановку. */
function withLetter(orig, P) {
  const whole = String(orig || '');
  /* ⚠️ Буква ставится в ПРАВУЮ часть уравнения. Первая версия прибора писала
     «a*y = 100 - x» — вырожденный случай, которого человек не набирает: буква
     умножает саму ось. Настоящее воспроизведение владельца — «y = 100 - a*x». */
  const eq = whole.search(/(?<![<>=!])=(?!=)/);
  const head = eq >= 0 ? whole.slice(0, eq + 1) : '';
  const s = eq >= 0 ? whole.slice(eq + 1) : whole;
  const put = (text, base) => ({ text: head + text, base });

  let m = s.match(/(?<![\w.])(\d+(?:\.\d+)?)\s*\*/);
  if (m) return put(s.replace(m[0], P + '*'), +m[1]);
  // Перед первой переменной, стоящей отдельным словом (не именем функции).
  const re = /(?<![\w.\\])([A-Za-z][A-Za-z0-9]?)(?!\s*\()/g;
  let hit;
  while ((hit = re.exec(s)) !== null) {
    const name = hit[1];
    if (name === P) return null;                       // буква уже есть
    if (/^(min|max|abs|log|ln|exp|sqrt|sin|cos|tan|e|pi)$/i.test(name)) continue;
    return put(s.slice(0, hit.index) + P + '*' + s.slice(hit.index), 1);
  }
  // Чисто числовое поле («20» у MC): буква становится множителем этого числа.
  const num = s.match(/(?<![\w.])(\d+(?:\.\d+)?)(?![\d.])/);
  if (num) return put(s.replace(num[0], P + '*' + num[1]), 1);
  return null;
}


/* ⚠️ ПРИБОР ОБЯЗАН ЩЁЛКАТЬ ПО ТОМУ, ВО ЧТО ЦЕЛИТСЯ. Панель прокручивается, и
   поле формулы легко оказывается под шапкой сайта: первый прогон щёлкнул по
   ссылке «Статистика» на координатах поля и увёл страницу с калькулятора,
   отчитавшись «поле не приняло набор». Поэтому перед каждым щелчком элемент
   прокручивается в середину окна, а попадание проверяется elementFromPoint. */
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

// Щелчок по видимой кнопке внутри секции поля — с той же проверкой попадания.
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
      /* Сцена без единой заполненной формулы («Построение графиков» открывается
         пустым холстом) всё равно обязана держать договор: там пробуют пустое
         поле ввода кривой, вписывая в него формулу целиком. */
      const filled = live.filter(i => (i.value || '').trim().length > 0);
      const fs = filled.length ? filled : live.slice(0, 1);
      const busy = (typeof sceneReserved === 'function') ? sceneReserved() : new Set();
      const P = ['a', 'k', 'm', 'n', 'z'].find(n => !busy.has(n)) || 'z';
      return { letter: P, total: fs.length,
               ids: fs.slice(0, MAXF).map(i => ({ id: i.id, val: i.value })) };
    }, MAX_FIELDS);

    const rec = { letter: plan.letter, fieldsTotal: plan.total, capped: plan.total > MAX_FIELDS, fields: [] };

    for (const f of plan.ids) {
      const mod = String(f.val || '').trim()
        ? withLetter(f.val, plan.letter)
        : { text: '10 - ' + plan.letter + '*x', base: 1, seeded: true };
      if (!mod) { rec.fields.push({ id: f.id, was: f.val, skip: 'некуда-вставить-букву' }); continue; }
      const row = { id: f.id, was: f.val, want: mod.text, base: mod.base };
      if (mod.seeded) row.seeded = true;

      await openScene(page, key);          // каждое поле — с чистой сцены

      // 1. НАБОР С КЛАВИАТУРЫ в видимое поле MathLive.
      const typed = await aimAt(page, f.id, 'field');
      if (!typed || typed.w < 4) { row.input = 'поле не видно'; rec.fields.push(row); continue; }
      if (!typed.hit) { row.input = 'щелчок не попадает в поле'; rec.fields.push(row); continue; }

      await page.mouse.click(typed.x, typed.y);
      await page.waitForTimeout(120);
      /* ⚠️ Выделение НЕ гасим отдельным Backspace: пустая строка в карточке
         кривой означает «убрать кривую», строка списка исчезает вместе с полем,
         и дальше прибор мерил бы пустоту. Набор поверх выделения заменяет текст
         тем же одним действием, каким его заменяет человек. */
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
      await page.keyboard.type(mod.text, { delay: 12 });
      await page.waitForTimeout(250);

      let got = await page.evaluate(id => (document.getElementById(id) || {}).value, f.id);
      row.typedInto = got;
      row.typeOk = norm(got) === norm(mod.text);
      if (!row.typeOk) {
        // Набор искажён посредником — честно помечаем и ставим текст напрямую,
        // чтобы проверить остальную цепочку, а не бросать поле совсем.
        await page.evaluate(([id, t]) => {
          const i = document.getElementById(id);
          if (!i) return;
          i.value = t; i.dispatchEvent(new Event('input', { bubbles: true }));
        }, [f.id, mod.text]);
        await page.waitForTimeout(120);
      }

      // 2. ПРИМЕНЕНИЕ ТЕМ ЖЕ ОРГАНОМ: видимая кнопка «Построить» рядом, иначе Enter.
      const btn = await aimButton(page, f.id, '^Построить');
      if (btn && btn.hit) { row.applyBy = 'кнопка ' + (btn.id || '?'); await page.mouse.click(btn.x, btn.y); }
      else {
        row.applyBy = btn ? 'Enter (кнопка перекрыта)' : 'Enter';
        // Строка списка могла пересобраться на вводе: возвращаем указатель в поле.
        const back = await aimAt(page, f.id, 'field');
        if (back && back.hit) await page.mouse.click(back.x, back.y);
        await page.keyboard.press('Enter');
      }
      await page.waitForTimeout(500);
      // Enter в чужом фокусе способен увести страницу: тогда замер бессмыслен.
      const alive = await page.evaluate(() => typeof STATE === 'object' && !!document.getElementById('chart'))
        .catch(() => false);
      if (!alive) { row.lost = 'страница ушла после применения'; rec.fields.push(row); continue; }

      // 3. Появился ли ползунок И где осела формула.
      const after = await page.evaluate(([id, P, want, base]) => { try {
        const n = t => String(t || '').replace(/\s+/g, '').toLowerCase();
        const strings = [];
        Object.keys(STATE).forEach(k => {
          const v = STATE[k];
          if (typeof v === 'string' && v.length > 1) strings.push([k, v]);
        });
        (STATE.curves || []).forEach((c, i) => { if (c && c.expr) strings.push(['curves[' + i + '].expr', c.expr]); });
        const holds = strings.filter(([, v]) => n(v).indexOf(P) >= 0 && n(v) === n(want)).map(([k]) => k);
        const near  = strings.filter(([, v]) => n(v).indexOf(P + '*') >= 0).map(([k]) => k);
        return {
          slider: !!(STATE.params && STATE.params[P]),
          fieldNow: (document.getElementById(id) || {}).value,
          stateHolds: holds, stateAnyWithLetter: near,
          err: [...document.querySelectorAll('.f-why, #ppf-error, .err, .error')]
                 .filter(e => e.getClientRects().length && e.textContent.trim())
                 .map(e => e.textContent.trim().slice(0, 60)),
        };
        } catch (e) { return { slider: null, probeError: String(e && e.message).slice(0, 120) }; }
      }, [f.id, plan.letter, mod.text, mod.base]);
      Object.assign(row, after);

      if (!after.slider) { row.moves = null; rec.fields.push(row); continue; }

      // 4. НАСТОЯЩЕЕ ПЕРЕТАСКИВАНИЕ РУЧКИ ПОЛЗУНКА МЫШЬЮ.
      // Полосу заранее раздвигаем вокруг естественного значения — иначе крайние
      // положения ручки уводят кривую туда, где её на холсте не видно вовсе.
      await page.evaluate(([P, base]) => {
        const p = STATE.params[P];
        p.min = Math.min(p.min, base * 0.4); p.max = Math.max(p.max, base * 2.2);
        p.value = base;
        const pl = document.getElementById('params-panel'); if (pl) pl._extraSig = PULT_REBUILD;
        if (typeof updatePult === 'function') updatePult();
        redrawAll();
      }, [plan.letter, mod.base]);
      await page.waitForTimeout(350);

      const sl = await page.evaluate((P) => {
        const chips = [...document.querySelectorAll('.pchip-param')];
        for (const c of chips) {
          const t = (c.textContent || '').replace(/\s+/g, '');
          const r = c.querySelector('input[type=range]');
          if (r && r.getClientRects().length && t.indexOf(P) >= 0) {
            const b = r.getBoundingClientRect();
            return { x: b.x, y: b.y + b.height / 2, w: b.width, val: r.value };
          }
        }
        return null;
      }, plan.letter);
      if (!sl) { row.moves = null; row.sliderSeen = false; rec.fields.push(row); continue; }
      row.sliderSeen = true;

      const before = await page.evaluate(CURVE_SHOT);
      const vBefore = await page.evaluate(P => STATE.params[P].value, plan.letter);
      // Ручка стоит там, где стоит; тянем её мышью в правую четверть дорожки.
      await page.mouse.move(sl.x + sl.w * 0.5, sl.y);
      await page.mouse.down();
      await page.mouse.move(sl.x + sl.w * 0.78, sl.y, { steps: 8 });
      await page.mouse.up();
      await page.waitForTimeout(600);
      const vAfter = await page.evaluate(P => STATE.params[P].value, plan.letter);
      const afterShot = await page.evaluate(CURVE_SHOT);

      row.dragChangedValue = (vBefore !== vAfter);
      row.valueBefore = vBefore; row.valueAfter = vAfter;
      row.moves = (before !== afterShot);
      row.curvesInShot = before ? before.split('|').length : 0;
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
