/* Карта тем и тегов — /catalog/map/
 *
 * Свой движок на canvas 2D: перспективная проекция, силовая раскладка в трёх
 * измерениях, попадание курсором по экранным координатам. Библиотек нет —
 * вся отрисовка это 372 круга и 425 отрезков, three.js или d3-force дали бы
 * только вес.
 *
 * Порядок частей:
 *   1. Данные, палитра, раскладка
 *   2. Камера и проекция
 *   3. Отрисовка
 *   4. Взаимодействие
 *   5. Обучение при первом заходе
 */
(function () {
'use strict';

var root = document.getElementById('tmap');
if (!root) return;

var canvas = document.getElementById('tmap-canvas');
var ctx = canvas.getContext('2d');
var wrap = document.getElementById('tmap-canvas-wrap');

var W = 0, H = 0, DPR = 1;
var nodes = [], links = [], groups = [];
var byId = {}, themeList = [], tagsOfTheme = {}, nearOf = {};
var ready = false;

var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;


/* ═══════════════════════════════════════════════════════════════════════
   ЧАСТЬ 1. ДАННЫЕ, ПАЛИТРА, РАСКЛАДКА
   ═══════════════════════════════════════════════════════════════════════ */

/* Генератор случайных чисел с фиксированным зерном.
   Карта обязана быть одинаковой между перезагрузками: иначе человек,
   запомнивший «макроблок справа снизу», после F5 ищет его заново. */
function makeRandom(seed) {
  var s = seed >>> 0;
  return function () {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/* ── Цвет ──────────────────────────────────────────────────────────────
   Внутри раздела темы разводятся оттенком и светлотой от базового цвета.
   ⚠️ ЛОВУШКА, ИЗ-ЗА КОТОРОЙ КАРТА ТЕРЯЛА КАДРЫ: строку цвета нельзя
   собирать на каждый узел каждый кадр — 372 разбора CSS-цвета за кадр
   стоят дороже всей остальной отрисовки. Поэтому цвет узла переводится в
   rgb ОДИН раз при чтении токенов, и заранее строится массив готовых
   строк 'rgba(r,g,b,a)' по ступеням прозрачности; в кадре только
   индексация по номеру ступени. */

var ALPHA_STEPS = 15;              /* ступени прозрачности: 0 … 1 */

function hexToRgb(hex) {
  hex = String(hex).trim();
  var m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (m) {
    var v = parseInt(m[1], 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  m = /rgba?\(([^)]+)\)/i.exec(hex);
  if (m) {
    var p = m[1].split(',');
    return [parseInt(p[0], 10) || 0, parseInt(p[1], 10) || 0, parseInt(p[2], 10) || 0];
  }
  return [128, 128, 128];
}

function rgbToHsl(rgb) {
  var r = rgb[0] / 255, g = rgb[1] / 255, b = rgb[2] / 255;
  var mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  var h = 0, s = 0, l = (mx + mn) / 2;
  var d = mx - mn;
  if (d > 0) {
    s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    if (mx === r)      h = ((g - b) / d + (g < b ? 6 : 0));
    else if (mx === g) h = ((b - r) / d + 2);
    else               h = ((r - g) / d + 4);
    h *= 60;
  }
  return [h, s * 100, l * 100];
}

function hslToRgb(h, s, l) {
  h = ((h % 360) + 360) % 360; s = Math.max(0, Math.min(100, s)) / 100;
  l = Math.max(0, Math.min(100, l)) / 100;
  var c = (1 - Math.abs(2 * l - 1)) * s;
  var x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  var m = l - c / 2, r = 0, g = 0, b = 0;
  if (h < 60)       { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; }
  else if (h < 300) { r = x; b = c; }
  else              { r = c; b = x; }
  return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
}

function relLum(rgb) {
  var a = rgb.map(function (v) {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
}

function contrast(a, b) {
  var la = relLum(a), lb = relLum(b);
  var hi = Math.max(la, lb), lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

/* Дотяжка светлоты до порога контраста.
   ⚠️ ЭТО НЕ КОСТЫЛЬ ВМЕСТО ПРАВКИ ТОКЕНА, А ПОЧИНКА САМОГО РАЗВЕДЕНИЯ.
   Все семь цветов разделов проходят порог с запасом (3,94..9,64). Ломает
   их производная операция: сдвиг тона на ±12° уводит янтарь в жёлтый, а
   жёлтый при той же светлоте гораздо ярче — и на светлом фоне шесть
   узлов падали до 2,16:1 при норме 3:1. Зажим по светлоте это не чинит
   (проверено: результат не меняется), потому что виноват тон. Поэтому
   после разведения светлота подтягивается в безопасную сторону, пока
   контраст к фону не достигнет порога. Считается один раз при чтении
   токенов, не в кадре. */
var MIN_NODE_CONTRAST = 3.0;

function pullToContrast(h, s, l, bg, dark) {
  var step = dark ? 1 : -1;        /* на тёмном фоне светлеем, на светлом темнеем */
  var rgb = hslToRgb(h, s, l);
  for (var i = 0; i < 90; i++) {
    if (contrast(rgb, bg) >= MIN_NODE_CONTRAST) return rgb;
    var next = l + step;
    if (next < 0 || next > 100) return rgb;
    l = next;
    rgb = hslToRgb(h, s, l);
  }
  return rgb;
}

function makeShades(rgb) {
  /* 15 готовых строк по ступеням прозрачности — в кадре только индексация. */
  var out = new Array(ALPHA_STEPS);
  for (var i = 0; i < ALPHA_STEPS; i++) {
    var a = i / (ALPHA_STEPS - 1);
    out[i] = 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',' + a.toFixed(3) + ')';
  }
  return out;
}

function shadeIndex(a) {
  var i = Math.round(a * (ALPHA_STEPS - 1));
  return i < 0 ? 0 : (i > ALPHA_STEPS - 1 ? ALPHA_STEPS - 1 : i);
}

/* Палитра страницы: цвета из токенов + всё производное. */
var PAL = {};

function readPalette() {
  var cs = getComputedStyle(document.documentElement);
  var dark = document.documentElement.getAttribute('data-theme') === 'dark';
  var bgRaw = cs.getPropertyValue('--bg') || (dark ? '#10141c' : '#f5f5f3');
  var bg = hexToRgb(bgRaw);

  PAL.dark = dark;
  PAL.bg = bg;
  PAL.bgCss = 'rgb(' + bg[0] + ',' + bg[1] + ',' + bg[2] + ')';
  PAL.text = hexToRgb(cs.getPropertyValue('--text') || (dark ? '#e7e9ef' : '#1a1a1a'));
  PAL.text2 = hexToRgb(cs.getPropertyValue('--text2') || (dark ? '#a7aebc' : '#5b6472'));
  PAL.accent = hexToRgb(cs.getPropertyValue('--accent') || (dark ? '#FF4D94' : '#BE185D'));
  PAL.accentCss = 'rgb(' + PAL.accent.join(',') + ')';
  PAL.textCss = 'rgb(' + PAL.text.join(',') + ')';
  PAL.text2Css = 'rgb(' + PAL.text2.join(',') + ')';
  PAL.accentShades = makeShades(PAL.accent);
  PAL.borderShades = makeShades(hexToRgb(dark ? '#8e96a4' : '#687180'));

  /* Подложка под подписью — цвет холста, чтобы текст не перечёркивался
     рёбрами (дефект Б). Прозрачность 0.88 задаётся здесь же. */
  PAL.plate = 'rgba(' + bg[0] + ',' + bg[1] + ',' + bg[2] + ',0.88)';

  /* Цвет каждой темы и её тегов. */
  groups.forEach(function (g) {
    var base = cs.getPropertyValue('--g-' + g.k);
    var rgb = hexToRgb(base && base.trim() ? base : (dark ? g.cd : g.cl));
    var hsl = rgbToHsl(rgb);
    var n = g.themes.length;
    var mid = (n - 1) / 2;
    var half = mid > 0 ? mid : 1;
    g.rgb = rgb;
    g.css = 'rgb(' + rgb.join(',') + ')';
    g.themes.forEach(function (num, idx) {
      var k = (idx - mid) / half;
      var h = hsl[0] + k * 12;
      var l = Math.max(26, Math.min(78, hsl[2] + k * 10));
      var themeRgb = pullToContrast(h, hsl[1], l, bg, dark);
      /* Тег — тот же цвет со сдвигом светлоты в сторону фона: иначе на
         белом холсте светлые теги пропадают, а на тёмном тонут. */
      var lTag = Math.max(26, Math.min(78, l + (dark ? 8 : -6)));
      var tagRgb = pullToContrast(h, hsl[1], lTag, bg, dark);
      var themeNode = byId['t' + num];
      if (!themeNode) return;
      themeNode.rgb = themeRgb;
      themeNode.css = 'rgb(' + themeRgb.join(',') + ')';
      themeNode.shades = makeShades(themeRgb);
      var tagShades = makeShades(tagRgb);
      var tagCss = 'rgb(' + tagRgb.join(',') + ')';
      (tagsOfTheme[num] || []).forEach(function (t) {
        t.rgb = tagRgb; t.css = tagCss; t.shades = tagShades;
      });
    });
  });
}

/* ── Раскладка ───────────────────────────────────────────────────────── */

var R_SPHERE = 470;          /* радиус сферы тем */
var Y_SQUASH = 0.78;         /* сплющивание по вертикали */
var REP = 1450;              /* сила отталкивания */
var REP_CUT2 = 640000;       /* дальше 800 не считаем */
var K_TREE = 0.055;          /* пружина тема→тег */
var K_CROSS = 0.006, L_CROSS = 300;
var CENTER_PULL = 0.0016;
var DAMP = 0.82;

var alpha = 1;
var themeAffinity = [];      /* пары тем: {a, b, L, K, both} */

function tagRadius(count) {
  /* Венец тегов: у темы с 5 тегами ~74, с 18 — ~145. */
  return 46 + 5.5 * count;
}

function fibSphere(i, n, rnd) {
  /* Точка на сфере Фибоначчи. Теги вокруг темы раскладываются ИМЕННО так,
     а не случайно: случайное размещение сбивает их в комки, и подписи
     налезают друг на друга ещё до всякой симуляции. */
  var y = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
  var r = Math.sqrt(Math.max(0, 1 - y * y));
  var phi = i * 2.399963229728653;      /* золотой угол */
  return [Math.cos(phi) * r, y, Math.sin(phi) * r];
}

function seedLayout() {
  var rnd = makeRandom(20260829);
  var themeCount = themeList.length;

  themeList.forEach(function (th, i) {
    var p = fibSphere(i, themeCount, rnd);
    th.x = p[0] * R_SPHERE;
    th.y = p[1] * R_SPHERE * Y_SQUASH;
    th.z = p[2] * R_SPHERE;
    th.vx = th.vy = th.vz = 0;

    var tags = tagsOfTheme[th.n] || [];
    var R = tagRadius(tags.length);
    th.tagR = R;
    tags.forEach(function (tag, j) {
      var q = fibSphere(j, tags.length, rnd);
      /* Небольшой поворот венца, чтобы соседние темы не смотрели
         одинаково; берётся из того же зерна — карта остаётся стабильной. */
      var jitter = 0.85 + rnd() * 0.3;
      tag.x = th.x + q[0] * R * jitter;
      tag.y = th.y + q[1] * R * Y_SQUASH * jitter;
      tag.z = th.z + q[2] * R * jitter;
      tag.vx = tag.vy = tag.vz = 0;
    });
  });

  /* Матрица родства тем: сколько перекрёстных связей между их тегами.
     Родственные темы стягиваются, и макроблок собирается вместе. */
  var w = {};
  links.forEach(function (ln) {
    if (ln.k !== 'cross') return;
    var a = byId[ln.s].n, b = byId[ln.t].n;
    if (a === b) return;
    var key = a < b ? a + ':' + b : b + ':' + a;
    w[key] = (w[key] || 0) + 1;
  });
  themeAffinity = [];

  /* ⚠️ РОДСТВО ПО СВЯЗЯМ И ПРИНАДЛЕЖНОСТЬ К РАЗДЕЛУ — ЭТО РАЗНЫЕ ВЕЩИ,
     И ОДНОГО РОДСТВА МАЛО. Замер: из 82 перекрёстных связей 56 соединяют
     темы РАЗНЫХ разделов и только 26 — темы одного. То есть притяжение по
     числу общих связей тянет разделы друг в друга, а не собирает их: без
     второго слагаемого медиана расстояний внутри раздела отличалась от
     медианы между разделами всего на 16 % — то есть цветные блоки на
     карте взглядом не читались.
     Поэтому пар два вида: родство по связям (ниже) и принадлежность к
     одному разделу (здесь). Первое сближает смежные темы, второе собирает
     макроблок в макроблок. */
  themeList.forEach(function (a, i) {
    themeList.forEach(function (b, j) {
      if (j <= i || a.g !== b.g) return;
      themeAffinity.push({ a: a, b: b, L: 300, K: 0.010, both: 3 });
      a.affinity = a.affinity || {};
      b.affinity = b.affinity || {};
      a.affinity[b.id] = 3;
      b.affinity[a.id] = 3;
    });
  });

  Object.keys(w).forEach(function (key) {
    var parts = key.split(':');
    var a = byId['t' + parts[0]], b = byId['t' + parts[1]];
    if (!a || !b) return;
    var c = w[key];
    themeAffinity.push({
      a: a, b: b,
      L: 640 - 55 * Math.min(c, 8),
      K: 0.003 * Math.min(c, 6),
      both: Math.max(2, 9 - c)
    });
    /* Пара запоминает пониженное отталкивание: родственные темы не должны
       расталкиваться с той же силой, что чужие. */
    a.affinity = a.affinity || {};
    b.affinity = b.affinity || {};
    a.affinity[b.id] = Math.max(2, 9 - c);
    b.affinity[a.id] = Math.max(2, 9 - c);
  });
}

function step() {
  var i, j, n = nodes.length, a, b;

  /* Отталкивание всех пар. */
  for (i = 0; i < n; i++) {
    a = nodes[i];
    for (j = i + 1; j < n; j++) {
      b = nodes[j];
      var dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
      var d2 = dx * dx + dy * dy + dz * dz;
      if (d2 > REP_CUT2 || d2 < 0.0001) continue;
      var both = 1;
      if (a.k === 'theme' && b.k === 'theme') {
        both = (a.affinity && a.affinity[b.id]) || 9;
      }
      var f = REP * both / d2;
      var d = Math.sqrt(d2);
      var ux = dx / d, uy = dy / d, uz = dz / d;
      a.vx -= ux * f; a.vy -= uy * f; a.vz -= uz * f;
      b.vx += ux * f; b.vy += uy * f; b.vz += uz * f;
    }
  }

  /* Пружины. */
  for (i = 0; i < links.length; i++) {
    var ln = links[i];
    a = byId[ln.s]; b = byId[ln.t];
    var ddx = b.x - a.x, ddy = b.y - a.y, ddz = b.z - a.z;
    var dist = Math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) || 0.0001;
    var L, K;
    if (ln.k === 'tree') {
      L = (a.k === 'theme' ? a.tagR : b.tagR) || 90;
      K = K_TREE;
    } else {
      L = L_CROSS; K = K_CROSS;
      /* Перекрёстная нить работает только на растяжение: сжимать чужие
         теги друг к другу она не должна, иначе рвёт венцы своих тем. */
      if (dist < L) continue;
    }
    var force = (dist - L) * K;
    var fx = (ddx / dist) * force, fy = (ddy / dist) * force, fz = (ddz / dist) * force;
    a.vx += fx; a.vy += fy; a.vz += fz;
    b.vx -= fx; b.vy -= fy; b.vz -= fz;
  }

  /* Родство тем. */
  for (i = 0; i < themeAffinity.length; i++) {
    var pair = themeAffinity[i];
    a = pair.a; b = pair.b;
    var px = b.x - a.x, py = b.y - a.y, pz = b.z - a.z;
    var pd = Math.sqrt(px * px + py * py + pz * pz) || 0.0001;
    var pf = (pd - pair.L) * pair.K;
    a.vx += (px / pd) * pf; a.vy += (py / pd) * pf; a.vz += (pz / pd) * pf;
    b.vx -= (px / pd) * pf; b.vy -= (py / pd) * pf; b.vz -= (pz / pd) * pf;
  }

  /* Центростремительная и затухание.
     ⚠️ ПО ВЕРТИКАЛИ ТЯНЕМ СИЛЬНЕЕ, ЧЕМ ВБОК. Холст широкий и низкий
     (типично 990×554), а силы сами по себе дают граф «столбиком»: замер
     показал разлёт 169 px по горизонтали при доступных 411 и 232 по
     вертикали при доступных 231 — то есть высота забита под завязку, а
     половина ширины пустует, и карта выглядит узкой колонкой посреди
     пустого поля. Сплющивание по Y кладёт корпус в ту форму, которая у
     экрана есть. Стартовая раскладка сплющена той же логикой (Y_SQUASH). */
  for (i = 0; i < n; i++) {
    a = nodes[i];
    a.vx -= a.x * CENTER_PULL * alpha;
    a.vy -= a.y * CENTER_PULL * alpha * 3.4;
    a.vz -= a.z * CENTER_PULL * alpha;
    a.vx *= DAMP; a.vy *= DAMP; a.vz *= DAMP;
    a.x += a.vx; a.y += a.vy; a.z += a.vz;
  }
}

function settle(iterations) {
  alpha = 1;
  for (var i = 0; i < iterations; i++) {
    step();
    alpha *= 0.995;
  }
  alpha = 0.2;
}

/* Диагностика раскладки: медианное расстояние между темами внутри раздела
   и между разделами. Если числа равны — притяжение по родству не работает. */
function layoutStats() {
  var inside = [], between = [];
  for (var i = 0; i < themeList.length; i++) {
    for (var j = i + 1; j < themeList.length; j++) {
      var a = themeList[i], b = themeList[j];
      var d = Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);
      (a.g === b.g ? inside : between).push(d);
    }
  }
  function median(arr) {
    arr.sort(function (p, q) { return p - q; });
    var m = arr.length >> 1;
    return arr.length % 2 ? arr[m] : (arr[m - 1] + arr[m]) / 2;
  }
  return { inside: median(inside), between: median(between),
           insideN: inside.length, betweenN: between.length };
}


/* ═══════════════════════════════════════════════════════════════════════
   ЧАСТЬ 2. КАМЕРА И ПРОЕКЦИЯ
   ═══════════════════════════════════════════════════════════════════════ */

var DIST = 1240, FOCAL = 900;
var ZOOM_MIN = 0.45, ZOOM_MAX = 4.5;

var cam = {
  yaw: 0.35, pitch: -0.22,
  zoom: 1, zoomTarget: 1,
  tx: 0, ty: 0, tz: 0,               /* точка, вокруг которой вращаемся */
  goalX: null, goalY: null, goalZ: null, goalZoom: null
};

/* Синусы и косинусы считаются ОДИН раз за кадр, а не на каждый узел. */
var CY = 1, SY = 0, CP = 1, SP = 0;

/* ⚠️ МАСШТАБ ОБЗОРА — ЭТО НЕ ЕДИНИЦА, А ВПИСАННЫЙ В ХОЛСТ РАЗМЕР.
   При голом zoom = 1 из 372 узлов за кадром оставалось 133, и девять тем
   из 29 человек при открытии просто не видел — а первое, что обещает
   карта и первый шаг обучения, это «весь корпус целиком». Поэтому за
   100 % принят масштаб, при котором граф помещается в холст с полями;
   пределы 0,45..4,5 и кнопка «⟲» отсчитываются от него же.
   Считается один раз после раскладки, по СТАРТОВОМУ ракурсу: минимум по
   восьми поворотам ужимал карту вчетверо (при развороте на 90° узлы
   подходят ближе к камере и разлёт на экране растёт), и весь корпус
   оказывался комком в середине пустого холста. Поворот человек делает
   сам и сам же видит, что уезжает за край, — а вот открыть карту он
   должен на всём корпусе сразу. */
var fitScale = 1;

function computeFit() {
  var saveYaw = cam.yaw, savePitch = cam.pitch;
  var saveTx = cam.tx, saveTy = cam.ty, saveTz = cam.tz;
  var saveZoom = cam.zoom;
  cam.tx = cam.ty = cam.tz = 0;
  cam.zoom = 1;
  var marginX = 84, marginY = 46;      /* поля под подписи тем */
  camPrepare();
  var maxDx = 1, maxDy = 1;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    var ax = n.x * CY + n.z * SY, az = -n.x * SY + n.z * CY;
    var ay = n.y * CP - az * SP, pz = n.y * SP + az * CP + DIST;
    if (pz < 60) continue;
    var s = FOCAL / pz;
    maxDx = Math.max(maxDx, Math.abs(ax * s));
    maxDy = Math.max(maxDy, Math.abs(ay * s));
  }
  var best = Math.min((W / 2 - marginX) / maxDx, (H / 2 - marginY) / maxDy);
  cam.yaw = saveYaw; cam.pitch = savePitch;
  cam.tx = saveTx; cam.ty = saveTy; cam.tz = saveTz;
  cam.zoom = saveZoom;
  fitScale = Math.max(0.15, Math.min(1, best));
}

function camPrepare() {
  CY = Math.cos(cam.yaw); SY = Math.sin(cam.yaw);
  CP = Math.cos(cam.pitch); SP = Math.sin(cam.pitch);
}

/* Проекция пишет В ПОЛЯ УЗЛА и ничего не возвращает: 372 новых объекта за
   кадр — это мусор для сборщика и просадка на ровном месте. */
function project() {
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    var x = n.x - cam.tx, y = n.y - cam.ty, z = n.z - cam.tz;
    var ax = x * CY + z * SY, az = -x * SY + z * CY;
    var ay = y * CP - az * SP, pz = y * SP + az * CP + DIST;
    if (pz < 60) { n.pz = -1; continue; }      /* за камерой */
    var s = FOCAL / pz * cam.zoom * fitScale;
    n.px = W / 2 + ax * s;
    n.py = H / 2 + ay * s;
    n.ps = s;
    n.pz = pz;
  }
}

/* Обратное преобразование экранной точки в мировую на глубине DIST —
   нужно, чтобы зумить К ТОЧКЕ ПОД КУРСОРОМ, а не к центру экрана. */
function screenToWorld(sx, sy, depth) {
  var s = FOCAL / depth * cam.zoom * fitScale;
  var ax = (sx - W / 2) / s, ay = (sy - H / 2) / s;
  var az = (depth - DIST + ay * SP * 0) / 1;   /* глубину берём заданной */
  /* Разворачиваем поворот: сначала pitch, потом yaw. */
  var y = ay * CP + (az - DIST) * SP;
  var azz = -ay * SP + (az - DIST) * CP;
  var x = ax * CY - azz * SY;
  var z = ax * SY + azz * CY;
  return [x + cam.tx, y + cam.ty, z + cam.tz];
}

function nodeRadius(n) {
  /* Размер узла — от числа задач: крупная тема видна крупной. */
  if (n.r0 === undefined) {
    n.r0 = n.k === 'theme'
      ? 7.4 + Math.log(1 + (n.c || 0)) / 1.15
      : 2.5 + Math.log(1 + (n.c || 0)) / 1.9;
  }
  return Math.max(1.2, n.r0 * n.ps);
}

/* Попадание курсором.
   ⚠️ ЧИТАЕТ ТЕ ЖЕ ПОЛЯ, ЧТО ПИШЕТ ПРОЕКЦИЯ (px, py, ps, pz). Если
   переименовать поля в рендере и забыть здесь, клики молча перестают
   работать — без единой ошибки в консоли. */
function hitTest(mx, my) {
  var best = null, bestD = 10;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    if (n.pz < 0) continue;
    var d = Math.hypot(n.px - mx, n.py - my) - Math.max(3, n.r0 * n.ps);
    if (d < bestD) { bestD = d; best = n; }
  }
  return best;
}


/* ═══════════════════════════════════════════════════════════════════════
   ЧАСТЬ 3. ОТРИСОВКА
   ═══════════════════════════════════════════════════════════════════════ */

/* Состояние подсветки. */
var picked = {};             /* id → true: выбранные теги и темы          */
var hoverNode = null;        /* узел под курсором                         */
var focusTheme = null;       /* тема, у которой раскрыт список тегов      */
var searchHits = null;       /* null = поиск пуст; иначе объект id → true */

var order = [];              /* порядок отрисовки по глубине              */
var lastThemeBoxes = [];     /* занятые места последнего кадра (для замеров) */
var lastThemeFrom = 0;       /* с какого индекса в нём начинаются темы      */

/* Приглушение: на белом фоне гасить надо СЛАБЕЕ, иначе карта исчезает. */
function dimFloor(kind) {
  if (kind === 'theme') return 0.5;            /* тема не тонет никогда   */
  return PAL.dark ? 0.26 : 0.36;
}

function isLit(n) {
  /* Что считается подсвеченным при текущем выборе и наведении. */
  if (searchHits) return !!searchHits[n.id];
  if (!litSet) return true;
  return !!litSet[n.id];
}

var litSet = null;           /* null = ничего не выделено, всё яркое      */
var litNear = null;          /* второй, тихий уровень: смежные теги       */
var litEdges = null;         /* id рёбер, которые рисуются дорогой        */

function edgeKey(a, b) { return a < b ? a + '|' + b : b + '|' + a; }

function rebuildHighlight() {
  var any = false, k;
  for (k in picked) { if (picked[k]) { any = true; break; } }
  if (!any && !hoverNode) { litSet = litNear = litEdges = null; return; }

  litSet = {}; litNear = {}; litEdges = {};

  var seeds = [];
  for (k in picked) if (picked[k]) seeds.push(byId[k]);
  if (hoverNode) seeds.push(hoverNode);

  seeds.forEach(function (n) {
    if (!n) return;
    if (n.k === 'theme') {
      /* Тема целиком: она сама, все её теги и все дороги до них. */
      litSet[n.id] = true;
      (tagsOfTheme[n.n] || []).forEach(function (t) {
        litSet[t.id] = true;
        litEdges[edgeKey(n.id, t.id)] = true;
      });
    } else {
      litSet[n.id] = true;
      var parent = byId['t' + n.n];
      if (parent) {
        litSet[parent.id] = true;
        litEdges[edgeKey(parent.id, n.id)] = true;
      }
      /* Смежные теги — второй, тихий уровень. */
      (nearOf[n.id] || []).forEach(function (otherId) {
        litNear[otherId] = true;
        litEdges[edgeKey(n.id, otherId)] = true;
      });
    }
  });
}

/* ── Подписи ─────────────────────────────────────────────────────────── */

var LABEL_TAG_PX = 12, LABEL_THEME_PX = 13;
var TAG_WRAP_CHARS = 26, THEME_MAX_CHARS = 34;
var LINE_H = 14;

/* Перенос по словам: названия НЕ обрезаются многоточием на 34 символах —
   именно так терялось самое важное («Безусловная оптимизация функции о…»
   вместо «функции одной переменной»). Многоточие остаётся только для тех
   единиц, что не влезли и в две строки. */
function wrapLabel(text, maxChars, maxLines) {
  var words = String(text).split(/\s+/);
  var lines = [], cur = '';
  for (var i = 0; i < words.length; i++) {
    var w = words[i];
    var next = cur ? cur + ' ' + w : w;
    if (next.length <= maxChars || !cur) {
      cur = next;
    } else {
      lines.push(cur); cur = w;
      if (lines.length === maxLines) break;
    }
  }
  if (cur && lines.length < maxLines) lines.push(cur);
  if (lines.length === maxLines) {
    /* Хвост не поместился — многоточие ставится на ПОСЛЕДНЕЙ строке. */
    var used = lines.join(' ').length;
    if (used < String(text).replace(/\s+/g, ' ').length) {
      var last = lines[maxLines - 1];
      while (last.length > 3 && last.length > maxChars - 1) last = last.slice(0, -1);
      lines[maxLines - 1] = last.replace(/[\s,;:—-]+$/, '') + '…';
    }
  }
  return lines;
}

function cutLabel(text, maxChars) {
  text = String(text);
  if (text.length <= maxChars) return text;
  return text.slice(0, maxChars - 1).replace(/[\s,;:—-]+$/, '') + '…';
}

/* Подложка под подписью: прямоугольник цвета холста.
   Рисуется ДО текста и поверх рёбер — иначе буквы перечёркиваются
   спицами и линиями (дефект Б). */
function plate(x, y, w, h) {
  ctx.fillStyle = PAL.plate;
  var r = 4;
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
  ctx.fill();
}

function drawLabelLines(lines, x, y, align, alpha, colour, px) {
  ctx.font = '500 ' + px + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  ctx.textAlign = align;
  ctx.textBaseline = 'middle';
  var wMax = 0;
  for (var i = 0; i < lines.length; i++) {
    wMax = Math.max(wMax, ctx.measureText(lines[i]).width);
  }
  var hAll = lines.length * LINE_H;
  var px0 = align === 'right' ? x - wMax : (align === 'center' ? x - wMax / 2 : x);
  ctx.globalAlpha = alpha;
  plate(px0 - 4, y - hAll / 2 - 2, wMax + 8, hAll + 4);
  ctx.fillStyle = colour;
  for (i = 0; i < lines.length; i++) {
    ctx.fillText(lines[i], x, y - hAll / 2 + LINE_H / 2 + i * LINE_H);
  }
  ctx.globalAlpha = 1;
  return { w: wMax, h: hAll, left: px0 };
}

/* Раскладка подписей темы в фокус-режиме — две ровные колонки, как выноски
   у круговой диаграммы (дефект Г). Проверка на пересечение здесь НЕ
   применяется вовсе: раскладка по колонкам уже гарантирует, что подписи
   не налезут, а проверка выбрасывала часть тегов молча (дефект Д). */
var COL_DX = 130, ROW_MIN = 20, ROW_MIN_2 = 34;

function layoutFocusLabels(theme) {
  var tags = (tagsOfTheme[theme.n] || []).filter(function (t) { return t.pz > 0; });
  if (!tags.length) return [];
  var left = [], right = [];
  tags.forEach(function (t) {
    (t.px < theme.px ? left : right).push(t);
  });

  function place(list, side) {
    list.sort(function (a, b) { return a.py - b.py; });
    var items = list.map(function (t) {
      var lines = wrapLabel(t.l, TAG_WRAP_CHARS, 2);
      return { node: t, lines: lines, h: lines.length > 1 ? ROW_MIN_2 : ROW_MIN, y: t.py };
    });
    /* Раздвигаем по вертикали, центрируя разброс вокруг исходного y. */
    var total = items.reduce(function (s, it) { return s + it.h; }, 0);
    var start = theme.py - total / 2;
    var y = start;
    items.forEach(function (it) {
      it.y = y + it.h / 2;
      y += it.h;
    });
    var x = theme.px + (side < 0 ? -COL_DX : COL_DX);
    items.forEach(function (it) { it.x = x; it.side = side; });
    return items;
  }

  return place(left, -1).concat(place(right, 1));
}

/* ── Кадр ────────────────────────────────────────────────────────────── */

var LABEL_BUDGET = 90;       /* лимит подписей вне фокус-режима */

function draw() {
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.fillStyle = PAL.bgCss;
  ctx.fillRect(0, 0, W, H);

  camPrepare();
  project();

  var dim = !!(litSet || searchHits);

  /* ── Рёбра батчами ──────────────────────────────────────────────────
     Не 425 отдельных обводок, а четыре Path2D и четыре stroke(): каждая
     смена стиля и каждый stroke стоят дороже самой линии. */
  var pNear = new Path2D(), pFar = new Path2D(), pCross = new Path2D();
  var roads = [];

  for (var i = 0; i < links.length; i++) {
    var ln = links[i];
    var a = byId[ln.s], b = byId[ln.t];
    if (a.pz < 0 || b.pz < 0) continue;
    var lit = litEdges && litEdges[edgeKey(a.id, b.id)];
    if (lit) { roads.push({ a: a, b: b, k: ln.k }); continue; }
    var path;
    if (ln.k === 'cross') path = pCross;
    else path = ((a.pz + b.pz) / 2 < DIST) ? pNear : pFar;
    path.moveTo(a.px, a.py);
    path.lineTo(b.px, b.py);
  }

  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  ctx.strokeStyle = PAL.borderShades[shadeIndex(dim ? 0.14 : 0.42)];
  ctx.stroke(pFar);
  ctx.strokeStyle = PAL.borderShades[shadeIndex(dim ? 0.26 : 0.9)];
  ctx.stroke(pNear);
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = PAL.borderShades[shadeIndex(dim ? 0.2 : 0.75)];
  ctx.stroke(pCross);
  ctx.setLineDash([]);

  /* Подсвеченные дороги — их единицы, поэтому штучно и цветом темы. */
  for (i = 0; i < roads.length; i++) {
    var rd = roads[i];
    var owner = rd.a.k === 'theme' ? rd.a : rd.b;
    ctx.strokeStyle = (owner.shades || PAL.accentShades)[shadeIndex(0.95)];
    ctx.lineWidth = 2.2;
    if (rd.k === 'cross') {
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = PAL.accentShades[shadeIndex(0.7)];
    }
    ctx.beginPath();
    ctx.moveTo(rd.a.px, rd.a.py);
    ctx.lineTo(rd.b.px, rd.b.py);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.lineWidth = 1;

  /* ── Узлы: дальние раньше ближних ─────────────────────────────────── */
  order.sort(function (p, q) { return q.pz - p.pz; });

  for (i = 0; i < order.length; i++) {
    var n = order[i];
    if (n.pz < 0) continue;
    var r = nodeRadius(n);
    if (n.px < -40 || n.px > W + 40 || n.py < -40 || n.py > H + 40) continue;

    var on = isLit(n);
    var near = litNear && litNear[n.id];
    var a2;
    if (!dim) a2 = 1;
    else if (on) a2 = 1;
    else if (near) a2 = 0.62;
    else a2 = dimFloor(n.k);
    if (n.k === 'theme' && a2 < 0.5) a2 = 0.5;

    ctx.fillStyle = (n.shades || PAL.accentShades)[shadeIndex(a2)];
    ctx.beginPath();
    ctx.arc(n.px, n.py, r, 0, 6.283185307179586);
    ctx.fill();

    if (picked[n.id]) {
      /* Ореол своим цветом плюс обводка акцентом — выбранное видно всегда. */
      ctx.strokeStyle = (n.shades || PAL.accentShades)[shadeIndex(0.35)];
      ctx.lineWidth = 5;
      ctx.beginPath(); ctx.arc(n.px, n.py, r + 3.5, 0, 6.283185307179586); ctx.stroke();
      ctx.strokeStyle = PAL.accentCss;
      ctx.lineWidth = 1.8;
      ctx.beginPath(); ctx.arc(n.px, n.py, r + 2, 0, 6.283185307179586); ctx.stroke();
      ctx.lineWidth = 1;
    } else if (n === hoverNode) {
      ctx.strokeStyle = PAL.accentShades[shadeIndex(0.8)];
      ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.arc(n.px, n.py, r + 2.5, 0, 6.283185307179586); ctx.stroke();
      ctx.lineWidth = 1;
    }
  }

  drawLabels(dim);
}

function drawLabels(dim) {
  var i;
  /* ⚠️ ПОДПИСИ ТЕГОВ И ПОДПИСИ ТЕМ ДЕЛЯТ ОДИН ХОЛСТ, ЗНАЧИТ И ОДИН СПИСОК
     ЗАНЯТЫХ МЕСТ. Пока каждый слой раскладывался сам по себе, они честно
     не пересекались внутри себя и дружно налезали друг на друга: имя темы
     рисуется последним и своей подложкой затирало половину раскрытых имён
     тегов. */
  var taken = [];

  /* ── Теги ───────────────────────────────────────────────────────────
     Сначала фокус-режим: у темы под курсором подписываются ВСЕ теги,
     двумя колонками, с выносками. */
  if (focusTheme && focusTheme.pz > 0) {
    var items = layoutFocusLabels(focusTheme);
    for (i = 0; i < items.length; i++) {
      var it = items[i];
      var t = it.node;
      /* Выноска: от узла до края колонки, внутрь плашки не заходит. */
      ctx.strokeStyle = (t.shades || PAL.borderShades)[shadeIndex(0.55)];
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(t.px + (it.side < 0 ? -1 : 1) * (nodeRadius(t) + 2), t.py);
      ctx.lineTo(it.x - it.side * 10, it.y);
      ctx.stroke();
      ctx.lineWidth = 1;
      var box = drawLabelLines(it.lines, it.x, it.y, it.side < 0 ? 'right' : 'left',
                               1, PAL.textCss, LABEL_TAG_PX);
      taken.push({ x: box.left + box.w / 2, y: it.y, w: box.w,
                   h: box.h, l: it.node.l });
    }
  } else if (cam.zoom >= 1.25 || litSet || searchHits) {
    /* Вне фокус-режима — при приближении либо у подсвеченных, с лимитом. */
    var shown = 0;
    var boxes = [];
    for (i = 0; i < order.length && shown < LABEL_BUDGET; i++) {
      var n = order[order.length - 1 - i];        /* ближние раньше */
      if (!n || n.k !== 'tag' || n.pz < 0) continue;
      var lit = isLit(n) || (litNear && litNear[n.id]);
      if (dim && !lit) continue;
      if (!dim && cam.zoom < 1.25) continue;
      if (n.px < 0 || n.px > W || n.py < 0 || n.py > H) continue;

      var lines = wrapLabel(n.l, TAG_WRAP_CHARS, 2);
      ctx.font = '500 ' + LABEL_TAG_PX + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      var wMax = 0;
      for (var q = 0; q < lines.length; q++) {
        wMax = Math.max(wMax, ctx.measureText(lines[q]).width);
      }
      var hAll = lines.length * LINE_H;
      var gap = nodeRadius(n) + 12;               /* подпись не ближе 12px */
      var side = (n.px + gap + wMax < W) ? 1 : -1;
      var lx = n.px + side * gap;
      var ly = n.py, tries = 0, hit = true;
      while (tries < 3 && hit) {
        hit = false;
        for (var b = 0; b < boxes.length; b++) {
          var bx = boxes[b];
          if (Math.abs(bx.y - ly) < (bx.h + hAll) / 2 + 3 &&
              Math.abs(bx.x - lx) < (bx.w + wMax) / 2 + 6) { hit = true; break; }
        }
        if (hit) { ly += hAll + 4; tries++; }
      }
      if (hit) continue;
      var left = side > 0 ? lx : lx - wMax;
      boxes.push({ x: left + wMax / 2, y: ly, w: wMax, h: hAll });
      taken.push({ x: left + wMax / 2, y: ly, w: wMax, h: hAll, l: n.l });
      drawLabelLines(lines, lx, ly, side > 0 ? 'left' : 'right',
                     1, PAL.textCss, LABEL_TAG_PX);
      shown++;
    }
  }

  /* ── Темы: подписаны ВСЕГДА ─────────────────────────────────────────
     Включая режим приглушения. Иначе при выборе тега имена остальных тем
     гаснут, и человек ищет нужную тему наугад.
     ⚠️ «Видны всегда» означает и «не наезжают друг на друга»: темы стоят
     плотно, и без раздвижки соседние имена сливались в нечитаемую кашу
     («Другое» поверх «Данные, статистика и причинность»). Раздвигаем по
     вертикали, НИ ОДНУ не выбрасывая: ближние к камере занимают своё
     место первыми, дальние уступают. */
  ctx.font = '500 ' + LABEL_THEME_PX + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  var plan = [];
  for (i = 0; i < themeList.length; i++) {
    var th = themeList[i];
    if (th.pz < 0) continue;
    if (th.px < -60 || th.px > W + 60 || th.py < -40 || th.py > H + 40) continue;
    var text = cutLabel(th.l, THEME_MAX_CHARS);
    plan.push({
      node: th, text: text,
      w: ctx.measureText(text).width,
      y: th.py - nodeRadius(th) - 11,
      lit: !dim || isLit(th) || (focusTheme === th)
    });
  }
  plan.sort(function (p, q) { return p.node.pz - q.node.pz; });   /* ближние раньше */

  var placed = taken;            /* темы обходят и подписи тегов тоже */
  lastThemeBoxes = placed;
  lastThemeFrom = taken.length;
  for (i = 0; i < plan.length; i++) {
    var it2 = plan[i];
    var half = it2.w / 2 + 5;

    /* ⚠️ ИЩЕМ БЛИЖАЙШЕЕ СВОБОДНОЕ МЕСТО, А НЕ «ОТПРЫГИВАЕМ ОТ СОСЕДА».
       Отпрыгивание от первой помехи загоняет подпись в объятия второй, та
       отправляет обратно к первой, попытки кончаются — и подпись остаётся
       лежать поверх соседки. Замер на 29 подписях: 16 пересечений. Здесь
       позиции перебираются по возрастанию смещения от исходной, и берётся
       первая, свободная ОТ ВСЕХ уже размещённых. */
    var x0 = it2.node.px, y0 = it2.y;
    var foundX = x0, foundY = y0, ok = false;

    /* Ищем по кольцам вокруг исходного места: сначала чисто вертикальные
       сдвиги (они не отрывают подпись от своей колонки), потом с уходом
       вбок. Одной вертикали не хватает — в плотной середине колонка бывает
       занята целиком, и подпись оставалась лежать поверх соседки. */
    var STEP_Y = LINE_H + 7, STEP_X = 48;
    for (var d = 0; d <= 15 && !ok; d++) {
      for (var sx = 0; sx <= d && !ok; sx++) {
        var dy = d - sx;
        var xs = sx === 0 ? [0] : [-sx, sx];
        var ys = dy === 0 ? [0] : [-dy, dy];
        for (var a1 = 0; a1 < xs.length && !ok; a1++) {
          for (var a2 = 0; a2 < ys.length && !ok; a2++) {
            var cx = x0 + xs[a1] * STEP_X, cy = y0 + ys[a2] * STEP_Y;
            if (cy < 12 || cy > H - 12) continue;
            if (cx - half < 4 || cx + half > W - 4) continue;
            var clear = true;
            for (var b2 = 0; b2 < placed.length; b2++) {
              var pb = placed[b2];
              if (Math.abs(pb.x - cx) < half + pb.w / 2 + 5 &&
                  Math.abs(pb.y - cy) < (pb.h || LINE_H) / 2 + LINE_H / 2 + 6) {
                clear = false; break;
              }
            }
            if (clear) { foundX = cx; foundY = cy; ok = true; }
          }
        }
      }
    }
    it2.x = Math.max(half + 4, Math.min(W - half - 4, foundX));
    it2.y = Math.max(12, Math.min(H - 12, foundY));
    placed.push({ x: it2.x, y: it2.y, w: it2.w, h: LINE_H, l: it2.text });

    /* Подпись, уступившая место соседке, могла уехать далеко от своего
       узла. Тонкая выноска возвращает ей адрес: иначе имя темы висит в
       пустоте и человек не знает, к какому кружку оно относится. */
    var away = Math.hypot(it2.x - it2.node.px,
                          it2.y - (it2.node.py - nodeRadius(it2.node) - 11));
    if (away > 24) {
      /* Выноска ведёт к ближайшему краю плашки, а не в её середину: линия
         не должна заходить под текст. */
      var tx = it2.x + (it2.node.px > it2.x ? it2.w / 2 + 4 : -(it2.w / 2 + 4));
      if (Math.abs(it2.node.px - it2.x) < it2.w / 2) tx = it2.node.px;
      var ty = it2.y + (it2.y > it2.node.py ? -10 : 10);
      var rr = nodeRadius(it2.node) + 2;
      var ang = Math.atan2(ty - it2.node.py, tx - it2.node.px);
      ctx.strokeStyle = (it2.node.shades || PAL.borderShades)[shadeIndex(0.45)];
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(it2.node.px + Math.cos(ang) * rr, it2.node.py + Math.sin(ang) * rr);
      ctx.lineTo(tx, ty);
      ctx.stroke();
      ctx.lineWidth = 1;
    }

    drawLabelLines([it2.text], it2.x, it2.y, 'center',
                   it2.lit ? 1 : 0.55, PAL.textCss, LABEL_THEME_PX);
  }
}


/* ═══════════════════════════════════════════════════════════════════════
   ЧАСТЬ 4. ВЗАИМОДЕЙСТВИЕ
   ═══════════════════════════════════════════════════════════════════════ */

/* ⚠️ ЗУМ ПОСЛЕ КОЛЕСА НЕ СРАБАТЫВАЛ, ПОКА НЕ КЛИКНЕШЬ — ЭТО БЫЛ БАГ.
   Цикл пропускает кадры, когда сцена считается неподвижной, а обработчик
   колеса менял zoom, не помечая сцену изменившейся. Поэтому есть wake():
   она ставит флаг «перерисовать», и её обязан звать КАЖДЫЙ обработчик —
   колесо, перетаскивание, клик, наведение, кнопки зума, ввод в поиск,
   изменение размера окна, смена темы. */
var dirty = true;
function wake() { dirty = true; }

/* ── Авто-вращение ───────────────────────────────────────────────────── */
var SPIN_START = 0.0011;      /* при открытии карты                       */
var SPIN_IDLE = 0.00088;      /* после бездействия — на 20% медленнее     */
var IDLE_MS = 3000, SPIN_RAMP_MS = 800;

var spinMode = 'start';       /* start | off | ramp                       */
var idleTimer = null, rampStart = 0;

function touchActivity() {
  /* Любое действие человека останавливает вращение и заводит таймер. */
  if (reduceMotion) return;
  spinMode = 'off';
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(function () {
    spinMode = 'ramp';
    rampStart = performance.now();
    wake();
  }, IDLE_MS);
}

function spinSpeed(now) {
  if (reduceMotion) return 0;
  if (spinMode === 'start') return SPIN_START;
  if (spinMode === 'off') return 0;
  /* Разгон линейный за 0.8 с — вращение не должно включаться рывком. */
  var t = Math.min(1, (now - rampStart) / SPIN_RAMP_MS);
  return SPIN_IDLE * t;
}

/* ── Цикл кадров ─────────────────────────────────────────────────────── */
var fpsFrames = 0, fpsSince = 0, fpsValue = 0;

function frame(now) {
  requestAnimationFrame(frame);
  if (!ready) return;

  var moved = false;

  /* Раскладка досчитывается, пока не остыла. */
  if (alpha > 0.03) {
    step();
    alpha *= 0.975;
    moved = true;
  }

  /* Плавный зум: колесо меняет цель, кадр подтягивает значение. */
  if (Math.abs(cam.zoomTarget - cam.zoom) > 0.0005) {
    cam.zoom += (cam.zoomTarget - cam.zoom) * 0.25;
    moved = true;
  }

  /* Наводка камеры после двойного клика или клика по списку тем. */
  if (cam.goalX !== null) {
    cam.tx += (cam.goalX - cam.tx) * 0.12;
    cam.ty += (cam.goalY - cam.ty) * 0.12;
    cam.tz += (cam.goalZ - cam.tz) * 0.12;
    if (cam.goalZoom !== null) {
      cam.zoomTarget += (cam.goalZoom - cam.zoomTarget) * 0.12;
      showZoom();
    }
    moved = true;
    if (Math.hypot(cam.goalX - cam.tx, cam.goalY - cam.ty, cam.goalZ - cam.tz) < 1) {
      cam.goalX = cam.goalY = cam.goalZ = cam.goalZoom = null;
    }
  }

  var spin = spinSpeed(now);
  if (spin > 0) { cam.yaw += spin; moved = true; }

  if (moved || dirty) {
    dirty = false;
    draw();
  }

  /* Счётчик кадров — для замера, читается из консоли: TMAP.fps() */
  fpsFrames++;
  if (!fpsSince) fpsSince = now;
  if (now - fpsSince >= 1000) {
    fpsValue = Math.round(fpsFrames * 1000 / (now - fpsSince));
    fpsFrames = 0; fpsSince = now;
  }
}

/* ── Размер холста ───────────────────────────────────────────────────── */
function resize() {
  DPR = Math.min(2, window.devicePixelRatio || 1);
  var r = wrap.getBoundingClientRect();
  W = Math.max(320, Math.round(r.width));
  H = Math.max(280, Math.round(r.height));
  canvas.width = Math.round(W * DPR);
  canvas.height = Math.round(H * DPR);
  canvas.style.width = W + 'px';
  canvas.style.height = H + 'px';
  wake();
}

/* ── Мышь ────────────────────────────────────────────────────────────── */
var dragging = false, dragX = 0, dragY = 0, dragMoved = 0;

function localPoint(e) {
  var r = canvas.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
}

canvas.addEventListener('pointerdown', function (e) {
  canvas.setPointerCapture(e.pointerId);
  dragging = true; dragMoved = 0;
  dragX = e.clientX; dragY = e.clientY;
  canvas.classList.add('is-drag');
  touchActivity(); wake();
});

canvas.addEventListener('pointermove', function (e) {
  var p = localPoint(e);
  if (dragging) {
    var dx = e.clientX - dragX, dy = e.clientY - dragY;
    dragMoved += Math.abs(dx) + Math.abs(dy);
    cam.yaw += dx * 0.005;
    cam.pitch += dy * 0.005;
    cam.pitch = Math.max(-1.35, Math.min(1.35, cam.pitch));
    dragX = e.clientX; dragY = e.clientY;
    touchActivity(); wake();
    return;
  }
  var hit = hitTest(p[0], p[1]);
  canvas.classList.toggle('is-hit', !!hit);
  if (hit !== hoverNode) {
    hoverNode = hit;
    focusTheme = (hit && hit.k === 'theme') ? hit : null;
    rebuildHighlight();
    renderHover(hit);
    wake();
  }
  touchActivity();
});

canvas.addEventListener('pointerup', function (e) {
  dragging = false;
  canvas.classList.remove('is-drag');
  if (dragMoved < 5) {
    var p = localPoint(e);
    var hit = hitTest(p[0], p[1]);
    if (hit) togglePick(hit);
  }
  touchActivity(); wake();
});

canvas.addEventListener('pointerleave', function () {
  if (hoverNode) {
    hoverNode = null; focusTheme = null;
    rebuildHighlight(); renderHover(null); wake();
  }
});

canvas.addEventListener('dblclick', function (e) {
  var p = localPoint(e);
  var hit = hitTest(p[0], p[1]);
  if (hit) flyTo(hit, 2.1);
  touchActivity();
});

/* Зум К ТОЧКЕ ПОД КУРСОРОМ, а не к центру экрана. */
function zoomAt(mx, my, factor) {
  var before = cam.zoomTarget;
  var after = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, before * factor));
  if (after === before) return;
  cam.zoomTarget = after;

  /* Сдвигаем target так, чтобы точка под курсором осталась на месте.
     Работаем в осях камеры: right и up получены разворотом проекции. */
  camPrepare();
  var s = FOCAL / DIST * before * fitScale, s2 = FOCAL / DIST * after * fitScale;
  var ax = (mx - W / 2) / s, ay = (my - H / 2) / s;
  var k = 1 - s / s2;
  var dax = ax * k, day = ay * k;
  var rightX = CY, rightY = 0, rightZ = SY;
  var upX = SY * SP, upY = CP, upZ = -CY * SP;
  cam.tx += rightX * dax + upX * day;
  cam.ty += rightY * dax + upY * day;
  cam.tz += rightZ * dax + upZ * day;
  cam.goalX = cam.goalY = cam.goalZ = cam.goalZoom = null;
  showZoom();
  wake();
}

canvas.addEventListener('wheel', function (e) {
  e.preventDefault();
  var p = localPoint(e);
  zoomAt(p[0], p[1], e.deltaY < 0 ? 1.12 : 0.893);
  touchActivity();
}, { passive: false });

/* Подпись процента у кнопок масштаба. Обновляется в момент действия, а не
   в кадре: человек должен увидеть, куда едет масштаб, сразу. */
var zoomLabel = document.getElementById('tmap-zoom-val');
function showZoom() {
  if (zoomLabel) zoomLabel.textContent = Math.round(cam.zoomTarget * 100) + '%';
}

function flyTo(n, zoom) {
  cam.goalX = n.x; cam.goalY = n.y; cam.goalZ = n.z;
  cam.goalZoom = zoom === undefined ? null : zoom;
  if (reduceMotion) {
    /* Без анимации: сразу на месте. */
    cam.tx = n.x; cam.ty = n.y; cam.tz = n.z;
    if (zoom !== undefined) { cam.zoom = cam.zoomTarget = zoom; }
    cam.goalX = cam.goalY = cam.goalZ = cam.goalZoom = null;
  }
  if (zoom !== undefined) showZoom();
  wake();
}

function resetView() {
  cam.goalX = cam.goalY = cam.goalZ = null;
  cam.tx = cam.ty = cam.tz = 0;
  cam.zoomTarget = 1;
  cam.pitch = -0.22;
  if (reduceMotion) cam.zoom = 1;
  showZoom();
  wake();
}

/* ── Кнопки масштаба ─────────────────────────────────────────────────── */
document.getElementById('tmap-zoom-in').addEventListener('click', function () {
  zoomAt(W / 2, H / 2, 1.12); touchActivity();
});
document.getElementById('tmap-zoom-out').addEventListener('click', function () {
  zoomAt(W / 2, H / 2, 0.893); touchActivity();
});
document.getElementById('tmap-zoom-fit').addEventListener('click', function () {
  resetView(); touchActivity();
});

/* ── Выбор ───────────────────────────────────────────────────────────── */
function togglePick(n) {
  if (picked[n.id]) delete picked[n.id];
  else picked[n.id] = true;
  rebuildHighlight();
  renderPicked();
  wake();
}

function clearPick() {
  picked = {};
  var q = document.getElementById('tmap-q');
  if (q) q.value = '';
  applySearch('');
  rebuildHighlight();
  renderPicked();
  renderHover(hoverNode);
  wake();
}

/* ── Поиск ───────────────────────────────────────────────────────────── */
function norm(s) {
  return String(s).toLowerCase().replace(/ё/g, 'е');
}

function applySearch(raw) {
  var q = norm(raw).trim();
  var out = document.getElementById('tmap-q-count');
  if (!q) {
    searchHits = null;
    if (out) out.textContent = '';
    return 0;
  }
  searchHits = {};
  var hits = 0;
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].nl.indexOf(q) >= 0) { searchHits[nodes[i].id] = true; hits++; }
  }
  if (out) out.textContent = hits ? String(hits) : '0';
  return hits;
}

/* ── Панель ──────────────────────────────────────────────────────────── */
var hoverBox = document.getElementById('tmap-hover');

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtNum(n) {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

var HOWTO = '<ul class="tmap-howto">' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5.5" fill="currentColor" opacity=".7"/></svg>' +
  '<span>Крупный узел — <b>тема</b>, их 29.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="2.6" fill="currentColor" opacity=".7"/></svg>' +
  '<span>Мелкий узел — <b>тег</b>, их 343.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" stroke-width="1.5" opacity=".7"/></svg>' +
  '<span>Сплошная линия — дорога <b>тема → тег</b>.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 3" opacity=".7"/></svg>' +
  '<span>Пунктир — смежные теги из разных тем, 82 пары.</span></li></ul>';

function renderHover(n) {
  if (!hoverBox) return;
  if (!n) {
    var any = false;
    for (var k in picked) { if (picked[k]) { any = true; break; } }
    hoverBox.innerHTML = any ? '<div class="tmap-def">Наведите на узел, чтобы увидеть подробности.</div>' : HOWTO;
    return;
  }
  var html = '';
  if (n.k === 'theme') {
    var cnt = (tagsOfTheme[n.n] || []).length;
    html += '<span class="tmap-kind">тема ' + n.n + ' · ' + cnt + ' тегов</span>';
    html += '<div class="tmap-name">' + esc(n.l) + '</div>';
    if (n.d) html += '<div class="tmap-def">' + esc(n.d) + '</div>';
    html += n.c
      ? '<div class="tmap-num"><b>' + fmtNum(n.c) + '</b> задач по тегам темы</div>'
      : '<div class="tmap-num tmap-num--none">— счётчиков у тегов темы нет</div>';
  } else {
    var parent = byId['t' + n.n];
    html += '<span class="tmap-kind">тег темы ' + n.n + '</span>';
    html += '<div class="tmap-name">' + esc(n.l) + '</div>';
    if (parent) {
      html += '<div class="tmap-parent"><span>' + esc(parent.l) + '</span></div>';
    }
    /* Канон 2.3: отсутствие числа — прочерк и причина, а не пустое место. */
    html += n.c === null || n.c === undefined
      ? '<div class="tmap-num tmap-num--none">— <span>счётчика нет, тег размечается вручную</span></div>'
      : '<div class="tmap-num"><b>' + fmtNum(n.c) + '</b> задач</div>';

    var near = nearOf[n.id] || [];
    if (near.length) {
      html += '<div class="tmap-near-h">Смежные теги</div><div class="tmap-near">';
      near.forEach(function (id) {
        var t = byId[id];
        if (!t) return;
        html += '<button type="button" class="tmap-near-item" data-go="' + t.id + '">' +
                '<span class="tmap-near-n">' + t.n + '.</span>' +
                '<span>' + esc(t.l) + '</span></button>';
      });
      html += '</div>';
    }
  }
  hoverBox.innerHTML = html;
}

function renderPicked() {
  var ids = Object.keys(picked).filter(function (k) { return picked[k]; });
  var block = document.getElementById('tmap-picked-block');
  var chips = document.getElementById('tmap-chips');
  var nEl = document.getElementById('tmap-picked-n');
  if (block) block.hidden = ids.length === 0;
  if (nEl) nEl.textContent = String(ids.length);

  if (chips) {
    chips.innerHTML = ids.map(function (id) {
      var n = byId[id];
      if (!n) return '';
      return '<span class="tmap-chip"><span class="tmap-chip-l">' + esc(n.l) +
             '</span><button type="button" data-drop="' + id +
             '" aria-label="Убрать ' + esc(n.l) + '">✕</button></span>';
    }).join('');
  }

  /* Счётчик внизу: теги и оценка задач снизу. */
  var tagIds = ids.filter(function (id) { return byId[id] && byId[id].k === 'tag'; });
  var themeIds = ids.filter(function (id) { return byId[id] && byId[id].k === 'theme'; });
  var all = {};
  tagIds.forEach(function (id) { all[id] = true; });
  themeIds.forEach(function (id) {
    (tagsOfTheme[byId[id].n] || []).forEach(function (t) { all[t.id] = true; });
  });
  var keys = Object.keys(all);
  var sum = 0;
  keys.forEach(function (id) { sum += byId[id].c || 0; });

  var cEl = document.getElementById('tmap-count');
  if (cEl) {
    cEl.textContent = keys.length
      ? 'Выбрано: ' + keys.length + ' ' + plural(keys.length, 'тег', 'тега', 'тегов') +
        ' · примерно ' + fmtNum(sum) + ' ' + plural(sum, 'задача', 'задачи', 'задач')
      : 'Выбрано: 0 тегов';
  }
  var apply = document.getElementById('tmap-apply');
  var why = document.getElementById('tmap-why');
  if (apply) apply.disabled = keys.length === 0;
  /* Канон 2.7: причина выключенной кнопки стоит РЯДОМ, а не в подсказке. */
  if (why) why.hidden = keys.length > 0;

  /* Подсветка строк навигатора «Темы». */
  Array.prototype.forEach.call(document.querySelectorAll('.tmap-theme-row'), function (row) {
    row.classList.toggle('is-on', !!picked['t' + row.dataset.theme]);
  });
}

function plural(n, one, few, many) {
  var a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}


/* ═══════════════════════════════════════════════════════════════════════
   ЧАСТЬ 5. ОБУЧЕНИЕ ПРИ ПЕРВОМ ЗАХОДЕ
   ═══════════════════════════════════════════════════════════════════════ */

/* Версия в ключе нужна, чтобы при серьёзной переделке карты показать тур
   заново, не трогая тех, кто его уже видел на прежней версии. */
var TOUR_KEY = 'weconomics.map.tour.v1';

var tourBox = document.getElementById('tmap-tour');
var tourHole = document.getElementById('tmap-tour-hole');
var tourCard = document.getElementById('tmap-tour-card');
var tourStep = 0, tourOn = false, tourDemo = [];

/* Тур не рассказывает, а ПОКАЗЫВАЕТ: каждый шаг сам управляет картой. */
var TOUR = [
  {
    t: 'Это весь корпус',
    p: '29 тем и 343 тега — всё, из чего состоит банк задач. Крупные узлы это темы, ' +
       'мелкие вокруг них — теги.',
    at: function () { return wrap; },
    go: function () { resetView(); }
  },
  {
    t: 'Тяните мышью — карта поворачивается',
    p: 'Колесо приближает и отдаляет, причём к той точке, где стоит курсор. ' +
       'Кнопки в углу холста делают то же самое.',
    at: function () { return wrap; },
    go: function () {
      if (reduceMotion) return;
      var from = cam.yaw;
      spinTo(from + 0.7, 700, function () { spinTo(from, 700); });
    }
  },
  {
    t: 'Наведите на узел',
    p: 'Справа появится тема, число задач и смежные теги из других тем. ' +
       'Дорога от тега до его темы подсвечивается прямо на карте.',
    at: function () { return document.getElementById('tmap-hover-block'); },
    go: function () {
      var t = findTag('Кривая Лаффера');
      if (!t) return;
      hoverNode = t; focusTheme = null;
      rebuildHighlight(); renderHover(t);
      flyTo(byId['t' + t.n], 1.6);
    }
  },
  {
    t: 'Клик выбирает тег',
    p: 'Выбранный тег попадает в список справа, а внизу считается, сколько задач ' +
       'он примерно даёт. Тегов можно набрать сколько угодно, даже из разных тем.',
    at: function () { return document.getElementById('tmap-picked-block'); },
    go: function () {
      var a = findTag('Кривая Лаффера');
      var b = findTag('Расчёт коэффициента Джини');
      tourDemo = [];
      [a, b].forEach(function (t) {
        if (t && !picked[t.id]) { picked[t.id] = true; tourDemo.push(t.id); }
      });
      hoverNode = null;
      rebuildHighlight(); renderPicked(); renderHover(null);
    }
  },
  {
    t: 'Не нашли на карте — ищите',
    p: 'Поиск в шапке подсвечивает совпавшие узлы. А список тем справа — второй, ' +
       'надёжный способ: клик по строке наводит камеру на нужную тему.',
    at: function () { return document.getElementById('tmap-q'); },
    at2: function () { return document.getElementById('tmap-themes'); },
    go: function () {}
  }
];

function findTag(part) {
  var q = norm(part);
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].k === 'tag' && nodes[i].nl.indexOf(q) >= 0) return nodes[i];
  }
  return null;
}

/* Плавный поворот камеры для показа — только когда движение разрешено. */
function spinTo(target, ms, done) {
  var from = cam.yaw, t0 = performance.now();
  (function tick() {
    var k = Math.min(1, (performance.now() - t0) / ms);
    cam.yaw = from + (target - from) * (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);
    wake();
    if (k < 1) requestAnimationFrame(tick);
    else if (done) done();
  })();
}

function tourShow(i) {
  tourStep = Math.max(0, Math.min(TOUR.length - 1, i));
  var s = TOUR[tourStep];
  document.getElementById('tmap-tour-step').textContent =
    'Шаг ' + (tourStep + 1) + ' из ' + TOUR.length;
  document.getElementById('tmap-tour-title').textContent = s.t;
  document.getElementById('tmap-tour-text').textContent = s.p;
  document.getElementById('tmap-tour-next').textContent =
    tourStep === TOUR.length - 1 ? 'Понятно, начать' : 'Дальше';
  document.getElementById('tmap-tour-prev').disabled = tourStep === 0;

  var dots = document.getElementById('tmap-tour-dots');
  dots.innerHTML = TOUR.map(function (_, j) {
    return '<i class="' + (j === tourStep ? 'is-on' : '') + '"></i>';
  }).join('');

  var el = s.at && s.at();
  if (el) {
    var r = el.getBoundingClientRect();
    tourHole.style.left = (r.left - 6) + 'px';
    tourHole.style.top = (r.top - 6) + 'px';
    tourHole.style.width = (r.width + 12) + 'px';
    tourHole.style.height = (r.height + 12) + 'px';
    placeTourCard(r);
  }
  if (s.go) s.go();
  wake();
}

function placeTourCard(r) {
  var cw = 340, ch = tourCard.offsetHeight || 190, pad = 14;
  var left = r.left + r.width / 2 - cw / 2;
  var top = r.bottom + pad;
  if (top + ch > window.innerHeight - 8) top = Math.max(8, r.top - ch - pad);
  left = Math.max(8, Math.min(window.innerWidth - cw - 8, left));
  tourCard.style.left = left + 'px';
  tourCard.style.top = top + 'px';
}

function tourStart() {
  tourOn = true;
  tourBox.hidden = false;
  tourShow(0);
  document.addEventListener('keydown', tourKeys);
}

function tourEnd() {
  tourOn = false;
  tourBox.hidden = true;
  document.removeEventListener('keydown', tourKeys);
  /* Тур убирает за собой свой показательный выбор и возвращает обзор. */
  tourDemo.forEach(function (id) { delete picked[id]; });
  tourDemo = [];
  hoverNode = null; focusTheme = null;
  rebuildHighlight(); renderPicked(); renderHover(null);
  resetView();
  try { localStorage.setItem(TOUR_KEY, '1'); } catch (e) {}
  wake();
}

function tourKeys(e) {
  if (!tourOn) return;
  if (e.key === 'Escape') { tourEnd(); e.preventDefault(); }
  else if (e.key === 'ArrowRight') { tourNext(); e.preventDefault(); }
  else if (e.key === 'ArrowLeft') { tourShow(tourStep - 1); e.preventDefault(); }
}

function tourNext() {
  if (tourStep === TOUR.length - 1) tourEnd();
  else tourShow(tourStep + 1);
}

document.getElementById('tmap-tour-next').addEventListener('click', tourNext);
document.getElementById('tmap-tour-prev').addEventListener('click', function () {
  tourShow(tourStep - 1);
});
document.getElementById('tmap-tour-skip').addEventListener('click', tourEnd);
document.getElementById('tmap-help').addEventListener('click', function () {
  tourStart();
});


/* ═══════════════════════════════════════════════════════════════════════
   ОБРАБОТЧИКИ ПАНЕЛИ И ЗАПУСК
   ═══════════════════════════════════════════════════════════════════════ */

var qInput = document.getElementById('tmap-q');
if (qInput) {
  qInput.addEventListener('input', function () {
    applySearch(qInput.value);
    wake();
    touchActivity();
  });
}

document.getElementById('tmap-reset').addEventListener('click', function () {
  clearPick(); touchActivity();
});

/* Кнопка «Показать задачи» пока никуда не ведёт.
   TODO: логика И/ИЛИ и применение фильтра решаются вместе с переработкой
   поиска и каталога — карточка идеи в Notion,
   https://app.notion.com/p/3cbb11c92bc181629f4aff24af52d837 */
document.getElementById('tmap-apply').addEventListener('click', function () {
  var apply = document.getElementById('tmap-apply');
  apply.textContent = 'Фильтр появится вместе с новым каталогом';
  setTimeout(function () { apply.textContent = 'Показать задачи'; }, 2200);
});

/* Чипы: крестик снимает выбор. */
document.getElementById('tmap-chips').addEventListener('click', function (e) {
  var b = e.target.closest('[data-drop]');
  if (!b) return;
  delete picked[b.dataset.drop];
  rebuildHighlight(); renderPicked(); wake();
  touchActivity();
});

/* Смежные теги в панели — клик наводит камеру. */
hoverBox.addEventListener('click', function (e) {
  var b = e.target.closest('[data-go]');
  if (!b) return;
  var n = byId[b.dataset.go];
  if (n) { flyTo(n, 2.1); touchActivity(); }
});

/* Навигатор «Темы»: наведение подсвечивает, клик наводит камеру и выделяет.
   Это второй, надёжный способ найти тему, когда на карте её не видно. */
var themesBox = document.getElementById('tmap-themes');
if (themesBox) {
  themesBox.addEventListener('mouseover', function (e) {
    var row = e.target.closest('.tmap-theme-row');
    if (!row) return;
    var n = byId['t' + row.dataset.theme];
    if (n && n !== hoverNode) {
      hoverNode = n; focusTheme = n;
      rebuildHighlight(); renderHover(n); wake();
    }
  });
  themesBox.addEventListener('mouseleave', function () {
    if (hoverNode && hoverNode.k === 'theme') {
      hoverNode = null; focusTheme = null;
      rebuildHighlight(); renderHover(null); wake();
    }
  });
  themesBox.addEventListener('click', function (e) {
    var row = e.target.closest('.tmap-theme-row');
    if (!row) return;
    var n = byId['t' + row.dataset.theme];
    if (!n) return;
    flyTo(n, 2.1);
    togglePick(n);
    touchActivity();
  });
}

/* ⚠️ СЛЕДИМ ЗА РАЗМЕРОМ САМОГО КОНТЕЙНЕРА, А НЕ ТОЛЬКО ОКНА.
   Холст меняет размер и без изменения окна: скрытая и снова показанная
   панель, схлопнутая правая колонка, а в будущем — открытие карты во
   всплывающем окне. На событии `resize` окна это не ловится вовсе, и
   карта остаётся посчитанной под прежний, иногда нулевой размер. */
function onBoxResize() {
  var r = wrap.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;   /* холст ещё не разложен */
  resize();
  if (ready) computeFit();
}

window.addEventListener('resize', onBoxResize);
if (window.ResizeObserver) {
  new ResizeObserver(onBoxResize).observe(wrap);
}

/* Смена темы сайта: цвета перечитываются из токенов, своих значений у
   карты нет. */
new MutationObserver(function () {
  readPalette(); wake();
}).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', function (e) {
  reduceMotion = e.matches;
  if (reduceMotion) spinMode = 'off';
  wake();
});

/* ── Загрузка ────────────────────────────────────────────────────────── */
fetch(window.TMAP_URL, { credentials: 'same-origin' })
  .then(function (r) { return r.json(); })
  .then(function (data) {
    groups = data.groups;
    nodes = data.nodes;
    links = data.links;

    nodes.forEach(function (n) {
      byId[n.id] = n;
      n.nl = norm(n.l);                       /* нормализованное имя для поиска */
      if (n.k === 'theme') themeList.push(n);
      else (tagsOfTheme[n.n] = tagsOfTheme[n.n] || []).push(n);
    });
    order = nodes.slice();

    links.forEach(function (ln) {
      if (ln.k !== 'cross') return;
      (nearOf[ln.s] = nearOf[ln.s] || []).push(ln.t);
      (nearOf[ln.t] = nearOf[ln.t] || []).push(ln.s);
    });

    readPalette();
    seedLayout();
    /* 300 итераций синхронно: карта открывается уже почти собранной. */
    settle(300);

    resize();
    computeFit();
    ready = true;
    renderHover(null);
    renderPicked();
    wake();

    var show = false;
    try { show = !localStorage.getItem(TOUR_KEY); } catch (e) { show = false; }
    if (show) setTimeout(tourStart, 400);
  })
  .catch(function (err) {
    ready = false;
    if (hoverBox) {
      hoverBox.innerHTML = '<div class="tmap-def">Карта не загрузилась: ' +
                           esc(err && err.message ? err.message : 'нет данных') + '</div>';
    }
  });

/* Отладочный доступ: числа для отчёта о приёмке. */
window.TMAP = {
  fps: function () { return fpsValue; },
  stats: layoutStats,
  nodes: function () { return nodes; },
  search: function (q) { return applySearch(q); },
  draw: function () { draw(); },
  /* Прямоугольники подписей тем после раздвижки — чтобы проверить, что ни
     одна не потерялась и ни одна не наехала на соседнюю. */
  themeBoxes: function () { draw(); return lastThemeBoxes.slice(lastThemeFrom); },
  /* Все подписи кадра — и тегов, и тем: они делят холст, и проверять их
     на пересечение надо вместе, а не по слоям. */
  allBoxes: function () { draw(); return lastThemeBoxes.slice(); },
  /* Стоимость кадра. Частоту через requestAnimationFrame в скрытой вкладке
     измерить нельзя — браузер её там не гоняет вовсе; поэтому меряем, во
     что обходится САМ кадр, и переводим в кадры в секунду. */
  bench: function (times) {
    times = times || 60;
    draw();                                  /* прогрев */
    var t0 = performance.now();
    for (var i = 0; i < times; i++) draw();
    var ms = (performance.now() - t0) / times;
    return { msPerFrame: +ms.toFixed(2), fps: Math.round(1000 / ms) };
  },
  focus: function (name) {
    var items = window.TMAP.focusBoxes(name);
    return items ? items.length : -1;
  },
  /* Прямоугольники подписей в фокус-режиме — чтобы проверить, что они не
     налезают друг на друга и что не пропущено ни одного тега. */
  focusBoxes: function (name) {
    for (var i = 0; i < themeList.length; i++) {
      if (themeList[i].nl.indexOf(norm(name)) < 0) continue;
      hoverNode = themeList[i]; focusTheme = themeList[i];
      rebuildHighlight();
      draw();                                /* проекция должна быть свежей */
      wake();
      var items = layoutFocusLabels(themeList[i]);
      return items.map(function (it) {
        ctx.font = '500 ' + LABEL_TAG_PX + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        var w = 0;
        it.lines.forEach(function (l) { w = Math.max(w, ctx.measureText(l).width); });
        var h = it.lines.length * LINE_H;
        return {
          id: it.node.id, label: it.node.l, lines: it.lines.length, side: it.side,
          left: it.side < 0 ? it.x - w : it.x, right: it.side < 0 ? it.x : it.x + w,
          top: it.y - h / 2, bottom: it.y + h / 2
        };
      });
    }
    return null;
  }
};

requestAnimationFrame(frame);

})();
