// «Ответ»: представление поверх табло (редизайн 10.2026, фаза 6).
/* ---------------------------------------------------------------------
   Сцены по-прежнему пишут свои блоки #info-* (и #sec-eq) в табло #sb-body:
   этим живут печать, «Объяснение модели» и десятки проверок.
   «Ответ» собирается ПОВЕРХ них и только читает:
     · статус словами — предупреждения сцены (.warn) строкой над числами;
     · главные величины — выбранные строки табло (HERO ниже) СТРОКАМИ ПО
       ГРУППАМ (решение владельца 09.10, ADR 0144): у группы заголовок, в
       группе одна величина на строку, подпись слева, значение справа, один
       кегль у всех значений; у строки «было · Δ» из таблицы «До / После / Δ»;
     · дальше прежние блоки тем же видом строк; строка, ставшая главной, в
       блоке не повторяется (класс .is-hero), блок без своих строк прячется;
     · «Разбор» — абзацы #ex-body аккордеоном.
   Уже набранный KaTeX не разбирается: значение ячейки — копия узла значения
   той же строки, а у ячейки стоит data-src="блок#номер", по которому прибор
   паритета находит, откуда число.

   ⚠️ СКОРОСТЬ (COVERAGE О32): пересборка не на каждом кадре. Подпись
   содержимого табло сравнивается с прошлой, и «Ответ» пересобирается,
   только когда источник изменился; сам проход откладывается на кадр.
   --------------------------------------------------------------------- */

/* Главные числа модели: строки табло [блок, номер строки] и, если есть,
   строка таблицы «До / После / Δ», откуда брать «было» и Δ. Модели без
   записи главных чисел не получают (нет данных — нет секции). */
/* '*' — все строки блока с пометкой .ans-main, по порядку (ADR 0143): у
   «Математики» число главных величин зависит от модели и от числа кривых. */
const HERO = {
  'm-graph': [['info-graph', '*']],
  'm-transform': [['info-math', '*']],
  'm-optimum': [['info-math', '*']],
  'm-tangent': [['info-math', '*']],
  'm-minmax': [['info-math', '*']],
  'm-constraint': [['info-math', '*']],
  'ppf': [['info-ppf', 1], ['info-ppf', 2]],
  'ppfsum': [['info-ppfsum', 1], ['info-ppfsum', 2], ['info-ppfsum', 3]],
  'trade': [['info-ppft', 3], ['info-ppft', 4], ['info-ppft', 5]],
  'tradeprice': [['info-tb', 2], ['info-tb', 3]],
  /* Четвёртый элемент — [подпись, обозначение] вместо разбора подписи табло:
     «CS (потребитель)» в «Ответе» читается как «Излишек потребителя», CS = … */
  'sd': [['sec-eq', 0], ['sec-eq', 1],
    ['info-areas', 0, null, ['Излишек потребителя', 'CS']],
    ['info-areas', 1, null, ['Излишек производителя', 'PS']],
    ['info-areas', 2, null, ['Общественное благосостояние', 'SW']]],
  'sdsum': [['sec-eq', 0], ['sec-eq', 1]],
  'taxes': [['sec-eq', 0, 'Q'], ['sec-eq', 1, 'P покупателя'], ['sec-eq', 2, 'P продавца'], ['info-tax', 'DWL']],
  'tax': [['sec-eq', 0, 'Q'], ['sec-eq', 1, 'P покупателя'], ['sec-eq', 2, 'P продавца'], ['info-tax', 'DWL']],
  'tax-adv': [['sec-eq', 0, 'Q'], ['sec-eq', 1, 'P покупателя'], ['sec-eq', 2, 'P продавца'], ['info-tax', 'DWL']],
  'ceil': [['sec-eq', 0], ['sec-eq', 2], ['sec-eq', 3], ['sec-eq', 4]],
  'quota': [['sec-eq', 0], ['sec-eq', 1], ['sec-eq', 2]],
  'elast': [['info-elast', 1], ['info-elast', 7]],
  'ext': [['sec-eq', 0], ['sec-eq', 1], ['info-ext', 1], ['info-ext', 2]],
  'prod': [['info-prod', 0], ['info-prod', 1]],
  'costs': [['info-costs', 4], ['info-costs', 6]],
  'plants': [['info-plants', 0], ['info-plants', 1], ['info-plants', 2], ['info-plants', 3]],
  'isoquant': [['info-iso', 0], ['info-iso', 1]],
  /* Подписи монополии — названиями величин, а не «Монополия» / «Потребитель» из
     подписи табло «Qm (монополия)» (карточка Notion …8196…, 14.10). */
  'mono': [['info-mono', 0, null, ['Выпуск монополиста', 'Qm']], ['info-mono', 1, null, ['Цена монополиста', 'Pm']],
    ['info-mono', 4, null, ['Потери общества', 'DWL']], ['info-mono', 5, null, ['Излишек потребителя', 'CS']]],
  /* Естественная монополия: строка табло «(ATC(Qm); прибыль) = (40; 800)» — две
     величины. Режем в «Ответе», не в сцене (строку табло читает паритет): пятый
     элемент — части ячеек [подпись, обозначение, TeX обозначения], data-src
     «info-nat#2.1», «#2.2» (карточка …8121…). */
  'mono-nat': [['info-mono', 0, null, ['Выпуск монополиста', 'Qm']], ['info-mono', 1, null, ['Цена монополиста', 'Pm']],
    ['info-nat', 2, null, null, [['Средние издержки', 'ATC(Qm)', '\\mathrm{ATC}(Q_m)'], ['Прибыль', '', '']]]],
  'mono-d1': [['info-mono', 0], ['info-mono', 1]],
  'mono-d3': [['info-d3', 0], ['info-d3', 1]],
  'mono-kink': [['info-kink', 0], ['info-kink', 1], ['info-kink', 2]],
  'labor': [['info-labor', 0], ['info-labor', 1]],
  'labor-mono': [['info-labor', 0], ['info-labor', 1], ['info-labor', 4]],
  'labor-union': [['info-labor', 0], ['info-labor', 1]],
  'labor-bilat': [['info-labor', 0], ['info-labor', 1]],
  'smallopen': [['info-open', 2], ['info-open', 3]],
  'monoexport': [['info-d3', 0], ['info-d3', 1]],
  'consumer': [['info-consumer', 0], ['info-consumer', 1]],
  'cons-slutsky': [['info-consumer', 5], ['info-consumer', 6], ['info-consumer', 7]],
  'adas': [['info-macro', 0], ['info-macro', 1]],
  'islm': [['info-macro', 0], ['info-macro', 1]],
  'money': [['info-macro', 1]],
  'loanable': [['info-macro', 0]],
  'fx': [['info-macro', 0], ['info-macro', 1]],
  'laffer': [['info-macro', 0], ['info-macro', 1]],
  'ineq': [['info-inequality', 0], ['info-inequality', 1]],
};

/* ⚠️ ГЛАВНЫЕ СТРОКИ — ПО СОСТОЯНИЮ, А НЕ ПОСТОЯННЫМИ НОМЕРАМИ (А2 24.10, ADR 0158, карточка Notion …81e2…).
   HERO выше — строки модели БЕЗ вмешательства. Включили тариф, квоту, МРОТ, налог, потолок, пол — наверху
   «Ответа» встаёт ИТОГ вмешательства, как у «Налогов и субсидий» («Рынок после налога»): на графике цена 40 и
   импорт 20, а наверху стояла свободная торговля (70; 30; импорт 40), и итог тарифа оказывался в самом низу.
   Запись — функция от STATE: отдаёт список строк того же вида, что HERO, или null («как обычно»). Не нашлось ни
   одной строки (вмешательство не связывает — у табло нет его строк) — «Ответ» берёт HERO.
   Строка списка: [блок, строка, таблица, [подпись, обозначение, TeX], части, доп].
     · строка — номер, RegExp по подписи строки табло (номер у строки плавает: строки табло бывают через условие)
       или текст — строка таблицы «До / После» («Было / Стало»);
     · доп.g — заголовок группы («После тарифа»); строки с одним g — одна группа;
     · доп.before — число «до» (у частей — список): под значением «70 − 10» (ans-was);
     · доп.wasText — готовая строка под значением («50 + 50» у потерь из двух треугольников).
   Значение строки табло вида «55 (было 45)» в «Ответе» — «55», под ним «45 + 10» (answerCellWas). */
const HERO_STATE = {
  smallopen: () => {
    const o = STATE.open;
    if (!o || o.error) return null;
    const qds = [['Величина спроса', 'Qd', 'Q_d'], ['Величина предложения', 'Qs', 'Q_s']];
    const sur = [['Излишек потребителя', 'CS', '\\mathrm{CS}'], ['Излишек производителя', 'PS', '\\mathrm{PS}']];
    if (o.P1 == null) {
      const g = { g: 'Свободная торговля' };
      return [['info-open', /^При Pw/, null, null, qds, g], ['info-open', /^(Импорт|Экспорт)$/, null, null, null, g],
        ['info-open', /при своб\. торговле$/, null, null, sur, { g: 'Излишки при свободной торговле' }]];
    }
    const tar = (o.tool === 'tariff');
    const g = { g: tar ? 'После тарифа' : 'При квоте' };
    const dir = o.importing ? 'Импорт' : 'Экспорт';
    return [
      ['info-open', /^Внутренняя цена/, null, ['Внутренняя цена', 'P1', 'P_1'], null, g],
      ['info-open', /^\(Q/, null, null, [['Величина спроса', "Qd'", "Q_d'"], ['Величина предложения', "Qs'", "Q_s'"]],
        Object.assign({ before: [o.Qd, o.Qs] }, g)],
      ['info-open', new RegExp('^' + dir + ' после$'), null, [dir, ''], null, g],
      ['info-open', /^(Доход бюджета|Рента от квоты)$/, null, null, null, g],
      ['info-open', /^Итого потери$/, null, ['Потери общества', 'DWL'], null,
        Object.assign({ wasText: fmt(o.dwlProd) + ' + ' + fmt(o.dwlCons) }, g)],
      ['info-open', /^\(CS; PS\) (после тарифа|при квоте)$/, null, null, sur, { g: tar ? 'Излишки после тарифа' : 'Излишки при квоте' }],
    ];
  },
  'labor-mono': () => {
    const mn = STATE.laborMin, m = STATE.laborMono;
    if (STATE.laborStruct !== 'monopsony' || !mn || !mn.binding || !m) return null;
    const g = { g: 'С МРОТ' };
    return [['info-labor', /^Занятость с МРОТ$/, null, ['Занятость', 'L'], null, g],
      ['info-labor', /^Зарплата$/, null, ['Зарплата', 'W'], null, Object.assign({ before: m.Wm }, g)],
      ['info-labor', /^Безработица$/, null, null, null, g],
      ['info-labor', /^DWL \(потери\)$/, null, ['Потери общества', 'DWL'], null, Object.assign({ before: m.dwl }, g)]];
  },
  labor: () => {
    const mn = STATE.laborMin, eq = STATE.laborEq;
    if (STATE.laborStruct === 'monopsony' || STATE.laborStruct === 'union' || STATE.laborStruct === 'bilateral' || !mn || !mn.binding || !eq) return null;
    const g = { g: 'С МРОТ' };
    return [['info-labor', /^Занятость$/, null, ['Занятость', 'L'], null, g],
      ['info-labor', /^МРОТ/, null, ['Зарплата', 'W'], null, Object.assign({ before: eq.P }, g)],
      ['info-labor', /^Безработица$/, null, null, null, g],
      ['info-labor', /^DWL \(потери\)$/, null, ['Потери общества', 'DWL'], null, g]];
  },
  mono: () => {
    const it = STATE.intervType;
    const head = { tax: 'После налога', subsidy: 'После субсидии', quota: 'При квоте', ceiling: 'При потолке цены', floor: 'При поле цены' }[it];
    if (!head || STATE.monoMode !== 'simple') return null;
    const g = { g: head };
    if (it === 'tax' || it === 'subsidy' || it === 'quota') {
      return [['info-tax', it === 'quota' ? 'Q (выпуск)' : 'Q', null, ['Выпуск монополиста', 'Qm'], null, g],
        ['info-tax', 'P (цена)', null, ['Цена монополиста', 'Pm'], null, g],
        ['info-tax', 'DWL', null, ['Потери общества', 'DWL'], null, g],
        ['info-tax', 'CS', null, ['Излишек потребителя', 'CS'], null, g]];
    }
    return [['info-tax', /^Выпуск$/, null, ['Выпуск', 'Q'], null, g], ['info-tax', /^Цена$/, null, ['Цена', 'P'], null, g],
      ['info-tax', /^Дефицит$/, null, null, null, g], ['info-tax', /^DWL$/, null, ['Потери общества', 'DWL'], null, g]];
  },
  /* Пол цены: продаётся величина СПРОСА (продавцы готовы на 70, покупатели берут 30). У потолка продаётся
     величина предложения — его строки как в HERO. Заголовок группы — «Рынок при поле цены» блока равновесия. */
  ceil: () => {
    if (STATE.intervType !== 'floor' || !(STATE.pc && STATE.pc.binding)) return null;
    return [['sec-eq', 0], ['sec-eq', /^Qd/, null, ['Продаётся', 'Q']], ['sec-eq', /^Избыток$/], ['sec-eq', /^Потери|DWL/, null, ['Потери общества', 'DWL']]];
  },
  /* Внешние эффекты (решения владельца 24.10, …810e…, …81e7…): рынок — CS, PS, внешние издержки (выгоды) и SW
     С НИМИ; оптимум — внешние издержки и SW. Внешнего эффекта нет — как в HERO. */
  ext: () => {
    const e = STATE.ext;
    if (!e || (!e.msbOn && !e.mscOn) || e.Qopt == null) return null;
    const m = { g: 'Рынок' }, o = { g: 'Общественный оптимум' };
    return [['sec-eq', 0, null, null, null, m], ['sec-eq', 1, null, null, null, m],
      ['info-areas', /^CS/, null, ['Излишек потребителя', 'CS'], null, m],
      ['info-areas', /^PS/, null, ['Излишек производителя', 'PS'], null, m],
      ['info-areas', /^Внешние (издержки|выгоды)$/, null, null, null, m],
      ['info-areas', /^SW/, null, ['Общественное благосостояние', 'SW'], null, m],
      ['info-ext', /^Оптимум/, null, null, null, o],
      ['info-ext', /^Внешние (издержки|выгоды) в оптимуме$/, null, [(e.extOpt < 0 ? 'Внешние выгоды' : 'Внешние издержки'), ''], null, o],
      ['info-ext', /^SW в оптимуме$/, null, ['Общественное благосостояние', 'SW'], null, o],
      ['info-ext', /^DWL/, null, ['Потери общества', 'DWL'], null, o],
      ['info-ext', /^Корректирующ/, null, null, null, o]];
  },
};

/* Заголовок блока «Излишки» — по состоянию (карточка …81e2…): в «Малой открытой экономике» блок держит излишки
   автаркии, и без подписи их читали как излишки свободной торговли. Атрибут data-head, вид — calc2.css. */
function areasHead() {
  if (STATE.scenario === 'openecon') return 'Излишки при автаркии';
  return '';
}

/* Число из текста строки табло: «1 168,75», «−10». Не число — NaN. */
function ansNum(s) {
  const t = String(s == null ? '' : s).replace(/[\s   ]/g, '').replace(/−/g, '-').replace(',', '.');
  return /^-?\d+(\.\d+)?$/.test(t) ? parseFloat(t) : NaN;
}
/* «до» и изменение арифметикой: «70 − 10» (решение 13.10, ADR 0149). Разность — по ПОКАЗАННЫМ числам, иначе
   выражение не сходится с тем, что человек видит. Не числа — пусто. */
function answerCellWas(beforeText, afterText) {
  const a = ansNum(afterText), b = ansNum(beforeText);
  if (!isFinite(a) || !isFinite(b)) return '';
  const d = a - b;
  return String(beforeText).trim() + (d >= 0 ? ' + ' : ' − ') + fmt(Math.abs(d));
}

/* Заголовки групп «Ответа» по блоку табло. Блок без записи идёт без
   заголовка; у #sec-eq заголовок свой (копия .section-title); у «Математики»
   группы задают сами строки (data-ans-group, 70-scenes-math.js). */
const ANSWER_GROUP = {
  'info-areas': 'Излишки', 'info-tax': 'Вмешательство', 'info-sum': 'По группам',
  'info-mono': 'Монополия', 'info-nat': 'Естественная монополия', 'info-costs': 'Издержки',
  'info-prod': 'Производство', 'info-iso': 'Изокванта', 'info-plants': 'Два завода',
  'info-labor': 'Рынок труда', 'info-inequality': 'Неравенство', 'info-consumer': 'Выбор потребителя',
  'info-macro': 'Равновесие', 'info-math': 'Математика', 'info-elast': 'Эластичность',
  'info-ext': 'Внешние эффекты', 'info-open': 'Открытая экономика', 'info-d3': 'Дискриминация',
  'info-kink': 'Составной спрос', 'info-ppf': 'КПВ', 'info-ppfsum': 'Сумма КПВ',
  'info-ppft': 'Торговля', 'info-tb': 'Торговля двух стран', 'info-graph': 'Функция',
};

/* Имя группы главных строк, когда остаток её блока идёт ниже ОТДЕЛЬНО, со своим
   заголовком (buildAnswer): два «Монополия» подряд читались как ошибка (13.10). */
const ANSWER_GROUP_MAIN = { 'info-mono': 'Оптимум монополиста', 'info-costs': 'Оптимум фирмы' };

/* Подпись строки табло → подпись ячейки и обозначение. «Q* (количество)» →
   «Количество», «Q*»; «Равновесный выпуск Y» → «Равновесный выпуск», «Y»;
   иначе подпись целиком и без обозначения. */
/* Голое сокращение в подписи табло («DWL») — в ячейке словами и обозначением,
   как в макете: «Потери общества», «DWL = 225» (README 8.3). */
const HERO_WORDS = { DWL: 'Потери общества', CS: 'Излишек потребителя', PS: 'Излишек производителя' };
function heroLabel(t) {
  const s = String(t || '').replace(/\u200b/g, '').trim();
  if (HERO_WORDS[s]) return { caption: HERO_WORDS[s], not: s };
  const cap = (x) => x ? x.charAt(0).toUpperCase() + x.slice(1) : x;
  // «Q∗ (количество)»: обозначение, ПРОБЕЛ, слова в скобках. «f(x0)» — запись
  // функции, а не подпись со словами: её не режем.
  let m = /^([A-Za-zА-Яа-я][^\s()]{0,7})\s+\((.+)\)$/.exec(s);
  if (m && /[A-Za-z]/.test(m[1])) return { caption: cap(m[2].trim()), not: m[1] };
  m = /^(.+?)\s+([A-Za-z][A-Za-z0-9_*∗′]{0,5})$/.exec(s);
  if (m && /[А-Яа-я]/.test(m[1])) return { caption: cap(m[1].trim()), not: m[2] };
  return { caption: /^[A-Za-z]/.test(s) ? s : cap(s), not: '' };
}

/* Обозначение из подписи табло → TeX: заглавные в несколько букв (MC, DWL,
   CS) — прямым шрифтом; иначе буква и индекс («Qm» → Q_m, «X0» → X_0,
   «Wп» → W_п); звёздочка — верхним индексом. Не разобрали — null. */
function notationTex(t) {
  let s = String(t || '').replace(/[\u200b\s]/g, '');
  if (!s) return null;
  const star = /[∗*]$/.test(s); s = s.replace(/[∗*]$/, '');
  const sup = star ? '^{*}' : '';
  if (/^[A-Z]{2,4}$/.test(s)) return '\\mathrm{' + s + '}' + sup;
  const m = /^([A-Za-z])([A-Za-z0-9А-Яа-я]{0,4})$/.exec(s);
  if (!m) return null;
  const sub = m[2] ? '_{' + (/[А-Яа-я]/.test(m[2]) ? '\\text{' + m[2] + '}' : m[2]) + '}' : '';
  return m[1] + sub + sup;
}

function plainText(el) {
  if (!el) return '';
  const c = el.cloneNode(true);
  c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());
  return c.textContent.replace(/[\s   ​]+/g, ' ').trim();
}
function statRows(blk) {
  return blk ? [...blk.querySelectorAll('.stat')].filter(s => !s.closest('.ans-hero')) : [];
}
/* Строка таблицы «До / После / Δ» по подписи первой ячейки. */
function txRow(blkId, label) {
  // Таблица «До / После» живёт в блоке вмешательства, а строка главного числа —
  // в блоке равновесия (Q, цены): ищем в своём блоке, потом во вмешательстве.
  const own = document.getElementById(blkId);
  let tables = own ? [...own.querySelectorAll('table.tx-table')] : [];
  if (!tables.length) { const tx = document.getElementById('info-tax'); tables = tx ? [...tx.querySelectorAll('table.tx-table')] : []; }
  for (const t of tables) {
    const head = [...(t.querySelector('tr') || { children: [] }).children].map(plainText);
    for (const tr of t.querySelectorAll('tr')) {
      const cells = [...tr.children];
      if (cells.length < 3 || plainText(cells[0]) !== label) continue;
      const col = (name) => { const i = head.indexOf(name); return i > 0 ? plainText(cells[i]) : ''; };
      // У монополии столбцы «Было / Стало» (42-scenes-mono.js), у рынка — «До / После».
      return { before: col('До') || col('Было'), after: col('После') || col('Стало'), delta: col('Δ'), tr };
    }
  }
  return null;
}

const ANSWER_OPEN = {};   // раскрытые вопросы «Разбора» по моделям
let _answerSig = '';
let _answerMarks = 0;
let _answerQueued = false;
function answerSignature() {
  const sb = document.getElementById('sb-body');
  const ex = document.getElementById('ex-body');
  return String(STATE.sceneKey) + '|' + (sb ? sb.textContent.length + ':' + sb.textContent.slice(0, 4000) : '')
    + '|' + (ex ? ex.innerHTML.length : 0) + '|' + STATE.incBuyer + '|' + STATE.incSeller
    // Отрезок ответа: ручной отрезок с теми же числами ответа меняет строку под шапкой.
    + '|' + (typeof _ansSeg !== 'undefined' && _ansSeg ? _ansSeg.a + ':' + _ansSeg.b : '')
    // Свои площади (ADR 0148): посчитали, убрали, переименовали — группа заново.
    + '|' + (typeof areasLive === 'function' ? areasLive() : (STATE.areaCalcList || [])).map(r => r.id + ':' + r.label + ':' + r.value).join(',');
}
/* ⚠️ «ОТВЕТ» НЕ ЖДЁТ КАДРА, КОТОРОГО НЕ БУДЕТ (13.10). Пересборка отложена на
   кадр, чтобы протяжка не собирала колонку трижды за кадр. Но в фоновой
   вкладке кадров нет вовсе: модель, поля и табло уже новые, а колонка
   держала числа прошлого отрезка, пока вкладку не покажут (проверка карточки
   «ответ не пересчитывается после смены отрезка» шла чатом в Chrome, который
   читает страницу из фоновой вкладки). Скрытая страница собирает колонку
   сразу; видимая — на кадре, а таймер страхует, если кадр так и не пришёл. */
function scheduleAnswer() {
  if (_answerQueued) return;
  _answerQueued = true;
  const run = () => { if (!_answerQueued) return; _answerQueued = false; buildAnswer(); };
  if (document.hidden) { run(); return; }
  requestAnimationFrame(run);
  setTimeout(run, 250);
}

/* Модель «Математики» и «Построения графиков»: у её строк обозначение из
   подписи в значение не выносится («Пересекает ось x» → «−2; 2»). */
function answerIsMath() { return STATE.mode === 'math' || STATE.mode === 'graph'; }

/* Копия подписи строки табло без приписки .ans-ctx («, кривая f»): в
   «Ответе» её роль у заголовка группы. */
function labelCopy(lab) {
  const c = lab.cloneNode(true);
  c.querySelectorAll('.ans-ctx').forEach(x => x.remove());
  return c;
}

/* Значение строки «Ответа». Число — формулой прямым шрифтом; список и точки
   — по куску на значение, куски не рвутся, перенос (если весь список не
   влез даже в строку целиком) — только между ними; «нет» — приглушённо;
   прочее (фраза, «L = 10, MP = 300») — копией табло. Текст значения тот же,
   что у строки-источника: по нему сверяют паритет и «Сначала сам». */
const ANS_ITEM = /^\(?[−-]?\d[\d\s\u00a0\u202f\u2009]*([.,]\d+)?(;[−-]?\d[\d\s\u00a0\u202f\u2009]*([.,]\d+)?)?\)?(°|∘|\s?%)?$/;
function answerValueInto(v, srcEl, srcText) {
  const raw = srcEl ? plainText(srcEl) : String(srcText || '');
  if (/^нет$/i.test(raw)) { v.textContent = 'нет'; v.classList.add('ans-val--none'); return; }
  const pureNum = /^[−-]?\d[\d\s\u00a0\u202f\u2009]*([.,]\d+)?(\s?%)?$/.test(raw);
  if (typeof katexInto === 'function' && pureNum) {
    /* Пробелы — неразрывные (~), чтобы в тексте осталось «1 250», как в
       строке-источнике; запятая дроби без отбивки. */
    const tx = raw.replace(/^-/, '−').replace(/[\s\u00a0\u202f\u2009]+/g, '~').replace(/,/g, '{,}').replace(/%/g, '\\%').replace(/−/g, '\\text{−}');
    katexInto(v, '\\mathrm{' + tx + '}');
    return;
  }
  // Список чисел или точек через «;»: делим по «;» вне скобок.
  const items = [];
  let depth = 0, cur = '';
  for (const ch of raw) {
    if (ch === '(') depth++;
    if (ch === ')') depth--;
    if (ch === ';' && depth === 0) { items.push(cur.trim()); cur = ''; } else cur += ch;
  }
  items.push(cur.trim());
  if (items.length > 1 && typeof katexInto === 'function' && typeof statToTex === 'function'
      && items.every(it => ANS_ITEM.test(it.replace(/;\s+/g, ';')))) {
    v.innerHTML = '';
    /* Перенос только между точками: класс, а не :has() — и WebKit, в отличие от
       Chromium, при nowrap по <wbr> НЕ переносит (Safari резал строку краем
       колонки, 13.10, карточка …8100…). */
    v.classList.add('ans-val--list');
    items.forEach((it, k) => {
      const u = document.createElement('span'); u.className = 'ans-item';
      katexInto(u, statToTex(it));
      if (k < items.length - 1) {
        const sep = document.createElement('span'); sep.className = 'ans-sep'; sep.textContent = ';';
        u.appendChild(sep);
      }
      v.appendChild(u);
      // Место переноса без пробела в тексте: текст значения — побайтно табло («−2;2»).
      if (k < items.length - 1) v.appendChild(document.createElement('wbr'));
    });
    return;
  }
  if (srcEl) v.innerHTML = srcEl.innerHTML; else v.textContent = raw;
}

/* Заголовок группы: у кривой «Построения графиков» — цветная точка и запись
   «f(x) = x² − 4» (строка табло data-ans-head); иначе — текст, в котором
   $…$ набирается формулой, или готовая разметка заголовка табло. */
function answerGroupHead(g) {
  const h = document.createElement('h3');
  h.className = 'ans-ghead';
  if (g.head) {
    const dot = document.createElement('span'); dot.className = 'ans-gdot'; dot.setAttribute('aria-hidden', 'true');
    if (g.head.dataset.color) dot.style.background = g.head.dataset.color;
    const f = document.createElement('span'); f.className = 'ans-gform';
    if (!(typeof katexInto === 'function' && katexInto(f, g.head.dataset.tex || ''))) f.textContent = g.head.dataset.tex || '';
    h.append(dot, f);
  } else if (g.html) {
    h.innerHTML = g.html;
  } else {
    h.textContent = g.title;
    if (/\$/.test(g.title) && typeof renderMathIn === 'function') renderMathIn(h);
  }
  return h;
}

/* Строка об отрезке ответа под шапкой (только «Математика» и «Построение
   графиков», у «С ограничением» отрезка нет): числа живые, из _ansSeg. */
/* Вторая фраза строки об отрезке — пояснение: она живёт в «Разборе»
   (answerNotesToExplain, 86-workspace.js; тихие панели 14.10, README 5). */
const SEG_NOTE_SCALE = 'Масштаб графика на ответ не влияет.';
function segNoteOn() {
  const row = document.getElementById('ans-seg-row');
  return !!(answerIsMath() && typeof _ansSeg !== 'undefined' && _ansSeg && row && row.style.display !== 'none');
}
function buildSegNote() {
  const note = document.getElementById('ans-seg-note');
  if (!note) return;
  const on = segNoteOn();
  note.hidden = !on;
  if (!on) { note.textContent = ''; return; }
  const f = (typeof ansFmt === 'function') ? ansFmt : fmt;
  note.textContent = 'Ищем на отрезке $x$ от ' + f(_ansSeg.a) + ' до ' + f(_ansSeg.b) + '.';
  if (typeof renderMathIn === 'function') renderMathIn(note);
}

/* Блок табло, все строки которого ушли в «Ответ» (или в заголовок группы),
   не показывается вовсе: иначе от него оставался голый заголовок
   («Излишки» без строк у «Спроса и предложения»). */
function hideDrainedBlocks() {
  const sb = document.getElementById('sb-body');
  if (!sb) return;
  /* Та же величина второй строкой в другом блоке (у потолка цены «Дефицит 40»
     стоит и в равновесии, и под таблицей «До / После»): в колонке — один раз.
     Сравниваются подпись и значение строки-источника главной величины. */
  const key = (r) => plainText(r.querySelector(':scope > span')).replace(/\s+/g, '') + '=' + plainText(r.querySelector(':scope > b')).replace(/\s+/g, '');
  const heroKeys = new Set([...sb.querySelectorAll('.stat.is-hero')].map(key));
  sb.querySelectorAll('.stat').forEach(r => {
    r.classList.toggle('ans-dup', !r.classList.contains('is-hero') && heroKeys.has(key(r)));
  });
  const ownText = (el) => [...el.childNodes].some(n => n.nodeType === 3 && /\S/.test(n.nodeValue));
  /* «Блок пуст» решается по СОДЕРЖИМОМУ, а не по прямоугольникам (ADR 0150):
     в спрятанной колонке прямоугольников нет ни у кого, и живые блоки гасли
     (30 моделей из 42 открывались без строк). Узел виден человеку, если ни он,
     ни его предки в блоке не спрятаны — атрибутом или стилем (getComputedStyle
     считает и внутри спрятанной колонки). */
  const shownIn = (el, blk) => {
    for (let n = el; n && n !== blk; n = n.parentElement) {
      if (n.hidden) return false;
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    }
    return true;
  };
  /* С 14.10 — у ЛЮБОГО блока, не только с главными строками: пояснения ушли в
     «Разбор», повторы спрятаны, и блок, где кроме заголовка ничего не осталось
     («Вмешательство» монополии с одной заметкой «Двигайте ставку…»), не
     показывается (README пакета calc2_panels_20261014, 5). */
  [...sb.children].forEach(blk => {
    if (!blk.id) return;
    blk.classList.remove('ans-drained');
    if (!blk.children.length) return;
    const left = [...blk.querySelectorAll('*')].some(el => !el.closest('.section-title, .katex-mathml')
      && ownText(el) && shownIn(el, blk));
    if (!left) blk.classList.add('ans-drained');
  });
}

/* Строки табло, набранные ВСЛЕПУЮ (без прямоугольника: колонка «Ответ» спрятана
   или ещё не разложена), при первом показе набираются заново по месту: замер
   «помещается ли значение» (restatWide) вслепую пустой, и длинное значение
   оставалось сырым текстом. Зовётся в начале каждой сборки «Ответа» и при показе
   колонки (answerReflow); спрятанные строки (.is-hero и т. п.) не трогает.
   Возвращает число перенабранных строк (ADR 0150). */
function retypesetSeenRows() {
  const sb = document.getElementById('sb-body');
  if (!sb) return 0;
  /* Раскладка ещё едет (переход сетки колонок; при «меньше движения» сайт даёт
     всем свойствам переход 0,01 мс, и в кадр щелчка колонка ещё 44 px): мерить
     рано, перенаберёт отложенный проход answerReflow. */
  const app = document.querySelector('.app');
  if (app && typeof app.getAnimations === 'function' && app.getAnimations().length) return 0;
  const seen = [...sb.querySelectorAll('.stat')].filter(r => r._typesetBlind && typeof r._typesetSrc === 'string' && r.getClientRects().length);
  seen.forEach(row => {
    const val = row.querySelector(':scope > b');
    if (val) { val.innerHTML = row._typesetSrc; val.classList.remove('stat-tex'); }
    row.classList.remove('stat-eq', 'stat-own', 'stat-nosign', 'stat-stack', 'stat-phrase');
    row.querySelectorAll(':scope > .stat-sign').forEach(x => x.remove());
    row._typeset = false;
    delete row._typesetBlind;
  });
  if (seen.length && typeof typesetStats === 'function') typesetStats(sb);
  return seen.length;
}

/* Шрифт интерфейса догрузился: замер «помещается ли значение» шёл по запасному
   шрифту (другая ширина чернил), и стопка зависела от того, кто успел первым.
   Все набранные строки перемеряются один раз по настоящему шрифту. */
function remeasureStatsAfterFonts() {
  const sb = document.getElementById('sb-body');
  if (!sb) return;
  sb.querySelectorAll('.stat').forEach(r => { if (typeof r._typesetSrc === 'string') r._typesetBlind = true; });
  _answerSig = '';
  scheduleAnswer();
}
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(remeasureStatsAfterFonts);
  if (typeof document.fonts.addEventListener === 'function') document.fonts.addEventListener('loadingdone', remeasureStatsAfterFonts);
}

/* Колонку «Ответ» показали (стрелка, полоска, выезжающая панель, вкладка):
   «Ответ» пересобирается — собранный закрытым открывается тем же, что открытый
   с загрузки (ADR 0150). Пока колонка спрятана, это не зовётся. */
function answerReflow() {
  _answerSig = '';
  buildAnswer();
  // Ещё раз, когда раскладка устоялась (через два кадра; таймер — для фоновой вкладки).
  let done = false;
  const again = () => { if (done) return; done = true; _answerSig = ''; buildAnswer(); };
  requestAnimationFrame(() => requestAnimationFrame(again));
  setTimeout(again, 300);
}

/* Ячейки главных строк по списку вида HERO (см. HERO_STATE): строка табло помечается is-hero. */
function answerCells(spec) {
  const cells = [];
  const specRows = [];
  (spec || []).forEach(h => {
    const [blkId, i, tbl] = h;
    if (i === '*') {
      const blk = document.getElementById(blkId);
      const rows = statRows(blk);
      rows.forEach((r, k) => { if (r.classList.contains('ans-main')) specRows.push([blkId, k, tbl]); });
    } else specRows.push(h);
  });
  specRows.forEach(h => {
    const [blkId, i0, tbl, over, parts, opt] = h;
    const blk = document.getElementById(blkId);
    if (!blk || !blk.isConnected || blk.style.display === 'none') return;
    let i = i0;
    if (i instanceof RegExp) {
      // Строка по подписи: номер в data-src — настоящий номер строки табло (по нему сверяет паритет).
      i = statRows(blk).findIndex(r => i0.test(plainText(r.querySelector(':scope > span'))));
      if (i < 0) return;
    }
    if (typeof i === 'number') {
      const row = statRows(blk)[i];
      if (!row) return;
      const lab = row.querySelector(':scope > span'), val = row.querySelector(':scope > b');
      if (!val || !plainText(val)) return;
      row.classList.add('is-hero');
      if (parts) {
        // Пара «(40; 800)» — по ячейке на часть; текст значения — побайтно часть строки табло.
        const vals = plainText(val).replace(/^\(|\)$/g, '').split(';').map(x => x.trim());
        parts.forEach((pt, k) => {
          if (vals[k] == null || vals[k] === '') return;
          const before = opt && Array.isArray(opt.before) ? opt.before[k] : null;
          cells.push({ src: blkId + '#' + i + '.' + (k + 1), blk, row, labText: pt[0], valText: vals[k], over: [pt[0], pt[1], pt[2]], group: row.dataset.ansGroup || '', tx: null,
            opt, was: (before != null && isFinite(before)) ? answerCellWas(fmt(before), vals[k]) : '' });
        });
        return;
      }
      const c = { src: blkId + '#' + i, blk, row, lab, val, over, group: row.dataset.ansGroup || '', tx: tbl ? txRow(blkId, tbl) : null, opt, was: '' };
      /* «55 (было 45)» — значение 55, под ним «45 + 10» (ADR 0158): «было» строки табло — то же «до» и изменение,
         что у таблицы «До / После». */
      const m = /^(.+?)\s*\(было\s+(.+)\)$/.exec(plainText(val));
      if (m) { c.val = null; c.valText = m[1]; c.was = answerCellWas(m[2], m[1]) || ('было ' + m[2]); }
      else if (opt && typeof opt.before === 'number' && isFinite(opt.before)) c.was = answerCellWas(fmt(opt.before), plainText(val));
      if (opt && opt.wasText) c.was = opt.wasText;
      cells.push(c);
    } else {
      // Главное число из таблицы «До / После / Δ» (потери общества у налогов).
      const r = txRow(blkId, i);
      if (!r || !r.after) return;
      cells.push({ src: blkId + '@' + i, blk, labText: i, valText: r.after, tx: r, tableRow: true, over, opt });
    }
  });
  return cells;
}

function buildAnswer() {
  const host = document.getElementById('ans-hero');
  if (!host) return;
  if (retypesetSeenRows()) _answerSig = '';
  const sig = answerSignature();
  /* Сцена может переписать табло тем же текстом (пометки is-hero при этом
     пропадают): тогда собираем заново, хотя подпись та же. */
  const marks = document.querySelectorAll('#sb-body .stat.is-hero').length;
  if (sig === _answerSig && marks === _answerMarks) return;
  _answerSig = sig;
  document.querySelectorAll('#sb-body .stat.is-hero').forEach(s => s.classList.remove('is-hero'));
  document.querySelectorAll('#sb-body tr.ans-trdup').forEach(s => s.classList.remove('ans-trdup'));
  host.innerHTML = '';
  /* Главные строки по состоянию (HERO_STATE, ADR 0158); ни одной строки — как в HERO. */
  const base = HERO[STATE.sceneKey];
  const live = HERO_STATE[STATE.sceneKey] ? HERO_STATE[STATE.sceneKey]() : null;
  let cells = live ? answerCells(live) : [];
  if (!cells.length) {
    document.querySelectorAll('#sb-body .stat.is-hero').forEach(s => s.classList.remove('is-hero'));
    cells = answerCells(base);
  }
  host.hidden = !cells.length;
  _answerMarks = document.querySelectorAll('#sb-body .stat.is-hero').length;
  const isMath = answerIsMath();
  /* Группы: строки подряд с одним ключом. Ключ — data-ans-group строки
     (математика) или блок табло; строка из таблицы «До / После» стоит в группе
     предыдущей строки (потери общества — в «Рынке после налога»). */
  const eqTitle = document.querySelector('#sec-eq > .section-title');
  const eqShown = eqTitle && document.getElementById('sec-eq').style.display !== 'none' && plainText(eqTitle);
  const groups = [];
  cells.forEach(c => {
    let key, g = null;
    if (c.opt && c.opt.g) key = 'h:' + c.opt.g;
    else if (c.tableRow && groups.length) key = groups[groups.length - 1].key;
    else if (c.group) key = 'g:' + c.group;
    else key = 'b:' + c.src.replace(/[#@].*$/, '');
    const last = groups[groups.length - 1];
    if (last && last.key === key) { last.cells.push(c); return; }
    g = { key, cells: [c], title: '' };
    if (c.opt && c.opt.g) g.title = c.opt.g;
    else if (c.group) {
      g.head = [...c.blk.querySelectorAll('.stat[data-ans-head]')].find(x => x.dataset.ansHead === c.group) || null;
      g.title = c.group;
    } else {
      const blkId = c.src.replace(/[#@].*$/, '');
      if (blkId === 'sec-eq' && eqShown) g.html = eqTitle.innerHTML;
      else g.title = ANSWER_GROUP[blkId] || '';
    }
    groups.push(g);
  });
  /* Остаток блока табло, чьи главные строки стали ПОСЛЕДНЕЙ группой «Ответа», —
     продолжение этой группы: второй заголовок с тем же словом («Издержки»,
     «Монополия», «Равновесие») ему не нужен (13.10, карточка Notion …819f…). */
  const lastKey = groups.length ? groups[groups.length - 1].key : '';
  /* Не последняя группа: остаток её блока стоит ниже отдельно, под своим заголовком
     («Монополия» у «Естественной монополии»), и группа берёт своё имя. */
  groups.forEach(g => { const id = g.key.slice(2); if (g.key !== lastKey && /^b:/.test(g.key) && ANSWER_GROUP_MAIN[id]) g.title = ANSWER_GROUP_MAIN[id]; });
  const sbb = document.getElementById('sb-body');
  if (sbb) [...sbb.children].forEach(b => { if (b.id) b.classList.toggle('ans-cont', lastKey === 'b:' + b.id); });
  groups.forEach(g => {
    const box = document.createElement('div');
    box.className = 'ans-group';
    if (g.head || g.html || g.title) box.appendChild(answerGroupHead(g));
    /* Строки группы — на подложке (тихие панели 14.10, README 5 «Вид»): обёртка
       .ans-rows — новый узел ВНУТРИ .ans-group, классы строк и data-src прежние. */
    const rows = document.createElement('div');
    rows.className = 'ans-rows';
    g.cells.forEach(c => {
      const row = answerRow(c, isMath);
      /* Повтор — один раз (README 5): строка таблицы «До / После» прячется, только
         если главная ячейка показывает И её «после», И её «до» (изменение «50 − 10»
         собрано из этой самой строки). У потолка и квоты в HERO нет метки строки
         таблицы — их строки Q остаются. Класс на <tr> — атрибут: наблюдатель табло
         его пропускает. */
      if (c.tx && c.tx.tr && row.querySelector('.ans-was')) c.tx.tr.classList.add('ans-trdup');
      rows.appendChild(row);
    });
    box.appendChild(rows);
    host.appendChild(box);
  });
  /* «Свои площади» (решение владельца 13.10, ADR 0148): посчитанные человеком
     площади — группой ПОСЛЕ групп модели, в обоих режимах холста, строками
     «название — число» тем же видом (ADR 0144). Строки помечены .ans-own-cell:
     «Сначала сам» прячет их число, как остальные (selfCell), но главными
     числами модели они не считаются — ни для «всё сошлось», ни для подписей
     холста, ни для строки чисел «Скачать». Свои точки в «Ответ» не идут. */
  // Числа живые (areaLive, сессия 7): площадь по точкам и под кривой — по текущим точкам и кривой.
  const own = (typeof areasLive === 'function' ? areasLive() : (STATE.areaCalcList || [])).filter(r => r && isFinite(r.value));
  if (own.length) {
    const box = document.createElement('div');
    box.className = 'ans-group ans-own';
    box.appendChild(answerGroupHead({ title: 'Свои площади' }));
    const rows = document.createElement('div');
    rows.className = 'ans-rows';
    own.forEach(r => {
      const row = answerRow({ src: 'area#' + r.id, labText: r.label, valText: fmt(r.value), over: [r.label, ''] }, false);
      row.classList.add('ans-own-cell');
      rows.appendChild(row);
    });
    box.appendChild(rows);
    host.appendChild(box);
  }
  host.hidden = !cells.length && !own.length;
  buildSegNote();
  buildStatus();
  buildBurden();
  // Абзацы «Условия» в «Разборе» — по их тексту сейчас (сцена правит его после сборки «Разбора»).
  if (typeof conditionNotesToExplain === 'function') conditionNotesToExplain(document.getElementById('ex-body'));
  buildExplainAccordion();
  // Строка главных чисел над холстом (760–1239 px, «Ответ» выезжает).
  const strip = document.getElementById('ans-strip');
  if (strip) {
    strip.innerHTML = '';
    host.querySelectorAll('.ans-cell').forEach(c => {
      const s = document.createElement('span');
      const n = c.querySelector('.ans-not'), v = c.querySelector('.ans-val'), l = c.querySelector('.ans-lab');
      s.textContent = (n && plainText(n) ? plainText(n) : (l ? plainText(l) : '')) + ' = ';
      const b = document.createElement('b'); b.textContent = v ? plainText(v) : '';
      s.appendChild(b); strip.appendChild(s);
    });
  }
  // Обозначения в подписях строк («Весь ресурс на X») — формулой, как во всей панели.
  if (typeof markNotationsIn === 'function') markNotationsIn(host);
  decorateTables();
  hideEchoes();
  hideDrainedBlocks();
  liftTableHead();
  if (typeof applySelf === 'function') applySelf();
  markFirstSection();
}

/* Повторы «Ответа» — один раз (тихие панели 14.10, README 5 «Повторы»):
   · строка-эхо входа «Условия» в блоке вмешательства («Налог t = 20»);
   · «Бремя / Выигрыш покупателя и продавца», когда видна полоса «Кто несёт налог»;
   · блок «Излишки … до вмешательства» (#info-areas), если каждая его величина
     стоит в столбце «до» таблицы (CS, PS, SW; «CS + PS» квоты — это SW).
   Только классы (атрибуты): узлы табло «Ответ» не пишет. */
const ECHO_RE = /^(Налог t|Субсидия s|Ставка τ)/;
const BURDEN_RE = /^(Бремя|Выигрыш) (покупателя|продавца)$/;
function hideEchoes() {
  const tx = document.getElementById('info-tax');
  const burdenOn = !!(document.getElementById('ans-burden') && !document.getElementById('ans-burden').hidden);
  if (tx) statRows(tx).forEach(r => {
    const lab = plainText(r.querySelector(':scope > span'));
    r.classList.toggle('ans-echo', ECHO_RE.test(lab) || (burdenOn && BURDEN_RE.test(lab)));
  });
  const areas = document.getElementById('info-areas');
  if (!areas) return;
  areas.classList.remove('ans-intable');
  const num = (s) => { const m = String(s || '').replace(/[\s\u00a0\u202f\u2009]/g, '').replace(/−/g, '-').match(/-?\d+(?:[.,]\d+)?/g); return m ? m[m.length - 1] : null; };
  const before = new Map();
  document.querySelectorAll('#sb-body table.tx-table').forEach(t => {
    const head = [...(t.querySelector('tr') || { children: [] }).children].map(plainText);
    const iB = head.indexOf('До');
    if (iB < 1) return;
    t.querySelectorAll('tr').forEach(tr => {
      let k = plainText(tr.children[0]).replace(/\s+/g, '');
      if (k === 'CS+PS') k = 'SW';
      if (tr.children[iB]) before.set(k, num(plainText(tr.children[iB])));
    });
  });
  if (!before.size) return;
  const rows = statRows(areas);
  const all = rows.length > 0 && rows.every(r => {
    const m = /^(CS|PS|SW)\b/.exec(plainText(r.querySelector(':scope > span')));
    return !!m && before.get(m[1]) != null && before.get(m[1]) === num(plainText(r.querySelector(':scope > b')));
  });
  if (all) areas.classList.add('ans-intable');
}

/* Разделы колонки разделены чертой сверху; первый ВИДИМЫЙ раздел её не несёт
   (класс .ans-sec-first). Видимость — по вычисленному стилю, не по раскладке:
   колонка бывает спрятана (ADR 0150). */
function markFirstSection() {
  const shown = (el) => {
    for (let n = el; n && !n.classList.contains('side-inner'); n = n.parentElement) {
      if (n.hidden) return false;
      if (getComputedStyle(n).display === 'none') return false;
    }
    return true;
  };
  let first = null, prev = null;
  document.querySelectorAll('#ans-hero > .ans-group, #ans-burden, #sb-body > [id], #explain').forEach(el => {
    el.classList.remove('ans-sec-first', 'ans-sec-joined');
    if (!shown(el)) return;
    if (!first) first = el;
    /* Остаток блока табло — продолжение последней группы главных чисел (.ans-cont,
       без своего заголовка): сразу за ней он идёт без черты, частью того же раздела. */
    if (el.classList.contains('ans-cont') && prev && prev.classList.contains('ans-group')) el.classList.add('ans-sec-joined');
    prev = el;
  });
  if (first) first.classList.add('ans-sec-first');
}

/* Таблицы «До / После» табло в «Ответе» (тихие панели 14.10, README 5 «Вид»).
   Подписи строк — СЛОВАМИ: атрибут data-word у ячейки и CSS ::before; текст
   ячейки (CS, PS, «Бюджет (сбор)», SW) НЕ меняется — по нему ищут строки txRow и
   HERO, его читают паритет, «Сначала сам» и приборы. Столбец «Δ» помечен и не
   виден: изменение главных величин стоит под главными числами. Заголовок
   раздела вмешательства с таблицей — «До и после налога / субсидии /
   вмешательства». ⚠️ В табло меняются только АТРИБУТЫ: наблюдатель табло их
   пропускает, запись узлов зациклила бы пересборку. */
const TX_WORDS = {
  CS: 'Излишек потребителя', PS: 'Излишек производителя', 'Бюджет (сбор)': 'Налоговые сборы',
  'Бюджет (расход)': 'Расходы бюджета', DWL: 'Потери общества', SW: 'Общественное благосостояние',
};
function decorateTables() {
  const sb = document.getElementById('sb-body');
  if (!sb) return;
  sb.querySelectorAll('table.tx-table').forEach(t => {
    const head = t.querySelector('tr');
    const dCol = head ? [...head.children].findIndex(c => plainText(c) === 'Δ') : -1;
    t.querySelectorAll('tr').forEach(tr => {
      [...tr.children].forEach((c, i) => c.classList.toggle('tx-delta', i === dCol && dCol > 0));
      const first = tr.children[0];
      if (!first || first.tagName !== 'TD') return;
      const w = TX_WORDS[plainText(first)];
      if (w) { if (first.dataset.word !== w) first.dataset.word = w; }
      else if (first.hasAttribute('data-word')) first.removeAttribute('data-word');
    });
  });
  const ar = document.getElementById('info-areas');
  if (ar) {
    const h = areasHead();
    if (h) { if (ar.dataset.head !== h) ar.dataset.head = h; } else if (ar.hasAttribute('data-head')) ar.removeAttribute('data-head');
  }
  const tx = document.getElementById('info-tax');
  if (tx) {
    const hasTable = [...tx.querySelectorAll('table.tx-table tr:first-child th')].some(th => /^(До|Было)$/.test(plainText(th)));
    const it = STATE.intervType;
    const h = !hasTable ? '' : (it === 'tax' ? 'До и после налога' : it === 'subsidy' ? 'До и после субсидии' : 'До и после вмешательства');
    if (h) { if (tx.dataset.head !== h) tx.dataset.head = h; } else if (tx.hasAttribute('data-head')) tx.removeAttribute('data-head');
  }
}

/* Подписи столбцов «до», «после» стоят на строке заголовка раздела «До и после …», только если таблица идёт
   СРАЗУ за заголовком (правка А2 по приёмке 14.10, сессия 5). У квоты между заголовком и таблицей стоят «Коридор
   цен» и «Выбранная цена», и поднятые подписи ложились поверх второй строки — там подписи своей строкой над
   таблицей. «Видно» решается по вычисленному стилю узлов внутри блока (колонка может быть закрыта, и
   прямоугольников нет ни у кого); класс ставится на блок — атрибут, наблюдатель табло его пропускает. */
function liftTableHead() {
  const tx = document.getElementById('info-tax');
  if (!tx) return;
  const tbl = tx.querySelector('table.tx-table');
  let lift = !!(tbl && tx.hasAttribute('data-head'));
  if (lift) {
    const shown = (el) => {
      for (let n = el; n && n !== tx; n = n.parentElement) {
        const cs = getComputedStyle(n);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      }
      return true;
    };
    const w = document.createTreeWalker(tx, NodeFilter.SHOW_TEXT);
    for (let t = w.nextNode(); t; t = w.nextNode()) {
      if (tbl.contains(t)) break;
      if (!(tbl.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_PRECEDING)) break;
      if (t.nodeValue.trim() && shown(t.parentElement)) { lift = false; break; }
    }
  }
  if (tx.classList.contains('tx-lift') !== lift) tx.classList.toggle('tx-lift', lift);
}

/* Строка «Ответа»: подпись слева, значение справа, изменение «50 − 10» под значением.
   Классы .ans-cell / .ans-lab / .ans-not / .ans-val / .ans-was и data-src —
   прежние (меняется вид, а не смысл): по ним работают паритет и «Сначала сам».
   data-not — обозначение величины («x», «Q*»): по нему «Сначала сам» узнаёт
   ось, даже когда обозначение не выносится в значение (математика). */
function answerRow(c, isMath) {
  const d = document.createElement('div');
  d.className = 'ans-cell';
  d.dataset.src = c.src;
  const labText = c.lab ? plainText(labelCopy(c.lab)) : c.labText;
  let parts = c.over ? { caption: c.over[0], not: c.over[1] } : heroLabel(labText);
  /* Значение со своим «=» («L = 15, AP = 225»): обозначение остаётся в
     подписи («Максимум AP»), иначе выходило «AP = L = 15, AP = 225». */
  if (!c.over && parts.not && /=/.test(c.val ? plainText(c.val) : String(c.valText || ''))) parts = { caption: labText, not: '', keep: parts.not };
  if (parts.not || parts.keep) d.dataset.not = parts.not || parts.keep;
  const l = document.createElement('div'); l.className = 'ans-lab';
  const line = document.createElement('div'); line.className = 'ans-line';
  if (isMath || (!parts.not && c.lab && !c.over)) {
    // Подпись как в табло, вместе с набранными формулой обозначениями.
    if (c.lab) l.append(...labelCopy(c.lab).childNodes); else l.textContent = labText;
  } else {
    l.textContent = parts.caption;
  }
  if (parts.not && !isMath) {
    const n = document.createElement('span'); n.className = 'ans-not';
    // Обозначение — всегда формулой (правило 46 DESIGN.md): «Q∗» → Q*, «X0» → X₀.
    const tex = (c.over && c.over[2]) || notationTex(parts.not);
    if (tex && typeof katexInto === 'function') katexInto(n, tex);
    else if (typeof paintNotation === 'function') paintNotation(n, parts.not); else n.textContent = parts.not;
    const eq = document.createElement('span'); eq.className = 'ans-eq'; eq.textContent = '=';
    line.append(n, eq);
  }
  const v = document.createElement('span'); v.className = 'ans-val';
  answerValueInto(v, c.val || null, c.valText);
  line.appendChild(v);
  d.append(l, line);
  /* Изменение — арифметикой «50 − 10»: число до и изменение со знаком, и само
     выражение равно значению в строке (решение владельца 13.10, Notion …81a2…;
     прежде «было 50 · −10», ADR 0144). Знак — настоящий минус U+2212. */
  const delta = c.tx ? /^([+−-])\s*(.+)$/.exec(String(c.tx.delta || '').trim()) : null;
  if (c.was) {
    // «до» и изменение, собранные по строке табло или по числу «до» (answerCells, ADR 0158).
    const w = document.createElement('div'); w.className = 'ans-was';
    w.textContent = c.was;
    d.appendChild(w);
  } else if (c.tx && c.tx.before && (delta || /^0([,.]0*)?$/.test(String(c.tx.delta || '').trim()))) {
    const w = document.createElement('div'); w.className = 'ans-was';
    w.textContent = c.tx.before + (delta ? (delta[1] === '+' ? ' + ' : ' − ') + delta[2] : ' + 0');
    d.appendChild(w);
  }
  return d;
}

/* «Кто несёт налог» / «Кому достаётся субсидия» (README макета, 8.5): доли
   из бремени, которое сцена уже посчитала (STATE.incBuyer, incSeller —
   40-scenes-market.js). Нет вмешательства или нет исходного рынка — нет секции. */
function burdenOn() {
  const b = +STATE.incBuyer, s = +STATE.incSeller;
  return /^(taxes|tax|tax-adv)$/.test(STATE.sceneKey) && STATE.taxActive && !STATE.taxNoBase
    && isFinite(b) && isFinite(s) && Math.abs(b) + Math.abs(s) > 1e-9;
}
/* Строка-пояснение под полосой бремени — в «Разборе» (answerNotesToExplain). */
function burdenNoteText() {
  if (!burdenOn()) return '';
  const form = (typeof taxFormKey === 'function') ? taxFormKey() : 'unit';
  /* У потоварного налога строки нет (сессия 5, А4): «переключите сторону, и числа не изменятся» — интерфейс и та же
     мысль, что вопрос «Разбора» «Кто на самом деле платит налог?». */
  return (form && form !== 'unit') ? 'При налоге долей от цены клин растёт вместе с ценой.' : '';
}
function buildBurden() {
  const box = document.getElementById('ans-burden');
  if (!box) return;
  const b = +STATE.incBuyer, s = +STATE.incSeller;
  const on = burdenOn();
  box.hidden = !on;
  if (!on) { box.innerHTML = ''; return; }
  const sub = STATE.intervType === 'subsidy';
  const tot = Math.abs(b) + Math.abs(s);
  const pb = Math.abs(b) / tot * 100, ps = 100 - pb;
  const pct = (x) => fmt(Math.round(x)) + '\u202f%';
  box.innerHTML = '';
  const h = document.createElement('h3'); h.className = 'col-sub'; h.textContent = sub ? 'Кому достаётся субсидия' : 'Кто несёт налог';
  const bar = document.createElement('div'); bar.className = 'burden-bar';
  bar.setAttribute('role', 'img');
  bar.setAttribute('aria-label', 'Покупатели ' + pct(pb) + ', продавцы ' + pct(ps));
  const bb = document.createElement('span'); bb.className = 'burden-b'; bb.style.width = pb + '%';
  bar.appendChild(bb);
  const cols = document.createElement('div'); cols.className = 'burden-cols';
  const col = (cls, name, v, p) => {
    const c = document.createElement('div'); c.className = 'burden-col ' + cls;
    const n = document.createElement('div'); n.className = 'burden-name'; n.textContent = name;
    const x = document.createElement('div'); x.className = 'burden-val'; x.textContent = fmt(Math.abs(v)) + ' (' + pct(p) + ')';   // «10 (50 %)»: точка читалась умножением (13.10)
    c.append(n, x); return c;
  };
  cols.append(col('is-buyer', 'Покупатели', b, pb), col('is-seller', 'Продавцы', s, ps));
  // Пояснение под полосой — в «Разборе» (burdenNoteText); здесь только числа.
  box.append(h, bar, cols);
}

/* Статус словами: предупреждения сцены строкой над числами (канон 2.5:
   серая плашка, цветная полоса слева, значок; заливки -tint нет). Сами
   предупреждения остаются на месте в табло — это их источник. */
function buildStatus() {
  const box = document.getElementById('ans-status');
  if (!box) return;
  box.innerHTML = '';
  /* Предупреждение в табло спрятано стилем (оно стоит здесь строкой), поэтому
     по offsetParent не судим: отсеиваем только то, что спрятала САМА СЦЕНА —
     hidden, инлайновый display:none или scoped-off у узла и предков (блок
     чужой сцены). Прежнее условие было истинно всегда. */
  const sceneHidden = (w) => { for (let n = w; n && n.id !== 'sb-body'; n = n.parentElement) { if (n.hidden || (n.style && n.style.display === 'none') || n.classList.contains('scoped-off')) return true; } return false; };
  const warns = [...document.querySelectorAll('#sb-body .warn')].filter(w => !sceneHidden(w));
  warns.forEach(w => {
    const t = plainText(w);
    if (!t) return;
    const p = document.createElement('div');
    p.className = 'ans-status' + (/\d/.test(t) ? ' has-num' : '');
    p.setAttribute('role', 'status');
    p.innerHTML = w.innerHTML;
    box.appendChild(p);
  });
  box.hidden = !box.children.length;
}

/* «Разбор»: каждый абзац с жирным началом — вопрос-кнопка, остальное — ответ;
   абзац «Вывод:» / «Вывод.» — плашка вывода; абзац без жирного начала —
   продолжение предыдущего ответа (COVERAGE О8). По умолчанию ни один вопрос
   не раскрыт (решение владельца 14.10, Notion …81de…, ADR 0150; до того был
   раскрыт первый); раскрытые помнятся у модели (ANSWER_OPEN). */
function buildExplainAccordion() {
  const ex = document.getElementById('ex-body');
  syncExplainBar(ex);
  if (!ex || ex._accSig === ex.innerHTML.length + ':' + STATE.sceneKey) return;
  ex.querySelectorAll(':scope > .sb-note').forEach((note, ni) => {
    const ps = [...note.querySelectorAll(':scope > p')];
    ps.forEach((p, i) => {
      const b = p.firstElementChild;
      // Жирное НАЧАЛО абзаца: до <b> не должно стоять текста (иначе это выделенное
      // слово посреди фразы, а не вопрос).
      let before = '';
      for (let n = p.firstChild; n && n !== b; n = n.nextSibling) before += n.textContent || '';
      const lead = (b && b.tagName === 'B' && !before.trim()) ? plainText(b) : '';
      p.classList.remove('ex-q', 'ex-out', 'ex-open');
      if (!lead) return;
      if (/^Вывод[.:]/.test(lead)) { p.classList.add('ex-out'); return; }
      p.classList.add('ex-q');
      const mem = ANSWER_OPEN[STATE.sceneKey];
      const id = ni + ':' + i;
      if (mem && mem.has(id)) p.classList.add('ex-open');
      p.dataset.acc = id;
      // Ответ — всё после жирного вопроса: в свой узел, его и прячет аккордеон.
      if (!p.querySelector(':scope > .ex-a')) {
        const a = document.createElement('span');
        a.className = 'ex-a';
        while (b.nextSibling) a.appendChild(b.nextSibling);
        p.appendChild(a);
      }
      if (!b._accWired) {
        b._accWired = true;
        b.setAttribute('role', 'button');
        b.tabIndex = 0;
        const toggle = () => {
          p.classList.toggle('ex-open');
          b.setAttribute('aria-expanded', p.classList.contains('ex-open') ? 'true' : 'false');
          // Раскрытое помнится у каждой модели (README макета, 8.8).
          const set = new Set([...ex.querySelectorAll('p.ex-open[data-acc]')].map(x => x.dataset.acc));
          ANSWER_OPEN[STATE.sceneKey] = set;
        };
        b.addEventListener('click', toggle);
        b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      }
      b.setAttribute('aria-expanded', p.classList.contains('ex-open') ? 'true' : 'false');
    });
  });
  /* Жирное слово ВНУТРИ фразы (до него стоит текст) — строчное: правило
     заголовка врезки (.sb-note b — блок 11 px) разрывало абзац «Налогов»
     («сдвигается» отдельной строкой). Свой заголовок врезки — жирное в начале,
     без текста перед ним — остаётся блоком. */
  ex.querySelectorAll('.sb-note b').forEach(b => {
    if (b.matches('p.ex-q > b')) return;
    let before = '';
    for (let n = b.previousSibling; n; n = n.previousSibling) before += n.textContent || '';
    b.classList.toggle('ex-inline', !!before.trim());
  });
  ex._accSig = ex.innerHTML.length + ':' + STATE.sceneKey;
  syncExplainBar(ex);
}

/* Полоса «Разбор · N вопросов» — последняя строка «Ответа» (решение владельца
   14.10, Notion …81de…, ADR 0150). «Разбор» свёрнут при загрузке и при каждом
   входе в модель. Свёрнутость — ВИД, а не модель: класс body.ex-shown (у body
   нет id, formNodes его не видит), кнопка #ex-bar — в FORM_SKIP_IDS. Ни шага
   истории, ни ссылки. На телефоне полосы нет: вкладка «Разбор» показывает всё. */
let _exBarScene = null;
function questionsWord(n) {
  const d = n % 10, h = n % 100;
  if (d === 1 && h !== 11) return n + ' вопрос';
  if (d >= 2 && d <= 4 && (h < 12 || h > 14)) return n + ' вопроса';
  return n + ' вопросов';
}
function syncExplainBar(ex) {
  const bar = document.getElementById('ex-bar');
  if (!bar) return;
  if (!bar._wired) {
    bar._wired = true;
    bar.addEventListener('click', () => {
      const on = !document.body.classList.contains('ex-shown');
      document.body.classList.toggle('ex-shown', on);
      bar.setAttribute('aria-expanded', on ? 'true' : 'false');
    });
  }
  if (_exBarScene !== STATE.sceneKey) {
    _exBarScene = STATE.sceneKey;
    document.body.classList.remove('ex-shown');
  }
  bar.setAttribute('aria-expanded', document.body.classList.contains('ex-shown') ? 'true' : 'false');
  const n = ex ? ex.querySelectorAll('p.ex-q').length : 0;
  const cnt = bar.querySelector('.ex-bar-count');
  const t = n ? questionsWord(n) : '';
  if (cnt && cnt.textContent !== t) cnt.textContent = t;
}

/* Табло пишут и вне перерисовки (отложенные расчёты сцен): «Ответ» следит
   за ним сам. Пересборка всё равно откладывается на кадр и сравнивает
   подпись содержимого, поэтому лишней работы на кадре протяжки нет. */
(function watchScoreboard() {
  const sb = document.getElementById('sb-body');
  if (!sb || typeof MutationObserver !== 'function') return;
  new MutationObserver((list) => {
    // Свои пометки is-hero «Ответ» ставит сам — на них не отвечаем.
    if (list.every(m => m.type === 'attributes')) return;
    scheduleAnswer();
  }).observe(sb, { childList: true, subtree: true, characterData: true });
})();
