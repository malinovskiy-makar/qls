// redrawAll и слой поверх сцены: заголовок, точки, площади, легенда.
/* ---------------------------------------------------------------------
   БЛОК 9. redrawAll() — единая точка перерисовки.
   Любое изменение (кривая, перетаскивание, налог) дёргает её.
   --------------------------------------------------------------------- */
/* Единая перерисовка = сцена + общий слой оформления поверх неё.
   Сцен много, и почти каждая выходит из redrawScene своим `return`, поэтому
   заголовок графика и свои точки рисуются НЕ внутри сцены, а обёрткой после неё:
   так они работают в любом режиме и ни одну сцену не пришлось трогать. */
function redrawAll() {
  syncParams();          // формулы могли завести или потерять буквы-параметры
  refreshLinearForParams();   // Н7: прямые с буквой пересобрать под новое значение
  /* Естественная область модели считается раз на кадр (см. modelSpanQ). Метку
     двигаем ЗДЕСЬ и только здесь: выше по коду формулы и ползунки уже собраны,
     ниже начинается счёт, который этой областью и пользуется. */
  bumpModelSpan();
  redrawScene();
  drawOverlays();
  applyLabelSize();      // общий размер подписей — одним проходом по холсту (П50)
  unclipLabels();        // подпись, которую режет её же обрезка, переезжает наружу
  keepAxisNamesInside(); // и название оси зажимается по ФАКТИЧЕСКОМУ кеглю
  spreadLabels();        // и разведение наложившихся — тем же приёмом (А60)
  applyLabelInk();       // и читаемые чернила подписей — тем же приёмом (П75)
  /* ⚠️ ОБОЗНАЧЕНИЯ НАБИРАЮТСЯ МАТЕМАТИКОЙ В САМОМ КОНЦЕ, ПОСЛЕ ВСЕХ СЛОЁВ.
     Первый заход стоял внутри drawOverlays, и подписи, которые сцена рисует
     позже (S в «Налогах», ATC и MC в естественной монополии, TC в «Сложении
     заводов»), правило уже не заставало: замер 24.08 находил их обычным
     шрифтом. Здесь холст собран целиком, кто бы что ни дорисовал. */
  typesetChartLabels();
  /* ⚠️ ОБОЗНАЧЕНИЯ В ПАНЕЛЯХ РАЗМЕЧАЮТСЯ ТУТ ЖЕ, В САМОМ КОНЦЕ, И ПО ТОЙ ЖЕ
     ПРИЧИНЕ. Первый заход стоял внутри refreshAnalyticsPanel, и прозу, которую
     сцена дописывает позже («продав единицу X, получаешь 2 ед…»), проход уже не
     заставал: замер 24.08 находил 26 таких мест в семи сценах. Здесь панель
     собрана целиком, кто бы что ни дописал. */
  markNotationsIn(document.getElementById('tools-panel'));
  markNotationsIn(document.getElementById('params-panel'));
  refreshRegulators();   // строки «имя = значение» идут за значениями ползунков
  // Заголовок раздела равновесия — свойство сцены (А52). Синхронизируем здесь,
  // а не только в рыночном пересчёте: иначе в сцене, куда пришли из монополии,
  // до первого пересчёта висел бы чужой заголовок.
  if (typeof updateEqSectionTitle === 'function') updateEqSectionTitle();
  /* Поля формул собираются лениво (А56): те, что стали видны после смены
     сцены или раскрытия секции, разбираются здесь — на СЛЕДУЮЩЕМ кадре, когда
     раскладка уже пересчитана. Синхронный вызов видел нулевые размеры у
     только что показанной секции и оставлял поле в очереди. */
  if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
  // А6: обычных текстовых окошек в панели не остаётся — имена правятся на
  // месте тем же способом, что и числа. Строки сцен собираются на лету,
  // поэтому проходим по панели после каждой перерисовки.
  if (typeof upgradeTextFieldsIn === 'function') upgradeTextFieldsIn('tools-panel');
  // Кусочная запись обязана помещаться в поле целиком (решение владельца 24.08):
  // строка отдаёт полю всю ширину, кегль подбирается вниз до предела 11 px.
  if (typeof fitFormulaFieldsSoon === 'function') fitFormulaFieldsSoon();
  // Последним: карточка блока прячет переключатели соседних моделей. Идёт после
  // обычной логики видимости, иначе та вернула бы их на место.
  applyCardScope();
  // И только теперь — вопросики: знак без живой подсказки прячется. Раньше
  // applyCardScope нельзя, иначе проход не увидит спрятанного соседа.
  if (typeof syncHintDots === 'function') syncHintDots();
  /* И подгонка аналитической записи по ширине панели — в самом конце, по той
     же причине, что и разметка обозначений: сцены дописывают разбор позже, и
     проход, стоящий раньше, мерил бы не всю врезку. */
  if (typeof fitPanelMath === 'function') fitPanelMath();
}

function redrawScene() {
  refreshColors();      // перечитать цвета из CSS-переменных (учитывает смену темы)
  clearResultPanels();  // очистить табло — активный режим заполнит свои блоки
  /* ⚠️ РЕЕСТР ПАНЕЛЕЙ ЧИСТИТСЯ ПЕРВЫМ ДЕЛОМ, ДО ЛЮБОЙ ОТРИСОВКИ.
     Панели прошлого кадра не имеют права дожить до нового: сцена сменилась,
     а слой поверх неё считал бы по чужим шкалам. */
  clearPanels();
  resetDrawnKeyPoints();   // и пары нарисованных ключевых точек — тоже заново
  computeSize();
  makeScales();
  if (STATE.mode === 'costs') { redrawCosts(); return; }   // режим издержек (Задача 2)
  if (STATE.mode === 'ppf')   { redrawPpf();   return; }   // режим КПВ (Задача 3)
  if (STATE.mode === 'labor') { redrawLabor(); return; }   // режим рынка труда (Чекпоинт 1)
  if (STATE.mode === 'inequality') { redrawInequality(); return; }   // режим неравенства (ЧК1–3)
  if (STATE.mode === 'consumer')   { redrawConsumer();   return; }   // теория потребителя (Фаза 8)
  if (STATE.mode === 'macro')      { redrawMacro();      return; }   // макромодели (Фазы 16–22)
  if (STATE.mode === 'math')       { redrawMath();       return; }   // раздел «Математика» (Фаза 7)
  if (STATE.mode === 'graph')      { redrawGraphMode();  return; }   // построение графиков
  // Под-режимы монополии с собственной отрисовкой (Чекпоинт 2): дискриминация 3-й степени
  // (два мини-графика) и ломаный спрос — самодостаточны, рисуют свои оси и панель.
  if (STATE.mode === 'market' && STATE.market === 'monopoly') {
    if (STATE.monoMode === 'discr3') { redrawDiscr3(); return; }
    if (STATE.monoMode === 'kinked') { drawKinkedFull(); return; }
  }
  recompute();                   // сначала считаем (равновесие, площади, налог)
  svg.selectAll('*').remove();   // полная перерисовка с чистого листа
  addDefs();
  drawGrid();
  drawAxes();
  if (STATE.market === 'monopoly' && STATE.monoMode === 'discr1') {
    // Ценовая дискриминация 1-й степени (Задача 4): D, MC и область прибыли.
    drawDiscr1();
  } else if (STATE.market === 'monopoly' && STATE.monoMode === 'natural') {
    // Естественная монополия (Фаза 3в): ATC + три ориентира регулирования.
    drawNaturalFull();
  } else if (STATE.market === 'monopoly') {
    if (STATE.monoCeil && STATE.monoCeil.binding) {
      // Связывающий потолок (Задача 3): ломаный MR_eff, новый выпуск, дефицит.
      drawMonoCeilingAreas();    // CS/VC/PS до нового Q + DWL (Qstar..Qc)
      drawCurves();              // спрос D и (если задана явно) кривая MC
      drawMonopoly();            // обычный падающий MR
      drawMonoKinkedMR();        // ломаный MR_eff (горизонталь на Pc до Q̂)
      drawMonoCeilingPoints();   // новый M(Qstar,price), призрак M₀(Qm,Pm), дефицит
      drawMonoCeilingLine();     // перетаскиваемая линия потолка
    } else if (STATE.monoTax) {
      // Налог/субсидия (Фаза 2): сдвиг MC, новый оптимум MR = MC ± ставка.
      drawMonoTaxAreas();        // CS + деньги бюджета (полоса между MC и MC±ставка) + DWL
      drawCurves();              // спрос D и базовая MC
      drawMonopoly();            // MR + (если MC из TC) базовая MC
      drawMonoTaxShiftedMC();    // пунктирная сдвинутая MC±ставка
      drawMonoTaxPoints();       // новый M(Qt,Pt) + призрак M₀(Qm,Pm)
    } else if (STATE.monoFloor && STATE.monoFloor.binding) {
      // Связывающий пол цены (Фаза 2): цена = Pf, выпуск = спрос при Pf.
      drawMonoFloorAreas();
      drawCurves();
      drawMonopoly();
      drawMonoFloorPoints();     // новый M(Q,Pf) + призрак M₀(Qm,Pm)
      drawMonoFloorLine();       // перетаскиваемая линия пола
    } else if (STATE.monoQuota && STATE.monoQuota.binding) {
      // Связывающая квота (приёмка 31.08): выпуск = Qk, цена = D(Qk).
      // Коридора цен здесь нет — монополист берёт верхний край (см. monopolyQuota).
      drawMonoQuotaAreas();
      drawCurves();
      drawMonopoly();
      drawMonoQuotaPoints();     // новый M(Qk, D(Qk)) + призрак M₀(Qm,Pm)
      drawMonoQuotaLine();       // вертикаль разрешённого объёма
    } else {
      // Обычная монополия (вмешательства нет / не связывает): потери DWL, D/MC, MR, точки.
      drawMonopolyAreas();
      drawCurves();              // спрос D и (если задана явно) кривая MC
      drawMonopoly();            // MR + (если MC выведена из TC) сама MC
      drawMonopolyPoints();      // точки M и MR=MC, проекции, конкурентный ориентир
      if (STATE.intervType === 'ceiling' && STATE.pRegSet) drawMonoCeilingLine();  // линия видна, но не связывает
      else if (STATE.intervType === 'floor' && STATE.pRegSet) drawMonoFloorLine(); // линия видна, но не связывает
      else if (STATE.intervType === 'quota' && STATE.quotaSet) drawMonoQuotaLine();// вертикаль видна, но не связывает
    }
  } else if (STATE.scenario === 'externality') {
    // Внешний эффект (Задача 4): DWL + D/MPC + MSC + точки Qрын/Qопт (+ Пигу).
    drawExtScenario();
  } else if (STATE.scenario === 'openecon') {
    // Малая открытая экономика (Фаза 4в): излишки/деньги/потери, кривые, линии цен.
    drawOpenAreas();
    drawCurves();
    drawOpenLines();
  } else if (STATE.scenario === 'elasticity') {
    // Эластичность спроса (Задача 2): зоны + кривые + равновесие + точка |Ed|.
    drawElasticityZones();
    drawCurves();
    drawEquilibrium();
    drawElasticityPoint();
    drawElasticityPointS();   // вторая точка — на предложении (Фаза 2а)
  } else {
    // Конкуренция, обычный сценарий: заливки + кривые + равновесие/вмешательство.
    if (STATE.taxActive) drawTaxAreas();
    else if (STATE.pcActive) drawPcAreas();
    else if (STATE.quotaActive) drawQuotaAreas();
    else drawAreas();
    drawGhost();                 // бледный слой «было» под кривыми/точками
    drawCurves();
    drawShiftedSupply();         // пунктирная S + t (если налог активен)
    // Центр поворота при процентной форме: обе кривые предложения продолжены
    // пунктиром к общей точке на оси Q (рис. 81 учебника).
    if (typeof drawTaxPivot === 'function') drawTaxPivot();
    // Точки/линии: налог E₀/E₁, регулирование цены, квота или равновесие E*.
    if (STATE.taxActive) drawTaxPoints();
    else if (STATE.pcMode) drawPriceControl();
    else if (STATE.quotaMode) drawQuotaLines();
    else drawEquilibrium();
    // Равновесия нет, а пересечение есть — показываем, куда оно уехало.
    if (typeof drawOffQuadIntersection === 'function') drawOffQuadIntersection();
  }
  updateInfoPanel();
  updateAreasPanel();
  // Табло «По группам» сюжета сложения: в остальных сценах оно молчит само.
  if (typeof updateSumPanel === 'function') updateSumPanel();
  if (STATE.market === 'monopoly') {
    if (STATE.monoMode === 'discr1') updateDiscr1Panel(); else updateMonoPanel();
    if (STATE.monoMode === 'natural') updateNaturalPanel();   // три ориентира регулирования (Фаза 3в)
    // Вмешательство государства в монополии (Фаза 2): налог/субсидия/потолок/пол.
    updateMonoInterventionPanel();
  } else if (STATE.scenario === 'externality') {
    updateExtPanel();
    const imono = document.getElementById('info-mono'); if (imono) imono.innerHTML = '';
  } else if (STATE.scenario === 'elasticity') {
    updateElasticityPanel();
    const imono = document.getElementById('info-mono'); if (imono) imono.innerHTML = '';
  } else if (STATE.scenario === 'openecon') {
    updateOpenPanel();
    const imono = document.getElementById('info-mono'); if (imono) imono.innerHTML = '';
  } else {
    if (STATE.pcMode) updatePcPanel();
    else if (STATE.quotaMode) updateQuotaPanel();
    else updateTaxPanel();
    // Панель монополии очищаем, чтобы не висело старое из прошлого режима.
    const imono = document.getElementById('info-mono');
    if (imono) imono.innerHTML = '';
  }
}

/* ---------------------------------------------------------------------
   ПОСТРОЕНИЕ ГРАФИКОВ — режим mode='graph'.
   Экономики здесь нет: только оси, сетка и столько функций, сколько нужно.
   Равновесия, излишков и вмешательств сцена не считает, поэтому и «Аналитики»
   у неё нет. Свои точки, площади и ползунки параметров работают как везде.
   --------------------------------------------------------------------- */
function redrawGraphMode() {
  svg.selectAll('*').remove();
  addDefs();
  drawGrid();
  drawAxes('x', 'y');
  drawCurves();
  updateGraphPanel();   // А53: нули, вершины и пересечения построенных кривых
}

/* Строки функций сюжета min/max. Первая строка это общее поле f(x) раздела,
   остальные свои; каждая со своим цветом и набирается тем же движком ввода. */
function renderMmRows() {
  const box = document.getElementById('mm-rows');
  if (!box) return;
  const n = Math.max(2, STATE.mmCount || 2);
  box.innerHTML = '';
  for (let i = 0; i < n; i++) {
    const row = document.createElement('div');
    row.className = 'field';
    const lab = document.createElement('label');
    lab.textContent = 'Функция ' + mmLabel(i);
    row.appendChild(lab);

    const line = document.createElement('div');
    line.className = 'grow';
    line.appendChild(makeColorPicker(mmColor(i), (hex) => {
      STATE.colorOverride['mm' + i] = hex; redrawAll();
    }, 'Цвет ' + mmLabel(i)));
    const slot = document.createElement('div');
    slot.className = 'f-slot';
    const inp = document.createElement('input');
    inp.type = 'text'; inp.autocomplete = 'off';
    inp.value = mmGet(i);
    inp.placeholder = i === 0 ? 'Например: x^2' : 'Например: 4 - x';
    inp.setAttribute('aria-label', 'Функция ' + mmLabel(i));
    inp.addEventListener('input', () => { mmSet(i, inp.value); redrawAll(); });
    slot.appendChild(inp);
    line.appendChild(slot);
    row.appendChild(line);
    box.appendChild(row);
    /* Н70. Поля этого сюжета собираются здесь, вручную, и раньше получали
       только upgradeFormulaField — то есть математический набор, но БЕЗ кнопки
       клавиатуры и без вопросика. Клавиатура должна быть у каждого поля формулы
       в каждой сцене, поэтому подключаем общую оснастку: ей нужен id. */
    if (!inp.id) inp.id = 'mm-f' + i;
    equipFormulaField(inp.id, 'MATHF');
  }
}

/* Список функций как в графопостроителе: внизу всегда одна пустая строка.
   Начали печатать — она превращается в обычную строку списка (цвет, имя,
   удаление, правка формулы), а под ней появляется новая пустая. */
function graphRowsBox() { return document.getElementById('graph-rows'); }
let graphFieldSeq = 0;   // порядковый номер поля строки: набор навешивается по id

function renderGraphRows() {
  const box = graphRowsBox();
  if (!box) return;
  box.innerHTML = '';
  /* Блока пустого состояния здесь нет: исключение из канона 3.13 записано в
     DESIGN.md 5.1. Пустая строка ввода сама является приглашением к действию —
     она подписана и несёт образец формулы, — а плашка занимала место на самом
     плотном экране продукта и вдобавок оставалась на виду ПОСЛЕ того, как
     функция введена и кривая построена. */
  STATE.curves.forEach(c => box.appendChild(buildGraphRow(c)));
  box.appendChild(buildGraphRow(null));
  equipGraphRows(box);
  /* Поля формул собираются лениво и только когда видны (А56), а строки мы
     вставили в разметку только что: разбираем очередь здесь, иначе поле
     остаётся обычным текстовым окошком до следующей перерисовки. */
  if (typeof flushMathfields === 'function') flushMathfields();
}

function graphError(msg) {
  const e = document.getElementById('graph-error');
  if (!e) return;
  e.textContent = msg || '';
  e.style.display = msg ? 'block' : 'none';
}

function buildGraphRow(curve) {
  const row = document.createElement('div');
  row.className = 'grow';
  if (curve) row.dataset.cid = curve.id;

  // Цвет: у пустой строки показываем тот, который достанется следующей кривой.
  const pick = makeColorPicker(curve ? curve.color : nextColor(), (hex) => {
    if (!row._curve) return;
    row._curve.color = hex; row._curve.colorCustom = true;
    redrawAll();
  }, 'Цвет кривой');
  row.appendChild(pick);

  const slot = document.createElement('div');
  slot.className = 'f-slot';
  const inp = document.createElement('input');
  inp.type = 'text'; inp.autocomplete = 'off';
  inp.value = curve ? curve.expr : '';
  /* Образец без пробелов вокруг минуса: замер показал, что «x^2 - 4» шире
     содержимого поля на пять пикселей и обрезается. Текст образца владелец
     оставил, требование было одно — он обязан помещаться целиком. */
  inp.placeholder = curve ? '' : 'Например: x^2-4';
  inp.setAttribute('aria-label', 'Формула функции');
  slot.appendChild(inp);
  row.appendChild(slot);

  const del = document.createElement('button');
  del.type = 'button'; del.className = 'btn-icon'; del.textContent = '✕';
  del.setAttribute('data-tip', 'Убрать функцию');
  del.style.visibility = curve ? '' : 'hidden';
  del.addEventListener('click', () => {
    if (!row._curve) return;
    pushUndo();
    STATE.curves = STATE.curves.filter(c => c !== row._curve);
    renderGraphRows();
    redrawAll();
  });
  row.appendChild(del);

  const name = document.createElement('input');
  name.type = 'text'; name.className = 'grow-name';
  name.placeholder = 'Имя на графике';
  name.value = (curve && curve.label) || '';
  name.addEventListener('input', () => {
    if (!row._curve) return;
    const v = name.value.trim();
    if (v) row._curve.label = v; else delete row._curve.label;
    redrawAll();
  });
  row.appendChild(name);

  row._curve = curve || null;
  inp.addEventListener('input', () => graphRowInput(row, inp, del, name));
  /* П19 · П21. Строка «Построения графиков» получает ТОТ ЖЕ набор, что поля
     формул во всех остальных сценах: клавиатуру и вопросик. Прежде здесь
     звалась только `upgradeFormulaField` — поле становилось математическим,
     но без клавиатуры и без подсказки, и это была единственная сцена, где
     формулу набирать было нечем, кроме системной клавиатуры.
     Идентификатор строке нужен: набор навешивается по id. */
  /* ⚠️ НАБОР НАВЕШИВАЕТСЯ ПОСЛЕ ВСТАВКИ В СТРАНИЦУ, А НЕ ЗДЕСЬ.
     `equipFormulaField` ищет поле через `getElementById`, а строка в этот
     момент ещё не в документе: вызов отсюда молча ничего не делал, и поле
     оставалось без клавиатуры и вопросика. Отдаём id, разбирает renderGraphRows. */
  if (!inp.id) inp.id = 'graph-f-' + (++graphFieldSeq);
  return row;
}

/* ⚠️ СТРОКА СПИСКА РОЖДАЕТСЯ ОДИНАКОВО, КАКИМ БЫ ПУТЁМ ЕЁ НИ ЗАВЕЛИ.

   Путей два: полная пересборка списка и «рождение» следующей пустой строки
   сразу после ввода. Набор полей вешала только пересборка, поэтому строка,
   добавившаяся сама, оставалась обычным текстовым полем — и общий проход по
   текстовым полям превращал её в правку-на-месте с пунктиром. На экране
   выходило два разных способа ввода одного и того же: у первой строки
   настоящее поле формул с клавиатурой, у второй — пунктирная строчка, дающая
   по щелчку голый курсор с обрубком линии.

   Разница была не в оформлении, а в том, что набор навешивался в одном месте
   из двух. Теперь он один на оба пути.

   П19 · П21: строки «Построения графиков» получают ТОТ ЖЕ набор, что поля
   формул остальных сцен, — клавиатуру и вопросик. */
function equipGraphRows(box) {
  if (!box || typeof equipFormulaField !== 'function') return;
  box.querySelectorAll('.f-slot > input[id]').forEach(el => equipFormulaField(el.id, 'MATH'));
  if (typeof flushMathfields === 'function') flushMathfields();
}

/* Правка строки. Пустая строка при первом же осмысленном вводе заводит кривую
   и «рожает» следующую пустую; заполненная просто обновляет свою формулу. */
function graphRowInput(row, inp, del, name) {
  const txt = (inp.value || '').trim();
  if (!row._curve) {
    if (!txt) return;
    const { compiled, error } = compileFormula(txt);
    /* П16. Фраза стоит У ЭТОГО поля, а не в общем блоке ошибок наверху панели:
       строк формул в сцене несколько, и общий блок не говорит, в какой из них
       беда. Общий блок оставлен пустым, чтобы не сообщать одно и то же дважды. */
    if (error) { fieldProblem(inp, 'Пока не понимаю запись: ' + error); return; }
    fieldProblem(inp, ''); graphError('');
    curveCounter++;
    const c = { id: curveCounter, expr: txt, compiled, color: nextColor(),
                role: null, visible: true,
                linear: detectLinear(compiled), srcForm: 'PQ' };
    STATE.curves.push(c);
    row._curve = c;
    row.dataset.cid = c.id;
    del.style.visibility = '';
    const box = graphRowsBox();
    if (box) { box.appendChild(buildGraphRow(null)); equipGraphRows(box); }
    redrawAll();
    return;
  }
  if (!txt) return;                       // пустое поле не роняет кривую
  pushUndo();
  const err = updateCurveExpr(row._curve, txt);
  fieldProblem(inp, err ? ('Пока не понимаю запись: ' + err) : '');
  if (!err) redrawAll();
}

/* ---------------------------------------------------------------------
   ОФОРМЛЕНИЕ (Фаза 1) — слой поверх любой сцены: заголовок и свои точки.
   --------------------------------------------------------------------- */

/* Шкалы ПАНЕЛИ. Без аргумента — панели под курсором, с аргументом — названной.

   ⚠️ Здесь стояло построение шкал из CONFIG.Qmin/Qmax на всю ширину холста.
   Сделано это было нарочно — чтобы не брать глобальные sx/sy, в которых у
   многопанельных сцен остаётся шкала ПОСЛЕДНЕЙ панели. Лечение вышло хуже
   болезни: слой перестал совпадать НИ С ОДНОЙ панелью (разбор — у registerPanel
   в 20-plane.js). Ветки «в математике окно другое» здесь тоже больше нет:
   панель раздела «Математика» регистрируется наравне со всеми.

   Запасной путь оставлен на один случай: реестр пуст до самой первой
   перерисовки, а спросить шкалы могут и раньше. */
function mainScales(panelId) {
  const p = (panelId != null) ? panelById(panelId) : activePanel();
  if (p) return { mx: p.mx, my: p.my };
  const m = CONFIG.margin;
  if (STATE.mode === 'math') return mathScales();
  return {
    mx: d3.scaleLinear().domain([CONFIG.Qmin, CONFIG.Qmax]).range([m.left, W - m.right]),
    my: d3.scaleLinear().domain([CONFIG.Pmin, CONFIG.Pmax]).range([H - m.bottom, m.top]),
  };
}

function drawOverlays() {
  if (!svg || !svg.node()) return;
  /* Сцена дорисована — объявляем на холсте её ключевые точки. Строго ЗДЕСЬ:
     раньше сцены нет целиком, а пары ищутся по пунктиру, который сцена рисует
     то до числа на оси, то после него. */
  flushDrawnKeyPoints();
  invalidateKeyTargets();    // особые точки считаются заново под новую картинку
  /* ⚠️ ПЕРЕСЕЧЕНИЯ СЧИТАЮТСЯ ЗДЕСЬ, А НЕ ТАМ, ГДЕ ИХ РИСУЮТ.

     Раньше `STATE.crosses` обновлял `drawCrossPoints`, а он идёт ниже расчёта
     площадей и набранных вершин. Всё, что спрашивало ключевые точки раньше
     него, получало картину ПРОШЛОГО кадра — и, что хуже, клало её в кэш на
     весь текущий. Сдвинули кривую: пересечение уже в другом месте, а вершина,
     стоящая в старом, всё ещё считает себя стоящей в пересечении. Общее
     состояние не может обновляться побочным действием отрисовки. */
  /* Пересечения считаются для ПАНЕЛИ ВЗВЕДЁННОЙ КРИВОЙ, а нет взведённой —
     для панели под курсором. Рядом с ними кладётся её id: без него полка
     отдала бы соседней панели чужие точки. */
  const crossPanel = armedPanelId();
  STATE.crossesPanel = String(crossPanel == null
    ? (activePanel() ? activePanel().id : '') : crossPanel);
  STATE.crosses = crossPoints(crossPanel);
  if (typeof resetLabelBoxes === 'function') resetLabelBoxes();   // подписи расставляются заново
  applyAreaColors();         // свои цвета заливок — одним проходом по data-legend
  drawAreaCalc();            // посчитанная площадь (Фаза 10)
  drawAreaVerts();           // набранные вершины будущей площади
  /* Полосы попадания — СТРОГО перед кружками: кружку ключевой точки нужен свой
     запас попадания, и он обязан лежать ВЫШЕ полосы кривой, иначе промах по
     точке на пять пикселей уносит руку в кривую. */
  drawCurveHits();           // полосы попадания у кривых, нарисованных сценой
  drawCrossPoints();         // ключевые точки взведённой кривой
  drawRoller();              // точка, катящаяся по кривой
  drawGraphTitle();
  drawLegend();
  drawMarks();
  syncAxisPlaceholders();
  syncSceneColorPickers();   // образцы в панели идут за темой и за своими цветами
  syncAreaCalcUI();          // выпадашка кривых и список точек для расчёта площади
  hintsToDots();             // подсказки, добавленные сценой, тоже уходят под вопросик
  syncFirstCard();                                     // ярче та карточка, где вводят формулы
  refreshAnalyticsPanel();
  renderMathIn(document.getElementById('ex-body'));    // и в объяснении модели
  renderMathIn(document.getElementById('tools-panel'));// и в подсказках панели
  /* Обозначения в подписях панели размечает redrawAll в самом конце: сцена
     дописывает часть текста позже, и проход отсюда её не застаёт. */
}

/* Довести правую панель до готового вида: разбор в свой блок, формулы, числа
   с колонкой знаков равенства. Вынесено отдельно, потому что зовётся не только
   из общей перерисовки: перетаскивание линии цены обновляет ТОЛЬКО панель и
   слои цены (Б32), и без этого прохода числа в пути показывались сырым текстом,
   а на отпускании скачком превращались в формулы. */
/* ── ТАБЛО ПЕРЕПИСЫВАЕТСЯ, ТОЛЬКО ЕСЛИ ТЕКСТ ИЗМЕНИЛСЯ ────────────────
   Второй приём, взятый из сложения КПВ (там кэш зовётся STATE.ppfSumData и
   держится по подписи): панорама и зум не имеют права ничего пересчитывать
   заново. Здесь ровно та же болезнь, только не в счёте, а в наборе.

   Что происходило. `drawOverlays` зовёт `update*Panel` на КАЖДОЙ перерисовке,
   то есть на каждое движение мыши при панорамировании. Каждая такая функция
   собирает свою разметку и кладёт её в табло целиком — `box.innerHTML = html`.
   Числа при этом те же самые: равновесие, излишки и разбор по группам от
   границ кадра не зависят и с прошлой сессии считаются по кэшу. Но текст
   перезаписывался, а значит заново набирался KaTeX, заново размечались
   обозначения, заново мерились ширины строк — и браузер заново раскладывал
   всю правую панель.

   Замер 25.08, набор Б при РАСКРЫТЫХ карточках (иначе замер занижен):
   33,56 мс на кадр; с отключённым набором формул — 18,48 мс. То есть сорок
   пять процентов кадра уходило на перенабор того же самого текста. Записей в
   табло за кадр — тридцать штук, и содержимое менялось ровно у трёх:
   `info-sum` (1641 символ), `info-areas` (199) и `info-eq` (123), да и у тех
   от кадра к кадру текст один и тот же.

   ⚠️ ЗАЩИТА СТОИТ НА САМОМ УЗЛЕ, А НЕ НА ТРИДЦАТИ МЕСТАХ ЗАПИСИ.
   Табло пишут тридцать разных мест в четырёх файлах, и каждое пишет
   СОДЕРЖИМОЕ ЦЕЛИКОМ. Ставить проверку в каждом — тридцать шансов забыть
   одно и получить табло, которое молча не обновляется. Поэтому свойство
   переопределяется у самих узлов табло, один раз: запись тем же текстом
   ничего не делает, запись другим текстом работает как и работала.
   Чтение (`get`) не трогаем вовсе — оно отдаёт настоящее содержимое, уже
   набранное формулами.

   ⚠️ ПОЧЕМУ ЭТО НЕ ЛОМАЕТ ПЕРЕЕЗД ВРЕЗОК. `syncAnalyticsPanel` переносит
   `.sb-note` из табло в «Объяснение модели» узлами, а не текстом. Пропущенная
   запись тем же текстом врезку не вернёт — и правильно: она уже на месте.
   Как только текст табло действительно изменится, разметка перепишется
   целиком, врезка появится снова и снова переедет. */
/* ⚠️ ОДНОЙ ЗАЩИТЫ НА ЗАПИСЬ НЕ ХВАТИЛО, И ВОТ ПОЧЕМУ.
   Перед каждой перерисовкой `clearResultPanels` гасит ВСЕ табло пустой
   строкой, чтобы активный режим заполнил свои, а чужие остались пустыми.
   Получается, что за кадр в каждое табло пишут дважды: сперва пустоту, потом
   содержимое. Сравнение «тот же текст?» при таком чередовании не совпадает
   НИКОГДА: пустота против содержимого и содержимое против пустоты.
   Замер 25.08: строк табло, набираемых заново, — 24 на кадр, при том что
   числа в них не менялись.

   Поэтому гашение стало ОТЛОЖЕННЫМ. Табло помечается «погасить, если никто
   не напишет», а гасится в конце перерисовки — и только то, в которое так
   никто и не написал. Смысл прежний: чужие блоки остаются пустыми, чисел из
   прошлого режима на экране нет. */
/* ⚠️ info-final ЗАЩИЩАЕТСЯ, НО В RESULT_IDS НЕ ВХОДИТ, И ЭТО РАЗНЫЕ СПИСКИ.
   RESULT_IDS отвечает за ПЕРЕЕЗД блока в конец табло (relocateForScene), а
   здесь речь только о защите от перенабора тем же текстом. Итоговая функция
   обязана остаться первой, поэтому переезжать ей нельзя, а не переписываться
   лишний раз — нужно ровно так же, как всем: она набирается KaTeX, и перенабор
   на каждом кадре панорамы стоит дороже всего остального в панели. */
function guardedPanelIds() {
  const extra = (typeof RESULT_IDS !== 'undefined' && Array.isArray(RESULT_IDS)) ? RESULT_IDS : [];
  return ['info-eq', 'info-final'].concat(extra);
}
function guardPanelBoxes() {
  if (guardPanelBoxes._done) return;
  const proto = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  if (!proto || !proto.get || !proto.set) return;     // разметка чужая — просто не защищаем
  let n = 0;
  guardedPanelIds().forEach(id => {
    const box = document.getElementById(id);
    if (!box || box._panelGuarded) return;
    box._panelGuarded = true;
    n++;
    Object.defineProperty(box, 'innerHTML', {
      configurable: true,
      get() { return proto.get.call(this); },
      set(v) {
        this._pendingClear = false;                   // написали — гасить не надо
        if (this._srcHtml === v) return;              // тот же текст — набирать нечего
        this._srcHtml = v;
        _panelsChanged = true;
        proto.set.call(this, v);
      },
    });
  });
  if (n) guardPanelBoxes._done = true;
}

/* Изменилось ли за эту перерисовку хоть одно табло. Нужен переезду врезок:
   он забирает `.sb-note` ИЗ табло в «Объяснение модели», то есть после
   переезда в табло врезки уже нет. Пока табло переписывалось каждый кадр,
   врезка появлялась заново и переезжала заново; теперь табло не
   переписывается — и переезжать нечему. Значит и трогать «Объяснение модели»
   не надо: разбор уже там и никуда не делся.

   ⚠️ ЭТО НЕ УКРАШЕНИЕ, А УСЛОВИЕ ПРАВИЛЬНОСТИ. Без него проверка «Панель · в
   построении графиков и деформациях есть что показать» сразу покраснела:
   разбор становился пустым на втором же кадре. */
let _panelsChanged = true;
function panelsChangedSinceLastPass() {
  const was = _panelsChanged;
  _panelsChanged = false;
  return was;
}
function markPanelsChanged() { _panelsChanged = true; }

// Погасить те табло, в которые за эту перерисовку никто так и не написал.
function flushPendingPanelClears() {
  guardedPanelIds().forEach(id => {
    const box = document.getElementById(id);
    if (!box || !box._panelGuarded || !box._pendingClear) return;
    box._pendingClear = false;
    box.innerHTML = '';
  });
}

function refreshAnalyticsPanel() {
  guardPanelBoxes();                                   // ставится один раз, дальше бесплатно
  flushPendingPanelClears();                           // чужие блоки гаснут здесь, а не заранее
  syncAnalyticsPanel();                                // разбор уезжает в свой блок
  typesetChartLabels();                                // обозначения на графике — математикой
  renderMathIn(document.getElementById('sb-body'));    // формулы в аналитике
  /* Здесь проход нужен ОТДЕЛЬНО от общего: перетаскивание линии цены обновляет
     ТОЛЬКО панель, redrawAll при этом не зовётся, и подписи в пути остались бы
     обычным шрифтом, а на отпускании скачком стали бы формулами. */
  markNotationsIn(document.getElementById('params-panel'));
  typesetStats(document.getElementById('sb-body'));    // Н6: числа тоже формулой
}

/* ── Н6. Правая колонка «Ключевых значений» ───────────────────────────────
   Подписи слева и раньше шли через рендер формул, а числа справа печатались
   обычным жирным текстом и разметка растягивала их по краям строки. Отсюда и
   «далеко стоят», и «жирные», и «скачут по вертикали»: у каждой строки своя
   длина подписи, и числа вставали лесенкой.

   Пройтись по 244 местам, где сцены собирают строки, невозможно и не нужно:
   один проход по готовому табло делает то же самое для всех сразу. Каждое
   число печатается KaTeX (значит, настоящие индексы и минусы), между подписью
   и числом ставится знак равенства, и колонка знаков стоит на одной линии —
   как в учебнике.

   Что НЕ трогаем: строки-подсказки без числа (там нечего приравнивать),
   уже обработанные строки и значения, которые сами являются словом («да»,
   «дефицит»): равенство между подписью и словом читалось бы неверно. */
function typesetStats(root) {
  if (!root) return;
  root.querySelectorAll('.stat').forEach(row => {
    if (row._typeset) return;
    const lab = row.querySelector(':scope > span');
    const val = row.querySelector(':scope > b');
    if (!lab || !val) return;
    row._typeset = true;
    /* Значение уже набрано формулой самой сценой (renderMathIn прошёл раньше
       нас). Тогда трогать его нельзя: textContent у готового KaTeX это тройка
       «MathML + исходная запись + видимый текст», и мы напечатали бы её целиком.
       И знак равенства не ставим: в таком значении он обычно уже есть, вышло бы
       «Наибольшее = y* = 5». */
    /* Значение уже набрано формулой самой сценой? Тогда textContent у него —
       тройка «MathML + исходная запись + видимый текст», и читать надо только
       видимую часть. Проверку на «не помещается» делаем ДО остального: длинная
       фраза с формулой внутри («эластичный, |E_d| > 1») это тоже KaTeX. */
    const own = !!val.querySelector('.katex');
    const raw = (own ? katexVisibleText(val) : (val.textContent || '')).trim();
    if (!raw) { if (own) row.classList.add('stat-eq', 'stat-own', 'stat-nosign'); return; }
    // Составное значение и фраза не помещаются в ячейку для числа (Б39, Б40).
    if (restatWide(row, lab, val, raw, own)) { addStatSign(row, val, raw); return; }
    if (own) { row.classList.add('stat-eq', 'stat-own'); addStatSign(row, val, raw); return; }
    // Числовое ли значение: число, пара, проценты, знак — да; фраза — нет.
    const numeric = /^[(\[]?\s*[-−+]?[\d.,]/.test(raw) || /^[-−+]?\d/.test(raw);
    if (numeric && typeof katex !== 'undefined') {
      try {
        if (!katexInto(val, statToTex(raw))) throw new Error('katex');
        val.classList.add('stat-tex');
      } catch (e) { /* остаётся прежним текстом */ }
    }
    row.classList.add('stat-eq');
    // Своё равенство внутри значения («SW = CS + PS») тоже не удваиваем.
    addStatSign(row, val, raw);
  });
}

/* ⚠️ ФОРМАТ СТРОКИ ОДИН НА ВЕСЬ СПИСОК — СО ЗНАКОМ РАВЕНСТВА.

   Форматов было три сразу: без знака (подпись, а значение под ней), со знаком,
   и один выровненный по правому краю. В одном списке это читается как три
   разных вида данных, хотя данные одни. Знак теперь ставит одна функция, и
   зовут её ВСЕ ветки разбора, включая те, что раньше возвращались раньше
   времени.

   Единственное исключение — значение со СВОИМ равенством внутри («SW = CS +
   PS»): второй знак дал бы «SW = = CS + PS». */
function addStatSign(row, val, raw) {
  if (!row || !val) return;
  if (row.querySelector(':scope > .stat-sign')) return;
  if (String(raw || '').indexOf('=') >= 0) { row.classList.add('stat-nosign'); return; }
  const eq = document.createElement('i');
  eq.className = 'stat-sign';
  eq.setAttribute('aria-hidden', 'true');
  eq.textContent = '=';
  row.insertBefore(eq, val);
}

/* Значение табло в запись для KaTeX. Числа и разделители оставляем как есть,
   проценты и градусы экранируем, юникодный минус переводим в математический. */
function statToTex(s) {
  return String(s)
    .replace(/−/g, '-')
    .replace(/ /g, '\\,')
    // Запятая между цифрами — десятичный разделитель, а не перечисление: без
    // скобок KaTeX ставит после неё пробел, и «3,67» читается как «3, 67».
    .replace(/(\d),(\d)/g, '$1{,}$2')
    .replace(/%/g, '\\%')
    .replace(/°/g, '^{\\circ}')
    .replace(/([A-Za-zА-Яа-я ]{2,})/g, (w) => '\\text{' + w + '}');
}

/* Строка табло, в которую значение не помещается (Б39, Б40).

   Строка «подпись слева, число справа» рассчитана ровно на ОДНО число.
   Значение, набранное KaTeX, — это inline-block с готовой шириной: сжиматься
   ему нечем, поэтому длинное значение выдавливало подпись и печаталось прямо
   поверх неё. Разница кеглей (12 против 16) делала кашу заметной, но причина
   была не в кегле.

   Два вида таких значений и два ответа:
     · СПИСОК величин («Q=3.67, ATC=11.35») — подпись сверху, каждая величина
       своей строкой снизу;
     · ФРАЗА («эластичный (|Ed|>1)») — своей строкой под подписью, обычным
       начертанием: это качественная характеристика, а не отсчёт прибора. */
/* Видимый текст значения, набранного KaTeX.

   Читать одни .katex-html нельзя: значение бывает СМЕШАННЫМ («единичная,
   $|E_d| = 1$», «$y^* = -18$ при $x^* = -3$»), и обычные слова между формулами
   так теряются — а именно по ним и видно, что перед нами фраза. Поэтому берём
   копию узла и выбрасываем из неё MathML: он и есть тот невидимый двойник,
   из-за которого textContent приходит утроенным. */
function katexVisibleText(val) {
  const clone = val.cloneNode(true);
  clone.querySelectorAll('.katex-mathml').forEach(e => e.remove());
  return clone.textContent || '';
}

function restatWide(row, lab, val, raw, own) {
  const pieces = statPieces(raw);
  const isList = pieces.length >= 2 && pieces.every(p => p.indexOf('=') >= 0);
  const isPhrase = /[А-Яа-яЁё]{3,}/.test(raw);
  /* Последняя проверка — по МЕСТУ, а не по виду значения. Бывает значение,
     которое не список и не фраза, а просто длинное («MR=MC @ Q = 60»):
     смотреть на его вид бесполезно, надо мерить. Больше двух третей строки —
     значит подписи не осталось места, и строку раскладываем стопкой. */
  if (!isList && !isPhrase && !statTooWide(row, lab, val)) return false;
  row.classList.add('stat-stack');
  /* Значение, набранное сценой, переносим КАК ЕСТЬ: разбирать готовый KaTeX
     обратно в текст значит потерять формулы внутри. Меняется только раскладка
     строки — подпись сверху, значение снизу. */
  if (own) { row.classList.add('stat-own');
    if (isPhrase && !isList) row.classList.add('stat-phrase'); return true; }
  val.innerHTML = '';
  if (isList) {
    pieces.forEach(p => {
      const line = document.createElement('span');
      line.className = 'stat-line';
      if (typeof katex !== 'undefined') {
        if (!katexInto(line, statToTex(p))) line.textContent = p;
      } else line.textContent = p;
      val.appendChild(line);
    });
    val.classList.add('stat-tex');
  } else {
    row.classList.add('stat-phrase');
    val.textContent = raw;
  }
  return true;
}

/* Помещаются ли подпись и значение в одну строку.

   Мерим НАПЕЧАТАННЫЙ текст (Range по содержимому), а не коробки: колонке
   подписи разрешено сжиматься до нуля, поэтому по коробкам наложения не видно
   вовсе — оно видно только по чернилам. И сравнивать надо СУММУ двух чернил с
   шириной строки: значение бывает и не самым длинным, а места всё равно нет,
   потому что длинная подпись. */
function statInkWidth(el) {
  try {
    const r = document.createRange(); r.selectNodeContents(el);
    const w = r.getBoundingClientRect().width;
    if (w > 0) return w;
  } catch (e) { /* ниже возьмём коробку */ }
  return el.getBoundingClientRect().width;
}
function statTooWide(row, lab, val) {
  const rw = row.getBoundingClientRect().width;
  if (!(rw > 0)) return false;
  // 20 px — зазор между колонками и место под знак равенства.
  return statInkWidth(lab) + statInkWidth(val) + 20 > rw;
}

/* Разбор значения на части по запятым и точкам с запятой ВЕРХНЕГО уровня.
   Внутри скобок не режем: «(|Ed|>1)» и «(P − ATC)·Q» это один кусок. */
function statPieces(raw) {
  const s = String(raw);
  const out = [];
  let depth = 0, cur = '';
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === '(' || ch === '[') depth++;
    else if (ch === ')' || ch === ']') depth = Math.max(0, depth - 1);
    /* Запятая между цифрами — ДЕСЯТИЧНЫЙ разделитель (Б15), а не граница
       списка: без этой оговорки «Q = 3,67, ATC = 11,35» разваливалось на
       четыре куска, и составное значение переставало опознаваться. */
    const decimal = (ch === ',') && /\d/.test(s[i - 1] || '') && /\d/.test(s[i + 1] || '');
    if ((ch === ',' || ch === ';') && depth === 0 && !decimal) { out.push(cur); cur = ''; continue; }
    cur += ch;
  }
  out.push(cur);
  return out.map(t => t.trim()).filter(Boolean);
}

/* ── Общий рендер математики в тексте интерфейса (Фаза 4) ─────────────
   Всё, что в тексте заключено в $…$, печатается формулой. Один проход по
   контейнеру после того, как он заполнен, поэтому новому блоку аналитики
   ничего дополнительно делать не нужно: достаточно поставить доллары.

   Правится только текст, разметка не трогается: обходим текстовые узлы и
   заменяем найденный кусок на span с формулой. Узлы, уже прошедшие обработку,
   помечаются, чтобы статичные подсказки не разбирались заново на каждом кадре. */
/* ⚠️ п. 48. `$MC$` KaTeX набирает как ПРОИЗВЕДЕНИЕ переменных M·C: курсив
   с зазором, и на экране это читается как «M с индексом C». Аббревиатура
   величины (MC, ATC, AVC, CS, PS, DWL, TP, MP, AP) — ОДНО имя, и набирается
   прямым шрифтом. Тот же разбор уже стоит на холсте: qtyParts не режет на
   буквы то, что целиком заглавное.
   Правим в единственной точке печати формул панели, а не в 244 строках сцен,
   где эти доллары написаны. Имена команд LaTeX не трогаем, содержимое
   \text{…} и \mathrm{…} тоже: там прямой шрифт уже задан. */
function texAbbrev(src) {
  return String(src).replace(
    /(\\(?:text|mathrm|mathbf|operatorname)\s*\{[^{}]*\})|(\\[a-zA-Z]+)|([A-Z]{2,})/g,
    (all, keep, cmd, abbr) => keep || cmd || ('\\mathrm{' + abbr + '}'));
}

function renderMathIn(root) {
  if (!root || typeof katex === 'undefined') return;
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => {
      if (!n.nodeValue || n.nodeValue.indexOf('$') < 0) return NodeFilter.FILTER_REJECT;
      const p = n.parentElement;
      if (!p || p.closest('.katex, script, style, textarea, input')) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const jobs = [];
  let n;
  while ((n = walk.nextNode())) jobs.push(n);
  jobs.forEach(node => {
    const parts = String(node.nodeValue).split(/\$([^$]+)\$/);
    if (parts.length < 3) return;
    const frag = document.createDocumentFragment();
    parts.forEach((piece, i) => {
      if (i % 2 === 0) { if (piece) frag.appendChild(document.createTextNode(piece)); return; }
      const span = document.createElement('span');
      span.className = 'tex';
      if (!katexInto(span, texAbbrev(piece))) span.textContent = piece;
      frag.appendChild(span);
    });
    node.parentNode.replaceChild(frag, node);
  });
}

/* ---------------------------------------------------------------------
   ЛЕГЕНДА ЗАКРАШЕННЫХ ОБЛАСТЕЙ
   Цвет площади сам по себе ничего не говорит: синее пятно над ценой это
   излишек покупателя, серое между кривыми это потери общества, и без
   подписи их не различить.
   Сцены не ведут никакого реестра: каждая заливка помечена при отрисовке
   атрибутом data-legend, а легенда просто собирает то, что уже нарисовано.
   Значит, новая сцена получает легенду бесплатно, достаточно пометить
   заливку. Рисуется в том же SVG, поэтому попадает и в PNG, и в .tex.
   Место: верхнее поле под заголовком — там никогда не проходят кривые.
   --------------------------------------------------------------------- */
/* ── Цвета закрашенных областей (Фаза 8) ──────────────────────────────
   Каждая заливка при отрисовке помечена data-legend. Отдельного пикера у
   каждой из сорока с лишним заливок нет и не надо: после отрисовки один
   проход перекрашивает те, у которых пользователь выбрал свой цвет. */
function areaKey(name) { return String(name || '').trim(); }

/* Настоящие подстрочные цифры (Н27). Имя площади уходит и в легенду на холст,
   и в подпись рядом с кривой, поэтому нужен готовый символ, а не разметка:
   в SVG вложенный <tspan> пришлось бы тащить через все места сразу. */
function subDigits(n) {
  const S = '₀₁₂₃₄₅₆₇₈₉';
  return String(n).replace(/\d/g, (d) => S[+d]);
}

function applyAreaColors() {
  const map = STATE.areaColor || {};
  svg.selectAll('[data-legend]').each(function () {
    const k = areaKey(this.getAttribute('data-legend'));
    const c = map[k];
    if (c) this.setAttribute('fill', c);
  });
}

// Какие области сейчас на графике: [{key, color, opacity, value}] без повторов.
function currentAreas() {
  const seen = [], by = {};
  svg.selectAll('[data-legend]').each(function () {
    const k = areaKey(this.getAttribute('data-legend'));
    if (!k || by[k]) return;
    by[k] = 1;
    seen.push({ key: k, color: this.getAttribute('fill') || COL.ink,
                opacity: +this.getAttribute('opacity') || 0.2,
                value: areaOfPathEl(this), el: this });
  });
  return seen;
}

/* Площадь закрашенной фигуры В ЕДИНИЦАХ ЗАДАЧИ (Свх-5). Сцена рисует область
   готовым путём в пикселях и число нигде не хранит, поэтому считаем прямо по
   нарисованному: разбираем путь на точки, переводим их обратно через шкалы и
   берём формулу площади многоугольника. Способ общий, поэтому число появляется
   у ЛЮБОЙ области любой сцены, и заводить реестр на каждый сюжет не нужно. */
function areaOfPathEl(el) {
  try {
    const d = el.getAttribute('d') || '';
    if (!d) return null;
    const nums = d.match(/-?\d+(?:\.\d+)?(?:e-?\d+)?/gi);
    if (!nums || nums.length < 6) return null;
    const { mx, my } = mainScales();
    const pts = [];
    for (let i = 0; i + 1 < nums.length; i += 2) {
      const x = mx.invert(+nums[i]), y = my.invert(+nums[i + 1]);
      if (isFinite(x) && isFinite(y)) pts.push([x, y]);
    }
    if (pts.length < 3) return null;
    let s = 0;
    for (let i = 0, n = pts.length; i < n; i++) {
      const a = pts[i], b = pts[(i + 1) % n];
      s += a[0] * b[1] - b[0] * a[1];
    }
    const v = Math.abs(s) / 2;
    return isFinite(v) ? v : null;
  } catch (e) { return null; }
}

/* Короткие обозначения для легенды: на графике место дорого, а CS и DWL
   школьник читает быстрее любой фразы. Полное название остаётся в подсказке. */
const AREA_SHORT = {
  'Излишек покупателя (CS)': 'CS',
  // Коридор возможных цен при квоте: полное имя вдвое шире всей легенды.
  'Коридор возможных цен': 'Коридор',
  'Излишек продавца (PS)': 'PS',
  'Излишек производителя (TR - VC)': 'PS',
  /* ⚠️ п. 41. НА РЫНКЕ ТРУДА ПРОДАЮТ РАБОТНИКИ, А ПОКУПАЮТ ФИРМЫ.
     Обозначения стояли наоборот, и получалось противоречие между сценами:
     заливка честно берёт цвет ОГРАНИЧИВАЮЩЕЙ кривой (излишек под D — синий,
     над S — оранжевый), а легенда называла синее пятно «PS», оранжевое «CS».
     На рынке благ «CS синий, PS оранжевый», в монопсонии выходило наоборот.
     Правило одно: CS живёт под кривой спроса и потому синий, PS над кривой
     предложения и потому оранжевый; кто в модели покупатель, а кто продавец,
     на цвет не влияет. */
  'Излишек работников': 'PS',
  'Излишек фирм': 'CS',
  'Излишек фирмы: весь излишек рынка': 'PS',
  'Переменные издержки (VC)': 'VC',
  'Потери общества (DWL)': 'DWL',
  'Потери от внешнего эффекта (DWL)': 'DWL',
  'Сбор бюджета': 'Tx',
  'Поступления бюджета': 'Tx',
  'Доход бюджета': 'Tx',
  'Расход бюджета': 'GS',
  'Рента квоты': 'R',
  /* «Достижимые наборы» короткого обозначения не имеет: «Дост.» это не
     сокращение величины, а обрубок слова (п. 45). Пишем целиком. */
  'Диапазон возможных зарплат': 'W',
  'Площадь': 'S',
};
/* ⚠️ ОБРУБОК ПО ЧИСЛУ ЗНАКОВ ОТМЕНЁН (п. 45).
   Осмысленное сокращение — это CS, PS, DWL, Tx: их школьник читает быстрее
   фразы, и они входят в реестр обозначений. А «Прибыль ф…» и «Дост.» это не
   сокращения, а обрезанные слова: подпись перестаёт читаться, а места экономит
   меньше, чем стоит потеря смысла. Незнакомое название печатается целиком,
   коробка легенды просто становится шире — её ширина считается по фактически
   измеренному тексту, а не по числу знаков. */
function areaShort(name) {
  if (AREA_SHORT[name]) return AREA_SHORT[name];
  const m = /\(([^)]{1,5})\)\s*$/.exec(name);      // «… (CS)» → CS
  return m ? m[1] : name;
}

/* Легенда: столбик у правого нижнего угла поля графика. Раньше она лежала
   поперёк верхнего поля и спорила с заголовком; внизу справа под кривыми
   почти всегда пусто, и читать её удобнее. */
function drawLegend() {
  if (!STATE.showLegend) return;
  const seen = currentAreas();
  if (!seen.length) return;
  const m = CONFIG.margin;
  /* А27 · А59. Легенда кричала громче графика: кегль 18.7 против 10 у делений
     осей и 14 у подписей кривых, коробка 75×112 при поле 262×344 — девять
     процентов площади, поверх линии S + t и поверх подписи координат.

     Кегль — ступень «обычный», не крупнее подписей значений. Размер числом
     здесь больше не пишется: раньше локальная переменная с именем FS ещё и
     перекрывала общую шкалу кеглей.

     Угол выбирается СВОБОДНЫЙ: считаем, сколько нарисованных кривых попадает
     в коробку в каждом из четырёх углов, и садимся туда, где их меньше всего.
     Подложка не залезает на конец оси — то же правило про отступ, что и в П33. */
  const SW = 12, GAP = 6, LH = 18, PAD = 8;
  const fsz = FS.base;
  const labels = seen.map(e => areaShort(e.key));
  // Ширину меряет браузер: оценка «знаков × 0,62 кегля» врала, и подпись
  // выходила за подложку (та же беда, что была у полей холста).
  const wide = Math.max.apply(null, labels.map(t => measureText(t, fsz, 600)));
  const boxW = SW + GAP + wide + 2 * PAD;
  const boxH = seen.length * LH + 2 * PAD;
  const { x, y } = legendCorner(boxW, boxH);
  const g = svg.append('g').attr('class', 'legend').style('pointer-events', 'none');
  g.append('rect').attr('x', x).attr('y', y).attr('width', boxW).attr('height', boxH)
    .attr('rx', 6).attr('fill', COL.halo).attr('opacity', 0.82)
    .attr('stroke', COL.grid).attr('stroke-width', 1);
  seen.forEach((e, i) => {
    const cy = y + PAD + i * LH;
    g.append('rect')
      .attr('x', x + PAD).attr('y', cy + 3).attr('width', SW).attr('height', SW)
      .attr('rx', 3).attr('fill', e.color).attr('opacity', Math.max(0.35, e.opacity * 2))
      .attr('stroke', e.color).attr('stroke-opacity', 0.55).attr('stroke-width', 1);
    const t = g.append('text')
      .attr('x', x + PAD + SW + GAP).attr('y', cy + SW * 0.95)
      .attr('font-size', fsz).attr('font-weight', 600).attr('fill', COL.ink)
      .text(labels[i]);
    /* Полное название аббревиатуры остаётся узлом `title` внутри SVG, и это
       не та подсказка, о которой говорит правило 18: строка легенды ничего не
       делает по нажатию, а `title` у фигуры это её ИМЯ — им же её называет
       чтец с экрана. Заменять его всплывающей плашкой значило бы отобрать
       имя и ничего не дать взамен. */
    t.append('title').text(e.key);
  });
}

/* Свободный угол под легенду (А59). Кривые уже нарисованы, поэтому просто
   считаем, сколько их точек попадает в коробку в каждом из четырёх углов, и
   садимся в самый пустой. При равенстве побеждает правый нижний — привычное
   место, к которому глаз уже приучен. */
/* ⚠️ ЕДИНАЯ РАСКЛАДКА ПЛАВАЮЩЕГО (механизм 3.3; п. 38, 39, 40, 45).

   Над холстом висят HTML-блоки: стопка кнопок масштаба с гаечным ключом
   (`.graph-tools`, правый верхний угол) и кнопка площади по точкам. Они лежат
   в обёртке `#graph-wrap`, а не внутри SVG, поэтому холст про них не знал
   ВООБЩЕ. Отсюда 124 наложения из замера: легенда садилась ровно под кнопки
   («DWL» читалось как «DW»), туда же уезжали подписи кривых.

   Прямоугольники собираются ОДИН раз и отдаются всем, кому нужно свободное
   место: выбору места легенды и разведению подписей. Второго списка «кто над
   холстом висит» не заводим — он разъехался бы с разметкой. */
function floatRects() {
  const node = svg.node();
  const wrap = document.getElementById('graph-wrap');
  if (!node || !wrap) return [];
  const box = node.getBoundingClientRect();
  const out = [];
  wrap.querySelectorAll('.graph-tools, .cv-mode, .wrench, .graph-float').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.hasAttribute('hidden')) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    out.push({ x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height,
               left: r.left, top: r.top, right: r.right, bottom: r.bottom });
  });
  return out;
}

function legendCorner(boxW, boxH) {
  const m = CONFIG.margin, EDGE = 8;
  /* Б47. Место только СПРАВА. Слева у графика ось значений с цифрами делений и
     подписями величин, и легенда, севшая туда, всякий раз спорит с ними, даже
     когда кривых в том углу нет.

     Но одними двумя углами обойтись нельзя: свободного угла может не оказаться
     вовсе, а требование «никого не накрывать» остаётся. Поэтому легенда
     скользит вдоль правого края — от верхнего угла к нижнему, — и садится
     туда, где занято меньше всего. Углы стоят первыми, чтобы при прочих
     равных выбирался угол. */
  const xRight = (W - m.right) - boxW - EDGE;
  const yTop = m.top + EDGE, yBot = (H - m.bottom) - boxH - 26;
  /* ⚠️ ПЕРВЫМ ИДЁТ НИЖНИЙ УГОЛ, А НЕ ВЕРХНИЙ. Верхний правый занят стопкой
     кнопок масштаба — постоянно, во всех сценах. Порядок кандидатов закреплён,
     и место выбирается ПЕРВОЕ подходящее, а не «лучшее» из всех: канон просит
     устойчивое место (п. 40), а «лучшее» пересчитывалось на каждое движение
     кривой, и легенда прыгала снизу вверх сама собой. */
  const corners = [{ x: xRight, y: yBot }, { x: xRight, y: yTop }];
  for (let i = 1; i < 8; i++) corners.push({ x: xRight, y: yTop + (yBot - yTop) * i / 8 });
  // Точки нарисованных кривых в пикселях холста, разреженно: для выбора угла
  // этого хватает, обходить каждый узел каждой кривой незачем. Подписи тоже
  // учитываем: иначе легенда садилась ровно на ярлык кривой (замер А60 ловил
  // пару «D» и «DWL»).
  const pts = [];
  const node = svg.node();
  if (node) {
    const box = node.getBoundingClientRect();
    node.querySelectorAll('text').forEach(t => {
      const r = t.getBoundingClientRect();
      if (r.width < 0.5) return;
      pts.push([r.left - box.left + r.width / 2, r.top - box.top + r.height / 2]);
    });
    node.querySelectorAll('path').forEach(p => {
      const cs = getComputedStyle(p);
      if (!cs.stroke || cs.stroke === 'none' || parseFloat(cs.strokeWidth) < 1) return;
      let len = 0;
      try { len = p.getTotalLength(); } catch (err) { return; }
      if (!(len > 0) || len > 1e5) return;
      for (let i = 0; i <= 24; i++) {
        try { const q = p.getPointAtLength(len * i / 24); pts.push([q.x, q.y]); } catch (err) { return; }
      }
    });
  }
  /* Плавающие блоки — ЗАПРЕТ, а не штраф: под кнопками легенду не прочитать
     никак, сколько бы свободного места вокруг ни было. */
  const blocked = floatRects();
  const clash = (c) => blocked.some(b =>
    c.x < b.x + b.w && b.x < c.x + boxW && c.y < b.y + b.h && b.y < c.y + boxH);
  const cost = corners.map(c => {
    if (clash(c)) return Infinity;
    let hits = 0;
    pts.forEach(([px, py]) => {
      if (px >= c.x && px <= c.x + boxW && py >= c.y && py <= c.y + boxH) hits++;
    });
    return hits;
  });
  // Прежнее место остаётся за легендой, пока оно свободно (п. 40).
  const prev = STATE.legendSpot;
  if (prev != null && corners[prev] && cost[prev] === 0) return corners[prev];
  let best = 0;
  for (let i = 1; i < corners.length; i++) if (cost[i] < cost[best]) best = i;
  STATE.legendSpot = best;
  return corners[best];
}


/* ── Точки пересечения (Фаза 6, дополнено) ────────────────────────────
   Считаются сами: кривые друг с другом И каждая кривая с осями координат.
   Показываются тускло; наведение или щелчок делает точку яркой и подписывает
   координаты, курсор ушёл — снова тускнеет. */
/* Окно, в котором сцена РЕАЛЬНО рисует. Берём у главных шкал, а не у CONFIG:
   в «Математике» и в сценах с двумя панелями окно своё, и всё, что считалось
   от CONFIG, искалось не там, где нарисованы кривые (отсюда терялись корни
   в отрицательной части плана). Нижние границы режем по правилу первой
   четверти — тем же econLo, что и обрезка кривых: в экономической сцене
   пересечений и корней ниже нуля не бывает независимо от галочки. */
function viewWindow(panelId) {
  const { mx, my } = mainScales(panelId);
  const [dx0, dx1] = mx.domain(), [dy0, dy1] = my.domain();
  const [px0, px1] = mx.range();
  return {
    x0: econLo(dx0), x1: dx1,
    y0: econLo(dy0), y1: dy1,
    px: Math.abs(px1 - px0),
  };
}

// Как назвать оси в подписи ключевой точки: в «Математике» это x и y.
function axisWords() {
  if (STATE.mode === 'math') return ['ось x', 'ось y'];
  if (STATE.mode === 'ppf') return ['ось X', 'ось Y'];
  return ['ось Q', 'ось P'];
}

function crossPoints(panelId) {
  const t = snapTargets(panelId);
  if (!t.length) return [];
  const w = viewWindow(panelId);
  const lo0 = w.x0, hi = w.x1, yLo = w.y0, yHi = w.y1;
  if (!(hi > lo0) || !isFinite(hi - lo0)) return [];
  const lo = lo0 + (hi - lo0) * 1e-6;
  // Узлов столько, чтобы шаг был около двух пикселей: жёсткие 240 в широком
  // окне пропускали корни, а в узком считались впустую.
  const N = Math.max(240, Math.min(900, Math.round(w.px / 2)));
  const out = [];
  const dupTol = (hi - lo) * 1e-3, dupTolY = (yHi - yLo) * 1e-3;
  const [xAxis, yAxis] = axisWords();
  const push = (x, y, a, b) => {
    if (!isFinite(x) || !isFinite(y)) return;
    if (x < lo0 - 1e-9 || x > hi + 1e-9 || y < yLo - 1e-9 || y > yHi + 1e-9) return;
    // Одну и ту же точку три кривые дают трижды — рядом стоящие сливаем.
    if (out.some(o => Math.abs(o.x - x) < dupTol && Math.abs(o.y - y) < dupTolY)) return;
    out.push({ x, y, a, b });
  };
  // Считаем каждую кривую по сетке ОДИН раз и переиспользуем во всех парах:
  // иначе при большем числе узлов расчёт кривых умножался бы на число пар.
  const xs = new Array(N + 1), vals = [];
  for (let i = 0; i <= N; i++) xs[i] = lo + (hi - lo) * i / N;
  t.forEach(c => { const arr = new Array(N + 1); for (let i = 0; i <= N; i++) arr[i] = c.f(xs[i]); vals.push(arr); });

  // Совпадение двух кривых на целом отрезке — это НЕ пересечение. Раньше край
  // такого отрезка выдавался за точку, и на экране появлялся узел расчётной
  // сетки: у min(f, g) кривая Z совпадает с f слева и с g справа, и обе
  // «точки» были просто числами вида 1.25 и 1.6667 — шагом сетки.
  const zTol = Math.max(1e-12, (yHi - yLo) * 1e-9);
  for (let a = 0; a < t.length; a++) {
    for (let b = a + 1; b < t.length; b++) {
      const va = vals[a], vb = vals[b];
      const gs = new Array(N + 1), zero = new Array(N + 1);
      for (let i = 0; i <= N; i++) {
        const p = va[i], q = vb[i];
        gs[i] = (isNaN(p) || isNaN(q)) ? NaN : p - q;
        zero[i] = !isNaN(gs[i]) && Math.abs(gs[i]) <= zTol;
      }
      const runAt = (i) => {                 // длина участка совпадения вокруг узла
        let n = 1;
        for (let k = i - 1; k >= 0 && zero[k]; k--) n++;
        for (let k = i + 1; k <= N && zero[k]; k++) n++;
        return n;
      };
      const gf = (x) => { const p = t[a].f(x), q = t[b].f(x); return (isNaN(p) || isNaN(q)) ? NaN : p - q; };
      for (let i = 1; i <= N && out.length < 60; i++) {
        const p = gs[i - 1], c = gs[i];
        if (isNaN(p) || isNaN(c)) continue;
        if (zero[i - 1] && zero[i]) continue;                    // идём внутри совпадения
        if (zero[i - 1] || zero[i]) {                            // касание или край совпадения
          const j = zero[i - 1] ? i - 1 : i;
          if (runAt(j) > 1) continue;                            // край — не точка
          push(xs[j], va[j], t[a].name, t[b].name);
          continue;
        }
        if (p * c < 0) { const r = bisect(gf, xs[i - 1], xs[i]); push(r, t[a].f(r), t[a].name, t[b].name); }
      }
    }
  }
  // Пересечения с осями: где кривая садится на ось X (y = 0) и где начинается
  // на оси Y (x = 0). В экономике это выпуск при нулевой цене и цена отсечения.
  t.forEach((c, k) => {
    const arr = vals[k];
    for (let i = 1; i <= N && out.length < 60; i++) {
      const p = arr[i - 1], v = arr[i];
      if (isNaN(p) || isNaN(v)) continue;
      if (p === 0) push(xs[i - 1], 0, c.name, xAxis);
      else if (v === 0) push(xs[i], 0, c.name, xAxis);
      else if (p * v < 0) { const r = bisect((z) => c.f(z), xs[i - 1], xs[i]); push(r, 0, c.name, xAxis); }
    }
    if (lo0 <= 1e-9 && hi >= -1e-9) push(0, c.f(0), c.name, yAxis);
  });
  return out;
}

/* Ключевые точки на графике: пересечения кривых между собой и с осями.
   По умолчанию тусклые серые, наведение показывает координаты, щелчок
   закрепляет их и гасит повторным нажатием.

   Важно: наведение НЕ перерисовывает холст. Раньше pointerenter звал redrawAll,
   тот сносил весь SVG вместе с кружком под курсором, и pointerleave с
   удалённого элемента уже не приходил — точка оставалась гореть навсегда.
   Теперь меняем только атрибуты самого кружка и подпись рядом с ним. */
/* ── Особые точки сцены (Фаза 7) ──────────────────────────────────────
   Раньше они считались в трёх местах и не знали друг о друге: crossPoints —
   пересечения кривых и с осями, mathAnalyse — экстремумы и только в
   «Математике», snapTargets — сами кривые. Доводке вершины нужен один список
   с человеческими именами, поэтому он здесь.

   Экстремумы ищем во ВСЕХ сценах, а не только в математических: минимум
   средних издержек и вершина кривой Лаффера ничем не отличаются от вершины
   параболы. Границы — у шкал сцены (viewWindow), как и всё остальное.

   Список кэшируется до следующей перерисовки: его дёргает движение мыши,
   а пересчёт по всем кривым стоит несколько тысяч вычислений. */
/* ⚠️ КЭШ КЛЮЧЕВЫХ ТОЧЕК — ПО ПАНЕЛЯМ, А НЕ ОДИН НА СЦЕНУ.
   Панель под курсором меняется БЕЗ перерисовки (человек просто ведёт мышь),
   а сбрасывается кэш только на перерисовке. Один общий кэш отдавал бы соседней
   панели точки той, над которой курсор был раньше. */
let _keyPtsCache = {};
function invalidateKeyTargets() { _keyPtsCache = {}; }

// Изломы кривой: там, где наклон меняется скачком (кусочная запись, min и max).
function kinksOf(f, lo, hi) {
  const out = [];
  if (!(hi > lo)) return out;
  const N = 240, h = (hi - lo) / (N * 4);
  const slope = (x) => {
    const a = f(x + h), b = f(x - h);
    return (isFinite(a) && isFinite(b)) ? (a - b) / (2 * h) : NaN;
  };
  const xs = [], ss = [], mag = [];
  for (let i = 0; i <= N; i++) {
    const x = lo + (hi - lo) * i / N, s = slope(x);
    xs.push(x); ss.push(s);
    if (isFinite(s)) mag.push(Math.abs(s));
  }
  if (mag.length < 5) return out;
  mag.sort((a, b) => a - b);
  const med = mag[Math.floor(mag.length / 2)] || 1;
  // Порог берём от типичного наклона: иначе он зависел бы от единиц измерения.
  const jump = Math.max(med * 0.6, 1e-9);
  /* Скачок наклона ищем через ОДИН узел, а не между соседними.
     Производная считается центральной разностью с шагом h, поэтому у самого
     излома есть узел, где окно ±h лежит по обе стороны от него: наклон там
     смешанный, и весь скачок делится на две половинки, каждая ниже порога.
     На «Q < 40 ? 100 - Q : 80 - 0.5*Q» так и было — 0.264 и 0.236 при пороге
     0.3, и излом не находился вовсе. Смотрим ss[i+1] против ss[i-1]: смазанный
     узел остаётся посередине и в сравнение не попадает. Чтобы гладкая кривая
     не сошла за излом, требуем ещё и «полки» с обеих сторон. */
  for (let i = 2; i <= N - 2; i++) {
    const l = ss[i - 1], r = ss[i + 1];
    if (!isFinite(l) || !isFinite(r)) continue;
    if (Math.abs(r - l) <= jump) continue;
    const lFlat = isFinite(ss[i - 2]) && Math.abs(l - ss[i - 2]) < jump / 3;
    const rFlat = isFinite(ss[i + 2]) && Math.abs(r - ss[i + 2]) < jump / 3;
    if (!lFlat || !rFlat) continue;
    // Точное место излома — пересечение продолжений левой и правой ветвей.
    // Для кусочно-линейной записи это ровно точка стыка.
    const xL = xs[i - 2], xR = xs[i + 2];
    const yL = f(xL), yR = f(xR);
    let xr = xs[i];
    if (isFinite(yL) && isFinite(yR) && Math.abs(l - r) > 1e-12) {
      const cand = (yR - yL + l * xL - r * xR) / (l - r);
      if (isFinite(cand) && cand >= xs[i - 2] && cand <= xs[i + 2]) xr = cand;
    }
    if (!out.some(v => Math.abs(v - xr) < (hi - lo) * 0.01)) out.push(xr);
  }
  return out;
}

function keyTargets(panelId) {
  const ap = activePanel();
  const pid = (panelId != null) ? panelId : (ap ? ap.id : '');
  const ck = String(pid);
  if (_keyPtsCache[ck]) return _keyPtsCache[ck];
  const out = [];
  const w = viewWindow(panelId);
  const dx = (w.x1 - w.x0) * 1e-3, dy = (w.y1 - w.y0) * 1e-3;
  /* Вид точки нужен отрисовке (П36–П38): излом рисуется по-особому, у
     остальных вид одинаковый. Перегибы сюда не попадают и не попадут:
     договорились их ключевыми точками не считать. */
  /* ⚠️ У КАЖДОЙ ТОЧКИ ЕСТЬ ХОЗЯЕВА — КРИВЫЕ, КОТОРЫМ ОНА ПРИНАДЛЕЖИТ.

     Без этого списка нельзя ответить на вопрос фазы 3: «какие точки зажечь,
     когда щёлкнули по этой кривой». Хозяев может быть двое — точка пересечения
     принадлежит обеим кривым и обязана загораться при щелчке по любой из них
     (решение владельца). У экстремума и излома хозяин один. У начала координат
     хозяев нет вовсе: это пересечение ОСЕЙ, а не кривой, и загораться вместе с
     кривой ему не за что.

     Хозяин записывается ИМЕНЕМ, тем же, что печатает snapTargets: по имени же
     сверяет взведение, и второго способа отождествить кривую заводить нельзя. */
  /* ⚠️ ДУБЛЬ СХЛОПЫВАЕТСЯ СО СЛИЯНИЕМ ХОЗЯЕВ, А НЕ МОЛЧА РОНЯЕТСЯ.
     Одна и та же точка приходит сюда с разных сторон: равновесие E — и как
     пересечение D и S, и как нарисованная сценой точка; излом суммарного
     спроса в наборе владельца стоит ровно там же, где пересечение двух других
     кривых. Прежний push просто выходил на дубле — и излом ТЕРЯЛ хозяина, то
     есть переставал загораться при щелчке по своей кривой (замер: излом
     рыночного спроса (40; 60) не загорался вовсе). Имя у точки остаётся
     первое — оно содержательнее; хозяева складываются. */
  const push = (x, y, name, kind, owners) => {
    if (!isFinite(x) || !isFinite(y)) return;
    if (x < w.x0 - 1e-9 || x > w.x1 + 1e-9 || y < w.y0 - 1e-9 || y > w.y1 + 1e-9) return;
    const same = out.find(o => Math.abs(o.x - x) < dx && Math.abs(o.y - y) < dy);
    if (same) {
      (owners || []).forEach(nm => { if (!same.owners.includes(nm)) same.owners.push(nm); });
      return same;
    }
    const rec = { x, y, name, kind: kind || 'cross', owners: (owners || []).slice() };
    out.push(rec);
    return rec;
  };
  const curveNames = new Set(snapTargets(panelId).map(t => t.name));
  /* Готовые пересечения берём с полки, только если их считали ДЛЯ ЭТОЙ ЖЕ
     панели: у соседней они совсем другие. */
  const ready = (STATE.crosses && STATE.crosses.length && STATE.crossesPanel === ck)
    ? STATE.crosses : crossPoints(panelId);
  ready.forEach(p => {
    // Второй участник бывает осью, а не кривой: ось в хозяева не идёт.
    const own = [p.a, p.b].filter(nm => curveNames.has(nm));
    push(p.x, p.y, /^ось /.test(p.b)
      ? ('пересечение с ' + p.b.replace('ось ', 'осью '))
      : ('пересечение ' + p.a + ' и ' + p.b), 'cross', own);
  });
  /* Н40: начало координат тоже ключевая точка. Добавляем ПОСЛЕ пересечений:
     если кривая и так пересекает ось в нуле, это одна и та же точка, и имя у
     неё должно остаться содержательным, а не превратиться в «начало координат».
     Сам push отсеет повтор по координатам. */
  /* ── (б) и (в): точки, которые НАРИСОВАЛА сама сцена, и их проекции ──
     Читаем метки с холста (`data-key-point`), а не считаем правило второй раз:
     сцена уже отрисована, и на ней стоит ровно то, что человек видит.
     Хозяева — кривые, на которых точка лежит: равновесие принадлежит и спросу,
     и предложению, и загорается при щелчке по любой из них. */
  const drawn = [];
  try {
    svg.selectAll('[data-key-point]').each(function () {
      const pl = this.getAttribute('data-kp-panel') || '';
      if (pl && ck && pl !== ck) return;
      const x = +this.getAttribute('data-kp-x'), y = +this.getAttribute('data-kp-y');
      if (!isFinite(x) || !isFinite(y)) return;
      drawn.push({ x, y, name: this.getAttribute('data-key-point') || 'отмеченная точка' });
    });
  } catch (e) { /* холста ещё нет — нарисованных точек тоже */ }
  const targets = snapTargets(panelId);
  const onCurves = (x, y) => targets.filter(t => {
    let v; try { v = t.f(x); } catch (e) { return false; }
    return isFinite(v) && Math.abs(v - y) <= Math.max(dy * 8, (w.y1 - w.y0) * 1e-3);
  }).map(t => t.name);
  const [xAxisNm, yAxisNm] = axisWords();
  drawn.forEach(p => {
    const own = onCurves(p.x, p.y);
    push(p.x, p.y, p.name, 'drawn', own);
    // Проекции на обе оси: для равновесия (50; 50) это (0; 50) и (50; 0).
    push(0, p.y, 'проекция ' + p.name + ' на ' + yAxisNm.replace('ось ', 'ось '), 'drawn', own);
    push(p.x, 0, 'проекция ' + p.name + ' на ' + xAxisNm.replace('ось ', 'ось '), 'drawn', own);
  });
  push(0, 0, 'начало координат', 'cross', []);
  if (!(w.x1 > w.x0)) { _keyPtsCache[ck] = out; return out; }
  const lo = w.x0 + (w.x1 - w.x0) * 1e-4, hi = w.x1;
  const h = (w.x1 - w.x0) * 1e-4;
  const h2 = Math.max(h * 20, (w.x1 - w.x0) * 1e-3);
  snapTargets(panelId).forEach(t => {
    /* У постоянной кривой (горизонтальная MC, потолок цены, мировая цена)
       производная равна нулю ВЕЗДЕ, и экстремумом объявлялся каждый узел сетки:
       на холсте вдоль такой линии выстраивались сотни серых кружков.
       У прямой линии экстремумов нет по определению, поэтому просто пропускаем
       поиск, если функция на всём окне постоянна. */
    let flat = true;
    // Кривая сцены может бросить на негодном аргументе: без обёртки такой
    // случай обрывал бы весь обход ключевых точек.
    try {
      const y0f = t.f(lo);
      for (let i = 1; i <= 12 && flat; i++) {
        const v = t.f(lo + (hi - lo) * i / 12);
        if (!isFinite(v) || !isFinite(y0f) || Math.abs(v - y0f) > 1e-9 * (1 + Math.abs(y0f))) flat = false;
      }
    } catch (e) { flat = false; }
    let ext = [];
    if (!flat) {
      try { ext = rootsOf((x) => dNum(t.f, x, h), lo, hi, 400); } catch (e) { ext = []; }
    }
    ext.forEach(x => {
      const y = t.f(x);
      if (!isFinite(y)) return;
      const s = d2Num(t.f, x, h2);
      const kind = (s > 0) ? 'минимум ' : (s < 0 ? 'максимум ' : 'плато ');
      push(x, y, kind + t.name, 'extremum', [t.name]);
    });
    /* Излом, совпавший с уже найденным пересечением, не добавляем: у Z = min(f, g)
       ветвь переключается ровно там, где кривые пересекаются, а пересечение и
       посчитано точнее (бисекцией), и названо понятнее.

       ⚠️ СОВПАДЕНИЕ ПРОВЕРЯЕТСЯ ПО ОБЕИМ КООРДИНАТАМ. Раньше сверялся только X,
       и излом гасила ЛЮБАЯ точка с тем же количеством — даже лежащая на другой
       высоте, то есть совсем другая точка. Замер 24.08 в сюжете сложения: излом
       рыночного предложения (20; 20) пропадал из списка, потому что рядом стояло
       пересечение двух групп в (20; 40). Один и тот же Q, разные точки. */
    /* ⚠️ Излом, совпавший с уже найденной точкой, НЕ выбрасывается: он отдаёт
       ей своего хозяина (см. push выше). Раньше здесь стоял выход, и излом
       суммарного спроса пропадал из списка целиком — вместе с возможностью
       зажечь его щелчком по самой суммарной кривой. */
    const nearX = (w.x1 - w.x0) * 0.02, nearY = (w.y1 - w.y0) * 0.02;
    kinksOf(t.f, lo, hi).forEach(x => {
      const y = t.f(x);
      if (!isFinite(y)) return;
      const near = out.find(o => Math.abs(o.x - x) < nearX && Math.abs(o.y - y) < nearY);
      if (near) { if (!near.owners.includes(t.name)) near.owners.push(t.name); return; }
      push(x, y, 'излом ' + t.name, 'kink', [t.name]);
    });
  });
  _keyPtsCache[ck] = out;
  return out;
}

/* Куда сядет вершина площади. Рядом с особой точкой прыгает точно в неё,
   иначе садится просто на ближайшую кривую. Радиус у особой точки чуть
   больше, чтобы попадать в неё было легче, чем промахнуться мимо. */
// В ключевую точку попасть должно быть заметно легче, чем просто в кривую (П42).
const KEY_SNAP_PX = 22;
/* Запас попадания по кружку ключевой точки. Больше половины ширины полосы
   кривой (16 px): иначе зазора между «взял точку» и «взял кривую» нет вовсе. */
const KEY_HIT_PX = 11;
/* п. 33. ВОЗМОЖНОСТЬ, О КОТОРОЙ ЗНАЕТ ТОЛЬКО НАВЕДЕНИЕ МЫШИ, НЕ СУЩЕСТВУЕТ.

   «Двойной щелчок, чтобы переименовать», «Добавить в список точек» и
   «Потяните, чтобы перенести» жили внутри SVG узлами `title`, то есть в
   подсказке браузера. На сенсорном экране её нет вовсе, с клавиатуры не
   открыть, оформлению не поддаётся — узнать о возможности можно было только
   случайно, мышью.

   ⚠️ ЗАМЕНИТЬ ИХ ВСПЛЫВАЮЩЕЙ ПЛАШКОЙ НЕ ВЫШЛО, И ЭТО ПРАВИЛЬНО. Плашка
   всплывает ровно там, где рука ведёт указатель, перехватывает его и мешает
   тому самому действию, ради которого показана: подпись максимума с плашкой
   перестала открываться двойным щелчком совсем. Нашёл браузер; ни один
   разбор исходников такого не видит.

   Поэтому возможности названы ТАМ, ГДЕ ИМИ УПРАВЛЯЮТ: переименование и
   значок закрепки — в подсказке блока «Точки на графике», перенос названия
   графика — рядом с полем этого названия в меню плоскости. Узел `title` у
   аббревиатуры легенды оставлен: это не подсказка, а ИМЯ фигуры.            */

function snapVertexAt(px, py) {
  // Панель решает ПИКСЕЛЬ, а не курсор: щелчок мог прийти и с клавиатуры,
  // и из прибора, а панель у него всё равно та, над которой он случился.
  const pan = panelAt(px, py);
  const pid = pan ? pan.id : null;
  const { mx, my } = mainScales(pid);
  let best = null;
  keyTargets(pid).forEach(p => {
    const d = Math.hypot(mx(p.x) - px, my(p.y) - py);
    if (d <= KEY_SNAP_PX && (!best || d < best.d)) best = { x: p.x, y: p.y, name: p.name, key: true, d, panel: pid };
  });
  /* ⚠️ СВОИ ТОЧКИ — ТОЖЕ КАНДИДАТ НА ЗАХВАТ, НАРАВНЕ С КЛЮЧЕВЫМИ (замер
     владельца 21.08: промах 5 px давал вершину в 7+ px от своей точки — щелчок
     соскальзывал на ближайшую кривую вместо неё). Раньше их не было вовсе ни
     здесь, ни в snapPointAt: своя точка часто стоит НЕ на кривой и НЕ в
     пересечении, и тогда ловить её было нечем — засечь получалось только
     координатами до пикселя. Тот же радиус KEY_SNAP_PX, что и у ключевых
     точек: своя точка для вершины площади не менее важна. */
  // Своя точка — кандидат только в СВОЕЙ панели: в соседней её нет на экране.
  (STATE.marks || []).filter(mk => markPanelId(mk) === pid).forEach(mk => {
    const d = Math.hypot(mx(mk.x) - px, my(mk.y) - py);
    if (d <= KEY_SNAP_PX && (!best || d < best.d)) best = { x: mk.x, y: mk.y, name: mk.name || 'своя точка', key: true, d, panel: pid };
  });
  if (best) return best;
  const hit = snapPointAt(px, py);
  return hit ? { x: hit.x, y: hit.y, name: hit.name, key: false, cross: hit.cross, panel: pid } : null;
}

/* Панель объекта слоя (точка, вершина, посчитанная площадь). Записи без поля
   `panel` считаются принадлежащими панели по умолчанию: калькулятор ничего не
   хранит между сессиями, но защита от undefined нужна — объект мог быть
   заведён кодом, который про панели ещё не знает. */
function markPanelId(o) {
  if (o && o.panel) return o.panel;
  const list = STATE.panels || [];
  return list.some(p => p.id === 'main') ? 'main' : (list[0] ? list[0].id : null);
}

/* Ключевые точки на холсте (П36–П38).

   Что считаем ключевой точкой (П36): любое пересечение — кривой с кривой,
   кривой с осью, оси с осью; излом кусочно заданной кривой; любой экстремум.
   ПЕРЕГИБЫ ключевыми точками не считаем и не отмечаем. Ровно это и возвращает
   keyTargets(); раньше на холсте рисовался более бедный crossPoints() — без
   экстремумов и изломов, — и договорённость держалась только на словах.

   Излом (П37) особый: у него сразу, без всякого щелчка, проводится пунктир к
   обеим осям и подписываются координаты НА ОСЯХ. У остальных точек так не
   делается: они серые, а координаты и «закрепка» появляются по щелчку. */
/* Панель ВЗВЕДЁННОЙ кривой. Взводят кривую щелчком, а курсор потом уходит
   куда угодно — привязывать её точки к панели под курсором было бы неверно.
   Кривая без панели (а таких 38 сцен из 44) отдаёт null: там панель одна. */
function armedPanelId() {
  if (!STATE.armedCurve) return null;
  const t = snapTargetsAll().filter(t => t.name === STATE.armedCurve)[0];
  return (t && t.panel) || null;
}

function drawCrossPoints() {
  /* По умолчанию автоматических ключевых точек нет вовсе (решение владельца).
     Пока ни одна кривая не взведена, рисовать нечего — холст чистый.
     Своих точек и вершин площадей это не касается: их рисуют drawMarks и
     drawAreaVerts, и они видны всегда. */
  if (!STATE.armedCurve) return;
  const pid = armedPanelId();
  const pts = keyTargets(pid).filter(keyPointLit);
  if (!pts.length) return;
  const { mx, my } = mainScales(pid);
  const g = svg.append('g').attr('class', 'crosses');
  // Цвет взведённой кривой: загоревшаяся точка красится им, а не общим сланцем.
  const armed = snapTargetsAll().filter(t => t.name === STATE.armedCurve)[0];
  const litColor = (armed && armed.color) || COL.ink;
  // Пока набирают вершины или ставят свою точку, кружки ключевых точек не ловят
  // щелчок: иначе щелчок рядом с пересечением уходил в кружок и вершина не
  // ставилась вовсе. Прилипание к этим же точкам работает и без их кликабельности.
  if (STATE.vertArm || STATE.markArm) g.style('pointer-events', 'none');

  pts.forEach((p, i) => {
    const px = mx(p.x), py = my(p.y);

    /* Излом раньше рисовался ОСОБО: пунктир к обеим осям и числа прямо на
       осях, показанные СРАЗУ, без наведения, и вообще без значка закрепки —
       свой код, в обход всего, что ниже. Приёмка владельца 21.08: излом обязан
       быть ключевой точкой НАРАВНЕ с пересечением кривой с осью — наведение
       показывает подпись с координатами, щелчок по значку закрепляет. Особого
       пути для 'kink' больше нет: точка идёт тем же кодом, что и все прочие. */
    const item = g.append('g').attr('class', 'cross-item');
    /* ⚠️ ЗАПАС ПОПАДАНИЯ ПО ТОЧКЕ. Замер до правки: сама точка ловила щелчок
       кругом радиусом 4 px, а с пяти пикселей в любую сторону под курсором
       была уже полоса кривой шириной 16. Зазора не было вовсе — промах на пять
       пикселей уносил руку в кривую вместо точки. Прозрачный круг радиусом 11
       лежит выше полос (см. порядок в drawOverlays), и пока курсор внутри
       него, кривая на указатель не отзывается. */
    item.append('circle').attr('cx', px).attr('cy', py).attr('r', KEY_HIT_PX)
      .attr('fill', 'transparent').attr('data-skip-export', '1').style('cursor', 'pointer');
    const dot = item.append('circle').attr('cx', px).attr('cy', py)
      .style('cursor', 'pointer');
    // Подпись живёт в своей группе: её показываем и прячем, не трогая остальное.
    const lab = item.append('g').attr('class', 'cross-label').style('display', 'none');
    haloText(lab, px + 9, py - 9, '(' + fmt(p.x) + '; ' + fmt(p.y) + ')', 'start', 'auto');
    // «Закрепка» рядом с координатами: кладёт точку в список своих точек.
    const pin = lab.append('g').attr('class', 'cross-pin').style('cursor', 'pointer');
    pin.append('rect').attr('x', px + 9).attr('y', py - 5).attr('width', 15).attr('height', 15)
      .attr('rx', 3).attr('fill', COL.halo).attr('stroke', COL.inkSoft).attr('stroke-width', 1);
    pin.append('path')
      .attr('d', `M${px + 12.5},${py + 7} l0,-3 l6,-6 l3,3 l-6,6 z`)
      .attr('fill', 'none').attr('stroke', COL.inkSoft).attr('stroke-width', 1.2)
      .attr('stroke-linejoin', 'round');
    /* Значок без подписи и без пояснения — просто точка (решение владельца).
       Он единственный выносит точку в список насовсем. */
    pin.on('click', (ev) => { ev.stopPropagation(); pinKeyPoint(p); });

    /* Точка взведённой кривой горит цветом этой кривой и жирнее обычного, но
       БЕЗ координат: координаты показывает наведение и только оно. */
    const paint = () => {
      const hover = (STATE.hoverCross === i);
      dot.attr('r', hover ? 5.5 : 4.5)
         .attr('fill', hover ? litColor : COL.halo)
         .attr('stroke', litColor)
         .attr('stroke-width', hover ? 2.6 : 2.2)
         .attr('opacity', 1);
      lab.style('display', hover ? null : 'none');
      pin.style('display', hover ? null : 'none');
    };
    paint();
    /* ⚠️ ПЛАШКА ОБЯЗАНА ПЕРЕЖИТЬ ПЕРЕХОД С ТОЧКИ НА ЗНАЧОК.
       Значок лежит внутри плашки, то есть в стороне от кружка. Скрой плашку
       сразу по уходу курсора с кружка — и до значка не дотянуться никогда:
       он исчезает ровно в тот момент, когда рука к нему движется. Поэтому
       уход даёт короткую отсрочку, а вход в саму плашку её отменяет.
       Второй раз в проекте: тем же способом лечится любая плашка с кнопкой. */
    let leaveTimer = null;
    const show = () => {
      if (leaveTimer) { clearTimeout(leaveTimer); leaveTimer = null; }
      STATE.hoverCross = i; paint();
    };
    const hide = () => {
      if (leaveTimer) clearTimeout(leaveTimer);
      leaveTimer = setTimeout(() => {
        leaveTimer = null;
        if (STATE.hoverCross === i) { STATE.hoverCross = null; paint(); }
      }, 160);
    };
    item.on('pointerenter', show).on('pointerleave', hide);
    /* Щелчок по самой точке НЕ закрепляет её: закрепки больше нет, выносит
       только значок. Всплытие останавливаем, иначе щелчок дошёл бы до холста
       и погасил взведённую кривую прямо из-под руки. */
    item.on('click', (ev) => ev.stopPropagation());
  });
}

/* ── ВЗВЕДЕНИЕ КРИВОЙ (фаза 3) ────────────────────────────────────────────

   Правило владельца: по умолчанию автоматических ключевых точек на холсте нет
   вовсе. Щелчок по кривой ЗАЖИГАЕТ её ключевые точки — цветом и жирностью, без
   координат. Наведение на загоревшуюся точку ПОКАЗЫВАЕТ координаты и значок;
   наведение ничего не выносит и ничего не сохраняет. Выносит точку в список
   только щелчок по значку.

   ⚠️ Это НЕ копия Десмоса, и это осознанно. В Десмосе шага «щёлкнуть по
   кривой» нет: точка появляется только под курсором, по одной, и найти их все
   можно лишь обшарив кривую мышью. Для учебного инструмента это хуже — ученик
   должен видеть, ГДЕ у функции особые точки. Отсюда гибрид: щелчок показывает
   все точки разом, дальше наведение работает по-десмосовски.

   Взведена всегда ОДНА кривая: щелчок по другой гасит первую. Гасится ровно
   двумя способами — повторным щелчком по той же кривой и щелчком по пустому
   месту холста. Escape не гасит: так решил владелец. */
function armCurve(name) {
  const nm = name || null;
  STATE.armedCurve = (STATE.armedCurve === nm) ? null : nm;
  redrawAll();
}

function disarmCurve() {
  if (STATE.armedCurve === null) return false;
  STATE.armedCurve = null;
  redrawAll();
  return true;
}

// Горит ли точка сейчас: у неё есть хозяин, и он взведён.
function keyPointLit(p) {
  return !!STATE.armedCurve && !!p.owners && p.owners.indexOf(STATE.armedCurve) >= 0;
}

/* Полосы попадания для кривых, которые сцена рисует САМА, мимо общего
   рисовальщика. Их одиннадцать сцен из сорока одной (издержки, макро, КПВ,
   «ломаный спрос» и прочие): у них нет записи в STATE.curves, которую видит
   drawCurves, а значит нет и полосы — то есть взвести их было бы нечем.

   Полоса строится по той же функции, по которой считаются ключевые точки
   (snapTargets), поэтому кривая и её точки не могут разъехаться по построению.
   Имена, у которых полоса уже есть, пропускаем: две полосы на одну кривую
   означали бы, что верхняя молча съедает щелчок по нижней. */
function drawCurveHits() {
  if (STATE.markArm || STATE.vertArm) return;   // сейчас на холсте ставят точку
  /* Полосы нужны у ВСЕХ кривых сцены, а не только у панели под курсором:
     щёлкнуть по кривой соседней панели человек вправе. Считает каждую полосу
     её собственная панель. */
  const targets = snapTargetsAll();
  if (!targets.length) return;
  const done = new Set();
  svg.selectAll('g.curves path[data-hit]').each(function () {
    const nm = this.getAttribute('data-hit-name');
    if (nm) done.add(nm);
  });
  const g = svg.append('g').attr('class', 'curve-hits').attr('clip-path', 'url(#plot-clip)');
  targets.forEach(t => {
    if (done.has(t.name)) return;
    const ts = mainScales(t.panel);
    const mx = ts.mx, my = ts.my;
    const [xLo, xHi] = mx.domain();
    const line = d3.line().defined(d => d !== null).x(d => mx(d[0])).y(d => my(d[1]));
    const pts = [];
    for (let i = 0; i <= 240; i++) {
      const x = xLo + (xHi - xLo) * i / 240;
      let v;
      try { v = t.f(x); } catch (e) { v = NaN; }
      pts.push(isFinite(v) ? [x, v] : null);
    }
    if (!pts.some(p => p)) return;
    g.append('path').datum(pts)
      .attr('fill', 'none').attr('stroke', 'transparent').attr('stroke-width', CURVE_HIT_PX)
      .attr('data-skip-export', '1').attr('data-hit-name', t.name)
      .attr('d', line).style('cursor', 'pointer')
      .on('click', (ev) => { ev.stopPropagation(); armCurve(t.name); });
  });
}

/* Закрепка: ключевая точка становится обычной своей точкой — последней в
   списке. Блок «Точки на графике» при этом раскрывается сразу же, иначе точка
   уходит в закрытую карточку и выглядит как «ничего не произошло». */
function pinKeyPoint(p) {
  pushUndo();
  /* Единственный способ вынести точку насовсем. Наведение этого не делает
     намеренно: владелец оговорил отдельно и настойчиво, что увёл курсор — и
     не осталось ничего. */
  addMarkAt(p.x, p.y, null);              // последней в списке, как обычная точка
  openSection('sec-view');
}

/* Прокатывание по кривой: нажимаете НА кривую и, не отпуская, ведёте — по ней
   едет точка, а рядом с курсором висит окошко с координатами. Отпустили — и
   точки, и окошка нет. Просто провести курсором рядом недостаточно: раньше
   точка выскакивала от одного движения мыши в радиусе 90 пикселей и мешала
   попадать по всему остальному. Чтобы точка осталась насовсем, есть кнопка
   «Поставить точку». */
/* Подпись, которая всплывает только при наведении на точку (Фаза 8). Тот же
   приём, что у ключевых точек: подпись живёт в своей группе со display:none,
   наведение меняет ТОЛЬКО её. Звать redrawAll из обработчика наведения нельзя:
   он снесёт кружок вместе с обработчиком, pointerleave с удалённого узла не
   придёт, и подпись останется гореть навсегда — эта ошибка уже была. */
function hoverLabel(g, dot, x, y, text, anchor, baseline) {
  const lab = g.append('g').attr('class', 'hover-label').style('display', 'none');
  haloText(lab, x, y, text, anchor || 'start', baseline || 'auto');
  dot.style('cursor', 'pointer')
     .on('pointerenter', () => lab.style('display', null))
     .on('pointerleave', () => lab.style('display', 'none'));
  /* Своей плашки здесь не нужно: та же фраза уже показывается подписью на
     холсте, а `pointerenter` приходит и от касания. */
  return lab;
}

function drawRoller() {
  const r = STATE.roller;
  if (!r) return;
  const { mx, my } = mainScales(r.panel);
  const g = svg.append('g').attr('class', 'roller').style('pointer-events', 'none');
  const px = mx(r.x), py = my(r.y);
  // Проекции ведём до самой оси, а если ноль ушёл за край окна — до края.
  // Раньше начало брали из CONFIG, и в «Математике» отрезки начинались не там.
  const [dx0, dx1] = mx.domain(), [dy0, dy1] = my.domain();
  const xAxis = Math.max(dx0, Math.min(0, dx1)), yAxis = Math.max(dy0, Math.min(0, dy1));
  g.append('line').attr('x1', mx(xAxis)).attr('y1', py).attr('x2', px).attr('y2', py)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '3 3').attr('opacity', .55);
  g.append('line').attr('x1', px).attr('y1', my(yAxis)).attr('x2', px).attr('y2', py)
    .attr('stroke', COL.inkSoft).attr('stroke-width', 1).attr('stroke-dasharray', '3 3').attr('opacity', .55);
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', 5.5)
    .attr('fill', COL.halo).attr('stroke', r.color || COL.ink).attr('stroke-width', 2.4);
  // Координаты показывает окошко у курсора (showRollTip): на холсте подпись
  // дублировала бы его и норовила залезть под руку.
}

// Кривая под курсором (в пикселях) — для прокатывания.
function rollerTargetAt(px, py) {
  const pan = panelAt(px, py);
  const pid = pan ? pan.id : null;
  const { mx, my } = mainScales(pid);
  const targets = snapTargets(pid);
  if (!targets.length) return null;
  const [xLo, xHi] = mx.domain();
  let best = null;
  targets.forEach(t => {
    const N = 200;
    for (let i = 0; i <= N; i++) {
      const x = xLo + (xHi - xLo) * i / N;
      const y = t.f(x);
      if (!isFinite(y)) continue;
      const d = Math.hypot(mx(x) - px, my(y) - py);
      if (!best || d < best.d) best = { d, t };
    }
  });
  // Панель запоминаем у самой цели: точка покатится по шкалам своей панели.
  return (best && best.d <= ROLL_PX)
    ? Object.assign({}, best.t, { panel: best.t.panel || pid }) : null;
}

const ROLL_PX = 12;    // на каком расстоянии нажатие считается «по кривой»

/* Осмысленная область кривой. На КПВ за точкой пересечения с осью кривой нет,
   и катать по ней точку в отрицательных значениях бессмысленно. Возвращаем
   ближайший к запрошенному x, где функция считается и (в ЭКОНОМИЧЕСКИХ сценах)
   не уходит ниже оси; годной точки нет — null. Условие — isEconScene(), а не
   галочка: точка катается по кривой, а кривой ниже оси Q нет. */
function rollerClampX(f, x, panelId) {
  const { mx } = mainScales(panelId);
  let [lo, hi] = mx.domain();
  if (isEconScene()) lo = Math.max(lo, 0);
  const ok = (t) => { const v = f(t); return isFinite(v) && (!isEconScene() || v >= -1e-9); };
  x = Math.max(lo, Math.min(hi, x));
  if (ok(x)) return x;
  const N = 240, step = (hi - lo) / N;
  for (let k = 1; k <= N; k++) {
    const a = x - k * step, b = x + k * step;
    if (a >= lo && ok(a)) return a;
    if (b <= hi && ok(b)) return b;
  }
  return null;
}

/* Точка едет за курсором без задержки. Раньше здесь стоял redrawAll: холст
   пересобирался целиком на каждом кадре движения, и точка отставала от руки.
   Теперь перерисовывается только слой самой точки. */
function rollerMove(px, clientX, clientY) {
  const r = STATE.roller;
  if (!r) return;
  const { mx } = mainScales(r.panel);
  const x = rollerClampX(r.f, mx.invert(px), r.panel);
  if (x == null) return;
  const y = r.f(x);
  if (!isFinite(y)) return;
  r.x = x; r.y = y;
  svg.selectAll('g.roller').remove();
  drawRoller();
  showRollTip(r, clientX, clientY);
}

/* Окошко с координатами рядом с курсором, пока держат кнопку. Обычный div над
   холстом: рисовать его в SVG значило бы трогать холст на каждом движении. */
function showRollTip(r, clientX, clientY) {
  const gw = document.getElementById('graph-wrap');
  if (!gw) return;
  let tip = document.getElementById('roll-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'roll-tip';
    gw.appendChild(tip);
  }
  if (!r) { tip.style.display = 'none'; return; }
  const box = gw.getBoundingClientRect();
  const x = (clientX == null) ? box.left + 10 : clientX;
  const y = (clientY == null) ? box.top + 10 : clientY;
  tip.textContent = r.name + ' (' + fmt(r.x) + '; ' + fmt(r.y) + ')';
  tip.style.display = 'block';
  // Держим окошко внутри холста: у правого и нижнего края разворачиваем.
  const w = tip.offsetWidth || 120, h = tip.offsetHeight || 24;
  let left = x - box.left + 16, top = y - box.top - h - 12;
  if (left + w > box.width - 4) left = x - box.left - w - 16;
  if (top < 4) top = y - box.top + 18;
  tip.style.left = Math.round(left) + 'px';
  tip.style.top = Math.round(top) + 'px';
}
function hideRollTip() {
  const tip = document.getElementById('roll-tip');
  if (tip) tip.style.display = 'none';
}

/* Точка едет за курсором без нажатия. Кривую выбираем по вертикальной близости
   в текущем положении курсора: так точка не перескакивает между кривыми, когда
   те идут рядом, и уверенно держится той, над которой ведут мышь. */
/* Убрать бегущую точку и её окошко (отпустили кнопку, сменили сцену). */
function rollerOff() {
  STATE.roller = null;
  hideRollTip();
  if (svg && svg.node()) svg.selectAll('g.roller').remove();
}
/* ── Расчёт площадей (Фаза 10) ────────────────────────────────────────
   Два способа: под кривой на отрезке и по выбранным точкам. Оба считаются
   численно тем же способом, что и излишки: трапециями и формулой площади
   многоугольника. Результат уходит в «Аналитику» и закрашивается на графике. */

// Правый край кривой в первой четверти: где она уходит вниз за ось.
function curveRightEdge(f) {
  const w = viewWindow();
  const lo = Math.max(0, w.x0), hi = w.x1;
  const ok = (x) => { const y = f(x); return isFinite(y) && y >= 0; };
  if (!ok(lo)) return lo;
  const N = 400;
  let last = lo;
  for (let i = 1; i <= N; i++) {
    const x = lo + (hi - lo) * i / N;
    if (!ok(x)) {
      // Точный край — там, где кривая садится на ось. Сетка даёт только вилку
      // между последней годной и первой негодной точкой, поэтому дожимаем её
      // делением пополам. Без этого у 10 − x правая граница выходила 9.97
      // вместо 10, и площадь получалась меньше настоящей.
      let a = last, b = x;
      for (let k = 0; k < 60; k++) { const m = (a + b) / 2; if (ok(m)) a = m; else b = m; }
      return a;
    }
    last = x;
  }
  return last;
}

// Как называется переменная горизонтальной оси в текущей сцене: границы отрезка
// подписываются ею, а не безликими «от» и «до».
function axisXLetter() { return axisLetter('x'); }

/* п. 32. КООРДИНАТА НАЗЫВАЕТСЯ ТАК ЖЕ, КАК ОСЬ.

   Оси подписаны Q и P, а форма ввода точки просила x и y — две системы
   обозначений на одном экране. Берём обозначение самой оси, но ТОЛЬКО когда
   это обозначение, а не фраза: «Издержки = 50» в колонке шириной в сотню
   пикселей нечитаемо, а «TP, MP, AP» ещё и не одна величина. Длинное
   название оси оставляем осям, координате даём привычные x и y. */
const AXIS_LETTER_MAX = 3;
function axisLetter(which) {
  const src = (which === 'y')
    ? (STATE.axisYName || STATE.axisYDefault)
    : (STATE.axisXName || STATE.axisXDefault);
  const t = String(src || '').trim();
  if (t && t.length <= AXIS_LETTER_MAX && !/[\s,;]/.test(t)) return t;
  return which === 'y' ? 'y' : 'x';
}

/* ── Вершины площади щелчками (Фаза 7) ────────────────────────────────
   Режим «Между точками» переводит график в набор вершин: каждый щелчок
   ставит вершину, рядом с особой точкой она прыгает точно в неё. Галочки
   в списке для этого больше не нужны. */
function armVerts(on) {
  const was = STATE.vertArm;
  STATE.vertArm = !!on;
  const wrap = document.getElementById('graph-wrap');
  if (wrap) wrap.style.cursor = STATE.vertArm ? 'crosshair' : '';
  if (!STATE.vertArm) showSnapHint(null);
  renderVertList();
  syncCanvasMode();
  // Дорожка захвата кривой во взведённом режиме не рисуется, поэтому холст
  // надо переложить. Только НА СМЕНЕ состояния: снятие уже снятого режима
  // случается при каждой загрузке сцены, и лишняя перерисовка там ни к чему.
  if (was !== STATE.vertArm && typeof redrawAll === 'function') redrawAll();
}

/* п. 25. Полоса режима холста: что делает щелчок и чем это кончить.

   Слова берём здесь, в одном месте, а не в каждом, кто взводит режим:
   иначе «ставите точку» и «набираете вершины» разъехались бы с тем, что
   на самом деле произойдёт. Состояние спрашиваем у `canvasMode()` —
   второго списка флагов не заводим. */
const CANVAS_MODE_TEXT = {
  mark: () => ({ what: '<b>Ставите точку</b> <span>· нажмите на график</span>', stop: 'Отмена' }),
  /* Счёт набранного стоит здесь, а не отдельной плавающей кнопкой (п. 80):
     человек работает на холсте, и видеть, сколько уже отмечено, ему нужно
     здесь же. Считает площадь по-прежнему одна кнопка — та, под которой
     появляется результат. */
  vert: () => {
    const n = (STATE.areaVerts || []).length;
    const tail = n ? ('· отмечено ' + n + (n < 3 ? ', нужно хотя бы три' : ''))
                   : '· каждый щелчок ставит вершину';
    return { what: '<b>Отмечаете вершины</b> <span>' + tail + '</span>', stop: 'Готово' };
  },
};

function syncCanvasMode() {
  // Пока вершины отмечаются, закончить набор предлагает полоса режима над
  // холстом; кнопка в панели на это время уходит, чтобы одно и то же действие
  // не стояло на экране дважды. Состояние у обеих одно — `canvasMode()`.
  const arm = document.getElementById('ac-vert-arm');
  if (arm) arm.hidden = !!STATE.vertArm;
  const bar = document.getElementById('cv-mode');
  if (!bar) return;
  const make = CANVAS_MODE_TEXT[canvasMode()];
  bar.hidden = !make;
  if (!make) return;
  const t = make();
  const what = document.getElementById('cv-mode-what');
  const stop = document.getElementById('cv-mode-stop');
  if (what) what.innerHTML = t.what;
  if (stop) stop.textContent = t.stop;
}

// Выйти из любого взведённого режима холста. Одна дверь на кнопку «Готово»,
// на Escape и на всё, что режим прерывает.
function leaveCanvasMode() {
  if (STATE.markArm) { cancelMarkDraft(); return; }
  if (STATE.vertArm) armVerts(false);
}

function addAreaVert(x, y, name, panel) {
  STATE.areaVerts = STATE.areaVerts || [];
  // Хозяйская панель вершины: в ней её поставили, по её шкалам и рисуем.
  const pid = panel || (activePanel() ? activePanel().id : null);
  STATE.areaVerts.push({ x, y, name: name || '', panel: pid });
  renderVertList();
  redrawAll();
}

/* ⚠️ ПЛОЩАДЬ НЕ ПЕРЕСЕКАЕТ ГРАНИЦУ ПАНЕЛИ.
   Многоугольник собирается из вершин ОДНОЙ панели. Иначе получается фигура,
   натянутая между графиком функции и графиком её производной, — у неё нет ни
   смысла, ни числа: у панелей разные единицы по обеим осям. */
function vertPanels() {
  return Array.from(new Set((STATE.areaVerts || []).map(markPanelId)));
}
function vertsMixed() { return vertPanels().length > 1; }

function clearAreaVerts() { STATE.areaVerts = []; renderVertList(); redrawAll(); }

/* Список набранных вершин (П42). Пока не выбрана ни одна точка, вместо списка
   стоит надпись «Выберите точки на графике»; с первой же вершиной вместо неё
   появляется кнопка «Убрать все вершины», а под ней сам список: у каждой
   строки крестик, а по двойному щелчку координата правится прямо в строке. */
function renderVertList() {
  const box = document.getElementById('ac-verts');
  if (!box) return;
  const list = STATE.areaVerts || [];
  const empty = document.getElementById('ac-verts-empty');
  const btns = document.getElementById('ac-vert-btns');
  if (empty) empty.style.display = list.length ? 'none' : '';
  if (btns) btns.style.display = list.length ? '' : 'none';
  syncCanvasMode();   // подпись кнопки «Отмечать вершины» идёт за состоянием
  box.innerHTML = '';
  if (vertsMixed()) {
    const warn = document.createElement('div');
    warn.className = 'vert-mixed warn';
    warn.textContent = 'Вершины стоят на разных графиках — площадь считается внутри одного.';
    box.appendChild(warn);
  }
  list.forEach((p, i) => {
    const row = document.createElement('div');
    row.className = 'vert-row';
    const n = document.createElement('b'); n.textContent = (i + 1) + '.';

    const t = document.createElement('span');
    t.className = 'vert-co';
    t.setAttribute('data-tip', 'Двойной щелчок — поправить координаты');
    const paint = () => {
      t.textContent = (p.name ? p.name + ' ' : '') + '(' + fmt(p.x) + '; ' + fmt(p.y) + ')';
    };
    paint();
    t.addEventListener('dblclick', () => {
      const ed = document.createElement('span');
      ed.className = 'vert-edit';
      const mk = (key) => {
        const inp = document.createElement('input');
        inp.type = 'number'; inp.step = 'any'; inp.value = Math.round(p[key] * 1000) / 1000;
        inp.addEventListener('input', () => {
          const v = parseFloat(inp.value);
          if (isFinite(v)) { p[key] = v; p.name = ''; redrawAll(); }
        });
        inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') e.target.blur(); });
        return inp;
      };
      const ix = mk('x'), iy = mk('y');
      ed.append(ix, document.createTextNode(';'), iy);
      t.replaceWith(ed);
      ix.focus(); ix.select();
      const done = () => {
        // Уходим из строки, только когда фокус ушёл из обоих полей.
        setTimeout(() => {
          if (document.activeElement === ix || document.activeElement === iy) return;
          paint(); ed.replaceWith(t); redrawAll();
        }, 0);
      };
      ix.addEventListener('blur', done); iy.addEventListener('blur', done);
    });

    const del = document.createElement('button');
    del.type = 'button'; del.className = 'btn-icon'; del.textContent = '✕';
    del.setAttribute('data-tip', 'Убрать эту вершину');
    del.addEventListener('click', () => {
      STATE.areaVerts = (STATE.areaVerts || []).filter(v => v !== p);
      renderVertList(); syncAreaCalcButton(); redrawAll();
    });

    row.append(n, t, del);
    box.appendChild(row);
  });
  syncAreaCalcButton();
}

/* П41: «Посчитать площадь» не горит и не нажимается, пока считать нечего.
   Раньше кнопка была активна всегда и при пустом выборе просто выдавала
   ошибку текстом — сначала жмёшь, потом узнаёшь, что рано. */
function syncAreaCalcButton() {
  const btn = document.getElementById('ac-calc');
  if (!btn) return;
  const ready = (STATE.areaCalcMode === 'poly')
    ? ((STATE.areaVerts || []).length >= 3 && !vertsMixed())
    : !!areaPickedCurve();
  btn.disabled = !ready;
  btn.setAttribute('data-tip', ready ? '' : (STATE.areaCalcMode === 'poly'
    ? 'Отметьте на графике хотя бы три точки'
    : 'Сначала выберите кривую'));
}

function areaPickedCurve() {
  const sel = document.getElementById('ac-pick');
  const name = sel ? sel.value : '';
  return areaTargets().filter(x => x.name === name)[0] || null;
}

/* Отрезок, на котором считается площадь под кривой (П41). Показываем его
   рядом с выбором кривой в виде [0; Xmax] — это границы первой четверти для
   выбранной кривой. */
function areaCurveRange() {
  const t = areaPickedCurve();
  if (!t) return null;
  /* Н52. По умолчанию отрезок это первая четверть выбранной кривой: от нуля до
     её правого края. Но человек вправе задать свой, и тогда его границы главнее
     умолчания. Держим их в состоянии, а не в разметке: список площадей
     пересобирается, и подпись живёт недолго. */
  const a0 = Math.max(0, viewWindow().x0);
  const b0 = curveRightEdge(t.f);
  // Именно typeof: isFinite(null) это true, и пустое умолчание прошло бы за
  // настоящую границу, обнулив отрезок.
  const num = (v) => (typeof v === 'number' && isFinite(v));
  const a = num(STATE.acFrom) ? STATE.acFrom : a0;
  const b = num(STATE.acTo) ? STATE.acTo : b0;
  return (isFinite(a) && isFinite(b) && b > a) ? { a, b } : null;
}
/* Н51, Н52. Одна строка: «на отрезке [0; 100]», где обе границы правятся тем же
   компонентом, что и всюду. Прежде здесь стоял неизменяемый текст. */
function syncAreaRangeLabel() {
  const el = document.getElementById('ac-range');
  if (!el) return;
  const r = areaCurveRange();
  el.innerHTML = '';
  if (!r) {
    /* А65. Пока кривая не выбрана, здесь не показывается ничего. Раньше стоял
       тот же текст, что и в самом списке слева («Выберите кривую»), причём в
       поле шириной 43 пикселя — он переносился в две строки и выглядел как
       вторая, сбившаяся подсказка. По замыслу здесь стоит отрезок, на котором
       считается площадь, и он появляется вместе с выбором. */
    el.textContent = areaTargets().length ? '' : 'Сначала постройте кривую';
    return;
  }
  const bound = (key, get) => makeEditableValue({
    get,
    set: (v) => { STATE[key] = v; syncAreaRangeLabel(); },
    tex: (v, text) => text,
    title: key === 'acFrom' ? 'Начало отрезка' : 'Конец отрезка',
  });
  const word = document.createElement('span');
  word.className = 'ac-range-word'; word.textContent = 'на отрезке';
  const open = document.createElement('span'); open.textContent = '[';
  const semi = document.createElement('span'); semi.textContent = ';';
  const close = document.createElement('span'); close.textContent = ']';
  el.append(word, open, bound('acFrom', () => r.a), semi, bound('acTo', () => r.b), close);
}

/* п. 29. ИМЯ ВЕРШИНЫ УСТАРЕВАЕТ ВМЕСТЕ С КАРТИНКОЙ.

   Вершина, поставленная в пересечение D и S, запоминает это имя. Потом
   кривые сдвигают, пересечение уезжает, а в списке по-прежнему написано
   «1. пересечение D и S (50; 50)»: координаты верны, объяснение — нет.
   Координаты человек ставил сам, их не трогаем; имя это НАША подпись, и
   держать её можно, только пока она правда. Сверяем с текущими ключевыми
   точками: нет такой на этом месте — имя снимаем, остаются числа. */
function freshenVertNames() {
  const list = (STATE.areaVerts || []).filter(p => p.name);
  if (!list.length) return false;
  const w = viewWindow();
  const dx = (w.x1 - w.x0) * 2e-3, dy = (w.y1 - w.y0) * 2e-3;
  const keys = keyTargets();
  let changed = false;
  list.forEach(p => {
    const ok = keys.some(k => k.name === p.name &&
      Math.abs(k.x - p.x) <= dx && Math.abs(k.y - p.y) <= dy);
    if (!ok) { p.name = ''; changed = true; }
  });
  return changed;
}

// Набранные вершины на графике: номер у каждой и бледный контур будущей фигуры.
function drawAreaVerts() {
  const list = STATE.areaVerts || [];
  if (!list.length) return;
  // Список перекладываем ПОСЛЕ проверки имён и только если что-то изменилось:
  // renderVertList не перерисовывает холст, поэтому петли здесь нет.
  if (freshenVertNames()) renderVertList();
  /* Контур собирается ТОЛЬКО из вершин одной панели: у смешанного набора
     фигуры нет, и рисовать её было бы враньём (см. vertsMixed). Кружки при
     этом рисуются у всех вершин — каждый по шкалам своей панели. */
  const { mx, my } = mainScales(markPanelId(list[0]));
  const g = svg.append('g').attr('class', 'area-verts').style('pointer-events', 'none');
  if (vertsMixed()) {
    // нечего соединять
  } else if (list.length >= 3) {
    /* П43: контур показывает РОВНО ту фигуру, которая будет посчитана.
       Раньше пунктир соединял вершины в порядке щелчков, а площадь считалась
       по другому обходу — картинка и число расходились. */
    const ring = bestAreaRing(list).ring;
    g.append('path')
      .attr('d', 'M' + ring.map(p => mx(p.x) + ',' + my(p.y)).join('L') + 'Z')
      .attr('fill', COL.reg).attr('fill-opacity', 0.1)
      .attr('stroke', COL.reg).attr('stroke-width', 1.4).attr('stroke-dasharray', '5 4');
  } else if (list.length === 2) {
    g.append('line').attr('x1', mx(list[0].x)).attr('y1', my(list[0].y))
      .attr('x2', mx(list[1].x)).attr('y2', my(list[1].y))
      .attr('stroke', COL.reg).attr('stroke-width', 1.4).attr('stroke-dasharray', '5 4');
  }
  /* Вершины на графике (П42): при наведении явно выделяются, щелчок по уже
     выбранной снимает её, а зажатую можно перетащить — координата в списке
     меняется сама. Рядом с кривой вершина катится по ней, как и при постановке. */
  list.forEach((p, i) => {
    const ps = mainScales(markPanelId(p));
    const pmx = ps.mx, pmy = ps.my;
    const [xLo, xHi] = pmx.domain(), [yLo, yHi] = pmy.domain();
    const dot = g.append('circle').attr('cx', pmx(p.x)).attr('cy', pmy(p.y)).attr('r', 4.5)
      .attr('fill', COL.halo).attr('stroke', COL.reg).attr('stroke-width', 2)
      .style('pointer-events', 'all').style('cursor', 'grab');
    // Номер вершины стоит вплотную к своей точке: на 8 px вправо и вверх,
    // то есть в углу её же кружка радиусом 4,5.
    haloText(g, pmx(p.x) + 8, pmy(p.y) - 8, String(i + 1), 'start', 'auto');

    dot.on('pointerenter', () => dot.attr('r', 6.5).attr('stroke-width', 3))
       .on('pointerleave', () => dot.attr('r', 4.5).attr('stroke-width', 2));

    let moved = false;
    dot.call(d3.drag().container(() => svg.node())
      .on('start', () => { moved = false; })
      .on('drag', (ev) => {
        moved = true;
        const hit = snapVertexAt(ev.x, ev.y);
        // Вершина не переезжает в чужую панель протяжкой: хозяин у неё один.
        const inOwn = hit && markPanelId(hit) === markPanelId(p);
        p.x = inOwn ? hit.x : Math.max(xLo, Math.min(xHi, pmx.invert(ev.x)));
        p.y = inOwn ? hit.y : Math.max(yLo, Math.min(yHi, pmy.invert(ev.y)));
        p.name = (inOwn && hit.key) ? hit.name : '';
        renderVertList(); redrawAll();
      })
      .on('end', () => {
        if (moved) return;
        // Щелчок без движения по уже выбранной вершине снимает её. Щелчок по
        // холсту, который придёт следом, надо погасить: иначе на том же месте
        // тут же появится новая вершина.
        STATE._vertClickEaten = true;
        STATE.areaVerts = (STATE.areaVerts || []).filter(v => v !== p);
        renderVertList(); redrawAll();
      }));
  });
}

function areaTargets(panelId) {
  return snapTargets(panelId);
}

function calcAreaUnderCurve() {
  const t = areaPickedCurve();
  if (!t) return { error: 'Сначала постройте кривую и выберите её в списке.' };
  const name = t.name;
  const r = areaCurveRange();
  if (!r) return { error: 'Не удалось определить отрезок для этой кривой.' };
  const a = r.a, b = r.b;
  const val = integrate((x) => { const y = t.f(x); return isFinite(y) ? Math.max(0, y) : 0; }, a, b);
  if (!isFinite(val)) return { error: 'Не удалось посчитать: кривая не определена на этом отрезке.' };
  return { kind: 'curve', value: val, a, b, name, panel: activePanel() ? activePanel().id : null };
}

// Площадь замкнутого обхода по формуле шнурков.
function ringArea(ring) {
  let s2 = 0;
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i], q = ring[(i + 1) % ring.length];
    s2 += p.x * q.y - q.x * p.y;
  }
  return Math.abs(s2) / 2;
}

// Пересекаются ли отрезки p1p2 и q1q2 (без учёта общих концов).
function segCross(p1, p2, q1, q2) {
  const d = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const d1 = d(q1, q2, p1), d2 = d(q1, q2, p2), d3 = d(p1, p2, q1), d4 = d(p1, p2, q2);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
         ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}
// Есть ли у обхода самопересечение (несоседние стороны пересекаются).
function ringSelfCrosses(ring) {
  const n = ring.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (i === j || (i + 1) % n === j || (j + 1) % n === i) continue;
      if (segCross(ring[i], ring[(i + 1) % n], ring[j], ring[(j + 1) % n])) return true;
    }
  }
  return false;
}

/* Площадь по отмеченным точкам (П43).

   Все выбранные точки остаются вершинами: выпуклую оболочку не берём. Ищем
   многоугольник НАИБОЛЬШЕЙ площади без самопересечений, у которого вершины —
   ровно все отмеченные точки. До восьми вершин включительно перебираем все
   циклические обходы ((n−1)!/2 штук, при восьми это 2520 — считается мгновенно),
   отбрасываем самопересекающиеся и берём максимум. От девяти вершин перебор
   растёт факториально, поэтому остаётся прежняя сортировка по углу, и рядом с
   результатом честно пишется, что это приближение. */
const AREA_EXACT_MAX = 8;

function angleRing(pts) {
  const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
  const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
  return pts.slice().sort((p, q) => Math.atan2(p.y - cy, p.x - cx) - Math.atan2(q.y - cy, q.x - cx));
}

function bestAreaRing(pts) {
  if (pts.length > AREA_EXACT_MAX) return { ring: angleRing(pts), exact: false };
  // Первую вершину закрепляем и перебираем перестановки остальных: так каждый
  // цикл встречается ровно дважды (в двух направлениях), а не n·2 раз.
  const rest = pts.slice(1);
  let best = null;
  const perm = (arr, cur) => {
    if (!arr.length) {
      const ring = [pts[0]].concat(cur);
      if (ringSelfCrosses(ring)) return;
      const a = ringArea(ring);
      if (!best || a > best.a) best = { a, ring };
      return;
    }
    for (let i = 0; i < arr.length; i++) {
      perm(arr.slice(0, i).concat(arr.slice(i + 1)), cur.concat([arr[i]]));
    }
  };
  perm(rest, []);
  return best ? { ring: best.ring, exact: true } : { ring: angleRing(pts), exact: false };
}

/* п. 26. САМОПЕРЕСЕЧЕНИЕ НАЗЫВАЕТСЯ ВСЛУХ.

   До восьми вершин перебор сам отбрасывает «бабочки», и обход всегда простой.
   От девяти он невозможен по времени, остаётся обход по кругу — а он у
   некоторых наборов точек пересекает сам себя, и площадь по формуле шнурков
   тогда не значит ничего: части фигуры вычитаются друг из друга. Молчать об
   этом нельзя (канон 2.13), поэтому оговорка едет вместе с числом и видна на
   экране, а не в подсказке браузера. */
function calcAreaPolygon() {
  const pts = (STATE.areaVerts || []).slice();
  if (pts.length < 3) return { error: 'Нужно хотя бы три вершины: щёлкните по графику ещё раз.' };
  if (vertsMixed()) return { error: 'Вершины стоят на разных графиках — площадь считается внутри одного.' };
  const r = bestAreaRing(pts);
  return { kind: 'poly', value: ringArea(r.ring), exact: r.exact,
           crosses: !r.exact && ringSelfCrosses(r.ring),
           panel: markPanelId(pts[0]),
           ring: r.ring.map(p => [p.x, p.y]) };
}

/* Порядок действий (Фаза 6): задал кривую и границы, нажал «Посчитать» — и
   только тогда появилась карточка результата, где можно назвать площадь и
   выбрать цвет. Раньше цвет выбирался ДО расчёта и потом не менялся.
   Результатов может быть несколько: они складываются в список и показываются
   таблицей «кривая · отрезок · площадь · цвет». */
let areaCalcCounter = 0;
const AREA_PALETTE = () => [COL.MR, COL.D, COL.S, COL.tax, COL.reg, COL.MC];

function runAreaCalc() {
  const err = document.getElementById('ac-error');
  const res = (STATE.areaCalcMode === 'poly') ? calcAreaPolygon() : calcAreaUnderCurve();
  if (res.error) {
    if (err) { err.textContent = res.error; err.style.display = 'block'; }
    return;
  }
  if (err) { err.textContent = ''; err.style.display = 'none'; }
  STATE.areaCalcList = STATE.areaCalcList || [];
  const pal = AREA_PALETTE();
  res.id = ++areaCalcCounter;
  res.color = pal[(STATE.areaCalcList.length) % pal.length];
  /* Н27: короткое имя с настоящим индексом — S₁, S₂, S₃. Прежние «Площадь под
     D» и «Площадь по точкам» не помещались в легенду и вытесняли из неё сами
     области. Что именно посчитано, видно рядом в строке таблицы. */
  res.label = 'S' + subDigits(STATE.areaCalcList.length + 1);
  STATE.areaCalcList.push(res);
  redrawAll();
}

function clearAreaCalc() {
  STATE.areaCalcList = [];
  const err = document.getElementById('ac-error');
  if (err) { err.textContent = ''; err.style.display = 'none'; }
  redrawAll();
}

function drawAreaCalc() {
  const list = STATE.areaCalcList || [];
  if (!list.length) { updateAreaCalcPanel(); return; }
  const g = svg.append('g').attr('class', 'areacalc').attr('clip-path', 'url(#plot-clip)');
  list.forEach(r => {
    // Площадь помнит свою панель: посчитана она в её шкалах, в них и рисуется.
    const { mx, my } = mainScales(markPanelId(r));
    const color = r.color || COL.MR;
    if (r.kind === 'curve') {
      const t = areaTargets(markPanelId(r)).filter(x => x.name === r.name)[0];
      if (!t) return;
      const N = 160, pts = [];
      for (let i = 0; i <= N; i++) pts.push(r.a + (r.b - r.a) * i / N);
      const yBase = Math.max(my.domain()[0], Math.min(0, my.domain()[1]));
      const ar = d3.area().x(d => mx(d)).y0(my(yBase))
        .y1(d => my(Math.max(0, t.f(d) || 0)));
      g.append('path').datum(pts).attr('d', ar).attr('fill', color).attr('opacity', 0.2)
        .attr('data-legend', r.label);
    } else if (r.ring && r.ring.length > 2) {
      const line = d3.line().x(d => mx(d[0])).y(d => my(d[1]));
      g.append('path').datum(r.ring.concat([r.ring[0]])).attr('d', line)
        .attr('fill', color).attr('opacity', 0.2).attr('stroke', color).attr('stroke-width', 1.5)
        .attr('data-legend', r.label);
    }
  });
  updateAreaCalcPanel();
}

/* Таблица результатов: что посчитано, на каком отрезке, сколько вышло и каким
   цветом закрашено. Название и цвет правятся прямо здесь. */
function updateAreaCalcPanel() {
  const box = document.getElementById('info-areacalc');
  if (!box) return;
  const list = STATE.areaCalcList || [];
  /* Свх-5, Н59. Таблица это единый список ВСЕГО закрашенного на графике: и
     посчитанного пользователем, и нарисованного самой сценой (излишки, сбор
     бюджета, потери общества). Раньше сценовые области жили только в отдельном
     разделе «Цвета областей», и там у них не было ни числа, ни соседства с
     посчитанными площадями. Раздел удалён, ничего не потеряно. */
  /* Области, которые нарисовала САМА МОДЕЛЬ. Посчитанные человеком площади
     тоже помечены `data-legend` — иначе они не попали бы в легенду на холсте,
     а там они нужны. Но в ТАБЛИЦЕ им не место: они уже идут своими строками
     ниже, со своим именем, цветом и крестиком. Без этой отсечки одна и та же
     площадь стояла дважды: S₁ без крестика и S₁ с крестиком, с одним числом. */
  const mine = {};
  (list || []).forEach(r => { mine[areaKey(r.label)] = 1; });
  const scene = currentAreas().filter(e => !mine[e.key]);
  box.innerHTML = '';
  if (!list.length && !scene.length) return;

  const table = document.createElement('div');
  table.className = 'area-table';
  // П44: столбцы «Название» и «Площадь». «Отрезок» убран — он и так виден
  // рядом с выбором кривой, а в таблице только занимал место.
  const head = document.createElement('div');
  head.className = 'area-row area-head';
  ['Название', 'Площадь', ''].forEach(t => {
    const c = document.createElement('span'); c.textContent = t; head.appendChild(c);
  });
  table.appendChild(head);

  // Сначала области сцены: их не удаляют (их рисует сама модель), поэтому
  // вместо крестика пустая клетка, а цвет правится тем же пикером.
  scene.forEach(e => {
    const row = document.createElement('div');
    row.className = 'area-row';
    const c1 = document.createElement('span');
    c1.className = 'area-what';
    const pick = makeColorPicker(e.color, (hex) => { STATE.areaColor[e.key] = hex; redrawAll(); },
                                 tipName('Цвет области: ' + e.key));
    pick.setAttribute('data-area', e.key);
    const lab = document.createElement('span');
    lab.className = 'area-name-fixed';
    paintNotation(lab, areaShort(e.key));   // «CS», «PS», «DWL» — формулой
    lab.setAttribute('data-tip', tipName(e.key));
    c1.append(pick, lab);
    const c2 = document.createElement('b');
    c2.textContent = (e.value == null) ? '' : fmt(e.value);
    const c3 = document.createElement('span');
    row.append(c1, c2, c3);
    table.appendChild(row);
  });

  list.forEach(r => {
    const row = document.createElement('div');
    row.className = 'area-row';

    const c1 = document.createElement('span');
    c1.className = 'area-what';
    // Шесть образцов, как и у всех остальных мест выбора цвета (П34).
    const pick = makeColorPicker(r.color, (hex) => { r.color = hex; redrawAll(); }, 'Цвет площади');
    const nameInp = document.createElement('input');
    nameInp.type = 'text'; nameInp.className = 'area-name'; nameInp.value = r.label;
    nameInp.setAttribute('data-tip', 'Название площади');
    nameInp.addEventListener('input', () => { r.label = nameInp.value; });
    nameInp.addEventListener('change', () => redrawAll());
    c1.append(pick, nameInp);

    const c3 = document.createElement('b');
    c3.textContent = fmt(r.value);
    if (r.kind === 'poly' && r.exact === false) c3.classList.add('area-approx');

    const del = document.createElement('button');
    del.type = 'button'; del.className = 'btn-icon'; del.textContent = '×';
    del.setAttribute('data-tip', 'Убрать эту площадь');
    del.addEventListener('click', () => {
      STATE.areaCalcList = STATE.areaCalcList.filter(x => x !== r);
      redrawAll();
    });

    row.append(c1, c3, del);
    /* Оговорка идёт СТРОКОЙ ПОД числом, а не подсказкой браузера: подсказку
       на планшете не открыть вовсе, а знать про приближение надо до того, как
       число выпишут в тетрадь. */
    if (r.kind === 'poly' && r.exact === false) {
      const note = document.createElement('span');
      note.className = 'area-note' + (r.crosses ? ' area-note--bad' : '');
      note.textContent = r.crosses
        ? 'Обход пересекает сам себя: это число не площадь фигуры. Уберите лишние вершины.'
        : 'Вершин больше восьми: обход взят по кругу, площадь приближённая.';
      row.appendChild(note);
    }
    table.appendChild(row);
  });
  box.appendChild(table);
}

// Выпадашка кривых и список точек: пересобираются под текущую сцену.
function syncAreaCalcUI() {
  // Границы подписаны буквой горизонтальной оси текущей сцены: где-то это Q,
  // где-то X, а в «Математике» x. Безликие «от» и «до» ничего не говорили.
  const v = axisXLetter();
  document.querySelectorAll('.ac-var').forEach(el => { el.textContent = v; });
  const sel = document.getElementById('ac-pick');
  if (sel) {
    const names = areaTargets().map(t => t.name);
    const sig = names.join('|');
    if (sel._sig !== sig) {
      sel._sig = sig;
      const prev = sel.value;
      sel.innerHTML = '';
      // Пустой первый пункт: пока кривая не выбрана, «Посчитать площадь» не
      // горит — выбор должен быть осознанным, а не «первая попавшаяся» (П41).
      const none = document.createElement('option');
      none.value = ''; none.textContent = 'Выберите кривую';
      sel.appendChild(none);
      names.forEach(n => {
        const o = document.createElement('option');
        o.value = n; o.textContent = n;
        sel.appendChild(o);
      });
      sel.value = (names.indexOf(prev) >= 0) ? prev : '';
      // Список пересобран: своя кнопка выбора должна показать новое значение.
      if (typeof sel._paint === 'function') sel._paint();
    }
  }
  renderVertList();
  syncAreaRangeLabel();
  syncAreaCalcButton();
  updateQuickArea();
}

// Сколько вершин набрано — говорит полоса режима над холстом (п. 80).
function updateQuickArea() { syncCanvasMode(); }

function setAreaCalcMode(mode) {
  STATE.areaCalcMode = (mode === 'poly') ? 'poly' : 'curve';
  const c = document.getElementById('ac-curve'), p = document.getElementById('ac-poly');
  if (c) c.classList.toggle('active', STATE.areaCalcMode === 'curve');
  if (p) p.classList.toggle('active', STATE.areaCalcMode === 'poly');
  const pc = document.getElementById('ac-pane-curve'), pp = document.getElementById('ac-pane-poly');
  if (pc) pc.style.display = (STATE.areaCalcMode === 'curve') ? '' : 'none';
  if (pp) pp.style.display = (STATE.areaCalcMode === 'poly') ? '' : 'none';
  armVerts(STATE.areaCalcMode === 'poly');
  updateQuickArea();
  redrawAll();   // кружки ключевых точек перестают ловить щелчок (см. drawCrossPoints)
}

/* Сворачивание секций. Одна проводка на все складные заголовки: кнопка
   .fold-btn знает свою начинку через aria-controls. Так новая складная секция
   не требует ни строчки в JS. */
function wireFolds() {
  document.querySelectorAll('.fold-btn[aria-controls]').forEach(btn => {
    if (btn._folded) return;
    btn._folded = true;
    const body = document.getElementById(btn.getAttribute('aria-controls'));
    if (!body) return;
    btn.addEventListener('click', () => {
      const open = body.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      // Раскрытая карточка меняет фон: видно, что это по-прежнему свой блок,
      // а не продолжение ленты.
      const card = btn.closest('.section, .side-part');
      if (card) card.classList.toggle('open-card', open);
      /* Поля формул собираются лениво (А56): пока секция была свёрнута, поле
         оставалось в очереди. Раскрыли — собираем то, что стало видно.
         Перерисовку тут не зовём: раскрытие карточки график не меняет. */
      if (open && typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
      /* Итоговая функция подгоняется по ширине контейнера, а у свёрнутой
         панели ширина нулевая: подгонку в этот момент сделать нечем.
         Раскрыли — делаем. */
      if (open && typeof refitFinalMathSoon === 'function') refitFinalMathSoon();
    });
  });
}

function wireAreaCalc() {
  const c = document.getElementById('ac-curve'), p = document.getElementById('ac-poly');
  if (c) c.addEventListener('click', () => setAreaCalcMode('curve'));
  if (p) p.addEventListener('click', () => setAreaCalcMode('poly'));
  const calc = document.getElementById('ac-calc');
  if (calc) calc.addEventListener('click', () => runAreaCalc());
  const clr = document.getElementById('ac-clear');
  if (clr) clr.addEventListener('click', () => clearAreaCalc());
  // Выбрали кривую — сразу видно, на каком отрезке считаем, и кнопка загорается.
  const pick = document.getElementById('ac-pick');
  if (pick) pick.addEventListener('change', () => { syncAreaRangeLabel(); syncAreaCalcButton(); });
  const vClear = document.getElementById('ac-vert-clear');
  if (vClear) vClear.addEventListener('click', () => clearAreaVerts());
  const vArm = document.getElementById('ac-vert-arm');
  if (vArm) vArm.addEventListener('click', () => armVerts(!STATE.vertArm));
  setAreaCalcMode('curve');
}

/* ── Ползунки параметров ──────────────────────────────────────────────
   Если в формуле встретилась буква, которая не переменная графика и не
   известная функция, для неё заводится ползунок в «Основных параметрах».
   Двигаешь — формула пересчитывается, график перерисовывается.

   Механика общая для всех сцен. Раньше она работала только в «Свободном
   холсте» и в «Математике» из опасения, что в экономике буквы уже заняты
   (t — ставка, w — зарплата). Опасение не подтвердилось: ставку и зарплату
   держат отдельные поля STATE, а в формулу их никто не пишет. Буквы внутри
   формулы принадлежат тому, кто её набрал, поэтому «a - Q» в спросе теперь
   даёт ползунок a, а не ошибку разбора. */
function paramsAllowed() { return true; }

/* Переменные графика: буквы, которыми подписаны оси. Параметром такая буква
   стать не может — её значение задаёт сама точка на графике. */
/* П14. Строчная и заглавная — ОДНА величина. «100 - q» давало прямую P = 99
   и ползунок q = 1: буква не значилась осью, становилась параметром со
   значением 1, и формула честно считала «100 − 1». При этом «100 - x»
   работало, и разницы человек объяснить не мог. Синонимы объявлены здесь и
   ПОДСТАВЛЯЮТСЯ в расчёт (см. axisScope в 10-math-core.js) — одного списка
   мало: буква перестала бы быть параметром, но осталась бы неизвестной. */
const AXIS_VARS = new Set(['x', 'y', 'Q', 'q', 'P', 'p', 'L', 'l', 'K', 'X', 'Y']);

/* Настоящие математические константы. Только они из всего словаря Math.js
   закрывают одиночную букву. Раньше проверка была «есть ли math[имя]», и под
   неё попадало пол-алфавита: в Math.js есть и физические постоянные, и
   короткие имена функций, поэтому «x^2 + 5 + c» не давал ползунка для c. */
const MATH_CONSTS = new Set(['e', 'i', 'pi', 'PI', 'E', 'tau', 'phi',
  'Infinity', 'NaN', 'true', 'false', 'null']);

/* Многобуквенные обозначения, которые в экономике читаются как ОДНО имя,
   а не как произведение букв: MC — предельные издержки, а не M·C. */
const ECON_WORDS = new Set(['MC', 'MR', 'TC', 'ATC', 'AVC', 'AFC', 'FC', 'VC',
  'TR', 'TP', 'MP', 'AP', 'MPL', 'MRP', 'Qd', 'Qs', 'Pd', 'Ps', 'Pb', 'Pw',
  'CS', 'PS', 'DWL', 'AD', 'AS', 'IS', 'LM', 'GDP']);

function isReservedName(n) {
  if (AXIS_VARS.has(n) || MATH_CONSTS.has(n)) return true;
  // Многобуквенное имя закрыто, если это функция Math.js (sqrt, log, min…).
  if (n.length > 1) { try { if (typeof math[n] !== 'undefined') return true; } catch (e) {} }
  return false;
}

/* Неявное умножение. Math.js читает «bx» как ОДНО имя переменной, поэтому в
   формуле «b*x^2», записанной по-школьному как «bx^2», параметром оказывалась
   буква «bx». Это и была настоящая причина: не подпись в панели, а разбор.
   Здесь склейка букв раскрывается в произведение: bx → b*x, abc → a*b*c.
   Имена с цифрами и подчёркиванием (Q_1, x1), функции Math.js и экономические
   обозначения из ECON_WORDS не трогаем. */
/* ⚠️ ЧИСЛО ПЕРЕД БУКВОЙ ИЛИ ПЕРЕД СКОБКОЙ — ТОЖЕ УМНОЖЕНИЕ.
   Замер 24.08: сам Math.js «100-2P» читает верно (100 - 2 P, при P = 10 даёт
   80), поэтому расчёт от этой записи не падал. Падало другое: определитель
   формы записи (`curveSrcForm`, 80-ui.js) искал букву P по соседям и цифру
   слева соседом не считал — «100-2P» уезжало в форму P = f(Q), и вместо
   наклонной выходила горизонталь на 98 без единого слова об ошибке.
   Раскрываем звёздочку ЗДЕСЬ, в единственной двери разбора, чтобы у правила
   «цифра слева — это множитель» было одно место, а не два.

   Что здесь НЕЛЬЗЯ сломать (проверяется в calc2_math.mjs, набор «раскрытие»):
     · научная запись: «1e5», «2e-3» — целое число, а не «2*e-3». Одного
       «показатель входит в совпадение» МАЛО: движок регулярных выражений
       откатывает необязательную часть назад, и «1e5» всё равно распадалось на
       «1*e5» (замер 24.08, первая попытка правки). Поэтому стоит вторая,
       запрещающая проверка `(?![eE][+-]?\d)`: если сразу за числом начинается
       годный показатель степени, звёздочка не ставится ВООБЩЕ. При этом
       «1e5Q» остаётся умножением: там показатель уже съеден числом, а дальше
       идёт буква;
     · имя с цифрой ПОСЛЕ буквы: «Q_1», «x1», «P2» — одно имя. Цифра внутри
       имени в совпадение не попадает: слева от числа обязан стоять символ,
       которым имя продолжаться не может (не буква, не цифра, не «_», не «.»);
     · вызов функции: «sqrt(4)», «log(10)» — цифра в скобках, а за ней «)»,
       а не буква, поэтому правило молчит;
     · команды LaTeX: «2\cdot P» — за цифрой обратный слэш, он в список
       «буква или открывающая скобка» не входит, и команда доходит целой. */
const NUM_BEFORE_NAME = /(^|[^A-Za-z0-9_.])((?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(?![eE][+-]?\d)(?=[A-Za-z_(])/g;

function expandImplicitMul(expr) {
  const s0 = String(expr || '');
  if (!s0) return s0;
  // Сначала цифра-множитель, потом склейка букв: «2ab» → «2*ab» → «2*a*b».
  const s = s0.replace(NUM_BEFORE_NAME, '$1$2*');
  return s.replace(/[A-Za-z_][A-Za-z_]*/g, (name, at) => {
    if (name.length < 2) return name;
    /* ⚠️ ИМЯ ПОСЛЕ ОБРАТНОГО СЛЭША — ЭТО КОМАНДА, А НЕ ПРОИЗВЕДЕНИЕ БУКВ.
       Замер 22.08 до правки: «100-a\cdot x» превращалось здесь в
       «100-a\c*d*o*t x». То есть разбор не просто не понимал запись из
       MathLive — он её ДОЛОМЫВАЛ, и сообщение об ошибке показывало уже свою
       собственную порчу, а не то, что набрал человек. Перевод LaTeX стоит выше
       (prepExpr), но и здесь имя за слэшем неприкосновенно: непереведённая
       команда обязана дойти до Math.js целой и получить честный отказ. */
    if (at > 0 && s[at - 1] === '\\') return name;
    if (ECON_WORDS.has(name) || MATH_CONSTS.has(name)) return name;
    try { if (typeof math[name] !== 'undefined') return name; } catch (e) {}
    // Имя перед скобкой — вызов функции, разбирать его на буквы нельзя.
    const after = s.slice(at + name.length).match(/^\s*\(/);
    if (after) return name;
    if (!/^[A-Za-z]+$/.test(name)) return name;
    return name.split('').join('*');
  });
}


/* ── Подписи графика набираются МАТЕМАТИКОЙ ───────────────────────────
   Правило владельца: любые СЛОВА — шрифтом сайта, любая МАТЕМАТИКА —
   набрана формулой. В разметке за это отвечает KaTeX, но подписи графика
   живут в SVG, куда KaTeX не встаёт: там надо взять его же шрифты руками.
   Так это и делает сам KaTeX — переменная идёт наклонным математическим
   начертанием (KaTeX_Math), многобуквенное обозначение прямым (KaTeX_Main),
   как \mathrm{MC}.

   ⚠️ ТРОГАЕМ ТОЛЬКО ПОДПИСЬ, КОТОРАЯ ЦЕЛИКОМ ОБОЗНАЧЕНИЕ. Смешанную фразу
   («Излишек покупателя (CS)») пришлось бы резать на куски и собирать из
   tspan, а это переносы и съехавшая привязка. Такие подписи остаются в
   описи долга (night2_font_audit.mjs) и чинятся отдельной задачей. */
const CHART_MATH_WORDS = new Set(['MC','MR','TC','ATC','AVC','AFC','FC','VC','TR','TP','MP','AP',
  'MPL','MRP','Qd','Qs','Pd','Ps','Pb','Pw','Pc','Pf','CS','PS','DWL','AD','AS','SRAS','LRAS',
  'IS','LM','GDP','MSB','MSC','SW','Qm','Pm','Qc','Px','Py']);
/* Образец «одна буква с хвостом» больше не нужен: индекс и звёздочку теперь
   отрезает chartLabelBase, и решение принимается по ОСНОВАНИЮ подписи. */


// Видимый текст подписи SVG: всё, кроме всплывающей подсказки <title>.
function visibleSvgText(t) {
  let out = '';
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c.nodeType === 3) { out += c.nodeValue; continue; }
      if (c.nodeType !== 1) continue;
      if (String(c.nodeName).toLowerCase() === 'title') continue;
      walk(c);
    }
  };
  walk(t);
  return out.replace(/\s+/g, ' ').trim();
}
/* ⚠️ ПРАВИЛО СПРАШИВАЕТ ИСХОДНУЮ ЗАПИСЬ ПОДПИСИ, А НЕ НАРИСОВАННОЕ.

   Пять подписей (S в «Налогах», ATC / MC / E в естественной монополии, TC в
   «Сложении заводов») правило не брало, и в карточке это было записано как
   «рисуются ПОСЛЕ конца перерисовки». ЗАМЕР 24.08 ЭТОТ ДИАГНОЗ ОТВЁРГ: повтор
   `typesetChartLabels()` прямо в браузере, уже после всей перерисовки, не
   менял НИ ОДНОЙ подписи в трёх сценах. Значит рисуются они вовремя.

   Настоящая причина: подпись с индексом разложена на tspan'ы (`mathTspans`,
   `qtyTspans`), и её `textContent` — склейка «EATC», «TC1», «Q∗». Такой
   склейке не отвечает ни список обозначений, ни образец одиночной буквы.
   Исходная запись при этом лежит рядом с узлом в `data-raw` — её и спрашиваем.
   Особого пути отрисовки не заводим: путь остаётся один, умнее стало правило. */
function chartLabelSource(t) {
  const raw = t.dataset ? t.dataset.raw : null;
  return (raw != null && raw !== '') ? raw : visibleSvgText(t);
}

/* Основание подписи: индекс, степень и звёздочка отброшены.
   «E_{ATC}» → «E», «TC_1» → «TC», «Q*» → «Q», «TC₁» → «TC».
   Юникодные индексы отрезаются наравне с записью через подчёркивание: часть
   сцен пишет «TC₁» готовым символом, и без этой строки подпись «Сложения
   заводов» оставалась бы системным шрифтом. */
function chartLabelBase(src) {
  return String(src == null ? '' : src)
    .replace(/[_^](\{[^}]*\}|.)/g, '')
    .replace(/[\u2080-\u2089\u2070\u00b9\u00b2\u00b3\u2074-\u2079]/g, '')
    .replace(/[*\u2217\u2032']/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/* Каким начертанием набрать подпись: прямым (обозначение вроде MC),
   наклонным (величина вроде Q) или никаким (это проза).

   Короткая запись из одних обозначений и знаков («S + t») — тоже математика:
   иначе имя сдвинутой кривой предложения оставалось бы системным шрифтом
   рядом с той же буквой S, набранной курсивом. Кириллица в запись не
   допускается вовсе: смешанная фраза («TC совокупная») режется на куски,
   а это отдельная работа и своя карточка. */
function chartLabelKind(src) {
  const base = chartLabelBase(src);
  if (!base) return null;
  if (CHART_MATH_WORDS.has(base)) return 'upright';
  if (/^[A-Za-z]$/.test(base)) return 'italic';
  /* Греческая буква в записи — это тоже математика: «S·(1+τ)» (адвалорный
     налог) без неё оставалась бы системным шрифтом рядом с курсивной S. */
  if (!/^[A-Za-z0-9 +\-−·()\u0391-\u03c9]{1,14}$/.test(base)) return null;
  const runs = base.match(/[A-Za-z]+/g) || [];
  if (!runs.length) return null;
  if (!runs.every(r => CHART_MATH_WORDS.has(r) || r.length === 1)) return null;
  return 'italic';
}

function typesetChartLabels() {
  const root = document.getElementById('chart');
  if (!root) return;
  /* ⚠️ ИДЁМ ПО ВСЕМ ПОДПИСЯМ ХОЛСТА, А НЕ ТОЛЬКО ПО ДВУМ КЛАССАМ.
     Замер 24.08: правило по .axis-name и .curve-name починило три строки из
     сорока четырёх — остальные подписи 19 сцен рисуются мимо общего помощника
     и этих классов не несут (известный долг, своя карточка). Правило про
     шрифт от классов не зависит: подпись, которая ЦЕЛИКОМ обозначение,
     набирается математикой, кто бы её ни нарисовал. Числа на осях под правило
     не попадают — оно требует букву первой. */
  root.querySelectorAll('text').forEach(t => {
    const kind = chartLabelKind(chartLabelSource(t));
    if (kind === 'upright') {
      // Многобуквенное обозначение — прямое начертание, как \mathrm.
      t.style.fontFamily = "'KaTeX_Main', 'Times New Roman', serif";
      t.style.fontStyle = 'normal';
      t.dataset.mathset = 'upright';
    } else if (kind === 'italic') {
      t.style.fontFamily = "'KaTeX_Math', 'Times New Roman', serif";
      t.style.fontStyle = 'italic';
      t.dataset.mathset = 'italic';
    }
  });
}

/* Формула в том виде, в каком её считает движок. Раскрытие неявного умножения
   включается только там, где буквы и так становятся ползунками: в готовых
   экономических сценах у обозначений свой смысл, и трогать их нельзя. */
function prepExpr(expr) {
  const plain = texToPlain(expr);
  return paramsAllowed() ? expandImplicitMul(plain) : plain;
}

/* ⚠️ ФОРМУЛА ПРИХОДИТ ИЗ ПОЛЯ НА ЯЗЫКЕ LaTeX, А СЧИТАЕТ ЕЁ Math.js.
   Обычно перевод делает сам ввод (`latexToMath` в связке с MathLive), но
   надеяться на это нельзя: поле бывает и обычным, запись попадает вставкой из
   буфера, а математическое поле собирается лениво и до входа в сцену его может
   не быть вовсе. Поэтому перевод стоит ещё и ЗДЕСЬ, в единственной двери
   разбора, и раньше раскрытия неявного умножения.

   Дешёвая проверка на слэш — не преждевременная оптимизация: prepExpr зовётся
   из разбора свободных букв, то есть на каждой новой строке в поле, а подряд
   идущие символы дают подряд идущие вызовы.

   Перевод, оставивший слэш, означает незнакомую команду. Такую строку отдаём
   Math.js как есть: пусть откажет он и назовёт место, а не мы молча. */
function texToPlain(expr) {
  const s = String(expr == null ? '' : expr);
  if (s.indexOf('\\') < 0) return s;
  if (typeof latexToMath !== 'function') return s;
  try {
    const t = latexToMath(s);
    return (typeof t === 'string' && t.trim()) ? t : s;
  } catch (e) { return s; }
}

/* Свободные буквы формулы: то, что придётся чем-то заменить при расчёте.

   Запись уравнением («x + y = 10», «x^2 + y^2 = 25») разбираем по частям.
   Math.js считает «=» присваиванием и требует слева одно имя, поэтому на целом
   уравнении parse падал, а мы молча возвращали пустой список — и у формул,
   записанных уравнением (ограничение, неявная КПВ), буква-параметр не
   заводилась совсем (Н7). */
/* Память разбора (А1 · А55). Разбор формулы через math.parse дорогой, а
   freeSymbols звалась из scopeFor, то есть на КАЖДОМ вычислении функции. При
   трассировке кривой уровня это десятки тысяч разборов одной и той же строки
   за одну перерисовку: изокванта открывалась семь секунд.

   Ответ зависит от строки и от того, какие буквы заняты сценой, поэтому ключ
   составной. Набор занятых букв меняется редко (смена режима, появление поля
   ставки), и его подпись считается дёшево — без разбора формулы. */
const _freeSymCache = new Map();
function sceneReservedKey() {
  const s = sceneReserved();
  return STATE.mode + '|' + (STATE.mathSub || '') + '|' + Array.from(s).sort().join(',');
}
function freeSymbols(expr) {
  const key = sceneReservedKey() + '\u0000' + String(expr || '');
  const hit = _freeSymCache.get(key);
  if (hit) return hit;
  const res = freeSymbolsUncached(expr);
  // Память не растёт бесконечно: формул на экране единицы, а ключей за сессию
  // набирается много (каждое нажатие в поле формулы даёт новую строку).
  if (_freeSymCache.size > 400) _freeSymCache.clear();
  _freeSymCache.set(key, res);
  return res;
}

/* ⚠️ ПУСТОЙ СПИСОК БУКВ ЗНАЧИТ «БУКВ НЕТ», А НЕ «НЕ СМОГ РАЗОБРАТЬ».
   Разные ответы, а форма у них была одна: упавший разбор молча отдавал [], и
   для всякого, кто спрашивал буквы, непонятая формула была неотличима от
   «100 - x». Признак разбора носим отдельным полем на самом списке: он не
   мешает читать список как список (а его читают из десятка мест), но даёт
   спросить «а разобралось ли вообще». */
function freeSymbolsUncached(expr) {
  const out = [];
  let failed = false;
  const scan = (src) => {
    try {
      const node = math.parse(prepExpr(src));
      node.traverse((n, path, parent) => {
        if (n.type !== 'SymbolNode') return;
        // Имя функции в вызове — не параметр.
        if (parent && parent.type === 'FunctionNode' && parent.fn === n) return;
        if (isReservedName(n.name)) return;
        if (sceneReserved().has(n.name)) return;
        if (out.indexOf(n.name) < 0) out.push(n.name);
      });
    } catch (e) { failed = true; }
  };
  const s = String(expr || '');
  // Только одиночное «=»; «==», «<=», «>=», «!=» это сравнения, их не делим.
  const parts = s.split(/(?<![<>=!])=(?!=)/);
  if (parts.length === 2) { scan(parts[0]); scan(parts[1]); } else scan(s);
  // Пустая строка — это не отказ разбора, а отсутствие формулы.
  if (s.trim() && failed) Object.defineProperty(out, 'parseFailed', { value: true, enumerable: false });
  return out;
}

/* Буквы, занятые самой сценой. У сюжетов есть свои обозначения со своими
   полями (ставка t, зарплата w, мировая цена Pw), и подсовывать им ползунок
   нельзя: получится два хозяина у одного числа. */
function sceneReserved() {
  if (STATE.mode === 'math') {
    // В «Оптимуме при ограничении» a и b — это оси, а не параметры.
    if (STATE.mathSub === 'constraint') return new Set(['a', 'b']);
    return new Set();
  }
  // Занято ровно там, где у буквы и правда есть свой хозяин: ставка налога и
  // субсидии — пока на экране поле ставки, зарплата — на рынке труда. В остальных
  // сценах те же буквы свободны и становятся обычными ползунками. Смотрим на
  // само поле, а не на STATE.intervType: тип вмешательства держится в состоянии
  // всегда, даже там, где блока вмешательства нет и в помине.
  const s = new Set();
  const taxField = document.getElementById('tax-field');
  if (taxField && fieldActive(taxField)) { s.add('t'); s.add('s'); }
  if (STATE.mode === 'labor') s.add('w');
  return s;
}

/* Буквы, которые нужны САМОЙ сцене, даже если в формуле их нет (П26).
   «Деформации графика» двигают кривую параметром a, а формулу пишут без него —
   раньше у сюжета был свой ползунок с собственной разметкой и обвязкой, копия
   общего механизма. Теперь сцена просто заявляет букву, а всё остальное —
   вид, границы, шаг, точный ввод, крестик — берётся из общего кода. */
function sceneExtraParams() {
  if (STATE.mode === 'math' && STATE.mathSub === 'transform') return ['a'];
  return [];
}

// Значение параметра с запасным вариантом: сцены читают его вместо своего поля.
function paramValue(name, fallback) {
  const p = (STATE.params || {})[name];
  return (p && isFinite(p.value)) ? p.value : fallback;
}

// Значения параметров подмешиваются в КАЖДЫЙ расчёт формулы.
function paramScope(ctx) {
  const p = STATE.params || {};
  Object.keys(p).forEach(k => { if (ctx[k] === undefined) ctx[k] = p[k].value; });
  return ctx;
}

/* Контекст расчёта для конкретной формулы: сначала значения ползунков, потом
   единица для буквы, ползунка у которой ещё нет. Второе нужно на пробном
   расчёте при разборе: ползунок заводится уже ПОСЛЕ того, как формула принята,
   и без этого «a - Q» падало бы с «Undefined symbol a». */
function scopeFor(expr, ctx) {
  const c = paramScope(ctx || {});
  try { freeSymbols(expr).forEach(n => { if (c[n] === undefined) c[n] = 1; }); } catch (e) {}
  return c;
}

// Расчёт с параметрами: буква, для которой ползунка ещё нет, считается единицей.
function evalWithParams(compiled, ctx, expr) {
  const c = paramScope(ctx);
  try { return compiled.evaluate(c); }
  catch (e) {
    if (!paramsAllowed()) throw e;
    freeSymbols(expr).forEach(n => { if (c[n] === undefined) c[n] = 1; });
    return compiled.evaluate(c);
  }
}

// Завести ползунки для новых букв, забыть те, которых больше нигде нет.
function syncParams() {
  if (!paramsAllowed()) {
    if (Object.keys(STATE.params || {}).length) { STATE.params = {}; updatePult(); }
    return;
  }
  const names = [];
  /* ⚠️ БУКВА НЕ ПРОПАДАЕТ ИЗ-ЗА ПОЛУНАБРАННОЙ ФОРМУЛЫ.
     Замер 22.08: ползунок «a» уводили на 3,5 и продолжали править формулу.
     Стирание звёздочки даёт промежуточную запись «y = 100 - a*», разбор её не
     берёт, freeSymbols отдаёт пустой список — и проход удаления сносил живой
     ползунок. Следующая нажатая клавиша возвращала его со значением 1: набранное
     человеком число исчезало под рукой, а виноватой выглядела кривая.
     Пока хоть одна формула на экране не разобралась, только ДОБАВЛЯЕМ буквы;
     уборка лишних ждёт, пока запись снова станет целой. Ждать недолго — это
     ровно то время, пока человек дописывает формулу. */
  let pending = false;
  const take = (expr) => {
    if (!expr) return;
    const got = freeSymbols(expr);
    if (got.parseFailed) pending = true;
    got.forEach(n => { if (names.indexOf(n) < 0) names.push(n); });
  };
  /* ⚠️ Вторая половина договора о параметрах. Карточку списка сцена уже не
     показывает (syncCurveListVisibility), но сами кривые в STATE.curves у неё
     остаются — их кладёт пресет монополии. Пока буквы из них заводили ползунки,
     рычаг оставался молчащим, просто без своей карточки. */
  if (typeof sceneDrawsCurveList !== 'function' || sceneDrawsCurveList()) {
    STATE.curves.forEach(c => take(c.expr));
  }
  if (STATE.mode === 'math') [STATE.mathFormula, STATE.mathG2, STATE.mathG3, STATE.mathG4].forEach(take);
  // Формулы сцен (КПВ, издержки, макро, полезность и прочие) живут не в
  // STATE.curves, а в своих полях ввода. Берём их из общего реестра — только
  // те поля, чья секция сейчас на экране, иначе спрятанные сцены наплодили бы
  // ползунков для букв, которых пользователь не видит.
  liveFormulaTexts().forEach(take);
  sceneExtraParams().forEach(n => { if (names.indexOf(n) < 0) names.push(n); });
  STATE.params = STATE.params || {};
  let changed = false;
  names.forEach(n => {
    if (!STATE.params[n]) { STATE.params[n] = { value: 1, min: -10, max: 10, step: 0.1 }; changed = true; }
  });
  if (!pending) Object.keys(STATE.params).forEach(n => {
    if (names.indexOf(n) < 0) { delete STATE.params[n]; changed = true; }
  });
  if (changed) {
    const panel = document.getElementById('params-panel');
    if (panel) panel._extraSig = PULT_REBUILD;     // пересобрать правую панель
    updatePult();
  }
}

/* Один ползунок параметра. Обычный вид — только буква, её значение и ползунок,
   по краям которого написаны границы. Щелчок по границе раскрывает маленький
   редактор «−10 ≤ a ≤ 10» с шагом; закрыл — снова обычный ползунок.
   Четыре числовых поля разом, как было раньше, читались как приборная панель,
   хотя нужны один раз на всю задачу. */
function buildParamChip(box, name) {
  const p = STATE.params[name];
  const { chip, lab, val } = makePchip(name, fmt(p.value), null);
  chip.classList.add('pchip-param');

  /* П23. Значение — набранная формула «a = 1», как у Desmos: курсивная буква,
     знак равенства, число. Раньше буква и число были обычным текстом в разных
     углах строки. Печатает KaTeX; нет CDN — остаётся тот же текст, что и был. */
  const paintEq = () => paintEqLabel(lab, name, p.value);

  /* Точное значение (П24): отдельного поля нет, щёлкают прямо по формуле.
     Число справа при этом лишнее — вся строка «a = 1» и есть значение. */
  val.style.display = 'none';
  lab.classList.add('pchip-editable');
  lab.setAttribute('data-tip', 'Щёлкните, чтобы ввести точное значение');

  /* Крестик справа вверху — как у Desmos. У нас параметр не объявляют строкой,
     а выводят из формулы, поэтому «удалить» его насовсем нельзя: syncParams
     завёл бы его заново на следующей перерисовке, а формула осталась бы без
     значения. Поэтому крестик СВОРАЧИВАЕТ ползунок: буква держит своё нынешнее
     значение, строка ужимается до «a = 1», а щелчок по ней разворачивает
     обратно. Чтобы убрать параметр совсем, букву стирают из формулы (П18). */
  const kill = document.createElement('button');
  kill.type = 'button'; kill.className = 'param-kill';
  kill.textContent = '✕';
  kill.setAttribute('data-tip', 'Свернуть ползунок (буква останется с этим значением)');
  chip.querySelector('.pchip-top').appendChild(kill);

  const track = document.createElement('div');
  track.className = 'param-track';
  const loLab = document.createElement('button');
  loLab.type = 'button'; loLab.className = 'param-bound';
  loLab.setAttribute('data-tip', 'Границы и шаг');
  const hiLab = document.createElement('button');
  hiLab.type = 'button'; hiLab.className = 'param-bound';
  hiLab.setAttribute('data-tip', 'Границы и шаг');

  const sl = document.createElement('input');
  sl.type = 'range'; sl.style.accentColor = cssVar('--accent');
  track.append(loLab, sl, hiLab);
  chip.appendChild(track);

  const editor = document.createElement('div');
  editor.className = 'param-editor';
  chip.appendChild(editor);
  /* Объявлено ЗАРАНЕЕ: обработчики ниже читают bounds, а создаётся он в
     конце функции. С const это была бы временная мёртвая зона, и охрана
     «bounds && bounds.close» бросала бы ReferenceError вместо того, чтобы
     тихо пропустить вызов. */
  let bounds = null;

  const syncSlider = () => {
    sl.min = p.min; sl.max = p.max; sl.step = Math.max(1e-9, p.step);
    sl.value = p.value;
    loLab.textContent = fmt(p.min);
    hiLab.textContent = fmt(p.max);
    val.textContent = fmt(p.value);
    paintEq();
  };
  syncSlider();

  // Свёрнутое состояние: остаётся только строка «a = 1» и знак развернуть.
  const applyFold = () => {
    chip.classList.toggle('folded', !!p.folded);
    kill.textContent = p.folded ? '＋' : '✕';
    kill.setAttribute('data-tip', p.folded ? 'Показать ползунок'
                                          : 'Свернуть ползунок (буква останется с этим значением)');
  };
  applyFold();
  kill.addEventListener('click', (e) => { e.stopPropagation(); p.folded = !p.folded; applyFold(); });

  sl.addEventListener('input', () => {
    p.value = parseFloat(sl.value);
    val.textContent = fmt(p.value);
    paintEq();
    if (bounds && bounds.close) bounds.close();   // Н10: тронули ползунок — меню закрылось
    redrawKeepingWindow();     // окно подбирается под формулу, а не под значение буквы
  });

  /* Н12: щёлкнули по значению — «a =» остаётся на месте, правится только число
     справа, и набор не превращается в системный шрифт. Н10: точный ввод
     закрывает меню интервала. */
  lab.addEventListener('click', () => {
    if (p.folded) { p.folded = false; applyFold(); return; }   // свёрнутый — сначала разворачиваем
    if (bounds && bounds.close) bounds.close();
    editEqValue(lab, name, p.value, (v) => {
      /* Случай первый (см. разбор у centerBandOn): вписали значение за полосой —
         полоса переезжает так, чтобы значение встало ровно посередине, ширина
         сохраняется. Раньше граница просто раздвигалась до значения, и полоса
         становилась неуправляемо длинной. */
      if (v < p.min || v > p.max) {
        const b = centerBandOn({ min: p.min, max: p.max }, v);
        p.min = b.min; p.max = b.max;
      }
      p.value = v;
      syncSlider();
      redrawKeepingWindow();
    });
  });

  /* Меню интервала — общее с регуляторами сцен: «мин ≤ a ≤ макс» и шаг, всё
     набрано формулой, без кнопки «Готово» (Н9), с живым обновлением на каждый
     введённый символ и закрытием по щелчку мимо (Н10). */
  bounds = attachBoundsEditor(chip, editor, name,
    (key) => p[key],
    (key, v) => {
      p[key] = v;
      if (p.max <= p.min) p.max = p.min + 1;
      // Случай второй: границы заданы человеком и остаются как заданы,
      // подтягивается ЗНАЧЕНИЕ — к ближайшей границе.
      p.value = pullIntoBand({ min: p.min, max: p.max }, p.value);
      syncSlider();
      redrawKeepingWindow();
    });
  loLab.addEventListener('click', () => bounds.open('min'));
  hiLab.addEventListener('click', () => bounds.open('max'));

  box.appendChild(chip);
}

/* Цвета кривых сцены (издержки, производство, вееры, «Математика»).
   В шаблоне это нативные input[type=color]; подменяем их на общий компонент
   с шестью образцами (П34), сохраняя data-col — по нему идёт синхронизация. */
function initSceneColorPickers() {
  document.querySelectorAll('input.swatch-pick[data-col]').forEach(inp => {
    const key = inp.dataset.col;
    const pick = makeColorPicker(COL[key] || inp.value, (hex) => {
      STATE.colorOverride[key] = hex;
      redrawAll();
    }, inp.title || 'Цвет кривой');
    pick.setAttribute('data-col', key);
    inp.replaceWith(pick);
  });
  syncSceneColorPickers();
}
function syncSceneColorPickers() {
  document.querySelectorAll('.cpick[data-col]').forEach(pick => {
    const v = COL[pick.dataset.col];
    if (v && pick._setValue) pick._setValue(v);
  });
}

// Плейсхолдеры полей «Ось X/Y» показывают, что нарисует сцена, если оставить пусто.
function syncAxisPlaceholders() {
  const x = document.getElementById('inp-xname'), y = document.getElementById('inp-yname');
  if (x) x.placeholder = STATE.axisXDefault || 'Q';
  if (y) y.placeholder = STATE.axisYDefault || 'P';
}

// Заголовок графика по центру верхнего поля.
/* Н22. Название графика правится и переносится прямо на холсте.

   Место хранится в ДОЛЯХ поля (0…1), а не в пикселях: холст меняет размер при
   сворачивании панелей, и пиксельные координаты уехали бы. Пока пользователь
   подпись не двигал, она стоит по центру верхнего поля, как раньше.

   Двойной щелчок по холсту возвращает масштаб, поэтому на самой подписи он
   останавливается (stopPropagation) и вместо этого открывает правку. */
function titleAnchorPx() {
  const m = CONFIG.margin;
  const x0 = m.left, x1 = W - m.right, y0 = 0, y1 = H - m.bottom;
  const p = STATE.titlePos;
  if (p && isFinite(p.fx) && isFinite(p.fy)) {
    return { x: x0 + (x1 - x0) * p.fx, y: y0 + (y1 - y0) * p.fy };
  }
  return { x: (x0 + x1) / 2, y: Math.max(17, m.top - 11) };
}

function drawGraphTitle() {
  const t = (STATE.graphTitle || '').trim();
  if (!t) return;
  const at = titleAnchorPx();
  const el = svg.append('text').attr('class', 'graph-title')
    .attr('x', at.x).attr('y', at.y)
    .attr('text-anchor', 'middle').attr('font-size', FS.large).attr('font-weight', 650)
    .attr('fill', STATE.titleColor || COL.ink)
    /* Обводка цветом холста: если подпись всё же легла на кривую, она читается
       поверх неё, а не сливается (Н22). */
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 3)
    .style('cursor', 'move')
    .text(t);

  // Название графика тянут и правят двойным щелчком; про это сказано в меню
  // координатной плоскости, где это название и вводят.

  // Перетаскивание: запоминаем долю поля, а не пиксели.
  el.call(d3.drag().container(() => svg.node())
    .on('start', (ev) => { ev.sourceEvent.stopPropagation(); })
    .on('drag', (ev) => {
      ev.sourceEvent.stopPropagation();      // не тянем ни поле, ни кривую
      const m = CONFIG.margin;
      const x0 = m.left, x1 = W - m.right, y0 = 0, y1 = H - m.bottom;
      const fx = Math.max(0, Math.min(1, (ev.x - x0) / Math.max(1, x1 - x0)));
      const fy = Math.max(0, Math.min(1, (ev.y - y0) / Math.max(1, y1 - y0)));
      STATE.titlePos = { fx, fy };
      redrawAll();
    }));

  el.on('dblclick', (ev) => {
    ev.stopPropagation();                    // двойной щелчок НЕ сбрасывает масштаб
    ev.preventDefault();
    editGraphTitleOnCanvas(at);
  });
}

/* Правка названия на месте: поле ввода поверх холста, ровно там, где стоит сама
   подпись, тем же кеглем. Рядом выбор цвета, чтобы не искать его в меню. */
function editGraphTitleOnCanvas(at) {
  const wrap = document.getElementById('graph-wrap');
  if (!wrap || wrap.querySelector('.title-edit')) return;
  const box = document.createElement('div');
  box.className = 'title-edit';
  box.style.left = at.x + 'px';
  box.style.top = (at.y - 14) + 'px';

  const inp = document.createElement('input');
  inp.type = 'text';
  inp.value = STATE.graphTitle || '';
  inp.setAttribute('aria-label', 'Название графика');

  const pick = makeColorPicker(STATE.titleColor || COL.ink, (hex) => {
    STATE.titleColor = hex;
    const f = document.getElementById('gtitle-color-slot');
    if (f && f._setValue) f._setValue(hex);
    redrawAll();
  }, 'Цвет названия');

  const close = () => {
    STATE.graphTitle = inp.value;
    const f = document.getElementById('inp-gtitle');
    if (f) f.value = inp.value;              // поле в меню плоскости идёт следом
    box.remove();
    redrawAll();
  };
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); close(); }
    if (e.key === 'Escape') { e.preventDefault(); box.remove(); }
  });
  inp.addEventListener('blur', () => setTimeout(() => { if (box.isConnected && !box.contains(document.activeElement)) close(); }, 120));

  box.append(inp, pick);
  wrap.appendChild(box);
  inp.focus();
  const n = inp.value.length;
  try { inp.setSelectionRange(n, n); } catch (e) {}
}

/* Пикер цвета (Фаза 2) — переиспользуемый для ЛЮБОГО списка кривых.
   Нативный <input type="color"> под видом того же квадратика-образца: сторонняя
   библиотека не нужна. Меняет цвет только у своего экземпляра кривой; файл
   дизайн-токенов (--curve-*, --cost-*) остаётся нетронутым и служит палитрой
   по умолчанию — колорблайнд-безопасной точкой отсчёта. */
function normHex(c) {
  const s = String(c || '').trim();
  if (/^#[0-9a-f]{6}$/i.test(s)) return s;
  if (/^#[0-9a-f]{3}$/i.test(s)) return '#' + s[1] + s[1] + s[2] + s[2] + s[3] + s[3];
  const m = s.match(/rgba?\(\s*(\d+)\D+(\d+)\D+(\d+)/i);
  if (m) return '#' + [1, 2, 3].map(i => (+m[i]).toString(16).padStart(2, '0')).join('');
  /* Разобрать не удалось. Нейтральный цвет берём ИЗ ТОКЕНА, а не числом.
     ⚠️ Рекурсией сюда возвращаться нельзя: если у токена пустое значение,
     `normHex(cssVar(...))` позвал бы сам себя без конца. Поэтому значение
     токена разбирается тем же кодом ОДИН раз, через флаг. */
  if (!normHex._deep) {
    normHex._deep = true;
    const t = cssVar('--text3');
    normHex._deep = false;
    if (t) { const v = normHex(t); if (v) return v; }
  }
  return '#888888';                       // запасное значение, если токена нет
}
/* Шесть предложенных цветов (П34). Значения живут в токенах --pal-1…--pal-6,
   поэтому светлая и тёмная тема дают РАЗНЫЕ образцы, а перекрашивание темы
   само подтягивает новые. Читаем через cssVar на каждый показ меню: тему
   переключают прямо во время работы. */
function paletteSix() {
  const out = [];
  for (let i = 1; i <= 6; i++) out.push(normHex(cssVar('--pal-' + i)));
  return out;
}

let openCPick = null;   // единственное открытое меню цвета

function closeColorMenu() {
  if (!openCPick) return;
  // Нативный input живёт в обёртке кнопки, а в меню только гостит: иначе он
  // уехал бы в мусор вместе с меню и «Свой цвет» перестал бы работать.
  if (openCPick._own && openCPick._owner) {
    openCPick._own.style.display = 'none';
    openCPick._owner.appendChild(openCPick._own);
  }
  openCPick.remove();
  openCPick = null;
  document.removeEventListener('pointerdown', onDocClosePick, true);
  window.removeEventListener('resize', closeColorMenu);
  window.removeEventListener('keydown', onEscClosePick, true);
}
function onDocClosePick(e) {
  if (openCPick && (openCPick.contains(e.target) || (openCPick._owner && openCPick._owner.contains(e.target)))) return;
  closeColorMenu();
}
function onEscClosePick(e) { if (e.key === 'Escape') closeColorMenu(); }

/* Выбор цвета: ряд из шести образцов плюс «Свой цвет» (П34).
   Возвращает ОБЁРТКУ, а не сам input: меню уезжает в <body> с position:fixed,
   иначе панель с прокруткой обрезала бы его по своему краю.
   ВАЖНО: из onChange нельзя перерисовывать список, в котором живёт эта кнопка,
   иначе нативная палитра «Своего цвета» захлопнется на первом же клике. */
function makeColorPicker(value, onChange, title) {
  const wrap = document.createElement('span');
  wrap.className = 'cpick';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'swatch cpick-btn';
  btn.setAttribute('data-tip', title || 'Цвет кривой');

  // Скрытый нативный input — только под кнопку «Свой цвет». Держим его тут,
  // чтобы пикер цвета не пропадал вместе с меню при переоткрытии.
  const own = document.createElement('input');
  own.type = 'color';

  let cur = normHex(value);
  const paint = () => { btn.style.background = cur; own.value = cur; };
  paint();

  const apply = (hex) => { cur = normHex(hex); paint(); onChange(cur); };
  own.addEventListener('input', () => apply(own.value));

  btn.addEventListener('click', (e) => {
    e.preventDefault(); e.stopPropagation();
    const was = openCPick && openCPick._owner === wrap;
    closeColorMenu();
    if (was) return;                       // повторный щелчок закрывает меню

    const menu = document.createElement('div');
    menu.className = 'cpick-menu';
    menu.setAttribute('role', 'dialog');
    menu.setAttribute('aria-label', btn.title);
    const grid = document.createElement('div');
    grid.className = 'cpick-grid';
    paletteSix().forEach((hex) => {
      const sw = document.createElement('button');
      sw.type = 'button';
      sw.className = 'cpick-sw';
      sw.style.background = hex;
      sw.setAttribute('role', 'radio');
      sw.setAttribute('aria-checked', hex.toLowerCase() === cur.toLowerCase() ? 'true' : 'false');
      sw.setAttribute('data-tip', hex);
      sw.addEventListener('click', (ev) => { ev.stopPropagation(); apply(hex); closeColorMenu(); });
      grid.appendChild(sw);
    });
    menu.appendChild(grid);

    const ownRow = document.createElement('label');
    ownRow.className = 'cpick-own';
    own.style.display = '';
    ownRow.append(own, document.createTextNode('Свой цвет'));
    ownRow.addEventListener('click', (ev) => ev.stopPropagation());
    menu.appendChild(ownRow);

    document.body.appendChild(menu);
    menu._owner = wrap;
    menu._own = own;
    openCPick = menu;

    // Ставим под кнопкой, а если снизу не хватает места — над ней.
    const r = btn.getBoundingClientRect();
    const mh = menu.offsetHeight, mw = menu.offsetWidth;
    let top = r.bottom + 6;
    if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 6);
    let left = r.left;
    if (left + mw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - mw - 8);
    menu.style.top = top + 'px';
    menu.style.left = left + 'px';

    document.addEventListener('pointerdown', onDocClosePick, true);
    window.addEventListener('resize', closeColorMenu);
    window.addEventListener('keydown', onEscClosePick, true);
  });

  own.style.display = 'none';
  wrap.append(btn, own);
  wrap._setValue = (hex) => { cur = normHex(hex); paint(); };
  return wrap;
}

// Короткое имя кривой для подписей: своё имя → роль → формула.
/* Короткое имя кривой: своё, потом по роли, потом автоимя. Свх-2: у кривой,
   которую пользователь добавил сам, роли нет, и раньше именем становилась вся
   формула — в чипе панели и в легенде стояло «100 - a*Q» вместо обозначения.
   Даём буквы f, g, h… (общепринятое «некоторая функция»), они не спорят ни с
   одной ролью. Имя закрепляется за кривой один раз, поэтому при правке формулы
   не прыгает; полная формула остаётся подсказкой при наведении. */
const AUTO_CURVE_LETTERS = ['f', 'g', 'h', 'k', 'u', 'v', 'w', 'z'];
function autoCurveName(c) {
  if (c._auto) return c._auto;
  // Заняты только буквы кривых, которые СЕЙЧАС живут без роли: получившая роль
  // кривая зовётся по ней, и держать за собой букву ей незачем.
  const taken = new Set((STATE.curves || []).filter(x => x !== c && !x.role).map(x => x._auto).filter(Boolean));
  const free = AUTO_CURVE_LETTERS.find(l => !taken.has(l));
  c._auto = free || ('Кривая ' + ((STATE.curves || []).indexOf(c) + 1));
  return c._auto;
}
function curveShortName(c) {
  const custom = (c.label || '').trim();
  if (custom) return custom;
  const byRole = { demand: 'D', supply: 'S', mc: 'MC', tc: 'TC', atc: 'ATC' };
  if (c.role && byRole[c.role]) return byRole[c.role];
  return autoCurveName(c);
}

// Строки подписи своей точки: текст пользователя + по галочкам координаты
// и значения видимых кривых в этой точке.
function markCaption(mk) {
  const parts = [];
  if (mk.text) parts.push(mk.text);
  if (mk.showCoords) parts.push('(' + fmt(mk.x) + '; ' + fmt(mk.y) + ')');
  // Значения кривых в точке убраны по П29: подпись из четырёх строк накрывала
  // сам график, а нужное число всегда видно по кривой и осям.
  return parts;
}

function drawMarks() {
  if (!STATE.marks || !STATE.marks.length) return;
  const g = svg.append('g').attr('class', 'marks');
  STATE.marks.forEach(mk => {
    // Точка, у которой заполнено ещё не всё, на плоскости не появляется (П28).
    if (mk.pending || !isFinite(mk.x) || !isFinite(mk.y)) return;
    const ms = mainScales(markPanelId(mk));
    const mx = ms.mx, my = ms.my;
    const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
    if (mk.x < xLo || mk.x > xHi || mk.y < yLo || mk.y > yHi) return;
    const px = mx(mk.x), py = my(mk.y);
    const col = mk.color || COL.ink;
    // Пунктирные проекции на оси — как у равновесия: так точка читается по осям.
    if (mk.showDash !== false) {
      g.append('line').attr('x1', mx(0)).attr('y1', py).attr('x2', px).attr('y2', py)
        .attr('stroke', COL.inkSoft).attr('stroke-width', 1)
        .attr('stroke-dasharray', '3 3').attr('opacity', .5);
      g.append('line').attr('x1', px).attr('y1', my(0)).attr('x2', px).attr('y2', py)
        .attr('stroke', COL.inkSoft).attr('stroke-width', 1)
        .attr('stroke-dasharray', '3 3').attr('opacity', .5);
    }
    g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4.5)
      .attr('fill', col).attr('stroke', COL.halo).attr('stroke-width', 1.6)
      .style('cursor', 'move')
      /* Перетаскивание (П30) с сопротивлением при отрыве (П31).
         Пока точка сидит на линии, она скользит по ней и НЕ срывается от
         небольшого увода курсора: оторвать её можно, только уведя дальше
         RELEASE_PX (в два с половиной раза больше радиуса захвата). Свободная
         точка, наоборот, прилипает, как только курсор подошёл ближе SNAP_PX —
         и к кривым, и к осям. */
      .call(d3.drag().container(() => svg.node()).on('drag', ev => {
        if (mk.snapTo && snapDistPx(mk.snapTo, ev.x, ev.y) > RELEASE_PX) mk.snapTo = null;
        /* Н41: тот же магнит, что при постановке. Ключевая точка перехватывает
           первой — в неё точка «падает» и стоит ровно в ней, а не скользит по
           одной из кривых мимо перекрестья. */
        const key = snapVertexAt(ev.x, ev.y);
        // Магнит соседней панели точке не хозяин: она живёт в своей.
        const own = (h) => h && markPanelId(h) === markPanelId(mk);
        if (key && key.key && own(key)) { mk.snapTo = null; mk.x = key.x; mk.y = key.y; renderMarkList(); redrawAll(); return; }
        if (!mk.snapTo) {
          const hit = snapPointAt(ev.x, ev.y);
          if (hit && !hit.cross && own(hit)) mk.snapTo = hit.name;
        }
        if (mk.snapTo === 'ось Y') {
          mk.x = 0;
          mk.y = Math.max(yLo, Math.min(yHi, my.invert(ev.y)));
        } else if (mk.snapTo === 'ось X') {
          mk.x = Math.max(xLo, Math.min(xHi, mx.invert(ev.x)));
          mk.y = 0;
        } else if (mk.snapTo === 'начало координат') {
          mk.x = 0; mk.y = 0;
        } else {
          mk.x = Math.max(xLo, Math.min(xHi, mx.invert(ev.x)));
          // Точка на кривой скользит ПО ней: тянем вдоль оси X, высоту берём
          // с самой кривой.
          const f = markSnapFn(mk);
          const onCurve = f ? f(mk.x) : NaN;
          mk.y = isFinite(onCurve) ? onCurve
               : Math.max(yLo, Math.min(yHi, my.invert(ev.y)));
        }
        renderMarkList(); redrawAll();
      }));
    // Подпись растёт ВВЕРХ от точки, чтобы не накрывать её саму.
    const lines = markCaption(mk);
    lines.forEach((s, i) => {
      const ty = py - 9 - (lines.length - 1 - i) * 13;
      const t = g.append('text').attr('x', px + 9).attr('y', ty)
        .attr('font-size', FS.base).attr('font-weight', i === 0 ? 650 : 500).attr('fill', col)
        .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 2.6)
        .text(s);
      // Первая строка — имя точки, его и правим двойным щелчком.
      if (i === 0) makeRenamable(t, mk.text, px + 9, ty, (v) => { mk.text = v; renderMarkList(); });
    });
  });
}

/* ---------------------------------------------------------------------
   ПРИЛИПАНИЕ ТОЧЕК К КРИВЫМ
   Попасть щелчком ровно в кривую мышью невозможно, а точка нужна именно НА
   ней: «отметьте выпуск при цене 60» теряет смысл, если отметка висит рядом.
   Поэтому щелчок в пределах нескольких пикселей от кривой сажает точку на
   кривую, а щелчок в пустом месте оставляет её там, где щёлкнули.
   Если рядом сразу две кривые, метят почти наверняка в их пересечение:
   там и ставим, честно решая f1(x) = f2(x).
   --------------------------------------------------------------------- */
const SNAP_PX = 14;      // на каком расстоянии от линии щелчок считается «в неё»
const RELEASE_PX = 35;   // а на каком уже отрывается (П31: отпустить труднее, чем прилипнуть)

// К чему можно прилипнуть в текущей сцене. Кривые берём готовыми функциями:
// откуда они взялись, прилипанию знать не нужно.
/* ⚠️ У КРИВОЙ ЕСТЬ ПАНЕЛЬ, И ПРИТЯГИВАТЬСЯ К НЕЙ МОЖНО ТОЛЬКО В НЕЙ.

   `snapTargets()` отдаёт кривые ПАНЕЛИ ПОД КУРСОРОМ. Раньше список был один на
   всю сцену, и в сюжете про производную мышь на НИЖНЕЙ панели липла к f(x),
   которой там нет: обе панели спрашивали один и тот же список.

   Поле `panel` ставится только там, где панелей в сцене больше одной. Кривая
   БЕЗ этого поля принадлежит любой панели — так однопанельные сцены (а их 38
   из 44) не приходится размечать поштучно, и правило у них не меняется. */
function snapTargets(panelId) {
  const all = snapTargetsAll();
  const list = STATE.panels || [];
  const id = (panelId != null) ? panelId : (activePanel() ? activePanel().id : null);
  if (!id || !list.some(p => p.id === id)) return all;
  return all.filter(t => !t.panel || t.panel === id);
}

function snapTargetsAll() {
  const out = [];
  if (STATE.mode === 'costs' && STATE.costsSub === 'costs' && STATE.costsReady) {
    if (STATE.showMC)  out.push({ name: 'MC',  f: costMC });
    if (STATE.showATC) out.push({ name: 'ATC', f: costATC });
    if (STATE.showAVC) out.push({ name: 'AVC', f: costAVC });
    if (STATE.showAFC) out.push({ name: 'AFC', f: costAFC });
    return out;
  }
  // Было условие на STATE.prodReady, которого в состоянии нет вовсе, поэтому
  // ветка не срабатывала никогда и в «Производственной функции» точка не каталась.
  if (STATE.mode === 'costs' && STATE.costsSub === 'production' && STATE.prodCompiled) {
    // TP нарисован на ВЕРХНЕЙ панели: на нижней стоят MP и AP, и притягиваться
    // там к общему продукту нечему.
    out.push({ name: 'TP', f: prodEval, panel: 'prod-top' });
    return out;
  }
  /* Дискриминация 3-й степени и «Монополист и внешний рынок»: два мини-рынка,
     у каждого свой спрос, и предельные издержки общие. Кривые лежат в
     STATE.discr3, а не в STATE.curves, поэтому раньше список молча
     проваливался в общую ветку и отдавал спрос с издержками ГЛАВНОЙ сцены
     монополии — кривые, которых на этом холсте нет вовсе. */
  if (STATE.mode === 'market' && STATE.market === 'monopoly'
      && STATE.monoMode === 'discr3' && STATE.discr3 && STATE.discr3.found) {
    const d = STATE.discr3;
    const nm1 = STATE.d3World ? 'D внутри' : 'D₁';
    const nm2 = STATE.d3World ? 'Pw' : 'D₂';
    out.push({ name: nm1, f: (q) => evalCurve(d.c1, q), color: COL.D, panel: 'mini-1' });
    out.push({ name: nm2, f: (q) => evalCurve(d.c2, q), color: COL.D, panel: 'mini-2' });
    out.push({ name: 'MC₁', f: (q) => evalCurve(d.cm, q), color: COL.S, panel: 'mini-1' });
    out.push({ name: 'MC₂', f: (q) => evalCurve(d.cm, q), color: COL.S, panel: 'mini-2' });
    return out;
  }
  // Изокванта задана уровнем выпуска, а не формулой K = f(L): её точки считает
  // общий движок касания уровня, по ним и катаемся.
  if (STATE.mode === 'costs' && STATE.costsSub === 'isoquant' && STATE.iso) {
    const s = mainScales();
    const pts = traceLevelCurve(STATE.iso.f, STATE.iso.Q, s.mx.domain()[1], s.my.domain()[1] * 6, 220);
    if (pts && pts.length) out.push({ name: 'изокванта', f: (l) => interpY(pts, l) });
    return out;
  }
  /* Два завода: катаемся по ТОЙ кривой, что сейчас нарисована (Б9). Раньше
     здесь всегда стояла совокупная MC, даже когда на экране совокупная TC.
     Ключевые точки строятся по этому же списку, поэтому на графике затрат
     появлялась точка «излом MC» в (150; 200) — координаты правильные для MC,
     но на оси до 40 000 она ложилась на самую ось и в выгрузку уходила
     точкой ниоткуда. Обе кривые посчитаны одной таблицей, выбрать нужную
     дёшево. */
  if (STATE.mode === 'costs' && STATE.costsSub === 'plants' && STATE.plants) {
    const p = STATE.plants;
    const mc = (STATE.plView === 'mc');
    const pts = p.table.map(r => [r.Q, mc ? r.m : r.tcDirect]);
    out.push({ name: mc ? 'MC' : 'TC', f: (q) => interpY(pts, q) });
    return out;
  }
  if (STATE.mode === 'ppf' && STATE.ppfSub === 'single' && STATE.ppfReady) {
    // Обе кривые сравнения: тогда и в площадях есть выбор, под какой считать,
    // и точки пересечения между ними находятся сами (Фаза 12.6).
    out.push({ name: STATE.ppfName1 || 'КПВ', f: evalPpf, color: STATE.ppfColor1 || null });
    if (STATE.ppfF2) out.push({ name: STATE.ppfName2 || 'КПВ 2', f: evalPpf2, color: STATE.ppfColor2 || null });
    return out;
  }
  // Сумма КПВ: суммарная кривая посчитана по точкам (Минковский), исходные —
  // тоже. Катаемся и по сумме, и по слагаемым.
  if (STATE.mode === 'ppf' && STATE.ppfSub === 'sum') {
    const d = STATE.ppfSumData;
    if (d && d.ok) {
      out.push({ name: 'Сумма', f: (x) => interpY(d.points, x) });
      out.push({ name: 'КПВ 1', f: (x) => interpY(d.c1pts, x) });
      out.push({ name: 'КПВ 2', f: (x) => interpY(d.c2pts, x) });
    }
    return out;
  }
  // Торговля: КПВ страны плюс линия торговых возможностей, если она построена.
  if (STATE.mode === 'ppf' && STATE.ppfSub === 'trade') {
    tradeSnapTargets(out);
    return out;
  }
  if (STATE.mode === 'math') { mathSnapTargets(out); return out; }
  if (STATE.mode === 'macro')      { macroSnapTargets(out); return out; }
  if (STATE.mode === 'consumer')   { consumerSnapTargets(out); return out; }
  if (STATE.mode === 'inequality') { ineqSnapTargets(out); return out; }
  STATE.curves.filter(c => c.visible && !isVertical(c)).forEach(c => {
    /* Цвет и сама кривая нужны взведению (фаза 3): загоревшаяся точка красится
       цветом своей кривой, а полоса попадания должна знать, какую кривую
       взводит. Раньше сюда попадало только имя и функция. */
    out.push({ name: curveShortName(c), f: (q) => evalCurve(c, q), color: c.color, curve: c });
  });
  return out;
}

/* П21. Кривые макромоделей, потребителя и неравенства.

   Полоса захвата и ключевые точки строятся по одному списку (snapTargets),
   поэтому кривая, которой здесь нет, не только не взводится щелчком, но и не
   отдаёт своих пересечений. Замер 21.08: полосы не было ни в одной из десяти
   сцен этих трёх режимов, хотя кривые в них есть и они главные.

   Вертикальные кривые (LRAS, Ms, долгосрочная Филлипса) не берём — по ним
   не катаются, ровно как в общей ветке ниже.

   Одиннадцатая сцена без полосы — «Построение графиков»: она открывается
   пустым холстом, и полоса появляется вместе с первой же кривой. Это не
   пробел, а её устройство. */
function macroSnapTargets(out) {
  const r = STATE.macroRes;
  if (!r) return;
  if (r.kind === 'laffer') {
    if (r.pts && r.pts.length) {
      out.push({ name: 'Поступления', f: (t) => interpY(r.pts, t), color: COL.tax });
    }
    return;
  }
  [].concat(r.extra || [], r.curves || []).forEach(([lab, c, col]) => {
    if (!c || typeof c.fn !== 'function' || isVertical(c)) return;
    out.push({ name: lab, f: (x) => { const v = c.fn(x); return isFinite(v) ? v : NaN; }, color: col });
  });
}

/* Потребитель. Бюджетная линия задана перехватами, кривая безразличия — уровнем
   полезности: её точки считает тот же движок касания уровня, что рисует её на
   холсте, второй математики здесь нет. В разложении Слуцкого линий три, и
   каждая своя: спрашивают именно «эта или та». */
function consumerSnapTargets(out) {
  const c = STATE.cons;
  if (!c) return;
  const budget = (o) => (x) => {
    if (!(o.xInt > 0)) return NaN;
    const y = o.yInt - (o.yInt / o.xInt) * x;
    return (x >= 0 && x <= o.xInt) ? y : NaN;
  };
  const level = (U) => {
    const pts = traceLevelCurve(c.f, U, CONFIG.Qmax, CONFIG.Pmax * 6, 220);
    return (pts && pts.length) ? ((x) => interpY(pts, x)) : null;
  };
  const push = (name, f, color) => { if (f) out.push({ name, f, color }); };
  const s = c.slutsky, b = c.base;
  if (s) {
    push('бюджет: старый', budget(b), COL.ghost);
    push('бюджет: компенсир.', budget(s.comp), COL.MR);
    push('бюджет: новый', budget(s.fin), COL.reg);
    push('U исходная', level(b.U), COL.indiff);
    if (s.fin.U > 0) push('U новая', level(s.fin.U), COL.reg);
  } else {
    push('бюджетная линия', budget(b), COL.reg);
    push('кривая безразличия', level(b.U), COL.indiff);
  }
}

/* Неравенство. Кривая Лоренца хранится долями 0…1, а холст размечен в
   процентах: переводим на входе и на выходе, чтобы полоса легла ровно на
   нарисованную линию. */
function ineqSnapTargets(out) {
  const pts = STATE.ineqLorenz;
  if (!pts || !pts.length) return;
  out.push({ name: 'Лоренц', f: (x) => lorenzAt(pts, Math.max(0, Math.min(1, x / 100))) * 100, color: COL.D });
  const rd = STATE.ineqRedist;
  if (rd && rd.lorenz && rd.lorenz.length) {
    out.push({ name: 'Лоренц после', f: (x) => lorenzAt(rd.lorenz, Math.max(0, Math.min(1, x / 100))) * 100, color: COL.S });
  }
}

/* Кривые раздела «Математика» для прокатывания и пересечений. Берём то же,
   что сцена рисует: саму функцию, а в сюжетах со сравнением — все участвующие
   кривые. Вспомогательные линии (касательная, секущая) сюда не идут: по ним
   не катаются, и пересечения с ними только загромождали бы поле. */
function mathSnapTargets(out) {
  const f = mathF();
  const sub = STATE.mathSub;
  /* ⚠️ У СЮЖЕТА ПРО ПРОИЗВОДНУЮ ДВЕ ПАНЕЛИ, И ФУНКЦИИ У НИХ РАЗНЫЕ.
     Раньше ветки здесь не было вовсе: сюжет проваливался в общий конец, и на
     обе панели отдавалась одна f(x). На нижнем графике мышь притягивалась к
     x², которой там нет, а к самой производной — не притягивалась ни к чему.
     Производную берём ту же, что рисует сцена: численную dNum, второй
     математики здесь заводить нельзя. */
  if (sub === 'tangent') {
    if (f) {
      out.push({ name: 'f', f, color: COL.tanF, panel: 'deriv-top' });
      out.push({ name: "f'", f: (x) => dNum(f, x), color: COL.tanD, panel: 'deriv-bottom' });
    }
    return;
  }
  if (sub === 'minmax') {
    if (f) out.push({ name: mmLabel(0), f, color: mmColor(0) });
    for (let i = 1; i < mmSlots(); i++) {
      const expr = mmGet(i);
      if (!expr.trim()) continue;
      const { compiled } = compileMath(expr, 'x');
      if (!compiled) continue;
      out.push({ name: mmLabel(i), f: (x) => evalMathAt(compiled, 'x', x), color: mmColor(i) });
    }
    const isMin = (STATE.mathMinMax === 'min');
    const parts = out.slice();
    if (parts.length >= 2) {
      out.push({
        name: (STATE.mmName || 'Z').trim() || 'Z',
        f: (x) => {
          let best = NaN;
          parts.forEach(p => {
            const v = p.f(x);
            if (!isFinite(v)) return;
            if (!isFinite(best) || (isMin ? v < best : v > best)) best = v;
          });
          return best;
        },
      });
    }
    return;
  }
  if (sub === 'transform') {
    if (f) {
      out.push({ name: 'f', f });
      out.push({ name: 'после', f: mathTransformed(f, STATE.mathTrans, paramValue('a', 1)) });
    }
    return;
  }
  /* Н66. «Оптимум при ограничении» поля #inp-mathf не использует: там своя цель
     и своё ограничение. Раньше сюжет проваливался в общую ветку и катал точку
     по СПРЯТАННОЙ формуле из чужого поля, то есть по кривой, которой на экране
     нет. Катаем по самому ограничению: его точки сцена уже посчитала. */
  if (sub === 'constraint') {
    const pts = (STATE.mathRes && STATE.mathRes.conPts) || [];
    if (pts.length >= 2) out.push({ name: 'ограничение', f: (x) => interpY(pts, x) });
    return;
  }
  if (f) out.push({ name: 'f', f });
}

/* Кривые сцен торговли. Сама КПВ есть всегда; линия торговых возможностей —
   когда сцена её посчитала. Обе заданы формулой или точками, поэтому
   прокатывание и пересечения работают одинаково. */
function tradeSnapTargets(out) {
  const d = STATE.ppfTradeData;
  if (d && d.ok) {
    out.push({ name: 'КПВ', f: (x) => interpY(d.ppfPts, x) });
    if (d.line) out.push({ name: 'КТВ', f: (x) => d.line.intercept - d.line.slope * x });
    return;
  }
  const b = STATE.tradeBData;
  if (b && b.ok) {
    // Две страны — два поля со своими масштабами: каждая КПВ живёт в своём.
    if (b.co1) out.push({ name: 'КПВ 1', f: (x) => interpY(b.co1.ppts, x), panel: 'trade-1' });
    if (b.co2) out.push({ name: 'КПВ 2', f: (x) => interpY(b.co2.ppts, x), panel: 'trade-2' });
  }
}

// Ближайшая точка НА кривых к пикселю (px, py) или null, если все далеко.
/* Оси как цель прилипания (П31). В snapTargets их нет и быть не должно: там
   лежат кривые вида y = f(x), по ним ищутся экстремумы и изломы, а у прямой
   y = 0 производная нулевая всюду и «экстремумом» оказался бы каждый узел.
   Поэтому оси считаем отдельно, и ось Y — вертикаль, для которой f(x) вообще
   не определена. */
function axisSnapAt(px, py) {
  const pan = panelAt(px, py);
  const { mx, my } = mainScales(pan ? pan.id : null);
  const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
  const zx = (0 >= xLo && 0 <= xHi) ? mx(0) : null;
  const zy = (0 >= yLo && 0 <= yHi) ? my(0) : null;
  const out = [];
  if (zy !== null && Math.abs(py - zy) <= SNAP_PX) {
    out.push({ x: mx.invert(px), y: 0, name: 'ось X', kind: 'axis', d: Math.abs(py - zy) });
  }
  if (zx !== null && Math.abs(px - zx) <= SNAP_PX) {
    out.push({ x: 0, y: my.invert(py), name: 'ось Y', kind: 'axis', d: Math.abs(px - zx) });
  }
  // Обе рядом — метят в начало координат.
  if (out.length === 2) return { x: 0, y: 0, name: 'начало координат', kind: 'axis', d: Math.hypot(px - zx, py - zy) };
  return out[0] || null;
}

// Расстояние в пикселях от курсора до линии, на которой сидит точка. Нужно
// для сопротивления при отрыве: пока курсор ближе порога, точка не срывается.
function snapDistPx(name, px, py) {
  const pan = panelAt(px, py);
  const pid = pan ? pan.id : null;
  const { mx, my } = mainScales(pid);
  if (name === 'ось X') return Math.abs(py - my(0));
  if (name === 'ось Y') return Math.abs(px - mx(0));
  if (name === 'начало координат') return Math.hypot(px - mx(0), py - my(0));
  const t = snapTargets(pid).filter(t => t.name === name)[0];
  if (!t) return Infinity;
  const [xLo, xHi] = mx.domain();
  let best = Infinity;
  const N = 200;
  for (let i = 0; i <= N; i++) {
    const x = xLo + (xHi - xLo) * i / N, y = t.f(x);
    if (!isFinite(y)) continue;
    const d = Math.hypot(mx(x) - px, my(y) - py);
    if (d < best) best = d;
  }
  return best;
}

function snapPointAt(px, py) {
  const pan = panelAt(px, py);
  const pid = pan ? pan.id : null;
  const { mx, my } = mainScales(pid);
  const targets = snapTargets(pid);
  const ax = axisSnapAt(px, py);
  if (!targets.length) return ax;
  const [xLo, xHi] = mx.domain();
  const near = [];
  targets.forEach(t => {
    let bd = Infinity, bx = null, by = null;
    const N = 300;
    for (let i = 0; i <= N; i++) {
      const x = xLo + (xHi - xLo) * i / N;
      const y = t.f(x);
      if (!isFinite(y)) continue;
      const d = Math.hypot(mx(x) - px, my(y) - py);
      if (d < bd) { bd = d; bx = x; by = y; }
    }
    if (bx !== null && bd <= SNAP_PX) near.push({ t, d: bd, x: bx, y: by });
  });
  // Ось ближе любой кривой — садимся на неё.
  if (!near.length) return ax;
  near.sort((a, b) => a.d - b.d);
  if (ax && ax.d < near[0].d) return ax;

  // Две кривые в пределах допуска — метят в пересечение. Ищем его в окне
  // вокруг щелчка шириной в тот же допуск, переведённый в единицы данных.
  if (near.length >= 2) {
    const span = Math.abs(mx.invert(px + SNAP_PX * 2) - mx.invert(px - SNAP_PX * 2));
    const a = near[0].t, b = near[1].t;
    const r = findRootIn((x) => a.f(x) - b.f(x),
                         Math.max(xLo, near[0].x - span), Math.min(xHi, near[0].x + span));
    if (r != null && isFinite(a.f(r))) {
      return { x: r, y: a.f(r), name: a.name + ' и ' + b.name, cross: true };
    }
  }
  return { x: near[0].x, y: near[0].y, name: near[0].t.name, cross: false };
}

// Подсказка при наведении во взведённом режиме: кружок там, куда сядет точка.
// Двигаем отдельный элемент, а не перерисовываем весь холст: перерисовка на
// каждое движение мыши заметно тормозила бы.
function showSnapHint(hit) {
  const old = document.getElementById('snap-hint');
  if (!hit) { if (old) old.remove(); return; }
  if (old) old.remove();
  const { mx, my } = mainScales(hit.panel);
  const g = svg.append('g').attr('id', 'snap-hint').style('pointer-events', 'none');
  const px = mx(hit.x), py = my(hit.y);
  const hot = !!(hit.key || hit.cross);
  g.append('circle').attr('cx', px).attr('cy', py).attr('r', hot ? 8 : 7)
    .attr('fill', 'none').attr('stroke-width', hot ? 2.6 : 2)
    .attr('stroke', hot ? COL.reg : COL.ink);
  // Особая точка называет себя: «максимум MC», «пересечение D и S». Так видно,
  // куда именно сядет вершина, и не надо целиться пикселем.
  if (hit.key && hit.name) haloText(g, px + 12, py - 12, hit.name, 'start', 'auto');
}

let markCounter = 0;

// Взвести/снять режим «следующий щелчок по графику ставит точку».
function armMark(on) {
  const was = STATE.markArm;
  STATE.markArm = !!on;
  const wrap = document.getElementById('graph-wrap');
  if (wrap) wrap.style.cursor = on ? 'crosshair' : '';
  if (!on) showSnapHint(null);   // снятый режим не оставляет кружок-подсказку
  syncCanvasMode();
  if (was !== STATE.markArm && typeof redrawAll === 'function') redrawAll();
}

/* Отмена начатой точки: убираем заготовку и снимаем режим. Раньше Escape
   только снимал режим, и в списке оставалась строка-заготовка без координат —
   состояние, из которого не было выхода, кроме как ввести числа руками. */
function cancelMarkDraft() {
  armMark(false);
  const draft = pendingMark();
  if (draft) STATE.marks = STATE.marks.filter(m => m !== draft);
  renderMarkList();
}

/* П20. Сброс при переходе между моделями. Раньше сбрасывалось только
   «оформление»: название графика, подписи осей, свои точки, прокатывание.
   Всё остальное переживало смену сцены и всплывало в чужой модели: галочки
   заливок, свои цвета кривых и областей, размер подписей, режим первой
   четверти, шаги делений, кэши расчётов и — самое заметное — уже посчитанные
   площади. Посчитал площадь в «Спросе и предложении», ушёл в «Монополию», а
   она там же. Теперь сбрасывается ВСЁ, что не относится к самой сцене.

   Что НЕ сбрасываем сознательно: тему (общая на весь сайт) и состояние
   панелей (свёрнута или нет) — это настройки рабочего места, а не модели. */
const SCENE_DEFAULTS = {
  // Оформление графика.
  graphTitle: '', axisXName: '', axisYName: '', titleColor: null,
  // Точки, вершины и посчитанные площади.
  marks: [], areaVerts: [], areaCalcList: [], areaCalcMode: 'curve',
  roller: null, armedCurve: null, hoverCross: null, pointNames: {},
  markArm: false, vertArm: false,
  acFrom: null, acTo: null,   // свой отрезок «Под кривой» (Н52); null = вся первая четверть
  // Заливки и цвета.
  showCS: true, showPS: true, showGhost: false,
  showMonoCS: true, showMonoPS: true, showMonoVC: false,
  colorOverride: {}, areaColor: {}, titlePos: null,   // своё место названия (доли поля, Н22)
  // Плоскость и подписи.
  labelSize: LABEL_SIZE_DEFAULT, firstQuad: true, xStep: null, yStep: null,
  quadSaved: null,            // окно до включения первой четверти (обратный ход тумблера)
  showLegend: true, zoomLock: false, viewDirty: false,
  legendSpot: null,           // выбранное место легенды: держится, пока свободно
  // Буквы-параметры и кэши расчётов.
  params: {}, ppfSumData: null, ppfTradeData: null, mathRes: null,
  bundleOn: false, bundleX: null, bundleY: null,
  ineqMasterBase: null, ineqMasterDetached: false, ineqMasterS: 1,
};

function resetDecor() {
  clearUndo();          // шаги прежней модели к новой отношения не имеют
  /* ⚠️ СБРОСИТЬ СОСТОЯНИЕ МАЛО — НАДО ЕЩЁ СКАЗАТЬ ПАНЕЛИ ПЕРЕСОБРАТЬСЯ.

     Контрольный опыт владельца: зайти в «Построение графиков», вписать
     «x^2-a*x» (появляется ползунок a), вернуться ко всем блокам и открыть
     «Потоварные налоги» — ползунок «a» на месте, рядом с настоящей ставкой t.
     Прямым путём в ту же модель ползунков ноль.

     Замер показал, ГДЕ именно течёт: `STATE.params` к этому моменту уже пуст
     (буквы в состоянии нет вовсе), а чип по-прежнему в разметке. Правая панель
     пересобирается только при СМЕНЕ ПОДПИСИ своего содержимого, и подпись эта
     считается по состоянию — которое как раз стало прежним, пустым. Значит
     течёт не состояние, а разметка, пережившая его.

     Чистка состояния и приказ панели пересобраться обязаны стоять рядом:
     именно потому, что это одно событие — «началась новая модель». */
  /* ⚠️ ОБНУЛИТЬ ПОДПИСЬ НЕДОСТАТОЧНО, И ЭТО ВТОРОЙ СЛОЙ ТОЙ ЖЕ БЕДЫ.
     Панель пересобирается, когда подпись её содержимого ИЗМЕНИЛАСЬ. У сцены
     без своих ползунков подпись — пустая строка, и после «обнуления» она
     совпадала с новой: «не изменилось, пересобирать нечего», а чип прежней
     модели оставался на экране. Поэтому чистим САМИ КОНТЕЙНЕРЫ: новая модель
     начинается с пустой панели, а наполнит её updatePult. */
  const panel = document.getElementById('params-panel');
  if (panel) { panel._extraSig = PULT_REBUILD; panel._curveSig = PULT_REBUILD; }
  ['params-extra', 'params-curves'].forEach(id => {
    const box = document.getElementById(id);
    if (box) box.innerHTML = '';
  });
  Object.keys(SCENE_DEFAULTS).forEach(k => {
    const v = SCENE_DEFAULTS[k];
    STATE[k] = Array.isArray(v) ? [] : (v && typeof v === 'object' ? {} : v);
  });
  markCounter = 0; areaCalcCounter = 0;
  hideRollTip();
  resetLabelPositions();   // сглаживание подписей не тянет места из прошлой сцены
  const ren = document.getElementById('pt-rename'); if (ren) ren.remove();
  armMark(false);
  [['inp-gtitle', ''], ['inp-xname', ''], ['inp-yname', '']].forEach(([id, v]) => {
    const e = document.getElementById(id); if (e) e.value = v;
  });
  if (typeof syncLabelSizeSeg === 'function') syncLabelSizeSeg();
  renderMarkList();
  renderVertList();
}

/* П51. Память внутри модели, но не между моделями.
   Поработал в «КТВ. Две страны», ушёл в «Совершенную конкуренцию», поработал
   там, вернулся — в КТВ остались ТВОИ изменения именно этой модели.

   Сохраняем не весь STATE, а явный список полей: иначе вместе с полезным
   утечёт и то, что утекать не должно (режимы, подрежимы, ключ сцены). Список
   тот же, что и у сброса, плюс формулы и границы окна — то, что человек в
   этой модели действительно менял. */
const SNAPSHOT_KEYS = Object.keys(SCENE_DEFAULTS).concat([
  'curves', 'ppfFormula', 'ppfFormula2', 'ppftFormula', 'ppftPrice',
  'costsTC', 'costsMode', 'costsMCx', 'costsATCx', 'costsAVCx',
  'ineqIncomes', 'ineqFormula', 'mathFormula',
  'tax', 'pReg', 'taxKind', 'intervType',
]);
const _sceneSnaps = {};

/* ── ОТМЕНА ПОСЛЕДНЕГО ДЕЙСТВИЯ (фаза 4) ──────────────────────────────────

   Строится на УЖЕ СУЩЕСТВУЮЩЕМ списке полей SNAPSHOT_KEYS — на том самом, по
   которому работает память моделей и кнопка «Вернуть исходный вид». Второй
   механизм состояния рядом с первым разъехался бы с ним на первой же новой
   настройке: список полей один, и он один.

   ⚠️ СНИМОК ДЛЯ ОТМЕНЫ ОБЯЗАН БЫТЬ КОПИЕЙ, А НЕ ССЫЛКОЙ. saveSceneSnapshot
   кладёт `snap[k] = STATE[k]`, и ему этого хватает: он снимает состояние
   ровно в тот момент, когда сцена уходит с экрана и меняться уже не будет.
   Отмене нужно другое — состояние ДО действия, которое случится через
   мгновение и переписывает те же массивы на месте. Со ссылкой снимок менялся
   бы вместе с оригиналом, и «отмена» возвращала бы то же самое.

   Копируем два уровня: сам массив или объект и его прямых детей (кривую,
   точку, запись параметра, разбор прямой `linear`, который перетаскивание
   правит на месте). Глубже не идём намеренно — там скомпилированная формула и
   функции сцены, их надо оставить ссылкой. */
const UNDO_DEPTH = 20;
const _undoStack = [];

/* ⚠️ КОПИЯ ОБЯЗАНА ДОСТАТЬ ДО ТОГО, ЧТО ПРАВЯТ НА МЕСТЕ.
   Первая версия копировала ровно один уровень: массив кривых → сама кривая.
   Разбор прямой `curve.linear` при этом оставался ОБЩИМ объектом, а
   перетаскивание пишет именно в него (`curve.linear.b = …`). Снимок менялся
   вместе с оригиналом, и отмена возвращала формулу «100 - Q» при свободном
   члене 90,661 — запись и расчёт расходились ровно так же, как в дефекте,
   ради которого фаза и затевалась. Нашёл прибор: формулы сошлись, числа нет.
   Поэтому у ребёнка копируются и его собственные простые дети. */
function _undoCopyChild(v) {
  if (Array.isArray(v)) return v.slice();
  if (v && typeof v === 'object' && v.constructor === Object) {
    const o = {};
    Object.keys(v).forEach(k => {
      const x = v[k];
      if (Array.isArray(x)) o[k] = x.slice();
      else if (x && typeof x === 'object' && x.constructor === Object) o[k] = Object.assign({}, x);
      else o[k] = x;
    });
    return o;
  }
  return v;
}
function _undoCopy(v) {
  if (Array.isArray(v)) return v.map(_undoCopyChild);
  if (v && typeof v === 'object' && v.constructor === Object) {
    const o = {};
    Object.keys(v).forEach(k => { o[k] = _undoCopyChild(v[k]); });
    return o;
  }
  return v;
}

/* Положить состояние на полку ПЕРЕД изменяющим действием. Зовётся из мест,
   которые действительно меняют модель: сдвиг кривой, вынос и удаление точки,
   удаление кривой, переименование, правка формулы, значение и границы
   параметра. Тихо ничего не делает, пока сцена не открыта. */
function pushUndo() {
  if (!STATE.sceneKey) return;
  const snap = { scene: STATE.sceneKey, data: {} };
  SNAPSHOT_KEYS.forEach(k => { snap.data[k] = _undoCopy(STATE[k]); });
  _undoStack.push(snap);
  if (_undoStack.length > UNDO_DEPTH) _undoStack.shift();
}

/* Шаг назад. Снимок чужой модели не применяем: человек ушёл в другую сцену,
   и вернуть туда состояние отсюда значило бы менять то, чего он не видит. */
function undoLast() {
  while (_undoStack.length) {
    const snap = _undoStack.pop();
    if (snap.scene !== STATE.sceneKey) continue;
    SNAPSHOT_KEYS.forEach(k => { STATE[k] = snap.data[k]; });
    if (typeof renderCurveList === 'function') renderCurveList();
    if (typeof renderGraphRows === 'function' && document.getElementById('graph-rows')) renderGraphRows();
    if (typeof renderMarkList === 'function') renderMarkList();
    if (typeof renderVertList === 'function') renderVertList();
    redrawAll();
    return true;
  }
  return false;
}

// Уходя из модели, забываем её шаги: отмена — про «здесь и сейчас».
function clearUndo() { _undoStack.length = 0; }


// Забыть, что помнилось по моделям. Нужно, когда состояние надо начать с нуля
// (например, в контрольных прогонах, где каждый случай ставит свою обстановку).
/* Забыть снимок ОДНОЙ модели: на этом стоит «вернуть модель к исходному виду».
   Без этого pickScene тут же восстановил бы то, что мы только что отменили. */
function forgetSceneSnapshot(key) { delete _sceneSnaps[key]; }

function resetSceneMemory() { Object.keys(_sceneSnaps).forEach(k => { delete _sceneSnaps[k]; }); }

function saveSceneSnapshot(key) {
  if (!key) return;
  const snap = {};
  SNAPSHOT_KEYS.forEach(k => { snap[k] = STATE[k]; });
  snap._view = { Qmin: CONFIG.Qmin, Qmax: CONFIG.Qmax, Pmin: CONFIG.Pmin, Pmax: CONFIG.Pmax };
  snap._counters = { mark: markCounter, area: areaCalcCounter };
  _sceneSnaps[key] = snap;
}

function restoreSceneSnapshot(key) {
  const snap = key && _sceneSnaps[key];
  if (!snap) return false;
  SNAPSHOT_KEYS.forEach(k => { STATE[k] = snap[k]; });
  if (snap._view) {
    CONFIG.Qmin = snap._view.Qmin; CONFIG.Qmax = snap._view.Qmax;
    CONFIG.Pmin = snap._view.Pmin; CONFIG.Pmax = snap._view.Pmax;
  }
  if (snap._counters) { markCounter = snap._counters.mark; areaCalcCounter = snap._counters.area; }
  if (typeof syncLabelSizeSeg === 'function') syncLabelSizeSeg();
  // Способ ввода издержек — часть обстановки модели, поэтому его переключатель
  // и поля надо вернуть в согласие с восстановленным состоянием (Б24).
  if (typeof syncCostsInputMode === 'function') syncCostsInputMode();
  renderMarkList();
  renderVertList();
  renderCurveList();
  return true;
}

function addMarkAt(x, y, snapTo, panel) {
  const pid = panel || (activePanel() ? activePanel().id : null);
  // Щелчок по графику в режиме «Указать на графике» достраивает уже заведённую
  // заготовку, а не плодит вторую точку (П28).
  const draft = pendingMark();
  if (draft) {
    draft.x = x; draft.y = y; draft.snapTo = snapTo || null;
    draft.panel = pid;
    draft.pending = false;
    renderMarkList();
    redrawAll();
    return;
  }
  STATE.marks.push(newMark(x, y, snapTo, 'graph', pid));
  renderMarkList();
  redrawAll();
}

/* Заготовка точки: строка списка уже есть, а на плоскости точки ещё нет.
   Так работает пайплайн П28 — тумблер и поля координат живут в той же строке,
   которая потом станет обычной строкой точки, и фокус при наборе не теряется. */
/* Цвет новой точки — следующий свободный из общей палитры (А63).

   Было: у всех точек цвет null, то есть COL.ink, и на графике с тремя точками
   их было не различить ни на холсте, ни в списке. Палитра та же, что предлагает
   пикер (--pal-1…--pal-6), поэтому светлая и тёмная тема дают свои значения;
   когда цвета кончаются, начинаем заново. */
/* п. 32. НОВАЯ ТОЧКА НЕ ПОВТОРЯЕТ ЦВЕТ ТОГО, ЧТО УЖЕ НАРИСОВАНО.

   Совпадения по коду цвета тут не было и быть не могло: у палитры точек свои
   значения (--pal-*), у кривых свои (--curve-*). А глазом красная точка на
   красной кривой предложения читалась как её часть. Поэтому сравниваем не
   строки, а РАССТОЯНИЕ между цветами, и берём тот образец палитры, который
   дальше всего от уже нарисованного.

   Цвета берём с самого холста: спрашивать сцену, чем она рисует, значит
   держать второй список ролей и разойтись с ним на первой же новой сцене. */
function colorDist(a, b) {
  const px = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const [r1, g1, b1] = px(a), [r2, g2, b2] = px(b);
  // «Redmean» — дешёвое приближение к воспринимаемой разнице, точнее простой
  // евклидовой метрики по RGB: у тёмных и светлых пар веса каналов разные.
  const rm = (r1 + r2) / 2, dr = r1 - r2, dg = g1 - g2, db = b1 - b2;
  return Math.sqrt((2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db);
}

function drawnStrokeColors() {
  const out = [];
  const node = (typeof svg !== 'undefined' && svg && svg.node) ? svg.node() : null;
  if (!node) return out;
  node.querySelectorAll('path[stroke], line[stroke]').forEach(el => {
    const c = el.getAttribute('stroke');
    if (!c || c === 'none' || c === 'transparent') return;
    const h = normHex(c);
    if (h && out.indexOf(h) < 0) out.push(h);
  });
  return out;
}

// Ниже этого расстояния два цвета на графике читаются как один.
const COLOR_NEAR = 90;

function nextMarkColor() {
  const pal = paletteSix().filter(Boolean);
  if (!pal.length) return null;
  const used = (STATE.marks || []).map(m => normHex(m.color || '')).filter(Boolean);
  const busy = used.concat(drawnStrokeColors());
  const far = (c) => busy.reduce((m, b) => Math.min(m, colorDist(normHex(c), b)), Infinity);
  // Свободный по коду и достаточно далёкий от нарисованного — лучший выбор.
  const free = pal.filter(c => used.indexOf(normHex(c)) < 0);
  const good = free.filter(c => far(c) >= COLOR_NEAR);
  if (good.length) return good[0];
  // Ни один не проходит порог (на графике уже много цветов) — берём самый
  // дальний из ещё не занятых, а если заняты все, идём по кругу, как раньше.
  if (free.length) return free.slice().sort((a, b) => far(b) - far(a))[0];
  return pal[(STATE.marks || []).length % pal.length];
}

function newMark(x, y, snapTo, mode, panel) {
  markCounter++;
  return {
    id: markCounter, x, y, text: 'Точка ' + markCounter,
    // Хозяйская панель: в ней точку поставили, по её шкалам и рисуем.
    panel: panel || (activePanel() ? activePanel().id : null),
    showCoords: true, showDash: true, color: nextMarkColor(),
    mode: mode || 'coords',      // как её создавали: тумблер после этого заперт
    pending: false,
    // Имя кривой, на которой сидит точка. Пока оно задано, точка при
    // перетаскивании скользит ПО кривой, а не отрывается от неё.
    snapTo: snapTo || null,
  };
}
function pendingMark() { return (STATE.marks || []).filter(m => m.pending)[0] || null; }

// «Добавить точку»: заводим заготовку и ждём координаты или щелчок по графику.
function startMarkDraft() {
  if (pendingMark()) return;
  const m = newMark(NaN, NaN, null, 'coords');
  m.pending = true;
  STATE.marks.push(m);
  renderMarkList();
}

// Функция кривой, к которой привязана точка (или null, если привязки нет).
function markSnapFn(mk) {
  if (!mk.snapTo) return null;
  const t = snapTargets().filter(t => t.name === mk.snapTo)[0];
  return t ? t.f : null;
}

/* Список своих точек (П28, П29).
   Порядок на экране: сначала уже созданные точки, потом заготовка, если она
   есть, и в самом низу кнопка «Добавить точку». Пока заготовка не превратилась
   в точку, кнопки нет: два незаконченных ввода разом только путают. */
function renderMarkList() {
  const box = document.getElementById('mark-list');
  if (!box) return;
  box.innerHTML = '';
  (STATE.marks || []).forEach(mk => box.appendChild(buildMarkRow(mk)));

  if (!pendingMark()) ensureAddMarkButton();
}

/* Н38. Кнопка «Добавить точку» всегда стоит ПОД списком: новая точка появляется
   выше неё, а кнопка съезжает вниз. Отдельная функция, потому что кнопку надо
   вернуть и в тот момент, когда заготовка превратилась в точку прямо во время
   набора координат, без пересборки всего списка (иначе теряется фокус). */
function ensureAddMarkButton() {
  const box = document.getElementById('mark-list');
  if (!box || box.querySelector('.btn-mark-add')) return;
  const add = document.createElement('button');
  add.type = 'button'; add.className = 'btn-sm btn-mark-add';
  add.textContent = 'Добавить точку';
  add.addEventListener('click', () => startMarkDraft());
  box.appendChild(add);
}

function buildMarkRow(mk) {
  const row = document.createElement('div');
  row.className = 'mark-row';
  if (mk.pending) row.classList.add('mark-draft');

  /* Тумблер «Ввести координаты | Указать на графике» (П28). Он живёт только
     у заготовки: как только точка появилась на плоскости, способ ввода уже
     выбран и менять его нечем — тумблер из строки уходит совсем. Держать его
     навсегда серым в каждой строке было бы мёртвым элементом. */
  let seg = null;
  if (mk.pending) {
    seg = makeToggle('Ввести координаты', 'Указать на графике', mk.mode === 'graph', (v) => {
      if (!mk.pending) return;
      mk.mode = (v === 'right') ? 'graph' : 'coords';
      armMark(mk.mode === 'graph');
      renderMarkList();
    });
    row.appendChild(seg);
  }

  if (mk.pending && mk.mode === 'graph') {
    const hint = document.createElement('div');
    hint.className = 'mark-hint';
    hint.textContent = 'Нажмите на график';
    row.appendChild(hint);
    return row;
  }

  /* Координаты. У заготовки они и есть способ создания: точка появляется, как
     только оба поля заполнены, и переезжает на каждый введённый символ —
     поэтому слушаем input, а не change, и НЕ пересобираем список (иначе
     потерялся бы фокус посреди набора). */
  const xy = document.createElement('div');
  xy.className = 'mark-xy';
  const nums = {};
  /* Н47, Н36. Координата это набранное «x = 50», а не подпись и прямоугольное
     поле рядом. Правится тем же компонентом, что и всюду: пунктир снизу, правка
     на месте, применение на каждый символ. */
  const mkNum = (key) => {
    // п. 32. Координата подписана буквой ТОЙ ЖЕ оси, что нарисована на графике.
    const letter = axisLetter(key);
    const n = makeEditableValue({
      get: () => (isFinite(mk[key]) ? Math.round(mk[key] * 1000) / 1000 : ''),
      tex: (v, text) => letter + ' = ' + (text === '' ? '{?}' : text),
      title: 'Координата ' + letter,
      set: (v) => {
        mk[key] = isFinite(v) ? v : NaN;
        // Точка на кривой держится за неё: меняем x, высоту берём с кривой.
        const f = markSnapFn(mk);
        if (f && key === 'x' && isFinite(v)) { const y = f(v); if (isFinite(y)) mk.y = y; }
        const ready = isFinite(mk.x) && isFinite(mk.y);
        if (mk.pending && ready) {
          mk.pending = false;
          if (seg) seg.remove();          // способ ввода выбран, тумблер больше не нужен
          row.classList.remove('mark-draft');
          ensureAddMarkButton();
        } else if (!ready && !mk.pending) {
          mk.pending = true;                     // стёрли координату — точка ушла
        }
        redrawAll();
      },
    });
    nums[key] = n;
    xy.append(n);
  };
  mkNum('x');
  mkNum('y');
  if (mk.pending) {
    /* Н37. Галочка подтверждения. Точка встаёт и сама, как только заполнены обе
       координаты, но без видимого «готово» заготовка выглядит незавершённой. */
    const ok = document.createElement('button');
    ok.type = 'button'; ok.className = 'btn-icon mark-ok';
    ok.textContent = '✓';
    ok.setAttribute('data-tip', 'Поставить точку');
    ok.addEventListener('click', () => {
      if (!isFinite(mk.x) || !isFinite(mk.y)) return;
      mk.pending = false;
      ensureAddMarkButton();
      renderMarkList(); redrawAll();
    });
    xy.appendChild(ok);
    row.appendChild(xy);
    return row;                                  // остальное — когда точка встанет
  }

  /* Н46. Сразу после цвета идёт ИМЯ точки, и правится оно щелчком по самому
     имени, а не в отдельном текстовом поле под строкой. Надписи «Своя точка»
     больше нет: она ничего не сообщала. */
  const top = document.createElement('div');
  top.className = 'mark-top';
  const pick = makeColorPicker(mk.color || COL.ink, (hex) => { mk.color = hex; redrawAll(); }, 'Цвет точки');
  const nameEl = makeEditableValue({
    kind: 'text',
    get: () => mk.text || '',
    set: (v) => { mk.text = String(v).trim(); redrawAll(); },
    // Имя это ТЕКСТ, а не формула: в математическом наборе KaTeX съедает
    // пробелы, и «Точка A» превратилась бы в «ТочкаA».
    tex: (v, text) => (text ? '\\text{' + String(text).replace(/([{}\\$&#^_~%])/g, '\\$1') + '}' : '\\text{без имени}'),
    title: 'Имя точки',
  });
  nameEl.classList.add('mark-name');
  const del = document.createElement('button');
  del.className = 'btn-icon'; del.type = 'button'; del.textContent = '✕'; del.setAttribute('data-tip', 'Убрать точку');
  del.addEventListener('click', () => {
    STATE.marks = STATE.marks.filter(m => m.id !== mk.id);
    renderMarkList(); redrawAll();
  });
  top.append(pick, nameEl, del);

  const toggle = (label, key, def) => {
    const w = document.createElement('label');
    w.className = 'chk';
    const c = document.createElement('input');
    c.type = 'checkbox';
    c.checked = (mk[key] === undefined) ? def : !!mk[key];
    c.addEventListener('change', () => { mk[key] = c.checked; redrawAll(); });
    w.append(c, document.createTextNode(label));
    return w;
  };

  /* Н48. Координаты в столбик, галочки правее: две строки вместо четырёх, и
     строка точки перестала быть самой высокой в панели. */
  const body = document.createElement('div');
  body.className = 'mark-body';
  const chks = document.createElement('div');
  chks.className = 'mark-chks';
  chks.append(toggle('Пунктир к осям', 'showDash', true),
              toggle('Координаты', 'showCoords', true));
  xy.classList.add('mark-xy-col');
  body.append(xy, chks);
  row.append(top, body);

  /* Н45. Точка, посаженная на кривую, скользит по ней, и это видно по самому
     поведению — отдельная строка «Удерживать точку на КПВ» ничего не добавляла
     и только занимала место в списке. Отпустить точку по-прежнему можно:
     достаточно оттащить её от линии дальше порога отрыва. */
  return row;
}
