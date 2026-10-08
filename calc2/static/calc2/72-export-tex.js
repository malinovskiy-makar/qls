// Выгрузка графика в LaTeX: бумажный прогон → опись → сборка (SPEC задания 07.10.2026).
/* ---------------------------------------------------------------------
   ФАЙЛ .tex ИЗ ЗАПИСИ ПРИ РИСОВАНИИ (решение владельца 07.10.2026, ADR 0139).

   Прежняя выгрузка обходила нарисованное и снимала кривые и закрашенные
   области сотнями точек с экрана; у моделей с двумя графиками панели
   сливались в один, часть файлов не собиралась. Теперь три части:

     1) бумажный прогон (texEnterPaper) — холст на миг перерисовывается на
        белом листе ПОСТОЯННОГО размера (1 px = 0,75 pt), от окна и темы не
        зависит, и возвращается в прежний вид в той же задаче браузера;
     2) опись (texCapture) — обход нарисованного в координатах модели своей
        панели. У кривой и области место рисования оставило ЗАПИСЬ (формула и
        отрезок, границы — data-* на самом узле, см. markExpr и markArea в
        30-curves.js), и опись СВЕРЯЕТ её с нарисованными узлами. Не сошлась
        или записи нет — в файл идут узлы самого пути (запасной путь), а в
        счётчик прибора — дефект. Отрезки, точки, подписи, деления, сетка и
        легенда записи не требуют: их числа на узле и так точные;
     3) сборка (texEmit) — чистая функция «опись → текст pgfplots», DOM не
        трогает; её проверяют приборы calc2/tests/tex/ на готовых описях.

   Дверь одна — buildTex(title, label) в 70-scenes-math.js; её зовут кнопка
   «Скачать», PDF и приборы.
   --------------------------------------------------------------------- */

/* Бумажный прогон идёт? Читают computeSize (20-plane.js) и floatRects
   (60-overlays.js): на листе поле графика постоянного размера, а плавающих
   блоков над холстом нет. */
let _texPaper = null;
function texPaperActive() { return !!_texPaper; }

/* Размер холста на листе: поля fitMargins() плюс поле графика постоянного
   размера (12 × 8 см у одной панели). Зовётся из computeSize вместо мерки
   обёртки #graph-wrap. */
function texPaperComputeSize() {
  const plot = _texPaper.plot;
  W = 640; H = 440;
  svg.attr('width', W).attr('height', H);
  fitMargins();
  const m = CONFIG.margin;
  W = m.left + plot[0] + m.right; H = m.top + plot[1] + m.bottom;
  svg.attr('width', W).attr('height', H);
  makeScales();
  /* ⚠️ У #chart в стилях width:100 %; height:100 % — его РАМКА равна обёртке,
     а не атрибутам width/height. Проходы подписей (keepAxisNamesInside,
     spreadLabels, unclipLabels) меряют именно рамку, поэтому на время прогона
     она задаётся строчным стилем; иначе на телефоне подписи прижимались бы к
     краю экрана, а не листа. Переходы гашены первым свойством: при «меньше
     движения» любое изменение стиля идёт переходом, и синхронный замер рамки
     видел бы прежний размер. */
  const el = document.getElementById('chart');
  [['transition', 'none'], ['width', W + 'px'], ['height', H + 'px'], ['min-width', W + 'px'], ['max-width', W + 'px'],
   ['min-height', H + 'px'], ['max-height', H + 'px'], ['flex', '0 0 auto']]
    .forEach(([k, v]) => el.style.setProperty(k, v, 'important'));
}

const TexExport = (function () {
  'use strict';

  const PX2PT = 0.75;                 // 1 px холста = 0,75 pt страницы
  const K_LINE = 0.45;                // толщина: 2,5 px кривой → 1,13 pt
  const K_DASH = 0.6;                 // штрих
  const K_DOT = 0.6;                  // радиус точки
  const PLOT_SINGLE = [454, 302];     // поле графика 12 × 8 см
  const PLOT_WIDE = [605, 283];       // панели рядом: 16 × 7,5 см на всех
  const PLOT_TALL = [454, 454];       // панели одна над другой: 12 × 12 см на всех
  const POLY_MAX = 12;                // столько вершин ещё «ломаная с точными вершинами»
  /* Координаты в атрибуте d округлены самим D3 до 0,001 px — это 1,6·10⁻⁶
     размаха оси на поле в 300 px. Отсюда допуски (SPEC, раздел 4). */
  const SIMPLIFY_TOL = 4e-6;          // узел на одной прямой с соседями (в долях размаха)
  const VERIFY_TOL = 2e-5;            // формула проходит через нарисованные узлы
  const BETWEEN_TOL = 2e-3;           // между соседними узлами формула не уходит от ломаной дальше
  const AREA_TOL = 5e-3;              // площадь нарисованной области против интеграла между границами
  const EXT = 0.3;                    // запас окна, за которым координаты в файл не идут
  // знаков после запятой у координаты при таком размахе оси (при размахе 100 — три)
  const decOf = (span) => Math.max(0, Math.min(8, Math.ceil(4.3 - Math.log10(span))));

  /* ───────────────────────── помощники ───────────────────────── */
  function rgba(css) {
    const m = String(css || '').match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?/i);
    return m ? [+m[1], +m[2], +m[3], m[4] == null ? 1 : +m[4]] : null;
  }
  function hex(css) {
    const c = rgba(css);
    if (!c) return null;
    const two = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).toUpperCase().padStart(2, '0');
    return two(c[0]) + two(c[1]) + two(c[2]);
  }
  // Итоговая прозрачность: произведение opacity узла и всех предков.
  function chainOpacity(el, root) {
    let o = 1;
    for (let n = el; n && n !== root && n.nodeType === 1; n = n.parentNode) {
      const v = parseFloat(getComputedStyle(n).opacity);
      if (isFinite(v)) o *= v;
    }
    return o;
  }
  function shown(el) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0.5 || r.height > 0.5;
  }
  /* Разбор атрибута d. Понимает M L H V Z в обоих регистрах: других команд на
     бумажном прогоне 44 сцен нет (замер). На первой ошибке останавливается
     ТАК ЖЕ, КАК БРАУЗЕР: путь нарисован до команды с ошибкой, она сама и всё
     после неё на экран не попали. Ошибка бывает двух видов: незнакомая
     команда (bad = 'cmd:C') и нечисловая координата — NaN, который D3
     печатает в путь, когда сцена дала ему не число (bad = 'nan'). */
  function parseD(d) {
    const toks = String(d || '').match(/NaN|-?Infinity|[a-zA-Z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g) || [];
    const subs = []; let cur = null, x = 0, y = 0, i = 0, cmd = '', bad = '';
    const isNum = (t) => t != null && /^[-+]?(?:\d|\.\d)/.test(t);
    while (i < toks.length) {
      if (/^[a-zA-Z]$/.test(toks[i])) cmd = toks[i++];
      const rel = cmd === cmd.toLowerCase(), C = cmd.toUpperCase();
      if (C === 'Z') { if (cur) cur.closed = true; cur = null; continue; }
      const need = (C === 'M' || C === 'L') ? 2 : (C === 'H' || C === 'V') ? 1 : 0;
      if (!need) { bad = 'cmd:' + cmd; break; }
      const a = toks.slice(i, i + need);
      if (a.length < need || !a.every(isNum)) { bad = 'nan'; break; }
      i += need;
      const v = a.map(parseFloat);
      if (C === 'M') { x = (rel ? x : 0) + v[0]; y = (rel ? y : 0) + v[1]; cur = { pts: [[x, y]], closed: false }; subs.push(cur); cmd = rel ? 'l' : 'L'; continue; }
      if (C === 'L') { x = (rel ? x : 0) + v[0]; y = (rel ? y : 0) + v[1]; }
      else if (C === 'H') { x = (rel ? x : 0) + v[0]; }
      else { y = (rel ? y : 0) + v[0]; }
      if (!cur) { cur = { pts: [], closed: false }; subs.push(cur); }
      cur.pts.push([x, y]);
    }
    return { subs, bad };
  }
  // Убрать повторы и узлы, лежащие на одной прямой с соседями (в долях размаха осей).
  function simplify(pts, sx, sy, closed) {
    const N = (p) => [p[0] / sx, p[1] / sy];
    let a = [];
    pts.forEach(p => { const q = a[a.length - 1]; if (!q || Math.hypot((p[0] - q[0]) / sx, (p[1] - q[1]) / sy) > 1e-9) a.push(p); });
    if (closed && a.length > 1) { const f = a[0], l = a[a.length - 1]; if (Math.hypot((f[0] - l[0]) / sx, (f[1] - l[1]) / sy) <= 1e-9) a.pop(); }
    const off = (p, q, r) => {           // расстояние q от прямой p–r
      const [x1, y1] = N(p), [x2, y2] = N(r), [x0, y0] = N(q);
      const L = Math.hypot(x2 - x1, y2 - y1);
      if (L < 1e-12) return Math.hypot(x0 - x1, y0 - y1);
      // узел обязан лежать МЕЖДУ соседями, иначе это разворот, а не лишний узел
      const t = ((x0 - x1) * (x2 - x1) + (y0 - y1) * (y2 - y1)) / (L * L);
      if (t < -1e-9 || t > 1 + 1e-9) return 1;
      return Math.abs((x2 - x1) * (y1 - y0) - (x1 - x0) * (y2 - y1)) / L;
    };
    let changed = true, guard = 0;
    while (changed && guard++ < 6) {
      changed = false;
      const out = [];
      const n = a.length;
      for (let i = 0; i < n; i++) {
        const isEnd = !closed && (i === 0 || i === n - 1);
        if (isEnd || n < 3) { out.push(a[i]); continue; }
        const p = out.length ? out[out.length - 1] : a[(i - 1 + n) % n];
        const r = a[(i + 1) % n];
        if (off(p, a[i], r) < SIMPLIFY_TOL) { changed = true; continue; }
        out.push(a[i]);
      }
      a = out;
    }
    return a;
  }

  /* Участки аргумента внутри [a, b], на которых значение формулы лежит в
     [lo, hi] (расширенное окно): за ним pgfplots падает с «Dimension too
     large». Сетка 400 шагов, края участка уточняются делением пополам.
     digits — сколько знаков после запятой получит край в файле: проверяется
     ИМЕННО напечатанное число, потому что pgfplots считает формулу в нём. */
  function visibleRuns(a, b, f, lo, hi, digits) {
    const inside = (v) => isFinite(v) && v >= lo && v <= hi;
    const N = 400, h = (b - a) / N, runs = []; let start = null, prev = null;
    const edge = (xin, xout) => {         // f(xin) внутри, f(xout) снаружи (или не число) → граница
      let p = xin, q = xout;
      for (let k = 0; k < 50; k++) { const m = (p + q) / 2; if (inside(f(m))) p = m; else q = m; }
      return p;
    };
    for (let i = 0; i <= N; i++) {
      const x = (i === N) ? b : a + h * i, ok = inside(f(x));
      if (ok && start == null) start = (prev != null) ? edge(x, prev) : x;
      if (!ok && start != null) { runs.push([start, edge(prev, x)]); start = null; }
      prev = x;
    }
    if (start != null) runs.push([start, b]);
    const span = Math.abs(b - a) || 1;
    const printed = (v) => +v.toFixed(digits == null ? 8 : digits);
    return runs.filter(r => Math.abs(r[1] - r[0]) > span * 1e-9).map(r => {
      let p = Math.min(r[0], r[1]), q = Math.max(r[0], r[1]);
      /* Край, в котором формула не считается (AVC при Q = 0: ноль на ноль),
         отодвигаем внутрь на миллионную долю участка: деление пополам
         подходит к такому краю вплотную, а после округления это он и есть. */
      if (!isFinite(f(printed(p)))) p += span * 1e-6;
      if (!isFinite(f(printed(q)))) q -= span * 1e-6;
      return [p, q];
    }).filter(r => r[1] > r[0]);
  }
  /* Сколько отсчётов дать pgfplots. Прямая — два. Иначе наименьшее число из
     ряда, при котором ломаная через равномерные отсчёты отходит от кривой
     меньше чем на 0,1 % высоты окна. Постоянные 161 отсчёт рисовали
     «5·sin x + x/2» на окне шириной 100 зубцами, а гиперболе у нуля давали
     0,3 % высоты (замер разведки). */
  const SAMPLE_STEPS = [41, 81, 161, 321, 641, 1281];
  function pickSamples(f, a, b, lo, hi, span) {
    const fa = f(a), fb = f(b);
    if (isFinite(fa) && isFinite(fb) && [0.123, 0.377, 0.5, 0.711, 0.931].every(t => { const v = f(a + (b - a) * t); return isFinite(v) && Math.abs(v - (fa + (fb - fa) * t)) < span * 1e-7; })) return 2;
    for (const n of SAMPLE_STEPS) {
      const h = (b - a) / (n - 1); let worst = 0;
      for (let i = 0; i < n - 1 && worst < span * 1e-3; i++) {
        const x0 = a + h * i, y0 = f(x0), y1 = f(x0 + h);
        if (!isFinite(y0) || !isFinite(y1)) continue;
        if ((y0 < lo && y1 < lo) || (y0 > hi && y1 > hi)) continue;    // за окном кривую режет обрезка
        for (const t of [0.382, 0.71]) { const v = f(x0 + h * t); if (isFinite(v)) worst = Math.max(worst, Math.abs(v - (y0 + (y1 - y0) * t))); }
      }
      if (worst < span * 1e-3) return n;
    }
    return SAMPLE_STEPS[SAMPLE_STEPS.length - 1];
  }
  // Ломаная, обрезанная прямоугольником: куски внутри, точки входа и выхода — на границе.
  function clipLine(pts, x0, x1, y0, y1) {
    const code = (p) => (p[0] < x0 ? 1 : p[0] > x1 ? 2 : 0) | (p[1] < y0 ? 4 : p[1] > y1 ? 8 : 0);
    const cut = (a, b) => {               // отрезок a–b → часть внутри либо null (Коэн — Сазерленд)
      let A = a.slice(), B = b.slice(), ca = code(A), cb = code(B);
      for (let k = 0; k < 8; k++) {
        if (!(ca | cb)) return [A, B];
        if (ca & cb) return null;
        const c = ca || cb; let x, y;
        if (c & 8) { x = A[0] + (B[0] - A[0]) * (y1 - A[1]) / (B[1] - A[1]); y = y1; }
        else if (c & 4) { x = A[0] + (B[0] - A[0]) * (y0 - A[1]) / (B[1] - A[1]); y = y0; }
        else if (c & 2) { y = A[1] + (B[1] - A[1]) * (x1 - A[0]) / (B[0] - A[0]); x = x1; }
        else { y = A[1] + (B[1] - A[1]) * (x0 - A[0]) / (B[0] - A[0]); x = x0; }
        if (c === ca) { A = [x, y]; ca = code(A); } else { B = [x, y]; cb = code(B); }
      }
      return null;
    };
    const out = []; let cur = null;
    for (let i = 1; i < pts.length; i++) {
      const seg = cut(pts[i - 1], pts[i]);
      if (!seg) { cur = null; continue; }
      const same = cur && Math.abs(cur[cur.length - 1][0] - seg[0][0]) < 1e-12 && Math.abs(cur[cur.length - 1][1] - seg[0][1]) < 1e-12;
      if (same) cur.push(seg[1]); else { cur = [seg[0], seg[1]]; out.push(cur); }
    }
    return out;
  }
  // Многоугольник, обрезанный прямоугольником (Сазерленд — Ходжман).
  function clipPoly(pts, x0, x1, y0, y1) {
    const edges = [[(p) => p[0] >= x0, (a, b) => [x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0])]],
                   [(p) => p[0] <= x1, (a, b) => [x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0])]],
                   [(p) => p[1] >= y0, (a, b) => [a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0]],
                   [(p) => p[1] <= y1, (a, b) => [a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1]]];
    let poly = pts.slice();
    edges.forEach(([inside, cross]) => {
      const res = [];
      for (let i = 0; i < poly.length; i++) {
        const a = poly[i], b = poly[(i + 1) % poly.length];
        const ia = inside(a), ib = inside(b);
        if (ia) res.push(a);
        if (ia !== ib) res.push(cross(a, b));
      }
      poly = res;
    });
    return poly;
  }
  function panelDistPx(p, px, py) {
    const dx = Math.max(p.x0 - px, 0, px - p.x1), dy = Math.max(p.y0 - py, 0, py - p.y1);
    return Math.hypot(dx, dy);
  }

  /* ───────────────── подпись холста → TeX (SPEC, раздел 7) ─────────────────
     Решение «величина или слово» принимает разметка самой подписи (data-raw):
     слова с кириллицей — текст, остальное — математика. Прежний перевод
     (quantityTex → qtyLatex) ронял сборку на штрихе внутри математики, на
     «\Deltax» и на греческой букве в индексе числа; этот проходит корпус
     подписей (calc2/tests/tex/labels.py). */
  const GREEK = { 'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta', 'ε': 'varepsilon', 'θ': 'theta', 'λ': 'lambda', 'μ': 'mu', 'π': 'pi', 'ρ': 'rho', 'σ': 'sigma', 'τ': 'tau', 'φ': 'varphi', 'ω': 'omega', 'η': 'eta', 'Δ': 'Delta', 'Σ': 'Sigma', 'Ω': 'Omega', 'Π': 'Pi' };
  const SUBD = { '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9' };
  const SUPD = { '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9' };
  const OPS = { '−': '-', '–': '-', '·': '\\cdot ', '×': '\\times ', '÷': '\\div ', '≈': '\\approx ', '≤': '\\le ', '≥': '\\ge ', '≠': '\\ne ', '→': '\\to ', '←': '\\leftarrow ', '±': '\\pm ', '∞': '\\infty ', '∈': '\\in ', '′': "'", '″': "''", '∂': '\\partial ', '∑': '\\sum ', '∫': '\\int ', '√': '\\surd ', '°': '^{\\circ}', '%': '\\%', '&': '\\&', '#': '\\#', '$': '\\$', '~': '\\sim ' };
  const FUNCS = ['max', 'min', 'log', 'ln', 'lim', 'exp', 'sin', 'cos', 'tan'];
  const IDXW = ['min', 'max', 'avg', 'opt', 'eq', 'tot', 'reg', 'imp', 'exp', 'eff'];
  const SPACES = /[     ]/;
  const CYR = /[А-Яа-яЁё]/;

  /* Текст человека (заголовок, метка, имя кривой) — буквально: каждый знак
     TeX экранируется, обратный слэш не доходит до файла командой. Знак за
     знаком, а не цепочкой замен: замена «\» на «\textbackslash{}» с
     последующим экранированием скобок давала «\textbackslash\{\}». */
  const ESC = { '\\': '\\textbackslash{}', '{': '\\{', '}': '\\}', '&': '\\&', '%': '\\%', '$': '\\$', '#': '\\#', '_': '\\_', '~': '\\textasciitilde{}', '^': '\\textasciicircum{}' };
  function texEsc(s) {
    let out = '';
    for (const ch of String(s)) out += ESC[ch] || ch;
    return out;
  }
  function proseTex(s) {
    let out = '';
    for (const ch of String(s)) {
      if (ch === ' ' || ch === ' ' || ch === ' ') out += '~';
      else if (ch === '\u2014') out += '---';
      else if (ch === '–') out += '--';
      else if (ch === '−') out += '$-$';
      else if (ch === '«') out += '<<';
      else if (ch === '»') out += '>>';
      else if (ch === '№') out += '\\textnumero{}';
      else if (ch === '…') out += '\\ldots{}';
      else if (GREEK[ch]) out += '$\\' + GREEK[ch] + '$';
      else if (OPS[ch] && !/[%&#$~]/.test(ch)) out += '$' + OPS[ch].trim() + '$';
      else if (SUBD[ch]) out += '$_{' + SUBD[ch] + '}$';
      else if (SUPD[ch]) out += '$^{' + SUPD[ch] + '}$';
      else if (ch.charCodeAt(0) < 128 || CYR.test(ch)) out += texEsc(ch);
      else out += '?';                                   // неизвестный знак: не роняем сборку
    }
    return out;
  }
  // Имя латиницей: аббревиатура, символ с индексом, функция или слово.
  function latinTex(run) {
    if (run.length === 1) return run;
    if (FUNCS.indexOf(run) >= 0) return '\\' + run + ' ';
    if (/^[A-Z]+$/.test(run)) return '\\mathrm{' + run + '}';
    const tail = run.slice(1);
    if (/^[A-Z]$/.test(run[0]) && (/^[a-z]{1,2}$/.test(tail) || IDXW.indexOf(tail) >= 0)) {
      return run[0] + '_{' + (tail.length > 1 ? '\\mathrm{' + tail + '}' : tail) + '}';
    }
    return '\\mathrm{' + run + '}';
  }
  /* ⚠️ КИРИЛЛИЦЫ В МАТЕМАТИКЕ НЕТ. \text{…} внутри формулы строит все четыре
     кегля (amstext, \mathchoice), и кириллице нужен шрифт T2A в 5 pt. В TeX
     Live его нет готовым: TeX создаёт его сам (mktextfm), но сервер сборки PDF
     запускает pdflatex без домашней папки и с запретами (calc2/views.py), и
     там «$33{,}33_{\text{м}}$» не собирается (замер 08.10: «Росcийский труд»
     в «Двусторонней монополии»). Поэтому кириллица выходит из формулы:
     индекс — \textsubscript, степень — \textsuperscript, слово — текстом.
     В тексте формулы такие куски помечены знаками \u0001…\u0002, а labelTex
     разрезает по ним строку на математику и текст. */
  const TXT = (kind, text) => '\u0001' + kind + ':' + text + '\u0002';
  function idxTex(s, kind) {                            // содержимое индекса или степени
    if (!s) return '';
    if (CYR.test(s)) return TXT(kind, proseTex(s));
    if (/^[A-Za-z]{2,}$/.test(s)) return '\\mathrm{' + s + '}';
    return mathTex(s);
  }
  function mathTex(src) {
    const s = String(src); let out = '', i = 0, prevSym = false;
    const group = () => {                               // { … } либо один знак/пробег
      if (s[i] === '{') { let d = 0, j = i; for (; j < s.length; j++) { if (s[j] === '{') d++; else if (s[j] === '}' && --d === 0) break; } const body = s.slice(i + 1, j); i = j + 1; return body; }
      const m = /^[A-Za-z]+|^[0-9]+|^./.exec(s.slice(i)); const body = m ? m[0] : ''; i += body.length; return body;
    };
    while (i < s.length) {
      const ch = s[i];
      if (/[A-Za-z]/.test(ch)) { let run = ''; while (i < s.length && /[A-Za-z]/.test(s[i])) run += s[i++]; out += latinTex(run); prevSym = true; continue; }
      if (/[0-9]/.test(ch)) {
        let run = '';
        while (i < s.length && (/[0-9.,]/.test(s[i]) || (SPACES.test(s[i]) && /[0-9]/.test(s[i + 1] || '') && /[0-9]/.test(s[i - 1] || '') && s[i] !== ' '))) run += s[i++];
        // хвостовая запятая или точка — знак препинания, а не дробная часть
        let tailP = ''; const mt = /[.,]+$/.exec(run); if (mt) { tailP = mt[0]; run = run.slice(0, -tailP.length); }
        // цифры сразу за буквой — индекс (Q1, D2)
        if (prevSym && /^[0-9]+$/.test(run) && /[A-Za-z}]$/.test(out)) out += '_{' + run + '}';
        else out += run.replace(/,/g, '{,}').replace(new RegExp(SPACES.source, 'g'), '\\,');
        out += tailP; prevSym = false; continue;
      }
      if (ch === '_') { i++; const g = idxTex(group(), 'sub'); out += g.charAt(0) === '\u0001' ? g : '_{' + g + '}'; continue; }
      if (ch === '^') { i++; const g = idxTex(group(), 'sup'); out += g.charAt(0) === '\u0001' ? g : '^{' + g + '}'; continue; }
      if (SUBD[ch]) { let r = ''; while (SUBD[s[i]]) r += SUBD[s[i++]]; out += '_{' + r + '}'; continue; }
      if (SUPD[ch]) { let r = ''; while (SUPD[s[i]]) r += SUPD[s[i++]]; out += '^{' + r + '}'; continue; }
      if (GREEK[ch]) { out += '\\' + GREEK[ch] + ' '; prevSym = true; i++; continue; }
      if (ch === '*' || ch === '∗') { out += prevSym ? '^{*}' : '\\ast '; i++; continue; }
      if (OPS[ch] !== undefined) { out += OPS[ch]; prevSym = false; i++; continue; }
      if (ch === '=') { out += ' = '; prevSym = false; i++; continue; }
      /* Двоеточие после слова — знак препинания («max: (0; 1)»), а в математике
         TeX считает его отношением и ставит пробел с обеих сторон. */
      if (ch === ':') { const nx = s[i + 1]; out += (nx === undefined || SPACES.test(nx)) ? '\\colon ' : ':'; prevSym = false; i++; continue; }
      // неразрывный пробел внутри формулы («20 %») — тонкая шпация: обычный пробел в математике пропадает
      if (SPACES.test(ch)) { out += (ch === ' ' ? ' ' : '\\,'); i++; continue; }
      if (ch === '{' || ch === '}') { out += '\\' + ch; i++; continue; }
      if (ch === '\\') { out += '\\backslash '; i++; continue; }
      if (CYR.test(ch)) { let run = ''; while (i < s.length && CYR.test(s[i])) run += s[i++]; out += TXT('txt', proseTex(run)); prevSym = false; continue; }
      if (ch.charCodeAt(0) < 128) { out += ch; prevSym = (ch === ')' || ch === ']'); i++; continue; }
      out += '?'; i++;
    }
    return out.replace(/ {2,}/g, ' ').trim();
  }
  /* Подпись целиком: слова с кириллицей — текст, остальное — математика. */
  function labelTex(raw) {
    const s = String(raw == null ? '' : raw).replace(/​/g, '').trim();
    if (!s) return '';
    // слова делим по ОБЫЧНОМУ пробелу: узкий неразрывный стоит внутри чисел
    const words = s.split(/ +/);
    const segs = [];
    words.forEach(w => {
      /* Слово из одних знаков препинания («&» в «50% & выше», «%» в «τ = 20 %») —
         текст: в математике пробел перед ним пропал бы. */
      const prose = (CYR.test(w) && !/[_^]/.test(w)) || /^[&%,;:!?.«»()\u2014\u2013…]+$/.test(w);
      const last = segs[segs.length - 1];
      if (last && last.prose === prose) last.w.push(w); else segs.push({ prose, w: [w] });
    });
    return segs.map(g => g.prose ? proseTex(g.w.join(' ')) : mathOut(mathTex(g.w.join(' ')))).join(' ');
  }
  // Математика с вынесенными кусками кириллицы → «$…$\textsubscript{…}$…$».
  function mathOut(m) {
    let out = '';
    m.split(/\u0001|\u0002/).forEach((part, k) => {
      if (k % 2 === 0) { if (part.trim()) out += '$' + part.trim() + '$'; return; }
      const c = part.indexOf(':'), kind = part.slice(0, c), text = part.slice(c + 1);
      out += kind === 'sub' ? '\\textsubscript{' + text + '}' : kind === 'sup' ? '\\textsuperscript{' + text + '}' : (out ? ' ' : '') + text + ' ';
    });
    return out.trim();
  }
  /* Комментарий в файле: имена и причины — только знаки ASCII и кириллица
     (правило «в теле файла только ASCII, кириллица и « » — – №»). */
  function commentText(s) {
    let out = '';
    for (const ch of String(s == null ? '' : s)) {
      if (SUBD[ch]) out += SUBD[ch];
      else if (SUPD[ch]) out += '^' + SUPD[ch];
      else if (ch === '′') out += "'";
      else if (ch === '−') out += '-';
      else if (GREEK[ch]) out += GREEK[ch];
      else if (/[    ]/.test(ch)) out += ' ';
      else if (ch === '\n' || ch === '\r') out += ' ';
      else if ((ch.charCodeAt(0) >= 32 && ch.charCodeAt(0) < 127) || CYR.test(ch) || '«»\u2014–№'.indexOf(ch) >= 0) out += ch;
      else out += '?';
    }
    return out;
  }

  /* ───────────── формула Math.js → pgfplots (SPEC, раздел 8) ─────────────
     Каждое правило проверено настоящим pgfmath:
       • степень в pgfmath ЛЕВОассоциативна: 2^3^2 = 64, у Math.js 512 —
         вложенная степень всегда в скобках;
       • унарный минус без своих скобок — только в начале выражения, после
         скобки или запятой; его операнд — в скобках, если это не имя, число
         или вызов функции (старые версии pgf считали -x^2 как (-x)^2);
       • тригонометрия pgfmath в градусах, обратная отдаёт градусы;
       • (-8)^(1/3) в pgfmath не число: корень нечётной степени идёт через
         sign(a) * abs(a)^(1/n), как nthRoot у Math.js;
       • log(x) у Math.js натуральный, log(x, b) — по основанию b.
     asVar — имя переменной в файле: 'x' у обычной кривой, 't' у записи
     «по вертикали» (параметрический \addplot). Неизвестная буква — null:
     формулу не перевести, кривая идёт запасным путём (дефект в приборе). */
  const PGF_FN = { sqrt: 'sqrt', abs: 'abs', exp: 'exp', ln: 'ln', min: 'min', max: 'max', round: 'round', floor: 'floor', ceil: 'ceil', sign: 'sign', log10: 'log10', log2: 'log2', sinh: 'sinh', cosh: 'cosh', tanh: 'tanh' };
  const PGF_TRIG = { sin: 'sin', cos: 'cos', tan: 'tan', cot: 'cot' };
  const PGF_ATRIG = { asin: 'asin', acos: 'acos', atan: 'atan' };
  const PREC = { '+': 1, '-': 1, '*': 2, '/': 2, '^': 4 };
  const AXIS_VARS = ['x', 'Q', 'q', 'L', 'l', 'X'];           // то же, что подставляет axisScope (10-math-core.js)
  function exprToPgf(expr, varName, asVar) {
    let node;
    try { node = math.parse(prepExpr(String(expr == null ? '' : expr))); } catch (e) { return null; }
    const V = asVar || 'x';
    const vars = new Set(AXIS_VARS.concat(varName ? [varName, varName.toLowerCase(), varName.toUpperCase()] : []));
    let bad = false;
    const fmtNum = (v) => { const r = +(+v).toPrecision(12); return (r < 0 ? '(' + r + ')' : String(r)); };
    const constOf = (n) => { let x = n; while (x && x.type === 'ParenthesisNode') x = x.content; return (x && x.type === 'ConstantNode' && typeof x.value === 'number') ? x.value : null; };
    /* lead — текст узла встанет в самом начале выражения, сразу после скобки
       или запятой: только там унарный минус печатается без своих скобок. */
    const walk = (n, parentPrec, right, lead) => {
      if (bad) return '';
      switch (n.type) {
        case 'ConstantNode': return (typeof n.value === 'number' && isFinite(n.value)) ? fmtNum(n.value) : (bad = true, '');
        case 'SymbolNode': {
          if (vars.has(n.name)) return V;
          if (n.name === 'pi') return 'pi';
          if (n.name === 'e') return 'e';
          const p = (STATE.params || {})[n.name];
          if (p && isFinite(p.value)) return fmtNum(p.value);
          bad = true; return '';
        }
        case 'ParenthesisNode': return walk(n.content, parentPrec, right, lead);
        case 'OperatorNode': {
          if (n.args.length === 1) {
            if (n.op !== '-' && n.op !== '+') { bad = true; return ''; }
            const inner = walk(n.args[0], 5, false, false);
            const s = (n.op === '-' ? '-' : '') + inner;
            return (lead && parentPrec < 4) ? s : '(' + s + ')';
          }
          if (n.args.length !== 2) { bad = true; return ''; }
          if (n.op === '%' || n.fn === 'mod') return 'mod(' + walk(n.args[0], 0, false, true) + ', ' + walk(n.args[1], 0, false, true) + ')';
          if (PREC[n.op] == null) { bad = true; return ''; }
          const pr = PREC[n.op];
          // скобки: приоритет ниже родителя; равный приоритет справа; под степенью и под унарным минусом — всегда
          const need = pr < parentPrec || (pr === parentPrec && right && parentPrec !== 0) || parentPrec >= 4;
          const a = walk(n.args[0], pr, false, need || !!lead);
          const b = walk(n.args[1], pr, true, false);
          const s = (n.op === '^') ? a + '^' + b : a + ' ' + n.op + ' ' + b;
          return need ? '(' + s + ')' : s;
        }
        case 'FunctionNode': {
          const name = n.fn && n.fn.name, A = n.args;
          const arg = (k) => walk(A[k], 0, false, true);
          if ((name === 'nthRoot' && (A.length === 1 || A.length === 2)) || (name === 'cbrt' && A.length === 1)) {
            const a = arg(0);
            const deg = name === 'cbrt' ? 3 : (A.length === 2 ? constOf(A[1]) : 2);
            if (deg === 2) return 'sqrt(' + a + ')';
            if (deg != null && Number.isInteger(deg) && deg % 2 !== 0) return '(sign(' + a + ') * abs(' + a + ')^(1/' + deg + '))';
            return '((' + a + ')^(1/(' + (deg != null ? fmtNum(deg) : arg(1)) + ')))';
          }
          if (name === 'log' && A.length === 1) return 'ln(' + arg(0) + ')';
          if (name === 'log' && A.length === 2) return '(ln(' + arg(0) + ') / ln(' + arg(1) + '))';
          if (name === 'pow' && A.length === 2) return '((' + arg(0) + ')^(' + arg(1) + '))';
          if (name === 'mod' && A.length === 2) return 'mod(' + arg(0) + ', ' + arg(1) + ')';
          if (PGF_TRIG[name] && A.length === 1) return PGF_TRIG[name] + '(deg(' + arg(0) + '))';
          if (PGF_ATRIG[name] && A.length === 1) return 'rad(' + PGF_ATRIG[name] + '(' + arg(0) + '))';
          const f = PGF_FN[name];
          if (!f || !A.length) { bad = true; return ''; }
          return f + '(' + A.map((_, k) => arg(k)).join(', ') + ')';
        }
        case 'ConditionalNode': {
          const cond = (cn) => {
            let x = cn; while (x && x.type === 'ParenthesisNode') x = x.content;
            if (!x || x.type !== 'OperatorNode') { bad = true; return ''; }
            if (x.fn === 'and') return '(' + cond(x.args[0]) + ' && ' + cond(x.args[1]) + ')';
            if (x.fn === 'or') return '(' + cond(x.args[0]) + ' || ' + cond(x.args[1]) + ')';
            if (x.fn === 'not') return '!(' + cond(x.args[0]) + ')';
            const map = { smaller: '<', smallerEq: '<=', larger: '>', largerEq: '>=', equal: '==', unequal: '!=' };
            if (!map[x.fn]) { bad = true; return ''; }
            return walk(x.args[0], 1, false, true) + ' ' + map[x.fn] + ' ' + walk(x.args[1], 1, false, false);
          };
          let f = n.falseExpr; while (f && f.type === 'ParenthesisNode') f = f.content;
          const isNaNTail = f && ((f.type === 'ConstantNode' && typeof f.value === 'number' && isNaN(f.value)) || (f.type === 'SymbolNode' && f.name === 'NaN'));
          const t = walk(n.trueExpr, 0, false, false);
          const e = isNaNTail ? 'nan' : walk(n.falseExpr, 0, false, false);
          return '(' + cond(n.condition) + ' ? ' + t + ' : ' + e + ')';
        }
        default: bad = true; return '';
      }
    };
    const out = walk(node, 0, false, true);
    return bad ? null : out;
  }
  /* Куски кусочной записи (SPEC, раздел 8). Запись вида
       (Q >= 0 and Q < 40) ? 100 - Q : ((Q >= 40 and Q <= 160) ? 80 - 0.5*Q : NaN)
     собирают окно «Кусочная функция» и сложение кривых; в файл она идёт по
     куску на участок, с точной границей из условия. Разбор — по дереву
     Math.js (сравнения любого вида, границы числом или параметром), а не
     текстовым pwParse окна: тот понимает только «>=» и «<». Возвращает
     [{ lo, hi, expr }] либо null, если условие не про участки переменной.
     ⚠️ Разбору не верим на слово: вызывающий сверяет каждый кусок с целой
     записью числом и проверяет, что куски покрывают всё, где запись определена. */
  function condPieces(expr, varName) {
    let node;
    try { node = math.parse(prepExpr(String(expr == null ? '' : expr))); } catch (e) { return null; }
    const un = (n) => { let x = n; while (x && x.type === 'ParenthesisNode') x = x.content; return x; };
    const isVar = (n) => !!n && n.type === 'SymbolNode' && (AXIS_VARS.indexOf(n.name) >= 0 || (!!varName && n.name.toLowerCase() === varName.toLowerCase()));
    const numOf = (n) => { try { const v = n.compile().evaluate(paramScope({})); return (typeof v === 'number' && isFinite(v)) ? v : null; } catch (e) { return null; } };
    const LOWER = { larger: 1, largerEq: 1 }, UPPER = { smaller: 1, smallerEq: 1 };
    const one = (c) => {                                   // «переменная ? число» → нижняя или верхняя граница
      if (!c || c.type !== 'OperatorNode' || c.args.length !== 2) return null;
      const L = un(c.args[0]), R = un(c.args[1]);
      if (isVar(L)) { const v = numOf(R); if (v == null) return null; return LOWER[c.fn] ? { lo: v, hi: Infinity } : UPPER[c.fn] ? { lo: -Infinity, hi: v } : null; }
      if (isVar(R)) { const v = numOf(L); if (v == null) return null; return LOWER[c.fn] ? { lo: -Infinity, hi: v } : UPPER[c.fn] ? { lo: v, hi: Infinity } : null; }
      return null;
    };
    const bounds = (c0) => {
      const c = un(c0);
      if (c && c.type === 'OperatorNode' && c.fn === 'and') { const a = bounds(c.args[0]), b = bounds(c.args[1]); return (a && b) ? { lo: Math.max(a.lo, b.lo), hi: Math.min(a.hi, b.hi) } : null; }
      return one(c);
    };
    /* Цепочка «если … иначе если …»: кусок действует там, где его условие
       верно, а условия всех прежних кусков — нет. Если после вычитания
       прежних участок распался надвое, запись не наша: null. */
    const taken = [];
    const free = (b) => {
      let lo = b.lo, hi = b.hi;
      for (const t of taken) {
        if (t.hi <= lo || t.lo >= hi) continue;
        if (t.lo <= lo && t.hi >= hi) return { lo: 0, hi: 0 };
        if (t.lo <= lo) lo = t.hi;
        else if (t.hi >= hi) hi = t.lo;
        else return null;
      }
      return { lo, hi };
    };
    const out = []; let cur = un(node), guard = 0;
    while (cur && cur.type === 'ConditionalNode' && guard++ < 32) {
      const b = bounds(cur.condition);
      if (!b) return null;
      const f = free(b);
      if (!f) return null;
      if (f.hi > f.lo) out.push({ lo: f.lo, hi: f.hi, expr: cur.trueExpr.toString() });
      taken.push(b);
      cur = un(cur.falseExpr);
    }
    if (!taken.length) return null;
    const nanTail = cur && ((cur.type === 'SymbolNode' && cur.name === 'NaN') || (cur.type === 'ConstantNode' && typeof cur.value === 'number' && isNaN(cur.value)));
    // Хвост без условия («иначе») действует правее всех границ.
    if (cur && !nanTail) {
      const f = free({ lo: Math.max.apply(null, taken.map(q => q.hi).filter(isFinite).concat([-Infinity])), hi: Infinity });
      if (!f) return null;
      if (f.hi > f.lo) out.push({ lo: f.lo, hi: f.hi, expr: cur.toString() });
    }
    return out.length ? out : null;
  }
  /* Вычислитель ЗАПИСИ: считает ту самую строку, которая уйдёт в файл (а не
     функцию движка: у кривой есть быстрые пути linear и fn, и строка может с
     ними разойтись). Переменная записи и синонимы оси привязаны к аргументу
     так же, как в exprToPgf. */
  function exprFn(expr, varName) {
    try {
      const c = math.parse(prepExpr(String(expr))).compile();
      const names = varName ? [varName, varName.toLowerCase(), varName.toUpperCase()] : [];
      return (q) => {
        try {
          const sc = axisScope(q, {}); names.forEach(nm => { sc[nm] = q; });
          const v = c.evaluate(paramScope(sc));
          return (typeof v === 'number' && isFinite(v)) ? v : NaN;
        } catch (e) { return NaN; }
      };
    } catch (e) { return null; }
  }

  /* ───────────────────────── бумажный прогон ───────────────────────── */
  /* Холст перерисовывается так, как он выглядел бы на листе, и после описи
     возвращается. Всё в одной задаче браузера, экран не мигает (тот же приём,
     что у paperChartClone для PNG). Каждый пункт ниже получен замером
     разведки (RECON задания, раздел 6):
       • светлая тема, --canvas и --halo равны --paper;
       • постоянный размер поля: признак _texPaper читает computeSize;
       • переходы и анимации погашены на всём графике: при обычных переходах
         цвет подписи и рамка холста читались бы на полпути;
       • память подписей кривых (_labelPos, _anchorQ, _labelW: подпись едет к
         месту долями по 0,35 за кадр) и легенды (STATE.legendSpot) сброшены,
         две перерисовки подряд — иначе место подписи на листе зависело бы от
         того, что было на экране; после прогона всё возвращается;
       • размер подписей бумажный (LABEL_BASE), курсора нет;
       • история молчит (_histMute, 91-session.js): перерисовки прогона не дают
         шага «Отменить», автосохранения и события «модель изменилась»;
       • плавающих блоков над холстом на листе нет (floatRects пуст). */
  function enterPaper() {
    if (_texPaper) throw new Error('бумажный прогон уже идёт');
    const root = document.documentElement;
    const theme = root.getAttribute('data-theme');
    const paper = cssVar('--paper') || '#ffffff';
    const chartEl = document.getElementById('chart');
    const keep = {
      style: chartEl.getAttribute('style'), margin: Object.assign({}, CONFIG.margin),
      ls: STATE.labelSize, legendSpot: STATE.legendSpot, px: STATE.pointerPx, py: STATE.pointerPy,
      pos: new Map(_labelPos), anc: new Map(_anchorQ), lw: new Map(_labelW),
    };
    /* Переходы гашены на холсте: при обычных переходах цвет подписи и рамка
       холста читались бы на полпути, и файл зависел бы от настройки «меньше
       движения». Только на холсте, а не на всём #graph-wrap: снятие перехода
       завершает его, и экран после выгрузки был бы уже не тем. */
    const still = document.createElement('style');
    still.textContent = '#chart, #chart * { transition: none !important; animation: none !important; }';
    document.head.appendChild(still);
    /* Свой замерщик ширины подписей (measureText, 20-plane.js) на время
       прогона. Экранный при «меньше движения» читает кегль с отставанием
       (переход font-size длиной 0,01 мс не успевает до замера: '100' мерится
       12-м кеглем вместо 10-го), и поле холста на листе зависело бы от этой
       настройки. Свой — без переходов, а экранный не трогается вовсе: его
       состояние и есть то, по чему экран считает поля. */
    keep.meas = [_measSvg, _measText];
    const NS = 'http://www.w3.org/2000/svg';
    const meas = document.createElementNS(NS, 'svg');
    meas.setAttribute('aria-hidden', 'true');
    meas.setAttribute('data-skip-export', '1');
    meas.style.cssText = 'position:absolute;left:-9999px;top:-9999px;width:10px;height:10px;overflow:hidden;pointer-events:none;transition:none !important;';
    const measText = document.createElementNS(NS, 'text');
    measText.style.cssText = 'transition:none !important;';
    meas.appendChild(measText);
    (document.getElementById('graph-wrap') || document.body).appendChild(meas);
    _measSvg = meas; _measText = measText;
    _histMute++;
    _texPaper = { plot: PLOT_SINGLE };
    let left = false;
    function leave() {
      if (left) return;
      left = true;
      // размеры возвращаем при ещё погашенных переходах рамки, иначе обратная перерисовка меряет рамку листа
      chartEl.setAttribute('style', (keep.style ? keep.style + ';' : '') + 'transition: none !important');
      void chartEl.getBoundingClientRect();
      // экранный замерщик подписей — обратно (см. выше): поля экрана считаются им
      still.remove();
      meas.remove(); _measSvg = keep.meas[0]; _measText = keep.meas[1];
      _texPaper = null;
      STATE.legendSpot = keep.legendSpot; STATE.labelSize = keep.ls;
      STATE.pointerPx = keep.px; STATE.pointerPy = keep.py;
      if (theme) root.setAttribute('data-theme', theme); else root.removeAttribute('data-theme');
      root.style.removeProperty('--canvas'); root.style.removeProperty('--halo');
      _labelPos.clear(); keep.pos.forEach((v, k) => _labelPos.set(k, v));
      _anchorQ.clear(); keep.anc.forEach((v, k) => _anchorQ.set(k, v));
      _labelW.clear(); keep.lw.forEach((v, k) => _labelW.set(k, v));
      Object.assign(CONFIG.margin, keep.margin);
      try { refreshColors(); redrawAll(); }
      finally {
        void chartEl.getBoundingClientRect();
        if (keep.style == null) chartEl.removeAttribute('style'); else chartEl.setAttribute('style', keep.style);
        _histMute--;
      }
    }
    try {
      root.setAttribute('data-theme', 'light');
      root.style.setProperty('--canvas', paper);
      root.style.setProperty('--halo', paper);
      STATE.legendSpot = null;                    // место легенды выбирается заново, без памяти экрана
      STATE.labelSize = LABEL_BASE;
      STATE.pointerPx = null; STATE.pointerPy = null;
      const twice = () => { resetLabelPositions(); refreshColors(); redrawAll(); redrawAll(); };
      twice();
      const ps = STATE.panels || [];
      if (ps.length >= 2) {
        // панели рядом — 16 × 7,5 см на всех, одна над другой — 12 × 12 см
        const side = ps.every((p, i) => i === 0 || p.x0 >= ps[i - 1].x1 - 1 || p.x1 <= ps[i - 1].x0 + 1);
        _texPaper.plot = side ? PLOT_WIDE : PLOT_TALL;
        twice();
      }
    } catch (e) { leave(); throw e; }
    return leave;
  }

  /* ───────────────────────────── опись ───────────────────────────── */
  /* Обход #chart в порядке узлов (он же порядок слоёв) на бумажном прогоне.
     Каждый видимый предмет — в координатах модели СВОЕЙ панели: у
     двухпанельных сцен в глобальных sx/sy лежат шкалы последней панели,
     поэтому шкалы берутся у панели (STATE.panels[i].mx, .my). */
  function capture() {
    const chart = document.getElementById('chart');
    const canvasHex = hex(getComputedStyle(document.documentElement).getPropertyValue('--canvas')) || 'FFFFFF';
    const panels = (STATE.panels || []).map(p => ({
      id: p.id, x0: p.x0, x1: p.x1, y0: p.y0, y1: p.y1, mx: p.mx, my: p.my,
      xd: p.mx.domain().slice(), yd: p.my.domain().slice(),
      ax: { xLine: null, yLine: null, xt: [], yt: [], zero: null, xName: null, yName: null, gx: [], gy: [], gxm: [], gym: [], gridColor: null, extra: [], marks: 0 },
      items: [], legend: null, clips: {},
    }));
    const plot = _texPaper ? _texPaper.plot : null;
    if (!panels.length) return { W, H, plot, panels: [], warn: ['нет панелей'], scene: STATE.sceneKey || '', name: '' };
    const warn = [];
    const clips = {};
    chart.querySelectorAll('clipPath').forEach(c => {
      const r = c.querySelector('rect'); if (!r) return;
      clips[c.id] = { x: +r.getAttribute('x'), y: +r.getAttribute('y'), w: +r.getAttribute('width'), h: +r.getAttribute('height') };
    });
    panels.forEach(p => Object.keys(clips).forEach(id => { const c = clips[id]; p.clips[id] = [p.mx.invert(c.x), p.my.invert(c.y + c.h), p.mx.invert(c.x + c.w), p.my.invert(c.y)]; }));
    // пути и отрезки без своей обрезки, выходящие за холст, режет край SVG — окно «весь холст»
    panels.forEach(p => { p.clips['@canvas'] = [p.mx.invert(0), p.my.invert(H), p.mx.invert(W), p.my.invert(0)]; });
    const nearest = (px, py) => { let b = panels[0], bd = Infinity; panels.forEach(p => { const d = panelDistPx(p, px, py); if (d < bd) { bd = d; b = p; } }); return b; };
    const D = (p, px, py) => [p.mx.invert(px), p.my.invert(py)];
    const strokeOf = (el, cs, op) => {
      const c = rgba(cs.stroke);
      if (!c || c[3] < 0.02 || !(parseFloat(cs.strokeWidth) > 0)) return null;
      const dash = (el.getAttribute('stroke-dasharray') || (cs.strokeDasharray !== 'none' ? cs.strokeDasharray : '') || '').trim();
      const so = parseFloat(cs.strokeOpacity);
      return { color: hex(cs.stroke), w: parseFloat(cs.strokeWidth) || 1, dash: dash && dash !== 'none' ? dash.split(/[\s,]+/).map(v => parseFloat(v)).filter(v => isFinite(v)) : null, op: op * c[3] * (isFinite(so) ? so : 1) };
    };
    const fillOf = (el, cs, op) => {
      const f = String(cs.fill || '');
      const h = /url\(["']?#(hatch-[a-z]+)/.exec(f);
      if (h) return { hatch: h[1], color: hex(h[1] === 'hatch-profit' ? COL.profit : COL.bad) || '2E9E44', op: 1 };
      const c = rgba(f);
      const fo = parseFloat(cs.fillOpacity);
      if (!c || c[3] < 0.02 || (isFinite(fo) && fo < 0.01)) return null;
      return { color: hex(f), op: op * c[3] * (isFinite(fo) ? fo : 1) };
    };

    /* Пробные точки формулы: аргумент и значение по движку. По ним прибор
       calc2/tests/tex/formulas.py сверяет, что НАСТОЯЩИЙ pgfmath считает
       напечатанную формулу так же, как Math.js — исходную. */
    const probeOf = (f, a, b) => [0.1, 0.3, 0.5, 0.7, 0.9].map(t => { const x = a + (b - a) * t; return [x, f(x)]; }).filter(q => isFinite(q[1]));
    /* Запись, которую место рисования оставило на узле (SPEC, раздел 3). */
    const readRecord = (el) => {
      const cid = el.getAttribute('data-curve');
      if (cid != null) {
        const c = (STATE.curves || []).find(k => String(k.id) === String(cid));
        if (!c) return null;
        const name = (typeof curveShortName === 'function' ? curveShortName(c) : '') || '';
        if (c.kind === 'vertical') return { kind: 'poly', why: 'вертикальная прямая', name };
        if (c.sumNumeric) return { kind: 'numeric', why: 'сумма посчитана по точкам: среди слагаемых есть непрямая, записи формулой у суммы нет', name };
        // кривая, введённая как Q = f(P): в файл идёт запись человека, аргумент — вертикальная ось
        if (c.srcForm === 'QP' && c.srcExpr) return { kind: 'expr', src: 'curve', expr: c.srcExpr, v: 'P', axis: 'y', name };
        const e = c.texExpr || c.expr;
        return e ? { kind: 'expr', src: 'curve', expr: e, v: 'Q', axis: 'x', name } : null;
      }
      const area = el.getAttribute('data-area');
      if (area) { try { return Object.assign({ kind: 'area' }, JSON.parse(area)); } catch (e) { return null; } }
      const ex = el.getAttribute('data-expr');
      if (ex) return { kind: 'expr', src: 'scene', expr: ex, v: el.getAttribute('data-expr-var') || 'Q', axis: el.getAttribute('data-expr-axis') === 'y' ? 'y' : 'x', from: parseFloat(el.getAttribute('data-expr-from')), to: parseFloat(el.getAttribute('data-expr-to')), name: el.getAttribute('data-expr-name') || '' };
      const nm = el.getAttribute('data-numeric');
      if (nm) return { kind: 'numeric', why: nm, name: el.getAttribute('data-expr-name') || '' };
      const pl = el.getAttribute('data-poly');
      if (pl) return { kind: 'poly', why: pl, name: el.getAttribute('data-expr-name') || '' };
      return null;
    };
    /* Насколько формула не проходит через узел (a; b), в долях размаха оси
       значения. Узел округлён D3 до 0,001 px по ОБЕИМ осям, поэтому формула
       обязана пройти через окрестность узла: сдвиг по аргументу не больше
       VERIFY_TOL его размаха, остаток — по оси значения. Сверка только по
       вертикали давала ложное «не сошлось» у крутой кривой (Q^2 в окне 250 на 5). */
    const nodeMiss = (f, a, b, spanA, spanB) => {
      const e = spanA * VERIFY_TOL;
      const xs = [a - e, a, a + e], fs = xs.map(f);
      const vs = fs.filter(isFinite);
      /* Узел у края области записи (условие «X ≤ 120») округлён за край: в
         окрестности есть точки и с записью, и без неё. Край области — тоже
         точка записи, он находится делением пополам. Замер 08.10: сумма КПВ
         в окне «от 1,5», узел (120,00002; 0) при наклоне −3 давал промах
         4,9·10⁻⁵ по одной точке (120 − e). */
      for (let k = 0; k < 2; k++) {
        if (isFinite(fs[k]) === isFinite(fs[k + 1])) continue;
        let p = isFinite(fs[k]) ? xs[k] : xs[k + 1], q = isFinite(fs[k]) ? xs[k + 1] : xs[k];
        for (let i = 0; i < 40; i++) { const m = (p + q) / 2; if (isFinite(f(m))) p = m; else q = m; }
        vs.push(f(p));
      }
      if (!vs.length) return 1;
      return Math.max(Math.min.apply(null, vs) - b, b - Math.max.apply(null, vs), 0) / spanB;
    };
    /* Сверка записи кривой с нарисованным путём (SPEC, раздел 4). Сверяется
       строка, которая уйдёт в файл. A — ось аргумента (0 — горизонталь,
       1 — вертикаль), B — ось значения. */
    const verifyCurve = (data, r, win, sxn, syn) => {
      const A = r.axis === 'y' ? 1 : 0, B = 1 - A;
      const f = exprFn(r.expr, r.v);
      if (!f) return { ok: false, why: 'формула записи не разбирается' };
      const pgf = exprToPgf(r.expr, r.v, A ? 't' : 'x');
      if (!pgf) return { ok: false, why: 'формула записи не переводится в pgfplots' };
      const spanB = B ? syn : sxn, spanA = A ? syn : sxn, wB = B ? win.y : win.x;
      const lo = wB[0] - spanB * 0.02, hi = wB[1] + spanB * 0.02;
      const n = data.length, step = Math.max(1, Math.floor(n / 60));
      let maxErr = 0, exact = 0, beyond = 0;
      const check = (a, b) => {
        const v = f(a);
        /* Узел за окном сцена вправе прижать к краю или не досчитать:
           расхождение там прощается, если и формула уходит за тот же край.
           Узел за окном, лежащий на формуле, проверяется как обычный. */
        if ((b < lo || b > hi) && (!isFinite(v) || (b < lo && v < lo) || (b > hi && v > hi))) { beyond++; return; }
        maxErr = Math.max(maxErr, nodeMiss(f, a, b, spanA, spanB)); exact++;
      };
      for (let k = 0; k < n; k += step) check(data[k][A], data[k][B]);
      if ((n - 1) % step) check(data[n - 1][A], data[n - 1][B]);
      /* Между соседними узлами формула не должна уходить в сторону, иначе в
         файле окажется то, чего на экране нет: колебания чаще сетки пути
         либо вторая ветвь у записи «по вертикали». */
      let between = 0;
      for (let k = 0; k + 1 < n; k += step) {
        const b0 = data[k][B], b1 = data[k + 1][B];
        if (b0 < lo || b0 > hi || b1 < lo || b1 > hi) continue;
        const v = f((data[k][A] + data[k + 1][A]) / 2);
        if (!isFinite(v)) { between = Math.max(between, 1); continue; }
        between = Math.max(between, Math.max(Math.min(b0, b1) - v, v - Math.max(b0, b1), 0) / spanB);
      }
      const ok = (exact + beyond) > 0 && maxErr < VERIFY_TOL && between < BETWEEN_TOL;
      return { ok, maxErr, between, f, pgf, A, B, why: ok ? '' : (maxErr >= VERIFY_TOL ? 'формула не проходит через нарисованные узлы' : 'между узлами формула уходит от нарисованной линии') };
    };
    /* Сверка записи области: каждый узел пути лежит на одной из двух границ
       и внутри отрезка, а площадь нарисованного многоугольника равна
       интегралу разности границ с точностью 0,5 %. */
    const verifyArea = (data, r, win, sxn, syn) => {
      const vn = r.v || 'Q';
      const side = (b) => {
        if (typeof b === 'number') return isFinite(b) ? { num: b, f: () => b } : null;
        const f = exprFn(b, vn), pgf = exprToPgf(b, vn, 'x');
        return (f && pgf) ? { expr: String(b), f, pgf } : null;
      };
      const lo = side(r.lo), hi = side(r.hi);
      const a = Math.min(r.from, r.to), b = Math.max(r.from, r.to);
      if (!lo || !hi || !isFinite(a) || !isFinite(b) || !(b > a)) return { ok: false, why: 'запись области не разбирается или не переводится в pgfplots' };
      let maxErr = 0;
      data.forEach(([x, y]) => {
        if (x < a - sxn * VERIFY_TOL || x > b + sxn * VERIFY_TOL) { maxErr = Math.max(maxErr, 1); return; }
        const e = Math.min(nodeMiss(lo.f, x, y, sxn, syn), nodeMiss(hi.f, x, y, sxn, syn));
        maxErr = Math.max(maxErr, isFinite(e) ? e : 1);
      });
      let poly = 0;
      for (let i = 0; i < data.length; i++) { const q = data[i], w = data[(i + 1) % data.length]; poly += q[0] * w[1] - w[0] * q[1]; }
      poly = Math.abs(poly) / 2;
      const N = 400, h = (b - a) / N; let integ = 0;
      for (let i = 0; i <= N; i++) { const d = hi.f(a + h * i) - lo.f(a + h * i); integ += (isFinite(d) ? d : 0) * (i === 0 || i === N ? 1 : (i % 2 ? 4 : 2)); }
      integ = Math.abs(integ * h / 3);
      const areaErr = Math.abs(poly - integ) / Math.max(integ, sxn * syn * 1e-4);
      const ok = maxErr < VERIFY_TOL && areaErr < AREA_TOL;
      /* В файл идёт часть отрезка в окне плюс 30 % размаха (SPEC, раздел 2.2):
         дальше её всё равно режет \clip, а далёкие числа роняют pgfplots. */
      const ca = Math.max(a, win.x[0] - EXT * sxn), cb = Math.min(b, win.x[1] + EXT * sxn);
      const lin = (s) => s.num != null ? true : pickSamples(s.f, ca, cb, win.y[0], win.y[1], syn) === 2;
      const smp = (s) => s.num != null ? 2 : pickSamples(s.f, ca, cb, win.y[0], win.y[1], syn);
      const far = [lo, hi].some(s => { for (let i = 0; i <= 40; i++) { const v = s.f(ca + (cb - ca) * i / 40); if (!isFinite(v) || v < win.y[0] - EXT * syn || v > win.y[1] + EXT * syn) return true; } return false; });
      // край, в котором кривая граница не считается, отодвигаем внутрь — как у кривых (visibleRuns)
      const pr = (v) => +v.toFixed(decOf(sxn) + 3);
      let da = ca, db = cb;
      [lo, hi].forEach(s => { if (s.num != null) return; if (!isFinite(s.f(pr(ca)))) da = ca + (cb - ca) * 1e-6; if (!isFinite(s.f(pr(cb)))) db = cb - (cb - ca) * 1e-6; });
      const out = (s) => ({ num: s.num, expr: s.expr, pgf: s.pgf, lin: lin(s), at: [s.f(ca), s.f(cb)], probe: s.pgf ? probeOf(s.f, da, db) : null });
      /* Запись верна, но вся область лежит за окном плюс 30 % (обе границы выше
         или обе ниже на всём отрезке, либо отрезок вне окна): на экране её
         срезает обрезка, в файл она не идёт и дефектом не считается. */
      const yLo = win.y[0] - EXT * syn, yHi = win.y[1] + EXT * syn;
      let hidden = !(cb > ca);
      if (!hidden) {
        hidden = true;
        for (let i = 0; i <= 80 && hidden; i++) {
          const x = ca + (cb - ca) * i / 80, u = lo.f(x), w = hi.f(x);
          if (!isFinite(u) || !isFinite(w)) { hidden = false; break; }
          if (!((u > yHi && w > yHi) || (u < yLo && w < yLo))) hidden = false;
        }
      }
      return { ok, hidden, maxErr, areaErr, a, b, ca, cb, da, db, lo: out(lo), hi: out(hi), span: syn, samples: Math.max(smp(lo), smp(hi)), far, bLo: yLo, bHi: yHi, bx0: win.x[0] - EXT * sxn, bx1: win.x[1] + EXT * sxn,
        why: ok ? '' : (maxErr >= VERIFY_TOL ? 'узлы области не лежат на записанных границах' : 'площадь области не равна интегралу между границами') };
    };

    const legendRoot = chart.querySelector('g.legend');
    const order = { n: 0 };

    const walk = (node, ctx) => {
      for (const el of node.children) {
        const tag = el.tagName.toLowerCase();
        if (tag === 'defs' || tag === 'title' || tag === 'desc' || tag === 'clippath' || tag === 'marker') continue;
        /* Служебное (ручки, зажжённые точки) и невидимые полосы попадания в файл
           не идут — с потомками. Кроме кружка своей точки (g.marks): его тянут
           мышью, и markServiceNodes считает его ручкой, но это сама точка
           человека, и она видна на холсте (COVERAGE редизайна, 6.8: свои точки
           уходят в файл). */
        const ownPoint = tag === 'circle' && el.parentNode && el.parentNode.classList && el.parentNode.classList.contains('marks');
        if ((el.getAttribute('data-skip-export') || el.getAttribute('data-service')) && !ownPoint) continue;
        const cls = String(el.getAttribute('class') || '');
        if (tag === 'g') {
          if (el === legendRoot) continue;                 // легенда разбирается отдельно
          let c2 = ctx;
          const cp = /url\(["']?#([^)"']+)/.exec(el.getAttribute('clip-path') || '');
          if (cp && clips[cp[1]]) c2 = Object.assign({}, ctx, { clip: cp[1] });
          if (/\bgrid\b/.test(cls)) c2 = Object.assign({}, c2, { role: 'grid' });
          else if (/\baxes\b/.test(cls)) c2 = Object.assign({}, c2, { role: 'axes' });
          walk(el, c2);
          continue;
        }
        if (!shown(el)) continue;
        const cs = getComputedStyle(el);
        const op = chainOpacity(el, chart);
        if (op < 0.02) continue;
        const clipR = ctx.clip ? clips[ctx.clip] : null;
        const panelOf = (px, py) => clipR ? nearest(clipR.x + clipR.w / 2, clipR.y + clipR.h / 2) : nearest(px, py);
        const base = { z: order.n++, clip: ctx.clip || null };

        if (tag === 'line') {
          const x1 = +el.getAttribute('x1'), y1 = +el.getAttribute('y1'), x2 = +el.getAttribute('x2'), y2 = +el.getAttribute('y2');
          const st = strokeOf(el, cs, op); if (!st) continue;
          const p = panelOf((x1 + x2) / 2, (y1 + y2) / 2);
          if (ctx.role === 'grid') {
            /* Линия сетки: запоминается её МЕСТО. Линии стоят на всех делениях
               шкалы, включая край окна, где числа и засечки нет (там стрелка
               оси): по одним числам делений сетку не восстановить. */
            const minor = /0\.45/.test(el.getAttribute('opacity') || '');
            const vert = Math.abs(x1 - x2) < 0.5;
            const val = vert ? p.mx.invert(x1) : p.my.invert(y1);
            (vert ? (minor ? p.ax.gxm : p.ax.gx) : (minor ? p.ax.gym : p.ax.gy)).push(val);
            if (!minor && !p.ax.gridColor) { p.ax.gridColor = st.color; p.ax.gridOp = st.op; p.ax.gridW = st.w; }
            if (minor && p.ax.gridMinorOp == null) p.ax.gridMinorOp = st.op;
            continue;
          }
          const arrow = !!el.getAttribute('marker-end');
          if (arrow) {
            const horiz = Math.abs(y1 - y2) < 0.5;
            const rec = { px: [x1, y1, x2, y2], a: D(p, x1, y1), b: D(p, x2, y2), st };
            if (horiz && !p.ax.xLine) { p.ax.xLine = rec; continue; }
            if (!horiz && Math.abs(x1 - x2) < 0.5 && !p.ax.yLine) { p.ax.yLine = rec; continue; }
          }
          // отрезок целиком за краем холста на экран не попал — и в файл не идёт
          if ((x1 < 0 && x2 < 0) || (x1 > W && x2 > W) || (y1 < 0 && y2 < 0) || (y1 > H && y2 > H)) continue;
          const segOut = [x1, x2].some(v => v < -0.5 || v > W + 0.5) || [y1, y2].some(v => v < -0.5 || v > H + 0.5);
          p.items.push(Object.assign(base, { kind: 'seg', px: [x1, y1, x2, y2], a: D(p, x1, y1), b: D(p, x2, y2), st, arrow, role: ctx.role || '' }, (!base.clip && segOut) ? { clip: '@canvas' } : {}));
        } else if (tag === 'rect') {
          const x = +el.getAttribute('x'), y = +el.getAttribute('y'), w = +el.getAttribute('width'), h = +el.getAttribute('height');
          if (!(w > 0 && h > 0)) continue;
          if (x + w < 0 || x > W || y + h < 0 || y > H) continue;                 // целиком за краем холста
          const fl = fillOf(el, cs, op), st = strokeOf(el, cs, op);
          if (!fl && !st) continue;
          if (fl && !fl.hatch && fl.color === canvasHex && !st) continue;      // подложка цветом листа
          const p = panelOf(x + w / 2, y + h / 2);
          // без своей обрезки и за краем холста: на экране его режет сам SVG — окно «весь холст»
          const rectOut = x < -0.5 || y < -0.5 || x + w > W + 0.5 || y + h > H + 0.5;
          p.items.push(Object.assign(base, { kind: 'rect', a: D(p, x, y + h), b: D(p, x + w, y), fl: (fl && fl.color === canvasHex && !fl.hatch) ? null : fl, st, legend: el.getAttribute('data-legend') || '' }, (!base.clip && rectOut) ? { clip: '@canvas' } : {}));
        } else if (tag === 'circle') {
          const cx = +el.getAttribute('cx'), cy = +el.getAttribute('cy'), r = +el.getAttribute('r');
          if (!(r > 0)) continue;
          if (cx < -r || cx > W + r || cy < -r || cy > H + r) continue;        // целиком за краем холста
          const fl = fillOf(el, cs, op), st = strokeOf(el, cs, op);
          if (!fl && !st) continue;
          const p = panelOf(cx, cy);
          const hollow = !fl || fl.color === canvasHex;
          const dotOut = cx - r < -0.5 || cy - r < -0.5 || cx + r > W + 0.5 || cy + r > H + 0.5;
          p.items.push(Object.assign(base, { kind: 'dot', c: D(p, cx, cy), r, hollow, color: hollow ? (st ? st.color : '000000') : fl.color, st, op: fl ? fl.op : 1 }, (!base.clip && dotOut) ? { clip: '@canvas' } : {}));
        } else if (tag === 'text') {
          /* Источник текста — исходная разметка (data-raw), у узлов без неё —
             видимый текст без <title> (подсказки «Двойной щелчок…»).
             «Сначала сам» меняет data-raw вместе с видимым текстом (96-self.js,
             selfCanvas), поэтому чисел ответа здесь нет. */
          const shownText = (function () { const k = el.cloneNode(true); k.querySelectorAll('title,desc').forEach(n => n.remove()); return k.textContent.replace(/​/g, ''); })();
          const raw = el.getAttribute('data-raw') || shownText;
          if (!raw.trim()) continue;
          const x = +el.getAttribute('x') || 0, y = +el.getAttribute('y') || 0;
          const bb = el.getBBox();
          if (bb.x + bb.width < 0 || bb.x > W || bb.y + bb.height < 0 || bb.y > H) continue;   // целиком за краем холста
          const p = panelOf(bb.x + bb.width / 2, bb.y + bb.height / 2);
          const anchorH = cs.textAnchor || 'start';
          const bl = el.getAttribute('dominant-baseline') || cs.dominantBaseline || 'auto';
          const sizePx = parseFloat(cs.fontSize) || 12;
          /* Точка привязки подписи за полем прижимается к краю поля, остаток —
             сдвигом в пунктах: «Дефицит = 40» под осью, числа у оси. */
          const ax = Math.min(p.x1, Math.max(p.x0, x)), ay = Math.min(p.y1, Math.max(p.y0, y));
          const rec = Object.assign(base, {
            kind: 'text', px: [x, y], bb: [bb.x, bb.y, bb.width, bb.height], raw, tex: labelTex(raw),
            at: D(p, ax, ay), shift: [(x - ax) * PX2PT, (ay - y) * PX2PT],
            h: anchorH, v: (bl === 'hanging' || bl === 'text-before-edge') ? 'top' : (bl === 'middle' || bl === 'central') ? 'mid' : 'base',
            step: fsStep(sizePx, 1), color: hex(cs.fill) || '000000', bold: parseInt(cs.fontWeight, 10) >= 700,
            cls, halo: !!el.getAttribute('paint-order'), role: ctx.role || '',
          });
          if (/\baxis-num\b/.test(cls)) { p.ax.extra.push(rec); continue; }      // разберём, когда узнаем оси
          if (/\baxis-name\b/.test(cls)) { rec.axisName = true; }
          p.items.push(rec);
        } else if (tag === 'path') {
          const parsed = parseD(el.getAttribute('d'));
          if (parsed.bad) warn.push(parsed.bad === 'nan'
            ? 'в пути нечисловая координата (NaN): на экране и в файле только часть до неё'
            : 'в пути команда «' + parsed.bad.slice(4) + '», которую разбор не понимает: взята часть до неё');
          const fl = fillOf(el, cs, op), st = strokeOf(el, cs, op);
          if (!fl && !st) continue;
          if (fl && !fl.hatch && fl.color === canvasHex && !st) continue;
          const bb = el.getBBox();
          const p = panelOf(bb.x + bb.width / 2, bb.y + bb.height / 2);
          const sxn = Math.abs(p.xd[1] - p.xd[0]) || 1, syn = Math.abs(p.yd[1] - p.yd[0]) || 1;
          const win = { x: [Math.min(p.xd[0], p.xd[1]), Math.max(p.xd[0], p.xd[1])], y: [Math.min(p.yd[0], p.yd[1]), Math.max(p.yd[0], p.yd[1])] };
          // расширенное окно: дальше него координаты в файл не идут
          const bx0 = win.x[0] - EXT * sxn, bx1 = win.x[1] + EXT * sxn, by0 = win.y[0] - EXT * syn, by1 = win.y[1] + EXT * syn;
          const decl = readRecord(el);
          /* Кривая без формулы уходит узлами, которые посчитала САМА МОДЕЛЬ: D3
             хранит привязанные данные на узле (__data__), у линий это массив
             пар в единицах модели. Берём их, если они совпали с нарисованным
             путём узел в узел; иначе — узлы пути (те же, но округлены до
             0,001 px). Разрывы линии делят данные на куски так же, как путь. */
          let exact = null;
          if (decl && decl.kind === 'numeric' && Array.isArray(el.__data__)) {
            const runs = []; let cur = null;
            el.__data__.forEach(q => {
              const ok = Array.isArray(q) && q.length >= 2 && isFinite(q[0]) && isFinite(q[1]);
              if (!ok) { cur = null; return; }
              if (!cur) { cur = []; runs.push(cur); }
              cur.push([+q[0], +q[1]]);
            });
            const subs = parsed.subs.filter(sp => sp.pts.length >= 1);
            const same = runs.length === subs.length && runs.every((r, i) => r.length === subs[i].pts.length &&
              r.every((q, k) => Math.abs(p.mx(q[0]) - subs[i].pts[k][0]) < 0.01 && Math.abs(p.my(q[1]) - subs[i].pts[k][1]) < 0.01));
            if (same) exact = new Map(subs.map((sp, i) => [sp, runs[i]]));
          }
          parsed.subs.forEach((sp, si) => {
            if (sp.pts.length < 2) return;
            const data = (exact && exact.get(sp)) || sp.pts.map(q => D(p, q[0], q[1]));
            const closed = sp.closed || (!!fl && !st);
            const far = data.some(q => q[0] < bx0 || q[0] > bx1 || q[1] < by0 || q[1] > by1);
            const outside = sp.pts.some(q => q[0] < -0.5 || q[0] > W + 0.5 || q[1] < -0.5 || q[1] > H + 0.5);
            const clipId = base.clip || (outside ? '@canvas' : null);
            const mk = (pts, extra) => {
              const simp = simplify(pts, sxn, syn, closed);
              const it = Object.assign({}, base, { clip: clipId, kind: 'path', sub: si, n: data.length, pts: simp, closed, fl, st, legend: el.getAttribute('data-legend') || '', cls, pcls: String((el.parentNode.getAttribute && el.parentNode.getAttribute('class')) || '') }, extra || {});
              it.shape = simp.length <= POLY_MAX ? 'poly' : 'sampled';
              return it;
            };
            let extra = {};
            // 1) кривая с записью формулы: сверяем с нарисованным и пишем формулой
            if (decl && decl.kind === 'expr' && st && !fl) {
              const v = verifyCurve(data, decl, win, sxn, syn);
              if (v.ok) {
                const A = v.A, spanA = A ? syn : sxn, spanB = A ? sxn : syn, wA = A ? win.y : win.x, wB = A ? win.x : win.y;
                const eB0 = A ? bx0 : by0, eB1 = A ? bx1 : by1;
                const args = data.map(q => q[A]);
                let a0 = Math.min.apply(null, args), a1 = Math.max.apply(null, args);
                /* Отрезок записи вправе выйти за крайние узлы не дальше полутора
                   шагов сетки пути: у корня предельной кривой основная часть и
                   хвост рисуются разными путями, и между их крайними узлами на
                   экране щель в шаг сетки (49,8 и 50,1 при корне 50). */
                const h = (a1 - a0) / Math.max(1, data.length - 1);
                if (isFinite(decl.from) && isFinite(decl.to)) {
                  const f0 = Math.min(decl.from, decl.to), f1 = Math.max(decl.from, decl.to);
                  a0 = (f0 < a0 && a0 - f0 <= h * 1.5) ? f0 : Math.max(a0, f0);
                  a1 = (f1 > a1 && f1 - a1 <= h * 1.5) ? f1 : Math.min(a1, f1);
                }
                // и не дальше окна плюс 30 % по оси аргумента (у записи «по вертикали» это вертикальная ось)
                a0 = Math.max(a0, wA[0] - EXT * spanA); a1 = Math.min(a1, wA[1] + EXT * spanA);
                /* Кусочная запись уходит по куску на участок: у каждого куска
                   своя формула и точные границы из условия. Запись сверена
                   целиком выше; не разобралась на куски или куски не сошлись с
                   целой записью — одной формулой с условиями. */
                let pieces = [{ expr: decl.expr, f: v.f, pgf: v.pgf, a: a0, b: a1, tag: '' }];
                const cp = /\?/.test(decl.expr) ? condPieces(decl.expr, decl.v) : null;
                if (cp) {
                  const cut = cp.map((c, k) => ({ expr: c.expr, f: exprFn(c.expr, decl.v), pgf: exprToPgf(c.expr, decl.v, A ? 't' : 'x'), a: Math.max(a0, c.lo), b: Math.min(a1, c.hi), tag: 'кусок ' + (k + 1) })).filter(c => c.b > c.a);
                  // каждый кусок на своём участке равен целой записи, и куски покрывают всё, где запись определена
                  const same = cut.length > 0 && cut.every(c => c.f && c.pgf && [0.05, 0.3, 0.5, 0.7, 0.95].every(t => { const x = c.a + (c.b - c.a) * t, w = v.f(x), q = c.f(x); return (!isFinite(w) && !isFinite(q)) || Math.abs(w - q) <= spanB * 1e-9; }));
                  let covered = same;
                  for (let k = 0; covered && k <= 200; k++) { const x = a0 + (a1 - a0) * k / 200; if (isFinite(v.f(x)) && !cut.some(c => x >= c.a - spanA * 1e-9 && x <= c.b + spanA * 1e-9)) covered = false; }
                  if (same && covered) pieces = cut;
                }
                let zi = 0, any = false;
                pieces.filter(pc => pc.b > pc.a).forEach(pc => {
                  visibleRuns(pc.a, pc.b, pc.f, eB0, eB1, decOf(spanA) + 3).forEach(r => {
                    const it = mk(data, { rec: { ok: true, src: decl.src, expr: pc.expr, v: decl.v, axis: A ? 'y' : 'x', pgf: pc.pgf, maxErr: v.maxErr, lo: r[0], hi: r[1], samples: pickSamples(pc.f, r[0], r[1], wB[0], wB[1], spanB), name: [decl.name || '', pc.tag].filter(Boolean).join(', '), bLo: eB0, bHi: eB1, far, probe: probeOf(pc.f, r[0], r[1]), span: spanB } });
                    it.z = base.z + (zi++) * 1e-3;
                    p.items.push(it); any = true;
                  });
                });
                if (any) return;
                // запись верна, но видимой части в расширенном окне нет: на экране кривая за краем
                return;
              }
              extra = { rec: { ok: false, src: decl.src, expr: decl.expr, v: decl.v, maxErr: v.maxErr, between: v.between, why: v.why, name: decl.name || '' } };
            }
            // 2) область с записью границ: сверяем и пишем границами
            else if (decl && decl.kind === 'area' && fl) {
              const v = verifyArea(data, decl, win, sxn, syn);
              if (v.ok) { if (!v.hidden) p.items.push(mk(data, { area: v })); return; }
              extra = { area: { ok: false, why: v.why, maxErr: v.maxErr, areaErr: v.areaErr } };
            }
            // 3) узлы расчёта или ломаная с названной причиной
            else if (decl && (decl.kind === 'numeric' || decl.kind === 'poly')) extra = { nodes: { kind: decl.kind, why: decl.why, name: decl.name || '', exact: !!(exact && exact.get(sp)) } };
            // запасной путь: узлы самого нарисованного пути
            if (far && closed) { p.items.push(mk(clipPoly(data, bx0, bx1, by0, by1), extra)); return; }
            if (far) { clipLine(data, bx0, bx1, by0, by1).forEach((piece, k) => { const it = mk(piece, extra); it.z = base.z + k * 1e-3; p.items.push(it); }); return; }
            p.items.push(mk(data, extra));
          });
        }
      }
    };
    walk(chart, {});

    // Оси: деления, ноль, названия.
    panels.forEach(p => {
      const ax = p.ax;
      const oxPx = ax.yLine ? ax.yLine.px[0] : null, oyPx = ax.xLine ? ax.xLine.px[1] : null;
      ax.extra.forEach(t => {
        // подпись деления: под горизонтальной осью или слева от вертикальной
        const cx = t.bb[0] + t.bb[2] / 2, cy = t.bb[1] + t.bb[3] / 2;
        const isZero = (t.h === 'end' && t.v === 'top') || (oxPx != null && oyPx != null && t.raw.trim() === '0' && cx < oxPx && cy > oyPx);
        if (isZero) { ax.zero = t; return; }
        const underX = oyPx != null && t.h === 'middle' && cy > oyPx && cy - oyPx < 30;
        const leftY = oxPx != null && t.h === 'end' && cx < oxPx && oxPx - t.bb[0] - t.bb[2] < 16;
        if (underX) ax.xt.push({ v: p.mx.invert(t.px[0]), tex: t.tex, raw: t.raw, color: t.color, bold: t.bold });
        else if (leftY) ax.yt.push({ v: p.my.invert(t.px[1]), tex: t.tex, raw: t.raw, color: t.color, bold: t.bold });
        else p.items.push(t);                              // не опознали — уйдёт обычной подписью
      });
      delete ax.extra;
      /* Засечки у делений рисует pgfplots сам. Засечка без числа — деление,
         уступившее место числу точки (dropTickAt): в файле это деление с
         подписью-числом точки её цветом. */
      const coordAt = (horizontal, pos) => {
        const i = p.items.findIndex(it => it.kind === 'text' && /\bcoord-num\b/.test(it.cls) &&
          (horizontal ? (it.h === 'middle' && Math.abs(it.px[0] - pos) < 1.5 && oyPx != null && it.px[1] > oyPx && it.px[1] - oyPx < 14)
                      : (it.h === 'end' && Math.abs(it.px[1] - pos) < 1.5 && oxPx != null && it.px[0] < oxPx && oxPx - it.px[0] < 14)));
        if (i < 0) return null;
        const it = p.items[i]; p.items.splice(i, 1); return it;
      };
      p.items = p.items.filter(it => {
        if (it.kind !== 'seg' || it.arrow) return true;
        const [x1, y1, x2, y2] = it.px;
        const len = Math.hypot(x2 - x1, y2 - y1);
        if (len > 10) return true;
        const inAxes = it.role === 'axes';
        // засечка деления: её рисует pgfplots сам (счёт засечек — для сверки «предметов столько же»)
        if (oyPx != null && Math.abs(x1 - x2) < 0.5 && Math.min(Math.abs(y1 - oyPx), Math.abs(y2 - oyPx)) < 1.5) {
          if (ax.xt.some(t => Math.abs(p.mx(t.v) - x1) < 1.5)) { ax.marks++; return false; }
          if (inAxes) { ax.xt.push({ v: p.mx.invert(x1), tex: '', raw: '', color: '', pending: x1 }); ax.marks++; return false; }
        }
        if (oxPx != null && Math.abs(y1 - y2) < 0.5 && Math.min(Math.abs(x1 - oxPx), Math.abs(x2 - oxPx)) < 1.5) {
          if (ax.yt.some(t => Math.abs(p.my(t.v) - y1) < 1.5)) { ax.marks++; return false; }
          if (inAxes) { ax.yt.push({ v: p.my.invert(y1), tex: '', raw: '', color: '', pending: y1 }); ax.marks++; return false; }
        }
        return true;
      });
      ax.xt.forEach(t => { if (t.pending == null) return; const c = coordAt(true, t.pending); if (c) { t.tex = c.tex; t.raw = c.raw; t.color = c.color; t.accent = true; t.bold = c.bold; } delete t.pending; });
      ax.yt.forEach(t => { if (t.pending == null) return; const c = coordAt(false, t.pending); if (c) { t.tex = c.tex; t.raw = c.raw; t.color = c.color; t.accent = true; t.bold = c.bold; } delete t.pending; });
      // названия осей
      p.items = p.items.filter(it => {
        if (it.kind !== 'text' || !it.axisName) return true;
        if (ax.xLine && !ax.xName && it.h === 'start' && it.px[0] >= Math.max(ax.xLine.px[0], ax.xLine.px[2]) - 1 && Math.abs(it.px[1] - oyPx) < 12) { ax.xName = it; return false; }
        if (ax.yLine && !ax.yName && it.h === 'middle' && it.px[1] <= Math.min(ax.yLine.px[1], ax.yLine.px[3]) + 1 && Math.abs(it.px[0] - oxPx) < 30) { ax.yName = it; return false; }
        return true;
      });
    });

    // Легенда закрашенных областей: строки берутся у нарисованной легенды.
    if (legendRoot && shown(legendRoot)) {
      const rows = []; let box = null; const texts = [], sw = [];
      legendRoot.querySelectorAll('rect').forEach(r => {
        const w = +r.getAttribute('width'), h = +r.getAttribute('height');
        const cs = getComputedStyle(r);
        if (w > 40 && h > 16 && !box) { box = { x: +r.getAttribute('x'), y: +r.getAttribute('y'), w, h, stroke: hex(cs.stroke), fill: hex(cs.fill) }; return; }
        const fl = fillOf(r, cs, chainOpacity(r, chart)); if (fl) sw.push({ y: +r.getAttribute('y') + h / 2, fl });
      });
      legendRoot.querySelectorAll('text').forEach(t => {
        // у строки внутри text лежит <title> с полным названием: в текст он не входит
        const k2 = t.cloneNode(true); k2.querySelectorAll('title,desc').forEach(n => n.remove());
        const raw = t.getAttribute('data-raw') || k2.textContent; if (!raw.trim()) return;
        const bb = t.getBBox(); texts.push({ y: bb.y + bb.height / 2, raw, tex: labelTex(raw) });
      });
      texts.forEach(t => { let b = null, bd = 9; sw.forEach(s => { const d = Math.abs(s.y - t.y); if (d < bd) { bd = d; b = s; } }); rows.push({ tex: t.tex, raw: t.raw, fl: b ? b.fl : null }); });
      if (rows.length) {
        const bx = box || (function () { const b = legendRoot.getBBox(); return { x: b.x, y: b.y, w: b.width, h: b.height }; })();
        const p = nearest(bx.x + bx.w / 2, bx.y + bx.h / 2);
        p.legend = { rows, rx: (bx.x - p.x0) / (p.x1 - p.x0), ry: 1 - (bx.y - p.y0) / (p.y1 - p.y0), boxed: !!box };
      }
    }
    return { W, H, plot, panels: panels.map(p => { const q = Object.assign({}, p); delete q.mx; delete q.my; return q; }), warn,
      scene: STATE.sceneKey || '', name: (typeof SCENE_NAMES === 'object' && SCENE_NAMES[STATE.sceneKey]) || '', mode: STATE.mode };
  }

  /* ───────────────────────────── сборка ───────────────────────────── */
  /* Чистая функция: опись и параметры окна «Скачать» (заголовок, метка) →
     текст файла. Порядок строк — порядок слоёв на холсте; соседние предметы
     под одним окном обрезки — в одном scope с \clip. Возвращает и счётчики
     (stats — для приборов, SPEC, раздел 12; tally — опись окна «Скачать»:
     что человек видит на графике, его словами). */
  function emit(list, opts) {
    const o = opts || {};
    const defs = [];
    const col = (h) => { const key = 'c' + h; const line = '\\definecolor{' + key + '}{HTML}{' + h + '}'; if (defs.indexOf(line) < 0) defs.push(line); return key; };
    /* Дефекты: curvesNoRecPoly, curvesNoRecSampled, curvesMismatch,
       areasNoRecSampled, areasMismatch. Многоугольник без записи у области
       (areasPoly) дефектом не считается: три точные вершины треугольника и
       есть его полное описание. */
    const stats = { panels: list.panels.length, axisLines: 0, gridLines: 0, ticks: 0,
      curvesFormula: 0, curvesNumeric: 0, numericExact: 0, curvesPolyRec: 0, curvesNoRecPoly: 0, curvesNoRecSampled: 0, curvesMismatch: 0,
      areasBounds: 0, areasPoly: 0, areasNumeric: 0, areasNoRecSampled: 0, areasMismatch: 0, outlines: 0,
      rects: 0, segs: 0, dots: 0, texts: 0, legendRows: 0, pairs: 0,
      // что видно на листе, но в файле стоит настройкой оси, а не своей строкой
      tickLabels: 0, tickMarks: 0, zeroLabels: 0, axisNames: 0 };
    // опись окна «Скачать»: по одному на нарисованный предмет (у кривой с разрывом или кусками строк несколько)
    const seenCurves = new Set(), seenAreas = new Set();
    let needFillBetween = false, needPatterns = false, areaSeq = 0;
    const font = (step) => { const s = FS_PT[step] || 9; return '\\fontsize{' + s + '}{' + (s * 1.15).toFixed(1) + '}\\selectfont'; };
    const note = (t) => (t ? '   % ' + commentText(t) : '');
    const out = [];

    list.panels.forEach((p, pi) => {
      const sx = Math.abs(p.xd[1] - p.xd[0]) || 1, sy = Math.abs(p.yd[1] - p.yd[0]) || 1;
      const dx = decOf(sx), dy = decOf(sy);
      const nn = (v, d) => { const r = +v.toFixed(d); return String(Object.is(r, -0) ? 0 : r); };
      const X = (v) => nn(v, dx), Y = (v) => nn(v, dy);
      const P = (q) => { stats.pairs++; return '(axis cs:' + X(q[0]) + ',' + Y(q[1]) + ')'; };
      const strokeOpts = (st, extra) => {
        const a = [col(st.color), 'line width=' + (st.w * K_LINE).toFixed(2) + 'pt'];
        if (st.dash && st.dash.length) a.push('dash pattern=' + st.dash.map((v, i) => (i % 2 ? 'off ' : 'on ') + (v * K_DASH).toFixed(1) + 'pt').join(' '));
        if (st.op < 0.985) a.push('opacity=' + st.op.toFixed(2));
        return a.concat(extra || []);
      };
      const fillOpts = (fl) => {
        if (fl.hatch) { needPatterns = true; return ['pattern=north east lines', 'pattern color=' + col(fl.color)]; }
        return [col(fl.color), 'opacity=' + Math.max(0.03, fl.op).toFixed(2)];
      };

      // ── настройки осей: одной строкой (пустая строка внутри роняет pgfplots, а браузер шлёт CRLF)
      const ax = p.ax, a = [];
      const wpt = ((p.x1 - p.x0) * PX2PT).toFixed(1), hpt = ((p.y1 - p.y0) * PX2PT).toFixed(1);
      a.push('name=' + ('panel' + String.fromCharCode(65 + pi)), 'at={(' + (p.x0 * PX2PT).toFixed(1) + 'pt,' + ((list.H - p.y1) * PX2PT).toFixed(1) + 'pt)}', 'anchor=south west');
      a.push('width=' + wpt + 'pt', 'height=' + hpt + 'pt', 'scale only axis', 'clip=false');
      a.push('xmin=' + X(p.xd[0]) + ', xmax=' + X(p.xd[1]) + ', ymin=' + Y(p.yd[0]) + ', ymax=' + Y(p.yd[1]));
      const snap = (v, span) => { const r = Math.round(v / (span * 1e-6)) * (span * 1e-6); return Math.abs(r) < span * 1e-9 ? 0 : r; };
      /* Оси панели всегда задаются средствами pgfplots (проверено сборкой):
           • линия оси на холсте есть — axis x line=middle (ось в нуле); линии
             нет (ноль уехал за кадр) — линия невидима, сетка остаётся
             (axis lines=none убрал бы вместе с осью и её сетку);
           • деление с числом — xtick; линия сетки без числа и засечки (край
             окна) — extra x ticks с пустой подписью и нулевой засечкой;
           • мелкая сетка — явный список minor xtick. */
      const hasGrid = ax.gx.length + ax.gy.length > 0, hasMinor = ax.gxm.length + ax.gym.length > 0;
      const lineSt = (ax.xLine || ax.yLine || {}).st || null;
      stats.axisLines += (ax.xLine ? 1 : 0) + (ax.yLine ? 1 : 0);
      stats.gridLines += ax.gx.length + ax.gy.length + ax.gxm.length + ax.gym.length;
      a.push('axis x line=' + (ax.xLine ? 'middle' : 'bottom'), 'axis y line=' + (ax.yLine ? 'middle' : 'left'));
      if (lineSt) a.push('axis line style={' + col(lineSt.color) + ', line width=' + (lineSt.w * K_LINE).toFixed(2) + 'pt, -{Stealth[length=5pt]}}');
      else a.push('axis line style={draw=none}');
      if (lineSt && !ax.xLine) a.push('x axis line style={draw=none}');
      if (lineSt && !ax.yLine) a.push('y axis line style={draw=none}');
      a.push('tick align=outside', 'major tick length=3pt', 'scaled ticks=false');
      if (lineSt) a.push('tick style={' + col(lineSt.color) + ', line width=0.4pt}');
      const ticks = (arr, d, span) => {
        const t = arr.slice().sort((u, w) => u.v - w.v);
        const vals = t.map(k => nn(snap(k.v, span), d));
        // подписи пишутся, только если это не простые целые до тысячи
        const plain = t.every((k, i) => k.raw.replace(/\s/g, '') === vals[i] && Math.abs(+vals[i]) < 1000 && !k.accent);
        return { vals, labels: plain ? null : t.map(k => (k.tex ? (k.accent ? '\\textcolor{' + col(k.color) + '}{' + k.tex + '}' : k.tex) : '')) };
      };
      const tx = ticks(ax.xt, dx, sx), ty = ticks(ax.yt, dy, sy);
      stats.ticks += tx.vals.length + ty.vals.length;
      [tx, ty].forEach(t => { stats.tickLabels += t.labels ? t.labels.filter(Boolean).length : t.vals.length; });
      stats.tickMarks += ax.marks || 0;
      stats.axisNames += (ax.xName ? 1 : 0) + (ax.yName ? 1 : 0);
      a.push(tx.vals.length ? 'xtick={' + tx.vals.join(',') + '}' : 'xtick=\\empty'); if (tx.labels) a.push('xticklabels={' + tx.labels.map(s => '{' + s + '}').join(',') + '}');
      a.push(ty.vals.length ? 'ytick={' + ty.vals.join(',') + '}' : 'ytick=\\empty'); if (ty.labels) a.push('yticklabels={' + ty.labels.map(s => '{' + s + '}').join(',') + '}');
      if (tx.vals.length + ty.vals.length) {
        const tc = (ax.xt.concat(ax.yt).find(t => t.color && !t.accent) || {}).color || '6B6457';
        a.push('tick label style={font=' + font('small') + ', text=' + col(tc) + '}');
      }
      if (hasGrid) {
        // линии сетки, на которых нет деления с числом
        const only = (g, vals, d, span) => { const u = []; g.map(v => nn(snap(v, span), d)).forEach(v => { if (vals.indexOf(v) < 0 && u.indexOf(v) < 0) u.push(v); }); return u.sort((p1, p2) => p1 - p2); };
        const ex = only(ax.gx, tx.vals, dx, sx), ey = only(ax.gy, ty.vals, dy, sy);
        if (ex.length) a.push('extra x ticks={' + ex.join(',') + '}', 'extra x tick labels={}');
        if (ey.length) a.push('extra y ticks={' + ey.join(',') + '}', 'extra y tick labels={}');
        if (ex.length + ey.length) a.push('extra tick style={grid=major, major tick length=0pt}');
        if (hasMinor) {
          const mxs = only(ax.gxm, [], dx + 1, sx), mys = only(ax.gym, [], dy + 1, sy);
          if (mxs.length) a.push('minor xtick={' + mxs.join(',') + '}');
          if (mys.length) a.push('minor ytick={' + mys.join(',') + '}');
          a.push('minor tick length=0pt');
        }
        const gs = 'line width=' + ((ax.gridW || 1) * 0.4).toFixed(2) + 'pt, ' + col(ax.gridColor || 'D9D4C7');
        a.push('grid=' + (hasMinor ? 'both' : 'major'), 'grid style={' + gs + (ax.gridOp < 0.985 ? ', opacity=' + ax.gridOp.toFixed(2) : '') + '}');
        if (hasMinor) a.push('minor grid style={' + gs + ', opacity=' + (ax.gridMinorOp != null ? ax.gridMinorOp : (ax.gridOp || 1) * 0.45).toFixed(2) + '}');
      }
      // имена осей: у конца стрелки, буква стоит прямо (rotate у ylabel положил бы её набок)
      if (ax.xName) a.push('xlabel={' + ax.xName.tex + '}', 'xlabel style={at={(current axis.right of origin)}, anchor=west, font=' + font(ax.xName.step) + ', text=' + col(ax.xName.color) + '}');
      if (ax.yName) a.push('ylabel={' + ax.yName.tex + '}', 'ylabel style={at={(current axis.above origin)}, anchor=south, font=' + font(ax.yName.step) + ', text=' + col(ax.yName.color) + '}');
      if (p.legend) {
        const L = p.legend;
        a.push('legend style={at={(' + L.rx.toFixed(3) + ',' + L.ry.toFixed(3) + ')}, anchor=north west, draw=' + (L.boxed ? col('C9C3B5') : 'none') + ', fill=white, fill opacity=0.9, text opacity=1, font=' + font('base') + ', cells={anchor=west}, row sep=0.5pt, inner sep=3pt}');
      }
      out.push('% -- Панель ' + commentText(p.id) + ': x от ' + X(p.xd[0]) + ' до ' + X(p.xd[1]) + ', y от ' + Y(p.yd[0]) + ' до ' + Y(p.yd[1]));
      out.push('\\begin{axis}[' + a.join(', ') + ']');

      // ── содержимое в порядке отрисовки; соседние под одной обрезкой — в одном scope
      let openClip = null;
      const closeScope = () => { if (openClip) { out.push('\\end{scope}'); openClip = null; } };
      const clipBox = (id) => (p.clips && p.clips[id]) || null;
      const body0 = p.items.slice().sort((u, w) => u.z - w.z);
      const body = [];
      // соседние одинаковые прямоугольники сливаются (у «Максимумов и минимумов» 240 полос знака — в две)
      body0.forEach(it => {
        const last = body[body.length - 1];
        if (it.kind === 'rect' && last && last.kind === 'rect' && it.fl && last.fl && !it.st && !last.st && !it.fl.hatch && !last.fl.hatch
            && it.fl.color === last.fl.color && Math.abs(it.fl.op - last.fl.op) < 1e-6 && it.clip === last.clip
            && Math.abs(it.a[1] - last.a[1]) < sy * 1e-6 && Math.abs(it.b[1] - last.b[1]) < sy * 1e-6
            && Math.abs(it.a[0] - last.b[0]) < sx * 2e-3) {
          last.b = [it.b[0], last.b[1]]; last.merged = (last.merged || 1) + 1; return;
        }
        body.push(it.kind === 'rect' ? Object.assign({}, it) : it);
      });
      body.forEach(it => {
        const cb = it.clip ? clipBox(it.clip) : null;
        const key = cb ? it.clip : null;
        if (key !== openClip) {
          closeScope();
          if (key) { out.push('\\begin{scope}'); out.push('\\clip (axis cs:' + X(cb[0]) + ',' + Y(cb[1]) + ') rectangle (axis cs:' + X(cb[2]) + ',' + Y(cb[3]) + ');'); openClip = key; }
        }
        /* Конец отрезка или угол прямоугольника далеко за окном обрезки в файл
           не идёт: pgfplots падает с «Dimension too large» (замер: «IS–LM» с
           окном до 5 и равновесием при 166,67; «Кривая Лаффера» с осью до 5 и
           вершиной 1 250). Видимая часть та же: её и так режет \clip. «Далеко»
           — дальше размера окна обрезки за его краем. */
        let segA = it.a, segB = it.b, segArrow = it.arrow;
        if (cb && (it.kind === 'seg' || it.kind === 'rect')) {
          const bx0 = Math.min(cb[0], cb[2]), bx1 = Math.max(cb[0], cb[2]), by0 = Math.min(cb[1], cb[3]), by1 = Math.max(cb[1], cb[3]);
          const wx = bx1 - bx0, wy = by1 - by0;
          const far = (q) => q[0] < bx0 - wx || q[0] > bx1 + wx || q[1] < by0 - wy || q[1] > by1 + wy;
          if (far(it.a) || far(it.b)) {
            if (it.kind === 'seg') {
              const pieces = clipLine([it.a, it.b], bx0, bx1, by0, by1);
              if (!pieces.length) return;                    // за окном обрезки целиком: на экране его нет
              if (far(it.b)) segArrow = false;               // конец со стрелкой за окном: стрелки не видно
              segA = pieces[0][0]; segB = pieces[0][pieces[0].length - 1];
            } else {
              const cl = (q) => [Math.max(bx0 - wx, Math.min(bx1 + wx, q[0])), Math.max(by0 - wy, Math.min(by1 + wy, q[1]))];
              segA = cl(it.a); segB = cl(it.b);
            }
          }
        }
        if (it.kind === 'seg') {
          stats.segs++;
          out.push('\\draw[' + strokeOpts(it.st).join(', ') + (segArrow ? ', -{Stealth[length=5pt]}' : '') + '] ' + P(segA) + ' -- ' + P(segB) + ';');
        } else if (it.kind === 'rect') {
          stats.rects++;
          if (it.fl) { seenAreas.add('r' + it.z); out.push('\\fill[' + fillOpts(it.fl).join(', ') + '] ' + P(segA) + ' rectangle ' + P(segB) + ';' + note(it.legend)); }
          if (it.st) out.push('\\draw[' + strokeOpts(it.st).join(', ') + '] ' + P(segA) + ' rectangle ' + P(segB) + ';');
        } else if (it.kind === 'dot') {
          stats.dots++;
          const r = Math.min(3, Math.max(1, it.r * K_DOT)).toFixed(1);
          if (it.hollow) out.push('\\draw[' + col(it.color) + ', line width=' + ((it.st ? it.st.w : 1.5) * K_LINE).toFixed(2) + 'pt, fill=white] ' + P(it.c) + ' circle[radius=' + r + 'pt];');
          else out.push('\\fill[' + col(it.color) + (it.op < 0.985 ? ', opacity=' + it.op.toFixed(2) : '') + '] ' + P(it.c) + ' circle[radius=' + r + 'pt];');
        } else if (it.kind === 'text') {
          stats.texts++;
          const dxp = it.shift[0], dyp = it.shift[1], at = it.at;
          const anch = ({ top: 'north', mid: '', base: 'base' }[it.v] + ' ' + ({ start: 'west', middle: '', end: 'east' }[it.h] || '')).trim() || 'center';
          // жирное в математике — через font=…\boldmath: {\boldmath $…$} внутри axis роняет сборку
          const opt = ['anchor=' + anch, 'inner sep=' + (it.halo && !dxp && !dyp ? '1pt' : '0pt'), 'font=' + font(it.step) + (it.bold ? '\\boldmath' : ''), 'text=' + col(it.color)];
          if (Math.abs(dxp) > 0.05) opt.push('xshift=' + dxp.toFixed(1) + 'pt');
          if (Math.abs(dyp) > 0.05) opt.push('yshift=' + dyp.toFixed(1) + 'pt');
          out.push('\\node[' + opt.join(', ') + '] at ' + P(at) + ' {' + it.tex + '};');
        } else if (it.kind === 'path') {
          const el = Math.floor(it.z);
          if (it.fl) {                                        // ── закрашенная область
            seenAreas.add('p' + el);
            const A = it.area, name = it.legend || 'область';
            if (A && A.ok) {
              const DX = (v) => nn(v, dx + 3);
              if (+DX(A.da) >= +DX(A.db)) return;              // отрезок нулевой длины: не виден, а pgfplots на нём падает
              stats.areasBounds++;
              // углы — с той же точностью, что и отрезок построения: общий край соседних областей сходится знак в знак
              const corner = (x, y) => { stats.pairs++; return '(axis cs:' + DX(x) + ',' + nn(y, dy + 3) + ')'; };
              const po = it.fl.hatch ? ['draw=none', 'pattern=north east lines', 'pattern color=' + col(it.fl.color)] : ['draw=none', 'fill=' + col(it.fl.color), 'fill opacity=' + Math.max(0.03, it.fl.op).toFixed(2)];
              if (it.fl.hatch) needPatterns = true;
              const dom = ['domain=' + DX(A.da) + ':' + DX(A.db), 'samples=' + A.samples].concat(A.far ? ['restrict y to domain*=' + Y(A.bLo) + ':' + Y(A.bHi)] : []);
              const what = (s) => s.num != null ? Y(s.num) : s.expr;
              const about = name + ': от ' + X(A.a) + ' до ' + X(A.b) + ', между ' + what(A.lo) + ' и ' + what(A.hi);
              // дальше расширенного окна всё срезает \clip: число-граница прижимается к нему без изменения картинки
              const yIn = (v) => Math.max(A.bLo, Math.min(A.bHi, v));
              if (A.lo.num != null && A.hi.num != null) {
                out.push('\\fill[' + fillOpts(it.fl).join(', ') + '] ' + corner(A.ca, yIn(A.lo.num)) + ' rectangle ' + corner(A.cb, yIn(A.hi.num)) + ';' + note(about));
              } else if (A.lo.lin && A.hi.lin) {              // обе границы прямые: углы по записи, многоугольник обрезан расширенным окном
                const cs4 = clipPoly([[A.ca, A.lo.at[0]], [A.cb, A.lo.at[1]], [A.cb, A.hi.at[1]], [A.ca, A.hi.at[0]]], A.bx0, A.bx1, A.bLo, A.bHi);
                const uniq = cs4.filter((c, i) => { const q = cs4[(i + cs4.length - 1) % cs4.length]; return Math.abs(c[0] - q[0]) > sx * 1e-9 || Math.abs(c[1] - q[1]) > sy * 1e-9; });
                if (uniq.length >= 3) out.push('\\fill[' + fillOpts(it.fl).join(', ') + '] ' + uniq.map(c => corner(c[0], c[1])).join(' -- ') + ' -- cycle;' + note(about));
              } else if (A.lo.lin || A.hi.lin) {              // одна граница кривая: формула и два угла по прямой границе
                const cur = A.lo.lin ? A.hi : A.lo, flat = A.lo.lin ? A.lo : A.hi;
                // горизонтальную прямую прижать к окну можно без изменения картинки, наклонную — нельзя
                const fy = (v) => (flat.num != null ? yIn(v) : v);
                out.push('\\addplot[' + po.concat(dom, ['forget plot']).join(', ') + '] {' + cur.pgf + '} -- ' + corner(A.cb, fy(flat.at[1])) + ' -- ' + corner(A.ca, fy(flat.at[0])) + ' -- cycle;' + note(about));
              } else {                                        // обе границы кривые
                const id = 'area' + String.fromCharCode(65 + pi) + (++areaSeq);
                needFillBetween = true;
                out.push('\\addplot[' + ['draw=none', 'name path=' + id + 'hi'].concat(dom, ['forget plot']).join(', ') + '] {' + A.hi.pgf + '};');
                out.push('\\addplot[' + ['draw=none', 'name path=' + id + 'lo'].concat(dom, ['forget plot']).join(', ') + '] {' + A.lo.pgf + '};');
                out.push('\\addplot[' + fillOpts(it.fl).concat(['forget plot']).join(', ') + '] fill between[of=' + id + 'hi and ' + id + 'lo];' + note(about));
              }
            } else {
              let why;
              if (A) { stats.areasMismatch++; why = 'ЗАПИСЬ НЕ СОШЛАСЬ (' + A.why + '): узлы пути'; }
              else if (it.nodes && it.nodes.kind === 'numeric') { stats.areasNumeric++; why = 'узлы расчёта модели: ' + it.nodes.why; }
              else if (it.shape === 'poly') { stats.areasPoly++; why = 'многоугольник, вершины точные'; }
              else { stats.areasNoRecSampled++; why = 'БЕЗ ЗАПИСИ: по отсчётам (' + it.pts.length + ' узлов)'; }
              out.push('\\fill[' + fillOpts(it.fl).join(', ') + '] ' + it.pts.map(P).join(' -- ') + ' -- cycle;' + note(name + ': ' + why));
            }
          }
          if (it.st) {                                        // ── кривая или контур области
            if (!it.fl) seenCurves.add(el);
            const r = it.rec, so = strokeOpts(it.st);
            if (r && r.ok) {
              const vert = r.axis === 'y';
              const DA = (v) => nn(v, (vert ? dy : dx) + 3);
              /* Кусок нулевой длины после округления («domain=50:50» у хвоста MR
                 при кусочном спросе) не виден, а pgfplots на нём исчерпывает
                 память TeX: в файл не идёт. */
              if (+DA(r.lo) >= +DA(r.hi)) return;
              stats.curvesFormula++;
              const opts2 = ['domain=' + DA(r.lo) + ':' + DA(r.hi), 'samples=' + r.samples];
              if (vert) {
                opts2.push('variable=\\t');
                if (r.far) opts2.push('restrict x to domain*=' + X(r.bLo) + ':' + X(r.bHi));
                out.push('\\addplot[' + so.concat(opts2, ['forget plot']).join(', ') + '] ({' + r.pgf + '}, {t});' + note(r.name));
              } else {
                if (r.far) opts2.push('restrict y to domain*=' + Y(r.bLo) + ':' + Y(r.bHi));
                out.push('\\addplot[' + so.concat(opts2, ['forget plot']).join(', ') + '] {' + r.pgf + '};' + note(r.name));
              }
            } else {
              let why;
              if (r) { stats.curvesMismatch++; why = 'ЗАПИСЬ НЕ СОШЛАСЬ (' + r.why + '): узлы пути'; }
              else if (it.nodes && it.nodes.kind === 'numeric') { stats.curvesNumeric++; if (it.nodes.exact) stats.numericExact++; why = 'узлы расчёта модели: ' + it.nodes.why; }
              else if (it.nodes) { stats.curvesPolyRec++; why = 'ломаная: ' + it.nodes.why; }
              else if (it.fl) { stats.outlines++; why = 'контур области'; }
              else if (it.shape === 'poly') { stats.curvesNoRecPoly++; why = 'БЕЗ ЗАПИСИ: ломаная, вершины точные'; }
              else { stats.curvesNoRecSampled++; why = 'БЕЗ ЗАПИСИ: по отсчётам (' + it.pts.length + ' узлов)'; }
              const nm = (it.nodes && it.nodes.name) || (r && r.name) || '';
              if (it.pts.length <= 4 && !it.closed) out.push('\\draw[' + so.join(', ') + '] ' + it.pts.map(P).join(' -- ') + ';' + note((nm ? nm + ': ' : '') + why));
              else out.push('\\addplot[' + so.concat(['forget plot']).join(', ') + '] coordinates {' + it.pts.map(q => { stats.pairs++; return '(' + X(q[0]) + ',' + Y(q[1]) + ')'; }).join(' ') + (it.closed ? ' (' + X(it.pts[0][0]) + ',' + Y(it.pts[0][1]) + ')' : '') + '};' + note((nm ? nm + ': ' : '') + why));
            }
          }
        }
      });
      closeScope();
      // единственный «0» в начале координат — отдельный узел, в списки делений ноль не входит
      if (ax.zero && (ax.xLine || ax.yLine)) stats.zeroLabels++;
      if (ax.zero && (ax.xLine || ax.yLine)) out.push('\\node[anchor=north east, inner sep=0pt, xshift=-4pt, yshift=-4pt, font=' + font('small') + ', text=' + col(ax.zero.color) + '] at (axis cs:0,0) {$0$};');
      // легенда собирается своими строками: у каждого \addplot стоит forget plot
      if (p.legend) p.legend.rows.forEach(r => {
        stats.legendRows++;
        const f = r.fl || { color: '888888', op: 0.3 };
        out.push('\\addlegendimage{legend image code/.code={\\fill[' + (f.hatch ? 'pattern=north east lines, pattern color=' + col(f.color) : col(f.color) + ', opacity=' + Math.min(1, Math.max(0.2, f.op)).toFixed(2)) + '] (0cm,-0.09cm) rectangle (0.42cm,0.11cm);}} \\addlegendentry{' + r.tex + '}');
        if (f.hatch) needPatterns = true;
      });
      out.push('\\end{axis}');
    });

    const cap = o.title ? proseTex(String(o.title).trim()) : '';
    const lab = String(o.label || '').trim().replace(/[^A-Za-z0-9:_-]/g, '');
    const head = [
      '% Собран калькулятором Weconomics. Компилируется обычным pdflatex.',
      list.name ? '% Модель: ' + commentText(list.name) + '.' : '',
      '\\documentclass[12pt,a4paper]{article}',
      '\\usepackage[T2A]{fontenc}', '\\usepackage[utf8]{inputenc}', '\\usepackage[english,russian]{babel}',
      '\\usepackage{amsmath}', '\\usepackage{pgfplots}', '\\pgfplotsset{compat=1.18}',
      '\\usetikzlibrary{arrows.meta}', needPatterns ? '\\usetikzlibrary{patterns}' : '', needFillBetween ? '\\usepgfplotslibrary{fillbetween}' : '',
      '\\usepackage{geometry}', '\\geometry{margin=2cm}',
    ];
    const text = head.concat(defs, ['\\begin{document}', '\\begin{figure}[h]', '\\centering', '\\begin{tikzpicture}'], out,
      ['\\end{tikzpicture}', cap ? '\\caption{' + cap + '}' : '', lab ? '\\label{' + lab + '}' : '', '\\end{figure}', '\\end{document}'])
      .filter(s => s !== '').join('\n');
    const tally = { curves: seenCurves.size, areas: seenAreas.size, dots: stats.dots, lines: stats.segs, labels: stats.texts,
      legend: stats.legendRows > 0, plotCm: plotCm(list.plot) };
    return { tex: text, stats, tally };
  }

  // Размер поля графика в сантиметрах для описи окна «Скачать» (12 на 8, 16 на 7,5…).
  function plotCm(plot) {
    if (!plot) return null;
    const cm = (px) => Math.round(px * PX2PT / 72.27 * 2.54 * 2) / 2;
    return [cm(plot[0]), cm(plot[1])];
  }

  // Бумажный прогон и опись — одной задачей браузера; холст возвращается при любом исходе.
  function inventory() {
    const leave = enterPaper();
    try { return capture(); } finally { leave(); }
  }

  return { enterPaper, capture, emit, inventory, labelTex, mathTex, exprToPgf, condPieces, parseD, simplify, texEsc, commentText };
})();

// Двери для 70-scenes-math.js (buildTex, окно «Скачать») и для приборов calc2/tests/tex/.
function texEnterPaper() { return TexExport.enterPaper(); }
function texCapture() { return TexExport.capture(); }
function texEmit(list, opts) { return TexExport.emit(list, opts); }
function texInventory() { return TexExport.inventory(); }
