# 02 · 40-scenes-market.js: опись мест рисования (рыночные сцены)

Файл `calc2/static/calc2/40-scenes-market.js`, 3 729 строк, ветка `feat/calc2-redesign`. Прочитан целиком. Ничего не запускалось: всё ниже получено чтением кода; выводы, которые стоило бы подтвердить запуском, помечены «не проверено запуском».

Общее для всего файла (в таблицах не повторяется):

- **Шкалы.** Везде глобальные `sx` / `sy` (20-plane.js:9; строит `makeScales`, 20-plane.js:141, домен `[CONFIG.Qmin, CONFIG.Qmax] × [CONFIG.Pmin, CONFIG.Pmax]`), `toPx(q, p) = [sx(q), sy(p)]` (20-plane.js:353). Локальных шкал `mx/my` в файле нет.
- **Панели.** У всех сцен файла одна панель `'main'` (регистрирует `makeScales`, 20-plane.js:148). `registerPanel` / `clearPanels` файл не вызывает.
- **Счёт `.append(…)`:** 109 штук: path 24, line 21, rect 7, circle 20, text 10, g 20, tspan 7.
- **Группы с обрезкой** `clip-path: url(#plot-clip)` (окно; при `STATE.firstQuad` первая четверть, 20-plane.js:486–492): 619, 845, 2136, 2218, 2302, 2342, 3057, 3203, 3215, 3411, 3579. **Без обрезки:** 663, 810, 2375, 3074, 3111, 3239, 3439, 3608, 3716.
- **Цвета.** `COL.*` читается из CSS-переменных (00-config.js:470–523): D `--curve-d`, S `--curve-s`, MR `--curve-mr`, tax `--curve-tax`, dwl `--curve-dwl`, reg `--curve-reg`, ghost `--curve-ghost`, bad `--c-bad`, ink `--ink`, inkSoft `--ink-soft`, halo `--halo`. Кегли `FS` (00-config.js:57): small 10, base 12, large 14.
- **Кривая-роль.** `STATE.D` / `STATE.S` ставит `recompute` (29–30) через `curveByRole` (17): это объект из `STATE.curves` с полями `expr` (строка, как набрана), `compiled`, `linear {a, b}`, `fn`, `color`, `srcForm`, у суммарной ещё `kind:'sum'`, `sumBreaks`, `sumGhostTo`, `sumDomainTo`, `sumNumeric`. Значение считает `evalCurve` (10-math-core.js:242) в порядке `fn` → `linear` → `compiled`. Оговорки про `expr` в разделе F.
- **Тип источника геометрии:** (а) строка Math.js; (б) JS-функция без строки; (в) массив точек модели; (г) отдельные числа.

---

## A. Функции и порядок вызова

### A.1 Кто кого зовёт

`redrawAll` (60-overlays.js:10) → `redrawScene` (60-overlays.js:78) → `recompute()` (этот файл, 24–482; считает всё в `STATE` ДО рисования) → `svg.selectAll('*').remove()`, `addDefs`, `drawGrid`, `drawAxes` (60-overlays.js:103–106) → ветка сцены (ниже) → табло `update*Panel` (60-overlays.js:189–214) → `drawOverlays` (60-overlays.js:453: ключевые точки, свои точки, площади, легенда) → общие проходы по подписям (60-overlays.js:19–29) → `markServiceNodes`, `selfCanvas` (60-overlays.js:74–75).

Отдельной функции-сцены в файле нет (кроме `drawExtScenario`); сцену собирает `redrawScene` из функций этого файла и `drawCurves` (30-curves.js:1072, рисует сами D, S и группы сложения).

| Ветка `redrawScene` (60-overlays.js) | Ключи моделей | Порядок вызовов (он же порядок слоёв снизу вверх) |
|---|---|---|
| `scenario === 'externality'` (154–156) | `ext` | `drawExtScenario` (3271): `drawExtAreas` → `drawCurves` → `drawExtCurves` → `drawExtPoints` |
| `scenario === 'openecon'` (157–161) | `smallopen` | `drawOpenAreas` → `drawCurves` → `drawOpenLines` |
| `scenario === 'elasticity'` (162–168) | `elast` | `drawElasticityZones` → `drawCurves` → `drawEquilibrium` → `drawElasticityPoint` → `drawElasticityPointS` |
| иначе, конкуренция и `scenario 'none'` (169–188) | `sd`, `sdsum`, `taxes`, `tax`, `tax-adv`, `ceil`, `quota` | заливки: `taxActive` → `drawTaxAreas`, иначе `pcActive` → `drawPcAreas`, иначе `quotaActive` → `drawQuotaAreas`, иначе `drawAreas`; затем `drawGhost` → `drawCurves` → `drawShiftedSupply` → `drawTaxPivot`; точки и линии: `taxActive` → `drawTaxPoints`, иначе `pcMode` → `drawPriceControl`, иначе `quotaMode` → `drawQuotaLines`, иначе `drawEquilibrium`; последним `drawOffQuadIntersection` |
| `market === 'monopoly'` (107–153) | `mono`, `mono-nat`, `mono-d1` | рисует 42-scenes-mono.js; из этого файла работают `recompute()` (STATE.mono, monoTax, monoCeil, monoFloor, monoQuota, natural, discr1: 329–400), помощники подписей `haloText` и `pointName` (B.0) и `attachPcDrag` (3481; 2 вызова в 42) |
| выход до `recompute` (98–101) | `mono-d3`, `mono-kink`, `monoexport` | `recompute` не зовётся (единственный вызов: 60-overlays.js:102); из этого файла возможны только общие помощники подписей |

Чем сцены отличаются по состоянию (ставит `loadScene`, 84-picker.js:8–113, и маршруты `SCENE_ROUTE`, 84-picker.js:256–302):

| Ключ | Что в STATE |
|---|---|
| `sd` | `scenario 'none'`, `intervType 'tax'`, `tax 0`; блок вмешательства заперт |
| `sdsum` | то же + `STATE.sumOn`; `STATE.curves` = группы и две суммарные кривые (`sumBuildScene`, 1946); вмешательство заперто |
| `taxes`, `tax` | `intervType 'tax'`, `tax 20`; переключаются налог/субсидия, вид (`taxForm`, `subKind`), сторона (`taxSide`) |
| `tax-adv` | то же, затем `setTaxForm('vat')`, `setTax(20)` |
| `ceil` | `intervType 'ceiling'` или `'floor'`, `pReg 30`, `pRegSet` |
| `quota` | `intervType 'quota'`, `quota 40`, `quotaPos 0.5`, `quotaSet` |
| `elast` | `scenario 'elasticity'`, `elastQ`, `elastQS`, `showElastS` |
| `ext` | `scenario 'externality'`, `msbOn/mscOn`, `msbExpr/mscExpr`, `applyPigou` |
| `smallopen` | `scenario 'openecon'`, `openPw 30`, `openTool none/tariff/quota`, `openTariff`, `openQuota` |

Признаки, по которым идут ветки, ставит `recompute`: `taxCurveOn` (184: есть S, D и ставка > 0), `taxActive` (199: нашлось новое равновесие), `taxNoBase` (222), `pcMode` (229), `pcActive` (279: связывает, есть `Qtrade` и `STATE.eq`), `quotaMode` (304), `quotaActive` (325), `STATE.elast` (417), `STATE.elastS` (432), `STATE.ext` (473), `STATE.open` (612 или 528 с `error`).

### A.2 Функции рисования

| Функция (строки) | Что рисует | Когда | Панелей |
|---|---|---|---|
| `drawEquilibrium` (805–830) | проекции равновесия, числа у осей, буква E | `STATE.eq`; зовут 60-overlays.js:166, 185 и `drawPriceControl` (3435, 3467), `drawQuotaLines` (3606, 3618) | 1 |
| `drawOffQuadIntersection` (842–872) | пунктир D и S к пересечению вне четверти, крестик | `STATE.offEq && !STATE.eq` | 1 |
| `drawAreas` (2132–2152) | CS, PS без вмешательства | `STATE.eq`, нет активного вмешательства | 1 |
| `drawGhost` (3710–3728) | бледное исходное равновесие E₀ | `showGhost && (taxActive ‖ pcActive ‖ quotaActive) && eq` | 1 |
| `drawShiftedSupply` (2207–2240) | кривая после налога/субсидии и её подпись | `taxCurveOn` | 1 |
| `drawTaxPivot` (2299–2331) | продолжения S и S_после к центру поворота, точка центра | процентная форма, нуль S левее оси P (`taxPivotPoint`, 2290) | 1 |
| `drawTaxAreas` (2334–2367) | CS, PS, деньги бюджета, DWL | `taxActive` | 1 |
| `drawTaxPoints` (2370–2419) | проекции, числа у осей, точки Pb/Ps, клин ставки, ручка | `taxActive` | 1 |
| `drawPcAreas` (3408–3429) | CS, PS, DWL при потолке/поле | `pcActive` | 1 |
| `drawPriceControl` (3432–3478) | линия цены, проекции Qs/Qd, дефицит/избыток, ручка | `pcMode` | 1 |
| `drawQuotaAreas` (3576–3600) | CS, PS, DWL при квоте | `quotaActive` | 1 |
| `drawQuotaLines` (3603–3645) | вертикаль квоты, коридор цен, выбранная цена | `quotaMode` | 1 |
| `drawElasticityZones` (3054–3069) | две зоны под спросом и их подписи | `STATE.elast.unit` | 1 |
| `drawElasticityPoint` (3072–3098) | единичная точка, тянущаяся точка на D | `STATE.elast` | 1 |
| `drawElasticityPointS` (3109–3127) | тянущаяся точка на S | `STATE.elastS` | 1 |
| `drawExtAreas` (3201–3209), `drawExtCurves` (3213–3234), `drawExtPoints` (3237–3268) | DWL; MSC, MSB, S + сдвиг Пигу; точки рынка и оптимума | `STATE.ext` | 1 |
| `drawOpenAreas` (616–658), `drawOpenLines` (661–706) | CS, PS, деньги, два треугольника потерь; линии цен, объём торговли, ручка | `STATE.open` | 1 |

Помощники подписей (B.0): `mathTspans` 942, `markNotationTspan` 1006, `mixedMathTspans` 1031, `qtyTspans` 1075, `texToCanvasText` 1150, `renderLabelText` 1159, `haloText` 1180, `pointName` 1213, `yWageLabel` 1239, `yWageValue` 1244. Вне файла их зовут 10 файлов: 20-plane, 30-curves, 42, 44, 46, 48, 50, 54, 60, 70 (56 строк с вызовами: `haloText` 26, `pointName` 14, `renderLabelText` 12, `yWageLabel` 1, `yWageValue` 3).

Навешивают перетаскивание: `attachOpenPwDrag` 708, `attachTaxDrag` 2423, `attachElastDrag` 3101, `attachElastDragS` 3129, `attachPcDrag` 3481, `attachQuotaDrag` 3648.

На холст НЕ рисуют: `recompute` 24–482, `recomputeOpenEconomy` 524–613, `qtyAtPrice` 510, весь блок сложения 1491–2127 (`sumLinearRecord` 1561, `sumPolyline` 1719, `sumRebuildSide` 1747, `sumBuildScene` 1946, `sumGroupStats` 2007), табло `updateOpenPanel` 750, `updateInfoPanel` 1382, `updateSumPanel` 2071, `updateAreasPanel` 2169, `updateTaxPanel` 2907, `updateElasticityPanel` 3137, `updateExtPanel` 3280, `updatePcPanel` 3490, `updateQuotaPanel` 3661 (пишут HTML в `#info-*`), каскад вмешательства и сеттеры 2444–3045, 3321–3405, 3535–3573, таблица `PCT_FORMS` 2518–2551.

Записи в HTML-блок «Итоговая функция» (`setFinalFunctions`, 86-workspace.js:1458) отдают два места файла: `sumFinalRecords` (2053–2069: суммарные D и S, поля `expr`, `lhs: 'P'`, либо приписка «сумма посчитана по точкам») и `updateTaxPanel` (2927–2941: кривая после вмешательства, `after.texExpr`). Это не холст; выгрузка от состояния читает из блока `data-ff-tex` (70-scenes-math.js:1890–1897).

---

## B. Опись мест рисования

### B.0 Общие помощники подписей

| Строка · функция | Что добавляет | Вход | Пометки | Стиль |
|---|---|---|---|---|
| 1196 · `haloText` (1180–1202) | `<text>` с ореолом | x, y в ПИКСЕЛЯХ, текст, anchor, baseline, `{noFlip}`; при нечисловой координате не рисует и возвращает `null` (1187) | `data-raw` через `renderLabelText` (1200) | FS.small, 600, fill COL.ink, обводка COL.halo 3 под заливкой |
| 1223 · `pointName` (1213–1235) | `<text class="point-name">` | px, py в пикселях; сдвиг (+8, −8) px или `opts.dx/dy` | `data-raw`; `kpName(g, px, py, sym)` (1233) отдаёт имя слою ключевых точек | FS.large или `opts.size`, 600, fill `color` или COL.ink, обводка COL.halo 5, скругление |
| 1168 · `renderLabelText` (1159–1174) | узла не добавляет: ставит `data-raw`, раскладывает текст | выбранный `<text>`, строка | `data-raw` = строка ПОСЛЕ `texToCanvasText` (1150: доллары сняты, команды TeX заменены юникодом) | нет |
| 968, 972, 977 · `mathTspans`; 1047 · `mixedMathTspans`; 1087, 1093, 1106 · `qtyTspans` | `<tspan>` внутри подписи | разметка `_`, `^`, `*`, `{…}` | `data-mathset` на tspan (1014, 1017, 1056), `'mixed'` на text (1059) | индекс: font-size 76 %, dy −0,42em или +0,26em; шрифт KaTeX через `style` |
| 1240 · `yWageLabel`, 1244 · `yWageValue` | обёртки над `haloText(ox − 8, py, 'end', 'middle')` и `axisValueY` | зовёт 46-scenes-labor.js | как у вызываемых | нет |

### B.1 Равновесие, «было», пересечение вне четверти

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 810 · `drawEquilibrium` | группа `g.equilibrium`, служебное | нет | `STATE.eq` | class | нет |
| 813 · `drawEquilibrium` | линия-проекция на ось Q | (г) (Q\*, P\*) → (Q\*, 0): `STATE.eq.Q`, `STATE.eq.P` | `STATE.eq` | нет | COL.inkSoft, 1, штрих 4 3 |
| 815 · `drawEquilibrium` | линия-проекция на ось P | (г) (Q\*, P\*) → (0, P\*) | то же | нет | то же |
| 819 · `drawEquilibrium` | отметка у оси Q | `axisValueX(g, sx(Q), sy(0), fmt(Q), '')` | то же | `coord-num`, `data-raw` | D.1 |
| 820 · `drawEquilibrium` | отметка у оси P | `axisValueY(g, sx(0), sy(P), fmt(P), '')` | то же | то же | D.1 |
| 829 · `drawEquilibrium` | подпись точки «E» | `pointName`: (Q\*, P\*) + (8, −8) px | то же | `point-name`, `data-raw 'E'` | FS.large, 600, COL.ink. Кружка у точки нет (комментарий 822–824) |
| 3716 · `drawGhost` | группа `g.ghost` | нет | условие функции (3711–3712) | class | нет |
| 3718, 3720 · `drawGhost` | 2 линии-проекции исходного равновесия | (г) (Q0, P0) → (Q0, 0) и → (0, P0), из `STATE.eq` | `STATE.showGhost` (галочка `#chk-ghost`; при смене сцены гасится, 60-overlays.js:4077) и активное вмешательство | нет | COL.ghost, 1, штрих 3 3 |
| 3723 · `drawGhost` | точка E₀, полая | (г) (`STATE.eq.Q`, `STATE.eq.P`) | то же | нет | r 4, fill COL.halo, stroke COL.ghost 1,5 |
| 3725 · `drawGhost` | подпись «E₀» | точка + (7, −6) px | то же | `data-raw` НЕТ (голый `.text`) | FS.base, 600, fill COL.inkSoft, ореол 2,5 |
| 845 · `drawOffQuadIntersection` | группа `g.offquad`, с обрезкой | нет | `STATE.offEq && !STATE.eq` | class | нет |
| 856 · `drawOffQuadIntersection` | 2 кривые: продолжения D и S к пересечению вне четверти | (а) `expr` кривых `STATE.D`, `STATE.S`; Q ∈ [min(0, off.Q), max(0, off.Q)], 161 точка, `evalCurve` | то же | `data-offquad=1`, `data-skip-export=1` | цвет кривой, 1,5, штрих 5 4, opacity 0,65 |
| 868 · `drawOffQuadIntersection` | крестик из 2 линий в точке пересечения | (г) `STATE.offEq.Q`, `.P`; концы ±5 px | точка внутри доменов `sx`, `sy` (865) | `data-offquad=1`; `data-skip-export` НЕТ | COL.inkSoft, 1,5 |

### B.2 Излишки без вмешательства

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 2136 · `drawAreas` | группа `g.areas`, с обрезкой | нет | `STATE.eq`, Q > 0 | class | нет |
| 2145 · `drawAreas` | область CS | верх (а) `STATE.D` через `quadPrice` = max(0, D) (20-plane.js:343); низ (г) `STATE.eq.P`; Q ∈ [0, `STATE.eq.Q`], 101 узел | `STATE.showCS` (`#chk-cs`) | `data-legend` «Излишек покупателя (CS)» | fill COL.D, opacity 0,16 |
| 2150 · `drawAreas` | область PS | низ (а) `STATE.S` через `quadPrice`; верх (г) `STATE.eq.P`; тот же отрезок | `STATE.showPS` (`#chk-ps`) | `data-legend` «Излишек продавца (PS)» | fill COL.S, opacity 0,16 |

### B.3 Налоги и субсидии

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 2342 · `drawTaxAreas` | группа с обрезкой | нет | `STATE.taxActive` | нет | нет |
| 2348 · `drawTaxAreas` | область CS | верх (а) `STATE.D` (`quadPrice`); низ (г) `STATE.taxEq.Pb`; Q ∈ [0, `taxEq.Q`], 101 узел | `showCS` | `data-legend` CS | COL.D, 0,16 |
| 2352 · `drawTaxAreas` | область PS | низ (а) `STATE.S` (`quadPrice`); верх (г) `STATE.taxEq.Ps` | `showPS` | `data-legend` PS | COL.S, 0,16 |
| 2358 · `drawTaxAreas` | область «деньги бюджета»: сбор налога или расход на субсидию | (г) прямоугольник [0, `taxEq.Q`] × [min(Pb, Ps), max(Pb, Ps)]; нарисован `d3.area` по 101 узлу, не `<rect>` | всегда при `taxActive`, галочки нет | `data-legend` «Сбор бюджета» / «Расход бюджета» (по `STATE.intervType`, 2359) | COL.tax, 0,22 |
| 2365 · `drawTaxAreas` | область DWL | низ (а) `STATE.S`, верх (а) `STATE.D`, оба через `evalCurve` без обрезки нулём; Q ∈ [min(Q1, Q0), max(Q1, Q0)], Q0 = `STATE.eq.Q`, 101 узел | есть `STATE.eq` и hi > lo; галочки нет | `data-legend` «Потери общества (DWL)» | COL.inkSoft, 0,28 |
| 2218 · `drawShiftedSupply` | группа с обрезкой | нет | `STATE.taxCurveOn` | нет | нет |
| 2227 · `drawShiftedSupply` | кривая после вмешательства: S ± ставка или factor·S; при стороне «покупатель» D ∓ ставка или D / factor | (а) `STATE.taxAfterS.texExpr` либо `STATE.taxAfterD.texExpr` (строка Math.js от Q после `simplifyRecord`, собирается в `recompute` 156–183). Точки берутся по `after.fn`: 401 штука, Q ∈ [0, `CONFIG.Qmax`]; NaN даёт разрыв; отрицательные значения не отбрасываются | `taxCurveOn`; какую кривую двигать, решает `intervOnBuyer()` (2198: `STATE.taxSide === 'buyer'`) | `markExpr` (30-curves.js:242) ставит `data-expr = texExpr`, если строка непустая. `data-curve` нет | цвет базовой кривой (D или S), 2, штрих 6 4 |
| 2239 · `drawShiftedSupply` | подпись кривой | `labelCurve(g, f, nm, цвет, {from: 0.82})`; `nm`: «S + t», «S − s», «D − t», «D + s» либо `PCT_FORMS[…].curve` / `.curveD` (2237–2238) | то же | `curve-name`, `data-raw` | кегль 12, 600, цвет кривой, ореол 2,6 |
| 2302 · `drawTaxPivot` | группа `g.pivot`, с обрезкой | нет | `taxPivotPoint()` не null | class | нет |
| 2316 · `drawTaxPivot` | 2 кривые: продолжения S и S_после влево-вниз к центру поворота | (а) `STATE.S.expr` и `STATE.taxAfterS.texExpr`; Q ∈ [p.Q, 0], p.Q < 0, 161 точка. p.Q даёт `taxPivotQ` (2259): у прямой −b/a из `S.linear`, иначе сетка 400 узлов и бисекция | `taxCurveOn`, процентная форма (`pctForm()`), нуль S левее оси P | `data-pivot '1'/'2'`; `data-expr` и `data-skip-export` НЕТ | цвет S, 1,1, штрих 5 4, opacity 0,5 |
| 2327 · `drawTaxPivot` | точка: центр поворота, полая | (г) (p.Q, 0) | точка внутри доменов шкал (2325) | `data-pivot 'dot'` | r 3,2, без заливки, stroke 1,4, opacity 0,75 |
| 2375 · `drawTaxPoints` | группа без обрезки | нет | `STATE.taxActive` | нет | нет |
| 2384 · `drawTaxPoints` | линия-проекция (Q1, Pb) → (Q1, 0) | (г) `STATE.taxEq.Q`, `.Pb` | то же | нет | COL.inkSoft, 1, штрих 4 3 |
| 2385 · `drawTaxPoints` | линия-проекция (Q1, Pb) → (0, Pb) | (г) | то же | нет | то же |
| 2386 · `drawTaxPoints` | линия-проекция (Q1, Ps) → (0, Ps) | (г) `STATE.taxEq.Ps` | то же | нет | то же |
| 2388, 2389 · `drawTaxPoints` | отметки у оси P: Pb с индексом b, Ps с индексом s | `axisValueY(…, fmt(Pb), 'b')`, `(…, fmt(Ps), 's')` | то же | `coord-num`, `data-raw` («60_b», «40_s») | D.1 |
| 2390 · `drawTaxPoints` | отметка у оси Q: Q1 с индексом 1 | `axisValueX(…, fmt(Q), '1')` | то же | то же | D.1 |
| 2393 · `drawTaxPoints` | точка покупателя | (г) (Q1, Pb) | то же | нет | r 4, fill COL.D, stroke COL.halo 1,5 |
| 2395 · `drawTaxPoints` | точка продавца | (г) (Q1, Ps) | то же | нет | r 4, fill COL.S |
| 2399 · `drawTaxPoints` | отрезок-скобка: клин ставки | (г) (Q1, Ps) – (Q1, Pb) | то же | нет | COL.ink, 2,5 |
| 2406 · `drawTaxPoints` | подпись клина «t=20», «s=20», «τ=20 %» | `haloText`: (sx(Q1) + 16 px, середина клина); текст `rateLetter() + '=' + fmt(STATE.tax) + единица` | то же | `data-raw` | FS.small, 600, COL.ink |
| 2409 · `drawTaxPoints` | зона захвата клина, служебное невидимое | rect 26 px × \|sy(Pb) − sy(Ps)\| вокруг x = sx(Q1); `attachTaxDrag` → `setTax` | то же | нет | fill transparent |
| 2416 · `drawTaxPoints` | ручка клина | (г) (Q1, середина между Pb и Ps) | то же | в файле нет; `data-service="handle"` и `data-skip-export` позже ставит `markServiceNodes` (60-overlays.js:2002) | r 7, fill COL.reg, stroke COL.halo 2 |

### B.4 Потолок и пол цены

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 3411 · `drawPcAreas` | группа с обрезкой | нет | `STATE.pcActive` | нет | нет |
| 3416 · `drawPcAreas` | область CS | верх (а) `STATE.D` (`quadPrice`); низ (г) `STATE.pc.Preg`; Q ∈ [0, `pc.Qtrade`], 101 узел | `showCS` | `data-legend` CS | COL.D, 0,16 |
| 3420 · `drawPcAreas` | область PS | низ (а) `STATE.S` (`quadPrice`); верх (г) `Preg` | `showPS` | `data-legend` PS | COL.S, 0,16 |
| 3427 · `drawPcAreas` | область DWL | между `STATE.S` и `STATE.D` (`evalCurve`); Q ∈ [min(Qtrade, Q\*), max(Qtrade, Q\*)], 101 узел | hi > lo; галочки нет | `data-legend` DWL | COL.inkSoft, 0,28 |
| 3439 · `drawPriceControl` | группа без обрезки | нет | `STATE.pcMode` и есть `STATE.pc` | нет | нет |
| 3443 · `drawPriceControl` | линия цены (потолок или пол), на всю ширину окна | (г) (0, Preg) – (`CONFIG.Qmax`, Preg) | `STATE.pc` (цена задана, `pRegSet`) | нет | COL.reg у потолка, COL.MR у пола; 2,5; сплошная |
| 3446 · `drawPriceControl` | отметка у оси P: Preg с индексом c или f | `axisValueY(g, ox, yReg, Preg, …)`, передано ЧИСЛО | то же | `coord-num`, `data-raw` («30_c») | D.1 |
| 3454, 3455 · `drawPriceControl` | 2 линии-проекции (Qs, Preg) → (Qs, 0), (Qd, Preg) → (Qd, 0) | (г) `pc.Qs`, `pc.Qd` | `STATE.pcActive` | нет | COL.inkSoft, 1, штрих 4 3 |
| 3456, 3457 · `drawPriceControl` | отметки у оси Q: Qs с индексом s, Qd с индексом d | `axisValueX(…, fmt(Qs), 's')`, `(…, fmt(Qd), 'd')` | то же | `coord-num`, `data-raw` | D.1 |
| 3460 · `drawPriceControl` | отрезок-скобка «дефицит / избыток», лежит на самой оси Q | (г) (min(Qs, Qd), 0) – (max(Qs, Qd), 0) | то же | нет | COL.bad у потолка, COL.MR у пола; 5; opacity 0,5 |
| 3462 · `drawPriceControl` | индикатор под осью «Дефицит = N» / «Избыток = N» | `haloText`: x середина отрезка, y = sy(0) + 24 px, baseline hanging; N = `fmt(pc.gap)` | то же | `data-raw` | FS.small, 600 |
| 3464 · `drawPriceControl` | точка фактической сделки | (г) (`pc.Qtrade`, Preg) | то же | нет | r 4, fill COL.ink, stroke COL.halo 1,5 |
| 3471 · `drawPriceControl` | зона захвата линии цены, служебное | rect от sx(0) до sx(Qmax), ±12 px по вертикали; `attachPcDrag` → `setPReg` | есть `STATE.pc` | нет | fill transparent |
| 3475 · `drawPriceControl` | ручка линии цены | x посередине [sx(0), sx(`CONFIG.Qmax`)], то есть Q = 0,5·Qmax; P = Preg | то же | ставит `markServiceNodes` | r 7, fill цвет линии, stroke COL.halo 2 |

### B.5 Квота

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 3579 · `drawQuotaAreas` | группа с обрезкой | нет | `STATE.quotaActive` | нет | нет |
| 3584 · `drawQuotaAreas` | область CS | верх (а) `STATE.D` через `evalCurve` (без обрезки нулём); низ (г) `STATE.qt.P`; Q ∈ [0, `qt.Qq`], 101 узел | `showCS` | `data-legend` CS | COL.D, 0,16 |
| 3589 · `drawQuotaAreas` | область PS | низ (а) `STATE.S` через `evalCurve`; верх (г) `qt.P` | `showPS` | `data-legend` PS | COL.S, 0,16 |
| 3597 · `drawQuotaAreas` | область DWL | между `STATE.S` и `STATE.D`; Q ∈ [min(Qq, Q\*), max(Qq, Q\*)] | hi > lo | `data-legend` DWL | COL.inkSoft, 0,28 |
| 3608 · `drawQuotaLines` | группа без обрезки | нет | `STATE.quotaMode` и есть `STATE.qt` | нет | нет |
| 3612 · `drawQuotaLines` | вертикальная линия квоты | (г) (Qq, 0) – (Qq, `CONFIG.Pmax`) | есть `STATE.qt` (`quotaSet`) | нет | COL.reg, 2,5 |
| 3614 · `drawQuotaLines` | отметка у оси Q: Qq с индексом «к» | `axisValueX(…, fmt(q.Qq), 'к')` | то же | `coord-num`, `data-raw` («40_к») | D.1 |
| 3623 · `drawQuotaLines` | область «коридор возможных цен», `<rect>` | (г) [0, Qq] × [Plo, Phi]: `qt.Qq`, `qt.Plo`, `qt.Phi` | `quotaActive` | `data-legend` «Коридор возможных цен» | fill COL.reg, opacity 0,12 |
| 3630 · `drawQuotaLines` | 2 пунктира границ коридора (в цикле) | (г) (0, Plo) – (Qq, Plo), (0, Phi) – (Qq, Phi) | то же | нет | COL.reg, 1, штрих 4 3 |
| 3632 · `drawQuotaLines` | 2 отметки у оси P: Plo с индексом s, Phi с индексом d (в цикле) | `axisValueY(g, ox, y, val, idx)`, передано ЧИСЛО | то же | `coord-num`, `data-raw` | D.1 |
| 3635 · `drawQuotaLines` | линия выбранной цены, на всю ширину окна | (г) (0, P) – (`CONFIG.Qmax`, P), P = `qt.P` | то же | нет; отметки у оси для этой цены нет | COL.reg, 2,5 |
| 3637 · `drawQuotaLines` | точка сделки | (г) (Qq, P) | то же | нет | r 4, fill COL.ink, stroke COL.halo 1,5 |
| 3640 · `drawQuotaLines` | зона захвата цены, служебное | rect от sx(0) до sx(Qmax), ±12 px; `attachQuotaDrag` → `setQuotaPos` | то же | нет; видимой ручки у квоты нет | fill transparent |

### B.6 Эластичность

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 3057 · `drawElasticityZones` | группа с обрезкой | нет | `STATE.elast.unit` | нет | нет |
| 3060 · `drawElasticityZones` | область: зона «эластичный» под спросом | верх (а) `STATE.D` (`evalCurve`); низ P = 0; Q ∈ [0, `elast.unit.Q`], 101 узел | всегда при `unit`, галочки нет | `data-legend` НЕТ | fill COL.tax, opacity 0,10 |
| 3061 · `drawElasticityZones` | область: зона «неэластичный» | то же, Q ∈ [`unit.Q`, `elast.qDmax`] | то же | `data-legend` НЕТ | fill COL.reg, 0,10 |
| 3064 (вызовы 3067, 3068) · `drawElasticityZones` | 2 подписи зон: «эластичный», «неэластичный» | x = sx(`unit.Q`/2) и sx((`unit.Q` + `qDmax`)/2); y = sy(0) − 8 px; anchor middle | то же | `data-raw` НЕТ; узлы лежат в группе с обрезкой | FS.small, 600, fill COL.tax / COL.reg, opacity 0,8, ореол 2,5 |
| 3074 · `drawElasticityPoint` | группа без обрезки | нет | `STATE.elast`, `p` конечно | нет | нет |
| 3078 · `drawElasticityPoint` | линия-проекция единичной точки на ось Q | (г) (`unit.Q`, `unit.P`) → (`unit.Q`, 0) | `elast.unit` | нет | COL.MR, 1, штрих 3 3 |
| 3080 · `drawElasticityPoint` | точка единичной эластичности | (г) (`unit.Q`, `unit.P`) | то же | нет | r 4, fill COL.MR |
| 3081 · `drawElasticityPoint` | подпись «\|Ed\|=1 · MR=0 · TR макс» | точка + (7, −7) px | то же | `data-raw` (свой `<text>` + `renderLabelText`, 3083) | FS.small, 600, COL.MR |
| 3089 (помощник 3087) · `drawElasticityPoint` | 2 линии-проекции тянущейся точки | (г) (`elast.q`, `elast.p`) → (q, 0) и → (0, p) | `STATE.elast` | нет | COL.inkSoft, 1, штрих 4 3 |
| 3090, 3091 · `drawElasticityPoint` | отметки у осей Q и P, без индекса | `axisValueX(…, fmt(e.q), '')`, `axisValueY(…, fmt(e.p), '')` | то же | `coord-num`, `data-raw` | D.1 |
| 3092 · `drawElasticityPoint` | подпись «\|Ed\|=N» | точка + (9, −9) px; N = `fmt(e.absEd)` | то же | `data-raw` НЕТ | FS.base, 600, COL.ink |
| 3094 · `drawElasticityPoint` | зона захвата, служебное | circle r 13 в точке; `attachElastDrag` → `STATE.elastQ` | то же | `markServiceNodes` помечает именно её | fill transparent |
| 3096 · `drawElasticityPoint` | точка на спросе (её и тянут) | (г) (`elast.q`, `elast.p`) | то же | служебной не помечается | r 5,5, fill COL.ink, stroke COL.halo 2 |
| 3111 · `drawElasticityPointS` | группа без обрезки | нет | `STATE.elastS` (нужны `STATE.S` и `STATE.showElastS`, галочка `#chk-elast-s`) | нет | нет |
| 3115 (помощник 3113) · `drawElasticityPointS` | 2 линии-проекции | (г) (`elastS.q`, `elastS.p`) → оси | то же | нет | COL.inkSoft, 1, штрих 4 3 |
| 3119, 3120 · `drawElasticityPointS` | отметки у осей Q и P, без индекса | `axisValueX/Y(…, fmt(…), '')` | то же | `coord-num`, `data-raw` | D.1 |
| 3121 · `drawElasticityPointS` | подпись «\|Es\|=N» | точка + (9, +15) px | то же | `data-raw` НЕТ | FS.base, 600, COL.S |
| 3123 · `drawElasticityPointS` | зона захвата, служебное | circle r 13; `attachElastDragS` → `STATE.elastQS` | то же | помечает `markServiceNodes` | fill transparent |
| 3125 · `drawElasticityPointS` | точка на предложении | (г) (`elastS.q`, `elastS.p`) | то же | нет | r 5,5, fill COL.S, stroke COL.halo 2 |

### B.7 Внешние эффекты

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 3203 · `drawExtAreas` | группа с обрезкой | нет | `STATE.ext`, `Qopt != null` | нет | нет |
| 3208 · `drawExtAreas` | область DWL внешнего эффекта | низ `e.msc`, верх `e.msb`: замыкания из `recompute` (449–452). (а) `STATE.mscExpr` / `STATE.msbExpr`, когда включены `STATE.mscOn` / `msbOn`; иначе это S и D. Q ∈ [min(Qopt, Qmkt), max(Qopt, Qmkt)], 101 узел | hi > lo (3205) | `data-legend` «Потери от внешнего эффекта (DWL)» | COL.inkSoft, 0,28 |
| 3215 · `drawExtCurves` | группа с обрезкой | нет | `STATE.ext` | нет | нет |
| 3222 · `drawExtCurves` | кривая MSC | (а) строка `STATE.mscExpr` есть в состоянии, но в функцию приходит только замыкание `e.msc`; 401 точка, Q ∈ [0, `CONFIG.Qmax`] | `e.mscOn` (галочка `#chk-msc`) | НЕТ: ни `data-expr`, ни `data-curve` | COL.reg, 2,5, сплошная |
| 3223 · `drawExtCurves` | подпись «MSC» | `labelCurve(g, e.msc, 'MSC', COL.reg, {from: 0.9})` | то же | `curve-name`, `data-raw` | кегль 12, 600, COL.reg |
| 3226 · `drawExtCurves` | кривая MSB | (а) `STATE.msbExpr`, рисуется по `e.msb`; 401 точка | `e.msbOn` (`#chk-msb`) | НЕТ | COL.MR, 2,5, сплошная |
| 3227 · `drawExtCurves` | подпись «MSB» | `labelCurve(…, {from: 0.9})` | то же | `curve-name`, `data-raw` | COL.MR |
| 3231 · `drawExtCurves` | кривая: S плюс корректирующий сдвиг (налог или субсидия Пигу) | (б) лямбда `q => evalCurve(STATE.S, q) + e.corrective`; закрытая запись существует как `STATE.S.expr` плюс число `STATE.ext.corrective`, строкой не собирается; 401 точка | `e.applyPigou` (`#ext-pigou`) и \|corrective\| > 1e-9 | НЕТ; подписи у кривой нет | COL.tax, 2, штрих 6 4 |
| 3239 · `drawExtPoints` | группа без обрезки | нет | `STATE.ext` | нет | нет |
| 3244 (помощник 3240) · `drawExtPoints` | 2 линии-проекции рыночной точки | (г) (`ext.Qmkt`, `ext.Pmkt`) → оси | то же | нет | COL.inkSoft, 1, штрих 4 3 |
| 3245 · `drawExtPoints` | точка рынка | (г) (Qmkt, Pmkt) | то же | нет | r 4,5, fill COL.ink |
| 3246 · `drawExtPoints` | подпись «Qрын» | точка + (8, −8) px | то же | `data-raw` НЕТ | FS.base, 600, COL.ink |
| 3248, 3252 · `drawExtPoints` | отметки у осей Q и P с индексом «рын» | `axisValueX(…, fmt(e.Qmkt), 'рын')`, `axisValueY(…, fmt(e.Pmkt), 'рын')` | то же | `coord-num`, `data-raw` («50_{рын}») | D.1 |
| 3256 · `drawExtPoints` | 2 линии-проекции оптимума | (г) (`ext.Qopt`, `ext.Popt`) → оси | `Qopt != null` | нет | COL.tax, 1, штрих 4 3 |
| 3257 · `drawExtPoints` | точка оптимума | (г) (Qopt, Popt) | то же | нет | r 4,5, fill COL.tax |
| 3258 · `drawExtPoints` | подпись «Qопт» | точка + (8, −8) px | то же | `data-raw` НЕТ | FS.base, 600, COL.tax |
| 3260, 3261 · `drawExtPoints` | отметки у осей с индексом «опт» | `axisValueX/Y(…, fmt(…), 'опт')` | то же | `coord-num`, `data-raw` | D.1 |
| 3265 · `drawExtPoints` | точка-кольцо: новое равновесие с налогом Пигу | (г) (`ext.pigouEq.Q`, `ext.pigouEq.P`) | `e.applyPigou && e.pigouEq` | нет | r 7, без заливки, stroke COL.tax 2 |

### B.8 Малая открытая экономика

| Строка · функция | Что это | Геометрия в данных | Видимость | Пометки | Стиль |
|---|---|---|---|---|---|
| 619 · `drawOpenAreas` | группа с обрезкой | нет | `STATE.open` без `error` | нет | нет |
| 626 · `drawOpenAreas` | область CS | верх (а) `STATE.D` (`evalCurve`); низ (г) `Pdom` = `o.P1 ?? o.Pw`; Q ∈ [0, qD], qD = `o.Qd1 ?? o.Qd`, 101 узел | `showCS && qD > 0` | `data-legend` CS | COL.D, 0,16 |
| 630 · `drawOpenAreas` | область PS | низ (а) `STATE.S` (`evalCurve`); верх (г) `Pdom`; Q ∈ [0, qS], qS = `o.Qs1 ?? o.Qs` | `showPS && qS > 0` | `data-legend` PS | COL.S, 0,16 |
| 640 · `drawOpenAreas` | область «деньги»: доход бюджета (тариф) или рента квоты, `<rect>` | (г) [min(Qs1, Qd1), max(Qs1, Qd1)] × [min(P1, Pw), max(P1, Pw)]: `o.Qs1`, `o.Qd1`, `o.P1`, `o.Pw` | `o.P1 != null`, `STATE.showOpenMoney` (`#chk-open-money`), `o.vol1 > 1e-9` | `data-legend` «Доход бюджета» / «Рента квоты» (по `STATE.openTool`, 642) | COL.tax, 0,22 |
| 653 (вызовы 655, 656) · `drawOpenAreas` | 2 области DWL: производственный и потребительский треугольники | (г) `o.Pw` и (а) `STATE.S` на Q ∈ [Qs, Qs1]; `o.Pw` и (а) `STATE.D` на Q ∈ [Qd1, Qd]; концы упорядочиваются (650); по 101 узлу | `o.P1 != null`, `STATE.showOpenDwl` (`#chk-open-dwl`), `!o.prohibitive`, длина > 1e-9 | `data-legend` «Потери общества (DWL)», один ключ на обе фигуры | COL.dwl, 0,38 |
| 663 · `drawOpenLines` | группа без обрезки | нет | `STATE.open` | нет | нет |
| 665 · `drawOpenLines` | линия мировой цены, на всю ширину окна | (г) (0, Pw) – (`CONFIG.Qmax`, Pw), Pw = `STATE.open.Pw` | всегда | нет | COL.reg, 2,5 |
| 667 · `drawOpenLines` | отметка у оси P: Pw с индексом w | `axisValueY(…, fmt(o.Pw), 'w')` | всегда | `coord-num`, `data-raw` («30_w») | D.1 |
| 668 · `drawOpenLines` | зона захвата в ветке ошибки, служебное; после неё выход | rect ±12 px вокруг линии; `attachOpenPwDrag` | `o.error` | нет | fill transparent |
| 672 · `drawOpenLines` | линия внутренней цены при тарифе или квоте | (г) (0, P1) – (`CONFIG.Qmax`, P1), `o.P1` | `o.P1 != null` | нет | COL.MR, 2,5, штрих 7 4 |
| 674 · `drawOpenLines` | отметка у оси P: P1 с индексом 1 | `axisValueY(…, fmt(o.P1), '1')` | то же | `coord-num`, `data-raw` | D.1 |
| 682 (помощник 680) · `drawOpenLines` | 2 линии-проекции на ось Q | (г) (qS, Pdom) → (qS, 0), (qD, Pdom) → (qD, 0) | нет `error` | нет | COL.inkSoft, 1, штрих 4 3 |
| 683, 684 · `drawOpenLines` | отметки у оси Q: qS с индексом s, qD с индексом d | `axisValueX(…, fmt(qS), 's')`, `(…, fmt(qD), 'd')` | то же | `coord-num`, `data-raw` | D.1 |
| 687 · `drawOpenLines` | отрезок-скобка объёма торговли (импорт или экспорт) | (г) (min(qS, qD), Pdom) – (max(qS, qD), Pdom) | длина > 1 ПИКСЕЛЯ (686) | нет | COL.D при импорте, COL.S при экспорте; 6; opacity 0,45 |
| 689 · `drawOpenLines` | подпись отрезка «Импорт = N» / «Экспорт = N» | `haloText`: x середина отрезка, y = sy(Pdom) − 12 px; N = `fmt(\|qD − qS\|)` | то же | `data-raw` | FS.small, 600 |
| 692, 693 · `drawOpenLines` | 2 точки на кривых | (г) (qS, Pdom), (qD, Pdom) | нет `error` | нет | r 4, fill COL.S и COL.D, stroke COL.halo 1,5 |
| 696 · `drawOpenLines` | точка автаркии, полая | (г) (`o.aut.Q`, `o.aut.P`), это `STATE.eq` | `STATE.showGhost && o.aut` | нет | r 4, fill COL.halo, stroke COL.ghost 1,5 |
| 697 · `drawOpenLines` | подпись «Автаркия» | точка + (7, −6) px | то же | `data-raw` НЕТ | FS.base, 600, COL.inkSoft, ореол 2,5 |
| 701 · `drawOpenLines` | зона захвата мировой цены, служебное | rect от sx(0) до sx(Qmax), ±12 px; `attachOpenPwDrag` → `setOpenPw` | нет `error` | нет | fill transparent |
| 704 · `drawOpenLines` | ручка мировой цены | x на 0,86 ширины [sx(0), sx(`CONFIG.Qmax`)], то есть Q = 0,86·Qmax; P = Pw | то же | ставит `markServiceNodes` | r 7, fill COL.reg, stroke COL.halo 2 |

Дополнительно, не из этого файла, но в его группы: `flushDrawnKeyPoints` (20-plane.js:766) после сцены дописывает в группу, переданную в `axisValueX`, невидимые `circle.kp-mark` (r 0, `data-skip-export`, `data-key-point`, `data-kp-x/y/panel`).

---

## C. Области подробно

Все области с кривой границей строит `d3.area()` с линейной интерполяцией: `.x(d => sx(d))`, `.y0(…)`, `.y1(…)`, без `.defined()`. Узлы равномерные по Q: помощник `samp(a, b)` даёт 101 точку (620, 2343, 3058, 3412, 3580; в `drawAreas` 2139–2140, в `drawExtAreas` 3206). Путь получается из 202 вершин: верхняя граница слева направо, нижняя справа налево. Два места используют `<rect>` (640, 3623). Ручной сборки строки `d` в файле нет.

| № | Строка | Область | Верхняя граница | Нижняя граница | Отрезок по Q | Способ | Форма | Точные вершины в месте рисования |
|---|---|---|---|---|---|---|---|---|
| 1 | 2145 | CS, без вмешательства | max(0, D(Q)) (`quadPrice`) | P\* | [0, Q\*] | d3.area, 101 | кривая сверху | да: `Q`, `P` из `STATE.eq` (2134) |
| 2 | 2150 | PS, без вмешательства | P\* | max(0, S(Q)) | [0, Q\*] | d3.area, 101 | кривая снизу | да |
| 3 | 2348 | CS, налог/субсидия | max(0, D) | Pb | [0, Q1] | d3.area, 101 | кривая сверху | да: `Q`, `Pb`, `Ps` из `STATE.taxEq` (2336) |
| 4 | 2352 | PS, налог/субсидия | Ps | max(0, S) | [0, Q1] | d3.area, 101 | кривая снизу | да |
| 5 | 2358 | сбор / расход бюджета | max(Pb, Ps) | min(Pb, Ps) | [0, Q1] | d3.area, 101 | всегда прямоугольник | да: `lowP`, `highP` (2356) |
| 6 | 2365 | DWL, налог/субсидия | D(Q) | S(Q) | [min(Q1, Q0), max(Q1, Q0)] | d3.area, 101 | между двумя кривыми | да: `lo`, `hi` (2361) |
| 7 | 3416 | CS, потолок/пол | max(0, D) | Preg | [0, Qtrade] | d3.area, 101 | кривая сверху | да: `Preg`, `Qtrade` из `STATE.pc` (3410) |
| 8 | 3420 | PS, потолок/пол | Preg | max(0, S) | [0, Qtrade] | d3.area, 101 | кривая снизу | да |
| 9 | 3427 | DWL, потолок/пол | D | S | [min(Qtrade, Q\*), max(Qtrade, Q\*)] | d3.area, 101 | между двумя кривыми | да: `lo`, `hi` (3423) |
| 10 | 3584 | CS, квота | D (без обрезки нулём) | P (выбранная) | [0, Qq] | d3.area, 101 | кривая сверху | да: `Qq`, `P` из `STATE.qt` (3578) |
| 11 | 3589 | PS, квота | P | S (без обрезки нулём) | [0, Qq] | d3.area, 101 | кривая снизу | да |
| 12 | 3597 | DWL, квота | D | S | [min(Qq, Q\*), max(Qq, Q\*)] | d3.area, 101 | между двумя кривыми | да: `lo`, `hi` (3593) |
| 13 | 3623 | коридор цен | Phi | Plo | [0, Qq] | `<rect>` | всегда прямоугольник | да: `q.Plo`, `q.Phi`, `q.Qq` |
| 14 | 626 | CS, открытая экономика | D (без обрезки) | Pdom | [0, qD] | d3.area, 101 | кривая сверху | да: `Pdom`, `qD` (621–622) |
| 15 | 630 | PS, открытая экономика | Pdom | S (без обрезки) | [0, qS] | d3.area, 101 | кривая снизу | да: `qS` (623) |
| 16 | 640 | доход бюджета / рента квоты | max(P1, Pw) | min(P1, Pw) | [min(Qs1, Qd1), max(Qs1, Qd1)] | `<rect>` | всегда прямоугольник | да, но в пикселях `xa, xb, ya, yb` (638–639); числа `o.Qs1`, `o.Qd1`, `o.P1`, `o.Pw` рядом |
| 17 | 653 ← 655 | DWL производственный | S | Pw (порядок y0/y1 задан как y0 = Pw, y1 = кривая) | [min(Qs, Qs1), max(Qs, Qs1)] | d3.area, 101 | кривая с одной стороны | да: `a1`, `b1` (650), `o.Pw` |
| 18 | 653 ← 656 | DWL потребительский | D | Pw | [min(Qd1, Qd), max(Qd1, Qd)] | d3.area, 101 | кривая с одной стороны | да |
| 19 | 3060 | зона «эластичный» | D | 0 | [0, unit.Q] | d3.area, 101 | кривая сверху | да: `e.unit.Q` |
| 20 | 3061 | зона «неэластичный» | D | 0 | [unit.Q, qDmax] | d3.area, 101 | кривая сверху | да: `e.unit.Q`, `e.qDmax` |
| 21 | 3208 | DWL внешнего эффекта | msb(Q) | msc(Q) | [min(Qopt, Qmkt), max(Qopt, Qmkt)] | d3.area, 101 | между двумя кривыми | да: `lo`, `hi` (3204) |

Итого 20 мест в коде, 21 фигура (место 653 вызывается дважды). «Кривая» граница становится прямой, только если сама D, S, MSB или MSC прямая; при стартовых формулах (D = 100 − Q, S = Q) все фигуры многоугольники.

Факты о границах:

- **Обрезка нулём непоследовательна.** `quadPrice` (max(0, цена)) стоит у CS/PS в 2144, 2149, 2347, 2351, 3415, 3419. `evalCurve` без обрезки стоит у CS/PS в квоте (3583, 3588) и открытой экономике (625, 629), у всех DWL и у зон эластичности. При этом числа квоты `STATE.qt.cs/ps` считаются через `quadPrice` (319–320), то есть в квоте число и заливка берут разные границы, когда S или D уходит ниже нуля на [0, Qq].
- **Узлы заливки не совпадают с изломами.** Сетка равномерная (Q·i/100), а излом суммарной кривой (`sumBreaks`) или нуль кривой (где срабатывает `quadPrice`) в узел не попадает. Числа при этом считаются по участкам (`integrateBroken` + `quadBreaks`, 63–64, 1663, 1685).
- **Цвет заливки может быть переписан после рисования:** `applyAreaColors` (60-overlays.js:893) ставит `fill` из `STATE.areaColor[ключ data-legend]`.
- **Наложения.** При субсидии прямоугольник расхода (2358) лежит между Pb и Ps и перекрывает CS и PS. DWL в открытой экономике состоит из двух отдельных фигур под одним ключом легенды.

`areaBetween` (10-math-core.js:732, сигнатура `(g, lo, hi, n = 400)`): режет отрезок по сменам знака (`signChanges`, :716) и складывает модули интегралов (`integrate`, :694, 1000 шагов). Возвращает число, геометрии не строит. В этом файле 7 вызовов, все в расчёте, ни одного в рисовании: 213 (`STATE.dwl`), 278 (`STATE.pc.dwl`), 324 (`STATE.qt.dwl`), 341 (DWL монополии в `STATE.mono`), 463 (`STATE.ext.dwl`), 597 и 598 (`dwlProd`, `dwlCons` открытой экономики). Вне файла: 42-scenes-mono.js:260, 382, 399, 451; 46-scenes-labor.js:58, 96, 137, 180.

---

## D. Элементы у осей, под осью и на краю поля

### D.1 Отметки у осей (числа точек за осью)

Рисуют `axisValueX` (20-plane.js:831) и `axisValueY` (20-plane.js:858), оба через `haloText`. В этом файле 22 вызова, 23 подписи.

| Строка | Функция | Ось | Величина (переменная в месте вызова) | Что передано | Индекс | Пример при стартовых формулах |
|---|---|---|---|---|---|---|
| 667 | `drawOpenLines` | P | `o.Pw` | `fmt(...)` | w | 30_w |
| 674 | `drawOpenLines` | P | `o.P1` | `fmt(...)` | 1 | нет в старте |
| 683 | `drawOpenLines` | Q | `qS` | `fmt(...)` | s | 30_s |
| 684 | `drawOpenLines` | Q | `qD` | `fmt(...)` | d | 70_d |
| 819 | `drawEquilibrium` | Q | `STATE.eq.Q` | `fmt(...)` | нет | 50 |
| 820 | `drawEquilibrium` | P | `STATE.eq.P` | `fmt(...)` | нет | 50 |
| 2388 | `drawTaxPoints` | P | `taxEq.Pb` | `fmt(...)` | b | 60_b |
| 2389 | `drawTaxPoints` | P | `taxEq.Ps` | `fmt(...)` | s | 40_s |
| 2390 | `drawTaxPoints` | Q | `taxEq.Q` | `fmt(...)` | 1 | 40_1 |
| 3090 | `drawElasticityPoint` | Q | `elast.q` | `fmt(...)` | нет | 50; в старте совпадает с отметкой равновесия и как дубль не рисуется |
| 3091 | `drawElasticityPoint` | P | `elast.p` | `fmt(...)` | нет | 50; то же |
| 3119 | `drawElasticityPointS` | Q | `elastS.q` | `fmt(...)` | нет | 65 |
| 3120 | `drawElasticityPointS` | P | `elastS.p` | `fmt(...)` | нет | 65 |
| 3248 | `drawExtPoints` | Q | `ext.Qmkt` | `fmt(...)` | рын | 50_{рын} |
| 3252 | `drawExtPoints` | P | `ext.Pmkt` | `fmt(...)` | рын | 50_{рын} |
| 3260 | `drawExtPoints` | Q | `ext.Qopt` | `fmt(...)` | опт | 50_{опт} |
| 3261 | `drawExtPoints` | P | `ext.Popt` | `fmt(...)` | опт | 50_{опт} |
| 3446 | `drawPriceControl` | P | `pc.Preg` | ЧИСЛО | c или f | 30_c |
| 3456 | `drawPriceControl` | Q | `pc.Qs` | `fmt(...)` | s | 30_s |
| 3457 | `drawPriceControl` | Q | `pc.Qd` | `fmt(...)` | d | 70_d |
| 3614 | `drawQuotaLines` | Q | `qt.Qq` | `fmt(...)` | к | 40_к |
| 3632 | `drawQuotaLines` (цикл, 2 подписи) | P | `qt.Plo`, `qt.Phi` | ЧИСЛО | s, d | 40_s, 60_d |

Примеры в последнем столбце выведены из стартовых значений сцен (84-picker.js:40–101), запуском не проверены.

Как ставятся:

- Ось Q: `haloText(g, px, oy + 8, текст, 'middle', 'hanging')`, то есть x = sx(значение), y = sy(0) + 8 px. Ось P: `haloText(g, ox − 8, py, текст, 'end', 'middle', {noFlip: true})`, то есть x = sx(0) − 8 px, y = sy(значение). В помощник приходит уже ПИКСЕЛЬ и, в 20 вызовах из 22, готовая строка `fmt` (2 знака, запятая, узкий пробел разрядов); число из неё разбирается обратно (`coordValue`, 20-plane.js:659).
- Текст собирает `axisValueText` (20-plane.js:883): `N_i` для индекса в один знак, `N_{idx}` для длинного. Рисуется нижним индексом через `mathTspans`; `data-raw` хранит запись с подчёркиванием. Класс `coord-num`.
- Совпало с делением шкалы (ближе 7 px либо 2 % размаха): деление удаляется (`dropTickAt`, 20-plane.js:632), подпись красится `--accent` и ставится жирность 700 (20-plane.js:842, 875).
- Такой же текст уже стоит ближе 6 px: подпись НЕ рисуется, помощник возвращает `null` (`coordAlreadyAt`, 20-plane.js:679, 838, 865).
- Каждый вызов записывает пару (пиксель, число, индекс) в `_kpX` / `_kpY` (`noteAxisX/Y`, 20-plane.js:814–823); `flushDrawnKeyPoints` собирает из них ключевые точки по пунктирам. Число там берётся из напечатанной строки.
- Дальше подпись двигают общие проходы (раздел E.3).

### D.2 Индикаторы, отрезки и ручки у края

| Строка | Элемент | Положение |
|---|---|---|
| 3460 | отрезок дефицита / избытка | на самой оси Q: y = sy(0); толщина 5 px, группа без обрезки, половина толщины ниже оси |
| 3462 | «Дефицит = N» / «Избыток = N» | под осью: x середина [sx(Qs), sx(Qd)] (данные), y = sy(0) + 24 px (пиксели). Под такие подписи отведена нижняя полоса `BOTTOM_BAND = 44` px (20-plane.js:72) |
| 689 | «Импорт = N» / «Экспорт = N» | внутри поля: середина отрезка, y = sy(Pdom) − 12 px |
| 2406 | «t=20» | внутри поля: x = sx(Q1) + 16 px, y середина клина |
| 3064 | подписи зон эластичности | над осью Q на 8 px |
| 665, 672, 3443, 3635 | горизонтальные линии цен | от sx(0) до sx(`CONFIG.Qmax`); группы без обрезки |
| 3612 | вертикаль квоты | от sy(0) до sy(`CONFIG.Pmax`) |
| 704, 3475 | ручки линий | на 0,86 и 0,5 ширины [sx(0), sx(`CONFIG.Qmax`)] |
| 668, 701, 2409, 3471, 3640 | прозрачные зоны захвата | полосы ±12 px (у клина 26 px по горизонтали) |

Легенда, названия осей, деления шкал, заголовок графика рисуются не здесь: `drawLegend` (60-overlays.js:992) собирает узлы `[data-legend]` и ищет место в пикселях (`legendCorner`, 60-overlays.js:1072); оси и деления рисует `drawAxes` (20-plane.js:900).

---

## E. Подписи

### E.1 Чем ставятся

| Способ | Места в файле | Текст | `data-raw` | Правило места |
|---|---|---|---|---|
| `axisValueX` / `axisValueY` → `haloText` | 22 вызова (D.1) | число и индекс: «60_b», «50_{рын}» | да | данные по одной оси, 8 px от оси по другой |
| `haloText` напрямую | 689, 2406, 3462 | обычная строка: «Импорт = 40», «t=20», «τ=20 %», «Дефицит = 40» | да | данные плюс сдвиг в px (−12, +16, +24); затем зажим внутрь холста по оценке ширины `длина × 5,9 + 6` и размерам `W`, `H` (1188–1195) |
| `pointName` | 829 | «E» | да | точка + (8, −8) px |
| `labelCurve` (30-curves.js:928) | 2239, 3223, 3227 | «S + t», «S − s», «D − t», «D + s», «S/(1−τ)», «S·(1+τ)», «S/(1+τ)», «S·(1−τ)» и варианты `curveD`; «MSC», «MSB» | да | `curveAnchor` (30-curves.js:304) ищет точку на кривой в координатах данных: 241 проба от `from·Qmax` (0,82 или 0,9) влево до 0,04·Qmax, первая внутри окна с запасом 2 %, край уточняется бисекцией. Дальше пиксели: сглаживание 0,35 пути за кадр с памятью прошлого места (`_labelPos`, ключ здесь сам текст подписи), переворот влево у правого края по измеренной ширине, над или под кривой (−7 / +14 px) |
| свой `<text>` + `renderLabelText` | 3081–3083 | «\|Ed\|=1 · MR=0 · TR макс» | да | точка + (7, −7) px |
| голый `.text()` | 697–698, 3064–3068 (2 подписи), 3092–3093, 3121–3122, 3246–3247, 3258–3259, 3725–3727 | «Автаркия», «эластичный», «неэластичный», «\|Ed\|=N», «\|Es\|=N», «Qрын», «Qопт», «E₀» | НЕТ | точка плюс фиксированный сдвиг в px; у зон (sx(Q), sy(0) − 8 px) |

Итого 15 мест, 16 подписей (без отметок у осей): 8 мест с `data-raw`, 7 мест без.

### E.2 Откуда текст и как разбирается

- Подписи холста в этом файле: обычные строки и лёгкая разметка (`_`, `^`, `*`, `{…}`, юникодные индексы вроде «E₀»). Строк с `$…$` среди подписей холста нет; доллары встречаются только в HTML табло (`eqSectionTitle` 1275, `interventionKeyValues` 1308, `update*Panel`) и набираются KaTeX вне SVG.
- `renderLabelText` (1159): `texToCanvasText` → запись `data-raw` (1168) → если есть `*`, `^`, `_`, то `mathTspans`; иначе если `qtyIsQuantity` (10-math-core.js:1027), то `qtyTspans` по `qtyParts` (10-math-core.js:1041); иначе если есть кириллица, то `mixedMathTspans`; иначе `.text(s)`.
- Исходная запись хранится атрибутом `data-raw` на самом узле `<text>`; его читают выгрузка (`labelPlainText`, 70-scenes-math.js:1358) и правило шрифтов (`chartLabelSource`, 60-overlays.js:2811).

### E.3 Что происходит с подписью после сцены

Общие проходы `redrawAll` (60-overlays.js:19–29, 74–75) меняют уже нарисованные узлы:

- `applyLabelSize` (30-curves.js:841): множит `font-size` всех `<text>`, кроме `.axis-num`, на `STATE.labelSize / 12`; стартовое `labelSize` 14 (00-config.js:22).
- `unclipLabels` (30-curves.js:447): подпись, которую частично режет её группа с обрезкой, переносится в слой `g.free-labels`. В группах с обрезкой у нас лежат подписи кривых (2239, 3223, 3227) и подписи зон (3064).
- `spreadLabels` (30-curves.js:533): прижимает `coord-num` к левому краю холста, удаляет деления шкалы под ними, сдвигает налезающие подписи шагами по 13 px (числа у осей только прочь от своей оси).
- `applyLabelInk` (30-curves.js:806): меняет `fill` подписи ради контраста, прозрачность сворачивает в цвет (касается подписей зон с opacity 0,8).
- `typesetChartLabels` (60-overlays.js:2852): ставит шрифт KaTeX по `data-raw`.
- `selfCanvas` (96-self.js:139), режим «Сначала сам»: `coord-num` заменяет обозначением или «?», в подписях «дефицит / избыток N» число меняет на «?».

---

## F. Трудные случаи

1. **Суммарные кривые (`sdsum`).** Рисует их `drawCurves` (30-curves.js:1072), этот файл готовит данные (`sumRebuildSide`, 1747).
   - Все группы прямые: `cur.expr` это цепочка условий `(Q >= lo and Q < hi) ? тело : (…)` с хвостом `NaN` (1643–1652), `cur.compiled` из неё же. Тела печатает `sumSegExpr` (1701): либо `fmtLinear`, либо дробь вида `(Q - c)/a`. Изломы в `cur.sumBreaks` (1626), участок «рынка нет» [0, `sumGhostTo`] с телом `'0'` (1619–1623), правый конец в `cur.sumDomainTo` (1638).
   - У суммарного предложения последний участок без правого края: условие `(Q >= lo)` без `and`, `sumDomainTo = Infinity` (1638, 1646–1647). Разбор участков в выгрузке от состояния (`texCondBounds`, 70-scenes-math.js:1596–1606) требует условие вида `A and B` и на первом же несоответствии возвращает `null` для всей записи (`texCondPieces`, 70-scenes-math.js:1617–1618); по чтению кода такая запись на участки не разбирается, не проверено запуском.
   - Хоть одна группа не прямая: `cur.fn = q => interpY(pts, q)`, `cur.sumNumeric = true`, а в поле `cur.expr` лежит фраза `'сумма посчитана по точкам'` (1778–1780). `pts` даёт `sumPolyline` (1719): 401 цена равномерно от 0 до max(100, 2·макс. запретительная) плюс запретительные цены групп, для каждой цены точка (ΣQ, P), сортировка по Q, при нужде приставка [0, 0]. Изломы найдены приближённо (1785–1791).
   - Кривые-группы: обычные записи `STATE.curves` с `sumGroup`, `sumIdx`, цветом `sumGroupColor` (1915) и обозначением `sumShortTag` (1886: «D_1», «S_2», «D», «S»).
2. **Кривая, введённая как Q(P).** У кривой с `srcForm === 'QP'` поле `expr` это выражение от P (80-ui.js:60–64, 117–122); канон для расчёта: `linear {a, b}` у прямой, численное обращение `fn = q => invertQofP(…)` у остальных (10-math-core.js:471–486). `recompute` собирает `texExpr` кривой после вмешательства как `'(' + STATE.S.expr + ') + (сдвиг)'` (156–161, 171–183) без проверки `srcForm`. По коду выходит, что для Q(P)-кривой в `texExpr` (а значит в `data-expr` на 2227 и в блок «Итоговая функция», 2931–2937) попадает выражение от P, не являющееся записью P(Q). Не проверено запуском. Перевод в pgfplots (`mathToPgf`, 70-scenes-math.js:1497–1542) переменной считает только `Q`, `x`, `L`, `X` и переданное имя; букву P он не знает и возвращает `null`.
3. **Кривые без строки и с неиспользуемой строкой.** MSC и MSB (3222, 3226) рисуются по замыканиям `e.msc` / `e.msb`, хотя строки `STATE.mscExpr` / `STATE.msbExpr` есть; при выключенной галочке те же замыкания возвращают S или D (449–452), и область DWL (3208) берёт границы именно так. Кривая Пигу (3231) существует только лямбдой. В формулах возможны буквы-параметры из `STATE.params`.
4. **Запись после вмешательства.** `texExpr` проходит `simplifyRecord` (10-math-core.js:88): может остаться шаблоном со скобками, если сверка не сошлась; у процентных форм множитель `factor` это число JS (например 1/(1 − τ)), в записи возможны длинные десятичные или дроби. `texExpr` пустая, если у базовой кривой нет `expr` (156, 171). У кусочной базовой кривой условие поднимается наверх (`liftConditional`).
5. **Вертикальные и горизонтальные линии.** Линии цен (665, 672, 3443, 3635) идут от Q = 0 до `CONFIG.Qmax`, вертикаль квоты (3612) от P = 0 до `CONFIG.Pmax`: второй конец задаёт окно, а не модель. Кривые 2227, 3222, 3226, 3231 сэмплируются на [0, `CONFIG.Qmax`], то есть тоже до края окна.
6. **Области из нескольких кусков и с изломами.** Два треугольника DWL в открытой экономике (653) под одним ключом легенды; прямоугольник денег при субсидии поверх CS и PS; граница с изломом от `quadPrice` и от суммарной кривой при равномерных узлах (раздел C); у DWL «между двумя кривыми» знак разности не проверяется, фигура строится как есть.
7. **Продолжения за первую четверть.** 856 (к пересечению вне четверти, Q или P отрицательны) и 2316 (к центру поворота, Q < 0), точка центра 2327 на оси Q левее нуля. Первое помечено `data-skip-export`, второе нет.
8. **Зависимость от пикселей и окна.**
   - Порог показа отрезка торговли: длина больше 1 px (686). Крестик ±5 px (867). Ручки на долях ширины окна (704, 3475). Зоны захвата в пикселях.
   - Сдвиги подписей в пикселях (все места E.1), оценка ширины в `haloText` по числу знаков, зажим по `W`, `H`.
   - Отметки у осей: пороги 7 px и 6 px, удаление деления, возможный отказ рисовать (D.1).
   - Подписи кривых: место зависит от прошлых кадров (сглаживание и память, E.1).
   - Расчёт тоже местами смотрит на окно: запасной конец спроса `qDmax = CONFIG.Qmax` (412), зажим точки на предложении (428–429), верх поиска цены под импортную квоту `Math.max(Pw, CONFIG.Pmax)` (572), отрезок поиска центра поворота у непрямой S (2269).
9. **Служебные узлы.** В самом файле нет ни одного `data-service`. Ручки помечает `markServiceNodes` (60-overlays.js:2002) уже после рисования: по наличию d3-drag у узла; у прозрачного rect помечается следующий сосед-кружок r ≥ 5 (704, 2416, 3475), у кружков r 13 помечается сам кружок захвата (3094, 3123), а видимые точки 3096 и 3125 остаются обычными точками. Прозрачные rect пометок не получают.
10. **Пометки для выгрузки в файле.** `data-expr`: одно место (2227). `data-curve`: нет (ставит только `drawCurves`). `data-numeric`: нет. `data-skip-export`: одно место (860). `data-legend`: 18 мест. `data-raw`: через `renderLabelText`. Прочие: `data-offquad` (859, 869), `data-pivot` (2319, 2329), `data-mathset` (1014, 1017, 1056, 1059); по найденному в `calc2/static/calc2/*.js` `data-offquad` и `data-pivot` никто не читает.
11. **Расхождение комментария и кода.** Комментарий 281–288 говорит, что без исходного равновесия проекции Qd, Qs и зона дефицита рисуются по `STATE.pc`; код рисует их только при `STATE.pcActive` (3448), а `pcActive` ставится лишь при наличии `STATE.eq` (276–279). Без равновесия остаются линия цены, её отметка и ручка.

---

## G. Итоговые числа по файлу

| Что | Мест в коде | Фигур при полном показе | Примечание |
|---|---|---|---|
| Кривые | 6 | 8 | 856 (×2), 2227, 2316 (×2), 3222, 3226, 3231 |
| из них со строкой-формулой в состоянии | 5 | 7 | 856, 2227, 2316, 3222, 3226; формулу объявляет через `markExpr` только 2227 |
| из них с закрытой записью без строки | 1 | 1 | 3231 (S + число) |
| из них численные | 0 | 0 | любая становится численной, если базовая D или S это численная сумма (`sumNumeric`) или нелинейная Q(P) |
| Области | 20 | 21 | 18 через `d3.area`, 2 через `<rect>` |
| из них всегда с прямыми сторонами | 3 | 3 | 2358, 3623, 640 |
| из них с кривой границей | 17 | 18 | 13 мест «кривая против горизонтали», 4 места «между двумя кривыми» (2365, 3427, 3597, 3208) |
| Линии-проекции (пунктир к оси) | 12 | 22 | 680, 813, 815, 2381, 3078, 3087, 3113, 3240, 3451, 3630, 3718, 3720 |
| Линии уровня на всю ширину или высоту окна | 5 | 5 | 665, 672, 3443, 3612, 3635 |
| Отрезки-скобки | 3 | 3 | 687 (импорт / экспорт), 2399 (клин ставки), 3460 (дефицит / избыток) |
| Крестик пересечения вне четверти | 1 | 2 линии | 868 |
| Точки | 15 | 15 | 692, 693, 696, 2327, 2393, 2395, 3080, 3096, 3125, 3245, 3257, 3265, 3464, 3637, 3723; полые: 696, 2327, 3265, 3723 |
| Подписи (кроме отметок у осей) | 15 | 16 | кривых 3, точек 8, отрезков и индикаторов 3, зон 1 место (2 подписи); с `data-raw` 8 мест, без 7 |
| Отметки у осей | 22 | 23 | 11 `axisValueX`, 11 `axisValueY`; 20 получают строку `fmt`, 2 число |
| Строки легенды | 0 | до 4 на сцену | легенду рисует 60-overlays.js; здесь 18 пометок `data-legend`, 9 разных ключей |
| Ручки видимые | 3 | 3 | 704, 2416, 3475; плюс 2 тянущиеся точки 3096, 3125 |
| Зоны захвата (невидимые) | 7 | до 2 на сцену | rect: 668, 701, 2409, 3471, 3640; circle: 3094, 3123 |
| Группы `<g>` | 20 | | 11 с обрезкой, 9 без |

Кривые D, S и группы сложения в счёт не входят: их рисует `drawCurves` (30-curves.js:1072) с пометкой `data-curve`.
