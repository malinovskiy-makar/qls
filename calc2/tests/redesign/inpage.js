/* Внутристраничная часть прибора базового снимка (фаза 0 редизайна calc2).

   Вставляется в страницу /calc2/ через addScriptTag и заводит window.__RD.
   Здесь только ЧТЕНИЕ: слепок STATE, окна панелей, геометрия холста в
   координатах модели, перечень органов управления и видимый ответ. Как найти
   орган и как прочитать ответ, зависит от раскладки экрана, поэтому эти две
   части спрашивают «слой» (window.__RD_LAYER = 'old' | 'new'); всё остальное
   общее для старого и нового экрана. */
(function () {
  'use strict';
  const LAYER = () => window.__RD_LAYER || 'old';

  /* ── Числа: 10 значащих цифр ─────────────────────────────────────────
     При 12 знаках слепок дрожал между двумя загрузками одной модели:
     пересечение D и S выходило то 50, то 49,9999999999 (численный поиск
     crossPoints, 60-overlays.js:463). Допуск инварианта «слепок STATE» —
     1e-9, десяти знаков для него хватает с запасом. */
  const num = (v) => {
    if (typeof v !== 'number') return v;
    if (!isFinite(v)) return String(v);
    if (v === 0) return 0;
    const r = +v.toPrecision(10);
    return r === 0 ? 0 : r;   // −0 и 0 в слепке одно и то же
  };

  /* ── Слепок STATE: всё простое, кроме недетерминированного ──────────────
     Список исключений короткий и с причиной у каждого: пиксели и следы мыши
     зависят от размера холста и курсора, а не от модели. */
  const STATE_SKIP = new Set([
    'panels',        // прямоугольники панелей в пикселях и функции шкал (20-plane.js:178)
    'pointerPx', 'pointerPy',   // последнее положение мыши (52-modes.js:586)
    'resizeRedraws', // счётчик перерисовок наблюдателя размера (86-workspace.js:591)
    'roller', 'hoverCross', 'armedCurve',   // следы наведения мыши
    'titlePos',      // место названия графика в пикселях (тянется мышью)
    '_paramsSig', '_sumSig',    // служебные подписи пересборки пульта
  ]);
  function plain(v, depth) {
    if (v === null || v === undefined) return null;
    const t = typeof v;
    if (t === 'number') return num(v);
    if (t === 'string' || t === 'boolean') return v;
    if (t === 'function') return undefined;
    if (depth > 6) return undefined;
    if (Array.isArray(v)) {
      const out = [];
      for (let i = 0; i < Math.min(v.length, 4000); i++) {
        const x = plain(v[i], depth + 1);
        out.push(x === undefined ? null : x);
      }
      return out;
    }
    if (t === 'object') {
      const pr = Object.getPrototypeOf(v);
      if (pr !== Object.prototype && pr !== null) return undefined;   // узлы, шкалы d3, скомпилированные формулы
      const out = {};
      Object.keys(v).sort().forEach(k => {
        if (k.charAt(0) === '_') return;
        const x = plain(v[k], depth + 1);
        if (x !== undefined) out[k] = x;
      });
      return out;
    }
    return undefined;
  }
  function stateDump() {
    const out = {};
    Object.keys(STATE).sort().forEach(k => {
      if (STATE_SKIP.has(k) || k.charAt(0) === '_') return;
      const x = plain(STATE[k], 0);
      if (x !== undefined) out[k] = x;
    });
    return out;
  }

  /* ── Окна: границы CONFIG и окно каждой зарегистрированной панели ── */
  function windows() {
    const out = { config: {} };
    ['Qmin', 'Qmax', 'Pmin', 'Pmax'].forEach(k => { out.config[k] = num(CONFIG[k]); });
    out.panels = {};
    (STATE.panels || []).forEach(p => {
      try {
        const w = viewWindow(p.id);
        out.panels[p.id] = { x0: num(w.x0), x1: num(w.x1), y0: num(w.y0), y1: num(w.y1) };
      } catch (e) { out.panels[p.id] = 'ошибка'; }
    });
    return out;
  }

  /* ── Геометрия холста в координатах модели ──────────────────────────────
     Точку пути относим к панели, в прямоугольник которой она попала, и
     переводим шкалами ЭТОЙ панели (CODE_NOTES 12.5). Цвета, подписи, вид
     ручек и точек в слепок не входят: они меняются по замыслу. Ручки (узлы с
     d3.drag) и служебные узлы (data-service) пропускаются. */
  const isDrag = (el) => {
    for (let n = el; n && n.nodeType === 1 && n.id !== 'chart'; n = n.parentNode) {
      if (n.__on && n.__on.some(o => o.name === 'drag')) return true;
      if (n.hasAttribute && n.hasAttribute('data-service')) return true;
    }
    return false;
  };
  function panelOfPx(x, y) {
    const list = STATE.panels || [];
    let best = null, bd = Infinity;
    list.forEach(p => {
      const dx = Math.max(p.x0 - x, 0, x - p.x1), dy = Math.max(p.y0 - y, 0, y - p.y1);
      const d = Math.hypot(dx, dy);
      if (d < bd) { bd = d; best = p; }
    });
    return best;
  }
  function toModel(p, x, y) { return [num(p.mx.invert(x)), num(p.my.invert(y))]; }
  function pathPoints(d) {
    // d3.line пишет M/L с абсолютными координатами; дуги и кривые Безье
    // встречаются только у значков, их точки берём как есть по парам чисел.
    const pts = [];
    String(d || '').replace(/[ML]\s*(-?[\d.]+(?:e-?\d+)?)[ ,](-?[\d.]+(?:e-?\d+)?)/g,
      (_, a, b) => { pts.push([+a, +b]); return ''; });
    return pts;
  }
  function applyM(m, x, y) { return m ? [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f] : [x, y]; }
  function thin(pts) {
    // Каждая двадцатая точка, концы и изломы (поворот больше 1°).
    if (pts.length <= 24) return pts;
    const keep = new Set([0, pts.length - 1]);
    for (let i = 0; i < pts.length; i += 20) keep.add(i);
    for (let i = 1; i < pts.length - 1; i++) {
      const a = pts[i - 1], b = pts[i], c = pts[i + 1];
      const a1 = Math.atan2(b[1] - a[1], b[0] - a[0]), a2 = Math.atan2(c[1] - b[1], c[0] - b[0]);
      let da = Math.abs(a1 - a2); if (da > Math.PI) da = 2 * Math.PI - da;
      if (da > Math.PI / 180) keep.add(i);
    }
    return [...keep].sort((x, y) => x - y).map(i => pts[i]);
  }
  function geometry(full) {
    const svg = document.getElementById('chart');
    const out = { paths: [], lines: [], rects: [], dots: [], keyPoints: {} };
    if (!svg || !(STATE.panels || []).length) return out;
    const vis = (el) => {
      for (let n = el; n && n !== svg; n = n.parentNode) {
        const cs = getComputedStyle(n);
        if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
      }
      return true;
    };
    svg.querySelectorAll('path, line, rect, circle, polyline, polygon').forEach(el => {
      if (isDrag(el) || !vis(el)) return;
      if (el.closest('defs, clipPath, marker, mask, pattern, .katex, foreignObject')) return;
      // Сетка и оси зависят от размера холста (число делений), а не от модели.
      if (el.closest('.grid, .axes, [class*="axis"], [class*="grid"], [class*="tick"]')) return;
      const m = el.transform && el.transform.baseVal && el.transform.baseVal.numberOfItems
        ? el.transform.baseVal.consolidate().matrix : null;
      const tag = el.tagName.toLowerCase();
      const fill = (el.getAttribute('fill') || getComputedStyle(el).fill || '');
      const filled = fill && fill !== 'none' && !/rgba\(0, 0, 0, 0\)/.test(fill);
      if (tag === 'path' || tag === 'polyline' || tag === 'polygon') {
        let px = tag === 'path' ? pathPoints(el.getAttribute('d'))
          : String(el.getAttribute('points') || '').trim().split(/\s+/).map(s => s.split(',').map(Number));
        px = px.map(([x, y]) => applyM(m, x, y));
        if (px.length < 2) return;
        // Панель — по большинству точек.
        const cnt = new Map();
        px.forEach(([x, y]) => { const p = panelOfPx(x, y); if (p) cnt.set(p, (cnt.get(p) || 0) + 1); });
        let p = null, best = -1; cnt.forEach((n, k) => { if (n > best) { best = n; p = k; } });
        if (!p) return;
        const mp = px.map(([x, y]) => toModel(p, x, y));
        out.paths.push({ panel: p.id, filled: !!filled, n: mp.length, pts: full ? mp : thin(mp) });
      } else if (tag === 'line') {
        const a = applyM(m, +el.getAttribute('x1'), +el.getAttribute('y1'));
        const b = applyM(m, +el.getAttribute('x2'), +el.getAttribute('y2'));
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 7) return;   // деление оси, а не линия модели
        const p = panelOfPx((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
        if (!p) return;
        out.lines.push({ panel: p.id, a: toModel(p, a[0], a[1]), b: toModel(p, b[0], b[1]) });
      } else if (tag === 'rect') {
        // Подложка подписи и легенда: их размер считается по ширине текста
        // (и дрожит на загрузке шрифта), а подписи и легенда в слепок не входят.
        if (el.parentNode && el.parentNode.querySelector(':scope > text')) return;
        if (el.closest('.legend, [class*="legend"], [data-legend-box]')) return;
        const x = +el.getAttribute('x'), y = +el.getAttribute('y');
        const w = +el.getAttribute('width'), h = +el.getAttribute('height');
        if (!isFinite(x) || !isFinite(w) || w <= 0 || h <= 0) return;
        const a = applyM(m, x, y), b = applyM(m, x + w, y + h);
        const p = panelOfPx((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
        if (!p) return;
        // Фон панели и обрезку не считаем: прямоугольник во всю панель.
        if (Math.abs(a[0] - p.x0) < 1 && Math.abs(b[0] - p.x1) < 1 && Math.abs(a[1] - p.y0) < 1 && Math.abs(b[1] - p.y1) < 1) return;
        out.rects.push({ panel: p.id, filled: !!filled, a: toModel(p, a[0], a[1]), b: toModel(p, b[0], b[1]) });
      } else if (tag === 'circle') {
        if (el.closest('.kp-mark, .kp-layer, [data-key-point]')) return;   // ключевые точки берём у движка
        const c = applyM(m, +el.getAttribute('cx'), +el.getAttribute('cy'));
        const p = panelOfPx(c[0], c[1]);
        if (!p) return;
        out.dots.push({ panel: p.id, c: toModel(p, c[0], c[1]), r: num(+el.getAttribute('r')) });
      }
    });
    (STATE.panels || []).forEach(p => {
      try {
        out.keyPoints[p.id] = keyTargets(p.id).map(k => [num(k.x), num(k.y), k.kind || '']);
      } catch (e) { out.keyPoints[p.id] = 'ошибка'; }
    });
    const key = (o) => JSON.stringify(o);
    ['paths', 'lines', 'rects', 'dots'].forEach(k => out[k].sort((a, b) => key(a) < key(b) ? -1 : 1));
    Object.keys(out.keyPoints).forEach(id => {
      if (Array.isArray(out.keyPoints[id])) out.keyPoints[id].sort((a, b) => key(a) < key(b) ? -1 : 1);
    });
    return out;
  }

  /* ── Текст без невидимой половины KaTeX (calc2/CLAUDE.md, ловушки) ── */
  function text(el) {
    if (!el) return '';
    const c = el.cloneNode(true);
    c.querySelectorAll('.katex-mathml, annotation, .stat-sign, button').forEach(x => x.remove());
    return c.textContent.replace(/[\s   ]+/g, ' ').trim();
  }
  const visible = (el) => {
    if (!el || !el.isConnected) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) < 0.05) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0.5 && r.height > 0.5;
  };
  /* «Показано сценой»: узел не спрятан ни сценой, ни маршрутом. Свёрнутость
     карточек сюда не входит: прибор сначала раскрывает всё. */
  const shownByScene = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (n.hidden) return false;
      if (n.style && n.style.display === 'none') return false;
      if (n.classList && n.classList.contains('scoped-off')) return false;
    }
    return true;
  };

  /* ── Ответ старого экрана: табло #sb-body, «Объяснение модели», заголовок ── */
  function answerOld() {
    const out = { blocks: [], title: '', explain: [], tips: [] };
    const sb = document.getElementById('sb-body');
    const title = document.querySelector('#sec-eq .section-title');
    if (title && shownByScene(title)) out.title = text(title);
    if (sb) {
      const blocks = [...sb.children].filter(b => b.id && shownByScene(b));
      blocks.forEach(b => {
        const r = readBlock(b);
        // Пустые блоки чужих сцен в слепок не идут: они ничего не показывают.
        if (r.rows.length || r.tables.length || r.notes.length || r.warns.length || r.final.length) out.blocks.push(r);
      });
    }
    const ex = document.getElementById('ex-body');
    if (ex) {
      ex.querySelectorAll(':scope > .sb-note').forEach(n => {
        if (!shownByScene(n)) return;
        const ps = n.querySelectorAll(':scope > p');
        if (ps.length) ps.forEach(p => out.explain.push(text(p)));
        else out.explain.push(text(n));
      });
    }
    return out;
  }
  /* Блок табло: строки .stat (подпись, значение), таблицы, пояснения,
     предупреждения, итоговая функция. Порядок — порядок в разметке. */
  function readBlock(b) {
    const blk = { id: b.id, rows: [], tables: [], notes: [], warns: [], final: [] };
    let i = 0;
    b.querySelectorAll('.stat').forEach(s => {
      if (!shownByScene(s)) return;
      const lab = s.querySelector(':scope > span');
      const val = s.querySelector(':scope > b');
      blk.rows.push({ i: i++, label: text(lab), value: text(val), raw: val ? (val.dataset.v || null) : null });
    });
    b.querySelectorAll('table').forEach(t => {
      if (!shownByScene(t)) return;
      blk.tables.push([...t.querySelectorAll('tr')].map(tr => [...tr.children].map(td => text(td))));
    });
    b.querySelectorAll('.hint, .muted, .scope-note, .sb-note, .note').forEach(h => {
      if (!shownByScene(h) || h.closest('.stat')) return;
      if (h.parentElement && h.parentElement.closest('.hint, .muted, .scope-note, .sb-note, .note') &&
          h.parentElement.closest('.hint, .muted, .scope-note, .sb-note, .note') !== h) return;
      blk.notes.push(text(h));
    });
    b.querySelectorAll('.warn').forEach(w => { if (shownByScene(w)) blk.warns.push(text(w)); });
    b.querySelectorAll('.ff').forEach(f => {
      if (!shownByScene(f)) return;
      const copy = f.querySelector('[data-ff-expr]');
      const mth = f.querySelector('[data-ff-tex]');
      blk.final.push({ name: text(f.querySelector('.ff-name')), tex: mth ? mth.getAttribute('data-ff-tex') : '',
                       copy: copy ? copy.getAttribute('data-ff-expr') : '' });
    });
    return blk;
  }

  /* Тексты подсказок: data-tip у видимых органов, тела кнопок «?» и абзацы
     .hint в панели ввода. Набор, а не список: порядок раскладки не важен. */
  function tipsOld() {
    const s = new Set();
    document.querySelectorAll('.app [data-tip]').forEach(el => {
      if (visible(el) && !el.closest('#chart')) s.add(el.getAttribute('data-tip'));
    });
    document.querySelectorAll('.app .hint-btn[data-pop]').forEach(b => {
      if (!visible(b)) return;
      const pop = document.getElementById(b.getAttribute('data-pop'));
      if (pop) s.add('?' + b.getAttribute('data-pop') + ': ' + text(pop));
    });
    document.querySelectorAll('#tools-panel .hint, #params-panel #params-body .hint, #sec-tax .hint').forEach(h => {
      if (visible(h)) s.add('hint: ' + text(h));
    });
    return [...s].sort();
  }

  /* ── Органы управления ─────────────────────────────────────────────────
     Всё, что человек может нажать, набрать, сдвинуть. Ключ — id, а где его
     нет, составной: ближайший предок с id, роль узла и порядковый номер. */
  const CTRL_SEL = 'input:not([type=hidden]), select, button, math-field, textarea, [role=switch], '
    + '[contenteditable=true], .pchip-editable, .edval, [data-editable]';
  function ctrlKind(el) {
    const t = el.tagName.toLowerCase();
    if (t === 'input') return 'input:' + el.type;
    if (t === 'math-field') return 'math-field';
    if (el.classList.contains('pchip-editable')) return 'exact';
    if (el.classList.contains('edval')) return 'edval';
    if (el.classList.contains('param-bound')) return 'bounds';
    if (el.getAttribute('role') === 'switch') return 'switch';
    return t;
  }
  function ctrlKey(el) {
    if (el.id) return '#' + el.id;
    // Поле MathLive: ключ по его скрытому input (у него id есть).
    if (el.tagName.toLowerCase() === 'math-field') {
      const inp = el._inp || (el.parentElement && el.parentElement.querySelector('input[id]'));
      if (inp && inp.id) return 'mf:#' + inp.id;
    }
    const anc = el.parentElement ? el.parentElement.closest('[id]') : null;
    const cls = (el.className && typeof el.className === 'string') ? el.className.split(/\s+/).filter(c => c && !/^(open|active|on|bad|no-init-ring|is-)/.test(c))[0] || '' : '';
    const role = [el.tagName.toLowerCase(), cls, el.dataset.col || el.dataset.cid || el.dataset.scene || el.dataset.mode || ''].filter(Boolean).join('.');
    let idx = 0;
    if (anc) {
      const same = [...anc.querySelectorAll(CTRL_SEL)].filter(x => {
        const a2 = x.parentElement ? x.parentElement.closest('[id]') : null;
        if (a2 !== anc) return false;
        const c2 = (x.className && typeof x.className === 'string') ? x.className.split(/\s+/).filter(c => c && !/^(open|active|on|bad|no-init-ring|is-)/.test(c))[0] || '' : '';
        return [x.tagName.toLowerCase(), c2, x.dataset.col || x.dataset.cid || x.dataset.scene || x.dataset.mode || ''].filter(Boolean).join('.') === role;
      });
      idx = same.indexOf(el);
    }
    return (anc ? '#' + anc.id : '') + '>' + role + (idx > 0 ? '[' + idx + ']' : '');
  }
  function ctrlLabel(el) {
    const a = el.getAttribute('aria-label') || el.getAttribute('data-tip');
    if (a) return a;
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) return text(l);
    }
    const wrap = el.closest('label');
    if (wrap) return text(wrap).slice(0, 80);
    const f = el.closest('.field, .pchip, .wrench-row, .crow');
    if (f) { const l = f.querySelector('label, .pchip-label, .wrench-label'); if (l && l !== el) return text(l).slice(0, 80); }
    if (el.placeholder) return el.placeholder;
    return text(el).slice(0, 80);
  }
  function ctrlSection(el) {
    const s = el.closest('.modal, #wrench-pop, .section, .side-part, .graph-tools, .dock, .side-head, .side-reset, #params-body, .side');
    if (!s) return '';
    return s.id ? '#' + s.id : '.' + s.className.split(/\s+/)[0];
  }
  function ctrlProps(el) {
    const t = el.tagName.toLowerCase();
    const p = {};
    if (t === 'input') {
      if (el.type === 'checkbox' || el.type === 'radio') p.checked = el.checked;
      else p.value = el.value;
      if (el.type === 'range' || el.type === 'number') { p.min = el.min; p.max = el.max; p.step = el.step; }
    } else if (t === 'select') {
      p.value = el.value; p.options = [...el.options].map(o => o.value + '=' + o.textContent.trim());
    } else if (t === 'math-field') {
      const inp = el._inp || (el.parentElement && el.parentElement.querySelector('input'));
      p.value = inp ? inp.value : el.value;
    } else if (el.classList.contains('edval')) {
      p.value = el.textContent;
    } else {
      const pr = el.getAttribute('aria-pressed') || el.getAttribute('aria-checked') || el.getAttribute('aria-selected');
      if (pr) p.pressed = pr;
      if (el.classList.contains('active') || el.classList.contains('on')) p.active = true;
      if (el.disabled) p.disabled = true;
    }
    return p;
  }
  /* Где искать органы: рабочее место, окно выбора (если открыто) и всё, что
     calc2 вешает прямо в body (меню цвета .cpick-menu, выпадающие списки).
     Шапка сайта, метка версии, кружок Telegram и угол с «Всё ли нравится?»
     органами модели не являются. */
  const NOT_MODEL = '.site-nav, nav, .site-version, #corner-stack, .tg-fab, #hint-tip, script, style, template';
  function roots() {
    const out = [];
    [...document.body.children].forEach(ch => {
      if (ch.matches(NOT_MODEL) || ch.tagName === 'FORM' || ch.tagName === 'INPUT') return;
      if (ch.id === 'scene-picker' && ch.classList.contains('hidden')) return;
      out.push(ch);
    });
    return out;
  }
  function controls(root) {
    const out = [];
    const seen = new Set();
    const roots_ = root ? [root] : roots();
    roots_.forEach(r => {
      if (!r) return;
      r.querySelectorAll(CTRL_SEL).forEach(el => {
        if (seen.has(el)) return;
        if (el.closest('nav.site-nav, #site-nav, header.site-header')) return;
        if (el.closest('#chart')) return;
        if (!visible(el)) {
          // Поле MathLive прячет свой input: такой input органом не считаем.
          return;
        }
        seen.add(el);
        const c = { key: ctrlKey(el), kind: ctrlKind(el), label: ctrlLabel(el), section: ctrlSection(el), props: ctrlProps(el) };
        if (el.closest('#scene-picker')) c.picker = true;
        out.push(c);
      });
    });
    // Ключи обязаны быть уникальны: иначе шаг сценария не найдёт свой орган.
    const n = new Map();
    out.forEach(c => { const k = c.key; const i = n.get(k) || 0; n.set(k, i + 1); if (i) c.key = k + '~' + i; });
    return out;
  }
  function findControl(key) {
    const list = [];
    const seen = new Set();
    roots().forEach(r => r && r.querySelectorAll(CTRL_SEL).forEach(el => {
      if (seen.has(el) || el.closest('#chart') || !visible(el)) return;
      seen.add(el); list.push(el);
    }));
    const n = new Map();
    for (const el of list) {
      let k = ctrlKey(el); const i = n.get(k) || 0; n.set(k, i + 1); if (i) k = k + '~' + i;
      if (k === key) return el;
    }
    return null;
  }

  /* ── Готовность экрана к слепку (CODE_NOTES 12.3) ── */
  function settled() {
    if (typeof _rangeAnimReq !== 'undefined' && _rangeAnimReq !== null) return false;
    if (typeof _rangeSchedT !== 'undefined' && _rangeSchedT !== null) return false;
    // Поле формулы ждёт в очереди _mfWaiting, пока его слот не на экране
    // (82-input.js:860, 979). Видимое и не собранное — экран не готов.
    if (typeof _mfWaiting !== 'undefined' && typeof fieldOnScreen === 'function' && typeof MATHLIVE_READY !== 'undefined'
        && MATHLIVE_READY && _mfWaiting.some(i => i.isConnected && fieldOnScreen(i))) return false;
    return true;
  }

  /* Все ручки холста: узлы с d3.drag. Ключ — класс и порядковый номер. */
  function handles() {
    const svg = document.getElementById('chart');
    if (!svg) return [];
    const out = [];
    const cnt = new Map();
    svg.querySelectorAll('*').forEach(el => {
      if (!(el.__on && el.__on.some(o => o.name === 'drag'))) return;
      const r = el.getBoundingClientRect();
      if (r.width < 0.5 && r.height < 0.5) return;
      const cls = (el.getAttribute('class') || el.tagName).split(/\s+/)[0];
      const i = cnt.get(cls) || 0; cnt.set(cls, i + 1);
      out.push({ key: cls + '#' + i, x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height,
                 cursor: getComputedStyle(el).cursor });
    });
    return out;
  }

  /* Открытые всплывашки с текстом: подсказка #hint-tip, тела кнопок «?»,
     карточки примеров формул. Нужны, чтобы щелчок по «?» считался действием. */
  function popups() {
    const out = [];
    document.querySelectorAll('#hint-tip, [id^=hp-], .hint-pop, .f-pop, [role=tooltip], .popover, .toast').forEach(el => {
      if (visible(el)) out.push((el.id ? '#' + el.id : '.' + String(el.className).split(/\s+/)[0]) + ': ' + text(el).slice(0, 400));
    });
    return out.sort();
  }

  window.__RD = { popups, stateDump, windows, geometry, answerOld, tipsOld, controls, findControl, settled, handles, text, visible, shownByScene };
})();
