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
  redrawScene();
  drawOverlays();
  applyLabelSize();      // общий размер подписей — одним проходом по холсту (П50)
  // Последним: карточка блока прячет переключатели соседних моделей. Идёт после
  // обычной логики видимости, иначе та вернула бы их на место.
  applyCardScope();
}

function redrawScene() {
  refreshColors();      // перечитать цвета из CSS-переменных (учитывает смену темы)
  clearResultPanels();  // очистить табло — активный режим заполнит свои блоки
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
    } else {
      // Обычная монополия (вмешательства нет / не связывает): потери DWL, D/MC, MR, точки.
      drawMonopolyAreas();
      drawCurves();              // спрос D и (если задана явно) кривая MC
      drawMonopoly();            // MR + (если MC выведена из TC) сама MC
      drawMonopolyPoints();      // точки M и MR=MC, проекции, конкурентный ориентир
      if (STATE.intervType === 'ceiling' && STATE.pReg > 0) drawMonoCeilingLine();  // линия видна, но не связывает
      else if (STATE.intervType === 'floor' && STATE.pReg > 0) drawMonoFloorLine(); // линия видна, но не связывает
    }
  } else if (STATE.scenario === 'externality') {
    // Внешний эффект (Задача 4): DWL + D/MPC + MSC + точки Qрын/Qопт (+ Пигу).
    drawExtScenario();
  } else if (STATE.scenario === 'shift') {
    // Разложение сдвигов (Задача 3): исходные + сдвинутые кривые + E_d/E_s/E₁.
    drawShiftScenario();
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
    else drawAreas();
    drawGhost();                 // бледный слой «было» под кривыми/точками
    drawCurves();
    drawShiftedSupply();         // пунктирная S + t (если налог активен)
    // Точки/линии: налог E₀/E₁, регулирование цены или обычное равновесие E*.
    if (STATE.taxActive) drawTaxPoints();
    else if (STATE.pcMode) drawPriceControl();
    else drawEquilibrium();
  }
  updateInfoPanel();
  updateAreasPanel();
  if (STATE.market === 'monopoly') {
    if (STATE.monoMode === 'discr1') updateDiscr1Panel(); else updateMonoPanel();
    if (STATE.monoMode === 'natural') updateNaturalPanel();   // три ориентира регулирования (Фаза 3в)
    // Вмешательство государства в монополии (Фаза 2): налог/субсидия/потолок/пол.
    updateMonoInterventionPanel();
  } else if (STATE.scenario === 'externality') {
    updateExtPanel();
    const imono = document.getElementById('info-mono'); if (imono) imono.innerHTML = '';
  } else if (STATE.scenario === 'shift') {
    updateShiftPanel();
    const imono = document.getElementById('info-mono'); if (imono) imono.innerHTML = '';
  } else if (STATE.scenario === 'elasticity') {
    updateElasticityPanel();
    const imono = document.getElementById('info-mono'); if (imono) imono.innerHTML = '';
  } else if (STATE.scenario === 'openecon') {
    updateOpenPanel();
    const imono = document.getElementById('info-mono'); if (imono) imono.innerHTML = '';
  } else {
    if (STATE.pcMode) updatePcPanel(); else updateTaxPanel();
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
    upgradeFormulaField(inp);
  }
}

/* Список функций как в графопостроителе: внизу всегда одна пустая строка.
   Начали печатать — она превращается в обычную строку списка (цвет, имя,
   удаление, правка формулы), а под ней появляется новая пустая. */
function graphRowsBox() { return document.getElementById('graph-rows'); }

function renderGraphRows() {
  const box = graphRowsBox();
  if (!box) return;
  box.innerHTML = '';
  STATE.curves.forEach(c => box.appendChild(buildGraphRow(c)));
  box.appendChild(buildGraphRow(null));
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
  inp.placeholder = curve ? '' : 'Например: x^2 - 4';
  inp.setAttribute('aria-label', 'Формула функции');
  slot.appendChild(inp);
  row.appendChild(slot);

  const del = document.createElement('button');
  del.type = 'button'; del.className = 'btn-icon'; del.textContent = '✕';
  del.title = 'Убрать функцию';
  del.style.visibility = curve ? '' : 'hidden';
  del.addEventListener('click', () => {
    if (!row._curve) return;
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
  upgradeFormulaField(inp);
  return row;
}

/* Правка строки. Пустая строка при первом же осмысленном вводе заводит кривую
   и «рожает» следующую пустую; заполненная просто обновляет свою формулу. */
function graphRowInput(row, inp, del, name) {
  const txt = (inp.value || '').trim();
  if (!row._curve) {
    if (!txt) return;
    const { compiled, error } = compileFormula(txt);
    if (error) { graphError('Пока не понимаю: ' + error); return; }
    graphError('');
    curveCounter++;
    const c = { id: curveCounter, expr: txt, compiled, color: nextColor(),
                name: txt, role: null, visible: true,
                linear: detectLinear(compiled), srcForm: 'PQ' };
    STATE.curves.push(c);
    row._curve = c;
    row.dataset.cid = c.id;
    del.style.visibility = '';
    const box = graphRowsBox();
    if (box) box.appendChild(buildGraphRow(null));
    redrawAll();
    return;
  }
  if (!txt) return;                       // пустое поле не роняет кривую
  const err = updateCurveExpr(row._curve, txt);
  graphError(err ? ('Пока не понимаю: ' + err) : '');
  if (!err) redrawAll();
}

/* ---------------------------------------------------------------------
   ОФОРМЛЕНИЕ (Фаза 1) — слой поверх любой сцены: заголовок и свои точки.
   --------------------------------------------------------------------- */

// Канонические шкалы главного графика. Считаем свои копии, а не берём глобальные
// sx/sy: сцены с двумя мини-графиками (дискриминация 3°, производство, два завода)
// оставляют в sx/sy шкалу ПОСЛЕДНЕЙ панели, и точки уехали бы вместе с ней.
function mainScales() {
  const m = CONFIG.margin;
  // В «Математике» окно другое — полный план вместо первой четверти.
  if (STATE.mode === 'math') return mathScales();
  // Берём и нижние границы: после панорамирования начало окна уже не в нуле,
  // и точки, посчитанные от нуля, разъезжались бы с кривыми.
  return {
    mx: d3.scaleLinear().domain([CONFIG.Qmin, CONFIG.Qmax]).range([m.left, W - m.right]),
    my: d3.scaleLinear().domain([CONFIG.Pmin, CONFIG.Pmax]).range([H - m.bottom, m.top]),
  };
}

function drawOverlays() {
  if (!svg || !svg.node()) return;
  invalidateKeyTargets();    // особые точки считаются заново под новую картинку
  if (typeof resetLabelBoxes === 'function') resetLabelBoxes();   // подписи расставляются заново
  applyAreaColors();         // свои цвета заливок — одним проходом по data-legend
  drawAreaCalc();            // посчитанная площадь (Фаза 10)
  drawAreaVerts();           // набранные вершины будущей площади
  drawCrossPoints();         // пересечения кривых тусклыми точками
  drawRoller();              // точка, катящаяся по кривой
  drawGraphTitle();
  drawLegend();
  drawMarks();
  syncAxisPlaceholders();
  syncSceneColorPickers();   // образцы в панели идут за темой и за своими цветами
  syncAreaColorList();       // список областей с пикерами
  syncAreaCalcUI();          // выпадашка кривых и список точек для расчёта площади
  hintsToDots();             // подсказки, добавленные сценой, тоже уходят под вопросик
  syncFirstCard();                                     // ярче та карточка, что сверху
  syncAnalyticsPanel();                                // разбор уезжает в свой блок
  renderMathIn(document.getElementById('sb-body'));    // формулы в аналитике
  renderMathIn(document.getElementById('ex-body'));    // и в объяснении модели
  renderMathIn(document.getElementById('tools-panel'));// и в подсказках панели
}

/* ── Общий рендер математики в тексте интерфейса (Фаза 4) ─────────────
   Всё, что в тексте заключено в $…$, печатается формулой. Один проход по
   контейнеру после того, как он заполнен, поэтому новому блоку аналитики
   ничего дополнительно делать не нужно: достаточно поставить доллары.

   Правится только текст, разметка не трогается: обходим текстовые узлы и
   заменяем найденный кусок на span с формулой. Узлы, уже прошедшие обработку,
   помечаются, чтобы статичные подсказки не разбирались заново на каждом кадре. */
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
      try { katex.render(piece, span, { throwOnError: false, displayMode: false }); }
      catch (e) { span.textContent = piece; }
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

function applyAreaColors() {
  const map = STATE.areaColor || {};
  svg.selectAll('[data-legend]').each(function () {
    const k = areaKey(this.getAttribute('data-legend'));
    const c = map[k];
    if (c) this.setAttribute('fill', c);
  });
}

// Какие области сейчас на графике: [{key, color, opacity}] без повторов.
function currentAreas() {
  const seen = [], by = {};
  svg.selectAll('[data-legend]').each(function () {
    const k = areaKey(this.getAttribute('data-legend'));
    if (!k || by[k]) return;
    by[k] = 1;
    seen.push({ key: k, color: this.getAttribute('fill') || COL.ink, opacity: +this.getAttribute('opacity') || 0.2 });
  });
  return seen;
}

/* Короткие обозначения для легенды: на графике место дорого, а CS и DWL
   школьник читает быстрее любой фразы. Полное название остаётся в подсказке. */
const AREA_SHORT = {
  'Излишек покупателя (CS)': 'CS',
  'Излишек продавца (PS)': 'PS',
  'Излишек производителя (TR - VC)': 'PS',
  'Излишек работников': 'CS',
  'Излишек фирм': 'PS',
  'Излишек фирмы: весь излишек рынка': 'PS',
  'Переменные издержки (VC)': 'VC',
  'Потери общества (DWL)': 'DWL',
  'Потери от внешнего эффекта (DWL)': 'DWL',
  'Сбор бюджета': 'Tx',
  'Поступления бюджета': 'Tx',
  'Доход бюджета': 'Tx',
  'Расход бюджета': 'GS',
  'Рента квоты': 'R',
  'Достижимые наборы': 'Дост.',
  'Диапазон возможных зарплат': 'W',
  'Площадь': 'S',
};
function areaShort(name) {
  if (AREA_SHORT[name]) return AREA_SHORT[name];
  const m = /\(([^)]{1,5})\)\s*$/.exec(name);      // «… (CS)» → CS
  if (m) return m[1];
  return name.length > 10 ? name.slice(0, 9) + '…' : name;
}

/* Легенда: столбик у правого нижнего угла поля графика. Раньше она лежала
   поперёк верхнего поля и спорила с заголовком; внизу справа под кривыми
   почти всегда пусто, и читать её удобнее. */
function drawLegend() {
  if (!STATE.showLegend) return;
  const seen = currentAreas();
  if (!seen.length) return;
  const m = CONFIG.margin;
  /* П47: легенда вдвое крупнее прежнего — кегль 24 вместо 12, квадратик 24
     вместо 12, шаг строк 36 вместо 18. Ширину подложки считаем от РЕАЛЬНОГО
     кегля, а не по прежней прикидке «длина строки × 6.8»: с удвоенным
     размером текст просто вылезал бы за рамку.
     Подложка не залезает на конец оси: это то же правило про отступ, что и
     в П33, только здесь его соблюдает сама легенда. */
  const SW = 24, GAP = 12, LH = 36, FS = 24;
  const labels = seen.map(e => areaShort(e.key));
  const wide = Math.max.apply(null, labels.map(s => s.length)) * FS * 0.62;
  const boxW = SW + GAP + wide + 20;
  const boxH = seen.length * LH + 16;
  const x = (W - m.right) - boxW - 8;
  const y = (H - m.bottom) - boxH - 26;
  const g = svg.append('g').attr('class', 'legend').style('pointer-events', 'none');
  g.append('rect').attr('x', x).attr('y', y).attr('width', boxW).attr('height', boxH)
    .attr('rx', 6).attr('fill', COL.halo).attr('opacity', 0.82)
    .attr('stroke', COL.grid).attr('stroke-width', 1);
  seen.forEach((e, i) => {
    const cy = y + 8 + i * LH;
    g.append('rect')
      .attr('x', x + 10).attr('y', cy + 4).attr('width', SW).attr('height', SW)
      .attr('rx', 4).attr('fill', e.color).attr('opacity', Math.max(0.35, e.opacity * 2))
      .attr('stroke', e.color).attr('stroke-opacity', 0.55).attr('stroke-width', 1);
    const t = g.append('text')
      .attr('x', x + 10 + SW + GAP).attr('y', cy + SW * 0.82)
      .attr('font-size', FS).attr('font-weight', 600).attr('fill', COL.ink)
      .text(labels[i]);
    t.append('title').text(e.key);
  });
}

/* Список областей с пикерами цвета — в панели ввода. Пересобирается после
   каждой отрисовки, потому что набор областей зависит от сцены. */
function syncAreaColorList() {
  const box = document.getElementById('area-colors');
  if (!box) return;
  const seen = currentAreas();
  const sig = seen.map(e => e.key).join('|');
  if (box._sig === sig) {                       // набор тот же — только цвета
    seen.forEach(e => {
      const p = box.querySelector('.cpick[data-area="' + CSS.escape(e.key) + '"]');
      if (p && p._setValue) p._setValue(e.color);
    });
    return;
  }
  box._sig = sig;
  box.innerHTML = '';
  const sec = document.getElementById('sec-areacolors');
  if (sec) sec.style.display = seen.length ? '' : 'none';
  seen.forEach(e => {
    const row = document.createElement('div');
    row.className = 'ac-row';
    const pick = makeColorPicker(e.color, (hex) => {
      STATE.areaColor[e.key] = hex;
      redrawAll();
    }, 'Цвет области: ' + e.key);
    pick.setAttribute('data-area', e.key);
    const lab = document.createElement('span');
    lab.className = 'ac-name'; lab.textContent = e.key;
    row.append(pick, lab);
    box.appendChild(row);
  });
}

/* ── Точки пересечения (Фаза 6, дополнено) ────────────────────────────
   Считаются сами: кривые друг с другом И каждая кривая с осями координат.
   Показываются тускло; наведение или щелчок делает точку яркой и подписывает
   координаты, курсор ушёл — снова тускнеет. */
/* Окно, в котором сцена РЕАЛЬНО рисует. Берём у главных шкал, а не у CONFIG:
   в «Математике» и в сценах с двумя панелями окно своё, и всё, что считалось
   от CONFIG, искалось не там, где нарисованы кривые (отсюда терялись корни
   в отрицательной части плана). Нижние границы режем по правилу первой
   четверти — тем же quadLo, что и остальной движок. */
function viewWindow() {
  const { mx, my } = mainScales();
  const [dx0, dx1] = mx.domain(), [dy0, dy1] = my.domain();
  const [px0, px1] = mx.range();
  return {
    x0: quadLo(dx0), x1: dx1,
    y0: quadLo(dy0), y1: dy1,
    px: Math.abs(px1 - px0),
  };
}

// Как назвать оси в подписи ключевой точки: в «Математике» это x и y.
function axisWords() {
  if (STATE.mode === 'math') return ['ось x', 'ось y'];
  if (STATE.mode === 'ppf') return ['ось X', 'ось Y'];
  return ['ось Q', 'ось P'];
}

function crossPoints() {
  const t = snapTargets();
  if (!t.length) return [];
  const w = viewWindow();
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
let _keyPtsCache = null;
function invalidateKeyTargets() { _keyPtsCache = null; }

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

function keyTargets() {
  if (_keyPtsCache) return _keyPtsCache;
  const out = [];
  const w = viewWindow();
  const dx = (w.x1 - w.x0) * 1e-3, dy = (w.y1 - w.y0) * 1e-3;
  /* Вид точки нужен отрисовке (П36–П38): излом рисуется по-особому, у
     остальных вид одинаковый. Перегибы сюда не попадают и не попадут:
     договорились их ключевыми точками не считать. */
  const push = (x, y, name, kind) => {
    if (!isFinite(x) || !isFinite(y)) return;
    if (x < w.x0 - 1e-9 || x > w.x1 + 1e-9 || y < w.y0 - 1e-9 || y > w.y1 + 1e-9) return;
    if (out.some(o => Math.abs(o.x - x) < dx && Math.abs(o.y - y) < dy)) return;
    out.push({ x, y, name, kind: kind || 'cross' });
  };
  (STATE.crosses && STATE.crosses.length ? STATE.crosses : crossPoints()).forEach(p => {
    push(p.x, p.y, /^ось /.test(p.b)
      ? ('пересечение с ' + p.b.replace('ось ', 'осью '))
      : ('пересечение ' + p.a + ' и ' + p.b), 'cross');
  });
  if (!(w.x1 > w.x0)) { _keyPtsCache = out; return out; }
  const lo = w.x0 + (w.x1 - w.x0) * 1e-4, hi = w.x1;
  const h = (w.x1 - w.x0) * 1e-4;
  const h2 = Math.max(h * 20, (w.x1 - w.x0) * 1e-3);
  snapTargets().forEach(t => {
    let ext = [];
    try { ext = rootsOf((x) => dNum(t.f, x, h), lo, hi, 400); } catch (e) { ext = []; }
    ext.forEach(x => {
      const y = t.f(x);
      if (!isFinite(y)) return;
      const s = d2Num(t.f, x, h2);
      const kind = (s > 0) ? 'минимум ' : (s < 0 ? 'максимум ' : 'плато ');
      push(x, y, kind + t.name, 'extremum');
    });
    // Излом, совпавший с уже найденным пересечением, не добавляем: у Z = min(f, g)
    // ветвь переключается ровно там, где кривые пересекаются, а пересечение и
    // посчитано точнее (бисекцией), и названо понятнее.
    const near = (w.x1 - w.x0) * 0.02;
    kinksOf(t.f, lo, hi).forEach(x => {
      if (out.some(o => Math.abs(o.x - x) < near)) return;
      push(x, t.f(x), 'излом ' + t.name, 'kink');
    });
  });
  _keyPtsCache = out;
  return out;
}

/* Куда сядет вершина площади. Рядом с особой точкой прыгает точно в неё,
   иначе садится просто на ближайшую кривую. Радиус у особой точки чуть
   больше, чтобы попадать в неё было легче, чем промахнуться мимо. */
// В ключевую точку попасть должно быть заметно легче, чем просто в кривую (П42).
const KEY_SNAP_PX = 22;
function snapVertexAt(px, py) {
  const { mx, my } = mainScales();
  let best = null;
  keyTargets().forEach(p => {
    const d = Math.hypot(mx(p.x) - px, my(p.y) - py);
    if (d <= KEY_SNAP_PX && (!best || d < best.d)) best = { x: p.x, y: p.y, name: p.name, key: true, d };
  });
  if (best) return best;
  const hit = snapPointAt(px, py);
  return hit ? { x: hit.x, y: hit.y, name: hit.name, key: false, cross: hit.cross } : null;
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
function drawCrossPoints() {
  STATE.crosses = crossPoints();
  const pts = keyTargets();
  if (!pts.length) return;
  const { mx, my } = mainScales();
  const g = svg.append('g').attr('class', 'crosses');
  // Пока набирают вершины или ставят свою точку, кружки ключевых точек не ловят
  // щелчок: иначе щелчок рядом с пересечением уходил в кружок и вершина не
  // ставилась вовсе. Прилипание к этим же точкам работает и без их кликабельности.
  if (STATE.vertArm || STATE.markArm) g.style('pointer-events', 'none');

  const [x0] = mx.domain(), [y0] = my.domain();
  const zx = mx(Math.max(0, x0)), zy = my(Math.max(0, y0));   // где стоят оси

  pts.forEach((p, i) => {
    const px = mx(p.x), py = my(p.y);

    if (p.kind === 'kink') {
      // Пунктир к обеим осям и числа прямо на осях — без щелчка.
      g.append('line').attr('x1', zx).attr('y1', py).attr('x2', px).attr('y2', py)
        .attr('stroke', COL.inkSoft).attr('stroke-width', 1)
        .attr('stroke-dasharray', '3 3').attr('opacity', .6);
      g.append('line').attr('x1', px).attr('y1', zy).attr('x2', px).attr('y2', py)
        .attr('stroke', COL.inkSoft).attr('stroke-width', 1)
        .attr('stroke-dasharray', '3 3').attr('opacity', .6);
      /* Числа на осях. Если ровно там уже стоит деление, второй раз его не
         печатаем: вышло бы одно число поверх другого. Делаем как extraTickX —
         засечка и подпись, только по шкалам сцены, а не по глобальным. */
      const axg = g.append('g').attr('class', 'kink-axis');
      const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
      const spanX = Math.abs(xHi - xLo), spanY = Math.abs(yHi - yLo);
      if (!xTicks().some(t => Math.abs(t - p.x) < spanX * 0.025)) {
        axg.append('line').attr('x1', px).attr('y1', zy - 4).attr('x2', px).attr('y2', zy + 4)
          .attr('stroke', COL.ink).attr('stroke-width', 1.4);
        haloText(axg, px, zy + 8, fmt(p.x), 'middle', 'hanging');
      }
      if (!yTicks().some(t => Math.abs(t - p.y) < spanY * 0.025)) {
        axg.append('line').attr('x1', zx - 4).attr('y1', py).attr('x2', zx + 4).attr('y2', py)
          .attr('stroke', COL.ink).attr('stroke-width', 1.4);
        haloText(axg, zx - 8, py, fmt(p.y), 'end', 'middle');
      }
      g.append('circle').attr('cx', px).attr('cy', py).attr('r', 4)
        .attr('fill', COL.ink).attr('stroke', COL.halo).attr('stroke-width', 1.6);
      return;
    }

    const dot = g.append('circle').attr('cx', px).attr('cy', py)
      .style('cursor', 'pointer');
    // Подпись живёт в своей группе: её показываем и прячем, не трогая остальное.
    const lab = g.append('g').attr('class', 'cross-label').style('display', 'none');
    haloText(lab, px + 9, py - 9, '(' + fmt(p.x) + '; ' + fmt(p.y) + ')', 'start', 'auto');
    // «Закрепка» рядом с координатами: кладёт точку в список своих точек.
    const pin = lab.append('g').attr('class', 'cross-pin').style('cursor', 'pointer');
    pin.append('rect').attr('x', px + 9).attr('y', py - 5).attr('width', 15).attr('height', 15)
      .attr('rx', 3).attr('fill', COL.halo).attr('stroke', COL.inkSoft).attr('stroke-width', 1);
    pin.append('path')
      .attr('d', `M${px + 12.5},${py + 7} l0,-3 l6,-6 l3,3 l-6,6 z`)
      .attr('fill', 'none').attr('stroke', COL.inkSoft).attr('stroke-width', 1.2)
      .attr('stroke-linejoin', 'round');
    pin.append('title').text('Добавить в список точек');
    pin.on('click', (ev) => { ev.stopPropagation(); pinKeyPoint(p); });

    const paint = () => {
      const hot = (STATE.hotCross === i) || (STATE.hoverCross === i);
      dot.attr('r', hot ? 5 : 4)
         .attr('fill', hot ? COL.ink : COL.halo)
         .attr('stroke', hot ? COL.ink : COL.inkSoft)
         .attr('stroke-width', hot ? 2 : 1.4)
         .attr('opacity', hot ? 1 : 0.55);
      // Координаты и закрепка — только у закреплённой щелчком точки: при простом
      // наведении показывать нечего, а всплывающая подсказка «КТВ и ось Y»
      // раньше только мешала (её больше нет совсем).
      lab.style('display', (STATE.hotCross === i) ? null : 'none');
    };
    paint();
    dot.on('click', (ev) => { ev.stopPropagation(); STATE.hotCross = (STATE.hotCross === i) ? null : i; redrawAll(); })
       .on('pointerenter', () => { STATE.hoverCross = i; paint(); })
       .on('pointerleave', () => { if (STATE.hoverCross === i) STATE.hoverCross = null; paint(); });
  });
}

/* Закрепка: ключевая точка становится обычной своей точкой — последней в
   списке. Блок «Точки на графике» при этом раскрывается сразу же, иначе точка
   уходит в закрытую карточку и выглядит как «ничего не произошло». */
function pinKeyPoint(p) {
  STATE.hotCross = null;
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
  dot.append('title').text(text);
  return lab;
}

function drawRoller() {
  const r = STATE.roller;
  if (!r) return;
  const { mx, my } = mainScales();
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
  const { mx, my } = mainScales();
  const targets = snapTargets();
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
  return (best && best.d <= ROLL_PX) ? best.t : null;
}

const ROLL_PX = 12;    // на каком расстоянии нажатие считается «по кривой»

/* Осмысленная область кривой. На КПВ за точкой пересечения с осью кривой нет,
   и катать по ней точку в отрицательных значениях бессмысленно. Возвращаем
   ближайший к запрошенному x, где функция считается и (в сценах первой
   четверти) не уходит ниже оси; годной точки нет — null. */
function rollerClampX(f, x) {
  const { mx } = mainScales();
  let [lo, hi] = mx.domain();
  if (STATE.firstQuad) lo = Math.max(lo, 0);
  const ok = (t) => { const v = f(t); return isFinite(v) && (!STATE.firstQuad || v >= -1e-9); };
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
  const { mx } = mainScales();
  const x = rollerClampX(r.f, mx.invert(px));
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
function axisXLetter() {
  return (STATE.axisXName || STATE.axisXDefault || 'x').trim() || 'x';
}

/* ── Вершины площади щелчками (Фаза 7) ────────────────────────────────
   Режим «Между точками» переводит график в набор вершин: каждый щелчок
   ставит вершину, рядом с особой точкой она прыгает точно в неё. Галочки
   в списке для этого больше не нужны. */
function armVerts(on) {
  STATE.vertArm = !!on;
  const wrap = document.getElementById('graph-wrap');
  if (wrap) wrap.style.cursor = STATE.vertArm ? 'crosshair' : '';
  if (!STATE.vertArm) showSnapHint(null);
  renderVertList();
}

function addAreaVert(x, y, name) {
  STATE.areaVerts = STATE.areaVerts || [];
  STATE.areaVerts.push({ x, y, name: name || '' });
  renderVertList();
  redrawAll();
}

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
  box.innerHTML = '';
  list.forEach((p, i) => {
    const row = document.createElement('div');
    row.className = 'vert-row';
    const n = document.createElement('b'); n.textContent = (i + 1) + '.';

    const t = document.createElement('span');
    t.className = 'vert-co';
    t.title = 'Двойной щелчок — поправить координаты';
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
    del.title = 'Убрать эту вершину';
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
    ? ((STATE.areaVerts || []).length >= 3)
    : !!areaPickedCurve();
  btn.disabled = !ready;
  btn.title = ready ? '' : (STATE.areaCalcMode === 'poly'
    ? 'Отметьте на графике хотя бы три точки'
    : 'Сначала выберите кривую');
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
  const a = Math.max(0, viewWindow().x0);
  const b = curveRightEdge(t.f);
  return (isFinite(a) && isFinite(b) && b > a) ? { a, b } : null;
}
function syncAreaRangeLabel() {
  const el = document.getElementById('ac-range');
  if (!el) return;
  const r = areaCurveRange();
  el.textContent = r
    ? ('на отрезке [' + fmt(r.a) + '; ' + fmt(r.b) + ']')
    : (areaTargets().length ? 'Выберите кривую' : 'Сначала постройте кривую');
}

// Набранные вершины на графике: номер у каждой и бледный контур будущей фигуры.
function drawAreaVerts() {
  const list = STATE.areaVerts || [];
  if (!list.length) return;
  const { mx, my } = mainScales();
  const g = svg.append('g').attr('class', 'area-verts').style('pointer-events', 'none');
  if (list.length >= 3) {
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
  const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
  list.forEach((p, i) => {
    const dot = g.append('circle').attr('cx', mx(p.x)).attr('cy', my(p.y)).attr('r', 4.5)
      .attr('fill', COL.halo).attr('stroke', COL.reg).attr('stroke-width', 2)
      .style('pointer-events', 'all').style('cursor', 'grab');
    haloText(g, mx(p.x) + 8, my(p.y) - 8, String(i + 1), 'start', 'auto');

    dot.on('pointerenter', () => dot.attr('r', 6.5).attr('stroke-width', 3))
       .on('pointerleave', () => dot.attr('r', 4.5).attr('stroke-width', 2));

    let moved = false;
    dot.call(d3.drag().container(() => svg.node())
      .on('start', () => { moved = false; })
      .on('drag', (ev) => {
        moved = true;
        const hit = snapVertexAt(ev.x, ev.y);
        p.x = hit ? hit.x : Math.max(xLo, Math.min(xHi, mx.invert(ev.x)));
        p.y = hit ? hit.y : Math.max(yLo, Math.min(yHi, my.invert(ev.y)));
        p.name = (hit && hit.key) ? hit.name : '';
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

function areaTargets() {
  return snapTargets();
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
  return { kind: 'curve', value: val, a, b, name };
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

function calcAreaPolygon() {
  const pts = (STATE.areaVerts || []).slice();
  if (pts.length < 3) return { error: 'Нужно хотя бы три вершины: щёлкните по графику ещё раз.' };
  const r = bestAreaRing(pts);
  return { kind: 'poly', value: ringArea(r.ring), exact: r.exact,
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
  res.label = (res.kind === 'curve') ? ('Площадь под ' + res.name) : 'Площадь по точкам';
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
  const { mx, my } = mainScales();
  const g = svg.append('g').attr('class', 'areacalc').attr('clip-path', 'url(#plot-clip)');
  list.forEach(r => {
    const color = r.color || COL.MR;
    if (r.kind === 'curve') {
      const t = areaTargets().filter(x => x.name === r.name)[0];
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
  box.innerHTML = '';
  if (!list.length) return;

  const table = document.createElement('div');
  table.className = 'area-table';
  // П44: столбцы «Названия» и «Площадь». «Отрезок» убран — он и так виден
  // рядом с выбором кривой, а в таблице только занимал место.
  const head = document.createElement('div');
  head.className = 'area-row area-head';
  ['Названия', 'Площадь', ''].forEach(t => {
    const c = document.createElement('span'); c.textContent = t; head.appendChild(c);
  });
  table.appendChild(head);
  list.forEach(r => {
    const row = document.createElement('div');
    row.className = 'area-row';

    const c1 = document.createElement('span');
    c1.className = 'area-what';
    // Шесть образцов, как и у всех остальных мест выбора цвета (П34).
    const pick = makeColorPicker(r.color, (hex) => { r.color = hex; redrawAll(); }, 'Цвет площади');
    const nameInp = document.createElement('input');
    nameInp.type = 'text'; nameInp.className = 'area-name'; nameInp.value = r.label;
    nameInp.title = 'Название площади';
    nameInp.addEventListener('input', () => { r.label = nameInp.value; });
    nameInp.addEventListener('change', () => redrawAll());
    c1.append(pick, nameInp);

    const c3 = document.createElement('b');
    c3.textContent = fmt(r.value);
    if (r.kind === 'poly' && r.exact === false) {
      c3.classList.add('area-approx');
      c3.title = 'Вершин больше восьми: полный перебор обходов слишком долгий, '
               + 'поэтому берётся приближение — обход вершин по кругу.';
    }

    const del = document.createElement('button');
    del.type = 'button'; del.className = 'btn-icon'; del.textContent = '×';
    del.title = 'Убрать эту площадь';
    del.addEventListener('click', () => {
      STATE.areaCalcList = STATE.areaCalcList.filter(x => x !== r);
      redrawAll();
    });

    row.append(c1, c3, del);
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
    }
  }
  renderVertList();
  syncAreaRangeLabel();
  syncAreaCalcButton();
  updateQuickArea();
}

// Быстрая кнопка у графика, когда вершин набрано достаточно.
function updateQuickArea() {
  const b = document.getElementById('quick-area');
  if (!b) return;
  const n = (STATE.areaVerts || []).length;
  const show = (STATE.areaCalcMode === 'poly') && n >= 3;
  b.hidden = !show;
  if (show) b.textContent = 'Площадь по ' + n + ' точкам';
}

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
  const q = document.getElementById('quick-area');
  if (q) q.addEventListener('click', () => { setAreaCalcMode('poly'); runAreaCalc(); });
  // Выбрали кривую — сразу видно, на каком отрезке считаем, и кнопка загорается.
  const pick = document.getElementById('ac-pick');
  if (pick) pick.addEventListener('change', () => { syncAreaRangeLabel(); syncAreaCalcButton(); });
  const vClear = document.getElementById('ac-vert-clear');
  if (vClear) vClear.addEventListener('click', () => clearAreaVerts());
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
const AXIS_VARS = new Set(['x', 'y', 'Q', 'P', 'L', 'K', 'X', 'Y']);

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
function expandImplicitMul(expr) {
  const s = String(expr || '');
  if (!s) return s;
  return s.replace(/[A-Za-z_][A-Za-z_]*/g, (name, at) => {
    if (name.length < 2) return name;
    if (ECON_WORDS.has(name) || MATH_CONSTS.has(name)) return name;
    try { if (typeof math[name] !== 'undefined') return name; } catch (e) {}
    // Имя перед скобкой — вызов функции, разбирать его на буквы нельзя.
    const after = s.slice(at + name.length).match(/^\s*\(/);
    if (after) return name;
    if (!/^[A-Za-z]+$/.test(name)) return name;
    return name.split('').join('*');
  });
}

/* Формула в том виде, в каком её считает движок. Раскрытие неявного умножения
   включается только там, где буквы и так становятся ползунками: в готовых
   экономических сценах у обозначений свой смысл, и трогать их нельзя. */
function prepExpr(expr) {
  return paramsAllowed() ? expandImplicitMul(expr) : String(expr || '');
}

/* Свободные буквы формулы: то, что придётся чем-то заменить при расчёте.

   Запись уравнением («x + y = 10», «x^2 + y^2 = 25») разбираем по частям.
   Math.js считает «=» присваиванием и требует слева одно имя, поэтому на целом
   уравнении parse падал, а мы молча возвращали пустой список — и у формул,
   записанных уравнением (ограничение, неявная КПВ), буква-параметр не
   заводилась совсем (Н7). */
function freeSymbols(expr) {
  const out = [];
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
    } catch (e) {}
  };
  const s = String(expr || '');
  // Только одиночное «=»; «==», «<=», «>=», «!=» это сравнения, их не делим.
  const parts = s.split(/(?<![<>=!])=(?!=)/);
  if (parts.length === 2) { scan(parts[0]); scan(parts[1]); } else scan(s);
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
  const take = (expr) => { if (expr) freeSymbols(expr).forEach(n => { if (names.indexOf(n) < 0) names.push(n); }); };
  STATE.curves.forEach(c => take(c.expr));
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
  Object.keys(STATE.params).forEach(n => {
    if (names.indexOf(n) < 0) { delete STATE.params[n]; changed = true; }
  });
  if (changed) {
    const panel = document.getElementById('params-panel');
    if (panel) panel._extraSig = '';     // пересобрать правую панель
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
  lab.classList.add('param-eq');
  const paintEq = () => {
    if (typeof katex === 'undefined') { lab.textContent = name + ' = ' + fmt(p.value); return; }
    try { katex.render(name + ' = ' + fmt(p.value).replace(/ /g, '\\,'), lab,
                       { throwOnError: false, displayMode: false }); }
    catch (e) { lab.textContent = name + ' = ' + fmt(p.value); }
  };

  /* Точное значение (П24): отдельного поля нет, щёлкают прямо по формуле.
     Число справа при этом лишнее — вся строка «a = 1» и есть значение. */
  val.style.display = 'none';
  lab.classList.add('pchip-editable');
  lab.title = 'Щёлкните, чтобы ввести точное значение';

  /* Крестик справа вверху — как у Desmos. У нас параметр не объявляют строкой,
     а выводят из формулы, поэтому «удалить» его насовсем нельзя: syncParams
     завёл бы его заново на следующей перерисовке, а формула осталась бы без
     значения. Поэтому крестик СВОРАЧИВАЕТ ползунок: буква держит своё нынешнее
     значение, строка ужимается до «a = 1», а щелчок по ней разворачивает
     обратно. Чтобы убрать параметр совсем, букву стирают из формулы (П18). */
  const kill = document.createElement('button');
  kill.type = 'button'; kill.className = 'param-kill';
  kill.textContent = '✕';
  kill.title = 'Свернуть ползунок (буква останется с этим значением)';
  kill.setAttribute('aria-label', kill.title);
  chip.querySelector('.pchip-top').appendChild(kill);

  const track = document.createElement('div');
  track.className = 'param-track';
  const loLab = document.createElement('button');
  loLab.type = 'button'; loLab.className = 'param-bound';
  loLab.title = 'Границы и шаг';
  const hiLab = document.createElement('button');
  hiLab.type = 'button'; hiLab.className = 'param-bound';
  hiLab.title = 'Границы и шаг';

  const sl = document.createElement('input');
  sl.type = 'range'; sl.style.accentColor = cssVar('--accent');
  track.append(loLab, sl, hiLab);
  chip.appendChild(track);

  const editor = document.createElement('div');
  editor.className = 'param-editor';
  chip.appendChild(editor);

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
    kill.title = p.folded ? 'Показать ползунок' : 'Свернуть ползунок (буква останется с этим значением)';
    kill.setAttribute('aria-label', kill.title);
  };
  applyFold();
  kill.addEventListener('click', (e) => { e.stopPropagation(); p.folded = !p.folded; applyFold(); });

  sl.addEventListener('input', () => {
    p.value = parseFloat(sl.value);
    val.textContent = fmt(p.value);
    redrawAll();
  });

  lab.addEventListener('click', () => {
    if (p.folded) { p.folded = false; applyFold(); return; }   // свёрнутый — сначала разворачиваем
    const inp = document.createElement('input');
    inp.type = 'number'; inp.step = 'any'; inp.value = p.value;
    inp.className = 'pchip-valedit';
    lab.replaceWith(inp);
    inp.focus(); inp.select();
    const done = () => {
      const v = parseFloat(inp.value);
      if (isFinite(v)) {
        p.value = v;
        if (v < p.min) p.min = v;      // вышли за границу — она раздвигается сама
        if (v > p.max) p.max = v;
      }
      inp.replaceWith(lab);
      syncSlider();
      redrawAll();
    };
    inp.addEventListener('blur', done);
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); inp.blur(); } });
  });

  // Редактор границ: «мин ≤ имя ≤ макс» плюс шаг — прямо в строке.
  const openEditor = () => {
    if (editor.classList.contains('open')) { editor.classList.remove('open'); editor.innerHTML = ''; return; }
    editor.classList.add('open');
    editor.innerHTML = '';
    const mk = (key) => {
      const n = document.createElement('input');
      n.type = 'number'; n.step = 'any'; n.value = p[key];
      n.addEventListener('change', () => {
        const v = parseFloat(n.value);
        if (!isFinite(v)) return;
        p[key] = v;
        if (p.max <= p.min) p.max = p.min + 1;
        p.value = Math.max(p.min, Math.min(p.max, p.value));
        syncSlider();
        redrawAll();
      });
      return n;
    };
    /* Строка «−10 ≤ a ≤ 10» набрана формулой целиком, а не собрана из текстовых
       знаков: неравенства и курсивная буква печатаются KaTeX, как у Desmos. */
    const tex = (t) => {
      const s = document.createElement('span'); s.className = 'param-ed-tex';
      if (typeof katex === 'undefined') { s.textContent = t.replace(/\\le/g, '≤'); return s; }
      try { katex.render(t, s, { throwOnError: false, displayMode: false }); }
      catch (e) { s.textContent = t.replace(/\\le/g, '≤'); }
      return s;
    };
    const line = document.createElement('div');
    line.className = 'param-ed-line';
    line.append(mk('min'), tex('\\le ' + name + ' \\le'), mk('max'));
    const line2 = document.createElement('div');
    line2.className = 'param-ed-line';
    const st = document.createElement('span'); st.className = 'param-ed-name'; st.textContent = 'Шаг';
    line2.append(st, mk('step'));
    const ok = document.createElement('button');
    ok.type = 'button'; ok.className = 'param-ed-ok'; ok.textContent = 'Готово';
    ok.addEventListener('click', () => { editor.classList.remove('open'); editor.innerHTML = ''; });
    editor.append(line, line2, ok);
  };
  loLab.addEventListener('click', openEditor);
  hiLab.addEventListener('click', openEditor);

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
function drawGraphTitle() {
  const t = (STATE.graphTitle || '').trim();
  if (!t) return;
  const m = CONFIG.margin;
  svg.append('text')
    .attr('x', (m.left + (W - m.right)) / 2).attr('y', Math.max(17, m.top - 11))
    .attr('text-anchor', 'middle').attr('font-size', 15).attr('font-weight', 650)
    .attr('fill', STATE.titleColor || COL.ink)
    .attr('paint-order', 'stroke').attr('stroke', COL.halo).attr('stroke-width', 3)
    .text(t);
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
  return '#888888';
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
  btn.title = title || 'Цвет кривой';
  btn.setAttribute('aria-label', btn.title);

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
      sw.title = hex;
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
function curveShortName(c) {
  const custom = (c.label || '').trim();
  if (custom) return custom;
  const byRole = { demand: 'D', supply: 'S', mc: 'MC', tc: 'TC', atc: 'ATC' };
  if (c.role && byRole[c.role]) return byRole[c.role];
  return (c.name || c.expr || '').trim() || '?';
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
  const { mx, my } = mainScales();
  const g = svg.append('g').attr('class', 'marks');
  const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
  STATE.marks.forEach(mk => {
    // Точка, у которой заполнено ещё не всё, на плоскости не появляется (П28).
    if (mk.pending || !isFinite(mk.x) || !isFinite(mk.y)) return;
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
        if (!mk.snapTo) {
          const hit = snapPointAt(ev.x, ev.y);
          if (hit && !hit.cross) mk.snapTo = hit.name;
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
        .attr('font-size', 11.5).attr('font-weight', i === 0 ? 650 : 500).attr('fill', col)
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
function snapTargets() {
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
    out.push({ name: 'TP', f: prodEval });
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
  // Два завода: совокупные предельные издержки — это горизонтальная сумма,
  // и она уже посчитана таблицей. Катаемся по ней, а не по TC₁ и TC₂.
  if (STATE.mode === 'costs' && STATE.costsSub === 'plants' && STATE.plants) {
    const p = STATE.plants;
    out.push({ name: 'MC', f: (q) => interpY(p.table.map(r => [r.Q, r.m]), q) });
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
  STATE.curves.filter(c => c.visible && !isVertical(c)).forEach(c => {
    out.push({ name: curveShortName(c), f: (q) => evalCurve(c, q) });
  });
  return out;
}

/* Кривые раздела «Математика» для прокатывания и пересечений. Берём то же,
   что сцена рисует: саму функцию, а в сюжетах со сравнением — все участвующие
   кривые. Вспомогательные линии (касательная, секущая) сюда не идут: по ним
   не катаются, и пересечения с ними только загромождали бы поле. */
function mathSnapTargets(out) {
  const f = mathF();
  const sub = STATE.mathSub;
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
    if (b.co1) out.push({ name: 'КПВ 1', f: (x) => interpY(b.co1.ppts, x) });
    if (b.co2) out.push({ name: 'КПВ 2', f: (x) => interpY(b.co2.ppts, x) });
  }
}

// Ближайшая точка НА кривых к пикселю (px, py) или null, если все далеко.
/* Оси как цель прилипания (П31). В snapTargets их нет и быть не должно: там
   лежат кривые вида y = f(x), по ним ищутся экстремумы и изломы, а у прямой
   y = 0 производная нулевая всюду и «экстремумом» оказался бы каждый узел.
   Поэтому оси считаем отдельно, и ось Y — вертикаль, для которой f(x) вообще
   не определена. */
function axisSnapAt(px, py) {
  const { mx, my } = mainScales();
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
  const { mx, my } = mainScales();
  if (name === 'ось X') return Math.abs(py - my(0));
  if (name === 'ось Y') return Math.abs(px - mx(0));
  if (name === 'начало координат') return Math.hypot(px - mx(0), py - my(0));
  const t = snapTargets().filter(t => t.name === name)[0];
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
  const { mx, my } = mainScales();
  const targets = snapTargets();
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
  const { mx, my } = mainScales();
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
  STATE.markArm = on;
  const wrap = document.getElementById('graph-wrap');
  if (wrap) wrap.style.cursor = on ? 'crosshair' : '';
  if (!on) showSnapHint(null);   // снятый режим не оставляет кружок-подсказку
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
  roller: null, hotCross: null, hoverCross: null, pointNames: {},
  markArm: false, vertArm: false,
  // Заливки и цвета.
  showCS: true, showPS: true, showGhost: false,
  showMonoCS: true, showMonoPS: true, showMonoVC: false,
  colorOverride: {}, areaColor: {},
  // Плоскость и подписи.
  labelSize: LABEL_SIZE_DEFAULT, firstQuad: true, xStep: null, yStep: null,
  showLegend: true, zoomLock: false, viewDirty: false,
  // Буквы-параметры и кэши расчётов.
  params: {}, ppfSumData: null, ppfTradeData: null, mathRes: null,
  bundleOn: false, bundleX: null, bundleY: null,
  ineqMasterBase: null, ineqMasterDetached: false, ineqMasterS: 1,
};

function resetDecor() {
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
  'costsTC', 'costsFC', 'ineqIncomes', 'ineqFormula', 'mathFormula',
  'tax', 'pReg', 'taxKind', 'intervType',
]);
const _sceneSnaps = {};

// Забыть, что помнилось по моделям. Нужно, когда состояние надо начать с нуля
// (например, в контрольных прогонах, где каждый случай ставит свою обстановку).
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
  renderMarkList();
  renderVertList();
  renderCurveList();
  return true;
}

function addMarkAt(x, y, snapTo) {
  // Щелчок по графику в режиме «Указать на графике» достраивает уже заведённую
  // заготовку, а не плодит вторую точку (П28).
  const draft = pendingMark();
  if (draft) {
    draft.x = x; draft.y = y; draft.snapTo = snapTo || null;
    draft.pending = false;
    renderMarkList();
    redrawAll();
    return;
  }
  STATE.marks.push(newMark(x, y, snapTo, 'graph'));
  renderMarkList();
  redrawAll();
}

/* Заготовка точки: строка списка уже есть, а на плоскости точки ещё нет.
   Так работает пайплайн П28 — тумблер и поля координат живут в той же строке,
   которая потом станет обычной строкой точки, и фокус при наборе не теряется. */
function newMark(x, y, snapTo, mode) {
  markCounter++;
  return {
    id: markCounter, x, y, text: 'Точка ' + markCounter,
    showCoords: true, showDash: true, color: null,
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

  const add = document.createElement('button');
  add.type = 'button'; add.className = 'btn-sm btn-mark-add';
  add.textContent = 'Добавить точку';
  add.addEventListener('click', () => startMarkDraft());
  if (!pendingMark()) box.appendChild(add);
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
    seg = document.createElement('div');
    seg.className = 'seg mark-mode';
    const mkBtn = (mode, text) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'seg-btn' + (mk.mode === mode ? ' active' : '');
      b.textContent = text;
      b.addEventListener('click', () => {
        if (!mk.pending) return;
        mk.mode = mode;
        armMark(mode === 'graph');
        renderMarkList();
      });
      return b;
    };
    seg.append(mkBtn('coords', 'Ввести координаты'), mkBtn('graph', 'Указать на графике'));
    row.appendChild(seg);
  }

  if (mk.pending && mk.mode === 'graph') {
    const hint = document.createElement('div');
    hint.className = 'mark-hint';
    hint.textContent = 'Нажмите на график!';
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
  const mkNum = (key, label) => {
    const l = document.createElement('label'); l.textContent = label;
    const n = document.createElement('input');
    n.type = 'number'; n.step = 'any';
    n.value = isFinite(mk[key]) ? Math.round(mk[key] * 1000) / 1000 : '';
    n.addEventListener('input', () => {
      const v = parseFloat(n.value);
      mk[key] = isFinite(v) ? v : NaN;
      // Точка на кривой держится за неё: меняем x, высоту берём с кривой.
      const f = markSnapFn(mk);
      if (f && key === 'x' && isFinite(v)) { const y = f(v); if (isFinite(y)) mk.y = y; }
      const ready = isFinite(mk.x) && isFinite(mk.y);
      if (mk.pending && ready) {
        mk.pending = false;
        if (seg) seg.remove();          // способ ввода выбран, тумблер больше не нужен
        row.classList.remove('mark-draft');
        const box = document.getElementById('mark-list');
        if (box && !box.querySelector('.btn-mark-add')) {
          const add = document.createElement('button');
          add.type = 'button'; add.className = 'btn-sm btn-mark-add';
          add.textContent = 'Добавить точку';
          add.addEventListener('click', () => startMarkDraft());
          box.appendChild(add);
        }
      } else if (!ready && !mk.pending) {
        mk.pending = true;                     // стёрли координату — точка ушла
      }
      redrawAll();
    });
    nums[key] = n;
    xy.append(l, n);
  };
  mkNum('x', 'X');
  mkNum('y', 'Y');
  if (mk.pending) { row.appendChild(xy); return row; }   // остальное — когда точка встанет

  const top = document.createElement('div');
  top.className = 'mark-top';
  const pick = makeColorPicker(mk.color || COL.ink, (hex) => { mk.color = hex; redrawAll(); }, 'Цвет точки');
  const co = document.createElement('span');
  co.className = 'mark-co';
  co.textContent = mk.snapTo ? ('На ' + mk.snapTo) : 'Своя точка';
  const del = document.createElement('button');
  del.className = 'btn-icon'; del.type = 'button'; del.textContent = '✕'; del.title = 'Убрать точку';
  del.addEventListener('click', () => {
    STATE.marks = STATE.marks.filter(m => m.id !== mk.id);
    renderMarkList(); redrawAll();
  });
  top.append(pick, co, del);

  const inp = document.createElement('input');
  inp.type = 'text'; inp.value = mk.text; inp.placeholder = 'Подпись точки';
  inp.addEventListener('input', () => { mk.text = inp.value; redrawAll(); });

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

  row.append(top, inp, xy,
    toggle('Пунктир к осям', 'showDash', true),
    toggle('Координаты', 'showCoords', true));

  // Точка, посаженная на кривую или ось, скользит по ней. Галочка отпускает её,
  // если нужно поставить отметку рядом, а не на самой линии.
  if (mk.snapTo) {
    const w = document.createElement('label');
    w.className = 'chk';
    const c = document.createElement('input'); c.type = 'checkbox'; c.checked = true;
    c.addEventListener('change', () => { if (!c.checked) mk.snapTo = null; renderMarkList(); redrawAll(); });
    w.append(c, document.createTextNode('Держать на линии ' + mk.snapTo));
    row.appendChild(w);
  }
  return row;
}
