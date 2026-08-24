/* ФАЗА 4.2 сессии 22.08 — ЖИВОЙ ЦИКЛ ПО БЛОКУ «КПВ И КТВ».

   Проверяет ровно то, что делает человек, и НИ ОДНОГО лишнего движения:
   щелчок по полю, набор с клавиатуры, кнопка «Построить», протяжка ручки
   ползунка мышью. Выделять содержимое перед набором ЗАПРЕЩЕНО — именно
   лишний Cmd+A обошёл настоящий дефект в прошлой сессии; замену прежней
   записи обязана делать сама страница.

   Сравниваем только ВИДИМЫЕ линии кривых: непрозрачная обводка, без заливки,
   без пометки «не выгружать». Полосы захвата, легенды и заливки к геометрии
   кривой отношения не имеют, и на них уже обжигались дважды.

   ⚠️ Неизвестный ключ сцены калькулятор молча уводит на «Спрос и предложение».
   Ключи сверяются со SCENE_ROUTE ДО открытия — иначе прибор отчитается о
   сцене, которую ни разу не видел.

   Запуск: node scripts/calc2_ppfparam_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8710';
const OUT  = process.argv[3] || 'reports/calc2_22aug/ppfparam.json';
const BASE = `http://127.0.0.1:${PORT}`;

// поле · кнопка · где лежит формула в состоянии
const MODELS = [
  { key: 'ppf',        inp: 'inp-ppf',      btn: 'btn-ppf-apply',    state: 'ppfFormula'  },
  { key: 'ppfsum',     inp: 'inp-ppfsum-0', btn: 'btn-ppfsum-apply', state: 'ppf1'        },
  { key: 'trade',      inp: 'inp-ppft',     btn: 'btn-ppft-apply',   state: 'ppftFormula' },
  { key: 'tradeprice', inp: 'inp-tb1',      btn: 'btn-tb-apply',     state: 'tbF1'        },
];
const TYPED = 'y=100-a*x';

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

// Геометрия видимых линий — то, что видит глаз.
const LINES = () => [...document.querySelectorAll('#chart path')].filter(p => {
  if (p.getAttribute('data-skip-export') === '1') return false;
  const cs = getComputedStyle(p);
  if (cs.stroke === 'none' || parseFloat(cs.strokeOpacity || '1') < 0.9) return false;
  if (cs.fill && cs.fill !== 'none') return false;
  return true;
}).map(p => (p.getAttribute('d') || '').replace(/-?\d+\.\d+/g, m => (+m).toFixed(1))).join('|');

async function openScene(page, key) {
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function' && typeof STATE === 'object',
                             null, { timeout: 20000 });
  const known = await page.evaluate(() => Object.keys(SCENE_ROUTE || {}));
  if (!known.includes(key)) throw new Error('НЕТ ТАКОГО КЛЮЧА СЦЕНЫ: ' + key);
  await page.evaluate(k => pickScene(k), key);
  await page.waitForTimeout(1000);
  // Человек раскрывает карточку ввода — только видимые секции.
  await page.evaluate(() => {
    document.querySelectorAll('#tools-panel .section, #params-panel .section').forEach(s => {
      if (s.id && getComputedStyle(s).display !== 'none') openSection(s.id);
    });
  });
  await page.waitForTimeout(700);
}

/* ⚠️ ЧЕЛОВЕК ЩЁЛКАЕТ НЕ ПО `input`. Поле формулы устроено так: в ячейке
   `.f-slot` лежат спрятанный `input` (в нём текст для движка), набранная
   формула `.f-typeset` (её и видно в покое) и математическое поле MathLive
   (всплывает по щелчку). Прибор, целившийся в сам `input`, тридцать секунд
   ждал видимости узла, который спрятан по устройству, и объявлял «поля нет».
   Одиннадцатый способ, которым врёт прибор: целиться в носитель значения
   вместо органа, которым работают. Щёлкаем по видимому в ячейке. */
async function clickInto(page, id) {
  const el = await page.$('#' + id);
  if (!el) return { ok: false, why: 'поля нет в разметке' };
  const target = await page.evaluateHandle((id) => {
    const inp = document.getElementById(id);
    const slot = inp.closest('.f-slot') || inp.parentElement;
    const vis = (n) => { if (!n) return false; const r = n.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
    return [slot.querySelector('math-field'), slot.querySelector('.f-typeset'), inp].find(vis) || null;
  }, id);
  const node = target.asElement();
  if (!node) return { ok: false, why: 'в ячейке нет ни одного видимого органа ввода' };
  await node.scrollIntoViewIfNeeded();
  const box = await node.boundingBox();
  if (!box) return { ok: false, why: 'нулевой размер' };
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  // Попадание проверяем по-настоящему: под шапкой сайта щелчок уходил в навигацию.
  const hit = await page.evaluate(([x, y]) => {
    const t = document.elementFromPoint(x, y);
    if (!t) return 'none';
    return t.closest('.f-slot') ? 'slot' : (t.id || t.className || t.tagName);
  }, [x, y]);
  if (hit !== 'slot') return { ok: false, why: 'в этой точке лежит другое: ' + hit };
  await page.mouse.click(x, y);
  await page.waitForTimeout(320);   // математическое поле всплывает и берёт фокус
  return { ok: true };
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(String(e).slice(0, 140)));
  await login(page);

  const report = [];
  for (const m of MODELS) {
    const row = { model: m.key, typed: TYPED };
    try {
      await openScene(page, m.key);

      const click = await clickInto(page, m.inp);
      row.click = click.ok ? 'попал' : ('НЕ ПОПАЛ: ' + click.why);
      if (!click.ok) { report.push(row); continue; }

      // Набор с клавиатуры. Ничего не выделяем и не чистим руками.
      await page.keyboard.type(TYPED, { delay: 22 });
      await page.waitForTimeout(400);
      row.fieldAfterTyping = await page.evaluate(id => document.getElementById(id).value, m.inp);
      row.mathfieldRaw = await page.evaluate(id => {
        const slot = document.getElementById(id).closest('.f-slot');
        const mf = slot && slot.querySelector('math-field');
        return mf ? mf.value : null;
      }, m.inp);

      const btn = await page.$('#' + m.btn);
      if (btn) { await btn.scrollIntoViewIfNeeded(); await btn.click(); }
      else await page.keyboard.press('Enter');
      await page.waitForTimeout(700);

      row.stateFormula = await page.evaluate(k => STATE[k], m.state);
      row.letterKept = /\ba\b/.test(String(row.stateFormula || ''));
      row.sliderExists = await page.evaluate(() => !!(STATE.params && STATE.params.a));
      row.paneError = await page.evaluate(() => {
        const vis = [...document.querySelectorAll('#tools-panel .error')]
          .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
          .map(e => e.textContent.trim()).filter(Boolean);
        return vis.join(' / ');
      });

      if (!row.sliderExists) { row.verdict = 'ползунка буквы нет'; report.push(row); continue; }

      // Протяжка ручки ползунка мышью: a = 1 → a = 10.
      const SHOT = async () => ({
        picture: await page.evaluate(LINES),
        // Окно берём у самих границ плоскости: у mainScales поля называются
        // mx/my, и придуманные наугад x/y роняли замер на всех четырёх моделях.
        window: await page.evaluate(() =>
          [CONFIG.Qmin, CONFIG.Qmax, CONFIG.Pmin, CONFIG.Pmax].map(v => +(+v).toFixed(2)).join(',')),
        numbers: await page.evaluate(() => {
          const b = document.getElementById('info-ppf') || document.querySelector('#params-panel .info');
          return b ? b.textContent.replace(/\s+/g, ' ').trim().slice(0, 200) : '';
        }),
      });
      const shotBefore = await SHOT();
      const before = shotBefore.picture;
      const slider = await page.$('#params-panel input[type=range][data-param="a"], #params-panel input[type=range]');
      let moved = 'нет ручки';
      if (slider) {
        const b = await slider.boundingBox();
        if (b) {
          await page.mouse.move(b.x + b.width * 0.5, b.y + b.height / 2);
          await page.mouse.down();
          await page.mouse.move(b.x + b.width - 2, b.y + b.height / 2, { steps: 12 });
          await page.mouse.up();
          moved = 'протянул';
        }
      }
      await page.waitForTimeout(600);
      row.drag = moved;
      row.aValue = await page.evaluate(() => (STATE.params.a || {}).value);
      const shotAfter = await SHOT();
      const after = shotAfter.picture;
      row.pictureChanged = (before !== after);
      row.windowChanged  = (shotBefore.window !== shotAfter.window);
      row.numbersChanged = (shotBefore.numbers !== shotAfter.numbers);
      row.windowBefore = shotBefore.window;
      row.windowAfter  = shotAfter.window;
      /* Рычаг ОБМАНЫВАЕТ, если поехали окно и числа, а линия стоит: сцена
         подогнала оси под формулу, и на экране всё те же пиксели. Это не то же
         самое, что «молчит», и лечится по-разному. */
      row.verdict = row.pictureChanged ? 'ЖИВОЙ'
                  : ((row.windowChanged || row.numbersChanged) ? 'ОБМАНЫВАЕТ (двигает окно, не кривую)' : 'МОЛЧИТ');
    } catch (e) {
      row.verdict = 'ОШИБКА ПРИБОРА: ' + e.message;
    }
    report.push(row);
  }

  const out = { typed: TYPED, pageErrors, models: report };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), 'utf8');
  report.forEach(r => console.log(
    String(r.model).padEnd(12), '|', String(r.click || '').padEnd(10),
    '| поле:', String(r.fieldAfterTyping || '').padEnd(14),
    '| STATE:', String(r.stateFormula || '').padEnd(14),
    '| a:', String(r.aValue), '|', r.verdict, r.paneError ? ('| отказ: ' + r.paneError) : ''));
  console.log('ошибок страницы:', pageErrors.length, pageErrors.slice(0, 3));
  await browser.close();
})();
