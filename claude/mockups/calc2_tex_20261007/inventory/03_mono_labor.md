# 03 · Монополия и рынок труда: опись мест рисования

Файлы: `calc2/static/calc2/42-scenes-mono.js` (1677 строк) и `calc2/static/calc2/46-scenes-labor.js` (744 строки), ветка `feat/calc2-redesign`. Оба прочитаны целиком. Код репозитория не запускался и не менялся. Номера строк — по текущему состоянию файлов. Там, где трактовка не проверена запуском, стоит пометка «по чтению кода».

---

## 0. Общее для обоих файлов

### 0.1. Порядок кадра

`redrawAll()` (60-overlays.js:10) → `redrawScene()` (:78) → `drawOverlays()` (:453) → проходы по подписям: `applyLabelSize` (:19), `unclipLabels` (:20), `keepAxisNamesInside` (:21), `spreadLabels` (:22), `applyLabelInk` (:23), `typesetChartLabels` (:29) → `markServiceNodes` (:74) → `selfCanvas` (:75).

Что эти проходы делают с уже нарисованным сценой (важно для «записи при рисовании»: сцена знает состояние ДО них):

| Проход | Адрес | Что меняет |
|---|---|---|
| `flushDrawnKeyPoints` | 20-plane.js:766 | добавляет невидимые `circle.kp-mark` (r=0, `data-skip-export`) в углы «число на оси Q × число на оси P с пунктиром» |
| `applyAreaColors` | 60-overlays.js:893 | перекрашивает заливки по ключу `data-legend`, если человек выбрал свой цвет (`STATE.areaColor`) |
| `drawCurveHits` | 60-overlays.js:1717 | прозрачные полосы попадания по `snapTargetsAll()` (`data-skip-export`) |
| `drawLegend` | 60-overlays.js:992 | легенда: по одной строке на каждый РАЗНЫЙ ключ `data-legend` на холсте; подпись строки = `areaShort(key)` (:983); место выбирается по пикселям (`legendCorner`, :1072) |
| `applyLabelSize` | 30-curves.js:841 | множит `font-size` всех `text`, кроме `.axis-num`, на `STATE.labelSize/12` |
| `unclipLabels` | 30-curves.js:447 | подпись, которую режет clip-path её группы, ПЕРЕНОСИТ в слой `g.free-labels` в конце SVG |
| `spreadLabels` | 30-curves.js:533 | прижимает `.coord-num` к краю холста; удаляет `.axis-num`, на которые легла `.coord-num`; сдвигает наложившиеся подписи (шаг 13 px по вертикали, до 70 px вбок) |
| `applyLabelInk` | 30-curves.js:806 | меняет `fill` текста до контраста 4,6; прозрачность текста сворачивает в цвет |
| `markServiceNodes` | 60-overlays.js:2002 | ставит `data-service="handle"` и `data-skip-export` кружку-ручке, стоящему сразу за элементом с d3.drag |
| `selfCanvas` | 96-self.js:139 | в режиме «Сначала сам» переписывает текст `.coord-num` на обозначение или «?» |

### 0.2. Общие помощники и сокращения в таблицах

| Сокращение | Что это | Адрес | Вид на месте |
|---|---|---|---|
| **П** | пунктир-проекция (`line`) | локальный `dash` в каждой функции | stroke `COL.inkSoft`, 1, dash «4 3» |
| **ТчкM** | главная точка | — | `circle` r 4.5, fill `COL.ink`, stroke `COL.halo` 1.5 |
| **Призрак** | бледная точка «было» | — | `circle` r 4, fill `COL.halo`, stroke `COL.ghost` 1.5 |
| **Тголый** | `append('text')….text(строка)` мимо `renderLabelText` | — | `FS.base` (12), 600, ореол `COL.halo` 2.5; класса нет, `data-raw` нет |
| **pointName** | имя точки | 40-scenes-market.js:1213 | `text.point-name` в (px+8; py−8), `FS.large` (14), 600, ореол 5; `data-raw`; регистрирует имя ключевой точки |
| **осьX** = `axisValueX` | число у оси количества | 20-plane.js:831 | `text.coord-num` в (px; sy(0)+8 px), anchor middle, hanging; `FS.small` (10), 600, `COL.ink`, ореол 3; текст «число» либо «число_индекс»; `data-raw` |
| **осьY** = `axisValueY` (и `yWageValue`, 40-scenes-market.js:1244) | число у оси цены/зарплаты | 20-plane.js:858 | то же в (sx(0)−8 px; py), anchor end, middle |
| **haloText** | текст с ореолом | 40-scenes-market.js:1180 | `text`, `FS.small`, 600, `COL.ink`, ореол 3; `data-raw`; x зажат в холст, y в [9; H−4] |
| **labelCurve** | подпись кривой | 30-curves.js:928 | `text.curve-name`, 12, 600, ореол 2.6; `data-raw`; место = `curveAnchor` (крайняя правая видимая точка кривой) ±6 px по x, −7 либо +14 px по y; переворот и сглаживание по пикселям |
| **drawMarginalCurve** | предельная кривая | 30-curves.js:180 | два `path`: основной (значения ≥ 0, q ≤ to) и хвост ниже оси (значения ≤ 0, q ≤ ноль породившей кривой; `data-marginal-tail="1"`, толщина 0.55·w, opacity .45); 401 узел (либо `opts.n`+1) на [from; max(to, ноль родителя)]; dash «6 4» |
| **drawCurves** | кривые общего списка `STATE.curves` | 30-curves.js:1072 | на каждую видимую кривую: `path` (`data-curve`=id, цвет `curve.color`, толщина `LW.base` 2.5), прозрачная полоса 16 px (`data-skip-export`, `data-hit`, `data-hit-name`), подпись через labelCurve (имя: D, S, MC, TC, ATC либо своё) |

У осьX/осьY: при совпадении с делением шкалы (7 px либо 2 % размаха) деление удаляется (`dropTickAt`, 20-plane.js:632), число красится в `--accent` и 700; такое же число в 6 px от этого места второй раз не печатается (`coordAlreadyAt`, :679). Оба помощника зовут `noteAxisX/Y` (реестр ключевых точек).

Стили заливок (одинаковы во всех местах): **VC** = fill `COL.dwl`, opacity .22; **PS** = `COL.S` .16; **CS** = `COL.D` .16; **DWL** = `COL.inkSoft` .28; **бюджет** = `COL.tax` .22.

**MC⁺(q)** = `mcFloor(mcAt(q))` = max(0, MC(q)); NaN превращается в 0 (42-scenes-mono.js:51).

### 0.3. Откуда берутся формулы

| Источник | Поле | Примечание |
|---|---|---|
| Кривая списка с ролью | `curve.expr` (строка Math.js; переменная Q, q, x, L, l, X — синонимы, 10-math-core.js:36) | у прямой ещё `curve.linear {a,b}`; у нелинейной, введённой как Q = f(P), `expr` — это Q(P), а P(Q) есть только численно (`curve.fn`, 10-math-core.js:485) |
| D монополии (mono, mono-nat, mono-d1) | `STATE.D` = `curveByRole('demand')` | 40-scenes-market.js:29 |
| MC монополии | `mcSourceCurve()` = роль `mc`, иначе `supply` (42:11); иначе `mcAt` = численная производная кривой роли `tc` (42:20–31) | строка есть у кривой списка; у MC из TC строки нет |
| mono-d3, monoexport | `STATE.d3D1`, `STATE.d3D2`, `STATE.d3MC` → `makeCurve` (42:937) → `STATE.discr3.c1/c2/cm` | объект `{compiled, linear}` БЕЗ поля `expr` |
| mono-kink | `STATE.kiD1…kiD3` (суммируемые спросы) либо `STATE.kpD1`, `STATE.kpD2` (два куска); `STATE.kinkMC` | результат в `STATE.kinked {segs, kinks, Dfn, mcCurve}` |
| Рынок труда | `STATE.laborD`, `STATE.laborS` = кривые списка ролей `demand`, `supply` (46:115–116) | по умолчанию `100 - L` и `L` (52-modes.js:862–863) |
| Числа-регуляторы | `STATE.tax`, `STATE.pReg`, `STATE.quota`, `STATE.natFC`, `STATE.laborMinW`, `STATE.unionWage` | |

В строках могут стоять буквы-параметры; значения лежат в `STATE.params` (выгрузка подставляет их числом, 70-scenes-math.js:1513).

### 0.4. Пометки для выгрузки: что есть сейчас

- В обоих файлах НЕТ ни одного `markExpr`, `data-expr`, `data-curve`, `data-numeric`, `data-skip-export`, `data-service`, `data-raw`, поставленного своим кодом (проверено поиском по файлам).
- Свои пометки: `data-legend` (26 мест в mono, 8 в labor); классы `axis-num` (mono 1101, 1104) и `coord-num` (mono 1140, 1143).
- Через помощников: `data-raw` и классы — у pointName, haloText, labelCurve, осьX/осьY; `data-marginal-tail` — у хвоста MR/MRL; `data-curve` — только у кривых списка из `drawCurves`.
- Следствие для legacy-выгрузки (`buildTexLegacy`, 70-scenes-math.js:1952): все кривые, нарисованные самими этими файлами, уходят таблицей точек, снятых с пикселей (ветка :2130–2155).

---

# Часть I. 42-scenes-mono.js

## I-A. Сцены, функции, панели

### Сцены

| Ключ сцены | Признаки в STATE | Вход в отрисовку | Панели и шкалы |
|---|---|---|---|
| `mono` | `mode='market'`, `market='monopoly'`, `monoMode='simple'` | `redrawScene`, 60-overlays.js:113–153 | 1 панель `main`: `sx`, `sy` из `makeScales()` (20-plane.js:141): домен [`CONFIG.Qmin`; `Qmax`] × [`Pmin`; `Pmax`], диапазон по `CONFIG.margin` и W×H |
| `mono-nat` | `monoMode='natural'` | 60-overlays.js:110–112 → `drawNaturalFull` (645) | `main` |
| `mono-d1` | `monoMode='discr1'` | 60-overlays.js:107–109 → `drawDiscr1` (946) | `main` |
| `mono-d3` | `monoMode='discr3'`, `d3World=false` | 60-overlays.js:99 → `redrawDiscr3` (1157); выход из `redrawScene` ДО `recompute()` | 2 панели `mini-1`, `mini-2` (подробно ниже); если оптимум не найден — пустые оси `main` (1168–1171) |
| `mono-kink` | `monoMode='kinked'` | 60-overlays.js:100 → `drawKinkedFull` (1496); тоже до `recompute()` | `main` |
| `monoexport` | `monoMode='discr3'`, `d3World=true` (84-picker.js:108) | `redrawDiscr3` (1162) → `drawMonoExport` (1200) | `main`; сцена сама ставит окно `applyAutoRanges(padMax(qWant), padMax(pWant))` и заново зовёт `makeScales()` (1226–1231) |

Перед сценами `mono`, `mono-nat`, `mono-d1` общий код рисует: `addDefs` → `drawGrid` → `drawAxes()` (оси Q, P; 60-overlays.js:104–106). `mono-kink` и `monoexport` зовут эти три функции сами (1499, 1234). `mono-d3` зовёт только `addDefs` (1164); сетку и оси каждой панели рисует `drawMiniMarket` (1073, 1077–1078).

### Порядок вызовов в `mono` (слои снизу вверх; 60-overlays.js:113–153)

| Состояние | Порядок |
|---|---|
| `STATE.monoCeil.binding` (потолок связывает) | `drawMonoCeilingAreas` → `drawCurves` → `drawMonopoly` → `drawMonoKinkedMR` → `drawMonoCeilingPoints` → `drawMonoCeilingLine` |
| `STATE.monoTax` (налог либо субсидия, ставка > 0) | `drawMonoTaxAreas` → `drawCurves` → `drawMonopoly` → `drawMonoTaxShiftedMC` → `drawMonoTaxPoints` |
| `STATE.monoFloor.binding` | `drawMonoFloorAreas` → `drawCurves` → `drawMonopoly` → `drawMonoFloorPoints` → `drawMonoFloorLine` |
| `STATE.monoQuota.binding` | `drawMonoQuotaAreas` → `drawCurves` → `drawMonopoly` → `drawMonoQuotaPoints` → `drawMonoQuotaLine` |
| иначе | `drawMonopolyAreas` → `drawCurves` → `drawMonopoly` → `drawMonopolyPoints` → одна из линий регулятора, если он задан, но не связывает (`drawMonoCeilingLine` / `drawMonoFloorLine` / `drawMonoQuotaLine`) |

Результаты расчёта, из которых берутся числа: `STATE.mono {Qm, Pm, mcAtQm, Qc, Pc, …}` (40-scenes-market.js:351), `STATE.monoCeil {binding, Qstar, price, Qhat, shortage, Pc}` (42:266), `STATE.monoTax {isTax, shift, Qt, Pt, …}` (42:383), `STATE.monoFloor {binding, Pf, Q, price}` (42:400), `STATE.monoQuota {binding, Qk, Q, price}` (42:453), `STATE.natural {Qm, Pm, atcAtQm, profit, mcReg{Q,P,atc,subsidy}, acReg{Q,P,atc}}` (42:578), `STATE.discr1 {Qcomp, profit}` (40-scenes-market.js:398), `STATE.discr3 {c1, c2, cm, found, Qtot, q1, q2, P1, P2, mcLevel}` либо `{found:false, unbounded:{Pw, q1, P1}}` (42:1043, 1048), `STATE.kinked {segs, kinks, Dfn, mcCurve, found, Qstar, Pstar, Qc, …}` (42:1491).

### Функции рисования

| Функция (строки) | Рисует | Когда |
|---|---|---|
| `drawMonopolyAreas` (64–96) | CS, PS, VC до Qm; DWL от Qm до Qc | `mono`, нет связывающего вмешательства |
| `drawMonopoly` (99–116) | MR; MC, выведенную из TC | `mono`, все пять веток |
| `drawMonopolyPoints` (119–153) | M, точка MR=MC, ориентир «К», проекции, отметки | `mono`, нет связывающего |
| `drawMonoCeilingAreas` (270–286) | CS, PS, VC до Qstar; DWL | потолок связывает |
| `drawMonoKinkedMR` (289–303) | ломаный MRэфф: полка, обрыв, подпись | потолок связывает |
| `drawMonoCeilingPoints` (306–334) | M, призрак M₀, отрезок и надпись дефицита | потолок связывает |
| `drawMonoCeilingLine` (338–350) | линия потолка с ручкой | `intervType='ceiling'` и `pRegSet` |
| `drawMonoQuotaAreas` (457–476) | CS, PS, VC до Qk; DWL | квота связывает |
| `drawMonoQuotaPoints` (479–496) | M, призрак M₀ | квота связывает |
| `drawMonoQuotaLine` (501–507) | вертикаль квоты | `intervType='quota'` и `quotaSet` |
| `drawNaturalAreas` (582–594) | прямоугольники прибыли и убытка | `mono-nat` |
| `drawNaturalCurves` (597–612) | MR, ATC, подпись ATC | `mono-nat` |
| `drawNaturalPoints` (616–642) | три ориентира M, E_ATC, E_MC | `mono-nat` |
| `drawNaturalFull` (645–650) | порядок: области → `drawCurves` → кривые → точки | `mono-nat` |
| `drawMonoTaxAreas` (691–722) | VC, PS, CS, полоса бюджета, DWL | `STATE.monoTax` |
| `drawMonoTaxShiftedMC` (725–737) | MC ± ставка, подпись | `STATE.monoTax` |
| `drawMonoTaxPoints` (740–758) | M, призрак M₀ | `STATE.monoTax` |
| `drawMonoFloorAreas` (761–773) | CS, PS, VC до Q; DWL | пол связывает |
| `drawMonoFloorPoints` (776–793) | M, призрак M₀ | пол связывает |
| `drawMonoFloorLine` (796–808) | линия пола с ручкой | `intervType='floor'` и `pRegSet` |
| `drawDiscr1` (946–972) | D и MC из списка, MC из TC, область прибыли, точка, подпись | `mono-d1` |
| `drawMiniMarket` (1052–1154) | одна мини-панель: сетка, оси, заголовок, D, MR, MC, точка, отметки | `mono-d3`, два вызова |
| `redrawDiscr3` (1157–1180) | две мини-панели и разделитель; при `d3World` уходит в `drawMonoExport` | `mono-d3`, `monoexport` |
| `drawMonoExport` (1200–1321) | один график: D, MR, MC, Pw, три отметки, отрезок экспорта | `monoexport` |
| `drawKinkedFull` (1496–1571) | области, ломаный D, MR по кускам, разрывы MR, MC, точка M | `mono-kink` |

Не рисуют на холсте (расчёт, табло HTML, переключатели): `mcSourceCurve` 11, `mcSourceCurveAny` 15, `mcAt` 20, `mcFloor` 51, `marginalRevenue` 55, `updateMonoPanel` 156, `setMarket` 187, `monopolyCeiling` 222, `monopolyTax` 362, `monopolyFloor` 387, `monopolyQuota` 429, `naturalATC` 527, `findRootLast` 538, `recomputeNatural` 553, `updateNaturalPanel` 653, `updateMonoInterventionPanel` 811, `makeCurve` 937, `updateDiscr1Panel` 974, `allocateMR` 999, `recomputeDiscr3` 1012, `updateDiscr3Panel` 1323, `applyD3WorldLabels` 1386, `buildKinkedDemand` 1409, `recomputeKinked` 1456, `updateKinkPanel` 1573, `applyMonoVisibility` 1602, `ensureMonopolyCurves` 1623, `fillIfEmpty` 1634, `ensureD3Fields` 1637, `ensureKinkFields` 1642, `ensureMonopolyPreset` 1648, `setMonoMode` 1655, `setKinkInput` 1666.

### Мини-панели `mono-d3`: как создаются шкалы (1052–1071, 1167–1176)

- Пиксельные рамки: `gxLeft = 64`, `midX = gxLeft + (W − gxLeft)/2` (1167); панель 1 — полоса [64; midX], панель 2 — [midX; W].
- Поля внутри полосы: `ml=46, mr=18, mt=64, mb=42` (1055); `left = gx0+46`, `right = gx1−18`, `top = 64`, `bottom = H−42` (1056).
- Окно по умолчанию: `Xmax = padMax(invCurve(D,0) либо CONFIG.Qmax)`, `Ymax = padMax(evalCurve(D,0) либо CONFIG.Pmax)` (1058–1059). Затем `wnd = panelWin('mini-'+idx, 0, Xmax, 0, Ymax)` (1065): если человек крутил колесо над панелью, берётся его окно из `STATE.panelWin`.
- Шкалы: `lx = scaleLinear().domain([wnd.x0, wnd.x1]).range([left, right])`, `ly = …domain([wnd.y0, wnd.y1]).range([bottom, top])` (1067–1068).
- Регистрация: `registerPanel('mini-'+idx, lx, ly, {x0:left, y0:top, x1:right, y1:bottom})` (1071). Панель `main` перед этим снята `clearPanels()` (1174); глобальные `sx`, `sy` при этом остаются шкалами всего холста.
- Обратно в `Xmax` записывается только `wnd.x1` (1066); `Ymax` остаётся расчётным — деления оси P (1102–1104) считаются от него, даже если окно панели изменено человеком.

### Что слой поверх сцены знает о кривых этих сцен (`snapTargetsAll`, 60-overlays.js:3659)

| Сцена | Кривые в списке | Чего в списке нет |
|---|---|---|
| `mono`, `mono-nat`, `mono-d1` | видимые кривые `STATE.curves` (:3765) | MR, MC из TC, MC±ставка, ATC |
| `mono-d3` | D₁, MC₁ (панель `mini-1`), D₂, MC₂ (`mini-2`) (:3695–3698) | MR обеих панелей |
| `monoexport` | «D внутри», MC (:3690–3691) | MR, линия Pw |
| `mono-kink` | D (`k.Dfn`), MC (:3757–3758) | MR по кускам |

---

## I-B. Опись мест рисования

Во всех функциях, кроме `drawMiniMarket`, перевод в пиксели идёт глобальными `sx`, `sy` (панель `main`); это указано один раз в заголовке каждой таблицы. Обозначения источника геометрии: **(а)** строка Math.js; **(б)** только JS-функция, закрытая запись существует; **(б✗)** только JS-функция, общей закрытой записи нет; **(г)** отдельные числа.

### `drawMonopolyAreas` 64–96 · шкалы sx/sy · группа 67 с clip `#plot-clip`

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 75 | область VC | 101 узел на [0; `m.Qm`]; низ 0; верх MC⁺(q) | `STATE.showMonoVC`, Qm > 0 | `data-legend`=«Переменные издержки (VC)» | VC |
| 79 | область PS | те же узлы; низ MC⁺(q); верх `m.Pm` | `showMonoPS` | «Излишек производителя (TR - VC)» | PS |
| 83 | область CS | те же узлы; низ `m.Pm`; верх D(q) | `showMonoCS` | «Излишек покупателя (CS)» | CS |
| 93 | область DWL | 101 узел на [min(Qm,Qc); max(Qm,Qc)]; низ MC⁺; верх D | `m.Qc` найден (галочки нет) | «Потери общества (DWL)» | DWL |

### `drawMonopoly` 99–116 · sx/sy · группа 101 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 110 | кривая MR (drawMarginalCurve) | **(б)** q → `marginalRevenue(STATE.D, q)`: центральная разность d(D·q)/dq, шаг h = max(1e-4, Qmax·1e-5) (55–61). Закрытая запись: производная от Q·(`D.expr`); для прямой D = b + aQ это b + 2aQ. 401 узел на [0; max(`CONFIG.Qmax`, ноль D)] | `STATE.mono` | у хвоста `data-marginal-tail`; `data-expr` нет | `COL.MR`, 2, «6 4»; хвост 1.1, opacity .45 |
| 113 | кривая MC, выведенная из TC | **(б)** `mcAt` = центральная разность TC (кривая списка роли `tc`, строка `expr` есть). Закрытая запись: производная `TC.expr`. 401 узел на [0; `CONFIG.Qmax`]; NaN даёт разрыв | нет кривой `mc`/`supply`, но есть `tc` | нет | `COL.S`, 2.5, сплошная |

### `drawMonopolyPoints` 119–153 · sx/sy · группа 123 без clip · `dash` 126

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 133 | точка-ориентир «К» | (г) (`m.Qc`; `m.Pc`), Pc = MC(Qc) | `STATE.showGhost`, Qc найден | нет | Призрак |
| 135 | подпись точки «К» | там же, сдвиг +7 / +13 px | то же | нет | Тголый, fill `COL.inkSoft` |
| 138 | отметка у оси Q | `fmt(m.Qc)`, индекс `c` | то же | coord-num, data-raw | осьX |
| 142 | проекция вертикальная | (Qm; 0) – (Qm; Pm) | `STATE.mono` | нет | П |
| 143 | проекция горизонтальная | (0; Pm) – (Qm; Pm) | | нет | П |
| 145 | точка MR = MC | (`m.Qm`; `m.mcAtQm`) — MC без обрезки нулём | | нет | r 3.5, fill `COL.MR`, stroke halo 1.2 |
| 148 | точка M | (Qm; Pm) | | нет | ТчкM |
| 150 | подпись точки «M» | там же | | point-name, data-raw | pointName |
| 151 | отметка у оси Q | `fmt(m.Qm)`, индекс `m` | | coord-num, data-raw | осьX |
| 152 | отметка у оси P | `fmt(m.Pm)`, индекс `m` | | coord-num, data-raw | осьY |

### `drawMonoCeilingAreas` 270–286 · sx/sy · группа 273 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 278 | область VC | 101 узел на [0; `mc.Qstar`]; 0 … MC⁺ | `showMonoVC`, Qstar > 1e-6 | «Переменные издержки (VC)» | VC |
| 279 | область PS | MC⁺ … `mc.price` | `showMonoPS` | «Излишек производителя (TR - VC)» | PS |
| 280 | область CS | `mc.price` … D | `showMonoCS` | «Излишек покупателя (CS)» | CS |
| 284 | область DWL | 101 узел на [min(Qstar,Qc); max]; MC⁺ … D | Qc найден | «Потери общества (DWL)» | DWL |

### `drawMonoKinkedMR` 289–303 · sx/sy · группа 292 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 294 | отрезок: полка MRэфф | (г) (0; `mc.Pc`) – (`mc.Qhat`; Pc); Qhat = `invCurve(D, Pc)` | потолок связывает, Qhat найден | нет | `COL.MR`, 3, «2 2» |
| 298 | отрезок вертикальный: обрыв MRэфф | (Qhat; Pc) – (Qhat; max(0, MR(Qhat))), MR численно | MR(Qhat) не NaN | нет | `COL.MR`, 1.5, «2 2», opacity .6 |
| 301 | подпись «MRэфф = Pc» | x = 0.4·Qhat, y = Pc, сдвиг −5 px | | нет | Тголый, fill `COL.MR` |

### `drawMonoCeilingPoints` 306–334 · sx/sy · группа 309 · `dash` 310

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 315 | призрак M₀ | (`m.Qm`; `m.Pm`) | `showGhost` | нет | Призрак |
| 316 | подпись «M₀» | там же, +7 / −6 px | `showGhost` | нет | Тголый, `COL.inkSoft` |
| 322 | проекция вертикальная | (Qstar; 0) – (Qstar; price) | Qstar > 1e-6 | нет | П |
| 322 | проекция горизонтальная | (0; price) – (Qstar; price) | то же | нет | П |
| 323 | точка M | (`mc.Qstar`; `mc.price`) | то же | нет | ТчкM |
| 324 | подпись «M» | | то же | point-name, data-raw | pointName |
| 325 | отметка у оси Q | `fmt(mc.Qstar)`, без индекса | то же | coord-num | осьX |
| 330 | отрезок-скобка «дефицит» на оси Q | (min(Qstar,Qhat); 0) – (max; 0) | `mc.shortage` > 1e-6 | нет | `COL.bad`, 5, opacity .5 |
| 331 | отметка у оси Q | `fmt(mc.Qhat)`, индекс `d` | то же | coord-num | осьX |
| 332 | индикатор под осью «Дефицит = N» | середина отрезка; y = sy(0) + 24 px | то же | data-raw | haloText middle / hanging |

Отметки цены у точки M здесь нет: уровень потолка печатает `drawMonoCeilingLine` (344).

### `drawMonoCeilingLine` 338–350 · sx/sy · группа 341

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 342 | линия потолка (уровень через весь кадр) | (0; `STATE.pReg`) – (`CONFIG.Qmax`; pReg) | `intervType='ceiling'`, `pRegSet` | нет | `COL.reg`, 2.5 |
| 344 | отметка у оси P | `fmt(STATE.pReg)`, индекс `c` | | coord-num | осьY |
| 345 | служебное: прозрачная полоса захвата, d3.drag → `setPReg(sy.invert(y))` (`attachPcDrag`, 347) | x от 0 до Qmax; y = pReg ± 12 px | | нет | `rect`, fill transparent |
| 348 | ручка | (0.72·`CONFIG.Qmax`; pReg) | | после кадра: `data-service="handle"`, `data-skip-export` | r 7, fill `COL.reg`, stroke halo 2 |

### `drawMonoQuotaAreas` 457–476 · sx/sy · группа 460 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 464 | область VC | 101 узел на [0; `qt.Q`]; 0 … MC⁺ | `showMonoVC`, Q > 1e-6 | «Переменные издержки (VC)» | VC |
| 465 | область PS | MC⁺ … `qt.price` | `showMonoPS` | «Излишек производителя (TR - VC)» | PS |
| 466 | область CS | `qt.price` … D | `showMonoCS` | «Излишек покупателя (CS)» | CS |
| 473 | область DWL | 101 узел на [min(Q,Qc); max]; MC⁺ … D | Qc найден | «Потери общества (DWL)» | DWL |

### `drawMonoQuotaPoints` 479–496 · sx/sy · группа 482 · `dash` 483

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 486 | призрак M₀ | (`m.Qm`; `m.Pm`) | `showGhost` | нет | Призрак |
| 487 | подпись «M₀» | +7 / −6 px | `showGhost` | нет | Тголый |
| 491 | проекция горизонтальная | (0; price) – (Q; price); вертикальной нет | Q > 1e-6 | нет | П |
| 492 | точка M | (`qt.Q`; `qt.price` = D(Qk)) | то же | нет | ТчкM |
| 493 | подпись «M» | | то же | point-name | pointName |
| 494 | отметка у оси P | `fmt(qt.price)`, без индекса | то же | coord-num | осьY |

### `drawMonoQuotaLine` 501–507 · sx/sy · группа 503

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 504 | вертикальная линия квоты | (`STATE.quota`; 0) – (quota; `CONFIG.Pmax`) | `intervType='quota'`, `quotaSet` | нет | `COL.reg`, 2.5; ручки и захвата нет |
| 506 | отметка у оси Q | `fmt(STATE.quota)`, индекс «к» (кириллица, U+043A) | | coord-num | осьX |

### `drawNaturalAreas` 582–594 · sx/sy · группа 584 с clip · помощник `rect` 585–590

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 587 (вызов 591) | область «прибыль монополии», прямоугольник | (г) x ∈ [0; `n.Qm`], y ∈ [`n.atcAtQm`; `n.Pm`] | `STATE.showNatProfit`, profit > 0 | `data-legend` НЕТ | `rect`, fill `COL.tax`, opacity .20 |
| 587 (вызов 592–593) | область «убыток при P = MC», прямоугольник | (г) x ∈ [0; `n.mcReg.Q`], y ∈ [`n.mcReg.P`; `n.mcReg.atc`] | `STATE.showNatLoss`, subsidy > 0 | `data-legend` НЕТ | `rect`, fill `COL.bad`, opacity .18 |

### `drawNaturalCurves` 597–612 · sx/sy · группа 599 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 606 | кривая MR (drawMarginalCurve) | как в строке 110; сверху отсечка `cap` = 4·`CONFIG.Pmax` | `STATE.D` | хвост `data-marginal-tail` | `COL.MR`, 2, «6 4» |
| 607 | кривая ATC | **(б✗)** `naturalATC(q)` = (`STATE.natFC` + ∫₀^q max(0, MC)) / q; интеграл трапециями, 400 шагов на каждую точку (527–534). 401 узел на [0.005·Qmax; Qmax]; значения NaN и больше 4·Pmax дают разрыв (603). Строки нет; закрытая запись есть только для частных MC (MC = c даёт FC/Q + c) | | нет | `COL.reg`, 2.5, сплошная |
| 611 | подпись кривой «ATC» | labelCurve по `naturalATC`, поиск якоря с 0.93 ширины окна | | curve-name, data-raw | labelCurve, `COL.reg` |

MC, выведенная из TC, в этой сцене не рисуется вовсе (ветки, как в строке 113, здесь нет).

### `drawNaturalPoints` 616–642 · sx/sy · группа 618 · помощник `mark` 619–638

Три вызова: 639 — M (`n.Qm`; `n.Pm`), цвет `COL.ink`, индекс `m`; 640 — E_ATC (`n.acReg.Q`; `n.acReg.P`), `COL.reg`, индекс `ATC` (если `acReg`); 641 — E_MC (`n.mcReg.Q`; `n.mcReg.P`), `COL.MC`, индекс `MC` (если `mcReg`).

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 622 | проекция вертикальная | (Q; 0) – (Q; P) | Q > 0, P не NaN | нет | цвет точки, 1.2, «4 3», opacity .85 |
| 624 | проекция горизонтальная | (0; P) – (Q; P) | | нет | цвет точки, 1, «4 3», opacity .55 |
| 626 | точка-ориентир | (Q; P) | | нет | r 4.5, fill цвет точки, stroke halo 1.5 |
| 630 | подпись точки «M» / «E_{ATC}» / «E_{MC}» | сдвиг ±9 / −9 px, anchor end либо start | | point-name, data-raw | pointName, `FS.base`, 700 |
| 633 | отметка у оси Q | `fmt(Q)`, индекс | | coord-num | осьX |
| 637 | отметка у оси P | `fmt(P)`, индекс | | coord-num | осьY |

### `drawNaturalFull` 645–650

Строка 647: `drawCurves()` — D и MC (и любые другие видимые кривые списка) общим рисователем.

### `drawMonoTaxAreas` 691–722 · sx/sy · группа 694 с clip · `mcEff(q) = mcAt(q) + t.shift` (696)

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 702 | область VC | 101 узел на [0; `t.Qt`]; 0 … MC⁺ (социальная MC, без ставки) | `showMonoVC`, Qt > 1e-6 | «Переменные издержки (VC)» | VC |
| 707 | область PS | max(0, mcEff) … `t.Pt` | `showMonoPS` | «Излишек производителя (TR - VC)» | PS |
| 711 | область CS | `t.Pt` … D | `showMonoCS` | «Излишек покупателя (CS)» | CS |
| 715 | область «деньги бюджета» | MC⁺ … max(0, mcEff); при субсидии полоса лежит ниже MC | Qt > 1e-6 (галочки нет) | «Сбор бюджета» либо «Расход бюджета» (по `STATE.intervType`) | бюджет |
| 720 | область DWL | 101 узел на [min(Qt,Qc); max]; MC⁺ … D | Qc найден | «Потери общества (DWL)» | DWL |

### `drawMonoTaxShiftedMC` 725–737 · sx/sy · группа 728 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 732 | кривая MC ± ставка | **(б)** q → `mcAt(q) + t.shift`. Закрытая запись: (`MC.expr`) ± `STATE.tax`, если MC — кривая списка; иначе производная `TC.expr` ± ставка. 401 узел на [0; Qmax] | `STATE.monoTax` | нет | `COL.MC`, 2, «6 4» |
| 735 | подпись «MC+t» либо «MC−s» | x = 0.62·`CONFIG.Qmax`, y = MC(x) + shift, сдвиг −6 px | значение в точке > 0 | нет | Тголый, fill `COL.MC` |

### `drawMonoTaxPoints` 740–758 · sx/sy · группа 743 · `dash` 744

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 747 | призрак M₀ | (`m.Qm`; `m.Pm`) | `showGhost` | нет | Призрак |
| 748 | подпись «M₀» | +7 / −6 px | `showGhost` | нет | Тголый |
| 752 | проекция вертикальная | (Qt; 0) – (Qt; Pt) | Qt > 1e-6 | нет | П |
| 752 | проекция горизонтальная | (0; Pt) – (Qt; Pt) | то же | нет | П |
| 753 | точка M | (`t.Qt`; `t.Pt`) | то же | нет | ТчкM |
| 754 | подпись «M» | | то же | point-name | pointName |
| 755 | отметка у оси Q | `fmt(t.Qt)`, без индекса | то же | coord-num | осьX |
| 756 | отметка у оси P | `fmt(t.Pt)`, без индекса | то же | coord-num | осьY |

### `drawMonoFloorAreas` 761–773 · sx/sy · группа 764 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 768 | область VC | 101 узел на [0; `fl.Q`]; 0 … MC⁺ | `showMonoVC`, Q > 1e-6 | «Переменные издержки (VC)» | VC |
| 769 | область PS | MC⁺ … `fl.price` | `showMonoPS` | «Излишек производителя (TR - VC)» | PS |
| 770 | область CS | `fl.price` … D | `showMonoCS` | «Излишек покупателя (CS)» | CS |
| 772 | область DWL | 101 узел на [min(Q,Qc); max]; MC⁺ … D | Qc найден | «Потери общества (DWL)» | DWL |

### `drawMonoFloorPoints` 776–793 · sx/sy · группа 779 · `dash` 780

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 783 | призрак M₀ | (`m.Qm`; `m.Pm`) | `showGhost` | нет | Призрак |
| 784 | подпись «M₀» | +7 / −6 px | `showGhost` | нет | Тголый |
| 788 | проекция вертикальная | (Q; 0) – (Q; price) | Q > 1e-6 | нет | П |
| 788 | проекция горизонтальная | (0; price) – (Q; price) | то же | нет | П |
| 789 | точка M | (`fl.Q`; `fl.price` = Pf) | то же | нет | ТчкM |
| 790 | подпись «M» | | то же | point-name | pointName |
| 791 | отметка у оси Q | `fmt(fl.Q)`, без индекса | то же | coord-num | осьX |

### `drawMonoFloorLine` 796–808 · sx/sy · группа 799

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 800 | линия пола (уровень через весь кадр) | (0; `STATE.pReg`) – (`CONFIG.Qmax`; pReg) | `intervType='floor'`, `pRegSet` | нет | `COL.MR`, 2.5 |
| 802 | отметка у оси P | `fmt(STATE.pReg)`, индекс `f` | | coord-num | осьY |
| 803 | служебное: полоса захвата, d3.drag (`attachPcDrag`, 805) | y = pReg ± 12 px | | нет | `rect`, transparent |
| 806 | ручка | (0.72·Qmax; pReg) | | после кадра: `data-service`, `data-skip-export` | r 7, fill `COL.MR`, stroke halo 2 |

### `drawDiscr1` 946–972 · sx/sy · 948: `drawCurves()` · группа 949 с clip, группа 967 без clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 954 | кривая MC, выведенная из TC | как в строке 113 | нет `mc`/`supply`, есть `tc` | нет | `COL.S`, 2.5 |
| 964 | область «прибыль = весь излишек» | 121 узел на [0; `d1.Qcomp`]; низ MC⁺; верх D | `STATE.discr1` | «Излишек фирмы: весь излишек рынка» | fill `COL.tax`, opacity .20 |
| 968 | проекция вертикальная | (Qcomp; D(Qcomp)) – (Qcomp; 0) | то же | нет | П |
| 969 | точка | (Qcomp; D(Qcomp)) | то же | нет | r 4, fill `COL.tax`, stroke halo 1.5 |
| 970 | отметка у оси Q | `fmt(d1.Qcomp)`, индекс `comp` | то же | coord-num | осьX |
| 971 | подпись области «Прибыль» | x = 0.45·Qcomp; y = max(0, (D(Qcomp) + MC(0.45·Qcomp)) / 2) | то же | data-raw | haloText middle / middle |

### `drawMiniMarket` 1052–1154 · шкалы СВОИ: `lx`, `ly` панели `mini-idx`

Вызовы: 1175 — idx 1, D = `d.c1`, точка (`d.q1`; `d.P1`), заголовок «Рынок 1»; 1176 — idx 2, D = `d.c2`, (`d.q2`; `d.P2`), «Рынок 2». MC = `d.cm` в обеих.

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 1072 | служебное: группа панели | | | | |
| 1073 | сетка панели, `drawGrid(lx, ly, g)` | деления `axisTicks` по `lx`, `ly` | `STATE.showGrid` | `g.grid` | `COL.grid`, 1 |
| 1075 | служебное: `clipPath#mini-clip-idx` с прямоугольником панели | | | | |
| 1077 | ось Q панели | (wnd.x0; wnd.y0) – (wnd.x1; wnd.y0) | | класса `axes` нет | `COL.ink`, 1.5, стрелка `#arrow` |
| 1078 | ось P панели | (wnd.x0; wnd.y0) – (wnd.x0; wnd.y1) | | класса `axes` нет | то же |
| 1083 | заголовок панели «Рынок 1» / «Рынок 2» | только пиксели: x = середина панели, зажатая в холст по измеренной ширине (1081–1082); y = top − 12 | | нет | `.text()`, `FS.base`, 600, `COL.ink`, без ореола |
| 1084 | имя оси «Q» | пиксели (right + 4; bottom + 4) | | класса `axis-name` нет | `.text()`, `FS.base`, `COL.inkSoft` |
| 1085 | имя оси «P» | пиксели (left − 4; top − 2), anchor end | | нет | то же |
| 1101 | деления оси Q (числа) | q = Xmax·{0.25, 0.5, 0.75, 1}; y = bottom + 12 px; деление пропускается, если оно ближе 0.1·Xmax к `qi` | | класс `axis-num` | `FS.small`, `COL.inkSoft` |
| 1104 | деления оси P (числа) | p = Ymax·{0.25 … 1}; x = left − 5 px; пропуск рядом с `Pi` | | класс `axis-num` | то же |
| 1105 | служебное: группа кривых с clip `mini-clip-idx` | | | | |
| 1108 | кривая D рынка | **(а)** строка `STATE.d3D1` (idx 1) либо `STATE.d3D2` (idx 2). 301 узел на [0; Xmax]; значения < 0 и NaN дают разрыв | | нет | `COL.D`, 2.5 |
| 1109 | кривая MR рынка | **(б)** `marginalRevenue(D, q)` численно; закрытая запись: производная Q·(`d3D1` либо `d3D2`). 301 узел; значения < 0 дают разрыв (хвоста ниже оси нет) | | нет | `COL.MR`, 2, «6 4» |
| 1110 | кривая MC | **(а)** строка `STATE.d3MC`; 301 узел; аргумент — собственное q панели | | нет | `COL.S`, 2 |
| 1113 | проекция вертикальная | (qi; Pi) – (qi; нижний край панели) | qi > 0, Pi не NaN | нет | П |
| 1114 | проекция горизонтальная | (qi; Pi) – (левый край панели; Pi) | то же | нет | П |
| 1115 | точка оптимума рынка | (qi; Pi) | то же | нет | ТчкM |
| 1139 | отметка у оси Q панели | `fmt(qi)`; пиксели (lx(qi); bottom + 12) | то же | класс `coord-num` (1140), data-raw | haloText, fill `--accent`, 700 |
| 1142 | отметка у оси P панели | `fmt(Pi)`; пиксели (left − 5; ly(Pi)) | то же | класс `coord-num` (1143), data-raw | то же |
| 1151–1152 | служебное невидимое: `noteAxisX`, `noteAxisY` с панелью `mini-idx` | | то же | | |

Подписей кривых (D, MR, MC) и имени точки в мини-панели нет.

### `redrawDiscr3` 1157–1180

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 1178 | разделитель панелей (служебная линия) | данных нет; пиксели (midX; 52) – (midX; H − 30) | оптимум найден | нет | `COL.grid`, 1 |

### `drawMonoExport` 1200–1321 · sx/sy (после своего `makeScales`, 1231) · группы: 1235 (clip), 1258, 1268 · `dash` 1269

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 1246 | кривая D (внутренний спрос) | **(а)** `STATE.d3D1`; 401 узел на [0; `CONFIG.Qmax`]; значения < 0 дают разрыв | `d.found` либо `d.unbounded` | нет | `COL.D`, 2.5 |
| 1250 | кривая MR (drawMarginalCurve) | **(б)** как в строке 110, от `d.c1`; закрытая запись: производная Q·(`d3D1`) | то же | хвост `data-marginal-tail` | `COL.MR`, 2, «6 4» |
| 1252 | кривая MC от общего выпуска | **(а)** `STATE.d3MC`; 401 узел | то же | нет | `COL.S`, 2.5 |
| 1259 | линия мировой цены Pw | (0; Pw) – (`CONFIG.Qmax`; Pw); Pw = значение `STATE.d3D2` в нуле (1212) либо `u.Pw` | то же | нет | `COL.reg`, 2.5 |
| 1261 | отметка у оси P | `fmt(Pw)`, индекс `w` | то же | coord-num | осьY |
| 1263 | подпись кривой «D» | labelCurve, ключ `mx-d` | то же | curve-name, data-raw | `COL.D` |
| 1264 | подпись кривой «MR» | labelCurve по численной MR, ключ `mx-mr`, под кривой | то же | curve-name | `COL.MR` |
| 1265 | подпись кривой «MC» | labelCurve, ключ `mx-mc` | то же | curve-name | `COL.S` |
| 1266 | подпись линии «P_w» | labelCurve по функции-константе Pw, ключ `mx-pw`, под линией | то же | curve-name | `COL.reg` |
| 1278 | проекция вертикальная | (q1; P1) – (q1; 0) | q1 > 1e-9, P1 конечна | нет | П |
| 1278 | проекция горизонтальная | (q1; P1) – (0; P1) | то же | нет | П |
| 1285 | точка на вертикали «MR сравнялся с альтернативой» | (q1; MR(q1)), MR численно | MR(q1) конечен | нет | r 3.5, fill `COL.MR`, stroke halo 1.2 |
| 1287 | точка M (внутренний оптимум) | (q1; P1) | то же, что 1278 | нет | ТчкM |
| 1289 | подпись «M» | | то же | point-name | pointName |
| 1290 | отметка у оси Q | `fmt(q1)`, индекс `1` | то же | coord-num | осьX |
| 1291 | отметка у оси P | `fmt(P1)`, индекс `1` | то же | coord-num | осьY |
| 1299 | проекция вертикальная | (Qtot; Pw) – (Qtot; 0) | `hasExport` (Qtot > q1 + 1e-6) | нет | П |
| 1300 | точка общего выпуска | (Qtot; Pw) | то же | нет | r 4.5, fill `COL.S`, stroke halo 1.5 |
| 1305 | отметка у оси Q | `fmt(Qtot)`, индекс «Σ» (U+03A3) | то же | coord-num | осьX |
| 1313 (вызовы 1317, 1318) | отрезок-скобка «экспорт» на линии Pw | (max(q1,0); Pw) – (Qtot; Pw); при неограниченном экспорте — до (`CONFIG.Qmax`; Pw). Рисуется, только если длиннее 1 px (1312) | `hasExport` либо `!d.found` | нет | `COL.S`, 6, opacity .45 |
| 1315 | индикатор «Экспорт = N» либо «Объём экспорта не ограничен» | середина отрезка; на 12 px ВЫШЕ линии Pw (внутри поля, не под осью) | то же | data-raw | haloText middle / auto |

### `drawKinkedFull` 1496–1571 · sx/sy · группы 1502 (clip), 1562 · `dash` 1563

`mcK(q) = evalCurve(k.mcCurve, q)` (1508). Узлы заливок даёт `sampK` (1509–1516): отрезок режется по изломам `k.kinks`, на каждый кусок 60 шагов, плюс конечная точка.

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 1521 | область VC | узлы `sampK(0, k.Qstar)`; 0 … max(0, mcK) | `showMonoVC`, найден оптимум, Qstar > 1e-6 | «Переменные издержки (VC)» | VC |
| 1525 | область PS | max(0, mcK) … `k.Pstar` | `showMonoPS` | «Излишек производителя (TR - VC)» | PS |
| 1529 | область CS | `k.Pstar` … `k.Dfn` | `showMonoCS` | «Излишек покупателя (CS)» | CS |
| 1534 | область DWL | узлы `sampK(k.Qstar, k.Qc)`; max(0, mcK) … `k.Dfn` | Qc > Qstar | «Потери общества (DWL)» | DWL |
| 1539 | кривая D (ломаный спрос) | `k.Dfn`, см. I-E п. 2. 401 узел равномерной сетки на [0; `CONFIG.Qmax`] (изломы в узлы не попадают); значения < 0 дают разрыв | `STATE.kinked` | нет | `COL.D`, 2.5 |
| 1546 | кривая MR по кускам (drawMarginalCurve на каждый `k.segs[i]`, от `q0` до `q1`, 201 узел) | **(б)** `marginalRevenue(s.D, q)` численно; для линейного куска {a, b} закрытая запись 2a·Q + b. Хвост ниже оси только у последнего куска | то же | хвост `data-marginal-tail` | `COL.MR`, 2, «6 4» |
| 1553 | отрезок вертикальный: разрыв MR в каждом изломе | (qk; max(0, MR слева)) – (qk; max(0, MR справа)) | есть оба соседних куска | нет | `COL.MR`, 1.3, «2 2», opacity .6 |
| 1559 | кривая MC | **(а)** `STATE.kinkMC`; 401 узел | то же | нет | `COL.S`, 2.5 |
| 1564 | проекция вертикальная | (Qstar; Pstar) – (Qstar; 0) | оптимум найден | нет | П |
| 1564 | проекция горизонтальная | (Qstar; Pstar) – (0; Pstar) | то же | нет | П |
| 1565 | точка M | (`k.Qstar`; `k.Pstar`) | то же | нет | ТчкM |
| 1566 | подпись «M» | | то же | point-name | pointName |
| 1567 | отметка у оси Q | `fmt(k.Qstar)`, без индекса | то же | coord-num | осьX |
| 1568 | отметка у оси P | `fmt(k.Pstar)`, без индекса | то же | coord-num | осьY |

Подписей кривых D, MR, MC в сцене нет.

---

## I-C. Области подробно

Способ построения один для всех криволинейных областей: `d3.area().x(d => sx(d)).y0(низ).y1(верх)` по массиву значений Q; интерполяции (`.curve`) и `.defined` нет, то есть контур — ломаная: верхняя граница слева направо, нижняя справа налево, замыкание. Все области лежат в группах с `clip-path: url(#plot-clip)` и рисуются раньше кривых.

| Область | Места | Отрезок по Q | Нижняя граница | Верхняя граница | Узлов | Стороны |
|---|---|---|---|---|---|---|
| VC | 75, 278, 464, 702, 768 | [0; Q*] | прямая P = 0 | max(0, MC(q)) | 101 | одна по кривой |
| PS | 79, 279, 465, 769 | [0; Q*] | max(0, MC(q)) | прямая P = цена | 101 | одна по кривой |
| PS при ставке | 707 | [0; Qt] | max(0, MC(q) + shift) | P = Pt | 101 | одна по кривой |
| CS | 83, 280, 466, 711, 770 | [0; Q*] | прямая P = цена | D(q) | 101 | одна по кривой |
| DWL | 93, 284, 473, 720, 772 | [min(Q*, Qc); max(Q*, Qc)] | max(0, MC(q)) | D(q) | 101 | две по кривым |
| деньги бюджета | 715 | [0; Qt] | max(0, MC(q)) | max(0, MC(q) + shift) | 101 | две по кривым (параллельные) |
| прибыль discr1 | 964 | [0; Qcomp] | max(0, MC(q)) | D(q) | 121 | две по кривым |
| VC, PS, CS ломаного спроса | 1521, 1525, 1529 | [0; Qstar] | как выше, MC = `kinkMC`, D = `k.Dfn` | | 60 на кусок + 1 | по кривой; изломы — узлы |
| DWL ломаного спроса | 1534 | [Qstar; Qc] | max(0, mcK) | `k.Dfn` | 60 на кусок + 1 | две по кривым |
| прибыль естественной монополии | 587 (591) | [0; Qm] | ATC(Qm) | Pm | `rect` | все прямые |
| убыток при P = MC | 587 (592–593) | [0; Qc] | P = MC(Qc) | ATC(Qc) | `rect` | все прямые |

Q* и цена по состояниям: без вмешательства — `m.Qm`, `m.Pm`; потолок — `mc.Qstar`, `mc.price`; квота — `qt.Q`, `qt.price`; ставка — `t.Qt`, `t.Pt`; пол — `fl.Q`, `fl.price`.

Точные вершины в координатах данных:

- Концы отрезков по Q и уровни цены хранятся числами в `STATE.mono / monoCeil / monoQuota / monoTax / monoFloor / natural / discr1 / kinked` (см. I-A). Значения кривых в концах (MC⁺(0), MC⁺(Q*), D(0), D(Q*)) отдельно не хранятся, вычисляются по функциям.
- Оба прямоугольника (587) заданы четырьмя числами точно.
- При линейных D и MC (пресет: D = 100 − Q, MC = 20) все криволинейные области — точные многоугольники, но рисуются всё равно 101 узлом.
- Нижняя граница max(0, MC) кусочная: если MC пересекает ноль внутри отрезка, излом в узел сетки не попадает (точность — один шаг Q*/100). У ломаного спроса изломы D в узлы попадают (правило `sampK`), излом max(0, MC) — нет.
- `mcFloor(NaN)` = 0, то есть там, где MC не считается, граница ложится на ось. Защиты от NaN у D нет: `sy(NaN)` попадёт в путь.
- У CS правая сторона вырождается в точку, когда цена лежит на спросе (без вмешательства, квота, ставка, пол: D(Q*) = цена). При потолке на плоской части D(Qstar) > Pc, справа остаётся вертикальный отрезок.

---

## I-D. Элементы у осей, под осью, на полях

| Элемент | Места | Как позиционируется |
|---|---|---|
| Отметка у оси Q (осьX) | 138, 151, 325, 331, 506, 633, 755, 791, 970, 1290, 1305, 1567 | x = sx(значение); y = sy(0) + 8 px; anchor middle, baseline hanging. После кадра `spreadLabels` может сдвинуть вниз |
| Отметка у оси P (осьY) | 152, 344, 494, 637, 756, 802, 1261, 1291, 1568 | x = sx(0) − 8 px; y = sy(значение); anchor end. `spreadLabels` прижимает к левому краю холста и может сдвинуть левее |
| Индексы отметок | | `c` (138, 344), `m` (151, 152, 639), `d` (331), «к» кириллицей (506), `ATC`, `MC` (640, 641), `comp` (970), `f` (802), `w` (1261), `1` (1290, 1291), «Σ» (1305); без индекса: 325, 494, 755, 756, 791, 1567, 1568. Текст собирает `axisValueText` (20-plane.js:883): `число_и` либо `число_{индекс}` |
| Отрезок дефицита на оси Q | 330 | по оси: от min(Qstar, Qhat) до max, y = sy(0) |
| Индикатор «Дефицит = N» | 332 | x = середина отрезка (px), y = sy(0) + 24 px; под него в полях холста заведена полоса `BOTTOM_BAND = 44` (20-plane.js:72) |
| Отрезок экспорта | 1313 | на линии Pw, от q1 до Qtot (либо до правого края окна) |
| Индикатор «Экспорт = N» | 1315 | середина отрезка, y = sy(Pw) − 12 px — внутри поля графика, не под осью |
| Ручки линий потолка и пола | 348, 806 | на линии уровня, x = 0.72·`CONFIG.Qmax` |
| Заголовки панелей «Рынок 1», «Рынок 2» | 1083 | только пиксели: над панелью, y = 64 − 12 = 52 px от верха холста; x зажимается по измеренной ширине текста |
| Имена осей мини-панели «Q», «P» | 1084, 1085 | пиксели от углов панели: (right + 4; bottom + 4) и (left − 4; top − 2) |
| Деления осей мини-панели | 1101, 1104 | четыре доли Xmax и Ymax; ниже оси на 12 px, левее оси на 5 px |
| Отметки точки в мини-панели | 1139, 1142 | там же, где деления: (lx(qi); bottom + 12), (left − 5; ly(Pi)); свои, мимо осьX/осьY |
| Разделитель панелей | 1178 | вертикаль x = midX от 52 px до H − 30 px |
| Подписи кривых у правого края | 611, 1263–1266 (и подписи кривых списка из `drawCurves`) | место ищет `curveAnchor` по окну; переворот у края по пикселям |

Заголовок графика, оси, деления и названия главных осей рисуют `drawGraphTitle` (60-overlays.js:3263) и `drawAxes` (20-plane.js:900) — вне этих файлов.

---

## I-E. Трудные случаи для записи формулой

1. **Кривые, которые считаются численно, хотя закрытая запись есть.** MR — 110, 606, 1109, 1250, 1546 (центральная разность, 55–61); MC из TC — 113, 954 (20–31); MC ± ставка — 732. Шаг разности h = max(1e-4, `CONFIG.Qmax`·1e-5) зависит от окна. Помощник символьной производной `derivativeExpr` существует (30-curves.js:265), но в этом файле не используется. Для MR нужна производная от Q·D(Q); у объектов `makeCurve` (d3, kink) поля `expr` нет — строка лежит только в `STATE.d3D1` и подобных.
2. **Ломаный спрос** (`buildKinkedDemand`, 1409–1453) — три разных происхождения одной кривой 1539:
   - суммируемые спросы, все линейные (1425–1443): точные вершины `bps` = (Q(P), P) при ценах-перехватах, куски `{q0, q1, D:{linear:{a,b}}}`, изломы в `k.kinks`; закрытая кусочно-линейная запись есть, строки нет;
   - суммируемые спросы, есть нелинейный (1444–1452): `Dfn(Q)` — бисекция по цене на [0; 4·`CONFIG.Pmax`] от суммы численно обращённых кривых; формулы нет вовсе, изломов нет;
   - два куска (1410–1420): строки `STATE.kpD1`, `STATE.kpD2`, стык `qk` найден численно (`findRoot`), куски [0; qk] и [qk; `CONFIG.Qmax`]; если стыка нет или он ≥ Qmax — один кусок.
   Сама линия D рисуется одним путём по равномерной сетке (1538), а заливки под ней — с изломами в узлах (1509–1516).
3. **Ломаный MR.** `mono-kink`: отдельный путь на каждый кусок (1544–1548) плюс вертикальные пунктиры разрыва (1549–1556); хвост ниже оси только у последнего куска. Потолок в `mono`: MRэфф — не кривая, а два отрезка (294, 298) и подпись (301) поверх обычного MR (110); концы обрыва зажаты `max(0, …)`.
4. **ATC естественной монополии** (607): интеграл max(0, MC) трапециями на каждую из 401 точки, начало с 0.005·Qmax, отсечка 4·Pmax. Общей закрытой записи нет.
5. **Вертикальные линии:** квота (504: от 0 до `CONFIG.Pmax`), обрыв MRэфф (298), разрывы MR (1553), все вертикальные проекции, оси и разделитель мини-панелей (1078, 1178).
6. **Две панели** (`mono-d3`): свои шкалы, свой clipPath, оси и деления вручную, отметки точки мимо осьX/осьY, заголовки и разделитель в чистых пикселях. MC в каждой панели построена как функция собственного q рынка (1110), тогда как оптимум считается по MC от суммарного выпуска (1018, 1024: `mc(Qtot)`); при непостоянной MC уровень MR(qi) = MC(Qtot) не совпадёт со значением нарисованной MC в точке qi — факт кода, задумано ли так, не знаю. Legacy-выгрузка берёт одну пару шкал на весь SVG (`mainScales()` без id, 70-scenes-math.js:1955) — по чтению кода, вторая панель переводится из пикселей чужими шкалами.
7. **Обрыв кривой у оси по сетке.** В 1107, 1241, 1538 значение < 0 превращается в `null`: линия кончается на последнем узле сетки перед осью, точное пересечение не досчитывается (у кривых списка его досчитывает `pointsFromNodes`, 30-curves.js:107).
8. **Хвост предельной кривой** (110, 606, 1250, 1546): отдельный путь другого вида, тянется до нуля породившего спроса, который ищется на [0; 4·Qmax] (30-curves.js:197) и может лежать правее окна.
9. **Зависимость от окна (не от пикселей):** сетки дискретизации идут от 0 до `CONFIG.Qmax` (105, 603, 731, 953, 1240, 1538, 1558) и не следуют за панорамой (`CONFIG.Qmin`); линии-уровни тянутся до `CONFIG.Qmax` (340, 798, 1257) и `CONFIG.Pmax` (504); места подписей — доли окна (734: 0.62·Qmax); ручки — 0.72·Qmax; пороги показа подписей зависят от окна (735: значение > 0). Модельные поиски тоже привязаны к окну: 249 (`CONFIG.Qmax`), 1024 и 1038 (2·Qmax), 1415–1418, 1447 (4·Pmax).
10. **Зависимость от размера холста в пикселях:** рамки мини-панелей (1055–1056, 1167), разделитель (1178), зажим заголовка (1081–1082); порог «отрезок экспорта длиннее 1 px» (1312); сдвиги подписей в px в каждом месте; `haloText` зажимает текст в W×H; `labelCurve` переворачивает подпись у края; осьX/осьY убирают деление по порогу 7 px; место легенды; проходы из 0.1.
11. **Кривые списка, введённые как Q = f(P):** у нелинейной P(Q) есть только численным обращением (`curve.fn`), строки P(Q) нет; D и MC сцен `mono`, `mono-nat`, `mono-d1` могут быть такими.
12. **Цепочка источников MC:** роль `mc` → роль `supply` → производная роли `tc` (11–31); от неё зависит, есть ли у MC строка.

---

## I-F. Итог по 42-scenes-mono.js (места в коде)

| Что | Сколько | Адреса |
|---|---|---|
| Кривые, которые рисует сам файл | **15** | 110, 113, 606, 607, 732, 954, 1108, 1109, 1110, 1246, 1250, 1252, 1539, 1546, 1559 |
| — со строкой-формулой в STATE | 5 | 1108, 1110, 1246, 1252, 1559 (строка есть, но путь не помечен) |
| — закрытая запись есть, строки нет | 7 | 110, 113, 606, 732, 954, 1109, 1250 |
| — зависит от способа ввода (кусочная закрытая либо численная) | 2 | 1539, 1546 |
| — численная без общей закрытой записи | 1 | 607 (ATC) |
| Вызовы общего `drawCurves()` | 2 в файле (+5 в 60-overlays.js для `mono`) | 647, 948 |
| Области | **27 мест, 28 фигур** | см. I-C |
| — прямые стороны всегда | 2 | оба прямоугольника из 587 |
| — граница по кривой | 26 | VC 6, PS 6, CS 6, DWL 6, бюджет 1, прибыль discr1 1 |
| Линии-проекции | **19** | 142, 143, 322×2, 491, 622, 624, 752×2, 788×2, 968, 1113, 1114, 1278×2, 1299, 1564×2 |
| Отрезки (не проекции) | **9** | уровни через кадр 342, 504, 800, 1259; скобки 330, 1313; части ломаных MR 294, 298, 1553 |
| Служебные линии | 3 | оси мини-панели 1077, 1078; разделитель 1178 |
| Точки | **18** | 133, 145, 148, 315, 323, 486, 492, 626, 747, 753, 783, 789, 969, 1115, 1285, 1287, 1300, 1565 |
| Подписи кривых, точек, областей | **21** | pointName 8 (150, 324, 493, 630, 754, 790, 1289, 1566); labelCurve 5 (611, 1263–1266); haloText 1 (971); голый `.text()` 7 (135, 301, 316, 487, 735, 748, 784) |
| Индикаторы | 2 | 332, 1315 |
| Надписи мини-панели | 3 | заголовок 1083; имена осей 1084, 1085 |
| Отметки у осей | **23** | осьX 12, осьY 9, свои в мини-панели 2 (1139, 1142) |
| Деления мини-панели | 2 места | 1101, 1104 |
| Строки легенды | своих мест нет | 26 элементов с `data-legend`, 7 разных ключей; одновременно до 5 строк (налог: VC, PS, CS, бюджет, DWL) |
| Ручки | **2** (+2 полосы захвата) | 348, 806 (полосы 345, 803) |
| Служебные группы, clipPath, реестр | 28 групп, 1 clipPath (1075), сетка панели (1073), `noteAxis` (1151–1152) | |

---

# Часть II. 46-scenes-labor.js

## II-A. Сцены, функции, панели

| Ключ сцены | Признаки в STATE | Панели и шкалы |
|---|---|---|
| `labor` | `mode='labor'`, `laborStruct='competition'` | 1 панель `main` |
| `labor-mono` | `laborStruct='monopsony'` | `main` |
| `labor-union` | `laborStruct='union'`, `unionModel` = `'monopoly'` либо `'wagefloor'` | `main` |
| `labor-bilat` | `laborStruct='bilateral'` | `main` |

Вход один: `redrawScene` (60-overlays.js:90) → `redrawLabor` (705). Шкалы: `recomputeLabor` (114) в конце сам ставит окно `applyAutoRanges(padMax(Lmax), padMax(Wmax))` (187–192: перехваты D и S, уровень МРОТ, зарплата профсоюза), затем `makeScales()` (707) заново строит `sx`, `sy`. Дальше: очистка → `addDefs` → `drawGrid` → `drawAxes('L', 'W')` (708–711).

МРОТ — общий регулятор: `STATE.laborMinOn`, `STATE.laborMinW`; «связывает» = `STATE.laborMin.binding`. При первом входе в режим МРОТ включён и равен 65 (52-modes.js:865–872).

### Порядок вызовов (слои снизу вверх; 712–742)

| Структура | Порядок |
|---|---|
| `bilateral` | `drawLaborBilateral` → `drawCurves` → `drawLaborMCL` → `drawLaborUnionMRL` → `drawLaborGhost(Lk, Wk, 'К')` |
| `union` | `drawLaborGapDWL(u.Lu, u.Lk)` (если модель «монополист» либо диктат связывает) → `drawCurves` → `drawLaborUnionMRL` (только «монополист») → `drawLaborUnionPoints` → `drawLaborUnionWageLine` (только диктат) |
| `monopsony` | `drawLaborMinWelfare` (МРОТ связывает) либо `drawLaborDWL` → `drawCurves` → `drawLaborMCL` → `drawLaborMonopsonyPoints` |
| `competition` | `drawLaborMinWelfare` (МРОТ связывает) либо `drawLaborSurpluses` → `drawCurves` → `drawLaborCompPoints` |
| в конце | `drawLaborMinLine`, если `laborMinOn` и структура не `union` (741) |

Результаты расчёта: `STATE.laborEq {Q, P}`, `STATE.laborMono {Lm, Wm, Lk, Wk, dwl}` (138), `STATE.laborUnion` — `{Lu, Wu, Lk, Wk, dwl}` (97) либо `{binding, W, Lu, Qs, unemployment, Lk, Wk}` (110), `STATE.laborBilateral {Wlo, Whi, Wm, Lm, Wu, Lu, Wk, Lk}` (159), `STATE.laborMin` — монопсония `{binding, Lstar, wage, Lhat, unemployment, Wmin}` (59), конкуренция `{binding, Wmin, Qd, Qs, employment, unemployment}` (82), `STATE.laborMinWelfare {Lstar, Wfact, …}` (181).

### Функции рисования

| Функция (строки) | Рисует | Когда |
|---|---|---|
| `laborPoint` (196–211) | помощник: точка, две проекции, отметки L и W, имя | вызовы 339, 389, 569, 570 |
| `drawLaborGhost` (214–221) | помощник: призрак, подпись, отметка L | вызовы 316, 374, 458, 719 |
| `drawLaborSurpluses` (224–235) | излишки работников и фирм | конкуренция, МРОТ не связывает |
| `drawLaborMinWelfare` (240–260) | излишки и DWL при МРОТ | конкуренция и монопсония, МРОТ связывает |
| `drawLaborMCL` (269–296) | MCL, подпись; при МРОТ ломаная MCLэфф | монопсония, двусторонняя |
| `drawLaborDWL` (299–309) | DWL монопсонии | монопсония, МРОТ не связывает |
| `drawLaborMonopsonyPoints` (312–365) | точки монопсонии, безработица | монопсония |
| `drawLaborCompPoints` (368–391) | равновесие либо занятость и безработица | конкуренция |
| `drawLaborMinLine` (394–406) | линия МРОТ с ручкой | `laborMinOn`, `laborMinW` > 0, не профсоюз |
| `drawLaborUnionMRL` (435–443) | MRL, подпись | профсоюз-монополист, двусторонняя |
| `drawLaborGapDWL` (446–453) | DWL профсоюза | профсоюз |
| `drawLaborUnionPoints` (456–487) | точки профсоюза, безработица | профсоюз |
| `drawLaborUnionWageLine` (490–502) | линия зарплаты профсоюза с ручкой | профсоюз, диктат, `unionWage` > 0 |
| `drawLaborBilateral` (546–571) | полоса диапазона, границы, две подписи, две точки | двусторонняя |
| `redrawLabor` (705–743) | оркестратор | режим `labor` |

Не рисуют на холсте: `laborMCL` 14, `laborMinMonopsony` 26, `laborMinCompetition` 64, `laborUnionMonopoly` 89, `laborUnionWageFloor` 103, `recomputeLabor` 114, `attachLaborMinDrag` 408, `setLaborMinFields` 416, `setLaborMin` 423, `attachUnionWageDrag` 504, `setUnionWageFields` 512, `setUnionWage` 519, `setUnionModel` 529, `updateLaborBilateralPanel` 574, `setLaborStruct` 592, `updateLaborPanel` 615.

Слой поверх сцены (`snapTargetsAll`, 60-overlays.js:3765) знает здесь только кривые списка D и S; MCL и MRL в нём нет.

---

## II-B. Опись мест рисования

Все функции переводят данные в пиксели глобальными `sx`, `sy` (панель `main`).

### `laborPoint(g, L, W, color, label, opts)` 196–211 · группу даёт вызывающий · `dash` 199

Вызовы: 339 — (`min.Lstar`; `min.wage`), `COL.ink`, «M», отметка W гасится, если `fmt(wage) === fmt(laborMinW)` (337–340); 389 — (`eq.Q`; `eq.P`), «E», индексы `k`, `k`; 569 — (`b.Lm`; `b.Wm`), `COL.S`, «M», индекс «м», без отметки W; 570 — (`b.Lu`; `b.Wu`), `COL.MR`, «E′», индекс «п», без отметки W.

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 201 | проекция вертикальная | (L; W) – (L; 0) | всегда | нет | П |
| 201 | проекция горизонтальная | (L; W) – (0; W) | всегда | нет | П |
| 204 | подпись под осью вместо числа | — | `opts.lText` — НИ ОДИН вызов его не передаёт (мёртвая ветка) | — | haloText |
| 205 | отметка у оси L | число L (форматирует `coordValue`), индекс `opts.lIdx` | `opts.lText !== null` | coord-num | осьX |
| 207 | подпись у оси W вместо числа (`yWageLabel`) | — | `opts.wText` строкой не передаётся (мёртвая ветка) | — | haloText |
| 208 | отметка у оси W (`yWageValue`) | число W, индекс `opts.wIdx` | `opts.wText !== null` | coord-num | осьY |
| 209 | точка | (L; W) | всегда | нет | r 4.5, fill = `color`, stroke halo 1.5 |
| 210 | подпись точки | `label` | всегда | point-name, data-raw | pointName, цвет = `color` |

### `drawLaborGhost(L, W, label)` 214–221 · группа 216

Вызовы: 316 — (`mono.Lk`; `mono.Wk`), «К»; 374 — (`eq.Q`; `eq.P`), «E₀»; 458 — (`u.Lk`; `u.Wk`), «К»; 719 — (`b.Lk`; `b.Wk`), «К». Условие: `STATE.showGhost` и оба числа заданы.

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 217 | точка-призрак | (L; W) | `showGhost` | нет | Призрак |
| 218 | подпись («К», «E₀») | там же, +7 / +13 px | `showGhost` | нет | Тголый, fill `COL.inkSoft` |
| 220 | отметка у оси L | `fmt(L)`, индекс `k` | `showGhost` | coord-num | осьX |

### `drawLaborSurpluses` 224–235 · группа 227 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 231 | область «излишек работников» | 101 узел на [0; `eq.Q`]; низ S(l); верх `eq.P` | `eq.Q` > 0 (галочки нет) | `data-legend`=«Излишек работников» | fill `COL.S`, opacity .16 |
| 234 | область «излишек фирм» | те же узлы; низ `eq.P`; верх D(l) | то же | «Излишек фирм» | fill `COL.D`, opacity .16 |

### `drawLaborMinWelfare` 240–260 · группа 244 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 249 | область «излишек работников» | 101 узел на [0; `wf.Lstar`]; S(l) … `wf.Wfact` | `STATE.laborMinWelfare` | «Излишек работников» | `COL.S` .16 |
| 252 | область «излишек фирм» | `wf.Wfact` … D(l) | то же | «Излишек фирм» | `COL.D` .16 |
| 258 | область DWL | 101 узел на [min(Lstar, `eq.Q`); max]; S … D | отрезок не пуст | «Потери общества (DWL)» | DWL |

### `drawLaborMCL` 269–296 · группа 271 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 275 | кривая MCL | **(б)** l → `laborMCL(S, l)`: центральная разность d(S·l)/dl, h = max(1e-4, Qmax·1e-5) (14–19). Закрытая запись: производная от L·(`S.expr`); для S = a + bL это a + 2bL. 401 узел на [0; `CONFIG.Qmax`]; NaN даёт разрыв; хвоста ниже оси нет | есть D и S | нет | `COL.reg`, 2, «6 4» |
| 277 | подпись кривой «MCL» | x = 0.85·`CONFIG.Qmax`, y = MCL(x), сдвиг −4 px | MCL(x) ≤ `CONFIG.Pmax` | нет | Тголый, fill `COL.reg` |
| 284 | отрезок: полка MCLэфф | (0; `min.Wmin`) – (`min.Lhat`; Wmin); Lhat = `invCurve(S, Wmin)` | `laborMin.binding` и есть `Lhat` (поле `Lhat` есть только у расчёта монопсонии) | нет | `COL.warn`, 3.5, сплошная |
| 288 | кривая: MCL правее L̂, поверх 275 | те же 401 узел; узлы с l < Lhat выброшены, первая точка — первый узел сетки не левее Lhat (не сам Lhat) | то же | нет | `COL.warn`, 3, сплошная |
| 291 | отрезок вертикальный: скачок MCLэфф | (Lhat; Wmin) – (Lhat; MCL(Lhat)) | MCL(Lhat) не NaN | нет | `COL.warn`, 2, «3 2», opacity .7 |
| 293 | подпись «MCLэфф» | x = 0.4·Lhat, y = Wmin, сдвиг −5 px | то же, что 284 | нет | Тголый, fill `COL.warn` |

### `drawLaborDWL(Lfrom)` 299–309 · группа 305 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 308 | область DWL монопсонии | 101 узел на [min(Lm, Lk); max]; S … D (единственный вызов 731 без аргумента, то есть от `mono.Lm`) | `mono.Lk` задан | «Потери общества (DWL)» | DWL |

### `drawLaborMonopsonyPoints` 312–365 · 316: `drawLaborGhost` · группа 317 · `dash` 319

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 325 | призрак M₀ | (`mono.Lm`; `mono.Wm`) | МРОТ связывает, `showGhost` | нет | Призрак |
| 326 | подпись «M₀» | +7 / −6 px | то же | нет | Тголый |
| 339 | новый оптимум при МРОТ — через `laborPoint` | (`min.Lstar`; `min.wage`) | МРОТ связывает, Lstar > 1e-6 | см. `laborPoint` | |
| 345 | отрезок-скобка «безработица» на оси L | (min(Lstar, Lhat); 0) – (max; 0) | `min.unemployment` > 1e-6 | нет | `COL.bad`, 5, opacity .5 |
| 346 | индикатор под осью «Безработица = N» | середина отрезка; y = sy(0) + 24 px | то же | data-raw | haloText middle / hanging |
| 354 | проекция вертикальная | (Lm; MCL(Lm)) – (Lm; 0), MCL численно | МРОТ не связывает | нет | П |
| 357 | точка MCL = D | (Lm; MCL(Lm)) | то же | нет | r 3.5, fill `COL.reg`, stroke halo 1.2 |
| 359 | проекция горизонтальная | (0; Wm) – (Lm; Wm) | то же | нет | П |
| 360 | точка M | (`mono.Lm`; `mono.Wm`) | то же | нет | ТчкM |
| 361 | подпись «M» | | то же | point-name | pointName |
| 362 | отметка у оси L | `fmt(mono.Lm)`, индекс «м» | то же | coord-num | осьX |
| 363 | отметка у оси W | `mono.Wm`, индекс «м» | то же | coord-num | осьY |

### `drawLaborCompPoints` 368–391 · группа 371 · `dash` 377

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 374 | ориентир «E₀» — через `drawLaborGhost` | (`eq.Q`; `eq.P`) | МРОТ связывает | | |
| 379 | проекция вертикальная | (`min.Qd`; Wmin) – (Qd; 0) | МРОТ связывает | нет | П |
| 379 | проекция вертикальная | (`min.Qs`; Wmin) – (Qs; 0) | то же | нет | П |
| 380 | отметка у оси L | `fmt(min.Qd)`, индекс «спрос» | то же | coord-num | осьX |
| 381 | отметка у оси L | `fmt(min.Qs)`, индекс «предл» | то же | coord-num | осьX |
| 384 | отрезок-скобка «безработица» на оси L | (min(Qd, Qs); 0) – (max; 0) | то же | нет | `COL.bad`, 5, opacity .5 |
| 385 | индикатор под осью «Безработица = N» | середина отрезка; y = sy(0) + 24 px | `min.unemployment` конечна | data-raw | haloText |
| 387 | точка занятости (без имени) | (`min.Qd`; `min.Wmin`) | МРОТ связывает | нет | r 4, fill `COL.ink`, stroke halo 1.5 |
| 389 | равновесие «E» — через `laborPoint` | (`eq.Q`; `eq.P`) | МРОТ не связывает | см. `laborPoint` | |

### `drawLaborMinLine` 394–406 · группа 397

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 398 | линия МРОТ (уровень через весь кадр) | (0; `STATE.laborMinW`) – (`CONFIG.Qmax`; laborMinW) | `laborMinOn`, `laborMinW` > 0, не профсоюз | нет | `COL.reg`, 2.5 |
| 400 | отметка у оси W | `fmt(STATE.laborMinW)`, индекс `min` | то же | coord-num | осьY |
| 401 | служебное: полоса захвата, d3.drag → `setLaborMin(sy.invert(y))` (403, 408) | y = уровень ± 12 px | то же | нет | `rect`, transparent |
| 404 | ручка | (0.6·`CONFIG.Qmax`; laborMinW) | то же | после кадра: `data-service`, `data-skip-export` | r 7, fill `COL.reg`, stroke halo 2 |

### `drawLaborUnionMRL` 435–443 · группа 437 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 439 | кривая MRL (drawMarginalCurve) | **(б)** l → `marginalRevenue(D, l)` численно. Закрытая запись: производная от L·(`D.expr`). 401 узел на [0; max(Qmax, ноль D)]; хвост ниже оси | есть D | хвост `data-marginal-tail` | `COL.MR`, 2, «6 4» |
| 441 | подпись кривой «MRL» | x = 0.28·`CONFIG.Qmax`, y = MRL(x), сдвиг −4 px | 0 ≤ MRL(x) ≤ `CONFIG.Pmax` | нет | Тголый, fill `COL.MR` |

### `drawLaborGapDWL(La, Lb)` 446–453 · группа 449 с clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 452 | область DWL профсоюза | 101 узел на [min(Lu, Lk); max]; S … D | оба конца заданы, отрезок не пуст | «Потери общества (DWL)» | DWL |

### `drawLaborUnionPoints` 456–487 · 458: `drawLaborGhost` · группа 459 · `dash` 460

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 466 | проекция вертикальная | (Lu; 0) – (Lu; Wu) | модель «монополист» | нет | П |
| 468 | точка MRL = S | (`u.Lu`; S(Lu)) | то же | нет | r 3.5, fill `COL.MR`, stroke halo 1.2 |
| 470 | проекция горизонтальная | (0; Wu) – (Lu; Wu) | то же | нет | П |
| 471 | точка E′ | (`u.Lu`; `u.Wu`) | то же | нет | ТчкM |
| 472 | подпись «E′» | | то же | point-name | pointName |
| 473 | отметка у оси L | `fmt(u.Lu)`, индекс «п» | то же | coord-num | осьX |
| 474 | отметка у оси W | `u.Wu`, индекс «п» | то же | coord-num | осьY |
| 478 | проекция вертикальная | (`u.Lu`; `u.W`) – (Lu; 0) | диктат связывает | нет | П |
| 478 | проекция вертикальная | (`u.Qs`; W) – (Qs; 0) | то же | нет | П |
| 479 | отметка у оси L | `fmt(u.Lu)`, индекс «п» | то же | coord-num | осьX |
| 480 | отметка у оси L | `fmt(u.Qs)`, индекс «предл» | то же | coord-num | осьX |
| 482 | отрезок-скобка «безработица» на оси L | (min(Lu, Qs); 0) – (max; 0) | то же | нет | `COL.bad`, 5, opacity .5 |
| 483 | индикатор под осью «Безработица = N» | середина отрезка; y = sy(0) + 24 px | `u.unemployment` > 1e-6 | data-raw | haloText |
| 484 | точка E′ | (`u.Lu`; `u.W`) | диктат связывает | нет | ТчкM |
| 485 | подпись «E′» | | то же | point-name | pointName |

### `drawLaborUnionWageLine` 490–502 · группа 493

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 494 | линия зарплаты профсоюза (уровень через весь кадр) | (0; `STATE.unionWage`) – (`CONFIG.Qmax`; unionWage) | диктат, `unionWage` > 0 | нет | `COL.MC`, 2.5 |
| 496 | отметка у оси W | `fmt(STATE.unionWage)`, индекс «п» | то же | coord-num | осьY |
| 497 | служебное: полоса захвата, d3.drag → `setUnionWage(sy.invert(y))` (499, 504) | y = уровень ± 12 px | то же | нет | `rect`, transparent |
| 500 | ручка | (0.6·`CONFIG.Qmax`; unionWage) | то же | после кадра: `data-service`, `data-skip-export` | r 7, fill `COL.MC`, stroke halo 2 |

### `drawLaborBilateral` 546–571 · группа 549 с clip, группа 557 без clip

| Стр. | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 551 | область «диапазон зарплат», прямоугольник | (г) x ∈ [0; `CONFIG.Qmax`], y ∈ [`b.Wlo`; `b.Whi`] | `STATE.laborBilateral` | `data-legend`=«Диапазон возможных зарплат» | `rect`, fill `COL.reg`, opacity .16 |
| 553 | линия нижней границы | (0; Wlo) – (`CONFIG.Qmax`; Wlo) | то же | нет | `COL.reg`, 1.8, «6 4» |
| 555 | линия верхней границы | (0; Whi) – (`CONFIG.Qmax`; Whi) | то же | нет | то же |
| 558 | отметка у оси W | текст `fmt(b.Wm)`, индекс «м»; место — уровень `b.Wlo` | то же | coord-num | осьY |
| 559 | отметка у оси W | текст `fmt(b.Wu)`, индекс «п»; место — уровень `b.Whi` | то же | coord-num | осьY |
| 560 | подпись области «Диапазон возможных исходов» | x = `CONFIG.Qmax`/2, y = (Wlo + Whi)/2 | то же | нет | `.text()`, `FS.base`, 600, fill `COL.warn`, ореол 3, anchor middle |
| 564 | подпись-пояснение «Конкретная точка зависит от переговорной силы, а её модель не определяет» | там же, на 15 px ниже | то же | нет | `.text()`, `FS.small`, fill `COL.inkSoft`, ореол 3 |
| 569 | граничная точка «M» — через `laborPoint` | (`b.Lm`; `b.Wm`), цвет `COL.S` | то же | см. `laborPoint` | |
| 570 | граничная точка «E′» — через `laborPoint` | (`b.Lu`; `b.Wu`), цвет `COL.MR` | то же | см. `laborPoint` | |

---

## II-C. Области подробно

Построение то же, что в монополии: `d3.area` по 101 значению L (`samp`), без `.curve` и `.defined`; группы с `clip-path: url(#plot-clip)`; рисуются раньше кривых.

| Область | Место | Отрезок по L | Нижняя граница | Верхняя граница | Узлов | Стороны |
|---|---|---|---|---|---|---|
| излишек работников | 231 | [0; `eq.Q`] | S(l) | W = `eq.P` | 101 | одна по кривой |
| излишек фирм | 234 | [0; `eq.Q`] | W = `eq.P` | D(l) | 101 | одна по кривой |
| излишек работников при МРОТ | 249 | [0; `wf.Lstar`] | S(l) | `wf.Wfact` | 101 | одна по кривой |
| излишек фирм при МРОТ | 252 | [0; `wf.Lstar`] | `wf.Wfact` | D(l) | 101 | одна по кривой |
| DWL при МРОТ | 258 | [min(Lstar, Lk); max] | S(l) | D(l) | 101 | две по кривым |
| DWL монопсонии | 308 | [min(Lm, Lk); max] | S(l) | D(l) | 101 | две по кривым |
| DWL профсоюза | 452 | [min(Lu, Lk); max] | S(l) | D(l) | 101 | две по кривым |
| диапазон зарплат | 551 | [0; `CONFIG.Qmax`] | `b.Wlo` | `b.Whi` | `rect` | все прямые |

- Концы отрезков и уровни зарплаты хранятся числами (`laborEq`, `laborMinWelfare`, `laborMono`, `laborUnion`, `laborBilateral`).
- Обрезки нулём (аналога `mcFloor`) здесь нет: нижняя граница — сама S(l). Если S уходит ниже нуля, фигуру режет только clip-path окна.
- Правый край прямоугольника 551 — край окна `CONFIG.Qmax`, а не число модели.
- При линейных D и S (пресет `100 - L` и `L`) семь криволинейных областей — точные треугольники и трапеции, нарисованные 101 узлом.

---

## II-D. Элементы у осей, под осью, на полях

| Элемент | Места | Как позиционируется |
|---|---|---|
| Отметка у оси L (осьX) | 205, 220, 362, 380, 381, 473, 479, 480 | x = sx(значение); y = sy(0) + 8 px |
| Отметка у оси W (осьY, `yWageValue`) | 208, 363, 400, 474, 496, 558, 559 | x = sx(0) − 8 px; y = sy(значение) |
| Индексы отметок | | `k` латиницей (220, 389); «м» (362, 363, 558, 569); «п» (473, 474, 479, 496, 559, 570); «спрос» (380); «предл» (381, 480); `min` (400); без индекса (339) |
| Отрезок безработицы на оси L | 345, 384, 482 | по оси от меньшего объёма до большего, y = sy(0); толщина 5, `COL.bad` |
| Индикатор «Безработица = N» | 346, 385, 483 | x = середина отрезка (px), y = sy(0) + 24 px (полоса `BOTTOM_BAND`) |
| Ручки линий МРОТ и зарплаты профсоюза | 404, 500 | на линии уровня, x = 0.6·`CONFIG.Qmax` |
| Подписи внутри полосы диапазона | 560, 564 | центр окна по L, середина полосы по W; вторая строка на 15 px ниже |
| Подписи «MCL», «MRL», «MCLэфф» | 277, 441, 293 | фиксированные доли окна (0.85·Qmax, 0.28·Qmax) либо 0.4·Lhat; лежат в группах с clip, поэтому `unclipLabels` может перенести их в `g.free-labels` |

Оси «L», «W», деления и названия — `drawAxes('L', 'W')` (711), вне этого файла.

---

## II-E. Трудные случаи для записи формулой

1. **MCL и MRL считаются численно** (275, 288, 439): центральная разность с шагом, зависящим от `CONFIG.Qmax` (14–19; 42-scenes-mono.js:55–61). Закрытая запись — производная от L·S(L) и L·D(L); строки берутся из кривых списка. Символьный помощник `derivativeExpr` (30-curves.js:265) здесь не используется.
2. **Ломаная MCLэфф при МРОТ в монопсонии** собрана из трёх мест: полка (284), вертикальный скачок (291) и участок обычной MCL правее L̂ (288). Участок 288 начинается с узла сетки, а не с L̂: между скачком и началом сплошной линии возможен зазор до одного шага Qmax/400. Под ломаной целиком остаётся пунктирная MCL (275).
3. **MRL с хвостом ниже оси** (439): два пути, хвост тянется до нуля спроса.
4. **Вертикальные линии:** скачок MCLэфф (291) и вертикальные проекции (201, 354, 379, 466, 478).
5. **Окно переставляется на каждой перерисовке** (`applyAutoRanges`, 192): `CONFIG.Qmax`, `CONFIG.Pmax` следуют за кривыми, МРОТ и зарплатой профсоюза. От `CONFIG.Qmax` зависят: сетки 274 и 287, правые концы линий 396, 492, 548, правый край прямоугольника 551, места подписей 276, 440, 560, ручки 404, 500, а в расчёте — отрезок поиска корня 47.
6. **Пороги показа подписей зависят от окна:** «MCL» при MCL(0.85·Qmax) ≤ Pmax (277), «MRL» при 0 ≤ MRL(0.28·Qmax) ≤ Pmax (441).
7. **Отметка гасится по совпадению строк:** при МРОТ, равном зарплате монопсониста, отметка W у точки M не печатается (337–340: сравнение `fmt(...)`).
8. **Кириллические индексы** у чисел на осях: «м», «п», «спрос», «предл» (в выгрузке они станут нижними индексами в математике).
9. **Кривые списка, введённые как L = f(W):** у нелинейной обратная запись есть только численно (см. 0.3).
10. **Пиксели:** сдвиги подписей в px в каждом месте; зажимы `haloText`; пороги осьX/осьY; проходы из 0.1.
11. По чтению кода: отметки 558 и 559 печатают числа `b.Wm` и `b.Wu` на уровнях `b.Wlo` и `b.Whi`; при `Wm > Wu` текст и место разошлись бы. Бывает ли такое в модели, не проверял.

---

## II-F. Итог по 46-scenes-labor.js (места в коде)

| Что | Сколько | Адреса |
|---|---|---|
| Кривые, которые рисует сам файл | **3** | 275 (MCL), 288 (MCL правее L̂), 439 (MRL) |
| — со строкой-формулой в STATE | 0 | |
| — закрытая запись есть, строки нет | 3 | все три; сейчас считаются численно |
| — численные без закрытой записи | 0 | |
| Вызовы общего `drawCurves()` | 4 | 716, 725, 732, 738 |
| Области | **8** | 231, 234, 249, 252, 258, 308, 452, 551 |
| — прямые стороны всегда | 1 | 551 (`rect`) |
| — граница по кривой | 7 | остальные |
| Линии-проекции | **10** | 201×2 (помощник), 354, 359, 379×2, 466, 470, 478×2 |
| Отрезки (не проекции) | **9** | уровни через кадр 398, 494, 553, 555; скобки 345, 384, 482; части ломаной MCLэфф 284, 291 |
| Точки | **9** | 209 (помощник), 217 (помощник), 325, 357, 360, 387, 468, 471, 484 |
| Подписи кривых, точек, областей | **11** | pointName 4 (210, 361, 472, 485); голый `.text()` 7 (218, 277, 293, 326, 441, 560, 564) |
| Мёртвые ветки подписей | 2 | 204, 207 |
| Индикаторы | 3 | 346, 385, 483 |
| Отметки у осей | **15** | осьX 8, осьY 7 |
| Строки легенды | своих мест нет | 8 элементов с `data-legend`, 4 разных ключа; одновременно до 3 строк |
| Ручки | **2** (+2 полосы захвата) | 404, 500 (полосы 401, 497) |
| Служебные группы | 14 | 216, 227, 244, 271, 305, 317, 371, 397, 437, 449, 459, 493, 549, 557 |

---

# Сводка по двум файлам

| Что | mono | labor | Вместе |
|---|---|---|---|
| Мест, рисующих кривые | 15 | 3 | 18 |
| — строка в STATE есть | 5 | 0 | 5 |
| — закрытая запись без строки | 7 | 3 | 10 |
| — зависит от способа ввода | 2 | 0 | 2 |
| — численная без закрытой записи | 1 | 0 | 1 |
| Областей (фигур) | 28 | 8 | 36 |
| — прямоугольники | 2 | 1 | 3 |
| — с границей по кривой | 26 | 7 | 33 |
| Линий-проекций | 19 | 10 | 29 |
| Отрезков | 9 | 9 | 18 |
| Точек | 18 | 9 | 27 |
| Подписей кривых, точек, областей | 21 | 11 | 32 |
| — из них голым `.text()` | 7 | 7 | 14 |
| Индикаторов | 2 | 3 | 5 |
| Отметок у осей | 23 | 15 | 38 |
| Ключей легенды | 7 | 4 | 10 разных (DWL общий) |
| Ручек | 2 | 2 | 4 |

Ни одна из 18 кривых сейчас не помечена для выгрузки формулой.

---

# Попутные наблюдения (вне двух файлов; по чтению кода, запуском не проверялись)

1. **Оба сборщика .tex идут по `STATE.curves` без проверки, рисует ли сцена этот список.** `buildTexLegacy` (70-scenes-math.js:2043–2057) и `buildTexFromState` (:1704) не спрашивают `sceneDrawsCurveList()` (30-curves.js:1233). В `mono-d3`, `mono-kink`, `monoexport` список не рисуется, но кривые в нём остаются (их кладёт `loadScene`, 84-picker.js:43–45, 105–106). По коду выходит, что в файл уйдут D и MC из скрытого списка, которых на холсте нет.
2. **Голые `.text()`** (14 мест, см. сводку) не получают `data-raw` и классов; по правилу из calc2/CLAUDE.md подписи холста рисуются только через `renderLabelText`. У legacy-выгрузки такие подписи читаются по содержимому узла (`labelPlainText`, 70-scenes-math.js:1358).
3. **Режим «Сначала сам» и надпись «Дефицит = N».** Правило в 96-self.js:177 — `/^\s*(дефицит|избыток)\b/i`. Отдельная проверка этого регулярного выражения в node (вне репозитория) показала: к строке «Дефицит = 40» оно не подходит, потому что `\b` в JS не считает кириллицу буквами слова. «Безработица = N» и «Экспорт = N» в списке правил нет вовсе. В самом приложении не проверял.
4. **Подписи кривых есть не везде:** у MR нет подписи в `mono`, `mono-nat`, `mono-kink`, `mono-d3`; у D и MC нет подписи в `mono-kink` и `mono-d3`; у MC, выведенной из TC, нет нигде.
