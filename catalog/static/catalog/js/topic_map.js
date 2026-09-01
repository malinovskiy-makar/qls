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
   У КАЖДОГО РАЗДЕЛА КОРПУСА СВОЙ ЦВЕТ, ИХ СЕМЬ. Тема и все её теги
   красятся цветом своего раздела; тема отличается от тега размером и
   непрозрачностью (1 против 0,72), а не оттенком. Всё подсвеченное
   рисуется акцентом платформы — акцент поверх цвета раздела, а не вместо
   него.

   Это ВОЗВРАТ, а не новинка: цвета уже были (ADR 0036), их сняли в пользу
   одного нейтрального `--map-node` (ADR 0038) с доводом «пестрит, а
   легенду никто не помнит». Довод оказался неполным: без цвета коллеге не
   за что зацепиться взглядом, карта читается как однородная сеть. Легенду
   в этот раз держит правая панель — заголовок раздела написан своим
   цветом, и подсказка всегда рядом с картой. См. ADR 0053.

   Сами значения — CSS-переменные `--map-g-*` в topic_map.css (не в общих
   токенах; почему — долг записан там же).

   ⚠️ ЛОВУШКА, ИЗ-ЗА КОТОРОЙ КАРТА ТЕРЯЛА КАДРЫ: строку цвета нельзя
   собирать на каждый узел каждый кадр — 372 разбора CSS-цвета за кадр
   стоят дороже всей остальной отрисовки. Поэтому цвет переводится в rgb
   ОДИН раз при чтении токенов, и заранее строится массив готовых строк
   'rgba(r,g,b,a)' по ступеням прозрачности; в кадре только индексация по
   номеру ступени. Семь цветов не меняют этого правила: массивов теперь
   семь, а в кадре по-прежнему только индексация. */

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
  /* ⚠️ ЧИТАЕМ У БЛОКА КАРТЫ, А НЕ У КОРНЯ ДОКУМЕНТА. Цвета разделов
     объявлены в скоупе `.tmap`, и с корня их не видно; общие токены сайта
     блок наследует, поэтому одного чтения хватает на всё. */
  var cs = getComputedStyle(root);
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
  PAL.borderShades = makeShades(hexToRgb(dark ? '#8e96a4' : '#5a6472'));

  /* ⚠️ В СВЕТЛОЙ ТЕМЕ РЁБРА РИСУЮТСЯ ПЛОТНЕЕ, И ЭТО НЕ ПРИХОТЬ.
     Тонкая линия в один пиксель на белом холсте видна заметно хуже, чем
     та же линия на тёмном: глаз хуже различает тёмное на светлом при
     малой площади. С прежними ступенями светлая карта выглядела почти без
     связей — узлы висели в пустоте. Ступени подобраны отдельно на тему. */
  PAL.edge = dark
    ? { far: 0.42, near: 0.90, cross: 0.75 }
    : { far: 0.58, near: 1.00, cross: 0.88 };
  PAL.edgeDim = dark
    ? { far: 0.14, near: 0.26, cross: 0.20 }
    : { far: 0.22, near: 0.38, cross: 0.30 };

  /* Подложка под подписью — цвет холста, чтобы текст не перечёркивался
     рёбрами (дефект Б). Прозрачность 0.88 задаётся здесь же. */
  PAL.plate = 'rgba(' + bg[0] + ',' + bg[1] + ',' + bg[2] + ',0.88)';

  /* Нейтральный цвет остаётся запасным: им рисуется узел, чей раздел
     почему-либо не нашёлся. Молча пропасть узел не должен. */
  PAL.node = hexToRgb(cs.getPropertyValue('--map-node') ||
                      (dark ? '#C8CEDA' : '#4A5260'));
  PAL.nodeShades = makeShades(PAL.node);

  /* Семь наборов ступеней — по одному на раздел. Ключ тот же, что в поле
     `g` у узла, поэтому в кадре не нужен ни поиск, ни разбор цвета. */
  PAL.groupShades = {};
  PAL.groupCss = {};
  for (var gi = 0; gi < groups.length; gi++) {
    var gk = groups[gi].k;
    var raw = cs.getPropertyValue('--map-g-' + gk);
    var col = raw && raw.trim() ? hexToRgb(raw) : PAL.node;
    PAL.groupShades[gk] = makeShades(col);
    PAL.groupCss[gk] = 'rgb(' + col.join(',') + ')';
  }

  /* Надписи-ориентиры по разделам — третий цвет карты, не узел и не
     подсветка (ADR 0046). Ступеней не нужно: прозрачность у них своя, и
     задаётся она globalAlpha сразу обоим проходам — обводке и заливке. */
  PAL.region = hexToRgb(cs.getPropertyValue('--map-region') ||
                        (dark ? '#6794C1' : '#3E6C99'));
  PAL.regionCss = 'rgb(' + PAL.region.join(',') + ')';

  /* Семейство шрифта — тем же путём, что и цвета: из токенов. */
  PAL.font = (cs.getPropertyValue('--font-ui') || '').trim() ||
             '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
}

/* ── Раскладка ───────────────────────────────────────────────────────── */

var R_SPHERE = 470;          /* радиус сферы тем */
var Y_SQUASH = 0.78;         /* сплющивание по вертикали */
/* ⚠️ ПРОСТОРНЕЕ ДЕЛАЕТ НЕ РАЗМЕР ОБЛАКА, А ЕГО ФОРМА, и это замер, а не
   рассуждение. Поднять все силы и длины разом бесполезно: обзор вписывает
   облако в холст (computeFit), и равномерно раздутая раскладка вернётся на
   экран ровно того же размера. Проверено — отталкивание +18 % вместе с
   перекрёстной нитью +15 % не сдвинули ни одного числа: узлов ближе 6 px
   друг к другу осталось 46 из 372, как и было.
   Расходится ровно то, что растёт ОТНОСИТЕЛЬНО остального. Здесь это венец
   тегов: он и есть длина связи тема→тег. Замер по числу узлов, у которых
   сосед ближе 6 px (меньше — лучше):
     46 + 5,5·n  (было)      46
     55 + 6,6·n  (+20 %)     32   ← взято
     58 + 7,0·n и пружина слабее  41
     60 + 7,2·n  (+30 %)     48
   Дальше +20 % венец начинает налезать на соседние темы, и теснота
   возвращается уже между темами, а не внутри них. */
var REP = 1450;              /* сила отталкивания */
var REP_CUT2 = 640000;       /* дальше 800 не считаем */
var K_TREE = 0.055;          /* пружина тема→тег */
var K_CROSS = 0.006, L_CROSS = 300;
var CENTER_PULL = 0.0016;
var DAMP = 0.82;

var alpha = 1;
var themeAffinity = [];      /* пары тем: {a, b, L, K, both} */

function tagRadius(count) {
  /* Венец тегов: у темы с 5 тегами ~88, с 18 — ~174. Он же длина связи
     тема→тег, и он же главный рычаг тесноты — см. замер выше. */
  return 55 + 6.6 * count;
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
  /* ⚠️ ПОСЛЕ ПРОГОНА РАСКЛАДКА ЗАМОРАЖИВАЕТСЯ (alpha = 0), А НЕ ДОСТЫВАЕТ
     В КАДРАХ. Раньше здесь оставалось 0.2, и симуляция доигрывала ещё
     секунду в цикле кадров. Теперь после прогона координаты растягиваются
     под форму холста (spreadCloud), и живая симуляция стянула бы их
     обратно к шару — растяжение продержалось бы ровно до первого кадра. */
  alpha = 0;
}

/* Центр облака — в начало координат. Камера смотрит в ноль, и если облако
   стоит смещённым, поле с одной стороны шире, чем с другой, а вписывание
   по половинам разлёта теряет ровно эту разницу. */
function recentre() {
  var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, z0 = 1e9, z1 = -1e9, i, n;
  for (i = 0; i < nodes.length; i++) {
    n = nodes[i];
    if (n.x < x0) x0 = n.x; if (n.x > x1) x1 = n.x;
    if (n.y < y0) y0 = n.y; if (n.y > y1) y1 = n.y;
    if (n.z < z0) z0 = n.z; if (n.z > z1) z1 = n.z;
  }
  var cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, cz = (z0 + z1) / 2;
  for (i = 0; i < nodes.length; i++) {
    n = nodes[i];
    n.x -= cx; n.y -= cy; n.z -= cz;
  }
}

/* Базовые координаты: от них считается растяжение под холст. Хранить их
   обязательно — иначе повторное растяжение (смена размера окна, будущая
   модалка) множилось бы на прежнее и облако уезжало бы в блин. */
function snapshotLayout() {
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    n.bx = n.x; n.by = n.y; n.bz = n.z;
  }
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

/* Стартовый ракурс. По нему считаются и растяжение облака, и обзор: это
   тот угол, под которым человек открывает карту. */
var START_YAW = 0.35, START_PITCH = -0.22;

var cam = {
  yaw: START_YAW, pitch: START_PITCH,
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
   Считается по СТАРТОВОМУ ракурсу, а не по текущему: минимум по восьми
   поворотам ужимал карту вчетверо (при развороте на 90° узлы подходят
   ближе к камере и разлёт на экране растёт), и весь корпус оказывался
   комком в середине пустого холста. Поворот человек делает сам и сам же
   видит, что уезжает за край, — а вот открыть карту он должен на всём
   корпусе сразу. */
var FIT_MARGIN = 0.08;       /* поле по каждому краю холста, доля стороны */
var fitScale = 1;

/* Половины разлёта облака на экране при стартовом ракурсе, zoom = 1 и
   fitScale = 1. Камера здесь не трогается вовсе: углы взяты из констант,
   и функцию можно звать в любой момент, не сохраняя и не восстанавливая
   состояние камеры. */
function viewSpread() {
  var cy = Math.cos(START_YAW), sy = Math.sin(START_YAW);
  var cp = Math.cos(START_PITCH), sp = Math.sin(START_PITCH);
  var hx = 1, hy = 1;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    var ax = n.x * cy + n.z * sy, az = -n.x * sy + n.z * cy;
    var ay = n.y * cp - az * sp, pz = n.y * sp + az * cp + DIST;
    if (pz < 60) continue;
    var s = FOCAL / pz;
    hx = Math.max(hx, Math.abs(ax * s));
    hy = Math.max(hy, Math.abs(ay * s));
  }
  return { hx: hx, hy: hy };
}

/* ⚠️ ФОРМА ОБЛАКА ПРИВОДИТСЯ К ФОРМЕ ХОЛСТА — САМИМИ КООРДИНАТАМИ, А НЕ
   МАСШТАБОМ КАМЕРЫ.
   Замер до правки: холст 911×534, узлы занимали 424×415 — 46,6 % ширины
   при 77,7 % высоты, то есть слева и справа по 240 px пустоты, а сверху и
   снизу впритык. Причина не в камере: силовая раскладка даёт облако,
   близкое к шару, а холст широкий (16:9). Обзор вписывается по узкой
   оси — по высоте, — и по ширине неизбежно остаётся пустота. Прибавить
   масштаб нельзя: узлы тут же уедут за верхний и нижний край.

   ⚠️ ПРИВОДИМ СЖАТИЕМ ПО ВЕРТИКАЛИ, А НЕ РАСТЯЖЕНИЕМ ПО ГОРИЗОНТАЛИ, И НА
   ТО ДВЕ ПРИЧИНЫ — обе проверены на живой карте.
   Первая: карта сама поворачивается вокруг вертикали. Растянутая
   горизонтальная ось через четверть оборота уходит в глубину, и граф
   снова становится узким столбиком; сжатие по вертикали от угла поворота
   не зависит вовсе.
   Вторая: горизонтальные оси участвуют в перспективе. Раздвигая узлы
   вбок, мы подводим часть из них вплотную к камере: замер показал разлёт
   7 744 px при доступных 383 — облако вывернулось наизнанку и вылезло за
   край на 184 % ширины. Вертикаль в знаменатель перспективы почти не
   входит, и сжатие по ней ведёт себя линейно.
   На экране это выглядит ровно как растяжение вбок: облако стало ниже,
   обзор — крупнее, и по горизонтали узлы разъехались вместе с местом для
   подписей.

   Проход не один: сжатие по Y всё же чуть меняет глубину, поэтому
   коэффициент уточняется, пока не сойдётся (обычно за два прохода). */
function spreadCloud() {
  var i, n0;
  for (i = 0; i < nodes.length; i++) {
    n0 = nodes[i];
    n0.x = n0.bx; n0.y = n0.by; n0.z = n0.bz;
  }

  /* Оси камеры в мировых координатах при стартовом ракурсе.
     ⚠️ СДВИГ ПО НИМ — ТОЧНЫЙ, И ЭТО НЕ СЛУЧАЙНОСТЬ. Обе оси
     перпендикулярны направлению взгляда: сдвиг вдоль «вправо» меняет
     ТОЛЬКО горизонталь на экране, сдвиг вдоль «вверх» — только вертикаль,
     а глубина (а значит, и перспектива, и размер узла) не меняется ни от
     того, ни от другого. Сдвиг по голым осям мира так не умеет. */
  var cy = Math.cos(START_YAW), sy = Math.sin(START_YAW);
  var cp = Math.cos(START_PITCH), sp = Math.sin(START_PITCH);
  var rx = cy, rz = sy;                       /* ось «вправо» */
  var ux = sy * sp, uy = cp, uz = -cy * sp;   /* ось «вверх»  */

  var want = W / H;                           /* форма холста */
  for (var pass = 0; pass < 8; pass++) {
    /* Собственно облако на экране: и края, и середина. */
    var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, sSum = 0, cnt = 0;
    for (i = 0; i < nodes.length; i++) {
      n0 = nodes[i];
      var ax = n0.x * cy + n0.z * sy, az = -n0.x * sy + n0.z * cy;
      var ay = n0.y * cp - az * sp, pz = n0.y * sp + az * cp + DIST;
      if (pz < 60) continue;
      var sc = FOCAL / pz, X = ax * sc, Y = ay * sc;
      sSum += sc; cnt++;
      if (X < x0) x0 = X; if (X > x1) x1 = X;
      if (Y < y0) y0 = Y; if (Y > y1) y1 = Y;
    }
    if (!cnt) return;
    var sAvg = sSum / cnt;

    /* ⚠️ СНАЧАЛА СЕРЕДИНА, ПОТОМ ФОРМА. Обзор вписывается по САМОМУ
       дальнему узлу от центра холста, а не по ширине облака: если облако
       стоит смещённым, половина поля с одной стороны пропадает впустую.
       Замер: смещение вниз на 65 px при половине разлёта 313 съедало
       пятую часть высоты — заполнение падало с 84 % до 66,6 %. */
    var dax = -((x0 + x1) / 2) / sAvg, day = -((y0 + y1) / 2) / sAvg;
    for (i = 0; i < nodes.length; i++) {
      n0 = nodes[i];
      n0.x += rx * dax + ux * day;
      n0.y += uy * day;
      n0.z += rz * dax + uz * day;
    }

    var m = (x1 - x0) / (want * (y1 - y0));   /* во сколько раз сжать вертикаль */
    if (m > 2.5) m = 2.5;
    if (m < 0.4) m = 0.4;
    for (i = 0; i < nodes.length; i++) { nodes[i].y *= m; }

    if (Math.abs(m - 1) < 0.004 && Math.abs(dax) < 1 && Math.abs(day) < 1) break;
  }
}

/* Обзор подбирается ПО ОБЕИМ ОСЯМ СРАЗУ: берётся меньший из двух
   масштабов, поэтому ни один узел не выходит за край ни по ширине, ни по
   высоте. Верхнего ограничения «не больше единицы» здесь нет намеренно:
   после растяжения облако вписывается в холст масштабом больше единицы,
   и прежний потолок оставил бы карту мелкой. */
function computeFit() {
  var sp = viewSpread();
  var availX = W * (0.5 - FIT_MARGIN);
  var availY = H * (0.5 - FIT_MARGIN);
  fitScale = Math.max(0.15, Math.min(4, Math.min(availX / sp.hx, availY / sp.hy)));
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

/* Та же проекция для одной произвольной точки — нужна подписям разделов:
   у раздела нет своего узла, его якорь — центр масс тем. */
function projectPoint(x, y, z, out) {
  var dx = x - cam.tx, dy = y - cam.ty, dz = z - cam.tz;
  var ax = dx * CY + dz * SY, az = -dx * SY + dz * CY;
  var ay = dy * CP - az * SP, pz = dy * SP + az * CP + DIST;
  if (pz < 60) { out.pz = -1; return out; }
  var s = FOCAL / pz * cam.zoom * fitScale;
  out.px = W / 2 + ax * s;
  out.py = H / 2 + ay * s;
  out.ps = s;
  out.pz = pz;
  return out;
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
var HIT_NODE = 10;           /* порог попадания по узлу, px             */
var HIT_EDGE = 6;            /* по связи — уже: линия тоньше кружка     */

function hitTest(mx, my) {
  var best = null, bestD = HIT_NODE;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    if (n.pz < 0) continue;
    var d = Math.hypot(n.px - mx, n.py - my) - Math.max(3, n.r0 * n.ps);
    if (d < bestD) { bestD = d; best = n; hitNodeDist = d; }
  }
  if (!best) hitNodeDist = 1e9;
  return best;
}

/* Насколько далеко был узел, выигравший последний hitTest. Нужно, чтобы
   решить спор «узел или связь» — см. pick() ниже. */
var hitNodeDist = 1e9;

/* Расстояние от точки до отрезка в экранных координатах. */
function distToSeg(px, py, x1, y1, x2, y2) {
  var dx = x2 - x1, dy = y2 - y1;
  var len2 = dx * dx + dy * dy;
  var t = len2 ? ((px - x1) * dx + (py - y1) * dy) / len2 : 0;
  t = t < 0 ? 0 : t > 1 ? 1 : t;
  var cx = x1 + t * dx, cy = y1 + t * dy;
  return Math.hypot(px - cx, py - cy);
}

/* ── Проходимые рёбра активного узла ──────────────────────────────────

   ⚠️ ЭТО ЗАМЕНА ПРЕЖНЕГО ПОВЕДЕНИЯ, А НЕ ДОБАВКА К НЕМУ. Раньше подсветка
   включалась от наведения на ЛЮБОЕ из 425 рёбер, и любое случайное движение
   мыши что-то подсвечивало — шум. Теперь модель другая: человек встаёт на
   узел и уходит от него ПО ЕГО ЛИНИЯМ, как по дорогам с перекрёстка.

   Отсюда и широкий коридор. Кандидатов теперь единицы — только рёбра
   active, а не сотни, — поэтому 16 px не создают конфликтов и попадать
   пиксель в пиксель не требуется. */
var HIT_CORRIDOR = 16;       /* коридор попадания вдоль ребра active, px */
var ROUTE_START = 20;        /* ближе к active маршрут не начинается    */
var ROUTE_ARRIVE_T = 0.78;   /* доля пути, после которой переходим      */
var ROUTE_ARRIVE_PX = 12;    /* или подошли к дальнему узлу ближе этого */

/* Доля вдоль отрезка, куда проецируется точка (0 — у первого конца). */
function projT(px, py, x1, y1, x2, y2) {
  var dx = x2 - x1, dy = y2 - y1;
  var len2 = dx * dx + dy * dy;
  if (!len2) return 0;
  var t = ((px - x1) * dx + (py - y1) * dy) / len2;
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

/* Ищем ребро active, в коридор которого попал курсор.
   ⚠️ ВПЛОТНУЮ К УЗЛУ МАРШРУТ НЕ НАЧИНАЕТСЯ. У тега сходится веером до
   десятка спиц, и в первых двадцати пикселях их коридоры перекрываются:
   курсор дребезжал бы между соседними линиями, не давая выбрать ни одну. */
function hitTestRoute(mx, my) {
  if (!active || active.pz <= 0) return null;
  var best = null, bestD = HIT_CORRIDOR;
  for (var i = 0; i < links.length; i++) {
    var ln = links[i];
    var a = byId[ln.s], b = byId[ln.t];
    var far;
    if (a === active) far = b;
    else if (b === active) far = a;
    else continue;                          /* чужие рёбра не проходимы */
    if (far.pz <= 0) continue;

    /* Быстрый отсев по рамке: расстояние считается только для тех
       отрезков, рядом с которыми курсор вообще может быть. */
    if (mx < Math.min(active.px, far.px) - HIT_CORRIDOR ||
        mx > Math.max(active.px, far.px) + HIT_CORRIDOR ||
        my < Math.min(active.py, far.py) - HIT_CORRIDOR ||
        my > Math.max(active.py, far.py) + HIT_CORRIDOR) continue;

    var d = distToSeg(mx, my, active.px, active.py, far.px, far.py);
    if (d > HIT_CORRIDOR) continue;

    var t = projT(mx, my, active.px, active.py, far.px, far.py);
    var len = Math.hypot(far.px - active.px, far.py - active.py);
    if (t * len < ROUTE_START) continue;    /* слишком близко к active */

    if (d < bestD) {
      bestD = d;
      best = { key: edgeKey(active.id, far.id), a: active, b: far,
               why: (ln.k === 'cross' ? (ln.w || '') : ''), link: ln,
               t: t, d: d, len: len,
               cx: active.px + (far.px - active.px) * t,
               cy: active.py + (far.py - active.py) * t };
    }
  }
  return best;
}

/* ── Кто старше: узел или линия ───────────────────────────────────────

   ⚠️ ЭТО ПРАВИЛО ПЕРЕПИСАНО ПОД МОДЕЛЬ ХОЖДЕНИЯ, и его прежний числовой
   вид («узел старше при равном или меньшем расстоянии», ADR 0045) здесь не
   работает. Причина: карта плотная, и чужие узлы стоят вплотную к линиям —
   на отрезке «Монопсония и покупательная власть» ↔ «Монопсония на рынке
   труда» лежат t8.8 в 5,0 px от линии, t10.2 в 2,6, t8.18 в 3,3, t10.3 в
   3,5. Пока старшинство решалось сравнением расстояний, они забирали
   курсор: по самой линии маршрут доходил до цели 3 раза из 20, а при
   небрежном ведении в 12 px от неё — ни разу.

   Дух ADR 0045 сохранён: узел НЕ забирает курсор, который явно целится в
   линию. Изменилась буква — вместо сравнения расстояний старшинство теперь
   такое:

     1. точное попадание в кружок (расстояние отрицательное) сильнее всего —
        так с маршрута можно сойти намеренно;
     2. иначе, если стоишь на узле и курсор в коридоре одной из ЕГО линий, —
        идёшь по линии;
     3. иначе ближняя зона своего узла принадлежит ему, а не соседям;
     4. и только потом — обычное попадание по узлу. */
function pick(mx, my) {
  var n = hitTest(mx, my);
  var e = active ? hitTestRoute(mx, my) : null;

  /* 1. Внутри кружка — это узел, и спорить не о чем. */
  if (n && hitNodeDist <= 0) return { node: n };

  if (active && active.pz > 0) {
    /* 2. В коридоре своей линии — идём по ней. */
    if (e) return { route: e };
    /* 3. Ближняя зона своего узла: там маршрут ещё не начинается (спицы
       сходятся веером), и отдавать её соседям нельзя — иначе путь рвётся
       на первом же шаге. */
    if (Math.hypot(mx - active.px, my - active.py) < ROUTE_START) {
      return { node: active };
    }
  }

  /* 4. Обычное попадание по узлу — так и входят в режим хождения. */
  if (n) return { node: n };
  return {};
}


/* ═══════════════════════════════════════════════════════════════════════
   ЧАСТЬ 3. ОТРИСОВКА
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Импульс по ребру ────────────────────────────────────────────────
   Когда тег выбирают в дереве, а не на холсте, связи с темой не видно: в
   списке они стоят рядом, а на карте могут оказаться в разных концах
   экрана. Импульс — точка, пробегающая по ребру от тега к его теме, —
   показывает принадлежность движением, не занимая места.
   ⚠️ ПРИ prefers-reduced-motion ИМПУЛЬСА НЕТ ВОВСЕ: он ничего не сообщает
   сверх подсветки, которая остаётся. */
var PULSE_MS = 620;          /* один пробег                             */
var PULSE_TIMES = 3;         /* столько раз                             */
var pulse = null;            /* {from, to, t0} либо null                */

/* Состояние подсветки. */
var picked = {};             /* id → true: выбранные теги и темы          */
/* ⚠️ ACTIVE — ЭТО НЕ «УЗЕЛ ПОД КУРСОРОМ», А «УЗЕЛ, НА КОТОРОМ ТЫ СТОИШЬ».
   Разница важна: курсор может уйти с узла вдоль линии, а стоишь ты всё ещё
   на нём. Войти в режим можно ТОЛЬКО через узел; ни одно ребро само по себе
   active не задаёт. */
var active = null;           /* узел, на котором стоит человек, либо null  */
var route = null;            /* ребро active, по которому идёт курсор      */
var focusTheme = null;       /* тема, у которой раскрыт список тегов      */
var searchHits = null;       /* null = поиск пуст; иначе объект id → true */

var order = [];              /* порядок отрисовки по глубине              */
var lastThemeBoxes = [];     /* занятые места последнего кадра (для замеров) */
var lastThemeFrom = 0;       /* с какого индекса в нём начинаются темы      */

/* Толщина главной дороги «тег → его тема». Прочие подсвеченные связи
   рисуются в 2,2 px; 3,8 отличается от них заметно и на глаз, и на
   замере — полторы толщины, а не десятая доля. */
var ROAD_HOME_WIDTH = 3.8;

/* Базовая непрозрачность узла: тема в полную силу, тег вполсилы с
   небольшим запасом. Это второй после размера признак «тема или тег» —
   цвет у них общий, раздела. */
var BASE_ALPHA_THEME = 1, BASE_ALPHA_TAG = 0.72;

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
  if (!any && !active) { litSet = litNear = litEdges = null; return; }

  litSet = {}; litNear = {}; litEdges = {};

  /* ⚠️ ПОДСВЕТКУ ЗАДАЁТ ТОЛЬКО ACTIVE, А НЕ МАРШРУТ. Пока курсор идёт по
     ребру, подсвечено ровно то же, что было на самом узле: маршрут —
     визуальный слой поверх, а не второй источник подсветки. Иначе картина
     перестраивалась бы на каждом шаге пути. */
  var seeds = [];
  for (k in picked) if (picked[k]) seeds.push(byId[k]);
  if (active) seeds.push(active);

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
        /* ⚠️ СВОЯ ТЕМА — ВТОРОЙ УРОВЕНЬ, А НЕ ПЕРВЫЙ. Тег и его тема
           отвечают на разные вопросы: тег это «вот что ты держишь», тема —
           «вот чьё оно». Гори они одинаково, глазу не за что зацепиться, и
           выбранный тег теряется рядом с крупным узлом темы. */
        litNear[parent.id] = true;
        /* ⚠️ ГЛАВНАЯ ДОРОГА ПОМЕЧАЕТСЯ ОТДЕЛЬНО (2, а не true). Связь тега
           со СВОЕЙ темой отвечает на вопрос «откуда этот тег», и среди
           десятка подсвеченных линий она обязана читаться первой. Одной
           толщиной со смежными связями она в них терялась. */
        litEdges[edgeKey(parent.id, n.id)] = 2;
      }
      /* Смежные теги — второй, тихий уровень. */
      (nearOf[n.id] || []).forEach(function (otherId) {
        litNear[otherId] = true;
        litEdges[edgeKey(n.id, otherId)] = 1;
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

/* Шрифт подписи. Разрядка (letterSpacing) нужна только надписям-
   ориентирам; там, где её нет, поле обязано сбрасываться в ноль — иначе
   она протекает на следующую подпись и на замер ширины.

   ⚠️ СЕМЕЙСТВО БЕРЁТСЯ ИЗ ТОКЕНА `--font-ui`, А НЕ ЗАШИТО ЗДЕСЬ. Раньше в
   этой строке стоял свой набор (-apple-system, Segoe UI), и подписи на
   холсте единственные на всём сайте рисовались НЕ фирменным шрифтом. На
   глаз это ловится плохо: системный гротеск похож на Montserrat ровно
   настолько, чтобы разницу списали на сглаживание холста. */
function setLabelFont(px, weight, spacing) {
  ctx.font = (weight || 500) + ' ' + px + 'px ' + PAL.font;
  ctx.letterSpacing = spacing ? (spacing * px).toFixed(2) + 'px' : '0px';
}

function drawLabelLines(lines, x, y, align, alpha, colour, px, weight, spacing, withPlate, halo) {
  setLabelFont(px, weight, spacing);
  ctx.textAlign = align;
  ctx.textBaseline = 'middle';
  var wMax = 0;
  for (var i = 0; i < lines.length; i++) {
    wMax = Math.max(wMax, ctx.measureText(lines[i]).width);
  }
  var hAll = lines.length * LINE_H;
  var px0 = align === 'right' ? x - wMax : (align === 'center' ? x - wMax / 2 : x);
  ctx.globalAlpha = alpha;
  /* Подложка цвета холста рисуется ДО текста и поверх рёбер — иначе буквы
     перечёркиваются спицами и линиями. Надписям-ориентирам она не нужна:
     ⚠️ ПЛАШКА ВЫРЕЗАЛА БЫ В ГРАФЕ ПРЯМОУГОЛЬНЫЕ ДЫРЫ. Ориентир широкий, и
     под ним всегда есть линии и узлы; закрасив их фоном, мы порвали бы граф
     ради подписи. Читаемость даёт ОБВОДКА: она облегает буквы и оставляет
     всё между ними видимым. */
  if (withPlate !== false) plate(px0 - 4, y - hAll / 2 - 2, wMax + 8, hAll + 4);

  var ty;
  /* ⚠️ ОБВОДКА И ЗАЛИВКА ИДУТ ПОД ОДНОЙ И ТОЙ ЖЕ ПРОЗРАЧНОСТЬЮ, и меняется
     она ОДИН раз на оба прохода. Задай их порознь — на просвет вылезет
     ореол: полупрозрачная обводка проступит из-под полупрозрачных букв
     светлым контуром. */
  if (halo) {
    ctx.strokeStyle = PAL.bgCss;
    ctx.lineWidth = halo;
    ctx.lineJoin = 'round';
    ctx.miterLimit = 2;
    for (i = 0; i < lines.length; i++) {
      ty = y - hAll / 2 + LINE_H / 2 + i * LINE_H;
      ctx.strokeText(lines[i], x, ty);
    }
    ctx.lineWidth = 1;
    ctx.lineJoin = 'miter';
  }

  ctx.fillStyle = colour;
  for (i = 0; i < lines.length; i++) {
    ctx.fillText(lines[i], x, y - hAll / 2 + LINE_H / 2 + i * LINE_H);
  }
  ctx.globalAlpha = 1;
  ctx.letterSpacing = '0px';
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
    setLabelFont(LABEL_TAG_PX, 500, 0);
    var wMax = 0;
    var items = list.map(function (t) {
      var lines = wrapLabel(t.l, TAG_WRAP_CHARS, 2);
      var w = 0;
      for (var i = 0; i < lines.length; i++) {
        w = Math.max(w, ctx.measureText(lines[i]).width);
      }
      if (w > wMax) wMax = w;
      return { node: t, lines: lines, w: w,
               h: lines.length > 1 ? ROW_MIN_2 : ROW_MIN, y: t.py };
    });

    /* Раздвигаем по вертикали, центрируя разброс вокруг исходного y.
       ⚠️ СТОЛБИК ПРИЖИМАЕТСЯ К ХОЛСТУ, А НЕ ВЫЕЗЖАЕТ ЗА НЕГО. У темы,
       стоящей у верхнего или нижнего края, половина имён уходила за кадр
       молча — на глаз это читалось как «у темы меньше тегов». */
    var total = items.reduce(function (s, it) { return s + it.h; }, 0);
    var start = theme.py - total / 2;
    if (start < 12) start = 12;
    if (start + total > H - 12) start = Math.max(12, H - 12 - total);
    var y = start;
    items.forEach(function (it) {
      it.y = y + it.h / 2;
      y += it.h;
    });

    /* ⚠️ И ПО ГОРИЗОНТАЛИ ТОЖЕ. Колонка стоит на COL_DX от узла, но у тем
       ближе к краю холста самое длинное имя не помещалось: замер — семь
       тем из 29 обрезались, у «Олигополии и теории игр» правая колонка
       уходила за край на 141 px. Двигаем всю колонку целиком, чтобы
       имена остались на одной вертикали. */
    var x = theme.px + (side < 0 ? -COL_DX : COL_DX);
    if (side < 0) x = Math.max(x, wMax + 8);
    else x = Math.min(x, W - wMax - 8);
    items.forEach(function (it) { it.x = x; it.side = side; });
    return items;
  }

  return place(left, -1).concat(place(right, 1));
}

/* ── Кадр ────────────────────────────────────────────────────────────── */

/* ── Надписи-ориентиры по разделам ────────────────────────────────────
   Семь названий разделов корпуса вместо двадцати девяти имён тем. Вид
   намеренно другой: прописные, разрядка, вполсилы — это ориентир, как
   название страны на карте, а не подпись объекта. */
var GROUP_PX = 17;           /* кегль надписи раздела                   */
var GROUP_SPACING = 0.07;    /* разрядка, доля кегля                    */
var GROUP_ALPHA = 0.62;      /* в покое, у САМОГО БЛИЖНЕГО раздела      */
var GROUP_ALPHA_DIM = 0.28;  /* при любой подсветке — остаётся фоном    */
/* ── Ориентир гаснет с глубиной ───────────────────────────────────────
   ⚠️ РАНЬШЕ ВСЕ СЕМЬ НАДПИСЕЙ ГОРЕЛИ ОДИНАКОВО И ВСЕГДА, и это был дефект:
   сцена поворачивается, скопления меняются местами, а подписи стоят как
   вкопанные. Хуже того, надпись раздела, уехавшего ЗА граф, проецируется в
   середину экрана поверх чужих узлов и врёт про то, что под ней.
   Теперь у каждой надписи свой вес по глубине её скопления в ТЕКУЩЕЙ
   ориентации: ближнее скопление подписано в полную силу, дальнее тает, а
   то, что ушло за спину, не рисуется вовсе. При повороте набор ярких
   надписей меняется сам — считать его отдельно не нужно. */
var GROUP_DEPTH_FLOOR = 0.34;   /* во сколько раз тише самый дальний   */
var GROUP_DEPTH_DROP = 0.16;    /* ниже этой доли не рисуем вовсе      */
var GROUP_HALO = 3;          /* толщина обводки цветом холста, px       */
/* Вблизи ориентир уже не нужен: человек смотрит на конкретные узлы.
   Гаснет не щелчком на пороге, а рампой, иначе дрожание масштаба около
   порога читалось бы как мигание. */
var GROUP_ZOOM_FROM = 1.9, GROUP_ZOOM_TO = 2.2;

var EDGE_LABEL_PX = 11;      /* пояснение связи                         */
var EDGE_LABEL_ALPHA = 0.85;

var gAnchor = { px: 0, py: 0, pz: 1, r: 0, cx: 0, cy: 0 };

var LABEL_BUDGET = 90;       /* лимит подписей тегов на кадр            */
var LABEL_MAX_AWAY = 90;     /* дальше подпись от своего узла не уходит */
var LABEL_LEADER_MIN = 24;   /* ближе выноска не нужна                  */
var THEME_QUIET_ALPHA = 0.3; /* чужое имя темы в фокус-режиме           */

/* Счётчики последнего кадра — для приёмки через window.TMAP. */
var lastQuietCount = 0;      /* приглушённых имён тем                   */
var lastThemeMissing = 0;    /* подписей, которым места не нашлось      */
var lastThemeMissingNames = [];
var lastThemeAway = 0;       /* самая дальняя подпись от узла, px       */

/* ═══════════════════════════════════════════════════════════════════════
   ПАМЯТЬ ПОДПИСЕЙ

   ⚠️ РАНЬШЕ МЕСТО ДЛЯ ПОДПИСИ ИСКАЛОСЬ ЗАНОВО КАЖДЫЙ КАДР, И ЭТО БЫЛО
   ПРИЧИНОЙ ДРОЖАНИЯ. Узел сдвигался на полпикселя — алгоритм находил уже
   другое свободное место, и текст перепрыгивал. Плюс подписи включались и
   выключались мгновенно, а глаз читает мгновенное включение как рывок.

   Теперь у каждой подписи есть объект, который живёт МЕЖДУ кадрами:

     key      — id узла, id ребра или ключ раздела: по нему подпись
                находится в следующем кадре и НЕ создаётся заново;
     kind     — 'group' | 'theme' | 'tag' | 'edge';
     ax, ay   — якорь: экранная позиция узла, середины ребра или облака;
     ox, oy   — где подпись стоит СЕЙЧАС относительно якоря;
     tox, toy — куда её положила раскладка (цель);
     alpha    — какая она сейчас; talpha — какой должна стать;
     placedAt — когда раскладка считалась в последний раз.

   Рисуем всегда в (ax + ox, ay + oy) — то есть там, где подпись доехала,
   а не там, куда раскладка положила её прямо сейчас. */
var LB = {};                 /* key → объект подписи                    */

var LB_FADE = 0.18;          /* шаг прозрачности за кадр                */
var LB_SLIDE = 0.2;          /* доля пути к цели за кадр                */
/* ⚠️ ПОТОЛОК 2 px, А НЕ 3, И ЭТО ПО ОТСМОТРУ ВЛАДЕЛЬЦА. При 3 px за кадр
   подпись движется со скоростью 180 px/с, и это читалось не как «едет за
   узлом», а как «уползает». */
var LB_SLIDE_MAX = 2;        /* и не больше 2 px за кадр                */
/* ⚠️ МЁРТВАЯ ЗОНА. Раскладка каждые 180 мс возвращает чуть иную цель — на
   полпикселя-пиксель, — и подпись бесконечно подрагивала, догоняя её.
   Разница меньше 2 px не двигает подпись вовсе. */
var LB_DEAD = 2;             /* ближе этого к цели не шевелимся, px     */
var LB_MIN_ALPHA = 0.02;     /* ниже — не рисуем и места не занимаем    */

var lbJumpMax = 0;           /* самый большой шаг ox/oy — для приёмки   */

function labelOf(key, kind, text) {
  var L = LB[key];
  if (!L) {
    L = LB[key] = { key: key, kind: kind, text: text,
                    ax: 0, ay: 0, ox: 0, oy: 0, tox: 0, toy: 0,
                    alpha: 0, talpha: 0, placedAt: 0,
                    w: 0, h: LINE_H, born: true };
  }
  if (L.text !== text) { L.text = text; L.w = 0; }
  L.kind = kind;
  return L;
}

/* Шаг анимации подписей. Живёт в цикле кадра, а НЕ в draw(): draw() зовут
   ещё и замеры (TMAP.bench гоняет её шестьдесят раз подряд), и анимация
   внутри неё пролетала бы шестьдесят шагов за один кадр. */
function labelTick() {
  var k, L, dx, dy, mx, my;
  for (k in LB) {
    L = LB[k];
    L.alpha += (L.talpha - L.alpha) * LB_FADE;
    dx = L.tox - L.ox; dy = L.toy - L.oy;
    /* Мёртвая зона: цель почти там же, где подпись, — не шевелимся.
       ⚠️ Это НЕ выход из шага: погасшую подпись всё равно надо выбросить
       ниже, иначе объекты копятся без конца. */
    if (Math.abs(dx) >= LB_DEAD || Math.abs(dy) >= LB_DEAD) {
      mx = dx * LB_SLIDE; my = dy * LB_SLIDE;
      if (mx > LB_SLIDE_MAX) mx = LB_SLIDE_MAX;
      else if (mx < -LB_SLIDE_MAX) mx = -LB_SLIDE_MAX;
      if (my > LB_SLIDE_MAX) my = LB_SLIDE_MAX;
      else if (my < -LB_SLIDE_MAX) my = -LB_SLIDE_MAX;
      L.ox += mx; L.oy += my;
      var jump = Math.max(Math.abs(mx), Math.abs(my));
      if (jump > lbJumpMax) lbJumpMax = jump;
    }
    /* Погасшую подпись выбрасываем: иначе объекты копятся без конца. */
    if (L.talpha < LB_MIN_ALPHA && L.alpha < LB_MIN_ALPHA) delete LB[k];
  }
}

/* Едет ли ещё хоть одна подпись: пока едет — кадр нужен. */
function labelsBusy() {
  for (var k in LB) {
    var L = LB[k];
    if (Math.abs(L.talpha - L.alpha) > 0.004) return true;
    if (Math.abs(L.tox - L.ox) > 0.4 || Math.abs(L.toy - L.oy) > 0.4) return true;
  }
  return false;
}

/* Досчитать анимацию до конца одним махом — для приёмки: инварианты
   меряются «в покое», а не через двадцать кадров плавного проявления. */
function labelSettle() {
  var k, L;
  for (var pass = 0; pass < 200; pass++) labelTick();
  for (k in LB) { L = LB[k]; L.alpha = L.talpha; L.ox = L.tox; L.oy = L.toy; }
}

/* ── Спокойствие сцены ───────────────────────────────────────────────── */

/* Скорость сцены за кадр: повороты в радианах плюс изменение масштаба.
   ⚠️ ПОРОГ ВЫШЕ СКОРОСТИ АВТОВРАЩЕНИЯ (0,00088), И ЭТО НАРОЧНО. Тихое
   вращение подписи НЕ гасит: они просто плавно едут за своими узлами.
   Гаснут только от активного движения — тянут мышью, крутят колесо,
   летит камера после двойного клика. */
var SPEED_QUIET = 0.0016;    /* рад/кадр: граница «сцена спокойна»      */
var CALM_MS = 150;           /* столько тишины до возвращения подписей  */
var LAYOUT_MS = 180;         /* реже раскладку не пересчитываем         */

/* Часы кадра. ⚠️ ОДНИ НА ВСЕХ: скорость сцены, возвращение подписей и
   пересчёт раскладки обязаны мерить время по одному и тому же источнику,
   иначе замер прогоняет сцену по виртуальным часам, а раскладку — по
   настоящим, и числа расходятся. */
var frameNow = 0;
var sceneSpeed = 0;          /* скорость последнего кадра               */
var lastYaw = START_YAW, lastPitch = START_PITCH, lastZoom = 1;
var lastLoudAt = -1e9;       /* когда сцена в последний раз шумела      */
var labelsCalm = true;       /* можно ли показывать фоновые подписи     */
var labelLayoutAt = -1e9;    /* когда раскладывали в последний раз      */
var labelSig = '';           /* состав подписей прошлого кадра          */

function sceneTick(now) {
  var d = Math.abs(cam.yaw - lastYaw) + Math.abs(cam.pitch - lastPitch) +
          Math.abs(cam.zoom - lastZoom) * 0.5;
  lastYaw = cam.yaw; lastPitch = cam.pitch; lastZoom = cam.zoom;
  sceneSpeed = d;
  if (d > SPEED_QUIET) lastLoudAt = now;
  labelsCalm = (now - lastLoudAt) >= CALM_MS;
}

function draw() {
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.fillStyle = PAL.bgCss;
  ctx.fillRect(0, 0, W, H);

  camPrepare();
  project();

  var dim = !!(litSet || searchHits);
  /* Сила подсветки. Пока она гаснет, карта плавно возвращается к обычному
     виду: подсвеченное теряет акцент, приглушённое — приглушение. */
  var hl = dim ? hlAlpha : 0;

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
    if (lit) {
      roads.push({ a: a, b: b, k: ln.k, key: edgeKey(a.id, b.id),
                   home: lit === 2 });
      continue;
    }
    var path;
    if (ln.k === 'cross') path = pCross;
    else path = ((a.pz + b.pz) / 2 < DIST) ? pNear : pFar;
    path.moveTo(a.px, a.py);
    path.lineTo(b.px, b.py);
  }

  var ed = dim ? PAL.edgeDim : PAL.edge;
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  ctx.strokeStyle = PAL.borderShades[shadeIndex(ed.far)];
  ctx.stroke(pFar);
  ctx.strokeStyle = PAL.borderShades[shadeIndex(ed.near)];
  ctx.stroke(pNear);
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = PAL.borderShades[shadeIndex(ed.cross)];
  ctx.stroke(pCross);
  ctx.setLineDash([]);

  /* Подсвеченные дороги — их единицы, поэтому штучно и акцентом.
     Прямая дорога тема→тег сплошная и в полную силу; смежный тег из
     чужой темы — тот же акцент, но пунктиром и вполсилы: связь по смыслу
     слабее принадлежности теме, и на глаз это должно быть видно. */
  for (i = 0; i < roads.length; i++) {
    var rd = roads[i];
    ctx.strokeStyle = PAL.accentShades[shadeIndex(0.95 * hl)];
    ctx.lineWidth = 2.2;
    /* Дорога тега к своей теме — толще и в полную силу: это ответ на
       вопрос «откуда он», и он важнее прочих подсвеченных связей. */
    if (rd.home) {
      ctx.lineWidth = ROAD_HOME_WIDTH;
      ctx.strokeStyle = PAL.accentShades[shadeIndex(hl)];
    }
    if (rd.k === 'cross') {
      /* Пунктир остаётся пунктиром: он означает «связь по смыслу», а не
         «принадлежность теме», и менять его значение при наведении — врать
         про природу линии. */
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = PAL.accentShades[shadeIndex(0.5 * hl)];
    }
    ctx.beginPath();
    ctx.moveTo(rd.a.px, rd.a.py);
    ctx.lineTo(rd.b.px, rd.b.py);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.lineWidth = 1;

  /* ── Маршрут: линия, по которой человек идёт прямо сейчас ────────────
     Рисуется ПОСЛЕ всех прочих рёбер и СПЛОШНОЙ, даже если это пунктирная
     перекрёстная связь: пунктир говорит, какого рода связь, а сплошная
     жирная линия — «ты сейчас идёшь здесь». Второе важнее в момент пути. */
  if (route && hl > 0.01 && route.a.pz > 0 && route.b.pz > 0) {
    ctx.strokeStyle = PAL.accentShades[shadeIndex(hl)];
    ctx.lineWidth = 3;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(route.a.px, route.a.py);
    ctx.lineTo(route.b.px, route.b.py);
    ctx.stroke();
    ctx.lineWidth = 1;

    /* Каретка — проекция курсора на линию. Она делает движение
       буквальным: видно не только КУДА идёшь, но и ГДЕ ты на пути. */
    ctx.fillStyle = PAL.accentShades[shadeIndex(hl)];
    ctx.beginPath();
    ctx.arc(route.cx, route.cy, 4, 0, 6.283185307179586);
    ctx.fill();
  }

  /* ── Импульс: бежит по ребру от тега к его теме ──────────────────── */
  if (pulse && !reduceMotion) {
    var age = (frameNow || performance.now()) - pulse.t0;
    if (age > PULSE_MS * PULSE_TIMES) {
      pulse = null;
    } else if (pulse.from.pz > 0 && pulse.to.pz > 0) {
      var k = (age % PULSE_MS) / PULSE_MS;
      /* Ход не линейный: точка выходит быстро и подходит к теме мягко —
         так читается направление, а не просто мигание. */
      var ease = 1 - Math.pow(1 - k, 3);
      var ux = pulse.from.px + (pulse.to.px - pulse.from.px) * ease;
      var uy = pulse.from.py + (pulse.to.py - pulse.from.py) * ease;
      ctx.fillStyle = PAL.accentShades[shadeIndex(1 - k * 0.55)];
      ctx.beginPath();
      ctx.arc(ux, uy, 4.5 - k * 1.5, 0, 6.283185307179586);
      ctx.fill();
    }
  }

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
    /* ⚠️ ПРИГЛУШЕНИЕ СМЕШИВАЕТСЯ С ОБЫЧНЫМ ВИДОМ ПО СИЛЕ ПОДСВЕТКИ, а не
       включается щелчком. Иначе после соскальзывания с линии карта
       возвращалась бы к обычному виду рывком, ровно тем самым миганием,
       ради которого и заведена липкость. */
    a2 = a2 * hl + (1 - hl);
    /* Тема и тег отличаются РАЗМЕРОМ И СИЛОЙ ЦВЕТА, а не оттенком: цвет
       у всех один. Базовая непрозрачность домножается на состояние. */
    a2 *= n.k === 'theme' ? BASE_ALPHA_THEME : BASE_ALPHA_TAG;

    /* Подсветка — всегда акцент, и наведение, и выбор, и найденное
       поиском: один цвет на все случаи, чтобы человек не гадал, что
       означает второй. Акцент кладётся ПОВЕРХ цвета раздела с силой
       подсветки: так он не переключается, а проступает и тает, и под ним
       остаётся видно, какого раздела узел. */
    var hot = dim && (on || near);
    ctx.fillStyle = (PAL.groupShades[n.g] || PAL.nodeShades)[shadeIndex(a2)];
    ctx.beginPath();
    ctx.arc(n.px, n.py, r, 0, 6.283185307179586);
    ctx.fill();
    if (hot && hl > 0.01) {
      ctx.fillStyle = PAL.accentShades[shadeIndex(a2 * hl)];
      ctx.beginPath();
      ctx.arc(n.px, n.py, r, 0, 6.283185307179586);
      ctx.fill();
    }

    if (picked[n.id]) {
      /* Ореол и обводка — тем же акцентом: выбранное видно всегда. */
      ctx.strokeStyle = PAL.accentShades[shadeIndex(0.35)];
      ctx.lineWidth = 5;
      ctx.beginPath(); ctx.arc(n.px, n.py, r + 3.5, 0, 6.283185307179586); ctx.stroke();
      ctx.strokeStyle = PAL.accentCss;
      ctx.lineWidth = 1.8;
      ctx.beginPath(); ctx.arc(n.px, n.py, r + 2, 0, 6.283185307179586); ctx.stroke();
      ctx.lineWidth = 1;
    } else if (n === active) {
      ctx.strokeStyle = PAL.accentShades[shadeIndex(0.8 * hl)];
      ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.arc(n.px, n.py, r + 2.5, 0, 6.283185307179586); ctx.stroke();
      ctx.lineWidth = 1;
    }
  }

  drawLabels(dim);
}

/* Просвет между узлом и подписью: расстояние от центра узла до ближней
   точки прямоугольника подписи. Ноль — подпись накрывает узел. Это же
   число — длина выноски, поэтому ограничение радиуса и длина выноски
   меряются одним и тем же. */
function labelGap(node, cx, cy, w, h) {
  var dx = Math.max(Math.abs(node.px - cx) - w / 2, 0);
  var dy = Math.max(Math.abs(node.py - cy) - h / 2, 0);
  return Math.hypot(dx, dy);
}

/* ── Якорь подписи раздела ────────────────────────────────────────────
   Раздел — не узел, у него нет своего места на карте. Его якорь: центр
   масс ТЕМ раздела в трёхмерных координатах, спроецированный на экран и
   приподнятый на 0,6 экранного радиуса ОБЛАКА раздела (тем и их тегов).
   Приподнятый — потому что надпись-ориентир стоит НАД скоплением, как
   название страны над её городами, а не поверх них. */
var groupPt = { px: 0, py: 0, ps: 1, pz: 1 };

function groupAnchor(g, out) {
  var i, j, th, tags, cnt = 0, sx = 0, sy = 0, sz = 0;
  for (i = 0; i < g.themes.length; i++) {
    th = byId['t' + g.themes[i]];
    if (!th) continue;
    sx += th.x; sy += th.y; sz += th.z; cnt++;
  }
  if (!cnt) { out.pz = -1; return out; }
  projectPoint(sx / cnt, sy / cnt, sz / cnt, groupPt);
  if (groupPt.pz < 0) { out.pz = -1; return out; }
  /* Дальше нужны экранные центры соседей — см. подъём ниже. */

  /* Экранный радиус облака.
     ⚠️ СРЕДНЕКВАДРАТИЧНЫЙ, А НЕ МАКСИМАЛЬНЫЙ. По максимуму один-
     единственный далеко улетевший тег раздувал радиус вчетверо (у «Фирмы
     и структур рынка» 520 px против 190 по среднему), и надпись улетала
     на треть холста от своего скопления. Среднеквадратичное расстояние
     описывает облако, а не его самый дальний выброс. */
  var s2 = 0, m = 0;
  for (i = 0; i < g.themes.length; i++) {
    th = byId['t' + g.themes[i]];
    if (!th || th.pz < 0) continue;
    s2 += (th.px - groupPt.px) * (th.px - groupPt.px) +
          (th.py - groupPt.py) * (th.py - groupPt.py);
    m++;
    tags = tagsOfTheme[g.themes[i]] || [];
    for (j = 0; j < tags.length; j++) {
      if (tags[j].pz < 0) continue;
      s2 += (tags[j].px - groupPt.px) * (tags[j].px - groupPt.px) +
            (tags[j].py - groupPt.py) * (tags[j].py - groupPt.py);
      m++;
    }
  }
  var R = m ? Math.sqrt(s2 / m) : 0;

  /* ⚠️ ПОДЪЁМ ОГЛЯДЫВАЕТСЯ НА СОСЕДЕЙ, А НЕ ТОЛЬКО НА СВОЙ РАДИУС.
     Облака разделов на экране пересекаются: центры масс «Основ и выбора»
     и «Рынка и потребителя» отстоят на 49 px. Подъём на 0,6 радиуса уводил
     надпись мимо своего скопления прямо к чужому — у трёх разделов из семи
     она оказывалась ближе к чужому центру масс, чем к своему.

     Сколько поднимать можно, считается точно, а не на глаз. Надпись стоит
     в (cx, cy − h); чужой центр в (ox, oy); dx = cx − ox, dy = cy − oy.
     Условие «ближе к своему» h² < dx² + (dy − h)² сводится к
     2·h·dy < dx² + dy². Соседи НИЖЕ нас (dy ≤ 0) подъёму не мешают вовсе,
     а каждый сосед выше даёт свой потолок D²/(2·dy). */
  var lift = R * 0.6;
  for (i = 0; i < groups.length; i++) {
    if (groups[i].k === g.k) continue;
    var o = groupCentre(groups[i], groupOther);
    if (o.pz < 0) continue;
    var dx = groupPt.px - o.px, dy = groupPt.py - o.py;
    if (dy <= 0) continue;                    /* сосед ниже — не мешает */
    var cap = (dx * dx + dy * dy) / (2 * dy) * 0.9;   /* с полем в 10 % */
    if (cap < lift) lift = cap;
  }
  if (lift < 0) lift = 0;

  out.px = groupPt.px;
  out.py = groupPt.py - lift;
  out.pz = groupPt.pz;
  out.r = R;
  out.lift = lift;
  out.cx = groupPt.px;
  out.cy = groupPt.py;
  return out;
}

/* Только центр масс раздела, без радиуса и подъёма: нужен и самому
   groupAnchor (чтобы оглядываться на соседей), и сторожу раскладки. */
var groupOther = { px: 0, py: 0, pz: 1 };

function groupCentre(g, out) {
  var cnt = 0, sx = 0, sy = 0, sz = 0, th;
  for (var i = 0; i < g.themes.length; i++) {
    th = byId['t' + g.themes[i]];
    if (!th) continue;
    sx += th.x; sy += th.y; sz += th.z; cnt++;
  }
  if (!cnt) { out.pz = -1; return out; }
  return projectPoint(sx / cnt, sy / cnt, sz / cnt, out);
}

/* Сторож надписи-ориентира: точка годится, только если она ближе к центру
   масс СВОЕГО раздела, чем к центру масс любого чужого. Это и есть
   инвариант «надпись принадлежит своему скоплению», проверяемый прямо, а
   не через запас по расстоянию. Соседние центры снимаются один раз на
   кадр: внутри перебора позиций их пересчёт стоил бы семикратно. */
function groupGuard(g, cx, cy) {
  var others = [];
  for (var i = 0; i < groups.length; i++) {
    if (groups[i].k === g.k) continue;
    var o = groupCentre(groups[i], { });
    if (o.pz > 0) others.push([o.px, o.py]);
  }
  return function (x, y) {
    var own = (x - cx) * (x - cx) + (y - cy) * (y - cy);
    for (var j = 0; j < others.length; j++) {
      var dx = x - others[j][0], dy = y - others[j][1];
      if (dx * dx + dy * dy <= own) return false;
    }
    return true;
  };
}

/* ── Поиск свободного места ───────────────────────────────────────────
   Позиции перебираются по возрастанию смещения от исходной, берётся
   первая свободная ОТ ВСЕХ уже размещённых. Отпрыгивание «от первой
   помехи» здесь не годится: оно загоняет подпись в объятия второй, та
   отправляет обратно к первой, попытки кончаются — и подпись остаётся
   лежать поверх соседки (замер на 29 подписях: 16 пересечений).

   ⚠️ РАДИУС ПОИСКА ОГРАНИЧЕН. Двумерный поиск без ограничения доводил
   пересечения до нуля ценой смысла: подпись уезжала к краю холста, а её
   узел оставался в середине, и выноска читалась как случайная линия.
   Дальше maxAway от своего узла подпись не ставится ВОВСЕ: имя без
   адреса хуже, чем его отсутствие. */
function findSpot(x0, y0, w, h, node, maxAway, placed, guard) {
  var half = w / 2 + 5;
  var STEP_Y = LINE_H + 5, STEP_X = 24;
  for (var d = 0; d <= 14; d++) {
    for (var sx = 0; sx <= d; sx++) {
      var dy = d - sx;
      var xs = sx === 0 ? [0] : [-sx, sx];
      var ys = dy === 0 ? [0] : [-dy, dy];
      for (var a1 = 0; a1 < xs.length; a1++) {
        for (var a2 = 0; a2 < ys.length; a2++) {
          var cx = x0 + xs[a1] * STEP_X, cy = y0 + ys[a2] * STEP_Y;
          if (cy - h / 2 < 6 || cy + h / 2 > H - 6) continue;
          if (cx - half < 4 || cx + half > W - 4) continue;
          /* ⚠️ Меряем до БЛИЖНЕЙ КРОМКИ подписи, а не до её середины: ровно
             это расстояние человек видит — оно и есть длина выноски. */
          if (node && labelGap(node, cx, cy, w, h) > maxAway) continue;
          /* Сторож: у надписи-ориентира нет своего узла, зато есть своё
             скопление, с которого она не должна сходить. */
          if (guard && !guard(cx, cy)) continue;
          var clear = true;
          for (var b = 0; b < placed.length; b++) {
            var pb = placed[b];
            if (Math.abs(pb.x - cx) < half + pb.w / 2 + 5 &&
                Math.abs(pb.y - cy) < (pb.h + h) / 2 + 4) { clear = false; break; }
          }
          if (clear) return [cx, cy];
        }
      }
    }
  }
  return null;
}

function drawLabels(dim) {
  var i, k, L;
  var now = frameNow || performance.now();

  /* ⚠️ ВСЕ ПОДПИСИ ДЕЛЯТ ОДИН ХОЛСТ, ЗНАЧИТ И ОДИН СПИСОК ЗАНЯТЫХ МЕСТ.
     Пока каждый слой раскладывался сам по себе, они честно не пересекались
     внутри себя и дружно налезали друг на друга. */
  var placed = [];

  /* ── 1. Кто вообще должен быть виден ─────────────────────────────────
     ⚠️ ИМЁН ТЕМ И ТЕГОВ В ПОКОЕ БОЛЬШЕ НЕТ. Двадцать девять подписей во
     вращающейся сцене читались как каша: ни один живой аналог столько
     текста в движении не держит (3d-force-graph, Obsidian, Map of Reddit,
     Embedding Projector — обзор владельца, ADR 0039). Вместо них семь
     надписей-ориентиров по разделам корпуса, как названия стран на карте.
     Имя темы или тега появляется ровно в четырёх случаях, и все четыре —
     по воле человека: узел под курсором, связь под курсором, узел выбран,
     узел найден поиском. */
  var want = [];
  var lit = !!(litSet || searchHits);

  /* Разделы. */
  var zoomFade = 1 - (cam.zoom - GROUP_ZOOM_FROM) / (GROUP_ZOOM_TO - GROUP_ZOOM_FROM);
  if (zoomFade > 1) zoomFade = 1; else if (zoomFade < 0) zoomFade = 0;
  var groupAlpha = (lit ? GROUP_ALPHA_DIM : GROUP_ALPHA) * zoomFade;
  if (!focusTheme) {
    /* Сначала глубины всех разделов — доля считается от РАЗМАХА этого
       кадра, а не от абсолютного pz: облако то ближе, то дальше, и
       постоянный порог гасил бы то все надписи разом, то ни одной. */
    var anchors = [], zMin = 1e9, zMax = -1e9;
    for (i = 0; i < groups.length; i++) {
      var a0 = groupAnchor(groups[i], { });
      anchors.push(a0);
      if (a0.pz < 0) continue;
      if (a0.pz < zMin) zMin = a0.pz;
      if (a0.pz > zMax) zMax = a0.pz;
    }
    var span = zMax - zMin;
    for (i = 0; i < groups.length; i++) {
      var g = groups[i];
      var a = anchors[i];
      if (a.pz < 0) continue;
      /* 1 у самого ближнего скопления, 0 у самого дальнего. */
      var front = span > 1 ? (zMax - a.pz) / span : 1;
      if (front < GROUP_DEPTH_DROP) continue;      /* ушло за спину */
      var depth = GROUP_DEPTH_FLOOR + (1 - GROUP_DEPTH_FLOOR) * front;
      want.push({ key: 'g:' + g.k, kind: 'group', text: g.l.toUpperCase(),
                  lines: null, node: null, ax: a.px, ay: a.py,
                  talpha: groupAlpha * depth, prio: 9 - front, stick: false,
                  px: GROUP_PX, weight: 600, spacing: GROUP_SPACING,
                  maxAway: 1e9, plate: false,
                  guard: groupGuard(g, a.cx, a.cy) });
    }
  }

  /* Узлы: под курсором, выбранные, найденные поиском. */
  var nodeWant = {};
  function askNode(n, prio, stick) {
    if (!n || n.pz < 0) return;
    if (n.px < 0 || n.px > W || n.py < 0 || n.py > H) return;
    /* Теги темы в фокусе рисует раскладка по колонкам — не дублируем. */
    if (focusTheme && n.k === 'tag' && n.n === focusTheme.n) return;
    var was = nodeWant[n.id];
    if (was && was.prio <= prio) { if (stick) was.stick = true; return; }
    var isTheme = n.k === 'theme';
    var item = {
      key: n.id, kind: n.k,
      text: isTheme ? cutLabel(n.l, THEME_MAX_CHARS) : n.l,
      lines: isTheme ? null : wrapLabel(n.l, TAG_WRAP_CHARS, 2),
      node: n, ax: n.px, ay: n.py,
      talpha: 1, prio: prio, stick: !!stick,
      px: isTheme ? LABEL_THEME_PX : LABEL_TAG_PX, weight: 500, spacing: 0,
      maxAway: LABEL_MAX_AWAY, plate: true
    };
    if (was) { for (var f in item) was[f] = item[f]; }
    else { nodeWant[n.id] = item; want.push(item); }
  }

  /* Узел под курсором и его контекст: тег — вместе со своей темой.
     Прозрачность берётся у подсветки: подпись обязана таять вместе с ней,
     иначе имя висит над уже погасшим узлом. */
  if (active) {
    askNode(active, 0, true);
    if (active.k === 'tag') askNode(byId['t' + active.n], 1, true);
  }
  /* Идём по маршруту — подписан узел на ДАЛЬНЕМ конце: видно, куда придёшь.
     Ближний конец — это сам active, он подписан выше. */
  if (route) askNode(route.b, 0, true);
  /* Выбранное. */
  for (k in picked) {
    if (!picked[k]) continue;
    var pn = byId[k];
    askNode(pn, 2, true);
    if (pn && pn.k === 'tag') askNode(byId['t' + pn.n], 3, true);
  }
  /* Найденное поиском — с лимитом: сотня строк на экране это не помощь. */
  if (searchHits) {
    var shown = 0;
    for (i = order.length - 1; i >= 0 && shown < LABEL_BUDGET; i--) {
      var sn = order[i];
      if (!sn || !searchHits[sn.id] || sn.pz < 0) continue;
      askNode(sn, 4, false);
      shown++;
    }
  }

  /* Пояснение — только у перекрёстной связи: у дороги тема→тег пояснять
     нечего, там связь и так очевидна из имён. */
  if (route && route.why) {
    want.push({ key: 'e:' + route.key, kind: 'edge', text: route.why,
                lines: null, node: null,
                ax: (route.a.px + route.b.px) / 2,
                ay: (route.a.py + route.b.py) / 2,
                talpha: EDGE_LABEL_ALPHA, prio: 0, stick: true,
                px: EDGE_LABEL_PX, weight: 500, spacing: 0,
                maxAway: 1e9, plate: true });
  }

  /* Наведение тает вместе с подсветкой; выбранное и найденное — нет. */
  if (hlAlpha < 1 && active) {
    for (i = 0; i < want.length; i++) {
      var wq = want[i];
      if (wq.kind === 'group') continue;
      if (wq.node && picked[wq.node.id]) continue;
      if (wq.talpha > hlAlpha) wq.talpha = hlAlpha;
    }
  }

  /* ── 2. Гашение на время движения ────────────────────────────────────
     Активное движение уводит прозрачность в ноль у всего, кроме того, что
     человек держит под курсором или выбрал: иначе невозможно рассмотреть
     то, что держишь. Порог выше скорости автовращения, поэтому тихое
     вращение подписи не гасит — они просто едут за узлами. */
  if (!labelsCalm) {
    for (i = 0; i < want.length; i++) if (!want[i].stick) want[i].talpha = 0;
  }

  /* ── 3. Обновляем память подписей ────────────────────────────────────*/
  var sig = '';
  for (i = 0; i < want.length; i++) {
    var it = want[i];
    if (it.talpha >= LB_MIN_ALPHA) sig += it.key + '|';
  }
  var composed = (sig !== labelSig);
  labelSig = sig;

  /* Раскладка запускается, когда сцена спокойна и с прошлой прошло не
     меньше LAYOUT_MS, либо когда изменился сам состав подписей. Во время
     движения раскладка НЕ считается: подписи едут за якорями с прежним
     смещением — от этого и уходит дрожание. */
  var relayout = composed || (labelsCalm && now - labelLayoutAt >= LAYOUT_MS);

  var live = [];
  for (i = 0; i < want.length; i++) {
    var w0 = want[i];
    L = labelOf(w0.key, w0.kind, w0.text);
    L.ax = w0.ax; L.ay = w0.ay;
    L.talpha = w0.talpha;
    L.prio = w0.prio;
    L.lines = w0.lines || [w0.text];
    L.pxSize = w0.px; L.weight = w0.weight; L.spacing = w0.spacing;
    L.plate = w0.plate; L.node = w0.node; L.maxAway = w0.maxAway;
    L.guard = w0.guard || null;
    /* Размеры меряются в текущем шрифте — они нужны и раскладке, и
       отрисовке, и проверке на пересечение. */
    setLabelFont(L.pxSize, L.weight, L.spacing);
    var wMax = 0;
    for (k = 0; k < L.lines.length; k++) {
      wMax = Math.max(wMax, ctx.measureText(L.lines[k]).width);
    }
    L.w = wMax;
    L.h = L.lines.length * LINE_H;
    live.push(L);
  }
  /* Подпись, которой в этом кадре не попросили, гаснет — плавно. */
  for (k in LB) if (LB[k].talpha !== 0 && live.indexOf(LB[k]) < 0) LB[k].talpha = 0;

  /* ── 4. Раскладка ────────────────────────────────────────────────────*/
  lastThemeMissing = 0;
  lastThemeMissingNames = [];
  lastThemeAway = 0;

  if (relayout) {
    labelLayoutAt = now;
    /* Порядок важности: связь и то, что под курсором, — раньше фона. */
    live.sort(function (p, q) { return p.prio - q.prio; });
    for (i = 0; i < live.length; i++) {
      L = live[i];
      if (L.talpha < LB_MIN_ALPHA) continue;
      var y0 = L.node ? L.ay - nodeRadius(L.node) - 11 - (L.h - LINE_H) / 2 : L.ay;
      var spot = findSpot(L.ax, y0, L.w, L.h, L.node, L.maxAway, placed, L.guard);
      if (!spot) {
        L.missed = true;
        lastThemeMissing++;
        lastThemeMissingNames.push(L.text);
        continue;
      }
      L.missed = false;
      L.tox = spot[0] - L.ax;
      L.toy = spot[1] - L.ay;
      L.placedAt = now;
      if (L.born) { L.ox = L.tox; L.oy = L.toy; L.born = false; }
      placed.push({ x: spot[0], y: spot[1], w: L.w, h: L.h, l: L.text });
    }
  }

  /* ── 5. Отрисовка ────────────────────────────────────────────────────
     Рисуем в (ax + ox, ay + oy) — там, куда подпись ДОЕХАЛА, а не там,
     куда раскладка положила её прямо сейчас. Фоновые подписи разделов
     идут первыми, под всем остальным. */
  var boxes = [];
  live.sort(function (p, q) { return q.prio - p.prio; });
  for (i = 0; i < live.length; i++) {
    L = live[i];
    if (L.alpha < LB_MIN_ALPHA || L.missed) continue;
    var lx = L.ax + L.ox, ly = L.ay + L.oy;

    /* Выноска: подпись, уступившая место соседке, могла отойти от узла —
       тонкая линия возвращает ей адрес. */
    if (L.node) {
      var away = labelGap(L.node, lx, ly, L.w, L.h);
      if (away > lastThemeAway) lastThemeAway = away;
      if (away > LABEL_LEADER_MIN) drawLeader(L.node, lx, ly, L.w, L.alpha);
    }

    setLabelFont(L.pxSize, L.weight, L.spacing);
    var isRegion = L.kind === 'group';
    drawLabelLines(L.lines, lx, ly, 'center', L.alpha,
                   isRegion ? PAL.regionCss : PAL.textCss,
                   L.pxSize, L.weight, L.spacing, L.plate,
                   isRegion ? GROUP_HALO : 0);
    boxes.push({ x: lx, y: ly, w: L.w, h: L.h, l: L.text, kind: L.kind });
  }
  ctx.letterSpacing = '0px';

  /* ── 6. Фокус-режим: у темы под курсором подписаны ВСЕ теги ──────────
     Единственное место, где текста на экране много, и там он оправдан:
     человек сам раскрыл тему и смотрит её состав. */
  lastQuietCount = 0;
  if (focusTheme && focusTheme.pz > 0) {
    var items = layoutFocusLabels(focusTheme);
    for (i = 0; i < items.length; i++) {
      var it2 = items[i];
      var t = it2.node;
      ctx.strokeStyle = PAL.accentShades[shadeIndex(0.55)];
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(t.px + (it2.side < 0 ? -1 : 1) * (nodeRadius(t) + 2), t.py);
      ctx.lineTo(it2.x - it2.side * 10, it2.y);
      ctx.stroke();
      ctx.lineWidth = 1;
      var box = drawLabelLines(it2.lines, it2.x, it2.y,
                               it2.side < 0 ? 'right' : 'left',
                               1, PAL.textCss, LABEL_TAG_PX, 500, 0, true);
      boxes.push({ x: box.left + box.w / 2, y: it2.y, w: box.w, h: box.h,
                   l: t.l, kind: 'tag' });
    }
  }

  lastThemeBoxes = boxes;
  lastThemeFrom = 0;
}

/* Выноска от узла к ближнему краю плашки: линия не должна заходить под
   текст, иначе она перечёркивает буквы. */
function drawLeader(node, lx, ly, w, alpha) {
  var tx = lx + (node.px > lx ? w / 2 + 4 : -(w / 2 + 4));
  if (Math.abs(node.px - lx) < w / 2) tx = node.px;
  var ty = ly + (ly > node.py ? -10 : 10);
  var rr = nodeRadius(node) + 2;
  var ang = Math.atan2(ty - node.py, tx - node.px);
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = PAL.borderShades[shadeIndex(0.45)];
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  ctx.moveTo(node.px + Math.cos(ang) * rr, node.py + Math.sin(ang) * rr);
  ctx.lineTo(tx, ty);
  ctx.stroke();
  ctx.lineWidth = 1;
  ctx.globalAlpha = 1;
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

/* ── Липкость подсветки ──────────────────────────────────────────────
   ⚠️ БЕЗ НЕЁ «ИДТИ ПО ЛИНИИ» НЕВОЗМОЖНО. Пунктир тонкий, рука дрожит, и
   курсор соскальзывает с него на пиксель по десять раз на пути. Мгновенное
   гашение читалось бы как мигание, а вести мышью вдоль связи было бы
   нельзя вовсе.

   Потеряли цель — держим подсветку ещё STICKY_MS без единого изменения,
   потом гасим за HL_FADE_MS. Нашли НОВУЮ цель за это время — переключаемся
   немедленно; нашли ТУ ЖЕ — просто сбрасываем таймер, и никакого мигания. */
var STICKY_MS = 280;
var HL_FADE_MS = 200;
var stickyUntil = 0;         /* до какого времени держим без изменений  */
var hlAlpha = 0;             /* сила подсветки: 1 — полная, 0 — нет     */
var hlTarget = 0;
var lastFrameAt = 0;

function hasPicked() {
  for (var k in picked) if (picked[k]) return true;
  return false;
}

/* Курсор нашёл цель — подсветка включается сразу, без плавности:
   ожидание при наведении читается как задержка отклика. */
function holdHighlight() {
  stickyUntil = 0;
  hlTarget = 1;
  hlAlpha = 1;
}

/* Курсор цель потерял. Ничего не меняем — только заводим часы. */
function releaseHighlight(now) {
  if (!active) return;
  if (!stickyUntil) stickyUntil = now + STICKY_MS;
}

function highlightTick(now) {
  var dt = lastFrameAt ? Math.min(64, now - lastFrameAt) : 16;
  lastFrameAt = now;

  /* Выбранное и найденное держат подсветку сами: гаснет только наведение. */
  if (hasPicked() || searchHits) { hlTarget = 1; if (hlAlpha < 1) hlAlpha = 1; }

  if (stickyUntil && now >= stickyUntil) {
    stickyUntil = 0;
    active = null; route = null; focusTheme = null;
    /* Выбранное и найденное держат подсветку сами — гасить нечего. */
    if (hasPicked() || searchHits) { rebuildHighlight(); }
    else { hlTarget = 0; }
    renderHover(null);
    canvas.classList.remove('is-hit');
    wake();
  }

  if (hlAlpha !== hlTarget) {
    var step = dt / HL_FADE_MS;
    if (hlAlpha < hlTarget) hlAlpha = Math.min(hlTarget, hlAlpha + step);
    else hlAlpha = Math.max(hlTarget, hlAlpha - step);
    /* Догорело — только теперь снимаем подсветку по-настоящему. */
    if (hlAlpha === 0) rebuildHighlight();
    wake();
    return true;
  }
  return false;
}

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

  /* Скорость сцены и шаг анимации подписей — до отрисовки: кадр рисует
     то, куда подписи доехали к этому моменту. */
  frameNow = now;
  if (highlightTick(now)) moved = true;
  sceneTick(now);
  labelTick();

  /* Подписи едут или проявляются — значит кадру есть что показать, даже
     если камера стоит. И раз в LAYOUT_MS в покое кадр нужен, чтобы
     раскладка пересчиталась и подписи вернулись после движения. */
  if (labelsBusy()) moved = true;
  else if (labelsCalm && now - labelLayoutAt > LAYOUT_MS) moved = true;
  if (pulse) moved = true;

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
    tourNotice('drag', dragMoved);
    touchActivity(); wake();
    return;
  }
  var got = pick(p[0], p[1]);
  var hit = got.node || null, r = got.route || null;
  canvas.classList.toggle('is-hit', !!(hit || r));

  if (hit) {
    /* Встали на узел. Маршрут при этом сбрасывается: путь кончился. */
    holdHighlight();
    if (hit !== active) {
      setActive(hit);
    } else if (route) {
      route = null; wake();
    }
  } else if (r) {
    /* Идём по ребру active. Сам active НЕ меняется — пока не дойдём. */
    holdHighlight();
    /* ⚠️ ПЕРЕХОД ТОЛЬКО ВПЕРЁД. Прошли больше ROUTE_ARRIVE_T пути либо
       подошли к дальнему узлу ближе ROUTE_ARRIVE_PX — оказались в нём.
       Движение НАЗАД по той же линии не переключает ничего: доля пути
       уменьшается, ни одно из двух условий не выполняется. */
    var toFar = Math.hypot(p[0] - r.b.px, p[1] - r.b.py);
    if (r.t > ROUTE_ARRIVE_T || toFar < ROUTE_ARRIVE_PX) {
      setActive(r.b, true);
    } else if (!route || route.key !== r.key) {
      route = r;
      renderRoute(r);
      wake();
    } else {
      /* Та же линия — обновляем только положение каретки. */
      route = r;
      wake();
    }
  } else {
    /* Соскользнули — подсветка держится, часы пошли. */
    releaseHighlight(performance.now());
  }
  touchActivity();
});

/* Встать на узел: одна точка входа в режим хождения.
   `viaRoute` — пришли ли сюда, пройдя линию до конца: тур различает
   «навёл курсор» и «дошёл по дороге», это разные умения. */
function setActive(n, viaRoute) {
  active = n;
  route = null;
  focusTheme = (n && n.k === 'theme') ? n : null;
  rebuildHighlight();
  renderHover(n);
  if (n) tourNotice(viaRoute ? 'walk' : 'node', n);
  wake();
}

canvas.addEventListener('pointerup', function (e) {
  dragging = false;
  canvas.classList.remove('is-drag');
  if (dragMoved < 5) {
    var p = localPoint(e);
    /* ⚠️ КЛИК ЦЕЛИТСЯ В УЗЕЛ, А НЕ В ЛИНИЮ, И ЭТО ОТДЕЛЬНОЕ ПРАВИЛО ОТ
       НАВЕДЕНИЯ. У pick() старшинство настроено под ХОЖДЕНИЕ: стоишь на
       узле — коридор его линии сильнее соседнего кружка (ADR 0047). Для
       наведения это верно, для клика — нет: попасть в тег требовалось
       пиксель в пиксель (кружок тега 3–5 px), промах на шесть пикселей
       отдавал клик линии, а клик по линии брал ОБА её конца — то есть тег
       вместе с его темой. Человек видел «кликнул по тегу, выбралась вся
       тема», и это был не каприз выделения, а промах прицела.
       Поэтому у клика свой прицел: hitTest с допуском 10 px. */
    var hit = hitTest(p[0], p[1]);
    if (hit) {
      selectNode(hit);
    } else {
      /* Не попали ни в один узел — значит, клик пришёлся на линию.
         ⚠️ БЕРЁМ ТОЛЬКО ДАЛЬНИЙ КОНЕЦ, А НЕ ОБА. Панель в этот момент
         крупно показывает именно его («идём к …»), и выбраться должно то,
         что человек читает. Прежний захват пары молча добавлял второй
         узел, которого на экране никто не обещал. */
      var r2 = pick(p[0], p[1]).route;
      if (r2) selectNode(r2.b);
    }
  }
  touchActivity(); wake();
});

canvas.addEventListener('pointerleave', function () {
  /* Курсор ушёл с холста — гасим по тем же часам, что и соскальзывание с
     линии: отдельный мгновенный путь давал бы рывок там, где везде плавно. */
  releaseHighlight(performance.now());
  wake();
});

canvas.addEventListener('dblclick', function (e) {
  var p = localPoint(e);
  var hit = hitTest(p[0], p[1]);
  /* По узлу — подлёт к нему; по пустому месту — возврат к исходному виду.
     Двойной клик по пустоте это привычный жест «покажи всё целиком», и
     доходить до кнопки ⟲ в углу ради него не нужно. */
  if (hit) flyTo(hit, 2.1);
  else resetView();
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
  var was = cam.zoomTarget;
  zoomAt(p[0], p[1], e.deltaY < 0 ? 1.12 : 0.893);
  /* Сообщаем туру только о зуме, который ЧТО-ТО изменил: на упоре шкалы
     колесо крутится, а масштаб стоит, и шаг засчитывать не за что. */
  if (cam.zoomTarget !== was) tourNotice('zoom', cam.zoomTarget);
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

/* Возврат к тому виду, с которого карта открылась.
   ⚠️ ПОВОРОТ ВОЗВРАЩАЕТСЯ ТОЖЕ. Раньше здесь сбрасывались смещение,
   масштаб и наклон, а yaw оставался где был — и «вернуть обзор» возвращало
   не тот вид, с которого человек начал: карта успевает уехать сама, она
   тихо вращается. Обзор — это ВЕСЬ ракурс целиком, иначе кнопка не
   отвечает на вопрос «как было в начале». */
function resetView() {
  cam.goalX = cam.goalY = cam.goalZ = null;
  cam.tx = cam.ty = cam.tz = 0;
  cam.zoomTarget = 1;
  cam.yaw = START_YAW;
  cam.pitch = START_PITCH;
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
/* Последний выбранный узел: его показывает панель, когда курсор ни на
   чём. Хранится отдельно от `picked`, потому что порядок ключей объекта
   для этого — не источник правды. */
var lastPickedId = null;

/* ⚠️ ЕДИНСТВЕННАЯ ТОЧКА ВЫБОРА НА ВСЮ КАРТУ. Через неё идут и клик по
   холсту, и строки правой панели, и обучение. Правило у неё одно и
   короткое: ВЫБИРАЕТСЯ РОВНО ТОТ УЗЕЛ, КОТОРЫЙ ПЕРЕДАЛИ, — ни его тема,
   ни его теги, ни второй конец линии. Всё остальное (подсветка соседей,
   подсчёт задач) считается уже ОТ выбранного, а не подмешивается в него.

   Заводить второй путь выбора мимо этой функции нельзя: каждый такой путь
   заново решает, что значит «выбрать тег», и решает по-своему. */
function selectNode(n) {
  if (!n) return false;
  if (picked[n.id]) {
    delete picked[n.id];
    if (lastPickedId === n.id) lastPickedId = null;
  } else {
    picked[n.id] = true;
    lastPickedId = n.id;
  }
  rebuildHighlight();
  renderPicked();
  if (!active) refreshHoverPanel();
  if (picked[n.id]) tourNotice('pick', n);
  wake();
  return !!picked[n.id];
}

function clearPick() {
  picked = {};
  lastPickedId = null;
  var q = document.getElementById('tmap-q');
  if (q) q.value = '';
  applySearch('');
  rebuildHighlight();
  renderPicked();
  refreshHoverPanel();
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

/* ⚠️ ЭТО ЛЕГЕНДА, А НЕ «ПОД КУРСОРОМ», И ЗАГОЛОВОК БЛОКА МЕНЯЕТСЯ ВМЕСТЕ С
   СОДЕРЖИМЫМ. Блок один, состояний два: пока ничего не наведено и не
   выбрано, в нём объяснение знаков, и над ним обязано стоять «Как
   пользоваться». Заголовок «Под курсором» над легендой сообщал неправду —
   под курсором в этот момент ровно ничего.

   Текст переписан короче и без длинных тире: пять строк, каждая про один
   знак, глагол в начале там, где от человека ждут действия. */
var HOWTO = '<ul class="tmap-howto">' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5.5" fill="currentColor" opacity=".7"/></svg>' +
  '<span>Крупный узел это <b>тема</b>. Их 29.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="2.6" fill="currentColor" opacity=".7"/></svg>' +
  '<span>Мелкий узел это <b>тег</b>. Их 343.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5.5" fill="currentColor" opacity=".28"/><circle cx="7" cy="7" r="2.6" fill="currentColor"/></svg>' +
  '<span>Цвет узла это его <b>раздел</b>, они перечислены ниже.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" stroke-width="1.5" opacity=".7"/></svg>' +
  '<span>Сплошная линия ведёт от темы к её тегу.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 3" opacity=".7"/></svg>' +
  '<span>Пунктир связывает близкие теги разных тем. Таких пар 82.</span></li>' +
  '<li><svg width="14" height="14" viewBox="0 0 14 14"><circle cx="2.5" cy="11" r="2" fill="currentColor" opacity=".7"/><path d="M4 10 L12 3.5" stroke="currentColor" stroke-width="1.5" opacity=".7"/><circle cx="8" cy="6.5" r="2" fill="currentColor" opacity=".45"/></svg>' +
  '<span><b>Встаньте на тег</b> и уходите по линиям к его теме и ' +
  'соседям.</span></li></ul>';

/* Заголовок блока живёт вместе с его содержимым. */
var hoverHead = document.getElementById('tmap-hover-head');

function setHoverHead(text) {
  if (hoverHead) hoverHead.textContent = text;
}

function renderHover(n) {
  if (!hoverBox) return;
  if (!n) {
    /* ⚠️ КУРСОР УШЁЛ — ПАНЕЛЬ НЕ ПУСТЕЕТ. Раньше здесь стояло «Наведите на
       узел, чтобы увидеть подробности», и человек, выбравший тег и
       отведший мышь, видел вместо своего тега приглашение навести: выбор
       на экране будто пропадал. Теперь панель показывает ПОСЛЕДНИЙ
       выбранный тег, и только когда выбора нет вовсе — «Как читать
       карту». */
    var last = (lastPickedId && picked[lastPickedId]) ? byId[lastPickedId] : null;
    if (!last) {
      for (var k in picked) { if (picked[k]) { last = byId[k]; break; } }
    }
    if (last) { renderHover(last); return; }
    hoverBox.innerHTML = HOWTO;
    setHoverHead('Как пользоваться');
    return;
  }
  setHoverHead('Под курсором');
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

/* Панель «Под курсором» по текущему состоянию. ⚠️ ОДНА ТОЧКА НА ВСЕХ:
   пока сброс выбора звал renderHover(active) напрямую, он затирал
   карточку связи подсказкой «Как читать карту» — курсор всё ещё стоял на
   линии, а панель об этом уже не знала. */
function refreshHoverPanel() {
  if (route) renderRoute(route);
  else renderHover(active);
}

/* Панель, пока человек идёт по линии. Главный вопрос в этот момент —
   «куда я приду», поэтому дальний узел стоит первым и крупно. Пояснение
   показывается только у перекрёстной связи: у дороги тема→тег пояснять
   нечего. */
function renderRoute(r) {
  if (!hoverBox) return;
  setHoverHead('Под курсором');
  var far = r.b;
  var isCross = r.link.k === 'cross';
  var html = '<span class="tmap-kind">' +
             (isCross ? 'идём к смежному тегу' : 'идём по дороге') + '</span>';
  html += '<div class="tmap-name">' + esc(far.l) + '</div>';

  if (far.k === 'theme') {
    html += '<div class="tmap-parent"><span>тема ' + far.n + ' · ' +
            (tagsOfTheme[far.n] || []).length + ' тегов</span></div>';
  } else {
    var th = byId['t' + far.n];
    if (th) html += '<div class="tmap-parent"><span>' + esc(th.l) + '</span></div>';
  }
  html += (far.c === null || far.c === undefined)
    ? '<div class="tmap-num tmap-num--none">— <span>счётчика нет</span></div>'
    : '<div class="tmap-num"><b>' + fmtNum(far.c) + '</b> задач</div>';

  if (isCross && r.why) {
    html += '<div class="tmap-why-link">Родство: <b>' + esc(r.why) + '</b></div>';
  }
  html += '<div class="tmap-from">от: ' + esc(r.a.l) + '</div>';
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
  /* ⚠️ СУММИРУЕМ ТОЛЬКО ТЕ ТЕГИ, У КОТОРЫХ СЧЁТЧИК ЗАДАН. Счётчик известен
     не у всех: часть тегов размечается вручную и числа ещё не имеет.
     Пока отсутствие числа считалось нулём, выбор из одних таких тегов давал
     «примерно 0 задач» — а это читается как «ничего не нашлось», то есть
     ровно противоположное правде («неизвестно»). */
  var counted = keys.filter(function (id) {
    var n = byId[id];
    return n && n.c !== null && n.c !== undefined;
  });
  var sum = 0;
  counted.forEach(function (id) { sum += byId[id].c; });

  var cEl = document.getElementById('tmap-count');
  if (cEl) {
    var head = 'Выбрано: ' + keys.length + ' ' +
               plural(keys.length, 'тег', 'тега', 'тегов');
    cEl.textContent = !keys.length
      ? 'Выбрано: 0 тегов'
      : head + ' · ' + (counted.length
          ? 'примерно ' + fmtNum(sum) + ' ' +
            plural(sum, 'задача', 'задачи', 'задач')
          : 'число задач пока неизвестно');
  }
  var apply = document.getElementById('tmap-apply');
  var why = document.getElementById('tmap-why');
  if (apply) apply.disabled = keys.length === 0;
  /* Канон 2.7: причина выключенной кнопки стоит РЯДОМ, а не в подсказке. */
  if (why) why.hidden = keys.length > 0;

  /* Отметка выбранного в дереве: и темы, и теги. Дерево — второй экран
     того же состояния, и оно обязано показывать выбор так же, как чипы. */
  Array.prototype.forEach.call(document.querySelectorAll('.tmap-theme-row'), function (row) {
    row.classList.toggle('is-on', !!picked['t' + row.dataset.theme]);
  });
  Array.prototype.forEach.call(document.querySelectorAll('.tmap-tag-row'), function (row) {
    row.classList.toggle('is-on', !!picked[row.dataset.goTag]);
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

/* ⚠️ ТУР НЕ РАССКАЗЫВАЕТ, А ЗАСТАВЛЯЕТ ПОПРОБОВАТЬ. Прежняя версия
   показывала пять карточек и сама двигала камеру: человек досматривал её
   как ролик и закрывал, ничего не научившись — руками он к карте так и не
   прикоснулся. Теперь каждый шаг ждёт НАСТОЯЩЕГО действия и засчитывается
   слушателем этого действия, а не кнопкой «дальше» и не таймером.

   Пять шагов — пять разных механик: повернуть, приблизить, встать на узел,
   уйти по линии, выбрать тег. Кнопки «дальше» у шага нет вовсе; есть
   «пропустить шаг» — на случай мыши без колеса или сенсорного экрана — и
   «пропустить» на весь тур.

   Версия в ключе поднята до v2: логика шагов изменилась целиком, и те, кто
   видел рассказ, должны один раз увидеть и практику. */
var TOUR_KEY = 'weconomics.map.tour.v2';

var tourBox = document.getElementById('tmap-tour');
var tourHole = document.getElementById('tmap-tour-hole');
var tourCard = document.getElementById('tmap-tour-card');
var tourStep = 0, tourOn = false, tourDone = false;

/* ⚠️ ШАГ ЗАСЧИТЫВАЕТСЯ СОБЫТИЕМ, А НЕ СОСТОЯНИЕМ. Проверять «стоит ли
   курсор на теге» опросом нельзя: человек мог оказаться там случайно ещё
   до того, как прочёл задание, и шаг засчитался бы сам. Поэтому места
   взаимодействия сообщают туру, ЧТО ИМЕННО СЕЙЧАС ПРОИЗОШЛО, а шаг решает,
   его ли это событие. */
var TOUR = [
  {
    t: 'Поверните корпус',
    p: 'Возьмите карту мышью и потяните в сторону. Она объёмная: то, что ' +
       'сейчас далеко, повернётся к вам.',
    hint: 'Тяните мышью по холсту',
    at: function () { return wrap; },
    want: function (kind, value) { return kind === 'drag' && value >= 60; }
  },
  {
    t: 'Приблизьте',
    p: 'Покрутите колесо. Масштаб идёт к точке под курсором, поэтому целиться ' +
       'можно прямо в скопление, которое хочется рассмотреть.',
    hint: 'Колесо мыши над холстом',
    at: function () { return wrap; },
    want: function (kind) { return kind === 'zoom'; }
  },
  {
    t: 'Встаньте на тег',
    p: 'Наведите курсор на любой мелкий узел. Справа появится его тема, число ' +
       'задач и смежные теги из других тем.',
    hint: 'Мелкий узел — это тег',
    at: function () { return wrap; },
    want: function (kind, node) { return kind === 'node' && node.k === 'tag'; }
  },
  {
    t: 'Уйдите по линии',
    p: 'Не спеша ведите курсор от тега вдоль линии до её дальнего конца. Так по ' +
       'карте и ходят: встают на узел и уходят по его дорогам.',
    hint: 'Ведите курсор вдоль линии до конца',
    at: function () { return wrap; },
    want: function (kind) { return kind === 'walk'; }
  },
  {
    t: 'Выберите тег',
    p: 'Кликните по тегу. Он попадёт в список справа, а внизу посчитается, ' +
       'сколько задач он примерно даёт. Тегов можно набрать сколько угодно.',
    hint: 'Клик по мелкому узлу',
    at: function () { return root; },
    want: function (kind, node) { return kind === 'pick' && node.k === 'tag'; }
  }
];

/* Единственный вход для всех сообщений о действиях человека.
   ⚠️ Зовётся ИЗ мест взаимодействия, а не наоборот: тур не вешает своих
   слушателей на холст и не может перехватить или сломать обычную работу
   карты. Выключен тур — вызов стоит ровно ничего. */
function tourNotice(kind, value) {
  if (!tourOn || tourDone) return;
  var step = TOUR[tourStep];
  if (!step.want(kind, value)) return;
  tourPass();
}

/* Шаг взят. Показываем это отдельным состоянием и только потом идём
   дальше: мгновенный перескок читается как сбой, а не как «получилось». */
function tourPass() {
  tourDone = true;
  tourCard.classList.add('is-done');
  var next = document.getElementById('tmap-tour-hint');
  if (next) next.textContent = 'Получилось';
  setTimeout(function () {
    if (!tourOn) return;
    if (tourStep === TOUR.length - 1) tourEnd();
    else tourShow(tourStep + 1);
  }, reduceMotion ? 200 : 620);
}

function tourShow(i) {
  tourStep = Math.max(0, Math.min(TOUR.length - 1, i));
  tourDone = false;
  tourCard.classList.remove('is-done');
  var s = TOUR[tourStep];
  document.getElementById('tmap-tour-step').textContent =
    'Шаг ' + (tourStep + 1) + ' из ' + TOUR.length;
  document.getElementById('tmap-tour-title').textContent = s.t;
  document.getElementById('tmap-tour-text').textContent = s.p;
  var hint = document.getElementById('tmap-tour-hint');
  if (hint) hint.textContent = s.hint;
  document.getElementById('tmap-tour-prev').disabled = tourStep === 0;

  var dots = document.getElementById('tmap-tour-dots');
  dots.innerHTML = TOUR.map(function (_, j) {
    return '<i class="' + (j === tourStep ? 'is-on' : (j < tourStep ? 'is-past' : '')) + '"></i>';
  }).join('');

  var el = s.at && s.at();
  if (el) {
    var r = el.getBoundingClientRect();
    tourHole.style.left = (r.left - 6) + 'px';
    tourHole.style.top = (r.top - 6) + 'px';
    tourHole.style.width = (r.width + 12) + 'px';
    tourHole.style.height = (r.height + 12) + 'px';
  }
  placeTourCard();
  wake();
}

/* ⚠️ КАРТОЧКА СТОИТ В ПРАВОМ НИЖНЕМ УГЛУ ХОЛСТА, И ЭТО ЕДИНСТВЕННОЕ МЕСТО,
   КОТОРОЕ НИЧЕМУ НЕ МЕШАЕТ. Прежде она вставала слева внизу и закрывала
   угол графа — а теперь работать руками надо именно по графу. Слева внизу
   кнопки масштаба (о них второй шаг), сверху шапка с поиском, справа за
   краем холста панель, где показывается результат третьего и пятого шага.
   Остаётся правый нижний угол САМОГО ХОЛСТА: панель он не закрывает,
   потому что лежит левее её кромки. */
function placeTourCard() {
  var cw = tourCard.offsetWidth || 340, ch = tourCard.offsetHeight || 190;
  var box = wrap.getBoundingClientRect();
  var left = box.right - cw - 16;
  var top = box.bottom - ch - 16;
  left = Math.max(8, Math.min(window.innerWidth - cw - 8, left));
  top = Math.max(root.getBoundingClientRect().top + 8,
                 Math.min(window.innerHeight - ch - 8, top));
  tourCard.style.left = left + 'px';
  tourCard.style.top = top + 'px';
}

function tourStart() {
  tourOn = true;
  tourBox.hidden = false;
  tourShow(0);
  document.addEventListener('keydown', tourKeys);
  window.addEventListener('resize', placeTourCard);
}

function tourEnd() {
  tourOn = false;
  tourDone = false;
  tourBox.hidden = true;
  tourCard.classList.remove('is-done');
  document.removeEventListener('keydown', tourKeys);
  window.removeEventListener('resize', placeTourCard);
  /* ⚠️ ЗА СОБОЙ ТУР БОЛЬШЕ НЕ УБИРАЕТ, И ЭТО НАРОЧНО. Раньше он сам делал
     показательный выбор и сам его снимал. Теперь всё, что на карте, —
     сделано руками человека: снимать его выбор и уводить камеру значило бы
     стереть результат его же работы на глазах. */
  try { localStorage.setItem(TOUR_KEY, '1'); } catch (e) {}
  wake();
}

function tourKeys(e) {
  if (!tourOn) return;
  if (e.key === 'Escape') { tourEnd(); e.preventDefault(); }
  else if (e.key === 'ArrowRight') { tourSkipStep(); e.preventDefault(); }
  else if (e.key === 'ArrowLeft') { tourShow(tourStep - 1); e.preventDefault(); }
}

/* Пропуск ОДНОГО шага: у человека может не быть колеса мыши или он на
   сенсорном экране. Это выход из положения, а не обычный путь — потому и
   написано «пропустить шаг», а не «дальше». */
function tourSkipStep() {
  if (tourStep === TOUR.length - 1) tourEnd();
  else tourShow(tourStep + 1);
}

document.getElementById('tmap-tour-next').addEventListener('click', tourSkipStep);
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
  if (lastPickedId === b.dataset.drop) lastPickedId = null;
  rebuildHighlight(); renderPicked();
  if (!active) renderHover(null);
  wake();
  touchActivity();
});

/* Смежные теги в панели — клик наводит камеру. */
hoverBox.addEventListener('click', function (e) {
  var b = e.target.closest('[data-go]');
  if (!b) return;
  var n = byId[b.dataset.go];
  if (n) { flyTo(n, 2.1); touchActivity(); }
});

/* ── Дерево «Разделы → Темы → Теги» ───────────────────────────────────
   Второй, надёжный способ дойти до нужного места, когда на карте его не
   видно. Свёрнуто по умолчанию: семь строк вместо двадцати девяти.

   ⚠️ РАЗДЕЛЫ И ТЕМЫ РАСКРЫВАЮТСЯ, А НЕ ВЫБИРАЮТСЯ. Раньше клик по теме
   разом и наводил камеру, и добавлял тему в выбранное — одна кнопка делала
   два разных дела, и человек, открывавший список посмотреть состав, молча
   получал 16 тегов в подборке. Раскрытие и выбор разведены: клик по
   разделу и по теме раскрывает, выбор живёт на холсте, а клик по ТЕГУ
   ведёт к нему камеру.
   Наведение по-прежнему подсвечивает тему на карте: это подсказка, она
   ничего не меняет. */
var themesBox = document.getElementById('tmap-themes');

/* Показать тег на карте: камера к нему, подсветка на него, импульс по
   ребру к его теме. Тема при этом подсвечена мягче — см. rebuildHighlight. */
function revealTag(n) {
  if (!n) return;
  flyTo(n, 2.1);
  active = n;
  focusTheme = null;
  rebuildHighlight();
  renderHover(n);
  holdHighlight();
  var parent = byId['t' + n.n];
  pulse = parent ? { from: n, to: parent, t0: performance.now() } : null;
  /* ⚠️ КЛАСС ЗДЕСЬ ДРУГОЙ, НЕ `is-on`. `is-on` означает «выбрано» и его
     ставит renderPicked по `picked`; «камера стоит здесь» — другое
     состояние, и делить с ним один класс значит, что один из двух будет
     затирать другой при каждом обновлении. */
  Array.prototype.forEach.call(themesBox.querySelectorAll('.tmap-tag-row'),
    function (row) { row.classList.toggle('is-at', row.dataset.goTag === n.id); });
  wake();
}

if (themesBox) {
  themesBox.addEventListener('click', function (e) {
    var open = e.target.closest('[data-open]');
    if (open) {
      var body = open.nextElementSibling;
      var was = open.getAttribute('aria-expanded') === 'true';
      open.setAttribute('aria-expanded', was ? 'false' : 'true');
      if (body) body.hidden = was;
      showPanelFade();
      return;
    }
    var tagRow = e.target.closest('[data-go-tag]');
    if (tagRow) {
      revealTag(byId[tagRow.dataset.goTag]);
      touchActivity();
    }
  });

  /* Наведение на строку темы подсвечивает её на карте — но только если
     человек не держит что-то своё: перебивать выбранное подсказкой нельзя. */
  themesBox.addEventListener('mouseover', function (e) {
    var row = e.target.closest('.tmap-theme-row');
    if (!row) return;
    var n = byId['t' + row.dataset.theme];
    if (n && n !== active) {
      active = n; focusTheme = n;
      rebuildHighlight(); renderHover(n); wake();
    }
  });
  themesBox.addEventListener('mouseleave', function () {
    if (active && active.k === 'theme') {
      active = null; focusTheme = null;
      rebuildHighlight(); renderHover(null); wake();
    }
  });
}

/* Полоса затухания у нижней кромки панели гаснет, когда список
   докручен до конца или прокручивать нечего вовсе. */
/* ⚠️ Опрашиваем НЕ панель, а её прокручиваемую часть: панель стала
   неподвижной flex-колонкой и сама не прокручивается вовсе. */
var panelBox = document.getElementById('tmap-panel-scroll');
var panelFade = document.getElementById('tmap-panel-fade');

function showPanelFade() {
  if (!panelBox || !panelFade) return;
  var rest = panelBox.scrollHeight - panelBox.scrollTop - panelBox.clientHeight;
  panelFade.classList.toggle('is-off', rest <= 2);
}

if (panelBox) panelBox.addEventListener('scroll', showPanelFade, { passive: true });

/* ⚠️ СЛЕДИМ ЗА РАЗМЕРОМ САМОГО КОНТЕЙНЕРА, А НЕ ТОЛЬКО ОКНА.
   Холст меняет размер и без изменения окна: скрытая и снова показанная
   панель, схлопнутая правая колонка, а в будущем — открытие карты во
   всплывающем окне. На событии `resize` окна это не ловится вовсе, и
   карта остаётся посчитанной под прежний, иногда нулевой размер. */
function onBoxResize() {
  var r = wrap.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;   /* холст ещё не разложен */
  resize();
  /* Форма холста поменялась — значит, и растяжение облака под неё, и
     обзор. Растяжение всегда считается ОТ БАЗОВЫХ координат, поэтому
     повторный вызов не множится на прежний. */
  if (ready) { spreadCloud(); computeFit(); }
  showPanelFade();
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

/* ⚠️ ФИРМЕННЫЙ ШРИФТ ПРИЕЗЖАЕТ ПОЗЖЕ ПЕРВОГО КАДРА. Пока он грузится,
   measureText меряет запасным, и раскладка подписей считается по чужим
   ширинам. Дождавшись загрузки, пересчитываем: это один кадр, а не цикл. */
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(function () { labelSig = ''; wake(); });
}

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
    /* 300 итераций синхронно: карта открывается уже собранной. */
    settle(300);
    recentre();
    snapshotLayout();

    resize();
    spreadCloud();          /* облако под форму холста */
    computeFit();           /* и обзор по обеим осям сразу */
    ready = true;
    renderHover(null);
    renderPicked();
    showPanelFade();
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
  /* Рёбра с уже разрешёнными концами — для замеров попадания. */
  links: function () {
    return links.map(function (ln) {
      return { a: byId[ln.s], b: byId[ln.t], k: ln.k, w: ln.w || '' };
    });
  },
  search: function (q) { return applySearch(q); },
  draw: function () { draw(); },
  /* Прямоугольники подписей тем после раздвижки — чтобы проверить, что ни
     одна не потерялась и ни одна не наехала на соседнюю. */
  themeBoxes: function () { draw(); return lastThemeBoxes.slice(lastThemeFrom); },
  /* Все подписи кадра — и тегов, и тем: они делят холст, и проверять их
     на пересечение надо вместе, а не по слоям. */
  allBoxes: function () { draw(); return lastThemeBoxes.slice(); },
  /* Что кадр НЕ показал и как далеко увёл: приглушённые имена тем,
     ненарисованные имена тем и самое дальнее отстояние подписи от узла. */
  labelReport: function (settle) {
    /* Инварианты меряются В ПОКОЕ: если не досчитать анимацию, замер
       поймает подписи на полпути к своей прозрачности. */
    if (settle !== false) { draw(); labelSettle(); }
    draw();
    var by = { group: 0, theme: 0, tag: 0, edge: 0 };
    for (var i = 0; i < lastThemeBoxes.length; i++) {
      var kk = lastThemeBoxes[i].kind || 'tag';
      by[kk] = (by[kk] || 0) + 1;
    }
    return { drawn: lastThemeBoxes.length,
             groups: by.group, themes: by.theme, tags: by.tag, edges: by.edge,
             quiet: lastQuietCount,
             missing: lastThemeMissing,
             missingNames: lastThemeMissingNames.slice(),
             maxAway: +lastThemeAway.toFixed(1) };
  },
  /* Скорость сцены и спокойствие — для проверки гашения при движении. */
  motion: function () {
    return { speed: +sceneSpeed.toFixed(5), calm: labelsCalm,
             threshold: SPEED_QUIET, spinIdle: SPIN_IDLE };
  },
  /* Самый большой шаг смещения подписи за кадр — инвариант плавности. */
  jump: function (reset) { var v = +lbJumpMax.toFixed(3); if (reset) lbJumpMax = 0; return v; },
  settleLabels: labelSettle,
  /* Что сейчас под курсором — узел, связь или ничего; и жива ли липкость. */
  hoverState: function () {
    return { node: active ? active.id : null,
             edge: route ? route.key : null,
             why: route ? route.why : null,
             far: route ? route.b.id : null,
             t: route ? +route.t.toFixed(3) : null,
             hl: +hlAlpha.toFixed(3),
             sticky: stickyUntil ? +(stickyUntil - performance.now()).toFixed(0) : 0 };
  },
  /* Прямой хит-тест по экранной точке — без событий мыши. */
  probe: function (x, y) {
    var g = pick(x, y);
    if (g.node) return { kind: 'node', id: g.node.id, label: g.node.l };
    if (g.route) return { kind: 'route', id: g.route.key, far: g.route.b.id,
                          why: g.route.why, t: +g.route.t.toFixed(3),
                          d: +g.route.d.toFixed(2) };
    return { kind: 'none' };
  },
  /* Встать на узел без событий мыши — для замеров хождения. */
  setActive: function (id) { var n = byId[id]; if (n) setActive(n); return !!n; },
  /* Прогнать курсор через обработчик: тот же путь, что у живой мыши. */
  move: function (x, y) {
    var cr = canvas.getBoundingClientRect();
    canvas.dispatchEvent(new PointerEvent('pointermove',
      { bubbles: true, clientX: cr.left + x, clientY: cr.top + y }));
    return { active: active ? active.id : null,
             route: route ? route.key : null,
             far: route ? route.b.id : null,
             t: route ? +route.t.toFixed(3) : null,
             litOn: !!litSet };
  },
  region: function () {
    var L = LB['g:' + groups[0].k];
    return { css: PAL.regionCss, alpha: L ? +L.alpha.toFixed(3) : 0,
             px: GROUP_PX, halo: GROUP_HALO };
  },
  /* Поставить масштаб мгновенно — для проверки затухания ориентиров. */
  zoomTo: function (z) {
    cam.zoom = cam.zoomTarget = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
    lastZoom = cam.zoom; showZoom(); draw(); labelSettle(); draw();
    var a = LB['g:' + groups[0].k];
    return { zoom: +cam.zoom.toFixed(2), groupAlpha: a ? +a.alpha.toFixed(3) : 0 };
  },
  /* Прогон N кадров тихого автовращения БЕЗ requestAnimationFrame: в
     скрытой вкладке браузер кадры не гоняет вовсе, и замер плавности там
     не снять. Здесь кадр воспроизводится вручную — поворот, скорость,
     шаг подписей, отрисовка, — ровно в том же порядке, что в frame(). */
  spinFrames: function (n, speed) {
    n = n || 120;
    var step = speed === undefined ? SPIN_IDLE : speed;
    var t = Math.max(frameNow, performance.now());
    lbJumpMax = 0;
    var minVisible = 1e9, maxVisible = 0;
    for (var i = 0; i < n; i++) {
      cam.yaw += step;
      t += 16.7;
      frameNow = t;
      highlightTick(t);
      sceneTick(t);
      labelTick();
      draw();
      var vis = 0;
      for (var k in LB) if (LB[k].alpha >= LB_MIN_ALPHA) vis++;
      if (vis < minVisible) minVisible = vis;
      if (vis > maxVisible) maxVisible = vis;
    }
    var layouts = 0;
    return { frames: n, jumpMax: +lbJumpMax.toFixed(3),
             speed: +sceneSpeed.toFixed(5), calm: labelsCalm,
             visibleMin: minVisible, visibleMax: maxVisible,
             visibleEnd: (function () { var c = 0; for (var q in LB) if (LB[q].alpha >= LB_MIN_ALPHA) c++; return c; })() };
  },
  /* Якоря разделов: центр масс своих тем и куда встала надпись. */
  groupAnchors: function () {
    draw();
    var out = [];
    for (var i = 0; i < groups.length; i++) {
      var a = groupAnchor(groups[i], { });
      var L = LB['g:' + groups[i].k];
      out.push({ key: groups[i].k, label: groups[i].l,
                 cx: a.cx, cy: a.cy, r: +(a.r || 0).toFixed(1),
                 pz: +(a.pz || 0).toFixed(1),
                 anchorY: a.py,
                 x: L ? L.ax + L.ox : null, y: L ? L.ay + L.oy : null,
                 alpha: L ? +L.alpha.toFixed(3) : 0 });
    }
    return out;
  },
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
      active = themeList[i]; focusTheme = themeList[i];
      rebuildHighlight();
      draw();                                /* проекция должна быть свежей */
      wake();
      var items = layoutFocusLabels(themeList[i]);
      return items.map(function (it) {
        var w = it.w;
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
