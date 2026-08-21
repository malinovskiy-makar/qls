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
  const t = String(expr || '');
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
function renderCurveList() {
  const list = document.getElementById('curve-list');
  list.innerHTML = '';
  if (STATE.curves.length === 0) {
    list.innerHTML = '<div class="muted">Пока нет кривых.</div>';
    return;
  }
  STATE.curves.forEach(curve => {
    const row = document.createElement('div');
    row.className = 'curve-row';

    // Верхняя строка: галочка видимости, цвет, формула, удаление.
    const top = document.createElement('div');
    top.className = 'crow-top';

    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = curve.visible; cb.title = 'Показать/скрыть';
    cb.addEventListener('change', () => { curve.visible = cb.checked; renderCurveList(); redrawAll(); });

    // Цвет кривой (Фаза 2): пикер меняет цвет ТОЛЬКО у этого экземпляра.
    // Палитра по умолчанию (--curve-*) не трогается: она остаётся точкой отсчёта,
    // пользователь лишь перекрывает её локально на время сеанса.
    //
    // ВАЖНО: здесь НЕЛЬЗЯ вызывать renderCurveList(). Она чистит innerHTML
    // списка и уничтожает тот самый input, к которому привязана открытая
    // палитра браузера, поэтому окно выбора цвета захлопывалось на первом же
    // клике по градиенту. Перерисовываем только график, а строку списка
    // подкрашиваем на месте.
    const sw = makeColorPicker(curve.color, (hex) => {
      curve.color = hex; curve.colorCustom = true;
      redrawAll();
    });

    const nm = document.createElement('span');
    nm.className = 'curve-name'; nm.textContent = curveShortName(curve);
    nm.title = curve.expr || '';        // под именем — сама формула
    if (!curve.visible) nm.style.opacity = '.4';

    // Бейдж формы записи (Фаза 1б): видно, что кривая введена как «объём от цены».
    let badge = null;
    if (curve.srcForm === 'QP') {
      badge = document.createElement('span');
      badge.className = 'form-badge'; badge.textContent = 'Q(P)';
      const can = curve.linear ? ('P = ' + fmtLinear(curve.linear.a, curve.linear.b))
                              : 'P = f(Q) считается численно';
      badge.title = 'Введено как Q(P), в расчётах ' + can;
    }

    /* ⚠️ КРЕСТИК ДЕЛАЕТ РАЗНОЕ У РАЗНЫХ КРИВЫХ (решение владельца 22.08).
       У ДОБАВЛЕННОЙ кривой (роли нет) он удаляет — её завёл человек, ему и
       убирать. У ШТАТНОЙ кривой модели (спрос, предложение, MC и прочие с
       ролью) он ГАСИТ: удалённый спрос в «Спросе и предложении» оставляет
       ученика с пустой моделью и без пути назад, кроме «Вернуть исходный
       вид», который заодно снесёт все его правки.
       Гашение — это уже написанный признак visible и та же галочка слева:
       второго механизма видимости рядом с первым не заводим. */
    const staff = !!curve.role;
    const del = document.createElement('button');
    del.className = 'btn-icon'; del.textContent = '✕';
    del.title = staff ? 'Убрать кривую с графика (вернуть — галочкой слева)' : 'Удалить кривую';
    del.setAttribute('aria-label', del.title);
    del.addEventListener('click', () => {
      pushUndo();
      if (staff) { curve.visible = false; }
      else { STATE.curves = STATE.curves.filter(c => c.id !== curve.id); }
      renderCurveList();
      redrawAll();
    });
    if (badge) top.append(cb, sw, nm, badge, del); else top.append(cb, sw, nm, del);

    // Нижняя строка: роль кривой (обычная / спрос / предложение).
    const sel = document.createElement('select');
    sel.className = 'role-sel';
    [['', 'обычная кривая'], ['demand', 'D, спрос'], ['supply', 'S, предложение'],
     ['mc', 'MC, предельные издержки'], ['tc', 'TC, суммарные затраты'], ['atc', 'ATC, средние затраты']]
      .forEach(([v, t]) => {
        const o = document.createElement('option'); o.value = v; o.textContent = t;
        sel.appendChild(o);
      });
    sel.value = curve.role || '';
    sel.addEventListener('change', () => setRole(curve, sel.value));

    // Формула кривой правится прямо здесь: кривая остаётся в списке со своей
    // записью, её не нужно удалять и заводить заново ради одной опечатки.
    // Битую формулу не применяем: подсвечиваем поле и оставляем прежнюю кривую.
    let fInp = null;
    if (curve.kind !== 'vertical') {
      fInp = document.createElement('input');
      fInp.type = 'text'; fInp.className = 'curve-expr-inp';
      fInp.value = curve.srcForm === 'QP' ? (curve.srcExpr || curve.expr) : curve.expr;
      fInp.placeholder = curve.expr ? (curve.srcForm === 'QP' ? 'Q = f(P)' : 'P = f(Q)')
                                    : 'Например: 100 - Q';
      fInp.title = 'Формула кривой: правится на месте';
      fInp.addEventListener('input', () => {
        pushUndo();
        const err = updateCurveExpr(curve, fInp.value);
        fInp.classList.toggle('bad', !!err);
        fInp.title = err ? ('Пока не применено: ' + err) : 'Формула кривой: правится на месте';
        if (!err) {
          nm.textContent = curveShortName(curve);
          redrawAll();
          if (typeof updatePult === 'function') updatePult();
        }
      });
    }

    // Своё имя кривой (Фаза 1). Если задано — идёт и в подпись на графике,
    // и в список, и в чип пульта вместо родового «D»/«S».
    const nameInp = document.createElement('input');
    nameInp.type = 'text'; nameInp.className = 'curve-label-inp';
    nameInp.value = curve.label || '';
    nameInp.placeholder = 'Имя на графике, напр. D₁';
    nameInp.addEventListener('input', () => {
      curve.label = nameInp.value;
      nm.textContent = curveShortName(curve);
      redrawAll();
      if (typeof updatePult === 'function') updatePult();
    });

    /* Плотность строки (Фаза 10). Раньше на каждую кривую приходилось четыре
       контрола во всю ширину подряд, и три кривые занимали весь экран панели.
       Главное в строке — формула, она встаёт наверх рядом с цветом. Своё имя
       и роль нужны заметно реже, поэтому уходят во второй ряд под галочку. */
    const more = document.createElement('div');
    more.className = 'crow-more';
    more.append(nameInp, sel);

    const gear = document.createElement('button');
    gear.type = 'button'; gear.className = 'btn-icon crow-gear';
    gear.title = 'Имя на графике и роль кривой';
    gear.setAttribute('aria-expanded', 'false');
    gear.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
      + ' stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
    gear.addEventListener('click', () => {
      const open = more.classList.toggle('open');
      gear.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    if (fInp) {
      /* Формула занимает ОТДЕЛЬНУЮ строку во всю ширину (А66). Раньше она
         стояла в одном ряду с галочкой, цветом, шестерёнкой и крестиком, и на
         неё оставалось 82 пикселя из 215. Наверху остаётся имя кривой, снизу
         сама запись — так она читается и правится, а не прокручивается по
         букве. */
      const fLine = document.createElement('div');
      fLine.className = 'crow-formula';
      fLine.appendChild(fInp);
      top.insertBefore(gear, del);
      row.append(top, fLine, more);
      /* А66 · А6. Формула кривой правится ТЕМ ЖЕ полем, что и новая: набранная
         запись, клавиатура, подсказка с примерами. Раньше в одном блоке жили
         два способа ввода — у пресетных кривых обычное текстовое окошко
         шириной 84px, у новой кривой поле с набором формул. Поле собирается
         лениво (А56): пока строка не на экране, тяжёлый компонент не создаётся. */
      fInp.id = fInp.id || ('curve-expr-' + curve.id);
    } else {
      top.insertBefore(gear, del);
      row.append(top, more);
    }
    list.appendChild(row);
    /* Оснащаем поле формулы ПОСЛЕ вставки строки в разметку: до этого
       getElementById его не найдёт, и оснащение молча не срабатывало. */
    if (fInp) equipFormulaField(fInp.id, () => (curve.srcForm === 'QP' ? 'QP' : 'PQ'));
  });
  /* Поля формул собираются лениво и только когда видны, а строку мы добавили в
     разметку только что — разбираем очередь здесь (А56 · А66). */
  if (typeof flushMathfields === 'function') flushMathfields();
  if (typeof updatePult === 'function') updatePult();   // пересобрать слайдеры кривых в пульте
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

