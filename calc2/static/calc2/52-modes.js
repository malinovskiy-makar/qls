// Переключатель режимов и подрежимов.
/* ---------------------------------------------------------------------
   БЛОК 11. ПЕРЕКЛЮЧАТЕЛЬ РЕЖИМОВ (рынок / издержки / КПВ).
   Показывает нужные секции панели и дёргает перерисовку. Сами режимы
   издержек (Задача 2) и КПВ (Задача 3) рисуются своими redraw-функциями.
   --------------------------------------------------------------------- */

// Установить границы осей Qmax/Pmax (и поля ввода / пределы ползунков) разом.
// Нижние границы сцена всегда хочет нулевые: она рисует первую четверть.
/* opts.symmetric — окно раскрывается на все четыре четверти поровну
   (−max…max), а не первая четверть с тонкой каймой. Просится ЯВНО и ровно
   одной моделью: у остальных границы выбраны осознанно, и общая правка
   переставила бы оси там, где их никто не просил трогать. */
function setRanges(qmax, pmax, opts) {
  CONFIG.Qmax = qmax; CONFIG.Pmax = pmax;
  // В режиме «только первая четверть» окно начинается ровно в нуле. Режим сняли —
  // оставляем немного места слева и снизу, чтобы ось не липла к самому краю.
  const sym = !!(opts && opts.symmetric);
  CONFIG.Qmin = STATE.firstQuad ? 0 : (sym ? -qmax : -qmax * 0.08);
  CONFIG.Pmin = STATE.firstQuad ? 0 : (sym ? -pmax : -pmax * 0.08);
  syncViewFields();
  // Адвалорная ставка меряется в ПРОЦЕНТАХ — её пределы к масштабу цены не привязаны
  // (ими управляет applyTaxRateBounds), поэтому поля ставки в этом случае пропускаем.
  const advRate = (STATE.taxKind === 'advalorem');
  ['tax-slider', 'tax-input', 'pc-slider', 'pc-input',
   'labmin-slider', 'labmin-input', 'union-wage-slider', 'union-wage-input',
   'open-pw-slider', 'open-pw-input', 'open-tariff-slider', 'open-tariff-input'].forEach(id => {
    if (advRate && (id === 'tax-slider' || id === 'tax-input')) return;
    const e = document.getElementById(id); if (e) e.max = pmax;
  });
  // Квота меряется в ЕДИНИЦАХ товара — её предел задаёт масштаб количества (Фаза 4в).
  ['open-quota-slider', 'open-quota-input', 'quota-slider', 'quota-input'].forEach(id => { const e = document.getElementById(id); if (e) e.max = qmax; });
}

/* Поля границ в меню плоскости показывают то, что на экране прямо сейчас:
   их двигают и колесо, и панорама, и сцена со своим авто-масштабом. */
function syncViewFields() {
  const math = (STATE.mode === 'math');
  const v = math
    ? [STATE.mathXmin, STATE.mathXmax, STATE.mathYmin, STATE.mathYmax]
    : [CONFIG.Qmin, CONFIG.Qmax, CONFIG.Pmin, CONFIG.Pmax];
  [['inp-qmin', v[0]], ['inp-qmax', v[1]], ['inp-pmin', v[2]], ['inp-pmax', v[3]]].forEach(([id, val]) => {
    const e = document.getElementById(id);
    if (e && document.activeElement !== e) e.value = Math.round(val * 1000) / 1000;
  });
  /* Тумблер излишков ставим в согласие с состоянием: новая модель обнуляет
     showCS/showPS через SCENE_DEFAULTS, и меню, открытое после смены сцены,
     иначе показывало бы прежнее положение. */
  const ac = document.getElementById('chk-areas');
  if (ac) ac.checked = !!(STATE.showCS || STATE.showPS);
  /* «Было → стало» — та же болезнь, что была у излишков: SCENE_DEFAULTS гасит
     showGhost при входе в модель, а галочка в разметке стоит отмеченной. Тумблер
     врал: отмечен, а бледного исходного равновесия на графике нет, и первое
     нажатие человека ничего не убирало (оно и так было выключено). Ставим обе
     галочки в согласие с состоянием там же, где и излишки. */
  ['chk-ghost', 'chk-lab-ghost'].forEach(id => {
    const e = document.getElementById(id);
    if (e) e.checked = !!STATE.showGhost;
  });
  updateResetViewBtn();
}

// Кнопка возврата масштаба появляется, только когда есть куда возвращаться.
/* ⚠️ МЕСТО ПОД КНОПКУ ЗАНЯТО ВСЕГДА (п. 31).
   Кнопка появляется, только когда есть куда возвращаться, — это верно. Но
   пряталась она через `hidden`, то есть с выпадением из раскладки, и стопка
   разъезжалась: гаечный ключ уезжал с отметки 79 px на 117 px прямо под рукой,
   и человек промахивался по кнопке, которой только что пользовался.
   Теперь слот держит своё место, а меняется только видимость. */
function updateResetViewBtn() {
  const b = document.getElementById('btn-resetview');
  if (!b) return;
  const show = !!STATE.viewDirty;
  if (show === !b.classList.contains('is-off')) return;
  b.classList.toggle('is-off', !show);
  b.disabled = !show;
  b.setAttribute('aria-hidden', show ? 'false' : 'true');
  b.tabIndex = show ? 0 : -1;
  if (show) { b.classList.remove('appear'); void b.offsetWidth; b.classList.add('appear'); }
}

// Пользователь сам выбрал масштаб: авто-подгонка сцены отступает.
function markViewDirty() {
  STATE.viewDirty = true;
  STATE.zoomLock = true;
  updateResetViewBtn();
}

/* ---------------------------------------------------------------------
   Плавная анимация осей (КТВ). При смене мировой цены Pw в режиме
   КПВ → КТВ масштаб не должен скакать: оси и кривые плавно «доезжают»
   до нового масштаба за ~0.45 с (ease-out). Идея — не менять отрисовку,
   а интерполировать CONFIG.Qmax/Pmax по кадрам requestAnimationFrame и
   каждый кадр звать redrawAll() (он сам перечитывает CONFIG и рисует всё).
   Анимируем ТОЛЬКО смену Pw; переключение сцен/режимов — мгновенно.
   --------------------------------------------------------------------- */
let _rangeAnimReq = null;     // id текущего кадра анимации (для отмены)
let _rangeAnimating = false;  // идёт ли анимация прямо сейчас (мы внутри кадра)
let _wantRangeAnim = false;   // одноразовый запрос анимации от ползунка/поля Pw
let _paramOnlyRedraw = false; // перерисовка вызвана ТОЛЬКО сменой значения буквы
                              // (разбор правила — у redrawKeepingWindow ниже)

function prefersReducedMotion() {
  return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

// Плавно перевести масштаб осей к (targetQmax, targetPmax) за ~450 мс (ease-out).
function animateRanges(targetQmax, targetPmax) {
  // Отменить незавершённую анимацию (быстрые подёргивания ползунка Pw).
  if (_rangeAnimReq != null) { cancelAnimationFrame(_rangeAnimReq); _rangeAnimReq = null; }
  const startQ = CONFIG.Qmax, startP = CONFIG.Pmax;
  // Уже на месте — просто выставить точные значения, без анимации.
  if (Math.abs(startQ - targetQmax) < 1e-6 && Math.abs(startP - targetPmax) < 1e-6) {
    setRanges(targetQmax, targetPmax); return;
  }
  const DUR = 450;            // длительность, мс
  let t0 = null;
  const step = (ts) => {
    if (t0 == null) t0 = ts;
    let t = (ts - t0) / DUR; if (t > 1) t = 1;
    const e = 1 - (1 - t) * (1 - t);    // ease-out (квадратичный)
    _rangeAnimating = true;             // в кадре recompute не трогает CONFIG (цикл ведёт сам)
    CONFIG.Qmax = startQ + (targetQmax - startQ) * e;
    CONFIG.Pmax = startP + (targetPmax - startP) * e;
    redrawAll();
    _rangeAnimating = false;
    if (t < 1) {
      _rangeAnimReq = requestAnimationFrame(step);
    } else {
      _rangeAnimReq = null;
      setRanges(targetQmax, targetPmax);  // точные финальные значения + синк полей «Оси»/ползунков
    }
  };
  _rangeAnimReq = requestAnimationFrame(step);
}

// Применить масштаб осей в КТВ: анимировать (если запрошено сменой Pw и не reduce-motion)
// либо выставить мгновенно. Вызывается ВМЕСТО прямого setRanges в recompute КТВ.
function applyTradeRanges(targetQmax, targetPmax) {
  if (_rangeAnimating) return;                 // внутри кадра анимации границами управляет цикл
  if (_paramOnlyRedraw) { _wantRangeAnim = false; return; }   // окно идёт за формулой, не за буквой
  /* П54. Масштаб, выбранный человеком, главнее авто-подгонки — ровно как в
     applyAutoRanges. Без этой проверки сцены торговли возвращали свой вид на
     первой же перерисовке, и колесо на них не работало совсем. */
  if (STATE.zoomLock) { _wantRangeAnim = false; return; }
  const wantAnim = _wantRangeAnim;
  _wantRangeAnim = false;                       // запрос одноразовый — гасим сразу
  if (wantAnim && !prefersReducedMotion()) animateRanges(targetQmax, targetPmax);
  else setRanges(targetQmax, targetPmax);
}

/* --- Плавный авто-масштаб с дебаунсом (КПВ одна/сумма, труд) ---------------
   Тот же твин animateRanges, что у КТВ, но с маленькой задержкой (~90 мс): при
   живом кручении ползунка экран НЕ дёргается на каждый пиксель — оси «доезжают»
   до нового размера, когда пользователь чуть притормозит. Цель считается из
   данных (не из CONFIG) — во время кадра анимации recompute её не трогает
   (guard _rangeAnimating). reduce-motion → мгновенный setRanges. */
const RANGE_DEBOUNCE = 90;     // мс задержки перед стартом плавного переезда осей
let _rangeSchedT = null;       // таймер дебаунса
let _rangeSchedTarget = null;  // последняя запрошенная цель [qmax, pmax]

function scheduleRangeAnim(qmax, pmax) {
  _rangeSchedTarget = [qmax, pmax];
  clearTimeout(_rangeSchedT);
  _rangeSchedT = setTimeout(() => {
    _rangeSchedT = null;
    if (_rangeAnimating) return;
    const [q, p] = _rangeSchedTarget;
    animateRanges(q, p);
  }, RANGE_DEBOUNCE);
}

// Аналог applyTradeRanges для сцен с авто-масштабом: вход на сцену / reduce-motion —
// мгновенно; живое кручение ползунка (_wantRangeAnim) — плавно с дебаунсом.
/* Запас у конца оси (П33). Раньше он был раскидан по сценам множителями
   ×1.05, ×1.1, ×1.12, ×1.15, ×1.2 — где-то подпись «Y» налезала на кривую,
   где-то оставалось полполя пустоты. Одна функция на весь калькулятор:
   к самому дальнему числу добавляем 12 %, потом округляем до «красивого».
   Через неё же считает возврат масштаба, поэтому вид всегда один и тот же. */
const AXIS_PAD = 1.12;
function padMax(v) {
  // На пустом или отрицательном входе ведём себя как niceMax: он в таком
  // случае отдаёт 10. Это не косметика — в «Оптимуме при ограничении» зонд
  // ограничения находит всего одну точку с x = 0, и сцена всегда жила на этом
  // запасном значении. Верни сюда 1.5 (то есть niceMax(1·1.12)) — окно
  // схлопнется, и оптимум уедет на границу.
  if (!(isFinite(v) && v > 0)) return niceMax(0);
  return niceMax(v * AXIS_PAD);
}

/* Н20. Перехваты ВСЕХ построенных кривых с осями. Именно перехваты, а не размах
   кривой: растущая кривая вроде S = Q не кончается никогда, и по её протяжённости
   окно раздувалось бы бесконечно. А точка, где кривая встречает ось, конечна и
   как раз задаёт, сколько места модели нужно.

   Ищем два числа на кривую: значение в нуле (перехват с осью Y) и первый
   положительный корень (перехват с осью X). Корень ищем численно в окне втрое
   шире текущего: этого хватает и когда сцену только что открыли. */
function curveAxisBounds() {
  let mx = 0, my = 0, any = false;
  let targets = [];
  try { targets = (typeof snapTargets === 'function') ? snapTargets() : []; } catch (e) { targets = []; }
  const hi = Math.max(10, (CONFIG.Qmax - CONFIG.Qmin) * 3);
  targets.forEach(t => {
    if (typeof t.f !== 'function') return;
    const y0 = t.f(0);
    if (isFinite(y0) && y0 > 0) { my = Math.max(my, y0); any = true; }
    /* findRootIn объявлен в файле сцен, который грузится ПОЗЖЕ этого. К моменту
       вызова он на месте, но проверяем явно: без этого ReferenceError молча
       уходил в catch, и умный подбор так же молча откатывался к 100 на 100. */
    let root = null;
    if (typeof findRootIn === 'function') {
      try { root = findRootIn((x) => t.f(x), 1e-6, hi); } catch (e) { root = null; }
    }
    if (root != null && isFinite(root) && root > 0) { mx = Math.max(mx, root); any = true; }
  });
  return any ? { qmax: mx, pmax: my } : null;
}

/* Границы по тому, что РЕАЛЬНО нарисовано (П32): свои точки, вершины будущей
   площади, посчитанные площади и ключевые точки. Отсчёт идёт от переданного
   основания (его задают перехваты кривых, см. curveAxisBounds выше) и только
   РАСШИРЯЕТСЯ — до того, что за него вылезло. Сами кривые здесь не опрашиваются:
   их вклад уже учтён основанием. */
function boundsOfDrawn(baseQ, baseP) {
  let mx = baseQ, my = baseP, grew = false;
  const eat = (x, y) => {
    if (!isFinite(x) || !isFinite(y)) return;
    if (x > mx) { mx = x; grew = true; }
    if (y > my) { my = y; grew = true; }
  };
  (STATE.marks || []).forEach(m => { if (!m.pending) eat(m.x, m.y); });
  (STATE.areaVerts || []).forEach(v => eat(v.x, v.y));
  (STATE.areaCalcList || []).forEach(r => {
    if (r.ring) r.ring.forEach(p => eat(p[0], p[1]));
    else if (isFinite(r.b)) eat(r.b, 0);
  });
  try { (keyTargets() || []).forEach(p => eat(p.x, p.y)); } catch (e) {}
  if (!grew) return null;                      // всё и так помещается
  return { qmax: mx > baseQ ? padMax(mx) : baseQ,
           pmax: my > baseP ? padMax(my) : baseP };
}

/* ⚠️ АВТО-ПОДГОНКА ОСЕЙ ИДЁТ ЗА ФОРМУЛОЙ, А НЕ ЗА ЗНАЧЕНИЕМ БУКВЫ.

   Ради этого правила существует флаг ниже. Сцены, которые вписывают свою кривую
   в окно на каждой перерисовке (КПВ, КТВ, сумма КПВ, труд, фирма, потребитель,
   вся макроэкономика), при линейной формуле давали БАЙТ В БАЙТ ту же картинку,
   сколько бы ни двигали ползунок буквы: прямая идёт от перехвата до перехвата,
   а оси едут вместе с перехватами. У «y = 100 − a·x» при a = 1 и при a = 10
   линия занимала одни и те же пиксели, менялись только числа на осях. Владелец
   на приёмке 20.08 прочитал это ровно так, как оно выглядит: рычаг не двигает
   ничего. И был прав — рычаг обязан двигать КРИВУЮ.

   Поэтому окно подбирается тогда, когда меняется САМА ФУНКЦИЯ: сцена
   загрузилась, формулу вписали заново, тронули регулятор модели (ставка,
   мировая цена, границы КПВ). Значение буквы окна не трогает: линия ходит
   внутри того окна, которое уже выбрано, и её видно.

   Вернуть вид, если кривая ушла за край, по-прежнему можно кнопкой возврата
   масштаба — она считает границы по нарисованному (boundsOfDrawn).

   Сам признак объявлен рядом с прочими флагами масштаба, выше по файлу: его
   читает и applyTradeRanges, которая стоит раньше этого места. */
function redrawKeepingWindow() {
  _paramOnlyRedraw = true;
  try { redrawAll(); } finally { _paramOnlyRedraw = false; }
}

function applyAutoRanges(qmax, pmax) {
  if (_rangeAnimating) return;
  if (_paramOnlyRedraw) { _wantRangeAnim = false; return; }
  // Пользователь покрутил колесо — его масштаб главнее авто-подгонки, иначе
  // сцена возвращала бы свой вид на первой же перерисовке. Снимается сменой
  // сцены или двойным щелчком по графику (resetZoom).
  if (STATE.zoomLock) { _wantRangeAnim = false; return; }
  const wantAnim = _wantRangeAnim;
  _wantRangeAnim = false;
  if (wantAnim && !prefersReducedMotion()) scheduleRangeAnim(qmax, pmax);
  else setRanges(qmax, pmax);
}

/* ---------------------------------------------------------------------
   ЗУМ И ПАНОРАМИРОВАНИЕ
   Колесо и щипок приближают, перетаскивание фона двигает окно вбок и вверх
   вниз. Экономические сцены живут в первой четверти, поэтому зум растягивает
   окно от начала координат: это привычное «отдалить, чтобы увидеть больше».
   Раздел «Математика» показывает полный план, и там окно тянется К КУРСОРУ,
   как в обычном графопостроителе.
   --------------------------------------------------------------------- */
const ZOOM_MIN = 1e-3, ZOOM_MAX = 1e7;

// Три значащие цифры: и полям границ есть что показать, и мелкий шаг колеса
// не залипает на округлении.
function zoomRound(v) {
  if (!isFinite(v) || v <= 0) return v;
  const mag = Math.pow(10, Math.floor(Math.log10(v)) - 2);
  return Math.round(v / mag) * mag;
}

function zoomBy(factor, px, py) {
  if (!isFinite(factor) || factor <= 0) return;
  /* ⚠️ КОЛЕСО КРУТИТ ПАНЕЛЬ ПОД КУРСОРОМ, А НЕ ХОЛСТ ЦЕЛИКОМ.
     Раньше здесь всегда менялись CONFIG.Qmax/Pmax, поэтому в многопанельных
     сценах колесо действовало только там, где панель на CONFIG и опирается:
     у мини-рынка с горизонтальной мировой ценой своего масштаба нет, и он
     откатывался к CONFIG — колесо над ЛЕВОЙ панелью меняло ПРАВУЮ. */
  const gid = gesturePanelId(px, py);
  if (gid) {
    if (panelZoomBy(gid, factor, px, py)) { markViewDirty(); redrawAll(); }
    return;
  }
  if (STATE.mode === 'math') {
    const m = CONFIG.margin;
    const w = Math.max(1, W - m.left - m.right);
    const tx = Math.min(1, Math.max(0, (px - m.left) / w));
    // Сюжет про производную: панели независимы, поэтому зумим ТУ, над которой
    // стоит курсор, и только её. Мимо панелей — ничего не делаем.
    if (STATE.mathSub === 'tangent') {
      const which = tangentPanelAt(py);
      if (!which) return;
      const L = tangentLayout();
      const pxTop = (which === 'top') ? L.top : L.botTop;
      const pxBot = (which === 'top') ? L.yMid : L.bottom;
      const hh = Math.max(1, pxBot - pxTop);
      const ty2 = Math.min(1, Math.max(0, (py - pxTop) / hh));
      const wn = tanWin(which);
      const span = (wn.xmax - wn.xmin) * factor;
      if (!(span > 1e-6 && span < 1e9)) return;
      const xc = wn.xmin + (wn.xmax - wn.xmin) * tx;
      const yc = wn.ymax - (wn.ymax - wn.ymin) * ty2;
      const nx0 = xc - (xc - wn.xmin) * factor, nx1 = xc + (wn.xmax - xc) * factor;
      const ny0 = yc - (yc - wn.ymin) * factor, ny1 = yc + (wn.ymax - yc) * factor;
      wn.xmin = nx0; wn.xmax = nx1; wn.ymin = ny0; wn.ymax = ny1;
      wn.auto = false;                     // масштаб выбрал человек, авто-подбор молчит
      markViewDirty();
      redrawAll();
      return;
    }
    const h = Math.max(1, H - m.top - m.bottom);
    const ty = Math.min(1, Math.max(0, (py - m.top) / h));
    const x0 = STATE.mathXmin, x1 = STATE.mathXmax, y0 = STATE.mathYmin, y1 = STATE.mathYmax;
    const span = (x1 - x0) * factor;
    if (!(span > 1e-6 && span < 1e9)) return;
    const xc = x0 + (x1 - x0) * tx;
    const yc = y1 - (y1 - y0) * ty;
    setMathWindow(xc - (xc - x0) * factor, xc + (x1 - xc) * factor,
                  yc - (yc - y0) * factor, yc + (y1 - yc) * factor);
    markViewDirty();
    redrawAll();
    return;
  }
  cancelRangeAnim();          // отложенный переезд осей больше не нужен
  if (!STATE.firstQuad) {
    // Полный план: окно тянется К КУРСОРУ, как в обычном графопостроителе.
    const m = CONFIG.margin;
    const w = Math.max(1, W - m.left - m.right), h = Math.max(1, H - m.top - m.bottom);
    const tx = Math.min(1, Math.max(0, (px - m.left) / w));
    const ty = Math.min(1, Math.max(0, (py - m.top) / h));
    const x0 = CONFIG.Qmin, x1 = CONFIG.Qmax, y0 = CONFIG.Pmin, y1 = CONFIG.Pmax;
    const span = (x1 - x0) * factor;
    if (!(span > ZOOM_MIN && span < ZOOM_MAX)) return;
    const xc = x0 + (x1 - x0) * tx, yc = y1 - (y1 - y0) * ty;
    CONFIG.Qmin = xc - (xc - x0) * factor; CONFIG.Qmax = xc + (x1 - xc) * factor;
    CONFIG.Pmin = yc - (yc - y0) * factor; CONFIG.Pmax = yc + (y1 - yc) * factor;
    markViewDirty();
    syncViewFields();
    redrawAll();
    return;
  }
  const q = CONFIG.Qmax * factor, p = CONFIG.Pmax * factor;
  if (q < ZOOM_MIN || p < ZOOM_MIN || q > ZOOM_MAX || p > ZOOM_MAX) return;
  // Первая четверть: окно растягивается от начала координат.
  const qmin = CONFIG.Qmin * factor, pmin = CONFIG.Pmin * factor;
  setRanges(zoomRound(q), zoomRound(p));
  CONFIG.Qmin = qmin; CONFIG.Pmin = pmin;
  markViewDirty();
  syncViewFields();
  redrawAll();
}

/* Панорамирование: сдвиг окна на столько единиц, на сколько уехал курсор.
   Тянем «бумагу под графиком», поэтому окно едет в противоположную сторону. */
function panByPixels(dxPx, dyPx, panel) {
  const m = CONFIG.margin;
  const w = Math.max(1, W - m.left - m.right), h = Math.max(1, H - m.top - m.bottom);
  // Тянем окно ТОЙ панели, с которой начали жест (её запомнил pointerdown).
  if (panel && panel.gesture) {
    if (panelPanBy(panel.gesture, dxPx, dyPx)) { markViewDirty(); syncViewFields(); redrawAll(); }
    return;
  }
  if (STATE.mode === 'math') {
    // Сюжет про производную: двигаем только ту панель, с которой начали.
    if (STATE.mathSub === 'tangent') {
      if (!panel) return;
      const L = tangentLayout();
      const hh = Math.max(1, (panel === 'top') ? (L.yMid - L.top) : (L.bottom - L.botTop));
      const wn = tanWin(panel);
      const dx = (wn.xmax - wn.xmin) * dxPx / w;
      const dy = (wn.ymax - wn.ymin) * dyPx / hh;
      wn.xmin -= dx; wn.xmax -= dx;
      wn.ymin += dy; wn.ymax += dy;
      wn.auto = false;
      markViewDirty();
      syncViewFields();
      redrawAll();
      return;
    }
    const dx = (STATE.mathXmax - STATE.mathXmin) * dxPx / w;
    const dy = (STATE.mathYmax - STATE.mathYmin) * dyPx / h;
    setMathWindow(STATE.mathXmin - dx, STATE.mathXmax - dx,
                  STATE.mathYmin + dy, STATE.mathYmax + dy);
  } else {
    const dq = (CONFIG.Qmax - CONFIG.Qmin) * dxPx / w;
    const dp = (CONFIG.Pmax - CONFIG.Pmin) * dyPx / h;
    CONFIG.Qmin -= dq; CONFIG.Qmax -= dq;
    CONFIG.Pmin += dp; CONFIG.Pmax += dp;
    /* П10 · Н-глобальное. Здесь стоял возврат окна в первую четверть: уехало
       начало ниже нуля — вернуть. Из-за него после приближения поле переставало
       двигаться в ДВЕ стороны из четырёх. Зум прижимает окно началом к нулю
       (Qmin = 0), и любой сдвиг вправо или вверх делал Qmin отрицательным, а
       возврат тут же ставил его обратно: пользователь тянул, и ничего не
       происходило. Проверка этого не ловила, потому что тянула только в ту
       сторону, которая и так работала.

       Тяга это осознанное действие: куда потянули, то и показываем.

       ⚠️ НО ГАЛОЧКА «ТОЛЬКО ПЕРВАЯ ЧЕТВЕРТЬ» — ЭТО ОБЕЩАНИЕ (п. 30).
       При снятом ограничении окно едет свободно, как и задумано выше. При
       ВКЛЮЧЁННОМ уезжать ниже нуля нельзя: замер поймал Pmin = −41,8, сетку
       в отрицательной области и пропавшие подписи оси цен. Стена мягкая —
       окно доезжает до нуля и там останавливается, СОХРАНЯЯ свой размер,
       поэтому тяга не «залипает»: движение видно до самого края, как у любой
       прокручиваемой области. Две стороны из четырёх у прижатого к нулю окна
       и должны стоять: показывать за ними нечего.

       Здесь была история наоборот (П10): возврат в четверть стоял БЕЗУСЛОВНО,
       и мешал даже при снятой галочке. Условие — вся разница. */
    if (STATE.firstQuad) {
      if (CONFIG.Qmin < 0) { CONFIG.Qmax -= CONFIG.Qmin; CONFIG.Qmin = 0; }
      if (CONFIG.Pmin < 0) { CONFIG.Pmax -= CONFIG.Pmin; CONFIG.Pmin = 0; }
    }
    cancelRangeAnim();
  }
  markViewDirty();
  syncViewFields();
  redrawAll();
}

// Двойной щелчок по графику (и кнопка над графиком) возвращают масштаб сцены:
// снимаем замок и даём сцене снова подогнать оси под свои данные.
/* П32. Возврат масштаба показывает ВСЁ, что нарисовано: кривые, свои точки,
   вершины, посчитанные площади и ключевые точки. Раньше здесь стояли жёстко
   зашитые числа (издержки 10 на 50, остальное 100 на 100), и точка за краем
   после возврата так и оставалась за краем. Сцены с собственной авто-подгонкой
   работают как прежде: у них подгонка отработает на первой же перерисовке,
   как только снят замок. */
function resetZoom() {
  STATE.zoomLock = false;
  STATE.viewDirty = false;
  tanResetWindows();
  resetPanelWins();      // окна панелей тоже возвращаются к тому, что даёт сцена
  if (STATE.mode === 'math') {
    /* Н20: подбор работает и здесь. Пресет сюжета берём за основу (в
       «Математике» нужен полный план, а не только первая четверть), но окно
       раздвигаем, если построенное в него не помещается. */
    const p = MATH_PRESETS[STATE.mathSub];
    if (p) {
      let [x0, x1, y0, y1] = p.win;
      const b = boundsOfDrawn(x1, y1);
      if (b) { x1 = Math.max(x1, b.qmax); y1 = Math.max(y1, b.pmax); }
      setMathWindow(x0, x1, y0, y1);
    }
  } else {
    /* Н20, Н21. Порядок ровно такой: сначала перехваты кривых с осями, затем
       проверка, влезли ли точки и площади, и только если нет — отдаляемся.
       Жёсткие числа (издержки 10 на 50, остальное 100 на 100) остались лишь
       как запасной вариант, когда кривых ещё нет вовсе. */
    const fallbackQ = (STATE.mode === 'costs') ? 10 : 100;
    const fallbackP = (STATE.mode === 'costs') ? 50 : 100;
    /* Привычный масштаб сцены остаётся, пока кривые в него помещаются: у
       стандартного спроса перехваты ровно на краях окна, и раздвигать его
       незачем. Раздвигаем только тогда, когда перехват ВЫШЕ края, то есть
       кривая иначе не поместилась бы. */
    const c = curveAxisBounds();
    const baseQ = (c && c.qmax > fallbackQ) ? padMax(c.qmax) : fallbackQ;
    const baseP = (c && c.pmax > fallbackP) ? padMax(c.pmax) : fallbackP;
    const b = boundsOfDrawn(baseQ, baseP);
    setRanges(b ? b.qmax : baseQ, b ? b.pmax : baseP);
  }
  syncViewFields();
  redrawAll();
}

/* Колесо и жест тачпада приходят пачками по несколько событий на кадр. Если
   перерисовывать холст на каждое, экран моргает, а подписи дёргаются. Копим
   события и применяем один раз за кадр — движение получается плавным. */
let _wheelAcc = null;
function flushWheel() {
  const a = _wheelAcc;
  _wheelAcc = null;
  if (!a) return;
  const gid = gesturePanelId(a.px, a.py);
  const panel = gid ? { gesture: gid }
    : ((STATE.mode === 'math' && STATE.mathSub === 'tangent') ? tangentPanelAt(a.py) : null);
  if (a.panX || a.panY) panByPixels(a.panX, a.panY, panel);
  else if (a.factor !== 1) zoomBy(a.factor, a.px, a.py);
}

function initZoom() {
  const gw = document.getElementById('graph-wrap');
  if (!gw) return;
  /* ⚠️ ПОЗИЦИЯ КУРСОРА — ОБЩЕЕ ЗНАНИЕ, А НЕ ЧАСТНОЕ ДЕЛО ОБРАБОТЧИКА.
     По ней `activePanel()` решает, чьи шкалы отдать тому, кто спросил без
     аргумента. Слушаем в фазе погружения и отдельно от жестов: тот
     обработчик ниже выходит рано (нет протяжки — нечего делать), и позиция
     обновлялась бы только во время перетаскивания. */
  gw.addEventListener('pointermove', (e) => {
    const r = gw.getBoundingClientRect();
    STATE.pointerPx = e.clientX - r.left;
    STATE.pointerPy = e.clientY - r.top;
  }, true);
  gw.addEventListener('wheel', (e) => {
    e.preventDefault();
    let dy = e.deltaY, dx = e.deltaX;
    const k = (e.deltaMode === 1) ? 16 : (e.deltaMode === 2 ? 100 : 1);
    dy *= k; dx *= k;
    const r = gw.getBoundingClientRect();
    if (!_wheelAcc) {
      _wheelAcc = { factor: 1, panX: 0, panY: 0, px: e.clientX - r.left, py: e.clientY - r.top };
      requestAnimationFrame(flushWheel);
    }
    /* Щипок на тачпаде приходит сюда же, но с ctrlKey и мелкой дельтой,
       поэтому ему нужен более крупный шаг. Двупальцевый свайп без ctrl и с
       заметным горизонтальным сдвигом — это прокрутка вбок, а не зум.
       П10: с обычной мышью горизонтальной дельты не бывает вовсе, поэтому
       колесо на Windows всегда оказывалось зумом и никогда сдвигом. Добавлен
       Shift: с ним колесо двигает поле по горизонтали, как в любом редакторе. */
    if (e.shiftKey && !e.ctrlKey) { _wheelAcc.panX += -(dx || dy); return; }
    if (!e.ctrlKey && Math.abs(dx) > Math.abs(dy)) { _wheelAcc.panX += -dx; _wheelAcc.panY += dy; return; }
    _wheelAcc.px = e.clientX - r.left; _wheelAcc.py = e.clientY - r.top;
    _wheelAcc.factor *= Math.exp(dy * (e.ctrlKey ? 0.011 : 0.0022));
  }, { passive: false });
  gw.addEventListener('dblclick', () => resetZoom());

  /* Перетаскивание фона. Стартуем только на пустом месте: у кривых, точек и
     клина свои d3-drag, и перехватывать их нельзя. Порог в 3 пикселя не даёт
     обычному щелчку (постановка точки) превратиться в микро-сдвиг. */
  let pan = null, roll = null;
  // Правая кнопка двигает поле — своё меню браузера тут только мешает (П10).
  gw.addEventListener('contextmenu', (e) => e.preventDefault());
  gw.addEventListener('pointerdown', (e) => {
    /* П10. На Windows тянуть поле было нечем: левая кнопка рядом с кривой
       уходила в прокатывание точки, а кривые на приближённом графике повсюду.
       Теперь поле двигают ПРАВОЙ кнопкой или левой с зажатым пробелом либо
       Shift — и тогда прокатывание не перехватывает нажатие. */
    const forcePan = (e.button === 2) || _spaceDown || e.shiftKey;
    if (forcePan) {
      if (canvasArmed()) return;
      const rp = gw.getBoundingClientRect();
      const gid = gesturePanelId(e.clientX - rp.left, e.clientY - rp.top);
      const panel = gid ? { gesture: gid }
        : ((STATE.mode === 'math' && STATE.mathSub === 'tangent')
            ? tangentPanelAt(e.clientY - rp.top) : null);
      pan = { x: e.clientX, y: e.clientY, moved: false, id: e.pointerId, panel };
      e.preventDefault();
      return;
    }
    // п. 25. Взведённый режим — единственный хозяин щелчка: ни прокатывание
    // точки, ни сдвиг поля не имеют права его перехватить.
    if (e.button !== 0 || canvasArmed()) return;
    /* ⚠️ ОДНО НАЖАТИЕ — ОДИН СМЫСЛ, И РЕШАЕТСЯ ОН НЕ В МОМЕНТ НАЖАТИЯ.

       Прокатывание начиналось прямо на pointerdown: оно тут же забирало
       указатель себе (setPointerCapture) и звало перерисовку. Полосу кривой
       при этом пересобирало заново, поэтому ни mouseup, ни click до неё уже
       не доходили — щелчок по кривой не существовал как событие вовсе.
       Замер: из всех событий нажатия до полосы доходило одно, mousedown.

       Теперь пресс по кривой только ЗАПОМИНАЕТСЯ. Сдвинули указатель — это
       прокатывание, оно и начинается. Отпустили не сдвинув — это щелчок, и он
       спокойно доходит до полосы и взводит кривую. Порога взведения это не
       вводит: взводит настоящее событие click, а не расстояние.

       Если под нажатием лежит ПОДВИЖНАЯ кривая, прокатывания нет вовсе:
       у такого нажатия уже есть хозяин — перетаскивание самой кривой. Раньше
       оба жеста шли одновременно, и это и есть та «одновременно двигается и
       кривая, и точка», о которой писал владелец. */
    const r0 = gw.getBoundingClientRect();
    const onDragBand = !!(e.target && e.target.getAttribute &&
                          e.target.getAttribute('data-hit-name') !== null &&
                          (e.target.style.cursor === 'ns-resize' || e.target.style.cursor === 'ew-resize'));
    const hit = onDragBand ? null : rollerTargetAt(e.clientX - r0.left, e.clientY - r0.top);
    if (hit) {
      roll = { id: e.pointerId, hit, live: false, x0: e.clientX, y0: e.clientY };
      return;
    }
    const t = e.target;
    if (t && t.closest && t.closest('.graph-tools, .wrench')) return;
    const tag = (t && t.tagName || '').toLowerCase();
    /* ⚠️ ОДНО НАЖАТИЕ — ОДИН СМЫСЛ, манипуляторы сцены (замер владельца 21.08,
       ручка налога в «Потоварных налогах»). Клин налога t, потолок/пол цены,
       Wmin, Pw, цена в длительном периоде и им подобные рисуются прозрачным
       rect с курсором grab и уже держат свой d3-drag (см. «МАНИПУЛЯТОРЫ СЦЕНЫ»
       в 30-curves.js — там же и сказано «курсор у них grab»). Тот же rect
       ниже проходит как фон, и pointerdown раньше запускал сразу два жеста:
       ручка меняла значение, а этот обработчик тащил поле следом за пальцем.
       Признак — курсор grab на самом элементе, а не перечень сцен: список
       забудут дополнить при новом сюжете. */
    if (tag === 'rect' && t.style && t.style.cursor === 'grab') return;
    if (tag !== 'svg' && tag !== 'rect' && !(t && t.classList && t.classList.contains('grid'))) {
      // Внутри SVG отзывчивы только сами фигуры; фон — это svg и прозрачные rect.
      if (tag !== 'g' && tag !== 'div') return;
    }
    // Панель запоминаем в момент нажатия: у сюжета про производную их две,
    // и вести надо ту, с которой начали, даже если курсор ушёл на соседнюю.
    const gid2 = gesturePanelId(e.clientX - r0.left, e.clientY - r0.top);
    const panel = gid2 ? { gesture: gid2 }
      : ((STATE.mode === 'math' && STATE.mathSub === 'tangent')
          ? tangentPanelAt(e.clientY - r0.top) : null);
    pan = { x: e.clientX, y: e.clientY, moved: false, id: e.pointerId, panel };
  });
  gw.addEventListener('pointermove', (e) => {
    if (roll && e.pointerId === roll.id) {
      if (!roll.live) {
        // Пока указатель стоит на месте, это ещё щелчок, а не прокатывание.
        if (Math.hypot(e.clientX - roll.x0, e.clientY - roll.y0) < ROLL_START_PX) return;
        roll.live = true;
        STATE.roller = { f: roll.hit.f, name: roll.hit.name,
                         color: roll.hit.color || null, panel: roll.hit.panel || null,
                         x: 0, y: 0, pinned: true };
        try { gw.setPointerCapture(roll.id); } catch (err) {}
      }
      rollerMove(e.clientX - gw.getBoundingClientRect().left, e.clientX, e.clientY);
      return;
    }
    if (!pan || e.pointerId !== pan.id) return;
    const dx = e.clientX - pan.x, dy = e.clientY - pan.y;
    if (!pan.moved && Math.hypot(dx, dy) < 3) return;
    // Захват указателя не критичен: без него сдвиг просто оборвётся за краем
    // холста. А исключение здесь останавливало бы само движение.
    if (!pan.moved) {
      pan.moved = true;
      try { gw.setPointerCapture(pan.id); } catch (err) {}
      gw.style.cursor = 'grabbing';
    }
    pan.x = e.clientX; pan.y = e.clientY;
    panByPixels(dx, dy, pan.panel);
  });
  const endPan = (e) => {
    if (roll && e.pointerId === roll.id) {
      const wasLive = roll.live;
      try { gw.releasePointerCapture(roll.id); } catch (err) {}
      roll = null;
      // Не катили — и убирать нечего: перерисовка здесь снесла бы полосу
      // раньше, чем до неё дойдёт щелчок, и мы вернулись бы к прежней беде.
      if (wasLive) rollerOff();
      return;
    }
    if (!pan) return;
    if (pan.moved) { try { gw.releasePointerCapture(pan.id); } catch (err) {} gw.style.cursor = ''; }
    pan = null;
  };
  gw.addEventListener('pointerup', endPan);
  gw.addEventListener('pointercancel', endPan);

  /* Клавиатура (П10): стрелки двигают поле, плюс и минус меняют масштаб.
     Пробел, пока зажат, превращает левую кнопку в «руку» — привычный жест
     из графических редакторов. Слушаем на окне, но игнорируем набор в полях. */
  window.addEventListener('keydown', (e) => {
    const t = e.target;
    if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || '')) return;
    if (t && t.isContentEditable) return;
    if (document.getElementById('scene-picker') &&
        !document.getElementById('scene-picker').classList.contains('hidden')) return;
    /* Отмена последнего действия. Cmd+Z на маке, Ctrl+Z на остальных.
       Стоит ДО остальных разборов клавиш: иначе «z» ушло бы дальше по цепочке.
       Поля ввода отсеяны выше по этой же функции — в них работает своя отмена
       браузера, и перехватывать её нельзя. */
    if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === 'z' || e.key === 'Z' ||
        e.code === 'KeyZ')) {
      if (e.shiftKey) return;          // Shift+Z это «вернуть», а его мы не делаем
      if (typeof undoLast === 'function' && undoLast()) e.preventDefault();
      return;
    }
    if (e.code === 'Space') { _spaceDown = true; gw.style.cursor = 'grab'; return; }
    const step = e.shiftKey ? 120 : 40;   // с Shift шаг крупнее
    if (e.key === 'ArrowLeft')  { panByPixels(step, 0); e.preventDefault(); }
    else if (e.key === 'ArrowRight') { panByPixels(-step, 0); e.preventDefault(); }
    else if (e.key === 'ArrowUp')    { panByPixels(0, step); e.preventDefault(); }
    else if (e.key === 'ArrowDown')  { panByPixels(0, -step); e.preventDefault(); }
    else if (e.key === '+' || e.key === '=') { zoomStep(1 / 1.25); e.preventDefault(); }
    else if (e.key === '-' || e.key === '_') { zoomStep(1.25); e.preventDefault(); }
  });
  window.addEventListener('keyup', (e) => {
    if (e.code === 'Space') { _spaceDown = false; gw.style.cursor = ''; }
  });
  window.addEventListener('blur', () => { _spaceDown = false; gw.style.cursor = ''; });
}

let _spaceDown = false;

/* Приблизить или отдалить на шаг — от центра видимой области.
   Через неё работают и кнопки «+»/«−» над графиком (П53), и клавиши. */
function zoomStep(factor) {
  const gw = document.getElementById('graph-wrap');
  if (!gw) return;
  const r = gw.getBoundingClientRect();
  zoomBy(factor, r.width / 2, r.height / 2);
}

// Отменить и дебаунс, и текущий твин (при смене сцены/режима — чтобы отложенный
// переезд не сработал уже на ДРУГОЙ сцене).
function cancelRangeAnim() {
  if (_rangeSchedT != null) { clearTimeout(_rangeSchedT); _rangeSchedT = null; }
  if (_rangeAnimReq != null) { cancelAnimationFrame(_rangeAnimReq); _rangeAnimReq = null; }
  _rangeAnimating = false;
  _wantRangeAnim = false;
}

/* --- Троттл живого пересчёта (неравенство) ---------------------------------
   Тяжёлый recomputeInequality + полная пересборка SVG/панели на каждый микрошаг
   ползунка мигают. Троттл (ведущий + хвостовой, ~90 мс) обновляет картинку
   и числа СОГЛАСОВАННО, не чаще ~11 раз/с — плавно, без мигания. Это не «motion»,
   а ограничение частоты пересчёта, поэтому действует и при reduce-motion. */
function makeThrottle(interval) {
  let last = 0, tid = null, pending = null;
  return (fn) => {
    pending = fn;
    const now = Date.now();
    const wait = interval - (now - last);
    if (wait <= 0) { last = now; if (tid) { clearTimeout(tid); tid = null; } const f = pending; pending = null; f(); }
    else if (tid == null) {
      tid = setTimeout(() => { last = Date.now(); tid = null; const f = pending; pending = null; if (f) f(); }, wait);
    }
  };
}
const _ineqThrottle = makeThrottle(90);
function ineqRedraw() { _ineqThrottle(() => redrawAll()); }   // живой пересчёт неравенства — троттлом

// Переключение режима: рынок / издержки / КПВ.
function setMode(mode) {
  cancelRangeAnim();   // отложенный/идущий переезд осей прошлой сцены — отменить
  STATE.zoomLock = false;   // новая сцена показывает себя в своём масштабе
  STATE.mode = mode;
  STATE.roller = null;      // бегущая точка держалась за кривую прошлого режима
  /* Начальное положение ГАЛОЧКИ «только первая четверть»: экономика
     открывается в первой четверти, «Математика» и построение графиков — на
     полном плане. Дальше человек переключает её в меню плоскости, и она
     двигает только оси, сетку и границы. То, где существует экономическая
     кривая, задаёт isEconScene() (20-plane.js), а не эта строка. */
  STATE.firstQuad = isEconScene();
  const quadChk = document.getElementById('chk-quad');
  if (quadChk) quadChk.checked = STATE.firstQuad;
  /* Какие блоки ВНУТРИ карточки «Ввод функций» показывать в каждом режиме
     (отсутствующие id просто игнорируются). Сама карточка #sec-input видна
     всегда: панель во всех 41 сцене состоит из одних и тех же трёх карточек,
     и меняется только начинка первой. Из списка ушли 'sec-areas' и
     'sec-analysis' — этих блоков в разметке больше нет. */
  const groups = {
    market: ['sec-curves', 'sec-eq', 'sec-tax', 'sec-mono'],
    costs:  ['sec-costs'],
    ppf:    ['sec-ppf'],
    labor:  ['sec-curves', 'sec-labor'],
    inequality: ['sec-inequality'],
    consumer: ['sec-consumer'],
    macro: ['sec-macro'],
    math: ['sec-math'],
    graph: ['sec-graph'],
  };
  const all = new Set([].concat(...Object.values(groups)));
  all.forEach(id => { const e = document.getElementById(id); if (e) e.style.display = 'none'; });
  (groups[mode] || []).forEach(id => { const e = document.getElementById(id); if (e) e.style.display = ''; });
  applyScenarioVisibility();   // уточнить видимость интервенций/панелей по текущему сценарию
  // Рынок труда работает на общем списке кривых, поэтому при входе он обязан
  // получить спрос на труд и предложение труда. Раньше пресет ставился ТОЛЬКО
  // при первом входе, и сцена, открытая вторым заходом после монополии,
  // доставалась с чужими кривыми (спрос и MC): равновесия нет, площадей нет.
  // Теперь пресет восстанавливается всякий раз, когда нужной роли не хватает;
  // свои кривые пользователя при этом не трогаются.
  if (mode === 'labor') {
    if (!curveByRole('demand') || !curveByRole('supply')) {
      STATE.curves = []; curveCounter = 0;
      addCurve('100 - L'); if (STATE.curves[0]) setRole(STATE.curves[0], 'demand');
      addCurve('L');       if (STATE.curves[1]) setRole(STATE.curves[1], 'supply');
    }
    if (!STATE.laborVisited) {
      STATE.laborVisited = true;
      // По умолчанию для сцены включаем МРОТ — чтобы пульт сразу показал его ползунок
      // (Фаза 6). Дальше пользователь может снять галочку — ползунок уйдёт как обычно.
      STATE.laborMinOn = true;
      const chk = document.getElementById('chk-labmin'); if (chk) chk.checked = true;
      const lf = document.getElementById('labmin-field'); if (lf) lf.style.display = '';
      if (!(STATE.laborMinW > 0) && typeof setLaborMinFields === 'function') setLaborMinFields(65);  // выше равновесия (≈50) → связывающий
    }
  }
  // Режим неравенства: пометить первый вход и заполнить таблицу групп.
  if (mode === 'inequality') { STATE.ineqVisited = true; renderIneqGroupsTable(); }
  // При каждом переключении режима — выставлять характерный масштаб осей.
  // Ручные правки в полях «Оси» при смене режима намеренно сбрасываются.
  if (mode === 'math') { /* окно задаёт сам раздел (setMathWindow) */ }
  /* Чистый лист открывается на −10…10 по ОБЕИМ осям: все четыре четверти
     равноправно, как в Десмосе (решение владельца 19.08). Прежде здесь была
     первая четверть с тонкой каймой: x от −0,8 до 10. Тумблер первого
     квадранта в меню плоскости остаётся и работает как прежде. */
  else if (mode === 'graph') setRanges(10, 10, { symmetric: true });
  else if (mode === 'costs') setRanges(10, 50);
  else setRanges(100, 100);   // market / labor / ppf / inequality — стандартный масштаб 0..100
  // Секция «Оси» с полями «Q макс»/«P макс» уехала в меню гаечного ключа, где
  // группы называются просто «Ось X» и «Ось Y», а буквы задаются своими полями
  // названий осей. Подписи под режим здесь больше некуда ставить (Свх-4б).
  if (mode === 'consumer') applyConsumerTypeUI();   // показать поля под текущий тип предпочтений
  if (mode === 'macro') setMacroModel(STATE.macroModel);   // подписи осей и панель полей модели
  if (typeof updatePult === 'function') updatePult();   // вне рыночного режима пульт скрыт
  redrawAll();
}

// Видимость панелей по сценарию анализа рынка (Задачи 2–4). Без перерисовки.
// Интервенции и переключатель структуры рынка видны только в обычном сценарии;
// остальные сценарии показывают свою под-панель (взаимоисключение).
function applyScenarioVisibility() {
  const s = STATE.scenario, inMarket = (STATE.mode === 'market');
  const show = (id, on) => { const e = document.getElementById(id); if (e) e.style.display = on ? '' : 'none'; };
  show('scn-pane-elast', inMarket && s === 'elasticity');
  show('scn-pane-ext',   inMarket && s === 'externality');
  show('scn-pane-open',  inMarket && s === 'openecon');
  show('sec-tax',  inMarket && s === 'none');
  show('sec-mono', inMarket && s === 'none');
  /* ⚠️ ОБЩЕСТВЕННЫЕ КРИВЫЕ ПРЯЧУТСЯ ЗДЕСЬ, А НЕ В ОБРАБОТЧИКЕ ЩЕЛЧКА.
     Блок MSB / MSC живёт во «Вводе функций», и раньше его видимость ставил
     только `setScenario`. Смена модели меняет STATE.scenario напрямую и зовёт
     не его, а эту функцию — блок оставался на экране: замер 24.08 показывал
     два чужих поля в монополии и на рынке труда после захода во «Внешние
     эффекты». То же семейство, что и прежняя утечка параметров между сценами:
     состояние приводится к экрану в ОДНОМ месте, иначе всякий новый путь
     входа в сцену обязан помнить про каждый блок по отдельности. */
  show('social-curves', inMarket && s === 'externality');
  [['scn-none', 'none'], ['scn-elast', 'elasticity'],
   ['scn-ext', 'externality'], ['scn-open', 'openecon']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.classList.toggle('active', s === v); });
  // Карточка общего списка кривых живёт только там, где сцена его рисует.
  if (typeof syncCurveListVisibility === 'function') syncCurveListVisibility();
}

// Переключение сценария анализа рынка. Сценарии — конкурентный контекст: если был
// монополист, возвращаем конкуренцию (как монополия выключает интервенции).
function setScenario(s) {
  STATE.scenario = s;
  // Общественные кривые сюжета внешних эффектов живут во «Вводе функций»:
  // формулы готовятся заранее, а показывает блок applyScenarioVisibility ниже.
  if (s === 'externality') { recompileSocial(); syncSocialFields(); }
  if (s !== 'none' && STATE.market === 'monopoly') {
    STATE.market = 'comp';
    const mh = document.getElementById('mono-hint'); if (mh) mh.style.display = 'none';
    applyMonoVisibility();   // спрятать под-режим монополии и его панели (market теперь comp)
  }
  applyScenarioVisibility();
  redrawAll();
}

