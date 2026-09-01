/* Предпросмотр карты тем — встраиваемый режим движка карты.
 *
 * Это ВТОРОЙ режим карты, а не вторая карта. Полная карта живёт на
 * /catalog/map/ (topic_map.js); здесь — маленькое окно, которое ставится в
 * чужой экран (блок «Умного каталога») и работает по другим правилам:
 *
 *   • подписей нет вовсе — только узлы и связи;
 *   • медленное автовращение, курсор на карту не влияет НИКАК;
 *   • клик в любом месте блока ведёт на полную карту;
 *   • данные и раскладка считаются ПОСЛЕ отрисовки экрана-хозяина;
 *   • вне экрана и при prefers-reduced-motion цикл кадров останавливается
 *     совсем — не «рисуем то же самое», а не рисуем вообще.
 *
 * Требования — решение владельца от 01.09.2026 «Предпросмотр карты тем:
 * сейчас готовим только место и архитектуру»:
 * https://app.notion.com/p/3ceb11c92bc18146a098f0e93526c347
 *
 * ⚠️ ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ ФАЙЛ, А НЕ ФЛАГ ВНУТРИ topic_map.js.
 * Полный движок весит около 150 КБ и на три четверти состоит из того, чего
 * у предпросмотра нет вовсе: подписи и их память, поиск, панель, хождение
 * по линиям, обучение. Тянуть его на КАЖДОЕ открытие каталога — платить
 * за то, что в маленьком окне не показывается. Здесь общее с полной картой
 * не код, а ДАННЫЕ: тот же /catalog/map/data.json и то же зерно раскладки,
 * поэтому облако узнаётся глазом как та же карта.
 *
 * ── Как подключить (для чужого экрана) ────────────────────────────────
 *
 *   <link rel="stylesheet" href="{% static 'catalog/css/topic_map_preview.css' %}">
 *   <a class="tmap-preview" data-tmap-preview
 *      data-tmap-preview-data="{% url 'catalog:topic_map_data' %}"
 *      href="{% url 'catalog:topic_map' %}"
 *      aria-label="Интерактивная карта тем и тегов"></a>
 *   <script defer src="{% static 'catalog/js/topic_map_preview.js' %}"></script>
 *
 * Всё остальное скрипт делает сам: находит контейнеры с атрибутом
 * `data-tmap-preview`, ждёт простоя и появления блока на экране, и только
 * тогда идёт за данными.
 *
 * Ручное подключение, если контейнер появляется позже (например, его
 * вставил другой скрипт):
 *
 *   var h = window.TopicMapPreview.mount(el, { href: '/catalog/map/' });
 *   h.stats();     // { state, frames, visible, reduced, msPerFrame }
 *   h.destroy();   // снять наблюдателей и остановить цикл
 */
(function () {
'use strict';

/* ── Настройки по умолчанию ──────────────────────────────────────────── */

var DEFAULTS = {
  dataUrl: '/catalog/map/data.json',
  href: '/catalog/map/',
  /* Рад/кадр. При 60 кадрах это 4,6°/с — оборот за 78 секунд. Медленнее
     полной карты в покое смысла нет: там вращение ещё и подписи возит. */
  spin: 0.0013,
  /* Итераций силовой раскладки. У полной карты 300; здесь меньше, потому
     что подписям место искать не надо, а облако на 300×200 всё равно
     читается общей формой, а не точным местом узла. */
  iterations: 200,
  /* Бюджет одного среза раскладки, мс. ⚠️ РАСКЛАДКА СЧИТАЕТСЯ СРЕЗАМИ, А
     НЕ ОДНИМ КУСКОМ. 200 итераций по 372 узла — это около четверти
     секунды сплошной работы; выполненные разом, они дают долгую задачу и
     подвешивают экран-хозяина ровно в тот момент, когда человек по нему
     кликает. */
  slice: 5,
  /* Во сколько раз крупнее рисовать узлы. В маленьком окне обзор ужимает
     их до точек, и граф выглядит пылью. */
  nodeScale: 1.7,
  margin: 0.05
};

/* ── Мелкие утилиты ──────────────────────────────────────────────────── */

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

function rgba(rgb, a) {
  return 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',' + a + ')';
}

/* Генератор случайных чисел с фиксированным зерном — то же, что у полной
   карты, и зерно то же: облако обязано быть узнаваемо тем же самым. */
function makeRandom(seed) {
  var s = seed >>> 0;
  return function () {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function fibSphere(i, n) {
  var y = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
  var r = Math.sqrt(Math.max(0, 1 - y * y));
  var phi = i * 2.399963229728653;
  return [Math.cos(phi) * r, y, Math.sin(phi) * r];
}

/* Отложенный старт: сначала экран-хозяин, потом мы.
   ⚠️ ЖДЁМ ИМЕННО ЗАГРУЗКИ, А НЕ DOMContentLoaded. Задача — не помешать
   ПЕРВОЙ ОТРИСОВКЕ, а она случается уже после разбора разметки, но обычно
   до конца загрузки картинок и шрифтов. requestIdleCallback добавляет
   сверху «когда браузеру нечего делать»; там, где его нет (Safari до 16),
   довольствуемся таймером. */
function whenIdle(fn) {
  function go() {
    if (window.requestIdleCallback) window.requestIdleCallback(fn, { timeout: 2000 });
    else setTimeout(fn, 200);
  }
  if (document.readyState === 'complete') go();
  else window.addEventListener('load', go, { once: true });
}


/* ═══════════════════════════════════════════════════════════════════════
   ОДИН ПРЕДПРОСМОТР
   ═══════════════════════════════════════════════════════════════════════ */

function mount(el, options) {
  if (!el || el.__tmapPreview) return el ? el.__tmapPreview : null;

  var opt = {};
  var k;
  for (k in DEFAULTS) opt[k] = DEFAULTS[k];
  var ds = el.dataset || {};
  if (ds.tmapPreviewData) opt.dataUrl = ds.tmapPreviewData;
  if (ds.tmapPreviewHref) opt.href = ds.tmapPreviewHref;
  if (el.tagName === 'A' && el.getAttribute('href')) opt.href = el.getAttribute('href');
  if (options) for (k in options) opt[k] = options[k];

  var canvas = document.createElement('canvas');
  canvas.className = 'tmap-preview-canvas';
  /* ⚠️ ХОЛСТ НЕ ЛОВИТ КУРСОР ВООБЩЕ. Так требование «карта ни на что не
     реагирует» держится устройством, а не дисциплиной: у предпросмотра нет
     ни одного обработчика указателя, и клик в любой точке блока достаётся
     самому блоку — то есть ссылке на полную карту. */
  canvas.style.pointerEvents = 'none';
  canvas.setAttribute('aria-hidden', 'true');
  el.appendChild(canvas);

  var ctx = canvas.getContext('2d');

  var W = 0, H = 0, DPR = 1;
  var nodes = [], links = [], byId = {}, themeList = [], tagsOfTheme = {};
  var PAL = { node: [74, 82, 96], bg: [245, 245, 243] };

  var yaw = 0.35, pitch = -0.22, fitScale = 1;
  var DIST = 1240, FOCAL = 900;

  var state = 'idle';          /* idle | loading | settling | live | error */
  var visible = false;
  var frames = 0, drawMs = 0, drawn = 0;
  var raf = 0;
  var left = 0;                /* сколько итераций раскладки осталось */
  var dead = false;

  var mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  var reduced = mq.matches;

  /* ── Раскладка ─────────────────────────────────────────────────────── */

  var R_SPHERE = 470, Y_SQUASH = 0.78;
  var REP = 1450, REP_CUT2 = 640000;
  var K_TREE = 0.055, K_CROSS = 0.006, L_CROSS = 300;
  var CENTER_PULL = 0.0016, DAMP = 0.82;
  var alpha = 1;

  function seedLayout() {
    var rnd = makeRandom(20260829);
    themeList.forEach(function (th, i) {
      var p = fibSphere(i, themeList.length);
      th.x = p[0] * R_SPHERE;
      th.y = p[1] * R_SPHERE * Y_SQUASH;
      th.z = p[2] * R_SPHERE;
      th.vx = th.vy = th.vz = 0;
      var tags = tagsOfTheme[th.n] || [];
      var R = 46 + 5.5 * tags.length;
      th.tagR = R;
      tags.forEach(function (tag, j) {
        var q = fibSphere(j, tags.length);
        var jitter = 0.85 + rnd() * 0.3;
        tag.x = th.x + q[0] * R * jitter;
        tag.y = th.y + q[1] * R * Y_SQUASH * jitter;
        tag.z = th.z + q[2] * R * jitter;
        tag.vx = tag.vy = tag.vz = 0;
      });
    });
  }

  function step() {
    var i, j, n = nodes.length, a, b;
    for (i = 0; i < n; i++) {
      a = nodes[i];
      for (j = i + 1; j < n; j++) {
        b = nodes[j];
        var dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
        var d2 = dx * dx + dy * dy + dz * dz;
        if (d2 > REP_CUT2 || d2 < 0.0001) continue;
        var both = (a.k === 'theme' && b.k === 'theme') ? 9 : 1;
        var f = REP * both / d2;
        var d = Math.sqrt(d2);
        var ux = dx / d, uy = dy / d, uz = dz / d;
        a.vx -= ux * f; a.vy -= uy * f; a.vz -= uz * f;
        b.vx += ux * f; b.vy += uy * f; b.vz += uz * f;
      }
    }
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
        if (dist < L) continue;
      }
      var force = (dist - L) * K;
      var fx = (ddx / dist) * force, fy = (ddy / dist) * force, fz = (ddz / dist) * force;
      a.vx += fx; a.vy += fy; a.vz += fz;
      b.vx -= fx; b.vy -= fy; b.vz -= fz;
    }
    for (i = 0; i < n; i++) {
      a = nodes[i];
      a.vx -= a.x * CENTER_PULL * alpha;
      a.vy -= a.y * CENTER_PULL * alpha * 3.4;
      a.vz -= a.z * CENTER_PULL * alpha;
      a.vx *= DAMP; a.vy *= DAMP; a.vz *= DAMP;
      a.x += a.vx; a.y += a.vy; a.z += a.vz;
    }
    alpha *= 0.995;
  }

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

  /* Обзор по обеим осям сразу — как у полной карты, но считается по
     ТЕКУЩЕМУ углу поворота: облако здесь крутится без остановки, и запас
     должен хватать на весь оборот. Поэтому берём максимум разлёта по
     восьми ракурсам. */
  function computeFit() {
    var hx = 1, hy = 1, t;
    for (t = 0; t < 8; t++) {
      var ang = t * Math.PI / 4;
      var cy = Math.cos(ang), sy = Math.sin(ang);
      var cp = Math.cos(pitch), sp = Math.sin(pitch);
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var ax = n.x * cy + n.z * sy, az = -n.x * sy + n.z * cy;
        var ay = n.y * cp - az * sp, pz = n.y * sp + az * cp + DIST;
        if (pz < 60) continue;
        var s = FOCAL / pz;
        if (Math.abs(ax * s) > hx) hx = Math.abs(ax * s);
        if (Math.abs(ay * s) > hy) hy = Math.abs(ay * s);
      }
    }
    var availX = W * (0.5 - opt.margin), availY = H * (0.5 - opt.margin);
    fitScale = Math.max(0.05, Math.min(4, Math.min(availX / hx, availY / hy)));
  }

  /* ── Отрисовка ─────────────────────────────────────────────────────── */

  function readPalette() {
    /* Читаем у САМОГО БЛОКА: цвета разделов объявлены в скоупе
       `.tmap-preview`, а общие токены сайта блок наследует. */
    var cs = getComputedStyle(el);
    PAL.node = hexToRgb(cs.getPropertyValue('--map-node') || '#4A5260');
    PAL.dark = document.documentElement.getAttribute('data-theme') === 'dark';
    /* Готовые строки цвета по разделам: в кадре разбирать CSS-цвет 372
       раза дороже всей отрисовки. Ключи берём из самих узлов — списка
       разделов у предпросмотра нет, он его и не показывает. */
    PAL.theme = {}; PAL.tag = {};
    for (var i = 0; i < nodes.length; i++) {
      var g = nodes[i].g;
      if (PAL.theme[g]) continue;
      var raw = cs.getPropertyValue('--map-g-' + g);
      var col = raw && raw.trim() ? hexToRgb(raw) : PAL.node;
      PAL.theme[g] = rgba(col, 1);
      PAL.tag[g] = rgba(col, 0.72);
    }
  }

  function draw() {
    var t0 = performance.now();
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    /* ⚠️ ФОН НЕ ЗАКРАШИВАЕТСЯ, А ОЧИЩАЕТСЯ. Блок стоит в чужом экране, и
       свой цвет холста он бы вырезал прямоугольником поверх карточки
       хозяина. Фон задаёт CSS блока. */
    ctx.clearRect(0, 0, W, H);

    var CY = Math.cos(yaw), SY = Math.sin(yaw);
    var CP = Math.cos(pitch), SP = Math.sin(pitch);
    var i, n;

    for (i = 0; i < nodes.length; i++) {
      n = nodes[i];
      var ax = n.x * CY + n.z * SY, az = -n.x * SY + n.z * CY;
      var ay = n.y * CP - az * SP, pz = n.y * SP + az * CP + DIST;
      if (pz < 60) { n.pz = -1; continue; }
      var s = FOCAL / pz * fitScale;
      n.px = W / 2 + ax * s;
      n.py = H / 2 + ay * s;
      n.ps = s;
      n.pz = pz;
    }

    /* Связи одним путём на вид: смена стиля стоит дороже самой линии. */
    var pTree = new Path2D(), pCross = new Path2D();
    for (i = 0; i < links.length; i++) {
      var ln = links[i];
      var a = byId[ln.s], b = byId[ln.t];
      if (a.pz < 0 || b.pz < 0) continue;
      var path = ln.k === 'cross' ? pCross : pTree;
      path.moveTo(a.px, a.py);
      path.lineTo(b.px, b.py);
    }
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(PAL.node, PAL.dark ? 0.30 : 0.38);
    ctx.stroke(pTree);
    ctx.setLineDash([2, 3]);
    ctx.strokeStyle = rgba(PAL.node, PAL.dark ? 0.18 : 0.24);
    ctx.stroke(pCross);
    ctx.setLineDash([]);

    /* Узлы: дальние раньше ближних. Порядок пересобирается каждый кадр —
       сцена вращается, и глубина меняется у всех. */
    nodes.sort(function (p, q) { return q.pz - p.pz; });
    var fallbackTheme = rgba(PAL.node, 1), fallbackTag = rgba(PAL.node, 0.72);
    for (i = 0; i < nodes.length; i++) {
      n = nodes[i];
      if (n.pz < 0) continue;
      if (n.px < -20 || n.px > W + 20 || n.py < -20 || n.py > H + 20) continue;
      var r = Math.max(0.8, n.r0 * n.ps * opt.nodeScale);
      ctx.fillStyle = n.k === 'theme'
        ? (PAL.theme[n.g] || fallbackTheme)
        : (PAL.tag[n.g] || fallbackTag);
      ctx.beginPath();
      ctx.arc(n.px, n.py, r, 0, 6.283185307179586);
      ctx.fill();
    }

    drawn++;
    drawMs += performance.now() - t0;
  }

  /* ── Цикл кадров ───────────────────────────────────────────────────── */

  function tick() {
    raf = 0;
    if (dead) return;
    frames++;

    if (state === 'settling') {
      /* Срез раскладки: считаем, пока не кончится бюджет кадра. */
      var until = performance.now() + opt.slice;
      while (left > 0 && performance.now() < until) { step(); left--; }
      /* ⚠️ ОБЗОР ПЕРЕСЧИТЫВАЕТСЯ И ПО ХОДУ РАСКЛАДКИ, А НЕ ТОЛЬКО В КОНЦЕ.
         Облако разлетается от стартового шара к своему размеру за первые же
         десятки итераций, и с обзором «как было» оно эту секунду лезет за
         края блока. Стоит пересчёт 8 проходов по узлам — вдесятеро дешевле
         одной итерации силовой модели. */
      recentre();
      computeFit();
      if (left <= 0) state = 'live';
      /* ⚠️ ПОКА РАСКЛАДКА СЧИТАЕТСЯ, ПРИ prefers-reduced-motion НЕ РИСУЕМ
         ВОВСЕ. Сама сходимость облака — это движение; показать её значит
         показать анимацию тому, кто её отключил. Лучше пустой блок
         полсекунды и один готовый кадр потом. */
      if (!reduced) draw();
      if (state === 'live' && reduced) draw();
      schedule();
      return;
    }

    if (state === 'live') {
      if (reduced) return;              /* один кадр уже нарисован */
      yaw += opt.spin;
      draw();
      schedule();
    }
  }

  function schedule() {
    if (dead || raf) return;
    if (!visible) return;                          /* блока нет на экране */
    if (reduced && state === 'live') return;       /* движение отключено  */
    if (state !== 'settling' && state !== 'live') return;
    raf = requestAnimationFrame(tick);
  }

  /* ── Размер ────────────────────────────────────────────────────────── */

  function resize() {
    var r = el.getBoundingClientRect();
    var w = Math.max(80, Math.round(r.width));
    var h = Math.max(60, Math.round(r.height));
    if (w === W && h === H && DPR === Math.min(2, window.devicePixelRatio || 1)) return;
    W = w; H = h;
    DPR = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    if (state === 'live') { computeFit(); draw(); }
  }

  /* ── Загрузка данных ───────────────────────────────────────────────── */

  function start() {
    if (state !== 'idle' || dead) return;
    state = 'loading';
    fetch(opt.dataUrl, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (dead) return;
        nodes = data.nodes;
        links = data.links;
        nodes.forEach(function (n) {
          byId[n.id] = n;
          n.r0 = n.k === 'theme'
            ? 7.4 + Math.log(1 + (n.c || 0)) / 1.15
            : 2.5 + Math.log(1 + (n.c || 0)) / 1.9;
          if (n.k === 'theme') themeList.push(n);
          else (tagsOfTheme[n.n] = tagsOfTheme[n.n] || []).push(n);
        });
        readPalette();
        seedLayout();
        left = opt.iterations;
        alpha = 1;
        state = 'settling';
        resize();
        schedule();
      })
      .catch(function () {
        state = 'error';
        el.classList.add('is-failed');
      });
  }

  /* ── Наблюдатели ───────────────────────────────────────────────────── */

  var io = null;
  if (window.IntersectionObserver) {
    io = new IntersectionObserver(function (entries) {
      var was = visible;
      visible = entries[entries.length - 1].isIntersecting;
      if (visible && !was) {
        if (state === 'idle') whenIdle(start);
        else schedule();
      }
      /* Ушли за край экрана — кадр не просто пропускаем, а снимаем
         заявку: иначе браузер продолжает будить нас шестьдесят раз в
         секунду ради проверки «а не пора ли». */
      if (!visible && raf) { cancelAnimationFrame(raf); raf = 0; }
    }, { rootMargin: '120px' });
    io.observe(el);
  } else {
    visible = true;
    whenIdle(start);
  }

  var ro = null;
  if (window.ResizeObserver) {
    ro = new ResizeObserver(resize);
    ro.observe(el);
  } else {
    window.addEventListener('resize', resize);
  }

  function onMotionChange(e) {
    reduced = e.matches;
    if (reduced) {
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      if (state === 'live') draw();      /* застываем на текущем кадре */
    } else {
      schedule();
    }
  }
  if (mq.addEventListener) mq.addEventListener('change', onMotionChange);
  else if (mq.addListener) mq.addListener(onMotionChange);

  var themeWatch = new MutationObserver(function () {
    readPalette();
    if (state === 'live') draw();
  });
  themeWatch.observe(document.documentElement,
                     { attributes: true, attributeFilter: ['data-theme'] });

  /* Клик по блоку. Если контейнер — ссылка, ничего делать не нужно: браузер
     справится сам, включая среднюю кнопку и Ctrl+клик. Для не-ссылки блок
     получает роль ссылки, фокус с клавиатуры и Enter. */
  function onClick() { window.location.href = opt.href; }
  function onKey(e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); }
  }
  var ownsClick = el.tagName !== 'A';
  if (ownsClick) {
    el.addEventListener('click', onClick);
    el.addEventListener('keydown', onKey);
    if (!el.hasAttribute('role')) el.setAttribute('role', 'link');
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
  }

  resize();

  var handle = {
    el: el,
    canvas: canvas,
    stats: function () {
      return {
        state: state, visible: visible, reduced: reduced,
        frames: frames, drawn: drawn,
        msPerFrame: drawn ? +(drawMs / drawn).toFixed(2) : 0,
        nodes: nodes.length, links: links.length, settleLeft: left,
        size: [W, H], fitScale: +fitScale.toFixed(3), yaw: +yaw.toFixed(3)
      };
    },
    /* Идёт ли прямо сейчас цикл кадров. ⚠️ ЭТО И ЕСТЬ ПРОВЕРЯЕМЫЙ
       ИНВАРИАНТ «вне экрана не рисуем»: не «кадры те же самые», а заявки на
       кадр нет вовсе. */
    looping: function () { return !!raf; },
    /* Прогон N кадров ВРУЧНУЮ, без requestAnimationFrame — тем же приёмом,
       что TMAP.spinFrames() у полной карты: в скрытой вкладке браузер кадры
       не гоняет, и ни раскладку досчитать, ни стоимость кадра снять нельзя.
       Только для приёмки. */
    pump: function (n) {
      n = n || 60;
      for (var i = 0; i < n; i++) {
        if (state === 'settling') {
          var until = performance.now() + opt.slice;
          while (left > 0 && performance.now() < until) { step(); left--; }
          recentre();
          computeFit();
          if (left <= 0) state = 'live';
          draw();
        } else if (state === 'live') {
          yaw += opt.spin;
          draw();
        }
      }
      return handle.stats();
    },
    /* Замер стоимости кадра — тем же способом, что TMAP.bench() у полной
       карты: частоту в скрытой вкладке не снять, поэтому меряем сам кадр. */
    bench: function (times) {
      if (state !== 'live') return null;
      times = times || 40;
      draw();
      var t0 = performance.now();
      for (var i = 0; i < times; i++) draw();
      var ms = (performance.now() - t0) / times;
      return { msPerFrame: +ms.toFixed(2), fps: Math.round(1000 / ms) };
    },
    destroy: function () {
      dead = true;
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      if (io) io.disconnect();
      if (ro) ro.disconnect(); else window.removeEventListener('resize', resize);
      themeWatch.disconnect();
      if (mq.removeEventListener) mq.removeEventListener('change', onMotionChange);
      else if (mq.removeListener) mq.removeListener(onMotionChange);
      if (ownsClick) {
        el.removeEventListener('click', onClick);
        el.removeEventListener('keydown', onKey);
      }
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      delete el.__tmapPreview;
      var at = ALL.indexOf(handle);
      if (at >= 0) ALL.splice(at, 1);
    }
  };
  el.__tmapPreview = handle;
  ALL.push(handle);
  return handle;
}


/* ═══════════════════════════════════════════════════════════════════════
   ТОЧКА ВХОДА
   ═══════════════════════════════════════════════════════════════════════ */

var ALL = [];

function scan(root) {
  var list = (root || document).querySelectorAll('[data-tmap-preview]');
  for (var i = 0; i < list.length; i++) mount(list[i]);
  return ALL.length;
}

window.TopicMapPreview = {
  version: 1,
  mount: mount,
  scan: scan,
  all: function () { return ALL.slice(); },
  stats: function () { return ALL.map(function (h) { return h.stats(); }); }
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () { scan(); });
} else {
  scan();
}

})();
