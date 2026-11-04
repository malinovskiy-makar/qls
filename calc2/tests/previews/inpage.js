/* Превью модели из записи при рисовании (ADR 0141). Подключается в страницу
   калькулятора приборами: make_previews.mjs (собирает previews.json) и
   tex/ci_quick.mjs (сторож свежести сверяет отпечаток).

   window.__PV.build(tokens) — на открытой модели: бумажный прогон и опись,
   как у выгрузки .tex (texEnterPaper + texCapture), и из описи — маленькая
   векторная картинка:
     берём    кривые (path), закрашенные области (path и rect с заливкой),
              сплошные отрезки длиннее засечки, оси тонкой линией;
     бросаем  подписи и числа (text), точки (dot), пунктирные отрезки
              (проекции), сетку, деления, легенду, бледные служебные линии.
   Цвета — НЕ числами, а именами токенов темы (tokens: светлое значение
   бумажного прогона → имя токена). Несопоставленный цвет — в unknown.

   Отпечаток fp считается по содержимому превью В ЕДИНИЦАХ МОДЕЛИ (окно
   панели, вид предмета, цвет, толщина, узлы с шагом 0,1 % размаха окна), а
   не в пикселях листа: пиксели зависят от ширины подписей, то есть от
   шрифтов машины, а сторож бежит в CI на другой системе. */
(function () {
  'use strict';
  const SEG_MIN = 10;        // px листа: отрезок короче — засечка деления
  const OP_MIN = 0.2;        // бледнее — служебная линия (разделитель панелей)
  const DP_TOL = 0.45;       // px листа: допуск упрощения ломаной
  const Q = 1000;            // шаг узла в отпечатке — 1/Q размаха окна
  const BAND_W = 4;          // px листа: отрезок толще — полоса, рисуется закраской

  function cyrb53(str) {
    let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
    for (let i = 0; i < str.length; i++) {
      const ch = str.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761); h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return (h2 >>> 0).toString(16).padStart(8, '0') + (h1 >>> 0).toString(16).padStart(8, '0');
  }

  // Отрезок p–q, обрезанный прямоугольником (Лян — Барски); null — снаружи.
  function clipSeg(p, q, r) {
    let t0 = 0, t1 = 1;
    const dx = q[0] - p[0], dy = q[1] - p[1];
    const P = [-dx, dx, -dy, dy], Qv = [p[0] - r[0], r[2] - p[0], p[1] - r[1], r[3] - p[1]];
    for (let i = 0; i < 4; i++) {
      if (Math.abs(P[i]) < 1e-12) { if (Qv[i] < 0) return null; continue; }
      const t = Qv[i] / P[i];
      if (P[i] < 0) { if (t > t1) return null; if (t > t0) t0 = t; }
      else { if (t < t0) return null; if (t < t1) t1 = t; }
    }
    return [[p[0] + t0 * dx, p[1] + t0 * dy], [p[0] + t1 * dx, p[1] + t1 * dy]];
  }
  // Ломаная, обрезанная прямоугольником: куски внутри.
  function clipLine(pts, r) {
    const runs = []; let cur = null;
    for (let i = 0; i + 1 < pts.length; i++) {
      const c = clipSeg(pts[i], pts[i + 1], r);
      if (!c) { cur = null; continue; }
      const same = cur && Math.abs(cur[cur.length - 1][0] - c[0][0]) < 1e-6 && Math.abs(cur[cur.length - 1][1] - c[0][1]) < 1e-6;
      if (!same) { cur = [c[0]]; runs.push(cur); }
      cur.push(c[1]);
    }
    return runs.filter(r2 => r2.length >= 2);
  }
  // Многоугольник, обрезанный прямоугольником (Сазерленд — Ходжман).
  function clipPoly(pts, r) {
    const edges = [
      [p => p[0] >= r[0], (a, b) => { const t = (r[0] - a[0]) / (b[0] - a[0]); return [r[0], a[1] + t * (b[1] - a[1])]; }],
      [p => p[0] <= r[2], (a, b) => { const t = (r[2] - a[0]) / (b[0] - a[0]); return [r[2], a[1] + t * (b[1] - a[1])]; }],
      [p => p[1] >= r[1], (a, b) => { const t = (r[1] - a[1]) / (b[1] - a[1]); return [a[0] + t * (b[0] - a[0]), r[1]]; }],
      [p => p[1] <= r[3], (a, b) => { const t = (r[3] - a[1]) / (b[1] - a[1]); return [a[0] + t * (b[0] - a[0]), r[3]]; }],
    ];
    let out = pts.slice();
    for (const [inside, cross] of edges) {
      const inp = out; out = [];
      for (let i = 0; i < inp.length; i++) {
        const a = inp[(i + inp.length - 1) % inp.length], b = inp[i];
        if (inside(b)) { if (!inside(a)) out.push(cross(a, b)); out.push(b); }
        else if (inside(a)) out.push(cross(a, b));
      }
      if (!out.length) break;
    }
    return out;
  }
  // Упрощение ломаной (Дуглас — Пекер) в пикселях листа.
  function dp(pts, tol) {
    if (pts.length <= 2) return pts.slice();
    const keep = new Uint8Array(pts.length); keep[0] = keep[pts.length - 1] = 1;
    const st = [[0, pts.length - 1]];
    while (st.length) {
      const [a, b] = st.pop();
      const [x1, y1] = pts[a], [x2, y2] = pts[b];
      const L = Math.hypot(x2 - x1, y2 - y1);
      let best = -1, bi = -1;
      for (let i = a + 1; i < b; i++) {
        const [x0, y0] = pts[i];
        const d = L < 1e-9 ? Math.hypot(x0 - x1, y0 - y1) : Math.abs((x2 - x1) * (y1 - y0) - (x1 - x0) * (y2 - y1)) / L;
        if (d > best) { best = d; bi = i; }
      }
      if (best > tol) { keep[bi] = 1; st.push([a, bi], [bi, b]); }
    }
    return pts.filter((_, i) => keep[i]);
  }
  const n1 = (v) => { const s = (Math.round(v * 10) / 10).toFixed(1); return s.endsWith('.0') ? s.slice(0, -2) : s; };
  const dOf = (runs, ox, oy, closed) => runs.map(r => 'M' + r.map(p => n1(p[0] - ox) + ' ' + n1(p[1] - oy)).join('L') + (closed ? 'Z' : '')).join('');
  const wOf = (w) => Math.max(1, Math.min(5, Math.round(w * 0.8 * 10) / 10));

  function build(tokens) {
    const unknown = [];
    const tok = (hex, what) => {
      const t = tokens[String(hex || '').toUpperCase()];
      if (!t) unknown.push(what + ' #' + hex);
      return t || '?';
    };
    // всё — внутри бумажного прогона: шкалы панелей после выхода уже экранные
    const leave = texEnterPaper();
    try { return assemble(texCapture(), tok, unknown); } finally { leave(); }
  }

  function assemble(L, tok, unknown) {
    const fills = [], strokes = [], axes = [], fpParts = [];
    // шкалы бумажного прогона: опись их из списка убирает, берём у реестра панелей
    const live = STATE.panels || [];
    const rects = L.panels.map((p, i) => ({ p, mx: live[i].mx, my: live[i].my, r: [p.x0, p.y0, p.x1, p.y1] }));
    let texts = 0;
    rects.forEach((R, pi) => {
      const p = R.p;
      const sx = Math.abs(p.xd[1] - p.xd[0]) || 1, sy = Math.abs(p.yd[1] - p.yd[0]) || 1;
      const qx = (v) => Math.round((v - p.xd[0]) / sx * Q), qy = (v) => Math.round((v - p.yd[0]) / sy * Q);
      const qpts = (pts) => pts.map(q => qx(q[0]) + ',' + qy(q[1])).join(' ');
      const px = (q) => [R.mx(q[0]), R.my(q[1])];
      fpParts.push('P' + pi + ':' + [p.xd[0], p.xd[1], p.yd[0], p.yd[1]].map(v => +v.toPrecision(6)).join(','));
      // оси: тонкой линией, без делений и стрелок
      [['x', p.ax.xLine], ['y', p.ax.yLine]].forEach(([n, a]) => {
        if (!a) return;
        const c = clipSeg([a.px[0], a.px[1]], [a.px[2], a.px[3]], R.r);
        if (!c) return;
        axes.push({ run: c, s: tok(a.st.color, 'ось') });
        fpParts.push('A' + n + ':' + a.st.color + ':' + qpts([a.a, a.b]));
      });
      p.items.forEach(it => {
        if (it.kind === 'text') { texts++; return; }
        if (it.kind === 'dot') return;
        if (it.kind === 'seg') {
          if (it.role === 'grid' || it.role === 'axes' || it.arrow) return;
          const st = it.st; if (!st || st.dash || st.op < OP_MIN) return;
          const [x1, y1, x2, y2] = it.px;
          if (Math.hypot(x2 - x1, y2 - y1) < SEG_MIN) return;
          const c = clipSeg([x1, y1], [x2, y2], R.r); if (!c) return;
          if (st.w >= BAND_W) {
            /* Толстая полупрозрачная полоса (дефицит на оси, импорт по мировой
               цене) — по смыслу закраска, а не линия: идёт прямоугольником
               своей толщины в пикселях листа. */
            const [a, b] = c, L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
            const nx = -(b[1] - a[1]) / L * st.w / 2, ny = (b[0] - a[0]) / L * st.w / 2;
            fills.push({ z: it.z, poly: [[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny]], f: tok(st.color, 'полоса'), fo: st.op });
          } else strokes.push({ z: it.z, runs: [c], s: tok(st.color, 'отрезок'), w: wOf(st.w), o: st.op });
          fpParts.push('S:' + st.color + ':' + st.w + ':' + st.op.toFixed(2) + ':' + qpts([it.a, it.b]));
          return;
        }
        if (it.kind === 'rect') {
          const fl = it.fl; if (!fl) return;
          const a = px(it.a), b = px(it.b);
          const box = [Math.max(Math.min(a[0], b[0]), R.r[0]), Math.max(Math.min(a[1], b[1]), R.r[1]), Math.min(Math.max(a[0], b[0]), R.r[2]), Math.min(Math.max(a[1], b[1]), R.r[3])];
          if (!(box[2] > box[0] && box[3] > box[1])) return;
          const f = fl.hatch ? { t: tok(fl.color, 'штриховка'), o: 0.22 } : { t: tok(fl.color, 'заливка'), o: fl.op };
          fills.push({ z: it.z, box, f: f.t, fo: f.o });
          fpParts.push('R:' + (fl.hatch || fl.color) + ':' + fl.op.toFixed(2) + ':' + qpts([it.a, it.b]));
          return;
        }
        if (it.kind === 'path') {
          const pts = (it.pts || []).map(px);
          if (pts.length < 2) return;
          if (it.fl) {
            const poly = clipPoly(pts, R.r);
            if (poly.length >= 3) {
              const f = it.fl.hatch ? { t: tok(it.fl.color, 'штриховка'), o: 0.22 } : { t: tok(it.fl.color, 'заливка'), o: it.fl.op };
              fills.push({ z: it.z, poly: dp(poly.concat([poly[0]]), DP_TOL).slice(0, -1), f: f.t, fo: f.o });
            }
          }
          if (it.st && !it.fl) {
            const runs = clipLine(pts, R.r).map(r => dp(r, DP_TOL));
            if (runs.length) strokes.push({ z: it.z, runs, s: tok(it.st.color, 'кривая'), w: wOf(it.st.w), o: it.st.op, da: it.st.dash ? it.st.dash.map(v => n1(v * 0.8)).join(' ') : '' });
          }
          fpParts.push('C:' + (it.st ? it.st.color + ':' + it.st.w + ':' + (it.st.dash ? 'd' : '') + ':' + it.st.op.toFixed(2) : '-') + ':' +
            (it.fl ? (it.fl.hatch || it.fl.color) + ':' + it.fl.op.toFixed(2) : '-') + ':' + qpts(it.pts || []));
        }
      });
    });
    // окно превью — общий прямоугольник полей всех панелей
    const ox = Math.min.apply(null, rects.map(R => R.r[0])), oy = Math.min.apply(null, rects.map(R => R.r[1]));
    const W = Math.max.apply(null, rects.map(R => R.r[2])) - ox, H = Math.max.apply(null, rects.map(R => R.r[3])) - oy;
    // соседние полосы одной заливки (экстремумы «Максимумов и минимумов») — одним путём
    const fillPaths = [];
    fills.sort((a, b) => a.z - b.z).forEach(f => {
      const d = f.box ? 'M' + n1(f.box[0] - ox) + ' ' + n1(f.box[1] - oy) + 'H' + n1(f.box[2] - ox) + 'V' + n1(f.box[3] - oy) + 'H' + n1(f.box[0] - ox) + 'Z'
        : dOf([f.poly], ox, oy, true);
      const last = fillPaths[fillPaths.length - 1];
      if (last && last.f === f.f && last.fo === f.fo) last.d += d;
      else fillPaths.push({ d, f: f.f, fo: f.fo });
    });
    const axisPaths = axes.map(a => ({ d: dOf([a.run], ox, oy, false), s: a.s, w: 1.2, o: 0.6 }));
    const strokePaths = strokes.sort((a, b) => a.z - b.z).map(s => {
      const o = { d: dOf(s.runs, ox, oy, false), s: s.s, w: s.w };
      if (s.o < 0.995) o.o = Math.round(s.o * 100) / 100;
      if (s.da) o.da = s.da;
      return o;
    });
    const out = [];
    fillPaths.forEach(f => out.push({ d: f.d, f: f.f, fo: Math.round(f.fo * 100) / 100 }));
    axisPaths.forEach(a => out.push(a));
    strokePaths.forEach(s => out.push(s));
    return {
      vb: '0 0 ' + n1(W) + ' ' + n1(H), p: out, fp: cyrb53(fpParts.join('\n')), parts: window.__PV_DEBUG ? fpParts : undefined,
      stats: { texts, unknown, panels: rects.length },
    };
  }

  // Только отпечаток (сторож свежести): тот же обход, без сборки картинки.
  function fp(tokens) { return build(tokens).fp; }

  window.__PV = { build, fp };
})();
