/* Рисователь чертежей к сгенерированным задачам Econ Rush.
   ОБЩИЙ модуль: его подключают и страница игры (разбор ошибок), и
   HTML-предпросмотр генераторов (manage.py preview_generated). Один
   рисователь на обе поверхности — иначе предпросмотр показывал бы
   преподавателю не то, что увидит игрок.

   Рисователь не знает ни про монополию, ни про КПВ: сервер присылает
   декларативную геометрию (game/generators/_figure.py) — линии, заливки,
   точки и засечки в координатах ЗАДАЧИ, здесь они пересчитываются в
   пиксели. Добавить график новому архетипу = вернуть геометрию из
   figure(), этот файл не трогать.

   Наружу отдаётся одна функция — window.drawFigure(fig) → DOM-узел
   (или null, если чертежа нет). Всё остальное спрятано в замыкании.
   Стили — game/static/game/figure.css (пара к этому файлу). */
(function () {
  'use strict';
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var FIG_ROLES = {
    d: 'd', s: 's', mr: 'mr', mc: 'mc', tax: 'tax', dwl: 'dwl',
    reg: 'reg', ghost: 'ghost',
    cs: 'd', ps: 's',            /* излишки — цветом своей стороны рынка */
    ppf: 'd', feasible: 'd'
  };
  var FIG_W = 460, FIG_H = 320;
  var FIG_PAD = { l: 44, r: 16, t: 16, b: 52 };  // b — с запасом под
                                                 // опущенные подписи засечек

  function figColor(role) {
    return 'var(--gfig-' + (FIG_ROLES[role] || 'ghost') + ')';
  }

  function svgEl(name, attrs) {
    var e = document.createElementNS(SVG_NS, name);
    for (var k in attrs) { if (attrs[k] !== null) e.setAttribute(k, attrs[k]); }
    return e;
  }

  /* Подпись вида 'Q_m' / 'P^*' — в SVG нет KaTeX, но индекс и звёздочку
     собрать вручную дешевле, чем тащить рендерер ради двух символов. */
  function figLabel(text, x, y, color, anchor, size) {
    var t = svgEl('text', { x: x, y: y, fill: color, 'font-size': size || 11,
                            'text-anchor': anchor || 'start',
                            'font-family': 'inherit', 'font-weight': 600 });
    var m = /^([^_^]+)(?:_(.+)|\^(.+))?$/.exec(text);
    if (!m) { t.textContent = text; return t; }
    var base = svgEl('tspan', {});
    base.textContent = m[1];
    t.appendChild(base);
    if (m[2] || m[3]) {
      var sub = svgEl('tspan', { 'font-size': (size || 11) * 0.75,
                                 dy: m[2] ? 3 : -4 });
      sub.textContent = m[2] || m[3];
      t.appendChild(sub);
    }
    return t;
  }

  function drawFigure(fig) {
    if (!fig || !fig.xmax || !fig.ymax) return null;
    var box = document.createElement('div');
    box.className = 'mi-figure';
    var svg = svgEl('svg', { viewBox: '0 0 ' + FIG_W + ' ' + FIG_H,
                             role: 'img' });
    svg.setAttribute('aria-label', 'Чертёж к задаче: ' + (fig.kind || ''));
    var x0 = FIG_PAD.l, y0 = FIG_H - FIG_PAD.b;
    var w = FIG_W - FIG_PAD.l - FIG_PAD.r, h = FIG_H - FIG_PAD.t - FIG_PAD.b;
    function px(x) { return x0 + (x / fig.xmax) * w; }
    function py(y) { return y0 - (y / fig.ymax) * h; }

    // заливки — под кривыми, иначе перекроют их
    (fig.areas || []).forEach(function (a) {
      var pts = a.points.map(function (p) { return px(p[0]) + ',' + py(p[1]); });
      svg.appendChild(svgEl('polygon', {
        points: pts.join(' '), fill: figColor(a.role), 'fill-opacity': 0.16,
        stroke: 'none' }));
    });

    (fig.lines || []).forEach(function (ln) {
      svg.appendChild(svgEl('line', {
        x1: px(ln.from[0]), y1: py(ln.from[1]),
        x2: px(ln.to[0]), y2: py(ln.to[1]),
        stroke: figColor(ln.role),
        'stroke-width': ln.dash ? 1.2 : 2.4,
        'stroke-dasharray': ln.dash ? '4 4' : null,
        'stroke-linecap': 'round' }));
      /* Подпись — на самой кривой (≈2/3 длины), а не у её конца: у спроса и
         MR конец лежит на оси Q, и там подписи сбивались в кучу с засечками
         и точкой конкурентного исхода. На середине же кривые заведомо
         разведены — их там и различают глазом. */
      if (ln.label) {
        var t = 0.66;
        var lx = px(ln.from[0] + (ln.to[0] - ln.from[0]) * t);
        var ly = py(ln.from[1] + (ln.to[1] - ln.from[1]) * t);
        lx = Math.min(Math.max(lx + 7, x0 + 4), FIG_W - FIG_PAD.r - 4);
        ly = Math.min(Math.max(ly - 6, FIG_PAD.t + 9), y0 - 4);
        svg.appendChild(figLabel(ln.label, lx, ly, figColor(ln.role),
                                 'start', 12));
      }
    });

    // оси поверх заливок, но под точками
    svg.appendChild(svgEl('line', { x1: x0, y1: y0, x2: px(fig.xmax), y2: y0,
                                    stroke: 'var(--gfig-ink)',
                                    'stroke-width': 1.4 }));
    svg.appendChild(svgEl('line', { x1: x0, y1: y0, x2: x0, y2: FIG_PAD.t,
                                    stroke: 'var(--gfig-ink)',
                                    'stroke-width': 1.4 }));

    /* Засечки. Соседние засечки на одной оси часто стоят вплотную (Q_0 = 70
       и Q_1 = 76 — это норма, а не редкий случай), и подписи налезают друг
       на друга. Поэтому при близости к уже поставленной подписи опускаем
       текущую на строку ниже. */
    var usedX = [], usedY = [];
    (fig.marks || []).forEach(function (mk) {
      var isX = mk.axis === 'x';
      var cx = isX ? px(mk.at) : x0, cy = isX ? y0 : py(mk.at);
      svg.appendChild(svgEl('line', {
        x1: isX ? cx : cx - 4, y1: cy,
        x2: cx, y2: isX ? cy + 4 : cy,
        stroke: 'var(--gfig-ink)', 'stroke-width': 1.4 }));
      var used = isX ? usedX : usedY;
      var here = isX ? cx : cy;
      var row = 0;
      while (used.some(function (u) {
        return u.row === row && Math.abs(u.at - here) < (isX ? 30 : 13);
      })) { row++; }
      used.push({ at: here, row: row });
      var drop = row * (isX ? 22 : 11);
      var num = svgEl('text', {
        x: isX ? cx : cx - 6, y: isX ? cy + 15 + drop : cy + 3.5,
        fill: 'var(--gfig-soft)', 'font-size': 10,
        'text-anchor': isX ? 'middle' : 'end', 'font-family': 'inherit' });
      num.textContent = mk.at;
      svg.appendChild(num);
      // подпись величины: у оси X — правее числа, у оси Y — внутрь поля
      // (слева от оси стоит само число, туда её ставить нельзя)
      if (mk.label) {
        svg.appendChild(figLabel(mk.label, isX ? cx + 14 : cx + 5,
                                 isX ? cy + 15 + drop : cy - 5,
                                 'var(--gfig-ink)', 'start', 10));
      }
    });

    (fig.points || []).forEach(function (p) {
      svg.appendChild(svgEl('circle', {
        cx: px(p.x), cy: py(p.y), r: 4, fill: figColor(p.role),
        stroke: 'var(--gfig-canvas)', 'stroke-width': 1.5 }));
      if (p.label) {
        svg.appendChild(figLabel(p.label, px(p.x) + 7, py(p.y) - 6,
                                 'var(--gfig-ink)', 'start', 12));
      }
    });

    // подписи осей
    var xl = svgEl('text', { x: px(fig.xmax), y: y0 + 46,
                             fill: 'var(--gfig-soft)', 'font-size': 11,
                             'text-anchor': 'end', 'font-family': 'inherit' });
    xl.textContent = fig.xlabel || '';
    svg.appendChild(xl);
    // подпись оси Y — вдоль оси, снизу вверх: поворот вокруг точки на
    // середине левого поля, text-anchor middle центрирует надпись на ней
    var yl = svgEl('text', { x: 0, y: 0, fill: 'var(--gfig-soft)',
                             'font-size': 11, 'text-anchor': 'middle',
                             'font-family': 'inherit',
                             transform: 'translate(11,' +
                                        (FIG_PAD.t + h / 2) + ') rotate(-90)' });
    yl.textContent = fig.ylabel || '';
    svg.appendChild(yl);

    box.appendChild(svg);
    return box;
  }

  window.drawFigure = drawFigure;
})();
