/* calc-models.js — живые модели макета «Графики» и единый вид для любой из 42.
   Каждая модель отдаёт ОДНУ и ту же структуру:
     left   — секции «Условия»: функции, параметры, вмешательство, что показать;
     chart  — панели холста (готовая геометрия: пути, заливки, точки, ручки);
     answer — «Ответ»: главные числа, таблица «было → стало», итоговая функция, разбор.
   Разметка артборда рисует эту структуру, не зная, какая модель перед ней.
   Это и есть предложение для calc2: один каркас на все модели. */
(function () {
  'use strict';
  var E = (window.CalcEngine = window.CalcEngine || {});
  var C = E.CV, fmt = E.fmt, fmtD = E.fmtDelta, MINUS = E.MINUS;
  var LS = 1;   // масштаб подписей на холсте («Вид графика» → размер подписей)
  var CO = {}, LB = {};   // свои цвета и подписи кривых (ms.colors, ms.labels)
  var XCOL = ['var(--c-mr)', 'var(--c-reg)', 'var(--c-tax)', 'var(--c-mc)'];
  /* Изломы и разрывы всех функций модели (в единицах оси): через них проходят узлы
     кривых и границы интегрирования. Собираются заново при каждом расчёте вида. */
  var BRK = [];
  function addBreaks() {
    for (var i = 0; i < arguments.length; i++) if (arguments[i] && arguments[i].breaks) BRK = BRK.concat(arguments[i].breaks);
    BRK.sort(function (a, b) { return a - b; });
    BRK = BRK.filter(function (x, i) { return !i || Math.abs(x - BRK[i - 1]) > 1e-9; });
  }
  function I(g, a, b) { return E.integrate(g, a, b, undefined, BRK); }
  /* Производная: рядом с изломом берётся с той стороны, где стоит точка, иначе наклон
     двух кусков смешается (у MR в изломе спроса это дало бы ложное значение). */
  function dF(f, x) {
    var h = 1e-4 * Math.max(1, Math.abs(x));
    for (var i = 0; i < BRK.length; i++) {
      var b = BRK[i];
      if (Math.abs(x - b) < h) return x < b ? (f(x) - f(x - h)) / h : (f(x + h) - f(x)) / h;
    }
    return (f(x + h) - f(x - h)) / (2 * h);
  }

  /* ── общие мелочи ─────────────────────────────────────────────────────── */
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  E.clone = clone;
  function m(s) { return E.mathTokens(s); }                 // обозначение → токены
  function num(v, d) { return fmt(v, d === undefined ? 2 : d); }
  function pct(v) { return fmt(v * 100, 1) + ' %'; }

  /* Элементы управления — одна форма на всю панель. */
  function seg(id, label, options, value) {
    return { type: 'seg', id: id, label: label, options: options.map(function (o) { return { id: o[0], label: o[1], on: o[0] === value }; }) };
  }
  function slider(id, label, sym, min, max, step, value, unit, hint) {
    return {
      type: 'slider', id: id, label: label, sym: sym ? m(sym) : [], min: min, max: max, step: step,
      value: value, text: fmt(value, step < 1 ? 2 : 0), unit: unit || '', hint: hint || '',
      minText: fmt(min, 2), maxText: fmt(max, 2)
    };
  }
  function toggle(id, label, on, swatch, sym) { return { type: 'toggle', id: id, label: label, on: !!on, swatch: swatch || '', sym: sym ? m(sym) : [] }; }
  function note(text, tone) { return { type: 'note', text: text, tone: tone || 'plain' }; }
  function numField(id, label, sym, value) { return { type: 'num', id: id, label: label, sym: sym ? m(sym) : [], value: String(value) }; }

  /* ── функции модели: разбор с учётом сдвига и букв ─────────────────────── */
  /* Граница участка: пусто — открытая (null), число — число, иначе NaN (ошибка). */
  function boundVal(t) {
    t = String(t === undefined || t === null ? '' : t).trim();
    if (t === '') return null;
    var c = E.compile(t, '\u0001');
    if (!c.ok || c.letters.length) return NaN;
    var v = c.f(0, {});
    return v === Infinity || v === -Infinity ? null : v;
  }
  function lowerFirst(t) { t = String(t || ''); return t.charAt(0).toLowerCase() + t.slice(1); }
  function spanText(lo, hi, v) {
    if (lo === -Infinity && hi === Infinity) return 'везде';
    if (lo === -Infinity) return 'при ' + v + ' до ' + num(hi);
    if (hi === Infinity) return 'при ' + v + ' от ' + num(lo);
    return 'при ' + v + ' от ' + num(lo) + ' до ' + num(hi);
  }
  /* Строки «формула · от · до» → запись для движка (цепочка условий, как pwFormula в calc2),
     ошибки по строкам и замечания про перекрытия и дыры в области. */
  function piecesInfo(pieces, axis) {
    var errors = [], notes = [], form = null, mixed = false, iv = [];
    pieces.forEach(function (pc, i) {
      var t = String(pc.expr || '').trim(), n = i + 1;
      if (!t) errors.push({ i: i, field: 'expr', text: 'Кусок ' + n + ': впишите формулу' });
      else {
        var c = E.compileFn(t, axis);
        if (!c.ok) errors.push({ i: i, field: 'expr', text: 'Кусок ' + n + ': ' + lowerFirst(c.error) });
        else { var f = c.form || 'PQ'; if (form === null) form = f; else if (form !== f) mixed = true; }
      }
      var a = boundVal(pc.from), b = boundVal(pc.to);
      if (a !== a && a !== null) errors.push({ i: i, field: 'from', text: 'Кусок ' + n + ': граница «от» должна быть числом' });
      if (b !== b && b !== null) errors.push({ i: i, field: 'to', text: 'Кусок ' + n + ': граница «до» должна быть числом' });
      if (typeof a === 'number' && typeof b === 'number' && a === a && b === b && !(a < b)) errors.push({ i: i, field: 'to', text: 'Кусок ' + n + ': «от» должно быть меньше «до»' });
      iv.push({ a: typeof a === 'number' && a === a ? a : -Infinity, b: typeof b === 'number' && b === b ? b : Infinity });
    });
    if (mixed) errors.push({ i: -1, field: 'expr', text: 'Куски записаны по-разному: либо все как P от Q, либо все как Q от P' });
    form = form || 'PQ';
    var v = form === 'QP' ? 'P' : axis;
    if (!errors.length && iv.length > 1) {
      for (var i = 0; i < iv.length; i++) for (var j = i + 1; j < iv.length; j++) {
        var lo = Math.max(iv[i].a, iv[j].a), hi = Math.min(iv[i].b, iv[j].b);
        if (lo < hi) notes.push('Куски ' + (i + 1) + ' и ' + (j + 1) + ' перекрываются ' + spanText(lo, hi, v) + ': там считается кусок ' + (i + 1) + '.');
      }
      var srt = iv.slice().sort(function (x, y) { return x.a - y.a; }), reach = srt[0].b;
      for (var k = 1; k < srt.length; k++) {
        if (srt[k].a > reach) notes.push('При ' + v + ' от ' + num(reach) + ' до ' + num(srt[k].a) + ' функция не задана.');
        reach = Math.max(reach, srt[k].b);
      }
    }
    var lhs = form === 'QP' ? 'Q = ' : (axis === 'x' ? 'y = ' : 'P = ');
    return { ok: !errors.length, error: errors.length ? errors[0].text : '', errors: errors, notes: notes, form: form, v: v, text: lhs + E.pwText(pieces, v) };
  }
  E.piecesInfo = piecesInfo;

  function fnOf(ms, id, axis) {
    var fs = ms.fns[id], src, pw = null;
    axis = axis || 'Q';
    if (fs && fs.pieces && fs.pieces.length) {
      pw = piecesInfo(fs.pieces, axis);
      if (!pw.ok) return { ok: false, error: pw.error, letters: [], pw: pw };
      src = pw.text;
    } else {
      if (!fs || !String(fs.expr || '').trim()) return { ok: false, empty: true, error: 'Формула пустая', letters: [] };
      src = fs.expr;
    }
    var c = E.compileFn(src, axis);
    if (!c.ok) return { ok: false, error: c.error, letters: [], pw: pw };
    var shift = fs.shift || 0, params = ms.letters || {};
    c.letters.forEach(function (l) { if (params[l] === undefined) params[l] = 1; });
    var out = { ok: true, form: c.form || 'PQ', letters: c.letters, f: function (x) { return c.f(x, params) + shift; }, base: function (x) { return c.f(x, params); }, pw: pw, v: c.form === 'QP' ? 'P' : axis };
    // изломы в единицах оси и строки кусочной записи (и собранной кусками, и набранной руками через «?:»)
    out.breaks = c.form === 'QP' ? c.breaksQ(params) : (c.breaks || []);
    var rows = c.form === 'QP' ? c.rowsP : c.rows;
    if (rows) out.rows = rows.map(function (rw) {
      return { from: rw.from, to: rw.to, fromInc: rw.fromInc, toInc: rw.toInc, rest: rw.rest, ast: rw.ast, f: function (x) { return rw.f(x, params) + (c.form === 'QP' ? 0 : shift); } };
    });
    // запись Q(P) → канон P = a + bQ, чтобы человек видел, что именно посчитано
    if (c.form === 'QP') {
      var L = c.linear(params);
      out.canon = L && Math.abs(L.d) > 1e-12 ? E.linearText(-L.c / L.d, 1 / L.d, 'Q') : null;
      // кусочная Q(P) из прямых: тот же канон по участкам, уже с условиями по Q
      if (out.rows) {
        var cr = out.rows.map(function (rw) {
          var lo = rw.from !== null ? rw.from : 0, hi = rw.to !== null ? rw.to : lo + 100;
          var ln = E.linearOf(rw.f, lo, hi);
          if (!ln || Math.abs(ln.b) < 1e-12) return null;
          var qa = rw.from !== null ? ln.a + ln.b * rw.from : null, qb = rw.to !== null ? ln.a + ln.b * rw.to : null;
          var dec = ln.b < 0;
          return { text: E.linearText(-ln.a / ln.b + shift, 1 / ln.b, 'Q'), from: dec ? qb : qa, to: dec ? qa : qb, fromInc: dec ? !!rw.toInc : !!rw.fromInc, toInc: dec ? !!rw.fromInc : !!rw.toInc, rest: false };
        });
        out.canonRows = cr.every(function (x) { return !!x; }) ? cr.sort(function (x, y) { return (x.from === null ? -Infinity : x.from) - (y.from === null ? -Infinity : y.from); }) : null;
        out.canon = null;
      }
    }
    return out;
  }

  /* Строка функции для «Условия». */
  function fnRow(ms, def, fres, opts) {
    opts = opts || {};
    var fs = ms.fns[def.id];
    var row = {
      id: def.id, sym: m(LB[def.id] || def.sym), name: def.name, color: CO[def.id] || def.color, visible: fs.visible !== false, axis: def.axis || 'Q',
      prefix: fres.form === 'QP' ? 'Q =' : (def.prefix || 'P ='), expr: fs.expr, toks: E.typeset(fs.expr), error: fres.ok ? '' : fres.error,
      canHide: opts.canHide !== false, sliders: [],
      isQP: fres.form === 'QP',
      // нелинейная Q(P) обращается численно: пишем это словами, а не пустую строку
      canonToks: fres.canon ? E.typeset(fres.canon) : (fres.form === 'QP' ? [{ k: 'raw', t: 'обратная функция, считаем численно' }] : []),
      canonText: fres.canon ? 'P = ' + E.prettyExpr(fres.canon) : (fres.form === 'QP' ? 'P: обратная функция, считаем численно' : '')
    };
    // кусочная запись: строки для ввода и запись скобкой для показа
    var axis = def.axis || 'Q';
    row.pw = !!(fs.pieces && fs.pieces.length);
    row.v = fres.v || axis;
    row.fromPh = axis === 'x' ? MINUS + '∞' : '0';
    if (row.pw) {
      var info = fres.pw || piecesInfo(fs.pieces, axis);
      row.v = info.v;
      row.prefix = info.form === 'QP' ? 'Q =' : (def.prefix || 'P =');
      row.isQP = info.form === 'QP';
      row.pieces = fs.pieces.map(function (pc, i) {
        var er = info.errors.filter(function (e) { return e.i === i; });
        return { i: i, expr: pc.expr || '', from: pc.from === undefined || pc.from === null ? '' : String(pc.from), to: pc.to === undefined || pc.to === null ? '' : String(pc.to),
          errExpr: er.some(function (e) { return e.field === 'expr'; }), errFrom: er.some(function (e) { return e.field === 'from'; }), errTo: er.some(function (e) { return e.field === 'to'; }) };
      });
      row.notes = info.notes;
      if (!info.ok) row.error = info.error;
    }
    if (fres.ok && fres.rows) {
      row.record = fres.rows.map(function (rw) { return { toks: E.typesetAst(rw.ast), cond: E.condToks(rw, row.v), rest: !!rw.rest }; });
      if (fres.form === 'QP') {
        row.canonRows = fres.canonRows ? fres.canonRows.map(function (cr) { return { toks: E.typeset(cr.text), cond: E.condToks(cr, 'Q'), rest: false }; }) : null;
        if (!fres.canonRows) { row.canonToks = [{ k: 'raw', t: 'обратная функция, считаем численно' }]; row.canonText = 'P: обратная функция, считаем численно'; }
      }
    }
    if (fres.ok) {
      fres.letters.forEach(function (l) {
        row.sliders.push(slider('letter.' + l, 'буква', l, -10, 10, 0.1, (ms.letters || {})[l] !== undefined ? ms.letters[l] : 1, '', 'Буква из формулы стала ползунком'));
      });
      if (opts.shift && !fres.rows) {
        var lim = opts.shiftLim || 50;
        row.sliders.push(slider('fns.' + def.id + '.shift', 'сдвиг', '', -lim, lim, 1, fs.shift || 0, '', 'Параллельный сдвиг кривой'));
      }
    }
    return row;
  }

  /* ── окно рынка: по пересечениям кривых с осями, «круглыми» числами ─── */
  function marketWindow(fs, extraQ, extraP) {
    var D = fs[0];
    var qz = D ? E.firstRoot(function (q) { return D(q); }, 0, 5000, 2500) : null;
    var qmax = qz || 100;
    (extraQ || []).forEach(function (q) { if (isFinite(q)) qmax = Math.max(qmax, q * 1.15); });
    qmax = E.niceCeil(qmax);
    var pmax = 0;
    fs.forEach(function (f) { var v0 = f(0); if (isFinite(v0)) pmax = Math.max(pmax, v0); });
    (extraP || []).forEach(function (p) { if (isFinite(p)) pmax = Math.max(pmax, p * 1.1); });
    if (!(pmax > 0)) pmax = 100;
    pmax = E.niceCeil(pmax);
    return { x0: 0, x1: qmax, y0: 0, y1: pmax };
  }

  function equilibrium(D, S, span) {
    var r = E.roots(function (q) { return D(q) - S(q); }, 0, span, 3000);
    for (var i = 0; i < r.length; i++) { var p = D(r[i]); if (r[i] >= -1e-9 && p >= -1e-9) return { q: Math.max(0, r[i]), p: Math.max(0, p) }; }
    return null;
  }
  function posPart(f) { return function (x) { return Math.max(0, f(x)); }; }

  /* ── холст: общие куски ────────────────────────────────────────────────── */
  function base(P, ctx) {
    return {
      id: P.id, plot: P.plot, win: P.win, clipId: 'clip-' + P.id + '-' + (ctx.uid || 'a'),
      grid: P.grid.map(function (g) { return { x1: g.x1, y1: g.y1, x2: g.x2, y2: g.y2, c: g.major ? 'var(--grid-strong)' : 'var(--grid)' }; }),
      axis: P.axis, ticksX: P.ticksX, ticksY: P.ticksY, keyTicks: [], fills: [], ghosts: [], curves: [], hits: [], dashes: [], segs: [],
      points: [], labels: [], handles: [], kps: [], kpTip: null, title: null, _P: P, _boxes: [],
      __hover: ctx.hover && ctx.hover.curve, __armed: ctx.armed || null
    };
  }
  /* Общие настройки вида для E.panel: сетка, ручные границы, масштаб, имена осей. */
  function popt(ctx, o) {
    var r = { grid: ctx.grid, margin: ctx.margin, lock: ctx.lock, view: ctx.view, names: ctx.names };
    for (var k in o) r[k] = o[k];
    return r;
  }
  function curve(pn, P, id, f, color, o) {
    o = o || {};
    if (CO[id]) color = CO[id];
    if (LB[id] && o.label) o.label = LB[id];
    var bks = o.breaks || BRK;
    var d = E.pathOf(f, P, o.x0, o.x1, o.n || 240, bks);
    if (!d) return;
    // под курсором и «зажжённая» щелчком кривая чуть толще: видно, чьи точки горят
    var hl = !o.noHit && (pn.__hover === id || pn.__armed === id);
    pn.curves.push({ id: id, d: d, color: color, w: (o.w || 2.5) + (hl ? 1 : 0), dash: o.dash || 'none', op: o.op || 1 });
    if (!o.noHit) pn.hits.push({ id: id, d: d });
    // разрыв: закрашенная точка там, где значение есть, пустая там, где его нет
    if (o.ends) E.jumpsOf(f, bks, P).forEach(function (j) {
      [[j.yl, j.inc === 'l'], [j.yr, j.inc === 'r']].forEach(function (e) {
        if (e[0] === null || !(e[0] >= P.win.y0 && e[0] <= P.win.y1)) return;
        pn.points.push({ id: 'end:' + id, cx: E.r1(P.sx(j.x)), cy: E.r1(P.sy(e[0])), r: 3.4, fill: e[1] ? color : 'var(--canvas)', stroke: e[1] ? 'var(--canvas)' : color, sw: e[1] ? 1.4 : 1.8, x: j.x, y: e[0], key: false, name: '' });
      });
    });
    if (o.label) {
      var L = E.endLabel(f, P, o.x0, o.x1);
      if (L) addLabel(pn, label(L.x, L.y, o.label, color, L.anchor, o.labelSize || 15));
    }
  }
  /* Подписи не наезжают друг на друга: каждая занимает прямоугольник, следующая ищет свободное место. */
  function boxOf(lb) {
    var x1 = lb.anchor === 'end' ? lb.x - lb.w : lb.anchor === 'middle' ? lb.x - lb.w / 2 : lb.x;
    return { x1: x1 - 2, y1: lb.y - lb.size, x2: x1 + lb.w + 2, y2: lb.y + 4 };
  }
  function boxHits(pn, b) { return pn._boxes.some(function (o) { return b.x1 < o.x2 && b.x2 > o.x1 && b.y1 < o.y2 && b.y2 > o.y1; }); }
  function addLabel(pn, lb) { pn.labels.push(lb); pn._boxes.push(boxOf(lb)); }
  function label(x, y, text, color, anchor, size, bold) {
    size = Math.round((size || 15) * LS * 10) / 10;
    var parts = E.mathTokens(text).map(function (t) { return part(t, size); });
    var flat = [];
    parts.forEach(function (p) { flat = flat.concat(p); });
    // ширина на глаз: STIX около половины кегля на знак, индексы мельче
    var w = flat.reduce(function (a, q) { return a + String(q.t).length * (/font-size/.test(q.style) ? 0.38 : 0.52); }, 0) * (size || 15);
    return { x: E.r1(x), y: E.r1(y), anchor: anchor || 'start', color: color, size: size || 15, weight: bold ? 700 : 500, parts: flat, w: Math.round(w) };
  }
  function part(t, size) {
    if (t.k === 'sub' || t.k === 'sup') {
      return t.items.map(function (it) {
        return { t: it.t, style: 'font-style: ' + (it.k === 'v' ? 'italic' : 'normal') + '; font-size: ' + Math.round((size || 15) * 0.72) + 'px; baseline-shift: ' + (t.k === 'sub' ? 'sub' : 'super') };
      });
    }
    var it = t.k === 'v';
    var sp = t.k === 'o' ? ' ' : '';
    return [{ t: sp + t.t + sp, style: 'font-style: ' + (it ? 'italic' : 'normal') }];
  }
  function dashTo(pn, P, x, y, toX, toY) {
    var px = E.r1(P.sx(x)), py = E.r1(P.sy(y));
    if (toY !== false) pn.dashes.push({ x1: px, y1: py, x2: px, y2: E.r1(P.plot.y + P.plot.h) });
    if (toX !== false) pn.dashes.push({ x1: px, y1: py, x2: E.r1(P.plot.x), y2: py });
  }
  /* Выделенное значение на оси; в режиме «Сначала сам» вместо числа — обозначение. */
  function keyTickX(pn, P, v, text, ctx, sym) {
    if (!(v >= P.win.x0 && v <= P.win.x1)) return;
    var t = ctx.selfCheck ? sym : text;
    pn.keyTicks.push({ x: E.r1(P.sx(v)), y: E.r1(P.plot.y + P.plot.h + 17), anchor: 'middle', parts: label(0, 0, t, 'var(--ink)', 'middle', 12.5).parts });
  }
  function keyTickY(pn, P, v, text, ctx, sym) {
    if (!(v >= P.win.y0 && v <= P.win.y1)) return;
    var t = ctx.selfCheck ? sym : text;
    pn.keyTicks.push({ x: E.r1(P.plot.x - 7), y: E.r1(P.sy(v) + 4), anchor: 'end', parts: label(0, 0, t, 'var(--ink)', 'end', 12.5).parts });
  }
  function point(pn, P, id, x, y, color, o) {
    o = o || {};
    if (!(x >= P.win.x0 - 1e-9 && x <= P.win.x1 + 1e-9 && y >= P.win.y0 - 1e-9 && y <= P.win.y1 + 1e-9)) return;
    pn.points.push({ id: id, cx: E.r1(P.sx(x)), cy: E.r1(P.sy(y)), r: o.r || 4.5, fill: color, stroke: 'var(--canvas)', sw: 1.6, x: x, y: y, key: false, name: o.name || '' });
    if (o.label) {
      // справа сверху, если свободно; иначе по очереди: справа снизу, слева сверху, слева снизу, над точкой, под точкой
      var px = P.sx(x), py = P.sy(y), col = o.labelColor || 'var(--ink)';
      var cands = [[o.lx || 8, o.ly || -9, o.anchor || 'start'], [8, 19, 'start'], [-8, -9, 'end'], [-8, 19, 'end'], [0, -13, 'middle'], [0, 25, 'middle']];
      var pick = null, first = null;
      for (var i = 0; i < cands.length && !pick; i++) {
        var lb = label(px + cands[i][0], py + cands[i][1], o.label, col, cands[i][2], 15, true), b = boxOf(lb);
        if (!first) first = lb;
        if (b.x1 < P.plot.x - 2 || b.x2 > P.plot.x + P.plot.w + 26 || b.y1 < P.plot.y - 16 || b.y2 > P.plot.y + P.plot.h + 2) continue;
        if (!boxHits(pn, b)) pick = lb;
      }
      addLabel(pn, pick || first);
    }
  }
  function handle(pn, P, id, x, y, text, o) {
    o = o || {};
    var cx = E.r1(P.sx(x)), cy = E.r1(P.sy(y));
    var tw = Math.max(34, 8 + text.length * 7.4);
    var side = o.side || 'right';
    var px = side === 'right' ? cx + 12 : cx - 12 - tw;
    pn.handles.push({ id: id, cx: cx, cy: cy, r: o.r || 8, px: E.r1(px), py: E.r1(cy - 12), pw: E.r1(tw), ph: 24, tx: E.r1(px + tw / 2), ty: E.r1(cy + 4.5), text: text, cursor: o.cursor || 'grab', axis: o.axis || 'xy' });
    pn._boxes.push({ x1: Math.min(px, cx - 10), y1: cy - 14, x2: Math.max(px + tw, cx + 10), y2: cy + 14 });
  }
  /* Ключевые точки кривой: пересечения с осями и с соседями, изломы кусочной.
     Правило calc2 (решение владельца): по умолчанию на холсте их нет вовсе. Щелчок по
     кривой ЗАЖИГАЕТ её точки, без координат. Наведение на зажжённую точку показывает
     координаты и значок закрепки; точку в «Свои точки» выносит только щелчок по значку.
     Вид точки и подписи — один из трёх (ctx.kp):
       a — бусина цветом кривой, подпись без рамки;
       b — точка с мягким ореолом, тёмная капсула;
       c — ромб, пунктиры к осям и значения на самих осях. */
  function keyPoints(pn, P, curveId, pts, ctx) {
    if (ctx.armed !== curveId) return;
    var style = ctx.kp === 'a' || ctx.kp === 'c' ? ctx.kp : 'b';   // решение 04.10: вид Б; 'a' и 'c' остались для архивной доски
    var hot = ctx.hover ? ctx.hover.point : null, seen = [];
    pts.forEach(function (p, i) {
      if (!p || !isFinite(p[0]) || !isFinite(p[1])) return;
      var x = p[0], y = p[1], w = P.win;
      if (!(x >= w.x0 - 1e-9 && x <= w.x1 + 1e-9 && y >= w.y0 - 1e-9 && y <= w.y1 + 1e-9)) return;
      var cx = E.r1(P.sx(x)), cy = E.r1(P.sy(y));
      if (seen.some(function (q) { return Math.abs(q[0] - cx) < 1.5 && Math.abs(q[1] - cy) < 1.5; })) return;
      seen.push([cx, cy]);
      var id = 'kp:' + curveId + ':' + i, isHot = hot === id, color = p[2] || 'var(--ink)';
      var k = { id: id, cx: cx, cy: cy, x: x, y: y, color: color, hot: isHot, style: style };
      if (style === 'b') { k.r = isHot ? 4.8 : 4; k.gr = isHot ? 13 : 9.5; k.go = isHot ? 0.28 : 0.2; }
      else if (style === 'c') { var q = isHot ? 6.8 : 5.6; k.d = 'M' + cx + ',' + E.r1(cy - q) + ' L' + E.r1(cx + q) + ',' + cy + ' L' + cx + ',' + E.r1(cy + q) + ' L' + E.r1(cx - q) + ',' + cy + ' Z'; }
      else { k.r = isHot ? 5.8 : 4.4; }
      pn.kps.push(k);
      if (isHot) pn.kpTip = kpTip(style, pn, P, k, ctx);
    });
    dodgePills(pn, P);
  }
  /* Плашка ручки не должна закрывать зажжённую точку: если закрыла, переезжает на другую сторону ручки. */
  function dodgePills(pn, P) {
    function covers(hd, px) { return pn.kps.some(function (k) { return k.cx > px - 7 && k.cx < px + hd.pw + 7 && k.cy > hd.py - 7 && k.cy < hd.py + hd.ph + 7; }); }
    pn.handles.forEach(function (hd) {
      if (!covers(hd, hd.px)) return;
      var alt = hd.px > hd.cx ? hd.cx - 12 - hd.pw : hd.cx + 12;
      if (alt < P.plot.x - 4 || alt + hd.pw > P.plot.x + P.plot.w + 24 || covers(hd, alt)) return;
      hd.px = E.r1(alt); hd.tx = E.r1(alt + hd.pw / 2);
    });
  }
  /* Точки всех нарисованных линий панели — чтобы подпись точки вставала туда, где линий нет. */
  function linePoints(pn) {
    var out = [];
    pn.curves.forEach(function (c) {
      var n = String(c.d).match(/-?\d+(\.\d+)?/g);
      if (n) for (var i = 0; i + 1 < n.length; i += 2) out.push([+n[i], +n[i + 1]]);
    });
    pn.segs.forEach(function (g) {
      var len = Math.hypot(g.x2 - g.x1, g.y2 - g.y1), k = Math.max(1, Math.round(len / 4));
      for (var i = 0; i <= k; i++) out.push([g.x1 + (g.x2 - g.x1) * i / k, g.y1 + (g.y2 - g.y1) * i / k]);
    });
    return out;
  }
  /* Место подписи размером w×h у точки (cx; cy): восемь положений, выбирается то, где меньше всего
     линий и нет чужих подписей. При равных условиях выигрывает «справа сверху». */
  function tipPlace(pn, P, cx, cy, w, h, gap) {
    var plot = P.plot, pts = pn._lpts || (pn._lpts = linePoints(pn));
    var cand = [
      ['ne', cx + gap, cy - gap - h], ['e', cx + gap + 8, cy - h / 2], ['se', cx + gap, cy + gap],
      ['nw', cx - gap - w, cy - gap - h], ['w', cx - gap - 8 - w, cy - h / 2], ['sw', cx - gap - w, cy + gap],
      ['n', cx - w / 2, cy - gap - 10 - h], ['s', cx - w / 2, cy + gap + 10]
    ];
    var best = null, bestScore = Infinity;
    cand.forEach(function (c, i) {
      var b = { x1: c[1] - 3, y1: c[2] - 3, x2: c[1] + w + 3, y2: c[2] + h + 3 };
      var score = i * 0.4;
      if (b.x1 < plot.x - 4 || b.x2 > plot.x + plot.w + 30 || b.y1 < plot.y - 26 || b.y2 > plot.y + plot.h + 2) score += 5000;
      pn._boxes.forEach(function (o) { if (b.x1 < o.x2 && b.x2 > o.x1 && b.y1 < o.y2 && b.y2 > o.y1) score += 400; });
      for (var k = 0; k < pts.length; k++) { var q = pts[k]; if (q[0] > b.x1 && q[0] < b.x2 && q[1] > b.y1 && q[1] < b.y2) score += 1; }
      if (score < bestScore) { bestScore = score; best = { side: c[0], x: c[1], y: c[2] }; }
    });
    return best;
  }
  E.tipPlace = tipPlace;
  /* Геометрия подписи зажжённой точки под курсором. Значок закрепки 16 px стоит с той стороны
     подписи, что ближе к точке: до него короткий путь мышью. */
  function kpTip(style, pn, P, k, ctx) {
    var sc = !!ctx.selfCheck, cx = k.cx, cy = k.cy, IC = 16;
    var t = sc ? '(?; ?)' : '(' + num(k.x) + '; ' + num(k.y) + ')';
    var tip = { id: k.id, style: style, t: t, color: k.color, x: k.x, y: k.y, cx: cx, cy: cy };
    function keepBox(x, y, w, h) {
      var x1 = Math.min(x, cx - 13), y1 = Math.min(y, cy - 13), x2 = Math.max(x + w, cx + 13), y2 = Math.max(y + h, cy + 13);
      return { x: E.r1(x1 - 3), y: E.r1(y1 - 3), w: E.r1(x2 - x1 + 6), h: E.r1(y2 - y1 + 6) };
    }
    if (style === 'b') {
      /* ctx.noPin — касание (телефон): закрепки нет, капсула короче, поля по 12 с обеих сторон. */
      var noPin = !!ctx.noPin;
      var tw = Math.round(t.length * 7) + 2, w = noPin ? 12 + tw + 12 : 12 + tw + 9 + 28, h = 28;
      var pb = tipPlace(pn, P, cx, cy, w, h, 10), px = pb.x, py = pb.y;
      tip.px = E.r1(px); tip.py = E.r1(py); tip.pw = w; tip.ph = h;
      tip.tx = E.r1(px + 12); tip.ty = E.r1(py + h / 2 + 4.5);
      tip.noPin = noPin;
      if (!noPin) { tip.sx = E.r1(px + 12 + tw + 9); tip.ix = E.r1(px + 12 + tw + 9 + 7); tip.iy = E.r1(py + 7); tip.is = 14; }
      tip.keep = keepBox(px, py, w, h);
      return tip;
    }
    if (style === 'c') {
      var axY = P.axis.x.y1, axX = P.axis.y.x1;
      tip.proj = [];
      if (Math.abs(cy - axY) > 2) tip.proj.push({ x1: cx, y1: cy, x2: cx, y2: axY });
      if (Math.abs(cx - axX) > 2) tip.proj.push({ x1: cx, y1: cy, x2: axX, y2: cy });
      tip.axis = [
        { x: cx, y: E.r1(axY + 17), anchor: 'middle', t: sc ? '?' : num(k.x) },
        { x: E.r1(axX - 7), y: E.r1(cy + 4), anchor: 'end', t: sc ? '?' : num(k.y) }
      ];
      var pc = tipPlace(pn, P, cx, cy, IC, IC, 8);
      tip.ix = E.r1(pc.x); tip.iy = E.r1(pc.y); tip.is = IC;
      tip.keep = keepBox(pc.x, pc.y, IC, IC);
      return tip;
    }
    var tw2 = Math.round(t.length * 7.6) + 2, w2 = IC + 6 + tw2, h2 = 18;
    var pa = tipPlace(pn, P, cx, cy, w2, h2, 8);
    var leftSide = pa.side === 'nw' || pa.side === 'w' || pa.side === 'sw';
    tip.anchor = leftSide ? 'end' : 'start';
    tip.ix = E.r1(leftSide ? pa.x + w2 - IC : pa.x); tip.iy = E.r1(pa.y + 1); tip.is = IC;
    tip.tx = E.r1(leftSide ? pa.x + tw2 : pa.x + IC + 6); tip.ty = E.r1(pa.y + 14.5);
    tip.keep = keepBox(pa.x, pa.y, w2, h2);
    return tip;
  }
  /* Легенда — строкой над полем графика, справа: в поле она закрывала бы концы кривых с подписями. */
  function legend(pn, P, items) {
    if (!items.length) return null;
    var widths = items.map(function (i) { return 12 + 6 + i.t.length * 7.6 + 16; });
    var total = widths.reduce(function (a, b) { return a + b; }, 0) - 16;
    var x = P.plot.x + P.plot.w - total, y = P.plot.y - 27, cx = x;
    var out = items.map(function (it, i) {
      var o = { fill: it.fill, t: it.t, sx: E.r1(cx), sy: E.r1(y + 3), tx: E.r1(cx + 18), ty: E.r1(y + 14) };
      cx += widths[i];
      return o;
    });
    return { x: E.r1(x - 6), y: E.r1(y), w: E.r1(total + 12), h: 20, items: out };
  }

  /* Итоговая функция после сдвига (tf.add) или поворота (tf.mul): одной строкой, а у кусочной
     исходной — по участкам с теми же условиями. Запись Q(P) идёт уже в каноне P от Q. */
  function ffOf(res, fn, exprText, win, tf) {
    function moved(g, lo, hi, text) {
      var d = (hi - lo) * 1e-6, L = E.linearOf(g, lo + d, hi - d);
      if (!L && text === null) return null;
      if (tf.mul !== undefined) return L ? E.linearText(L.a * tf.mul, L.b * tf.mul) : String(Math.round(tf.mul * 1e4) / 1e4) + '*(' + text + ')';
      return L ? E.linearText(L.a + tf.add, L.b) : '(' + text + ')' + (tf.add < 0 ? ' - ' : ' + ') + num(Math.abs(tf.add));
    }
    var raw = { toks: [{ k: 'raw', t: 'обратная функция, считаем численно' }], copy: '', prefix: 'P =' };
    var rows = res.form === 'QP' ? res.canonRows : res.rows;
    if (rows && rows.length) {
      var out = rows.map(function (rw) {
        var has = function (v) { return v !== null && v !== undefined; };
        var lo = has(rw.from) ? rw.from : Math.max(0, win.x0), hi = has(rw.to) ? rw.to : Math.max(win.x1, lo + 1);
        var text = moved(res.form === 'QP' ? fn : (rw.f || fn), lo, hi, rw.ast ? E.astText(rw.ast) : null);
        if (text === null) return null;
        var cond = E.condText(rw, 'Q');
        return { toks: E.typeset(text), cond: E.condToks(rw, 'Q'), rest: !!rw.rest, copy: E.prettyExpr(text) + (cond ? ', если ' + cond : (rw.rest ? ', иначе' : '')) };
      });
      if (out.some(function (r) { return !r; })) return raw;
      return { rows: out, toks: [], copy: 'P = { ' + out.map(function (r) { return r.copy; }).join('; ') + ' }', prefix: 'P =' };
    }
    if (res.form === 'QP' && res.rows) return raw;
    var t = moved(fn, 0, win.x1, res.form === 'QP' ? null : exprText);
    if (t === null) return raw;
    return { toks: E.typeset(t), copy: 'P = ' + E.prettyExpr(t), prefix: 'P =' };
  }

  /* ── ответ: главные числа и таблица ────────────────────────────────────── */
  function hero(id, label, sym, value, was, dec) {
    var v = typeof value === 'number' ? num(value, dec) : value;
    var w = was === undefined || was === null ? null : (typeof was === 'number' ? num(was, dec) : was);
    var delta = (typeof value === 'number' && typeof was === 'number') ? fmtD(value - was, dec) : '';
    return { id: id, label: label, sym: m(sym), value: v, was: w, delta: delta, hasWas: w !== null };
  }
  function row(id, label, sym, value, was, dec, neg) {
    var r = hero(id, label, sym, value, was, dec);
    r.neg = !!neg;
    return r;
  }

  /* ── тексты разбора ─────────────────────────────────────────────────────── */
  var EX = {
    sd: [
      ['Что показывают эти две кривые?', 'Спрос $D$ говорит, сколько покупатели готовы взять при каждой цене, предложение $S$ говорит, сколько готовы отдать продавцы. Спрос убывает: чем дороже, тем меньше берут. Предложение растёт: чем дороже, тем выгоднее производить.'],
      ['Почему равновесие именно в точке пересечения?', 'Только там намерения сторон совпадают. Выше равновесной цены продавцы предлагают больше, чем покупатели готовы взять, излишек давит цену вниз. Ниже наоборот: дефицит толкает цену вверх. Движение прекращается ровно при $Q_d = Q_s$.'],
      ['Что означают закрашенные области?', 'Излишек покупателя $CS$ это разница между тем, сколько человек готов был заплатить (высота спроса), и тем, сколько заплатил (цена). Излишек продавца $PS$ считается между ценой и издержками (высотой предложения). Их сумма это общий выигрыш рынка.']
    ],
    sdC: 'Свободное равновесие максимизирует сумму излишков: любое другое количество отнимает у одной стороны больше, чем добавляет другой.',
    taxes: [
      ['Что делает налог на товар?', 'Он вставляет клин между ценой, которую платит покупатель, и ценой, которую получает продавец: $P_b - P_s$ равно ставке. Потоварный налог берут фиксированной суммой с единицы, поэтому предложение сдвигается вверх параллельно. НДС и акциз берут долей от цены, поэтому предложение поворачивается: $S_{после} = (1 + \\tau) \\cdot S$.'],
      ['Кто на самом деле платит налог?', 'Не тот, с кого его берут по закону. Переключите «Налог платит» с продавца на покупателя: объём, обе цены и сбор бюджета не изменятся. Бремя делится по наклонам: чем круче кривая, тем большую часть налога несёт эта сторона.'],
      ['Откуда берутся потери общества?', 'Налог сокращает объём с $Q_0$ до $Q_1$. Сделки между этими объёмами были выгодны обеим сторонам, но после налога перестали окупаться. Их выигрыш не достался никому: ни сторонам, ни бюджету. Это и есть треугольник $DWL$.'],
      ['А субсидия?', 'Тот же механизм с обратным знаком: предложение опускается, объём растёт выше равновесного, расход бюджета больше прироста излишков, и $DWL$ снова положителен.']
    ],
    taxesC: 'Сбор бюджета меньше, чем потеряли покупатель и продавец вместе: разница и есть безвозвратная потеря. Чем эластичнее рынок, тем она больше при той же ставке.',
    ceil: [
      ['Что такое потолок и пол цены?', 'Потолок это запрет продавать дороже некоторого уровня, а пол запрет продавать дешевле. Работает только та граница, которая мешает рынку: потолок ниже равновесия и пол выше него.'],
      ['Почему возникает дефицит или излишек?', 'При потолке ниже равновесия покупатели хотят взять больше, чем продавцы готовы отдать по этой цене: разница и есть дефицит. При поле выше равновесия наоборот образуется непроданный излишек.'],
      ['Кто выигрывает и кто теряет?', 'Часть излишка переходит от одной стороны к другой, но обмен сокращается, и часть выигрыша исчезает совсем. Тем, кому товара не хватило, регулирование не помогло ничем.']
    ],
    ceilC: 'Ограничение цены перераспределяет выигрыш и одновременно уменьшает его общий размер. Дефицит это не «жадность продавцов», а прямое следствие цены ниже равновесной.',
    mono: [
      ['Чем монополист отличается от конкурентной фирмы?', 'Он видит перед собой весь рыночный спрос, поэтому не может продать больше, не снизив цену. Из-за этого предельная выручка $MR$ идёт ниже спроса.'],
      ['Почему оптимум там, где $MR = MC$?', 'Пока последняя единица приносит больше, чем стоит, её стоит выпустить. Как только приносит меньше, не стоит. Цену монополист берёт с кривой спроса над этой точкой, а не с $MR$.'],
      ['Откуда потери общества?', 'Монополист останавливается раньше, чем цена сравнялась бы с издержками. Сделки между монопольным и конкурентным объёмом были бы выгодны обеим сторонам, но не состоятся.'],
      ['Откуда берётся $MR$ ниже спроса?', 'Продавая лишнюю единицу, монополист выигрывает её цену, но теряет скидку на всех прежних. Для линейного спроса $P = a - bQ$ выручка равна $aQ - bQ^2$, а её прирост $a - 2bQ$: та же точка на оси цен, наклон вдвое круче.']
    ],
    monoC: 'Вред монополии не в самой высокой цене (это перераспределение), а в недопроизводстве: именно оно уменьшает общий выигрыш.',
    costs: [
      ['Откуда берутся все эти кривые?', 'Из одной функции общих издержек $TC(Q)$. Средние $ATC = TC / Q$, переменные средние $AVC = VC / Q$, предельные $MC$ это прирост издержек на последней единице.'],
      ['Почему $MC$ пересекает $ATC$ ровно в её минимуме?', 'Пока последняя единица дешевле среднего, среднее падает; как только дороже, начинает расти. Значит, среднее перестаёт падать ровно тогда, когда предельные издержки сравнялись с ним.'],
      ['Что решает фирма по этим кривым?', 'Сколько выпускать: при совершенной конкуренции оптимум там, где $P = MC$ на возрастающей ветке. Останавливаться ли: если цена ниже минимума $AVC$, выгоднее не работать вовсе.']
    ],
    costsC: 'Форма кривых не произвольна: она целиком следует из $TC(Q)$, и точки их пересечения имеют смысл, а не совпадение.',
    tangent: [
      ['Что такое производная в точке?', 'Наклон касательной: насколько быстро растёт функция возле $x_0$. Касательная – прямая, которая в этой точке идёт вровень с кривой.'],
      ['Зачем секущая?', 'Секущая соединяет две точки кривой. Когда шаг $\\Delta x$ уменьшается, её наклон $\\Delta y / \\Delta x$ приближается к производной. Так производную и определяют.'],
      ['Как связаны два графика?', 'Нижний график в каждой точке показывает наклон верхнего. Там, где верхний растёт, нижний выше нуля; в вершине верхнего нижний пересекает ось.']
    ],
    tangentC: 'Производная – это функция наклонов: по её знаку видно, где исходная функция растёт и убывает, а по нулям – где у неё вершины.'
  };
  function explain(list, conclusion) {
    return {
      items: (list || []).map(function (qa, i) { return { id: 'ex' + i, q: E.richText(qa[0]), a: E.richText(qa[1]) }; }),
      conclusion: conclusion ? E.richText(conclusion) : null
    };
  }

  /* ════════════════════════════════════════════════════════════════════════
     ЖИВЫЕ МОДЕЛИ
     ════════════════════════════════════════════════════════════════════════ */
  var LIVE = {};

  /* ── 1. Спрос и предложение ───────────────────────────────────────────── */
  LIVE.sd = {
    init: function () {
      return { fns: { D: { expr: '100 - Q', shift: 0, visible: true }, S: { expr: 'Q', shift: 0, visible: true } }, letters: {}, show: { cs: true, ps: true } };
    },
    view: function (ms, ctx) { return marketView(ms, ctx, 'sd'); }
  };

  /* ── 2. Налоги и субсидии ──────────────────────────────────────────────── */
  LIVE.taxes = {
    init: function () {
      return {
        fns: { D: { expr: '100 - Q', shift: 0, visible: true }, S: { expr: 'Q', shift: 0, visible: true } }, letters: {},
        iv: { instr: 'tax', kind: 'unit', side: 'seller', rate: 20, pct: 20, ghost: false },
        show: { cs: true, ps: true, tx: true, dwl: true }
      };
    },
    view: function (ms, ctx) { return marketView(ms, ctx, 'taxes'); }
  };

  /* ── 3. Пол и потолок цены ─────────────────────────────────────────────── */
  LIVE.ceil = {
    init: function () {
      return {
        fns: { D: { expr: '100 - Q', shift: 0, visible: true }, S: { expr: 'Q', shift: 0, visible: true } }, letters: {},
        iv: { instr: 'ceil', price: 30, ghost: false },
        show: { cs: true, ps: true, dwl: true }
      };
    },
    view: function (ms, ctx) { return marketView(ms, ctx, 'ceil'); }
  };

  /* Налоговые формы: как вмешательство меняет цену, которую требуют продавцы. */
  function taxWedge(iv) {
    var r = iv.kind === 'unit' ? iv.rate : iv.pct / 100;
    var tax = iv.instr === 'tax';
    return {
      unit: iv.kind === 'unit', tax: tax, r: r,
      // цена покупателя, при которой продавец соглашается дать Q (по кривой S)
      eff: function (S) {
        if (iv.kind === 'unit') return function (q) { return S(q) + (tax ? r : -r); };
        if (tax && iv.kind === 'vat') return function (q) { return S(q) * (1 + r); };
        if (tax && iv.kind === 'exc') return function (q) { return S(q) / Math.max(1e-6, 1 - r); };
        if (!tax && iv.kind === 'vat') return function (q) { return S(q) * (1 - r); };
        return function (q) { return S(q) / (1 + r); };
      }
    };
  }

  function marketView(ms, ctx, key) {
    var isTax = key === 'taxes', isCeil = key === 'ceil';
    var dres = fnOf(ms, 'D'), sres = fnOf(ms, 'S');
    addBreaks(dres, sres);
    var defs = [
      { id: 'D', sym: 'D', name: 'Спрос', color: C.d },
      { id: 'S', sym: 'S', name: 'Предложение', color: C.s }
    ];
    var shiftOK = !isTax;
    var left = [], answer, chart = { panels: [], legend: null, note: null };
    var fnsSection = {
      kind: 'fns', title: 'Функции', addLabel: 'Добавить функцию',
      rows: [fnRow(ms, defs[0], dres, { shift: shiftOK }), fnRow(ms, defs[1], sres, { shift: shiftOK })]
    };
    left.push(fnsSection);

    var ivItems = null;
    if (isTax) {
      var iv = ms.iv, tax = iv.instr === 'tax';
      ivItems = [seg('iv.instr', '', [['tax', 'Налог'], ['sub', 'Субсидия']], iv.instr)];
      ivItems.push(seg('iv.kind', tax ? 'Вид налога' : 'Вид субсидии', tax
        ? [['unit', 'Потоварный'], ['vat', 'НДС'], ['exc', 'Акциз']]
        : [['unit', 'Потоварная'], ['vat', '% от цены продавца'], ['exc', '% от цены покупателя']], iv.kind));
      if (iv.kind === 'unit') ivItems.push(seg('iv.side', tax ? 'Налог платит' : 'Субсидию получает', [['seller', 'Продавец'], ['buyer', 'Покупатель']], iv.side));
      if (iv.kind === 'unit') ivItems.push(slider('iv.rate', tax ? 'Ставка налога' : 'Размер субсидии', tax ? 't' : 's', 0, 150, 1, iv.rate, '', 'С единицы товара'));
      else ivItems.push(slider('iv.pct', tax ? (iv.kind === 'vat' ? 'Ставка НДС' : 'Ставка акциза') : 'Доля субсидии', '\\tau', 0, iv.kind === 'exc' && tax ? 90 : 100, 1, iv.pct, '%', iv.kind === 'vat' ? 'Доля от цены продавца' : 'Доля от цены покупателя'));
      ivItems.push(toggle('iv.ghost', 'Показать исходное состояние на графике', iv.ghost, C.ghost));
    }
    if (isCeil) {
      var ivc = ms.iv;
      ivItems = [seg('iv.instr', '', [['ceil', 'Потолок цены'], ['floor', 'Пол цены']], ivc.instr)];
      ivItems.push(slider('iv.price', ivc.instr === 'ceil' ? 'Потолок' : 'Пол', ivc.instr === 'ceil' ? 'P_{c}' : 'P_{f}', 0, 100, 1, ivc.price, '', 'Линию цены можно тянуть на графике'));
      ivItems.push(toggle('iv.ghost', 'Показать исходное состояние на графике', ivc.ghost, C.ghost));
    }
    if (ivItems) left.push({ kind: 'iv', title: 'Вмешательство государства', items: ivItems });

    var showItems = [toggle('show.cs', 'Излишек покупателя', ms.show.cs, 'var(--fill-c-s)', 'CS'), toggle('show.ps', 'Излишек продавца', ms.show.ps, 'var(--fill-p-s)', 'PS')];
    if (isTax) showItems.push(toggle('show.tx', 'Бюджет', ms.show.tx, 'var(--fill-t-x)', ''));
    if (isTax || isCeil) showItems.push(toggle('show.dwl', 'Потери общества', ms.show.dwl, 'var(--fill-d-w-l)', 'DWL'));
    left.push({ kind: 'show', title: 'Показать на графике', items: showItems });
    left.push({ kind: 'tools', title: 'Свои точки и площади' });

    // ── расчёт ──
    if (!dres.ok || !sres.ok) {
      answer = { status: { tone: 'error', text: 'Проверьте запись функции: ' + (!dres.ok ? dres.error : sres.error) + '. График перестроится, как только запись станет понятной.' }, hero: [], tables: [], burden: null, ff: null, explain: explain([], null) };
      return { left: left, chart: chart, answer: answer, primary: null };
    }
    var D = dres.f, S = sres.f, Sp = posPart(S);
    var dVis = ms.fns.D.visible !== false, sVis = ms.fns.S.visible !== false;
    // скрытая кривая для модели отсутствует (ADR 0085 calc2): без неё нет равновесия и ответа
    var hiddenMsg = dVis && sVis ? null : ((!dVis && !sVis) ? 'Спрос и предложение скрыты' : !dVis ? 'Спрос скрыт' : 'Предложение скрыто') + ': скрытой кривой для модели нет, поэтому нет ни равновесия, ни ответа. Верните кривую глазом на её карточке.';
    var span = 5000;
    var e0 = hiddenMsg ? null : equilibrium(D, S, span);
    var win = marketWindow([D, S], e0 ? [e0.q] : [], e0 ? [e0.p] : []);
    // окно не сжимается при сдвиге: база без сдвигов
    var bw = marketWindow([dres.base, sres.base]);
    win.x1 = Math.max(win.x1, bw.x1); win.y1 = Math.max(win.y1, bw.y1);

    var P = E.panel({ x: 0, y: 0, w: ctx.cw, h: ctx.ch }, win, popt(ctx, { id: 'main', xName: 'Q', yName: 'P' }));
    var pn = base(P, ctx);
    pn.__hover = ctx.hover && ctx.hover.curve;

    var cs0 = null, ps0 = null, sw0 = null;
    if (e0) {
      cs0 = I(function (q) { return D(q) - e0.p; }, 0, e0.q);
      ps0 = I(function (q) { return e0.p - Sp(q); }, 0, e0.q);
      sw0 = cs0 + ps0;
    }
    var legendItems = [];
    var heroItems = [], tables = [], burden = null, ff = null, status = null, ex;

    if (key === 'sd') {
      if (e0) {
        if (ms.show.cs) { pn.fills.push({ pts: E.polyBetween(D, function () { return e0.p; }, 0, e0.q, P), fill: 'var(--fill-c-s)' }); legendItems.push({ fill: 'var(--fill-c-s)', t: 'CS' }); }
        if (ms.show.ps) { pn.fills.push({ pts: E.polyBetween(function () { return e0.p; }, Sp, 0, e0.q, P), fill: 'var(--fill-p-s)' }); legendItems.push({ fill: 'var(--fill-p-s)', t: 'PS' }); }
        dashTo(pn, P, e0.q, e0.p);
        keyTickX(pn, P, e0.q, num(e0.q), ctx, 'Q^*');
        keyTickY(pn, P, e0.p, num(e0.p), ctx, 'P^*');
        heroItems = [hero('Q', 'Равновесный объём', 'Q^*', e0.q), hero('P', 'Равновесная цена', 'P^*', e0.p)];
        tables.push({ id: 'surplus', title: 'Излишки', cols: null, rows: [row('cs', 'Излишек покупателя', 'CS', cs0), row('ps', 'Излишек продавца', 'PS', ps0), row('sw', 'Общий выигрыш', 'SW', sw0)] });
      } else {
        status = { tone: 'warn', text: 'Равновесия нет: в первой четверти кривые не пересекаются. Это честный ответ: рынка при таких функциях нет.' };
      }
      ex = explain(EX.sd, EX.sdC);
    }

    if (isTax && e0) {
      var ivt = ms.iv, W = taxWedge(ivt);
      var Seff = W.eff(S);
      var q1 = E.firstRoot(function (q) { return D(q) - Seff(q); }, 0, span, 3000);
      if (q1 === null || D(q1) < 0) {
        status = { tone: 'warn', text: 'При такой ставке рынка нет: покупатели не готовы платить цену, которую требуют продавцы.' };
        q1 = null;
      }
      var buyerSide = W.unit && ivt.side === 'buyer';
      // нарисованная кривая после вмешательства
      var shifted, shiftedLabel, shiftedColor;
      if (buyerSide) {
        shifted = function (q) { return D(q) + (W.tax ? -W.r : W.r); };
        shiftedLabel = W.tax ? 'D - t' : 'D + s'; shiftedColor = C.d;
      } else {
        shifted = Seff; shiftedColor = C.s;
        shiftedLabel = W.unit ? (W.tax ? 'S + t' : 'S - s') : (W.tax ? (ivt.kind === 'vat' ? 'S(1+\\tau)' : 'S/(1-\\tau)') : (ivt.kind === 'vat' ? 'S(1-\\tau)' : 'S/(1+\\tau)'));
      }
      if (q1 !== null) {
        var pb = D(q1), ps = S(q1);
        var money = Math.abs(pb - ps) * q1;
        var cs1 = I(function (q) { return D(q) - pb; }, 0, q1);
        var ps1 = I(function (q) { return ps - Sp(q); }, 0, q1);
        var sw1 = W.tax ? cs1 + ps1 + money : cs1 + ps1 - money;
        var dwl = Math.max(0, sw0 - sw1);
        // заливки
        if (ms.show.cs) pn.fills.push({ pts: E.polyBetween(D, function () { return pb; }, 0, q1, P), fill: 'var(--fill-c-s)' });
        if (ms.show.ps) pn.fills.push({ pts: E.polyBetween(function () { return ps; }, Sp, 0, q1, P), fill: 'var(--fill-p-s)' });
        if (ms.show.tx) pn.fills.push({ pts: E.rectPoly(0, q1, Math.min(pb, ps), Math.max(pb, ps), P), fill: 'var(--fill-t-x)' });
        if (ms.show.dwl) {
          if (W.tax) pn.fills.push({ pts: E.polyBetween(D, S, q1, e0.q, P), fill: 'var(--fill-d-w-l)' });
          else pn.fills.push({ pts: E.polyBetween(S, D, e0.q, q1, P), fill: 'var(--fill-d-w-l)' });
        }
        if (ms.show.cs) legendItems.push({ fill: 'var(--fill-c-s)', t: 'CS' });
        if (ms.show.ps) legendItems.push({ fill: 'var(--fill-p-s)', t: 'PS' });
        if (ms.show.tx) legendItems.push({ fill: 'var(--fill-t-x)', t: W.tax ? 'Сбор' : 'Расход' });
        if (ms.show.dwl) legendItems.push({ fill: 'var(--fill-d-w-l)', t: 'DWL' });
        // клин и его ручка
        pn.segs.push({ x1: E.r1(P.sx(q1)), y1: E.r1(P.sy(pb)), x2: E.r1(P.sx(q1)), y2: E.r1(P.sy(ps)), color: 'var(--ink)', w: 2.5, dash: 'none' });
        dashTo(pn, P, q1, Math.max(pb, ps));
        pn.dashes.push({ x1: E.r1(P.plot.x), y1: E.r1(P.sy(Math.min(pb, ps))), x2: E.r1(P.sx(q1)), y2: E.r1(P.sy(Math.min(pb, ps))) });
        keyTickX(pn, P, q1, num(q1), ctx, 'Q_1');
        keyTickY(pn, P, pb, num(pb) + '_b', ctx, 'P_b');
        keyTickY(pn, P, ps, num(ps) + '_s', ctx, 'P_s');
        var rateText = W.unit ? (W.tax ? 't' : 's') + ' = ' + num(W.r) : 'τ = ' + num(ivt.pct) + ' %';
        handle(pn, P, 'wedge', q1, (pb + ps) / 2, rateText, { axis: 'x', cursor: 'ew-resize' });
        point(pn, P, 'pb', q1, pb, C.d, { r: 3.6 });
        point(pn, P, 'ps', q1, ps, C.s, { r: 3.6 });
        if (ivt.ghost) {
          dashTo(pn, P, e0.q, e0.p);
          point(pn, P, 'e0', e0.q, e0.p, C.ghost, { label: 'E_0', labelColor: 'var(--ink-soft)' });
        }
        // ответ
        heroItems = [
          hero('Q', 'Объём торговли', 'Q_1', q1, e0.q),
          hero('Pb', 'Цена покупателя', 'P_b', pb, e0.p),
          hero('Ps', 'Цена продавца', 'P_s', ps, e0.p),
          hero('DWL', 'Потери общества', 'DWL', dwl, 0)
        ];
        tables.push({
          id: 'welfare', title: 'Благосостояние', cols: ['Было', 'Стало', 'Δ'],
          rows: [
            row('cs', 'Излишек покупателя', 'CS', cs1, cs0),
            row('ps', 'Излишек продавца', 'PS', ps1, ps0),
            row('budget', W.tax ? 'Сбор бюджета' : 'Расход бюджета', '', money, 0),
            row('dwl', 'Потери общества', 'DWL', dwl, 0),
            row('sw', 'Общий выигрыш', 'SW', sw1, sw0)
          ]
        });
        var bB = W.tax ? pb - e0.p : e0.p - pb, bS = W.tax ? e0.p - ps : ps - e0.p;
        var tot = bB + bS;
        burden = {
          title: W.tax ? 'Кто несёт налог' : 'Кому достаётся субсидия',
          buyer: num(bB), seller: num(bS),
          buyerPct: tot > 0 ? Math.round(bB / tot * 100) : 50, sellerPct: tot > 0 ? 100 - Math.round(bB / tot * 100) : 50,
          note: W.unit ? 'Не зависит от того, кто платит по закону: переключите сторону, и числа не изменятся.' : 'При налоге долей от цены клин растёт вместе с ценой.'
        };
        // итоговая функция
        var ffSym, ffName, tf;
        if (buyerSide) { ffSym = 'D′'; ffName = W.tax ? 'Спрос после налога' : 'Спрос после субсидии'; tf = { add: W.tax ? -W.r : W.r }; }
        else {
          ffSym = 'S′'; ffName = W.tax ? 'Предложение после налога' : 'Предложение после субсидии';
          tf = W.unit ? { add: W.tax ? W.r : -W.r } : { mul: W.tax ? (ivt.kind === 'vat' ? 1 + W.r : 1 / (1 - W.r)) : (ivt.kind === 'vat' ? 1 - W.r : 1 / (1 + W.r)) };
        }
        ff = ffOf(buyerSide ? dres : sres, buyerSide ? D : S, E.splitEq((buyerSide ? ms.fns.D : ms.fns.S).expr).rhs.trim(), win, tf);
        ff.name = ffName; ff.sym = m(ffSym);
      }
      curve(pn, P, 'shifted', shifted, shiftedColor, { dash: '8 5', label: shiftedLabel, w: 2.2, noHit: true });
      ex = explain(EX.taxes, EX.taxesC);
    } else if (isTax) {
      status = status || { tone: 'warn', text: 'Равновесия без вмешательства нет, поэтому сравнивать не с чем.' };
      ex = explain(EX.taxes, EX.taxesC);
    }

    if (isCeil && e0) {
      var ivc2 = ms.iv, isC = ivc2.instr === 'ceil', pr = ivc2.price;
      var qd = E.solveFor(D, pr, 0, span); if (qd === null) qd = D(0) < pr ? 0 : win.x1;
      var qs = E.solveFor(S, pr, 0, span); if (qs === null) qs = S(0) > pr ? 0 : win.x1;
      var binding = isC ? pr < e0.p : pr > e0.p;
      var qt = binding ? Math.min(qd, qs) : e0.q;
      var pt = binding ? pr : e0.p;
      var cs2 = I(function (q) { return D(q) - pt; }, 0, qt);
      var ps2 = I(function (q) { return pt - Sp(q); }, 0, qt);
      var dwl2 = Math.max(0, sw0 - cs2 - ps2);
      if (ms.show.cs) { pn.fills.push({ pts: E.polyBetween(D, function () { return pt; }, 0, qt, P), fill: 'var(--fill-c-s)' }); legendItems.push({ fill: 'var(--fill-c-s)', t: 'CS' }); }
      if (ms.show.ps) { pn.fills.push({ pts: E.polyBetween(function () { return pt; }, Sp, 0, qt, P), fill: 'var(--fill-p-s)' }); legendItems.push({ fill: 'var(--fill-p-s)', t: 'PS' }); }
      if (ms.show.dwl && binding && dwl2 > 0.01) { pn.fills.push({ pts: E.polyBetween(D, S, qt, e0.q, P), fill: 'var(--fill-d-w-l)' }); legendItems.push({ fill: 'var(--fill-d-w-l)', t: 'DWL' }); }
      // линия цены
      pn.segs.push({ x1: E.r1(P.plot.x), y1: E.r1(P.sy(pr)), x2: E.r1(P.plot.x + P.plot.w), y2: E.r1(P.sy(pr)), color: C.reg, w: 2.5, dash: 'none' });
      handle(pn, P, 'price', win.x1 * 0.86, pr, (isC ? 'Pc' : 'Pf') + ' = ' + num(pr), { axis: 'y', cursor: 'ns-resize', side: 'left' });
      if (binding) {
        point(pn, P, 'qs', qs, pr, C.s, { r: 3.6 });
        point(pn, P, 'qd', qd, pr, C.d, { r: 3.6 });
        var gapY = P.sy(pr) + (isC ? 16 : -12);
        pn.segs.push({ x1: E.r1(P.sx(Math.min(qd, qs))), y1: E.r1(gapY), x2: E.r1(P.sx(Math.max(qd, qs))), y2: E.r1(gapY), color: 'var(--ink)', w: 1.5, dash: 'none' });
        pn.labels.push(label((P.sx(qd) + P.sx(qs)) / 2, gapY + (isC ? 16 : -6), (isC ? 'дефицит ' : 'избыток ') + (ctx.selfCheck ? '?' : num(Math.abs(qd - qs))), 'var(--ink)', 'middle', 13));
        dashTo(pn, P, qt, pr, false, true);
        keyTickX(pn, P, qs, num(qs) + (isC ? '' : ''), ctx, 'Q_s');
        keyTickX(pn, P, qd, num(qd), ctx, 'Q_d');
      }
      keyTickY(pn, P, pr, num(pr), { selfCheck: false }, '');
      if (ivc2.ghost) { dashTo(pn, P, e0.q, e0.p); point(pn, P, 'e0', e0.q, e0.p, C.ghost, { label: 'E_0', labelColor: 'var(--ink-soft)' }); }
      if (!binding) status = { tone: 'info', text: isC ? 'Потолок не ниже равновесной цены, поэтому не мешает рынку: всё как без регулирования.' : 'Пол не выше равновесной цены, поэтому не мешает рынку: всё как без регулирования.' };
      heroItems = [
        hero('Q', 'Объём торговли', 'Q', qt, e0.q),
        hero('P', 'Цена', 'P', pt, e0.p),
        hero('gap', isC ? 'Дефицит' : 'Избыток', isC ? 'Q_d - Q_s' : 'Q_s - Q_d', binding ? Math.abs(qd - qs) : 0, 0),
        hero('DWL', 'Потери общества', 'DWL', dwl2, 0)
      ];
      tables.push({
        id: 'welfare', title: 'Рынок и благосостояние', cols: ['Было', 'Стало', 'Δ'],
        rows: [
          row('qd', 'Хотят купить', 'Q_d', binding ? qd : e0.q, e0.q),
          row('qs', 'Готовы продать', 'Q_s', binding ? qs : e0.q, e0.q),
          row('cs', 'Излишек покупателя', 'CS', cs2, cs0),
          row('ps', 'Излишек продавца', 'PS', ps2, ps0),
          row('dwl', 'Потери общества', 'DWL', dwl2, 0)
        ]
      });
      ex = explain(EX.ceil, EX.ceilC);
    } else if (isCeil) { ex = explain(EX.ceil, EX.ceilC); }

    if (hiddenMsg) status = { tone: 'info', text: hiddenMsg };
    if (!e0 && !status) status = { tone: 'warn', text: 'Равновесия нет: в первой четверти кривые не пересекаются.' };

    // кривые поверх заливок
    if (dVis) curve(pn, P, 'D', D, C.d, { label: 'D', ends: true });
    if (sVis) curve(pn, P, 'S', S, C.s, { label: 'S', ends: true });
    if (e0 && (key === 'sd' || (isTax && ms.iv.ghost))) {
      if (key === 'sd') point(pn, P, 'E', e0.q, e0.p, 'var(--ink)', { label: 'E' });
    }
    // ключевые точки зажжённой кривой: оси, пересечения, изломы кусочной
    var kpD = [[0, D(0), C.d]], kpS = [[0, S(0), C.s]];
    var qzD = E.firstRoot(D, 0, span, 2000); if (qzD !== null) kpD.push([qzD, 0, C.d]);
    var qzS = E.firstRoot(S, 0, span, 2000); if (qzS !== null) kpS.push([qzS, 0, C.s]);
    if (e0) { kpD.push([e0.q, e0.p, C.d]); kpS.push([e0.q, e0.p, C.s]); }
    if (isTax && typeof q1 === 'number' && q1 !== null && typeof pb === 'number') { kpD.push([q1, pb, C.d]); kpS.push([q1, ps, C.s]); }
    (dres.breaks || []).forEach(function (b) { if (b > 0) kpD.push([b, D(b), C.d]); });
    (sres.breaks || []).forEach(function (b) { if (b > 0) kpS.push([b, S(b), C.s]); });
    if (dVis) keyPoints(pn, P, 'D', kpD, ctx);
    if (sVis) keyPoints(pn, P, 'S', kpS, ctx);

    chart.panels.push(pn);
    chart.legend = ctx.legend === false ? null : legend(pn, P, legendItems);
    answer = { status: status, hero: heroItems, tables: tables, burden: burden, ff: ff, explain: ex || explain([], null) };
    var primary = isTax ? (ms.iv.kind === 'unit' ? ivItems[3] : ivItems[2]) : isCeil ? ivItems[1] : (fnsSection.rows[0].sliders[0] || null);
    return { left: left, chart: chart, answer: answer, primary: primary };
  }

  /* ── 4. Стандартная монополия ─────────────────────────────────────────── */
  LIVE.mono = {
    init: function () {
      return {
        fns: { D: { expr: '100 - Q', shift: 0, visible: true }, MC: { expr: '20', shift: 0, visible: true } }, letters: {},
        iv: { instr: 'none', rate: 20, price: 50, quota: 20, ghost: false },
        show: { cs: true, ps: true, vc: false, dwl: true }
      };
    },
    view: function (ms, ctx) {
      var dres = fnOf(ms, 'D'), mres = fnOf(ms, 'MC');
      addBreaks(dres, mres);
      var defs = [{ id: 'D', sym: 'D', name: 'Спрос', color: C.d }, { id: 'MC', sym: 'MC', name: 'Предельные издержки', color: C.mc }];
      var left = [{ kind: 'fns', title: 'Функции', addLabel: 'Добавить функцию', rows: [fnRow(ms, defs[0], dres, { shift: true }), fnRow(ms, defs[1], mres, { shift: true })] }];
      var iv = ms.iv;
      var ivItems = [seg('iv.instr', '', [['none', 'Нет'], ['tax', 'Налог'], ['sub', 'Субсидия'], ['ceil', 'Потолок'], ['floor', 'Пол'], ['quota', 'Квота']], iv.instr)];
      if (iv.instr === 'tax' || iv.instr === 'sub') ivItems.push(slider('iv.rate', iv.instr === 'tax' ? 'Ставка налога' : 'Размер субсидии', iv.instr === 'tax' ? 't' : 's', 0, 80, 1, iv.rate, '', 'С единицы выпуска: сдвигает MC'));
      if (iv.instr === 'ceil' || iv.instr === 'floor') ivItems.push(slider('iv.price', iv.instr === 'ceil' ? 'Потолок' : 'Пол', iv.instr === 'ceil' ? 'P_{c}' : 'P_{f}', 0, 100, 1, iv.price, '', 'Линию цены можно тянуть на графике'));
      if (iv.instr === 'quota') ivItems.push(slider('iv.quota', 'Квота', 'Q_{к}', 0, 100, 1, iv.quota, '', 'Монополист выпускает не больше квоты'));
      if (iv.instr !== 'none') ivItems.push(toggle('iv.ghost', 'Показать исходное состояние на графике', iv.ghost, C.ghost));
      left.push({ kind: 'iv', title: 'Вмешательство государства', items: ivItems });
      left.push({ kind: 'show', title: 'Показать на графике', items: [
        toggle('show.cs', 'Излишек покупателя', ms.show.cs, 'var(--fill-c-s)', 'CS'),
        toggle('show.ps', 'Излишек производителя', ms.show.ps, 'var(--fill-p-s)', 'PS'),
        toggle('show.vc', 'Переменные издержки', ms.show.vc, 'var(--fill-v-c)', 'VC'),
        toggle('show.dwl', 'Потери общества', ms.show.dwl, 'var(--fill-d-w-l)', 'DWL')
      ] });
      left.push({ kind: 'tools', title: 'Свои точки и площади' });
      var chart = { panels: [], legend: null, note: null };
      if (!dres.ok || !mres.ok) {
        return { left: left, chart: chart, answer: { status: { tone: 'error', text: 'Проверьте запись функции: ' + (!dres.ok ? dres.error : mres.error) }, hero: [], tables: [], burden: null, ff: null, explain: explain(EX.mono, EX.monoC) }, primary: ivItems[1] || null };
      }
      var D = dres.f, MC = mres.f, MCp = posPart(MC);
      var hidM = ms.fns.D.visible === false || ms.fns.MC.visible === false;
      var span = 5000;
      var TR = function (q) { return D(q) * q; };
      var MR = function (q) { return dF(TR, q); };
      var qc = hidM ? null : E.firstRoot(function (q) { return D(q) - MC(q); }, 0, span, 3000);
      var qzero = E.firstRoot(D, 0, span, 3000) || span;
      function optimum(mc) {
        var roots = E.roots(function (q) { return MR(q) - mc(q); }, 0, qzero, 2000);
        var best = null, bestP = -Infinity;
        // кандидаты: корни MR = MC, ноль и изломы спроса (в изломе MR рвётся, и оптимум может стоять ровно там)
        roots.concat([0], BRK.filter(function (b) { return b > 0 && b < qzero; })).forEach(function (q) {
          var prof = TR(q) - I(mc, 0, q);
          if (prof > bestP + 1e-9) { bestP = prof; best = q; }
        });
        return best;
      }
      var qm0 = hidM ? null : optimum(MC);
      var status = null;
      if (hidM) status = { tone: 'info', text: (ms.fns.D.visible === false ? 'Спрос скрыт' : 'Предельные издержки скрыты') + ': скрытой кривой для модели нет, поэтому нет ни оптимума, ни ответа. Верните кривую глазом на её карточке.' };
      else if (qm0 === null || qc === null) status = { tone: 'warn', text: 'Не нашёлся оптимум: проверьте, что спрос убывает, а MC пересекает спрос в первой четверти.' };
      var win = marketWindow([D, MC], [qc || 0], [D(0)]);
      var bw = marketWindow([dres.base]);
      win.x1 = Math.max(win.x1, bw.x1); win.y1 = Math.max(win.y1, bw.y1);
      var P = E.panel({ x: 0, y: 0, w: ctx.cw, h: ctx.ch }, win, popt(ctx, { id: 'main', xName: 'Q', yName: 'P' }));
      var pn = base(P, ctx);
      pn.__hover = ctx.hover && ctx.hover.curve;
      var heroItems = [], tables = [], legendItems = [];
      var total = qc !== null ? I(function (q) { return D(q) - MCp(q); }, 0, qc) : null;
      if (qm0 !== null && qc !== null) {
        var pm0 = D(qm0);
        var vc0 = I(MCp, 0, qm0), cs0 = I(function (q) { return D(q) - pm0; }, 0, qm0);
        var ps0 = pm0 * qm0 - vc0, dwl0 = Math.max(0, total - cs0 - ps0);
        var q = qm0, p = pm0, money = 0, moneySign = 0, mcEff = MC, shortage = null, note2 = null;
        if (iv.instr === 'tax' || iv.instr === 'sub') {
          var t = iv.instr === 'tax' ? iv.rate : -iv.rate;
          mcEff = function (x) { return MC(x) + t; };
          q = optimum(mcEff) || 0; p = D(q);
          money = Math.abs(t) * q; moneySign = iv.instr === 'tax' ? 1 : -1;
        } else if (iv.instr === 'ceil') {
          if (iv.price < pm0) {
            var qd = E.solveFor(D, iv.price, 0, span); if (qd === null) qd = 0;
            var qmc = E.solveFor(MC, iv.price, 0, span);
            q = qmc === null ? (MC(0) > iv.price ? 0 : qd) : Math.min(qd, qmc); p = iv.price;
            if (qd - q > 1e-6) shortage = qd - q;
          } else note2 = 'Потолок не ниже монопольной цены, поэтому не мешает монополисту.';
        } else if (iv.instr === 'floor') {
          if (iv.price > pm0) { var qf = E.solveFor(D, iv.price, 0, span); q = qf === null ? 0 : qf; p = iv.price; }
          else note2 = 'Пол не выше монопольной цены, поэтому не мешает монополисту.';
        } else if (iv.instr === 'quota') {
          if (iv.quota < qm0) { q = iv.quota; p = D(q); }
          else note2 = 'Квота не меньше монопольного выпуска, поэтому не связывает.';
        }
        var vc = I(MCp, 0, q), cs = I(function (x) { return D(x) - p; }, 0, q);
        var ps = p * q - vc - moneySign * money;
        var sw = cs + ps + moneySign * money;
        var dwl = Math.max(0, total - sw);
        var act = iv.instr !== 'none';
        if (note2) status = { tone: 'info', text: note2 };
        // заливки
        var mcTop = function (x) { return Math.max(MCp(x), 0); };
        if (ms.show.vc) { pn.fills.push({ pts: E.polyBetween(mcTop, function () { return 0; }, 0, q, P), fill: 'var(--fill-v-c)' }); legendItems.push({ fill: 'var(--fill-v-c)', t: 'VC' }); }
        if (ms.show.ps) { pn.fills.push({ pts: E.polyBetween(function () { return p; }, function (x) { return Math.min(p, iv.instr === 'tax' ? MCp(x) + iv.rate : MCp(x)); }, 0, q, P), fill: 'var(--fill-p-s)' }); legendItems.push({ fill: 'var(--fill-p-s)', t: 'PS' }); }
        if (ms.show.cs) { pn.fills.push({ pts: E.polyBetween(D, function () { return p; }, 0, q, P), fill: 'var(--fill-c-s)' }); legendItems.push({ fill: 'var(--fill-c-s)', t: 'CS' }); }
        if (iv.instr === 'tax') { pn.fills.push({ pts: E.polyBetween(function (x) { return MCp(x) + iv.rate; }, MCp, 0, q, P), fill: 'var(--fill-t-x)' }); legendItems.push({ fill: 'var(--fill-t-x)', t: 'Сбор' }); }
        if (ms.show.dwl && dwl > 0.01) { pn.fills.push({ pts: E.polyBetween(D, MCp, q, qc, P), fill: 'var(--fill-d-w-l)' }); legendItems.push({ fill: 'var(--fill-d-w-l)', t: 'DWL' }); }
        // кривые
        curve(pn, P, 'MR', MR, C.mr, { dash: '8 5', label: 'MR', w: 2.2, x1: qzero });
        if (iv.instr === 'tax' || iv.instr === 'sub') curve(pn, P, 'mct', mcEff, C.mc, { dash: '8 5', label: iv.instr === 'tax' ? 'MC + t' : 'MC - s', w: 2, noHit: true });
        if (iv.instr === 'ceil' || iv.instr === 'floor') {
          pn.segs.push({ x1: E.r1(P.plot.x), y1: E.r1(P.sy(iv.price)), x2: E.r1(P.plot.x + P.plot.w), y2: E.r1(P.sy(iv.price)), color: C.reg, w: 2.5, dash: 'none' });
          handle(pn, P, 'price', win.x1 * 0.86, iv.price, (iv.instr === 'ceil' ? 'Pc' : 'Pf') + ' = ' + num(iv.price), { axis: 'y', cursor: 'ns-resize', side: 'left' });
        }
        if (iv.instr === 'quota') {
          pn.segs.push({ x1: E.r1(P.sx(iv.quota)), y1: E.r1(P.plot.y), x2: E.r1(P.sx(iv.quota)), y2: E.r1(P.plot.y + P.plot.h), color: C.reg, w: 2.5, dash: 'none' });
          handle(pn, P, 'quota', iv.quota, win.y1 * 0.9, 'Qк = ' + num(iv.quota), { axis: 'x', cursor: 'ew-resize' });
        }
        dashTo(pn, P, q, p);
        keyTickX(pn, P, q, num(q), ctx, 'Q_m');
        keyTickY(pn, P, p, num(p), ctx, 'P_m');
        keyTickX(pn, P, qc, num(qc) + '_c', ctx, 'Q_c');
        point(pn, P, 'M', q, p, 'var(--ink)', { label: 'M' });
        var mrAt = iv.instr === 'tax' || iv.instr === 'sub' ? mcEff(q) : MR(q);
        if (!iv.instr || iv.instr === 'none' || iv.instr === 'tax' || iv.instr === 'sub') point(pn, P, 'mrmc', q, mrAt, C.mr, { r: 3.6 });
        if (act && iv.ghost) { dashTo(pn, P, qm0, pm0); point(pn, P, 'M0', qm0, pm0, C.ghost, { label: 'M_0', labelColor: 'var(--ink-soft)' }); }
        heroItems = [
          hero('Q', 'Выпуск монополиста', 'Q_m', q, act ? qm0 : null),
          hero('P', 'Цена', 'P_m', p, act ? pm0 : null),
          hero('DWL', 'Потери общества', 'DWL', dwl, act ? dwl0 : null),
          hero('Qc', 'Конкурентный выпуск', 'Q_c', qc, null)
        ];
        var rows = [
          row('cs', 'Излишек покупателя', 'CS', cs, act ? cs0 : null),
          row('ps', 'Излишек производителя', 'PS', ps, act ? ps0 : null),
          row('vc', 'Переменные издержки', 'VC', vc, act ? vc0 : null)
        ];
        if (iv.instr === 'tax' || iv.instr === 'sub') rows.push(row('budget', iv.instr === 'tax' ? 'Сбор бюджета' : 'Расход бюджета', '', money, 0));
        if (shortage !== null) rows.push(row('short', 'Дефицит', '', shortage, 0));
        rows.push(row('dwl', 'Потери общества', 'DWL', dwl, act ? dwl0 : null));
        tables.push({ id: 'welfare', title: act ? 'Благосостояние' : 'Излишки и потери', cols: act ? ['Было', 'Стало', 'Δ'] : null, rows: rows });
      }
      if (ms.fns.D.visible !== false) curve(pn, P, 'D', D, C.d, { label: 'D', ends: true });
      if (ms.fns.MC.visible !== false) curve(pn, P, 'MC', MC, C.mc, { label: 'MC', ends: true });
      var kpD = [[0, D(0), C.d]]; var z = E.firstRoot(D, 0, span, 2000); if (z !== null) kpD.push([z, 0, C.d]);
      if (qc !== null) kpD.push([qc, D(qc), C.d]);
      (dres.breaks || []).forEach(function (b) { if (b > 0) kpD.push([b, D(b), C.d]); });
      var kpM = [[0, MC(0), C.mc]].concat(qc !== null ? [[qc, MC(qc), C.mc]] : []);
      (mres.breaks || []).forEach(function (b) { if (b > 0) kpM.push([b, MC(b), C.mc]); });
      if (ms.fns.D.visible !== false) keyPoints(pn, P, 'D', kpD, ctx);
      if (ms.fns.MC.visible !== false) keyPoints(pn, P, 'MC', kpM, ctx);
      chart.panels.push(pn);
      chart.legend = ctx.legend === false ? null : legend(pn, P, legendItems);
      return {
        left: left, chart: chart,
        answer: { status: status, hero: heroItems, tables: tables, burden: null, ff: null, explain: explain(EX.mono, EX.monoC) },
        primary: ivItems[1] || left[0].rows[0].sliders[0] || null
      };
    }
  };

  /* ── 5. Издержки фирмы ─────────────────────────────────────────────────
     Два способа ввода, как в calc2: «Задам TC» (всё выводится из TC) и
     «Задам кривые» (MC, ATC, AVC — каждая своя, пустое поле = кривой нет). */
  LIVE.costs = {
    init: function () {
      return {
        fns: {
          TC: { expr: 'Q^3 - 6Q^2 + 15Q + 18', shift: 0, visible: true },
          MC: { expr: '3Q^2 - 12Q + 15', shift: 0, visible: true },
          ATC: { expr: 'Q^2 - 6Q + 15 + 18/Q', shift: 0, visible: true },
          AVC: { expr: 'Q^2 - 6Q + 15', shift: 0, visible: true }
        },
        letters: {},
        par: { P: 15, mode: 'tc' },
        show: { mc: true, atc: true, avc: true, afc: true, tc: false, vc: false, fc: false, price: true, profit: true }
      };
    },
    view: function (ms, ctx) {
      var mode = ms.par.mode === 'curves' ? 'curves' : 'tc';
      var fnsSec = { kind: 'fns', title: 'Функции', addLabel: '', rows: [],
        pre: seg('par.mode', 'Как задаём издержки', [['tc', 'Задам TC'], ['curves', 'Задам кривые']], mode) };
      var TC = null, MC = null, ATC = null, AVC = null, VC = null, AFC = null, FC = null, err = null, warn = null;
      if (mode === 'tc') {
        var tres = fnOf(ms, 'TC');
        addBreaks(tres);
        fnsSec.rows.push(fnRow(ms, { id: 'TC', sym: 'TC(Q)', name: 'Общие издержки', color: C.tc, prefix: 'TC =' }, tres, { canHide: false }));
        fnsSec.hint = 'FC = TC(0), VC = TC − FC, ATC = TC / Q, AVC = VC / Q, MC = dTC / dQ.';
        if (!tres.ok) err = 'Проверьте запись TC(Q): ' + tres.error;
        else {
          var T = tres.f; TC = T; FC = T(0);
          VC = function (q) { return T(q) - FC; };
          MC = function (q) { return dF(T, q); };
          ATC = function (q) { return q > 1e-6 ? T(q) / q : NaN; };
          AVC = function (q) { return q > 1e-6 ? VC(q) / q : NaN; };
        }
      } else {
        var defs = [['MC', 'Предельные издержки', C.mc], ['ATC', 'Средние общие', C.atc], ['AVC', 'Средние переменные', C.avc]];
        var res = {};
        defs.forEach(function (d) {
          var r = fnOf(ms, d[0]); res[d[0]] = r; addBreaks(r);
          var row = fnRow(ms, { id: d[0], sym: d[0] + '(Q)', name: d[1], color: d[2], prefix: d[0] + ' =' }, r, { canHide: false });
          if (r.empty) { row.error = ''; row.emptyNote = 'Поле пустое, этой кривой нет.'; }
          fnsSec.rows.push(row);
          if (!r.ok && !r.empty && !err) err = 'Проверьте запись ' + d[0] + '(Q): ' + r.error;
        });
        fnsSec.hint = 'Для условий, где даны MC и ATC, а TC нет. Пустое поле значит, что кривой нет. Если даны ATC и AVC, FC = (ATC − AVC) · Q.';
        if (res.MC.ok) MC = res.MC.f;
        if (res.ATC.ok) ATC = function (q) { return q > 1e-6 ? res.ATC.f(q) : NaN; };
        if (res.AVC.ok) AVC = function (q) { return q > 1e-6 ? res.AVC.f(q) : NaN; };
        if (ATC && AVC) {
          FC = ATC(1) - AVC(1);
          var fc2 = (ATC(3) - AVC(3)) * 3;
          if (Math.abs(fc2 - FC) > 1e-6 * (1 + Math.abs(FC))) warn = 'ATC и AVC несогласованы: (ATC − AVC) · Q должно быть постоянным. Расчёт идёт, но проверьте условие.';
        }
        if (ATC) TC = function (q) { return q > 1e-6 ? ATC(q) * q : FC !== null ? FC : NaN; };
        if (AVC) VC = function (q) { return q > 1e-6 ? AVC(q) * q : 0; };
      }
      if (FC !== null) { var FCc = FC; AFC = function (q) { return q > 1e-6 ? FCc / q : NaN; }; }
      var left = [fnsSec];
      left.push({ kind: 'params', title: 'Параметры', items: [
        slider('par.P', 'Рыночная цена', 'P', 0, 50, 0.5, ms.par.P, '', 'Линию цены можно тянуть на графике'),
        { type: 'button', id: 'reset.tc', label: 'Стандартные издержки' }
      ] });
      var sh = ms.show, showItems = [];
      if (MC) showItems.push(toggle('show.mc', 'Предельные', sh.mc, C.mc, 'MC'));
      if (ATC) showItems.push(toggle('show.atc', 'Средние общие', sh.atc, C.atc, 'ATC'));
      if (AVC) showItems.push(toggle('show.avc', 'Средние переменные', sh.avc, C.avc, 'AVC'));
      if (AFC) showItems.push(toggle('show.afc', 'Средние постоянные', sh.afc, C.afc, 'AFC'));
      if (TC) showItems.push(toggle('show.tc', 'Общие', sh.tc, C.tc, 'TC'));
      if (VC) showItems.push(toggle('show.vc', 'Переменные', sh.vc, C.vc, 'VC'));
      if (FC !== null) showItems.push(toggle('show.fc', 'Постоянные', sh.fc, C.fc, 'FC'));
      showItems.push(toggle('show.price', 'Цена и прибыль', sh.price, C.price, ''));
      showItems.push(toggle('show.profit', 'Прямоугольник прибыли или убытка', sh.profit, 'var(--fill-profit)', ''));
      left.push({ kind: 'show', title: 'Показать на графике', items: showItems });
      left.push({ kind: 'tools', title: 'Свои точки и площади' });
      var chart = { panels: [], legend: null, note: null };
      if (err || !MC) {
        return { left: left, chart: chart, answer: { status: { tone: 'error', text: err || 'Без MC фирма не найдёт выпуск: задайте MC(Q).' }, hero: [], tables: [], burden: null, ff: null, explain: explain(EX.costs, EX.costsC) }, primary: left[1].items[0] };
      }
      var price = ms.par.P;
      var win = { x0: 0, x1: 10, y0: 0, y1: 50 };
      // минимумы средних — там, где их пересекает MC
      var qAVC = AVC ? E.firstRoot(function (q) { return MC(q) - AVC(q); }, 0.05, 50, 2000) : null;
      var qATC = ATC ? E.firstRoot(function (q) { return MC(q) - ATC(q); }, 0.05, 50, 2000) : null;
      var minAVC = qAVC !== null ? AVC(qAVC) : null, minATC = qATC !== null ? ATC(qATC) : null;
      // оптимум: P = MC на возрастающей ветке MC и P ≥ min AVC
      var qStar = 0;
      if (minAVC === null || price >= minAVC) {
        var rts = E.roots(function (q) { return MC(q) - price; }, 0.01, 60, 3000).filter(function (q) { return dF(MC, q) > 0; });
        qStar = rts.length ? rts[rts.length - 1] : 0;
      }
      var profit = ATC && qStar > 0 ? (price - ATC(qStar)) * qStar : (FC !== null && qStar === 0 ? -FC : null);
      var P = E.panel({ x: 0, y: 0, w: ctx.cw, h: ctx.ch }, win, popt(ctx, { id: 'main', xName: 'Q', yName: 'P' }));
      var pn = base(P, ctx);
      pn.__hover = ctx.hover && ctx.hover.curve;
      var lg = [];
      if (sh.profit && sh.price && qStar > 0 && ATC) {
        var atcS = ATC(qStar);
        pn.fills.push({ pts: E.rectPoly(0, qStar, Math.min(price, atcS), Math.max(price, atcS), P), fill: profit >= 0 ? 'var(--fill-profit)' : 'var(--fill-loss)' });
        lg.push({ fill: profit >= 0 ? 'var(--fill-profit)' : 'var(--fill-loss)', t: profit >= 0 ? 'Прибыль' : 'Убыток' });
      }
      if (sh.tc && TC) curve(pn, P, 'TC', TC, C.tc, { label: 'TC', x0: 0.001 });
      if (sh.vc && VC) curve(pn, P, 'VC', VC, C.vc, { label: 'VC', x0: 0.001 });
      if (sh.fc && FC !== null) curve(pn, P, 'FC', function () { return FC; }, C.fc, { label: 'FC' });
      if (sh.afc && AFC) curve(pn, P, 'AFC', AFC, C.afc, { label: 'AFC', x0: 0.05 });
      if (sh.avc && AVC) curve(pn, P, 'AVC', AVC, C.avc, { label: 'AVC', x0: 0.05 });
      if (sh.atc && ATC) curve(pn, P, 'ATC', ATC, C.atc, { label: 'ATC', x0: 0.05 });
      if (sh.mc) curve(pn, P, 'MC', MC, C.mc, { label: 'MC', x0: 0 });
      if (sh.price) {
        pn.segs.push({ x1: E.r1(P.plot.x), y1: E.r1(P.sy(price)), x2: E.r1(P.plot.x + P.plot.w), y2: E.r1(P.sy(price)), color: C.price, w: 2.5, dash: 'none' });
        handle(pn, P, 'price', P.win.x0 + (P.win.x1 - P.win.x0) * 0.86, price, 'P = ' + num(price), { axis: 'y', cursor: 'ns-resize', side: 'left' });
        keyTickY(pn, P, price, num(price), { selfCheck: false }, '');
        if (qStar > 0) {
          dashTo(pn, P, qStar, price, false, true);
          keyTickX(pn, P, qStar, num(qStar), ctx, 'Q^*');
          point(pn, P, 'opt', qStar, price, 'var(--ink)', { label: 'P = MC' });
        }
      }
      if (qAVC !== null) point(pn, P, 'shut', qAVC, minAVC, C.avc, { label: 'закрытие', labelColor: C.avc, r: 4 });
      if (qATC !== null) point(pn, P, 'be', qATC, minATC, C.atc, { label: 'безубыточность', labelColor: C.atc, r: 4, ly: 18, lx: 8 });
      var kpMC = [];
      if (qAVC !== null) kpMC.push([qAVC, minAVC, C.mc]);
      if (qATC !== null) kpMC.push([qATC, minATC, C.mc]);
      if (sh.mc && kpMC.length) keyPoints(pn, P, 'MC', kpMC, ctx);
      chart.panels.push(pn);
      chart.legend = ctx.legend === false ? null : legend(pn, P, lg);
      var verdict, tone = 'info';
      if (qStar === 0) verdict = 'Цена ниже минимума AVC: выгоднее не работать вовсе' + (FC !== null ? ', убыток равен постоянным издержкам.' : '.');
      else if (profit === null) verdict = 'Выпуск найден по P = MC. Чтобы посчитать прибыль, нужна ATC или TC.';
      else if (profit > 0.005) verdict = 'Цена выше минимума ATC: фирма получает экономическую прибыль. В длинном периоде в отрасль войдут новые фирмы.';
      else if (profit < -0.005) verdict = 'Цена между минимумами AVC и ATC: фирма работает в убыток, но меньший, чем при закрытии.';
      else verdict = 'Цена равна минимуму ATC: прибыль нулевая, это точка безубыточности.';
      if (warn) { verdict = warn; tone = 'warn'; }
      var marks = [];
      if (minAVC !== null) marks.push(row('shut', 'Закрытие: минимум AVC', 'AVC_{min}', minAVC), row('qshut', 'при выпуске', 'Q', qAVC));
      if (minATC !== null) marks.push(row('be', 'Безубыточность: минимум ATC', 'ATC_{min}', minATC), row('qbe', 'при выпуске', 'Q', qATC));
      if (FC !== null) marks.push(row('fc', 'Постоянные издержки', 'FC', FC));
      return {
        left: left, chart: chart,
        answer: {
          status: { tone: tone, text: verdict },
          hero: [hero('Q', 'Выпуск фирмы', 'Q^*', qStar), hero('profit', profit === null || profit >= 0 ? 'Прибыль' : 'Убыток', '\\pi', profit === null ? '–' : profit), hero('atc', 'Средние издержки', 'ATC(Q^*)', qStar > 0 && ATC ? ATC(qStar) : '–'), hero('P', 'Цена', 'P', price)],
          tables: marks.length ? [{ id: 'marks', title: 'Ориентиры', cols: null, rows: marks }] : [],
          burden: null, ff: null, explain: explain(EX.costs, EX.costsC)
        },
        primary: left[1].items[0]
      };
    }
  };

  /* ── 6. Функция и её производная (две панели) ────────────────────────── */
  LIVE['m-tangent'] = {
    init: function () {
      return { fns: { f: { expr: 'x^2', shift: 0, visible: true } }, letters: {}, par: { x0: 1, dx: 1, secant: false } };
    },
    view: function (ms, ctx) {
      var fres = fnOf(ms, 'f', 'x');
      addBreaks(fres);
      var left = [{ kind: 'fns', title: 'Функция', addLabel: '', rows: [fnRow(ms, { id: 'f', sym: 'f(x)', name: 'Исследуемая функция', color: C.d, prefix: 'y =', axis: 'x' }, fres, { canHide: false })] }];
      var par = ms.par;
      var items = [slider('par.x0', 'Точка касания', 'x_0', -5, 5, 0.01, par.x0, '', 'Точку можно тянуть в обеих панелях'), toggle('par.secant', 'Секущая через две точки', par.secant, C.tax)];
      if (par.secant) items.push(slider('par.dx', 'Шаг секущей', '\\Delta x', 0.1, 3, 0.05, par.dx, ''));
      left.push({ kind: 'params', title: 'Параметры', items: items });
      left.push({ kind: 'tools', title: 'Свои точки и площади' });
      var chart = { panels: [], legend: null, note: null };
      if (!fres.ok) return { left: left, chart: chart, answer: { status: { tone: 'error', text: 'Проверьте запись f(x): ' + fres.error }, hero: [], tables: [], burden: null, ff: null, explain: explain(EX.tangent, EX.tangentC) }, primary: items[0] };
      var f = fres.f, fp = function (x) { return dF(f, x); };
      var x0 = par.x0, y0 = f(x0), k = fp(x0);
      // окна: по значениям функции на [−6; 6]
      var xs = [], lo = Infinity, hi = -Infinity, dlo = Infinity, dhi = -Infinity;
      for (var i = 0; i <= 120; i++) { var x = -6 + i * 0.1; var v = f(x), dv = fp(x); if (isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } if (isFinite(dv)) { dlo = Math.min(dlo, dv); dhi = Math.max(dhi, dv); } xs.push(x); }
      var top = { x0: -6, x1: 6, y0: Math.min(-2, Math.floor(lo - 1)), y1: Math.max(4, Math.min(40, E.niceCeil(Math.max(1, hi)))) };
      var dm = Math.max(Math.abs(dlo), Math.abs(dhi), 2);
      var bot = { x0: -6, x1: 6, y0: -E.niceCeil(dm), y1: E.niceCeil(dm) };
      var gap = 14, hTop = Math.round((ctx.ch - gap) * 0.56), hBot = ctx.ch - gap - hTop;
      var P1 = E.panel({ x: 0, y: 0, w: ctx.cw, h: hTop }, top, { id: 'top', xName: 'x', yName: 'y', grid: ctx.grid, view: ctx.view, margin: { l: 46, r: 34, t: 34, b: 26 } });
      var P2 = E.panel({ x: 0, y: hTop + gap, w: ctx.cw, h: hBot }, bot, { id: 'bottom', xName: 'x', yName: 'y′', grid: ctx.grid, view: ctx.view ? { k: ctx.view.k, px: ctx.view.px, py: 0 } : null, margin: { l: 46, r: 34, t: 34, b: 26 } });
      var a = base(P1, ctx), b = base(P2, ctx);
      a.__hover = b.__hover = ctx.hover && ctx.hover.curve;
      a.title = { x: P1.plot.x + 22, y: P1.box.y + 16, t: 'f(x): сама функция' };
      b.title = { x: P2.plot.x + 22, y: P2.box.y + 16, t: 'f′(x): её производная, наклон в каждой точке' };
      curve(a, P1, 'f', f, C.d, { label: 'f', ends: true });
      curve(a, P1, 'tan', function (x) { return y0 + k * (x - x0); }, C.reg, { w: 2, label: 'касательная', labelSize: 13, noHit: true });
      var dx = par.dx;
      // треугольник Δx, Δy по касательной
      var tx1 = x0 + 1.5, ty1 = y0 + k * 1.5;
      a.segs.push({ x1: E.r1(P1.sx(x0)), y1: E.r1(P1.sy(y0)), x2: E.r1(P1.sx(tx1)), y2: E.r1(P1.sy(y0)), color: C.reg, w: 1.4, dash: '4 3' });
      a.segs.push({ x1: E.r1(P1.sx(tx1)), y1: E.r1(P1.sy(y0)), x2: E.r1(P1.sx(tx1)), y2: E.r1(P1.sy(ty1)), color: C.reg, w: 1.4, dash: '4 3' });
      var lyx = P1.sy(y0) + 16; if (Math.abs(lyx - P1.axis.x.y1) < 24) lyx = P1.sy(y0) - 7;
      a.labels.push(label(P1.sx(x0 + 0.75), lyx, '\\Delta x = 1,5', C.reg, 'middle', 12.5));
      a.labels.push(label(P1.sx(tx1) + 6, (P1.sy(y0) + P1.sy(ty1)) / 2 + 4, '\\Delta y = ' + (ctx.selfCheck ? '?' : num(k * 1.5)), C.reg, 'start', 12.5));
      var ks = null;
      if (par.secant) {
        var x1s = x0 + dx, y1s = f(x1s); ks = (y1s - y0) / dx;
        curve(a, P1, 'sec', function (x) { return y0 + ks * (x - x0); }, C.tax, { w: 2, dash: '8 5', label: 'секущая', labelSize: 13, noHit: true });
        point(a, P1, 'x1', x1s, y1s, C.tax, { r: 4 });
      }
      point(a, P1, 'x0', x0, y0, C.d, { r: 5 });
      handle(a, P1, 'x0top', x0, y0, 'x₀ = ' + num(x0), { axis: 'x', cursor: 'ew-resize', side: 'left' });
      curve(b, P2, 'fp', fp, C.mc, { label: 'f′' });
      point(b, P2, 'd0', x0, k, C.mc, { r: 5 });
      handle(b, P2, 'x0bot', x0, k, 'f′(x₀) = ' + (ctx.selfCheck ? '?' : num(k)), { axis: 'x', cursor: 'ew-resize', side: 'left' });
      // вертикаль x₀ через обе панели
      b.dashes.push({ x1: E.r1(P2.sx(x0)), y1: E.r1(P2.plot.y), x2: E.r1(P2.sx(x0)), y2: E.r1(P2.plot.y + P2.plot.h) });
      a.dashes.push({ x1: E.r1(P1.sx(x0)), y1: E.r1(P1.sy(y0)), x2: E.r1(P1.sx(x0)), y2: E.r1(P1.plot.y + P1.plot.h) });
      var kz = E.roots(fp, -6, 6, 600);
      keyPoints(a, P1, 'f', kz.map(function (x) { return [x, f(x), C.d]; }).concat(E.roots(f, -6, 6, 600).map(function (x) { return [x, 0, C.d]; }), [[0, f(0), C.d]], (fres.breaks || []).map(function (b) { return [b, f(b), C.d]; })), ctx);
      keyPoints(b, P2, 'fp', kz.map(function (x) { return [x, 0, C.mc]; }), ctx);
      chart.panels.push(a, b);
      var angle = Math.atan(k) * 180 / Math.PI;
      var tanText = E.linearText(y0 - k * x0, k, 'x', true);
      var rows = [row('x0', 'Точка касания', 'x_0', x0), row('ang', 'Угол наклона касательной', '\\alpha', num(angle) + '°')];
      if (ks !== null) rows.push(row('ks', 'Наклон секущей', '\\Delta y / \\Delta x', ks));
      return {
        left: left, chart: chart,
        answer: {
          status: null,
          hero: [hero('fx', 'Значение функции', 'f(x_0)', y0), hero('k', 'Производная', 'f′(x_0)', k)],
          tables: [{ id: 'tan', title: 'Касательная', cols: null, rows: rows }],
          burden: null,
          ff: { name: 'Уравнение касательной', sym: [], toks: E.typeset(tanText), copy: 'y = ' + E.prettyExpr(tanText), prefix: 'y =' },
          explain: explain(EX.tangent, EX.tangentC)
        },
        primary: items[0]
      };
    }
  };

  E.LIVE = LIVE;

  /* ════════════════════════════════════════════════════════════════════════
     СХЕМА: любая из остальных 36 моделей на том же каркасе
     ════════════════════════════════════════════════════════════════════════ */
  function schematicView(key, ctx) {
    var sp = E.SPECS[key] || { fn: [], par: [], sl: [], show: [], hero: [], more: [] };
    var cols = [C.d, C.s, C.mc, C.mr, C.reg, C.tax];
    var left = [];
    if (sp.fn.length) left.push({ kind: 'fns', title: 'Функции', addLabel: '', schematic: true, rows: sp.fn.map(function (f, i) {
      return { id: 'f' + i, sym: m(f[0].replace('₁', '_1').replace('₂', '_2').replace('₀', '_0')), name: f[1], color: cols[i % cols.length], visible: true, prefix: '', expr: f[2], toks: E.typeset(f[2]), error: '', canHide: false, sliders: [] };
    }) });
    var pitems = sp.par.map(function (p) { return { type: 'static', label: p[1], sym: p[0] ? m(p[0]) : [], value: p[2] }; });
    sp.sl.forEach(function (s) { pitems.push({ type: 'static', label: 'Ползунок', sym: [], value: s }); });
    if (pitems.length) left.push({ kind: 'params', title: 'Параметры', items: pitems });
    if (sp.iv) left.push({ kind: 'iv', title: 'Вмешательство', items: [{ type: 'static', label: 'Каскад', sym: [], value: sp.iv }] });
    if (sp.show.length) left.push({ kind: 'show', title: 'Показать на графике', items: sp.show.map(function (s, i) { return toggle('x' + i, s, true, cols[i % cols.length]); }) });
    left.push({ kind: 'tools', title: 'Свои точки и площади' });
    var card = E.card(key);
    return {
      left: left,
      chart: { panels: [], legend: null, note: { card: card, cv: sp.cv, hd: sp.hd, ax: sp.ax } },
      answer: {
        status: { tone: 'info', text: 'Схема модели: в макете оживлены 6 моделей, остальные показаны скелетом. Числа и график считает рабочий движок calc2, каркас экрана для них тот же.' },
        hero: sp.hero.map(function (h, i) { return { id: 'h' + i, label: h, sym: [], value: '–', was: null, delta: '', hasWas: false }; }),
        tables: sp.more.length ? [{ id: 'more', title: 'Остальные значения', cols: null, rows: sp.more.map(function (h, i) { return { id: 'r' + i, label: h, sym: [], value: '–', was: null, delta: '', hasWas: false }; }) }] : [],
        burden: null,
        ff: sp.ff ? { name: sp.ff, sym: [], toks: [{ k: 'raw', t: 'кусочная запись, как сейчас в calc2' }], copy: '', prefix: '' } : null,
        explain: { items: [{ id: 'ex0', q: E.richText('Разбор модели'), a: E.richText('Текст берётся из реестра SCENE_EXPLAIN (calc2/static/calc2/90-explain.js) по ключу «' + key + '» без изменений, в том же порядке: вопрос → ответ → вывод.') }], conclusion: sp.note ? E.richText(sp.note) : null }
      },
      primary: null
    };
  }

  /* «Добавить функцию»: свои кривые поверх любой живой модели — рисуются,
     подписываются, но в расчёт модели не входят (как в calc2). */
  function addExtras(v, ms, ctx) {
    var ids = Object.keys(ms.fns || {}).filter(function (k) { return ms.fns[k].extra; });
    if (!ids.length) return;
    var sec = null;
    v.left.forEach(function (s) { if (s.kind === 'fns' && !sec) sec = s; });
    var pn = v.chart.panels[0];
    var axis = sec && sec.rows[0] ? sec.rows[0].axis : 'Q';
    ids.forEach(function (id, i) {
      var fs = ms.fns[id];
      var res = fnOf(ms, id, axis);
      var row = fnRow(ms, { id: id, sym: 'F_' + (i + 1), name: 'Своя функция', color: XCOL[i % XCOL.length], prefix: axis === 'x' ? 'y =' : 'P =', axis: axis }, res, { canHide: true });
      row.isExtra = true;
      if (res.empty) { row.error = ''; row.emptyNote = 'Введите формулу, и кривая появится на графике.'; }
      if (sec) sec.rows.push(row);
      if (res.ok && pn && pn._P && fs.visible !== false) {
        curve(pn, pn._P, id, res.f, row.color, { label: LB[id] || ('F_' + (i + 1)), w: 2.4, breaks: res.breaks, ends: true });
        var kx = [[0, res.f(0), row.color]];
        var zx = E.firstRoot(res.f, pn._P.win.x0, pn._P.win.x1, 800); if (zx !== null) kx.push([zx, 0, row.color]);
        (res.breaks || []).forEach(function (b) { kx.push([b, res.f(b), row.color]); });
        keyPoints(pn, pn._P, id, kx, ctx);
      }
    });
  }

  /* ════════════════════════════════════════════════════════════════════════
     ПУБЛИЧНЫЙ ВХОД
     ════════════════════════════════════════════════════════════════════════ */
  E.isLive = function (key) { return !!LIVE[key]; };
  E.initModel = function (key) { return LIVE[key] ? LIVE[key].init() : { schematic: true }; };
  E.view = function (key, ms, ctx) {
    LS = ctx.labelScale || 1;
    CO = (ms && ms.colors) || {}; LB = (ms && ms.labels) || {};
    BRK = [];
    try {
      var v = LIVE[key] ? LIVE[key].view(ms, ctx) : schematicView(key, ctx);
      v.live = !!LIVE[key];
      if (v.live) addExtras(v, ms, ctx);
      return v;
    } catch (e) {
      return { live: !!LIVE[key], left: [], chart: { panels: [], legend: null, note: null }, answer: { status: { tone: 'error', text: 'Ошибка макета: ' + e.message }, hero: [], tables: [], burden: null, ff: null, explain: { items: [], conclusion: null } }, primary: null };
    }
  };

  /* ── куски: начало, добавление, удаление ──────────────────────────────── */
  function axisOf(key) { return key === 'm-tangent' ? 'x' : 'Q'; }
  function numStr(v) { return String(Math.round(v * 1e6) / 1e6).replace('.', ','); }
  function round1(v) { if (!(v > 0)) return 0; var p = Math.pow(10, Math.floor(Math.log10(v))); return Math.round(v / p) * p; }
  /* «Задать кусками»: набранная цепочка условий разворачивается в те же строки; обычная формула
     делится на два одинаковых куска с границей посередине — график при этом не меняется. */
  function piecesFrom(key, ms, id) {
    var fs = ms.fns[id], axis = axisOf(key), e = String(fs.expr || '').trim();
    var c = e ? E.compileFn(e, axis) : { ok: false };
    var rows = c.ok ? (c.form === 'QP' ? c.rowsP : c.rows) : null;
    if (rows && rows.length) {
      var lhs = E.splitEq(e).lhs;
      return rows.map(function (rw, i) {
        // хвост «иначе» продолжает предыдущий участок: его «от» — это «до» соседа сверху
        var from = rw.from === null ? (rw.rest && i > 0 && rows[i - 1].to !== null ? numStr(rows[i - 1].to) : '') : numStr(rw.from);
        return { expr: (lhs ? lhs + ' = ' : '') + E.astText(rw.ast), from: from, to: rw.to === null ? '' : numStr(rw.to) };
      });
    }
    var B = 0;
    if (axis !== 'x') {
      B = 50;
      if (c.ok) {
        var params = ms.letters || {};
        var g = c.form === 'QP' ? function (p) { return c.g(p, params); } : function (q) { return c.f(q, params); };
        var z = E.firstRoot(g, 0.001, 5000, 2500);
        if (z !== null && z > 0) B = round1(z / 2) || 50;
      }
    }
    return [{ expr: e, from: '', to: numStr(B) }, { expr: e, from: numStr(B), to: '' }];
  }
  function pwAdd(pieces) {
    var last = pieces[pieces.length - 1], prev = pieces[pieces.length - 2];
    var lt = boundVal(last.to), lf = boundVal(last.from);
    if (lt === null || lt !== lt) {
      // последняя граница открыта: закрываем её на шаг дальше и продолжаем тем же куском
      var base = typeof lf === 'number' && lf === lf ? lf : 0;
      var pf = prev ? boundVal(prev.from) : null;
      var step = (typeof pf === 'number' && pf === pf && base > pf) ? base - pf : (base > 0 ? base : 10);
      var nb = numStr(base + step);
      last.to = nb;
      pieces.push({ expr: last.expr, from: nb, to: '' });
    } else pieces.push({ expr: last.expr, from: String(last.to), to: '' });
  }
  function pwDel(pieces, i) {
    var gone = pieces[i];
    if (!gone || pieces.length < 2) return;
    // участок удалённого куска достаётся соседу, чтобы в области не осталось дыры
    if (pieces[i - 1]) pieces[i - 1].to = gone.to;
    else if (pieces[i + 1]) pieces[i + 1].from = gone.from;
    pieces.splice(i, 1);
  }

  /* Изменение состояния по id элемента управления: 'fns.D.expr', 'iv.rate', 'show.cs'… */
  E.setValue = function (key, ms, id, value) {
    var n = clone(ms);
    var parts = id.split('.');
    if (parts[0] === 'color') { n.colors = n.colors || {}; n.colors[parts[1]] = value; return n; }
    if (parts[0] === 'label') { n.labels = n.labels || {}; if (value) n.labels[parts[1]] = value; else delete n.labels[parts[1]]; return n; }
    if (id === 'fns.add') {
      var k = 1; while (n.fns['F' + k]) k++;
      n.fns['F' + k] = { expr: value || '', shift: 0, visible: true, extra: true };
      return n;
    }
    if (parts[0] === 'fns' && parts[2] === 'remove') { delete n.fns[parts[1]]; return n; }
    if (parts[0] === 'fns' && parts[2] === 'restore') { var ini = E.initModel(key); if (ini.fns && ini.fns[parts[1]]) { n.fns[parts[1]].expr = ini.fns[parts[1]].expr; delete n.fns[parts[1]].pieces; } return n; }
    // куски целиком: массив или строка «формула|от|до/формула|от|до» (так их задают доски макета)
    if (parts[0] === 'fns' && parts[2] === 'pieces') {
      var fq = n.fns[parts[1]];
      if (!fq) return n;
      if (!value) { delete fq.pieces; return n; }
      fq.pieces = typeof value === 'string' ? value.split('/').map(function (t) { var q = t.split('|'); return { expr: (q[0] || '').trim(), from: (q[1] || '').trim(), to: (q[2] || '').trim() }; }) : clone(value);
      if (fq.pieces[0]) fq.expr = fq.pieces[0].expr;
      return n;
    }
    if (parts[0] === 'fns' && parts[2] === 'pw') {
      var fp = n.fns[parts[1]], act = parts[3];
      if (!fp) return n;
      if (act === 'on') { fp.pieces = piecesFrom(key, n, parts[1]); return n; }
      if (act === 'off') { if (fp.pieces && fp.pieces.length) fp.expr = fp.pieces[0].expr; delete fp.pieces; return n; }
      if (!fp.pieces || !fp.pieces.length) return n;
      if (act === 'add') { pwAdd(fp.pieces); return n; }
      if (act === 'count') {
        var want = Math.max(1, Math.min(12, Math.round(+value) || 1));
        while (fp.pieces.length < want) pwAdd(fp.pieces);
        while (fp.pieces.length > want) pwDel(fp.pieces, fp.pieces.length - 1);
        return n;
      }
      if (act === 'del') {
        pwDel(fp.pieces, +value);
        // остался один кусок без границ — это снова обычная формула
        if (fp.pieces.length === 1 && !String(fp.pieces[0].from || '').trim() && !String(fp.pieces[0].to || '').trim()) { fp.expr = fp.pieces[0].expr; delete fp.pieces; }
        return n;
      }
      var idx = +act, fld = parts[4], pc = fp.pieces[idx];
      if (!pc || (fld !== 'expr' && fld !== 'from' && fld !== 'to')) return n;
      var old = String(pc[fld] === undefined || pc[fld] === null ? '' : pc[fld]).trim();
      pc[fld] = String(value);
      // соседние границы связаны: «до» этого куска — это «от» следующего
      if (fld === 'to' && fp.pieces[idx + 1] && String(fp.pieces[idx + 1].from || '').trim() === old) fp.pieces[idx + 1].from = String(value);
      if (fld === 'from' && fp.pieces[idx - 1] && String(fp.pieces[idx - 1].to || '').trim() === old) fp.pieces[idx - 1].to = String(value);
      if (idx === 0 && fld === 'expr') fp.expr = String(value);
      return n;
    }
    if (parts[0] === 'letter') { n.letters = n.letters || {}; n.letters[parts[1]] = +value; return n; }
    if (parts[0] === 'fns') { n.fns[parts[1]][parts[2]] = parts[2] === 'expr' ? value : parts[2] === 'visible' ? !!value : +value; return n; }
    if (parts[0] === 'show') { n.show[parts[1]] = !!value; return n; }
    if (parts[0] === 'iv') {
      var f = parts[1];
      if (f === 'instr') {
        n.iv.instr = value;
        if (key === 'taxes') { n.iv.kind = 'unit'; }
        if (key === 'ceil') { n.iv.price = value === 'ceil' ? 30 : 70; }
        if (key === 'mono') { if (value === 'ceil') n.iv.price = 40; if (value === 'floor') n.iv.price = 70; }
      } else if (f === 'kind' || f === 'side') n.iv[f] = value;
      else if (f === 'ghost') n.iv.ghost = !!value;
      else n.iv[f] = +value;
      return n;
    }
    if (id === 'reset.tc') { var ini = LIVE.costs.init(); n.fns = ini.fns; return n; }
    if (parts[0] === 'par') {
      var g = parts[1];
      n.par[g] = (g === 'mode') ? value : (g === 'secant') ? !!value : +value;
      return n;
    }
    return n;
  };

  /* Перетаскивание ручки: координаты уже в единицах модели. */
  E.drag = function (key, ms, handleId, x, y) {
    var n = clone(ms);
    if (key === 'taxes' && handleId === 'wedge') {
      var d = fnOf(n, 'D'), s = fnOf(n, 'S');
      if (!d.ok || !s.ok) return n;
      var q = Math.max(0.01, x), D = d.f(q), S = s.f(q);
      var tax = n.iv.instr === 'tax';
      if (n.iv.kind === 'unit') n.iv.rate = E.clamp(Math.round(Math.abs(D - S)), 0, 150);
      else {
        var r;
        if (tax) r = n.iv.kind === 'vat' ? D / S - 1 : 1 - S / D;
        else r = n.iv.kind === 'vat' ? 1 - D / S : S / D - 1;
        n.iv.pct = E.clamp(Math.round(r * 100), 0, tax && n.iv.kind === 'exc' ? 90 : 100);
      }
      return n;
    }
    if ((key === 'ceil' || key === 'mono' || key === 'costs') && handleId === 'price') {
      if (key === 'costs') n.par.P = E.clamp(Math.round(y * 2) / 2, 0, 50);
      else n.iv.price = E.clamp(Math.round(y), 0, 100);
      return n;
    }
    if (key === 'mono' && handleId === 'quota') { n.iv.quota = E.clamp(Math.round(x), 0, 100); return n; }
    if (key === 'm-tangent' && (handleId === 'x0top' || handleId === 'x0bot')) { n.par.x0 = E.clamp(Math.round(x * 100) / 100, -5, 5); return n; }
    return n;
  };

  /* Короткое описание состояния — для «Продолжить», «Недавних» и ссылки. */
  E.summary = function (key, ms) {
    if (!ms || ms.schematic) return '';
    var parts = [];
    Object.keys(ms.fns || {}).forEach(function (k) {
      if (!String(ms.fns[k].expr || '').trim()) return;
      if (key === 'costs' && (ms.par || {}).mode !== 'curves' && k !== 'TC') return;
      if (key === 'costs' && (ms.par || {}).mode === 'curves' && k === 'TC') return;
      var pcs = ms.fns[k].pieces;
      if (pcs && pcs.length) { parts.push(k + ': ' + pcs.length + ' ' + (pcs.length === 1 ? 'кусок' : pcs.length < 5 ? 'куска' : 'кусков') + ' (' + pcs.map(function (pc) { return E.prettyExpr(E.splitEq(pc.expr).rhs.trim()); }).join('; ') + ')'); return; }
      parts.push(k + ' = ' + E.prettyExpr(E.splitEq(ms.fns[k].expr).rhs.trim()));
    });
    if (ms.iv) {
      if (ms.iv.instr === 'tax' || ms.iv.instr === 'sub') parts.push((ms.iv.instr === 'tax' ? 'налог ' : 'субсидия ') + (ms.iv.kind && ms.iv.kind !== 'unit' ? ms.iv.pct + ' %' : (ms.iv.instr === 'tax' ? 't = ' : 's = ') + ms.iv.rate));
      if (ms.iv.instr === 'ceil' || ms.iv.instr === 'floor') parts.push((ms.iv.instr === 'ceil' ? 'потолок ' : 'пол ') + ms.iv.price);
      if (ms.iv.instr === 'quota') parts.push('квота ' + ms.iv.quota);
    }
    if (ms.par && ms.par.P !== undefined && key === 'costs') parts.push('P = ' + ms.par.P);
    if (ms.par && ms.par.x0 !== undefined) parts.push('x₀ = ' + fmt(ms.par.x0));
    return parts.join(', ');
  };
  E.shareUrl = function (key, ms) {
    var q = [];
    if (ms && ms.fns) Object.keys(ms.fns).forEach(function (k) {
      var ex = String(ms.fns[k].expr || '').replace(/\s+/g, '');
      if (!ex) return;
      if (key === 'costs' && ((ms.par || {}).mode === 'curves') === (k === 'TC')) return;
      var pcs = ms.fns[k].pieces;
      if (pcs && pcs.length) { q.push(k + '=pw(' + pcs.map(function (pc) { return [pc.expr, pc.from, pc.to].map(function (t) { return String(t === undefined || t === null ? '' : t).replace(/\s+/g, ''); }).join('|'); }).join(';') + ')'); return; }
      q.push(k + '=' + ex);
    });
    if (ms && ms.iv) { if (ms.iv.instr) q.push('iv=' + ms.iv.instr); if (ms.iv.rate !== undefined && (ms.iv.instr === 'tax' || ms.iv.instr === 'sub')) q.push('t=' + ms.iv.rate); if (ms.iv.price !== undefined && (ms.iv.instr === 'ceil' || ms.iv.instr === 'floor')) q.push('p=' + ms.iv.price); }
    if (ms && ms.par && ms.par.P !== undefined && key === 'costs') q.push('P=' + ms.par.P);
    return 'weconomics.ai/calc2/' + key + (q.length ? '#' + q.join('&') : '');
  };
})();
