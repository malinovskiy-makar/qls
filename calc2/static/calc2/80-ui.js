// Панель управления: элементы, подсказки формата формулы.
/* ---------------------------------------------------------------------
   БЛОК UI. Элементы управления панели и их привязка к логике.
   --------------------------------------------------------------------- */

// Сообщение об ошибке формулы (понятно пользователю, без падения страницы).
function showError(msg) {
  const box = document.getElementById('curve-error');
  box.textContent = msg; box.style.display = 'block';
}
function hideError() {
  document.getElementById('curve-error').style.display = 'none';
}

let curveCounter = 0;   // сквозной счётчик id кривых

/* ФОРМУ ЗАПИСИ ОПРЕДЕЛЯЕТ САМ РАЗБОР (решение владельца 22.08).
   Переключателя «Вводить P(Q) / Вводить Q(P)» больше нет. Правило простое и
   однозначное: формула, в которой стоит цена P и НЕТ количества Q, — это
   «объём от цены», Q = f(P); всё остальное — канон движка P = f(Q).

   Почему именно так, а не «угадываем по смыслу»: спрос пишут и «100 - Q»,
   и «100 - 2*P», и различить их можно ровно по одной вещи — какой буквой
   названа переменная. Спорный случай, где есть ОБЕ буквы («P - Q»), уходит
   в P = f(Q): это канон движка, и ошибка в понятную сторону. Формула без
   букв вовсе («20», предельные издержки) — тоже канон.

   Внутренние вызовы движка (пресеты сцен, ensureMonopolyCurves) формулу с
   одинокой P не пишут, поэтому для них ничего не меняется. */
function curveSrcForm(expr) {
  /* ⚠️ ФОРМУ ЧИТАЕМ ПО ПОДГОТОВЛЕННОЙ ЗАПИСИ, А НЕ ПО СЫРОЙ СТРОКЕ.
     Соседи буквы решают всё: правила ниже требуют, чтобы слева от P или Q
     стоял символ, которым имя продолжаться не может. В записи «100-2P» слева
     от P стоит цифра, и до правки 24.08 буква P не находилась вовсе — формула
     уезжала в P = f(Q), где P посторонняя, и на графике выходила горизонталь
     на 98 (замер Фазы 0), причём молча.
     prepExpr раскрывает и LaTeX (поле хранит набранную запись), и неявное
     умножение — «100-2P» приходит сюда уже как «100-2*P». Одно правило про
     «цифра слева — это множитель» живёт в одном месте (60-overlays.js). */
  let t = String(expr || '');
  try { if (typeof prepExpr === 'function') t = prepExpr(t); } catch (e) { /* разбор не удался — судим по сырой строке */ }
  const has = (re) => re.test(t);
  const hasQ = has(/(^|[^A-Za-z0-9_])[Qq]([^A-Za-z0-9_]|$)/);
  const hasP = has(/(^|[^A-Za-z0-9_])[Pp]([^A-Za-z0-9_]|$)/);
  return (hasP && !hasQ) ? 'QP' : 'PQ';
}

// Добавить кривую по формуле. form: 'PQ' — P = f(Q) (канон движка),
// 'QP' — Q = f(P) (приводится к канону в buildCurveFromQP).
// Форму не передали — определяем сами по формуле (curveSrcForm).
function addCurve(expr, form) {
  expr = (expr || '').trim();
  if (!expr) { showError('Введите формулу, например 100 - Q'); return; }
  if (!form) form = curveSrcForm(expr);
  if (form === 'QP') {
    const built = buildCurveFromQP(expr);
    if (built.error) { showError('Не понял формулу Q(P): ' + built.error); return; }
    hideError();
    curveCounter++;
    STATE.curves.push({
      id: curveCounter, expr, compiled: null,
      color: nextColor(), role: null, visible: true,
      linear: built.linear, fn: built.fn,
      srcForm: 'QP', srcExpr: expr, srcCompiled: built.srcCompiled, srcLinear: built.srcLinear,
    });
    renderCurveList();
    redrawAll();
    return;
  }
  const { compiled, error } = compileFormula(expr);
  if (error) { showError('Не понял формулу: ' + error); return; }
  hideError();
  curveCounter++;
  STATE.curves.push({
    id: curveCounter, expr, compiled,
    color: nextColor(), role: null, visible: true,
    linear: detectLinear(compiled),   // {a, b} для прямых, иначе null
    srcForm: 'PQ',
  });
  renderCurveList();
  redrawAll();
}

/* ПУСТАЯ СТРОКА ПО КНОПКЕ (решение владельца 22.08). Кнопка «Добавить кривую»
   заводит не кривую, а ПОЛЕ: строка появляется пустой, и человек печатает
   формулу прямо в ней — тем же полем с набором формул, что и у готовых кривых.
   Роль не спрашивается: добавленная кривая всегда обычная и в расчёты модели
   не входит (у неё нет роли, а равновесие и излишки считаются по ролям).
   Пока формула не набрана, кривой на холсте нет — drawCurves пропускает
   строки с пустой записью. */
function addEmptyCurve() {
  hideError();
  curveCounter++;
  STATE.curves.push({
    id: curveCounter, expr: '', compiled: null,
    color: nextColor(), role: null, visible: true,
    linear: null, srcForm: 'PQ',
  });
  renderCurveList();
  redrawAll();
  // Курсор сразу в новое поле: кнопку нажали, чтобы печатать.
  const inp = document.getElementById('curve-expr-' + curveCounter);
  if (inp) { const mf = inp._mf; if (mf && mf.focusField) mf.focusField(); else inp.focus(); }
}

/* Правка формулы уже добавленной кривой. Пересобираем её внутренности на
   месте, сохраняя id, цвет, роль, своё имя и видимость: раньше, чтобы
   поправить опечатку, кривую приходилось удалять и заводить заново, теряя
   все настройки. Возвращает текст ошибки или null, если всё хорошо. */
function updateCurveExpr(curve, expr) {
  expr = (expr || '').trim();
  if (!expr) return 'пустая формула';
  if (curve.kind === 'vertical') return 'у вертикальной линии формулы нет';
  // Форму записи пересматриваем на КАЖДОЙ правке: переключателя нет, и
  // «100 - Q», переписанное в «100 - 2*P», обязано стать «объёмом от цены».
  curve.srcForm = curveSrcForm(expr);
  if (curve.srcForm === 'QP') {
    const built = buildCurveFromQP(expr);
    if (built.error) return built.error;
    curve.expr = expr; curve.compiled = null;
    curve.linear = built.linear; curve.fn = built.fn;
    curve.srcExpr = expr; curve.srcCompiled = built.srcCompiled; curve.srcLinear = built.srcLinear;
  } else {
    const { compiled, error } = compileFormula(expr);
    if (error) return error;
    curve.expr = expr; curve.compiled = compiled;
    curve.linear = detectLinear(compiled);
    curve.fn = null;   // синтетическая функция (S + t и т.п.) больше не действует
  }
  /* ⚠️ НОВАЯ ФОРМУЛА — НОВАЯ ТОЧКА ОТСЧЁТА СДВИГА (решение владельца 24.08).
     Сдвиг это смещение ОТ введённой формулы, поэтому переписали формулу —
     сдвиг ноль, ручка посередине дорожки. Точку отсчёта заводит заново
     `curveShiftBase` (88-params.js) при первой же сборке чипа.
     Без этого замер 24.08 давал «Сдвиг D = −50» сразу после набора «100-2*P»:
     свободный член сменился, а отсчёт остался от прежней формулы. */
  delete curve.shiftBase;
  return null;
}

// Назначить роль кривой. D и S — единственны: при назначении снимаем
// ту же роль с других кривых.
function setRole(curve, role) {
  if (!role) {
    curve.role = null;
  } else {
    STATE.curves.forEach(c => { if (c !== curve && c.role === role) c.role = null; });
    curve.role = role;
    // Перекрашиваем по роли: спрос — синий, предложение — красный, MC — бирюзовый.
    // Свой цвет из пикера (Фаза 2) сильнее роли: выбор пользователя не затираем.
    const rc = roleColor(role);
    if (rc && !curve.colorCustom) curve.color = rc;
  }
  renderCurveList();
  redrawAll();
}

// Перерисовать список кривых в панели.
/* ── КАРТОЧКА ФУНКЦИИ (редизайн 10.2026, фаза 5б; README макета, 6.1) ──
   Верхний ряд: кружок цвета → окно «Цвет кривой», обозначение (D, S, MC, своя
   подпись), имя роли, глаз «Скрыть кривую» и «…» с меню. Ниже поле формулы с
   приставкой «P =» / «Q =» и кнопкой клавиатуры в правом конце, ошибка под
   полем, под карточкой — её ползунки (сдвиг и буквы, 88-params.js).

   ⚠️ ПОРЯДОК УЗЛОВ В РАЗМЕТКЕ НЕ МЕНЯЕТСЯ ЗРЯ. Кнопка «…» (бывший шеврон) и
   крестик по-прежнему идут в строке друг за другом, теперь крестик живёт в
   меню «…». Прибор паритета (calc2/tests/redesign) узнаёт органы по ближнему
   id и порядку одинаковых узлов: лишняя перестановка разорвала бы сверку со
   старым экраном, ничего не дав человеку.
   Галочка видимости стала глазом (пункт (ж) закрытого списка). */
const ROLE_HUMAN = { demand: 'Спрос', supply: 'Предложение', mc: 'Предельные издержки',
                     tc: 'Общие издержки', atc: 'Средние общие издержки' };
function curveHumanName(c) {
  if (c.kind === 'sum') return c.role === 'supply' ? 'Суммарное предложение' : 'Суммарный спрос';
  if (c.sumGroup) return (c.role === 'supply' ? 'Предложение' : 'Спрос') + ' группы';
  if (c.role && ROLE_HUMAN[c.role]) return ROLE_HUMAN[c.role];
  return 'Своя функция';
}
// Приставка поля: буква вертикальной оси для P(Q), горизонтальной для Q(P).
function curvePrefix(c) {
  const ax = (name, dflt) => { const m = /^[A-Za-z]+/.exec(String(name || '')); return m ? m[0] : dflt; };
  return c.srcForm === 'QP' ? ax(STATE.axisXDefault, 'Q') + ' =' : ax(STATE.axisYDefault, 'P') + ' =';
}
/* Стартовые записи кривых модели — для пункта «Вернуть стартовую запись».
   Пишутся при входе в модель сразу после её маршрута (84-picker.js), до
   восстановления памяти: это запись, с которой модель открывается всегда. */
const MODEL_START_CURVES = {};
function rememberStartCurves(key) {
  MODEL_START_CURVES[key] = STATE.curves.map(c => ({
    id: c.id, role: c.role || null, kind: c.kind || '',
    expr: c.srcForm === 'QP' ? (c.srcExpr || c.expr) : c.expr }));
}
function startExprOf(curve) {
  const list = MODEL_START_CURVES[STATE.sceneKey] || [];
  const hit = (curve.role && list.find(x => x.role === curve.role && !x.kind)) || list.find(x => x.id === curve.id && !x.kind);
  return hit ? hit.expr : null;
}
function curveIsPiecewise(c) {
  return !!(c && typeof pwParse === 'function' && pwParse(c.srcForm === 'QP' ? (c.srcExpr || c.expr) : c.expr, 'Q'));
}
const ICON_EYE = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"'
  + ' stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/>'
  + '<circle cx="12" cy="12" r="2.8"/></svg>';
const ICON_EYE_OFF = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"'
  + ' stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18"/><path d="M10.6 5.6A10.6 10.6 0 0 1 12 5.5'
  + 'c6.4 0 10 6.5 10 6.5a17 17 0 0 1-3.2 3.9M6.4 6.5C3.6 8.3 2 12 2 12s3.6 6.5 10 6.5c1.6 0 3-.4 4.2-1"/>'
  + '<path d="M9.9 9.9a2.8 2.8 0 0 0 4 4"/></svg>';
const ICON_DOTS = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><circle cx="5.5" cy="12" r="1.6"/>'
  + '<circle cx="12" cy="12" r="1.6"/><circle cx="18.5" cy="12" r="1.6"/></svg>';

function renderCurveList() {
  const list = document.getElementById('curve-list');
  // Ползунки кривых живут под карточками: перед пересборкой списка они уходят
  // домой в «Параметры», иначе пропали бы вместе со старыми карточками.
  if (typeof parkCurveSliders === 'function') parkCurveSliders();
  if (typeof closeFcMenu === 'function') closeFcMenu();
  list.innerHTML = '';
  if (STATE.curves.length === 0) {
    list.innerHTML = '<div class="muted">Пока нет кривых.</div>';
    return;
  }
  STATE.curves.forEach(curve => {
    const row = document.createElement('div');
    row.className = 'curve-row fc-card';
    row.dataset.cid = curve.id;
    if (!curve.visible) row.classList.add('is-hidden');

    // Верхний ряд: цвет, обозначение, имя, глаз, «…».
    const top = document.createElement('div');
    top.className = 'crow-top';

    // Цвет кривой (Фаза 2): окно меняет цвет ТОЛЬКО у этого экземпляра.
    // ВАЖНО: здесь нельзя вызывать renderCurveList(): «Свой цвет» держит
    // системное окно выбора на input внутри окна «Цвет кривой».
    const sw = makeColorPicker(curve.color, (hex) => {
      if (hex == null) { delete curve.colorCustom; curve.color = roleColor(curve.role) || curve.color; }
      else { curve.color = hex; curve.colorCustom = true; }
      redrawAll();
      return curve.color;
    }, 'Цвет кривой: ' + curveHumanName(curve), {
      title: 'Цвет кривой «' + curveHumanName(curve) + '»',
      dflt: () => roleColor(curve.role) || null,
    });

    /* ОБОЗНАЧЕНИЕ (Фаза 3 и макет 6.1): у кривой сложения короткое D₁, S₂
       (тем же обозначением она подписана на холсте), у остальных D, S, MC или
       своя подпись из меню «…». Набирается формулой. */
    const rowTag = (typeof sumTagOf === 'function' && typeof sumSceneOn === 'function' && sumSceneOn())
      ? sumTagOf(curve) : null;
    const nm = document.createElement('span');
    nm.className = 'curve-name fc-notation';
    if (rowTag && !(curve.label || '').trim()) {
      nm.classList.add('crow-tag');
      nm.style.color = curve.color;
      const tex = rowTag.replace(/_(\d)/, '_{$1}');
      if (typeof katexInto === 'function') katexInto(nm, tex);
      else nm.textContent = rowTag.replace('_', '');
    } else {
      paintNotation(nm, curveShortName(curve));   // «D», «MC» — формулой, своё имя — текстом
    }
    nm.setAttribute('data-tip', tipExpr(curve.expr));   // под обозначением — сама формула

    const human = document.createElement('span');
    human.className = 'fc-name';
    human.textContent = curveHumanName(curve);

    // Бейдж формы записи (Фаза 1б): видно, что кривая введена как «объём от цены».
    let badge = null;
    if (curve.srcForm === 'QP') {
      badge = document.createElement('span');
      badge.className = 'form-badge'; badge.textContent = 'Q(P)';
      const can = curve.linear
        ? ('$P = ' + fmtLinear(curve.linear.a, curve.linear.b) + '$')
        : '$P = f(Q)$ считается численно';
      badge.setAttribute('data-tip', 'Введено как $Q(P)$, в расчётах ' + can);
    }

    // Глаз (пункт (ж)): тот же признак visible, что был у галочки.
    const eye = document.createElement('button');
    eye.type = 'button'; eye.className = 'fc-eye fc-ico';
    const paintEye = () => {
      eye.innerHTML = curve.visible ? ICON_EYE : ICON_EYE_OFF;
      eye.setAttribute('aria-pressed', curve.visible ? 'false' : 'true');
      const t = curve.visible ? 'Скрыть кривую' : 'Показать кривую';
      eye.setAttribute('aria-label', t + ' ' + curveShortName(curve));
      eye.setAttribute('data-tip', t);
    };
    paintEye();
    eye.addEventListener('click', () => {
      pushUndo(curve.visible ? 'Скрыть кривую' : 'Показать кривую');
      curve.visible = !curve.visible;
      renderCurveList(); redrawAll();
    });

    /* ⚠️ КРЕСТИК ДЕЛАЕТ РАЗНОЕ У РАЗНЫХ КРИВЫХ (решение владельца 22.08).
       У добавленной кривой (роли нет) он удаляет, у штатной кривой модели
       гасит: удалённый спрос оставил бы ученика с пустой моделью. Теперь это
       пункт меню «…»: «Удалить функцию» или «Убрать с графика». */
    const staff = !!curve.role;
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn-icon fc-mi' + (staff ? '' : ' fc-danger');
    del.textContent = staff ? 'Убрать с графика' : 'Удалить функцию';
    del.setAttribute('data-tip',
      staff ? 'Убрать кривую с графика (вернуть глазом на карточке)' : 'Удалить кривую');
    del.addEventListener('click', () => {
      pushUndo(staff ? 'Убрать кривую' : 'Удалить функцию');
      closeFcMenu();
      if (staff) { curve.visible = false; }
      else { STATE.curves = STATE.curves.filter(c => c.id !== curve.id); }
      renderCurveList();
      redrawAll();
    });

    // «Роль кривой»: обычная / спрос / предложение / MC / TC / ATC (О9).
    const sel = document.createElement('select');
    sel.className = 'role-sel';
    sel.setAttribute('aria-label', 'Роль кривой');
    [['', 'Обычная кривая'], ['demand', 'D, спрос'], ['supply', 'S, предложение'],
     ['mc', 'MC, предельные издержки'], ['tc', 'TC, суммарные затраты'], ['atc', 'ATC, средние затраты']]
      .forEach(([v, t]) => {
        const o = document.createElement('option'); o.value = v; o.textContent = t;
        sel.appendChild(o);
      });
    sel.value = curve.role || '';
    sel.addEventListener('change', () => { pushUndo('Роль кривой'); setRole(curve, sel.value); });

    // Формула кривой правится прямо здесь; неверная остаётся черновиком в поле.
    let fInp = null;
    /* ⚠️ У СУММАРНОЙ КРИВОЙ ПОЛЯ ФОРМУЛЫ НЕТ: её запись считается из формул
       групп на каждой перерисовке (sumRebuild). */
    if (curve.kind !== 'vertical' && curve.kind !== 'sum') {
      fInp = document.createElement('input');
      fInp.type = 'text'; fInp.className = 'curve-expr-inp';
      fInp.value = curve.srcForm === 'QP' ? (curve.srcExpr || curve.expr) : curve.expr;
      fInp.placeholder = curve.expr ? (curve.srcForm === 'QP' ? 'Q = f(P)' : 'P = f(Q)')
                                    : 'Например: 100 - Q';
      fInp.setAttribute('aria-label', 'Формула: ' + curveHumanName(curve));
      fInp.addEventListener('input', () => {
        pushUndo();
        const raw = String(fInp.value || '').trim();
        // Пустое поле у своей функции законно: кривой просто нет (макет 6.1).
        const err = (!raw && !staff) ? null : updateCurveExpr(curve, fInp.value);
        if (!raw && !staff) { curve.expr = ''; curve.compiled = null; curve.linear = null; }
        fInp.classList.toggle('bad', !!err);
        fInp.setAttribute('aria-invalid', err ? 'true' : 'false');
        if (typeof fieldProblem === 'function') {
          fieldProblem(fInp, err ? (err.charAt(0).toUpperCase() + err.slice(1) + '. График держит последнюю верную запись.') : '');
        }
        if (!err) {
          paintNotation(nm, curveShortName(curve));
          redrawAll();
          if (typeof updatePult === 'function') updatePult();
        }
      });
    }

    // «Подпись на графике» (Фаза 1): своё имя идёт на холст, в карточку и в ползунок.
    const nameInp = document.createElement('input');
    nameInp.type = 'text'; nameInp.className = 'curve-label-inp';
    nameInp.value = curve.label || '';
    nameInp.placeholder = curveShortName(Object.assign({}, curve, { label: '' }));
    nameInp.setAttribute('aria-label', 'Подпись на графике');
    nameInp.addEventListener('input', () => {
      curve.label = nameInp.value;
      paintNotation(nm, curveShortName(curve));
      redrawAll();
      if (typeof updatePult === 'function') updatePult();
    });

    /* Меню «…» (макет, раздел 10): подпись на графике, куски, стартовая
       запись, роль, удаление. Узел меню живёт в строке и открывается поверх
       колонки, как всплывающее окно. */
    const more = document.createElement('div');
    more.className = 'crow-more fc-menu';
    more.setAttribute('role', 'dialog');
    more.setAttribute('aria-label', 'Настройки функции ' + curveShortName(curve));
    const lab = document.createElement('label');
    lab.className = 'fc-menu-lab'; lab.textContent = 'Подпись на графике';
    const note = document.createElement('div');
    note.className = 'fc-menu-note'; note.textContent = 'Индекс через «_»: D_1 → D₁. Пусто: обозначение по умолчанию.';
    more.append(lab, nameInp, note);
    const items = document.createElement('div');
    items.className = 'fc-menu-items';
    const mi = (text, fn, cls) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'fc-mi' + (cls ? ' ' + cls : '');
      b.textContent = text;
      b.addEventListener('click', () => { closeFcMenu(); fn(); });
      items.appendChild(b);
      return b;
    };
    if (fInp) {
      if (curveIsPiecewise(curve)) {
        mi('Изменить куски', () => openPiecewise(fInp, pwVarForField(fInp, curvePrefix(curve)[0] === 'Q' ? 'P' : 'Q')));
        mi('Одной формулой', () => curveToSingleFormula(curve, fInp));
      } else {
        mi('Задать кусками', () => openPiecewise(fInp, pwVarForField(fInp, curve.srcForm === 'QP' ? 'P' : 'Q'), { split: true }));
      }
    }
    if (staff && fInp) {
      mi('Вернуть стартовую запись', () => {
        const ex = startExprOf(curve);
        if (ex == null) { toast('Стартовой записи у этой кривой нет'); return; }
        pushUndo('Вернуть стартовую запись');
        setFieldValue(fInp, ex);
      });
    }
    const roleBox = document.createElement('div');
    roleBox.className = 'fc-menu-role';
    const rl = document.createElement('div');
    rl.className = 'fc-menu-lab'; rl.textContent = 'Роль кривой';
    roleBox.append(rl, sel);
    more.append(items, roleBox, del);

    const gear = document.createElement('button');
    gear.type = 'button'; gear.className = 'btn-icon crow-gear fc-ico';
    gear.setAttribute('data-tip', 'Подпись на графике, стартовая запись, удаление');
    gear.setAttribute('aria-label', 'Настройки функции ' + curveShortName(curve));
    gear.setAttribute('aria-haspopup', 'dialog');
    gear.setAttribute('aria-expanded', 'false');
    gear.innerHTML = ICON_DOTS;
    gear.addEventListener('click', (e) => {
      e.stopPropagation();
      if (more.classList.contains('open')) { closeFcMenu(); return; }
      openFcMenu(gear, more);
    });

    top.append(sw, nm, human);
    if (badge) top.append(badge);
    top.append(eye, gear);

    /* Строка суммарной кривой: поля у неё нет и быть не может, на его месте
       прямая надпись, а в подсказке — запись, по которой кривая считается. */
    let autoLine = null;
    if (curve.kind === 'sum') {
      autoLine = document.createElement('div');
      autoLine.className = 'crow-auto';
      autoLine.textContent = 'считается по группам, правке не подлежит';
      autoLine.setAttribute('data-tip', curve.expr
        ? ('Сейчас это ' + tipExpr(curve.expr))
        : 'Ни одна группа ещё не задана');
    }

    const sliders = document.createElement('div');
    sliders.className = 'crow-sliders';
    if (fInp) {
      const fLine = document.createElement('div');
      fLine.className = 'crow-formula';
      const pre = document.createElement('span');
      pre.className = 'fc-prefix';
      pre.setAttribute('aria-hidden', 'true');
      if (typeof katexInto === 'function') katexInto(pre, curvePrefix(curve).replace(' =', '\\,='));
      else pre.textContent = curvePrefix(curve);
      fLine.append(pre, fInp);
      row.append(top, fLine, more, sliders);
      fInp.id = fInp.id || ('curve-expr-' + curve.id);
    } else if (autoLine) {
      row.append(top, autoLine, more, sliders);
    } else {
      row.append(top, more, sliders);
    }
    list.appendChild(row);
    /* Оснащаем поле формулы ПОСЛЕ вставки строки в разметку: до этого
       getElementById его не найдёт, и оснащение молча не срабатывало. */
    if (fInp) equipFormulaField(fInp.id, () => (curve.srcForm === 'QP' ? 'QP' : 'PQ'));
  });
  if (typeof flushMathfields === 'function') flushMathfields();
  if (typeof updatePult === 'function') updatePult();   // пересобрать ползунки кривых
  if (typeof placeCurveSliders === 'function') placeCurveSliders();
}

/* «Одной формулой»: куски убираются, остаётся формула первого куска;
   тост с «Вернуть» (макет 6.6). Отдельный шаг истории. */
function curveToSingleFormula(curve, fInp) {
  const was = fInp.value;
  const parsed = pwParse(was, 'Q');
  if (!parsed || !parsed.rows.length) return;
  pushUndo('Одной формулой');
  setFieldValue(fInp, pwPrefixOf(was) + parsed.rows[0].f);
  toast('Куски убраны, осталась формула первого куска', {
    action: 'Вернуть', fn: () => { pushUndo('Вернуть куски'); setFieldValue(fInp, was); } });
}

/* ---------------------------------------------------------------------
   ФАЗА 1а. ПОДСКАЗКА ФОРМАТА ФОРМУЛЫ — переиспользуемый компонент.
   Кнопка «?» рядом с полем раскрывает карточку с 4 примерами синтаксиса
   Math.js. Пример кликабелен — подставляется прямо в поле. Один и тот же
   компонент вешается на любое поле формулы (kind задаёт набор примеров).
   --------------------------------------------------------------------- */
const FORMULA_EXAMPLES = {
  // Рыночная кривая P = f(Q) — канон движка.
  PQ: { title: 'Цена от количества: P = f(Q)', items: [
    ['100 - 2*Q',                    'линейная'],
    ['sqrt(100 - Q^2)',              'с корнем, даёт дугу'],
    ['120 / (Q + 1)',                'дробная, даёт гиперболу'],
    ['Q < 40 ? 100 - Q : 80 - 0.5*Q', 'кусочная: условие ? … : …'],
  ] },
  // Ввод «объём от цены» (Фаза 1б) — приводится к канону автоматически.
  QP: { title: 'Количество от цены: Q = f(P)', items: [
    ['100 - 2*P',        'линейная'],
    ['sqrt(400 - P^2)',  'с корнем, даёт дугу'],
    ['500 / (P + 1)',    'дробная, даёт гиперболу'],
    ['P < 30 ? 90 - P : 120 - 2*P', 'кусочная: условие ? … : …'],
  ] },
  // Примеры под конкретную роль: их показывает справка, когда в поле «Что
  // добавляем» выбрана эта роль. Общая PQ-подсказка про запись спроса рядом
  // с предельными издержками только сбивала бы.
  DEMAND: { title: 'Спрос: цена от количества P = f(Q)', items: [
    ['100 - Q',                       'линейный'],
    ['100 - 2*Q',                     'круче: цена падает быстрее'],
    ['200 / (Q + 1)',                 'с постоянной эластичностью по виду'],
    ['Q < 40 ? 100 - Q : 80 - 0.5*Q', 'кусочный: сегменты покупателей'],
  ] },
  SUPPLY: { title: 'Предложение: цена от количества P = f(Q)', items: [
    ['Q',            'линейное из начала координат'],
    ['20 + 0.5*Q',   'с порогом: дешевле 20 никто не продаёт'],
    ['0.02*Q^2',     'растущие предельные издержки'],
    ['Q < 30 ? 10 : 10 + 2*(Q - 30)', 'кусочное: мощности кончились'],
  ] },
  MC: { title: 'Предельные издержки MC(Q)', items: [
    ['20',           'постоянные'],
    ['2*Q',          'линейно растущие'],
    ['0.03*Q^2 + 5', 'растущие с ускорением'],
    ['40 - 0.3*Q',   'убывающие (эффект масштаба)'],
  ] },
  ATC: { title: 'Средние затраты ATC(Q)', items: [
    ['Q - 10 + 100/Q', 'U-образные'],
    ['500/Q + 4',      'падающие: большие постоянные издержки'],
    ['20',             'постоянные'],
  ] },
  // Суммарные затраты TC(Q) в режиме издержек.
  TC: { title: 'Суммарные затраты TC(Q)', items: [
    ['Q^3 - 6*Q^2 + 15*Q + 18', 'кубическая, средние выходят U-образными'],
    ['2*Q^2 + 10*Q + 50',       'квадратичная'],
    ['30 + 8*Q',                'линейная, предельные издержки постоянны'],
    ['20 + 4*Q*sqrt(Q)',        'с корнем'],
  ] },
  // Граница производственных возможностей Y = f(X).
  // Производственная функция от труда Q = f(L) — режим «Фирма → Производство».
  PROD: { title: 'Выпуск от труда Q = f(L)', items: [
    ['30*L^2 - L^3',  'классическая S-образная'],
    ['20*L - 0.5*L^2', 'квадратичная'],
    ['12*sqrt(L)',    'убывающая отдача сразу'],
    ['10*L',          'постоянная отдача'],
  ] },
  // Производственная функция двух факторов Q(L, K) — изокванты.
  ISO: { title: 'Выпуск от факторов Q(L, K)', items: [
    ['L^0.5 * K^0.5',   'Кобб-Дуглас (пост. отдача)'],
    ['L^0.3 * K^0.7',   'капиталоёмкая'],
    ['2*L + K',         'совершенные субституты'],
    ['min(L/1, K/2)',   'жёсткая пропорция (Леонтьев)'],
  ] },
  // Функция полезности U(x, y) — своя формула в режиме «Потребитель».
  UTIL: { title: 'Полезность U(x, y)', items: [
    ['x^0.5 * y^0.5',   'Кобб-Дуглас'],
    ['2*x + y',         'совершенные субституты'],
    ['min(x/1, y/2)',   'совершенные комплементы'],
    ['x + 2*sqrt(y)',   'квазилинейные'],
  ] },
  // Раздел «Математика» (Фаза 7): произвольная функция одной переменной.
  MATHF: { title: 'Функция y = f(x)', items: [
    ['x^2',                    'парабола'],
    ['x^3 - 3*x',              'кубическая: максимум, минимум, перегиб'],
    ['sqrt(abs(x))',           'корень из модуля'],
    ['x < 0 ? -x : x^2',       'кусочная: условие ? … : …'],
  ] },
  MATHY: { title: 'Кривая как x = g(y)', items: [
    ['10 - y^2/10', 'парабола, лежащая на боку'],
    ['sqrt(100 - y^2)', 'четверть окружности'],
    ['4 + 2*y',     'прямая'],
    ['20/(y + 1)',  'гипербола'],
  ] },
  MATHAB: { title: 'Целевая функция F(a, b)', items: [
    ['a^0.5 * b^0.5', 'корень из произведения'],
    ['a^0.3 * b^0.7', 'с перекосом в b'],
    ['2*a + b',       'линейная'],
    ['min(a/1, b/2)', 'жёсткая пропорция'],
  ] },
  PPF: { title: 'Граница возможностей Y = f(X)', items: [
    ['100 - X',          'линейная, альтернативные издержки постоянны'],
    ['sqrt(10000 - X^2)', 'дуга, альтернативные издержки растут'],
    ['100 - 0.01*X^2',   'парабола, альтернативные издержки растут'],
    ['100 - 10*sqrt(X)', 'выпуклая, альтернативные издержки убывают'],
  ] },
  // Макромодели: по горизонтали всегда выпуск, ставка или количество денег,
  // по вертикали — уровень цен, ставка процента или курс. Запись одна и та же.
  MACRO: { title: 'Кривая макромодели', items: [
    ['120 - 0.6*Y',  'убывающая (AD, спрос на деньги)'],
    ['10 + 0.5*Y',   'растущая (SRAS, предложение сбережений)'],
    ['a - 0.6*Y',    'с буквой: a получит ползунок'],
    ['200 / (Y + 1)', 'нелинейная'],
  ] },
};
const FORMULA_FOOT = 'Умножение ставится звёздочкой (2*Q), степень знаком ^. Дробное значение пишется через точку: 0.5.';

/* Палитра операций: всё, что понимает движок, разложено по кучкам и
   подставляется в строку ПО КУСОЧКАМ, а не заменяет её целиком. Это главный
   вход для новичка, который не знает, как вообще набирать формулы.
   ins — что вставить; caret — на сколько символов увести курсор назад от
   конца вставки, чтобы он оказался внутри скобок. */
const FORMULA_PALETTE = [
  ['Арифметика', [
    ['+', 'сложить'], ['-', 'вычесть'], ['*', 'умножить'], ['/', 'разделить'],
    ['( )', 'скобки', '()', 1],
  ]],
  ['Степени и корни', [
    ['^2', 'квадрат'], ['^3', 'куб'], ['^0.5', 'корень степенью'],
    ['sqrt( )', 'квадратный корень', 'sqrt()', 1],
    ['nthRoot( , 3)', 'корень любой степени', 'nthRoot(, 3)', 4],
  ]],
  ['Функции', [
    ['abs( )', 'модуль', 'abs()', 1],
    ['min( , )', 'наименьшее из', 'min(, )', 3],
    ['max( , )', 'наибольшее из', 'max(, )', 3],
    ['exp( )', 'экспонента', 'exp()', 1],
    ['log( )', 'натуральный логарифм', 'log()', 1],
    ['log( , 10)', 'логарифм по основанию', 'log(, 10)', 5],
    ['round( )', 'округлить', 'round()', 1],
    ['floor( )', 'округлить вниз', 'floor()', 1],
  ]],
  ['Тригонометрия', [
    ['sin( )', 'синус', 'sin()', 1], ['cos( )', 'косинус', 'cos()', 1],
    ['tan( )', 'тангенс', 'tan()', 1], ['pi', 'число пи'], ['e', 'число e'],
  ]],
  ['Кусочная функция', [
    ['Q < 40 ? … : …', 'один излом', 'Q < 40 ? 100 - Q : 80 - 0.5*Q', 0],
    ['? :', 'условие: если ? то : иначе', ' ?  : ', 4],
    ['<', 'меньше'], ['<=', 'меньше или равно'],
    ['>', 'больше'], ['>=', 'больше или равно'],
  ]],
];

