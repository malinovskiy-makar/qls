// Правая панель: регуляторы сцены и ползунки кривых.
/* ---------------------------------------------------------------------
   ПУЛЬТ — единое «рабочее место руками» для ВСЕХ сцен.
   Лента собирается для АКТИВНОЙ сцены из трёх источников:
   (1) слайдеры сдвига видимых линейных кривин (#pult-curves) — ползунок задаёт
       свободный член b ТЕМ ЖЕ путём, что перетаскивание (setCurveFreeTerm);
   (2) сцен-слайдеры (#pult-extra), генерируемые для сцены: КПВ «Макс X/Y»
       (одна — 2, сумма — 4 по странам) и мастер «Сила неравенства». Каждый
       задаёт реальное состояние ТЕМ ЖЕ путём, что ручной ввод (формула КПВ /
       поля долей), и зовёт штатный redraw — новой экономики нет;
   (3) ЭКРАННЫЕ регуляторы сцены (ставка/цена/зарплата/МРОТ/мировая цена/α),
       которые ФИЗИЧЕСКИ переносятся из «Инструментов» в пульт через appendChild
       (ID и обработчики сохраняются — НЕ клонируем) и возвращаются домой.
   Всё вычисляется по текущему STATE — механизм единый для всех режимов.
   --------------------------------------------------------------------- */

// Все переносимые экранные регуляторы (по всем сценам). «Дом» каждого запоминается
// при первом обращении (исходный родитель + стабильный якорь) — поддержка любой секции.
// «Вид ставки» (taxkind-row) намеренно НЕ переносится в ленту: это разовая настройка
// постановки задачи, а не живой регулятор — иначе лента вырастает в три ряда и
// закрывает график. Живой регулятор здесь один — сама ставка.
const PULT_MOVABLE = ['mono-submode',                                          // монополия: под-режим
  'taxside-row', 'tax-field', 'pc-field', 'quota-field', 'quota-price-field',  // рынок: вмешательство
  'open-pw-field', 'open-tariff-field', 'open-quota-field',                    // открытая экономика
  'union-wage-field', 'labmin-field',                                  // труд: зарплата / МРОТ
  'ppft-price-field', 'tb-price-field',                                // КТВ: мировая цена (A / Б)
  'ineq-alpha-field',                                                  // неравенство: α (формула)
  'cons-px1-row',                                                      // потребитель: новая цена Px₁
  'lr-price-field', 'pl-q-field',                                      // фирма: цена P / выпуск двух заводов
  'ma-dg-field', 'ma-fx-fixed-field'];                                 // макро: дефицит ΔG / фикс. курс
const PULT_MOVABLE_SET = new Set(PULT_MOVABLE);

// Какие экранные регуляторы должны жить в пульте ПРЯМО СЕЙЧАС (по состоянию).
function pultRegulatorIds() {
  if (STATE.mode === 'market') {
    // Малая открытая экономика (Фаза 4в): мировая цена — главный живой регулятор,
    // рядом — ставка действующего инструмента.
    if (STATE.scenario === 'openecon') {
      const ids = ['open-pw-field'];
      if (STATE.openTool === 'tariff') ids.push('open-tariff-field');
      else if (STATE.openTool === 'quota') ids.push('open-quota-field');
      return ids;
    }
    const bs = baseScene();   // 'mono-nat' и т.п. для пульта — та же сцена 'mono'
    const interventionScene = (bs === 'tax' || bs === 'ceil' || bs === 'mono');
    if (!interventionScene) return [];
    // Монополия: переключатель под-режима — главный регулятор сцены, поэтому он в ленте
    // (Фаза 3а: раньше жил только в свёрнутых «Инструментах» и был не виден).
    // Вмешательство государства считается лишь в под-режиме «Обычная» (см. recompute),
    // поэтому в остальных под-режимах поля ставки/цены в ленту не выносим.
    if (STATE.market === 'monopoly') {
      if (STATE.monoMode !== 'simple') return ['mono-submode'];
      const t0 = STATE.intervType;
      const ids = ['mono-submode'];
      if (t0 === 'tax' || t0 === 'subsidy') ids.push('tax-field'); else ids.push('pc-field');
      return ids;
    }
    const t = STATE.intervType;
    if (t === 'tax' || t === 'subsidy') {
      const ids = [];
      // Ряд стороны живёт в ленте ровно тогда, когда каскад его показывает:
      // потоварный налог и любая субсидия. У НДС и акциза стороны нет.
      const sideOn = (STATE.market !== 'monopoly')
                  && ((t === 'tax' && STATE.taxForm === 'unit') || t === 'subsidy');
      if (sideOn) ids.push('taxside-row');
      ids.push('tax-field');
      return ids;
    }
    if (t === 'quota') {
      // Объём квоты — живой регулятор; выбор цены внутри коридора появляется
      // рядом с ним ровно тогда, когда коридор есть.
      return STATE.quotaActive ? ['quota-field', 'quota-price-field'] : ['quota-field'];
    }
    return ['pc-field'];   // потолок / пол
  }
  if (STATE.mode === 'labor') {
    const ids = [];
    if (STATE.laborStruct === 'union' && STATE.unionModel === 'wagefloor') ids.push('union-wage-field');
    if (STATE.laborStruct !== 'union' && STATE.laborMinOn) ids.push('labmin-field');
    return ids;
  }
  if (STATE.mode === 'ppf' && STATE.ppfSub === 'trade') {
    return [STATE.tradeScenario === 'B' ? 'tb-price-field' : 'ppft-price-field'];
  }
  if (STATE.mode === 'inequality' && STATE.ineqInput === 'formula') {
    return ['ineq-alpha-field'];
  }
  // Потребитель (Фаза 8): живой регулятор — новая цена Px₁ при разложении Слуцкого.
  if (STATE.mode === 'consumer') {
    return STATE.consSlutskyOn ? ['cons-px1-row'] : [];
  }
  // Фирма (Фаза 9): рыночная цена в сюжете «Издержки» — от неё зависит прибыль.
  // Макро (Фазы 16–22): живой регулятор — дефицит бюджета / фиксированный курс.
  if (STATE.mode === 'macro') {
    if (STATE.macroModel === 'loanable') return ['ma-dg-field'];
    if (STATE.macroModel === 'fx' && STATE.macro.fx.fixedOn) return ['ma-fx-fixed-field'];
    return [];
  }
  if (STATE.mode === 'costs') {
    if (STATE.costsSub === 'plants') return ['pl-q-field'];
    return (STATE.costsSub === 'costs' && STATE.lrOn) ? ['lr-price-field'] : [];
  }
  return [];
}

// Линейные (=> перетаскиваемые) видимые кривые активной сцены — под слайдеры.
// Рынок и труд держат D/S в STATE.curves; остальные режимы — свои кривые без сдвига.
/* Б34. Ползунок «Сдвиг кривых» — второй показ того же действия, что и
   перетаскивание кривой мышью. В перегруженных сюжетах убираем оба: там
   двигается своё (точки эластичности, линия ставки), и лишние ручки только
   мешают попасть в нужную. Список общий с curveDragAllowed. */
function pultCurveList() {
  if (typeof curveDragAllowed === 'function' && !curveDragAllowed()) return [];
  // Под-режимы монополии «Дискр. 3°» и «Составной спрос» рисуются по СВОИМ полям формул,
  // а не по списку кривых — слайдеры сдвига там ничего бы не двигали на графике.
  if (STATE.mode === 'market' && STATE.market === 'monopoly' &&
      (STATE.monoMode === 'discr3' || STATE.monoMode === 'kinked')) return [];
  if (STATE.mode === 'market' || STATE.mode === 'labor') return STATE.curves.filter(c => c.linear && c.visible);
  return [];
}

// Сцен-слайдеры (#pult-extra): что определяет их НАБОР (для пере-сборки при смене).
function pultExtraSig() {
  const ps = Object.keys(STATE.params || {}).sort().join(',');
  const tail = ps ? ('|par:' + ps) : '';
  if (tail) return pultExtraSigBase() + tail;
  return pultExtraSigBase();
}
function pultExtraSigBase() {
  if (STATE.mode === 'ppf') {
    if (STATE.ppfSub === 'single') return 'ppf1';   // одна КПВ → Макс X / Макс Y
    if (STATE.ppfSub === 'sum')    return 'ppf2';   // сумма → 4 ползунка по странам
    return '';                                       // КТВ — мировая цена идёт регулятором
  }
  if (STATE.mode === 'inequality' && (STATE.ineqInput === 'groups' || STATE.ineqInput === 'incomes')) return 'ineqM';
  return '';
}

// Панель нужна, если есть хоть один регулятор, слайдер кривой, сцен-слайдер
// или ползунок параметра.
function pultShouldShow() {
  return pultRegulatorIds().length > 0 || pultCurveList().length > 0 ||
         pultExtraSig() !== '' || Object.keys(STATE.params || {}).length > 0;
}


/* Имя регулятора сдвига: «Сдвиг D». Буква кривой уезжает в набор формулой
   (texifyName делает из одинокой латинской буквы курсивную переменную), а
   слово «Сдвиг» остаётся прямым текстом. Длинное своё имя кривой сокращаем
   так же, как раньше: колонка панели узкая. */
function shiftChipLabel(c) {
  return 'Сдвиг ' + curveChipLabel(c);
}

// Короткая метка кривой для чипа: по роли, иначе усечённая формула.
function curveChipLabel(c) {
  const f = curveShortName(c);   // своё имя → роль → формула (Фаза 1)
  return f.length > 16 ? f.slice(0, 15) + '…' : f;
}

// Сигнатура набора кривых — чтобы НЕ пересобирать чипы на каждом кадре перетаскивания
// (там меняется только b → достаточно обновить значения, см. syncPultCurveValues).
function pultCurveSig(list) {
  return list.map(c => c.id + ':' + (c.role || '') + ':' + c.color + ':' + (c.label || '')).join('|');
}

/* Строка «имя = значение», набранная формулой (Н8, Н11, Н12). Одна на все виды
   регуляторов: и на буквы из формул, и на встроенные ставки, зарплаты и мировые
   цены — раньше они выглядели по-разному, хотя делают одно и то же. */
function paintEqLabel(lab, name, value) {
  lab.classList.add('param-eq');
  lab.dataset.eqName = name;
  const plain = name + ' = ' + fmt(value);
  if (typeof katex === 'undefined') { lab.textContent = plain; return; }
  try {
    katexInto(lab, texifyName(name) + ' = ' + fmt(value));
  } catch (e) { lab.textContent = plain; }
}

/* Имя регулятора в математическом наборе. Одна латинская буква идёт как есть
   (курсивная переменная), обозначение вида «Pw» или «Wmin» становится буквой с
   индексом. Слово («Ставка», «Значение») набирается прямым текстом: разложить
   его на букву с индексом значило бы прочитать слово как произведение букв. */
function texifyName(name) {
  const s = String(name || '').trim();
  if (/^[A-Za-z]$/.test(s)) return s;
  /* «Сдвиг D» — слово прямым текстом, обозначение кривой набором. Без этой
     ветки вся строка уходила бы в \text{} целиком, и буква D стояла бы
     обычным шрифтом рядом с формулой на графике, где она курсивная. */
  const sh = s.match(/^(Сдвиг)\s+(.+)$/);
  if (sh) return '\\text{' + sh[1] + '\\,}' + texifyName(sh[2]);
  const m = s.match(/^([A-Za-z])([A-Za-z0-9]{1,4})$/);
  if (m && !/[А-Яа-я]/.test(s)) return m[1] + '_{\\text{' + m[2] + '}}';
  return '\\text{' + s.replace(/([{}\\$&#^_~%])/g, '\\$1') + '}';
}

/* Правка точного значения по щелчку на строке (Н12): «имя =» остаётся на месте,
   меняется только число справа, и набор при этом не превращается в системный
   шрифт — поле лежит ВНУТРИ той же формулы. */
function editEqValue(lab, name, current, apply) {
  if (lab.querySelector('input')) return;
  lab.innerHTML = '';
  const head = document.createElement('span');
  head.className = 'param-eq-head';
  if (typeof katex !== 'undefined') {
    if (!katexInto(head, texifyName(name) + ' =')) head.textContent = name + ' =';
  } else head.textContent = name + ' =';
  const inp = document.createElement('input');
  inp.type = 'number'; inp.step = 'any'; inp.value = current;
  inp.className = 'param-eq-input';
  lab.append(head, inp);
  /* Ширина поля идёт за содержимым: подчёркивание должно стоять ровно под
     числом, а не тянуться до края строки. У input[type=number] нет усадки
     по содержимому, поэтому считаем сами. */
  const fitWidth = () => { inp.style.width = Math.max(2, String(inp.value || '').length + 1) + 'ch'; };
  fitWidth();
  inp.addEventListener('input', fitWidth);
  /* ⚠️ СОДЕРЖИМОЕ ВЫДЕЛЯЕТСЯ ЦЕЛИКОМ: первый набранный символ заменяет старое
     значение. Это отмена прежнего решения «курсор в конец» (Н75): при a = 1
     набор «50» давал 150, а вместе с ним и границы 146…154 — то есть один
     промах уводил и значение, и полосу. Правило теперь общее для всех правок
     на месте, ровно как у makeEditableValue (А61): дописать к значению
     по-прежнему можно стрелкой или вторым щелчком. */
  inp.focus();
  try { inp.select(); } catch (e) {}
  let closed = false;
  const done = () => {
    if (closed) return; closed = true;
    const v = parseFloat(inp.value);
    if (isFinite(v) && v !== current) pushUndo();
    apply(isFinite(v) ? v : current);
  };
  inp.addEventListener('blur', done);
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
    if (e.key === 'Escape') { e.preventDefault(); inp.value = current; inp.blur(); }
  });
}

/* Меню интервала (Н9, Н10). Одно на все регуляторы: «мин ≤ имя ≤ макс» и шаг,
   всё набрано формулой. Кнопки «Готово» нет — правка применяется на каждый
   введённый символ, поэтому «−12» проезжает через «−» (неполное значение,
   пропускаем), «−1» и «−12». Закрывается тремя способами: тронули этот ползунок,
   ввели точное значение, щёлкнули мимо полей интервала. */
/* ⚠️ ПРАВИЛО ВЫХОДА ЗНАЧЕНИЯ ЗА ПОЛОСУ — ОДНО НА ВЕСЬ КАЛЬКУЛЯТОР, И СЛУЧАЕВ
   В НЁМ ДВА РАЗНЫХ (решение владельца 19.08).

   Случай первый: человек вписывает ЗНАЧЕНИЕ за пределами действующих границ.
   Границы переезжают так, чтобы новое значение встало ровно посередине; ширина
   полосы сохраняется. Проверка: границы −5…3 (ширина 8), вписали 50 → 46…54.
   Прежде граница просто раздвигалась до значения, и полоса становилась
   неуправляемо длинной: вписал 1000 при −10…10 — и шаг ползунка обесценился.

   Случай второй: человек задаёт ГРАНИЦЫ, не содержащие текущего значения.
   Здесь границы остаются как заданы, а подтягивается значение — к ближайшей
   границе. Проверка: значение 6, задали −1…1 → границы −1…1, значение 1.

   Разница не произвольная: человек всегда получает то, что назвал последним. */
function centerBandOn(band, value) {
  const width = Math.abs(band.max - band.min) || 2;
  return { min: value - width / 2, max: value + width / 2 };
}
function pullIntoBand(band, value) {
  return Math.max(band.min, Math.min(band.max, value));
}

function attachBoundsEditor(chip, editor, name, get, set) {
  const tex = (t) => {
    const s = document.createElement('span'); s.className = 'param-ed-tex';
    if (typeof katex === 'undefined') { s.textContent = t.replace(/\\le/g, '≤'); return s; }
    if (!katexInto(s, t)) s.textContent = t.replace(/\\le/g, '≤');
    return s;
  };
  const close = () => {
    if (!editor.classList.contains('open')) return;
    editor.classList.remove('open'); editor.innerHTML = '';
    const track = chip.querySelector('.param-track');
    if (track && track.dataset.hidden) { delete track.dataset.hidden; track.style.display = ''; }
    document.removeEventListener('pointerdown', onOutside, true);
  };
  /* Слушатель снимается и когда чип уехал из разметки: правая панель
     пересобирается целиком (innerHTML = ''), и открытое меню может исчезнуть
     вместе с ней, а слушатель остался бы висеть на документе и звать close()
     у оторванного узла. */
  function onOutside(e) {
    if (!chip.isConnected) { document.removeEventListener('pointerdown', onOutside, true); return; }
    const track = chip.querySelector('.param-track');
    if (!editor.contains(e.target) && !(track && track.contains(e.target))) close();
  }
  editor._close = close;
  const open = (side) => {
    if (editor.classList.contains('open')) { close(); return; }
    editor.classList.add('open');
    editor.innerHTML = '';
    /* Полоса ползунка и обе подписи границ на время правки убираются: их место
       и занимает меню. Копия Десмоса, и она же честнее — иначе на экране разом
       два способа задать одно и то же. */
    const track = chip.querySelector('.param-track');
    if (track) { track.dataset.hidden = '1'; track.style.display = 'none'; }
    /* Три значения интервала — тем же компонентом, что и всюду: пунктир снизу,
       правка на месте, ни одной прямоугольной рамки (Н75). Живое обновление на
       каждый символ; неполный ввод («−», «1e») компонент не применяет и красит
       подчёркивание. */
    /* ⚠️ ПОЛЯ ПУСТЫЕ, ДЕЙСТВУЮЩИЕ ЗНАЧЕНИЯ НЕ ПОДСТАВЛЯЮТСЯ. Это сознательная
       копия Десмоса: владелец выбрал именно так. Незаполненное поле сохраняет
       прежнее значение — см. `set` ниже, он зовётся только на осмысленный
       ввод. */
    const mk = (key) => makeEditableValue({
      get: () => '',
      set: (v) => {
        /* Пока идёт правка, меню закрывать нельзя: set() может зажать значение
           ползунка и разбудить «input», а тот закрыл бы меню и снёс поле, в
           котором прямо сейчас печатают. */
        // Вторая застава к правилу «пустое поле не трогает границу»: сюда
        // не должно доехать ничего, кроме числа.
        if (!isFinite(parseFloat(v))) return;
        editor._busy = true;
        pushUndo();
        try { set(key, +v); } finally { editor._busy = false; }
      },
      tex: (v, text) => text,
      title: key === 'step' ? 'Шаг' : (key === 'min' ? 'Нижняя граница' : 'Верхняя граница'),
    });
    // C.5: «мин ≤ имя ≤ макс с шагом …» одной строкой.
    const line = document.createElement('div'); line.className = 'param-ed-line';
    line.append(mk('min'), tex('\\le ' + texifyName(name) + ' \\le'), mk('max'),
                tex('\\text{с шагом}'), mk('step'));
    editor.append(line);
    document.addEventListener('pointerdown', onOutside, true);
    /* Курсор встаёт в поле ТОЙ границы, по которой щёлкнули: слева — в левое,
       справа — в правое. Правку открывает сама эта граница, значит и продолжить
       человек хочет с неё. */
    const fields = line.querySelectorAll('.edval');
    const want = (side === 'max') ? fields[1] : fields[0];
    if (want && want.click) { want.click(); }
    /* Enter закрывает и применяет. Щелчок мимо — тоже применяет, а не
       отменяет: проверено на Десмосе, введённое без Enter сохраняется. */
    line.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); close(); }
    });
  };
  return { open, close };
}

/* Строка «имя = значение» у всех регуляторов идёт за фактическим значением
   ползунка. Нужен общий проход: сцена ставит значение свойством, а не событием
   и не атрибутом, поэтому ни слушатель, ни наблюдатель такого не видят. */
const UPGRADED_REGULATORS = new Set();
function refreshRegulators() {
  UPGRADED_REGULATORS.forEach(field => {
    // Панели пересобираются целиком: то, что уехало из разметки, забываем.
    if (!field.isConnected) { UPGRADED_REGULATORS.delete(field); return; }
    if (typeof field._regSync === 'function') field._regSync();
  });
}

/* Заготовка регулятора для правой панели: сверху имя и значение, снизу
   ползунок во всю ширину. Одна форма на все виды регуляторов — колонка узкая,
   и в одну строку метка с числом уже не помещаются. */
function makePchip(labelText, valueText, color) {
  const chip = document.createElement('div'); chip.className = 'pchip';
  const top = document.createElement('div'); top.className = 'pchip-top';
  if (color) {
    const dot = document.createElement('span');
    dot.className = 'pchip-dot'; dot.style.background = color;
    top.appendChild(dot);
  }
  const lab = document.createElement('span'); lab.className = 'pchip-label'; lab.textContent = labelText;
  const val = document.createElement('span'); val.className = 'pchip-val'; val.textContent = valueText;
  top.append(lab, val);
  chip.appendChild(top);
  return { chip, lab, val };
}

// Построить (пересобрать) слайдеры кривых в контейнере #params-curves.
function buildPultCurveChips(list) {
  const body = document.getElementById('params-body');
  let box = document.getElementById('params-curves');
  if (!box) {
    box = document.createElement('div');
    box.id = 'params-curves';
    if (body) body.insertBefore(box, body.firstChild);
  }
  box.innerHTML = '';
  // Заголовок группы нужен, только когда рядом есть вторая группа: буквы из формул.
  if (list.length && Object.keys(STATE.params || {}).length) {
    const t = document.createElement('div');
    t.className = 'params-group-title'; t.textContent = 'Сдвиг кривых';
    box.appendChild(t);
  }
  list.forEach(c => {
    /* ⚠️ ПОЛЗУНОК ПОКАЗЫВАЕТ СДВИГ, А НЕ ЗНАЧЕНИЕ КРИВОЙ (решение владельца 22.08).
       Раньше в строке стояло «D = 100»: имя кривой и её свободный член. Подпись
       врала дважды — D это функция, а не число, и ползунок двигает не значение
       спроса, а параллельный сдвиг всей кривой. Теперь имя регулятора прямо
       называет действие («Сдвиг D», буква набрана формулой), а число рядом —
       это сам сдвиг: 0 на старте, 12 после протяжки вверх, −12 вниз.
       Свободный член кривой остаётся ЕДИНСТВЕННЫМ источником правды: сдвиг
       считается от значения, с которого модель открылась (base), и обратно в
       кривую кладётся тем же setCurveFreeTerm. */
    const base = c.linear.b;
    const { chip, lab, val } = makePchip(shiftChipLabel(c), fmt(0), c.color);
    chip.dataset.cid = c.id;
    // Подсказку вешаем на сам чип: подпись .pchip-label заменяет
    // upgradeRegulator строкой «имя = значение», и title на ней пропал бы.
    chip.title = 'Сдвиг кривой ' + curveShortName(c) + ': ' + (c.expr || '');

    const sl = document.createElement('input');
    /* ⚠️ ОДНО ЗНАЧЕНИЕ — ОДИН ИСТОЧНИК (п. 3, канон 2.1).
       Было: шаг 1 и `Math.round(c.linear.b)`, то есть у свободного члена
       появлялось ВТОРОЕ значение. После перетаскивания кривой формула
       становилась «85.22 - Q», а строка над ползунком показывала «D = 85»
       (её собирает upgradeRegulator из значения ползунка) — и первое же
       касание ползунка молча теряло 0,22.
       `step = 'any'` разрешает ползунку нести точное значение; клавиши-стрелки
       при этом по-прежнему ходят целыми (браузер берёт сотую долю размаха,
       а размах здесь 0…100). */
    /* Старт по центру диапазона — общее правило для всех ползунков аналитики.
       Диапазон симметричен вокруг нуля, поэтому ручка стоит ровно посередине
       и сразу видно, что двигать можно в обе стороны. Размах прежний (Pmax),
       просто он теперь отсчитывается от текущего положения кривой, а не от
       нуля оси цен. */
    const half = Math.max(1, CONFIG.Pmax / 2);
    sl.type = 'range'; sl.min = -half; sl.max = half; sl.step = 'any';
    sl.value = 0;
    sl.style.accentColor = c.color;   // акцент ползунка в цвет кривой
    // п. 78. Подсказка идёт через общую плашку, а не через нативный title:
    // тот не появляется ни с клавиатуры, ни на сенсорном экране.
    sl.setAttribute('data-tip', 'Параллельный сдвиг кривой по вертикали');

    // Слайдер → задаём b ТЕМ ЖЕ путём, что перетаскивание (по id, кривая могла пересоздаться).
    sl.addEventListener('input', () => {
      const cur = STATE.curves.find(x => x.id === c.id);
      if (cur && cur.linear) setCurveFreeTerm(cur, base + parseFloat(sl.value));
    });
    chip._shiftBase = base;   // от какого свободного члена считается сдвиг

    // Дорожка с кликабельными границами — как у букв-параметров: один и тот же
    // ползунок во всех сценах, а не два похожих вида.
    const track = document.createElement('div');
    track.className = 'param-track';
    track.appendChild(sl);
    chip.appendChild(track);
    /* Точное значение вводится щелчком по строке «D = 100», её ставит
       upgradeRegulator ниже. Собственный обработчик на числе справа был
       недостижим: тот же upgradeRegulator это число и прячет. */
    box.appendChild(chip);
    upgradeRegulator(chip);
  });
}

// Обновить ТОЛЬКО значения существующих чипов (после перетаскивания/redraw) — без пересборки.
// Слайдер, который пользователь держит прямо сейчас, не трогаем (чтобы не спорить с рукой).
function syncPultCurveValues(list) {
  const box = document.getElementById('params-curves');
  if (!box) return;
  list.forEach(c => {
    const chip = box.querySelector('.pchip[data-cid="' + c.id + '"]');
    if (!chip) return;
    const sl = chip.querySelector('input[type="range"]');
    const val = chip.querySelector('.pchip-val');
    /* Ползунок несёт СДВИГ, поэтому синхронизируем разницу с базой, а не сам
       свободный член: иначе протяжка кривой мышью ставила бы в ползунок 85,22
       при размахе −50…50 и ручка улетала бы за край. */
    const base = (chip._shiftBase == null) ? c.linear.b : chip._shiftBase;
    const shift = c.linear.b - base;
    if (sl && document.activeElement !== sl) sl.value = shift;   // точное, см. п. 3
    if (val) val.textContent = fmt(shift);
    /* Видимая строка «Сдвиг D = …» это .reg-eq, её пишет upgradeRegulator;
       .pchip-val он же прячет. Значит после синхронизации значения надо
       позвать его же обновление, иначе число в строке останется прежним. */
    if (chip._regSync) chip._regSync();
  });
}

/* --- «Дом» переносимых регуляторов: исходный родитель + стабильный якорь ----
   Запоминаем ОДИН раз (до первого переноса), чтобы вернуть узел точно на место в
   любой секции, а не только в #sec-tax. Якорь — ближайший следующий НЕ-переносимый
   элемент (он не двигается), иначе append в конец. */
function capturePultHome(id) {
  const n = document.getElementById(id);
  if (!n || n._pultHome) return;
  let a = n.nextSibling;
  while (a && (a.nodeType !== 1 || (a.id && PULT_MOVABLE_SET.has(a.id)))) a = a.nextSibling;
  n._pultHome = { parent: n.parentElement, anchor: a };
}
function capturePultHomes() {
  if (capturePultHomes._done) return;
  PULT_MOVABLE.forEach(capturePultHome);
  capturePultHomes._done = true;
}
function returnPultHome(id) {
  const n = document.getElementById(id);
  if (!n || !n._pultHome) return;
  const { parent, anchor } = n._pultHome;
  if (!parent || n.parentElement === parent) return;
  if (anchor && anchor.parentElement === parent) parent.insertBefore(n, anchor);
  else parent.appendChild(n);
}

// Перенести активные регуляторы в пульт (после контейнеров чипов/сцен-слайдеров),
// лишние — домой. Узлы те же — appendChild/insertBefore, не клон. В ленте регулятор
// всегда видим (он здесь, потому что активен) — снимаем возможный inline display:none.
function syncPultRegulators(activeIds) {
  capturePultHomes();
  const body = document.getElementById('params-body');
  activeIds.forEach(id => {
    const n = document.getElementById(id);
    if (!n || !body) return;
    if (n.parentElement !== body) body.appendChild(n);
    n.style.display = '';
    upgradeRegulator(n);
  });
  PULT_MOVABLE.forEach(id => { if (!activeIds.includes(id)) returnPultHome(id); });
}

/* Регулятор сцены (ставка, регулируемая цена, зарплата, мировая цена) в том же
   виде, что и ползунок буквы-параметра: по краям дорожки написаны границы, щелчок
   по границе раскрывает «мин ≤ … ≤ макс» с шагом. Разметка у регуляторов своя и
   у каждого разная, поэтому не переписываем её, а достраиваем: границы читаются
   и пишутся прямо в атрибуты min/max/step ползунка, то есть остаются ровно тем,
   чем и были. Сама сцена об этом ничего не знает. */
function upgradeRegulator(field) {
  if (!field || field._regUpgraded) return;
  const sl = field.querySelector('input[type=range]');
  if (!sl) return;
  field._regUpgraded = true;
  const num = field.querySelector('input[type=number]');

  /* Н74. Дорожке нужна СВОЯ строка. У регуляторов сцен ползунок лежит прямо в
     поле, и раньше классом .param-track помечалось само поле; но поле в правой
     панели выстроено колонкой (#params-body .field), и колонка побеждала — имя,
     левая граница, ползунок и правая граница вставали друг под другом и по
     центру. Заводим отдельную дорожку и переносим ползунок в неё: тогда строк
     ровно две, а границы стоят по краям ползунка. */
  let track = sl.parentElement;
  if (!track.classList.contains('param-track') || track === field) {
    const own = document.createElement('div');
    own.className = 'param-track';
    sl.parentElement.insertBefore(own, sl);
    own.appendChild(sl);
    track = own;
  }
  field.classList.remove('param-track');   // поле дорожкой больше не притворяется
  const lo = document.createElement('button');
  lo.type = 'button'; lo.className = 'param-bound'; lo.setAttribute('data-tip', 'Границы и шаг');
  const hi = document.createElement('button');
  hi.type = 'button'; hi.className = 'param-bound'; hi.setAttribute('data-tip', 'Границы и шаг');
  track.insertBefore(lo, sl);
  track.insertBefore(hi, sl.nextSibling);

  const editor = document.createElement('div');
  editor.className = 'param-editor';
  field.appendChild(editor);

  /* Имя регулятора для строки «имя = значение». Длинные подписи сокращаем по
     реестру (Н8): «Мировая цена Px/Py» в колонке 268px не помещается, а смысл
     несёт короткое обозначение. Полное название остаётся подсказкой. */
  const labEl = field.querySelector('label');
  const chipLab = field.querySelector('.pchip-label');
  // У регуляторов сцен подпись это <label>, у чипов кривых — .pchip-label.
  const rawName = ((labEl ? labEl.textContent : (chipLab ? chipLab.textContent : ''))
                    .split('=')[0]).replace(/[:\s]+$/, '').trim();
  const name = shortRegulatorName(field.id, rawName);

  /* Значение показываем строкой «имя = значение», как у буквы-параметра, а не
     подписью слева и числом справа. Собственную подпись поля прячем, иначе имя
     стояло бы дважды. */
  let eq = field.querySelector('.reg-eq');
  if (!eq) {
    eq = document.createElement('span');
    eq.className = 'pchip-label reg-eq pchip-editable';
    eq.title = rawName ? (rawName + '. Щёлкните, чтобы ввести точное значение') : 'Щёлкните, чтобы ввести точное значение';
    /* Куда встать: у чипа есть верхняя строка, у поля сцены её нет. Дорожка
       ползунка может лежать глубже, поэтому вставляем в САМОЕ НАЧАЛО поля, а не
       перед дорожкой: она не всегда прямой потомок, и insertBefore на чужом
       родителе падает. */
    const top = field.querySelector('.pchip-top');
    if (top) {
      const old = top.querySelector('.pchip-label');
      if (old) old.remove();
      /* А36. Цветная точка стоит ПЕРЕД именем, как в списке кривых. Раньше
         строка «имя = значение» вставлялась в самое начало, точка оказывалась
         между именем и числом («D = 100 ●») и читалась как часть числа. */
      const dot = top.querySelector('.pchip-dot');
      if (dot) top.insertBefore(eq, dot.nextSibling);
      else top.insertBefore(eq, top.firstChild);
    } else field.insertBefore(eq, field.firstChild);
    if (labEl) labEl.classList.add('reg-label-hidden');
    const oldVal = field.querySelector('.pchip-val');
    if (oldVal) oldVal.style.display = 'none';
    // Своё числовое поле сцены теперь дублирует строку «t = 20» — прячем, но
    // держим в разметке: сцена пишет в него значение, и слушатели живы.
    if (num) num.classList.add('reg-num-hidden');
  }

  const paint = () => paintEqLabel(eq, name, +sl.value);
  const sync = () => { lo.textContent = fmt(+sl.min); hi.textContent = fmt(+sl.max); paint(); };
  sync();
  /* Границы сцена двигает атрибутами, и наблюдатель их ловит. А вот САМО
     значение сцена присваивает свойством (`sl.value = …` в setTax, в сбросе
     сцены, в syncPultCurveValues): ни события, ни изменения атрибута при этом
     нет, поэтому наблюдателем такое не поймать, и строка «t = 20» показывала
     то, что было при сборке чипа. Держим строку в согласии со значением из
     общего прохода refreshRegulators(), он идёт после каждой перерисовки. */
  new MutationObserver(sync).observe(sl, { attributes: true, attributeFilter: ['min', 'max', 'step'] });
  field._regSync = sync;
  UPGRADED_REGULATORS.add(field);
  sl.addEventListener('input', () => {
    paint();
    // Правку границ ведут прямо в этом меню, и наш же clamp дёргает «input».
    // Закрыть меню сейчас значило бы снести поле из-под пальцев (см. _busy).
    if (editor._close && !editor._busy) editor._close();
  });

  eq.addEventListener('click', () => {
    if (editor._close) editor._close();          // Н10: точное значение закрывает интервал
    editEqValue(eq, name, +sl.value, (v) => {
      // Случай первый: значение за полосой — полоса переезжает, значение в центре.
      if (v < +sl.min || v > +sl.max) {
        const b = centerBandOn({ min: +sl.min, max: +sl.max }, v);
        sl.min = b.min; sl.max = b.max;
      }
      sl.value = v;
      sl.dispatchEvent(new Event('input', { bubbles: true }));
      sync();
    });
  });

  const { open } = attachBoundsEditor(field, editor, name,
    (key) => sl[key],
    (key, v) => {
      sl[key] = v;
      if (+sl.max <= +sl.min) sl.max = +sl.min + 1;
      if (num) { if (key === 'min') num.min = sl.min; if (key === 'max') num.max = sl.max; if (key === 'step') num.step = sl.step; }
      const cur = Math.max(+sl.min, Math.min(+sl.max, +sl.value));
      if (+sl.value !== cur) { sl.value = cur; sl.dispatchEvent(new Event('input', { bubbles: true })); }
      sync();
    });
  lo.addEventListener('click', () => open('min'));
  hi.addEventListener('click', () => open('max'));
}

/* Короткие обозначения длинных регуляторов (Н8). Полное название остаётся в
   подсказке; в колонке 268px помещается только обозначение. */
const REGULATOR_SHORT = {
  'ppft-price-field': 'Pw', 'tb-price-field': 'Pw', 'open-pw-field': 'Pw',
  'tax-field': 't', 'pc-field': 'Preg', 'union-wage-field': 'Wu',
  'labmin-field': 'Wmin', 'ineq-alpha-field': 'alpha',
};
function shortRegulatorName(id, raw) {
  if (REGULATOR_SHORT[id]) return REGULATOR_SHORT[id];
  const s = String(raw || '').trim();
  if (!s) return 'Значение';
  // «Ставка налога t» и подобное: если в конце стоит обозначение, берём его.
  const tail = s.match(/([A-Za-z][A-Za-z0-9]{0,3})$/);
  if (tail && s.length > 12) return tail[1];
  return s.length > 12 ? s.slice(0, 11) + '…' : s;
}

/* --- Сцен-слайдеры (#pult-extra): КПВ «Макс X/Y» и мастер «Сила неравенства».
   Генерируются как чипы; задают реальное состояние ТЕМ ЖЕ путём, что ручной ввод. */

// Линейная КПВ из перехватов: Y = maxY − (maxY/maxX)·X (переменная X, как требует compilePpf).
function ppfLinearFormula(maxX, maxY) {
  maxX = Math.max(1, maxX); maxY = Math.max(0, maxY);
  const slope = Math.round((maxY / maxX) * 1000) / 1000;
  return fmt(Math.round(maxY * 100) / 100) + ' - ' + slope + '*X';
}
// Перехваты {maxX,maxY} произвольной формулы КПВ (через существующие хелперы движка).
function ppfInterceptsOf(formulaStr) {
  const r = compilePpf(formulaStr);
  if (!r.compiled) return { maxX: CONFIG.Qmax, maxY: CONFIG.Pmax };
  const f = (x) => ppfEvalWith(r.compiled, x);
  const my = f(0), mx = ppfXmaxOf(f);
  return { maxX: (mx != null && mx > 0) ? mx : CONFIG.Qmax, maxY: (my > 0) ? my : CONFIG.Pmax };
}
// Задать одиночную КПВ по перехватам — ТОТ ЖЕ путь, что ручной ввод формулы (applyPpf).
function ppfSetSingle(maxX, maxY) {
  const formula = ppfLinearFormula(maxX, maxY);
  const inp = document.getElementById('inp-ppf'); if (inp) inp.value = formula;
  STATE.ppfFormula = formula;
  _wantRangeAnim = true;   // смена формы → плавный переезд осей (с дебаунсом)
  redrawAll();
}
// Задать КПВ страны (1/2) в режиме суммы — ТОТ ЖЕ путь, что applyPpfSum.
function ppfSetSum(which, maxX, maxY) {
  const formula = ppfLinearFormula(maxX, maxY);
  /* Долг-2. Здесь стояли id «inp-ppf1»/«inp-ppf2», которых в разметке нет:
     строки стран собираются на лету и называются «inp-ppfsum-N». Ползунки
     «Макс X/Y» меняли состояние и график, а формула в поле оставалась прежней,
     и человек видел одно, а считалось другое. Пишем и в состояние, и в поле
     тем же путём, что ручной ввод. */
  const inp = document.getElementById('inp-ppfsum-' + (which - 1));
  if (inp) inp.value = formula;
  if (typeof ppfSumSet === 'function') ppfSumSet(which - 1, formula);
  if (which === 1) STATE.ppf1 = formula; else STATE.ppf2 = formula;
  STATE.ppfSumData = null;   // форс пересчёт суммы (как applyPpfSum)
  _wantRangeAnim = true;     // смена формы страны → плавный переезд осей (с дебаунсом)
  redrawAll();
}

// Один сцен-слайдер (метка + число сверху, range снизу). onInput(value) применяет состояние.
function addPultXChip(box, label, value, color, min, max, step, onInput, idAttr) {
  const { chip, val } = makePchip(label, fmt(value), null);
  const sl = document.createElement('input');
  sl.type = 'range'; sl.min = min; sl.max = max; sl.step = step;
  sl.value = Math.round(value); sl.style.accentColor = color || cssVar('--accent');
  if (idAttr) { sl.id = idAttr; val.id = idAttr + '-val'; }
  sl.addEventListener('input', () => { const v = parseFloat(sl.value); val.textContent = fmt(v); onInput(v); });
  chip.appendChild(sl); box.appendChild(chip);
}

// Пересобрать сцен-слайдеры под текущую сцену.
function buildPultExtra(sig) {
  const box = document.getElementById('params-extra'); if (!box) return;
  box.innerHTML = '';
  /* Две разные вещи, поэтому и две группы: сверху регуляторы самой модели
     (ставка, мировая цена, границы КПВ), ниже буквы, которые пользователь
     завёл своей формулой. В общий список их мешать нельзя. */
  const names = Object.keys(STATE.params || {}).sort();
  const addTitle = (text) => {
    const t = document.createElement('div');
    t.className = 'params-group-title'; t.textContent = text;
    box.appendChild(t);
  };
  const hasModel = /^(ppf1|ppf2|ineqM)$/.test(String(sig).split('|par:')[0]);
  if (names.length) {
    if (hasModel) addTitle('Буквы из формул');
    names.forEach(n => buildParamChip(box, n));
    if (hasModel) addTitle('Параметры модели');
  }
  sig = String(sig).split('|par:')[0];
  // В блоке КПВ ползунков модели нет: форму границы задаёт само уравнение,
  // а «Макс X / Макс Y» для дуги или неявной кривой ничего осмысленного не
  // двигали — было непонятно, что именно они меняют (Фаза 11.3).
  if (sig === 'ineqM') {                                  // неравенство: мастер «Сила неравенства»
    buildIneqMasterChip(box);
  }
}

/* --- Мастер «Сила неравенства» (способы «Доли» / «Доходы») -----------------
   s = ползунок/100. Эффективное значение группы i = mean + s·(base_i − mean):
   s=0 — полное равенство (Джини→0), 100% — базовый профиль, >100% — усиление.
   Меняем ТОЛЬКО входные доли/доходы — Джини/Лоренца считает существующий движок
   (тот же путь, что ручной ввод полей). Ручная правка поля/узла Лоренца → «отвязка». */
function ineqParseIncomes(str) {
  return String(str || '').split(/[\s,;]+/).map(Number).filter(v => isFinite(v));
}
function ineqMasterRebase() {        // запомнить текущий профиль как базу (отсчёт 100%)
  STATE.ineqMasterBase = (STATE.ineqInput === 'incomes')
    ? ineqParseIncomes(STATE.ineqIncomes)
    : STATE.ineqGroups.map(Number);
}
function ineqMasterScale(s) {         // применить масштаб s → задать доли/доходы как ручной ввод
  const base = STATE.ineqMasterBase; if (!base || !base.length) return;
  const n = base.length;
  if (STATE.ineqInput === 'incomes') {
    const mean = base.reduce((a, b) => a + b, 0) / n;
    const eff = base.map(v => Math.max(0, mean + s * (v - mean)));
    STATE.ineqIncomes = eff.map(v => fmt(v)).join(', ');
    const inc = document.getElementById('ineq-incomes'); if (inc) inc.value = STATE.ineqIncomes;
  } else {
    const mean = 100 / n;                            // равное распределение долей
    let eff = base.map(v => Math.max(0, mean + s * (v - mean)));
    const sum = eff.reduce((a, b) => a + b, 0) || 1;
    eff = eff.map(v => v / sum * 100);               // ренормировка к 100 %
    STATE.ineqGroups = eff;
    renderIneqGroupsTable();
  }
  redrawAll();
}
function ineqMasterApply(sliderVal) { // движение мастера (отвязан → сперва перебазируемся)
  // Живой readout % — сразу (это сам регулятор). Тяжёлый пересчёт (доли + таблица +
  // перерисовка + Джини/Робин Гуд) — троттлом, чтобы числа и кривая обновлялись
  // СОГЛАСОВАННО и без мигания при живом кручении (Фаза 5).
  const val = document.getElementById('ineq-master-slider-val'); if (val) val.textContent = Math.round(sliderVal) + '%';
  _ineqThrottle(() => {
    const s = sliderVal / 100;
    if (STATE.ineqMasterDetached || !STATE.ineqMasterBase) { ineqMasterRebase(); STATE.ineqMasterDetached = false; }
    STATE.ineqMasterS = s;
    ineqMasterScale(s);   // доли/доходы + таблица + redrawAll (внутри троттла)
  });
}
function ineqMasterDetach() {         // ручная правка профиля → одним числом не выразить
  STATE.ineqMasterDetached = true;
  const sl = document.getElementById('ineq-master-slider'); if (sl) sl.value = 100;
  const val = document.getElementById('ineq-master-slider-val'); if (val) val.textContent = 'Своё';
}
function buildIneqMasterChip(box) {
  const detached = !!STATE.ineqMasterDetached;
  const pct = detached ? 100 : Math.round((STATE.ineqMasterS != null ? STATE.ineqMasterS : 1) * 100);
  addPultXChip(box, 'Сила неравенства', pct, COL.D, 0, 200, 1, v => ineqMasterApply(v), 'ineq-master-slider');
  const val = document.getElementById('ineq-master-slider-val');
  if (val) val.textContent = detached ? 'Своё' : (pct + '%');
}

function showPult(on) {
  const panel = document.getElementById('params-panel');
  if (!panel) return;
  const empty = document.getElementById('params-empty');
  if (!on) {
    syncPultRegulators([]);   // все узлы — домой
    const cc = document.getElementById('params-curves'); if (cc) cc.innerHTML = '';
    const ce = document.getElementById('params-extra'); if (ce) ce.innerHTML = '';
    panel._curveSig = PULT_REBUILD; panel._extraSig = PULT_REBUILD;
  }
  if (empty) empty.style.display = on ? 'none' : '';
}

// Единая точка пересмотра содержимого «Основных параметров» — дёргается из
// renderCurveList (кривые) и из set-функций режима/сцены/типа.
/* ⚠️ ПРИЗНАК «ПЕРЕСОБРАТЬ» НЕ ИМЕЕТ ПРАВА СОВПАДАТЬ С НАСТОЯЩЕЙ ПОДПИСЬЮ.

   Правая панель пересобирается, когда подпись её содержимого изменилась.
   «Заставить пересобраться» записывали пустой строкой — но пустая строка это
   ЗАКОННАЯ подпись сцены, у которой своих ползунков нет. У такой
   сцены приказ пересобраться читался как «ничего не изменилось», и чип
   прежней модели оставался на экране: ровно та утечка параметра между
   моделями, которую нашёл владелец.

   Сентинел не равен ни одной настоящей подписи, потому что все они строки. */
const PULT_REBUILD = null;

function updatePult() {
  const panel = document.getElementById('params-panel');
  if (!panel) return;
  if (!pultShouldShow()) { showPult(false); return; }

  // (1) слайдеры кривых: пересборка только при изменении набора, иначе синхронизация значений.
  const curves = pultCurveList();
  const csig = pultCurveSig(curves);
  if (panel._curveSig !== csig) { buildPultCurveChips(curves); panel._curveSig = csig; }
  else { syncPultCurveValues(curves); }

  // (2) сцен-слайдеры: пересборка только при смене сцены/под-режима.
  const esig = pultExtraSig();
  if (panel._extraSig !== esig) { buildPultExtra(esig); panel._extraSig = esig; }

  // (3) экранные регуляторы сцены → в панель (после контейнеров).
  syncPultRegulators(pultRegulatorIds());
  showPult(true);
}

function wireControls() {
  // Окно выбора сценария: клик по карточке → соответствующий пресет движка.
  const picker = document.getElementById('scene-picker');
  if (picker) picker.addEventListener('click', (e) => {
    const card = e.target.closest('.scard');
    if (card && card.dataset.scene) pickScene(card.dataset.scene);
  });
  // Клавиатура в окне выбора: Escape закрывает, Tab «закольцован» по карточкам.
  document.addEventListener('keydown', (e) => {
    const p = document.getElementById('scene-picker');
    if (!p || p.classList.contains('hidden')) return;
    if (e.key === 'Escape') { e.preventDefault(); closePicker(); return; }
    if (e.key === 'Tab') {
      // Карточки «скоро» отключены (disabled) и в кольцо фокуса не входят.
      const cards = p.querySelectorAll('.scard:not([disabled])');
      if (!cards.length) return;
      const first = cards[0], last = cards[cards.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  const addBtn = document.getElementById('btn-add-curve');

  // Границы осей, сетка, легенда и названия осей живут в меню гаечного ключа
  // (см. wireWrench). После ручной правки верхней границы цены пределы ползунков
  // ставки и регулируемой цены обязаны догнать новый масштаб.
  const pmaxField = document.getElementById('inp-pmax');
  if (pmaxField) pmaxField.addEventListener('change', () => {
    const v = parseFloat(pmaxField.value);
    if (!(v > 0)) return;
    ['tax-slider', 'tax-input', 'pc-slider', 'pc-input'].forEach(id => {
      const e = document.getElementById(id); if (e) e.max = v;
    });
    const pl = document.getElementById('params-panel'); if (pl) pl._curveSig = PULT_REBUILD;   // форсируем пересборку
    if (typeof updatePult === 'function') updatePult();   // слайдеры кривых: новый предел = Pmax
  });

  // Фаза 1а: подсказки формата формулы у полей ввода. Поля новой кривой здесь
  // больше нет — справка живёт у полей самих кривых (equipFormulaField).
  attachFormulaHelp('fh-tc', 'fp-tc', 'inp-tc', 'TC');
  attachFormulaHelp('fh-ppf', 'fp-ppf', 'inp-ppf', 'PPF');
  // Остальные формульные поля сцен: обвязку им достраиваем на месте, дальше
  // работает та же механика (LaTeX-ввод, клавиатура, примеры, кусочные).
  equipAllFormulaFields();
  attachFormulaHelp('fh-mathf', 'fp-mathf', 'inp-mathf', 'MATHF');
  attachFormulaHelp('fh-mathfc', 'fp-mathfc', 'inp-mathfc', 'MATHAB');
  attachFormulaHelp('fh-mathgc', 'fp-mathgc', 'inp-mathgc', 'MATHAB');

  /* Показ излишков — один тумблер в меню гаечного ключа (решение владельца
     22.08). Раньше это были две галочки (CS и PS) в карточке «Излишки» левой
     панели; сама карточка убрана. Оба признака состояния (showCS и showPS)
     остались — их читают заливки в четырёх местах 40-scenes-market.js, — но
     переключаются вместе: порознь их не включал никто, а излишки монополии
     живут на своих галочках #chk-mono-* и сюда не относятся. */
  const areasChk = document.getElementById('chk-areas');
  if (areasChk) areasChk.addEventListener('change', () => {
    STATE.showCS = areasChk.checked; STATE.showPS = areasChk.checked;
    redrawAll();
  });

  // Галочки областей монополии (Задача 1): CS / VC / PS.
  [['chk-mono-cs', 'showMonoCS'], ['chk-mono-vc', 'showMonoVC'], ['chk-mono-ps', 'showMonoPS']]
    .forEach(([id, key]) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', () => { STATE[key] = el.checked; redrawAll(); });
    });

  // Галочка «было → стало» (бледное исходное состояние при вмешательстве).
  const ghost = document.getElementById('chk-ghost');
  if (ghost) ghost.addEventListener('change', () => { STATE.showGhost = ghost.checked; redrawAll(); });

  // Ползунок ставки (синхронизирован с перетаскиванием клина через setTax).
  const taxSlider = document.getElementById('tax-slider');
  taxSlider.addEventListener('input', () => setTax(parseFloat(taxSlider.value)));

  // Числовое поле ставки: принимает дробные значения (0.1), точнее ползунка.
  const taxInput = document.getElementById('tax-input');
  if (taxInput) {
    taxInput.addEventListener('change', () => {
      const v = parseFloat(taxInput.value);
      if (!isNaN(v)) setTax(v);
    });
  }

  // Переключатель «Налог / Субсидия / Потолок / Пол».
  document.getElementById('seg-tax').addEventListener('click', () => setType('tax'));
  document.getElementById('seg-sub').addEventListener('click', () => setType('subsidy'));
  document.getElementById('seg-ceil').addEventListener('click', () => setType('ceiling'));
  document.getElementById('seg-floor').addEventListener('click', () => setType('floor'));
  const segQuota = document.getElementById('seg-quota');
  if (segQuota) segQuota.addEventListener('click', () => setType('quota'));
  // Квота: объём и выбор цены внутри коридора.
  const qSl = document.getElementById('quota-slider'), qIn = document.getElementById('quota-input');
  if (qSl) qSl.addEventListener('input', () => setQuota(parseFloat(qSl.value)));
  if (qIn) qIn.addEventListener('change', () => { const v = parseFloat(qIn.value); if (!isNaN(v)) setQuota(v); });
  const qP = document.getElementById('quota-price-slider');
  if (qP) qP.addEventListener('input', () => setQuotaPos(parseFloat(qP.value) / 100));

  // Сторона налога (Задача 1): продавец / покупатель.
  const tsbSel = document.getElementById('tsb-seller'), tsbBuy = document.getElementById('tsb-buyer');
  if (tsbSel) tsbSel.addEventListener('click', () => setTaxSide('seller'));
  if (tsbBuy) tsbBuy.addEventListener('click', () => setTaxSide('buyer'));

  // Переключатель рынка «Конкуренция / Монополия».
  const segComp = document.getElementById('seg-comp');
  const segMono = document.getElementById('seg-mono');
  if (segComp) segComp.addEventListener('click', () => setMarket('comp'));
  if (segMono) segMono.addEventListener('click', () => setMarket('monopoly'));

  // Под-режимы монополии: обычная / дискр. 1° / дискр. 3° / составной спрос / естественная.
  [['mm-simple', 'simple'], ['mm-d1', 'discr1'], ['mm-d3', 'discr3'],
   ['mm-kink', 'kinked'], ['mm-nat', 'natural']]
    .forEach(([id, mm]) => { const b = document.getElementById(id); if (b) b.addEventListener('click', () => setMonoMode(mm)); });

  // Естественная монополия (Фаза 3в): постоянные издержки FC + галочки заливок.
  const natFC = document.getElementById('inp-nat-fc');
  if (natFC) {
    const applyFC = () => { const v = parseFloat(natFC.value); if (!isNaN(v) && v >= 0) { STATE.natFC = v; redrawAll(); } };
    natFC.addEventListener('change', applyFC);
    natFC.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyFC(); });
  }
  [['chk-nat-profit', 'showNatProfit'], ['chk-nat-loss', 'showNatLoss']].forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => { STATE[key] = el.checked; redrawAll(); });
  });

  // Дискриминация 3-й степени (Задача 5): два спроса + общий MC, кнопка «Построить».
  const d3a = document.getElementById('inp-d3-1'), d3b = document.getElementById('inp-d3-2'), d3m = document.getElementById('inp-d3-mc');
  function applyD3() {
    if (d3a) STATE.d3D1 = d3a.value; if (d3b) STATE.d3D2 = d3b.value; if (d3m) STATE.d3MC = d3m.value;
    redrawAll();
  }
  const d3btn = document.getElementById('btn-d3-apply');
  if (d3btn) d3btn.addEventListener('click', applyD3);
  [d3a, d3b, d3m].forEach(el => { if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') applyD3(); }); });

  // Ломаный спрос (Задача 6): переключатель ввода + поля + кнопка «Построить».
  const kiI = document.getElementById('ki-indiv'), kiP = document.getElementById('ki-piece');
  if (kiI) kiI.addEventListener('click', () => setKinkInput('individual'));
  if (kiP) kiP.addEventListener('click', () => setKinkInput('piecewise'));
  const ki1 = document.getElementById('inp-ki-1'), ki2 = document.getElementById('inp-ki-2'), ki3 = document.getElementById('inp-ki-3');
  const kp1 = document.getElementById('inp-kp-1'), kp2 = document.getElementById('inp-kp-2'), kmc = document.getElementById('inp-kink-mc');
  function applyKink() {
    if (ki1) STATE.kiD1 = ki1.value; if (ki2) STATE.kiD2 = ki2.value; if (ki3) STATE.kiD3 = ki3.value;
    if (kp1) STATE.kpD1 = kp1.value; if (kp2) STATE.kpD2 = kp2.value; if (kmc) STATE.kinkMC = kmc.value;
    redrawAll();
  }
  const kbtn = document.getElementById('btn-kink-apply');
  if (kbtn) kbtn.addEventListener('click', applyKink);
  [ki1, ki2, ki3, kp1, kp2, kmc].forEach(el => { if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') applyKink(); }); });

  // Потолок/пол цены в монополии (Фаза 2) задаются ОБЩИМ блоком «Вмешательство»
  // (сегменты «Потолок»/«Пол» + ползунок pc-slider → setPReg), отдельной галочки больше нет.

  // Режим выбирается карточкой в окне сценариев; кнопок режима в панели больше нет.

  // Теория потребителя (Фаза 8): цены, доход, тип предпочтений, параметры, Слуцкий.
  [['cons-px', 'consPx'], ['cons-py', 'consPy'], ['cons-i', 'consI'],
   ['cons-a', 'consA'], ['cons-b', 'consB'], ['cons-k', 'consK']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('change', () => {
      const v = parseFloat(e.value);
      if (isNaN(v)) return;
      STATE[key] = v; _wantRangeAnim = true; redrawAll();
    });
  });
  const consType = document.getElementById('cons-type');
  if (consType) consType.addEventListener('change', () => setConsumerType(consType.value));
  const consCustom = document.getElementById('cons-custom');
  if (consCustom) {
    const applyU = () => { STATE.consCustom = (consCustom.value || '').trim(); redrawAll(); };
    consCustom.addEventListener('change', applyU);
    consCustom.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyU(); });
  }
  attachFormulaHelp('fh-cons', 'fp-cons', 'cons-custom', 'UTIL');
  const consFan = document.getElementById('chk-cons-fan');
  if (consFan) consFan.addEventListener('change', () => { STATE.consFan = consFan.checked; redrawAll(); });
  const consSl = document.getElementById('chk-cons-slutsky');
  if (consSl) consSl.addEventListener('change', () => setConsSlutsky(consSl.checked));
  const px1S = document.getElementById('cons-px1-slider'), px1I = document.getElementById('cons-px1-input');
  const applyPx1 = (v) => {
    if (isNaN(v) || v <= 0) return;
    STATE.consPx1 = v;
    if (px1S) px1S.value = v; if (px1I) px1I.value = v;
    const l = document.getElementById('cons-px1-val'); if (l) l.textContent = fmt(v);
    _wantRangeAnim = true; redrawAll();
  };
  if (px1S) px1S.addEventListener('input', () => applyPx1(parseFloat(px1S.value)));
  if (px1I) px1I.addEventListener('change', () => applyPx1(parseFloat(px1I.value)));

  // Рынок труда (Чекпоинт 1): структура, МРОТ, конкурентный ориентир.
  const labComp = document.getElementById('lab-comp'), labMono = document.getElementById('lab-mono');
  if (labComp) labComp.addEventListener('click', () => setLaborStruct('competition'));
  if (labMono) labMono.addEventListener('click', () => setLaborStruct('monopsony'));
  // Профсоюз (ЧК4): структура + под-модель + ползунок/поле зарплаты при диктате.
  const labUnion = document.getElementById('lab-union');
  if (labUnion) labUnion.addEventListener('click', () => setLaborStruct('union'));
  const labBilat = document.getElementById('lab-bilat');
  if (labBilat) labBilat.addEventListener('click', () => setLaborStruct('bilateral'));
  const unMono = document.getElementById('un-monopoly'), unWf = document.getElementById('un-wagefloor');
  if (unMono) unMono.addEventListener('click', () => setUnionModel('monopoly'));
  if (unWf) unWf.addEventListener('click', () => setUnionModel('wagefloor'));
  const unWageSlider = document.getElementById('union-wage-slider');
  if (unWageSlider) unWageSlider.addEventListener('input', () => setUnionWage(parseFloat(unWageSlider.value)));
  const unWageInput = document.getElementById('union-wage-input');
  if (unWageInput) unWageInput.addEventListener('change', () => { const v = parseFloat(unWageInput.value); if (!isNaN(v)) setUnionWage(v); });
  const labMinChk = document.getElementById('chk-labmin');
  if (labMinChk) labMinChk.addEventListener('change', () => {
    STATE.laborMinOn = labMinChk.checked;
    const f = document.getElementById('labmin-field'); if (f) f.style.display = labMinChk.checked ? '' : 'none';
    // При включении ставим линию на уровень текущей зарплаты (пока не связывает) — точка отсчёта.
    if (labMinChk.checked && !(STATE.laborMinW > 0)) {
      const base = (STATE.laborStruct === 'monopsony' && STATE.laborMono) ? STATE.laborMono.Wm
                 : (STATE.laborEq ? STATE.laborEq.P : 0);
      if (base > 0) setLaborMinFields(Math.round(base));
    }
    if (typeof updatePult === 'function') updatePult();   // ползунок МРОТ в пульт / домой
    redrawAll();
  });
  const labMinSlider = document.getElementById('labmin-slider');
  if (labMinSlider) labMinSlider.addEventListener('input', () => setLaborMin(parseFloat(labMinSlider.value)));
  const labMinInput = document.getElementById('labmin-input');
  if (labMinInput) labMinInput.addEventListener('change', () => { const v = parseFloat(labMinInput.value); if (!isNaN(v)) setLaborMin(v); });
  const labGhost = document.getElementById('chk-lab-ghost');
  if (labGhost) labGhost.addEventListener('change', () => { STATE.showGhost = labGhost.checked; redrawAll(); });

  // Сценарии анализа рынка: обычный / эластичность / сдвиги / внешний эффект / открытая экономика.
  [['scn-none', 'none'], ['scn-elast', 'elasticity'], ['scn-shift', 'shift'],
   ['scn-ext', 'externality'], ['scn-open', 'openecon']]
    .forEach(([id, s]) => { const b = document.getElementById(id); if (b) b.addEventListener('click', () => setScenario(s)); });

  // Малая открытая экономика (Фаза 4в): мировая цена, инструмент, тариф и квота.
  const opwS = document.getElementById('open-pw-slider'), opwI = document.getElementById('open-pw-input');
  if (opwS) opwS.addEventListener('input', () => setOpenPw(parseFloat(opwS.value)));
  if (opwI) opwI.addEventListener('change', () => { const v = parseFloat(opwI.value); if (!isNaN(v)) setOpenPw(v); });
  [['oi-none', 'none'], ['oi-tariff', 'tariff'], ['oi-quota', 'quota']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.addEventListener('click', () => setOpenTool(v)); });
  const setOpenNum = (key, sliderId, inputId, valId) => {
    const sl = document.getElementById(sliderId), inp = document.getElementById(inputId), lab = document.getElementById(valId);
    const apply = (v) => {
      if (isNaN(v) || v < 0) return;
      STATE[key] = v;
      if (sl) sl.value = v; if (inp) inp.value = fmtInput(v); if (lab) lab.textContent = fmt(v);
      redrawAll();
    };
    if (sl) sl.addEventListener('input', () => apply(parseFloat(sl.value)));
    if (inp) inp.addEventListener('change', () => apply(parseFloat(inp.value)));
  };
  setOpenNum('openTariff', 'open-tariff-slider', 'open-tariff-input', 'open-tariff-val');
  setOpenNum('openQuota', 'open-quota-slider', 'open-quota-input', 'open-quota-val');
  [['chk-open-money', 'showOpenMoney'], ['chk-open-dwl', 'showOpenDwl']].forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => { STATE[key] = el.checked; redrawAll(); });
  });

  // Сдвиги спроса и предложения (Задача 3): ползунки + числовые поля.
  [['shiftD-slider', 'shiftD-input', 'D'], ['shiftS-slider', 'shiftS-input', 'S']].forEach(([sid, iid, which]) => {
    const sl = document.getElementById(sid), inp = document.getElementById(iid);
    if (sl) sl.addEventListener('input', () => setShift(which, parseFloat(sl.value)));
    if (inp) inp.addEventListener('change', () => setShift(which, parseFloat(inp.value)));
  });

  // Внешний эффект (Задача 4): формула внешних издержек + галочка налога Пигу.
  const extInp = document.getElementById('ext-input');
  if (extInp) {
    const applyExt = () => { STATE.extExpr = (extInp.value || '').trim(); recompileExt(); redrawAll(); };
    extInp.addEventListener('change', applyExt);
    extInp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') applyExt(); });
  }
  const extPigou = document.getElementById('ext-pigou');
  if (extPigou) extPigou.addEventListener('change', () => { STATE.applyPigou = extPigou.checked; redrawAll(); });
  // Фаза 2б: знак внешнего эффекта (отрицательный ↔ положительный).
  const extNeg = document.getElementById('ext-neg'), extPos = document.getElementById('ext-pos');
  if (extNeg) extNeg.addEventListener('click', () => setExtSign('neg'));
  if (extPos) extPos.addEventListener('click', () => setExtSign('pos'));

  // Фаза 2а: галочка «точка на предложении» (вторая точка эластичности).
  const elS = document.getElementById('chk-elast-s');
  if (elS) elS.addEventListener('change', () => { STATE.showElastS = elS.checked; redrawAll(); });

  // Уровень 2 каскада вмешательства: вид налога (потоварный / НДС / акциз)
  // или вид субсидии (потоварная / процентная — третья кнопка тогда скрыта).
  [['tk-unit', 'unit'], ['tk-vat', 'vat'], ['tk-exc', 'excise']].forEach(([id, form]) => {
    const b = document.getElementById(id);
    if (b) b.addEventListener('click', () => setTaxForm(form));
  });

  /* Режим издержек (Задача 2). Постоянные затраты отдельным полем больше не
     вводятся (Б24): в режиме «задаю TC» они равны TC(0). Поэтому здесь только
     формула TC — либо, во втором режиме, три формулы кривых. */
  const tcInp = document.getElementById('inp-tc');
  function applyCosts() {
    const tc = ((tcInp && tcInp.value) || '').trim();
    const { error } = compileFormula(tc);
    const errBox = document.getElementById('costs-error');
    if (error) { if (errBox) { errBox.textContent = 'Не понял формулу TC: ' + error; errBox.style.display = 'block'; } return; }
    if (errBox) errBox.style.display = 'none';
    STATE.costsTC = tc;
    redrawAll();
  }
  const cApply = document.getElementById('btn-costs-apply');
  if (cApply) cApply.addEventListener('click', applyCosts);
  const cPreset = document.getElementById('btn-costs-preset');
  if (cPreset) cPreset.addEventListener('click', () => {
    if (tcInp) tcInp.value = 'Q^3 - 6*Q^2 + 15*Q + 18';
    applyCosts();
  });
  if (tcInp) tcInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyCosts(); });
  // Второй способ ввода: кривые по отдельности.
  const cmcInp = document.getElementById('inp-cmc'), catcInp = document.getElementById('inp-catc'),
        cavcInp = document.getElementById('inp-cavc');
  function applyCostParts() {
    const errBox = document.getElementById('costs-error');
    const bad = [];
    [[cmcInp, 'MC', 'costsMCx'], [catcInp, 'ATC', 'costsATCx'], [cavcInp, 'AVC', 'costsAVCx']]
      .forEach(([el, name, key]) => {
        const src = ((el && el.value) || '').trim();
        if (src && compileFormula(src).error) { bad.push(name); return; }
        STATE[key] = src;
      });
    if (errBox) {
      errBox.style.display = bad.length ? 'block' : 'none';
      errBox.textContent = bad.length ? ('Не понял формулу ' + bad.join(' и ')) : '';
    }
    redrawAll();
  }
  const cpApply = document.getElementById('btn-cparts-apply');
  if (cpApply) cpApply.addEventListener('click', applyCostParts);
  [cmcInp, catcInp, cavcInp].forEach(e => {
    if (e) e.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') applyCostParts(); });
  });
  const cmTc = document.getElementById('cm-tc'), cmCur = document.getElementById('cm-curves');
  if (cmTc) cmTc.addEventListener('click', () => setCostsInputMode('tc'));
  if (cmCur) cmCur.addEventListener('click', () => setCostsInputMode('curves'));
  [['chk-mc', 'showMC'], ['chk-atc', 'showATC'], ['chk-avc', 'showAVC'], ['chk-afc', 'showAFC'], ['chk-vc', 'showVC'], ['chk-tc', 'showTC'], ['chk-fc', 'showFC'],
   ['chk-tp', 'showTP'], ['chk-mp', 'showMP'], ['chk-ap', 'showAP'], ['chk-iso-fan', 'isoFan'], ['chk-lr-area', 'lrArea']]
    .forEach(([id, key]) => { const el = document.getElementById(id); if (el) el.addEventListener('change', () => { STATE[key] = el.checked; redrawAll(); }); });

  // Фаза 9: сюжеты режима «Фирма» (издержки / производство / изокванты).
  [['cs-costs', 'costs'], ['cs-prod', 'production'], ['cs-iso', 'isoquant'], ['cs-plants', 'plants']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.addEventListener('click', () => setCostsSub(v)); });
  // Фаза 10: два завода — формулы TC, вид графика, совокупный выпуск.
  const pl1 = document.getElementById('inp-pl1'), pl2 = document.getElementById('inp-pl2');
  const applyPl = () => { if (pl1) STATE.pl1 = (pl1.value || '').trim(); if (pl2) STATE.pl2 = (pl2.value || '').trim(); redrawAll(); };
  const plBtn = document.getElementById('btn-pl-apply');
  if (plBtn) plBtn.addEventListener('click', applyPl);
  [pl1, pl2].forEach(e => { if (e) e.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') applyPl(); }); });
  [['plv-tc', 'tc'], ['plv-mc', 'mc']].forEach(([id, v]) => {
    const b = document.getElementById(id); if (b) b.addEventListener('click', () => setPlantsView(v));
  });
  const plS = document.getElementById('pl-q-slider'), plI = document.getElementById('pl-q-input');
  if (plS) plS.addEventListener('input', () => setPlantsQ(parseFloat(plS.value)));
  if (plI) plI.addEventListener('change', () => setPlantsQ(parseFloat(plI.value)));
  // 9в: рыночная цена и прибыль.
  const lrChk = document.getElementById('chk-lr');
  if (lrChk) lrChk.addEventListener('change', () => {
    STATE.lrOn = lrChk.checked;
    const f = document.getElementById('lr-price-field'); if (f) f.style.display = lrChk.checked ? '' : 'none';
    if (typeof updatePult === 'function') updatePult();
    redrawAll();
  });
  const lrS = document.getElementById('lr-price-slider'), lrI = document.getElementById('lr-price-input');
  if (lrS) lrS.addEventListener('input', () => setLrPrice(parseFloat(lrS.value)));
  if (lrI) lrI.addEventListener('change', () => { const v = parseFloat(lrI.value); if (!isNaN(v)) setLrPrice(v); });
  // 9а: производственная функция.
  const prodInp = document.getElementById('inp-prod');
  const applyProd = () => { if (prodInp) STATE.prodExpr = (prodInp.value || '').trim(); redrawAll(); };
  const prodBtn = document.getElementById('btn-prod-apply');
  if (prodBtn) prodBtn.addEventListener('click', applyProd);
  if (prodInp) prodInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyProd(); });
  attachFormulaHelp('fh-prod', 'fp-prod', 'inp-prod', 'PROD');
  // 9б: изокванты и изокосты.
  const isoInp = document.getElementById('inp-iso');
  if (isoInp) {
    const applyIso = () => { STATE.isoExpr = (isoInp.value || '').trim(); redrawAll(); };
    isoInp.addEventListener('change', applyIso);
    isoInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyIso(); });
  }
  attachFormulaHelp('fh-iso', 'fp-iso', 'inp-iso', 'ISO');
  [['iso-w', 'isoW'], ['iso-r', 'isoR'], ['iso-c', 'isoC']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('change', () => { const v = parseFloat(e.value); if (!isNaN(v) && v > 0) { STATE[key] = v; _wantRangeAnim = true; redrawAll(); } });
  });

  // Режим КПВ: одна строка на любую форму уравнения (Фаза 11), вторая кривая
  // для сравнения, луч комплектов и области.
  const ppfInp = document.getElementById('inp-ppf');
  const ppfInp2 = document.getElementById('inp-ppf2b');
  function applyPpf() {
    const f = ((ppfInp && ppfInp.value) || '').trim();
    const r = parsePpfEquation(f);
    const errBox = document.getElementById('ppf-error');
    if (r.error) { if (errBox) { errBox.textContent = 'Не понял уравнение: ' + r.error; errBox.style.display = 'block'; } return; }
    if (errBox) errBox.style.display = 'none';
    STATE.ppfFormula = f;
    STATE.ppfFormula2 = ((ppfInp2 && ppfInp2.value) || '').trim();
    STATE.ppfX = null;
    redrawAll();
    const pl = document.getElementById('params-panel'); if (pl) pl._extraSig = PULT_REBUILD;   // пере-инициализировать
    if (typeof updatePult === 'function') updatePult();
  }
  const pApply = document.getElementById('btn-ppf-apply');
  if (pApply) pApply.addEventListener('click', applyPpf);
  if (ppfInp) ppfInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyPpf(); });
  if (ppfInp2) ppfInp2.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyPpf(); });

  // Вторая КПВ: кнопка показывает второе поле и строит обе кривые (Фаза 12.2).
  const cmp = document.getElementById('btn-ppf-compare');
  if (cmp) cmp.addEventListener('click', () => {
    STATE.ppfCompare = !STATE.ppfCompare;
    const box = document.getElementById('ppf-second');
    if (box) box.style.display = STATE.ppfCompare ? '' : 'none';
    cmp.textContent = STATE.ppfCompare ? 'Убрать вторую КПВ' : 'Сравнить с другой КПВ';
    applyPpf();
  });

  // Свои имена кривых.
  [['inp-ppf-name1', 'ppfName1'], ['inp-ppf-name2', 'ppfName2']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('input', () => { STATE[key] = e.value.trim(); redrawAll(); });
  });

  /* Н17. Кривая комплектов во ВСЕХ моделях блока «КПВ и КТВ» заводится
     одинаково: галочка (по умолчанию снята) раскрывает два пустых значения, и
     как только введены оба, луч строится САМ и перестраивается при любой
     правке. Отдельной кнопки «Построить» больше нет: она была лишним шагом
     между «ввёл» и «увидел». */
  const BUNDLE_BLOCKS = [
    ['chk-bundle-1', 'bundle-row',  'inp-bundle-x',  'inp-bundle-y'],
    ['chk-bundle-2', 'bundle-row2', 'inp-bundle-x2', 'inp-bundle-y2'],
    ['chk-bundle-t', 'bundle-rowt', 'inp-bundle-xt', 'inp-bundle-yt'],
  ];
  const bundleApply = (idX, idY) => {
    const ex = document.getElementById(idX), ey = document.getElementById(idY);
    const rawX = (ex && ex.value || '').trim(), rawY = (ey && ey.value || '').trim();
    const x = parseFloat(rawX), y = parseFloat(rawY);
    const err = document.getElementById('bundle-error');
    const bad = (rawX !== '' && !(x > 0)) || (rawY !== '' && !(y > 0));
    if (err) {
      err.textContent = bad ? 'Единиц в комплекте не может быть меньше нуля' : '';
      err.style.display = bad ? 'block' : 'none';
    }
    if (bad) { STATE.bundleOn = false; redrawAll(); return; }
    if (!(x > 0) || !(y > 0)) { STATE.bundleOn = false; redrawAll(); return; }
    STATE.bundleX = x; STATE.bundleY = y; STATE.bundleOn = true;
    redrawAll();
  };
  BUNDLE_BLOCKS.forEach(([chkId, rowId, idX, idY]) => {
    const chk = document.getElementById(chkId), row = document.getElementById(rowId);
    if (!chk || !row) return;
    chk.addEventListener('change', () => {
      row.style.display = chk.checked ? '' : 'none';
      if (!chk.checked) { STATE.bundleOn = false; redrawAll(); return; }
      bundleApply(idX, idY);
    });
    [idX, idY].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', () => bundleApply(idX, idY));
    });
  });

  // Показ областей.
  [['chk-ppf-in', 'ppfShowIn'], ['chk-ppf-out', 'ppfShowOut']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('change', () => { STATE[key] = e.checked; redrawAll(); });
  });

  // Под-режимы КПВ (Задачи 1–2): одна / сумма двух / КТВ.
  [['ppfsub-single', 'single'], ['ppfsub-sum', 'sum'], ['ppfsub-trade', 'trade']].forEach(([id, sub]) => {
    const b = document.getElementById(id); if (b) b.addEventListener('click', () => setPpfSub(sub));
  });

  // Сложение КПВ: число кривых задаётся числом, строки заводятся сами (Фаза 13).
  function applyPpfSum() {
    STATE.ppfSumData = null;   // принудительный пересчёт
    redrawAll();
    const pl = document.getElementById('params-panel'); if (pl) pl._extraSig = PULT_REBUILD;
    if (typeof updatePult === 'function') updatePult();
  }
  const sumApply = document.getElementById('btn-ppfsum-apply');
  if (sumApply) sumApply.addEventListener('click', applyPpfSum);
  const sumN = document.getElementById('inp-ppfsum-n');
  if (sumN) sumN.addEventListener('input', () => {
    STATE.ppfSumCount = Math.max(2, Math.min(5, parseInt(sumN.value, 10) || 2));
    renderPpfSumRows(); applyPpfSum();
  });
  const sumNm = document.getElementById('inp-ppfsum-name');
  if (sumNm) sumNm.addEventListener('input', () => { STATE.ppfSumName = sumNm.value.trim(); redrawAll(); });
  renderPpfSumRows();


  // КТВ — торговые возможности (Задача 2): КПВ + мировая цена Px/Py.
  const ppftInp = document.getElementById('inp-ppft'), ppftPriceInp = document.getElementById('inp-ppft-price');
  function applyPpfTrade() {
    STATE.ppftFormula = ((ppftInp && ppftInp.value) || '').trim();
    const v = parseFloat(ppftPriceInp && ppftPriceInp.value);
    STATE.ppftPrice = isNaN(v) ? 0 : v;
    redrawAll();
  }
  const tApply = document.getElementById('btn-ppft-apply');
  if (tApply) tApply.addEventListener('click', applyPpfTrade);
  if (ppftInp) ppftInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyPpfTrade(); });
  // Смена мировой цены полем — анимируем переезд осей (как и ползунком).
  if (ppftPriceInp) ppftPriceInp.addEventListener('change', () => { _wantRangeAnim = true; applyPpfTrade(); });
  // Задача 2: ползунок мировой цены Px/Py — основное управление, синхронен с полем.
  const ppftSlider = document.getElementById('ppft-price-slider');
  if (ppftSlider) ppftSlider.addEventListener('input', () => {
    const v = parseFloat(ppftSlider.value); if (isNaN(v)) return;
    STATE.ppftPrice = v;       // фактическое значение зажмётся в recomputePpfTrade
    _wantRangeAnim = true;     // смена Pw → плавный переезд осей (см. applyTradeRanges)
    redrawAll();
  });

  // ЧК5: две страны (эндогенная мировая цена). Сценарий А/Б задаёт карточка
  // сюжета через setTradeScenario, кнопок в разметке нет (Свх-4б).
  const tb1 = document.getElementById('inp-tb1'), tb2 = document.getElementById('inp-tb2');
  function applyTradeB() {
    if (tb1) STATE.tbF1 = (tb1.value || '').trim();
    if (tb2) STATE.tbF2 = (tb2.value || '').trim();
    redrawAll();
  }
  const tbApply = document.getElementById('btn-tb-apply');
  if (tbApply) tbApply.addEventListener('click', applyTradeB);
  [tb1, tb2].forEach(el => { if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') applyTradeB(); }); });
  // Задача 2: своя мировая цена — ползунок + поле + сброс к равновесной (всё синхронно).
  const tbPrice = document.getElementById('inp-tb-price');
  if (tbPrice) tbPrice.addEventListener('change', () => {
    const v = parseFloat(tbPrice.value);
    STATE.tbManualPrice = (!isNaN(v) && v > 0) ? v : null;
    _wantRangeAnim = true;     // смена Pw → плавный переезд осей
    redrawAll();
  });
  const tbSlider = document.getElementById('tb-price-slider');
  if (tbSlider) tbSlider.addEventListener('input', () => {
    const v = parseFloat(tbSlider.value); if (isNaN(v)) return;
    STATE.tbManualPrice = v;   // фактическое значение зажмётся в recomputeTradeB
    _wantRangeAnim = true;     // смена Pw → плавный переезд осей
    redrawAll();
  });
  const tbReset = document.getElementById('btn-tb-reset');
  if (tbReset) tbReset.addEventListener('click', () => {
    STATE.tbManualPrice = null;   // вернуться к равновесной; ползунок/поле обновит syncTbPriceUI
    _wantRangeAnim = true;        // равновесная Pw тоже меняет масштаб — плавно
    redrawAll();
  });

  // Готовые сцены раздаёт окно сценариев (#scene-picker) — второго списка кнопок нет.

  /* ── Раздел «Математика» (Фаза 7) ─────────────────────────────────── */
  [['ms-tangent', 'tangent'], ['ms-optimum', 'optimum'], ['ms-transform', 'transform'],
   ['ms-minmax', 'minmax'], ['ms-constraint', 'constraint']]
    .forEach(([id, sub]) => {
      const b = document.getElementById(id);
      if (b) b.addEventListener('click', () => setMathSub(sub));
    });

  // Поля формул раздела: правка сразу перерисовывает график.
  [['inp-mathf', 'mathFormula'],
   ['inp-mathfc', 'mathFC']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('input', () => { STATE[key] = e.value; redrawAll(); });
  });

  // Точка касания: ползунок, числовое поле (её же тянут мышью по кривой).
  const mx0s = document.getElementById('mathx0-slider');
  if (mx0s) mx0s.addEventListener('input', () => setMathX0(parseFloat(mx0s.value)));
  const mx0i = document.getElementById('mathx0-input');
  // Реагируем на ввод, а не только на уход из поля: число видно на графике сразу.
  if (mx0i) ['input', 'change'].forEach(ev => mx0i.addEventListener(ev, () => {
    const v = parseFloat(mx0i.value);
    if (!isNaN(v)) setMathX0(v);
  }));
  // Секущая через две точки: ползунок Δx появляется вместе с галочкой.
  const secChk = document.getElementById('chk-secant');
  if (secChk) secChk.addEventListener('change', () => {
    STATE.mathSecant = secChk.checked;
    const f = document.getElementById('mathdx-field');
    if (f) f.style.display = secChk.checked ? '' : 'none';
    redrawAll();
  });
  const dxs = document.getElementById('mathdx-slider');
  if (dxs) dxs.addEventListener('input', () => {
    STATE.mathDx = parseFloat(dxs.value);
    const v = document.getElementById('mathdx-val'); if (v) v.textContent = fmt(STATE.mathDx);
    redrawAll();
  });
  [['chk-convex', 'mathConvex'], ['chk-inflect', 'mathInflect']].forEach(([id, key]) => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('change', () => { STATE[key] = e.checked; redrawAll(); });
  });
  // Деформации: вид преобразования и его параметр.
  const trSel = document.getElementById('math-trans');
  if (trSel) trSel.addEventListener('change', () => {
    STATE.mathTrans = trSel.value;
    const h = document.getElementById('math-trans-hint');
    if (h) h.textContent = MATH_TRANS[STATE.mathTrans].note;
    redrawAll();
  });
  /* П26. Параметр деформаций ведёт общий механизм параметров (sceneExtraParams заявляет
     букву a, buildParamChip рисует ползунок). Своей обвязки у сюжета больше нет. */
  const mcMax = document.getElementById('mc-max'), mcMin = document.getElementById('mc-min');
  const setWantMax = (v) => {
    STATE.mathConsWantMax = v;
    if (mcMax) mcMax.classList.toggle('active', v);
    if (mcMin) mcMin.classList.toggle('active', !v);
    redrawAll();
  };
  if (mcMax) mcMax.addEventListener('click', () => setWantMax(true));
  if (mcMin) mcMin.addEventListener('click', () => setWantMax(false));
  // Ограничение сменилось — окно подгоняется заново, дальше им распоряжается человек.
  const gcField = document.getElementById('inp-mathgc');
  if (gcField) gcField.addEventListener('input', () => {
    STATE.mathGC = gcField.value;
    constraintFit();
    redrawAll();
  });

  const mmMin = document.getElementById('mm-min'), mmMax = document.getElementById('mm-max');
  if (mmMin) mmMin.addEventListener('click', () => {
    STATE.mathMinMax = 'min'; mmMin.classList.add('active'); mmMax.classList.remove('active'); redrawAll();
  });
  if (mmMax) mmMax.addEventListener('click', () => {
    STATE.mathMinMax = 'max'; mmMax.classList.add('active'); mmMin.classList.remove('active'); redrawAll();
  });
  // Сколько функций участвует: любое число, не только две.
  const mmCnt = document.getElementById('mm-count');
  if (mmCnt) mmCnt.addEventListener('input', () => {
    const n = parseInt(mmCnt.value, 10);
    if (!isFinite(n) || n < 2 || n > 8) return;
    STATE.mmCount = n;
    renderMmRows();
    redrawAll();
  });
  // Имя результата: Z по умолчанию, но можно назвать по-своему.
  const mmName = document.getElementById('mm-name');
  if (mmName) mmName.addEventListener('input', () => { STATE.mmName = mmName.value; redrawAll(); });
  { const h = document.getElementById('math-trans-hint');
    if (h) h.textContent = MATH_TRANS[STATE.mathTrans].note; }

  // Оформление (Фаза 1): заголовок графика и свои названия осей.
  const gTitle = document.getElementById('inp-gtitle');
  if (gTitle) gTitle.addEventListener('input', () => { STATE.graphTitle = gTitle.value; redrawAll(); });
  const xName = document.getElementById('inp-xname');
  if (xName) xName.addEventListener('input', () => { STATE.axisXName = xName.value; redrawAll(); });
  const yName = document.getElementById('inp-yname');
  if (yName) yName.addEventListener('input', () => { STATE.axisYName = yName.value; redrawAll(); });

  /* Своя точка (П28): режим взводит тумблер «Указать на графике» в самой
     строке заготовки, отдельной кнопки над списком больше нет. */
  const chartEl = document.getElementById('chart');
  if (chartEl) chartEl.addEventListener('click', (ev) => {
    if (!STATE.markArm) return;
    const { mx, my } = mainScales();
    const [px, py] = d3.pointer(ev, chartEl);
    const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
    armMark(false);
    showSnapHint(null);
    /* Рядом с кривой точка садится НА неё, в пустом месте остаётся где щёлкнули.
       Магнит тот же, что у вершин площади (Н41, Н54): в ключевую точку попасть
       должно быть заметно легче, чем мимо, и правило это одно на все три случая
       (своя точка, вершина площади, перетаскивание готовой). */
    const hit = snapVertexAt(px, py);
    const x = hit ? hit.x : mx.invert(px);
    const y = hit ? hit.y : my.invert(py);
    if (x < xLo || x > xHi || y < yLo || y > yHi) return;   // щелчок мимо поля
    // К пересечению и к особой точке не привязываем: скольжение по одной из
    // кривых увело бы точку из перекрестья, а смысл отметки именно в нём.
    addMarkAt(x, y, (hit && !hit.cross && !hit.key) ? hit.name : null);
  });
  // Набор вершин площади: щелчок ставит вершину и режим не снимается —
  // вершин надо хотя бы три, и каждый раз жать кнопку было бы издевательством.
  if (chartEl) chartEl.addEventListener('click', (ev) => {
    if (!STATE.vertArm || STATE.markArm) return;
    // Только что сняли вершину щелчком по ней — этот щелчок уже отработан (П42).
    if (STATE._vertClickEaten) { STATE._vertClickEaten = false; return; }
    const { mx, my } = mainScales();
    const [px, py] = d3.pointer(ev, chartEl);
    const [xLo, xHi] = mx.domain(), [yLo, yHi] = my.domain();
    const hit = snapVertexAt(px, py);
    const x = hit ? hit.x : mx.invert(px);
    const y = hit ? hit.y : my.invert(py);
    if (x < xLo || x > xHi || y < yLo || y > yHi) return;   // щелчок мимо поля
    addAreaVert(x, y, hit && hit.key ? hit.name : '');
  });
  // «Убрать последнюю» убрана по П42: у каждой вершины в списке свой крестик.
  // «Убрать все вершины» подключается в wireAreaCalc вместе с остальной секцией.

  /* Щелчок по пустому месту холста гасит взведённую кривую — один из ровно
     двух способов (второй — повторный щелчок по той же кривой). Escape не
     гасит: так решил владелец. Полосы кривых и кружки точек останавливают
     всплытие, поэтому сюда доходит только настоящее «мимо». */
  if (chartEl) chartEl.addEventListener('click', () => {
    if (STATE.markArm || STATE.vertArm) return;      // взведённые режимы заняты своим
    disarmCurve();
  });

  // Подсказка: пока режим взведён, показываем кружком, куда сядет точка.
  if (chartEl) chartEl.addEventListener('mousemove', (ev) => {
    if (!STATE.markArm && !STATE.vertArm) return;
    const [px, py] = d3.pointer(ev, chartEl);
    // Н55: подсказка показывает ключевую точку в обоих режимах, а не только при
    // наборе вершин — иначе не видно, куда именно сядет своя точка.
    showSnapHint(snapVertexAt(px, py));
  });
  if (chartEl) chartEl.addEventListener('mouseleave', () => showSnapHint(null));
  /* Esc снимает ЛЮБОЙ взведённый режим — иначе курсор-перекрестие остаётся
     «залипшим». Раньше Escape знал только про свою точку, и из набора вершин
     выйти с клавиатуры было нечем. То же делает кнопка в полосе режима. */
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && canvasArmed()) leaveCanvasMode(); });
  const cvStop = document.getElementById('cv-mode-stop');
  if (cvStop) cvStop.addEventListener('click', () => leaveCanvasMode());
  renderMarkList();
  initSceneColorPickers();   // Фаза 2: пикеры у кривых издержек, производства, вееров
  wireFolds();               // сворачивание любых секций со складным заголовком
  hintsToDots();             // инструкции уходят под вопросик у заголовка
  wireAreaCalc();            // расчёт площадей: под кривой и по точкам
  initZoom();                // колесо и тачпад приближают график, двойной щелчок возвращает масштаб

  // Регулируемая цена (потолок / пол): ползунок (целые) + числовое поле (дробные).
  const pcSlider = document.getElementById('pc-slider');
  if (pcSlider) pcSlider.addEventListener('input', () => setPReg(parseFloat(pcSlider.value)));
  const pcInput = document.getElementById('pc-input');
  if (pcInput) pcInput.addEventListener('change', () => {
    const v = parseFloat(pcInput.value); if (!isNaN(v)) setPReg(v);
  });

  // Неравенство (ЧК1): способ ввода, число групп, поля доходов и формулы Лоренца.
  [['ineq-in-groups', 'groups'], ['ineq-in-incomes', 'incomes'], ['ineq-in-formula', 'formula']].forEach(([id, v]) => {
    const b = document.getElementById(id); if (b) b.addEventListener('click', () => setIneqInput(v));
  });
  const ineqN = document.getElementById('ineq-ngroups');
  if (ineqN) ineqN.addEventListener('change', () => setIneqGroupN(ineqN.value));
  const ineqInc = document.getElementById('ineq-incomes');
  const applyIneqInc = () => { if (ineqInc) STATE.ineqIncomes = ineqInc.value; if (typeof ineqMasterDetach === 'function') ineqMasterDetach(); redrawAll(); };
  const ineqIncBtn = document.getElementById('ineq-incomes-apply');
  if (ineqIncBtn) ineqIncBtn.addEventListener('click', applyIneqInc);
  if (ineqInc) ineqInc.addEventListener('keydown', e => { if (e.key === 'Enter') applyIneqInc(); });
  const ineqFm = document.getElementById('ineq-formula');
  const applyIneqFm = () => { if (ineqFm) STATE.ineqFormula = ineqFm.value; redrawAll(); };
  const ineqFmBtn = document.getElementById('ineq-formula-apply');
  if (ineqFmBtn) ineqFmBtn.addEventListener('click', applyIneqFm);
  if (ineqFm) ineqFm.addEventListener('keydown', e => { if (e.key === 'Enter') applyIneqFm(); });
  // Задача 3: ползунок и поле α для семейства L(p)=p^α.
  const ineqAlpha = document.getElementById('ineq-alpha');
  if (ineqAlpha) ineqAlpha.addEventListener('input', () => setIneqAlpha(ineqAlpha.value));
  const ineqAlphaNum = document.getElementById('ineq-alpha-num');
  if (ineqAlphaNum) ineqAlphaNum.addEventListener('change', () => setIneqAlpha(ineqAlphaNum.value));
  // ЧК2: галочка «Исходное состояние» — снимок текущей кривой как «было».
  const ineqGhostChk = document.getElementById('ineq-ghost');
  if (ineqGhostChk) ineqGhostChk.addEventListener('change', () => {
    STATE.showIneqGhost = ineqGhostChk.checked;
    if (ineqGhostChk.checked) ineqSnapshot(); else STATE.ineqGhost = null;
    redrawAll();
  });
  // ЧК3: перераспределение — галочка, инструмент, ползунки τ и T.
  const ineqRedistChk = document.getElementById('ineq-redist');
  if (ineqRedistChk) ineqRedistChk.addEventListener('change', () => {
    STATE.ineqRedistOn = ineqRedistChk.checked;
    const p = document.getElementById('ineq-redist-pane'); if (p) p.style.display = ineqRedistChk.checked ? '' : 'none';
    redrawAll();
  });
  [['ineq-rd-tax', 'tax'], ['ineq-rd-transfer', 'transfer']]
    .forEach(([id, v]) => { const b = document.getElementById(id); if (b) b.addEventListener('click', () => setIneqRedistTool(v)); });
  const ineqTau = document.getElementById('ineq-tau');
  if (ineqTau) ineqTau.addEventListener('input', () => {
    STATE.ineqTau = parseFloat(ineqTau.value);
    const l = document.getElementById('ineq-tau-val'); if (l) l.textContent = fmt(STATE.ineqTau);
    ineqRedraw();   // живой ползунок τ — пересчёт троттлом
  });
  const ineqTr = document.getElementById('ineq-transfer');
  if (ineqTr) ineqTr.addEventListener('input', () => {
    STATE.ineqTransfer = parseFloat(ineqTr.value);
    const l = document.getElementById('ineq-transfer-val'); if (l) l.textContent = fmt(STATE.ineqTransfer);
    ineqRedraw();   // живой ползунок трансферта — пересчёт троттлом
  });

  /* Макроэкономика (Фазы 16–22). Поля моделей связываются единообразно:
     текстовые — с формулами, числовые — с параметрами, ползунки — с живыми
     регуляторами. Каждое изменение просто дёргает redrawAll(). */
  Object.keys(MACRO).forEach(k => {
    const b = document.getElementById('mm-' + k); if (b) b.addEventListener('click', () => setMacroModel(k));
  });
  const macroField = (id, model, key, isNum) => {
    const e = document.getElementById(id); if (!e) return;
    const apply = () => {
      const v = isNum ? parseFloat(e.value) : (e.value || '').trim();
      if (isNum && isNaN(v)) return;
      STATE.macro[model][key] = v;
      _wantRangeAnim = true;
      redrawAll();
    };
    e.addEventListener('change', apply);
    if (!isNum) e.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') apply(); });
  };
  macroField('ma-lras', 'adas', 'lras', true);
  macroField('ma-sras', 'adas', 'sras', false);
  macroField('ma-ad', 'adas', 'ad', false);
  macroField('ma-pe', 'phillips', 'pe', true);
  macroField('ma-ustar', 'phillips', 'ustar', true);
  macroField('ma-beta', 'phillips', 'beta', true);
  macroField('ma-md', 'money', 'md', false);
  macroField('ma-ms', 'money', 'ms', true);
  macroField('ma-ls', 'loanable', 's', false);
  macroField('ma-ld', 'loanable', 'd', false);
  macroField('ma-fxd', 'fx', 'd', false);
  macroField('ma-fxs', 'fx', 's', false);
  macroField('ma-lafd', 'laffer', 'd', false);
  macroField('ma-lafs', 'laffer', 's', false);
  macroField('ma-lafmax', 'laffer', 'tmax', true);
  macroField('ma-is', 'islm', 'is', false);
  macroField('ma-lm', 'islm', 'lm', false);
  // Живые ползунки: дефицит бюджета и фиксированный курс.
  const macroSlider = (sid, iid, vid, model, key) => {
    const sl = document.getElementById(sid), inp = document.getElementById(iid), lab = document.getElementById(vid);
    const apply = (v) => {
      if (isNaN(v) || v < 0) return;
      STATE.macro[model][key] = v;
      if (sl) sl.value = v; if (inp) inp.value = v; if (lab) lab.textContent = fmt(v);
      _wantRangeAnim = true; redrawAll();
    };
    if (sl) sl.addEventListener('input', () => apply(parseFloat(sl.value)));
    if (inp) inp.addEventListener('change', () => apply(parseFloat(inp.value)));
  };
  macroSlider('ma-dg-slider', 'ma-dg-input', 'ma-dg-val', 'loanable', 'dg');
  macroSlider('ma-fxe-slider', 'ma-fxe-input', 'ma-fxe-val', 'fx', 'fixed');
  const fxFix = document.getElementById('ma-fx-fixed');
  if (fxFix) fxFix.addEventListener('change', () => {
    STATE.macro.fx.fixedOn = fxFix.checked;
    const f = document.getElementById('ma-fx-fixed-field'); if (f) f.style.display = fxFix.checked ? '' : 'none';
    if (typeof updatePult === 'function') updatePult();
    redrawAll();
  });

  /* Кнопка «Добавить кривую» заводит ПУСТУЮ строку под списком (решение
     владельца 22.08). Ни формулы, ни роли она не спрашивает: формулу человек
     печатает прямо в новой строке, роль у добавленной кривой всегда пустая,
     и в расчёты модели такая кривая не входит. */
  if (addBtn) addBtn.addEventListener('click', () => addEmptyCurve());
}

