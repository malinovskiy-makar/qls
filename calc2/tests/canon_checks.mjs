/* ПРОВЕРКА КАНОНА ДЛЯ /calc2/ — двадцать проверок части 4 DESIGN.md.

   Раннер обходит живые страницы калькулятора в ОБЕИХ темах и печатает результат
   каждой проверки машинно-разбираемым блоком. Решение «зелёный/красный» принимает
   питон-тест `problems/tests/test_design_canon.py`: у него есть словарь ещё не
   закрытых проверок, и он же знает, какая фаза какую строку убирает.

   Запуск руками против живого сервера:
     CALC2_BASE_URL=http://127.0.0.1:8601 CALC2_USER=student1 \
     CALC2_PASS=student12345 node calc2/tests/canon_checks.mjs

   Коды возврата: 0 — обход прошёл, 3 — страница не загрузилась (нет браузера
   или CDN). Красные проверки НЕ роняют раннер: их считает питон.                */
import { chromium } from 'playwright';

const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8601';
const USER = process.env.CALC2_USER || 'student1';
const PASS = process.env.CALC2_PASS || 'student12345';
/* Сцен в продукте 41; для проверки каркаса берём шесть разных по устройству:
   рыночная, вмешательство, монополия с двумя панелями, издержки, две панели
   производной, раздел «Математика». Полный обход всех сцен делает замер
   раскладки, здесь важна ШИРИНА классов элементов, а не число сцен.          */
const SCENES = (process.env.CALC2_CANON_SCENES || 'sd,tax,mono,costs,m-tangent,prod').split(',');
const THEMES = ['light', 'dark'];
const WIDTHS = [360, 560, 760, 1024];

/* ── Общее ───────────────────────────────────────────────────────────────── */

async function login(page) {
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', USER);
    await page.fill('input[name="password"]', PASS);
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
}

/* ⚠️ ЗАМЕР НЕ СМЕЕТ ЗАВИСЕТЬ ОТ ТОГО, ЧТО БЫЛО РАСКРЫТО.

   Все проверки считают только ВИДИМЫЕ элементы (`vis`), а сцена открывается со
   всеми закрытыми карточками. Значит без этого шага потолки храповика были бы
   свойством не кода, а кода плюс состояния экрана: починили нарушение внутри
   свёрнутой карточки — счётчик не шелохнулся, и наоборот.

   Раскрываем ПРИНУДИТЕЛЬНО, а не переводим проверки на разбор исходников:
   восемнадцать правил из двадцати спрашивают ВЫЧИСЛЕННЫЙ стиль (контраст, кегль,
   радиус, тень, размер области касания), а его из текста CSS не вывести: одно и то же
   правило даёт разный цвет в двух темах и разный кегль на четырёх ширинах.

   Скрытое СЦЕНОЙ (`style.display = none` у чужих блоков) остаётся скрытым: это
   не состояние экрана, а состав сцены, и человек его в этой модели не увидит никогда. */
async function expandAll(page) {
  const opened = await page.evaluate(() => {
    if (typeof setToolsOpen === 'function') setToolsOpen(true);
    if (typeof setParamsOpen === 'function') setParamsOpen(true);
    let n = 0;
    document.querySelectorAll('.fold-btn[aria-controls]').forEach(btn => {
      const body = document.getElementById(btn.getAttribute('aria-controls'));
      if (!body) return;
      if (!body.classList.contains('open')) n += 1;
      body.classList.add('open');
      btn.setAttribute('aria-expanded', 'true');
      const card = btn.closest('.section, .side-part');
      if (card) card.classList.add('open-card');
    });
    /* Поля формул собираются лениво (А56): пока карточка была свёрнута, поле
       стояло в очереди и было бы замерено как голое текстовое окошко. */
    if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
    return n;
  });
  await page.waitForTimeout(opened ? 550 : 120);
}

async function openScene(page, key, theme) {
  await page.evaluate((t) => localStorage.setItem('theme', t), theme);
  await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
  await page.waitForFunction(
    () => typeof pickScene === 'function' && typeof STATE === 'object',
    null, { timeout: 25000 });
  await page.evaluate((k) => { pickScene(k); }, key);
  await page.waitForTimeout(650);
  await expandAll(page);
}

/* Копилка находок. У каждой проверки свой ключ; питон читает ровно эти ключи. */
const R = {};
const put = (key, where, what) => {
  const b = (R[key] = R[key] || { n: 0, ex: [] });
  b.n += 1;
  if (b.ex.length < 6) b.ex.push(where + ' · ' + what);
};
const seen = (key) => { R[key] = R[key] || { n: 0, ex: [] }; };

/* ── Проверки, которые целиком живут внутри страницы ──────────────────────
   Одна функция на страницу: браузерных переходов и так много, а разбивать
   обход на двадцать проходов значит умножить время на двадцать.             */
const inPage = (theme) => {
  const out = [];
  const add = (key, what) => out.push([key, what]);
  const vis = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) < 0.05) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0.5 && r.height > 0.5;
  };
  /* ШАПКА САЙТА ИСКЛЮЧЕНА ИЗ ПРОВЕРОК ЯВНО, А НЕ ТИХО.
     `templates/_nav.html` — общий файл платформы, границы работы его не
     касаются. Мимо канона там три вещи: радиусы 7/8/8, границы в половину
     пикселя и логотип (белый текст на акценте, в тёмной теме 3,12:1 при норме
     4,6). Все три — карточка владельцу, а не правка отсюда. */
  const inNav = (el) => !!el.closest('nav, .nav, header, .site-header, #site-nav');
  const px = (s) => {
    if (!s) return null;
    s = String(s).trim();
    const m = /rgba?\(([^)]+)\)/.exec(s);
    if (m) {
      const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    }
    const h = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
    if (!h) return null;
    let v = h[1];
    if (v.length === 3) v = v.split('').map(c => c + c).join('');
    return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16), 1];
  };
  const lum = (c) => {
    const f = (u) => { u /= 255; return u <= 0.03928 ? u / 12.92 : Math.pow((u + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };
  const over = (fg, bg) => {                       // наложение полупрозрачного на фон
    const a = fg[3] == null ? 1 : fg[3];
    return [fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1];
  };
  const bgOf = (el) => {                           // ближайший непрозрачный фон предка
    let e = el;
    while (e && e !== document.documentElement) {
      const c = px(getComputedStyle(e).backgroundColor);
      if (c && (c[3] == null || c[3] > 0.5)) return c;
      e = e.parentElement;
    }
    return px(getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1];
  };
  const name = (el) => (el.tagName.toLowerCase()
    + (el.id ? '#' + el.id : '')
    + (el.className && typeof el.className === 'string'
        ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''));

  const cs0 = getComputedStyle(document.documentElement);
  const accent = px(cs0.getPropertyValue('--accent').trim());
  const all = Array.from(document.querySelectorAll('body *')).filter(vis);

  /* 2. В тёмной теме нет белого текста на акценте. Акцент тёмной темы светлый
     (#FF4D94), и белым по нему выходит около двух с половиной. */
  if (theme === 'dark' && accent) {
    all.forEach(el => {
      if (inNav(el)) return;                       // см. пояснение у inNav
      const c = getComputedStyle(el);
      const bg = px(c.backgroundColor);
      if (!bg || bg[3] < 0.9) return;
      if (Math.abs(bg[0] - accent[0]) + Math.abs(bg[1] - accent[1]) + Math.abs(bg[2] - accent[2]) > 12) return;
      const fg = px(c.color);
      if (!fg) return;
      if (lum(fg) > 0.75 && ratio(fg, bg) < 4.5) add('dark_white_on_accent', name(el) + ' ' + c.color);
    });
  }

  /* 3. Контраст текста: обычный не ниже 4,6, крупный не ниже 3,0. Считаем
     только у элементов с СОБСТВЕННЫМ текстом, иначе один и тот же абзац
     попадёт в отчёт столько раз, сколько над ним обёрток. */
  all.forEach(el => {
    if (inNav(el)) return;                         // см. пояснение у inNav
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3)
      .map(n => n.nodeValue).join('').trim();
    if (own.length < 2) return;
    const c = getComputedStyle(el);
    const fg = px(c.color);
    if (!fg) return;
    const bg = bgOf(el);
    const r = ratio(over(fg, bg), bg);
    const size = parseFloat(c.fontSize) || 13;
    const weight = parseInt(c.fontWeight, 10) || 400;
    const big = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = big ? 3.0 : 4.6;
    if (r < need - 0.005) add('contrast_text', name(el) + ' ' + r.toFixed(2) + ' < ' + need + ' «' + own.slice(0, 24) + '»');
  });

  /* 4. Системный вид органа управления. Канон 3.2: поле и переключатель
     рисуются нами, а не операционной системой. */
  /* ⚠️ У <button> и текстового поля `appearance: auto` стоит ВСЕГДА, даже
     когда элемент перерисован до последнего пикселя: браузер не снимает флаг
     от того, что мы задали фон и рамку. Спрашиваем только те органы, где хром
     ДЕЙСТВИТЕЛЬНО рисует система и разница видна глазом. */
  /* ⚠️ СПИСОК ВЗЯТ У КАНОНА ДОСЛОВНО (правило 6 части 4): список, флажок,
     переключатель, выбор файла. Ползунка в этом списке НЕТ, и статьи о нём в
     каноне тоже нет вовсе — сейчас он системный, крашенный `accent-color`.
     Рисовать свой значит изобрести правило, которого канон не даёт: вопрос
     отложен владельцу, а не решён прибором. */
  Array.from(document.querySelectorAll(
    'select, input[type=checkbox], input[type=radio], input[type=file]'))
    .filter(vis).forEach(el => {
      if (inNav(el)) return;
      const c = getComputedStyle(el);
      const app = c.appearance || c.webkitAppearance;
      if (app === 'auto') add('appearance_auto', name(el));
    });

  /* 5. Не более одной главной кнопки на экран. Главная — залитая акцентом или
     графитом кнопка действия; в калькуляторе это `.btn` без `.btn-quiet`. */
  const mains = all.filter(el => el.matches('.btn:not(.btn-quiet):not(.btn-sm), .k-btn--main'));
  if (mains.length > 1) add('one_main_button', mains.length + ' шт: ' + mains.slice(0, 4).map(name).join(', '));

  /* 6. У выключенной кнопки есть видимый текстовый сосед: почему она заперта,
     говорят словами, а не серым цветом. */
  Array.from(document.querySelectorAll('button')).filter(vis).forEach(el => {
    if (!(el.disabled || el.getAttribute('aria-disabled') === 'true')) return;
    const host = el.closest('.field, .side-part, .row, .stat, .seg, div') || el.parentElement;
    const txt = host ? host.textContent.replace(el.textContent, '').trim() : '';
    if (txt.length < 3) add('disabled_button_explained', name(el));
  });

  /* 7. Крупное число набирается табличными цифрами: иначе столбец «пляшет». */
  /* Внутренности KaTeX не в счёт: цифру в формуле набирает математический
     шрифт своими правилами, и табличные цифры ей не положены. */
  all.forEach(el => {
    if (el.closest('.katex')) return;
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3)
      .map(n => n.nodeValue).join('').trim();
    if (!own || !/[0-9]/.test(own)) return;
    if (!/^[0-9\s.,%+−–-]+$/.test(own)) return;      // именно число, а не фраза с числом
    const c = getComputedStyle(el);
    if ((parseFloat(c.fontSize) || 0) < 15) return;
    const fv = (c.fontVariantNumeric || '') + ' ' + (c.fontFeatureSettings || '');
    if (!/tabular-nums|tnum/.test(fv)) add('tabular_nums', name(el) + ' «' + own.slice(0, 14) + '»');
  });

  /* 8. Нативная подсказка браузера не используется нигде (правило 18 части 4):
     она не появляется по клавиатуре, не появляется на сенсорном экране и не
     поддаётся оформлению. */
  Array.from(document.querySelectorAll('[title]')).filter(vis).forEach(el => {
    if (el.closest('svg')) return;                  // <title> внутри SVG — это имя фигуры, не подсказка
    /* Шапка сайта — общий файл платформы, и правится она не отсюда: у неё
       мимо канона ещё радиусы, границы и контраст логотипа, и все эти
       проверки исключают её так же явно. Карточка владельцу заведена. */
    if (inNav(el)) return;
    if (!el.matches('a, button, input, select, textarea, [role="button"], [tabindex], label')) return;
    add('title_on_interactive', name(el) + ' title=«' + el.getAttribute('title').slice(0, 24) + '»');
  });

  /* 10. Кегль и вес — только из шкалы канона 1.2. */
  /* Шкала канона 1.2 (текст) + 1.2.2 (числа) + два места, названные в самом
     каноне отдельно: мелкая кнопка 12px при базовом весе 500 (3.1) и глиф «?»
     кеглем 10 внутри кружка 15x15 (1.2, «это знак, а не текст»). */
  const SCALE = new Set([
    '11/400', '11/600', '11/700',
    '12/400', '12/500', '12/600', '12/700',
    '13/400', '13/500', '13/600', '13/700',
    '14/400', '14/600', '14/700',
    '15/600', '15/700', '22/600',
    '26/700', '56/800', '10/700']);
  all.forEach(el => {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.nodeValue).join('').trim();
    if (own.length < 2 || inNav(el) || el.closest('svg') || el.closest('.katex')) return;
    const c = getComputedStyle(el);
    const k = Math.round(parseFloat(c.fontSize)) + '/' + (parseInt(c.fontWeight, 10) || 400);
    if (!SCALE.has(k)) add('type_scale', name(el) + ' ' + k);
  });

  /* 11. Скругление — только из пяти значений канона 1.5. */
  const RAD = new Set([0, 4, 6, 10, 12]);
  all.forEach(el => {
    if (inNav(el) || el.closest('svg')) return;
    const c = getComputedStyle(el);
    ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius']
      .forEach(p => {
        const v = parseFloat(c[p]);
        if (!isFinite(v)) return;
        if (v >= 900 || /%/.test(c[p])) return;                 // пилюля и кружок
        if (!RAD.has(Math.round(v))) add('radius_scale', name(el) + ' ' + p.replace('border', '') + ' ' + c[p]);
      });
  });

  /* 13. У плашки состояния нет фона из семейства «-tint»: заливка сигнального
     оттенка делает плашку вторым акцентом экрана (канон 2.4). */
  const TINT = ['--accent-tint', '--amber-tint', '--green-tint', '--error-tint']
    .map(v => px(cs0.getPropertyValue(v).trim())).filter(Boolean);
  Array.from(document.querySelectorAll('.warn, .err, .error, .state, .k-state, .notice')).filter(vis).forEach(el => {
    const bg = px(getComputedStyle(el).backgroundColor);
    if (!bg || bg[3] < 0.05) return;
    if (TINT.some(t => Math.abs(t[0] - bg[0]) + Math.abs(t[1] - bg[1]) + Math.abs(t[2] - bg[2]) < 12))
      add('state_plate_tint', name(el));
  });

  /* 14. Две полосы на одном крае читаются как одна двухцветная. */
  all.forEach(el => {
    const c = getComputedStyle(el);
    const sh = c.boxShadow || '';
    if (!/inset/.test(sh)) return;
    ['Left', 'Right', 'Top', 'Bottom'].forEach(side => {
      const w = parseFloat(c['border' + side + 'Width']) || 0;
      if (w >= 1.5) add('two_stripes', name(el) + ' ' + side.toLowerCase() + ' + inset');
    });
  });

  /* 15. Текст с формулами набирается не теснее 1,55: тесная выключка
     превращает дробь в грязь. Однострочные элементы управления не в счёт —
     у них формула стоит одна и переноса нет. */
  Array.from(document.querySelectorAll('.katex')).forEach(k => {
    const host = k.parentElement && k.parentElement.closest('p, div, li, td, span');
    if (!host || !vis(host)) return;
    const c = getComputedStyle(host);
    const size = parseFloat(c.fontSize) || 13;
    const lh = c.lineHeight === 'normal' ? size * 1.2 : parseFloat(c.lineHeight);
    if (host.getBoundingClientRect().height < lh * 1.6) return;    // одна строка
    if (lh / size < 1.55 - 0.005) add('math_line_height', name(host) + ' ' + (lh / size).toFixed(2));
  });

  /* 16. Тень бывает только у того, что физически висит над страницей, и у колец
     фокуса (канон 1.7). */
  /* ⚠️ «ВСПЛЫВАЮЩЕЕ» СПРАШИВАЕТСЯ У РАСКЛАДКИ, А НЕ У СПИСКА КЛАССОВ.
     Список устаревает от первого нового окна, а канон говорит не про классы,
     а про то, что элемент физически висит НАД страницей. Измеримо это ровно
     две вещи: элемент вынут из потока (absolute / fixed / sticky) и поднят
     (z-index больше нуля). Кнопки масштаба над холстом под это подходят
     и тень им положена; панель в покое — нет. */
  const raised = (el) => {
    const c = getComputedStyle(el);
    if (!/^(absolute|fixed|sticky)$/.test(c.position)) return false;
    const z = parseInt(c.zIndex, 10);
    return isFinite(z) && z > 0;
  };
  const floating = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) if (raised(e)) return true;
    return false;
  };
  all.forEach(el => {
    if (inNav(el) || el.closest('svg')) return;
    const sh = getComputedStyle(el).boxShadow;
    if (!sh || sh === 'none') return;
    if (floating(el)) return;
    if (el === document.activeElement) return;                     // кольцо фокуса
    add('shadow_only_pop', name(el) + ' ' + sh.slice(0, 40));
  });

  /* 17. Область касания у поля-полосочки — не ниже 44 px (канон 3.3).
     ⚠️ ПРОВЕРКА СУЖЕНА ПО КАНОНУ, И ЭТО НЕ ПОБЛАЖКА. В плане работы она
     записана как «высота нажимаемого пальцем элемента ≥ 44 px», но канон
     такого правила не содержит: 44 px названы ровно в 3.3 (числовое
     поле-полосочка, «это область касания»), а у кнопки канон 3.1 задаёт
     высоту 33 px и мелкий вариант 25 px. Требовать 44 у кнопки значит
     противоречить статье 3.1 той же книги. */
  Array.from(document.querySelectorAll('.k-num')).filter(vis).forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.height < 44 - 0.5) add('knum_44', name(el) + ' h=' + r.height.toFixed(0));
  });

  /* 8 (канон, часть 4). Сплошной акцент — только у ВЫБРАННОГО из равноправных,
     и таких мест на экране не больше трёх. */
  if (accent) {
    const filled = all.filter(el => {
      if (inNav(el) || el.closest('svg')) return false;
      const bg = px(getComputedStyle(el).backgroundColor);
      if (!bg || bg[3] < 0.9) return false;
      return Math.abs(bg[0] - accent[0]) + Math.abs(bg[1] - accent[1]) + Math.abs(bg[2] - accent[2]) <= 12;
    });
    if (filled.length > 3)
      add('accent_fill_count', filled.length + ' шт: ' + filled.slice(0, 4).map(name).join(', '));
  }

  /* 18. В тёмной теме нет светлых системных виджетов: белое поле на тёмной
     панели слепит и выдаёт, что элемент рисует не сайт. */
  if (theme === 'dark') {
    Array.from(document.querySelectorAll('input, select, textarea')).filter(vis).forEach(el => {
      if (inNav(el)) return;
      const bg = px(getComputedStyle(el).backgroundColor);
      if (bg && bg[3] > 0.5 && lum(bg) > 0.55) add('dark_light_widget', name(el) + ' ' + getComputedStyle(el).backgroundColor);
    });
  }

  /* 19. Сырой шаблонный синтаксис на экране. Дефект прожил целую фазу и
     визуальную приёмку, поэтому проверка вынесена отдельной. */
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const p = n.parentElement;
    if (!p || p.closest('script, style')) continue;
    const t = n.nodeValue || '';
    if (/\{#|#\}|\{%|\{\{/.test(t)) add('raw_template', name(p) + ' «' + t.trim().slice(0, 30) + '»');
  }

  /* 20. Ни одна подпись холста не обрезана: прямоугольник целиком внутри и
     холста, и клипа своей группы. Подпись, спрятанную клипом ЦЕЛИКОМ, не
     трогаем — её скрыли намеренно. */
  const svgEl = document.querySelector('#chart');
  if (svgEl) {
    const box = svgEl.getBoundingClientRect();
    const clipOf = (node) => {
      let el = node;
      while (el && el !== svgEl) {
        const cp = el.getAttribute && el.getAttribute('clip-path');
        const m = cp && cp.match(/url\(#([^)]+)\)/);
        if (m) {
          const def = svgEl.querySelector('#' + m[1]) || document.getElementById(m[1]);
          const rc = def && def.querySelector('rect');
          const ctm = el.getScreenCTM && el.getScreenCTM();
          if (rc && ctm) {
            const num = (a) => parseFloat(rc.getAttribute(a)) || 0;
            const at = (x, y) => {
              const p = svgEl.createSVGPoint(); p.x = x; p.y = y;
              const q = p.matrixTransform(ctm);
              return { x: q.x - box.left, y: q.y - box.top };
            };
            const a = at(num('x'), num('y'));
            const b = at(num('x') + num('width'), num('y') + num('height'));
            return { id: m[1], x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
                     w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y) };
          }
        }
        el = el.parentNode;
      }
      return null;
    };
    svgEl.querySelectorAll('text').forEach(t => {
      const c = getComputedStyle(t);
      if (c.display === 'none' || c.visibility === 'hidden' || parseFloat(c.opacity) < 0.05) return;
      const r = t.getBoundingClientRect();
      if (r.width < 0.5 || r.height < 0.5) return;
      const rr = { x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height };
      const s = (Array.from(t.childNodes).filter(n => n.nodeType === 3).map(n => n.nodeValue).join('').trim()
                 || Array.from(t.querySelectorAll('tspan')).map(x => x.textContent).join('').trim()).slice(0, 22);
      const outside = (b) => rr.x < b.x - 0.6 || rr.y < b.y - 0.6
                          || rr.x + rr.w > b.x + b.w + 0.6 || rr.y + rr.h > b.y + b.h + 0.6;
      const gone = (b) => rr.x + rr.w <= b.x + 0.6 || rr.x >= b.x + b.w - 0.6
                       || rr.y + rr.h <= b.y + 0.6 || rr.y >= b.y + b.h - 0.6;
      if (outside({ x: 0, y: 0, w: box.width, h: box.height })) add('label_clipped', 'холст «' + s + '»');
      const cl = clipOf(t);
      if (cl && !gone(cl) && outside(cl)) add('label_clipped', 'клип #' + cl.id + ' «' + s + '»');
    });
  }

  return out;
};

/* ── Обход ───────────────────────────────────────────────────────────────── */

const KEYS = ['dark_white_on_accent', 'contrast_text', 'appearance_auto', 'one_main_button',
  'disabled_button_explained', 'tabular_nums', 'title_on_interactive', 'no_h_scroll',
  'type_scale', 'radius_scale', 'state_plate_tint', 'two_stripes', 'math_line_height',
  'shadow_only_pop', 'knum_44', 'accent_fill_count', 'dark_light_widget', 'raw_template',
  'label_clipped', 'label_shake'];

(async () => {
  let browser;
  try {
    browser = await chromium.launch();
  } catch (e) {
    console.error('Playwright не запустился: ' + e.message);
    process.exit(3);
  }
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  KEYS.forEach(seen);

  try {
    await login(page);
    await page.goto(BASE + '/calc2/', { waitUntil: 'load' });
    const ready = await page.evaluate(() => typeof pickScene === 'function').catch(() => false);
    if (!ready) { console.error('calc2 не загрузился'); await browser.close(); process.exit(3); }

    for (const theme of THEMES) {
      for (const key of SCENES) {
        await openScene(page, key, theme);
        const found = await page.evaluate(inPage, theme);
        found.forEach(([k, what]) => put(k, theme + '/' + key, what));
      }
    }

    /* 20. Подпись кривой не дёргается, пока ведут ползунок параметра.

       Это тот самый прогон, которым дефект был найден: «a» ведётся от 1,00 до
       2,00 шагами по 0,05, и на каждом шаге меряется место подписи. Заодно
       меряется деление «2» на оси: если плоскость сама поехала, движение
       подписи было бы честным следствием, а не дефектом.

       Порог 2 px за шаг: подпись имеет право ЕХАТЬ вслед за кривой, но не
       имеет права прыгать туда-сюда. До правки замер давал до 16 px при
       неподвижной плоскости. */
    await openScene(page, 'm-graph', 'light');
    await page.evaluate(() => {
      const box = document.getElementById('graph-rows');
      if (box) openSection(box.closest('.section').id);
      const inp = document.querySelector('#graph-rows .f-slot > input');
      if (inp) { inp.value = 'a*x^2 - 3*x'; inp.dispatchEvent(new Event('input', { bubbles: true })); }
    });
    await page.waitForTimeout(900);
    let prevY = null, prevTick = null, worst = 0, tickMoved = 0;
    for (let i = 0; i <= 20; i++) {
      await page.evaluate((v) => {
        if (STATE.params && STATE.params.a) STATE.params.a.value = v;
        redrawAll();
      }, 1 + i * 0.05);
      await page.waitForTimeout(200);
      const st = await page.evaluate(() => {
        const lab = document.querySelector('#chart text.curve-name');
        const box = document.querySelector('#chart').getBoundingClientRect();
        const tick = Array.from(document.querySelectorAll('#chart text.axis-num'))
          .filter(t => t.textContent.trim() === '2')[0];
        return { y: lab ? lab.getBoundingClientRect().top - box.top : null,
                 tick: tick ? tick.getBoundingClientRect().left - box.left : null };
      });
      if (st.y == null) continue;
      if (prevY != null) worst = Math.max(worst, Math.abs(st.y - prevY));
      if (prevTick != null && st.tick != null) tickMoved = Math.max(tickMoved, Math.abs(st.tick - prevTick));
      prevY = st.y; if (prevTick == null) prevTick = st.tick;
    }
    if (worst > 2) put('label_shake', 'm-graph',
                       'скачок ' + worst.toFixed(1) + ' px за шаг при сдвиге плоскости ' +
                       tickMoved.toFixed(1) + ' px');

    /* 9. Страница не едет вбок ни на одной из четырёх ширин (канон 1.9.1). */
    await openScene(page, SCENES[0], 'light');
    for (const w of WIDTHS) {
      await page.setViewportSize({ width: w, height: 900 });
      await page.waitForTimeout(450);
      const over = await page.evaluate(() =>
        document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (over > 1) put('no_h_scroll', 'ширина ' + w, 'вылезает на ' + over + ' px');
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  } catch (e) {
    console.error('обход прерван: ' + (e && e.message));
    await browser.close();
    process.exit(3);
  }
  await browser.close();

  KEYS.forEach(k => {
    const b = R[k];
    console.log((b.n ? 'x ' : 'v ') + k + ': ' + b.n + (b.n ? ' — ' + b.ex[0] : ''));
  });
  console.log('###CANON-JSON###');
  console.log(JSON.stringify(R));
  process.exit(0);
})();
