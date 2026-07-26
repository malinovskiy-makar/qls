/* Рисователь чертежей Econ Rush.

   ОБЩИЙ модуль. Его подключают: страница игры (карточка вопроса режима
   «График» и разбор ошибок), HTML-предпросмотр генераторов
   (manage.py preview_generated) и предпросмотр сюжетов
   (manage.py preview_figure_audit). Один рисователь на все поверхности —
   иначе предпросмотр показывал бы преподавателю не то, что увидит игрок.
   Это уже проверено на практике: второй рисователь «только для превью»
   расходится с боевым за одну сессию.

   Рисователь не знает ни про монополию, ни про КПВ: сервер присылает
   декларативную геометрию (game/generators/_figure.py) — линии, заливки,
   точки, засечки и выноски в координатах ЗАДАЧИ, здесь они пересчитываются
   в пиксели. Добавить график = вернуть геометрию из figure(), этот файл не
   трогать.

   ⚠️ РИСОВАТЕЛЬ НИЧЕГО НЕ ПРОВЕРЯЕТ И НИЧЕГО НЕ ЧИНИТ. В режиме «График»
   игроку показывают ЧУЖОЕ РЕШЕНИЕ, в котором может быть ошибка: точка стоит
   не там, заштрихована не та область, число не сходится. Если рисователь
   «поправит» такую геометрию — вопрос лишится ответа. Поэтому здесь нет ни
   одной проверки экономического смысла и ни одного подтягивания координат
   к «правильным». Единственное, что рисователь двигает сам, — ПОДПИСИ
   (чтобы не налезали друг на друга), и это оформление, а не данные.

   Наружу отдаётся одна функция — window.drawFigure(fig) → DOM-узел
   (или null, если чертежа нет). Всё остальное спрятано в замыкании.
   Стили — game/static/game/figure.css (пара к этому файлу). */
(function () {
  'use strict';
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var FIG_ROLES = {
    d: 'd', s: 's', mr: 'mr', mc: 'mc', tax: 'tax', dwl: 'dwl',
    reg: 'reg', ghost: 'ghost', atc: 'atc', zone: 'zone',
    cs: 'd', ps: 's',            /* излишки — цветом своей стороны рынка */
    ppf: 'd', feasible: 'd'
  };
  var FIG_W = 520, FIG_H = 360;
  var FIG_PAD = { l: 48, r: 18, t: 18, b: 54 };  // b — с запасом под
                                                 // опущенные подписи засечек
  /* Минимальный кегль подписи. Ниже 11px чертёж не читается на телефоне,
     а именно там его и будут разглядывать. */
  var FS_MIN = 11;
  var FS_LABEL = 12;      // подписи точек и кривых
  var FS_TICK = 11;       // числа у засечек

  function figColor(role) {
    return 'var(--gfig-' + (FIG_ROLES[role] || 'ghost') + ')';
  }

  function svgEl(name, attrs) {
    var e = document.createElementNS(SVG_NS, name);
    for (var k in attrs) { if (attrs[k] !== null) e.setAttribute(k, attrs[k]); }
    return e;
  }

  /* ---------- подписи ----------------------------------------------------
     Подпись бывает вида 'Q_m', 'P^*', 'E_0 (40; 60)', '|E| = 1'. Индекс
     относится ТОЛЬКО к следующему за '_' символу (или к группе в фигурных
     скобках) — иначе координаты «(40; 60)» целиком уехали бы в нижний
     индекс, что и случалось в первой версии. */
  function splitLabel(text) {
    var runs = [], buf = '', i = 0;
    function flush() { if (buf) { runs.push({ t: buf, k: 'b' }); buf = ''; } }
    while (i < text.length) {
      var ch = text.charAt(i);
      if ((ch === '_' || ch === '^') && i + 1 < text.length) {
        flush();
        var kind = ch === '_' ? 'sub' : 'sup';
        i++;
        if (text.charAt(i) === '{') {
          var close = text.indexOf('}', i);
          if (close === -1) { close = text.length; }
          runs.push({ t: text.slice(i + 1, close), k: kind });
          i = close + 1;
        } else {
          runs.push({ t: text.charAt(i), k: kind });
          i++;
        }
      } else { buf += ch; i++; }
    }
    flush();
    return runs;
  }

  function figLabel(text, x, y, color, anchor, size, cls) {
    var fs = Math.max(size || FS_LABEL, FS_MIN);
    var t = svgEl('text', { x: x, y: y, fill: color, 'font-size': fs,
                            'text-anchor': anchor || 'start',
                            'class': cls || null,
                            'font-family': 'inherit', 'font-weight': 600 });
    splitLabel(text).forEach(function (run) {
      if (run.k === 'b') {
        var base = svgEl('tspan', {});
        base.textContent = run.t;
        t.appendChild(base);
        return;
      }
      var sm = svgEl('tspan', { 'font-size': Math.round(fs * 0.75),
                                dy: run.k === 'sub' ? 3 : -4 });
      sm.textContent = run.t;
      t.appendChild(sm);
      /* вернуть базовую линию на место, иначе следующий кусок уедет */
      var back = svgEl('tspan', { dy: run.k === 'sub' ? -3 : 4 });
      back.textContent = '';
      t.appendChild(back);
    });
    return t;
  }

  /* Ширина надписи ОЦЕНИВАЕТСЯ, а не измеряется: getComputedTextLength у
     ещё не вставленного в документ узла возвращает 0, а вставлять ради
     замера — значит перерисовывать чертёж дважды. Оценка с запасом:
     замер в браузере даёт ≈0,50 em на знак для наших подписей, берём 0,56 —
     лучше отодвинуть подпись на лишний пиксель, чем наложить её на кривую.
     Настоящие метрики проверяет node-тест figure_draw.mjs. */
  function textWidth(text, fs) {
    var n = 0;
    splitLabel(text).forEach(function (r) {
      n += r.t.length * (r.k === 'b' ? 1 : 0.75);
    });
    return n * fs * 0.56;
  }

  /* ---------- геометрия для раскладки подписей ---------- */
  function rectsOverlap(a, b) {
    return !(a.x1 <= b.x0 || b.x1 <= a.x0 || a.y1 <= b.y0 || b.y1 <= a.y0);
  }

  function overlapArea(a, b) {
    var w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
    var h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
    return (w > 0 && h > 0) ? w * h : 0;
  }

  /* Пересекает ли отрезок прямоугольник (кривая под подписью). */
  function segHitsRect(p, q, r) {
    if ((p.x < r.x0 && q.x < r.x0) || (p.x > r.x1 && q.x > r.x1)
        || (p.y < r.y0 && q.y < r.y0) || (p.y > r.y1 && q.y > r.y1)) {
      return false;
    }
    if ((p.x >= r.x0 && p.x <= r.x1 && p.y >= r.y0 && p.y <= r.y1)
        || (q.x >= r.x0 && q.x <= r.x1 && q.y >= r.y0 && q.y <= r.y1)) {
      return true;
    }
    var dx = q.x - p.x, dy = q.y - p.y;
    var corners = [[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]];
    var sign = 0;
    for (var i = 0; i < 4; i++) {
      var cross = dx * (corners[i][1] - p.y) - dy * (corners[i][0] - p.x);
      var s = cross > 0 ? 1 : (cross < 0 ? -1 : 0);
      if (s === 0) { return true; }
      if (sign === 0) { sign = s; } else if (s !== sign) { return true; }
    }
    return false;
  }

  /* Внутри ли точка многоугольника — лучом вправо. Метод не зависит от
     направления обхода вершин: по часовой и против дают один ответ. */
  function pointInPoly(x, y, poly) {
    var inside = false;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
      if ((yi > y) !== (yj > y)
          && x < (xj - xi) * (y - yi) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }

  /* Центр тяжести многоугольника. abs() у площади — чтобы обход против
     часовой стрелки не давал зеркальный центр. */
  function polyCentroid(poly) {
    var a = 0, cx = 0, cy = 0;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var f = poly[j][0] * poly[i][1] - poly[i][0] * poly[j][1];
      a += f; cx += (poly[j][0] + poly[i][0]) * f;
      cy += (poly[j][1] + poly[i][1]) * f;
    }
    if (Math.abs(a) < 1e-9) {          // вырожденный многоугольник
      var sx = 0, sy = 0;
      poly.forEach(function (p) { sx += p[0]; sy += p[1]; });
      return [sx / poly.length, sy / poly.length];
    }
    return [cx / (3 * a), cy / (3 * a)];
  }

  function labelRect(x, y, w, fs, anchor) {
    var x0 = anchor === 'end' ? x - w : (anchor === 'middle' ? x - w / 2 : x);
    /* 0,95 и 0,30 — не «на глаз»: столько занимают подъём и свес шрифта
       интерфейса на 12px (замерено getBBox в figure_draw.mjs). При меньших
       числах рисователь считал подпись ниже, чем она есть, и та задевала
       кривую снизу. */
    return { x0: x0, x1: x0 + w, y0: y - fs * 0.95, y1: y + fs * 0.30 };
  }

  function drawFigure(fig) {
    if (!fig || !fig.xmax || !fig.ymax) return null;
    var box = document.createElement('div');
    box.className = 'mi-figure';
    var svg = svgEl('svg', { viewBox: '0 0 ' + FIG_W + ' ' + FIG_H,
                             preserveAspectRatio: 'xMidYMid meet',
                             role: 'img' });
    svg.setAttribute('aria-label', 'Чертёж к задаче: ' + (fig.kind || ''));
    var x0 = FIG_PAD.l, y0 = FIG_H - FIG_PAD.b;
    var w = FIG_W - FIG_PAD.l - FIG_PAD.r, h = FIG_H - FIG_PAD.t - FIG_PAD.b;
    function px(x) { return x0 + (x / fig.xmax) * w; }
    function py(y) { return y0 - (y / fig.ymax) * h; }
    var frame = { x0: x0, x1: FIG_W - FIG_PAD.r, y0: FIG_PAD.t, y1: y0 };
    /* Холст шире поля осей: в поля можно немного зайти подписью, за холст —
       нельзя, оттуда её обрежет viewBox. Низ оставляем засечкам и подписи
       оси X. */
    var canvas = { x0: 2, x1: FIG_W - 2, y0: 11, y1: y0 + 12 };

    /* Занятые подписями прямоугольники и отрезки кривых — под них потом
       подбирается свободная сторона у подписей точек. */
    var busy = [], strokes = [];

    /* ---------- заливки: под кривыми, иначе перекроют их ---------- */
    (fig.areas || []).forEach(function (a) {
      var poly = a.points.map(function (p) { return [px(p[0]), py(p[1])]; });
      var pts = poly.map(function (p) { return p[0] + ',' + p[1]; }).join(' ');
      /* Контурная область: заливка ЗАМЕТНО прозрачнее контура. Без этого
         область съедает кривые, которые под ней, и игрок не видит, по чему
         она построена. */
      svg.appendChild(svgEl('polygon', {
        points: pts, fill: figColor(a.role),
        'fill-opacity': a.outline ? 0.25 : 0.16, stroke: 'none' }));
      if (a.outline) {
        svg.appendChild(svgEl('polygon', {
          points: pts, fill: 'none', stroke: figColor(a.role),
          'stroke-width': 1.6, 'stroke-linejoin': 'round' }));
      }
    });

    /* ---------- кривые ---------- */
    function pushStroke(ax, ay, bx, by) {
      strokes.push([{ x: ax, y: ay }, { x: bx, y: by }]);
    }

    function placeCurveLabel(text, lx, ly, role) {
      lx = Math.min(Math.max(lx, x0 + 4), FIG_W - FIG_PAD.r - 4);
      ly = Math.min(Math.max(ly, FIG_PAD.t + 9), y0 - 4);
      var r = labelRect(lx, ly, textWidth(text, FS_LABEL), FS_LABEL, 'start');
      busy.push(r);
      svg.appendChild(figLabel(text, lx, ly, figColor(role), 'start',
                               FS_LABEL, 'fig-lbl-curve'));
    }

    (fig.lines || []).forEach(function (ln) {
      var ax = px(ln.from[0]), ay = py(ln.from[1]);
      var bx = px(ln.to[0]), by = py(ln.to[1]);
      svg.appendChild(svgEl('line', {
        x1: ax, y1: ay, x2: bx, y2: by,
        stroke: figColor(ln.role),
        'stroke-width': ln.dash ? 1.2 : 2.4,
        'stroke-dasharray': ln.dash ? '4 4' : null,
        'stroke-linecap': 'round' }));
      if (!ln.dash) { pushStroke(ax, ay, bx, by); }
      /* Подпись — на самой кривой (≈2/3 длины), а не у её конца: у спроса и
         MR конец лежит на оси Q, и там подписи сбивались в кучу с засечками
         и точкой конкурентного исхода. */
      if (ln.label) {
        var t = 0.66;
        placeCurveLabel(ln.label, ax + (bx - ax) * t + 7,
                        ay + (by - ay) * t - 6, ln.role);
      }
    });

    /* ---------- ломаные (совместная КПВ и подобное) ---------- */
    (fig.polylines || []).forEach(function (pl) {
      var pts = pl.points.map(function (p) { return px(p[0]) + ',' + py(p[1]); });
      svg.appendChild(svgEl('polyline', {
        points: pts.join(' '), fill: 'none', stroke: figColor(pl.role),
        'stroke-width': pl.dash ? 1.2 : 2.4,
        'stroke-dasharray': pl.dash ? '4 4' : null,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
      for (var i = 1; i < pl.points.length; i++) {
        if (!pl.dash) {
          pushStroke(px(pl.points[i - 1][0]), py(pl.points[i - 1][1]),
                     px(pl.points[i][0]), py(pl.points[i][1]));
        }
      }
      if (pl.label && pl.points.length) {
        var mid = pl.points[Math.floor(pl.points.length / 2)];
        placeCurveLabel(pl.label, px(mid[0]) + 8, py(mid[1]) - 8, pl.role);
      }
    });

    /* ---------- оси: поверх заливок, но под точками ---------- */
    svg.appendChild(svgEl('line', { x1: x0, y1: y0, x2: px(fig.xmax), y2: y0,
                                    stroke: 'var(--gfig-ink)',
                                    'stroke-width': 1.4 }));
    svg.appendChild(svgEl('line', { x1: x0, y1: y0, x2: x0, y2: FIG_PAD.t,
                                    stroke: 'var(--gfig-ink)',
                                    'stroke-width': 1.4 }));

    /* ---------- засечки ----------
       Соседние засечки на одной оси часто стоят вплотную (Q_0 = 70 и
       Q_1 = 76 — это норма, а не редкий случай), и подписи налезают друг на
       друга. При близости к уже поставленной опускаем текущую на строку. */
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
        return u.row === row && Math.abs(u.at - here) < (isX ? 32 : 14);
      })) { row++; }
      used.push({ at: here, row: row });
      var drop = row * (isX ? 22 : 12);
      var num = svgEl('text', {
        x: isX ? cx : cx - 6, y: isX ? cy + 16 + drop : cy + 3.5,
        fill: 'var(--gfig-soft)', 'font-size': FS_TICK, 'class': 'fig-tick',
        'text-anchor': isX ? 'middle' : 'end', 'font-family': 'inherit' });
      num.textContent = mk.at;
      svg.appendChild(num);
      // подпись величины: у оси X — правее числа, у оси Y — внутрь поля
      // (слева от оси стоит само число, туда её ставить нельзя)
      if (mk.label) {
        var lw = textWidth(mk.label, FS_TICK);
        var lx = isX ? cx + 14 : cx + 5;
        var ly = isX ? cy + 16 + drop : cy - 5;
        if (!isX) {
          /* Цены на оси P часто стоят вплотную (P_b = 65, P_0 = 60,
             P_s = 55 — это ровно сюжет про налог), и опускать подпись
             «на строку ниже» тут некуда: строка ниже — это соседняя цена.
             Поэтому при столкновении подпись уходит ВПРАВО, вдоль своей
             засечки, а не вниз. */
          var mrect = labelRect(lx, ly, lw, FS_TICK, 'start');
          var guard = 0;
          while (guard < 8 && busy.some(function (b) {
            return rectsOverlap(mrect, b);
          })) {
            lx += lw + 8;
            mrect = labelRect(lx, ly, lw, FS_TICK, 'start');
            guard++;
          }
          busy.push(mrect);
        }
        svg.appendChild(figLabel(mk.label, lx, ly, 'var(--gfig-ink)', 'start',
                                 FS_TICK, 'fig-lbl-mark'));
      }
    });

    /* ---------- выноски с числом ----------
       Число обязано стоять у своей области. Помещается внутрь — пишем
       внутрь; не помещается — выносим наружу и ведём хвостик. Решение
       принимает рисователь: только он знает ширину надписи в пикселях. */
    (fig.callouts || []).forEach(function (c) {
      var poly = c.points.map(function (p) { return [px(p[0]), py(p[1])]; });
      var ctr = polyCentroid(poly);
      var tw = textWidth(c.text, FS_LABEL);
      var inner = labelRect(ctr[0], ctr[1] + FS_LABEL * 0.3, tw, FS_LABEL,
                            'middle');
      var fits = pointInPoly(inner.x0, inner.y0, poly)
              && pointInPoly(inner.x1, inner.y0, poly)
              && pointInPoly(inner.x0, inner.y1, poly)
              && pointInPoly(inner.x1, inner.y1, poly);
      if (fits) {
        busy.push(inner);
        svg.appendChild(figLabel(c.text, ctr[0], ctr[1] + FS_LABEL * 0.3,
                                 figColor(c.role), 'middle', FS_LABEL,
                                 'fig-callout fig-callout-in'));
        return;
      }
      /* наружу: вправо-вверх от центра области, а если там край — влево */
      var ox = ctr[0] + 26, oy = ctr[1] - 18, anchor = 'start';
      if (ox + tw > frame.x1 - 2) { ox = ctr[0] - 26; anchor = 'end'; }
      oy = Math.min(Math.max(oy, frame.y0 + FS_LABEL), frame.y1 - 2);
      var outer = labelRect(ox, oy, tw, FS_LABEL, anchor);
      var guard = 0;
      while (guard < 6 && busy.some(function (b) {
        return rectsOverlap(outer, b);
      })) { oy -= FS_LABEL + 3; outer = labelRect(ox, oy, tw, FS_LABEL, anchor);
            guard++; }
      svg.appendChild(svgEl('line', {
        x1: ctr[0], y1: ctr[1], x2: ox + (anchor === 'end' ? -3 : 3),
        y2: oy + 2, stroke: figColor(c.role), 'stroke-width': 1,
        'class': 'fig-callout-tail', 'stroke-dasharray': '3 3' }));
      busy.push(outer);
      svg.appendChild(figLabel(c.text, ox, oy, figColor(c.role), anchor,
                               FS_LABEL, 'fig-callout fig-callout-out'));
    });

    /* ---------- точки и их подписи ----------
       Подпись отодвигается в СВОБОДНУЮ сторону: из восьми кандидатов
       (четыре стороны × два выноса) выбираем тот, где меньше всего
       наложений на уже нарисованное. Без этого подписи слипаются — ровно
       это и случилось 16 июля, когда Q_0 = 200 и Q_1 = 216 встали друг на
       друга. */
    /* Восемь сторон света: четырёх мало — равновесие лежит СРАЗУ НА ДВУХ
       кривых, и все четыре угла вокруг него заняты. */
    var CAND = [
      { dx: 1, dy: -1, a: 'start' }, { dx: -1, dy: -1, a: 'end' },
      { dx: 1, dy: 1, a: 'start' },  { dx: -1, dy: 1, a: 'end' },
      { dx: 1, dy: 0, a: 'start' },  { dx: -1, dy: 0, a: 'end' },
      { dx: 0, dy: -1, a: 'middle' }, { dx: 0, dy: 1, a: 'middle' }
    ];
    (fig.points || []).forEach(function (p) {
      var cx = px(p.x), cy = py(p.y);
      svg.appendChild(svgEl('circle', {
        cx: cx, cy: cy, r: 4, fill: figColor(p.role), 'class': 'fig-pt',
        stroke: 'var(--gfig-canvas)', 'stroke-width': 1.5 }));
      if (!p.label && !p.coords) { return; }
      var text = p.label || '';
      if (p.coords) {
        text = (text ? text + ' ' : '') + '(' + p.x + '; ' + p.y + ')';
      }
      var tw = textWidth(text, FS_LABEL);
      var best = null;
      /* Выносы от 10 до 124 пикселей. Ближние предпочтительнее (штраф ri),
         но в углу чертежа четыре точки с координатными подписями рядом не
         разложить вовсе: ближние места кончаются, и подписи начинают
         слипаться. Тогда подпись уезжает далеко, а к точке от неё ведётся
         тонкая выноска — так делают все нормальные рисователи графиков,
         и это честнее, чем оставить надпись поверх кривой. */
      [10, 20, 32, 46, 62, 82, 104, 128].forEach(function (r, ri) {
        CAND.forEach(function (dir, idx) {
          var lx = cx + dir.dx * r;
          var ly = cy + (dir.dy < 0 ? -r
                       : (dir.dy > 0 ? r + FS_LABEL * 0.7 : FS_LABEL * 0.3));
          var rect = labelRect(lx, ly, tw, FS_LABEL, dir.a);
          // порядок сторон и близость — мягкие предпочтения, а не запреты
          var cost = idx * 0.6 + ri * 2;
          /* Выход за поле осей — штраф ПО ВЕЛИЧИНЕ вылета, а не запрет:
             в углу чертежа подписи иначе некуда девать, и жёсткий запрет
             заставлял их слипаться друг с другом — а это хуже, чем на два
             пикселя зайти на поле. Запрет остаётся только на выход за сам
             холст: оттуда подпись просто пропадёт. */
          cost += 20 * (Math.max(0, frame.x0 - rect.x0)
                      + Math.max(0, rect.x1 - frame.x1)
                      + Math.max(0, frame.y0 - rect.y0)
                      + Math.max(0, rect.y1 - frame.y1));
          if (rect.x0 < canvas.x0 || rect.x1 > canvas.x1
              || rect.y0 < canvas.y0 || rect.y1 > canvas.y1) { cost += 8000; }
          busy.forEach(function (b) {
            var ov = overlapArea(rect, b);
            // штраф с «порогом»: любое, даже крохотное, наложение подписей
            // должно быть дороже любого мягкого предпочтения по стороне
            if (ov > 0) { cost += 2000 + ov; }
          });
          strokes.forEach(function (sg) {
            if (segHitsRect(sg[0], sg[1], rect)) { cost += 900; }
          });
          if (!best || cost < best.cost) {
            best = { cost: cost, x: lx, y: ly, anchor: dir.a, rect: rect,
                     far: r >= 82 };
          }
        });
      });
      busy.push(best.rect);
      if (best.far) {
        // подпись уехала далеко — ведём к ней выноску от точки
        svg.appendChild(svgEl('line', {
          x1: cx, y1: cy,
          x2: best.anchor === 'end' ? best.rect.x1 + 3
            : (best.anchor === 'middle' ? (best.rect.x0 + best.rect.x1) / 2
                                        : best.rect.x0 - 3),
          y2: best.y - 3, stroke: 'var(--gfig-soft)', 'stroke-width': 0.9,
          'class': 'fig-lbl-tail', 'stroke-dasharray': '3 3' }));
      }
      svg.appendChild(figLabel(text, best.x, best.y, 'var(--gfig-ink)',
                               best.anchor, FS_LABEL, 'fig-lbl-point'));
    });

    /* ---------- подписи осей ---------- */
    var xl = svgEl('text', { x: px(fig.xmax), y: y0 + 48,
                             fill: 'var(--gfig-soft)', 'font-size': FS_MIN,
                             'text-anchor': 'end', 'font-family': 'inherit' });
    xl.textContent = fig.xlabel || '';
    svg.appendChild(xl);
    // подпись оси Y — вдоль оси, снизу вверх: поворот вокруг точки на
    // середине левого поля, text-anchor middle центрирует надпись на ней
    var yl = svgEl('text', { x: 0, y: 0, fill: 'var(--gfig-soft)',
                             'font-size': FS_MIN, 'text-anchor': 'middle',
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
